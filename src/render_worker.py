# תהליך רינדור: מחזיק עותק משלו של המסמך ומטמון DisplayList לכל עמוד,
# כך שכל אריח מצויר מתוך רשימה מוכנה בלי לפענח שוב את העמוד.
from collections import OrderedDict

DL_CACHE_PAGES = 4


def worker_main(job_conn, res_conn, wid):
    import pymupdf
    # קווים דקים מאוד (hairline) מצוירים ברוחב פיקסל אחד לפחות, כמו ב-Foxit,
    # כדי שהשרטוט לא ייראה חיוור ודהוי בהקטנה
    pymupdf.TOOLS.set_graphics_min_line_width(1.0)
    try:
        pymupdf.TOOLS.mupdf_display_errors(False)
        pymupdf.TOOLS.mupdf_display_warnings(False)
    except Exception:
        pass
    doc = None
    doc_key = None
    dls = OrderedDict()
    cur_aa = None
    res_conn.send(("ready", wid))
    while True:
        try:
            msg = job_conn.recv()
        except (EOFError, OSError):
            break
        if msg is None:
            break
        if msg == "close":
            if doc is not None:
                doc.close()
            doc, doc_key = None, None
            dls.clear()
            continue
        jobid, path, pw, pno, scale, clip, aa = msg
        try:
            if (path, pw) != doc_key:
                if doc is not None:
                    doc.close()
                dls.clear()
                doc = pymupdf.open(path)
                if doc.needs_pass:
                    doc.authenticate(pw or "")
                doc_key = (path, pw)
            dl = dls.get(pno)
            if dl is None:
                dl = doc[pno].get_displaylist()
                dls[pno] = dl
                while len(dls) > DL_CACHE_PAGES:
                    dls.popitem(last=False)
            else:
                dls.move_to_end(pno)
            if aa != cur_aa:
                pymupdf.TOOLS.set_aa_level(aa)
                cur_aa = aa
            pix = dl.get_pixmap(matrix=pymupdf.Matrix(scale, scale),
                                clip=pymupdf.Rect(*clip), alpha=False)
            res_conn.send(("ok", wid, jobid, pix.x, pix.y, pix.width,
                           pix.height, pix.stride, pix.samples))
        except Exception as e:  # noqa
            res_conn.send(("err", wid, jobid, str(e)))
