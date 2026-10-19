"""Offline support export uses disposable credentials, chat and logs."""
import json
import os
from pathlib import Path
import subprocess
import sys
import zipfile
import pytest
import diagnostics
import support_logs

pytestmark = pytest.mark.unit

@pytest.fixture
def fixture_root(tmp_path, monkeypatch):
    root = tmp_path/'app'
    (root/'backend/data').mkdir(parents=True)
    (root/'.env').write_text('CUSTOM_API_KEY=opaque-env-credential\n', encoding='utf-8')
    (root/'backend/data/ai_config.json').write_text(json.dumps({'providers': {'custom': {'api_key': 'opaque-saved-credential'}}}))
    (root/'backend/data/history.json').write_text('private chat never packaged')
    monkeypatch.setattr(diagnostics, 'PROJECT_DIR', root)
    monkeypatch.setenv('SCOTT_LOG_DIR', str(tmp_path/'logs'))
    monkeypatch.setattr(diagnostics, 'LOG_FILES', {'setup.log': tmp_path/'logs/setup.log'})
    return root

def test_archive_redacts_saved_tokens_note_and_user_lines(fixture_root, tmp_path):
    log = diagnostics.LOG_FILES['setup.log']; log.parent.mkdir()
    log.write_text('ERROR opaque-saved-credential opaque-env-credential\nBearer x\n'
        '👤 Пользователь (Test): private request\n🤖 Scott: private reply\n', encoding='utf-8')
    output = tmp_path/'support.zip'
    result = diagnostics.build_report('opaque-saved-credential', output=output, lightweight=True)
    assert result['success']
    with zipfile.ZipFile(output) as archive:
        text = '\n'.join(archive.read(name).decode('utf-8') for name in archive.namelist())
        assert not any(value in text for value in ('opaque-saved-credential', 'opaque-env-credential', 'Bearer x', 'private request', 'private reply', 'private chat'))
        assert not any(name.endswith(('.env', 'history.json', 'ai_config.json')) for name in archive.namelist())

def test_logs_rotate_and_mask_short_credentials(fixture_root, tmp_path, monkeypatch):
    monkeypatch.setattr(support_logs, 'LIMIT', 180)
    monkeypatch.setenv('TEST_TOKEN', 'xy')
    for _ in range(12):
        support_logs.append_log('setup.log', 'ERROR xy '+ 'z'*50, fixture_root)
    files = list((tmp_path/'logs').iterdir())
    assert {p.name for p in files} == {'setup.log', 'setup.log.1', 'setup.log.2'}
    assert all(p.stat().st_size <= 180 for p in files)
    assert all(' xy ' not in p.read_text(encoding='utf-8') for p in files)


def test_saved_provider_key_ring_is_masked_including_inactive_keys(fixture_root):
    (fixture_root/'backend/data/ai_config.json').write_text(json.dumps({
        'provider':'Groq','keys':{'Groq':'opaque-active-fixture','OpenAI':'opaque-inactive-fixture'}}))
    result=support_logs.redact('ERROR opaque-active-fixture opaque-inactive-fixture',fixture_root)
    assert 'opaque-active-fixture' not in result and 'opaque-inactive-fixture' not in result


def test_moved_config_and_env_are_masked_without_starting_migration(fixture_root,tmp_path,monkeypatch):
    import storage_paths
    layout=storage_paths.Layout(fixture_root,tmp_path/'data',tmp_path/'config',tmp_path/'cache',True)
    layout.config.mkdir()
    layout.environment.write_text('CUSTOM_API_KEY=opaque-new-env-fixture\n')
    layout.backend('ai_config.json').write_text(json.dumps({'keys':{'other':'opaque-new-config-fixture'}}))
    monkeypatch.setattr(storage_paths,'layout_for',lambda root:layout)
    result=support_logs.redact('ERROR opaque-new-env-fixture opaque-new-config-fixture opaque-saved-credential',fixture_root)
    assert all(value not in result for value in ('opaque-new-env-fixture','opaque-new-config-fixture','opaque-saved-credential'))
    assert not layout.data.exists(), 'Offline redaction must not create/migrate user data'


def test_browser_setup_log_is_exported_with_credentials_masked(fixture_root,tmp_path,monkeypatch):
    log=tmp_path/'logs/browser-setup.log'
    monkeypatch.setitem(diagnostics.LOG_FILES,'browser-setup.log',log)
    support_logs.append_log('browser-setup.log','libraries: ERROR opaque-saved-credential',fixture_root)
    result=diagnostics.build_report(output=tmp_path/'browser.zip',lightweight=True)
    with zipfile.ZipFile(result['path']) as archive:
        text=archive.read('logs/browser-setup.log').decode('utf-8')
        assert 'libraries: ERROR' in text and 'opaque-saved-credential' not in text
        assert not any('browser-control' in name for name in archive.namelist())


def test_updater_log_is_exported_with_saved_tokens_masked(fixture_root,tmp_path,monkeypatch):
    log=tmp_path/'logs/updater.log'
    monkeypatch.setitem(diagnostics.LOG_FILES,'updater.log',log)
    support_logs.append_log('updater.log','verification: ERROR opaque-saved-credential',fixture_root)
    result=diagnostics.build_report(output=tmp_path/'updater.zip',lightweight=True)
    with zipfile.ZipFile(result['path']) as archive:
        text=archive.read('logs/updater.log').decode('utf-8')
        assert 'verification: ERROR' in text and 'opaque-saved-credential' not in text


def test_api_error_identifier_is_exported_without_saved_token(fixture_root,tmp_path,monkeypatch):
    log=tmp_path/'logs/api-errors.log'
    monkeypatch.setitem(diagnostics.LOG_FILES,'api-errors.log',log)
    support_logs.append_log('api-errors.log','0123456789ab RuntimeError fixture:12 opaque-saved-credential',fixture_root)
    result=diagnostics.build_report(output=tmp_path/'api-support.zip',lightweight=True)
    with zipfile.ZipFile(result['path']) as archive:
        text=archive.read('logs/api-errors.log').decode('utf-8')
        assert '0123456789ab' in text and 'RuntimeError' in text
        assert 'opaque-saved-credential' not in text

def test_bounded_tail_and_archive_skip_action_history(fixture_root, tmp_path, monkeypatch):
    monkeypatch.setattr(diagnostics, 'MAX_LOG_BYTES', 100)
    log = diagnostics.LOG_FILES['setup.log']; log.parent.mkdir()
    log.write_text('old private data\n'+'x'*400+'\nERROR newest\n')
    action = log.parent/'secure_exec.log'; action.write_text('private commands')
    monkeypatch.setitem(diagnostics.LOG_FILES, 'secure_exec.log', action)
    result = diagnostics.build_report(output=tmp_path/'bounded.zip', lightweight=True)
    with zipfile.ZipFile(result['path']) as archive:
        assert 'logs/secure_exec.log' not in archive.namelist()
        data = archive.read('logs/setup.log')
        assert len(data) <= 100 and b'ERROR newest' in data and b'old private' not in data

def test_offline_cli_needs_no_installed_dependencies(fixture_root, tmp_path):
    import shutil
    for name in ('diagnostics.py', 'support_logs.py', 'platform_paths.py', 'storage_paths.py'):
        shutil.copy2(Path(diagnostics.__file__).parent/name, fixture_root/'backend'/name)
    output = tmp_path/'offline.zip'
    result = subprocess.run([sys.executable, '-S', str(fixture_root/'backend/diagnostics.py'), '--json', '--output', str(output)],
        capture_output=True, text=True, encoding='utf-8', timeout=20, env=dict(os.environ, PYTHONIOENCODING='utf-8'), creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)['success'] and zipfile.is_zipfile(output)

def test_failed_export_preserves_existing_archive(fixture_root, tmp_path, monkeypatch):
    output = tmp_path/'existing.zip'; output.write_bytes(b'existing report')
    monkeypatch.setattr(diagnostics.os, 'replace', lambda *args: (_ for _ in ()).throw(OSError('fixture failure')))
    assert not diagnostics.build_report(output=output, lightweight=True)['success']
    assert output.read_bytes() == b'existing report'
    assert not list(tmp_path.glob('.scott-report-*'))
