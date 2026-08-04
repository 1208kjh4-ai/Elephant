# -*- coding: utf-8 -*-
"""Regression tests for the main-dialog auditorium ceiling input."""

import ast
import unittest
from pathlib import Path

from commands.auditorium_generator.calculations.sections import (
    calculate_auditorium_ceiling,
)


ROOT = Path(__file__).resolve().parents[1]
MAIN_DIALOG_PATH = (
    ROOT
    / "commands"
    / "auditorium_generator"
    / "main_dialog.py"
)
PREVIEW_GEOMETRY_PATH = (
    ROOT
    / "commands"
    / "auditorium_generator"
    / "preview_geometry.py"
)
CEILING_CLEAR_HEIGHT_KEY = "auditorium_ceiling_clear_height"


def _parse(path):
    return ast.parse(
        path.read_text(encoding="utf-8-sig"),
        filename=str(path),
    )


def _class_method(tree, class_name, method_name):
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


def _assigned_dict_value(tree, assignment_name, key):
    assignment = next(
        node
        for node in tree.body
        if isinstance(node, ast.Assign)
        and any(
            isinstance(target, ast.Name)
            and target.id == assignment_name
            for target in node.targets
        )
    )
    if not isinstance(assignment.value, ast.Dict):
        raise AssertionError(
            "{0} must be a dictionary literal.".format(assignment_name)
        )
    for key_node, value_node in zip(
        assignment.value.keys,
        assignment.value.values,
    ):
        if (
            isinstance(key_node, ast.Constant)
            and key_node.value == key
        ):
            return ast.literal_eval(value_node)
    raise AssertionError(
        "{0!r} is missing from {1}.".format(key, assignment_name)
    )


def _string_constants(node):
    return {
        child.value
        for child in ast.walk(node)
        if isinstance(child, ast.Constant)
        and isinstance(child.value, str)
    }


def _attribute_names(node):
    return {
        child.attr
        for child in ast.walk(node)
        if isinstance(child, ast.Attribute)
    }


def _called_function_name(call):
    if isinstance(call.func, ast.Name):
        return call.func.id
    if isinstance(call.func, ast.Attribute):
        return call.func.attr
    return None


class CeilingMainInputStructureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.main_tree = _parse(MAIN_DIALOG_PATH)
        cls.preview_tree = _parse(PREVIEW_GEOMETRY_PATH)

    def test_default_clear_height_is_5000_mm(self):
        self.assertEqual(
            _assigned_dict_value(
                self.main_tree,
                "DEFAULTS",
                CEILING_CLEAR_HEIGHT_KEY,
            ),
            5000.0,
        )

    def test_defaults_schema_version_is_bumped_for_new_sticky_value(self):
        version = next(
            ast.literal_eval(node.value)
            for node in self.main_tree.body
            if isinstance(node, ast.Assign)
            and any(
                isinstance(target, ast.Name)
                and target.id == "AUDITORIUM_DEFAULTS_VERSION"
                for target in node.targets
            )
        )
        self.assertGreaterEqual(version, 10)

    def test_main_dialog_owns_ceiling_text_box_and_read_param(self):
        init_method = _class_method(
            self.main_tree,
            "AuditoriumDialog",
            "__init__",
        )
        read_params = _class_method(
            self.main_tree,
            "AuditoriumDialog",
            "read_params",
        )
        all_text_boxes = _class_method(
            self.main_tree,
            "AuditoriumDialog",
            "all_text_boxes",
        )

        self.assertIn(CEILING_CLEAR_HEIGHT_KEY, _string_constants(init_method))
        self.assertIn(CEILING_CLEAR_HEIGHT_KEY, _string_constants(read_params))
        self.assertIn(
            "auditorium_ceiling_clear_height_box",
            _attribute_names(all_text_boxes),
        )

    def test_read_params_value_is_persisted_by_main_ok_flow(self):
        read_params = _class_method(
            self.main_tree,
            "AuditoriumDialog",
            "read_params",
        )
        on_ok = _class_method(
            self.main_tree,
            "AuditoriumDialog",
            "on_ok",
        )

        self.assertIn(CEILING_CLEAR_HEIGHT_KEY, _string_constants(read_params))
        self.assertIn("STICKY_KEY", {
            node.id
            for node in ast.walk(on_ok)
            if isinstance(node, ast.Name)
        })
        self.assertTrue(
            any(
                isinstance(node, ast.Call)
                and _called_function_name(node) == "dict"
                and any(
                    isinstance(arg, ast.Name) and arg.id == "params"
                    for arg in node.args
                )
                for node in ast.walk(on_ok)
            ),
            "on_ok must persist the full params dictionary.",
        )

    def test_section_dimension_control_no_longer_adds_ceiling_row(self):
        section_rows = _class_method(
            self.main_tree,
            "AuditoriumDialog",
            "section_interpolation_rows",
        )
        self.assertNotIn("ceiling", _string_constants(section_rows))
        self.assertNotIn(
            "ceiling_clear_height",
            _string_constants(section_rows),
        )

    def test_preview_uses_main_param_as_ceiling_clear_height_target(self):
        preview_builder = next(
            node
            for node in self.preview_tree.body
            if isinstance(node, ast.FunctionDef)
            and node.name == "build_preview_geometry"
        )
        ceiling_call = next(
            node
            for node in ast.walk(preview_builder)
            if isinstance(node, ast.Call)
            and _called_function_name(node) == "calculate_auditorium_ceiling"
        )
        supplied_arguments = list(ceiling_call.args) + [
            keyword.value for keyword in ceiling_call.keywords
        ]
        self.assertTrue(
            any(
                CEILING_CLEAR_HEIGHT_KEY in _string_constants(argument)
                for argument in supplied_arguments
            ),
            "The ceiling calculator must receive the main-dialog clear-height "
            "parameter, not a transient Section Dimension Control override.",
        )


class CeilingClearHeightCalculationTests(unittest.TestCase):
    @staticmethod
    def tier(*base_z_values):
        return {"base_z_values": list(base_z_values)}

    def test_5000_is_added_to_stalls_actual_rear_platform(self):
        result = calculate_auditorium_ceiling(
            6000.0,
            self.tier(0.0, 3880.0),
            [None, None],
            5000.0,
        )

        self.assertEqual(result["reference_tier_key"], "stalls")
        self.assertAlmostEqual(result["reference_platform_z"], 3880.0)
        self.assertAlmostEqual(result["actual_clear_height"], 5000.0)
        self.assertAlmostEqual(result["ceiling_z"], 8880.0)

    def test_5000_follows_the_last_active_balcony_rear_platform(self):
        result = calculate_auditorium_ceiling(
            6000.0,
            self.tier(0.0, 3880.0),
            [
                self.tier(5000.0, 7200.0),
                self.tier(10000.0, 12400.0),
            ],
            5000.0,
        )

        self.assertEqual(result["reference_tier_key"], "balcony_2")
        self.assertAlmostEqual(result["reference_platform_z"], 12400.0)
        self.assertAlmostEqual(result["actual_clear_height"], 5000.0)
        self.assertAlmostEqual(result["ceiling_z"], 17400.0)

    def test_rear_platform_edit_moves_ceiling_by_the_same_delta(self):
        before = calculate_auditorium_ceiling(
            6000.0,
            self.tier(0.0, 3800.0),
            [None, None],
            5000.0,
        )
        after = calculate_auditorium_ceiling(
            6000.0,
            self.tier(0.0, 4250.0),
            [None, None],
            5000.0,
        )

        self.assertAlmostEqual(
            after["ceiling_z"] - before["ceiling_z"],
            450.0,
        )
        self.assertAlmostEqual(before["actual_clear_height"], 5000.0)
        self.assertAlmostEqual(after["actual_clear_height"], 5000.0)

    def test_opening_top_remains_a_hard_minimum(self):
        result = calculate_auditorium_ceiling(
            6000.0,
            self.tier(0.0, 500.0),
            [None, None],
            5000.0,
        )

        self.assertAlmostEqual(result["requested_clear_height"], 5000.0)
        self.assertAlmostEqual(result["actual_clear_height"], 5500.0)
        self.assertAlmostEqual(result["ceiling_z"], 6000.0)
        self.assertTrue(result["clamped_to_opening_top"])


if __name__ == "__main__":
    unittest.main()
