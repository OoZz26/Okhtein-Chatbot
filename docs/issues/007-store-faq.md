# 007 — Store FAQ answers

**Status:** ⚪ Todo · **Estimate:** 10 min

## What to build

The bot answers store questions (returns, refunds, changing or cancelling an order, about the
brand) **only** from the store knowledge file the owner can edit. When the answer is not there
(e.g. shipping fees, cash on delivery — still TODO for the owner), the bot says so kindly and
offers to connect a team member. It never invents policies, numbers or contact details.

The knowledge reaches the agent through a store-info port (file adapter today, could be a CMS
later). Editing the file changes answers without touching code.

## Acceptance criteria

- [ ] "Can I return an item?" → correct 14-day policy, in the customer's language
- [ ] "How much is shipping?" → no invented number; offers a team member
- [ ] Editing the knowledge file changes the answer after a reload, no code change
- [ ] Eval scenarios cover a known answer and an unknown answer
- [ ] Unit test with a fake store-info source

## Blocked by

- 002 — Tracer bullet: chat over HTTP
