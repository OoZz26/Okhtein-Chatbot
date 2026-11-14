# 013 — README & demo

**Status:** ✅ Done (code and docs) · ⏳ demo script on the phone pending, see docs/morning-checklist.md · **Estimate:** 10 min

## What to build

Anyone (the client, a future developer, you in three months) can understand, run and demo the bot.

- README: what it does, architecture diagram (layers + ports), setup from zero (Docker, `.env`,
  QR scan), how to run, test, run evals and the load test, and a table mapping each design
  pattern to where it lives in the code.
- A short demo script: 4–5 conversations that show discovery, recommendation with image cards,
  memory, FAQ and handoff.
- Final cleanup: dead code removed, `.env.example` complete, all checks green.

## Acceptance criteria

- [x] Following the README on a fresh clone gives a working bot
- [x] Every design pattern in the table points to real code
- [x] `ruff`, `mypy`, `pytest` green; latest eval and load-test results linked
- [ ] Demo script runs end-to-end on the test number — ⏳ needs manual check (phone)

## Blocked by

- All previous slices (001–012)
