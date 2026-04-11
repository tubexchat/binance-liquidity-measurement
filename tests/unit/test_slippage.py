import math

from bliq.metrics.slippage import compute_slippage, simulate_market_order
from bliq.metrics.types import OrderBook, OrderBookLevel


def _deep_book() -> OrderBook:
    # Mid ≈ 100. Each ask level has 10 units = 1000 USDT notional.
    asks = tuple(
        OrderBookLevel(100.0 + i * 0.1, 10.0) for i in range(1, 11)
    )
    bids = tuple(
        OrderBookLevel(100.0 - i * 0.1, 10.0) for i in range(1, 11)
    )
    return OrderBook("X", 0, bids, asks)


def test_simulate_buy_consumes_levels_in_order():
    ob = _deep_book()
    avg, filled = simulate_market_order(ob, side="buy", notional_usdt=1500.0)
    # Level 1: 100.1 * 10 = 1001 USDT -> fully consumed (1001)
    # Remaining: 499 USDT at 100.2 -> qty ~4.9800
    # avg = (1001 + 499) / (10 + 499/100.2)
    assert math.isclose(filled, 1500.0, rel_tol=1e-9)
    assert 100.1 < avg < 100.2


def test_simulate_buy_runs_out_of_book():
    ob = _deep_book()
    total_notional = sum(a.price * a.qty for a in ob.asks)
    _avg, filled = simulate_market_order(ob, side="buy", notional_usdt=total_notional * 2)
    assert math.isclose(filled, total_notional, rel_tol=1e-9)


def test_slippage_ladder_populates_both_sides():
    ob = _deep_book()
    r = compute_slippage(ob, levels_usdt=[500, 2000], max_slippage_bps=20.0)
    sides = {(p.side, p.notional_usdt) for p in r.points}
    assert ("buy", 500.0) in sides
    assert ("sell", 500.0) in sides
    assert ("buy", 2000.0) in sides
    assert ("sell", 2000.0) in sides
    # Larger notional => larger or equal slippage.
    buy_points = sorted(
        [p for p in r.points if p.side == "buy"], key=lambda p: p.notional_usdt
    )
    assert buy_points[0].slippage_bps <= buy_points[1].slippage_bps


def test_capacity_finds_boundary():
    ob = _deep_book()
    r = compute_slippage(ob, levels_usdt=[500], max_slippage_bps=10.0)
    # Capacity > 0 and < total book notional on each side.
    assert r.capacity_buy_usdt > 0
    assert r.capacity_sell_usdt > 0
    total_ask = sum(a.price * a.qty for a in ob.asks)
    assert r.capacity_buy_usdt < total_ask


def test_slippage_zero_notional_is_zero():
    ob = _deep_book()
    r = compute_slippage(ob, levels_usdt=[0], max_slippage_bps=20.0)
    for p in r.points:
        assert p.slippage_bps == 0.0
