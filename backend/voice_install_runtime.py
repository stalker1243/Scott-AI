"""Private CPython and cancellable children for optional voice provisioning."""
from pathlib import Path
import hashlib
import json
import os
import math
import queue
import stat
import subprocess
import threading
import time
import urllib.request
import zipfile
from collections import deque

try:
    from .support_logs import append_log, redact
except ImportError:
    from support_logs import append_log, redact

import psutil
try:
    from .performance_trace import measured
except ImportError:
    from performance_trace import measured

PYTHON_VERSION = '3.13.7'
PYTHON_URL = 'https://api.nuget.org/v3-flatcontainer/python/3.13.7/python.3.13.7.nupkg'
PYTHON_SHA256 = 'e74272a824e23702dfb5f3e11c3660ceabac7487e3366d4551391db5cd762853'


def digest(path):
    checksum = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(8*1024*1024), b''):
            checksum.update(block)
    return checksum.hexdigest()


@measured('voice_setup.python')
def prepare_python(home, progress=None, package=None, cancelled=None):
    started = time.monotonic()
    def checkpoint():
        if cancelled is not None and cancelled.is_set():
            raise InstallationCancelled()
        if time.monotonic() - started > 1800:
            raise subprocess.TimeoutExpired('Scott Voice Python download', 1800)
    checkpoint()
    home = Path(home).resolve()
    destination = home/'python'
    if not destination.resolve().is_relative_to(home) or destination.is_symlink() or destination.is_junction():
        raise ValueError('Папка Python содержит перенаправление.')
    marker = destination/'package.json'
    if marker.is_file():
        info = json.loads(marker.read_text(encoding='utf-8'))
        if info.get('sha256') != PYTHON_SHA256:
            raise ValueError('В папке находится другой Python; выберите новую папку.')
        core = ('tools/python.exe', 'tools/python313.dll', 'tools/Lib/venv/__init__.py')
        if set(info.get('core', {})) == set(core) and all((destination/name).resolve().is_relative_to(destination)
                and (destination/name).is_file() and digest(destination/name) == info['core'][name] for name in core):
            return destination/'tools/python.exe'
    archive = Path(package) if package else home/'download-cache/python.3.13.7.nupkg'
    if not archive.is_file() or digest(archive) != PYTHON_SHA256:
        if package:
            raise ValueError('Контрольная сумма Python не совпадает.')
        archive.parent.mkdir(parents=True, exist_ok=True)
        try:
            from .model_download import download_file
        except ImportError:
            from model_download import download_file
        last_update = [0.]
        def transfer(done, total):
            checkpoint()
            if progress and time.monotonic() - last_update[0] >= 1:
                last_update[0] = time.monotonic()
                amount = f'{done/(1024*1024):.1f} МиБ' + (f' / {total/(1024*1024):.1f} МиБ' if total else '')
                progress('python', 'Загружаем Python: '+amount, .05)
        download_file(PYTHON_URL, archive, expected_sha256=PYTHON_SHA256, progress=transfer,
            status=lambda message: append_log('scott-voice-install.log', message))
    with zipfile.ZipFile(archive) as bundle:
        files = [item for item in bundle.infolist() if item.filename.startswith('tools/') and not item.is_dir()]
        for item in files:
            target = destination/item.filename
            if item.orig_filename != item.filename or not target.resolve().is_relative_to(destination.resolve()) or '\\' in item.filename or ':' in item.filename or '..' in Path(item.filename).parts or stat.S_ISLNK(item.external_attr >> 16):
                raise ValueError('Неверный путь в пакете Python.')
        for item in files:
            checkpoint()
            target = destination/item.filename
            target.parent.mkdir(parents=True, exist_ok=True)
            with bundle.open(item) as source, target.open('wb') as output:
                while block := source.read(1024*1024):
                    checkpoint()
                    output.write(block)
    core = ('tools/python.exe', 'tools/python313.dll', 'tools/Lib/venv/__init__.py')
    if not all((destination/name).is_file() for name in core):
        raise ValueError('Пакет Python неполон.')
    marker.write_text(json.dumps(dict(version=PYTHON_VERSION, sha256=PYTHON_SHA256,
                      core={name:digest(destination/name) for name in core}), indent=2), encoding='utf-8')
    return destination/'tools/python.exe'


class InstallationCancelled(Exception):
    pass


class CancellableRunner:
    def __init__(self, progress):
        self.cancelled = threading.Event()
        self.progress = progress
        self.stage, self.message, self.fraction = 'libraries', 'Подготавливаем Scott Voice', .2

    def step(self, stage, message, fraction):
        self.stage, self.message, self.fraction = stage, message, fraction
        if self.progress:
            self.progress(stage, message, fraction)

    def watch_parent(self):
        owner = os.getenv('SCOTT_VOICE_INSTALL_OWNER', '')
        if not owner:
            return
        try:
            expected = float(os.getenv('SCOTT_VOICE_INSTALL_OWNER_CREATED', '0'))
        except ValueError:
            self.cancelled.set()
            return
        def watch():
            while not self.cancelled.wait(.3):
                try:
                    parent = psutil.Process(int(owner))
                    if parent.create_time() != expected or not parent.is_running():
                        self.cancelled.set()
                except (psutil.NoSuchProcess, psutil.ZombieProcess, psutil.AccessDenied, ValueError):
                    self.cancelled.set()
        threading.Thread(target=watch, daemon=True).start()

    def __call__(self, command, **kwargs):
        if self.cancelled.is_set():
            raise InstallationCancelled()
        captured = kwargs.pop('capture_output', False)
        kwargs.pop('check', None)
        kwargs.pop('text', None)
        timeout = kwargs.pop('timeout', None)
        stdin = kwargs.pop('stdin', subprocess.DEVNULL)
        process = subprocess.Popen(command, stdout=subprocess.PIPE,
            stdin=stdin, stderr=subprocess.PIPE, text=True, encoding='utf-8', errors='replace',
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0), **kwargs)
        output, errors, tail = deque(), deque(), deque(maxlen=12)
        events = queue.Queue(maxsize=64)
        sizes = [0, 0]
        def drain(stream, parts, index):
            while line := stream.readline(16384):
                safe = redact(line).strip()
                if safe:
                    append_log('scott-voice-install.log', safe)
                    display = safe[-1000:]
                    if index == 0 and self.stage == 'model':
                        try:
                            event = json.loads(safe)
                            fraction = event.get('fraction') if isinstance(event, dict) else None
                            if event.get('type') == 'progress' and event.get('stage') == 'model' and type(fraction) in (int, float) and math.isfinite(fraction) and isinstance(event.get('message'), str):
                                events.put_nowait((event['message'][:1000], max(.6, min(.9, fraction))))
                                display = event['message'][:1000]
                        except (ValueError, AttributeError, queue.Full):
                            pass
                    tail.append(display)
                parts.append(line); sizes[index] += len(line)
                while sizes[index] > 1024*1024 and len(parts) > 1:
                    sizes[index] -= len(parts.popleft())
        readers = [threading.Thread(target=drain, args=(process.stdout, output, 0), daemon=True),
                   threading.Thread(target=drain, args=(process.stderr, errors, 1), daemon=True)]
        for reader in readers:
            reader.start()
        def forward_events():
            while True:
                try:
                    message, fraction = events.get_nowait()
                except queue.Empty:
                    return
                self.step('model', message, fraction)
        try:
            owner = psutil.Process(process.pid)
        except psutil.NoSuchProcess:
            owner = None
        try:
            started = time.monotonic()
            last_progress = started
            while True:
                forward_events()
                expired = timeout is not None and time.monotonic()-started > timeout
                if self.cancelled.is_set() or expired:
                    try:
                        from .scott_voice_process import stop_process_tree
                    except ImportError:
                        from scott_voice_process import stop_process_tree
                    stop_process_tree(process, owner)
                    if expired:
                        raise subprocess.TimeoutExpired(command, timeout, stderr='\n'.join(tail))
                    raise InstallationCancelled()
                try:
                    process.wait(timeout=.2)
                    break
                except subprocess.TimeoutExpired:
                    if self.progress and time.monotonic() - last_progress >= 2:
                        last_progress = time.monotonic()
                        self.progress(self.stage, f'{self.message} · {int((last_progress-started)/60)} мин.\n'+(tail[-1] if tail else 'Ожидаем ответ процесса…'), self.fraction)
            for reader in readers:
                reader.join(timeout=2)
            forward_events()
            if process.returncode:
                raise subprocess.CalledProcessError(process.returncode, command,
                    output=''.join(output), stderr='\n'.join(tail))
            return subprocess.CompletedProcess(command, 0, stdout=''.join(output) if captured else '', stderr=''.join(errors) if captured else '')
        finally:
            if process.poll() is None:
                try:
                    from .scott_voice_process import stop_process_tree
                except ImportError:
                    from scott_voice_process import stop_process_tree
                stop_process_tree(process, owner)
            for reader in readers:
                reader.join(timeout=2)
            process.stdout.close(); process.stderr.close()
