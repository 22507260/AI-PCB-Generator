"""Multi-format PCB exporter.

Generates KiCad (.kicad_pcb), Gerber, SVG, and JSON output files
from the internal Board representation.
"""

from __future__ import annotations

import json
from pathlib import Path

from src.pcb.generator import Board, PlacedComponent, TraceSegment, Via
from src.utils.logger import get_logger

log = get_logger("pcb.exporter")


class ExportError(Exception):
    """Raised when export fails."""


# ======================================================================
# KiCad .kicad_pcb exporter
# ======================================================================

def export_kicad_pcb(board: Board, path: Path | str) -> Path:
    """Write the board as a KiCad 8 .kicad_pcb file."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    lines: list[str] = []
    lines.append('(kicad_pcb (version 20240108) (generator "ai-pcb-generator")')
    lines.append("  (general (thickness {:.2f}))".format(board.thickness_mm))

    # Layers
    lines.append("  (layers")
    layer_defs = [
        (0, "F.Cu", "signal"),
        (31, "B.Cu", "signal"),
        (36, "B.SilkS", "user"),
        (37, "F.SilkS", "user"),
        (38, "B.Mask", "user"),
        (39, "F.Mask", "user"),
        (44, "Edge.Cuts", "user"),
        (48, "B.CrtYd", "user"),
        (49, "F.CrtYd", "user"),
    ]
    # Add inner layers
    for i in range(1, board.layers - 1):
        layer_defs.insert(i, (i, f"In{i}.Cu", "signal"))
    for num, name, ltype in layer_defs:
        lines.append(f'    ({num} "{name}" {ltype})')
    lines.append("  )")

    # Setup / design rules
    c = board.constraints
    lines.append("  (setup")
    lines.append(f"    (pad_to_mask_clearance 0.05)")
    lines.append(f"    (pcbplotparams (layerselection 0x00010fc_ffffffff))")
    lines.append("  )")

    # Net declarations
    lines.append('  (net 0 "")')
    net_names = board.get_net_names()
    for i, name in enumerate(net_names, start=1):
        lines.append(f'  (net {i} "{name}")')

    net_id_map = {name: i + 1 for i, name in enumerate(net_names)}

    # Board outline
    o = board.outline
    lines.append(
        f"  (gr_rect (start {o.x_mm} {o.y_mm}) "
        f"(end {o.x_mm + o.width_mm} {o.y_mm + o.height_mm}) "
        f'(layer "Edge.Cuts") (stroke (width 0.1)))'
    )

    # Footprints (components)
    for comp in board.components:
        lines.append(f'  (footprint "{comp.footprint}"')
        lines.append(f'    (layer "{comp.layer}")')
        lines.append(f"    (at {comp.x_mm} {comp.y_mm} {comp.rotation_deg})")
        lines.append(f'    (property "Reference" "{comp.ref}" (at 0 -2)  (layer "F.SilkS"))')
        lines.append(f'    (property "Value" "{comp.value}" (at 0 2) (layer "F.Fab"))')

        for pad in comp.pads:
            net_id = net_id_map.get(pad.net_name, 0)
            pad_type = "thru_hole" if pad.drill_mm > 0 else "smd"
            pad_shape = pad.shape
            rel_x = pad.x_mm - comp.x_mm
            rel_y = pad.y_mm - comp.y_mm

            drill_str = f" (drill {pad.drill_mm})" if pad.drill_mm > 0 else ""
            pad_layers = '(layers "F.Cu" "B.Cu" "*.Mask")' if pad.drill_mm > 0 else '(layers "F.Cu" "F.Mask" "F.Paste")'

            lines.append(
                f'    (pad "{pad.number}" {pad_type} {pad_shape} '
                f"(at {rel_x} {rel_y}) "
                f"(size {pad.width_mm} {pad.height_mm})"
                f"{drill_str} "
                f"{pad_layers} "
                f'(net {net_id} "{pad.net_name}"))'
            )
        lines.append("  )")

    # Traces
    for trace in board.traces:
        net_id = net_id_map.get(trace.net_name, 0)
        lines.append(
            f"  (segment (start {trace.start_x} {trace.start_y}) "
            f"(end {trace.end_x} {trace.end_y}) "
            f"(width {trace.width_mm}) "
            f'(layer "{trace.layer}") '
            f"(net {net_id}))"
        )

    # Vias
    for via in board.vias:
        net_id = net_id_map.get(via.net_name, 0)
        lines.append(
            f"  (via (at {via.x_mm} {via.y_mm}) "
            f"(size {via.diameter_mm}) (drill {via.drill_mm}) "
            f'(layers "F.Cu" "B.Cu") '
            f"(net {net_id}))"
        )

    lines.append(")")

    path.write_text("\n".join(lines), encoding="utf-8")
    log.info("Exported KiCad PCB to %s", path)
    return path


# ======================================================================
# SVG exporter (self-contained, no external deps)
# ======================================================================

# Layer colors
_LAYER_COLORS = {
    "F.Cu": "#c83232",       # Red
    "B.Cu": "#3232c8",       # Blue
    "In1.Cu": "#c8c832",     # Yellow
    "In2.Cu": "#32c832",     # Green
    "F.SilkS": "#f0f0f0",   # White
    "B.SilkS": "#f0f0f0",
    "Edge.Cuts": "#c8c800",  # Yellow
}


def _component_silk_bounds(
    comp: PlacedComponent,
    clearance_mm: float = 0.5,
) -> tuple[float, float, float, float]:
    """Estimate a silkscreen-safe component body box from pad extents."""
    if not comp.pads:
        half_w = 1.5
        half_h = 1.0
        return (
            comp.x_mm - half_w,
            comp.y_mm - half_h,
            comp.x_mm + half_w,
            comp.y_mm + half_h,
        )

    min_x = min(pad.x_mm - (pad.width_mm or 0.8) / 2 for pad in comp.pads) - clearance_mm
    max_x = max(pad.x_mm + (pad.width_mm or 0.8) / 2 for pad in comp.pads) + clearance_mm
    min_y = min(pad.y_mm - (pad.height_mm or pad.width_mm or 0.8) / 2 for pad in comp.pads) - clearance_mm
    max_y = max(pad.y_mm + (pad.height_mm or pad.width_mm or 0.8) / 2 for pad in comp.pads) + clearance_mm
    return min_x, min_y, max_x, max_y


def export_svg(board: Board, path: Path | str) -> Path:
    """Render the board as an SVG image."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    o = board.outline
    margin = 5.0
    vb_x = o.x_mm - margin
    vb_y = o.y_mm - margin
    vb_w = o.width_mm + 2 * margin
    vb_h = o.height_mm + 2 * margin
    scale = 4  # px per mm

    svg_parts: list[str] = []
    svg_parts.append(
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'width="{vb_w * scale}" height="{vb_h * scale}" '
        f'viewBox="{vb_x} {vb_y} {vb_w} {vb_h}">'
    )
    svg_parts.append(f'<rect x="{vb_x}" y="{vb_y}" width="{vb_w}" height="{vb_h}" fill="#1a1a2e"/>')

    # Board outline
    svg_parts.append(
        f'<rect x="{o.x_mm}" y="{o.y_mm}" width="{o.width_mm}" height="{o.height_mm}" '
        f'fill="#2d2d44" stroke="{_LAYER_COLORS["Edge.Cuts"]}" stroke-width="0.3"/>'
    )

    # Traces
    for trace in board.traces:
        color = _LAYER_COLORS.get(trace.layer, "#c83232")
        svg_parts.append(
            f'<line x1="{trace.start_x}" y1="{trace.start_y}" '
            f'x2="{trace.end_x}" y2="{trace.end_y}" '
            f'stroke="{color}" stroke-width="{trace.width_mm}" '
            f'stroke-linecap="round" opacity="0.8"/>'
        )

    # Vias
    for via in board.vias:
        r = via.diameter_mm / 2
        svg_parts.append(
            f'<circle cx="{via.x_mm}" cy="{via.y_mm}" r="{r}" '
            f'fill="#c8c832" stroke="#888" stroke-width="0.1"/>'
        )
        svg_parts.append(
            f'<circle cx="{via.x_mm}" cy="{via.y_mm}" r="{via.drill_mm / 2}" fill="#1a1a2e"/>'
        )

    # Components (pads + labels)
    for comp in board.components:
        for pad in comp.pads:
            color = _LAYER_COLORS.get(comp.layer, "#c83232")
            w, h = pad.width_mm, pad.height_mm
            if pad.shape == "circle":
                svg_parts.append(
                    f'<circle cx="{pad.x_mm}" cy="{pad.y_mm}" r="{w / 2}" '
                    f'fill="{color}" opacity="0.9"/>'
                )
            else:
                svg_parts.append(
                    f'<rect x="{pad.x_mm - w / 2}" y="{pad.y_mm - h / 2}" '
                    f'width="{w}" height="{h}" rx="0.1" '
                    f'fill="{color}" opacity="0.9"/>'
                )
            if pad.drill_mm > 0:
                svg_parts.append(
                    f'<circle cx="{pad.x_mm}" cy="{pad.y_mm}" r="{pad.drill_mm / 2}" fill="#1a1a2e"/>'
                )

        # Reference label
        svg_parts.append(
            f'<text x="{comp.x_mm}" y="{comp.y_mm - 2.5}" '
            f'font-size="1.5" fill="white" text-anchor="middle" '
            f'font-family="monospace">{comp.ref}</text>'
        )

    svg_parts.append("</svg>")

    path.write_text("\n".join(svg_parts), encoding="utf-8")
    log.info("Exported SVG to %s", path)
    return path


# ======================================================================
# JSON exporter
# ======================================================================

def export_json(board: Board, spec_dict: dict, path: Path | str) -> Path:
    """Export the full circuit + board data as JSON."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    data = {
        "version": "1.0",
        "circuit": spec_dict,
        "board": {
            "outline": {
                "x_mm": board.outline.x_mm,
                "y_mm": board.outline.y_mm,
                "width_mm": board.outline.width_mm,
                "height_mm": board.outline.height_mm,
            },
            "layers": board.layers,
            "thickness_mm": board.thickness_mm,
            "components": [
                {
                    "ref": c.ref,
                    "value": c.value,
                    "footprint": c.footprint,
                    "x_mm": c.x_mm,
                    "y_mm": c.y_mm,
                    "rotation_deg": c.rotation_deg,
                    "layer": c.layer,
                    "pads": [
                        {
                            "number": p.number,
                            "net": p.net_name,
                            "x_mm": p.x_mm,
                            "y_mm": p.y_mm,
                        }
                        for p in c.pads
                    ],
                }
                for c in board.components
            ],
            "traces": [
                {
                    "net": t.net_name,
                    "start": [t.start_x, t.start_y],
                    "end": [t.end_x, t.end_y],
                    "width_mm": t.width_mm,
                    "layer": t.layer,
                }
                for t in board.traces
            ],
            "vias": [
                {
                    "net": v.net_name,
                    "x_mm": v.x_mm,
                    "y_mm": v.y_mm,
                    "diameter_mm": v.diameter_mm,
                    "drill_mm": v.drill_mm,
                }
                for v in board.vias
            ],
        },
    }

    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    log.info("Exported JSON to %s", path)
    return path


# ======================================================================
# Gerber exporter (multi-layer RS-274X + Excellon drill)
# ======================================================================

def _mm_to_coord(mm: float) -> int:
    """Convert mm to Gerber coordinate (4.6 format — micrometers)."""
    return int(round(mm * 1_000_000))


def _gerber_header(file_function: str, layer_num: int = 1,
                   layer_side: str = "Top") -> list[str]:
    """Generate RS-274X header lines."""
    lines = [
        "G04 AI PCB Generator*",
        "%FSLAX46Y46*%",
        "%MOMM*%",
        f"%TF.GenerationSoftware,AI-PCB-Generator,1.0*%",
        f"%TF.FileFunction,{file_function}*%",
    ]
    return lines


def _gerber_footer() -> list[str]:
    return ["M02*"]


def _write_gerber(path: Path, lines: list[str]) -> None:
    path.write_text("\n".join(lines), encoding="ascii")


def export_gerber(board: Board, output_dir: Path | str) -> list[Path]:
    """Export production-ready Gerber files + Excellon drill file.

    Generated files:
      - F_Cu.gbr      — Front copper
      - B_Cu.gbr      — Back copper
      - F_Mask.gbr    — Front solder mask
      - B_Mask.gbr    — Back solder mask
      - F_SilkS.gbr   — Front silkscreen
      - Edge_Cuts.gbr — Board outline
      - drill.drl     — Excellon drill file (PTH + NPTH)
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    files: list[Path] = []

    o = board.outline

    # Collect pad sizes for aperture table
    apertures: dict[str, int] = {}  # "C,0.250" -> D-code
    next_d = 10

    def _get_aperture(shape: str, w_mm: float, h_mm: float = 0) -> int:
        nonlocal next_d
        if shape == "circle":
            key = f"C,{w_mm:.4f}"
        else:
            key = f"R,{w_mm:.4f}X{h_mm or w_mm:.4f}"
        if key not in apertures:
            apertures[key] = next_d
            next_d += 1
        return apertures[key]

    # Pre-register common apertures
    trace_widths = {t.width_mm for t in board.traces}
    for tw in trace_widths:
        _get_aperture("circle", tw)

    for comp in board.components:
        for pad in comp.pads:
            pw = pad.width_mm or 0.8
            ph = pad.height_mm or pw
            _get_aperture(pad.shape or "circle", pw, ph)

    for via in board.vias:
        _get_aperture("circle", via.diameter_mm)

    def _aperture_defs() -> list[str]:
        lines = []
        for key, d_code in sorted(apertures.items(), key=lambda x: x[1]):
            lines.append(f"%ADD{d_code}{key}*%")
        return lines

    # ── Copper layers ──
    for layer_name, file_func, filename in [
        ("F.Cu", "Copper,L1,Top", "F_Cu.gbr"),
        ("B.Cu", "Copper,L2,Bot", "B_Cu.gbr"),
    ]:
        layer_traces = [t for t in board.traces if t.layer == layer_name]
        layer_pads = [
            p for c in board.components for p in c.pads
            if c.layer == layer_name or p.drill_mm > 0
        ]
        layer_vias = board.vias if layer_name in ("F.Cu", "B.Cu") else []

        if not layer_traces and not layer_pads and not layer_vias:
            continue

        lines = _gerber_header(file_func)
        lines.extend(_aperture_defs())

        # Draw traces
        for trace in layer_traces:
            d = _get_aperture("circle", trace.width_mm)
            lines.append(f"D{d}*")
            x1 = _mm_to_coord(trace.start_x)
            y1 = _mm_to_coord(trace.start_y)
            x2 = _mm_to_coord(trace.end_x)
            y2 = _mm_to_coord(trace.end_y)
            lines.append(f"X{x1}Y{y1}D02*")
            lines.append(f"X{x2}Y{y2}D01*")

        # Flash pads
        for pad in layer_pads:
            pw = pad.width_mm or 0.8
            ph = pad.height_mm or pw
            d = _get_aperture(pad.shape or "circle", pw, ph)
            lines.append(f"D{d}*")
            x = _mm_to_coord(pad.x_mm)
            y = _mm_to_coord(pad.y_mm)
            lines.append(f"X{x}Y{y}D03*")

        # Flash vias
        for via in layer_vias:
            d = _get_aperture("circle", via.diameter_mm)
            lines.append(f"D{d}*")
            x = _mm_to_coord(via.x_mm)
            y = _mm_to_coord(via.y_mm)
            lines.append(f"X{x}Y{y}D03*")

        lines.extend(_gerber_footer())
        fpath = output_dir / filename
        _write_gerber(fpath, lines)
        files.append(fpath)

    # ── Solder mask layers ──
    mask_expansion = 0.05  # 50µm expansion from pad
    for layer_name, file_func, filename in [
        ("F.Cu", "Soldermask,Top", "F_Mask.gbr"),
        ("B.Cu", "Soldermask,Bot", "B_Mask.gbr"),
    ]:
        layer_pads = [
            p for c in board.components for p in c.pads
            if c.layer == layer_name or p.drill_mm > 0
        ]
        if not layer_pads and not board.vias:
            continue

        mask_apertures: dict[str, int] = {}
        mask_d = 10

        def _get_mask_ap(shape: str, w: float, h: float = 0) -> int:
            nonlocal mask_d
            w_exp = w + mask_expansion * 2
            h_exp = (h or w) + mask_expansion * 2
            if shape == "circle":
                key = f"C,{w_exp:.4f}"
            else:
                key = f"R,{w_exp:.4f}X{h_exp:.4f}"
            if key not in mask_apertures:
                mask_apertures[key] = mask_d
                mask_d += 1
            return mask_apertures[key]

        lines = _gerber_header(file_func)

        # Pre-compute apertures
        for pad in layer_pads:
            pw = pad.width_mm or 0.8
            ph = pad.height_mm or pw
            _get_mask_ap(pad.shape or "circle", pw, ph)
        for via in board.vias:
            _get_mask_ap("circle", via.diameter_mm)

        for key, d_code in sorted(mask_apertures.items(), key=lambda x: x[1]):
            lines.append(f"%ADD{d_code}{key}*%")

        # Mask openings at pads
        for pad in layer_pads:
            pw = pad.width_mm or 0.8
            ph = pad.height_mm or pw
            d = _get_mask_ap(pad.shape or "circle", pw, ph)
            lines.append(f"D{d}*")
            x = _mm_to_coord(pad.x_mm)
            y = _mm_to_coord(pad.y_mm)
            lines.append(f"X{x}Y{y}D03*")

        for via in board.vias:
            d = _get_mask_ap("circle", via.diameter_mm)
            lines.append(f"D{d}*")
            x = _mm_to_coord(via.x_mm)
            y = _mm_to_coord(via.y_mm)
            lines.append(f"X{x}Y{y}D03*")

        lines.extend(_gerber_footer())
        fpath = output_dir / filename
        _write_gerber(fpath, lines)
        files.append(fpath)

    # ── Silkscreen (front) ──
    silk_lines = _gerber_header("Legend,Top")
    silk_ap = 10
    silk_lines.append(f"%ADD{silk_ap}C,0.150*%")  # 0.15mm line width
    silk_lines.append(f"D{silk_ap}*")

    for comp in board.components:
        x0_mm, y0_mm, x1_mm, y1_mm = _component_silk_bounds(comp)
        x0 = _mm_to_coord(x0_mm)
        y0 = _mm_to_coord(y0_mm)
        x1 = _mm_to_coord(x1_mm)
        y1 = _mm_to_coord(y1_mm)
        silk_lines.append(f"X{x0}Y{y0}D02*")
        silk_lines.append(f"X{x1}Y{y0}D01*")
        silk_lines.append(f"X{x1}Y{y1}D01*")
        silk_lines.append(f"X{x0}Y{y1}D01*")
        silk_lines.append(f"X{x0}Y{y0}D01*")

    silk_lines.extend(_gerber_footer())
    fpath = output_dir / "F_SilkS.gbr"
    _write_gerber(fpath, silk_lines)
    files.append(fpath)

    # ── Edge Cuts (board outline) ──
    edge_lines = _gerber_header("Profile,NP")
    edge_ap = 10
    edge_lines.append(f"%ADD{edge_ap}C,0.050*%")
    edge_lines.append(f"D{edge_ap}*")

    corners = [
        (o.x_mm, o.y_mm),
        (o.x_mm + o.width_mm, o.y_mm),
        (o.x_mm + o.width_mm, o.y_mm + o.height_mm),
        (o.x_mm, o.y_mm + o.height_mm),
    ]
    x0 = _mm_to_coord(corners[0][0])
    y0 = _mm_to_coord(corners[0][1])
    edge_lines.append(f"X{x0}Y{y0}D02*")
    for cx, cy in corners[1:]:
        edge_lines.append(f"X{_mm_to_coord(cx)}Y{_mm_to_coord(cy)}D01*")
    edge_lines.append(f"X{x0}Y{y0}D01*")  # close outline

    edge_lines.extend(_gerber_footer())
    fpath = output_dir / "Edge_Cuts.gbr"
    _write_gerber(fpath, edge_lines)
    files.append(fpath)

    # ── Excellon drill file ──
    drill_holes: list[tuple[float, float, float]] = []  # (x, y, diameter)
    for comp in board.components:
        for pad in comp.pads:
            if pad.drill_mm > 0:
                drill_holes.append((pad.x_mm, pad.y_mm, pad.drill_mm))
    for via in board.vias:
        drill_holes.append((via.x_mm, via.y_mm, via.drill_mm))

    if drill_holes:
        # Group by drill diameter
        drill_by_size: dict[float, list[tuple[float, float]]] = {}
        for x, y, d in drill_holes:
            drill_by_size.setdefault(d, []).append((x, y))

        drill_lines: list[str] = [
            "M48",
            ";TYPE=PLATED",
            ";FORMAT={-:-/ absolute / metric / decimal}",
            "FMAT,2",
            "METRIC,TZ",
        ]

        # Tool definitions
        tool_map: dict[float, int] = {}
        for i, diameter in enumerate(sorted(drill_by_size.keys()), start=1):
            tool_map[diameter] = i
            drill_lines.append(f"T{i:02d}C{diameter:.3f}")

        drill_lines.append("%")

        # Drill hits
        for diameter in sorted(drill_by_size.keys()):
            tool = tool_map[diameter]
            drill_lines.append(f"T{tool:02d}")
            for x, y in drill_by_size[diameter]:
                drill_lines.append(f"X{x:.3f}Y{y:.3f}")

        drill_lines.append("T00")
        drill_lines.append("M30")

        drill_path = output_dir / "drill.drl"
        drill_path.write_text("\n".join(drill_lines), encoding="ascii")
        files.append(drill_path)

    log.info("Exported %d Gerber/drill files to %s", len(files), output_dir)
    return files
