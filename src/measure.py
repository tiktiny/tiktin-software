# כלי מדידה נוספים (גרסת המשרד): מדידה רציפה, שטח והיקף, קו מידה קבוע ושרשרת מידות.
# כל הקואורדינטות בנקודות PDF של העמוד כפי שהוא מוצג. המידות מחושבות לפי קנ"מ העמוד.
#   pdim – מדידה רציפה:  {"type": "pdim", "pts": [(x, y), ...], "color"}
#   area – שטח והיקף:     {"type": "area", "pts": [(x, y), ...], "color"}
#   ldim – קו מידה קבוע:  {"type": "ldim", "p1", "p2", "u": (ux, uy), "d": (x, y), "color"}
#          u = כיוון המידה, d = נקודה על קו המידה. שרשרת מידות = כמה ldim על אותו קו.
import math
from PySide6.QtCore import Qt, QPointF, QRectF
from PySide6.QtGui import QColor, QPolygonF, QPainterPath

import annotations as A

TYPES = ("pdim", "area", "ldim")
AREA_COLOR = "#0057b8"
EXT_GAP = 1.2         # רווח בין הנקודה הנמדדת לתחילת קו העזר (נקודות נייר)
EXT_OVER = 1.8        # כמה קו העזר עובר את קו המידה
TICK = 2.2            # חצי אורך סימון הקצה


# ---------------------------------------------------------------- מספרים
def cm(pt_len, S):
    return A.pt_to_cm(pt_len, S)


def fmt_cm(v):
    return f"{v:.0f} ס\"מ" if v >= 10 else f"{v:.1f} ס\"מ"


def fmt_m(v_cm):
    return f"{v_cm / 100.0:.2f} מ'"


def poly_len(pts, closed=False):
    n = len(pts)
    L = sum(math.hypot(pts[k + 1][0] - pts[k][0], pts[k + 1][1] - pts[k][1]) for k in range(n - 1))
    if closed and n > 2:
        L += math.hypot(pts[0][0] - pts[-1][0], pts[0][1] - pts[-1][1])
    return L


def poly_area(pts):
    n = len(pts)
    if n < 3:
        return 0.0
    s = 0.0
    for k in range(n):
        x1, y1 = pts[k]
        x2, y2 = pts[(k + 1) % n]
        s += x1 * y2 - x2 * y1
    return abs(s) / 2.0


def centroid(pts):
    n = len(pts)
    a = 0.0
    cx = cy = 0.0
    for k in range(n):
        x1, y1 = pts[k]
        x2, y2 = pts[(k + 1) % n]
        c = x1 * y2 - x2 * y1
        a += c
        cx += (x1 + x2) * c
        cy += (y1 + y2) * c
    if abs(a) < 1e-9:
        return sum(p[0] for p in pts) / n, sum(p[1] for p in pts) / n
    return cx / (3 * a), cy / (3 * a)


# ---------------------------------------------------------------- קו מידה
def ldim_geom(it):
    """נקודות קו המידה (q1, q2) והאורך הנמדד בנקודות."""
    (x1, y1), (x2, y2) = it["p1"], it["p2"]
    ux, uy = it["u"]
    dx, dy = it["d"]
    t1 = (x1 - dx) * ux + (y1 - dy) * uy
    t2 = (x2 - dx) * ux + (y2 - dy) * uy
    q1 = (dx + ux * t1, dy + uy * t1)
    q2 = (dx + ux * t2, dy + uy * t2)
    return q1, q2, abs(t2 - t1)


def ldim_ext(p, q):
    """קו עזר מהנקודה הנמדדת אל קו המידה (עם רווח קטן בהתחלה ומעבר קטן אחרי)."""
    vx, vy = q[0] - p[0], q[1] - p[1]
    L = math.hypot(vx, vy)
    if L < EXT_GAP + 0.3:
        return None
    vx, vy = vx / L, vy / L
    return (p[0] + vx * EXT_GAP, p[1] + vy * EXT_GAP), (q[0] + vx * EXT_OVER, q[1] + vy * EXT_OVER)


def make_ldim(p1, p2, cursor, u=None, color=None):
    """קו מידה מ-p1 ל-p2, כשקו המידה עובר דרך מיקום העכבר. u = כיוון קבוע (שרשרת / אופקי / אנכי)."""
    if u is None:
        vx, vy = p2[0] - p1[0], p2[1] - p1[1]
        L = math.hypot(vx, vy) or 1.0
        u = (vx / L, vy / L)
    nx, ny = -u[1], u[0]
    off = (cursor[0] - p1[0]) * nx + (cursor[1] - p1[1]) * ny
    d = (p1[0] + nx * off, p1[1] + ny * off)
    it = {"type": "ldim", "p1": tuple(p1), "p2": tuple(p2), "u": tuple(u), "d": d}
    if color:
        it["color"] = color
    return it


# ---------------------------------------------------------------- תוויות
def label_of(it, S):
    t = it["type"]
    if t == "ldim":
        return fmt_cm(cm(ldim_geom(it)[2], S))
    if t == "pdim":
        return "סה\"כ " + fmt_m(cm(poly_len(it["pts"]), S))
    a_m2 = cm(1.0, S) ** 2 * poly_area(it["pts"]) / 10000.0
    return f"שטח {a_m2:.2f} מ\"ר · היקף {fmt_m(cm(poly_len(it['pts'], True), S))}"


def label_center(it):
    t = it["type"]
    if t == "ldim":
        q1, q2, _ = ldim_geom(it)
        return (q1[0] + q2[0]) / 2, (q1[1] + q2[1]) / 2
    if t == "pdim":
        (x, y) = it["pts"][-1]
        return x, y - A.LABEL_PT * 1.1
    return centroid(it["pts"])


def label_rect(it, S):
    path = A._text_path(label_of(it, S))
    k = A.LABEL_PT / 100.0
    w, h = path.boundingRect().width() * k, A.LABEL_PT * 0.95
    cx, cy = label_center(it)
    return QRectF(cx - w / 2 - 1, cy - h / 2 - 0.8, w + 2, h + 1.6)


def _paint_label(p, it, S, color):
    text = label_of(it, S)
    path = A._text_path(text)
    br = path.boundingRect()
    k = A.LABEL_PT / 100.0
    lr = label_rect(it, S)
    p.fillRect(lr, QColor(255, 255, 255, 235))
    p.save()
    p.translate(lr.center().x() - br.center().x() * k, lr.bottom() - br.bottom() * k - 0.8)
    p.scale(k, k)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(color))
    p.drawPath(path)
    p.restore()


# ---------------------------------------------------------------- קווים לציור (משותף לתצוגה ולשמירה)
def _ticks(a, b):
    """סימוני 45° בשני קצוות קו."""
    L = math.hypot(b[0] - a[0], b[1] - a[1])
    if L <= 0:
        return []
    ux, uy = (b[0] - a[0]) / L, (b[1] - a[1]) / L
    dx, dy = (ux - uy) * TICK / math.sqrt(2), (uy + ux) * TICK / math.sqrt(2)
    return [((x - dx, y - dy), (x + dx, y + dy)) for x, y in (a, b)]


def lines_of(it):
    """כל קטעי הקו של הסימון: [(נקודה, נקודה), ...]."""
    t = it["type"]
    if t == "ldim":
        q1, q2, L = ldim_geom(it)
        out = [(q1, q2)]
        for p, q in ((it["p1"], q1), (it["p2"], q2)):
            e = ldim_ext(tuple(p), q)
            if e:
                out.append(e)
        out += _ticks(q1, q2)
        return out
    pts = [tuple(q) for q in it["pts"]]
    out = [(pts[k], pts[k + 1]) for k in range(len(pts) - 1)]
    if t == "area" and len(pts) > 2:
        out.append((pts[-1], pts[0]))
    if t == "pdim":
        for k in range(len(pts) - 1):           # סימון קטן בכל נקודת שבירה
            out += _ticks(pts[k], pts[k + 1])
    return out


# ---------------------------------------------------------------- ממשק לסימונים
def bbox(it, S):
    xs, ys = [], []
    for a, b in lines_of(it):
        xs += [a[0], b[0]]
        ys += [a[1], b[1]]
    if not xs:
        xs, ys = [p[0] for p in it.get("pts", [(0, 0)])], [p[1] for p in it.get("pts", [(0, 0)])]
    r = QRectF(QPointF(min(xs), min(ys)), QPointF(max(xs), max(ys)))
    return r.united(label_rect(it, S))


def hit(it, pt, S, tol):
    if label_rect(it, S).adjusted(-tol, -tol, tol, tol).contains(pt):
        return True
    for a, b in lines_of(it):
        if A._seg_dist(pt.x(), pt.y(), a[0], a[1], b[0], b[1]) <= tol:
            return True
    if it["type"] == "area" and len(it["pts"]) > 2:
        return QPolygonF([QPointF(*q) for q in it["pts"]]).containsPoint(pt, Qt.OddEvenFill)
    return False


def move(it, dx, dy):
    if "pts" in it:
        it["pts"] = [(x + dx, y + dy) for x, y in it["pts"]]
    for k in ("p1", "p2", "d"):
        if k in it:
            it[k] = (it[k][0] + dx, it[k][1] + dy)


def transform(it, T):
    """מעביר את הסימון דרך פונקציית נקודות T (סיבוב עמוד)."""
    if "pts" in it:
        it["pts"] = [T(x, y) for x, y in it["pts"]]
    if it["type"] == "ldim":
        o = T(0.0, 0.0)
        e = T(it["u"][0], it["u"][1])
        it["u"] = (e[0] - o[0], e[1] - o[1])
        for k in ("p1", "p2", "d"):
            it[k] = T(*it[k])


def paint(p, it, S, cosmetic=True, selected=False, ghost=False):
    color = QColor(it.get("color") or A.DIM_COLOR)
    if ghost:
        color.setAlpha(170)
    p.save()
    if it["type"] == "area" and len(it["pts"]) > 2:
        fill = QColor(color)
        fill.setAlpha(38)
        p.setPen(Qt.NoPen)
        p.setBrush(fill)
        p.drawPolygon(QPolygonF([QPointF(*q) for q in it["pts"]]))
    p.setBrush(Qt.NoBrush)
    p.setPen(A._pen(color, cosmetic))
    for a, b in lines_of(it):
        p.drawLine(QPointF(*a), QPointF(*b))
    if it["type"] != "pdim" or len(it["pts"]) > 1:
        _paint_label(p, it, S, color)
    if selected:
        p.setPen(A._pen(A.SEL_COLOR, cosmetic, True, 1.2))
        p.setBrush(Qt.NoBrush)
        p.drawRect(bbox(it, S).adjusted(-1.5, -1.5, 1.5, 1.5))
    p.restore()


def bake(page, it, S, m):
    """צריבה וקטורית בקובץ (מופיע בכל תוכנה)."""
    import pymupdf

    def P(x, y):
        return pymupdf.Point(x, y) * m

    col = A._rgb(it.get("color") or A.DIM_COLOR)
    if it["type"] == "area" and len(it["pts"]) > 2:
        sh = page.new_shape()
        pts = [P(x, y) for x, y in it["pts"]]
        sh.draw_polyline(pts + [pts[0]])
        sh.finish(oc=A.OC(), color=None, fill=col, fill_opacity=0.15, closePath=True)
        sh.commit()
    sh = page.new_shape()
    for a, b in lines_of(it):
        sh.draw_line(P(*a), P(*b))
    sh.finish(oc=A.OC(), color=col, width=A.PRINT_LINE_PT, closePath=False)
    sh.commit()
    lr = label_rect(it, S)
    bg = pymupdf.Rect(lr.left(), lr.top(), lr.right(), lr.bottom()) * m
    page.draw_rect(bg, color=None, fill=(1, 1, 1), fill_opacity=0.92, overlay=True, oc=A.OC())
    rect = pymupdf.Rect(lr.left() - 30, lr.top() - 1, lr.right() + 30, lr.bottom() + 3)
    color = it.get("color") or A.DIM_COLOR
    html = (f'<div dir="rtl" style="font-family:sans-serif;font-size:{A.LABEL_PT * 0.98:.2f}pt;'
            f'line-height:1;color:{color};text-align:center">{label_of(it, S)}</div>')
    page.insert_htmlbox((rect * m).normalize() if page.rotation else rect, html,
                        rotate=page.rotation, overlay=True, oc=A.OC())


# ---------------------------------------------------------------- הצמדה לקווי השרטוט
SNAP_NAMES = {"end": "קצה קו", "mid": "אמצע קו", "int": "מפגש קווים", "perp": "ניצב לקו", "near": "על הקו"}
_PRIO = {"end": 0, "int": 1, "mid": 2, "perp": 3, "near": 4}


from snap_worker import build_snap_segments  # noqa: E402,F401  (נקרא בתהליך הרקע)


def _foot(px, py, x1, y1, x2, y2, clamp=True):
    dx, dy = x2 - x1, y2 - y1
    L2 = dx * dx + dy * dy
    if L2 == 0:
        return x1, y1, 0.0
    t = ((px - x1) * dx + (py - y1) * dy) / L2
    if clamp:
        t = max(0.0, min(1.0, t))
    return x1 + t * dx, y1 + t * dy, t


def _inter(s1, s2):
    x1, y1, x2, y2 = s1
    x3, y3, x4, y4 = s2
    d = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4)
    if abs(d) < 1e-9:
        return None
    t = ((x1 - x3) * (y3 - y4) - (y1 - y3) * (x3 - x4)) / d
    u = -((x1 - x2) * (y1 - y3) - (y1 - y2) * (x1 - x3)) / d
    if -1e-6 <= t <= 1 + 1e-6 and -1e-6 <= u <= 1 + 1e-6:
        return x1 + t * (x2 - x1), y1 + t * (y2 - y1)
    return None


def find_snap(cache, x, y, tol, base=None):
    """הנקודה הכי מתאימה להצמדה ליד (x, y), במערכת העמוד הלא מסובבת.
    base = נקודת ההתחלה של המדידה (לניצב). מחזיר (x, y, סוג) או None."""
    cell = cache["cell"]
    sids = set()
    for gx in range(int((x - tol) // cell), int((x + tol) // cell) + 1):
        for gy in range(int((y - tol) // cell), int((y + tol) // cell) + 1):
            sids |= cache["grid"].get((gx, gy), set())
    near = []
    for sid in sids:
        s = cache["segs"][sid]
        fx, fy, _ = _foot(x, y, *s)
        d = math.hypot(fx - x, fy - y)
        if d <= tol:
            near.append((d, s, fx, fy))
    if not near:
        return None
    near.sort(key=lambda r: r[0])
    near = near[:60]
    best = None

    def offer(px, py, kind):
        nonlocal best
        d = math.hypot(px - x, py - y)
        if d > tol:
            return
        key = (_PRIO[kind], d)
        if best is None or key < best[0]:
            best = (key, px, py, kind)

    for d, s, fx, fy in near:
        x1, y1, x2, y2 = s
        offer(x1, y1, "end")
        offer(x2, y2, "end")
        offer((x1 + x2) / 2, (y1 + y2) / 2, "mid")
        if base is not None:
            px, py, t = _foot(base[0], base[1], x1, y1, x2, y2, clamp=False)
            if 0.0 <= t <= 1.0 and math.hypot(px - base[0], py - base[1]) > 1.0:
                offer(px, py, "perp")
        offer(fx, fy, "near")
    if best[0][0] > 1:                    # אין קצה – בודקים מפגשי קווים
        for a in range(min(len(near), 25)):
            for b in range(a + 1, min(len(near), 25)):
                p = _inter(near[a][1], near[b][1])
                if p:
                    offer(p[0], p[1], "int")
    return best[1], best[2], best[3]


def paint_snap_marker(p, c, kind, color="#e8590c"):
    """סימן ההצמדה ליד העכבר (במערכת המסך)."""
    from PySide6.QtGui import QPen
    pen = QPen(QColor(color))
    pen.setWidthF(2.0)
    pen.setCosmetic(True)
    p.save()
    p.setPen(pen)
    p.setBrush(Qt.NoBrush)
    s = 6.0
    x, y = c.x(), c.y()
    if kind == "end":
        p.drawRect(QRectF(x - s, y - s, 2 * s, 2 * s))
    elif kind == "mid":
        p.drawPolygon(QPolygonF([QPointF(x, y - s), QPointF(x + s, y + s * 0.8), QPointF(x - s, y + s * 0.8)]))
    elif kind == "int":
        p.drawLine(QPointF(x - s, y - s), QPointF(x + s, y + s))
        p.drawLine(QPointF(x - s, y + s), QPointF(x + s, y - s))
    elif kind == "perp":
        p.drawLine(QPointF(x - s, y + s), QPointF(x + s, y + s))
        p.drawLine(QPointF(x - s, y + s), QPointF(x - s, y - s))
        p.drawLine(QPointF(x - s, y), QPointF(x, y))
        p.drawLine(QPointF(x, y), QPointF(x, y + s))
    else:
        path = QPainterPath()
        path.moveTo(x - s, y - s)
        path.lineTo(x + s, y - s)
        path.lineTo(x - s, y + s)
        path.lineTo(x + s, y + s)
        path.closeSubpath()
        p.drawPath(path)
    f = p.font()
    f.setPointSizeF(8.5)
    p.setFont(f)
    txt = SNAP_NAMES.get(kind, "")
    fm = p.fontMetrics()
    r = QRectF(x + 10, y + 8, fm.horizontalAdvance(txt) + 8, fm.height() + 2)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(255, 255, 255, 230))
    p.drawRect(r)
    p.setPen(QColor(color))
    p.drawText(r, Qt.AlignCenter, txt)
    p.restore()
