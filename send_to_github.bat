@echo off
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"

where git >nul 2>&1
if errorlevel 1 (
  echo.
  echo ERROR: Git is not installed or is not in PATH.
  echo Install Git for Windows, then run this file again.
  pause
  exit /b 1
)

echo ========================================
echo   CharChat - Send to GitHub
echo ========================================
echo.

if not exist ".git" (
  echo No Git repository found. Initializing one...
  git init
  if errorlevel 1 goto :error
)

for /f "delims=" %%R in ('git remote get-url origin 2^>nul') do set "REMOTE=%%R"
if not defined REMOTE (
  echo No GitHub remote named "origin" is configured.
  echo.
  set /p "REMOTE=Paste your GitHub repository URL: "
  if not defined REMOTE (
    echo ERROR: No repository URL was entered.
    pause
    exit /b 1
  )
  git remote add origin "!REMOTE!"
  if errorlevel 1 goto :error
)

echo Remote: !REMOTE!
echo.

for /f "delims=" %%B in ('git branch --show-current 2^>nul') do set "BRANCH=%%B"
if not defined BRANCH set "BRANCH=main"

if /i not "!BRANCH!"=="main" if /i not "!BRANCH!"=="master" (
  echo Current branch: !BRANCH!
) else (
  echo Current branch: !BRANCH!
)

echo.
echo Checking GitHub authentication...
git ls-remote origin HEAD >nul 2>&1
if errorlevel 1 (
  echo.
  echo Git could not authenticate to the GitHub repository.
  echo If this is your first push, configure GitHub authentication/credentials.
  echo GitHub CLI users can run: gh auth login
  echo.
  pause
  exit /b 1
)

echo Authentication/remote check OK.
echo.

git status --short

echo.
set "MSG="
set /p "MSG=Commit message (press Enter for 'Update CharChat iOS'): "
if not defined MSG set "MSG=Update CharChat iOS"

echo.
echo Staging changes...
git add -A
if errorlevel 1 goto :error

REM Do not create an empty commit when nothing changed.
git diff --cached --quiet
if not errorlevel 1 (
  echo No changes to commit.
  echo.
  echo Nothing was pushed.
  pause
  exit /b 0
)

echo Creating commit...
git commit -m "!MSG!"
if errorlevel 1 goto :error

echo.
echo Pushing to GitHub...
git push -u origin "!BRANCH!"
if errorlevel 1 goto :error

echo.
echo ========================================
echo   Successfully pushed to GitHub.
echo ========================================
echo.
pause
exit /b 0

:error
echo.
echo ========================================
echo   GitHub upload failed.
echo ========================================
echo Check the error above.
echo.
pause
exit /b 1
