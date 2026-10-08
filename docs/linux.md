# Scott AI на Linux

Экспериментальный Qt-пакет для Ubuntu 24.04 x86-64. Он включает приложение,
библиотеки Qt, QML-модули и backend. Системный Python используется для создания
отдельного окружения; зависимости и модели речи устанавливаются при первом
запуске. Голос на настоящем устройстве, Wayland и другие дистрибутивы пока
не проверены. Scott Voice остаётся экспериментом Windows/NVIDIA.

## Установка

Для Ubuntu 24.04:

```bash
sudo apt-get install python3 python3-venv libportaudio2 libpulse0 ffmpeg \
  libegl1 libgl1 libxkbcommon-x11-0 libxcb-cursor0 libxcb-icccm4 \
  libxcb-keysyms1 libxcb-image0 libxcb-render-util0 libxcb-xinerama0 libxcb-xkb1
```

Скачайте архив и файл `.sha256` среди артефактов успешного запуска
[сборки Linux](https://github.com/stalker1243/Scott-AI/actions/workflows/linux-qt.yml).
GitHub может запросить вход для скачивания артефактов.

```bash
sha256sum -c ScottAI-2.0.0-Qt-linux-x86_64.tar.gz.sha256
tar -xzf ScottAI-2.0.0-Qt-linux-x86_64.tar.gz
cd ScottAI-2.0.0-Qt-linux-x86_64
./install.sh
~/.local/share/ScottAI/run.sh
```

Сама установка выполняется без sudo и создаёт ярлык в меню приложений.
Папку можно выбрать через `./install.sh --prefix /путь/к/ScottAI`.
Нужны Python 3.11–3.13, интернет и место под зависимости и модели.
Если системный Python новее, установите Python 3.13 с модулем venv и запустите
`python3.13 install.py` из распакованного архива.
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

Нужны Linux x86-64, CMake 3.24+, Ninja, GCC, Python и Qt 6.8+ с Qt Quick,
QuickControls2, Network, Widgets и Test. CI использует Qt 6.11.2.

```bash
python3 installer/build_linux.py --qt-root /путь/к/Qt/6.11.2/gcc_64
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

Qt deployment API: [развёртывание Qt Quick](https://doc.qt.io/qt-6/cmake-deployment.html).
