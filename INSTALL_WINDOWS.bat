@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0INSTALL_WINDOWS.ps1"
if errorlevel 1 (
 echo.
 echo Installation was not completed. Review the message above.
 pause
 exit /b 1
)
exit /b 0
