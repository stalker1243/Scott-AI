"""Model settings: persistence, rollback and responsive API. No provider network."""
import asyncio
import json
import threading
from types import SimpleNamespace

import pytest
import ai_endpoints as routes
import intelligent_answerer as ia

pytestmark = pytest.mark.unit


@pytest.fixture
def answerer(tmp_path, monkeypatch):
    monkeypatch.setattr(ia, "AI_CONFIG_PATH", tmp_path / "ai_config.json")
    obj = ia.IntelligentAnswerer.__new__(ia.IntelligentAnswerer)
    obj.custom_keys = {}
    obj.env_keys = {}
    obj.api_provider = "Groq"
    obj.model = "previous"
    obj.client = object()
    obj.enabled = True
    obj.last_connect_error = ""

    def connect(obj, provider, model, key):
        obj.api_provider, obj.model, obj.client, obj.enabled = provider, model, {"api_key": key}, True
        return True
    monkeypatch.setattr(ia.IntelligentAnswerer, "_connect_provider", connect)
    return obj


def test_tokens_for_each_provider_survive_switches(answerer):
    assert answerer.configure("OpenAI", "custom-gpt", "test-openai")["success"]
    assert answerer.configure("DeepSeek", "deepseek-chat", "test-deepseek")["success"]
    assert answerer.configure("OpenAI", "custom-gpt-next")["success"]
    saved = json.loads(ia.AI_CONFIG_PATH.read_text(encoding="utf-8"))
    assert saved["keys"] == {"OpenAI": "test-openai", "DeepSeek": "test-deepseek"}
    assert saved["api_key"] == "test-openai"
    assert saved["model"] == "custom-gpt-next"
    assert not list(ia.AI_CONFIG_PATH.parent.glob(".ai-config-*.tmp"))


def test_saved_keys_loaded_on_restart(answerer, monkeypatch):
    answerer.configure("OpenAI", "custom-gpt", "test-openai")
    answerer.configure("DeepSeek", "deepseek-chat", "test-deepseek")
    seen = []
    def connect(obj, provider, model, key):
        seen.append((provider, model, key))
        obj.api_provider, obj.model, obj.enabled = provider, model, True
        return True
    monkeypatch.setattr(ia.IntelligentAnswerer, "_connect_provider", connect)
    monkeypatch.setattr(ia, "ConversationMemory", lambda **kwargs: SimpleNamespace(conversations=[], max_history=6))
    restarted = ia.IntelligentAnswerer()
    assert restarted.custom_keys == {"OpenAI": "test-openai", "DeepSeek": "test-deepseek"}
    assert seen[0] == ("DeepSeek", "deepseek-chat", "test-deepseek")


def test_disk_failure_retains_previous_file_and_connection(answerer, monkeypatch):
    answerer.configure("OpenAI", "before", "test-original")
    previous = (answerer.api_provider, answerer.model, answerer.client, answerer.enabled)
    contents = ia.AI_CONFIG_PATH.read_bytes()
    def fail(*args):
        raise PermissionError("fixture disk failure")
    monkeypatch.setattr(ia.os, "replace", fail)
    result = answerer.configure("DeepSeek", "after", "test-new")
    assert not result["success"]
    assert (answerer.api_provider, answerer.model, answerer.client, answerer.enabled) == previous
    assert answerer.custom_keys == {"OpenAI": "test-original"}
    assert ia.AI_CONFIG_PATH.read_bytes() == contents
    assert not list(ia.AI_CONFIG_PATH.parent.glob(".ai-config-*.tmp"))
    assert "test-new" not in str(result)


def test_failed_probe_does_not_save_or_echo_token(answerer, monkeypatch):
    previous = (answerer.api_provider, answerer.model, answerer.client, answerer.enabled)
    def fail(candidate, *args):
        candidate.last_connect_error = "provider echoed test-secret"
        candidate.enabled = False
        return False
    monkeypatch.setattr(ia.IntelligentAnswerer, "_connect_provider", fail)
    result = answerer.configure("DeepSeek", "test-model", "test-secret")
    assert not result["success"] and "test-secret" not in str(result)
    assert (answerer.api_provider, answerer.model, answerer.client, answerer.enabled) == previous
    assert not ia.AI_CONFIG_PATH.exists()


def test_probe_keeps_current_connection_and_fallback_commits_actual_model(answerer, monkeypatch):
    previous = (answerer.api_provider, answerer.model, answerer.client, answerer.enabled)
    def probe(candidate, provider, model, key):
        assert candidate is not answerer
        assert (answerer.api_provider, answerer.model, answerer.client, answerer.enabled) == previous
        candidate.api_provider, candidate.model, candidate.client = provider, model, {"api_key": key}
        candidate.enabled = model == "available"
        candidate.last_connect_error = "model not found"
        return candidate.enabled
    monkeypatch.setattr(ia.IntelligentAnswerer, "_connect_provider", probe)
    monkeypatch.setattr(ia, "list_groq_models", lambda key: [{"id": "available"}])
    result = answerer.configure("Groq", "missing", "test-key")
    assert result["success"] and result["model"] == "available" and result["note"]
    assert answerer.model == "available"
    assert json.loads(ia.AI_CONFIG_PATH.read_text())["model"] == "available"


def test_probe_does_not_log_token(answerer, capsys):
    def fail():
        raise RuntimeError("fixture-secret was rejected")
    answerer.client = SimpleNamespace(api_key="fixture-secret", models=SimpleNamespace(list=fail))
    answerer._test_connection_openai()
    assert "fixture-secret" not in capsys.readouterr().out
    assert "fixture-secret" not in answerer.last_connect_error
    assert not answerer.enabled


@pytest.mark.asyncio
@pytest.mark.parametrize("body", [
    {"provider": ["Groq"], "model": "m"},
    {"provider": "Groq", "model": "m", "api_key": ["key"]},
    {"provider": "Groq", "model": "m", "api_key": []},
    {"provider": "Unknown", "model": "m"},
    {"provider": "Groq", "model": "bad model"},
    {"provider": "Groq", "model": "x" * 201},
    {"provider": "Groq", "model": "m", "api_key": "key\nsecond"},
])
async def test_invalid_configuration_never_contacts_provider(body, monkeypatch):
    def unexpected(*args):
        pytest.fail("invalid settings reached provider")
    monkeypatch.setattr(routes, "get_intelligent_answerer", lambda: SimpleNamespace(configure=unexpected))
    result = await routes.configure_ai(body)
    assert not result["success"] and result["error"]


@pytest.mark.asyncio
async def test_catalog_is_responsive_and_returns_only_metadata(monkeypatch):
    entered, finish = threading.Event(), threading.Event()
    def catalog():
        entered.set()
        assert finish.wait(2)
        return [{"id": "Groq", "configured": True, "models": [{"id": "demo"}]}]
    obj = SimpleNamespace(get_available_providers=catalog, api_provider="Groq", model="demo", enabled=True)
    monkeypatch.setattr(routes, "get_intelligent_answerer", lambda: obj)
    task = asyncio.create_task(routes.list_ai_providers())
    try:
        assert await asyncio.to_thread(entered.wait, 1)
        assert not task.done()
    finally:
        finish.set()
    result = await task
    assert result["enabled"] and result["active_model"] == "demo"
    assert "api_key" not in json.dumps(result)


@pytest.mark.asyncio
async def test_configuration_does_not_block_event_loop(monkeypatch):
    entered, finish = threading.Event(), threading.Event()
    def configure(provider, model, key):
        entered.set()
        assert finish.wait(2)
        return {"success": True, "provider": provider, "model": model}
    monkeypatch.setattr(routes, "get_intelligent_answerer", lambda: SimpleNamespace(configure=configure))
    task = asyncio.create_task(routes.configure_ai({"provider": "OpenAI", "model": "demo", "api_key": "test-key"}))
    try:
        assert await asyncio.to_thread(entered.wait, 1)
        assert not task.done()
    finally:
        finish.set()
    assert (await task)["success"]
