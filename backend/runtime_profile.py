"""Explicit experimental CPU profile; the full installation remains the default."""
import os
import json
from pathlib import Path
import re

COMPACT_CT2 = 'ctranslate2==4.8.2'
REPAIR_MESSAGE = ('Локальное распознавание недоступно в компактном режиме. '
                  'Повторите подготовку приложения. Для резервного движка выберите '
                  'обычный CPU-режим и повторите подготовку; чат доступен.')


class ProfileError(ValueError):
    pass


class RecognitionUnavailable(RuntimeError):
    pass


SETUP_MODES = {
    'auto': {'SCOTT_RUNTIME_PROFILE': 'full', 'SCOTT_TORCH_BACKEND': 'auto'},
    'cpu': {'SCOTT_RUNTIME_PROFILE': 'full', 'SCOTT_TORCH_BACKEND': 'cpu', 'WHISPER_DEVICE': 'cpu'},
    'compact': {'SCOTT_RUNTIME_PROFILE': 'compact', 'SCOTT_TORCH_BACKEND': 'cpu',
                'WHISPER_ENGINE': 'faster', 'WHISPER_DEVICE': 'cpu'},
}


def selection_path():
    try:
        from .storage_paths import backend_path
    except ImportError:
        from storage_paths import backend_path
    return backend_path('runtime_profile.json')


def saved_selection():
    """Read only a small versioned mode, never an arbitrary environment map."""
    try:
        with selection_path().open('rb') as stream:
            raw = stream.read(4097)
    except FileNotFoundError:
        return None
    except OSError as error:
        raise ProfileError('Не удалось прочитать режим подготовки. Проверьте права и выберите режим заново.') from error
    try:
        value = json.loads(raw) if len(raw) <= 4096 else None
        if (not isinstance(value, dict) or set(value) != {'version', 'mode'}
                or type(value['version']) is not int or value['version'] != 1
                or value['mode'] not in SETUP_MODES):
            raise ValueError('Invalid selection')
        return value['mode']
    except (ValueError, TypeError, KeyError) as error:
        raise ProfileError('Сохранённый режим подготовки повреждён. Выберите режим в мастере и повторите подготовку.') from error


def apply_selection(mode=None):
    """Overlay an explicit wizard choice after .env; never rewrite the latter.

    Each invocation starts with the caller's original environment. Moving back
    to auto therefore restores its engine/device; the saved compact overlay is
    not copied to .env. No selection preserves all legacy environment settings.
    """
    mode = saved_selection() if mode is None else mode
    if mode is not None:
        if mode not in SETUP_MODES:
            raise ProfileError('Неизвестный режим подготовки. Выберите auto, cpu или compact.')
        os.environ.update(SETUP_MODES[mode])
    return mode


def save_selection(mode):
    if mode not in SETUP_MODES:
        raise ProfileError('Неизвестный режим подготовки. Выберите auto, cpu или compact.')
    try:
        try:
            from .storage import atomic_write_text
        except ImportError:
            from storage import atomic_write_text
        atomic_write_text(selection_path(), json.dumps({'version': 1, 'mode': mode})+'\n')
    except OSError as error:
        raise ProfileError('Не удалось сохранить режим подготовки. Проверьте права и свободное место, затем повторите.') from error


def compact_mode():
    choice = os.getenv('SCOTT_RUNTIME_PROFILE', 'full').strip().lower()
    if choice not in ('full', 'compact'):
        raise ProfileError('Неизвестный SCOTT_RUNTIME_PROFILE. Выберите full или compact.')
    if choice == 'compact':
        if (os.getenv('WHISPER_ENGINE', 'auto').strip().lower() != 'faster'
                or os.getenv('WHISPER_DEVICE', '').strip().lower() != 'cpu'):
            raise ProfileError('Компактный режим требует WHISPER_ENGINE=faster и '
                               'WHISPER_DEVICE=cpu. Для других настроек выберите SCOTT_RUNTIME_PROFILE=full.')
        return True
    return False


def compact_requirements(source=None):
    """Keep the exact full-profile roots/markers except the two Torch roots."""
    path = Path(source) if source is not None else Path(__file__).with_name('requirements.txt')
    result, excluded, names = [], set(), set()
    for line in path.read_text(encoding='utf-8-sig').splitlines():
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        match = re.match(r'^([A-Za-z0-9][A-Za-z0-9_.-]*)(?:[<>=!~;\s]|$)', line)
        if match is None:
            raise ProfileError('Неподдерживаемая строка зависимостей компактного режима.')
        name = re.sub(r'[-_.]+', '-', match[1]).lower()
        if name in ('torch', 'openai-whisper'):
            excluded.add(name)
        else:
            result.append(line)
            names.add(name)
    if excluded != {'torch', 'openai-whisper'} or 'faster-whisper' not in names:
        raise ProfileError('Перечень зависимостей изменился. Компактный режим требует повторной проверки.')
    if 'ctranslate2' in names:
        raise ProfileError('Версия CTranslate2 в основном профиле изменилась. Повторите проверку компактного режима.')
    return result + [COMPACT_CT2]
