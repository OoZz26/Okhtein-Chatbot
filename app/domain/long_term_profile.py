"""What we remember about a customer between visits. Pure data and merge rules, no I/O."""

from collections.abc import Sequence
from dataclasses import dataclass, field, replace
from datetime import datetime

from app.domain.discovery import CustomerProfile

ELLIPSIS = "…"


@dataclass(frozen=True)
class LongTermProfile:
    slots: CustomerProfile = field(default_factory=CustomerProfile)
    summary: str = ""
    products_shown: tuple[str, ...] = ()
    summarized_until: datetime | None = None  # messages up to this time are already in `summary`
    updated_at: datetime | None = None

    @property
    def is_empty(self) -> bool:
        return not self.slots.known() and not self.summary and not self.products_shown

    def merge_session(
        self, session: CustomerProfile, shown: Sequence[str], at: datetime, shown_limit: int
    ) -> "LongTermProfile":
        """Fold what a session learned into the profile. Newer information wins; products stay unique."""
        seen = list(self.products_shown)
        seen.extend(handle for handle in shown if handle not in seen)
        return replace(
            self,
            slots=self.slots.apply(session.known()),
            products_shown=tuple(seen[-shown_limit:]),
            updated_at=at,
        )

    def with_summary(
        self, summary: str, summarized_until: datetime, at: datetime, max_chars: int
    ) -> "LongTermProfile":
        return replace(
            self, summary=bound(summary, max_chars), summarized_until=summarized_until, updated_at=at
        )

    def describe(self) -> str:
        """The text the agent reads about this customer."""
        parts = []
        if self.summary:
            parts.append(f"Summary of earlier visits: {self.summary}")
        if self.slots.known():
            parts.append(f"Preferences: {self.slots.summary()}")
        if self.products_shown:
            parts.append(f"Products already shown before (handles): {', '.join(self.products_shown)}")
        return "\n".join(parts)


def bound(text: str, max_chars: int) -> str:
    """Trim to `max_chars`, cutting at a word boundary and marking the cut."""
    text = " ".join(text.split())
    if len(text) <= max_chars:
        return text
    cut = text[: max_chars - len(ELLIPSIS)]
    return cut.rsplit(" ", 1)[0].rstrip(".,;: ") + ELLIPSIS
