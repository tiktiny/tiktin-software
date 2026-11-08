# סימונים על השרטוט: חור ברצפה / בתקרה / בקיר, ומדידה בס"מ.
# כל הקואורדינטות בנקודות PDF של העמוד (כפי שהוא מוצג), המידות בס"מ אמיתיים לפי קנ"מ.
import math
from PySide6.QtCore import Qt, QPointF, QRectF
from PySide6.QtGui import QPen, QColor, QFont, QPainterPath, QPolygonF, QBrush

PT_PER_MM = 72.0 / 25.4
HOLE_COLOR = "#d0021b"
DIM_COLOR = "#0057b8"
SEL_COLOR = "#ff8a00"
LABEL_PT = 7.0            # גובה טקסט על הנייר (כ-2.5 מ"מ)
PRINT_LINE_PT = 0.8       # עובי קו בהדפסה ובשמירה
KIND_NAME = {"floor": "חור ברצפה", "ceil": "חור בתקרה", "wall": "חור בקיר"}


BAKE_OC = 0          # שכבת "סימוני טיקטין" שאליה נצרבים הסימונים (0 = בלי שכבה)
MARK_TAG = b"%TIKTIN-MARKS"


def OC():
    return BAKE_OC


def cm_to_pt(cm, S):
    return cm * 10.0 / S * PT_PER_MM


def pt_to_cm(pt, S):
    return pt / PT_PER_MM * S / 10.0


def fmt(v):
    v = round(float(v), 1)
    return f"{v:g}"


# ---------------------------------------------------------------- geometry
def hole_half(it, S):
    """חצי רוחב וחצי עומק של טביעת החור בתוכנית, בנקודות."""
    if it["shape"] == "round":
        a = it["d"] / 2.0
        b = it["thick"] / 2.0 if it["kind"] == "wall" else a
    else:
        a = it["w"] / 2.0
        b = (it["thick"] if it["kind"] == "wall" else it["l"]) / 2.0
    return cm_to_pt(a, S), cm_to_pt(b, S)


def hole_corners(it, S):
    a, b = hole_half(it, S)
    t = math.radians(it.get("angle", 0.0))
    c, s = math.cos(t), math.sin(t)
    cx, cy = it["c"]
    return [QPointF(cx + x * c - y * s, cy + x * s + y * c)
            for x, y in ((-a, -b), (a, -b), (a, b), (-a, b))]


def is_circle(it):
    return it["shape"] == "round" and it["kind"] != "wall"


def hole_label(it):
    if it["shape"] == "round":
        dims = f"Ø{fmt(it['d'])}"
    elif it["kind"] == "wall":
        dims = f"{fmt(it['w'])}×{fmt(it['h'])}"
    else:
        dims = f"{fmt(it['w'])}×{fmt(it['l'])}"
    s = f"{KIND_NAME[it['kind']]} \u202a{dims}\u202c ס\"מ"
    if it["kind"] == "wall" and it["shape"] != "round":
        s += " (ר×ג)"
    if it["kind"] == "wall" and it.get("bottom") not in (None, ""):
        s += f", תחתית \u202a+{fmt(it['bottom'])}\u202c"
    return s


def dim_label(it, S):
    (x1, y1), (x2, y2) = it["p1"], it["p2"]
    cm = pt_to_cm(math.hypot(x2 - x1, y2 - y1), S)
    return f"{cm:.0f} ס\"מ" if cm >= 10 else f"{cm:.1f} ס\"מ"


def _shape_bbox(it, S):
    if it["type"] == "dim":
        (x1, y1), (x2, y2) = it["p1"], it["p2"]
        return QRectF(QPointF(min(x1, x2), min(y1, y2)), QPointF(max(x1, x2), max(y1, y2)))
    if is_circle(it):
        r = hole_half(it, S)[0]
        cx, cy = it["c"]
        return QRectF(cx - r, cy - r, 2 * r, 2 * r)
    return QPolygonF(hole_corners(it, S)).boundingRect()


def label_anchor(it, S):
    """מרכז תחתית התווית (חורים) או מרכז התווית (מדידה)."""
    if it["type"] == "dim":
        (x1, y1), (x2, y2) = it["p1"], it["p2"]
        return QPointF((x1 + x2) / 2, (y1 + y2) / 2)
    bb = _shape_bbox(it, S)
    return QPointF(bb.center().x(), bb.top() - LABEL_PT * 0.5)


def label_text(it, S):
    return dim_label(it, S) if it["type"] == "dim" else hole_label(it)


# ---------------------------------------------------------------- text as path
_FONT = None


def _text_path(text):
    global _FONT
    if _FONT is None:
        _FONT = QFont("Arial")
        _FONT.setPixelSize(100)
    path = QPainterPath()
    path.addText(0, 0, _FONT, text)
    return path


def label_rect(it, S):
    """מלבן התווית בנקודות העמוד."""
    path = _text_path(label_text(it, S))
    br = path.boundingRect()
    k = LABEL_PT / 100.0
    w, h = br.width() * k, LABEL_PT * 0.95
    a = label_anchor(it, S)
    if it["type"] == "dim":
        return QRectF(a.x() - w / 2 - 1, a.y() - h / 2 - 0.8, w + 2, h + 1.6)
    return QRectF(a.x() - w / 2, a.y() - h, w, h)


def item_bbox(it, S):
    if it.get("angle") and it["type"] != "hole":
        from annotations_extra import rot_bbox
        return rot_bbox(it)
    if it["type"] in EXTRA:
        return EXTRA[it["type"]]["bbox"](it)
    if it["type"] == "trafo":
        return trafo_rect(it)
    if it["type"] == "ink":
        return ink_bbox(it)
    if it["type"] == "text":
        return text_rect(it)
    return _shape_bbox(it, S).united(label_rect(it, S))


def hit(it, pt, S, tol):
    if it.get("angle") and it["type"] != "hole":
        from annotations_extra import to_local
        pt = to_local(it, pt)
    if it["type"] in EXTRA:
        return EXTRA[it["type"]]["hit"](it, pt, tol)
    if it["type"] == "trafo":
        return trafo_rect(it).adjusted(-tol, -tol, tol, tol).contains(pt)
    if it["type"] == "ink":
        return ink_hit(it, pt, tol)
    if it["type"] == "text":
        return text_rect(it).adjusted(-tol, -tol, tol, tol).contains(pt)
    if label_rect(it, S).adjusted(-tol, -tol, tol, tol).contains(pt):
        return True
    if it["type"] == "dim":
        (x1, y1), (x2, y2) = it["p1"], it["p2"]
        dx, dy = x2 - x1, y2 - y1
        L2 = dx * dx + dy * dy or 1e-9
        t = max(0, min(1, ((pt.x() - x1) * dx + (pt.y() - y1) * dy) / L2))
        return math.hypot(pt.x() - (x1 + t * dx), pt.y() - (y1 + t * dy)) <= tol
    return _shape_bbox(it, S).adjusted(-tol, -tol, tol, tol).contains(pt)


def move(it, dx, dy):
    if it["type"] == "shape":
        it["p1"] = (it["p1"][0] + dx, it["p1"][1] + dy)
        it["p2"] = (it["p2"][0] + dx, it["p2"][1] + dy)
        return
    if it["type"] in ("mark", "stamp"):
        it["c"] = (it["c"][0] + dx, it["c"][1] + dy)
        return
    if it["type"] == "trafo":
        it["c"] = (it["c"][0] + dx, it["c"][1] + dy)
        return
    if it["type"] == "ink":
        it["pts"] = [(x + dx, y + dy) for x, y in it["pts"]]
        return
    if it["type"] == "text":
        it["p"] = (it["p"][0] + dx, it["p"][1] + dy)
        return
    if it["type"] == "dim":
        it["p1"] = (it["p1"][0] + dx, it["p1"][1] + dy)
        it["p2"] = (it["p2"][0] + dx, it["p2"][1] + dy)
    else:
        it["c"] = (it["c"][0] + dx, it["c"][1] + dy)


# ---------------------------------------------------------------- QPainter drawing
def _pen(color, cosmetic, dashed=False, width=None):
    pen = QPen(QColor(color))
    if cosmetic:
        pen.setCosmetic(True)
        pen.setWidthF(width or 1.6)
    else:
        pen.setWidthF(width or PRINT_LINE_PT)
    pen.setCapStyle(Qt.FlatCap)
    pen.setJoinStyle(Qt.MiterJoin)
    if dashed:
        pen.setDashPattern([5, 3] if cosmetic else [4, 2.5])
    return pen


def _draw_label(p, it, S, color, white_bg):
    text = label_text(it, S)
    path = _text_path(text)
    br = path.boundingRect()
    k = LABEL_PT / 100.0
    lr = label_rect(it, S)
    if white_bg:
        p.fillRect(lr, QColor(255, 255, 255, 235))
    p.save()
    # מיקום: מרכז אופקי, בסיס הטקסט בתחתית המלבן
    x = lr.center().x() - br.center().x() * k
    y = lr.bottom() - (br.bottom() * k) - (0.8 if it["type"] == "dim" else 0.3)
    p.translate(x, y)
    p.scale(k, k)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(color))
    p.drawPath(path)
    p.restore()


def paint_item(p, it, S, cosmetic=True, selected=False, ghost=False):
    if it.get("angle") and it["type"] not in ("hole", "dim", "ink", "text"):
        from annotations_extra import xform
        p.save()
        p.setTransform(xform(it), True)
        r = dict(it)
        r["angle"] = 0.0
        paint_item(p, r, S, cosmetic, False, ghost)
        p.restore()
        if selected:
            p.save()
            p.setPen(_pen(SEL_COLOR, cosmetic, True, 1.2))
            p.setBrush(Qt.NoBrush)
            from annotations_extra import _base_bbox
            p.drawPolygon(xform(it).map(QPolygonF(_base_bbox(it).adjusted(-1.5, -1.5, 1.5, 1.5))))
            p.restore()
        return
    if it["type"] in EXTRA:
        p.save()
        if ghost:
            p.setOpacity(0.55)
        EXTRA[it["type"]]["paint"](p, it, cosmetic)
        if selected:
            p.setOpacity(1.0)
            p.setPen(_pen(SEL_COLOR, cosmetic, True, 1.2))
            p.setBrush(Qt.NoBrush)
            p.drawRect(item_bbox(it, S).adjusted(-1.5, -1.5, 1.5, 1.5))
        p.restore()
        return
    if it["type"] == "trafo":
        p.save()
        if ghost:
            p.setOpacity(0.55)
        paint_trafo(p, it, cosmetic)
        if selected:
            p.setPen(_pen(SEL_COLOR, cosmetic, True, 1.2))
            p.setBrush(Qt.NoBrush)
            p.drawRect(trafo_rect(it).adjusted(-1.5, -1.5, 1.5, 1.5))
        p.restore()
        return
    if it["type"] in ("ink", "text"):
        p.save()
        (paint_ink if it["type"] == "ink" else paint_text)(p, it)
        if it["type"] == "text" and cosmetic:
            fp = _pen(SEL_COLOR if selected else "#9aa8b4", True, True, 1.0)
            p.setPen(fp)
            p.setBrush(Qt.NoBrush)
            p.drawRect(text_frame(it))
            selected = False
        if selected:
            p.setPen(_pen(SEL_COLOR, cosmetic, True, 1.2))
            p.setBrush(Qt.NoBrush)
            p.drawRect(item_bbox(it, S).adjusted(-1.5, -1.5, 1.5, 1.5))
        p.restore()
        return
    color = it.get("color") or (DIM_COLOR if it["type"] == "dim" else HOLE_COLOR)
    if ghost:
        c = QColor(color)
        c.setAlpha(150)
        color = c
    p.save()
    p.setBrush(Qt.NoBrush)
    if it["type"] == "dim":
        (x1, y1), (x2, y2) = it["p1"], it["p2"]
        p.setPen(_pen(color, cosmetic))
        p.drawLine(QPointF(x1, y1), QPointF(x2, y2))
        L = math.hypot(x2 - x1, y2 - y1)
        if L > 0:
            ux, uy = (x2 - x1) / L, (y2 - y1) / L
            t = 2.2  # חצי אורך סימון הקצה (נקודות נייר)
            # סימון אלכסוני 45° בכל קצה, כמו בקווי מידה
            dx, dy = (ux - uy) * t / math.sqrt(2), (uy + ux) * t / math.sqrt(2)
            for x, y in ((x1, y1), (x2, y2)):
                p.drawLine(QPointF(x - dx, y - dy), QPointF(x + dx, y + dy))
        _draw_label(p, it, S, color, white_bg=True)
    else:
        dashed = it["kind"] == "ceil"
        p.setPen(_pen(color, cosmetic, dashed))
        if is_circle(it):
            r = hole_half(it, S)[0]
            cx, cy = it["c"]
            p.drawEllipse(QPointF(cx, cy), r, r)
            t = math.radians(it.get("angle", 0.0) + 45)
            for a in (t, t + math.pi / 2):
                p.drawLine(QPointF(cx - r * math.cos(a), cy - r * math.sin(a)),
                           QPointF(cx + r * math.cos(a), cy + r * math.sin(a)))
        else:
            c = hole_corners(it, S)
            p.drawPolygon(QPolygonF(c))
            p.drawLine(c[0], c[2])
            if it["kind"] != "wall":
                p.drawLine(c[1], c[3])
        _draw_label(p, it, S, color, white_bg=False)
    if selected:
        sp = _pen(SEL_COLOR, cosmetic, True, 1.2)
        p.setPen(sp)
        p.setBrush(Qt.NoBrush)
        p.drawRect(item_bbox(it, S).adjusted(-1.5, -1.5, 1.5, 1.5))
    p.restore()


# ---------------------------------------------------------------- baking into the PDF
def bake_page(page, items, S):
    """מטמיע את הסימונים כתוכן וקטורי בעמוד (יופיעו בכל תוכנה)."""
    import pymupdf
    if not items:
        return
    page.wrap_contents()
    m = page.derotation_matrix

    def P(x, y):
        return pymupdf.Point(x, y) * m

    shape = page.new_shape()
    for it in items:
        if it["type"] in ("text", "trafo") or it["type"] in EXTRA:
            continue
        if it["type"] == "ink":
            pts = [P(x, y) for x, y in it["pts"]]
            if len(pts) >= 2:
                shape.draw_polyline(pts)
                shape.finish(oc=OC(), color=_rgb(it["color"]), width=it["w"] * PT_PER_MM,
                             lineCap=1, lineJoin=1, closePath=False)
            continue
        if it["type"] == "dim":
            col = _rgb(it.get("color") or DIM_COLOR)
            (x1, y1), (x2, y2) = it["p1"], it["p2"]
            shape.draw_line(P(x1, y1), P(x2, y2))
            L = math.hypot(x2 - x1, y2 - y1)
            if L > 0:
                ux, uy = (x2 - x1) / L, (y2 - y1) / L
                t = 2.2
                dx, dy = (ux - uy) * t / math.sqrt(2), (uy + ux) * t / math.sqrt(2)
                for x, y in ((x1, y1), (x2, y2)):
                    shape.draw_line(P(x - dx, y - dy), P(x + dx, y + dy))
            shape.finish(oc=OC(), color=col, width=PRINT_LINE_PT, closePath=False)
        else:
            col = _rgb(it.get("color") or HOLE_COLOR)
            dashes = "[4 2.5] 0" if it["kind"] == "ceil" else None
            if is_circle(it):
                r = hole_half(it, S)[0]
                cx, cy = it["c"]
                shape.draw_circle(P(cx, cy), r)
                t = math.radians(it.get("angle", 0.0) + 45)
                for a in (t, t + math.pi / 2):
                    shape.draw_line(P(cx - r * math.cos(a), cy - r * math.sin(a)),
                                    P(cx + r * math.cos(a), cy + r * math.sin(a)))
            else:
                c = hole_corners(it, S)
                pts = [P(q.x(), q.y()) for q in c]
                shape.draw_polyline(pts + [pts[0]])
                shape.draw_line(pts[0], pts[2])
                if it["kind"] != "wall":
                    shape.draw_line(pts[1], pts[3])
            shape.finish(oc=OC(), color=col, width=PRINT_LINE_PT, dashes=dashes, closePath=False)
    shape.commit()
    for it in items:
        if it["type"] == "ink":
            continue
        if it.get("angle") and it["type"] in ("trafo", "mark", "stamp", "shape"):
            from annotations_extra import bake_rotated
            bake_rotated(page, it, m)
            continue
        if it["type"] == "text":
            bake_text(page, it, m)
            continue
        if it["type"] == "trafo":
            bake_trafo(page, it, m)
            continue
        if it["type"] in EXTRA:
            EXTRA[it["type"]]["bake"](page, it, m)
            continue
        lr = label_rect(it, S)
        is_dim = it["type"] == "dim"
        rect = pymupdf.Rect(lr.left() - 30, lr.top() - 1, lr.right() + 30, lr.bottom() + 3)
        if is_dim:
            bg = pymupdf.Rect(lr.left(), lr.top(), lr.right(), lr.bottom()) * m
            page.draw_rect(bg, color=None, fill=(1, 1, 1), fill_opacity=0.92, overlay=True, oc=OC())
        color = it.get("color") or (DIM_COLOR if is_dim else HOLE_COLOR)
        html = (f'<div dir="rtl" style="font-family:sans-serif;font-size:{LABEL_PT * 0.98:.2f}pt;'
                f'line-height:1;color:{color};text-align:center">{label_text(it, S)}</div>')
        page.insert_htmlbox((rect * m).normalize() if page.rotation else rect, html,
                            rotate=page.rotation, overlay=True, oc=OC())


# ---------------------------------------------------------------- resize handles
def _dim_keys(it):
    """אילו מידות (בס"מ) קובעות את חצי-הרוחב וחצי-העומק של טביעת החור."""
    if it["kind"] == "wall":
        return ("d" if it["shape"] == "round" else "w"), "thick"
    return "w", "l"


def hole_handles(it, S):
    """ידיות גרירה: ((מיקום בעמוד), (sx, sy))."""
    a, b = hole_half(it, S)
    t = math.radians(it.get("angle", 0.0))
    c, s = math.cos(t), math.sin(t)
    cx, cy = it["c"]
    if is_circle(it):
        hs = [(1, 0), (-1, 0), (0, 1), (0, -1)]
    else:
        hs = [(sx, sy) for sx in (-1, 0, 1) for sy in (-1, 0, 1) if (sx, sy) != (0, 0)]
    out = []
    for sx, sy in hs:
        x, y = sx * a, sy * b
        out.append((QPointF(cx + x * c - y * s, cy + x * s + y * c), (sx, sy)))
    return out


def resize_hole(it, orig, hh, pt, S):
    """גרירת ידית: הצלע הנגדית נשארת במקומה, המידות מתעגלות לס"מ שלם."""
    sx, sy = hh
    t = math.radians(orig.get("angle", 0.0))
    c, s = math.cos(t), math.sin(t)
    cx0, cy0 = orig["c"]
    dx, dy = pt.x() - cx0, pt.y() - cy0
    lx, ly = dx * c + dy * s, -dx * s + dy * c          # נקודה במערכת המקומית של החור
    if is_circle(orig):
        r = math.hypot(lx, ly)
        it["d"] = max(1.0, round(pt_to_cm(2 * r, S)))
        it["c"] = orig["c"]
        return
    a0, b0 = hole_half(orig, S)
    ka, kb = _dim_keys(orig)
    if orig["shape"] == "square":
        it["shape"] = "rect"
    ncx, ncy = 0.0, 0.0
    if sx:
        fx = -sx * a0
        cm = max(1.0, round(pt_to_cm(max(0.0, sx * (lx - fx)), S)))
        it[ka] = cm
        ncx = fx + sx * cm_to_pt(cm, S) / 2
    if sy:
        fy = -sy * b0
        cm = max(1.0, round(pt_to_cm(max(0.0, sy * (ly - fy)), S)))
        it[kb] = cm
        ncy = fy + sy * cm_to_pt(cm, S) / 2
    it["c"] = (cx0 + ncx * c - ncy * s, cy0 + ncx * s + ncy * c)


def handle_cursor(it, hh):
    sx, sy = hh
    if sx == "e":
        return Qt.CrossCursor
    if sx == "r":
        return Qt.PointingHandCursor
    ang = it.get("angle", 0.0) % 180
    swap = 45 <= ang < 135
    if sx and sy:
        diag = (sx * sy > 0) != swap
        return Qt.SizeFDiagCursor if diag else Qt.SizeBDiagCursor
    horiz = bool(sx) != swap
    return Qt.SizeHorCursor if horiz else Qt.SizeVerCursor


# ---------------------------------------------------------------- free pen (ink)
def _rgb(hexcol):
    c = QColor(hexcol)
    return (c.redF(), c.greenF(), c.blueF())


def ink_bbox(it):
    xs = [x for x, _ in it["pts"]]
    ys = [y for _, y in it["pts"]]
    h = it["w"] * PT_PER_MM / 2
    return QRectF(QPointF(min(xs) - h, min(ys) - h), QPointF(max(xs) + h, max(ys) + h))


def _seg_dist(px, py, x1, y1, x2, y2):
    dx, dy = x2 - x1, y2 - y1
    L2 = dx * dx + dy * dy
    t = 0.0 if L2 == 0 else max(0.0, min(1.0, ((px - x1) * dx + (py - y1) * dy) / L2))
    return math.hypot(px - (x1 + t * dx), py - (y1 + t * dy))


def ink_hit(it, pt, tol):
    pts = it["pts"]
    tol = tol + it["w"] * PT_PER_MM / 2
    if len(pts) == 1:
        return math.hypot(pt.x() - pts[0][0], pt.y() - pts[0][1]) <= tol
    return any(_seg_dist(pt.x(), pt.y(), *pts[k], *pts[k + 1]) <= tol for k in range(len(pts) - 1))


def paint_ink(p, it):
    pts = it["pts"]
    pen = QPen(QColor(it["color"]))
    pen.setWidthF(max(0.05, it["w"] * PT_PER_MM))
    pen.setCapStyle(Qt.RoundCap)
    pen.setJoinStyle(Qt.RoundJoin)
    p.setPen(pen)
    p.setBrush(Qt.NoBrush)
    if len(pts) == 1:
        p.drawPoint(QPointF(*pts[0]))
        return
    path = QPainterPath(QPointF(*pts[0]))
    for x, y in pts[1:]:
        path.lineTo(x, y)
    p.drawPath(path)


def erase_ink(items, pt, r):
    """מחק: מסיר את חלקי הקווים שבתוך עיגול ברדיוס r סביב הנקודה. מחזיר רשימה חדשה ודגל שינוי."""
    out, changed = [], False
    for it in items:
        if it["type"] != "ink" or not ink_bbox(it).adjusted(-r, -r, r, r).contains(pt):
            out.append(it)
            continue
        dense = []
        pts = it["pts"]
        step = max(r / 2.0, 0.05)
        for k, (x, y) in enumerate(pts):
            if k:
                x0, y0 = pts[k - 1]
                n = int(math.hypot(x - x0, y - y0) / step)
                for j in range(1, n):
                    dense.append((x0 + (x - x0) * j / n, y0 + (y - y0) * j / n))
            dense.append((x, y))
        segs, cur = [], []
        for q in dense:
            if math.hypot(q[0] - pt.x(), q[1] - pt.y()) <= r:
                changed = True
                if len(cur) >= 2:
                    segs.append(cur)
                cur = []
            else:
                cur.append(q)
        if len(cur) >= 2:
            segs.append(cur)
        if len(segs) == 1 and len(segs[0]) == len(dense):
            out.append(it)
            continue
        for sg in segs:
            n = dict(it)
            n["pts"] = sg
            out.append(n)
    return out, changed


# ---------------------------------------------------------------- free text
def _text_lines(it):
    return it["text"].split("\n") if it["text"] else [""]


def text_rect(it):
    """מלבן הטקסט. נקודת העיגון p היא הפינה הימנית-עליונה (עברית מיושרת לימין)."""
    size = it["size"] * PT_PER_MM
    k = size / 100.0
    w = 0.0
    for line in _text_lines(it):
        br = _text_path(line or " ").boundingRect()
        w = max(w, br.width() * k)
    n = len(_text_lines(it))
    lh = size * 1.25
    x, y = it["p"]
    return QRectF(x - w, y, w, n * lh)


def paint_text(p, it):
    size = it["size"] * PT_PER_MM
    k = size / 100.0
    lh = size * 1.25
    x, y = it["p"]
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(it["color"]))
    for i, line in enumerate(_text_lines(it)):
        if not line.strip():
            continue
        path = _text_path(line)
        br = path.boundingRect()
        p.save()
        p.translate(x - br.right() * k, y + i * lh + size * 0.95)
        p.scale(k, k)
        p.drawPath(path)
        p.restore()


def bake_text(page, it, m):
    import pymupdf
    import html as _html
    r = text_rect(it)
    size = it["size"] * PT_PER_MM
    rect = pymupdf.Rect(r.left() - 60, r.top() - size * 0.15, r.right() + 2, r.bottom() + size * 0.6)
    body = "<br>".join(_html.escape(l) for l in _text_lines(it))
    css = (f'font-family:sans-serif;font-size:{size:.2f}pt;line-height:1.25;color:{it["color"]};'
           'text-align:right')
    page.insert_htmlbox((rect * m).normalize() if page.rotation else rect,
                        f'<div dir="rtl" style="{css}">{body}</div>',
                        rotate=page.rotation, overlay=True, oc=OC())


# ---------------------------------------------------------------- text frame & resize
def text_pad(it):
    return it["size"] * PT_PER_MM * 0.25


def text_frame(it):
    r = text_rect(it)
    d = text_pad(it)
    return r.adjusted(-d, -d, d, d)


def text_handles(it):
    f = text_frame(it)
    return [(QPointF(f.left(), f.top()), (-1, -1)), (QPointF(f.right(), f.top()), (1, -1)),
            (QPointF(f.left(), f.bottom()), (-1, 1)), (QPointF(f.right(), f.bottom()), (1, 1))]


def resize_text(it, orig, hh, pt):
    """גרירת פינה: הפינה הנגדית נשארת במקומה, הטקסט גדל או קטן באופן יחסי."""
    sx, sy = hh
    f = text_frame(orig)
    ox = f.left() if sx > 0 else f.right()
    oy = f.top() if sy > 0 else f.bottom()
    diag = math.hypot(f.width(), f.height()) or 1.0
    k = math.hypot(pt.x() - ox, pt.y() - oy) / diag
    size = max(1.0, min(60.0, round(orig["size"] * k, 1)))
    it["size"] = size
    it["p"] = orig["p"]
    nf = text_frame(it)
    w, h = nf.width(), nf.height()
    right = ox + w if sx > 0 else ox
    top = oy if sy > 0 else oy - h
    d = text_pad(it)
    it["p"] = (right - d, top + d)


# ---------------------------------------------------------------- transformer station (תחנת שנאים)
TRAFO_COLOR = "#d0021b"


def trafo_text(it):
    n = int(it.get("n", 1))
    return "שנאי 1" if n == 1 else f"{n} שנאים"


def trafo_rect(it):
    W = it["w"] * PT_PER_MM
    H = W * 0.82
    cx, cy = it["c"]
    return QRectF(cx - W / 2, cy - H / 2, W, H)


def trafo_parts(it):
    """מלבן, שני עיגולים משולבים, ומיקום הטקסט."""
    r = trafo_rect(it)
    W, H = r.width(), r.height()
    rad = W * 0.19
    cy = r.top() + H * 0.38
    c1 = QPointF(r.center().x() - W * 0.12, cy)
    c2 = QPointF(r.center().x() + W * 0.12, cy)
    tsize = W * 0.15
    base = r.top() + H * 0.86
    return r, rad, c1, c2, tsize, base


def paint_trafo(p, it, cosmetic):
    r, rad, c1, c2, tsize, base = trafo_parts(it)
    col = it.get("color") or TRAFO_COLOR
    p.setPen(_pen(col, cosmetic))
    p.setBrush(Qt.NoBrush)
    p.drawRect(r)
    p.drawEllipse(c1, rad, rad)
    p.drawEllipse(c2, rad, rad)
    path = _text_path(trafo_text(it))
    br = path.boundingRect()
    k = tsize / 100.0
    p.save()
    p.translate(r.center().x() - br.center().x() * k, base)
    p.scale(k, k)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(col))
    p.drawPath(path)
    p.restore()


def trafo_handles(it):
    r = trafo_rect(it)
    return [(QPointF(r.left(), r.top()), (-1, -1)), (QPointF(r.right(), r.top()), (1, -1)),
            (QPointF(r.left(), r.bottom()), (-1, 1)), (QPointF(r.right(), r.bottom()), (1, 1))]


def resize_trafo(it, orig, hh, pt):
    """גרירת פינה: הפינה הנגדית נשארת במקומה, הסמל גדל או קטן באופן יחסי."""
    sx, sy = hh
    r = trafo_rect(orig)
    ox = r.left() if sx > 0 else r.right()
    oy = r.top() if sy > 0 else r.bottom()
    diag = math.hypot(r.width(), r.height()) or 1.0
    k = math.hypot(pt.x() - ox, pt.y() - oy) / diag
    w = max(4.0, min(120.0, round(orig["w"] * k, 1)))
    it["w"] = w
    W = w * PT_PER_MM
    H = W * 0.82
    it["c"] = (ox + sx * W / 2, oy + sy * H / 2)


def bake_trafo(page, it, m):
    import pymupdf
    r, rad, c1, c2, tsize, base = trafo_parts(it)

    def P(x, y):
        return pymupdf.Point(x, y) * m

    shape = page.new_shape()
    q = [P(r.left(), r.top()), P(r.right(), r.top()), P(r.right(), r.bottom()), P(r.left(), r.bottom())]
    shape.draw_polyline(q + [q[0]])
    shape.draw_circle(P(c1.x(), c1.y()), rad)
    shape.draw_circle(P(c2.x(), c2.y()), rad)
    col = it.get("color") or TRAFO_COLOR
    shape.finish(oc=OC(), color=_rgb(col), width=PRINT_LINE_PT, closePath=False)
    shape.commit()
    rect = pymupdf.Rect(r.left(), base - tsize * 1.05, r.right(), base + tsize * 0.45)
    html = (f'<div dir="rtl" style="font-family:sans-serif;font-size:{tsize * 0.98:.2f}pt;'
            f'line-height:1;color:{col};text-align:center">{trafo_text(it)}</div>')
    page.insert_htmlbox((rect * m).normalize() if page.rotation else rect, html,
                        rotate=page.rotation, overlay=True, oc=OC())


from annotations_extra import EXTRA  # noqa: E402  (צורות, סימנים וחותמות)
