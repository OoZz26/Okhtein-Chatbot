from fakeredis import FakeAsyncRedis

from app.domain.models import ChatMessage
from app.infra.cache.redis_short_term import RedisShortTermMemory

CHAT = "chat-1"


def memory(max_messages: int = 3, ttl: int = 60) -> tuple[RedisShortTermMemory, FakeAsyncRedis]:
    client = FakeAsyncRedis(decode_responses=True)
    return RedisShortTermMemory(client, max_messages, ttl), client


async def test_messages_round_trip_in_order_including_arabic() -> None:
    short_term, _ = memory()
    await short_term.append(CHAT, ChatMessage("user", "عايزة شنطة"))
    await short_term.append(CHAT, ChatMessage("assistant", "حاضر ✨"))

    assert await short_term.recent(CHAT, 10) == [
        ChatMessage("user", "عايزة شنطة"),
        ChatMessage("assistant", "حاضر ✨"),
    ]


async def test_list_is_trimmed_to_the_newest_n() -> None:
    short_term, _ = memory(max_messages=3)
    for i in range(5):
        await short_term.append(CHAT, ChatMessage("user", f"m{i}"))

    assert [m.content for m in await short_term.recent(CHAT, 10)] == ["m2", "m3", "m4"]


async def test_recent_returns_only_the_last_limit() -> None:
    short_term, _ = memory(max_messages=10)
    for i in range(5):
        await short_term.append(CHAT, ChatMessage("user", f"m{i}"))

    assert [m.content for m in await short_term.recent(CHAT, 2)] == ["m3", "m4"]


async def test_ttl_is_set_and_renewed_on_every_write() -> None:
    short_term, client = memory(ttl=60)
    await short_term.append(CHAT, ChatMessage("user", "a"))
    await client.expire(f"chat:{CHAT}:history", 5)  # pretend time passed

    await short_term.append(CHAT, ChatMessage("user", "b"))

    assert await client.ttl(f"chat:{CHAT}:history") > 5


async def test_clear_removes_the_history() -> None:
    short_term, _ = memory()
    await short_term.append(CHAT, ChatMessage("user", "a"))
    await short_term.clear(CHAT)

    assert await short_term.recent(CHAT, 10) == []
