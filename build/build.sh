#!/usr/bin/env bash
# בניית קובץ ההתקנה של טיקטין PDF ל-Windows (רץ ב-GitHub Actions על Linux)
set -euo pipefail
ROOT="$(pwd)"
VER="$(sed -n 1p VERSION)"; DATE="$(sed -n 2p VERSION)"
sudo apt-get update -qq && sudo apt-get install -y -qq nsis >/dev/null
python -m pip install -q pillow
curl -sL -o mm https://github.com/mamba-org/micromamba-releases/releases/latest/download/micromamba-linux-64
chmod +x mm
export MAMBA_ROOT_PREFIX="$ROOT/mroot"
./mm create -y -q -p "$ROOT/winpy" --platform win-64 -c conda-forge python=3.12 vc14_runtime
python -m pip install -q --no-deps --only-binary=:all: --platform win_amd64 --python-version 3.12 \
  --target "$ROOT/winpy/Lib/site-packages" pymupdf==2.1 PySide6-Essentials==6.12.0 shiboken6==6.12.0
python build/trim.py "$ROOT/winpy"
curl -sL -o logo.png https://raw.githubusercontent.com/tiktiny/tiktin-tools/main/tiktin-logo.png
mkdir -p "$ROOT/winpy/app" "$ROOT/out"
python build/make_assets.py logo.png "$VER" "$DATE" "$ROOT/winpy/app/version.py" "$ROOT/out/tiktin_pdf.ico"
cp src/*.py "$ROOT/winpy/app/"
cp -r src/fonts "$ROOT/winpy/app/"
python -m compileall -q "$ROOT/winpy/app"
cd build
makensis -V2 -DROOT="$ROOT" -DVERSION="$VER" launcher.nsi
makensis -V2 -DROOT="$ROOT" -DVERSION="$VER" installer.nsi
# גרסה B (ממשק חדש): אותו קוד, עם הקובץ new_ui.flag שמפעיל את הממשק החדש
touch "$ROOT/winpy/app/new_ui.flag"
makensis -V2 -DROOT="$ROOT" -DVERSION="$VER" -DVARIANT_B launcher.nsi
makensis -V2 -DROOT="$ROOT" -DVERSION="$VER" -DVARIANT_B installer.nsi
rm -f "$ROOT/winpy/app/new_ui.flag"
ls -la "$ROOT/out"
