# MEMS Technical-Support Agent

A retrieval-augmented (RAG) technical-support agent that answers questions about
the STMicroelectronics **LSM6DSOX** IMU directly from its datasheet — wrapped in
a **QA-grade evaluation and regression-testing harness**.

The RAG service shows the system can be built. The evaluation harness — with
deterministic grading, a trustworthy baseline, and a CI regression gate that
protects a safety property — is the point of the project: it demonstrates the
ability to both *build* and *rigorously validate* an LLM system, which is a
rarer combination than either skill alone.

---

## Status

| Phase | Scope | State |
|------|-------|-------|
| 0 | Repo skeleton, CI, Docker, `/health` | ✅ |
| 1 | Ingestion → retrieval → cited answers via `POST /ask` | ✅ |
| 2 | Golden-set evaluation harness + trustworthy baseline | ✅ |
| 3 | Two-tier regression gate + observability | ✅ |
| 4 | Hybrid retrieval (BM25 + dense), table-aware chunking | planned |
| 5 | Live deployment + minimal web frontend | planned |

---

## Architecture

```
data/raw/*.pdf | *.c | *.md
        │  scripts/ingest.py  (PyMuPDF → chunk → embed)
        ▼
   Chroma index (data/index/)           sentence-transformers, local & free
        │  top-k similarity
        ▼
POST /ask ──► retrieved chunks ──► LLM (OpenAI-compatible / Ollama) ──► grounded
        │                                                    answer + [n] citations
        └──► logs/requests.jsonl   (query, chunk ids, answer, latency)
                                          │
                                          ▼
                          scripts/log_stats.py  (latency p50/p95, refusal rate)

eval/golden_set.yaml  ──►  eval/run_eval.py  ──►  scorecard + eval/last_report.json
   24 labelled Q&A            hybrid grading            hit@k · MRR · correctness
   across 7 categories                                  · faithfulness
                                     │
                                     ▼
                        eval/thresholds.yaml  +  --gate  →  exit 1 on regression
```

---

## Baseline (Phase 3)

24-question golden set, `top_k = 5`, generation + judging on a local
`llama3.1:8b` via Ollama.

| Metric | Value |
|---|---|
| Retrieval hit@5 | **0.524** |
| Retrieval MRR | **0.369** |
| Answer correctness | 0.375 |
| Answer faithfulness | **0.875** |
| Out-of-scope refusal | **1.000** |

hit@5 improved from an initial 0.476 → 0.524 after fixing a measurement bug:
retrieval keys were failing to match their target chunks because of PDF spacing
artifacts (`"0.55 mA"` vs `"0.55\u2009mA"`). Normalizing to alphanumerics before
matching recovered hits that were always present. No pipeline change — just
honest measurement.

### What the numbers say

The aggregate hides the real story; the per-category breakdown tells it:

| Category | Retrieval hit-rate | Correctness | Reading |
|---|---|---|---|
| conceptual | 1.00 | 0.00 | retrieval perfect → failure is **generation** |
| factual | 0.44 | 0.44 | mixed; prose facts pass, table facts miss |
| register | 0.75 | 0.50 | names retrieved, bit-field details shaky |
| procedural | 0.50 | 0.00 | multi-step synthesis is hard for an 8B model |
| conditional | 0.00 | 0.00 | table-value lookups never retrieved |
| pointer | 0.00 | 0.00 | app-note references never retrieved |
| out_of_scope | — | 1.00 | refuses instead of fabricating — the safety win |

Two distinct, measured failure modes:

1. **Retrieval fails on exact identifiers, table values, and cross-references.**
   Dense embeddings match prose well but miss register mnemonics (`WHO_AM_I`),
   spec-table rows (gyro sensitivity at ±2000 dps), and pointers (`AN5259`).
   → Phase 4: hybrid BM25 + dense retrieval and table-aware chunking.
2. **Generation is weak even when retrieval succeeds.** On conceptual questions
   the correct chunk is retrieved at rank 1, yet the 8B model rambles, invents
   details, or contradicts itself. → Phase 4: prompt work / stronger generation
   model.

Faithfulness is high (0.875) and refusal is perfect (1.0): the agent
overwhelmingly declines rather than hallucinates. The one real hallucination in
the set (`fact-fifo` — "3 KB" from a wrong chunk) is documented rather than
hidden.

---

## Evaluation methodology

The harness grades three things and picks the cheapest *reliable* grader per
question category — a deliberate design choice after an early run showed a weak
LLM judge mislabeling answers we had hand-verified as correct.

**Retrieval** (deterministic): `hit@k` and `MRR`, scored by checking whether any
retrieved chunk contains an entry's `retrieval_keys` (exact strings marking the
correct region), matched after alphanumeric normalization.

**Answer correctness** (hybrid):
- *Factual / register / conditional / pointer* → **deterministic**: the answer
  must contain every token in `answer_must_contain` (e.g. `6Ch`, `0.061`,
  `AN5259`). No LLM, so exact values can't be misgraded.
- *Conceptual / procedural* → **LLM judge**: paraphrase genuinely needs
  judgment here.
- *Out-of-scope* → **LLM refusal judge**: "did the agent decline?" is a
  semantic question, and this is the one category where the judge earns its keep.

**Faithfulness** (refusal-aware): a refusal makes no factual claims, so it is
faithful by construction; only substantive answers are sent to the judge.

Every result row records which grader produced its verdict (`deterministic` /
`llm-judge` / `llm-judge-refusal`), so any LLM-graded call can be audited.

---

## Regression gate

`python eval/run_eval.py --gate` enforces the floors in `eval/thresholds.yaml`
and **exits 1** if any metric drops below its floor.

Floors are set *below* the baseline, with a deliberate asymmetry: deterministic
metrics (retrieval, exact-value correctness) get tight floors because they can't
drift; LLM-judged metrics get a wider tolerance band because the judge is
nondeterministic and a floor set exactly at the baseline would flake. Per-category
floors catch regressions the aggregate would hide — most importantly
`out_of_scope.correctness: 1.0`, so a change that raises overall correctness while
silently breaking refusals still fails the build. The gate is a ratchet: floors
only move up.

### Two-tier design (why CI can't run the full eval)

The full eval needs a local LLM (Ollama), the built vector index, and the ST
datasheet — none of which belong on a GitHub runner (the datasheet is ST's
copyrighted document and is intentionally kept out of the repo). So gating is
split:

- **Tier 1 — CI, every push:** unit-tests the *grader itself* (31 tests),
  validates the golden set is well-formed, and re-checks the committed report
  against thresholds. If the thing that measures quality breaks, every number
  the project reports is worthless — so that is blocked automatically.
- **Tier 2 — local, pre-push:** the real quality gate (`--gate`) runs the full
  eval and blocks on regression. The passing report is committed so quality
  history is visible in the diff.

---

## Observability

Every `/ask` call is logged to `logs/requests.jsonl` (query, retrieved chunk ids,
answer, latency). `scripts/log_stats.py` turns that into latency p50/p95, refusal
rate, and most-retrieved chunks. The golden set measures the questions *I* thought
to ask; the log shows what users actually ask — and a rising refusal rate is the
earliest signal that real traffic has drifted outside the indexed corpus.

---

## Quickstart

Windows / PowerShell (no `make` needed):

```powershell
# 1. Install
python -m venv .venv; .venv\Scripts\Activate.ps1
pip install -r requirements.txt

# 2. Configure the LLM (OpenAI-compatible or local Ollama)
Copy-Item .env.example .env      # then edit: API key, or point at Ollama

# 3. Add the corpus
#    Put lsm6dsox.pdf (datasheet DS12814) into data\raw\

# 4. Ingest
python scripts/ingest.py

# 5. Run
uvicorn app.main:app --reload --port 8000
```

Open `http://localhost:8000/docs` and try `POST /ask`, or:

```powershell
Invoke-RestMethod -Uri http://localhost:8000/ask -Method Post `
  -ContentType "application/json" `
  -Body '{"question": "What is the WHO_AM_I value of the LSM6DSOX?"}'
```

### Evaluation & gate

```powershell
pytest -q                        # 31 tests (grader + API), no LLM needed
python eval/run_eval.py          # full eval → scorecard + report
python eval/run_eval.py --gate   # enforce thresholds, exit 1 on regression
python scripts/log_stats.py      # production traffic summary
```

---

## Design choices worth noting

- **Citations and refusal from day one.** `/ask` returns the exact chunks an
  answer is grounded in, and the system prompt requires "not covered in the
  documentation" over guessing. The eval *measures* how well that holds rather
  than assuming it.
- **Local embeddings** (sentence-transformers) keep ingestion and retrieval free;
  only answer generation touches an LLM, and that runs on Ollama at zero cost.
- **Deterministic grading where values are exact.** Asking a weak model to grade
  whether "6Ch" is correct is both unnecessary and unreliable; a normalized
  substring check cannot be wrong.
- **The safety property has its own floor.** Out-of-scope refusal is guarded
  separately so it can never be traded away for a higher aggregate score.

---

## Tech stack

FastAPI · PyMuPDF · sentence-transformers · Chroma · Ollama (llama3.1:8b) ·
pytest · ruff · GitHub Actions · Docker
