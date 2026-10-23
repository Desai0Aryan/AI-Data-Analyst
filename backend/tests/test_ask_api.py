import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.llm import LLMError, get_llm
from app.main import app

from .fakes import GOLDEN_DECLINE_SQL, FakeLLM, sql_block

pytestmark = pytest.mark.usefixtures("require_db")
client = TestClient(app)
Q = {"question": "Which products had the biggest revenue decline last quarter?"}


@pytest.fixture
def use_llm():
    def _use(llm):
        app.dependency_overrides[get_llm] = lambda: llm
    yield _use
    app.dependency_overrides.clear()


def test_ask_success_returns_result_and_trace(use_llm):
    use_llm(FakeLLM([sql_block("SELECT bad FROM orders"), sql_block(GOLDEN_DECLINE_SQL)]))
    body = client.post("/api/ask", json=Q).json()
    assert body["status"] == "ok" and body["model"] == "fake-model"
    assert body["rows"][0][0] == "Wireless Earbuds"
    assert [c["name"] for c in body["columns"]] == ["product", "prev_quarter_revenue", "last_quarter_revenue", "change"]
    assert [a["outcome"] for a in body["attempts"]] == ["database_error", "ok"]
    assert body["sql"].endswith("LIMIT 5")


def test_ask_failure_is_http_200_with_trace(use_llm):
    use_llm(FakeLLM([sql_block("DROP TABLE orders")] * 3))
    r = client.post("/api/ask", json=Q)
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "failed" and len(body["attempts"]) == 3 and body["rows"] == []


def test_ask_cannot_answer(use_llm):
    use_llm(FakeLLM(["CANNOT_ANSWER: no such data"]))
    assert client.post("/api/ask", json={"question": "What's the weather?"}).json()["status"] == "cannot_answer"


def test_ask_without_api_key_gives_clear_503(monkeypatch):
    monkeypatch.setattr(get_settings(), "llm_api_key", "")
    monkeypatch.setattr(get_settings(), "llm_base_url", "")
    get_llm.cache_clear()
    r = client.post("/api/ask", json=Q)
    assert r.status_code == 503 and r.json()["detail"]["code"] == "not_configured"


def test_ask_provider_failure_is_502(use_llm):
    class Broken:
        model = "x"
        def complete(self, system, messages):
            raise LLMError("rate limited")
    use_llm(Broken())
    r = client.post("/api/ask", json=Q)
    assert r.status_code == 502 and r.json()["detail"]["message"] == "rate limited"


@pytest.mark.parametrize("payload", [{"question": "hi"}, {"question": "x" * 1001}, {}])
def test_ask_input_validation(payload, use_llm):
    use_llm(FakeLLM([]))
    assert client.post("/api/ask", json=payload).status_code == 422


def test_database_down_returns_clean_503(monkeypatch):
    """No bare 500s: an unreachable database is reported as a structured 503."""
    import psycopg_pool
    from app import db, schema

    def boom():
        raise psycopg_pool.PoolTimeout("pool initialization incomplete after 5 sec")

    monkeypatch.setattr(db, "get_pool", boom)
    schema.get_schema.cache_clear()
    try:
        r = client.post("/api/sql/execute", json={"sql": "SELECT 1"})
    finally:
        schema.get_schema.cache_clear()
    assert r.status_code == 503 and r.json()["detail"]["code"] == "unavailable"
