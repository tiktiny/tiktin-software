Unicode true
!include "MUI2.nsh"
; שתי גרסאות מאותו קוד: A = הממשק הקיים, B = הממשק החדש (מותקנות זו לצד זו)
!ifdef VARIANT_B
  !define APPNAME "טיקטין PDF ממשק חדש"
  !define EXE "TiktinPDF-B"
  !define KEY "TiktinPDF-B"
  !define SETUP "TiktinPDF-B-Setup"
  !define ICO "tiktin_pdf_b"
!else
  !define APPNAME "טיקטין PDF"
  !define EXE "TiktinPDF"
  !define KEY "TiktinPDF"
  !define SETUP "TiktinPDF-Setup"
  !define ICO "tiktin_pdf"
!endif
Name "${APPNAME}"
OutFile "${ROOT}/out/${SETUP}.exe"
InstallDir "$LOCALAPPDATA\Programs\${KEY}"
RequestExecutionLevel user
SetCompressor /SOLID lzma
Icon "${ROOT}/out/${ICO}.ico"
!define MUI_ICON "${ROOT}/out/${ICO}.ico"
!define MUI_UNICON "${ROOT}/out/${ICO}.ico"
!define MUI_FINISHPAGE_RUN "$INSTDIR\${EXE}.exe"
!define MUI_FINISHPAGE_RUN_TEXT "הפעלת ${APPNAME}"
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES
!insertmacro MUI_LANGUAGE "Hebrew"
VIProductVersion "${VERSION}.0"
VIAddVersionKey /LANG=${LANG_HEBREW} "ProductName" "Tiktin PDF"
VIAddVersionKey /LANG=${LANG_HEBREW} "FileVersion" "${VERSION}"
VIAddVersionKey /LANG=${LANG_HEBREW} "CompanyName" "Tiktin"
VIAddVersionKey /LANG=${LANG_HEBREW} "FileDescription" "Tiktin PDF Setup"
VIAddVersionKey /LANG=${LANG_HEBREW} "LegalCopyright" "Tiktin"

Section "install"
  nsExec::Exec 'taskkill /F /IM pythonw.exe /FI "MODULES eq Qt6Core.dll"'
  RMDir /r "$INSTDIR\runtime"
  SetOutPath "$INSTDIR"
  File "${ROOT}/out/${EXE}.exe"
  File "${ROOT}/out/${ICO}.ico"
  SetOutPath "$INSTDIR\runtime"
  File /r "${ROOT}/winpy/*.*"
  WriteUninstaller "$INSTDIR\uninstall.exe"
  CreateShortcut "$SMPROGRAMS\${APPNAME}.lnk" "$INSTDIR\${EXE}.exe" "" "$INSTDIR\${ICO}.ico"
  CreateShortcut "$DESKTOP\${APPNAME}.lnk" "$INSTDIR\${EXE}.exe" "" "$INSTDIR\${ICO}.ico"
  ; שיוך לקובצי PDF (פתיחה באמצעות)
  WriteRegStr HKCU "Software\Classes\${KEY}.Document" "" "מסמך PDF"
  WriteRegStr HKCU "Software\Classes\${KEY}.Document\DefaultIcon" "" "$INSTDIR\${ICO}.ico"
  WriteRegStr HKCU "Software\Classes\${KEY}.Document\shell\open\command" "" '"$INSTDIR\${EXE}.exe" "%1"'
  WriteRegStr HKCU "Software\Classes\.pdf\OpenWithProgids" "${KEY}.Document" ""
  WriteRegStr HKCU "Software\Classes\Applications\${EXE}.exe" "FriendlyAppName" "${APPNAME}"
  WriteRegStr HKCU "Software\Classes\Applications\${EXE}.exe\SupportedTypes" ".pdf" ""
  WriteRegStr HKCU "Software\Classes\Applications\${EXE}.exe\shell\open\command" "" '"$INSTDIR\${EXE}.exe" "%1"'
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\${KEY}" "DisplayName" "${APPNAME}"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\${KEY}" "DisplayVersion" "${VERSION}"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\${KEY}" "Publisher" "Tiktin"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\${KEY}" "DisplayIcon" "$INSTDIR\${ICO}.ico"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\${KEY}" "UninstallString" '"$INSTDIR\uninstall.exe"'
  WriteRegDWORD HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\${KEY}" "NoModify" 1
  System::Call 'shell32::SHChangeNotify(i 0x08000000, i 0, p 0, p 0)'
SectionEnd

Section "Uninstall"
  Delete "$SMPROGRAMS\${APPNAME}.lnk"
  Delete "$DESKTOP\${APPNAME}.lnk"
  DeleteRegKey HKCU "Software\Classes\${KEY}.Document"
  DeleteRegValue HKCU "Software\Classes\.pdf\OpenWithProgids" "${KEY}.Document"
  DeleteRegKey HKCU "Software\Classes\Applications\${EXE}.exe"
  DeleteRegKey HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\${KEY}"
  RMDir /r "$INSTDIR"
  System::Call 'shell32::SHChangeNotify(i 0x08000000, i 0, p 0, p 0)'
SectionEnd
