"""The Tool protocol and the registry that dispatches the model's tool calls (Command + Registry)."""

import logging
from collections.abc import Sequence
from typing import Any, Protocol

from app.domain.models import ToolSpec

logger = logging.getLogger(__name__)


class Tool(Protocol):
    """One capability the model can call. Adding a tool = adding a class, not editing the agent."""

    name: str
    description: str
    parameters: dict[str, Any]

    def run(self, arguments: dict[str, Any]) -> dict[str, Any]: ...


class ToolRegistry:
    def __init__(self, tools: Sequence[Tool]) -> None:
        self._tools = {tool.name: tool for tool in tools}

    def specs(self) -> list[ToolSpec]:
        return [ToolSpec(t.name, t.description, t.parameters) for t in self._tools.values()]

    def run(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        """Run a tool. Problems are returned to the model as an error result, never raised."""
        tool = self._tools.get(name)
        if tool is None:
            logger.warning("Model called unknown tool %r", name)
            return {"error": f"unknown tool {name}"}
        try:
            return tool.run(arguments)
        except (TypeError, ValueError) as exc:
            logger.warning("Tool %s got bad arguments %r: %s", name, arguments, exc)
            return {"error": f"invalid arguments: {exc}"}
