@echo off
title Chat CAD - Uninstaller
echo.
echo This will remove:
echo   - %USERPROFILE%\miniforge-chatcad   (the private Python env, ~1.5 GB)
echo   - Chat CAD shortcuts from Desktop and Start Menu
echo.
echo The chat_cad folder (this folder) is NOT touched. Delete it manually
echo if you want to remove the source files too.
echo.
choice /M "Proceed"
if errorlevel 2 exit /b 0

echo Removing env...
rmdir /s /q "%USERPROFILE%\miniforge-chatcad" 2>nul

echo Removing shortcuts...
del "%USERPROFILE%\Desktop\Chat CAD.lnk" 2>nul
del "%APPDATA%\Microsoft\Windows\Start Menu\Programs\Chat CAD.lnk" 2>nul

echo Done.
pause
