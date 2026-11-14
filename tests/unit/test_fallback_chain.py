import logging

import pytest

from app.domain.errors import (
    AllProvidersFailedError,
    LLMError,
    PermanentLLMError,
    TransientLLMError,
)
from app.domain.llm.fallback_chain import FallbackLLMProvider, ProviderSlot
from app.domain.models import ChatMessage, LLMResponse
from tests.fakes import ScriptedProvider

MESSAGES = [ChatMessage("user", "hi")]
OK = LLMResponse("answer")


class Sleeps:
    """Records the backoff delays instead of really sleeping."""

    def __init__(self) -> None:
        self.delays: list[float] = []

    async def __call__(self, seconds: float) -> None:
        self.delays.append(seconds)


def chain(
    *providers: tuple[str, ScriptedProvider], max_retries: int = 2, sleeps: Sleeps | None = None
) -> FallbackLLMProvider:
    return FallbackLLMProvider(
        [ProviderSlot(name, provider) for name, provider in providers],
        max_retries=max_retries,
        base_delay_seconds=1.0,
        sleep=sleeps or Sleeps(),
        jitter=lambda: 0.0,  # no randomness in tests
    )


async def test_primary_works_so_fallback_is_never_called() -> None:
    primary, fallback = ScriptedProvider(OK), ScriptedProvider(LLMResponse("never"))

    response = await chain(("openai", primary), ("openrouter", fallback)).chat(MESSAGES)

    assert response.content == "answer"
    assert (primary.calls, fallback.calls) == (1, 0)


async def test_primary_raises_so_the_fallback_answers() -> None:
    primary = ScriptedProvider(PermanentLLMError("bad key"))
    fallback = ScriptedProvider(LLMResponse("from fallback"))

    response = await chain(("openai", primary), ("openrouter", fallback)).chat(MESSAGES)

    assert response.content == "from fallback"


async def test_permanent_errors_fall_back_immediately_without_retrying() -> None:
    primary, fallback = ScriptedProvider(PermanentLLMError("401")), ScriptedProvider(OK)
    sleeps = Sleeps()

    await chain(("openai", primary), ("openrouter", fallback), sleeps=sleeps).chat(MESSAGES)

    assert primary.calls == 1
    assert sleeps.delays == []


async def test_a_transient_error_is_retried_before_falling_back() -> None:
    primary = ScriptedProvider(TransientLLMError("429"), OK)
    fallback = ScriptedProvider(LLMResponse("never"))

    response = await chain(("openai", primary), ("openrouter", fallback)).chat(MESSAGES)

    assert response.content == "answer"  # the retry on the same provider succeeded
    assert (primary.calls, fallback.calls) == (2, 0)


async def test_retries_back_off_exponentially_then_fall_back() -> None:
    primary = ScriptedProvider(*[TransientLLMError("503")] * 3)  # 1 try + 2 retries, all failing
    fallback = ScriptedProvider(OK)
    sleeps = Sleeps()

    await chain(("openai", primary), ("openrouter", fallback), max_retries=2, sleeps=sleeps).chat(MESSAGES)

    assert primary.calls == 3
    assert sleeps.delays == [1.0, 2.0]  # base * 2^(attempt-1)
    assert fallback.calls == 1


async def test_jitter_adds_up_to_half_the_delay() -> None:
    sleeps = Sleeps()
    slow = FallbackLLMProvider(
        [ProviderSlot("openai", ScriptedProvider(TransientLLMError("x"), OK))],
        max_retries=1,
        base_delay_seconds=2.0,
        sleep=sleeps,
        jitter=lambda: 1.0,
    )

    await slow.chat(MESSAGES)

    assert sleeps.delays == [3.0]  # 2.0 + 50%


async def test_all_providers_failing_raises_one_error_naming_each_failure() -> None:
    chain_of_failures = chain(
        ("openai", ScriptedProvider(PermanentLLMError("bad key"))),
        ("openrouter", ScriptedProvider(PermanentLLMError("no credit"))),
    )

    with pytest.raises(AllProvidersFailedError) as caught:
        await chain_of_failures.chat(MESSAGES)

    assert len(caught.value.failures) == 2
    assert "openai: bad key" in caught.value.failures[0]
    assert "openrouter: no credit" in caught.value.failures[1]
    assert isinstance(caught.value, LLMError)  # callers can catch the base type


async def test_provider_order_is_respected() -> None:
    first, second = ScriptedProvider(LLMResponse("first")), ScriptedProvider(LLMResponse("second"))

    response = await chain(("openrouter", first), ("openai", second)).chat(MESSAGES)

    assert response.content == "first"


async def test_every_call_logs_provider_attempts_and_outcome(caplog: pytest.LogCaptureFixture) -> None:
    primary = ScriptedProvider(PermanentLLMError("bad key"))
    fallback = ScriptedProvider(OK)

    with caplog.at_level(logging.INFO):
        await chain(("openai", primary), ("openrouter", fallback)).chat(MESSAGES)

    assert "llm_provider_failed provider=openai outcome=fallback" in caplog.text
    assert "llm_call provider=openrouter attempts=1" in caplog.text
    assert "outcome=ok" in caplog.text
