"""Bounded text-only streams. No tool execution or replay after partial output."""
import json
import threading
import time
import requests
try:
    from .model_requests import openai_options, anthropic_options, deepseek_options
    from . import request_flow
except ImportError:
    from model_requests import openai_options, anthropic_options, deepseek_options
    import request_flow

_sessions = threading.local()
MAX_EVENT = 256 * 1024
MAX_TEXT = 128 * 1024

def session():
    if not hasattr(_sessions, 'value'):
        _sessions.value = requests.Session()
    return _sessions.value

def events(response):
    """SSE comments/multiline data/UTF-8; require an explicit terminal event."""
    data = []
    size = 0
    # One byte avoids Requests buffering a short first sentence until 512 B.
    # Bodies are bounded; JSON is parsed only at complete event boundaries.
    for line in response.iter_lines(chunk_size=1):
        request_flow.current().check()
        size += len(line)
        if size > MAX_EVENT:
            raise ValueError('Слишком большое событие модели.')
        if not line:
            if data:
                yield b'\n'.join(data).decode('utf-8')
            data, size = [], 0
        elif line.startswith(b'data:'):
            data.append(line[5:].lstrip(b' '))
    if data:
        raise ValueError('Поток модели оборвался внутри события.')

class Text:
    def __init__(self):
        self.parts = []
        self.size = 0
        self.finished = False

    def add(self, text):
        if not text:
            return
        if not isinstance(text, str):
            raise ValueError('Некорректный текст модели.')
        self.size += len(text)
        if self.size > MAX_TEXT:
            raise ValueError('Ответ модели слишком большой.')
        self.parts.append(text)
        request_flow.current().emit(text)

    def result(self):
        request_flow.current().check()
        answer = ''.join(self.parts).strip()
        if not self.finished or not answer:
            raise ValueError('Модель не завершила текстовый ответ.')
        return answer

def openai_event(value, text):
    if value.get('error'):
        raise ValueError('Провайдер прервал ответ.')
    for choice in value.get('choices', []):
        if choice.get('index', 0) != 0:
            continue
        delta = choice.get('delta') or {}
        if delta.get('tool_calls') or delta.get('function_call'):
            raise ValueError('Модель вернула вызов инструмента вместо ответа.')
        text.add(delta.get('content'))
        reason = choice.get('finish_reason')
        if reason is not None:
            if reason not in ('stop', 'length'):
                raise ValueError('Модель не завершила текстовый ответ.')
            text.finished = True

def _anthropic_messages(messages):
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
    return converted

def complete(ia, messages, instructions, tokens=None, temperature=None):
    """Use the configured provider and model, without hidden model substitution."""
    flow = request_flow.current()
    flow.check()
    tokens = ia.max_tokens if tokens is None else tokens
    text = Text()
    provider = ia.api_provider
    system = [dict(role='system', content=instructions)] + messages
    if provider in ('OpenAI', 'Groq'):
        options = openai_options(ia.model, tokens, temperature) if provider == 'OpenAI' else dict(max_tokens=tokens)
        if provider == 'Groq' and temperature is not None:
            options['temperature'] = temperature
        client = ia.client
        if callable(getattr(client, 'with_options', None)):
            client = client.with_options(max_retries=0)
        stream = client.chat.completions.create(model=ia.model, messages=system, stream=True,
                                                 timeout=min(90, max(.1, flow.deadline - time.monotonic())), **options)
        try:
            for chunk in stream:
                flow.check()
                openai_event(chunk.model_dump(), text)
                if text.finished:
                    break
        finally:
            stream.close()
        return text.result()

    base = ia.client['base_url'].rstrip('/')
    if provider == 'Anthropic':
        url = base + '/messages'
        payload = dict(model=ia.model, system=instructions, messages=_anthropic_messages(messages), stream=True,
                       **anthropic_options(ia.model, tokens, temperature))
        headers = {'x-api-key':ia.client['api_key'], 'anthropic-version':'2023-06-01'}
    else:
        url = base + '/chat/completions'
        options = deepseek_options(ia.model, tokens, temperature) if provider == 'DeepSeek' else dict(max_tokens=tokens)
        if provider != 'DeepSeek' and temperature is not None:
            options['temperature'] = temperature
        payload = dict(model=ia.model, messages=system, stream=True, **options)
        headers = {'Authorization':'Bearer ' + ia.client['api_key']}
    ring = getattr(ia, 'openrouter_ring', None) if provider == 'OpenRouter' else None
    attempts = max(1, len(ring)) if ring is not None else 1
    for attempt in range(attempts):
        flow.check()
        if ring is not None:
            headers['Authorization'] = 'Bearer ' + (ring.current() or ia.client['api_key'])
        response = session().post(url, headers=headers, json=payload, stream=True,
                                  timeout=(10, 30), allow_redirects=False)
        try:
            if response.status_code >= 400 and ring is not None and attempt + 1 < attempts:
                # Only a refused request may rotate a key. Never replay audio/text.
                try:
                    from . import key_ring as keys
                except ImportError:
                    import key_ring as keys
                reason = keys.why_refused(str(response.status_code))
                if reason and ring.set_aside(headers['Authorization'][7:], reason):
                    continue
            response.raise_for_status()
            if response.status_code != 200:
                raise ValueError('Провайдер вернул неожиданный ответ.')
            for data in events(response):
                if data == '[DONE]':
                    break
                value = json.loads(data)
                if not isinstance(value, dict) or value.get('error') or value.get('type') == 'error':
                    raise ValueError('Провайдер прервал ответ.')
                if provider == 'Anthropic':
                    kind = value.get('type')
                    if kind == 'content_block_start':
                        block = value.get('content_block', {})
                        if block.get('type') == 'tool_use':
                            raise ValueError('Модель вернула вызов инструмента вместо ответа.')
                        if block.get('type') == 'text':
                            text.add(block.get('text'))
                    if kind == 'content_block_delta' and value.get('delta', {}).get('type') == 'text_delta':
                        text.add(value['delta'].get('text'))
                    elif kind == 'message_stop':
                        text.finished = True
                        break
                else:
                    openai_event(value, text)
            return text.result()
        finally:
            response.close()
            session().cookies.clear()
    raise ValueError('Провайдер не ответил.')
