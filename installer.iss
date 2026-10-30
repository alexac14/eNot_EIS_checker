#ifndef PackageDir
  #error Укажите /DPackageDir с папкой собранной программы
#endif
#ifndef ReleaseDir
  #error Укажите /DReleaseDir для установщика
#endif
[Setup]
AppId={{9B6E8A18-52F8-4D04-BD30-EB85E13B28B9}
AppName=Проверки еНот
AppVersion=0.1.2
AppPublisher=Проверки еНот
DefaultDirName={localappdata}\Programs\EnotChecks
DefaultGroupName=Проверки еНот
DisableDirPage=no
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
OutputDir={#ReleaseDir}
OutputBaseFilename=Setup_EnotChecks_0.1.2
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
Name: "{group}\Проверки еНот"; Filename: "{app}\EnotChecks.exe"
Name: "{userdesktop}\Проверки еНот"; Filename: "{app}\EnotChecks.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\EnotChecks.exe"; Description: "Открыть Проверки еНот"; Flags: nowait postinstall skipifsilent

; Пользовательские данные не включаются в установщик и не удаляются деинсталлятором.
