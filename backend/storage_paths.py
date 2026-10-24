"""User storage for installed Linux builds; source/Windows paths stay compatible.

The first reader completes migration before opening any application store. Original
files are never removed. The receipt prevents deleted history being imported again.
This module deliberately uses only the standard library (setup/offline diagnostics).
"""
from contextlib import contextmanager, closing
from dataclasses import dataclass, replace
from functools import lru_cache
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import sys
import tempfile
import time

try:
    from .platform_paths import xdg_home, private_directory
except ImportError:
    from platform_paths import xdg_home, private_directory

ROOT = Path(__file__).resolve().parent.parent
CONFIG_FILES = frozenset(('ai_config.json', 'personality.json', 'device_config.json',
                          'audio_config.json', 'voice_config.json', 'remote_access.json',
                          'runtime_profile.json'))
RECEIPT = '.storage-v1.json'


class StorageMigrationError(RuntimeError):
    pass


@dataclass(frozen=True)
class Layout:
    root: Path
    data: Path
    config: Path
    cache: Path
    external: bool

    def backend(self, name=''):
        if self.external and name == 'update_check.json':
            return self.cache/name
        return (self.config if self.external and name in CONFIG_FILES else self.data)/name

    @property
    def environment(self):
        return self.config/'.env' if self.external else self.root/'.env'

    def legacy_data(self, name):
        return self.data/'legacy'/name if self.external else self.root/'data'/name


def layout_for(root=ROOT, *, env=None, home=None, platform=None):
    """Pure decision. Only a marked Linux installation opts into XDG storage."""
    root = Path(root).resolve()
    env = os.environ if env is None else env
    external = ((platform or sys.platform) == 'linux'
                and env.get('SCOTT_STORAGE_MODE') != 'legacy'
                and (root/'.scott-linux-install.json').is_file())
    if not external:
        return Layout(root, root/'backend/data', root/'backend/data', root/'audio_cache', False)
    # The historical install prefix is Data/ScottAI (capital S). A distinct
    # Linux user directory also works when that entire prefix is read-only.
    def base(variable):
        # Normalize '..' lexically without following symlinks; migration still
        # rejects linked destination ancestors rather than hiding them here.
        return Path(os.path.abspath(xdg_home(variable, env=env, home=home)))
    return Layout(root, base('XDG_DATA_HOME')/'scottai',
                  base('XDG_CONFIG_HOME')/'ScottAI', base('XDG_CACHE_HOME')/'ScottAI', True)


def _no_links(path):
    if any(parent.is_symlink() for parent in (path, *path.parents)):
        raise StorageMigrationError('Перенос данных остановлен: путь содержит символическую ссылку. Оригиналы сохранены.')


def _digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


@contextmanager
def _migration_lock(directory, timeout=30):
    _no_links(directory)
    private_directory(directory)
    path = directory/'.migration.lock'
    _no_links(path)
    with path.open('a+b') as lock:
        if not path.stat().st_size:
            lock.write(b'0'); lock.flush()
        deadline = time.monotonic()+timeout
        while True:
            try:
                if os.name == 'nt':
                    import msvcrt
                    lock.seek(0)
                    msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except (BlockingIOError, OSError):
                if time.monotonic() >= deadline:
                    raise StorageMigrationError('Другой процесс переносит данные ScottAI. Закройте его и повторите запуск.') from None
                time.sleep(.05)
        try:
            yield
        finally:
            if os.name == 'nt':
                lock.seek(0)
                msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(lock, fcntl.LOCK_UN)


def _sources(layout):
    backend = layout.root/'backend/data'
    for base in (backend, layout.root/'data'):
        if not base.exists():
            continue
        _no_links(base)
        for folder, directories, files in os.walk(base, followlinks=False):
            folder = Path(folder)
            # Model files keep their original location and are reused there.
            if folder == backend:
                directories[:] = [name for name in directories if name not in ('models', 'semantic-model')]
            directories[:] = [name for name in directories if name != '__pycache__']
            for name in directories:
                _no_links(folder/name)
            for name in files:
                source = folder/name
                _no_links(source)
                if not source.is_file():
                    raise StorageMigrationError('Перенос данных остановлен: неизвестный тип файла. Оригиналы сохранены.')
                relative = source.relative_to(base)
                sidecar = next((suffix for suffix in ('-wal', '-shm', '-journal') if name.endswith(suffix)), None)
                if sidecar:
                    database = source.with_name(name[:-len(sidecar)])
                    if database.is_file():
                        with database.open('rb') as stream:
                            if stream.read(16) == b'SQLite format 3\0':
                                continue
                if source.suffix == '.pyc':
                    continue
                target = layout.backend(relative.as_posix()) if base == backend else layout.legacy_data(relative)
                yield source, target
    environment = layout.root/'.env'
    if environment.exists() or environment.is_symlink():
        _no_links(environment)
        yield environment, layout.environment
    heard = layout.root/'backend/logs/heard.jsonl'
    if heard.exists() or heard.is_symlink():
        _no_links(heard)
        yield heard, layout.backend('heard.jsonl')


def _snapshot(source, target):
    with source.open('rb') as stream:
        sqlite = stream.read(16) == b'SQLite format 3\0'
    if not sqlite:
        shutil.copyfile(source, target)
    else:
        # mode=ro includes committed WAL frames without checkpointing/removing
        # the user's original WAL. immutable=1 would lose those transactions.
        deadline = time.monotonic()+30
        def progress(status, remaining, total):
            if time.monotonic() > deadline:
                raise StorageMigrationError('История занята другим процессом. Закройте старый ScottAI и повторите запуск.')
        with closing(sqlite3.connect(source.as_uri()+'?mode=ro', uri=True, timeout=1)) as original:
            with closing(sqlite3.connect(target)) as snapshot:
                original.backup(snapshot, pages=256, progress=progress, sleep=.05)
                snapshot.execute('PRAGMA journal_mode=DELETE')
                if snapshot.execute('PRAGMA quick_check').fetchone() != ('ok',):
                    raise StorageMigrationError('Не удалось проверить копию истории. Оригинал сохранён.')
    target.chmod(0o600)


def _source_stamp(source):
    """Detect ordinary concurrent edits, including commits appended to a WAL."""
    values = []
    for file in (source, source.with_name(source.name+'-wal'), source.with_name(source.name+'-journal')):
        _no_links(file)
        try:
            value = file.stat()
            values.append((value.st_dev, value.st_ino, value.st_size, value.st_mtime_ns))
        except FileNotFoundError:
            values.append(None)
    return tuple(values)


def _publish(source, target):
    """Exclusive atomic file publication, including across XDG filesystems."""
    _no_links(target)
    private_directory(target.parent)
    descriptor, name = tempfile.mkstemp(prefix='.scott-copy-', dir=target.parent)
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, 'wb') as stream, source.open('rb') as original:
            shutil.copyfileobj(original, stream)
            stream.flush(); os.fsync(stream.fileno())
        os.link(temporary, target)  # Fails if another file appeared; never replace it.
        if os.name != 'nt':
            directory = os.open(target.parent, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
    finally:
        temporary.unlink(missing_ok=True)


def migrate(layout):
    """Copy once; validate all conflicts before publication; retry after interruption."""
    if not layout.external:
        return
    destinations = (layout.data, layout.config, layout.cache)
    for index, directory in enumerate(destinations):
        _no_links(directory)
        for other in destinations[index+1:]:
            if directory.is_relative_to(other) or other.is_relative_to(directory):
                raise StorageMigrationError('Каталоги XDG для данных, настроек и кеша пересекаются. Выберите отдельные каталоги; оригиналы сохранены.')
        for source in (layout.root/'backend/data', layout.root/'data'):
            if directory.is_relative_to(source) or source.is_relative_to(directory):
                raise StorageMigrationError('Новое хранилище пересекается со старой папкой данных. Оригиналы сохранены.')
    with _migration_lock(layout.data):
        receipt = layout.data/RECEIPT
        _no_links(receipt)
        pending = layout.data/'.migration-source-v1.json'
        _no_links(pending)
        locator = layout.config/'.storage-location-v1.json'
        _no_links(locator)
        if locator.exists():
            try:
                location = json.loads(locator.read_text(encoding='utf-8'))
                if location != {'version': 1, 'data': str(layout.data)}:
                    raise ValueError('data changed')
            except ValueError:
                raise StorageMigrationError('XDG_DATA_HOME изменён или запись хранилища повреждена. Восстановите прежнее расположение данных; оригиналы сохранены.') from None
        if receipt.exists():
            try:
                state = json.loads(receipt.read_text(encoding='utf-8'))
                if state.get('version') != 1 or state.get('config') != str(layout.config) or not locator.exists():
                    raise ValueError('layout changed')
            except (ValueError, AttributeError):
                raise StorageMigrationError('Каталог настроек изменён или запись переноса повреждена. Оригиналы сохранены; восстановите прежний XDG_CONFIG_HOME.') from None
            # One user store is shared by installed versions. Never import stale
            # originals again, even from a new install prefix or after clearing chat.
            private_directory(layout.config)
            private_directory(layout.cache)
            return
        origin = layout
        if pending.exists():
            try:
                state = json.loads(pending.read_text(encoding='utf-8'))
                source = Path(state['source'])
                if (state.get('version') != 1 or state.get('config') != str(layout.config)
                        or not source.is_absolute() or not source.is_dir()):
                    raise ValueError('invalid pending source')
                _no_links(source)
                origin = replace(layout, root=source)
            except (ValueError, KeyError, TypeError):
                raise StorageMigrationError('Незавершённый перенос требует прежнюю папку приложения. Восстановите её и повторите запуск; оригиналы сохранены.') from None
        for directory in (layout.config, layout.cache):
            _no_links(directory)
            private_directory(directory)
        # Only TemporaryDirectory's own staging directory may be removed.
        with tempfile.TemporaryDirectory(prefix='.migration-', dir=layout.data) as staging:
            copies = []
            stamps = []
            targets = {}
            for index, (source, target) in enumerate(_sources(origin)):
                before = _source_stamp(source)
                staged = Path(staging)/str(index)
                _snapshot(source, staged)
                stamps.append((source, before))
                digest = _digest(staged)
                if target in targets:
                    if targets[target] != digest:
                        raise StorageMigrationError(f'Два старых файла претендуют на {target}. Оригиналы сохранены; выберите нужную версию отдельно.')
                    continue
                targets[target] = digest
                _no_links(target)
                if target.exists():
                    if not target.is_file() or _digest(target) != digest:
                        raise StorageMigrationError(f'Конфликт переноса: {target}. Оба файла сохранены. Закройте ScottAI и сохраните нужную версию отдельно.')
                else:
                    copies.append((staged, target))
            for source, before in stamps:
                if before != _source_stamp(source):
                    raise StorageMigrationError('Старые данные изменились во время переноса. Закройте старый ScottAI и повторите запуск; оригиналы сохранены.')
            if not pending.exists():
                staged_pending = Path(staging)/'pending'
                staged_pending.write_text(json.dumps({'version': 1, 'source': str(origin.root),
                    'config': str(layout.config)}), encoding='utf-8')
                _publish(staged_pending, pending)
            for staged, target in copies:
                _publish(staged, target)
            if not locator.exists():
                staged_locator = Path(staging)/'location'
                staged_locator.write_text(json.dumps({'version': 1, 'data': str(layout.data)}), encoding='utf-8')
                _publish(staged_locator, locator)
            staged_receipt = Path(staging)/'receipt'
            staged_receipt.write_text(json.dumps({'version': 1, 'source': str(origin.root),
                'config': str(layout.config), 'files': len(stamps)}, indent=2), encoding='utf-8')
            _publish(staged_receipt, receipt)
            pending.unlink()


@lru_cache(maxsize=1)
def current():
    layout = layout_for()
    try:
        migrate(layout)
    except (OSError, sqlite3.Error) as error:
        raise StorageMigrationError('Не удалось перенести данные ScottAI. Проверьте права и свободное место. Оригиналы сохранены. '+str(error)) from error
    return layout


def backend_path(name=''):
    return current().backend(name)


def environment_path():
    return current().environment


def legacy_data_path(name):
    return current().legacy_data(name)


def heard_log_path():
    layout = current()
    return layout.backend('heard.jsonl') if layout.external else layout.root/'backend/logs/heard.jsonl'


def audio_cache():
    layout = current()
    return layout.cache/'audio' if layout.external else layout.cache


def model_directory(name, *, backend=None):
    """Reuse existing local weights; new optional weights go to the user cache."""
    if backend is not None and Path(backend).resolve() != ROOT/'backend':
        # Explicit standalone/diagnostic module roots retain their old contract.
        return Path(backend)/'data'/name
    layout = current()
    legacy = layout.root/'backend/data'/name
    if not layout.external or legacy.exists():
        return legacy
    try:
        state = json.loads((layout.data/RECEIPT).read_text(encoding='utf-8'))
        original = Path(state['source'])/'backend/data'/name
        if original.is_absolute() and original.exists():
            return original
    except (OSError, ValueError, KeyError, TypeError):
        pass
    return layout.cache/name
