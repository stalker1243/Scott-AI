# Библиотеки в Windows-дистрибутиве Scott AI

Scott AI использует Qt 6.11.2, Copyright The Qt Company Ltd. and contributors.
Qt поставляется отдельными динамическими библиотеками рядом с лаунчером.
Тексты LGPL v3, GPL v3 и исключения Qt находятся в этой папке. Сведения о
компонентах и сторонних библиотеках Qt копируются из установленного Qt SDK
в `licenses/qt-sbom.zip` при сборке. Архив содержит полные исходные сведения
из SDK; его можно открыть обычным архиватором.

- [Лицензирование Qt](https://doc.qt.io/qt-6/licensing.html)
- [Исходники Qt 6.11.2](https://code.qt.io/cgit/qt/qtbase.git/tree/?h=v6.11.2)
- [Исходники Qt Declarative](https://code.qt.io/cgit/qt/qtdeclarative.git/tree/?h=v6.11.2)
- [Исходники Scott AI и инструкции сборки](https://github.com/stalker1243/Scott-AI)

CPython 3.13.7 поставляется во встроенной сборке; его лицензия включена
в папку `runtime`. Библиотеки Python и модели ставятся при первом запуске;
их сведения о лицензиях сохраняются в установленных пакетах.

Необязательный пакет Scott Voice содержит собственные уведомления
в `voice-assets/NOTICE.md`; веса и отдельное окружение устанавливаются отдельно.
В него входит небольшой wheel `qwen-tts 0.1.1+scott.1` под Apache-2.0.
Исходная лицензия сохранена внутри wheel, изменения перечислены в
`SCOTT-NOTICE.txt`; исходный патч и сборщик находятся в `tools/voice_compat`
и `tools/build_voice_sdk.py` репозитория Scott AI.

Windows ScottSystem использует Core Audio и статически собранные runtime
MinGW/GCC. Тексты поставленного toolchain сохранены в `licenses/native`:
исключение GCC Runtime Library, уведомления MinGW-w64 и winpthreads.
GPL v3 находится рядом в `GPL-3.0-only.txt`. Исходник ScottSystem и его
инструкция сборки находятся в репозитории Scott AI, `backend/native`.
