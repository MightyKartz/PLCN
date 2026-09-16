#ifndef AppVersion
  #define AppVersion "3.2.0"
#endif
[Setup]
AppId={{5E9907D4-B062-4E6A-AEB0-223E3249D942}
AppName=PLCN
AppVersion={#AppVersion}
AppPublisher=MightyKartz
AppPublisherURL=https://github.com/MightyKartz/PLCN
DefaultDirName={localappdata}\Programs\PLCN
DefaultGroupName=PLCN
AllowNoIcons=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\dist
OutputBaseFilename=PLCN-Windows-x64-Setup
Compression=lzma2
SolidCompression=yes
UninstallDisplayIcon={app}\PLCN.exe

[Files]
Source: "..\dist\PLCN\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\PLCN"; Filename: "{app}\PLCN.exe"
Name: "{autodesktop}\PLCN"; Filename: "{app}\PLCN.exe"; Tasks: desktopicon

[Tasks]
Name: desktopicon; Description: "Create a desktop shortcut"; Flags: unchecked

[Run]
Filename: "{app}\PLCN.exe"; Description: "Open PLCN"; Flags: nowait postinstall skipifsilent
