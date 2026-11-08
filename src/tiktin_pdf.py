import multiprocessing as mp

if __name__ == "__main__":
    mp.freeze_support()
    import sys
    from app import main
    sys.exit(main())
