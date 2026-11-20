# מנוע ה-PDF של הגרסה המסחרית.
# אותו ממשק (החלק שהתוכנה משתמשת בו) כמו המנוע של גרסת המשרד, אבל בנוי רק על רכיבים
# שמותר למכור איתם תוכנה בקוד סגור:
#   * PDFium (המנוע של כרום, רישיון Apache/BSD) — תצוגה, טקסט, קווי השרטוט
#   * pikepdf (רישיון MPL) — שינוי הקובץ ושמירה
#   * Qt (רישיון LGPL) — תמונות
# הקובץ נקרא pymupdf.py כדי שאותו קוד של התוכנה ירוץ בלי שינוי; בגרסה המסחרית המנוע המקורי לא מותקן בכלל.
import builtins
import io
import itertools
import math
import os
import ctypes

from collections import OrderedDict

import pypdfium2 as _pd
import pypdfium2.raw as _R

VersionBind = "commercial-pdfium"
__doc__ = "commercial engine (PDFium + pikepdf)"

csRGB = "rgb"
csGRAY = "gray"
LINK_NONE, LINK_GOTO, LINK_URI, LINK_LAUNCH, LINK_NAMED, LINK_GOTOR = 0, 1, 2, 3, 4, 5
PDF_REDACT_IMAGE_NONE = 0
PDF_REDACT_IMAGE_REMOVE = 1
PDF_REDACT_IMAGE_PIXELS = 2
PDF_REDACT_LINE_ART_NONE = 0
PDF_REDACT_LINE_ART_REMOVE_IF_COVERED = 1
PDF_REDACT_LINE_ART_REMOVE_IF_TOUCHED = 2
PDF_REDACT_TEXT_REMOVE = 0
PDF_REDACT_TEXT_NONE = 1


class _Tools:
    aa = 8

    def set_graphics_min_line_width(self, w):
        pass

    def set_aa_level(self, n):
        _Tools.aa = n

    def mupdf_display_errors(self, on=None):
        pass

    def mupdf_display_warnings(self, on=None):
        pass


TOOLS = _Tools()
_NAMES = itertools.count(1)


class FileDataError(RuntimeError):
    pass


# ---------------------------------------------------------------- geometry
class Matrix:
    __slots__ = ("a", "b", "c", "d", "e", "f")

    def __init__(self, *args):
        if len(args) == 6:
            self.a, self.b, self.c, self.d, self.e, self.f = map(float, args)
        elif len(args) == 2:
            self.a, self.b, self.c, self.d, self.e, self.f = float(args[0]), 0.0, 0.0, float(args[1]), 0.0, 0.0
        elif len(args) == 1 and hasattr(args[0], "__len__") and len(args[0]) == 6:
            self.a, self.b, self.c, self.d, self.e, self.f = map(float, args[0])
        elif len(args) == 1:          # סיבוב במעלות
            t = math.radians(float(args[0]))
            co, si = math.cos(t), math.sin(t)
            self.a, self.b, self.c, self.d, self.e, self.f = co, si, -si, co, 0.0, 0.0
        else:
            self.a, self.b, self.c, self.d, self.e, self.f = 1.0, 0.0, 0.0, 1.0, 0.0, 0.0

    def __iter__(self):
        return iter((self.a, self.b, self.c, self.d, self.e, self.f))

    def __len__(self):
        return 6

    def __getitem__(self, k):
        return tuple(self)[k]

    def __mul__(self, m):
        # self, ואחריו m (כמו ב-PDF: נקודה * self * m)
        return Matrix(self.a * m.a + self.b * m.c, self.a * m.b + self.b * m.d,
                      self.c * m.a + self.d * m.c, self.c * m.b + self.d * m.d,
                      self.e * m.a + self.f * m.c + m.e, self.e * m.b + self.f * m.d + m.f)

    def inverted(self):
        det = self.a * self.d - self.b * self.c
        if abs(det) < 1e-12:
            return Matrix()
        return Matrix(self.d / det, -self.b / det, -self.c / det, self.a / det,
                      (self.c * self.f - self.d * self.e) / det, (self.b * self.e - self.a * self.f) / det)

    def __invert__(self):
        return self.inverted()

    def apply(self, x, y):
        return x * self.a + y * self.c + self.e, x * self.b + y * self.d + self.f

    def __repr__(self):
        return "Matrix" + repr(tuple(self))


Identity = Matrix()


class Point:
    __slots__ = ("x", "y")

    def __init__(self, *args):
        if len(args) == 1:
            args = tuple(args[0])
        self.x, self.y = (float(args[0]), float(args[1])) if args else (0.0, 0.0)

    def __iter__(self):
        return iter((self.x, self.y))

    def __len__(self):
        return 2

    def __getitem__(self, k):
        return (self.x, self.y)[k]

    def __mul__(self, m):
        return Point(*m.apply(self.x, self.y))

    def __add__(self, o):
        return Point(self.x + o[0], self.y + o[1])

    def __sub__(self, o):
        return Point(self.x - o[0], self.y - o[1])

    def __repr__(self):
        return f"Point({self.x}, {self.y})"


class Rect:
    __slots__ = ("x0", "y0", "x1", "y1")

    def __init__(self, *args):
        if len(args) == 1:
            args = tuple(args[0])
        if len(args) == 2:
            args = (args[0][0], args[0][1], args[1][0], args[1][1])
        if not args:
            args = (0, 0, 0, 0)
        self.x0, self.y0, self.x1, self.y1 = map(float, args[:4])

    width = property(lambda s: abs(s.x1 - s.x0))
    height = property(lambda s: abs(s.y1 - s.y0))
    tl = property(lambda s: Point(s.x0, s.y0))
    br = property(lambda s: Point(s.x1, s.y1))
    top_left = tl
    bottom_right = br
    is_empty = property(lambda s: s.x0 >= s.x1 or s.y0 >= s.y1)

    def __iter__(self):
        return iter((self.x0, self.y0, self.x1, self.y1))

    def __len__(self):
        return 4

    def __getitem__(self, k):
        return (self.x0, self.y0, self.x1, self.y1)[k]

    def normalize(self):
        self.x0, self.x1 = min(self.x0, self.x1), max(self.x0, self.x1)
        self.y0, self.y1 = min(self.y0, self.y1), max(self.y0, self.y1)
        return self

    def __mul__(self, m):
        pts = [m.apply(x, y) for x, y in ((self.x0, self.y0), (self.x1, self.y0), (self.x0, self.y1), (self.x1, self.y1))]
        xs, ys = [p[0] for p in pts], [p[1] for p in pts]
        return Rect(min(xs), min(ys), max(xs), max(ys))

    def contains(self, o):
        if isinstance(o, Point) or len(o) == 2:
            return self.x0 <= o[0] <= self.x1 and self.y0 <= o[1] <= self.y1
        return self.x0 <= o[0] and self.y0 <= o[1] and o[2] <= self.x1 and o[3] <= self.y1

    __contains__ = contains

    def intersect(self, r):
        self.x0, self.y0 = max(self.x0, r[0]), max(self.y0, r[1])
        self.x1, self.y1 = min(self.x1, r[2]), min(self.y1, r[3])
        return self

    def intersects(self, r):
        return self.x0 < r[2] and r[0] < self.x1 and self.y0 < r[3] and r[1] < self.y1

    def include_point(self, p):
        self.x0, self.y0 = min(self.x0, p[0]), min(self.y0, p[1])
        self.x1, self.y1 = max(self.x1, p[0]), max(self.y1, p[1])
        return self

    @property
    def irect(self):
        return Rect(math.floor(self.x0), math.floor(self.y0), math.ceil(self.x1), math.ceil(self.y1))

    def __repr__(self):
        return f"Rect({self.x0}, {self.y0}, {self.x1}, {self.y1})"


Quad = Rect
IRect = Rect


def _rot_matrix(r, w, h):
    """לא מסובב → מסובב (כמו במנוע המקורי). w, h = רוחב וגובה העמוד הלא מסובב."""
    r %= 360
    if r == 90:
        return Matrix(0, 1, -1, 0, h, 0)
    if r == 180:
        return Matrix(-1, 0, 0, -1, w, h)
    if r == 270:
        return Matrix(0, -1, 1, 0, 0, w)
    return Matrix()


# ---------------------------------------------------------------- pixmap
class Pixmap:
    """תמונת עמוד (או תמונה מקובץ — רק מידות ורזולוציה)."""

    def __init__(self, *args, **kw):
        self.x = self.y = 0
        self.xres = self.yres = 96
        self.alpha = 0
        if len(args) == 1 and isinstance(args[0], (str, bytes, bytearray)) and not kw:
            from PySide6.QtGui import QImageReader
            src = args[0]
            if isinstance(src, (bytes, bytearray)):
                from PySide6.QtCore import QBuffer, QByteArray, QIODevice
                self._buf = QBuffer()
                self._buf.setData(QByteArray(bytes(src)))
                self._buf.open(QIODevice.ReadOnly)
                rd = QImageReader(self._buf)
            else:
                rd = QImageReader(src)
            img = rd.read()
            if img.isNull():
                raise FileDataError("לא ניתן לקרוא את התמונה")
            self.width, self.height = img.width(), img.height()
            dx, dy = img.dotsPerMeterX(), img.dotsPerMeterY()
            self.xres = int(round(dx * 0.0254)) if dx > 0 else 72
            self.yres = int(round(dy * 0.0254)) if dy > 0 else 72
            self.n = 3
            self.stride = self.width * 3
            self.samples = b""
            return
        self.width, self.height, self.n, self.stride, self.samples = 0, 0, 3, 0, b""

    @property
    def samples_mv(self):
        return memoryview(self.samples)

    @property
    def irect(self):
        return Rect(self.x, self.y, self.x + self.width, self.y + self.height)

    def tobytes(self, output="png"):
        from PySide6.QtCore import QBuffer, QByteArray, QIODevice
        from PySide6.QtGui import QImage
        fmt = QImage.Format_Grayscale8 if self.n == 1 else QImage.Format_RGB888
        img = QImage(self.samples, self.width, self.height, self.stride, fmt)
        ba = QByteArray()
        b = QBuffer(ba)
        b.open(QIODevice.WriteOnly)
        img.save(b, "PNG" if output.lower() == "png" else output.upper())
        b.close()
        return bytes(ba)

    def save(self, path, output=None):
        with builtins.open(path, "wb") as f:
            f.write(self.tobytes(output or os.path.splitext(path)[1][1:] or "png"))


def _render_px(pdpage, scale_x, scale_y, x0, y0, w, h, gray, aa):
    """רינדור אזור פיקסלים מדויק של העמוד (במערכת המסובבת, כמו שהוא מוצג)."""
    fmt = _R.FPDFBitmap_Gray if gray else _R.FPDFBitmap_BGR
    bmp = _R.FPDFBitmap_CreateEx(w, h, fmt, None, 0)
    if not bmp:
        raise MemoryError("אין מספיק זיכרון לתמונת העמוד")
    try:
        _R.FPDFBitmap_FillRect(bmp, 0, 0, w, h, 0xFFFFFFFF)
        m = _R.FS_MATRIX(scale_x, 0, 0, scale_y, -x0, -y0)
        cl = _R.FS_RECTF(0, 0, w, h)
        flags = _R.FPDF_ANNOT
        if not gray:
            flags |= _R.FPDF_REVERSE_BYTE_ORDER
        if aa is not None and aa < 1:
            flags |= _R.FPDF_RENDER_NO_SMOOTHPATH | _R.FPDF_RENDER_NO_SMOOTHTEXT
        _R.FPDF_RenderPageBitmapWithMatrix(bmp, pdpage.raw, m, cl, flags)
        stride = _R.FPDFBitmap_GetStride(bmp)
        data = ctypes.string_at(_R.FPDFBitmap_GetBuffer(bmp), stride * h)
    finally:
        _R.FPDFBitmap_Destroy(bmp)
    return data, stride


# אריחי-על: בהגדלה, כמה אריחים סמוכים מצוירים במעבר אחד על תוכן העמוד ונשמרים לשימוש חוזר.
# בשרטוט כבד רוב הזמן הולך על המעבר על כל הקווים, לא על הפיקסלים — כך חוסכים מעברים.
SUPER = 1536
USE_SUPER = False
_super = OrderedDict()
_SUPER_MAX = 6


def _render(pdpage, scale_x, scale_y, clip, gray, aa, key=None):
    pw, ph = pdpage.get_size()                 # כבר כולל את סיבוב העמוד
    if clip is None:
        clip = Rect(0, 0, pw, ph)
    c = Rect(max(0.0, clip[0]), max(0.0, clip[1]), min(pw, clip[2]), min(ph, clip[3]))
    if c.is_empty:
        c = Rect(clip)
    x0, y0 = math.floor(c.x0 * scale_x + 1e-6), math.floor(c.y0 * scale_y + 1e-6)
    x1, y1 = math.ceil(c.x1 * scale_x - 1e-6), math.ceil(c.y1 * scale_y - 1e-6)
    w, h = max(1, x1 - x0), max(1, y1 - y0)
    pix = Pixmap()
    pix.x, pix.y, pix.width, pix.height = x0, y0, w, h
    pix.n = 1 if gray else 3
    full_w, full_h = math.ceil(pw * scale_x - 1e-6), math.ceil(ph * scale_y - 1e-6)
    sx, sy = x0 // SUPER, y0 // SUPER
    if key is not None and w <= 1024 and h <= 1024 and (x1 - 1) // SUPER == sx and (y1 - 1) // SUPER == sy:
        k = (key, round(scale_x, 6), round(scale_y, 6), gray, aa, sx, sy)
        hit = _super.get(k)
        if hit is None:
            ox, oy = sx * SUPER, sy * SUPER
            sw, shh = min(SUPER, full_w - ox), min(SUPER, full_h - oy)
            data, stride = _render_px(pdpage, scale_x, scale_y, ox, oy, sw, shh, gray, aa)
            hit = _super[k] = (data, stride, ox, oy)
            while len(_super) > _SUPER_MAX:
                _super.popitem(last=False)
        else:
            _super.move_to_end(k)
        data, stride, ox, oy = hit
        bpp = 1 if gray else 3
        a = (x0 - ox) * bpp
        rows = [data[(y - oy) * stride + a: (y - oy) * stride + a + w * bpp] for y in range(y0, y0 + h)]
        pix.samples = b"".join(rows)
        pix.stride = w * bpp
        return pix
    data, stride = _render_px(pdpage, scale_x, scale_y, x0, y0, w, h, gray, aa)
    pix.samples, pix.stride = data, stride
    return pix


def clear_cache():
    _super.clear()


# ---------------------------------------------------------------- text
def _is_space(ch):
    return ch in " \t\r\n\x00\x02\xa0\ufffe"


class _TextPage:
    def __init__(self, page):
        self.page = page

    def extractWORDS(self):
        return self.page.get_text("words")

    def extractText(self):
        return self.page.get_text("text")


def TextPage(tp):
    return tp


# ---------------------------------------------------------------- drawing (תוכן שמוסיפים לעמוד)
def _num(v):
    s = ("%.4f" % v).rstrip("0").rstrip(".")
    return s if s not in ("", "-0") else "0"


def _col(c, stroke):
    if c is None:
        return ""
    if isinstance(c, (int, float)):
        c = (c, c, c)
    return " ".join(_num(x) for x in c) + (" RG" if stroke else " rg")


class Shape:
    """ציור קווים על עמוד (במערכת העמוד הלא מסובבת, כמו במנוע המקורי)."""

    def __init__(self, page):
        self.page = page
        self.draw_cont = []
        self.text_cont = []
        self.last = None

    def _pt(self, p):
        return _num(p[0]) + " " + _num(p[1])

    def draw_line(self, p1, p2):
        self.draw_cont.append(f"{self._pt(p1)} m {self._pt(p2)} l")
        self.last = p2
        return p2

    def draw_polyline(self, pts):
        pts = list(pts)
        if pts:
            self.draw_cont.append(f"{self._pt(pts[0])} m " + " ".join(f"{self._pt(p)} l" for p in pts[1:]))
        return pts[-1] if pts else None

    def draw_bezier(self, p1, p2, p3, p4):
        self.draw_cont.append(f"{self._pt(p1)} m {self._pt(p2)} {self._pt(p3)} {self._pt(p4)} c")
        return p4

    def draw_rect(self, r):
        r = Rect(r)
        self.draw_cont.append(f"{_num(r.x0)} {_num(r.y0)} {_num(r.width)} {_num(r.height)} re")
        return r.tl

    def draw_oval(self, r):
        r = Rect(r)
        cx, cy, rx, ry = (r.x0 + r.x1) / 2, (r.y0 + r.y1) / 2, r.width / 2, r.height / 2
        k = 0.5523
        self.draw_cont.append(
            f"{_num(cx + rx)} {_num(cy)} m "
            f"{_num(cx + rx)} {_num(cy + ry * k)} {_num(cx + rx * k)} {_num(cy + ry)} {_num(cx)} {_num(cy + ry)} c "
            f"{_num(cx - rx * k)} {_num(cy + ry)} {_num(cx - rx)} {_num(cy + ry * k)} {_num(cx - rx)} {_num(cy)} c "
            f"{_num(cx - rx)} {_num(cy - ry * k)} {_num(cx - rx * k)} {_num(cy - ry)} {_num(cx)} {_num(cy - ry)} c "
            f"{_num(cx + rx * k)} {_num(cy - ry)} {_num(cx + rx)} {_num(cy - ry * k)} {_num(cx + rx)} {_num(cy)} c")
        return Point(cx, cy)

    def draw_circle(self, c, r):
        return self.draw_oval(Rect(c[0] - r, c[1] - r, c[0] + r, c[1] + r))

    def finish(self, width=1, color=(0,), fill=None, lineCap=0, lineJoin=0, dashes=None,
               closePath=True, even_odd=False, morph=None, stroke_opacity=1, fill_opacity=1, oc=0, **kw):
        if not self.draw_cont:
            return
        ops = ["q", f"{_num(width)} w", f"{int(lineCap)} J", f"{int(lineJoin)} j"]
        if dashes:
            ops.append(dashes + " d")
        if color is not None:
            ops.append(_col(color, True))
        if fill is not None:
            ops.append(_col(fill, False))
        ops.extend(self.draw_cont)
        if closePath:
            ops.append("h")
        if fill is not None and color is not None:
            ops.append("B*" if even_odd else "B")
        elif fill is not None:
            ops.append("f*" if even_odd else "f")
        else:
            ops.append("S")
        ops.append("Q")
        self.text_cont.append("\n".join(ops))
        self.draw_cont = []

    def commit(self, overlay=True):
        if self.text_cont:
            self.page._add_content("\n".join(self.text_cont), overlay=overlay)
        self.text_cont = []


# ---------------------------------------------------------------- page
class Page:
    def __init__(self, doc, number):
        self.parent = doc
        self.number = number
        self._redacts = []

    # --- חלקים מהמנועים
    @property
    def _pd(self):
        return self.parent._pd_page(self.number)

    @property
    def _pk(self):
        return self.parent._pk_doc().pages[self.number]

    def _box(self):
        """CropBox (במערכת PDF, y למעלה) ומידות לא מסובבות."""
        return self.parent._box(self.number)

    @property
    def rotation(self):
        return self.parent._rot(self.number)

    def set_rotation(self, r):
        self._pk.obj["/Rotate"] = int(r) % 360
        self.parent._edited()

    @property
    def cropbox(self):
        x0, y0, x1, y1 = self._box()
        return Rect(0, 0, x1 - x0, y1 - y0)

    @property
    def mediabox(self):
        return self.cropbox

    @property
    def rect(self):
        if not (self.parent._dirty and self.parent._pk is not None):
            w, h = self.parent._size(self.number)
            return Rect(0, 0, w, h)
        x0, y0, x1, y1 = self._box()
        w, h = x1 - x0, y1 - y0
        return Rect(0, 0, h, w) if self.rotation in (90, 270) else Rect(0, 0, w, h)

    bound = lambda self: self.rect      # noqa: E731

    @property
    def rotation_matrix(self):
        x0, y0, x1, y1 = self._box()
        return _rot_matrix(self.rotation, x1 - x0, y1 - y0)

    @property
    def derotation_matrix(self):
        return self.rotation_matrix.inverted()

    @property
    def transformation_matrix(self):
        x0, y0, x1, y1 = self._box()
        return Matrix(1, 0, 0, -1, -x0, y1)

    def _user(self):
        """מהמערכת של התוכנה (לא מסובבת, y למטה, מפינת ה-CropBox) למערכת PDF."""
        x0, y0, x1, y1 = self._box()
        return Matrix(1, 0, 0, -1, x0, y1)

    # --- תצוגה
    def get_pixmap(self, matrix=None, clip=None, alpha=False, colorspace=None, dpi=None, annots=True):
        m = matrix or Matrix()
        if dpi:
            m = Matrix(dpi / 72.0, dpi / 72.0)
        gray = colorspace in (csGRAY, "gray", "GRAY")
        # אריחי-על כבויים: במדידה הם האטו שרטוטים רגילים והגדילו את הזיכרון
        key = (id(self.parent), self.parent._gen, self.number) if (self.parent._tiles and USE_SUPER) else None
        return _render(self._pd, m.a, m.d, clip, gray, TOOLS.aa, key)

    def get_displaylist(self):
        self.parent._tiles = True      # נקרא רק מתהליך הרינדור של האריחים
        return self

    def get_textpage(self, *a, **k):
        return _TextPage(self)

    # --- טקסט
    def _chars(self):
        """(תו, x0, y0, x1, y1, זווית) לכל תו, במערכת הלא מסובבת של התוכנה."""
        cache = getattr(self, "_chars_cache", None)
        if cache is not None:
            return cache
        tp = self._pd.get_textpage()
        x0b, y0b, x1b, y1b = self._box()
        out = []
        try:
            n = tp.count_chars()
            raw = tp.raw
            L, B, Rr, T = ctypes.c_double(), ctypes.c_double(), ctypes.c_double(), ctypes.c_double()
            for i in range(n):
                u = _R.FPDFText_GetUnicode(raw, i)
                ch = chr(u) if u else ""
                if not ch or _is_space(ch) or _R.FPDFText_IsGenerated(raw, i) == 1:
                    out.append((" ", 0, 0, 0, 0, 0))
                    continue
                _R.FPDFText_GetCharBox(raw, i, L, Rr, B, T)
                ang = _R.FPDFText_GetCharAngle(raw, i)
                out.append((ch, L.value - x0b, y1b - T.value, Rr.value - x0b, y1b - B.value,
                            ang if ang >= 0 else 0.0))
        finally:
            tp.close()
        self._chars_cache = out
        return out

    def _words(self):
        words, cur = [], None
        line_no = 0
        last = None
        for ch, a, b, c, d, ang in self._chars():
            if ch == " ":
                if cur:
                    words.append(cur)
                cur = None
                continue
            if cur is not None and last is not None:
                # קפיצה גדולה או שורה אחרת = מילה חדשה
                h = max(d - b, last[3] - last[1], 1.0)
                if abs((b + d) / 2 - (last[1] + last[3]) / 2) > h * 0.6 or \
                        (a - last[2] > h * 0.8 and abs(ang) < 0.01) or abs(ang - last[4]) > 0.05:
                    words.append(cur)
                    cur = None
                    if abs((b + d) / 2 - (last[1] + last[3]) / 2) > h * 0.6:
                        line_no += 1
            if cur is None:
                cur = [a, b, c, d, ch, 0, line_no, 0, ang]
            else:
                cur[0], cur[1] = min(cur[0], a), min(cur[1], b)
                cur[2], cur[3] = max(cur[2], c), max(cur[3], d)
                cur[4] += ch
            last = (a, b, c, d, ang)
        if cur:
            words.append(cur)
        for k, w in enumerate(words):
            w[7] = k
        return words

    def get_text(self, option="text", flags=None, clip=None, sort=False, **kw):
        if option in ("text", None):
            tp = self._pd.get_textpage()
            try:
                return tp.get_text_range()
            finally:
                tp.close()
        if option == "words":
            ws = [tuple(w[:8]) for w in self._words()]
            if clip is not None:
                c = Rect(clip)
                ws = [w for w in ws if c.intersects(w)]
            return ws
        if option in ("dict", "rawdict"):
            lines = {}
            for w in self._words():
                lines.setdefault(w[6], []).append(w)
            blocks = []
            for ln, ws in sorted(lines.items()):
                txt = " ".join(w[4] for w in ws)
                x0 = min(w[0] for w in ws)
                y0 = min(w[1] for w in ws)
                x1 = max(w[2] for w in ws)
                y1 = max(w[3] for w in ws)
                blocks.append({"type": 0, "bbox": (x0, y0, x1, y1),
                               "lines": [{"dir": self._line_dir(ws), "bbox": (x0, y0, x1, y1),
                                          "spans": [{"text": txt, "bbox": (x0, y0, x1, y1), "size": y1 - y0}]}]})
            return {"width": self.cropbox.width, "height": self.cropbox.height, "blocks": blocks}
        if option == "blocks":
            return [(w[0], w[1], w[2], w[3], w[4], i, 0) for i, w in enumerate(self._words())]
        return self.get_text("text")

    @staticmethod
    def _line_dir(ws):
        # כיוון השורה לפי זווית התווים (רדיאנים נגד השעון במערכת PDF; אצלנו y למטה)
        ang = ws[0][8] if ws else 0.0
        return (math.cos(ang), -math.sin(ang))

    def get_links(self):
        """קישורים בעמוד: [{"kind", "from" (במערכת המוצגת), "uri" או "page"}] — כמו במנוע המקורי."""
        out = []
        doc = self.parent._pdf.raw
        page = self._pd.raw
        x0b, y0b, x1b, y1b = self._box()
        to_disp = Matrix(1, 0, 0, -1, -x0b, y1b) * self.rotation_matrix
        pos = ctypes.c_int(0)
        link = _R.FPDF_LINK()
        rc = _R.FS_RECTF()
        while _R.FPDFLink_Enumerate(page, pos, link):
            if not _R.FPDFLink_GetAnnotRect(link, rc):
                continue
            r = Rect(rc.left, rc.bottom, rc.right, rc.top) * to_disp
            item = None
            act = _R.FPDFLink_GetAction(link)
            dest = _R.FPDFLink_GetDest(doc, link)
            if act:
                t = _R.FPDFAction_GetType(act)
                if t == _R.PDFACTION_URI:
                    n = _R.FPDFAction_GetURIPath(doc, act, None, 0)
                    if n > 0:
                        buf = ctypes.create_string_buffer(n)
                        _R.FPDFAction_GetURIPath(doc, act, buf, n)
                        uri = buf.raw[:n].rstrip(b"\x00").decode("utf-8", "replace")
                        item = {"kind": LINK_URI, "from": r, "uri": uri}
                elif t in (_R.PDFACTION_GOTO,) and not dest:
                    dest = _R.FPDFAction_GetDest(doc, act)
            if item is None and dest:
                pg = _R.FPDFDest_GetDestPageIndex(doc, dest)
                if pg >= 0:
                    item = {"kind": LINK_GOTO, "from": r, "page": pg}
            if item:
                out.append(item)
        return out

    def search_for(self, needle, quads=False):
        out = []
        for w in self._words():
            if needle.lower() in w[4].lower():
                out.append(Rect(w[:4]))
        return out

    # --- קווי השרטוט
    def get_drawings(self, extended=False):
        return self.get_cdrawings()

    def get_cdrawings(self, extended=None, callback=None):
        x0b, y0b, x1b, y1b = self._box()
        to_app = Matrix(1, 0, 0, -1, -x0b, y1b)
        out = []
        page = self._pd.raw
        X, Y = _R.FS_FLOAT(), _R.FS_FLOAT()
        FM = _R.FS_MATRIX()
        W = _R.FS_FLOAT()
        RGBA = [ctypes.c_uint() for _ in range(4)]

        def mat(obj):
            if _R.FPDFPageObj_GetMatrix(obj, FM):
                return Matrix(FM.a, FM.b, FM.c, FM.d, FM.e, FM.f)
            return Matrix()

        def walk(count, get, parent):
            for i in range(count):
                obj = get(i)
                t = _R.FPDFPageObj_GetType(obj)
                if t == _R.FPDF_PAGEOBJ_FORM:
                    m = mat(obj) * parent
                    walk(_R.FPDFFormObj_CountObjects(obj), lambda k, o=obj: _R.FPDFFormObj_GetObject(o, k), m)
                    continue
                if t != _R.FPDF_PAGEOBJ_PATH:
                    continue
                m = mat(obj) * parent * to_app
                fillmode, stroke = ctypes.c_int(), ctypes.c_int()
                _R.FPDFPath_GetDrawMode(obj, fillmode, stroke)
                if not stroke.value and fillmode.value:
                    kind = "f"
                elif stroke.value and fillmode.value:
                    kind = "fs"
                else:
                    kind = "s"
                width = 1.0
                if _R.FPDFPageObj_GetStrokeWidth(obj, W):
                    sc = math.sqrt(abs(m.a * m.d - m.b * m.c)) or 1.0
                    width = W.value * sc
                color = None
                if _R.FPDFPageObj_GetStrokeColor(obj, *RGBA):
                    color = (RGBA[0].value / 255.0, RGBA[1].value / 255.0, RGBA[2].value / 255.0)
                items = []
                n = _R.FPDFPath_CountSegments(obj)
                start = cur = None
                pend = []
                for k in range(n):
                    sg = _R.FPDFPath_GetPathSegment(obj, k)
                    _R.FPDFPathSegment_GetPoint(sg, X, Y)
                    p = Point(*m.apply(X.value, Y.value))
                    st = _R.FPDFPathSegment_GetType(sg)
                    if st == _R.FPDF_SEGMENT_MOVETO:
                        start = cur = p
                        pend = []
                    elif st == _R.FPDF_SEGMENT_LINETO:
                        if cur is not None:
                            items.append(("l", cur, p))
                        cur = p
                    elif st == _R.FPDF_SEGMENT_BEZIERTO:
                        pend.append(p)
                        if len(pend) == 3:
                            if cur is not None:
                                items.append(("c", cur, pend[0], pend[1], pend[2]))
                            cur = pend[2]
                            pend = []
                    if _R.FPDFPathSegment_GetClose(sg) and start is not None and cur is not None:
                        if abs(cur.x - start.x) > 1e-6 or abs(cur.y - start.y) > 1e-6:
                            items.append(("l", cur, start))
                        cur = start
                if items:
                    xs = [q.x for it in items for q in it[1:]]
                    ys = [q.y for it in items for q in it[1:]]
                    out.append({"items": items, "type": kind, "width": width, "color": color,
                                "rect": Rect(min(xs), min(ys), max(xs), max(ys))})

        walk(_R.FPDFPage_CountObjects(page), lambda k: _R.FPDFPage_GetObject(page, k), Matrix())
        return out

    # --- שינוי העמוד
    def _add_content(self, ops, overlay=True, tag=None):
        """מוסיף פקודות ציור במערכת של התוכנה (לא מסובבת, y למטה)."""
        import pikepdf
        pk = self.parent._pk_doc()
        u = self._user()
        body = f"q {' '.join(_num(v) for v in u)} cm\n{ops}\nQ"
        data = ((tag + b"\n") if tag else b"") + body.encode("latin-1")
        pg = pk.pages[self.number]
        st = pikepdf.Stream(pk, data)
        pg.contents_coalesce() if False else None
        if overlay:
            pg.contents_add(st, prepend=False)
        else:
            pg.contents_add(st, prepend=True)
        self.parent._edited()

    def wrap_contents(self):
        pass

    def is_wrapped(self):
        return True

    def new_shape(self):
        return Shape(self)

    def add_redact_annot(self, quad, text=None, fill=(1, 1, 1), **kw):
        self._redacts.append((Rect(quad), fill if fill is not None else (1, 1, 1)))

    def apply_redactions(self, images=0, graphics=0, text=0):
        """בגרסה המסחרית: האזור מכוסה בלבן (המחיקה האמיתית מתוך הקובץ — בהמשך)."""
        if not self._redacts:
            return False
        ops = []
        for r, fill in self._redacts:
            r = Rect(r).normalize()
            ops.append(f"{_col(fill or (1, 1, 1), False)} {_num(r.x0)} {_num(r.y0)} "
                       f"{_num(r.width)} {_num(r.height)} re f")
        self._redacts = []
        self._add_content("\n".join(ops))
        return True

    def show_pdf_page(self, rect, src, pno=0, clip=None, keep_proportion=True, overlay=True, rotate=0, oc=0, **kw):
        """מציב עמוד מקובץ אחר (או חלק ממנו) במלבן שבעמוד הזה."""
        import pikepdf
        pk = self.parent._pk_doc()
        sp = src._pk_doc().pages[pno]
        sp_page = src[pno]
        sw, sh = sp_page.rect.width, sp_page.rect.height
        c = Rect(clip) if clip is not None else Rect(0, 0, sw, sh)
        r = Rect(rect)
        sx, sy = r.width / max(c.width, 1e-6), r.height / max(c.height, 1e-6)
        if keep_proportion:
            s = min(sx, sy)
            ox = r.x0 + (r.width - c.width * s) / 2
            oy = r.y0 + (r.height - c.height * s) / 2
            sx = sy = s
        else:
            ox, oy = r.x0, r.y0
        # מעמוד המקור (מערכת PDF) → מוצג במקור → מלבן ביעד (מוצג) → מערכת PDF של היעד
        src_user_to_disp = src[pno].transformation_matrix * src[pno].rotation_matrix
        place = Matrix(sx, 0, 0, sy, ox - c.x0 * sx, oy - c.y0 * sy)
        dst_disp_to_user = self.derotation_matrix * self._user()
        total = src_user_to_disp * place * dst_disp_to_user
        form = sp.as_form_xobject(handle_transformations=False)
        if src._pk_doc() is not pk:
            form = pk.copy_foreign(form)
        name = pikepdf.Name(f"/TkPg{next(_NAMES)}")
        pg = pk.pages[self.number]
        res = pg.obj.get("/Resources")
        if res is None:
            pg.obj["/Resources"] = pikepdf.Dictionary()
            res = pg.obj["/Resources"]
        if "/XObject" not in res:
            res["/XObject"] = pikepdf.Dictionary()
        res["/XObject"][name] = form
        # גבול החיתוך, במערכת PDF של היעד
        cr = Rect(ox, oy, ox + c.width * sx, oy + c.height * sy) * dst_disp_to_user
        ops = (f"q {_num(cr.x0)} {_num(cr.y0)} {_num(cr.width)} {_num(cr.height)} re W n "
               f"{' '.join(_num(v) for v in total)} cm {name} Do Q")
        st = pikepdf.Stream(pk, ops.encode("latin-1"))
        pg.contents_add(st, prepend=not overlay)
        self.parent._edited()
        return 0

    def insert_image(self, rect, filename=None, stream=None, pixmap=None, keep_proportion=True,
                     rotate=0, overlay=True, oc=0, **kw):
        """תמונה (PNG/JPG) במלבן שבמערכת המוצגת של העמוד."""
        import pikepdf
        from PySide6.QtGui import QImage
        data = stream if stream is not None else builtins.open(filename, "rb").read()
        img = QImage()
        img.loadFromData(data)
        if img.isNull():
            raise FileDataError("תמונה לא תקינה")
        pk = self.parent._pk_doc()
        xo = _image_xobject(pk, img, data)
        name = pikepdf.Name(f"/TkIm{next(_NAMES)}")
        pg = pk.pages[self.number]
        if "/Resources" not in pg.obj:
            pg.obj["/Resources"] = pikepdf.Dictionary()
        if "/XObject" not in pg.obj.Resources:
            pg.obj.Resources["/XObject"] = pikepdf.Dictionary()
        pg.obj.Resources.XObject[name] = xo
        r = Rect(rect)
        # תמונה: יחידה → מלבן מוצג (y למטה) → מערכת PDF
        m = Matrix(r.width, 0, 0, -r.height, r.x0, r.y1) * self.derotation_matrix * self._user()
        ops = f"q {' '.join(_num(v) for v in m)} cm {name} Do Q"
        pg.contents_add(pikepdf.Stream(pk, ops.encode("latin-1")), prepend=not overlay)
        self.parent._edited()
        return 0

    def get_contents(self):
        return []

    def get_fonts(self, full=False):
        return []

    def get_images(self, full=False):
        return []

    def __repr__(self):
        return f"page {self.number} of {self.parent.name}"


def _image_xobject(pk, qimg, raw=None):
    import pikepdf
    import zlib
    from PySide6.QtGui import QImage
    if raw is not None and raw[:3] == b"\xff\xd8\xff" and not qimg.hasAlphaChannel():
        gray = qimg.isGrayscale()
        return pikepdf.Stream(pk, bytes(raw), Type=pikepdf.Name.XObject, Subtype=pikepdf.Name.Image,
                              Width=qimg.width(), Height=qimg.height(), BitsPerComponent=8,
                              ColorSpace=pikepdf.Name.DeviceGray if gray else pikepdf.Name.DeviceRGB,
                              Filter=pikepdf.Name.DCTDecode)
    im = qimg.convertToFormat(QImage.Format_RGB888)
    w, h = im.width(), im.height()
    bpl = im.bytesPerLine()
    buf = bytes(im.constBits())[:bpl * h]
    rows = b"".join(buf[y * bpl: y * bpl + w * 3] for y in range(h)) if bpl != w * 3 else buf
    xo = pikepdf.Stream(pk, zlib.compress(rows, 6), Type=pikepdf.Name.XObject, Subtype=pikepdf.Name.Image,
                        Width=w, Height=h, BitsPerComponent=8, ColorSpace=pikepdf.Name.DeviceRGB,
                        Filter=pikepdf.Name.FlateDecode)
    if qimg.hasAlphaChannel():
        a = qimg.convertToFormat(QImage.Format_Alpha8)
        abpl = a.bytesPerLine()
        ab = bytes(a.constBits())[:abpl * h]
        arows = b"".join(ab[y * abpl: y * abpl + w] for y in range(h)) if abpl != w else ab
        xo.SMask = pikepdf.Stream(pk, zlib.compress(arows, 6), Type=pikepdf.Name.XObject,
                                  Subtype=pikepdf.Name.Image, Width=w, Height=h, BitsPerComponent=8,
                                  ColorSpace=pikepdf.Name.DeviceGray, Filter=pikepdf.Name.FlateDecode)
    return xo


# ---------------------------------------------------------------- document
MARKS_KEY = "/TiktinMarks"
MARK_TAG = b"%TIKTIN-MARKS"


class Document:
    """קובץ PDF. קריאה ותצוגה דרך PDFium; שינויים דרך pikepdf (נטען רק כשצריך)."""

    def __init__(self, filename=None, stream=None, filetype=None):
        if isinstance(filename, (bytes, bytearray)) and stream is None:
            stream, filename = filename, None
        if filename in ("pdf",) and stream is not None:
            filename = None
        self.name = filename or ""
        self._bytes = bytes(stream) if stream is not None else None
        self._pdf = None          # PDFium
        self._pk = None           # pikepdf
        self._pages = {}
        self._dirty = False
        self._pw = None
        self.needs_pass = False
        self.is_closed = False
        self._image = None
        self._boxes = None
        self._tiles = False       # תהליך הרינדור מפעיל אריחי-על
        self._gen = 0
        if filename and os.path.splitext(filename)[1].lower() in (
                ".png", ".jpg", ".jpeg", ".jfif", ".bmp", ".gif", ".tif", ".tiff", ".webp"):
            self._image = filename
            return
        if filename is None and stream is None:
            import pikepdf
            self._pk = pikepdf.new()
            self._dirty = True
            return
        self._load_pdfium()

    # --- טעינה
    def _src(self):
        return self._bytes if self._bytes is not None else self.name

    def _load_pdfium(self, data=None):
        if self._pdf is not None:
            try:
                self._pdf.close()
            except Exception:
                pass
        self._pages = {}
        self._boxes = None
        src = data if data is not None else self._src()
        try:
            self._pdf = _pd.PdfDocument(src, password=self._pw)
            self.needs_pass = False
        except _pd.PdfiumError as e:
            if "password" in str(e).lower() or getattr(e, "err_code", None) == 4:
                self.needs_pass = True
                self._pdf = None
                return
            raise FileDataError(str(e))
        if data is None and self._has_marks_quick():
            # סימונים שנשמרו בקובץ מוצגים לעריכה מעל השרטוט — העותק הצרוב לא מוצג
            try:
                pk = self._pk_doc()
                buf = io.BytesIO()
                clone = _strip_marks_copy(pk)
                clone.save(buf)
                self._pdf.close()
                self._pdf = _pd.PdfDocument(buf.getvalue(), password=self._pw)
            except Exception:
                pass

    def _has_marks_quick(self):
        """בדיקה מהירה בלי לפענח את הקובץ: האם נשמרו בו סימונים של התוכנה."""
        key = MARKS_KEY.encode()
        try:
            if self._bytes is not None:
                return key in self._bytes
            import mmap
            with builtins.open(self.name, "rb") as f:
                try:
                    mm = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
                except ValueError:
                    return False
                try:
                    return mm.find(key) >= 0
                finally:
                    mm.close()
        except Exception:
            return False

    def authenticate(self, pw):
        self._pw = pw
        try:
            self._load_pdfium()
        except Exception:
            return False
        if self.needs_pass:
            return False
        if self._pk is not None:
            self._pk = None
        return True

    def _pk_doc(self):
        if self._pk is None:
            import pikepdf
            src = self._src()
            self._pk = pikepdf.open(io.BytesIO(src) if isinstance(src, bytes) else src,
                                    password=self._pw or "")
        return self._pk

    def _edited(self):
        self._gen += 1
        self._dirty = True
        self._boxes = None
        self._pages = {}

    def _sync(self):
        """אחרי שינוי: PDFium קורא מחדש את הגרסה המעודכנת."""
        if self._dirty and self._pk is not None:
            buf = io.BytesIO()
            self._pk.save(buf)
            self._pdf_bytes_after_edit = buf.getvalue()
            if self._pdf is not None:
                try:
                    self._pdf.close()
                except Exception:
                    pass
            self._pdf = _pd.PdfDocument(self._pdf_bytes_after_edit, password=self._pw)
            self._pages = {}
            self._boxes = None
            self._dirty = False

    def _pd_page(self, i):
        self._sync()
        p = self._pages.get(i)
        if p is None:
            p = self._pages[i] = self._pdf[i]
        return p

    def _box(self, i):
        if self._dirty and self._pk is not None:
            pg = self._pk.pages[i]
            cb = pg.obj.get("/CropBox") or pg.obj.get("/MediaBox") or pg.mediabox
            x0, y0, x1, y1 = [float(v) for v in cb]
            return min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1)
        if self._boxes is None:
            self._boxes = {}
        b = self._boxes.get(i)
        if b is None:
            p = self._pd_page(i)
            l_, b_, r_, t_ = p.get_cropbox()
            b = self._boxes[i] = (l_, b_, r_, t_)
        return b

    def _size(self, i):
        """מידות העמוד כפי שהוא מוצג (כולל סיבוב), בלי לטעון את תוכן העמוד."""
        self._sync()
        sz = _R.FS_SIZEF()
        if _R.FPDF_GetPageSizeByIndexF(self._pdf.raw, i, sz):
            return sz.width, sz.height
        return self._pd_page(i).get_size()

    def _rot(self, i):
        if self._dirty and self._pk is not None:
            return int(self._pk.pages[i].obj.get("/Rotate", 0)) % 360
        return self._pd_page(i).get_rotation() % 360

    # --- כמו במנוע המקורי
    @property
    def page_count(self):
        if self._image:
            return self._image_frames()
        if self.needs_pass:
            return 0
        if self._dirty and self._pk is not None:
            return len(self._pk.pages)
        return len(self._pdf) if self._pdf is not None else len(self._pk_doc().pages)

    def __len__(self):
        return self.page_count

    def __getitem__(self, i):
        n = self.page_count
        if i < 0:
            i += n
        if not 0 <= i < n:
            raise IndexError("page not in document")
        return Page(self, i)

    def __iter__(self):
        for i in range(self.page_count):
            yield Page(self, i)

    def load_page(self, i=0):
        return self[i]

    def close(self):
        try:
            if self._pdf is not None:
                self._pdf.close()
        except Exception:
            pass
        self._pdf = None
        self._pk = None
        self._pages = {}
        self.is_closed = True

    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()

    @property
    def metadata(self):
        return {}

    @property
    def is_pdf(self):
        return not self._image

    def new_page(self, pno=-1, width=595, height=842):
        import pikepdf
        pk = self._pk_doc()
        pg = pikepdf.Page(pikepdf.Dictionary(Type=pikepdf.Name.Page,
                                             MediaBox=[0, 0, width, height],
                                             Resources=pikepdf.Dictionary(),
                                             Contents=pikepdf.Stream(pk, b"")))
        if pno < 0 or pno >= len(pk.pages):
            pk.pages.append(pg)
            idx = len(pk.pages) - 1
        else:
            pk.pages.insert(pno, pg)
            idx = pno
        self._edited()
        return Page(self, idx)

    def insert_pdf(self, src, from_page=0, to_page=-1, start_at=-1, **kw):
        pk = self._pk_doc()
        n = src.page_count
        if to_page < 0 or to_page >= n:
            to_page = n - 1
        sp = src._pk_doc()
        step = 1 if to_page >= from_page else -1
        for i in range(from_page, to_page + step, step):
            if sp is pk:
                pk.pages.append(pk.pages[i])
            else:
                pk.pages.append(sp.pages[i])
        # הגדרות העמוד (סיבוב) עוברות עם העמוד; נתוני הסימונים — גם
        try:
            if MARKS_KEY in sp.Root and MARKS_KEY not in pk.Root:
                pk.Root[MARKS_KEY] = pk.copy_foreign(sp.Root[MARKS_KEY])
        except Exception:
            pass
        self._edited()

    def select(self, lst):
        pk = self._pk_doc()
        keep = [pk.pages[i] for i in lst]
        import pikepdf
        new = pikepdf.new()
        for p in keep:
            new.pages.append(p)
        try:
            if MARKS_KEY in pk.Root:
                new.Root[MARKS_KEY] = new.copy_foreign(pk.Root[MARKS_KEY])
        except Exception:
            pass
        self._pk = new
        self._edited()

    def delete_pages(self, *args, **kw):
        n = self.page_count
        if "from_page" in kw:
            a, b = kw["from_page"], kw.get("to_page", n - 1)
            idx = list(range(a, b + 1))
        elif len(args) == 1 and isinstance(args[0], (list, tuple, set, range)):
            idx = list(args[0])
        elif len(args) == 2:
            idx = list(range(args[0], args[1] + 1))
        elif len(args) == 1:
            idx = [args[0]]
        else:
            idx = []
        idx = set(i % n for i in idx)
        self.select([i for i in range(n) if i not in idx])

    def delete_page(self, i=-1):
        self.delete_pages([i])

    def tobytes(self, **kw):
        buf = io.BytesIO()
        self.save(buf, **kw)
        return buf.getvalue()

    write = tobytes

    def save(self, target, garbage=0, deflate=False, incremental=False, encryption=None, **kw):
        if self._image:
            raise FileDataError("זו תמונה — צריך להמיר ל-PDF")
        if self._pk is None and not self._dirty:
            data = self._bytes
            if data is None:
                with builtins.open(self.name, "rb") as f:
                    data = f.read()
            if hasattr(target, "write"):
                target.write(data)
            else:
                with builtins.open(target, "wb") as f:
                    f.write(data)
            return
        import pikepdf
        pk = self._pk_doc()
        # בלי דחיסת אובייקטים: כך אפשר לזהות מהר (בלי לפענח) קובץ שיש בו סימונים
        pk.save(target, compress_streams=True, object_stream_mode=pikepdf.ObjectStreamMode.disable)

    # --- תמונות (המרה ל-PDF)
    def _image_frames(self):
        from PySide6.QtGui import QImageReader
        rd = QImageReader(self._image)
        n = rd.imageCount()
        return max(1, n)

    def convert_to_pdf(self, from_page=0, to_page=-1, rotate=0):
        if not self._image:
            return self.tobytes()
        import pikepdf
        from PySide6.QtGui import QImageReader
        pk = pikepdf.new()
        rd = QImageReader(self._image)
        raw = builtins.open(self._image, "rb").read()
        k = 0
        while True:
            img = rd.read()
            if img.isNull():
                break
            dx, dy = img.dotsPerMeterX(), img.dotsPerMeterY()
            xres = dx * 0.0254 if dx > 0 else 72.0
            yres = dy * 0.0254 if dy > 0 else 72.0
            w, h = img.width() * 72.0 / xres, img.height() * 72.0 / yres
            xo = _image_xobject(pk, img, raw if k == 0 and rd.imageCount() <= 1 else None)
            pg = pikepdf.Page(pikepdf.Dictionary(Type=pikepdf.Name.Page, MediaBox=[0, 0, w, h],
                                                 Resources=pikepdf.Dictionary(
                                                     XObject=pikepdf.Dictionary(Im0=xo)),
                                                 Contents=pikepdf.Stream(
                                                     pk, f"q {_num(w)} 0 0 {_num(h)} 0 0 cm /Im0 Do Q".encode())))
            pk.pages.append(pg)
            k += 1
            if not rd.jumpToNextImage():
                break
        buf = io.BytesIO()
        pk.save(buf)
        return buf.getvalue()


def _strip_marks_copy(pk):
    """עותק של הקובץ בלי הסימונים הצרובים (לתצוגה: הסימונים מוצגים לעריכה מעל השרטוט)."""
    import pikepdf
    buf = io.BytesIO()
    pk.save(buf)
    cl = pikepdf.open(io.BytesIO(buf.getvalue()))
    for pg in cl.pages:
        strip_tagged(pg)
    return cl


def strip_tagged(pg):
    """מסיר מהעמוד את זרמי התוכן שמתחילים בתג הסימונים. מחזיר True אם משהו הוסר."""
    import pikepdf
    c = pg.obj.get("/Contents")
    if c is None:
        return False
    arr = list(c) if isinstance(c, pikepdf.Array) else [c]
    keep = []
    removed = False
    for s in arr:
        try:
            head = s.read_bytes()[:len(MARK_TAG)]
        except Exception:
            head = b""
        if head == MARK_TAG:
            removed = True
        else:
            keep.append(s)
    if removed:
        pg.obj["/Contents"] = pikepdf.Array(keep)
    return removed


def open(*args, **kw):        # noqa: A001 — כמו במנוע המקורי
    if not args and not kw:
        return Document()
    if len(args) >= 2:
        return Document(None, stream=args[1])
    if "stream" in kw:
        return Document(None, stream=kw["stream"])
    if "filename" in kw:
        return Document(kw["filename"])
    return Document(args[0])


Document.open = staticmethod(open)
