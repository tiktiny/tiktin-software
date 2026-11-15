# חלון הגדרת מידות חור (רצפה / תקרה / קיר)
from PySide6.QtCore import Qt, QTimer, QSettings
from PySide6.QtGui import QDoubleValidator
from PySide6.QtWidgets import (QComboBox, QDialog, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel,
                               QLineEdit, QPushButton)
from annotations import KIND_NAME

DEFAULTS = {
    "floor": {"shape": "rect", "w": 40, "l": 40, "d": 15, "angle": 0},
    "ceil": {"shape": "rect", "w": 40, "l": 40, "d": 15, "angle": 0},
    "wall": {"shape": "rect", "w": 30, "h": 20, "d": 15, "thick": 20, "bottom": "", "angle": 0},
}


class NumField(QLineEdit):
    """שדה מספרי: כפתור X לניקוי, והקשה ראשונה מחליפה את הערך הקיים."""

    def __init__(self, value, allow_empty=False):
        super().__init__("" if value in (None, "") else f"{float(value):g}")
        self.allow_empty = allow_empty
        self.setClearButtonEnabled(True)
        v = QDoubleValidator(0.0, 100000.0, 1, self)
        v.setNotation(QDoubleValidator.StandardNotation)
        self.setValidator(v)
        self.setAlignment(Qt.AlignCenter)
        self.setFixedWidth(110)

    def focusInEvent(self, ev):
        super().focusInEvent(ev)
        QTimer.singleShot(0, self.selectAll)

    def value(self):
        t = self.text().strip()
        if not t:
            return "" if self.allow_empty else None
        try:
            return float(t)
        except ValueError:
            return None


class HoleDialog(QDialog):
    def __init__(self, parent, kind, item=None, shape=None):
        super().__init__(parent)
        self.kind = kind
        self.setWindowTitle(KIND_NAME[kind])
        self.setLayoutDirection(Qt.RightToLeft)
        st = QSettings("Tiktin", "TiktinPDF")
        base = dict(DEFAULTS[kind])
        saved = st.value(f"hole_{kind}")
        if isinstance(saved, dict):
            base.update(saved)
        if item:
            base.update({k: item[k] for k in item if k in base})
        if shape:
            base["shape"] = shape
        self.base = base
        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 18, 20, 18)
        lay.setSpacing(14)

        # צורה: תפריט נפתח (לא כרטיסיות)
        self.shape_box = QComboBox()
        for key, text in (("rect", "מלבני"), ("square", "מרובע"), ("round", "עגול")):
            self.shape_box.addItem(text, key)
        self.shape_box.setCurrentIndex(max(0, self.shape_box.findData(base["shape"])))
        self.shape_box.setMinimumWidth(140)
        row = QHBoxLayout()
        row.addWidget(QLabel("צורה"))
        row.addSpacing(10)
        row.addWidget(self.shape_box)
        row.addStretch(1)
        lay.addLayout(row)

        self.grid = QGridLayout()
        self.grid.setHorizontalSpacing(12)
        self.grid.setVerticalSpacing(10)
        lay.addLayout(self.grid)
        self.f = {}
        specs = [("w", "רוחב (ס\"מ)"), ("l", "אורך (ס\"מ)"), ("h", "גובה (ס\"מ)"),
                 ("d", "קוטר (ס\"מ)"), ("thick", "עובי קיר (ס\"מ)"),
                 ("bottom", "גובה תחתית מהרצפה (ס\"מ)"), ("angle", "סיבוב (מעלות)")]
        self.rows = {}
        for r, (key, label) in enumerate(specs):
            if key not in base:
                continue
            lab = QLabel(label)
            fld = NumField(base.get(key), allow_empty=(key == "bottom"))
            if key == "bottom":
                fld.setToolTip("לא חובה — אם ממלאים, יופיע בתווית")
            if key == "angle":
                fld.setToolTip("0 = לאורך הדף, 90 = לרוחב. אפשר גם לסובב אחר כך עם המקש R")
            self.grid.addWidget(lab, r, 0)
            self.grid.addWidget(fld, r, 1, Qt.AlignRight)
            self.f[key] = fld
            self.rows[key] = (lab, fld)
        self.grid.setColumnStretch(2, 1)
        self.err = QLabel("")
        self.err.setStyleSheet("color:#c8202f;")
        lay.addWidget(self.err)

        btns = QHBoxLayout()
        btns.addStretch(1)
        cancel = QPushButton("ביטול")
        cancel.setObjectName("plainBtn")
        ok = QPushButton("עדכון" if item else "המשך להצבה")
        ok.setObjectName("primaryBtn")
        ok.setDefault(True)
        ok.setToolTip("אחרי הלחיצה מקליקים על השרטוט במקום החור")
        btns.addWidget(cancel)
        btns.addWidget(ok)
        lay.addLayout(btns)
        cancel.clicked.connect(self.reject)
        ok.clicked.connect(self._ok)
        self.shape_box.currentIndexChanged.connect(lambda *_: self._refresh())
        self._refresh()

    def shape(self):
        return self.shape_box.currentData()

    def _refresh(self, *_):
        rnd = self.shape() == "round"
        sq = self.shape() == "square"
        show = {"w": not rnd, "l": not rnd and not sq, "h": not rnd and not sq, "d": rnd,
                "thick": True, "bottom": True, "angle": True}
        if "w" in self.rows:
            self.rows["w"][0].setText("צלע (ס\"מ)" if sq else "רוחב (ס\"מ)")
        for k, (lab, fld) in self.rows.items():
            lab.setVisible(show[k])
            fld.setVisible(show[k])
        first = "d" if rnd else "w"
        if first in self.f:
            QTimer.singleShot(0, self.f[first].setFocus)
        self.adjustSize()

    def _ok(self):
        out = {"shape": self.shape()}
        for k, fld in self.f.items():
            if not fld.isVisible():
                out[k] = self.base.get(k)
                continue
            v = fld.value()
            if v is None or (k not in ("bottom", "angle") and v == 0):
                self.err.setText("יש למלא את כל המידות במספרים גדולים מאפס")
                fld.setFocus()
                return
            out[k] = v
        if out["shape"] == "square":
            out["l"] = out["w"]
            if "h" in out:
                out["h"] = out["w"]
        self.result_dims = out
        QSettings("Tiktin", "TiktinPDF").setValue(f"hole_{self.kind}", out)
        self.accept()
