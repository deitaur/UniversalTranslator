; ============================================================
;  Universal Translator - Inno Setup Installer Script
;  Compile with Inno Setup 6+ (https://jrsoftware.org/isinfo.php)
;  Prerequisites: run build.bat first to create dist\UniversalTranslator.exe
; ============================================================

#define MyAppName "Universal Translator"
#define MyAppVersion "3.1"
#define MyAppPublisher "Universal Translator"
#define MyAppExeName "UniversalTranslator.exe"

[Setup]
AppId={{E7A3F2B1-4D5C-6E7F-8A9B-0C1D2E3F4A5B}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
UninstallDisplayIcon={app}\{#MyAppExeName}
OutputDir=installer_output
OutputBaseFilename=UniversalTranslator_Setup_{#MyAppVersion}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
SetupIconFile=..\dist\app_icon.ico
DisableProgramGroupPage=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Additional shortcuts:"
Name: "startupentry"; Description: "&Start automatically with Windows"; GroupDescription: "Startup:"

[Files]
Source: "..\dist\UniversalTranslator.exe"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon
Name: "{userstartup}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: startupentry

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch {#MyAppName}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{userappdata}\DeepLTranslator"

[Code]
// ---- Language selection page during install ----

var
  LangPage: TInputOptionWizardPage;

const
  LangCount = 15;

procedure InitializeWizard;
begin
  LangPage := CreateInputOptionPage(wpSelectTasks,
    'Source Language',
    'Which language do you want to translate FROM?',
    'Select the language you will be translating from. This translates to English. You can change it later in Settings.',
    True, False);
  LangPage.Add('Russian');
  LangPage.Add('Spanish');
  LangPage.Add('French');
  LangPage.Add('German');
  LangPage.Add('Chinese');
  LangPage.Add('Japanese');
  LangPage.Add('Korean');
  LangPage.Add('Portuguese');
  LangPage.Add('Italian');
  LangPage.Add('Arabic');
  LangPage.Add('Dutch');
  LangPage.Add('Polish');
  LangPage.Add('Turkish');
  LangPage.Add('Ukrainian');
  LangPage.Add('Czech');

  // Try to detect system language and pre-select it
  case ActiveLanguage of
    'russian': LangPage.SelectedValueIndex := 0;
    'spanish': LangPage.SelectedValueIndex := 1;
    'french':  LangPage.SelectedValueIndex := 2;
    'german':  LangPage.SelectedValueIndex := 3;
  else
    // Default: detect from Windows UI language
    LangPage.SelectedValueIndex := 0; // Russian as fallback
  end;
end;

function GetLangCode: String;
begin
  case LangPage.SelectedValueIndex of
    0:  Result := 'ru';
    1:  Result := 'es';
    2:  Result := 'fr';
    3:  Result := 'de';
    4:  Result := 'zh';
    5:  Result := 'ja';
    6:  Result := 'ko';
    7:  Result := 'pt';
    8:  Result := 'it';
    9:  Result := 'ar';
    10: Result := 'nl';
    11: Result := 'pl';
    12: Result := 'tr';
    13: Result := 'uk';
    14: Result := 'cs';
  else
    Result := 'ru';
  end;
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  ConfigDir: String;
  ConfigFile: String;
  LangCode: String;
  JsonContent: String;
begin
  if CurStep = ssPostInstall then
  begin
    // Write initial config with the selected language
    ConfigDir := ExpandConstant('{userappdata}\DeepLTranslator');
    ForceDirectories(ConfigDir);
    ConfigFile := ConfigDir + '\config.json';

    LangCode := GetLangCode;

    // Only write config if it doesn't already exist (fresh install)
    if not FileExists(ConfigFile) then
    begin
      JsonContent := '{' + #13#10 +
        '  "source_lang": "' + LangCode + '",' + #13#10 +
        '  "engine": "google"' + #13#10 +
        '}';
      SaveStringToFile(ConfigFile, JsonContent, False);
    end;
  end;
end;

// Kill the running app before uninstall
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  ResultCode: Integer;
begin
  if CurUninstallStep = usUninstall then
  begin
    Exec('taskkill', '/F /IM UniversalTranslator.exe', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  end;
end;
