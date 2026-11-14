# Morning checklist

> This file is written and updated by the overnight build sessions. The summary at the top is filled in at the very end.

## Summary
_(written after the last slice)_

## Things that need you (manual checks)

Each item says what to do and what you should see. Nothing here was done overnight because it needs your phone, your accounts or your `.env`.

_(items are added below as slices finish)_

### 008: Human-like WhatsApp (needs your phone)
Start the stack first (see the commands at the top once the summary is written), then from a **second phone** (an allowed number) message the linked WhatsApp number:
1. **Burst:** send three quick messages in a row, e.g. `hi` / `I want a bag` / `for a wedding`. You should get **one** reply, about 4 seconds after your last message (`DEBOUNCE_SECONDS`), that addresses all three.
2. **Typing:** the chat should show "typing…" before the reply arrives.
3. **Cards:** ask for something specific (`a black clutch under 60000`). After the text you should receive **one image per product** with a caption: name, price and the real link. Tap a link to check it opens.
4. If images do not arrive but text links do, the image fallback worked (check `uvicorn.log` for `Image failed ... sending a text link`).
New `.env` settings: none are required (defaults are in `.env.example`: `LOCK_TTL_SECONDS`, `LOCK_WAIT_SECONDS`, `MAX_BUBBLES`, `TYPING_SECONDS_PER_CHAR`, `TYPING_MAX_DELAY_SECONDS`, `SEND_RATE_LIMIT_PER_MINUTE`).

### 010: Human handoff (needs your phone, one `.env` line, and a WAHA restart)
**One-time setup:** the compose file now subscribes WAHA to `message.any` events too (needed to notice staff replies). Recreate the WAHA container once; your WhatsApp session is kept in its volume (it survived this before):
```bash
docker compose up -d
```
Add to `.env` (both optional but needed for the checks below):
- `ADMIN_API_KEY=` any long random string (protects the release endpoint).
- `STAFF_PHONE=` the WhatsApp number (digits with country code) that should get handoff alerts. Leave it empty to only log them.

Checks (from the second phone, an allowed number):
1. Send `Where is my order?`. The bot should say a team member will reply here. If `STAFF_PHONE` is set, that number gets a "🔔 A customer needs a person" message with the reason and summary. The same line is in `uvicorn.log` (`handoff chat=… reason=…`).
2. Send another message: the bot must stay **silent** (no typing, no reply).
3. Release it (replace the chat id with the customer's, e.g. `201001234567@c.us`):
   ```bash
   curl -X POST "http://localhost:8000/admin/chats/201001234567@c.us/release" -H "X-Admin-Key: YOUR_ADMIN_API_KEY"
   ```
   Expect `{"chat_id": "...", "released": true}`, then the bot answers again.
4. **Staff takeover (the unverified one):** on the business phone (the linked WhatsApp), open that customer's chat and type a reply yourself. Then message again from the customer phone: the bot must stay silent. If it still answers, WAHA's `source` field is not `app` for phone-typed messages on your engine. Look at `docker compose logs waha` or the dashboard Event Monitor for a `message.any` event and tell the next session what `source` it carries.
5. Handoffs expire by themselves after `HANDOFF_TIMEOUT_HOURS` (default 12).

### Known flake (not a bug to fix tonight)
The conversation evals showed an occasional (~1 in 5 runs) reply in Arabic to an English customer in the `gift_for_mum` scenario. A prompt rule exists; the model (gpt-5-mini) still drifts rarely.
