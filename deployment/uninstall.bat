@echo off
title Universal Translator - Uninstaller
echo ============================================
echo   Universal Translator - Uninstaller
echo ============================================
echo.

:: Kill running instance
echo Stopping application...
taskkill /f /im UniversalTranslator.exe >nul 2>&1
taskkill /f /im pythonw.exe /fi "WINDOWTITLE eq Universal*" >nul 2>&1
echo [OK] Application stopped.

:: Remove startup shortcut
set "STARTUP_DIR=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"
del "%STARTUP_DIR%\Universal Translator.lnk" >nul 2>&1
echo [OK] Startup shortcut removed.

:: Remove desktop shortcut
del "%USERPROFILE%\Desktop\Universal Translator.lnk" >nul 2>&1
echo [OK] Desktop shortcut removed.

:: Remove Start Menu group
set "SM_DIR=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Universal Translator"
if exist "%SM_DIR%" rmdir /s /q "%SM_DIR%" >nul 2>&1
echo [OK] Start Menu shortcuts removed.

:: Ask about config
set "APP_DIR=%APPDATA%\DeepLTranslator"
echo.
set /p DELCONFIG="Delete settings, API keys and saved roles? (y/n): "
if /i "%DELCONFIG%"=="y" (
    if exist "%APP_DIR%" rmdir /s /q "%APP_DIR%" >nul 2>&1
    echo [OK] All settings and data deleted.
) else (
    echo [OK] Settings kept in %APP_DIR%
)

:: Remove registry entries
reg delete "HKCU\Software\Microsoft\Windows\CurrentVersion\Uninstall\Universal Translator" /f >nul 2>&1
reg delete "HKCU\Software\Universal Translator" /f >nul 2>&1
echo [OK] Registry entries removed.

echo.
echo ============================================
echo   Uninstall complete.
echo ============================================
echo.
pause
