"""Use case: answer one (already debounced) customer message on WhatsApp."""

import logging

from app.core.privacy import mask_chat_id
from app.domain.errors import OkhteinError
from app.domain.ports import MessagingGateway
from app.services.chat_service import ChatService
from app.services.product_cards import ProductCardFactory
from app.services.reply_sender import ReplySender

logger = logging.getLogger(__name__)


class ReplyService:
    def __init__(
        self,
        chat_service: ChatService,
        gateway: MessagingGateway,
        sender: ReplySender,
        cards: ProductCardFactory,
    ) -> None:
        self._chat = chat_service
        self._gateway = gateway
        self._sender = sender
        self._cards = cards

    async def reply(self, chat_id: str, text: str, sender_name: str = "") -> None:
        """Typing shows while the answer is generated. Expected failures are logged, never raised:
        this runs in a background task where nobody could catch them."""
        try:
            await self._gateway.start_typing(chat_id)
            result = await self._chat.handle_message(chat_id, text, sender_name)
            await self._sender.send(chat_id, result.message, self._cards.build(result.product_handles))
        except OkhteinError:
            logger.exception("Could not answer the message from %s", mask_chat_id(chat_id))
        finally:
            await self._stop_typing(chat_id)

    async def _stop_typing(self, chat_id: str) -> None:
        try:
            await self._gateway.stop_typing(chat_id)
        except OkhteinError:
            logger.warning("Could not clear the typing indicator for %s", mask_chat_id(chat_id))
