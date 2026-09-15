"""Optional local embedding providers and small vector math helpers."""

from __future__ import annotations

import math
from typing import Protocol, Sequence


class EmbeddingError(RuntimeError):
    """Raised when an embedding provider cannot load or encode input."""


class EmbeddingProvider(Protocol):
    model_name: str
    dimension: int

    def embed(self, texts: list[str]) -> list[list[float]]:
        ...


class SentenceTransformerEmbeddingProvider:
    """Load a local sentence-transformers model without downloading at query time."""

    def __init__(self, model_name: str) -> None:
        if not model_name.strip():
            raise EmbeddingError("embedding model name is required")
        try:
            from sentence_transformers import SentenceTransformer
        except (ImportError, ModuleNotFoundError) as exc:
            raise EmbeddingError(
                "sentence-transformers is required for embedding retrieval; install requirements-embeddings.txt"
            ) from exc
        try:
            try:
                self._model = SentenceTransformer(model_name, local_files_only=True)
            except TypeError:
                self._model = SentenceTransformer(
                    model_name, model_kwargs={"local_files_only": True}
                )
            dimension = self._model.get_sentence_embedding_dimension()
        except Exception as exc:  # provider exceptions vary by installed version
            raise EmbeddingError(f"unable to load local embedding model: {model_name}") from exc
        if not isinstance(dimension, int) or dimension <= 0:
            raise EmbeddingError("embedding model returned an invalid dimension")
        self.model_name = model_name
        self.dimension = dimension

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts or any(not isinstance(text, str) or not text.strip() for text in texts):
            raise EmbeddingError("embedding input must contain non-empty text")
        try:
            values = self._model.encode(texts, convert_to_numpy=False, normalize_embeddings=False)
            vectors = [[float(value) for value in vector] for vector in values]
        except Exception as exc:  # provider exceptions vary by installed version
            raise EmbeddingError("unable to encode embedding input") from exc
        if len(vectors) != len(texts) or any(len(vector) != self.dimension for vector in vectors):
            raise EmbeddingError("embedding provider returned inconsistent dimensions")
        return vectors


def cosine_similarity(left: Sequence[float], right: Sequence[float]) -> float:
    if len(left) != len(right) or not left:
        raise ValueError("vectors must have the same non-zero dimension")
    left_norm = math.sqrt(sum(float(value) ** 2 for value in left))
    right_norm = math.sqrt(sum(float(value) ** 2 for value in right))
    if left_norm == 0.0 or right_norm == 0.0:
        raise ValueError("zero vectors cannot be compared")
    return sum(float(a) * float(b) for a, b in zip(left, right)) / (left_norm * right_norm)


def rank_by_cosine(query: Sequence[float], vectors: Sequence[Sequence[float]]) -> list[int]:
    scored = [(cosine_similarity(query, vector), index) for index, vector in enumerate(vectors)]
    scored.sort(key=lambda item: (-item[0], item[1]))
    return [index for _, index in scored]
