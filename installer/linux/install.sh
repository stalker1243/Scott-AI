#!/usr/bin/env bash
#
# Установка Scott AI на Linux.
#
# Ставит в папку пользователя и не просит прав администратора: программа пишет
# рядом с собой — логи, данные, кэш речи, — и в системных каталогах это
# упиралось бы в права.
#
# Тяжёлого здесь нет: torch и модели речи (около 4.5 ГБ) скачиваются при первом
# запуске, когда уже известно, есть ли в машине видеокарта NVIDIA.

set -euo pipefail

APP_DIR="${SCOTT_INSTALL_DIR:-$HOME/.local/share/scottai}"
BIN_LINK="$HOME/.local/bin/scottai"
DESKTOP_DIR="$HOME/.local/share/applications"
ICON_DIR="$HOME/.local/share/icons/hicolor/256x256/apps"
SOURCE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

say() { printf '  %s\n' "$1"; }
fail() { printf '\n  ОШИБКА: %s\n\n' "$1" >&2; exit 1; }

echo
echo "Установка Scott AI"
echo

# ---------------------------------------------------------------- проверки
#
# Всё, чего может не хватать, проверяется ДО копирования файлов: лучше сказать
# заранее, чем оставить человека с наполовину установленной программой.

command -v python3 >/dev/null 2>&1 || fail "не найден python3 — установите его и повторите"

PY_VERSION="$(python3 -c 'import sys; print("%d.%d" % sys.version_info[:2])')"
PY_MAJOR="${PY_VERSION%%.*}"
PY_MINOR="${PY_VERSION##*.}"

if [ "$PY_MAJOR" -lt 3 ] || { [ "$PY_MAJOR" -eq 3 ] && [ "$PY_MINOR" -lt 10 ]; }; then
    fail "нужен Python 3.10 или новее, найден $PY_VERSION"
fi
say "Python $PY_VERSION — подходит"

# Модуль venv в Debian и Ubuntu лежит отдельным пакетом, и без него установка
# зависимостей упрётся в защиту системного Python (PEP 668).
python3 -c 'import venv' >/dev/null 2>&1 || fail \
    "не хватает модуля venv — установите: sudo apt install python3-venv"

# PortAudio нужен для микрофона (sounddevice). Без него Scott запустится, но
# слушать не сможет, поэтому предупреждаем, а не падаем.
if ! ldconfig -p 2>/dev/null | grep -q libportaudio; then
    say "ВНИМАНИЕ: не найден libportaudio2 — микрофон работать не будет."
    say "          Установите: sudo apt install libportaudio2"
fi

# ---------------------------------------------------------------- установка
say "Ставлю в $APP_DIR"
mkdir -p "$APP_DIR"

# rsync есть не везде, поэтому обычный cp. Прежняя установка перезаписывается,
# но данные пользователя (backend/data) остаются нетронутыми.
cp -r "$SOURCE_DIR/backend" "$APP_DIR/"
cp -r "$SOURCE_DIR/launcher" "$APP_DIR/"
cp "$SOURCE_DIR/VERSION.json" "$APP_DIR/" 2>/dev/null || true
cp "$SOURCE_DIR/.env.example" "$APP_DIR/" 2>/dev/null || true
cp "$SOURCE_DIR/README.md" "$APP_DIR/" 2>/dev/null || true

chmod +x "$APP_DIR/launcher/ScottAI"

# ------------------------------------------------------------- окружение
#
# Виртуальное окружение живёт в runtime/ — там же, где лаунчер ищет Python на
# Linux (runtime/bin/python3). Системный Python не трогаем вовсе: в свежих
# Debian и Ubuntu ставить в него пакеты запрещено (PEP 668), да и чужие
# программы от этого страдать не должны.
if [ ! -x "$APP_DIR/runtime/bin/python3" ]; then
    say "Создаю окружение Python (это займёт несколько секунд)…"
    python3 -m venv "$APP_DIR/runtime"
else
    say "Окружение Python уже есть — оставляю как есть"
fi

"$APP_DIR/runtime/bin/python3" -m pip install --quiet --upgrade pip >/dev/null 2>&1 || true

# --------------------------------------------------------------- ярлыки
mkdir -p "$DESKTOP_DIR" "$ICON_DIR" "$(dirname "$BIN_LINK")"

if [ -f "$SOURCE_DIR/scott.png" ]; then
    cp "$SOURCE_DIR/scott.png" "$ICON_DIR/scottai.png"
fi

cat > "$DESKTOP_DIR/scottai.desktop" <<DESKTOP
[Desktop Entry]
Type=Application
Name=Scott AI
Comment=Голосовой ассистент, который слушает и управляет компьютером
Exec=$APP_DIR/launcher/ScottAI
Icon=scottai
Terminal=false
Categories=Utility;AudioVideo;
StartupWMClass=ScottAI
DESKTOP

chmod +x "$DESKTOP_DIR/scottai.desktop"
ln -sf "$APP_DIR/launcher/ScottAI" "$BIN_LINK"

# Меню приложений обновляется само, но не сразу: подтолкнём, если есть чем.
command -v update-desktop-database >/dev/null 2>&1 && \
    update-desktop-database "$DESKTOP_DIR" >/dev/null 2>&1 || true

echo
say "Готово."
say "Запустить: из меню приложений «Scott AI» или командой scottai"
say "При первом запуске Scott скачает библиотеки и модели речи — около 4.5 ГБ."
echo
say "Удалить: $APP_DIR/uninstall.sh"
echo

# ------------------------------------------------------------ удаление
cat > "$APP_DIR/uninstall.sh" <<UNINSTALL
#!/usr/bin/env bash
# Удаление Scott AI.
set -eu

echo "Удаляю Scott AI…"
rm -rf "$APP_DIR"
rm -f "$DESKTOP_DIR/scottai.desktop"
rm -f "$ICON_DIR/scottai.png"
rm -f "$BIN_LINK"

echo "Готово. Модели речи остались в ~/.cache — они общие для программ на PyTorch."
echo "Если они больше не нужны: rm -rf ~/.cache/whisper ~/.cache/torch/hub/snakers4_silero-models_master"
UNINSTALL

chmod +x "$APP_DIR/uninstall.sh"
