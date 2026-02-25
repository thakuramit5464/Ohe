; ============================================================
; OHE Stagger & Wire Diameter Measurement System
; Inno Setup Script  (v6.x)
;
; To compile:
;   1. Install Inno Setup 6 from https://jrsoftware.org/isinfo.php
;   2. Run PyInstaller first:  pyinstaller ohe.spec --noconfirm
;   3. Open this file in Inno Setup Compiler and press Ctrl+F9
;      OR run:  iscc installer\ohe_setup.iss
;
; Output: installer\Output\OHE_Setup_1.0.0.exe
; ============================================================

#define MyAppName      "OHE Measurement System"
#define MyAppVersion   "1.0.0"
#define MyAppPublisher "OHE Project"
#define MyAppURL       "https://github.com/thakuramit5464/Ohe"
#define MyAppExeName   "ohe-gui.exe"
#define MySourceDir    "..\dist\ohe-gui"
#define MyOutputDir    "Output"

[Setup]
; ---- Identity ----
AppId={{B3C7A8F2-9D14-4E6A-BC21-37F0D8E5A924}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}

; ---- Install location ----
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
AllowNoIcons=no

; ---- Output ----
OutputDir={#MyOutputDir}
OutputBaseFilename=OHE_Setup_{#MyAppVersion}
; SetupIconFile=assets\icon.ico          ; Uncomment after adding assets\icon.ico
UninstallDisplayIcon={app}\{#MyAppExeName}

; ---- Compression ----
Compression=lzma2/ultra64
SolidCompression=yes
LZMAUseSeparateProcess=yes

; ---- UI & Wizard ----
WizardStyle=modern
WizardResizable=no
DisableWelcomePage=no
DisableDirPage=no
DisableReadyPage=no

; ---- Privileges ----
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog

; ---- Minimum OS ----
MinVersion=10.0.17763
ArchitecturesInstallIn64BitMode=x64compatible

; ---- After install ----
ChangesAssociations=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon";    Description: "Create a &desktop shortcut";    GroupDescription: "Additional icons:"; Flags: unchecked
Name: "quicklaunch";    Description: "Create a &Quick Launch shortcut"; GroupDescription: "Additional icons:"; Flags: unchecked; OnlyBelowVersion: 6.1
Name: "associatemp4";   Description: "Associate .mp4 files with OHE GUI"; GroupDescription: "File associations:"; Flags: unchecked

[Files]
; Main application (everything PyInstaller produced)
Source: "{#MySourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

; Runtime data directories (created empty)
; (handled in [Dirs] below)

; Default config (only if not already present — user may have customised it)
Source: "..\config\default.yaml";    DestDir: "{app}\config"; Flags: ignoreversion onlyifdoesntexist
Source: "..\config\calibration.json"; DestDir: "{app}\config"; Flags: ignoreversion onlyifdoesntexist

[Dirs]
; Create writable session / debug / video data dirs under the install folder
Name: "{app}\data\sessions"
Name: "{app}\data\debug"
Name: "{app}\data\sample_videos"
; Also create writable user-local dirs for session data (preferred for non-admin installs)
Name: "{userappdata}\OHE\sessions"
Name: "{userappdata}\OHE\debug"

[Icons]
; Start Menu
Name: "{group}\{#MyAppName}";           Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"
Name: "{group}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}"

; Desktop shortcut (optional task)
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; Tasks: desktopicon

; Quick Launch (XP/Vista compat)
Name: "{userappdata}\Microsoft\Internet Explorer\Quick Launch\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: quicklaunch

[Registry]
; File association: open .mp4 with OHE GUI (optional task)
Root: HKCU; Subkey: "Software\Classes\.mp4\OpenWithProgids"; ValueType: string; ValueName: "OHE.VideoFile"; ValueData: ""; Flags: uninsdeletevalue; Tasks: associatemp4
Root: HKCU; Subkey: "Software\Classes\OHE.VideoFile"; ValueType: string; ValueName: ""; ValueData: "OHE Video File"; Flags: uninsdeletekey; Tasks: associatemp4
Root: HKCU; Subkey: "Software\Classes\OHE.VideoFile\DefaultIcon"; ValueType: string; ValueName: ""; ValueData: "{app}\{#MyAppExeName},0"; Tasks: associatemp4
Root: HKCU; Subkey: "Software\Classes\OHE.VideoFile\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#MyAppExeName}"" ""%1"""; Tasks: associatemp4

[Run]
; Offer to launch app after install
Filename: "{app}\{#MyAppExeName}"; Description: "Launch {#MyAppName} now"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Remove log / cache files created at runtime
Type: filesandordirs; Name: "{app}\data\debug"
Type: filesandordirs; Name: "{app}\__pycache__"

[Code]
// ---------------------------------------------------------------
// Pre-install check: warn if a previous version is running
// ---------------------------------------------------------------
function InitializeSetup(): Boolean;
var
  ResultCode: Integer;
begin
  Result := True;
  if CheckForMutexes('OHE_GUI_RUNNING') then begin
    MsgBox(
      'OHE Measurement System appears to be running.' + #13#10 +
      'Please close it before installing.',
      mbError, MB_OK
    );
    Result := False;
  end;
end;
