"""LLMProvider adapter for OpenAI chat completions. Translates between our types and OpenAI's."""

import json
import logging
from collections.abc import Sequence
from typing import Any

import openai
from openai import AsyncOpenAI

from app.domain.errors import LLMError
from app.domain.models import ChatMessage, LLMResponse, ToolCall, ToolSpec

logger = logging.getLogger(__name__)


class OpenAIProvider:
    def __init__(self, api_key: str, model: str, timeout_seconds: float) -> None:
        self._client = AsyncOpenAI(api_key=api_key, timeout=timeout_seconds)
        self._model = model

    async def chat(
        self,
        messages: Sequence[ChatMessage],
        tools: Sequence[ToolSpec] = (),
        response_schema: dict[str, Any] | None = None,
    ) -> LLMResponse:
        kwargs: dict[str, Any] = {"model": self._model, "messages": [self._message(m) for m in messages]}
        if tools:
            kwargs["tools"] = [self._tool(t) for t in tools]
        if response_schema:
            kwargs["response_format"] = {
                "type": "json_schema",
                "json_schema": {"name": "agent_reply", "strict": True, "schema": response_schema},
            }
        try:
            completion = await self._client.chat.completions.create(**kwargs)
        except openai.OpenAIError as exc:
            logger.error("OpenAI request failed: %s", exc)
            raise LLMError(f"OpenAI request failed: {exc}") from exc
        message = completion.choices[0].message
        calls = tuple(
            ToolCall(c.id, c.function.name, self._parse_arguments(c.function.arguments))
            for c in message.tool_calls or []
            if c.type == "function"
        )
        return LLMResponse(message.content or "", calls)

    @staticmethod
    def _parse_arguments(raw: str) -> dict[str, Any]:
        try:
            parsed = json.loads(raw or "{}")
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}

    @staticmethod
    def _tool(spec: ToolSpec) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {"name": spec.name, "description": spec.description, "parameters": spec.parameters},
        }

    @staticmethod
    def _message(message: ChatMessage) -> dict[str, Any]:
        if message.role == "tool":
            return {"role": "tool", "tool_call_id": message.tool_call_id, "content": message.content}
        payload: dict[str, Any] = {"role": message.role, "content": message.content}
        if message.tool_calls:
            payload["tool_calls"] = [
                {
                    "id": c.id,
                    "type": "function",
                    "function": {"name": c.name, "arguments": json.dumps(c.arguments)},
                }
                for c in message.tool_calls
            ]
        return payload
