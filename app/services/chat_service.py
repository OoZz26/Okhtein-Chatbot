"""Use case: turn a customer message into a reply with real product links, remembering the chat."""

import logging
from dataclasses import dataclass

from app.domain.agent.sales_agent import SalesAgent
from app.domain.models import ChatMessage
from app.domain.ports import ConversationMemory

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ChatResult:
    reply: str
    product_handles: list[str]
    links: list[str]


class ChatService:
    def __init__(self, agent: SalesAgent, memory: ConversationMemory, store_url: str) -> None:
        self._agent = agent
        self._memory = memory
        self._store_url = store_url.rstrip("/")

    async def handle_message(self, chat_id: str, text: str, sender_name: str = "") -> ChatResult:
        history = await self._memory.context(chat_id)
        await self._memory.record(chat_id, ChatMessage("user", text), sender_name)
        agent_reply = await self._agent.respond(text, history)
        links = [self.product_link(handle) for handle in agent_reply.product_handles]
        reply = "\n\n".join([agent_reply.message, *links]) if links else agent_reply.message
        await self._memory.record(chat_id, ChatMessage("assistant", reply))
        logger.info("Replied with %d product link(s)", len(links))
        return ChatResult(reply, agent_reply.product_handles, links)

    def product_link(self, handle: str) -> str:
        return f"{self._store_url}/products/{handle}"
