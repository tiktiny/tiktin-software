# חותמת אוטומטית — מטביעה חותמת בשחור בכל עמודי קובץ PDF, במקום שאין בו טקסט או שרטוט
# (ואם אין מקום כזה — במקום שמסתיר הכי פחות). לפני ההטבעה בוחרים איזו חותמת:
# חותמת לוחות ריקה (עם או בלי התאריך של היום), חותמת טיקטין לאישור ציוד, או חותמת מקובץ.
# מפעילים: מהאייקון, בגרירת קבצים עליו, או בלחצן ימני על קובץ PDF.
import os
import sys

SLOT = 5                      # "חותמת לוחות – ריקה"
COLOR = "#000000"
ANCHOR = (0.30, 0.78)         # המקום המועדף בעמוד (יחסי): שמאל-למטה, ליד טבלת הכותרת
SUFFIX = " - עם חותמת"


def out_path_for(path):
    base, ext = os.path.splitext(path)
    if base.endswith(SUFFIX):
        return path                              # קובץ שכבר הוטבע: מעדכנים אותו
    return base + SUFFIX + (ext or ".pdf")


def text_turn(page):
    """כמה מעלות (עם השעון) צריך לסובב את העמוד כדי שרוב הטקסט יעמוד ישר. None = אין טקסט (למשל סריקה)."""
    import math
    try:
        w = {0: 0, 90: 0, 180: 0, 270: 0}
        for b in page.get_text("dict", flags=0)["blocks"]:
            for ln in b.get("lines", ()):
                k = sum(len(sp["text"].strip()) for sp in ln["spans"])
                if k:
                    dx, dy = ln["dir"]
                    w[int(round(math.degrees(math.atan2(dy, dx)) / 90.0)) * 90 % 360] += k
        a, k = max(w.items(), key=lambda kv: kv[1])
        return None if k < 8 else (-(a + page.rotation)) % 360
    except Exception:
        return None


def stamp_file(path, progress=None, with_date=False, slot=SLOT):
    """מטביע את החותמת בכל העמודים ושומר קובץ חדש ליד המקור. with_date = לכתוב בחותמת את התאריך של היום.
    מחזיר (קובץ הפלט, עמודים, עמודים צפופים, עמודים בלי טקסט)."""
    import pymupdf
    import stamps
    import marks_store
    pymupdf.TOOLS.set_graphics_min_line_width(1.0)
    doc = pymupdf.open(path)
    if doc.needs_pass:
        raise RuntimeError("הקובץ מוגן בסיסמה")
    try:
        old = marks_store.load(doc)
    except Exception:
        old = None
    items = dict(old[0]) if old else {}
    scales = dict(old[1]) if old else {}
    marks_store.hide_layer(doc)                  # סימונים קודמים של טיקטין לא נחשבים "שרטוט" — הם נשמרים בנפרד
    SLOT_ = slot if stamps.has(slot) else SLOT
    ar = stamps.aspect(SLOT_)
    dp = stamps.date_pos(SLOT_) if with_date else None
    today = None
    if dp:
        from datetime import date
        today = date.today().strftime("%d/%m/%Y")
    crowded = []
    no_text = 0
    n = doc.page_count
    for i in range(n):
        if progress and progress(i, n) is False:
            raise KeyboardInterrupt
        page = doc[i]
        cur = [it for it in items.get(i, []) if not it.get("auto")]     # הרצה חוזרת מחליפה את החותמת האוטומטית, לא מכפילה
        ink = stamps.page_ink(page)
        w_mm = stamps.auto_width_mm(SLOT_, ink)
        W = w_mm * 72.0 / 25.4
        H = W * ar
        # החותמת מונחת בכיוון הטקסט של השרטוט (בעמוד סרוק אין טקסט לקרוא — היא מונחת ישר ביחס לדף)
        turn = text_turn(page)
        if turn is None:
            no_text += 1
        angle = (360 - turn) % 360 if turn else 0
        if angle in (90, 270):
            W, H = H, W
        blocked = []
        for it in cur:
            if it.get("type") == "stamp" and "c" in it:
                bw = it["w"] * 72.0 / 25.4
                bh = bw * it.get("ar", 0.5)
                blocked.append((it["c"][0] - bw / 2, it["c"][1] - bh / 2, it["c"][0] + bw / 2, it["c"][1] + bh / 2))
        cx, cy, clean = stamps.find_free_spot(ink, W, H, ink["PW"] * ANCHOR[0], ink["PH"] * ANCHOR[1], blocked)
        if not clean:
            crowded.append(i + 1)
        st = {"type": "stamp", "slot": SLOT_, "w": w_mm, "ar": ar, "color": COLOR, "c": (cx, cy), "auto": 1}
        if angle:
            st["angle"] = float(angle)
        if dp:
            st["date"], st["datepos"] = today, list(dp)
        cur.append(st)
        items[i] = cur
    doc.close()
    out = out_path_for(path)
    doc2 = pymupdf.open(path)
    marks_store.save(doc2, items, {i: scales.get(i, 50.0) for i in items})
    tmp = out + ".tmp"
    doc2.save(tmp, garbage=3, deflate=True)
    doc2.close()
    os.replace(tmp, out)
    return out, n, crowded, no_text


def main():
    from PySide6.QtCore import Qt, QUrl, QSettings
    from PySide6.QtGui import QPixmap, QIcon, QDesktopServices
    from PySide6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QPushButton,
                                   QFileDialog, QProgressBar, QTextBrowser, QComboBox)
    import base64
    from version import VERSION, BUILD_DATE, LOGO_B64
    VERSION = VERSION.lstrip("AB")          # לתוכנה הזו אין גרסאות A/B
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("Tiktin.AutoStamp")
        except Exception:
            pass
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setLayoutDirection(Qt.RightToLeft)
    app.setStyleSheet("""
        QWidget { background: #ffffff; color: #1f2328; font-family: 'Segoe UI', Arial; font-size: 10.5pt; }
        QLabel#title { font-size: 15pt; font-weight: 700; }
        QLabel#ver { color: #5f6670; font-size: 9.5pt; }
        QLabel#step { font-weight: 700; }
        QLabel#files { border: 2px dashed #d5d9de; border-radius: 10px; color: #5f6670; padding: 10px 14px; }
        QPushButton { background: #ffffff; border: 1px solid #d5d9de; border-radius: 8px; min-height: 36px; padding: 0 16px; }
        QPushButton:hover { border-color: #c8202f; }
        QPushButton#main { background: #c8202f; border-color: #c8202f; color: #ffffff; font-weight: 600; min-height: 42px; }
        QPushButton#main:hover { background: #a31724; }
        QPushButton#main:disabled { background: #e3b5b9; border-color: #e3b5b9; color: #ffffff; }
        QPushButton:disabled { color: #a0a6ad; }
        QComboBox { background: #ffffff; border: 1px solid #d5d9de; border-radius: 8px; min-height: 36px; padding: 0 10px; }
        QComboBox:disabled { color: #a0a6ad; background: #f4f5f7; }
        QComboBox QAbstractItemView { background: #ffffff; color: #1f2328; selection-background-color: #c8202f; }
        QTextBrowser { border: 1px solid #d5d9de; border-radius: 8px; }
        QProgressBar { border: 1px solid #d5d9de; border-radius: 6px; height: 14px; text-align: center; }
        QProgressBar::chunk { background: #c8202f; border-radius: 5px; }
    """)
    import stamps
    st = QSettings("Tiktin", "TiktinPDF")
    FILE_ITEM = "__file__"

    class Win(QWidget):
        def __init__(self):
            super().__init__()
            self.setWindowTitle(f"חותמת אוטומטית – טיקטין   |   גרסה {VERSION} ({BUILD_DATE})")
            self.setAcceptDrops(True)
            self.resize(760, 600)
            self.files, self.outs, self.file_key = [], [], None
            lay = QVBoxLayout(self)
            lay.setContentsMargins(18, 14, 18, 14)
            lay.setSpacing(10)
            hd = QHBoxLayout()
            logo = QLabel()
            pm = QPixmap()
            pm.loadFromData(base64.b64decode(LOGO_B64))
            logo.setPixmap(pm.scaledToHeight(38, Qt.SmoothTransformation))
            self.setWindowIcon(QIcon(pm.copy(179, 12, 75, 86)))
            hd.addWidget(logo)
            t = QLabel("חותמת אוטומטית")
            t.setObjectName("title")
            hd.addWidget(t)
            v = QLabel(f"גרסה {VERSION} · עודכן {BUILD_DATE}")
            v.setObjectName("ver")
            hd.addWidget(v)
            hd.addStretch(1)
            lay.addLayout(hd)
            line = QLabel()
            line.setFixedHeight(2)
            line.setStyleSheet("background: #c8202f;")
            lay.addWidget(line)

            # ----- 1. איזו חותמת
            g = QGridLayout()
            g.setHorizontalSpacing(10)
            g.setVerticalSpacing(8)
            l1 = QLabel("1. החותמת:")
            l1.setObjectName("step")
            g.addWidget(l1, 0, 0)
            self.stamp_box = QComboBox()
            self.stamp_box.setToolTip("איזו חותמת להטביע בכל העמודים")
            for sl in stamps.FIXED + stamps.CUSTOM:        # חותמות שהוספת בטיקטין PDF במחשב הזה מופיעות כאן רק אצלך
                if stamps.has(sl):
                    self.stamp_box.addItem(stamps.name(sl), sl)
            self.stamp_box.addItem("חותמת מקובץ – בחירת קובץ תמונה או PDF...", FILE_ITEM)
            self.stamp_box.activated.connect(self._stamp_picked)
            g.addWidget(self.stamp_box, 0, 1)
            l2 = QLabel("תאריך בחותמת:")
            g.addWidget(l2, 0, 2)
            self.date_box = QComboBox()
            self.date_box.addItem("בלי תאריך", False)
            self.date_box.addItem("התאריך של היום", True)
            self.date_box.setToolTip("בחותמת שיש בה שדה תאריך: לכתוב את התאריך של היום, או להשאיר ריק")
            self.date_box.setCurrentIndex(1 if st.value("autostamp_date", False, type=bool) else 0)
            self.date_box.currentIndexChanged.connect(
                lambda *_: st.setValue("autostamp_date", bool(self.date_box.currentData())))
            g.addWidget(self.date_box, 0, 3)
            # ----- 2. אילו קבצים
            l3 = QLabel("2. הקבצים:")
            l3.setObjectName("step")
            g.addWidget(l3, 1, 0)
            self.files_lbl = QLabel()
            self.files_lbl.setObjectName("files")
            self.files_lbl.setWordWrap(True)
            g.addWidget(self.files_lbl, 1, 1, 1, 2)
            self.pick = QPushButton("בחירת קובצי PDF")
            self.pick.setToolTip("בחירת קובץ PDF אחד או כמה. אפשר גם לגרור קבצים לחלון")
            self.pick.clicked.connect(self.choose)
            g.addWidget(self.pick, 1, 3)
            g.setColumnStretch(1, 1)
            lay.addLayout(g)
            # ----- 3. הטבעה
            self.go = QPushButton("3. הטבעת החותמת בכל העמודים")
            self.go.setObjectName("main")
            self.go.clicked.connect(self.run)
            lay.addWidget(self.go)
            self.bar = QProgressBar()
            self.bar.setVisible(False)
            lay.addWidget(self.bar)
            self.log = QTextBrowser()
            self.log.setOpenLinks(False)
            self.log.anchorClicked.connect(lambda u: QDesktopServices.openUrl(u))
            self.log.setHtml("<p dir=\"rtl\" style='color:#5f6670'>החותמת מוטבעת בשחור, בכל עמוד במקום שלא מסתיר טקסט או שרטוט. "
                             "אם בעמוד אין מקום פנוי לגמרי, היא מונחת במקום שמסתיר הכי פחות, ומספר העמוד יופיע כאן.<br>"
                             "הקובץ המקורי לא משתנה — נשמר לידו קובץ חדש עם הסיומת \"- עם חותמת\".</p>")
            lay.addWidget(self.log, 1)
            row = QHBoxLayout()
            self.open_btn = QPushButton("פתיחת הקובץ האחרון")
            self.open_btn.setToolTip("פותח את הקובץ עם החותמות. בטיקטין PDF אפשר להזיז, למלא ולמחוק אותן")
            self.open_btn.setEnabled(False)
            self.open_btn.clicked.connect(lambda: self.outs and QDesktopServices.openUrl(QUrl.fromLocalFile(self.outs[-1])))
            row.addWidget(self.open_btn)
            self.dir_btn = QPushButton("פתיחת התיקייה")
            self.dir_btn.setEnabled(False)
            self.dir_btn.clicked.connect(
                lambda: self.outs and QDesktopServices.openUrl(QUrl.fromLocalFile(os.path.dirname(self.outs[-1]))))
            row.addWidget(self.dir_btn)
            reset = QPushButton("איפוס")
            reset.setToolTip("מנקה את רשימת הקבצים ומחזיר את הבחירות למצב ההתחלתי")
            reset.clicked.connect(self.reset)
            row.addWidget(reset)
            row.addStretch(1)
            close = QPushButton("סגירה")
            close.clicked.connect(self.close)
            row.addWidget(close)
            lay.addLayout(row)
            last = st.value("autostamp_slot", stamps.FIXED[0])
            i = self.stamp_box.findData(int(last) if str(last).isdigit() else last)
            self.stamp_box.setCurrentIndex(max(0, i) if self.stamp_box.itemData(max(0, i)) != FILE_ITEM else 0)
            self._sync()

        # ----- בחירות
        def slot(self):
            d = self.stamp_box.currentData()
            return self.file_key if d == FILE_ITEM else d

        def _stamp_picked(self, *_):
            if self.stamp_box.currentData() == FILE_ITEM:
                path, _ = QFileDialog.getOpenFileName(self, "קובץ החותמת", st.value("stamp_dir", st.value("last_dir", "")),
                                                      "תמונה או PDF (*.png *.jpg *.jpeg *.bmp *.gif *.pdf)")
                key = None
                if path:
                    st.setValue("stamp_dir", os.path.dirname(path))
                    QApplication.setOverrideCursor(Qt.WaitCursor)
                    try:
                        key = stamps.register_file(path)
                    except Exception:
                        key = None
                    finally:
                        QApplication.restoreOverrideCursor()
                    if key is None:
                        self.log.append("<p dir=\"rtl\" style='color:#c8202f'>לא נמצאה חותמת בקובץ שנבחר. "
                                        "בוחרים תמונה או PDF של החותמת על רקע לבן או שקוף.</p>")
                if key is None:
                    self.file_key = None
                    self.stamp_box.setItemText(self.stamp_box.currentIndex(), "חותמת מקובץ – בחירת קובץ תמונה או PDF...")
                    self.stamp_box.setCurrentIndex(0)
                else:
                    self.file_key = key
                    self.stamp_box.setItemText(self.stamp_box.currentIndex(), "חותמת מקובץ: " + os.path.basename(path))
            else:
                st.setValue("autostamp_slot", self.stamp_box.currentData())
            self._sync()

        def _sync(self):
            sl = self.slot()
            self.date_box.setEnabled(bool(sl is not None and stamps.date_pos(sl)))
            n = len(self.files)
            if not n:
                self.files_lbl.setText("לא נבחרו קבצים — לוחצים \"בחירת קובצי PDF\" או גוררים קבצים לחלון")
            else:
                names = "\u200f, ".join("\u200f" + os.path.basename(f) for f in self.files[:4])
                self.files_lbl.setText(f"{n} קבצים: {names}" + ("\u200f ועוד..." if n > 4 else "") if n > 1 else names)
            self.go.setEnabled(bool(n) and sl is not None)

        def add_files(self, files):
            for f in files:
                if f.lower().endswith(".pdf") and f not in self.files:
                    self.files.append(f)
            self._sync()

        def dragEnterEvent(self, ev):
            if ev.mimeData().hasUrls():
                ev.acceptProposedAction()

        def dropEvent(self, ev):
            self.add_files([u.toLocalFile() for u in ev.mimeData().urls()])

        def choose(self):
            files, _ = QFileDialog.getOpenFileNames(self, "בחירת קובצי PDF", st.value("last_dir", ""), "קובצי PDF (*.pdf)")
            if files:
                st.setValue("last_dir", os.path.dirname(files[0]))
                self.files = []
                self.add_files(files)

        def reset(self):
            self.files, self.file_key = [], None
            self.stamp_box.setItemText(self.stamp_box.findData(FILE_ITEM), "חותמת מקובץ – בחירת קובץ תמונה או PDF...")
            self.stamp_box.setCurrentIndex(0)
            self.date_box.setCurrentIndex(0)
            self.log.clear()
            self._sync()

        # ----- הטבעה
        def run(self):
            sl = self.slot()
            if not self.files or sl is None:
                return
            with_date = bool(self.date_box.currentData()) and self.date_box.isEnabled()
            for w in (self.go, self.pick, self.stamp_box, self.date_box):
                w.setEnabled(False)
            self.bar.setVisible(True)
            sname = self.stamp_box.currentText()
            for f in self.files:
                name = os.path.basename(f)
                self.bar.setFormat(f"{name} — %p%")

                def prog(i, n):
                    self.bar.setMaximum(n)
                    self.bar.setValue(i)
                    QApplication.processEvents()
                    return True
                try:
                    out, n, crowded, no_text = stamp_file(f, prog, with_date, sl)
                    self.outs.append(out)
                    link = QUrl.fromLocalFile(out).toString()
                    msg = (f"<p dir=\"rtl\">\u200f<b>✓ {name}</b>\u200f — \u200f{sname}\u200f הוטבעה ב-{n} עמודים"
                           f"{' עם התאריך של היום' if with_date else ''}.<br>"
                           f"\u200fנשמר: <a href=\"{link}\">{os.path.basename(out)}</a>\u200f")
                    if crowded:
                        pg = ", ".join(map(str, crowded[:20])) + ("..." if len(crowded) > 20 else "")
                        msg += (f"<br><span style='color:#c8202f'>בעמודים {pg} אין מקום פנוי לגמרי — "
                                "החותמת הונחה במקום שמסתיר הכי פחות. כדאי לבדוק אותם.</span>")
                    if no_text:
                        msg += (f"<br><span style='color:#5f6670'>ב-{no_text} עמודים אין טקסט שהמחשב יכול לקרוא (סריקה) — "
                                "שם החותמת מונחת ישר ביחס לדף, גם אם השרטוט שוכב על הצד.</span>")
                    self.log.append(msg + "</p>")
                except Exception as e:
                    self.log.append(f"<p dir=\"rtl\">\u200f<b style='color:#c8202f'>✗ {name}</b>\u200f — לא הוטבע: {e}</p>")
                QApplication.processEvents()
            self.bar.setVisible(False)
            for w in (self.pick, self.stamp_box):
                w.setEnabled(True)
            self.files = []
            self._sync()
            self.open_btn.setEnabled(bool(self.outs))
            self.dir_btn.setEnabled(bool(self.outs))

    w = Win()
    w.show()
    w.add_files([a for a in sys.argv[1:] if not a.startswith("-")])     # קבצים שנגררו על האייקון או נבחרו בלחצן ימני
    return app.exec()


if __name__ == "__main__":
    rc = main()
    sys.stdout.flush()
    os._exit(rc)        # יציאה מיידית ונקייה, בלי פירוק איטי של הספריות
