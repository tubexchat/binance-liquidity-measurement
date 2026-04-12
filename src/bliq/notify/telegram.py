"""Telegram bot notification for whale alerts."""

from __future__ import annotations

import os

import httpx
from loguru import logger


def _get_config() -> tuple[str, str]:
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")
    if not token or not chat_id:
        raise RuntimeError(
            "TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID must be set in environment"
        )
    return token, chat_id


async def send_telegram(text: str) -> bool:
    """Send a message via Telegram Bot API. Returns True on success."""
    token, chat_id = _get_config()
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "Markdown",
        "disable_web_page_preview": True,
    }
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(url, json=payload)
            if resp.status_code == 200:
                logger.debug(f"Telegram message sent ({len(text)} chars)")
                return True
            logger.warning(f"Telegram API error: {resp.status_code} {resp.text}")
            return False
    except httpx.HTTPError as exc:
        logger.warning(f"Telegram send failed: {exc}")
        return False
