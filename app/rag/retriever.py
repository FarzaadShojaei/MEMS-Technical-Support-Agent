"""Retrieval entrypoint: dense, or hybrid (dense + BM25 fused with RRF).

`retrieve()` is the single call the rest of the app uses; the mode is driven by
settings.retrieval_mode, so switching dense<->hybrid for an A/B comparison is
just an environment variable — no code change, and the eval harness picks it up
automatically.

Fusion is Reciprocal Rank Fusion (RRF): each retriever contributes 1/(k+rank)
to a chunk's score. RRF needs no score normalization between the two very
different scales (cosine distance vs BM25), which makes it robust and is why
it's the standard choice for combining lexical and dense retrieval.
"""

from collections import defaultdict

from app.config import settings
from app.rag import store
from app.rag.lexical import bm25_search


def rrf_fuse(result_lists: list[list[dict]], k: int, top_k: int) -> list[dict]:
    """Fuse multiple ranked chunk lists into one via Reciprocal Rank Fusion."""
    scores: dict[str, float] = defaultdict(float)
    chunk_by_id: dict[str, dict] = {}
    for results in result_lists:
        for rank, chunk in enumerate(results, start=1):
            cid = chunk["chunk_id"]
            scores[cid] += 1.0 / (k + rank)
            chunk_by_id.setdefault(cid, chunk)

    ranked_ids = sorted(scores, key=lambda cid: scores[cid], reverse=True)[:top_k]
    fused = []
    for cid in ranked_ids:
        chunk = dict(chunk_by_id[cid])
        chunk["score"] = round(scores[cid], 5)
        chunk.setdefault("distance", None)  # lexical-only hits have no distance
        fused.append(chunk)
    return fused


def hybrid_retrieve(query: str, top_k: int | None = None) -> list[dict]:
    top_k = top_k or settings.top_k
    pool = max(settings.fusion_pool, top_k)
    dense = store.query(query, top_k=pool)
    lexical = bm25_search(query, n=pool)
    return rrf_fuse([dense, lexical], k=settings.rrf_k, top_k=top_k)


def retrieve(query: str, top_k: int | None = None) -> list[dict]:
    """Dispatch on the configured retrieval mode."""
    if settings.retrieval_mode == "hybrid":
        return hybrid_retrieve(query, top_k)
    return store.query(query, top_k)
