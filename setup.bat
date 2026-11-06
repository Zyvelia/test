@echo off
setlocal
cd /d "%~dp0"
py -3 --version >nul 2>&1
if errorlevel 1 (
  echo Install Python 3.11 or newer from https://www.python.org/downloads/windows/
  echo Include the Python launcher during installation, then run this again.
  pause
  exit /b 1
)
py -3 -c "import sys; sys.exit(0 if sys.version_info >= (3,11) else 1)"
if errorlevel 1 (
  echo Python 3.11 or newer is required.
  pause
  exit /b 1
)
if not exist ".venv\Scripts\python.exe" py -3 -m venv .venv
if not exist ".venv\Scripts\python.exe" goto failed
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto failed
if not exist ".env" copy /y ".env.example" ".env" >nul
echo Setup complete. Read README.md, add your bot token to .env, then run start.bat.
notepad ".env"
pause
exit /b 0
:failed
echo Setup failed. Read the error above and try again.
pause
exit /b 1
