@echo off
setlocal

echo Building Rmo-AI Backend...

pyinstaller rom_ai.spec --clean

if %ERRORLEVEL% neq 0 (
    echo Backend build failed!
    exit /b %ERRORLEVEL%
)

echo Done! Output in backend\dist\rmo-ai-backend\
