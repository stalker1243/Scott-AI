"""Driver inventory without requiring a PyTorch GPU build."""
import json
import subprocess
import sys
from functools import lru_cache
from pathlib import Path


def _linux_amd(root=Path('/sys/class/drm')):
    result, seen = [], set()
    for card in sorted(root.glob('card[0-9]*')):
        try:
            device = (card / 'device').resolve()
            if device in seen or (device / 'vendor').read_text().strip().lower() != '0x1002':
                continue
            seen.add(device)
            driver = (device / 'driver').resolve().name if (device / 'driver').exists() else ''
            result.append({'name': f'AMD GPU ({card.name})', 'driver': driver})
        except OSError:
            continue
    return result


@lru_cache(maxsize=1)
def _probe_amd():
    if sys.platform.startswith('linux'):
        return tuple(_linux_amd())
    if sys.platform != 'win32':
        return ()
    # Only video-controller metadata is queried. Keep the helper invisible.
    command = ("[Console]::OutputEncoding = [Text.UTF8Encoding]::new(); "
               "Get-CimInstance Win32_VideoController | "
               "Where-Object { $_.PNPDeviceID -match 'VEN_1002' } | "
               "Select-Object Name,DriverVersion | ConvertTo-Json -Compress")
    try:
        response = subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-Command', command],
            capture_output=True, encoding='utf-8', errors='replace', timeout=8,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        if response.returncode or not response.stdout.strip():
            return ()
        values = json.loads(response.stdout.lstrip('\ufeff'))
        values = values if isinstance(values, list) else [values]
        return tuple({'name': entry['Name'], 'driver': entry.get('DriverVersion', '')}
                     for entry in values if isinstance(entry, dict) and entry.get('Name'))
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return ()


def amd_adapters():
    return [dict(entry) for entry in _probe_amd()]
