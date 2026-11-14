# 004 — Bot remembers the conversation

**Status:** ⚪ Todo · **Estimate:** 30 min

## What to build

Multi-turn conversations. After a recommendation, the customer can say "show me a cheaper one" or
"the second one in gold?" and the bot understands, because it remembers the conversation.

Two-tier memory, hidden behind a memory facade so the agent never sees Redis or Postgres:
- **Long term (Postgres, source of truth):** every inbound and outbound message is stored, plus a
  customer record (chat id, WhatsApp display name, first/last seen).
- **Short term (Redis):** the last N messages of the current conversation, with a sliding TTL.
- **Write-through:** every message goes to both.
- **Cache-aside on read:** if Redis has nothing (expired, flushed or restarted), the recent
  messages are reloaded from Postgres and Redis is refilled. Losing Redis never loses context.
- Only the last N messages (default 20) are sent to the LLM.
- When the short-term TTL expires (default 24h of silence) the next message starts a new session.

## Acceptance criteria

- [ ] "Show me a cheaper one" after a recommendation returns cheaper related products (integration test or eval)
- [ ] Flushing Redis between two messages keeps the context (cache-aside works)
- [ ] Restarting the app keeps the context
- [ ] Every message appears in Postgres with chat id, role and timestamp
- [ ] At most N messages are sent to the LLM (unit test)
- [ ] After TTL expiry a new session starts (test with a short TTL)
- [ ] Unit tests use fakes (e.g. fakeredis + in-memory store); integration tests use the real Docker services
- [ ] The agent and conversation service depend only on the memory port, not on Redis/SQLAlchemy

## Blocked by

- 002 — Tracer bullet: chat over HTTP
