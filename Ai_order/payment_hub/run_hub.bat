@echo off
cd /d "%~dp0"

echo [Info] Checking Python...
set PY="C:\Users\USER\AppData\Local\Programs\Python\Python313\python.exe"

if not exist .venv (
    echo [Info] Creating VENV...
    %PY% -m venv .venv
)

echo [Info] Installing requirements...
.venv\Scripts\python.exe -m pip install -r requirements.txt

echo [Info] Running Database Migration...
.venv\Scripts\python.exe update_db_schema.py

echo [Info] Running Payment Hub Server...
.venv\Scripts\python.exe server.py

pause
