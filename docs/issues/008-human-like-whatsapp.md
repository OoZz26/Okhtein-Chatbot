# 008 — Human-like WhatsApp experience

**Status:** ✅ Done (code) · ⏳ manual phone checks pending, see docs/morning-checklist.md · **Estimate:** 30 min

## What to build

The bot behaves like a person on WhatsApp, which also lowers the ban risk of an unofficial gateway.

- **Debounce:** customers often send bursts ("hi" / "I want a bag" / "for a wedding"). Messages
  are buffered per chat and the bot replies once, a few seconds after the last message, to all of them.
- **Per-chat lock:** never two replies being generated for the same chat at once.
- **Typing indicator** while the reply is generated, with a short delay proportional to the
  message length.
- **Bubbles:** long replies are split into 2–3 natural messages.
- **Product cards:** each recommended product is sent as an image (JPEG) with a caption of name,
  price and link, after the text. If the image fails, a text link is sent instead.
- **Send rate limit:** a configurable global cap on outgoing messages per minute.

## Acceptance criteria

- [x] 3 messages within 2 seconds → exactly one reply that addresses all of them (test with a fake gateway)
- [x] Two bursts racing on the same chat never produce interleaved or duplicate replies (test)
- [ ] Typing indicator visible on the phone before the reply (manual) — ⏳ needs manual check
- [ ] Recommended products arrive as image cards with name, price and working link (manual) — ⏳ needs manual check
- [x] Image send failure falls back to a text link (test)
- [x] Outgoing rate limit is configurable and enforced (test)

## Blocked by

- 003 — Tracer bullet over WhatsApp
- 004 — Bot remembers the conversation
