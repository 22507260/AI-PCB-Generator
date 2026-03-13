"""Model registry — maps component packages to KiCad 3D model files.

Auto-detects KiCad installation, maps (category, package) pairs to .wrl
file paths, and caches parsed Mesh3D objects in memory.
"""

from __future__ import annotations

import glob
import os
import re
from functools import lru_cache
from pathlib import Path
from typing import Optional

from src.models.vrml_parser import Mesh3D, parse_vrml
from src.utils.logger import get_logger

log = get_logger("models.registry")

# ── KiCad auto-detection ──────────────────────────────────────────────────

def _find_kicad_3dmodels() -> Optional[str]:
    """Auto-detect KiCad 3D models directory on Windows."""
    base = r"C:\Program Files\KiCad"
    if not os.path.isdir(base):
        return None
    # Try versioned subdirectories in descending order (newest first)
    candidates = sorted(
        [d for d in os.listdir(base) if os.path.isdir(os.path.join(base, d))],
        reverse=True,
    )
    for ver in candidates:
        models_dir = os.path.join(base, ver, "share", "kicad", "3dmodels")
        if os.path.isdir(models_dir):
            return models_dir
    return None


# ── Package → WRL mapping rules ──────────────────────────────────────────

# Maps AI-generated package strings to (library_dir_prefix, filename_pattern).
# Entries are checked in order; first match wins.

_METRIC_SIZES = {
    "01005": "0402Metric",
    "0201": "0603Metric",
    "0402": "1005Metric",
    "0603": "1608Metric",
    "0805": "2012Metric",
    "1206": "3216Metric",
    "1210": "3225Metric",
    "1812": "4532Metric",
    "2010": "5025Metric",
    "2512": "6332Metric",
}


def _map_package(category: str, package: str, models_dir: str) -> Optional[str]:
    """Map a component (category, package) to a .wrl file path.

    Returns the full path to the .wrl file, or None if no match found.
    """
    pkg = package.strip()
    pkg_upper = pkg.upper()

    # ── SMD passives (resistor, capacitor, inductor, diode, LED) ──
    if pkg_upper in _METRIC_SIZES or pkg_upper.startswith("LED_"):
        metric = _METRIC_SIZES.get(pkg_upper, "")
        if category == "resistor":
            if metric:
                path = os.path.join(models_dir, "Resistor_SMD.3dshapes",
                                    f"R_{pkg_upper}_{metric}.wrl")
                if os.path.isfile(path):
                    return path
        elif category in ("capacitor", "cap_ceramic"):
            if metric:
                path = os.path.join(models_dir, "Capacitor_SMD.3dshapes",
                                    f"C_{pkg_upper}_{metric}.wrl")
                if os.path.isfile(path):
                    return path
        elif category == "inductor":
            if metric:
                path = os.path.join(models_dir, "Inductor_SMD.3dshapes",
                                    f"L_{pkg_upper}_{metric}.wrl")
                if os.path.isfile(path):
                    return path
        elif category in ("diode", "led"):
            if metric:
                dirs = ["LED_SMD.3dshapes", "Diode_SMD.3dshapes"]
                prefixes = ["LED_", "D_"]
                for d, pfx in zip(dirs, prefixes):
                    path = os.path.join(models_dir, d,
                                        f"{pfx}{pkg_upper}_{metric}.wrl")
                    if os.path.isfile(path):
                        return path
        # Try LED special pattern  LED_0805 → LED_0805_2012Metric
        if pkg_upper.startswith("LED_"):
            size_part = pkg_upper.replace("LED_", "")
            metric = _METRIC_SIZES.get(size_part, "")
            if metric:
                path = os.path.join(models_dir, "LED_SMD.3dshapes",
                                    f"LED_{size_part}_{metric}.wrl")
                if os.path.isfile(path):
                    return path

    # ── DIP packages ──
    if pkg_upper.startswith("DIP-") or pkg_upper.startswith("DIP"):
        # Extract pin count: DIP-8 → 8
        m = re.search(r'(\d+)', pkg_upper)
        if m:
            pins = m.group(1)
            # Try standard 7.62mm width first
            path = os.path.join(models_dir, "Package_DIP.3dshapes",
                                f"DIP-{pins}_W7.62mm.wrl")
            if os.path.isfile(path):
                return path
            # Try 10.16mm
            path = os.path.join(models_dir, "Package_DIP.3dshapes",
                                f"DIP-{pins}_W10.16mm.wrl")
            if os.path.isfile(path):
                return path

    # ── TO-220 / TO-92 / SOT packages (THT) ──
    if pkg_upper.startswith("TO-220"):
        # Extract pin count variant: TO-220-3 → TO-220-3_Vertical.wrl
        path = os.path.join(models_dir, "Package_TO_SOT_THT.3dshapes",
                            f"{pkg}_Vertical.wrl")
        if os.path.isfile(path):
            return path
        # Bare TO-220 defaults to 3-pin
        if pkg_upper == "TO-220":
            path = os.path.join(models_dir, "Package_TO_SOT_THT.3dshapes",
                                "TO-220-3_Vertical.wrl")
            if os.path.isfile(path):
                return path
        # Try exact match
        path = os.path.join(models_dir, "Package_TO_SOT_THT.3dshapes",
                            f"{pkg}.wrl")
        if os.path.isfile(path):
            return path

    if pkg_upper.startswith("TO-92"):
        path = os.path.join(models_dir, "Package_TO_SOT_THT.3dshapes",
                            f"{pkg}.wrl")
        if os.path.isfile(path):
            return path
        path = os.path.join(models_dir, "Package_TO_SOT_THT.3dshapes",
                            "TO-92.wrl")
        if os.path.isfile(path):
            return path

    # ── SOT-23 / SOT-89 etc (SMD) ──
    if pkg_upper.startswith("SOT-"):
        path = os.path.join(models_dir, "Package_TO_SOT_SMD.3dshapes",
                            f"{pkg}.wrl")
        if os.path.isfile(path):
            return path
        # SOT-23 without pin count
        if pkg_upper == "SOT-23":
            path = os.path.join(models_dir, "Package_TO_SOT_SMD.3dshapes",
                                "SOT-23.wrl")
            if os.path.isfile(path):
                return path

    # ── SOIC packages ──
    if pkg_upper.startswith("SOIC"):
        m = re.search(r'(\d+)', pkg_upper)
        if m:
            pins = m.group(1)
            path = os.path.join(models_dir, "Package_SO.3dshapes",
                                f"SOIC-{pins}_3.9x4.9mm_P1.27mm.wrl")
            if os.path.isfile(path):
                return path

    # ── TQFP / LQFP / QFP packages ──
    if any(pkg_upper.startswith(p) for p in ("TQFP-", "LQFP-", "QFP-")):
        _glob_results = glob.glob(
            os.path.join(models_dir, "Package_QFP.3dshapes", f"{pkg}*.wrl"))
        if _glob_results:
            return _glob_results[0]

    # ── QFN / DFN packages ──
    if any(pkg_upper.startswith(p) for p in ("QFN-", "DFN-")):
        _glob_results = glob.glob(
            os.path.join(models_dir, "Package_DFN_QFN.3dshapes", f"{pkg}*.wrl"))
        if _glob_results:
            return _glob_results[0]

    # ── PinHeader connectors ──
    if "PINHEADER" in pkg_upper or pkg_upper.startswith("PINHEADER"):
        # PinHeader_1x02_P2.54mm → PinHeader_1x02_P2.54mm_Vertical.wrl
        path = os.path.join(models_dir, "Connector_PinHeader_2.54mm.3dshapes",
                            f"{pkg}_Vertical.wrl")
        if os.path.isfile(path):
            return path
        path = os.path.join(models_dir, "Connector_PinHeader_2.54mm.3dshapes",
                            f"{pkg}.wrl")
        if os.path.isfile(path):
            return path

    # Bare RxC notation for connectors: "1x04", "2x05"
    if category == "connector" and re.match(r'^\d+x\d+$', pkg, re.IGNORECASE):
        rows, cols = pkg.split("x")
        path = os.path.join(
            models_dir, "Connector_PinHeader_2.54mm.3dshapes",
            f"PinHeader_{rows}x{cols.zfill(2)}_P2.54mm_Vertical.wrl")
        if os.path.isfile(path):
            return path

    # If the package string looks like a PinHeader dimension e.g. "Conn_01x02"
    if pkg_upper.startswith("CONN_01X") or pkg_upper.startswith("CONN_02X"):
        m = re.match(r'CONN_(\d+)X(\d+)', pkg_upper)
        if m:
            rows, cols = m.group(1), m.group(2)
            if rows == "01":
                path = os.path.join(
                    models_dir, "Connector_PinHeader_2.54mm.3dshapes",
                    f"PinHeader_1x{cols.zfill(2)}_P2.54mm_Vertical.wrl")
                if os.path.isfile(path):
                    return path
            elif rows == "02":
                path = os.path.join(
                    models_dir, "Connector_PinHeader_2.54mm.3dshapes",
                    f"PinHeader_2x{cols.zfill(2)}_P2.54mm_Vertical.wrl")
                if os.path.isfile(path):
                    return path

    # ── Crystal ──
    if category == "crystal":
        _glob_results = glob.glob(
            os.path.join(models_dir, "Crystal.3dshapes", "*.wrl"))
        if _glob_results:
            return _glob_results[0]

    # ── Electrolytic capacitors (THT) ──
    if category == "cap_electrolytic":
        _glob_results = glob.glob(
            os.path.join(models_dir, "Capacitor_THT.3dshapes", "CP_Radial*D5.0*P2.5*.wrl"))
        if _glob_results:
            return _glob_results[0]
        _glob_results = glob.glob(
            os.path.join(models_dir, "Capacitor_THT.3dshapes", "CP_Radial*.wrl"))
        if _glob_results:
            return _glob_results[0]

    # ── Fallback: glob search across all .3dshapes directories ──
    if pkg:
        # Sanitise package name for glob
        safe_pkg = pkg.replace("(", "[").replace(")", "]")
        _glob_results = glob.glob(
            os.path.join(models_dir, "*.3dshapes", f"*{safe_pkg}*.wrl"))
        if _glob_results:
            return _glob_results[0]

    return None


# ── Registry class ────────────────────────────────────────────────────────

class ModelRegistry:
    """Manages KiCad 3D model lookup and caching."""

    def __init__(self, models_dir: str = ""):
        if models_dir and os.path.isdir(models_dir):
            self._models_dir = models_dir
        else:
            self._models_dir = _find_kicad_3dmodels() or ""
        self._cache: dict[str, Optional[Mesh3D]] = {}
        if self._models_dir:
            log.info("KiCad 3D models: %s", self._models_dir)
        else:
            log.warning("KiCad 3D models directory not found")

    @property
    def available(self) -> bool:
        return bool(self._models_dir)

    def find_model(self, category: str, package: str) -> Optional[str]:
        """Find the .wrl file path for a component, or None."""
        if not self._models_dir:
            return None
        return _map_package(category, package, self._models_dir)

    def get_mesh(self, category: str, package: str) -> Optional[Mesh3D]:
        """Get parsed Mesh3D for a component, with caching.

        Returns None if no model found or parsing fails.
        """
        key = f"{category}:{package}"
        if key in self._cache:
            return self._cache[key]

        path = self.find_model(category, package)
        if not path:
            self._cache[key] = None
            return None

        try:
            mesh = parse_vrml(path)
            if not mesh.faces:
                self._cache[key] = None
                return None
            self._cache[key] = mesh
            log.debug("Loaded 3D model: %s (%d faces)", path, len(mesh.faces))
            return mesh
        except Exception as e:
            log.warning("Failed to parse WRL: %s — %s", path, e)
            self._cache[key] = None
            return None
