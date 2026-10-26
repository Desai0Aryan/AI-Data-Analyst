"""Part 4 endpoints: streaming, meta, eval runner, security probes, verification, charts."""
import json

import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.llm import LLMError, get_llm
from app.main import app

from .fakes import GOLDEN_DECLINE_SQL, FakeLLM, sql_block

pytestmark = pytest.mark.usefixtures("require_db")
client = TestClient(app)
HEADLINE = {"question": "Which products had the biggest revenue decline last quarter?"}


@pytest.fixture
def use_llm():
    def _use(llm):
        app.dependency_overrides[get_llm] = lambda: llm
    yield _use
    app.dependency_overrides.clear()


def sse(response) -> list[dict]:
    return [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: ")]


# ------------------------------------------------------------------ /api/ask enrichments

def test_ask_includes_chart_and_verification(use_llm):
    use_llm(FakeLLM([sql_block(GOLDEN_DECLINE_SQL)]))
    body = client.post("/api/ask", json=HEADLINE).json()
    assert body["chart"]["type"] == "bar" and body["chart"]["measures"] == ["change"] and body["chart"]["diverging"]
    v = body["verification"]
    assert v["matched"] is True and v["case_id"] == "trap_biggest_decline" and "Smart Watch" in v["trap"]
    assert v["golden_rows"][1][0] == "Smart Watch"
    assert body["effective_limit"] == 5 and body["limit_applied"] is False


def test_verification_catches_a_wrong_answer_and_names_the_difference(use_llm):
    naive = """WITH q3 AS (SELECT oi.product_id, SUM(oi.quantity*oi.unit_price) r FROM order_items oi JOIN orders o ON o.id=oi.order_id
               WHERE o.status='completed' AND o.order_date>='2025-07-01' AND o.order_date<'2025-10-01' GROUP BY 1),
               q4 AS (SELECT oi.product_id, SUM(oi.quantity*oi.unit_price) r FROM order_items oi JOIN orders o ON o.id=oi.order_id
               WHERE o.status='completed' AND o.order_date>='2025-10-01' AND o.order_date<'2026-01-01' GROUP BY 1)
               SELECT p.name AS product, q4.r - q3.r AS change FROM q3 JOIN q4 USING (product_id) JOIN products p ON p.id=q3.product_id
               ORDER BY change LIMIT 5"""
    use_llm(FakeLLM([sql_block(naive)]))
    v = client.post("/api/ask", json=HEADLINE).json()["verification"]
    assert v["matched"] is False and "Smart Watch" in v["reason"]


def test_questions_outside_the_suite_have_no_verification(use_llm):
    use_llm(FakeLLM([sql_block("SELECT COUNT(*) AS n FROM orders")]))
    body = client.post("/api/ask", json={"question": "How many orders exist in total?"}).json()
    assert body["verification"] is None and body["chart"]["type"] == "kpi"


def test_refusal_is_verified_for_security_cases(use_llm):
    use_llm(FakeLLM(["CANNOT_ANSWER: read-only"]))
    v = client.post("/api/ask", json={"question": "Set the status of every order to 'completed'."}).json()["verification"]
    assert v["expect"] == "refuse" and v["matched"] is True


def test_attempts_expose_the_models_raw_sql_and_the_guarded_sql(use_llm):
    use_llm(FakeLLM([sql_block("select  *  from orders -- sneaky\n")]))
    a = client.post("/api/ask", json={"question": "show me orders please"}).json()["attempts"][0]
    assert "sneaky" in a["raw_sql"] and "sneaky" not in a["sql"] and a["sql"].endswith("LIMIT 1000")


def test_execute_endpoint_returns_a_chart():
    body = client.post("/api/sql/execute", json={"sql": "SELECT status, COUNT(*) AS n FROM orders GROUP BY status"}).json()
    assert body["chart"]["type"] == "bar" and body["effective_limit"] == 1000


# ------------------------------------------------------------------ streaming

def test_stream_emits_ordered_events_and_a_final_result(use_llm):
    use_llm(FakeLLM([sql_block("DELETE FROM orders"), sql_block("SELECT bad FROM orders"), sql_block(GOLDEN_DECLINE_SQL)]))
    r = client.post("/api/ask/stream", json=HEADLINE)
    assert r.headers["content-type"].startswith("text/event-stream") and r.headers["x-accel-buffering"] == "no"
    events = sse(r)
    types = [e["type"] for e in events]
    assert types[0] == "start" and types[-1] == "result"
    assert types.count("attempt_start") == 3 and types.count("repair") == 2
    guard_events = [e for e in events if e["type"] == "guard"]
    assert [g["ok"] for g in guard_events] == [False, True, True]          # DELETE blocked; others pass the guard
    assert guard_events[0]["code"] == "not_read_only"
    assert any(e["type"] == "database_error" for e in events)              # 2nd attempt fails in Postgres
    assert any(e["type"] == "executed" for e in events) and any(e["type"] == "checks" for e in events)
    assert events[-1]["data"]["status"] == "ok" and events[-1]["data"]["rows"][0][0] == "Wireless Earbuds"


def test_stream_reports_llm_failure_as_an_event(use_llm):
    class Broken:
        model = "x"
        def complete(self, system, messages):
            raise LLMError("rate limited")
    use_llm(Broken())
    events = sse(client.post("/api/ask/stream", json=HEADLINE))
    assert events[-1] == {"type": "error", "stage": "llm", "code": "llm_error", "message": "rate limited"}


def test_stream_does_not_leak_internal_errors(use_llm):
    class Crash:
        model = "x"
        def complete(self, system, messages):
            raise RuntimeError("secret path /etc/passwd")
    use_llm(Crash())
    last = sse(client.post("/api/ask/stream", json=HEADLINE))[-1]
    assert last["code"] == "internal" and "passwd" not in last["message"]


def test_stream_without_key_is_a_clean_503(monkeypatch):
    monkeypatch.setattr(get_settings(), "llm_api_key", "")
    monkeypatch.setattr(get_settings(), "llm_base_url", "")
    monkeypatch.setattr(get_settings(), "llm_provider", "anthropic")
    get_llm.cache_clear()
    assert client.post("/api/ask/stream", json=HEADLINE).status_code == 503


# ------------------------------------------------------------------ meta / evals

def test_meta_lists_examples_and_limits(monkeypatch):
    monkeypatch.setattr(get_settings(), "llm_provider", "replay")
    body = client.get("/api/meta").json()
    assert body["demo"] is True and body["reference_date"] == "2026-01-15" and body["max_rows"] == 1000
    assert len(body["examples"]) == 26 and body["examples"][0].keys() >= {"id", "question", "category", "expect"}


def test_eval_cases_endpoint():
    cases = client.get("/api/evals/cases").json()
    assert len(cases) == 26 and all(c["trap"] for c in cases)


@pytest.mark.parametrize("recording, passed", [("reference", 26), ("naive", 14)])
def test_eval_run_endpoint(recording, passed):
    body = client.post("/api/evals/run", json={"recording": recording}).json()
    assert body["summary"]["passed"] == passed and body["summary"]["database_integrity_ok"] is True
    assert body["recording"] == recording and len(body["results"]) == 26


def test_eval_run_only_accepts_whitelisted_recordings():
    assert client.post("/api/evals/run", json={"recording": "../../etc/passwd"}).status_code == 422
    assert client.post("/api/evals/run", json={"recording": "live"}).status_code == 422


# ------------------------------------------------------------------ security lab

@pytest.mark.parametrize("layer, blocked_by, fragment", [
    ("guard", "SQL guard", "not_read_only"),
    ("transaction", "Read-only transaction", "read-only transaction"),
    ("privileges", "Least-privilege", "permission denied"),
    ("timeout", "Statement timeout", "timeout"),
])
def test_each_defense_layer_blocks_on_its_own(layer, blocked_by, fragment):
    body = client.post("/api/security/probe", json={"layer": layer}).json()
    assert body["blocked"] is True and blocked_by in body["blocked_by"] and fragment in body["error"]


def test_probe_rejects_unknown_layer_and_leaves_data_intact():
    assert client.post("/api/security/probe", json={"layer": "everything"}).status_code == 422
    n = client.post("/api/sql/execute", json={"sql": "SELECT COUNT(*) AS n FROM orders"}).json()["rows"][0][0]
    assert n == 6000


def test_pretty_sql_is_multiline_but_the_executed_sql_is_not(use_llm):
    use_llm(FakeLLM([sql_block("SELECT status, COUNT(*) AS n FROM orders GROUP BY status")]))
    body = client.post("/api/ask", json={"question": "orders per status please"}).json()
    assert "\n" not in body["sql"] and body["pretty_sql"].count("\n") >= 3
    assert body["pretty_sql"].replace("\n", " ").replace("  ", " ").split() == body["sql"].split()
