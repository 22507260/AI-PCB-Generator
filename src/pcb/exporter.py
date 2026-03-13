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
# Gerber exporter (simplified — single layer)
# ======================================================================

def export_gerber(board: Board, output_dir: Path | str) -> list[Path]:
    """Export Gerber files for each copper layer + drill file.

    This is a simplified RS-274X Gerber generator suitable for
    basic 2-layer boards. For production use, KiCad's own Gerber
    plotter should be used.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    files: list[Path] = []

    layer_map = {
        "F.Cu": ("F_Cu.gbr", "GTL"),
        "B.Cu": ("B_Cu.gbr", "GBL"),
    }

    for layer_name, (filename, _ext) in layer_map.items():
        layer_traces = [t for t in board.traces if t.layer == layer_name]
        layer_pads = [
            p for c in board.components for p in c.pads
            if c.layer == layer_name or p.drill_mm > 0
        ]

        if not layer_traces and not layer_pads:
            continue

        gerber_lines: list[str] = []
        gerber_lines.append("%FSLAX36Y36*%")          # Format spec
        gerber_lines.append("%MOIN*%")                  # Metric
        gerber_lines.append("%MOMM*%")
        gerber_lines.append(f"%TF.FileFunction,Copper,L1,Top*%")
        gerber_lines.append("%ADD10C,0.250*%")          # Aperture D10 = circle 0.25mm
        gerber_lines.append("%ADD11R,0.800X0.800*%")    # Aperture D11 = rect pad
        gerber_lines.append("%ADD12C,0.800*%")          # Aperture D12 = round pad

        # Draw traces
        gerber_lines.append("D10*")
        for trace in layer_traces:
            x1 = int(trace.start_x * 1_000_000)
            y1 = int(trace.start_y * 1_000_000)
            x2 = int(trace.end_x * 1_000_000)
            y2 = int(trace.end_y * 1_000_000)
            gerber_lines.append(f"X{x1}Y{y1}D02*")
            gerber_lines.append(f"X{x2}Y{y2}D01*")

        # Flash pads
        for pad in layer_pads:
            ap = "D12" if pad.shape == "circle" else "D11"
            gerber_lines.append(f"{ap}*")
            x = int(pad.x_mm * 1_000_000)
            y = int(pad.y_mm * 1_000_000)
            gerber_lines.append(f"X{x}Y{y}D03*")

        gerber_lines.append("M02*")  # End of file

        fpath = output_dir / filename
        fpath.write_text("\n".join(gerber_lines), encoding="ascii")
        files.append(fpath)

    # Drill file (Excellon format)
    drill_pads = [
        p for c in board.components for p in c.pads if p.drill_mm > 0
    ]
    drill_vias = board.vias
    if drill_pads or drill_vias:
        drill_lines: list[str] = []
        drill_lines.append("M48")
        drill_lines.append("METRIC,TZ")
        drill_lines.append("T01C0.800")
        drill_lines.append("%")
        drill_lines.append("T01")

        for pad in drill_pads:
            x = f"{pad.x_mm:.3f}"
            y = f"{pad.y_mm:.3f}"
            drill_lines.append(f"X{x}Y{y}")
        for via in drill_vias:
            x = f"{via.x_mm:.3f}"
            y = f"{via.y_mm:.3f}"
            drill_lines.append(f"X{x}Y{y}")

        drill_lines.append("M30")
        drill_path = output_dir / "drill.drl"
        drill_path.write_text("\n".join(drill_lines), encoding="ascii")
        files.append(drill_path)

    log.info("Exported %d Gerber/drill files to %s", len(files), output_dir)
    return files
