"""Regressions found by the backend audit; no external actions or models."""
import asyncio
import json
import threading
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import httpx
import pytest

import accuracy_voice
import understanding
from command_parser import CommandParser, ParsedCommand
from fast_intent import get_fast_intent_engine
from knowledge_base import KnowledgeBase
from question_answerer import get_question_answerer

pytestmark = pytest.mark.unit


def decision(text):
    return understanding.understand(text, intent_engine=get_fast_intent_engine(),
        parser=CommandParser(), answerer=get_question_answerer())


@pytest.mark.parametrize('text,kind,action,param', [
    ('Скот, создай папку отчеты.', 'action', 'create_folder', 'отчеты.'),
    ('Скотт, найди в интернете рецепт борща.', 'action', 'search', 'рецепт борща'),
    ('Выключим музыку.', 'action', 'close_app', 'музыку'),
    ('открой телеграм.', 'action', 'open_app', 'телеграм'),
    ('Прибав яркость.', 'action', 'system_command', 'brightness_up'),
])
def test_parameter_routing_after_transcription(text, kind, action, param):
    result = decision(text)
    assert (result.kind, result.action, result.parsed.main_param) == (kind, action, param)


def test_voice_accuracy_checks_actual_target_and_settings():
    assert not accuracy_voice._same_decision(decision('открой блокнот'), decision('открой браузер'))
    assert not accuracy_voice._same_decision(decision('громкость голоса 50 процентов'), decision('громкость голоса 15 процентов'))
    assert accuracy_voice._same_decision(decision('открой гугл хром'), decision('Открой Google Chrome.'))
    assert accuracy_voice._same_decision(decision('напомни через двадцать минут проверить почту'),
                                        decision('Напомни через 20 минут проверить почту.'))
    assert accuracy_voice._same_decision(decision('очисти всю папку загрузок'), decision('Очистить всю папку загрузок.'))
    assert accuracy_voice._same_decision(decision('открой браузер'), decision('Открой браузера.'))
    assert accuracy_voice._same_decision(decision('зайди на гитхаб'), decision('Заеди на GitHub.'))


@pytest.mark.parametrize('text,action,value', [
    ('Выбери голос у Ильяма.', 'select', 'en-AU-WilliamMultilingualNeural'),
    ('Выбери голос у Илима.', 'select', 'en-AU-WilliamMultilingualNeural'),
    ('Выпери голос Флориана.', 'select', 'de-DE-FlorianMultilingualNeural'),
    ('Выбери голос Флорианы.', 'select', 'de-DE-FlorianMultilingualNeural'),
    ('Выключаю озвучку.', 'quiet', True),
])
def test_voice_controls_handle_observed_name_and_verb_errors(text, action, value):
    result = decision(text)
    assert (result.kind, result.action, result.parsed.main_param) == ('action', 'voice_settings', action)
    assert result.parsed.context['voice_value'] == value


@pytest.mark.parametrize('text', ['что такое GitHub', 'как пользоваться YouTube', 'объясни, что такое ютуб',
    'чем отличается http от https', 'Скотт, чем отличается HTTP от HTTPS',
    'чем отличается http:// от https://'])
def test_question_about_website_does_not_open_browser(text):
    assert decision(text).kind == 'question'


@pytest.mark.parametrize('text', ['заверши процесс chrome', 'закрой программу chrome',
    'закрой приложение chrome', 'Скотт, заверши процесс chrome.'])
def test_close_command_targets_process_name(text):
    result = decision(text)
    assert (result.kind, result.action, result.parsed.main_param) == ('action', 'close_app', 'chrome')


@pytest.mark.parametrize('text,number', [('Громкость, голоса 50%.', 50),
    ('Громкость, голоса, 55%.', 55), ('Громкость голоса пятьдесят, пять процентов.', 55)])
def test_transcribed_commas_do_not_route_voice_volume_to_system(text, number):
    result = decision(text)
    assert (result.kind, result.action, result.parsed.main_param) == ('action', 'voice_settings', 'volume')
    assert result.parsed.context['voice_value'] == number


def test_split_search_verb_keeps_query():
    assert decision('за гугли погоду в Питере.').parsed.main_param == 'погоду питере'


@pytest.mark.parametrize('name,expected', [('гугл', 'https://www.google.com'),
    ('Google.', 'https://www.google.com'), ('яндекс', 'https://ya.ru'),
    ('example.org/test?x=1', 'https://example.org/test?x=1')])
def test_site_names_reach_real_addresses(monkeypatch, name, expected):
    import command_executor
    opened = []
    monkeypatch.setattr(command_executor.webbrowser, 'open', lambda url: opened.append(url) or True)
    executor = command_executor.CommandExecutor.__new__(command_executor.CommandExecutor)
    assert executor.open_website(name).startswith('✅')
    assert opened == [expected]


def test_website_failure_is_reported(monkeypatch):
    import command_executor
    monkeypatch.setattr(command_executor.webbrowser, 'open', lambda _: False)
    executor = command_executor.CommandExecutor.__new__(command_executor.CommandExecutor)
    assert executor.open_website('example.org').startswith('❌')


def test_atomic_knowledge_save_preserves_existing_file(tmp_path, monkeypatch):
    import knowledge_base
    path = tmp_path / 'memory.json'
    kb = KnowledgeBase(str(path))
    kb.add_memory('old', 'original')
    monkeypatch.setattr(knowledge_base, 'atomic_write_text', lambda *args: (_ for _ in ()).throw(OSError('disk')))
    kb.add_memory('new', 'value')
    assert json.loads(path.read_text(encoding='utf-8'))['old']['value'] == 'original'
    assert 'new' not in json.loads(path.read_text(encoding='utf-8'))


def test_concurrent_knowledge_updates_and_search(tmp_path):
    kb = KnowledgeBase(str(tmp_path / 'memory.json'))
    def update(i):
        kb.add_memory(f'key{i}', str(i))
        kb.search_memory('key')
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(update, range(25)))
    assert len(json.loads(kb.db_file.read_text(encoding='utf-8'))) == 25


@pytest.mark.parametrize('text', ['удали все файлы с рабочего стола', 'выполни команду powershell get-process'])
def test_cache_cannot_override_refusal(main_module, monkeypatch, text):
    main = main_module
    monkeypatch.setattr(main, 'HAS_V32_FEATURES', False)
    monkeypatch.setattr(main, 'knowledge_base', SimpleNamespace(
        search_memory=lambda _: {text: {'value': 'Выполнено', 'category': 'general'}}, add_conversation=lambda *a: None))
    monkeypatch.setattr(main.executor, 'execute', lambda *a, **k: pytest.fail('Real action must not execute'))
    assert asyncio.run(main.scott_ai.process_command(text))['type'] == 'refused'


def test_learned_answer_does_not_override_current_question(main_module, monkeypatch):
    main = main_module
    monkeypatch.setattr(main, 'HAS_V32_FEATURES', False)
    monkeypatch.setattr(main, 'knowledge_base', SimpleNamespace(
        search_memory=lambda _: {'сколько времени': {'value': '09:00', 'category': 'learned'}},
        add_conversation=lambda *a: None))
    monkeypatch.setattr(main.question_answerer, 'answer', lambda *a, **k: '12:00')
    assert asyncio.run(main.scott_ai.process_command('сколько времени'))['response'] == '12:00'


@pytest.mark.parametrize('path', ['/diagnostics/checks', '/diagnostics/system', '/audio/settings'])
def test_device_checks_do_not_block_health(main_module, monkeypatch, path):
    import audio_settings
    import diagnostics
    import health_checks
    started, release = threading.Event(), threading.Event()
    def slow_result(*a, **k):
        started.set()
        release.wait(0.8)
        return {'success': True}
    module, attribute = {'/diagnostics/checks': (health_checks, 'run_all'),
        '/diagnostics/system': (diagnostics, 'collect_system_info'),
        '/audio/settings': (audio_settings, 'describe')}[path]
    monkeypatch.setattr(module, attribute, slow_result)
    async def check():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main_module.app), base_url='http://test') as client:
            task = asyncio.create_task(client.get(path))
            try:
                while not started.is_set():
                    await asyncio.sleep(0.005)
                response = await asyncio.wait_for(client.get('/health'), 0.3)
                assert response.status_code == 200 and not task.done()
            finally:
                release.set()
                await task
    asyncio.run(check())
