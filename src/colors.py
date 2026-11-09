# כפתור צבע עם תפריט צבעים קבוע (עברית, בלי חלון צבעים באנגלית)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPixmap, QColor, QIcon, QPainter
from PySide6.QtWidgets import QToolButton

PALETTE = [("#d0021b", "אדום"), ("#000000", "שחור")]


def swatch(color, w=18, h=18):
    pm = QPixmap(w, h)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(QColor("#9aa3ad"))
    p.setBrush(QColor(color))
    p.drawRoundedRect(1, 1, w - 2, h - 2, 3, 3)
    p.end()
    return QIcon(pm)


class ColorButton(QToolButton):
    """שני צבעים בלבד: לחיצה מחליפה בין אדום לשחור."""
    changed = Signal(str)

    def __init__(self, color="#d0021b"):
        super().__init__()
        self.setObjectName("tb")
        self.setToolButtonStyle(Qt.ToolButtonIconOnly)
        self.setToolTip("צבע לכל הסימונים, לטקסט ולחותמות — לחיצה מחליפה בין אדום לשחור")
        self.clicked.connect(self._toggle)
        self.set_color(color, emit=False)

    def _toggle(self):
        self.set_color("#000000" if self.color != "#000000" else "#d0021b")

    def set_color(self, c, emit=True):
        c = QColor(c).name()
        if c not in dict(PALETTE):
            c = "#d0021b"
        self.color = c
        self.setIcon(swatch(c))
        self.setText(dict(PALETTE)[c])
        if emit:
            self.changed.emit(c)
