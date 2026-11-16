# תקן ירוק — אפשרות 1: פתיחת אפליקציית "מילוי אוטומטי של תקן ירוק" (אתר הטפסים של טיקטין) בדפדפן,
# כשהטופס הפתוח בטיקטין PDF כבר טעון בה. המנוע והכללים הם של האפליקציה עצמה — אין כאן העתק שלהם.
# המודול נטען רק בלחיצה על הכפתור, כך שאינו מאט את עליית התוכנה.
import os
import threading
import urllib.request
import http.server
import socketserver

BASE = "https://raw.githubusercontent.com/tiktiny/tiktin-forms/main/green/"
SMALL = ("index.html", "templates.js", "logo.js", "font.js")              # מתעדכנים בכל פתיחה (כללים ונוסח)
BIG = ("pdf-lib.min.js", "fontkit.umd.min.js", "pdf.min.mjs", "pdf.worker.min.mjs")   # ספריות — נטענות פעם אחת
PORT = 51287          # פורט קבוע: כך החותמת שנשמרה בדפדפן נשמרת גם בפעם הבאה
TYPES = {".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8",
         ".mjs": "text/javascript; charset=utf-8", ".pdf": "application/pdf"}

_state = {"server": None, "pdf": b"", "name": "", "port": None, "src": "", "on_result": None}


def cache_dir():
    root = os.environ.get("LOCALAPPDATA") or os.path.join(os.path.expanduser("~"), ".cache")
    d = os.path.join(root, "TiktinPDF", "green")
    os.makedirs(d, exist_ok=True)
    return d


def _fetch(url):
    """הורדה דרך curl.exe של Windows (מובנה ב-Windows 10/11, משתמש בתעודות ובפרוקסי של המחשב).
    גיבוי: פייתון, אם יש בו תמיכה ב-HTTPS. (בחבילת התוכנה אין רכיב הצפנה של פייתון, כדי שתהיה קטנה.)"""
    import subprocess
    exe = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32", "curl.exe")
    if os.name == "nt" and os.path.exists(exe):
        try:
            r = subprocess.run([exe, "-fsSL", "--retry", "2", "--connect-timeout", "15", "--max-time", "120", url],
                               capture_output=True, timeout=150, creationflags=0x08000000)   # בלי חלון שחור
            if r.returncode == 0 and r.stdout:
                return r.stdout
        except Exception:
            pass
    with urllib.request.urlopen(url, timeout=20) as r:
        return r.read()


def update_files(progress=None):
    """מוריד את קבצי האפליקציה לתיקייה מקומית. בלי אינטרנט — משתמש בעותק הקודם (אם יש).
    מחזיר None כשהכול מוכן, או הודעת שגיאה בעברית."""
    d = cache_dir()
    todo = list(SMALL) + [f for f in BIG if not os.path.exists(os.path.join(d, f))]
    failed = []
    for k, f in enumerate(todo):
        if progress:
            progress(k, len(todo))
        try:
            data = _fetch(BASE + f)
            if len(data) < 50:
                raise IOError("empty")
            tmp = os.path.join(d, f + ".tmp")
            with open(tmp, "wb") as fh:
                fh.write(data)
            os.replace(tmp, os.path.join(d, f))
        except Exception:
            failed.append(f)
    missing = [f for f in SMALL + BIG if not os.path.exists(os.path.join(d, f))]
    if missing:
        return ("לא ניתן להוריד את אפליקציית התקן הירוק מהאינטרנט. "
                "ייתכן שחומת אש או אנטי-וירוס חוסמים את raw.githubusercontent.com. "
                "בפעם הראשונה צריך חיבור לאינטרנט — אחר כך היא עובדת גם בלי.")
    return None


def _loader():
    import json
    name = json.dumps(_state["name"], ensure_ascii=False)
    stem = json.dumps(os.path.splitext(_state["name"])[0], ensure_ascii=False)
    return ("<script type=\"module\">\n"
            "/* טיקטין PDF: הטופס הפתוח נטען אוטומטית */\n"
            "const r = await fetch('/__form.pdf?' + Date.now()); const b = new Uint8Array(await r.arrayBuffer());\n"
            "const go = () => window.__green ? window.__green.loadBytes(b, " + name + ") : setTimeout(go, 80); go();\n"
            "/* ייצוא PDF: הטופס הממולא והחתום חוזר לטיקטין PDF (נשמר ליד המקורי ונפתח בלשונית חדשה) */\n"
            "const dl = document.getElementById('dl');\n"
            "if (dl) { const sp = dl.querySelector('span'); if (sp) sp.textContent = 'שמירה ופתיחה בטיקטין PDF';\n"
            " dl.title = 'הטופס הממולא נשמר ליד הקובץ המקורי ונפתח בטיקטין PDF בלשונית חדשה';\n"
            " const note = (t, bad) => { let n = document.getElementById('__tkn'); if (!n) { n = document.createElement('div'); n.id = '__tkn';\n"
            "   n.style.cssText = 'position:fixed;left:16px;bottom:16px;z-index:9999;padding:10px 16px;border-radius:8px;color:#fff;font:15px Rubik,Arial;max-width:70vw'; document.body.appendChild(n); }\n"
            "   n.style.background = bad ? '#c8202f' : '#17364c'; n.textContent = t; n.style.display = 'block'; clearTimeout(n._t); n._t = setTimeout(() => n.style.display = 'none', 6000); };\n"
            " dl.onclick = async () => { const o = window.__green.out(); if (!o) return;\n"
            "  try { const r = await fetch('/__result', { method: 'POST', body: o });\n"
            "   const j = await r.json(); if (!j.ok) throw new Error(j.err || '');\n"
            "   note('נשמר ונפתח בטיקטין PDF: ' + j.name);\n"
            "  } catch (e) { note('לא הצלחתי להחזיר לטיקטין PDF (התוכנה סגורה?) – הקובץ יורד כרגיל', true);\n"
            "   const u = URL.createObjectURL(new Blob([o], { type: 'application/pdf' })); const a = document.createElement('a'); a.href = u;\n"
            "   a.download = " + stem + " + ' - ממולא וחתום.pdf'; document.body.appendChild(a); a.click(); a.remove(); } }; }\n"
            "</script>\n")


class _H(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, data, ctype):
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        path = self.path.split("?")[0].lstrip("/") or "index.html"
        if path == "__form.pdf":
            return self._send(_state["pdf"], TYPES[".pdf"])
        if "/" in path or "\\" in path or path.startswith(".") or path not in SMALL + BIG:
            self.send_error(404)
            return
        with open(os.path.join(cache_dir(), path), "rb") as fh:
            data = fh.read()
        if path == "index.html":
            html = data.decode("utf-8")
            i = html.rfind("</body>")
            html = html[:i] + _loader() + html[i:] if i >= 0 else html + _loader()
            data = html.encode("utf-8")
        self._send(data, TYPES.get(os.path.splitext(path)[1], "application/octet-stream"))


    def do_POST(self):
        import json
        if self.path.split("?")[0] != "/__result":
            self.send_error(404)
            return
        try:
            n = int(self.headers.get("Content-Length") or 0)
            data = self.rfile.read(n) if 0 < n < 200 * 1024 * 1024 else b""
            if not data.startswith(b"%PDF"):
                raise ValueError("not a pdf")
            path = save_result(data)
            cb = _state["on_result"]
            if cb:
                cb(path)
            ans = {"ok": True, "name": os.path.basename(path)}
        except Exception as e:
            ans = {"ok": False, "err": str(e)}
        self._send(json.dumps(ans, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")


def save_result(data):
    """שומר את הטופס הממולא ליד הקובץ המקורי: "<שם> - ממולא וחתום.pdf".
    אם הקובץ קיים ופתוח (נעול) — שם עם מספר; אם אין הרשאה לתיקייה — תיקיית המסמכים."""
    src = _state["src"]
    folder = os.path.dirname(src) if src else ""
    stem = os.path.splitext(os.path.basename(src or _state["name"] or "טופס"))[0]
    docs = os.path.join(os.path.expanduser("~"), "Documents")
    for d in [f for f in (folder, docs, os.path.expanduser("~")) if f]:
        for k in range(1, 30):
            p = os.path.join(d, stem + " - ממולא וחתום" + ("" if k == 1 else " (%d)" % k) + ".pdf")
            busy = _state.get("is_open")
            if busy and busy(p):          # פתוח כבר בטיקטין PDF — לא דורסים, שם חדש
                continue
            try:
                with open(p, "wb") as fh:
                    fh.write(data)
                return p
            except OSError:
                continue
    raise OSError("לא ניתן לשמור את הקובץ")


class _Srv(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def serve(pdf_bytes, name, src_path="", on_result=None, is_open=None):
    """מגיש את האפליקציה ואת הטופס במחשב המקומי בלבד (127.0.0.1). מחזיר את הכתובת לפתיחה בדפדפן.
    on_result(path) נקרא כשהטופס הממולא חוזר (מתהליך הרשת — לקרוא ממנו רק לאות Qt)."""
    _state["pdf"], _state["name"], _state["src"], _state["on_result"] = pdf_bytes, name, src_path, on_result
    _state["is_open"] = is_open
    if _state["server"] is None:
        srv = None
        for port in (PORT, PORT + 1, PORT + 2, 0):
            try:
                srv = _Srv(("127.0.0.1", port), _H)
                break
            except OSError:
                continue
        if srv is None:
            raise OSError("no port")
        _state["server"], _state["port"] = srv, srv.server_address[1]
        threading.Thread(target=srv.serve_forever, daemon=True).start()
    return "http://127.0.0.1:%d/index.html" % _state["port"]


def shutdown():
    if _state["server"] is not None:
        try:
            _state["server"].shutdown()
        except Exception:
            pass
