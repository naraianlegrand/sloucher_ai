; Sloucher installer (Inno Setup 6). Build: packaging\build.ps1
; One file, no admin rights, installs to %LOCALAPPDATA%\Programs\Sloucher.
; Checks the NPU and AMD Ryzen AI Software first, and says plainly what's missing.

#define AppName "Sloucher"
#define AppVersion "0.1.0"
#define AppPublisher "Karthikeyan Umesh"
#define AppURL "https://sloucher.karthikeyanumesh.com"
#define RyzenAIVersion "1.6.1"
#define RyzenAIHelp "https://ryzenai.docs.amd.com/en/latest/inst.html"

[Setup]
AppId={{8B3E2B71-4F0C-4E5B-9C1A-5C7F2D9A6E14}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL={#AppURL}
AppSupportURL={#AppURL}
DefaultDirName={localappdata}\Programs\{#AppName}
DisableProgramGroupPage=yes
DisableDirPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0.22000
OutputDir=..\dist
OutputBaseFilename=SloucherSetup-{#AppVersion}
SetupIconFile=..\src\sloucher\assets\icon.ico
UninstallDisplayIcon={app}\Sloucher.exe
UninstallDisplayName={#AppName}
WizardStyle=modern
Compression=lzma2/ultra64
SolidCompression=yes
LZMAUseSeparateProcess=yes
AppMutex=Local\Sloucher.App
CloseApplications=yes

[Tasks]
Name: "startup"; Description: "Start Sloucher when I sign in to Windows (recommended)"; GroupDescription: "Options:"
Name: "desktopicon"; Description: "Add a desktop shortcut"; GroupDescription: "Options:"; Flags: unchecked

[Files]
Source: "..\dist\Sloucher\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\Sloucher.exe"
Name: "{autoprograms}\{#AppName} - check my laptop"; Filename: "{app}\sloucher-cli.exe"; Parameters: "doctor"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\Sloucher.exe"; Tasks: desktopicon

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "{#AppName}"; \
  ValueData: """{app}\Sloucher.exe"""; Flags: uninsdeletevalue; Tasks: startup

[UninstallDelete]
; Just in case an older NPU runtime wrote bytecode next to the host scripts
Type: filesandordirs; Name: "{app}\_internal\sloucher\npu\__pycache__"

[Run]
Filename: "{app}\Sloucher.exe"; Description: "Start Sloucher now"; Flags: nowait postinstall skipifsilent

[Code]
const
  NpuClass = 'SYSTEM\CurrentControlSet\Control\Class\{f01a9d53-3ff6-48d2-9f97-c8a7004be10c}';

var
  RyzenPage: TOutputMsgWizardPage;

{ The same check the app does: an AMD Phoenix / Hawk Point NPU (PCI VEN_1022 DEV_1502). }
function HasSupportedNpu(): Boolean;
var
  I: Integer;
  Id: String;
begin
  Result := False;
  for I := 0 to 9 do
    if RegQueryStringValue(HKLM, NpuClass + '\' + Format('%.4d', [I]), 'MatchingDeviceId', Id) then
      if Pos('VEN_1022&DEV_1502', Uppercase(Id)) > 0 then
      begin
        Result := True;
        Exit;
      end;
end;

function HasRyzenAI(): Boolean;
begin
  Result := DirExists(ExpandConstant('{commonpf64}\RyzenAI\{#RyzenAIVersion}'));
end;

function InitializeSetup(): Boolean;
begin
  Result := True;
  if not HasSupportedNpu() then
    Result := SuppressibleMsgBox('Sloucher runs on the NPU, and this version supports AMD Ryzen 7040 / 8040 laptops ' +
      '(Phoenix, Hawk Point). This laptop''s NPU wasn''t recognised, so Sloucher will most likely not start.' + #13#10#13#10 +
      'Install anyway?', mbConfirmation, MB_YESNO or MB_DEFBUTTON2, IDNO) = IDYES;
end;

procedure OpenRyzenHelp(Sender: TObject);
var
  Code: Integer;
begin
  ShellExec('open', '{#RyzenAIHelp}', '', '', SW_SHOWNORMAL, ewNoWait, Code);
end;

procedure InitializeWizard();
var
  Button: TNewButton;
begin
  RyzenPage := CreateOutputMsgPage(wpWelcome, 'One thing first: AMD Ryzen AI Software',
    'Sloucher uses AMD''s NPU runtime, which AMD installs separately.',
    'Sloucher couldn''t find AMD Ryzen AI Software {#RyzenAIVersion} on this laptop. It''s a one-time install:' + #13#10#13#10 +
    '1. Open AMD''s install page (button below) and download Ryzen AI Software {#RyzenAIVersion}.' + #13#10 +
    '2. Run AMD''s installer with its default options.' + #13#10 +
    '3. Come back and click Next. Sloucher finds it on its own.' + #13#10#13#10 +
    'You can also install Sloucher now and AMD''s software later: Sloucher will tell you when it''s missing.');
  Button := TNewButton.Create(RyzenPage);
  Button.Parent := RyzenPage.Surface;
  Button.Caption := 'Open AMD''s install page';
  Button.Width := ScaleX(200);
  Button.Height := ScaleY(28);
  Button.Top := RyzenPage.Surface.Height - Button.Height - ScaleY(8);
  Button.OnClick := @OpenRyzenHelp;
end;

function ShouldSkipPage(PageID: Integer): Boolean;
begin
  Result := (PageID = RyzenPage.ID) and HasRyzenAI();
end;

{ Uninstall: also remove the start-with-Windows entry the app itself may have set, and offer to remove your data. }
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if CurUninstallStep = usPostUninstall then
  begin
    RegDeleteValue(HKCU, 'Software\Microsoft\Windows\CurrentVersion\Run', '{#AppName}');
    if DirExists(ExpandConstant('{localappdata}\Sloucher')) then
      if SuppressibleMsgBox('Also remove your Sloucher settings and calibration?', mbConfirmation,
                            MB_YESNO or MB_DEFBUTTON2, IDNO) = IDYES then
        DelTree(ExpandConstant('{localappdata}\Sloucher'), True, True, True);
  end;
end;
