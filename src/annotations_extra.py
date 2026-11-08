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
        sh.finish(oc=A.OC(), color=col, width=w, lineCap=0 if k != "line" else 1, closePath=False)
        for tri in _heads(it):
            q = [P(*t) for t in tri]
            sh.draw_polyline(q + [q[0]])
            sh.finish(oc=A.OC(), color=None, fill=col, closePath=True)
    elif k == "rect":
        r = shape_box(it)
        q = [P(r.left(), r.top()), P(r.right(), r.top()), P(r.right(), r.bottom()), P(r.left(), r.bottom())]
        sh.draw_polyline(q + [q[0]])
        sh.finish(oc=A.OC(), color=col, width=w, lineJoin=1, closePath=True)
    elif k == "ellipse":
        r = shape_box(it)
        rr = pymupdf.Rect(r.left(), r.top(), r.right(), r.bottom()) * m
        sh.draw_oval(rr.normalize())
        sh.finish(oc=A.OC(), color=col, width=w)
    elif k == "cloud":
        for a, c, b in cloud_arcs(it):
            c1 = (a[0] + 2 / 3 * (c[0] - a[0]), a[1] + 2 / 3 * (c[1] - a[1]))
            c2 = (b[0] + 2 / 3 * (c[0] - b[0]), b[1] + 2 / 3 * (c[1] - b[1]))
            sh.draw_bezier(P(*a), P(*c1), P(*c2), P(*b))
        sh.finish(oc=A.OC(), color=col, width=w, lineCap=1, lineJoin=1, closePath=False)
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
        sh.finish(oc=A.OC(), color=col, width=lw, lineCap=1, closePath=False)
        sh.commit()
        return
    if k == "v":
        sh.draw_polyline([P(*q) for q in _v_pts(r)])
        sh.finish(oc=A.OC(), color=col, width=lw, lineCap=1, lineJoin=1, closePath=False)
        sh.commit()
        return
    sh.draw_circle(P(r.center().x(), r.center().y()), r.width() / 2)
    sh.finish(oc=A.OC(), color=col, fill=(1, 1, 1), width=lw)
    sh.commit()
    c, h = _mark_text_geom(it)
    fs = h / 0.72
    box = pymupdf.Rect(r.left() - r.width(), c.y() - fs * 0.62, r.right() + r.width(), c.y() + fs * 0.62)
    html = (f'<div style="font-family:sans-serif;font-weight:bold;font-size:{fs:.2f}pt;line-height:1;'
            f'color:{_color(it)};text-align:center">{_mark_text(it)}</div>')
    page.insert_htmlbox((box * m).normalize() if page.rotation else box, html,
                        rotate=page.rotation, overlay=True, oc=A.OC())


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
                      overlay=True, oc=A.OC())


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


# ================================================================ rotation (סיבוב סימנים וצורות)
from PySide6.QtGui import QTransform  # noqa: E402

BOX_SHAPES = ("rect", "ellipse", "cloud")


def rotatable(it):
    t = it["type"]
    return t in ("trafo", "mark", "stamp") or (t == "shape" and it["kind"] in BOX_SHAPES)


def center(it):
    if it["type"] == "shape":
        return shape_box(it).center()
    return QPointF(*it["c"])


def _base_bbox(it):
    t = it["type"]
    if t == "trafo":
        return A.trafo_rect(it)
    if t == "shape":
        return shape_bbox(it)
    return EXTRA[t]["bbox"](it) if t in EXTRA else A.trafo_rect(it)


def xform(it):
    """מטריצת הסיבוב סביב מרכז הסימן."""
    c = center(it)
    tr = QTransform()
    tr.translate(c.x(), c.y())
    tr.rotate(it.get("angle", 0.0))
    tr.translate(-c.x(), -c.y())
    return tr


def to_local(it, pt):
    a = it.get("angle", 0.0)
    if not a:
        return pt
    inv, _ = xform(it).inverted()
    return inv.map(pt)


def to_world(it, pt):
    a = it.get("angle", 0.0)
    return xform(it).map(pt) if a else pt


def rot_bbox(it):
    r = _base_bbox(it)
    if not it.get("angle", 0.0):
        return r
    return xform(it).map(QPolygonF(r)).boundingRect()


def rot_handles(base_handles, it):
    return [(to_world(it, loc), hh) for loc, hh in base_handles]


def rot_handle_pos(it, offset):
    """ידית הסיבוב: מעל מרכז הצלע העליונה."""
    r = _base_bbox(it)
    return to_world(it, QPointF(r.center().x(), r.top() - offset))


def apply_rotation_drag(it, pt, snap=5.0):
    c = center(it)
    ang = math.degrees(math.atan2(pt.y() - c.y(), pt.x() - c.x())) + 90.0
    ang = round(ang / snap) * snap % 360
    it["angle"] = 0.0 if abs(ang) < 1e-6 or abs(ang - 360) < 1e-6 else ang


def rotated_resize(base_resize, it, orig, hh, pt):
    """גרירת ידית של סימן מסובב: מחשבים במערכת המקומית ואז מחזירים את המרכז לעולם."""
    a = orig.get("angle", 0.0)
    if not a:
        base_resize(it, orig, hh, pt)
        return
    c0 = center(orig)
    local = to_local(orig, pt)
    base_resize(it, orig, hh, local)
    c1 = center(it)                         # מרכז חדש, במערכת המקומית סביב c0
    tr = QTransform()
    tr.translate(c0.x(), c0.y())
    tr.rotate(a)
    tr.translate(-c0.x(), -c0.y())
    w = tr.map(c1)
    dx, dy = w.x() - c1.x(), w.y() - c1.y()
    if it["type"] == "shape":
        it["p1"] = (it["p1"][0] + dx, it["p1"][1] + dy)
        it["p2"] = (it["p2"][0] + dx, it["p2"][1] + dy)
    else:
        it["c"] = (it["c"][0] + dx, it["c"][1] + dy)
    it["angle"] = a


# ----- baking rotated items: הכול וקטורי, גם הטקסט (כקווי מתאר)
def bake_text_path(page, m, text, cx, cy, height, angle, color):
    import pymupdf
    path = A._text_path(text)
    br = path.boundingRect()
    k = height / max(1.0, br.height())
    tr = QTransform()
    tr.translate(cx, cy)
    tr.rotate(angle)
    tr.scale(k, k)
    tr.translate(-br.center().x(), -br.center().y())
    sh = page.new_shape()
    for poly in tr.map(path).toSubpathPolygons():
        pts = [pymupdf.Point(q.x(), q.y()) * m for q in poly]
        if len(pts) >= 3:
            sh.draw_polyline(pts)
    sh.finish(oc=A.OC(), color=None, fill=A._rgb(color), even_odd=True, closePath=True)
    sh.commit()


def _P(m, tr, x, y):
    import pymupdf
    q = tr.map(QPointF(x, y))
    return pymupdf.Point(q.x(), q.y()) * m


def bake_rotated(page, it, m):
    """צריבה של סימן מסובב (זווית שאינה 0)."""
    import pymupdf
    tr = xform(it)
    col = _color(it)
    rgb = A._rgb(col)
    t = it["type"]
    if t == "stamp":
        import stamps
        img = stamps.colored(it["slot"], col)
        if img is None:
            return
        r = stamp_rect(it)
        bb = rot_bbox(it)
        scale = img.width() / max(1e-6, r.width())
        from PySide6.QtGui import QImage, QPainter
        out = QImage(int(bb.width() * scale) + 2, int(bb.height() * scale) + 2,
                     QImage.Format_ARGB32_Premultiplied)
        out.fill(0)
        p = QPainter(out)
        p.setRenderHint(QPainter.SmoothPixmapTransform, True)
        p.scale(scale, scale)
        p.translate(-bb.left(), -bb.top())
        p.setTransform(tr, True)
        p.drawImage(r, img)
        p.end()
        data = stamps._to_png(out.convertToFormat(QImage.Format_ARGB32))
        rect = pymupdf.Rect(bb.left(), bb.top(), bb.left() + out.width() / scale,
                            bb.top() + out.height() / scale)
        if page.rotation:
            rect = (rect * m).normalize()
        page.insert_image(rect, stream=data, rotate=page.rotation, keep_proportion=False, overlay=True, oc=A.OC())
        return
    sh = page.new_shape()
    if t == "shape":
        k = it["kind"]
        r = shape_box(it)
        w = _wpt(it)
        if k == "rect":
            q = [_P(m, tr, r.left(), r.top()), _P(m, tr, r.right(), r.top()),
                 _P(m, tr, r.right(), r.bottom()), _P(m, tr, r.left(), r.bottom())]
            sh.draw_polyline(q + [q[0]])
            sh.finish(oc=A.OC(), color=rgb, width=w, lineJoin=1, closePath=True)
        elif k == "ellipse":
            cx, cy, a, b = r.center().x(), r.center().y(), r.width() / 2, r.height() / 2
            kk = 0.5523
            segs = [((a, 0), (a, kk * b), (kk * a, b), (0, b)), ((0, b), (-kk * a, b), (-a, kk * b), (-a, 0)),
                    ((-a, 0), (-a, -kk * b), (-kk * a, -b), (0, -b)), ((0, -b), (kk * a, -b), (a, -kk * b), (a, 0))]
            for s4 in segs:
                sh.draw_bezier(*[_P(m, tr, cx + x, cy + y) for x, y in s4])
            sh.finish(oc=A.OC(), color=rgb, width=w, closePath=False)
        else:
            for a_, c_, b_ in cloud_arcs(it):
                c1 = (a_[0] + 2 / 3 * (c_[0] - a_[0]), a_[1] + 2 / 3 * (c_[1] - a_[1]))
                c2 = (b_[0] + 2 / 3 * (c_[0] - b_[0]), b_[1] + 2 / 3 * (c_[1] - b_[1]))
                sh.draw_bezier(_P(m, tr, *a_), _P(m, tr, *c1), _P(m, tr, *c2), _P(m, tr, *b_))
            sh.finish(oc=A.OC(), color=rgb, width=w, lineCap=1, lineJoin=1, closePath=False)
        sh.commit()
        return
    if t == "mark":
        r = mark_rect(it)
        lw = _mark_lw(it)
        k = it["kind"]
        if k == "x":
            sh.draw_line(_P(m, tr, r.left(), r.top()), _P(m, tr, r.right(), r.bottom()))
            sh.draw_line(_P(m, tr, r.right(), r.top()), _P(m, tr, r.left(), r.bottom()))
            sh.finish(oc=A.OC(), color=rgb, width=lw, lineCap=1, closePath=False)
            sh.commit()
            return
        if k == "v":
            sh.draw_polyline([_P(m, tr, *q) for q in _v_pts(r)])
            sh.finish(oc=A.OC(), color=rgb, width=lw, lineCap=1, lineJoin=1, closePath=False)
            sh.commit()
            return
        c = r.center()
        sh.draw_circle(_P(m, tr, c.x(), c.y()), r.width() / 2)
        sh.finish(oc=A.OC(), color=rgb, fill=(1, 1, 1), width=lw)
        sh.commit()
        cc, h = _mark_text_geom(it)
        bake_text_path(page, m, _mark_text(it), cc.x(), cc.y(), h, it.get("angle", 0.0), col)
        return
    if t == "trafo":
        r, rad, c1, c2, tsize, base = A.trafo_parts(it)
        q = [_P(m, tr, r.left(), r.top()), _P(m, tr, r.right(), r.top()),
             _P(m, tr, r.right(), r.bottom()), _P(m, tr, r.left(), r.bottom())]
        sh.draw_polyline(q + [q[0]])
        sh.draw_circle(_P(m, tr, c1.x(), c1.y()), rad)
        sh.draw_circle(_P(m, tr, c2.x(), c2.y()), rad)
        sh.finish(oc=A.OC(), color=rgb, width=A.PRINT_LINE_PT, closePath=False)
        sh.commit()
        path = A._text_path(A.trafo_text(it))
        br = path.boundingRect()
        h = br.height() * tsize / 100.0
        # מרכז הטקסט: הבסיס + מרכז האותיות
        ty = base + (br.center().y()) * tsize / 100.0
        tc = tr.map(QPointF(r.center().x(), ty))
        bake_text_path(page, m, A.trafo_text(it), tc.x(), tc.y(), h, it.get("angle", 0.0), col)
