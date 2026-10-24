"""Prepare the same Whisper format that the recognizer selects; no audio input."""
from __future__ import annotations

import ast
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import time

try:
    from .model_download import DownloadError
    from .voice_install_errors import failure_code
except ImportError:
    from model_download import DownloadError
    from voice_install_errors import failure_code

FILES = {'config.json', 'preprocessor_config.json', 'model.bin', 'tokenizer.json',
         'vocabulary.json', 'vocabulary.txt'}
REQUIRED = {'config.json', 'model.bin', 'tokenizer.json'}


def selected_engine():
    try:
        from .runtime_profile import compact_mode, ProfileError, REPAIR_MESSAGE
    except ImportError:
        from runtime_profile import compact_mode, ProfileError, REPAIR_MESSAGE
    if compact_mode():
        try:
            from faster_whisper import WhisperModel
        except (ImportError, OSError) as error:
            raise ProfileError(REPAIR_MESSAGE) from error
        return 'faster'
    choice = os.getenv('WHISPER_ENGINE', 'auto').strip().lower()
    if choice not in ('auto', 'faster'):
        return 'openai'
    try:
        from faster_whisper import WhisperModel  # Check native library import, not just its metadata.
        try:
            from . import device_settings
        except ImportError:
            import device_settings
        if device_settings.resolve_device('whisper') == 'cuda' and device_settings.rocm_build():
            return 'openai'
        return 'faster'
    except (ImportError, OSError):
        return 'openai'


def repository(model):
    """Read the installed provider's aliases, including turbo, without loading weights."""
    spec = importlib.util.find_spec('faster_whisper')
    if spec is None or not spec.origin:
        raise ValueError('faster-whisper не установлен')
    source = Path(spec.origin).with_name('utils.py')
    aliases = {}
    for node in ast.parse(source.read_text(encoding='utf-8')).body:
        if isinstance(node, ast.Assign) and any(isinstance(n, ast.Name) and n.id == '_MODELS' for n in node.targets):
            aliases = ast.literal_eval(node.value)
            break
    repo = aliases.get(model)
    if not isinstance(repo, str) or not re.fullmatch(r'[\w.-]+/[\w.-]+', repo):
        raise ValueError('Неизвестная модель WHISPER_MODEL для faster-whisper.')
    return repo


def receipt_path(repo):
    cache = Path(os.getenv('XDG_CACHE_HOME') or Path.home()/'.cache')
    return cache/'scottai/recognition'/('faster-'+repo.replace('/', '--')+'.json')


def valid_plan(plan, repo):
    if not isinstance(plan, dict) or plan.get('repo') != repo or not re.fullmatch(r'[0-9a-f]{40}', str(plan.get('revision', ''))):
        return False
    files = plan.get('files')
    return (isinstance(files, dict) and REQUIRED.issubset(files) and set(files).issubset(FILES)
            and bool({'vocabulary.json', 'vocabulary.txt'} & set(files))
            and all(isinstance(info, dict) and type(info.get('size')) is int and info['size'] > 0
                    and info.get('kind') in ('sha256', 'git') and re.fullmatch(
                        r'[0-9a-f]{64}' if info['kind'] == 'sha256' else r'[0-9a-f]{40}', str(info.get('hash', '')))
                    for info in files.values()))


def read_plan(repo):
    try:
        plan = json.loads(receipt_path(repo).read_text(encoding='utf-8'))
        return plan if valid_plan(plan, repo) else None
    except (OSError, ValueError):
        return None


def verified(path, info):
    path = Path(path)
    if not path.is_file() or path.stat().st_size != info['size']:
        return False
    digest = hashlib.sha256() if info['kind'] == 'sha256' else hashlib.sha1(b'blob '+str(info['size']).encode()+b'\0')
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(8*1024*1024), b''):
            digest.update(block)
    return digest.hexdigest() == info['hash']


def cached_file(repo, name, revision):
    from huggingface_hub import try_to_load_from_cache
    path = try_to_load_from_cache(repo, name, revision=revision)
    return Path(path) if isinstance(path, str) else None


def prepared_faster_path(model):
    """Only return a fully verified local snapshot. This check never downloads."""
    try:
        repo = repository(model)
        plan = read_plan(repo)
        if not plan:
            return None
        paths = [cached_file(repo, name, plan['revision']) for name in plan['files']]
        if any(path is None for path in paths):
            return None
        if len({path.parent for path in paths}) != 1:
            return None
        if all(verified(path, info) for path, info in zip(paths, plan['files'].values())):
            return paths[0].parent
    except (OSError, ValueError, ImportError, TypeError):
        pass
    return None


def transfer_progress(label, file_size, completed, total, report):
    """A silent SDK progress bar that reports real bytes to the setup window."""
    from tqdm.auto import tqdm
    class Transfer(tqdm):
        def __init__(self, *args, **kwargs):
            self.done = kwargs.get('initial', 0)
            self.size = kwargs.get('total') or file_size
            self.last_report = 0.
            kwargs['disable'] = True
            super().__init__(*args, **kwargs)

        def update(self, n=1):
            self.done += n
            now = time.monotonic()
            if now-self.last_report >= .5 or self.done >= self.size:
                self.last_report = now
                done = min(self.done, self.size)
                report(f'{label}: {done/1024**2:.1f} / {self.size/1024**2:.1f} МиБ',
                       .76 + .14 * min(1., (completed + done)/total))
            return super().update(n)
    return Transfer


def prepare_faster(model, report):
    from huggingface_hub import HfApi, hf_hub_download
    repo = repository(model)
    ready = prepared_faster_path(model)
    if ready:
        report(f'faster-whisper {model}: файлы проверены, повторная загрузка не нужна', .9)
        return ready
    plan = read_plan(repo)
    def retry(operation):
        for attempt in range(3):
            try:
                return operation()
            except Exception as error:
                code = failure_code(error)
                if attempt == 2 or code not in ('network_unavailable', 'download_timeout', 'download_server'):
                    if code:
                        raise DownloadError(f'Не удалось загрузить faster-whisper ({code}). Скачанные части сохранены. Соберите логи и повторите подготовку.') from error
                    raise
                report(f'Сервис faster-whisper временно не отвечает. Повтор {attempt + 2}/3', .76)
                time.sleep(2 ** attempt)
    if not plan:
        report(f'Получаем список файлов faster-whisper {model}', .76)
        info = retry(lambda: HfApi(token=False).model_info(repo, files_metadata=True, timeout=30))
        files = {}
        for item in info.siblings:
            if item.rfilename in FILES:
                files[item.rfilename] = dict(size=item.size, kind='sha256' if item.lfs else 'git',
                    hash=item.lfs.sha256 if item.lfs else item.blob_id)
        plan = dict(repo=repo, revision=info.sha, files=files)
        if not valid_plan(plan, repo):
            raise ValueError('Неполный официальный пакет faster-whisper.')
        receipt = receipt_path(repo)
        receipt.parent.mkdir(parents=True, exist_ok=True)
        temporary = receipt.with_suffix('.tmp')
        temporary.write_text(json.dumps(plan, indent=2), encoding='utf-8')
        os.replace(temporary, receipt)
    total = sum(info['size'] for info in plan['files'].values())
    completed = 0
    for index, (name, info) in enumerate(plan['files'].items()):
        fraction = .76 + .14 * completed / total
        report(f'faster-whisper {model}: файл {index + 1}/{len(plan["files"])} · {name}', fraction)
        path = cached_file(repo, name, plan['revision'])
        if path and verified(path, info):
            completed += info['size']
            continue
        force = path is not None
        transfer = transfer_progress('faster-whisper '+name, info['size'], completed, total, report)
        path = Path(retry(lambda: hf_hub_download(repo, name, revision=plan['revision'], token=False,
                                                 force_download=force, etag_timeout=30, tqdm_class=transfer)))
        if not verified(path, info):
            raise DownloadError('Контрольная сумма faster-whisper не совпадает: '+name)
        completed += info['size']
    ready = prepared_faster_path(model)
    if ready is None:
        raise DownloadError('Проверка faster-whisper не завершена. Продолжите подготовку.')
    return ready
