#!/bin/sh
# Accept both `sh ./install.sh` and `bash ./install.sh`, even without +x.
if [ -z "${BASH_VERSION:-}" ]; then
    if ! command -v bash >/dev/null 2>&1; then
        printf '%s\n' 'Для установки ScottAI нужен bash. Установите пакет bash и запустите: bash ./install.sh' >&2
        exit 1
    fi
    exec bash "$0" "$@"
fi
set -euo pipefail
umask 077
scott_source=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
scott_state="${XDG_STATE_HOME:-}"
if [[ "$scott_state" != /* ]]; then scott_state="$HOME/.local/state"; fi
scott_logs="${SCOTT_LOG_DIR:-$scott_state/ScottAI/logs}"
if ! mkdir -p -- "$scott_logs"; then
    printf 'Не удалось создать папку журналов: %s. Выберите доступную папку через SCOTT_LOG_DIR.\n' "$scott_logs" >&2
    exit 1
fi
export SCOTT_LOG_DIR="$scott_logs"
scott_log="$scott_logs/linux-install.log"
if [[ -L "$scott_log" ]]; then
    echo 'Журнал установки является ссылкой. Выберите другую папку SCOTT_LOG_DIR.' >&2
    exit 1
fi
if [[ -f "$scott_log" ]] && (( $(wc -c < "$scott_log") > 2097152 )); then
    mv -f -- "$scott_log" "$scott_log.1"
fi
if ! touch -- "$scott_log"; then
    printf 'Нет доступа к журналу: %s. Выберите другую папку SCOTT_LOG_DIR.\n' "$scott_log" >&2
    exit 1
fi
chmod 600 -- "$scott_log"
exec > >(tee -a -- "$scott_log") 2>&1
trap 'scott_code=$?; if (( scott_code != 0 )); then printf "Установка остановлена (код %s). Журнал: %s\n" "$scott_code" "$scott_log"; fi' EXIT
printf 'ScottAI: проверяем установщик. Журнал: %s\n' "$scott_log"
for scott_file in python-environment.sh install.py; do
    if [[ ! -f "$scott_source/$scott_file" ]]; then
        printf 'Пакет распакован не полностью: отсутствует %s. Распакуйте весь архив в одну папку.\n' "$scott_file" >&2
        exit 1
    fi
done
source "$scott_source/python-environment.sh"
scott_python="$scott_source/python-runtime/bin/python3.13"
if [[ ! -f "$scott_python" ]]; then
    echo 'В пакете отсутствует встроенный Python. Распакуйте полный архив ScottAI.' >&2
    exit 1
fi
if ! "$scott_python" -I -B -c 'import sys; assert sys.version_info[:2] == (3,13)' ; then
    echo 'Встроенный Python не запускается из распакованной папки (права или noexec).'
    echo 'Пробуем системный Python только для копирования установщика; backend получит Python из пакета.'
    scott_fallback=$(command -v python3 || true)
    if [[ -z "$scott_fallback" ]] || ! "$scott_fallback" -I -B -c 'import sys; assert sys.version_info >= (3,11)'; then
        echo 'Распакуйте архив в домашнюю папку на разделе с разрешённым запуском и выполните: bash ./install.sh' >&2
        exit 1
    fi
    scott_python="$scott_fallback"
fi
"$scott_python" -I -B "$scott_source/install.py" "$@"
