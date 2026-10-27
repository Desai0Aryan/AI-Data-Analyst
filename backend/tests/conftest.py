import os

import pytest

# Tests talk to a real Postgres seeded from db/init. Override with DATABASE_URL.
# Limits/caching/explanations are off by default so tests stay independent; tests that need them turn them on.
for _k, _v in {"CACHE_TTL_S": "0", "RATE_LIMIT_PER_MINUTE": "0", "DAILY_LLM_BUDGET": "0", "EXPLANATIONS_ENABLED": "false"}.items():
    os.environ.setdefault(_k, _v)
os.environ.setdefault("DATABASE_URL", "postgresql://analyst_ro:ro_secret@localhost:5432/analytics")


def _db_available() -> bool:
    from app import db
    db.get_pool.cache_clear()
    try:
        return db.ping()
    except Exception:
        return False


@pytest.fixture(scope="session")
def require_db():
    if not _db_available():
        pytest.skip("PostgreSQL not reachable. Run `docker compose up -d db` first.")


@pytest.fixture(autouse=True)
def _fresh_state():
    from app import cache, limits
    cache.answers.clear()
    limits.reset()
    yield
    cache.answers.clear()
    limits.reset()
