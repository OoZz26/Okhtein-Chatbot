import json

import httpx
import pytest

from app.domain.errors import MessagingError
from app.infra.whatsapp.waha_gateway import WahaGateway


def gateway(handler: httpx.MockTransport) -> WahaGateway:
    return WahaGateway("http://waha:3000/", "secret-key", "default", 5.0, transport=handler)


async def test_send_text_posts_to_waha_with_api_key() -> None:
    seen: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(201, json={})

    await gateway(httpx.MockTransport(handle)).send_text("201001234567@c.us", "hello")

    request = seen[0]
    assert str(request.url) == "http://waha:3000/api/sendText"
    assert request.headers["X-Api-Key"] == "secret-key"
    assert json.loads(request.content) == {
        "session": "default",
        "chatId": "201001234567@c.us",
        "text": "hello",
    }


async def test_mark_seen_uses_send_seen_endpoint() -> None:
    seen: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(201, json={})

    await gateway(httpx.MockTransport(handle)).mark_seen("201001234567@c.us")

    assert seen[0].url.path == "/api/sendSeen"


async def test_send_image_posts_a_jpeg_with_caption() -> None:
    seen: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(201, json={})

    await gateway(httpx.MockTransport(handle)).send_image("2010@c.us", "https://img/a.jpg", "*Clutch*")

    assert seen[0].url.path == "/api/sendImage"
    assert json.loads(seen[0].content) == {
        "session": "default",
        "chatId": "2010@c.us",
        "file": {"mimetype": "image/jpeg", "url": "https://img/a.jpg", "filename": "product.jpg"},
        "caption": "*Clutch*",
    }


async def test_typing_calls_use_the_start_and_stop_endpoints() -> None:
    paths: list[str] = []

    def handle(request: httpx.Request) -> httpx.Response:
        paths.append(request.url.path)
        return httpx.Response(201, json={})

    waha = gateway(httpx.MockTransport(handle))
    await waha.start_typing("2010@c.us")
    await waha.stop_typing("2010@c.us")

    assert paths == ["/api/startTyping", "/api/stopTyping"]


async def test_http_errors_become_messaging_errors() -> None:
    failing = httpx.MockTransport(lambda _: httpx.Response(500))
    with pytest.raises(MessagingError):
        await gateway(failing).send_text("201001234567@c.us", "hello")
