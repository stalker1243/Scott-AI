; Установщик Scott AI.
;
; Собирается из installer/dist — папки, которую готовит build.py: встроенный
; Python, backend и лаунчер (self-contained, .NET у человека не нужен).
; Тяжёлого здесь нет: torch и модели речи ставятся при первом запуске, когда
; уже известно, есть ли в машине видеокарта NVIDIA.
;
; Версия и путь к dist передаются снаружи, из build.py:
;   ISCC.exe /DAppVersion=1.0.0 /DDistDir=...\dist installer\scott.iss

#ifndef AppVersion
  #define AppVersion "1.0.0"
#endif

#ifndef DistDir
  #define DistDir "dist"
#endif

#ifndef OutputDir
  #define OutputDir "release"
#endif

#define AppName "Scott AI"
#define AppPublisher "Scott AI"
#define AppExe "ScottAI.exe"

[Setup]
AppId={{8F3C5A21-6B4D-4E7A-9C12-5D8E3F1A7B60}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher={#AppPublisher}
DefaultDirName={autopf}\ScottAI
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
OutputDir={#OutputDir}
OutputBaseFilename=ScottAI-{#AppVersion}-setup
SetupIconFile=..\ScottAI_avalonia\Assets\scott.ico
UninstallDisplayIcon={app}\launcher\{#AppExe}
UninstallDisplayName={#AppName}
WizardStyle=modern
Compression=lzma2/max
SolidCompression=yes

; Место под то, что докачается при первом запуске: сборка torch под видеокарту
; (~4 ГБ) плюс модели речи (~1.5 ГБ). Без этой поправки установщик обещал бы
; 230 МБ — столько занимает сама программа, — и человек с почти полным диском
; узнал бы правду уже посреди загрузки.
ExtraDiskSpaceRequired=5368709120

; Ставим без прав администратора, в папку пользователя. Программа пишет рядом
; с собой — логи, кэш речи, настройки backend, — и в Program Files это
; упиралось бы в права. Заодно человеку не нужно объяснять запрос UAC.
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog

; Закрывать программы, которые держат наши файлы. Само по себе это не
; помогает против backend (у него нет окна), поэтому есть ещё и PrepareToInstall
; ниже — но с этим флагом Windows хотя бы корректно закроет само окно лаунчера.
CloseApplications=force
RestartApplications=no

; Встроенный Python и .NET-сборка лаунчера — 64-битные.
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

; Windows 10 и новее: Avalonia и встроенный Python 3.13 старее не поддерживают.
MinVersion=10.0

[Languages]
Name: "russian"; MessagesFile: "compiler:Languages\Russian.isl"

[Tasks]
; Ярлыки — раздельными галочками, включая меню «Пуск». Раньше он создавался
; всегда, без спроса: человек, которому нужен только ярлык на столе, всё равно
; получал запись в меню.
Name: "startmenuicon"; Description: "В меню «Пуск»"; GroupDescription: "Ярлыки:"
Name: "desktopicon"; Description: "На рабочем столе"; GroupDescription: "Ярлыки:"

; Автозапуск снят по умолчанию намеренно: Scott поднимает распознавание речи и
; занимает видеокарту, и решать, нужно ли это при каждом входе в Windows,
; должен человек, а не установщик.
Name: "autostart"; Description: "Запускать Scott при входе в Windows"; GroupDescription: "Дополнительно:"; Flags: unchecked

[InstallDelete]
; Лаунчер раньше назывался ScottAI.Avalonia.exe. При обновлении поверх Inno
; Setup оставил бы старый файл рядом с новым — в папке лежали бы две программы,
; и ярлык из прошлой установки вёл бы на старую.
Type: files; Name: "{app}\launcher\ScottAI.Avalonia.exe"
Type: files; Name: "{app}\launcher\ScottAI.Avalonia.pdb"

[Files]
Source: "{#DistDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\launcher\{#AppExe}"; Tasks: startmenuicon
Name: "{group}\Удалить {#AppName}"; Filename: "{uninstallexe}"; Tasks: startmenuicon
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\launcher\{#AppExe}"; Tasks: desktopicon
Name: "{userstartup}\{#AppName}"; Filename: "{app}\launcher\{#AppExe}"; Tasks: autostart

[Run]
Filename: "{app}\launcher\{#AppExe}"; Description: "Запустить {#AppName}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Всё, что программа создаёт во время работы: логи, кэш синтезированной речи,
; данные backend. Без этого после удаления остаётся папка с мусором.
;
; Отдельно — библиотеки, которые ставит мастер первого запуска. Их здесь не
; было при установке, поэтому сам Inno Setup их не удалит: проверено живьём —
; после удаления оставалось около четырёх гигабайт в site-packages.
Type: filesandordirs; Name: "{app}\runtime\Lib\site-packages"
Type: filesandordirs; Name: "{app}\runtime\Scripts"
Type: filesandordirs; Name: "{app}\backend\logs"
Type: filesandordirs; Name: "{app}\backend\data"
Type: filesandordirs; Name: "{app}\backend\__pycache__"
Type: filesandordirs; Name: "{app}\audio_cache"
Type: filesandordirs; Name: "{app}\logs"
Type: filesandordirs; Name: "{app}\reports"

[Messages]
russian.WelcomeLabel2=Будет установлен [name/ver].%n%nПри первом запуске Scott докачает библиотеки для распознавания речи и модели — от 1 до 4 ГБ в зависимости от того, есть ли в компьютере видеокарта NVIDIA. Понадобится интернет.

[Code]
// Закрыть работающий Scott перед обновлением.
//
// Штатный механизм Windows (RestartManager) справляется с окном лаунчера, но
// не с backend: это python.exe без окна, и закрывать его некому. Из-за этого
// обновление поверх упиралось в «не удалось автоматически закрыть все
// приложения».
//
// Python гасится не любой, а только запущенный из папки программы — иначе
// установщик убил бы чужие процессы, к Scott отношения не имеющие.
procedure StopRunningScott;
var
  ResultCode: Integer;
  Script: String;
begin
  // Двойных кавычек в команде нет намеренно: она сама передаётся в кавычках,
  // и вложенные разорвали бы её. Поэтому вместо -Filter используется
  // Where-Object с одинарными кавычками.
  Script :=
    'Get-Process -Name ''ScottAI'',''ScottAI.Avalonia'' -ErrorAction SilentlyContinue | ' +
    'Stop-Process -Force -ErrorAction SilentlyContinue; ' +
    'Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | ' +
    'Where-Object { $_.Name -eq ''python.exe'' -and $_.ExecutablePath -like ''' +
    ExpandConstant('{app}') + '\*'' } | ' +
    'ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }';

  Exec('powershell.exe',
       '-NoProfile -NonInteractive -WindowStyle Hidden -Command "' + Script + '"',
       '', SW_HIDE, ewWaitUntilTerminated, ResultCode);

  // Секунда на то, чтобы система освободила файлы: сразу после Stop-Process
  // они ещё могут быть заняты.
  Sleep(1200);
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
begin
  StopRunningScott();
  Result := '';
end;

// Модели распознавания и синтеза речи весят около полутора гигабайт и лежат
// в общем кэше PyTorch (%USERPROFILE%\.cache), а не в папке программы. Их
// могут использовать другие программы на том же PyTorch, поэтому удаление —
// отдельный вопрос человеку, а не молчаливое действие.
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  CachePath: String;
begin
  if CurUninstallStep = usPostUninstall then
  begin
    CachePath := ExpandConstant('{%USERPROFILE}') + '\.cache';

    // В тихом режиме диалоги подавляются, и Inno отвечает на них утвердительно
    // сам — проверено живьём: при /VERYSILENT /SUPPRESSMSGBOXES общий кэш
    // моделей стирался молча, хотя человека никто не спрашивал. Чужое добро
    // без спроса не трогаем: удаляем, только когда есть кому ответить.
    if (not UninstallSilent) and
       (DirExists(CachePath + '\whisper') or DirExists(CachePath + '\torch')) then
    begin
      if MsgBox('Удалить также скачанные модели речи (около 1.5 ГБ)?' + #13#10 + #13#10 +
                'Они лежат в общем кэше PyTorch и могут использоваться другими программами. ' +
                'Если сомневаетесь — оставьте: при повторной установке Scott не будет качать их заново.',
                mbConfirmation, MB_YESNO) = IDYES then
      begin
        DelTree(CachePath + '\whisper', True, True, True);
        DelTree(CachePath + '\torch\hub\snakers4_silero-models_master', True, True, True);
      end;
    end;
  end;
end;
