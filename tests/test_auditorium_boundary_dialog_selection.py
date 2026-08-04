# -*- coding: utf-8 -*-
"""Regressions for managing the optional boundary from the main dialog."""

import ast
import copy
import unittest
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]
RUNTIME_PATH = (
    ROOT / "commands" / "auditorium_generator" / "command_runtime.py"
)
MAIN_DIALOG_PATH = (
    ROOT / "commands" / "auditorium_generator" / "main_dialog.py"
)


def _tree(path):
    return ast.parse(path.read_text(encoding="utf-8-sig"), str(path))


def _function(tree, name):
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise AssertionError("Function {0} was not found.".format(name))


def _method(tree, class_name, method_name):
    for node in tree.body:
        if not isinstance(node, ast.ClassDef) or node.name != class_name:
            continue
        for child in node.body:
            if (
                isinstance(child, ast.FunctionDef)
                and child.name == method_name
            ):
                return child
    raise AssertionError(
        "Method {0}.{1} was not found.".format(class_name, method_name)
    )


def _called_name(call):
    if not isinstance(call, ast.Call):
        return None
    if isinstance(call.func, ast.Name):
        return call.func.id
    if isinstance(call.func, ast.Attribute):
        return call.func.attr
    return None


def _call_names(node):
    return {
        _called_name(child)
        for child in ast.walk(node)
        if isinstance(child, ast.Call)
    }


def _self_attributes(node):
    return {
        child.attr
        for child in ast.walk(node)
        if (
            isinstance(child, ast.Attribute)
            and isinstance(child.value, ast.Name)
            and child.value.id == "self"
        )
    }


def _load_method(method_name, namespace):
    source_tree = _tree(MAIN_DIALOG_PATH)
    node = copy.deepcopy(
        _method(source_tree, "AuditoriumDialog", method_name)
    )
    node.decorator_list = []
    module = ast.fix_missing_locations(
        ast.Module(body=[node], type_ignores=[])
    )
    exec(compile(module, str(MAIN_DIALOG_PATH), "exec"), namespace)
    return namespace[method_name]


class _BoundaryGetter(object):
    def __init__(self, result, curve=None):
        self.result = result
        self.curve = curve
        self.GeometryFilter = None
        self.prompt = None
        self.object_indices = []

    def SetCommandPrompt(self, prompt):
        self.prompt = prompt

    def Get(self):
        return self.result

    def Object(self, index):
        self.object_indices.append(index)
        if self.curve is None:
            return None
        return SimpleNamespace(Curve=lambda: self.curve)


class RuntimeBoundaryFlowTests(unittest.TestCase):
    def test_main_opens_dialog_without_pre_dialog_boundary_prompt(self):
        main = _function(_tree(RUNTIME_PATH), "main")
        calls = _call_names(main)

        self.assertNotIn("select_optional_auditorium_boundary", calls)
        self.assertIn("select_reference_baseline", calls)
        self.assertIn("analyze_reference_baseline", calls)
        self.assertIn("AuditoriumDialog", calls)
        self.assertIn("show_dialog_semi_modal", calls)


class BoundaryDialogStructureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tree = _tree(MAIN_DIALOG_PATH)

    def test_dialog_owns_status_select_change_and_clear_controls(self):
        initializer = _method(
            self.tree,
            "AuditoriumDialog",
            "__init__",
        )
        attributes = _self_attributes(initializer)
        self.assertTrue(
            {
                "boundary_status_label",
                "boundary_select_button",
                "boundary_clear_button",
            }.issubset(attributes)
        )
        self.assertIn("on_select_auditorium_boundary", attributes)
        self.assertIn("on_clear_auditorium_boundary", attributes)

    def test_select_handler_uses_push_pick_button(self):
        handler = _method(
            self.tree,
            "AuditoriumDialog",
            "on_select_auditorium_boundary",
        )
        self.assertIn("PushPickButton", _call_names(handler))
        self.assertIn("pick_auditorium_boundary", _self_attributes(handler))

    def test_picker_normalizes_and_commits_only_a_curve_selection(self):
        picker = _method(
            self.tree,
            "AuditoriumDialog",
            "pick_auditorium_boundary",
        )
        calls = _call_names(picker)
        self.assertIn("GetObject", calls)
        self.assertIn("normalize_boundary_curve", calls)
        self.assertIn("update_boundary_status", calls)
        self.assertIn("update_preview", calls)
        self.assertTrue(
            any(
                isinstance(node, ast.Constant)
                and node.value == "auditorium_boundary_curve"
                for node in ast.walk(picker)
            )
        )

    def test_clear_handler_removes_boundary_and_refreshes_preview(self):
        clearer = _method(
            self.tree,
            "AuditoriumDialog",
            "on_clear_auditorium_boundary",
        )
        calls = _call_names(clearer)
        self.assertIn("pop", calls)
        self.assertIn("update_boundary_status", calls)
        self.assertIn("update_preview", calls)
        self.assertTrue(
            any(
                isinstance(node, ast.Constant)
                and node.value == "auditorium_boundary_curve"
                for node in ast.walk(clearer)
            )
        )

    def test_status_changes_select_button_to_change_when_present(self):
        updater = _method(
            self.tree,
            "AuditoriumDialog",
            "update_boundary_status",
        )
        text_values = {
            node.value
            for node in ast.walk(updater)
            if isinstance(node, ast.Constant) and isinstance(node.value, str)
        }
        self.assertIn("Select Boundary", text_values)
        self.assertIn("Change Boundary", text_values)


class BoundaryDialogBehaviorTests(unittest.TestCase):
    def make_picker(self, result, curve=None, normalizer=None):
        getter = _BoundaryGetter(result, curve)
        selected_result = object()
        if result == "selected":
            getter.result = selected_result
        curve_filter = object()
        normalize_calls = []

        if normalizer is None:
            normalizer = lambda source, datum, tolerance: (
                normalize_calls.append((source, datum, tolerance))
                or "normalized-boundary"
            )

        namespace = {
            "ric": SimpleNamespace(GetObject=lambda: getter),
            "Rhino": SimpleNamespace(
                DocObjects=SimpleNamespace(
                    ObjectType=SimpleNamespace(Curve=curve_filter)
                ),
                Input=SimpleNamespace(
                    GetResult=SimpleNamespace(Object=selected_result)
                ),
            ),
            "normalize_boundary_curve": normalizer,
            "forms": SimpleNamespace(
                MessageBox=SimpleNamespace(Show=lambda *args: None),
                MessageBoxButtons=SimpleNamespace(OK=object()),
                MessageBoxType=SimpleNamespace(Warning=object()),
            ),
        }
        picker = _load_method("pick_auditorium_boundary", namespace)
        return picker, getter, curve_filter, normalize_calls

    @staticmethod
    def fake_dialog(boundary="old-boundary"):
        stage_data = {"audience_datum_point": "datum"}
        if boundary is not None:
            stage_data["auditorium_boundary_curve"] = boundary
        calls = []
        dialog = SimpleNamespace(
            stage_data=stage_data,
            doc=SimpleNamespace(ModelAbsoluteTolerance=0.01),
            update_boundary_status=lambda: calls.append("status"),
            update_preview=lambda *args, **kwargs: calls.append(
                ("preview", args, kwargs)
            ),
        )
        return dialog, calls

    def test_successful_selection_replaces_boundary_and_updates_now(self):
        source_curve = object()
        picker, getter, curve_filter, normalize_calls = self.make_picker(
            "selected",
            source_curve,
        )
        dialog, calls = self.fake_dialog()

        picker(dialog, None, None)

        self.assertIs(curve_filter, getter.GeometryFilter)
        self.assertEqual([0], getter.object_indices)
        self.assertEqual(
            [(source_curve, "datum", 0.01)],
            normalize_calls,
        )
        self.assertEqual(
            "normalized-boundary",
            dialog.stage_data["auditorium_boundary_curve"],
        )
        self.assertEqual("status", calls[0])
        self.assertEqual("preview", calls[1][0])

    def test_cancel_preserves_current_boundary_without_refresh(self):
        cancel_result = object()
        picker, _getter, _filter, normalize_calls = self.make_picker(
            cancel_result,
            object(),
        )
        dialog, calls = self.fake_dialog()

        picker(dialog, None, None)

        self.assertEqual(
            "old-boundary",
            dialog.stage_data["auditorium_boundary_curve"],
        )
        self.assertEqual([], normalize_calls)
        self.assertEqual([], calls)

    def test_clear_is_the_only_action_that_removes_boundary(self):
        namespace = {}
        clearer = _load_method(
            "on_clear_auditorium_boundary",
            namespace,
        )
        dialog, calls = self.fake_dialog()

        clearer(dialog, None, None)

        self.assertNotIn(
            "auditorium_boundary_curve",
            dialog.stage_data,
        )
        self.assertEqual("status", calls[0])
        self.assertEqual("preview", calls[1][0])


if __name__ == "__main__":
    unittest.main()
