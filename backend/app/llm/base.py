from __future__ import annotations

from typing import Protocol


class LLMError(Exception):
    """The LLM provider failed (network, auth, rate limit, bad response)."""


class LLMNotConfigured(LLMError):
    """No API key / unknown provider."""


class LLMClient(Protocol):
    model: str

    def complete(self, system: str, messages: list[dict[str, str]]) -> str:
        """Send a conversation, return the assistant's text.

        ``messages`` is a list of {"role": "user" | "assistant", "content": str}.
        """
        ...
