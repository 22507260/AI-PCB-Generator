"""Tests for KiCad PCB exporter in src/pcb/exporter.py."""

import pytest
from pathlib import Path

from src.pcb.exporter import export_kicad_pcb, ExportError
from src.pcb.generator import (
    Board,
    BoardOutline,
    Pad,
    PlacedComponent,
    TraceSegment,
    Via,
)


class TestExportKicadPcb:
    def test_creates_file(self, board_with_components, tmp_path):
        out = tmp_path / "test.kicad_pcb"
        result = export_kicad_pcb(board_with_components, out)
        assert result.exists()
        assert result.suffix == ".kicad_pcb"

    def test_creates_parent_dirs(self, board_with_components, tmp_path):
        out = tmp_path / "sub" / "deep" / "board.kicad_pcb"
        result = export_kicad_pcb(board_with_components, out)
        assert result.exists()

    def test_header(self, board_with_components, tmp_path):
        out = tmp_path / "h.kicad_pcb"
        export_kicad_pcb(board_with_components, out)
        content = out.read_text(encoding="utf-8")
        assert "(kicad_pcb" in content
        assert '"ai-pcb-generator"' in content

    def test_net_declarations(self, board_with_components, tmp_path):
        out = tmp_path / "n.kicad_pcb"
        export_kicad_pcb(board_with_components, out)
        content = out.read_text(encoding="utf-8")
        assert '(net 0 "")' in content
        assert '"VCC"' in content
        assert '"GND"' in content
        assert '"VOUT"' in content

    def test_footprint_sections(self, board_with_components, tmp_path):
        out = tmp_path / "f.kicad_pcb"
        export_kicad_pcb(board_with_components, out)
        content = out.read_text(encoding="utf-8")
        assert '(footprint "R_0805"' in content
        assert '"R1"' in content
        assert '"R2"' in content

    def test_board_outline(self, board_with_components, tmp_path):
        out = tmp_path / "o.kicad_pcb"
        export_kicad_pcb(board_with_components, out)
        content = out.read_text(encoding="utf-8")
        assert '(gr_rect' in content
        assert '"Edge.Cuts"' in content

    def test_traces_exported(self, board_with_traces, tmp_path):
        out = tmp_path / "t.kicad_pcb"
        export_kicad_pcb(board_with_traces, out)
        content = out.read_text(encoding="utf-8")
        assert "(segment" in content

    def test_vias_exported(self, board_with_vias, tmp_path):
        out = tmp_path / "v.kicad_pcb"
        export_kicad_pcb(board_with_vias, out)
        content = out.read_text(encoding="utf-8")
        assert "(via (at" in content

    def test_empty_board(self, empty_board, tmp_path):
        out = tmp_path / "e.kicad_pcb"
        result = export_kicad_pcb(empty_board, out)
        assert result.exists()
        content = out.read_text(encoding="utf-8")
        assert "(kicad_pcb" in content

    def test_layer_definitions(self, board_with_components, tmp_path):
        out = tmp_path / "l.kicad_pcb"
        export_kicad_pcb(board_with_components, out)
        content = out.read_text(encoding="utf-8")
        assert '"F.Cu"' in content
        assert '"B.Cu"' in content
        assert '"Edge.Cuts"' in content
