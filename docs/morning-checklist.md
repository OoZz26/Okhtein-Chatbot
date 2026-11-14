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
