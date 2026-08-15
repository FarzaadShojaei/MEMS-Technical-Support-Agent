# MEMS Technical-Support Agent

A retrieval-augmented (RAG) support agent that answers technical questions about
the STMicroelectronics **LSM6DSOX** IMU straight from its datasheet — citing the
page, and declining when the answer isn't in the docs — wrapped in a **QA-grade
evaluation harness and CI regression gate**.

The RAG is the easy half. The point of this project is the rigor around it:
knowing *whether the answers are right*, measuring it, and protecting that
measurement from regressions — the same discipline a QA/SDET brings to software,
applied to an LLM system.

---

## Headline result

Adding hybrid retrieval, guided by the evaluation harness, produced a measured
improvement — not a vibe:

| Metric | Dense | Hybrid | Δ |
|---|---|---|---|
| Retrieval hit@5 | 0.52 | **0.76** | +45% |
| Retrieval MRR | 0.37 | **0.54** | +47% |
| Answer correctness | 0.38 | **0.54** | +45% |
| Faithfulness | 0.88 | 0.79 | −0.09* |
| Out-of-scope refusal | 1.00 | **1.00** | held |

<sub>*Faithfulness dips because the stronger agent *attempts* more answers
instead of refusing — more surface area, still grounded. Refusal-as-safety is
held at 1.00 by a dedicated gate floor.</sub>

Measured on a 24-question golden set across seven question categories.

---

## Status

| Phase | Scope | State |
|------|-------|-------|
| 0 | Repo skeleton, CI, Docker, `/health` | ✅ |
| 1 | Ingestion → retrieval → cited answers via `POST /ask` | ✅ |
| 2 | Golden-set evaluation harness + trustworthy baseline | ✅ |
| 3 | Two-tier regression gate + observability | ✅ |
| 4 | Hybrid retrieval (BM25 + dense, RRF fusion) | ✅ |
| 5 | Web frontends (React SPA + built-in HTML) | ✅ built · deploy documented |

> The demo runs locally today; cloud deployment is documented in
> [`DEPLOY.md`](DEPLOY.md) but not yet hosted.

---

## Architecture

```
data/raw/*.pdf | *.c | *.md
        │  scripts/ingest.py  (PyMuPDF → chunk → embed)
        ▼
   Chroma index ──► dense (vector) ─┐
        │                           ├─► Reciprocal Rank Fusion ─► top-k
   BM25 lexical  ──► exact tokens ──┘        (app/rag/retriever.py)
        ▼
POST /ask ──► fused chunks ──► LLM (Ollama / Groq) ──► grounded answer + [n] cites
        │                                                        or a refusal
        └──► logs/requests.jsonl  (query, chunks, answer, latency)

eval/golden_set.yaml ─► eval/run_eval.py ─► hit@k · MRR · correctness · faithfulness
                                     └─► --gate → exit 1 on regression (eval/thresholds.yaml)
```

---

## Why hybrid retrieval

The evaluation harness didn't just score the system — it localized the failure.
Dense embeddings were blind to exact tokens: register mnemonics (`WHO_AM_I`),
spec-table values (`±2000 dps → 70 mdps/LSB`), and app-note references
(`AN5259`) carry little semantic signal, so their vectors sit near everything
and nowhere. BM25 matches them on the token. Fusing the two with Reciprocal Rank
Fusion (which needs no score normalization between cosine distance and BM25)
moved factual retrieval from 0.44 to 0.89 and cracked open categories that were
flat zero.

---

## Evaluation methodology

The harness picks the cheapest *reliable* grader per question category — a
decision made after an early run showed a weak LLM judge mislabeling answers
that were hand-verified correct:

- **Factual / register / conditional / pointer** → **deterministic**: the answer
  must contain exact tokens (`6Ch`, `0.061`, `AN5259`), matched after
  normalization. No LLM, so exact values can't be misgraded.
- **Conceptual / procedural** → **LLM judge**: paraphrase needs judgment.
- **Out-of-scope** → **LLM refusal judge**: "did it decline?" is semantic.

Faithfulness is refusal-aware (a refusal makes no claims to hallucinate), and
every result row records which grader produced its verdict, so any LLM-graded
call is auditable.

---

## Regression gate

`python eval/run_eval.py --gate` enforces `eval/thresholds.yaml` and exits 1 if
any metric falls below its floor. Floors sit below the baseline with a
deliberate asymmetry — tight on deterministic metrics, wider on LLM-judged ones
(the judge is nondeterministic) — and per-category floors catch regressions the
aggregate would hide, most importantly `out_of_scope: 1.0`, so a change that
raises overall correctness while breaking refusals still fails the build.

**Two-tier design:** the full eval needs a local LLM, the vector index, and the
datasheet — none of which belong on a CI runner. So CI (Tier 1) unit-tests the
*grader itself* and validates the golden set; the full quality gate (Tier 2)
runs locally pre-push. Being able to explain *why* CI can't run the full eval is
part of the point.

---

## Frontends

Two, by design:

- **Built-in HTML** served by FastAPI at `/` — single deployment, one URL.
- **React (Vite) SPA** in `frontend/` — a chat-style UI with a "How it works"
  page, meant for a separate Vercel deployment calling the backend.

Both render answers with page-level citations, latency, and a declined/answered
outcome — the refusal behavior is visible in the UI itself.

---

## Quickstart

```bash
# backend
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\Activate.ps1
pip install -r requirements.txt
cp .env.example .env          # add an LLM key, or point at local Ollama
# put lsm6dsox.pdf into data/raw/
python scripts/ingest.py
uvicorn app.main:app --reload --port 8000
```

Open `http://localhost:8000/` for the built-in UI, or run the React app:

```bash
cd frontend && npm install && npm run dev   # http://localhost:5173, proxies to :8000
```

### Evaluation & gate

```bash
python eval/run_eval.py                 # full eval → scorecard + report
python eval/run_eval.py --retrieval-only  # fast: hit@k / MRR only, no LLM
python eval/run_eval.py --gate          # enforce thresholds, exit 1 on regression
$env:RETRIEVAL_MODE="dense"; python eval/run_eval.py   # A/B against the baseline
```

---

## Tech stack

FastAPI · PyMuPDF · sentence-transformers · Chroma · rank-bm25 · Ollama / Groq ·
React (Vite) · pytest · ruff · GitHub Actions · Docker

---

## Notes

- The LSM6DSOX datasheet is ST's copyrighted document (freely available from
  st.com); this is an educational/portfolio project and does not redistribute
  the PDF.
- `/ask` is single-turn: each question retrieves independently, with no
  conversation memory. Multi-turn context is a documented next step.
