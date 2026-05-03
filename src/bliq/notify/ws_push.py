"""Push structured whale signals to a remote WebSocket relay via HTTP POST."""

from __future__ import annotations

import os
from dataclasses import asdict, is_dataclass
from typing import Any

import httpx
from loguru import logger


async def push_signal(signal: Any) -> bool:
    """POST a structured signal to the relay. No-op if env not configured.

    Env:
        SIGNAL_PUSH_URL   e.g. http://api.lewiszhang.top:8080/signal
        SIGNAL_PUSH_TOKEN bearer token expected by the relay
    """
    url = os.environ.get("SIGNAL_PUSH_URL", "")
    token = os.environ.get("SIGNAL_PUSH_TOKEN", "")
    if not url:
        return False

    payload = asdict(signal) if is_dataclass(signal) else dict(signal)

    headers = {"Authorization": f"Bearer {token}"} if token else {}
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.post(url, json=payload, headers=headers)
            if resp.status_code == 200:
                return True
            logger.warning(f"Signal relay error: {resp.status_code} {resp.text}")
            return False
    except httpx.HTTPError as exc:
        logger.warning(f"Signal relay send failed: {exc}")
        return False
