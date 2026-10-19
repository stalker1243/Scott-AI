import base64
import asyncio
import io
import threading
import time
from types import SimpleNamespace
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image

from backend import chat_endpoints as routes, model_capabilities as caps, memories
from backend.chat_store import ChatStore


def png():
    output = io.BytesIO()
    Image.new('RGB', (16, 12), '#5588ff').save(output, 'PNG')
    return output.getvalue()


@pytest.fixture
def setup(tmp_path, monkeypatch):
    monkeypatch.setattr(routes, 'auto_command_handler', None)
    database = ChatStore(tmp_path / 'chats')
    monkeypatch.setattr(routes, 'store', lambda: database)
    ia = SimpleNamespace(enabled=True, api_provider='OpenRouter', model='demo/vision', max_tokens=1000,
                         custom_keys={}, env_keys={}, client={'api_key': 'test-secret', 'base_url': 'https://openrouter.ai/api/v1'},
                         _state_lock=lambda: threading.RLock(), instructions=lambda **kw: 'System')
    monkeypatch.setattr(routes, 'get_intelligent_answerer', lambda: ia)
    capabilities = dict(known=True, text=True, documents=True, images=True, video=True, image_generation=True)
    monkeypatch.setattr(caps, 'capabilities', lambda *args, **kw: dict(capabilities))
    observed, sent = [], []
    monkeypatch.setattr(memories, 'observe', observed.append)
    monkeypatch.setattr(routes, 'complete', lambda ai, messages, instructions: sent.append(messages) or 'Ответ')
    app = FastAPI()
    app.include_router(routes.router)
    @app.get('/health')
    def health():
        return {'status': 'online'}
    with TestClient(app) as client:
        yield SimpleNamespace(client=client, db=database, ia=ia, capabilities=capabilities, observed=observed, sent=sent)


def create(env):
    return env.client.post('/chats').json()['chat']['id']


@pytest.mark.parametrize('text', ['Нарисуй кота', 'Скотт, создай картинку ночного города',
    'Сгенерируй изображение леса', 'Можешь нарисовать закат?', 'Generate an image of a robot'])
def test_image_request_runs_without_mode_button(setup, monkeypatch, text):
    generated = []
    monkeypatch.setattr(routes, 'generate', lambda ia, prompt: generated.append(prompt) or png())
    ident = create(setup)
    result = setup.client.post(f'/chats/{ident}/messages', data={'question': text})
    assert result.status_code == 200
    assert generated == [text]
    assert result.json()['chat']['messages'][-1]['attachments'][0]['mime'] == 'image/png'
    assert not setup.sent


@pytest.mark.parametrize('text', ['Как нарисовать кота?', 'Не рисуй кота', 'Создай файл image.py',
    'Напиши код генерации изображений', 'Переведи: нарисуй кота', 'Я сказал нарисуй кота'])
def test_discussion_of_images_does_not_generate(setup, monkeypatch, text):
    monkeypatch.setattr(routes, 'generate', lambda *a: pytest.fail('Unrequested image generation'))
    result = setup.client.post(f'/chats/{create(setup)}/messages', data={'question': text})
    assert result.status_code == 200 and setup.sent


def test_automatic_image_request_checks_model_before_provider(setup, monkeypatch):
    setup.capabilities['image_generation'] = False
    monkeypatch.setattr(routes, 'generate', lambda *a: pytest.fail('Unsupported generation'))
    ident = create(setup)
    result = setup.client.post(f'/chats/{ident}/messages', data={'question': 'Нарисуй кота'})
    assert result.status_code == 400 and 'не поддерживает генерацию' in result.json()['detail']
    assert not setup.db.get(ident)['messages'] and not setup.sent


def test_identity_is_local_without_token_and_follow_up_is_chat_scoped(setup, monkeypatch):
    from backend import assistant_identity as identity
    env = setup
    first, second = create(env), create(env)
    env.ia.enabled = False
    def no_model(): pytest.fail('Local introduction initialized a model')
    monkeypatch.setattr(routes, 'get_intelligent_answerer', no_model)
    result = env.client.post(f'/chats/{first}/messages', data={'question': 'Кто ты?'}).json()
    assert result['chat']['messages'][-1]['text'] == identity.INTRODUCTION
    assert result['chat']['messages'][-1]['model'] == 'Scott · знакомство'
    result = env.client.post(f'/chats/{first}/messages', data={'question': 'Да, расскажи подробнее'}).json()
    assert result['chat']['messages'][-1]['text'] == identity.HOW_IT_WORKS
    assert len(result['chat']['messages']) == 4
    # No offer in another chat: the ordinary model path is still selected.
    monkeypatch.setattr(routes, 'get_intelligent_answerer', lambda: env.ia)
    env.ia.enabled = True
    result = env.client.post(f'/chats/{second}/messages', data={'question': 'да'}).json()
    assert result['chat']['messages'][-1]['text'] == 'Ответ'
    assert env.sent


def test_cleared_chat_does_not_keep_identity_offer(setup):
    env = setup
    ident = create(env)
    env.client.post(f'/chats/{ident}/messages', data={'question': 'Кто тебя создал?'})
    env.db.delete(ident, clear=True)
    result = env.client.post(f'/chats/{ident}/messages', data={'question': 'да'}).json()
    assert result['chat']['messages'][-1]['text'] == 'Ответ'


def test_plain_chat_executes_recognised_request_without_model(setup, monkeypatch):
    env = setup
    calls = []
    async def action(text, quiet_mode):
        calls.append((text, quiet_mode))
        return {'response': 'Блокнот открыт'}
    monkeypatch.setattr(routes, 'auto_command_handler', action)
    env.ia.enabled = False
    ident = create(env)
    response = env.client.post(f'/chats/{ident}/messages', data={'question': 'Скотт, можешь открыть блокнот?'})
    assert response.status_code == 200
    assert calls == [('Скотт, можешь открыть блокнот?', True)]
    messages = response.json()['chat']['messages']
    assert messages[-1]['text'] == 'Блокнот открыт'
    assert messages[-1]['model'] == 'Scott · действие'
    assert len(messages) == 2 and not env.sent
    assert ident not in routes._busy_chats


def test_automatic_fallback_keeps_named_chat_context(setup, monkeypatch):
    env = setup
    async def question(text, quiet_mode):
        return None
    monkeypatch.setattr(routes, 'auto_command_handler', question)
    ident = create(env)
    for text in ['План проекта', 'Продолжи этот план']:
        response = env.client.post(f'/chats/{ident}/messages', data={'question': text})
        assert response.status_code == 200
    assert len(env.sent) == 2
    assert env.sent[-1][0]['content'] == 'План проекта'
    assert env.sent[-1][-1]['content'] == 'Продолжи этот план'
    assert len(response.json()['chat']['messages']) == 4
    assert ident not in routes._busy_chats


def test_attachments_never_go_to_action_executor(setup, monkeypatch):
    async def unexpected(*args, **kwargs):
        pytest.fail('An attachment must remain model input')
    monkeypatch.setattr(routes, 'auto_command_handler', unexpected)
    ident = create(setup)
    response = setup.client.post(f'/chats/{ident}/messages', data={'question': 'Открой блокнот'},
                                files=[('files', ('notes.txt', b'example', 'text/plain'))])
    assert response.status_code == 200 and len(setup.sent) == 1


def test_failed_auto_action_releases_chat_and_does_not_call_model(setup, monkeypatch):
    async def empty(text, quiet_mode):
        return {'response': ''}
    monkeypatch.setattr(routes, 'auto_command_handler', empty)
    ident = create(setup)
    response = setup.client.post(f'/chats/{ident}/messages', data={'question': 'Открой блокнот'})
    assert response.status_code == 502
    assert ident not in routes._busy_chats
    assert not setup.sent and setup.db.get(ident)['messages'] == []


def test_busy_auto_action_rejects_second_request_and_history_change(setup, monkeypatch):
    started, release = threading.Event(), threading.Event()
    calls = []
    async def action(text, quiet_mode):
        calls.append(text)
        started.set()
        while not release.is_set():
            await asyncio.sleep(0.005)
        return {'response': 'Готово'}
    monkeypatch.setattr(routes, 'auto_command_handler', action)
    ident = create(setup)
    with ThreadPoolExecutor(max_workers=1) as pool:
        pending = pool.submit(setup.client.post, f'/chats/{ident}/messages', data={'question': 'Открой блокнот'})
        try:
            assert started.wait(3)
            assert setup.client.post(f'/chats/{ident}/messages', data={'question': 'Открой браузер'}).status_code == 409
            assert setup.client.delete(f'/chats/{ident}/messages').status_code == 409
        finally:
            release.set()
        assert pending.result(timeout=3).status_code == 200
    assert calls == ['Открой блокнот']
    assert len(setup.db.get(ident)['messages']) == 2
    assert ident not in routes._busy_chats


def test_code_format_is_requested_without_changing_context(setup, monkeypatch):
    captured = []
    def complete(ia, messages, instructions):
        captured.append(instructions)
        assert messages[-1]['content'] == 'Напиши функцию приветствия'
        return 'Пример:\n```python\ndef greet():\n    return "Hi"\n```'
    monkeypatch.setattr(routes, 'complete', complete)
    response = setup.client.post(f'/chats/{create(setup)}/messages', data={'question': 'Напиши функцию приветствия'})
    assert response.status_code == 200
    assert 'Markdown' in captured[0] and captured[0].startswith('System')
    assert '```python' in response.json()['chat']['messages'][-1]['text']


def test_history_survives_restart_and_rename_clear_delete(setup):
    env = setup
    ident = create(env)
    assert env.client.post(f'/chats/{ident}/messages', data={'question': 'План проекта'}).status_code == 200
    reopened = ChatStore(env.db.directory)
    assert len(reopened.get(ident)['messages']) == 2
    assert reopened.context(ident)[0]['content'] == 'План проекта'
    assert env.client.patch(f'/chats/{ident}', json={'title': 'Новый план'}).json()['chat']['title'] == 'Новый план'
    assert env.client.delete(f'/chats/{ident}/messages').status_code == 200
    assert reopened.get(ident)['messages'] == []
    env.client.delete(f'/chats/{ident}')
    assert env.client.get(f'/chats/{ident}').status_code == 404


def test_context_is_scoped_to_chat_and_complete_pairs(setup):
    a, b = create(setup), create(setup)
    setup.client.post(f'/chats/{a}/messages', data={'question': 'Первый'})
    setup.client.post(f'/chats/{b}/messages', data={'question': 'Другой'})
    assert len(setup.sent[-1]) == 1
    setup.client.post(f'/chats/{a}/messages', data={'question': 'Продолжим'})
    assert [m['role'] for m in setup.sent[-1]] == ['user', 'assistant', 'user']
    assert 'Другой' not in str(setup.sent[-1])


def test_photo_and_document_bytes_reach_model_and_assets_deleted(setup):
    ident = create(setup)
    response = setup.client.post(f'/chats/{ident}/messages', data={'question': 'Разбери'},
                                 files=[('files', ('image.png', png(), 'image/png')), ('files', ('note.txt', 'Меня зовут Чужой'.encode(), 'text/plain'))])
    assert response.status_code == 200
    content = setup.sent[-1][-1]['content']
    assert 'Чужой' in content[0]['text']
    assert content[1]['image_url']['url'].startswith('data:image/png;base64,')
    assert setup.observed == ['Разбери']
    assets = response.json()['chat']['messages'][0]['attachments']
    assert len(assets) == 2
    assert setup.client.get(assets[0]['url']).content == png()
    setup.client.delete('/chats')
    assert setup.client.get(assets[0]['url']).status_code == 404
    assert list(setup.db.assets.iterdir()) == []


def test_generation_persists_png_and_uses_selected_model(setup, monkeypatch):
    async def unexpected(*args, **kwargs):
        pytest.fail('Image generation must not execute actions')
    monkeypatch.setattr(routes, 'auto_command_handler', unexpected)
    def generate(ia, question):
        assert ia.model == 'demo/vision'
        assert question == 'Нарисуй город'
        return png()
    monkeypatch.setattr(routes, 'generate', generate)
    ident = create(setup)
    response = setup.client.post(f'/chats/{ident}/messages', data={'question': 'Нарисуй город', 'mode': 'image'})
    assert response.status_code == 200
    asset = response.json()['chat']['messages'][1]['attachments'][0]
    assert setup.client.get(asset['url']).content == png()
    assert not setup.sent


@pytest.mark.parametrize('file_name, flag', [('image.png', 'images'), ('video.mp4', 'video'), ('note.txt', 'documents')])
def test_unsupported_media_rejected_before_model(setup, file_name, flag):
    setup.capabilities[flag] = False
    ident = create(setup)
    data = png() if flag == 'images' else b'example'
    response = setup.client.post(f'/chats/{ident}/messages', files={'files': (file_name, data)})
    assert response.status_code == 400
    assert not setup.sent
    assert setup.db.get(ident)['messages'] == []


def test_video_has_native_video_payload(setup):
    ident = create(setup)
    response = setup.client.post(f'/chats/{ident}/messages', files={'files': ('clip.mp4', b'video')})
    assert response.status_code == 200
    assert setup.sent[-1][-1]['content'][1]['video_url']['url'] == 'data:video/mp4;base64,dmlkZW8='


def test_model_specific_image_limit_blocks_request_before_provider(setup):
    setup.capabilities['max_images'] = 3
    ident = create(setup)
    response = setup.client.post(f'/chats/{ident}/messages',
                                 files=[('files', (f'{i}.png', png(), 'image/png')) for i in range(4)])
    assert response.status_code == 400
    assert '3' in response.json()['detail']
    assert not setup.sent
    assert setup.db.get(ident)['messages'] == []


def test_limits_failure_and_path_traversal(setup, monkeypatch):
    ident = create(setup)
    monkeypatch.setattr(routes, 'MAX_TOTAL_BYTES', 10)
    response = setup.client.post(f'/chats/{ident}/messages', files={'files': ('note.txt', b'x' * 11)})
    assert response.status_code == 413
    assert setup.client.post(f'/chats/{ident}/messages', files=[('files', (f'{i}.txt', b'x')) for i in range(5)]).status_code == 400
    assert setup.client.get('/chats/assets/not-an-asset').status_code == 404
    assert setup.client.patch(f'/chats/{ident}', json={'title': '  '}).status_code == 400
    assert setup.client.post(f'/chats/{ident}/messages', data={'mode': 'invalid', 'question': 'abc'}).status_code == 400
    assert setup.db.get(ident)['messages'] == []


def test_empty_reply_leaves_no_partial_turn_or_assets(setup, monkeypatch):
    monkeypatch.setattr(routes, 'complete', lambda *args: '')
    ident = create(setup)
    assert setup.client.post(f'/chats/{ident}/messages', files={'files': ('image.png', png())}).status_code == 400
    assert setup.db.get(ident)['messages'] == []
    assert list(setup.db.assets.iterdir()) == []


def test_provider_error_redacts_token(setup, monkeypatch):
    setup.ia.custom_keys['OpenRouter'] = 'test-secret'
    def fail(*args):
        raise RuntimeError('Authorization: test-secret')
    monkeypatch.setattr(routes, 'complete', fail)
    response = setup.client.post(f'/chats/{create(setup)}/messages', data={'question': 'Test'})
    assert response.status_code == 502
    assert 'test-secret' not in response.text


def test_health_remains_responsive_during_completion(setup, monkeypatch):
    entered, release = threading.Event(), threading.Event()
    def slow(*args):
        entered.set()
        assert release.wait(3)
        return 'Done'
    monkeypatch.setattr(routes, 'complete', slow)
    ident = create(setup)
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(setup.client.post, f'/chats/{ident}/messages', data={'question': 'Test'})
        try:
            assert entered.wait(2)
            started = time.monotonic()
            assert setup.client.get('/health').status_code == 200
            assert time.monotonic() - started < 1
        finally:
            release.set()
        assert future.result().status_code == 200


def test_openai_and_openrouter_generation_contract(setup, monkeypatch):
    encoded = base64.b64encode(png()).decode()
    calls = []
    def post(url, **kwargs):
        calls.append((url, kwargs['json']))
        return SimpleNamespace(status_code=200, raise_for_status=lambda: None, json=lambda: {'data': [{'b64_json': encoded}]})
    monkeypatch.setattr(routes.requests, 'post', post)
    assert routes.generate(setup.ia, 'City') == png()
    assert calls[0] == ('https://openrouter.ai/api/v1/images', {'model': 'demo/vision', 'prompt': 'City', 'n': 1, 'output_format': 'png'})
    def openai_image(**kwargs):
        assert kwargs['model'] == 'demo/vision'
        return SimpleNamespace(data=[SimpleNamespace(b64_json=encoded)])
    setup.ia.api_provider = 'OpenAI'
    setup.ia.client = SimpleNamespace(images=SimpleNamespace(generate=openai_image))
    assert routes.generate(setup.ia, 'City') == png()


def test_capabilities_come_from_modalities_and_unknown_is_honest():
    vision = caps.capabilities('OpenRouter', 'x', {'input_modalities': ['text', 'image', 'video'], 'output_modalities': ['text', 'image']})
    assert all(vision[key] for key in ['images', 'video', 'documents', 'image_generation'])
    text = caps.capabilities('OpenRouter', 'y', {'modality': 'text->text'})
    assert text['known'] and not text['images'] and not text['image_generation']
    unknown = caps.capabilities('OpenRouter', 'missing-model')
    assert not unknown['known'] and not unknown['images'] and not unknown['video']
    assert caps.capabilities('OpenAI', 'gpt-image-1')['image_generation']
    assert not caps.capabilities('DeepSeek', 'deepseek-chat')['images']
    assert caps.capabilities('Groq', 'qwen/qwen3.8-27b')['images']
    assert caps.capabilities('Groq', 'qwen/qwen3.8-27b')['max_images'] == 3
    assert not caps.capabilities('Groq', 'unconfirmed-model')['known']


def test_legacy_import_is_once_and_does_not_resurrect_deleted_chat(tmp_path):
    from backend.conversation_archive import ConversationArchive
    archive = ConversationArchive(tmp_path / 'archive.sqlite3')
    archive.add('Old user', 'Old answer', '2026-10-06T10:00:00')
    database = ChatStore(tmp_path / 'chats')
    database.import_legacy(archive.path)
    database.import_legacy(archive.path)
    assert len(database.list()) == 1
    assert len(database.get(database.list()[0]['id'])['messages']) == 2
    database.delete()
    database.import_legacy(archive.path)
    assert database.list() == []


def test_completed_chats_use_long_term_memory_and_deletion_removes_vectors(setup, tmp_path):
    from backend.intelligent_answerer import ConversationMemory
    setup.ia.memory = ConversationMemory(context_file=tmp_path / 'recent.jsonl')
    ident = create(setup)
    setup.client.post(f'/chats/{ident}/messages', data={'question': 'Стек проекта PostgreSQL'})
    archive = setup.ia.memory.archive
    assert archive.count() == 1
    assert archive.recall('PostgreSQL')
    with archive.connection() as db:
        turn_id = db.execute('SELECT id FROM turns').fetchone()[0]
        db.execute('INSERT INTO semantic_turns VALUES(?,?)', (turn_id, 'test-model'))
    setup.client.delete(f'/chats/{ident}')
    assert archive.count() == 0
    assert archive.recall('PostgreSQL') == []
    with archive.connection() as db:
        assert db.execute('SELECT COUNT(*) FROM semantic_turns').fetchone()[0] == 0
        assert db.execute('SELECT COUNT(*) FROM chat_sources').fetchone()[0] == 0


def test_clear_history_failure_keeps_recall_and_chat(setup, tmp_path, monkeypatch):
    from backend.intelligent_answerer import ConversationMemory
    setup.ia.memory = ConversationMemory(context_file=tmp_path / 'recent.jsonl')
    ident = create(setup)
    setup.client.post(f'/chats/{ident}/messages', data={'question': 'Проект PostgreSQL'})
    def fail(*args):
        raise OSError('Disk locked')
    monkeypatch.setattr(routes, 'atomic_write_text', fail)
    with pytest.raises(OSError):
        setup.client.delete(f'/chats/{ident}')
    assert setup.ia.memory.archive.count() == 1
    assert len(setup.db.get(ident)['messages']) == 2


def test_command_uses_existing_executor_without_model_or_attachments(setup, monkeypatch):
    calls = []
    async def command(text, quiet_mode):
        calls.append((text, quiet_mode))
        return {'response': 'Готово'}
    monkeypatch.setattr(routes, 'command_handler', command)
    ident = create(setup)
    setup.ia.enabled = False
    result = setup.client.post(f'/chats/{ident}/messages', data={'question': 'Команда', 'mode': 'command'})
    assert result.status_code == 200
    assert calls == [('Команда', True)]
    assert len(setup.db.get(ident)['messages']) == 2
    assert not setup.sent
    assert setup.client.post(f'/chats/{ident}/messages', data={'question': 'Команда', 'mode': 'command'}, files={'files': ('note.txt', b'text')}).status_code == 400
    assert len(calls) == 1


def test_invalid_image_is_refused_before_api(setup):
    ident = create(setup)
    response = setup.client.post(f'/chats/{ident}/messages', files={'files': ('invalid.png', b'not-png')})
    assert response.status_code == 400
    assert not setup.sent


def test_followup_preserves_photo_and_large_text_context(setup):
    ident = create(setup)
    setup.client.post(f'/chats/{ident}/messages', data={'question': 'Что на фото?'}, files={'files': ('image.png', png())})
    setup.client.post(f'/chats/{ident}/messages', data={'question': 'Что видно на заднем плане?'})
    assert setup.sent[-1][0]['content'][1]['image_url']['url'].startswith('data:image/png;base64,')
    setup.capabilities['images'] = False
    setup.client.post(f'/chats/{ident}/messages', data={'question': 'Опиши вывод словами'})
    assert all(isinstance(row['content'], str) for row in setup.sent[-1])
    other = create(setup)
    setup.db.commit_turn(other, 'Large document', 'a' * 30000, 'b' * 10000, 'demo', [])
    assert len(setup.db.context(other)) == 2


def test_bmp_is_converted_to_supported_image_format(setup):
    image = io.BytesIO()
    Image.new('RGB', (16, 12), 'blue').save(image, 'BMP')
    response = setup.client.post(f'/chats/{create(setup)}/messages', files={'files': ('image.bmp', image.getvalue())})
    assert response.status_code == 200
    assert setup.sent[-1][-1]['content'][1]['image_url']['url'].startswith('data:image/png;base64,')
