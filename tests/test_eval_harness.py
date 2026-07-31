"""Tests for the evaluation harness itself.

These matter more than they look. The harness is what gates every future
change to the RAG pipeline — so if the *grader* silently breaks, every
downstream quality number becomes meaningless and the regression gate
starts waving through real regressions.

Several cases below are regression tests for bugs found during the Phase 2
baseline run:
  - retrieval keys missed real hits over PDF spacing ("0.55 mA" vs "0.55 mA")
  - a valid refusal ("does not compare...") was scored as a non-refusal
  - refusals were judged "unfaithful" despite making no factual claims

All pure functions: no vector index, no LLM, no network. Fast enough to run
on every push.
"""

import pytest

from eval.run_eval import (
    _is_refusal,
    _normalize,
    check_gate,
    eval_retrieval,
    grade_deterministic,
    summarize,
)

# --------------------------------------------------------------------------
# normalization — the fix for PDF spacing artifacts
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "a,b",
    [
        ("0.55 mA", "0.55mA"),
        ("0.55 mA", "0.55\u2009mA"),  # thin space, common in PDF extraction
        ("-40 to +85", "−40 to +85"),  # unicode minus vs hyphen
        ("±2/±4/±8/±16 g", "2 4 8 16g"),
        ("WHO_AM_I", "who am i"),
    ],
)
def test_normalize_collapses_formatting_differences(a, b):
    assert _normalize(a) == _normalize(b)


def test_normalize_preserves_meaningful_difference():
    assert _normalize("9 KB") != _normalize("3 KB")


def test_normalize_does_not_erase_unit_letters():
    """Documented limitation: normalization strips punctuation and spacing,
    but letters survive — so "-40 to +85" does NOT match "-40°C to +85°C".

    Consequence for the golden set: retrieval_keys and answer_must_contain
    should be short numeric/identifier cores ("40", "0.061", "AN5259"), not
    full phrases carrying units. Asserted here so the constraint is explicit
    rather than rediscovered as a false-miss in a future baseline.
    """
    assert _normalize("-40 to +85") != _normalize("-40°C to +85°C")
    # the robust form: bare numeric tokens, matched independently
    assert _normalize("40") in _normalize("-40°C to +85°C")
    assert _normalize("85") in _normalize("-40°C to +85°C")


# --------------------------------------------------------------------------
# retrieval scoring
# --------------------------------------------------------------------------


def test_retrieval_hit_reports_rank():
    entry = {"retrieval_keys": ["6Ch"]}
    chunks = [{"text": "irrelevant"}, {"text": "its value is fixed at 6Ch"}]
    assert eval_retrieval(entry, chunks) == {"hit": True, "rank": 2}


def test_retrieval_miss():
    entry = {"retrieval_keys": ["6Ch"]}
    assert eval_retrieval(entry, [{"text": "nothing here"}]) == {"hit": False, "rank": None}


def test_retrieval_unscorable_without_keys():
    """out_of_scope entries have no correct chunk, so they must not be
    counted as misses — that would understate the true hit rate."""
    assert eval_retrieval({}, [{"text": "x"}]) == {"hit": None, "rank": None}


def test_retrieval_survives_pdf_spacing():
    """Regression: this exact case was scored a miss in the first baseline."""
    entry = {"retrieval_keys": ["0.55 mA"]}
    chunks = [{"text": "Supply current: 0.55 mA in combo high-performance mode"}]
    assert eval_retrieval(entry, chunks)["hit"] is True


# --------------------------------------------------------------------------
# deterministic grading — no LLM, cannot mislabel exact values
# --------------------------------------------------------------------------


def test_deterministic_requires_all_tokens():
    entry = {"answer_must_contain": ["INT1_CTRL", "0Dh"]}
    assert grade_deterministic(entry, "INT1_CTRL is at 0Dh")["correct"] is True
    assert grade_deterministic(entry, "INT1_CTRL exists")["correct"] is False


def test_deterministic_catches_wrong_value():
    """Regression: the agent answered 3 KB when the datasheet says 9 KB."""
    entry = {"answer_must_contain": ["9kb"]}
    assert grade_deterministic(entry, "the LSM6DSOX embeds 3 KB of FIFO")["correct"] is False


def test_deterministic_credits_answer_buried_in_noise():
    """Regression: the LLM judge failed this answer for rambling, but the
    required value IS present, so it is correct."""
    entry = {"answer_must_contain": ["INT1_CTRL", "0Dh"]}
    rambling = "First, WHO_AM_I (0Fh) is 6Ch. But we want INT1_CTRL... its address is 0Dh."
    assert grade_deterministic(entry, rambling)["correct"] is True


def test_deterministic_skips_when_no_tokens_defined():
    assert grade_deterministic({}, "anything")["correct"] is None


# --------------------------------------------------------------------------
# refusal detection
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "answer",
    [
        "The provided documentation does not cover pricing.",
        "The documentation does not compare the LSM6DSOX to the Bosch BMI270.",
        "I couldn't find any information on that in the excerpts.",
        "That value is not specified in the provided context.",
    ],
)
def test_refusals_detected(answer):
    assert _is_refusal(answer) is True


def test_substantive_answer_is_not_a_refusal():
    assert _is_refusal("The WHO_AM_I register is fixed at 6Ch.") is False


# --------------------------------------------------------------------------
# summary math
# --------------------------------------------------------------------------


def test_summarize_excludes_unscorable_from_retrieval_rate():
    rows = [
        {"id": "a", "category": "factual", "retrieval_hit": True, "retrieval_rank": 1,
         "correct": True, "faithful": True},
        {"id": "b", "category": "register", "retrieval_hit": False, "retrieval_rank": None,
         "correct": False, "faithful": True},
        {"id": "c", "category": "out_of_scope", "retrieval_hit": None, "retrieval_rank": None,
         "correct": True, "faithful": True},
    ]
    s = summarize(rows, top_k=5)
    assert s["retrieval"]["scorable"] == 2  # the out_of_scope row is excluded
    assert s["retrieval"]["hit@5"] == 0.5
    assert s["retrieval"]["mrr"] == 0.5
    assert s["answers"]["correctness"] == round(2 / 3, 3)
    assert s["by_category"]["out_of_scope"]["retrieval_hit_rate"] is None


# --------------------------------------------------------------------------
# the gate
# --------------------------------------------------------------------------


def _summary(hit=0.48, mrr=0.32, corr=0.375, faith=0.875, oos=1.0):
    return {
        "top_k": 5,
        "n": 24,
        "retrieval": {"scorable": 21, "hit@5": hit, "mrr": mrr},
        "answers": {"graded": 24, "correctness": corr, "faithfulness": faith},
        "by_category": {"out_of_scope": {"n": 3, "retrieval_hit_rate": None, "correctness": oos}},
    }


THRESHOLDS = {
    "retrieval": {"hit_at_k": 0.45, "mrr": 0.29},
    "answers": {"correctness": 0.30, "faithfulness": 0.75},
    "by_category": {"out_of_scope": {"correctness": 1.0}},
}


def test_gate_passes_at_baseline():
    checks = check_gate(_summary(), THRESHOLDS)
    assert checks and all(c["passed"] for c in checks)


def test_gate_fails_on_retrieval_regression():
    checks = check_gate(_summary(hit=0.30), THRESHOLDS)
    failed = [c for c in checks if not c["passed"]]
    assert [c["metric"] for c in failed] == ["hit@5"]


def test_gate_fails_when_refusals_regress():
    """The safety property: a change that boosts correctness while breaking
    out-of-scope refusal must still fail the build."""
    checks = check_gate(_summary(corr=0.60, oos=0.67), THRESHOLDS)
    failed = [c for c in checks if not c["passed"]]
    assert [c["metric"] for c in failed] == ["out_of_scope.correctness"]


def test_gate_skips_unmeasured_metrics():
    """A --retrieval-only run has no answer metrics; absence of data must not
    be treated as a regression."""
    s = _summary()
    s["answers"] = {"graded": 0, "correctness": None, "faithfulness": None}
    metrics = [c["metric"] for c in check_gate(s, THRESHOLDS)]
    assert "correctness" not in metrics
    assert "hit@5" in metrics
