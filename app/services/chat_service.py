"""Use case: turn a customer message into a reply with real product links, remembering the chat."""

import logging
from dataclasses import dataclass

from app.domain.agent.sales_agent import SalesAgent
from app.domain.discovery import DiscoveryPolicy
from app.domain.models import AgentContext, ChatMessage, ConversationStage
from app.domain.ports import ConversationMemory, SessionStore

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ChatResult:
    reply: str
    product_handles: list[str]
    links: list[str]
    stage: ConversationStage


class ChatService:
    def __init__(
        self,
        agent: SalesAgent,
        memory: ConversationMemory,
        sessions: SessionStore,
        policy: DiscoveryPolicy,
        store_url: str,
    ) -> None:
        self._agent = agent
        self._memory = memory
        self._sessions = sessions
        self._policy = policy
        self._store_url = store_url.rstrip("/")

    async def handle_message(self, chat_id: str, text: str, sender_name: str = "") -> ChatResult:
        history = await self._memory.context(chat_id)
        state = await self._sessions.load(chat_id)
        await self._memory.record(chat_id, ChatMessage("user", text), sender_name)
        context = AgentContext(
            sender_name=sender_name,
            stage=state.stage,
            profile_summary=state.profile.summary(),
            guidance=self._policy.guidance(state),
        )
        agent_reply = await self._agent.respond(text, history, context)
        new_state = self._policy.update(state, agent_reply)
        await self._sessions.save(chat_id, new_state)
        links = [self.product_link(handle) for handle in agent_reply.product_handles]
        reply = "\n\n".join([agent_reply.message, *links]) if links else agent_reply.message
        await self._memory.record(chat_id, ChatMessage("assistant", reply))
        logger.info("Replied at stage %s with %d product link(s)", new_state.stage.value, len(links))
        return ChatResult(reply, agent_reply.product_handles, links, new_state.stage)

    def product_link(self, handle: str) -> str:
        return f"{self._store_url}/products/{handle}"
