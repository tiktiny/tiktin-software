# חותמת לוחות אוטומטית — מטביעה חותמת לוחות ריקה (עם או בלי התאריך של היום), בשחור, בכל עמודי קובץ PDF,
# במקום שאין בו טקסט או שרטוט (ואם אין מקום כזה — במקום שמסתיר הכי פחות).
# מפעילים על קובץ: גרירה על האייקון, לחצן ימני על קובץ PDF, או בחירת קבצים בחלון.
import os
import sys

SLOT = 5                      # "חותמת לוחות – ריקה"
COLOR = "#000000"
ANCHOR = (0.30, 0.78)         # המקום המועדף בעמוד (יחסי): שמאל-למטה, ליד טבלת הכותרת
SUFFIX = " - חותמת לוחות"


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
    from PySide6.QtCore import Qt, QTimer, QUrl
    from PySide6.QtGui import QPixmap, QIcon, QDesktopServices
    from PySide6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
                                   QFileDialog, QProgressBar, QTextBrowser, QComboBox)
    import base64
    from version import VERSION, BUILD_DATE, LOGO_B64
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("Tiktin.BoardStamp")
        except Exception:
            pass
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setLayoutDirection(Qt.RightToLeft)
    app.setStyleSheet("""
        QWidget { background: #ffffff; color: #1f2328; font-family: 'Segoe UI', Arial; font-size: 10.5pt; }
        QLabel#title { font-size: 15pt; font-weight: 700; }
        QLabel#ver { color: #5f6670; font-size: 9.5pt; }
        QLabel#drop { border: 2px dashed #d5d9de; border-radius: 10px; color: #5f6670; padding: 18px; font-size: 11pt; }
        QPushButton { background: #ffffff; border: 1px solid #d5d9de; border-radius: 8px; min-height: 36px; padding: 0 16px; }
        QPushButton:hover { border-color: #c8202f; }
        QPushButton#main { background: #c8202f; border-color: #c8202f; color: #ffffff; font-weight: 600; }
        QPushButton#main:hover { background: #a31724; }
        QPushButton:disabled { color: #a0a6ad; }
        QComboBox { background: #ffffff; border: 1px solid #d5d9de; border-radius: 8px; min-height: 34px; padding: 0 8px; }
        QComboBox QAbstractItemView { background: #ffffff; color: #1f2328; }
        QTextBrowser { border: 1px solid #d5d9de; border-radius: 8px; }
        QProgressBar { border: 1px solid #d5d9de; border-radius: 6px; height: 14px; text-align: center; }
        QProgressBar::chunk { background: #c8202f; border-radius: 5px; }
    """)

    class Win(QWidget):
        def __init__(self):
            super().__init__()
            self.setWindowTitle(f"חותמת לוחות אוטומטית – טיקטין   |   גרסה {VERSION} ({BUILD_DATE})")
            self.setAcceptDrops(True)
            self.resize(720, 520)
            self.outs = []
            lay = QVBoxLayout(self)
            lay.setContentsMargins(18, 14, 18, 14)
            lay.setSpacing(12)
            hd = QHBoxLayout()
            logo = QLabel()
            pm = QPixmap()
            pm.loadFromData(base64.b64decode(LOGO_B64))
            logo.setPixmap(pm.scaledToHeight(38, Qt.SmoothTransformation))
            self.setWindowIcon(QIcon(pm.copy(179, 12, 75, 86)))
            hd.addWidget(logo)
            t = QLabel("חותמת לוחות אוטומטית")
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
            self.drop = QLabel("גוררים לכאן קובצי PDF, או לוחצים על \"בחירת קבצים\".\n"
                               "בכל עמוד תוטבע חותמת לוחות ריקה, בשחור, במקום שלא מסתיר טקסט או שרטוט.\n"
                               "הקובץ המקורי לא משתנה — נשמר קובץ חדש לידו, עם הסיומת \"- חותמת לוחות\".")
            self.drop.setObjectName("drop")
            self.drop.setAlignment(Qt.AlignCenter)
            self.drop.setWordWrap(True)
            lay.addWidget(self.drop)
            self.bar = QProgressBar()
            self.bar.setVisible(False)
            lay.addWidget(self.bar)
            self.log = QTextBrowser()
            self.log.setOpenLinks(False)
            self.log.anchorClicked.connect(lambda u: QDesktopServices.openUrl(u))
            lay.addWidget(self.log, 1)
            row = QHBoxLayout()
            from PySide6.QtCore import QSettings
            row.addWidget(QLabel("תאריך בחותמת:"))
            self.date_box = QComboBox()
            self.date_box.addItem("בלי תאריך", False)
            self.date_box.addItem("התאריך של היום", True)
            self.date_box.setToolTip("האם לכתוב בחותמת את התאריך של היום, או להשאיר את שדה התאריך ריק. הבחירה נשמרת")
            self.date_box.setMinimumWidth(150)
            self.date_box.setCurrentIndex(1 if QSettings("Tiktin", "TiktinPDF").value("autostamp_date", False, type=bool) else 0)
            self.date_box.currentIndexChanged.connect(
                lambda *_: QSettings("Tiktin", "TiktinPDF").setValue("autostamp_date", bool(self.date_box.currentData())))
            row.addWidget(self.date_box)
            import stamps
            self.stamp_box = QComboBox()
            for sl in stamps.FIXED + stamps.CUSTOM:        # חותמות שהוספת במחשב הזה (למשל חותמת חתומה) מופיעות רק אצלך
                if stamps.has(sl):
                    self.stamp_box.addItem(stamps.name(sl), sl)
            self.stamp_box.setToolTip("איזו חותמת להטביע. חותמות שהוספת בטיקטין PDF במחשב הזה מופיעות כאן רק אצלך")
            self.stamp_box.setMinimumWidth(190)
            self.stamp_box.setVisible(self.stamp_box.count() > 1)
            row.addWidget(self.stamp_box)
            self.pick = QPushButton("בחירת קבצים")
            self.pick.setObjectName("main")
            self.pick.setToolTip("בחירת קובץ PDF אחד או כמה קבצים")
            self.pick.clicked.connect(self.choose)
            row.insertWidget(0, self.pick)
            self.open_btn = QPushButton("פתיחת הקובץ האחרון")
            self.open_btn.setToolTip("פותח את הקובץ עם החותמות — שם אפשר להזיז, למלא ולמחוק חותמות")
            self.open_btn.setEnabled(False)
            self.open_btn.clicked.connect(lambda: self.outs and QDesktopServices.openUrl(QUrl.fromLocalFile(self.outs[-1])))
            row.addWidget(self.open_btn)
            self.dir_btn = QPushButton("פתיחת התיקייה")
            self.dir_btn.setEnabled(False)
            self.dir_btn.clicked.connect(
                lambda: self.outs and QDesktopServices.openUrl(QUrl.fromLocalFile(os.path.dirname(self.outs[-1]))))
            row.addWidget(self.dir_btn)
            row.addStretch(1)
            close = QPushButton("סגירה")
            close.clicked.connect(self.close)
            row.addWidget(close)
            lay.addLayout(row)

        def dragEnterEvent(self, ev):
            if ev.mimeData().hasUrls():
                ev.acceptProposedAction()

        def dropEvent(self, ev):
            self.run([u.toLocalFile() for u in ev.mimeData().urls() if u.toLocalFile().lower().endswith(".pdf")])

        def choose(self):
            from PySide6.QtCore import QSettings
            st = QSettings("Tiktin", "TiktinPDF")
            files, _ = QFileDialog.getOpenFileNames(self, "בחירת קובצי PDF", st.value("last_dir", ""), "קובצי PDF (*.pdf)")
            if files:
                st.setValue("last_dir", os.path.dirname(files[0]))
                self.run(files)

        def run(self, files):
            if not files:
                return
            self.pick.setEnabled(False)
            self.bar.setVisible(True)
            for k, f in enumerate(files):
                name = os.path.basename(f)
                self.bar.setFormat(f"{name} — %p%")

                def prog(i, n, k=k):
                    self.bar.setMaximum(n)
                    self.bar.setValue(i)
                    QApplication.processEvents()
                    return True
                try:
                    out, n, crowded, no_text = stamp_file(f, prog, bool(self.date_box.currentData()),
                                                          self.stamp_box.currentData() or SLOT)
                    self.outs.append(out)
                    link = QUrl.fromLocalFile(out).toString()
                    msg = (f"<p dir=\"rtl\">\u200f<b>✓ {name}</b>\u200f — הוטבעה חותמת ב-{n} עמודים.<br>"
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
            self.pick.setEnabled(True)
            self.open_btn.setEnabled(bool(self.outs))
            self.dir_btn.setEnabled(bool(self.outs))

    w = Win()
    w.show()
    args = [a for a in sys.argv[1:] if not a.startswith("-") and a.lower().endswith(".pdf")]
    if args:
        QTimer.singleShot(50, lambda: w.run(args))
    return app.exec()


if __name__ == "__main__":
    rc = main()
    sys.stdout.flush()
    os._exit(rc)        # יציאה מיידית ונקייה, בלי פירוק איטי של הספריות
