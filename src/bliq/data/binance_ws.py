"""Binance WebSocket client for aggTrades stream.

Connects to the USDT-M futures WebSocket and yields parsed AggTrade events.
Handles reconnection with exponential backoff.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from dataclasses import dataclass

import websockets
from loguru import logger


@dataclass(frozen=True, slots=True)
class AggTrade:
    """A single aggregated trade from Binance."""

    symbol: str
    price: float
    qty: float
    notional: float  # price * qty
    is_buyer_maker: bool  # True = sell (taker sold), False = buy (taker bought)
    ts_ms: int
    trade_id: int

    @property
    def side(self) -> str:
        return "sell" if self.is_buyer_maker else "buy"


def _parse_agg_trade(data: dict) -> AggTrade:
    price = float(data["p"])
    qty = float(data["q"])
    return AggTrade(
        symbol=data["s"],
        price=price,
        qty=qty,
        notional=price * qty,
        is_buyer_maker=data["m"],
        ts_ms=data["T"],
        trade_id=data["a"],
    )


async def stream_agg_trades(
    ws_base: str,
    symbols: list[str],
    *,
    max_reconnect_attempts: int = 10,
    reconnect_backoff_base: float = 1.0,
) -> AsyncIterator[AggTrade]:
    """Stream aggregated trades for one or more symbols.

    Connects to Binance combined stream endpoint. Yields AggTrade objects
    indefinitely. Reconnects automatically on disconnection.
    """
    streams = "/".join(f"{s.lower()}@aggTrade" for s in symbols)
    url = f"{ws_base.rstrip('/')}/stream?streams={streams}"

    attempt = 0
    while attempt < max_reconnect_attempts:
        try:
            async with websockets.connect(url, ping_interval=20) as ws:
                attempt = 0  # reset on successful connect
                logger.info(f"WebSocket connected: {len(symbols)} symbol(s)")
                async for raw in ws:
                    try:
                        msg = json.loads(raw)
                        data = msg.get("data", msg)
                        if data.get("e") == "aggTrade":
                            yield _parse_agg_trade(data)
                    except (json.JSONDecodeError, KeyError, ValueError) as exc:
                        logger.warning(f"malformed aggTrade message: {exc}")
                        continue
        except (
            websockets.ConnectionClosed,
            websockets.InvalidURI,
            OSError,
        ) as exc:
            attempt += 1
            wait = reconnect_backoff_base * (2 ** min(attempt, 6))
            logger.warning(
                f"WebSocket disconnected ({exc}), reconnecting in {wait:.1f}s "
                f"(attempt {attempt}/{max_reconnect_attempts})"
            )
            await asyncio.sleep(wait)

    logger.error("WebSocket max reconnect attempts reached, stopping")
