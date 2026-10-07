"""One owned provisioning process; HTTP never waits for pip or a model."""
from __future__ import annotations
import atexit
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
import threading
import uuid
import psutil

try:
    from . import scott_voice_install as setup
    from .scott_voice_process import stop_process_tree
except ImportError:
    import scott_voice_install as setup
    from scott_voice_process import stop_process_tree

STAGES = {'python':'Подготавливаем окружение', 'environment':'Создаём окружение голоса',
    'libraries':'Устанавливаем библиотеки голоса', 'model':'Загружаем файлы голоса',
    'verification':'Проверяем готовность голоса', 'complete':'Scott Voice готов'}
ACTIVE = {'running', 'cancelling'}

class JobConflict(ValueError):
    pass

class VoiceInstallJobs:
    def __init__(self, root=setup.ROOT, popen=subprocess.Popen, refresh=None, before_update=None):
        self.root = Path(root)
        self.home = setup.home_path(root)
        self.popen, self.refresh = popen, refresh
        self.before_update=before_update
        self._lock = threading.RLock()
        self._process = self._owner = self._thread = None
        self._state = dict(id='', state='idle', action='', stage='', message='', progress=0.)

    def installed(self):
        try:
            marker = json.loads((self.home/'scott-install.json').read_text(encoding='utf-8'))
            return (marker.get('ready') is True and marker.get('model') == setup.MODEL
                    and marker.get('revision') == setup.REVISION)
        except (OSError, ValueError, AttributeError):
            return False

    def snapshot(self):
        with self._lock:
            return dict(self._state, installed=self.installed(),
                        supported=os.name == 'nt' and struct.calcsize('P') == 8)

    def start(self, action):
        if action not in ('install', 'check'):
            raise ValueError('Неизвестное действие.')
        with self._lock:
            if self._state['state'] in ACTIVE:
                raise JobConflict('Подготовка голоса уже выполняется.')
            if action == 'install' and (os.name != 'nt' or struct.calcsize('P') != 8):
                raise ValueError('Установка Scott Voice пока доступна для Windows x64.')
            home = self.home
            command = [sys.executable, '-u', str(self.root/'backend/scott_voice_install.py'), '--json', '--'+action]
            if action == 'install':
                command += ['--auto-python']
                source = self.root/'experiments/voice_design/models/base'
                if source.is_dir():
                    command += ['--model-source', str(source)]
            elif not self.installed() and not os.getenv('SCOTT_VOICE_HOME', '').strip():
                home = self.root
            else:
                command += ['--deep']
            command += ['--home', str(home)]
            if action=='install' and self.before_update is not None:
                self.before_update()
            env = setup.clean_environment()
            env.update(SCOTT_VOICE_INSTALL_OWNER=str(os.getpid()),
                       SCOTT_VOICE_INSTALL_OWNER_CREATED=str(psutil.Process().create_time()))
            process = self.popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL, text=True, encoding='utf-8', env=env,
                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            try:
                owner = psutil.Process(process.pid)
            except psutil.NoSuchProcess:
                owner = None
            job = uuid.uuid4().hex
            self._process, self._owner = process, owner
            self._state = dict(id=job, state='running', action=action,
                stage='verification' if action == 'check' else 'python',
                message='Проверяем Scott Voice' if action == 'check' else 'Подготавливаем Scott Voice', progress=0.)
            self._thread = threading.Thread(target=self._read, args=(job, process, owner), daemon=True)
            self._thread.start()
            return self.snapshot()

    def _read(self, job, process, owner):
        result, cancelled, error_code = None, False, ''
        try:
            while line := process.stdout.readline(16385):
                if len(line) > 16384:
                    continue
                try:
                    event = json.loads(line)
                    if not isinstance(event, dict):
                        continue
                except ValueError:
                    continue
                with self._lock:
                    if self._state['id'] != job:
                        return
                    if event.get('type') == 'progress' and self._state['state'] == 'running':
                        stage = event.get('stage')
                        if stage in STAGES:
                            self._state.update(stage=stage, message=STAGES[stage],
                                progress={'python':.05, 'environment':.15, 'libraries':.3,
                                          'model':.6, 'verification':.9, 'complete':1.}[stage])
                    elif event.get('type') == 'result':
                        result = event.get('available') is True
                        error_code = event.get('error', '')
                    elif event.get('type') == 'error':
                        cancelled = event.get('cancelled') is True
                        error_code = 'cancelled' if cancelled else 'install_failed'
            code = process.wait()
            with self._lock:
                cancelled = cancelled or self._state['state'] == 'cancelling'
            if code == 0 and result and not cancelled:
                if self.refresh:
                    self.refresh()
                else:
                    try:
                        from .scott_voice_engine import reload_installation
                    except ImportError:
                        from scott_voice_engine import reload_installation
                    reload_installation()
            with self._lock:
                if self._state['id'] == job:
                    cancelled = cancelled or self._state['state'] == 'cancelling'
                    state = 'cancelled' if cancelled else 'complete' if code == 0 and result else 'failed'
                    self._state.update(state=state, progress=1. if state == 'complete' else self._state['progress'],
                        error=error_code if error_code in ('cuda_unavailable', 'not_installed', 'invalid_assets', 'runtime_unavailable', 'missing_checksums', 'cancelled', 'install_failed') else 'process_failed' if state == 'failed' else '',
                        exit_code=code,
                        message={'cancelled':'Подготовка отменена. Её можно продолжить позже.',
                                 'complete':'Scott Voice проверен и готов к выбору.',
                                 'failed':'Подготовка не завершена. Проверьте подключение, свободное место и повторите попытку.'}[state])
                    if state == 'failed' and error_code == 'cuda_unavailable':
                        self._state['message'] = 'Для Scott Voice не найдена доступная NVIDIA/CUDA. Поддержка AMD и CPU ещё проверяется.'
                    elif state == 'failed' and error_code == 'not_installed':
                        self._state['message'] = 'Scott Voice пока не установлен. Нажмите «Установить Scott Voice».'
        except (OSError, ValueError, subprocess.SubprocessError):
            with self._lock:
                if self._state['id'] == job:
                    self._state.update(state='failed', message='Не удалось проверить Scott Voice. Повторите попытку.')
        finally:
            if process.poll() is None:
                stop_process_tree(process, owner)
            for stream in (process.stdin, process.stdout):
                if stream:
                    stream.close()
            with self._lock:
                if self._process is process:
                    self._process = self._owner = None

    def cancel(self, job):
        with self._lock:
            if job != self._state['id']:
                raise JobConflict('Это уже другая подготовка голоса. Обновите состояние.')
            if self._state['state'] not in ACTIVE:
                return self.snapshot()
            self._state.update(state='cancelling', message='Отменяем подготовку…')
            process, owner = self._process, self._owner
            try:
                process.stdin.write('cancel\n')
                process.stdin.flush()
            except (OSError, ValueError, AttributeError):
                pass
            def finish():
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    stop_process_tree(process, owner)
            threading.Thread(target=finish, daemon=True).start()
            return self.snapshot()

    def close(self):
        with self._lock:
            job = self._state['id'] if self._state['state'] in ACTIVE else None
            thread = self._thread
        if job:
            self.cancel(job)
        if thread and thread is not threading.current_thread():
            thread.join(timeout=7)

def _quiesce_voice():
    try:
        from .audio_endpoints import _stop_current_speech
        from .scott_voice_engine import reload_installation
    except ImportError:
        from audio_endpoints import _stop_current_speech
        from scott_voice_engine import reload_installation
    _stop_current_speech()
    reload_installation()


jobs = VoiceInstallJobs(before_update=_quiesce_voice)
atexit.register(jobs.close)
