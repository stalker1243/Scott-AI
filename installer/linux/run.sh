#!/usr/bin/env bash
set -euo pipefail
umask 077
scott_root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
source "$scott_root/python-environment.sh"
scott_python="$scott_root/runtime/bin/python"
if [[ -f "$scott_root/backend/linux_runtime.py" && -f "$scott_root/.scott-linux-install.json" ]]; then
    scott_python=$("$scott_root/python-runtime/bin/python3.13" -I "$scott_root/backend/linux_runtime.py" --root "$scott_root")
    # Also works when an AppImage has no per-user runtime symlink in its image.
    set -- --python "$scott_python" --backend-dir "$scott_root/backend" "$@"
fi
if [[ ! -x "$scott_python" ]]; then
    echo 'Сначала установите приложение: ./install.sh' >&2
    exit 1
fi
export LD_LIBRARY_PATH="$scott_root/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
export QT_PLUGIN_PATH="$scott_root/plugins"
export QML2_IMPORT_PATH="$scott_root/qml"
export QML_IMPORT_PATH="$scott_root/qml"
# Prefer native Wayland only with an available socket and our own plugin.
# Old packages and X11 sessions continue to use XCB. Respect explicit overrides.
if [[ -z "${QT_QPA_PLATFORM:-}" ]]; then
    scott_wayland_socket="${WAYLAND_DISPLAY:-wayland-0}"
    if [[ "$scott_wayland_socket" != /* ]]; then
        if [[ "${XDG_RUNTIME_DIR:-}" == /* ]]; then
            scott_wayland_socket="$XDG_RUNTIME_DIR/$scott_wayland_socket"
        else
            scott_wayland_socket=/nonexistent
        fi
    fi
    if [[ -S "$scott_wayland_socket" ]] && { [[ -f "$scott_root/plugins/platforms/libqwayland.so" ]] || [[ -f "$scott_root/plugins/platforms/libqwayland-generic.so" ]]; }; then
        export QT_QPA_PLATFORM='wayland;xcb'
    else
        export QT_QPA_PLATFORM=xcb
    fi
fi
# Backend and setup receive absolute paths and set their own working directory.
# Keep the caller's directory writable for diagnostic/visual test output.
exec "$scott_root/launcher/ScottAIQt" --start-backend "$@"
