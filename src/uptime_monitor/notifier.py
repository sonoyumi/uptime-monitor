"""Sending alerts. Telegram is the default; the Notifier protocol lets you add e-mail or Slack."""

from __future__ import annotations

import logging
from typing import Protocol

import httpx

logger = logging.getLogger(__name__)


class Notifier(Protocol):
    async def send(self, text: str) -> bool: ...


class TelegramNotifier:
    def __init__(self, client: httpx.AsyncClient, token: str, chat_id: str) -> None:
        self._client = client
        self._url = f"https://api.telegram.org/bot{token}/sendMessage"
        self._chat_id = chat_id

    async def send(self, text: str) -> bool:
        try:
            response = await self._client.post(
                self._url,
                json={"chat_id": self._chat_id, "text": text, "parse_mode": "HTML", "disable_web_page_preview": True},
                timeout=15,
            )
        except httpx.HTTPError as exc:
            logger.warning("Telegram alert not sent: %s", type(exc).__name__)  # never log the URL: it has the token
            return False
        if response.status_code != 200:
            logger.warning("Telegram alert rejected: HTTP %s %s", response.status_code, response.text[:200])
            return False
        return True


class LogNotifier:
    """When no Telegram token is configured: alerts go to the log."""

    async def send(self, text: str) -> bool:
        logger.warning("ALERT: %s", text.replace("\n", " | "))
        return True
