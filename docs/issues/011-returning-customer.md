# 011 — Returning customer

**Status:** ✅ Done (code) · ⏳ optional phone check, see docs/morning-checklist.md · **Estimate:** 15 min

## What to build

The bot remembers people across visits. When a session ends, what was learned (the profile
slots from 005 plus a 2-line LLM summary and products shown) is merged into the customer's
long-term profile in Postgres. When the customer comes back after the session expired, the agent
receives that profile and greets them naturally — "أهلاً تاني 🤍 لسه بتحبي الحاجات الجريئة؟"
(welcome back, still into bold pieces?) — without being creepy or assuming nothing has changed.
If the customer says their taste changed, the profile is updated.

## Acceptance criteria

- [x] After the session expires (or Redis is flushed), a new message gets a reply that naturally uses a remembered preference (test / eval)
- [x] The long-term profile contains the learned slots and a short summary (bounded length)
- [x] New information overrides old preferences (unit test)
- [x] Products already shown are not pushed again unless relevant
- [x] Unit tests with fakes; no LLM call needed except for the summary (faked in tests)

## Blocked by

- 005 — Discovery & friendliness

## Notes

- **When "welcome back" happens:** on a genuinely new session (the short-term TTL has passed). A Redis flush *inside* a live session keeps the conversation (issue 004 reloads it from Postgres), so the bot just continues. What the flush must not lose is the profile: learned slots and shown products are written to Postgres after **every turn** (no LLM), and only the 2-line summary needs the LLM, at the start of the next session.
- **Storage:** `customers.profile` (JSONB), added with an idempotent `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` at startup because `create_all` never alters existing tables (Alembic is a "Later" item). The profile records `summarized_until`, so each visit is summarised once and only what is new is summarised next time.
- **Failure behaviour:** if the summarising LLM call fails, the customer is still welcomed back from the stored slots; the chat is never blocked.
- **Eval:** `returning_customer` scenario (visit 1 about bold gold rings, session expired, visit 2 just says "hi") passes with the real summariser.
