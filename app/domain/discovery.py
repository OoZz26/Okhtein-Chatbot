"""Discovery rules enforced in code (not only in the prompt): profile slots, stages, question limit."""

from collections.abc import Mapping
from dataclasses import dataclass, field, fields, replace

from app.domain.models import AgentReply, ConversationStage

QUESTION_MARKS = ("?", "؟")

Stage = ConversationStage
_ALLOWED_TRANSITIONS: dict[Stage, frozenset[Stage]] = {
    Stage.GREET: frozenset({Stage.GREET, Stage.DISCOVER, Stage.RECOMMEND, Stage.CLOSE}),
    Stage.DISCOVER: frozenset({Stage.DISCOVER, Stage.RECOMMEND, Stage.CLOSE}),
    Stage.RECOMMEND: frozenset({Stage.RECOMMEND, Stage.REFINE, Stage.DISCOVER, Stage.CLOSE}),
    Stage.REFINE: frozenset({Stage.REFINE, Stage.RECOMMEND, Stage.DISCOVER, Stage.CLOSE}),
    Stage.CLOSE: frozenset({Stage.CLOSE, Stage.GREET, Stage.DISCOVER, Stage.RECOMMEND}),
}


@dataclass(frozen=True)
class CustomerProfile:
    """What we have learned about the customer's needs this session (slot filling)."""

    for_whom: str = ""
    occasion: str = ""
    category: str = ""
    style: str = ""
    colour: str = ""
    practicality: str = ""
    budget: str = ""

    def apply(self, updates: Mapping[str, str]) -> "CustomerProfile":
        """Return a new profile with the non-blank, known slots overwritten. Pure: self is unchanged."""
        slots = {f.name for f in fields(self)}
        valid = {key: value.strip() for key, value in updates.items() if key in slots and value.strip()}
        return replace(self, **valid)

    def known(self) -> dict[str, str]:
        return {f.name: getattr(self, f.name) for f in fields(self) if getattr(self, f.name)}

    def summary(self) -> str:
        return "; ".join(f"{slot}: {value}" for slot, value in self.known().items())


PROFILE_SLOT_NAMES = tuple(f.name for f in fields(CustomerProfile))


@dataclass(frozen=True)
class SessionState:
    stage: ConversationStage = ConversationStage.GREET
    profile: CustomerProfile = field(default_factory=CustomerProfile)
    questions_asked: int = 0


class DiscoveryPolicy:
    def __init__(self, max_questions: int) -> None:
        self._max_questions = max_questions

    def guidance(self, state: SessionState) -> str:
        """An instruction for the agent when a hard rule applies this turn; empty when none does."""
        if state.questions_asked >= self._max_questions:
            return (
                f"You have already asked {state.questions_asked} questions. Do NOT ask another one: "
                "search the catalog now and recommend products that fit what you know."
            )
        return ""

    def update(self, state: SessionState, reply: AgentReply) -> SessionState:
        shown_products = bool(reply.product_handles)
        return SessionState(
            stage=self._next_stage(state.stage, reply.stage, shown_products),
            profile=state.profile.apply(reply.profile_updates),
            questions_asked=0 if shown_products else state.questions_asked + self._is_question(reply),
        )

    @staticmethod
    def _is_question(reply: AgentReply) -> int:
        return int(any(mark in reply.message for mark in QUESTION_MARKS))

    @staticmethod
    def _next_stage(
        current: ConversationStage, proposed: ConversationStage | None, shown_products: bool
    ) -> ConversationStage:
        """Accept the model's proposed stage only if the transition is allowed and matches what happened."""
        if shown_products:
            was_recommending = current in (ConversationStage.RECOMMEND, ConversationStage.REFINE)
            return ConversationStage.REFINE if was_recommending else ConversationStage.RECOMMEND
        if proposed is not None and proposed in _ALLOWED_TRANSITIONS[current]:
            return proposed if proposed != ConversationStage.RECOMMEND else current  # nothing was shown
        return current
