[Setup]
AppName=GTAO HorseBet
AppVersion=1.0
DefaultDirName={pf}\GTAO HorseBet
DefaultGroupName=GTAO HorseBet
OutputDir=Output
OutputBaseFilename=GTAO_HorseBet_Installer
Compression=lzma2
SolidCompression=yes
; Ensure you have built the app using PyInstaller before compiling this script
SetupIconFile=resources\icon.ico
UninstallDisplayIcon={app}\GTAO_HorseBet.exe

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Additional icons:"

[Files]
; Copies everything from your PyInstaller "dist" directory into the installation directory
Source: "dist\GTAO_HorseBet\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
; Creates Start Menu shortcut
Name: "{group}\GTAO HorseBet"; Filename: "{app}\GTAO_HorseBet.exe"
; Creates Desktop shortcut
Name: "{commondesktop}\GTAO HorseBet"; Filename: "{app}\GTAO_HorseBet.exe"; Tasks: desktopicon

[Run]
; Offers to launch the app immediately after the installer finishes
Filename: "{app}\GTAO_HorseBet.exe"; Description: "Launch GTAO HorseBet"; Flags: nowait postinstall skipifsilent