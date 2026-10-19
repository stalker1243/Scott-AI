"""HTTP/WebSocket access checks and bounded request ingestion for the desktop API."""
from __future__ import annotations

import asyncio
import ipaddress
import re
import tempfile
import traceback
import uuid
from urllib.parse import urlsplit

from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException
from starlette.responses import JSONResponse

from support_logs import append_log, redact

MAX_BODY_BYTES = 32 * 1024 * 1024
MAX_WS_BYTES = 64 * 1024
TECHNICAL_DETAILS = frozenset({'Not Found', 'Method Not Allowed', 'Unauthorized', 'Forbidden',
                               'Too many requests', 'IP not allowed', 'Missing Authorization header',
                               'Invalid or missing token'})
MESSAGES = {
    400: ('Некорректный запрос.', 'Проверьте введённые данные и повторите запрос.'),
    401: ('Требуется авторизация.', 'Проверьте настройки доступа к backend.'),
    403: ('Доступ к backend запрещён.', 'Откройте ScottAI напрямую и проверьте настройки доступа.'),
    404: ('Запрошенный раздел не найден.', 'Обновите данные. Если ошибка повторится, откройте «Логи».'),
    405: ('Этот способ обращения не поддерживается.', 'Проверьте, что лаунчер и backend обновлены вместе.'),
    408: ('Передача запроса заняла слишком много времени.', 'Проверьте соединение и отправьте запрос ещё раз.'),
    413: ('Запрос слишком большой.', 'Уменьшите вложения: до 20 МБ суммарно для одного сообщения.'),
    422: ('Не удалось проверить данные запроса.', 'Проверьте заполнение полей и формат вложений.'),
    429: ('Слишком много одновременных запросов.', 'Дождитесь завершения текущей операции и повторите запрос.'),
    500: ('Не удалось завершить операцию.', 'Проверьте историю перед повтором. Сохраните архив во вкладке «Логи».'),
    503: ('Backend временно занят.', 'Дождитесь завершения текущей операции и повторите запрос.'),
    504: ('Ответ занял слишком много времени.', 'Проверьте историю перед повторной отправкой. Операция могла завершиться позднее.'),
}


def error_response(status, scope, detail=None, headers=None):
    message, hint = MESSAGES.get(status, MESSAGES[500 if status >= 500 else 400])
    # Preserve intentional endpoint messages, never validation inputs or exception text.
    if status < 500 and isinstance(detail, str) and detail and detail not in TECHNICAL_DETAILS:
        message = redact(detail[:2048])
    state = scope.setdefault('state', {})
    request_id = state.setdefault('request_id', uuid.uuid4().hex[:12])
    return JSONResponse(status_code=status, headers=headers, content={
        'success': False, 'message': message, 'hint': hint, 'data': None,
        'code': f'SCOTT-API-{status}', 'request_id': request_id,
    })


def install_error_handlers(app):
    async def http_error(request, exc):
        if exc.status_code >= 500:
            request_id = request.scope.setdefault('state', {}).setdefault('request_id', uuid.uuid4().hex[:12])
            append_log('api-errors.log', f'{request_id} HTTPException {exc.status_code}')
        return error_response(exc.status_code, request.scope, exc.detail, exc.headers)

    async def invalid_request(request, exc):
        # Pydantic's default response can include the submitted API Token in "input".
        return error_response(422, request.scope)

    app.add_exception_handler(HTTPException, http_error)
    app.add_exception_handler(RequestValidationError, invalid_request)


def _loopback(host):
    if host == 'localhost':
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def _host(value):
    if not value or len(value) > 255 or re.search(r'[\s/@\\?#]', value):
        return None
    try:
        parsed = urlsplit('//'+value)
        if parsed.port is not None and not 1 <= parsed.port <= 65535:
            return None
        return parsed.hostname
    except ValueError:
        return None


class ApiBoundary:
    def __init__(self, app, *, allowed_origins, remote_paths, device_lookup,
                 max_body_bytes=MAX_BODY_BYTES, body_timeout=30):
        self.app = app
        self.allowed_origins = frozenset(allowed_origins)
        self.remote_paths = frozenset(remote_paths)
        self.device_lookup = device_lookup
        self.max_body_bytes = max_body_bytes
        self.body_timeout = body_timeout
        self.uploads = asyncio.Semaphore(4)

    async def __call__(self, scope, receive, send):
        if scope['type'] not in ('http', 'websocket'):
            return await self.app(scope, receive, send)
        state = scope.setdefault('state', {})
        # Never trust an inbound request identifier or forwarded client address.
        state['request_id'] = uuid.uuid4().hex[:12]
        started = False

        async def safe_send(message):
            nonlocal started
            if message['type'] == 'http.response.start':
                started = True
                headers = [(k, v) for k, v in message.get('headers', [])
                           if k.lower() not in (b'x-request-id', b'cache-control', b'x-content-type-options')]
                headers.extend([(b'x-request-id', state['request_id'].encode()),
                                (b'cache-control', b'no-store'), (b'x-content-type-options', b'nosniff')])
                message = dict(message, headers=headers)
            await send(message)

        async def reject(status):
            if scope['type'] == 'websocket':
                await send({'type': 'websocket.close', 'code': 1008})
            else:
                response = error_response(status, scope, headers={'Retry-After': '2'} if status == 429 else None)
                await response(scope, receive, safe_send)

        headers = {}
        for key, value in scope.get('headers', []):
            key = key.lower()
            if key in headers and key in (b'host', b'origin', b'content-length', b'x-scott-device', b'sec-fetch-site'):
                return await reject(400)
            headers[key] = value.decode('latin-1')
        peer = (scope.get('client') or ('', 0))[0]
        host = _host(headers.get(b'host', ''))
        if not host or (_loopback(peer) and not _loopback(host)):
            return await reject(403)
        origin = headers.get(b'origin')
        if origin is not None and origin not in self.allowed_origins:
            return await reject(403)
        if origin is None and headers.get(b'sec-fetch-site', '').lower() == 'cross-site':
            return await reject(403)
        if not _loopback(peer):
            if scope['type'] == 'websocket' or scope.get('path') not in self.remote_paths:
                return await reject(404)
            token = headers.get(b'x-scott-device', '')
            try:
                device = self.device_lookup(token) if token and len(token) <= 2048 else None
            except (ValueError, TypeError, OSError):
                device = None
            except Exception as exc:
                append_log('api-errors.log', f'{state["request_id"]} device_lookup {type(exc).__name__}')
                return await reject(503)
            if device is None:
                return await reject(403)
            state['device'] = device

        async def bounded_ws_receive():
            message = await receive()
            if message['type'] == 'websocket.receive':
                size = len(message.get('bytes') or b'') + len((message.get('text') or '').encode('utf-8'))
                if size > MAX_WS_BYTES:
                    await send({'type': 'websocket.close', 'code': 1009})
                    return {'type': 'websocket.disconnect', 'code': 1009}
            return message

        try:
            if scope['type'] == 'websocket':
                return await self.app(scope, bounded_ws_receive, safe_send)
            length = headers.get(b'content-length')
            if length is not None and (not length.isascii() or not length.isdecimal() or len(length) > 12):
                return await reject(400)
            if length is not None and int(length) > self.max_body_bytes:
                return await reject(413)
            if scope.get('method') in ('GET', 'HEAD', 'OPTIONS') and length in (None, '0') and b'transfer-encoding' not in headers:
                return await self.app(scope, receive, safe_send)
            # Buffer before dispatch: an incomplete/oversized body must not execute
            # an action, even if a route ignores part of its request stream.
            if self.uploads.locked():
                return await reject(429)
            with tempfile.SpooledTemporaryFile(max_size=1024 * 1024) as body:
                await self.uploads.acquire()
                try:
                    total = 0
                    async def ingest():
                        nonlocal total
                        while True:
                            message = await receive()
                            if message['type'] == 'http.disconnect':
                                return False
                            chunk = message.get('body', b'')
                            total += len(chunk)
                            if total > self.max_body_bytes:
                                return None
                            body.write(chunk)
                            if not message.get('more_body', False):
                                return True
                    try:
                        complete = await asyncio.wait_for(ingest(), self.body_timeout)
                    except TimeoutError:
                        return await reject(408)
                    if complete is False:
                        return
                    if complete is None:
                        return await reject(413)
                    if length is not None and int(length) != total:
                        return await reject(400)
                finally:
                    self.uploads.release()
                body.seek(0)
                remaining = total
                delivered_end = False
                async def replay():
                    nonlocal remaining, delivered_end
                    if not delivered_end:
                        chunk = body.read(min(65536, remaining)); remaining -= len(chunk)
                        delivered_end = remaining == 0
                        return {'type': 'http.request', 'body': chunk, 'more_body': not delivered_end}
                    # Downstream may watch disconnects while streaming a reply.
                    return await receive()
                await self.app(scope, replay, safe_send)
        except Exception as exc:
            frames = [f'{frame.name}:{frame.lineno}' for frame in traceback.extract_tb(exc.__traceback__)[-8:]]
            append_log('api-errors.log', f'{state["request_id"]} {type(exc).__name__} {" > ".join(frames)}')
            if scope['type'] == 'websocket':
                await send({'type': 'websocket.close', 'code': 1011})
            elif not started:
                await error_response(500, scope)(scope, receive, safe_send)
            else:
                # A partial response cannot be replaced by a new JSON response.
                # End it without exposing the exception to Uvicorn's raw logger.
                try:
                    await send({'type': 'http.response.body', 'body': b'', 'more_body': False})
                except (RuntimeError, OSError):
                    pass
