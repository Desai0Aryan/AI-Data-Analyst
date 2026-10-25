"""Replay and recording LLM wrappers.

ReplayLLM    serves pre-recorded replies, keyed by question. Use cases:
               * offline / CI evaluation (no API key, deterministic, free)
               * a keyless demo (LLM_PROVIDER=replay)
RecordingLLM wraps a real client and saves every reply so a live run can be replayed later.

Recording format (JSON):
    {"meta": {...}, "answers": {"<question>": ["<reply 1>", "<reply 2 after repair>", ...]}}

Replay is stateless: the reply index is the number of assistant turns already in the
conversation, so a repair conversation gets reply #2 and concurrent requests never collide.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from .base import LLMClient, LLMError


def normalize_question(q: str) -> str:
    return re.sub(r"[\s]+", " ", q.strip().lower()).rstrip("?.! ")


def _question_of(messages: list[dict[str, str]]) -> str:
    return next(m["content"] for m in messages if m["role"] == "user")


class ReplayLLM:
    def __init__(self, answers: dict[str, list[str]], model: str = "replay"):
        self.model = model
        self._answers = {normalize_question(q): replies for q, replies in answers.items()}
        self._examples = list(answers)[:3]

    @classmethod
    def from_file(cls, path: str | Path) -> "ReplayLLM":
        p = Path(path)
        if not p.exists():
            raise LLMError(f"Replay file not found: {p}")
        data = json.loads(p.read_text())
        name = data.get("meta", {}).get("name", p.stem)
        return cls(data["answers"], model=f"replay:{name}")

    def complete(self, system: str, messages: list[dict[str, str]]) -> str:
        question = _question_of(messages)
        replies = self._answers.get(normalize_question(question))
        if replies is None:
            hint = "; ".join(f'"{q}"' for q in self._examples)
            return f"CANNOT_ANSWER: Demo mode only knows recorded questions. Try one of: {hint}"
        turn = sum(1 for m in messages if m["role"] == "assistant")
        if turn >= len(replies):
            raise LLMError(f"Recording exhausted: no reply #{turn + 1} recorded for this question.")
        return replies[turn]


class RecordingLLM:
    """Pass-through wrapper that remembers every reply."""

    def __init__(self, inner: LLMClient):
        self.inner = inner
        self.model = getattr(inner, "model", "unknown")
        self.answers: dict[str, list[str]] = {}

    def complete(self, system: str, messages: list[dict[str, str]]) -> str:
        reply = self.inner.complete(system, messages)
        question = _question_of(messages)
        turn = sum(1 for m in messages if m["role"] == "assistant")
        replies = self.answers.setdefault(question, [])
        del replies[turn:]                  # a re-run of the same question overwrites older takes
        replies.append(reply)
        return reply

    def save(self, path: str | Path, name: str = "recorded") -> None:
        payload = {"meta": {"name": name, "model": self.model}, "answers": self.answers}
        Path(path).write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
