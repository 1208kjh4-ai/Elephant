# -*- coding: utf-8 -*-
"""Rhino-free integration regressions for custom-boundary preview wiring.

The preview builder itself imports RhinoCommon.  These tests exercise the
small boundary/data-flow slice directly from its AST and use structural
checks for the geometry calls that cannot run in ordinary CPython.
"""

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
MAIN_DIALOG_PATH = (
    ROOT
    / "commands"
    / "auditorium_generator"
    / "main_dialog.py"
)


def _preview_function():
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


def _assignment_name(node):
    if not isinstance(node, ast.Assign) or len(node.targets) != 1:
        return None
    target = node.targets[0]
    return target.id if isinstance(target, ast.Name) else None


def _call_name(node):
    if not isinstance(node, ast.Call):
        return None
    if isinstance(node.func, ast.Name):
        return node.func.id
    if isinstance(node.func, ast.Attribute):
        return node.func.attr
    return None


def _calls(node, name):
    return [
        child
        for child in ast.walk(node)
        if isinstance(child, ast.Call) and _call_name(child) == name
    ]


def _contains_name(node, name):
    return any(
        isinstance(child, ast.Name) and child.id == name
        for child in ast.walk(node)
    )


def _contains_constant(node, value):
    return any(
        isinstance(child, ast.Constant) and child.value == value
        for child in ast.walk(node)
    )


def _is_none_check(test, name, operator_type):
    return (
        isinstance(test, ast.Compare)
        and isinstance(test.left, ast.Name)
        and test.left.id == name
        and len(test.ops) == 1
        and isinstance(test.ops[0], operator_type)
        and len(test.comparators) == 1
        and isinstance(test.comparators[0], ast.Constant)
        and test.comparators[0].value is None
    )


def _wiring_statements():
    """Extract the exact context/row-region statements from production."""
    function = _preview_function()
    assignments = {
        _assignment_name(node): node
        for node in function.body
        if _assignment_name(node) in {
            "boundary_context",
            "boundary_tier_row_regions",
            "tier_row_intervals",
        }
    }
    missing = {
        "boundary_context",
        "boundary_tier_row_regions",
        "tier_row_intervals",
    } - set(assignments)
    if missing:
        raise AssertionError(
            "Boundary wiring assignments are missing: {0}".format(
                sorted(missing)
            )
        )

    region_if = None
    for node in function.body:
        if (
            isinstance(node, ast.If)
            and _is_none_check(
                node.test,
                "boundary_context",
                ast.IsNot,
            )
            and _calls(node, "build_tier_row_regions")
            and _contains_name(node, "tier_row_intervals")
        ):
            region_if = node
            break
    if region_if is None:
        raise AssertionError("Boundary row-region branch was not found.")

    return [
        copy.deepcopy(assignments["boundary_context"]),
        copy.deepcopy(assignments["boundary_tier_row_regions"]),
        copy.deepcopy(assignments["tier_row_intervals"]),
        copy.deepcopy(region_if),
    ]


def _execute_boundary_wiring(
    boundary_curve,
    balcony_2_displayable=False,
):
    context_calls = []
    row_calls = []
    context = {"id": "boundary-context"}
    stalls = {"name": "stalls", "displayable": True}
    balcony_1 = {"name": "balcony-1", "displayable": True}
    balcony_2 = {
        "name": "balcony-2",
        "displayable": balcony_2_displayable,
    }

    def build_boundary_context(curve, datum, tolerance):
        context_calls.append((curve, datum, tolerance))
        return context if curve is not None else None

    def build_tier_row_regions(
        received_context,
        layout,
        tier,
        scale,
        footprint_depth_mm=0.0,
    ):
        row_calls.append((
            received_context,
            layout,
            tier,
            scale,
            footprint_depth_mm,
        ))
        tag = tier["name"]
        return [{
            "segments": ["{0}-clipped-segment".format(tag)],
            "intervals": [("{0}-left".format(tag), "right")],
        }]

    datum = object()
    layout = object()
    module = ast.Module(
        body=_wiring_statements(),
        type_ignores=[],
    )
    ast.fix_missing_locations(module)
    namespace = {
        "stage_data": (
            {"auditorium_boundary_curve": boundary_curve}
            if boundary_curve is not None
            else {}
        ),
        "audience_datum_point": datum,
        "doc": SimpleNamespace(ModelAbsoluteTolerance=0.025),
        "build_boundary_context": build_boundary_context,
        "build_tier_row_regions": build_tier_row_regions,
        "boundary_context": "uninitialized",
        "layout_context": layout,
        "result": stalls,
        "balcony_results": [balcony_1, balcony_2],
        "balcony_tier_params": [
            {"balcony_row_pitch": 900.0},
            {"balcony_row_pitch": 1000.0},
        ],
        "balcony_result_is_displayable": (
            lambda tier: bool(tier and tier["displayable"])
        ),
        "mm_scale": 0.001,
        "params": {"row_pitch": 1100.0},
    }
    exec(
        compile(module, str(PREVIEW_GEOMETRY_PATH), "exec"),
        namespace,
    )
    namespace["_context_calls"] = context_calls
    namespace["_row_calls"] = row_calls
    namespace["_context_sentinel"] = context
    namespace["_datum_sentinel"] = datum
    namespace["_layout_sentinel"] = layout
    return namespace


def _return_mapping():
    returns = [
        node
        for node in ast.walk(_preview_function())
        if isinstance(node, ast.Return)
    ]
    dictionary_returns = [
        node.value
        for node in returns
        if isinstance(node.value, ast.Dict)
    ]
    if len(dictionary_returns) != 1:
        raise AssertionError(
            "Expected one dictionary return from build_preview_geometry."
        )
    result = dictionary_returns[0]
    return {
        key.value: value
        for key, value in zip(result.keys, result.values)
        if isinstance(key, ast.Constant)
    }


class BoundaryPreviewDataFlowTests(unittest.TestCase):
    def test_selected_boundary_builds_context_and_displayable_tier_rows(self):
        source_curve = object()
        executed = _execute_boundary_wiring(source_curve)

        self.assertEqual(1, len(executed["_context_calls"]))
        curve, datum, tolerance = executed["_context_calls"][0]
        self.assertIs(source_curve, curve)
        self.assertIs(executed["_datum_sentinel"], datum)
        self.assertEqual(0.025, tolerance)
        self.assertIs(
            executed["_context_sentinel"],
            executed["boundary_context"],
        )

        row_calls = executed["_row_calls"]
        self.assertEqual(2, len(row_calls))
        self.assertEqual(
            ["stalls", "balcony-1"],
            [call[2]["name"] for call in row_calls],
        )
        self.assertTrue(all(
            call[0] is executed["_context_sentinel"]
            and call[1] is executed["_layout_sentinel"]
            and call[3] == 0.001
            for call in row_calls
        ))
        self.assertEqual(
            [1100.0, 900.0],
            [call[4] for call in row_calls],
        )
        self.assertEqual(3, len(executed["boundary_tier_row_regions"]))
        self.assertIsNone(executed["boundary_tier_row_regions"][2])
        self.assertEqual(
            [
                [[("stalls-left", "right")]],
                [[("balcony-1-left", "right")]],
                None,
            ],
            executed["tier_row_intervals"],
        )

    def test_no_boundary_keeps_old_none_arguments_available(self):
        executed = _execute_boundary_wiring(None)

        self.assertEqual(1, len(executed["_context_calls"]))
        curve, datum, tolerance = executed["_context_calls"][0]
        self.assertIsNone(curve)
        self.assertIs(executed["_datum_sentinel"], datum)
        self.assertEqual(0.025, tolerance)
        self.assertIsNone(executed["boundary_context"])
        self.assertIsNone(executed["boundary_tier_row_regions"])
        self.assertIsNone(executed["tier_row_intervals"])
        self.assertEqual([], executed["_row_calls"])

    def test_each_balcony_uses_its_own_row_pitch_for_footprint(self):
        executed = _execute_boundary_wiring(
            object(),
            balcony_2_displayable=True,
        )

        self.assertEqual(
            ["stalls", "balcony-1", "balcony-2"],
            [call[2]["name"] for call in executed["_row_calls"]],
        )
        self.assertEqual(
            [1100.0, 900.0, 1000.0],
            [call[4] for call in executed["_row_calls"]],
        )


class BoundaryPreviewCallWiringTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.function = _preview_function()

    def test_actual_count_and_3d_seats_share_tier_intervals(self):
        total_calls = _calls(
            self.function,
            "calculate_total_3d_seat_count",
        )
        self.assertEqual(2, len(total_calls))
        custom_total_calls = [
            call for call in total_calls if len(call.args) == 5
        ]
        self.assertEqual(1, len(custom_total_calls))
        self.assertIsInstance(custom_total_calls[0].args[-1], ast.Name)
        self.assertEqual(
            "tier_row_intervals",
            custom_total_calls[0].args[-1].id,
        )

        seat_calls = _calls(
            self.function,
            "build_3d_seat_module_geometry",
        )
        self.assertEqual(2, len(seat_calls))
        custom_seat_calls = [
            call
            for call in seat_calls
            if _contains_name(call, "tier_row_intervals")
        ]
        self.assertEqual(1, len(custom_seat_calls))
        self.assertTrue(
            _contains_name(custom_seat_calls[0], "tier_slot")
        )

    def test_radial_guides_use_clipped_segments(self):
        matching_branches = []
        for node in ast.walk(self.function):
            if not (
                isinstance(node, ast.If)
                and _is_none_check(
                    node.test,
                    "boundary_tier_row_regions",
                    ast.IsNot,
                )
            ):
                continue
            body_module = ast.Module(body=node.body, type_ignores=[])
            else_module = ast.Module(body=node.orelse, type_ignores=[])
            if (
                _contains_constant(body_module, "segments")
                and _contains_name(body_module, "boundary_tier_row_regions")
                and _calls(body_module, "DuplicateCurve")
                and _calls(else_module, "build_radial_arc")
            ):
                matching_branches.append(node)

        self.assertEqual(1, len(matching_branches))
        branch = matching_branches[0]
        clipped_loops = [
            node
            for node in ast.walk(ast.Module(
                body=branch.body,
                type_ignores=[],
            ))
            if (
                isinstance(node, ast.For)
                and _contains_name(node.iter, "boundary_tier_row_regions")
                and _contains_constant(node.iter, "segments")
            )
        ]
        self.assertEqual(1, len(clipped_loops))
        self.assertTrue(_calls(clipped_loops[0], "Transform"))

    def test_custom_boundary_suppresses_legacy_radial_side_lines(self):
        parents = {}
        for parent in ast.walk(self.function):
            for child in ast.iter_child_nodes(parent):
                parents[child] = parent

        side_calls = _calls(self.function, "build_radial_side_line")
        self.assertEqual(1, len(side_calls))
        ancestors = []
        current = side_calls[0]
        while current in parents:
            current = parents[current]
            ancestors.append(current)
        self.assertTrue(any(
            isinstance(node, ast.If)
            and _is_none_check(
                node.test,
                "boundary_context",
                ast.Is,
            )
            for node in ancestors
        ))

    def test_floor_builder_receives_boundary_context(self):
        floor_calls = _calls(
            self.function,
            "build_floor_surface_geometry",
        )
        self.assertEqual(2, len(floor_calls))
        custom_floor_calls = [
            call
            for call in floor_calls
            if _contains_name(call, "boundary_context")
        ]
        self.assertEqual(1, len(custom_floor_calls))

    def test_return_exposes_boundary_context_and_row_regions(self):
        returned = _return_mapping()
        expected = {
            "auditorium_boundary": "boundary_context",
            "boundary_tier_row_regions": "boundary_tier_row_regions",
        }
        for key, variable_name in expected.items():
            with self.subTest(key=key):
                self.assertIn(key, returned)
                self.assertIsInstance(returned[key], ast.Name)
                self.assertEqual(variable_name, returned[key].id)


class BoundaryMainDialogValidationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        tree = ast.parse(
            MAIN_DIALOG_PATH.read_text(encoding="utf-8"),
            str(MAIN_DIALOG_PATH),
        )
        dialog_class = next(
            node
            for node in tree.body
            if (
                isinstance(node, ast.ClassDef)
                and node.name == "AuditoriumDialog"
            )
        )
        cls.read_params = next(
            node
            for node in dialog_class.body
            if (
                isinstance(node, ast.FunctionDef)
                and node.name == "read_params"
            )
        )

    def test_custom_boundary_allows_rectangular_auto_blocks(self):
        automatic_checks = [
            node
            for node in ast.walk(self.read_params)
            if (
                isinstance(node, ast.If)
                and _calls(node.test, "seat_blocks_have_auto")
            )
        ]
        self.assertTrue(any(
            _contains_constant(node.test, "auditorium_boundary_curve")
            for node in automatic_checks
        ))

    def test_custom_boundary_defers_fixed_preview_limit_to_actual_count(self):
        limit_checks = [
            node
            for node in ast.walk(self.read_params)
            if (
                isinstance(node, ast.If)
                and _contains_name(node.test, "MAXIMUM_3D_CHAIR_COUNT")
            )
        ]
        self.assertTrue(any(
            _contains_constant(node.test, "auditorium_boundary_curve")
            for node in limit_checks
        ))


if __name__ == "__main__":
    unittest.main()
