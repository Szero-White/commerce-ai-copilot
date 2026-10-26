@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo =================================================
echo  COMMERCE AI COPILOT v2 - LOCAL DEMO
echo =================================================
where py >nul 2>nul
if %errorlevel%==0 (set "PYCMD=py -3") else (set "PYCMD=python")
if not exist ".venv\Scripts\python.exe" (
 echo [1/3] Creating Python environment...
 %PYCMD% -m venv .venv
 if errorlevel 1 (echo Cannot create venv. Please install Python 3.10+ & pause & exit /b 1)
)
echo [2/3] Installing dependencies...
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 (echo Package installation failed. Check internet connection. & pause & exit /b 1)
echo [3/3] Starting at http://127.0.0.1:8000
start "" /min cmd /c "timeout /t 3 /nobreak >nul & start http://127.0.0.1:8000"
".venv\Scripts\python.exe" -m uvicorn app.main:app --host 127.0.0.1 --port 8000
pause
