@echo off
cd /d "%~dp0"
set "AUDITIA_BETA=1"
if exist "..\.venv\Scripts\python.exe" (
  "..\.venv\Scripts\python.exe" app.py
) else (
  py -3 app.py
)
pause
