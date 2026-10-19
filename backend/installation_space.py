"""Offline space estimates for components; no models, drivers or network imports."""
from pathlib import Path
import json
import shutil
import tempfile
import sys

GIB = 1024**3
PROFILES = {
    'cpu': (1.8, 2, .5),
    'gpu': (5, 7, 2),
    'voice': (7, 8, 2),
    'voice_shared': (3, 4, 1),
}


class InsufficientSpace(ValueError):
    code = 'disk_full'


def gib(value):
    return f'{value/GIB:g}'.replace('.', ',')


def existing_parent(path):
    path = Path(path).absolute()
    while not path.exists() and path != path.parent:
        path = path.parent
    return path


def free_bytes(path):
    try:
        return shutil.disk_usage(existing_parent(path)).free
    except OSError:
        return None


def budget(profile, path):
    low, high, temporary = PROFILES[profile]
    # Linux x86-64 also installs Triton through openai-whisper. The measured
    # dependency closure alone is 2.56 GiB, before Python, Qt and speech models.
    if profile == 'cpu' and sys.platform == 'linux':
        low, high, temporary = 3, 4, .5
    installed_low, installed_high = int(low*GIB), int(high*GIB)
    temporary_bytes = int(temporary*GIB)
    required = installed_high+temporary_bytes
    free = free_bytes(path)
    title = 'Scott Voice' if profile.startswith('voice') else 'Чат и голос'
    hint = f'{title}: примерно {gib(installed_low)}–{gib(installed_high)} ГиБ. Для подготовки оставьте {gib(required)} ГиБ свободно.'
    if profile == 'voice_shared':
        hint += ' Готовое ускорение основной установки используется повторно.'
    elif profile in ('cpu', 'gpu'):
        hint += ' Оценка для стандартной модели речи; другие модели требуют больше места.'
    return dict(profile=profile, installed_min_bytes=installed_low, installed_max_bytes=installed_high,
        temporary_bytes=temporary_bytes, required_free_bytes=required, free_bytes=free,
        enough_space=free >= required if free is not None else None, hint=hint)


def setup_budgets(root):
    cpu, gpu = budget('cpu', runtime_destination(root)), budget('gpu', runtime_destination(root))
    auto = dict(gpu)
    cpu_size = '4' if sys.platform == 'linux' else '2'
    auto['hint'] = (f'Чат и голос: около {cpu_size} ГиБ на CPU или 5–7 ГиБ на GPU. '
        f'На время подготовки оставьте {gib(cpu["required_free_bytes"])} ГиБ для CPU или 9 ГиБ для GPU. '
        'Дополнительные модели и Scott Voice устанавливаются отдельно.')
    return dict(cpu=cpu, auto=auto)


def runtime_destination(root):
    """Measure the writable runtime disk rather than a read-only package mount."""
    root = Path(root)
    try:
        metadata=json.loads((root/'.scott-linux-install.json').read_text(encoding='utf-8'))
        if metadata.get('runtime_home'):
            path=Path(metadata['runtime_home'])
            if path.is_absolute():
                return path/'runtime'
        elif (root/'python-runtime/.scott-python.json').is_file():
            try:
                from .linux_runtime import read_receipt, slot_path
            except ImportError:
                from linux_runtime import read_receipt, slot_path
            return slot_path(read_receipt(root/'python-runtime'))/'runtime'
    except (OSError, ValueError, KeyError, TypeError):
        pass
    return root


def require_space(profile, destination, temporary=None):
    """Use only for fresh components; repairs can need far less than a full install."""
    plan = budget(profile, destination)
    target, temporary = existing_parent(destination), existing_parent(temporary or tempfile.gettempdir())
    try:
        same_volume = target.stat().st_dev == temporary.stat().st_dev
    except OSError:
        same_volume = True
    checks = [('на диске установки', target, plan['required_free_bytes'] if same_volume else plan['installed_max_bytes'])]
    if not same_volume:
        checks.append(('на диске временных файлов', temporary, plan['temporary_bytes']))
    for label, path, required in checks:
        available = free_bytes(path)
        if available is not None and available < required:
            raise InsufficientSpace(f'Недостаточно места {label}: свободно {gib(available)} ГиБ, '
                f'для новой подготовки нужно около {gib(required)} ГиБ. Освободите место и повторите подготовку.')
    return plan
