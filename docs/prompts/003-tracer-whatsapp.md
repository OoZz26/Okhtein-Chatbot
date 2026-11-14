Implement issue **003 — Tracer bullet over WhatsApp**.

First read `docs/prompts/_common.md` and `docs/issues/003-tracer-whatsapp.md`. Check the current
WAHA docs (https://waha.devlike.pro/docs/) for the exact webhook payload, HMAC header, and the
`sendText` / `sendSeen` endpoints — do not guess field names.

Suggested design:
- `app/domain/ports.py`: `MessagingGateway` (`send_text(chat_id, text)`, `mark_seen(...)`) and
  an `IncomingMessage` domain model (message id, chat id, text, sender display name, from_me,
  is_group, has_media).
- `app/infra/whatsapp/waha_gateway.py`: Adapter over WAHA's REST API with `httpx.AsyncClient`
  and the `X-Api-Key` header.
- `app/infra/whatsapp/waha_mapper.py`: maps WAHA's webhook JSON to `IncomingMessage` (keeps
  WAHA's format out of the rest of the app).
- `app/api/webhook.py`: verifies the HMAC/secret, maps the payload, returns 200 immediately and
  schedules processing (FastAPI `BackgroundTasks` is enough for now — 008 adds debounce).
- `app/services/incoming_message_service.py`: filter rules (from_me, groups, status@broadcast,
  media), idempotency via an `IdempotencyStore` port (Redis `SET NX` with TTL adapter), then
  calls the existing chat service and sends the reply through the gateway.
- Configure WAHA in `docker-compose.yml` to post webhooks to the app on the host
  (`http://host.docker.internal:8000/webhook`), events `message`.
- Tests: fake gateway records sends; duplicate event → one send; ignored message types; bad
  signature → 401; slow FakeLLM → webhook still fast.

Help me connect the session: tell me how to open the WAHA dashboard and scan the QR with the
**test** phone, then verify with a real message. Never message anyone except the test number.
