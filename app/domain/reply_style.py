"""Make a reply read like a person texting, not a generated document.

The prompt asks for this too, but models slip back into dashes and bullet lists, so the reply is cleaned in
code as well: dashes become commas and list markers are dropped (the line itself stays). The bot
answers in English for now, so any Arabic word the persona slips in ("أكيد", "يا حلوة") is removed too.
"""

import re

_SPACED_DASH = re.compile(r"\s*[—–]\s*")  # "pretty — and practical" -> "pretty, and practical"
_LIST_MARKER = re.compile(r"(?m)^[ \t]*(?:[•●▪◦‣]|[-–—](?=\s)|\d{1,2}[.)](?=\s))[ \t]*")
_DOUBLE_COMMA = re.compile(r",\s*,")
_COMMA_BEFORE_STOP = re.compile(r",\s*([.!?\n]|$)")


_ARABIC_WORD = re.compile(r"[؀-ۿ]+[\s,.!?؟،]*")  # one Arabic-script word and what trails it
_LEADING_JUNK = re.compile(r"^[\s,.!?]+")


def remove_arabic_words(message: str) -> str:
    """The bot speaks English only for now; the model still slips in "أكيد 🤍" or "تمام يا حلوة"."""
    lines = [_LEADING_JUNK.sub("", _ARABIC_WORD.sub("", line)) for line in message.split("\n")]
    return "\n".join(lines).strip()


def humanize_punctuation(message: str) -> str:
    text = _LIST_MARKER.sub("", message)
    text = _SPACED_DASH.sub(", ", text)
    text = _DOUBLE_COMMA.sub(",", text)
    return _COMMA_BEFORE_STOP.sub(r"\1", text).strip()
