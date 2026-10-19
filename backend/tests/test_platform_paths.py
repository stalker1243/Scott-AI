"""Path decisions are read-only; permission checks use temporary directories."""
import os
from pathlib import Path
import stat
import pytest
from platform_paths import xdg_home, private_directory

pytestmark = pytest.mark.unit


@pytest.mark.parametrize('variable,relative', [
    ('XDG_DATA_HOME','.local/share'),('XDG_CONFIG_HOME','.config'),
    ('XDG_STATE_HOME','.local/state'),('XDG_CACHE_HOME','.cache')])
@pytest.mark.parametrize('value', ['', 'relative/state', '~/not-expanded'])
def test_missing_or_relative_xdg_values_use_home(variable, relative, value, tmp_path):
    home = tmp_path/'home'
    assert xdg_home(variable,env={variable:value},home=home) == home/relative
    assert not home.exists()


def test_absolute_xdg_value_preserves_spaces(tmp_path):
    custom = tmp_path/'custom space'
    assert xdg_home('XDG_STATE_HOME',env={'XDG_STATE_HOME':str(custom)},home=tmp_path) == custom
    assert not custom.exists()


@pytest.mark.skipif(os.name == 'nt', reason='POSIX modes')
def test_missing_parents_are_private_existing_permissions_unchanged(tmp_path):
    existing = tmp_path/'existing'
    existing.mkdir(mode=0o755)
    destination = existing/'ScottAI/logs'
    assert private_directory(destination) == destination
    assert stat.S_IMODE(existing.stat().st_mode) == 0o755
    assert stat.S_IMODE(destination.parent.stat().st_mode) == 0o700
    assert stat.S_IMODE(destination.stat().st_mode) == 0o700


def test_existing_file_is_not_replaced_by_directory(tmp_path):
    path = tmp_path/'file'
    path.write_bytes(b'keep')
    with pytest.raises(OSError):
        private_directory(path/'child')
    assert path.read_bytes() == b'keep'
