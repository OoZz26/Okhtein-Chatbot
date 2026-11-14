"""Stand-ins used ONLY in load-test mode, so capacity can be measured without OpenAI or WhatsApp.

Why fake the LLM: the real one costs money per call, rate-limits us, and its latency (seconds) would
measure OpenAI, not our code. Why fake WhatsApp: one real number, and a ban risk if hammered.
"""

import asyncio
import json
import random
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from app.domain.models import ChatMessage, LLMResponse, ToolSpec

CANNED_REPLY = "Thank you for your message 🤍 This is a load-test reply."
MIN_LATENCY_SECONDS = 1.0
MAX_LATENCY_SECONDS = 3.0


class FakeLatencyLLM:
    """An LLMProvider that waits like a real model (1-3 s) and answers with a canned reply."""

    def __init__(
        self, min_seconds: float = MIN_LATENCY_SECONDS, max_seconds: float = MAX_LATENCY_SECONDS
    ) -> None:
        self._min = min_seconds
        self._max = max_seconds

    async def chat(
        self,
        messages: Sequence[ChatMessage],
        tools: Sequence[ToolSpec] = (),
        response_schema: dict[str, Any] | None = None,
    ) -> LLMResponse:
        await asyncio.sleep(random.uniform(self._min, self._max))
        if response_schema is None:  # a plain-text request, such as the returning-customer summary
            return LLMResponse("Likes bold pieces.")
        return LLMResponse(json.dumps({"message": CANNED_REPLY, "product_handles": []}))


@dataclass(frozen=True)
class RecordedSend:
    chat_id: str
    kind: str  # "text" | "image"
    text: str


class RecordingGateway:
    """A MessagingGateway that sends nothing: it records what would have been sent."""

    def __init__(self) -> None:
        self.sends: list[RecordedSend] = []

    async def send_text(self, chat_id: str, text: str) -> None:
        self.sends.append(RecordedSend(chat_id, "text", text))

    async def send_image(self, chat_id: str, image_url: str, caption: str) -> None:
        self.sends.append(RecordedSend(chat_id, "image", caption))

    async def mark_seen(self, chat_id: str) -> None:
        return None

    async def start_typing(self, chat_id: str) -> None:
        return None

    async def stop_typing(self, chat_id: str) -> None:
        return None

    def reset(self) -> None:
        self.sends.clear()
