Implement issue **010 — Human handoff**.

First read `docs/prompts/_common.md` and `docs/issues/010-human-handoff.md`.

Suggested design:
- Domain: `ChatMode` (`BOT_ACTIVE`, `HANDED_OFF`) with an explicit **State machine**
  (`handoff(reason, summary)`, `release()`; invalid transitions raise a domain error).
- A `handoff_to_human` tool registered in the `ToolRegistry` (reason + summary). When the agent
  calls it, the reply tells the customer warmly that a team member will answer here.
- `HandoffStore` port: Postgres table `handoffs` (chat id, mode, reason, summary, created_at,
  released_at) as source of truth, Redis cache for the fast "is handed off?" check on every message.
- `StaffNotifier` port: log adapter + optional WhatsApp adapter sending a summary to
  `Settings.staff_phone` (only if configured; never any other number).
- Incoming-message service: if handed off → store the message, do not reply. If a `from_me`
  message arrives in a customer chat that was **not** sent by the bot (track ids of bot-sent
  messages), switch the chat to handed off.
- Release: `POST /admin/chats/{chat_id}/release` protected by an admin API key from `Settings`,
  plus auto-release after `Settings.handoff_timeout_hours`.
- Add eval scenarios: "where is my order?", angry complaint, "can I talk to a person?".

Demo: trigger a handoff from the phone, show the bot goes silent, release via the admin endpoint,
and show it answers again.
