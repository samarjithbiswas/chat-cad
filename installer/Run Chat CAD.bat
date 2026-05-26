@echo off
REM Launch Chat CAD. Created by install.ps1.
REM Activates the private chatcad env and starts the Flask server,
REM which then auto-opens a browser tab at http://127.0.0.1:5000/.

title Chat CAD
set "MINIFORGE=%USERPROFILE%\miniforge-chatcad"
set "ENVPY=%MINIFORGE%\envs\chatcad\python.exe"
set "APPDIR=%~dp0.."

if not exist "%ENVPY%" (
    echo Chat CAD is not installed yet.
    echo Double-click "Install Chat CAD.bat" first, then try again.
    pause
    exit /b 1
)

cd /d "%APPDIR%"
"%ENVPY%" app.py

if errorlevel 1 (
    echo.
    echo Chat CAD exited with an error. Scroll up for details.
    pause
)
