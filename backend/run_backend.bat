@echo off
REM Scott AI Backend Server

echo.
echo ╔════════════════════════════════════════════════════════╗
echo ║   🤖 SCOTT AI - BACKEND SERVER 🤖                     ║
echo ║                                                        ║
echo ║   Доступ: http://localhost:8000                       ║
echo ║   WebSocket: ws://localhost:8000/ws/chat              ║
echo ║   Docs: http://localhost:8000/docs                    ║
echo ╚════════════════════════════════════════════════════════╝
echo.

REM Активировать venv если существует
if exist "..\venv" (
    call ..\venv\Scripts\activate.bat
)

REM Запустить backend
python main.py
