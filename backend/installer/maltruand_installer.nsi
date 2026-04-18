; NSIS-скрипт установщика Scott
; Требуется установленный NSIS (https://nsis.sourceforge.io)

!include "MUI2.nsh"

; --- Общая информация ---
!define APP_NAME       "Scott"
!define APP_VERSION    "1.0.0"
!define APP_PUBLISHER  "SKYNET"

Name "${APP_NAME} ${APP_VERSION}"
OutFile "ScottSetup_${APP_VERSION}.exe"

; Иконка установщика (если есть)
!define MUI_ICON  "..\assets\maltruand.ico"
!define MUI_UNICON "..\assets\maltruand.ico"

; Каталог по умолчанию (пользователь может изменить)
InstallDir "$PROGRAMFILES\Scott"

; --- Страницы мастера ---
!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_LICENSE "..\LICENSE.txt"
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH

!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES

!insertmacro MUI_LANGUAGE "Russian"

; --- Секции ---

Section "Основная программа" SEC_MAIN
  SetOutPath "$INSTDIR"

  ; Копируем уже собранный launcher EXE
  ; Перед сборкой установщика нужно запустить build_launcher_exe.bat
  File "..\dist\ScottLauncher.exe"

  ; Иконка и ассеты (по желанию)
  SetOutPath "$INSTDIR\assets"
  File /nonfatal "..\assets\maltruand.ico"
  File /nonfatal "..\assets\logo.png"

  ; Конфиг по умолчанию (будет перезаписываться самим приложением)
  SetOutPath "$INSTDIR"
  File /nonfatal "..\config.json"

  ; Создаём ярлык на рабочем столе
  SetOutPath "$INSTDIR"
  CreateShortCut "$DESKTOP\Scott.lnk" "$INSTDIR\ScottLauncher.exe" "" "$INSTDIR\assets\maltruand.ico" 0

  ; Запоминаем каталог для деинсталляции
  WriteRegStr HKLM "Software\${APP_NAME}" "InstallDir" "$INSTDIR"

SectionEnd


Section "Удаление"
  ; Читаем путь установки
  ReadRegStr $0 HKLM "Software\${APP_NAME}" "InstallDir"
  StrCmp $0 "" +2 0
    StrCpy $0 "$INSTDIR"

  ; Удаляем файлы
  Delete "$0\ScottLauncher.exe"
  Delete "$0\config.json"
  Delete "$0\assets\maltruand.ico"
  Delete "$0\assets\logo.png"
  RMDir  "$0\assets"

  ; Удаляем ярлык
  Delete "$DESKTOP\Scott.lnk"

  ; Удаляем каталог, если пуст
  RMDir "$0"

  DeleteRegKey HKLM "Software\${APP_NAME}"

SectionEnd


