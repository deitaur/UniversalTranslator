@echo off
title Universal Translator - Cleanup
echo ============================================
echo   Cleaning up project structure
echo ============================================
echo.

cd /d "%~dp0"

:: Remove all __pycache__ directories
echo [1/7] Removing __pycache__...
for /d /r %%i in (__pycache__) do @if exist "%%i" rmdir /s /q "%%i"

:: Remove pytest cache
echo [2/7] Removing pytest cache...
if exist ".pytest_cache" rmdir /s /q ".pytest_cache"
for /d %%i in (pytest-cache-*) do @if exist "%%i" rmdir /s /q "%%i"

:: Remove build artifacts
echo [3/7] Removing build artifacts...
if exist "build" rmdir /s /q "build"

:: Remove old archive
echo [4/7] Removing archive (old code)...
if exist "archive" rmdir /s /q "archive"

:: Remove duplicate .spec from deployment
echo [5/7] Removing duplicate files...
if exist "deployment\UniversalTranslator.spec" del /f "deployment\UniversalTranslator.spec"
if exist "deployment\uninstall_old.bat" del /f "deployment\uninstall_old.bat"
if exist "deployment\installer.iss" del /f "deployment\installer.iss"

:: Remove root __init__.py (not needed, this is an app not a package)
echo [6/7] Removing unnecessary __init__.py from root...
if exist "__init__.py" del /f "__init__.py"

:: Add .gitignore if missing
echo [7/7] Updating .gitignore...
(
echo __pycache__/
echo *.pyc
echo build/
echo dist/
echo installer_output/
echo *.egg-info/
echo .pytest_cache/
echo pytest-cache-*/
) > .gitignore

echo.
echo ============================================
echo   Cleanup complete!
echo ============================================
echo.
echo   Final structure:
echo.
echo   main.py, config.py, globals.py    (core)
echo   services\translators\             (DeepL, Google, Yandex)
echo   services\ai\                      (Ollama, Whisper, RAG)
echo   storage\                          (roles, history)
echo   ui\                               (windows, tray, notifications)
echo   win32\                            (clipboard, hotkeys, keyboard)
echo   utils\                            (language)
echo   deployment\                       (build, install, NSIS)
echo   docs\                             (documentation)
echo   RAG\                              (training materials)
echo   tests\                            (unit tests)
echo.
pause
