"""Evaluation CLI.

  python -m evals.run                                  # offline replay of the reference recording
  python -m evals.run --recording evals/recordings/naive.json
  python -m evals.run --mode live                      # call your real LLM (needs LLM_API_KEY)
  python -m evals.run --mode live --record evals/recordings/mine.json   # save it for later replay
  python -m evals.run --category traps --min-accuracy 0.9 --markdown out.md --json out.json
"""
from __future__ import annotations

import argparse
import json
import sys

from app.llm import LLMError, RecordingLLM, ReplayLLM, get_llm

from . import report as rep
from .cases import CASES
from .runner import run_all


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="evals.run", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--mode", choices=["replay", "live"], default="replay")
    ap.add_argument("--recording", default="evals/recordings/reference.json", help="replay file (replay mode)")
    ap.add_argument("--record", metavar="PATH", help="live mode: save replies to PATH for later replay")
    ap.add_argument("--category", action="append", help="only run this category (repeatable)")
    ap.add_argument("--case", action="append", help="only run this case id (repeatable)")
    ap.add_argument("--min-accuracy", type=float, default=None, help="exit 1 if accuracy is below this (0-1)")
    ap.add_argument("--json", dest="json_path")
    ap.add_argument("--markdown", dest="md_path")
    ap.add_argument("--quiet", action="store_true", help="hide failure details")
    args = ap.parse_args(argv)

    cases = [c for c in CASES
             if (not args.category or c.category in args.category) and (not args.case or c.id in args.case)]
    if not cases:
        print("No cases selected.", file=sys.stderr)
        return 2

    try:
        llm = ReplayLLM.from_file(args.recording) if args.mode == "replay" else get_llm()
    except LLMError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 2
    if args.record:
        if args.mode != "live":
            print("--record only makes sense with --mode live", file=sys.stderr)
            return 2
        llm = RecordingLLM(llm)

    print(f"Running {len(cases)} cases ({args.mode})...\n", file=sys.stderr)
    report = run_all(llm, cases)

    print(rep.console(report, verbose_failures=not args.quiet))
    if args.json_path:
        with open(args.json_path, "w") as f:
            json.dump(report.to_dict(), f, indent=2)
    if args.md_path:
        with open(args.md_path, "w") as f:
            f.write(rep.markdown(report))
    if args.record:
        llm.save(args.record, name="recorded")
        print(f"\nSaved recording to {args.record}")

    if not report.integrity_ok:
        return 3
    if args.min_accuracy is not None and report.accuracy < args.min_accuracy:
        print(f"\nAccuracy {report.accuracy:.0%} is below the required {args.min_accuracy:.0%}.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
