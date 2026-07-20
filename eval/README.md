# MEMS Technical-Support Agent

A RAG-based technical-support agent that answers questions about the
STMicroelectronics **LSM6DSOX** IMU from its real documentation — with a
QA-grade evaluation and regression-test harness (in progress).

## Status

- [x] Phase 0 — repo skeleton, CI, Docker, `/health`
- [x] Phase 1 — ingestion → retrieval → cited answers via `POST /ask`
- [ ] Phase 2 — golden-set evaluation harness (`eval/golden_set.yaml` ready)
- [ ] Phase 3 — regression gate in CI + observability
- [ ] Phase 4 — hybrid retrieval, table/code-aware chunking, robustness
- [ ] Phase 5 — frontend + live deployment

## Architecture (Phase 1)

```
data/raw/*.pdf|*.c|*.md
        │  scripts/ingest.py  (PyMuPDF → chunk → embed)
        ▼
   Chroma index (data/index/)          sentence-transformers, local & free
        │  top-k similarity
        ▼
POST /ask ──► retrieved chunks ──► LLM (OpenAI-compatible) ──► grounded answer
        │                                                       + [n] citations
        └──► logs/requests.jsonl  (query, chunks, answer, latency)
```

## Quickstart

```bash
# 1. Install
python -m venv .venv && source .venv/bin/activate
make install

# 2. Configure the LLM
cp .env.example .env    # add your API key, or point it at local Ollama

# 3. Add the corpus
#    Put lsm6dsox.pdf (datasheet DS12814) into data/raw/
#    Optionally add app notes, the driver README, and .c examples.

# 4. Ingest
make ingest

# 5. Run
make run
```

Then ask it something:

```bash
curl -s localhost:8000/ask \
  -H 'Content-Type: application/json' \
  -d '{"question": "What is the WHO_AM_I value of the LSM6DSOX?"}' | jq
```

You get back the answer, the exact source chunks it used (with page
numbers), and the latency:

```json
{
  "answer": "The WHO_AM_I register (0Fh) is fixed at 6Ch (see [1]).",
  "sources": [{ "chunk_id": "lsm6dsox.pdf:53:1", "page": 53, "...": "..." }],
  "latency_ms": 1240
}
```

## Design choices worth noting

- **Citations from day one.** `/ask` always returns the chunks the answer
  is grounded in — non-negotiable for a support agent.
- **Out-of-scope refusal is a feature.** The system prompt requires the
  model to say when the docs don't contain the answer. Phase 2 *measures*
  how well this holds instead of assuming it.
- **Every request is logged** (`logs/requests.jsonl`): query, retrieved
  chunk ids, answer, latency — the raw material for Phase 3 monitoring.
- **Local embeddings** (sentence-transformers) keep the iteration loop
  free; only answer generation costs API tokens, and it runs on Ollama too.

## Evaluation (Phase 2 — next)

`eval/golden_set.yaml` contains a labeled Q&A set spanning seven question
categories (factual, register, conceptual, procedural, conditional,
pointer, **out-of-scope**). The harness will score retrieval (recall@k,
MRR) and answers (faithfulness, correctness) and gate CI on regressions.

## Dev

```bash
make test   # unit tests
make lint   # ruff
docker compose up --build   # run containerized
```
