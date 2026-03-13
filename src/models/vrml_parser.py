"""VRML 2.0 parser for KiCad 3D models (.wrl files).

Parses the subset of VRML 2.0 used by KiCad StepUp exports:
  Shape, IndexedFaceSet, Coordinate, Material, Transform, DEF/USE.

Returns a Mesh3D containing triangulated faces with RGB material colours.
Coordinates are in millimetres (KiCad native unit).
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field


# ── Data structures ────────────────────────────────────────────────────────

@dataclass
class Face:
    """A single triangulated polygon face."""
    vertices: list[tuple[float, float, float]]
    color: tuple[float, float, float]  # diffuseColor RGB 0..1


@dataclass
class Mesh3D:
    """Parsed 3D mesh ready for rendering."""
    faces: list[Face] = field(default_factory=list)
    bbox_min: tuple[float, float, float] = (0.0, 0.0, 0.0)
    bbox_max: tuple[float, float, float] = (0.0, 0.0, 0.0)

    def compute_bbox(self):
        if not self.faces:
            return
        xs, ys, zs = [], [], []
        for f in self.faces:
            for v in f.vertices:
                xs.append(v[0])
                ys.append(v[1])
                zs.append(v[2])
        self.bbox_min = (min(xs), min(ys), min(zs))
        self.bbox_max = (max(xs), max(ys), max(zs))


# ── Tokeniser ─────────────────────────────────────────────────────────────

_TOKEN_RE = re.compile(
    r'#[^\n]*'           # comment → skip
    r'|"[^"]*"'          # quoted string
    r'|[{}\[\]]'         # braces / brackets
    r'|[^\s{}\[\],]+'    # word token
)


def _tokenise(text: str) -> list[str]:
    """Split VRML source into tokens, stripping comments."""
    return [t for t in _TOKEN_RE.findall(text) if not t.startswith('#')]


# ── Parser ─────────────────────────────────────────────────────────────────

def _parse_floats(tokens: list[str], pos: int) -> tuple[list[float], int]:
    """Parse a bracketed list of float values: [ 1.0 2.0 ... ]."""
    if tokens[pos] != '[':
        # Single value
        return [float(tokens[pos])], pos + 1
    pos += 1  # skip '['
    vals: list[float] = []
    while pos < len(tokens) and tokens[pos] != ']':
        t = tokens[pos]
        if t == ',':
            pos += 1
            continue
        try:
            vals.append(float(t))
        except ValueError:
            break
        pos += 1
    if pos < len(tokens) and tokens[pos] == ']':
        pos += 1
    return vals, pos


def _parse_ints(tokens: list[str], pos: int) -> tuple[list[int], int]:
    """Parse a bracketed list of int values: [ 0,1,2,-1, ... ]."""
    if tokens[pos] != '[':
        return [int(tokens[pos])], pos + 1
    pos += 1
    vals: list[int] = []
    while pos < len(tokens) and tokens[pos] != ']':
        t = tokens[pos]
        if t == ',':
            pos += 1
            continue
        try:
            vals.append(int(t))
        except ValueError:
            break
        pos += 1
    if pos < len(tokens) and tokens[pos] == ']':
        pos += 1
    return vals, pos


def _skip_block(tokens: list[str], pos: int) -> int:
    """Skip a { ... } block."""
    depth = 1
    while pos < len(tokens) and depth > 0:
        if tokens[pos] == '{':
            depth += 1
        elif tokens[pos] == '}':
            depth -= 1
        pos += 1
    return pos


def _apply_transform(vertices: list[tuple[float, float, float]],
                     translation: tuple[float, float, float],
                     rotation: tuple[float, float, float, float],
                     scale: tuple[float, float, float],
                     ) -> list[tuple[float, float, float]]:
    """Apply translation, rotation (axis-angle), and scale to vertices."""
    result = []
    sx, sy, sz = scale
    tx, ty, tz = translation

    # Rotation via axis-angle (Rodrigues' formula)
    ax, ay, az, angle = rotation
    has_rot = abs(angle) > 1e-9
    if has_rot:
        c = math.cos(angle)
        s = math.sin(angle)
        t = 1 - c
        # Normalise axis
        length = math.sqrt(ax*ax + ay*ay + az*az)
        if length > 1e-9:
            ax, ay, az = ax/length, ay/length, az/length

    for vx, vy, vz in vertices:
        # Scale
        x, y, z = vx * sx, vy * sy, vz * sz
        # Rotate
        if has_rot:
            rx = (t*ax*ax + c)*x + (t*ax*ay - s*az)*y + (t*ax*az + s*ay)*z
            ry = (t*ax*ay + s*az)*x + (t*ay*ay + c)*y + (t*ay*az - s*ax)*z
            rz = (t*ax*az - s*ay)*x + (t*ay*az + s*ax)*y + (t*az*az + c)*z
            x, y, z = rx, ry, rz
        # Translate
        result.append((x + tx, y + ty, z + tz))
    return result


def parse_vrml(filepath: str) -> Mesh3D:
    """Parse a KiCad VRML 2.0 (.wrl) file into a Mesh3D.

    Args:
        filepath: Path to the .wrl file.

    Returns:
        Mesh3D with faces and computed bounding box.
    """
    with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
        text = f.read()

    tokens = _tokenise(text)
    n = len(tokens)

    materials: dict[str, tuple[float, float, float]] = {}
    mesh = Mesh3D()

    # State for current Transform stack
    transform_stack: list[tuple[
        tuple[float, float, float],        # translation
        tuple[float, float, float, float], # rotation
        tuple[float, float, float],        # scale
    ]] = []

    pos = 0
    while pos < n:
        tok = tokens[pos]

        # ── DEF material_name Material { ... } ──
        if tok == 'DEF' and pos + 2 < n:
            mat_name = tokens[pos + 1]
            # Look ahead for Material keyword
            if tokens[pos + 2] == 'Material' or (pos + 3 < n and tokens[pos + 3] == 'Material'):
                pos += 2
                # Find the opening brace
                while pos < n and tokens[pos] != '{':
                    pos += 1
                if pos < n:
                    pos += 1  # skip '{'
                    dc = (0.5, 0.5, 0.5)
                    while pos < n and tokens[pos] != '}':
                        if tokens[pos] == 'diffuseColor' and pos + 3 < n:
                            try:
                                dc = (float(tokens[pos+1]),
                                      float(tokens[pos+2]),
                                      float(tokens[pos+3]))
                            except (ValueError, IndexError):
                                pass
                            pos += 4
                        else:
                            pos += 1
                    if pos < n:
                        pos += 1  # skip '}'
                    materials[mat_name] = dc
                continue
            else:
                pos += 1
                continue

        # ── Transform { ... } ──
        if tok == 'Transform' and pos + 1 < n and tokens[pos + 1] == '{':
            pos += 2  # skip 'Transform {'
            translation = (0.0, 0.0, 0.0)
            rotation = (0.0, 1.0, 0.0, 0.0)
            scale = (1.0, 1.0, 1.0)

            # Parse transform fields until 'children' or nested block
            while pos < n and tokens[pos] != '}':
                if tokens[pos] == 'translation' and pos + 3 < n:
                    try:
                        translation = (float(tokens[pos+1]),
                                       float(tokens[pos+2]),
                                       float(tokens[pos+3]))
                    except ValueError:
                        pass
                    pos += 4
                elif tokens[pos] == 'rotation' and pos + 4 < n:
                    try:
                        rotation = (float(tokens[pos+1]),
                                    float(tokens[pos+2]),
                                    float(tokens[pos+3]),
                                    float(tokens[pos+4]))
                    except ValueError:
                        pass
                    pos += 5
                elif tokens[pos] == 'scale' and pos + 3 < n:
                    try:
                        scale = (float(tokens[pos+1]),
                                 float(tokens[pos+2]),
                                 float(tokens[pos+3]))
                    except ValueError:
                        pass
                    pos += 4
                elif tokens[pos] == 'children' or tokens[pos] == '[':
                    transform_stack.append((translation, rotation, scale))
                    pos += 1
                    if pos < n and tokens[pos] == '[':
                        pos += 1
                    break
                else:
                    if tokens[pos] == '{':
                        pos = _skip_block(tokens, pos + 1)
                    else:
                        pos += 1
            continue

        # ── Shape { ... } (geometry with IndexedFaceSet) ──
        if tok == 'Shape' and pos + 1 < n and tokens[pos + 1] == '{':
            pos += 2  # skip 'Shape {'
            coord_points: list[tuple[float, float, float]] = []
            face_indices: list[int] = []
            color: tuple[float, float, float] = (0.5, 0.5, 0.5)

            depth = 1
            while pos < n and depth > 0:
                t = tokens[pos]

                if t == '{':
                    depth += 1
                    pos += 1
                elif t == '}':
                    depth -= 1
                    pos += 1
                elif t == 'coordIndex':
                    pos += 1
                    face_indices, pos = _parse_ints(tokens, pos)
                elif t == 'point':
                    pos += 1
                    floats, pos = _parse_floats(tokens, pos)
                    # Group into xyz triples
                    for i in range(0, len(floats) - 2, 3):
                        coord_points.append((floats[i], floats[i+1], floats[i+2]))
                elif t == 'USE' and pos + 1 < n:
                    mat_ref = tokens[pos + 1]
                    if mat_ref in materials:
                        color = materials[mat_ref]
                    pos += 2
                elif t == 'diffuseColor' and pos + 3 < n:
                    try:
                        color = (float(tokens[pos+1]),
                                 float(tokens[pos+2]),
                                 float(tokens[pos+3]))
                    except (ValueError, IndexError):
                        pass
                    pos += 4
                elif t == 'DEF' and pos + 2 < n:
                    mat_name = tokens[pos + 1]
                    if tokens[pos + 2] == 'Material' or tokens[pos + 2] == '{':
                        pos += 2
                        continue
                    pos += 2
                elif t == 'Material' and pos + 1 < n and tokens[pos + 1] == '{':
                    pos += 2  # skip 'Material {'
                    mat_depth = 1
                    while pos < n and mat_depth > 0:
                        if tokens[pos] == '{':
                            mat_depth += 1
                        elif tokens[pos] == '}':
                            mat_depth -= 1
                        elif tokens[pos] == 'diffuseColor' and pos + 3 < n:
                            try:
                                color = (float(tokens[pos+1]),
                                         float(tokens[pos+2]),
                                         float(tokens[pos+3]))
                            except (ValueError, IndexError):
                                pass
                            pos += 3
                        pos += 1
                else:
                    pos += 1

            # Apply transforms from stack
            if coord_points and transform_stack:
                for translation, rotation, scale in transform_stack:
                    coord_points = _apply_transform(
                        coord_points, translation, rotation, scale)

            # Triangulate faces from coordIndex
            if coord_points and face_indices:
                face_verts: list[int] = []
                for idx in face_indices:
                    if idx == -1:
                        # End of face polygon → triangulate as fan
                        if len(face_verts) >= 3:
                            v0 = face_verts[0]
                            for k in range(1, len(face_verts) - 1):
                                v1 = face_verts[k]
                                v2 = face_verts[k + 1]
                                if (0 <= v0 < len(coord_points) and
                                    0 <= v1 < len(coord_points) and
                                    0 <= v2 < len(coord_points)):
                                    mesh.faces.append(Face(
                                        vertices=[coord_points[v0],
                                                  coord_points[v1],
                                                  coord_points[v2]],
                                        color=color,
                                    ))
                        face_verts = []
                    else:
                        face_verts.append(idx)
                # Handle case where last face polygon doesn't end with -1
                if len(face_verts) >= 3:
                    v0 = face_verts[0]
                    for k in range(1, len(face_verts) - 1):
                        v1 = face_verts[k]
                        v2 = face_verts[k + 1]
                        if (0 <= v0 < len(coord_points) and
                            0 <= v1 < len(coord_points) and
                            0 <= v2 < len(coord_points)):
                            mesh.faces.append(Face(
                                vertices=[coord_points[v0],
                                          coord_points[v1],
                                          coord_points[v2]],
                                color=color,
                            ))
            continue

        # ── Close bracket for Transform children ──
        if tok == ']' and transform_stack:
            pos += 1
            continue
        if tok == '}' and transform_stack:
            transform_stack.pop()
            pos += 1
            continue

        pos += 1

    mesh.compute_bbox()
    return mesh
