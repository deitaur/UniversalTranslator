; ============================================================
;  Universal Translator - NSIS Installer Script
;  Requires: NSIS 3.x (https://nsis.sourceforge.io/)
;  Prerequisites: run build.bat first to create dist\UniversalTranslator*.exe
; ============================================================

!include "MUI2.nsh"
!include "LogicLib.nsh"
!include "nsDialogs.nsh"

; ---- App Info ----
!define APP_NAME "Universal Translator"
!define APP_VERSION "3.1"
!define APP_EXE "UniversalTranslator.exe"
!define APP_PUBLISHER "Universal Translator"
!define CONFIG_DIR "$APPDATA\DeepLTranslator"

; ---- Installer Settings ----
Name "${APP_NAME} ${APP_VERSION}"
OutFile "..\installer_output\UniversalTranslator_Setup_v${APP_VERSION}.exe"
InstallDir "$LOCALAPPDATA\${APP_NAME}"
InstallDirRegKey HKCU "Software\${APP_NAME}" "InstallDir"
RequestExecutionLevel user
Unicode True

; ---- UI Settings ----
!define MUI_ICON "..\dist\app_icon.ico"
!define MUI_UNICON "..\dist\app_icon.ico"
!define MUI_ABORTWARNING
!define MUI_WELCOMEFINISHPAGE_BITMAP_NOSTRETCH

; ---- Variables ----
Var ChkWhisper
Var ChkSpellCheck
Var ChkOllama
Var InstallWhisper
Var InstallSpellCheck
Var InstallOllama
Var PythonPath

; ============================================================
;  PAGES
; ============================================================

; Welcome
!define MUI_WELCOMEPAGE_TITLE "Welcome to ${APP_NAME} Setup"
!define MUI_WELCOMEPAGE_TEXT "This wizard will install ${APP_NAME} v${APP_VERSION} on your computer.$\r$\n$\r$\nFeatures:$\r$\n  - Translate text with DeepL, Google, Yandex$\r$\n  - Voice dictation with Whisper AI$\r$\n  - AI Chat with local Ollama models$\r$\n  - Customizable AI roles with RAG$\r$\n$\r$\nClick Next to continue."
!insertmacro MUI_PAGE_WELCOME

; License (optional - skip if no license file)
; !insertmacro MUI_PAGE_LICENSE "..\LICENSE.txt"

; Install directory
!insertmacro MUI_PAGE_DIRECTORY

; AI Components page (custom)
Page custom AIComponentsPage AIComponentsPageLeave

; Install files
!insertmacro MUI_PAGE_INSTFILES

; Finish
!define MUI_FINISHPAGE_RUN "$INSTDIR\${APP_EXE}"
!define MUI_FINISHPAGE_RUN_TEXT "Launch ${APP_NAME}"
!define MUI_FINISHPAGE_SHOWREADME ""
!define MUI_FINISHPAGE_SHOWREADME_TEXT "Create Desktop Shortcut"
!define MUI_FINISHPAGE_SHOWREADME_FUNCTION CreateDesktopShortcut
!insertmacro MUI_PAGE_FINISH

; Uninstaller pages
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES

; Language
!insertmacro MUI_LANGUAGE "English"
!insertmacro MUI_LANGUAGE "Russian"

; ============================================================
;  AI COMPONENTS CUSTOM PAGE
; ============================================================

Function AIComponentsPage
    nsDialogs::Create 1018
    Pop $0

    ${NSD_CreateGroupBox} 5% 0 90% 85u "Optional AI Components"
    Pop $0

    ${NSD_CreateLabel} 10% 14u 80% 20u "Select which AI features to install.$\r$\nThese require Python and pip. Skip if unsure."
    Pop $0

    ${NSD_CreateCheckbox} 10% 40u 80% 12u "Voice Dictation (faster-whisper + sounddevice) ~200 MB"
    Pop $ChkWhisper

    ${NSD_CreateCheckbox} 10% 56u 80% 12u "Russian Spell Check (transformers + torch) ~700 MB"
    Pop $ChkSpellCheck

    ${NSD_CreateCheckbox} 10% 72u 80% 12u "Download and install Ollama for local AI chat"
    Pop $ChkOllama

    ${NSD_CreateGroupBox} 5% 92u 90% 40u "Note"
    Pop $0

    ${NSD_CreateLabel} 10% 104u 80% 24u "AI components are installed via pip and require Python 3.10+.$\r$\nYou can install them later: Settings > the app will show instructions."
    Pop $0

    nsDialogs::Show
FunctionEnd

Function AIComponentsPageLeave
    ${NSD_GetState} $ChkWhisper $InstallWhisper
    ${NSD_GetState} $ChkSpellCheck $InstallSpellCheck
    ${NSD_GetState} $ChkOllama $InstallOllama
FunctionEnd

; ============================================================
;  INSTALLER SECTIONS
; ============================================================

Section "Core Application" SecCore
    SectionIn RO ; Required, cannot be unchecked

    SetOutPath "$INSTDIR"

    ; Kill running instance
    nsExec::ExecToLog 'taskkill /F /IM ${APP_EXE}'

    ; Copy main exe
    File "..\dist\${APP_EXE}"

    ; Create config directory
    CreateDirectory "${CONFIG_DIR}"

    ; Write initial config if not exists
    IfFileExists "${CONFIG_DIR}\config.json" +2 0
    FileOpen $0 "${CONFIG_DIR}\config.json" w
    FileWrite $0 '{$\r$\n  "source_lang": "ru",$\r$\n  "engine": "google",$\r$\n  "ollama_model": "qwen2.5:14b"$\r$\n}'
    FileClose $0

    ; Start Menu shortcuts
    CreateDirectory "$SMPROGRAMS\${APP_NAME}"
    CreateShortcut "$SMPROGRAMS\${APP_NAME}\${APP_NAME}.lnk" "$INSTDIR\${APP_EXE}"
    CreateShortcut "$SMPROGRAMS\${APP_NAME}\Uninstall.lnk" "$INSTDIR\Uninstall.exe"

    ; Write uninstaller
    WriteUninstaller "$INSTDIR\Uninstall.exe"

    ; Registry for Add/Remove Programs
    WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_NAME}" "DisplayName" "${APP_NAME}"
    WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_NAME}" "UninstallString" "$\"$INSTDIR\Uninstall.exe$\""
    WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_NAME}" "DisplayIcon" "$INSTDIR\${APP_EXE}"
    WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_NAME}" "DisplayVersion" "${APP_VERSION}"
    WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_NAME}" "Publisher" "${APP_PUBLISHER}"
    WriteRegStr HKCU "Software\${APP_NAME}" "InstallDir" "$INSTDIR"
SectionEnd

Section "AI Components" SecAI
    ; Find Python
    nsExec::ExecToStack 'python --version'
    Pop $0
    Pop $PythonPath

    ${If} $0 != 0
        ; Try python3
        nsExec::ExecToStack 'python3 --version'
        Pop $0
        ${If} $0 != 0
            MessageBox MB_OK|MB_ICONINFORMATION "Python not found. AI components require Python 3.10+.$\r$\n$\r$\nInstall Python from https://python.org and then run:$\r$\npip install faster-whisper sounddevice numpy"
            Goto ai_done
        ${EndIf}
    ${EndIf}

    ; Install Whisper
    ${If} $InstallWhisper == ${BST_CHECKED}
        DetailPrint "Installing Voice Dictation components..."
        nsExec::ExecToLog 'pip install faster-whisper sounddevice numpy --quiet'
        Pop $0
        ${If} $0 != 0
            DetailPrint "Warning: Whisper installation had issues. You can retry manually."
        ${Else}
            DetailPrint "Voice Dictation installed successfully."
        ${EndIf}
    ${EndIf}

    ; Install Spell Check
    ${If} $InstallSpellCheck == ${BST_CHECKED}
        DetailPrint "Installing Spell Check components (this may take a while)..."
        nsExec::ExecToLog 'pip install transformers torch --quiet'
        Pop $0
        ${If} $0 != 0
            DetailPrint "Warning: Spell Check installation had issues. You can retry manually."
        ${Else}
            DetailPrint "Spell Check installed successfully."
        ${EndIf}
    ${EndIf}

    ; Install Ollama
    ${If} $InstallOllama == ${BST_CHECKED}
        DetailPrint "Opening Ollama download page..."
        ExecShell "open" "https://ollama.com/download"
        MessageBox MB_OK|MB_ICONINFORMATION "Ollama download page opened in your browser.$\r$\n$\r$\nAfter installing Ollama, run this command:$\r$\n  ollama pull qwen2.5:14b"
        DetailPrint "Ollama: user directed to download page."
    ${EndIf}

    ai_done:
SectionEnd

; ============================================================
;  HELPER FUNCTIONS
; ============================================================

Function CreateDesktopShortcut
    CreateShortcut "$DESKTOP\${APP_NAME}.lnk" "$INSTDIR\${APP_EXE}"
FunctionEnd

Function .onInit
    ; Set default language based on system
    System::Call 'kernel32::GetUserDefaultUILanguage() i .r0'
    ${If} $0 == 1049 ; Russian
        !insertmacro MUI_LANGDLL_DISPLAY
    ${EndIf}
FunctionEnd

; ============================================================
;  UNINSTALLER
; ============================================================

Section "Uninstall"
    ; Kill running instance
    nsExec::ExecToLog 'taskkill /F /IM ${APP_EXE}'
    Sleep 1000

    ; Remove files
    Delete "$INSTDIR\${APP_EXE}"
    Delete "$INSTDIR\Uninstall.exe"
    RMDir "$INSTDIR"

    ; Remove shortcuts
    Delete "$DESKTOP\${APP_NAME}.lnk"
    Delete "$SMPROGRAMS\${APP_NAME}\${APP_NAME}.lnk"
    Delete "$SMPROGRAMS\${APP_NAME}\Uninstall.lnk"
    RMDir "$SMPROGRAMS\${APP_NAME}"

    ; Remove startup entry
    Delete "$SMSTARTUP\${APP_NAME}.lnk"

    ; Remove registry
    DeleteRegKey HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_NAME}"
    DeleteRegKey HKCU "Software\${APP_NAME}"

    ; Ask to remove config
    MessageBox MB_YESNO "Remove settings and saved data?" IDNO skip_config
    RMDir /r "${CONFIG_DIR}"
    skip_config:
SectionEnd
