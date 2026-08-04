# -*- coding: utf-8 -*-
"""Rhino-free regression tests for two-stage dialog Enter handling."""

import ast
import math
import types
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BALCONY_DIALOG_PATH = (
    ROOT
    / "commands"
    / "auditorium_generator"
    / "balcony_settings_dialog.py"
)
SECTION_DIALOG_PATH = (
    ROOT
    / "commands"
    / "auditorium_generator"
    / "section_result_dialogs.py"
)


class _FakeDialog(object):
    @classmethod
    def __class_getitem__(cls, item):
        return cls


class _FakeKeys(object):
    Enter = object()


class _FakeMessageBox(object):
    calls = []

    @classmethod
    def Show(cls, *args):
        cls.calls.append(args)
        return None


class _FakeForms(object):
    Dialog = _FakeDialog
    Keys = _FakeKeys
    MessageBox = _FakeMessageBox
    MessageBoxButtons = types.SimpleNamespace(
        OK=object(),
        YesNo=object(),
    )
    MessageBoxType = types.SimpleNamespace(Warning=object())
    DialogResult = types.SimpleNamespace(Yes=object())


def _validate_section_rise_target(z_values, target, label):
    value = float(target)
    if not math.isfinite(value) or value < 0.0:
        raise ValueError("invalid target for {0}".format(label))
    return value


def _load_selected_class(path, class_name):
    tree = ast.parse(
        path.read_text(encoding="utf-8-sig"),
        filename=str(path),
    )
    class_nodes = [
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == class_name
    ]
    if len(class_nodes) != 1:
        raise AssertionError(
            "Expected one {0} definition, found {1}.".format(
                class_name,
                len(class_nodes),
            )
        )

    selected = ast.fix_missing_locations(
        ast.Module(body=class_nodes, type_ignores=[])
    )
    namespace = {
        "__builtins__": __builtins__,
        "forms": _FakeForms,
        "math": math,
        "is_finite_number": math.isfinite,
        "validate_section_rise_target": (
            _validate_section_rise_target
        ),
        "SECTION_INTERPOLATION_WARNING_RATIO": 0.2,
        "SECTION_RISE_KEYS": (),
        "format_section_height_dimension": (
            lambda value: "current:{0}".format(value)
        ),
    }
    exec(compile(selected, str(path), "exec"), namespace)
    return namespace[class_name]


def _key_event(key):
    return types.SimpleNamespace(Key=key, Handled=False)


def _text_box(text, enabled=True):
    return types.SimpleNamespace(Text=str(text), Enabled=enabled)


class DialogEnterKeyTests(unittest.TestCase):
    def setUp(self):
        _FakeMessageBox.calls = []

    def make_balcony_dialog(self):
        dialog_class = _load_selected_class(
            BALCONY_DIALOG_PATH,
            "BalconySettingsDialog",
        )
        dialog = object.__new__(dialog_class)
        boxes = [_text_box("100"), _text_box("8")]
        dialog.last_platform_z_box = boxes[0]
        dialog.all_text_boxes = lambda: boxes
        dialog._enter_text_snapshot = dialog.text_box_snapshot()
        dialog._text_changed_since_enter = False
        dialog._enter_close_armed = False
        dialog.accepted = False
        dialog.close_calls = []
        dialog.Close = lambda result: dialog.close_calls.append(result)
        return dialog, boxes

    def make_section_dialog(self, callback):
        dialog_class = _load_selected_class(
            SECTION_DIALOG_PATH,
            "SectionDimensionInterpolationDialog",
        )
        dialog = object.__new__(dialog_class)
        dialog.sections = [
            {
                "key": "main",
                "label": "Main floor",
                "current_rise": 100.0,
                "editable": True,
            },
            {
                "key": "fixed",
                "label": "Fixed interval",
                "current_rise": 50.0,
                "editable": False,
            },
        ]
        dialog.target_boxes = {
            "main": _text_box("100"),
            "fixed": _text_box("50", enabled=False),
        }
        dialog.current_labels = {
            "main": _text_box("current:100.0"),
            "fixed": _text_box("current:50.0"),
        }
        dialog.overrides = {}
        dialog.live_preview_callback = callback
        dialog.accepted = False
        dialog.close_calls = []
        dialog.Close = lambda result: dialog.close_calls.append(result)
        dialog._enter_applied_snapshot = dialog.target_text_snapshot()
        return dialog

    def test_balcony_edit_enter_applies_then_second_enter_closes(self):
        dialog, boxes = self.make_balcony_dialog()
        preview_snapshots = []

        def preview():
            preview_snapshots.append(dialog.text_box_snapshot())
            return True

        dialog.try_live_preview = preview
        boxes[0].Text = "110"
        dialog.on_text_box_text_changed(boxes[0], None)

        first_event = _key_event(_FakeForms.Keys.Enter)
        dialog.on_text_box_key_down(boxes[0], first_event)

        self.assertTrue(first_event.Handled)
        self.assertEqual(preview_snapshots, [("110", "8")])
        self.assertEqual(dialog.close_calls, [])
        self.assertFalse(dialog.accepted)

        second_event = _key_event(_FakeForms.Keys.Enter)
        dialog.on_text_box_key_down(boxes[0], second_event)

        self.assertTrue(second_event.Handled)
        self.assertEqual(preview_snapshots, [("110", "8")])
        self.assertEqual(dialog.close_calls, [True])
        self.assertTrue(dialog.accepted)

    def test_balcony_reedit_requires_another_apply_enter(self):
        dialog, boxes = self.make_balcony_dialog()
        preview_snapshots = []
        dialog.try_live_preview = lambda: (
            preview_snapshots.append(dialog.text_box_snapshot()) or True
        )

        boxes[0].Text = "110"
        dialog.on_text_box_text_changed(boxes[0], None)
        dialog.on_text_box_key_down(
            boxes[0],
            _key_event(_FakeForms.Keys.Enter),
        )

        boxes[1].Text = "9"
        dialog.on_text_box_text_changed(boxes[1], None)
        dialog.on_text_box_key_down(
            boxes[1],
            _key_event(_FakeForms.Keys.Enter),
        )

        self.assertEqual(
            preview_snapshots,
            [("110", "8"), ("110", "9")],
        )
        self.assertEqual(dialog.close_calls, [])

        dialog.on_text_box_key_down(
            boxes[1],
            _key_event(_FakeForms.Keys.Enter),
        )
        self.assertEqual(dialog.close_calls, [True])
        self.assertEqual(len(preview_snapshots), 2)

    def test_balcony_failed_apply_stays_open_and_unarmed(self):
        dialog, boxes = self.make_balcony_dialog()
        preview_calls = []
        dialog.try_live_preview = lambda: (
            preview_calls.append(True) and False
        )
        boxes[0].Text = "invalid"
        dialog.on_text_box_text_changed(boxes[0], None)

        dialog.on_text_box_key_down(
            boxes[0],
            _key_event(_FakeForms.Keys.Enter),
        )
        dialog.on_text_box_key_down(
            boxes[0],
            _key_event(_FakeForms.Keys.Enter),
        )

        self.assertEqual(len(preview_calls), 2)
        self.assertEqual(dialog.close_calls, [])
        self.assertFalse(dialog._enter_close_armed)

    def test_balcony_lost_focus_failure_disarms_close(self):
        dialog, boxes = self.make_balcony_dialog()
        preview_results = [True, False, False]
        dialog.try_live_preview = lambda: preview_results.pop(0)
        boxes[0].Text = "110"
        dialog.on_text_box_text_changed(boxes[0], None)
        dialog.on_text_box_key_down(
            boxes[0],
            _key_event(_FakeForms.Keys.Enter),
        )
        self.assertTrue(dialog._enter_close_armed)

        dialog.on_text_box_lost_focus(boxes[0], None)
        self.assertFalse(dialog._enter_close_armed)
        self.assertTrue(dialog._text_changed_since_enter)

        dialog.on_text_box_key_down(
            boxes[0],
            _key_event(_FakeForms.Keys.Enter),
        )
        self.assertEqual(dialog.close_calls, [])

    def test_balcony_option_change_restarts_enter_cycle(self):
        dialog, boxes = self.make_balcony_dialog()
        preview_calls = []
        dialog.try_live_preview = lambda: (
            preview_calls.append(True) or True
        )
        dialog.update_enabled_state = lambda: None
        boxes[0].Text = "110"
        dialog.on_text_box_text_changed(boxes[0], None)
        dialog.on_text_box_key_down(
            boxes[0],
            _key_event(_FakeForms.Keys.Enter),
        )

        dialog.on_option_changed(None, None)
        self.assertFalse(dialog._enter_close_armed)
        dialog.on_text_box_key_down(
            boxes[0],
            _key_event(_FakeForms.Keys.Enter),
        )
        self.assertEqual(dialog.close_calls, [])

        dialog.on_text_box_key_down(
            boxes[0],
            _key_event(_FakeForms.Keys.Enter),
        )
        self.assertEqual(dialog.close_calls, [True])
        self.assertEqual(len(preview_calls), 3)

    def test_balcony_initial_unchanged_enter_may_close(self):
        dialog, boxes = self.make_balcony_dialog()
        ok_calls = []
        dialog.on_ok = lambda sender, args: ok_calls.append(
            (sender, args)
        )
        event = _key_event(_FakeForms.Keys.Enter)

        dialog.on_text_box_key_down(boxes[0], event)

        self.assertTrue(event.Handled)
        self.assertEqual(ok_calls, [(boxes[0], event)])

    def test_balcony_other_key_is_ignored(self):
        dialog, boxes = self.make_balcony_dialog()
        dialog.try_live_preview = lambda: self.fail(
            "preview should not run"
        )
        event = _key_event(object())

        dialog.on_text_box_key_down(boxes[0], event)

        self.assertFalse(event.Handled)
        self.assertEqual(dialog.close_calls, [])

    def test_section_edit_enter_applies_canonical_result_then_closes(self):
        callback_calls = []

        def callback(overrides):
            callback_calls.append(dict(overrides))
            canonical = overrides["main"] + 0.25
            return {
                "overrides": {"main": canonical},
                "sections": [
                    {
                        "key": "main",
                        "label": "Main floor",
                        "current_rise": canonical,
                        "editable": True,
                    },
                    {
                        "key": "fixed",
                        "label": "Fixed interval",
                        "current_rise": 50.0,
                        "editable": False,
                    },
                ],
            }

        dialog = self.make_section_dialog(callback)
        dialog.target_boxes["main"].Text = "110"

        first_event = _key_event(_FakeForms.Keys.Enter)
        dialog.on_target_box_key_down(
            dialog.target_boxes["main"],
            first_event,
        )

        self.assertTrue(first_event.Handled)
        self.assertEqual(callback_calls, [{"main": 110.0}])
        self.assertEqual(dialog.overrides, {"main": 110.25})
        self.assertEqual(dialog.target_boxes["main"].Text, "110.25")
        self.assertEqual(dialog.sections[0]["current_rise"], 110.25)
        self.assertEqual(
            dialog.current_labels["main"].Text,
            "current:110.25",
        )
        self.assertEqual(dialog.close_calls, [])
        self.assertFalse(dialog.accepted)

        second_event = _key_event(_FakeForms.Keys.Enter)
        dialog.on_target_box_key_down(
            dialog.target_boxes["main"],
            second_event,
        )

        self.assertTrue(second_event.Handled)
        self.assertEqual(len(callback_calls), 1)
        self.assertEqual(dialog.close_calls, [True])
        self.assertTrue(dialog.accepted)

    def test_section_reedit_restarts_apply_then_close_cycle(self):
        callback_calls = []

        def callback(overrides):
            callback_calls.append(dict(overrides))
            return dict(overrides)

        dialog = self.make_section_dialog(callback)
        dialog.target_boxes["main"].Text = "105"
        dialog.on_target_box_key_down(
            dialog.target_boxes["main"],
            _key_event(_FakeForms.Keys.Enter),
        )

        dialog.target_boxes["main"].Text = "108"
        dialog.on_target_box_key_down(
            dialog.target_boxes["main"],
            _key_event(_FakeForms.Keys.Enter),
        )

        self.assertEqual(
            callback_calls,
            [{"main": 105.0}, {"main": 108.0}],
        )
        self.assertEqual(dialog.close_calls, [])

        dialog.on_target_box_key_down(
            dialog.target_boxes["main"],
            _key_event(_FakeForms.Keys.Enter),
        )
        self.assertEqual(dialog.close_calls, [True])
        self.assertEqual(len(callback_calls), 2)

    def test_section_failed_apply_stays_open(self):
        callback_calls = []

        def callback(overrides):
            callback_calls.append(dict(overrides))
            return None

        dialog = self.make_section_dialog(callback)
        original_snapshot = dialog._enter_applied_snapshot
        dialog.target_boxes["main"].Text = "110"

        dialog.on_target_box_key_down(
            dialog.target_boxes["main"],
            _key_event(_FakeForms.Keys.Enter),
        )

        self.assertEqual(callback_calls, [{"main": 110.0}])
        self.assertEqual(dialog.close_calls, [])
        self.assertFalse(dialog.accepted)
        self.assertEqual(
            dialog._enter_applied_snapshot,
            original_snapshot,
        )
        self.assertEqual(len(_FakeMessageBox.calls), 1)

    def test_section_initial_unchanged_enter_closes(self):
        dialog = self.make_section_dialog(
            lambda overrides: self.fail("callback should not run")
        )
        event = _key_event(_FakeForms.Keys.Enter)

        dialog.on_target_box_key_down(
            dialog.target_boxes["main"],
            event,
        )

        self.assertTrue(event.Handled)
        self.assertEqual(dialog.close_calls, [True])
        self.assertTrue(dialog.accepted)

    def test_section_other_key_is_ignored(self):
        dialog = self.make_section_dialog(
            lambda overrides: self.fail("callback should not run")
        )
        event = _key_event(object())

        dialog.on_target_box_key_down(
            dialog.target_boxes["main"],
            event,
        )

        self.assertFalse(event.Handled)
        self.assertEqual(dialog.close_calls, [])
        self.assertFalse(dialog.accepted)


if __name__ == "__main__":
    unittest.main()
