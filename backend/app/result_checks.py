"""Semantic checks on a result that *ran successfully*.

A query can be valid SQL and still be wrong. These heuristics catch the classic silent
failures: a filter that matches nothing (wrong status string, wrong date range) or a join
that never matches (column entirely NULL). Repairable issues trigger one more LLM attempt;
others are surfaced to the user as warnings.
"""
from __future__ import annotations

from dataclasses import dataclass

from .db import QueryResult


@dataclass
class Issue:
    code: str
    message: str
    repairable: bool


def check_result(result: QueryResult) -> list[Issue]:
    issues: list[Issue] = []

    if result.row_count == 0:
        issues.append(Issue(
            "empty_result",
            "The query returned zero rows.",
            repairable=True,
        ))
        return issues

    for i, col in enumerate(result.columns):
        if all(row[i] is None for row in result.rows):
            issues.append(Issue(
                "all_null_column",
                f"Column '{col['name']}' is NULL in every row (a join or filter may be wrong).",
                repairable=True,
            ))

    if result.truncated:
        issues.append(Issue(
            "truncated",
            f"Result was cut off at {result.row_count} rows; the full answer has more rows.",
            repairable=False,
        ))
    return issues
