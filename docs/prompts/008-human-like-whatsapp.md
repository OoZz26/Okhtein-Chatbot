Implement issue **008 — Human-like WhatsApp experience**.

First read `docs/prompts/_common.md` and `docs/issues/008-human-like-whatsapp.md`. Check the WAHA
docs for `sendImage`, `startTyping` / `stopTyping` (image sending is in the free Core edition;
prefer JPEG URLs — Shopify CDN URLs can request JPEG via the `format=jpg` / `&width=` params).

Suggested design:
- `app/services/debouncer.py` — **Producer/Consumer + debounce**: the webhook appends to a Redis
  buffer (`chat:{id}:buffer`) and (re)schedules processing; the consumer waits until N seconds of
  quiet, drains the buffer atomically, and passes the combined text to the chat service.
  Inject a `Clock`/sleep function so tests do not really wait.
- A `Lock` port with a Redis adapter (`SET lock:chat:{id} NX PX`, token-checked release) —
  **distributed lock**, so a chat never has two replies in flight.
- `ReplySender` service: typing indicator → delay proportional to length (capped) → split into
  bubbles → send text → send product cards (image + caption: name, price, link) → fallback to a
  text link on image failure.
- `RateLimiter` port (Redis token bucket or fixed window) applied to all outgoing sends.
- Extend the `MessagingGateway` port with `send_image` and typing methods; update the WAHA adapter
  and the fake gateway.
- Tests: burst → one reply; racing bursts → no interleaving; image failure → text fallback;
  rate limit enforced.

Demo on the test phone: send three quick messages, show one reply with typing, and product cards.
