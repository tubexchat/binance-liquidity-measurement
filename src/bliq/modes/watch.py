"""Watch mode — continuous whale detection for selected symbols.

Combines periodic order book snapshots with real-time aggTrades streaming
to detect whale activity signals.
"""

from __future__ import annotations

import asyncio
import time

from loguru import logger
from rich.console import Console
from rich.live import Live
from rich.table import Table
from rich.text import Text

from bliq.data.binance_rest import BinanceRestClient
from bliq.data.binance_ws import stream_agg_trades
from bliq.data.rate_limiter import WeightRateLimiter
from bliq.infra.config import Config
from bliq.infra.errors import BinanceAPIError
from bliq.metrics.whale import (
    TradeFlowTracker,
    WhaleSignal,
    detect_cap_asymmetry,
    detect_depth_pulse,
    detect_obi_shift,
)
from bliq.modes.snapshot import build_report


def _signal_color(signal: WhaleSignal) -> str:
    if signal.strength >= 0.7:
        return "bold red"
    if signal.strength >= 0.4:
        return "bold yellow"
    return "bold cyan"


def _signal_icon(signal: WhaleSignal) -> str:
    icons = {
        "obi_shift": "<<OBI>>",
        "depth_pulse": "<<DEP>>",
        "large_trade": "<<BIG>>",
        "cvd_surge": "<<CVD>>",
        "cap_asymmetry": "<<CAP>>",
    }
    return icons.get(signal.signal_type, "<<???>>")


def _side_arrow(side: str) -> str:
    return "BUY ^" if side == "buy" else "SELL v"


def _build_signal_table(signals: list[WhaleSignal], max_rows: int = 20) -> Table:
    table = Table(title="Whale Signals", expand=True)
    table.add_column("Time", style="dim", width=8)
    table.add_column("Symbol", width=12)
    table.add_column("Type", width=7)
    table.add_column("Side", width=8)
    table.add_column("Str", width=5)
    table.add_column("Description")

    recent = signals[-max_rows:] if len(signals) > max_rows else signals
    for sig in reversed(recent):
        ts = time.strftime("%H:%M:%S", time.localtime(sig.ts_ms / 1000))
        color = _signal_color(sig)
        strength_bar = "#" * int(sig.strength * 5)
        table.add_row(
            ts,
            sig.symbol,
            Text(_signal_icon(sig), style=color),
            Text(_side_arrow(sig.side), style="green" if sig.side == "buy" else "red"),
            Text(strength_bar, style=color),
            Text(sig.description, style=color),
        )
    return table


def _build_status_table(
    trackers: dict[str, TradeFlowTracker],
    last_reports: dict[str, object],
) -> Table:
    table = Table(title="Live Status", expand=True)
    table.add_column("Symbol", width=12)
    table.add_column("Mid", justify="right", width=12)
    table.add_column("Spread", justify="right", width=8)
    table.add_column("OBI-5", justify="right", width=8)
    table.add_column("CVD(5m)", justify="right", width=14)
    table.add_column("Buy Vol", justify="right", width=12)
    table.add_column("Sell Vol", justify="right", width=12)

    for sym in sorted(trackers):
        tracker = trackers[sym]
        report = last_reports.get(sym)
        mid = f"{report.mid_price:,.4f}" if report else "-"
        spread = f"{report.spread.spread_bps:.2f}" if report else "-"
        obi = f"{report.obi.by_levels.get(5, 0):+.3f}" if report else "-"
        cvd = tracker.cvd
        cvd_style = "green" if cvd > 0 else "red" if cvd < 0 else ""
        table.add_row(
            sym,
            mid,
            spread,
            obi,
            Text(f"${cvd:+,.0f}", style=cvd_style),
            f"${tracker.buy_volume:,.0f}",
            f"${tracker.sell_volume:,.0f}",
        )
    return table


async def run_watch(
    symbols: list[str],
    cfg: Config,
    *,
    snapshot_interval: float = 10.0,
    large_trade_threshold: float = 50_000.0,
    cvd_surge_threshold: float = 200_000.0,
) -> None:
    """Run continuous whale detection.

    Streams aggTrades via WebSocket and periodically snapshots the order book.
    Prints whale signals to the terminal in real time.
    """
    console = Console()
    all_signals: list[WhaleSignal] = []
    last_reports: dict[str, object] = {}
    trackers: dict[str, TradeFlowTracker] = {
        sym: TradeFlowTracker(
            symbol=sym,
            large_trade_threshold_usdt=large_trade_threshold,
            cvd_surge_threshold_usdt=cvd_surge_threshold,
        )
        for sym in symbols
    }

    rate_limiter = WeightRateLimiter(capacity_per_minute=cfg.data.rate_limit_weight_per_min)

    def _render():
        from rich.layout import Layout
        from rich.panel import Panel

        layout = Layout()
        layout.split_column(
            Layout(_build_status_table(trackers, last_reports), name="status", ratio=1),
            Layout(
                _build_signal_table(all_signals) if all_signals else Panel("Waiting for signals...", title="Whale Signals"),
                name="signals",
                ratio=2,
            ),
        )
        return layout

    async def _snapshot_loop(client: BinanceRestClient):
        """Periodically fetch order book snapshots and run signal detection."""
        while True:
            for sym in symbols:
                try:
                    ob = await client.fetch_depth(sym, limit=cfg.metrics.orderbook_limit)
                    report = build_report(ob, cfg)
                    prev = last_reports.get(sym)
                    last_reports[sym] = report

                    # Run snapshot-based signals
                    if prev is not None:
                        for detector in (detect_obi_shift, detect_depth_pulse):
                            sig = detector(report, prev)
                            if sig:
                                all_signals.append(sig)
                                logger.info(f"WHALE SIGNAL [{sig.signal_type}] {sig.description}")

                    sig = detect_cap_asymmetry(report)
                    if sig:
                        all_signals.append(sig)
                        logger.info(f"WHALE SIGNAL [{sig.signal_type}] {sig.description}")

                except BinanceAPIError as exc:
                    logger.warning(f"{sym}: snapshot failed ({exc})")

            await asyncio.sleep(snapshot_interval)

    async def _trade_loop():
        """Stream aggTrades and run trade-flow signals."""
        async for trade in stream_agg_trades(cfg.data.ws_base, symbols):
            tracker = trackers.get(trade.symbol)
            if tracker is None:
                continue
            sigs = tracker.ingest(trade)
            for sig in sigs:
                all_signals.append(sig)
                logger.info(f"WHALE SIGNAL [{sig.signal_type}] {sig.description}")

    console.print(f"\n[bold]Watching {len(symbols)} symbol(s) for whale activity...[/bold]")
    console.print(f"Snapshot interval: {snapshot_interval}s | Large trade: ${large_trade_threshold:,.0f} | CVD surge: ${cvd_surge_threshold:,.0f}")
    console.print("[dim]Press Ctrl+C to stop[/dim]\n")

    async with BinanceRestClient(
        base_url=cfg.data.rest_base,
        rate_limiter=rate_limiter,
        retry_attempts=cfg.data.retry_attempts,
        retry_backoff_base=cfg.data.retry_backoff_base,
    ) as client:
        snapshot_task = asyncio.create_task(_snapshot_loop(client))
        trade_task = asyncio.create_task(_trade_loop())

        try:
            with Live(_render(), console=console, refresh_per_second=2) as live:
                while True:
                    await asyncio.sleep(0.5)
                    live.update(_render())
        except (KeyboardInterrupt, asyncio.CancelledError):
            pass
        finally:
            snapshot_task.cancel()
            trade_task.cancel()

    console.print(f"\n[bold]Session ended. {len(all_signals)} whale signal(s) detected.[/bold]")
