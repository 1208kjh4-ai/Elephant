# -*- coding: utf-8 -*-
"""Rhino-free regression tests for the basic stair dialog calculations."""

import ast
import types
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
STAIR_PATH = ROOT / "commands" / "Stair.py"


def _load_calculation_namespace():
    tree = ast.parse(
        STAIR_PATH.read_text(encoding="utf-8-sig"),
        filename=str(STAIR_PATH),
    )
    selected_names = {
        "MIN_STEP_COUNT",
        "MAX_STEP_COUNT",
        "CALC_BY_TREADS",
        "CALC_BY_TREADS_PLUS_ONE",
    }
    selected_functions = {
        "parse_step_count",
        "calculate_landing_count",
        "calculate_stair_layout",
        "calculate_riser_metrics",
        "calculate_top_offset_transform",
    }
    nodes = []
    for node in tree.body:
        if isinstance(node, ast.Assign):
            assigned_names = {
                target.id
                for target in node.targets
                if isinstance(target, ast.Name)
            }
            if assigned_names.intersection(selected_names):
                nodes.append(node)
        elif isinstance(node, ast.FunctionDef) and node.name in selected_functions:
            nodes.append(node)

    namespace = {"__builtins__": __builtins__}
    module = ast.fix_missing_locations(ast.Module(body=nodes, type_ignores=[]))
    exec(compile(module, str(STAIR_PATH), "exec"), namespace)
    return namespace


def _load_dialog_methods(method_names):
    if isinstance(method_names, str):
        method_names = {method_names}
    else:
        method_names = set(method_names)
    tree = ast.parse(
        STAIR_PATH.read_text(encoding="utf-8-sig"),
        filename=str(STAIR_PATH),
    )
    dialog_nodes = [
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "StairGeneratorDialog"
    ]
    if len(dialog_nodes) != 1:
        raise AssertionError("StairGeneratorDialog definition was not found.")
    method_nodes = [
        node
        for node in dialog_nodes[0].body
        if isinstance(node, ast.FunctionDef) and node.name in method_names
    ]
    if len(method_nodes) != len(method_names):
        raise AssertionError("Requested dialog methods were not found.")

    selected_class = ast.ClassDef(
        name="SelectedDialog",
        bases=[],
        keywords=[],
        body=method_nodes,
        decorator_list=[],
    )
    namespace = _load_calculation_namespace()
    module = ast.fix_missing_locations(
        ast.Module(body=[selected_class], type_ignores=[])
    )
    exec(compile(module, str(STAIR_PATH), "exec"), namespace)
    return namespace["SelectedDialog"]


class _Value(object):
    def __init__(self, value):
        self.Text = str(value)


class _Disposable(object):
    def __init__(self):
        self.dispose_calls = 0

    def Dispose(self):
        self.dispose_calls += 1


class StairCalculationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.namespace = _load_calculation_namespace()
        cls.parse_step_count = staticmethod(cls.namespace["parse_step_count"])
        cls.calculate_landing_count = staticmethod(
            cls.namespace["calculate_landing_count"]
        )
        cls.calculate_stair_layout = staticmethod(
            cls.namespace["calculate_stair_layout"]
        )
        cls.calculate_riser_metrics = staticmethod(
            cls.namespace["calculate_riser_metrics"]
        )
        cls.calculate_top_offset_transform = staticmethod(
            cls.namespace["calculate_top_offset_transform"]
        )
        cls.by_treads = cls.namespace["CALC_BY_TREADS"]
        cls.plus_one = cls.namespace["CALC_BY_TREADS_PLUS_ONE"]

    def test_step_count_text_accepts_only_range_limited_integers(self):
        self.assertEqual(self.parse_step_count(" 17 "), 17)
        for invalid in ("", "17.0", "abc", "0", "101"):
            with self.subTest(invalid=invalid):
                with self.assertRaises(ValueError):
                    self.parse_step_count(invalid)

    def test_landing_count_uses_height_and_available_run(self):
        self.assertEqual(self.calculate_landing_count(6000.0, 10000.0), (2, False))
        self.assertEqual(self.calculate_landing_count(6000.0, 2400.0), (0, True))
        self.assertEqual(self.calculate_landing_count(2500.0, 1000.0), (0, False))

    def test_without_landing_input_is_the_total_tread_count(self):
        result = self.calculate_stair_layout(17, 1, self.by_treads, False)
        self.assertEqual(result, (17, [17], 17, 0))

    def test_landing_input_is_repeated_for_every_flight(self):
        result = self.calculate_stair_layout(11, 3, self.by_treads, True)
        self.assertEqual(result, (33, [11, 11, 11], 33, 0))

    def test_lower_final_tread_adds_one_global_riser(self):
        result = self.calculate_stair_layout(11, 3, self.plus_one, True)
        self.assertEqual(result, (33, [11, 11, 11], 34, 1))

        riser_height, top_offset = self.calculate_riser_metrics(
            6000.0,
            result[2],
            result[3],
        )
        highest_tread = 6000.0 - top_offset
        self.assertAlmostEqual(top_offset, riser_height)
        self.assertAlmostEqual(highest_tread - (33 * riser_height), 0.0)

    def test_different_side_heights_get_matching_top_offsets(self):
        start_height, start_offset = self.calculate_riser_metrics(
            6000.0, 34, 1
        )
        end_height, end_offset = self.calculate_riser_metrics(
            6200.0, 34, 1
        )
        self.assertAlmostEqual(6000.0 - start_offset - (33 * start_height), 0.0)
        self.assertAlmostEqual(6200.0 - end_offset - (33 * end_height), 0.0)

        m20, m21, m23 = self.calculate_top_offset_transform(
            10.0,
            20.0,
            110.0,
            20.0,
            start_offset,
            end_offset,
        )
        start_shift = (m20 * 10.0) + (m21 * 20.0) + m23
        end_shift = (m20 * 110.0) + (m21 * 20.0) + m23
        self.assertAlmostEqual(start_shift, -start_offset)
        self.assertAlmostEqual(end_shift, -end_offset)

        with self.assertRaises(ValueError):
            self.calculate_top_offset_transform(
                10.0,
                20.0,
                10.0,
                20.0,
                start_offset,
                end_offset,
            )

    def test_total_mode_rejects_multiple_flights(self):
        with self.assertRaises(ValueError):
            self.calculate_stair_layout(17, 2, self.by_treads, False)


class StairDialogModeTests(unittest.TestCase):
    def make_dialog(self):
        dialog_class = _load_dialog_methods("OnLandingChanged")
        dialog = dialog_class()
        dialog.chk_landing = type("CheckBox", (), {"Checked": False})()
        dialog.step_count_box = _Value(16)
        dialog.step_count_label = _Value("계단 단수:")
        dialog.non_landing_step_count = 16
        dialog.landing_step_count = 8
        dialog._step_input_uses_per_flight = False
        dialog.preview_calls = 0

        def update_preview():
            dialog.preview_calls += 1

        dialog.UpdatePreview = update_preview
        return dialog

    def test_landing_toggle_switches_between_total_and_per_flight_values(self):
        dialog = self.make_dialog()
        dialog.chk_landing.Checked = True
        dialog.OnLandingChanged(None, None)

        self.assertEqual(dialog.step_count_box.Text, "8")
        self.assertEqual(dialog.step_count_label.Text, "구간당 단수:")
        self.assertTrue(dialog._step_input_uses_per_flight)

        dialog.step_count_box.Text = "9"
        dialog.chk_landing.Checked = False
        dialog.OnLandingChanged(None, None)

        self.assertEqual(dialog.step_count_box.Text, "16")
        self.assertEqual(dialog.step_count_label.Text, "계단 단수:")
        self.assertEqual(dialog.landing_step_count, 9)
        self.assertFalse(dialog._step_input_uses_per_flight)
        self.assertEqual(dialog.preview_calls, 2)

    def test_preview_cleanup_disposes_hidden_guides_and_temporary_top_curve(self):
        dialog_class = _load_dialog_methods(
            {"DisposeGeometry", "DisposeCurrentPreview"}
        )
        dialog = dialog_class()
        original_top = _Disposable()
        active_top = _Disposable()
        pending_top = _Disposable()
        brep = _Disposable()
        mesh = _Disposable()
        guide_s = _Disposable()
        guide_e = _Disposable()

        dialog.top_crv = original_top
        dialog.stair_top_crv = active_top
        dialog._pending_top_crv = pending_top
        dialog.final_breps = [brep]
        dialog.guide_s = guide_s
        dialog.guide_e = guide_e
        dialog.conduit = types.SimpleNamespace(
            meshes=[mesh],
            breps=[brep],
            railing_lines=[],
        )

        dialog.DisposeCurrentPreview()

        for geometry in (active_top, pending_top, brep, mesh, guide_s, guide_e):
            self.assertEqual(geometry.dispose_calls, 1)
        self.assertEqual(original_top.dispose_calls, 0)
        self.assertEqual(dialog.conduit.meshes, [])
        self.assertEqual(dialog.conduit.breps, [])
        self.assertEqual(dialog.conduit.railing_lines, [])
        self.assertIs(dialog.stair_top_crv, original_top)
        self.assertIsNone(dialog._pending_top_crv)


if __name__ == "__main__":
    unittest.main()
