# -*- coding: utf-8 -*-
"""Rhino-free tests for section live-preview transaction handling."""

import ast
import types
import unittest
from pathlib import Path


MAIN_DIALOG_PATH = (
    Path(__file__).resolve().parents[1]
    / "commands"
    / "auditorium_generator"
    / "main_dialog.py"
)


def _load_method(class_name, method_name):
    tree = ast.parse(
        MAIN_DIALOG_PATH.read_text(encoding="utf-8-sig"),
        filename=str(MAIN_DIALOG_PATH),
    )
    class_node = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == class_name
    )
    method_node = next(
        node
        for node in class_node.body
        if isinstance(node, ast.FunctionDef) and node.name == method_name
    )
    selected = ast.fix_missing_locations(
        ast.Module(body=[method_node], type_ignores=[])
    )
    namespace = {"__builtins__": __builtins__}
    exec(compile(selected, str(MAIN_DIALOG_PATH), "exec"), namespace)
    return namespace[method_name]


class SectionLivePreviewTransactionTests(unittest.TestCase):
    def setUp(self):
        self.live_preview = _load_method(
            "AuditoriumDialog",
            "on_section_dimension_live_preview",
        )

    def make_dialog(self):
        return types.SimpleNamespace(
            section_rise_overrides={"stalls": 100.0},
            section_solver_signatures={"stalls": "original"},
            warning_text="",
        )

    def test_success_returns_canonical_overrides_and_fresh_rows(self):
        dialog = self.make_dialog()
        update_calls = []

        def update_preview(show_error):
            update_calls.append(
                (show_error, dict(dialog.section_rise_overrides))
            )
            dialog.section_rise_overrides["stalls"] += 0.25
            return True

        rows = [{"key": "stalls", "current_rise": 110.25}]
        dialog.update_preview = update_preview
        dialog.section_interpolation_rows = lambda: list(rows)

        result = self.live_preview(dialog, {"stalls": 110.0})

        self.assertEqual(
            update_calls,
            [(False, {"stalls": 110.0})],
        )
        self.assertEqual(
            result,
            {
                "overrides": {"stalls": 110.25},
                "sections": rows,
            },
        )

    def test_failed_preview_restores_previous_state(self):
        dialog = self.make_dialog()
        update_calls = []

        def update_preview(show_error):
            update_calls.append(dict(dialog.section_rise_overrides))
            if len(update_calls) == 1:
                dialog.warning_text = "preview failed"
                return False
            return True

        dialog.update_preview = update_preview
        dialog.section_interpolation_rows = lambda: self.fail(
            "rows should not be requested"
        )

        with self.assertRaisesRegex(ValueError, "preview failed"):
            self.live_preview(dialog, {"stalls": 110.0})

        self.assertEqual(
            update_calls,
            [{"stalls": 110.0}, {"stalls": 100.0}],
        )
        self.assertEqual(
            dialog.section_rise_overrides,
            {"stalls": 100.0},
        )
        self.assertEqual(
            dialog.section_solver_signatures,
            {"stalls": "original"},
        )

    def test_row_refresh_error_also_restores_previous_state(self):
        dialog = self.make_dialog()
        update_calls = []
        dialog.update_preview = lambda show_error: (
            update_calls.append(dict(dialog.section_rise_overrides))
            or True
        )

        def fail_rows():
            raise RuntimeError("row refresh failed")

        dialog.section_interpolation_rows = fail_rows

        with self.assertRaisesRegex(RuntimeError, "row refresh failed"):
            self.live_preview(dialog, {"stalls": 110.0})

        self.assertEqual(
            update_calls,
            [{"stalls": 110.0}, {"stalls": 100.0}],
        )
        self.assertEqual(
            dialog.section_rise_overrides,
            {"stalls": 100.0},
        )
        self.assertEqual(
            dialog.section_solver_signatures,
            {"stalls": "original"},
        )


if __name__ == "__main__":
    unittest.main()
