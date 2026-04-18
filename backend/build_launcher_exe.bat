@echo off
setlocal

REM One-click build for Scott Qt launcher (GUI .exe without console)

cd /d "%~dp0"

echo =========================================
echo  Scott Launcher - EXE builder
echo =========================================
echo.

REM 1. Install UI deps (PySide6) if needed
echo [INFO] Installing UI requirements (PySide6) if missing...
python -m pip install --disable-pip-version-check -r launcher\requirements_ui.txt
if errorlevel 1 (
  echo [ERROR] Failed to install UI requirements.
  goto :end
)

REM 2. Install PyInstaller
echo [INFO] Installing PyInstaller...
python -m pip install --disable-pip-version-check pyinstaller
if errorlevel 1 (
  echo [ERROR] Failed to install PyInstaller.
  goto :end
)

REM 3. Optional icon
set ICO_ARG=
set ICO_PATH=assets\maltruand.ico
if exist "%ICO_PATH%" (
  echo [INFO] Using icon: %ICO_PATH%
  set ICO_ARG=--icon "%ICO_PATH%"
) else (
  echo [INFO] Icon not found at %ICO_PATH% ^(optional^). Build will use default icon.
)

REM 4. Build
echo [INFO] Building EXE...
pyinstaller --noconsole --onefile %ICO_ARG% --name "ScottLauncher" launcher\launcher_qt.py
if errorlevel 1 (
  echo [ERROR] PyInstaller build failed.
  goto :end
)

echo.
echo ✅ Build complete!
echo EXE: %cd%\dist\ScottLauncher.exe
echo.
echo [INFO] Creating Desktop + Start Menu shortcuts...
powershell -ExecutionPolicy Bypass -File ".\create_launcher_shortcut.ps1" -LauncherBat "%cd%\dist\ScottLauncher.exe" -ShortcutName "Scott"
if errorlevel 1 (
  echo [WARN] Shortcut creation failed. You can retry with:
  echo   install_launcher_shortcuts.bat
)
echo.
echo You can run shortcuts setup anytime via:
echo   install_launcher_shortcuts.bat
echo.

:end
endlocal


