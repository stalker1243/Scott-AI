"""Pinned PyTorch wheels: bounded range requests, durable resume and final SHA256.

The application selects four qualified CPython 3.13 x86-64 CPU/CUDA wheels.
Other platforms retain the ordinary pip path; no package is executed here.
"""
from __future__ import annotations

from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from dataclasses import dataclass
import hashlib
import http.client
import json
import os
from pathlib import Path
import platform
import re
import stat
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

try:
    from .model_download import DownloadError, _lock, checksum, download_file
except ImportError:
    from model_download import DownloadError, _lock, checksum, download_file


@dataclass(frozen=True)
class Wheel:
    filename: str
    size: int
    sha256: str
    channel: str

    @property
    def urls(self):
        suffix='/whl/'+self.channel+'/'+urllib.parse.quote(self.filename, safe='-_.')
        return tuple('https://'+host+suffix for host in ('download.pytorch.org','download-r2.pytorch.org'))


WHEELS={
    ('win32','cpu'):Wheel('torch-2.14.1+cpu-cp313-cp313-win_amd64.whl',123995848,
        '4eec5a4fadd7a18f9c75b97fdb374fbb579ce4b1604bf66eeb14dc2201d54def','cpu'),
    ('linux','cpu'):Wheel('torch-2.14.1+cpu-cp313-cp313-manylinux_2_28_x86_64.whl',196253851,
        '331fa474e26e428e2e6af1143b2fdab19cee492d7d21897b8899ce1c14755662','cpu'),
    ('win32','cuda'):Wheel('torch-2.14.1+cu126-cp313-cp313-win_amd64.whl',2602769784,
        '92d0ae66f10ae9dfaaf85d684d6794a3d6ca4ed938dcfaa25e94c54cff3764eb','cu126'),
    ('linux','cuda'):Wheel('torch-2.14.1+cu126-cp313-cp313-manylinux_2_28_x86_64.whl',869172663,
        '049cc7f36a5bc6f0f9c1e96ed5076f7b634d638a817b00bb1d882f3e172d3147','cu126'),
}
CHUNK=8*1024*1024


def selected(backend):
    if sys.implementation.name!='cpython' or sys.version_info[:2]!=(3,13) or platform.machine().lower() not in ('amd64','x86_64'):
        return None
    return WHEELS.get((sys.platform,backend))


def _safe(path):
    path=Path(path).absolute()
    for item in (path,*path.parents):
        if item.is_symlink() or item.is_junction():
            raise DownloadError('Папка загрузки содержит перенаправление. Выберите другую папку установки.')
    try:
        info=path.stat()
    except FileNotFoundError:
        return
    if stat.S_ISREG(info.st_mode) and info.st_nlink!=1:
        raise DownloadError('Файл загрузки связан с другим файлом. Выберите другую папку установки.')
    if not stat.S_ISREG(info.st_mode) and not stat.S_ISDIR(info.st_mode):
        raise DownloadError('Неверный тип файла загрузки.')


def _folder(directory):
    directory=Path(directory).absolute();_safe(directory)
    directory.mkdir(parents=True,exist_ok=True,mode=0o700);_safe(directory)
    if os.name!='nt':
        info=directory.stat()
        if info.st_uid!=os.getuid():
            raise DownloadError('Папка загрузки принадлежит другому пользователю.')
        os.chmod(directory,0o700)
    return directory


def _file(path,mode):
    _safe(path)
    flags={'rb':os.O_RDONLY,'r+b':os.O_RDWR,'wb':os.O_WRONLY|os.O_CREAT}[mode]
    descriptor=os.open(path,flags|getattr(os,'O_BINARY',0)|getattr(os,'O_NOFOLLOW',0)|getattr(os,'O_NONBLOCK',0),0o600)
    info=os.fstat(descriptor)
    if not stat.S_ISREG(info.st_mode) or info.st_nlink!=1:
        os.close(descriptor);raise DownloadError('Неверный файл загрузки.')
    stream=os.fdopen(descriptor,mode)
    # O_TRUNC would modify a raced hard link before fstat can reject it.
    if mode=='wb':stream.truncate(0)
    return stream


def _unlink(path):
    _safe(path);path.unlink(missing_ok=True)


class _NoRange(Exception):
    pass


def fetch(wheel,directory,*,progress=None,cancelled=None,timeout=30,attempts=3,deadline=3600,workers=4):
    """Return a verified wheel. Keep completed chunks after cancellation/failure."""
    if not isinstance(wheel,Wheel) or Path(wheel.filename).name!=wheel.filename or not wheel.filename.endswith('.whl') \
            or not re.fullmatch('[0-9a-f]{64}',wheel.sha256) or wheel.size<=0:
        raise ValueError('Invalid wheel specification')
    if not 1<=workers<=4 or not 1<=attempts<=5 or timeout<=0 or deadline<=0:
        raise ValueError('Invalid download budget')
    directory=_folder(directory);target=directory/wheel.filename
    part=target.with_name(target.name+'.ranges')
    ledger=target.with_name(target.name+'.ranges.json')
    pending=ledger.with_suffix('.tmp')
    lock=target.with_name(target.name+'.ranges.lock')
    for path in (target,part,ledger,pending,lock,*[target.with_name(target.name+suffix) for suffix in ('.part','.part.json','.part.json.tmp','.download.lock')]):
        _safe(path)
        if path.exists() and not path.is_file():raise DownloadError('Вместо файла загрузки находится папка.')
    started=time.monotonic();abort=threading.Event();mutex=threading.Lock()
    def check():
        if cancelled is not None and cancelled.is_set():raise DownloadError('Загрузка отменена. Скачанная часть сохранена.')
        if abort.is_set():raise DownloadError('Загрузка приостановлена. Скачанная часть сохранена.')
        if time.monotonic()-started>deadline:raise DownloadError('Истекло время загрузки. Повторите: скачанная часть сохранена.')
    def valid(path):
        return path.is_file() and path.stat().st_size==wheel.size and checksum(path)==wheel.sha256
    with _lock(lock):
        check()
        if valid(target):
            if progress:progress(wheel.size,wheel.size)
            return target
        identity=dict(sha256=wheel.sha256,size=wheel.size,chunk=CHUNK)
        count=(wheel.size+CHUNK-1)//CHUNK
        saved={}
        try:
            if ledger.stat().st_size<=4*1024*1024:
                with _file(ledger,'rb') as stream:saved=json.load(stream)
        except (FileNotFoundError,ValueError,TypeError):pass
        completed=saved.get('completed',{}) if isinstance(saved,dict) and saved.get('identity')==identity else {}
        if not isinstance(completed,dict):completed={}
        if not part.is_file() or part.stat().st_size!=wheel.size:
            with _file(part,'wb') as stream:stream.truncate(wheel.size)
            completed={}
        # Validate resumable chunks themselves; the ledger is never trusted as a hash bypass.
        with _file(part,'rb') as stream:
            for key,value in list(completed.items()):
                if not re.fullmatch(r'0|[1-9][0-9]{0,7}',key) or not 0<=int(key)<count or not isinstance(value,str):
                    completed.pop(key);continue
                index=int(key);stream.seek(index*CHUNK)
                if hashlib.sha256(stream.read(min(CHUNK,wheel.size-index*CHUNK))).hexdigest()!=value:
                    completed.pop(key)
        def save():
            with _file(pending,'wb') as stream:
                stream.write(json.dumps(dict(identity=identity,completed=completed),sort_keys=True).encode())
                stream.flush();os.fsync(stream.fileno())
            _safe(ledger);os.replace(pending,ledger)
        active={}
        def report():
            if progress:
                done=sum(min(CHUNK,wheel.size-int(key)*CHUNK) for key in completed)+sum(active.values())
                progress(min(done,wheel.size),wheel.size)
        save();report()
        def chunk(index):
            begin=index*CHUNK;end=min(wheel.size,begin+CHUNK)-1;length=end-begin+1
            for attempt in range(attempts):
                check()
                try:
                    request=urllib.request.Request(wheel.urls[attempt%len(wheel.urls)],headers={
                        'Range':f'bytes={begin}-{end}','Accept-Encoding':'identity','User-Agent':'ScottAI-setup'})
                    with urllib.request.urlopen(request,timeout=timeout) as response:
                        final=urllib.parse.urlsplit(response.geturl())
                        if final.scheme!='https' or final.hostname not in ('download.pytorch.org','download-r2.pytorch.org'):
                            raise DownloadError('Неверный сервер загрузки PyTorch.')
                        if response.status==200:raise _NoRange()
                        if response.status!=206 or response.headers.get('Content-Range')!=f'bytes {begin}-{end}/{wheel.size}' \
                                or response.headers.get('Content-Encoding','identity')!='identity':
                            raise DownloadError('Сервер вернул неверный диапазон файла.')
                        declared=response.headers.get('Content-Length')
                        if declared is not None and declared!=str(length):raise DownloadError('Неверная длина загрузки.')
                        digest=hashlib.sha256();received=0
                        with _file(part,'r+b') as stream:
                            stream.seek(begin)
                            while True:
                                check();block=response.read(min(256*1024,length-received+1))
                                if not block:break
                                if received+len(block)>length:raise DownloadError('Лишние данные в диапазоне загрузки.')
                                stream.write(block);digest.update(block);received+=len(block)
                                with mutex:active[index]=received;report()
                            if received!=length:raise DownloadError('Соединение прервалось во время загрузки.')
                            stream.flush();os.fsync(stream.fileno())
                        with mutex:
                            completed[str(index)]=digest.hexdigest();active.pop(index,None);save();report()
                        return
                except _NoRange:raise
                except (urllib.error.URLError,http.client.HTTPException,TimeoutError,ConnectionError,DownloadError):
                    with mutex:active.pop(index,None)
                    if attempt+1==attempts:raise DownloadError('Не удалось закончить загрузку PyTorch. Повторите: скачанная часть сохранена.') from None
                    if abort.wait(min(2,attempt+1)):check()
        missing=iter(index for index in range(count) if str(index) not in completed)
        pool=ThreadPoolExecutor(max_workers=workers,thread_name_prefix='scott-package')
        futures=set();fallback=False
        try:
            for _ in range(workers):
                index=next(missing,None)
                if index is not None:futures.add(pool.submit(chunk,index))
            while futures:
                check();done,futures=wait(futures,timeout=.2,return_when=FIRST_COMPLETED)
                for future in done:
                    future.result()
                    index=next(missing,None)
                    if index is not None:futures.add(pool.submit(chunk,index))
        except _NoRange:
            fallback=True
        finally:
            abort.set()
            for future in futures:future.cancel()
            pool.shutdown(wait=True,cancel_futures=True)
        # Workers have settled before the sequential fallback or publication.
        abort.clear();check()
        if fallback:
            def transfer(done,total):
                check()
                if progress:progress(done,total or wheel.size)
            download_file(wheel.urls[0],target,expected_sha256=wheel.sha256,progress=transfer,
                          attempts=attempts,timeout=timeout)
        elif not valid(part):
            completed.clear();save()
            raise DownloadError('PyTorch не прошёл проверку SHA256. Повреждённый файл не будет установлен; повторите загрузку.')
        else:
            _safe(target);os.replace(part,target)
        if not valid(target):raise DownloadError('PyTorch не прошёл проверку SHA256.')
        for path in (part,ledger,pending):_unlink(path)
        if progress:progress(wheel.size,wheel.size)
        return target


def discard(wheel,directory):
    """Remove only this verified download after pip has installed it successfully."""
    target=Path(directory)/wheel.filename;_safe(target)
    if target.is_file() and target.stat().st_size==wheel.size and checksum(target)==wheel.sha256:
        _unlink(target)
