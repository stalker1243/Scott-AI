"""Selected STT, resumable provider cache and offline completeness; synthetic weights."""
import hashlib
import json
import sys
from pathlib import Path
from types import SimpleNamespace
import zipfile

import pytest
import recognition_models as setup
import model_setup

pytestmark = pytest.mark.unit


@pytest.fixture
def hub(tmp_path, monkeypatch):
    monkeypatch.setenv('XDG_CACHE_HOME', str(tmp_path/'cache'))
    monkeypatch.setattr(setup, 'repository', lambda name: 'Systran/faster-whisper-'+name)
    data = b'synthetic checkpoint'
    names = ['config.json', 'model.bin', 'tokenizer.json', 'vocabulary.json']
    revision = 'a'*40
    cache = tmp_path/'hub'/revision
    files = {}
    items = [SimpleNamespace(rfilename=n, size=len(data), lfs=SimpleNamespace(sha256=hashlib.sha256(data).hexdigest()) if n=='model.bin' else None,
        blob_id=hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()) for n in names]
    calls = []
    def metadata(repo, **kw):
        assert kw['timeout'] == 30 and kw['files_metadata'] is True
        calls.append('metadata')
        return SimpleNamespace(sha=revision, siblings=items)
    def download(repo, name, **kw):
        calls.append(name)
        assert kw['token'] is False and kw['revision'] == revision
        cache.mkdir(parents=True, exist_ok=True)
        path = cache/name
        path.write_bytes(data)
        files[name] = path
        return str(path)
    def cached(repo, name, **kw):
        assert kw['revision'] == revision
        return str(files[name]) if name in files else None
    module = SimpleNamespace(HfApi=lambda **kw: SimpleNamespace(model_info=metadata),
        hf_hub_download=download, try_to_load_from_cache=cached)
    monkeypatch.setitem(sys.modules, 'huggingface_hub', module)
    return SimpleNamespace(module=module, calls=calls, cache=cache, files=files, items=items)


def test_prepare_and_ready_use_same_snapshot_offline(hub):
    assert setup.prepared_faster_path('small') is None
    assert setup.prepare_faster('small', lambda *a: None) == hub.cache
    hub.calls.clear()
    hub.module.HfApi = lambda **kw: pytest.fail('Completed model must work offline')
    assert setup.prepared_faster_path('small') == hub.cache
    assert setup.prepare_faster('small', lambda *a: None) == hub.cache
    assert hub.calls == []


def test_interrupted_setup_reuses_revision_and_finished_files(hub):
    original = hub.module.hf_hub_download
    def broken(repo, name, **kw):
        if name == 'tokenizer.json':
            raise RuntimeError('synthetic interruption')
        return original(repo, name, **kw)
    hub.module.hf_hub_download = broken
    with pytest.raises(RuntimeError, match='interruption'):
        setup.prepare_faster('small', lambda *a: None)
    assert setup.prepared_faster_path('small') is None
    hub.calls.clear()
    hub.module.hf_hub_download = original
    hub.module.HfApi = lambda **kw: pytest.fail('Resume must keep pinned metadata')
    assert setup.prepare_faster('small', lambda *a: None) == hub.cache
    assert hub.calls == ['tokenizer.json', 'vocabulary.json']


def test_bad_cached_weight_is_not_ready_and_is_repaired(hub):
    setup.prepare_faster('small', lambda *a: None)
    (hub.cache/'model.bin').write_bytes(b'corrupt')
    assert setup.prepared_faster_path('small') is None
    hub.calls.clear()
    setup.prepare_faster('small', lambda *a: None)
    assert hub.calls == ['model.bin']


@pytest.mark.parametrize('change', ['path', 'revision', 'hash', 'tokenizer'])
def test_untrusted_or_incomplete_plan_is_not_ready(hub, change):
    setup.prepare_faster('small', lambda *a: None)
    receipt = setup.receipt_path('Systran/faster-whisper-small')
    plan = json.loads(receipt.read_text())
    if change == 'path':
        plan['files']['../outside'] = plan['files']['model.bin']
    elif change == 'revision':
        plan['revision'] = '../escape'
    elif change == 'hash':
        plan['files']['model.bin']['hash'] = 'bad'
    else:
        del plan['files']['tokenizer.json']
    receipt.write_text(json.dumps(plan))
    assert setup.prepared_faster_path('small') is None


@pytest.mark.parametrize('choice, device, hip, expected', [
    ('auto', 'cpu', False, 'faster'), ('faster', 'cuda', False, 'faster'),
    ('auto', 'cuda', True, 'openai'), ('faster', 'cpu', True, 'faster'),
    ('openai', 'cuda', False, 'openai'),
])
def test_setup_preserves_engine_and_amd_policy(monkeypatch, choice, device, hip, expected):
    import device_settings
    monkeypatch.setenv('WHISPER_ENGINE', choice)
    monkeypatch.setitem(sys.modules, 'faster_whisper', SimpleNamespace(WhisperModel=object))
    monkeypatch.setattr(device_settings, 'resolve_device', lambda _: device)
    monkeypatch.setattr(device_settings, 'rocm_build', lambda: hip)
    assert setup.selected_engine() == expected


def test_absent_fast_library_preserves_openai_fallback(monkeypatch):
    monkeypatch.setenv('WHISPER_ENGINE', 'faster')
    monkeypatch.setitem(sys.modules, 'faster_whisper', None)
    assert setup.selected_engine() == 'openai'


def test_faster_readiness_does_not_require_unused_pt_weight(hub, tmp_path, monkeypatch):
    setup.prepare_faster('small', lambda *a: None)
    monkeypatch.setattr(setup, 'selected_engine', lambda: 'faster')
    monkeypatch.setattr(model_setup, 'whisper_spec', lambda: pytest.fail('No unused OpenAI weight'))
    repo = tmp_path/'silero'; voice = repo/'src/silero/model/v4_ru.pt'
    voice.parent.mkdir(parents=True)
    with zipfile.ZipFile(voice, 'w') as archive:
        archive.writestr('archive/tts_models/model', b'synthetic')
    assert model_setup.models_ready() is True
    (hub.cache/'tokenizer.json').unlink()
    assert model_setup.models_ready() is False


def test_byte_progress_accounts_for_resumed_bytes_without_terminal_output(capsys):
    updates = []
    progress = setup.transfer_progress('model.bin', 4*1024**2, 1024**2, 5*1024**2, lambda *event: updates.append(event))
    with progress(total=4*1024**2, initial=2*1024**2) as bar:
        bar.update(2*1024**2)
    assert updates[-1][0] == 'model.bin: 4.0 / 4.0 МиБ'
    assert updates[-1][1] == pytest.approx(.9)
    assert capsys.readouterr().err == ''
