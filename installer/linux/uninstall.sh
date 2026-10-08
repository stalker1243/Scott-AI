#!/usr/bin/env bash
set -euo pipefail
scott_root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
exec python3 "$scott_root/install.py" --uninstall --prefix "$scott_root" "$@"
