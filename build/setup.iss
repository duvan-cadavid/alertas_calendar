; Inno Setup Script — Goujana Agenda
; Descarga Inno Setup: https://jrsoftware.org/isdl.php
; Compilar: iscc build\setup.iss

#define AppName      "Goujana Agenda"
#define AppVersion   "1.0.0"
#define AppPublisher "Goujana"
#define AppExeName   "Goujana Agenda.exe"
#define AppId        "{{A1B2C3D4-E5F6-7890-ABCD-EF1234567890}"
; Meetily (transcripción de reuniones) — el .exe se descarga a vendor\
; antes de compilar (lo hace el workflow de release; ver release.yml).
; Si vendor\ no existe, el instalador se compila sin Meetily.
#define MeetilyVersion "0.4.0"
#define MeetilySetup   "meetily_" + MeetilyVersion + "_x64-setup.exe"

[Setup]
AppId={#AppId}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
OutputDir=..\dist\installer
OutputBaseFilename=Goujana_Agenda_Setup
SetupIconFile=..\assets\icon.ico
Compression=lzma
SolidCompression=yes
WizardStyle=modern
ChangesEnvironment=yes
MinVersion=10.0
PrivilegesRequired=admin

[Languages]
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"

[Tasks]
Name: "desktopicon"; Description: "Crear icono en el escritorio"; GroupDescription: "Opciones adicionales:"

[Files]
; Aplicación principal
Source: "..\dist\{#AppName}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
; FFmpeg — descargado por el workflow de CI en build\bin\ffmpeg.exe
Source: "bin\ffmpeg.exe"; DestDir: "{app}\bin"; Flags: ignoreversion
; Meetily — descargado por el workflow de CI en vendor\ (opcional)
Source: "..\vendor\{#MeetilySetup}"; DestDir: "{tmp}"; Flags: deleteafterinstall skipifsourcedoesntexist

[Icons]
Name: "{group}\{#AppName}";         Filename: "{app}\{#AppExeName}"
Name: "{group}\Desinstalar";        Filename: "{uninstallexe}"
Name: "{commondesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"; Tasks: desktopicon

[Registry]
; Autostart obligatorio — inicia con Windows en cualquier sesión del usuario
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "{#AppName}"; ValueData: """{app}\{#AppExeName}"""; Flags: uninsdeletevalue

[Run]
; Instalación silenciosa de Meetily (instalador NSIS de Tauri: flag /S)
Filename: "{tmp}\{#MeetilySetup}"; Parameters: "/S"; \
    StatusMsg: "Instalando Meetily (transcripción de reuniones)..."; \
    Flags: waituntilterminated skipifdoesntexist
Filename: "{app}\{#AppExeName}"; Description: "Iniciar {#AppName} ahora"; Flags: nowait postinstall skipifsilent

[Code]
const
  ENV_KEY          = 'SYSTEM\CurrentControlSet\Control\Session Manager\Environment';
  WM_SETTINGCHANGE = $001A;

{ ── PATH helpers ─────────────────────────────────────────────────────────── }

function GetSystemPath: string;
begin
  RegQueryStringValue(HKLM, ENV_KEY, 'Path', Result);
end;

procedure SetSystemPath(const NewPath: string);
begin
  RegWriteExpandStringValue(HKLM, ENV_KEY, 'Path', NewPath);
end;

procedure BroadcastPathChange;
var
  S: string;
begin
  S := 'Environment';
  SendBroadcastMessage(WM_SETTINGCHANGE, 0, CastStringToInteger(S));
end;

procedure AddToPath(const Dir: string);
var
  Paths: string;
  DirU: string;
begin
  Paths := GetSystemPath;
  DirU  := Uppercase(Dir);
  // Already in PATH?
  if Pos(';' + DirU + ';', ';' + Uppercase(Paths) + ';') > 0 then exit;
  if Paths = '' then
    SetSystemPath(Dir)
  else
    SetSystemPath(Paths + ';' + Dir);
  BroadcastPathChange;
end;

procedure RemoveFromPath(const Dir: string);
var
  Paths, DirU, PathsU: string;
  P: Integer;
begin
  Paths  := GetSystemPath;
  DirU   := ';' + Uppercase(Dir) + ';';
  PathsU := ';' + Uppercase(Paths) + ';';
  P := Pos(DirU, PathsU);
  if P = 0 then exit;
  Delete(Paths, P, Length(Dir) + 1);   // remove ;Dir
  SetSystemPath(Paths);
  BroadcastPathChange;
end;

{ ── Install / Uninstall hooks ─────────────────────────────────────────────── }

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then
    AddToPath(ExpandConstant('{app}\bin'));
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if CurUninstallStep = usPostUninstall then
    RemoveFromPath(ExpandConstant('{app}\bin'));
end;
