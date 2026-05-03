"""HTTP API for querying stored contrarian signals (for backtesting)."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

from fastapi import Depends, FastAPI, Header, HTTPException, Query

from bliq.notify.signal_store import SignalStore


def _verify_token(authorization: str | None = Header(default=None)) -> None:
    expected = os.environ.get("BLIQ_API_TOKEN", "")
    if not expected:
        return
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="missing bearer token")
    if authorization.removeprefix("Bearer ").strip() != expected:
        raise HTTPException(status_code=401, detail="invalid bearer token")


def create_app(db_path: Path | str) -> FastAPI:
    store = SignalStore(db_path)
    store.init_schema()

    app = FastAPI(title="bliq signals API", version="0.1.0")
    auth = [Depends(_verify_token)]

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/signals", dependencies=auth)
    def list_signals(
        symbol: str | None = None,
        direction: Literal["LONG", "SHORT"] | None = None,
        pushed: bool | None = None,
        skip_reason: str | None = None,
        start_ms: int | None = Query(default=None, ge=0),
        end_ms: int | None = Query(default=None, ge=0),
        limit: int = Query(default=100, ge=1, le=1000),
        offset: int = Query(default=0, ge=0),
    ) -> dict:
        items, total = store.list_signals(
            symbol=symbol,
            direction=direction,
            pushed=pushed,
            skip_reason=skip_reason,
            start_ms=start_ms,
            end_ms=end_ms,
            limit=limit,
            offset=offset,
        )
        return {"items": items, "total": total, "limit": limit, "offset": offset}

    @app.get("/signals/latest", dependencies=auth)
    def latest(
        symbol: str | None = None,
        limit: int = Query(default=200, ge=1, le=1000),
    ) -> dict:
        return {"items": store.latest_per_symbol(symbol=symbol, limit=limit)}

    @app.get("/signals/stats/overview", dependencies=auth)
    def overview(
        start_ms: int | None = Query(default=None, ge=0),
        end_ms: int | None = Query(default=None, ge=0),
    ) -> dict:
        return store.overview_stats(start_ms=start_ms, end_ms=end_ms)

    @app.get("/signals/stats/buckets", dependencies=auth)
    def buckets(
        bucket: Literal["hour", "day"] = "hour",
        start_ms: int | None = Query(default=None, ge=0),
        end_ms: int | None = Query(default=None, ge=0),
    ) -> dict:
        return {
            "bucket": bucket,
            "items": store.bucketed_counts(bucket=bucket, start_ms=start_ms, end_ms=end_ms),
        }

    @app.get("/signals/stats/by-symbol", dependencies=auth)
    def by_symbol(
        start_ms: int | None = Query(default=None, ge=0),
        end_ms: int | None = Query(default=None, ge=0),
        limit: int = Query(default=100, ge=1, le=1000),
    ) -> dict:
        return {
            "items": store.by_symbol_stats(start_ms=start_ms, end_ms=end_ms, limit=limit)
        }

    return app
