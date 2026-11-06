@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\pythonw.exe" (
  echo Run setup.bat first.
  pause
  exit /b 1
)
start "Vivi tray" ".venv\Scripts\pythonw.exe" -m vivi.tray
