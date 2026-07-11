"""Text chunking.

v0: fixed-size character chunks with overlap, splitting on paragraph
boundaries where possible. Deliberately simple — Phase 4 replaces this
with structure-aware chunking (register tables, C code blocks).
"""

from dataclasses import dataclass


@dataclass
class Chunk:
    text: str
    source: str      # e.g. "lsm6dsox.pdf"
    page: int        # 1-based page number the chunk starts on
    chunk_id: str    # stable id: "<source>:<page>:<n>"


def chunk_text(text: str, source: str, page: int, chunk_size: int, overlap: int) -> list[Chunk]:
    """Split one page's text into overlapping chunks, preferring paragraph breaks."""
    if not text.strip():
        return []

    chunks: list[Chunk] = []
    start = 0
    n = 0
    while start < len(text):
        end = min(start + chunk_size, len(text))
        # try to end on a paragraph or line break for cleaner chunks
        if end < len(text):
            for sep in ("\n\n", "\n", ". "):
                cut = text.rfind(sep, start + chunk_size // 2, end)
                if cut != -1:
                    end = cut + len(sep)
                    break
        piece = text[start:end].strip()
        if piece:
            chunks.append(Chunk(text=piece, source=source, page=page, chunk_id=f"{source}:{page}:{n}"))
            n += 1
        if end >= len(text):
            break
        start = max(end - overlap, start + 1)
    return chunks
