"""Discovery rules enforced in code (not only in the prompt): profile slots, stages, question limit."""

from collections.abc import Mapping, Sequence
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

# The discovery checklist, in the order worth asking. Each topic is answered by any of its slots.
CHECKLIST: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("who it is for (themselves or a gift)", ("for_whom",)),
    ("the occasion", ("occasion",)),
    ("the type of piece (bag, clutch, jewelry, eyewear...)", ("category",)),
    ("colour or style", ("colour", "style")),
    ("the budget", ("budget",)),
)
DISCOVERY_STAGES = frozenset({ConversationStage.GREET, ConversationStage.DISCOVER})


@dataclass(frozen=True)
class SessionState:
    stage: ConversationStage = ConversationStage.GREET
    profile: CustomerProfile = field(default_factory=CustomerProfile)
    questions_asked: int = 0
    shown_products: tuple[str, ...] = ()  # handles already recommended this session, oldest first
    awaiting_answer: bool = False  # the last reply asked the customer a question
    dodged_questions: int = 0  # questions in a row the customer answered without any new detail


DEFAULT_SHOWN_LIMIT = 30
MAX_DODGED_QUESTIONS = 2  # "I don't know" twice: stop asking and show a varied selection


class DiscoveryPolicy:
    def __init__(self, max_questions: int, shown_limit: int = DEFAULT_SHOWN_LIMIT) -> None:
        self._max_questions = max_questions
        self._shown_limit = shown_limit

    def guidance(self, state: SessionState) -> str:
        """An instruction for the agent when a hard rule applies this turn; empty when none does."""
        if state.questions_asked >= self._max_questions:
            return (
                f"You have already asked {state.questions_asked} questions. Do NOT ask another one: "
                "search the catalog now and recommend products that fit what you know."
            )
        if state.dodged_questions >= MAX_DODGED_QUESTIONS:
            return (
                "The customer has not been able to answer your last questions. Do NOT ask anything "
                "more: search now and show a small varied selection (for instance a bag, a small "
                "leather piece and a piece of jewelry) so they can react to real pieces."
            )
        if state.stage in DISCOVERY_STAGES:
            return self._checklist_note(state)
        return ""

    def _checklist_note(self, state: SessionState) -> str:
        known = state.profile.known()
        missing = [topic for topic, slots in CHECKLIST if not any(slot in known for slot in slots)]
        if not missing:
            return "The discovery checklist is complete: search now and recommend."
        left = self._max_questions - state.questions_asked
        return (
            "If the customer's latest message is a specific request (a type of piece plus a colour or "
            "a budget, in any language: 'a gold clutch', 'a bag under 50000'; a type alone like 'a bag' "
            "is NOT specific), asks to see products, "
            "sounds impatient, or answers the budget: search and recommend NOW. Otherwise keep "
            f"discovering. Checklist items unknown BEFORE the latest message: {'; '.join(missing)}. "
            "Tick off whatever the latest message answers, skip any item you already asked about "
            "(a skipped or 'don't know' answer counts as done), and ask about the first item left in "
            f"one short question ({left} question(s) left)."
        )

    def update(self, state: SessionState, reply: AgentReply) -> SessionState:
        shown_products = bool(reply.product_handles)
        return SessionState(
            stage=self._next_stage(state.stage, reply.stage, shown_products),
            profile=state.profile.apply(reply.profile_updates),
            questions_asked=0 if shown_products else state.questions_asked + self._is_question(reply),
            shown_products=self._remember_shown(state.shown_products, reply.product_handles),
            awaiting_answer=bool(self._is_question(reply)),
            dodged_questions=0 if shown_products else self._dodged(state, reply),
        )

    @staticmethod
    def _dodged(state: SessionState, reply: AgentReply) -> int:
        """The customer just answered our question; did the answer teach us anything new?"""
        if not state.awaiting_answer:
            return state.dodged_questions
        learned = any(state.profile.apply({k: v}) != state.profile for k, v in reply.profile_updates.items())
        return 0 if learned else state.dodged_questions + 1

    @staticmethod
    def cards_to_send(state: SessionState, handles: Sequence[str]) -> list[str]:
        """Never resend a product card the customer has already seen this session, unless the reply
        shows ONLY products seen before: then the customer asked for them again, so send them."""
        new = [handle for handle in handles if handle not in state.shown_products]
        return new or list(handles)

    def _remember_shown(self, shown: tuple[str, ...], handles: Sequence[str]) -> tuple[str, ...]:
        merged = [h for h in shown if h not in handles] + list(dict.fromkeys(handles))
        return tuple(merged[-self._shown_limit :])

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
