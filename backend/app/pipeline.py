"""Question -> SQL -> guarded execution -> validation, with a repair loop.

    ask LLM  ──►  extract SQL  ──►  guard  ──►  execute  ──►  result checks
        ▲                              │           │               │
        └──── error / suspicious ──────┴───────────┴───────────────┘   (up to MAX_ATTEMPTS)

Every attempt is recorded so the UI can show the full trace (great for a demo).
Robustness rule: once we hold *a* runnable result, later failures never discard it;
the loop falls back to the best result and surfaces warnings instead of failing.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from . import prompts, services
from .config import Settings, get_settings
from .db import QueryResult
from .llm import LLMClient
from .result_checks import Issue, check_result
from .schema import get_schema
from .sql_extract import extract_sql
from .sql_guard import GuardResult


@dataclass
class Attempt:
    number: int
    sql: str | None
    outcome: str           # ok | no_sql | rejected_by_guard | database_error | timeout | suspicious_result | cannot_answer
    detail: str | None = None


@dataclass
class Outcome:
    status: str                              # ok | failed | cannot_answer
    question: str
    attempts: list[Attempt] = field(default_factory=list)
    sql: str | None = None                   # final, normalized SQL
    tables: list[str] = field(default_factory=list)
    result: QueryResult | None = None
    warnings: list[str] = field(default_factory=list)
    message: str | None = None               # explanation for failed / cannot_answer


def answer_question(
    question: str,
    llm: LLMClient,
    *,
    schema_prompt: str | None = None,
    settings: Settings | None = None,
) -> Outcome:
    settings = settings or get_settings()
    schema_prompt = schema_prompt if schema_prompt is not None else get_schema().to_prompt()
    today = date.fromisoformat(settings.reference_date)
    system = prompts.build_system_prompt(schema_prompt, today)

    messages: list[dict[str, str]] = [{"role": "user", "content": question}]
    out = Outcome(status="failed", question=question)
    fallback: tuple[GuardResult, QueryResult, list[Issue]] | None = None

    def finish_with_fallback(note: str | None = None) -> Outcome:
        guarded, result, issues = fallback  # type: ignore[misc]
        out.status, out.sql, out.tables, out.result = "ok", guarded.sql, guarded.tables, result
        out.warnings = [*guarded.warnings, *(i.message for i in issues)]
        if note:
            out.warnings.append(note)
        return out

    for n in range(1, settings.max_attempts + 1):
        raw = llm.complete(system, messages)
        parsed = extract_sql(raw)
        messages.append({"role": "assistant", "content": raw})

        # --- model declined ---
        if parsed.cannot_answer_reason:
            out.attempts.append(Attempt(n, None, "cannot_answer", parsed.cannot_answer_reason))
            if fallback:
                return finish_with_fallback()
            out.status, out.message = "cannot_answer", parsed.cannot_answer_reason
            return out

        # --- no SQL in reply ---
        if not parsed.sql:
            out.attempts.append(Attempt(n, None, "no_sql", "Reply contained no SQL."))
            messages.append({"role": "user", "content": prompts.repair_message(None, "format", "No SQL block found.")})
            continue

        # --- guard + execute ---
        try:
            guarded, result = services.run_sql(parsed.sql)
        except services.QueryFailure as f:
            outcome = {"guard": "rejected_by_guard", "database": "timeout" if f.code == "timeout" else "database_error"}[f.stage]
            out.attempts.append(Attempt(n, parsed.sql, outcome, f.message))
            if fallback:   # a repair attempt broke things: keep the earlier runnable result
                return finish_with_fallback()
            messages.append({"role": "user", "content": prompts.repair_message(parsed.sql, f.stage, f.message)})
            continue

        # --- semantic checks ---
        issues = check_result(result)
        repairable = [i for i in issues if i.repairable]
        same_as_before = fallback is not None and fallback[0].sql == guarded.sql
        last_chance = n == settings.max_attempts

        if not repairable or same_as_before or last_chance:
            out.attempts.append(Attempt(n, guarded.sql, "ok", None))
            fallback = (guarded, result, issues)
            note = "The model re-checked this query and kept it unchanged." if same_as_before else None
            return finish_with_fallback(note)

        out.attempts.append(Attempt(n, guarded.sql, "suspicious_result", "; ".join(i.message for i in repairable)))
        fallback = (guarded, result, issues)
        messages.append({"role": "user", "content": prompts.suspicious_result_message(guarded.sql, [i.message for i in repairable])})

    if fallback:
        return finish_with_fallback()
    last = out.attempts[-1] if out.attempts else None
    out.message = (
        f"Could not produce a working query after {settings.max_attempts} attempts."
        + (f" Last problem: {last.detail}" if last and last.detail else "")
    )
    return out
