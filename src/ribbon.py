# המראה האחיד של אפליקציות טיקטין: כפתורי סרגל עם סמל קווי אדום ומתחתיו השם.
# הסמלים מצוירים בקוד (בלי קובצי תמונה ובלי רכיבים נוספים) — קל ומהיר.
from PySide6.QtCore import Qt, QPointF, QRectF, QSize
from PySide6.QtGui import QPixmap, QPainter, QPen, QColor, QIcon, QPainterPath
from PySide6.QtWidgets import QToolButton

RED = "#c8202f"
ICON_PX = 24


def _line(pp, *pts):
    pp.moveTo(*pts[0])
    for q in pts[1:]:
        pp.lineTo(*q)


def _draw(name, pp):
    """מצייר את הסמל על רשת 24×24."""
    L = lambda *pts: _line(pp, *pts)     # noqa: E731
    if name == "open":
        L((3, 19), (3, 6), (9, 6), (11, 8), (21, 8), (21, 19), (3, 19))
        L((3, 12), (21, 12))
    elif name == "save":
        L((5, 3), (16, 3), (21, 8), (21, 20), (19, 21), (5, 21), (3, 20), (3, 5), (5, 3))
        pp.addRect(QRectF(7, 13, 10, 8))
        L((8, 3), (8, 8), (15, 8), (15, 3))
    elif name == "file":
        L((3, 19), (3, 6), (9, 6), (11, 8), (21, 8), (21, 19), (3, 19))
        L((12, 11), (12, 16))
        L((9.5, 14), (12, 16.5), (14.5, 14))
    elif name == "print":
        L((7, 9), (7, 3), (17, 3), (17, 9))
        pp.addRoundedRect(QRectF(3, 9, 18, 8), 2, 2)
        pp.addRect(QRectF(7, 14, 10, 7))
    elif name == "copy":
        L((4, 8), (4, 4), (8, 4))
        L((16, 4), (20, 4), (20, 8))
        L((20, 16), (20, 20), (16, 20))
        L((8, 20), (4, 20), (4, 16))
        pp.addRoundedRect(QRectF(8, 8, 8, 8), 1, 1)
    elif name == "add":
        pp.addEllipse(QRectF(3, 3, 18, 18))
        L((12, 8), (12, 16))
        L((8, 12), (16, 12))
    elif name == "stamp":
        pp.addRoundedRect(QRectF(9, 3, 6, 6), 3, 3)
        L((10.5, 9), (9.5, 13), (5, 14), (5, 17), (19, 17), (19, 14), (14.5, 13), (13.5, 9))
        L((5, 21), (19, 21))
    elif name == "erase":
        L((20, 20), (9, 20), (3.5, 14.5), (13.5, 4.5), (20.5, 11.5), (12, 20))
        L((8, 10), (15, 17))
    elif name == "ruler":
        pp.addRoundedRect(QRectF(2, 8, 20, 8), 1.5, 1.5)
        for x, h in ((6, 3), (10, 4), (14, 3), (18, 4)):
            L((x, 8), (x, 8 + h))
    elif name == "undo":
        L((9, 14), (4, 9), (9, 4))
        pp.moveTo(4, 9)
        pp.lineTo(14.5, 9)
        pp.arcTo(QRectF(9, 9, 11, 11), 90, -180)
        pp.lineTo(11, 20)
    elif name == "redo":
        L((15, 14), (20, 9), (15, 4))
        pp.moveTo(20, 9)
        pp.lineTo(9.5, 9)
        pp.arcTo(QRectF(4, 9, 11, 11), 90, 180)
        pp.lineTo(13, 20)
    elif name == "x":
        L((6, 6), (18, 18))
        L((18, 6), (6, 18))
    elif name == "rotate":
        pp.moveTo(20, 12)
        pp.arcTo(QRectF(4, 4, 16, 16), 0, -305)
        L((20, 4), (20, 9), (15, 9))
    elif name == "view":
        pp.moveTo(2, 12)
        pp.cubicTo(5, 6, 9, 5, 12, 5)
        pp.cubicTo(15, 5, 19, 6, 22, 12)
        pp.cubicTo(19, 18, 15, 19, 12, 19)
        pp.cubicTo(9, 19, 5, 18, 2, 12)
        pp.addEllipse(QRectF(9, 9, 6, 6))
    elif name == "full":
        L((3, 8), (3, 3), (8, 3))
        L((16, 3), (21, 3), (21, 8))
        L((21, 16), (21, 21), (16, 21))
        L((8, 21), (3, 21), (3, 16))
    elif name == "help":
        pp.addEllipse(QRectF(3, 3, 18, 18))
        pp.moveTo(9.3, 9.5)
        pp.cubicTo(9.3, 6.5, 14.7, 6.5, 14.7, 9.5)
        pp.cubicTo(14.7, 11.5, 12, 11.5, 12, 13.8)
        L((12, 16.8), (12, 17))
    elif name == "home":
        L((3, 11), (12, 3), (21, 11))
        L((5, 9.5), (5, 21), (19, 21), (19, 9.5))
        L((10, 21), (10, 14), (14, 14), (14, 21))


_cache = {}


def icon(name, color=RED, dpr=2.0):
    key = (name, color)
    ic = _cache.get(key)
    if ic is None:
        n = int(ICON_PX * dpr)
        pm = QPixmap(n, n)
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing)
        p.scale(n / 24.0, n / 24.0)
        pen = QPen(QColor(color), 1.7)
        pen.setCapStyle(Qt.RoundCap)
        pen.setJoinStyle(Qt.RoundJoin)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        pp = QPainterPath()
        _draw(name, pp)
        p.drawPath(pp)
        p.end()
        pm.setDevicePixelRatio(dpr)
        ic = _cache[key] = QIcon(pm)
    return ic


class RibbonButton(QToolButton):
    """כפתור סרגל: סמל למעלה, שם מתחת. כשהפעולה פעילה — מילוי אדום וסמל לבן."""

    def __init__(self, text, tip, icon_name, main=False):
        super().__init__()
        self.icon_name = icon_name
        self.main = main
        self.setObjectName("rbmain" if main else "rb")
        self.setText(text)
        self.setToolTip(tip)
        self.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
        self.setIconSize(QSize(ICON_PX, ICON_PX))
        self.setFocusPolicy(Qt.NoFocus)
        if icon_name:
            self.setIcon(icon(icon_name, "#ffffff" if main else RED))

    def set_active(self, on):
        if self.icon_name and not self.main:
            self.setIcon(icon(self.icon_name, "#ffffff" if on else RED))


RIBBON_STYLE = """
QToolBar#hdr { background: #ffffff; border: none; border-bottom: 1px solid #d5d9de; padding: 6px 12px; spacing: 10px; }
QToolBar#ribbon { background: #ffffff; border: none; border-bottom: 2px solid #c8202f; padding: 4px 4px; spacing: 0px; }
QToolBar#ribbon::separator { background: #d5d9de; width: 1px; margin: 4px 3px; }
QLabel#apptitle { color: #1f2328; font-size: 14pt; font-weight: 700; }
QLabel#filename { color: #5f6670; font-size: 10.5pt; }
QLabel#hver { color: #5f6670; font-size: 9.5pt; }
QToolButton#rb, QToolButton#rbmain { color: #1f2328; background: transparent; border: 1px solid transparent;
    border-radius: 8px; padding: 4px 5px 4px 5px; min-height: 58px; max-height: 58px; min-width: 40px; font-size: 9.5pt; }
QToolButton#rb:hover { background: #f4f5f7; border-color: #d5d9de; }
QToolButton#rb::menu-indicator, QToolButton#rbmain::menu-indicator { image: none; width: 0; }
QToolButton#rb::menu-button { border: none; border-right: 1px solid #d5d9de; width: 14px; }
QToolButton#rbmain { background: #c8202f; border-color: #c8202f; color: #ffffff; font-weight: 600; }
QToolButton#rbmain:hover { background: #a31724; border-color: #a31724; }
QToolButton#fz { color: #1f2328; background: #ffffff; border: 1px solid #d5d9de; border-radius: 0; margin-left: -1px;
    padding: 0 10px; min-height: 30px; max-height: 30px; min-width: 14px; font-size: 10pt; }
QToolButton#fz:hover { background: #f4f5f7; }
QLabel#pagelbl { color: #1f2328; font-size: 10pt; padding: 0 4px; }
"""
