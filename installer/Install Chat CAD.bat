@echo off
REM First-time setup. Double-click this file.
REM It calls the PowerShell installer with execution policy bypass so users
REM don't have to fiddle with Set-ExecutionPolicy.

title Chat CAD - Installer
echo.
echo Chat CAD installer
echo ------------------
echo This will install Miniforge (~100 MB), then cadquery + OpenCascade
echo (~1.5 GB) into a private env under %%USERPROFILE%%\miniforge-chatcad.
echo Nothing is installed system-wide. Re-run safely to upgrade.
echo.
pause

powershell -ExecutionPolicy Bypass -NoProfile -File "%~dp0install.ps1"

if errorlevel 1 (
    echo.
    echo Install failed. Scroll up for the error message.
    pause
    exit /b 1
)

echo.
pause
