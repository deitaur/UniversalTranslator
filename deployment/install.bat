@echo off
title Universal Translator v3.1 - Install from Source
echo ============================================
echo   Universal Translator v3.1
echo   Install from Source
echo ============================================
echo.

cd /d "%~dp0.."

:: ---- Check Python ----
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found in PATH.
    echo         Download from https://python.org
    echo         Check "Add Python to PATH" during install.
    pause
    exit /b 1
)
echo [OK] Python found.

:: ---- Install core dependencies ----
echo.
echo Installing core packages...
pip install pystray Pillow requests customtkinter --quiet
if errorlevel 1 (
    echo [WARN] Trying with --user flag...
    pip install pystray Pillow requests customtkinter --user --quiet
)
echo [OK] Core dependencies installed.

:: ---- Optional AI components ----
echo.
echo ============================================
echo   Optional AI Components
echo ============================================
echo.

set /p INSTALL_WHISPER="Install Voice Dictation (faster-whisper ~200MB)? (y/n): "
if /i "%INSTALL_WHISPER%"=="y" (
    echo Installing Whisper...
    pip install faster-whisper sounddevice numpy --quiet
    echo [OK] Voice Dictation ready.
)

set /p INSTALL_SPELL="Install Russian Spell Check (torch ~700MB)? (y/n): "
if /i "%INSTALL_SPELL%"=="y" (
    echo Installing Spell Check (this takes a while)...
    pip install transformers torch --quiet
    echo [OK] Spell Check ready.
)

:: ---- Setup app directory ----
set "APP_DIR=%APPDATA%\DeepLTranslator"
if not exist "%APP_DIR%" mkdir "%APP_DIR%"

:: Copy source files (exclude dev folders)
echo.
echo Copying application files...
xcopy /E /I /Y "." "%APP_DIR%" /EXCLUDE:deployment\exclude.txt >nul 2>&1
if errorlevel 1 xcopy /E /I /Y "." "%APP_DIR%" >nul
echo [OK] App installed to %APP_DIR%

:: ---- Create silent launcher ----
(
echo Set WshShell = CreateObject^("WScript.Shell"^)
echo WshShell.Run "pythonw ""%APP_DIR%\main.py""", 0, False
) > "%APP_DIR%\launch.vbs"
echo [OK] Launcher created.

:: ---- Generate icon + desktop shortcut ----
echo Creating shortcuts...
python -c "import sys; sys.path.insert(0, r'%APP_DIR%'); from ui.icon_generator import generate_app_icon; from ui.tray_menu import create_desktop_shortcut; generate_app_icon(); create_desktop_shortcut()" 2>nul
echo [OK] Desktop shortcut created.

:: ---- Launch ----
echo.
echo ============================================
echo   Installation complete!
echo ============================================
echo.
echo   Hotkeys:
echo     Ctrl+Alt+T  - Popup translation
echo     Ctrl+Alt+R  - Replace selected text
echo     Ctrl+Alt+Y  - Translate clipboard
echo     Ctrl+Alt+W  - Voice dictation
echo     Ctrl+Alt+N  - AI Negotiator
echo     Ctrl+Alt+E  - English Teacher
echo.

start "" wscript.exe "%APP_DIR%\launch.vbs"
echo App launched! Check your system tray.
pause
