"""Application-agnostic window actions and explicit accessibility invocation."""
import json
import os
from pathlib import Path
import re
import subprocess
import sys

OPERATIONS = {'list', 'close_all', 'minimize_all', 'focus', 'close', 'close_app', 'minimize',
              'maximize', 'restore', 'controls', 'invoke', 'list_apps', 'refresh_apps'}


def environment():
    return {key:value for key,value in os.environ.items() if not key.upper().endswith(
        ('_API_KEY', '_TOKEN', '_SECRET', '_ACCESS_KEY', '_SECRET_ACCESS_KEY'))}


def own_pids():
    result = {os.getpid(), os.getppid()}
    try:
        import psutil
        result.update(parent.pid for parent in psutil.Process().parents())
    except Exception:
        pass
    return sorted(result)[:64]


def _worker(spec):
    options = {'creationflags': subprocess.CREATE_NO_WINDOW} if os.name == 'nt' else {}
    try:
        result = subprocess.run([sys.executable, '-I', '-S', str(Path(__file__).with_name('desktop_worker.py'))],
            input=json.dumps(spec).encode('utf-8'), capture_output=True, timeout=8,
            env=environment(), **options)
        if len(result.stdout) > 1048576:
            raise ValueError('Слишком большой ответ управления окнами.')
        value = json.loads(result.stdout.decode('utf-8-sig'))
        if not isinstance(value, dict) or not isinstance(value.get('success'), bool):
            raise ValueError('Некорректный ответ управления окнами.')
        return value
    except subprocess.TimeoutExpired:
        return dict(success=False, code='timeout', message='Оконная система не ответила вовремя. Не удалось подтвердить действие.')
    except (OSError, ValueError):
        return dict(success=False, code='worker_failed', message='Не удалось подключиться к управлению окнами. Backend продолжает работать.')


def _normal(value):
    return re.sub(r'[^\w]+', ' ', value.casefold().replace('ё', 'е')).strip()


def _score(query, window):
    from app_resolver import ALIASES, transliterate, _normalize
    query = _normalize(query.strip('«»“”\"\''))
    app = _normal(Path(window.get('app', '')).stem)
    title = _normal(window.get('title', ''))
    variants = {query, transliterate(query), ALIASES.get(query, '')}
    best = 0
    for value in variants:
        value = _normal(value)
        if not value:
            continue
        if value in (app, title):
            best = max(best, 1.)
        elif len(value) >= 3 and (f' {value} ' in f' {title} ' or f' {value} ' in f' {app} '):
            best = max(best, .9)
    return best


def _select(windows, query, active, multiple=False):
    if not query:
        return [window for window in windows if window['id'] == active], ''
    matches = sorted(((_score(query, window), index, window) for index,window in enumerate(windows)),
                     key=lambda row: (-row[0], row[1]))
    matches = [row for row in matches if row[0] >= .9]
    if not matches:
        return [], 'Не нашёл открытое окно с таким названием. Скажите: «Покажи открытые окна».'
    first = matches[0]
    tied = [row[2] for row in matches if row[0] == first[0]]
    if len(tied) == 1:
        return tied, ''
    if multiple and len({row.get('app') for row in tied}) == 1:
        return tied[:64], ''
    current = [row for row in tied if row['id'] == active]
    if current:
        return current, ''
    return [], 'Подходят несколько окон: ' + '; '.join(row['title'][:100] for row in tied[:5]) + '. Уточните название окна.'


def execute(request, *, scope_pids=None):
    """scope_pids restricts integration fixtures; text commands never supply it."""
    try:
        if os.environ.get('SCOTT_DESKTOP_DISABLED') == '1':
            return dict(success=False, code='disabled', response='Управление окнами отключено в этом окружении.')
        if not isinstance(request, dict) or request.get('operation') not in OPERATIONS:
            raise ValueError('Неизвестное действие с приложением.')
        operation = request['operation']
        query, control = request.get('query', ''), request.get('control', '')
        if not isinstance(query, str) or not isinstance(control, str) or len(query) > 512 or len(control) > 160:
            raise ValueError('Слишком длинное название окна или кнопки.')
        if operation in ('list_apps', 'refresh_apps'):
            import app_resolver
            if operation == 'refresh_apps':
                counts = app_resolver.refresh_index()
                return dict(success=True, response=f"Каталог приложений обновлён. Найдено записей: {sum(counts.values())}.")
            names = app_resolver.installed_names()
            return dict(success=True, response='Установленные приложения:\n'+'\n'.join(names[:60]) if names else 'Каталог приложений пока пуст.', count=len(names))
        excluded = own_pids()
        snapshot = _worker(dict(operation='list', exclude_pids=excluded))
        if not snapshot['success']:
            return dict(success=False, code=snapshot.get('code', 'unsupported'), response=snapshot.get('message', 'Оконная система недоступна.'))
        windows = snapshot.get('windows', [])
        if not isinstance(windows, list) or len(windows) > 256:
            raise ValueError('Некорректный список окон.')
        if scope_pids is not None:
            windows = [window for window in windows if window['pid'] in set(scope_pids)]
        if operation == 'list':
            return dict(success=True, response=('Открытые окна:\n'+'\n'.join(window['title'] for window in windows[:60])) if windows else 'Открытых окон приложений не найдено.', count=len(windows))
        if operation in ('close_all', 'minimize_all'):
            except_names = request.get('exclude', [])
            if not isinstance(except_names, list) or len(except_names) > 8 or any(not isinstance(name, str) or len(name)>160 for name in except_names):
                raise ValueError('Неверный список исключений.')
            targets = [window for window in windows if not any(_score(name, window) >= .9 for name in except_names)][:64]
        else:
            targets, reason = _select(windows, query, snapshot.get('active'), multiple=operation=='close_app')
            if reason:
                return dict(success=False, code='not_found' if not any(_score(query,w)>=.9 for w in windows) else 'ambiguous', response=reason)
        if not targets:
            return dict(success=False, code='not_found', response='Нет доступных окон для этого действия. Окна Скотта и его родительского процесса защищены.')
        if operation in ('controls', 'invoke'):
            from desktop_accessibility import run
            result = run(operation, targets[0], control, environment())
            fallback = (operation=='controls' and result['success'] and not result.get('controls')) or (
                operation=='invoke' and not result['success'] and result.get('code') in ('no_control','no_pattern'))
            if os.name=='nt' and fallback:
                result = _worker(dict(operation=operation,exclude_pids=excluded,
                                      targets=[dict(id=targets[0]['id'],pid=targets[0]['pid'])],control=control))
            if not result['success']:
                return dict(success=False, code=result.get('code', 'unavailable'), response=result.get('message', 'Действие с кнопкой не подтверждено.'))
            if operation == 'controls':
                names = result.get('controls', [])
                response = 'Доступные элементы:\n'+'\n'.join(names) if names else 'Приложение не предоставило доступных кнопок.'
                if result.get('truncated'):
                    response += '\nПоказана только часть элементов большого окна.'
            else:
                response = f'Нажал «{control}» в выбранном окне.'
            return dict(success=True, response=response,provider=result.get('provider','uia'))
        native_operation = {'close_all':'close', 'close_app':'close', 'minimize_all':'minimize'}.get(operation, operation)
        result = _worker(dict(operation=native_operation, exclude_pids=excluded,
                             targets=[dict(id=window['id'], pid=window['pid']) for window in targets]))
        accepted = result.get('accepted', [])
        if not result['success'] or not accepted:
            return dict(success=False, response=result.get('message', 'Система не подтвердила действие. Возможно, приложение имеет больше прав или запрещено переключение фокуса.'))
        if native_operation == 'close':
            response = f'Отправил запрос закрытия {len(accepted)} окнам. Приложения могут предложить сохранить документы.'
        elif operation == 'minimize_all':
            response = f'Отправил сворачивание {len(accepted)} окнам.'
        else:
            response = {'focus':'Переключился на выбранное окно.', 'minimize':'Отправил команду сворачивания окна.',
                        'maximize':'Отправил команду разворачивания окна.', 'restore':'Восстановил выбранное окно.'}[native_operation]
        if result.get('failed'):
            response += f" Не подтвердили действие: {len(result['failed'])}."
        if len(windows) > 64 and operation in ('close_all','minimize_all'):
            response += ' Обработано до 64 окон за одну команду.'
        return dict(success=True, response=response, requested=len(accepted))
    except Exception as error:
        # Do not let a disappearing window, provider or malformed catalog kill a request.
        return dict(success=False, response=str(error)[:400] if isinstance(error, ValueError) else 'Не удалось выполнить действие с приложением. Backend продолжает работать.')
