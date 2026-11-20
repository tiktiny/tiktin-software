#!/usr/bin/env bash
# בניית קובץ ההתקנה של טיקטין PDF ל-Windows (רץ ב-GitHub Actions על Linux)
set -euo pipefail
ROOT="$(pwd)"
VER="$(sed -n 1p VERSION)"; DATE="$(sed -n 2p VERSION)"; VNUM="$VER"
sudo apt-get update -qq && sudo apt-get install -y -qq nsis >/dev/null
python -m pip install -q pillow
curl -sL -o mm https://github.com/mamba-org/micromamba-releases/releases/latest/download/micromamba-linux-64
chmod +x mm
export MAMBA_ROOT_PREFIX="$ROOT/mroot"
./mm create -y -q -p "$ROOT/winpy" --platform win-64 -c conda-forge python=3.12 vc14_runtime
# הגרסה המסחרית: אותו פייתון, בלי המנוע של גרסת המשרד — עם מנועים שמותר למכור איתם
cp -r "$ROOT/winpy" "$ROOT/winpy_c"
python -m pip install -q --no-deps --only-binary=:all: --platform win_amd64 --python-version 3.12 \
  --target "$ROOT/winpy/Lib/site-packages" pymupdf==2.1 PySide6-Essentials==6.12.0 shiboken6==6.12.0
python -m pip install -q --no-deps --only-binary=:all: --platform win_amd64 --python-version 3.12 \
  --target "$ROOT/winpy_c/Lib/site-packages" PySide6-Essentials==6.12.0 shiboken6==6.12.0 \
  pypdfium2==5.14.0 pikepdf==10.16.0 packaging==25.0
python build/trim.py "$ROOT/winpy"
python build/trim.py "$ROOT/winpy_c"
curl -sL -o logo.png https://raw.githubusercontent.com/tiktiny/tiktin-tools/main/tiktin-logo.png
mkdir -p "$ROOT/winpy/app" "$ROOT/out"
# אייקון עם האות O (גרסה משרדית) / C (גרסה מסחרית)
python build/make_assets.py logo.png "$VER" "$DATE" "$ROOT/winpy/app/version.py" "$ROOT/out/tiktin_pdf.ico" "O"
# אייקון לתוכנת "חותמת לוחות אוטומטית" (אותו אייקון, עם האות ח)
python build/make_assets.py logo.png "$VER" "$DATE" "$ROOT/out/_unused_version.py" "$ROOT/out/tiktin_stamp.ico" "ח"
rm -f "$ROOT/out/_unused_version.py"
cp src/*.py "$ROOT/winpy/app/"
python -m compileall -q "$ROOT/winpy/app"
# הגרסה המסחרית: אותו קוד, עם המנוע, שמירת הסימונים והזהות שלה, בלי הכלים של משרד טיקטין
mkdir -p "$ROOT/winpy_c/app"
cp src/*.py "$ROOT/winpy_c/app/"
cp commercial/pymupdf.py commercial/marks_store.py commercial/brand.py commercial/default_stamps.py "$ROOT/winpy_c/app/"
rm -f "$ROOT/winpy_c/app/green_web.py" "$ROOT/winpy_c/app/tiktin_stamp.py"
python build/make_assets.py logo.png "$VER" "$DATE" "$ROOT/out/_unused_c.py" "$ROOT/out/tiktin_pdf_c.ico" "C"
rm -f "$ROOT/out/_unused_c.py"
python commercial/make_assets_c.py "$VER" "$DATE" "$ROOT/winpy_c/app/version.py" "$ROOT/out/tiktin_pdf_c.png"
python -m compileall -q "$ROOT/winpy_c/app"
cd build
makensis -V2 -DROOT="$ROOT" -DVERSION="$VER" -DVNUM="$VNUM" launcher.nsi
makensis -V2 -DROOT="$ROOT" -DVERSION="$VER" -DVNUM="$VNUM" launcher_stamp.nsi
makensis -V2 -DROOT="$ROOT" -DVERSION="$VER" -DVNUM="$VNUM" installer.nsi
# תוכנה נפרדת, עם קובץ התקנה משלה: חותמת אוטומטית
makensis -V2 -DROOT="$ROOT" -DVERSION="$VER" -DVNUM="$VNUM" installer_stamp.nsi
# הגרסה המסחרית
makensis -V2 -DROOT="$ROOT" -DVERSION="$VER" -DVNUM="$VNUM" launcher_c.nsi
makensis -V2 -DROOT="$ROOT" -DVERSION="$VER" -DVNUM="$VNUM" installer_c.nsi
# הקישור הישן (עם A) ממשיך לעבוד — אותו קובץ התקנה של גרסת המשרד
cp "$ROOT/out/TiktinPDF-Setup.exe" "$ROOT/out/TiktinPDF-Setup-A.exe"
ls -la "$ROOT/out"
