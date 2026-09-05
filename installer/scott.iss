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
#define AppExe "ScottAI.Avalonia.exe"

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

; Ставим без прав администратора, в папку пользователя. Программа пишет рядом
; с собой — логи, кэш речи, настройки backend, — и в Program Files это
; упиралось бы в права. Заодно человеку не нужно объяснять запрос UAC.
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog

; Встроенный Python и .NET-сборка лаунчера — 64-битные.
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

; Windows 10 и новее: Avalonia и встроенный Python 3.13 старее не поддерживают.
MinVersion=10.0

[Languages]
Name: "russian"; MessagesFile: "compiler:Languages\Russian.isl"

[Tasks]
Name: "desktopicon"; Description: "Создать ярлык на рабочем столе"; GroupDescription: "Ярлыки:"
Name: "autostart"; Description: "Запускать Scott при входе в Windows"; GroupDescription: "Автозапуск:"; Flags: unchecked

[Files]
Source: "{#DistDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\launcher\{#AppExe}"
Name: "{group}\Удалить {#AppName}"; Filename: "{uninstallexe}"
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
