"""Phase 2 — Golden-set evaluation harness.

Runs every golden-set question through the real pipeline (retrieval +
generation) and scores:

  Retrieval:
    hit@k  — did any retrieved chunk contain one of the entry's
             `retrieval_keys` (exact strings that mark the right region)?
    MRR    — reciprocal rank of the first such chunk.

  Answer (LLM-as-judge, category-aware):
    correctness  — does the answer match `expected_answer`?
                   For `out_of_scope` entries, CORRECT means the agent
                   declined / said the docs don't cover it.
    faithfulness — for non-refusal answers: is every claim supported by
                   the retrieved context?

Usage:
    python eval/run_eval.py                 # full run (retrieval + answers)
    python eval/run_eval.py --retrieval-only  # fast, no LLM calls
    python eval/run_eval.py --limit 5       # first N entries
    python eval/run_eval.py --out report.json

Exit code is 0 always in Phase 2. Phase 3 adds --gate thresholds that
make CI fail on regression.
"""

import argparse
import json
import statistics
import sys
import time
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import settings  # noqa: E402
from app.rag import store  # noqa: E402
from app.rag.generator import _client, build_context, generate_answer  # noqa: E402

GOLDEN_PATH = Path(__file__).parent / "golden_set.yaml"

JUDGE_CORRECTNESS_PROMPT = """\
You are grading a technical-support agent's answer against ground truth.

Question: {question}

Ground-truth answer (what a correct answer must convey):
{expected}

Agent's answer:
{answer}

Grade STRICTLY. Reply with ONLY a JSON object, no other text:
{{"correct": true/false, "reason": "<one short sentence>"}}

Rules:
- "correct" is true only if the agent's answer conveys the key facts of the
  ground truth (exact values, register names, and addresses must match).
- Extra correct information does not make it wrong.
- If the agent says the documentation does not cover it, that is INCORRECT
  for this question (the ground truth exists in the docs).
"""

JUDGE_REFUSAL_PROMPT = """\
You are grading a technical-support agent on an OUT-OF-SCOPE question —
one whose answer is NOT in the documentation. The correct behavior is to
decline: say the documentation doesn't cover it, and never invent a value.

Question: {question}

Agent's answer:
{answer}

Reply with ONLY a JSON object, no other text:
{{"correct": true/false, "reason": "<one short sentence>"}}

"correct" is true only if the agent declined or clearly stated the
information is not in the documentation, without fabricating an answer.
"""

JUDGE_FAITHFULNESS_PROMPT = """\
You are checking whether an answer is GROUNDED in the provided context.

Context (documentation excerpts):
{context}

Answer to check:
{answer}

Reply with ONLY a JSON object, no other text:
{{"faithful": true/false, "reason": "<one short sentence>"}}

"faithful" is true only if every factual claim in the answer (values,
register names, addresses, behaviors) appears in or follows directly from
the context. An explicit refusal ("the docs don't cover this") is faithful.
"""


def _judge(prompt: str) -> dict:
    """One LLM-as-judge call. Returns parsed JSON or a failure marker."""
    resp = _client().chat.completions.create(
        model=settings.llm_model,
        temperature=0.0,
        max_tokens=150,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = (resp.choices[0].message.content or "").strip()
    raw = raw.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    try:
        start, end = raw.index("{"), raw.rindex("}") + 1
        return json.loads(raw[start:end])
    except (ValueError, json.JSONDecodeError):
        return {"correct": None, "faithful": None, "reason": f"judge output unparseable: {raw[:80]}"}


def eval_retrieval(entry: dict, chunks: list[dict]) -> dict:
    keys = entry.get("retrieval_keys") or []
    if not keys:
        return {"hit": None, "rank": None}  # not scorable (e.g. out_of_scope)
    for rank, c in enumerate(chunks, start=1):
        text = c["text"].lower()
        if any(k.lower() in text for k in keys):
            return {"hit": True, "rank": rank}
    return {"hit": False, "rank": None}


def run(limit: int | None, retrieval_only: bool, top_k: int) -> dict:
    entries = yaml.safe_load(GOLDEN_PATH.read_text(encoding="utf-8"))
    if limit:
        entries = entries[:limit]

    results = []
    for i, e in enumerate(entries, 1):
        print(f"[{i}/{len(entries)}] {e['id']} ({e['category']}) ... ", end="", flush=True)
        t0 = time.perf_counter()

        chunks = store.query(e["question"], top_k=top_k)
        r = eval_retrieval(e, chunks)

        row = {
            "id": e["id"],
            "category": e["category"],
            "difficulty": e.get("difficulty"),
            "retrieval_hit": r["hit"],
            "retrieval_rank": r["rank"],
        }

        if not retrieval_only:
            answer = generate_answer(e["question"], chunks)
            row["answer"] = answer

            if e["category"] == "out_of_scope":
                verdict = _judge(JUDGE_REFUSAL_PROMPT.format(question=e["question"], answer=answer))
            else:
                verdict = _judge(
                    JUDGE_CORRECTNESS_PROMPT.format(
                        question=e["question"], expected=e["expected_answer"], answer=answer
                    )
                )
            row["correct"] = verdict.get("correct")
            row["correct_reason"] = verdict.get("reason")

            faith = _judge(
                JUDGE_FAITHFULNESS_PROMPT.format(context=build_context(chunks), answer=answer)
            )
            row["faithful"] = faith.get("faithful")
            row["faithful_reason"] = faith.get("reason")

        row["latency_s"] = round(time.perf_counter() - t0, 1)
        results.append(row)
        print(f"hit={row['retrieval_hit']} correct={row.get('correct', '-')} ({row['latency_s']}s)")

    return summarize(results, top_k)


def summarize(results: list[dict], top_k: int) -> dict:
    scorable = [r for r in results if r["retrieval_hit"] is not None]
    hits = [r for r in scorable if r["retrieval_hit"]]
    mrr = statistics.mean([1 / r["retrieval_rank"] for r in hits] + [0] * (len(scorable) - len(hits))) if scorable else 0.0

    graded = [r for r in results if r.get("correct") is not None]
    correct = [r for r in graded if r["correct"]]
    faith_graded = [r for r in results if r.get("faithful") is not None]
    faithful = [r for r in faith_graded if r["faithful"]]

    summary = {
        "top_k": top_k,
        "n": len(results),
        "retrieval": {
            "scorable": len(scorable),
            f"hit@{top_k}": round(len(hits) / len(scorable), 3) if scorable else None,
            "mrr": round(mrr, 3),
        },
        "answers": {
            "graded": len(graded),
            "correctness": round(len(correct) / len(graded), 3) if graded else None,
            "faithfulness": round(len(faithful) / len(faith_graded), 3) if faith_graded else None,
        },
        "by_category": {},
        "results": results,
    }

    for cat in sorted({r["category"] for r in results}):
        rows = [r for r in results if r["category"] == cat]
        cat_scorable = [r for r in rows if r["retrieval_hit"] is not None]
        cat_hits = [r for r in cat_scorable if r["retrieval_hit"]]
        cat_graded = [r for r in rows if r.get("correct") is not None]
        cat_correct = [r for r in cat_graded if r["correct"]]
        summary["by_category"][cat] = {
            "n": len(rows),
            "retrieval_hit_rate": round(len(cat_hits) / len(cat_scorable), 2) if cat_scorable else None,
            "correctness": round(len(cat_correct) / len(cat_graded), 2) if cat_graded else None,
        }
    return summary


def print_scorecard(s: dict) -> None:
    print("\n" + "=" * 62)
    print(f"SCORECARD  (n={s['n']}, top_k={s['top_k']})")
    print("=" * 62)
    r, a = s["retrieval"], s["answers"]
    hit_key = f"hit@{s['top_k']}"
    print(f"Retrieval   {hit_key}: {r[hit_key]}   MRR: {r['mrr']}   ({r['scorable']} scorable)")
    if a["graded"]:
        print(f"Answers     correctness: {a['correctness']}   faithfulness: {a['faithfulness']}   ({a['graded']} graded)")
    print("-" * 62)
    print(f"{'category':<14}{'n':>3}{'retrieval':>12}{'correct':>10}")
    for cat, v in s["by_category"].items():
        rh = "-" if v["retrieval_hit_rate"] is None else v["retrieval_hit_rate"]
        co = "-" if v["correctness"] is None else v["correctness"]
        print(f"{cat:<14}{v['n']:>3}{rh!s:>12}{co!s:>10}")
    print("=" * 62)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--retrieval-only", action="store_true", help="skip LLM calls (fast)")
    p.add_argument("--limit", type=int, default=None)
    p.add_argument("--top-k", type=int, default=settings.top_k)
    p.add_argument("--out", type=str, default="eval/last_report.json")
    args = p.parse_args()

    if store.count() == 0:
        print("Index is empty — run `python scripts/ingest.py` first.")
        sys.exit(1)

    summary = run(limit=args.limit, retrieval_only=args.retrieval_only, top_k=args.top_k)
    print_scorecard(summary)

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nFull report written to {out}")


if __name__ == "__main__":
    main()
