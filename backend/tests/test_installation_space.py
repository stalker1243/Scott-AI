"""Capacity checks do not download components or inspect user content."""
from types import SimpleNamespace
import json
import pytest
import installation_space as space

pytestmark = pytest.mark.unit


def test_budget_includes_temporary_space_and_reports_unknown_capacity(tmp_path, monkeypatch):
    monkeypatch.setattr(space.shutil, 'disk_usage', lambda path: (_ for _ in ()).throw(OSError()))
    result = space.budget('voice_shared', tmp_path/'not-created')
    assert result['required_free_bytes'] == 5*space.GIB
    assert result['free_bytes'] is None and result['enough_space'] is None
    assert not (tmp_path/'not-created').exists()


def test_low_space_is_actionable_before_install(tmp_path, monkeypatch):
    monkeypatch.setattr(space, 'free_bytes', lambda path: space.GIB)
    with pytest.raises(space.InsufficientSpace, match='Освободите место') as caught:
        space.require_space('cpu', tmp_path, temporary=tmp_path)
    assert caught.value.code == 'disk_full'


def test_enough_space_is_read_only(tmp_path, monkeypatch):
    monkeypatch.setattr(space, 'free_bytes', lambda path: 10*space.GIB)
    result = space.require_space('voice', tmp_path/'optional', temporary=tmp_path)
    assert result['enough_space'] and not (tmp_path/'optional').exists()


def test_separate_temporary_volume_is_checked(tmp_path, monkeypatch):
    target = SimpleNamespace(stat=lambda: SimpleNamespace(st_dev=1))
    temporary = SimpleNamespace(stat=lambda: SimpleNamespace(st_dev=2))
    monkeypatch.setattr(space, 'existing_parent', lambda path: target if path == 'destination' else temporary)
    monkeypatch.setattr(space, 'budget', lambda *a: dict(installed_max_bytes=8*space.GIB,
        temporary_bytes=2*space.GIB, required_free_bytes=10*space.GIB))
    monkeypatch.setattr(space, 'free_bytes', lambda path: 8*space.GIB if path is target else space.GIB)
    with pytest.raises(space.InsufficientSpace, match='временных файлов'):
        space.require_space('voice', 'destination', temporary='temporary')


def test_setup_retains_both_cpu_and_gpu_estimates(tmp_path):
    result = space.setup_budgets(tmp_path)
    assert set(result) == {'cpu', 'auto'}
    assert result['cpu']['required_free_bytes'] < result['auto']['required_free_bytes']
    assert 'Scott Voice' in result['auto']['hint']


def test_linux_cpu_budget_covers_measured_dependencies_before_models(tmp_path,monkeypatch):
    monkeypatch.setattr(space.sys,'platform','linux')
    result=space.setup_budgets(tmp_path)
    assert result['cpu']['installed_min_bytes']>=3*space.GIB
    assert result['cpu']['required_free_bytes']>=4.5*space.GIB
    assert '4,5' in result['auto']['hint'] and '4 ГиБ на CPU' in result['auto']['hint']


def test_windows_cpu_estimate_is_not_inflated_by_linux_only_dependencies(tmp_path,monkeypatch):
    monkeypatch.setattr(space.sys,'platform','win32')
    result=space.setup_budgets(tmp_path)
    assert result['cpu']['installed_max_bytes']==2*space.GIB
    assert result['cpu']['required_free_bytes']==2.5*space.GIB


def test_setup_measures_persistent_runtime_disk_instead_of_install_mount(tmp_path,monkeypatch):
    destination=tmp_path/'persistent disk/runtime'
    (tmp_path/'.scott-linux-install.json').write_text(json.dumps(dict(runtime_home=str(destination.parent))))
    paths=[]
    monkeypatch.setattr(space,'free_bytes',lambda path: paths.append(path) or 10*space.GIB)
    space.setup_budgets(tmp_path)
    assert paths==[destination,destination]
