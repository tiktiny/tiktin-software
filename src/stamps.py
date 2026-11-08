# חותמות: שתי תמונות שנשמרות פעם אחת, צביעה בשחור או אדום, וחיפוש מקום פנוי בכל עמוד.
import base64
from PySide6.QtCore import Qt, QSettings, QBuffer, QByteArray, QIODevice
from PySide6.QtGui import QImage, QPainter, QColor
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
                               QButtonGroup, QWidget)

MAX_SIDE = 900
_masks = {}       # slot -> QImage (Alpha8)
_colored = {}     # (slot, color) -> QImage
_png = {}         # (slot, color) -> bytes


def _st():
    return QSettings("Tiktin", "TiktinPDF")


def make_mask(img):
    """הופך תמונת חותמת למסכה: דיו כהה = אטום, נייר לבן או רקע שקוף = שקוף. חותך שוליים ריקים."""
    img = img.convertToFormat(QImage.Format_ARGB32)
    if max(img.width(), img.height()) > MAX_SIDE:
        img = img.scaled(MAX_SIDE, MAX_SIDE, Qt.KeepAspectRatio, Qt.SmoothTransformation)
    w, h = img.width(), img.height()
    src = bytes(img.constBits())[: img.bytesPerLine() * h]
    bpl = img.bytesPerLine()
    out = bytearray(w * h)
    for y in range(h):
        row = y * bpl
        o = y * w
        for x in range(w):
            i = row + x * 4
            b, g, r, a = src[i], src[i + 1], src[i + 2], src[i + 3]
            if a < 8:
                continue
            lum = (r * 299 + g * 587 + b * 114) // 1000
            if lum >= 235:
                continue
            v = (235 - lum) * 255 // 150
            out[o + x] = min(255, v) * a // 255
    # חיתוך לשטח הדיו
    xs0, ys0, xs1, ys1 = w, h, -1, -1
    for y in range(h):
        row = out[y * w:(y + 1) * w]
        if max(row) > 24:
            ys0 = min(ys0, y)
            ys1 = y
            for x in range(w):
                if row[x] > 24:
                    xs0 = min(xs0, x)
                    break
            for x in range(w - 1, -1, -1):
                if row[x] > 24:
                    xs1 = max(xs1, x)
                    break
    if ys1 < 0:
        return None
    # נשמר כתמונה אפורה (ערך = אטימות), נקרא בחזרה כמסכת שקיפות
    m = QImage(bytes(out), w, h, w, QImage.Format_Grayscale8).copy()
    return m.copy(xs0, ys0, xs1 - xs0 + 1, ys1 - ys0 + 1)


def _to_png(img):
    ba = QByteArray()
    buf = QBuffer(ba)
    buf.open(QIODevice.WriteOnly)
    img.save(buf, "PNG")
    buf.close()
    return bytes(ba)


def load_file(slot, path):
    img = QImage(path)
    if img.isNull():
        return False
    m = make_mask(img)
    if m is None:
        return False
    _st().setValue(f"stamp{slot}", base64.b64encode(_to_png(m)).decode())
    _masks.pop(slot, None)
    for k in [k for k in _colored if k[0] == slot]:
        _colored.pop(k, None)
        _png.pop(k, None)
    return True


_extra = {}       # חותמות שנטענו מתוך קובץ PDF (מפתח -> PNG)


def register(key, png):
    _extra[key] = png
    _masks.pop(key, None)


def mask_png(slot):
    """ה-PNG של מסכת החותמת (לשמירה בתוך הקובץ)."""
    if slot in _extra:
        return _extra[slot]
    raw = _st().value(f"stamp{slot}", "")
    return base64.b64decode(raw) if raw else b""


def mask(slot):
    if slot not in _masks:
        raw = base64.b64encode(_extra[slot]).decode() if slot in _extra else _st().value(f"stamp{slot}", "")
        m = None
        if raw:
            g = QImage.fromData(base64.b64decode(raw), "PNG")
            if not g.isNull():
                m = g.convertToFormat(QImage.Format_Grayscale8)
                m.reinterpretAsFormat(QImage.Format_Alpha8)
        _masks[slot] = m
    return _masks[slot]


def has(slot):
    return mask(slot) is not None


def aspect(slot):
    m = mask(slot)
    return m.height() / m.width() if m is not None and m.width() else 0.5


def colored(slot, color):
    key = (slot, QColor(color).name())
    if key not in _colored:
        m = mask(slot)
        if m is None:
            return None
        img = QImage(m.size(), QImage.Format_ARGB32_Premultiplied)
        img.fill(QColor(color))
        p = QPainter(img)
        p.setCompositionMode(QPainter.CompositionMode_DestinationIn)
        p.drawImage(0, 0, m)
        p.end()
        _colored[key] = img
    return _colored[key]


def png_bytes(slot, color):
    key = (slot, QColor(color).name())
    if key not in _png:
        img = colored(slot, color)
        _png[key] = _to_png(img.convertToFormat(QImage.Format_ARGB32)) if img is not None else b""
    return _png[key]


# ---------------------------------------------------------------- free spot
def find_free_spot(page, W, H, cx, cy, margin=4.0):
    """מחפש מקום פנוי מטקסט, קרוב ככל האפשר ל-(cx, cy), לחותמת ברוחב W וגובה H (נקודות, עמוד מוצג)."""
    import pymupdf
    pr = page.rect
    PW, PH = pr.width, pr.height
    cell = max(2.0, min(W, H) / 8.0)
    nx, ny = int(PW / cell) + 1, int(PH / cell) + 1
    grid = bytearray(nx * ny)
    rm = page.rotation_matrix
    try:
        words = page.get_text("words")
    except Exception:
        words = []
    for w_ in words:
        r = (pymupdf.Rect(w_[:4]) * rm).normalize() if page.rotation else pymupdf.Rect(w_[:4])
        x0, y0 = max(0, int((r.x0 - 1) / cell)), max(0, int((r.y0 - 1) / cell))
        x1, y1 = min(nx - 1, int((r.x1 + 1) / cell)), min(ny - 1, int((r.y1 + 1) / cell))
        for yy in range(y0, y1 + 1):
            base = yy * nx
            for xx in range(x0, x1 + 1):
                grid[base + xx] = 1
    # טבלת סכומים מצטברים: בדיקת מלבן ב-O(1)
    sat = [0] * ((nx + 1) * (ny + 1))
    for yy in range(ny):
        run = 0
        a = (yy + 1) * (nx + 1)
        b = yy * (nx + 1)
        g0 = yy * nx
        for xx in range(nx):
            run += grid[g0 + xx]
            sat[a + xx + 1] = sat[b + xx + 1] + run

    def busy(x, y):
        gx0, gy0 = int(x / cell), int(y / cell)
        gx1, gy1 = min(nx, int((x + W) / cell) + 1), min(ny, int((y + H) / cell) + 1)
        n1 = nx + 1
        return sat[gy1 * n1 + gx1] - sat[gy0 * n1 + gx1] - sat[gy1 * n1 + gx0] + sat[gy0 * n1 + gx0]

    def inside(x, y):
        return margin <= x and margin <= y and x + W <= PW - margin and y + H <= PH - margin

    x0, y0 = cx - W / 2, cy - H / 2
    x0 = min(max(x0, margin), PW - margin - W)
    y0 = min(max(y0, margin), PH - margin - H)
    if inside(x0, y0) and busy(x0, y0) == 0:
        return x0 + W / 2, y0 + H / 2, True
    step = max(cell, min(W, H) / 4.0)
    maxr = int(max(PW, PH) / step) + 1
    for ring in range(1, maxr):
        best = None
        for i in range(-ring, ring + 1):
            for j in (-ring, ring):
                for dx, dy in ((i, j), (j, i)):
                    x, y = x0 + dx * step, y0 + dy * step
                    if inside(x, y) and busy(x, y) == 0:
                        d = dx * dx + dy * dy
                        if best is None or d < best[0]:
                            best = (d, x, y)
        if best:
            return best[1] + W / 2, best[2] + H / 2, True
    return cx, cy, False


# ---------------------------------------------------------------- dialog
class StampDialog(QDialog):
    """בחירת צבע החותמת ואם להוסיף אותה לעמוד הנוכחי או לכל העמודים."""

    def __init__(self, parent, slot, color, n_pages):
        super().__init__(parent)
        self.setWindowTitle(f"חותמת {slot}")
        self.setLayoutDirection(Qt.RightToLeft)
        st = _st()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 18, 20, 18)
        lay.setSpacing(14)

        def seg(label, opts, cur):
            row = QHBoxLayout()
            lab = QLabel(label)
            lab.setMinimumWidth(70)
            row.addWidget(lab)
            box = QWidget()
            h = QHBoxLayout(box)
            h.setContentsMargins(0, 0, 0, 0)
            h.setSpacing(0)
            grp = QButtonGroup(self)
            for k, (key, text) in enumerate(opts):
                b = QPushButton(text)
                b.setObjectName("seg")
                b.setCheckable(True)
                b.setProperty("key", key)
                b.setMinimumWidth(110)
                grp.addButton(b, k)
                h.addWidget(b)
                if key == cur:
                    b.setChecked(True)
            if grp.checkedButton() is None:
                grp.buttons()[0].setChecked(True)
            row.addWidget(box)
            row.addStretch(1)
            lay.addLayout(row)
            return grp

        self.color_grp = seg("צבע", [("#000000", "שחור"), ("#d0021b", "אדום")],
                             st.value("stamp_color", color))
        self.where_grp = seg("איפה", [("page", "בעמוד הנוכחי"), ("all", f"בכל העמודים ({n_pages})")],
                             st.value("stamp_where", "page"))
        if n_pages < 2:
            self.where_grp.buttons()[1].setEnabled(False)
            self.where_grp.buttons()[0].setChecked(True)
        tip = QLabel("אחרי האישור מקליקים על השרטוט במקום החותמת.\n"
                     "בכל העמודים: בשאר העמודים החותמת תונח במקום פנוי מטקסט, קרוב לאותו מקום.")
        tip.setStyleSheet("color:#5b6470;")
        tip.setAlignment(Qt.AlignAbsolute | Qt.AlignRight)
        lay.addWidget(tip)
        btns = QHBoxLayout()
        btns.addStretch(1)
        cancel = QPushButton("ביטול")
        cancel.setObjectName("plainBtn")
        ok = QPushButton("המשך להצבה")
        ok.setObjectName("primaryBtn")
        ok.setDefault(True)
        btns.addWidget(cancel)
        btns.addWidget(ok)
        lay.addLayout(btns)
        cancel.clicked.connect(self.reject)
        ok.clicked.connect(self._ok)

    def _ok(self):
        self.color = self.color_grp.checkedButton().property("key")
        self.where = self.where_grp.checkedButton().property("key")
        st = _st()
        st.setValue("stamp_color", self.color)
        st.setValue("stamp_where", self.where)
        self.accept()
