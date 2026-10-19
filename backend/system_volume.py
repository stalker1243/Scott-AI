"""Fixed output-device controls with native Core Audio on Windows."""
import json
import os
from pathlib import Path
import re
import subprocess

def native_path():
    backend = Path(__file__).resolve().parent
    for path in (backend / 'native/ScottSystem.exe', backend.parent / 'ScottAI_qt/build/ScottSystem.exe'):
        if path.is_file():
            return str(path)
    return None

def _run(command):
    result = subprocess.run(command, capture_output=True, text=True, encoding='utf-8', errors='replace',
        timeout=4, env=dict(os.environ, LC_ALL='C'), creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    if result.returncode:
        raise ValueError('Устройство звука недоступно или команда не выполнена.')
    return result.stdout.strip()

def available():
    import os_actions
    if os_actions.is_windows(): return bool(native_path())
    if os_actions.current_os() == os_actions.MACOS: return bool(os_actions.find_tool('osascript'))
    return bool(os_actions.find_tool('wpctl', 'pactl', 'amixer'))

def _native(operation, value):
    path = native_path()
    if not path:
        raise ValueError('Для точного управления звуком обновите Qt-пакет с помощником ScottSystem.')
    command = [path, {'status': 'status', 'set': 'volume', 'delta': 'delta', 'mute': 'mute'}[operation]]
    if operation != 'status': command.append(str(value))
    try:
        data = json.loads(_run(command))
    except json.JSONDecodeError:
        raise ValueError('Нативный помощник вернул некорректный ответ.') from None
    if not isinstance(data, dict) or type(data.get('protocol')) is not int or data.get('protocol') != 1 or data.get('success') is not True or type(data.get('muted')) is not bool:
        raise ValueError('Не удалось подтвердить состояние звука.')
    volume = data.get('volume')
    if type(volume) is not int or not 0 <= volume <= 100:
        raise ValueError('Нативный помощник вернул некорректную громкость.')
    return volume, data['muted']

def _status(tool):
    if tool == 'wpctl':
        text = _run(['wpctl', 'get-volume', '@DEFAULT_AUDIO_SINK@'])
        match = re.search(r'Volume:\s*([0-9]+(?:\.[0-9]+)?)', text)
        if match: return round(float(match[1])*100), '[MUTED]' in text
    elif tool == 'pactl':
        match = re.search(r'(\d+)%', _run(['pactl', 'get-sink-volume', '@DEFAULT_SINK@']))
        muted = _run(['pactl', 'get-sink-mute', '@DEFAULT_SINK@'])
        if match and re.search(r'\b(?:yes|no)\b', muted, re.I):
            return int(match[1]), bool(re.search(r'\byes\b', muted, re.I))
    elif tool == 'amixer':
        text = _run(['amixer', 'get', 'Master'])
        match = re.search(r'\[(\d+)%\]', text)
        if match: return int(match[1]), '[off]' in text
    elif tool == 'osascript':
        text = _run(['osascript', '-e', 'set s to get volume settings', '-e',
                     'return (output volume of s as text) & "," & (output muted of s as text)'])
        match = re.fullmatch(r'(\d+),\s*(true|false)', text)
        if match: return int(match[1]), match[2] == 'true'
    raise ValueError('Не удалось прочитать громкость устройства.')

def execute(operation, value=None):
    try:
        import os_actions
        if operation not in ('status', 'set', 'delta', 'mute'):
            raise ValueError('Неизвестное действие со звуком.')
        if operation != 'status' and (type(value) is not int
                or (operation == 'set' and not 0 <= value <= 100)
                or (operation == 'delta' and not -100 <= value <= 100)
                or (operation == 'mute' and value not in (0, 1))):
            raise ValueError('Громкость задаётся от 0 до 100 процентов.')
        if os_actions.is_windows():
            volume, muted = _native(operation, value)
        else:
            tool = 'osascript' if os_actions.current_os() == os_actions.MACOS else os_actions.find_tool('wpctl', 'pactl', 'amixer')
            if not tool: raise ValueError('Установите wpctl, pactl или amixer для управления звуком.')
            if operation != 'status':
                if operation == 'delta':
                    current, _ = _status(tool)
                    value = min(100, max(0, current + value))
                if tool == 'wpctl':
                    command = ['wpctl', 'set-mute' if operation == 'mute' else 'set-volume', '@DEFAULT_AUDIO_SINK@', str(value) if operation == 'mute' else f'{value}%', *([] if operation == 'mute' else ['--limit', '1.0'])]
                elif tool == 'pactl':
                    command = ['pactl', 'set-sink-mute' if operation == 'mute' else 'set-sink-volume', '@DEFAULT_SINK@', str(value) if operation == 'mute' else f'{value}%']
                elif tool == 'amixer':
                    command = ['amixer', '-q', 'set', 'Master', ('mute' if value else 'unmute') if operation == 'mute' else f'{value}%']
                else:
                    command = ['osascript', '-e', f'set volume output muted {"true" if value else "false"}' if operation == 'mute' else f'set volume output volume {value}']
                _run(command)
            volume, muted = _status(tool)
        return {'success': True, 'response': f'Системная громкость: {volume}%. Звук {"выключен" if muted else "включён"}.',
                'data': {'volume': volume, 'muted': muted}}
    except ValueError as error:
        return {'success': False, 'response': str(error)}
    except (OSError, subprocess.SubprocessError, OverflowError):
        return {'success': False, 'response': 'Не удалось управлять звуком. Проверьте устройство вывода и доступность системного инструмента.'}
