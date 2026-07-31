"""Summarize production traffic from logs/requests.jsonl.

Phase 1 started logging every /ask call (query, retrieved chunk ids, answer,
latency). This turns that raw log into the numbers you actually act on:
latency percentiles, refusal rate, and which chunks the retriever leans on.

Why it matters for the agent: the golden set measures questions *you* thought
to ask. The log shows what users actually ask — and a rising refusal rate is
the earliest signal that real traffic has drifted outside the indexed corpus.

Usage:
    python scripts/log_stats.py
    python scripts/log_stats.py --log logs/requests.jsonl --top 10
"""

import argparse
import json
import statistics
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from eval.run_eval import _is_refusal  # noqa: E402


def load(path: Path) -> list[dict]:
    if not path.exists():
        print(f"No log file at {path} — serve some /ask requests first.")
        sys.exit(1)
    rows = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue  # tolerate a partially-written final line
    return rows


def percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = min(round(pct / 100 * (len(ordered) - 1)), len(ordered) - 1)
    return ordered[idx]


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--log", default="logs/requests.jsonl")
    p.add_argument("--top", type=int, default=5, help="how many top chunks/questions to show")
    args = p.parse_args()

    rows = load(Path(args.log))
    if not rows:
        print("Log file is empty.")
        return

    latencies = [r["latency_ms"] for r in rows if "latency_ms" in r]
    refusals = [r for r in rows if _is_refusal(r.get("answer", ""))]

    print("=" * 58)
    print(f"REQUEST LOG  ({len(rows)} requests)")
    print("=" * 58)
    if latencies:
        print(f"Latency   p50 {percentile(latencies, 50):>7.0f} ms")
        print(f"          p95 {percentile(latencies, 95):>7.0f} ms")
        print(f"          max {max(latencies):>7.0f} ms")
        print(f"         mean {statistics.mean(latencies):>7.0f} ms")
    rate = len(refusals) / len(rows)
    print(f"\nRefusal rate  {rate:.1%}  ({len(refusals)}/{len(rows)})")
    if rate > 0.5:
        print("  ^ over half of traffic is unanswerable from the current corpus.")
        print("    Either users are asking outside scope, or retrieval is failing.")

    chunk_counts = Counter(cid for r in rows for cid in r.get("retrieved", []))
    if chunk_counts:
        print(f"\nMost-retrieved chunks (top {args.top}):")
        for cid, n in chunk_counts.most_common(args.top):
            print(f"  {n:>4}x  {cid}")
        print(f"\nDistinct chunks ever retrieved: {len(chunk_counts)}")

    q_counts = Counter(r.get("question", "").strip().lower() for r in rows)
    repeats = [(q, n) for q, n in q_counts.most_common(args.top) if n > 1]
    if repeats:
        print("\nRepeated questions:")
        for q, n in repeats:
            print(f"  {n:>4}x  {q[:60]}")
    print("=" * 58)


if __name__ == "__main__":
    main()
