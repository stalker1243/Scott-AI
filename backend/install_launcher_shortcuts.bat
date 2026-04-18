@echo off
setlocal
cd /d "%~dp0"

echo =========================================
echo  Scott Launcher - Shortcut Installer
echo =========================================
echo.

set "TARGET=%cd%\launcher.bat"
if exist "%cd%\dist\ScottLauncher.exe" (
  set "TARGET=%cd%\dist\ScottLauncher.exe"
)

echo [INFO] Shortcut target: %TARGET%
powershell -ExecutionPolicy Bypass -File ".\create_launcher_shortcut.ps1" -LauncherBat "%TARGET%" -ShortcutName "Scott"
if errorlevel 1 (
  echo [ERROR] Failed to create shortcuts.
  goto :end
)

echo.
echo [OK] Shortcuts created on Desktop and Start Menu.
echo [TIP] Launch "Scott" from desktop shortcut or Start menu.

:end
endlocal
