"""Chart recommendation: pick a sensible visualization from the *shape* of a result.

The frontend renders whatever spec this returns (and lets the user switch among
``alternatives``), so the chart is always derived from the actual query result, never invented.

Rules, in priority order
  no rows                         -> empty
  one row, numeric measure(s)     -> kpi
  no numeric measure              -> table
  date/timestamp + measure(s)     -> line (bar when fewer than 3 points)
  category + measure(s)           -> bar (horizontal when long/many labels); table when > 40 categories
  only numeric columns            -> scatter (>= 5 rows) else table
Measures: id-like columns are labels, not measures. If a column is named like change/delta/diff/growth
it becomes the single default measure (the "story" column). Columns on wildly different scales are
not drawn on the same axis. Negative values switch on ``diverging`` (colored by sign).
"""
from __future__ import annotations

import re
from typing import Any

NUMERIC = {"int2", "int4", "int8", "numeric", "float4", "float8", "money"}
TEMPORAL = {"date", "timestamp", "timestamptz"}
_ID_LIKE = re.compile(r"(^id$|_id$|^id_)", re.I)
_STORY = re.compile(r"change|delta|diff|growth|variance", re.I)
MAX_CATEGORIES = 40


def _is_measure(col: dict[str, str]) -> bool:
    return col["type"] in NUMERIC and not _ID_LIKE.search(col["name"])


def _abs_max(values: list[Any]) -> float:
    nums = [abs(float(v)) for v in values if isinstance(v, (int, float)) and not isinstance(v, bool)]
    return max(nums) if nums else 0.0


def recommend_chart(columns: list[dict[str, str]], rows: list[list[Any]]) -> dict[str, Any]:
    spec: dict[str, Any] = {
        "type": "table", "x": None, "measures": [], "available_measures": [], "alternatives": [],
        "horizontal": False, "diverging": False, "reason": "",
    }
    if not rows:
        return {**spec, "type": "empty", "reason": "The query returned no rows."}

    idx = {c["name"]: i for i, c in enumerate(columns)}
    measures_all = [c["name"] for c in columns if _is_measure(c)]
    temporal = [c["name"] for c in columns if c["type"] in TEMPORAL]
    labels = [c["name"] for c in columns if not _is_measure(c) and c["type"] not in TEMPORAL]
    spec["available_measures"] = measures_all

    def col_values(name: str) -> list[Any]:
        return [r[idx[name]] for r in rows]

    # ---- default measures ----
    story = [m for m in measures_all if _STORY.search(m)]
    if story:
        chosen = story[:1]
    else:
        chosen = []
        base = max(_abs_max(col_values(measures_all[0])), 1e-9) if measures_all else 1
        for m in measures_all[:3]:
            if not chosen or _abs_max(col_values(m)) * 25 >= base and base * 25 >= _abs_max(col_values(m)):
                chosen.append(m)
        chosen = chosen or measures_all[:1]
    spec["measures"] = chosen
    spec["diverging"] = any(
        isinstance(v, (int, float)) and v < 0 for m in chosen for v in col_values(m)
    )

    # ---- choose type ----
    if len(rows) == 1 and measures_all:
        label = labels[0] if labels else (temporal[0] if temporal else None)
        return {**spec, "type": "kpi", "x": label, "measures": measures_all[:4], "diverging": False,
                "alternatives": ["table"], "reason": "A single row with numbers reads best as headline figures."}

    if not measures_all:
        return {**spec, "reason": "No numeric column to plot, so showing the table."}

    if temporal:
        x = temporal[0]
        if len(rows) >= 3:
            return {**spec, "type": "line", "x": x, "alternatives": ["area", "bar", "table"],
                    "reason": f"'{x}' is a date and there are {len(rows)} points, so a trend line."}
        return {**spec, "type": "bar", "x": x, "alternatives": ["line", "table"],
                "reason": "Only a couple of dates, so bars compare them more clearly than a line."}

    if labels:
        x = labels[0]
        if len(rows) > MAX_CATEGORIES:
            return {**spec, "type": "table", "x": x, "alternatives": ["bar"],
                    "reason": f"{len(rows)} categories is too many for a readable chart."}
        longest = max(len(str(v)) for v in col_values(x))
        alternatives = ["table"]
        if len(rows) <= 8 and len(chosen) == 1 and all(
            isinstance(v, (int, float)) and v >= 0 for v in col_values(chosen[0])
        ):
            alternatives.insert(0, "pie")
        return {**spec, "type": "bar", "x": x, "horizontal": len(rows) > 6 or longest > 14,
                "alternatives": alternatives,
                "reason": f"A category ('{x}') compared on {', '.join(chosen)}: bars."}

    if len(measures_all) >= 2 and len(rows) >= 5:
        return {**spec, "type": "scatter", "x": measures_all[0], "measures": [measures_all[1]],
                "alternatives": ["table"], "reason": "Two numeric columns and no label: relationship plot."}
    return {**spec, "reason": "Not enough structure to chart, so showing the table."}
