# שמירת הסימונים בקובץ — גרסה מסחרית.
# הסימונים מצוירים בדיוק כמו בהדפסה (אותו צייר של Qt) לעמוד PDF שקוף, והעמוד הזה מוצב מעל השרטוט.
# כך כל תוכנה מציגה אותם, והטקסט העברי נשמר כמו שהוא. נתוני העריכה נשמרים בקובץ כדי לחזור ולערוך.
import base64
import io
import json
import zlib

import annotations as A
import pymupdf

KEY = "TiktinMarks"
FORMAT = 1
MARK_TAG = pymupdf.MARK_TAG


def has_marks(doc):
    try:
        return ("/" + KEY) in doc._pk_doc().Root
    except Exception:
        return False


def layer_xrefs(doc):
    return []


def hide_layer(doc):
    pass


def strip_page(doc, page):
    pk = doc._pk_doc()
    if pymupdf.strip_tagged(pk.pages[page.number]):
        doc._edited()
        return True
    return False


def strip_all(doc):
    for i in range(doc.page_count):
        strip_page(doc, doc[i])


def load(doc):
    try:
        st = doc._pk_doc().Root.get("/" + KEY)
        if st is None:
            return None
        data = json.loads(st.read_bytes().decode("utf-8"))
    except Exception:
        return None
    if data.get("format", 0) > FORMAT:
        return None
    import stamps
    for key, b64 in data.get("stamps", {}).items():
        stamps.register(key, base64.b64decode(b64))
    items = {}
    for k, lst in data.get("items", {}).items():
        i = int(k)
        if 0 <= i < doc.page_count:
            items[i] = [dict(it) for it in lst]
    scales = {int(k): float(v) for k, v in data.get("scales", {}).items()}
    return items, scales


def _overlay_pdf(pages):
    """pages: [(רוחב, גובה, סימונים, קנ"מ)] → קובץ PDF (בזיכרון) שבו כל עמוד הוא שכבת הסימונים בלבד."""
    from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QMarginsF, QSizeF
    from PySide6.QtGui import QPageLayout, QPageSize, QPainter, QPdfWriter
    ba = QByteArray()
    buf = QBuffer(ba)
    buf.open(QIODevice.WriteOnly)
    wr = QPdfWriter(buf)
    wr.setResolution(72)
    wr.setCreator("PDF")
    p = None
    for k, (w, h, items, S) in enumerate(pages):
        lay = QPageLayout(QPageSize(QSizeF(w, h), QPageSize.Point), QPageLayout.Portrait, QMarginsF(0, 0, 0, 0))
        wr.setPageLayout(lay)
        if p is None:
            p = QPainter(wr)
        else:
            wr.newPage()
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setRenderHint(QPainter.TextAntialiasing, True)
        for it in items:
            try:
                A.paint_item(p, it, S, cosmetic=False)
            except Exception:
                pass
    if p is not None:
        p.end()
    buf.close()
    return bytes(ba)


def _bake(doc, page_items):
    """page_items: {עמוד: (סימונים, קנ"מ)} — מציב את שכבת הסימונים מעל כל עמוד, עם תג להסרה בשמירה הבאה."""
    import pikepdf
    order = [i for i, (lst, _) in sorted(page_items.items()) if lst and i < doc.page_count]
    if not order:
        return
    pages = []
    for i in order:
        r = doc[i].rect
        lst, S = page_items[i]
        pages.append((r.width, r.height, lst, S))
    data = _overlay_pdf(pages)
    ov = pikepdf.open(io.BytesIO(data))
    pk = doc._pk_doc()
    for k, i in enumerate(order):
        pg = doc[i]
        form = ov.pages[k].as_form_xobject(handle_transformations=False)
        form = pk.copy_foreign(form)
        r = pg.rect
        # שכבת הסימונים (PDF, y למעלה, בגודל העמוד המוצג) → מוצג (y למטה) → עמוד לא מסובב → מערכת PDF
        to_disp = pymupdf.Matrix(1, 0, 0, -1, 0, r.height)
        total = to_disp * pg.derotation_matrix * pg._user()
        name = pikepdf.Name(f"/TkMarks{k + 1}")
        tp = pk.pages[i]
        if "/Resources" not in tp.obj:
            tp.obj["/Resources"] = pikepdf.Dictionary()
        if "/XObject" not in tp.obj.Resources:
            tp.obj.Resources["/XObject"] = pikepdf.Dictionary()
        tp.obj.Resources.XObject[name] = form
        ops = MARK_TAG + b"\n" + (f"q {' '.join(pymupdf._num(v) for v in total)} cm {name} Do Q").encode("latin-1")
        tp.contents_add(pikepdf.Stream(pk, ops), prepend=False)
    doc._edited()


def bake_page(page, items, S):
    """כמו במנוע המקורי: צורב סימונים של עמוד אחד (משמש גם בהעתקת קטע)."""
    if items:
        _bake(page.parent, {page.number: (items, S)})


A.bake_page = bake_page


def save(doc, items, scales):
    """צורב את הסימונים מעל השרטוט, ושומר את נתוני העריכה בקובץ. מוחק צריבה קודמת."""
    import pikepdf
    import stamps
    strip_all(doc)
    page_items = {i: (lst, scales.get(i, 50.0)) for i, lst in items.items() if lst and i < doc.page_count}
    _bake(doc, page_items)
    stamp_data, out_items = {}, {}
    for i, (lst, _) in page_items.items():
        saved = []
        for it in lst:
            it = dict(it)
            if it["type"] == "stamp":
                png = stamps.mask_png(it["slot"])
                if png:
                    key = "f%08x%06x" % (zlib.crc32(png) & 0xffffffff, len(png))
                    stamp_data[key] = base64.b64encode(png).decode()
                    it["slot"] = key
            saved.append(it)
        out_items[str(i)] = saved
    data = {"format": FORMAT, "items": out_items,
            "scales": {str(k): v for k, v in scales.items()}, "stamps": stamp_data}
    raw = json.dumps(data, ensure_ascii=False).encode("utf-8")
    pk = doc._pk_doc()
    pk.Root["/" + KEY] = pikepdf.Stream(pk, raw)
    doc._edited()
