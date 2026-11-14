Implement issue **004 — Bot remembers the conversation**.

First read `docs/prompts/_common.md` and `docs/issues/004-conversation-memory.md`.

Suggested design:
- Ports in the domain: `ShortTermMemory` (append, recent(n), clear, ttl renew) and
  `ConversationStore` (save message, recent messages, upsert customer).
- `app/infra/cache/redis_short_term.py`: Redis list per chat (`chat:{id}:history`), `RPUSH` +
  `LTRIM` to N, `EXPIRE` renewed on every write (sliding TTL). Messages serialised as JSON.
- `app/infra/db/`: SQLAlchemy 2 async models `customers` and `messages`, a session factory, and
  `PostgresConversationStore`. Create tables with `metadata.create_all` at startup for now
  (Alembic is a "Later" item unless time allows).
- `app/services/memory_service.py` — **Facade**: `record(chat_id, message)` = write-through to
  Postgres first, then Redis; `context(chat_id)` = Redis, and on a miss reload the last N from
  Postgres and refill Redis (**cache-aside**). Also exposes `is_new_session`.
- Wire it into the chat service so the agent receives history; keep the agent unaware of storage.
- Tests: unit with fakeredis + an in-memory `ConversationStore` fake; integration tests (marked
  `@pytest.mark.integration`) against the Docker services, including "flush Redis, context still there".

Demo: two messages over WhatsApp or `/chat` ("I want a clutch" → "show me a cheaper one"),
then `docker compose exec redis redis-cli FLUSHALL`, send a third message, and show the bot still
knows the context. Show the rows with `docker compose exec postgres psql ...`.
