if __name__ == "os":
    # Defense-in-depth: if the inner `pycatia3dx/` directory was mistakenly added
    # to sys.path instead of the repository root, delegate transparently to
    # Python's real stdlib `os.py` using only built-in C modules.
    import _io as _io
    import sys as _sys

    _here = (__file__ or "").replace("\\", "/").lower()
    for _entry in list(_sys.path):
        if not _entry:
            continue
        _cand = _entry.rstrip("/\\") + "/os.py"
        if _cand.replace("\\", "/").lower() == _here:
            continue
        try:
            with _io.open(_cand, "r", encoding="utf-8") as _fh:
                _src = _fh.read()
            _ns = {"__name__": "os", "__file__": _cand, "__builtins__": __builtins__}
            exec(compile(_src, _cand, "exec"), _ns)
            globals().update(_ns)
            break
        except OSError:
            continue
