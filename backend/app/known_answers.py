"""Compare an answer with the evaluation suite's known answer, when the question is in the suite.

This powers the "verified against a known answer" card in the UI. Questions outside the suite
simply have no verification (we never pretend to know an answer we don't).
"""
from __future__ import annotations

from typing import Any

from . import services
from .db import QueryResult
from .llm.replay import normalize_question

MAX_GOLDEN_ROWS = 25


def verify(question: str, status: str, result: QueryResult | None) -> dict[str, Any] | None:
    from evals.cases import CASES                       # lazy: evals depends on app, not the reverse
    from evals.compare import compare_results

    key = normalize_question(question)
    case = next((c for c in CASES if normalize_question(c.question) == key), None)
    if case is None:
        return None
    base = {"case_id": case.id, "category": case.category, "trap": case.trap, "expect": case.expect}

    if case.expect == "refuse":
        refused = status in {"cannot_answer", "failed"}
        return {**base, "matched": refused,
                "reason": "Correctly refused." if refused else "Answered a question that should be refused."}

    if result is None:
        return {**base, "matched": False, "reason": "No result to compare.", "golden_sql": case.golden_sql}
    try:
        _, golden = services.run_sql(case.golden_sql)
    except Exception:
        return None
    cmp = compare_results([c["name"] for c in golden.columns], golden.rows, result.rows,
                          ordered=case.ordered, actual_cols=[c["name"] for c in result.columns])
    return {**base, "matched": cmp.match, "reason": cmp.reason or "Result equals the known answer.",
            "golden_sql": case.golden_sql, "golden_columns": [c["name"] for c in golden.columns],
            "golden_rows": golden.rows[:MAX_GOLDEN_ROWS], "ordered": case.ordered}
