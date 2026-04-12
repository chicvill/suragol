@echo off

echo ========================================================
echo  [Wang-gung] Local PC Test Mode
echo ========================================================
echo.
echo  * This mode DOES NOT start Cloudflare Tunnel.
echo  * Safe to test on PC without disrupting Pad server.
echo.
echo  [Local URLs]
echo   - Counter:  http://localhost:10000/counter
echo   - Customer: http://localhost:10000/customer/3
echo   - Waiting:  http://localhost:10000/waiting
echo.
echo ========================================================
echo Starting server... (Close this window to stop)

if not exist ".venv\Scripts\python.exe" (
    echo [ERROR] Cannot find .venv Python. Please check the setup.
    pause
    exit /b 1
)

set PORT=10000
set FLASK_DEBUG=1
.\.venv\Scripts\python.exe app.py
pause
