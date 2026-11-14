"""Splitting a long reply into a few natural WhatsApp messages."""

PARAGRAPH_BREAK = "\n\n"


def split_into_bubbles(text: str, max_bubbles: int) -> list[str]:
    """Split on blank lines; if there are too many paragraphs, the last bubble keeps all the remainder.

    A short reply stays a single message. Never returns more than `max_bubbles` parts, never an empty part.
    """
    paragraphs = [p.strip() for p in text.split(PARAGRAPH_BREAK) if p.strip()]
    if len(paragraphs) <= max_bubbles:
        return paragraphs
    head, tail = paragraphs[: max_bubbles - 1], paragraphs[max_bubbles - 1 :]
    return [*head, PARAGRAPH_BREAK.join(tail)]
