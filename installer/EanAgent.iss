; Instalátor EAN agenta (Inno Setup 6). Sestavuje build.bat: ISCC /DAppVersion=x.y.z
#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif

[Setup]
AppId={{6F1E2C7A-4B8D-4E35-9A61-EA4A6E5C0B17}
AppName=EAN Agent
AppVersion={#AppVersion}
AppVerName=EAN Agent {#AppVersion}
AppPublisher=Mixit
AppPublisherURL=https://github.com/bluebeing/ean-skener
; instalace jen pro aktuálního uživatele, bez práv správce
PrivilegesRequired=lowest
DefaultDirName={localappdata}\Programs\EAN Agent
DisableDirPage=yes
DisableProgramGroupPage=yes
DisableReadyPage=yes
OutputDir=..\dist
OutputBaseFilename=EanAgent-Setup-{#AppVersion}
SetupIconFile=..\agent\app.ico
UninstallDisplayIcon={app}\EanAgent.exe
UninstallDisplayName=EAN Agent
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
CloseApplications=no

[Languages]
Name: "cs"; MessagesFile: "compiler:Languages\Czech.isl"

[Tasks]
Name: "autostart"; Description: "Spouštět EAN agenta automaticky po přihlášení do Windows"
Name: "desktopicon"; Description: "Vytvořit zástupce na ploše"; Flags: unchecked

[Files]
; složka data (párovací klíč) se do instalátoru nikdy nepřibalí a při aktualizaci zůstane
Source: "..\dist\EanAgent\*"; DestDir: "{app}"; Excludes: "\data,\data\*"; \
  Flags: ignoreversion recursesubdirs createallsubdirs

[InstallDelete]
; staré knihovny z předchozí verze (data zůstávají)
Type: filesandordirs; Name: "{app}\_internal"

[Icons]
Name: "{autoprograms}\EAN Agent"; Filename: "{app}\EanAgent.exe"
Name: "{autodesktop}\EAN Agent"; Filename: "{app}\EanAgent.exe"; Tasks: desktopicon

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; \
  ValueName: "EanAgent"; ValueData: """{app}\EanAgent.exe"""; Flags: uninsdeletevalue; Tasks: autostart

[Run]
; spustí se i po tiché aktualizaci (bez skipifsilent)
Filename: "{app}\EanAgent.exe"; Description: "Spustit EAN agenta"; Flags: nowait postinstall

[Code]
procedure StopAgent();
var
  ResultCode: Integer;
begin
  Exec(ExpandConstant('{sys}\taskkill.exe'), '/F /IM EanAgent.exe', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  Sleep(500);
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
begin
  StopAgent();
  Result := '';
end;

function InitializeUninstall(): Boolean;
begin
  StopAgent();
  Result := True;
end;
