"""Install only the optional browser libraries; reuse a system browser when available."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
try:
    from .browser_control_config import VERSION, browser_options, clean_environment, watch_owner
    from .storage import atomic_write_text
    from .support_logs import append_log
    from .voice_install_errors import failure_code
except ImportError:
    from browser_control_config import VERSION, browser_options, clean_environment, watch_owner
    from storage import atomic_write_text
    from support_logs import append_log
    from voice_install_errors import failure_code


# Run in the optional interpreter path. Neither a global Playwright nor a
# ready marker from an interrupted installation proves these libraries work.
LIBRARY_PROBE = '''
import importlib,json,sys
from pathlib import Path
home=Path(sys.argv[1]).resolve()
sys.path.insert(0,str(home))
for name in ('playwright','pyee','greenlet'):
    module=importlib.import_module(name)
    if not Path(module.__file__).resolve().is_relative_to(home):
        raise RuntimeError('Optional library came from another environment: '+name)
from playwright._repo_version import version
driver=json.loads((home/'playwright/driver/package/package.json').read_text(encoding='utf-8'))
if version!=sys.argv[2] or driver.get('version')!=sys.argv[2]:
    raise RuntimeError('Playwright Python/driver version mismatch')
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    executable=p.chromium.executable_path
print(json.dumps(dict(version=version,browser_executable=executable)))
'''


class SetupFailure(RuntimeError):
    def __init__(self, message, code):
        super().__init__(message)
        self.code = code


LOG_LIMIT = 2 * 1024 * 1024


def trim_log(path):
    temporary = None
    try:
        if path.stat().st_size > LOG_LIMIT:
            with path.open('rb') as stream:
                stream.seek(-LOG_LIMIT, 2)
                tail = stream.read()
            # Preserve raw CRLF and partial UTF-8 exactly. Text-mode rewriting
            # expands CRLF a second time on Windows and exceeds the byte limit.
            with tempfile.NamedTemporaryFile(mode='wb', dir=path.parent,
                    prefix='.'+path.name+'.', suffix='.tmp', delete=False) as output:
                temporary = Path(output.name)
                output.write(tail)
                output.flush()
                os.fsync(output.fileno())
            temporary.replace(path)
    except OSError:
        pass  # Keep the original installation error if log cleanup is unavailable.
    finally:
        if temporary is not None:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass


def setup_failure(error, stage):
    # A process deadline alone is not evidence of a network problem.
    code = 'timeout' if isinstance(error, subprocess.TimeoutExpired) else failure_code(error)
    messages = {
        'timeout': 'Превышено время этапа подготовки браузера. Готовые библиотеки сохраняются; повторите подготовку и соберите логи.',
        'disk_full': 'Недостаточно места для компонента браузера. Освободите место на диске установки и во временной папке.',
        'permission_denied': 'Нет доступа к файлам компонента браузера. Проверьте права на папку и журнал защитного ПО.',
        'network_unavailable': 'Сервис загрузки браузера не отвечает. Возможен сбой сервиса, DNS или прокси; повторите подготовку позже.',
        'download_timeout': 'Сервис загрузки браузера слишком долго не передаёт данные. Повторите подготовку позже.',
        'download_certificate': 'Не удалось проверить сертификат сервиса загрузки браузера. Проверьте дату компьютера и сертификаты прокси; соберите логи.',
        'download_access': 'Сервис отклонил загрузку компонента браузера. Проверьте доступ к сервису и настройки прокси.',
        'download_server': 'Сервис загрузки браузера временно недоступен. Повторите подготовку позже.',
    }
    label = {'probe': 'проверка библиотек', 'libraries': 'установка библиотек',
             'browser': 'подготовка Chromium'}.get(stage, 'подготовка файлов')
    return SetupFailure(messages.get(code, f'Не завершена {label}. Причина сохранена в логах; повторите подготовку.'),
                        code or 'process_failed')


def emit(**event):
    print(json.dumps(event, ensure_ascii=False), flush=True)


def prepare(home):
    home = Path(home).resolve()
    home.mkdir(parents=True, exist_ok=True)
    libraries = home / 'libraries'
    env = clean_environment(home)
    def run(command, timeout, stage, capture=False):
        # The supervisor owns the tree and cancellation. Keep pip output away
        # from the event protocol and user chat; its return code determines readiness.
        log = home / 'setup.log'
        try:
            with log.open('a', encoding='utf-8') as stream:
                operation_start = stream.tell()
                stream.write('\n['+stage+']\n')
                stream.flush()
                result = subprocess.run(command, stdout=subprocess.PIPE if capture else stream,
                    stderr=stream if capture else subprocess.STDOUT, env=env, text=True,
                    encoding='utf-8', errors='replace', timeout=timeout,
                    creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        except (OSError, subprocess.TimeoutExpired) as error:
            trim_log(log)
            append_log('browser-setup.log', f'{stage}: {type(error).__name__}: {error}')
            raise setup_failure(error, stage) from None
        if result.returncode:
            with log.open('rb') as stream:
                stream.seek(max(operation_start, log.stat().st_size-8192))
                tail = stream.read().decode('utf-8', errors='replace')
            trim_log(log)
            append_log('browser-setup.log', f'{stage}: exit {result.returncode}\n'+tail)
            error = subprocess.CalledProcessError(result.returncode, command, stderr=tail)
            raise setup_failure(error, stage)
        trim_log(log)
        append_log('browser-setup.log', f'{stage}: complete')
        return result.stdout if capture else None

    def probe():
        output = run([sys.executable, '-c', LIBRARY_PROBE, str(libraries), VERSION], 30, 'probe', capture=True)
        try:
            result = json.loads(output)
            if result.get('version') != VERSION or not isinstance(result.get('browser_executable'), str) or not result['browser_executable']:
                raise ValueError('Invalid library probe response')
            return result
        except (ValueError, TypeError, AttributeError):
            raise SetupFailure('Не удалось подтвердить готовность библиотек браузера. Повторите подготовку.', 'invalid_probe') from None

    checked = False
    (home / 'ready.json').unlink(missing_ok=True)
    if libraries.is_dir():
        try:
            result = probe()
            checked = True
        except SetupFailure as error:
            if error.code in ('timeout', 'permission_denied', 'disk_full'):
                raise  # Reinstalling cannot repair a local deadline/access failure.
    if not checked:
        emit(type='progress', stage='libraries', message='Подготавливаем управление браузером', progress=.15)
        run([sys.executable, '-m', 'pip', 'install', '--target', str(libraries), '--upgrade',
             '--no-compile', '--no-cache-dir', '--only-binary=:all:', '--timeout', '30', '--retries', '3',
             f'playwright=={VERSION}'], 900, 'libraries')
        # Insert optional libraries even with embedded Python's _pth isolation.
        result = probe()
    else:
        emit(type='progress', stage='libraries', message='Библиотеки браузера уже готовы', progress=.5)
    options = browser_options(home)
    if not options:
        emit(type='progress', stage='browser', message='Загружаем Chromium для Scott', progress=.65)
        command = "import sys; sys.path.insert(0, sys.argv[1]); from playwright.__main__ import main; sys.argv=['playwright','install','chromium','--no-shell']; main()"
        # The pinned SDK reuses complete browser/ffmpeg caches, and resumes the
        # component that was interrupted. Never launch a browser just to install.
        run([sys.executable, '-c', command, str(libraries)], 900, 'browser')
        if not Path(result['browser_executable']).is_file():
            raise SetupFailure('Chromium не найден после подготовки. Соберите логи и повторите подготовку браузера.', 'browser_missing')
    atomic_write_text(home / 'ready.json', json.dumps({'version': VERSION}))
    emit(type='result', state='complete', message='Браузер готов к управлению', progress=1.,
         reused_libraries=checked, browser='system' if options else 'bundled')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--home', type=Path, required=True)
    parser.add_argument('--owner', type=int, default=0)
    parser.add_argument('--owner-created', type=float, default=0.)
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding='utf-8')
    watch_owner(args.owner, args.owner_created)
    try:
        prepare(args.home)
    except Exception as error:
        failure = error if isinstance(error, SetupFailure) else setup_failure(error, 'files')
        append_log('browser-setup.log', f'failed: {failure.code}; {type(error).__name__}: {error}')
        emit(type='result', state='failed', message=str(failure), error=failure.code, progress=0.)
        raise SystemExit(1)
