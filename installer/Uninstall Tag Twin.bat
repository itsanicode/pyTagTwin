@echo off
title Tag Twin - Uninstall
if not exist "%~dp0tagtwin-install.ps1" (
    echo.
    echo   "tagtwin-install.ps1" was not found next to this file, in:
    echo   %~dp0
    echo.
    pause
    exit /b 1
)
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0tagtwin-install.ps1" -Uninstall
echo.
pause
