"""Isolated stdlib window worker. Native failures never take down the server."""
import ctypes
import ctypes.util
import json
import os
from pathlib import Path
import subprocess
import sys

OPERATIONS = {'list', 'close', 'minimize', 'maximize', 'restore', 'focus', 'controls', 'invoke'}
OWN_IMAGES = {'scottaiqt.exe', 'scottaipet.exe', 'scottaiupdater.exe', 'scottsystem.exe'}
SYSTEM_IMAGES = {'csrss.exe', 'winlogon.exe', 'wininit.exe', 'lsass.exe', 'services.exe',
                 'svchost.exe', 'dwm.exe', 'sihost.exe', 'shellexperiencehost.exe'}


class Windows:
    def __init__(self, excluded):
        from ctypes import wintypes as w
        self.w = w; self.excluded = set(excluded)
        self.user = ctypes.WinDLL('user32', use_last_error=True)
        self.kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        self.dwm = ctypes.WinDLL('dwmapi')
        self.callback = ctypes.WINFUNCTYPE(w.BOOL, w.HWND, w.LPARAM)
        signatures = {
            'EnumWindows': ([self.callback, w.LPARAM], w.BOOL),
            'EnumChildWindows': ([w.HWND, self.callback, w.LPARAM], w.BOOL),
            'IsWindowEnabled': ([w.HWND], w.BOOL),
            'IsWindowVisible': ([w.HWND], w.BOOL), 'IsWindow': ([w.HWND], w.BOOL),
            'GetWindow': ([w.HWND, w.UINT], w.HWND), 'GetForegroundWindow': ([], w.HWND),
            'GetWindowThreadProcessId': ([w.HWND, ctypes.POINTER(w.DWORD)], w.DWORD),
            'GetWindowTextW': ([w.HWND, w.LPWSTR, ctypes.c_int], ctypes.c_int),
            'GetClassNameW': ([w.HWND, w.LPWSTR, ctypes.c_int], ctypes.c_int),
            'PostMessageW': ([w.HWND, w.UINT, w.WPARAM, w.LPARAM], w.BOOL),
            'ShowWindowAsync': ([w.HWND, ctypes.c_int], w.BOOL),
            'SetForegroundWindow': ([w.HWND], w.BOOL),
            'SendMessageTimeoutW': ([w.HWND,w.UINT,w.WPARAM,w.LPARAM,w.UINT,w.UINT,ctypes.POINTER(ctypes.c_size_t)],ctypes.c_ssize_t),
        }
        for name, (args, result) in signatures.items():
            function = getattr(self.user, name); function.argtypes = args; function.restype = result
        self.style = getattr(self.user, 'GetWindowLongPtrW', self.user.GetWindowLongW)
        self.style.argtypes = [w.HWND, ctypes.c_int]; self.style.restype = ctypes.c_ssize_t
        self.kernel.OpenProcess.argtypes = [w.DWORD, w.BOOL, w.DWORD]; self.kernel.OpenProcess.restype = w.HANDLE
        self.kernel.CloseHandle.argtypes = [w.HANDLE]; self.kernel.CloseHandle.restype = w.BOOL
        self.kernel.QueryFullProcessImageNameW.argtypes = [w.HANDLE, w.DWORD, w.LPWSTR, ctypes.POINTER(w.DWORD)]
        self.kernel.QueryFullProcessImageNameW.restype = w.BOOL
        self.dwm.DwmGetWindowAttribute.argtypes = [w.HWND, w.DWORD, ctypes.c_void_p, w.DWORD]
        self.dwm.DwmGetWindowAttribute.restype = ctypes.c_long

    def image(self, pid):
        process = self.kernel.OpenProcess(0x1000, False, pid)
        if not process:
            return ''
        try:
            length = self.w.DWORD(32768); buffer = ctypes.create_unicode_buffer(length.value)
            return Path(buffer.value).name if self.kernel.QueryFullProcessImageNameW(process, 0, buffer, ctypes.byref(length)) else ''
        finally:
            self.kernel.CloseHandle(process)

    def describe(self, handle):
        if not self.user.IsWindow(handle) or not self.user.IsWindowVisible(handle):
            return None
        pid = self.w.DWORD(); self.user.GetWindowThreadProcessId(handle, ctypes.byref(pid))
        if not pid.value or pid.value in self.excluded or pid.value == os.getpid():
            return None
        name = ctypes.create_unicode_buffer(256); self.user.GetClassNameW(handle, name, len(name))
        if name.value in {'Progman', 'WorkerW', 'Shell_TrayWnd', 'Shell_SecondaryTrayWnd'}:
            return None
        if self.user.GetWindow(handle, 4) or self.style(handle, -20) & 0x80:
            return None
        cloaked = self.w.DWORD()
        if self.dwm.DwmGetWindowAttribute(handle, 14, ctypes.byref(cloaked), ctypes.sizeof(cloaked)) == 0 and cloaked.value:
            return None
        app = self.image(pid.value)
        if not app or app.lower() in OWN_IMAGES | SYSTEM_IMAGES:
            return None
        title = ctypes.create_unicode_buffer(513); self.user.GetWindowTextW(handle, title, len(title))
        if not title.value.strip():
            return None
        return dict(id=hex(handle), pid=pid.value, app=app, title=title.value)

    def snapshot(self):
        windows = []
        @self.callback
        def collect(handle, _):
            if len(windows) >= 256:
                return False
            try:
                entry = self.describe(handle)
                if entry:
                    windows.append(entry)
            except (OSError, ValueError):
                pass  # A disappearing/inaccessible window is normal.
            return True
        self.user.EnumWindows(collect, 0)
        return dict(success=True, windows=windows, active=hex(self.user.GetForegroundWindow() or 0))

    def act(self, operation, targets):
        accepted, failed = [], []
        for target in targets:
            handle = int(target['id'], 16); current = self.describe(handle)
            if not current or current['pid'] != target['pid']:
                failed.append(target['id']); continue
            if operation == 'close':
                ok = self.user.PostMessageW(handle, 0x10, 0, 0)  # WM_CLOSE, never TerminateProcess.
            elif operation == 'focus':
                self.user.ShowWindowAsync(handle, 9)
                ok = self.user.SetForegroundWindow(handle)
            else:
                ok = self.user.ShowWindowAsync(handle, {'minimize': 6, 'maximize': 3, 'restore': 9}[operation])
            (accepted if ok else failed).append(target['id'])
        return dict(success=bool(accepted), accepted=accepted, failed=failed)

    def buttons(self, target, operation, control):
        root = int(target['id'],16); current = self.describe(root)
        if not current or current['pid'] != target['pid']:
            return dict(success=False,code='window_changed',message='Окно изменилось. Действие отменено.')
        buttons=[];inspected=0
        def label(value):
            return value.replace('&&','\x00').replace('&','').replace('\x00','&').strip()
        @self.callback
        def collect(handle,_):
            nonlocal inspected
            inspected+=1
            if inspected>1000:return False
            if not self.user.IsWindowVisible(handle) or not self.user.IsWindowEnabled(handle):return True
            pid=self.w.DWORD();self.user.GetWindowThreadProcessId(handle,ctypes.byref(pid))
            if pid.value!=target['pid']:return True
            kind=ctypes.create_unicode_buffer(256);self.user.GetClassNameW(handle,kind,len(kind))
            # Never read Edit/password text. Only standard Button-class HWNDs
            # (including WinForms' Button superclass) understand BM_CLICK.
            if kind.value.casefold()!='button' and not kind.value.casefold().startswith('windowsforms10.button.'):
                return True
            text=ctypes.create_unicode_buffer(161);self.user.GetWindowTextW(handle,text,len(text))
            name=label(text.value)
            if name:buttons.append((handle,name))
            return True
        self.user.EnumChildWindows(root,collect,0)
        if operation=='controls':
            return dict(success=True,controls=list(dict.fromkeys(name for _,name in buttons))[:80],provider='win32-control',truncated=inspected>1000)
        matches=[handle for handle,name in buttons if name.casefold()==control.strip().casefold()]
        if len(matches)!=1:
            return dict(success=False,code='ambiguous' if matches else 'no_control',message='Нашлось несколько одинаковых кнопок. Уточните окно.' if matches else 'Не нашёл доступную кнопку с таким названием.')
        handle=matches[0];pid=self.w.DWORD();self.user.GetWindowThreadProcessId(handle,ctypes.byref(pid))
        if pid.value!=target['pid'] or not self.user.IsWindowEnabled(handle):
            return dict(success=False,message='Кнопка изменилась. Действие отменено.')
        result=ctypes.c_size_t()
        ok=self.user.SendMessageTimeoutW(handle,0xF5,0,0,0x3,1000,ctypes.byref(result))
        return dict(success=bool(ok),invoked=bool(ok),provider='win32-control',
                    message='' if ok else 'Кнопка не подтвердила завершение нажатия. Автоматического повтора не было.')


class X11:
    def __init__(self, excluded):
        import shutil
        if os.environ.get('XDG_SESSION_TYPE') == 'wayland' or os.environ.get('WAYLAND_DISPLAY'):
            raise RuntimeError('Wayland не предоставляет общего управления окнами. Запуск приложений доступен.')
        self.tool = shutil.which('wmctrl'); self.excluded = set(excluded)
        if not os.environ.get('DISPLAY') or not self.tool:
            raise RuntimeError('Для управления окнами X11 нужен wmctrl и активный сеанс X11.')

    def run(self, *args):
        result = subprocess.run([self.tool, *args], capture_output=True, timeout=2)
        if result.returncode:
            raise RuntimeError('Менеджер окон не подтвердил действие.')
        return result.stdout.decode('utf-8', errors='replace')[:262144]

    def xlib(self):
        library = ctypes.util.find_library('X11')
        if not library:
            raise RuntimeError('Библиотека X11 недоступна.')
        x = ctypes.CDLL(library)
        x.XOpenDisplay.argtypes = [ctypes.c_char_p]; x.XOpenDisplay.restype = ctypes.c_void_p
        x.XCloseDisplay.argtypes = [ctypes.c_void_p]
        x.XDefaultScreen.argtypes = [ctypes.c_void_p]; x.XDefaultScreen.restype = ctypes.c_int
        x.XDefaultRootWindow.argtypes = [ctypes.c_void_p]; x.XDefaultRootWindow.restype = ctypes.c_ulong
        x.XInternAtom.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_int]; x.XInternAtom.restype = ctypes.c_ulong
        x.XGetWindowProperty.argtypes = [ctypes.c_void_p, ctypes.c_ulong, ctypes.c_ulong, ctypes.c_long,
            ctypes.c_long, ctypes.c_int, ctypes.c_ulong, ctypes.POINTER(ctypes.c_ulong), ctypes.POINTER(ctypes.c_int),
            ctypes.POINTER(ctypes.c_ulong), ctypes.POINTER(ctypes.c_ulong), ctypes.POINTER(ctypes.POINTER(ctypes.c_ubyte))]
        x.XIconifyWindow.argtypes = [ctypes.c_void_p, ctypes.c_ulong, ctypes.c_int]; x.XIconifyWindow.restype = ctypes.c_int
        x.XFlush.argtypes = [ctypes.c_void_p]
        x.XFree.argtypes = [ctypes.c_void_p]
        display = x.XOpenDisplay(None)
        if not display:
            raise RuntimeError('Нет подключения к рабочему столу X11.')
        return x, display

    def snapshot(self):
        windows = []
        for line in self.run('-lp').splitlines():
            parts = line.split(None, 4)
            if len(parts) != 5:
                continue
            identifier, desktop, pid, _, title = parts
            try:
                pid = int(pid)
                int(identifier, 16)
            except ValueError:
                continue
            if pid <= 0 or pid in self.excluded or int(desktop) < 0:
                continue
            try:
                app = Path(f'/proc/{pid}/comm').read_text().strip()
            except OSError:
                continue
            if app.lower().startswith(('scottai', 'gnome-shell', 'plasmashell')):
                continue
            windows.append(dict(id=hex(int(identifier, 16)), pid=pid, app=app, title=title[:512]))
            if len(windows) >= 256:
                break
        active = '0x0'
        x, display = self.xlib()
        try:
            atom = x.XInternAtom(display, b'_NET_ACTIVE_WINDOW', 0)
            actual = ctypes.c_ulong(); fmt = ctypes.c_int(); count = ctypes.c_ulong(); extra = ctypes.c_ulong()
            data = ctypes.POINTER(ctypes.c_ubyte)()
            result = x.XGetWindowProperty(display, x.XDefaultRootWindow(display), atom, 0, 1, 0, 0,
                ctypes.byref(actual), ctypes.byref(fmt), ctypes.byref(count), ctypes.byref(extra), ctypes.byref(data))
            if result == 0 and data:
                if fmt.value == 32 and count.value:
                    active = hex(ctypes.cast(data, ctypes.POINTER(ctypes.c_ulong))[0])
                x.XFree(data)
        finally:
            x.XCloseDisplay(display)
        return dict(success=True, windows=windows, active=active)

    def act(self, operation, targets):
        current = {row['id']: row for row in self.snapshot()['windows']}
        accepted, failed = [], []
        for target in targets:
            if target['id'] not in current or current[target['id']]['pid'] != target['pid']:
                failed.append(target['id']); continue
            try:
                if operation == 'minimize':
                    x, display = self.xlib()
                    try:
                        if not x.XIconifyWindow(display, int(target['id'], 16), x.XDefaultScreen(display)):
                            raise RuntimeError('Не удалось свернуть окно.')
                        x.XFlush(display)
                    finally:
                        x.XCloseDisplay(display)
                elif operation == 'close': self.run('-ic', target['id'])
                elif operation == 'focus': self.run('-ia', target['id'])
                elif operation == 'maximize': self.run('-ir', target['id'], '-b', 'add,maximized_vert,maximized_horz')
                else:
                    self.run('-ir', target['id'], '-b', 'remove,maximized_vert,maximized_horz')
                    self.run('-ia', target['id'])
                accepted.append(target['id'])
            except (OSError, RuntimeError, subprocess.TimeoutExpired):
                failed.append(target['id'])
        return dict(success=bool(accepted), accepted=accepted, failed=failed)


def main():
    raw = sys.stdin.buffer.read(16385)
    if len(raw) > 16384:
        raise ValueError('Слишком большой запрос управления окнами.')
    spec = json.loads(raw)
    operation = spec['operation']
    if operation not in OPERATIONS:
        raise ValueError('Неизвестное действие с окном.')
    excluded = [int(pid) for pid in spec.get('exclude_pids', [])][:64]
    desktop = Windows(excluded) if sys.platform == 'win32' else X11(excluded) if sys.platform.startswith('linux') else None
    if desktop is None:
        raise RuntimeError('Управление окнами этой системы пока недоступно.')
    if operation == 'list':
        result = desktop.snapshot()
    else:
        targets = spec.get('targets', [])
        if not isinstance(targets, list) or not 1 <= len(targets) <= 64:
            raise ValueError('Неверный список окон.')
        if operation in ('controls','invoke'):
            if not isinstance(desktop,Windows) or len(targets)!=1:
                raise ValueError('Действие с кнопкой доступно для одного окна Windows.')
            control=spec.get('control','')
            if not isinstance(control,str) or len(control)>160:
                raise ValueError('Неверное название кнопки.')
            result=desktop.buttons(targets[0],operation,control)
        else:
            result = desktop.act(operation, targets)
    print(json.dumps(result, ensure_ascii=True))


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print(json.dumps(dict(success=False, message=str(error)[:400]), ensure_ascii=True))
        raise SystemExit(1)
