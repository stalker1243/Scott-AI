"""Bounded browser jobs with a persistent, owned subprocess and stale-ID checks."""
import atexit
from functools import wraps
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import threading
import time
import uuid
import psutil
try:
    from .browser_control_config import HOME, ACTIONS, ACTIVE, installed, clean_environment
    from .storage import atomic_write_text
    from .scott_voice_process import stop_process_tree
except ImportError:
    from browser_control_config import HOME, ACTIONS, ACTIVE, installed, clean_environment
    from storage import atomic_write_text
    from scott_voice_process import stop_process_tree


class JobConflict(ValueError):
    pass


def serialized(method):
    @wraps(method)
    def call(self, *args, **kwargs):
        with self._operation_lock:
            return method(self, *args, **kwargs)
    return call


class BrowserJobs:
    def __init__(self, home=HOME, popen=subprocess.Popen, timeout=95):
        self.home, self.popen, self.timeout = Path(home), popen, timeout
        self._lock = threading.RLock()
        self._operation_lock = threading.RLock()
        self._process = self._owner = None
        self._setup_process = False
        self._deadline = 0
        self._state = dict(id='', state='idle', action='', stage='', message='', progress=0.,
                           candidates=[], results_id='', playback={}, browser_open=False)

    @property
    def enabled(self):
        try:
            return json.loads((self.home / 'settings.json').read_text(encoding='utf-8')).get('enabled') is True
        except (OSError, ValueError, AttributeError):
            return False

    @serialized
    def set_enabled(self, enabled):
        if not enabled:
            self.close()
        atomic_write_text(self.home / 'settings.json', json.dumps({'enabled': bool(enabled)}))
        return self.snapshot()

    def snapshot(self):
        with self._lock:
            return dict(self._state, candidates=[dict(row) for row in self._state['candidates']],
                        installed=installed(self.home), enabled=self.enabled)

    @serialized
    def start(self, action, query='', index=None, results_id=None):
        if action not in ACTIONS:
            raise ValueError('Неизвестная команда браузеру.')
        if action in ('search', 'play') and (not isinstance(query, str) or not query.strip() or len(query) > 500):
            raise ValueError('Введите запрос длиной до 500 символов.')
        with self._lock:
            if self._state['state'] in ACTIVE:
                raise JobConflict('Дождитесь текущего действия или нажмите «Стоп».')
            if action == 'close':
                self.close()
                self._state.update(state='idle', action='close', message='Окно браузера Scott закрыто')
                return self.snapshot()
            if action != 'install' and (not installed(self.home) or not self.enabled):
                raise ValueError('Подготовьте управление браузером в меню «Браузер» диалога.')
            ident, command = uuid.uuid4().hex, {'action': action, 'query': query.strip()}
            if action == 'select':
                if results_id != self._state['results_id'] or not results_id:
                    raise JobConflict('Результаты поиска изменились. Выберите видео заново.')
                if isinstance(index, bool) or not isinstance(index, int) or not 0 <= index < len(self._state['candidates']):
                    raise ValueError('Такого видео нет в результатах.')
                command['video_id'] = self._state['candidates'][index]['video_id']
            command['id'] = ident
            if (action == 'install' or self._setup_process) and self._process is not None:
                self.close()
            self._state.update(id=ident, state='running', action=action, stage='starting',
                               message='Подготавливаем браузер' if action == 'install' else 'Начинаем действие в браузере', progress=0.)
            if action in ('search', 'play', 'home', 'install'):
                self._state.update(candidates=[], results_id='', playback={})
            elif action in ('select', 'pause', 'resume'):
                self._state['playback'] = {}
            self._deadline = time.monotonic() + (1900 if action == 'install' else self.timeout)
            if self._process is None or self._process.poll() is not None:
                module = 'browser_setup.py' if action == 'install' else 'browser_control_worker.py'
                args = [sys.executable, '-u', str(Path(__file__).with_name(module)), '--home', str(self.home)]
                args += ['--owner', str(os.getpid()), '--owner-created', str(psutil.Process().create_time())]
                try:
                    process = self.popen(args, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                         text=True, encoding='utf-8', env=clean_environment(self.home),
                                         creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
                except OSError:
                    self._state.update(state='failed', message='Не удалось запустить процесс браузера.')
                    raise ValueError(self._state['message']) from None
                self._process = process
                self._setup_process = action == 'install'
                try:
                    self._owner = psutil.Process(process.pid)
                except psutil.NoSuchProcess:
                    self._owner = None
                threading.Thread(target=self._read, args=(process, action == 'install'), daemon=True).start()
                threading.Thread(target=self._drain, args=(process,), daemon=True).start()
                threading.Thread(target=self._watch, args=(process,), daemon=True).start()
            if action != 'install':
                try:
                    self._process.stdin.write(json.dumps(command, ensure_ascii=False) + '\n')
                    self._process.stdin.flush()
                except (OSError, ValueError):
                    self.close()
                    self._state.update(state='failed', message='Связь с браузером прервана. Повторите команду.')
            return self.snapshot()

    def _event(self, event, setup):
        if not isinstance(event, dict):
            return
        with self._lock:
            if event.get('type') == 'fatal':
                self._state.update(state='failed', message='Браузер недоступен. Повторите подготовку; на Linux проверьте библиотеки Chromium.', browser_open=False)
                return
            if event.get('type') == 'window_closed':
                self._state['browser_open'] = False
                self._state['playback'] = {}
                return
            if not setup and event.get('id') != self._state['id']:
                return
            if self._state['state'] != 'running':
                return
            if event.get('type') == 'window_open':
                self._state['browser_open'] = True
                return
            if event.get('type') not in ('progress', 'result'):
                return
            self._state['message'] = str(event.get('message', ''))[:500]
            progress = event.get('progress', 0.)
            if isinstance(progress, (int, float)):
                self._state['progress'] = max(0., min(1., progress))
            if event.get('type') == 'progress':
                self._state['stage'] = str(event.get('stage', ''))[:32]
            else:
                self._state['state'] = 'complete' if event.get('state') == 'complete' else 'failed'
                if setup and self._state['state'] == 'complete':
                    if installed(self.home):
                        atomic_write_text(self.home / 'settings.json', json.dumps({'enabled': True}))
                    else:
                        self._state.update(state='failed', message='Подготовка браузера не подтверждена.')
                rows = event.get('candidates')
                if isinstance(rows, list):
                    self._state['candidates'] = [{'video_id': str(row['video_id']), 'title': str(row.get('title', 'Видео'))[:200]}
                        for row in rows[:5] if isinstance(row, dict) and re.fullmatch(r'[A-Za-z0-9_-]{11}', str(row.get('video_id', '')))]
                    self._state['results_id'] = self._state['id']
                if isinstance(event.get('playback'), dict):
                    row = event['playback']
                    self._state['playback'] = {key: row[key] for key in ('title', 'video_id', 'paused', 'verified') if key in row}

    def _read(self, process, setup):
        try:
            while line := process.stdout.readline(16385):
                if len(line) > 16384:
                    continue
                try:
                    event = json.loads(line)
                except ValueError:
                    continue
                with self._lock:
                    if self._process is not process:
                        return
                    self._event(event, setup)
            code = process.wait(timeout=3)
            with self._lock:
                if self._process is process:
                    if self._state['state'] == 'running' or code != 0:
                        self._state.update(state='failed', message='Процесс браузера завершился. Повторите подготовку или команду.')
                    self._process = self._owner = None
                    self._state['browser_open'] = False
        except (OSError, ValueError, subprocess.SubprocessError):
            with self._operation_lock:
                with self._lock:
                    current = self._process is process
                if current:
                    self.close()
                    with self._lock:
                        self._state.update(state='failed', message='Связь с браузером потеряна.')

    def _drain(self, process):
        # Do not persist URLs, searches, page text or browser stderr in support logs.
        try:
            while process.stderr.read(4096):
                pass
        except (OSError, ValueError):
            pass

    def _watch(self, process):
        while True:
            time.sleep(.2)
            with self._lock:
                if self._process is not process:
                    return
                overdue = self._state['state'] == 'running' and time.monotonic() > self._deadline
                ident = self._state['id']
            if overdue:
                try:
                    self.cancel(ident, timeout=True)
                except JobConflict:
                    pass
                return

    @serialized
    def cancel(self, ident, timeout=False):
        with self._lock:
            if ident != self._state['id'] or self._state['state'] not in ACTIVE:
                raise JobConflict('Это действие уже завершилось или было заменено.')
            self._state['state'] = 'cancelling'
        self.close()
        with self._lock:
            self._state.update(state='failed' if timeout else 'cancelled',
                message='Действие заняло слишком много времени. Проверьте страницу и повторите.' if timeout else 'Действие остановлено')
            return self.snapshot()

    @serialized
    def close(self):
        with self._lock:
            process, owner = self._process, self._owner
            self._process = self._owner = None
            self._state.update(browser_open=False, candidates=[], results_id='', playback={})
            ident = self._state['id']
            active = self._state['state'] in ACTIVE
            if active:
                self._state.update(state='cancelling', message='Останавливаем действие')
        if process is not None:
            try:
                stop_process_tree(process, owner)
            finally:
                for stream in (process.stdin, process.stdout, process.stderr):
                    if stream:
                        stream.close()
        with self._lock:
            if active and self._state['id'] == ident:
                self._state.update(state='cancelled', message='Действие остановлено')


jobs = BrowserJobs()
atexit.register(jobs.close)
