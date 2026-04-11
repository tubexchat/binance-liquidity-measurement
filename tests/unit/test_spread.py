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
