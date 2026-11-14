"""The sales agent: runs the tool loop and returns a validated, structured reply."""

import json
import logging
import re
from pathlib import Path
from typing import Any

from app.domain.errors import LLMError
from app.domain.models import AgentReply, ChatMessage
from app.domain.ports import LLMProvider, ProductRepository
from app.domain.tools.base import ToolRegistry

logger = logging.getLogger(__name__)

PROMPTS_DIR = Path(__file__).parent / "prompts"
_URL_PATTERN = re.compile(r"https?://\S+")

REPLY_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "message": {"type": "string"},
        "product_handles": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["message", "product_handles"],
    "additionalProperties": False,
}


def load_system_prompt(version: str = "v1") -> str:
    return (PROMPTS_DIR / f"system_{version}.md").read_text(encoding="utf-8")


class SalesAgent:
    def __init__(
        self,
        llm: LLMProvider,
        tools: ToolRegistry,
        products: ProductRepository,
        system_prompt: str,
        max_tool_rounds: int,
    ) -> None:
        self._llm = llm
        self._tools = tools
        self._products = products
        self._system_prompt = system_prompt
        self._max_tool_rounds = max_tool_rounds

    async def respond(self, user_text: str) -> AgentReply:
        messages = [ChatMessage("system", self._system_prompt), ChatMessage("user", user_text)]
        for _ in range(self._max_tool_rounds):
            response = await self._llm.chat(messages, self._tools.specs(), REPLY_SCHEMA)
            if not response.tool_calls:
                return self._validate(response.content)
            messages.append(ChatMessage("assistant", response.content, response.tool_calls))
            for call in response.tool_calls:
                result = self._tools.run(call.name, call.arguments)
                messages.append(
                    ChatMessage("tool", json.dumps(result, ensure_ascii=False), tool_call_id=call.id)
                )
        logger.warning("Tool loop hit the %d-round limit; asking for a final answer", self._max_tool_rounds)
        final = await self._llm.chat(messages, (), REPLY_SCHEMA)
        return self._validate(final.content)

    def _validate(self, raw: str) -> AgentReply:
        """Trust nothing the model says: drop unknown handles and every URL."""
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise LLMError(f"Model did not return valid JSON: {exc}") from exc
        if not isinstance(data, dict) or not isinstance(data.get("message"), str):
            raise LLMError("Model reply is missing a text `message`")
        return AgentReply(self._strip_urls(data["message"]), self._known_handles(data.get("product_handles")))

    def _known_handles(self, handles: object) -> list[str]:
        known: list[str] = []
        for handle in handles if isinstance(handles, list) else []:
            if not isinstance(handle, str) or self._products.get(handle) is None:
                logger.warning("Dropped unknown product handle from model reply: %r", handle)
            elif handle not in known:
                known.append(handle)
        return known

    @staticmethod
    def _strip_urls(message: str) -> str:
        if _URL_PATTERN.search(message):
            logger.warning("Removed URL(s) written by the model; links are built from handles")
        return _URL_PATTERN.sub("", message).strip()
