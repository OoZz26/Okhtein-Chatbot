"""MessagingGateway adapter over WAHA's REST API."""

import logging
from typing import Any

import httpx

from app.core.privacy import mask_chat_id
from app.domain.errors import MessagingError

logger = logging.getLogger(__name__)


class WahaGateway:
    def __init__(
        self,
        base_url: str,
        api_key: str,
        session: str,
        timeout_seconds: float,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._headers = {"X-Api-Key": api_key}
        self._session = session
        self._timeout = timeout_seconds
        self._transport = transport  # tests inject a fake transport; production leaves it None

    async def send_text(self, chat_id: str, text: str) -> None:
        await self._post("/api/sendText", {"chatId": chat_id, "text": text})
        logger.info("Sent a message to %s", mask_chat_id(chat_id))

    async def mark_seen(self, chat_id: str) -> None:
        await self._post("/api/sendSeen", {"chatId": chat_id})

    async def _post(self, path: str, body: dict[str, Any]) -> None:
        payload = {"session": self._session, **body}
        try:
            async with httpx.AsyncClient(timeout=self._timeout, transport=self._transport) as client:
                response = await client.post(self._base_url + path, json=payload, headers=self._headers)
                response.raise_for_status()
        except httpx.HTTPError as exc:
            raise MessagingError(f"WAHA request to {path} failed: {exc}") from exc
