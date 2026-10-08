"""Build a native Qt Linux package. Run on Linux x86-64 with Qt 6.8+."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tarfile

import build as shared
from linux_python import copy_python

ROOT = Path(__file__).resolve().parents[1]


def new_output(path: Path) -> Path:
    output = path.resolve()
    if not output.is_relative_to(ROOT.resolve()) or output == ROOT.resolve():
        raise ValueError('Output must be inside the project.')
    if output.exists():
        raise ValueError('Output already exists; choose a new directory.')
    return output


def build(output: Path, qt_root: Path, jobs: int) -> Path:
    build_dir = ROOT / 'ScottAI_qt' / 'build-linux'
    subprocess.run(['cmake', '-S', str(ROOT/'ScottAI_qt'), '-B', str(build_dir),
                    '-G', 'Ninja', '-DCMAKE_BUILD_TYPE=Release',
                    f'-DCMAKE_PREFIX_PATH={qt_root}', f'-DCMAKE_INSTALL_PREFIX={output}'], check=True)
    subprocess.run(['cmake', '--build', str(build_dir), '--parallel', str(jobs)], check=True)
    subprocess.run(['cmake', '--install', str(build_dir)], check=True)
    copy_python(output)
    shared.copy_backend(output)
    shared.copy_voice_assets(output)
    shared.copy_extras(output)
    shutil.copytree(ROOT/'assets/brand', output/'assets/brand', dirs_exist_ok=True)
    shutil.copytree(ROOT/'installer/licenses', output/'licenses', dirs_exist_ok=True)
    if (qt_root/'sbom').is_dir():
        shutil.copytree(qt_root/'sbom', output/'licenses/qt-sbom', dirs_exist_ok=True)
    for name in ('install.py', 'install.sh', 'uninstall.sh', 'run.sh', 'python-environment.sh'):
        target = output/name
        shutil.copy2(ROOT/'installer/linux'/name, target)
        target.chmod(0o755)
    if not (output/'launcher/ScottAIQt').is_file():
        raise RuntimeError('Qt executable is missing.')
    if not list((output/'lib').glob('libQt6Core.so*')):
        raise RuntimeError('Qt libraries were not deployed.')
    return output


def pack(output: Path) -> Path:
    version = shared.read_version()
    release = ROOT/'installer/release'
    release.mkdir(parents=True, exist_ok=True)
    name = f'ScottAI-{version}-Qt-linux-x86_64'
    archive = release/f'{name}.tar.gz'
    if archive.exists():
        raise ValueError('Linux archive already exists; refusing to overwrite it.')
    def permissions(info: tarfile.TarInfo) -> tarfile.TarInfo:
        info.uid = info.gid = 0
        info.uname = info.gname = 'root'
        return info
    with tarfile.open(archive, 'w:gz') as tar:
        tar.add(output, arcname=name, filter=permissions)
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    archive.with_suffix('.gz.sha256').write_text(f'{digest}  {archive.name}\n', encoding='ascii')
    print(json.dumps({'archive': str(archive), 'bytes': archive.stat().st_size, 'sha256': digest}))
    return archive


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--qt-root', type=Path, default=os.environ.get('QT_ROOT_DIR'))
    parser.add_argument('--output', type=Path, default=ROOT/'installer/dist-linux-qt')
    parser.add_argument('--jobs', type=int, default=4)
    args = parser.parse_args()
    if sys.platform != 'linux' or platform.machine() not in ('x86_64', 'amd64'):
        parser.error('Build this package on Linux x86-64 (for example Ubuntu 24.04).')
    if args.qt_root is None or not args.qt_root.is_dir():
        parser.error('Set --qt-root or QT_ROOT_DIR to the Qt SDK directory.')
    if not 1 <= args.jobs <= 16:
        parser.error('--jobs must be between 1 and 16.')
    try:
        pack(build(new_output(args.output), args.qt_root.resolve(), args.jobs))
    except (ValueError, RuntimeError, subprocess.CalledProcessError) as error:
        parser.exit(1, f'{error}\n')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
