"""BM25 lexical retrieval — the exact-token complement to dense retrieval.

Dense embeddings underperform on exact identifiers (WHO_AM_I), spec-table
values (±2000 dps → 70 mdps/LSB), and cross-references (AN5259): these carry
little semantic signal, so their vectors sit near everything and nowhere.
BM25 scores on token overlap, which is exactly where those queries win.

The index is built once from the same chunks stored in Chroma and cached for
the process lifetime — a ~500-chunk corpus tokenizes in well under a second.
"""

import re
from functools import lru_cache

from rank_bm25 import BM25Okapi

from app.rag import store

# Keep identifiers whole: WHO_AM_I -> "who_am_i", CTRL1_XL -> "ctrl1_xl",
# 0Dh -> "0dh", 6Ch -> "6ch", AN5259 -> "an5259". Decimal values split on the
# dot (0.061 -> "0","061"), which still leaves a distinctive numeric token.
_TOKEN = re.compile(r"[a-z0-9_]+")


def tokenize(text: str) -> list[str]:
    return _TOKEN.findall(text.lower())


@lru_cache(maxsize=1)
def _index() -> tuple[BM25Okapi, list[dict]]:
    corpus = store.all_chunks()
    if not corpus:
        raise RuntimeError("Lexical index is empty — ingest the corpus first.")
    bm25 = BM25Okapi([tokenize(c["text"]) for c in corpus])
    return bm25, corpus


def bm25_search(query: str, n: int) -> list[dict]:
    """Top-n chunks by BM25 score. Same dict shape as store.query (no distance)."""
    bm25, corpus = _index()
    scores = bm25.get_scores(tokenize(query))
    ranked = sorted(range(len(corpus)), key=lambda i: scores[i], reverse=True)
    return [corpus[i] for i in ranked[:n]]


def reset_cache() -> None:
    """Drop the cached index (call after re-ingesting within one process)."""
    _index.cache_clear()
