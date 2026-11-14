"""Turns the owner-edited knowledge file into the text the agent sees."""

import re

_TODO_HEADING = re.compile(r"^##\s*TODO\b.*$", re.IGNORECASE | re.MULTILINE)
_NEXT_HEADING = re.compile(r"^##\s", re.MULTILINE)

UNKNOWN_HEADING = "## Topics the store has NOT provided (unknown: never guess, a team member will confirm)"


def render_store_knowledge(raw: str) -> str:
    """Keep known facts as they are; turn the owner's TODO list into an explicit 'unknown' list.

    The TODO section lists topics with empty values ("Shipping fees:"). Left as is, a model may fill the
    gaps with plausible inventions, so we state plainly that these topics are unknown.
    """
    todo = _TODO_HEADING.search(raw)
    if todo is None:
        return raw.strip()
    next_heading = _NEXT_HEADING.search(raw, todo.end())
    section_end = next_heading.start() if next_heading else len(raw)
    topics = [_topic(line) for line in raw[todo.end() : section_end].splitlines() if line.strip()]
    unknown = "\n".join(f"- {topic}" for topic in topics if topic)
    rest = raw[: todo.start()] + (raw[section_end:] if next_heading else "")
    return f"{rest.strip()}\n\n{UNKNOWN_HEADING}\n{unknown}".strip()


def _topic(line: str) -> str:
    """'- Shipping times and fees inside Egypt:' -> 'Shipping times and fees inside Egypt'."""
    return line.strip().lstrip("-* ").rstrip(": ").strip()
