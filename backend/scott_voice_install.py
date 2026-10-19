"""Optional Scott Voice provisioning; --plan and --check never install anything."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import struct
import uuid
import psutil
import subprocess
import sys
import time

try:
    from .scott_voice_sdk import REQUIREMENTS, TORCH, TORCHAUDIO, WHEEL, WHEEL_SHA256
except ImportError:
    from scott_voice_sdk import REQUIREMENTS, TORCH, TORCHAUDIO, WHEEL, WHEEL_SHA256

try:
    from .voice_install_errors import InstallationError, MESSAGES, child_failure, failure_code
except ImportError:
    from voice_install_errors import InstallationError, MESSAGES, child_failure, failure_code

ROOT = Path(__file__).resolve().parent.parent
MODEL = 'Qwen/Qwen3-TTS-12Hz-0.6B-Base'
REVISION = '5d83992436eae1d760afd27aff78a71d676296fc'
REFERENCE_SHA = '78f48237579b5323bd5e738095fa17f4c30f1f76d8976e66ef128b850eea42f3'
TORCH_INDEX = 'https://download.pytorch.org/whl/cu126'
ASSETS = tuple('experiments/voice_design/'+name for name in (
    'voice_worker.py', 'trial_utils.py', 'generate_samples.py', 'evaluate_samples.py',
    'create_scott_voice.py', 'robotic_profiles.json', 'stream_voice.py')) + (
    WHEEL, 'assets/scott-voice/vendor/provenance.json', 'assets/scott-voice/vendor/NOTICE.txt',
    'reports/voice-design/reference/reference.json',
    'reports/voice-design/reference/scott-reference.wav')
CLIENT_FILES = ('backend/scott_voice_process.py', 'backend/voice_shared_runtime.py', 'backend/scott_voice_sdk.py', 'backend/voice_cache.py',
                'backend/speech_text.py')
MODEL_FILES = ('config.json', 'generation_config.json', 'merges.txt', 'model.safetensors',
    'preprocessor_config.json', 'tokenizer_config.json', 'vocab.json',
    'speech_tokenizer/config.json', 'speech_tokenizer/configuration.json',
    'speech_tokenizer/model.safetensors', 'speech_tokenizer/preprocessor_config.json')


def preflight_nvidia():
    """Fail before large downloads when the NVIDIA driver cannot be queried."""
    try:
        result = subprocess.run(['nvidia-smi', '--query-gpu=name,driver_version,memory.total', '--format=csv,noheader'],
            capture_output=True, text=True, timeout=15, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        if result.returncode != 0 or not result.stdout.strip():
            raise OSError('NVIDIA driver unavailable')
    except (OSError, subprocess.SubprocessError):
        raise InstallationError('Драйвер NVIDIA не отвечает. Установите или обновите драйвер, перезагрузите компьютер и повторите установку Scott Voice. Обычный голос остаётся доступен.', 'cuda_unavailable') from None
    try:
        from .support_logs import append_log
    except ImportError:
        from support_logs import append_log
    append_log('scott-voice-install.log', 'NVIDIA: '+result.stdout.strip())


def home_path(root=ROOT):
    value = os.getenv('SCOTT_VOICE_HOME', '').strip()
    if value:
        return Path(value).expanduser().resolve()
    try:
        from .storage_paths import layout_for
    except ImportError:
        from storage_paths import layout_for
    layout = layout_for(root)
    legacy = Path(root)/'voice-runtime'
    # Preserve existing venvs in place; new installed-Linux voices live outside
    # the application/mount. Explicit overrides retain their previous meaning.
    if layout.external and not (legacy/'scott-install.json').is_file():
        return layout.data/'components/voice-runtime'
    return legacy


def python_path(home):
    return Path(home)/'experiments/voice_design/.venv'/('Scripts/python.exe' if os.name == 'nt' else 'bin/python')


def checksum(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(8*1024*1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path, value):
    temporary = Path(path).with_suffix('.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
    os.replace(temporary, path)


def asset_sources(root=ROOT):
    root = Path(root)
    packed = root/'voice-assets'
    source = packed if packed.is_dir() else root
    result = {name: source/name for name in ASSETS}
    if source == root:
        public = root/'assets/scott-voice/reference'
        for name in ASSETS[-2:]:
            candidate = public/Path(name).name
            if candidate.is_file():
                result[name] = candidate
    result.update({name: root/name for name in CLIENT_FILES})
    if any(not path.is_file() or path.is_symlink() or not path.resolve().is_relative_to(root.resolve())
           for path in result.values()):
        raise ValueError('Неполный пакет исходников Scott Voice.')
    reference = result[ASSETS[-1]]
    metadata = json.loads(result[ASSETS[-2]].read_text(encoding='utf-8'))
    if metadata.get('sha256') != REFERENCE_SHA or checksum(reference) != REFERENCE_SHA:
        raise ValueError('Контрольная сумма принятого эталона не совпадает.')
    if checksum(result[WHEEL]) != WHEEL_SHA256:
        raise ValueError('Повреждён пакет совместимости Scott Voice. Загрузите приложение повторно.')
    # A built package also seals scripts/profiles, not just the accepted voice.
    if source == packed:
        manifest = json.loads((packed/'assets.json').read_text(encoding='utf-8'))
        if set(manifest.get('files', {})) != set(ASSETS):
            raise ValueError('Неверный перечень файлов Scott Voice.')
        for name in ASSETS:
            if checksum(result[name]) != manifest['files'][name]:
                raise ValueError('Повреждён файл пакета Scott Voice: '+name)
    return result


def bundle_assets(destination, root=ROOT):
    """Whitelist only runtime helpers and the accepted synthetic reference."""
    sources = asset_sources(root)
    legacy=Path(root)/('voice-assets/legacy-assets-v1.json' if (Path(root)/'voice-assets').is_dir()
                      else 'assets/scott-voice/legacy-assets-v1.json')
    destination = Path(destination)
    if destination.exists():
        raise ValueError('Папка пакета уже существует; выберите новую папку.')
    destination.mkdir(parents=True)
    manifest = {}
    for name in ASSETS:
        target = destination/name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(sources[name], target)
        manifest[name] = checksum(target)
    write_json(destination/'assets.json', dict(version=1, reference_sha256=REFERENCE_SHA, files=manifest))
    if legacy.is_file():
        shutil.copy2(legacy,destination/'legacy-assets-v1.json')
    (destination/'NOTICE.md').write_text(
        '# Scott Voice\n\n'
        'Synthetic reference accepted for ScottAI. Qwen weights and SDK are installed separately.\n'
        'Qwen3-TTS: https://github.com/QwenLM/Qwen3-TTS (Apache-2.0).\n'
        'Model: https://huggingface.co/'+MODEL+' (Apache-2.0).\n'
        'PyTorch packages: https://pytorch.org/get-started/previous-versions/.\n', encoding='utf-8')
    return dict(files=len(manifest), bytes=sum((destination/name).stat().st_size for name in ASSETS))


def plan(home, python, auto_python=False, root=ROOT):
    if auto_python:
        python = Path(home)/'python/tools/python.exe'
    environment = python_path(home)
    pip = [str(environment), '-m', 'pip', 'install', '--disable-pip-version-check', '--no-cache-dir', '--no-input',
           '--timeout', '30', '--retries', '3', '--prefer-binary']
    try:
        from .voice_shared_runtime import candidate
        from .installation_space import budget
    except ImportError:
        from voice_shared_runtime import candidate
        from installation_space import budget
    return dict(home=str(Path(home).resolve()), model=MODEL, revision=REVISION,
        reference_sha256=REFERENCE_SHA, device='cuda', platform='Windows x64 / Python 3.13',
        auto_python=auto_python, space=budget('voice_shared' if candidate(home, root) else 'voice', home),
        commands=[[str(python), '-m', 'venv', str(environment.parent.parent)],
                  pip+['--index-url', TORCH_INDEX, 'torch=='+TORCH, 'torchaudio=='+TORCHAUDIO],
                  pip+[str(Path(home)/WHEEL), *REQUIREMENTS[1:]], [str(environment), '-m', 'pip', 'check']],
        notes=['Установка отдельная; глобальные пакеты и настройки голоса не меняются.',
               'Совместимое ускорение основной установки используется повторно; готовые отдельные окружения сохраняются.',
               'Проверена NVIDIA/CUDA. AMD/CPU для этого движка ещё не проверены.',
               'После установки перезапустите backend и выберите голос в настройках.'])


def clean_environment():
    env = dict(os.environ)
    for key in tuple(env):
        upper = key.upper()
        if upper.endswith(('_API_KEY', '_TOKEN')) or upper in (
            'AWS_ACCESS_KEY_ID', 'AWS_SECRET_ACCESS_KEY', 'PYTHONPATH', 'PYTHONHOME',
            'HF_HUB_OFFLINE', 'TRANSFORMERS_OFFLINE', 'VIRTUAL_ENV') or upper.startswith('PIP_'):
            env.pop(key, None)
    env.update(PYTHONUTF8='1', PYTHONNOUSERSITE='1', HF_HUB_DISABLE_IMPLICIT_TOKEN='1',
               HF_HUB_DISABLE_XET='1', HF_HUB_DOWNLOAD_TIMEOUT='60', HF_HUB_ETAG_TIMEOUT='30',
               PIP_CONFIG_FILE=os.devnull)
    return env


def download_model(home, model_source=None, progress=None):
    """Pin the accepted revision; verify official LFS hashes before publishing."""
    # Called with the optional interpreter after installing its dependencies.
    destination = Path(home)/'experiments/voice_design/models/base'
    emit = progress or (lambda stage, message, fraction: print(message, flush=True))
    # A previous successful download can finish an interrupted installation offline.
    # Do not trust file existence or a ready marker: verify every pinned file again.
    manifest_path = destination/'scott-model.json'
    try:
        manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
        hashes = manifest.get('sha256', {})
        files = manifest.get('files')
        if (manifest.get('model') == MODEL and manifest.get('revision') == REVISION
                and isinstance(files, list) and set(MODEL_FILES).issubset(files)
                and set(files).issubset((*MODEL_FILES, 'README.md')) and set(MODEL_FILES).issubset(hashes)):
            emit('model', 'Проверяем уже скачанные файлы Scott Voice', .6)
            if all((destination/name).resolve().is_relative_to(Path(home).resolve())
                   and not (destination/name).is_symlink() and (destination/name).is_file()
                   and checksum(destination/name) == hashes[name] for name in MODEL_FILES):
                emit('model', 'Файлы Scott Voice проверены. Повторная загрузка не нужна', .9)
                return
    except (OSError, ValueError, TypeError, AttributeError):
        pass
    from huggingface_hub import HfApi, hf_hub_download

    def retry(operation, label, fraction):
        for attempt in range(3):
            try:
                return operation()
            except Exception as error:
                code = failure_code(error)
                if code not in ('network_unavailable', 'download_timeout', 'download_server') or attempt == 2:
                    if code:
                        raise InstallationError(MESSAGES[code], code) from error
                    raise
                emit('model', label + f': повтор {attempt + 2}/3, скачанные части сохранены', fraction)
                time.sleep(2 ** attempt)

    emit('model', 'Получаем список файлов Scott Voice', .6)
    info = retry(lambda: HfApi(token=False).model_info(MODEL, revision=REVISION, files_metadata=True, timeout=30),
                 'Список файлов', .6)
    if info.sha != REVISION:
        raise ValueError('Неверная версия модели.')
    items = {item.rfilename: item for item in info.siblings}
    if not set(MODEL_FILES).issubset(items):
        raise ValueError('Неполный официальный пакет модели.')
    hashes = {}
    for index, name in enumerate((*MODEL_FILES, 'README.md')):
        item = items.get(name)
        if item is None:
            continue
        target = destination/name
        if not target.resolve().is_relative_to(Path(home).resolve()) or target.is_symlink():
            raise ValueError('Путь модели выходит из выбранной папки.')
        def verified(path):
            if not path.is_file() or (item.size is not None and path.stat().st_size != item.size):
                return False
            if item.lfs:
                return checksum(path) == item.lfs.sha256
            # Ordinary Hub files use Git's SHA1 blob identity in official metadata.
            git = hashlib.sha1(b'blob '+str(path.stat().st_size).encode()+b'\0')
            with path.open('rb') as stream:
                for chunk in iter(lambda: stream.read(1024*1024), b''):
                    git.update(chunk)
            return git.hexdigest() == item.blob_id
        force = target.exists() and not verified(target)
        reusable = Path(model_source)/name if model_source else None
        if not target.exists() and reusable and verified(reusable):
            target.parent.mkdir(parents=True, exist_ok=True)
            temporary = target.with_suffix('.reuse')
            shutil.copyfile(reusable, temporary)
            if not verified(temporary):
                raise ValueError('Контрольная сумма копии модели не совпадает.')
            os.replace(temporary, target)
        fraction = .6 + .28 * index / (len(MODEL_FILES) + 1)
        emit('model', f'Файл {index + 1}/{len(MODEL_FILES) + 1}: {name}', fraction)
        backup = None
        if force:
            if not target.is_file():
                raise ValueError('Вместо файла модели находится папка: '+name)
            # force_download deletes the SDK's .incomplete on every retry.
            # Keep the invalid final file aside so the SDK can resume normally.
            backup = target.with_name(target.name+'.corrupt-'+uuid.uuid4().hex)
            os.replace(target, backup)
        try:
            path = target if verified(target) else Path(retry(lambda: hf_hub_download(MODEL, name, revision=REVISION, token=False,
                        local_dir=destination, cache_dir=Path(home)/'download-cache', force_download=False, etag_timeout=30), name, fraction))
            if path.resolve() != (destination/name).resolve() or not path.is_file():
                raise ValueError('Загрузчик вернул неверный путь.')
            actual = checksum(path)
            if not verified(path):
                raise ValueError('Контрольная сумма модели не совпадает: '+name)
        except BaseException:
            if backup:
                os.replace(backup, target)  # Restore the previous file; keep resumable parts.
            raise
        else:
            if backup:
                backup.unlink()
        hashes[name] = actual
        emit('model', 'Проверен файл модели: '+name, fraction)
    write_json(destination/'scott-model.json', dict(model=MODEL, revision=REVISION,
                files=list(hashes), sha256=hashes))


def check(home, deep=False):
    try:
        from .scott_voice_engine import config_at, inspect_installation, _probe_runtime
    except ImportError:
        from scott_voice_engine import config_at, inspect_installation, _probe_runtime
    config = config_at(home)
    if deep:
        # An installer repair may replace libraries at the same paths.
        clear = getattr(inspect_installation, 'cache_clear', None)
        if clear:
            clear()
        _probe_runtime.cache_clear()
    error = inspect_installation(config)
    if not error and deep:
        manifest = json.loads((config.model_dir/'scott-model.json').read_text(encoding='utf-8'))
        hashes = manifest.get('sha256', {})
        if not set(MODEL_FILES).issubset(hashes):
            error = 'missing_checksums'
        elif any(checksum(config.model_dir/name) != hashes[name] for name in MODEL_FILES):
            error = 'invalid_assets'
    return dict(available=not bool(error), error=error, device=config.device,
                home=str(Path(home).resolve()), deep=deep)


def install(home, python, root=ROOT, **options):
    home = Path(home).resolve()
    if os.name != 'nt' or struct.calcsize('P') != 8:
        raise ValueError('Этот установщик рассчитан на Windows x64; другие платформы ещё не проверены.')
    asset_sources(root)
    for name in ('python', 'download-cache', 'experiments/voice_design/.venv', 'experiments/voice_design/models'):
        target = home/name
        if not target.resolve().is_relative_to(home) or target.is_symlink() or target.is_junction():
            raise ValueError('Папка установки содержит перенаправление: '+name)
    marker = home/'scott-install.json'
    if home.exists() and not marker.is_file() and any(home.iterdir()):
        raise ValueError('В выбранной папке есть другие файлы; выберите отдельную пустую папку.')
    if marker.is_file():
        previous = json.loads(marker.read_text(encoding='utf-8'))
        if not isinstance(previous, dict) or previous.get('version') != 1 or previous.get('model') != MODEL or previous.get('revision') != REVISION:
            raise ValueError('В папке другая установка; выберите новую папку.')
    home.mkdir(parents=True, exist_ok=True)
    if not marker.is_file():
        write_json(marker, dict(version=1, model=MODEL, revision=REVISION, ready=False))
    lock = home/'installation.lock'
    token = dict(pid=os.getpid(), created=psutil.Process().create_time(), nonce=uuid.uuid4().hex)
    try:
        descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        try:
            old = json.loads(lock.read_text(encoding='utf-8'))
            try:
                owner = psutil.Process(old['pid'])
                alive = owner.create_time() == old['created'] and owner.is_running()
            except psutil.NoSuchProcess:
                alive = False
            if alive or not isinstance(old.get('nonce'), str):
                raise ValueError()
            if json.loads(lock.read_text(encoding='utf-8')) != old:
                raise ValueError()
            lock.unlink()
            descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except (OSError, ValueError, TypeError, KeyError, AssertionError):
            raise ValueError('Установка уже выполняется; проверьте installation.lock после завершения процесса.') from None
    with os.fdopen(descriptor, 'w', encoding='utf-8') as stream:
        json.dump(token, stream)
    try:
        return _install_owned(home, python, root, **options)
    finally:
        try:
            if lock.is_file() and json.loads(lock.read_text(encoding='utf-8')) == token:
                lock.unlink()
        except (OSError, ValueError):
            pass  # Never hide the installation error or remove somebody else's lock.


def _install_owned(home, python, root=ROOT, auto_python=False, progress=None, runner=None, model_source=None):
    home = Path(home).resolve()
    python = Path(python).resolve()
    run = runner or subprocess.run
    emit = runner.step if runner is not None and hasattr(runner, 'step') else progress or (lambda *args: None)
    if os.name != 'nt' or struct.calcsize('P') != 8:
        raise ValueError('Этот установщик рассчитан на Windows x64; другие платформы ещё не проверены.')
    sources = asset_sources(root)  # Validate before creating or changing anything.
    if not json.loads((home/'scott-install.json').read_text(encoding='utf-8')).get('ready'):
        preflight_nvidia()
    try:
        from .voice_shared_runtime import candidate, configure
        from .installation_space import require_space
    except ImportError:
        from voice_shared_runtime import candidate, configure
        from installation_space import require_space
    fresh = not python_path(home).is_file() and not (home/'experiments/voice_design/models/base/model.safetensors').exists()
    if fresh:
        require_space('voice_shared' if candidate(home, root) else 'voice', home)
    env = clean_environment()
    env['HF_HOME'] = str(home/'download-cache')
    if auto_python:
        # First establish an owned home; never place an interpreter in unrelated data.
        marker = home/'scott-install.json'
        if home.exists() and not marker.is_file() and any(home.iterdir()):
            raise ValueError('В выбранной папке есть другие файлы; выберите отдельную пустую папку.')
        if marker.is_file():
            previous = json.loads(marker.read_text(encoding='utf-8'))
            if previous.get('version') != 1 or previous.get('model') != MODEL or previous.get('revision') != REVISION:
                raise ValueError('В папке другая установка; выберите новую папку.')
        else:
            home.mkdir(parents=True, exist_ok=True)
            write_json(marker, dict(version=1, model=MODEL, revision=REVISION, ready=False))
        emit('python', 'Подготавливаем окружение', .05)
        try:
            from .voice_install_runtime import prepare_python
        except ImportError:
            from voice_install_runtime import prepare_python
        python = prepare_python(home, progress=emit, cancelled=runner.cancelled if runner else None)
    try:
        probe = run([str(python), '-c',
            'import sys,struct,venv; print(str(sys.version_info[:2])+":"+str(struct.calcsize("P")))'],
            check=True, capture_output=True, text=True, env=env, timeout=20)
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        raise ValueError('Нужен полный Python 3.13 x64 с модулем venv; используйте --python.') from None
    if probe.stdout.strip() != '(3, 13):8':
        raise ValueError('Нужен полный Python 3.13 x64 с модулем venv.')
    marker = home/'scott-install.json'
    if home.exists() and not marker.is_file() and any(home.iterdir()):
        raise ValueError('В выбранной папке есть другие файлы; выберите отдельную пустую папку.')
    if marker.is_file():
        previous = json.loads(marker.read_text(encoding='utf-8'))
        if not isinstance(previous, dict) or previous.get('version') != 1 or previous.get('model') != MODEL or previous.get('revision') != REVISION:
            raise ValueError('В папке другая установка; выберите новую папку.')
    for name in ('experiments/voice_design/.venv', 'experiments/voice_design/models', 'download-cache'):
        target = home/name
        if not target.resolve().is_relative_to(home) or target.is_symlink() or target.is_junction():
            raise ValueError('Папка установки содержит перенаправление: '+name)
    if python_path(home).exists():
        venv = python_path(home).parent.parent
        settings = (venv/'pyvenv.cfg').read_text(encoding='utf-8').lower()
        if 'include-system-site-packages = false' not in settings:
            raise ValueError('Окружение использует глобальные пакеты; выберите новую папку.')
    try:
        from .voice_asset_update import sync_assets, manifest as asset_manifest
    except ImportError:
        from voice_asset_update import sync_assets, manifest as asset_manifest
    legacy_path = Path(root)/('voice-assets/legacy-assets-v1.json' if (Path(root)/'voice-assets').is_dir()
                             else 'assets/scott-voice/legacy-assets-v1.json')
    if not marker.is_file():
        home.mkdir(parents=True, exist_ok=True)
        write_json(marker, dict(version=1, model=MODEL, revision=REVISION, ready=False))
    emit('verification', 'Проверяем файлы голоса', .1)
    sync_assets(home, sources, legacy=asset_manifest(legacy_path))
    if marker.is_file() and previous.get('ready') is True:
        emit('verification', 'Проверяем готовность голоса', .9)
        result = check(home, deep=True)
        if result['available']:
            emit('complete', 'Scott Voice готов', 1)
            return result  # Rechecking a complete installation never reinstalls packages.
    home.mkdir(parents=True, exist_ok=True)
    write_json(marker, dict(version=1, model=MODEL, revision=REVISION, ready=False))
    commands = plan(home, python, root=root)['commands']
    emit('environment', 'Подготавливаем окружение', .15)
    if not python_path(home).is_file():
        run(commands[0], check=True, env=env, timeout=120)
    shared = configure(home, root, run=run, env=env)
    if fresh and not shared:
        require_space('voice', home)
    if shared:
        emit('environment', 'Используем готовое ускорение основной установки', .18)
    # Resume interrupted model downloads without reinstalling ready libraries.
    ready_code = ('import importlib.metadata as m; '
        f'assert m.version("torch")=={TORCH!r} and m.version("torchaudio")=={TORCHAUDIO!r}; '
        f'assert all(m.version(r.split("==")[0])==r.split("==")[1] for r in {REQUIREMENTS!r}); '
        'import torch,torchaudio,qwen_tts')
    try:
        run([str(python_path(home)), '-c', ready_code], check=True, env=env, timeout=60)
        libraries_ready = True
    except (OSError, subprocess.SubprocessError):
        libraries_ready = False
    framework_ready = libraries_ready
    if not framework_ready:
        # A failed SDK/model step must not download an already installed 2.6 GB
        # framework again. Validate the exact pair independently of Qwen.
        framework_code = ('import importlib.metadata as m; '
            f'assert m.version("torch")=={TORCH!r} and m.version("torchaudio")=={TORCHAUDIO!r}; '
            'import torch,torchaudio')
        try:
            run([str(python_path(home)), '-c', framework_code],check=True,env=env,timeout=60)
            framework_ready = True
        except (OSError,subprocess.SubprocessError):
            pass
    for index, command in enumerate(commands[1:]):
        if libraries_ready and index < 2 or framework_ready and index == 0:
            continue
        emit('libraries', 'Устанавливаем библиотеки голоса', .2+index*.12)
        if index < 2:
            help_result = run([str(python_path(home)), '-m', 'pip', 'install', '--help'], check=True, capture_output=True, text=True, env=env, timeout=30)
            if '--resume-retries' in (getattr(help_result, 'stdout', '') or ''):
                command[4:4] = ['--resume-retries', '5']
        downloaded = None
        if index == 0 and not shared:
            try:
                from . import torch_download
            except ImportError:
                import torch_download
            wheel=torch_download.selected('cuda')
            if wheel is not None:
                last=[0.]
                def transfer(done,total):
                    if runner is not None and runner.cancelled.is_set():
                        try:
                            from .voice_install_runtime import InstallationCancelled
                        except ImportError:
                            from voice_install_runtime import InstallationCancelled
                        raise InstallationCancelled()
                    now=time.monotonic()
                    if done==total or now-last[0]>=.5:
                        last[0]=now
                        emit('libraries',f'Загружаем PyTorch: {done/1024**2:.1f} / {total/1024**2:.1f} МиБ',.2+.1*done/total)
                try:
                    downloaded=torch_download.fetch(wheel,home/'download-cache/torch',progress=transfer,
                        cancelled=runner.cancelled if runner is not None else None)
                except torch_download.DownloadError:
                    if runner is not None and runner.cancelled.is_set():
                        try:
                            from .voice_install_runtime import InstallationCancelled
                        except ImportError:
                            from voice_install_runtime import InstallationCancelled
                        raise InstallationCancelled() from None
                    raise
                command=[str(downloaded) if item=='torch=='+TORCH else item for item in command]
        run(command, check=True, env=env, timeout=3600 if index == 0 else 1800 if index == 1 else 60)
        if downloaded is not None:
            torch_download.discard(wheel,home/'download-cache/torch')
    emit('model', 'Подготавливаем файлы голоса', .6)
    download = [str(python_path(home)), str(Path(__file__).resolve()), '--download-model', '--json', '--home', str(home)]
    if model_source:
        download += ['--model-source', str(model_source)]
    run(download, check=True, env=env, timeout=3600)
    emit('verification', 'Проверяем готовность голоса', .9)
    result = check(home, deep=True)
    if not result['available']:
        raise ValueError('Окружение подготовлено, но проверка не прошла: '+result['error'])
    if runner is not None and runner.cancelled.is_set():
        try:
            from .voice_install_runtime import InstallationCancelled
        except ImportError:
            from voice_install_runtime import InstallationCancelled
        raise InstallationCancelled()
    write_json(marker, dict(version=1, model=MODEL, revision=REVISION, ready=True))
    emit('complete', 'Scott Voice готов', 1)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument('--plan', action='store_true', help='Показать план без установки (по умолчанию).')
    modes.add_argument('--check', action='store_true', help='Проверить окружение без установки.')
    modes.add_argument('--install', action='store_true', help='Установить отдельное окружение и веса.')
    modes.add_argument('--bundle', type=Path, help='Собрать малый пакет для установщика.')
    modes.add_argument('--download-model', action='store_true', help=argparse.SUPPRESS)
    parser.add_argument('--home', type=Path, default=home_path())
    parser.add_argument('--python', type=Path, default=Path(sys.executable))
    parser.add_argument('--deep', action='store_true', help='Сверить SHA256 всех весов при --check.')
    parser.add_argument('--auto-python', action='store_true', help='Подготовить отдельный Python автоматически.')
    parser.add_argument('--json', action='store_true', help='Сообщать ход установки JSON строками.')
    parser.add_argument('--model-source', type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    try:
        runner = None
        progress = None
        if args.json:
            def progress(stage, message, fraction):
                print(json.dumps(dict(type='progress', stage=stage, message=message, fraction=fraction), ensure_ascii=False), flush=True)
            try:
                from .voice_install_runtime import CancellableRunner
            except ImportError:
                from voice_install_runtime import CancellableRunner
            runner = CancellableRunner(progress)
            if not args.download_model:
                runner.watch_parent()
            import threading
            def cancel_input():
                # Buffered stdin locks can block inherited handles and Python shutdown.
                # Read the dedicated pipe directly; never hold sys.stdin's buffer lock.
                try:
                    descriptor = sys.stdin.fileno()
                    pending = b''
                    while block := os.read(descriptor, 128):
                        pending = (pending+block)[-256:]
                        while b'\n' in pending:
                            line, pending = pending.split(b'\n', 1)
                            if line.strip() == b'cancel':
                                runner.cancelled.set()
                                return
                except (OSError, ValueError):
                    return
            if not args.download_model:
                threading.Thread(target=cancel_input, daemon=True).start()
        if args.bundle:
            result = bundle_assets(args.bundle)
        elif args.install:
            result = install(args.home, args.python, auto_python=args.auto_python, progress=progress,
                             runner=runner, model_source=args.model_source)
        elif args.check:
            result = check(args.home, args.deep)
        elif args.download_model:
            download_model(args.home, args.model_source, progress)
            return 0
        else:
            result = plan(args.home, args.python, args.auto_python)
        if args.json:
            print(json.dumps(dict(type='result', **result), ensure_ascii=False), flush=True)
        else:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        return 1 if result.get('available') is False else 0
    except Exception as error:
        try:
            from .support_logs import append_log, redact
        except ImportError:
            from support_logs import append_log, redact
        detail = redact(str(getattr(error, 'stderr', '') or error))
        append_log('scott-voice-install.log', type(error).__name__+': '+detail)
        error = child_failure(error)
        if args.json:
            cancelled = type(error).__name__ == 'InstallationCancelled'
            code = getattr(error, 'code', 'timeout' if isinstance(error, subprocess.TimeoutExpired) else 'process_failed' if isinstance(error, subprocess.CalledProcessError) else 'install_failed')
            message = 'Установка отменена. Её можно продолжить позже.' if cancelled else redact(str(error)) if isinstance(error, ValueError) else 'Истекло время подготовки. Скачанные файлы сохранены; повторите попытку.' if code == 'timeout' else 'Не удалось завершить установку. Откройте «Логи» и соберите архив.'
            print(json.dumps(dict(type='error', cancelled=cancelled, code=code, message=message, detail=detail[-2000:]), ensure_ascii=False), flush=True)
            return 3 if cancelled else 1
        print('Scott Voice: '+(str(error) if isinstance(error, ValueError) else type(error).__name__), file=sys.stderr)
        return 1


if __name__ == '__main__':
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, 'reconfigure'):
            stream.reconfigure(encoding='utf-8', errors='replace')
    raise SystemExit(main())
