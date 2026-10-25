"""Run evaluation cases through the real pipeline and score them against golden answers."""
from __future__ import annotations

import time
from collections import defaultdict
from dataclasses import asdict, dataclass, field

import sqlglot
from sqlglot import exp

from app import db, services
from app.llm import LLMClient, LLMError
from app.pipeline import answer_question

from .cases import CASES, Case
from .compare import compare_results

_TABLES = ["categories", "products", "customers", "orders", "order_items"]
_CLOCK_NODES = tuple(getattr(exp, n) for n in ("CurrentDate", "CurrentTimestamp", "CurrentTime", "CurrentDatetime") if hasattr(exp, n))


@dataclass
class CaseResult:
    id: str
    category: str
    question: str
    expect: str
    passed: bool
    status: str                  # pipeline status: ok / failed / cannot_answer / llm_error
    reason: str                  # why it failed (empty when passed)
    attempts: int
    generated_sql: str | None
    golden_sql: str | None
    elapsed_s: float
    flags: list[str] = field(default_factory=list)   # non-fatal lint findings
    trap: str = ""


@dataclass
class Report:
    model: str
    results: list[CaseResult]
    integrity_ok: bool
    integrity_detail: str = ""

    # ---- metrics ----
    @property
    def total(self) -> int: return len(self.results)
    @property
    def passed(self) -> int: return sum(r.passed for r in self.results)
    @property
    def accuracy(self) -> float: return self.passed / self.total if self.total else 0.0
    @property
    def first_try(self) -> int: return sum(r.passed and r.attempts == 1 for r in self.results)
    @property
    def recovered_by_repair(self) -> int: return sum(r.passed and r.attempts > 1 for r in self.results)
    @property
    def avg_attempts(self) -> float: return sum(r.attempts for r in self.results) / self.total if self.total else 0.0
    @property
    def total_seconds(self) -> float: return sum(r.elapsed_s for r in self.results)

    def by_category(self) -> dict[str, tuple[int, int]]:
        out: dict[str, list[int]] = defaultdict(lambda: [0, 0])
        for r in self.results:
            out[r.category][1] += 1
            out[r.category][0] += r.passed
        return {k: (v[0], v[1]) for k, v in out.items()}

    def to_dict(self) -> dict:
        return {
            "model": self.model,
            "summary": {
                "total": self.total, "passed": self.passed, "accuracy": round(self.accuracy, 4),
                "first_try_passes": self.first_try, "recovered_by_repair": self.recovered_by_repair,
                "avg_attempts": round(self.avg_attempts, 3), "total_seconds": round(self.total_seconds, 2),
                "database_integrity_ok": self.integrity_ok,
            },
            "by_category": {k: {"passed": p, "total": t} for k, (p, t) in self.by_category().items()},
            "results": [asdict(r) for r in self.results],
        }


def fingerprint() -> dict[str, int]:
    """Row counts of every table, used to prove the evaluation never modified data."""
    counts = {}
    for t in _TABLES:
        _, res = services.run_sql(f"SELECT COUNT(*) AS n FROM {t}")
        counts[t] = res.rows[0][0]
    return counts


def lint_sql(sql: str | None) -> list[str]:
    """Non-fatal findings. Using the wall clock on a historical dataset is a date-handling smell."""
    if not sql:
        return []
    try:
        tree = sqlglot.parse_one(sql, read="postgres")
    except Exception:
        return []
    if _CLOCK_NODES and any(tree.find_all(*_CLOCK_NODES)):
        return ["uses CURRENT_DATE/NOW() instead of the provided date windows"]
    return []


def run_case(case: Case, llm: LLMClient) -> CaseResult:
    start = time.perf_counter()
    base = dict(id=case.id, category=case.category, question=case.question, expect=case.expect,
                golden_sql=case.golden_sql, trap=case.trap)
    try:
        out = answer_question(case.question, llm)
    except LLMError as e:
        return CaseResult(**base, passed=False, status="llm_error", reason=str(e), attempts=0,
                          generated_sql=None, elapsed_s=round(time.perf_counter() - start, 3))

    generated = out.sql or next((a.sql for a in reversed(out.attempts) if a.sql), None)
    common = dict(status=out.status, attempts=len(out.attempts), generated_sql=generated,
                  flags=lint_sql(out.sql))

    if case.expect == "refuse":
        passed = out.status in {"cannot_answer", "failed"}
        reason = "" if passed else f"answered instead of refusing (status={out.status}): {out.sql}"
    elif out.status != "ok":
        passed, reason = False, f"pipeline {out.status}: {out.message}"
    else:
        _, golden = services.run_sql(case.golden_sql)
        cmp = compare_results([c["name"] for c in golden.columns], golden.rows, out.result.rows,
                              ordered=case.ordered, actual_cols=[c["name"] for c in out.result.columns])
        passed, reason = cmp.match, cmp.reason

    return CaseResult(**base, **common, passed=passed, reason=reason, elapsed_s=round(time.perf_counter() - start, 3))


def run_all(llm: LLMClient, cases: list[Case] | None = None, on_result=None) -> Report:
    cases = cases if cases is not None else CASES
    before = fingerprint()
    results = []
    for case in cases:
        r = run_case(case, llm)
        results.append(r)
        if on_result:
            on_result(r)
    after = fingerprint()
    return Report(
        model=getattr(llm, "model", "unknown"),
        results=results,
        integrity_ok=before == after,
        integrity_detail="" if before == after else f"row counts changed: {before} -> {after}",
    )
