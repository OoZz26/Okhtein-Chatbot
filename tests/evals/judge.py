"""LLM-as-judge: scores each bot reply 1-5 on friendliness dimensions, using a written rubric."""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.domain.errors import LLMError
from app.domain.models import ChatMessage
from app.domain.ports import LLMProvider
from tests.evals.checks import BotTurn

DIMENSIONS = ("warmth", "dialect", "not_pushy", "brevity", "helpfulness")

RUBRIC = (Path(__file__).parent / "rubric.md").read_text(encoding="utf-8")

JUDGE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "replies": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    **{dimension: {"type": "integer"} for dimension in DIMENSIONS},
                    "reason": {"type": "string"},
                },
                "required": [*DIMENSIONS, "reason"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["replies"],
    "additionalProperties": False,
}


@dataclass(frozen=True)
class ReplyScore:
    scores: dict[str, int]
    reason: str

    @property
    def average(self) -> float:
        return sum(self.scores.values()) / len(self.scores)


class Judge:
    def __init__(self, llm: LLMProvider) -> None:
        self._llm = llm

    async def score(self, scenario_note: str, turns: list[BotTurn]) -> list[ReplyScore]:
        transcript = "\n\n".join(f"Customer: {t.customer}\nAssistant: {t.reply}" for t in turns)
        prompt = f"Scenario note: {scenario_note}\n\nConversation:\n\n{transcript}"
        response = await self._llm.chat(
            [ChatMessage("system", RUBRIC), ChatMessage("user", prompt)], response_schema=JUDGE_SCHEMA
        )
        entries = json.loads(response.content)["replies"]
        if len(entries) != len(turns):
            raise LLMError(f"Judge returned {len(entries)} scores for {len(turns)} replies")
        return [
            ReplyScore({d: min(5, max(1, int(e[d]))) for d in DIMENSIONS}, str(e["reason"])) for e in entries
        ]
