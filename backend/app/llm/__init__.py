from functools import lru_cache

from ..config import get_settings
from .base import LLMClient, LLMError, LLMNotConfigured
from .http_clients import AnthropicClient, OpenAIClient
from .replay import RecordingLLM, ReplayLLM

__all__ = ["LLMClient", "LLMError", "LLMNotConfigured", "RecordingLLM", "ReplayLLM", "get_llm"]


@lru_cache
def get_llm() -> LLMClient:
    """FastAPI dependency. Override in tests with app.dependency_overrides."""
    s = get_settings()
    provider = s.llm_provider.lower().strip()
    if provider == "replay":                 # keyless demo / offline mode
        return ReplayLLM.from_file(s.llm_replay_file)
    if provider not in {"anthropic", "openai"}:
        raise LLMNotConfigured(f"Unknown LLM_PROVIDER '{s.llm_provider}'. Use 'anthropic', 'openai' or 'replay'.")
    # Local OpenAI-compatible servers (Ollama etc.) don't need a key; hosted providers do.
    if not s.llm_api_key and not (provider == "openai" and s.llm_base_url):
        raise LLMNotConfigured("LLM_API_KEY is not set. Add it to your .env file (see .env.example).")
    cls = AnthropicClient if provider == "anthropic" else OpenAIClient
    return cls(
        api_key=s.llm_api_key,
        model=s.llm_model,
        base_url=s.llm_base_url,
        temperature=s.llm_temperature,
        max_tokens=s.llm_max_tokens,
        timeout_s=s.llm_timeout_s,
    )
