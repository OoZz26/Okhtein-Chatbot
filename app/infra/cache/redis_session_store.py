"""SessionStore adapter: the discovery state as one JSON value per chat, with the same sliding TTL."""

import json

from redis.asyncio import Redis

from app.domain.discovery import CustomerProfile, SessionState
from app.domain.models import ConversationStage


class RedisSessionStore:
    def __init__(self, client: Redis, ttl_seconds: int) -> None:
        self._client = client
        self._ttl_seconds = ttl_seconds

    @staticmethod
    def _key(chat_id: str) -> str:
        return f"chat:{chat_id}:session"

    async def load(self, chat_id: str) -> SessionState:
        raw = await self._client.get(self._key(chat_id))
        if raw is None:
            return SessionState()
        data = json.loads(raw)
        return SessionState(
            stage=ConversationStage(data["stage"]),
            profile=CustomerProfile().apply(data["profile"]),
            questions_asked=int(data["questions_asked"]),
            shown_products=tuple(data.get("shown_products", ())),  # absent in sessions saved before
            awaiting_answer=bool(data.get("awaiting_answer", False)),
            dodged_questions=int(data.get("dodged_questions", 0)),
        )

    async def save(self, chat_id: str, state: SessionState) -> None:
        payload = {
            "stage": state.stage.value,
            "profile": state.profile.known(),
            "questions_asked": state.questions_asked,
            "shown_products": list(state.shown_products),
            "awaiting_answer": state.awaiting_answer,
            "dodged_questions": state.dodged_questions,
        }
        await self._client.set(
            self._key(chat_id), json.dumps(payload, ensure_ascii=False), ex=self._ttl_seconds
        )
