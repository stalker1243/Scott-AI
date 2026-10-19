"""Owned fixtures only: no real Torch, pip, GPU or user runtime mutations."""
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
import voice_shared_runtime as shared
import scott_voice_engine as engine
import scott_voice_process as client

pytestmark = pytest.mark.unit


@pytest.fixture
def app(tmp_path, monkeypatch):
    root = tmp_path/'application'
    site = root/'runtime/Lib/site-packages'
    metadata = site/f'torch-{shared.TORCH}.dist-info'
    metadata.mkdir(parents=True)
    (metadata/'METADATA').write_text('Name: torch\nVersion: '+shared.TORCH+'\n')
    (metadata/'WHEEL').write_text('Tag: cp313-cp313-win_amd64\n')
    (metadata/'RECORD').write_text('pinned wheel contents')
    (site/'torch').mkdir()
    (site/'torch/__init__.py').write_text('fixture')
    (root/'runtime/python.exe').write_bytes(b'fixture')
    home = root/'voice-runtime'
    shared.site_path(home).mkdir(parents=True)
    # Exercise the Windows layout on Linux without changing global os.name.
    monkeypatch.setattr(shared, 'candidate', lambda home, root:
        None if (shared.site_path(home)/'torch').exists() else shared._base(root))
    return root, home, metadata


def probe(root, **changes):
    info = dict(python=[3, 13], bits=64, version=shared.TORCH, cuda=True,
                path=str(root/'runtime/Lib/site-packages/torch/__init__.py'))
    info.update(changes)
    return lambda *a, **k: SimpleNamespace(stdout=json.dumps(info))


def test_fresh_binding_is_relative_private_and_preserves_base(app):
    root, home, metadata = app
    original = (metadata/'RECORD').read_bytes()
    assert shared.configure(home, root, run=probe(root))
    assert shared.fingerprint(home) == shared._base(root)['base_sha256']
    hook = (shared.site_path(home)/shared.HOOK).read_text()
    assert hook.startswith(shared.HEADER) and str(root) not in hook
    assert (shared.site_path(home)/hook.splitlines()[1]).resolve() == root/'runtime/Lib/site-packages'
    assert not (shared.site_path(home)/'torch').exists()
    assert (metadata/'RECORD').read_bytes() == original


def test_existing_independent_torch_is_never_converted(app):
    root, home, _ = app
    torch = shared.site_path(home)/'torch'
    torch.mkdir()
    (torch/'user-file').write_bytes(b'keep')
    assert not shared.configure(home, root, run=lambda *a, **k: pytest.fail('No probe for independent runtime'))
    assert not (home/shared.MANIFEST).exists()
    assert (torch/'user-file').read_bytes() == b'keep'


@pytest.mark.parametrize('changes', [dict(cuda=False), dict(bits=32), dict(python=[3, 12]),
    dict(version='2.10.0'), dict(path='C:/unrelated/torch/__init__.py')])
def test_incompatible_base_uses_independent_install(app, changes):
    root, home, _ = app
    assert not shared.configure(home, root, run=probe(root, **changes))
    assert not (home/shared.MANIFEST).exists()
    assert not (shared.site_path(home)/shared.HOOK).exists()


def test_updated_base_invalidates_ready_even_with_cached_probe(app, monkeypatch):
    root, home, metadata = app
    assert shared.configure(home, root, run=probe(root))
    config = SimpleNamespace(worker=home/'experiments/voice_design/voice_worker.py')
    calls = []
    monkeypatch.setattr(engine, '_inspect_installation', lambda config,*ignored: calls.append(True) or '')
    assert engine.inspect_installation(config) == ''
    (metadata/'RECORD').write_text('new wheel')
    assert engine.inspect_installation(config) == 'runtime_update_required'
    assert calls == [True]
    # Repair detaches only the recognized binding and never edits base files.
    assert not shared.configure(home, root, run=lambda *a, **k: pytest.fail('Changed base is not reused on repair'))
    assert not (shared.site_path(home)/shared.HOOK).exists()
    assert not (home/shared.MANIFEST).exists()
    assert (metadata/'RECORD').read_text() == 'new wheel'


def test_changes_to_another_inherited_dependency_also_invalidate_binding(app):
    root, home, _ = app
    assert shared.configure(home, root, run=probe(root))
    metadata = root/'runtime/Lib/site-packages/numpy-2.3.4.dist-info'
    metadata.mkdir()
    (metadata/'METADATA').write_text('Name: numpy\nVersion: 2.3.4\n')
    with pytest.raises(shared.SharedRuntimeError):
        shared.fingerprint(home)
    assert not shared.configure(home, root)


def test_legacy_binding_is_reverified_before_metadata_fingerprint_upgrade(app):
    root, home, _ = app
    assert shared.configure(home, root, run=probe(root))
    marker = home/shared.MANIFEST
    value = json.loads(marker.read_text())
    value.pop('base_sha256')
    marker.write_text(json.dumps(value))
    with pytest.raises(shared.SharedRuntimeError):
        shared.fingerprint(home)
    assert shared.configure(home, root, run=probe(root))
    assert shared.fingerprint(home)


def test_worker_start_rechecks_base_before_spawning(app, monkeypatch):
    root, home, metadata = app
    assert shared.configure(home, root, run=probe(root))
    voice = object.__new__(client.ScottVoiceProcess)
    voice.config = SimpleNamespace(worker=home/'experiments/voice_design/voice_worker.py')
    (metadata/'RECORD').unlink()
    with pytest.raises(client.VoiceProcessError) as caught:
        voice._start(0)
    assert caught.value.code == 'runtime_update_required'


def test_interrupted_hook_commit_is_recoverable(app, monkeypatch):
    root, home, _ = app
    write = shared._write
    def fail_hook(path, text):
        if Path(path).name == shared.HOOK:
            raise OSError('interrupted')
        return write(path, text)
    monkeypatch.setattr(shared, '_write', fail_hook)
    with pytest.raises(OSError):
        shared.configure(home, root, run=probe(root))
    with pytest.raises(shared.SharedRuntimeError):
        shared.fingerprint(home)
    monkeypatch.setattr(shared, '_write', write)
    assert shared.configure(home, root, run=probe(root))
    assert shared.fingerprint(home)


@pytest.mark.parametrize('modified', ['hook', 'manifest', 'unknown_hook'])
def test_unknown_or_modified_binding_is_preserved(app, modified):
    root, home, _ = app
    assert shared.configure(home, root, run=probe(root))
    if modified == 'hook':
        path = shared.site_path(home)/shared.HOOK
        path.write_bytes(b'import custom_hook\n')
    elif modified == 'manifest':
        path = home/shared.MANIFEST
        path.write_bytes(b'unknown manifest')
    else:
        (home/shared.MANIFEST).unlink()
        path = shared.site_path(home)/shared.HOOK
    before = path.read_bytes()
    with pytest.raises(shared.SharedRuntimeError):
        shared.configure(home, root, run=probe(root))
    assert path.read_bytes() == before


def test_missing_base_detaches_only_owned_files_and_keeps_models(app):
    root, home, metadata = app
    assert shared.configure(home, root, run=probe(root))
    model = home/'experiments/voice_design/models/base/model.safetensors'
    model.parent.mkdir(parents=True)
    model.write_bytes(b'accepted weights')
    extra = shared.site_path(home)/'unrelated.pth'
    extra.write_text('custom-library\n')
    (metadata/'METADATA').unlink()
    assert not shared.configure(home, root)
    assert model.read_bytes() == b'accepted weights'
    assert extra.read_text() == 'custom-library\n'


def test_old_featureless_runtime_and_arbitrary_test_worker_need_no_binding(tmp_path):
    assert shared.fingerprint(tmp_path) is None
    assert shared.config_fingerprint(SimpleNamespace(worker=tmp_path/'fixture.py')) is None


def test_application_move_retains_relative_binding(app, tmp_path):
    root, home, _ = app
    assert shared.configure(home, root, run=probe(root))
    destination = tmp_path/'moved'
    root.rename(destination)
    assert shared.fingerprint(destination/'voice-runtime')


def test_source_symlink_is_not_a_shareable_owned_dependency(app, tmp_path):
    root, home, metadata = app
    target = root/'runtime/Lib/site-packages/torch'
    moved = tmp_path/'external-torch'
    target.rename(moved)
    try:
        target.symlink_to(moved, target_is_directory=True)
    except OSError:
        pytest.skip('symlinks unavailable')
    assert shared._base(root) is None


def test_known_old_torch_binding_can_be_repaired_to_qualified_base(app):
    root,home,_=app
    assert shared.configure(home,root,run=probe(root))
    marker=home/shared.MANIFEST
    value=json.loads(marker.read_text());value.update(torch='2.9.1+cu126',record_sha256='a'*64,base_sha256='b'*64)
    marker.write_text(json.dumps(value))
    with pytest.raises(shared.SharedRuntimeError):shared.fingerprint(home)
    assert shared.configure(home,root,run=probe(root))
    assert json.loads(marker.read_text())['torch']==shared.TORCH and shared.fingerprint(home)


def test_known_old_binding_detaches_when_no_qualified_base_exists(app):
    root,home,metadata=app
    assert shared.configure(home,root,run=probe(root))
    marker=home/shared.MANIFEST;value=json.loads(marker.read_text());value['torch']='2.9.1+cu126';marker.write_text(json.dumps(value))
    (metadata/'METADATA').unlink()
    assert not shared.configure(home,root,run=lambda *a,**k:pytest.fail('Missing base must not be executed'))
    assert not marker.exists() and not (shared.site_path(home)/shared.HOOK).exists()


def test_independent_package_upgrade_changes_audio_identity(tmp_path):
    site=tmp_path/'.venv/Lib/site-packages/qwen_tts-0.1.1.dist-info'
    site.mkdir(parents=True)
    metadata=site/'METADATA';metadata.write_text('Name: qwen-tts\nVersion: 0.1.1\n')
    config=SimpleNamespace(worker=tmp_path/'fixture.py',python=tmp_path/'.venv/Scripts/python.exe')
    before=shared.config_fingerprint(config)
    metadata.write_text('Name: qwen-tts\nVersion: 0.1.1+scott.1\n')
    assert before and before!=shared.config_fingerprint(config)

