# bliq

**Binance USDT-M perpetual futures liquidity measurement CLI.**

bliq fetches real-time order book data from Binance, computes a suite of liquidity metrics, and persists results to SQLite for further analysis. Built for quant researchers, market makers, and traders who need to quantify execution costs before sizing positions.

## Features

- One-shot snapshot of any USDT-M perpetual contract
- Batch scanning across all 500+ trading pairs
- Computes spread, depth, order book imbalance, slippage ladder, and capacity metrics
- SQLite persistence with WAL mode for concurrent reads
- Configurable via YAML (depth bands, slippage levels, OBI levels, retry policy)
- Rate-limit aware with automatic backoff and retry

## Quick Start

### Prerequisites

- Python 3.11+
- [uv](https://github.com/astral-sh/uv)

### Install

```bash
git clone https://github.com/<your-org>/bliq.git
cd bliq
uv sync
```

### Snapshot a single pair

```bash
uv run bliq snapshot --symbols BTCUSDT
```

### Snapshot multiple pairs

```bash
uv run bliq snapshot --symbols BTCUSDT,ETHUSDT,SOLUSDT
```

### Load symbols from file

```yaml
# symbols.yaml
symbols:
  - BTCUSDT
  - ETHUSDT
  - SOLUSDT
```

```bash
uv run bliq snapshot --from-file symbols.yaml
```

### Override database path

```bash
uv run bliq snapshot --symbols BTCUSDT --db /tmp/bliq.db
```

## Metrics

### Relative Spread (bps)

```
(best_ask - best_bid) / mid_price * 10000
```

Measures the tightness of the top-of-book. Lower is better.

### Depth Bands

Cumulative USDT liquidity within percentage bands of the mid price, on both bid and ask sides:

| Band | Description |
|------|-------------|
| +/-0.1% | Tight liquidity around mid |
| +/-0.5% | Near-book depth |
| +/-1.0% | Medium depth |
| +/-2.0% | Wide depth |

### Order Book Imbalance (OBI)

```
OBI = (sum(bid_qty) - sum(ask_qty)) / (sum(bid_qty) + sum(ask_qty))
```

Computed at top 5, 10, and 20 levels. Range `[-1, +1]`. Positive = heavier bid side.

### Slippage Ladder

Simulates a market order at increasing notional sizes and reports the expected slippage in bps:

| Notional (USDT) |
|-----------------|
| 1,000 |
| 5,000 |
| 10,000 |
| 50,000 |
| 100,000 |
| 500,000 |
| 1,000,000 |

Both buy and sell sides are simulated independently.

### Capacity @ 20 bps

The maximum notional (in USDT) that can be executed before slippage exceeds 20 bps. Reported for both buy and sell sides. This is the single most useful metric for position sizing.

## Example Output

```
                           Liquidity Snapshot
┏━━━━━━━━━┳━━━━━━━━━━┳━━━━━━━━━━━━━┳━━━━━━━━┳━━━━━━━━━━━━┳━━━━━━━━━━━━━┓
┃ symbol  ┃      mid ┃ spread(bps) ┃  obi_5 ┃ cap_buy($) ┃ cap_sell($) ┃
┡━━━━━━━━━╇━━━━━━━━━━╇━━━━━━━━━━━━━╇━━━━━━━━╇━━━━━━━━━━━━╇━━━━━━━━━━━━━┩
│ BTCUSDT │ 71,684.1 │        0.01 │ +0.392 │    419,066 │   1,100,420 │
│ ETHUSDT │ 2,217.91 │        0.05 │ -0.287 │    342,971 │     239,759 │
│ SOLUSDT │    82.18 │        1.22 │ -0.009 │  5,420,937 │   7,335,869 │
└─────────┴──────────┴─────────────┴────────┴────────────┴─────────────┘
```

## Configuration

All parameters are tunable via `config/default.yaml` or a custom config file:

```bash
uv run bliq snapshot --symbols BTCUSDT --config my-config.yaml
```

Key configuration sections:

| Section | Controls |
|---------|----------|
| `metrics.depth_pcts` | Depth band percentages |
| `metrics.obi_levels` | Number of levels for OBI calculation |
| `metrics.slippage_levels_usdt` | Notional sizes for slippage ladder |
| `metrics.max_slippage_bps` | Capacity threshold (default: 20 bps) |
| `data.rate_limit_weight_per_min` | Binance API weight budget |
| `data.max_concurrent_requests` | Parallel request limit |

See [`config/default.yaml`](config/default.yaml) for the full reference.

## Architecture

```
src/bliq/
  cli/          CLI entry point (Typer)
  data/         Binance REST client, rate limiter, SQLite storage
  metrics/      Pure metric functions (spread, depth, OBI, slippage)
  modes/        Execution modes (snapshot)
  infra/        Config, logging, error types
```

The design separates data fetching, metric computation, and persistence into independent layers. Metric functions are pure — they take an `OrderBook` and return a typed result, making them easy to test and compose.

## Roadmap

| Milestone | Status | Description |
|-----------|--------|-------------|
| M1 | Done | `snapshot` — static order book metrics |
| M2 | Planned | `scan` — batch all pairs, 24h ticker ranking, Amihud illiquidity, taker ratio |
| M3 | Planned | `monitor` — WebSocket streaming, composite `liquidity_score` |
| M4 | Planned | `analyze` — historical trends, cross-pair comparison |

## Development

```bash
uv run pytest                    # unit + integration tests
uv run ruff check src tests      # lint
uv run ruff format src tests     # format
```

Integration tests that hit the real Binance API are opt-in:

```bash
uv run pytest -m integration
```

## License

[Apache License 2.0](LICENSE)
