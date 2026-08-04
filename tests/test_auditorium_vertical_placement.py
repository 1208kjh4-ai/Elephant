# -*- coding: utf-8 -*-
"""Rhino-free tests for absolute stalls-rear vertical placement."""

import ast
import math
import unittest
from pathlib import Path

from commands.auditorium_generator.vertical_placement import (
    calculate_vertical_placement,
)


ROOT = Path(__file__).resolve().parents[1]
PACKAGE_ROOT = ROOT / "commands" / "auditorium_generator"
MAIN_DIALOG_PATH = PACKAGE_ROOT / "main_dialog.py"
PREVIEW_GEOMETRY_PATH = PACKAGE_ROOT / "preview_geometry.py"


def _parse(path):
    return ast.parse(path.read_text(encoding="utf-8"), str(path))


def _function(tree, name):
    return next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == name
    )


def _method(tree, class_name, method_name):
    class_node = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == class_name
    )
    return next(
        node
        for node in class_node.body
        if isinstance(node, ast.FunctionDef) and node.name == method_name
    )


def _called_name(call):
    if isinstance(call.func, ast.Name):
        return call.func.id
    if isinstance(call.func, ast.Attribute):
        return call.func.attr
    return None


class VerticalPlacementTests(unittest.TestCase):
    def assert_close(self, actual, expected):
        self.assertTrue(
            math.isclose(float(actual), float(expected), abs_tol=1e-9),
            "{0!r} != {1!r}".format(actual, expected),
        )

    def test_none_target_preserves_existing_datum(self):
        placement = calculate_vertical_placement(
            datum_z_model_units=1000.0,
            mm_scale=1.0,
            stage_height_mm=1100.0,
            stalls_rear_local_z_mm=2780.0,
            target_world_z_mm=None,
        )

        self.assertFalse(placement["override_applied"])
        self.assert_close(placement["unshifted_rear_world_z_mm"], 4880.0)
        self.assert_close(placement["vertical_offset_mm"], 0.0)
        self.assert_close(placement["vertical_offset_model_units"], 0.0)
        self.assert_close(placement["placed_datum_z_model_units"], 1000.0)
        self.assert_close(placement["actual_rear_world_z_mm"], 4880.0)

    def test_target_moves_whole_datum_to_exact_rear_world_z(self):
        placement = calculate_vertical_placement(
            datum_z_model_units=1000.0,
            mm_scale=1.0,
            stage_height_mm=1100.0,
            stalls_rear_local_z_mm=2780.0,
            target_world_z_mm=12000.0,
        )

        self.assertTrue(placement["override_applied"])
        self.assert_close(placement["vertical_offset_mm"], 7120.0)
        self.assert_close(placement["placed_datum_z_model_units"], 8120.0)
        self.assert_close(placement["actual_rear_world_z_mm"], 12000.0)

    def test_model_unit_scale_is_applied_in_both_directions(self):
        # In a metre model, one millimetre is 0.001 model units.
        placement = calculate_vertical_placement(
            datum_z_model_units=2.5,
            mm_scale=0.001,
            stage_height_mm=1100.0,
            stalls_rear_local_z_mm=2780.0,
            target_world_z_mm=12000.0,
        )

        self.assert_close(placement["unshifted_rear_world_z_mm"], 6380.0)
        self.assert_close(placement["vertical_offset_mm"], 5620.0)
        self.assert_close(placement["vertical_offset_model_units"], 5.62)
        self.assert_close(placement["placed_datum_z_model_units"], 8.12)
        self.assert_close(placement["actual_rear_world_z_mm"], 12000.0)

    def test_zero_and_negative_world_targets_are_valid_elevations(self):
        zero = calculate_vertical_placement(
            1.0,
            1.0,
            1100.0,
            -100.0,
            0.0,
        )
        negative = calculate_vertical_placement(
            1.0,
            1.0,
            1100.0,
            -100.0,
            -2500.0,
        )

        self.assert_close(zero["actual_rear_world_z_mm"], 0.0)
        self.assert_close(negative["actual_rear_world_z_mm"], -2500.0)

    def test_invalid_scale_and_non_finite_inputs_are_rejected(self):
        invalid_calls = (
            (0.0, 0.0, 1100.0, 2780.0, None),
            (0.0, -1.0, 1100.0, 2780.0, None),
            (float("nan"), 1.0, 1100.0, 2780.0, None),
            (0.0, 1.0, float("inf"), 2780.0, None),
            (0.0, 1.0, 1100.0, float("nan"), None),
            (0.0, 1.0, 1100.0, 2780.0, float("inf")),
        )
        for arguments in invalid_calls:
            with self.subTest(arguments=arguments):
                with self.assertRaises(ValueError):
                    calculate_vertical_placement(*arguments)


class VerticalPlacementWiringTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.main_tree = _parse(MAIN_DIALOG_PATH)
        cls.preview_tree = _parse(PREVIEW_GEOMETRY_PATH)

    def test_preview_uses_effective_stalls_rear_and_main_target(self):
        preview = _function(
            self.preview_tree,
            "build_preview_geometry",
        )
        placement_call = next(
            node
            for node in ast.walk(preview)
            if isinstance(node, ast.Call)
            and _called_name(node) == "calculate_vertical_placement"
        )
        self.assertEqual(5, len(placement_call.args))
        self.assertTrue(
            any(
                isinstance(node, ast.Name)
                and node.id == "effective_stalls_rear_z"
                for node in ast.walk(placement_call.args[3])
            )
        )
        self.assertTrue(
            any(
                isinstance(node, ast.Constant)
                and node.value == "stalls_rear_world_z"
                for node in ast.walk(placement_call.args[4])
            )
        )

        returned = next(
            node
            for node in preview.body
            if isinstance(node, ast.Return)
        )
        return_keys = {
            key.value
            for key in returned.value.keys
            if isinstance(key, ast.Constant)
        }
        self.assertIn("vertical_placement", return_keys)

    def test_main_dialog_supports_blank_numeric_and_picked_world_z(self):
        init_method = _method(
            self.main_tree,
            "AuditoriumDialog",
            "__init__",
        )
        read_params = _method(
            self.main_tree,
            "AuditoriumDialog",
            "read_params",
        )
        picker = _method(
            self.main_tree,
            "AuditoriumDialog",
            "pick_stalls_rear_world_z",
        )
        push_picker = _method(
            self.main_tree,
            "AuditoriumDialog",
            "on_pick_stalls_rear_world_z",
        )

        self.assertTrue(
            any(
                isinstance(node, ast.Constant)
                and node.value == "stalls_rear_world_z"
                for node in ast.walk(init_method)
            )
        )
        self.assertTrue(
            any(
                isinstance(node, ast.Call)
                and _called_name(node) == "parse_optional_float"
                for node in ast.walk(read_params)
            )
        )
        self.assertTrue(
            any(
                isinstance(node, ast.Call)
                and _called_name(node) == "GetPoint"
                for node in ast.walk(picker)
            )
        )
        self.assertTrue(
            any(
                isinstance(node, ast.Call)
                and _called_name(node) == "PushPickButton"
                for node in ast.walk(push_picker)
            )
        )


if __name__ == "__main__":
    unittest.main()
