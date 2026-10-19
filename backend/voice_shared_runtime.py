"""Reuse one pinned, application-owned CUDA runtime for a new private Voice venv.

No Torch imports here. Existing independent environments are never converted.
The private SDK remains first on sys.path; pip cannot uninstall packages outside
its venv. A binding is invalidated when the base distribution changes.
"""
from __future__ import annotations

import hashlib
from functools import lru_cache
import json
import os
from pathlib import Path
import subprocess
import uuid

try:
    from .scott_voice_sdk import TORCH
except ImportError:
    from scott_voice_sdk import TORCH
LEGACY_TORCH = ('2.9.1+cu126',)
MANIFEST = 'scott-shared-runtime.json'
HOOK = 'scott_base_runtime.pth'
HEADER = '# ScottAI shared runtime v1\n'


class SharedRuntimeError(ValueError):
    code = 'runtime_update_required'


def site_path(home):
    return Path(home)/'experiments/voice_design/.venv/Lib/site-packages'


def _hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


@lru_cache(maxsize=4)
def _metadata_hash(snapshot):
    digest = hashlib.sha256()
    for name, modified, size in snapshot:
        digest.update(Path(name).name.encode())
        digest.update(Path(name).parent.name.encode())
        digest.update(Path(name).read_bytes())
    return digest.hexdigest()


def _base_fingerprint(site, root):
    # The appended base also supplies SDK dependencies already present there.
    # Track every distribution, not just Torch, so a base upgrade cannot
    # silently change the private SDK's inherited dependencies.
    files = sorted([*site.glob('*.dist-info/METADATA'), *site.glob('*.dist-info/RECORD'), *site.glob('*.pth')])
    if not all(_owned(path, root) for path in files):
        raise ValueError('Redirected base metadata')
    snapshot = tuple((str(path), path.stat().st_mtime_ns, path.stat().st_size) for path in files)
    return _metadata_hash(snapshot)


def _owned(path, root):
    path, root = Path(path).absolute(), Path(root).resolve()
    if not path.is_relative_to(root) or not path.resolve().is_relative_to(root):
        return False
    while path != root:
        if path.is_symlink() or (hasattr(path, 'is_junction') and path.is_junction()):
            return False
        path = path.parent
    return True


def _base(root):
    root = Path(root).resolve()
    site = root/'runtime/Lib/site-packages'
    python = root/'runtime/python.exe'
    metadata = site/f'torch-{TORCH}.dist-info'
    try:
        if not all(_owned(path, root) for path in (python, site, metadata,
                metadata/'METADATA', metadata/'WHEEL', metadata/'RECORD')):
            return None
        if not python.is_file() or not _owned(site/'torch/__init__.py', root) or not (site/'torch/__init__.py').is_file():
            return None
        info = (metadata/'METADATA').read_text(encoding='utf-8')
        wheel = (metadata/'WHEEL').read_text(encoding='utf-8')
        if f'\nVersion: {TORCH}\n' not in '\n'+info or 'cp313-cp313-win_amd64' not in wheel:
            return None
        return dict(root=str(root), site=str(site), python=str(python),
                    record_sha256=_hash(metadata/'RECORD'), base_sha256=_base_fingerprint(site, root),
                    torch=TORCH, abi='cp313-win_amd64')
    except (OSError, ValueError):
        return None


def candidate(home, root):
    """Cheap conservative estimate. Actual activation also probes CUDA in a child."""
    if os.name != 'nt' or (site_path(home)/'torch').exists() or \
            Path(home).resolve().drive.lower() != Path(root).resolve().drive.lower():
        return None
    return _base(root)


def _hook_text(home, root):
    relative = os.path.relpath(Path(root)/'runtime/Lib/site-packages', site_path(home))
    if any(c in relative for c in '\r\n'):
        raise SharedRuntimeError('Путь установки содержит перевод строки; выберите другую папку.')
    return HEADER+relative.replace('\\', '/')+'\n'


def _binding(home):
    """Recognize only our own pair, including an interrupted write before .pth."""
    home = Path(home).resolve()
    marker, hook = home/MANIFEST, site_path(home)/HOOK
    if not marker.exists() and not hook.exists():
        return None
    try:
        if not _owned(marker, home) or not _owned(hook, home):
            raise ValueError()
        value = json.loads(marker.read_text(encoding='utf-8'))
        if value.get('version') != 1 or value.get('torch') not in (TORCH,*LEGACY_TORCH) or value.get('abi') != 'cp313-win_amd64':
            raise ValueError()
        root = (home/value['root']).resolve()
        expected = _hook_text(home, root)
        if value.get('hook_sha256') != hashlib.sha256(expected.encode()).hexdigest():
            raise ValueError()
        if hook.exists() and hook.read_text(encoding='utf-8') != expected:
            raise ValueError()
        if not isinstance(value.get('record_sha256'), str) or len(value['record_sha256']) != 64:
            raise ValueError()
        return value, root, hook.exists()
    except (OSError, ValueError, TypeError, KeyError):
        raise SharedRuntimeError('Связь окружений Scott Voice повреждена. Обновите голос в отдельной папке; файлы сохранены.') from None


def fingerprint(home):
    binding = _binding(home)
    if not binding:
        return None
    value, root, hook_ready = binding
    base = _base(root)
    if value.get('torch') != TORCH or not hook_ready or not base or base['record_sha256'] != value['record_sha256'] or \
            base['base_sha256'] != value.get('base_sha256') or (site_path(home)/'torch').exists():
        raise SharedRuntimeError('Основное окружение изменилось. Обновите Scott Voice в настройках голоса.')
    return value['base_sha256']


def config_home(config):
    worker = Path(config.worker)
    if worker.name == 'voice_worker.py' and worker.parent.name == 'voice_design' and worker.parent.parent.name == 'experiments':
        return worker.parents[2]
    return None


def config_fingerprint(config):
    home = config_home(config)
    shared = fingerprint(home) if home is not None else None
    python = Path(config.python) if hasattr(config,'python') else None
    if python is None or python.parent.name not in ('Scripts','bin'):
        return shared
    venv = python.parent.parent
    sites = [venv/'Lib/site-packages',*venv.glob('lib/python*/site-packages')]
    names=('torch','torchaudio','qwen_tts','transformers','accelerate')
    files=sorted(path for site in sites for path in site.glob('*.dist-info/METADATA')
                 if any(path.parent.name.startswith(name+'-') for name in names))
    if not files:
        return shared
    if not all(_owned(path,venv) for path in files):
        raise SharedRuntimeError('Файлы библиотек голоса перенаправлены. Обновите Scott Voice в отдельной папке.')
    value=dict(shared=shared,packages=_metadata_hash(tuple((str(path),path.stat().st_mtime_ns,path.stat().st_size) for path in files)))
    return hashlib.sha256(json.dumps(value,sort_keys=True).encode()).hexdigest()


def _write(path, text):
    path = Path(path)
    temporary = path.with_name(path.name+'.'+uuid.uuid4().hex+'.tmp')
    try:
        with temporary.open('w', encoding='utf-8', newline='\n') as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def configure(home, root, *, run=subprocess.run, env=None):
    """Call after venv creation, before pip. Return whether sharing is active.

    A changed/missing base detaches our own hook and uses a private Torch on
    repair. Unknown hooks/manifests are preserved and require a separate home.
    """
    home, root = Path(home).resolve(), Path(root).resolve()
    binding = _binding(home)
    base = candidate(home, root)
    # A valid old binding can also be re-established after moving the app.
    if binding:
        value, old_root, ready = binding
        upgraded = value['torch'] in LEGACY_TORCH and base and old_root == root
        if not upgraded and (not base or old_root != root or base['record_sha256'] != value['record_sha256'] or \
                (value.get('base_sha256') is not None and value['base_sha256'] != base['base_sha256'])):
            # _binding established ownership/content before either removal.
            (site_path(home)/HOOK).unlink(missing_ok=True)
            (home/MANIFEST).unlink()
            base = None  # Repair conservatively into an independent runtime.
    if base is None:
        return False
    probe = ('import json,struct,sys,torch; print(json.dumps(dict('
             'python=list(sys.version_info[:2]),bits=struct.calcsize("P")*8,'
             'version=torch.__version__,cuda=torch.cuda.is_available(),path=torch.__file__)))')
    try:
        result = run([base['python'], '-c', probe], check=True, capture_output=True,
                     text=True, env=env, timeout=45)
        info = json.loads(result.stdout.strip())
        valid = (info.get('python') == [3, 13] and info.get('bits') == 64 and info.get('version') == TORCH
                 and info.get('cuda') is True and Path(info['path']).resolve().is_relative_to(Path(base['site'])/'torch'))
    except (OSError, subprocess.SubprocessError, ValueError, KeyError, TypeError):
        valid = False
    if not valid:
        if binding:
            (site_path(home)/HOOK).unlink(missing_ok=True)
            (home/MANIFEST).unlink(missing_ok=True)
        return False
    if not _owned(site_path(home), home) or not site_path(home).is_dir():
        raise SharedRuntimeError('Неверный путь отдельного окружения Scott Voice.')
    hook = _hook_text(home, root)
    value = dict(version=1, root=os.path.relpath(root, home), torch=TORCH, abi='cp313-win_amd64',
                 record_sha256=base['record_sha256'], base_sha256=base['base_sha256'],
                 hook_sha256=hashlib.sha256(hook.encode()).hexdigest())
    # A crash between these writes is recoverable by configure; runtime rejects
    # the incomplete pair instead of accidentally using a different dependency.
    _write(home/MANIFEST, json.dumps(value, sort_keys=True))
    _write(site_path(home)/HOOK, hook)
    return True
