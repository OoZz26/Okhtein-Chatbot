"""Use case: moving a chat between the bot and a person."""

import logging
from collections.abc import Callable
from datetime import datetime, timedelta

from app.core.clock import utc_now
from app.core.privacy import mask_chat_id
from app.domain.ports import HandoffStore, StaffNotifier

logger = logging.getLogger(__name__)

STAFF_REPLY_REASON = "A team member replied from the business phone"


class HandoffService:
    def __init__(
        self,
        store: HandoffStore,
        notifier: StaffNotifier,
        timeout_hours: float,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        self._store = store
        self._notifier = notifier
        self._timeout = timedelta(hours=timeout_hours)
        self._clock = clock

    async def is_handed_off(self, chat_id: str) -> bool:
        """True while a person owns the chat. A handoff that outlived its timeout is released here."""
        state = await self._store.get(chat_id)
        if not state.is_handed_off:
            return False
        if state.since is not None and self._clock() - state.since >= self._timeout:
            await self._store.save(chat_id, state.release())
            logger.info("Handoff of %s expired; the bot answers again", mask_chat_id(chat_id))
            return False
        return True

    async def hand_off(self, chat_id: str, reason: str, summary: str) -> bool:
        """Hand the chat to a person and tell the team. Returns False if it was already handed off."""
        state = await self._store.get(chat_id)
        if state.is_handed_off:
            return False
        new_state = state.handoff(reason, summary, self._clock())
        await self._store.save(chat_id, new_state)
        logger.warning("handoff chat=%s reason=%s", mask_chat_id(chat_id), reason)
        await self._notifier.notify(chat_id, new_state)
        return True

    async def staff_took_over(self, chat_id: str) -> None:
        """A person wrote in the chat from the business phone: the bot must stop. No notification needed.
        Every staff message restarts the timeout, so the bot never jumps into a live human conversation."""
        state = await self._store.get(chat_id)
        if state.is_handed_off:
            await self._store.save(chat_id, state.refreshed(self._clock()))
            return
        await self._store.save(chat_id, state.handoff(STAFF_REPLY_REASON, "", self._clock()))
        logger.warning("handoff chat=%s reason=%s", mask_chat_id(chat_id), STAFF_REPLY_REASON)

    async def release(self, chat_id: str) -> bool:
        """Give the chat back to the bot. Returns False if it was not handed off."""
        state = await self._store.get(chat_id)
        if not state.is_handed_off:
            return False
        await self._store.save(chat_id, state.release())
        logger.info("Released %s back to the bot", mask_chat_id(chat_id))
        return True
