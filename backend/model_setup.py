"""First-run model preparation, with no microphone, inference or audio output."""
from __future__ import annotations

import ast
from contextlib import redirect_stdout
import importlib.util
import os
import socket
from pathlib import Path
import sys
import time
from urllib.parse import urlsplit
import zipfile
import zlib

try:
    from .model_download import checksum, download_file, DownloadError
except ImportError:
    from model_download import checksum, download_file, DownloadError


def load_environment():
    # The embeddable interpreter may not have python-dotenv until pip finishes.
    try:
        from dotenv import load_dotenv
        try:
            from .storage_paths import environment_path
        except ImportError:
            from storage_paths import environment_path
        load_dotenv(environment_path(), override=False)
    except ImportError:
        pass
    # The Hub reads these at import time, before faster-whisper is imported.
    os.environ.setdefault('HF_HUB_DOWNLOAD_TIMEOUT', '60')
    os.environ.setdefault('HF_HUB_ETAG_TIMEOUT', '30')


def whisper_spec(model_name=None) -> tuple[Path, str, str]:
    """Read the installed provider's manifest without importing torch or loading weights."""
    spec = importlib.util.find_spec('whisper')
    if spec is None or not spec.origin:
        raise ValueError('Whisper не установлен')
    manifest = {}
    for node in ast.parse(Path(spec.origin).read_text(encoding='utf-8')).body:
        if isinstance(node, ast.Assign) and any(isinstance(n, ast.Name) and n.id == '_MODELS' for n in node.targets):
            manifest = ast.literal_eval(node.value)
            break
    model = model_name or os.getenv('WHISPER_MODEL', 'small').strip()
    if model == 'turbo':
        model = 'large-v3-turbo'
    if model not in manifest:
        raise ValueError('Неизвестная модель WHISPER_MODEL. Выберите модель Whisper из списка в настройках.')
    url = manifest[model]
    digest = urlsplit(url).path.split('/')[-2]
    filename = urlsplit(url).path.split('/')[-1]
    try:
        from .storage_paths import model_directory
    except ImportError:
        from storage_paths import model_directory
    local = model_directory('models/whisper', backend=Path(__file__).resolve().parent) / filename
    root = Path(os.getenv('XDG_CACHE_HOME') or Path.home() / '.cache') / 'whisper'
    # Follow the existing recognizer's choice; never move an existing user's cache.
    target = local if local.is_file() else root / filename
    return target, url, digest


def prepare_openai(model_name, report):
    """A needed fallback uses the same resumable, verified download as setup."""
    target, url, digest = whisper_spec(model_name)
    download_file(url, target, expected_sha256=digest, status=lambda message: report(message))
    return target


def silero_repo() -> Path:
    torch_home = Path(os.getenv('TORCH_HOME') or Path(os.getenv('XDG_CACHE_HOME') or Path.home() / '.cache') / 'torch')
    return torch_home / 'hub/snakers4_silero-models_master'


def valid_archive(path: Path) -> bool:
    try:
        with zipfile.ZipFile(path) as archive:
            return bool(archive.namelist()) and archive.testzip() is None
    except (OSError, ValueError, zipfile.BadZipFile, RuntimeError, EOFError, zlib.error):
        return False


def valid_silero(path: Path) -> bool:
    if not valid_archive(path):
        return False
    try:
        with zipfile.ZipFile(path) as archive:
            return any(name.endswith('/tts_models/model') or name == 'tts_models/model'
                       for name in archive.namelist())
    except (OSError, ValueError, zipfile.BadZipFile):
        return False


def models_ready() -> bool:
    try:
        try:
            from .recognition_models import selected_engine, prepared_faster_path
        except ImportError:
            from recognition_models import selected_engine, prepared_faster_path
        voice = silero_repo() / 'src/silero/model/v4_ru.pt'
        if selected_engine() == 'faster':
            speech_ready = prepared_faster_path(os.getenv('WHISPER_MODEL', 'small').strip()) is not None
        else:
            target, _, digest = whisper_spec()
            speech_ready = target.is_file() and checksum(target) == digest
        return speech_ready and valid_silero(voice)
    except (OSError, ValueError, SyntaxError, ImportError):
        return False


def prepare_models(report):
    load_environment()
    try:
        from .recognition_models import selected_engine, prepare_faster
    except ImportError:
        from recognition_models import selected_engine, prepare_faster
    last = [0.0]
    fraction = [.76]

    def bytes_progress(done, total, label, start, span):
        now = time.monotonic()
        if now - last[0] < .25 and done != total:
            return
        last[0] = now
        mib = done / 1024 ** 2
        text = f'{label}: {mib:.0f} МБ'
        if total:
            text += f' из {total / 1024 ** 2:.0f} МБ'
        fraction[0] = start + span * (min(1, done / total) if total else 0)
        report(text, fraction[0])

    if selected_engine() == 'faster':
        prepare_faster(os.getenv('WHISPER_MODEL', 'small').strip(), report)
    else:
        target, url, digest = whisper_spec()
        report(f'Готовлю Whisper {target.stem}…', .76)
        download_file(url, target, expected_sha256=digest,
                      progress=lambda done, total: bytes_progress(done, total, 'Whisper', .76, .14),
                      status=lambda message: report(message, fraction[0]))
    report('Готовлю локальный голос Silero…', .90)
    fraction[0] = .90
    import torch
    original = torch.hub.download_url_to_file
    original_timeout = socket.getdefaulttimeout()

    def reliable_download(url, destination, hash_prefix=None, progress=True):
        # Torch hub supplies archives for both its source repository and TTS weights.
        # Silero publishes no full SHA256 here, so check archive CRCs; then hub
        # imports the model package below. Never describe this as provider authentication.
        if hash_prefix:
            return original(url, destination, hash_prefix=hash_prefix, progress=progress)
        validator = valid_silero if str(destination).endswith('.pt') else valid_archive
        download_file(url, Path(destination), validate=validator,
                      progress=lambda done, total: bytes_progress(done, total, 'Silero', .90, .04),
                      status=lambda message: report(message, fraction[0]))

    # Old torch.hub versions trust the existence of a partial weight file.
    # Replace only this known corrupt cache after a validated new download.
    repo = silero_repo()
    voice = repo / 'src/silero/model/v4_ru.pt'
    if voice.exists() and not valid_silero(voice):
        from omegaconf import OmegaConf
        config = OmegaConf.load(repo / 'models.yml')
        reliable_download(config.tts_models.ru.v4_ru.latest.package, str(voice))
    torch.hub.download_url_to_file = reliable_download
    socket.setdefaulttimeout(30)
    try:
        # Hub also emits plain text; keep the stdout JSON protocol intact.
        with redirect_stdout(sys.stderr):
            model, _ = torch.hub.load(repo_or_dir='snakers4/silero-models', model='silero_tts',
                                      language='ru', speaker='v4_ru', trust_repo=True)
            model.to(torch.device('cpu'))
        del model
    except DownloadError:
        raise
    except Exception as error:
        try:
            from .support_logs import append_log
        except ImportError:
            from support_logs import append_log
        append_log('setup.log', 'Silero: '+type(error).__name__+': '+str(error))
        raise DownloadError('Не удалось подготовить голос Silero. Причина сохранена в setup.log; соберите логи и повторите подготовку. Whisper повторно скачиваться не будет.') from error
    finally:
        torch.hub.download_url_to_file = original
        socket.setdefaulttimeout(original_timeout)
    if not models_ready():
        raise DownloadError('Проверка моделей не завершена. Нажмите «Повторить», чтобы закончить подготовку.')
    report('Модели проверены и готовы', .95)
