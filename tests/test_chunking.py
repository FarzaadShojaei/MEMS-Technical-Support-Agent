"""Phase 0/1 tests. Kept dependency-light so CI stays fast.

The /ask endpoint's *quality* is deliberately NOT tested here — that's
Phase 2's eval harness job. These tests cover pure logic and API shape.
"""

from app.rag.chunking import chunk_text


def test_chunking_empty_text_returns_nothing():
    assert chunk_text("", "x.pdf", 1, chunk_size=100, overlap=10) == []


def test_chunking_short_text_is_single_chunk():
    chunks = chunk_text("hello world", "x.pdf", 1, chunk_size=100, overlap=10)
    assert len(chunks) == 1
    assert chunks[0].text == "hello world"
    assert chunks[0].chunk_id == "x.pdf:1:0"


def test_chunking_long_text_overlaps_and_covers():
    text = ("The WHO_AM_I register value is 6Ch. " * 60).strip()
    chunks = chunk_text(text, "ds.pdf", 3, chunk_size=200, overlap=50)
    assert len(chunks) > 1
    # ids are stable and ordered
    assert chunks[0].chunk_id == "ds.pdf:3:0"
    assert chunks[1].chunk_id == "ds.pdf:3:1"
    # no chunk wildly exceeds the target size
    assert all(len(c.text) <= 260 for c in chunks)
