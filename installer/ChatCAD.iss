; Inno Setup script for Chat CAD.
; Build:
;   1. Install Inno Setup 6 from https://jrsoftware.org/isdl.php   (free, ~5 MB)
;   2. Right-click this .iss file -> "Compile" (or open it in the Inno IDE
;      and press F9). The output is dist\ChatCAD_Setup.exe.
;   3. Distribute ChatCAD_Setup.exe. End users double-click it and get
;      a proper Windows install wizard.

#define MyAppName       "Chat CAD"
#define MyAppVersion    "0.1.0"
#define MyAppPublisher  "Samarjith Biswas"
#define MyAppExeName    "Run Chat CAD.bat"
#define MyAppId         "{{A4F4C9D2-1B2E-4C3F-9A5D-CADCHATCAD001}}"

[Setup]
AppId={#MyAppId}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\ChatCAD
DefaultGroupName={#MyAppName}
UninstallDisplayName={#MyAppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
OutputDir=dist
OutputBaseFilename=ChatCAD_Setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64
SetupIconFile=
LicenseFile=
DisableWelcomePage=no

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; \
    GroupDescription: "Additional shortcuts:"; Flags: checkablealone

[Files]
; ship the entire chat_cad/ folder (parent of this installer/ dir)
Source: "..\*"; DestDir: "{app}"; Excludes: "installer\dist\*,output\*.stl,output\*.step,__pycache__\*,.git\*"; \
    Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}";          Filename: "{app}\installer\{#MyAppExeName}"; WorkingDir: "{app}"
Name: "{group}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}";    Filename: "{app}\installer\{#MyAppExeName}"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
; one-time conda+cadquery bootstrap; runs only if Miniforge isn't already there.
Filename: "powershell.exe"; \
    Parameters: "-ExecutionPolicy Bypass -NoProfile -File ""{app}\installer\install.ps1"""; \
    StatusMsg: "Installing Python environment + cadquery (~5 min, ~1.5 GB).  Please wait..."; \
    Flags: runhidden waituntilterminated

; Optionally launch the app at the end of install
Filename: "{app}\installer\{#MyAppExeName}"; \
    Description: "Launch {#MyAppName} now"; \
    Flags: postinstall shellexec skipifsilent nowait

[UninstallRun]
; offer to clean up the conda env on uninstall
Filename: "cmd.exe"; \
    Parameters: "/c rmdir /s /q ""%USERPROFILE%\miniforge-chatcad"""; \
    RunOnceId: "RemoveCondaEnv"; \
    Flags: runhidden

[Code]
function InitializeSetup(): Boolean;
begin
  Result := True;
end;
