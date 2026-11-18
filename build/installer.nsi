Unicode true
!include "MUI2.nsh"
Name "טיקטין PDF A"
OutFile "${ROOT}/out/TiktinPDF-Setup-A.exe"
InstallDir "$LOCALAPPDATA\Programs\TiktinPDF-A"
RequestExecutionLevel user
SetCompressor /SOLID lzma
SetCompressorDictSize 64
Icon "${ROOT}/out/tiktin_pdf.ico"
!define MUI_ICON "${ROOT}/out/tiktin_pdf.ico"
!define MUI_UNICON "${ROOT}/out/tiktin_pdf.ico"
!define MUI_FINISHPAGE_RUN "$INSTDIR\TiktinPDF-A.exe"
!define MUI_FINISHPAGE_RUN_TEXT "הפעלת טיקטין PDF A"
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES
!insertmacro MUI_LANGUAGE "Hebrew"
VIProductVersion "${VNUM}.0"
VIAddVersionKey /LANG=${LANG_HEBREW} "ProductName" "Tiktin PDF"
VIAddVersionKey /LANG=${LANG_HEBREW} "FileVersion" "${VERSION}"
VIAddVersionKey /LANG=${LANG_HEBREW} "CompanyName" "Tiktin"
VIAddVersionKey /LANG=${LANG_HEBREW} "FileDescription" "Tiktin PDF Setup"
VIAddVersionKey /LANG=${LANG_HEBREW} "LegalCopyright" "Tiktin"

Section "install"
  nsExec::Exec `powershell -NoProfile -Command "Get-Process pythonw -ErrorAction SilentlyContinue | Where-Object { $$_.Path -like '$INSTDIR\*' } | Stop-Process -Force"`
  RMDir /r "$INSTDIR\runtime"
  SetOutPath "$INSTDIR"
  File "${ROOT}/out/TiktinPDF-A.exe"
  File "${ROOT}/out/tiktin_pdf.ico"
  SetOutPath "$INSTDIR\runtime"
  File /r "${ROOT}/winpy/*.*"
  WriteUninstaller "$INSTDIR\uninstall.exe"
  CreateShortcut "$SMPROGRAMS\טיקטין PDF A.lnk" "$INSTDIR\TiktinPDF-A.exe" "" "$INSTDIR\tiktin_pdf.ico"
  CreateShortcut "$DESKTOP\טיקטין PDF A.lnk" "$INSTDIR\TiktinPDF-A.exe" "" "$INSTDIR\tiktin_pdf.ico"
  ; "חותמת אוטומטית" היא עכשיו תוכנה נפרדת עם התקנה משלה — מסירים את מה שגרסה A1.11.0 התקינה כאן
  Delete "$INSTDIR\TiktinBoardStamp.exe"
  Delete "$INSTDIR\tiktin_stamp.ico"
  Delete "$SMPROGRAMS\חותמת לוחות אוטומטית – טיקטין.lnk"
  Delete "$DESKTOP\חותמת לוחות אוטומטית – טיקטין.lnk"
  DeleteRegKey HKCU "Software\Classes\SystemFileAssociations\.pdf\shell\TiktinBoardStamp"
  ; שיוך לקובצי PDF (פתיחה באמצעות)
  WriteRegStr HKCU "Software\Classes\TiktinPDF-A.Document" "" "מסמך PDF (טיקטין A)"
  WriteRegStr HKCU "Software\Classes\TiktinPDF-A.Document\DefaultIcon" "" "$INSTDIR\tiktin_pdf.ico"
  WriteRegStr HKCU "Software\Classes\TiktinPDF-A.Document\shell\open\command" "" '"$INSTDIR\TiktinPDF-A.exe" "%1"'
  WriteRegStr HKCU "Software\Classes\.pdf\OpenWithProgids" "TiktinPDF-A.Document" ""
  WriteRegStr HKCU "Software\Classes\Applications\TiktinPDF-A.exe" "FriendlyAppName" "טיקטין PDF A"
  WriteRegStr HKCU "Software\Classes\Applications\TiktinPDF-A.exe\SupportedTypes" ".pdf" ""
  ; תמונות: "פתיחה באמצעות" טיקטין PDF — התמונה מומרת ל-PDF
  WriteRegStr HKCU "Software\Classes\.png\OpenWithProgids" "TiktinPDF-A.Document" ""
  WriteRegStr HKCU "Software\Classes\Applications\TiktinPDF-A.exe\SupportedTypes" ".png" ""
  WriteRegStr HKCU "Software\Classes\.jpg\OpenWithProgids" "TiktinPDF-A.Document" ""
  WriteRegStr HKCU "Software\Classes\Applications\TiktinPDF-A.exe\SupportedTypes" ".jpg" ""
  WriteRegStr HKCU "Software\Classes\.jpeg\OpenWithProgids" "TiktinPDF-A.Document" ""
  WriteRegStr HKCU "Software\Classes\Applications\TiktinPDF-A.exe\SupportedTypes" ".jpeg" ""
  WriteRegStr HKCU "Software\Classes\.jfif\OpenWithProgids" "TiktinPDF-A.Document" ""
  WriteRegStr HKCU "Software\Classes\Applications\TiktinPDF-A.exe\SupportedTypes" ".jfif" ""
  WriteRegStr HKCU "Software\Classes\.bmp\OpenWithProgids" "TiktinPDF-A.Document" ""
  WriteRegStr HKCU "Software\Classes\Applications\TiktinPDF-A.exe\SupportedTypes" ".bmp" ""
  WriteRegStr HKCU "Software\Classes\.gif\OpenWithProgids" "TiktinPDF-A.Document" ""
  WriteRegStr HKCU "Software\Classes\Applications\TiktinPDF-A.exe\SupportedTypes" ".gif" ""
  WriteRegStr HKCU "Software\Classes\.tif\OpenWithProgids" "TiktinPDF-A.Document" ""
  WriteRegStr HKCU "Software\Classes\Applications\TiktinPDF-A.exe\SupportedTypes" ".tif" ""
  WriteRegStr HKCU "Software\Classes\.tiff\OpenWithProgids" "TiktinPDF-A.Document" ""
  WriteRegStr HKCU "Software\Classes\Applications\TiktinPDF-A.exe\SupportedTypes" ".tiff" ""
  WriteRegStr HKCU "Software\Classes\.webp\OpenWithProgids" "TiktinPDF-A.Document" ""
  WriteRegStr HKCU "Software\Classes\Applications\TiktinPDF-A.exe\SupportedTypes" ".webp" ""
  WriteRegStr HKCU "Software\Classes\Applications\TiktinPDF-A.exe\shell\open\command" "" '"$INSTDIR\TiktinPDF-A.exe" "%1"'
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\TiktinPDF-A" "DisplayName" "טיקטין PDF A"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\TiktinPDF-A" "DisplayVersion" "${VERSION}"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\TiktinPDF-A" "Publisher" "Tiktin"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\TiktinPDF-A" "DisplayIcon" "$INSTDIR\tiktin_pdf.ico"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\TiktinPDF-A" "UninstallString" '"$INSTDIR\uninstall.exe"'
  WriteRegDWORD HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\TiktinPDF-A" "NoModify" 1
  System::Call 'shell32::SHChangeNotify(i 0x08000000, i 0, p 0, p 0)'
SectionEnd

Section "Uninstall"
  Delete "$SMPROGRAMS\טיקטין PDF A.lnk"
  Delete "$DESKTOP\טיקטין PDF A.lnk"
  Delete "$SMPROGRAMS\חותמת לוחות אוטומטית – טיקטין.lnk"
  Delete "$DESKTOP\חותמת לוחות אוטומטית – טיקטין.lnk"
  DeleteRegKey HKCU "Software\Classes\SystemFileAssociations\.pdf\shell\TiktinBoardStamp"
  DeleteRegKey HKCU "Software\Classes\TiktinPDF-A.Document"
  DeleteRegValue HKCU "Software\Classes\.pdf\OpenWithProgids" "TiktinPDF-A.Document"
  DeleteRegValue HKCU "Software\Classes\.png\OpenWithProgids" "TiktinPDF-A.Document"
  DeleteRegValue HKCU "Software\Classes\.jpg\OpenWithProgids" "TiktinPDF-A.Document"
  DeleteRegValue HKCU "Software\Classes\.jpeg\OpenWithProgids" "TiktinPDF-A.Document"
  DeleteRegValue HKCU "Software\Classes\.jfif\OpenWithProgids" "TiktinPDF-A.Document"
  DeleteRegValue HKCU "Software\Classes\.bmp\OpenWithProgids" "TiktinPDF-A.Document"
  DeleteRegValue HKCU "Software\Classes\.gif\OpenWithProgids" "TiktinPDF-A.Document"
  DeleteRegValue HKCU "Software\Classes\.tif\OpenWithProgids" "TiktinPDF-A.Document"
  DeleteRegValue HKCU "Software\Classes\.tiff\OpenWithProgids" "TiktinPDF-A.Document"
  DeleteRegValue HKCU "Software\Classes\.webp\OpenWithProgids" "TiktinPDF-A.Document"
  DeleteRegKey HKCU "Software\Classes\Applications\TiktinPDF-A.exe"
  DeleteRegKey HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\TiktinPDF-A"
  RMDir /r "$INSTDIR"
  System::Call 'shell32::SHChangeNotify(i 0x08000000, i 0, p 0, p 0)'
SectionEnd
