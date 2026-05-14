@echo off
title Universal Translator - Remove Old Version
echo ============================================
echo   Removing old version from AppData...
echo ============================================
echo.

:: Kill running instance
taskkill /F /IM pythonw.exe /FI "WINDOWTITLE eq *" >nul 2>&1
wscript.exe //B //nologo "%APPDATA%\DeepLTranslator\launch.vbs" >nul 2>&1
taskkill /F /IM wscript.exe /FI "MODULES eq launch.vbs" >nul 2>&1

:: Remove startup shortcut
set "STARTUP_LINK=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\Universal Translator.lnk"
if exist "%STARTUP_LINK%" (
    del "%STARTUP_LINK%"
    echo [OK] Startup shortcut removed.
) else (
    echo [--] No startup shortcut found.
)

:: Also check old name
set "OLD_LINK=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\DeepL Translator.lnk"
if exist "%OLD_LINK%" (
    del "%OLD_LINK%"
    echo [OK] Old startup shortcut removed.
)

:: Remove desktop shortcut
set "DESKTOP_LINK=%USERPROFILE%\Desktop\Universal Translator.lnk"
if exist "%DESKTOP_LINK%" (
    del "%DESKTOP_LINK%"
    echo [OK] Desktop shortcut removed.
)

:: Remove app folder (keep config)
set "APP_DIR=%APPDATA%\DeepLTranslator"
if exist "%APP_DIR%\deepl_translator.py" (
    del "%APP_DIR%\deepl_translator.py"
    echo [OK] Old script removed.
)
if exist "%APP_DIR%\launch.vbs" (
    del "%APP_DIR%\launch.vbs"
    echo [OK] Launcher removed.
)
if exist "%APP_DIR%\app_icon.ico" (
    del "%APP_DIR%\app_icon.ico"
    echo [OK] Icon removed.
)
if exist "%APP_DIR%\_make_desktop_shortcut.vbs" del "%APP_DIR%\_make_desktop_shortcut.vbs"
if exist "%APP_DIR%\_make_startup.vbs" del "%APP_DIR%\_make_startup.vbs"

echo.
echo [OK] Old version removed. Config (config.json) was kept.
echo     You can now run the new installer.
echo.
pause
