"""Validate a Linux package using synthetic data and a disposable installation."""
import argparse
import hashlib
import os
from pathlib import Path
import subprocess

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--package', type=Path, required=True)
args = parser.parse_args()
source = args.package.resolve()
temporary = Path(os.environ['RUNNER_TEMP']).resolve()
prefix = temporary/'Scott AI package'
assert not prefix.exists()
assert source.is_dir() and (source/'launcher/ScottAIQt').is_file()
def install():
    subprocess.run(['bash', str(source/'install.sh'), '--prefix', str(prefix), '--no-shortcut'], check=True)
install()
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
subprocess.run(['bash', str(prefix/'uninstall.sh')], check=True)
intact()
assert not (prefix/'launcher/ScottAIQt').exists()
install()
intact()
assert (prefix/'runtime/bin/python').is_file()
assert (prefix/'launcher/ScottAIQt').read_bytes() == (source/'launcher/ScottAIQt').read_bytes()
assert not (source/'backend/data').exists()
assert not (source/'.env').exists()
print('Installation, upgrade, data retention, uninstall and reinstall passed.')
