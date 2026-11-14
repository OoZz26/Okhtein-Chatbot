from datetime import UTC, datetime

from fakeredis import FakeAsyncRedis

from app.domain.handoff import ChatMode, HandoffState
from app.infra.cache.redis_handoff_cache import CachedHandoffStore
from app.infra.whatsapp.waha_mapper import map_webhook
from tests.fakes import InMemoryHandoffStore

NOW = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
CHAT = "201001234567@c.us"


class CountingStore(InMemoryHandoffStore):
    def __init__(self) -> None:
        super().__init__()
        self.reads = 0

    async def get(self, chat_id: str) -> HandoffState:
        self.reads += 1
        return await super().get(chat_id)


class TestCachedHandoffStore:
    async def test_the_second_read_comes_from_redis_not_the_database(self) -> None:
        inner = CountingStore()
        store = CachedHandoffStore(inner, FakeAsyncRedis(decode_responses=True), ttl_seconds=60)

        await store.get(CHAT)
        await store.get(CHAT)

        assert inner.reads == 1

    async def test_saving_updates_both_and_round_trips_the_state(self) -> None:
        inner = CountingStore()
        store = CachedHandoffStore(inner, FakeAsyncRedis(decode_responses=True), ttl_seconds=60)
        state = HandoffState().handoff("complaint", "Bag damaged: عايزة حقي", NOW)

        await store.save(CHAT, state)

        assert inner.states[CHAT] == state  # the source of truth has it
        assert await store.get(CHAT) == state  # and the cache returns the identical state
        assert inner.reads == 0

    async def test_losing_redis_loses_nothing(self) -> None:
        inner = CountingStore()
        client = FakeAsyncRedis(decode_responses=True)
        store = CachedHandoffStore(inner, client, ttl_seconds=60)
        await store.save(CHAT, HandoffState().handoff("complaint", "x", NOW))

        await client.flushall()

        assert (await store.get(CHAT)).mode == ChatMode.HANDED_OFF  # rebuilt from the database

    async def test_release_is_cached_too(self) -> None:
        inner = CountingStore()
        store = CachedHandoffStore(inner, FakeAsyncRedis(decode_responses=True), ttl_seconds=60)
        await store.save(CHAT, HandoffState().handoff("c", "x", NOW))
        await store.save(CHAT, HandoffState())

        assert not (await store.get(CHAT)).is_handed_off


class TestMapperForPhoneMessages:
    def event(self, name: str, **payload: object) -> dict[str, object]:
        base = {"id": "true_x_1", "to": CHAT, "from": "201000000000@c.us", "fromMe": True, "body": "On it!"}
        return {"event": name, "payload": {**base, **payload}}

    def test_a_message_typed_on_the_phone_is_marked_from_phone(self) -> None:
        message = map_webhook(self.event("message.any", source="app"))

        assert message is not None
        assert message.from_me and message.from_phone
        assert message.chat_id == CHAT  # the customer's chat, not our own number

    def test_a_message_sent_through_our_api_is_not_from_phone(self) -> None:
        message = map_webhook(self.event("message.any", source="api"))

        assert message is not None
        assert message.from_me and not message.from_phone

    def test_incoming_messages_in_message_any_are_skipped_to_avoid_double_handling(self) -> None:
        assert map_webhook(self.event("message.any", fromMe=False, source="app")) is None
