# bliq M1 — Foundation & Snapshot Mode Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver M1 of the `bliq` Binance perpetual liquidity tool — project scaffold, infra, REST data layer, pure-function metrics engine (spread/depth/OBI/slippage), SQLite storage, and a minimal working `bliq snapshot` subcommand that fetches one sample and persists it.

**Architecture:** Python 3.11+ `src/bliq` package, typer CLI, strict layering (cli → modes → metrics+reporters → data → infra). `metrics/` is pure functions with no IO; `data/` owns all network and disk. Async REST client with token-bucket rate limiter. SQLite with WAL mode. TDD throughout: write failing test, verify, implement, verify pass, commit.

**Tech Stack:** Python 3.11+, uv, typer, pydantic, aiohttp, PyYAML, loguru, rich, pytest, pytest-asyncio, pytest-httpx, ruff.

**Spec reference:** `docs/superpowers/specs/2026-04-11-binance-liquidity-measurement-design.md` (milestone M1).

---

## File Structure Created by This Plan

```
binance-liquidity-measurement/
├── .gitignore
├── .python-version
├── pyproject.toml
├── config/
│   └── default.yaml
├── src/bliq/
│   ├── __init__.py
│   ├── __main__.py
│   ├── cli/
│   │   ├── __init__.py
│   │   └── main.py
│   ├── infra/
│   │   ├── __init__.py
│   │   ├── errors.py
│   │   ├── config.py
│   │   └── logging.py
│   ├── metrics/
│   │   ├── __init__.py
│   │   ├── types.py
│   │   ├── spread.py
│   │   ├── depth.py
│   │   ├── obi.py
│   │   └── slippage.py
│   ├── data/
│   │   ├── __init__.py
│   │   ├── rate_limiter.py
│   │   ├── binance_rest.py
│   │   ├── symbols.py
│   │   └── storage.py
│   └── modes/
│       ├── __init__.py
│       └── snapshot.py
└── tests/
    ├── __init__.py
    ├── conftest.py
    ├── fixtures/
    │   └── orderbook_btcusdt.json
    ├── unit/
    │   ├── test_config.py
    │   ├── test_rate_limiter.py
    │   ├── test_binance_rest.py
    │   ├── test_symbols.py
    │   ├── test_storage.py
    │   ├── test_spread.py
    │   ├── test_depth.py
    │   ├── test_obi.py
    │   └── test_slippage.py
    └── integration/
        └── test_snapshot_e2e.py
```

**Module responsibilities:**
- `infra/errors.py` — exception hierarchy rooted at `BliqError`.
- `infra/config.py` — pydantic-validated config loaded from `config/default.yaml`, overridable by `--config`.
- `infra/logging.py` — loguru setup (console + rotating file).
- `metrics/types.py` — `OrderBook`, `OrderBookLevel`, `Kline`, `AggTrade`, `LiquidityReport`, `SlippagePoint` dataclasses.
- `metrics/*.py` — pure functions, no IO.
- `data/rate_limiter.py` — async token bucket keyed on weight.
- `data/binance_rest.py` — `BinanceRestClient` (async) with retry + rate limiter integration.
- `data/symbols.py` — resolver for `--symbols`/`--top`/`--all`/`--from-file`.
- `data/storage.py` — SQLite DDL, migrations, insertion API.
- `modes/snapshot.py` — orchestrates one sampling tick (M1 only implements one-shot; scheduler loop comes in M4).
- `cli/main.py` — typer app with `snapshot` subcommand.

---

## Task 1: Project Scaffold

**Files:**
- Create: `.gitignore`
- Create: `.python-version`
- Create: `pyproject.toml`
- Create: `src/bliq/__init__.py`
- Create: `src/bliq/__main__.py`
- Create: `tests/__init__.py`
- Create: `tests/conftest.py`

- [ ] **Step 1: Create `.gitignore`**

Write to `.gitignore`:

```
__pycache__/
*.py[cod]
*.egg-info/
.venv/
.pytest_cache/
.ruff_cache/
dist/
build/
*.db
*.db-journal
*.db-wal
*.db-shm
logs/
reports/
.coverage
htmlcov/
```

- [ ] **Step 2: Create `.python-version`**

Write to `.python-version`:

```
3.11
```

- [ ] **Step 3: Create `pyproject.toml`**

Write to `pyproject.toml`:

```toml
[project]
name = "bliq"
version = "0.1.0"
description = "Binance USDT-M perpetual futures liquidity measurement CLI"
requires-python = ">=3.11"
readme = "README.md"
license = { file = "LICENSE" }
dependencies = [
    "typer>=0.12",
    "pydantic>=2.6",
    "pyyaml>=6.0",
    "aiohttp>=3.9",
    "loguru>=0.7",
    "rich>=13.7",
]

[project.scripts]
bliq = "bliq.cli.main:app"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/bliq"]

[dependency-groups]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.23",
    "pytest-httpx>=0.30",
    "ruff>=0.4",
]

[tool.pytest.ini_options]
testpaths = ["tests"]
asyncio_mode = "auto"
markers = [
    "integration: tests that hit real Binance endpoints (opt-in)",
]
addopts = "-ra --strict-markers"

[tool.ruff]
line-length = 100
target-version = "py311"
src = ["src"]

[tool.ruff.lint]
select = ["E", "F", "W", "I", "N", "UP", "B", "SIM", "RUF"]
ignore = ["E501"]

[tool.ruff.lint.per-file-ignores]
"tests/**" = ["N802", "N803"]
```

- [ ] **Step 4: Create empty package files**

Write to `src/bliq/__init__.py`:

```python
"""bliq — Binance USDT-M perpetual futures liquidity measurement."""

__version__ = "0.1.0"
```

Write to `src/bliq/__main__.py`:

```python
from bliq.cli.main import app

if __name__ == "__main__":
    app()
```

Write to `tests/__init__.py`:

```python
```

Write to `tests/conftest.py`:

```python
from pathlib import Path

import pytest


@pytest.fixture
def fixtures_dir() -> Path:
    return Path(__file__).parent / "fixtures"
```

- [ ] **Step 5: Install with uv and verify**

Run: `uv sync`
Expected: dependency resolution succeeds; a `.venv/` directory is created.

Run: `uv run pytest --collect-only`
Expected: `collected 0 items` (no tests yet, no errors).

Run: `uv run ruff check src tests`
Expected: `All checks passed!`

- [ ] **Step 6: Commit**

```bash
git add .gitignore .python-version pyproject.toml src tests
git commit -m "chore: project scaffold with uv, typer, pytest, ruff"
```

---

## Task 2: Error Hierarchy

**Files:**
- Create: `src/bliq/infra/__init__.py`
- Create: `src/bliq/infra/errors.py`

- [ ] **Step 1: Create `src/bliq/infra/__init__.py`**

Write:

```python
```

- [ ] **Step 2: Write `src/bliq/infra/errors.py`**

Write:

```python
"""Exception hierarchy for bliq."""


class BliqError(Exception):
    """Base for all bliq-specific errors."""


class ConfigError(BliqError):
    """Raised when configuration parsing or validation fails."""


class BinanceAPIError(BliqError):
    """Raised when a Binance REST/WS call returns an unexpected error."""


class RateLimitError(BinanceAPIError):
    """Raised on HTTP 429 or 418 from Binance."""


class SymbolNotFoundError(BinanceAPIError):
    """Raised when a requested symbol is not tradable on the target market."""


class DataIntegrityError(BliqError):
    """Raised when local state cannot be reconciled with upstream data."""


class StorageError(BliqError):
    """Raised when SQLite reads/writes fail."""
```

- [ ] **Step 3: Verify import works**

Run: `uv run python -c "from bliq.infra.errors import BliqError, RateLimitError; print('ok')"`
Expected output: `ok`

- [ ] **Step 4: Commit**

```bash
git add src/bliq/infra
git commit -m "feat(infra): add error hierarchy rooted at BliqError"
```

---

## Task 3: Config Model and YAML Loader

**Files:**
- Create: `config/default.yaml`
- Create: `src/bliq/infra/config.py`
- Test: `tests/unit/test_config.py`

- [ ] **Step 1: Write `config/default.yaml`**

Write:

```yaml
symbols:
  default_mode: top
  default_top_n: 50

metrics:
  depth_pcts: [0.001, 0.005, 0.01, 0.02]
  obi_levels: [5, 10, 20]
  orderbook_limit: 20
  slippage_levels_usdt: [1000, 5000, 10000, 50000, 100000, 500000, 1000000]
  max_slippage_bps: 20
  amihud:
    interval: 5m
    lookback_bars: 288
  taker_ratio_window: 1000

score_weights:
  spread: 0.25
  capacity: 0.35
  amihud: 0.25
  obi_stability: 0.15

data:
  rest_base: https://fapi.binance.com
  ws_base: wss://fstream.binance.com
  max_concurrent_requests: 20
  rate_limit_weight_per_min: 2400
  retry_attempts: 3
  retry_backoff_base: 1.0

storage:
  db_path: liquidity.db
  wal_mode: true

logging:
  level: INFO
  file: logs/bliq.log
  rotation: "10 MB"
```

- [ ] **Step 2: Create `tests/unit/__init__.py` and write the failing test**

Write `tests/unit/__init__.py`:

```python
```

Write `tests/unit/test_config.py`:

```python
import math
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
    with pytest.raises(ConfigError, match="score_weights must sum to 1.0"):
        load_config(bad)


def test_missing_file_raises_config_error(tmp_path: Path):
    with pytest.raises(ConfigError, match="not found"):
        load_config(tmp_path / "missing.yaml")
```

- [ ] **Step 3: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_config.py -v`
Expected: ImportError / collection error — `bliq.infra.config` does not exist yet.

- [ ] **Step 4: Implement `src/bliq/infra/config.py`**

Write:

```python
"""Configuration model and YAML loader."""

from __future__ import annotations

import math
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field, ValidationError, model_validator

from bliq.infra.errors import ConfigError


class SymbolsConfig(BaseModel):
    default_mode: Literal["top", "all", "file"] = "top"
    default_top_n: int = Field(50, gt=0)


class AmihudConfig(BaseModel):
    interval: str = "5m"
    lookback_bars: int = Field(288, gt=0)


class MetricsConfig(BaseModel):
    depth_pcts: list[float]
    obi_levels: list[int]
    orderbook_limit: int = Field(gt=0)
    slippage_levels_usdt: list[float]
    max_slippage_bps: float = Field(gt=0)
    amihud: AmihudConfig
    taker_ratio_window: int = Field(gt=0)


class ScoreWeights(BaseModel):
    spread: float
    capacity: float
    amihud: float
    obi_stability: float

    @model_validator(mode="after")
    def _sum_to_one(self) -> "ScoreWeights":
        total = self.spread + self.capacity + self.amihud + self.obi_stability
        if not math.isclose(total, 1.0, abs_tol=1e-6):
            raise ValueError(f"score_weights must sum to 1.0, got {total}")
        return self


class DataConfig(BaseModel):
    rest_base: str
    ws_base: str
    max_concurrent_requests: int = Field(gt=0)
    rate_limit_weight_per_min: int = Field(gt=0)
    retry_attempts: int = Field(ge=0)
    retry_backoff_base: float = Field(gt=0)


class StorageConfig(BaseModel):
    db_path: str
    wal_mode: bool = True


class LoggingConfig(BaseModel):
    level: str = "INFO"
    file: str = "logs/bliq.log"
    rotation: str = "10 MB"


class Config(BaseModel):
    symbols: SymbolsConfig
    metrics: MetricsConfig
    score_weights: ScoreWeights
    data: DataConfig
    storage: StorageConfig
    logging: LoggingConfig


def load_config(path: Path) -> Config:
    path = Path(path)
    if not path.exists():
        raise ConfigError(f"config file not found: {path}")
    try:
        raw = yaml.safe_load(path.read_text())
    except yaml.YAMLError as exc:
        raise ConfigError(f"invalid YAML in {path}: {exc}") from exc
    try:
        return Config.model_validate(raw)
    except ValidationError as exc:
        # Unwrap pydantic errors so ConfigError messages are readable.
        msgs = "; ".join(e["msg"] for e in exc.errors())
        raise ConfigError(f"config validation failed: {msgs}") from exc
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_config.py -v`
Expected: 3 passed.

- [ ] **Step 6: Commit**

```bash
git add config src/bliq/infra/config.py tests/unit/__init__.py tests/unit/test_config.py
git commit -m "feat(infra): pydantic config model + yaml loader with validation"
```

---

## Task 4: Logging Setup

**Files:**
- Create: `src/bliq/infra/logging.py`

- [ ] **Step 1: Write `src/bliq/infra/logging.py`**

Write:

```python
"""loguru setup — called once at CLI startup."""

from __future__ import annotations

import sys
from pathlib import Path

from loguru import logger

from bliq.infra.config import LoggingConfig


def setup_logging(cfg: LoggingConfig) -> None:
    logger.remove()
    logger.add(
        sys.stderr,
        level=cfg.level,
        format="<green>{time:HH:mm:ss}</green> | <level>{level:<7}</level> | "
        "<cyan>{name}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
    )
    log_path = Path(cfg.file)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    logger.add(
        log_path,
        level=cfg.level,
        rotation=cfg.rotation,
        enqueue=True,
        backtrace=False,
        diagnose=False,
    )
```

- [ ] **Step 2: Smoke-check it imports**

Run: `uv run python -c "from bliq.infra.logging import setup_logging; print('ok')"`
Expected: `ok`

- [ ] **Step 3: Commit**

```bash
git add src/bliq/infra/logging.py
git commit -m "feat(infra): loguru setup with console and rotating file sinks"
```

---

## Task 5: Metric Types (Shared Dataclasses)

**Files:**
- Create: `src/bliq/metrics/__init__.py`
- Create: `src/bliq/metrics/types.py`

- [ ] **Step 1: Write `src/bliq/metrics/__init__.py`**

Write:

```python
```

- [ ] **Step 2: Write `src/bliq/metrics/types.py`**

Write:

```python
"""Shared dataclasses used by metric functions and the data layer."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class OrderBookLevel:
    price: float
    qty: float


@dataclass(frozen=True, slots=True)
class OrderBook:
    symbol: str
    ts_ms: int
    bids: tuple[OrderBookLevel, ...]  # sorted descending by price
    asks: tuple[OrderBookLevel, ...]  # sorted ascending by price

    @property
    def best_bid(self) -> float:
        return self.bids[0].price

    @property
    def best_ask(self) -> float:
        return self.asks[0].price

    @property
    def mid(self) -> float:
        return (self.best_bid + self.best_ask) / 2.0


@dataclass(frozen=True, slots=True)
class SpreadMetric:
    bid: float
    ask: float
    mid: float
    spread_bps: float


@dataclass(frozen=True, slots=True)
class DepthMetric:
    by_pct: dict[float, tuple[float, float]] = field(default_factory=dict)
    # key = pct (e.g. 0.005); value = (bid_usdt, ask_usdt)


@dataclass(frozen=True, slots=True)
class OBIMetric:
    by_levels: dict[int, float] = field(default_factory=dict)
    # key = N top levels; value = OBI in [-1, 1]


@dataclass(frozen=True, slots=True)
class SlippagePoint:
    side: str  # "buy" | "sell"
    notional_usdt: float
    slippage_bps: float
    avg_fill_px: float


@dataclass(frozen=True, slots=True)
class SlippageMetric:
    points: tuple[SlippagePoint, ...]
    capacity_buy_usdt: float
    capacity_sell_usdt: float
    max_slippage_bps: float


@dataclass(frozen=True, slots=True)
class LiquidityReport:
    symbol: str
    ts_ms: int
    mid_price: float
    spread: SpreadMetric
    depth: DepthMetric
    obi: OBIMetric
    slippage: SlippageMetric
```

- [ ] **Step 3: Import smoke test**

Run: `uv run python -c "from bliq.metrics.types import OrderBook, OrderBookLevel; ob = OrderBook('X', 0, (OrderBookLevel(1,1),), (OrderBookLevel(2,1),)); print(ob.mid)"`
Expected output: `1.5`

- [ ] **Step 4: Commit**

```bash
git add src/bliq/metrics/__init__.py src/bliq/metrics/types.py
git commit -m "feat(metrics): shared dataclasses for order book and metric results"
```

---

## Task 6: Spread Metric

**Files:**
- Create: `src/bliq/metrics/spread.py`
- Test: `tests/unit/test_spread.py`

- [ ] **Step 1: Write the failing test**

Write `tests/unit/test_spread.py`:

```python
import math

from bliq.metrics.spread import compute_spread
from bliq.metrics.types import OrderBook, OrderBookLevel


def _book(bid: float, ask: float) -> OrderBook:
    return OrderBook(
        symbol="BTCUSDT",
        ts_ms=0,
        bids=(OrderBookLevel(bid, 1.0),),
        asks=(OrderBookLevel(ask, 1.0),),
    )


def test_spread_basic():
    r = compute_spread(_book(100.0, 100.1))
    assert r.bid == 100.0
    assert r.ask == 100.1
    assert r.mid == 100.05
    # (100.1 - 100.0) / 100.05 * 10000 ≈ 9.995 bps
    assert math.isclose(r.spread_bps, 9.9950024987, rel_tol=1e-6)


def test_spread_zero_when_crossed_or_equal():
    r = compute_spread(_book(100.0, 100.0))
    assert r.spread_bps == 0.0


def test_spread_altcoin_wide():
    r = compute_spread(_book(0.0001, 0.00012))
    # spread 0.00002 / mid 0.00011 * 10000 ≈ 1818 bps
    assert math.isclose(r.spread_bps, 1818.1818182, rel_tol=1e-6)
```

- [ ] **Step 2: Run the failing test**

Run: `uv run pytest tests/unit/test_spread.py -v`
Expected: ImportError — `bliq.metrics.spread` does not exist.

- [ ] **Step 3: Implement `src/bliq/metrics/spread.py`**

Write:

```python
"""Bid-ask spread metric (relative, in basis points)."""

from __future__ import annotations

from bliq.metrics.types import OrderBook, SpreadMetric


def compute_spread(ob: OrderBook) -> SpreadMetric:
    bid = ob.best_bid
    ask = ob.best_ask
    mid = (bid + ask) / 2.0
    if mid <= 0 or ask <= bid:
        spread_bps = 0.0
    else:
        spread_bps = (ask - bid) / mid * 10_000.0
    return SpreadMetric(bid=bid, ask=ask, mid=mid, spread_bps=spread_bps)
```

- [ ] **Step 4: Run the test to verify pass**

Run: `uv run pytest tests/unit/test_spread.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add src/bliq/metrics/spread.py tests/unit/test_spread.py
git commit -m "feat(metrics): relative bid-ask spread in basis points"
```

---

## Task 7: Depth Metric

**Files:**
- Create: `src/bliq/metrics/depth.py`
- Test: `tests/unit/test_depth.py`

- [ ] **Step 1: Write the failing test**

Write `tests/unit/test_depth.py`:

```python
from bliq.metrics.depth import compute_depth
from bliq.metrics.types import OrderBook, OrderBookLevel


def _book() -> OrderBook:
    # mid = 100
    bids = tuple(
        OrderBookLevel(price, 1.0)  # 1 unit at each level
        for price in [99.9, 99.5, 99.0, 98.0, 95.0]
    )
    asks = tuple(
        OrderBookLevel(price, 1.0)
        for price in [100.1, 100.5, 101.0, 102.0, 105.0]
    )
    return OrderBook("X", 0, bids, asks)


def test_depth_within_05pct():
    r = compute_depth(_book(), pcts=[0.005])
    bid_usdt, ask_usdt = r.by_pct[0.005]
    # 0.5% of mid 100 => [99.5, 100.5].
    # Bids eligible: 99.9 (99.9 * 1), 99.5 (99.5 * 1) -> 199.4
    # Asks eligible: 100.1 (100.1 * 1), 100.5 (100.5 * 1) -> 200.6
    assert round(bid_usdt, 4) == 199.4
    assert round(ask_usdt, 4) == 200.6


def test_depth_within_2pct_accumulates_more():
    r = compute_depth(_book(), pcts=[0.02])
    bid_usdt, ask_usdt = r.by_pct[0.02]
    # 2% band: [98, 102]. Bid levels: 99.9, 99.5, 99.0, 98.0 -> 396.4
    # Ask levels: 100.1, 100.5, 101.0, 102.0 -> 403.6
    assert round(bid_usdt, 4) == 396.4
    assert round(ask_usdt, 4) == 403.6


def test_depth_empty_book_returns_zeros():
    ob = OrderBook(
        "X",
        0,
        (OrderBookLevel(100.0, 0.0),),
        (OrderBookLevel(100.0, 0.0),),
    )
    r = compute_depth(ob, pcts=[0.01])
    assert r.by_pct[0.01] == (0.0, 0.0)


def test_depth_multiple_pcts():
    r = compute_depth(_book(), pcts=[0.005, 0.01, 0.02])
    assert set(r.by_pct.keys()) == {0.005, 0.01, 0.02}
    # Wider bands should be monotonically >= narrower.
    assert r.by_pct[0.01][0] >= r.by_pct[0.005][0]
    assert r.by_pct[0.02][0] >= r.by_pct[0.01][0]
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/unit/test_depth.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement `src/bliq/metrics/depth.py`**

Write:

```python
"""Cumulative order book depth within percentage bands."""

from __future__ import annotations

from collections.abc import Iterable

from bliq.metrics.types import DepthMetric, OrderBook, OrderBookLevel


def _notional_within(
    levels: Iterable[OrderBookLevel], lower: float, upper: float
) -> float:
    total = 0.0
    for lvl in levels:
        if lower <= lvl.price <= upper:
            total += lvl.price * lvl.qty
    return total


def compute_depth(ob: OrderBook, pcts: list[float]) -> DepthMetric:
    mid = ob.mid
    result: dict[float, tuple[float, float]] = {}
    for pct in pcts:
        lower = mid * (1 - pct)
        upper = mid * (1 + pct)
        bid_usdt = _notional_within(ob.bids, lower, mid)
        ask_usdt = _notional_within(ob.asks, mid, upper)
        result[pct] = (bid_usdt, ask_usdt)
    return DepthMetric(by_pct=result)
```

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest tests/unit/test_depth.py -v`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add src/bliq/metrics/depth.py tests/unit/test_depth.py
git commit -m "feat(metrics): cumulative depth within percentage bands"
```

---

## Task 8: OBI Metric

**Files:**
- Create: `src/bliq/metrics/obi.py`
- Test: `tests/unit/test_obi.py`

- [ ] **Step 1: Write the failing test**

Write `tests/unit/test_obi.py`:

```python
import math

from bliq.metrics.obi import compute_obi
from bliq.metrics.types import OrderBook, OrderBookLevel


def _book(bid_qtys: list[float], ask_qtys: list[float]) -> OrderBook:
    bids = tuple(OrderBookLevel(100.0 - i * 0.1, q) for i, q in enumerate(bid_qtys))
    asks = tuple(OrderBookLevel(100.1 + i * 0.1, q) for i, q in enumerate(ask_qtys))
    return OrderBook("X", 0, bids, asks)


def test_obi_balanced_is_zero():
    r = compute_obi(_book([1, 1, 1, 1, 1], [1, 1, 1, 1, 1]), levels=[5])
    assert math.isclose(r.by_levels[5], 0.0, abs_tol=1e-9)


def test_obi_all_bid_is_one():
    r = compute_obi(_book([1, 1, 1, 1, 1], [0, 0, 0, 0, 0]), levels=[5])
    assert r.by_levels[5] == 1.0


def test_obi_all_ask_is_minus_one():
    r = compute_obi(_book([0, 0, 0, 0, 0], [1, 1, 1, 1, 1]), levels=[5])
    assert r.by_levels[5] == -1.0


def test_obi_multi_levels_independent():
    # top-5 balanced, top-10 tilted: simulate by stacking extra bids past 5
    bids = [1] * 5 + [10] * 5
    asks = [1] * 10
    r = compute_obi(_book(bids, asks), levels=[5, 10])
    assert math.isclose(r.by_levels[5], 0.0, abs_tol=1e-9)
    # 55 bid vs 10 ask over top 10 -> (55-10)/65
    assert math.isclose(r.by_levels[10], 45.0 / 65.0, rel_tol=1e-9)


def test_obi_empty_sides_returns_zero():
    r = compute_obi(_book([0, 0, 0, 0, 0], [0, 0, 0, 0, 0]), levels=[5])
    assert r.by_levels[5] == 0.0
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/unit/test_obi.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement `src/bliq/metrics/obi.py`**

Write:

```python
"""Order Book Imbalance (top-N level volume imbalance)."""

from __future__ import annotations

from bliq.metrics.types import OBIMetric, OrderBook


def compute_obi(ob: OrderBook, levels: list[int]) -> OBIMetric:
    result: dict[int, float] = {}
    for n in levels:
        top_bids = ob.bids[:n]
        top_asks = ob.asks[:n]
        bid_vol = sum(lvl.qty for lvl in top_bids)
        ask_vol = sum(lvl.qty for lvl in top_asks)
        total = bid_vol + ask_vol
        if total == 0:
            result[n] = 0.0
        else:
            result[n] = (bid_vol - ask_vol) / total
    return OBIMetric(by_levels=result)
```

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest tests/unit/test_obi.py -v`
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add src/bliq/metrics/obi.py tests/unit/test_obi.py
git commit -m "feat(metrics): order book imbalance across top-N levels"
```

---

## Task 9: Slippage Metric (Ladder + Capacity)

**Files:**
- Create: `src/bliq/metrics/slippage.py`
- Test: `tests/unit/test_slippage.py`

- [ ] **Step 1: Write the failing test**

Write `tests/unit/test_slippage.py`:

```python
import math

import pytest

from bliq.metrics.slippage import compute_slippage, simulate_market_order
from bliq.metrics.types import OrderBook, OrderBookLevel


def _deep_book() -> OrderBook:
    # Mid ≈ 100. Each ask level has 10 units = 1000 USDT notional.
    asks = tuple(
        OrderBookLevel(100.0 + i * 0.1, 10.0) for i in range(1, 11)
    )
    bids = tuple(
        OrderBookLevel(100.0 - i * 0.1, 10.0) for i in range(1, 11)
    )
    return OrderBook("X", 0, bids, asks)


def test_simulate_buy_consumes_levels_in_order():
    ob = _deep_book()
    avg, filled = simulate_market_order(ob, side="buy", notional_usdt=1500.0)
    # Level 1: 100.1 * 10 = 1001 USDT -> fully consumed (1001)
    # Remaining: 499 USDT at 100.2 -> qty ~4.9800
    # avg = (1001 + 499) / (10 + 499/100.2)
    assert math.isclose(filled, 1500.0, rel_tol=1e-9)
    assert 100.1 < avg < 100.2


def test_simulate_buy_runs_out_of_book():
    ob = _deep_book()
    total_notional = sum(a.price * a.qty for a in ob.asks)
    avg, filled = simulate_market_order(ob, side="buy", notional_usdt=total_notional * 2)
    assert math.isclose(filled, total_notional, rel_tol=1e-9)


def test_slippage_ladder_populates_both_sides():
    ob = _deep_book()
    r = compute_slippage(ob, levels_usdt=[500, 2000], max_slippage_bps=20.0)
    sides = {(p.side, p.notional_usdt) for p in r.points}
    assert ("buy", 500.0) in sides
    assert ("sell", 500.0) in sides
    assert ("buy", 2000.0) in sides
    assert ("sell", 2000.0) in sides
    # Larger notional => larger or equal slippage.
    buy_points = sorted(
        [p for p in r.points if p.side == "buy"], key=lambda p: p.notional_usdt
    )
    assert buy_points[0].slippage_bps <= buy_points[1].slippage_bps


def test_capacity_finds_boundary():
    ob = _deep_book()
    r = compute_slippage(ob, levels_usdt=[500], max_slippage_bps=10.0)
    # Capacity > 0 and < total book notional on each side.
    assert r.capacity_buy_usdt > 0
    assert r.capacity_sell_usdt > 0
    total_ask = sum(a.price * a.qty for a in ob.asks)
    assert r.capacity_buy_usdt < total_ask


def test_slippage_zero_notional_is_zero():
    ob = _deep_book()
    r = compute_slippage(ob, levels_usdt=[0], max_slippage_bps=20.0)
    for p in r.points:
        assert p.slippage_bps == 0.0
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/unit/test_slippage.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement `src/bliq/metrics/slippage.py`**

Write:

```python
"""Market-order slippage simulation and capacity estimation."""

from __future__ import annotations

from bliq.metrics.types import OrderBook, SlippageMetric, SlippagePoint


def simulate_market_order(
    ob: OrderBook, *, side: str, notional_usdt: float
) -> tuple[float, float]:
    """Walk the book on the given side until `notional_usdt` is filled.

    Returns ``(avg_fill_price, filled_notional)``. If the book is exhausted
    before the requested notional is met, ``filled_notional`` is the actual
    amount consumed.
    """
    if notional_usdt <= 0:
        mid = ob.mid
        return mid, 0.0

    levels = ob.asks if side == "buy" else ob.bids
    remaining = notional_usdt
    filled_notional = 0.0
    filled_qty = 0.0
    for lvl in levels:
        if remaining <= 0 or lvl.qty <= 0:
            continue
        level_notional = lvl.price * lvl.qty
        if level_notional >= remaining:
            qty_taken = remaining / lvl.price
            filled_notional += remaining
            filled_qty += qty_taken
            remaining = 0
            break
        filled_notional += level_notional
        filled_qty += lvl.qty
        remaining -= level_notional

    if filled_qty == 0:
        return ob.mid, 0.0
    return filled_notional / filled_qty, filled_notional


def _slippage_bps(avg_px: float, mid: float, side: str) -> float:
    if mid <= 0 or avg_px <= 0:
        return 0.0
    if side == "buy":
        return (avg_px - mid) / mid * 10_000.0
    return (mid - avg_px) / mid * 10_000.0


def _capacity_at(ob: OrderBook, *, side: str, max_bps: float) -> float:
    """Largest notional that keeps slippage <= max_bps.

    Implementation: walk the book level by level, accumulating notional. After
    each level, compute the slippage at the cumulative fill. Stop at the first
    level where slippage exceeds the cap and interpolate the exact boundary
    within that level.
    """
    mid = ob.mid
    if mid <= 0:
        return 0.0
    levels = ob.asks if side == "buy" else ob.bids

    cum_notional = 0.0
    cum_qty = 0.0
    for lvl in levels:
        if lvl.qty <= 0:
            continue
        level_notional = lvl.price * lvl.qty
        new_notional = cum_notional + level_notional
        new_qty = cum_qty + lvl.qty
        new_avg = new_notional / new_qty
        new_bps = _slippage_bps(new_avg, mid, side)
        if new_bps <= max_bps:
            cum_notional = new_notional
            cum_qty = new_qty
            continue
        # Binary search within this level for the max qty that keeps slippage <= cap.
        lo, hi = 0.0, lvl.qty
        for _ in range(40):
            m = (lo + hi) / 2.0
            trial_notional = cum_notional + lvl.price * m
            trial_qty = cum_qty + m
            if trial_qty == 0:
                lo = m
                continue
            trial_avg = trial_notional / trial_qty
            trial_bps = _slippage_bps(trial_avg, mid, side)
            if trial_bps <= max_bps:
                lo = m
            else:
                hi = m
        cum_notional += lvl.price * lo
        cum_qty += lo
        break
    return cum_notional


def compute_slippage(
    ob: OrderBook, *, levels_usdt: list[float], max_slippage_bps: float
) -> SlippageMetric:
    mid = ob.mid
    points: list[SlippagePoint] = []
    for notional in levels_usdt:
        for side in ("buy", "sell"):
            avg, _filled = simulate_market_order(ob, side=side, notional_usdt=notional)
            bps = _slippage_bps(avg, mid, side) if notional > 0 else 0.0
            points.append(
                SlippagePoint(
                    side=side,
                    notional_usdt=float(notional),
                    slippage_bps=bps,
                    avg_fill_px=avg,
                )
            )
    cap_buy = _capacity_at(ob, side="buy", max_bps=max_slippage_bps)
    cap_sell = _capacity_at(ob, side="sell", max_bps=max_slippage_bps)
    return SlippageMetric(
        points=tuple(points),
        capacity_buy_usdt=cap_buy,
        capacity_sell_usdt=cap_sell,
        max_slippage_bps=max_slippage_bps,
    )
```

- [ ] **Step 4: Run the tests to verify pass**

Run: `uv run pytest tests/unit/test_slippage.py -v`
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add src/bliq/metrics/slippage.py tests/unit/test_slippage.py
git commit -m "feat(metrics): slippage ladder and capacity estimation"
```

---

## Task 10: Token Bucket Rate Limiter

**Files:**
- Create: `src/bliq/data/__init__.py`
- Create: `src/bliq/data/rate_limiter.py`
- Test: `tests/unit/test_rate_limiter.py`

- [ ] **Step 1: Write the failing test**

Write `tests/unit/test_rate_limiter.py`:

```python
import asyncio
import time

import pytest

from bliq.data.rate_limiter import WeightRateLimiter


async def test_acquire_under_budget_is_nonblocking():
    rl = WeightRateLimiter(capacity_per_minute=100)
    start = time.monotonic()
    await rl.acquire(10)
    await rl.acquire(20)
    elapsed = time.monotonic() - start
    assert elapsed < 0.05


async def test_acquire_over_budget_waits_until_window_reset():
    rl = WeightRateLimiter(capacity_per_minute=100, _now=lambda: 0.0)
    # Fast-forward time manually via _now injection.
    now = [0.0]
    rl._now = lambda: now[0]

    await rl.acquire(60)
    await rl.acquire(30)
    # We've used 90 in the window starting at 0.
    # Requesting 20 should need to wait until the window rolls over at 60s.
    wait_coro = rl.acquire(20)

    async def advance():
        # Pump time forward to simulate the window rolling over.
        await asyncio.sleep(0)
        now[0] = 61.0
        await rl._tick()

    await asyncio.gather(wait_coro, advance())
    # After acquire completes, used should reflect only the new request.
    assert rl.used == 20


async def test_reconcile_with_server_header_resets_counter():
    rl = WeightRateLimiter(capacity_per_minute=2400)
    await rl.acquire(10)
    rl.reconcile(used_weight_1m=1500)
    assert rl.used == 1500
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/unit/test_rate_limiter.py -v`
Expected: ImportError.

- [ ] **Step 3: Write `src/bliq/data/__init__.py`**

Write:

```python
```

- [ ] **Step 4: Implement `src/bliq/data/rate_limiter.py`**

Write:

```python
"""Token-bucket-style rate limiter for Binance weight quotas.

Binance USDT-M Futures is capped at ``rate_limit_weight_per_min`` weight per
IP per rolling minute. This limiter keeps a local counter, reconciles it
against ``X-MBX-USED-WEIGHT-1M`` response headers, and blocks callers when
the budget is exhausted until the current 60-second window rolls over.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable


class WeightRateLimiter:
    def __init__(
        self,
        capacity_per_minute: int,
        *,
        _now: Callable[[], float] | None = None,
    ) -> None:
        self.capacity = capacity_per_minute
        self._now = _now or time.monotonic
        self._window_start = self._now()
        self._used = 0
        self._lock = asyncio.Lock()
        self._cond = asyncio.Condition(self._lock)

    @property
    def used(self) -> int:
        return self._used

    async def _tick(self) -> None:
        """Roll the window forward if >=60s have elapsed, and wake waiters."""
        async with self._cond:
            if self._now() - self._window_start >= 60.0:
                self._window_start = self._now()
                self._used = 0
                self._cond.notify_all()

    async def acquire(self, weight: int) -> None:
        async with self._cond:
            while True:
                if self._now() - self._window_start >= 60.0:
                    self._window_start = self._now()
                    self._used = 0
                if self._used + weight <= self.capacity:
                    self._used += weight
                    return
                # Wait until the window advances. Use wait_for with a small
                # timeout so external _now injection can advance time.
                try:
                    await asyncio.wait_for(self._cond.wait(), timeout=0.05)
                except TimeoutError:
                    continue

    def reconcile(self, used_weight_1m: int) -> None:
        """Update the local counter from a server-reported value."""
        self._used = int(used_weight_1m)
```

- [ ] **Step 5: Run to verify pass**

Run: `uv run pytest tests/unit/test_rate_limiter.py -v`
Expected: 3 passed.

- [ ] **Step 6: Commit**

```bash
git add src/bliq/data/__init__.py src/bliq/data/rate_limiter.py tests/unit/test_rate_limiter.py
git commit -m "feat(data): async weight-based rate limiter for binance fapi"
```

---

## Task 11: Binance REST Client

**Files:**
- Create: `src/bliq/data/binance_rest.py`
- Create: `tests/fixtures/orderbook_btcusdt.json`
- Test: `tests/unit/test_binance_rest.py`

- [ ] **Step 1: Create the order book fixture**

Write `tests/fixtures/orderbook_btcusdt.json`:

```json
{
  "lastUpdateId": 123456789,
  "E": 1744387200000,
  "T": 1744387200000,
  "bids": [
    ["65000.00", "1.500"],
    ["64999.50", "2.000"],
    ["64999.00", "0.800"],
    ["64998.00", "5.000"],
    ["64997.00", "1.200"]
  ],
  "asks": [
    ["65001.00", "1.800"],
    ["65001.50", "2.500"],
    ["65002.00", "0.600"],
    ["65003.00", "4.000"],
    ["65004.00", "0.900"]
  ]
}
```

- [ ] **Step 2: Write the failing test**

Write `tests/unit/test_binance_rest.py`:

```python
import json
from pathlib import Path

import pytest
from pytest_httpx import HTTPXMock

from bliq.data.binance_rest import BinanceRestClient
from bliq.data.rate_limiter import WeightRateLimiter
from bliq.infra.errors import BinanceAPIError, RateLimitError


BASE = "https://fapi.binance.com"


@pytest.fixture
def client() -> BinanceRestClient:
    return BinanceRestClient(
        base_url=BASE,
        rate_limiter=WeightRateLimiter(capacity_per_minute=2400),
        retry_attempts=3,
        retry_backoff_base=0.0,
    )


async def test_fetch_depth_parses_levels(
    client: BinanceRestClient, fixtures_dir: Path, httpx_mock: HTTPXMock
):
    payload = json.loads((fixtures_dir / "orderbook_btcusdt.json").read_text())
    httpx_mock.add_response(
        url=f"{BASE}/fapi/v1/depth?symbol=BTCUSDT&limit=20",
        json=payload,
        headers={"X-MBX-USED-WEIGHT-1M": "12"},
    )

    async with client:
        ob = await client.fetch_depth("BTCUSDT", limit=20)

    assert ob.symbol == "BTCUSDT"
    assert ob.best_bid == 65000.0
    assert ob.best_ask == 65001.0
    assert len(ob.bids) == 5
    assert len(ob.asks) == 5


async def test_retries_on_5xx_then_succeeds(
    client: BinanceRestClient, fixtures_dir: Path, httpx_mock: HTTPXMock
):
    payload = json.loads((fixtures_dir / "orderbook_btcusdt.json").read_text())
    url = f"{BASE}/fapi/v1/depth?symbol=BTCUSDT&limit=20"
    httpx_mock.add_response(url=url, status_code=502)
    httpx_mock.add_response(url=url, status_code=503)
    httpx_mock.add_response(url=url, json=payload)

    async with client:
        ob = await client.fetch_depth("BTCUSDT", limit=20)
    assert ob.best_bid == 65000.0


async def test_429_raises_rate_limit_error(
    client: BinanceRestClient, httpx_mock: HTTPXMock
):
    url = f"{BASE}/fapi/v1/depth?symbol=BTCUSDT&limit=20"
    httpx_mock.add_response(url=url, status_code=429)
    httpx_mock.add_response(url=url, status_code=429)
    httpx_mock.add_response(url=url, status_code=429)
    async with client:
        with pytest.raises(RateLimitError):
            await client.fetch_depth("BTCUSDT", limit=20)


async def test_4xx_other_raises_api_error(
    client: BinanceRestClient, httpx_mock: HTTPXMock
):
    url = f"{BASE}/fapi/v1/depth?symbol=FOOUSDT&limit=20"
    httpx_mock.add_response(
        url=url, status_code=400, json={"code": -1121, "msg": "Invalid symbol."}
    )
    async with client:
        with pytest.raises(BinanceAPIError):
            await client.fetch_depth("FOOUSDT", limit=20)


async def test_reconciles_weight_header(
    client: BinanceRestClient, fixtures_dir: Path, httpx_mock: HTTPXMock
):
    payload = json.loads((fixtures_dir / "orderbook_btcusdt.json").read_text())
    httpx_mock.add_response(
        url=f"{BASE}/fapi/v1/depth?symbol=BTCUSDT&limit=20",
        json=payload,
        headers={"X-MBX-USED-WEIGHT-1M": "987"},
    )
    async with client:
        await client.fetch_depth("BTCUSDT", limit=20)
    assert client.rate_limiter.used == 987
```

**Deviation from spec:** the spec names `aiohttp` as the HTTP client, but this plan uses `httpx` instead. Rationale: `httpx` has first-class async support, is actively maintained, and `pytest-httpx` gives us clean transport-level mocking without running a fake server. This is a permanent switch — replace `aiohttp` with `httpx` in dependencies in the next step.

- [ ] **Step 3: Update `pyproject.toml` to use httpx instead of aiohttp**

In `pyproject.toml`, replace `"aiohttp>=3.9",` with `"httpx>=0.27",`. Then run:

```bash
uv sync
```

Expected: httpx installs; aiohttp is removed from the lockfile.

- [ ] **Step 4: Run the failing test**

Run: `uv run pytest tests/unit/test_binance_rest.py -v`
Expected: ImportError — `bliq.data.binance_rest` does not exist.

- [ ] **Step 5: Implement `src/bliq/data/binance_rest.py`**

Write:

```python
"""Async Binance USDT-M Futures REST client.

Wraps the subset of ``/fapi/v1`` endpoints needed by M1 (depth). Future
milestones will add klines, aggTrades, ticker, and exchangeInfo.
"""

from __future__ import annotations

import asyncio
from typing import Any

import httpx

from bliq.data.rate_limiter import WeightRateLimiter
from bliq.infra.errors import BinanceAPIError, RateLimitError, SymbolNotFoundError
from bliq.metrics.types import OrderBook, OrderBookLevel

ENDPOINT_WEIGHTS = {
    "/fapi/v1/depth": 2,  # limit <= 50 costs 2; we stay within that.
}


class BinanceRestClient:
    def __init__(
        self,
        *,
        base_url: str,
        rate_limiter: WeightRateLimiter,
        retry_attempts: int = 3,
        retry_backoff_base: float = 1.0,
        timeout: float = 10.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.rate_limiter = rate_limiter
        self.retry_attempts = retry_attempts
        self.retry_backoff_base = retry_backoff_base
        self.timeout = timeout
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> "BinanceRestClient":
        self._client = httpx.AsyncClient(timeout=self.timeout)
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def _get(
        self, path: str, params: dict[str, Any] | None = None
    ) -> httpx.Response:
        if self._client is None:
            raise RuntimeError("BinanceRestClient used outside its async context")
        weight = ENDPOINT_WEIGHTS.get(path, 1)
        url = f"{self.base_url}{path}"
        last_exc: Exception | None = None
        for attempt in range(self.retry_attempts):
            await self.rate_limiter.acquire(weight)
            try:
                resp = await self._client.get(url, params=params)
            except httpx.HTTPError as exc:
                last_exc = exc
                await asyncio.sleep(self.retry_backoff_base * (2**attempt))
                continue

            header = resp.headers.get("X-MBX-USED-WEIGHT-1M")
            if header is not None:
                try:
                    self.rate_limiter.reconcile(int(header))
                except ValueError:
                    pass

            if resp.status_code == 429 or resp.status_code == 418:
                if attempt < self.retry_attempts - 1:
                    retry_after = float(resp.headers.get("Retry-After", "1"))
                    await asyncio.sleep(retry_after)
                    continue
                raise RateLimitError(f"rate limited: {resp.status_code}")
            if 500 <= resp.status_code < 600:
                last_exc = BinanceAPIError(f"server error {resp.status_code}")
                await asyncio.sleep(self.retry_backoff_base * (2**attempt))
                continue
            if resp.status_code >= 400:
                try:
                    body = resp.json()
                    msg = body.get("msg", "")
                    code = body.get("code", 0)
                except Exception:
                    msg, code = resp.text, 0
                if code == -1121:
                    raise SymbolNotFoundError(msg)
                raise BinanceAPIError(f"{resp.status_code}: {msg}")
            return resp
        raise BinanceAPIError(f"request to {path} failed: {last_exc}")

    async def fetch_depth(self, symbol: str, *, limit: int = 20) -> OrderBook:
        resp = await self._get(
            "/fapi/v1/depth", params={"symbol": symbol, "limit": limit}
        )
        body = resp.json()
        bids = tuple(
            OrderBookLevel(float(p), float(q)) for p, q in body.get("bids", [])
        )
        asks = tuple(
            OrderBookLevel(float(p), float(q)) for p, q in body.get("asks", [])
        )
        ts_ms = int(body.get("E") or body.get("T") or 0)
        return OrderBook(symbol=symbol, ts_ms=ts_ms, bids=bids, asks=asks)
```

- [ ] **Step 6: Run the tests to verify pass**

Run: `uv run pytest tests/unit/test_binance_rest.py -v`
Expected: 5 passed.

- [ ] **Step 7: Commit**

```bash
git add pyproject.toml src/bliq/data/binance_rest.py tests/unit/test_binance_rest.py tests/fixtures/orderbook_btcusdt.json
git commit -m "feat(data): httpx binance fapi client with retry and weight reconciliation"
```

---

## Task 12: Symbol Resolver

**Files:**
- Create: `src/bliq/data/symbols.py`
- Test: `tests/unit/test_symbols.py`

For M1, the resolver only needs to handle `--symbols`, `--all`, and `--from-file`. The `--top N` branch is stubbed until M2 ships `/fapi/v1/ticker/24hr`.

- [ ] **Step 1: Write the failing test**

Write `tests/unit/test_symbols.py`:

```python
from pathlib import Path

import pytest
import yaml

from bliq.data.symbols import SymbolSelection, resolve_symbols
from bliq.infra.errors import ConfigError


def test_explicit_list():
    out = resolve_symbols(
        SymbolSelection(explicit=["BTCUSDT", "ETHUSDT"])
    )
    assert out == ["BTCUSDT", "ETHUSDT"]


def test_from_file_yaml_list(tmp_path: Path):
    f = tmp_path / "symbols.yaml"
    yaml.safe_dump({"symbols": ["BTCUSDT", "SOLUSDT"]}, f.open("w"))
    out = resolve_symbols(SymbolSelection(from_file=f))
    assert out == ["BTCUSDT", "SOLUSDT"]


def test_from_file_plain_text(tmp_path: Path):
    f = tmp_path / "symbols.txt"
    f.write_text("BTCUSDT\n# comment\nETHUSDT\n\n")
    out = resolve_symbols(SymbolSelection(from_file=f))
    assert out == ["BTCUSDT", "ETHUSDT"]


def test_no_selection_raises():
    with pytest.raises(ConfigError, match="no symbol selection"):
        resolve_symbols(SymbolSelection())


def test_top_n_requires_m2(tmp_path: Path):
    with pytest.raises(ConfigError, match="--top is not available in M1"):
        resolve_symbols(SymbolSelection(top_n=50))
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/unit/test_symbols.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement `src/bliq/data/symbols.py`**

Write:

```python
"""Symbol selection / resolution for all bliq subcommands.

M1 supports: explicit list, from-file (YAML or newline text), or a stubbed
"all" branch placeholder. The `--top N` branch is defined here but raises
until M2 ships the 24h ticker fetch.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

from bliq.infra.errors import ConfigError


@dataclass
class SymbolSelection:
    explicit: list[str] = field(default_factory=list)
    all_symbols: bool = False
    top_n: int | None = None
    from_file: Path | None = None


def _load_file(path: Path) -> list[str]:
    if not path.exists():
        raise ConfigError(f"symbols file not found: {path}")
    text = path.read_text()
    if path.suffix in {".yaml", ".yml"}:
        data = yaml.safe_load(text) or {}
        if isinstance(data, list):
            return [str(s).strip() for s in data if str(s).strip()]
        if isinstance(data, dict) and "symbols" in data:
            return [str(s).strip() for s in data["symbols"] if str(s).strip()]
        raise ConfigError(f"unexpected YAML shape in {path}")
    # plain text: one symbol per line, '#' for comments
    out: list[str] = []
    for line in text.splitlines():
        line = line.split("#", 1)[0].strip()
        if line:
            out.append(line)
    return out


def resolve_symbols(sel: SymbolSelection) -> list[str]:
    if sel.explicit:
        return list(sel.explicit)
    if sel.from_file is not None:
        return _load_file(sel.from_file)
    if sel.top_n is not None:
        raise ConfigError("--top is not available in M1 (arrives in M2)")
    if sel.all_symbols:
        raise ConfigError("--all is not available in M1 (arrives in M2)")
    raise ConfigError("no symbol selection provided")
```

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest tests/unit/test_symbols.py -v`
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add src/bliq/data/symbols.py tests/unit/test_symbols.py
git commit -m "feat(data): symbol selection resolver (explicit + file for m1)"
```

---

## Task 13: SQLite Storage — Schema and Writer

**Files:**
- Create: `src/bliq/data/storage.py`
- Test: `tests/unit/test_storage.py`

- [ ] **Step 1: Write the failing test**

Write `tests/unit/test_storage.py`:

```python
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
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/unit/test_storage.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement `src/bliq/data/storage.py`**

Write:

```python
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
        ts              INTEGER NOT NULL,
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
    "CREATE INDEX IF NOT EXISTS idx_snapshots_symbol_ts ON snapshots(symbol, ts)",
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
            "ts": report.ts_ms,
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
                assert snap_id is not None
                return int(snap_id)
        except sqlite3.Error as exc:
            raise StorageError(f"failed to insert report: {exc}") from exc
```

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest tests/unit/test_storage.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add src/bliq/data/storage.py tests/unit/test_storage.py
git commit -m "feat(data): sqlite snapshot store with wal and slippage subtable"
```

---

## Task 14: Snapshot Mode Orchestrator

**Files:**
- Create: `src/bliq/modes/__init__.py`
- Create: `src/bliq/modes/snapshot.py`

The snapshot mode for M1 is a single-shot: for each symbol, fetch the order book, compute all static metrics, build a `LiquidityReport`, and persist it.

- [ ] **Step 1: Write `src/bliq/modes/__init__.py`**

Write:

```python
```

- [ ] **Step 2: Write `src/bliq/modes/snapshot.py`**

Write:

```python
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

    reports: list[LiquidityReport] = []
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
```

- [ ] **Step 3: Smoke-import**

Run: `uv run python -c "from bliq.modes.snapshot import run_snapshot_once, build_report; print('ok')"`
Expected: `ok`

- [ ] **Step 4: Commit**

```bash
git add src/bliq/modes/__init__.py src/bliq/modes/snapshot.py
git commit -m "feat(modes): snapshot one-shot orchestrator (spread+depth+obi+slippage)"
```

---

## Task 15: CLI Entry

**Files:**
- Create: `src/bliq/cli/__init__.py`
- Create: `src/bliq/cli/main.py`

- [ ] **Step 1: Write `src/bliq/cli/__init__.py`**

Write:

```python
```

- [ ] **Step 2: Write `src/bliq/cli/main.py`**

Write:

```python
"""typer CLI entry for bliq."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import typer
from loguru import logger
from rich.console import Console
from rich.table import Table

from bliq.data.symbols import SymbolSelection, resolve_symbols
from bliq.infra.config import Config, load_config
from bliq.infra.errors import BliqError
from bliq.infra.logging import setup_logging
from bliq.modes.snapshot import run_snapshot_once

app = typer.Typer(
    name="bliq",
    help="Binance USDT-M perpetual futures liquidity measurement.",
    no_args_is_help=True,
    add_completion=False,
)
console = Console()

DEFAULT_CONFIG = Path("config/default.yaml")


def _bootstrap(config_path: Path) -> Config:
    try:
        cfg = load_config(config_path)
    except BliqError as exc:
        console.print(f"[red]config error:[/red] {exc}")
        raise typer.Exit(code=2)
    setup_logging(cfg.logging)
    return cfg


def _selection(
    symbols: str | None, all_flag: bool, top: int | None, from_file: Path | None
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
    from_file: Path = typer.Option(None, "--from-file", help="YAML or text file"),
    config_path: Path = typer.Option(
        DEFAULT_CONFIG, "--config", help="Path to config yaml"
    ),
    db: Path = typer.Option(
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
        raise typer.Exit(code=2)

    try:
        reports = asyncio.run(
            run_snapshot_once(
                target_symbols, cfg, db_path=db, fail_fast=fail_fast
            )
        )
    except BliqError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1)

    _print_report_table(reports)
    console.print(
        f"[green]persisted {len(reports)} snapshot(s) to "
        f"{db or cfg.storage.db_path}[/green]"
    )
```

- [ ] **Step 3: Smoke-test `--help`**

Run: `uv run bliq --help`
Expected: typer help text showing the `snapshot` subcommand.

Run: `uv run bliq snapshot --help`
Expected: help for `snapshot` showing `--symbols`, `--all`, `--top`, `--from-file`, `--config`, `--db`, `--fail-fast`.

- [ ] **Step 4: Commit**

```bash
git add src/bliq/cli/__init__.py src/bliq/cli/main.py
git commit -m "feat(cli): typer entry with snapshot subcommand and rich table output"
```

---

## Task 16: End-to-End Integration Test (Mocked)

**Files:**
- Create: `tests/integration/__init__.py`
- Create: `tests/integration/test_snapshot_e2e.py`

- [ ] **Step 1: Create `tests/integration/__init__.py`**

Write:

```python
```

- [ ] **Step 2: Write the e2e test with httpx mock**

Write `tests/integration/test_snapshot_e2e.py`:

```python
"""End-to-end test for `bliq snapshot` without hitting the network.

All httpx traffic is intercepted by pytest-httpx. The real SQLite store is
used on a tmp_path.
"""

import json
import sqlite3
from pathlib import Path

import pytest
import yaml
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
```

- [ ] **Step 3: Run the e2e test**

Run: `uv run pytest tests/integration/test_snapshot_e2e.py -v`
Expected: 2 passed.

- [ ] **Step 4: Run the full test suite and verify everything is green**

Run: `uv run pytest -v`
Expected: all tests from tasks 3-16 pass.

Run: `uv run ruff check src tests`
Expected: `All checks passed!`

- [ ] **Step 5: Commit**

```bash
git add tests/integration
git commit -m "test(integration): end-to-end snapshot with mocked httpx transport"
```

---

## Task 17: README Quickstart

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Replace the current README with a real quickstart**

Overwrite `README.md`:

```markdown
# bliq — Binance Perpetual Liquidity Measurement

`bliq` is a CLI tool that measures the liquidity of Binance USDT-M perpetual
futures contracts. It computes static order-book metrics (spread, depth, OBI,
slippage ladder, capacity) and persists them to SQLite.

**Status:** M1 — `snapshot` subcommand is functional. `scan`, `analyze`, and
`monitor` land in later milestones.

## Requirements

- Python 3.11+
- [uv](https://github.com/astral-sh/uv) for dependency management

## Install

```bash
uv sync
```

## Usage

### One-shot snapshot for specific symbols

```bash
uv run bliq snapshot --symbols BTCUSDT,ETHUSDT
```

This fetches the current order book for each symbol, computes all M1 metrics,
prints a summary table to the terminal, and persists one row per symbol into
`liquidity.db` (SQLite, WAL mode).

### From a file

`symbols.yaml`:
```yaml
symbols:
  - BTCUSDT
  - ETHUSDT
  - SOLUSDT
```

```bash
uv run bliq snapshot --from-file symbols.yaml
```

### Override the database location

```bash
uv run bliq snapshot --symbols BTCUSDT --db /tmp/bliq.db
```

### Custom config

```bash
uv run bliq snapshot --symbols BTCUSDT --config my-config.yaml
```

See `config/default.yaml` for the full list of tunable parameters
(depth percentages, slippage ladder, OBI levels, retry policy, etc.).

## Design

See `docs/superpowers/specs/2026-04-11-binance-liquidity-measurement-design.md`
for the full architecture and metric definitions.

## Development

```bash
uv run pytest            # run unit + integration tests
uv run ruff check src tests
uv run ruff format src tests
```

Integration tests that hit the real Binance API are marked `integration` and
opt-in:

```bash
uv run pytest -m integration
```

## License

See `LICENSE`.
```

- [ ] **Step 2: Verify the CLI actually works against the real Binance API**

Run (this hits real network — optional, skip if offline):

```bash
uv run bliq snapshot --symbols BTCUSDT --db /tmp/bliq-smoke.db
```

Expected: a rich table with one row for BTCUSDT, and the message
`persisted 1 snapshot(s) to /tmp/bliq-smoke.db`. Confirm with:

```bash
sqlite3 /tmp/bliq-smoke.db "SELECT symbol, mid_price, spread_bps FROM snapshots"
```

Expected: one row with BTCUSDT and realistic numbers.

If this step is not feasible (no network / firewall), skip it and note in the
commit message.

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs: readme quickstart for m1 snapshot mode"
```

---

## Final Verification Checklist

- [ ] `uv run pytest -v` — all unit + integration tests pass.
- [ ] `uv run ruff check src tests` — clean.
- [ ] `uv run bliq --help` — shows `snapshot` subcommand.
- [ ] `uv run bliq snapshot --symbols BTCUSDT` — writes a row (real network) or mocked equivalent works.
- [ ] Git history shows one commit per task (~17 commits).
- [ ] Coverage spot-check: `metrics/` modules each have at least one test file.

## Out of Scope for M1 (Deferred to M2+)

- `--top N` symbol selection (needs `/fapi/v1/ticker/24hr` client).
- `--all` symbol selection (needs `/fapi/v1/exchangeInfo` client).
- `metrics/taker_ratio` and `metrics/amihud` (need aggTrades + klines fetchers).
- `metrics/score` composite liquidity score.
- `scan` subcommand and ranked table output.
- `analyze` subcommand and HTML report.
- `monitor` subcommand, WS client, alerts DSL, webhook notifier.
- Scheduler loop for `snapshot --every` (currently one-shot only).
