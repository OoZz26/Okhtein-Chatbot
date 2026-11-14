"""Helpers that keep personal data out of logs."""

VISIBLE_DIGITS = 4


def mask_chat_id(chat_id: str) -> str:
    """'201001234567@c.us' -> '…4567' so logs never contain a full phone number."""
    local_part = chat_id.split("@")[0]
    return "…" + local_part[-VISIBLE_DIGITS:]
