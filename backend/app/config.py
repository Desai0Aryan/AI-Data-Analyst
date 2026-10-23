"""Application settings, loaded from environment variables (see .env.example)."""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # The API connects as the least-privilege analyst_ro role, never as the owner.
    database_url: str = "postgresql://analyst_ro:ro_secret@localhost:5432/analytics"

    max_rows: int = 1000
    statement_timeout_ms: int = 5000

    # "Today" for the demo dataset. Orders end 2025-12-31, so with this date
    # "last quarter" means Q4 2025. Used by the LLM prompts in Part 2.
    reference_date: str = "2026-01-15"

    # --- LLM (provider-agnostic) ---
    llm_provider: str = "anthropic"          # "anthropic" | "openai" (also any OpenAI-compatible server)
    llm_api_key: str = ""
    llm_model: str = ""                      # empty -> sensible default per provider
    llm_base_url: str = ""                   # empty -> provider default; set for Ollama/vLLM/Azure etc.
    llm_temperature: float = 0.0             # 0 = as deterministic as possible (good for SQL + evals)
    llm_max_tokens: int = 1500
    llm_timeout_s: float = 60.0

    # Total SQL generation attempts per question (1 initial + repairs).
    max_attempts: int = 3

    cors_origins: list[str] = ["http://localhost:5173", "http://localhost:3000"]


@lru_cache
def get_settings() -> Settings:
    return Settings()
