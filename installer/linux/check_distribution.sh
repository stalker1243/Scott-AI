#!/usr/bin/env bash
set -euo pipefail
if [[ "${SCOTT_CONTAINER_TEST:-}" != 1 || ! -f /.dockerenv ]]; then
    echo 'This check is only for disposable Docker CI containers.' >&2
    exit 1
fi
source /etc/os-release
case "$ID" in
    ubuntu|debian)
        export DEBIAN_FRONTEND=noninteractive
        apt-get update
        apt-get install -y ca-certificates tar gzip xvfb fonts-dejavu-core libegl1 libgl1 libxkbcommon-x11-0 libxcb-cursor0 libxcb-icccm4 libxcb-keysyms1 libxcb-image0 libxcb-render-util0 libxcb-xinerama0 libxcb-xkb1 libpulse0 libportaudio2 ffmpeg
        ;;
    fedora)
        dnf install -y ca-certificates tar gzip xorg-x11-server-Xvfb dejavu-sans-fonts mesa-libEGL mesa-libGL libxkbcommon-x11 xcb-util-cursor xcb-util-wm xcb-util-keysyms xcb-util-image xcb-util-renderutil libXcursor libXrandr libXi libXrender pulseaudio-libs portaudio ffmpeg-free
        ;;
    arch)
        pacman -Syu --noconfirm --needed ca-certificates tar gzip xorg-server-xvfb ttf-dejavu mesa libglvnd libxkbcommon libxkbcommon-x11 libxcb xcb-util-cursor xcb-util-wm xcb-util-keysyms xcb-util-image xcb-util-renderutil libxcursor libxrandr libxi libxrender libpulse portaudio ffmpeg
        ;;
    *) echo "Unsupported CI image: $ID" >&2; exit 1 ;;
esac
echo "Distribution: $PRETTY_NAME"
export RUNNER_TEMP=/tmp/scott-check
export WARMUP_MODELS=0 SCOTT_SEMANTIC_MEMORY=0 PYTHONDONTWRITEBYTECODE=1
export QSG_RHI_BACKEND=software QT_QUICK_BACKEND=software
mkdir -p "$RUNNER_TEMP/package"
cd /artifact
sha256sum -c ./*.sha256
tar -xzf ./*.tar.gz -C "$RUNNER_TEMP/package"
scott_source=$(find "$RUNNER_TEMP/package" -mindepth 1 -maxdepth 1 -type d)
source "$scott_source/python-environment.sh"
"$scott_source/python-runtime/bin/python3.13" -I /checks/check_package.py --package "$scott_source"
scott_prefix="$RUNNER_TEMP/Scott AI package"
scott_python="$scott_prefix/runtime/bin/python"
"$scott_python" -I -m pip install --index-url https://download.pytorch.org/whl/cpu torch==2.9.1+cpu
"$scott_python" -I -m pip install -r "$scott_prefix/backend/requirements.txt"
"$scott_python" -I -m pip check
"$scott_python" -I /checks/check_backend.py --prefix "$scott_prefix"
Xvfb :99 -screen 0 1280x800x24 -nolisten tcp &
scott_xvfb=$!
trap 'kill "$scott_xvfb" 2>/dev/null || true' EXIT
for scott_try in {1..30}; do
    [[ -S /tmp/.X11-unix/X99 ]] && break
    sleep 0.1
done
export DISPLAY=:99
"$scott_prefix/run.sh" --smoke-chat
"$scott_prefix/run.sh" --smoke-voice
echo "Distribution package check passed: $PRETTY_NAME"
