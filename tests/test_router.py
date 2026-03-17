"""Tests for Freerouting fallback behavior in src/pcb/router.py."""

from __future__ import annotations

from src.pcb.router import FreeroutingRouter, RoutingError


class TestFreeroutingRouter:
    def test_falls_back_to_maze_router_when_freerouting_errors(
        self,
        board_with_components,
        tmp_path,
        monkeypatch,
    ):
        fake_jar = tmp_path / "freerouting.jar"
        fake_jar.write_text("placeholder", encoding="utf-8")

        monkeypatch.setattr(FreeroutingRouter, "_java_available", lambda self: True)

        def _raise_routing_error(self, dsn, ses, timeout):
            raise RoutingError("synthetic freerouting failure")

        monkeypatch.setattr(FreeroutingRouter, "_run_freerouting", _raise_routing_error)

        board = FreeroutingRouter(board_with_components, jar_path=str(fake_jar)).route()

        assert board is board_with_components
        assert any(t.net_name == "VOUT" for t in board.traces)
        assert any(not t.is_ratsnest for t in board.traces)

    def test_falls_back_to_maze_router_when_freerouting_outputs_no_ses(
        self,
        board_with_components,
        tmp_path,
        monkeypatch,
    ):
        fake_jar = tmp_path / "freerouting.jar"
        fake_jar.write_text("placeholder", encoding="utf-8")

        monkeypatch.setattr(FreeroutingRouter, "_java_available", lambda self: True)
        monkeypatch.setattr(
            FreeroutingRouter,
            "_run_freerouting",
            lambda self, dsn, ses, timeout: None,
        )

        board = FreeroutingRouter(board_with_components, jar_path=str(fake_jar)).route()

        assert any(t.net_name == "VOUT" for t in board.traces)
        assert any(not t.is_ratsnest for t in board.traces)
