# -*- coding: utf-8 -*-
"""Focused regression tests for the latest auditorium geometry changes.

The production geometry modules import RhinoCommon, so the Rhino-dependent
functions are loaded selectively from their AST and exercised with small fake
APIs.  This keeps the tests runnable in ordinary CPython without weakening the
older characterization/parity suite.
"""

import ast
import copy
import unittest
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]
GEOMETRY_METADATA_PATH = (
    ROOT
    / "commands"
    / "auditorium_generator"
    / "geometry_metadata.py"
)
PREVIEW_GEOMETRY_PATH = (
    ROOT
    / "commands"
    / "auditorium_generator"
    / "preview_geometry.py"
)
FLOOR_SURFACE_GEOMETRY_PATH = (
    ROOT
    / "commands"
    / "auditorium_generator"
    / "floor_surface_geometry.py"
)


def _parse(path):
    return ast.parse(path.read_text(encoding="utf-8"), str(path))


def _function_node(path, function_name):
    for node in _parse(path).body:
        if isinstance(node, ast.FunctionDef) and node.name == function_name:
            return node
    raise AssertionError(
        "Function {0!r} was not found in {1}.".format(
            function_name,
            path,
        )
    )


def _load_selected_function(path, function_name, namespace):
    node = copy.deepcopy(_function_node(path, function_name))
    module = ast.Module(body=[node], type_ignores=[])
    ast.fix_missing_locations(module)
    loaded = dict(namespace)
    exec(compile(module, str(path), "exec"), loaded)
    return loaded[function_name]


def _assignment_name(node):
    if not isinstance(node, ast.Assign) or len(node.targets) != 1:
        return None
    target = node.targets[0]
    return target.id if isinstance(target, ast.Name) else None


def _contains_string(node, value):
    return any(
        isinstance(child, ast.Constant) and child.value == value
        for child in ast.walk(node)
    )


def _execute_rear_floor_slice(params, result, balcony_results):
    """Execute the exact rear-wall/closure statements from the preview."""
    function = _function_node(
        PREVIEW_GEOMETRY_PATH,
        "build_preview_geometry",
    )
    wanted_assignments = {
        "x_values",
        "rear_aisle_width",
        "tier_rear_edges",
        "rear_wall_x",
        "preview_curves",
        "bake_curves",
    }
    statements = []
    for node in function.body:
        assignment_name = _assignment_name(node)
        if assignment_name in wanted_assignments:
            statements.append(copy.deepcopy(node))
            continue
        if (
            isinstance(node, ast.Expr)
            and isinstance(node.value, ast.Call)
            and isinstance(node.value.func, ast.Attribute)
            and isinstance(node.value.func.value, ast.Name)
            and node.value.func.value.id == "tier_rear_edges"
            and node.value.func.attr == "extend"
        ):
            statements.append(copy.deepcopy(node))
            continue
        if (
            isinstance(node, ast.For)
            and _contains_string(node, "Balcony{0:02d}RearFloorClosure")
        ):
            statements.append(copy.deepcopy(node))

    assignment_names = {
        _assignment_name(node)
        for node in statements
        if _assignment_name(node) is not None
    }
    missing = wanted_assignments - assignment_names
    if missing:
        raise AssertionError(
            "Rear-floor AST extraction is incomplete: {0}".format(
                sorted(missing)
            )
        )
    if not any(isinstance(node, ast.For) for node in statements):
        raise AssertionError("Rear-floor closure loop was not extracted.")

    def point_at(_stage_point, _direction, x_value, z_value, _scale):
        return {"x": float(x_value), "z": float(z_value)}

    def line_curve(start, end):
        return {"start": start, "end": end}

    namespace = {
        "params": params,
        "result": result,
        "balcony_results": balcony_results,
        "balcony_result_is_displayable": lambda item: item is not None,
        "point_at": point_at,
        "line_curve": line_curve,
        "stage_point": object(),
        "direction": object(),
        "mm_scale": 1.0,
        "PREVIEW_FLOOR": "floor-color",
    }
    module = ast.Module(body=statements, type_ignores=[])
    ast.fix_missing_locations(module)
    exec(compile(module, str(PREVIEW_GEOMETRY_PATH), "exec"), namespace)
    return {
        "rear_wall_x": namespace["rear_wall_x"],
        "preview_curves": namespace["preview_curves"],
        "bake_curves": namespace["bake_curves"],
    }


class GeometryMetadataRecentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.section_floor_surface_name = staticmethod(
            _load_selected_function(
                GEOMETRY_METADATA_PATH,
                "section_floor_surface_name",
                {},
            )
        )

    def test_balcony_rear_floor_closures_map_to_surfaces(self):
        for tier_number in (1, 2):
            curve_name = "Balcony{0:02d}RearFloorClosure".format(
                tier_number
            )
            with self.subTest(curve_name=curve_name):
                self.assertEqual(
                    self.section_floor_surface_name(curve_name),
                    curve_name + "Surface",
                )


class SharedRearWallClosureTests(unittest.TestCase):
    @staticmethod
    def _tier(x_value, z_value):
        return {
            "x_values": [float(x_value)],
            "base_z_values": [float(z_value)],
        }

    def _run(self, stalls_x, aisle_width, balcony_results):
        params = {"aisle_width": float(aisle_width)}
        before = copy.deepcopy(params)
        result = {"x_values": [float(stalls_x)]}
        generated = _execute_rear_floor_slice(
            params,
            result,
            balcony_results,
        )
        self.assertEqual(params, before, "preview mutated source params")
        return generated

    def assertClosure(
        self,
        generated,
        expected_wall_x,
        expected_name,
        expected_start_x,
        expected_z,
    ):
        self.assertAlmostEqual(generated["rear_wall_x"], expected_wall_x)
        self.assertEqual(len(generated["preview_curves"]), 1)
        self.assertEqual(len(generated["bake_curves"]), 1)

        curve, color, name = generated["bake_curves"][0]
        self.assertEqual(name, expected_name)
        self.assertEqual(color, "floor-color")
        self.assertAlmostEqual(curve["start"]["x"], expected_start_x)
        self.assertAlmostEqual(curve["end"]["x"], expected_wall_x)
        self.assertAlmostEqual(curve["start"]["z"], expected_z)
        self.assertAlmostEqual(curve["end"]["z"], expected_z)

        preview_curve, preview_color, preview_width = (
            generated["preview_curves"][0]
        )
        self.assertIs(preview_curve, curve)
        self.assertEqual(preview_color, "floor-color")
        self.assertEqual(preview_width, 3)

    def test_shorter_balcony_one_reaches_balcony_two_rear_wall(self):
        generated = self._run(
            stalls_x=100.0,
            aisle_width=10.0,
            balcony_results=[
                self._tier(70.0, 1700.0),
                self._tier(120.0, 2800.0),
            ],
        )
        self.assertClosure(
            generated,
            expected_wall_x=130.0,
            expected_name="Balcony01RearFloorClosure",
            expected_start_x=80.0,
            expected_z=1700.0,
        )

    def test_shorter_balcony_two_reaches_balcony_one_rear_wall(self):
        generated = self._run(
            stalls_x=100.0,
            aisle_width=10.0,
            balcony_results=[
                self._tier(120.0, 1700.0),
                self._tier(65.0, 2800.0),
            ],
        )
        self.assertClosure(
            generated,
            expected_wall_x=130.0,
            expected_name="Balcony02RearFloorClosure",
            expected_start_x=75.0,
            expected_z=2800.0,
        )

    def test_identical_balcony_rear_edges_need_no_closure(self):
        generated = self._run(
            stalls_x=90.0,
            aisle_width=10.0,
            balcony_results=[
                self._tier(120.0, 1700.0),
                self._tier(120.0, 2800.0),
            ],
        )
        self.assertAlmostEqual(generated["rear_wall_x"], 130.0)
        self.assertEqual(generated["preview_curves"], [])
        self.assertEqual(generated["bake_curves"], [])

    def test_zero_aisle_width_closes_from_last_platform_edge(self):
        generated = self._run(
            stalls_x=100.0,
            aisle_width=0.0,
            balcony_results=[self._tier(60.0, 1700.0), None],
        )
        self.assertClosure(
            generated,
            expected_wall_x=100.0,
            expected_name="Balcony01RearFloorClosure",
            expected_start_x=60.0,
            expected_z=1700.0,
        )


class RadialChordToArcSurfaceTests(unittest.TestCase):
    def _fixture(self, join_result="valid", planar_result="valid"):
        calls = {
            "points": [],
            "arcs": [],
            "sides": [],
            "joins": [],
            "planars": [],
        }
        joined_curve = SimpleNamespace(IsClosed=True)
        valid_brep = SimpleNamespace(IsValid=True)

        def radial_point(context, radius, angle, z_value, mm_scale):
            point = (
                "point",
                float(radius),
                float(angle),
                float(z_value),
                float(mm_scale),
            )
            calls["points"].append((context, point))
            return point

        def build_radial_arc(context, radius, z_value, mm_scale):
            arc = (
                "arc",
                float(radius),
                float(z_value),
                float(mm_scale),
            )
            calls["arcs"].append((context, arc))
            return arc

        def build_radial_side_line(
            context,
            start_radius,
            end_radius,
            angle,
            start_z,
            end_z,
            mm_scale,
        ):
            side = (
                "side",
                float(start_radius),
                float(end_radius),
                float(angle),
                float(start_z),
                float(end_z),
                float(mm_scale),
            )
            calls["sides"].append((context, side))
            return side

        class FakeCurveApi:
            @staticmethod
            def JoinCurves(boundaries, tolerance):
                calls["joins"].append((list(boundaries), tolerance))
                if join_result == "raise":
                    raise RuntimeError("join failed")
                if join_result == "empty":
                    return []
                if join_result == "open":
                    return [SimpleNamespace(IsClosed=False)]
                return [joined_curve]

        class FakeBrepApi:
            @staticmethod
            def CreatePlanarBreps(curve, tolerance):
                calls["planars"].append((curve, tolerance))
                if planar_result == "raise":
                    raise RuntimeError("planar failed")
                if planar_result == "empty":
                    return []
                if planar_result == "invalid":
                    return [SimpleNamespace(IsValid=False)]
                return [valid_brep]

        def line_curve(start, end):
            return ("chord", start, end)

        rg = SimpleNamespace(
            Curve=FakeCurveApi,
            Brep=FakeBrepApi,
            LineCurve=line_curve,
        )
        function = _load_selected_function(
            FLOOR_SURFACE_GEOMETRY_PATH,
            "build_radial_chord_to_arc_surface",
            {
                "rg": rg,
                "radial_point": radial_point,
                "build_radial_arc": build_radial_arc,
                "build_radial_side_line": build_radial_side_line,
            },
        )
        return function, calls, joined_curve, valid_brep

    @staticmethod
    def _context():
        return {"mode": "radial", "radius": 100.0, "half_angle": 0.5}

    def test_outer_radius_builds_four_ordered_boundaries(self):
        function, calls, joined_curve, valid_brep = self._fixture()
        result = function(self._context(), 160.0, 30.0, 2.0, 0.01)

        self.assertIs(result, valid_brep)
        boundaries, tolerance = calls["joins"][0]
        self.assertEqual(
            [boundary[0] for boundary in boundaries],
            ["side", "arc", "side", "chord"],
        )
        self.assertEqual(
            [entry[1][1:4] for entry in calls["sides"]],
            [(100.0, 160.0, -0.5), (160.0, 100.0, 0.5)],
        )
        self.assertEqual(boundaries[-1][1][2], 0.5)
        self.assertEqual(boundaries[-1][2][2], -0.5)
        self.assertEqual(tolerance, 0.01)
        self.assertEqual(calls["planars"], [(joined_curve, 0.01)])

    def test_equal_radii_build_arc_and_chord_only(self):
        function, calls, _joined_curve, valid_brep = self._fixture()
        result = function(self._context(), 100.0, 30.0, 2.0, 0.01)

        self.assertIs(result, valid_brep)
        boundaries, _tolerance = calls["joins"][0]
        self.assertEqual(
            [boundary[0] for boundary in boundaries],
            ["arc", "chord"],
        )
        self.assertEqual(calls["sides"], [])

    def test_join_failure_returns_none_without_planar_attempt(self):
        for failure_mode in ("raise", "empty", "open"):
            with self.subTest(failure_mode=failure_mode):
                function, calls, _joined_curve, _valid_brep = self._fixture(
                    join_result=failure_mode
                )
                self.assertIsNone(
                    function(
                        self._context(),
                        160.0,
                        30.0,
                        2.0,
                        0.01,
                    )
                )
                self.assertEqual(calls["planars"], [])

    def test_planar_failure_returns_none(self):
        for failure_mode in ("raise", "empty", "invalid"):
            with self.subTest(failure_mode=failure_mode):
                function, _calls, _joined_curve, _valid_brep = self._fixture(
                    planar_result=failure_mode
                )
                self.assertIsNone(
                    function(
                        self._context(),
                        160.0,
                        30.0,
                        2.0,
                        0.01,
                    )
                )


class RadialFloorBuilderStructureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.function = _function_node(
            FLOOR_SURFACE_GEOMETRY_PATH,
            "build_floor_surface_geometry",
        )

    @staticmethod
    def _assigned_call(function, target_name, function_name):
        for node in ast.walk(function):
            if _assignment_name(node) != target_name:
                continue
            if (
                isinstance(node.value, ast.Call)
                and isinstance(node.value.func, ast.Name)
                and node.value.func.id == function_name
            ):
                return node.value
        raise AssertionError(
            "No {0} assignment calling {1}.".format(
                target_name,
                function_name,
            )
        )

    def test_radial_stage_and_ceiling_use_chord_to_arc_surfaces(self):
        stage_call = self._assigned_call(
            self.function,
            "stage_apron_brep",
            "build_radial_chord_to_arc_surface",
        )
        ceiling_call = self._assigned_call(
            self.function,
            "ceiling_brep",
            "build_radial_chord_to_arc_surface",
        )

        self.assertEqual(ast.unparse(stage_call.args[0]), "layout_context")
        self.assertEqual(
            ast.unparse(stage_call.args[1]),
            "layout_context['radius'] + max(float(params['stage_apron_projection']), 0.0)",
        )
        self.assertEqual(ast.unparse(stage_call.args[2]), "0.0")
        self.assertEqual(ast.unparse(ceiling_call.args[0]), "layout_context")
        self.assertEqual(
            ast.unparse(ceiling_call.args[1]),
            "layout_context['radius'] + rear_wall_x",
        )
        self.assertEqual(
            ast.unparse(ceiling_call.args[2]),
            "section_dimensions['auditorium_ceiling_z']",
        )

    def test_successful_planar_surfaces_skip_legacy_radial_sweeps(self):
        continue_conditions = [
            ast.unparse(node.test)
            for node in ast.walk(self.function)
            if isinstance(node, ast.If)
            and any(isinstance(item, ast.Continue) for item in node.body)
        ]
        self.assertTrue(
            any(
                "curve_name == 'StageApronSection'" in condition
                and "stage_apron_brep is not None" in condition
                for condition in continue_conditions
            )
        )
        self.assertTrue(
            any(
                "curve_name == 'AuditoriumCeilingSection'" in condition
                and "ceiling_brep is not None" in condition
                for condition in continue_conditions
            )
        )

        appended_names = []
        for node in ast.walk(self.function):
            if not isinstance(node, ast.Call):
                continue
            if not (
                isinstance(node.func, ast.Name)
                and node.func.id == "append_floor_surface"
            ):
                continue
            for argument in node.args:
                if isinstance(argument, ast.Constant):
                    appended_names.append(argument.value)
        self.assertIn("StageApronSurface", appended_names)
        self.assertIn("AuditoriumCeilingSurface", appended_names)


if __name__ == "__main__":
    unittest.main()
