"""Domain data types. Plain frozen dataclasses: no framework, no I/O."""

from dataclasses import dataclass, field
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


@dataclass
class AgentReply:
    """Structured agent output. `message` is what the customer reads; links are built from handles."""

    message: str
    product_handles: list[str] = field(default_factory=list)


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
