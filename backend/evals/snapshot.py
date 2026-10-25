"""Pins the golden results to evals/golden_snapshot.json so dataset or golden-SQL drift is caught.

Regenerate deliberately (after changing the seed data or a golden query):
    python -m evals.snapshot
"""
from __future__ import annotations

import json
from pathlib import Path

from app import services

from .cases import CASES

PATH = Path(__file__).parent / "golden_snapshot.json"


def current() -> dict:
    snap = {}
    for c in CASES:
        if c.expect != "match":
            continue
        _, res = services.run_sql(c.golden_sql)
        snap[c.id] = {"columns": [col["name"] for col in res.columns], "rows": res.rows}
    return snap


def main() -> None:
    PATH.write_text(json.dumps(current(), indent=1, ensure_ascii=False) + "\n")
    print(f"wrote {PATH}")


if __name__ == "__main__":
    main()
