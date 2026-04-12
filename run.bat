@echo off
setlocal enabledelayedexpansion
cd /d %~dp0

:MENU
cls
echo ===================================================
echo   [MQnet] Unified Server Manager
echo ===================================================
echo  1. Local Test Mode (Port 10000, Debug ON)
echo  2. Domain Connection (External Access, run_domain.py)
echo  3. Normal Server Run (Standard Environment)
echo  4. VENV Setup/Repair (Recreate .venv ^& Install)
echo  0. Exit
echo ===================================================
set /p choice="Enter choice (0-4): "

if "%choice%"=="1" goto LOCAL_RUN
if "%choice%"=="2" goto DOMAIN_RUN
if "%choice%"=="3" goto NORMAL_RUN
if "%choice%"=="4" goto SETUP_VENV
if "%choice%"=="0" exit
goto MENU

:LOCAL_RUN
echo [Info] Preparing Local Test Mode...
call :CHECK_VENV
if errorlevel 1 pause & goto MENU
echo.
echo  [Local URLs]
echo   - Counter:  http://localhost:10000/counter
echo   - Customer: http://localhost:10000/customer/3
echo   - Waiting:  http://localhost:10000/waiting
echo.
set PORT=10000
set FLASK_DEBUG=1
.venv\Scripts\python.exe app.py
pause
goto MENU

:DOMAIN_RUN
echo [Info] Starting Domain Connection Mode...
call :CHECK_VENV
if errorlevel 1 pause & goto MENU
.venv\Scripts\python.exe run_domain.py
pause
goto MENU

:NORMAL_RUN
echo [Info] Starting Normal Server Mode...
call :CHECK_VENV
if errorlevel 1 pause & goto MENU
.venv\Scripts\python.exe app.py
pause
goto MENU

:SETUP_VENV
echo ===================================================
echo [MQnet] VENV Setup and Repair Mode
echo ===================================================
if exist .venv (
    echo [Info] Removing existing .venv folder...
    rmdir /s /q .venv
)

echo [Info] Checking Python...
set PYTHON_CMD=python
python --version >nul 2>&1
if errorlevel 1 (
    set PYTHON_CMD=py
    py --version >nul 2>&1
    if errorlevel 1 (
        echo [ERROR] Python not found. Please install Python.
        pause
        goto MENU
    )
)

echo [Info] Creating VENV using %PYTHON_CMD%...
%PYTHON_CMD% -m venv .venv
if errorlevel 1 (
    echo [ERROR] Failed to create VENV.
    pause
    goto MENU
)

echo [Info] Installing packages...
.venv\Scripts\python.exe -m pip install --upgrade pip
.venv\Scripts\pip.exe install --no-cache-dir -r requirements.txt

echo ===================================================
echo Setup Complete!
echo ===================================================
pause
goto MENU

:CHECK_VENV
if not exist ".venv\Scripts\python.exe" (
    echo [ERROR] Virtual environment is missing or corrupted.
    echo         Please run option 4 first.
    exit /b 1
)
exit /b 0
