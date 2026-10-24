"""Bounded pip cache for one managed runtime; never touches the global cache."""
import json
import os
from pathlib import Path

try:
    from .torch_download import _safe, _file, _folder
    from .model_download import DownloadError
except ImportError:
    from torch_download import _safe, _file, _folder
    from model_download import DownloadError

LIMIT = 256 * 1024 * 1024
IDENTITY = {'version': 1, 'purpose': 'scott-runtime-pip-cache'}
MARKER = '.scott-cache.json'
PIP_FOLDERS = ('http', 'http-v2', 'wheels', 'selfcheck')

def prepare(directory):
    directory = Path(directory).absolute()
    _safe(directory)
    marker = directory / MARKER
    _safe(marker)
    if marker.is_file():
        try:
            owned = marker.stat().st_size <= 1024 and json.loads(marker.read_text(encoding='utf-8')) == IDENTITY
        except (OSError, ValueError):
            owned = False
        if not owned:
            raise DownloadError('В папке кеша находятся другие данные. Выберите другую папку установки.')
    elif directory.is_dir() and any(directory.iterdir()):
        raise DownloadError('Папка кеша не принадлежит установщику. Выберите другую папку установки.')
    directory = _folder(directory)
    if not marker.exists():
        with _file(marker, 'wb') as stream:
            stream.write(json.dumps(IDENTITY).encode('utf-8'))
    return directory

def trim(directory, limit=LIMIT):
    """Remove oldest owned cache entries only after pip has stopped."""
    if limit < 0:
        raise ValueError('Invalid cache limit')
    directory = prepare(directory)
    boundary = directory.resolve()
    files = []
    for name in PIP_FOLDERS:
        start = directory / name
        _safe(start)
        if not start.is_dir():
            continue
        for root, dirs, names in os.walk(start, followlinks=False):
            for part in dirs + names:
                path = Path(root) / part
                _safe(path)
                if not path.resolve().is_relative_to(boundary):
                    raise DownloadError('Файл кеша выходит за папку установки.')
            for name in names:
                path = Path(root) / name
                info = path.stat()
                files.append((info.st_mtime, info.st_size, path))
    size = sum(item[1] for item in files)
    for _, length, path in sorted(files):
        if size <= limit:
            break
        _safe(path)
        if not path.resolve().is_relative_to(boundary):
            raise DownloadError('Файл кеша выходит за папку установки.')
        path.unlink()
        size -= length
    return size

def maintain(directory, *, complete=False):
    if directory is None:
        return
    try:
        trim(directory, 0 if complete else LIMIT)
    except (OSError, ValueError, DownloadError):
        # Cleanup cannot invalidate an installed runtime or replace pip's error.
        pass
