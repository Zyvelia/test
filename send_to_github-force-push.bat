@echo off
setlocal EnableExtensions DisableDelayedExpansion
cd /d "%~dp0"

where git >nul 2>&1
if errorlevel 1 (
  echo ERROR: Git is not installed or is not in PATH.
  pause
  exit /b 1
)

echo ========================================
echo   CharChat - Send to GitHub
echo ========================================
echo.
echo Project folder: %CD%
echo.

set "REMOTE="
for /f "delims=" %%R in ('git remote get-url origin 2^>nul') do set "REMOTE=%%R"

if not defined REMOTE (
  set /p "REMOTE=Paste your GitHub repository URL: "
  if not defined REMOTE (
    echo ERROR: No repository URL was provided.
    pause
    exit /b 1
  )
  git remote add origin "%REMOTE%"
  if errorlevel 1 goto :error
)

echo Remote: %REMOTE%
echo Checking GitHub access...
git ls-remote --heads origin >nul 2>&1
if errorlevel 1 (
  echo ERROR: Git cannot access the remote. Check URL and authentication.
  echo You can test authentication with: gh auth login
  pause
  exit /b 1
)
echo Remote access OK.
echo.

REM Test status explicitly; a valid-looking HEAD can still have broken repository metadata.
git status --short > "%TEMP%\charchat_git_status_test.txt" 2>&1
if errorlevel 1 goto :repair_repo
type "%TEMP%\charchat_git_status_test.txt"
del "%TEMP%\charchat_git_status_test.txt" >nul 2>&1
goto :repo_ok

:repair_repo
echo.
echo ERROR: Git status failed. The local .git metadata is damaged.
echo This repair keeps your project files in place and backs up the old .git folder.
echo It will rebuild Git metadata using the existing GitHub remote.
echo.
type "%TEMP%\charchat_git_status_test.txt"
del "%TEMP%\charchat_git_status_test.txt" >nul 2>&1
echo.
set "CONFIRM="
set /p "CONFIRM=Type REPAIR to continue, or press Enter to stop: "
if /i not "%CONFIRM%"=="REPAIR" (
  echo Repair cancelled. No repair changes were made.
  pause
  exit /b 1
)

if not exist ".git" (
  echo ERROR: .git folder was not found, so automatic metadata backup is unavailable.
  goto :error
)

set "BACKUP=.git_backup_before_rebuild"
if exist "%BACKUP%" (
  echo ERROR: "%BACKUP%" already exists.
  echo Rename or move it after checking its contents, then rerun this script.
  goto :error
)

echo Backing up the damaged .git folder to "%BACKUP%"...
move ".git" "%BACKUP%" >nul
if errorlevel 1 (
  echo ERROR: Could not back up .git.
  goto :error
)

echo Initializing fresh Git metadata...
git init -b main
if errorlevel 1 (
  echo ERROR: git init failed. Original metadata is in "%BACKUP%".
  goto :error
)

git remote add origin "%REMOTE%"
if errorlevel 1 (
  echo ERROR: Could not add origin. Original metadata is in "%BACKUP%".
  goto :error
)

echo Fetching remote branches...
git fetch origin
if errorlevel 1 (
  echo ERROR: Fetch failed. Original metadata is in "%BACKUP%".
  goto :error
)

git show-ref --verify --quiet refs/remotes/origin/main
if not errorlevel 1 (
  set "BRANCH=main"
  goto :reset_from_remote
)
git show-ref --verify --quiet refs/remotes/origin/master
if not errorlevel 1 (
  set "BRANCH=master"
  goto :reset_from_remote
)

echo ERROR: Neither origin/main nor origin/master exists.
echo Your project files are untouched; old metadata is in "%BACKUP%".
echo Check the branch name on GitHub before continuing.
goto :error

:reset_from_remote
echo Rebuilding local branch from origin/%BRANCH% without overwriting project files...
git reset --mixed "origin/%BRANCH%"
if errorlevel 1 (
  echo ERROR: Reset failed. Original metadata is in "%BACKUP%".
  goto :error
)
git branch -M "%BRANCH%"
if errorlevel 1 (
  echo ERROR: Could not set the local branch name. Original metadata is in "%BACKUP%".
  goto :error
)

echo.
echo Git metadata repaired. Existing project files remain in place.
echo Original metadata backup: %CD%\%BACKUP%
echo.

:repo_ok
set "BRANCH="
for /f "delims=" %%B in ('git branch --show-current 2^>nul') do set "BRANCH=%%B"
if not defined BRANCH set "BRANCH=main"

echo Current branch: %BRANCH%
echo.
git status --short
if errorlevel 1 (
  echo ERROR: Git status still fails after recovery.
  echo Do not delete the backup folder. Keep it for manual recovery.
  goto :error
)

echo.
set "MSG="
set /p "MSG=Commit message (press Enter for 'Update CharChat iOS'): "
if not defined MSG set "MSG=Update CharChat iOS"

echo.
echo Staging changes...
git add -A
if errorlevel 1 goto :error

git diff --cached --quiet
if not errorlevel 1 (
  echo No changes to commit; nothing was pushed.
  pause
  exit /b 0
)

echo Creating commit...
git commit -m "%MSG%"
if errorlevel 1 goto :error

echo.
echo Pushing to GitHub...
git push -u origin "%BRANCH%"
if errorlevel 1 (
  echo.
  echo Push failed. If Git reports that the remote contains work you do not have,
  echo do not force-push; fetch/pull the remote branch first.
  goto :error
)

echo.
echo ========================================
echo   Successfully pushed to GitHub.
echo ========================================
pause
exit /b 0

:error
echo.
echo ========================================
echo   GitHub upload failed.
echo ========================================
echo Review the error above. Do not delete any .git backup folder.
pause
exit /b 1
