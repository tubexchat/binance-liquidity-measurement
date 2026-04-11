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
