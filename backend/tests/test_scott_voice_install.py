"""Optional provisioning uses synthetic assets, fake subprocesses and temporary roots."""
import hashlib
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

import scott_voice_engine as engine
import scott_voice_install as setup

pytestmark = pytest.mark.unit


@pytest.fixture
def source(tmp_path, monkeypatch):
    root = tmp_path/'source'
    reference = b'synthetic reference fixture'
    monkeypatch.setattr(setup, 'REFERENCE_SHA', hashlib.sha256(reference).hexdigest())
    for name in (*setup.ASSETS, *setup.CLIENT_FILES):
        path = root/name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('fixture', encoding='utf-8')
    (root/setup.ASSETS[-1]).write_bytes(reference)
    (root/setup.ASSETS[-2]).write_text(json.dumps({'sha256': setup.REFERENCE_SHA}), encoding='utf-8')
    (root/'personal.txt').write_text('never packaged', encoding='utf-8')
    return root


def test_plan_does_not_touch_disk_or_global_packages(tmp_path):
    home = tmp_path/'optional'
    result = setup.plan(home, 'python.exe')
    assert not home.exists()
    assert result['revision'] == setup.REVISION
    assert '--system-site-packages' not in str(result)
    for command in result['commands'][1:]:
        assert command[0] == str(setup.python_path(home))
    assert setup.REQUIREMENTS[-1] in result['commands'][2]


def test_bundle_whitelist_and_reference_are_sealed(source, tmp_path):
    target = tmp_path/'bundle'
    result = setup.bundle_assets(target, source)
    assert result['files'] == 9
    assert not (target/'personal.txt').exists()
    assert not (target/'backend').exists()
    manifest = json.loads((target/'assets.json').read_text())
    assert set(manifest['files']) == set(setup.ASSETS)
    assert manifest['files'][setup.ASSETS[-1]] == setup.REFERENCE_SHA
    with pytest.raises(ValueError, match='уже существует'):
        setup.bundle_assets(target, source)


def test_reference_corruption_stops_before_creating_bundle(source, tmp_path):
    (source/setup.ASSETS[-1]).write_bytes(b'changed')
    target = tmp_path/'bundle'
    with pytest.raises(ValueError, match='эталона'):
        setup.bundle_assets(target, source)
    assert not target.exists()


def test_built_package_rejects_modified_scripts(source):
    setup.bundle_assets(source/'voice-assets', source)
    assert setup.asset_sources(source)
    (source/'voice-assets'/setup.ASSETS[0]).write_text('changed')
    with pytest.raises(ValueError, match='Повреждён'):
        setup.asset_sources(source)


def test_rebundling_preserves_checked_legacy_upgrade_manifest(source,tmp_path):
    legacy=source/'assets/scott-voice/legacy-assets-v1.json'
    legacy.parent.mkdir(parents=True)
    legacy.write_text(json.dumps(dict(version=1,files={setup.ASSETS[0]:'a'*64})),encoding='utf-8')
    setup.bundle_assets(source/'voice-assets',source)
    setup.bundle_assets(tmp_path/'rebundled',source)
    assert (tmp_path/'rebundled/legacy-assets-v1.json').read_bytes()==legacy.read_bytes()


def test_public_reference_resources_make_reports_optional(source, tmp_path):
    public = source/'assets/scott-voice/reference'
    public.mkdir(parents=True)
    for name in setup.ASSETS[-2:]:
        original = source/name
        (public/original.name).write_bytes(original.read_bytes())
        original.unlink()
    assert setup.asset_sources(source)[setup.ASSETS[-1]].parent == public
    assert setup.bundle_assets(tmp_path/'bundle', source)['files'] == 9


def test_completed_optional_install_takes_priority_without_moving_cache(tmp_path, monkeypatch):
    monkeypatch.delenv('SCOTT_VOICE_HOME', raising=False)
    home = tmp_path/'voice-runtime'
    assert engine.default_config(tmp_path).worker == tmp_path/setup.ASSETS[0]
    home.mkdir()
    (home/'scott-install.json').write_text(json.dumps({'ready': False}))
    assert engine.default_config(tmp_path).worker == tmp_path/setup.ASSETS[0]
    (home/'scott-install.json').write_text(json.dumps({'ready': True}))
    config = engine.default_config(tmp_path)
    assert config.worker == home/setup.ASSETS[0]
    assert config.cache_dir == tmp_path/'audio_cache/scott-voice'


def test_explicit_home_does_not_silently_use_another_installation(tmp_path, monkeypatch):
    home = tmp_path/'elsewhere'
    monkeypatch.setenv('SCOTT_VOICE_HOME', str(home))
    assert setup.home_path(tmp_path) == home
    assert engine.default_config(tmp_path).worker == home/setup.ASSETS[0]
    assert not home.exists()


@pytest.mark.parametrize('marker', [[], None, 4, {'ready': 'true'}])
def test_invalid_ready_marker_keeps_development_default(tmp_path, monkeypatch, marker):
    monkeypatch.delenv('SCOTT_VOICE_HOME', raising=False)
    home = tmp_path/'voice-runtime'
    home.mkdir()
    (home/'scott-install.json').write_text(json.dumps(marker))
    assert engine.default_config(tmp_path).worker == tmp_path/setup.ASSETS[0]


def test_deep_check_detects_changed_weight(tmp_path, monkeypatch):
    monkeypatch.setattr(engine, 'inspect_installation', lambda config: '')
    model = tmp_path/'experiments/voice_design/models/base'
    hashes = {}
    for name in setup.MODEL_FILES:
        path = model/name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b'weight')
        hashes[name] = setup.checksum(path)
    setup.write_json(model/'scott-model.json', {'sha256': hashes})
    assert setup.check(tmp_path, deep=True)['available']
    (model/'model.safetensors').write_bytes(b'changed')
    assert setup.check(tmp_path, deep=True)['error'] == 'invalid_assets'


@pytest.fixture
def fake_processes(monkeypatch):
    calls = []
    def run(command, **kwargs):
        calls.append(command)
        if '-c' in command:
            return SimpleNamespace(stdout='(3, 13):8\n')
        if 'venv' in command:
            venv = Path(command[-1])
            executable = venv/('Scripts/python.exe' if setup.os.name == 'nt' else 'bin/python')
            executable.parent.mkdir(parents=True)
            executable.write_text('fixture')
            (venv/'pyvenv.cfg').write_text('include-system-site-packages = false')
        return SimpleNamespace(returncode=0)
    monkeypatch.setattr(setup.subprocess, 'run', run)
    monkeypatch.setattr(setup, 'check', lambda home, deep=False: {'available': True, 'error': ''})
    return calls


@pytest.mark.skipif(setup.os.name != 'nt', reason='Windows installer')
def test_install_isolated_and_idempotent(source, tmp_path, fake_processes):
    home = tmp_path/'optional'
    assert setup.install(home, 'python.exe', source)['available']
    assert not (home/'installation.lock').exists()
    assert json.loads((home/'scott-install.json').read_text())['ready']
    assert any('--download-model' in call for call in fake_processes)
    fake_processes.clear()
    assert setup.install(home, 'python.exe', source)['available']
    assert len(fake_processes) == 1  # Only base Python preflight; no pip/download.


@pytest.mark.skipif(setup.os.name != 'nt', reason='Windows installer')
def test_install_rejects_unrelated_folder(source, tmp_path, fake_processes):
    home = tmp_path/'other'
    home.mkdir()
    (home/'personal.txt').write_bytes(b'preserved')
    with pytest.raises(ValueError, match='другие файлы'):
        setup.install(home, 'python.exe', source)
    assert (home/'personal.txt').read_bytes() == b'preserved'
    assert not (home/'scott-install.json').exists()


@pytest.mark.skipif(setup.os.name != 'nt', reason='Windows installer')
def test_install_keeps_partial_files_after_failure_and_releases_lock(source, tmp_path, monkeypatch, fake_processes):
    home = tmp_path/'optional'
    run = setup.subprocess.run
    def fail(command, **kwargs):
        if 'pip' in command:
            raise OSError('network failed')
        return run(command, **kwargs)
    monkeypatch.setattr(setup.subprocess, 'run', fail)
    with pytest.raises(OSError):
        setup.install(home, 'python.exe', source)
    assert not (home/'installation.lock').exists()
    assert not json.loads((home/'scott-install.json').read_text())['ready']
    assert (home/setup.ASSETS[-1]).is_file()
    monkeypatch.setattr(setup.subprocess, 'run', run)
    assert setup.install(home, 'python.exe', source)['available']


@pytest.mark.skipif(setup.os.name != 'nt', reason='Windows installer')
def test_global_site_packages_are_rejected(source, tmp_path, fake_processes):
    home = tmp_path/'optional'
    setup.install(home, 'python.exe', source)
    venv = setup.python_path(home).parent.parent
    (venv/'pyvenv.cfg').write_text('include-system-site-packages = true')
    with pytest.raises(ValueError, match='глобальные пакеты'):
        setup.install(home, 'python.exe', source)


def test_installer_does_not_forward_provider_tokens_or_pip_target(monkeypatch):
    monkeypatch.setenv('SAMPLE_API_KEY', 'secret')
    monkeypatch.setenv('HF_TOKEN', 'secret')
    monkeypatch.setenv('PIP_TARGET', 'global')
    monkeypatch.setenv('PYTHONPATH', 'global')
    env = setup.clean_environment()
    assert not {'SAMPLE_API_KEY', 'HF_TOKEN', 'PIP_TARGET', 'PYTHONPATH'}.intersection(env)
    assert env['PIP_CONFIG_FILE'] == setup.os.devnull


@pytest.mark.skipif(setup.os.name != 'nt', reason='Windows installer')
def test_concurrent_install_keeps_existing_lock(source, tmp_path, fake_processes):
    home = tmp_path/'optional'
    setup.install(home, 'python.exe', source)
    setup.write_json(home/'scott-install.json', {'version': 1, 'model': setup.MODEL,
        'revision': setup.REVISION, 'ready': False})
    (home/'installation.lock').write_text('owned by another installer')
    with pytest.raises(ValueError, match='Установка уже выполняется'):
        setup.install(home, 'python.exe', source)
    assert (home/'installation.lock').read_text() == 'owned by another installer'


@pytest.mark.skipif(setup.os.name != 'nt', reason='Windows installer')
def test_stale_owned_lock_can_be_retried(source, tmp_path, fake_processes):
    home = tmp_path/'optional'
    setup.install(home, 'python.exe', source)
    setup.write_json(home/'installation.lock', {'pid': setup.os.getpid(), 'created':0, 'nonce':'old'})
    assert setup.install(home, 'python.exe', source)['available']
    assert not (home/'installation.lock').exists()


@pytest.mark.skipif(setup.os.name != 'nt', reason='Windows installer')
def test_live_owned_lock_is_preserved(source, tmp_path, fake_processes):
    home = tmp_path/'optional'
    setup.install(home, 'python.exe', source)
    token = {'pid': setup.os.getpid(), 'created': setup.psutil.Process().create_time(), 'nonce':'live'}
    setup.write_json(home/'installation.lock', token)
    with pytest.raises(ValueError, match='Установка уже выполняется'):
        setup.install(home, 'python.exe', source)
    assert json.loads((home/'installation.lock').read_text()) == token


@pytest.mark.skipif(setup.os.name != 'nt', reason='Windows installer')
def test_changed_recipe_does_not_overwrite_existing_scripts(source, tmp_path, fake_processes):
    home = tmp_path/'optional'
    setup.install(home, 'python.exe', source)
    target = home/setup.ASSETS[0]
    target.write_bytes(b'other recipe')
    with pytest.raises(ValueError, match='другая версия'):
        setup.install(home, 'python.exe', source)
    assert target.read_bytes() == b'other recipe'


def test_cli_default_only_prints_plan(tmp_path, capsys):
    home = tmp_path/'optional'
    assert setup.main(['--home', str(home)]) == 0
    assert json.loads(capsys.readouterr().out)['home'] == str(home.resolve())
    assert not home.exists()


@pytest.fixture
def fake_hub(monkeypatch):
    data = b'official synthetic file'
    items = [SimpleNamespace(rfilename=name, size=len(data),
        lfs=SimpleNamespace(sha256=hashlib.sha256(data).hexdigest()) if name.endswith('.safetensors') else None,
        blob_id=hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest())
        for name in (*setup.MODEL_FILES, 'README.md')]
    calls = []
    def model_info(repo, **kwargs):
        assert repo == setup.MODEL and kwargs['revision'] == setup.REVISION
        return SimpleNamespace(sha=setup.REVISION, siblings=items)
    def fetch(repo, name, **kwargs):
        assert kwargs['token'] is False and kwargs['revision'] == setup.REVISION
        calls.append((name, kwargs['force_download']))
        path = Path(kwargs['local_dir'])/name
        path.parent.mkdir(parents=True, exist_ok=True)
        if kwargs['force_download'] or not path.exists():
            path.write_bytes(data)
        return str(path)
    hub = SimpleNamespace(HfApi=lambda **kwargs: SimpleNamespace(model_info=model_info), hf_hub_download=fetch)
    monkeypatch.setitem(sys.modules, 'huggingface_hub', hub)
    return SimpleNamespace(calls=calls, items=items, hub=hub)


def test_download_reuses_only_verified_files_and_replaces_corrupt_partial(tmp_path, fake_hub):
    model = tmp_path/'experiments/voice_design/models/base'
    model.mkdir(parents=True)
    (model/'config.json').write_bytes(b'bad configuration')
    (model/'model.safetensors').write_bytes(b'bad checkpoint')
    setup.download_model(tmp_path)
    assert ('config.json', True) in fake_hub.calls
    assert ('model.safetensors', True) in fake_hub.calls
    manifest = json.loads((model/'scott-model.json').read_text())
    assert manifest['revision'] == setup.REVISION
    assert set(setup.MODEL_FILES).issubset(manifest['sha256'])


@pytest.mark.parametrize('name', ['config.json', 'model.safetensors'])
def test_incorrect_official_hash_never_publishes_model_manifest(tmp_path, fake_hub, name):
    item = next(item for item in fake_hub.items if item.rfilename == name)
    if item.lfs:
        item.lfs.sha256 = '0'*64
    else:
        item.blob_id = '0'*40
    with pytest.raises(ValueError, match='Контрольная сумма'):
        setup.download_model(tmp_path)
    assert not (tmp_path/'experiments/voice_design/models/base/scott-model.json').exists()
