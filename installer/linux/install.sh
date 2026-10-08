#!/usr/bin/env bash
set -euo pipefail
scott_source=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
source "$scott_source/python-environment.sh"
scott_python="$scott_source/python-runtime/bin/python3.13"
if [[ ! -x "$scott_python" ]]; then
    echo 'В пакете отсутствует встроенный Python. Распакуйте полный архив ScottAI.' >&2
    exit 1
fi
exec "$scott_python" -I "$scott_source/install.py" "$@"
