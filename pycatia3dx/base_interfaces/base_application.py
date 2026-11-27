from __future__ import annotations

import builtins
import importlib.machinery
import importlib.util
import logging
import os
import pathlib
import subprocess
import sys
import time
from types import ModuleType
from typing import TYPE_CHECKING, Any, Callable

try:
    import psutil
except ImportError:  # pragma: no cover - optional when driving standalone tools
    psutil = None  # type: ignore[assignment]

try:
    import pythoncom
    from win32com.client import Dispatch, GetActiveObject
except ImportError:  # pragma: no cover - optional on non-Windows / solver environments
    pythoncom = None  # type: ignore[assignment]
    Dispatch = None  # type: ignore[assignment]
    GetActiveObject = None  # type: ignore[assignment]

if TYPE_CHECKING:
    from pycatia3dx.interfaces.application import Application

logger = logging.getLogger(__name__)

# Name under which the Dassault Systèmes module is registered in sys.modules.
_COM3DX_MODULE_NAME = "com3dx"

# Name of the replacement hasattr function installed by com3dx.py.
_COM3DX_HASATTR_NAME = "dbcHasattr"

# Known 3DEXPERIENCE / CATIA Application CLSIDs registered in Windows ROT / HKCR.
_KNOWN_3DX_CLSIDS = frozenset({
    "{7D2C8116-DC44-0000-0280-030BA6000000}".lower(),
    "{87FD6F40-E252-11D5-8040-0010B5FA1031}".lower(),
})

# Keep a reference to the genuine builtin hasattr as early as possible (i.e.
# when pycatia3dx is imported), before com3dx.py gets the chance to patch it.
_BUILTIN_HASATTR: Callable[[object, str], bool] | None = (
    builtins.hasattr if getattr(builtins.hasattr, "__name__", "") != _COM3DX_HASATTR_NAME else None
)


def _pure_python_hasattr(obj: object, name: str) -> bool:
    """
    Exact behavioural equivalent of the builtin :func:`hasattr`.

    Used as a last resort when the genuine builtin cannot be recovered because
    another module has already replaced ``builtins.hasattr``.
    """
    try:
        getattr(obj, name)
    except AttributeError:
        return False
    return True


def _original_hasattr() -> Callable[[object, str], bool]:
    """
    Return the genuine (un-patched) :func:`hasattr` function.

    ``com3dx.py`` replaces ``builtins.hasattr`` with its own ``dbcHasattr``
    which delegates to a module global ``_builtin_hasattr``. That global is only
    assigned when ``builtins.hasattr`` has not been patched yet. If the module
    is executed a second time (for example because it was imported by another
    tool, by a different module name, or by an older pycatia3dx version) the
    global is never assigned and every ``hasattr`` call in the process raises
    ``NameError: name '_builtin_hasattr' is not defined``.

    This function follows the chain of patched functions back to the original.
    """
    if _BUILTIN_HASATTR is not None:
        return _BUILTIN_HASATTR

    current = builtins.hasattr
    seen: set[int] = set()
    while getattr(current, "__name__", "") == _COM3DX_HASATTR_NAME and id(current) not in seen:
        seen.add(id(current))
        nxt = getattr(current, "__globals__", {}).get("_builtin_hasattr")
        if nxt is None:
            return _pure_python_hasattr
        current = nxt

    if getattr(current, "__name__", "") == _COM3DX_HASATTR_NAME:
        return _pure_python_hasattr
    return current


def _repair_patched_hasattr() -> None:
    """
    Make sure that every ``dbcHasattr`` currently installed (or reachable
    through the chain of patched functions) has a valid ``_builtin_hasattr``.

    This fixes processes where ``com3dx.py`` was loaded more than once before
    pycatia3dx got involved.
    """
    original = _original_hasattr()
    current = builtins.hasattr
    seen: set[int] = set()
    while getattr(current, "__name__", "") == _COM3DX_HASATTR_NAME and id(current) not in seen:
        seen.add(id(current))
        func_globals = getattr(current, "__globals__", None)
        if func_globals is None:
            break
        if func_globals.get("_builtin_hasattr") is None:
            func_globals["_builtin_hasattr"] = original
        current = func_globals["_builtin_hasattr"]


# Heal builtins.hasattr immediately at import time in case external code loaded
# com3dx.py multiple times before pycatia3dx was imported.
_repair_patched_hasattr()


def _iter_3dx_process_executables() -> tuple[bool, list[str]]:
    """
    Return ``(process_found, exe_paths)`` for running ``3DEXPERIENCE.exe`` or
    ``CNEXT.exe`` processes.

    Uses ``psutil`` when installed, falling back to Windows PowerShell process
    inspection if ``psutil`` is unavailable.
    """
    exe_paths: list[str] = []
    process_found = False

    if psutil is not None:
        for proc in psutil.process_iter(["name", "exe"]):
            try:
                name = (proc.info["name"] or "").lower()
                if name not in ("3dexperience.exe", "cnext.exe"):
                    continue
                process_found = True
                exe_location = proc.info["exe"]
                if exe_location:
                    exe_paths.append(exe_location)
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                continue
        return process_found, exe_paths

    if sys.platform == "win32":
        try:
            proc = subprocess.run(
                [
                    "powershell",
                    "-NoProfile",
                    "-NonInteractive",
                    "-Command",
                    "Get-Process -Name 3DEXPERIENCE,CNEXT -ErrorAction SilentlyContinue | "
                    "ForEach-Object { if ($_.Path) { $_.Path } else { '<RUNNING>' } }",
                ],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
            for raw_line in proc.stdout.splitlines():
                line = raw_line.strip()
                if not line:
                    continue
                process_found = True
                if line != "<RUNNING>":
                    exe_paths.append(line)
        except Exception:
            pass

    return process_found, exe_paths


def _get_com3dx_path() -> pathlib.Path:
    """
    Locate the ``com3dx.py`` module from a running 3DEXPERIENCE process OR from
    any discovered 3DEXPERIENCE installation on disk (via Windows Registry,
    COM ``LocalServer32``, or ``CATEnv`` files).

    Returns:
        pathlib.Path: Absolute path to the ``com3dx.py`` module.

    Raises:
        RuntimeError: If 3DEXPERIENCE is neither running nor installed.
        FileNotFoundError: If ``com3dx.py`` does not exist at the derived
            installation path.
    """
    process_found, exe_locations = _iter_3dx_process_executables()
    candidates: list[pathlib.Path] = [
        pathlib.Path(exe_location).parent.parent.joinpath("python3dx", "lib", "com3dx.py")
        for exe_location in exe_locations
    ]

    for candidate in candidates:
        try:
            if candidate.exists():
                return candidate
        except OSError:
            continue

    # Also check discovered installations on disk (Registry / LocalServer32 / CATEnv)
    try:
        from pycatia3dx.ecosystem.discovery import discover_3dx_installations

        for inst in discover_3dx_installations():
            if inst.com3dx_path is not None:
                try:
                    if inst.com3dx_path.exists():
                        return inst.com3dx_path
                except OSError:
                    continue
                candidates.append(inst.com3dx_path)
    except Exception:
        pass

    if not process_found and not candidates:
        raise RuntimeError(
            "3DEXPERIENCE.exe is not running. Please launch the application first."
        )

    raise FileNotFoundError(
        "Could not find com3dx.py at the expected location(s): "
        + ", ".join(str(c) for c in candidates)
    )


def _import_com3dx_module() -> ModuleType:
    """
    Dynamically import the Dassault Systèmes `com3dx` module using importlib.

    The module is executed only once per Python process and registered in
    ``sys.modules``. Before it is executed, the module namespace is seeded with
    a valid ``_builtin_hasattr`` so that ``com3dx.py`` can never end up with an
    undefined reference, whatever the state of ``builtins.hasattr``. No change
    to the 3DEXPERIENCE installation is required.

    Returns:
        ModuleType: The loaded `com3dx` module.

    Raises:
        ImportError: If the module specification or loader cannot be
            created or executed.
    """
    _repair_patched_hasattr()

    existing = sys.modules.get(_COM3DX_MODULE_NAME)
    if existing is not None and _pure_python_hasattr(existing, "get3dxClient"):
        return existing

    module_path = _get_com3dx_path()
    spec = importlib.util.spec_from_file_location(_COM3DX_MODULE_NAME, module_path)

    if spec is None or spec.loader is None:
        raise ImportError(f"Could not load module spec from {module_path}")

    com3dx = importlib.util.module_from_spec(spec)
    # Seed the global used by com3dx.dbcHasattr. com3dx.py overwrites it with
    # builtins.hasattr when that has not been patched yet, which is the same
    # function, so behaviour is unchanged in the normal case.
    com3dx.__dict__["_builtin_hasattr"] = _original_hasattr()

    lib_dir = str(module_path.parent)
    added_sys_path = False
    if lib_dir not in sys.path:
        sys.path.append(lib_dir)
        added_sys_path = True

    sys.modules[_COM3DX_MODULE_NAME] = com3dx
    try:
        spec.loader.exec_module(com3dx)
    except BaseException:
        sys.modules.pop(_COM3DX_MODULE_NAME, None)
        raise
    finally:
        if added_sys_path and lib_dir in sys.path:
            sys.path.remove(lib_dir)
        _repair_patched_hasattr()

    return com3dx


def _dispatch_com(obj: Any) -> Any:
    """Call the current ``win32com.client.Dispatch`` (including ``com3dx.Dispatch3dx``)."""
    import win32com.client

    return win32com.client.Dispatch(obj)


def _scan_rot_for_3dx_idisp() -> Any:
    """
    Scan the current thread's Running Object Table (ROT) for a 3DEXPERIENCE
    moniker (``!{87FD6F40-...}`` or ``!{7D2C8116-...}``) and return its raw
    ``PyIDispatch``.
    """
    if pythoncom is None:
        return None

    try:
        pythoncom.CoInitialize()
    except Exception:
        pass

    try:
        rot = pythoncom.GetRunningObjectTable()
        ctx = pythoncom.CreateBindCtx(0)
        rotenum = rot.EnumRunning()
        while True:
            monikers = rotenum.Next()
            if not monikers:
                break
            moniker = monikers[0]
            display_name = ""
            try:
                display_name = (moniker.GetDisplayName(ctx, None) or "").upper()
            except Exception:
                pass

            matched_name = (
                "87FD6F40-E252-11D5-8040-0010B5FA1031" in display_name
                or "7D2C8116-DC44-0000-0280-030BA6000000" in display_name
            )
            try:
                obj = rot.GetObject(moniker)
                idisp = obj.QueryInterface(pythoncom.IID_IDispatch)
                if matched_name:
                    return idisp
                if Dispatch is not None:
                    disp = Dispatch(idisp)
                    clsid = str(getattr(disp, "CLSID", "")).lower()
                    if clsid in _KNOWN_3DX_CLSIDS or str(getattr(disp, "Name", "")) == "3DEXPERIENCE":
                        return idisp
            except Exception:
                continue
    except Exception:
        pass

    return None


def _current_desktop_name() -> str:
    """Return the current thread's Windows desktop name (e.g. ``'Default'``)."""
    try:
        import win32api
        import win32service

        desk = win32service.GetThreadDesktop(win32api.GetCurrentThreadId())
        name = win32service.GetUserObjectInformation(desk, win32service.UOI_NAME)
        return str(name or "")
    except Exception:
        return ""


def _find_3dx_in_running_object_table(prog_id: str = "CATIA.Application") -> Any:
    """
    Search the Windows Running Object Table (ROT) for an active 3DEXPERIENCE
    COM session across both ``{87FD6F40-...}`` and ``{7D2C8116-...}`` CLSIDs.

    If the current thread is running on a non-``Default`` desktop (such as an
    isolated automation desktop), switches a helper thread to the ``Default``
    desktop **before** initializing COM on the main thread so Windows COM binds
    to the interactive desktop's ROT, and marshals ``IDispatch`` back via
    ``CoMarshalInterThreadInterfaceInStream``.
    """
    if pythoncom is None or Dispatch is None:
        return None

    desk_name = _current_desktop_name()
    if not desk_name or desk_name.lower() == "default":
        idisp = _scan_rot_for_3dx_idisp()
        if idisp is not None:
            return _dispatch_com(idisp)

    # Try switching a fresh helper thread to the interactive "Default" desktop
    # BEFORE calling CoInitialize() on the main thread.
    try:
        import threading
        import win32service

        stream_holder: list[Any] = []

        def _default_desktop_worker() -> None:
            try:
                hdesk = win32service.OpenDesktop("Default", 0, False, 0x01FF)
                hdesk.SetThreadDesktop()
            except Exception:
                return
            worker_idisp = _scan_rot_for_3dx_idisp()
            if worker_idisp is not None:
                try:
                    stream = pythoncom.CoMarshalInterThreadInterfaceInStream(
                        pythoncom.IID_IDispatch,
                        worker_idisp,
                    )
                    stream_holder.append(stream)
                except Exception:
                    pass

        t = threading.Thread(target=_default_desktop_worker, daemon=True)
        t.start()
        t.join(timeout=30.0)
        if stream_holder:
            try:
                pythoncom.CoInitialize()
            except Exception:
                pass
            unmarshaled = pythoncom.CoGetInterfaceAndReleaseStream(
                stream_holder[0],
                pythoncom.IID_IDispatch,
            )
            return _dispatch_com(unmarshaled)
    except Exception:
        pass

    if desk_name and desk_name.lower() != "default":
        idisp = _scan_rot_for_3dx_idisp()
        if idisp is not None:
            return _dispatch_com(idisp)

    if GetActiveObject is not None:
        try:
            active = GetActiveObject(prog_id)
            if active is not None:
                return _dispatch_com(active)
        except Exception:
            pass

    return None


def _try_acquire_3dx_client(com3dx_mod: ModuleType | None, prog_id: str) -> Any:
    """Try to obtain a live 3DEXPERIENCE COM client from ROT or ``com3dx``."""
    if com3dx_mod is not None:
        try:
            if _pure_python_hasattr(com3dx_mod, "com3dxInit"):
                com3dx_mod.com3dxInit()
            _repair_patched_hasattr()
        except Exception:
            pass

    # Fast check via ROT (handles both {87FD6F40...} and {7D2C8116...} and Default desktop marshaling)
    rot_client = _find_3dx_in_running_object_table(prog_id)
    if rot_client is not None:
        return rot_client

    if com3dx_mod is not None:
        try:
            client = com3dx_mod._get3dxClientViaObjectTable(quiet=True)
            if client is not None:
                return client
        except Exception:
            try:
                client = com3dx_mod.get3dxClient(quiet=True)
                if client is not None:
                    return client
            except TypeError:
                client = com3dx_mod.get3dxClient()
                if client is not None:
                    return client
            except Exception:
                pass

    return None


def catia_application(
    prog_id: str = "CATIA.Application",
    *,
    auto_launch: bool = False,
    launch_timeout: float = 120.0,
) -> "Application":
    """
    Connects to the active 3DEXPERIENCE session and returns a pycatia3dx
    Application object.

    Locates ``com3dx.py`` automatically from the running ``3DEXPERIENCE.exe``
    process or from any installed 3DEXPERIENCE release registered in Windows
    (even when installed in a custom directory or drive such as ``D:\\...``).

    If ``3DEXPERIENCE.exe`` is not running and ``auto_launch=True`` (or
    ``PYCATIA3DX_AUTO_LAUNCH=1`` is set), automatically launches
    ``3DEXPERIENCE.exe`` with its ``CATEnv`` environment and waits for the COM
    server to become ready.

    Usage:

    >>> from pycatia3dx import catia3dx
    >>> application = catia3dx()

    :param str prog_id: Fallback COM ProgID (default ``'CATIA.Application'``;
        can also be ``'DELMIA.Application'``).
    :param bool auto_launch: If ``True``, automatically launch ``3DEXPERIENCE.exe``
        when it is not already running.
    :param float launch_timeout: Seconds to wait for COM registration after launching.
    :return: Application
    """
    from pycatia3dx.interfaces.application import Application

    def check_catia_version(application: Application) -> bool:
        try:
            if application.name != "3DEXPERIENCE":
                return False
        except Exception:
            return False
        return True

    if os.environ.get("PYCATIA3DX_AUTO_LAUNCH", "").lower() in ("1", "true", "yes"):
        auto_launch = True

    # Ensure COM apartment is initialized on the calling thread on normal desktops
    # (helps GUI / web-backend worker threads without interfering with non-Default desktop marshaling).
    if pythoncom is not None and _current_desktop_name().lower() in ("", "default"):
        try:
            pythoncom.CoInitialize()
        except Exception:
            pass

    if prog_id != "CATIA.Application":
        if Dispatch is None:
            raise ImportError("pywin32 is required to dispatch COM objects on Windows.")
        app = Application(Dispatch(prog_id))
        return app

    process_found, _ = _iter_3dx_process_executables()
    if (
        not process_found
        and not auto_launch
        and sys.modules.get(_COM3DX_MODULE_NAME) is None
        and _find_3dx_in_running_object_table(prog_id) is None
    ):
        raise RuntimeError(
            "3DEXPERIENCE.exe is not running. Please launch the application first "
            "(or call catia3dx(auto_launch=True) / dx.launch())."
        )

    com3dx_mod: ModuleType | None = None
    com3dx_error: Exception | None = None

    if process_found or sys.modules.get(_COM3DX_MODULE_NAME) is not None:
        try:
            com3dx_mod = _import_com3dx_module()
        except Exception as exc:
            com3dx_error = exc

    raw_client = _try_acquire_3dx_client(com3dx_mod, prog_id) if (process_found or com3dx_mod is not None) else None

    # If 3DEXPERIENCE.exe is running (or mocked in tests) and com3dx returned a client or failed:
    if raw_client is None and process_found:
        if Dispatch is None:
            if com3dx_error is not None:
                raise ImportError(
                    "pywin32 (win32com) is required to connect to 3DEXPERIENCE COM."
                ) from com3dx_error
            raise ImportError("pywin32 (win32com) is required to connect to 3DEXPERIENCE COM.")
        logger.warning(
            f"Could not connect through com3dx ({type(com3dx_error).__name__ if com3dx_error else 'NoneResult'}). "
            f"Falling back to win32com.client.Dispatch({prog_id!r})."
        )
        try:
            raw_client = Dispatch(prog_id)
        except Exception as dispatch_error:
            if com3dx_error is not None:
                raise com3dx_error from dispatch_error
            raise

    # If 3DEXPERIENCE.exe is not running yet, auto-launch if requested
    if raw_client is None and not process_found:
        if not auto_launch:
            raise RuntimeError(
                "3DEXPERIENCE.exe is not running. Please launch the application first "
                "(or call catia3dx(auto_launch=True) / dx.launch())."
            )

        from pycatia3dx.ecosystem.discovery import get_primary_3dx_installation

        inst = get_primary_3dx_installation()
        if inst is None:
            raise RuntimeError(
                "3DEXPERIENCE.exe is not running and no 3DEXPERIENCE installation was found on this machine."
            )

        launch_cmd = inst.build_launch_command()
        logger.info(f"Launching 3DEXPERIENCE automatically: {' '.join(launch_cmd)}")
        subprocess.Popen(launch_cmd, env=inst.build_runtime_env())

        deadline = time.monotonic() + max(launch_timeout, 5.0)
        while time.monotonic() < deadline:
            time.sleep(2.0)
            if com3dx_mod is None:
                try:
                    com3dx_mod = _import_com3dx_module()
                except Exception:
                    pass
            raw_client = _try_acquire_3dx_client(com3dx_mod, prog_id)
            if raw_client is not None:
                break

        if raw_client is None and Dispatch is not None:
            raw_client = Dispatch(prog_id)

    if raw_client is None:
        raise RuntimeError(
            "3DEXPERIENCE.exe is not running or its COM server is not responding."
        )

    app = Application(raw_client)
    if not check_catia_version(app):
        app.logger.warning(f'You are not running CATIA 3DEXPERIENCE. Running "{app.name}".')
    return app
