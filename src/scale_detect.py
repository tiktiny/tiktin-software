# זיהוי קנה מידה ואימותו מול המידות שרשומות בשרטוט.
# רץ בתהליך נפרד ברקע, רק אחרי שהשרטוט כבר מוצג — כך שאינו מאט את הפתיחה.
import re

PT_PER_MM = 72.0 / 25.4
COMMON = [10, 20, 25, 50, 75, 100, 125, 200, 250, 500, 1000]
MAX_SEGS = 400000
MAX_NUMS = 800
_RE_INT = re.compile(r"^\d{2,4}$")
_RE_DEC = re.compile(r"^\d{1,2}[.,]\d{2}$")


def text_scale(txt):
    found = [int(m) for m in re.findall(r"1\s*:\s*(\d{2,4})(?!\d)", txt) if int(m) in COMMON]
    if not found:
        return None
    return max(set(found), key=found.count)


def _snap(S):
    for c in COMMON:
        if abs(S - c) / c <= 0.04:
            return c
    return None


def _segments(page):
    """קווים אופקיים ואנכיים בשרטוט: [(קואורדינטה קבועה, התחלה, סוף)]."""
    hs, vs = [], []
    try:
        paths = page.get_cdrawings()
    except Exception:
        try:
            paths = page.get_drawings()
        except Exception:
            return hs, vs
    n = 0
    for pth in paths:
        for itm in pth.get("items", ()):
            if itm[0] != "l":
                continue
            p1, p2 = itm[1], itm[2]
            x1, y1 = (p1[0], p1[1]) if not hasattr(p1, "x") else (p1.x, p1.y)
            x2, y2 = (p2[0], p2[1]) if not hasattr(p2, "x") else (p2.x, p2.y)
            dx, dy = abs(x2 - x1), abs(y2 - y1)
            if dy <= dx * 0.01 and dx > 4:
                hs.append(((y1 + y2) / 2, min(x1, x2), max(x1, x2)))
            elif dx <= dy * 0.01 and dy > 4:
                vs.append(((x1 + x2) / 2, min(y1, y2), max(y1, y2)))
            n += 1
            if n > MAX_SEGS:
                return hs, vs
    return hs, vs


def _bucket(segs, size):
    b = {}
    for s in segs:
        b.setdefault(int(s[0] // size), []).append(s)
    return b


def _nearest(bk, size, c_fixed, c_along, lo, hi, minlen):
    best = None
    for k in range(int(lo // size), int(hi // size) + 1):
        for f, a, b in bk.get(k, ()):
            if lo <= f <= hi and a - 0.5 <= c_along <= b + 0.5 and b - a >= minlen:
                d = abs(f - c_fixed)
                if best is None or d < best[0] or (d == best[0] and b - a < best[1]):
                    best = (d, b - a)
    return best[1] if best else None


def analyze(page):
    """מחזיר: קנ"מ לפי הכיתוב, קנ"מ לפי המידות, ומספר המידות שהתאימו."""
    try:
        txt = page.get_text()
    except Exception:
        txt = ""
    res = {"text": text_scale(txt), "dims": None, "votes": 0, "matched": 0}
    try:
        words = page.get_text("words")
    except Exception:
        return res
    nums = []
    for w in words:
        s = w[4].strip()
        if _RE_INT.match(s):
            nums.append((w, [float(s), float(s) / 10.0]))           # ס"מ, או מ"מ
        elif _RE_DEC.match(s):
            nums.append((w, [float(s.replace(",", ".")) * 100.0]))  # מטרים
        if len(nums) >= MAX_NUMS:
            break
    if len(nums) < 3:
        return res
    hs, vs = _segments(page)
    if not hs and not vs:
        return res
    size = 20.0
    hb, vb = _bucket(hs, size), _bucket(vs, size)
    votes = {}
    matched = 0
    for w, vals in nums:
        x0, y0, x1, y1 = w[:4]
        bw, bh = x1 - x0, y1 - y0
        if bw <= 0 or bh <= 0:
            continue
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        if bw >= bh:
            t = bh
            L = _nearest(hb, size, cy, cx, y0 - t * 1.2, y1 + t * 1.2, bw * 0.9)
        else:
            t = bw
            L = _nearest(vb, size, cx, cy, x0 - t * 1.2, x1 + t * 1.2, bh * 0.9)
        if not L:
            continue
        matched += 1
        seen = set()
        for cm in vals:
            S = _snap(cm * 10.0 * PT_PER_MM / L)
            if S and S not in seen:
                seen.add(S)
                votes[S] = votes.get(S, 0) + 1
    res["matched"] = matched
    if votes:
        S, n = max(votes.items(), key=lambda kv: kv[1])
        if n >= 3 and n >= matched * 0.3:
            res["dims"], res["votes"] = S, n
    return res


def analyzer_main(job_conn, res_conn):
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
            res_conn.send((gen, pno, analyze(doc[pno])))
        except Exception as e:  # noqa
            res_conn.send((gen, pno, {"text": None, "dims": None, "votes": 0, "matched": 0, "err": str(e)}))
