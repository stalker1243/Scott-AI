### Сделать лаунчер полноценной программой (без терминала)

Да, можно: собираем **GUI-приложение (.exe)**, которое запускается без консоли.

## 1) Установить зависимости

```powershell
cd "C:\Users\SKYNET\OneDrive\Рабочий стол\neyro\backend"
python -m pip install -r launcher\requirements_ui.txt
python -m pip install pyinstaller
```

## 2) Собрать exe (без окна терминала)

```powershell
cd "C:\Users\SKYNET\OneDrive\Рабочий стол\neyro\backend"
pyinstaller --noconsole --onefile --name "ScottLauncher" launcher\launcher_qt.py
```

Готовый файл будет здесь:
- `backend\dist\ScottLauncher.exe`

## 3) Иконка для exe и ярлыка

- Положи картинку в `backend\assets\logo.png`
- Сделай ico:

```powershell
python -m pip install Pillow
python make_ico.py assets\logo.png assets\maltruand.ico
```

Чтобы собрать exe сразу с иконкой:

```powershell
pyinstaller --noconsole --onefile --icon assets\maltruand.ico --name "ScottLauncher" launcher\launcher_qt.py
```

## 4) Создать ярлык на рабочем столе

```powershell
powershell -ExecutionPolicy Bypass -File .\create_launcher_shortcut.ps1 -LauncherBat "C:\Users\SKYNET\OneDrive\Рабочий стол\neyro\backend\launcher.bat" -ShortcutName "Scott Launcher"
```


