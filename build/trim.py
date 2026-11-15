# מסיר מהחבילה רכיבים שהתוכנה לא צריכה, כדי שקובץ ההתקנה יהיה קטן
import os, shutil, sys, glob
W = sys.argv[1]
sp = os.path.join(W, "Lib", "site-packages")
qt = os.path.join(sp, "PySide6")
keep = {"Qt6Core.dll", "Qt6Gui.dll", "Qt6Widgets.dll", "Qt6PrintSupport.dll", "QtCore.pyd", "QtGui.pyd",
        "QtWidgets.pyd", "QtPrintSupport.pyd", "pyside6.abi3.dll", "__init__.py", "_config.py",
        "_git_pyside_version.py", "concrt140.dll", "msvcp140.dll", "msvcp140_1.dll", "msvcp140_2.dll",
        "msvcp140_codecvt_ids.dll", "vcruntime140.dll", "vcruntime140_1.dll", "vccorlib140.dll",
        "vcomp140.dll", "plugins", "support", "PySide6_Essentials.json"}


def rm(p):
    if os.path.isdir(p):
        shutil.rmtree(p, ignore_errors=True)
    elif os.path.exists(p):
        os.remove(p)


for f in os.listdir(qt):
    if f not in keep:
        rm(os.path.join(qt, f))
for d in os.listdir(os.path.join(qt, "plugins")):
    if d not in ("platforms", "imageformats"):
        rm(os.path.join(qt, "plugins", d))
# רק מה שהתוכנה משתמשת בו: חלון Windows, ותמונות JPG/GIF/ICO לחותמות (PNG ו-BMP מובנים)
for f in glob.glob(os.path.join(qt, "plugins", "platforms", "*")):
    if os.path.basename(f) != "qwindows.dll":
        rm(f)
for f in glob.glob(os.path.join(qt, "plugins", "imageformats", "*")):
    if os.path.basename(f) not in ("qjpeg.dll", "qgif.dll", "qico.dll"):
        rm(f)
for p in ("pymupdf4llm", "pymupdf/layout", "pymupdf/mupdf-devel"):
    rm(os.path.join(sp, p))
for p in ("Lib/test", "Lib/tkinter", "Lib/idlelib", "Lib/ensurepip", "Lib/lib2to3", "Tools", "Scripts",
          "share", "Lib/sqlite3", "Lib/venv", "Lib/pydoc_data", "Lib/unittest", "Lib/asyncio",
          "include", "libs", "lib", "Library/lib", "Library/include", "Library/share", "conda-meta",
          "python312.pdb"):
    rm(os.path.join(W, p))
for pat in ("Library/bin/*.pdb", "Library/bin/openssl.exe", "Library/bin/tcl*", "Library/bin/tk*",
            "Library/bin/wish*", "Library/bin/c_rehash.pl", "DLLs/_tkinter.pyd", "DLLs/tcl*", "DLLs/tk*",
            # לא בשימוש: הצפנה ורשת מאובטחת, מסד נתונים, בדיקות פנימיות של פייתון, אייקונים
            "Library/bin/libssl*", "Library/bin/libcrypto*", "Library/bin/sqlite3.dll", "Library/bin/vcamp140.dll",
            "DLLs/_ssl.pyd", "DLLs/_hashlib.pyd", "DLLs/_sqlite3.pyd", "DLLs/_test*.pyd", "DLLs/py*.ico"):
    for f in glob.glob(os.path.join(W, pat)):
        rm(f)
print("trimmed")
