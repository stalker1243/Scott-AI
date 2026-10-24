"""A wizard choice survives fresh Python and retries without rewriting .env."""
import builtins
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest
import bootstrap
import model_setup
import runtime_profile as profile
import storage_paths
import storage

pytestmark = pytest.mark.unit


@pytest.fixture
def selection(tmp_path, monkeypatch):
    path = tmp_path/'config/runtime_profile.json'
    monkeypatch.setattr(profile, 'selection_path', lambda: path)
    for key in {'SCOTT_RUNTIME_PROFILE', 'SCOTT_TORCH_BACKEND', 'WHISPER_ENGINE', 'WHISPER_DEVICE'}:
        monkeypatch.delenv(key, raising=False)
    return path


def test_no_saved_selection_preserves_legacy_environment(selection, monkeypatch):
    monkeypatch.setenv('WHISPER_ENGINE', 'openai')
    monkeypatch.setenv('WHISPER_DEVICE', 'cuda')
    monkeypatch.setenv('SCOTT_TORCH_BACKEND', 'rocm')
    before = dict(os.environ)
    assert profile.apply_selection() is None
    assert dict(os.environ) == before
    assert not selection.exists()


@pytest.mark.parametrize('mode', ['auto', 'cpu', 'compact'])
def test_choice_is_versioned_and_reapplied(selection, mode, monkeypatch):
    monkeypatch.setenv('WHISPER_ENGINE', 'openai')
    monkeypatch.setenv('WHISPER_DEVICE', 'cuda')
    monkeypatch.setenv('WHISPER_MODEL', 'medium')
    profile.save_selection(mode)
    assert json.loads(selection.read_text()) == {'version': 1, 'mode': mode}
    assert profile.apply_selection() == mode
    for key, value in profile.SETUP_MODES[mode].items():
        assert os.environ[key] == value
    assert os.environ['WHISPER_MODEL'] == 'medium'
    if mode == 'auto':
        assert os.environ['WHISPER_DEVICE'] == 'cuda'
        assert os.environ['WHISPER_ENGINE'] == 'openai'
    assert not list(selection.parent.glob('*.tmp'))


def test_compact_applies_without_dotenv_before_pip(selection, monkeypatch):
    original = builtins.__import__
    def import_without_dotenv(name, *args, **kwargs):
        if name == 'dotenv':
            raise ImportError('Not installed yet')
        return original(name, *args, **kwargs)
    monkeypatch.setattr(builtins, '__import__', import_without_dotenv)
    profile.save_selection('compact')
    model_setup.load_environment()
    assert profile.compact_mode()
    assert os.environ['WHISPER_DEVICE'] == 'cpu'
    assert os.environ['SCOTT_TORCH_BACKEND'] == 'cpu'


def test_return_to_auto_restores_original_settings_from_dotenv(selection, tmp_path, monkeypatch):
    path = tmp_path/'.env'
    original = b'# preserved settings\nWHISPER_ENGINE=openai\nWHISPER_DEVICE=cuda\nWHISPER_MODEL=medium\n'
    path.write_bytes(original)
    monkeypatch.setattr(storage_paths, 'environment_path', lambda: path)
    profile.save_selection('compact')
    model_setup.load_environment()
    assert profile.compact_mode()
    profile.save_selection('auto')
    # The next process starts without the previous process's overlay.
    for key in ('SCOTT_RUNTIME_PROFILE','SCOTT_TORCH_BACKEND','WHISPER_ENGINE','WHISPER_DEVICE','WHISPER_MODEL'):
        monkeypatch.delenv(key, raising=False)
    model_setup.load_environment()
    assert not profile.compact_mode()
    assert os.environ['WHISPER_DEVICE'] == 'cuda'
    assert os.environ['WHISPER_ENGINE'] == 'openai'
    assert os.environ['WHISPER_MODEL'] == 'medium'
    assert path.read_bytes() == original


@pytest.mark.parametrize('raw', [b'{', b'[]', b'null', b'{}', b' '*4097,
    b'{"version":true,"mode":"compact"}', b'{"version":2,"mode":"auto"}',
    b'{"version":1,"mode":[]}', b'{"version":1,"mode":"other"}',
    b'{"version":1,"mode":"compact","API_TOKEN":"never apply"}'])
def test_bad_selection_fails_clearly_without_applying_environment(selection, raw):
    selection.parent.mkdir()
    selection.write_bytes(raw)
    before = dict(os.environ)
    with pytest.raises(profile.ProfileError, match='повреждён'):
        profile.apply_selection()
    assert dict(os.environ) == before
    assert selection.read_bytes() == raw


def test_failed_atomic_save_preserves_previous_choice(selection, monkeypatch):
    profile.save_selection('cpu')
    before = selection.read_bytes()
    def denied(*args):
        raise PermissionError('fixture')
    monkeypatch.setattr(storage.os, 'replace', denied)
    with pytest.raises(profile.ProfileError, match='сохранить'):
        profile.save_selection('compact')
    assert selection.read_bytes() == before
    assert not list(selection.parent.glob('*.tmp'))


def test_selection_uses_linux_user_config_in_readonly_install(tmp_path):
    root = tmp_path/'application'
    root.mkdir()
    (root/'.scott-linux-install.json').write_text('{}')
    layout = storage_paths.layout_for(root, platform='linux', env={}, home=tmp_path/'home')
    assert layout.external
    assert layout.backend('runtime_profile.json') == layout.config/'runtime_profile.json'
    assert root not in layout.config.parents


@pytest.mark.parametrize('args', [['--runtime-mode'], ['--runtime-mode','unknown'],
    ['--runtime-mode','cpu','--runtime-mode','compact']])
def test_cli_rejects_invalid_mode_before_install(selection, monkeypatch, args, capsys):
    monkeypatch.setattr(bootstrap, 'prepare', lambda **kw: pytest.fail('No install on invalid mode'))
    assert bootstrap.main(['--json',*args]) == 1
    assert json.loads(capsys.readouterr().out)['code'] == 'runtime_profile_invalid'
    assert not selection.exists()


def test_cli_check_does_not_persist_choice(selection, monkeypatch, capsys):
    profile.save_selection('cpu')
    before = selection.read_bytes()
    monkeypatch.setattr(bootstrap, 'is_ready', lambda: profile.compact_mode())
    monkeypatch.setattr(bootstrap, 'gpu_name', lambda: 'fixture')
    assert bootstrap.main(['--json','--check','--runtime-mode','compact']) == 0
    event = json.loads(capsys.readouterr().out)
    assert event['runtime_mode'] == 'compact'
    assert 'compact' in event['space']
    assert selection.read_bytes() == before


def test_cli_persists_before_failed_preparation_and_repairs_bad_file(selection, monkeypatch, capsys):
    selection.parent.mkdir()
    selection.write_bytes(b'broken')
    def prepare(**kw):
        assert profile.saved_selection() == 'compact'
        assert profile.compact_mode()
        return SimpleNamespace(done=False, error='Controlled download failure')
    monkeypatch.setattr(bootstrap, 'prepare', prepare)
    assert bootstrap.main(['--json','--runtime-mode','compact']) == 1
    assert profile.saved_selection() == 'compact'
    assert 'Controlled download failure' in capsys.readouterr().out


def test_cli_corrupt_selection_has_actionable_error_without_hardware_probe(selection, monkeypatch, capsys):
    selection.parent.mkdir()
    selection.write_bytes(b'broken')
    monkeypatch.setattr(bootstrap, 'is_ready', lambda: pytest.fail('No hardware work on corrupt selection'))
    assert bootstrap.main(['--check','--json']) == 1
    event = json.loads(capsys.readouterr().out)
    assert event['code'] == 'runtime_profile_invalid'
    assert 'Выберите режим' in event['message']
