from fakeredis import FakeAsyncRedis

from app.infra.cache.redis_idempotency import RedisIdempotencyStore


async def test_first_claim_wins_second_is_rejected() -> None:
    store = RedisIdempotencyStore(FakeAsyncRedis(), ttl_seconds=60)

    assert await store.claim("msg-1") is True
    assert await store.claim("msg-1") is False
    assert await store.claim("msg-2") is True


async def test_claims_expire_after_the_ttl() -> None:
    client = FakeAsyncRedis()
    store = RedisIdempotencyStore(client, ttl_seconds=60)
    await store.claim("msg-1")

    assert 0 < await client.ttl("idem:msg-1") <= 60
