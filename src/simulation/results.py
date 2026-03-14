"""Data structures for simulation results and waveform data."""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np


@dataclass
class WaveformData:
    """A single simulation signal (voltage, current, etc.)."""

    name: str
    unit: str  # "V", "A", "Hz", "s", "dB", "°"
    values: np.ndarray = field(default_factory=lambda: np.array([]))

    @property
    def min(self) -> float:
        return float(np.min(self.values)) if self.values.size else 0.0

    @property
    def max(self) -> float:
        return float(np.max(self.values)) if self.values.size else 0.0


@dataclass
class OperatingPoint:
    """DC operating point results — node voltages and branch currents."""

    node_voltages: dict[str, float] = field(default_factory=dict)
    branch_currents: dict[str, float] = field(default_factory=dict)


@dataclass
class SimulationResult:
    """Complete result of a SPICE simulation run."""

    analysis_type: str  # "op", "tran", "ac", "dc"
    success: bool = True
    error_message: str = ""

    # For waveform analyses (tran, ac, dc sweep)
    x_axis: WaveformData | None = None
    signals: dict[str, WaveformData] = field(default_factory=dict)

    # For DC operating point
    operating_point: OperatingPoint | None = None

    # Engine info
    engine_used: str = ""  # "ngspice" or "built-in"
    raw_output: str = ""


@dataclass
class AnalysisConfig:
    """Configuration for a simulation analysis."""

    analysis_type: str = "op"  # "op", "tran", "ac", "dc"

    # Transient
    tran_step: float = 1e-6      # time step (s)
    tran_stop: float = 1e-3      # stop time (s)
    tran_start: float = 0.0      # start time (s)

    # AC sweep
    ac_sweep_type: str = "dec"   # "dec", "lin", "oct"
    ac_n_points: int = 100
    ac_f_start: float = 1.0      # Hz
    ac_f_stop: float = 1e6       # Hz

    # DC sweep
    dc_source: str = ""          # source name (e.g. "V1")
    dc_start: float = 0.0       # V
    dc_stop: float = 5.0        # V
    dc_step: float = 0.1        # V
