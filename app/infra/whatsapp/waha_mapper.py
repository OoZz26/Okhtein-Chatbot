"""Maps WAHA's webhook JSON to our IncomingMessage. WAHA's format stops here."""

from typing import Any

from app.domain.models import IncomingMessage

MESSAGE_EVENT = "message"
MESSAGE_ANY_EVENT = "message.any"  # includes messages we or the business phone SEND
SOURCE_PHONE = "app"  # WAHA marks messages typed on the phone "app" and its own API calls "api"
GROUP_SUFFIX = "@g.us"
STATUS_BROADCAST = "status@broadcast"
CHANNEL_SUFFIX = "@newsletter"


def map_webhook(event: dict[str, Any]) -> IncomingMessage | None:
    """Return the message for a `message` / `message.any` event, or None for anything else."""
    name = event.get("event")
    if name not in (MESSAGE_EVENT, MESSAGE_ANY_EVENT):
        return None
    payload = event.get("payload")
    if not isinstance(payload, dict):
        return None
    from_me = bool(payload.get("fromMe"))
    if name == MESSAGE_ANY_EVENT and not from_me:
        return None  # incoming messages already arrive as `message` events; do not handle them twice
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
        from_phone=from_me and payload.get("source") == SOURCE_PHONE,
    )
