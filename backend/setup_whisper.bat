@echo off
setlocal

echo =========================================
echo Scott - Whisper setup (Windows)
echo =========================================
echo.

REM Must be run from backend folder or will cd there from script location
cd /d "%~dp0"

where py >nul 2>nul
if errorlevel 1 (
  echo [ERROR] Python Launcher "py" not found.
  echo Install Python 3.11 and enable the Python Launcher.
  echo See: SETUP_WHISPER.md
  exit /b 1
)

REM Check if Python 3.11 exists
py -3.11 -c "import sys; print(sys.version)" >nul 2>nul
if errorlevel 1 (
  echo [ERROR] Python 3.11 is not installed.
  echo Please install Python 3.11 x64, then run this script again.
  echo See: SETUP_WHISPER.md
  exit /b 1
)

if not exist ".venv" (
  echo [INFO] Creating venv: .venv (Python 3.11)...
  py -3.11 -m venv .venv
  if errorlevel 1 exit /b 1
)

echo [INFO] Activating venv...
call ".venv\Scripts\activate.bat"
if errorlevel 1 exit /b 1

echo [INFO] Upgrading pip...
python -m pip install --upgrade pip
if errorlevel 1 exit /b 1

echo [INFO] Installing requirements (includes openai-whisper)...
python -m pip install -r requirements.txt
if errorlevel 1 exit /b 1

echo [INFO] Verifying whisper import...
python -c "import whisper; print('Whisper OK')"
if errorlevel 1 exit /b 1

echo.
echo ✅ Whisper installed successfully.
echo You can now run:
echo   .venv\Scripts\activate
echo   python voice_assistant_daemon.py
echo.
endlocal


