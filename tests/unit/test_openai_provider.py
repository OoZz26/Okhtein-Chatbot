"""The adapter turns the OpenAI SDK's exceptions into our two error kinds, using a fake HTTP transport."""

import json

import httpx2
import openai
import pytest

from app.domain.errors import PermanentLLMError, TransientLLMError
from app.domain.models import ChatMessage
from app.infra.llm.openai_provider import OpenAICompatibleProvider

COMPLETION = {
    "id": "x",
    "object": "chat.completion",
    "created": 0,
    "model": "m",
    "choices": [{"index": 0, "finish_reason": "stop", "message": {"role": "assistant", "content": "hello"}}],
}


def provider(handler: httpx2.MockTransport, **kwargs: object) -> OpenAICompatibleProvider:
    client = openai.DefaultAsyncHttpxClient(transport=handler)
    return OpenAICompatibleProvider("key", "model", 5.0, http_client=client, **kwargs)  # type: ignore[arg-type]


def status(code: int) -> httpx2.MockTransport:
    return httpx2.MockTransport(lambda _: httpx2.Response(code, json={"error": {"message": f"HTTP {code}"}}))


MESSAGES = [ChatMessage("user", "hi")]


@pytest.mark.parametrize("code", [429, 500, 502, 503])
async def test_rate_limits_and_server_errors_are_transient(code: int) -> None:
    with pytest.raises(TransientLLMError):
        await provider(status(code)).chat(MESSAGES)


@pytest.mark.parametrize("code", [400, 401, 403, 404])
async def test_auth_and_request_errors_are_permanent(code: int) -> None:
    with pytest.raises(PermanentLLMError):
        await provider(status(code)).chat(MESSAGES)


async def test_timeouts_and_dropped_connections_are_transient() -> None:
    def fail(request: httpx2.Request) -> httpx2.Response:
        raise httpx2.ConnectTimeout("too slow", request=request)

    with pytest.raises(TransientLLMError):
        await provider(httpx2.MockTransport(fail)).chat(MESSAGES)


async def test_the_sdk_does_not_retry_on_its_own() -> None:
    calls = 0

    def count(_: httpx2.Request) -> httpx2.Response:
        nonlocal calls
        calls += 1
        return httpx2.Response(503, json={"error": {"message": "down"}})

    with pytest.raises(TransientLLMError):
        await provider(httpx2.MockTransport(count)).chat(MESSAGES)

    assert calls == 1  # retrying is the chain's job; SDK retries would multiply ours


async def test_a_good_response_is_mapped_to_our_type() -> None:
    ok = httpx2.MockTransport(lambda _: httpx2.Response(200, json=COMPLETION))

    response = await provider(ok).chat(MESSAGES)

    assert response.content == "hello"
    assert response.tool_calls == ()


async def test_base_url_and_headers_are_what_makes_it_openrouter() -> None:
    seen: list[httpx2.Request] = []

    def record(request: httpx2.Request) -> httpx2.Response:
        seen.append(request)
        return httpx2.Response(200, json=COMPLETION)

    openrouter = provider(
        httpx2.MockTransport(record),
        base_url="https://openrouter.ai/api/v1",
        headers={"X-Title": "Okhtein"},
    )
    await openrouter.chat(MESSAGES)

    assert str(seen[0].url) == "https://openrouter.ai/api/v1/chat/completions"
    assert seen[0].headers["X-Title"] == "Okhtein"
    assert json.loads(seen[0].content)["model"] == "model"


@pytest.mark.parametrize(("effort", "sent"), [("low", "low"), ("", None)])
async def test_reasoning_effort_is_sent_only_when_set(effort: str, sent: str | None) -> None:
    bodies: list[dict[str, object]] = []

    def record(request: httpx2.Request) -> httpx2.Response:
        bodies.append(json.loads(request.content))
        return httpx2.Response(200, json=COMPLETION)

    await provider(httpx2.MockTransport(record), reasoning_effort=effort).chat(MESSAGES)

    assert bodies[0].get("reasoning_effort") == sent
