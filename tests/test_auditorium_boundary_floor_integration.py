# -*- coding: utf-8 -*-
"""Rhino-free contract tests for custom auditorium floor integration."""

import ast
import math
import unittest
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]
FLOOR_SURFACE_PATH = (
    ROOT
    / "commands"
    / "auditorium_generator"
    / "floor_surface_geometry.py"
)
RADIAL_LAYOUT_PATH = (
    ROOT
    / "commands"
    / "auditorium_generator"
    / "radial_layout.py"
)


def load_tree():
    return ast.parse(
        FLOOR_SURFACE_PATH.read_text(encoding="utf-8"),
        str(FLOOR_SURFACE_PATH),
    )


def find_function(tree, name):
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise AssertionError("Function not found: {0}".format(name))


def find_nested_function(function_node, name):
    for node in ast.walk(function_node):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise AssertionError("Nested function not found: {0}".format(name))


def dotted_name(node):
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        prefix = dotted_name(node.value)
        if prefix:
            return prefix + "." + node.attr
        return node.attr
    return None


def calls_named(node, name):
    return [
        candidate
        for candidate in ast.walk(node)
        if (
            isinstance(candidate, ast.Call)
            and dotted_name(candidate.func) == name
        )
    ]


def returned_boundary_flags(function_node):
    flags = []
    for candidate in ast.walk(function_node):
        if not isinstance(candidate, ast.Return):
            continue
        if not isinstance(candidate.value, ast.Dict):
            continue
        for key, value in zip(candidate.value.keys, candidate.value.values):
            if (
                isinstance(key, ast.Constant)
                and key.value == "auditorium_boundary_applied"
                and isinstance(value, ast.Constant)
            ):
                flags.append(value.value)
    return flags


class FakeVector(object):
    def __init__(self, *args):
        if len(args) == 1:
            source = args[0]
            self.X = float(source.X)
            self.Y = float(source.Y)
            self.Z = float(source.Z)
        elif len(args) == 3:
            self.X = float(args[0])
            self.Y = float(args[1])
            self.Z = float(args[2])
        else:
            raise TypeError("Vector needs one vector or three coordinates")

    def Unitize(self):
        length = math.sqrt(
            self.X * self.X + self.Y * self.Y + self.Z * self.Z
        )
        if length <= 1e-12:
            return False
        self.X /= length
        self.Y /= length
        self.Z /= length
        return True

    def __mul__(self, scalar):
        return FakeVector(
            self.X * float(scalar),
            self.Y * float(scalar),
            self.Z * float(scalar),
        )

    __rmul__ = __mul__


class FakeVector3dApi(FakeVector):
    @staticmethod
    def CrossProduct(first, second):
        return FakeVector(
            first.Y * second.Z - first.Z * second.Y,
            first.Z * second.X - first.X * second.Z,
            first.X * second.Y - first.Y * second.X,
        )

    @staticmethod
    def Multiply(first, second):
        return (
            first.X * second.X
            + first.Y * second.Y
            + first.Z * second.Z
        )


FakeVector3dApi.ZAxis = FakeVector(0.0, 0.0, 1.0)


class FakePoint(object):
    def __init__(self, x, y, z=0.0):
        self.X = float(x)
        self.Y = float(y)
        self.Z = float(z)

    def __add__(self, vector):
        return FakePoint(
            self.X + vector.X,
            self.Y + vector.Y,
            self.Z + vector.Z,
        )

    def __sub__(self, other):
        if isinstance(other, FakePoint):
            return FakeVector(
                self.X - other.X,
                self.Y - other.Y,
                self.Z - other.Z,
            )
        return FakePoint(
            self.X - other.X,
            self.Y - other.Y,
            self.Z - other.Z,
        )

    def DistanceTo(self, other):
        delta = self - other
        return math.sqrt(
            delta.X * delta.X
            + delta.Y * delta.Y
            + delta.Z * delta.Z
        )


class FakeDomain(object):
    def __init__(self, start=0.0, end=1.0):
        self.T0 = float(start)
        self.T1 = float(end)


class FakeCandidateCurve(object):
    def __init__(self, midpoint_x, label):
        self.midpoint_x = float(midpoint_x)
        self.label = label
        self.Domain = FakeDomain()

    def PointAt(self, unused_parameter):
        return FakePoint(self.midpoint_x, 0.0, 0.0)


class FakeBoundaryCurve(object):
    def __init__(self, candidates):
        self.Domain = FakeDomain()
        self.candidates = list(candidates)
        self.split_parameters = None

    def Split(self, parameters):
        self.split_parameters = list(parameters)
        return list(self.candidates)

    def DuplicateCurve(self):
        return self


class FakePlane(object):
    def ClosestPoint(self, point):
        return FakePoint(point.X, point.Y, 0.0)


class FakeDiagonal(object):
    Length = 20.0


class FakeBoundingBox(object):
    def __init__(self):
        self.Diagonal = FakeDiagonal()
        self.Center = FakePoint(0.0, 0.0, 0.0)


class FakeIntersectionEvent(object):
    IsOverlap = False
    IsPoint = True

    def __init__(self, parameter):
        self.ParameterA = float(parameter)


class FakeIntersectionApi(object):
    events = [FakeIntersectionEvent(0.25), FakeIntersectionEvent(0.75)]

    @classmethod
    def CurveCurve(cls, *unused_args):
        return list(cls.events)


class FakeLineCurve(object):
    def __init__(self, start, end):
        self.start = start
        self.end = end


def load_boundary_wall_function(extrude_calls):
    tree = load_tree()
    selected = ast.Module(
        body=[find_function(tree, "build_audience_boundary_wall_breps")],
        type_ignores=[],
    )
    ast.fix_missing_locations(selected)

    def extrude_wall_curve(curve, min_z, max_z, tolerance):
        result = "wall:" + curve.label
        extrude_calls.append(
            (curve.label, float(min_z), float(max_z), float(tolerance))
        )
        return result

    namespace = {
        "rg": SimpleNamespace(
            Vector3d=FakeVector3dApi,
            LineCurve=FakeLineCurve,
            Intersect=SimpleNamespace(Intersection=FakeIntersectionApi),
        ),
        "extrude_wall_curve": extrude_wall_curve,
    }
    exec(compile(selected, str(FLOOR_SURFACE_PATH), "exec"), namespace)
    return namespace["build_audience_boundary_wall_breps"]


def load_pit_side_transition_domain_function():
    tree = load_tree()
    selected = ast.Module(
        body=[
            find_function(
                tree,
                "calculate_orchestra_pit_side_transition_domains",
            )
        ],
        type_ignores=[],
    )
    ast.fix_missing_locations(selected)
    namespace = {"math": math}
    exec(compile(selected, str(FLOOR_SURFACE_PATH), "exec"), namespace)
    return namespace[
        "calculate_orchestra_pit_side_transition_domains"
    ]


class BoundaryFloorIntegrationAstTests(unittest.TestCase):
    def setUp(self):
        self.tree = load_tree()
        self.function = find_function(
            self.tree,
            "build_floor_surface_geometry",
        )

    def test_boundary_context_is_optional_last_parameter(self):
        positional = [argument.arg for argument in self.function.args.args]
        self.assertEqual("boundary_context", positional[-1])
        self.assertEqual(3, len(self.function.args.defaults))
        self.assertIsInstance(self.function.args.defaults[-1], ast.Constant)
        self.assertIsNone(self.function.args.defaults[-1].value)

    def test_legacy_width_and_sweep_paths_remain_available(self):
        self.assertEqual(
            1,
            len(calls_named(self.function, "calculate_seat_layout_width")),
        )
        self.assertGreaterEqual(
            len(calls_named(self.function, "radial_available_chord_width")),
            2,
        )

        source_builder = find_nested_function(
            self.function,
            "build_auditorium_source_surface",
        )
        radial_calls = calls_named(
            source_builder,
            "sweep_section_curve_radially",
        )
        self.assertTrue(
            any(len(call.args) == 2 for call in radial_calls),
            "The legacy radial sweep must retain its default half-angle.",
        )
        extrusion_calls = calls_named(
            source_builder,
            "extrude_section_curve_across_width",
        )
        self.assertEqual(1, len(extrusion_calls))
        width_expression = extrusion_calls[0].args[2]
        self.assertIsInstance(width_expression, ast.IfExp)
        self.assertEqual("source_floor_width", dotted_name(width_expression.body))
        self.assertEqual("floor_width", dotted_name(width_expression.orelse))

        flags = returned_boundary_flags(self.function)
        self.assertGreaterEqual(flags.count(False), 2)
        self.assertIn(True, flags)

    def test_custom_boundary_builds_extents_cutter_and_clips_sources(self):
        self.assertEqual(
            1,
            len(calls_named(self.function, "calculate_boundary_plan_extents")),
        )
        self.assertEqual(
            1,
            len(calls_named(self.function, "build_boundary_vertical_cutter")),
        )
        self.assertEqual(
            1,
            len(calls_named(self.function, "split_brep_inside_boundary")),
        )

        source_builder = find_nested_function(
            self.function,
            "build_auditorium_source_surface",
        )
        full_radial_calls = [
            call
            for call in calls_named(
                source_builder,
                "sweep_section_curve_radially",
            )
            if len(call.args) == 4
        ]
        self.assertEqual(1, len(full_radial_calls))
        self.assertEqual("-math.pi", ast.unparse(full_radial_calls[0].args[2]))
        self.assertEqual("math.pi", ast.unparse(full_radial_calls[0].args[3]))

    def test_full_radial_source_keeps_the_explicit_rear_seam(self):
        radial_tree = ast.parse(
            RADIAL_LAYOUT_PATH.read_text(encoding="utf-8"),
            str(RADIAL_LAYOUT_PATH),
        )
        sweep_function = find_function(
            radial_tree,
            "sweep_section_curve_radially",
        )
        revolve_calls = calls_named(
            sweep_function,
            "rg.RevSurface.Create",
        )
        self.assertEqual(1, len(revolve_calls))
        self.assertEqual(4, len(revolve_calls[0].args))
        self.assertEqual(
            "float(start_angle)",
            ast.unparse(revolve_calls[0].args[2]),
        )
        self.assertEqual(
            "float(end_angle)",
            ast.unparse(revolve_calls[0].args[3]),
        )

    def test_custom_boundary_builds_ceiling_and_stage_open_walls(self):
        ceiling_calls = calls_named(
            self.function,
            "build_boundary_ceiling_brep",
        )
        self.assertEqual(1, len(ceiling_calls))
        self.assertEqual(
            "boundary_context",
            dotted_name(ceiling_calls[0].args[0]),
        )

        wall_calls = calls_named(
            self.function,
            "build_audience_boundary_wall_breps",
        )
        self.assertEqual(1, len(wall_calls))
        self.assertEqual("boundary_context", dotted_name(wall_calls[0].args[0]))
        self.assertEqual(
            "stage_surface_point",
            dotted_name(wall_calls[0].args[1]),
        )
        self.assertEqual(
            "audience_direction",
            dotted_name(wall_calls[0].args[2]),
        )

    def test_custom_boundary_extends_rear_floor_to_boundary(self):
        source = ast.unparse(self.function)
        self.assertIn(
            "boundary_extents['max_longitudinal_mm']",
            source,
        )
        self.assertIn("boundary_extents['max_radius_mm']", source)
        self.assertIn("source_rear_extent - rear_wall_x > 1e-08", source)
        self.assertIn(
            "AuditoriumBoundaryRearFloorExtension",
            source,
        )

        rear_line_found = False
        for call in calls_named(self.function, "rg.LineCurve"):
            call_source = ast.unparse(call)
            if (
                "rear_wall_x" in call_source
                and "source_rear_extent" in call_source
            ):
                rear_line_found = True
                break
        self.assertTrue(rear_line_found)

    def test_custom_boundary_pit_adds_only_clipped_side_floor_sources(self):
        source = ast.unparse(self.function)
        self.assertIn(
            "custom_boundary and float(params.get('orchestra_pit_depth', 0.0)) > 1e-08",
            source,
        )
        source_calls = calls_named(
            self.function,
            "build_orchestra_pit_side_transition_source_breps",
        )
        self.assertEqual(1, len(source_calls))
        self.assertEqual(
            "boundary_extents",
            dotted_name(source_calls[0].args[4]),
        )
        self.assertIn("OrchestraPitSideTransition", source)

        source_builder = find_function(
            self.tree,
            "build_orchestra_pit_side_transition_source_breps",
        )
        self.assertEqual(
            1,
            len(
                calls_named(
                    source_builder,
                    "rg.Brep.CreateFromCornerPoints",
                )
            ),
        )
        radial_calls = calls_named(
            source_builder,
            "sweep_section_curve_radially",
        )
        self.assertEqual(1, len(radial_calls))
        self.assertEqual("domain_start", dotted_name(radial_calls[0].args[2]))
        self.assertEqual("domain_end", dotted_name(radial_calls[0].args[3]))


class OrchestraPitSideTransitionDomainTests(unittest.TestCase):
    def setUp(self):
        self.domains = load_pit_side_transition_domain_function()

    def test_rectangular_domains_leave_the_opening_footprint_empty(self):
        result = self.domains(
            False,
            {
                "min_lateral_mm": -8000.0,
                "max_lateral_mm": 7000.0,
            },
            12000.0,
        )
        self.assertEqual(
            ((-8000.0, -6000.0), (6000.0, 7000.0)),
            result,
        )

    def test_rectangular_domains_skip_sides_outside_the_boundary(self):
        result = self.domains(
            False,
            {
                "min_lateral_mm": -8000.0,
                "max_lateral_mm": 1000.0,
            },
            12000.0,
        )
        self.assertEqual(((-8000.0, -6000.0),), result)

    def test_radial_domains_are_the_two_sectors_outside_half_angle(self):
        result = self.domains(
            True,
            None,
            12000.0,
            {"half_angle": 0.4},
        )
        self.assertEqual(
            ((-math.pi, -0.4), (0.4, math.pi)),
            result,
        )


class AudienceBoundaryWallBehaviorTests(unittest.TestCase):
    def test_stageward_and_interface_segments_stay_open(self):
        extrude_calls = []
        build_walls = load_boundary_wall_function(extrude_calls)
        curve = FakeBoundaryCurve(
            [
                FakeCandidateCurve(-2.0, "stageward"),
                FakeCandidateCurve(0.05, "on-interface"),
                FakeCandidateCurve(0.101, "audienceward-near"),
                FakeCandidateCurve(4.0, "audienceward-far"),
            ]
        )
        context = {
            "curve": curve,
            "plane": FakePlane(),
            "bbox": FakeBoundingBox(),
            "tolerance": 0.1,
        }

        walls = build_walls(
            context,
            FakePoint(0.0, 0.0, 3.0),
            FakeVector(1.0, 0.0, 0.0),
            -1.0,
            8.0,
            0.01,
        )

        self.assertEqual([0.25, 0.75], curve.split_parameters)
        self.assertEqual(
            ["wall:audienceward-near", "wall:audienceward-far"],
            walls,
        )
        self.assertEqual(
            [
                ("audienceward-near", -1.0, 8.0, 0.1),
                ("audienceward-far", -1.0, 8.0, 0.1),
            ],
            extrude_calls,
        )


if __name__ == "__main__":
    unittest.main()
