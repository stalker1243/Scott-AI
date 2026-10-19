"""No sockets, real providers, personal data, or desktop actions."""
import asyncio
import json

import httpx
import pytest
from fastapi import FastAPI
from pydantic import BaseModel
from starlette.responses import JSONResponse

import api_boundary as boundary

pytestmark = pytest.mark.unit


def make_app(**kwargs):
    app = FastAPI()
    boundary.install_error_handlers(app)
    app.add_middleware(boundary.ApiBoundary, allowed_origins=['http://localhost:1420'],
                       remote_paths={'/health'}, device_lookup=lambda key: {'name': 'fixture'} if key == 'fixture-key' else None,
                       **kwargs)
    calls = []

    @app.api_route('/health', methods=['GET', 'POST'])
    async def health():
        calls.append('health')
        return {'status': 'online'}

    class KeyInput(BaseModel):
        api_key: int

    @app.post('/settings')
    async def settings(body: KeyInput):
        calls.append('settings')
        return {'success': True}

    @app.get('/crash')
    async def crash():
        raise RuntimeError('fixture-SECRET-user-text')

    return app, calls


def request(app, method='GET', path='/health', peer='127.0.0.1', **kwargs):
    async def run():
        transport = httpx.ASGITransport(app=app, client=(peer, 32123))
        async with httpx.AsyncClient(transport=transport, base_url='http://localhost') as client:
            return await client.request(method, path, **kwargs)
    return asyncio.run(run())


@pytest.mark.parametrize('headers', [
    {'Origin': 'https://attacker.example'}, {'Origin': 'null'},
    {'Host': 'attacker.example:8000'}, {'Host': 'localhost.attacker.example'},
    {'Host': 'localhost@attacker.example'}, {'Host': '[::1'},
    {'Sec-Fetch-Site': 'cross-site'},
    [('Host', 'localhost'), ('Host', 'attacker.example')],
    [('Origin', 'http://localhost:1420'), ('Origin', 'https://attacker.example')],
])
def test_browser_request_is_rejected_before_action(headers):
    app, calls = make_app()
    result = request(app, 'POST', headers=headers, content='x=1')
    assert result.status_code in (400, 403)
    assert not calls
    assert result.json()['code'].startswith('SCOTT-API-')


@pytest.mark.parametrize('host', ['localhost', 'localhost:8000', '127.0.0.1:8000', '[::1]:8000'])
def test_native_loopback_and_known_dev_origin(host):
    app, calls = make_app()
    assert request(app, headers={'Host': host}).status_code == 200
    assert request(app, 'POST', headers={'Host': host, 'Origin': 'http://localhost:1420'}, json={}).status_code == 200
    assert len(calls) == 2


def test_remote_requires_path_and_paired_key_and_cannot_spoof_peer():
    app, calls = make_app()
    assert request(app, peer='192.0.2.1').status_code == 403
    assert request(app, peer='192.0.2.1', path='/settings', headers={'X-Scott-Device': 'fixture-key'}).status_code == 404
    assert request(app, peer='192.0.2.1', headers={'X-Scott-Device': 'fixture-key'}).status_code == 200
    assert request(app, peer='192.0.2.1', headers={'X-Forwarded-For': '127.0.0.1'}).status_code == 403
    assert calls == ['health']


def test_validation_does_not_echo_token_and_empty_body_finishes():
    app, calls = make_app()
    response = request(app, 'POST', '/settings', json={'api_key': 'fixture-SECRET-user-text'})
    assert response.status_code == 422
    assert 'fixture-SECRET' not in response.text
    assert response.json()['hint']
    assert request(app, 'POST', '/settings').status_code == 422
    assert not calls


def test_unexpected_failure_is_safe_identifiable_and_backend_survives(monkeypatch):
    recorded = []
    monkeypatch.setattr(boundary, 'append_log', lambda name, text: recorded.append((name, text)))
    app, _ = make_app()
    response = request(app, path='/crash', headers={'X-Request-ID': 'attacker-id'})
    assert response.status_code == 500
    error = response.json()
    assert error['request_id'] != 'attacker-id'
    assert response.headers['x-request-id'] == error['request_id']
    assert response.headers['cache-control'] == 'no-store'
    assert response.headers['x-content-type-options'] == 'nosniff'
    assert error['request_id'] in recorded[0][1]
    assert 'RuntimeError' in recorded[0][1]
    assert 'fixture-SECRET' not in response.text + str(recorded)
    assert 'Traceback' not in response.text
    assert request(app).status_code == 200


def scope(kind='http', **changes):
    value = dict(type=kind, asgi={'version': '3.0'}, method='POST', path='/health', raw_path=b'/health',
                 root_path='', scheme='http', query_string=b'', server=('localhost', 8000),
                 client=('127.0.0.1', 32123), headers=[(b'host', b'localhost')], http_version='1.1')
    value.update(changes)
    return value


@pytest.mark.parametrize('mode', ['declared', 'chunked', 'mismatch', 'invalid', 'disconnect', 'timeout'])
def test_incomplete_or_oversized_body_never_dispatches(mode):
    app, calls = make_app(max_body_bytes=8, body_timeout=.02)
    async def run():
        sent = []
        header = b'9' if mode == 'declared' else b'4' if mode == 'mismatch' else b'-1' if mode == 'invalid' else None
        incoming = scope(headers=[(b'host', b'localhost')] + ([(b'content-length', header)] if header else []))
        async def receive():
            if mode == 'timeout':
                await asyncio.sleep(1)
            if mode == 'disconnect':
                return {'type': 'http.disconnect'}
            return {'type': 'http.request', 'body': b'123456789' if mode == 'chunked' else b'x', 'more_body': False}
        async def send(message):
            sent.append(message)
        await app(incoming, receive, send)
        return sent
    sent = asyncio.run(run())
    assert not calls
    expected = {'declared': 413, 'chunked': 413, 'mismatch': 400, 'invalid': 400, 'timeout': 408}
    if mode in expected:
        assert sent[0]['status'] == expected[mode]
    else:
        assert not sent


def test_slow_uploads_leave_health_available_and_release_slots():
    async def run():
        app, calls = make_app(body_timeout=1)
        release = asyncio.Event(); entered = 0
        async def receive():
            nonlocal entered
            entered += 1
            await release.wait()
            return {'type': 'http.request', 'body': b'', 'more_body': False}
        async def send(message):
            pass
        tasks = [asyncio.create_task(app(scope(), receive, send)) for _ in range(4)]
        while entered < 4:
            await asyncio.sleep(.001)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://localhost') as client:
            assert (await client.post('/health')).status_code == 429
            assert (await client.get('/health')).status_code == 200
            release.set(); await asyncio.gather(*tasks)
            assert (await client.post('/health')).status_code == 200
        assert len(calls) == 6
    asyncio.run(run())


@pytest.mark.parametrize('peer,headers', [
    ('192.0.2.1', [(b'host', b'localhost'), (b'x-scott-device', b'fixture-key')]),
    ('127.0.0.1', [(b'host', b'localhost'), (b'origin', b'https://attacker.example')]),
    ('127.0.0.1', [(b'host', b'attacker.example')]),
])
def test_websocket_denied_before_accept(peer, headers):
    called = []
    async def inner(*args):
        called.append(True)
    async def run():
        sent = []
        async def receive():
            return {'type': 'websocket.connect'}
        async def send(value):
            sent.append(value)
        app = boundary.ApiBoundary(inner, allowed_origins=['http://localhost:1420'], remote_paths={'/health'}, device_lookup=lambda _: {})
        await app(scope('websocket', path='/ws/chat', client=(peer, 123), headers=headers), receive, send)
        return sent
    assert asyncio.run(run()) == [{'type': 'websocket.close', 'code': 1008}]
    assert not called


def test_actual_main_rejects_foreign_origin_and_keeps_health(main_module):
    assert request(main_module.app, headers={'Origin': 'https://attacker.example'}).status_code == 403
    assert request(main_module.app).status_code == 200


def test_websocket_size_limit_closes_before_dispatch():
    reached = []
    async def inner(incoming, receive, send):
        assert (await receive())['type'] == 'websocket.connect'
        await send({'type': 'websocket.accept'})
        message = await receive()
        assert message == {'type': 'websocket.disconnect', 'code': 1009}
        reached.append(True)
    async def run():
        messages = iter([{'type': 'websocket.connect'}, {'type': 'websocket.receive', 'text': 'x'*(boundary.MAX_WS_BYTES+1)}])
        sent = []
        async def receive(): return next(messages)
        async def send(value): sent.append(value)
        app = boundary.ApiBoundary(inner, allowed_origins=[], remote_paths=[], device_lookup=lambda _: None)
        await app(scope('websocket'), receive, send)
        return sent
    assert asyncio.run(run()) == [{'type': 'websocket.accept'}, {'type': 'websocket.close', 'code': 1009}]
    assert reached == [True]


def test_allowed_development_origin_can_use_cross_site_loopback():
    app, calls = make_app()
    assert request(app, headers={'Origin': 'http://localhost:1420', 'Sec-Fetch-Site': 'cross-site'}).status_code == 200
    assert calls == ['health']


@pytest.mark.parametrize('status,detail', [(401,'Missing Authorization header'), (403,'IP not allowed'),
                                         (404,'Not Found'), (405,'Method Not Allowed'), (429,'Too many requests')])
def test_technical_status_text_has_a_user_message(status, detail):
    response = boundary.error_response(status, scope(), detail)
    value = json.loads(response.body)
    assert value['message'] == boundary.MESSAGES[status][0]
    assert value['hint'] and value['code'] == f'SCOTT-API-{status}'


def test_dangerous_action_rate_limit_is_atomic(monkeypatch):
    import security
    from concurrent.futures import ThreadPoolExecutor
    from types import SimpleNamespace
    from fastapi import HTTPException
    monkeypatch.setattr(security, '_redis', None)
    monkeypatch.setattr(security, '_rate_store', {})
    monkeypatch.setattr(security, 'RATE_LIMIT_PER_MIN', 5)
    incoming = SimpleNamespace(client=SimpleNamespace(host='127.0.0.1'))
    def attempt(_):
        try:
            security.check_rate_limit(incoming)
            return True
        except HTTPException as exc:
            assert exc.status_code == 429
            return False
    with ThreadPoolExecutor(max_workers=20) as pool:
        assert sum(pool.map(attempt, range(100))) == 5


@pytest.mark.parametrize('value', [None, 123, {}, 'x'*2049, 'тест'])
def test_remote_token_invalid_values_are_denied(value, monkeypatch):
    import remote_access
    monkeypatch.setattr(remote_access, '_load', lambda: {'devices': [{'token': 'fixture'}]})
    assert remote_access.find_by_token(value) is None


@pytest.mark.parametrize('command', ['powershell', 'run_script', 'delete_file', 'file_operation', 'system_command', 'kill_process', 'open_app', 'open_program'])
def test_legacy_ai_execute_cannot_bypass_dangerous_token(main_module, monkeypatch, command):
    import ai_endpoints
    import security
    monkeypatch.setattr(security, 'EXECUTE_TOKEN', '')
    monkeypatch.setattr(ai_endpoints, 'get_command_executor', lambda: pytest.fail('Executor must not be reached'))
    result = request(main_module.app, 'POST', '/ai/execute', json={'command_type': command, 'params': {'name': 'powershell', 'args': '-Command fixture'} if command.startswith('open_') else {}})
    assert result.status_code in (401, 403)


def test_invalid_ai_parameters_do_not_reach_executor(main_module, monkeypatch):
    import ai_endpoints
    monkeypatch.setattr(ai_endpoints, 'get_command_executor', lambda: pytest.fail('Executor must not be reached'))
    assert request(main_module.app, 'POST', '/ai/execute', json={'command_type': 'open_app', 'params': ['bad']}).status_code == 422


def test_document_zip_budget_and_generic_error(monkeypatch):
    import io
    import zipfile
    import attachments
    monkeypatch.setattr(attachments, 'MAX_DOCX_EXPANDED', 16)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr('word/document.xml', 'x'*200)
    result = attachments.read('fixture.docx', data=buffer.getvalue())
    assert not result.ok and 'DOCX' in result.error
    result = attachments.read('fixture.pdf', data=b'fixture-SECRET-bad-pdf')
    assert not result.ok and 'fixture-SECRET' not in result.error


def test_missing_audio_dependency_keeps_routes_and_explains_failure(monkeypatch):
    import builtins
    import importlib.util
    import runtime
    from pathlib import Path
    original = builtins.__import__
    def without_listener(name, *args, **kwargs):
        if name == 'listener':
            raise ImportError('fixture audio dependency is missing')
        return original(name, *args, **kwargs)
    monkeypatch.setattr(builtins, '__import__', without_listener)
    monkeypatch.setattr(runtime, 'listener', None)
    path = Path(__file__).resolve().parents[1]/'listen_endpoints.py'
    spec = importlib.util.spec_from_file_location('listen_optional_fixture', path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    app = FastAPI(); app.include_router(module.router)
    assert request(app, path='/listen/status').json()['available'] is False
    for method, path in [('GET','/listen/devices'), ('POST','/listen/start')]:
        result = request(app, method, path)
        assert result.status_code == 503
        assert result.json()['message'] == 'Голосовой режим недоступен. Проверьте настройки звука.'
