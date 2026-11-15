# מקלדת עברית אוטומטית בזמן כתיבת טקסט על השרטוט
import sys


class HebrewKeyboard:
    """ב-Windows: מעביר את המקלדת לעברית בזמן הכתיבה ומחזיר את הקודמת בסיום."""

    def __init__(self):
        self.prev = None

    def on(self):
        if sys.platform != "win32":
            return
        try:
            import ctypes
            u = ctypes.windll.user32
            self.prev = u.GetKeyboardLayout(0)
            hkl = u.LoadKeyboardLayoutW("0000040D", 1)
            u.ActivateKeyboardLayout(hkl, 0)
        except Exception:
            pass

    def off(self):
        if sys.platform != "win32" or not self.prev:
            return
        try:
            import ctypes
            ctypes.windll.user32.ActivateKeyboardLayout(self.prev, 0)
        except Exception:
            pass
