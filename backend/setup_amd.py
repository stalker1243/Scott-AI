"""Print an AMD installation plan, or install it in the active virtualenv."""
import argparse
import json
import subprocess
import sys
from pathlib import Path

from bootstrap import rocm_requirement


def main():
    parser = argparse.ArgumentParser(description='Подготовка AMD ROCm для Scott. По умолчанию только план.')
    parser.add_argument('--gfx', default='all', help='Архитектура AMD из матрицы совместимости, например gfx1100')
    parser.add_argument('--install', action='store_true', help='Установить библиотеки в активное виртуальное окружение')
    args = parser.parse_args()
    try:
        torch_args = rocm_requirement(args.gfx)
    except ValueError as error:
        parser.error(str(error))
    commands = [[sys.executable, '-m', 'pip', 'install', *torch_args],
                [sys.executable, '-m', 'pip', 'install', '-r', str(Path(__file__).with_name('requirements.txt'))]]
    if not args.install:
        print(json.dumps({'commands': commands, 'guide': 'docs/amd-support.md'}, ensure_ascii=False, indent=2))
        return 0
    if sys.prefix == sys.base_prefix:
        parser.error('Сначала создайте и активируйте отдельное виртуальное окружение для AMD')
    if sys.platform not in ('win32', 'linux') or not (3, 11) <= sys.version_info[:2] <= (3, 14):
        parser.error('Этот профиль ROCm рассчитан на Windows/Linux и Python 3.11–3.14')
    for command in commands:
        subprocess.run(command, check=True)
    import torch
    if not torch.version.hip or not torch.cuda.is_available():
        print('PyTorch установлен, но AMD GPU недоступен. Проверьте драйвер и карту по docs/amd-support.md.', file=sys.stderr)
        return 1
    # Verify an actual kernel, not just the presence of a package or driver.
    value = (torch.ones(2, device='cuda') + 1).sum().item()
    if value != 4:
        raise RuntimeError('AMD GPU не прошёл проверку вычислений')
    print(f'AMD ROCm/HIP готов: {torch.cuda.get_device_name(0)}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
