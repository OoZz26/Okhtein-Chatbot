"""Debounce + per-chat lock: a burst of messages becomes ONE reply, and replies never overlap.

Producer/consumer: the webhook produces (`submit`), a short-lived task per message consumes.
"""

import asyncio
import logging
from collections.abc import Awaitable, Callable

from app.core.privacy import mask_chat_id
from app.domain.ports import ChatLock, MessageBuffer

logger = logging.getLogger(__name__)

Process = Callable[[str, str, str], Awaitable[None]]  # (chat_id, combined_text, sender_name)
Sleep = Callable[[float], Awaitable[None]]

LOCK_POLL_SECONDS = 0.2


class Debouncer:
    def __init__(
        self,
        buffer: MessageBuffer,
        lock: ChatLock,
        process: Process,
        quiet_seconds: float,
        lock_wait_seconds: float,
        sleep: Sleep = asyncio.sleep,
        renew_every_seconds: float | None = None,
    ) -> None:
        """`renew_every_seconds`: how often the lock's TTL is reset while a reply is being made, so
        a slow reply (LLM retries, fallback, rate-limit waits) never outlives its lock. None = never."""
        self._buffer = buffer
        self._lock = lock
        self._process = process
        self._quiet_seconds = quiet_seconds
        self._lock_wait_seconds = lock_wait_seconds
        self._sleep = sleep
        self._renew_every = renew_every_seconds
        self._names: dict[str, str] = {}
        self._tasks: set[asyncio.Task[None]] = set()

    async def submit(self, chat_id: str, text: str, sender_name: str = "") -> None:
        """Buffer the message and return immediately; a background task replies after the quiet period."""
        self._names[chat_id] = sender_name or self._names.get(chat_id, "")
        sequence = await self._buffer.push(chat_id, text)
        self._schedule(chat_id, sequence)

    def _schedule(self, chat_id: str, sequence: int) -> None:
        task = asyncio.create_task(self._consume(chat_id, sequence))
        self._tasks.add(task)  # keep a reference, or the task could be garbage collected mid-flight
        task.add_done_callback(self._tasks.discard)

    async def wait_idle(self) -> None:
        """Wait for every scheduled reply to finish (used by tests and by graceful shutdown)."""
        while self._tasks:
            await asyncio.gather(*list(self._tasks), return_exceptions=True)

    async def _consume(self, chat_id: str, sequence: int) -> None:
        await self._sleep(self._quiet_seconds)
        if await self._buffer.latest_sequence(chat_id) != sequence:
            return  # a newer message arrived: its own task will answer for the whole burst
        token = await self._acquire_lock(chat_id)
        if token is None:
            logger.error("Gave up waiting for the chat lock of %s", mask_chat_id(chat_id))
            return
        renewal = self._start_renewal(chat_id, token)
        try:
            texts = await self._buffer.drain(chat_id)
            if texts:  # empty when a previous task already answered this burst
                await self._process(chat_id, "\n".join(texts), self._names.pop(chat_id, ""))
        finally:
            if renewal is not None:
                renewal.cancel()
            await self._lock.release(chat_id, token)
        await self._pick_up_messages_sent_meanwhile(chat_id, sequence)

    async def _pick_up_messages_sent_meanwhile(self, chat_id: str, sequence: int) -> None:
        """Messages that arrived while we were replying have their own task, but it may have given
        up waiting for our lock. Schedule one more pass; if that burst was already answered, the
        pass finds an empty buffer and does nothing."""
        latest = await self._buffer.latest_sequence(chat_id)
        if latest != sequence:
            self._schedule(chat_id, latest)

    def _start_renewal(self, chat_id: str, token: str) -> asyncio.Task[None] | None:
        if self._renew_every is None:
            return None
        return asyncio.create_task(self._keep_lock(chat_id, token, self._renew_every))

    async def _keep_lock(self, chat_id: str, token: str, every: float) -> None:
        while True:
            await self._sleep(every)
            if not await self._lock.extend(chat_id, token):
                logger.warning("Lost the chat lock of %s while replying", mask_chat_id(chat_id))
                return

    async def _acquire_lock(self, chat_id: str) -> str | None:
        waited = 0.0
        while True:
            token = await self._lock.acquire(chat_id)
            if token is not None or waited >= self._lock_wait_seconds:
                return token
            await self._sleep(LOCK_POLL_SECONDS)
            waited += LOCK_POLL_SECONDS
