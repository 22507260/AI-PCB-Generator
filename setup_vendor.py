"""Download and set up vendor tools (NgSpice, Freerouting).

Run this script once after cloning to bundle external tools:
    python setup_vendor.py
"""

from __future__ import annotations

import html
import os
import re
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path

VENDOR_DIR = Path(__file__).resolve().parent / "vendor"

# NgSpice
NGSPICE_VERSION = "46"
NGSPICE_7Z = f"ngspice-{NGSPICE_VERSION}_64.7z"
NGSPICE_RELEASE_PATHS = [
    f"ng-spice-rework/{NGSPICE_VERSION}/{NGSPICE_7Z}",
    f"ng-spice-rework/old-releases/{NGSPICE_VERSION}/{NGSPICE_7Z}",
]
NGSPICE_DOWNLOAD_PAGES = [
    f"https://sourceforge.net/projects/ngspice/files/{release_path}/download"
    for release_path in NGSPICE_RELEASE_PATHS
]
NGSPICE_DIRECT_URLS = [
    f"https://downloads.sourceforge.net/project/ngspice/{release_path}?use_mirror=master"
    for release_path in NGSPICE_RELEASE_PATHS
]
SEVEN_Z_MAGIC = b"7z\xbc\xaf\x27\x1c"

# Freerouting
FR_VERSION = "2.1.0"
FR_JAR = f"freerouting-{FR_VERSION}.jar"
FR_URL = f"https://github.com/freerouting/freerouting/releases/download/v{FR_VERSION}/{FR_JAR}"


def _has_magic(path: Path, magic: bytes) -> bool:
    """Return True when the file starts with the expected magic bytes."""
    if not path.is_file():
        return False
    with open(path, "rb") as f:
        return f.read(len(magic)) == magic


def _resolve_sourceforge_download(download_page: str, file_name: str) -> tuple[str, dict[str, str]] | None:
    """Resolve a SourceForge download page to the real file URL."""
    try:
        request = urllib.request.Request(download_page, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(request, timeout=60) as response:
            page = response.read().decode("utf-8", "replace")
    except Exception as e:
        print(f"  Could not resolve SourceForge download page: {e}")
        return None

    pattern = re.compile(
        rf'https://downloads\.sourceforge\.net/project/[^\s"\']*{re.escape(file_name)}\?[^\s"\']+'
    )
    match = pattern.search(page)
    if not match:
        return None

    return html.unescape(match.group(0)), {"Referer": download_page}


def _download(url: str, dest: Path, label: str, headers: dict[str, str] | None = None) -> bool:
    """Download a file via urllib."""
    print(f"  Downloading {label}...")
    try:
        request_headers = {"User-Agent": "Mozilla/5.0"}
        if headers:
            request_headers.update(headers)
        request = urllib.request.Request(url, headers=request_headers)
        with urllib.request.urlopen(request, timeout=300) as response, open(dest, "wb") as f:
            shutil.copyfileobj(response, f)
        size_mb = dest.stat().st_size / 1024 / 1024
        print(f"  Downloaded: {size_mb:.1f} MB")
        return True
    except Exception as e:
        dest.unlink(missing_ok=True)
        print(f"  Download failed: {e}")
        return False


def _curl_download(
    url: str,
    dest: Path,
    label: str,
    headers: dict[str, str] | None = None,
) -> bool:
    """Download a file via curl."""
    print(f"  Downloading {label} via curl...")
    try:
        curl_bin = shutil.which("curl.exe") or shutil.which("curl")
        if not curl_bin:
            raise FileNotFoundError("curl")

        command = [
            curl_bin,
            "-L",
            "--fail",
            "--retry",
            "3",
            "--retry-delay",
            "2",
            "--max-redirs",
            "15",
            "--connect-timeout",
            "30",
            "-o",
            str(dest),
            url,
        ]
        for name, value in (headers or {}).items():
            command.extend(["-H", f"{name}: {value}"])

        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=300,
        )
        if result.returncode == 0 and dest.exists() and dest.stat().st_size > 0:
            size_mb = dest.stat().st_size / 1024 / 1024
            print(f"  Downloaded: {size_mb:.1f} MB")
            return True

        dest.unlink(missing_ok=True)
        stderr = result.stderr.strip().splitlines()
        detail = stderr[-1] if stderr else "unknown error"
        print(f"  Download seems incomplete or failed: {detail}")
        return False
    except (FileNotFoundError, subprocess.TimeoutExpired) as e:
        dest.unlink(missing_ok=True)
        print(f"  curl not available or timed out: {e}")
        return False


def _download_ngspice_archive(archive: Path) -> bool:
    """Download the NgSpice 7z archive from SourceForge."""
    resolved_urls: list[tuple[str, dict[str, str]]] = []
    for page in NGSPICE_DOWNLOAD_PAGES:
        resolved = _resolve_sourceforge_download(page, NGSPICE_7Z)
        if resolved:
            resolved_urls.append(resolved)

    download_attempts = resolved_urls + [(url, {}) for url in NGSPICE_DIRECT_URLS]
    for url, headers in download_attempts:
        if _curl_download(url, archive, NGSPICE_7Z, headers=headers) and _has_magic(archive, SEVEN_Z_MAGIC):
            return True
        archive.unlink(missing_ok=True)

    for url, headers in resolved_urls:
        if _download(url, archive, NGSPICE_7Z, headers=headers) and _has_magic(archive, SEVEN_Z_MAGIC):
            return True
        archive.unlink(missing_ok=True)

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
    if archive.exists() and not _has_magic(archive, SEVEN_Z_MAGIC):
        print("  Removing invalid cached NgSpice archive...")
        archive.unlink(missing_ok=True)

    if not archive.exists():
        ok = _download_ngspice_archive(archive)
        if not ok:
            print("  ERROR: Could not download NgSpice. Please download manually:")
            print("  https://sourceforge.net/projects/ngspice/files/ng-spice-rework/")
            return False

    if not _has_magic(archive, SEVEN_Z_MAGIC):
        print("  ERROR: Downloaded file is not a valid 7z archive")
        archive.unlink(missing_ok=True)
        return False

    print("  Extracting...")
    try:
        subprocess.run(
            ["tar", "xf", str(archive)],
            cwd=str(VENDOR_DIR),
            check=True,
            capture_output=True,
        )
    except (FileNotFoundError, subprocess.CalledProcessError):
        for path_7z in [r"C:\Program Files\7-Zip\7z.exe", r"C:\Program Files (x86)\7-Zip\7z.exe"]:
            if os.path.isfile(path_7z):
                subprocess.run(
                    [path_7z, "x", str(archive), f"-o{VENDOR_DIR}"],
                    check=True,
                    capture_output=True,
                )
                break
        else:
            print("  ERROR: Cannot extract .7z - install 7-Zip or use Windows 10+ with bsdtar")
            return False

    archive.unlink(missing_ok=True)

    if exe_path.is_file():
        print(f"  OK: NgSpice installed at {exe_path}")
        return True

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

    if not _has_magic(jar_path, b"PK"):
        print("  ERROR: Downloaded file is not a valid JAR")
        jar_path.unlink(missing_ok=True)
        return False

    print(f"  OK: Freerouting installed at {jar_path}")

    try:
        result = subprocess.run(["java", "-version"], capture_output=True, text=True, timeout=10)
        if result.returncode == 0:
            print("  Java runtime: available")
        else:
            print("  WARNING: Java runtime not found - Freerouting requires Java 11+")
    except (FileNotFoundError, subprocess.TimeoutExpired):
        print("  WARNING: Java runtime not found - Freerouting requires Java 11+")

    return True


def main():
    print("=" * 50)
    print("AI PCB Generator - Vendor Tool Setup")
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

    print("\nSome tools failed to install. See errors above.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
