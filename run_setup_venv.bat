@echo off
setlocal
cd /d %~dp0

echo ===================================================
echo [WangGung] Virtual Environment REPAIR Mode
echo ===================================================

REM 1. Remove old venv
if exist .venv (
    echo [Info] Removing existing .venv folder...
    rmdir /s /q .venv
)

REM 2. Create new venv
echo [Info] Creating new .venv...
set PYTHON_CMD=python
python --version >nul 2>&1
if errorlevel 1 (
    set PYTHON_CMD=py
    py --version >nul 2>&1
    if errorlevel 1 (
        echo [ERROR] Python not found. Please install Python and add it to PATH.
        pause
        exit /b 1
    )
)

%PYTHON_CMD% -m venv .venv
if errorlevel 1 (
    echo [ERROR] Failed to create venv with %PYTHON_CMD%.
    pause
    exit /b 1
)

REM 3. Install packages
echo [Info] Installing requirements...
.venv\Scripts\python.exe -m pip install --upgrade pip
.venv\Scripts\pip.exe install --no-cache-dir -r requirements.txt

echo ===================================================
echo REPAIR COMPLETE! 
echo Please run 'run_with_domain.bat' now.
echo ===================================================
pause
