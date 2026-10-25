import json

import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.llm import LLMError, RecordingLLM, ReplayLLM, get_llm
from app.llm.replay import normalize_question
from app.main import app

from .fakes import FakeLLM, sql_block

MSG = lambda q, *replies: [{"role": "user", "content": q}] + [
    m for r in replies for m in ({"role": "assistant", "content": r}, {"role": "user", "content": "fix it"})]


def test_normalization_ignores_case_spacing_and_punctuation():
    assert normalize_question("  What IS   revenue? ") == normalize_question("what is revenue")


def test_replay_serves_replies_by_conversation_turn():
    llm = ReplayLLM({"Q one?": ["first", "second"]})
    assert llm.complete("s", MSG("q one")) == "first"
    assert llm.complete("s", MSG("Q ONE?", "first")) == "second"          # stateless: depends on history


def test_replay_exhaustion_is_an_error():
    llm = ReplayLLM({"q": ["only"]})
    with pytest.raises(LLMError, match="exhausted"):
        llm.complete("s", MSG("q", "only"))


def test_unknown_question_gets_a_friendly_refusal_with_examples():
    llm = ReplayLLM({"What is revenue?": ["x"]})
    reply = llm.complete("s", MSG("something else entirely"))
    assert reply.startswith("CANNOT_ANSWER") and "What is revenue?" in reply


def test_missing_file():
    with pytest.raises(LLMError, match="not found"):
        ReplayLLM.from_file("/nope.json")


def test_recording_roundtrip(tmp_path):
    fake = FakeLLM([sql_block("SELECT bad"), sql_block("SELECT 1")])
    rec = RecordingLLM(fake)
    rec.complete("s", MSG("How many?"))
    rec.complete("s", MSG("How many?", "x"))
    path = tmp_path / "rec.json"
    rec.save(path, name="mine")
    assert json.loads(path.read_text())["meta"]["name"] == "mine"

    replay = ReplayLLM.from_file(path)
    assert replay.model == "replay:mine"
    assert replay.complete("s", MSG("how many")) == sql_block("SELECT bad")
    assert replay.complete("s", MSG("how many", "x")) == sql_block("SELECT 1")


def test_rerecording_overwrites_instead_of_appending(tmp_path):
    rec = RecordingLLM(FakeLLM(["a", "b"]))
    rec.complete("s", MSG("q"))
    rec.complete("s", MSG("q"))                 # same question again, turn 0
    assert rec.answers == {"q": ["b"]}


# ---------------------------------------------------------------- keyless demo mode via the API

@pytest.fixture
def demo_mode(monkeypatch):
    monkeypatch.setattr(get_settings(), "llm_provider", "replay")
    get_llm.cache_clear()
    yield
    get_llm.cache_clear()


@pytest.mark.usefixtures("require_db", "demo_mode")
def test_api_works_without_an_api_key_in_replay_mode():
    client = TestClient(app)
    body = client.post("/api/ask", json={"question": "Which products had the biggest revenue decline last quarter?"}).json()
    assert body["status"] == "ok" and body["model"] == "replay:reference"
    assert [r[0] for r in body["rows"]][:2] == ["Wireless Earbuds", "Smart Watch"]

    other = client.post("/api/ask", json={"question": "Tell me a joke about databases"}).json()
    assert other["status"] == "cannot_answer" and "recorded questions" in other["message"]
