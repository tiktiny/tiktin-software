# חיפוש טקסט במסמך: צירוף מילים, חלקי מילים, וסימנים מיוחדים –
#   ?  = תו אחד כלשהו (בתוך מילה)
#   *  = כל רצף תווים (בתוך מילה, גם ריק)
# החיפוש לא תלוי באותיות גדולות/קטנות, ורווחים בחיפוש מתאימים לכל רווח בין מילים.
# התוצאות במערכת התצוגה של העמוד (אחרי סיבוב), מוכנות לציור.
import re
import pymupdf


def compile_pattern(text):
    """מחזיר ביטוי רגולרי, או None לחיפוש ריק."""
    t = (text or "").strip()
    if not t:
        return None
    out = []
    for ch in t:
        if ch == "?":
            out.append(r"\S")
        elif ch == "*":
            out.append(r"\S*?")
        elif ch.isspace():
            if not out or out[-1] != r"\s+":
                out.append(r"\s+")
        else:
            out.append(re.escape(ch))
    return re.compile("".join(out), re.IGNORECASE)


def page_hits(page, rx):
    """רשימת מלבנים (pymupdf.Rect, במערכת התצוגה) של כל ההתאמות בעמוד, לפי סדר הקריאה."""
    words = page.get_text("words", sort=False)
    if not words:
        return []
    lines = {}
    for w in words:
        lines.setdefault((w[5], w[6]), []).append(w)
    rot = page.rotation_matrix if page.rotation else None
    hits = []
    for key in sorted(lines):
        ws = sorted(lines[key], key=lambda w: w[7])
        text, spans = "", []
        for w in ws:
            if text:
                text += " "
            spans.append((len(text), len(text) + len(w[4])))
            text += w[4]
        for m in rx.finditer(text):
            a, b = m.span()
            if b <= a:
                continue
            r = None
            for (s, e), w in zip(spans, ws):
                if s < b and e > a:
                    wr = pymupdf.Rect(w[:4])
                    r = wr if r is None else r | wr
            if r is not None:
                if rot is not None:
                    r = r * rot
                    r.normalize()
                hits.append(r)
    return hits


# ----------------------------------------------------------------------------- סרגל החיפוש
import time
from PySide6.QtCore import Qt, QTimer, QEvent
from PySide6.QtWidgets import QToolBar, QLabel, QLineEdit, QToolButton, QWidget, QSizePolicy


class FindBar(QToolBar):
    """סרגל חיפוש שנפתח מתחת לסרגל הכפתורים (Ctrl+F). Enter = הבא, Shift+Enter = הקודם, Esc = סגירה.
    הסריקה עוברת עמוד אחרי עמוד בהפסקות קצרות, כך שהתוכנה לא נתקעת גם בקובץ גדול."""

    BUDGET = 0.035          # שניות עבודה בכל פעימה, ואז חוזרים לממשק

    def __init__(self, main):
        super().__init__(main)
        self.main = main
        self.setObjectName("findbar")
        self.setMovable(False)
        self.setFloatable(False)
        self.setContextMenuPolicy(Qt.PreventContextMenu)
        self.setLayoutDirection(Qt.RightToLeft)
        self.addWidget(QLabel("  חיפוש במסמך: "))
        self.edit = QLineEdit()
        self.edit.setPlaceholderText("מילים או צירוף מילים.   ? = תו אחד   * = כמה תווים")
        self.edit.setMinimumWidth(360)
        self.edit.setClearButtonEnabled(True)
        self.edit.installEventFilter(self)
        self.addWidget(self.edit)
        self.prev_b = self._tb("▲ הקודם", "התוצאה הקודמת (Shift+Enter)", lambda: self.go(-1))
        self.next_b = self._tb("הבא ▼", "התוצאה הבאה (Enter)", lambda: self.go(1))
        self.count = QLabel("")
        self.count.setMinimumWidth(180)
        self.addWidget(self.count)
        sp = QWidget()
        sp.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.addWidget(sp)
        self._tb("✕", "סגירת החיפוש (Esc)", self.close_bar)
        self.debounce = QTimer(self, singleShot=True, interval=350)
        self.debounce.timeout.connect(self.start)
        self.edit.textChanged.connect(lambda *_: self.debounce.start())
        self.tick = QTimer(self, interval=0)
        self.tick.timeout.connect(self._scan)
        self.view = None
        self.rx = None
        self.text = None
        self.order = []          # (עמוד, מספר) לפי סדר המסמך
        self.pos = -1            # מיקום בתוך order
        self.page = 0            # העמוד הבא לסריקה
        self.want_first = False  # לקפוץ לתוצאה הראשונה שנמצאת מהעמוד הנוכחי והלאה
        self.from_page = 0
        self.hide()

    def _tb(self, text, tip, slot):
        b = QToolButton()
        b.setText(text)
        b.setToolTip(tip)
        b.setAutoRaise(True)
        b.clicked.connect(slot)
        self.addWidget(b)
        return b

    # ----- פתיחה וסגירה
    def open_bar(self):
        self.show()
        self.edit.setFocus()
        self.edit.selectAll()
        if self.edit.text().strip() and (self.text is None or self._stale()):
            self.start()

    def close_bar(self):
        self.tick.stop()
        self.debounce.stop()
        self._clear_view()
        self.text = None
        self.hide()
        self.main.view.setFocus()

    def _clear_view(self):
        v = self.view
        if v is not None:
            try:
                v.search_hits = {}
                v.search_cur = None
                v.viewport().update()
            except RuntimeError:
                pass

    def view_changed(self):
        """כרטיסייה אחרת או קובץ אחר נפתח: מחפשים מחדש אם הסרגל פתוח."""
        if self.isVisible() and self.edit.text().strip() and self._stale():
            self.start()

    def _stale(self):
        v = self.main.view
        return self.view is not v or getattr(self, "gen", None) != getattr(v, "docgen", None)

    def eventFilter(self, obj, ev):
        if obj is self.edit and ev.type() == QEvent.KeyPress:
            k = ev.key()
            if k in (Qt.Key_Return, Qt.Key_Enter):
                if self.debounce.isActive() or self.text != self.edit.text().strip() or self._stale():
                    self.debounce.stop()
                    self.start()
                else:
                    self.go(-1 if ev.modifiers() & Qt.ShiftModifier else 1)
                return True
            if k == Qt.Key_Escape:
                self.close_bar()
                return True
        return super().eventFilter(obj, ev)

    # ----- סריקה
    def start(self):
        self.tick.stop()
        self._clear_view()
        v = self.main.view
        self.view = v
        self.gen = getattr(v, "docgen", None)
        self.text = self.edit.text().strip()
        self.rx = compile_pattern(self.text)
        self.order = []
        self.pos = -1
        self.page = 0
        v.search_hits = {}
        v.search_cur = None
        if not self.rx or not v.sizes:
            self.count.setText("" if not self.text else "אין קובץ פתוח")
            v.viewport().update()
            return
        self.from_page = max(0, v._cur_page)
        self.want_first = True
        self.count.setText("מחפש…")
        self.tick.start()

    def _scan(self):
        v = self.view
        try:
            n = len(v.sizes)
            doc = v.doc
        except (RuntimeError, AttributeError):
            self.tick.stop()
            return
        t0 = time.perf_counter()
        changed = False
        while self.page < n and time.perf_counter() - t0 < self.BUDGET:
            i = self.page
            self.page += 1
            try:
                hits = page_hits(doc[i], self.rx)
            except Exception:
                hits = []
            if hits:
                v.search_hits[i] = hits
                self.order.extend((i, k) for k in range(len(hits)))
                changed = True
                if self.want_first and i >= self.from_page:
                    self.want_first = False
                    self.pos = len(self.order) - len(hits)
                    self._show()
        done = self.page >= n
        if done:
            self.tick.stop()
            if self.want_first and self.order:          # אין תוצאה אחרי העמוד הנוכחי – חוזרים להתחלה
                self.want_first = False
                self.pos = 0
                self._show()
        if changed:
            v.viewport().update()
        self._count(done)

    def _count(self, done=True):
        m = len(self.order)
        if not m:
            self.count.setText("לא נמצא" if done else f"מחפש… (עמוד {self.page})")
            self.count.setStyleSheet("color:#c8202f;" if done else "")
            return
        self.count.setStyleSheet("")
        cur = f"{self.pos + 1} מתוך " if self.pos >= 0 else ""
        pages = len(self.view.search_hits)
        self.count.setText(f"{cur}{m} תוצאות ב-{pages} עמודים" + ("" if done else "  (ממשיך לחפש…)"))

    # ----- מעבר בין תוצאות
    def go(self, d):
        if self._stale() or self.text != self.edit.text().strip():
            self.start()
            return
        if not self.order:
            return
        self.want_first = False
        self.pos = (self.pos + d) % len(self.order) if self.pos >= 0 else (0 if d > 0 else len(self.order) - 1)
        self._show()
        self._count(self.page >= len(self.view.sizes))

    def _show(self):
        v = self.view
        i, k = self.order[self.pos]
        v.search_cur = (i, k)
        h = v.search_hits[i][k]
        r = v.page_rect(i)
        z = v.zoom
        cx, cy = r.x() + (h.x0 + h.x1) / 2 * z, r.y() + (h.y0 + h.y1) / 2 * z
        hs, vs = v.horizontalScrollBar(), v.verticalScrollBar()
        vw, vh = v.viewport().width(), v.viewport().height()
        if not (hs.value() + 40 < cx < hs.value() + vw - 40):
            hs.setValue(int(cx - vw / 2))
        if not (vs.value() + 40 < cy < vs.value() + vh - 40):
            vs.setValue(int(cy - vh / 2))
        v.viewport().update()
