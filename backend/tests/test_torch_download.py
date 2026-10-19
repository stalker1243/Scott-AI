"""Owned HTTP fixtures: real ranges, interrupted resume, hashes and path guards."""
from contextlib import contextmanager
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import re
import threading
import urllib.request

import pytest
import torch_download as downloads

pytestmark=pytest.mark.unit


@contextmanager
def server(monkeypatch,*,ignore_ranges=False,bad_range=False,corrupt=False,failed=None):
    content=bytes(range(251))*19
    seen=[]
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def do_GET(self):
            match=re.fullmatch(r'bytes=(\d+)-(\d+)',self.headers.get('Range',''))
            start,end=map(int,match.groups()) if match else (0,len(content)-1)
            seen.append((start,end))
            if failed and failed(start):
                self.send_error(503);return
            ranged=bool(match) and not ignore_ranges
            data=content[start:end+1] if ranged else content
            if corrupt:data=b'x'*len(data)
            self.send_response(206 if ranged else 200)
            if ranged:self.send_header('Content-Range',f'bytes {start+int(bad_range)}-{end}/{len(content)}')
            self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)
    http=ThreadingHTTPServer(('127.0.0.1',0),Handler)
    worker=threading.Thread(target=http.serve_forever,daemon=True);worker.start()
    original=urllib.request.urlopen
    class Response:
        def __init__(self,response,url):self.response=response;self.url=url
        def __enter__(self):return self
        def __exit__(self,*args):self.response.close()
        def geturl(self):return self.url
        def __getattr__(self,name):return getattr(self.response,name)
    def open_request(request,timeout):
        url=request.full_url if hasattr(request,'full_url') else request
        local=urllib.request.Request(f'http://127.0.0.1:{http.server_port}/wheel',
            headers=dict(request.header_items()) if hasattr(request,'header_items') else {})
        return Response(original(local,timeout=timeout),url)
    monkeypatch.setattr(downloads.urllib.request,'urlopen',open_request)
    monkeypatch.setattr(downloads,'CHUNK',1024)
    wheel=downloads.Wheel('torch-fixture.whl',len(content),hashlib.sha256(content).hexdigest(),'cpu')
    try:yield wheel,content,seen
    finally:http.shutdown();http.server_close();worker.join(timeout=3)


def test_parallel_ranges_publish_only_complete_verified_file(tmp_path,monkeypatch):
    with server(monkeypatch) as (wheel,content,seen):
        changes=[]
        target=downloads.fetch(wheel,tmp_path/'cache',progress=lambda done,total:changes.append((done,total)))
        assert target.read_bytes()==content
        assert len(seen)==5 and all(end-start+1<=1024 for start,end in seen)
        assert changes[-1]==(len(content),len(content))
        assert not target.with_name(target.name+'.ranges').exists()
        assert downloads.fetch(wheel,target.parent)==target and len(seen)==5
        downloads.discard(wheel,target.parent)
        assert not target.exists()


def test_resume_reuses_completed_chunks_and_detects_local_tampering(tmp_path,monkeypatch):
    fail=[True]
    with server(monkeypatch,failed=lambda start:fail[0] and start>=2048) as (wheel,content,seen):
        cache=tmp_path/'cache'
        with pytest.raises(downloads.DownloadError):downloads.fetch(wheel,cache,attempts=1,workers=1)
        ledger=cache/(wheel.filename+'.ranges.json');part=cache/(wheel.filename+'.ranges')
        assert set(json.loads(ledger.read_text())['completed'])=={'0','1'}
        with part.open('r+b') as stream:stream.seek(1024);stream.write(b'bad')
        seen.clear();fail[0]=False
        assert downloads.fetch(wheel,cache,workers=2).read_bytes()==content
        assert (0,1023) not in seen and (1024,2047) in seen


@pytest.mark.parametrize('option',['bad_range','corrupt'])
def test_bad_server_data_is_never_published(tmp_path,monkeypatch,option):
    with server(monkeypatch,**{option:True}) as (wheel,_,_):
        with pytest.raises(downloads.DownloadError):downloads.fetch(wheel,tmp_path/'cache',attempts=1)
        assert not (tmp_path/'cache'/wheel.filename).exists()


def test_ignored_ranges_fall_back_to_verified_sequential_download(tmp_path,monkeypatch):
    with server(monkeypatch,ignore_ranges=True) as (wheel,content,_):
        assert downloads.fetch(wheel,tmp_path/'cache').read_bytes()==content


def test_cancelled_request_keeps_chunks_for_next_run(tmp_path,monkeypatch):
    with server(monkeypatch) as (wheel,content,_):
        event=threading.Event();cache=tmp_path/'cache'
        def progress(done,total):
            ledger=cache/(wheel.filename+'.ranges.json')
            if ledger.exists() and json.loads(ledger.read_text()).get('completed'):event.set()
        with pytest.raises(downloads.DownloadError):downloads.fetch(wheel,cache,cancelled=event,progress=progress,workers=1)
        assert not (cache/wheel.filename).exists()
        assert json.loads((cache/(wheel.filename+'.ranges.json')).read_text())['completed']
        assert downloads.fetch(wheel,cache).read_bytes()==content


def test_redirected_cache_and_hardlinked_partial_are_preserved(tmp_path,monkeypatch):
    import os
    with server(monkeypatch) as (wheel,_,seen):
        cache=tmp_path/'cache';cache.mkdir()
        other=tmp_path/'other';other.write_bytes(b'keep')
        partial=cache/(wheel.filename+'.ranges')
        os.link(other,partial)
        with pytest.raises(downloads.DownloadError):downloads.fetch(wheel,cache)
        assert other.read_bytes()==b'keep' and not seen


def test_symlink_cache_is_rejected(tmp_path,monkeypatch):
    with server(monkeypatch) as (wheel,_,seen):
        other=tmp_path/'other';other.mkdir();cache=tmp_path/'cache'
        try:cache.symlink_to(other,target_is_directory=True)
        except OSError:pytest.skip('Symlinks unavailable')
        with pytest.raises(downloads.DownloadError):downloads.fetch(wheel,cache)
        assert not seen and not list(other.iterdir())


def test_concurrent_same_wheel_does_not_bypass_lock(tmp_path,monkeypatch):
    with server(monkeypatch) as (wheel,_,seen):
        cache=tmp_path/'cache';cache.mkdir()
        with downloads._lock(cache/(wheel.filename+'.ranges.lock')):
            with pytest.raises(downloads.DownloadError):downloads.fetch(wheel,cache)
        assert not seen


def test_unknown_platform_falls_back_to_pip(monkeypatch):
    monkeypatch.setattr(downloads.platform,'machine',lambda:'aarch64')
    assert downloads.selected('cuda') is None


def test_descriptor_is_verified_before_any_truncation(tmp_path,monkeypatch):
    import os
    other=tmp_path/'other';other.write_bytes(b'must survive')
    path=tmp_path/'partial';os.link(other,path)
    # Simulate a link swapped after the first path check. fstat must still
    # reject it before an output open can truncate the shared inode.
    monkeypatch.setattr(downloads,'_safe',lambda path:None)
    with pytest.raises(downloads.DownloadError):downloads._file(path,'wb')
    assert other.read_bytes()==b'must survive'
