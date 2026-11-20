import multiprocessing as mp

if __name__ == "__main__":
    mp.freeze_support()
    import sys
    import threading

    # אם התוכנה כבר פתוחה: מעבירים אליה את הקובץ (ייפתח שם ככרטיסייה) ויוצאים מיד
    try:
        import single
        import brand
        if single.send_to_running([a for a in sys.argv[1:] if not a.startswith("-")], brand.PIPE_TAG):
            sys.exit(0)
    except Exception:
        pass

    def _preload():
        # מנוע ה-PDF נטען ברקע במקביל לטעינת הממשק — קיצור זמן העלייה
        try:
            import pymupdf  # noqa: F401
        except Exception:
            pass

    threading.Thread(target=_preload, daemon=True).start()
    from app import main
    sys.exit(main())
