"""SQLite persistence for contrarian whale signals (for backtesting)."""

from __future__ import annotations

import sqlite3
import time
from contextlib import closing
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any

from bliq.infra.errors import StorageError

DDL = [
    """
    CREATE TABLE IF NOT EXISTS contrarian_signals (
        id                INTEGER PRIMARY KEY AUTOINCREMENT,
        ts_ms             INTEGER NOT NULL,
        symbol            TEXT    NOT NULL,
        direction         TEXT    NOT NULL,
        price_change_pct  REAL,
        mid_price         REAL,
        spread_bps        REAL,
        obi_5             REAL,
        cap_buy           REAL,
        cap_sell          REAL,
        large_buys_usdt   REAL,
        large_buys_count  INTEGER,
        total_buy_vol     REAL,
        total_sell_vol    REAL,
        long_short_ratio  REAL,
        macd_15m          REAL,
        pushed            INTEGER NOT NULL,
        skip_reason       TEXT
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_contrarian_ts ON contrarian_signals(ts_ms)",
    "CREATE INDEX IF NOT EXISTS idx_contrarian_symbol_ts ON contrarian_signals(symbol, ts_ms)",
]


class SignalStore:
    """Append-only log of contrarian signals for later backtesting."""

    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.path)

    def init_schema(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with closing(self._connect()) as conn:
                conn.execute("PRAGMA journal_mode = WAL")
                for stmt in DDL:
                    conn.execute(stmt)
                conn.commit()
        except sqlite3.Error as exc:
            raise StorageError(f"failed to init signal schema: {exc}") from exc

    def insert_signal(
        self,
        signal: Any,
        *,
        pushed: bool,
        skip_reason: str | None = None,
        ts_ms: int | None = None,
    ) -> int:
        data = asdict(signal) if is_dataclass(signal) else dict(signal)
        row = {
            "ts_ms": ts_ms if ts_ms is not None else int(time.time() * 1000),
            "symbol": data.get("symbol"),
            "direction": data.get("direction"),
            "price_change_pct": data.get("price_change_pct"),
            "mid_price": data.get("mid_price"),
            "spread_bps": data.get("spread_bps"),
            "obi_5": data.get("obi_5"),
            "cap_buy": data.get("cap_buy"),
            "cap_sell": data.get("cap_sell"),
            "large_buys_usdt": data.get("large_buys_usdt"),
            "large_buys_count": data.get("large_buys_count"),
            "total_buy_vol": data.get("total_buy_vol"),
            "total_sell_vol": data.get("total_sell_vol"),
            "long_short_ratio": data.get("long_short_ratio"),
            "macd_15m": data.get("macd_15m"),
            "pushed": 1 if pushed else 0,
            "skip_reason": skip_reason,
        }
        cols = ", ".join(row.keys())
        placeholders = ", ".join(["?"] * len(row))
        sql = f"INSERT INTO contrarian_signals ({cols}) VALUES ({placeholders})"
        try:
            with closing(self._connect()) as conn:
                cur = conn.execute(sql, tuple(row.values()))
                conn.commit()
                if cur.lastrowid is None:
                    raise StorageError("lastrowid unexpectedly None after INSERT")
                return cur.lastrowid
        except sqlite3.Error as exc:
            raise StorageError(f"failed to insert signal: {exc}") from exc

    @staticmethod
    def _where(
        symbol: str | None,
        direction: str | None,
        pushed: bool | None,
        skip_reason: str | None,
        start_ms: int | None,
        end_ms: int | None,
    ) -> tuple[str, list[Any]]:
        clauses: list[str] = []
        params: list[Any] = []
        if symbol is not None:
            clauses.append("symbol = ?")
            params.append(symbol)
        if direction is not None:
            clauses.append("direction = ?")
            params.append(direction)
        if pushed is not None:
            clauses.append("pushed = ?")
            params.append(1 if pushed else 0)
        if skip_reason is not None:
            clauses.append("skip_reason = ?")
            params.append(skip_reason)
        if start_ms is not None:
            clauses.append("ts_ms >= ?")
            params.append(start_ms)
        if end_ms is not None:
            clauses.append("ts_ms < ?")
            params.append(end_ms)
        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        return where, params

    def list_signals(
        self,
        *,
        symbol: str | None = None,
        direction: str | None = None,
        pushed: bool | None = None,
        skip_reason: str | None = None,
        start_ms: int | None = None,
        end_ms: int | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list[dict[str, Any]], int]:
        where, params = self._where(symbol, direction, pushed, skip_reason, start_ms, end_ms)
        try:
            with closing(self._connect()) as conn:
                conn.row_factory = sqlite3.Row
                total = conn.execute(
                    f"SELECT COUNT(*) FROM contrarian_signals{where}", params
                ).fetchone()[0]
                rows = conn.execute(
                    f"SELECT * FROM contrarian_signals{where} "
                    "ORDER BY ts_ms DESC, id DESC LIMIT ? OFFSET ?",
                    [*params, limit, offset],
                ).fetchall()
                return [dict(r) for r in rows], int(total)
        except sqlite3.Error as exc:
            raise StorageError(f"failed to list signals: {exc}") from exc

    def latest_per_symbol(
        self, *, symbol: str | None = None, limit: int = 200
    ) -> list[dict[str, Any]]:
        sub_where = " WHERE symbol = ?" if symbol else ""
        params: list[Any] = [symbol] if symbol else []
        sql = (
            "SELECT s.* FROM contrarian_signals s "
            "JOIN (SELECT symbol, MAX(ts_ms) AS mx FROM contrarian_signals"
            f"{sub_where} GROUP BY symbol) t "
            "ON s.symbol = t.symbol AND s.ts_ms = t.mx "
            "ORDER BY s.ts_ms DESC LIMIT ?"
        )
        try:
            with closing(self._connect()) as conn:
                conn.row_factory = sqlite3.Row
                rows = conn.execute(sql, [*params, limit]).fetchall()
                return [dict(r) for r in rows]
        except sqlite3.Error as exc:
            raise StorageError(f"failed to fetch latest per symbol: {exc}") from exc

    def overview_stats(
        self,
        *,
        start_ms: int | None = None,
        end_ms: int | None = None,
    ) -> dict[str, Any]:
        where, params = self._where(None, None, None, None, start_ms, end_ms)
        try:
            with closing(self._connect()) as conn:
                conn.row_factory = sqlite3.Row
                total = conn.execute(
                    f"SELECT COUNT(*) AS c FROM contrarian_signals{where}", params
                ).fetchone()["c"]
                pushed_clause = (" AND" if where else " WHERE") + " pushed = 1"
                skip_clause = (" AND" if where else " WHERE") + " pushed = 0"
                pushed = conn.execute(
                    f"SELECT COUNT(*) AS c FROM contrarian_signals{where}{pushed_clause}",
                    params,
                ).fetchone()["c"]
                by_direction = conn.execute(
                    f"SELECT direction, COUNT(*) AS c FROM contrarian_signals{where} "
                    "GROUP BY direction",
                    params,
                ).fetchall()
                by_skip = conn.execute(
                    f"SELECT COALESCE(skip_reason,'') AS skip_reason, COUNT(*) AS c "
                    f"FROM contrarian_signals{where}{skip_clause} GROUP BY skip_reason",
                    params,
                ).fetchall()
                return {
                    "total": int(total),
                    "pushed": int(pushed),
                    "skipped": int(total) - int(pushed),
                    "by_direction": {r["direction"]: int(r["c"]) for r in by_direction},
                    "by_skip_reason": {r["skip_reason"]: int(r["c"]) for r in by_skip},
                }
        except sqlite3.Error as exc:
            raise StorageError(f"failed to compute overview: {exc}") from exc

    def bucketed_counts(
        self,
        *,
        bucket: str = "hour",
        start_ms: int | None = None,
        end_ms: int | None = None,
    ) -> list[dict[str, Any]]:
        if bucket not in ("hour", "day"):
            raise ValueError("bucket must be 'hour' or 'day'")
        fmt = "%Y-%m-%d %H:00" if bucket == "hour" else "%Y-%m-%d"
        where, params = self._where(None, None, None, None, start_ms, end_ms)
        sql = (
            "SELECT strftime(?, ts_ms / 1000, 'unixepoch') AS bucket, "
            "SUM(pushed) AS pushed, COUNT(*) AS total "
            f"FROM contrarian_signals{where} GROUP BY bucket ORDER BY bucket"
        )
        try:
            with closing(self._connect()) as conn:
                conn.row_factory = sqlite3.Row
                rows = conn.execute(sql, [fmt, *params]).fetchall()
                return [
                    {
                        "bucket": r["bucket"],
                        "pushed": int(r["pushed"] or 0),
                        "skipped": int(r["total"]) - int(r["pushed"] or 0),
                        "total": int(r["total"]),
                    }
                    for r in rows
                ]
        except sqlite3.Error as exc:
            raise StorageError(f"failed to compute buckets: {exc}") from exc

    def by_symbol_stats(
        self,
        *,
        start_ms: int | None = None,
        end_ms: int | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        where, params = self._where(None, None, None, None, start_ms, end_ms)
        sql = (
            "SELECT symbol, "
            "COUNT(*) AS total, "
            "SUM(pushed) AS pushed, "
            "AVG(obi_5) AS avg_obi_5, "
            "AVG(long_short_ratio) AS avg_long_short, "
            "AVG(large_buys_usdt) AS avg_large_buys_usdt, "
            "MAX(ts_ms) AS last_ts_ms "
            f"FROM contrarian_signals{where} "
            "GROUP BY symbol ORDER BY pushed DESC, total DESC LIMIT ?"
        )
        try:
            with closing(self._connect()) as conn:
                conn.row_factory = sqlite3.Row
                rows = conn.execute(sql, [*params, limit]).fetchall()
                return [
                    {
                        "symbol": r["symbol"],
                        "total": int(r["total"]),
                        "pushed": int(r["pushed"] or 0),
                        "skipped": int(r["total"]) - int(r["pushed"] or 0),
                        "avg_obi_5": r["avg_obi_5"],
                        "avg_long_short": r["avg_long_short"],
                        "avg_large_buys_usdt": r["avg_large_buys_usdt"],
                        "last_ts_ms": int(r["last_ts_ms"]),
                    }
                    for r in rows
                ]
        except sqlite3.Error as exc:
            raise StorageError(f"failed to compute by-symbol stats: {exc}") from exc
