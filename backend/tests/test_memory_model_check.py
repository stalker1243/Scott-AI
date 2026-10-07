"""Safety and scoring of the optional live check; no actual API requests."""
import json
from types import SimpleNamespace

import pytest

import check_memory
import intelligent_answerer as ia
import memories
import personality
import projects

pytestmark = pytest.mark.unit


@pytest.mark.parametrize('probe,answer,expected', [
    ('corrected', 'Тебя зовут Михаил.', True),
    ('corrected', 'Вы Mikhail.', True),
    ('corrected', 'Тебя зовут Алексей.', False),
    ('corrected', 'Михаил, или, возможно, Алексей.', False),
    ('forgotten', 'Я не знаю вашего имени.', True),
    ('forgotten', 'Ваше имя не сохранено.', True),
    ('forgotten', 'Я не знаю. Может быть, Алексей?', False),
])
def test_identity_checks_accept_transliteration_and_reject_old_fact(probe, answer, expected):
    assert check_memory.evaluate_response(probe, answer)[0] is expected


def test_live_check_requires_explicit_network_flag(monkeypatch, capsys):
    monkeypatch.setattr(check_memory.sys, 'argv', ['check_memory.py'])
    def unexpected(*args, **kwargs):
        pytest.fail('Live check must not run without --live')
    monkeypatch.setattr(check_memory, 'worker', unexpected)
    monkeypatch.setattr(check_memory.subprocess, 'run', unexpected)
    assert check_memory.main() == 0
    assert '--live' in capsys.readouterr().out


def test_probe_isolates_history_facts_projects_and_personality(tmp_path, monkeypatch):
    personal = tmp_path / 'existing'
    personal.mkdir()
    paths = {
        (ia, 'CONVERSATION_PATH'): personal / 'conversations.jsonl',
        (ia, 'LEGACY_CHAT_PATH'): personal / 'legacy.jsonl',
        (ia, 'AI_CONFIG_PATH'): personal / 'ai_config.json',
        (memories, 'STORE_PATH'): personal / 'memories.json',
        (personality, 'CONFIG_PATH'): personal / 'personality.json',
        (projects, 'STORE_PATH'): personal / 'projects.json',
    }
    before = {}
    for (module, name), path in paths.items():
        monkeypatch.setattr(module, name, path)
        path.write_text('synthetic private sentinel', encoding='utf-8')
        before[path] = path.read_bytes()
    import dotenv
    monkeypatch.setattr(dotenv, 'load_dotenv', lambda *args, **kwargs: None)
    state = tmp_path / 'probe'

    def initialize():
        for module, name in paths:
            if name != 'AI_CONFIG_PATH':
                assert getattr(module, name).parent == state
        memory = ia.ConversationMemory()
        assert memory.stats()['archived_turns'] == 0
        assert not memories.all_memories()
        assert not projects.prompt_addition()
        assert not personality.prompt_addition()
        return SimpleNamespace(custom_keys={}, env_keys={}, memory=memory,
                               enabled=True, api_provider='Fake', model='fake',
                               answer=lambda text: ('Алексей, Казань, короткие ответы, C++ и Qt.', True))
    monkeypatch.setattr(ia, 'IntelligentAnswerer', initialize)
    result = tmp_path / 'result.json'
    args = SimpleNamespace(state=state, worker='profile', result=result,
                           model=None, seed_report=None)
    assert check_memory.worker(args) == 0
    report = json.loads(result.read_text(encoding='utf-8'))
    assert report['rows'][0]['passed']
    assert report['rows'][0]['facts'] == ''
    assert report['rows'][0]['recalled'] == []
    assert all(path.read_bytes() == content for path, content in before.items())
