Unicode true
SilentInstall silent
RequestExecutionLevel user
Name "TIKTINPDF Commercial"
OutFile "${ROOT}/out/TiktinPDF-C.exe"
Icon "${ROOT}/out/tiktin_pdf_c.ico"
VIProductVersion "${VNUM}.0"
VIAddVersionKey "ProductName" "TIKTINPDF Commercial"
VIAddVersionKey "FileDescription" "TIKTINPDF Commercial"
VIAddVersionKey "FileVersion" "${VERSION}"
VIAddVersionKey "CompanyName" ""
VIAddVersionKey "LegalCopyright" ""
!include "FileFunc.nsh"
Section
  ${GetParameters} $0
  Exec '"$EXEDIR\runtime\pythonw.exe" "$EXEDIR\runtime\app\tiktin_pdf.py" $0'
SectionEnd
