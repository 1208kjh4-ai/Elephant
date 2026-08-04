# -*- coding: utf-8 -*-
"""Rhino-free regression tests for main-dialog section quick actions."""

import ast
import copy
import math
import types
import unittest
from pathlib import Path

from commands.auditorium_generator.section_interpolation_constants import (
    SEATING_RISE_KEYS,
    SECTION_RISE_KEYS,
)


ROOT = Path(__file__).resolve().parents[1]
MAIN_DIALOG_PATH = (
    ROOT
    / "commands"
    / "auditorium_generator"
    / "main_dialog.py"
)
SECTION_DIALOG_PATH = (
    ROOT
    / "commands"
    / "auditorium_generator"
    / "section_result_dialogs.py"
)


def _parse(path):
    return ast.parse(
        path.read_text(encoding="utf-8-sig"),
        filename=str(path),
    )


def _class_node(path, class_name):
    return next(
        node
        for node in _parse(path).body
        if isinstance(node, ast.ClassDef) and node.name == class_name
    )


def _expression_text(node):
    return ast.unparse(node)


def _button_contract(class_node, button_text):
    init_node = next(
        node
        for node in class_node.body
        if isinstance(node, ast.FunctionDef) and node.name == "__init__"
    )
    control_expression = None
    for node in ast.walk(init_node):
        if (
            isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Attribute)
            and node.targets[0].attr == "Text"
            and isinstance(node.value, ast.Constant)
            and node.value.value == button_text
        ):
            control_expression = _expression_text(node.targets[0].value)
            break
    if control_expression is None:
        raise AssertionError(
            "Main dialog is missing the {0!r} quick-action button.".format(
                button_text
            )
        )

    handler_name = None
    for node in ast.walk(init_node):
        if (
            isinstance(node, ast.AugAssign)
            and isinstance(node.op, ast.Add)
            and isinstance(node.target, ast.Attribute)
            and node.target.attr == "Click"
            and _expression_text(node.target.value) == control_expression
            and isinstance(node.value, ast.Attribute)
            and isinstance(node.value.value, ast.Name)
            and node.value.value.id == "self"
        ):
            handler_name = node.value.attr
            break
    if handler_name is None:
        raise AssertionError(
            "The {0!r} quick-action button has no self handler.".format(
                button_text
            )
        )
    return control_expression, handler_name


def _load_class(path, class_name, globals_dict=None):
    class_node = copy.deepcopy(_class_node(path, class_name))
    class_node.bases = [ast.Name(id="object", ctx=ast.Load())]
    class_node.keywords = []
    module = ast.fix_missing_locations(
        ast.Module(body=[class_node], type_ignores=[])
    )
    namespace = {
        "__builtins__": __builtins__,
        "math": math,
        "SEATING_RISE_KEYS": SEATING_RISE_KEYS,
        "SECTION_RISE_KEYS": SECTION_RISE_KEYS,
    }
    if globals_dict:
        namespace.update(globals_dict)
    exec(compile(module, str(path), "exec"), namespace)
    return namespace[class_name]


def _controls_share_layout_group(class_node, control_expressions):
    init_node = next(
        node
        for node in class_node.body
        if isinstance(node, ast.FunctionDef) and node.name == "__init__"
    )

    for call in (
        node for node in ast.walk(init_node) if isinstance(node, ast.Call)
    ):
        if (
            isinstance(call.func, ast.Attribute)
            and call.func.attr == "AddRow"
        ):
            argument_text = " ".join(
                _expression_text(argument) for argument in call.args
            )
            if all(
                control in argument_text for control in control_expressions
            ):
                return True

    grouped_arguments = {}
    for call in (
        node for node in ast.walk(init_node) if isinstance(node, ast.Call)
    ):
        if not (
            isinstance(call.func, ast.Attribute)
            and call.func.attr == "Add"
            and isinstance(call.func.value, ast.Attribute)
            and call.func.value.attr == "Items"
        ):
            continue
        group = _expression_text(call.func.value.value)
        grouped_arguments.setdefault(group, []).extend(
            _expression_text(argument) for argument in call.args
        )

    add_row_arguments = [
        _expression_text(argument)
        for call in ast.walk(init_node)
        if isinstance(call, ast.Call)
        and isinstance(call.func, ast.Attribute)
        and call.func.attr == "AddRow"
        for argument in call.args
    ]
    for group, argument_texts in grouped_arguments.items():
        joined = " ".join(argument_texts)
        if (
            all(control in joined for control in control_expressions)
            and group in add_row_arguments
        ):
            return True
    return False


class MainSectionQuickActionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.main_node = _class_node(
            MAIN_DIALOG_PATH,
            "AuditoriumDialog",
        )
        cls.dialog_class = _load_class(
            MAIN_DIALOG_PATH,
            "AuditoriumDialog",
        )

    def button_handler(self, text):
        unused_control, handler_name = _button_contract(
            self.main_node,
            text,
        )
        return getattr(self.dialog_class, handler_name)

    def make_dialog(self, rows, overrides):
        dialog = object.__new__(self.dialog_class)
        dialog.section_rise_overrides = dict(overrides)
        dialog.section_solver_signatures = {"stable": True}
        dialog.warning_text = ""
        dialog.section_interpolation_rows = lambda: [
            dict(row) for row in rows
        ]
        preview_snapshots = []

        def update_preview(show_error):
            preview_snapshots.append(
                dict(dialog.section_rise_overrides)
            )
            return True

        dialog.update_preview = update_preview
        return dialog, preview_snapshots

    def test_quick_buttons_share_the_section_control_row(self):
        section_control, unused_handler = _button_contract(
            self.main_node,
            "Section Dimension Control",
        )
        round_up, unused_handler = _button_contract(
            self.main_node,
            "10 mm Up",
        )
        reset, unused_handler = _button_contract(
            self.main_node,
            "Reset",
        )

        self.assertTrue(
            _controls_share_layout_group(
                self.main_node,
                (section_control, round_up, reset),
            ),
            "Section Dimension Control, 10 mm Up, and Reset must share "
            "one main-dialog row.",
        )

    def test_10mm_up_rounds_editable_active_sections_and_previews(self):
        rows = [
            {
                "key": "stalls",
                "current_rise": 123.1,
                "editable": True,
            },
            {
                "key": "balcony_1",
                "current_rise": 240.0,
                "editable": True,
            },
            {
                "key": "balcony_2",
                "current_rise": 80.1,
                "editable": False,
            },
        ]
        initial = {
            "stalls": 123.1,
            "balcony_1": 240.0,
            "balcony_2": 75.0,
        }
        dialog, preview_snapshots = self.make_dialog(rows, initial)

        self.button_handler("10 mm Up")(dialog, None, None)

        expected = {
            "stalls": 130.0,
            "balcony_1": 240.0,
            "balcony_2": 75.0,
        }
        self.assertEqual(dialog.section_rise_overrides, expected)
        self.assertIn(expected, preview_snapshots)

    def test_10mm_up_matches_detailed_dialog_rounding_rule(self):
        rows = [
            {
                "key": "stalls",
                "current_rise": 123.1,
                "editable": True,
            },
            {
                "key": "balcony_1",
                "current_rise": 240.0,
                "editable": True,
            },
        ]
        initial = {
            "stalls": 123.1,
            "balcony_1": 240.0,
            "balcony_2": None,
        }
        dialog, unused_snapshots = self.make_dialog(rows, initial)

        detail_class = _load_class(
            SECTION_DIALOG_PATH,
            "SectionDimensionInterpolationDialog",
        )
        detail = object.__new__(detail_class)
        detail.sections = [dict(row) for row in rows]
        detail.target_boxes = {
            row["key"]: types.SimpleNamespace(
                Text=str(row["current_rise"])
            )
            for row in rows
        }
        detail.set_rounded_targets("up")
        detailed_targets = {
            key: float(box.Text)
            for key, box in detail.target_boxes.items()
        }

        self.button_handler("10 mm Up")(dialog, None, None)

        self.assertEqual(
            {
                key: dialog.section_rise_overrides[key]
                for key in detailed_targets
            },
            detailed_targets,
        )

    def test_reset_clears_every_seating_override_and_previews(self):
        initial = {
            "stalls": 130.0,
            "balcony_1": 240.0,
            "balcony_2": 310.0,
        }
        dialog, preview_snapshots = self.make_dialog([], initial)

        self.button_handler("Reset")(dialog, None, None)

        expected = {key: None for key in SEATING_RISE_KEYS}
        self.assertEqual(dialog.section_rise_overrides, expected)
        self.assertIn(expected, preview_snapshots)

    def test_reset_override_result_matches_detailed_dialog(self):
        initial = {
            "stalls": 130.0,
            "balcony_1": 240.0,
            "balcony_2": 310.0,
        }
        dialog, unused_snapshots = self.make_dialog([], initial)

        detail_class = _load_class(
            SECTION_DIALOG_PATH,
            "SectionDimensionInterpolationDialog",
        )
        detail = object.__new__(detail_class)
        detail.overrides = dict(initial)
        detail.accepted = False
        detail.Close = lambda result: None
        detail.on_reset(None, None)

        self.button_handler("Reset")(dialog, None, None)

        self.assertEqual(dialog.section_rise_overrides, detail.overrides)


if __name__ == "__main__":
    unittest.main()
