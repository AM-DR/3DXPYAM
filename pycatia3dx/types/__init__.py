from __future__ import annotations

if __name__ == "types":
    # Defense-in-depth: if the inner `pycatia3dx/` directory was mistakenly added
    # to sys.path instead of the repository root, Python's stdlib (`enum`, `typing`,
    # `functools`) can accidentally load this file as top-level `types`.
    # Load and re-export Python's real stdlib `types.py` using only built-in C modules.
    import _io as _io
    import sys as _sys

    _here = (__file__ or "").replace("\\", "/").lower()
    for _entry in list(_sys.path):
        if not _entry:
            continue
        _cand = _entry.rstrip("/\\") + "/types.py"
        if _cand.replace("\\", "/").lower() == _here:
            continue
        try:
            with _io.open(_cand, "r", encoding="utf-8") as _fh:
                _src = _fh.read()
            _ns = {"__name__": "types", "__file__": _cand, "__builtins__": __builtins__}
            exec(compile(_src, _cand, "exec"), _ns)
            globals().update(_ns)
            break
        except OSError:
            continue
else:
    from typing import TYPE_CHECKING, Any

    from .general import CATVariant, Variant

    if TYPE_CHECKING:
        from .service import (
            ApplicationService,
            EditorService,
            application_service_types,
            editor_service_types,
        )

    _SERVICE_EXPORTS = frozenset({
        "ApplicationService",
        "EditorService",
        "application_service_types",
        "editor_service_types",
    })

    def __getattr__(name: str) -> Any:
        if name in _SERVICE_EXPORTS:
            from . import service as _service_mod

            val = getattr(_service_mod, name)
            globals()[name] = val
            return val
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

    __all__ = [
        "ApplicationService",
        "CATVariant",
        "EditorService",
        "Variant",
        "application_service_types",
        "editor_service_types",
    ]
