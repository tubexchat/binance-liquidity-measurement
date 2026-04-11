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

## Metrics Computed in M1

| Metric | Description |
|---|---|
| **Relative spread (bps)** | `(ask1 - bid1) / mid × 10000` |
| **Depth bands** | Cumulative USDT within ±0.1%, ±0.5%, ±1%, ±2% of mid (bid and ask sides) |
| **OBI** | Order Book Imbalance at top 5/10/20 levels: `(ΣV_bid - ΣV_ask) / (ΣV_bid + ΣV_ask)` |
| **Slippage ladder** | Simulated market-order slippage at notional levels `[1k, 5k, 10k, 50k, 100k, 500k, 1M]` USDT, both buy and sell |
| **Capacity @ 20 bps** | Maximum notional that can be absorbed before slippage exceeds 20 bps, both sides |

Dynamic metrics (taker ratio, Amihud illiquidity, composite `liquidity_score`)
land in M2.

## Design

See `docs/superpowers/specs/2026-04-11-binance-liquidity-measurement-design.md`
for the full architecture and metric definitions. The M1 implementation plan
is at `docs/superpowers/plans/2026-04-11-bliq-m1-foundation.md`.

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
