"""Private CPython and cancellable children for optional voice provisioning."""
from pathlib import Path
import hashlib
import json
import os
import stat
import subprocess
import threading
import time
import urllib.request
import zipfile

import psutil

PYTHON_VERSION = '3.13.7'
PYTHON_URL = 'https://api.nuget.org/v3-flatcontainer/python/3.13.7/python.3.13.7.nupkg'
PYTHON_SHA256 = 'e74272a824e23702dfb5f3e11c3660ceabac7487e3366d4551391db5cd762853'


def digest(path):
    checksum = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(8*1024*1024), b''):
            checksum.update(block)
    return checksum.hexdigest()


def prepare_python(home, progress=None, package=None, cancelled=None):
    def checkpoint():
        if cancelled is not None and cancelled.is_set():
            raise InstallationCancelled()
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
        temporary = archive.with_suffix('.part')
        with urllib.request.urlopen(PYTHON_URL, timeout=30) as source, temporary.open('wb') as target:
            while block := source.read(1024*1024):
                checkpoint()
                target.write(block)
        if digest(temporary) != PYTHON_SHA256:
            raise ValueError('Контрольная сумма Python не совпадает.')
        os.replace(temporary, archive)
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
        process = subprocess.Popen(command, stdout=subprocess.PIPE if captured else subprocess.DEVNULL,
            stdin=stdin, stderr=subprocess.DEVNULL, text=True, encoding='utf-8',
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0), **kwargs)
        try:
            owner = psutil.Process(process.pid)
        except psutil.NoSuchProcess:
            owner = None
        try:
            started = time.monotonic()
            while True:
                expired = timeout is not None and time.monotonic()-started > timeout
                if self.cancelled.is_set() or expired:
                    try:
                        from .scott_voice_process import stop_process_tree
                    except ImportError:
                        from scott_voice_process import stop_process_tree
                    stop_process_tree(process, owner)
                    if expired:
                        raise subprocess.TimeoutExpired(command, timeout)
                    raise InstallationCancelled()
                try:
                    output, _ = process.communicate(timeout=.2)
                    break
                except subprocess.TimeoutExpired:
                    pass
            if process.returncode:
                raise subprocess.CalledProcessError(process.returncode, command)
            return subprocess.CompletedProcess(command, 0, stdout=output or '')
        finally:
            if process.poll() is None:
                try:
                    from .scott_voice_process import stop_process_tree
                except ImportError:
                    from scott_voice_process import stop_process_tree
                stop_process_tree(process, owner)
