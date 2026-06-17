[Setup]
AppName=AutoBet
AppVersion=1.0
AppPublisher=raeditio
DefaultDirName={commonpf}\AutoBet
DefaultGroupName=AutoBet
OutputDir=Output
OutputBaseFilename=AutoBet v1.0
Compression=lzma2
SolidCompression=yes
; Ensure you have built the app using PyInstaller before compiling this script
SetupIconFile=resources\icon.ico
UninstallDisplayIcon={app}\AutoBet.exe

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Additional icons:"

[Files]
; Copies everything from your PyInstaller "dist" directory into the installation directory
Source: "dist\AutoBet\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
; Creates Start Menu shortcut
Name: "{group}\AutoBet"; Filename: "{app}\AutoBet.exe"
; Creates Desktop shortcut
Name: "{commondesktop}\AutoBet"; Filename: "{app}\AutoBet.exe"; Tasks: desktopicon

[Run]
; Offers to launch the app immediately after the installer finishes
Filename: "{app}\AutoBet.exe"; Description: "Launch AutoBet"; Flags: nowait postinstall skipifsilent