"""Turns a finished session into a short summary, using the LLM through its port."""

import re
from collections.abc import Sequence

from app.domain.discovery import CustomerProfile
from app.domain.models import ChatMessage
from app.domain.ports import LLMProvider

URL = re.compile(r"https?://\S+")
MAX_TRANSCRIPT_MESSAGES = 40

INSTRUCTIONS = (
    "You write notes about a customer of OKHTEIN, an Egyptian luxury accessories store, for the next time "
    "they chat with the store's assistant. Read the conversation and write AT MOST TWO short lines, in "
    "English, about what this customer likes and is looking for (styles, colours, occasions, budget, who "
    "they shop for) and what happened (for example, which kind of products they liked or rejected). "
    "Plain facts only: no greetings, no advice, nothing the customer did not say. "
    "If nothing about their taste can be learned, answer with an empty line."
)


class LLMProfileSummarizer:
    def __init__(self, llm: LLMProvider) -> None:
        self._llm = llm

    async def summarize(self, messages: Sequence[ChatMessage], known: CustomerProfile) -> str:
        transcript = "\n".join(
            f"{'Customer' if m.role == 'user' else 'Assistant'}: {URL.sub('', m.content).strip()}"
            for m in messages[-MAX_TRANSCRIPT_MESSAGES:]
        )
        notes = f"Already known preferences: {known.summary()}\n\n" if known.known() else ""
        response = await self._llm.chat(
            [ChatMessage("system", INSTRUCTIONS), ChatMessage("user", f"{notes}Conversation:\n{transcript}")]
        )
        return response.content.strip()
