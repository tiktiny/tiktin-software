# חלון סיבוב עמודים (Ctrl+R): אילו עמודים, איזו פעולה, ולאיזה כיוון
from PySide6.QtCore import Qt, QSettings


def deg(n):
    """מספר מעלות שמוצג נכון בתוך טקסט עברי (בלי שהסימן ° יקפוץ לצד השני)."""
    return "\u202a" + f"{n}°" + "\u202c"

from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel,
                               QPushButton, QButtonGroup, QWidget)

ACTIONS = [("rot90", "סיבוב " + deg(90)), ("portrait", "לאורך"), ("landscape", "לרוחב"),
           ("upright", "טקסט ישר"), ("flip", "היפוך " + deg(180))]

HINTS = {
    "rot90": "מסובב כל עמוד ב־90 מעלות לכיוון שנבחר.",
    "portrait": "כל עמוד יהיה לאורך, והטקסט בו לא יהיה הפוך.",
    "landscape": "כל עמוד יהיה לרוחב, והטקסט בו לא יהיה הפוך.",
    "upright": "כל עמוד מסובב כך שרוב הטקסט בו ישר וקריא. עמוד בלי טקסט (סריקה) לא זז.",
    "flip": "הופך כל עמוד ב־180 מעלות – לשרטוט שנפתח הפוך.",
}


class RotateDialog(QDialog):
    def __init__(self, parent, n_pages, cur_page):
        super().__init__(parent)
        self.setWindowTitle("סיבוב עמודים")
        self.setLayoutDirection(Qt.RightToLeft)
        st = QSettings("Tiktin", "TiktinPDF")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 18, 20, 18)
        lay.setSpacing(14)
        grid = QGridLayout()
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(12)
        lay.addLayout(grid)

        def seg_row(r, title, items, saved):
            grp = QButtonGroup(self)
            w = QWidget()
            h = QHBoxLayout(w)
            h.setContentsMargins(0, 0, 0, 0)
            h.setSpacing(0)
            for i, (key, text) in enumerate(items):
                b = QPushButton(text)
                b.setObjectName("seg")
                b.setCheckable(True)
                b.setProperty("key", key)
                b.setMinimumWidth(96)
                grp.addButton(b, i)
                h.addWidget(b)
            h.addStretch(1)
            keys = [k for k, _ in items]
            grp.button(keys.index(saved) if saved in keys else 0).setChecked(True)
            grid.addWidget(QLabel(title), r, 0)
            grid.addWidget(w, r, 1)
            return grp

        self.scope = seg_row(0, "עמודים", [("page", f"העמוד הנוכחי ({cur_page + 1})"),
                                           ("all", f"כל העמודים ({n_pages})")],
                             st.value("rot_scope", "page"))
        self.action = seg_row(1, "פעולה", ACTIONS, st.value("rot_action", "rot90"))
        self.direction = seg_row(2, "כיוון", [("cw", "↻  עם כיוון השעון"), ("ccw", "↺  נגד כיוון השעון")],
                                 st.value("rot_dir", "cw"))
        self.hint = QLabel("")
        self.hint.setStyleSheet("color: #5c6367;")
        self.hint.setWordWrap(True)
        grid.addWidget(self.hint, 3, 1)
        grid.setColumnStretch(1, 1)

        btns = QHBoxLayout()
        btns.addStretch(1)
        cancel = QPushButton("ביטול")
        cancel.setObjectName("plainBtn")
        ok = QPushButton("סיבוב")
        ok.setObjectName("primaryBtn")
        ok.setDefault(True)
        btns.addWidget(cancel)
        btns.addWidget(ok)
        lay.addLayout(btns)
        cancel.clicked.connect(self.reject)
        ok.clicked.connect(self._ok)
        self.action.buttonToggled.connect(self._refresh)
        self._refresh()

    @staticmethod
    def _key(grp):
        return grp.checkedButton().property("key")

    def _refresh(self, *_):
        a = self._key(self.action)
        # הכיוון קובע בסיבוב 90°, ובלאורך / לרוחב רק לעמודים בלי טקסט
        on = a in ("rot90", "portrait", "landscape")
        for b in self.direction.buttons():
            b.setEnabled(on)
        extra = " הכיוון שנבחר משמש רק לעמודים בלי טקסט." if a in ("portrait", "landscape") else ""
        self.hint.setText(HINTS[a] + extra)

    def _ok(self):
        self.result_scope = self._key(self.scope)
        self.result_action = self._key(self.action)
        self.result_dir = self._key(self.direction)
        st = QSettings("Tiktin", "TiktinPDF")
        st.setValue("rot_scope", self.result_scope)
        st.setValue("rot_action", self.result_action)
        st.setValue("rot_dir", self.result_dir)
        self.accept()
