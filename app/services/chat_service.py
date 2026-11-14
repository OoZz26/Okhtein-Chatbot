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
from app.services.handoff_service import HandoffService
from app.services.returning_customer_service import ReturningCustomerService

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
    message: str = ""  # the text WITHOUT product links, for channels that send product cards
    silent: bool = False  # a person owns this chat: the message was stored, nothing should be sent
    handed_off: bool = False  # this very reply handed the chat to a person


class ChatService:
    def __init__(
        self,
        agent: SalesAgent,
        memory: ConversationMemory,
        sessions: SessionStore,
        policy: DiscoveryPolicy,
        follow_ups: FollowUpStore,
        handoffs: HandoffService,
        returning: ReturningCustomerService,
        store_url: str,
    ) -> None:
        self._agent = agent
        self._memory = memory
        self._sessions = sessions
        self._policy = policy
        self._follow_ups = follow_ups
        self._handoffs = handoffs
        self._returning = returning
        self._store_url = store_url.rstrip("/")

    async def is_handed_off(self, chat_id: str) -> bool:
        return await self._handoffs.is_handed_off(chat_id)

    async def handle_message(self, chat_id: str, text: str, sender_name: str = "") -> ChatResult:
        started = time.perf_counter()
        history = await self._memory.context(chat_id)
        state = await self._sessions.load(chat_id)
        returning = await self._returning.context_for(chat_id, new_session=not history)
        await self._memory.record(chat_id, ChatMessage("user", text), sender_name)
        if await self._handoffs.is_handed_off(chat_id):
            logger.info("chat_reply outcome=silent reason=handed_off")
            return ChatResult("", [], [], state.stage, message="", silent=True)
        context = AgentContext(
            sender_name=sender_name,
            stage=state.stage,
            profile_summary=state.profile.summary(),
            guidance=self._policy.guidance(state),
            returning_notes=returning.notes,
            welcome_back=returning.welcome_back,
        )
        try:
            agent_reply = await self._agent.respond(text, history, context)
        except LLMError as exc:
            return await self._degrade(chat_id, state.stage, exc, started)
        new_state = self._policy.update(state, agent_reply)
        await self._sessions.save(chat_id, new_state)
        await self._returning.remember(chat_id, new_state.profile, agent_reply.product_handles)
        links = [self.product_link(handle) for handle in agent_reply.product_handles]
        reply = "\n\n".join([agent_reply.message, *links]) if links else agent_reply.message
        await self._memory.record(chat_id, ChatMessage("assistant", reply))
        handed_off = False
        if agent_reply.wants_handoff:
            handed_off = await self._handoffs.hand_off(
                chat_id, agent_reply.handoff_reason, agent_reply.handoff_summary
            )
        logger.info(
            "chat_reply outcome=ok stage=%s products=%d latency_ms=%d",
            new_state.stage.value,
            len(links),
            self._elapsed_ms(started),
        )
        return ChatResult(
            reply,
            agent_reply.product_handles,
            links,
            new_state.stage,
            message=agent_reply.message,
            handed_off=handed_off,
        )

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
        return ChatResult(HOLDING_MESSAGE, [], [], stage, degraded=True, message=HOLDING_MESSAGE)

    @staticmethod
    def _elapsed_ms(started: float) -> int:
        return int((time.perf_counter() - started) * MS_PER_SECOND)

    def product_link(self, handle: str) -> str:
        return f"{self._store_url}/products/{handle}"
