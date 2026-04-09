from __future__ import annotations

from pathlib import Path

import setup_vendor


class _FakeResponse:
    def __init__(self, payload: bytes):
        self._payload = payload

    def read(self) -> bytes:
        return self._payload

    def __enter__(self) -> "_FakeResponse":
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        return False


def test_resolve_sourceforge_download_extracts_real_archive_url(monkeypatch):
    page_url = "https://sourceforge.net/projects/ngspice/files/ng-spice-rework/46/ngspice-46_64.7z/download"
    html = (
        b'<html><body><a href="https://downloads.sourceforge.net/project/ngspice/'
        b'ng-spice-rework/46/ngspice-46_64.7z?ts=123&amp;use_mirror=netix&amp;r=">'
        b"Download</a></body></html>"
    )

    monkeypatch.setattr(
        setup_vendor.urllib.request,
        "urlopen",
        lambda request, timeout=60: _FakeResponse(html),
    )

    resolved = setup_vendor._resolve_sourceforge_download(page_url, "ngspice-46_64.7z")

    assert resolved == (
        "https://downloads.sourceforge.net/project/ngspice/"
        "ng-spice-rework/46/ngspice-46_64.7z?ts=123&use_mirror=netix&r=",
        {"Referer": page_url},
    )


def test_has_magic_checks_archive_prefix(tmp_path):
    archive = tmp_path / "ngspice.7z"
    archive.write_bytes(setup_vendor.SEVEN_Z_MAGIC + b"payload")

    assert setup_vendor._has_magic(archive, setup_vendor.SEVEN_Z_MAGIC) is True

    archive.write_bytes(b"<!doctype html>")

    assert setup_vendor._has_magic(archive, setup_vendor.SEVEN_Z_MAGIC) is False


def test_download_ngspice_archive_falls_back_when_curl_payload_is_html(monkeypatch, tmp_path):
    archive = tmp_path / "ngspice.7z"
    resolved_url = "https://downloads.sourceforge.net/project/ngspice/ng-spice-rework/46/ngspice-46_64.7z?ts=123"
    page_url = "https://sourceforge.net/projects/ngspice/files/ng-spice-rework/46/ngspice-46_64.7z/download"

    monkeypatch.setattr(setup_vendor, "NGSPICE_DOWNLOAD_PAGES", [page_url])
    monkeypatch.setattr(setup_vendor, "NGSPICE_DIRECT_URLS", ["https://downloads.sourceforge.net/project/ngspice/direct"])
    monkeypatch.setattr(
        setup_vendor,
        "_resolve_sourceforge_download",
        lambda page, file_name: (resolved_url, {"Referer": page}),
    )

    curl_calls: list[tuple[str, dict[str, str] | None]] = []
    urllib_calls: list[tuple[str, dict[str, str] | None]] = []

    def fake_curl(url: str, dest: Path, label: str, headers: dict[str, str] | None = None) -> bool:
        curl_calls.append((url, headers))
        dest.write_bytes(b"<!doctype html>")
        return True

    def fake_download(url: str, dest: Path, label: str, headers: dict[str, str] | None = None) -> bool:
        urllib_calls.append((url, headers))
        dest.write_bytes(setup_vendor.SEVEN_Z_MAGIC + b"payload")
        return True

    monkeypatch.setattr(setup_vendor, "_curl_download", fake_curl)
    monkeypatch.setattr(setup_vendor, "_download", fake_download)

    assert setup_vendor._download_ngspice_archive(archive) is True
    assert archive.read_bytes().startswith(setup_vendor.SEVEN_Z_MAGIC)
    assert len(curl_calls) == 2
    assert urllib_calls == [(resolved_url, {"Referer": page_url})]
