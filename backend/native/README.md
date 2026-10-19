# ScottSystem

Небольшой Windows C++17 CLI для Core Audio: `probe`, `status`,
`volume 0..100`, `delta -100..100`, `mute 0|1`. Ответ — JSON protocol 1;
ошибка возвращает код 1. Числа и аргументы проверяются до обращения к устройству.
Вызовы ограничены четырьмя секундами со стороны Python.

Qt Windows-сборка создаёт ScottSystem.exe рядом с ScottAIQt.exe. Упаковщик
кладёт его в backend/native; Python ищет пакетный путь, затем путь Qt-сборки.
В MinGW runtime связан статически: дополнительные Qt/MinGW DLL не нужны.
Полезность этого переноса — убрать запуск PowerShell для системной громкости.
На Linux/macOS Python вызывает фиксированные системные инструменты.

Можно собрать отдельно, без Qt:

```powershell
cmake -S backend/native -B backend/native/build -G Ninja -DCMAKE_BUILD_TYPE=Release
cmake --build backend/native/build
ctest --test-dir backend/native/build --output-on-failure
```

Нужны CMake 3.24+, Windows C++ toolchain и Windows SDK/MinGW headers.
Автоматический CLI-тест вызывает probe и неверные аргументы; он не меняет звук.

Замер на машине разработки: бинарник 145 920 байт; запуск probe медиана
16,12 мс, запуск с чтением Core Audio — 21,45 мс (20 повторов каждого).
Пустой PowerShell запускался за 129,07 мс (7 повторов). Это стоимость запуска
и чтения, а не замер изменения громкости или полного ответа ассистента.
Отчёт: reports/backend-expansion/native-check.json.

Перенос маленького Python-модуля не уменьшает вес нейросетевых библиотек.
В этом окружении torch занимает 4 142 370 741 байт, а корневые Python-модули
backend — около 1,7 МБ. Для существенного уменьшения размера нужен отдельный
эксперимент с движками STT/TTS и сравнение качества на сохранённых WAV.
Модели, эталон Scott Voice и выбранные настройки этим этапом не меняются.
