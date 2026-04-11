# Binance Perpetual Liquidity Measurement Tool — Design Spec

- **Project:** `binance-liquidity-measurement` (CLI name: `bliq`)
- **Date:** 2026-04-11
- **Status:** Approved — ready for implementation planning
- **Scope:** Liquidity measurement for Binance USDT-M perpetual futures

---

## 1. Purpose

`bliq` is a CLI tool that measures the liquidity of Binance USDT-M perpetual
contracts across four usage modes, each exposed as a subcommand. It computes a
battery of static order-book metrics and dynamic trade-based metrics, lets users
rank/filter symbols by a composite `liquidity_score`, supports real-time
monitoring with rule-based alerts, and persists time series to SQLite for
historical replay and research.

The tool is **read-only**: it never places orders. It sits alongside the user's
existing `binance_tradingbot` project as pre-trade due-diligence and
post-trade liquidity research.

## 2. Metrics

### 2.1 Static (order-book) metrics

- **Relative bid-ask spread (bps):** `(ask1 - bid1) / mid * 10000`
- **Book depth at ±{0.1%, 0.5%, 1%, 2%}:** cumulative USDT notional within a
  percentage band off mid, both sides independently.
- **Order book imbalance (OBI)** at top `N ∈ {5, 10, 20}` levels:
  `(ΣV_bid − ΣV_ask) / (ΣV_bid + ΣV_ask)`
- **Slippage ladder:** simulated market-buy/sell fill for a fixed set of
  notional amounts (`[1k, 5k, 10k, 50k, 100k, 500k, 1M]` USDT by default).
  Output is average fill price and slippage in bps relative to mid.
- **Capacity @ 20 bps:** maximum notional USDT that can be absorbed without
  exceeding a configurable slippage cap (default 20 bps). One scalar per side
  — used as the primary "tradable size" metric for ranking.

### 2.2 Dynamic (trade-based) metrics

- **Taker buy/sell ratio** over the last 1000 aggregated trades. Highly
  skewed ratios indicate that "apparent" depth is maintained by a small number
  of one-sided participants.
- **Amihud illiquidity:** classic definition
  $$ILLIQ = \frac{1}{D} \sum_{t=1}^{D} \frac{|R_t|}{V_t}$$
  computed from kline data. Default window: **5-minute bars × 288 bars (24h)**.
  Both `interval` and `lookback` are configurable.

### 2.3 Composite `liquidity_score ∈ [0, 100]`

Weighted combination of normalized sub-metrics:

| Component       | Weight |
|----------------|--------|
| Spread          | 0.25  |
| Capacity @20bps | 0.35  |
| Amihud          | 0.25  |
| OBI stability   | 0.15  |

Each component is normalized before weighting:

- **Spread, Capacity, Amihud** are rank-normalized within the current scan
  batch (so `liquidity_score` is relative, not absolute, and only meaningful
  when comparing multiple symbols).
- **OBI stability** is `1 − clip(std(OBI_5) over last 60s, 0, 1)`, computed
  either from a short WS sampling window (analyze/monitor) or approximated
  as `1 − |OBI_5|` on a single snapshot (scan mode, where we do not have a
  time series). Scan-mode OBI stability is a degraded proxy and is labeled
  as such in output.

In `analyze` mode (single symbol), `liquidity_score` is omitted because
rank-based normalization is undefined with N=1; the terminal panel shows the
raw sub-metrics instead.

Weights live in `config/default.yaml` and are validated to sum to 1.0 at
startup.

## 3. CLI Surface

Top-level command: `bliq`. Global flags: `--config`, `--log-level`, `--db`.

### 3.1 `bliq scan` — batch ranking

```
bliq scan [--symbols A,B,C | --top N | --all | --from-file f.yaml]
          [--interval 5m] [--lookback 24h]
          [--sort-by score|spread|capacity|amihud]
          [--top-n 50] [--output report.json|.csv|.md]
          [--fail-fast]
```

Fetches order book snapshot + recent agg trades + klines for each symbol in
parallel (subject to rate-limit semaphore), computes all metrics, prints a
`rich` table sorted by `--sort-by` (default `score`). Failed symbols are
warned and skipped unless `--fail-fast`.

### 3.2 `bliq analyze SYMBOL` — single-symbol deep dive

```
bliq analyze BTCUSDT [--interval 5m] [--lookback 24h]
                     [--slippage-levels 1k,5k,...,1M] [--max-slippage 20]
                     [--html [path]] [--json [path]]
                     [--from-db] [--since T1] [--until T2]
```

Prints a full report in the terminal (one `rich` panel per metric group).
HTML and JSON are **opt-in**: passing `--html` without an argument writes to
`reports/analyze_SYMBOL_YYYYMMDD_HHMMSS.html` (same for `--json`); passing a
path writes there. HTML contains:
- depth curve (cumulative ask/bid)
- slippage ladder chart
- OBI time series (from a short WS sampling window, default 60s)
- Amihud histogram

`--from-db` replays data from SQLite instead of calling Binance.

### 3.3 `bliq monitor` — real-time dashboard + alerts

```
bliq monitor [--symbols ... | --top N | --all | --from-file f.yaml]
             [--interval 10s]
             [--alerts config/alerts.yaml] [--webhook URL]
```

Opens `<symbol>@depth20@100ms` and `<symbol>@aggTrade` WebSocket streams,
maintains a local order book per symbol, recomputes metrics every `--interval`
(default 10s). Klines for Amihud refresh every 5 minutes (REST). Renders a
`rich.Live` dashboard; rows that breach alert rules flash red, are appended
to `logs/alerts.log`, and POSTed to `--webhook` if configured.

Alert rules (YAML):

```yaml
rules:
  - name: wide_spread
    when: spread_bps > 50
  - name: thin_capacity
    when: capacity_20bps < 50000
  - name: obi_extreme
    when: abs(obi_5) > 0.7
  - name: rapid_deterioration
    when: capacity_20bps < 0.5 * ema(capacity_20bps, 5min)
```

`when` expressions are parsed by a restricted AST evaluator that allows numeric
comparisons and a whitelist of functions (`abs`, `ema`, `avg`, `min`, `max`).

### 3.4 `bliq snapshot` — scheduled persistence

```
bliq snapshot [--symbols ... | --top N | --all | --from-file f.yaml]
              [--every 10s] [--duration 24h] [--db liquidity.db]
```

Runs a periodic sampling loop that writes one row per symbol per tick into
SQLite. Default `--every` is 10s, matching monitor mode. `--duration 0`
runs until Ctrl+C. Terminal output is a single-line heartbeat log.

## 4. Architecture

### 4.1 Layering

```
cli/        typer entry + 4 subcommands
modes/      scan.py, analyze.py, monitor.py, snapshot.py (orchestration only)
metrics/    pure functions: spread, depth, obi, slippage,
            taker_ratio, amihud, score
reporters/  table (rich), json, csv, md, html, live_dashboard, sqlite_writer
data/       binance_rest, binance_ws, symbols, storage
infra/      config, logging, errors
```

**Key boundary rules:**
- `metrics/` is pure (no IO, no global state, fully unit-testable).
- `data/` owns every network/disk IO call.
- `modes/` is glue: decides what to fetch, which metric functions to call,
  and which reporters to invoke. Each modes file targets ~100-200 LOC.
- `reporters/` are pluggable; multiple reporters may consume the same report.

### 4.2 Directory layout (src layout)

```
binance-liquidity-measurement/
├── pyproject.toml
├── README.md
├── config/
│   ├── default.yaml
│   └── alerts.example.yaml
├── src/bliq/
│   ├── cli/
│   ├── modes/
│   ├── metrics/
│   ├── reporters/
│   ├── data/
│   └── infra/
├── tests/
│   ├── fixtures/
│   ├── unit/
│   └── integration/
└── docs/
```

### 4.3 Data flow (per symbol, per sample)

```
binance_rest.depth(symbol, limit=20)    ──┐
binance_rest.klines(symbol, interval,      │  OrderBookSnapshot
                    limit=288)          ──┼─▶ Klines
binance_rest.agg_trades(symbol,            │  AggTrades
                        limit=1000)     ──┘
                   │
                   ▼
metrics.{spread, depth, obi, slippage,
         taker_ratio, amihud, score}
                   │
                   ▼
            LiquidityReport
                   │
        ┌──────────┼───────────┬──────────┐
        ▼          ▼           ▼          ▼
   TableReporter  JsonRep.  HtmlRep.  SqliteWriter
```

Monitor mode differs: WS maintains a live order book; metrics are recomputed
on a timer rather than from a freshly-pulled REST snapshot. Amihud still
uses REST klines (refreshed every 5 min).

## 5. Storage — SQLite Schema

```sql
CREATE TABLE snapshots (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol         TEXT    NOT NULL,
    ts             INTEGER NOT NULL,        -- Unix ms
    mid_price      REAL    NOT NULL,
    spread_bps     REAL    NOT NULL,
    obi_5          REAL,
    obi_10         REAL,
    obi_20         REAL,
    depth_01pct_bid  REAL, depth_01pct_ask  REAL,
    depth_05pct_bid  REAL, depth_05pct_ask  REAL,
    depth_1pct_bid   REAL, depth_1pct_ask   REAL,
    depth_2pct_bid   REAL, depth_2pct_ask   REAL,
    capacity_20bps_bid REAL,
    capacity_20bps_ask REAL,
    amihud         REAL,
    taker_buy_ratio REAL,
    liquidity_score REAL
);
CREATE INDEX idx_snapshots_symbol_ts ON snapshots(symbol, ts);

CREATE TABLE slippage_points (
    snapshot_id   INTEGER NOT NULL REFERENCES snapshots(id) ON DELETE CASCADE,
    side          TEXT    NOT NULL,         -- 'buy' or 'sell'
    notional_usdt REAL    NOT NULL,
    slippage_bps  REAL    NOT NULL,
    avg_fill_px   REAL    NOT NULL,
    PRIMARY KEY (snapshot_id, side, notional_usdt)
);

CREATE TABLE alerts (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    ts          INTEGER NOT NULL,
    symbol      TEXT    NOT NULL,
    rule_name   TEXT    NOT NULL,
    rule_expr   TEXT    NOT NULL,
    snapshot_id INTEGER REFERENCES snapshots(id),
    payload     TEXT                         -- JSON of full snapshot
);
CREATE INDEX idx_alerts_ts ON alerts(ts);
CREATE INDEX idx_alerts_symbol_ts ON alerts(symbol, ts);

CREATE TABLE schema_version (version INTEGER PRIMARY KEY);
```

- Wide `snapshots` table for ergonomic time-series queries.
- `slippage_points` is a child table because ladder length is configurable.
- `alerts.payload` stores a JSON blob of the triggering snapshot for
  standalone forensic inspection.
- SQLite is opened with `PRAGMA journal_mode=WAL` so background `snapshot`
  and foreground `analyze --from-db` can run concurrently.
- Klines are **not** persisted. They are cached in-process in a small
  TTL-LRU map (TTL = 60s) to avoid re-fetching within a single scan.

## 6. Networking, Rate Limits & Reliability

### 6.1 REST rate limits

Binance USDT-M futures REST is IP-limited to **2400 weight per minute**.
Per-endpoint weights used by this tool:

| Endpoint | Weight |
|---|---|
| `/fapi/v1/depth?limit=20` | 2 |
| `/fapi/v1/klines?limit=288` | 2 |
| `/fapi/v1/aggTrades?limit=1000` | 20 |
| `/fapi/v1/exchangeInfo` | 1 |
| `/fapi/v1/ticker/24hr` (single) | 1 |
| `/fapi/v1/ticker/24hr` (all)    | 40 |

`data/binance_rest.py`:

1. **Token bucket limiter** keyed on the weight budget; every request subtracts
   its weight before firing and sleeps if the remaining budget would go
   negative. The local counter is reconciled against `X-MBX-USED-WEIGHT-1M`
   response headers on every response to prevent drift.
2. **Concurrent requests** via `aiohttp` + `asyncio.Semaphore(20)`.
3. **Retry policy:**
   - 5xx / connection timeout → exponential backoff (1s, 2s, 4s) × 3
   - 429 / 418 → honor `Retry-After` header, then retry
   - other 4xx → raise immediately
   - terminal failure → raise to `modes/` which warns-and-skips by default
     (`--fail-fast` aborts the run)

### 6.2 WebSocket

`data/binance_ws.py` opens a combined stream
(`wss://fstream.binance.com/stream?streams=...`) with these responsibilities:

1. **Subscription management** at runtime.
2. **Local order book sync** following Binance's documented REST-snapshot +
   buffered-diff algorithm. Each symbol carries its own book and lastUpdateId.
3. **Heartbeat / reconnect:** no-message-in-10-min → close and reconnect with
   exponential backoff up to 60s. On reconnect, re-run the sync procedure.
   Dashboard shows a "reconnecting" indicator during the gap but does not
   crash.
4. **Backpressure:** bounded `asyncio.Queue(maxsize=10000)` between the reader
   and the consumer; overflow drops oldest diffs and logs a warning (the next
   resnap covers the gap).

### 6.3 Error taxonomy

```python
class BliqError(Exception): ...
class ConfigError(BliqError): ...
class BinanceAPIError(BliqError): ...
class RateLimitError(BinanceAPIError): ...
class SymbolNotFoundError(BinanceAPIError): ...
class DataIntegrityError(BliqError): ...
class StorageError(BliqError): ...
```

The CLI entry point catches `BliqError`, prints a friendly message, and exits
non-zero. Everything else falls through as a regular traceback.

## 7. Configuration

All defaults live in `config/default.yaml`:

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
  rotation: 10 MB
```

Override layers (highest wins): CLI flag → `BLIQ_*` env var → user
`--config my.yaml` → `config/default.yaml`. Score weights are validated to
sum to 1.0 at startup; configuration validation raises `ConfigError`.

## 8. Tooling & Test Strategy

| Concern | Choice |
|---|---|
| Python | **3.11+** |
| Packaging | **uv** + `pyproject.toml` |
| CLI framework | **typer** |
| Config | **YAML** (+ `pydantic` model for validation) |
| HTTP | **aiohttp** (async) |
| WS | **websockets** |
| Logging | **loguru** |
| Rendering | **rich** |
| Charts (HTML) | **plotly** (self-contained HTML, no CDN) |
| Lint + format | **ruff** + `ruff format` |
| Tests | **pytest** |

### 8.1 Test layers

| Layer | Scope | Approach |
|---|---|---|
| `metrics/` | Pure function correctness incl. degenerate cases (empty book, zero spread, empty trades) | pytest + hand-written dict fixtures |
| `data/binance_rest` | Limiter, retry, parsing | pytest + `pytest-httpx` mocks incl. 429/5xx/timeout |
| `data/binance_ws` | Book sync, reconnect | pytest + recorded WS message replay |
| `data/storage` | Schema, migrations, queries | in-memory SQLite |
| `modes/` | Orchestration | downstream mocked, assert call graph |
| integration | Real-network smoke | `pytest -m integration`, opt-in, not in CI |

Coverage targets: **≥ 80% overall**, **≥ 90% for `metrics/` and `data/`**.

## 9. Non-Goals (v1)

Explicitly out of scope to keep v1 focused:

1. **Spot markets** — USDT-M perpetuals only.
2. **Exchanges other than Binance** — no exchange abstraction layer. Will
   fork/extend later if needed.
3. **Order execution or automated trading** — read-only measurement only.
4. **Web UI / service mode** — no Flask/FastAPI. HTML reports are static files.
5. **ML / prediction / anomaly detection** — rule-based alerts only.
6. **Market-making strategy backtesting** — other tools (vectorbt etc.) can
   read the SQLite directly.

## 10. Milestones

Each milestone is a usable stopping point, not a WIP. REST-only modes land
first; WS is deferred to M4 because book synchronization is the most delicate
part.

| Milestone | Deliverable | Usable outcome |
|---|---|---|
| **M1** | Project scaffold, `infra/`, `data/binance_rest`, `metrics/{spread,depth,obi,slippage}`, minimal `modes/snapshot`, `data/storage` | `bliq snapshot --symbols BTCUSDT` fetches one sample and writes it to SQLite |
| **M2** | `metrics/{taker_ratio,amihud,score}`, `modes/scan`, `reporters/{table,json}`, symbol resolver (`--symbols`/`--top`/`--all`/`--from-file`) | `bliq scan --top 50` prints the ranked table |
| **M3** | `modes/analyze`, `reporters/html` (plotly), `--from-db` replay | `bliq analyze BTCUSDT --html` produces a full report |
| **M4** | `data/binance_ws` (local book + reconnect), `modes/monitor`, `reporters/live_dashboard`, alerts DSL, webhook notifier | `bliq monitor --symbols BTCUSDT,ETHUSDT` runs a live dashboard with alerts |
| **M5** | Docs, coverage fill-in, README examples, CI | v1.0 release |

## 11. Open Questions

None at spec-write time. All design points were resolved during brainstorming
on 2026-04-11.
