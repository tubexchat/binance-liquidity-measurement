"""Token-bucket-style rate limiter for Binance weight quotas.

Binance USDT-M Futures is capped at ``rate_limit_weight_per_min`` weight per
IP per rolling minute. This limiter keeps a local counter, reconciles it
against ``X-MBX-USED-WEIGHT-1M`` response headers, and blocks callers when
the budget is exhausted until the current 60-second window rolls over.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable


class WeightRateLimiter:
    def __init__(
        self,
        capacity_per_minute: int,
        *,
        _now: Callable[[], float] | None = None,
    ) -> None:
        self.capacity = capacity_per_minute
        self._now = _now or time.monotonic
        self._window_start = self._now()
        self._used = 0
        self._lock = asyncio.Lock()
        self._cond = asyncio.Condition(self._lock)

    @property
    def used(self) -> int:
        return self._used

    async def _tick(self) -> None:
        """Roll the window forward if >=60s have elapsed, and wake waiters."""
        async with self._cond:
            if self._now() - self._window_start >= 60.0:
                self._window_start = self._now()
                self._used = 0
                self._cond.notify_all()

    async def acquire(self, weight: int) -> None:
        async with self._cond:
            while True:
                if self._now() - self._window_start >= 60.0:
                    self._window_start = self._now()
                    self._used = 0
                if self._used + weight <= self.capacity:
                    self._used += weight
                    return
                # Wait until the window advances. Use wait_for with a small
                # timeout so external _now injection can advance time.
                try:
                    await asyncio.wait_for(self._cond.wait(), timeout=0.05)
                except TimeoutError:
                    continue

    def reconcile(self, used_weight_1m: int) -> None:
        """Update the local counter from a server-reported value."""
        self._used = int(used_weight_1m)
