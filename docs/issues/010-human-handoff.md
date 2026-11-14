# 010 — Human handoff

**Status:** ✅ Done (code) · ⏳ manual phone check pending, see docs/morning-checklist.md · **Estimate:** 20 min

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

- [x] "Where is my order?" and an angry message trigger handoff (eval scenarios)
- [x] After handoff the bot sends nothing, but messages are still stored (test)
- [x] A manual staff reply from the business phone pauses the bot for that chat (test)
- [x] Release (admin endpoint or timeout) makes the bot answer again (test)
- [x] Handoff reason and summary are stored and included in the staff notification
- [x] State transitions are explicit and invalid transitions are rejected (unit test)

## Blocked by

- 003 — Tracer bullet over WhatsApp
- 004 — Bot remembers the conversation

## Notes

- The agent hands off through two extra fields in its structured reply (`handoff_reason`, `handoff_summary`) instead of a tool: tools here are stateless and shared across chats, so a tool would need hidden per-turn state. Same behaviour, one fewer LLM round trip.
- Staff replies from the business phone are detected with WAHA's `source` field (`app` = typed on the phone, `api` = sent by our own API calls) on `message.any` events. ⏳ needs manual check on the real phone (see the morning checklist).
