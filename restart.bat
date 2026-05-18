@echo off
setlocal

set "APP_DIR=%~dp0"
set "MAIN_PY=%APP_DIR%main.py"

echo Stopping running instance...
taskkill /F /FI "WINDOWTITLE eq Universal Translator" /T >nul 2>&1

:: Kill pythonw / python processes running main.py
for /f "tokens=2" %%P in ('wmic process where "CommandLine like '%%main.py%%'" get ProcessId /format:value 2^>nul ^| findstr "="') do (
    echo   killing PID %%P
    taskkill /F /PID %%P >nul 2>&1
)

:: Wait for Windows to release hotkey registrations (takes ~1-2s after process death)
echo Waiting for hotkeys to be released...
timeout /t 3 /nobreak >nul

echo Starting Universal Translator...
start "" pythonw "%MAIN_PY%"

echo Done.
endlocal
