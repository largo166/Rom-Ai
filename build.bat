@echo off
setlocal
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\build-windows-exe.ps1" %*
exit /b %ERRORLEVEL%
