Implement issue **011 — Returning customer**.

First read `docs/prompts/_common.md` and `docs/issues/011-returning-customer.md`.

Suggested design:
- Domain: `LongTermProfile` (preference slots, summary, products shown, updated_at) with a pure
  merge rule (newer information wins; summary bounded in length).
- `ProfileSummarizer` port: an LLM call that turns a finished session (messages + session profile)
  into a 2-line summary; fake in tests.
- When to persist: at the start of a new session, if the previous session has not been
  summarised yet, summarise it from Postgres messages and merge into `customers.profile` (JSONB).
  This avoids needing Redis expiry events.
- The agent receives the long-term profile in its prompt context with guidance to use it
  naturally ("welcome back"), not to recite it, and to update it if the customer says their
  taste changed.
- Tests: merge rules, summarise-on-new-session flow with fakes, products-shown not repeated.
- Add an eval scenario: session 1 (likes bold gold pieces) → flush session → session 2 greeting.

Demo: chat, flush Redis with `redis-cli FLUSHALL`, message again, show the "welcome back" reply.
