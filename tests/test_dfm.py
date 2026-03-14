"""Tests for DFM analysis engine in src/pcb/dfm.py."""

import math

import pytest

from src.pcb.dfm import DFMEngine, DFMSeverity, compute_dfm_score, _max_current_for_width
from src.pcb.generator import (
    Board,
    BoardOutline,
    Pad,
    PlacedComponent,
    TraceSegment,
    Via,
)


# ── Helper to build boards ───────────────────────────────


def _make_board(**kwargs) -> Board:
    defaults = dict(
        outline=BoardOutline(x_mm=0, y_mm=0, width_mm=50, height_mm=50),
    )
    defaults.update(kwargs)
    return Board(**defaults)


# ── Current capacity table tests ─────────────────────────


class TestCurrentCapacity:
    def test_below_minimum(self):
        assert _max_current_for_width(0.05) == 0.3

    def test_above_maximum(self):
        assert _max_current_for_width(10.0) == 7.0

    def test_exact_match(self):
        assert _max_current_for_width(1.00) == 2.0

    def test_interpolation(self):
        # Between 0.25mm (0.7A) and 0.30mm (0.8A)
        val = _max_current_for_width(0.275)
        assert 0.7 < val < 0.8


# ── DFM-001: Power trace current capacity ────────────────


class TestDFM001:
    def test_narrow_power_trace(self):
        board = _make_board(traces=[
            TraceSegment(net_name="VCC", start_x=0, start_y=0,
                         end_x=10, end_y=0, width_mm=0.2, layer="F.Cu"),
        ])
        engine = DFMEngine(board)
        issues = engine._check_trace_current_capacity()
        assert len(issues) == 1
        assert issues[0].code == "DFM-001"

    def test_wide_power_trace_ok(self):
        board = _make_board(traces=[
            TraceSegment(net_name="VCC", start_x=0, start_y=0,
                         end_x=10, end_y=0, width_mm=0.5, layer="F.Cu"),
        ])
        engine = DFMEngine(board)
        assert len(engine._check_trace_current_capacity()) == 0

    def test_signal_trace_ignored(self):
        board = _make_board(traces=[
            TraceSegment(net_name="NET1", start_x=0, start_y=0,
                         end_x=10, end_y=0, width_mm=0.1, layer="F.Cu"),
        ])
        engine = DFMEngine(board)
        assert len(engine._check_trace_current_capacity()) == 0

    def test_ratsnest_ignored(self):
        board = _make_board(traces=[
            TraceSegment(net_name="VCC", start_x=0, start_y=0,
                         end_x=10, end_y=0, width_mm=0.1, is_ratsnest=True),
        ])
        engine = DFMEngine(board)
        assert len(engine._check_trace_current_capacity()) == 0


# ── DFM-002: Annular ring ────────────────────────────────


class TestDFM002:
    def test_insufficient_via_ring(self):
        board = _make_board(vias=[
            Via(net_name="VCC", x_mm=10, y_mm=10,
                diameter_mm=0.4, drill_mm=0.3),  # ring = 0.05mm < 0.15mm
        ])
        engine = DFMEngine(board)
        issues = engine._check_annular_ring()
        assert any(i.code == "DFM-002" and i.severity == DFMSeverity.CRITICAL for i in issues)

    def test_sufficient_via_ring(self):
        board = _make_board(vias=[
            Via(net_name="VCC", x_mm=10, y_mm=10,
                diameter_mm=0.8, drill_mm=0.4),  # ring = 0.2mm > 0.15mm
        ])
        engine = DFMEngine(board)
        issues = [i for i in engine._check_annular_ring() if "via" in i.title.lower()]
        assert len(issues) == 0

    def test_insufficient_pad_ring(self):
        comp = PlacedComponent(ref="R1", x_mm=10, y_mm=10, pads=[
            Pad(component_ref="R1", number="1", x_mm=10, y_mm=10,
                width_mm=0.5, height_mm=0.5, drill_mm=0.4),  # ring = 0.05mm
        ])
        board = _make_board(components=[comp])
        engine = DFMEngine(board)
        issues = engine._check_annular_ring()
        assert any(i.code == "DFM-002" for i in issues)


# ── DFM-006: Component spacing ───────────────────────────


class TestDFM006:
    def test_tight_spacing(self):
        board = _make_board(components=[
            PlacedComponent(ref="R1", x_mm=10, y_mm=10, pads=[
                Pad(component_ref="R1", number="1", x_mm=10, y_mm=10),
            ]),
            PlacedComponent(ref="R2", x_mm=11.2, y_mm=10, pads=[
                Pad(component_ref="R2", number="1", x_mm=11.2, y_mm=10),
            ]),
        ])
        engine = DFMEngine(board)
        issues = engine._check_component_spacing()
        assert any(i.code == "DFM-006" for i in issues)

    def test_adequate_spacing(self):
        board = _make_board(components=[
            PlacedComponent(ref="R1", x_mm=10, y_mm=10, pads=[
                Pad(component_ref="R1", number="1", x_mm=10, y_mm=10),
            ]),
            PlacedComponent(ref="R2", x_mm=30, y_mm=10, pads=[
                Pad(component_ref="R2", number="1", x_mm=30, y_mm=10),
            ]),
        ])
        engine = DFMEngine(board)
        issues = engine._check_component_spacing()
        assert len(issues) == 0


# ── DFM-007: Board dimensions ────────────────────────────


class TestDFM007:
    def test_tiny_board(self):
        board = _make_board(outline=BoardOutline(width_mm=3, height_mm=3))
        engine = DFMEngine(board)
        issues = engine._check_board_size()
        assert any(i.code == "DFM-007" and "small" in i.title.lower() for i in issues)

    def test_huge_board(self):
        board = _make_board(outline=BoardOutline(width_mm=600, height_mm=600))
        engine = DFMEngine(board)
        issues = engine._check_board_size()
        assert any(i.code == "DFM-007" and "large" in i.title.lower() for i in issues)

    def test_normal_board_ok(self):
        board = _make_board(outline=BoardOutline(width_mm=100, height_mm=80))
        engine = DFMEngine(board)
        assert len(engine._check_board_size()) == 0


# ── DFM-008: Via aspect ratio ────────────────────────────


class TestDFM008:
    def test_high_aspect_ratio(self):
        board = _make_board(
            thickness_mm=3.2,
            vias=[Via(net_name="V", x_mm=10, y_mm=10, diameter_mm=0.5, drill_mm=0.3)],
        )
        # aspect = 3.2 / 0.3 ≈ 10.67 > 8
        engine = DFMEngine(board)
        issues = engine._check_via_aspect_ratio()
        assert any(i.code == "DFM-008" for i in issues)

    def test_normal_aspect_ratio(self):
        board = _make_board(
            thickness_mm=1.6,
            vias=[Via(net_name="V", x_mm=10, y_mm=10, diameter_mm=0.8, drill_mm=0.4)],
        )
        # aspect = 1.6 / 0.4 = 4.0 < 8
        engine = DFMEngine(board)
        assert len(engine._check_via_aspect_ratio()) == 0


# ── DFM-011: Minimum drill size ──────────────────────────


class TestDFM011:
    def test_drill_too_small(self):
        comp = PlacedComponent(ref="R1", x_mm=10, y_mm=10, pads=[
            Pad(component_ref="R1", number="1", x_mm=10, y_mm=10,
                width_mm=0.5, height_mm=0.5, drill_mm=0.1),  # < 0.2mm
        ])
        board = _make_board(components=[comp])
        engine = DFMEngine(board)
        issues = engine._check_minimum_drill()
        assert any(i.code == "DFM-011" for i in issues)

    def test_drill_ok(self):
        comp = PlacedComponent(ref="R1", x_mm=10, y_mm=10, pads=[
            Pad(component_ref="R1", number="1", x_mm=10, y_mm=10,
                width_mm=1.6, height_mm=1.6, drill_mm=0.8),
        ])
        board = _make_board(components=[comp])
        engine = DFMEngine(board)
        assert len(engine._check_minimum_drill()) == 0


# ── run_all integration test ─────────────────────────────


class TestDFMRunAll:
    def test_clean_board_passes(self):
        board = _make_board()
        engine = DFMEngine(board)
        issues = engine.run_all()
        assert len(issues) == 0

    def test_returns_all_issues(self):
        """A board with multiple problems should report all of them."""
        board = _make_board(
            outline=BoardOutline(width_mm=3, height_mm=3),  # DFM-007 tiny
            vias=[
                Via(net_name="V", x_mm=1, y_mm=1,
                    diameter_mm=0.35, drill_mm=0.3),  # DFM-002 ring
            ],
        )
        engine = DFMEngine(board)
        issues = engine.run_all()
        codes = {i.code for i in issues}
        assert "DFM-002" in codes
        assert "DFM-007" in codes


# ── Score computation ────────────────────────────────────


class TestDFMScore:
    def test_perfect_score(self):
        assert compute_dfm_score([]) == 100

    def test_critical_reduces_15(self):
        from src.pcb.dfm import DFMCategory, DFMIssue
        issues = [DFMIssue(
            category=DFMCategory.MANUFACTURING,
            severity=DFMSeverity.CRITICAL,
            code="T", title="t", description="d",
        )]
        assert compute_dfm_score(issues) == 85

    def test_warning_reduces_5(self):
        from src.pcb.dfm import DFMCategory, DFMIssue
        issues = [DFMIssue(
            category=DFMCategory.MANUFACTURING,
            severity=DFMSeverity.WARNING,
            code="T", title="t", description="d",
        )]
        assert compute_dfm_score(issues) == 95

    def test_score_floors_at_zero(self):
        from src.pcb.dfm import DFMCategory, DFMIssue
        issues = [DFMIssue(
            category=DFMCategory.MANUFACTURING,
            severity=DFMSeverity.CRITICAL,
            code="T", title="t", description="d",
        )] * 10  # 10×15 = 150 deduction
        assert compute_dfm_score(issues) == 0
