# עורך טקסט שמופיע ישירות על השרטוט, במקום ובגודל של הטקסט הסופי
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont, QTextOption, QFontMetricsF, QColor
from PySide6.QtWidgets import QPlainTextEdit, QFrame


class InlineText(QPlainTextEdit):
    finished = Signal()

    def __init__(self, parent):
        super().__init__(parent)
        self.setFrameShape(QFrame.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setLineWrapMode(QPlainTextEdit.NoWrap)
        self.setLayoutDirection(Qt.RightToLeft)
        opt = QTextOption(Qt.AlignRight)
        opt.setTextDirection(Qt.RightToLeft)
        opt.setWrapMode(QTextOption.NoWrap)
        self.document().setDefaultTextOption(opt)
        self.document().setDocumentMargin(0)
        self._done = False

    def set_style(self, color, px):
        f = QFont("Arial")
        f.setPixelSize(max(6, int(round(px))))
        self.setFont(f)
        self.setStyleSheet(
            "QPlainTextEdit{background:rgba(255,255,255,0.55);border:1px dashed #0057b8;"
            f"color:{QColor(color).name()};padding:0px;}}")

    def fit_size(self):
        fm = QFontMetricsF(self.font())
        lines = self.toPlainText().split("\n") or [""]
        w = max(fm.horizontalAdvance(l or " ") for l in lines) + fm.averageCharWidth() * 2 + 6
        h = fm.lineSpacing() * len(lines) + 6
        return int(w), int(h)

    def keyPressEvent(self, ev):
        if ev.key() == Qt.Key_Escape or (ev.key() in (Qt.Key_Return, Qt.Key_Enter)
                                         and ev.modifiers() & Qt.ControlModifier):
            self.finish()
            return
        super().keyPressEvent(ev)

    def focusOutEvent(self, ev):
        super().focusOutEvent(ev)
        # פתיחת תפריט צבע או מעבר לחלון אחר לא מסיימים את הכתיבה
        if ev.reason() in (Qt.PopupFocusReason, Qt.ActiveWindowFocusReason):
            return
        self.finish()

    def finish(self):
        if not self._done:
            self._done = True
            self.finished.emit()
