@echo off
setlocal
chcp 65001 >nul

echo ===================================================
echo  [MQnet] Seeding Demo Data...
echo ===================================================

set VENV_PATH=%~dp0.venv\Scripts\python.exe

if not exist "%VENV_PATH%" (
    echo [ERROR] Virtual environment not found at: %VENV_PATH%
    echo Please run setup_venv.bat first.
    pause
    exit /b 1
)

echo [Info] Running seed script...
"%VENV_PATH%" "%~dp0scratch\seed_demo_data.py"

if %ERRORLEVEL% equ 0 (
    echo.
    echo ===================================================
    echo  SUCCESS: Demo data has been generated.
    echo  Please refresh your stats dashboard!
    echo ===================================================
) else (
    echo.
    echo [ERROR] Data seeding failed with error code %ERRORLEVEL%.
)

pause
endlocal
