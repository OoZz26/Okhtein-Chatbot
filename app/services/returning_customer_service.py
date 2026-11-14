"""Use case: remember people between visits.

Every turn, what was learned goes into the long-term profile (cheap, no LLM, so a Redis flush loses
nothing). When a NEW session starts, the previous one is summarised by the LLM and the agent is told to
welcome the customer back.
"""

import logging
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime

from app.core.privacy import mask_chat_id
from app.domain.discovery import CustomerProfile
from app.domain.errors import LLMError
from app.domain.long_term_profile import LongTermProfile
from app.domain.ports import ConversationStore, LongTermProfileStore, ProfileSummarizer
from app.services.memory_service import utc_now

logger = logging.getLogger(__name__)

MIN_MESSAGES_TO_SUMMARIZE = 2  # a single "hi" says nothing about taste
MAX_MESSAGES_TO_SUMMARIZE = 60


@dataclass(frozen=True)
class ReturningContext:
    notes: str = ""  # what the agent should know about this customer
    welcome_back: bool = False  # a new session for a customer we already know


class ReturningCustomerService:
    def __init__(
        self,
        profiles: LongTermProfileStore,
        conversations: ConversationStore,
        summarizer: ProfileSummarizer,
        summary_max_chars: int,
        shown_limit: int,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        self._profiles = profiles
        self._conversations = conversations
        self._summarizer = summarizer
        self._summary_max_chars = summary_max_chars
        self._shown_limit = shown_limit
        self._clock = clock

    async def context_for(self, chat_id: str, new_session: bool) -> ReturningContext:
        profile = await self._profiles.get(chat_id)
        if new_session:
            profile = await self._summarize_previous_session(chat_id, profile)
        if profile.is_empty:
            return ReturningContext()
        return ReturningContext(profile.describe(), welcome_back=new_session)

    async def remember(
        self, chat_id: str, session_profile: CustomerProfile, product_handles: Sequence[str]
    ) -> None:
        """Write-through after every turn: new slots and newly shown products join the profile."""
        if not session_profile.known() and not product_handles:
            return
        profile = await self._profiles.get(chat_id)
        merged = profile.merge_session(session_profile, product_handles, self._clock(), self._shown_limit)
        if (merged.slots, merged.products_shown) != (profile.slots, profile.products_shown):
            await self._profiles.save(chat_id, merged)

    async def _summarize_previous_session(self, chat_id: str, profile: LongTermProfile) -> LongTermProfile:
        """Summarise what has not been summarised yet. A failing LLM never blocks the conversation."""
        unsummarized = await self._conversations.messages_after(
            chat_id, profile.summarized_until, MAX_MESSAGES_TO_SUMMARIZE
        )
        last_message_at = await self._conversations.last_message_at(chat_id)
        if len(unsummarized) < MIN_MESSAGES_TO_SUMMARIZE or last_message_at is None:
            return profile
        try:
            summary = await self._summarizer.summarize(unsummarized, profile.slots)
        except LLMError as exc:
            logger.warning("Could not summarise %s's last visit: %s", mask_chat_id(chat_id), exc)
            return profile
        updated = profile.with_summary(
            summary or profile.summary, last_message_at, self._clock(), self._summary_max_chars
        )
        await self._profiles.save(chat_id, updated)
        return updated
