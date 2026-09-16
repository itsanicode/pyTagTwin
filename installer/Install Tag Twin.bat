@echo off
title Tag Twin - Install
if not exist "%~dp0tagtwin-install.ps1" (
    echo.
    echo   The installer files are incomplete.
    echo.
    echo   "tagtwin-install.ps1" was not found next to this file, in:
    echo   %~dp0
    echo.
    echo   Please extract the ENTIRE Tag Twin zip first ^(right-click the zip
    echo   -^> Extract All...^), then run "Install Tag Twin.bat" from inside the
    echo   extracted folder. All package files must stay together.
    echo.
    pause
    exit /b 1
)
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0tagtwin-install.ps1"
echo.
pause
