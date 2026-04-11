"""Async Binance USDT-M Futures REST client.

Wraps the subset of ``/fapi/v1`` endpoints needed by M1 (depth). Future
milestones will add klines, aggTrades, ticker, and exchangeInfo.
"""

from __future__ import annotations

import asyncio
import contextlib
from typing import Any

import httpx

from bliq.data.rate_limiter import WeightRateLimiter
from bliq.infra.errors import BinanceAPIError, RateLimitError, SymbolNotFoundError
from bliq.metrics.types import OrderBook, OrderBookLevel

ENDPOINT_WEIGHTS = {
    "/fapi/v1/depth": 2,  # limit <= 50 costs 2; we stay within that.
}


class BinanceRestClient:
    def __init__(
        self,
        *,
        base_url: str,
        rate_limiter: WeightRateLimiter,
        retry_attempts: int = 3,
        retry_backoff_base: float = 1.0,
        timeout: float = 10.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.rate_limiter = rate_limiter
        self.retry_attempts = retry_attempts
        self.retry_backoff_base = retry_backoff_base
        self.timeout = timeout
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> BinanceRestClient:
        self._client = httpx.AsyncClient(timeout=self.timeout)
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def _get(
        self, path: str, params: dict[str, Any] | None = None
    ) -> httpx.Response:
        if self._client is None:
            raise RuntimeError("BinanceRestClient used outside its async context")
        weight = ENDPOINT_WEIGHTS.get(path, 1)
        url = f"{self.base_url}{path}"
        last_exc: Exception | None = None
        for attempt in range(self.retry_attempts):
            await self.rate_limiter.acquire(weight)
            try:
                resp = await self._client.get(url, params=params)
            except httpx.HTTPError as exc:
                last_exc = exc
                await asyncio.sleep(self.retry_backoff_base * (2**attempt))
                continue

            header = resp.headers.get("X-MBX-USED-WEIGHT-1M")
            if header is not None:
                with contextlib.suppress(ValueError):
                    self.rate_limiter.reconcile(int(header))

            if resp.status_code == 429 or resp.status_code == 418:
                if attempt < self.retry_attempts - 1:
                    retry_after = float(resp.headers.get("Retry-After", "1"))
                    await asyncio.sleep(retry_after)
                    continue
                raise RateLimitError(f"rate limited: {resp.status_code}")
            if 500 <= resp.status_code < 600:
                last_exc = BinanceAPIError(f"server error {resp.status_code}")
                await asyncio.sleep(self.retry_backoff_base * (2**attempt))
                continue
            if resp.status_code >= 400:
                try:
                    body = resp.json()
                    msg = body.get("msg", "")
                    code = body.get("code", 0)
                except (ValueError, KeyError):
                    msg, code = resp.text, 0
                if code == -1121:
                    raise SymbolNotFoundError(msg)
                raise BinanceAPIError(f"{resp.status_code}: {msg}")
            return resp
        raise BinanceAPIError(f"request to {path} failed: {last_exc}")

    async def fetch_depth(self, symbol: str, *, limit: int = 20) -> OrderBook:
        resp = await self._get(
            "/fapi/v1/depth", params={"symbol": symbol, "limit": limit}
        )
        body = resp.json()
        bids = tuple(
            OrderBookLevel(float(p), float(q)) for p, q in body.get("bids", [])
        )
        asks = tuple(
            OrderBookLevel(float(p), float(q)) for p, q in body.get("asks", [])
        )
        ts_ms = int(body.get("E") or body.get("T") or 0)
        return OrderBook(symbol=symbol, ts_ms=ts_ms, bids=bids, asks=asks)
