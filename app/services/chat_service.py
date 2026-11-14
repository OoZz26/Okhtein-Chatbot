"""Use case: turn a customer message into a reply with real product links."""

import logging
from dataclasses import dataclass

from app.domain.agent.sales_agent import SalesAgent

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ChatResult:
    reply: str
    product_handles: list[str]
    links: list[str]


class ChatService:
    def __init__(self, agent: SalesAgent, store_url: str) -> None:
        self._agent = agent
        self._store_url = store_url.rstrip("/")

    async def handle_message(self, chat_id: str, text: str) -> ChatResult:
        # chat_id is unused until conversation memory (issue 004); the service is stateless for now.
        agent_reply = await self._agent.respond(text)
        links = [self.product_link(handle) for handle in agent_reply.product_handles]
        reply = "\n\n".join([agent_reply.message, *links]) if links else agent_reply.message
        logger.info("Replied with %d product link(s)", len(links))
        return ChatResult(reply, agent_reply.product_handles, links)

    def product_link(self, handle: str) -> str:
        return f"{self._store_url}/products/{handle}"
