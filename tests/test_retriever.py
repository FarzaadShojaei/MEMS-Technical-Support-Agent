"""Tests for hybrid retrieval fusion and lexical tokenization.

RRF fusion is pure logic (no index, no LLM), so it's fully unit-testable and
runs in CI. These lock in the property that matters: a chunk ranked highly by
*either* retriever surfaces in the fused result — which is the entire reason
hybrid retrieval fixes the dense-only misses (WHO_AM_I, AN5259, table values).
"""

from app.rag.lexical import tokenize
from app.rag.retriever import rrf_fuse


def _chunk(cid: str) -> dict:
    return {"chunk_id": cid, "text": f"text-{cid}", "source": "ds.pdf", "page": 1}


# --------------------------------------------------------------------------
# tokenizer — must keep register identifiers whole
# --------------------------------------------------------------------------


def test_tokenize_keeps_identifiers_whole():
    assert tokenize("WHO_AM_I") == ["who_am_i"]
    assert tokenize("CTRL1_XL (10h)") == ["ctrl1_xl", "10h"]
    assert tokenize("AN5259") == ["an5259"]
    assert tokenize("value is 6Ch") == ["value", "is", "6ch"]


def test_tokenize_splits_decimals_but_keeps_numeric_signal():
    # 0.061 -> "0","061": the distinctive "061" survives as a token
    assert "061" in tokenize("0.061 mg/LSB")


# --------------------------------------------------------------------------
# RRF fusion
# --------------------------------------------------------------------------


def test_rrf_rewards_agreement():
    """A chunk both retrievers rank highly beats one only a single retriever
    likes."""
    dense = [_chunk("A"), _chunk("B"), _chunk("C")]
    lexical = [_chunk("A"), _chunk("D"), _chunk("E")]
    fused = rrf_fuse([dense, lexical], k=60, top_k=3)
    assert fused[0]["chunk_id"] == "A"  # top of both lists


def test_rrf_surfaces_lexical_only_hit():
    """The core reason hybrid fixes dense misses: a chunk dense ranked last but
    BM25 ranked first must still surface near the top."""
    dense = [_chunk("A"), _chunk("B"), _chunk("C"), _chunk("D"), _chunk("WHO")]
    lexical = [_chunk("WHO"), _chunk("X"), _chunk("Y")]
    fused = rrf_fuse([dense, lexical], k=60, top_k=3)
    ids = [c["chunk_id"] for c in fused]
    assert "WHO" in ids  # dense had it at rank 5; BM25 rank 1 rescues it


def test_rrf_attaches_score_and_default_distance():
    fused = rrf_fuse([[_chunk("A")]], k=60, top_k=1)
    assert fused[0]["score"] > 0
    assert fused[0]["distance"] is None  # lexical-only chunk carries no distance


def test_rrf_respects_top_k():
    dense = [_chunk(c) for c in "ABCDEF"]
    assert len(rrf_fuse([dense], k=60, top_k=3)) == 3


def test_rrf_preserves_dense_distance_when_present():
    dense = [{"chunk_id": "A", "text": "t", "source": "s", "page": 1, "distance": 0.42}]
    fused = rrf_fuse([dense], k=60, top_k=1)
    assert fused[0]["distance"] == 0.42
