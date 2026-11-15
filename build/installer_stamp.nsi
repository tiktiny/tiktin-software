Unicode true
!include "MUI2.nsh"
Name "חותמת אוטומטית – טיקטין"
OutFile "${ROOT}/out/TiktinStamp-Setup.exe"
InstallDir "$LOCALAPPDATA\Programs\TiktinStamp"
RequestExecutionLevel user
SetCompressor /SOLID lzma
SetCompressorDictSize 64
Icon "${ROOT}/out/tiktin_stamp.ico"
!define MUI_ICON "${ROOT}/out/tiktin_stamp.ico"
!define MUI_UNICON "${ROOT}/out/tiktin_stamp.ico"
!define MUI_FINISHPAGE_RUN "$INSTDIR\TiktinStamp.exe"
!define MUI_FINISHPAGE_RUN_TEXT "הפעלת חותמת אוטומטית"
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES
!insertmacro MUI_LANGUAGE "Hebrew"
VIProductVersion "${VNUM}.0"
VIAddVersionKey /LANG=${LANG_HEBREW} "ProductName" "Tiktin Auto Stamp"
VIAddVersionKey /LANG=${LANG_HEBREW} "FileVersion" "${VNUM}"
VIAddVersionKey /LANG=${LANG_HEBREW} "CompanyName" "Tiktin"
VIAddVersionKey /LANG=${LANG_HEBREW} "FileDescription" "Tiktin Auto Stamp Setup"
VIAddVersionKey /LANG=${LANG_HEBREW} "LegalCopyright" "Tiktin"

Section "install"
  ; סוגר את התוכנה הזו בלבד אם היא פתוחה (לא נוגע בטיקטין PDF)
  nsExec::Exec `powershell -NoProfile -Command "Get-Process pythonw -ErrorAction SilentlyContinue | Where-Object { $$_.Path -like '$INSTDIR\*' } | Stop-Process -Force"`
  RMDir /r "$INSTDIR\runtime"
  SetOutPath "$INSTDIR"
  File "${ROOT}/out/TiktinStamp.exe"
  File "${ROOT}/out/tiktin_stamp.ico"
  SetOutPath "$INSTDIR\runtime"
  File /r "${ROOT}/winpy/*.*"
  WriteUninstaller "$INSTDIR\uninstall.exe"
  CreateShortcut "$SMPROGRAMS\חותמת אוטומטית – טיקטין.lnk" "$INSTDIR\TiktinStamp.exe" "" "$INSTDIR\tiktin_stamp.ico"
  CreateShortcut "$DESKTOP\חותמת אוטומטית – טיקטין.lnk" "$INSTDIR\TiktinStamp.exe" "" "$INSTDIR\tiktin_stamp.ico"
  ; לחצן ימני על קובץ PDF
  WriteRegStr HKCU "Software\Classes\SystemFileAssociations\.pdf\shell\TiktinStamp" "" "הטבעת חותמת בכל העמודים – טיקטין"
  WriteRegStr HKCU "Software\Classes\SystemFileAssociations\.pdf\shell\TiktinStamp" "Icon" "$INSTDIR\tiktin_stamp.ico"
  WriteRegStr HKCU "Software\Classes\SystemFileAssociations\.pdf\shell\TiktinStamp\command" "" '"$INSTDIR\TiktinStamp.exe" "%1"'
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\TiktinStamp" "DisplayName" "חותמת אוטומטית – טיקטין"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\TiktinStamp" "DisplayVersion" "${VNUM}"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\TiktinStamp" "Publisher" "Tiktin"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\TiktinStamp" "DisplayIcon" "$INSTDIR\tiktin_stamp.ico"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\TiktinStamp" "UninstallString" '"$INSTDIR\uninstall.exe"'
  WriteRegDWORD HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\TiktinStamp" "NoModify" 1
  System::Call 'shell32::SHChangeNotify(i 0x08000000, i 0, p 0, p 0)'
SectionEnd

Section "Uninstall"
  Delete "$SMPROGRAMS\חותמת אוטומטית – טיקטין.lnk"
  Delete "$DESKTOP\חותמת אוטומטית – טיקטין.lnk"
  DeleteRegKey HKCU "Software\Classes\SystemFileAssociations\.pdf\shell\TiktinStamp"
  DeleteRegKey HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\TiktinStamp"
  RMDir /r "$INSTDIR"
  System::Call 'shell32::SHChangeNotify(i 0x08000000, i 0, p 0, p 0)'
SectionEnd
