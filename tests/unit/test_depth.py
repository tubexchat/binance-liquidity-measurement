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
