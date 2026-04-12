"""Contrarian whale detection — find bearish coins with sudden large buys.

Workflow (runs every 5 minutes):
1. Fetch 24h ticker for all USDT-M perpetual pairs
2. Pick the top 20 by price change (biggest gainers — volatile, active)
3. For each: fetch order book + recent aggTrades
4. Detect "contrarian buying": OBI negative (sellers dominate) BUT recent
   large buy trades appeared — someone is accumulating against the trend
5. Send alerts to Telegram
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

import httpx
from loguru import logger

from bliq.data.binance_rest import BinanceRestClient
from bliq.data.rate_limiter import WeightRateLimiter
from bliq.infra.config import Config
from bliq.metrics.obi import compute_obi
from bliq.metrics.slippage import compute_slippage
from bliq.metrics.spread import compute_spread
from bliq.notify.telegram import send_telegram


@dataclass
class ContrarianSignal:
    symbol: str
    price_change_pct: float
    mid_price: float
    spread_bps: float
    obi_5: float
    cap_buy: float
    cap_sell: float
    large_buys_usdt: float
    large_buys_count: int
    total_buy_vol: float
    total_sell_vol: float
    long_short_ratio: float | None


async def _fetch_top_gainers(base_url: str, top_n: int = 20) -> list[dict]:
    """Fetch 24h tickers and return top N by absolute price change %."""
    url = f"{base_url}/fapi/v1/ticker/24hr"
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        tickers = resp.json()

    # Filter USDT perpetuals, exclude extreme movers (likely delisting)
    usdt_tickers = [
        t for t in tickers
        if t.get("symbol", "").endswith("USDT")
        and 0 < abs(float(t.get("priceChangePercent", 0))) < 100
        and float(t.get("quoteVolume", 0)) > 100_000  # must have some volume
    ]
    usdt_tickers.sort(key=lambda t: abs(float(t["priceChangePercent"])), reverse=True)
    return usdt_tickers[:top_n]


async def _fetch_long_short_ratio(base_url: str, symbol: str) -> float | None:
    """Fetch the latest global long/short account ratio for a symbol.

    Returns the ratio (long accounts / short accounts), or None on failure.
    """
    url = f"{base_url}/futures/data/globalLongShortAccountRatio"
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(url, params={"symbol": symbol, "period": "5m", "limit": 1})
            resp.raise_for_status()
            data = resp.json()
            if data:
                return float(data[0]["longShortRatio"])
    except Exception as exc:
        logger.warning(f"{symbol}: failed to fetch long/short ratio ({exc})")
    return None


async def _fetch_recent_trades(base_url: str, symbol: str, limit: int = 100) -> list[dict]:
    """Fetch recent aggregated trades."""
    url = f"{base_url}/fapi/v1/aggTrades"
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(url, params={"symbol": symbol, "limit": limit})
        resp.raise_for_status()
        return resp.json()


def _format_signal(sig: ContrarianSignal) -> str:
    """Format a contrarian signal as a Telegram message."""
    direction = "+" if sig.price_change_pct > 0 else ""
    buy_sell_ratio = sig.total_buy_vol / sig.total_sell_vol if sig.total_sell_vol > 0 else 999

    lines = [
        "*CONTRARIAN WHALE DETECTED*",
        "",
        f"*{sig.symbol}* | {direction}{sig.price_change_pct:.2f}% (24h)",
        f"Mid: `${sig.mid_price:.6g}`",
        f"Spread: `{sig.spread_bps:.2f} bps`",
        "",
        "*Bearish Signals:*",
        f"  OBI-5: `{sig.obi_5:+.3f}` (sellers dominate)",
        f"  Sell capacity: `${sig.cap_sell:,.0f}`",
        "",
        "*But Large Buys Detected:*",
        f"  Large buy trades: `{sig.large_buys_count}` totaling `${sig.large_buys_usdt:,.0f}`",
        f"  Buy/Sell ratio: `{buy_sell_ratio:.2f}x`",
        f"  Total buy: `${sig.total_buy_vol:,.0f}` | sell: `${sig.total_sell_vol:,.0f}`",
        f"  Long/Short acct ratio: `{sig.long_short_ratio:.3f}`" if sig.long_short_ratio is not None else "  Long/Short acct ratio: `N/A`",
        "",
        "_Someone is accumulating against the trend_",
    ]
    return "\n".join(lines)


async def run_contrarian_scan(
    cfg: Config,
    *,
    top_n: int = 20,
    obi_threshold: float = -0.15,
    large_trade_pct: float = 0.05,
    max_long_short_ratio: float = 1.5,
) -> list[ContrarianSignal]:
    """Scan top movers for contrarian whale buying.

    Args:
        top_n: Number of top gainers/losers to scan.
        obi_threshold: OBI must be below this (negative = sellers dominate).
        large_trade_pct: A trade is "large" if its notional exceeds this fraction
                         of the total recent volume.
        max_long_short_ratio: Skip symbols where global long/short account ratio
                              exceeds this value — too crowded on the long side.
    """
    logger.info(f"Starting contrarian scan: top {top_n} movers")

    # Step 1: Get top movers
    top_movers = await _fetch_top_gainers(cfg.data.rest_base, top_n)
    if not top_movers:
        logger.warning("No tickers returned")
        return []

    symbols_info = {t["symbol"]: float(t["priceChangePercent"]) for t in top_movers}
    logger.info(
        f"Top {len(symbols_info)} movers: "
        + ", ".join(f"{s}({v:+.1f}%)" for s, v in list(symbols_info.items())[:5])
        + "..."
    )

    # Step 2: Fetch order books and trades in parallel
    rate_limiter = WeightRateLimiter(capacity_per_minute=cfg.data.rate_limit_weight_per_min)
    signals: list[ContrarianSignal] = []

    async with BinanceRestClient(
        base_url=cfg.data.rest_base,
        rate_limiter=rate_limiter,
        retry_attempts=cfg.data.retry_attempts,
        retry_backoff_base=cfg.data.retry_backoff_base,
    ) as client:
        sem = asyncio.Semaphore(cfg.data.max_concurrent_requests)

        async def _analyze(symbol: str) -> ContrarianSignal | None:
            async with sem:
                try:
                    # Fetch order book
                    ob = await client.fetch_depth(symbol, limit=cfg.metrics.orderbook_limit)
                    if not ob.bids or not ob.asks:
                        return None
                    spread = compute_spread(ob)
                    obi = compute_obi(ob, levels=cfg.metrics.obi_levels)
                    slippage = compute_slippage(
                        ob,
                        levels_usdt=cfg.metrics.slippage_levels_usdt,
                        max_slippage_bps=cfg.metrics.max_slippage_bps,
                    )

                    obi_5 = obi.by_levels.get(5, 0.0)

                    # Must be bearish (OBI negative)
                    if obi_5 > obi_threshold:
                        return None

                    # Fetch global long/short account ratio
                    ls_ratio = await _fetch_long_short_ratio(cfg.data.rest_base, symbol)

                    # Fetch recent trades
                    trades = await _fetch_recent_trades(cfg.data.rest_base, symbol, limit=200)
                    if not trades:
                        return None

                    # Analyze trade flow
                    total_buy = 0.0
                    total_sell = 0.0
                    trade_notionals: list[float] = []

                    for t in trades:
                        price = float(t["p"])
                        qty = float(t["q"])
                        notional = price * qty
                        is_buyer_maker = t["m"]  # True = taker sold
                        if is_buyer_maker:
                            total_sell += notional
                        else:
                            total_buy += notional
                        trade_notionals.append(notional)

                    total_vol = total_buy + total_sell
                    if total_vol == 0:
                        return None

                    # Define "large" as > large_trade_pct of total volume
                    large_threshold = total_vol * large_trade_pct
                    large_buys = [
                        (float(t["p"]) * float(t["q"]))
                        for t in trades
                        if not t["m"] and float(t["p"]) * float(t["q"]) >= large_threshold
                    ]

                    # Must have meaningful large buys
                    if not large_buys or sum(large_buys) < total_vol * 0.1:
                        return None

                    return ContrarianSignal(
                        symbol=symbol,
                        price_change_pct=symbols_info[symbol],
                        mid_price=spread.mid,
                        spread_bps=spread.spread_bps,
                        obi_5=obi_5,
                        cap_buy=slippage.capacity_buy_usdt,
                        cap_sell=slippage.capacity_sell_usdt,
                        large_buys_usdt=sum(large_buys),
                        large_buys_count=len(large_buys),
                        total_buy_vol=total_buy,
                        total_sell_vol=total_sell,
                        long_short_ratio=ls_ratio,
                    )

                except Exception as exc:
                    logger.warning(f"{symbol}: analysis failed ({exc})")
                    return None

        results = await asyncio.gather(*[_analyze(s) for s in symbols_info])
        signals = [r for r in results if r is not None]

    # Step 3: Send alerts (only push symbols with long/short ratio < threshold)
    if signals:
        logger.info(f"Found {len(signals)} contrarian signal(s)")
        pushed = 0
        for sig in signals:
            if sig.long_short_ratio is not None and sig.long_short_ratio >= max_long_short_ratio:
                logger.info(
                    f"SKIP push {sig.symbol}: long/short ratio {sig.long_short_ratio:.3f} >= {max_long_short_ratio}"
                )
                continue
            if sig.long_short_ratio is None:
                logger.info(f"SKIP push {sig.symbol}: long/short ratio unavailable")
                continue
            msg = _format_signal(sig)
            logger.info(f"CONTRARIAN: {sig.symbol} OBI={sig.obi_5:+.3f} large_buys=${sig.large_buys_usdt:,.0f} L/S={sig.long_short_ratio:.3f}")
            await send_telegram(msg)
            pushed += 1
        logger.info(f"Pushed {pushed}/{len(signals)} signal(s) to Telegram")
    else:
        logger.info("No contrarian signals detected this round")

    return signals
