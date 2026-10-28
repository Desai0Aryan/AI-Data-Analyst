"""Write a *live* evaluation result into the README, between its markers.

    python -m evals.readme_score eval-report.json [--readme ../README.md] [--date 2026-01-31]

It refuses replay reports on purpose: a replayed recording validates the harness, and presenting it as a
model's score would be exactly the kind of overclaim this project exists to prevent.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

START, END = "<!-- live-eval:start -->", "<!-- live-eval:end -->"
DEFAULT_README = Path(__file__).resolve().parents[2] / "README.md"


class ScoreError(Exception):
    pass


def summarize(report: dict, date: str) -> str:
    model = report.get("model", "")
    if not model or model.startswith("replay"):
        raise ScoreError(f"This report is from '{model or 'unknown'}', not a live model. Run `make eval-live` instead.")
    s = report["summary"]
    failed = [r["id"] for r in report["results"] if not r["passed"]]
    shown = ", ".join(f"`{i}`" for i in failed[:8]) + (f" and {len(failed) - 8} more" if len(failed) > 8 else "")
    tail = f" Failed: {shown}." if failed else " No failures."
    return (f"**{s['passed']}/{s['total']} ({round(s['accuracy'] * 100)}%)** with `{model}` on {date}. "
            f"{s['first_try_passes']} right on the first try, {s['recovered_by_repair']} fixed by the repair loop, "
            f"{s['avg_attempts']:.2f} attempts per question on average.{tail}")


def update_readme(readme: Path, report: dict, date: str) -> str:
    text = readme.read_text()
    pattern = re.compile(re.escape(START) + r".*?" + re.escape(END), re.S)
    if not pattern.search(text):
        raise ScoreError(f"Markers {START} ... {END} not found in {readme}.")
    line = summarize(report, date)
    readme.write_text(pattern.sub(lambda _: f"{START}{line}{END}", text, count=1))
    return line


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("report", help="JSON report from `evals.run --mode live --json ...`")
    ap.add_argument("--readme", default=str(DEFAULT_README))
    ap.add_argument("--date", default=datetime.now(timezone.utc).strftime("%Y-%m-%d"))
    args = ap.parse_args(argv)
    try:
        line = update_readme(Path(args.readme), json.loads(Path(args.report).read_text()), args.date)
    except (ScoreError, OSError, ValueError, KeyError) as e:
        print(f"Error: {e}", file=sys.stderr)
        return 2
    print(f"Updated {args.readme}:\n  {line}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
