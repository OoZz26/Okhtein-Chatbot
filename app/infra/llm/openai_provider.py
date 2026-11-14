"""LLMProvider adapter for any OpenAI-compatible chat API (OpenAI itself, OpenRouter, ...).

One class, configured twice: only the base URL, key, model and headers differ.
"""

import json
from collections.abc import Sequence
from typing import Any

import openai
from openai import AsyncOpenAI

from app.domain.errors import PermanentLLMError, TransientLLMError
from app.domain.models import ChatMessage, LLMResponse, ToolCall, ToolSpec

SERVER_ERROR_FLOOR = 500


class OpenAICompatibleProvider:
    def __init__(
        self,
        api_key: str,
        model: str,
        timeout_seconds: float,
        base_url: str | None = None,
        headers: dict[str, str] | None = None,
        http_client: openai.DefaultAsyncHttpxClient | None = None,
    ) -> None:
        # max_retries=0: retrying is the chain's job. The SDK's own hidden retries would multiply ours.
        self._client = AsyncOpenAI(
            api_key=api_key,
            base_url=base_url,
            timeout=timeout_seconds,
            max_retries=0,
            default_headers=headers,
            http_client=http_client,
        )
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
            raise self._classify(exc) from exc
        message = completion.choices[0].message
        calls = tuple(
            ToolCall(c.id, c.function.name, self._parse_arguments(c.function.arguments))
            for c in message.tool_calls or []
            if c.type == "function"
        )
        return LLMResponse(message.content or "", calls)

    @staticmethod
    def _classify(exc: openai.OpenAIError) -> Exception:
        """Translate the SDK's exceptions into our two kinds, so the chain never imports `openai`."""
        if isinstance(exc, openai.APITimeoutError | openai.APIConnectionError | openai.RateLimitError):
            return TransientLLMError(f"{type(exc).__name__}: {exc}")
        if isinstance(exc, openai.APIStatusError) and exc.status_code >= SERVER_ERROR_FLOOR:
            return TransientLLMError(f"HTTP {exc.status_code}: {exc}")
        return PermanentLLMError(f"{type(exc).__name__}: {exc}")

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
