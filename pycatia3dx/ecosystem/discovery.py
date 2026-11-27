"""
3DEXPERIENCE & Dassault Systèmes Installation, Registry, CATEnv, and Process Discovery.

Automatically locates 3DEXPERIENCE installations even when installed into custom
directories or separate drives (e.g. ``D:\\...``) and even when ``3DEXPERIENCE.exe``
is not currently running, by inspecting:

1. Running ``3DEXPERIENCE.exe`` / ``CNEXT.exe`` processes.
2. Windows COM Registry ``HKCR\\CATIA.Application\\CLSID`` -> ``LocalServer32``
   (which records the exact ``3DEXPERIENCE.exe -env ... -direnv ...`` command).
3. Windows Registry ``HKLM\\SOFTWARE\\Dassault Systemes`` & ``HKCU\\Software\\Dassault Systemes``
   (``V6\\B42x\\...`` keys containing ``Path``, ``Osds``, ``GAlevel``, ``ShortName``, ``LongName``).
4. ``CATEnv/*.txt`` environment files (parsing ``CATInstallPath`` and ``CATDLLPath``).
5. Standard installation directories across available drives.

Also provides :meth:`ThreeDXInstallation.build_runtime_env` to automatically
populate ``CATInstallPath``, ``CATDLLPath``, ``ABA_PATH``, ``PYTHONPATH``, and
``PATH`` from ``CATEnv/Env.txt`` so embedded solvers (``SMALauncher.exe``,
``SMAPython.exe``, ``SMATsoToscaOpt.exe``, ``SMAFsfDriverApplication.exe``,
``CATSTART.exe``, ``CATBatchStarter.exe``) work out-of-the-box without opening
any console or setting environment variables manually.
"""
from __future__ import annotations

import os
import pathlib
import re
import sys
from dataclasses import dataclass, field
from typing import Mapping, Sequence

try:
    import winreg
except ImportError:  # pragma: no cover - non-Windows
    winreg = None  # type: ignore[assignment]


def _safe_exists(p: pathlib.Path) -> bool:
    try:
        return p.exists()
    except OSError:
        return False


def _safe_is_dir(p: pathlib.Path) -> bool:
    try:
        return p.is_dir()
    except OSError:
        return False


def _safe_iterdir(p: pathlib.Path) -> list[pathlib.Path]:
    try:
        return list(p.iterdir())
    except OSError:
        return []


def _safe_glob(p: pathlib.Path, pattern: str) -> list[pathlib.Path]:
    try:
        return list(p.glob(pattern))
    except OSError:
        return []


_ENV_VAR_RE = re.compile(r"%([^%]+)%")


def parse_catenv_file(
    env_file: str | pathlib.Path,
    base_env: Mapping[str, str] | None = None,
) -> dict[str, str]:
    """
    Parse a Dassault Systèmes ``CATEnv/*.txt`` file (such as ``Env.txt``) into
    a dictionary of resolved environment variables.

    Expands ``CSIDL_APPDATA``, ``CSIDL_LOCAL_APPDATA``, ``CSIDL_PERSONAL``, and
    ``%VAR%`` placeholders automatically.
    """
    p = pathlib.Path(env_file)
    if not _safe_exists(p):
        return {}

    env_map: dict[str, str] = dict(base_env if base_env is not None else os.environ)
    appdata = env_map.get("APPDATA", str(pathlib.Path.home() / "AppData" / "Roaming"))
    local_appdata = env_map.get("LOCALAPPDATA", str(pathlib.Path.home() / "AppData" / "Local"))
    personal = str(pathlib.Path.home() / "Documents")

    parsed: dict[str, str] = {}
    try:
        lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return {}

    for raw_line in lines:
        line = raw_line.strip()
        if not line or line.startswith("!") or line.startswith("#") or "=" not in line:
            continue
        key, val = line.split("=", 1)
        key = key.strip()
        val = val.strip()
        if not key:
            continue

        val = (
            val.replace("CSIDL_LOCAL_APPDATA\\", local_appdata + "\\")
            .replace("CSIDL_LOCAL_APPDATA/", local_appdata + "/")
            .replace("CSIDL_LOCAL_APPDATA", local_appdata)
            .replace("CSIDL_APPDATA\\", appdata + "\\")
            .replace("CSIDL_APPDATA/", appdata + "/")
            .replace("CSIDL_APPDATA", appdata)
            .replace("CSIDL_PERSONAL\\", personal + "\\")
            .replace("CSIDL_PERSONAL/", personal + "/")
            .replace("CSIDL_PERSONAL", personal)
        )

        def _replace_var(match: re.Match[str]) -> str:
            var_name = match.group(1)
            if var_name in parsed:
                return parsed[var_name]
            return env_map.get(var_name, match.group(0))

        expanded = _ENV_VAR_RE.sub(_replace_var, val)
        parsed[key] = expanded
        env_map[key] = expanded

    return parsed


@dataclass
class ThreeDXInstallation:
    """Metadata describing a discovered Dassault Systèmes / 3DEXPERIENCE installation."""

    name: str
    root_dir: pathlib.Path
    bin_dir: pathlib.Path | None = None
    catenv_files: list[pathlib.Path] = field(default_factory=list)
    com3dx_path: pathlib.Path | None = None
    is_running: bool = False
    release: str = ""
    ga_level: str = ""
    default_env_name: str = ""
    catenv_dir: pathlib.Path | None = None

    @property
    def arch_dir(self) -> pathlib.Path | None:
        """Return the ``win_b64`` / ``linux_a64`` directory."""
        if self.bin_dir is not None and self.bin_dir.parent.name.lower() == "code":
            return self.bin_dir.parent.parent
        for arch in ("win_b64", "linux_a64"):
            cand = self.root_dir / arch
            if _safe_exists(cand):
                return cand
        return None

    @property
    def command_dir(self) -> pathlib.Path | None:
        arch = self.arch_dir
        if arch is not None:
            cand = arch / "code" / "command"
            if _safe_exists(cand):
                return cand
        return None

    @property
    def sma_python_path(self) -> pathlib.Path | None:
        """Return ``SMAPython.exe`` (or ``tools/SMApy/python3.10/python.exe``) if present."""
        exe = self.find_executable("SMAPython")
        if exe is not None:
            return exe
        arch = self.arch_dir
        if arch is not None:
            for rel in (
                pathlib.Path("tools") / "SMApy" / "python3.10" / "python.exe",
                pathlib.Path("code") / "python3.11" / "bin" / "python.exe",
            ):
                cand = arch / rel
                if _safe_exists(cand):
                    return cand
        return None

    @property
    def sma_launcher_path(self) -> pathlib.Path | None:
        """Return ``SMALauncher.exe`` (or ``ABQLauncher.exe``) if present."""
        for name in ("SMALauncher", "ABQLauncher", "SMAFeaExeLauncher"):
            exe = self.find_executable(name)
            if exe is not None:
                return exe
        return None

    def find_executable(self, binary_name: str) -> pathlib.Path | None:
        exts = ("", ".exe", ".bat", ".cmd") if sys.platform == "win32" else ("",)
        stem = binary_name
        for suffix in (".exe", ".bat", ".cmd"):
            if stem.lower().endswith(suffix):
                stem = stem[: -len(suffix)]
                break

        for folder in (self.bin_dir, self.command_dir):
            if folder is None or not _safe_exists(folder):
                continue
            for ext in exts:
                cand = folder / f"{stem}{ext}"
                if _safe_exists(cand):
                    return cand
        return None

    def is_primary_3dx(self) -> bool:
        """Return True if this installation contains the main client or SIMULIA solvers (not just CEF)."""
        if self.com3dx_path is not None and _safe_exists(self.com3dx_path):
            return True
        for bin_name in ("3DEXPERIENCE", "CNEXT", "CATSTART", "SMALauncher", "SMAPython"):
            if self.find_executable(bin_name) is not None:
                return True
        return False

    def build_launch_command(self, extra_args: Sequence[str] = ()) -> list[str]:
        """Build the command line to launch ``3DEXPERIENCE.exe`` with its ``CATEnv``."""
        exe = self.find_executable("3DEXPERIENCE") or self.find_executable("CNEXT")
        exe_str = str(exe) if exe is not None else "3DEXPERIENCE.exe"
        cmd = [exe_str]

        env_name = self.default_env_name
        env_dir = self.catenv_dir
        if not env_name or env_dir is None:
            local_env_dir = self.root_dir / "CATEnv"
            if _safe_exists(local_env_dir):
                txts = _safe_glob(local_env_dir, "*.txt")
                if txts:
                    env_name = env_name or txts[0].stem
                    env_dir = env_dir or local_env_dir
            elif self.catenv_files:
                env_name = env_name or self.catenv_files[0].stem
                env_dir = env_dir or self.catenv_files[0].parent

        if env_name:
            cmd.extend(["-env", env_name])
        if env_dir is not None:
            cmd.extend(["-direnv", str(env_dir)])
        cmd.extend(str(a) for a in extra_args)
        return cmd

    def build_runtime_env(self, base_env: Mapping[str, str] | None = None) -> dict[str, str]:
        """
        Construct a complete runtime environment dictionary for spawning embedded
        3DEXPERIENCE / CATIA / SIMULIA / Abaqus processes without manual setup.
        """
        env = dict(base_env if base_env is not None else os.environ)

        # 1. Load variables from the installation's CATEnv file (e.g. Env.txt)
        primary_catenv: pathlib.Path | None = None
        local_catenv_dir = self.catenv_dir or (self.root_dir / "CATEnv")
        if _safe_exists(local_catenv_dir):
            txts = _safe_glob(local_catenv_dir, "*.txt")
            if txts:
                primary_catenv = txts[0]
        if primary_catenv is None and self.catenv_files:
            primary_catenv = self.catenv_files[0]

        if primary_catenv is not None:
            parsed_env = parse_catenv_file(primary_catenv, env)
            for k, v in parsed_env.items():
                if v:
                    env[k] = v

        arch = self.arch_dir
        if arch is not None:
            code_dir = arch / "code"
            bin_dir = self.bin_dir or (code_dir / "bin")
            cmd_dir = code_dir / "command"
            smapy_dir = arch / "tools" / "SMApy" / "python3.10"

            env.setdefault("CATInstallPath", str(arch))
            env.setdefault("CATDLLPath", str(bin_dir))

            # Set ABA_PATH required by SMAPython.exe / OdbApi / SimApi / SMALauncher.exe
            aba_parts = [
                str(self.root_dir),
                str(arch),
                str(code_dir),
                str(bin_dir),
                str(bin_dir / "SMAExternal"),
                str(arch / "SMA"),
            ]
            env.setdefault("ABA_PATH", ";".join(aba_parts))

            # Prepend key binary & command directories to PATH
            path_prepend = [
                str(p)
                for p in (
                    bin_dir,
                    cmd_dir,
                    code_dir / "bin_trusted",
                    code_dir / "command_trusted",
                    smapy_dir,
                )
                if _safe_exists(p)
            ]
            existing_path = env.get("PATH", "")
            env["PATH"] = ";".join([*path_prepend, existing_path]) if existing_path else ";".join(path_prepend)

            # Populate PYTHONPATH for embedded Abaqus / SIMULIA / com3dx / SimProcess modules
            py_paths = [
                str(p)
                for p in (
                    code_dir / "python3.10" / "lib",
                    bin_dir,
                    code_dir / "python3dx" / "lib",
                    cmd_dir,
                    code_dir / "simProcessAPIs" / "lib",
                )
                if _safe_exists(p)
            ]
            if py_paths:
                existing_py = env.get("PYTHONPATH", "")
                env["PYTHONPATH"] = ";".join([*py_paths, existing_py]) if existing_py else ";".join(py_paths)

        return env


_LOCALSERVER_RE = re.compile(
    r'^\s*(?:"([^"]+)"|(\S+))(?:\s+(.*))?$'
)
_ARG_ENV_RE = re.compile(r'-env\s+(?:"([^"]+)"|(\S+))', re.IGNORECASE)
_ARG_DIRENV_RE = re.compile(r'-direnv\s+(?:"([^"]+)"|(\S+))', re.IGNORECASE)


def _discover_from_com_localserver() -> list[dict[str, str]]:
    """
    Inspect ``HKCR\\CATIA.Application\\CLSID`` and 3DEXPERIENCE CLSIDs for
    ``LocalServer32`` command lines (which record custom install paths & CATEnv).
    """
    if winreg is None:
        return []

    clsids: list[str] = [
        "{87fd6f40-e252-11d5-8040-0010b5fa1031}",
        "{7D2C8116-DC44-0000-0280-030BA6000000}",
    ]
    for prog_id in ("CATIA.Application", "CATIA.Application.1", "DELMIA.Application"):
        try:
            with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, f"{prog_id}\\CLSID") as k:
                clsid_val, _ = winreg.QueryValueEx(k, "")
                if isinstance(clsid_val, str) and clsid_val not in clsids:
                    clsids.insert(0, clsid_val)
        except OSError:
            continue

    results: list[dict[str, str]] = []
    for clsid in clsids:
        try:
            with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, f"CLSID\\{clsid}\\LocalServer32") as k:
                cmd_str, _ = winreg.QueryValueEx(k, "")
        except OSError:
            continue
        if not isinstance(cmd_str, str) or not cmd_str.strip():
            continue
        m = _LOCALSERVER_RE.match(cmd_str.strip())
        if not m:
            continue
        exe_path = m.group(1) or m.group(2) or ""
        rest_args = m.group(3) or ""
        env_match = _ARG_ENV_RE.search(rest_args)
        direnv_match = _ARG_DIRENV_RE.search(rest_args)
        env_name = (env_match.group(1) or env_match.group(2)) if env_match else ""
        direnv = (direnv_match.group(1) or direnv_match.group(2)) if direnv_match else ""
        if exe_path:
            results.append({
                "exe_path": exe_path,
                "env_name": env_name,
                "direnv": direnv,
            })
    return results


def _discover_from_ds_registry() -> list[dict[str, str]]:
    """
    Scan ``HKLM\\SOFTWARE\\Dassault Systemes`` and ``HKCU\\Software\\Dassault Systemes``
    for V6 / B42x / R202x installation entries.
    """
    if winreg is None:
        return []

    records: list[dict[str, str]] = []

    def _walk_key(hive: int, key_path: str, depth: int = 0) -> None:
        if depth > 5:
            return
        try:
            with winreg.OpenKey(hive, key_path) as k:
                values: dict[str, str] = {}
                idx = 0
                while True:
                    try:
                        vname, vval, _ = winreg.EnumValue(k, idx)
                        if isinstance(vval, str):
                            values[vname] = vval
                        idx += 1
                    except OSError:
                        break

                install_path = values.get("Path") or values.get("DEST_FOLDER")
                if install_path:
                    records.append({
                        "root_dir": install_path,
                        "osds": values.get("Osds", "win_b64"),
                        "ga_level": values.get("GAlevel", ""),
                        "short_name": values.get("ShortName", ""),
                        "long_name": values.get("LongName", ""),
                        "type": values.get("Type", ""),
                    })

                idx = 0
                while True:
                    try:
                        sub = winreg.EnumKey(k, idx)
                        if sub != "prd":  # skip huge product module lists
                            _walk_key(hive, f"{key_path}\\{sub}", depth + 1)
                        idx += 1
                    except OSError:
                        break
        except OSError:
            return

    for hive in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
        for base_path in (
            r"SOFTWARE\Dassault Systemes",
            r"SOFTWARE\WOW6432Node\Dassault Systemes",
        ):
            _walk_key(hive, base_path)

    return records


def _collect_catenv_files(install_roots: Sequence[pathlib.Path] = ()) -> list[pathlib.Path]:
    found: list[pathlib.Path] = []
    seen: set[pathlib.Path] = set()

    def _add_file(f: pathlib.Path) -> None:
        if f not in seen and _safe_exists(f):
            seen.add(f)
            found.append(f)

    # 1. Installation-local CATEnv folders first (e.g. D:\DassaultSystemes\B429\CATEnv\Env.txt)
    for root in install_roots:
        local_catenv = root / "CATEnv"
        if _safe_exists(local_catenv):
            for f in sorted(_safe_glob(local_catenv, "*.txt")):
                _add_file(f)

    # 2. LocalServer32 -direnv folder
    for entry in _discover_from_com_localserver():
        if entry.get("direnv"):
            dpath = pathlib.Path(entry["direnv"])
            if _safe_exists(dpath):
                for f in sorted(_safe_glob(dpath, "*.txt")):
                    _add_file(f)

    # 3. Standard user/system CATEnv folders
    roots: list[pathlib.Path] = []
    if sys.platform == "win32":
        prog_data = os.environ.get("ProgramData", r"C:\ProgramData")
        local_app = os.environ.get("LOCALAPPDATA", "")
        appdata = os.environ.get("APPDATA", "")
        for base in (prog_data, local_app, appdata):
            if base:
                roots.append(pathlib.Path(base) / "DassaultSystemes" / "CATEnv")
    else:
        home = pathlib.Path.home()
        roots.extend([
            home / "CATEnv",
            pathlib.Path("/var/DassaultSystemes/CATEnv"),
        ])

    for folder in roots:
        if _safe_exists(folder):
            for f in sorted(_safe_glob(folder, "*.txt")):
                _add_file(f)

    return found


def _build_installation_from_root(
    root_dir: pathlib.Path,
    *,
    osds: str = "win_b64",
    is_running: bool = False,
    release: str = "",
    ga_level: str = "",
    long_name: str = "",
    default_env_name: str = "",
    catenv_dir: pathlib.Path | None = None,
) -> ThreeDXInstallation | None:
    arch_candidates = [osds, "win_b64", "linux_a64"]
    bin_dir: pathlib.Path | None = None
    arch_dir: pathlib.Path | None = None

    # Handle case where root_dir is already the win_b64 directory
    if root_dir.name.lower() in ("win_b64", "linux_a64") and _safe_exists(root_dir / "code" / "bin"):
        arch_dir = root_dir
        bin_dir = root_dir / "code" / "bin"
        root_dir = root_dir.parent
    else:
        for arch in dict.fromkeys(arch_candidates):
            cand_bin = root_dir / arch / "code" / "bin"
            if _safe_exists(cand_bin):
                arch_dir = root_dir / arch
                bin_dir = cand_bin
                break

    if bin_dir is None or arch_dir is None:
        return None

    com3dx = arch_dir / "code" / "python3dx" / "lib" / "com3dx.py"
    local_catenv_dir = catenv_dir or (root_dir / "CATEnv")
    local_catenvs: list[pathlib.Path] = []
    if _safe_exists(local_catenv_dir):
        local_catenvs = sorted(_safe_glob(local_catenv_dir, "*.txt"))
        if not default_env_name and local_catenvs:
            default_env_name = local_catenvs[0].stem

    display_name = long_name or release or ga_level or root_dir.name
    return ThreeDXInstallation(
        name=display_name,
        root_dir=root_dir,
        bin_dir=bin_dir,
        catenv_files=local_catenvs,
        com3dx_path=com3dx if _safe_exists(com3dx) else None,
        is_running=is_running,
        release=release,
        ga_level=ga_level,
        default_env_name=default_env_name,
        catenv_dir=local_catenv_dir if _safe_exists(local_catenv_dir) else None,
    )


def discover_3dx_installations(*, include_auxiliary: bool = False) -> list[ThreeDXInstallation]:
    """
    Scan running processes, Windows COM ``LocalServer32``, Dassault Systèmes
    Registry keys, ``CATEnv`` files, and standard directories for 3DEXPERIENCE
    installations.

    Primary installations (containing ``3DEXPERIENCE.exe``, ``CNEXT.exe``,
    ``SMALauncher.exe``, or ``com3dx.py``) are always ordered first. Auxiliary
    shared components such as ``CEF`` are excluded by default unless no primary
    installation exists or ``include_auxiliary=True``.
    """
    installations: dict[pathlib.Path, ThreeDXInstallation] = {}

    def _register(inst: ThreeDXInstallation | None) -> None:
        if inst is None:
            return
        key = inst.root_dir
        existing = installations.get(key)
        if existing is None:
            installations[key] = inst
        else:
            if inst.is_running:
                existing.is_running = True
            if inst.release and not existing.release:
                existing.release = inst.release
            if inst.ga_level and not existing.ga_level:
                existing.ga_level = inst.ga_level
            if inst.default_env_name and not existing.default_env_name:
                existing.default_env_name = inst.default_env_name
            if inst.catenv_dir and not existing.catenv_dir:
                existing.catenv_dir = inst.catenv_dir
            if inst.name and existing.name == existing.root_dir.name:
                existing.name = inst.name

    # 1. Running 3DEXPERIENCE.exe processes
    from pycatia3dx.base_interfaces.base_application import _iter_3dx_process_executables

    _, running_exes = _iter_3dx_process_executables()
    for exe_str in running_exes:
        exe_path = pathlib.Path(exe_str)
        bin_dir = exe_path.parent
        root_dir = bin_dir.parent.parent.parent if bin_dir.name.lower() == "bin" else bin_dir
        _register(_build_installation_from_root(root_dir, is_running=True))

    # 2. Explicit environment variables
    for env_var in ("THREE_DX_ROOT", "CATIA_3DX_ROOT", "CATInstallPath"):
        raw_val = os.environ.get(env_var, "")
        for part in raw_val.split(";"):
            part = part.strip()
            if part and "%" not in part:
                p = pathlib.Path(part)
                if _safe_exists(p):
                    _register(_build_installation_from_root(p))

    # 3. Windows COM LocalServer32 (CATIA.Application -> exact exe, -env, -direnv)
    for ls_entry in _discover_from_com_localserver():
        exe_path = pathlib.Path(ls_entry["exe_path"])
        if _safe_exists(exe_path):
            bin_dir = exe_path.parent
            root_dir = bin_dir.parent.parent.parent if bin_dir.name.lower() == "bin" else bin_dir
            direnv_path = pathlib.Path(ls_entry["direnv"]) if ls_entry.get("direnv") else None
            _register(
                _build_installation_from_root(
                    root_dir,
                    default_env_name=ls_entry.get("env_name", ""),
                    catenv_dir=direnv_path,
                )
            )

    # 4. Windows Registry (HKLM / HKCU SOFTWARE\Dassault Systemes\V6\...)
    for reg_entry in _discover_from_ds_registry():
        root_p = pathlib.Path(reg_entry["root_dir"])
        if _safe_exists(root_p):
            _register(
                _build_installation_from_root(
                    root_p,
                    osds=reg_entry.get("osds", "win_b64"),
                    release=reg_entry.get("short_name", ""),
                    ga_level=reg_entry.get("ga_level", ""),
                    long_name=reg_entry.get("long_name", ""),
                )
            )

    # 5. Standard filesystem locations across drives
    candidate_parents: list[pathlib.Path] = []
    if sys.platform == "win32":
        for drive in ("C:\\", "D:\\", "E:\\"):
            d = pathlib.Path(drive)
            if not _safe_exists(d):
                continue
            candidate_parents.extend([
                d / "Program Files" / "Dassault Systemes",
                d / "Dassault Systemes",
            ])
        local_app = os.environ.get("LOCALAPPDATA")
        if local_app:
            candidate_parents.append(pathlib.Path(local_app) / "DassaultSystemes")
    else:
        candidate_parents.extend([
            pathlib.Path("/usr/DassaultSystemes"),
            pathlib.Path("/opt/DassaultSystemes"),
        ])

    for parent in candidate_parents:
        if not _safe_exists(parent):
            continue
        for child in sorted(_safe_iterdir(parent), reverse=True):
            if _safe_is_dir(child):
                _register(_build_installation_from_root(child))

    # Attach global CATEnv files and discover any roots referenced inside CATInstallPath
    all_catenvs = _collect_catenv_files(list(installations.keys()))
    for env_file in all_catenvs:
        parsed = parse_catenv_file(env_file)
        cat_install = parsed.get("CATInstallPath", "")
        for part in cat_install.split(";"):
            part = part.strip()
            if part and "%" not in part:
                p = pathlib.Path(part)
                if _safe_exists(p):
                    _register(_build_installation_from_root(p))

    all_catenvs = _collect_catenv_files(list(installations.keys()))
    for inst in installations.values():
        merged = list(inst.catenv_files)
        for cf in all_catenvs:
            if cf not in merged:
                merged.append(cf)
        inst.catenv_files = merged

    # Sort: running first, then primary 3DEXPERIENCE installations (with com3dx / 3DEXPERIENCE.exe), then auxiliary
    sorted_installs = sorted(
        installations.values(),
        key=lambda i: (
            not i.is_running,
            not i.is_primary_3dx(),
            i.com3dx_path is None,
        ),
    )

    if not include_auxiliary:
        primary = [i for i in sorted_installs if i.is_primary_3dx()]
        if primary:
            return primary

    return sorted_installs


def get_primary_3dx_installation() -> ThreeDXInstallation | None:
    """Return the active or primary discovered 3DEXPERIENCE installation on this machine."""
    installs = discover_3dx_installations(include_auxiliary=False)
    return installs[0] if installs else None


def discover_ecosystem_summary() -> dict[str, object]:
    """Return a diagnostic dictionary of discovered 3DEXPERIENCE installations."""
    installs = discover_3dx_installations(include_auxiliary=False)
    roots = [i.root_dir for i in installs]
    return {
        "3dexperience_installations": [
            {
                "name": inst.name,
                "release": inst.release,
                "ga_level": inst.ga_level,
                "root_dir": str(inst.root_dir),
                "bin_dir": str(inst.bin_dir) if inst.bin_dir else None,
                "catenv_dir": str(inst.catenv_dir) if inst.catenv_dir else None,
                "default_env_name": inst.default_env_name,
                "com3dx_available": inst.com3dx_path is not None,
                "com3dx_path": str(inst.com3dx_path) if inst.com3dx_path else None,
                "is_running": inst.is_running,
            }
            for inst in installs
        ],
        "catenv_files": [str(p) for p in _collect_catenv_files(roots)],
    }
