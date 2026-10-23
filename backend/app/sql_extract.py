"""Pull SQL (or a refusal) out of a free-text LLM reply."""
from __future__ import annotations

import re
from dataclasses import dataclass

_FENCE = re.compile(r"```[ \t]*(?:sql|postgresql|postgres|pgsql)?[ \t]*\n?(.*?)(?:```|\Z)", re.S | re.I)
_CANNOT = re.compile(r"CANNOT_ANSWER\s*:?\s*(.*)", re.S)
_LOOKS_LIKE_SQL = re.compile(r"^\s*(?:with\b|select\b|\()", re.I)


@dataclass
class Parsed:
    sql: str | None = None
    cannot_answer_reason: str | None = None


def extract_sql(reply: str) -> Parsed:
    text = (reply or "").strip()
    fences = [f.strip() for f in _FENCE.findall(text) if f.strip()]

    if not fences:
        m = _CANNOT.search(text)
        if m:
            return Parsed(cannot_answer_reason=(m.group(1).strip().splitlines() or ["unspecified"])[0] or "unspecified")

    if fences:
        return Parsed(sql=fences[-1].rstrip(";").strip())   # last block wins if the model self-corrected

    if _LOOKS_LIKE_SQL.match(text):
        return Parsed(sql=text.rstrip(";").strip())
    return Parsed()
