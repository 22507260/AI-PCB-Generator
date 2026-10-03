"""Physical geometry and footprint-coordinate regression tests."""

import math

import pytest
from shapely.geometry import Point, Polygon

from src.models.model_registry import ModelRegistry
from src.models.pcb_scene import build_scene, builtin_component, component_transform, local_pads
from src.models.vrml_parser import Face, Mesh3D, parse_vrml
from src.pcb.generator import Board, BoardOutline, Pad, PlacedComponent, TraceSegment, Via


def area(triangles):
    return sum(Polygon([(x, y) for x, y, z in tri.vertices]).area for tri in triangles)


def test_outline_origin_thickness_and_no_invented_holes():
    board = Board(outline=BoardOutline(5, 7, 30, 20), thickness_mm=2.4)
    scene = build_scene(board)
    assert scene.bounds == ((5, -27, -2.4), (35, -7, 0))
    top = [tri for tri in scene.groups["board"] if tri.normal[2] > 0.9]
    assert area(top) == pytest.approx(600)
    assert len(top) == 2


def test_through_holes_are_open_in_both_board_and_pads():
    pad = Pad(x_mm=10, y_mm=10, width_mm=2, height_mm=2, drill_mm=1)
    board = Board(
        outline=BoardOutline(0, 0, 20, 20),
        components=[PlacedComponent(ref="X1", pads=[pad])],
        vias=[Via(x_mm=15, y_mm=15, diameter_mm=1.5, drill_mm=0.6)],
    )
    scene = build_scene(board)
    for key in ("board", "pads"):
        faces = [tri for tri in scene.groups[key] if abs(tri.normal[2]) > 0.9]
        for tri in faces:
            polygon = Polygon([(x, y) for x, y, z in tri.vertices])
            assert not polygon.contains(Point(10, -10))
            assert not polygon.contains(Point(15, -15))
    top = [tri for tri in scene.groups["board"] if tri.normal[2] > 0.9]
    assert area(top) == pytest.approx(400 - math.pi * (0.5**2 + 0.3**2), rel=0.0001)


@pytest.mark.parametrize("layer,z", [("F.Cu", 3), ("B.Cu", -4.6)])
def test_component_rotation_origin_and_back_side(layer, z):
    comp = PlacedComponent(x_mm=20, y_mm=10, rotation_deg=90, layer=layer)
    transformed = component_transform(comp, (2, 0, 3), 1.6)
    assert transformed == pytest.approx((20, -12, z))
    # Asymmetric model origin is retained; bbox centering would break this.
    assert component_transform(comp, (0, 0, 0), 1.6) == pytest.approx(
        (20, -10, -1.6 if layer == "B.Cu" else 0)
    )


@pytest.mark.parametrize("layer", ["F.Cu", "B.Cu"])
def test_builtin_leads_keep_world_pad_locations(layer):
    comp = PlacedComponent(
        x_mm=8,
        y_mm=5,
        rotation_deg=35,
        layer=layer,
        pads=[Pad(x_mm=7, y_mm=4), Pad(x_mm=9, y_mm=6)],
    )
    for x, y, pad in local_pads(comp):
        world = component_transform(comp, (x, y, 0), 1.6)
        assert world[:2] == pytest.approx((pad.x_mm, -pad.y_mm))


def test_smd_capacitor_uses_package_not_value():
    comp = PlacedComponent(ref="C1", value="10uF", footprint="Capacitor_SMD:C_0805_2012Metric")
    vertices = [p for tri in builtin_component(comp) for p in tri.vertices]
    assert max(p[2] for p in vertices) < 1.0
    assert max(p[0] for p in vertices) - min(p[0] for p in vertices) == pytest.approx(2)


def test_layer_specific_pads_traces_and_guides():
    board = Board(
        components=[
            PlacedComponent(
                ref="R1",
                layer="B.Cu",
                pads=[Pad(x_mm=3, y_mm=3, width_mm=2, height_mm=1, shape="rect")],
            )
        ],
        traces=[
            TraceSegment(start_x=1, start_y=1, end_x=5, end_y=1, layer="B.Cu"),
            TraceSegment(start_x=1, start_y=2, end_x=5, end_y=2, is_ratsnest=True),
            TraceSegment(start_x=1, start_y=3, end_x=5, end_y=3, layer="In1.Cu"),
        ],
    )
    scene = build_scene(board)
    assert all(p[2] < -board.thickness_mm for tri in scene.groups["pads"] for p in tri.vertices)
    assert all(p[2] < -board.thickness_mm for tri in scene.groups["traces"] for p in tri.vertices)
    assert len(scene.guides) == 1
    assert all(a[2] == b[2] for a, b in scene.guides)


def test_wrl_units_origin_and_missing_model_fallback():
    class Registry:
        def get_mesh(self, category, package):
            if package == "known":
                return Mesh3D(faces=[Face([(0, 0, 0), (1, 0, 0), (0, 1, 1)], (0.3, 0.4, 0.5))])
            return None

    comp = PlacedComponent(ref="U1", footprint="known", x_mm=10, y_mm=5)
    scene = build_scene(Board(components=[comp]), Registry())
    assert scene.model_count == 1
    assert scene.groups["components"][0].vertices == (
        (10, -5, 0),
        (12.54, -5, 0),
        (10, -2.46, 2.54),
    )
    comp.footprint = "missing"
    scene = build_scene(Board(components=[comp]), Registry())
    assert scene.model_count == 0
    assert scene.groups["components"]


def test_model_registry_exact_footprint_and_ambiguous_connector(tmp_path):
    library = tmp_path / "Connector_USB.3dshapes"
    library.mkdir()
    path = library / "USB_C_Receptacle_Test.wrl"
    path.write_text("#VRML V2.0 utf8")
    registry = ModelRegistry(str(tmp_path))
    assert registry.find_model("usb_connector", "Connector_USB:USB_C_Receptacle_Test") == str(path)
    assert registry.find_model("usb_connector", "USB_UNKNOWN") is None
    assert registry.find_model("usb_connector", "../Connector_USB:Test") is None


def test_overlapping_holes_and_edge_hole_are_valid():
    board = Board(
        outline=BoardOutline(0, 0, 10, 10),
        vias=[Via(x_mm=0, y_mm=5, drill_mm=2), Via(x_mm=0.5, y_mm=5, drill_mm=2)],
    )
    scene = build_scene(board)
    assert scene.groups["board"]
    assert all(
        math.isfinite(value) for tri in scene.groups["board"] for p in tri.vertices for value in p
    )


def test_rotated_rectangular_pad():
    comp = PlacedComponent(
        ref="R1", rotation_deg=90, pads=[Pad(x_mm=5, y_mm=5, width_mm=4, height_mm=1, shape="rect")]
    )
    scene = build_scene(Board(components=[comp]))
    points = [p for tri in scene.groups["pads"] for p in tri.vertices]
    assert max(p[0] for p in points) - min(p[0] for p in points) == pytest.approx(1)
    assert max(p[1] for p in points) - min(p[1] for p in points) == pytest.approx(4)


def test_nested_wrl_transforms_apply_from_inside_out(tmp_path):
    path = tmp_path / "nested.wrl"
    path.write_text("""#VRML V2.0 utf8
    Transform { scale 2 2 2 children [
      Transform { translation 1 0 0 children [
        Shape { geometry IndexedFaceSet {
          coord Coordinate { point [0 0 0, 1 0 0, 0 1 0] }
          coordIndex [0 1 2 -1]
        } }
      ] }
    ] }
    """)
    mesh = parse_vrml(str(path))
    assert mesh.faces[0].vertices == [(2, 0, 0), (4, 0, 0), (2, 2, 0)]
