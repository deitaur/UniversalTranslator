@echo off
title Universal Translator - Build EXE + Installer
echo ============================================
echo   Building Universal Translator
echo ============================================
echo.

cd /d "%~dp0.."

:: Check PyInstaller
python -m PyInstaller --version >nul 2>&1
if errorlevel 1 (
    echo [INFO] Installing PyInstaller...
    pip install pyinstaller --quiet
)

:: Generate icon first
echo [1/4] Generating app icon...
python -c "import sys; sys.path.insert(0, '.'); from ui.icon_generator import generate_app_icon; print(generate_app_icon())"
set "ICON_PATH=%APPDATA%\DeepLTranslator\app_icon.ico"

:: Build with PyInstaller using .spec (lightweight, no AI deps)
echo [2/4] Building lightweight EXE via .spec...
python -m PyInstaller --noconfirm UniversalTranslator.spec

if errorlevel 1 (
    echo [ERROR] PyInstaller build failed.
    pause
    exit /b 1
)

:: Copy icon to dist for NSIS
copy /Y "%ICON_PATH%" "dist\app_icon.ico" >nul 2>&1

:: Rename exe to standard name for NSIS
for %%f in (dist\UniversalTranslator_v*.exe) do (
    copy /Y "%%f" "dist\UniversalTranslator.exe" >nul 2>&1
)

echo [3/4] EXE built: dist\UniversalTranslator.exe
echo.

:: Check for NSIS
where makensis >nul 2>&1
if errorlevel 1 (
    echo [INFO] NSIS not found. Skipping installer creation.
    echo   Install NSIS from https://nsis.sourceforge.io/
    echo   Then re-run this script to build the installer.
    echo.
    echo   Or run manually:
    echo     makensis deployment\installer.nsi
    echo.
    goto done
)

:: Create installer output directory
if not exist installer_output mkdir installer_output

:: Build NSIS installer
echo [4/4] Building NSIS installer...
cd deployment
makensis installer.nsi
cd ..

if errorlevel 1 (
    echo [WARNING] NSIS build had issues. Check output above.
) else (
    echo.
    echo   Installer: installer_output\UniversalTranslator_Setup_v3.1.exe
)

:done
echo.
echo ============================================
echo   Build complete!
echo ============================================
echo.
echo   Lightweight EXE: dist\UniversalTranslator.exe
echo   (AI components installed separately via installer)
echo.
pause
