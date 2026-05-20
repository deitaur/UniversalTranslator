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
!define APP_VERSION "3.3"
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
