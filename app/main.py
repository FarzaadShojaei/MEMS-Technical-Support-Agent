"""MEMS Technical-Support Agent — API.

Phase 1 surface:
  GET  /health  -> liveness + index size
  POST /ask     -> {question} -> {answer, sources[]}

Every request/response is logged as one JSON line (logs/requests.jsonl) —
the seed of Phase 3 observability.
"""

import json
import time
from pathlib import Path

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from app.rag import store
from app.rag.generator import generate_answer

app = FastAPI(title="MEMS Technical-Support Agent", version="0.1.0")

LOG_PATH = Path("logs/requests.jsonl")


class AskRequest(BaseModel):
    question: str = Field(..., min_length=3, max_length=2000)
    top_k: int | None = Field(default=None, ge=1, le=20)


class SourceOut(BaseModel):
    chunk_id: str
    source: str
    page: int
    distance: float
    text: str


class AskResponse(BaseModel):
    answer: str
    sources: list[SourceOut]
    latency_ms: int


def _log(record: dict) -> None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with LOG_PATH.open("a") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "indexed_chunks": store.count()}


@app.post("/ask", response_model=AskResponse)
def ask(req: AskRequest) -> AskResponse:
    if store.count() == 0:
        raise HTTPException(
            status_code=503,
            detail="Index is empty. Run `python scripts/ingest.py` first.",
        )
    t0 = time.perf_counter()
    chunks = store.query(req.question, top_k=req.top_k)
    answer = generate_answer(req.question, chunks)
    latency_ms = int((time.perf_counter() - t0) * 1000)

    _log(
        {
            "ts": time.time(),
            "question": req.question,
            "retrieved": [c["chunk_id"] for c in chunks],
            "answer": answer,
            "latency_ms": latency_ms,
        }
    )
    return AskResponse(
        answer=answer,
        sources=[SourceOut(**c) for c in chunks],
        latency_ms=latency_ms,
    )
