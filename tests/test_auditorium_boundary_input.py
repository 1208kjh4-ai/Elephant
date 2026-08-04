# -*- coding: utf-8 -*-
"""Rhino-free tests for optional auditorium-boundary command input."""

import ast
import unittest
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]
RUNTIME_PATH = (
    ROOT
    / "commands"
    / "auditorium_generator"
    / "command_runtime.py"
)


def _load_functions(names, namespace):
    tree = ast.parse(
        RUNTIME_PATH.read_text(encoding="utf-8-sig"),
        str(RUNTIME_PATH),
    )
    wanted = set(names)
    nodes = [
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name in wanted
    ]
    if {node.name for node in nodes} != wanted:
        raise AssertionError("The requested runtime functions were not found.")
    module = ast.fix_missing_locations(
        ast.Module(body=nodes, type_ignores=[])
    )
    exec(compile(module, str(RUNTIME_PATH), "exec"), namespace)
    return tuple(namespace[name] for name in names)


class _Getter(object):
    def __init__(self, result, curve=None):
        self.result = result
        self.curve = curve
        self.prompt = None
        self.GeometryFilter = None
        self.accept_nothing = None
        self.object_indexes = []

    def SetCommandPrompt(self, prompt):
        self.prompt = prompt

    def AcceptNothing(self, accept):
        self.accept_nothing = accept

    def Get(self):
        return self.result

    def Object(self, index):
        self.object_indexes.append(index)
        if self.curve is None:
            return None
        return SimpleNamespace(Curve=lambda: self.curve)


class BoundarySelectorTests(unittest.TestCase):
    def make_selector(self, result, curve=None, normalizer=None):
        getter = _Getter(result, curve)
        nothing = object()
        selected = object()
        curve_filter = object()
        messages = []
        if result == "nothing":
            getter.result = nothing
        elif result == "object":
            getter.result = selected

        if normalizer is None:
            normalizer = lambda source, datum, tolerance: source

        rhino = SimpleNamespace(
            DocObjects=SimpleNamespace(
                ObjectType=SimpleNamespace(Curve=curve_filter)
            ),
            Input=SimpleNamespace(
                GetResult=SimpleNamespace(
                    Nothing=nothing,
                    Object=selected,
                )
            ),
            UI=SimpleNamespace(
                Dialogs=SimpleNamespace(
                    ShowMessageBox=lambda *args: messages.append(args)
                )
            ),
        )
        namespace = {
            "Rhino": rhino,
            "ric": SimpleNamespace(GetObject=lambda: getter),
            "normalize_boundary_curve": normalizer,
        }
        selector, = _load_functions(
            ("select_optional_auditorium_boundary",),
            namespace,
        )
        doc = SimpleNamespace(ModelAbsoluteTolerance=0.01)
        return selector, getter, curve_filter, messages, doc

    def test_enter_skips_boundary_and_preserves_command(self):
        normalizer_calls = []
        selector, getter, curve_filter, _messages, doc = self.make_selector(
            "nothing",
            normalizer=lambda *args: normalizer_calls.append(args),
        )

        self.assertEqual((True, None), selector(doc, "datum"))
        self.assertTrue(getter.accept_nothing)
        self.assertIs(curve_filter, getter.GeometryFilter)
        self.assertIn("Enter", getter.prompt)
        self.assertEqual([], normalizer_calls)

    def test_cancel_or_get_failure_stops_command(self):
        selector, getter, _filter, _messages, doc = self.make_selector(
            object()
        )

        self.assertEqual((False, None), selector(doc, "datum"))
        self.assertEqual([], getter.object_indexes)

    def test_valid_curve_is_normalized_with_datum_and_tolerance(self):
        source_curve = object()
        normalized_curve = object()
        calls = []

        def normalize(curve, datum, tolerance):
            calls.append((curve, datum, tolerance))
            return normalized_curve

        selector, getter, _filter, messages, doc = self.make_selector(
            "object",
            source_curve,
            normalize,
        )

        self.assertEqual(
            (True, normalized_curve),
            selector(doc, "datum-point"),
        )
        self.assertEqual([(source_curve, "datum-point", 0.01)], calls)
        self.assertEqual([0], getter.object_indexes)
        self.assertEqual([], messages)

    def test_invalid_curve_reports_error_and_stops_command(self):
        def reject_curve(_curve, _datum, _tolerance):
            raise ValueError("Boundary must be closed.")

        selector, _getter, _filter, messages, doc = self.make_selector(
            "object",
            object(),
            reject_curve,
        )

        self.assertEqual((False, None), selector(doc, "datum"))
        self.assertEqual(1, len(messages))
        self.assertIn("Boundary must be closed.", messages[0][0])


class BoundaryMainWiringTests(unittest.TestCase):
    def run_main(self):
        doc = SimpleNamespace(ModelAbsoluteTolerance=0.01)
        stage_data = {"audience_datum_point": "datum"}
        log = []
        captured = {}

        class Dialog(object):
            def __init__(self, received_stage_data, received_doc, seat_source):
                captured["stage_data"] = received_stage_data
                captured["doc"] = received_doc
                captured["seat_source"] = seat_source
                self.accepted = True
                self.preview_data = "preview"

            def disable_preview(self):
                log.append("disable")

        def select_baseline(received_doc):
            log.append("baseline")
            self.assertIs(doc, received_doc)
            return "left", "right"

        def analyze(left, right, received_doc):
            log.append("analyze")
            self.assertEqual(("left", "right", doc), (left, right, received_doc))
            return stage_data

        namespace = {
            "Rhino": SimpleNamespace(
                RhinoDoc=SimpleNamespace(ActiveDoc=doc),
                UI=SimpleNamespace(
                    Dialogs=SimpleNamespace(ShowMessageBox=lambda *args: None)
                ),
            ),
            "select_reference_baseline": select_baseline,
            "analyze_reference_baseline": analyze,
            "load_auditorium_seat_source": lambda: log.append("seat") or "seat",
            "AuditoriumDialog": Dialog,
            "show_dialog_semi_modal": lambda dialog, received_doc: log.append(
                "dialog"
            ),
            "bake_preview": lambda preview, received_doc: log.append("bake"),
        }
        main, = _load_functions(("main",), namespace)
        main()
        return stage_data, log, captured

    def test_dialog_receives_boundary_free_stage_data_after_analysis(self):
        stage_data, log, captured = self.run_main()

        self.assertNotIn("auditorium_boundary_curve", stage_data)
        self.assertIs(stage_data, captured["stage_data"])
        self.assertLess(log.index("analyze"), log.index("seat"))
        self.assertIn("bake", log)

    def test_runtime_has_no_pre_dialog_boundary_prompt(self):
        stage_data, log, captured = self.run_main()

        self.assertNotIn("auditorium_boundary_curve", stage_data)
        self.assertIs(stage_data, captured["stage_data"])
        self.assertEqual(
            ["baseline", "analyze", "seat", "dialog", "disable", "bake"],
            log,
        )


if __name__ == "__main__":
    unittest.main()
