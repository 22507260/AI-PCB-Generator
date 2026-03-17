"""Tests for manufacturing package generation in src/pcb/manufacturing.py."""

from __future__ import annotations

import zipfile

from src.pcb.generator import PCBGenerator
from src.pcb.manufacturing import generate_production_package, _safe_project_name


def test_safe_project_name_sanitizes_invalid_chars():
    assert _safe_project_name("Arduino: Uno/Shield * v1?") == "Arduino_Uno_Shield_v1"


def test_production_package_uses_manufacturer_file_names(simple_spec, tmp_path):
    board = PCBGenerator(simple_spec).generate()
    files = generate_production_package(
        board=board,
        spec=simple_spec,
        output_dir=tmp_path,
        manufacturer_key="jlcpcb",
    )

    zip_path = files["gerber_zip"]
    assert zip_path.name.endswith("_gerber.zip")

    with zipfile.ZipFile(zip_path, "r") as zf:
        names = set(zf.namelist())

    assert "F_Cu.gtl" in names
    assert "B_Cu.gbl" in names
    assert "F_SilkS.gto" in names
    assert "Edge_Cuts.gm1" in names
    assert "drill.drl" in names
