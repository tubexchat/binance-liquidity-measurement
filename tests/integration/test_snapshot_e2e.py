"""End-to-end test for `bliq snapshot` without hitting the network.

All httpx traffic is intercepted by pytest-httpx. The real SQLite store is
used on a tmp_path.
"""

import json
import sqlite3
from pathlib import Path

from pytest_httpx import HTTPXMock

from bliq.infra.config import load_config
from bliq.modes.snapshot import run_snapshot_once


async def test_snapshot_persists_full_row(
    tmp_path: Path, fixtures_dir: Path, httpx_mock: HTTPXMock
):
    repo_root = Path(__file__).parents[2]
    cfg = load_config(repo_root / "config" / "default.yaml")

    ob_payload = json.loads((fixtures_dir / "orderbook_btcusdt.json").read_text())
    httpx_mock.add_response(
        url="https://fapi.binance.com/fapi/v1/depth?symbol=BTCUSDT&limit=20",
        json=ob_payload,
        headers={"X-MBX-USED-WEIGHT-1M": "2"},
    )

    db_path = tmp_path / "e2e.db"
    reports = await run_snapshot_once(["BTCUSDT"], cfg, db_path=db_path)
    assert len(reports) == 1
    r = reports[0]
    assert r.symbol == "BTCUSDT"
    assert r.spread.spread_bps > 0

    # Database should contain one snapshot with slippage children.
    with sqlite3.connect(db_path) as conn:
        n_snap = conn.execute("SELECT COUNT(*) FROM snapshots").fetchone()[0]
        n_pts = conn.execute("SELECT COUNT(*) FROM slippage_points").fetchone()[0]
    assert n_snap == 1
    # 7 notional levels * 2 sides = 14 slippage rows.
    assert n_pts == 14


async def test_snapshot_skips_failed_symbol(
    tmp_path: Path, fixtures_dir: Path, httpx_mock: HTTPXMock
):
    repo_root = Path(__file__).parents[2]
    cfg = load_config(repo_root / "config" / "default.yaml")

    ok_payload = json.loads((fixtures_dir / "orderbook_btcusdt.json").read_text())
    httpx_mock.add_response(
        url="https://fapi.binance.com/fapi/v1/depth?symbol=BTCUSDT&limit=20",
        json=ok_payload,
    )
    httpx_mock.add_response(
        url="https://fapi.binance.com/fapi/v1/depth?symbol=FOOUSDT&limit=20",
        status_code=400,
        json={"code": -1121, "msg": "Invalid symbol."},
    )

    reports = await run_snapshot_once(
        ["BTCUSDT", "FOOUSDT"], cfg, db_path=tmp_path / "e2e2.db"
    )
    assert [r.symbol for r in reports] == ["BTCUSDT"]
