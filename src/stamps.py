# חותמות: 2 חותמות קבועות של טיקטין + עד 2 חותמות נוספות (מתמונה או מ-PDF, עם שם קבוע),
# צביעה בשחור או אדום, תאריך אוטומטי בחותמת הלוחות, וחיפוש מקום פנוי בכל עמוד.
import base64
from PySide6.QtCore import Qt, QSettings, QBuffer, QByteArray, QIODevice
from PySide6.QtGui import QImage, QPainter, QColor
from default_stamps import STAMPS as BUILTIN

FIXED = (1, 2)          # החותמות הקבועות
CUSTOM = (3, 4)         # מקומות לחותמות נוספות

MAX_SIDE = 900
_masks = {}       # slot -> QImage (Alpha8)
_colored = {}     # (slot, color) -> QImage
_png = {}         # (slot, color) -> bytes
_extra = {}       # חותמות שנטענו מתוך קובץ PDF (מפתח -> PNG)


def _st():
    return QSettings("Tiktin", "TiktinPDF")


def make_mask(img, want_offset=False):
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
    cm = m.copy(xs0, ys0, xs1 - xs0 + 1, ys1 - ys0 + 1)
    return (cm, xs0, ys0, w / img.width()) if want_offset else cm


def _to_png(img):
    ba = QByteArray()
    buf = QBuffer(ba)
    buf.open(QIODevice.WriteOnly)
    img.save(buf, "PNG")
    buf.close()
    return bytes(ba)


def _read_image(path):
    """תמונה רגילה, או העמוד הראשון של קובץ PDF (ברזולוציה גבוהה)."""
    if path.lower().endswith(".pdf"):
        import pymupdf
        doc = pymupdf.open(path)
        pg = doc[0]
        z = min(300 / 72.0, 2400.0 / max(pg.rect.width, pg.rect.height))
        pix = pg.get_pixmap(matrix=pymupdf.Matrix(z, z), alpha=False)
        img = QImage(pix.samples, pix.width, pix.height, pix.stride, QImage.Format_RGB888).copy()
        doc.close()
        return img
    return QImage(path)


def load_file(slot, path, name=None):
    img = _read_image(path)
    if img.isNull():
        return False
    m = make_mask(img)
    if m is None:
        return False
    st = _st()
    st.setValue(f"stamp{slot}", base64.b64encode(_to_png(m)).decode())
    if name:
        st.setValue(f"stamp{slot}_name", name)
    _forget(slot)
    return True


def remove(slot):
    st = _st()
    st.remove(f"stamp{slot}")
    st.remove(f"stamp{slot}_name")
    _forget(slot)


def _forget(slot):
    _masks.pop(slot, None)
    for k in [k for k in _colored if k[0] == slot]:
        _colored.pop(k, None)
        _png.pop(k, None)


def name(slot):
    if slot in BUILTIN:
        return BUILTIN[slot]["name"]
    return _st().value(f"stamp{slot}_name", "") or f"חותמת {slot}"


def date_pos(slot):
    """מיקום שדה התאריך בחותמת (יחסי), או None."""
    d = BUILTIN.get(slot, {}).get("date") if slot in FIXED else None
    return tuple(d) if d else None


def free_custom_slot():
    for s_ in CUSTOM:
        if not has(s_):
            return s_
    return None


def register(key, png):
    _extra[key] = png
    _masks.pop(key, None)


def mask_png(slot):
    """ה-PNG של מסכת החותמת (לשמירה בתוך הקובץ)."""
    if slot in _extra:
        return _extra[slot]
    if slot in FIXED:
        return base64.b64decode(BUILTIN[slot]["png"])
    raw = _st().value(f"stamp{slot}", "")
    return base64.b64decode(raw) if raw else b""


def mask(slot):
    if slot not in _masks:
        if slot in _extra:
            raw = base64.b64encode(_extra[slot]).decode()
        elif slot in FIXED:
            raw = BUILTIN[slot]["png"]
        else:
            raw = _st().value(f"stamp{slot}", "")
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


# ---------------------------------------------------------------- free spot / size
INK_SIDE = 300            # רזולוציית מפת הדיו: הצלע הארוכה של העמוד בפיקסלים (קטן = מהיר)
TEXT_FRAC = {1: 0.11, 2: 0.07}    # גובה שורת כתב בחותמת ביחס לגובה החותמת


def page_ink(page):
    """מפת "דיו" של העמוד — טקסט, קווים וסריקה — מפענוח אחד של העמוד, וגם גובה הכתב האופייני בו.
    מחזיר dict: cell (נק' לתא), nx, ny, sat (טבלת סכומים מצטברים), text_h (נק', או None)."""
    import pymupdf
    pr = page.rect
    z = INK_SIDE / max(pr.width, pr.height, 1.0)
    dl = page.get_displaylist()
    pix = dl.get_pixmap(matrix=pymupdf.Matrix(z, z), colorspace=pymupdf.csGRAY, alpha=False)
    nx, ny, stride = pix.width, pix.height, pix.stride
    tbl = bytes(1 if v < 225 else 0 for v in range(256))
    ink = pix.samples.translate(tbl)
    n1 = nx + 1
    sat = [0] * (n1 * (ny + 1))
    for yy in range(ny):
        row = ink[yy * stride: yy * stride + nx]
        a = (yy + 1) * n1
        b = yy * n1
        run = 0
        if not any(row):
            sat[a + 1: a + n1] = sat[b + 1: b + n1]
            continue
        for xx in range(nx):
            run += row[xx]
            sat[a + xx + 1] = sat[b + xx + 1] + run
    text_h = None
    try:
        hs = sorted(min(w[2] - w[0], w[3] - w[1]) for w in pymupdf.TextPage(dl.get_textpage()).extractWORDS()
                    if len(w[4]) >= 2)
        if len(hs) >= 5:
            text_h = hs[len(hs) // 2] * 0.6          # גובה האותיות עצמן, בלי הרווח שמעל ומתחת
    except Exception:
        pass
    return {"cell": 1.0 / z, "nx": nx, "ny": ny, "sat": sat, "text_h": text_h, "PW": pr.width, "PH": pr.height}


def auto_width_mm(slot, ink, factor=1.0):
    """רוחב החותמת (מ"מ) כך שהכתב שבה יהיה בגודל הכתב שבשרטוט; בעמוד בלי טקסט — יחסית לגודל הדף."""
    side = min(ink["PW"], ink["PH"])
    th = ink["text_h"] or side * 0.0065
    h = th / TEXT_FRAC.get(slot, 0.12) * factor
    h = min(max(h, side * 0.03), side * 0.30)
    return (h / max(aspect(slot), 0.05)) / (72.0 / 25.4)


def find_free_spot(ink, W, H, cx, cy, blocked=(), margin=3.0):
    """המקום הקרוב ביותר ל-(cx, cy) שבו חותמת ברוחב W וגובה H (נקודות) לא מסתירה טקסט, קווים או סימונים.
    blocked = מלבנים תפוסים נוספים (x0, y0, x1, y1). מחזיר (cx, cy, נמצא מקום נקי לגמרי)."""
    cell, nx, ny, sat = ink["cell"], ink["nx"], ink["ny"], ink["sat"]
    n1 = nx + 1
    gw = min(nx, max(1, int(W / cell + 0.999) + 2))       # כולל שוליים של תא מכל צד
    gh = min(ny, max(1, int(H / cell + 0.999) + 2))
    mg = int(margin / cell + 0.5)
    lo_x, hi_x = mg, nx - gw - mg
    lo_y, hi_y = mg, ny - gh - mg
    if hi_x < lo_x:
        lo_x = hi_x = max(0, (nx - gw) // 2)
    if hi_y < lo_y:
        lo_y = hi_y = max(0, (ny - gh) // 2)
    tx = min(max(int((cx - W / 2) / cell) - 1, lo_x), hi_x)
    ty = min(max(int((cy - H / 2) / cell) - 1, lo_y), hi_y)
    bl = [(int(x0 / cell) - gw, int(y0 / cell) - gh, int(x1 / cell) + 1, int(y1 / cell) + 1) for x0, y0, x1, y1 in blocked]

    def cost(gx, gy):
        c = sat[(gy + gh) * n1 + gx + gw] - sat[gy * n1 + gx + gw] - sat[(gy + gh) * n1 + gx] + sat[gy * n1 + gx]
        for bx0, by0, bx1, by1 in bl:
            if bx0 < gx < bx1 and by0 < gy < by1:
                c += gw * gh
        return c

    def result(gx, gy, clean):
        if gx == tx and gy == ty:
            return cx, cy, clean
        return (gx + gw / 2.0) * cell, (gy + gh / 2.0) * cell, clean

    c0 = cost(tx, ty)
    if c0 == 0:
        return result(tx, ty, True)
    best = (c0, 0, tx, ty)
    maxr = max(hi_x - lo_x, hi_y - lo_y) + 1
    for ring in range(1, maxr + 1):
        found = None
        for i in range(-ring, ring + 1):
            for gx, gy in ((tx + i, ty - ring), (tx + i, ty + ring), (tx - ring, ty + i), (tx + ring, ty + i)):
                if gx < lo_x or gx > hi_x or gy < lo_y or gy > hi_y:
                    continue
                c = cost(gx, gy)
                d = (gx - tx) ** 2 + (gy - ty) ** 2
                if c == 0:
                    if found is None or d < found[0]:
                        found = (d, gx, gy)
                elif (c, d) < best[:2]:
                    best = (c, d, gx, gy)
        if found:
            return result(found[1], found[2], True)
    return result(best[2], best[3], False)      # אין מקום נקי לגמרי — המקום שמסתיר הכי פחות
