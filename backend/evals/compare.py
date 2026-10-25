"""Compare a generated result against the known answer.

Goal: be strict about *values* and lenient about *presentation*. A correct query should
never fail because of column aliases, column order, extra helpful columns, float noise,
or ('2025-10' vs '2025-10-01') date spelling. A wrong query must fail.

Algorithm
  1. Row counts must match.
  2. For each expected column, find the actual column(s) holding the same multiset of values
     (alias-independent). Missing -> fail ("expected values of <col> not found").
  3. Try each consistent column assignment and compare the rows built from it
     (as a multiset, or in order when the question implies an order).
Extra actual columns are allowed.
"""
from __future__ import annotations

import itertools
import math
import re
from dataclasses import dataclass
from typing import Any

ABS_TOL = 0.011      # money rounded to cents may differ by a rounding step
REL_TOL = 1e-6

_DATE = re.compile(r"^(\d{4})-(\d{2})(?:-(\d{2}))?(?:[ T].*)?$")


@dataclass
class Comparison:
    match: bool
    reason: str = ""


def norm(v: Any) -> Any:
    if v is None or isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip()
    m = _DATE.match(s)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3) or '01'}"
    return s


def eq(a: Any, b: Any) -> bool:
    if a is None or b is None:
        return a is None and b is None
    if isinstance(a, float) and isinstance(b, float):
        return math.isclose(a, b, rel_tol=REL_TOL, abs_tol=ABS_TOL)
    return a == b


def _sort_key(v: Any):
    return (v is None, isinstance(v, str), 0 if v is None else v)


def _same_multiset(xs: list, ys: list) -> bool:
    return len(xs) == len(ys) and all(eq(a, b) for a, b in zip(sorted(xs, key=_sort_key), sorted(ys, key=_sort_key)))


def _rows_eq(r1: tuple, r2: tuple) -> bool:
    return all(eq(a, b) for a, b in zip(r1, r2))


def _val(v: Any) -> str:
    if v is None:
        return "NULL"
    if isinstance(v, float):
        return f"{v:.4f}".rstrip("0").rstrip(".")
    return str(v)


def _fmt(row) -> str:
    return "[" + ", ".join(_val(v) for v in row) + "]"


def _diff(expected: list, actual: list) -> tuple[list, list]:
    """(expected values not found, actual values not expected), tolerant equality."""
    pool = list(actual)
    missing = []
    for e in expected:
        for k, a in enumerate(pool):
            if eq(e, a):
                pool.pop(k)
                break
        else:
            missing.append(e)
    return missing, pool


def _explain_missing_column(name: str, ecol: list, act_columns: list[list], act_names: list[str]) -> str:
    """Compare against the closest result column so the failure says *what* differs."""
    def score(j: int):
        missing, _ = _diff(ecol, act_columns[j])
        same_type = bool(act_columns[j]) and type(act_columns[j][0]) is type(ecol[0])
        return (len(missing), not same_type, j)
    best = min(range(len(act_columns)), key=score)
    missing, extra = _diff(ecol, act_columns[best])
    return (f"column '{name}' differs from result column '{act_names[best]}': "
            f"missing {_fmt(missing[:4])}, unexpected {_fmt(extra[:4])}")


def compare_results(
    expected_cols: list[str],
    expected_rows: list[list],
    actual_rows: list[list],
    *,
    ordered: bool = False,
    actual_cols: list[str] | None = None,
) -> Comparison:
    exp = [tuple(norm(v) for v in r) for r in expected_rows]
    act = [tuple(norm(v) for v in r) for r in actual_rows]

    if len(exp) != len(act):
        return Comparison(False, f"row count: expected {len(exp)}, got {len(act)}")
    if not exp:
        return Comparison(True)                      # both empty

    n_act_cols = len(act[0])
    exp_columns = [[r[i] for r in exp] for i in range(len(expected_cols))]
    act_columns = [[r[j] for r in act] for j in range(n_act_cols)]

    candidates: list[list[int]] = []
    for i, ecol in enumerate(exp_columns):
        found = [j for j, acol in enumerate(act_columns) if _same_multiset(ecol, acol)]
        if not found:
            names = actual_cols or [f"col{j + 1}" for j in range(n_act_cols)]
            return Comparison(False, _explain_missing_column(expected_cols[i], ecol, act_columns, names))
        candidates.append(found)

    first_failure = ""
    for assignment in itertools.product(*candidates):
        if len(set(assignment)) != len(assignment):
            continue                                  # two expected columns can't share one actual column
        projected = [tuple(r[j] for j in assignment) for r in act]
        verdict = _compare_rows(exp, projected, ordered)
        if verdict.match:
            return verdict
        first_failure = first_failure or verdict.reason
    return Comparison(False, first_failure or "columns exist but cannot be matched one-to-one")


def _compare_rows(exp: list[tuple], act: list[tuple], ordered: bool) -> Comparison:
    if ordered:
        for k, (e, a) in enumerate(zip(exp, act), start=1):
            if not _rows_eq(e, a):
                if _unordered_equal(exp, act):
                    return Comparison(False, f"right rows in the wrong order (row {k}: expected {_fmt(e)}, got {_fmt(a)})")
                return Comparison(False, f"row {k} differs: expected {_fmt(e)}, got {_fmt(a)}")
        return Comparison(True)
    missing = _first_unmatched(exp, act)
    if missing is not None:
        return Comparison(False, f"expected row {_fmt(missing)} not found in the result")
    return Comparison(True)


def _first_unmatched(exp: list[tuple], act: list[tuple]):
    used = [False] * len(act)
    for e in exp:
        for j, a in enumerate(act):
            if not used[j] and _rows_eq(e, a):
                used[j] = True
                break
        else:
            return e
    return None


def _unordered_equal(exp, act) -> bool:
    return _first_unmatched(exp, act) is None
