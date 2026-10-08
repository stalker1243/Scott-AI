#!/usr/bin/env bash
set -euo pipefail
scott_root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
source "$scott_root/python-environment.sh"
scott_python="$scott_root/python-runtime/bin/python3.13"
if [[ ! -x "$scott_python" ]]; then
    scott_python=python3
fi
exec "$scott_python" -I "$scott_root/install.py" --uninstall --prefix "$scott_root" "$@"
