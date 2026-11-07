@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Run setup.bat first.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" -m vivi.updater %*
set "vivi_update_exit=%errorlevel%"
pause
exit /b %vivi_update_exit%
