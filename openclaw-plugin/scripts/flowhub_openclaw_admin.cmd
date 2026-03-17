@echo off
setlocal

set "SCRIPT_DIR=%~dp0"
set "PY_SCRIPT=%SCRIPT_DIR%flowhub_openclaw_admin.py"

python -V >nul 2>nul
if %ERRORLEVEL%==0 (
  python "%PY_SCRIPT%" %*
  exit /b %ERRORLEVEL%
)

py -3 -V >nul 2>nul
if %ERRORLEVEL%==0 (
  py -3 "%PY_SCRIPT%" %*
  exit /b %ERRORLEVEL%
)

python3 -V >nul 2>nul
if %ERRORLEVEL%==0 (
  python3 "%PY_SCRIPT%" %*
  exit /b %ERRORLEVEL%
)

echo Python launcher not found. Install Python or run flowhub_openclaw_admin.py directly.
exit /b 1
