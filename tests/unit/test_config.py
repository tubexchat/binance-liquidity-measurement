from pathlib import Path

import pytest

from bliq.infra.config import Config, load_config
from bliq.infra.errors import ConfigError


def test_load_default_config_parses_cleanly():
    repo_root = Path(__file__).parents[2]
    cfg = load_config(repo_root / "config" / "default.yaml")
    assert isinstance(cfg, Config)
    assert cfg.metrics.orderbook_limit == 20
    assert cfg.metrics.depth_pcts == [0.001, 0.005, 0.01, 0.02]
    assert cfg.score_weights.spread == 0.25


def test_score_weights_must_sum_to_one(tmp_path: Path):
    bad = tmp_path / "bad.yaml"
    bad.write_text(
        """
symbols: {default_mode: top, default_top_n: 50}
metrics:
  depth_pcts: [0.01]
  obi_levels: [5]
  orderbook_limit: 20
  slippage_levels_usdt: [1000]
  max_slippage_bps: 20
  amihud: {interval: 5m, lookback_bars: 288}
  taker_ratio_window: 1000
score_weights: {spread: 0.5, capacity: 0.3, amihud: 0.3, obi_stability: 0.3}
data:
  rest_base: https://fapi.binance.com
  ws_base: wss://fstream.binance.com
  max_concurrent_requests: 20
  rate_limit_weight_per_min: 2400
  retry_attempts: 3
  retry_backoff_base: 1.0
storage: {db_path: liquidity.db, wal_mode: true}
logging: {level: INFO, file: logs/bliq.log, rotation: "10 MB"}
""".strip()
    )
    with pytest.raises(ConfigError, match=r"score_weights must sum to 1\.0"):
        load_config(bad)


def test_missing_file_raises_config_error(tmp_path: Path):
    with pytest.raises(ConfigError, match="not found"):
        load_config(tmp_path / "missing.yaml")
