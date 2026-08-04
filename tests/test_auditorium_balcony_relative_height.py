# -*- coding: utf-8 -*-
"""Rhino-free regressions for stalls-relative balcony heights."""

import ast
import copy
import inspect
import unittest
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]
PACKAGE_ROOT = ROOT / "commands" / "auditorium_generator"
HEIGHT_REFERENCE_PATH = PACKAGE_ROOT / "balcony_height_reference.py"
MAIN_DIALOG_PATH = PACKAGE_ROOT / "main_dialog.py"
PREVIEW_GEOMETRY_PATH = PACKAGE_ROOT / "preview_geometry.py"
BALCONY_DIALOG_PATH = PACKAGE_ROOT / "balcony_settings_dialog.py"

HEIGHT_HELPER_NAME = "rebase_balcony_last_platform_z"
BALCONY_HEIGHT_KEYS = (
    "balcony_last_platform_z",
    "balcony2_last_platform_z",
)
EXPECTED_DEFAULT_OFFSETS = (5000.0, 10000.0)


def _parse(path):
    return ast.parse(path.read_text(encoding="utf-8"), str(path))


def _top_level_assignment(tree, name):
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        if any(
            isinstance(target, ast.Name) and target.id == name
            for target in node.targets
        ):
            return ast.literal_eval(node.value)
    raise AssertionError("{0} was not found.".format(name))


def _top_level_literal_dict(tree, name):
    """Read literal entries while ignoring unrelated named constants."""
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        if not any(
            isinstance(target, ast.Name) and target.id == name
            for target in node.targets
        ):
            continue
        if not isinstance(node.value, ast.Dict):
            raise AssertionError("{0} is not a dictionary.".format(name))
        result = {}
        for key_node, value_node in zip(
            node.value.keys,
            node.value.values,
        ):
            key = ast.literal_eval(key_node)
            try:
                value = ast.literal_eval(value_node)
            except (TypeError, ValueError):
                continue
            result[key] = value
        return result
    raise AssertionError("{0} was not found.".format(name))


def _optional_top_level_assignment(tree, name):
    try:
        return _top_level_assignment(tree, name)
    except AssertionError:
        return None


def _function_node(tree, name):
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise AssertionError("{0} was not found.".format(name))


def _method_node(tree, class_name, method_name):
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
        "{0}.{1} was not found.".format(class_name, method_name)
    )


def _load_pure_function(path, name):
    tree = _parse(path)
    node = copy.deepcopy(_function_node(tree, name))
    module = ast.Module(body=[node], type_ignores=[])
    ast.fix_missing_locations(module)
    namespace = {}
    exec(compile(module, str(path), "exec"), namespace)
    return namespace[name]


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


def _self_values_key(target):
    if not isinstance(target, ast.Subscript):
        return None
    owner = target.value
    if not (
        isinstance(owner, ast.Attribute)
        and owner.attr == "values"
        and isinstance(owner.value, ast.Name)
        and owner.value.id == "self"
    ):
        return None
    key_node = target.slice
    if isinstance(key_node, ast.Constant) and isinstance(
        key_node.value, str
    ):
        return key_node.value
    return None


def _assigned_self_value_keys(node):
    keys = set()
    for child in ast.walk(node):
        if not isinstance(child, (ast.Assign, ast.AnnAssign)):
            continue
        targets = (
            child.targets
            if isinstance(child, ast.Assign)
            else [child.target]
        )
        for target in targets:
            key = _self_values_key(target)
            if key is not None:
                keys.add(key)
    return keys


def _run_fresh_balcony_initializers(defaults):
    """Run only the two per-tier legacy initializer guards."""
    tree = _parse(MAIN_DIALOG_PATH)
    init_node = _method_node(tree, "AuditoriumDialog", "__init__")
    statements = [
        copy.deepcopy(node)
        for node in init_node.body
        if (
            isinstance(node, ast.If)
            and (
                _contains_string(node.test, "balcony_settings_version")
                or _contains_string(
                    node.test,
                    "balcony2_settings_version",
                )
            )
        )
    ]
    if len(statements) < 2:
        raise AssertionError(
            "Both per-tier balcony initializer guards are required."
        )

    module = ast.Module(body=statements, type_ignores=[])
    ast.fix_missing_locations(module)
    state = SimpleNamespace(
        values=dict(defaults),
        opening_height_mm=4500.0,
    )
    namespace = {
        "self": state,
        "saved": {},
        "DEFAULTS": defaults,
        "standard_balcony_railing_height": lambda _t: 750.0,
    }
    exec(compile(module, str(MAIN_DIALOG_PATH), "exec"), namespace)
    return state.values


class BalconyRelativeHeightHelperTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.helper = _load_pure_function(
            HEIGHT_REFERENCE_PATH,
            HEIGHT_HELPER_NAME,
        )

    def resolve(self, stored_offset, raw_rear_z, effective_rear_z):
        """Exercise the compatibility composition used by the preview."""
        return type(self).helper(
            stored_offset + raw_rear_z,
            raw_rear_z,
            effective_rear_z,
        )

    def test_compatibility_helper_preserves_the_relative_offset(self):
        self.assertEqual(
            3,
            len(inspect.signature(type(self).helper).parameters),
        )

        for stored_offset in (5000.0, 10000.0):
            cases = (
                (-1100.0, -1100.0),
                (2500.0, 3880.0),
                (4300.0, 3880.0),
                (3880.0, 7425.25),
            )
            for raw_rear_z, effective_rear_z in cases:
                resolved_z = self.resolve(
                    stored_offset,
                    raw_rear_z,
                    effective_rear_z,
                )
                self.assertAlmostEqual(
                    stored_offset,
                    resolved_z - effective_rear_z,
                )

    def test_stalls_rear_change_moves_both_balconies_by_same_delta(self):
        rear_before = 3880.0
        rear_after = 4725.5
        expected_delta = rear_after - rear_before

        for stored_offset in EXPECTED_DEFAULT_OFFSETS:
            before = self.resolve(
                stored_offset,
                3200.0,
                rear_before,
            )
            after = self.resolve(
                stored_offset,
                4975.0,
                rear_after,
            )
            self.assertAlmostEqual(expected_delta, after - before)
            self.assertAlmostEqual(stored_offset, before - rear_before)
            self.assertAlmostEqual(stored_offset, after - rear_after)

    def test_repeated_preview_resolution_has_no_drift(self):
        for stored_offset in EXPECTED_DEFAULT_OFFSETS:
            results = [
                self.resolve(stored_offset, 4876.5, 6123.456)
                for _unused in range(5)
            ]
            self.assertEqual([results[0]] * len(results), results)
            self.assertEqual(stored_offset, results[0] - 6123.456)


class BalconyRelativeHeightDefaultsAndMigrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tree = _parse(MAIN_DIALOG_PATH)
        cls.defaults = _top_level_literal_dict(cls.tree, "DEFAULTS")

    def test_default_offsets_are_5000_and_10000(self):
        actual = tuple(
            float(self.defaults[key]) for key in BALCONY_HEIGHT_KEYS
        )
        self.assertEqual(EXPECTED_DEFAULT_OFFSETS, actual)

    def test_fresh_initialization_does_not_replace_relative_defaults(self):
        initialized = _run_fresh_balcony_initializers(self.defaults)
        actual = tuple(
            float(initialized[key]) for key in BALCONY_HEIGHT_KEYS
        )
        self.assertEqual(EXPECTED_DEFAULT_OFFSETS, actual)

    def test_height_storage_semantics_have_an_explicit_migration_guard(self):
        defaults_version = _top_level_assignment(
            self.tree,
            "AUDITORIUM_DEFAULTS_VERSION",
        )
        storage_version = _optional_top_level_assignment(
            self.tree,
            "BALCONY_HEIGHT_STORAGE_VERSION",
        )
        self.assertTrue(
            defaults_version >= 10
            or (
                storage_version is not None
                and float(storage_version) >= 1.0
            ),
            "Changing stored absolute Z values into relative offsets "
            "requires a sticky-data version bump.",
        )

        init_node = _method_node(
            self.tree,
            "AuditoriumDialog",
            "__init__",
        )
        migration_keys = set()
        for node in ast.walk(init_node):
            if not isinstance(node, ast.If):
                continue
            if not (
                _contains_string(
                    node.test,
                    "auditorium_defaults_version",
                )
                or _contains_string(
                    node.test,
                    "balcony_height_storage_version",
                )
            ):
                continue
            migration_keys.update(_assigned_self_value_keys(node))

        self.assertTrue(
            set(BALCONY_HEIGHT_KEYS).issubset(migration_keys),
            "Legacy absolute balcony heights must be converted or reset "
            "before they can be interpreted as relative offsets.",
        )


class BalconyRelativeHeightWiringTests(unittest.TestCase):
    def test_preview_resolves_both_tiers_from_effective_stalls_rear(self):
        tree = _parse(PREVIEW_GEOMETRY_PATH)
        preview = _function_node(tree, "build_preview_geometry")
        helper_calls = _calls_named(preview, HEIGHT_HELPER_NAME)

        self.assertEqual(2, len(helper_calls))
        for call in helper_calls:
            self.assertEqual(3, len(call.args))
            self.assertIsInstance(call.args[0], ast.BinOp)
            self.assertIsInstance(call.args[0].op, ast.Add)
            self.assertTrue(
                _contains_string(
                    call.args[0],
                    "balcony_last_platform_z",
                )
            )
            first_arg_names = {
                node.id
                for node in ast.walk(call.args[0])
                if isinstance(node, ast.Name)
            }
            self.assertIn("stalls_reference_z", first_arg_names)
            self.assertIsInstance(call.args[1], ast.Name)
            self.assertEqual(
                "stalls_reference_z",
                call.args[1].id,
            )
            self.assertIsInstance(call.args[2], ast.Name)
            self.assertEqual(
                "effective_stalls_rear_z",
                call.args[2].id,
            )

        self.assertEqual(
            1,
            len(_calls_named(preview, "stalls_height_reference_z")),
        )

    def test_settings_dialog_stores_offset_without_double_conversion(self):
        tree = _parse(BALCONY_DIALOG_PATH)
        init_node = _method_node(tree, "BalconySettingsDialog", "__init__")
        read_values = _method_node(
            tree,
            "BalconySettingsDialog",
            "read_values",
        )
        maximum_row_params = _method_node(
            tree,
            "BalconySettingsDialog",
            "maximum_row_params",
        )

        self.assertFalse(
            _calls_named(init_node, "balcony_height_from_stalls_rear")
        )
        self.assertFalse(
            _calls_named(read_values, "balcony_height_to_absolute")
        )

        helper_calls = _calls_named(
            maximum_row_params,
            HEIGHT_HELPER_NAME,
        )
        self.assertEqual(1, len(helper_calls))
        self.assertEqual(3, len(helper_calls[0].args))
        self.assertIsInstance(helper_calls[0].args[0], ast.BinOp)
        self.assertIsInstance(helper_calls[0].args[0].op, ast.Add)
        first_arg_attributes = {
            node.attr
            for node in ast.walk(helper_calls[0].args[0])
            if isinstance(node, ast.Attribute)
        }
        self.assertIn("stalls_rear_z", first_arg_attributes)
        self.assertTrue(
            any(
                isinstance(node, ast.Attribute)
                and node.attr == "stalls_rear_z"
                for node in ast.walk(helper_calls[0].args[1])
            )
        )
        self.assertTrue(
            any(
                isinstance(node, ast.Attribute)
                and node.attr == "effective_stalls_rear_z"
                for node in ast.walk(helper_calls[0].args[2])
            )
        )


if __name__ == "__main__":
    unittest.main()
