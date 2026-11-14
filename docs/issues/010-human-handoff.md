# 010 — Human handoff

**Status:** ⚪ Todo · **Estimate:** 20 min

## What to build

Some conversations belong to a person. Each chat has a state:

```
BOT_ACTIVE ──(handoff)──► HANDED_OFF ──(release / timeout)──► BOT_ACTIVE
```

- The agent hands off (with a reason and a 1–3 line summary for staff) when the customer asks for
  a human, wants to track / change / cancel an order, complains, is angry, or asks for bespoke work
  or discounts it cannot confirm.
- The customer is told warmly that a team member will reply in this chat.
- The team is notified (log + optional WhatsApp message to a configurable staff number).
- While handed off, the bot stays silent but still stores the messages.
- If staff reply manually from the business phone, the chat is treated as handed off.
- Release by a simple admin endpoint or automatically after a configurable number of hours.
- State lives in Postgres (source of truth), cached for fast checks.

## Acceptance criteria

- [ ] "Where is my order?" and an angry message trigger handoff (eval scenarios)
- [ ] After handoff the bot sends nothing, but messages are still stored (test)
- [ ] A manual staff reply from the business phone pauses the bot for that chat (test)
- [ ] Release (admin endpoint or timeout) makes the bot answer again (test)
- [ ] Handoff reason and summary are stored and included in the staff notification
- [ ] State transitions are explicit and invalid transitions are rejected (unit test)

## Blocked by

- 003 — Tracer bullet over WhatsApp
- 004 — Bot remembers the conversation
