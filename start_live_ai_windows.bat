@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo [ERROR] First run run_windows.bat to create .venv and install dependencies.
  pause
  exit /b 1
)
where ollama >nul 2>nul
if errorlevel 1 (
  echo [ERROR] Ollama is not installed or not on PATH. Read README section 3.
  pause
  exit /b 1
)
set "LLM_PROVIDER=ollama"
set "EMBEDDING_PROVIDER=ollama"
set "OLLAMA_MODEL=qwen2.5:1.5b"
set "EMBEDDING_MODEL=bge-m3"
set "OLLAMA_URL=http://127.0.0.1:11434"
echo [1/3] Building vector index for %EMBEDDING_MODEL%...
".venv\Scripts\python.exe" -m scripts.index_embeddings
if errorlevel 1 (
  echo [ERROR] Embedding index failed. Check that Ollama is running and bge-m3 is downloaded.
  pause
  exit /b 1
)
echo [2/3] Live generative-RAG smoke evaluation...
".venv\Scripts\python.exe" -m scripts.verify_live_rag
if errorlevel 1 (
  echo [WARNING] One or more live checks failed. Read reports\live_rag_report.json.
  echo No claims about live RAG should be added to your CV yet.
  pause
  exit /b 1
)
echo [3/3] Starting live AI at http://127.0.0.1:8000
start "" /min cmd /c "timeout /t 3 /nobreak >nul & start http://127.0.0.1:8000"
".venv\Scripts\python.exe" -m uvicorn app.main:app --host 127.0.0.1 --port 8000
pause
