; Установщик для Windows (Inno Setup 6). Собирается на GitHub: см. .github/workflows/windows.yml
; Ставится в профиль пользователя — права администратора не нужны. Данные (%APPDATA%\HabitTracker)
; установщик и удаление программы не трогают.
#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif

[Setup]
AppId={{6F1C2E7A-4B8D-4C1E-9A3F-2B7D4E9A1C55}
AppName=Трекер привычек и задач
AppVersion={#AppVersion}
AppVerName=Трекер привычек и задач {#AppVersion}
AppPublisher=HabitTracker
DefaultDirName={localappdata}\Programs\HabitTracker
DefaultGroupName=Трекер привычек и задач
DisableProgramGroupPage=yes
DisableDirPage=yes
PrivilegesRequired=lowest
OutputDir=..\dist
OutputBaseFilename=HabitTracker-Setup
SetupIconFile=icon.ico
UninstallDisplayIcon={app}\HabitTracker.exe
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
RestartApplications=no

[Languages]
Name: "ru"; MessagesFile: "compiler:Languages\Russian.isl"

[Tasks]
Name: "desktopicon"; Description: "Значок на рабочем столе"; GroupDescription: "Дополнительно:"

[InstallDelete]
; от прежней версии могли остаться лишние библиотеки — папку программы обновляем начисто
Type: filesandordirs; Name: "{app}\_internal"

[Files]
Source: "..\dist\HabitTracker\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\Трекер привычек и задач"; Filename: "{app}\HabitTracker.exe"
Name: "{autodesktop}\Трекер привычек и задач"; Filename: "{app}\HabitTracker.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\HabitTracker.exe"; Description: "Запустить трекер"; Flags: nowait postinstall skipifsilent
