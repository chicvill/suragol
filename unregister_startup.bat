@echo off
echo =========================================
echo Removing Auto-Startup Task
echo =========================================
echo.

net session >nul 2>&1
if %errorLevel% neq 0 (
    echo [ERROR] Must run as Administrator!
    echo Please Right-Click this file and choose "Run as administrator".
    echo.
    pause
    exit /b
)

echo Deleting Task...
schtasks /delete /tn "WangGungOrderSystem" /f >nul 2>&1

if %errorLevel% == 0 (
    echo [SUCCESS] Auto-startup disabled successfully.
) else (
    echo [INFO] Task not found or already deleted.
)

echo.
pause
