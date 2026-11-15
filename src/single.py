# מופע יחיד: כשמפעילים את התוכנה על קובץ נוסף והיא כבר פתוחה, הקובץ נשלח לחלון הפתוח
# ונפתח שם ככרטיסייה — במקום לפתוח את התוכנה פעם נוספת. מודול קל, בלי ממשק גרפי, כדי שההעברה תהיה מיידית.
import os
import sys
import getpass
import hashlib

AUTH = b"tiktin-pdf-single"


def address(tag="A"):
    user = hashlib.md5(getpass.getuser().encode("utf-8", "replace")).hexdigest()[:10]
    if sys.platform == "win32":
        return r"\\.\pipe\TiktinPDF-%s-%s" % (tag, user), "AF_PIPE"
    import tempfile
    return os.path.join(tempfile.gettempdir(), "tiktinpdf-%s-%s.sock" % (tag, user)), "AF_UNIX"


def send_to_running(paths, tag="A"):
    """מנסה להעביר את הקבצים לחלון שכבר פתוח. מחזיר True אם הצליח (ואז אין צורך להפעיל את התוכנה שוב)."""
    from multiprocessing.connection import Client
    addr, fam = address(tag)
    if fam == "AF_UNIX" and not os.path.exists(addr):
        return False
    try:
        c = Client(addr, family=fam, authkey=AUTH)
    except Exception:
        return False
    try:
        pid = c.recv()
        if sys.platform == "win32":
            try:
                import ctypes
                ctypes.windll.user32.AllowSetForegroundWindow(int(pid))     # מאפשר לחלון הפתוח לעלות לחזית
            except Exception:
                pass
        c.send([os.path.abspath(p) for p in paths])
        c.recv()
        return True
    except Exception:
        return False
    finally:
        try:
            c.close()
        except Exception:
            pass


def start_server(on_files, tag="A"):
    """מאזין ברקע לקבצים שנשלחים מהפעלות נוספות. on_files נקרא מתוך תהליכון רקע."""
    import threading
    from multiprocessing.connection import Listener
    addr, fam = address(tag)
    if fam == "AF_UNIX":
        try:
            os.unlink(addr)
        except OSError:
            pass
    try:
        lst = Listener(addr, family=fam, authkey=AUTH)
    except Exception:
        return None

    def loop():
        while True:
            try:
                c = lst.accept()
            except Exception:
                if getattr(lst, "_closed_by_app", False):
                    break
                continue
            try:
                c.send(os.getpid())
                paths = c.recv()
                on_files(list(paths))
                c.send("ok")
            except Exception:
                pass
            finally:
                try:
                    c.close()
                except Exception:
                    pass

    threading.Thread(target=loop, daemon=True).start()
    return lst
