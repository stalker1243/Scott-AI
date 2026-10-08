#!/usr/bin/env bash
set -euo pipefail
scott_root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
source "$scott_root/python-environment.sh"
if [[ ! -x "$scott_root/runtime/bin/python" ]]; then
    echo 'Сначала установите приложение: ./install.sh' >&2
    exit 1
fi
export LD_LIBRARY_PATH="$scott_root/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
export QT_PLUGIN_PATH="$scott_root/plugins"
export QML2_IMPORT_PATH="$scott_root/qml"
export QML_IMPORT_PATH="$scott_root/qml"
# The package deploys XCB. Wayland sessions use XWayland until a native plugin
# is shipped; an explicit platform override still belongs to the user.
export QT_QPA_PLATFORM="${QT_QPA_PLATFORM:-xcb}"
cd -- "$scott_root"
exec "$scott_root/launcher/ScottAIQt" --start-backend "$@"
