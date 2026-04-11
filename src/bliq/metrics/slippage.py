"""Market-order slippage simulation and capacity estimation."""

from __future__ import annotations

from bliq.metrics.types import OrderBook, SlippageMetric, SlippagePoint


def simulate_market_order(
    ob: OrderBook, *, side: str, notional_usdt: float
) -> tuple[float, float]:
    """Walk the book on the given side until `notional_usdt` is filled.

    Returns ``(avg_fill_price, filled_notional)``. If the book is exhausted
    before the requested notional is met, ``filled_notional`` is the actual
    amount consumed.
    """
    if notional_usdt <= 0:
        mid = ob.mid
        return mid, 0.0

    levels = ob.asks if side == "buy" else ob.bids
    remaining = notional_usdt
    filled_notional = 0.0
    filled_qty = 0.0
    for lvl in levels:
        if remaining <= 0 or lvl.qty <= 0:
            continue
        level_notional = lvl.price * lvl.qty
        if level_notional >= remaining:
            qty_taken = remaining / lvl.price
            filled_notional += remaining
            filled_qty += qty_taken
            remaining = 0
            break
        filled_notional += level_notional
        filled_qty += lvl.qty
        remaining -= level_notional

    if filled_qty == 0:
        return ob.mid, 0.0
    return filled_notional / filled_qty, filled_notional


def _slippage_bps(avg_px: float, mid: float, side: str) -> float:
    if mid <= 0 or avg_px <= 0:
        return 0.0
    if side == "buy":
        return (avg_px - mid) / mid * 10_000.0
    return (mid - avg_px) / mid * 10_000.0


def _capacity_at(ob: OrderBook, *, side: str, max_bps: float) -> float:
    """Largest notional that keeps slippage <= max_bps.

    Implementation: walk the book level by level, accumulating notional. After
    each level, compute the slippage at the cumulative fill. Stop at the first
    level where slippage exceeds the cap and interpolate the exact boundary
    within that level.
    """
    mid = ob.mid
    if mid <= 0:
        return 0.0
    levels = ob.asks if side == "buy" else ob.bids

    cum_notional = 0.0
    cum_qty = 0.0
    for lvl in levels:
        if lvl.qty <= 0:
            continue
        level_notional = lvl.price * lvl.qty
        new_notional = cum_notional + level_notional
        new_qty = cum_qty + lvl.qty
        new_avg = new_notional / new_qty
        new_bps = _slippage_bps(new_avg, mid, side)
        if new_bps <= max_bps:
            cum_notional = new_notional
            cum_qty = new_qty
            continue
        # Binary search within this level for the max qty that keeps slippage <= cap.
        lo, hi = 0.0, lvl.qty
        for _ in range(40):
            m = (lo + hi) / 2.0
            trial_notional = cum_notional + lvl.price * m
            trial_qty = cum_qty + m
            if trial_qty == 0:
                lo = m
                continue
            trial_avg = trial_notional / trial_qty
            trial_bps = _slippage_bps(trial_avg, mid, side)
            if trial_bps <= max_bps:
                lo = m
            else:
                hi = m
        cum_notional += lvl.price * lo
        cum_qty += lo
        break
    return cum_notional


def compute_slippage(
    ob: OrderBook, *, levels_usdt: list[float], max_slippage_bps: float
) -> SlippageMetric:
    mid = ob.mid
    points: list[SlippagePoint] = []
    for notional in levels_usdt:
        for side in ("buy", "sell"):
            avg, _filled = simulate_market_order(ob, side=side, notional_usdt=notional)
            bps = _slippage_bps(avg, mid, side) if notional > 0 else 0.0
            points.append(
                SlippagePoint(
                    side=side,
                    notional_usdt=float(notional),
                    slippage_bps=bps,
                    avg_fill_px=avg,
                )
            )
    cap_buy = _capacity_at(ob, side="buy", max_bps=max_slippage_bps)
    cap_sell = _capacity_at(ob, side="sell", max_bps=max_slippage_bps)
    return SlippageMetric(
        points=tuple(points),
        capacity_buy_usdt=cap_buy,
        capacity_sell_usdt=cap_sell,
        max_slippage_bps=max_slippage_bps,
    )
