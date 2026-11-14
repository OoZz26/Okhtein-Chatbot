# 011 — Returning customer

**Status:** ⚪ Todo · **Estimate:** 15 min

## What to build

The bot remembers people across visits. When a session ends, what was learned (the profile
slots from 005 plus a 2-line LLM summary and products shown) is merged into the customer's
long-term profile in Postgres. When the customer comes back after the session expired, the agent
receives that profile and greets them naturally — "أهلاً تاني 🤍 لسه بتحبي الحاجات الجريئة؟"
(welcome back, still into bold pieces?) — without being creepy or assuming nothing has changed.
If the customer says their taste changed, the profile is updated.

## Acceptance criteria

- [ ] After the session expires (or Redis is flushed), a new message gets a reply that naturally uses a remembered preference (test / eval)
- [ ] The long-term profile contains the learned slots and a short summary (bounded length)
- [ ] New information overrides old preferences (unit test)
- [ ] Products already shown are not pushed again unless relevant
- [ ] Unit tests with fakes; no LLM call needed except for the summary (faked in tests)

## Blocked by

- 005 — Discovery & friendliness
