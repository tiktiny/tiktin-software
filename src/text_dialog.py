# חלון טקסט חופשי: עברית כברירת מחדל, צבע וגודל
import sys
from PySide6.QtCore import Qt, QSettings, QTimer
from PySide6.QtGui import QTextOption, QKeySequence, QShortcut
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPlainTextEdit,
                               QPushButton, QComboBox)
from colors import ColorButton

SIZES = [("2.5 מ\"מ", 2.5), ("3.5 מ\"מ", 3.5), ("5 מ\"מ", 5.0), ("7 מ\"מ", 7.0), ("10 מ\"מ", 10.0)]


class HebrewKeyboard:
    """ב-Windows: מעביר את המקלדת לעברית בזמן הכתיבה ומחזיר את הקודמת בסיום."""

    def __init__(self):
        self.prev = None

    def on(self):
        if sys.platform != "win32":
            return
        try:
            import ctypes
            u = ctypes.windll.user32
            self.prev = u.GetKeyboardLayout(0)
            hkl = u.LoadKeyboardLayoutW("0000040D", 1)
            u.ActivateKeyboardLayout(hkl, 0)
        except Exception:
            pass

    def off(self):
        if sys.platform != "win32" or not self.prev:
            return
        try:
            import ctypes
            ctypes.windll.user32.ActivateKeyboardLayout(self.prev, 0)
        except Exception:
            pass


class TextDialog(QDialog):
    def __init__(self, parent, item=None, color=None):
        super().__init__(parent)
        self.setWindowTitle("טקסט על השרטוט")
        self.setLayoutDirection(Qt.RightToLeft)
        st = QSettings("Tiktin", "TiktinPDF")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 16, 18, 16)
        lay.setSpacing(10)

        row = QHBoxLayout()
        row.setSpacing(8)
        row.addWidget(QLabel("צבע"))
        self.color = ColorButton(item["color"] if item else (color or st.value("text_color", "#d0021b")))
        row.addWidget(self.color)
        row.addSpacing(14)
        row.addWidget(QLabel("גודל אות"))
        self.size = QComboBox()
        for t, v in SIZES:
            self.size.addItem(t, v)
        cur = item["size"] if item else st.value("text_size", 3.5, type=float)
        idx = min(range(len(SIZES)), key=lambda k: abs(SIZES[k][1] - cur))
        self.size.setCurrentIndex(idx)
        self.size.setToolTip("גובה האות על הנייר, לפי הדף המקורי")
        self.size.setFixedWidth(110)
        row.addWidget(self.size)
        row.addStretch(1)
        lay.addLayout(row)

        self.edit = QPlainTextEdit(item["text"] if item else "")
        self.edit.setLayoutDirection(Qt.RightToLeft)
        opt = QTextOption(Qt.AlignRight)
        opt.setTextDirection(Qt.RightToLeft)
        self.edit.document().setDefaultTextOption(opt)
        self.edit.setPlaceholderText("כותבים כאן. Enter = שורה חדשה, Ctrl+Enter = אישור")
        self.edit.setMinimumSize(420, 120)
        self.edit.setStyleSheet("QPlainTextEdit{background:#ffffff;color:#1f2630;border:1px solid #cfd4db;"
                                "border-radius:4px;font-size:12pt;}")
        lay.addWidget(self.edit)

        btns = QHBoxLayout()
        btns.addStretch(1)
        cancel = QPushButton("ביטול")
        cancel.setObjectName("plainBtn")
        ok = QPushButton("עדכון" if item else "הוספה")
        ok.setObjectName("primaryBtn")
        btns.addWidget(cancel)
        btns.addWidget(ok)
        lay.addLayout(btns)
        cancel.clicked.connect(self.reject)
        ok.clicked.connect(self._ok)
        QShortcut(QKeySequence("Ctrl+Return"), self, activated=self._ok)
        QShortcut(QKeySequence("Ctrl+Enter"), self, activated=self._ok)
        self.kb = HebrewKeyboard()
        QTimer.singleShot(0, self._start)

    def _start(self):
        self.edit.setFocus()
        self.edit.selectAll()
        self.kb.on()

    def done(self, r):
        self.kb.off()
        super().done(r)

    def _ok(self):
        text = self.edit.toPlainText().rstrip()
        if not text.strip():
            self.reject()
            return
        self.result_text = text
        self.result_color = self.color.color
        self.result_size = self.size.currentData()
        st = QSettings("Tiktin", "TiktinPDF")
        st.setValue("text_color", self.result_color)
        st.setValue("text_size", self.result_size)
        self.accept()
