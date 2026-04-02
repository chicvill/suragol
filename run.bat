@echo off
chcp 65001 >nul
setlocal
cd /d %~dp0

echo ==========================================
echo   WangGung Restaurant Server Starting...
echo ==========================================

if not exist .venv (
    echo [ERROR] .venv not found. Please run setup_venv.bat first.
    pause
    exit /b
)

echo [Info] Activating Virtual Environment...
set "PYTHONPATH=%cd%"
.venv\Scripts\python app.py

pause
