"""Who is talking to the customer: the bot or a person. An explicit two-state machine.

BOT_ACTIVE --handoff(reason, summary)--> HANDED_OFF --release()--> BOT_ACTIVE
HANDED_OFF --refreshed(at)--> HANDED_OFF  (staff wrote again: the timeout restarts)
"""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from app.domain.errors import InvalidTransitionError


class ChatMode(StrEnum):
    BOT_ACTIVE = "bot_active"
    HANDED_OFF = "handed_off"


@dataclass(frozen=True)
class HandoffState:
    mode: ChatMode = ChatMode.BOT_ACTIVE
    reason: str = ""
    summary: str = ""
    since: datetime | None = None

    @property
    def is_handed_off(self) -> bool:
        return self.mode == ChatMode.HANDED_OFF

    def handoff(self, reason: str, summary: str, at: datetime) -> "HandoffState":
        if self.is_handed_off:
            raise InvalidTransitionError("This chat is already handed off to a person")
        return HandoffState(ChatMode.HANDED_OFF, reason, summary, at)

    def refreshed(self, at: datetime) -> "HandoffState":
        """A person is still active in the chat: restart the timeout clock, keep reason and summary."""
        if not self.is_handed_off:
            raise InvalidTransitionError("Only a handed-off chat can be refreshed")
        return HandoffState(self.mode, self.reason, self.summary, at)

    def release(self) -> "HandoffState":
        if not self.is_handed_off:
            raise InvalidTransitionError("This chat is not handed off, so there is nothing to release")
        return HandoffState()
