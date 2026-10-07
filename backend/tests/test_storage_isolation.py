"""Clear APIs must only reach the temporary test stores, under either import."""
import asyncio
import importlib
from pathlib import Path
from types import SimpleNamespace
import pytest

pytestmark = pytest.mark.unit


@pytest.mark.parametrize('prefix', ['', 'backend.'])
def test_chat_clear_endpoint_cannot_use_personal_database(prefix, monkeypatch):
    endpoints = importlib.import_module(prefix+'ai_endpoints')
    chats = importlib.import_module(prefix+'chat_endpoints')
    store = chats.store()
    assert not store.path.resolve().is_relative_to(Path(__file__).resolve().parents[1]/'data')
    store.create()
    cleared = []
    fake = SimpleNamespace(clear_memory=lambda: cleared.append(True))
    monkeypatch.setattr(endpoints, 'get_intelligent_answerer', lambda: fake)
    result = asyncio.run(endpoints.clear_ai_memory())
    assert result['status'] == 'success' and cleared == [True]
    assert store.list() == []


@pytest.mark.parametrize('name', ['intelligent_answerer', 'backend.intelligent_answerer'])
def test_conversation_singleton_uses_temporary_history(name):
    module = importlib.import_module(name)
    real_data = Path(__file__).resolve().parents[1]/'data'
    assert not module.CONVERSATION_PATH.resolve().is_relative_to(real_data)
    # Without a configured API provider the singleton is intentionally absent.
    # A later initialization must still inherit the patched default path.
    memory = (module.intelligent_answerer.memory if module.intelligent_answerer is not None
              else module.ConversationMemory())
    assert not memory.context_file.resolve().is_relative_to(real_data)
    assert not memory.archive.path.resolve().is_relative_to(real_data)
