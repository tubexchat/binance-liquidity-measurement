"""SQLite persistence layer for bliq liquidity snapshots."""

from __future__ import annotations

import sqlite3
from contextlib import closing
from pathlib import Path

from bliq.infra.errors import StorageError
from bliq.metrics.types import LiquidityReport

SCHEMA_VERSION = 1

DDL = [
    """
    CREATE TABLE IF NOT EXISTS snapshots (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        symbol          TEXT    NOT NULL,
        ts_ms           INTEGER NOT NULL,
        mid_price       REAL    NOT NULL,
        spread_bps      REAL    NOT NULL,
        obi_5           REAL,
        obi_10          REAL,
        obi_20          REAL,
        depth_01pct_bid REAL, depth_01pct_ask REAL,
        depth_05pct_bid REAL, depth_05pct_ask REAL,
        depth_1pct_bid  REAL, depth_1pct_ask  REAL,
        depth_2pct_bid  REAL, depth_2pct_ask  REAL,
        capacity_20bps_buy  REAL,
        capacity_20bps_sell REAL,
        amihud          REAL,
        taker_buy_ratio REAL,
        liquidity_score REAL
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_snapshots_symbol_ts ON snapshots(symbol, ts_ms)",
    """
    CREATE TABLE IF NOT EXISTS slippage_points (
        snapshot_id   INTEGER NOT NULL REFERENCES snapshots(id) ON DELETE CASCADE,
        side          TEXT    NOT NULL,
        notional_usdt REAL    NOT NULL,
        slippage_bps  REAL    NOT NULL,
        avg_fill_px   REAL    NOT NULL,
        PRIMARY KEY (snapshot_id, side, notional_usdt)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS alerts (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        ts          INTEGER NOT NULL,
        symbol      TEXT    NOT NULL,
        rule_name   TEXT    NOT NULL,
        rule_expr   TEXT    NOT NULL,
        snapshot_id INTEGER REFERENCES snapshots(id),
        payload     TEXT
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_alerts_ts ON alerts(ts)",
    "CREATE INDEX IF NOT EXISTS idx_alerts_symbol_ts ON alerts(symbol, ts)",
    "CREATE TABLE IF NOT EXISTS schema_version (version INTEGER PRIMARY KEY)",
]

_DEPTH_COLS = {
    0.001: ("depth_01pct_bid", "depth_01pct_ask"),
    0.005: ("depth_05pct_bid", "depth_05pct_ask"),
    0.01: ("depth_1pct_bid", "depth_1pct_ask"),
    0.02: ("depth_2pct_bid", "depth_2pct_ask"),
}


class SnapshotStore:
    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def init_schema(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with closing(self._connect()) as conn:
                conn.execute("PRAGMA journal_mode = WAL")
                for stmt in DDL:
                    conn.execute(stmt)
                cur = conn.execute("SELECT version FROM schema_version")
                if cur.fetchone() is None:
                    conn.execute(
                        "INSERT INTO schema_version (version) VALUES (?)",
                        (SCHEMA_VERSION,),
                    )
                conn.commit()
        except sqlite3.Error as exc:
            raise StorageError(f"failed to initialize schema: {exc}") from exc

    def insert_report(self, report: LiquidityReport) -> int:
        row = {
            "symbol": report.symbol,
            "ts_ms": report.ts_ms,
            "mid_price": report.mid_price,
            "spread_bps": report.spread.spread_bps,
            "obi_5": report.obi.by_levels.get(5),
            "obi_10": report.obi.by_levels.get(10),
            "obi_20": report.obi.by_levels.get(20),
            "capacity_20bps_buy": report.slippage.capacity_buy_usdt,
            "capacity_20bps_sell": report.slippage.capacity_sell_usdt,
            "amihud": None,
            "taker_buy_ratio": None,
            "liquidity_score": None,
        }
        for pct, (bid_col, ask_col) in _DEPTH_COLS.items():
            bid, ask = report.depth.by_pct.get(pct, (None, None))
            row[bid_col] = bid
            row[ask_col] = ask

        cols = ", ".join(row.keys())
        placeholders = ", ".join(["?"] * len(row))
        sql = f"INSERT INTO snapshots ({cols}) VALUES ({placeholders})"
        try:
            with closing(self._connect()) as conn:
                cur = conn.execute(sql, tuple(row.values()))
                snap_id = cur.lastrowid
                conn.executemany(
                    "INSERT INTO slippage_points "
                    "(snapshot_id, side, notional_usdt, slippage_bps, avg_fill_px) "
                    "VALUES (?, ?, ?, ?, ?)",
                    [
                        (
                            snap_id,
                            p.side,
                            p.notional_usdt,
                            p.slippage_bps,
                            p.avg_fill_px,
                        )
                        for p in report.slippage.points
                    ],
                )
                conn.commit()
                if snap_id is None:
                    raise StorageError("lastrowid unexpectedly None after INSERT")
                return snap_id
        except sqlite3.Error as exc:
            raise StorageError(f"failed to insert report: {exc}") from exc
