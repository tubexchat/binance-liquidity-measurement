import json
from pathlib import Path

import pytest
from pytest_httpx import HTTPXMock

from bliq.data.binance_rest import BinanceRestClient
from bliq.data.rate_limiter import WeightRateLimiter
from bliq.infra.errors import BinanceAPIError, RateLimitError

BASE = "https://fapi.binance.com"


@pytest.fixture
def client() -> BinanceRestClient:
    return BinanceRestClient(
        base_url=BASE,
        rate_limiter=WeightRateLimiter(capacity_per_minute=2400),
        retry_attempts=3,
        retry_backoff_base=0.0,
    )


async def test_fetch_depth_parses_levels(
    client: BinanceRestClient, fixtures_dir: Path, httpx_mock: HTTPXMock
):
    payload = json.loads((fixtures_dir / "orderbook_btcusdt.json").read_text())
    httpx_mock.add_response(
        url=f"{BASE}/fapi/v1/depth?symbol=BTCUSDT&limit=20",
        json=payload,
        headers={"X-MBX-USED-WEIGHT-1M": "12"},
    )

    async with client:
        ob = await client.fetch_depth("BTCUSDT", limit=20)

    assert ob.symbol == "BTCUSDT"
    assert ob.best_bid == 65000.0
    assert ob.best_ask == 65001.0
    assert len(ob.bids) == 5
    assert len(ob.asks) == 5


async def test_retries_on_5xx_then_succeeds(
    client: BinanceRestClient, fixtures_dir: Path, httpx_mock: HTTPXMock
):
    payload = json.loads((fixtures_dir / "orderbook_btcusdt.json").read_text())
    url = f"{BASE}/fapi/v1/depth?symbol=BTCUSDT&limit=20"
    httpx_mock.add_response(url=url, status_code=502)
    httpx_mock.add_response(url=url, status_code=503)
    httpx_mock.add_response(url=url, json=payload)

    async with client:
        ob = await client.fetch_depth("BTCUSDT", limit=20)
    assert ob.best_bid == 65000.0


async def test_429_raises_rate_limit_error(
    client: BinanceRestClient, httpx_mock: HTTPXMock
):
    url = f"{BASE}/fapi/v1/depth?symbol=BTCUSDT&limit=20"
    httpx_mock.add_response(url=url, status_code=429)
    httpx_mock.add_response(url=url, status_code=429)
    httpx_mock.add_response(url=url, status_code=429)
    async with client:
        with pytest.raises(RateLimitError):
            await client.fetch_depth("BTCUSDT", limit=20)


async def test_4xx_other_raises_api_error(
    client: BinanceRestClient, httpx_mock: HTTPXMock
):
    url = f"{BASE}/fapi/v1/depth?symbol=FOOUSDT&limit=20"
    httpx_mock.add_response(
        url=url, status_code=400, json={"code": -1121, "msg": "Invalid symbol."}
    )
    async with client:
        with pytest.raises(BinanceAPIError):
            await client.fetch_depth("FOOUSDT", limit=20)


async def test_reconciles_weight_header(
    client: BinanceRestClient, fixtures_dir: Path, httpx_mock: HTTPXMock
):
    payload = json.loads((fixtures_dir / "orderbook_btcusdt.json").read_text())
    httpx_mock.add_response(
        url=f"{BASE}/fapi/v1/depth?symbol=BTCUSDT&limit=20",
        json=payload,
        headers={"X-MBX-USED-WEIGHT-1M": "987"},
    )
    async with client:
        await client.fetch_depth("BTCUSDT", limit=20)
    assert client.rate_limiter.used == 987
