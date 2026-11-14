"""Embedder adapter: OpenAI embeddings, sent in batches."""

from collections.abc import Sequence

import openai
from openai import AsyncOpenAI

from app.domain.errors import RetrievalError


class OpenAIEmbedder:
    def __init__(self, api_key: str, model: str, timeout_seconds: float, batch_size: int) -> None:
        self._client = AsyncOpenAI(api_key=api_key, timeout=timeout_seconds)
        self._model = model
        self._batch_size = batch_size

    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for start in range(0, len(texts), self._batch_size):
            batch = list(texts[start : start + self._batch_size])
            try:
                response = await self._client.embeddings.create(model=self._model, input=batch)
            except openai.OpenAIError as exc:
                raise RetrievalError(f"Embedding request failed: {exc}") from exc
            vectors.extend(item.embedding for item in sorted(response.data, key=lambda d: d.index))
        return vectors
