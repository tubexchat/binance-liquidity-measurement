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
