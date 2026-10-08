"""Named chat API; parsing, persistence and model requests run on workers."""
import asyncio
import base64
import io
import threading
import json
from pathlib import Path
from functools import lru_cache
from typing import Optional, List

import requests
from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from PIL import Image
from pydantic import BaseModel, Field

try:
    from .chat_store import ChatStore
    from . import attachments, model_capabilities
    from .storage import atomic_write_text
    from .intelligent_answerer import get_intelligent_answerer, explain_connect_error, raise_with_body
except ImportError:
    from chat_store import ChatStore
    import attachments, model_capabilities
    from storage import atomic_write_text
    from intelligent_answerer import get_intelligent_answerer, explain_connect_error, raise_with_body

router = APIRouter(prefix='/chats', tags=['chats'])
_operations = threading.RLock()
_busy_chats = set()
command_handler = None
MAX_FILES = 4
MAX_TOTAL_BYTES = attachments.MAX_BYTES
VIDEO_TYPES = {'.mp4': 'video/mp4', '.mpeg': 'video/mpeg', '.mov': 'video/mov', '.webm': 'video/webm'}


@lru_cache(maxsize=1)
def store():
    return ChatStore()


def operation(function, *args, **kwargs):
    with _operations:
        try:
            return function(*args, **kwargs)
        except KeyError as error:
            raise HTTPException(404, str(error.args[0])) from error
        except ValueError as error:
            raise HTTPException(400, str(error)) from error


def delete_saved(chat_id=None, clear=False):
    if (chat_id and chat_id in _busy_chats) or (not chat_id and _busy_chats):
        raise HTTPException(409, 'Дождитесь завершения действия')
    ia = get_intelligent_answerer()
    memory = getattr(ia, 'memory', None)
    archive = getattr(memory, 'archive', None)
    if chat_id:
        store().get(chat_id)
    if callable(getattr(archive, 'delete_chats', None)):
        with ia._state_lock(), memory._lock:
            candidate = list(memory.conversations)
            def clear_recent(pairs):
                nonlocal candidate
                candidate = []
                for index in range(0, len(memory.conversations), 2):
                    pair = memory.conversations[index:index + 2]
                    if len(pair) == 2 and (pair[0]['content'], pair[1]['content']) in pairs:
                        continue
                    candidate.extend(pair)
                atomic_write_text(memory.context_file, ''.join(json.dumps(row, ensure_ascii=False) + '\n' for row in candidate))
            archive.delete_chats([chat_id] if chat_id else None, clear_recent)
            memory.conversations = candidate
    store().delete(chat_id, clear=clear)


def remember(ia, chat, question, answer, notes, existing=False):
    archive = getattr(getattr(ia, 'memory', None), 'archive', None)
    if callable(getattr(archive, 'remember_chat', None)):
        try:
            archive.remember_chat(question, answer, chat['messages'][-2]['created'], chat['id'], existing=existing)
        except Exception:
            notes.append('Диалог сохранён, но пока недоступен для поиска в памяти.')


class Rename(BaseModel):
    title: str = Field(min_length=1, max_length=100)


@router.get('')
async def list_chats():
    def work():
        with _operations:
            ia = get_intelligent_answerer()
            archive = getattr(getattr(ia, 'memory', None), 'archive', None)
            imported = operation(store().import_legacy, getattr(archive, 'path', None))
            if imported and callable(getattr(archive, 'bind_chat', None)):
                archive.bind_chat(*imported)
                store().mark_legacy_bound()
            return operation(store().list)
    return {'success': True, 'chats': await asyncio.to_thread(work)}


@router.post('')
async def create_chat():
    def work():
        return operation(store().create)
    return {'success': True, 'chat': await asyncio.to_thread(work)}


@router.get('/capabilities')
async def current_capabilities():
    def read():
        ia = get_intelligent_answerer()
        if not ia:
            return {'success': False, 'error': 'ИИ не настроен'}
        provider, model, enabled = ia.api_provider, ia.model, ia.enabled
        caps = model_capabilities.capabilities(provider, model, refresh=True)
        return dict(success=True, provider=provider, model=model, enabled=enabled, capabilities=caps,
                    max_files=MAX_FILES, max_bytes=MAX_TOTAL_BYTES)
    return await asyncio.to_thread(read)


@router.get('/assets/{asset_id}')
async def get_asset(asset_id: str):
    def work():
        return operation(store().asset, asset_id)
    path, mime = await asyncio.to_thread(work)
    return FileResponse(path, media_type=mime, headers={'X-Content-Type-Options': 'nosniff'})


@router.delete('')
async def delete_history():
    def work():
        return operation(delete_saved)
    await asyncio.to_thread(work)
    return {'success': True}


@router.get('/{chat_id}')
async def get_chat(chat_id: str):
    def work():
        return operation(store().get, chat_id)
    return {'success': True, 'chat': await asyncio.to_thread(work)}


@router.patch('/{chat_id}')
async def rename_chat(chat_id: str, body: Rename):
    def work():
        return operation(store().rename, chat_id, body.title)
    return {'success': True, 'chat': await asyncio.to_thread(work)}


@router.delete('/{chat_id}')
async def delete_chat(chat_id: str):
    def work():
        return operation(delete_saved, chat_id)
    await asyncio.to_thread(work)
    return {'success': True}


@router.delete('/{chat_id}/messages')
async def clear_chat(chat_id: str):
    def work():
        operation(delete_saved, chat_id, clear=True)
        return operation(store().get, chat_id)
    return {'success': True, 'chat': await asyncio.to_thread(work)}


def complete(ia, messages, instructions):
    try:
        from .model_requests import openai_options, anthropic_options, deepseek_options
    except ImportError:
        from model_requests import openai_options, anthropic_options, deepseek_options
    if ia.api_provider == 'OpenRouter':
        return ia._ask_openrouter(dict(model=ia.model, messages=[dict(role='system', content=instructions)] + messages,
                                      max_tokens=ia.max_tokens))
    if ia.api_provider == 'Anthropic':
        converted = []
        for message in messages:
            content = message['content']
            if isinstance(content, list):
                blocks = []
                for part in content:
                    if part['type'] == 'text':
                        blocks.append(part)
                    elif part['type'] == 'image_url':
                        header, encoded = part['image_url']['url'].split(',', 1)
                        blocks.append(dict(type='image', source=dict(type='base64', media_type=header[5:].split(';')[0], data=encoded)))
                content = blocks
            converted.append(dict(role=message['role'], content=content))
        response = requests.post(ia.client['base_url'] + '/messages',
                                 headers={'x-api-key': ia.client['api_key'], 'anthropic-version': '2023-06-01'},
                                 json=dict(model=ia.model, system=instructions, messages=converted,
                                           **anthropic_options(ia.model, ia.max_tokens)), timeout=90)
        raise_with_body(response)
        return ''.join(p.get('text', '') for p in response.json().get('content', []) if p.get('type') == 'text').strip()
    messages = [dict(role='system', content=instructions)] + messages
    if ia.api_provider == 'DeepSeek':
        response = requests.post(ia.client['base_url'] + '/chat/completions',
                                 headers={'Authorization': 'Bearer ' + ia.client['api_key']},
                                 json=dict(model=ia.model, messages=messages,
                                           **deepseek_options(ia.model, ia.max_tokens)), timeout=90)
        raise_with_body(response)
        return response.json()['choices'][0]['message']['content'].strip()
    options = openai_options(ia.model, ia.max_tokens) if ia.api_provider == 'OpenAI' else dict(max_tokens=ia.max_tokens)
    response = ia.client.chat.completions.create(model=ia.model, messages=messages, timeout=90, **options)
    return (response.choices[0].message.content or '').strip()


def generate(ia, question):
    if ia.api_provider == 'OpenAI':
        response = ia.client.images.generate(model=ia.model, prompt=question, n=1, timeout=180)
        encoded = response.data[0].b64_json
    else:
        response = requests.post(ia.client['base_url'] + '/images',
                                 headers={'Authorization': 'Bearer ' + ia.client['api_key']},
                                 json=dict(model=ia.model, prompt=question, n=1, output_format='png'), timeout=180)
        raise_with_body(response)
        encoded = response.json()['data'][0]['b64_json']
    if not encoded or len(encoded) > MAX_TOTAL_BYTES * 4 // 3 + 8:
        raise ValueError('Модель вернула пустое или слишком большое изображение')
    data = base64.b64decode(encoded, validate=True)
    with Image.open(io.BytesIO(data)) as image:
        if image.width * image.height > 32_000_000:
            raise ValueError('Слишком большое разрешение изображения')
        image.load()
        output = io.BytesIO()
        image.save(output, format='PNG')
    data = output.getvalue()
    if len(data) > MAX_TOTAL_BYTES:
        raise ValueError('Слишком большое изображение от модели')
    return data


def send(chat_id, question, mode, files):
    if chat_id in _busy_chats:
        raise HTTPException(409, 'В этом диалоге ещё выполняется действие')
    database = store()
    snapshot = database.get(chat_id)
    ia = get_intelligent_answerer()
    if not ia or not ia.enabled:
        raise ValueError('Выберите и настройте модель на вкладке «Модели»')
    with ia._state_lock():
        caps = model_capabilities.capabilities(ia.api_provider, ia.model, refresh=True)
        media, notes, text_parts, content = [], [], [], []
        if mode == 'image':
            if not caps['image_generation'] or ia.api_provider not in {'OpenAI', 'OpenRouter'}:
                raise ValueError('Выбранная модель не поддерживает генерацию изображений')
            if files:
                raise ValueError('Для генерации сейчас нужен текст без вложений')
            if not question:
                raise ValueError('Опишите изображение, которое нужно создать')
            media = [('assistant', 'Scott-image.png', 'image/png', generate(ia, question))]
            answer, saved_content = 'Изображение готово.', question
        else:
            if not caps['text']:
                raise ValueError('Эта модель создаёт изображения. Выберите режим «Картинка» или разговорную модель')
            for name, data in files:
                suffix = Path(name).suffix.lower()
                if suffix in VIDEO_TYPES:
                    if not caps['video'] or ia.api_provider != 'OpenRouter':
                        raise ValueError('Выбранная модель не анализирует видео')
                    content.append(dict(type='video_url', video_url=dict(url='data:' + VIDEO_TYPES[suffix] + ';base64,' + base64.b64encode(data).decode('ascii'))))
                    mime = VIDEO_TYPES[suffix]
                else:
                    if suffix in attachments.IMAGE_TYPES:
                        try:
                            with Image.open(io.BytesIO(data)) as image:
                                if image.width * image.height > 32_000_000:
                                    raise ValueError('Слишком большое разрешение изображения')
                                image.verify()
                        except Exception as error:
                            raise ValueError('Не удалось прочитать изображение: файл повреждён или слишком большой') from error
                    attachment = attachments.read(name, data)
                    if not attachment.ok:
                        raise ValueError(attachment.error)
                    if attachment.kind == 'image':
                        if not caps['images']:
                            raise ValueError('Поддержка изображений для этой модели не подтверждена. Выберите модель со значком «Фото»')
                        content.append(dict(type='image_url', image_url=dict(url='data:' + attachment.media_type + ';base64,' + attachment.image_base64)))
                        mime, data = attachment.media_type, base64.b64decode(attachment.image_base64)
                    else:
                        if not caps['documents']:
                            raise ValueError('Выбранная модель не анализирует текст документов')
                        text_parts.append(attachments.as_question(attachment, ''))
                        mime = 'application/octet-stream'
                    if attachment.note:
                        notes.append(name + ': ' + attachment.note)
                media.append(('user', name, mime, data))
            question = question or ('Проанализируй вложения и кратко объясни содержимое.' if files else '')
            if not question:
                raise ValueError('Введите сообщение или прикрепите файл')
            prompt = question + ('\n\n' + '\n\n'.join(text_parts) if text_parts else '')
            if len(prompt) > 30000:
                raise ValueError('Слишком много текста во вложениях. Отправьте документы по отдельности')
            saved_content = prompt + ''.join('\n[Вложение: ' + name + ']' for name, _ in files)
            content = [dict(type='text', text=prompt)] + content if content else prompt
            has_new_image = isinstance(content, list) and any(part['type'] == 'image_url' for part in content)
            image_count = sum(part['type'] == 'image_url' for part in content) if isinstance(content, list) else 0
            if image_count > caps.get('max_images', MAX_FILES):
                raise ValueError(f"Эта модель принимает до {caps['max_images']} изображений за один запрос")
            history = database.context(chat_id, images=caps['images'] and not has_new_image)
            archive = getattr(getattr(ia, 'memory', None), 'archive', None)
            recalled = []
            if callable(getattr(archive, 'recall', None)):
                recent = snapshot['messages'][-20:]
                excluded = [(u['text'], a['text']) for u, a in zip(recent[::2], recent[1::2])]
                try:
                    recalled = archive.recall(question, excluded)
                except Exception:
                    pass
            answer = complete(ia, recalled + history + [dict(role='user', content=content)], ia.instructions(query=question))
            if not answer:
                raise ValueError('Модель вернула пустой ответ. Попробуйте ещё раз')
        chat = database.commit_turn(chat_id, question, saved_content, answer, ia.api_provider + ' · ' + ia.model, media)
        remember(ia, chat, question, answer, notes)
        try:
            from . import memories
        except ImportError:
            import memories
        try:
            memories.observe(question)
        except Exception:
            pass  # A fact-storage failure must not duplicate a committed chat turn.
        return dict(success=True, chat=chat, notes=notes)


@router.post('/{chat_id}/messages')
async def send_message(chat_id: str, question: str = Form(''), mode: str = Form('chat'),
                       files: Optional[List[UploadFile]] = File(None)):
    if len(question) > 12000 or mode not in {'chat', 'image', 'command'}:
        raise HTTPException(400, 'Проверьте сообщение и режим отправки')
    files = files or []
    payload, total = [], 0
    try:
        if len(files) > MAX_FILES:
            raise HTTPException(400, 'Можно прикрепить до четырёх файлов')
        for upload in files:
            data = await upload.read(MAX_TOTAL_BYTES - total + 1)
            total += len(data)
            if total > MAX_TOTAL_BYTES:
                raise HTTPException(413, 'Общий размер вложений: не более 20 МБ')
            payload.append((Path(upload.filename or 'файл').name, data))
    finally:
        for upload in files:
            await upload.close()
    if mode == 'command':
        if not question.strip() or files:
            raise HTTPException(400, 'Для действия нужен текст без вложений')
        if command_handler is None:
            raise HTTPException(503, 'Исполнитель команд недоступен')
        def reserve():
            store().get(chat_id)
            if chat_id in _busy_chats:
                raise HTTPException(409, 'Дождитесь завершения предыдущего действия')
            _busy_chats.add(chat_id)
        await asyncio.to_thread(operation, reserve)
        try:
            result = await command_handler(question.strip(), quiet_mode=True)
            answer = result.get('response', '')
            if not answer:
                raise HTTPException(502, 'Команда не вернула ответ')
            def commit():
                chat = store().commit_turn(chat_id, question.strip(), question.strip(), answer, 'Scott · действие', [])
                ia = get_intelligent_answerer()
                if ia:
                    remember(ia, chat, question.strip(), answer, [], True)
                return chat
            chat = await asyncio.to_thread(operation, commit)
            return dict(success=True, chat=chat, notes=[])
        finally:
            with _operations:
                _busy_chats.discard(chat_id)
    def work():
        try:
            return operation(send, chat_id, question.strip(), mode, payload)
        except HTTPException:
            raise
        except Exception as error:
            ia = get_intelligent_answerer()
            reason = explain_connect_error(ia.api_provider if ia else '', ia.model if ia else '', str(error))
            keys = list(getattr(ia, 'custom_keys', {}).values()) + list(getattr(ia, 'env_keys', {}).values())
            keys += list(getattr(getattr(ia, 'openrouter_ring', None), 'all', []))
            keys.append(ia.client.get('api_key') if isinstance(getattr(ia, 'client', None), dict) else getattr(getattr(ia, 'client', None), 'api_key', None))
            for key in keys:
                if isinstance(key, str) and key:
                    reason = reason.replace(key, '[скрыто]')
            raise HTTPException(502, reason) from error
    return await asyncio.to_thread(work)
