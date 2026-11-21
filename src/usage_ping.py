# דיווח שימוש אנונימי לדוח היומי של המשרד: איזו תוכנה נפתחה, באיזו גרסה, סוג המכשיר ומיקום משוער.
# בלי שמות משתמשים, בלי שמות קבצים ובלי כתובות רשת. רץ ברקע כמה שניות אחרי הפתיחה — לא מאט את התוכנה.
import json
import os
import subprocess
import threading

URL = "https://script.google.com/macros/s/AKfycbx0AvcfW7qws-CUUZbpIsVILxuobq18sVkjw6NqULMxfhZnM6Xp8ClZQnW5dtooz90J/exec"
_NO_WINDOW = 0x08000000


def _curl():
    exe = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32", "curl.exe")
    return exe if os.name == "nt" and os.path.exists(exe) else None


def ping(app, target, vid):
    def run():
        exe = _curl()
        if not exe:
            return
        try:
            g = {}
            r = subprocess.run([exe, "-s", "--max-time", "8", "https://ipwho.is/?fields=country,city"],
                               capture_output=True, timeout=12, creationflags=_NO_WINDOW)
            try:
                g = json.loads(r.stdout or b"{}")
            except Exception:
                g = {}
            import platform
            body = json.dumps({"app": app, "action": "open", "target": target, "device": "מחשב",
                               "os": "Windows " + platform.release(), "browser": "תוכנה",
                               "country": g.get("country", ""), "city": g.get("city", ""), "vid": vid},
                              ensure_ascii=False).encode("utf-8")
            subprocess.run([exe, "-s", "-L", "--max-time", "15", "-H", "Content-Type: text/plain",
                            "--data-binary", "@-", URL], input=body, capture_output=True, timeout=20,
                           creationflags=_NO_WINDOW)
        except Exception:
            pass

    t = threading.Timer(8.0, run)
    t.daemon = True
    t.start()
