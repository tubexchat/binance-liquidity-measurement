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
