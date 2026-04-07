@echo off
cd /d "%~dp0"
set PYTHON_PATH=.venv\Scripts\python.exe
if NOT exist %PYTHON_PATH% set PYTHON_PATH=python
%PYTHON_PATH% run_domain.py
pause
