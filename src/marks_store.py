# שמירת הסימונים בתוך קובץ ה-PDF כך שאפשר לחזור ולערוך אותם:
# 1. הסימונים נצרבים לשרטוט (כדי שכל תוכנה תציג אותם) בשכבה נפרדת, וכל זרם תוכן שלהם מסומן.
# 2. נתוני הסימונים עצמם נשמרים בקובץ (מוסתר, לא כקובץ מצורף).
# בפתיחה בטיקטין PDF השכבה הצרובה מוסתרת והסימונים נטענים מחדש לעריכה.
import json
import base64
import hashlib

import annotations as A

LAYER = "Tiktin marks"
KEY = "TiktinMarks"
FORMAT = 1


def _catalog_stream(doc):
    t, v = doc.xref_get_key(doc.pdf_catalog(), KEY)
    if t == "xref":
        try:
            return int(v.split()[0])
        except ValueError:
            return 0
    return 0


def has_marks(doc):
    return _catalog_stream(doc) > 0


def layer_xrefs(doc):
    try:
        return [x for x, o in doc.get_ocgs().items() if o.get("name") == LAYER]
    except Exception:
        return []


def hide_layer(doc):
    """מסתיר את הסימונים הצרובים בתצוגה (רק בזיכרון, הקובץ לא משתנה)."""
    if not has_marks(doc):
        return
    try:
        for c in doc.layer_ui_configs():
            if c.get("text") == LAYER:
                doc.set_layer_ui_config(c["number"], action=2)
    except Exception:
        pass


def strip_page(doc, page):
    """מסיר מהעמוד את זרמי התוכן של סימונים שנצרבו בשמירה קודמת."""
    import re
    xs = page.get_contents()
    keep, names = [], set()
    for x in xs:
        try:
            data = doc.xref_stream(x)
        except Exception:
            data = b""
        if data[:len(A.MARK_TAG)] != A.MARK_TAG:
            keep.append(x)
        else:
            names.update(n.decode("latin-1") for n in re.findall(rb"/([^\s/<>\[\]()]+)\s+Do\b", data))
    if len(keep) == len(xs):
        return False
    # גם האובייקטים (טקסט, תמונות) שרק הסימונים השתמשו בהם יוצאים מהעמוד, כדי שהקובץ לא יגדל
    used = set()
    for x in keep:
        try:
            used.update(n.decode("latin-1") for n in re.findall(rb"/([^\s/<>\[\]()]+)\s+Do\b", doc.xref_stream(x)))
        except Exception:
            pass
    for n in names - used:
        try:
            doc.xref_set_key(page.xref, f"Resources/XObject/{n}", "null")
        except Exception:
            pass
    if not keep:
        nx = doc.get_new_xref()
        doc.update_object(nx, "<<>>")
        doc.update_stream(nx, b" ")
        keep = [nx]
    doc.xref_set_key(page.xref, "Contents",
                     f"{keep[0]} 0 R" if len(keep) == 1 else "[" + " ".join(f"{x} 0 R" for x in keep) + "]")
    return True


def strip_all(doc):
    for page in doc:
        strip_page(doc, page)


def load(doc):
    """מחזיר (סימונים לפי עמוד, קנ"מ לפי עמוד) או None."""
    x = _catalog_stream(doc)
    if not x:
        return None
    try:
        data = json.loads(doc.xref_stream(x).decode("utf-8"))
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


def save(doc, items, scales):
    """צורב את הסימונים בשכבה, ושומר את נתוני העריכה בקובץ. מוחק צריבה קודמת של טיקטין."""
    import stamps
    strip_all(doc)
    xs = layer_xrefs(doc)
    ocg = xs[0] if xs else doc.add_ocg(LAYER, on=True)
    try:
        doc.set_layer(-1, on=[ocg])
    except Exception:
        pass
    stamp_data = {}
    out_items = {}
    A.BAKE_OC = ocg
    try:
        for i, lst in items.items():
            if not lst or i >= doc.page_count:
                continue
            page = doc[i]
            page.wrap_contents()
            before = set(page.get_contents())
            A.bake_page(page, lst, scales.get(i, 50.0))
            for x in set(page.get_contents()) - before:
                doc.update_stream(x, A.MARK_TAG + b"\n" + doc.xref_stream(x))
            saved = []
            for it in lst:
                it = dict(it)
                if it["type"] == "stamp":
                    png = stamps.mask_png(it["slot"])
                    if png:
                        key = "f" + hashlib.md5(png).hexdigest()[:16]
                        stamp_data[key] = base64.b64encode(png).decode()
                        it["slot"] = key
                saved.append(it)
            out_items[str(i)] = saved
    finally:
        A.BAKE_OC = 0
    data = {"format": FORMAT, "items": out_items,
            "scales": {str(k): v for k, v in scales.items()}, "stamps": stamp_data}
    raw = json.dumps(data, ensure_ascii=False).encode("utf-8")
    x = _catalog_stream(doc)
    if not x:
        x = doc.get_new_xref()
        doc.update_object(x, "<<>>")
        doc.xref_set_key(doc.pdf_catalog(), KEY, f"{x} 0 R")
    doc.update_stream(x, raw, compress=True)
