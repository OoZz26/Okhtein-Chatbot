"""Use case: a WhatsApp message arrived. Filter it, dedupe it, then hand it to the debouncer."""

import logging

from app.core.privacy import mask_chat_id
from app.domain.errors import MessagingError, OkhteinError
from app.domain.models import IncomingMessage
from app.domain.ports import IdempotencyStore, MessagingGateway
from app.services.debouncer import Debouncer
from app.services.handoff_service import HandoffService

logger = logging.getLogger(__name__)

TEXT_ONLY_REPLY = "I can only read text messages for now 🤍 Could you type it for me?"


class IncomingMessageService:
    def __init__(
        self,
        gateway: MessagingGateway,
        idempotency: IdempotencyStore,
        debouncer: Debouncer,
        handoffs: HandoffService,
        allowed_numbers: frozenset[str] = frozenset(),
    ) -> None:
        self._gateway = gateway
        self._idempotency = idempotency
        self._debouncer = debouncer
        self._handoffs = handoffs
        self._allowed_numbers = allowed_numbers

    async def handle(self, message: IncomingMessage) -> None:
        """Never raises for expected failures: it runs in the background, nobody could catch them."""
        reason = self._ignore_reason(message)
        if reason:
            logger.info("Ignored a message (%s)", reason)
            return
        if not await self._idempotency.claim(message.message_id):
            logger.info("Ignored a duplicate delivery of a message")
            return
        try:
            if message.from_me:
                await self._handoffs.staff_took_over(message.chat_id)  # a person is answering: step back
                return
            await self._mark_seen(message.chat_id)
            if message.has_media or not message.text.strip():
                await self._answer_without_reading(message)
            else:
                await self._debouncer.submit(message.chat_id, message.text, message.sender_name)
        except OkhteinError:
            logger.exception("Could not handle the message from %s", mask_chat_id(message.chat_id))

    async def _mark_seen(self, chat_id: str) -> None:
        """Blue ticks are cosmetic: if WAHA fails here, the message must still be answered."""
        try:
            await self._gateway.mark_seen(chat_id)
        except MessagingError as exc:
            logger.warning("Could not mark the chat of %s as seen: %s", mask_chat_id(chat_id), exc)

    async def _answer_without_reading(self, message: IncomingMessage) -> None:
        if not await self._handoffs.is_handed_off(message.chat_id):
            await self._gateway.send_text(message.chat_id, TEXT_ONLY_REPLY)

    def _ignore_reason(self, message: IncomingMessage) -> str | None:
        if message.is_group:
            return "group or channel"
        if message.is_status:
            return "status broadcast"
        if message.from_me and not message.from_phone:
            return "our own message"  # sent through the API by the bot itself
        if self._allowed_numbers and message.chat_id.split("@")[0] not in self._allowed_numbers:
            return "sender not in the allowed list"
        return None
