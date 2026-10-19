import asyncio
import base64
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import threading
import wave

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import browser_commands
import browser_control_config as config
import browser_control_endpoints as endpoints
from browser_control_jobs import BrowserJobs, JobConflict
from browser_control_worker import YouTubeDriver, video_id


@pytest.mark.parametrize('text,expected', [
    ('Скотт, можешь открыть YouTube?', {'action': 'home'}),
    ('найди на YouTube уроки Python', {'action': 'search', 'query': 'уроки Python'}),
    ('включи музыку на ютубе спокойный джаз', {'action': 'play', 'query': 'спокойный джаз'}),
    ('открой YouTube и найди уроки Qt', {'action': 'search', 'query': 'уроки Qt'}),
    ('открой YouTube и найди джаз и включи первое', {'action': 'play', 'query': 'джаз'}),
    ('включи второе', {'action': 'select', 'index': 1}),
    ('покажи пятое видео', {'action': 'select', 'index': 4}),
    ('поставь видео на паузу', None),
    ('поставь на паузу видео на YouTube', {'action': 'pause'}),
    ('продолжи воспроизведение на ютубе', {'action': 'resume'}),
    ('закрой YouTube', {'action': 'close'}),
    ('Скотт, подготовь браузер', {'action': 'install'}),
    ('включи управление браузером', {'action': 'enable'}),
    ('отключи управление браузером', {'action': 'disable'}),
    ('отмени действие в браузере', {'action': 'cancel'}),
    ('покажи статус браузера', {'action': 'status'}),
])
def test_natural_browser_requests(text, expected):
    assert browser_commands.parse(text) == expected


@pytest.mark.parametrize('text', ['Что такое YouTube?', 'Напиши код открытия YouTube',
    'Не открывай YouTube', 'Я сказал включи второе', 'Пример: открой YouTube',
    '```\nоткрой YouTube\n```', 'Открой YouTube\nи выключи компьютер', 'включи шестое'])
def test_discussion_does_not_control_browser(text):
    assert browser_commands.parse(text) is None


def test_browser_setup_and_cancel_are_available_without_launcher_switch(main_module, monkeypatch):
    import browser_control_jobs
    from types import SimpleNamespace
    calls = []
    jobs = SimpleNamespace(enabled=False, snapshot=lambda: dict(id='fixture', message='Готово', candidates=[]),
                           set_enabled=lambda value: calls.append(('enabled', value)),
                           cancel=lambda ident: calls.append(('cancel', ident)),
                           start=lambda **kw: calls.append(('start', kw)) or dict(id='fixture'))
    monkeypatch.setattr(browser_control_jobs, 'jobs', jobs)
    async def check():
        for text in ('Подготовь браузер', 'Включи управление браузером', 'Отмени действие в браузере'):
            decision = main_module.scott_ai._browser_decision(text)
            assert decision and decision.kind == 'browser'
            result = await main_module.scott_ai._process_command_impl(text, decision=decision)
            assert result['type'] == 'browser'
        assert calls == [('start', {'action': 'install'}), ('enabled', True), ('cancel', 'fixture')]
    asyncio.run(check())


@pytest.mark.parametrize('url', ['file:///secret', 'https://youtube.com.evil.test/watch?v=abcdefghijk',
    'http://www.youtube.com/watch?v=abcdefghijk', 'https://user@www.youtube.com/watch?v=abcdefghijk',
    'https://127.0.0.1/watch?v=abcdefghijk', 'https://www.youtube.com/watch?v=bad'])
def test_results_only_contain_youtube_video_ids(url):
    assert video_id(url) is None


def ready(home):
    (home / 'libraries/playwright').mkdir(parents=True)
    (home / 'libraries/playwright/__init__.py').write_text('', encoding='utf-8')
    (home / 'ready.json').write_text(json.dumps({'version': config.VERSION}), encoding='utf-8')
    (home / 'settings.json').write_text('{"enabled":true}', encoding='utf-8')


def eventually(check, timeout=4):
    until = time.monotonic() + timeout
    while time.monotonic() < until:
        if check():
            return
        time.sleep(.02)
    assert check()


@pytest.fixture
def service(tmp_path):
    ready(tmp_path)
    probe = tmp_path / 'probe.py'
    probe.write_text('''import sys,json,time
for line in sys.stdin:
 job=json.loads(line)
 if job['query']=='hang': time.sleep(30)
 event=dict(type='result',id=job['id'],state='complete',message='done',candidates=[dict(video_id='abcdefghijk',title='<b>Example</b>')])
 print(json.dumps(event),flush=True)
''', encoding='utf-8')
    def popen(command, **kwargs):
        return subprocess.Popen([sys.executable, '-u', str(probe)], **kwargs)
    manager = BrowserJobs(tmp_path, popen=popen, timeout=1.)
    yield manager
    manager.close()


def test_worker_reused_and_selection_checks_results_identity(service):
    first = service.start('search', 'example')
    eventually(lambda: service.snapshot()['state'] == 'complete')
    process = service._process
    state = service.snapshot()
    assert state['results_id'] == first['id']
    with pytest.raises(JobConflict):
        service.start('select', index=0, results_id='0' * 32)
    service.start('select', index=0, results_id=first['id'])
    eventually(lambda: service.snapshot()['state'] == 'complete')
    assert service._process is process and process.poll() is None
    service.start('close')
    assert process.poll() is not None and not service.snapshot()['browser_open']


def test_cancellation_stale_id_and_watchdog(service):
    state = service.start('search', 'hang')
    with pytest.raises(JobConflict):
        service.start('search', 'another')
    with pytest.raises(JobConflict):
        service.cancel('0' * 32)
    process = service._process
    assert service.cancel(state['id'])['state'] == 'cancelled'
    assert process.poll() is not None
    service.start('search', 'hang')
    process = service._process
    eventually(lambda: service.snapshot()['state'] == 'failed', timeout=5)
    assert process.poll() is not None


def test_cancel_cannot_overwrite_a_new_request(service, monkeypatch):
    import browser_control_jobs
    entered, release = threading.Event(), threading.Event()
    original = browser_control_jobs.stop_process_tree
    def slow_stop(process, owner):
        entered.set()
        assert release.wait(3)
        original(process, owner)
    monkeypatch.setattr(browser_control_jobs, 'stop_process_tree', slow_stop)
    state = service.start('search', 'hang')
    stopped, started = [], []
    cancel = threading.Thread(target=lambda: stopped.append(service.cancel(state['id'])))
    cancel.start()
    assert entered.wait(2)
    next_request = threading.Thread(target=lambda: started.append(service.start('search', 'example')))
    next_request.start()
    assert service.snapshot()['state'] == 'cancelling'
    release.set()
    cancel.join(3); next_request.join(3)
    assert stopped[0]['state'] == 'cancelled'
    eventually(lambda: service.snapshot()['state'] == 'complete')
    assert service.snapshot()['id'] == started[0]['id'] != state['id']


def test_closed_window_invalidates_verified_playback(service):
    service._state['playback'] = {'verified': True}
    service._state['browser_open'] = True
    service._event({'type': 'window_closed'}, False)
    assert not service.snapshot()['playback'] and not service.snapshot()['browser_open']


def test_api_does_not_accept_scripts_urls_or_stale_selection(service, monkeypatch):
    monkeypatch.setattr(endpoints, 'jobs', service)
    app = FastAPI()
    app.include_router(endpoints.router)
    with TestClient(app) as client:
        for payload in [{'action': 'eval', 'query': 'code'}, {'action': 'search', 'url': 'file:///secret'},
                        {'action': 'select', 'index': 99}]:
            assert client.post('/browser', json=payload).status_code == 422
        assert client.post('/browser', json={'action': 'select', 'index': 0, 'results_id': '0'*32}).status_code == 409
        state = client.post('/browser', json={'action': 'search', 'query': 'hang'}).json()
        assert client.get('/browser').json()['state'] == 'running'
        assert client.post('/browser/cancel', json={'id': state['id']}).json()['state'] == 'cancelled'
        assert client.post('/browser/settings', json={'enabled': False}).json()['enabled'] is False
        assert client.post('/browser', json={'action': 'home'}).status_code == 400


def test_browser_child_does_not_receive_model_tokens(monkeypatch, tmp_path):
    monkeypatch.setenv('OPENAI_API_KEY', 'test-secret')
    monkeypatch.setenv('CUSTOM_API_KEY', 'test-secret')
    monkeypatch.setenv('PRIVATE_TOKEN', 'test-secret')
    env = config.clean_environment(tmp_path)
    assert all('test-secret' != value for value in env.values())
    assert env['PLAYWRIGHT_BROWSERS_PATH'] == str(tmp_path / 'browsers')


def test_prepare_reuses_valid_libraries_and_repairs_a_broken_probe(tmp_path, monkeypatch):
    import browser_setup
    from types import SimpleNamespace
    ready(tmp_path)
    calls = []
    def run(command, **kwargs):
        calls.append(command)
        return SimpleNamespace(returncode=0,stdout=json.dumps({'version':config.VERSION,'browser_executable':str(tmp_path/'chrome')}))
    monkeypatch.setattr(browser_setup.subprocess, 'run', run)
    monkeypatch.setattr(browser_setup, 'browser_options', lambda home: {'channel': 'msedge'})
    browser_setup.prepare(tmp_path)
    assert len(calls) == 1 and 'pip' not in calls[0]
    calls.clear()
    def broken_once(command, **kwargs):
        calls.append(command)
        return SimpleNamespace(returncode=1 if len(calls) == 1 else 0,
            stdout=json.dumps({'version':config.VERSION,'browser_executable':str(tmp_path/'chrome')}))
    monkeypatch.setattr(browser_setup.subprocess, 'run', broken_once)
    browser_setup.prepare(tmp_path)
    assert len(calls) == 3 and 'pip' in calls[1]
    assert config.installed(tmp_path)


def test_failed_optional_install_does_not_publish_ready_marker(tmp_path, monkeypatch):
    import browser_setup
    def timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired('pip', 900)
    monkeypatch.setattr(browser_setup.subprocess, 'run', timeout)
    with pytest.raises(browser_setup.SetupFailure) as error:
        browser_setup.prepare(tmp_path)
    assert error.value.code=='timeout' and 'Проверьте интернет' not in str(error.value)
    assert not config.installed(tmp_path)


def test_main_chat_routes_enabled_browser_without_legacy_search(main_module, monkeypatch, tmp_path):
    import browser_control_jobs
    from chat_store import ChatStore
    requests = []
    class Jobs:
        enabled = True
        def start(self, **request):
            requests.append(request)
            return {'id': 'f' * 32}
        def snapshot(self):
            return {'results_id': 'e' * 32}
    monkeypatch.setattr(browser_control_jobs, 'jobs', Jobs())
    database = ChatStore(tmp_path / 'chats')
    monkeypatch.setattr(main_module.chat_api, 'store', lambda: database)
    monkeypatch.setattr(main_module.chat_api, 'get_intelligent_answerer', lambda: None)
    monkeypatch.setattr(main_module, 'intelligent_answerer', None)
    monkeypatch.setattr(main_module, 'HAS_V32_FEATURES', False)
    monkeypatch.setattr(main_module.memories_module, 'observe', lambda text: [])
    monkeypatch.setattr(main_module.web_integrations, 'search_youtube_video', lambda query: pytest.fail('Legacy search must not run'))
    async def check():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main_module.app), base_url='http://localhost') as client:
            ident = (await client.post('/chats')).json()['chat']['id']
            response = await client.post(f'/chats/{ident}/messages', data={'question': 'найди на YouTube уроки Python'})
            assert response.status_code == 200
            assert len(response.json()['chat']['messages']) == 2
    asyncio.run(check())
    assert requests == [{'action': 'search', 'query': 'уроки Python'}]


@pytest.mark.integration
def test_real_worker_stop_releases_owned_browser_processes(tmp_path):
    home = os.environ.get('SCOTT_BROWSER_TEST_HOME')
    if not home:
        pytest.skip('Explicit optional runtime required')
    import shutil
    import psutil
    ready(tmp_path)
    shutil.copytree(Path(home) / 'libraries', tmp_path / 'libraries', dirs_exist_ok=True)
    def popen(command, **kwargs):
        return subprocess.Popen(command + ['--headless'], **kwargs)
    manager = BrowserJobs(tmp_path, popen=popen)
    try:
        request = manager.start('search', 'Qt Quick official tutorial')
        eventually(lambda: manager.snapshot()['browser_open'], timeout=25)
        process = manager._process
        descendants = psutil.Process(process.pid).children(recursive=True)
        assert descendants
        assert manager.cancel(request['id'])['state'] == 'cancelled'
        assert process.poll() is not None
        eventually(lambda: all(not child.is_running() for child in descendants), timeout=5)
        assert not manager.snapshot()['browser_open'] and manager._process is None
    finally:
        manager.close()


@pytest.mark.integration
def test_live_youtube_search_in_owned_headless_profile(tmp_path):
    home = os.environ.get('SCOTT_BROWSER_TEST_HOME')
    if not home or os.environ.get('SCOTT_BROWSER_LIVE_TEST') != '1':
        pytest.skip('Explicit network check required')
    sys.path.insert(0, str(Path(home) / 'libraries'))
    from playwright.async_api import async_playwright
    async def check():
        async with async_playwright() as playwright:
            context = await playwright.chromium.launch_persistent_context(str(tmp_path / 'live-profile'), headless=True,
                                                                          **config.browser_options(Path(home)))
            try:
                candidates = await YouTubeDriver(context.pages[0]).search('Qt Quick official tutorial')
                assert candidates and len(candidates) <= 5
                assert all(len(row['video_id']) == 11 and row['title'] for row in candidates)
            finally:
                await context.close()
    asyncio.run(check())


@pytest.mark.integration
def test_real_browser_search_play_pause_resume_with_synthetic_media(tmp_path):
    home = os.environ.get('SCOTT_BROWSER_TEST_HOME')
    if not home:
        pytest.skip('Explicit optional runtime required; never open a personal profile')
    sys.path.insert(0, str(Path(home) / 'libraries'))
    from playwright.async_api import async_playwright
    output = io.BytesIO()
    with wave.open(output, 'wb') as audio:
        audio.setnchannels(1); audio.setsampwidth(2); audio.setframerate(8000)
        audio.writeframes(b'\0\0' * 8000 * 10)
    media = base64.b64encode(output.getvalue()).decode('ascii')
    results = '<ytd-video-renderer><a id="video-title" href="/watch?v=abcdefghijk">Example</a></ytd-video-renderer><ytd-video-renderer><a id="video-title" href="/watch?v=0123456789_">Second</a></ytd-video-renderer>'
    player = '<title>Example - YouTube</title><video muted loop src="data:audio/wav;base64,' + media + '"></video><button class="ytp-play-button" onclick="const v=document.querySelector(\'video\');v.paused?v.play():v.pause()">Play</button>'
    async def check():
        async with async_playwright() as playwright:
            context = await playwright.chromium.launch_persistent_context(str(tmp_path / 'profile'), headless=True,
                                                                          **config.browser_options(Path(home)))
            try:
                async def route(request):
                    await request.fulfill(status=200, content_type='text/html', body=player if '/watch?' in request.request.url else results)
                await context.route('**/*', route)
                page = context.pages[0]
                driver = YouTubeDriver(page)
                candidates = await driver.search('example')
                assert len(candidates) == 2 and candidates[0]['video_id'] == 'abcdefghijk'
                assert (await driver.playback('resume', candidates[0]['video_id']))['verified']
                assert (await driver.playback('pause'))['paused']
                assert not (await driver.playback('resume'))['paused']
            finally:
                await context.close()
    asyncio.run(check())
