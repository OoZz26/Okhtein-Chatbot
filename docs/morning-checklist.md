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

### 006: Hybrid retrieval with pgvector (done tonight, nothing manual)
Already done and verified: the Postgres container now runs `pgvector/pgvector:0.8.7-pg17-trixie` (your data was backed up first and is intact), the 212 products are embedded (`python scripts/build_embeddings.py`; a second run embeds 0), and the app uses `RETRIEVER=hybrid`. Optional: `python scripts/eval_retrieval.py` prints hit@3 for keyword/vector/hybrid. If you ever add products, re-run `python scripts/build_embeddings.py` (it only embeds what changed). If pgvector or embeddings are unavailable the bot silently falls back to keyword search (logged as `retrieval_fallback`).

### 011: Returning customer (optional phone check)
Tested with fakes, Postgres integration tests and a real-LLM eval scenario. To see it on your phone, you need a session that really expires:
1. In `.env` set `SESSION_TTL_SECONDS=60`, restart the app, then chat from the second phone (e.g. `I love bold gold rings, show me one`, then `I like the first one`).
2. Wait 70 seconds, then send `hi`. Expect a short "welcome back" that mentions your gold taste and asks if it still fits.
3. Restore `SESSION_TTL_SECONDS=86400` and restart.
Note: `redis-cli FLUSHALL` between messages will NOT trigger "welcome back" (the conversation is reloaded from Postgres, by design from issue 004). It does keep the learned preferences. Check the stored profile with:
```bash
docker compose exec postgres psql -U okhtein -d okhtein -c "select chat_id, profile from customers where profile is not null"
```

### 012: Load test (nothing manual; optional re-run)
Done and measured overnight (results in `docs/load-test-results.md`): webhook p95 **23 ms**, 0 failures at 100 simulated customers; 160/160 bursts got exactly one reply; 10 real-LLM conversations ran without errors, retries or fallbacks (replies took 20-40 s, all LLM time). To re-run: `python scripts/run_load_test.py` (isolated app on port 8001, cleans up after itself). Add nothing to `.env`; load mode is off by default (`LOAD_TEST_MODE=false`) and is refused when `ENVIRONMENT=production`.
