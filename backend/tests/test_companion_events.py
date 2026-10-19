"""Real atomic visual notifications; application launches themselves are mocked."""
import json
import os
from pathlib import Path
import re

import pytest

from backend import companion_events as events


@pytest.fixture
def profile(tmp_path, monkeypatch):
    root = tmp_path / 'pet'
    root.mkdir()
    (root / 'settings.ini').write_text('[General]\nenabled=true\n', encoding='utf-8')
    monkeypatch.setenv('SCOTT_PET_STATE_DIR', str(root))
    return root


def test_event_contains_no_application_or_user_data(profile):
    assert events.application_opened()
    value = json.loads((profile / 'activity.json').read_text())
    assert set(value) == {'version', 'event', 'id', 'created_ms'}
    assert value['version'] == 1 and value['event'] == 'application_opened'
    assert re.fullmatch('[a-f0-9]{32}', value['id'])
    assert isinstance(value['created_ms'], int)
    if os.name != 'nt':
        assert (profile / 'activity.json').stat().st_mode & 0o777 == 0o600
    assert events.application_opened()
    assert json.loads((profile / 'activity.json').read_text())['id'] != value['id']
    assert not list(profile.glob('.activity-*'))


@pytest.mark.parametrize('settings', ['[General]\nenabled=false\n', '[General]\n', 'broken', 'x' * 16385])
def test_disabled_or_invalid_profile_is_not_written(profile, settings):
    (profile / 'settings.ini').write_text(settings)
    assert not events.application_opened()
    assert not (profile / 'activity.json').exists()


def test_no_profile_is_created_and_relative_override_is_ignored(tmp_path, monkeypatch):
    missing = tmp_path / 'missing'
    monkeypatch.setenv('SCOTT_PET_STATE_DIR', str(missing))
    assert not events.application_opened() and not missing.exists()
    monkeypatch.setenv('SCOTT_PET_STATE_DIR', 'relative')
    assert events.state_directory() is None
    assert not events.application_opened()


def test_failed_publication_is_nonfatal_and_removes_only_its_temporary_file(profile, monkeypatch):
    original = profile / 'activity.json'
    original.write_text('previous')
    monkeypatch.setattr(events.os, 'replace', lambda *args: (_ for _ in ()).throw(PermissionError()))
    assert not events.application_opened()
    assert original.read_text() == 'previous'
    assert not list(profile.glob('.activity-*'))


@pytest.mark.parametrize('name', ['settings.ini', 'activity.json'])
def test_symlinks_are_not_followed(profile, tmp_path, name):
    outside = tmp_path / 'outside'
    outside.write_text('[General]\nenabled=true\n')
    target = profile / name
    if target.exists():
        target.unlink()
    try:
        target.symlink_to(outside)
    except OSError:
        pytest.skip('Symlink creation is unavailable for this user')
    assert not events.application_opened()
    assert outside.read_text() == '[General]\nenabled=true\n'


@pytest.mark.parametrize('kind', ['windows-path', 'windows-uri', 'linux-path', 'resolver'])
def test_successful_app_launch_publishes_once(profile, monkeypatch, kind):
    from backend import command_executor as commands
    import app_resolver
    executor = commands.CommandExecutor.__new__(commands.CommandExecutor)
    launches = []
    monkeypatch.setattr(commands.platform, 'system', lambda: 'Linux' if kind == 'linux-path' else 'Windows')
    monkeypatch.setattr(commands.shutil, 'which', lambda _: None if kind == 'resolver' else '/fixture/app')
    monkeypatch.setattr(commands.subprocess, 'Popen', lambda *a, **kw: launches.append(a))
    monkeypatch.setattr(commands.os, 'startfile', lambda *a: launches.append(a), raising=False)
    monkeypatch.setattr(app_resolver, 'launch_app', lambda _: dict(success=True, source='fixture', matched_name='Fixture'))
    published = []
    def publish():
        published.append(events.application_opened())
    monkeypatch.setattr(commands, 'application_opened', publish)
    result = executor.open_app('settings' if kind == 'windows-uri' else 'notepad' if kind == 'windows-path' else 'fixture')
    assert result.startswith('✅') and published == [True]
    assert (profile / 'activity.json').exists()
    assert len(launches) == (0 if kind == 'resolver' else 1)


def test_failed_app_does_not_publish(profile, monkeypatch):
    from backend import command_executor as commands
    import app_resolver
    executor = commands.CommandExecutor.__new__(commands.CommandExecutor)
    monkeypatch.setattr(commands.platform, 'system', lambda: 'Linux')
    monkeypatch.setattr(commands.shutil, 'which', lambda _: None)
    monkeypatch.setattr(app_resolver, 'launch_app', lambda _: dict(success=False, error='Fixture missing'))
    assert executor.open_app('fixture').startswith('❌')
    assert not (profile / 'activity.json').exists()
