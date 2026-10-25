"""Render an evaluation Report as console text or Markdown."""
from __future__ import annotations

from .runner import Report

W = 78


def _bar(frac: float, width: int = 20) -> str:
    filled = round(frac * width)
    return "#" * filled + "." * (width - filled)


def console(report: Report, verbose_failures: bool = True) -> str:
    lines = [f"Model: {report.model}", ""]
    lines.append(f"{'case':34}{'category':13}{'result':8}{'tries':6}time")
    lines.append("-" * W)
    for r in report.results:
        mark = "PASS" if r.passed else "FAIL"
        lines.append(f"{r.id:34}{r.category:13}{mark:8}{r.attempts:<6}{r.elapsed_s:.2f}s" + ("  [!]" if r.flags else ""))
    lines += ["", "By category", "-" * W]
    for cat, (p, t) in report.by_category().items():
        lines.append(f"{cat:14}{_bar(p / t)} {p}/{t}")
    lines += [
        "", "Summary", "-" * W,
        f"Accuracy              {report.passed}/{report.total}  ({report.accuracy:.0%})",
        f"Correct first try     {report.first_try}",
        f"Recovered by repair   {report.recovered_by_repair}",
        f"Avg attempts / case   {report.avg_attempts:.2f}",
        f"Database integrity    {'OK (no table changed)' if report.integrity_ok else 'VIOLATED: ' + report.integrity_detail}",
    ]
    failures = [r for r in report.results if not r.passed]
    if failures and verbose_failures:
        lines += ["", f"Failures ({len(failures)})", "=" * W]
        for r in failures:
            lines += [f"* {r.id}  [{r.category}]", f"  question : {r.question}", f"  why      : {r.reason}",
                      f"  trap     : {r.trap}"]
            if r.generated_sql:
                lines.append("  generated: " + " ".join(r.generated_sql.split())[:400])
            lines.append("")
    flagged = [r for r in report.results if r.flags]
    if flagged:
        lines += ["Lint warnings", "-" * W] + [f"  {r.id}: {'; '.join(r.flags)}" for r in flagged]
    return "\n".join(lines)


def markdown(report: Report) -> str:
    s = report
    out = [
        f"## Text-to-SQL evaluation: `{s.model}`", "",
        f"**Accuracy: {s.passed}/{s.total} ({s.accuracy:.0%})** | first try: {s.first_try} | "
        f"recovered by repair: {s.recovered_by_repair} | avg attempts: {s.avg_attempts:.2f} | "
        f"DB integrity: {'OK' if s.integrity_ok else 'VIOLATED'}", "",
        "| Category | Passed | |", "|---|---|---|",
    ]
    for cat, (p, t) in s.by_category().items():
        out.append(f"| {cat} | {p}/{t} | `{_bar(p / t, 10)}` |")
    out += ["", "| Case | Result | Tries | Notes |", "|---|---|---|---|"]
    for r in s.results:
        note = r.reason.replace("|", "/") if not r.passed else ("; ".join(r.flags))
        out.append(f"| {r.id} | {'PASS' if r.passed else '**FAIL**'} | {r.attempts} | {note} |")
    fails = [r for r in s.results if not r.passed]
    if fails:
        out += ["", "### Failures", ""]
        for r in fails:
            out += [f"**{r.id}** ({r.category}): {r.question}", f"- why: {r.reason}", f"- trap: {r.trap}"]
            if r.generated_sql:
                out += ["", "```sql", r.generated_sql, "```"]
            out.append("")
    return "\n".join(out)
