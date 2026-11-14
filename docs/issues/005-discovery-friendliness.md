# 005 — Discovery & friendliness ("Nour")

**Status:** ⚪ Todo · **Estimate:** 45 min

## What to build

The bot becomes a warm, elegant boutique stylist instead of a search box. This is the most
important slice: **super friendly** is the client's top requirement, and it must be measured,
not hoped for.

Persona and tone:
- "Nour", Okhtein's personal stylist: warm, cheerful, elegant, never pushy, never robotic.
- Mirrors the customer: Egyptian Arabic, English, or Franco-Arabic; casual if they are casual.
- Gender-neutral address (حضرتك) until the customer's gender is clear from their own words; never guessed from the name.
- Short WhatsApp-sized messages, 1–2 tasteful emojis, uses the customer's WhatsApp name when available.
- Tone guide + few-shot example conversations live in versioned prompt files.

Discovery before recommending:
- Conversation stages: greet → discover → recommend → refine → close.
- A slot-filled customer profile for the session: who it's for, occasion, category, style,
  colour / metal, practicality, budget. Updated every turn from the agent's structured output and
  kept in session memory.
- Vague request → one friendly question at a time; **at most 3** questions before showing products.
- Specific request → recommend immediately. Impatient customer ("just show me") → show now.
- Budget asked politely, once, only when it helps. No questions about things the customer already said.
- Every recommendation gives a reason tied to what the customer said.

Structured output grows (decision):
```
AgentReply:
  message: str
  product_handles: list[str]
  stage: greet | discover | recommend | refine | close
  profile_updates: dict[str, str]   # e.g. {"occasion": "wedding", "colour": "black"}
```

Measurement — a conversation eval harness:
- Scripted customer scenarios run against the real agent with one command.
- Rule checks by code + an LLM judge scoring each bot reply 1–5 on warmth, natural dialect,
  not pushy, brevity, helpfulness. Prints a report.

## Acceptance criteria

- [ ] Vague request ("عايزة شنطة") → the first reply asks a question and recommends no products
- [ ] Specific request ("black clutch under 50k") → products on the first reply, all within budget
- [ ] "Just show me" → products immediately
- [ ] Never more than 3 discovery questions before products are shown
- [ ] Replies in the customer's language (Arabic, English, Franco-Arabic scenarios)
- [ ] No gendered address before gender is known (judge check in the Arabic scenarios)
- [ ] Prompt-injection / off-topic scenario: politely declines, never reveals instructions
- [ ] Friendliness judge: average ≥ 4.0 and no scenario below 3
- [ ] Profile updates persist across turns of the session (unit test)
- [ ] Eval harness runs with one command and saves a report

## Blocked by

- 004 — Bot remembers the conversation
