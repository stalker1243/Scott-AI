"""Owned source upgrades use synthetic files and preserve edited runtime assets."""
import json
from pathlib import Path

import pytest
import voice_asset_update as update

pytestmark=pytest.mark.unit


@pytest.fixture
def assets(tmp_path):
    source=tmp_path/'source';home=tmp_path/'runtime'
    source.mkdir(); home.mkdir()
    files={}
    for name in ('backend/client.py','voice/worker.py','voice/reference.wav'):
        path=source/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(b'original')
        files[name]=path
    update.sync_assets(home,files)
    return home,files


def test_upgrade_changes_owned_sources_and_preserves_reference_and_data(assets):
    home,files=assets
    (home/'data').mkdir();(home/'data/history.txt').write_bytes(b'protected fixture')
    files['backend/client.py'].write_bytes(b'new code')
    assert update.sync_assets(home,files)==1
    assert (home/'backend/client.py').read_bytes()==b'new code'
    assert (home/'voice/reference.wav').read_bytes()==b'original'
    assert (home/'data/history.txt').read_bytes()==b'protected fixture'
    assert update.sync_assets(home,files)==0


def test_foreign_edit_blocks_every_update_before_any_change(assets):
    home,files=assets
    files['backend/client.py'].write_bytes(b'new code')
    (home/'voice/worker.py').write_bytes(b'foreign edit')
    with pytest.raises(ValueError,match='другая версия'): update.sync_assets(home,files)
    assert (home/'backend/client.py').read_bytes()==b'original'
    assert (home/'voice/worker.py').read_bytes()==b'foreign edit'


def test_reference_is_never_replaced_as_a_code_upgrade(assets):
    home,files=assets
    files['voice/reference.wav'].write_bytes(b'different reference')
    with pytest.raises(ValueError): update.sync_assets(home,files)
    assert (home/'voice/reference.wav').read_bytes()==b'original'


def test_failed_commit_rolls_back_changed_files_and_manifest(assets,monkeypatch):
    home,files=assets
    previous=(home/'scott-assets.json').read_bytes()
    for name in ('backend/client.py','voice/worker.py'): files[name].write_bytes(b'new code')
    replace=update.os.replace
    def fail(source,target):
        if Path(source).parts[-3:]==('new','voice','worker.py'):
            raise OSError('synthetic commit failure')
        replace(source,target)
    monkeypatch.setattr(update.os,'replace',fail)
    with pytest.raises(OSError): update.sync_assets(home,files)
    assert (home/'backend/client.py').read_bytes()==b'original'
    assert (home/'scott-assets.json').read_bytes()==previous
    assert not list(home.glob('.asset-update-*'))


def test_checked_legacy_identity_can_initialize_upgrade_receipt(assets):
    home,files=assets
    old=json.loads((home/'scott-assets.json').read_text())['files']
    (home/'scott-assets.json').unlink()
    files['backend/client.py'].write_bytes(b'new code')
    assert update.sync_assets(home,files,legacy=old)==1
    assert (home/'scott-assets.json').is_file()
