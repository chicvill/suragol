@echo off
chcp 65001 >nul
setlocal
cd /d %~dp0

echo ===================================================
echo [WangGung] Setting up Virtual Environment...
echo ===================================================

:: 1. Create venv if not exist
if not exist .venv (
    echo [Info] Creating new .venv...
    python -m venv .venv
)

:: 2. Check if venv creation succeeded
if not exist .venv\Scripts\python.exe (
    echo [ERROR] Failed to create .venv! 
    echo Please make sure Python is installed and added to PATH.
    pause
    exit /b
)

:: 3. Install/Upgrade packages
echo [Info] Installing requirements...
.venv\Scripts\python -m pip install --upgrade pip
.venv\Scripts\pip install -r requirements.txt

echo.
echo ===================================================
echo Setup Complete! 
echo Please run 'run.bat' to start the server.
echo ===================================================
pause
