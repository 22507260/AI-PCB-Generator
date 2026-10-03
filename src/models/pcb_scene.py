"""Renderer-independent PCB meshes, in millimetres, with Z up.

Board coordinates use Y down; the scene uses Y up. Board top is Z=0,
bottom is -thickness. KiCad WRL units are 0.1 inch (2.54 mm).
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from itertools import pairwise

from shapely import constrained_delaunay_triangles
from shapely.affinity import rotate, scale
from shapely.geometry import LineString, Point, Polygon, box
from shapely.geometry.polygon import orient
from shapely.ops import unary_union

from src.pcb.generator import Board, PlacedComponent

Vec3 = tuple[float, float, float]
Color = tuple[float, float, float]
MASK = (0.055, 0.31, 0.16)
FR4 = (0.57, 0.49, 0.29)
GOLD = (0.78, 0.64, 0.30)
TIN = (0.68, 0.70, 0.73)
BODY = (0.10, 0.11, 0.12)


@dataclass
class Triangle:
    vertices: tuple[Vec3, Vec3, Vec3]
    color: Color

    @property
    def normal(self) -> Vec3:
        a, b, c = self.vertices
        u = tuple(b[i] - a[i] for i in range(3))
        v = tuple(c[i] - a[i] for i in range(3))
        n = (u[1] * v[2] - u[2] * v[1], u[2] * v[0] - u[0] * v[2], u[0] * v[1] - u[1] * v[0])
        length = math.sqrt(sum(x * x for x in n)) or 1
        return tuple(x / length for x in n)


@dataclass
class Scene:
    groups: dict[str, list[Triangle]] = field(default_factory=dict)
    guides: list[tuple[Vec3, Vec3]] = field(default_factory=list)
    labels: list[tuple[str, Vec3]] = field(default_factory=list)
    bounds: tuple[Vec3, Vec3] = ((0, 0, -1.6), (1, 1, 0))
    model_count: int = 0


def polygons(geometry):
    if geometry.is_empty:
        return []
    return [geometry] if isinstance(geometry, Polygon) else list(geometry.geoms)


def surface(geometry, z: float, color: Color, flip=False) -> list[Triangle]:
    result = []
    for polygon in polygons(geometry):
        for tri in constrained_delaunay_triangles(polygon).geoms:
            pts = [(x, y, z) for x, y in list(tri.exterior.coords)[:3]]
            t = Triangle(tuple(pts), color)
            if (t.normal[2] < 0) != flip:
                t = Triangle((pts[0], pts[2], pts[1]), color)
            result.append(t)
    return result


def extrude(
    geometry, bottom: float, top: float, color: Color, side_color: Color | None = None
) -> list[Triangle]:
    result = surface(geometry, top, color) + surface(geometry, bottom, color, True)
    for polygon in polygons(geometry):
        polygon = orient(polygon, sign=1)
        for ring in [polygon.exterior, *polygon.interiors]:
            coords = list(ring.coords)
            for (x, y), (u, v) in pairwise(coords):
                a, b, c, d = (x, y, bottom), (u, v, bottom), (u, v, top), (x, y, top)
                result.extend(
                    [
                        Triangle((a, b, c), side_color or color),
                        Triangle((a, c, d), side_color or color),
                    ]
                )
    return result


def cuboid(x, y, w, h, z, height, color):
    return extrude(box(x - w / 2, y - h / 2, x + w / 2, y + h / 2), z, z + height, color)


def cylinder(x, y, radius, z, height, color):
    return extrude(Point(x, y).buffer(radius, quad_segs=12), z, z + height, color)


def category(comp: PlacedComponent) -> str:
    r, p, v = comp.ref.upper(), comp.footprint.upper(), comp.value.lower()
    if "USB" in p or "usb" in v:
        return "usb_connector"
    if r.startswith("LED") or (r.startswith("D") and "led" in v):
        return "led"
    if r.startswith("R"):
        return "resistor"
    if r.startswith("C"):
        return "capacitor"
    if r.startswith(("J", "P", "CN")):
        return "connector"
    if r.startswith("D"):
        return "diode"
    if r.startswith("L"):
        return "inductor"
    if r.startswith(("U", "Q")):
        return "ic"
    return "generic"


def component_transform(comp: PlacedComponent, point: Vec3, thickness: float) -> Vec3:
    """Preserve footprint origin. Back placement flips local Y and Z.

    Local model Y is up; positive board rotation is counterclockwise in
    the Y-down board coordinates, matching the generator's pad transform.
    """
    x, y, z = point
    back = comp.layer == "B.Cu"
    if back:
        y, z = -y, -z
    angle = math.radians(-comp.rotation_deg)
    c, s = math.cos(angle), math.sin(angle)
    return (comp.x_mm + x * c - y * s, -comp.y_mm + x * s + y * c, z - (thickness if back else 0))


def local_pads(comp):
    """Convert already-positioned world pads to model-local coordinates."""
    a = math.radians(comp.rotation_deg)
    c, s = math.cos(a), math.sin(a)
    result = []
    for pad in comp.pads:
        x, y = pad.x_mm - comp.x_mm, -(pad.y_mm - comp.y_mm)
        px, py = x * c - y * s, x * s + y * c
        result.append((px, -py if comp.layer == "B.Cu" else py, pad))
    return result


def builtin_component(comp: PlacedComponent) -> list[Triangle]:
    """Conservative package-sized bodies; leads terminate at the actual pads."""
    pkg, kind = comp.footprint.upper(), category(comp)
    pads = local_pads(comp)
    xs, ys = [p[0] for p in pads] or [0], [p[1] for p in pads] or [0]
    cx, cy = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
    span_x, span_y = max(xs) - min(xs), max(ys) - min(ys)
    smd = bool(pads) and all(p.drill_mm == 0 for _, _, p in pads)
    size = re.search(r"(?:^|_)(0402|0603|0805|1206|1210)(?:_|$)", pkg)
    sizes = {
        "0402": (1.0, 0.5),
        "0603": (1.6, 0.8),
        "0805": (2, 1.25),
        "1206": (3.2, 1.6),
        "1210": (3.2, 2.5),
    }
    w, h = sizes[size[1]] if size else (max(1.6, span_x * 0.65), max(1.2, span_y * 0.65))
    result = []
    z, height = 0.15, 0.65
    color = BODY
    if kind in ("resistor", "capacitor", "diode") and (smd or size):
        color = (0.64, 0.46, 0.28) if kind == "capacitor" else BODY
        result += cuboid(cx, cy, w, h, z, height, color)
        for x in (cx - w * 0.4, cx + w * 0.4):
            result += cuboid(x, cy, w * 0.2, h + 0.04, 0.05, height + 0.14, TIN)
    elif kind in ("resistor", "diode"):
        z, height = 0.75, 1.6
        result += cuboid(
            cx, cy, w, h, z, height, (0.68, 0.59, 0.40) if kind == "resistor" else BODY
        )
        result += cuboid(cx - w * 0.25, cy, w * 0.09, h + 0.025, z + 0.025, height, BODY)
    elif kind == "capacitor" and (
        "RADIAL" in pkg or "CP_" in pkg or "electro" in comp.value.lower()
    ):
        height = 6.0
        result += cylinder(cx, cy, 2.5, 0.3, height, BODY)
        result += cylinder(cx, cy, 2.4, height + 0.3, 0.08, TIN)
        result += cuboid(cx, cy, 3.5, 0.12, height + 0.39, 0.015, BODY)
    elif kind == "led" and not smd:
        height = 4.5
        result += cylinder(cx, cy, 1.5, 0.3, height, (0.65, 0.07, 0.05))
        result += cylinder(cx, cy, 1.7, 0.2, 0.3, (0.43, 0.05, 0.03))
    elif kind == "connector":
        height = 2.5
        result += cuboid(cx, cy, span_x + 2.3, span_y + 2.3, 0.1, height, BODY)
        for x, y, _ in pads:
            result += cuboid(x, y, 0.6, 0.6, 0, 5.5, GOLD)
    elif kind == "usb_connector":
        w, h, height = 8.9, 7.4, 3.2
        result += cuboid(cx, cy, w, h, 0.1, height, TIN)
        # Dark recess and insulating tongue at the front of the shell.
        result += cuboid(cx, cy - h / 2 - 0.01, w * 0.86, 0.06, 0.5, 2.4, BODY)
        result += cuboid(cx, cy - h / 2 - 0.05, w * 0.65, 0.08, 1.3, 0.4, (0.28, 0.29, 0.30))
    elif kind == "ic":
        if "DIP" in pkg:
            w, h, height = 6.4, max(4.5, span_y + 2.2), 3.0
        elif "TO-220" in pkg:
            w, h, height = 10, 3, 9
        elif "SOT-223" in pkg:
            w, h, height = 6.5, 3.5, 1.7
        elif "SOT-23" in pkg:
            w, h, height = 2.9, 1.3, 1.1
        elif "SOIC" in pkg:
            w, h, height = 3.9, max(4.9, span_y + 1.2), 1.5
        else:
            w, h, height = max(2, span_x * 0.7), max(2, span_y * 0.8), 1.4
        result += cuboid(cx, cy, w, h, 0.35, height, BODY)
        result += cylinder(
            cx - w * 0.32, cy + h * 0.32, 0.25, height + 0.36, 0.015, (0.55, 0.55, 0.55)
        )
    elif kind == "capacitor":
        result += cuboid(cx, cy, w, max(h, 2), 0.3, 2.5, (0.66, 0.40, 0.19))
        height = 2.5
    elif kind == "inductor":
        result += cylinder(cx, cy, max(1.5, w / 2), 0.2, 2.5, (0.25, 0.25, 0.26))
        height = 2.5
    else:
        result += cuboid(cx, cy, w, h, 0.2, 1.5, (0.28, 0.30, 0.32))
        height = 1.5
    if kind != "connector":
        for x, y, pad in pads:
            if pad.drill_mm:
                result += cylinder(
                    x, y, min(0.25, pad.drill_mm * 0.35), -0.6, z + height * 0.45 + 0.6, TIN
                )
            # Link body edge to its pad; never invent extra pins.
            ex, ey = max(cx - w / 2, min(cx + w / 2, x)), max(cy - h / 2, min(cy + h / 2, y))
            lead = LineString([(ex, ey), (x, y)]).buffer(0.14, quad_segs=3)
            result += extrude(lead, 0.07, 0.23, TIN)
    return result


def build_scene(board: Board, registry=None, use_models=True) -> Scene:
    scene = Scene(groups={key: [] for key in ("board", "pads", "traces", "components")})
    o, t = board.outline, board.thickness_mm
    outline = box(o.x_mm, -o.y_mm - o.height_mm, o.x_mm + o.width_mm, -o.y_mm)
    holes = [
        Point(p.x_mm, -p.y_mm).buffer(p.drill_mm / 2, quad_segs=12)
        for p in board.get_all_pads()
        if p.drill_mm > 0
    ]
    holes += [
        Point(v.x_mm, -v.y_mm).buffer(v.drill_mm / 2, quad_segs=12)
        for v in board.vias
        if v.drill_mm > 0
    ]
    drilled = unary_union(holes)
    scene.groups["board"] = extrude(outline.difference(drilled), -t, 0, MASK, FR4)
    # Plated barrels line the actual drill openings; they do not cap the hole.
    for hole in holes:
        for tri in extrude(hole.intersection(outline), -t - 0.01, 0.01, TIN):
            if abs(tri.normal[2]) < 0.9:
                scene.groups["pads"].append(tri)
    for comp in board.components:
        for p in comp.pads:
            x, y = p.x_mm, -p.y_mm
            if p.shape in ("rect", "roundrect"):
                shape = box(
                    x - p.width_mm / 2, y - p.height_mm / 2, x + p.width_mm / 2, y + p.height_mm / 2
                )
                if p.shape == "roundrect":
                    radius = min(p.width_mm, p.height_mm) * 0.2
                    shape = shape.buffer(-radius).buffer(radius, quad_segs=6)
            elif p.shape == "oval":
                r = min(p.width_mm, p.height_mm) / 2
                dx, dy = max(0, p.width_mm / 2 - r), max(0, p.height_mm / 2 - r)
                shape = LineString([(x - dx, y - dy), (x + dx, y + dy)]).buffer(r, quad_segs=12)
            else:
                shape = scale(
                    Point(x, y).buffer(0.5, quad_segs=12), p.width_mm, p.height_mm, origin=(x, y)
                )
            shape = rotate(shape, -comp.rotation_deg, origin=(x, y))
            ring = shape.difference(drilled).intersection(outline)
            if p.drill_mm or comp.layer != "B.Cu":
                scene.groups["pads"] += surface(ring, 0.028, GOLD)
            if p.drill_mm or comp.layer == "B.Cu":
                scene.groups["pads"] += surface(ring, -t - 0.028, GOLD, True)
    for v in board.vias:
        ring = Point(v.x_mm, -v.y_mm).buffer(v.diameter_mm / 2, quad_segs=12).difference(drilled)
        scene.groups["pads"] += surface(ring.intersection(outline), 0.028, GOLD)
        scene.groups["pads"] += surface(ring.intersection(outline), -t - 0.028, GOLD, True)
    for trace in board.traces:
        back = trace.layer == "B.Cu"
        z = -t - 0.015 if back else 0.015
        a, b = (trace.start_x, -trace.start_y), (trace.end_x, -trace.end_y)
        if trace.is_ratsnest:
            offset = -0.08 if back else 0.08
            scene.guides.append(((*a, z + offset), (*b, z + offset)))
        elif trace.layer in ("F.Cu", "B.Cu"):
            shape = LineString([a, b]).buffer(trace.width_mm / 2, quad_segs=6)
            scene.groups["traces"] += surface(
                shape.intersection(outline).difference(drilled), z, (0.16, 0.44, 0.25), back
            )
    for comp in board.components:
        kind = category(comp)
        mesh = registry.get_mesh(kind, comp.footprint) if registry and use_models else None
        if mesh and mesh.faces:
            # KiCad footprint models retain their origin, not their bbox centre.
            triangles = []
            for face in mesh.faces:
                points = [tuple(v * 2.54 for v in p) for p in face.vertices]
                for i in range(1, len(points) - 1):
                    triangles.append(Triangle((points[0], points[i], points[i + 1]), face.color))
            scene.model_count += 1
        else:
            triangles = builtin_component(comp)
        placed = [
            Triangle(tuple(component_transform(comp, p, t) for p in tri.vertices), tri.color)
            for tri in triangles
        ]
        scene.groups["components"] += placed
        back = comp.layer == "B.Cu"
        points = [p for tri in placed for p in tri.vertices]
        ys = [p[1] for p in points] or [-comp.y_mm]
        y = min(ys) - 1.5 if back else max(ys) + 0.7
        y = max(-o.y_mm - o.height_mm + 1.5, min(-o.y_mm - 1.5, y))
        x = max(
            o.x_mm + 0.5,
            min(o.x_mm + o.width_mm - len(comp.ref) * 0.75, comp.x_mm - len(comp.ref) * 0.35),
        )
        scene.labels.append((comp.ref, (x, y, -t - 0.05 if back else 0.05)))
    vertices = [p for group in scene.groups.values() for tri in group for p in tri.vertices]
    if vertices:
        scene.bounds = (
            tuple(min(p[i] for p in vertices) for i in range(3)),
            tuple(max(p[i] for p in vertices) for i in range(3)),
        )
    return scene
