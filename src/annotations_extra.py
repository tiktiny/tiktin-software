# סוגי תוספות לשרטוט: קווים וצורות, סימנים (X, V, ?, מספור) וחותמות.
# כל הקואורדינטות בנקודות PDF של העמוד המוצג; גדלים במ"מ על הנייר.
import math
from PySide6.QtCore import Qt, QPointF, QRectF
from PySide6.QtGui import QPen, QColor, QPainterPath, QPolygonF
import annotations as A

PT = A.PT_PER_MM
SHAPE_NAMES = {"line": "קו", "arrow": "חץ", "arrow2": "חץ דו-כיווני", "rect": "מלבן",
               "ellipse": "עיגול", "cloud": "ענן תיקונים"}
MARK_NAMES = {"x": "X ביטול", "v": "V אישור", "q": "? שאלה", "num": "מספור"}
LINEAR = ("line", "arrow", "arrow2")


def _color(it):
    return it.get("color") or "#d0021b"


# ================================================================ shapes
def _wpt(it):
    return max(0.1, it.get("w", 0.5)) * PT


def shape_box(it):
    (x1, y1), (x2, y2) = it["p1"], it["p2"]
    return QRectF(QPointF(min(x1, x2), min(y1, y2)), QPointF(max(x1, x2), max(y1, y2)))


def _head_len(it):
    return max(4.0 * PT, _wpt(it) * 5.0)


def _heads(it):
    """משולשי ראש החץ: רשימת מצולעים (3 נקודות כל אחד)."""
    out = []
    (x1, y1), (x2, y2) = it["p1"], it["p2"]
    L = math.hypot(x2 - x1, y2 - y1)
    if L < 1e-6:
        return out
    ux, uy = (x2 - x1) / L, (y2 - y1) / L
    hl = min(_head_len(it), L * 0.45)
    hw = hl * 0.38
    ends = [((x2, y2), (ux, uy))]
    if it["kind"] == "arrow2":
        ends.append(((x1, y1), (-ux, -uy)))
    for (ex, ey), (dx, dy) in ends:
        bx, by = ex - dx * hl, ey - dy * hl
        out.append([(ex, ey), (bx - dy * hw, by + dx * hw), (bx + dy * hw, by - dx * hw)])
    return out


def _line_ends(it):
    """הקו עצמו מתקצר מתחת לראש החץ כדי שהקצה יהיה חד."""
    (x1, y1), (x2, y2) = it["p1"], it["p2"]
    L = math.hypot(x2 - x1, y2 - y1)
    if L < 1e-6 or it["kind"] == "line":
        return (x1, y1), (x2, y2)
    ux, uy = (x2 - x1) / L, (y2 - y1) / L
    hl = min(_head_len(it), L * 0.45) * 0.8
    a = (x1 + ux * hl, y1 + uy * hl) if it["kind"] == "arrow2" else (x1, y1)
    return a, (x2 - ux * hl, y2 - uy * hl)


def cloud_arcs(it):
    """ענן: רצף קשתות לאורך היקף המלבן. מחזיר [(a, ctrl, b)] של עקומות ריבועיות."""
    r = shape_box(it)
    step = max(3.0 * PT, _wpt(it) * 6)
    pts = []
    corners = [r.topLeft(), r.topRight(), r.bottomRight(), r.bottomLeft()]
    for k in range(4):
        a, b = corners[k], corners[(k + 1) % 4]
        L = math.hypot(b.x() - a.x(), b.y() - a.y())
        n = max(1, int(round(L / step)))
        for j in range(n):
            pts.append(QPointF(a.x() + (b.x() - a.x()) * j / n, a.y() + (b.y() - a.y()) * j / n))
    c = r.center()
    out = []
    for k in range(len(pts)):
        a, b = pts[k], pts[(k + 1) % len(pts)]
        mx, my = (a.x() + b.x()) / 2, (a.y() + b.y()) / 2
        dx, dy = b.x() - a.x(), b.y() - a.y()
        L = math.hypot(dx, dy) or 1.0
        nx, ny = dy / L, -dx / L
        if (mx - c.x()) * nx + (my - c.y()) * ny < 0:
            nx, ny = -nx, -ny
        out.append(((a.x(), a.y()), (mx + nx * L * 0.55, my + ny * L * 0.55), (b.x(), b.y())))
    return out


def shape_bbox(it):
    pad = _wpt(it) / 2
    r = shape_box(it)
    if it["kind"] in ("arrow", "arrow2"):
        pad = max(pad, _head_len(it) * 0.4)
    if it["kind"] == "cloud":
        pad = max(pad, max(3.0 * PT, _wpt(it) * 6) * 0.3)
    return r.adjusted(-pad, -pad, pad, pad)


def shape_hit(it, pt, tol):
    tol = tol + _wpt(it) / 2
    k = it["kind"]
    if k in LINEAR:
        (x1, y1), (x2, y2) = it["p1"], it["p2"]
        return A._seg_dist(pt.x(), pt.y(), x1, y1, x2, y2) <= tol + 1
    r = shape_box(it)
    if k == "ellipse":
        a, b = r.width() / 2 or 1e-6, r.height() / 2 or 1e-6
        dx, dy = (pt.x() - r.center().x()) / a, (pt.y() - r.center().y()) / b
        d = math.hypot(dx, dy)
        return abs(d - 1) * min(a, b) <= tol + 1
    if k == "cloud":
        r = shape_bbox(it)
        inner = shape_box(it).adjusted(tol * 3, tol * 3, -tol * 3, -tol * 3)
        return r.adjusted(-tol, -tol, tol, tol).contains(pt) and not inner.contains(pt)
    # מלבן: קרוב לאחת הצלעות
    out = r.adjusted(-tol, -tol, tol, tol)
    inn = r.adjusted(tol, tol, -tol, -tol)
    return out.contains(pt) and not (inn.isValid() and inn.contains(pt))


def _shape_pen(it, cosmetic):
    pen = QPen(QColor(_color(it)))
    pen.setWidthF(_wpt(it))
    pen.setCapStyle(Qt.FlatCap if it["kind"] in ("arrow", "arrow2") else Qt.RoundCap)
    pen.setJoinStyle(Qt.RoundJoin)
    return pen


def paint_shape(p, it, cosmetic):
    k = it["kind"]
    p.setPen(_shape_pen(it, cosmetic))
    p.setBrush(Qt.NoBrush)
    if k in LINEAR:
        a, b = _line_ends(it)
        p.drawLine(QPointF(*a), QPointF(*b))
        if k != "line":
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(_color(it)))
            for tri in _heads(it):
                p.drawPolygon(QPolygonF([QPointF(*q) for q in tri]))
        return
    r = shape_box(it)
    if k == "rect":
        p.drawRect(r)
    elif k == "ellipse":
        p.drawEllipse(r)
    elif k == "cloud":
        arcs = cloud_arcs(it)
        if arcs:
            path = QPainterPath(QPointF(*arcs[0][0]))
            for a, c, b in arcs:
                path.quadTo(QPointF(*c), QPointF(*b))
            p.drawPath(path)


def bake_shape(page, it, m):
    import pymupdf

    def P(x, y):
        return pymupdf.Point(x, y) * m

    col = A._rgb(_color(it))
    w = _wpt(it)
    k = it["kind"]
    sh = page.new_shape()
    if k in LINEAR:
        a, b = _line_ends(it)
        sh.draw_line(P(*a), P(*b))
        sh.finish(color=col, width=w, lineCap=0 if k != "line" else 1, closePath=False)
        for tri in _heads(it):
            q = [P(*t) for t in tri]
            sh.draw_polyline(q + [q[0]])
            sh.finish(color=None, fill=col, closePath=True)
    elif k == "rect":
        r = shape_box(it)
        q = [P(r.left(), r.top()), P(r.right(), r.top()), P(r.right(), r.bottom()), P(r.left(), r.bottom())]
        sh.draw_polyline(q + [q[0]])
        sh.finish(color=col, width=w, lineJoin=1, closePath=True)
    elif k == "ellipse":
        r = shape_box(it)
        rr = pymupdf.Rect(r.left(), r.top(), r.right(), r.bottom()) * m
        sh.draw_oval(rr.normalize())
        sh.finish(color=col, width=w)
    elif k == "cloud":
        for a, c, b in cloud_arcs(it):
            c1 = (a[0] + 2 / 3 * (c[0] - a[0]), a[1] + 2 / 3 * (c[1] - a[1]))
            c2 = (b[0] + 2 / 3 * (c[0] - b[0]), b[1] + 2 / 3 * (c[1] - b[1]))
            sh.draw_bezier(P(*a), P(*c1), P(*c2), P(*b))
        sh.finish(color=col, width=w, lineCap=1, lineJoin=1, closePath=False)
    sh.commit()


def shape_handles(it):
    if it["kind"] in LINEAR:
        return [(QPointF(*it["p1"]), ("e", 1)), (QPointF(*it["p2"]), ("e", 2))]
    r = shape_box(it)
    return [(QPointF(r.left(), r.top()), (-1, -1)), (QPointF(r.right(), r.top()), (1, -1)),
            (QPointF(r.left(), r.bottom()), (-1, 1)), (QPointF(r.right(), r.bottom()), (1, 1))]


def resize_shape(it, orig, hh, pt):
    if hh[0] == "e":
        it["p1" if hh[1] == 1 else "p2"] = (pt.x(), pt.y())
        return
    r = shape_box(orig)
    sx, sy = hh
    fx = r.left() if sx > 0 else r.right()
    fy = r.top() if sy > 0 else r.bottom()
    it["p1"], it["p2"] = (fx, fy), (pt.x(), pt.y())


# ================================================================ marks (X, V, ?, numbers)
def mark_rect(it):
    s = it.get("s", 6.0) * PT
    cx, cy = it["c"]
    return QRectF(cx - s / 2, cy - s / 2, s, s)


def _mark_lw(it):
    return max(0.35 * PT, it.get("s", 6.0) * PT * 0.09)


def _v_pts(r):
    return [(r.left() + r.width() * 0.08, r.top() + r.height() * 0.55),
            (r.left() + r.width() * 0.38, r.bottom() - r.height() * 0.1),
            (r.right() - r.width() * 0.05, r.top() + r.height() * 0.1)]


def _mark_text(it):
    return "?" if it["kind"] == "q" else str(it.get("n", 1))


def _mark_text_geom(it):
    """מיקום הטקסט בתוך העיגול: (מרכז, גובה)."""
    r = mark_rect(it)
    t = _mark_text(it)
    h = r.height() * (0.62 if len(t) < 2 else 0.5 if len(t) == 2 else 0.4)
    return r.center(), h


def paint_mark(p, it, cosmetic):
    r = mark_rect(it)
    col = QColor(_color(it))
    pen = QPen(col)
    pen.setWidthF(_mark_lw(it))
    pen.setCapStyle(Qt.RoundCap)
    pen.setJoinStyle(Qt.RoundJoin)
    p.setPen(pen)
    p.setBrush(Qt.NoBrush)
    k = it["kind"]
    if k == "x":
        p.drawLine(r.topLeft(), r.bottomRight())
        p.drawLine(r.topRight(), r.bottomLeft())
        return
    if k == "v":
        p.drawPolyline(QPolygonF([QPointF(*q) for q in _v_pts(r)]))
        return
    p.setBrush(QColor(255, 255, 255))
    p.drawEllipse(r)
    path = A._text_path(_mark_text(it))
    br = path.boundingRect()
    c, h = _mark_text_geom(it)
    kk = h / max(1.0, br.height())
    p.save()
    p.translate(c.x() - br.center().x() * kk, c.y() - br.center().y() * kk)
    p.scale(kk, kk)
    p.setPen(Qt.NoPen)
    p.setBrush(col)
    p.drawPath(path)
    p.restore()


def bake_mark(page, it, m):
    import pymupdf

    def P(x, y):
        return pymupdf.Point(x, y) * m

    r = mark_rect(it)
    col = A._rgb(_color(it))
    lw = _mark_lw(it)
    sh = page.new_shape()
    k = it["kind"]
    if k == "x":
        sh.draw_line(P(r.left(), r.top()), P(r.right(), r.bottom()))
        sh.draw_line(P(r.right(), r.top()), P(r.left(), r.bottom()))
        sh.finish(color=col, width=lw, lineCap=1, closePath=False)
        sh.commit()
        return
    if k == "v":
        sh.draw_polyline([P(*q) for q in _v_pts(r)])
        sh.finish(color=col, width=lw, lineCap=1, lineJoin=1, closePath=False)
        sh.commit()
        return
    sh.draw_circle(P(r.center().x(), r.center().y()), r.width() / 2)
    sh.finish(color=col, fill=(1, 1, 1), width=lw)
    sh.commit()
    c, h = _mark_text_geom(it)
    fs = h / 0.72
    box = pymupdf.Rect(r.left() - r.width(), c.y() - fs * 0.62, r.right() + r.width(), c.y() + fs * 0.62)
    html = (f'<div style="font-family:sans-serif;font-weight:bold;font-size:{fs:.2f}pt;line-height:1;'
            f'color:{_color(it)};text-align:center">{_mark_text(it)}</div>')
    page.insert_htmlbox((box * m).normalize() if page.rotation else box, html,
                        rotate=page.rotation, overlay=True)


def corner_handles(r):
    return [(QPointF(r.left(), r.top()), (-1, -1)), (QPointF(r.right(), r.top()), (1, -1)),
            (QPointF(r.left(), r.bottom()), (-1, 1)), (QPointF(r.right(), r.bottom()), (1, 1))]


def resize_mark(it, orig, hh, pt):
    r = mark_rect(orig)
    sx, sy = hh
    ox = r.left() if sx > 0 else r.right()
    oy = r.top() if sy > 0 else r.bottom()
    side = max(abs(pt.x() - ox), abs(pt.y() - oy))
    s = max(2.0, min(80.0, round(side / PT, 1)))
    it["s"] = s
    S = s * PT
    it["c"] = (ox + sx * S / 2, oy + sy * S / 2)


# ================================================================ stamps
def stamp_rect(it):
    W = it["w"] * PT
    H = W * it.get("ar", 0.5)
    cx, cy = it["c"]
    return QRectF(cx - W / 2, cy - H / 2, W, H)


def paint_stamp(p, it, cosmetic):
    import stamps
    img = stamps.colored(it["slot"], _color(it))
    r = stamp_rect(it)
    if img is None:
        p.setPen(A._pen("#9aa8b4", cosmetic, True, 1.0))
        p.setBrush(Qt.NoBrush)
        p.drawRect(r)
        return
    p.save()
    p.setRenderHint(p.RenderHint.SmoothPixmapTransform, True)
    p.drawImage(r, img)
    p.restore()


def bake_stamp(page, it, m):
    import pymupdf
    import stamps
    data = stamps.png_bytes(it["slot"], _color(it))
    if not data:
        return
    r = stamp_rect(it)
    rect = pymupdf.Rect(r.left(), r.top(), r.right(), r.bottom())
    if page.rotation:
        rect = (rect * m).normalize()
    page.insert_image(rect, stream=data, rotate=page.rotation, keep_proportion=False,
                      overlay=True)


def resize_stamp(it, orig, hh, pt):
    r = stamp_rect(orig)
    sx, sy = hh
    ox = r.left() if sx > 0 else r.right()
    oy = r.top() if sy > 0 else r.bottom()
    diag = math.hypot(r.width(), r.height()) or 1.0
    k = math.hypot(pt.x() - ox, pt.y() - oy) / diag
    w = max(5.0, min(300.0, round(orig["w"] * k, 1)))
    it["w"] = w
    W = w * PT
    H = W * orig.get("ar", 0.5)
    it["c"] = (ox + sx * W / 2, oy + sy * H / 2)


def _rect_hit(rf):
    return lambda it, pt, tol: rf(it).adjusted(-tol, -tol, tol, tol).contains(pt)


EXTRA = {
    "shape": {"bbox": shape_bbox, "hit": shape_hit, "paint": paint_shape, "bake": bake_shape,
              "handles": shape_handles, "resize": resize_shape},
    "mark": {"bbox": mark_rect, "hit": _rect_hit(mark_rect), "paint": paint_mark, "bake": bake_mark,
             "handles": lambda it: corner_handles(mark_rect(it)), "resize": resize_mark},
    "stamp": {"bbox": stamp_rect, "hit": _rect_hit(stamp_rect), "paint": paint_stamp, "bake": bake_stamp,
              "handles": lambda it: corner_handles(stamp_rect(it)), "resize": resize_stamp},
}
