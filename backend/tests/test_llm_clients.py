import json

import httpx
import pytest

from app.config import get_settings
from app.llm import LLMError, LLMNotConfigured, get_llm
from app.llm import http_clients
from app.llm.http_clients import AnthropicClient, OpenAIClient

MSGS = [{"role": "user", "content": "hi"}]


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    monkeypatch.setattr(http_clients.time, "sleep", lambda s: None)


def transport(handler):
    return httpx.MockTransport(handler)


def test_anthropic_request_shape_and_parsing():
    seen = {}

    def handler(req: httpx.Request):
        seen["url"], seen["headers"], seen["body"] = str(req.url), req.headers, json.loads(req.content)
        return httpx.Response(200, json={"content": [{"type": "text", "text": "SELECT 1"}]})

    c = AnthropicClient("k", transport=transport(handler), temperature=0.0, max_tokens=99)
    assert c.complete("SYS", MSGS) == "SELECT 1"
    assert seen["url"] == "https://api.anthropic.com/v1/messages"
    assert seen["headers"]["x-api-key"] == "k" and "anthropic-version" in seen["headers"]
    assert seen["body"]["system"] == "SYS" and seen["body"]["messages"] == MSGS
    assert seen["body"]["max_tokens"] == 99 and seen["body"]["temperature"] == 0.0


def test_openai_request_shape_and_parsing():
    seen = {}

    def handler(req: httpx.Request):
        seen["url"], seen["headers"], seen["body"] = str(req.url), req.headers, json.loads(req.content)
        return httpx.Response(200, json={"choices": [{"message": {"content": "SELECT 2"}}]})

    c = OpenAIClient("sk", transport=transport(handler))
    assert c.complete("SYS", MSGS) == "SELECT 2"
    assert seen["url"] == "https://api.openai.com/v1/chat/completions"
    assert seen["headers"]["authorization"] == "Bearer sk"
    assert seen["body"]["messages"][0] == {"role": "system", "content": "SYS"}


def test_openai_compatible_base_url():
    seen = {}

    def handler(req):
        seen["url"] = str(req.url)
        return httpx.Response(200, json={"choices": [{"message": {"content": "x"}}]})

    OpenAIClient("", base_url="http://localhost:11434/v1/", transport=transport(handler)).complete("s", MSGS)
    assert seen["url"] == "http://localhost:11434/v1/chat/completions"


def test_retries_on_rate_limit_then_succeeds():
    calls = {"n": 0}

    def handler(req):
        calls["n"] += 1
        if calls["n"] < 3:
            return httpx.Response(429, text="slow down")
        return httpx.Response(200, json={"content": [{"type": "text", "text": "ok"}]})

    assert AnthropicClient("k", transport=transport(handler)).complete("s", MSGS) == "ok"
    assert calls["n"] == 3


def test_gives_up_after_retries():
    c = AnthropicClient("k", transport=transport(lambda r: httpx.Response(503, text="down")), max_retries=1)
    with pytest.raises(LLMError, match="after 2 attempts"):
        c.complete("s", MSGS)


def test_auth_error_is_not_retried():
    calls = {"n": 0}

    def handler(req):
        calls["n"] += 1
        return httpx.Response(401, text="bad key")

    with pytest.raises(LLMError, match="401"):
        AnthropicClient("k", transport=transport(handler)).complete("s", MSGS)
    assert calls["n"] == 1


def test_network_error_is_wrapped():
    def handler(req):
        raise httpx.ConnectError("boom")

    with pytest.raises(LLMError, match="network error"):
        AnthropicClient("k", transport=transport(handler), max_retries=0).complete("s", MSGS)


@pytest.mark.parametrize("payload", [{"content": []}, {"weird": 1}])
def test_empty_or_malformed_response(payload):
    c = AnthropicClient("k", transport=transport(lambda r: httpx.Response(200, json=payload)))
    with pytest.raises(LLMError):
        c.complete("s", MSGS)


# ---- factory ----

def _configure(monkeypatch, **kw):
    s = get_settings()
    for k, v in kw.items():
        monkeypatch.setattr(s, k, v)
    get_llm.cache_clear()


def test_factory_requires_key(monkeypatch):
    _configure(monkeypatch, llm_provider="anthropic", llm_api_key="", llm_base_url="")
    with pytest.raises(LLMNotConfigured, match="LLM_API_KEY"):
        get_llm()


def test_factory_unknown_provider(monkeypatch):
    _configure(monkeypatch, llm_provider="skynet", llm_api_key="x")
    with pytest.raises(LLMNotConfigured, match="Unknown"):
        get_llm()


def test_factory_builds_each_provider(monkeypatch):
    _configure(monkeypatch, llm_provider="anthropic", llm_api_key="x", llm_model="")
    assert isinstance(get_llm(), AnthropicClient)
    _configure(monkeypatch, llm_provider="openai", llm_api_key="x", llm_model="gpt-test")
    c = get_llm()
    assert isinstance(c, OpenAIClient) and c.model == "gpt-test"
    get_llm.cache_clear()


def test_local_openai_compatible_needs_no_key(monkeypatch):
    _configure(monkeypatch, llm_provider="openai", llm_api_key="", llm_base_url="http://localhost:11434/v1")
    assert isinstance(get_llm(), OpenAIClient)
    get_llm.cache_clear()
