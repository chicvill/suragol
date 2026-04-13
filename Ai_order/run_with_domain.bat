@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"

REM 1. Check for Virtual Environment
if exist ".venv" goto VENV_EXISTS

echo [Info] Virtual environment (.venv) not found. Creating...
python -m venv .venv
if errorlevel 1 (
    echo [Error] Failed to create VENV. Please check if Python is installed.
    pause
    exit /b 1
)

echo [Info] Installing requirements...
".venv\Scripts\python.exe" -m pip install --upgrade pip
".venv\Scripts\pip.exe" install -r requirements.txt

:VENV_EXISTS
set "PYTHON_PATH=.venv\Scripts\python.exe"

REM 2. Verify Python Path
if exist "%PYTHON_PATH%" goto START_SERVER

echo [Warning] Venv python not found, trying system python...
set "PYTHON_PATH=python"

:START_SERVER
echo.
echo [Info] Starting Server with Domain connection...
"%PYTHON_PATH%" run_domain.py

if errorlevel 1 (
    echo [Error] Server failed to start.
    pause
)
pause
