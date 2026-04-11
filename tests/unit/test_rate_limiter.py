import asyncio
import time

from bliq.data.rate_limiter import WeightRateLimiter


async def test_acquire_under_budget_is_nonblocking():
    rl = WeightRateLimiter(capacity_per_minute=100)
    start = time.monotonic()
    await rl.acquire(10)
    await rl.acquire(20)
    elapsed = time.monotonic() - start
    assert elapsed < 0.05


async def test_acquire_over_budget_waits_until_window_reset():
    rl = WeightRateLimiter(capacity_per_minute=100, _now=lambda: 0.0)
    # Fast-forward time manually via _now injection.
    now = [0.0]
    rl._now = lambda: now[0]

    await rl.acquire(60)
    await rl.acquire(30)
    # We've used 90 in the window starting at 0.
    # Requesting 20 should need to wait until the window rolls over at 60s.
    wait_coro = rl.acquire(20)

    async def advance():
        # Pump time forward to simulate the window rolling over.
        await asyncio.sleep(0)
        now[0] = 61.0
        await rl._tick()

    await asyncio.gather(wait_coro, advance())
    # After acquire completes, used should reflect only the new request.
    assert rl.used == 20


async def test_reconcile_with_server_header_resets_counter():
    rl = WeightRateLimiter(capacity_per_minute=2400)
    await rl.acquire(10)
    rl.reconcile(used_weight_1m=1500)
    assert rl.used == 1500
