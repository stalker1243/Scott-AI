"""Migration uses synthetic data only; no application process/audio/network."""
from dataclasses import replace
from contextlib import closing
import json
import os
from pathlib import Path
import sqlite3
import stat
import subprocess
import sys
import time

import pytest
import storage_paths as storage

pytestmark = pytest.mark.unit


@pytest.fixture
def layout(tmp_path):
    root = tmp_path/'application'
    (root/'backend/data').mkdir(parents=True)
    (root/'.scott-linux-install.json').write_text('{}')
    return storage.layout_for(root, env={}, home=tmp_path/'home', platform='linux')


@pytest.mark.parametrize('platform,marked,mode,external', [
    ('win32',True,'',False),('linux',False,'',False),('linux',True,'legacy',False),
    ('linux',True,'',True),('darwin',True,'',False)])
def test_activation_is_limited_to_installed_linux(tmp_path, platform, marked, mode, external):
    if marked:
        (tmp_path/'.scott-linux-install.json').write_text('{}')
    result = storage.layout_for(tmp_path,env={'SCOTT_STORAGE_MODE':mode},home=tmp_path/'home',platform=platform)
    assert result.external is external
    if not external:
        assert result.backend('ai_config.json') == tmp_path/'backend/data/ai_config.json'
        assert result.environment == tmp_path/'.env'
    assert not result.data.exists()


def test_copy_config_history_attachments_unknown_files_and_legacy_memory(layout):
    source=layout.root/'backend/data'
    (source/'chats/assets').mkdir(parents=True)
    contents={'ai_config.json':b'{"key":"synthetic"}', 'memories.json':b'[]',
              'chats/assets/photo.png':b'fake attachment', 'unknown/report-wal':b'keep too'}
    for name, value in contents.items():
        (source/name).parent.mkdir(parents=True,exist_ok=True)
        (source/name).write_bytes(value)
    (layout.root/'data').mkdir()
    (layout.root/'data/memory.jsonl').write_bytes(b'legacy conversation')
    (layout.root/'.env').write_bytes(b'CUSTOM_API_KEY=opaque-fixture\n')
    storage.migrate(layout)
    for name, value in contents.items():
        assert (source/name).read_bytes()==value
        assert layout.backend(name).read_bytes()==value
    assert layout.environment.read_bytes()==(layout.root/'.env').read_bytes()
    assert layout.legacy_data('memory.jsonl').read_bytes()==b'legacy conversation'
    assert not (layout.data/'ai_config.json').exists()
    assert json.loads((layout.data/storage.RECEIPT).read_text())['files']==6


def test_xdg_dot_segments_are_normalized_before_overlap_checks(layout):
    custom=storage.layout_for(layout.root,env={'XDG_DATA_HOME':str(layout.root/'../xdg-data')},
                              home=layout.root.parent/'home',platform='linux')
    assert custom.data==layout.root.parent/'xdg-data/scottai'


@pytest.mark.parametrize('readonly', [False,pytest.param(True,marks=pytest.mark.skipif(os.name=='nt',reason='POSIX readonly directory'))])
def test_wal_snapshot_includes_committed_rows_and_preserves_source(layout,readonly):
    source=layout.root/'backend/data/chats'
    source.mkdir()
    database=source/'chats.sqlite3'
    connection=sqlite3.connect(database)
    files=[]
    try:
        connection.execute('pragma journal_mode=wal')
        connection.execute('pragma wal_autocheckpoint=0')
        connection.execute('create table messages(text)')
        connection.execute('insert into messages values (?)',('committed in WAL',))
        connection.commit()
        original=database.read_bytes()
        wal=database.with_name(database.name+'-wal').read_bytes()
        files=list(source.iterdir())
        if readonly:
            for file in files:
                file.chmod(0o444)
            source.chmod(0o555)
        storage.migrate(layout)
        with closing(sqlite3.connect(layout.backend('chats/chats.sqlite3'))) as copied:
            assert copied.execute('select text from messages').fetchall()==[('committed in WAL',)]
        assert database.read_bytes()==original
        assert database.with_name(database.name+'-wal').read_bytes()==wal
        assert not layout.backend('chats/chats.sqlite3-wal').exists()
    finally:
        if readonly:
            source.chmod(0o700)
            for file in files:
                file.chmod(0o600)
        connection.close()


def test_conflict_preflight_never_overwrites_either_version(layout):
    (layout.root/'backend/data/first.json').write_bytes(b'first')
    (layout.root/'backend/data/memories.json').write_bytes(b'old')
    layout.data.mkdir(parents=True)
    layout.backend('memories.json').write_bytes(b'new')
    with pytest.raises(storage.StorageMigrationError,match='Конфликт'):
        storage.migrate(layout)
    assert layout.backend('memories.json').read_bytes()==b'new'
    assert not layout.backend('first.json').exists()
    assert not (layout.data/storage.RECEIPT).exists()
    assert (layout.root/'backend/data/memories.json').read_bytes()==b'old'


def test_legacy_target_collision_is_detected_before_publication(layout):
    for name,value in (('backend/data/legacy/memory.jsonl',b'one'),('data/memory.jsonl',b'two')):
        path=layout.root/name
        path.parent.mkdir(parents=True,exist_ok=True)
        path.write_bytes(value)
    with pytest.raises(storage.StorageMigrationError,match='Два старых файла'):
        storage.migrate(layout)
    assert not layout.legacy_data('memory.jsonl').exists()
    assert not (layout.data/storage.RECEIPT).exists()


def test_interrupted_publication_resumes_then_never_resurrects_deleted_data(layout, monkeypatch):
    for name in ('memories.json','projects.json'):
        (layout.root/'backend/data'/name).write_bytes(name.encode())
    publish=storage._publish
    count=0
    def interrupted(source,target):
        nonlocal count
        count+=1
        if count==2:
            raise OSError('synthetic interruption')
        publish(source,target)
    monkeypatch.setattr(storage,'_publish',interrupted)
    with pytest.raises(OSError):
        storage.migrate(layout)
    assert not (layout.data/storage.RECEIPT).exists()
    monkeypatch.setattr(storage,'_publish',publish)
    storage.migrate(layout)
    layout.backend('memories.json').unlink()
    layout.backend('projects.json').write_bytes(b'new user edits')
    storage.migrate(layout)
    storage.migrate(replace(layout,root=layout.root.parent/'new-install-prefix'))
    assert not layout.backend('memories.json').exists()
    assert layout.backend('projects.json').read_bytes()==b'new user edits'


def test_locator_interruption_resumes(layout, monkeypatch):
    publish=storage._publish
    def fail_receipt(source,target):
        if target.name==storage.RECEIPT:
            raise OSError('synthetic crash after locator')
        publish(source,target)
    monkeypatch.setattr(storage,'_publish',fail_receipt)
    with pytest.raises(OSError):
        storage.migrate(layout)
    monkeypatch.setattr(storage,'_publish',publish)
    storage.migrate(layout)
    assert (layout.data/storage.RECEIPT).is_file()


@pytest.mark.parametrize('changed', ['data','config'])
def test_changed_xdg_location_is_not_silently_reimported(layout,changed):
    storage.migrate(layout)
    with pytest.raises(storage.StorageMigrationError,match='измен'):
        storage.migrate(replace(layout,**{changed:getattr(layout,changed).with_name('changed')}))


def test_overlap_is_rejected_before_walking_or_copying(layout):
    with pytest.raises(storage.StorageMigrationError,match='пересека'):
        storage.migrate(replace(layout,data=layout.root/'backend/data/nested'))
    with pytest.raises(storage.StorageMigrationError,match='пересека'):
        storage.migrate(replace(layout,cache=layout.config))


@pytest.mark.skipif(os.name=='nt',reason='Unprivileged POSIX symlink fixture')
@pytest.mark.parametrize('target', ['source','destination','parent'])
def test_symlinks_are_preserved_and_migration_refuses_them(layout, target):
    foreign=layout.root.parent/'foreign'
    foreign.mkdir()
    (foreign/'private').write_bytes(b'protected')
    if target=='source':
        (layout.root/'backend/data/link').symlink_to(foreign,target_is_directory=True)
    elif target=='destination':
        layout.data.parent.mkdir(parents=True,exist_ok=True)
        layout.data.symlink_to(foreign,target_is_directory=True)
    else:
        layout.config.parent.mkdir(parents=True,exist_ok=True)
        layout.config.parent.rename(layout.config.parent.with_name('old-config'))
        layout.config.parent.symlink_to(foreign,target_is_directory=True)
    with pytest.raises(storage.StorageMigrationError,match='ссылк'):
        storage.migrate(layout)
    assert (foreign/'private').read_bytes()==b'protected'
    assert sorted(p.name for p in foreign.iterdir())==['private']


def test_changing_source_aborts_before_publication(layout, monkeypatch):
    source=layout.root/'backend/data/memories.json'
    source.write_bytes(b'old')
    snapshot=storage._snapshot
    def mutate(source,target):
        snapshot(source,target)
        source.write_bytes(b'concurrent edit')
    monkeypatch.setattr(storage,'_snapshot',mutate)
    with pytest.raises(storage.StorageMigrationError,match='изменились'):
        storage.migrate(layout)
    assert not layout.backend('memories.json').exists()


def test_wal_commit_during_migration_is_detected(layout, monkeypatch):
    source=layout.root/'backend/data/history.sqlite3'
    connection=sqlite3.connect(source)
    try:
        connection.execute('pragma journal_mode=wal')
        connection.execute('create table messages(text)')
        connection.commit()
        snapshot=storage._snapshot
        def concurrent_commit(source,target):
            snapshot(source,target)
            connection.execute("insert into messages values ('concurrent')")
            connection.commit()
        monkeypatch.setattr(storage,'_snapshot',concurrent_commit)
        with pytest.raises(storage.StorageMigrationError,match='изменились'):
            storage.migrate(layout)
        assert not layout.backend('history.sqlite3').exists()
    finally:
        connection.close()


def test_killed_process_releases_lock_and_next_process_resumes(layout):
    for name in ('memories.json','projects.json'):
        (layout.root/'backend/data'/name).write_bytes(name.encode())
    ready=layout.root.parent/'child-published'
    script='''import sys,time
from pathlib import Path
import storage_paths as s
layout=s.Layout(*(Path(p) for p in sys.argv[1:5]),True)
original=s._publish
def publish(source,target):
    if target.name.startswith('.migration-source'):
        original(source,target)
        return
    original(source,target)
    Path(sys.argv[5]).write_bytes(b'ready')
    time.sleep(30)
s._publish=publish
s.migrate(layout)
'''
    child=subprocess.Popen([sys.executable,'-B','-c',script,str(layout.root),str(layout.data),
        str(layout.config),str(layout.cache),str(ready)],stdout=subprocess.PIPE,stderr=subprocess.PIPE,
        env=dict(os.environ,PYTHONPATH=str(Path(storage.__file__).parent)),
        creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    try:
        deadline=time.monotonic()+10
        while not ready.exists() and child.poll() is None and time.monotonic()<deadline:
            time.sleep(.03)
        assert ready.exists(), 'Child did not publish the synthetic fixture file'
    finally:
        if child.poll() is None:
            child.kill()
        child.communicate(timeout=10)
    # A new application prefix must finish the original interrupted migration.
    next_prefix=layout.root.parent/'new-install'
    next_prefix.mkdir()
    storage.migrate(replace(layout,root=next_prefix))
    for name in ('memories.json','projects.json'):
        assert layout.backend(name).read_bytes()==name.encode()
    assert (layout.data/storage.RECEIPT).is_file()


def test_weights_and_old_audio_are_not_duplicated(layout,monkeypatch):
    for name in ('models/whisper/small.pt','semantic-model/revision/model.onnx'):
        source=layout.root/'backend/data'/name
        source.parent.mkdir(parents=True)
        source.write_bytes(b'protected synthetic weights')
    (layout.root/'audio_cache').mkdir()
    (layout.root/'audio_cache/old.wav').write_bytes(b'old cache')
    monkeypatch.setattr(storage,'current',lambda:layout)
    storage.migrate(layout)
    assert storage.model_directory('semantic-model')==layout.root/'backend/data/semantic-model'
    assert not layout.backend('models').exists()
    assert not layout.backend('semantic-model').exists()
    assert storage.audio_cache()==layout.cache/'audio'
    assert not (layout.cache/'audio/old.wav').exists()
    assert (layout.root/'audio_cache/old.wav').read_bytes()==b'old cache'


def test_new_install_prefix_can_reuse_original_weights(layout,monkeypatch):
    model=layout.root/'backend/data/models/whisper/small.pt'
    model.parent.mkdir(parents=True)
    model.write_bytes(b'protected fixture weights')
    storage.migrate(layout)
    next_layout=replace(layout,root=layout.root.parent/'next-install')
    monkeypatch.setattr(storage,'current',lambda:next_layout)
    assert storage.model_directory('models/whisper')==model.parent
    assert not (layout.cache/'models').exists()


@pytest.mark.skipif(os.name=='nt',reason='POSIX permissions and advisory lock')
def test_private_modes_and_lock_timeout(layout):
    (layout.root/'.env').write_bytes(b'SYNTHETIC=1')
    storage.migrate(layout)
    for directory in (layout.data,layout.config,layout.cache):
        assert stat.S_IMODE(directory.stat().st_mode)==0o700
    assert stat.S_IMODE(layout.environment.stat().st_mode)==0o600
    script='import sys; from pathlib import Path; import storage_paths as s\nwith s._migration_lock(Path(sys.argv[1]),timeout=.1): pass'
    with storage._migration_lock(layout.data):
        result=subprocess.run([sys.executable,'-c',script,str(layout.data)],capture_output=True,text=True,
                              env=dict(os.environ,PYTHONPATH=str(Path(storage.__file__).parent)),timeout=10)
    assert result.returncode!=0 and 'StorageMigrationError' in result.stderr
    # The OS releases locks when a process dies; the persistent lock file is safe.
    with storage._migration_lock(layout.data,timeout=.1):
        pass
