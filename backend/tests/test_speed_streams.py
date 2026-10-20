"""Latency/cancellation contracts, all providers and audio are synthetic."""
import asyncio
import json
import threading
import time
from types import SimpleNamespace
import pytest
from backend import model_stream, request_flow, text_stream, voice_flow, model_capabilities
from backend.tests.test_chats import setup, create, routes

pytestmark = pytest.mark.unit

def chunk(text='', finish=None, **delta):
    return dict(choices=[dict(index=0, delta=dict(content=text, **delta), finish_reason=finish)])

class SDKStream:
    def __init__(self, rows):
        self.rows = rows
        self.closed = False
    def __iter__(self):
        for row in self.rows:
            if isinstance(row, Exception):
                raise row
            yield SimpleNamespace(model_dump=lambda row=row: row)
    def close(self): self.closed = True

@pytest.mark.parametrize('provider', ['OpenAI', 'Groq'])
def test_sdk_stream_first_text_before_completion_and_closes(provider):
    seen, calls = [], []
    def rows():
        yield chunk('Первая фраза. ')
        assert seen == ['Первая фраза. ']
        yield chunk('Продолжение.')
        yield chunk(finish='stop')
    stream = SDKStream(rows())
    def create(**options): calls.append(options); return stream
    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    ia = SimpleNamespace(api_provider=provider, client=client, model='fixture', max_tokens=100)
    with request_flow.use(request_flow.Flow(seen.append)):
        assert model_stream.complete(ia, [dict(role='user', content='fixture')], 'system') == 'Первая фраза. Продолжение.'
    assert calls[0]['stream'] is True and stream.closed

@pytest.mark.parametrize('rows', [
    [chunk('partial')], [chunk('partial'), OSError('broken stream')],
    [chunk('partial', 'tool_calls')], [chunk('', tool_calls=[{'id':'unsafe'}])],
    [dict(error={'message':'provider secret'})], [chunk('x'*(model_stream.MAX_TEXT+1))],
])
def test_incomplete_error_tool_and_large_streams_never_succeed(rows):
    stream = SDKStream(rows)
    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=lambda **kw:stream)))
    ia = SimpleNamespace(api_provider='OpenAI', client=client, model='fixture', max_tokens=100)
    with request_flow.use(request_flow.Flow()):
        with pytest.raises((ValueError, OSError)):
            model_stream.complete(ia, [], 'system')
    assert stream.closed

def test_cancellation_closes_provider_without_replaying():
    flow = request_flow.Flow()
    def rows():
        yield chunk('One')
        flow.cancelled.set()
        yield chunk('Two')
    stream = SDKStream(rows())
    ia = SimpleNamespace(api_provider='Groq', model='fixture', max_tokens=100,
                         client=SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=lambda **kw:stream))))
    with request_flow.use(flow), pytest.raises(request_flow.RequestCancelled):
        model_stream.complete(ia, [], 'system')
    assert stream.closed

class HTTPResponse:
    status_code = 200
    def __init__(self, rows): self.rows = rows; self.closed = False
    def iter_lines(self, **kw):
        for row in self.rows:
            yield b'data: ' + (row if isinstance(row, bytes) else json.dumps(row, ensure_ascii=False).encode())
            yield b''
    def raise_for_status(self): pass
    def close(self): self.closed = True

@pytest.mark.parametrize('provider', ['DeepSeek', 'OpenRouter', 'Anthropic'])
def test_http_streams_and_utf8(provider, monkeypatch):
    rows = [chunk('Привет'), chunk('!', 'stop'), b'[DONE]']
    if provider == 'Anthropic':
        rows = [dict(type='ping'), dict(type='content_block_start',content_block=dict(type='text',text='При')),
                dict(type='content_block_delta', delta=dict(type='text_delta',text='вет!')), dict(type='message_stop')]
    response = HTTPResponse(rows)
    calls = []
    def post(*args, **kw): calls.append((args,kw)); return response
    monkeypatch.setattr(model_stream, 'session', lambda:SimpleNamespace(post=post,cookies=SimpleNamespace(clear=lambda:None)))
    ia = SimpleNamespace(api_provider=provider, model='fixture', max_tokens=100,
                         client=dict(api_key='fake-test-token',base_url='https://example.invalid/v1'))
    seen = []
    with request_flow.use(request_flow.Flow(seen.append)):
        assert model_stream.complete(ia, [dict(role='user',content='fixture')], 'system') == 'Привет!'
    assert ''.join(seen) == 'Привет!' and response.closed
    assert calls[0][1]['stream'] is True and calls[0][1]['allow_redirects'] is False

def test_sse_transport_delivers_before_provider_end_and_does_not_commit_on_disconnect(setup,monkeypatch):
    release = threading.Event()
    def complete(*args):
        request_flow.current().emit('Первая фраза. ')
        release.wait(2)
        request_flow.current().check()
        return 'Первая фраза. Всё.'
    monkeypatch.setattr(routes, 'complete', complete)
    ident = create(setup)
    async def check():
        response = text_stream.response(lambda:routes._send_message(ident,'fixture','chat',None),{})
        iterator = response.body_iterator
        try:
            first = await asyncio.wait_for(anext(iterator),1)
            assert 'event: delta' in first and 'Первая фраза' in first
            assert setup.db.get(ident)['messages'] == []
            assert ident in routes._busy_chats
        finally:
            await iterator.aclose()
            release.set()
        for _ in range(200):
            if ident not in routes._busy_chats: break
            await asyncio.sleep(.005)
        assert ident not in routes._busy_chats
        assert setup.db.get(ident)['messages'] == []
    asyncio.run(check())

@pytest.mark.parametrize('failure',[False,True])
def test_route_sse_terminal_event_and_safe_failure(setup,monkeypatch,failure):
    def complete(*args):
        request_flow.current().emit('Начало. ')
        if failure: raise RuntimeError('fake-test-token secret traceback')
        return 'Начало. Конец.'
    monkeypatch.setattr(routes, 'complete', complete)
    ident = create(setup)
    response = setup.client.post(f'/chats/{ident}/messages',data=dict(question='fixture',stream='true'))
    assert response.status_code == 200 and 'text/event-stream' in response.headers['content-type']
    assert 'event: delta' in response.text
    assert ('event: error' if failure else 'event: done') in response.text
    assert 'fake-test-token' not in response.text and 'traceback' not in response.text
    assert len(setup.db.get(ident)['messages']) == (0 if failure else 2)

def test_streaming_multipart_upload_remains_readable_until_body_runs(setup,monkeypatch):
    prompts=[]
    def complete(ia,messages,instructions):
        prompts.append(messages)
        request_flow.current().emit('Файл прочитан.')
        return 'Файл прочитан.'
    monkeypatch.setattr(routes,'complete',complete)
    ident=create(setup)
    result=setup.client.post(f'/chats/{ident}/messages',data={'question':'Проверь файл','stream':'true'},
                            files=[('files',('fixture.txt',b'controlled file content','text/plain'))])
    assert result.status_code == 200 and 'event: done' in result.text and 'event: error' not in result.text
    assert 'controlled file content' in prompts[0][-1]['content']
    assert len(setup.db.get(ident)['messages']) == 2

def test_streaming_action_runs_once_and_never_contacts_model(setup,monkeypatch):
    calls=[]
    async def action(text,**kwargs):calls.append(text);return dict(response='Открыто.')
    monkeypatch.setattr(routes,'auto_command_handler',action)
    monkeypatch.setattr(routes,'complete',lambda *a:pytest.fail('Local action reached a model'))
    ident=create(setup)
    result=setup.client.post(f'/chats/{ident}/messages',data={'question':'Открой fixture','stream':'true'})
    assert result.status_code == 200 and 'event: done' in result.text
    assert calls == ['Открой fixture'] and len(setup.db.get(ident)['messages']) == 2

def test_request_provider_snapshot_is_stable_and_releases_lock(setup):
    snapshot = request_flow.provider_snapshot(setup.ia)
    setup.ia.model = 'new-model'
    setup.ia.client['api_key'] = 'new-key'
    assert snapshot.model == 'demo/vision'
    assert snapshot.client['api_key'] == 'test-secret'

def test_real_http_disconnect_cancels_worker_and_preserves_history(setup,monkeypatch):
    """Exercise ASGI disconnect handling, not a buffered TestClient response."""
    import socket
    import requests
    import uvicorn
    from backend.api_boundary import ApiBoundary
    from fastapi import FastAPI
    app = FastAPI()
    app.include_router(routes.router)
    app.add_middleware(ApiBoundary, allowed_origins=['http://localhost:1420'],
                       remote_paths={'/health'}, device_lookup=lambda key:None)
    release = threading.Event()
    def complete(*args):
        request_flow.current().emit('First complete sentence. ')
        release.wait(3)
        request_flow.current().check()
        return 'First complete sentence. Last sentence.'
    monkeypatch.setattr(routes,'complete',complete)
    ident = create(setup)
    listener = socket.socket()
    listener.bind(('127.0.0.1',0))
    listener.listen(8)
    server = uvicorn.Server(uvicorn.Config(app,log_level='critical',access_log=False,log_config=None,lifespan='off'))
    thread = threading.Thread(target=lambda:server.run(sockets=[listener]),daemon=True)
    thread.start()
    try:
        for _ in range(200):
            if server.started:break
            time.sleep(.005)
        assert server.started
        with requests.post(f'http://127.0.0.1:{listener.getsockname()[1]}/chats/{ident}/messages',
                           data={'question':'fixture','stream':'true'},stream=True,timeout=2) as response:
            assert response.status_code == 200
            lines = response.iter_lines(chunk_size=1)
            assert next(lines) == b'event: delta'
            assert b'First complete sentence' in next(lines)
            assert not setup.db.get(ident)['messages']
        # The socket is now closed while the provider is still producing.
        time.sleep(.06)
        release.set()
        for _ in range(200):
            if ident not in routes._busy_chats:break
            time.sleep(.005)
        assert ident not in routes._busy_chats
        assert not setup.db.get(ident)['messages']
    finally:
        release.set()
        server.should_exit = True
        thread.join(4)
        listener.close()
        assert not thread.is_alive()

@pytest.mark.parametrize('uptime',[10.0,1000.0])
def test_stale_model_catalog_refresh_is_bounded_and_nonblocking(monkeypatch,uptime):
    from backend import intelligent_answerer
    started,release = threading.Event(),threading.Event()
    calls=[]
    def refresh(): calls.append(True);started.set();release.wait(2)
    monkeypatch.setattr(intelligent_answerer, 'list_openrouter_models', refresh)
    monkeypatch.setattr(model_capabilities, '_updated', 0)
    monkeypatch.setattr(model_capabilities, '_refresh_attempt', 0)
    monkeypatch.setattr(model_capabilities, '_refreshing', False)
    # A freshly booted Linux host can have monotonic uptime below the TTL.
    # Patch this module's clock only, leaving asyncio/HTTP deadlines untouched.
    monkeypatch.setattr(model_capabilities, 'time', SimpleNamespace(monotonic=lambda:uptime))
    try:
        for _ in range(8):
            model_capabilities.capabilities('OpenRouter','fixture',refresh='background')
        assert started.wait(1) and calls == [True]
    finally:
        release.set()
        for _ in range(100):
            if not model_capabilities._refreshing:break
            time.sleep(.005)

def test_voice_starts_complete_sentence_before_model_finishes():
    async def check():
        spoken = []
        first = asyncio.Event()
        async def play(text): spoken.append(text);first.set();return True
        async def process():
            flow = request_flow.current()
            await asyncio.to_thread(flow.emit, 'Первая законченная фраза. Вторая')
            await asyncio.wait_for(first.wait(),1)
            assert spoken == ['Первая законченная фраза.']
            await asyncio.to_thread(flow.emit, ' законченная фраза.')
            return dict(response='Первая законченная фраза. Вторая законченная фраза.')
        await voice_flow.respond(process,play,lambda:True,lambda s:s,lambda:play('cue'),10)
        assert spoken == ['Первая законченная фраза.','Вторая законченная фраза.']
    asyncio.run(check())

def test_voice_cancellation_never_plays_remainder_or_repeats_prefix():
    async def check():
        spoken=[];valid=True
        async def play(text):
            nonlocal valid
            spoken.append(text);valid=False;return True
        async def process():
            await asyncio.to_thread(request_flow.current().emit,'Первая законченная фраза. Вторая')
            await asyncio.sleep(.03)
            return dict(response='Первая законченная фраза. Вторая фраза.')
        await voice_flow.respond(process,play,lambda:valid,lambda s:s,lambda:play('cue'),10)
        assert spoken == ['Первая законченная фраза.']
    asyncio.run(check())

@pytest.mark.parametrize('text',['Версия 1.2 ещё готовится','```python\nprint("Hi.")\n```','Простой ответ'])
def test_voice_does_not_start_incomplete_or_code_fragments(text):
    async def check():
        spoken=[]
        async def play(value):
            assert request_flow.current() is not None
            spoken.append(value)
            return True
        async def process():
            await asyncio.to_thread(request_flow.current().emit,text)
            assert not spoken
            return dict(response=text)
        await voice_flow.respond(process,play,lambda:True,lambda s:s,lambda:play('cue'),10)
        assert spoken == [text]
    asyncio.run(check())
