import sqlite3

from bliq.data.storage import SnapshotStore
from bliq.metrics.types import (
    DepthMetric,
    LiquidityReport,
    OBIMetric,
    SlippageMetric,
    SlippagePoint,
    SpreadMetric,
)


def _sample_report() -> LiquidityReport:
    spread = SpreadMetric(bid=100.0, ask=100.1, mid=100.05, spread_bps=9.995)
    depth = DepthMetric(by_pct={0.001: (10.0, 12.0), 0.005: (40.0, 50.0),
                                 0.01: (80.0, 90.0), 0.02: (100.0, 110.0)})
    obi = OBIMetric(by_levels={5: 0.1, 10: 0.05, 20: -0.02})
    slippage = SlippageMetric(
        points=(
            SlippagePoint("buy", 1000.0, 0.5, 100.1),
            SlippagePoint("sell", 1000.0, 0.4, 100.0),
        ),
        capacity_buy_usdt=250000.0,
        capacity_sell_usdt=240000.0,
        max_slippage_bps=20.0,
    )
    return LiquidityReport(
        symbol="BTCUSDT",
        ts_ms=1_700_000_000_000,
        mid_price=100.05,
        spread=spread,
        depth=depth,
        obi=obi,
        slippage=slippage,
    )


def test_schema_creation_is_idempotent(tmp_path):
    db = tmp_path / "a.db"
    SnapshotStore(db).init_schema()
    SnapshotStore(db).init_schema()  # second call must not raise
    with sqlite3.connect(db) as conn:
        tables = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )}
    assert {"snapshots", "slippage_points", "alerts", "schema_version"} <= tables


def test_insert_report_round_trip(tmp_path):
    store = SnapshotStore(tmp_path / "rt.db")
    store.init_schema()
    snap_id = store.insert_report(_sample_report())
    assert snap_id > 0

    with sqlite3.connect(store.path) as conn:
        rows = conn.execute(
            "SELECT symbol, mid_price, spread_bps, obi_5, "
            "depth_05pct_ask, capacity_20bps_buy "
            "FROM snapshots WHERE id=?",
            (snap_id,),
        ).fetchall()
    assert len(rows) == 1
    symbol, mid, spread_bps, obi_5, depth_05_ask, cap_buy = rows[0]
    assert symbol == "BTCUSDT"
    assert round(mid, 2) == 100.05
    assert round(spread_bps, 3) == 9.995
    assert round(obi_5, 2) == 0.10
    assert round(depth_05_ask, 1) == 50.0
    assert round(cap_buy, 0) == 250000.0

    with sqlite3.connect(store.path) as conn:
        pts = conn.execute(
            "SELECT side, notional_usdt, slippage_bps FROM slippage_points "
            "WHERE snapshot_id=? ORDER BY side",
            (snap_id,),
        ).fetchall()
    assert pts == [("buy", 1000.0, 0.5), ("sell", 1000.0, 0.4)]


def test_wal_mode_enabled(tmp_path):
    store = SnapshotStore(tmp_path / "wal.db")
    store.init_schema()
    with sqlite3.connect(store.path) as conn:
        mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
    assert mode.lower() == "wal"
