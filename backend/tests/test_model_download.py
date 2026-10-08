"""Exercise real HTTP interruption/range behavior without model weights or user caches."""
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import socket
import subprocess
import sys
import threading
from types import SimpleNamespace
import zipfile

import pytest

from model_download import download_file, DownloadError

pytestmark = pytest.mark.unit
DATA = bytes(range(256)) * 2400
DIGEST = hashlib.sha256(DATA).hexdigest()


@pytest.fixture
def server():
    state = {'requests': [], 'mode': 'normal'}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            requested = self.headers.get('Range')
            state['requests'].append(requested)
            mode = state['mode']
            start = int(requested.split('=')[1].split('-')[0]) if requested else 0
            if mode == 'ignore':
                start = 0
            end = min(len(DATA), start + 65536) if mode == 'segments' else len(DATA)
            payload = DATA[start:end]
            if mode == 'corrupt':
                payload = b'x' * len(payload)
            code = 206 if requested and mode != 'ignore' or mode == 'segments' else 200
            self.send_response(code)
            self.send_header('Content-Length', str(len(payload)))
            self.send_header('ETag', '0x8DA9AC839BB55FC' if state.get('unquoted_etag') else '"model-v1"')
            state['if_range'] = self.headers.get('If-Range')
            if code == 206:
                begin = start + 1 if mode == 'bad-range' else start
                self.send_header('Content-Range', f'bytes {begin}-{end - 1}/{len(DATA)}')
            self.end_headers()
            if mode == 'cut' and len(state['requests']) == 1:
                self.wfile.write(payload[:32768])
                self.wfile.flush()
                self.connection.shutdown(socket.SHUT_RDWR)
                self.connection.close()
            else:
                self.wfile.write(payload)

    http = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    worker = threading.Thread(target=http.serve_forever, daemon=True)
    worker.start()
    yield f'http://127.0.0.1:{http.server_port}/model.pt', state
    http.shutdown()
    http.server_close()
    worker.join()


def partial(target, url, data):
    target.with_name(target.name + '.part').write_bytes(data)
    target.with_name(target.name + '.part.json').write_text(json.dumps({
        'identity': {'url': url, 'sha256': DIGEST}, 'total': len(DATA), 'etag': '"model-v1"'}))


def test_interrupted_response_resumes_and_verifies(server, tmp_path):
    url, state = server
    state['mode'] = 'cut'
    target = tmp_path / 'model.pt'
    samples = []
    download_file(url, target, expected_sha256=DIGEST, retry_delay=0, progress=lambda a, b: samples.append((a, b)))
    assert target.read_bytes() == DATA
    assert state['requests'] == [None, 'bytes=32768-']
    assert samples[-1] == (len(DATA), len(DATA))
    assert not target.with_name('model.pt.part').exists()


@pytest.mark.parametrize('mode', ['normal', 'ignore', 'segments'])
def test_saved_partial_handles_range_and_servers_ignoring_it(server, tmp_path, mode):
    url, state = server
    state['mode'] = mode
    target = tmp_path / 'model.pt'
    partial(target, url, DATA[:1024])
    download_file(url, target, expected_sha256=DIGEST, retry_delay=0)
    assert target.read_bytes() == DATA
    assert state['requests'][0] == 'bytes=1024-'


def test_wrong_range_never_appends_or_replaces_existing_file(server, tmp_path):
    url, state = server
    state['mode'] = 'bad-range'
    target = tmp_path / 'model.pt'
    target.write_bytes(b'original')
    partial(target, url, DATA[:1024])
    with pytest.raises(DownloadError):
        download_file(url, target, expected_sha256=DIGEST, attempts=2, retry_delay=0)
    assert target.read_bytes() == b'original'
    assert target.with_name('model.pt.part').read_bytes() == DATA[:1024]


def test_bad_hash_has_bounded_retries_and_preserves_original(server, tmp_path):
    url, state = server
    state['mode'] = 'corrupt'
    target = tmp_path / 'model.pt'
    target.write_bytes(b'original')
    with pytest.raises(DownloadError, match='SHA256'):
        download_file(url, target, expected_sha256=DIGEST, attempts=3, retry_delay=0)
    assert target.read_bytes() == b'original'
    assert len(state['requests']) == 3
    assert not target.with_name('model.pt.part').exists()


def test_valid_target_uses_no_network(server, tmp_path):
    url, state = server
    target = tmp_path / 'model.pt'
    target.write_bytes(DATA)
    download_file(url, target, expected_sha256=DIGEST)
    assert not state['requests']


def test_interruption_keeps_partial_for_next_run(server, tmp_path):
    url, state = server
    target = tmp_path / 'model.pt'

    def stop(done, total):
        if done > 0:
            raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        download_file(url, target, expected_sha256=DIGEST, progress=stop)
    assert not target.exists()
    size = target.with_name('model.pt.part').stat().st_size
    assert 0 < size < len(DATA)
    download_file(url, target, expected_sha256=DIGEST)
    assert state['requests'][-1] == f'bytes={size}-'
    assert target.read_bytes() == DATA


def test_complete_partial_is_verified_without_request(server, tmp_path):
    url, state = server
    target = tmp_path / 'model.pt'
    partial(target, url, DATA)
    download_file(url, target, expected_sha256=DIGEST)
    assert target.read_bytes() == DATA
    assert not state['requests']


def test_unquoted_cdn_etag_is_not_sent_as_if_range(server, tmp_path):
    url, state = server
    state['unquoted_etag'] = True
    target = tmp_path / 'model.pt'
    partial(target, url, DATA[:1024])
    metadata = target.with_name('model.pt.part.json')
    saved = json.loads(metadata.read_text())
    saved['etag'] = '0x8DA9AC839BB55FC'
    metadata.write_text(json.dumps(saved))
    download_file(url, target, expected_sha256=DIGEST)
    assert target.read_bytes() == DATA
    assert state['requests'] == ['bytes=1024-']
    assert state['if_range'] is None


def test_stream_process_deadline_covers_silent_child():
    import bootstrap
    with pytest.raises(subprocess.TimeoutExpired):
        bootstrap._stream_process([sys.executable, '-u', '-c', 'import time; time.sleep(30)'], lambda line: None, .3)


def test_model_retry_skips_pip(monkeypatch):
    import bootstrap
    monkeypatch.setattr(bootstrap, 'is_ready', lambda python=None: False)
    monkeypatch.setattr(bootstrap, 'dependencies_ready', lambda python=None: True)
    monkeypatch.setattr(bootstrap, 'install_dependencies', lambda *args: pytest.fail('pip must not run again'))
    monkeypatch.setattr(bootstrap, 'download_models', lambda *args: bootstrap.Step('Models', done=True))
    assert bootstrap.prepare().done


def test_download_worker_relays_json_including_friendly_error(monkeypatch):
    import bootstrap
    def fake_stream(command, consume, timeout, **kwargs):
        assert '--models' in command
        consume('an unrelated hub line')
        consume(json.dumps({'type': 'progress', 'message': 'Whisper: 10 MB', 'fraction': .8}))
        consume(json.dumps({'type': 'error', 'message': 'Try again'}))
        return 1
    monkeypatch.setattr(bootstrap, '_stream_process', fake_stream)
    messages = []
    result = bootstrap.download_models(progress=lambda msg, value: messages.append(msg))
    assert not result.done and result.error == 'Try again'
    assert 'Whisper: 10 MB' in messages


@pytest.mark.parametrize('name', ['small', 'turbo'])
def test_model_manifest_respects_choice_and_xdg_cache(tmp_path, monkeypatch, name):
    import model_setup
    source = tmp_path / 'whisper_init.py'
    source.write_text('_MODELS = ' + repr({n: f'https://example.com/{DIGEST}/{n}.pt' for n in ('small', 'large-v3-turbo')}))
    monkeypatch.setattr(model_setup.importlib.util, 'find_spec', lambda _: SimpleNamespace(origin=str(source)))
    monkeypatch.setattr(model_setup, '__file__', str(tmp_path / 'backend/model_setup.py'))
    monkeypatch.setenv('WHISPER_MODEL', name)
    monkeypatch.setenv('XDG_CACHE_HOME', str(tmp_path / 'cache'))
    selected = 'large-v3-turbo' if name == 'turbo' else name
    target, url, digest = model_setup.whisper_spec()
    assert target == tmp_path / 'cache/whisper' / (selected + '.pt')
    assert digest == DIGEST
    local = tmp_path / 'backend/data/models/whisper' / (selected + '.pt')
    local.parent.mkdir(parents=True)
    local.write_bytes(b'existing model')
    assert model_setup.whisper_spec()[0] == local


def test_readiness_rejects_valid_zip_without_silero_model(tmp_path, monkeypatch):
    import model_setup
    whisper = tmp_path / 'small.pt'
    whisper.write_bytes(DATA)
    repo = tmp_path / 'repo'
    voice = repo / 'src/silero/model/v4_ru.pt'
    voice.parent.mkdir(parents=True)
    with zipfile.ZipFile(voice, 'w') as archive:
        archive.writestr('unrelated', b'data')
    monkeypatch.setattr(model_setup, 'whisper_spec', lambda: (whisper, 'url', DIGEST))
    monkeypatch.setattr(model_setup, 'silero_repo', lambda: repo)
    assert not model_setup.models_ready()
