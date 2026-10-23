"""Minimal LLM clients over plain HTTP (httpx): no vendor SDKs, easy to test and to swap.

- AnthropicClient: Anthropic Messages API
- OpenAIClient:    OpenAI Chat Completions API; also works with any OpenAI-compatible
                   server (Ollama, vLLM, LM Studio, Azure...) via ``base_url``.
"""
from __future__ import annotations

import time

import httpx

from .base import LLMError

_RETRY_STATUS = {429, 500, 502, 503, 504, 529}


class _BaseHTTPClient:
    default_base_url = ""
    default_model = ""

    def __init__(
        self,
        api_key: str,
        model: str = "",
        base_url: str = "",
        temperature: float = 0.0,
        max_tokens: int = 1500,
        timeout_s: float = 60.0,
        max_retries: int = 2,
        transport: httpx.BaseTransport | None = None,   # injected in tests
    ):
        self.api_key = api_key
        self.model = model or self.default_model
        self.base_url = (base_url or self.default_base_url).rstrip("/")
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.max_retries = max_retries
        self._http = httpx.Client(timeout=timeout_s, transport=transport)

    # subclasses implement these three
    def _url(self) -> str: raise NotImplementedError
    def _headers(self) -> dict[str, str]: raise NotImplementedError
    def _payload(self, system: str, messages: list[dict[str, str]]) -> dict: raise NotImplementedError
    def _parse(self, data: dict) -> str: raise NotImplementedError

    def complete(self, system: str, messages: list[dict[str, str]]) -> str:
        last_error = "unknown error"
        for attempt in range(self.max_retries + 1):
            try:
                resp = self._http.post(self._url(), headers=self._headers(), json=self._payload(system, messages))
            except httpx.HTTPError as e:
                last_error = f"network error: {e}"
            else:
                if resp.status_code == 200:
                    try:
                        text = self._parse(resp.json())
                    except (KeyError, IndexError, TypeError, ValueError) as e:
                        raise LLMError(f"Unexpected response format from LLM provider: {e}") from e
                    if not text.strip():
                        raise LLMError("The LLM returned an empty response.")
                    return text
                last_error = f"HTTP {resp.status_code}: {resp.text[:300]}"
                if resp.status_code not in _RETRY_STATUS:
                    raise LLMError(f"LLM request failed ({last_error})")
            if attempt < self.max_retries:
                time.sleep(2 ** attempt)   # 1s, 2s
        raise LLMError(f"LLM request failed after {self.max_retries + 1} attempts ({last_error})")


class AnthropicClient(_BaseHTTPClient):
    default_base_url = "https://api.anthropic.com"
    default_model = "claude-sonnet-5-5"

    def _url(self) -> str:
        return f"{self.base_url}/v1/messages"

    def _headers(self) -> dict[str, str]:
        return {"x-api-key": self.api_key, "anthropic-version": "2023-06-01", "content-type": "application/json"}

    def _payload(self, system, messages) -> dict:
        return {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
            "system": system,
            "messages": messages,
        }

    def _parse(self, data: dict) -> str:
        return "".join(block["text"] for block in data["content"] if block.get("type") == "text")


class OpenAIClient(_BaseHTTPClient):
    default_base_url = "https://api.openai.com/v1"
    default_model = "gpt-4o"

    def _url(self) -> str:
        return f"{self.base_url}/chat/completions"

    def _headers(self) -> dict[str, str]:
        return {"authorization": f"Bearer {self.api_key}", "content-type": "application/json"}

    def _payload(self, system, messages) -> dict:
        return {
            "model": self.model,
            "temperature": self.temperature,
            "max_completion_tokens": self.max_tokens,
            "messages": [{"role": "system", "content": system}, *messages],
        }

    def _parse(self, data: dict) -> str:
        return data["choices"][0]["message"]["content"] or ""
