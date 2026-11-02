#ifndef PackageDir
  #error Укажите /DPackageDir с папкой собранной программы
#endif
#ifndef ReleaseDir
  #error Укажите /DReleaseDir для установщика
#endif
[Setup]
AppId={{9B6E8A18-52F8-4D04-BD30-EB85E13B28B9}
AppName=Проверки еНот & ЕИС
AppVersion=0.2.1
VersionInfoVersion=0.2.1.0
AppPublisher=Alexandr Andreev
DefaultDirName={localappdata}\Programs\EnotChecks
DefaultGroupName=Проверки еНот & ЕИС
DisableDirPage=no
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
OutputDir={#ReleaseDir}
OutputBaseFilename=Setup_EnotChecks_0.2.1
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
SetupIconFile=src\enot_app\app.ico
UninstallDisplayIcon={app}\EnotChecks.exe
CloseApplications=yes

[Languages]
Name: "russian"; MessagesFile: "compiler:Languages\Russian.isl"

[Tasks]
Name: "desktopicon"; Description: "Создать ярлык на рабочем столе"; Flags: unchecked

[Files]
Source: "{#PackageDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\Проверки еНот & ЕИС"; Filename: "{app}\EnotChecks.exe"
Name: "{userdesktop}\Проверки еНот & ЕИС"; Filename: "{app}\EnotChecks.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\EnotChecks.exe"; Description: "Открыть Проверки еНот & ЕИС"; Flags: nowait postinstall skipifsilent
