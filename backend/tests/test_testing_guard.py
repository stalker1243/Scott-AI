"""The test subprocess cannot read or replace protected working stores."""
from pathlib import Path
import subprocess
import sys

import pytest

pytestmark = pytest.mark.unit


@pytest.mark.parametrize('operation', ['read', 'write', 'sqlite', 'remove', 'rename', 'scan'])
def test_guard_blocks_accidental_access(tmp_path, operation):
    protected = tmp_path/'working'
    protected.mkdir()
    path = protected/'history.sqlite3'
    path.write_bytes(b'preserved')
    source = tmp_path/'candidate.sqlite3'
    source.write_bytes(b'candidate')
    script = '''
import os,sqlite3,sys
from pathlib import Path
from testing_guard import install
directory,path,source=map(Path,sys.argv[1:4]); operation=sys.argv[4]
install([directory])
try:
    if operation=='read':path.read_bytes()
    elif operation=='write':path.write_bytes(b'changed')
    elif operation=='sqlite':sqlite3.connect(path.as_uri()+'?mode=ro',uri=True)
    elif operation=='remove':path.unlink()
    elif operation=='rename':os.replace(source,path)
    elif operation=='scan':list(directory.iterdir())
except PermissionError:
    print('protected')
else:
    raise AssertionError('Working data was accessed')
'''
    result = subprocess.run([sys.executable, '-c', script, str(protected), str(path), str(source), operation],
                            capture_output=True, text=True, timeout=5)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == 'protected'
    assert path.read_bytes() == b'preserved' and source.read_bytes() == b'candidate'


def test_guard_allows_temporary_test_store(tmp_path):
    script = '''
import sys,sqlite3
from pathlib import Path
from testing_guard import install
allowed=Path(sys.argv[1]);protected=allowed/'working'
install([protected])
path=allowed/'temporary.sqlite3'
with sqlite3.connect(path) as db:
    db.execute('CREATE TABLE test (value)')
    db.execute('INSERT INTO test VALUES (1)')
db.close()
path.unlink()
print('isolated')
'''
    result = subprocess.run([sys.executable, '-c', script, str(tmp_path)], capture_output=True, text=True, timeout=5)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == 'isolated'
