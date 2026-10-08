# Scott AI на Linux

Экспериментальный Qt-пакет для Linux x86-64. Он включает приложение,
библиотеки Qt, QML-модули, backend и отдельный Python 3.13.16. Системный Python
для установки не нужен; зависимости и модели речи устанавливаются при первом
запуске. Установка, backend и запуск X11 проверены на Ubuntu 22.04/24.04,
Debian 12/13, Fedora 44 и Arch. GNOME/KDE, голос на настоящем устройстве и
Wayland ещё предстоит проверить. Scott Voice остаётся экспериментом Windows/NVIDIA.

В 2.0.1 улучшены загрузка моделей и выбор компактной CPU-установки:
[первая подготовка и размер](installation.md).
Пакет включает X11-плагин XCB. Для сеанса Wayland нужен XWayland;
нативный Wayland пока не включён.

## Установка

Сначала установите системные библиотеки для своего дистрибутива.

### Ubuntu 22.04/24.04 и Debian 12/13

```bash
sudo apt-get install ca-certificates fonts-dejavu-core libportaudio2 libpulse0 ffmpeg \
  libegl1 libgl1 libopengl0 libxkbcommon-x11-0 libxcb-cursor0 libxcb-icccm4 \
  libxcb-keysyms1 libxcb-image0 libxcb-render-util0 libxcb-xinerama0 libxcb-xkb1
```

### Fedora 44

```bash
sudo dnf install ca-certificates dejavu-sans-fonts mesa-libEGL mesa-libGL \
  libxkbcommon-x11 xcb-util-cursor xcb-util-wm xcb-util-keysyms \
  xcb-util-image xcb-util-renderutil libXcursor libXrandr libXi libXrender \
  pulseaudio-libs portaudio ffmpeg-free
```

Для сеанса Wayland, если XWayland ещё не установлен:

```bash
sudo dnf install xorg-x11-server-Xwayland
```

### Arch Linux

```bash
sudo pacman -Syu --needed ca-certificates ttf-dejavu mesa libglvnd \
  libxkbcommon libxkbcommon-x11 libxcb xcb-util-cursor xcb-util-wm \
  xcb-util-keysyms xcb-util-image xcb-util-renderutil libxcursor \
  libxrandr libxi libxrender libpulse portaudio ffmpeg
```

Для сеанса Wayland, если XWayland ещё не установлен:

```bash
sudo pacman -S --needed xorg-xwayland
```

### Установка приложения

Скачайте [архив Linux x86-64](https://github.com/stalker1243/Scott-AI/releases/download/v2.0.1/ScottAI-2.0.1-Qt-linux-x86_64.tar.gz)
и [файл SHA256](https://github.com/stalker1243/Scott-AI/releases/download/v2.0.1/ScottAI-2.0.1-Qt-linux-x86_64.tar.gz.sha256).
Вход в GitHub для скачивания выпуска не нужен.

```bash
sha256sum -c ScottAI-2.0.1-Qt-linux-x86_64.tar.gz.sha256
tar -xzf ScottAI-2.0.1-Qt-linux-x86_64.tar.gz
cd ScottAI-2.0.1-Qt-linux-x86_64
./install.sh
~/.local/share/ScottAI/run.sh
```

Сама установка выполняется без sudo и создаёт ярлык в меню приложений.
Папку можно выбрать через `./install.sh --prefix /путь/к/ScottAI`.
Нужны интернет и место под зависимости и модели. Python включён в пакет;
его архив закреплён по SHA256. Установка не меняет системный Python.
Источник Python — [python-build-standalone, выпуск 20261003](https://github.com/astral-sh/python-build-standalone/releases/tag/20261003).
При обновлении прежней установки окружение backend пересоздаётся на встроенном
Python; библиотеки потребуется подготовить заново. История и настройки остаются
на месте. Если создание окружения не удалось, прежнее окружение восстанавливается.
При обновлении используйте тот же путь установки: `.env`, история, вложения
и настройки моделей сохраняются. Установщик откажется писать в чужую непустую
папку или через символическую ссылку.

## Удаление

```bash
~/.local/share/ScottAI/uninstall.sh
```

По умолчанию рабочие данные сохраняются. Для их явного удаления:

```bash
~/.local/share/ScottAI/uninstall.sh --delete-data
```

Повторная установка в прежнюю папку использует сохранённые данные.

## Сборка из исходников

Нужны Linux x86-64, CMake 3.24+, Ninja, GCC, Python 3.11+ и Qt 6.8+ с Qt Quick,
QuickControls2, Network, Widgets и Test. CI использует Qt 6.11.2.

```bash
python3 -m venv installer/.cache/build-python
installer/.cache/build-python/bin/python -m pip install psutil==7.2.2
installer/.cache/build-python/bin/python installer/build_linux.py --qt-root /путь/к/Qt/6.11.2/gcc_64
xvfb-run -a ctest --test-dir ScottAI_qt/build-linux --output-on-failure \
  -E 'window_lifecycle|window_states|qml_screens'
python3 backend/run_tests.py
```

Результат — `installer/release/ScottAI-<версия>-Qt-linux-x86_64.tar.gz`
и файл `.sha256`. Сборщик использует CMake deployment API Qt и включает
использованные QML-модули, библиотеки и плагины. Уже существующий пакет
не перезаписывается; для повторной сборки выберите новый `--output` и сохраните
или уберите предыдущий архив.

Проверки не включают микрофон и не исполняют голосовые команды. В CI проверяются
установка, обновление, сохранение синтетических данных, удаление, переустановка
и запуск упакованного интерфейса без доступа к Qt SDK. Тесты поведения
настоящего Windows-композитора в Linux-набор не входят.

Выпуск 2.0.1: 8 октября 2026 года [сборка на Ubuntu 24.04](https://github.com/stalker1243/Scott-AI/actions/runs/37800830112)
прошла 13 проверок Qt и 1790 тестов backend на Python из пакета. Пропущены 11
проверок установки необязательного Scott Voice для Windows; 7 integration/slow
исключены. Полная загрузка Whisper small и Silero в новом CPU-кеше и проверка
готовности прошли. [Тот же архив прошёл матрицу дистрибутивов](https://github.com/stalker1243/Scott-AI/actions/runs/37800830112):

| Система | Окружение проверки | Результат |
| --- | --- | --- |
| Ubuntu 24.04 | GitHub Actions, Xvfb | Успешно |
| Ubuntu 22.04 | Контейнер, Xvfb | Успешно |
| Debian 12 и 13 | Контейнеры, Xvfb | Успешно |
| Fedora 44 | Контейнер, Xvfb | Успешно |
| Arch Linux | Контейнер, Xvfb; состояние на 8 октября | Успешно |

В матрице проверены встроенный Python, системные сертификаты, установка при
запрещённом системном Python, обновление, сохранение данных и переустановка,
зависимости backend, health/API чатов и интерфейс X11. GNOME/KDE, Wayland,
трей, GPU и реальный звук пока не проверены. Mint требует отдельной проверки.

Матрицу можно повторить отдельно через workflow «Проверка Linux-дистрибутивов»:
укажите ID сборки, которая загрузила артефакт `ScottAI-Qt-Linux-x86_64`. Это
позволяет проверить новые системные зависимости на уже собранном архиве.

Qt deployment API: [развёртывание Qt Quick](https://doc.qt.io/qt-6/cmake-deployment.html).
