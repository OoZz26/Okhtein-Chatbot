from fakeredis import FakeAsyncRedis

from app.domain.discovery import CustomerProfile, SessionState
from app.domain.models import ConversationStage
from app.infra.cache.redis_session_store import RedisSessionStore


async def test_unknown_chat_gets_a_fresh_state() -> None:
    store = RedisSessionStore(FakeAsyncRedis(decode_responses=True), ttl_seconds=60)

    assert await store.load("new-chat") == SessionState()


async def test_state_round_trips_including_arabic_profile_values() -> None:
    store = RedisSessionStore(FakeAsyncRedis(decode_responses=True), ttl_seconds=60)
    state = SessionState(
        ConversationStage.REFINE,
        CustomerProfile(occasion="فرح", colour="gold"),
        2,
        ("clutch-a", "ring-b"),
        awaiting_answer=True,
        dodged_questions=1,
        greet_turns=1,
    )

    await store.save("chat-1", state)

    assert await store.load("chat-1") == state


async def test_the_session_expires_with_the_same_ttl_as_history() -> None:
    client = FakeAsyncRedis(decode_responses=True)
    store = RedisSessionStore(client, ttl_seconds=60)
    await store.save("chat-1", SessionState())

    assert 0 < await client.ttl("chat:chat-1:session") <= 60


async def test_a_session_saved_before_shown_products_existed_still_loads() -> None:
    client = FakeAsyncRedis(decode_responses=True)
    store = RedisSessionStore(client, ttl_seconds=60)
    await client.set("chat:old:session", '{"stage": "discover", "profile": {}, "questions_asked": 1}')

    state = await store.load("old")

    assert state.questions_asked == 1
    assert state.shown_products == ()
