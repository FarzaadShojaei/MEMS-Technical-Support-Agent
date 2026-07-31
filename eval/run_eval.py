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
import re
import statistics
import sys
import time
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import settings
from app.rag import store
from app.rag.generator import _client, build_context, generate_answer

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
        return {
            "correct": None,
            "faithful": None,
            "reason": f"judge output unparseable: {raw[:80]}",
        }


# Categories whose ground truth is an exact string (value / register / address /
# app-note id) -> graded deterministically, no LLM. Only conceptual & procedural,
# where paraphrase matters, still use the LLM judge.
DETERMINISTIC_CATEGORIES = {"factual", "register", "conditional", "pointer"}

_REFUSAL_MARKERS = (
    "does not cover", "not mentioned", "not specified", "does not specify",
    "does not provide", "not provided", "could not find", "couldn't find",
    "unable to find", "not in the provided", "not covered", "not explicitly",
    "no information", "does not contain", "does not compare", "does not include",
    "does not offer", "no comparative", "not available in the",
)


def _normalize(s: str) -> str:
    """Collapse to alphanumerics only, lowercased.

    Makes matching robust to PDF spacing artifacts (thin/non-breaking spaces),
    punctuation, and unit formatting: "0.55 mA", "0.55\u2009mA" and "0.55mA"
    all normalize to "055ma".
    """
    return re.sub(r"[^a-z0-9]", "", s.lower())


def _is_refusal(answer: str) -> bool:
    a = answer.lower()
    return any(m in a for m in _REFUSAL_MARKERS)


def eval_retrieval(entry: dict, chunks: list[dict]) -> dict:
    keys = entry.get("retrieval_keys") or []
    if not keys:
        return {"hit": None, "rank": None}  # not scorable (e.g. out_of_scope)
    norm_keys = [_normalize(k) for k in keys]
    for rank, c in enumerate(chunks, start=1):
        text = _normalize(c["text"])
        if any(nk and nk in text for nk in norm_keys):
            return {"hit": True, "rank": rank}
    return {"hit": False, "rank": None}


def grade_deterministic(entry: dict, answer: str) -> dict:
    """Exact-value grading: every token in `answer_must_contain` must appear
    (normalized) in the answer. No LLM, so it cannot mislabel."""
    required = entry.get("answer_must_contain") or []
    if not required:
        return {"correct": None, "reason": "no answer_must_contain defined"}
    norm_answer = _normalize(answer)
    missing = [tok for tok in required if _normalize(tok) not in norm_answer]
    if missing:
        return {"correct": False, "reason": f"missing required token(s): {missing}"}
    return {"correct": True, "reason": f"contains all required: {required}"}


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
            refusal = _is_refusal(answer)

            # --- correctness: pick the cheapest reliable grader per category ---
            cat = e["category"]
            if cat in DETERMINISTIC_CATEGORIES:
                verdict = grade_deterministic(e, answer)
                row["grader"] = "deterministic"
            elif cat == "out_of_scope":
                # "Did the agent decline?" is a semantic question. The marker
                # heuristic proved too brittle here (it missed the perfectly
                # valid refusal "does not compare..."), so this one category
                # uses the LLM judge — the one place it genuinely earns its keep.
                verdict = _judge(JUDGE_REFUSAL_PROMPT.format(question=e["question"], answer=answer))
                row["grader"] = "llm-judge-refusal"
            else:  # conceptual, procedural -> paraphrase matters, use the judge
                verdict = _judge(
                    JUDGE_CORRECTNESS_PROMPT.format(
                        question=e["question"], expected=e["expected_answer"], answer=answer
                    )
                )
                row["grader"] = "llm-judge"
            row["correct"] = verdict.get("correct")
            row["correct_reason"] = verdict.get("reason")

            # --- faithfulness: a refusal makes no factual claims, so it is
            #     faithful by construction; only judge substantive answers. ---
            if refusal:
                row["faithful"] = True
                row["faithful_reason"] = "refusal makes no factual claims"
            else:
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
    if scorable:
        reciprocals = [1 / r["retrieval_rank"] for r in hits] + [0] * (len(scorable) - len(hits))
        mrr = statistics.mean(reciprocals)
    else:
        mrr = 0.0

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
            "retrieval_hit_rate": (
                round(len(cat_hits) / len(cat_scorable), 2) if cat_scorable else None
            ),
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
        print(
            f"Answers     correctness: {a['correctness']}   "
            f"faithfulness: {a['faithfulness']}   ({a['graded']} graded)"
        )
    print("-" * 62)
    print(f"{'category':<14}{'n':>3}{'retrieval':>12}{'correct':>10}")
    for cat, v in s["by_category"].items():
        rh = "-" if v["retrieval_hit_rate"] is None else v["retrieval_hit_rate"]
        co = "-" if v["correctness"] is None else v["correctness"]
        print(f"{cat:<14}{v['n']:>3}{rh!s:>12}{co!s:>10}")
    print("=" * 62)


def check_gate(summary: dict, thresholds: dict) -> list[dict]:
    """Compare a summary against threshold floors.

    Returns one row per checked metric: {metric, value, floor, passed}.
    A metric that wasn't measured (e.g. correctness on a --retrieval-only run)
    is skipped rather than failed — absence of data is not a regression.
    """
    checks: list[dict] = []
    hit_key = f"hit@{summary['top_k']}"

    def add(name: str, value, floor) -> None:
        if value is None or floor is None:
            return
        checks.append(
            {"metric": name, "value": value, "floor": floor, "passed": value >= floor}
        )

    r_th = thresholds.get("retrieval") or {}
    add(hit_key, summary["retrieval"].get(hit_key), r_th.get("hit_at_k"))
    add("mrr", summary["retrieval"].get("mrr"), r_th.get("mrr"))

    a_th = thresholds.get("answers") or {}
    add("correctness", summary["answers"].get("correctness"), a_th.get("correctness"))
    add("faithfulness", summary["answers"].get("faithfulness"), a_th.get("faithfulness"))

    for cat, cat_th in (thresholds.get("by_category") or {}).items():
        cat_summary = summary["by_category"].get(cat)
        if not cat_summary:
            continue
        add(f"{cat}.correctness", cat_summary.get("correctness"), cat_th.get("correctness"))
        add(
            f"{cat}.retrieval",
            cat_summary.get("retrieval_hit_rate"),
            cat_th.get("retrieval_hit_rate"),
        )

    return checks


def print_gate(checks: list[dict]) -> bool:
    """Print the gate table. Returns True if every check passed."""
    print("\n" + "=" * 62)
    print("QUALITY GATE")
    print("=" * 62)
    if not checks:
        print("No metrics to check (nothing measured).")
        return True
    print(f"{'metric':<26}{'value':>9}{'floor':>9}{'result':>12}")
    for c in checks:
        status = "PASS" if c["passed"] else "FAIL <<<"
        print(f"{c['metric']:<26}{c['value']:>9}{c['floor']:>9}{status:>12}")
    failed = [c for c in checks if not c["passed"]]
    print("-" * 62)
    if failed:
        print(f"GATE FAILED — {len(failed)} of {len(checks)} metric(s) below floor.")
        print("Quality regressed. Fix it, or if the drop is intentional and")
        print("justified, update eval/thresholds.yaml in the same commit.")
    else:
        print(f"GATE PASSED — all {len(checks)} metric(s) at or above floor.")
    print("=" * 62)
    return not failed


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--retrieval-only", action="store_true", help="skip LLM calls (fast)")
    p.add_argument("--limit", type=int, default=None)
    p.add_argument("--top-k", type=int, default=settings.top_k)
    p.add_argument("--out", type=str, default="eval/last_report.json")
    p.add_argument(
        "--gate",
        action="store_true",
        help="enforce eval/thresholds.yaml; exit 1 if any metric is below its floor",
    )
    p.add_argument("--thresholds", type=str, default="eval/thresholds.yaml")
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

    if args.gate:
        th_path = Path(args.thresholds)
        if not th_path.exists():
            print(f"Thresholds file not found: {th_path}")
            sys.exit(2)
        thresholds = yaml.safe_load(th_path.read_text(encoding="utf-8"))
        checks = check_gate(summary, thresholds)
        summary["gate"] = checks
        out.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
        if not print_gate(checks):
            sys.exit(1)


if __name__ == "__main__":
    main()
