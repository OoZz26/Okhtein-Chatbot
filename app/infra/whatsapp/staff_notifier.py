"""StaffNotifier adapters: the log, and optionally ONE configured staff WhatsApp number."""

import logging
from collections.abc import Sequence

from app.core.privacy import mask_chat_id
from app.domain.errors import OkhteinError
from app.domain.handoff import HandoffState
from app.domain.ports import MessagingGateway, StaffNotifier

logger = logging.getLogger(__name__)


def describe(chat_id: str, state: HandoffState) -> str:
    """The text staff read: who needs help, why, and a short summary."""
    customer = chat_id.split("@")[0]
    lines = ["🔔 A customer needs a person", f"Customer: +{customer}", f"Reason: {state.reason}"]
    if state.summary:
        lines.append(f"Summary: {state.summary}")
    return "\n".join(lines)


class LogStaffNotifier:
    async def notify(self, chat_id: str, state: HandoffState) -> None:
        logger.warning(
            "staff_notification chat=%s reason=%s summary=%s",
            mask_chat_id(chat_id),
            state.reason,
            state.summary,
        )


class WhatsAppStaffNotifier:
    """Sends the notification to the configured staff number and to nobody else."""

    def __init__(self, gateway: MessagingGateway, staff_chat_id: str) -> None:
        self._gateway = gateway
        self._staff_chat_id = staff_chat_id

    async def notify(self, chat_id: str, state: HandoffState) -> None:
        try:
            await self._gateway.send_text(self._staff_chat_id, describe(chat_id, state))
        except OkhteinError:
            # A failed alert must not break the chat.
            logger.exception("Could not send the staff notification")


class CompositeStaffNotifier:
    def __init__(self, notifiers: Sequence[StaffNotifier]) -> None:
        self._notifiers = list(notifiers)

    async def notify(self, chat_id: str, state: HandoffState) -> None:
        for notifier in self._notifiers:
            await notifier.notify(chat_id, state)
