"""typer CLI entry for bliq."""

from __future__ import annotations

import asyncio
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from bliq.data.symbols import SymbolSelection, resolve_symbols
from bliq.infra.config import Config, load_config
from bliq.infra.errors import BliqError
from bliq.infra.logging import setup_logging
from bliq.modes.contrarian import run_contrarian_scan
from bliq.modes.snapshot import run_snapshot_once
from bliq.modes.watch import run_watch

app = typer.Typer(
    name="bliq",
    help="Binance USDT-M perpetual futures liquidity measurement.",
    no_args_is_help=True,
    add_completion=False,
)
console = Console()

DEFAULT_CONFIG = Path("config/default.yaml")


@app.callback()
def _main() -> None:
    """Forces typer to treat subcommands as required even with one command."""


def _bootstrap(config_path: Path) -> Config:
    try:
        cfg = load_config(config_path)
    except BliqError as exc:
        console.print(f"[red]config error:[/red] {exc}")
        raise typer.Exit(code=2) from exc
    setup_logging(cfg.logging)
    return cfg


def _selection(
    symbols: str | None,
    all_flag: bool,
    top: int | None,
    from_file: Path | None,
) -> SymbolSelection:
    return SymbolSelection(
        explicit=[s.strip() for s in symbols.split(",") if s.strip()]
        if symbols
        else [],
        all_symbols=all_flag,
        top_n=top,
        from_file=from_file,
    )


def _print_report_table(reports: list) -> None:
    table = Table(title="Liquidity Snapshot")
    table.add_column("symbol", style="cyan")
    table.add_column("mid", justify="right")
    table.add_column("spread(bps)", justify="right")
    table.add_column("obi_5", justify="right")
    table.add_column("cap_buy($)", justify="right")
    table.add_column("cap_sell($)", justify="right")
    for r in reports:
        table.add_row(
            r.symbol,
            f"{r.mid_price:,.6g}",
            f"{r.spread.spread_bps:.2f}",
            f"{r.obi.by_levels.get(5, 0):+.3f}",
            f"{r.slippage.capacity_buy_usdt:,.0f}",
            f"{r.slippage.capacity_sell_usdt:,.0f}",
        )
    console.print(table)


@app.command("snapshot")
def snapshot(
    symbols: str = typer.Option(None, "--symbols", help="Comma-separated list"),
    all_flag: bool = typer.Option(False, "--all", help="All tradable symbols (M2+)"),
    top: int = typer.Option(None, "--top", help="Top-N by 24h volume (M2+)"),
    from_file: Path = typer.Option(None, "--from-file", help="YAML or text file"),  # noqa: B008
    config_path: Path = typer.Option(  # noqa: B008
        DEFAULT_CONFIG, "--config", help="Path to config yaml"
    ),
    db: Path = typer.Option(  # noqa: B008
        None, "--db", help="Override storage.db_path from config"
    ),
    fail_fast: bool = typer.Option(False, "--fail-fast"),
) -> None:
    """Fetch a single liquidity snapshot for each requested symbol."""
    cfg = _bootstrap(config_path)
    try:
        sel = _selection(symbols, all_flag, top, from_file)
        target_symbols = resolve_symbols(sel)
    except BliqError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=2) from exc

    try:
        reports = asyncio.run(
            run_snapshot_once(
                target_symbols, cfg, db_path=db, fail_fast=fail_fast
            )
        )
    except BliqError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc

    _print_report_table(reports)
    console.print(
        f"[green]persisted {len(reports)} snapshot(s) to "
        f"{db or cfg.storage.db_path}[/green]"
    )


@app.command("watch")
def watch(
    symbols: str = typer.Option(..., "--symbols", help="Comma-separated list of symbols to watch"),
    config_path: Path = typer.Option(  # noqa: B008
        DEFAULT_CONFIG, "--config", help="Path to config yaml"
    ),
    interval: float = typer.Option(10.0, "--interval", help="Snapshot interval in seconds"),
    large_trade: float = typer.Option(
        50_000.0, "--large-trade", help="Large trade threshold in USDT"
    ),
    cvd_surge: float = typer.Option(
        200_000.0, "--cvd-surge", help="CVD surge threshold in USDT (5min window)"
    ),
) -> None:
    """Watch symbols in real time and detect whale activity signals."""
    cfg = _bootstrap(config_path)
    target_symbols = [s.strip() for s in symbols.split(",") if s.strip()]
    if not target_symbols:
        console.print("[red]no symbols provided[/red]")
        raise typer.Exit(code=2)

    try:
        asyncio.run(
            run_watch(
                target_symbols,
                cfg,
                snapshot_interval=interval,
                large_trade_threshold=large_trade,
                cvd_surge_threshold=cvd_surge,
            )
        )
    except BliqError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc


@app.command("scan-whales")
def scan_whales(
    config_path: Path = typer.Option(  # noqa: B008
        DEFAULT_CONFIG, "--config", help="Path to config yaml"
    ),
    top_n: int = typer.Option(20, "--top-n", help="Number of top movers to scan"),
    max_ls: float = typer.Option(
        1.5, "--max-ls", help="Max long/short account ratio (skip if >=)"
    ),
    loop_minutes: int = typer.Option(0, "--loop", help="Run every N minutes (0 = run once)"),
) -> None:
    """Scan top movers for contrarian whale buying and alert via Telegram."""
    cfg = _bootstrap(config_path)

    async def _run():
        while True:
            signals = await run_contrarian_scan(cfg, top_n=top_n, max_long_short_ratio=max_ls)
            console.print(f"[green]Scan complete: {len(signals)} signal(s)[/green]")
            if loop_minutes <= 0:
                break
            console.print(f"[dim]Next scan in {loop_minutes} minutes...[/dim]")
            await asyncio.sleep(loop_minutes * 60)

    try:
        asyncio.run(_run())
    except BliqError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc
