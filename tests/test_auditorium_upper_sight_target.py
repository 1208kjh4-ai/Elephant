# -*- coding: utf-8 -*-
"""Rhino-free regressions for the upper stage sight target datum."""

import ast
import copy
import unittest
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]
PREVIEW_GEOMETRY_PATH = (
    ROOT
    / "commands"
    / "auditorium_generator"
    / "preview_geometry.py"
)


def _assignment_name(node):
    if not isinstance(node, ast.Assign) or len(node.targets) != 1:
        return None
    target = node.targets[0]
    return target.id if isinstance(target, ast.Name) else None


def _build_preview_node():
    tree = ast.parse(
        PREVIEW_GEOMETRY_PATH.read_text(encoding="utf-8"),
        str(PREVIEW_GEOMETRY_PATH),
    )
    for node in tree.body:
        if (
            isinstance(node, ast.FunctionDef)
            and node.name == "build_preview_geometry"
        ):
            return node
    raise AssertionError("build_preview_geometry was not found.")


def _execute_sight_target_initialization(
    stage_data,
    params,
    build_plan_layout_context,
):
    """Execute the production statements that establish both sight targets."""
    wanted_assignments = {
        "mm_scale",
        "audience_datum_point",
        "opening_stage_point",
        "direction",
        "opening_width_mm",
        "opening_height_mm",
        "layout_context",
        "stage_point",
        "stage_sight_point",
        "stage_upper_sight_point",
    }
    statements = []
    for node in _build_preview_node().body:
        assignment_name = _assignment_name(node)
        if assignment_name in wanted_assignments:
            statements.append(copy.deepcopy(node))
            continue
        if (
            isinstance(node, ast.If)
            and any(
                isinstance(child, ast.Constant)
                and child.value == "flipped"
                for child in ast.walk(node.test)
            )
        ):
            statements.append(copy.deepcopy(node))

    found_assignments = {
        _assignment_name(node)
        for node in statements
        if _assignment_name(node) is not None
    }
    missing = wanted_assignments - found_assignments
    if missing:
        raise AssertionError(
            "Sight-target AST extraction is incomplete: {0}".format(
                sorted(missing)
            )
        )

    module = ast.Module(body=statements, type_ignores=[])
    ast.fix_missing_locations(module)
    namespace = {
        "rg": SimpleNamespace(Point3d=_Point, Vector3d=_Vector),
        "unit_scale_from_mm": lambda _doc: 0.1,
        "build_plan_layout_context": build_plan_layout_context,
        "point_at": _point_at,
        "stage_data": stage_data,
        "params": params,
        "doc": object(),
    }
    exec(
        compile(module, str(PREVIEW_GEOMETRY_PATH), "exec"),
        namespace,
    )
    return namespace


class _Vector(object):
    ZAxis = None

    def __init__(self, x=0.0, y=0.0, z=0.0):
        if isinstance(x, _Vector):
            self.x, self.y, self.z = x.x, x.y, x.z
        elif isinstance(x, (tuple, list)):
            self.x, self.y, self.z = map(float, x)
        else:
            self.x = float(x)
            self.y = float(y)
            self.z = float(z)

    def __mul__(self, scalar):
        return _Vector(
            self.x * float(scalar),
            self.y * float(scalar),
            self.z * float(scalar),
        )

    __rmul__ = __mul__

    def Reverse(self):
        self.x = -self.x
        self.y = -self.y
        self.z = -self.z


_Vector.ZAxis = _Vector(0.0, 0.0, 1.0)


class _Point(object):
    def __init__(self, x=0.0, y=0.0, z=0.0):
        if isinstance(x, _Point):
            self.x, self.y, self.z = x.x, x.y, x.z
        elif isinstance(x, (tuple, list)):
            self.x, self.y, self.z = map(float, x)
        else:
            self.x = float(x)
            self.y = float(y)
            self.z = float(z)

    def __add__(self, vector):
        return _Point(
            self.x + vector.x,
            self.y + vector.y,
            self.z + vector.z,
        )


def _point_at(base, direction, x_mm, z_mm, mm_scale):
    return (
        _Point(base)
        + _Vector(direction) * (float(x_mm) * mm_scale)
        + _Vector.ZAxis * (float(z_mm) * mm_scale)
    )


class UpperSightTargetDatumTests(unittest.TestCase):
    def setUp(self):
        self.stage_data = {
            "stage_point": _Point(10.0, 20.0, 30.0),
            "default_direction": _Vector(1.0, 0.0, 0.0),
        }
        self.params = {
            "stage_height": 1000.0,
            "stage_sight_point_z": 50.0,
            "opening_width": 12000.0,
            "opening_height": 8000.0,
            "plan_layout_radius": 0.0,
            "flipped": False,
        }

    @staticmethod
    def _layout_builder(reference_offset):
        def build(stage_point, direction, _width, radius, scale):
            opening_midpoint = _Point(stage_point)
            reference_midpoint = (
                opening_midpoint
                + _Vector(direction) * (reference_offset * scale)
            )
            return {
                "mode": "radial" if radius else "rectangular",
                "opening_stage_point": opening_midpoint,
                "reference_mid_point": reference_midpoint,
            }

        return build

    def test_rectangular_upper_and_lower_targets_share_plan_midpoint(self):
        result = _execute_sight_target_initialization(
            self.stage_data,
            dict(self.params),
            self._layout_builder(reference_offset=0.0),
        )

        lower = result["stage_sight_point"]
        upper = result["stage_upper_sight_point"]
        opening = result["opening_stage_point"]

        self.assertEqual((opening.x, opening.y), (lower.x, lower.y))
        self.assertEqual((opening.x, opening.y), (upper.x, upper.y))
        self.assertEqual(930.0, upper.z)

    def test_radial_upper_target_uses_opening_chord_midpoint(self):
        params = dict(self.params)
        params["plan_layout_radius"] = 15000.0
        result = _execute_sight_target_initialization(
            self.stage_data,
            params,
            self._layout_builder(reference_offset=750.0),
        )

        opening = result["opening_stage_point"]
        reference = result["stage_point"]
        lower = result["stage_sight_point"]
        upper = result["stage_upper_sight_point"]

        self.assertNotEqual(
            (opening.x, opening.y),
            (reference.x, reference.y),
        )
        self.assertEqual((reference.x, reference.y), (lower.x, lower.y))
        self.assertEqual((opening.x, opening.y), (upper.x, upper.y))
        self.assertNotEqual((reference.x, reference.y), (upper.x, upper.y))
        self.assertEqual(930.0, upper.z)


if __name__ == "__main__":
    unittest.main()
