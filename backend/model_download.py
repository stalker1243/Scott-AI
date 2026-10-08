"""Resumable model downloads. Publish a file only after validating its contents."""
from __future__ import annotations

from contextlib import contextmanager
import hashlib
import http.client
import json
import os
from pathlib import Path
import re
import time
from typing import Callable
import urllib.error
import urllib.request


class DownloadError(RuntimeError):
    pass


def checksum(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


@contextmanager
def _lock(path: Path):
    # Keep the inode: deleting the lock file could let a third process bypass it.
    with path.open('a+b') as stream:
        if stream.tell() == 0:
            stream.write(b'0')
            stream.flush()
        stream.seek(0)
        try:
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            raise DownloadError('Модель уже скачивается другим экземпляром Scott. Подождите и повторите.') from error
        try:
            yield
        finally:
            stream.seek(0)
            if os.name == 'nt':
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def download_file(url: str, target: Path, *, expected_sha256: str | None = None,
                  validate: Callable[[Path], bool] | None = None,
                  progress: Callable[[int, int | None], None] | None = None,
                  status: Callable[[str], None] | None = None,
                  timeout: float = 30, attempts: int = 3, retry_delay: float = 1) -> Path:
    """Keep .part on interruption; never accept a failed hash or append a 200 response.

    A provider without an official hash must supply a content validator instead.
    The original final file is preserved until a replacement passes validation.
    """
    target = Path(target)
    if expected_sha256 is not None and not re.fullmatch(r'[0-9a-f]{64}', expected_sha256):
        raise ValueError('Expected SHA256 must be a lowercase hex digest')
    if expected_sha256 is None and validate is None:
        raise ValueError('A checksum or content validator is required')
    if attempts < 1 or timeout <= 0:
        raise ValueError('A positive timeout and attempt count are required')
    target.parent.mkdir(parents=True, exist_ok=True)

    def valid(path: Path) -> bool:
        return (path.is_file() and (expected_sha256 is None or checksum(path) == expected_sha256)
                and (validate is None or validate(path)))

    def say(message: str):
        if status:
            status(message)

    with _lock(target.with_name(target.name + '.download.lock')):
        if valid(target):
            if progress:
                progress(target.stat().st_size, target.stat().st_size)
            return target
        part = target.with_name(target.name + '.part')
        metadata = target.with_name(target.name + '.part.json')
        identity = {'url': url, 'sha256': expected_sha256}
        try:
            saved = json.loads(metadata.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            saved = {}
        if saved.get('identity') != identity:
            # These two names belong exclusively to this downloader.
            part.unlink(missing_ok=True)
            saved = {'identity': identity}
        def save_metadata():
            temporary = metadata.with_name(metadata.name + '.tmp')
            temporary.write_text(json.dumps(saved), encoding='utf-8')
            os.replace(temporary, metadata)

        save_metadata()
        last_error = 'network'
        attempt = 0
        while attempt < attempts:
            try:
                offset = part.stat().st_size if part.exists() else 0
                total = saved.get('total')
                if total is not None and offset > total:
                    part.unlink()
                    offset = 0
                if offset and offset == total:
                    say('Проверяю целостность модели…')
                    if valid(part):
                        os.replace(part, target)
                        metadata.unlink(missing_ok=True)
                        return target
                    part.unlink()
                    offset = 0
                    last_error = 'checksum'
                    say('Проверка файла не прошла. Скачиваю модель заново…')
                headers = {'User-Agent': 'ScottAI-model-setup', 'Accept-Encoding': 'identity'}
                if offset:
                    headers['Range'] = f'bytes={offset}-'
                    # Azure may send an unquoted ETag (e.g. 0x8DA...). It is
                    # invalid as If-Range and makes that CDN ignore Range.
                    etag = saved.get('etag', '') or ''
                    if etag.startswith('"') and etag.endswith('"'):
                        headers['If-Range'] = saved['etag']
                    say('Продолжаю загрузку с сохранённого места…')
                request = urllib.request.Request(url, headers=headers)
                with urllib.request.urlopen(request, timeout=timeout) as response:
                    code = response.status
                    length = response.headers.get('Content-Length')
                    length = int(length) if length is not None else None
                    if code == 206:
                        match = re.fullmatch(r'bytes (\d+)-(\d+)/(\d+)', response.headers.get('Content-Range', ''))
                        if not match:
                            raise DownloadError('range')
                        begin, end, total = map(int, match.groups())
                        if begin != offset or end < begin or total <= end or (length is not None and length != end - begin + 1):
                            raise DownloadError('range')
                        length = end - begin + 1
                    elif code == 200:
                        # A server may ignore Range, or an ETag may have changed.
                        if offset:
                            say('Сервер начал передачу заново. Скачиваю полный файл…')
                        offset = 0
                        total = length
                    else:
                        raise DownloadError('network')
                    saved.update(total=total, etag=response.headers.get('ETag'))
                    save_metadata()
                    if progress:
                        progress(offset, total)
                    received = 0
                    with part.open('ab' if offset else 'wb') as output:
                        while True:
                            block = response.read(256 * 1024)
                            if not block:
                                break
                            output.write(block)
                            received += len(block)
                            if progress:
                                progress(offset + received, total)
                    if length is not None and received != length:
                        raise DownloadError('network')
                    if total is not None and part.stat().st_size < total:
                        # Some mirrors return one valid range per request.
                        # Continue without spending a retry on successful data.
                        if received:
                            continue
                        raise DownloadError('network')
                say('Проверяю целостность модели…')
                if not valid(part):
                    part.unlink(missing_ok=True)
                    saved.pop('total', None)
                    save_metadata()
                    raise DownloadError('checksum')
                os.replace(part, target)
                metadata.unlink(missing_ok=True)
                return target
            except urllib.error.HTTPError as error:
                last_error = 'network'
                # A cached partial may refer to an older remote object.
                if error.code == 416:
                    part.unlink(missing_ok=True)
                    saved.pop('total', None)
            except (urllib.error.URLError, TimeoutError, http.client.HTTPException, DownloadError) as error:
                last_error = 'checksum' if str(error) == 'checksum' else 'network'
            except OSError as error:
                if isinstance(error, ConnectionError):
                    last_error = 'network'
                else:
                    raise DownloadError('Не удалось записать модель. Проверьте свободное место и права на папку кеша.') from error
            if attempt + 1 < attempts:
                say(f'Соединение прервалось или файл повреждён. Повтор {attempt + 2} из {attempts}…')
                time.sleep(retry_delay * (attempt + 1))
            attempt += 1
        if last_error == 'checksum':
            check = 'SHA256' if expected_sha256 else 'архива'
            raise DownloadError(f'Модель не прошла проверку целостности {check}. Нажмите «Повторить»; повреждённый файл не будет использован.')
        raise DownloadError('Не удалось закончить загрузку модели. Проверьте интернет и нажмите «Повторить»: скачанная часть сохранена.')
