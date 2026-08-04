# -*- coding: utf-8 -*-
"""AST regressions for the main-dialog balcony quick controls."""

import ast
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MAIN_DIALOG_PATH = (
    ROOT
    / "commands"
    / "auditorium_generator"
    / "main_dialog.py"
)

TIER_CONTROLS = (
    {
        "detail_button": "balcony_button",
        "height_box": "balcony_height_box",
        "max_button": "balcony_max_button",
        "height_key": "balcony_last_platform_z",
        "row_key": "balcony_row_count",
    },
    {
        "detail_button": "balcony2_button",
        "height_box": "balcony2_height_box",
        "max_button": "balcony2_max_button",
        "height_key": "balcony2_last_platform_z",
        "row_key": "balcony2_row_count",
    },
)


def _parse():
    return ast.parse(
        MAIN_DIALOG_PATH.read_text(encoding="utf-8"),
        str(MAIN_DIALOG_PATH),
    )


def _dialog_node(tree):
    for node in tree.body:
        if (
            isinstance(node, ast.ClassDef)
            and node.name == "AuditoriumDialog"
        ):
            return node
    raise AssertionError("AuditoriumDialog was not found.")


def _method_map(dialog_node):
    return {
        node.name: node
        for node in dialog_node.body
        if isinstance(node, ast.FunctionDef)
    }


def _attribute_chain(node):
    parts = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
    else:
        return None
    return tuple(reversed(parts))


def _assigned_self_attributes(node):
    result = {}
    for child in ast.walk(node):
        if not isinstance(child, ast.Assign):
            continue
        for target in child.targets:
            chain = _attribute_chain(target)
            if chain is not None and chain[:1] == ("self",):
                result.setdefault(chain, []).append((child, child.value))
    return result


def _called_name(call):
    if isinstance(call.func, ast.Name):
        return call.func.id
    if isinstance(call.func, ast.Attribute):
        return call.func.attr
    return None


def _calls_named(node, name):
    return [
        child
        for child in ast.walk(node)
        if isinstance(child, ast.Call) and _called_name(child) == name
    ]


def _contains_string(node, value):
    return any(
        isinstance(child, ast.Constant) and child.value == value
        for child in ast.walk(node)
    )


def _self_attribute_names(node):
    return {
        child.attr
        for child in ast.walk(node)
        if (
            isinstance(child, ast.Attribute)
            and isinstance(child.value, ast.Name)
            and child.value.id == "self"
        )
    }


def _self_method_call_names(node):
    names = set()
    for child in ast.walk(node):
        if not isinstance(child, ast.Call):
            continue
        chain = _attribute_chain(child.func)
        if chain is not None and len(chain) == 2 and chain[0] == "self":
            names.add(chain[1])
    return names


def _reachable_methods(methods, start_name, depth=3):
    pending = [(start_name, 0)]
    visited = set()
    result = []
    while pending:
        name, current_depth = pending.pop(0)
        if name in visited or name not in methods:
            continue
        visited.add(name)
        method = methods[name]
        result.append(method)
        if current_depth >= depth:
            continue
        for called_name in _self_method_call_names(method):
            pending.append((called_name, current_depth + 1))
    return result


def _event_handler_name(init_node, control_name, event_name):
    for node in ast.walk(init_node):
        if not isinstance(node, ast.AugAssign) or not isinstance(
            node.op, ast.Add
        ):
            continue
        if _attribute_chain(node.target) != (
            "self",
            control_name,
            event_name,
        ):
            continue
        value_chain = _attribute_chain(node.value)
        if (
            value_chain is not None
            and len(value_chain) == 2
            and value_chain[0] == "self"
        ):
            return value_chain[1]
    raise AssertionError(
        "{0}.{1} has no self-method handler.".format(
            control_name,
            event_name,
        )
    )


def _direct_main_layout_rows(init_node):
    rows = []
    for node in ast.walk(init_node):
        if not isinstance(node, ast.Call):
            continue
        if _attribute_chain(node.func) != ("main_layout", "AddRow"):
            continue
        rows.append(node)
    return rows


def _horizontal_quick_rows(init_node):
    """Return local StackLayouts added as one main-layout row."""
    item_controls = {}
    for node in ast.walk(init_node):
        if not isinstance(node, ast.Call):
            continue
        chain = _attribute_chain(node.func)
        if (
            chain is None
            or len(chain) != 3
            or chain[1:] != ("Items", "Add")
            or not node.args
            or not isinstance(node.args[0], ast.Call)
            or _called_name(node.args[0]) != "StackLayoutItem"
            or not node.args[0].args
        ):
            continue
        control_chain = _attribute_chain(node.args[0].args[0])
        if (
            control_chain is None
            or len(control_chain) != 2
            or control_chain[0] != "self"
        ):
            continue
        item_controls.setdefault(chain[0], []).append(
            (node.lineno, control_chain[1])
        )

    added_layouts = set()
    for row in _direct_main_layout_rows(init_node):
        if len(row.args) == 1 and isinstance(row.args[0], ast.Name):
            added_layouts.add(row.args[0].id)

    return {
        name: [
            control
            for _lineno, control in sorted(items)
        ]
        for name, items in item_controls.items()
        if name in added_layouts
    }


def _self_values_update_calls(node):
    return [
        child
        for child in ast.walk(node)
        if (
            isinstance(child, ast.Call)
            and _attribute_chain(child.func)
            == ("self", "values", "update")
        )
    ]


class BalconyQuickControlConstructionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tree = _parse()
        cls.dialog = _dialog_node(cls.tree)
        cls.methods = _method_map(cls.dialog)
        cls.init_node = cls.methods["__init__"]

    def test_height_boxes_bind_directly_to_relative_storage_keys(self):
        assignments = _assigned_self_attributes(self.init_node)
        for controls in TIER_CONTROLS:
            chain = ("self", controls["height_box"])
            self.assertIn(chain, assignments)
            creation = assignments[chain][0][1]
            self.assertIsInstance(creation, ast.Call)
            self.assertEqual("make_text_box", _called_name(creation))
            self.assertEqual(1, len(creation.args))
            self.assertIsInstance(creation.args[0], ast.Constant)
            self.assertEqual(
                controls["height_key"],
                creation.args[0].value,
            )

    def test_each_tier_has_a_max_apply_button_and_click_handler(self):
        assignments = _assigned_self_attributes(self.init_node)
        for controls in TIER_CONTROLS:
            chain = ("self", controls["max_button"])
            self.assertIn(chain, assignments)
            creation = assignments[chain][0][1]
            self.assertIsInstance(creation, ast.Call)
            self.assertEqual("Button", _called_name(creation))

            handler_name = _event_handler_name(
                self.init_node,
                controls["max_button"],
                "Click",
            )
            self.assertIn(handler_name, self.methods)

    def test_quick_controls_occupy_the_two_columns_right_of_detail(self):
        rows = _direct_main_layout_rows(self.init_node)
        stack_rows = _horizontal_quick_rows(self.init_node)
        for controls in TIER_CONTROLS:
            expected = [
                controls["detail_button"],
                controls["height_box"],
                controls["max_button"],
            ]
            matching_rows = []
            for row in rows:
                chains = [_attribute_chain(arg) for arg in row.args]
                if chains == [
                    ("self", attribute) for attribute in expected
                ]:
                    matching_rows.append(row)
            matching_stacks = [
                name
                for name, items in stack_rows.items()
                if items == expected
            ]
            self.assertEqual(
                1,
                len(matching_rows) + len(matching_stacks),
                "Expected one direct AddRow or one horizontal StackLayout "
                "containing ({0}) in that order.".format(
                    ", ".join("self." + item for item in expected)
                ),
            )

    def test_height_boxes_participate_in_main_enter_updates(self):
        all_text_boxes = self.methods["all_text_boxes"]
        referenced = _self_attribute_names(all_text_boxes)
        for controls in TIER_CONTROLS:
            self.assertIn(controls["height_box"], referenced)


class BalconyQuickControlSynchronizationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tree = _parse()
        cls.dialog = _dialog_node(cls.tree)
        cls.methods = _method_map(cls.dialog)

    def test_main_height_boxes_are_parsed_back_into_relative_values(self):
        reachable = _reachable_methods(
            self.methods,
            "read_params",
            depth=3,
        )
        for controls in TIER_CONTROLS:
            matching_parsers = []
            for method in reachable:
                for call in _calls_named(method, "parse_float"):
                    if not call.args:
                        continue
                    if _attribute_chain(call.args[0]) == (
                        "self",
                        controls["height_box"],
                    ):
                        matching_parsers.append(call)
            self.assertTrue(
                matching_parsers,
                "read_params must parse self.{0}.".format(
                    controls["height_box"]
                ),
            )
            self.assertTrue(
                any(
                    _contains_string(method, controls["height_key"])
                    for method in reachable
                ),
                "The parsed value must update {0}.".format(
                    controls["height_key"]
                ),
            )

    def test_detail_dialog_receives_quick_values_after_preview_update(self):
        method = self.methods["open_balcony_settings"]
        update_calls = _calls_named(method, "update_preview")
        dialog_calls = _calls_named(method, "BalconySettingsDialog")
        self.assertTrue(update_calls)
        self.assertEqual(1, len(dialog_calls))
        self.assertTrue(
            any(
                update_call.lineno < dialog_calls[0].lineno
                for update_call in update_calls
            )
        )

    def test_accepted_detail_values_refresh_both_main_height_boxes(self):
        open_method = self.methods["open_balcony_settings"]
        sync_methods = []
        expected_boxes = {
            controls["height_box"] for controls in TIER_CONTROLS
        }
        for name, method in self.methods.items():
            assigned = _assigned_self_attributes(method)
            written_boxes = {
                chain[1]
                for chain in assigned
                if (
                    len(chain) == 3
                    and chain[0] == "self"
                    and chain[2] == "Text"
                )
            }
            if expected_boxes.issubset(written_boxes):
                sync_methods.append(name)

        self.assertTrue(
            sync_methods,
            "A shared values-to-quick-controls synchronization method "
            "is required.",
        )
        called_syncs = [
            call
            for call in ast.walk(open_method)
            if (
                isinstance(call, ast.Call)
                and _called_name(call) in sync_methods
            )
        ]
        self.assertTrue(
            called_syncs,
            "Accepted detail-dialog values must refresh both main "
            "height boxes.",
        )

        values_updates = _self_values_update_calls(open_method)
        preview_updates = _calls_named(open_method, "update_preview")
        self.assertTrue(values_updates)
        refresh_after_commit = [
            call
            for call in called_syncs
            if any(
                update.lineno < call.lineno
                for update in values_updates
            )
        ]
        self.assertTrue(refresh_after_commit)
        self.assertTrue(
            any(
                sync_call.lineno < preview_call.lineno
                for sync_call in refresh_after_commit
                for preview_call in preview_updates
            ),
            "Text must be synchronized before rebuilding the preview, "
            "or stale quick values will overwrite the detail changes.",
        )


class BalconyQuickMaximumRowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tree = _parse()
        cls.dialog = _dialog_node(cls.tree)
        cls.methods = _method_map(cls.dialog)
        cls.init_node = cls.methods["__init__"]

    def test_preview_updates_both_max_button_states(self):
        update_preview = self.methods["update_preview"]
        self.assertTrue(
            _calls_named(update_preview, "update_balcony_max_buttons")
        )
        updater = self.methods["update_balcony_max_buttons"]
        referenced = _self_attribute_names(updater)
        direct_assignments = _assigned_self_attributes(updater)
        for controls in TIER_CONTROLS:
            self.assertIn(controls["max_button"], referenced)
            self.assertIn(
                ("self", controls["max_button"], "Text"),
                direct_assignments,
            )
            self.assertIn(
                ("self", controls["max_button"], "Enabled"),
                direct_assignments,
            )

        constants = {
            child.value
            for child in ast.walk(updater)
            if isinstance(child, ast.Constant)
            and isinstance(child.value, str)
        }
        self.assertTrue(
            any("Max" in value and "{0}" in value for value in constants)
        )
        self.assertTrue(
            any("Max" in value and "{0}" not in value for value in constants)
        )

    def test_max_handlers_apply_the_matching_tier_row_count(self):
        shared = self.methods["apply_balcony_max_rows"]
        self.assertTrue(_calls_named(shared, "update_preview"))
        self.assertIn("values", _self_attribute_names(shared))

        for tier_index, controls in enumerate(TIER_CONTROLS):
            handler_name = _event_handler_name(
                self.init_node,
                controls["max_button"],
                "Click",
            )
            handler = self.methods[handler_name]
            apply_calls = _calls_named(handler, "apply_balcony_max_rows")
            self.assertEqual(1, len(apply_calls))
            self.assertEqual(2, len(apply_calls[0].args))
            self.assertIsInstance(apply_calls[0].args[0], ast.Constant)
            self.assertEqual(
                tier_index,
                apply_calls[0].args[0].value,
            )
            self.assertIsInstance(apply_calls[0].args[1], ast.Constant)
            self.assertEqual(
                controls["row_key"],
                apply_calls[0].args[1].value,
            )


if __name__ == "__main__":
    unittest.main()
