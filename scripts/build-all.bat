@echo off
setlocal

echo === Building Rmo-AI Desktop ===

set ROOT=%~dp0..

:: 国内网络环境下加速 Electron 与 electron-builder 二进制下载
set ELECTRON_MIRROR=https://npmmirror.com/mirrors/electron/
set ELECTRON_BUILDER_BINARIES_MIRROR=https://npmmirror.com/mirrors/electron-builder-binaries/

echo [1/3] Building backend...
cd /d "%ROOT%\backend"
if exist "%ROOT%\backend\.venv-win\Scripts\activate.bat" (
    call "%ROOT%\backend\.venv-win\Scripts\activate.bat"
)
pip install pyinstaller
pyinstaller rom_ai.spec --clean --noconfirm
if %ERRORLEVEL% neq 0 (
    echo Backend build failed!
    exit /b %ERRORLEVEL%
)

echo [2/3] Building frontend...
cd /d "%ROOT%\frontend"
call npm run build
if %ERRORLEVEL% neq 0 (
    echo Frontend build failed!
    exit /b %ERRORLEVEL%
)

echo [3/3] Packaging with electron-builder...
cd /d "%ROOT%\desktop"
call npx electron-builder --win --publish never
if %ERRORLEVEL% neq 0 (
    echo Electron packaging failed!
    exit /b %ERRORLEVEL%
)

cd /d "%ROOT%"
echo === Build Complete ===
echo Output: %ROOT%\release\
