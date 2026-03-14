"""Download and set up vendor tools (NgSpice, Freerouting).

Run this script once after cloning to bundle external tools:
    python setup_vendor.py
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path

VENDOR_DIR = Path(__file__).resolve().parent / "vendor"

# NgSpice
NGSPICE_VERSION = "45.2"
NGSPICE_7Z = f"ngspice-{NGSPICE_VERSION}_64.7z"
NGSPICE_MIRROR = f"https://netix.dl.sourceforge.net/project/ngspice/ng-spice-rework/{NGSPICE_VERSION}/{NGSPICE_7Z}"
NGSPICE_FALLBACK = f"https://downloads.sourceforge.net/project/ngspice/ng-spice-rework/{NGSPICE_VERSION}/{NGSPICE_7Z}"

# Freerouting
FR_VERSION = "2.1.0"
FR_JAR = f"freerouting-{FR_VERSION}.jar"
FR_URL = f"https://github.com/freerouting/freerouting/releases/download/v{FR_VERSION}/{FR_JAR}"


def _download(url: str, dest: Path, label: str) -> bool:
    """Download a file with progress indicator."""
    print(f"  Downloading {label}...")
    try:
        opener = urllib.request.build_opener()
        opener.addheaders = [("User-Agent", "Mozilla/5.0")]
        urllib.request.install_opener(opener)
        urllib.request.urlretrieve(url, str(dest))
        size_mb = dest.stat().st_size / 1024 / 1024
        print(f"  Downloaded: {size_mb:.1f} MB")
        return True
    except Exception as e:
        print(f"  Download failed: {e}")
        return False


def _curl_download(url: str, dest: Path, label: str) -> bool:
    """Fallback download using curl (handles SourceForge redirects better)."""
    print(f"  Downloading {label} via curl...")
    try:
        result = subprocess.run(
            ["curl", "-L", "-o", str(dest), url, "--max-redirs", "15", "--connect-timeout", "30"],
            capture_output=True, text=True, timeout=300,
        )
        if dest.exists() and dest.stat().st_size > 1_000_000:
            size_mb = dest.stat().st_size / 1024 / 1024
            print(f"  Downloaded: {size_mb:.1f} MB")
            return True
        print(f"  Download seems incomplete or failed")
        return False
    except (FileNotFoundError, subprocess.TimeoutExpired) as e:
        print(f"  curl not available or timed out: {e}")
        return False


def setup_ngspice() -> bool:
    """Download and extract NgSpice."""
    exe_path = VENDOR_DIR / "Spice64" / "bin" / "ngspice_con.exe"
    if exe_path.is_file():
        print(f"[NgSpice] Already installed at {exe_path}")
        return True

    print(f"[NgSpice] Setting up v{NGSPICE_VERSION}...")
    VENDOR_DIR.mkdir(parents=True, exist_ok=True)

    archive = VENDOR_DIR / NGSPICE_7Z
    if not archive.exists():
        ok = _curl_download(NGSPICE_MIRROR, archive, NGSPICE_7Z)
        if not ok:
            ok = _curl_download(NGSPICE_FALLBACK, archive, NGSPICE_7Z)
        if not ok:
            ok = _download(NGSPICE_MIRROR, archive, NGSPICE_7Z)
        if not ok:
            print("  ERROR: Could not download NgSpice. Please download manually:")
            print(f"  https://sourceforge.net/projects/ngspice/files/ng-spice-rework/{NGSPICE_VERSION}/")
            return False

    # Verify it's actually a 7z file
    with open(archive, "rb") as f:
        if f.read(2) != b"7z":
            print("  ERROR: Downloaded file is not a valid 7z archive")
            archive.unlink()
            return False

    # Extract using bsdtar (Windows built-in) or 7z
    print("  Extracting...")
    try:
        subprocess.run(
            ["tar", "xf", str(archive)],
            cwd=str(VENDOR_DIR), check=True, capture_output=True,
        )
    except (FileNotFoundError, subprocess.CalledProcessError):
        # Try 7z
        for path_7z in [r"C:\Program Files\7-Zip\7z.exe", r"C:\Program Files (x86)\7-Zip\7z.exe"]:
            if os.path.isfile(path_7z):
                subprocess.run(
                    [path_7z, "x", str(archive), f"-o{VENDOR_DIR}"],
                    check=True, capture_output=True,
                )
                break
        else:
            print("  ERROR: Cannot extract .7z — install 7-Zip or use Windows 10+ with bsdtar")
            return False

    # Clean up archive
    archive.unlink(missing_ok=True)

    if exe_path.is_file():
        print(f"  OK: NgSpice installed at {exe_path}")
        return True
    else:
        print("  ERROR: Extraction succeeded but ngspice_con.exe not found")
        return False


def setup_freerouting() -> bool:
    """Download Freerouting JAR."""
    jar_path = VENDOR_DIR / FR_JAR
    if jar_path.is_file() and jar_path.stat().st_size > 1_000_000:
        print(f"[Freerouting] Already installed at {jar_path}")
        return True

    print(f"[Freerouting] Setting up v{FR_VERSION}...")
    VENDOR_DIR.mkdir(parents=True, exist_ok=True)

    ok = _download(FR_URL, jar_path, FR_JAR)
    if not ok:
        ok = _curl_download(FR_URL, jar_path, FR_JAR)
    if not ok:
        print("  ERROR: Could not download Freerouting. Please download manually:")
        print(f"  https://github.com/freerouting/freerouting/releases/tag/v{FR_VERSION}")
        return False

    # Verify JAR
    with open(jar_path, "rb") as f:
        if f.read(2) != b"PK":
            print("  ERROR: Downloaded file is not a valid JAR")
            jar_path.unlink()
            return False

    print(f"  OK: Freerouting installed at {jar_path}")

    # Check Java
    try:
        result = subprocess.run(["java", "-version"], capture_output=True, text=True, timeout=10)
        if result.returncode == 0:
            print("  Java runtime: available")
        else:
            print("  WARNING: Java runtime not found — Freerouting requires Java 11+")
    except (FileNotFoundError, subprocess.TimeoutExpired):
        print("  WARNING: Java runtime not found — Freerouting requires Java 11+")

    return True


def main():
    print("=" * 50)
    print("AI PCB Generator — Vendor Tool Setup")
    print("=" * 50)
    print()

    results = {
        "NgSpice": setup_ngspice(),
        "Freerouting": setup_freerouting(),
    }

    print()
    print("=" * 50)
    for name, ok in results.items():
        status = "OK" if ok else "FAILED"
        print(f"  {name}: {status}")
    print("=" * 50)

    if all(results.values()):
        print("\nAll vendor tools are ready!")
        return 0
    else:
        print("\nSome tools failed to install. See errors above.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
