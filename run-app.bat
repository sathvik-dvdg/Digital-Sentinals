@echo off
setlocal enabledelayedexpansion

echo.
echo  =========================================
echo       PII SHIELD MVP - STARTUP SCRIPT
echo  =========================================
echo.

:: Check for Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python not found. Please install Python 3.9+.
    pause
    exit /b
)

:: Check for Node
node --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Node.js not found. Please install Node.js.
    pause
    exit /b
)

echo [1/3] Starting Backend (FastAPI)...
start "PII-Shield-Backend" cmd /k "cd backend && python -m venv .venv && call .venv\Scripts\activate && pip install -r requirements.txt && uvicorn main:app --reload --port 8000"

echo [2/3] Starting Frontend (Vite)...
start "PII-Shield-Frontend" cmd /k "cd frontend && npm install && npm run dev"

echo [3/3] Launching Browser...
timeout /t 5 /nobreak >nul
start http://localhost:5173

echo.
echo  -----------------------------------------
echo   SYSTEMS ONLINE
echo   - Backend: http://localhost:8000
echo   - Frontend: http://localhost:5173
echo.
echo   Press Ctrl+Shift+D in the app for MOCK MODE.
echo  -----------------------------------------
echo.
pause
