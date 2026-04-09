"""Vendor tool discovery — locates bundled and system-installed tools."""

from __future__ import annotations

import os
import shutil
from pathlib import Path

from src.config import ROOT_DIR, get_settings

VENDOR_DIR = ROOT_DIR / "vendor"
VENDORED_NGSPICE_VERSION = "46"

# ---------------------------------------------------------------------------
# NgSpice
# ---------------------------------------------------------------------------

_NGSPICE_SYSTEM_PATHS = [
    r"C:\Spice64\bin\ngspice.exe",
    r"C:\Spice64_dll\bin\ngspice.exe",
    r"C:\Program Files\Spice64\bin\ngspice.exe",
    r"C:\Program Files\ngspice\bin\ngspice.exe",
    "/usr/bin/ngspice",
    "/usr/local/bin/ngspice",
    "/opt/homebrew/bin/ngspice",
]


def find_ngspice() -> str | None:
    """Return path to ngspice executable (vendor first, then system)."""
    # 1. Bundled vendor copy
    vendor_exe = VENDOR_DIR / "Spice64" / "bin" / "ngspice_con.exe"
    if vendor_exe.is_file():
        return str(vendor_exe)

    # 2. Settings override
    settings = get_settings()
    ngspice_setting = getattr(settings, "ngspice_path", "")
    if ngspice_setting and os.path.isfile(ngspice_setting):
        return ngspice_setting

    # 3. System PATH
    found = shutil.which("ngspice")
    if found:
        return found

    # 4. Common install locations
    for p in _NGSPICE_SYSTEM_PATHS:
        if os.path.isfile(p):
            return p

    return None


# ---------------------------------------------------------------------------
# Freerouting
# ---------------------------------------------------------------------------

def find_freerouting_jar() -> str | None:
    """Return path to freerouting.jar (vendor first, then settings)."""
    # 1. Bundled vendor copy
    for name in sorted(VENDOR_DIR.glob("freerouting*.jar"), reverse=True):
        if name.is_file():
            return str(name)

    # 2. Settings override
    settings = get_settings()
    jar = settings.freerouting_jar
    if jar and Path(jar).is_file():
        return jar

    return None


def java_available() -> bool:
    """Check if Java runtime is available on the system."""
    import subprocess
    try:
        result = subprocess.run(
            ["java", "-version"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


# ---------------------------------------------------------------------------
# KiCad
# ---------------------------------------------------------------------------

_KICAD_SEARCH_DIRS = [
    r"C:\Program Files\KiCad",
]


def find_kicad() -> str | None:
    """Return path to KiCad installation directory."""
    # 1. Settings override
    settings = get_settings()
    if settings.kicad_path and Path(settings.kicad_path).is_dir():
        return settings.kicad_path

    # 2. Auto-detect from common locations
    for base in _KICAD_SEARCH_DIRS:
        base_path = Path(base)
        if not base_path.exists():
            continue
        # Find highest version subfolder (e.g., 9.0, 8.0)
        versions = sorted(
            [d for d in base_path.iterdir() if d.is_dir()],
            key=lambda d: d.name,
            reverse=True,
        )
        for v in versions:
            if (v / "bin" / "kicad.exe").is_file() or (v / "bin" / "kicad-cli.exe").is_file():
                return str(v)

    # 3. Check PATH
    kicad_cli = shutil.which("kicad-cli") or shutil.which("kicad")
    if kicad_cli:
        # Return the installation directory (2 levels up from bin/kicad.exe)
        return str(Path(kicad_cli).parent.parent)

    return None


def find_kicad_3dmodels() -> str | None:
    """Return path to KiCad 3D models directory."""
    settings = get_settings()
    if settings.kicad_3dmodels_path and Path(settings.kicad_3dmodels_path).is_dir():
        return settings.kicad_3dmodels_path

    kicad = find_kicad()
    if kicad:
        models_path = Path(kicad) / "share" / "kicad" / "3dmodels"
        if models_path.is_dir():
            return str(models_path)

    return None


# ---------------------------------------------------------------------------
# Status summary
# ---------------------------------------------------------------------------

def get_tool_status() -> dict[str, dict]:
    """Return detection status for all vendor tools."""
    ngspice = find_ngspice()
    fr_jar = find_freerouting_jar()
    kicad = find_kicad()
    kicad_3d = find_kicad_3dmodels()

    return {
        "ngspice": {
            "found": ngspice is not None,
            "path": ngspice or "",
            "version": VENDORED_NGSPICE_VERSION if ngspice and "vendor" in (ngspice or "") else "",
        },
        "freerouting": {
            "found": fr_jar is not None,
            "path": fr_jar or "",
            "java": java_available(),
        },
        "kicad": {
            "found": kicad is not None,
            "path": kicad or "",
            "models_3d": kicad_3d or "",
        },
    }
