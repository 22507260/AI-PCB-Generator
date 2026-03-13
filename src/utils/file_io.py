"""File I/O utilities for project save/load."""

from __future__ import annotations

import json
from pathlib import Path

from src.ai.schemas import CircuitSpec
from src.utils.logger import get_logger

log = get_logger("utils.file_io")

PROJECT_EXTENSION = ".apcb"


def save_project(spec: CircuitSpec, path: Path | str) -> Path:
    """Save a CircuitSpec as a .apcb project file (JSON)."""
    path = Path(path)
    if path.suffix != PROJECT_EXTENSION:
        path = path.with_suffix(PROJECT_EXTENSION)
    path.parent.mkdir(parents=True, exist_ok=True)

    data = {
        "version": "1.0",
        "format": "ai-pcb-project",
        "circuit": spec.model_dump(mode="json"),
    }
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    log.info("Project saved to %s", path)
    return path


def load_project(path: Path | str) -> CircuitSpec:
    """Load a CircuitSpec from a .apcb project file."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Project file not found: {path}")

    data = json.loads(path.read_text(encoding="utf-8"))
    spec = CircuitSpec.model_validate(data["circuit"])
    log.info("Project loaded from %s — %s", path, spec.name)
    return spec
