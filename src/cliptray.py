# מגש העתקות: עד שני חלונות שנקלטו מהשרטוט, עם תמונה קטנה של מה שנקלט.
# כל חלון נשמר כ-PDF וקטורי (בלי איבוד רזולציה) וגם כתמונה ברזולוציה גבוהה.
import os
from PySide6.QtCore import Qt, Signal, QMimeData, QUrl, QTimer, QPoint
from PySide6.QtGui import QPixmap, QDrag
from PySide6.QtWidgets import (QWidget, QHBoxLayout, QVBoxLayout, QLabel, QToolButton, QMenu,
                               QApplication, QFileDialog, QFrame)

MAX_CLIPS = 2
THUMB_W, THUMB_H = 150, 104


def image_mime(img):
    """הקטע כתמונה בלבד — בפורמטים שמייל (אאוטלוק, ג'ימייל בדפדפן), וורד ווואטסאפ מקבלים.
    בלי קובץ ובלי HTML לצידה, כדי שהתוכנה שמדביקים בה לא תבחר בהם במקום בתמונה."""
    from PySide6.QtCore import QBuffer, QByteArray, QIODevice
    md = QMimeData()
    md.setImageData(img)                       # ‏DIB — אאוטלוק, וורד, פיינט
    ba = QByteArray()
    buf = QBuffer(ba)
    buf.open(QIODevice.WriteOnly)
    img.save(buf, "PNG")
    buf.close()
    md.setData("image/png", ba)                # ‏PNG — דפדפנים (ג'ימייל), וואטסאפ
    md.setData('application/x-qt-windows-mime;value="PNG"', ba)   # אותו PNG בשם שחלונות מכיר
    return md


def file_mime(path):
    """הקטע כקובץ PDF בלבד (בלי תמונה לצידו), כך שבהדבקה או בגרירה עובר בדיוק הקובץ הזה."""
    md = QMimeData()
    md.setUrls([QUrl.fromLocalFile(path)])
    md.setData('application/x-qt-windows-mime;value="Preferred DropEffect"', b"\x01\x00\x00\x00")   # העתקה, לא העברה
    return md


class ClipItem(QFrame):
    removed = Signal(object)
    copied = Signal(str)

    def __init__(self, parent, clip):
        super().__init__(parent)
        self.clip = clip              # {"pdf": path, "img": QImage, "name": str}
        self.setObjectName("clip")
        self.setFixedSize(THUMB_W + 12, THUMB_H + 34)
        self.setCursor(Qt.OpenHandCursor)
        self.setToolTip("לחיצה: העתקה כתמונה — מדביקים (Ctrl+V) בגוף המייל, בוורד או בוואטסאפ.\n"
                        "גרירה: הקטע עובר כקובץ PDF — לתיקייה או כקובץ מצורף למייל.\n"
                        "לחצן ימני: העתקה כקובץ PDF, שמירה ועוד")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(5, 4, 5, 4)
        lay.setSpacing(2)
        top = QHBoxLayout()
        top.setContentsMargins(0, 0, 0, 0)
        self.title = QLabel(clip["label"])
        self.title.setObjectName("clipTitle")
        top.addWidget(self.title, 1)
        x = QToolButton()
        x.setText("✕")
        x.setObjectName("clipX")
        x.setToolTip("הסרה מהמגש")
        x.clicked.connect(lambda: self.removed.emit(self))
        top.addWidget(x)
        lay.addLayout(top)
        self.pic = QLabel()
        self.pic.setAlignment(Qt.AlignCenter)
        pm = QPixmap.fromImage(clip["img"]).scaled(THUMB_W, THUMB_H - 8, Qt.KeepAspectRatio,
                                                    Qt.SmoothTransformation)
        self.pic.setPixmap(pm)
        lay.addWidget(self.pic, 1)
        self._press = None
        self._flash = 0
        self._timer = QTimer(self, interval=220)
        self._timer.timeout.connect(self._tick)

    def flash(self):
        self._flash = 6
        self._timer.start()
        self._tick()

    def _tick(self):
        self.setProperty("fresh", self._flash % 2 == 0 and self._flash > 0)
        self.style().unpolish(self)
        self.style().polish(self)
        if self._flash > 0:
            self._flash -= 1
        else:
            self._timer.stop()

    # ----- copy / drag
    def copy_image(self):
        QApplication.clipboard().setMimeData(image_mime(self.clip["img"]))
        self.copied.emit("הקטע הועתק כתמונה — מדביקים (Ctrl+V) בגוף המייל, בוורד או בוואטסאפ")

    def copy_pdf(self):
        if not os.path.exists(self.clip["pdf"]):
            self.copied.emit("קובץ הקטע כבר לא קיים — קולטים את האזור מחדש")
            return
        QApplication.clipboard().setMimeData(file_mime(self.clip["pdf"]))
        self.copied.emit("הקטע הועתק כקובץ PDF (" + os.path.basename(self.clip["pdf"]) +
                         ") — מדביקים (Ctrl+V) בתיקייה או כקובץ מצורף במייל")

    def save_pdf(self):
        path, _ = QFileDialog.getSaveFileName(self, "שמירת הקטע כ-PDF", self.clip["name"], "קובצי PDF (*.pdf)")
        if path:
            with open(self.clip["pdf"], "rb") as f, open(path, "wb") as g:
                g.write(f.read())
            self.copied.emit(f"נשמר: {os.path.basename(path)}")

    def mousePressEvent(self, ev):
        if ev.button() == Qt.LeftButton:
            self._press = ev.position().toPoint()

    def mouseMoveEvent(self, ev):
        if self._press is None or not (ev.buttons() & Qt.LeftButton):
            return
        if (ev.position().toPoint() - self._press).manhattanLength() < 8:
            return
        self._press = None
        drag = QDrag(self)
        drag.setMimeData(file_mime(self.clip["pdf"]))
        drag.setPixmap(self.pic.pixmap())
        drag.setHotSpot(QPoint(20, 20))
        drag.exec(Qt.CopyAction)

    def mouseReleaseEvent(self, ev):
        if self._press is not None and ev.button() == Qt.LeftButton:
            self.copy_image()
        self._press = None

    def contextMenuEvent(self, ev):
        m = QMenu(self)
        m.setLayoutDirection(Qt.RightToLeft)
        m.addAction("העתקה כתמונה (להדבקה בגוף המייל, בוורד ובוואטסאפ)").triggered.connect(self.copy_image)
        m.addAction("העתקה כקובץ PDF (לצירוף למייל או לתיקייה)").triggered.connect(self.copy_pdf)
        m.addAction("שמירה כ-PDF...").triggered.connect(self.save_pdf)
        m.addSeparator()
        m.addAction("הסרה מהמגש").triggered.connect(lambda: self.removed.emit(self))
        m.exec(ev.globalPos())


class ClipTray(QWidget):
    """מגש צף בפינת השרטוט."""
    message = Signal(str)

    def __init__(self, parent):
        super().__init__(parent)
        self.setObjectName("tray")
        self.setLayoutDirection(Qt.RightToLeft)
        self.lay = QHBoxLayout(self)
        self.lay.setContentsMargins(6, 6, 6, 6)
        self.lay.setSpacing(6)
        self.items = []
        self.hide()

    def add(self, clip):
        if len(self.items) >= MAX_CLIPS:
            self._remove(self.items[0])
        it = ClipItem(self, clip)
        it.removed.connect(self._remove)
        it.copied.connect(self.message)
        self.items.append(it)
        self.lay.addWidget(it)
        self._place()
        self.show()
        self.raise_()
        it.flash()

    def _remove(self, it):
        if it in self.items:
            self.items.remove(it)
            it.hide()
            it.deleteLater()
            # הקובץ לא נמחק כאן — אולי הוא עדיין בלוח ההעתקה; קבצים ישנים נמחקים בהפעלה הבאה
        if not self.items:
            self.hide()
        else:
            self._place()

    def _place(self):
        self.adjustSize()
        p = self.parentWidget()
        if p is not None:
            # פינה שמאלית-תחתונה של אזור השרטוט
            self.move(12, p.height() - self.sizeHint().height() - 26)



TRAY_STYLE = """
QWidget#tray { background: rgba(255,255,255,235); border: 1px solid #cfd4db; border-radius: 6px; }
QFrame#clip { background: #ffffff; border: 1px solid #cfd4db; border-radius: 4px; }
QFrame#clip[fresh="true"] { border: 2px solid #1a7f37; }
QFrame#clip:hover { border-color: #c8202f; }
QLabel#clipTitle { color: #1a7f37; font-size: 8.5pt; }
QToolButton#clipX { border: none; color: #7a828e; font-size: 9pt; padding: 0 2px; }
QToolButton#clipX:hover { color: #c8202f; }
"""
