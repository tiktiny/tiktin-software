Unicode true
!ifdef VARIANT_B
  !define EXE "TiktinPDF-B"
!else
  !define EXE "TiktinPDF"
!endif
SilentInstall silent
RequestExecutionLevel user
Name "Tiktin PDF"
OutFile "${ROOT}/out/${EXE}.exe"
Icon "${ROOT}/out/tiktin_pdf.ico"
VIProductVersion "${VERSION}.0"
VIAddVersionKey "ProductName" "Tiktin PDF"
VIAddVersionKey "FileDescription" "Tiktin PDF"
VIAddVersionKey "FileVersion" "${VERSION}"
VIAddVersionKey "CompanyName" "Tiktin"
VIAddVersionKey "LegalCopyright" "Tiktin"
!include "FileFunc.nsh"
Section
  ${GetParameters} $0
  Exec '"$EXEDIR\runtime\pythonw.exe" "$EXEDIR\runtime\app\tiktin_pdf.py" $0'
SectionEnd
