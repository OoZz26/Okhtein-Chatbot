"""FallbackLLMProvider: an ordered chain of providers that is itself an LLMProvider.

Chain of Responsibility (each provider gets a turn) + Composite (the agent sees one provider).
"""

import asyncio
import logging
import random
import time
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from typing import Any

from app.domain.errors import AllProvidersFailedError, LLMError, TransientLLMError
from app.domain.models import ChatMessage, LLMResponse, ToolSpec
from app.domain.ports import LLMProvider

logger = logging.getLogger(__name__)

MS_PER_SECOND = 1000


@dataclass(frozen=True)
class ProviderSlot:
    name: str
    provider: LLMProvider


class FallbackLLMProvider:
    def __init__(
        self,
        slots: Sequence[ProviderSlot],
        max_retries: int,
        base_delay_seconds: float,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        jitter: Callable[[], float] = random.random,
    ) -> None:
        self._slots = list(slots)
        self._max_retries = max_retries
        self._base_delay = base_delay_seconds
        self._sleep = sleep
        self._jitter = jitter  # returns 0..1; injected so tests are deterministic

    async def chat(
        self,
        messages: Sequence[ChatMessage],
        tools: Sequence[ToolSpec] = (),
        response_schema: dict[str, Any] | None = None,
    ) -> LLMResponse:
        failures: list[str] = []
        for slot in self._slots:
            try:
                return await self._call_with_retries(slot, messages, tools, response_schema)
            except LLMError as exc:
                failures.append(f"{slot.name}: {exc}")
                logger.warning("llm_provider_failed provider=%s outcome=fallback reason=%s", slot.name, exc)
        raise AllProvidersFailedError(failures)

    async def _call_with_retries(
        self,
        slot: ProviderSlot,
        messages: Sequence[ChatMessage],
        tools: Sequence[ToolSpec],
        response_schema: dict[str, Any] | None,
    ) -> LLMResponse:
        """Retry transient errors with exponential backoff; let anything else escape to the next provider."""
        for attempt in range(1, self._max_retries + 2):
            started = time.perf_counter()
            try:
                response = await slot.provider.chat(messages, tools, response_schema)
            except TransientLLMError as exc:
                if attempt > self._max_retries:
                    raise
                delay = self._backoff(attempt)
                logger.warning(
                    "llm_retry provider=%s attempt=%d delay_s=%.2f reason=%s", slot.name, attempt, delay, exc
                )
                await self._sleep(delay)
            else:
                latency_ms = int((time.perf_counter() - started) * MS_PER_SECOND)
                logger.info(
                    "llm_call provider=%s attempts=%d latency_ms=%d outcome=ok",
                    slot.name,
                    attempt,
                    latency_ms,
                )
                return response
        raise AssertionError("unreachable: the loop always returns or raises")  # pragma: no cover

    def _backoff(self, attempt: int) -> float:
        """base * 2^(attempt-1), plus up to 50% random jitter so retries don't arrive in lockstep."""
        delay: float = self._base_delay * 2 ** (attempt - 1)
        return delay * (1 + 0.5 * self._jitter())
