import os

import pytest

# Tests talk to a real Postgres seeded from db/init. Override with DATABASE_URL.
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
