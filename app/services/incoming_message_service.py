"""Use case: handle one incoming WhatsApp message end to end (filter, dedupe, reply)."""

import logging

from app.core.privacy import mask_chat_id
from app.domain.errors import OkhteinError
from app.domain.models import IncomingMessage
from app.domain.ports import IdempotencyStore, MessagingGateway
from app.services.chat_service import ChatService

logger = logging.getLogger(__name__)

TEXT_ONLY_REPLY = (
    "I can only read text messages for now 🤍 Could you type it for me?\n"
    "أقدر أقرأ الرسائل النصية بس دلوقتي، ممكن تكتبهالي؟"
)


class IncomingMessageService:
    def __init__(
        self,
        chat_service: ChatService,
        gateway: MessagingGateway,
        idempotency: IdempotencyStore,
        allowed_numbers: frozenset[str] = frozenset(),
    ) -> None:
        self._chat = chat_service
        self._gateway = gateway
        self._idempotency = idempotency
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
            await self._gateway.mark_seen(message.chat_id)
            await self._gateway.send_text(message.chat_id, await self._reply_text(message))
        except OkhteinError:
            logger.exception("Could not answer the message from %s", mask_chat_id(message.chat_id))

    def _ignore_reason(self, message: IncomingMessage) -> str | None:
        if message.from_me:
            return "our own message"
        if message.is_group:
            return "group or channel"
        if message.is_status:
            return "status broadcast"
        if self._allowed_numbers and message.chat_id.split("@")[0] not in self._allowed_numbers:
            return "sender not in the allowed list"
        return None

    async def _reply_text(self, message: IncomingMessage) -> str:
        if message.has_media or not message.text.strip():
            return TEXT_ONLY_REPLY
        result = await self._chat.handle_message(message.chat_id, message.text)
        return result.reply
