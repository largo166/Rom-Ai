@echo off
setlocal
cd /d "%~dp0"

if not exist "backend\dist\rmo-ai-backend\rmo-ai-backend.exe" (
  echo Backend executable not found. Please run backend packaging first.
  pause
  exit /b 1
)

if not exist "frontend\dist\index.html" (
  echo Frontend build not found. Please run npm run build in frontend first.
  pause
  exit /b 1
)

if not exist "logs" mkdir "logs"

echo Starting ROM-AI backend at http://127.0.0.1:8000 ...
start "ROM-AI Backend" /min cmd /c "backend\dist\rmo-ai-backend\rmo-ai-backend.exe > logs\backend-local.log 2> logs\backend-local-error.log"

echo Starting ROM-AI frontend at http://127.0.0.1:5175 ...
where py >nul 2>nul
if %errorlevel%==0 (
  start "ROM-AI Frontend" /min py serve-frontend.py
) else (
  start "ROM-AI Frontend" /min python serve-frontend.py
)

echo.
echo ROM-AI local run mode is starting.
echo Open: http://127.0.0.1:5175
echo Health: http://127.0.0.1:8000/api/health
echo.
pause
