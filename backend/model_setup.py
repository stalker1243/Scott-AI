"""First-run model preparation, with no microphone, inference or audio output."""
from __future__ import annotations

import ast
try:
    from .performance_trace import measured
except ImportError:
    from performance_trace import measured
import importlib.util
import os
from pathlib import Path
import time
from urllib.parse import urlsplit

try:
    from .model_download import checksum, download_file, DownloadError
except ImportError:
    from model_download import checksum, download_file, DownloadError


def load_environment(runtime_mode=None):
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
    try:
        from .runtime_profile import apply_selection
    except ImportError:
        from runtime_profile import apply_selection
    apply_selection(runtime_mode)
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


@measured('setup.models_check', success=bool)
def models_ready() -> bool:
    try:
        try:
            from .recognition_models import selected_engine, prepared_faster_path
        except ImportError:
            from recognition_models import selected_engine, prepared_faster_path
        if selected_engine() == 'faster':
            speech_ready = prepared_faster_path(os.getenv('WHISPER_MODEL', 'small').strip()) is not None
        else:
            target, _, digest = whisper_spec()
            speech_ready = target.is_file() and checksum(target) == digest
        return speech_ready
    except (OSError, ValueError, SyntaxError, ImportError):
        return False


@measured('setup.models_worker')
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
    if not models_ready():
        raise DownloadError('Проверка моделей не завершена. Нажмите «Повторить», чтобы закончить подготовку.')
    report('Распознавание готово. Scott Voice настраивается отдельно в разделе голоса.', .95)
