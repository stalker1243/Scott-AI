#!/usr/bin/env bash
set -euo pipefail
scott_source=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
exec python3 "$scott_source/install.py" "$@"
