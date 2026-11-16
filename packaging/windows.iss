#ifndef AppVersion
  #define AppVersion "3.3.0"
#endif
[Setup]
AppId={{5E9907D4-B062-4E6A-AEB0-223E3249D942}
AppName=RetroArch Assistant
AppVersion={#AppVersion}
AppPublisher=MightyKartz
AppPublisherURL=https://github.com/MightyKartz/PLCN
DefaultDirName={localappdata}\Programs\PLCN
DefaultGroupName=RetroArch Assistant
AllowNoIcons=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\dist
OutputBaseFilename=RetroArchAssistant-Windows-x64-Setup
Compression=lzma2
SolidCompression=yes
SetupIconFile=icons\app-icon.ico
UninstallDisplayIcon={app}\RetroArchAssistant.exe

[Files]
Source: "..\dist\RetroArchAssistant\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\RetroArch Assistant"; Filename: "{app}\RetroArchAssistant.exe"
Name: "{autodesktop}\RetroArch Assistant"; Filename: "{app}\RetroArchAssistant.exe"; Tasks: desktopicon

[Tasks]
Name: desktopicon; Description: "Create a desktop shortcut"; Flags: unchecked

[Run]
Filename: "{app}\RetroArchAssistant.exe"; Description: "Open RetroArch Assistant"; Flags: nowait postinstall skipifsilent
