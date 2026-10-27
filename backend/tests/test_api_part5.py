"""Part 5: written explanations, caching, rate limiting and the daily budget."""
import json

import pytest
from fastapi.testclient import TestClient

from app import cache
from app.config import get_settings
from app.llm import get_llm
from app.main import app

from .fakes import GOLDEN_DECLINE_SQL, FakeLLM, sql_block

pytestmark = pytest.mark.usefixtures("require_db")
client = TestClient(app)
Q = {"question": "Which products had the biggest revenue decline last quarter?"}
SIMPLE = sql_block("SELECT status, COUNT(*) AS n FROM orders GROUP BY status")
GOOD = "Wireless Earbuds had the biggest decline, down $12,934.38, followed by Smart Watch at $10,532.70, which sold nothing last quarter."
BAD = "Wireless Earbuds fell by $50,000, mainly because of a price increase."


@pytest.fixture
def use_llm():
    def _use(llm):
        app.dependency_overrides[get_llm] = lambda: llm
    yield _use
    app.dependency_overrides.clear()


@pytest.fixture
def setting(monkeypatch):
    def _set(**kw):
        for k, v in kw.items():
            monkeypatch.setattr(get_settings(), k, v)
    return _set


def sse(r):
    return [json.loads(l[6:]) for l in r.text.splitlines() if l.startswith("data: ")]


# ------------------------------------------------------------------ explanations

def test_ask_returns_a_grounded_llm_summary(use_llm, setting):
    setting(explanations_enabled=True)
    use_llm(FakeLLM([sql_block(GOLDEN_DECLINE_SQL), GOOD]))
    e = client.post("/api/ask", json=Q).json()["explanation"]
    assert e["source"] == "llm" and e["grounded"] is True and e["text"] == GOOD and e["numbers_checked"] == 2


def test_invented_figure_is_repaired_then_accepted(use_llm, setting):
    setting(explanations_enabled=True)
    llm = FakeLLM([sql_block(GOLDEN_DECLINE_SQL), BAD, GOOD])
    use_llm(llm)
    e = client.post("/api/ask", json=Q).json()["explanation"]
    assert e["source"] == "llm" and e["retried"] is True and e["text"] == GOOD
    assert "$50,000" in llm.calls[2][1][-1]["content"]           # the offending figure was named to the model


def test_persistent_invention_falls_back_to_the_rule_based_summary(use_llm, setting):
    setting(explanations_enabled=True)
    use_llm(FakeLLM([sql_block(GOLDEN_DECLINE_SQL), BAD, BAD]))
    e = client.post("/api/ask", json=Q).json()["explanation"]
    assert e["source"] == "template" and "$50,000" not in e["text"] and e["text"].startswith("The largest decrease is Wireless Earbuds")


def test_no_summary_for_refusals_or_failures(use_llm, setting):
    setting(explanations_enabled=True)
    use_llm(FakeLLM(["CANNOT_ANSWER: no data"]))
    assert client.post("/api/ask", json={"question": "What is the weather?"}).json()["explanation"] is None


def test_summaries_can_be_switched_off(use_llm, setting):
    setting(explanations_enabled=False)
    use_llm(FakeLLM([SIMPLE]))
    body = client.post("/api/ask", json={"question": "orders per status"}).json()
    assert body["explanation"] is None and body["explanation_pending"] is False


def test_replay_demo_mode_uses_rule_based_summaries(setting):
    setting(explanations_enabled=True, llm_provider="replay")
    get_llm.cache_clear()
    try:
        e = client.post("/api/ask", json=Q).json()["explanation"]
    finally:
        get_llm.cache_clear()
    assert e["source"] == "template" and "Wireless Earbuds" in e["text"]


def test_stream_sends_the_result_first_and_the_summary_after(use_llm, setting):
    setting(explanations_enabled=True)
    use_llm(FakeLLM([sql_block(GOLDEN_DECLINE_SQL), GOOD]))
    events = sse(client.post("/api/ask/stream", json=Q))
    types = [e["type"] for e in events]
    assert types[-2:] == ["result", "explanation"]
    result, explanation = events[-2]["data"], events[-1]["data"]
    assert result["explanation_pending"] is True and result["explanation"] is None and result["rows"]
    assert explanation["text"] == GOOD and explanation["source"] == "llm"


def test_stream_summary_failure_degrades_to_rules(use_llm, setting):
    setting(explanations_enabled=True)

    class SqlThenBoom(FakeLLM):
        def complete(self, system, messages):
            if "summary shown above" in system:
                raise RuntimeError("provider exploded")
            return super().complete(system, messages)

    use_llm(SqlThenBoom([sql_block(GOLDEN_DECLINE_SQL)]))
    last = sse(client.post("/api/ask/stream", json=Q))[-1]
    assert last["type"] == "explanation" and last["data"]["source"] == "template"


# ------------------------------------------------------------------ caching

def test_identical_questions_reuse_the_answer_without_calling_the_llm(use_llm, setting):
    setting(cache_ttl_s=60)
    llm = FakeLLM([SIMPLE])                                        # only ONE scripted reply: a 2nd call would fail
    use_llm(llm)
    first = client.post("/api/ask", json={"question": "Orders per status?"}).json()
    again = client.post("/api/ask", json={"question": "  orders per STATUS "}).json()
    assert first["cached"] is False and again["cached"] is True
    assert again["rows"] == first["rows"] and len(llm.calls) == 1


def test_the_free_replay_provider_is_never_cached(use_llm, setting):
    setting(cache_ttl_s=60, llm_provider="replay")
    llm = FakeLLM([SIMPLE, SIMPLE])
    use_llm(llm)
    for _ in range(2):
        assert client.post("/api/ask", json={"question": "orders per status"}).json()["cached"] is False
    assert len(llm.calls) == 2


def test_cache_can_be_disabled(use_llm, setting):
    setting(cache_ttl_s=0)
    llm = FakeLLM([SIMPLE, SIMPLE])
    use_llm(llm)
    for _ in range(2):
        client.post("/api/ask", json={"question": "orders per status"})
    assert len(llm.calls) == 2


def test_failures_are_not_cached(use_llm, setting):
    setting(cache_ttl_s=60)
    llm = FakeLLM([sql_block("SELECT bad FROM orders")] * 3 + [SIMPLE])
    use_llm(llm)
    assert client.post("/api/ask", json={"question": "orders per status"}).json()["status"] == "failed"
    assert client.post("/api/ask", json={"question": "orders per status"}).json()["status"] == "ok"


def test_cache_is_per_model(use_llm, setting):
    setting(cache_ttl_s=60)
    a, b = FakeLLM([SIMPLE]), FakeLLM([SIMPLE])
    a.model, b.model = "model-a", "model-b"
    use_llm(a); client.post("/api/ask", json={"question": "orders per status"})
    use_llm(b); body = client.post("/api/ask", json={"question": "orders per status"}).json()
    assert body["cached"] is False and len(b.calls) == 1


def test_entries_expire(use_llm, setting, monkeypatch):
    setting(cache_ttl_s=60)
    now = [1000.0]
    monkeypatch.setattr(cache.time, "monotonic", lambda: now[0])
    llm = FakeLLM([SIMPLE, SIMPLE])
    use_llm(llm)
    client.post("/api/ask", json={"question": "orders per status"})
    now[0] += 61
    assert client.post("/api/ask", json={"question": "orders per status"}).json()["cached"] is False


def test_cache_evicts_the_oldest_entry():
    c = cache.TTLCache()
    for i in range(3):
        c.set(f"k{i}", i, ttl_s=60, max_entries=2)
    assert c.get("k0") is None and c.get("k1") == 1 and c.get("k2") == 2


def test_stream_serves_cached_answers_instantly_with_their_summary(use_llm, setting):
    setting(cache_ttl_s=60, explanations_enabled=True)
    use_llm(FakeLLM([sql_block(GOLDEN_DECLINE_SQL), GOOD]))
    sse(client.post("/api/ask/stream", json=Q))                    # warm the cache (also stores the summary)
    events = sse(client.post("/api/ask/stream", json=Q))
    assert [e["type"] for e in events] == ["start", "result"]
    data = events[-1]["data"]
    assert data["cached"] is True and data["explanation"]["text"] == GOOD and data["explanation_pending"] is False


# ------------------------------------------------------------------ rate limiting and budget

def test_rate_limit_returns_429_with_retry_after(use_llm, setting):
    setting(rate_limit_per_minute=3)
    use_llm(FakeLLM([SIMPLE] * 5))
    codes = [client.post("/api/ask", json={"question": f"orders per status {i}"}).status_code for i in range(4)]
    assert codes == [200, 200, 200, 429]
    r = client.post("/api/ask", json={"question": "orders per status again"})
    assert r.status_code == 429 and int(r.headers["retry-after"]) >= 1
    assert r.json()["detail"]["code"] == "rate_limited"


def test_rate_limit_applies_to_the_stream_endpoint_too(use_llm, setting):
    setting(rate_limit_per_minute=1)
    use_llm(FakeLLM([SIMPLE] * 2))
    assert client.post("/api/ask/stream", json=Q).status_code == 200
    r = client.post("/api/ask/stream", json=Q)
    assert r.status_code == 429 and r.json()["detail"]["stage"] == "limits"


def test_clients_have_separate_buckets_behind_a_trusted_proxy(use_llm, setting):
    setting(rate_limit_per_minute=1, trust_proxy=True)
    use_llm(FakeLLM([SIMPLE] * 3))
    ask = lambda ip: client.post("/api/ask", json={"question": "orders per status"}, headers={"x-forwarded-for": ip}).status_code
    assert (ask("1.1.1.1"), ask("2.2.2.2"), ask("1.1.1.1")) == (200, 200, 429)


def test_forwarded_header_is_ignored_unless_the_proxy_is_trusted(use_llm, setting):
    setting(rate_limit_per_minute=1, trust_proxy=False)
    use_llm(FakeLLM([SIMPLE] * 3))
    ask = lambda ip: client.post("/api/ask", json={"question": "orders per status"}, headers={"x-forwarded-for": ip}).status_code
    assert (ask("1.1.1.1"), ask("2.2.2.2")) == (200, 429)           # spoofing a new address does not help


def test_daily_budget_protects_paid_providers(use_llm, setting):
    setting(daily_llm_budget=2, llm_provider="anthropic")
    use_llm(FakeLLM([SIMPLE] * 3))
    codes = [client.post("/api/ask", json={"question": f"orders per status {i}"}) for i in range(3)]
    assert [c.status_code for c in codes] == [200, 200, 429]
    assert codes[2].json()["detail"]["code"] == "budget_exhausted"


def test_daily_budget_does_not_apply_to_the_free_replay_provider(use_llm, setting):
    setting(daily_llm_budget=1, llm_provider="replay")
    use_llm(FakeLLM([SIMPLE] * 3))
    assert [client.post("/api/ask", json={"question": f"orders per status {i}"}).status_code for i in range(3)] == [200] * 3


def test_database_only_endpoints_are_throttled_too():
    codes = [client.post("/api/security/probe", json={"layer": "guard"}).status_code for _ in range(31)]
    assert codes[:30] == [200] * 30 and codes[30] == 429


def test_meta_reports_the_protections(setting):
    setting(rate_limit_per_minute=12, cache_ttl_s=99)
    body = client.get("/api/meta").json()
    assert body["rate_limit_per_minute"] == 12 and body["cache_ttl_s"] == 99 and "explanations_enabled" in body
