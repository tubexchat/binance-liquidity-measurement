"""Bid-ask spread metric (relative, in basis points)."""

from __future__ import annotations

from bliq.metrics.types import OrderBook, SpreadMetric


def compute_spread(ob: OrderBook) -> SpreadMetric:
    bid = ob.best_bid
    ask = ob.best_ask
    mid = (bid + ask) / 2.0
    spread_bps = 0.0 if mid <= 0 or ask <= bid else (ask - bid) / mid * 10_000.0
    return SpreadMetric(bid=bid, ask=ask, mid=mid, spread_bps=spread_bps)
