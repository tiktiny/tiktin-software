Unicode true
!include "MUI2.nsh"
Name "טיקטין PDF"
OutFile "${ROOT}/out/TiktinPDF-Setup.exe"
InstallDir "$LOCALAPPDATA\Programs\TiktinPDF"
RequestExecutionLevel user
SetCompressor /SOLID lzma
Icon "${ROOT}/out/tiktin_pdf.ico"
!define MUI_ICON "${ROOT}/out/tiktin_pdf.ico"
!define MUI_UNICON "${ROOT}/out/tiktin_pdf.ico"
!define MUI_FINISHPAGE_RUN "$INSTDIR\TiktinPDF.exe"
!define MUI_FINISHPAGE_RUN_TEXT "הפעלת טיקטין PDF"
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
  File "${ROOT}/out/TiktinPDF.exe"
  File "${ROOT}/out/tiktin_pdf.ico"
  SetOutPath "$INSTDIR\runtime"
  File /r "${ROOT}/winpy/*.*"
  WriteUninstaller "$INSTDIR\uninstall.exe"
  CreateShortcut "$SMPROGRAMS\טיקטין PDF.lnk" "$INSTDIR\TiktinPDF.exe" "" "$INSTDIR\tiktin_pdf.ico"
  CreateShortcut "$DESKTOP\טיקטין PDF.lnk" "$INSTDIR\TiktinPDF.exe" "" "$INSTDIR\tiktin_pdf.ico"
  ; שיוך לקובצי PDF (פתיחה באמצעות)
  WriteRegStr HKCU "Software\Classes\TiktinPDF.Document" "" "מסמך PDF"
  WriteRegStr HKCU "Software\Classes\TiktinPDF.Document\DefaultIcon" "" "$INSTDIR\tiktin_pdf.ico"
  WriteRegStr HKCU "Software\Classes\TiktinPDF.Document\shell\open\command" "" '"$INSTDIR\TiktinPDF.exe" "%1"'
  WriteRegStr HKCU "Software\Classes\.pdf\OpenWithProgids" "TiktinPDF.Document" ""
  WriteRegStr HKCU "Software\Classes\Applications\TiktinPDF.exe" "FriendlyAppName" "טיקטין PDF"
  WriteRegStr HKCU "Software\Classes\Applications\TiktinPDF.exe\SupportedTypes" ".pdf" ""
  WriteRegStr HKCU "Software\Classes\Applications\TiktinPDF.exe\shell\open\command" "" '"$INSTDIR\TiktinPDF.exe" "%1"'
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\TiktinPDF" "DisplayName" "טיקטין PDF"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\TiktinPDF" "DisplayVersion" "${VERSION}"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\TiktinPDF" "Publisher" "Tiktin"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\TiktinPDF" "DisplayIcon" "$INSTDIR\tiktin_pdf.ico"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\TiktinPDF" "UninstallString" '"$INSTDIR\uninstall.exe"'
  WriteRegDWORD HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\TiktinPDF" "NoModify" 1
  System::Call 'shell32::SHChangeNotify(i 0x08000000, i 0, p 0, p 0)'
SectionEnd

Section "Uninstall"
  Delete "$SMPROGRAMS\טיקטין PDF.lnk"
  Delete "$DESKTOP\טיקטין PDF.lnk"
  DeleteRegKey HKCU "Software\Classes\TiktinPDF.Document"
  DeleteRegValue HKCU "Software\Classes\.pdf\OpenWithProgids" "TiktinPDF.Document"
  DeleteRegKey HKCU "Software\Classes\Applications\TiktinPDF.exe"
  DeleteRegKey HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\TiktinPDF"
  RMDir /r "$INSTDIR"
  System::Call 'shell32::SHChangeNotify(i 0x08000000, i 0, p 0, p 0)'
SectionEnd
