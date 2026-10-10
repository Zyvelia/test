@echo off
setlocal EnableExtensions DisableDelayedExpansion
chcp 65001 >nul

echo ========================================
echo   Upload Project Files to GitHub
echo ========================================
echo.
where git >nul 2>&1
if errorlevel 1 (
  echo ERROR: Git is not installed or not in PATH.
  pause
  exit /b 1
)

REM Use the folder this .bat file is in as the project folder.
REM This assumes send_to_github-upload-fixed.bat is inside the Git repository.
set "PROJECT=%~dp0"
cd /d "%PROJECT%" || goto :error

echo.
echo Project folder (script location): %CD%
if not exist ".git" if not exist ".git\" (
  echo ERROR: This folder is not a Git repository (.git was not found).
  echo Open the actual cloned repository folder and run this script again.
  goto :error
)

set "BRANCH="
for /f "delims=" %%B in ('git branch --show-current 2^>nul') do set "BRANCH=%%B"
if not defined BRANCH (
  echo ERROR: No current branch found. Create or check out a branch first.
  goto :error
)

echo.
echo Current branch: %BRANCH%
set "REMOTE="
for /f "delims=" %%R in ('git remote get-url origin 2^>nul') do set "REMOTE=%%R"
if not defined REMOTE (
  echo ERROR: No remote named origin is configured.
  echo Configure it with: git remote add origin https://github.com/OWNER/REPOSITORY.git
  goto :error
)
echo Remote: %REMOTE%
echo.
echo Current status:
git status --short

echo.
set "MSG="
set /p "MSG=Commit message (Enter for 'Update project files'): "
if not defined MSG set "MSG=Update project files"

echo.
echo Staging project files...
git add -A
if errorlevel 1 goto :error

git diff --cached --quiet
if errorlevel 1 goto :make_commit
echo No new file changes to commit. Existing local commits can still be pushed.
goto :choose_mode

:make_commit
echo Creating commit...
git commit -m "%MSG%"
if errorlevel 1 goto :error

:choose_mode
echo.
echo Choose how to push to GitHub:
echo   1. Normal push - does not overwrite remote history
echo   2. Fetch and rebase remote changes, then push (recommended if both sides changed)
echo   3. Force push with lease - replaces remote branch history if needed
echo.
set "MODE="
set /p "MODE=Choose 1, 2, or 3: "
if "%MODE%"=="1" goto :normal_push
if "%MODE%"=="2" goto :rebase_push
if "%MODE%"=="3" goto :force_push
echo Invalid choice.
goto :error

:normal_push
echo.
echo Pushing branch %BRANCH%...
git push -u origin "%BRANCH%"
if errorlevel 1 goto :push_failed
goto :success

:rebase_push
echo.
echo Fetching remote branch...
git fetch origin
if errorlevel 1 goto :error
git show-ref --verify --quiet "refs/remotes/origin/%BRANCH%"
if errorlevel 1 (
  echo Remote branch does not exist yet; pushing the local branch.
  git push -u origin "%BRANCH%"
  if errorlevel 1 goto :push_failed
  goto :success
)
echo Rebasing local commits onto origin/%BRANCH%...
git pull --rebase origin "%BRANCH%"
if errorlevel 1 (
  echo.
  echo Rebase stopped, likely due to merge conflicts.
  echo Resolve conflicts, then run: git rebase --continue
  echo To cancel the rebase, run: git rebase --abort
  goto :error
)
git push -u origin "%BRANCH%"
if errorlevel 1 goto :push_failed
goto :success

:force_push
echo.
echo WARNING: This can replace commits currently on GitHub that are not in your local branch.
set "CONFIRM="
set /p "CONFIRM=Type FORCE to continue: "
if /i not "%CONFIRM%"=="FORCE" (
  echo Force push cancelled.
  pause
  exit /b 1
)
echo Fetching remote state for safety check...
git fetch origin
if errorlevel 1 goto :error
echo Force-pushing local branch %BRANCH%...
git push --force-with-lease -u origin "%BRANCH%"
if errorlevel 1 goto :push_failed
goto :success

:push_failed
echo.
echo Push failed. Check the Git error above.
echo If remote has work you want to keep, choose option 2 next time.
echo Only use option 3 if you intend to replace the GitHub branch history.
goto :error

:success
echo.
echo ========================================
echo   Push completed successfully.
echo ========================================
pause
exit /b 0

:error
echo.
echo ========================================
echo   Upload failed - review the message above.
echo ========================================
pause
exit /b 1
