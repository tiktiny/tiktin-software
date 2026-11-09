Unicode true
!ifdef VARIANT_B
  !define EXE "TiktinPDF-B"
  !define ICO "tiktin_pdf_b"
!else
  !define EXE "TiktinPDF"
  !define ICO "tiktin_pdf"
!endif
SilentInstall silent
RequestExecutionLevel user
Name "Tiktin PDF"
OutFile "${ROOT}/out/${EXE}.exe"
Icon "${ROOT}/out/${ICO}.ico"
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
