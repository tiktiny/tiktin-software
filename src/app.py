import os
import sys
import math
import base64
import multiprocessing as mp
from multiprocessing.connection import wait
from collections import OrderedDict

import pymupdf
from PySide6.QtCore import (Qt, QTimer, QThread, Signal, QObject, QRectF,
                            QPointF, QSettings, QSize, QEvent)
from PySide6.QtGui import (QPainter, QImage, QPixmap, QColor, QIcon, QKeySequence, QTextCursor,
                           QShortcut, QPalette, QCursor, QFont)
from PySide6.QtWidgets import (QApplication, QMainWindow, QAbstractScrollArea, QHBoxLayout,
                               QToolBar, QToolButton, QLabel, QLineEdit, QComboBox,
                               QFileDialog, QMessageBox, QInputDialog, QWidget,
                               QSizePolicy, QDialog, QMenu, QProgressDialog)

from render_worker import worker_main
from version import VERSION, BUILD_DATE, LOGO_B64
try:
    from version import ICON_B64
except ImportError:
    ICON_B64 = None
from text_dialog import HebrewKeyboard
from inline_text import InlineText
from colors import ColorButton
import annotations as A
from annotations_extra import EXTRA, SHAPE_NAMES, MARK_NAMES
import annotations_extra as AX
import stamps
from scale_detect import analyzer_main
from cliptray import ClipTray, TRAY_STYLE
import marks_store
from ribbon import RibbonButton, RIBBON_STYLE

APP_NAME = "טיקטין PDF A"
TILE = 512                 # גודל אריח בפיקסלים של המסך
MARGIN = 16                # שוליים סביב העמודים
GAP = 12                   # רווח בין עמודים
CACHE_BYTES = 700 * 2**20  # תקרת זיכרון לאריחים מוכנים
MIN_ZOOM, MAX_ZOOM = 0.02, 64.0
CANVAS_BG = QColor("#d9dde3")
ACCENT = "#c8202f"


# ---------------------------------------------------------------- rendering pool
class _Listener(QThread):
    got = Signal(object)

    def __init__(self, conns):
        super().__init__()
        self.conns = list(conns)
        self.running = True

    def run(self):
        while self.running and self.conns:
            for c in wait(self.conns, timeout=0.25):
                try:
                    self.got.emit(c.recv())
                except (EOFError, OSError):
                    self.conns.remove(c)


class RenderPool(QObject):
    """מחלק עבודות רינדור לתהליכים מקבילים, תמיד לפי סדר העדיפות העדכני."""
    tile_ready = Signal(object, object, int, int)   # key, QPixmap, px, py

    def __init__(self, n, autostart=True):
        super().__init__()
        self.procs, self.job_conns, res_conns = [], [], []
        self._ctx = mp.get_context("spawn")
        self._child_ends = []     # (jr, rw) של תהליכים שעוד לא הופעלו
        for i in range(n):
            jr, jw = self._ctx.Pipe(duplex=False)
            rr, rw = self._ctx.Pipe(duplex=False)
            self._child_ends.append((jr, rw))
            self.job_conns.append(jw)
            res_conns.append(rr)
        self._started = 0
        self._spawning = False
        self.idle = set()
        self.inflight = {}        # wid -> jobid
        self.jobs = {}            # jobid -> job
        self.wanted = []          # ordered list of jobs
        self.next_id = 1
        self.listener = _Listener(res_conns)
        self.listener.got.connect(self._on_msg)
        self.listener.start()
        if autostart:
            self.start()

    def start(self):
        """עלייה מהירה: מפעילים תהליך רינדור אחד, ואת השאר רק כשהוא מוכן —
        כך החלון עולה בלי שכל התהליכים יתחרו על הדיסק באותו רגע."""
        if self._started == 0:
            self._spawn(1)

    def _spawn(self, upto):
        while self._started < min(upto, len(self._child_ends)):
            i = self._started
            jr, rw = self._child_ends[i]
            p = self._ctx.Process(target=worker_main, args=(jr, rw, i), daemon=True)
            p.start()
            self.procs.append(p)
            self._started += 1

    @property
    def ready_count(self):
        return len(self.idle) + len(self.inflight)

    def set_wanted(self, jobs):
        self.wanted = jobs
        self._dispatch()

    def _busy_keys(self):
        return {self.jobs[j]["key"] for j in self.inflight.values() if j in self.jobs}

    def _dispatch(self):
        if not self.idle or not self.wanted:
            return
        busy = self._busy_keys()
        rest = []
        for job in self.wanted:
            if job["key"] in busy:
                continue
            if not self.idle:
                rest.append(job)
                continue
            wid = self.idle.pop()
            jid = self.next_id
            self.next_id += 1
            self.jobs[jid] = job
            self.inflight[wid] = jid
            busy.add(job["key"])
            self.job_conns[wid].send((jid, job["path"], job["pw"], job["pno"],
                                      job["scale"], job["clip"], job["aa"]))
        self.wanted = rest

    def _on_msg(self, msg):
        kind, wid = msg[0], msg[1]
        if kind == "ready":
            self.idle.add(wid)
            self._dispatch()
            if self._started < len(self._child_ends) and not self._spawning:
                # הראשון מוכן — מפעילים את כל השאר ברקע, בלי לעצור את הממשק ואת הציור
                self._spawning = True
                import threading
                threading.Thread(target=self._spawn, args=(len(self._child_ends),), daemon=True).start()
            return
        jid = msg[2]
        self.inflight.pop(wid, None)
        self.idle.add(wid)
        job = self.jobs.pop(jid, None)
        if kind == "ok" and job is not None:
            _, _, _, px, py, w, h, stride, samples = msg
            img = QImage(samples, w, h, stride, QImage.Format_RGB888)
            pm = QPixmap.fromImage(img)
            self.tile_ready.emit(job["key"], pm, px, py)
        self._dispatch()

    def close_docs(self):
        """משחרר את הקובץ בכל תהליכי הרינדור (נדרש לפני דריסה ב-Windows)."""
        self.wanted = []
        for c in self.job_conns:
            try:
                c.send("close")
            except Exception:
                pass

    def shutdown(self):
        self.listener.running = False
        self.listener.wait(700)
        for c in self.job_conns:
            try:
                c.send(None)
            except Exception:
                pass
        for p in self.procs:
            p.join(0.3)
            if p.is_alive():
                p.terminate()


class ScaleAnalyzer(QObject):
    """תהליך רקע אחד שמזהה ומאמת קנה מידה. מופעל רק אחרי שהשרטוט כבר מוצג."""
    result = Signal(int, int, object)     # docgen, עמוד, תוצאה

    def __init__(self):
        super().__init__()
        self.proc = None
        self.timer = QTimer(self, interval=120)
        self.timer.timeout.connect(self._poll)
        self.pending = 0

    def _start(self):
        ctx = mp.get_context("spawn")
        jr, self.jw = ctx.Pipe(duplex=False)
        self.rr, rw = ctx.Pipe(duplex=False)
        self.proc = ctx.Process(target=analyzer_main, args=(jr, rw), daemon=True)
        self.proc.start()

    def request(self, gen, path, pw, pno):
        try:
            if self.proc is None:
                self._start()
            self.jw.send((gen, path, pw, pno))
            self.pending += 1
            self.timer.start()
        except Exception:
            pass

    def close_doc(self):
        if self.proc is not None:
            try:
                self.jw.send("close")
            except Exception:
                pass

    def _poll(self):
        try:
            while self.rr.poll():
                gen, pno, res = self.rr.recv()
                self.pending -= 1
                self.result.emit(gen, pno, res)
        except (EOFError, OSError):
            self.pending = 0
        if self.pending <= 0:
            self.timer.stop()

    def shutdown(self):
        if self.proc is not None:
            try:
                self.jw.send(None)
            except Exception:
                pass
            self.proc.join(0.3)
            if self.proc.is_alive():
                self.proc.terminate()


# ---------------------------------------------------------------- viewer widget
class PdfView(QAbstractScrollArea):
    page_changed = Signal(int, int)
    zoom_changed = Signal(float)
    region_selected = Signal(int, object)   # עמוד, מלבן בנקודות
    select_cancelled = Signal()
    tool_changed = Signal(str)
    changed = Signal()
    status = Signal(str)
    scale_changed = Signal(float)

    def __init__(self, pool):
        super().__init__()
        self.pool = pool
        pool.tile_ready.connect(self._on_tile)
        self.setLayoutDirection(Qt.LeftToRight)
        self.viewport().setMouseTracking(True)
        self.setFrameShape(QAbstractScrollArea.NoFrame)
        self.setFocusPolicy(Qt.StrongFocus)
        self.doc = None
        self.path = None
        self.pw = None
        self.docgen = 0
        self.sizes = []
        self.cum = [0.0]
        self.maxw = 0.0
        self.zoom = 1.0
        self.tscale = 1.0           # קנה המידה שבו מבקשים אריחים חדים
        self.tiles = OrderedDict()  # key -> (pixmap, px, py, nbytes)
        self.by_page = {}           # pno -> set(keys)
        self.previews = {}          # pno -> (pixmap, scale)
        self.cache_bytes = 0
        self.wheel_zoom = False
        self._drag = None
        self._cur_page = -1
        self.select_mode = False
        self._sel = None            # (נקודת התחלה, נקודה נוכחית) בקואורדינטות תוכן
        self.items = {}             # עמוד -> רשימת סימונים
        self.scales = {}            # עמוד -> קנ"מ (50 = 1:50)
        self.default_scale = QSettings("Tiktin", "TiktinPDF").value("default_scale", 50.0, type=float)
        self.tool = "pan"
        self.template = None
        self.hole_kind = None
        self.ghost = None
        self.dim_start = None
        self.calib = None
        self.selected = None
        self._move = None
        self.undo = []
        self.redo = []
        self.src = None             # הקובץ שממנו קוראים בפועל (אחרי מחיקת עמודים: עותק זמני)
        self.pages_changed = False
        self.dirty = False
        self.overlay_version = 0
        self._resize = None
        self.select_purpose = "print"
        st = QSettings("Tiktin", "TiktinPDF")
        self.pen_color = st.value("pen_color", "#d0021b")
        if QColor(self.pen_color).name() not in ("#d0021b", "#000000"):
            self.pen_color = "#d0021b"
        self.pen_w = st.value("pen_w", 0.5, type=float)      # עובי עט במ"מ על הנייר
        self._stroke = None
        self.text_size = st.value("text_size", 3.5, type=float)
        self.editor = None          # עורך טקסט פתוח על השרטוט
        self.editing = None         # (עמוד, אינדקס) של הטקסט שנערך
        self._kb = HebrewKeyboard()
        self._erasing = False
        self._cursor_pt = None
        self.auto_scales = {}        # עמוד -> קנ"מ שזוהה אוטומטית
        self.scale_info = {}         # עמוד -> תוצאת הניתוח
        self.analyzer = ScaleAnalyzer()
        self.analyzer.result.connect(self._on_analysis)
        self._asked = set()
        self.analyze_timer = QTimer(self, singleShot=True, interval=600)
        self.analyze_timer.timeout.connect(self._request_analysis)
        self.shape_start = None
        self.stamp_job = None
        self.erase_rect = None       # (עמוד, מלבן) של מחיקת אזור שעוד לא אושרה
        self._seg_cache = {}         # עמוד -> קטעי קווים לחיפוש "פריט בודד" (נבנה רק בשימוש)
        self._ink_cache = {}         # (מסמך, עמוד) -> מפת דיו למציאת מקום פנוי לחותמת
        self._stamp_clean = True
        self._erase_drag = None
        self._last_erase = None
        self.zoom_timer = QTimer(self, singleShot=True, interval=140)
        self.zoom_timer.timeout.connect(self._settle_zoom)
        self.sched_timer = QTimer(self, singleShot=True, interval=0)
        self.sched_timer.timeout.connect(self._schedule)
        self.verticalScrollBar().valueChanged.connect(self._scrolled)
        self.horizontalScrollBar().valueChanged.connect(self._scrolled)
        self.verticalScrollBar().setSingleStep(40)
        self.horizontalScrollBar().setSingleStep(40)

    # ----- document
    def open_doc(self, doc, path, pw, src=None):
        self.doc = doc
        self.path = path
        self.src = src or path
        self.pw = pw
        self.docgen += 1
        self.sizes = [(r.width, r.height) for r in (doc[i].rect for i in range(doc.page_count))]
        self.cum = [0.0]
        for _, h in self.sizes:
            self.cum.append(self.cum[-1] + h)
        self.maxw = max((w for w, _ in self.sizes), default=1)
        self.tiles.clear()
        self.by_page.clear()
        self.previews.clear()
        self.items = {}
        self.undo = []
        self.redo = []
        self.dirty = False
        self.pages_changed = False
        self.selected = None
        if src is None or src == path:
            self._seg_cache = {}
        self._load_scales()
        self.auto_scales = {}
        self.scale_info = {}
        self._asked = set()
        self.analyzer.close_doc()
        self.set_tool("pan")
        self.cache_bytes = 0
        self._cur_page = -1
        w0, h0 = self.sizes[0]
        # שרטוטים (עמוד לרוחב או גדול) נפתחים בהתאמה לעמוד, מסמכים בהתאמה לרוחב
        if w0 > h0 or max(w0, h0) > 1300:
            self.fit_page(instant=True)
        else:
            self.fit_width(instant=True)
        self.verticalScrollBar().setValue(0)
        self.horizontalScrollBar().setValue(
            (self.horizontalScrollBar().maximum()) // 2)
        if self.pool.ready_count == 0:
            self._inline_preview(0)
        self.viewport().update()
        self._cur_page = -1
        self._scrolled()
        self._schedule()

    def _inline_preview(self, pno):
        """תצוגה ראשונה מיידית בזמן שתהליכי הרינדור עדיין עולים."""
        try:
            w, h = self.sizes[pno]
            s = min(self.zoom * self._dpr(), 900.0 / max(w, h))
            pymupdf.TOOLS.set_aa_level(2)
            pix = self.doc[pno].get_pixmap(matrix=pymupdf.Matrix(s, s), alpha=False)
            img = QImage(pix.samples, pix.width, pix.height, pix.stride, QImage.Format_RGB888)
            self.previews[pno] = (QPixmap.fromImage(img), s)
        except Exception:
            pass

    # ----- geometry
    def _dpr(self):
        return self.viewport().devicePixelRatioF()

    def _snap(self, v):
        d = self._dpr()
        return round(v * d) / d

    def content_size(self, z=None):
        z = self.zoom if z is None else z
        n = len(self.sizes)
        cw = max(self.maxw * z + 2 * MARGIN, self.viewport().width())
        ch = 2 * MARGIN + self.cum[-1] * z + max(0, n - 1) * GAP
        return cw, ch

    def page_rect(self, i, z=None):
        z = self.zoom if z is None else z
        cw, _ = self.content_size(z)
        w, h = self.sizes[i]
        x = self._snap((cw - w * z) / 2)
        y = self._snap(MARGIN + self.cum[i] * z + i * GAP)
        return QRectF(x, y, w * z, h * z)

    def page_at(self, cy, z=None):
        z = self.zoom if z is None else z
        if not self.sizes:
            return 0
        lo, hi = 0, len(self.sizes) - 1
        while lo < hi:
            mid = (lo + hi + 1) // 2
            if MARGIN + self.cum[mid] * z + mid * GAP <= cy:
                lo = mid
            else:
                hi = mid - 1
        return lo

    def _update_scrollbars(self):
        cw, ch = self.content_size()
        vw, vh = self.viewport().width(), self.viewport().height()
        hs, vs = self.horizontalScrollBar(), self.verticalScrollBar()
        hs.setRange(0, max(0, int(math.ceil(cw - vw))))
        vs.setRange(0, max(0, int(math.ceil(ch - vh))))
        hs.setPageStep(vw)
        vs.setPageStep(vh)

    def visible_pages(self):
        if not self.sizes:
            return []
        v = self.verticalScrollBar().value()
        vh = self.viewport().height()
        first = self.page_at(v)
        out = []
        for i in range(first, len(self.sizes)):
            r = self.page_rect(i)
            if r.top() > v + vh:
                break
            out.append(i)
        return out

    # ----- zoom
    def set_zoom(self, z, anchor=None):
        if not self.sizes:
            return
        z = max(MIN_ZOOM, min(MAX_ZOOM, z))
        if abs(z - self.zoom) < 1e-9:
            return
        vw, vh = self.viewport().width(), self.viewport().height()
        ax, ay = (anchor.x(), anchor.y()) if anchor is not None else (vw / 2, vh / 2)
        hs, vs = self.horizontalScrollBar(), self.verticalScrollBar()
        cx, cy = hs.value() + ax, vs.value() + ay
        i = self.page_at(cy)
        r = self.page_rect(i)
        lx, ly = (cx - r.x()) / self.zoom, (cy - r.y()) / self.zoom
        self.zoom = z
        self._update_scrollbars()
        r2 = self.page_rect(i)
        hs.setValue(int(round(r2.x() + lx * z - ax)))
        vs.setValue(int(round(r2.y() + ly * z - ay)))
        self.zoom_changed.emit(z)
        self._place_editor()
        self.zoom_timer.start()
        self.viewport().update()

    def _settle_zoom(self):
        self.tscale = self.zoom * self._dpr()
        self._schedule()
        self.viewport().update()

    def _fit_zoom(self, page_mode):
        if not self.sizes:
            return None
        i = max(0, self._cur_page)
        w, h = self.sizes[i]
        vw = max(50, self.viewport().width() - 2 * MARGIN)
        vh = max(50, self.viewport().height() - 2 * MARGIN)
        return min(vw / w, vh / h) if page_mode else vw / w

    def fit_page(self, instant=False):
        z = self._fit_zoom(True)
        if z is None:
            return
        i = max(0, self._cur_page)
        self.set_zoom(z)
        r = self.page_rect(i)
        self.verticalScrollBar().setValue(int(r.y() - MARGIN))
        if instant:
            self._settle_zoom()

    def fit_width(self, instant=False):
        z = self._fit_zoom(False)
        if z is None:
            return
        self.set_zoom(z)
        if instant:
            self._settle_zoom()

    def page_clip(self, i, crect):
        """מלבן בקואורדינטות תוכן -> מלבן בנקודות PDF בתוך עמוד i."""
        r = self.page_rect(i)
        w, h = self.sizes[i]
        x0 = max(0.0, (crect.left() - r.x()) / self.zoom)
        y0 = max(0.0, (crect.top() - r.y()) / self.zoom)
        x1 = min(w, (crect.right() - r.x()) / self.zoom)
        y1 = min(h, (crect.bottom() - r.y()) / self.zoom)
        if x1 - x0 < 2 or y1 - y0 < 2:
            return None
        return pymupdf.Rect(x0, y0, x1, y1)

    def screen_clip(self):
        """החלק של העמוד הנוכחי שנראה כרגע בחלון."""
        if not self.sizes:
            return None
        hs, vs = self.horizontalScrollBar().value(), self.verticalScrollBar().value()
        vr = QRectF(hs, vs, self.viewport().width(), self.viewport().height())
        best, area = None, 0
        for i in self.visible_pages():
            c = self.page_clip(i, vr)
            if c is not None and c.width * c.height > area:
                best, area = (i, c), c.width * c.height
        return best

    def start_select(self, purpose="print"):
        self.select_purpose = purpose
        self.select_mode = True
        self._sel = None
        self.viewport().setCursor(Qt.CrossCursor)

    def cancel_select(self):
        self.select_mode = False
        self._sel = None
        self.viewport().setCursor(Qt.OpenHandCursor if self.sizes else Qt.ArrowCursor)
        self.viewport().update()

    def _content_pt(self, pos):
        return QPointF(pos.x() + self.horizontalScrollBar().value(),
                       pos.y() + self.verticalScrollBar().value())

    def go_page(self, i):
        if not self.sizes:
            return
        i = max(0, min(len(self.sizes) - 1, i))
        self.verticalScrollBar().setValue(int(self.page_rect(i).y() - MARGIN / 2))

    # ----- tile management
    def _put_tile(self, key, pm, px, py):
        if key in self.tiles:
            return
        nb = pm.width() * pm.height() * 4
        self.tiles[key] = (pm, px, py, nb)
        self.by_page.setdefault(key[1], set()).add(key)
        self.cache_bytes += nb
        while self.cache_bytes > CACHE_BYTES and self.tiles:
            k, (_, _, _, b) = self.tiles.popitem(last=False)
            self.cache_bytes -= b
            s = self.by_page.get(k[1])
            if s:
                s.discard(k)

    def _on_tile(self, key, pm, px, py):
        if key[0] != self.docgen:
            return
        if key[2] == "pv":
            self.previews[key[1]] = (pm, key[3])
        else:
            self._put_tile(key, pm, px, py)
        self.viewport().update()
        self.sched_timer.start()

    def _skey(self, s):
        return round(s, 5)

    def _needed_tiles(self, i, s, extra=0):
        """אריחים שמכסים את החלק הנראה של עמוד i בקנה מידה s."""
        r = self.page_rect(i)
        hs, vs = self.horizontalScrollBar().value(), self.verticalScrollBar().value()
        vw, vh = self.viewport().width(), self.viewport().height()
        k = s / self.zoom                      # פיקסלים לכל יחידה לוגית
        x0 = max(0.0, hs - r.x()) * k
        y0 = max(0.0, vs - r.y()) * k
        x1 = min(r.width(), hs + vw - r.x()) * k
        y1 = min(r.height(), vs + vh - r.y()) * k
        if x1 <= x0 or y1 <= y0:
            return []
        w, h = self.sizes[i]
        maxtx = max(0, int(math.ceil(w * s / TILE)) - 1)
        maxty = max(0, int(math.ceil(h * s / TILE)) - 1)
        tx0 = max(0, int(x0 // TILE) - extra)
        ty0 = max(0, int(y0 // TILE) - extra)
        tx1 = min(maxtx, int((x1 - 1) // TILE) + extra)
        ty1 = min(maxty, int((y1 - 1) // TILE) + extra)
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        out = []
        for ty in range(ty0, ty1 + 1):
            for tx in range(tx0, tx1 + 1):
                d = (tx * TILE + TILE / 2 - cx) ** 2 + (ty * TILE + TILE / 2 - cy) ** 2
                out.append((d, tx, ty))
        out.sort()
        return [(tx, ty) for _, tx, ty in out]

    def _tile_job(self, i, s, tx, ty):
        w, h = self.sizes[i]
        clip = (tx * TILE / s, ty * TILE / s,
                min(w, (tx + 1) * TILE / s), min(h, (ty + 1) * TILE / s))
        return {"key": (self.docgen, i, self._skey(s), tx, ty), "path": self.src,
                "pw": self.pw, "pno": i, "scale": s, "clip": clip, "aa": 8}

    def _preview_job(self, i):
        w, h = self.sizes[i]
        s = min(1.5, 700.0 / max(w, h))
        return {"key": (self.docgen, i, "pv", s), "path": self.src, "pw": self.pw,
                "pno": i, "scale": s, "clip": (0, 0, w, h), "aa": 2}

    def _schedule(self):
        if not self.sizes:
            self.pool.set_wanted([])
            return
        s = self.tscale
        sk = self._skey(s)
        vis = self.visible_pages()
        jobs_pv, jobs_vis, jobs_more = [], [], []
        for i in vis:
            if i not in self.previews:
                jobs_pv.append(self._preview_job(i))
            for tx, ty in self._needed_tiles(i, s):
                if (self.docgen, i, sk, tx, ty) not in self.tiles:
                    jobs_vis.append(self._tile_job(i, s, tx, ty))
        for i in vis:
            for tx, ty in self._needed_tiles(i, s, extra=1):
                if (self.docgen, i, sk, tx, ty) not in self.tiles:
                    jobs_more.append(self._tile_job(i, s, tx, ty))
        if vis:
            for i in (vis[-1] + 1, vis[-1] + 2, vis[0] - 1):
                if 0 <= i < len(self.sizes) and i not in self.previews:
                    jobs_more.append(self._preview_job(i))
        seen, jobs = set(), []
        for j in jobs_pv + jobs_vis + jobs_more:
            if j["key"] not in seen:
                seen.add(j["key"])
                jobs.append(j)
        self.pool.set_wanted(jobs)

    # ----- painting
    def paintEvent(self, ev):
        p = QPainter(self.viewport())
        p.fillRect(self.viewport().rect(), CANVAS_BG)
        if not self.sizes:
            p.setPen(QColor("#5a6270"))
            f = p.font()
            f.setPointSize(13)
            p.setFont(f)
            p.drawText(self.viewport().rect(), Qt.AlignCenter,
                       "גררו קובץ PDF לכאן, או לחצו על ״פתיחה״")
            return
        hs, vs = self.horizontalScrollBar().value(), self.verticalScrollBar().value()
        p.translate(-hs, -vs)
        cur_s = self.zoom * self._dpr()
        sk = self._skey(self.tscale)
        exact = abs(self.tscale - cur_s) < 1e-6
        for i in self.visible_pages():
            r = self.page_rect(i)
            p.fillRect(r.adjusted(1, 1, 3, 3), QColor(0, 0, 0, 40))
            p.fillRect(r, Qt.white)
            needed = [(self.docgen, i, sk, tx, ty) for tx, ty in self._needed_tiles(i, self.tscale)]
            complete = exact and needed and all(k in self.tiles for k in needed)
            p.save()
            p.setClipRect(r)
            if not complete:
                p.setRenderHint(QPainter.SmoothPixmapTransform, True)
                pv = self.previews.get(i)
                if pv:
                    p.drawPixmap(r, pv[0], QRectF(pv[0].rect()))
                others = [k for k in self.by_page.get(i, ()) if k[0] == self.docgen and k[2] != sk]
                others.sort(key=lambda k: -abs(math.log(k[2] / cur_s)))
                for k in others:
                    self._draw_tile(p, r, k, cur_s, smooth=True)
            p.setRenderHint(QPainter.SmoothPixmapTransform, not exact)
            for k in needed:
                if k in self.tiles:
                    self.tiles.move_to_end(k)
                    self._draw_tile(p, r, k, cur_s, smooth=not exact)
            if self.items.get(i) or (self.ghost and self.ghost[0] == i):
                p.translate(r.x(), r.y())
                p.scale(self.zoom, self.zoom)
                p.setRenderHint(QPainter.Antialiasing, True)
                self.paint_overlay(p, i)
            p.restore()
        if self.tool == "erase" and self._cursor_pt is not None:
            c = self._content_pt(self._cursor_pt)
            pen = p.pen()
            pen.setColor(QColor("#5a6270"))
            pen.setStyle(Qt.SolidLine)
            pen.setWidthF(1.2)
            p.setPen(pen)
            p.setBrush(QColor(255, 255, 255, 90))
            p.drawEllipse(c, 8.0, 8.0)
            p.setBrush(Qt.NoBrush)
        if self._sel:
            a, b = self._sel
            sr = QRectF(a, b).normalized()
            p.fillRect(sr, QColor(200, 32, 47, 28))
            pen = p.pen()
            pen.setColor(QColor(ACCENT))
            pen.setStyle(Qt.DashLine)
            pen.setWidthF(1.5)
            p.setPen(pen)
            p.drawRect(sr)
        if self.erase_rect:
            ei, er = self.erase_rect
            prr = self.page_rect(ei)
            p.save()
            p.translate(prr.x(), prr.y())
            p.scale(self.zoom, self.zoom)
            p.fillRect(er, QColor(200, 32, 47, 45))
            p.setPen(A._pen("#c8202f", True, True, 1.6))
            p.setBrush(Qt.NoBrush)
            p.drawRect(er)
            hs = 4.5 / self.zoom
            p.setPen(A._pen("#c8202f", True, width=1.2))
            p.setBrush(QColor("#ffffff"))
            for loc, _ in self._erase_rect_handles():
                p.drawRect(QRectF(loc.x() - hs, loc.y() - hs, 2 * hs, 2 * hs))
            p.restore()
        b = self.scale_badge(self._cur_page)
        if b:
            p.resetTransform()
            f = p.font()
            f.setPointSizeF(9.5)
            p.setFont(f)
            fm = p.fontMetrics()
            w = fm.horizontalAdvance(b[0]) + 18
            rr = QRectF(self.viewport().width() - w - 10, 8, w, fm.height() + 8)
            p.setPen(QColor("#cfd4db"))
            p.setBrush(QColor(255, 255, 255, 235))
            p.drawRoundedRect(rr, 4, 4)
            p.setPen(QColor(b[1]))
            p.drawText(rr, Qt.AlignCenter, b[0])
        p.end()

    def _draw_tile(self, p, r, k, cur_s, smooth):
        pm, px, py, _ = self.tiles[k]
        f = self.zoom / k[2]          # מפיקסל אריח ליחידה לוגית
        tgt = QRectF(r.x() + px * f, r.y() + py * f, pm.width() * f, pm.height() * f)
        p.drawPixmap(tgt, pm, QRectF(0, 0, pm.width(), pm.height()))

    # ----- events
    def resizeEvent(self, ev):
        super().resizeEvent(ev)
        if getattr(self, "tray", None) is not None and self.tray.isVisible():
            self.tray._place()
        self._update_scrollbars()
        self.sched_timer.start()

    def scrollContentsBy(self, dx, dy):
        self._place_editor()
        self.viewport().update()

    def _scrolled(self, *_):
        self.sched_timer.start()
        if self.sizes:
            vs = self.verticalScrollBar().value()
            i = self.page_at(vs + self.viewport().height() / 3)
            if i != self._cur_page:
                self._cur_page = i
                self.page_changed.emit(i, len(self.sizes))
                if i not in self._asked:
                    self.analyze_timer.start()

    def wheelEvent(self, ev):
        if not self.sizes:
            return
        ctrl = bool(ev.modifiers() & Qt.ControlModifier)
        if ctrl != self.wheel_zoom:     # זום (Ctrl מחליף מצב)
            dy = ev.angleDelta().y() or ev.pixelDelta().y()
            if dy:
                self.set_zoom(self.zoom * (1.0015 ** dy), ev.position())
            ev.accept()
            return
        if ev.modifiers() & Qt.ShiftModifier:
            d = ev.angleDelta().y()
            self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() - d)
            ev.accept()
            return
        super().wheelEvent(ev)

    # ----- annotations (חורים ומדידה)
    def to_page(self, pos, page=None):
        c = self._content_pt(pos)
        i = self.page_at(c.y()) if page is None else page
        r = self.page_rect(i)
        return i, QPointF((c.x() - r.x()) / self.zoom, (c.y() - r.y()) / self.zoom)

    def scale_of(self, i):
        if i in self.scales:
            return self.scales[i]
        if i not in self.auto_scales:
            S = self._detect_scale(i)
            self.auto_scales[i] = S or self.default_scale
            if i not in self.scale_info:
                self.scale_info[i] = {"text": S, "dims": None, "votes": 0, "matched": 0, "quick": True}
        return self.auto_scales[i]

    def shown_scale(self, i):
        """הקנ"מ להצגה בסרגל — בלי לקרוא את העמוד (לא מאט את הפתיחה)."""
        return self.scales.get(i) or self.auto_scales.get(i) or self.default_scale

    # ----- זיהוי ואימות קנ"מ ברקע
    def _request_analysis(self):
        i = self._cur_page
        if not self.sizes or i < 0 or i in self._asked:
            return
        if self.pool.wanted or self.pool.inflight or self._drag or self.zoom_timer.isActive():
            # קודם כל השרטוט: הבדיקה מתחילה רק כשהרינדור סיים ואין תנועה
            self.analyze_timer.start(400)
            return
        self._asked.add(i)
        self.analyzer.request(self.docgen, self.src, self.pw, i)

    def reanalyze(self):
        i = max(0, self._cur_page)
        self.scales.pop(i, None)
        self._save_scales()
        self._asked.discard(i)
        self.scale_info.pop(i, None)
        self.auto_scales.pop(i, None)
        self._request_analysis()
        self.status.emit("בודק את קנה המידה מול המידות בשרטוט...")

    def _on_analysis(self, gen, i, res):
        if gen != self.docgen:
            return
        self.scale_info[i] = res
        S = res.get("dims") or res.get("text")
        if S:
            self.auto_scales[i] = float(S)
        if i == self._cur_page:
            msg = self.scale_message(i)
            if msg:
                self.status.emit(msg)
        self.scale_changed.emit(self.scale_of(i))
        self.viewport().update()

    def scale_message(self, i):
        if i in self.scales:
            return ""
        r = self.scale_info.get(i) or {}
        d, t = r.get("dims"), r.get("text")
        if d and t and d != t:
            return (f"שימו לב: בשרטוט כתוב 1:{t}, אבל המידות מתאימות ל-1:{d}. "
                    f"נקבע 1:{d} — אפשר לשנות במדידה ← קנה מידה לעמוד")
        if d:
            return f"קנ\"מ 1:{d} אומת מול {r.get('votes', 0)} מידות בשרטוט"
        if t:
            return f"קנ\"מ 1:{t} לפי הכיתוב בשרטוט (לא נמצאו מידות לאימות)"
        if r and not r.get("quick"):
            return "לא זוהה קנ\"מ בשרטוט — מומלץ לכייל (מדידה ← כיול)"
        return ""

    def scale_badge(self, i):
        """הטקסט שמוצג בפינת השרטוט: קנ"מ ומצב האימות."""
        if i < 0 or not self.sizes:
            return None
        if i in self.scales:
            return f"קנ\"מ 1:{self.scales[i]:.4g}  (נקבע ידנית)", "#1f2630"
        r = self.scale_info.get(i)
        if not r or r.get("quick"):
            if i in self._asked:
                return "בודק קנ\"מ...", "#7a828e"
            return None
        d, t = r.get("dims"), r.get("text")
        if d and t and d != t:
            return f"קנ\"מ 1:{d} ✓ לפי המידות (בכיתוב 1:{t})", "#c8202f"
        if d:
            return f"קנ\"מ 1:{d} ✓ אומת מול המידות", "#1a7f37"
        if t:
            return f"קנ\"מ 1:{t} לפי הכיתוב — לא אומת", "#9a6700"
        return "קנ\"מ לא זוהה — מומלץ לכייל", "#9a6700"

    def set_scale(self, i, S):
        self.scales[i] = S
        self.default_scale = S
        QSettings("Tiktin", "TiktinPDF").setValue("default_scale", S)
        self._save_scales()
        self.viewport().update()

    def _scale_key(self):
        import hashlib
        return "scales/" + hashlib.md5(os.path.abspath(self.path).lower().encode("utf-8")).hexdigest()

    def _save_scales(self):
        if self.path:
            QSettings("Tiktin", "TiktinPDF").setValue(
                self._scale_key(), ",".join(f"{k}:{v:g}" for k, v in self.scales.items()))

    def _load_scales(self):
        self.scales = {}
        raw = QSettings("Tiktin", "TiktinPDF").value(self._scale_key(), "")
        for part in str(raw or "").split(","):
            if ":" in part:
                k, v = part.split(":")
                try:
                    self.scales[int(k)] = float(v)
                except ValueError:
                    pass

    def _detect_scale(self, i):
        import re
        try:
            txt = self.doc[i].get_text()
        except Exception:
            return None
        common = {10, 20, 25, 50, 75, 100, 125, 200, 250, 500, 1000}
        found = [int(m) for m in re.findall(r"1\s*:\s*(\d{2,4})(?!\d)", txt) if int(m) in common]
        if not found:
            return None
        return max(set(found), key=found.count)

    def set_tool(self, tool, template=None):
        if self.editor:
            self.finish_text_edit()
        self.tool = tool
        self.template = template
        self.ghost = None
        self.dim_start = None
        self.shape_start = None
        self.erase_rect = None
        self._erase_drag = None
        self.calib = None
        if tool != "pan":
            self.selected = None
        cur = {"pan": Qt.OpenHandCursor if self.sizes else Qt.ArrowCursor, "text": Qt.IBeamCursor,
               "erase": Qt.BlankCursor}.get(tool, Qt.CrossCursor)
        self.viewport().setCursor(cur)
        self.tool_changed.emit(tool)
        self.viewport().update()

    def _snapshot(self):
        return {k: [dict(it) for it in v] for k, v in self.items.items()}

    def _push_undo(self):
        self.undo.append(self._snapshot())
        del self.undo[:-50]
        self.redo = []
        self.dirty = True
        self.changed.emit()

    def do_undo(self):
        if self.editor:
            self.finish_text_edit()
        if self.undo and isinstance(self.undo[-1], tuple):
            st = self.undo.pop()
            self.redo.append(self._page_state())
            self._restore_page_state(st)
            return
        if self.undo:
            self.redo.append(self._snapshot())
            self.items = self.undo.pop()
            self.selected = None
            self.dirty = True
            self.changed.emit()
            self.viewport().update()
        else:
            self.status.emit("אין פעולה לביטול")

    def do_redo(self):
        if self.editor:
            self.finish_text_edit()
        if self.redo and isinstance(self.redo[-1], tuple):
            st = self.redo.pop()
            self.undo.append(self._page_state())
            self._restore_page_state(st)
            return
        if self.redo:
            self.undo.append(self._snapshot())
            self.items = self.redo.pop()
            self.selected = None
            self.dirty = True
            self.changed.emit()
            self.viewport().update()
        else:
            self.status.emit("אין פעולה לחזרה")

    # ----- מחיקת עמודים (ניתנת לביטול עד השמירה)
    def _page_state(self):
        return ("pages", self.src, self.pw, self._snapshot(), dict(self.scales), dict(self.auto_scales),
                self.pages_changed)

    def _reload_src(self, src, pw, keep_view=False):
        undo, redo, path = self.undo, self.redo, self.path
        view = (self.zoom, self.horizontalScrollBar().value(), self.verticalScrollBar().value(),
                self.tool, dict(self.template or {})) if keep_view else None
        doc = pymupdf.open(src)
        if doc.needs_pass:
            doc.authenticate(pw or "")
        old = self.doc
        cur = max(0, self._cur_page)
        self.open_doc(doc, path, pw, src=src)
        if old is not None and old is not doc:
            try:
                old.close()
            except Exception:
                pass
        self.undo, self.redo = undo, redo
        if view:
            z, hx, vy, tool, tpl = view
            self.set_zoom(z)
            self.horizontalScrollBar().setValue(hx)
            self.verticalScrollBar().setValue(vy)
            if tool.startswith("erase_"):
                self.set_tool(tool, tpl)
        return cur

    def _restore_page_state(self, st):
        _, src, pw, items, scales, auto, changed = st
        self._seg_cache = {}
        cur = self._reload_src(src, pw, keep_view=True)
        self.items, self.scales, self.auto_scales = items, scales, auto
        self.pages_changed = changed
        self.dirty = True
        self.changed.emit()
        self.go_page(min(cur, len(self.sizes) - 1))
        self.viewport().update()

    # ----- מחיקה מהשרטוט המקורי (ניתנת לביטול עד השמירה)
    def _edit_src(self, i, fn):
        """מריץ שינוי על עמוד i בעותק של הקובץ, וטוען אותו במקום — בלי לשנות את התצוגה."""
        import tempfile
        import uuid
        st = self._page_state()
        doc2 = pymupdf.open(self.src)
        if doc2.needs_pass:
            doc2.authenticate(self.pw or "")
        marks_store.strip_page(doc2, doc2[i])      # סימונים צרובים ייצרבו שוב בשמירה
        result = fn(doc2[i])
        if not result:
            doc2.close()
            return result
        d = os.path.join(tempfile.gettempdir(), "TiktinPDF-work")
        os.makedirs(d, exist_ok=True)
        tmp = os.path.join(d, uuid.uuid4().hex + ".pdf")
        doc2.save(tmp)
        doc2.close()
        items, scales, auto = self._snapshot(), dict(self.scales), dict(self.auto_scales)
        self._reload_src(tmp, None, keep_view=True)
        self.undo.append(st)
        del self.undo[:-50]
        self.redo = []
        self.items, self.scales, self.auto_scales = items, scales, auto
        self.pages_changed = True
        self.dirty = True
        self.changed.emit()
        self.viewport().update()
        return result

    def _segments(self, i):
        """קטעי הקווים של עמוד (במערכת העמוד הלא מסובבת), עם רשת חיפוש מהירה. נבנה פעם אחת לעמוד."""
        cache = self._seg_cache.get(i)
        if cache is None:
            page = self.doc[i]
            grid, cell = {}, 40.0
            segs = []
            try:
                paths = page.get_cdrawings()
            except Exception:
                paths = []
            for pth in paths:
                if pth.get("type") == "f":            # מילוי בלבד (לא קו)
                    continue
                w = pth.get("width") or 0.5
                for itm in pth.get("items", ()):
                    k = itm[0]
                    if k == "l":
                        pieces = [(itm[1], itm[2])]
                    elif k == "re":
                        x0, y0, x1, y1 = itm[1]
                        pieces = [((x0, y0), (x1, y0)), ((x1, y0), (x1, y1)), ((x1, y1), (x0, y1)), ((x0, y1), (x0, y0))]
                    elif k == "qu":
                        q = itm[1]
                        pts = [q[0], q[1], q[3], q[2]] if len(q) == 4 else list(q)
                        pieces = [(pts[n], pts[(n + 1) % 4]) for n in range(4)]
                    elif k == "c":
                        pieces = [(itm[1], itm[2]), (itm[2], itm[3]), (itm[3], itm[4])]
                    else:
                        continue
                    for a_, b_ in pieces:
                        sid = len(segs)
                        segs.append((a_[0], a_[1], b_[0], b_[1], w, k, itm if k == "c" else None))
                        gx0, gx1 = int(min(a_[0], b_[0]) // cell), int(max(a_[0], b_[0]) // cell)
                        gy0, gy1 = int(min(a_[1], b_[1]) // cell), int(max(a_[1], b_[1]) // cell)
                        if (gx1 - gx0 + 1) * (gy1 - gy0 + 1) > 400:   # קו ארוך מאוד: רק בתאים שלאורכו
                            n = max(gx1 - gx0, gy1 - gy0) + 1
                            for t in range(n + 1):
                                x = a_[0] + (b_[0] - a_[0]) * t / n
                                y = a_[1] + (b_[1] - a_[1]) * t / n
                                grid.setdefault((int(x // cell), int(y // cell)), []).append(sid)
                        else:
                            for gx in range(gx0, gx1 + 1):
                                for gy in range(gy0, gy1 + 1):
                                    grid.setdefault((gx, gy), []).append(sid)
            cache = {"segs": segs, "grid": grid, "cell": cell, "erased": set()}
            self._seg_cache[i] = cache
        return cache

    def erase_src_item(self, i, pt):
        """מוחק מהשרטוט המקורי פריט בודד מתחת לעכבר: מילה (מחיקה אמיתית), או קטע קו (מכוסה בלבן)."""
        tol = max(1.0, 6.0 / self.zoom)
        page0 = self.doc[i]
        q = pymupdf.Point(pt.x(), pt.y()) * page0.derotation_matrix
        word = None
        for w in page0.get_text("words"):
            if pymupdf.Rect(w[:4]).contains(q):
                word = w
                break
        if word:
            def fn_word(page):
                page.add_redact_annot(pymupdf.Rect(word[:4]))
                page.apply_redactions(images=pymupdf.PDF_REDACT_IMAGE_NONE,
                                      graphics=pymupdf.PDF_REDACT_LINE_ART_NONE,
                                      text=pymupdf.PDF_REDACT_TEXT_REMOVE)
                return f"המילה \"{word[4]}\""
            return self._edit_src(i, fn_word)
        cache = self._segments(i)
        cell = cache["cell"]
        best = None
        for gx in range(int((q.x - tol) // cell), int((q.x + tol) // cell) + 1):
            for gy in range(int((q.y - tol) // cell), int((q.y + tol) // cell) + 1):
                for sid in cache["grid"].get((gx, gy), ()):
                    if sid in cache["erased"]:
                        continue
                    x1, y1, x2, y2, w, k, c = cache["segs"][sid]
                    d = A._seg_dist(q.x, q.y, x1, y1, x2, y2) - w / 2
                    if d <= tol and (best is None or d < best[0]):
                        best = (d, sid)
        if best is None:
            return ""
        sid = best[1]
        x1, y1, x2, y2, w, k, c = cache["segs"][sid]

        def fn_seg(page):
            sh = page.new_shape()
            if k == "c" and c is not None:
                sh.draw_bezier(c[1], c[2], c[3], c[4])
            else:
                sh.draw_line((x1, y1), (x2, y2))
            sh.finish(color=(1, 1, 1), width=w + 0.8, lineCap=0, closePath=False)
            sh.commit()
            return "הקו שנבחר"
        res = self._edit_src(i, fn_seg)
        if res:
            cache["erased"].add(sid)
        return res

    def erase_src_rect(self, i, rect):
        """מוחק מהשרטוט המקורי את כל מה שבתוך המלבן (קווים, טקסט, ובסריקה — הפיקסלים)."""
        def fn(page):
            m = page.derotation_matrix
            r = (pymupdf.Rect(rect.left(), rect.top(), rect.right(), rect.bottom()) * m).normalize()
            page.add_redact_annot(r, fill=(1, 1, 1))
            page.apply_redactions(images=pymupdf.PDF_REDACT_IMAGE_PIXELS,
                                  graphics=pymupdf.PDF_REDACT_LINE_ART_REMOVE_IF_COVERED,
                                  text=pymupdf.PDF_REDACT_TEXT_REMOVE)
            return "האזור שסומן"
        return self._edit_src(i, fn)

    def _erase_rect_handles(self):
        if not self.erase_rect:
            return []
        i, r = self.erase_rect
        return [(QPointF(r.left(), r.top()), (-1, -1)), (QPointF(r.right(), r.top()), (1, -1)),
                (QPointF(r.left(), r.bottom()), (-1, 1)), (QPointF(r.right(), r.bottom()), (1, 1))]

    def _erase_rect_hit(self, pos):
        """איזה חלק של המלבן מתחת לעכבר: ידית פינה, גוף המלבן, או כלום."""
        if not self.erase_rect:
            return None
        i, r = self.erase_rect
        _, pt = self.to_page(pos, page=i)
        tol = 7.0 / self.zoom
        for loc, hh in self._erase_rect_handles():
            if abs(loc.x() - pt.x()) <= tol and abs(loc.y() - pt.y()) <= tol:
                return ("h", hh)
        if r.contains(pt):
            return ("in", None)
        return None

    def apply_erase_rect(self):
        if not self.erase_rect:
            return
        i, r = self.erase_rect
        if r.width() * self.zoom < 3 or r.height() * self.zoom < 3:
            return
        self.erase_rect = None
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            what = self.erase_src_rect(i, r)
        finally:
            QApplication.restoreOverrideCursor()
        self.status.emit(f"נמחק מהשרטוט: {what}. UNDO מחזיר; הקובץ עצמו משתנה רק ב\"שמירת שינויים\"")

    def delete_pages(self, pages):
        """מוחק עמודים (אינדקסים מ-0). הקובץ המקורי לא משתנה עד "שמירת שינויים"."""
        import tempfile
        import uuid
        pages = sorted(set(p for p in pages if 0 <= p < len(self.sizes)))
        if not pages or len(pages) >= len(self.sizes):
            return False
        if self.editor:
            self.finish_text_edit()
        st = self._page_state()
        doc2 = pymupdf.open(self.src)
        if doc2.needs_pass:
            doc2.authenticate(self.pw or "")
        doc2.delete_pages(pages)
        d = os.path.join(tempfile.gettempdir(), "TiktinPDF-work")
        os.makedirs(d, exist_ok=True)
        tmp = os.path.join(d, uuid.uuid4().hex + ".pdf")
        doc2.save(tmp, garbage=1)
        doc2.close()
        gone = set(pages)
        self._seg_cache = {}

        def newidx(i):
            return i - sum(1 for p in pages if p < i)

        items = {newidx(i): v for i, v in self.items.items() if i not in gone}
        scales = {newidx(i): v for i, v in self.scales.items() if i not in gone}
        auto = {newidx(i): v for i, v in self.auto_scales.items() if i not in gone}
        cur = self._reload_src(tmp, None)
        self.undo.append(st)
        del self.undo[:-50]
        self.redo = []
        self.items, self.scales, self.auto_scales = items, scales, auto
        self.pages_changed = True
        self.dirty = True
        self.changed.emit()
        self.go_page(min(newidx(cur) if cur not in gone else cur, len(self.sizes) - 1))
        self.viewport().update()
        return True

    # ----- סיבוב עמודים (ניתן לביטול עד השמירה)
    @staticmethod
    def _rot_items(items, W, H, d):
        """מסובב את הסימונים יחד עם העמוד. d = 90 (עם השעון), -90 (נגד) או 180."""
        def T(x, y):
            if d == 90:
                return (H - y, x)
            if d == -90:
                return (y, W - x)
            return (W - x, H - y)

        out = []
        for it in items:
            it = dict(it)
            t = it["type"]
            if t in ("dim", "shape"):
                it["p1"], it["p2"] = T(*it["p1"]), T(*it["p2"])
            elif t == "ink":
                it["pts"] = [T(x, y) for x, y in it["pts"]]
            elif t == "text":
                r = A.text_rect(it)
                cx, cy = r.center().x(), r.center().y()
                ox, oy = it["p"][0] - cx, it["p"][1] - cy
                nx, ny = T(cx, cy)
                it["p"] = (nx + ox, ny + oy)          # הטקסט נשאר קריא (לא מסתובב)
            elif "c" in it:
                it["c"] = T(*it["c"])
                if t == "hole":
                    if d != 180:
                        it["angle"] = (it.get("angle", 0) + 90) % 180
                elif t == "mark" and it.get("kind") in ("num", "q"):
                    pass                                # מספרים וסימן שאלה נשארים קריאים
                else:
                    it["angle"] = (it.get("angle", 0.0) + d) % 360
            out.append(it)
        return out

    def _text_turn(self, i):
        """כמה מעלות (עם השעון) צריך לסובב את העמוד כדי שרוב הטקסט יעמוד ישר וקריא. None = אין מספיק טקסט."""
        try:
            page = self.doc[i]
            w = {0: 0, 90: 0, 180: 0, 270: 0}
            for b in page.get_text("dict", flags=0)["blocks"]:
                for ln in b.get("lines", ()):
                    n = sum(len(sp["text"].strip()) for sp in ln["spans"])
                    if not n:
                        continue
                    dx, dy = ln["dir"]
                    a = int(round(math.degrees(math.atan2(dy, dx)) / 90.0)) * 90 % 360
                    w[a] += n
            a, n = max(w.items(), key=lambda kv: kv[1])
            if n < 8:
                return None
            return (-(a + page.rotation)) % 360
        except Exception:
            return None

    def rotate_pages(self, pages, mode, cw=True):
        """mode: 'rot' = 90° / '180' / 'portrait' / 'landscape'. מחזיר את מספר העמודים שסובבו."""
        import tempfile
        import uuid
        if self.editor:
            self.finish_text_edit()
        d0 = 90 if cw else -90
        plan = {}
        self.rotate_unknown = []          # עמודים שבהם אי אפשר לזהות את כיוון הטקסט (למשל סריקה)
        self.rotate_sideways = []         # עמודים שבמצב שנבחר הטקסט יוצא אנכי
        for i in pages:
            W, H = self.sizes[i]
            if mode == "rot":
                plan[i] = d0
            elif mode == "180":
                plan[i] = 180
            elif mode in ("portrait", "landscape", "upright"):
                t = self._text_turn(i)            # הסיבוב שמעמיד את הטקסט ישר
                if t is None:
                    self.rotate_unknown.append(i)
                if mode == "upright":
                    r = t
                else:
                    want_land = mode == "landscape"
                    if t is None:
                        r = 0 if (W > H) == want_land else d0 % 360
                    else:
                        land_after = (W > H) if t in (0, 180) else (H > W)
                        if land_after == want_land:
                            r = t                  # גם במצב הנכון וגם טקסט ישר
                        else:
                            # אי אפשר גם וגם: עומדים במצב שנבחר, והטקסט נקרא מלמטה למעלה (כמו מידות בשרטוט)
                            r = (t - 90) % 360
                            self.rotate_sideways.append(i)
                if r:
                    plan[i] = {90: 90, 180: 180, 270: -90}[r % 360]
        if not plan:
            return 0
        self._seg_cache = {}
        st = self._page_state()
        doc2 = pymupdf.open(self.src)
        if doc2.needs_pass:
            doc2.authenticate(self.pw or "")
        for i, d in plan.items():
            pg = doc2[i]
            pg.set_rotation((pg.rotation + d) % 360)
        dd = os.path.join(tempfile.gettempdir(), "TiktinPDF-work")
        os.makedirs(dd, exist_ok=True)
        tmp = os.path.join(dd, uuid.uuid4().hex + ".pdf")
        doc2.save(tmp)
        doc2.close()
        items = dict(self.items)
        for i, d in plan.items():
            if items.get(i):
                W, H = self.sizes[i]
                items[i] = self._rot_items(items[i], W, H, d)
        scales, auto = dict(self.scales), dict(self.auto_scales)
        cur = self._reload_src(tmp, None)
        self.undo.append(st)
        del self.undo[:-50]
        self.redo = []
        self.items, self.scales, self.auto_scales = items, scales, auto
        self.pages_changed = True
        self.dirty = True
        self.changed.emit()
        self.go_page(cur)
        self.viewport().update()
        return len(plan)

    def delete_selected(self):
        if self.selected:
            i, idx = self.selected
            self._push_undo()
            del self.items[i][idx]
            self.selected = None
            self.viewport().update()

    def _handle_at(self, pos):
        if not self.selected or self.tool not in ("pan", "text") or self.editor:
            return None
        i, idx = self.selected
        if idx >= len(self.items.get(i, [])):
            return None
        it = self.items[i][idx]
        if it["type"] not in ("hole", "text", "trafo") and it["type"] not in EXTRA:
            return None
        _, pt = self.to_page(pos, page=i)
        tol = 6.0 / self.zoom
        hs = self._handles(it, i)
        for loc, hh in hs:
            if abs(loc.x() - pt.x()) <= tol and abs(loc.y() - pt.y()) <= tol:
                return i, idx, hh
        return None

    def _handles(self, it, i):
        t = it["type"]
        if AX.rotatable(it):
            base = EXTRA[t]["handles"](it) if t in EXTRA else A.trafo_handles(it)
            if it.get("angle"):
                base = AX.rot_handles(base, it)
            return base + [(AX.rot_handle_pos(it, 22.0 / self.zoom), ("r", 0))]
        if t in EXTRA:
            return EXTRA[t]["handles"](it)
        if t == "text":
            return A.text_handles(it)
        if t == "trafo":
            return A.trafo_handles(it)
        return A.hole_handles(it, self.scale_of(i))

    def _hit_item(self, pos):
        if not self.sizes:
            return None
        i, pt = self.to_page(pos)
        S = self.scale_of(i)
        tol = 4.0 / self.zoom
        for idx in range(len(self.items.get(i, [])) - 1, -1, -1):
            if A.hit(self.items[i][idx], pt, S, tol):
                return i, idx
        return None

    def _ortho(self, a, b, ev):
        if ev.modifiers() & Qt.ShiftModifier:
            if abs(b.x() - a.x()) >= abs(b.y() - a.y()):
                return QPointF(b.x(), a.y())
            return QPointF(a.x(), b.y())
        return b

    def _erase_at(self, pos):
        i, pt = self.to_page(pos)
        last = self._last_erase if self._erasing and self._last_erase and self._last_erase[0] == i else None
        self._last_erase = (i, pt)
        if not self.items.get(i):
            return
        r = 8.0 / self.zoom
        # מוחק לאורך כל המסלול מהנקודה הקודמת, כדי שתנועה מהירה לא "תדלג" על קווים
        pts = [pt]
        if last:
            p0 = last[1]
            n = int(math.hypot(pt.x() - p0.x(), pt.y() - p0.y()) / (r / 2)) + 1
            pts = [QPointF(p0.x() + (pt.x() - p0.x()) * j / n, p0.y() + (pt.y() - p0.y()) * j / n)
                   for j in range(1, n + 1)]
        items, changed = self.items[i], False
        for q in pts:
            items, ch = A.erase_ink(items, q, r)
            changed = changed or ch
        new = items
        if changed:
            self.items[i] = new
            self.selected = None
            self.dirty = True
            self.changed.emit()
            self.viewport().update()

    def leaveEvent(self, ev):
        self._cursor_pt = None
        self.viewport().update()
        super().leaveEvent(ev)

    # ----- inline text editing (הטקסט נכתב ישירות על השרטוט)
    def start_text_edit(self, i, idx, undo=True):
        if self.editor:
            self.finish_text_edit()
        if undo:
            self._push_undo()
        self.editing = (i, idx)
        self.selected = (i, idx)
        it = self.items[i][idx]
        ed = InlineText(self.viewport())
        ed.setPlainText(it["text"])
        ed.textChanged.connect(self._text_changed)
        ed.finished.connect(self.finish_text_edit)
        self.editor = ed
        self._place_editor()
        ed.show()
        ed.setFocus()
        ed.moveCursor(QTextCursor.End)
        self._kb.on()
        self.viewport().update()

    def _text_changed(self):
        if self.editor and self.editing:
            i, idx = self.editing
            self.items[i][idx]["text"] = self.editor.toPlainText()
            self._place_editor()

    def _place_editor(self):
        if not self.editor or not self.editing:
            return
        i, idx = self.editing
        it = self.items[i][idx]
        ed = self.editor
        ed.set_style(it["color"], it["size"] * A.PT_PER_MM * self.zoom)
        w, h = ed.fit_size()
        r = self.page_rect(i)
        x = r.x() + it["p"][0] * self.zoom - self.horizontalScrollBar().value()
        y = r.y() + it["p"][1] * self.zoom - self.verticalScrollBar().value()
        pad = 3
        ed.setGeometry(int(x - w + pad), int(y - pad), w, h)

    def finish_text_edit(self):
        ed, ref = self.editor, self.editing
        if not ed:
            return
        self.editor, self.editing = None, None
        self._kb.off()
        ed.hide()
        ed.deleteLater()
        i, idx = ref
        if idx < len(self.items.get(i, [])):
            it = self.items[i][idx]
            it["text"] = ed.toPlainText().rstrip()
            if not it["text"].strip():
                del self.items[i][idx]
                self.selected = None
                if self.undo:
                    self.undo.pop()
            else:
                self.selected = (i, idx)
                self.dirty = True
                self.changed.emit()
        self.viewport().update()
        self.setFocus()

    def edit_selected(self):
        if not self.selected:
            return
        i, idx = self.selected
        it = self.items[i][idx]
        if it["type"] == "text":
            self.start_text_edit(i, idx)
            return
        if it["type"] == "trafo":
            n = self.ask_trafo_count(QCursor.pos())
            if n:
                self._push_undo()
                it["n"] = n
                self.viewport().update()
            return
        if it["type"] != "hole":
            return
        from hole_dialog import HoleDialog
        dlg = HoleDialog(self, it["kind"], it)
        if dlg.exec() == QDialog.Accepted:
            self._push_undo()
            self.items[i][idx].update(dlg.result_dims)
            self.viewport().update()

    def ask_trafo_count(self, global_pos):
        """תפריט קטן לבחירת כמות השנאים."""
        menu = QMenu(self)
        menu.setLayoutDirection(Qt.RightToLeft)
        acts = {menu.addAction("שנאי 1"): 1, menu.addAction("2 שנאים"): 2, menu.addAction("3 שנאים"): 3}
        a = menu.exec(global_pos)
        return acts.get(a)

    def _finish_shape(self, ev):
        i, a, _ = self.shape_start
        _, b = self.to_page(ev.position(), page=i)
        if self.template["kind"] in ("line", "arrow", "arrow2"):
            b = self._ortho(a, b, ev)
        self.shape_start = None
        self.ghost = None
        if math.hypot(b.x() - a.x(), b.y() - a.y()) * self.zoom < 4:
            self.viewport().update()
            return
        it = dict(self.template)
        it.update({"type": "shape", "p1": (a.x(), a.y()), "p2": (b.x(), b.y()),
                   "color": self.pen_color, "w": self.pen_w})
        self._push_undo()
        self.items.setdefault(i, []).append(it)
        self.viewport().update()

    def next_number(self):
        n = 0
        for items in self.items.values():
            for it in items:
                if it["type"] == "mark" and it.get("kind") == "num":
                    n = max(n, int(it.get("n", 0)))
        return n + 1

    def _page_ink(self, i):
        """מפת הדיו של עמוד (נבנית פעם אחת לעמוד, מפענוח אחד)."""
        key = (self.docgen, i)
        ink = self._ink_cache.get(key)
        if ink is None:
            if len(self._ink_cache) > 400:
                self._ink_cache.clear()
            ink = self._ink_cache[key] = stamps.page_ink(self.doc[i])
        return ink

    def stamp_auto_w(self, i, slot):
        k = QSettings("Tiktin", "TiktinPDF").value(f"stamp_k{slot}", 1.0, type=float) if isinstance(slot, int) else 1.0
        return stamps.auto_width_mm(slot, self._page_ink(i), min(max(k, 0.3), 4.0))

    def _stamp_fit(self, i, it, autosize=False):
        """מתאים חותמת לעמוד: גודל לפי הכתב שבשרטוט, ומקום שלא מסתיר טקסט, קווים או סימונים. מחזיר True אם הוזזה."""
        ink = self._page_ink(i)
        if autosize:
            it["w"] = self.stamp_auto_w(i, it.get("slot"))
        r = EXTRA["stamp"]["bbox"](it)
        blocked = []
        for o in self.items.get(i, ()):
            if o is it:
                continue
            try:
                b = A.item_bbox(o, self.scale_of(i))
                blocked.append((b.left(), b.top(), b.right(), b.bottom()))
            except Exception:
                pass
        cx0, cy0 = it["c"]
        cx, cy, clean = stamps.find_free_spot(ink, r.width(), r.height(), cx0, cy0, blocked)
        it["c"] = (cx, cy)
        self._stamp_clean = clean
        return abs(cx - cx0) > 0.5 or abs(cy - cy0) > 0.5

    def stamp_all_pages(self, i0, it0):
        """מוסיף את החותמת לשאר העמודים, במקום פנוי מטקסט קרוב למיקום שנבחר בעמוד הראשון."""
        n = len(self.sizes)
        W0, H0 = self.sizes[i0]
        r = EXTRA["stamp"]["bbox"](it0)
        fx, fy = it0["c"][0] / W0, it0["c"][1] / H0
        del r
        prog = None
        if n > 8:
            prog = QProgressDialog("מוסיף חותמת לכל העמודים...", "ביטול", 0, n - 1, self)
            prog.setWindowTitle(APP_NAME)
            prog.setWindowModality(Qt.WindowModal)
            prog.setMinimumDuration(300)
        QApplication.setOverrideCursor(Qt.WaitCursor)
        moved, done, crowded = 0, 0, []
        try:
            for k, j in enumerate(x for x in range(n) if x != i0):
                if prog:
                    prog.setValue(k)
                    QApplication.processEvents()
                    if prog.wasCanceled():
                        break
                W, H = self.sizes[j]
                it = dict(it0)
                it["c"] = (fx * W, fy * H)
                if self._stamp_fit(j, it, autosize=True):
                    moved += 1
                if not self._stamp_clean:
                    crowded.append(j)
                self.items.setdefault(j, []).append(it)
                done += 1
        finally:
            QApplication.restoreOverrideCursor()
            if prog:
                prog.close()
        self.dirty = True
        self.changed.emit()
        self.viewport().update()
        extra = f" (ב-{moved} עמודים הוזזה למקום שלא מסתיר טקסט או שרטוט)" if moved else ""
        if crowded:
            pg = ", ".join(str(j + 1) for j in crowded[:12]) + ("..." if len(crowded) > 12 else "")
            extra += f". בעמודים {pg} אין מקום פנוי לגמרי — הונחה במקום שמסתיר הכי פחות, כדאי לבדוק"
        self.status.emit(f"החותמת נוספה ל-{done + 1} עמודים{extra}. ביטול פעולה מסיר את כולן")

    def has_items(self):
        return any(self.items.values())

    def paint_overlay(self, p, i, cosmetic=True):
        S = self.scale_of(i) if (self.items.get(i) or (self.ghost and self.ghost[0] == i)) else None
        if S is None:
            return
        for idx, it in enumerate(self.items.get(i, [])):
            if cosmetic and self.editing == (i, idx):
                continue
            A.paint_item(p, it, S, cosmetic, selected=cosmetic and self.selected == (i, idx))
        if cosmetic and self.selected and self.selected[0] == i and self.tool in ("pan", "text") \
                and self.selected[1] < len(self.items.get(i, [])):
            it = self.items[i][self.selected[1]]
            if (it["type"] in ("hole", "text", "trafo") or it["type"] in EXTRA) \
                    and self.editing != self.selected:
                hs = 4.0 / self.zoom
                p.save()
                p.setPen(A._pen(A.SEL_COLOR, True, width=1.2))
                p.setBrush(QColor("#ffffff"))
                hl = self._handles(it, i)
                for loc, hh in hl:
                    if hh[0] == "r":
                        top = AX.to_world(it, QPointF(AX._base_bbox(it).center().x(), AX._base_bbox(it).top()))
                        p.drawLine(top, loc)
                        p.setBrush(QColor(A.SEL_COLOR))
                        p.drawEllipse(loc, hs * 1.2, hs * 1.2)
                        p.setBrush(QColor("#ffffff"))
                    else:
                        p.drawRect(QRectF(loc.x() - hs, loc.y() - hs, 2 * hs, 2 * hs))
                p.restore()
        if self.ghost and self.ghost[0] == i:
            A.paint_item(p, self.ghost[1], S, cosmetic, ghost=True)

    # ----- mouse
    def mousePressEvent(self, ev):
        if self.select_mode and ev.button() == Qt.LeftButton:
            c = self._content_pt(ev.position())
            self._sel = (c, c)
            ev.accept()
            return
        if not self.sizes:
            return
        if ev.button() == Qt.RightButton and self.tool != "pan":
            self.set_tool("pan")
            return
        if ev.button() == Qt.LeftButton and self.tool == "pen":
            i, pt = self.to_page(ev.position())
            self._push_undo()
            it = {"type": "ink", "pts": [(pt.x(), pt.y())], "color": self.pen_color, "w": self.pen_w}
            self.items.setdefault(i, []).append(it)
            self._stroke = (i, it)
            self.viewport().update()
            return
        if ev.button() == Qt.LeftButton and self.tool == "erase":
            self._push_undo()
            self._erasing = True
            self._last_erase = None
            self._erase_at(ev.position())
            return
        if ev.button() == Qt.LeftButton and self.tool == "text":
            if self.editor:
                self.finish_text_edit()
                return
            hd = self._handle_at(ev.position())
            if hd:
                i, idx, hh = hd
                self._resize = (i, idx, hh, dict(self.items[i][idx]), False)
                return
            h = self._hit_item(ev.position())
            if h and self.items[h[0]][h[1]]["type"] == "text":
                # לחיצה על טקסט קיים: בחירה וגרירה. לחיצה כפולה: עריכת הכיתוב
                self.selected = h
                _, pt = self.to_page(ev.position(), page=h[0])
                self._move = (pt, False)
                self.viewport().update()
                return
            if self.selected:
                self.selected = None
                self.viewport().update()
                return
            i, pt = self.to_page(ev.position())
            self._push_undo()
            self.items.setdefault(i, []).append(
                {"type": "text", "p": (pt.x(), pt.y()), "text": "",
                 "color": self.pen_color, "size": self.text_size})
            self.start_text_edit(i, len(self.items[i]) - 1, undo=False)
            return
        if ev.button() == Qt.LeftButton and self.tool == "erase_item":
            i, pt = self.to_page(ev.position())
            QApplication.setOverrideCursor(Qt.WaitCursor)
            try:
                what = self.erase_src_item(i, pt)
            finally:
                QApplication.restoreOverrideCursor()
            self.status.emit(f"נמחק מהשרטוט: {what}. UNDO מחזיר" if what else
                             "לא נמצא פריט בנקודה הזו — מקליקים בדיוק על קו או על מילה")
            return
        if ev.button() == Qt.LeftButton and self.tool == "erase_rect":
            hit = self._erase_rect_hit(ev.position())
            if hit:
                i, r = self.erase_rect
                _, pt = self.to_page(ev.position(), page=i)
                self._erase_drag = (hit, pt, QRectF(r))
                return
            i, pt = self.to_page(ev.position())
            self.erase_rect = (i, QRectF(pt, pt))
            self._erase_drag = (("h", (1, 1)), pt, QRectF(pt, pt))
            self.viewport().update()
            return
        if ev.button() == Qt.LeftButton and self.tool == "shape":
            i, pt = self.to_page(ev.position(), page=self.shape_start[0] if self.shape_start else None)
            if self.shape_start is None:
                self.shape_start = (i, pt, ev.position())
                return
            self._finish_shape(ev)
            return
        if ev.button() == Qt.LeftButton and self.tool == "mark":
            i, pt = self.to_page(ev.position())
            it = dict(self.template)
            it.update({"type": "mark", "c": (pt.x(), pt.y()), "color": self.pen_color})
            if it["kind"] == "num":
                it["n"] = self.next_number()
            self._push_undo()
            self.items.setdefault(i, []).append(it)
            self.viewport().update()
            return
        if ev.button() == Qt.LeftButton and self.tool == "stamp":
            i, pt = self.to_page(ev.position())
            it = dict(self.template)
            it.update({"type": "stamp", "c": (pt.x(), pt.y())})
            QApplication.setOverrideCursor(Qt.WaitCursor)
            try:
                shifted = self._stamp_fit(i, it, autosize=True)
            except Exception:
                shifted = False
            finally:
                QApplication.restoreOverrideCursor()
            self._push_undo()
            self.items.setdefault(i, []).append(it)
            job = self.stamp_job
            self.set_tool("pan")
            self.selected = (i, len(self.items[i]) - 1)
            self.viewport().update()
            if job == "all":
                QTimer.singleShot(0, lambda: self.stamp_all_pages(i, it))
            else:
                self.status.emit(("" if self._stamp_clean else "אין בעמוד מקום פנוי לגמרי — החותמת הונחה במקום שמסתיר הכי פחות. ") +
                                 ("החותמת הוזזה למקום שלא מסתיר טקסט או שרטוט. " if shifted and self._stamp_clean else "") +
                                 "אפשר לגרור אותה, להגדיל או להקטין מהפינות ולסובב מהעיגול העליון")
            return
        if ev.button() == Qt.LeftButton and self.tool == "trafo":
            i, pt = self.to_page(ev.position())
            it = dict(self.template)
            it.update({"type": "trafo", "c": (pt.x(), pt.y()), "color": self.pen_color})
            self._push_undo()
            self.items.setdefault(i, []).append(it)
            self.set_tool("pan")
            self.selected = (i, len(self.items[i]) - 1)
            self.status.emit("אפשר לגרור את התחנה, להגדיל מהפינות, לסובב מהעיגול העליון (או R), ולשנות כמות בלחיצה כפולה")
            self.viewport().update()
            return
        if ev.button() == Qt.LeftButton and self.tool == "hole":
            i, pt = self.to_page(ev.position())
            it = dict(self.template)
            it.update({"type": "hole", "kind": self.hole_kind, "c": (pt.x(), pt.y()),
                       "color": self.pen_color})
            self._push_undo()
            self.items.setdefault(i, []).append(it)
            self.viewport().update()
            return
        if ev.button() == Qt.LeftButton and self.tool in ("dim", "calib"):
            if self.dim_start is None:
                self.dim_start = self.to_page(ev.position())
                return
            i, a = self.dim_start
            _, b = self.to_page(ev.position(), page=i)
            b = self._ortho(a, b, ev)
            self.dim_start = None
            self.ghost = None
            if math.hypot(b.x() - a.x(), b.y() - a.y()) < 0.5:
                return
            if self.tool == "calib":
                self._finish_calib(i, a, b)
                return
            self._push_undo()
            self.items.setdefault(i, []).append({"type": "dim", "p1": (a.x(), a.y()), "p2": (b.x(), b.y()),
                                                 "color": self.pen_color})
            self.viewport().update()
            return
        if ev.button() == Qt.LeftButton and self.tool == "pan" and self._handle_at(ev.position()):
            i, idx, hh = self._handle_at(ev.position())
            self._resize = (i, idx, hh, dict(self.items[i][idx]), False)
            return
        if ev.button() == Qt.LeftButton and self.tool == "pan":
            h = self._hit_item(ev.position())
            if h:
                self.selected = h
                i, pt = self.to_page(ev.position(), page=h[0])
                self._move = (pt, False)
                self.viewport().update()
                return
            if self.selected:
                self.selected = None
                self.viewport().update()
        if ev.button() in (Qt.LeftButton, Qt.MiddleButton):
            self._drag = (ev.position(), self.horizontalScrollBar().value(),
                          self.verticalScrollBar().value())
            self.viewport().setCursor(Qt.ClosedHandCursor)
            ev.accept()

    def mouseMoveEvent(self, ev):
        if self.tool == "erase_rect" and self._erase_drag and self.erase_rect:
            (kind, hh), p0, r0 = self._erase_drag
            i, _ = self.erase_rect
            _, pt = self.to_page(ev.position(), page=i)
            if kind == "in":
                self.erase_rect = (i, r0.translated(pt.x() - p0.x(), pt.y() - p0.y()))
            else:
                sx, sy = hh
                fx = r0.left() if sx > 0 else r0.right()
                fy = r0.top() if sy > 0 else r0.bottom()
                self.erase_rect = (i, QRectF(QPointF(fx, fy), pt).normalized())
            self.viewport().update()
            return
        if self.tool == "erase_rect" and self.erase_rect:
            h = self._erase_rect_hit(ev.position())
            if h and h[0] == "h":
                self.viewport().setCursor(Qt.SizeFDiagCursor if h[1][0] * h[1][1] > 0 else Qt.SizeBDiagCursor)
            else:
                self.viewport().setCursor(Qt.SizeAllCursor if h else Qt.CrossCursor)
        if self.select_mode:
            if self._sel:
                self._sel = (self._sel[0], self._content_pt(ev.position()))
                self.viewport().update()
            return
        if self._drag:
            p0, h0, v0 = self._drag
            d = ev.position() - p0
            self.horizontalScrollBar().setValue(int(h0 - d.x()))
            self.verticalScrollBar().setValue(int(v0 - d.y()))
            return
        if not self.sizes:
            return
        if self._stroke:
            i, it = self._stroke
            _, pt = self.to_page(ev.position(), page=i)
            lx, ly = it["pts"][-1]
            if (pt.x() - lx) ** 2 + (pt.y() - ly) ** 2 >= (0.6 / self.zoom) ** 2:
                it["pts"].append((pt.x(), pt.y()))
                self.viewport().update()
            return
        if self.tool == "erase":
            self._cursor_pt = ev.position()
            if self._erasing:
                self._erase_at(ev.position())
            self.viewport().update()
            return
        if self._resize:
            i, idx, hh, orig, started = self._resize
            if not started:
                self._push_undo()
                self._resize = (i, idx, hh, orig, True)
            _, pt = self.to_page(ev.position(), page=i)
            if hh[0] == "r":
                AX.apply_rotation_drag(self.items[i][idx], pt,
                                       snap=1.0 if ev.modifiers() & Qt.ShiftModifier else 5.0)
                self.status.emit(f"סיבוב {self.items[i][idx].get('angle', 0):g}°  (Shift = סיבוב חופשי)")
            elif AX.rotatable(orig) and orig.get("angle"):
                base = EXTRA[orig["type"]]["resize"] if orig["type"] in EXTRA else A.resize_trafo
                AX.rotated_resize(base, self.items[i][idx], orig, hh, pt)
            elif orig["type"] in EXTRA:
                EXTRA[orig["type"]]["resize"](self.items[i][idx], orig, hh, pt)
                if orig["type"] == "stamp":
                    # זוכרים את היחס שהמשתמש בחר מול הגודל האוטומטי — כך גם החותמת הבאה תצא בגודל שהוא אוהב
                    sl = self.items[i][idx].get("slot")
                    if isinstance(sl, int):
                        try:
                            ink = self._page_ink(i)
                            auto = stamps.auto_width_mm(sl, ink, 1.0)
                            QSettings("Tiktin", "TiktinPDF").setValue(
                                f"stamp_k{sl}", min(max(self.items[i][idx]["w"] / max(auto, 0.1), 0.3), 4.0))
                        except Exception:
                            pass
                elif orig["type"] == "mark":
                    QSettings("Tiktin", "TiktinPDF").setValue("mark_s", self.items[i][idx]["s"])
            elif orig["type"] == "text":
                A.resize_text(self.items[i][idx], orig, hh, pt)
            elif orig["type"] == "trafo":
                A.resize_trafo(self.items[i][idx], orig, hh, pt)
                QSettings("Tiktin", "TiktinPDF").setValue("trafo_w", self.items[i][idx]["w"])
            else:
                A.resize_hole(self.items[i][idx], orig, hh, pt, self.scale_of(i))
            self.viewport().update()
            return
        if self._move and self.selected:
            i, idx = self.selected
            _, pt = self.to_page(ev.position(), page=i)
            last, moved = self._move
            if not moved:
                self._push_undo()
            A.move(self.items[i][idx], pt.x() - last.x(), pt.y() - last.y())
            self._move = (pt, True)
            self.viewport().update()
            return
        if self.tool == "shape" and self.shape_start:
            i, a, _ = self.shape_start
            _, b = self.to_page(ev.position(), page=i)
            b = self._ortho(a, b, ev) if self.template["kind"] in ("line", "arrow", "arrow2") else b
            it = dict(self.template)
            it.update({"type": "shape", "p1": (a.x(), a.y()), "p2": (b.x(), b.y()), "color": self.pen_color,
                       "w": self.pen_w})
            self.ghost = (i, it)
            self.viewport().update()
            return
        if self.tool in ("mark", "stamp"):
            i, pt = self.to_page(ev.position())
            it = dict(self.template)
            it.update({"type": self.tool, "c": (pt.x(), pt.y())})
            it.setdefault("color", self.pen_color)
            if it.get("kind") == "num":
                it["n"] = self.next_number()
            self.ghost = (i, it)
            self.viewport().update()
            return
        if self.tool == "hole":
            i, pt = self.to_page(ev.position())
            it = dict(self.template)
            it.update({"type": "hole", "kind": self.hole_kind, "c": (pt.x(), pt.y())})
            self.ghost = (i, it)
            self.viewport().update()
        elif self.tool == "trafo":
            i, pt = self.to_page(ev.position())
            it = dict(self.template)
            it.update({"type": "trafo", "c": (pt.x(), pt.y())})
            self.ghost = (i, it)
            self.viewport().update()
        elif self.tool in ("dim", "calib") and self.dim_start:
            i, a = self.dim_start
            _, b = self.to_page(ev.position(), page=i)
            b = self._ortho(a, b, ev)
            self.ghost = (i, {"type": "dim", "p1": (a.x(), a.y()), "p2": (b.x(), b.y())})
            self.viewport().update()
        elif self.tool in ("pan", "text"):
            h = self._handle_at(ev.position())
            if h:
                self.viewport().setCursor(A.handle_cursor(self.items[h[0]][h[1]], h[2]))
            else:
                hit = self._hit_item(ev.position())
                if self.tool == "text":
                    hit = hit if hit and self.items[hit[0]][hit[1]]["type"] == "text" else None
                self.viewport().setCursor(Qt.SizeAllCursor if hit else
                                          (Qt.OpenHandCursor if self.tool == "pan" else Qt.IBeamCursor))

    def mouseReleaseEvent(self, ev):
        if self.tool == "erase_rect" and self._erase_drag:
            self._erase_drag = None
            if self.erase_rect:
                i, r = self.erase_rect
                r = r.normalized()
                if r.width() * self.zoom < 4 or r.height() * self.zoom < 4:
                    self.erase_rect = None
                else:
                    self.erase_rect = (i, r)
                    self.status.emit("אפשר לגרור את הפינות או להזיז את המלבן. Enter / Delete / לחיצה כפולה = מחיקה, "
                                     "Esc = ביטול")
            self.viewport().update()
            return
        if self.select_mode and self._sel and ev.button() == Qt.LeftButton:
            a, b = self._sel
            sr = QRectF(a, b).normalized()
            i = self.page_at(a.y())
            clip = self.page_clip(i, sr)
            self.cancel_select()
            if clip is not None:
                self.region_selected.emit(i, clip)
            else:
                self.select_cancelled.emit()
            return
        if self.tool == "shape" and self.shape_start and ev.button() == Qt.LeftButton:
            d = ev.position() - self.shape_start[2]
            if math.hypot(d.x(), d.y()) > 6:      # גרירה: הצורה נגמרת בשחרור
                self._finish_shape(ev)
                return
        if self._stroke:
            self._stroke = None
            self.dirty = True
            self.changed.emit()
        self._erasing = False
        self._move = None
        self._resize = None
        self._drag = None
        if self.tool == "pan":
            self.viewport().setCursor(Qt.OpenHandCursor if self.sizes else Qt.ArrowCursor)

    def mouseDoubleClickEvent(self, ev):
        if not self.sizes or ev.button() != Qt.LeftButton:
            return
        if self.tool == "erase_rect" and self.erase_rect and self._erase_rect_hit(ev.position()):
            self.apply_erase_rect()
            return
        if self.tool in ("pan", "text"):
            h = self._hit_item(ev.position())
            if h and (self.tool == "pan" or self.items[h[0]][h[1]]["type"] == "text"):
                self._move = None
                self.selected = h
                self.edit_selected()
                return
            if self.tool == "pan":
                self.set_zoom(self.zoom * 2, ev.position())

    def _finish_calib(self, i, a, b):
        L = math.hypot(b.x() - a.x(), b.y() - a.y())
        val, ok = QInputDialog.getDouble(self, "כיול קנה מידה",
                                         "מה האורך האמיתי של הקו שסימנתם, בס\"מ?",
                                         100.0, 0.1, 1e6, 1)
        self.set_tool("pan")
        if ok and val > 0:
            paper_mm = L / A.PT_PER_MM
            S = val * 10.0 / paper_mm
            self.set_scale(i, S)
            self.scale_changed.emit(S)
            self.status.emit(f"הקנ\"מ נקבע ל-1:{S:.4g}")

    def keyPressEvent(self, ev):
        k = ev.key()
        vs = self.verticalScrollBar()
        if k == Qt.Key_Escape and self.select_mode:
            self.cancel_select()
            self.window().statusBar().clearMessage()
            self.select_cancelled.emit()
        elif self.tool == "erase_rect" and self.erase_rect and k in (Qt.Key_Return, Qt.Key_Enter, Qt.Key_Delete):
            self.apply_erase_rect()
        elif k == Qt.Key_Escape and self.tool == "erase_rect" and self.erase_rect:
            self.erase_rect = None
            self.viewport().update()
        elif k == Qt.Key_Escape and self.tool == "pan" and not self.select_mode and self.window().isFullScreen():
            self.window()._toggle_full()
        elif k == Qt.Key_Escape and self.tool != "pan":
            if self.dim_start or self.shape_start:
                self.dim_start = None
                self.shape_start = None
                self.ghost = None
                self.viewport().update()
            else:
                self.set_tool("pan")
        elif k == Qt.Key_Escape and self.selected:
            self.selected = None
            self.viewport().update()
        elif k in (Qt.Key_Delete, Qt.Key_Backspace) and self.selected:
            self.delete_selected()
        elif k == Qt.Key_R and (self.tool == "hole" or self.selected):
            if self.tool == "hole":
                self.template["angle"] = (self.template.get("angle", 0) + 90) % 180
                if self.ghost:
                    self.ghost[1]["angle"] = self.template["angle"]
            else:
                i, idx = self.selected
                it = self.items[i][idx]
                if it["type"] == "hole":
                    self._push_undo()
                    it["angle"] = (it.get("angle", 0) + 90) % 180
                elif AX.rotatable(it):
                    self._push_undo()
                    it["angle"] = (it.get("angle", 0) + 90) % 360
            self.viewport().update()
        elif k in (Qt.Key_PageDown, Qt.Key_Space):
            vs.setValue(vs.value() + int(self.viewport().height() * 0.9))
        elif k == Qt.Key_PageUp:
            vs.setValue(vs.value() - int(self.viewport().height() * 0.9))
        elif k == Qt.Key_Home:
            vs.setValue(0)
        elif k == Qt.Key_End:
            vs.setValue(vs.maximum())
        else:
            super().keyPressEvent(ev)


# ---------------------------------------------------------------- main window
class MainWindow(QMainWindow):
    def __init__(self, pool):
        super().__init__()
        self.settings = QSettings("Tiktin", "TiktinPDF")
        self.setWindowTitle(f"{APP_NAME}   |   גרסה {VERSION} ({BUILD_DATE})")
        self.setAcceptDrops(True)
        self.view = PdfView(pool)
        self.setCentralWidget(self.view)
        self.view.page_changed.connect(self._on_page)
        self.view.zoom_changed.connect(self._on_zoom)
        self.view.tool_changed.connect(self._on_tool)
        self.view.changed.connect(self._on_changed)
        self.view.status.connect(lambda m: self.statusBar().showMessage(m, 6000))
        self.view.region_selected.connect(self._region)
        self.view.select_cancelled.connect(lambda: self.statusBar().clearMessage())
        self.view.scale_changed.connect(self._show_scale)
        self.tray = ClipTray(self.view)
        self.tray.message.connect(lambda m: self.statusBar().showMessage(m, 7000))
        self.view.tray = self.tray
        self._build_toolbar()
        self.view.wheel_zoom = False
        g = self.settings.value("geometry")
        if g is not None:
            self.restoreGeometry(g)
        else:
            self.resize(1280, 820)

    ICONS = {"פתיחה": "open", "קובץ": "file", "הדפסה": "print", "העתקה": "copy", "הוסף": "add", "חותמות": "stamp",
             "מחיקה מהשרטוט": "erase", "סיבוב": "rotate", "תצוגה": "view", "שמירת\nשינויים": "save"}
    LABELS = {"מחיקה מהשרטוט": "מחיקה\nמהשרטוט"}

    def _btn(self, text, tip, slot, primary=False, checkable=False, icon=None):
        b = RibbonButton(self.LABELS.get(text, text), tip, icon or self.ICONS.get(text), main=primary)
        b.setCheckable(checkable)
        if checkable:
            b.toggled.connect(slot)
        else:
            b.clicked.connect(slot)
        return b

    def _menu(self, parent):
        m = QMenu(parent)
        m.setLayoutDirection(Qt.RightToLeft)
        m.setToolTipsVisible(True)
        return m

    def _menu_btn(self, text, tip, menu, checkable=False):
        b = RibbonButton(self.LABELS.get(text, text) + " ▾", tip, self.ICONS.get(text))
        b.setCheckable(checkable)
        b.setPopupMode(QToolButton.InstantPopup)
        b.setMenu(menu)
        return b

    @staticmethod
    def _act(menu, text, slot, tip=None, shortcut=None):
        a = menu.addAction(text)
        a.triggered.connect(lambda _=False: slot())
        if tip:
            a.setToolTip(tip)
        if shortcut:
            a.setShortcut(QKeySequence(shortcut))
            a.setShortcutVisibleInContextMenu(True)
        return a

    def _build_toolbar(self):
        # ----- שורה עליונה (כמו בשאר אפליקציות טיקטין): לוגו, שם, גרסה, ובצד שמאל כפתורי הגודל
        hd = QToolBar()
        hd.setObjectName("hdr")
        tb = QToolBar()
        tb.setObjectName("ribbon")
        for t_ in (hd, tb):
            t_.setMovable(False)
            t_.setFloatable(False)
            t_.setContextMenuPolicy(Qt.PreventContextMenu)
        self.addToolBar(Qt.TopToolBarArea, hd)
        self.addToolBarBreak(Qt.TopToolBarArea)
        self.addToolBar(Qt.TopToolBarArea, tb)
        self.hdr_bar, self.ribbon_bar = hd, tb
        logo = QLabel()
        pm = QPixmap()
        pm.loadFromData(base64.b64decode(LOGO_B64))
        logo.setPixmap(pm.scaledToHeight(34, Qt.SmoothTransformation))
        hd.addWidget(logo)
        ttl = QLabel(APP_NAME)
        ttl.setObjectName("apptitle")
        hd.addWidget(ttl)
        self.file_lbl = QLabel("")
        self.file_lbl.setObjectName("filename")
        hd.addWidget(self.file_lbl)
        hver = QLabel(f"גרסה {VERSION} · עודכן {BUILD_DATE}")
        hver.setObjectName("hver")
        hd.addWidget(hver)
        hsp = QWidget()
        hsp.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        hd.addWidget(hsp)
        self._hdr = hd
        tb.addWidget(self._btn("פתיחה", "פתיחת קובץ PDF (Ctrl+O)", self.open_dialog, primary=True))
        tb.addSeparator()
        tb.addWidget(self._btn("שמירת\nשינויים", "שומר את התוספות ואת מחיקת העמודים בתוך הקובץ הפתוח (Ctrl+S)",
                               self.save_changes))

        # ----- קובץ
        fm = self._menu(self)
        self._act(fm, "פתיחת קובץ...", self.open_dialog, shortcut="Ctrl+O")
        self._act(fm, "שמירת שינויים", self.save_changes,
                  "שומר את התוספות ואת מחיקת העמודים בתוך הקובץ הפתוח", "Ctrl+S")
        self._act(fm, "שמירה בשם...", self.save_as, "שמירה כקובץ PDF חדש, והקובץ המקורי נשאר כמו שהוא",
                  "Ctrl+Shift+S")
        fm.addSeparator()
        self._act(fm, "מחיקת עמודים...", self.delete_pages_dialog,
                  "מחיקת העמוד הנוכחי או טווח עמודים. אפשר לבטל עד השמירה")
        tb.addWidget(self._menu_btn("קובץ", "פתיחה, שמירה ומחיקת עמודים", fm))
        self.print_btn = self._btn("הדפסה", "הדפסה בנייר — כל הקובץ, עמוד, מסך או חלון נבחר (Ctrl+P).\n"
                                            "בזמן בחירת חלון להדפסה הכפתור אדום; לחיצה נוספת או Esc מבטלים",
                                   self._print_clicked)
        self.print_btn.setCheckable(True)
        tb.addWidget(self.print_btn)
        self.copy_btn = self._btn("העתקה", "גוררים מלבן על השרטוט: הקטע נקלט באיכות מלאה (PDF וקטורי),\n"
                                           "מועתק להדבקה ונשמר במגש בפינה — עד 2 קטעים (Ctrl+Shift+C).\n"
                                           "בזמן הבחירה הכפתור אדום; לחיצה נוספת או Esc מבטלים",
                                  self._copy_clicked)
        self.copy_btn.setCheckable(True)
        tb.addWidget(self.copy_btn)
        tb.addSeparator()

        # ----- הוסף
        am = self._menu(self)
        self.add_menu = am
        hm = am.addMenu("חור")
        for kind, kname in (("floor", "חור ברצפה"), ("ceil", "חור בתקרה"), ("wall", "חור בקיר")):
            sm = hm.addMenu(kname)
            for shp, sname in (("round", "עגול"), ("rect", "מלבני"), ("square", "מרובע")):
                self._act(sm, sname, lambda k=kind, sh=shp: self._add_hole(k, sh),
                          "מגדירים מידות ואז מקליקים על השרטוט. R מסובב 90°")
        tm = am.addMenu("תחנת שנאים")
        for n, t in ((1, "שנאי 1"), (2, "2 שנאים"), (3, "3 שנאים")):
            self._act(tm, t, lambda n=n: self._add_trafo(n), "מקליקים על השרטוט במקום התחנה. גרירת פינה מגדילה")
        am.addSeparator()
        lm = am.addMenu("קווים וצורות")
        for k in ("line", "arrow", "arrow2"):
            self._act(lm, SHAPE_NAMES[k], lambda k=k: self._add_shape(k),
                      "גוררים מנקודה לנקודה (או שתי הקלקות). Shift = קו ישר")
        lm.addSeparator()
        for k in ("rect", "ellipse", "cloud"):
            self._act(lm, SHAPE_NAMES[k], lambda k=k: self._add_shape(k), "גוררים מפינה לפינה")
        mm = am.addMenu("סימנים")
        for k in ("x", "v", "q", "num"):
            self._act(mm, MARK_NAMES[k], lambda k=k: self._add_mark(k),
                      "מקליקים במקום הסימן — אפשר כמה ברצף. Esc מסיים" if k != "num" else
                      "כל הקלקה מוסיפה את המספר הבא: 1, 2, 3... Esc מסיים")
        self._act(am, "טקסט", lambda: self._tool_clicked("text", True),
                  "מקליקים במקום שבו יתחיל הטקסט (מימין), וכותבים בעברית")
        am.addSeparator()
        self._act(am, "עט חופשי", lambda: self._tool_clicked("pen", True), "ציור חופשי בצבע ובעובי שנבחרו")
        self._act(am, "מחק עט", lambda: self._tool_clicked("erase", True),
                  "מעבירים על קווי העט כדי למחוק אותם")
        sm = self._menu(self)
        self.stamp_menu = sm
        # התפריט נבנה מראש ומתעדכן רק אחרי הוספה או הסרה של חותמת —
        # בנייה מחדש בזמן שהתפריט נפתח משאירה ב-Windows תפריט ריק
        self._fill_stamp_menu()
        self.add_btn = self._menu_btn("הוסף", "הוספה לשרטוט: חורים, תחנת שנאים, קווים, חצים, צורות, סימנים, "
                                              "טקסט ועט", am, checkable=True)
        tb.addWidget(self.add_btn)
        self.add_btn.installEventFilter(self)

        self.stamp_btn = self._menu_btn("חותמות", "חותמת טיקטין, חותמת לוחות וחותמות נוספות — בעמוד הנוכחי או בכל העמודים. "
                                                  "הגודל מותאם לכתב שבשרטוט, והמקום נבחר כך שלא יסתיר טקסט או קווים",
                                        sm, checkable=True)
        self.stamp_btn.installEventFilter(self)
        tb.addWidget(self.stamp_btn)

        # ----- מחיקה מהשרטוט המקורי
        em = self._menu(self)
        self._act(em, "פריט בודד (קו או מילה)", lambda: self._erase_mode("erase_item"),
                  "מקליקים על קו או על מילה בשרטוט — הם נמחקים מהקובץ המקורי. אפשר כמה ברצף")
        self._act(em, "מלבן (אזור)", lambda: self._erase_mode("erase_rect"),
                  "גוררים מלבן, מכוונים את גודלו בפינות, ו-Enter מוחק את כל מה שבתוכו")
        self.erase_btn = self._menu_btn("מחיקה מהשרטוט", "מחיקת קווים, טקסט או אזור מהשרטוט המקורי עצמו "
                                                         "(לא רק מהסימונים). UNDO מחזיר", em, checkable=True)
        self.erase_btn.installEventFilter(self)
        tb.addWidget(self.erase_btn)

        # ----- מדידה
        mm2 = self._menu(self)
        self._act(mm2, "מדידת מרחק", lambda: self._tool_clicked("dim", True),
                  "מקליקים נקודת התחלה ונקודת סיום. Shift = קו ישר. התוצאה בס\"מ לפי הקנ\"מ")
        self._act(mm2, "כיול לפי קו באורך ידוע", lambda: self._tool_clicked("calib", True),
                  "מסמנים קו שאורכו ידוע ומקלידים את אורכו האמיתי — הקנ\"מ יחושב")
        self._act(mm2, "בדיקת קנ\"מ מחדש מול המידות", self._reanalyze,
                  "מבטל קנ\"מ שנקבע ידנית בעמוד ובודק שוב לפי הכיתוב והמידות בשרטוט")
        mb = RibbonButton("מדידה", "לחיצה: מתחילים למדוד (שתי הקלקות על השרטוט, התוצאה בס\"מ).\n"
                          "לחיצה נוספת או Esc: מפסיקים.  החץ הקטן שבצד: כיול, בדיקת קנ\"מ וקנה מידה לעמוד", "ruler")
        mb.setCheckable(True)
        mb.setPopupMode(QToolButton.MenuButtonPopup)
        mb.setMenu(mm2)
        mb.clicked.connect(self._measure_toggle)
        mb.setMinimumWidth(74)
        self.measure_btn = mb
        tb.addWidget(self.measure_btn)
        tb.addSeparator()
        self.scale_box = QComboBox()
        self.scale_box.setEditable(True)
        self.scale_box.setInsertPolicy(QComboBox.NoInsert)
        self.scale_box.addItems(["1:20", "1:25", "1:50", "1:100", "1:200", "1:250", "1:500"])
        self.scale_box.setFixedWidth(68)
        self.scale_box.lineEdit().setAlignment(Qt.AlignCenter)
        self.scale_box.setToolTip("קנה המידה של העמוד הנוכחי — מזוהה ומאומת אוטומטית. אפשר לבחור או להקליד, למשל 1:50")
        self.scale_box.textActivated.connect(self._scale_text)
        # הקנ"מ עבר לתפריט "מדידה" (והוא מוצג בפינת השרטוט) — כדי שהסרגל ייכנס בשורה אחת
        scm = mm2.addMenu("קנה מידה לעמוד")
        for t_ in ("1:20", "1:25", "1:50", "1:75", "1:100", "1:200", "1:250", "1:500"):
            self._act(scm, t_, lambda t_=t_: self._scale_text(t_))
        scm.addSeparator()
        self._act(scm, "קנ\"מ אחר...", self._scale_other)

        # ----- עריכה וצבע
        tb.addWidget(self._btn("ביטול\nפעולה", "UNDO — ביטול הפעולה האחרונה (Ctrl+Z)", self.view.do_undo, icon="undo"))
        tb.addWidget(self._btn("החזרת\nפעולה", "REDO — חזרה על הפעולה שבוטלה (Ctrl+Y)", self.view.do_redo, icon="redo"))
        self.del_btn = self._btn("מחיקת\nסימון", "מחיקת הסימון שנבחר (Delete)", self.view.delete_selected, icon="x")
        tb.addWidget(self.del_btn)
        self.color_btn = ColorButton(self.view.pen_color)
        self.color_btn.setObjectName("rb")
        self.color_btn.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
        self.color_btn.setIconSize(QSize(24, 24))
        self.color_btn.setFocusPolicy(Qt.NoFocus)
        self.color_btn.fixed_text = "צבע"
        self.color_btn.setText("צבע")
        self.color_btn.changed.connect(self._pen_color)
        tb.addWidget(self.color_btn)
        self.width_box = QComboBox()
        for t_, v_ in (("קו 0.25", 0.25), ("קו 0.5", 0.5), ("קו 1", 1.0), ("קו 2", 2.0), ("קו 4", 4.0)):
            self.width_box.addItem(t_, v_)
        self.width_box.setCurrentIndex(min(range(5), key=lambda k: abs(self.width_box.itemData(k) - self.view.pen_w)))
        self.width_box.setToolTip("עובי הקו במ\"מ על הנייר — לעט, לקווים ולצורות")
        self.width_box.setFixedWidth(84)
        self.width_box.setFocusPolicy(Qt.NoFocus)
        self.width_box.currentIndexChanged.connect(self._pen_width)
        self.width_act = tb.addWidget(self.width_box)
        self.tsize_box = QComboBox()
        for t_, v_ in (("אות 2.5", 2.5), ("אות 3.5", 3.5), ("אות 5", 5.0), ("אות 7", 7.0), ("אות 10", 10.0)):
            self.tsize_box.addItem(t_, v_)
        self.tsize_box.setCurrentIndex(min(range(5), key=lambda k: abs(self.tsize_box.itemData(k) - self.view.text_size)))
        self.tsize_box.setToolTip("גובה האות במ\"מ על הנייר. אפשר גם לגרור את פינות המסגרת")
        self.tsize_box.setFixedWidth(84)
        self.tsize_box.setFocusPolicy(Qt.NoFocus)
        self.tsize_box.currentIndexChanged.connect(self._text_size)
        self.tsize_act = tb.addWidget(self.tsize_box)

        tb.addSeparator()

        # ----- סיבוב ועמוד
        plbl = QLabel("עמוד")
        plbl.setObjectName("pagelbl")
        self.page_edit = QLineEdit()
        self.page_edit.setFixedWidth(40)
        self.page_edit.setAlignment(Qt.AlignCenter)
        self.page_edit.setToolTip("מספר עמוד — הקלידו ולחצו Enter")
        self.page_edit.returnPressed.connect(self._goto_page)
        self.page_total = QLabel(" / – ")
        self.page_total.setObjectName("pagelbl")
        rm = self._menu(self)
        for scope, title in (("page", "העמוד הנוכחי"), ("all", "כל העמודים")):
            sm = rm.addMenu(title)
            for mode, cw, text, tip in (
                    ("rot", True, "↻ 90° עם כיוון השעון", "רבע סיבוב ימינה"),
                    ("rot", False, "↺ 90° נגד כיוון השעון", "רבע סיבוב שמאלה"),
                    ("180", True, "היפוך 180°", "הופך עמוד שעומד הפוך"),
                    (None, None, None, None),
                    ("portrait", True, "לאורך", "העמוד יעמוד לאורך, והטקסט בשרטוט ישר וקריא"),
                    ("landscape", True, "לרוחב", "העמוד יעמוד לרוחב, והטקסט בשרטוט ישר וקריא"),
                    ("upright", True, "טקסט ישר", "מסובב כך שהטקסט בשרטוט יעמוד ישר וקריא")):
                if mode is None:
                    sm.addSeparator()
                    continue
                self._act(sm, text, lambda s_=scope, m_=mode, c_=cw: self.rotate_pages(s_, m_, c_), tip)
        self.rotate_menu = rm
        self.rotate_btn = self._menu_btn("סיבוב", "סיבוב העמוד הנוכחי או כל העמודים: 90°, 180°, לאורך, לרוחב "
                                                   "או טקסט ישר (Ctrl+R)", rm)
        tb.addWidget(self.rotate_btn)
        tb.addWidget(plbl)
        tb.addWidget(self.page_edit)
        tb.addWidget(self.page_total)
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        tb.addWidget(spacer)

        # ----- כפתורי הגודל, בשורה העליונה בצד שמאל (לא משפיעים על שום דבר מחוץ לתוכנה)
        def fz(text, tip, fn):
            b_ = QToolButton()
            b_.setObjectName("fz")
            b_.setText(text)
            b_.setToolTip(tip)
            b_.setFocusPolicy(Qt.NoFocus)
            b_.clicked.connect(fn)
            return b_
        for w_ in (logo, ttl, self.file_lbl, hver):
            w_.setContentsMargins(0, 0, 14, 0)
        zg = QWidget()
        zl = QHBoxLayout(zg)
        zl.setContentsMargins(0, 0, 0, 0)
        zl.setSpacing(0)
        zl.addWidget(fz("−", "הקטנה (Ctrl+-)", lambda: self.view.set_zoom(self.view.zoom / 1.25)))
        self.zoom_box = QComboBox()
        self.zoom_box.setEditable(True)
        self.zoom_box.setInsertPolicy(QComboBox.NoInsert)
        self.zoom_box.addItems(["25%", "50%", "75%", "100%", "150%", "200%", "400%", "800%", "1600%"])
        self.zoom_box.setFixedWidth(70)
        self.zoom_box.setToolTip("אחוז ההגדלה של השרטוט — בחרו או הקלידו")
        self.zoom_box.lineEdit().setAlignment(Qt.AlignCenter)
        self.zoom_box.setStyleSheet("QComboBox { border-radius: 0; margin-left: -1px; }")
        self.zoom_box.textActivated.connect(self._zoom_text)
        zl.addWidget(self.zoom_box)
        zl.addWidget(fz("+", "הגדלה (Ctrl++)", lambda: self.view.set_zoom(self.view.zoom * 1.25)))
        zl.addWidget(fz("התאמה למסך", "הצגת העמוד כולו במסך (Ctrl+0)", self.view.fit_page))
        zl.addWidget(fz("התאמה לרוחב", "העמוד ממלא את רוחב החלון (Ctrl+2)", self.view.fit_width))
        hd.addWidget(zg)
        vm = self._menu(self)
        self._act(vm, "התאמה לרוחב", self.view.fit_width, shortcut="Ctrl+2")
        self._act(vm, "עמוד מלא", self.view.fit_page, shortcut="Ctrl+0")
        self._act(vm, "גודל אמיתי 100%", lambda: self.view.set_zoom(1.0), shortcut="Ctrl+1")
        vm.addSeparator()
        self.wheel_act = vm.addAction("גלגלת העכבר = זום")
        self.wheel_act.setCheckable(True)
        self.wheel_act.setToolTip("כשמסומן: הגלגלת מגדילה ומקטינה כמו באוטוקד, ו-Ctrl+גלגלת גולל")
        self.wheel_act.toggled.connect(self._wheel_mode)
        self._act(vm, "מסך מלא", self._toggle_full, shortcut="F11")
        vm.addSeparator()
        self._act(vm, "הוראות הפעלה", self.show_help, shortcut="F1")
        tb.addSeparator()
        tb.addWidget(self._menu_btn("תצוגה", "התאמה לרוחב, 100%, מצב גלגלת ומסך מלא", vm))
        tb.addWidget(self._btn("מסך מלא", "השרטוט על כל המסך, בלי הסרגלים (F11). Esc או F11 חוזרים", self._toggle_full,
                               icon="full"))
        tb.addWidget(self._btn("הוראות\nF1", "הוראות ההפעלה של התוכנה (F1)", self.show_help, icon="help"))
        tb.addWidget(self._btn("אפליקציה\nראשית", "פתיחת האפליקציה הראשית של טיקטין בדפדפן", self._open_portal,
                               icon="home"))
        ver = QLabel(f" גרסה {VERSION} | {BUILD_DATE} ")
        ver.setObjectName("ver")
        ver.setToolTip(f"גרסה {VERSION}, עודכנה {BUILD_DATE}. F1 = הוראות הפעלה")
        self.statusBar().addPermanentWidget(ver)

        self.tool_btns = {}
        self.ctx_timer = QTimer(self, interval=200)
        self.ctx_timer.timeout.connect(self._sync_ctx)
        self.ctx_timer.start()
        self._sync_ctx()

        for seq, fn in ((QKeySequence.Open, self.open_dialog),
                        (QKeySequence.Print, self.print_dialog),
                        (QKeySequence.Save, self.save_changes),
                        ("Ctrl+Shift+S", self.save_as),
                        ("Ctrl+Y", self.view.do_redo),
                        ("Ctrl+Shift+Z", self.view.do_redo),
                        ("Ctrl+Shift+C", self.copy_window),
                        (QKeySequence.Undo, self.view.do_undo),
                        ("Ctrl+=", lambda: self.view.set_zoom(self.view.zoom * 1.25)),
                        ("Ctrl++", lambda: self.view.set_zoom(self.view.zoom * 1.25)),
                        ("Ctrl+-", lambda: self.view.set_zoom(self.view.zoom / 1.25)),
                        ("Ctrl+0", self.view.fit_page),
                        ("Ctrl+2", self.view.fit_width),
                        ("Ctrl+1", lambda: self.view.set_zoom(1.0)),
                        ("F11", self._toggle_full),
                        ("F1", self.show_help),
                        ("Ctrl+R", lambda: self.rotate_btn.showMenu())):
            QShortcut(QKeySequence(seq), self, activated=fn)

    # ----- תפריט הוסף
    def _need_doc(self):
        if not self.view.sizes:
            QMessageBox.information(self, APP_NAME, "קודם פותחים קובץ PDF.")
            return False
        return True

    def _add_hole(self, kind, shape):
        if not self._need_doc():
            return
        v = self.view
        v.scale_of(max(0, v._cur_page))
        from hole_dialog import HoleDialog
        dlg = HoleDialog(self, kind, shape=shape)
        if dlg.exec() != QDialog.Accepted:
            v.set_tool("pan")
            return
        v.hole_kind = kind
        v.set_tool("hole", dict(dlg.result_dims))
        self.statusBar().showMessage("מקליקים על השרטוט במקום החור. R מסובב, Esc או לחצן ימני מסיימים")
        v.setFocus()

    def _add_trafo(self, n):
        if not self._need_doc():
            return
        w = self.settings.value("trafo_w", 14.0, type=float)
        self.view.set_tool("trafo", {"n": n, "w": w})
        self.statusBar().showMessage("מקליקים על השרטוט במקום תחנת השנאים. Esc מבטל")
        self.view.setFocus()

    def _add_shape(self, kind):
        if not self._need_doc():
            return
        self.view.set_tool("shape", {"kind": kind})
        self.statusBar().showMessage(f"{SHAPE_NAMES[kind]}: גוררים על השרטוט (או מקליקים התחלה וסוף). "
                                     "Shift = ישר. Esc מסיים")
        self.view.setFocus()

    def _add_mark(self, kind):
        if not self._need_doc():
            return
        s = self.settings.value("mark_s", 6.0, type=float)
        self.view.set_tool("mark", {"kind": kind, "s": s})
        self.statusBar().showMessage("מקליקים במקום הסימן — אפשר כמה ברצף. Esc או לחצן ימני מסיימים")
        self.view.setFocus()

    def _fill_stamp_menu(self):
        """תפריט החותמות: 2 קבועות + עד 2 נוספות. כל חותמת נפתחת לתפריט צבע ומיקום (בלי חלונות בחירה)."""
        sm = self.stamp_menu
        for a_ in sm.actions():
            if a_.menu():
                a_.menu().deleteLater()
        sm.clear()
        for slot in stamps.FIXED + stamps.CUSTOM:
            if not stamps.has(slot):
                continue
            title = stamps.name(slot) + ("  (עם תאריך)" if stamps.date_pos(slot) else "")
            m = QMenu(title, sm)
            m.setLayoutDirection(Qt.RightToLeft)
            m.menuAction().setText(title)
            m.menuAction().setToolTip(title)
            sm.addMenu(m)
            for color, cname in (("#d0021b", "אדום"), ("#000000", "שחור")):
                for where, wname in (("page", "בעמוד הנוכחי"), ("all", "בכל העמודים")):
                    self._act(m, f"{cname} – {wname}",
                              lambda s_=slot, c_=color, w_=where: self._add_stamp(s_, c_, w_),
                              "מקליקים על השרטוט במקום החותמת" + (
                                  ". בשאר העמודים היא תונח במקום פנוי מטקסט, קרוב לאותו מקום" if where == "all" else ""))
            if slot in stamps.CUSTOM:
                m.addSeparator()
                self._act(m, "הסרת החותמת", lambda s_=slot: self._remove_stamp(s_))
        sm.addSeparator()
        a = self._act(sm, "הוספת חותמת נוספת...", self._new_stamp,
                      "מתמונה (PNG/JPG) או מקובץ PDF, עם שם שנשמר עד שמסירים אותה. עד 2 חותמות נוספות")
        a.setEnabled(stamps.free_custom_slot() is not None)

    def _new_stamp(self):
        slot = stamps.free_custom_slot()
        if slot is None:
            QMessageBox.information(self, APP_NAME, "כבר יש 2 חותמות נוספות. כדי להוסיף, קודם מסירים אחת מהן.")
            return
        d = self.settings.value("stamp_dir", self.settings.value("last_dir", ""))
        path, _ = QFileDialog.getOpenFileName(self, "קובץ החותמת", d,
                                              "תמונה או PDF (*.png *.jpg *.jpeg *.bmp *.gif *.pdf)")
        if not path:
            return
        self.settings.setValue("stamp_dir", os.path.dirname(path))
        base = os.path.splitext(os.path.basename(path))[0]
        nm, ok = QInputDialog.getText(self, "שם החותמת", "שם החותמת (יישמר עד שמסירים אותה):",
                                      QLineEdit.Normal, base)
        if not ok:
            return
        nm = nm.strip() or base
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            ok = stamps.load_file(slot, path, nm)
        except Exception:
            ok = False
        finally:
            QApplication.restoreOverrideCursor()
        if not ok:
            QMessageBox.warning(self, APP_NAME, "לא נמצאה חותמת בקובץ. בוחרים תמונה או PDF של החותמת על רקע לבן או שקוף.")
            return
        self._fill_stamp_menu()
        self.statusBar().showMessage(f"החותמת \"{nm}\" נוספה לתפריט החותמות", 6000)

    def _remove_stamp(self, slot):
        nm = stamps.name(slot)
        if QMessageBox.question(self, APP_NAME, f"להסיר את החותמת \"{nm}\" מהתפריט?\n"
                                "חותמות שכבר הונחו על שרטוטים לא נמחקות.") != QMessageBox.Yes:
            return
        stamps.remove(slot)
        self._fill_stamp_menu()
        self.statusBar().showMessage(f"החותמת \"{nm}\" הוסרה", 5000)

    def _add_stamp(self, slot, color, where):
        if not self._need_doc():
            return
        v = self.view
        # הגודל נקבע לפי הכתב שבשרטוט (ובעמוד בלי טקסט — לפי גודל הדף), ומחושב שוב בעמוד שבו מקליקים
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            w = v.stamp_auto_w(max(0, v._cur_page), slot)
        except Exception:
            w = 30.0
        finally:
            QApplication.restoreOverrideCursor()
        tpl = {"slot": slot, "w": w, "ar": stamps.aspect(slot), "color": color}
        dp = stamps.date_pos(slot)
        if dp:
            from datetime import date
            tpl["date"] = date.today().strftime("%d/%m/%Y")
            tpl["datepos"] = list(dp)
        v.set_tool("stamp", tpl)
        v.stamp_job = where
        self.statusBar().showMessage("מקליקים על השרטוט במקום החותמת — אם המקום תפוס, היא תונח במקום הפנוי הקרוב. Esc מבטל")
        v.setFocus()

    def _measure_toggle(self):
        if self.view.tool in ("dim", "calib"):
            self.view.set_tool("pan")
        else:
            self._tool_clicked("dim", True)
            if self.view.tool != "dim":
                self._on_tool(self.view.tool)

    def _reanalyze(self):
        if self._need_doc():
            self.view.reanalyze()
            self._show_scale()

    ADD_TOOLS = ("hole", "pen", "erase", "text", "trafo", "shape", "mark")

    def eventFilter(self, obj, ev):
        # כשכלי הוספה פעיל, לחיצה על "הוסף" מפסיקה אותו (במקום לפתוח שוב את התפריט)
        if ev.type() == QEvent.MouseButtonPress and (
                (obj is getattr(self, "add_btn", None) and self.view.tool in self.ADD_TOOLS) or
                (obj is getattr(self, "stamp_btn", None) and self.view.tool == "stamp") or
                (obj is getattr(self, "erase_btn", None) and self.view.tool in ("erase_item", "erase_rect"))):
            self.view.set_tool("pan")
            self.statusBar().clearMessage()
            return True
        return super().eventFilter(obj, ev)

    def _erase_mode(self, tool):
        if not self._need_doc():
            return
        self.view.set_tool(tool)
        if tool == "erase_item":
            self.statusBar().showMessage("מחיקה מהשרטוט: מקליקים על קו או על מילה. Esc או לחיצה על הכפתור מסיימים")
        else:
            self.statusBar().showMessage("מחיקה מהשרטוט: גוררים מלבן סביב מה שרוצים למחוק. Esc או לחיצה על הכפתור מסיימים")
        self.view.setFocus()

    def _copy_clicked(self):
        v = self.view
        if v.select_mode and v.select_purpose == "copy":
            v.cancel_select()
            self.statusBar().clearMessage()
        else:
            self.copy_window()
        self._sync_ctx()

    def _print_clicked(self):
        v = self.view
        if v.select_mode and v.select_purpose == "print":
            v.cancel_select()
            v.select_cancelled.emit()
            self.statusBar().clearMessage()
        else:
            self.print_dialog()
        self._sync_ctx()

    def _sync_ctx(self):
        """מציג את עובי הקו ואת גודל האות רק כשהם רלוונטיים, כדי שהסרגל יישאר נקי."""
        v = self.view
        sel_t = None
        if v.selected and v.selected[1] < len(v.items.get(v.selected[0], [])):
            sel_t = v.items[v.selected[0]][v.selected[1]]["type"]
        self.width_act.setVisible(v.tool in ("pen", "shape") or sel_t in ("ink", "shape"))
        self.tsize_act.setVisible(v.tool == "text" or sel_t == "text" or v.editing is not None)
        # כפתור של פעולה פעילה נצבע באדום
        for b, on in ((getattr(self, "copy_btn", None), v.select_mode and v.select_purpose == "copy"),
                      (getattr(self, "print_btn", None), v.select_mode and v.select_purpose == "print"),
                      (getattr(self, "add_btn", None), v.tool in self.ADD_TOOLS),
                      (getattr(self, "measure_btn", None), v.tool in ("dim", "calib")),
                      (getattr(self, "stamp_btn", None), v.tool == "stamp"),
                      (getattr(self, "erase_btn", None), v.tool in ("erase_item", "erase_rect"))):
            if b is None:
                continue
            if b.isChecked() != bool(on):
                b.blockSignals(True)
                b.setChecked(bool(on))
                b.blockSignals(False)
            if b.property("active") != bool(on):
                # סגנון ישיר על הכפתור: אדום בוודאות, גם כשהעכבר מעליו או כשהוא בפוקוס
                b.setProperty("active", bool(on))
                b.setStyleSheet(ACTIVE_BTN_CSS if on else "")
                if hasattr(b, "set_active"):
                    b.set_active(bool(on))

    def show_help(self):
        if getattr(self, "_help", None) is not None:
            self._help.raise_()
            self._help.activateWindow()
            return
        from help import HelpDialog
        self._help = HelpDialog(self, f"גרסה {VERSION} | {BUILD_DATE}")
        self._help.destroyed.connect(lambda *_: setattr(self, "_help", None))
        self._help.show()

    def _toggle_full(self):
        """מסך מלא: רק השרטוט, בלי הסרגלים. Esc או F11 חוזרים."""
        full = not self.isFullScreen()
        if full:
            self._was_max = self.isMaximized()
            self.showFullScreen()
        else:
            self.showMaximized() if getattr(self, "_was_max", False) else self.showNormal()
        for w_ in (self.hdr_bar, self.ribbon_bar, self.statusBar()):
            w_.setVisible(not full)
        if full:
            if getattr(self, "_exit_full", None) is None:
                b = QToolButton(self.view)
                b.setText("יציאה ממסך מלא  (Esc)")
                b.setStyleSheet("QToolButton { background: rgba(255,255,255,235); color: #1f2328; border: 1px solid #c8202f;"
                                " border-radius: 8px; padding: 6px 12px; font-size: 10pt; }"
                                "QToolButton:hover { background: #c8202f; color: #ffffff; }")
                b.clicked.connect(self._toggle_full)
                self._exit_full = b
            self._exit_full.adjustSize()
            self._exit_full.move(10, 10)
            self._exit_full.show()
            self._exit_full.raise_()
        elif getattr(self, "_exit_full", None) is not None:
            self._exit_full.hide()
        self.view.setFocus()

    def _open_portal(self):
        from PySide6.QtGui import QDesktopServices
        from PySide6.QtCore import QUrl
        QDesktopServices.openUrl(QUrl("https://tiktiny.github.io/tiktin-tools/"))

    def _wheel_mode(self, on):
        self.view.wheel_zoom = on

    def _zoom_text(self, t):
        try:
            v = float(t.replace("%", "").strip())
            self.view.set_zoom(v / 100.0)
        except ValueError:
            self._on_zoom(self.view.zoom)

    def _on_zoom(self, z):
        self.zoom_box.setEditText(f"{z * 100:.0f}%")

    def _on_page(self, i, n):
        self._show_scale()
        self.page_edit.setText(str(i + 1))
        self.page_total.setText(f" / {n} ")

    def _goto_page(self):
        try:
            self.view.go_page(int(self.page_edit.text()) - 1)
            self.view.setFocus()
        except ValueError:
            pass

    # ----- tools
    def _tool_clicked(self, key, on):
        v = self.view
        if not self._need_doc():
            return
        if not on:
            v.set_tool("pan")
            return
        v.scale_of(max(0, v._cur_page))
        self._show_scale()
        if key == "dim":
            v.set_tool("dim")
            self.statusBar().showMessage("מקליקים נקודת התחלה ונקודת סיום. Shift = קו ישר. Esc מסיים")
        elif key == "pen":
            v.set_tool("pen")
            self.statusBar().showMessage("ציור חופשי: לוחצים וגוררים. Esc או לחצן ימני מסיימים")
        elif key == "erase":
            v.set_tool("erase")
            self.statusBar().showMessage("מחק: לוחצים וגוררים על קווי העט. Esc מסיים")
        elif key == "text":
            v.set_tool("text")
            self.statusBar().showMessage("טקסט: מקליקים במקום וכותבים ישירות על השרטוט. לחיצה מחוץ לטקסט או Esc מסיימים")
        elif key == "calib":
            v.set_tool("calib")
            self.statusBar().showMessage("כיול: מקליקים על שני קצוות של קו שאורכו ידוע")
        v.setFocus()

    def _pen_color(self, c):
        self.view.pen_color = c
        QSettings("Tiktin", "TiktinPDF").setValue("pen_color", c)
        v = self.view
        ref = v.editing or v.selected
        if ref:
            i, idx = ref
            it = v.items[i][idx]
            if True:
                if not v.editing:
                    v._push_undo()
                it["color"] = c
                v._place_editor()
                v.viewport().update()
                if v.editor:
                    v.editor.setFocus()

    def _text_size(self, *_):
        s = self.tsize_box.currentData()
        v = self.view
        v.text_size = s
        QSettings("Tiktin", "TiktinPDF").setValue("text_size", s)
        ref = v.editing or v.selected
        if ref:
            it = v.items[ref[0]][ref[1]]
            if it["type"] == "text":
                if not v.editing:
                    v._push_undo()
                it["size"] = s
                v._place_editor()
                v.viewport().update()
                if v.editor:
                    v.editor.setFocus()

    def _pen_width(self, *_):
        w = self.width_box.currentData()
        self.view.pen_w = w
        QSettings("Tiktin", "TiktinPDF").setValue("pen_w", w)
        v = self.view
        if v.selected:
            i, idx = v.selected
            it = v.items[i][idx]
            if it["type"] in ("ink", "shape"):
                v._push_undo()
                it["w"] = w
                v.viewport().update()

    # ----- copy window to clipboard
    def copy_window(self):
        v = self.view
        if not v.sizes:
            QMessageBox.information(self, APP_NAME, "קודם פותחים קובץ PDF.")
            return
        if v.tool != "pan":
            v.set_tool("pan")
        v.start_select("copy")
        self.statusBar().showMessage("גררו מלבן סביב האזור להעתקה  (Esc לביטול)")
        v.setFocus()

    def _region(self, i, clip):
        v = self.view
        if v.select_purpose != "copy":
            return
        v.select_purpose = "print"
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            c = self._make_clip(i, clip)
        except Exception as e:
            QApplication.restoreOverrideCursor()
            QMessageBox.warning(self, APP_NAME, f"ההעתקה נכשלה:\n{e}")
            return
        QApplication.restoreOverrideCursor()
        QApplication.clipboard().setImage(c["img"])
        self.tray.add(c)
        self.statusBar().showMessage("✓ הקטע נקלט והועתק באיכות מלאה — אפשר להדביק (Ctrl+V). "
                                     "במגש בפינה: לחיצה מעתיקה שוב, גרירה מוציאה כקובץ PDF", 9000)

    def _make_clip(self, i, clip):
        """קטע מהשרטוט: PDF וקטורי (כולל הסימונים) + תמונה ברזולוציה גבוהה להדבקה."""
        import tempfile
        import uuid
        v = self.view
        one = pymupdf.open()
        one.insert_pdf(v.doc, from_page=i, to_page=i)
        if marks_store.has_marks(v.doc):
            marks_store.strip_page(one, one[0])
        if v.items.get(i):
            A.bake_page(one[0], v.items[i], v.scale_of(i))
        out = pymupdf.open()
        pg = out.new_page(width=clip.width, height=clip.height)
        pg.show_pdf_page(pg.rect, one, 0, clip=clip)
        d = os.path.join(tempfile.gettempdir(), "TiktinPDF-clips")
        os.makedirs(d, exist_ok=True)
        base = os.path.splitext(os.path.basename(v.path or "קטע"))[0]
        name = f"{base} - עמוד {i + 1} - קטע.pdf"
        path = os.path.join(d, uuid.uuid4().hex[:8] + " " + name)
        out.save(path, garbage=1, deflate=True)
        # תמונה: 400 DPI, עד 6000 פיקסלים בצד הארוך
        s = min(400 / 72.0, 6000.0 / max(clip.width, clip.height))
        pix = one[0].get_pixmap(matrix=pymupdf.Matrix(s, s), clip=clip, alpha=False)
        img = QImage(pix.samples, pix.width, pix.height, pix.stride, QImage.Format_RGB888).copy()
        one.close()
        out.close()
        return {"pdf": path, "img": img, "name": name,
                "label": f"✓ נקלט · עמוד {i + 1}"}

    def _on_tool(self, tool):
        add = tool in ("hole", "pen", "erase", "text", "trafo", "shape", "mark", "stamp")
        for b, on in ((self.add_btn, add), (self.measure_btn, tool in ("dim", "calib"))):
            b.blockSignals(True)
            b.setChecked(on)
            b.blockSignals(False)
        if tool == "pan":
            self.statusBar().clearMessage()
        self._sync_ctx()

    def _on_changed(self):
        name = os.path.basename(self.view.path or "")
        self.setWindowTitle(f"{'* ' if self.view.dirty else ''}{name} – {APP_NAME}   |   גרסה {VERSION} ({BUILD_DATE})")
        self.file_lbl.setText(("* " if self.view.dirty else "") + name)

    def _show_scale(self, *_):
        v = self.view
        if v.sizes:
            S = v.shown_scale(max(0, v._cur_page))
            self.scale_box.setEditText(f"1:{S:.4g}")

    def _scale_other(self):
        if not self._need_doc():
            return
        v = self.view
        t, ok = QInputDialog.getText(self, "קנה מידה", "קנה מידה לעמוד הנוכחי (למשל 1:50):", QLineEdit.Normal,
                                     f"1:{v.shown_scale(max(0, v._cur_page)):.4g}")
        if ok and t.strip():
            self._scale_text(t.strip())

    def _scale_text(self, t):
        v = self.view
        try:
            S = float(t.replace(" ", "").split(":")[-1])
            if S <= 0:
                raise ValueError
        except ValueError:
            self._show_scale()
            return
        if v.sizes:
            v.set_scale(max(0, v._cur_page), S)
        self._show_scale()

    # ----- save
    def _has_changes(self):
        v = self.view
        return v.dirty or v.has_items() or v.pages_changed

    def save_as(self):
        v = self.view
        if not v.sizes:
            return False
        if not self._has_changes():
            QMessageBox.information(self, APP_NAME, "אין שינויים לשמירה.")
            return False
        base, _ = os.path.splitext(v.path)
        target, _ = QFileDialog.getSaveFileName(self, "שמירה בשם", base + " - מעודכן.pdf",
                                                "קובצי PDF (*.pdf)")
        if not target:
            return False
        return self._save_to(target)

    def save_changes(self):
        """שמירה לתוך הקובץ הפתוח עצמו."""
        v = self.view
        if not v.sizes:
            return False
        if v.editor:
            v.finish_text_edit()
        if not self._has_changes():
            self.statusBar().showMessage("אין שינויים לשמירה", 4000)
            return False
        if not self.settings.value("save_same_ok", False, type=bool):
            box = QMessageBox(self)
            box.setWindowTitle(APP_NAME)
            box.setIcon(QMessageBox.Question)
            box.setText("השינויים יישמרו בתוך הקובץ:\n" + os.path.basename(v.path) +
                        "\n\nהסימונים יופיעו בכל תוכנה, ובטיקטין PDF אפשר יהיה לחזור ולשנות או למחוק אותם. להמשיך?")
            from PySide6.QtWidgets import QCheckBox
            cb = QCheckBox("לא לשאול שוב")
            box.setCheckBox(cb)
            yes = box.addButton("שמירה", QMessageBox.AcceptRole)
            other = box.addButton("שמירה בשם...", QMessageBox.ActionRole)
            box.addButton("ביטול", QMessageBox.RejectRole)
            box.exec()
            if box.clickedButton() is other:
                return self.save_as()
            if box.clickedButton() is not yes:
                return False
            if cb.isChecked():
                self.settings.setValue("save_same_ok", True)
        return self._save_to(v.path)

    def _save_to(self, target):
        v = self.view
        if v.editor:
            v.finish_text_edit()
        same = os.path.abspath(target).lower() == os.path.abspath(v.path).lower()
        tmp = target + ".tmp" if same else target
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            doc2 = pymupdf.open(v.src)
            if doc2.needs_pass:
                doc2.authenticate(v.pw or "")
            scales = {i: v.scale_of(i) for i, items in v.items.items() if items}
            marks_store.save(doc2, v.items, scales)
            # garbage=3: מאחד גופנים ותמונות כפולים, כך שהקובץ לא גדל משמירה לשמירה
            doc2.save(tmp, garbage=3, deflate=True)
            doc2.close()
            if same:
                v.pool.close_docs()
                v.analyzer.close_doc()
                v.doc.close()
                for _ in range(30):
                    try:
                        os.replace(tmp, target)
                        break
                    except PermissionError:
                        QThread.msleep(150)
                        QApplication.processEvents()
                else:
                    raise PermissionError("הקובץ פתוח בתוכנה אחרת")
        except Exception as e:
            QApplication.restoreOverrideCursor()
            QMessageBox.warning(self, APP_NAME, f"השמירה נכשלה:\n{e}")
            return False
        QApplication.restoreOverrideCursor()
        old_scales = dict(v.scales)
        page = max(0, v._cur_page)
        v.dirty = False
        self.open_path(target, ask=False)
        v.scales.update(old_scales)
        v._save_scales()
        QTimer.singleShot(0, lambda: v.go_page(page))
        self.statusBar().showMessage(f"נשמר: {os.path.basename(target)}", 6000)
        return True

    def rotate_pages(self, scope, mode, cw=True):
        v = self.view
        if not self._need_doc():
            return
        n = len(v.sizes)
        cur = max(0, v._cur_page)

        class dlg:  # noqa: N801
            pass
        dlg.scope, dlg.mode, dlg.cw = scope, mode, cw
        pages = range(n) if dlg.scope == "all" else [cur]
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            k = v.rotate_pages(list(pages), dlg.mode, dlg.cw)
        except Exception as e:
            QApplication.restoreOverrideCursor()
            QMessageBox.warning(self, APP_NAME, f"הסיבוב נכשל:\n{e}")
            return
        QApplication.restoreOverrideCursor()
        unknown = getattr(v, "rotate_unknown", []) if dlg.mode in ("portrait", "landscape", "upright") else []
        if k == 0 and not unknown:
            self.statusBar().showMessage("כל העמודים כבר במצב שנבחר — לא היה מה לסובב", 6000)
        elif k:
            self.statusBar().showMessage(f"סובבו {k} עמודים. UNDO מחזיר; הקובץ עצמו משתנה רק ב\"שמירת שינויים\"", 8000)
        side = getattr(v, "rotate_sideways", []) if dlg.mode in ("portrait", "landscape") else []
        if side:
            QMessageBox.information(
                self, APP_NAME,
                f"בעמודים {self._page_ranges(side)} אי אפשר להעמיד את הדף "
                f"{'לאורך' if dlg.mode == 'portrait' else 'לרוחב'} וגם את הטקסט ישר:\n"
                "הטקסט בשרטוט כתוב לאורך הצד הארוך של הדף.\n\n"
                "הדפים הועמדו כפי שביקשת, והטקסט בהם אנכי — נקרא מלמטה למעלה, לא הפוך.\n"
                "לטקסט ישר: סיבוב ← טקסט ישר.")
        if unknown:
            pages_txt = self._page_ranges(unknown)
            allp = len(unknown) == n if dlg.scope == "all" else True
            why = ("הקובץ סרוק כתמונה ואין בו טקסט שהמחשב יכול לקרוא" if allp else
                   "אין בעמודים האלה טקסט שהמחשב יכול לקרוא (כנראה סריקה או שרטוט בלי טקסט)")
            if dlg.mode == "upright":
                todo = ("העמודים האלה לא סובבו.\n"
                        "כדי ליישר אותם: סיבוב ← 90° עם או נגד כיוון השעון, או היפוך 180°.")
            else:
                todo = ("העמודים האלה סובבו עם כיוון השעון, ולא נבדק שהטקסט לא הפוך.\n"
                        "אם עמוד יצא הפוך: סיבוב ← היפוך 180°.")
            QMessageBox.information(
                self, APP_NAME,
                f"לא ניתן לזהות את כיוון הטקסט בעמודים: {pages_txt}\n({why}).\n\n{todo}")

    @staticmethod
    def _page_ranges(pages):
        """[0,1,2,5] -> '1–3, 6'"""
        out, run = [], []
        for p in sorted(pages):
            if run and p == run[-1] + 1:
                run.append(p)
            else:
                if run:
                    out.append(run)
                run = [p]
        if run:
            out.append(run)
        return ", ".join(f"{r[0] + 1}" if len(r) == 1 else f"{r[0] + 1}–{r[-1] + 1}" for r in out)

    def delete_pages_dialog(self):
        v = self.view
        if not self._need_doc():
            return
        n = len(v.sizes)
        if n < 2:
            QMessageBox.information(self, APP_NAME, "בקובץ יש עמוד אחד בלבד.")
            return
        cur = max(0, v._cur_page) + 1
        txt, ok = QInputDialog.getText(self, "מחיקת עמודים",
                                       f"אילו עמודים למחוק? (מתוך {n})\nלדוגמה: 3   או   2-5, 8",
                                       QLineEdit.Normal, str(cur))
        if not ok or not txt.strip():
            return
        pages = set()
        try:
            for part in txt.replace(" ", "").replace("–", "-").split(","):
                if not part:
                    continue
                if "-" in part:
                    a, b = part.split("-", 1)
                    a, b = int(a), int(b)
                    pages.update(range(min(a, b), max(a, b) + 1))
                else:
                    pages.add(int(part))
        except ValueError:
            QMessageBox.warning(self, APP_NAME, "לא הבנתי את מספרי העמודים. כותבים למשל: 3 או 2-5, 8")
            return
        bad = [p for p in pages if p < 1 or p > n]
        if bad:
            QMessageBox.warning(self, APP_NAME, f"אין עמוד {bad[0]} בקובץ (יש {n} עמודים).")
            return
        if len(pages) >= n:
            QMessageBox.warning(self, APP_NAME, "אי אפשר למחוק את כל העמודים.")
            return
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            v.delete_pages([p - 1 for p in pages])
        finally:
            QApplication.restoreOverrideCursor()
        k = len(pages)
        self.statusBar().showMessage(
            f"נמחקו {k} עמודים. ביטול פעולה (↶) מחזיר אותם; הקובץ עצמו משתנה רק ב\"שמירת שינויים\"", 9000)

    def _confirm_discard(self):
        if not self.view.dirty or not self._has_changes():
            return True
        r = QMessageBox.question(self, APP_NAME, "יש שינויים שלא נשמרו. לשמור לפני שממשיכים?",
                                 QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel)
        if r == QMessageBox.Save:
            return self.save_changes()
        return r == QMessageBox.Discard

    def print_dialog(self):
        v = self.view
        if not v.sizes:
            QMessageBox.information(self, APP_NAME, "קודם פותחים קובץ PDF.")
            return
        if v.tool != "pan":
            v.set_tool("pan")
        # חלון לא-מודאלי: כך אפשר להסתיר אותו זמנית לבחירת חלון על השרטוט
        if getattr(self, "_pdlg", None) is not None:
            self._pdlg.close()
        from printing import PrintDialog      # נטען רק בהדפסה הראשונה (חוסך זמן בעלייה)
        self._pdlg = PrintDialog(self)
        self._pdlg.setAttribute(Qt.WA_DeleteOnClose, True)
        self._pdlg.finished.connect(lambda *_: setattr(self, "_pdlg", None))
        self._pdlg.show()

    def _print_overlay(self, painter, pno):
        self.view.paint_overlay(painter, pno, cosmetic=False)

    def open_dialog(self):
        d = self.settings.value("last_dir", "")
        path, _ = QFileDialog.getOpenFileName(self, "פתיחת קובץ PDF", d, "קובצי PDF (*.pdf);;כל הקבצים (*.*)")
        if path:
            self.open_path(path)

    def open_path(self, path, ask=True):
        if ask and not self._confirm_discard():
            return
        try:
            doc = pymupdf.open(path)
        except Exception as e:
            QMessageBox.warning(self, APP_NAME, f"לא ניתן לפתוח את הקובץ:\n{path}\n\n{e}")
            return
        pw = None
        if doc.needs_pass:
            while True:
                pw, ok = QInputDialog.getText(self, APP_NAME, "הקובץ מוגן בסיסמה. הקלידו סיסמה:",
                                              QLineEdit.Password)
                if not ok:
                    return
                if doc.authenticate(pw):
                    break
        if doc.page_count == 0:
            QMessageBox.warning(self, APP_NAME, "בקובץ אין עמודים.")
            return
        self.settings.setValue("last_dir", os.path.dirname(path))
        self.setWindowTitle(f"{os.path.basename(path)} – {APP_NAME}")
        self.file_lbl.setText(os.path.basename(path))
        loaded = None
        try:
            loaded = marks_store.load(doc)
        except Exception:
            loaded = None
        marks_store.hide_layer(doc)
        v = self.view
        v.open_doc(doc, path, pw)
        if loaded:
            items, scales = loaded
            v.items = items
            for k, S in scales.items():
                v.scales.setdefault(k, S)
            n = sum(len(x) for x in items.values())
            if n:
                self.statusBar().showMessage(f"נטענו {n} סימונים מהקובץ — אפשר לגרור, לשנות ולמחוק אותם", 7000)
            v.viewport().update()
        # בפתיחת קובץ: הגלגלת גוללת, Ctrl+גלגלת מגדיל ומקטין
        v.wheel_zoom = False
        self.wheel_act.blockSignals(True)
        self.wheel_act.setChecked(False)
        self.wheel_act.blockSignals(False)
        v.setFocus()

    def dragEnterEvent(self, ev):
        if ev.mimeData().hasUrls():
            ev.acceptProposedAction()

    def dropEvent(self, ev):
        for u in ev.mimeData().urls():
            p = u.toLocalFile()
            if p:
                self.open_path(p)
                break

    def closeEvent(self, ev):
        if not self._confirm_discard():
            ev.ignore()
            return
        self.settings.setValue("geometry", self.saveGeometry())
        super().closeEvent(ev)


STYLE = f"""
QMainWindow {{ background: #ffffff; }}
QToolBar {{ background: #ffffff; border: none; border-bottom: 1px solid #d4d8de; padding: 4px 3px; spacing: 3px; }}
QToolButton#tb {{ color: #1f2630; background: #ffffff; border: 1px solid #cfd4db; border-radius: 4px;
                  padding: 0 4px; min-height: 30px; max-height: 30px; font-size: 9.25pt; }}
QToolButton#tb::menu-indicator {{ image: none; width: 0; }}
QToolButton#tbsplit {{ color: #1f2630; background: #ffffff; border: 1px solid #cfd4db; border-radius: 4px;
                      padding: 0 24px 0 24px; min-height: 30px; max-height: 30px; font-size: 9.5pt; }}
QToolButton#tbsplit:hover {{ background: #f2f4f7; }}
QToolButton#tbsplit:checked {{ background: {ACCENT}; border-color: {ACCENT}; color: #ffffff; font-weight: 600; }}
QToolButton#tbsplit::menu-button {{ border: none; border-right: 1px solid #cfd4db; width: 16px; }}
QToolButton#tbur {{ color: #1f2630; background: #ffffff; border: 1px solid #cfd4db; border-radius: 4px;
                    padding: 0 3px; min-height: 30px; max-height: 30px; font-size: 7pt; }}
QToolButton#tbur:hover {{ background: #f2f4f7; }}
QToolButton#tb:hover {{ background: #f2f4f7; }}
QToolButton#tb:checked {{ background: {ACCENT}; border-color: {ACCENT}; color: #ffffff; font-weight: 600; }}
QToolButton#primary {{ color: #ffffff; background: {ACCENT}; border: 1px solid {ACCENT}; border-radius: 4px;
                       padding: 0 10px; min-height: 30px; max-height: 30px; font-size: 10pt; font-weight: 600; }}
QToolButton#primary:hover {{ background: #a91a27; }}
QLineEdit, QComboBox {{ background: #ffffff; color: #1f2630; border: 1px solid #cfd4db; border-radius: 4px;
                        min-height: 30px; max-height: 30px; font-size: 10pt; }}
QComboBox::drop-down {{ border: none; width: 22px; }}
QComboBox QAbstractItemView {{ background: #ffffff; color: #1f2630; }}
QLabel {{ color: #1f2630; font-size: 10pt; }}
QDialog {{ background: #ffffff; }}
QPushButton#seg {{ background: #ffffff; color: #1f2630; border: 1px solid #cfd4db; border-radius: 0;
                   min-height: 32px; max-height: 32px; padding: 0 14px; font-size: 10pt; margin-left: -1px; }}
QPushButton#seg:checked {{ background: {ACCENT}; color: #ffffff; border-color: {ACCENT}; }}
QPushButton#seg:hover:!checked {{ background: #f2f4f7; }}
QPushButton#primaryBtn {{ background: {ACCENT}; color: #ffffff; border: 1px solid {ACCENT}; border-radius: 4px;
                          min-height: 32px; padding: 0 22px; font-size: 10pt; font-weight: 600; }}
QPushButton#plainBtn {{ background: #ffffff; color: #1f2630; border: 1px solid #cfd4db; border-radius: 4px;
                        min-height: 32px; padding: 0 22px; font-size: 10pt; }}
QSpinBox {{ background: #ffffff; color: #1f2630; border: 1px solid #cfd4db; border-radius: 4px;
            min-height: 30px; max-height: 30px; font-size: 10pt; }}
QStatusBar {{ background: #ffffff; color: {ACCENT}; font-size: 10pt; }}
QProgressDialog {{ background: #ffffff; }}
QLabel#ver {{ color: #7a828e; font-size: 9pt; }}
QToolTip {{ background: #ffffff; color: #1f2630; border: 1px solid #cfd4db; }}
QScrollBar:vertical {{ background: {CANVAS_BG.name()}; width: 12px; }}
QScrollBar:horizontal {{ background: {CANVAS_BG.name()}; height: 12px; }}
QScrollBar::handle {{ background: #a9b0ba; border-radius: 5px; min-height: 30px; min-width: 30px; margin: 2px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
"""


def light_palette():
    pal = QPalette()
    for role, c in ((QPalette.Window, "#ffffff"), (QPalette.WindowText, "#1f2630"),
                    (QPalette.Base, "#ffffff"), (QPalette.AlternateBase, "#f4f6f8"),
                    (QPalette.Text, "#1f2630"), (QPalette.Button, "#ffffff"),
                    (QPalette.ButtonText, "#1f2630"), (QPalette.Highlight, ACCENT),
                    (QPalette.HighlightedText, "#ffffff"), (QPalette.ToolTipBase, "#ffffff"),
                    (QPalette.ToolTipText, "#1f2630")):
        pal.setColor(role, QColor(c))
    return pal


ACTIVE_BTN_CSS = ("QToolButton, QToolButton:hover, QToolButton:pressed, QToolButton:checked, QToolButton:focus "
                  "{ background: #c8202f; border: 1px solid #c8202f; border-radius: 8px; color: #ffffff; }")


def _clean_temp():
    """מנקה קבצים זמניים (עמודים שנמחקו, קטעים שהועתקו) שנשארו מלפני יותר מיומיים."""
    import tempfile
    import time
    for sub in ("TiktinPDF-work", "TiktinPDF-clips"):
        d = os.path.join(tempfile.gettempdir(), sub)
        try:
            for f in os.listdir(d):
                fp = os.path.join(d, f)
                if time.time() - os.path.getmtime(fp) > 2 * 86400:
                    os.remove(fp)
        except OSError:
            pass


def main():
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("Tiktin.PDF")
        except Exception:
            pass
    pymupdf.TOOLS.set_graphics_min_line_width(1.0)   # קווים דקים כהים וברורים (גם בהדפסה)
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setStyle("Fusion")
    app.setPalette(light_palette())
    app.setLayoutDirection(Qt.RightToLeft)
    app.setStyleSheet(STYLE + TRAY_STYLE + RIBBON_STYLE)
    pm = QPixmap()
    pm.loadFromData(base64.b64decode(LOGO_B64))
    if ICON_B64:
        ipm = QPixmap()
        ipm.loadFromData(base64.b64decode(ICON_B64))
        app.setWindowIcon(QIcon(ipm))
    else:
        app.setWindowIcon(QIcon(pm.copy(179, 12, 75, 86)))
    n = max(2, min(6, (os.cpu_count() or 4) - 1))
    # תהליך רינדור אחד מתחיל לעלות כבר עכשיו, במקביל לבניית החלון, כדי שקובץ שנפתח בלחיצה כפולה
    # יוצג מיד; שאר התהליכים עולים רק אחרי שהוא מוכן, והחלון לא מחכה לאף אחד מהם
    pool = RenderPool(n, autostart=False)
    pool.start()
    win = MainWindow(pool)
    win.show()
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    if args:
        QTimer.singleShot(0, lambda: win.open_path(args[0]))
    QTimer.singleShot(3000, _clean_temp)
    rc = app.exec()
    pool.shutdown()
    win.view.analyzer.shutdown()
    return rc
