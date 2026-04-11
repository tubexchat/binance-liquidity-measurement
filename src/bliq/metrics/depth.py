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


_EPS = 1e-9  # tolerance for floating-point boundary comparisons


def compute_depth(ob: OrderBook, pcts: list[float]) -> DepthMetric:
    mid = ob.mid
    result: dict[float, tuple[float, float]] = {}
    for pct in pcts:
        lower = mid * (1 - pct) - _EPS
        upper = mid * (1 + pct) + _EPS
        bid_usdt = _notional_within(ob.bids, lower, mid + _EPS)
        ask_usdt = _notional_within(ob.asks, mid - _EPS, upper)
        result[pct] = (bid_usdt, ask_usdt)
    return DepthMetric(by_pct=result)
