@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo [ERROR] Run run_windows.bat once first to install Python environment.
  pause
  exit /b 1
)
echo Running automated tests (offline, no Ollama required)...
".venv\Scripts\python.exe" -m pip install -r requirements-dev.txt
if errorlevel 1 (
  echo Failed to install test dependencies.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" -m pytest -q
if errorlevel 1 (
  echo [FAIL] Some tests failed; copy the terminal output.
  pause
  exit /b 1
)
echo [OK] Automated tests passed. These are NOT real LLM inference tests.
pause
