Unicode true
!include "MUI2.nsh"
Name "TIKTINPDF – גרסה מסחרית"
OutFile "${ROOT}/out/TiktinPDF-Commercial-Setup.exe"
InstallDir "$LOCALAPPDATA\Programs\TiktinPDF-C"
RequestExecutionLevel user
SetCompressor /SOLID lzma
SetCompressorDictSize 64
Icon "${ROOT}/out/tiktin_pdf_c.ico"
!define MUI_ICON "${ROOT}/out/tiktin_pdf_c.ico"
!define MUI_UNICON "${ROOT}/out/tiktin_pdf_c.ico"
!define MUI_FINISHPAGE_RUN "$INSTDIR\TiktinPDF-C.exe"
!define MUI_FINISHPAGE_RUN_TEXT "הפעלת TIKTINPDF גרסה מסחרית"
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES
!insertmacro MUI_LANGUAGE "Hebrew"
VIProductVersion "${VNUM}.0"
VIAddVersionKey /LANG=${LANG_HEBREW} "ProductName" "TIKTINPDF Commercial"
VIAddVersionKey /LANG=${LANG_HEBREW} "FileVersion" "${VERSION}"
VIAddVersionKey /LANG=${LANG_HEBREW} "CompanyName" ""
VIAddVersionKey /LANG=${LANG_HEBREW} "FileDescription" "TIKTINPDF Commercial Setup"
VIAddVersionKey /LANG=${LANG_HEBREW} "LegalCopyright" ""

Section "install"
  nsExec::Exec `powershell -NoProfile -Command "Get-Process pythonw -ErrorAction SilentlyContinue | Where-Object { $$_.Path -like '$INSTDIR\*' } | Stop-Process -Force"`
  RMDir /r "$INSTDIR\runtime"
  SetOutPath "$INSTDIR"
  File "${ROOT}/out/TiktinPDF-C.exe"
  File "${ROOT}/out/tiktin_pdf_c.ico"
  SetOutPath "$INSTDIR\runtime"
  File /r "${ROOT}/winpy_c/*.*"
  WriteUninstaller "$INSTDIR\uninstall.exe"
  CreateShortcut "$SMPROGRAMS\TIKTINPDF גרסה מסחרית.lnk" "$INSTDIR\TiktinPDF-C.exe" "" "$INSTDIR\tiktin_pdf_c.ico"
  CreateShortcut "$DESKTOP\TIKTINPDF גרסה מסחרית.lnk" "$INSTDIR\TiktinPDF-C.exe" "" "$INSTDIR\tiktin_pdf_c.ico"
  ; שיוך לקובצי PDF (פתיחה באמצעות)
  WriteRegStr HKCU "Software\Classes\TiktinPDF-C.Document" "" "מסמך PDF (TIKTINPDF מסחרית)"
  WriteRegStr HKCU "Software\Classes\TiktinPDF-C.Document\DefaultIcon" "" "$INSTDIR\tiktin_pdf_c.ico"
  WriteRegStr HKCU "Software\Classes\TiktinPDF-C.Document\shell\open\command" "" '"$INSTDIR\TiktinPDF-C.exe" "%1"'
  WriteRegStr HKCU "Software\Classes\.pdf\OpenWithProgids" "TiktinPDF-C.Document" ""
  WriteRegStr HKCU "Software\Classes\Applications\TiktinPDF-C.exe" "FriendlyAppName" "TIKTINPDF גרסה מסחרית"
  WriteRegStr HKCU "Software\Classes\Applications\TiktinPDF-C.exe\SupportedTypes" ".pdf" ""
  ; תמונות: "פתיחה באמצעות" — התמונה מומרת ל-PDF
  WriteRegStr HKCU "Software\Classes\.png\OpenWithProgids" "TiktinPDF-C.Document" ""
  WriteRegStr HKCU "Software\Classes\Applications\TiktinPDF-C.exe\SupportedTypes" ".png" ""
  WriteRegStr HKCU "Software\Classes\.jpg\OpenWithProgids" "TiktinPDF-C.Document" ""
  WriteRegStr HKCU "Software\Classes\Applications\TiktinPDF-C.exe\SupportedTypes" ".jpg" ""
  WriteRegStr HKCU "Software\Classes\.jpeg\OpenWithProgids" "TiktinPDF-C.Document" ""
  WriteRegStr HKCU "Software\Classes\Applications\TiktinPDF-C.exe\SupportedTypes" ".jpeg" ""
  WriteRegStr HKCU "Software\Classes\.jfif\OpenWithProgids" "TiktinPDF-C.Document" ""
  WriteRegStr HKCU "Software\Classes\Applications\TiktinPDF-C.exe\SupportedTypes" ".jfif" ""
  WriteRegStr HKCU "Software\Classes\.bmp\OpenWithProgids" "TiktinPDF-C.Document" ""
  WriteRegStr HKCU "Software\Classes\Applications\TiktinPDF-C.exe\SupportedTypes" ".bmp" ""
  WriteRegStr HKCU "Software\Classes\.gif\OpenWithProgids" "TiktinPDF-C.Document" ""
  WriteRegStr HKCU "Software\Classes\Applications\TiktinPDF-C.exe\SupportedTypes" ".gif" ""
  WriteRegStr HKCU "Software\Classes\.tif\OpenWithProgids" "TiktinPDF-C.Document" ""
  WriteRegStr HKCU "Software\Classes\Applications\TiktinPDF-C.exe\SupportedTypes" ".tif" ""
  WriteRegStr HKCU "Software\Classes\.tiff\OpenWithProgids" "TiktinPDF-C.Document" ""
  WriteRegStr HKCU "Software\Classes\Applications\TiktinPDF-C.exe\SupportedTypes" ".tiff" ""
  WriteRegStr HKCU "Software\Classes\.webp\OpenWithProgids" "TiktinPDF-C.Document" ""
  WriteRegStr HKCU "Software\Classes\Applications\TiktinPDF-C.exe\SupportedTypes" ".webp" ""
  WriteRegStr HKCU "Software\Classes\Applications\TiktinPDF-C.exe\shell\open\command" "" '"$INSTDIR\TiktinPDF-C.exe" "%1"'
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\TiktinPDF-C" "DisplayName" "TIKTINPDF – גרסה מסחרית"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\TiktinPDF-C" "DisplayVersion" "${VERSION}"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\TiktinPDF-C" "Publisher" ""
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\TiktinPDF-C" "DisplayIcon" "$INSTDIR\tiktin_pdf_c.ico"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\TiktinPDF-C" "UninstallString" '"$INSTDIR\uninstall.exe"'
  WriteRegDWORD HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\TiktinPDF-C" "NoModify" 1
  System::Call 'shell32::SHChangeNotify(i 0x08000000, i 0, p 0, p 0)'
SectionEnd

Section "Uninstall"
  Delete "$SMPROGRAMS\TIKTINPDF גרסה מסחרית.lnk"
  Delete "$DESKTOP\TIKTINPDF גרסה מסחרית.lnk"
  DeleteRegKey HKCU "Software\Classes\TiktinPDF-C.Document"
  DeleteRegValue HKCU "Software\Classes\.pdf\OpenWithProgids" "TiktinPDF-C.Document"
  DeleteRegValue HKCU "Software\Classes\.png\OpenWithProgids" "TiktinPDF-C.Document"
  DeleteRegValue HKCU "Software\Classes\.jpg\OpenWithProgids" "TiktinPDF-C.Document"
  DeleteRegValue HKCU "Software\Classes\.jpeg\OpenWithProgids" "TiktinPDF-C.Document"
  DeleteRegValue HKCU "Software\Classes\.jfif\OpenWithProgids" "TiktinPDF-C.Document"
  DeleteRegValue HKCU "Software\Classes\.bmp\OpenWithProgids" "TiktinPDF-C.Document"
  DeleteRegValue HKCU "Software\Classes\.gif\OpenWithProgids" "TiktinPDF-C.Document"
  DeleteRegValue HKCU "Software\Classes\.tif\OpenWithProgids" "TiktinPDF-C.Document"
  DeleteRegValue HKCU "Software\Classes\.tiff\OpenWithProgids" "TiktinPDF-C.Document"
  DeleteRegValue HKCU "Software\Classes\.webp\OpenWithProgids" "TiktinPDF-C.Document"
  DeleteRegKey HKCU "Software\Classes\Applications\TiktinPDF-C.exe"
  DeleteRegKey HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\TiktinPDF-C"
  RMDir /r "$INSTDIR"
  System::Call 'shell32::SHChangeNotify(i 0x08000000, i 0, p 0, p 0)'
SectionEnd
