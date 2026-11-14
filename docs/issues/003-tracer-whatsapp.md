# 003 — Tracer bullet over WhatsApp

**Status:** ⚪ Todo · **Estimate:** 30 min

## What to build

The same flow as 002, but the customer uses WhatsApp. A message sent from a phone to the **test**
WhatsApp number reaches our app through a WAHA webhook, goes through the same conversation
service, and the reply is delivered back to the same chat. This brings the riskiest integration
in early.

Behaviour:
- A messaging-gateway port with a WAHA adapter (send text, mark as seen). The chat service does
  not know WAHA exists.
- The webhook is authenticated (shared secret / WAHA webhook HMAC) and rejects anything else.
- Ignored: our own outgoing messages, group chats, status broadcasts, and non-text messages
  (non-text gets a kind "I can only read text for now" reply).
- Idempotent: WAHA may deliver the same event twice; each message id is processed once.
- The webhook acknowledges immediately and processes the message in the background, so WAHA never
  waits on the LLM.
- The WAHA session is connected once by QR scan and survives restarts.

## Acceptance criteria

- [ ] Manual demo: message from your phone → bot reply on your phone
- [ ] The same webhook event delivered twice produces exactly one reply (test with a fake gateway)
- [ ] Own messages, group messages and status broadcasts produce no reply (tests)
- [ ] Unauthenticated webhook calls are rejected (test)
- [ ] The webhook responds in well under 200 ms regardless of LLM latency (test with a slow `FakeLLM`)
- [ ] Restarting Docker does not require scanning the QR code again
- [ ] The conversation service is unit-tested with a fake messaging gateway, no WAHA needed

## Blocked by

- 002 — Tracer bullet: chat over HTTP
