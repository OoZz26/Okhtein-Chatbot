from app.domain.models import ChatMessage
from tests.fakes import MemoryRig, make_memory

CHAT = "201001234567@c.us"


def user(text: str) -> ChatMessage:
    return ChatMessage("user", text)


async def record_exchange(rig: MemoryRig, question: str, answer: str) -> None:
    await rig.service.record(CHAT, user(question), "Sara")
    await rig.service.record(CHAT, ChatMessage("assistant", answer))


async def test_record_writes_through_to_both_stores() -> None:
    rig = make_memory()
    await record_exchange(rig, "hi", "hello!")

    assert [m.content for _, m, _ in rig.store.rows] == ["hi", "hello!"]  # Postgres side
    assert [m.content for m in await rig.service.context(CHAT)] == ["hi", "hello!"]  # Redis side
    assert rig.store.customers[CHAT] == "Sara"


async def test_flushing_redis_keeps_the_context_cache_aside() -> None:
    rig = make_memory()
    await record_exchange(rig, "I want a clutch", "Here is one")
    await rig.redis.flushall()

    context = await rig.service.context(CHAT)

    assert [m.content for m in context] == ["I want a clutch", "Here is one"]
    assert await rig.redis.llen(f"chat:{CHAT}:history") == 2  # and Redis was refilled


async def test_at_most_n_messages_are_returned() -> None:
    rig = make_memory(history_limit=4)
    for i in range(10):
        await rig.service.record(CHAT, user(f"message {i}"))

    from_redis = await rig.service.context(CHAT)
    await rig.redis.flushall()
    from_postgres = await rig.service.context(CHAT)

    assert [m.content for m in from_redis] == [f"message {i}" for i in range(6, 10)]
    assert from_postgres == from_redis
    assert len(rig.store.rows) == 10  # the source of truth keeps everything


async def test_a_new_session_starts_after_the_ttl() -> None:
    rig = make_memory(ttl_seconds=3600)
    await record_exchange(rig, "hi", "hello!")
    assert not await rig.service.is_new_session(CHAT)

    await rig.redis.flushall()  # Redis expired too
    rig.clock.advance(hours=2)

    assert await rig.service.is_new_session(CHAT)
    assert await rig.service.context(CHAT) == []


async def test_the_session_stays_alive_within_the_ttl() -> None:
    rig = make_memory(ttl_seconds=3600)
    await record_exchange(rig, "hi", "hello!")
    await rig.redis.flushall()
    rig.clock.advance(minutes=30)

    assert not await rig.service.is_new_session(CHAT)


async def test_unknown_chat_is_a_new_session() -> None:
    assert await make_memory().service.is_new_session("someone-new@c.us")
