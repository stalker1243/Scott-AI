### Maltruand Launcher (красивый UI + ярлык)

У тебя два варианта лаунчера:

- **Красивый лаунчер с анимациями (Qt / PySide6)** — рекомендуется
- **Простой встроенный лаунчер (Tkinter)** — работает без установки доп. пакетов

## 1) Установка красивого лаунчера (Qt)

```powershell
cd "C:\Users\SKYNET\OneDrive\Рабочий стол\neyro\backend"
python -m pip install -r launcher\requirements_ui.txt
```

Запуск:

```powershell
python launcher\launcher_qt.py
```

## 2) Запуск через универсальный `launcher.bat`

Этот файл сам выберет UI:
- если есть PySide6 → откроет Qt-лаунчер
- если нет → откроет Tkinter-панель

```powershell
cd "C:\Users\SKYNET\OneDrive\Рабочий стол\neyro\backend"
.\launcher.bat
```

## 3) Создать ярлык на рабочем столе

```powershell
cd "C:\Users\SKYNET\OneDrive\Рабочий стол\neyro\backend"
powershell -ExecutionPolicy Bypass -File .\create_launcher_shortcut.ps1
```

Потом ты сможешь заменить иконку на свой логотип.

## 4) Авто-обнаружение программ

Теперь при фразах вида:
- `открой discord`
- `открой steam`
- `запусти obs`

Мальтруант пробует найти программу через:
- PATH
- Windows Registry: App Paths

Если приложение не находится, скажи его точное общепринятое имя (как exe), например `notepad`, `chrome`, `calc`.


