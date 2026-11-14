"""Domain data types. Plain frozen dataclasses: no framework, no I/O."""

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Literal

Role = Literal["system", "user", "assistant", "tool"]


@dataclass(frozen=True)
class Product:
    handle: str
    title: str
    category: str
    color: str
    price_min: float
    price_max: float
    available: bool
    tags: tuple[str, ...] = ()
    description: str = ""
    image_url: str = ""


@dataclass(frozen=True)
class ToolCall:
    """The model asking us to run a tool."""

    id: str
    name: str
    arguments: dict[str, Any]


@dataclass(frozen=True)
class ToolSpec:
    """What the model is told about a tool (name, purpose, JSON schema of its arguments)."""

    name: str
    description: str
    parameters: dict[str, Any]


@dataclass(frozen=True)
class ChatMessage:
    role: Role
    content: str = ""
    tool_calls: tuple[ToolCall, ...] = ()
    tool_call_id: str | None = None


@dataclass(frozen=True)
class LLMResponse:
    content: str = ""
    tool_calls: tuple[ToolCall, ...] = ()


class ConversationStage(StrEnum):
    GREET = "greet"
    DISCOVER = "discover"
    RECOMMEND = "recommend"
    REFINE = "refine"
    CLOSE = "close"


@dataclass
class AgentReply:
    """Structured agent output. `message` is what the customer reads; links are built from handles."""

    message: str
    product_handles: list[str] = field(default_factory=list)
    stage: ConversationStage | None = None
    profile_updates: dict[str, str] = field(default_factory=dict)
    handoff_reason: str = ""  # non-empty: a person must take over, and why
    handoff_summary: str = ""  # 1-3 lines for the team

    @property
    def wants_handoff(self) -> bool:
        return bool(self.handoff_reason.strip())


@dataclass(frozen=True)
class AgentContext:
    """Per-turn facts the agent is told about the customer and the conversation so far."""

    sender_name: str = ""
    stage: ConversationStage = ConversationStage.GREET
    profile_summary: str = ""
    guidance: str = ""


@dataclass(frozen=True)
class IncomingMessage:
    """A customer message as the app sees it, independent of the WhatsApp gateway's JSON format."""

    message_id: str
    chat_id: str
    text: str
    sender_name: str = ""
    from_me: bool = False
    is_group: bool = False
    is_status: bool = False
    has_media: bool = False
    from_phone: bool = False  # sent by a person on the business phone (not by our own API calls)


@dataclass(frozen=True)
class ProductCard:
    """What a recommended product looks like on WhatsApp: a picture with a caption."""

    title: str
    price_text: str
    link: str
    image_url: str

    @property
    def caption(self) -> str:
        return "\n".join([f"*{self.title}*", self.price_text, self.link])


@dataclass(frozen=True)
class ScoredHandle:
    """A vector-search hit: which product, and how similar (0..1, higher is better)."""

    handle: str
    score: float


@dataclass(frozen=True)
class VectorFilters:
    """Hard constraints applied in the same query as the similarity ranking."""

    category: str | None = None
    max_price: float | None = None
    in_stock_only: bool = True


@dataclass(frozen=True)
class IndexedProduct:
    """One product in the vector index: facts for filtering stored next to the embedding."""

    handle: str
    content_hash: str
    embedding_model: str
    category: str
    price_min: float
    available: bool
    title: str
    embedding: tuple[float, ...]


@dataclass(frozen=True)
class ProductGroup:
    """A product model with its colour variants collapsed: the best match plus the other colours."""

    product: Product
    other_colours: tuple[str, ...] = ()
