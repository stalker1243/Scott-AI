"""Validate a Linux package using synthetic data and a disposable installation."""
import argparse
import hashlib
import os
from pathlib import Path
import subprocess
import sys
import json

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--package', type=Path, required=True)
args = parser.parse_args()
source = args.package.resolve()
temporary = Path(os.environ['RUNNER_TEMP']).resolve()
prefix = temporary/'Scott AI package'
assert not prefix.exists()
assert source.is_dir() and (source/'launcher/ScottAIQt').is_file()

# Any accidental call to a host Python through PATH must fail.
denied = temporary/'denied-python'
denied.mkdir(exist_ok=True)
for name in ('python', 'python3'):
    file = denied/name
    file.write_text('#!/bin/sh\necho "Host Python must not be used" >&2\nexit 86\n')
    file.chmod(0o755)
install_env = dict(os.environ, PATH=str(denied)+os.pathsep+os.environ['PATH'])

def runtime_check():
    code = ('import sys,ssl,sqlite3,bz2,lzma,ctypes,json; '
            'assert sys.version_info[:2] == (3,13); '
            f'assert sys.base_prefix == {str(prefix/"python-runtime")!r}; '
            'assert ssl.create_default_context().cert_store_stats()["x509_ca"] > 0; '
            'print(json.dumps({"version":sys.version.split()[0],"base":sys.base_prefix}))')
    subprocess.run([str(prefix/'runtime/bin/python'), '-I', '-c', code], check=True)
def install():
    subprocess.run(['/bin/bash', str(source/'install.sh'), '--prefix', str(prefix), '--no-shortcut'],
                   check=True, env=install_env)
install()
runtime_check()
files = {'backend/data/chats/synthetic.json': b'{"messages":[]}',
         'backend/data/ai_config.json': b'{"provider":"synthetic"}',
         '.env': b'SCOTT_PACKAGE_TEST=1\n'}
for name, payload in files.items():
    target = prefix/name
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(payload)
def intact():
    assert all((prefix/name).read_bytes() == payload for name, payload in files.items())
install()
intact()
runtime_check()
subprocess.run(['bash', str(prefix/'uninstall.sh')], check=True)
intact()
assert not (prefix/'launcher/ScottAIQt').exists()
install()
intact()
runtime_check()
assert (prefix/'runtime/bin/python').is_file()
assert (prefix/'launcher/ScottAIQt').read_bytes() == (source/'launcher/ScottAIQt').read_bytes()
assert not (source/'backend/data').exists()
assert not (source/'.env').exists()

# Simulate an earlier installation whose environment used an external Python.
legacy = temporary/'Scott AI legacy'
assert not legacy.exists()
legacy.mkdir()
subprocess.run([sys.executable, '-m', 'venv', str(legacy/'runtime')], check=True)
(legacy/'.scott-linux-install.json').write_text(json.dumps({'files':[], 'runtime_owned':True}))
(legacy/'backend/data').mkdir(parents=True)
(legacy/'backend/data/synthetic.json').write_bytes(b'{"legacy":true}')
subprocess.run(['/bin/bash', str(source/'install.sh'), '--prefix', str(legacy), '--no-shortcut'],
               check=True, env=install_env)
assert (legacy/'backend/data/synthetic.json').read_bytes() == b'{"legacy":true}'
subprocess.run([str(legacy/'runtime/bin/python'), '-I', '-c',
                f'import sys; assert sys.base_prefix == {str(legacy/"python-runtime")!r}'], check=True)
assert not list(legacy.glob('.runtime-before-*'))
print('Installation, legacy upgrade, data retention, uninstall and reinstall passed with bundled Python.')
