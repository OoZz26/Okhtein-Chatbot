"""Sends a reply the way a person would: typing pause, a few bubbles, then product cards."""

import asyncio
import logging
from collections.abc import Awaitable, Callable

from app.core.privacy import mask_chat_id
from app.domain.bubbles import split_into_bubbles
from app.domain.errors import MessagingError
from app.domain.models import ProductCard
from app.domain.ports import MessagingGateway, RateLimiter

logger = logging.getLogger(__name__)

Sleep = Callable[[float], Awaitable[None]]


class ReplySender:
    def __init__(
        self,
        gateway: MessagingGateway,
        limiter: RateLimiter,
        max_bubbles: int,
        seconds_per_char: float,
        max_typing_delay_seconds: float,
        sleep: Sleep = asyncio.sleep,
    ) -> None:
        self._gateway = gateway
        self._limiter = limiter
        self._max_bubbles = max_bubbles
        self._seconds_per_char = seconds_per_char
        self._max_typing_delay = max_typing_delay_seconds
        self._sleep = sleep

    async def send(self, chat_id: str, text: str, cards: list[ProductCard]) -> None:
        for bubble in split_into_bubbles(text, self._max_bubbles):
            await self._typing_pause(chat_id, bubble)
            await self._send_text(chat_id, bubble)
        for card in cards:
            await self._send_card(chat_id, card)

    async def _typing_pause(self, chat_id: str, bubble: str) -> None:
        """Proportional to the length, capped: a long message 'takes longer to type'."""
        await self._gateway.start_typing(chat_id)
        await self._sleep(min(len(bubble) * self._seconds_per_char, self._max_typing_delay))

    async def _send_text(self, chat_id: str, text: str) -> None:
        await self._wait_for_rate_limit()
        await self._gateway.send_text(chat_id, text)

    async def _send_card(self, chat_id: str, card: ProductCard) -> None:
        """An image with a caption; if the image cannot be sent, the same information goes as text."""
        await self._wait_for_rate_limit()
        try:
            await self._gateway.send_image(chat_id, card.image_url, card.caption)
        except MessagingError as exc:
            logger.warning("Image failed for %s, sending a text link: %s", mask_chat_id(chat_id), exc)
            await self._send_text(chat_id, card.caption)

    async def _wait_for_rate_limit(self) -> None:
        while (wait := await self._limiter.seconds_until_allowed()) > 0:
            logger.info("Outgoing rate limit reached; waiting %.1fs", wait)
            await self._sleep(wait)
