"""Tests for DRC engine in src/pcb/rules.py."""

import math

import pytest

from src.pcb.generator import (
    Board,
    BoardOutline,
    Pad,
    PlacedComponent,
    TraceSegment,
    Via,
)
from src.pcb.rules import DRCEngine, DRCViolation
from src.ai.schemas import DesignConstraints


def _make_board(**kwargs) -> Board:
    defaults = dict(
        outline=BoardOutline(x_mm=0, y_mm=0, width_mm=100, height_mm=100),
        constraints=DesignConstraints(),
    )
    defaults.update(kwargs)
    return Board(**defaults)


# ── Trace width check ────────────────────────────────────


class TestTraceWidth:
    def test_trace_below_minimum(self):
        board = _make_board(
            constraints=DesignConstraints(min_trace_width_mm=0.15),
            traces=[
                TraceSegment(net_name="N", start_x=0, start_y=0,
                             end_x=10, end_y=0, width_mm=0.1),
            ],
        )
        engine = DRCEngine(board)
        engine._check_trace_width()
        assert any(v.rule == "min_trace_width" for v in engine.violations)

    def test_trace_meets_minimum(self):
        board = _make_board(
            constraints=DesignConstraints(min_trace_width_mm=0.15),
            traces=[
                TraceSegment(net_name="N", start_x=0, start_y=0,
                             end_x=10, end_y=0, width_mm=0.25),
            ],
        )
        engine = DRCEngine(board)
        engine._check_trace_width()
        assert len(engine.violations) == 0


# ── Pad-to-pad clearance ─────────────────────────────────


class TestPadClearance:
    def test_pads_too_close(self):
        """Two pads from different components on different nets that are too close."""
        board = _make_board(
            constraints=DesignConstraints(min_clearance_mm=0.2),
            components=[
                PlacedComponent(ref="R1", x_mm=10, y_mm=10, pads=[
                    Pad(component_ref="R1", number="1", x_mm=10, y_mm=10,
                        width_mm=1.0, height_mm=1.0, net_name="A"),
                ]),
                PlacedComponent(ref="R2", x_mm=11, y_mm=10, pads=[
                    Pad(component_ref="R2", number="1", x_mm=11, y_mm=10,
                        width_mm=1.0, height_mm=1.0, net_name="B"),
                ]),
            ],
        )
        # dist = 1.0mm, edge_dist = 1.0 - (1.0+1.0)/2 = 0.0mm < 0.2mm
        engine = DRCEngine(board)
        engine._check_clearance_pad_to_pad()
        assert any(v.rule == "pad_clearance" for v in engine.violations)

    def test_same_net_pads_ok(self):
        """Pads on the same net should not be flagged."""
        board = _make_board(components=[
            PlacedComponent(ref="R1", x_mm=10, y_mm=10, pads=[
                Pad(component_ref="R1", number="1", x_mm=10, y_mm=10,
                    width_mm=1.0, height_mm=1.0, net_name="VCC"),
            ]),
            PlacedComponent(ref="R2", x_mm=11, y_mm=10, pads=[
                Pad(component_ref="R2", number="1", x_mm=11, y_mm=10,
                    width_mm=1.0, height_mm=1.0, net_name="VCC"),
            ]),
        ])
        engine = DRCEngine(board)
        engine._check_clearance_pad_to_pad()
        assert not any(v.rule == "pad_clearance" for v in engine.violations)


# ── Via drill check ──────────────────────────────────────


class TestViaDrill:
    def test_drill_too_small(self):
        board = _make_board(vias=[
            Via(net_name="V", x_mm=10, y_mm=10, diameter_mm=0.5, drill_mm=0.1),
        ])
        engine = DRCEngine(board)
        engine._check_via_drill()
        assert any(v.rule == "via_drill" for v in engine.violations)

    def test_drill_exceeds_diameter(self):
        board = _make_board(vias=[
            Via(net_name="V", x_mm=10, y_mm=10, diameter_mm=0.5, drill_mm=0.6),
        ])
        engine = DRCEngine(board)
        engine._check_via_drill()
        assert any(v.rule == "via_annular_ring" for v in engine.violations)

    def test_valid_via(self):
        board = _make_board(vias=[
            Via(net_name="V", x_mm=10, y_mm=10, diameter_mm=0.8, drill_mm=0.4),
        ])
        engine = DRCEngine(board)
        engine._check_via_drill()
        assert len(engine.violations) == 0


# ── Board boundary ───────────────────────────────────────


class TestBoardBoundary:
    def test_pad_outside_board(self):
        board = _make_board(
            outline=BoardOutline(x_mm=0, y_mm=0, width_mm=20, height_mm=20),
            components=[
                PlacedComponent(ref="R1", x_mm=25, y_mm=10, pads=[
                    Pad(component_ref="R1", number="1", x_mm=25, y_mm=10),
                ]),
            ],
        )
        engine = DRCEngine(board)
        engine._check_board_boundary()
        assert any(v.rule == "board_boundary" for v in engine.violations)

    def test_pad_inside_board(self):
        board = _make_board(
            outline=BoardOutline(x_mm=0, y_mm=0, width_mm=50, height_mm=50),
            components=[
                PlacedComponent(ref="R1", x_mm=25, y_mm=25, pads=[
                    Pad(component_ref="R1", number="1", x_mm=25, y_mm=25),
                ]),
            ],
        )
        engine = DRCEngine(board)
        engine._check_board_boundary()
        assert not any(v.rule == "board_boundary" for v in engine.violations)


# ── Unconnected pads ─────────────────────────────────────


class TestUnconnectedPads:
    def test_pad_without_net(self):
        board = _make_board(components=[
            PlacedComponent(ref="R1", x_mm=10, y_mm=10, pads=[
                Pad(component_ref="R1", number="1", x_mm=10, y_mm=10, net_name=""),
            ]),
        ])
        engine = DRCEngine(board)
        engine._check_unconnected_pads()
        assert any(v.rule == "unconnected" for v in engine.violations)

    def test_pad_with_net(self):
        board = _make_board(components=[
            PlacedComponent(ref="R1", x_mm=10, y_mm=10, pads=[
                Pad(component_ref="R1", number="1", x_mm=10, y_mm=10, net_name="VCC"),
            ]),
        ])
        engine = DRCEngine(board)
        engine._check_unconnected_pads()
        assert len(engine.violations) == 0


# ── run_all integration ──────────────────────────────────


class TestDRCRunAll:
    def test_clean_board(self, board_with_components):
        engine = DRCEngine(board_with_components)
        violations = engine.run_all()
        # All pads have nets, board is big, no traces
        assert not engine.has_errors

    def test_has_errors_property(self):
        board = _make_board(vias=[
            Via(net_name="V", x_mm=10, y_mm=10, diameter_mm=0.5, drill_mm=0.1),
        ])
        engine = DRCEngine(board)
        engine.run_all()
        assert engine.has_errors is True


# ── Geometry helper ──────────────────────────────────────


class TestPointToSegment:
    def test_perpendicular(self):
        d = DRCEngine._point_to_segment_distance(5, 5, 0, 0, 10, 0)
        assert abs(d - 5.0) < 1e-6

    def test_on_segment(self):
        d = DRCEngine._point_to_segment_distance(5, 0, 0, 0, 10, 0)
        assert abs(d) < 1e-6

    def test_beyond_endpoint(self):
        d = DRCEngine._point_to_segment_distance(15, 0, 0, 0, 10, 0)
        assert abs(d - 5.0) < 1e-6
