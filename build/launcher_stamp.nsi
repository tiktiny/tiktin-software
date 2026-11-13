Unicode true
SilentInstall silent
RequestExecutionLevel user
Name "Tiktin Board Stamp"
OutFile "${ROOT}/out/TiktinBoardStamp.exe"
Icon "${ROOT}/out/tiktin_stamp.ico"
VIProductVersion "${VNUM}.0"
VIAddVersionKey "ProductName" "Tiktin PDF"
VIAddVersionKey "FileDescription" "Tiktin Board Stamp"
VIAddVersionKey "FileVersion" "${VERSION}"
VIAddVersionKey "CompanyName" "Tiktin"
VIAddVersionKey "LegalCopyright" "Tiktin"
!include "FileFunc.nsh"
Section
  ${GetParameters} $0
  Exec '"$EXEDIR\runtime\pythonw.exe" "$EXEDIR\runtime\app\tiktin_stamp.py" $0'
SectionEnd
