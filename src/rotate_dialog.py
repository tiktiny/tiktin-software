# חלון סיבוב עמודים: עמוד נוכחי או כל העמודים, עם/נגד כיוון השעון, או מצב סופי לאורך/לרוחב
from PySide6.QtCore import Qt, QSettings
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QButtonGroup, QWidget)


class RotateDialog(QDialog):
    def __init__(self, parent, n_pages, cur_page):
        super().__init__(parent)
        self.setWindowTitle("סיבוב עמודים")
        self.setLayoutDirection(Qt.RightToLeft)
        st = QSettings("Tiktin", "TiktinPDF")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 18, 20, 18)
        lay.setSpacing(14)
        self.groups = {}

        def seg(key, label, opts, cur):
            row = QHBoxLayout()
            lab = QLabel(label)
            lab.setMinimumWidth(80)
            row.addWidget(lab)
            box = QWidget()
            h = QHBoxLayout(box)
            h.setContentsMargins(0, 0, 0, 0)
            h.setSpacing(0)
            grp = QButtonGroup(self)
            for k, (val, text, tip) in enumerate(opts):
                b = QPushButton(text)
                b.setObjectName("seg")
                b.setCheckable(True)
                b.setProperty("key", val)
                b.setToolTip(tip)
                b.setMinimumWidth(90)
                grp.addButton(b, k)
                h.addWidget(b)
                if val == cur:
                    b.setChecked(True)
            if grp.checkedButton() is None:
                grp.buttons()[0].setChecked(True)
            row.addWidget(box)
            row.addStretch(1)
            lay.addLayout(row)
            self.groups[key] = grp
            return grp

        seg("scope", "עמודים", [("page", f"העמוד הנוכחי ({cur_page})", "רק העמוד שמוצג עכשיו"),
                                ("all", f"כל העמודים ({n_pages})", "כל העמודים בקובץ")],
            st.value("rot_scope", "page"))
        seg("mode", "פעולה", [("rot", "סיבוב 90°", "מסובב רבע סיבוב בכיוון שנבחר"),
                              ("portrait", "לאורך", "העמוד יעמוד לאורך, והטקסט בשרטוט ישר וקריא"),
                              ("landscape", "לרוחב", "העמוד יעמוד לרוחב, והטקסט בשרטוט ישר וקריא"),
                              ("upright", "טקסט ישר", "מסובב כל עמוד כך שהטקסט בו יעמוד ישר וקריא"),
                              ("180", "היפוך 180°", "הופך עמוד שעומד הפוך")],
            st.value("rot_mode", "rot"))
        seg("dir", "כיוון", [("cw", "↻ עם כיוון השעון", "סיבוב ימינה"),
                             ("ccw", "↺ נגד כיוון השעון", "סיבוב שמאלה")],
            st.value("rot_dir", "cw"))
        if n_pages < 2:
            self.groups["scope"].buttons()[1].setEnabled(False)
            self.groups["scope"].buttons()[0].setChecked(True)
        tip = QLabel("לאורך, לרוחב וטקסט ישר: התוכנה בודקת את הטקסט בכל עמוד ומסובבת כך שהוא לא יהיה הפוך. "
                     "בעמודים בלי טקסט (למשל סריקה) אי אפשר לזהות מה ישר — התוכנה תודיע על כך.\n"
                     "הסימונים מסתובבים יחד עם השרטוט. הקובץ עצמו משתנה רק ב\"שמירת שינויים\", ו־UNDO מחזיר.")
        tip.setWordWrap(True)
        tip.setStyleSheet("color:#5b6470;")
        tip.setAlignment(Qt.AlignAbsolute | Qt.AlignRight)
        lay.addWidget(tip)
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

    def _ok(self):
        g = {k: v.checkedButton().property("key") for k, v in self.groups.items()}
        st = QSettings("Tiktin", "TiktinPDF")
        st.setValue("rot_scope", g["scope"])
        st.setValue("rot_mode", g["mode"])
        st.setValue("rot_dir", g["dir"])
        self.scope, self.mode, self.cw = g["scope"], g["mode"], g["dir"] == "cw"
        self.accept()
