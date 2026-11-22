# קריאת קווי השרטוט להצמדת המדידה – בתהליך רקע נפרד, כדי שהתוכנה לא תיתקע אף פעם
# (בשרטוט כבד הקריאה לוקחת שנייה ויותר). מודול קל: רק pymupdf, בלי ממשק גרפי.


def build_snap_segments(page):
    """כל קטעי הקו הישרים בעמוד (כולל קווי מתאר של משטחים מלאים – קירות), עם רשת חיפוש.
    הקואורדינטות במערכת העמוד הלא מסובבת."""
    grid, cell, segs = {}, 30.0, []
    try:
        paths = page.get_cdrawings()
    except Exception:
        paths = []
    for pth in paths:
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
                pieces = [(pts[n], pts[(n + 1) % len(pts)]) for n in range(len(pts))]
            else:
                continue                         # עקומות – לא נצמדים אליהן
            for a, b in pieces:
                if abs(a[0] - b[0]) < 1e-6 and abs(a[1] - b[1]) < 1e-6:
                    continue
                sid = len(segs)
                segs.append((a[0], a[1], b[0], b[1]))
                gx0, gx1 = int(min(a[0], b[0]) // cell), int(max(a[0], b[0]) // cell)
                gy0, gy1 = int(min(a[1], b[1]) // cell), int(max(a[1], b[1]) // cell)
                if (gx1 - gx0 + 1) * (gy1 - gy0 + 1) > 300:
                    n = max(gx1 - gx0, gy1 - gy0) + 1
                    for t in range(n + 1):
                        x = a[0] + (b[0] - a[0]) * t / n
                        y = a[1] + (b[1] - a[1]) * t / n
                        grid.setdefault((int(x // cell), int(y // cell)), set()).add(sid)
                else:
                    for gx in range(gx0, gx1 + 1):
                        for gy in range(gy0, gy1 + 1):
                            grid.setdefault((gx, gy), set()).add(sid)
    return {"segs": segs, "grid": grid, "cell": cell}


def snap_main(job_conn, res_conn):
    """תהליך הרקע: מקבל (דור, קובץ, סיסמה, עמוד) ומחזיר את קווי ההצמדה של העמוד."""
    import pymupdf
    try:
        pymupdf.TOOLS.mupdf_display_errors(False)
        pymupdf.TOOLS.mupdf_display_warnings(False)
    except Exception:
        pass
    doc, key = None, None
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
            doc, key = None, None
            continue
        gen, path, pw, pno = msg
        try:
            if key != (path, pw):
                if doc is not None:
                    doc.close()
                doc = pymupdf.open(path)
                if doc.needs_pass:
                    doc.authenticate(pw or "")
                key = (path, pw)
            res_conn.send((gen, pno, build_snap_segments(doc[pno])))
        except Exception:
            res_conn.send((gen, pno, {"segs": [], "grid": {}, "cell": 30.0}))
