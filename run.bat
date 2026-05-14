@echo off
title Universal Translator - DEV

:: Kill any already-running instance (installed or dev)
taskkill /F /FI "IMAGENAME eq pythonw.exe" /FI "WINDOWTITLE eq Universal Translator*" >nul 2>&1

:: Give it a moment to release the mutex
timeout /t 1 /nobreak >nul

:: Always run from the project root (this file's location)
cd /d "%~dp0"

echo Starting Universal Translator from project source...
echo Source: %CD%
echo.

:: Start hidden (no console window)
start "" pythonw "%~dp0main.py"

echo Launched. Check the system tray.
timeout /t 2 /nobreak >nul
