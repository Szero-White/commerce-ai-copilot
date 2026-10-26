@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo [ERROR] Run run_windows.bat once to create the Python environment.
  pause
  exit /b 1
)
echo [1/2] Preparing local test requirements (free libraries)...
".venv\Scripts\python.exe" -m pip install -r requirements-dev.txt
if errorlevel 1 (echo [ERROR] Could not install test dependencies. & pause & exit /b 1)
echo [2/2] Automated tests + offline API acceptance...
".venv\Scripts\python.exe" -m pytest -q
if errorlevel 1 (echo [FAIL] Tests failed. & pause & exit /b 1)
".venv\Scripts\python.exe" -m scripts.portfolio_check
if errorlevel 1 (echo [FAIL] Offline acceptance failed. & pause & exit /b 1)
echo [PASS] Reports in reports\ . Live AI is NOT verified by this script.
pause
