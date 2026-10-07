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

ROOT = Path(__file__).resolve().parent.parent
MODEL = 'Qwen/Qwen3-TTS-12Hz-0.6B-Base'
REVISION = '5d83992436eae1d760afd27aff78a71d676296fc'
REFERENCE_SHA = '78f48237579b5323bd5e738095fa17f4c30f1f76d8976e66ef128b850eea42f3'
TORCH_INDEX = 'https://download.pytorch.org/whl/cu126'
REQUIREMENTS = ('qwen-tts==0.1.1', 'transformers==4.57.3', 'accelerate==1.12.0',
                'soundfile==0.13.1', 'scipy==1.17.1', 'numpy==2.3.4',
                'huggingface-hub==0.36.2', 'psutil==7.2.2')
ASSETS = tuple('experiments/voice_design/'+name for name in (
    'voice_worker.py', 'trial_utils.py', 'generate_samples.py', 'evaluate_samples.py',
    'create_scott_voice.py', 'robotic_profiles.json', 'stream_voice.py')) + (
    'reports/voice-design/reference/reference.json',
    'reports/voice-design/reference/scott-reference.wav')
CLIENT_FILES = ('backend/scott_voice_process.py', 'backend/voice_cache.py',
                'backend/speech_text.py')
MODEL_FILES = ('config.json', 'generation_config.json', 'merges.txt', 'model.safetensors',
    'preprocessor_config.json', 'tokenizer_config.json', 'vocab.json',
    'speech_tokenizer/config.json', 'speech_tokenizer/configuration.json',
    'speech_tokenizer/model.safetensors', 'speech_tokenizer/preprocessor_config.json')


def home_path(root=ROOT):
    value = os.getenv('SCOTT_VOICE_HOME', '').strip()
    return Path(value).expanduser().resolve() if value else Path(root)/'voice-runtime'


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


def plan(home, python, auto_python=False):
    if auto_python:
        python = Path(home)/'python/tools/python.exe'
    environment = python_path(home)
    pip = [str(environment), '-m', 'pip', 'install', '--disable-pip-version-check', '--no-cache-dir', '--no-input']
    return dict(home=str(Path(home).resolve()), model=MODEL, revision=REVISION,
        reference_sha256=REFERENCE_SHA, device='cuda', platform='Windows x64 / Python 3.13',
        auto_python=auto_python,
        commands=[[str(python), '-m', 'venv', str(environment.parent.parent)],
                  pip+['--index-url', TORCH_INDEX, 'torch==2.9.1+cu126', 'torchaudio==2.9.1+cu126'],
                  pip+list(REQUIREMENTS), [str(environment), '-m', 'pip', 'check']],
        notes=['Установка отдельная; глобальные пакеты и настройки голоса не меняются.',
               'Загрузка весов и библиотек занимает несколько гигабайт.',
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
               HF_HUB_DISABLE_XET='1', PIP_CONFIG_FILE=os.devnull)
    return env


def download_model(home, model_source=None):
    """Pin the accepted revision; verify official LFS hashes before publishing."""
    # Called with the optional interpreter after installing its dependencies.
    from huggingface_hub import HfApi, hf_hub_download
    destination = Path(home)/'experiments/voice_design/models/base'
    info = HfApi(token=False).model_info(MODEL, revision=REVISION, files_metadata=True)
    if info.sha != REVISION:
        raise ValueError('Неверная версия модели.')
    items = {item.rfilename: item for item in info.siblings}
    if not set(MODEL_FILES).issubset(items):
        raise ValueError('Неполный официальный пакет модели.')
    hashes = {}
    for name in (*MODEL_FILES, 'README.md'):
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
        path = Path(hf_hub_download(MODEL, name, revision=REVISION, token=False,
                    local_dir=destination, cache_dir=Path(home)/'download-cache', force_download=force))
        if path.resolve() != (destination/name).resolve() or not path.is_file():
            raise ValueError('Загрузчик вернул неверный путь.')
        actual = checksum(path)
        if not verified(path):
            raise ValueError('Контрольная сумма модели не совпадает: '+name)
        hashes[name] = actual
        print('Проверен файл модели: '+name, flush=True)
    write_json(destination/'scott-model.json', dict(model=MODEL, revision=REVISION,
                files=list(hashes), sha256=hashes))


def check(home, deep=False):
    try:
        from .scott_voice_engine import config_at, inspect_installation
    except ImportError:
        from scott_voice_engine import config_at, inspect_installation
    config = config_at(home)
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
    emit = progress or (lambda *args: None)
    if os.name != 'nt' or struct.calcsize('P') != 8:
        raise ValueError('Этот установщик рассчитан на Windows x64; другие платформы ещё не проверены.')
    sources = asset_sources(root)  # Validate before creating or changing anything.
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
        python = prepare_python(home, cancelled=runner.cancelled if runner else None)
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
    commands = plan(home, python)['commands']
    emit('environment', 'Подготавливаем окружение', .15)
    if not python_path(home).is_file():
        run(commands[0], check=True, env=env)
    for index, command in enumerate(commands[1:]):
        emit('libraries', 'Устанавливаем библиотеки голоса', .2+index*.12)
        run(command, check=True, env=env)
    emit('model', 'Подготавливаем файлы голоса', .6)
    download = [str(python_path(home)), str(Path(__file__).resolve()), '--download-model', '--home', str(home)]
    if model_source:
        download += ['--model-source', str(model_source)]
    run(download, check=True, env=env)
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
            threading.Thread(target=cancel_input, daemon=True).start()
        if args.bundle:
            result = bundle_assets(args.bundle)
        elif args.install:
            result = install(args.home, args.python, auto_python=args.auto_python, progress=progress,
                             runner=runner, model_source=args.model_source)
        elif args.check:
            result = check(args.home, args.deep)
        elif args.download_model:
            download_model(args.home, args.model_source)
            return 0
        else:
            result = plan(args.home, args.python, args.auto_python)
        if args.json:
            print(json.dumps(dict(type='result', **result), ensure_ascii=False), flush=True)
        else:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        return 1 if result.get('available') is False else 0
    except Exception as error:
        if args.json:
            cancelled = type(error).__name__ == 'InstallationCancelled'
            message = 'Установка отменена. Её можно продолжить позже.' if cancelled else str(error) if isinstance(error, ValueError) else 'Не удалось завершить установку. Проверьте подключение и повторите попытку.'
            print(json.dumps(dict(type='error', cancelled=cancelled, message=message), ensure_ascii=False), flush=True)
            return 3 if cancelled else 1
        print('Scott Voice: '+(str(error) if isinstance(error, ValueError) else type(error).__name__), file=sys.stderr)
        return 1


if __name__ == '__main__':
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, 'reconfigure'):
            stream.reconfigure(encoding='utf-8', errors='replace')
    raise SystemExit(main())
