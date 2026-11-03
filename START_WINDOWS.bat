@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\pythonw.exe" (
 echo Installing TWYS desktop requirements. This is required only once.
 py -3 -m venv .venv || exit /b 1
 ".venv\Scripts\python.exe" -m pip install -r requirements-desktop.txt || exit /b 1
)
start "TWYS Terminal" ".venv\Scripts\pythonw.exe" "%~dp0twys_desktop.py"
