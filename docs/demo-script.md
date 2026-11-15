# Demo script

Five conversations to run live from the **test phone** (an allowed number) to the linked WhatsApp number. Each
takes 1-2 minutes. Replies take 10-40 seconds because the real LLM is working: "typing..." shows meanwhile.

**Before you start**

```bash
docker compose up -d && python scripts/check_infra.py          # all ✅
python scripts/build_embeddings.py                              # "embedded 0, unchanged 212" is fine
uvicorn app.main:app --host 0.0.0.0 --port 8000                 # leave running; watch its log
```

Never message anyone but the test number. To reset a demo between runs, use a different customer (or flush
Redis: `docker compose exec redis redis-cli FLUSHALL`; the conversation reloads from Postgres, see demo 5).

---

## 1. Vague request: discovery, then picture cards

| You send | Expected |
|---|---|
| `عايزة شنطة` | ONE short, warm question (occasion? everyday or evening?), **in English** with one kind line that Nour chats in English for now, **no products yet** |
| `لسهرة وميزانيتي 60 ألف` | A short warm message, then **2-3 image cards**, each with name, price and a real link, every price within 60,000 EGP |

Shows: discovery before searching, language mirroring, hybrid search, image cards, budget respected.
In the log: `llm_call provider=openai ... outcome=ok`, `chat_reply outcome=ok stage=recommend`.

## 2. Memory: "a cheaper one"

Continue demo 1 (or ask for a black clutch first), then send `show me a cheaper one` (English).

Expected: she understands what "one" refers to, replies in English, and recommends cheaper related products
(not the same ones). Optionally flush Redis in between: `docker compose exec redis redis-cli FLUSHALL`, then
ask `which one was the first you showed me?`: the context comes back from Postgres.

Shows: two-tier memory (write-through, cache-aside), language switching.

## 3. Store FAQ: known and unknown

| You send | Expected |
|---|---|
| `ينفع أرجع حاجة لو اشتريتها؟` | Arabic answer with the real policy: **14 days** from delivery, unused with tags and packaging, refund to the original payment method |
| `الشحن بكام؟` | **No invented number.** Says kindly that she does not have it and a team member will confirm |

Shows: answers only from `data/knowledge.md`. Try editing that file (change "14 days" to "30 days"), ask again
without restarting: the answer changes.

## 4. Handoff and release

| You send | Expected |
|---|---|
| `Where is my order? I ordered a week ago` | Warm apology, says a team member will reply in this chat. Log: `handoff chat=… reason=order tracking`. If `STAFF_PHONE` is set, that number gets a 🔔 alert with the reason and summary |
| `hello? anyone there?` | **Silence**: no reply, no typing indicator (the message is still stored) |

Release the chat (replace the id with your test number's chat id, e.g. `201001234567@c.us`):

```bash
curl -X POST "http://127.0.0.1:8000/admin/chats/201001234567@c.us/release" -H "X-Admin-Key: $ADMIN_API_KEY"
```

Then send `hi`: she answers again. **Staff takeover:** type a reply to the customer yourself from the business
phone; the bot must stay silent for that chat from then on (this relies on WAHA marking phone-typed messages
`source: app`; see the morning checklist if it does not).

## 5. Returning customer

Set `SESSION_TTL_SECONDS=60` in `.env` and restart the app. Chat as a new customer: `I love bold gold pieces,
show me a ring`, then `I like the first one`. Wait 70 seconds and send `hi`.

Expected: a short **welcome back** that mentions your gold taste once and asks whether it still fits, without
reciting your history or pushing the same ring again. Check what is remembered:

```bash
docker compose exec postgres psql -U okhtein -d okhtein -c "select chat_id, profile from customers where profile is not null"
```

Restore `SESSION_TTL_SECONDS=86400` afterwards.

---

## Bonus: it never fails silently

Temporarily set `OPENAI_API_KEY` to an invalid value (and a valid `OPENROUTER_API_KEY`), restart, and send a
message: the log shows `llm_provider_failed provider=openai outcome=fallback` then `llm_call provider=openrouter`,
and the customer still gets an answer. With both keys invalid she sends a warm "one moment" message and the chat
is flagged in the `follow_ups` table. **Restore your real key afterwards.**
