@echo off
setlocal

REM Scott Launcher entrypoint (runs the Qt launcher if installed, else falls back to tkinter panel)
cd /d "%~dp0"

set "PYTHONW=%LocalAppData%\Programs\Python\Python311\pythonw.exe"
if not exist "%PYTHONW%" set "PYTHONW=pythonw"

REM Prefer Qt launcher if PySide6 is installed
python -c "import PySide6" >nul 2>nul
if %errorlevel%==0 (
  start "" "%PYTHONW%" launcher\launcher_qt.py
  exit /b %errorlevel%
)

REM Fallback: built-in tkinter control panel
start "" "%PYTHONW%" control_panel.py
endlocal


