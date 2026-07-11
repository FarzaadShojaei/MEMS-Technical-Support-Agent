"""Embeddings via sentence-transformers (local, no API cost).

The model is loaded lazily and cached so the API process only pays the
load cost once.
"""

from functools import lru_cache

from sentence_transformers import SentenceTransformer

from app.config import settings


@lru_cache(maxsize=1)
def _model() -> SentenceTransformer:
    return SentenceTransformer(settings.embedding_model)


def embed_texts(texts: list[str]) -> list[list[float]]:
    return _model().encode(texts, normalize_embeddings=True).tolist()


def embed_query(query: str) -> list[float]:
    return embed_texts([query])[0]
