"""Deterministic date windows.

LLMs are unreliable at "last quarter" arithmetic, so we compute the windows in code and
hand them to the model as facts. Windows are returned as (start inclusive, end exclusive),
which is the safe way to filter date/timestamp columns:  col >= start AND col < end.
"""
from __future__ import annotations

from datetime import date, timedelta


def _quarter_start(d: date) -> date:
    return date(d.year, 3 * ((d.month - 1) // 3) + 1, 1)


def _add_months(d: date, months: int) -> date:
    total = d.year * 12 + (d.month - 1) + months
    return date(total // 12, total % 12 + 1, 1)


def date_windows(today: date) -> dict[str, tuple[date, date]]:
    q0 = _quarter_start(today)
    lq0 = _add_months(q0, -3)
    pq0 = _add_months(q0, -6)
    m0 = today.replace(day=1)
    return {
        "this quarter (to date)": (q0, today + timedelta(days=1)),
        "last quarter": (lq0, q0),
        "the quarter before last quarter": (pq0, lq0),
        "this month (to date)": (m0, today + timedelta(days=1)),
        "last month": (_add_months(m0, -1), m0),
        "this year (to date)": (date(today.year, 1, 1), today + timedelta(days=1)),
        "last year": (date(today.year - 1, 1, 1), date(today.year, 1, 1)),
        "last 30 days": (today - timedelta(days=30), today + timedelta(days=1)),
        "last 90 days": (today - timedelta(days=90), today + timedelta(days=1)),
    }


def describe_windows(today: date) -> str:
    lines = []
    for name, (start, end) in date_windows(today).items():
        last_day = end - timedelta(days=1)
        lines.append(f"- {name}: {start} to {last_day} inclusive  =>  >= '{start}' AND < '{end}'")
    return "\n".join(lines)
