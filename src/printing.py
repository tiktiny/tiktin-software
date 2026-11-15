# הדפסה עם תצוגה מקדימה: כל הקובץ / עמוד נוכחי / מסך נוכחי / בחירת חלון,
# A4 או A3, צבע או שחור-לבן. בשולי כל גיליון: שם הקובץ, תאריך ההדפסה וקנ"מ ההדפסה.
import os
import datetime
import pymupdf
from PySide6.QtCore import Qt, QSettings, QRectF, QMarginsF, QTimer, QEventLoop, QPointF
from PySide6.QtGui import QImage, QPainter, QPageSize, QPageLayout, QFont, QColor, QPen, QPixmap
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
                               QComboBox, QSpinBox, QProgressDialog, QMessageBox,
                               QApplication, QSizePolicy)
from PySide6.QtPrintSupport import QPrinter, QPrinterInfo

RANGES = [("all", "כל הקובץ"), ("page", "עמוד נוכחי"), ("screen", "מסך נוכחי"), ("window", "בחירת חלון")]
PAPERS = [("A4", "A4"), ("A3", "A3")]
COLORS = [("color", "צבע"), ("bw", "שחור-לבן")]
PAPER_MM = {"A4": (210.0, 297.0), "A3": (297.0, 420.0)}
MARGIN_MM = 5.0
FOOTER_MM = 6.0
MAX_DPI = 300

# שחור-לבן: גווני אפור מוכהים, כך שקווים צבעוניים בהירים (צהוב, תכלת) יודפסו כהים וברורים
_BW_LUT = bytes(255 if v >= 250 else int(255 * (v / 255.0) ** 2.6) for v in range(256))


def _fmt_scale(x):
    return f"{round(x):.0f}" if abs(x - round(x)) < 0.05 or x >= 100 else f"{x:.1f}"


def sheet_mm(paper, clip):
    w, h = PAPER_MM[paper]
    return (h, w) if clip.width > clip.height else (w, h)


def draw_sheet(p, area_w, area_h, res, doc, pno, clip, bw, overlay, S, fname, when):
    """מצייר גיליון אחד בתוך אזור ההדפסה (פיקסלים של ההתקן). מחזיר את קנ"מ ההדפסה."""
    px_mm = res / 25.4
    foot = FOOTER_MM * px_mm
    draw_h = area_h - foot
    fit = min(area_w / clip.width, draw_h / clip.height)      # פיקסל התקן לנקודת PDF
    scale = min(fit, MAX_DPI / 72.0)
    page = doc[pno]
    if bw:
        pix = page.get_pixmap(matrix=pymupdf.Matrix(scale, scale), clip=clip,
                              colorspace=pymupdf.csGRAY, alpha=False)
        data = pix.samples.translate(_BW_LUT)
        img = QImage(data, pix.width, pix.height, pix.stride, QImage.Format_Grayscale8)
    else:
        pix = page.get_pixmap(matrix=pymupdf.Matrix(scale, scale), clip=clip, alpha=False)
        data = pix.samples
        img = QImage(data, pix.width, pix.height, pix.stride, QImage.Format_RGB888)
    w, h = clip.width * fit, clip.height * fit
    tgt = QRectF((area_w - w) / 2, (draw_h - h) / 2, w, h)
    p.save()
    p.setRenderHint(QPainter.SmoothPixmapTransform, True)
    p.drawImage(tgt, img)
    if overlay is not None:
        p.setClipRect(tgt)
        p.translate(tgt.x() - clip.x0 * fit, tgt.y() - clip.y0 * fit)
        p.scale(fit, fit)
        p.setRenderHint(QPainter.Antialiasing, True)
        overlay(p, pno)
    p.restore()

    # קנ"מ בהדפסה: יחס בין גודל ההדפסה לגודל הדף המקורי
    ratio = fit * 72.0 / res
    printed = S / ratio
    p.save()
    pen = QPen(QColor(110, 110, 110))
    pen.setWidthF(max(1.0, 0.2 * px_mm))
    p.setPen(pen)
    y_line = area_h - foot + 1.2 * px_mm
    p.drawLine(QPointF(0, y_line), QPointF(area_w, y_line))
    f = QFont("Arial")
    f.setPixelSize(max(6, int(2.3 * px_mm)))
    p.setFont(f)
    p.setPen(QColor(40, 40, 40))
    box = QRectF(0, y_line + 0.6 * px_mm, area_w, foot - 1.8 * px_mm)
    p.setLayoutDirection(Qt.RightToLeft)
    p.drawText(box, Qt.AlignAbsolute | Qt.AlignRight | Qt.AlignVCenter, fname)
    p.drawText(box, Qt.AlignHCenter | Qt.AlignVCenter,
               f"קנ\"מ בהדפסה \u202a1:{_fmt_scale(printed)}\u202c   (קנ\"מ השרטוט \u202a1:{_fmt_scale(S)}\u202c)")
    p.drawText(box, Qt.AlignAbsolute | Qt.AlignLeft | Qt.AlignVCenter, f"הודפס \u202a{when}\u202c")
    p.restore()
    return printed


class PrintDialog(QDialog):
    def __init__(self, main):
        super().__init__(main)
        self.main = main
        self.view = main.view
        self.setWindowTitle("הדפסה")
        self.setLayoutDirection(Qt.RightToLeft)
        self.window_job = None
        self._cache = {}
        self.sheet = 0
        st = QSettings("Tiktin", "TiktinPDF")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 14, 16, 14)
        lay.setSpacing(10)

        row1 = QHBoxLayout()
        row1.setSpacing(8)
        lay.addLayout(row1)

        def seg(title, items, saved, tips=None):
            # תפריט נפתח (לא כרטיסיות)
            row1.addWidget(QLabel(title))
            box = QComboBox()
            for key, text in items:
                box.addItem(text, key)
                if tips and tips.get(key):
                    box.setItemData(box.count() - 1, tips[key], Qt.ToolTipRole)
            i = box.findData(saved)
            box.setCurrentIndex(i if i >= 0 else 0)
            box.setMinimumWidth(130)
            row1.addWidget(box)
            row1.addSpacing(14)
            return box

        n = len(self.view.sizes)
        saved_range = st.value("pr_range", "page")
        if saved_range == "window":
            saved_range = "page"
        self.g_range = seg("מה להדפיס", RANGES, saved_range, {
            "all": f"כל {n} העמודים", "page": "העמוד שמוצג כעת",
            "screen": "בדיוק מה שרואים כרגע בחלון",
            "window": "החלון ייסגר לרגע — גוררים מלבן על השרטוט"})
        self.g_paper = seg("גיליון", PAPERS, st.value("pr_paper", "A3"))
        self.g_color = seg("צבע", COLORS, st.value("pr_color", "color"),
                           {"bw": "קווים צבעוניים בהירים יודפסו כהים"})
        row1.addStretch(1)

        row2 = QHBoxLayout()
        row2.setSpacing(8)
        lay.addLayout(row2)
        row2.addWidget(QLabel("מדפסת"))
        self.printer_box = QComboBox()
        names = QPrinterInfo.availablePrinterNames()
        default = QPrinterInfo.defaultPrinterName()
        self.printer_box.addItems(names or ["(לא נמצאה מדפסת)"])
        last = st.value("pr_printer", default)
        if last in names:
            self.printer_box.setCurrentText(last)
        elif default in names:
            self.printer_box.setCurrentText(default)
        self.printer_box.setMinimumWidth(280)
        row2.addWidget(self.printer_box)
        row2.addSpacing(14)
        row2.addWidget(QLabel("עותקים"))
        self.copies = QSpinBox()
        self.copies.setRange(1, 99)
        self.copies.setFixedWidth(64)
        self.copies.setAlignment(Qt.AlignCenter)
        self.copies.setButtonSymbols(QSpinBox.NoButtons)
        self.copies.setToolTip("מספר עותקים")
        row2.addWidget(self.copies)
        row2.addSpacing(14)
        self.info = QLabel("")
        self.info.setObjectName("info")
        row2.addWidget(self.info, 1)
        cancel = QPushButton("ביטול")
        cancel.setObjectName("plainBtn")
        self.ok = QPushButton("הדפסה")
        self.ok.setObjectName("primaryBtn")
        self.ok.setDefault(True)
        self.ok.setEnabled(bool(names))
        row2.addWidget(cancel)
        row2.addWidget(self.ok)
        cancel.clicked.connect(self.reject)
        self.ok.clicked.connect(self._print)

        # תצוגה מקדימה
        self.pv = QLabel()
        self.pv.setAlignment(Qt.AlignCenter)
        self.pv.setMinimumSize(300, 300)
        self.pv.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.pv.setStyleSheet("background:#d9dde3; border:none; color:#5a6270;")
        lay.addWidget(self.pv, 1)
        nav = QHBoxLayout()
        self.prev_b = QPushButton("הקודם")
        self.next_b = QPushButton("הבא")
        for b in (self.prev_b, self.next_b):
            b.setObjectName("plainBtn")
        self.nav_lbl = QLabel("")
        self.nav_lbl.setAlignment(Qt.AlignCenter)
        self.nav_lbl.setMinimumWidth(120)
        nav.addStretch(1)
        nav.addWidget(self.prev_b)
        nav.addWidget(self.nav_lbl)
        nav.addWidget(self.next_b)
        nav.addStretch(1)
        lay.addLayout(nav)
        self.prev_b.clicked.connect(lambda: self._go(-1))
        self.next_b.clicked.connect(lambda: self._go(1))

        self.timer = QTimer(self, singleShot=True, interval=60)
        self.timer.timeout.connect(self._render_preview)
        for g in (self.g_paper, self.g_color):
            g.currentIndexChanged.connect(lambda *_: self._changed())
        self.g_range.activated.connect(self._range_clicked)
        r = main.geometry()
        self.resize(int(r.width() * 0.92), int(r.height() * 0.92))
        self._changed()

    # ----- options
    def opts(self):
        def k(g):
            return g.currentData()
        return {"range": k(self.g_range), "paper": k(self.g_paper), "color": k(self.g_color),
                "printer": self.printer_box.currentText(), "copies": self.copies.value()}

    def jobs(self):
        v = self.view
        o = self.opts()
        cur = max(0, v._cur_page)
        if o["range"] == "all":
            return [(i, v.doc[i].rect) for i in range(len(v.sizes))]
        if o["range"] == "page":
            return [(cur, v.doc[cur].rect)]
        if o["range"] == "screen":
            sc = v.screen_clip()
            return [sc] if sc else []
        return [self.window_job] if self.window_job else []

    def _set_range(self, key):
        i = self.g_range.findData(key)
        if i >= 0:
            self.g_range.setCurrentIndex(i)

    def _range_clicked(self, idx):
        if self.g_range.itemData(idx) == "window":
            QTimer.singleShot(0, self._pick_window)
        else:
            self._changed()

    def _pick_window(self):
        """מסתיר את החלון, נותן לגרור מלבן על השרטוט, וחוזר עם התצוגה המקדימה."""
        v = self.view
        loop = QEventLoop()
        got = []

        def on_region(i, clip):
            got.append((i, clip))
            loop.quit()

        v.region_selected.connect(on_region)
        v.select_cancelled.connect(loop.quit)
        self.hide()
        self.main.statusBar().showMessage("גררו מלבן סביב האזור להדפסה  (Esc לביטול)")
        self.main.activateWindow()
        v.start_select()
        v.setFocus()
        loop.exec()
        v.region_selected.disconnect(on_region)
        v.select_cancelled.disconnect(loop.quit)
        self.main.statusBar().clearMessage()
        if got:
            self.window_job = got[0]
        elif not self.window_job:
            self._set_range("page")
        self.show()
        self.raise_()
        self.activateWindow()
        self._changed()

    def _changed(self):
        self.sheet = 0
        self.timer.start()

    def _go(self, d):
        n = len(self.jobs())
        self.sheet = max(0, min(n - 1, self.sheet + d))
        self.timer.start()

    def resizeEvent(self, ev):
        super().resizeEvent(ev)
        self.timer.start()

    # ----- preview
    def _render_preview(self):
        jobs = self.jobs()
        n = len(jobs)
        self.sheet = max(0, min(self.sheet, n - 1))
        self.prev_b.setEnabled(self.sheet > 0)
        self.next_b.setEnabled(self.sheet < n - 1)
        self.nav_lbl.setText(f"גיליון {self.sheet + 1} מתוך {n}" if n else "")
        self.ok.setText(f"הדפסה ({n} גיליונות)" if n > 1 else "הדפסה")
        if not n:
            self.pv.setPixmap(QPixmap())
            self.pv.setText("לא נבחר אזור להדפסה")
            self.info.setText("")
            return
        o = self.opts()
        pno, clip = jobs[self.sheet]
        wmm, hmm = sheet_mm(o["paper"], clip)
        aw, ah = max(100, self.pv.width() - 30), max(100, self.pv.height() - 30)
        res = min(aw / (wmm / 25.4), ah / (hmm / 25.4))
        key = (pno, tuple(clip), o["paper"], o["color"], round(res), self.view.overlay_version)
        hit = self._cache.get(key)
        if hit is None:
            QApplication.setOverrideCursor(Qt.WaitCursor)
            try:
                W, H = int(wmm / 25.4 * res), int(hmm / 25.4 * res)
                img = QImage(W, H, QImage.Format_RGB32)
                img.fill(Qt.white)
                p = QPainter(img)
                p.setRenderHint(QPainter.Antialiasing, True)
                m = MARGIN_MM / 25.4 * res
                p.translate(m, m)
                printed = draw_sheet(p, W - 2 * m, H - 2 * m, res, self.view.doc, pno, clip,
                                     o["color"] == "bw", self.main._print_overlay,
                                     self.view.scale_of(pno), self._fname(), self._when())
                p.end()
                if len(self._cache) > 12:
                    self._cache.clear()
                hit = (QPixmap.fromImage(img), printed)
                self._cache[key] = hit
            finally:
                QApplication.restoreOverrideCursor()
        self.pv.setText("")
        self.pv.setPixmap(hit[0])
        self.info.setText(f"קנ\"מ בהדפסה \u202a1:{_fmt_scale(hit[1])}\u202c   |   "
                          f"גיליון {o['paper']} {'לרוחב' if wmm > hmm else 'לאורך'}")

    def _fname(self):
        return os.path.basename(self.view.path or "")

    @staticmethod
    def _when():
        return datetime.datetime.now().strftime("%d/%m/%Y %H:%M")

    # ----- print
    def save(self):
        o = self.opts()
        st = QSettings("Tiktin", "TiktinPDF")
        for k in ("range", "paper", "color", "printer"):
            st.setValue(f"pr_{k}", o[k])

    def _print(self):
        jobs = self.jobs()
        if not jobs:
            return
        self.save()
        o = self.opts()
        printer = QPrinter(QPrinter.HighResolution)
        printer.setPrinterName(o["printer"])
        if print_jobs(self, self.view, jobs, o, self._fname(), self._when(),
                      self.main._print_overlay, printer):
            self.accept()


def print_jobs(parent, view, jobs, opts, fname, when, overlay, printer):
    doc = view.doc
    printer.setDocName(fname)
    printer.setCopyCount(opts["copies"])
    bw = opts["color"] == "bw"
    printer.setColorMode(QPrinter.GrayScale if bw else QPrinter.Color)
    size = QPageSize(QPageSize.A3 if opts["paper"] == "A3" else QPageSize.A4)

    def orient(clip):
        return QPageLayout.Landscape if clip.width > clip.height else QPageLayout.Portrait

    printer.setPageLayout(QPageLayout(size, orient(jobs[0][1]),
                                      QMarginsF(MARGIN_MM, MARGIN_MM, MARGIN_MM, MARGIN_MM),
                                      QPageLayout.Millimeter))
    prog = QProgressDialog("מכין להדפסה…", "ביטול", 0, len(jobs), parent)
    prog.setWindowTitle("הדפסה")
    prog.setWindowModality(Qt.WindowModal)
    prog.setMinimumDuration(400)
    painter = QPainter()
    if not painter.begin(printer):
        QMessageBox.warning(parent, "הדפסה", "לא ניתן להתחיל הדפסה במדפסת שנבחרה.")
        return False
    try:
        for n, (pno, clip) in enumerate(jobs):
            if prog.wasCanceled():
                printer.abort()
                return False
            prog.setValue(n)
            prog.setLabelText(f"מדפיס {n + 1} מתוך {len(jobs)}")
            QApplication.processEvents()
            if n > 0:
                printer.setPageOrientation(orient(clip))
                printer.newPage()
            res = printer.resolution()
            area = printer.pageLayout().paintRectPixels(res)
            draw_sheet(painter, area.width(), area.height(), res, doc, pno, clip, bw,
                       overlay, view.scale_of(pno), fname, when)
        prog.setValue(len(jobs))
    finally:
        painter.end()
    return True
