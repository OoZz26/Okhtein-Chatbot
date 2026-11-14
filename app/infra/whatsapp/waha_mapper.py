"""Maps WAHA's webhook JSON to our IncomingMessage. WAHA's format stops here."""

from typing import Any

from app.domain.models import IncomingMessage

MESSAGE_EVENT = "message"
GROUP_SUFFIX = "@g.us"
STATUS_BROADCAST = "status@broadcast"
CHANNEL_SUFFIX = "@newsletter"


def map_webhook(event: dict[str, Any]) -> IncomingMessage | None:
    """Return the message for a `message` event, or None for any other / malformed event."""
    if event.get("event") != MESSAGE_EVENT:
        return None
    payload = event.get("payload")
    if not isinstance(payload, dict):
        return None
    from_me = bool(payload.get("fromMe"))
    chat_id = payload.get("to") if from_me else payload.get("from")
    message_id = payload.get("id")
    if not isinstance(chat_id, str) or not isinstance(message_id, str):
        return None
    raw_data = payload.get("_data")
    data: dict[str, Any] = raw_data if isinstance(raw_data, dict) else {}
    return IncomingMessage(
        message_id=message_id,
        chat_id=chat_id,
        text=str(payload.get("body") or ""),
        sender_name=str(data.get("notifyName") or ""),
        from_me=from_me,
        is_group=chat_id.endswith(GROUP_SUFFIX) or chat_id.endswith(CHANNEL_SUFFIX),
        is_status=chat_id == STATUS_BROADCAST,
        has_media=bool(payload.get("hasMedia")),
    )
