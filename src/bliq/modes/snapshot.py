"""Snapshot mode — one-shot sampling for M1.

For each requested symbol:
  1. Fetch order book via REST.
  2. Run spread / depth / OBI / slippage pure metrics.
  3. Persist a `LiquidityReport` to SQLite.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from loguru import logger

from bliq.data.binance_rest import BinanceRestClient
from bliq.data.rate_limiter import WeightRateLimiter
from bliq.data.storage import SnapshotStore
from bliq.infra.config import Config
from bliq.infra.errors import BinanceAPIError
from bliq.metrics.depth import compute_depth
from bliq.metrics.obi import compute_obi
from bliq.metrics.slippage import compute_slippage
from bliq.metrics.spread import compute_spread
from bliq.metrics.types import LiquidityReport, OrderBook


def build_report(ob: OrderBook, cfg: Config) -> LiquidityReport:
    spread = compute_spread(ob)
    depth = compute_depth(ob, pcts=cfg.metrics.depth_pcts)
    obi = compute_obi(ob, levels=cfg.metrics.obi_levels)
    slippage = compute_slippage(
        ob,
        levels_usdt=cfg.metrics.slippage_levels_usdt,
        max_slippage_bps=cfg.metrics.max_slippage_bps,
    )
    return LiquidityReport(
        symbol=ob.symbol,
        ts_ms=ob.ts_ms,
        mid_price=spread.mid,
        spread=spread,
        depth=depth,
        obi=obi,
        slippage=slippage,
    )


async def run_snapshot_once(
    symbols: list[str],
    cfg: Config,
    *,
    db_path: Path | None = None,
    fail_fast: bool = False,
) -> list[LiquidityReport]:
    rate_limiter = WeightRateLimiter(
        capacity_per_minute=cfg.data.rate_limit_weight_per_min
    )
    store = SnapshotStore(db_path or Path(cfg.storage.db_path))
    store.init_schema()

    async with BinanceRestClient(
        base_url=cfg.data.rest_base,
        rate_limiter=rate_limiter,
        retry_attempts=cfg.data.retry_attempts,
        retry_backoff_base=cfg.data.retry_backoff_base,
    ) as client:
        sem = asyncio.Semaphore(cfg.data.max_concurrent_requests)

        async def _one(symbol: str) -> LiquidityReport | None:
            async with sem:
                try:
                    ob = await client.fetch_depth(
                        symbol, limit=cfg.metrics.orderbook_limit
                    )
                except BinanceAPIError as exc:
                    if fail_fast:
                        raise
                    logger.warning(f"{symbol}: fetch failed ({exc}), skipping")
                    return None
                report = build_report(ob, cfg)
                store.insert_report(report)
                logger.info(
                    f"{symbol}: mid={report.mid_price:.6g} "
                    f"spread={report.spread.spread_bps:.2f}bps "
                    f"cap_buy={report.slippage.capacity_buy_usdt:,.0f}"
                )
                return report

        results = await asyncio.gather(*[_one(s) for s in symbols])
    return [r for r in results if r is not None]
