"""One-Click PCB Manufacturing — file generation & manufacturer integration.

Generates production-ready output packages: BOM CSV, pick-and-place CPL,
Gerber ZIP, and cost estimation for popular manufacturers.
"""

from __future__ import annotations

import csv
import io
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

from src.ai.schemas import CircuitSpec, ComponentSpec
from src.pcb.generator import Board, PCBGenerator
from src.pcb.exporter import export_gerber, export_kicad_pcb
from src.utils.logger import get_logger

log = get_logger("pcb.manufacturing")


# ======================================================================
# Manufacturer Profiles
# ======================================================================

@dataclass
class ManufacturerProfile:
    """PCB manufacturer capabilities and pricing model."""
    name: str
    website: str
    min_trace_mm: float = 0.15
    min_drill_mm: float = 0.2
    min_clearance_mm: float = 0.15
    max_layers: int = 16
    max_board_mm: tuple[float, float] = (400.0, 500.0)
    base_price_usd: float = 2.0
    price_per_sqcm: float = 0.02
    supports_smt: bool = True
    lead_time_days: int = 7
    gerber_zip_name: str = "gerber.zip"

    # File naming conventions per manufacturer
    file_naming: dict[str, str] = field(default_factory=dict)


MANUFACTURERS: dict[str, ManufacturerProfile] = {
    "jlcpcb": ManufacturerProfile(
        name="JLCPCB",
        website="https://www.jlcpcb.com",
        min_trace_mm=0.127,
        min_drill_mm=0.2,
        min_clearance_mm=0.127,
        max_layers=20,
        max_board_mm=(400, 500),
        base_price_usd=2.0,
        price_per_sqcm=0.015,
        supports_smt=True,
        lead_time_days=5,
        file_naming={
            "F.Cu": "F_Cu.gtl",
            "B.Cu": "B_Cu.gbl",
            "F.SilkS": "F_SilkS.gto",
            "B.SilkS": "B_SilkS.gbo",
            "F.Mask": "F_Mask.gts",
            "B.Mask": "B_Mask.gbs",
            "Edge.Cuts": "Edge_Cuts.gm1",
            "drill": "drill.drl",
        },
    ),
    "pcbway": ManufacturerProfile(
        name="PCBWay",
        website="https://www.pcbway.com",
        min_trace_mm=0.1,
        min_drill_mm=0.2,
        min_clearance_mm=0.1,
        max_layers=14,
        max_board_mm=(500, 600),
        base_price_usd=5.0,
        price_per_sqcm=0.02,
        supports_smt=True,
        lead_time_days=7,
        file_naming={
            "F.Cu": "F_Cu.gtl",
            "B.Cu": "B_Cu.gbl",
            "drill": "drill.drl",
        },
    ),
    "oshpark": ManufacturerProfile(
        name="OSH Park",
        website="https://oshpark.com",
        min_trace_mm=0.152,
        min_drill_mm=0.254,
        min_clearance_mm=0.152,
        max_layers=4,
        max_board_mm=(381, 432),
        base_price_usd=0.0,
        price_per_sqcm=0.17,
        supports_smt=False,
        lead_time_days=12,
        file_naming={
            "F.Cu": "F_Cu.gtl",
            "B.Cu": "B_Cu.gbl",
            "drill": "drill.drl",
        },
    ),
}


# ======================================================================
# Cost Estimation
# ======================================================================

@dataclass
class CostEstimate:
    """Estimated manufacturing cost breakdown."""
    manufacturer: str
    board_area_sqcm: float
    pcb_cost_usd: float
    smt_cost_usd: float
    total_cost_usd: float
    quantity: int
    lead_time_days: int
    notes: list[str] = field(default_factory=list)


def estimate_cost(
    board: Board,
    spec: CircuitSpec,
    manufacturer_key: str,
    quantity: int = 5,
) -> CostEstimate:
    """Estimate manufacturing cost for a given manufacturer."""
    profile = MANUFACTURERS.get(manufacturer_key)
    if not profile:
        return CostEstimate(
            manufacturer=manufacturer_key,
            board_area_sqcm=0,
            pcb_cost_usd=0,
            smt_cost_usd=0,
            total_cost_usd=0,
            quantity=quantity,
            lead_time_days=0,
            notes=["Unknown manufacturer"],
        )

    o = board.outline
    area_sqcm = (o.width_mm * o.height_mm) / 100.0
    notes: list[str] = []

    # PCB cost
    pcb_unit = max(profile.base_price_usd, area_sqcm * profile.price_per_sqcm)
    pcb_cost = pcb_unit * quantity

    # SMT assembly cost (rough estimate)
    smt_cost = 0.0
    if profile.supports_smt:
        smd_count = sum(
            1 for comp in board.components
            for pad in comp.pads if pad.drill_mm == 0
        )
        unique_parts = len(set(c.value for c in spec.components))
        smt_setup = 8.0 if smd_count > 0 else 0.0
        smt_per_part = smd_count * 0.03 * quantity
        smt_cost = smt_setup + smt_per_part + unique_parts * 1.5
        if smt_cost > 0:
            notes.append(f"{smd_count} SMD pads, {unique_parts} unique parts")

    # Capability checks
    constraints = board.constraints
    if constraints.min_trace_width_mm < profile.min_trace_mm:
        notes.append(
            f"Trace width {constraints.min_trace_width_mm}mm < "
            f"fab minimum {profile.min_trace_mm}mm"
        )
    if board.layers > profile.max_layers:
        notes.append(
            f"{board.layers} layers exceeds max {profile.max_layers}"
        )
    if o.width_mm > profile.max_board_mm[0] or o.height_mm > profile.max_board_mm[1]:
        notes.append("Board exceeds manufacturer max dimensions")

    total = pcb_cost + smt_cost

    return CostEstimate(
        manufacturer=profile.name,
        board_area_sqcm=area_sqcm,
        pcb_cost_usd=round(pcb_cost, 2),
        smt_cost_usd=round(smt_cost, 2),
        total_cost_usd=round(total, 2),
        quantity=quantity,
        lead_time_days=profile.lead_time_days,
        notes=notes,
    )


# ======================================================================
# BOM CSV Generation
# ======================================================================

def generate_bom_csv(spec: CircuitSpec, path: Path | str) -> Path:
    """Generate Bill of Materials in CSV format (JLCPCB compatible)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "Comment", "Designator", "Footprint", "LCSC Part#",
            "Manufacturer", "MPN", "Description", "Quantity",
        ])

        # Group components by value+footprint
        groups: dict[str, list[ComponentSpec]] = {}
        for comp in spec.components:
            key = f"{comp.value}|{comp.package or (comp.footprint.name if comp.footprint else '')}"
            groups.setdefault(key, []).append(comp)

        for _key, comps in groups.items():
            first = comps[0]
            designators = ",".join(c.ref for c in comps)
            footprint = first.footprint.name if first.footprint else first.package
            writer.writerow([
                first.value,
                designators,
                footprint,
                "",  # LCSC part number (user fills in)
                first.manufacturer,
                first.manufacturer_pn,
                first.description,
                len(comps),
            ])

    log.info("BOM CSV exported to %s (%d unique parts)", path, len(groups))
    return path


# ======================================================================
# Pick-and-Place CPL Generation
# ======================================================================

def generate_cpl_csv(board: Board, path: Path | str) -> Path:
    """Generate Component Placement List (CPL / Centroid) for SMT assembly."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "Designator", "Val", "Package", "Mid X", "Mid Y",
            "Rotation", "Layer",
        ])

        for comp in board.components:
            layer_name = "top" if comp.layer == "F.Cu" else "bottom"
            writer.writerow([
                comp.ref,
                comp.value,
                comp.footprint,
                f"{comp.x_mm:.4f}",
                f"{comp.y_mm:.4f}",
                f"{comp.rotation_deg:.1f}",
                layer_name,
            ])

    log.info("CPL CSV exported to %s (%d components)", path, len(board.components))
    return path


# ======================================================================
# Production Package (ZIP)
# ======================================================================

def generate_production_package(
    board: Board,
    spec: CircuitSpec,
    output_dir: Path | str,
    manufacturer_key: str = "jlcpcb",
) -> dict[str, Path]:
    """Generate complete production package for a manufacturer.

    Returns dict of generated file paths.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    result: dict[str, Path] = {}
    project_name = spec.name.replace(" ", "_")

    # 1. Gerber files
    gerber_dir = output_dir / "gerber"
    gerber_files = export_gerber(board, gerber_dir)

    # 2. Create Gerber ZIP
    zip_path = output_dir / f"{project_name}_gerber.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for gf in gerber_files:
            zf.write(gf, gf.name)
    result["gerber_zip"] = zip_path

    # 3. BOM CSV
    bom_path = output_dir / f"{project_name}_BOM.csv"
    generate_bom_csv(spec, bom_path)
    result["bom"] = bom_path

    # 4. Pick-and-Place CPL
    cpl_path = output_dir / f"{project_name}_CPL.csv"
    generate_cpl_csv(board, cpl_path)
    result["cpl"] = cpl_path

    # 5. KiCad PCB (for reference)
    kicad_path = output_dir / f"{project_name}.kicad_pcb"
    export_kicad_pcb(board, kicad_path)
    result["kicad_pcb"] = kicad_path

    log.info(
        "Production package generated: %d files in %s",
        len(result), output_dir,
    )
    return result
