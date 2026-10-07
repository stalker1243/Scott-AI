# AMD в Scott: ROCm/HIP

Добавлена первичная поддержка ускорения Whisper и Silero на AMD GPU.
Реальная проверка на Radeon ещё предстоит. Автоматические тесты проверяют
выбор устройства и обработку ошибок на подменённых движках.

## Совместимость

Нужны поддерживаемая карта, драйвер и PyTorch с HIP. Наличие драйвера Radeon
само по себе не включает ускорение. Поддержка зависит от конкретной модели
и ОС: проверьте [матрицу AMD](https://rocm.docs.amd.com/en/latest/compatibility/compatibility-matrix.html).
Для неподдерживаемых карт доступен CPU. Процессоры AMD работают через CPU
без ROCm.

Профиль установки Scott использует ROCm 10.0.0, PyTorch 2.13.0 и Python
3.11–3.14 на Windows/Linux. Для проекта рекомендуется Python 3.13.
Пакеты берутся из [официального индекса AMD](https://rocm.docs.amd.com/projects/ai-ecosystem/en/latest/frameworks/pytorch/install.html).
Драйвер установите по требованиям AMD для своей системы; скрипт Scott
устанавливает только Python-библиотеки.

## Windows: отдельное окружение

В PowerShell из корня проекта:

```powershell
py -3.13 -m venv .venv-amd
# Сначала показать команды установки, ничего не скачивая:
.\.venv-amd\Scripts\python.exe backend\setup_amd.py --gfx gfx1100
# Затем установить библиотеки и проверить вычисления на GPU:
.\.venv-amd\Scripts\python.exe backend\setup_amd.py --gfx gfx1100 --install
# Запустить Qt с этим Python:
.\ScottAI_qt\run.ps1 -Python (Resolve-Path .\.venv-amd\Scripts\python.exe).Path -Tab settings
```

`gfx1100` — пример. Подставьте архитектуру своей карты из матрицы AMD.
Если используете `--gfx all` или пропускаете параметр, профиль включает
все поддерживаемые архитектуры и скачивает больше данных.

`--install` разрешён только в виртуальном окружении. Скрипт устанавливает
PyTorch, зависимости backend и выполняет небольшую операцию на GPU.
Модели Whisper/Silero скачиваются при первом использовании, если их нет
в пользовательском кэше.

## Linux

Сначала подготовьте драйвер и систему по инструкции AMD. Из корня проекта:

```bash
python3.13 -m venv .venv-amd
.venv-amd/bin/python backend/setup_amd.py --gfx gfx1100
.venv-amd/bin/python backend/setup_amd.py --gfx gfx1100 --install
cd backend
../.venv-amd/bin/python main.py
```

Qt подключается к backend на `127.0.0.1:8000`. Автоматическое обнаружение
адаптеров в Linux использует `/sys/class/drm`, в Windows — системный список
видеоконтроллеров, включая версию драйвера.

## Выбор и проверка устройства

В Qt откройте **Настройки → Обработка**. Whisper и Silero имеют отдельные
кнопки **Авто**, **NVIDIA**, **AMD**, **Процессор**. Для Silero на macOS также
доступна **Apple**. AMD активна, когда PyTorch собран с HIP и видит GPU.
После переключения модель перезагрузится при следующем обращении.

Переменные `WHISPER_DEVICE=rocm` и `SILERO_DEVICE=rocm` задают AMD явно
и блокируют смену устройства в интерфейсе. Прежнее значение `cuda` в
HIP-окружении распознаётся как AMD. Авто выбирает доступный ускоритель;
при его отсутствии используется CPU.

Внутреннее значение `device="cuda"` на AMD корректно: HIP использует
[API PyTorch `torch.cuda`](https://docs.pytorch.org/docs/2.14/notes/hip.html).
Scott различает сборки по `torch.version.hip`, показывает AMD отдельно
и сохраняет выбор как `rocm`.

```powershell
.\.venv-amd\Scripts\python.exe -c "import torch; print('HIP:', torch.version.hip); print('GPU:', torch.cuda.is_available())"
Invoke-RestMethod http://127.0.0.1:8000/settings/device
Invoke-RestMethod http://127.0.0.1:8000/diagnostics/gpu
```

API настроек добавляет `rocm_available`, `rocm_build` и список `options`
для каждого движка. `cuda_available` означает NVIDIA CUDA. Поле `device`
показывает устройство для загрузки; при последующем сбое модель может
продолжить на CPU, о чём сообщает лог.

## Распознавание, синтез и запасной путь

- На AMD GPU Whisper использует PyTorch/openai-whisper. Обычные готовые
  GPU-пакеты CTranslate2 используют [NVIDIA CUDA](https://opennmt.net/CTranslate2/hardware_support.html),
  поэтому faster-whisper не выбирается для HIP GPU даже при явном выборе
  движка `faster`. CPU-версия faster-whisper остаётся доступной.
- Ошибки HIP, MIOpen, rocBLAS и нехватки памяти при распознавании запускают
  один повтор на CPU. CPU-модель сохраняется для следующих запросов.
- Silero при ошибке переноса на GPU или вычислений пробует CPU, сохраняя
  локальный голос. Если синтез всё равно не удался, действует прежний запасной
  путь озвучки Scott.
- Подготовка зависимостей сохраняет уже установленную сборку HIP. На AMD
  без неё выбирается профиль ROCm; при ошибке установки пробуется CPU.
  `SCOTT_TORCH_BACKEND=cpu` принудительно выбирает CPU-пакет при подготовке.

DirectML и показатели загрузки AMD GPU пока не реализованы. Скорость и
совместимость конкретной Radeon нужно проверять на физической карте.

Результаты проверок и ограничения: [отчёт backend](backend-amd-2026-10-05.md).
