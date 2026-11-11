import multiprocessing as mp

if __name__ == "__main__":
    mp.freeze_support()
    import sys
    import threading

    def _preload():
        # מנוע ה-PDF נטען ברקע במקביל לטעינת הממשק — קיצור זמן העלייה
        try:
            import pymupdf  # noqa: F401
        except Exception:
            pass

    threading.Thread(target=_preload, daemon=True).start()
    from app import main
    sys.exit(main())
