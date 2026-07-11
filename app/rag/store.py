"""Persistent Chroma vector store wrapper."""

import chromadb

from app.config import settings
from app.rag.chunking import Chunk
from app.rag.embeddings import embed_query, embed_texts


def _collection():
    client = chromadb.PersistentClient(path=settings.index_dir)
    return client.get_or_create_collection(settings.collection_name)


def add_chunks(chunks: list[Chunk], batch_size: int = 64) -> int:
    col = _collection()
    for i in range(0, len(chunks), batch_size):
        batch = chunks[i : i + batch_size]
        col.upsert(
            ids=[c.chunk_id for c in batch],
            documents=[c.text for c in batch],
            embeddings=embed_texts([c.text for c in batch]),
            metadatas=[{"source": c.source, "page": c.page} for c in batch],
        )
    return len(chunks)


def query(text: str, top_k: int | None = None) -> list[dict]:
    """Return top-k chunks as dicts: {chunk_id, text, source, page, distance}."""
    col = _collection()
    res = col.query(query_embeddings=[embed_query(text)], n_results=top_k or settings.top_k)
    out = []
    for chunk_id, doc, meta, dist in zip(
        res["ids"][0], res["documents"][0], res["metadatas"][0], res["distances"][0]
    ):
        out.append(
            {
                "chunk_id": chunk_id,
                "text": doc,
                "source": meta["source"],
                "page": meta["page"],
                "distance": dist,
            }
        )
    return out


def count() -> int:
    return _collection().count()
