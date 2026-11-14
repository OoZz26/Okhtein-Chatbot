"""Use case: turn a customer message into a reply with real product links, remembering the chat."""

import logging
import time
from dataclasses import dataclass

from app.core.privacy import mask_chat_id
from app.domain.agent.sales_agent import SalesAgent
from app.domain.discovery import DiscoveryPolicy
from app.domain.errors import LLMError
from app.domain.models import AgentContext, ChatMessage, ConversationStage
from app.domain.ports import ConversationMemory, FollowUpStore, SessionStore

logger = logging.getLogger(__name__)

MS_PER_SECOND = 1000
HOLDING_MESSAGE = (
    "Thank you for your message 🤍 I need a moment, and I'll get back to you very soon.\n"
    "شكراً لرسالة حضرتك 🤍 محتاجة لحظة وهرد على حضرتك في أقرب وقت."
)
FOLLOW_UP_REASON = "assistant unavailable: every LLM provider failed"


@dataclass(frozen=True)
class ChatResult:
    reply: str
    product_handles: list[str]
    links: list[str]
    stage: ConversationStage
    degraded: bool = False


class ChatService:
    def __init__(
        self,
        agent: SalesAgent,
        memory: ConversationMemory,
        sessions: SessionStore,
        policy: DiscoveryPolicy,
        follow_ups: FollowUpStore,
        store_url: str,
    ) -> None:
        self._agent = agent
        self._memory = memory
        self._sessions = sessions
        self._policy = policy
        self._follow_ups = follow_ups
        self._store_url = store_url.rstrip("/")

    async def handle_message(self, chat_id: str, text: str, sender_name: str = "") -> ChatResult:
        started = time.perf_counter()
        history = await self._memory.context(chat_id)
        state = await self._sessions.load(chat_id)
        await self._memory.record(chat_id, ChatMessage("user", text), sender_name)
        context = AgentContext(
            sender_name=sender_name,
            stage=state.stage,
            profile_summary=state.profile.summary(),
            guidance=self._policy.guidance(state),
        )
        try:
            agent_reply = await self._agent.respond(text, history, context)
        except LLMError as exc:
            return await self._degrade(chat_id, state.stage, exc, started)
        new_state = self._policy.update(state, agent_reply)
        await self._sessions.save(chat_id, new_state)
        links = [self.product_link(handle) for handle in agent_reply.product_handles]
        reply = "\n\n".join([agent_reply.message, *links]) if links else agent_reply.message
        await self._memory.record(chat_id, ChatMessage("assistant", reply))
        logger.info(
            "chat_reply outcome=ok stage=%s products=%d latency_ms=%d",
            new_state.stage.value,
            len(links),
            self._elapsed_ms(started),
        )
        return ChatResult(reply, agent_reply.product_handles, links, new_state.stage)

    async def _degrade(
        self, chat_id: str, stage: ConversationStage, error: LLMError, started: float
    ) -> ChatResult:
        """The assistant could not answer: never show an error or go silent. Hold, flag, and log."""
        logger.error(
            "chat_reply outcome=degraded chat=%s latency_ms=%d error=%s",
            mask_chat_id(chat_id),
            self._elapsed_ms(started),
            error,
        )
        await self._follow_ups.flag(chat_id, FOLLOW_UP_REASON)
        return ChatResult(HOLDING_MESSAGE, [], [], stage, degraded=True)

    @staticmethod
    def _elapsed_ms(started: float) -> int:
        return int((time.perf_counter() - started) * MS_PER_SECOND)

    def product_link(self, handle: str) -> str:
        return f"{self._store_url}/products/{handle}"
