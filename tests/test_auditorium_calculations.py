# -*- coding: utf-8 -*-
"""Characterization tests for the extracted auditorium calculations.

The Rhino-dependent command module cannot be imported by ordinary CPython.
Instead, this suite parses the frozen ``TTest.py`` command and executes only
the constants and functions that were moved to the Rhino-independent
calculation modules.
"""

import ast
import copy
import hashlib
import inspect
import math
import os
import sys
import symtable
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from commands.auditorium_generator.calculations import seating
from commands.auditorium_generator.calculations import sections
from commands.auditorium_generator.calculations import stage
from commands.auditorium_generator import balcony_height_reference
from commands.auditorium_generator import formatting
from commands.auditorium_generator import geometry_metadata


TTEST_PATH = ROOT / "commands" / "TTest.py"
AUDITORIUM_PATH = ROOT / "commands" / "Auditorium.py"
SECTIONS_PATH = (
    ROOT
    / "commands"
    / "auditorium_generator"
    / "calculations"
    / "sections.py"
)
STAGE_PATH = (
    ROOT
    / "commands"
    / "auditorium_generator"
    / "calculations"
    / "stage.py"
)
SEATING_PATH = (
    ROOT
    / "commands"
    / "auditorium_generator"
    / "calculations"
    / "seating.py"
)
CONSTANTS_PATH = (
    ROOT
    / "commands"
    / "auditorium_generator"
    / "constants.py"
)
FORMATTING_PATH = (
    ROOT
    / "commands"
    / "auditorium_generator"
    / "formatting.py"
)
GEOMETRY_METADATA_PATH = (
    ROOT
    / "commands"
    / "auditorium_generator"
    / "geometry_metadata.py"
)
RHINO_PRIMITIVES_PATH = (
    ROOT
    / "commands"
    / "auditorium_generator"
    / "rhino_primitives.py"
)
OPENING_GEOMETRY_PATH = (
    ROOT
    / "commands"
    / "auditorium_generator"
    / "opening_geometry.py"
)
PREVIEW_PALETTE_PATH = (
    ROOT
    / "commands"
    / "auditorium_generator"
    / "preview_palette.py"
)
STAGE_PREVIEW_GEOMETRY_PATH = (
    ROOT
    / "commands"
    / "auditorium_generator"
    / "stage_preview_geometry.py"
)
SECTION_PREVIEW_ANNOTATIONS_PATH = (
    ROOT
    / "commands"
    / "auditorium_generator"
    / "section_preview_annotations.py"
)
PREVIEW_CONDUIT_PATH = (
    ROOT
    / "commands"
    / "auditorium_generator"
    / "preview_conduit.py"
)
PREVIEW_MESH_GEOMETRY_PATH = (
    ROOT
    / "commands"
    / "auditorium_generator"
    / "preview_mesh_geometry.py"
)
CHAIR_PREVIEW_GEOMETRY_PATH = (
    ROOT
    / "commands"
    / "auditorium_generator"
    / "chair_preview_geometry.py"
)
BALCONY_PREVIEW_GEOMETRY_PATH = (
    ROOT
    / "commands"
    / "auditorium_generator"
    / "balcony_preview_geometry.py"
)
SEAT_PREVIEW_GEOMETRY_PATH = (
    ROOT
    / "commands"
    / "auditorium_generator"
    / "seat_preview_geometry.py"
)
PREVIEW_GEOMETRY_PATH = (
    ROOT
    / "commands"
    / "auditorium_generator"
    / "preview_geometry.py"
)
BALCONY_HEIGHT_REFERENCE_PATH = (
    ROOT
    / "commands"
    / "auditorium_generator"
    / "balcony_height_reference.py"
)
SEAT_SOURCE_PATH = (
    ROOT
    / "commands"
    / "auditorium_generator"
    / "seat_source.py"
)
FLOOR_SURFACE_GEOMETRY_PATH = (
    ROOT
    / "commands"
    / "auditorium_generator"
    / "floor_surface_geometry.py"
)
DOCUMENT_BAKING_PATH = (
    ROOT
    / "commands"
    / "auditorium_generator"
    / "document_baking.py"
)
SECTION_RESULT_DIALOGS_PATH = (
    ROOT
    / "commands"
    / "auditorium_generator"
    / "section_result_dialogs.py"
)
SECTION_INTERPOLATION_CONSTANTS_PATH = (
    ROOT
    / "commands"
    / "auditorium_generator"
    / "section_interpolation_constants.py"
)
PROSCENIUM_SETTINGS_DIALOG_PATH = (
    ROOT
    / "commands"
    / "auditorium_generator"
    / "proscenium_settings_dialog.py"
)
BALCONY_SETTINGS_DIALOG_PATH = (
    ROOT
    / "commands"
    / "auditorium_generator"
    / "balcony_settings_dialog.py"
)
MAIN_DIALOG_PATH = (
    ROOT
    / "commands"
    / "auditorium_generator"
    / "main_dialog.py"
)
COMMAND_RUNTIME_PATH = (
    ROOT
    / "commands"
    / "auditorium_generator"
    / "command_runtime.py"
)
AUDITORIUM_GENERATOR_INIT_PATH = (
    ROOT
    / "commands"
    / "auditorium_generator"
    / "__init__.py"
)
EXPECTED_TTEST_SHA256 = (
    "d4ee2852287635cabe48a0bc717719cbbb9213e35dac7e2b2ea89803327adc32"
)

MOVED_FUNCTION_NAMES = (
    "is_finite_number",
    "ceil_to_integer_mm",
    "calculate_actual_sightline_status",
    "validate_section_rise_target",
    "interpolate_front_anchored_z_values",
    "interpolate_rear_anchored_z_values",
    "rebuild_stalls_vertical_fields",
    "add_stalls_ceiling_validation",
    "apply_stalls_rise_interpolation",
    "stalls_solver_signature",
    "balcony_solver_signature",
    "section_solver_signatures",
    "balcony_result_is_displayable",
    "calculate_section",
    "standard_balcony_railing_height",
    "balcony_height_from_stalls_rear",
    "balcony_height_to_absolute",
    "normalized_balcony_tier_params",
    "calculate_balcony_spatial_max_rows",
    "calculate_balcony_max_rows",
    "calculate_balcony_section",
    "rebuild_balcony_vertical_fields",
    "apply_balcony_rise_interpolation",
)

SECOND_WAVE_STAGE_FUNCTION_NAMES = (
    "calculated_proscenium_defaults",
    "validate_proscenium_params",
    "calculate_stage_section_dimensions",
)

SECOND_WAVE_SEATING_FUNCTION_NAMES = (
    "calculate_3d_seat_placements",
    "calculate_total_3d_seat_count",
    "calculate_seat_layout_width",
)

SECOND_WAVE_FUNCTION_NAMES = (
    SECOND_WAVE_STAGE_FUNCTION_NAMES
    + SECOND_WAVE_SEATING_FUNCTION_NAMES
)

THIRD_WAVE_FORMATTING_FUNCTION_NAMES = (
    "format_riser_height_label",
    "format_section_height_dimension",
)

THIRD_WAVE_GEOMETRY_FUNCTION_NAMES = (
    "section_floor_surface_name",
    "stage_space_envelope_name",
    "stage_space_top_z",
    "stage_edge_adjacencies",
)

THIRD_WAVE_FUNCTION_NAMES = (
    THIRD_WAVE_FORMATTING_FUNCTION_NAMES
    + THIRD_WAVE_GEOMETRY_FUNCTION_NAMES
)

FOURTH_WAVE_PRIMITIVE_FUNCTION_NAMES = (
    "unit_scale_from_mm",
    "point_at",
    "line_curve",
    "stage_space_point",
    "build_plan_rectangle",
    "get_stage_directions",
)

FOURTH_WAVE_OPENING_FUNCTION_NAMES = (
    "get_curve_plane",
    "analyze_opening_rectangle",
)

FOURTH_WAVE_FUNCTION_NAMES = (
    FOURTH_WAVE_PRIMITIVE_FUNCTION_NAMES
    + FOURTH_WAVE_OPENING_FUNCTION_NAMES
)

FIFTH_WAVE_FUNCTION_NAMES = (
    "calculate_proscenium_space_layout",
    "build_proscenium_plan_curves",
    "build_stage_space_3d_curves",
    "build_stage_section_2d_curves",
    "build_stage_audience_transition_curves",
)

SIXTH_WAVE_FUNCTION_NAMES = (
    "build_riser_height_preview_labels",
    "build_section_height_dimension_preview",
)

PREVIEW_MESH_FUNCTION_NAMES = (
    "append_geometry_to_mesh",
    "build_seat_source_preview_mesh",
)

CHAIR_PREVIEW_DATA_NAMES = (
    "CHAIR_LINE_DATA",
    "CHAIR_ARC_DATA",
)

CHAIR_PREVIEW_FUNCTION_NAMES = (
    "build_chair_curves",
)

BALCONY_PREVIEW_FUNCTION_NAMES = (
    "append_balcony_tier_geometry",
)

SEAT_PREVIEW_CONSTANT_NAMES = (
    "SEAT_SOURCE_CHAIR_WIDTH",
    "SEAT_SOURCE_ARMREST_WIDTH",
)

SEAT_PREVIEW_FUNCTION_NAMES = (
    "seat_module_transform",
    "build_3d_seat_module_geometry",
)

PREVIEW_GEOMETRY_FUNCTION_NAMES = (
    "build_preview_geometry",
)

BALCONY_HEIGHT_REFERENCE_FUNCTION_NAMES = (
    "stalls_height_reference_z",
    "rebase_balcony_last_platform_z",
)

SEAT_SOURCE_FUNCTION_NAMES = (
    "auditorium_seat_source_path",
    "duplicate_file3dm_geometry",
    "file3dm_definition_geometry",
    "geometry_collection_bounding_box",
    "source_component_candidate",
    "compact_component_name",
    "component_name_kind",
    "choose_seat_source_components",
    "normalize_seat_source_component",
    "load_auditorium_seat_source",
)

FLOOR_SURFACE_FUNCTION_NAMES = (
    "extrude_section_curve_across_width",
    "append_floor_surface",
    "create_stage_vertical_face",
    "append_stage_envelope_surfaces",
    "append_understage_envelope_surfaces",
    "build_floor_surface_geometry",
)

DOCUMENT_BAKING_FUNCTION_NAMES = (
    "create_attributes",
    "ensure_seat_instance_definition",
    "bake_preview",
)

SECTION_RESULT_DIALOG_CLASS_NAMES = (
    "SectionDimensionInterpolationDialog",
    "CalculatedResultDialog",
)

SECTION_RESULT_DIALOG_CONSTANT_NAMES = (
    "SECTION_RISE_KEYS",
    "SECTION_INTERPOLATION_WARNING_RATIO",
)

SETTINGS_DIALOG_CLASS_NAMES = (
    "ProsceniumSettingsDialog",
    "BalconySettingsDialog",
)

SETTINGS_DIALOG_CONSTANT_NAMES = (
    "PROSCENIUM_PARAM_KEYS",
    "BALCONY_SETTINGS_VERSION",
)

MAIN_DIALOG_CONSTANT_NAMES = (
    "STICKY_KEY",
    "PROSCENIUM_SETTINGS_VERSION",
    "AUDITORIUM_DEFAULTS_VERSION",
    "DEFAULT_FIRST_PLATFORM_START_DISTANCE",
    "CHAIR_SIGHT_POINT_Z",
    "MAXIMUM_3D_CHAIR_COUNT",
    "BALCONY_PARAM_KEYS",
    "DEFAULTS",
)

COMMAND_RUNTIME_FUNCTION_NAMES = (
    "select_opening_curve",
    "show_dialog_semi_modal",
    "main",
)

PREVIEW_PALETTE_NAMES = (
    "PREVIEW_FLOOR",
    "PREVIEW_SEAT",
    "PREVIEW_SIGHT",
    "PREVIEW_POINT",
    "PREVIEW_WARNING",
    "PREVIEW_REFERENCE",
    "PREVIEW_FULL_STAGE_SIGHT",
    "PREVIEW_MAIN_STAGE",
    "PREVIEW_AUX_STAGE",
    "PREVIEW_STAGE_CLEARANCE",
    "PREVIEW_STAGE_SECTION",
    "PREVIEW_GRID",
    "PREVIEW_UNDERSTAGE",
    "PREVIEW_AUDITORIUM_CEILING",
    "PREVIEW_STAGE_APRON",
    "PREVIEW_ORCHESTRA_PIT",
    "PREVIEW_AISLE",
    "PREVIEW_BALCONY",
    "PREVIEW_BALCONY_SECOND",
    "PREVIEW_BALCONY_RAIL",
    "PREVIEW_SECTION_DIMENSION",
    "PREVIEW_3D_CHAIR",
    "PREVIEW_3D_ARMREST",
    "FLOOR_SURFACE_PREVIEW_TRANSPARENCY",
)

ORACLE_FUNCTION_NAMES = (
    MOVED_FUNCTION_NAMES
    + SECOND_WAVE_FUNCTION_NAMES
    + THIRD_WAVE_FUNCTION_NAMES
    + FOURTH_WAVE_FUNCTION_NAMES
    + FIFTH_WAVE_FUNCTION_NAMES
    + SIXTH_WAVE_FUNCTION_NAMES
    + PREVIEW_MESH_FUNCTION_NAMES
    + CHAIR_PREVIEW_FUNCTION_NAMES
    + BALCONY_PREVIEW_FUNCTION_NAMES
    + SEAT_PREVIEW_FUNCTION_NAMES
    + SEAT_SOURCE_FUNCTION_NAMES
    + FLOOR_SURFACE_FUNCTION_NAMES
    + DOCUMENT_BAKING_FUNCTION_NAMES
)

SECTION_ORACLE_CONSTANT_NAMES = {
    "AISLE_STAIR_TARGET_RISER_HEIGHT",
    "BALCONY_TIER_KEY_MAPS",
    "CHAIR_FRONT_X",
    "CHAIR_SIGHT_POINT_X",
    "CHAIR_TOP_Z",
}

STAGE_ORACLE_CONSTANT_NAMES = {
    "STAGE_EQUIPMENT_CLEARANCE",
}

SEAT_PREVIEW_ORACLE_CONSTANT_NAMES = set(
    SEAT_PREVIEW_CONSTANT_NAMES
)

ORACLE_CONSTANT_NAMES = (
    SECTION_ORACLE_CONSTANT_NAMES
    | STAGE_ORACLE_CONSTANT_NAMES
    | SEAT_PREVIEW_ORACLE_CONSTANT_NAMES
)


def _assigned_names(node):
    names = set()
    for target in node.targets:
        if isinstance(target, ast.Name):
            names.add(target.id)
        elif isinstance(target, (ast.Tuple, ast.List)):
            names.update(
                item.id
                for item in target.elts
                if isinstance(item, ast.Name)
            )
    return names


def _parse(path):
    return ast.parse(
        path.read_text(encoding="utf-8-sig"),
        filename=str(path),
    )


def _function_nodes(tree):
    return {
        node.name: node
        for node in tree.body
        if isinstance(node, ast.FunctionDef)
    }


def _class_nodes(tree):
    return {
        node.name: node
        for node in tree.body
        if isinstance(node, ast.ClassDef)
    }


def _assignment_nodes(tree):
    assignments = {}
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        for name in _assigned_names(node):
            assignments[name] = node
    return assignments


def _load_selected_functions(tree, names, namespace):
    """Execute selected definitions with caller-provided fake dependencies."""
    body = [
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name in names
    ]
    selected = ast.fix_missing_locations(
        ast.Module(body=body, type_ignores=[])
    )
    loaded = dict(namespace)
    loaded["__builtins__"] = __builtins__
    exec(compile(selected, "<selected-functions>", "exec"), loaded)

    missing = set(names) - set(loaded)
    if missing:
        raise AssertionError(
            "Selected function extraction is incomplete: {0}".format(
                sorted(missing)
            )
        )
    return loaded


def _load_selected_class(tree, name, namespace):
    """Execute one class definition with caller-provided fake dependencies."""
    class_node = _class_nodes(tree)[name]
    selected = ast.fix_missing_locations(
        ast.Module(body=[class_node], type_ignores=[])
    )
    loaded = dict(namespace)
    loaded["__builtins__"] = __builtins__
    exec(compile(selected, "<selected-class>", "exec"), loaded)
    return loaded[name]


def _load_ttest_oracle():
    """Execute only the selected Rhino-free declarations from TTest.py."""
    tree = _parse(TTEST_PATH)
    body = []
    for node in tree.body:
        if (
            isinstance(node, ast.Assign)
            and _assigned_names(node) & ORACLE_CONSTANT_NAMES
        ):
            body.append(node)
        elif (
            isinstance(node, ast.FunctionDef)
            and node.name in ORACLE_FUNCTION_NAMES
        ):
            body.append(node)

    extracted = ast.fix_missing_locations(
        ast.Module(body=body, type_ignores=[])
    )
    namespace = {
        "__builtins__": __builtins__,
        "math": math,
    }
    exec(compile(extracted, str(TTEST_PATH), "exec"), namespace)

    missing_functions = set(ORACLE_FUNCTION_NAMES) - set(namespace)
    missing_constants = ORACLE_CONSTANT_NAMES - set(namespace)
    if missing_functions or missing_constants:
        raise AssertionError(
            "TTest oracle extraction is incomplete: functions={0}, "
            "constants={1}".format(
                sorted(missing_functions),
                sorted(missing_constants),
            )
        )
    return namespace, tree


def _function(namespace, name):
    if isinstance(namespace, dict):
        return namespace[name]
    return getattr(namespace, name)


def _candidate_function(name):
    if name in SECOND_WAVE_STAGE_FUNCTION_NAMES:
        return getattr(stage, name)
    if name in SECOND_WAVE_SEATING_FUNCTION_NAMES:
        return getattr(seating, name)
    if name in THIRD_WAVE_FORMATTING_FUNCTION_NAMES:
        return getattr(formatting, name)
    if name in THIRD_WAVE_GEOMETRY_FUNCTION_NAMES:
        return getattr(geometry_metadata, name)
    return getattr(sections, name)


def _base_params(floor_type="stepped"):
    return {
        "stage_height": 1100.0,
        "first_row_distance": 7000.0,
        "row_pitch": 1100.0,
        "stage_sight_point_z": 50.0,
        "sight_point_z": 1123.991949,
        "sight_clearance": 113.0,
        "row_count": 15,
        "row_group_counts": [5, 5, 5],
        "aisle_width": 1000.0,
        "aisle_stair_tread_depth": 300.0,
        "max_slope_denominator": 12.0,
        "floor_type": floor_type,
        "balcony_enabled": True,
        "balcony_last_platform_z": 6000.0,
        "balcony_row_count": 4,
        "balcony_row_pitch": 1100.0,
        "balcony_railing_t": 250.0,
        "balcony_railing_w": 530.0,
        "balcony_railing_h": 750.0,
        "balcony_settings_version": 2,
        "balcony2_enabled": True,
        "balcony2_last_platform_z": 9000.0,
        "balcony2_row_count": 3,
        "balcony2_row_pitch": 1100.0,
        "balcony2_railing_t": 250.0,
        "balcony2_railing_w": 530.0,
        "balcony2_railing_h": 750.0,
        "balcony2_settings_version": 2,
    }


def _valid_stage_params():
    return {
        "stage_preview_mode": "section_2d",
        "main_stage_width": 20000.0,
        "main_stage_depth": 14400.0,
        "main_stage_height": 26000.0,
        "right_stage_enabled": True,
        "right_stage_width": 20000.0,
        "right_stage_depth": 14400.0,
        "right_stage_height": 10000.0,
        "left_stage_enabled": True,
        "left_stage_width": 20000.0,
        "left_stage_depth": 14400.0,
        "left_stage_height": 10000.0,
        "rear_stage_enabled": True,
        "rear_stage_width": 20000.0,
        "rear_stage_depth": 14400.0,
        "rear_stage_height": 10000.0,
        "understage_enabled": True,
        "understage_depth": 10000.0,
    }


def _seat_params(block_counts=None):
    return {
        "seat_module_width": 550.0,
        "longitudinal_aisle_width": 1200.0,
        "seat_block_counts": (
            [8, 16, 8]
            if block_counts is None
            else block_counts
        ),
    }


def _seat_section_result():
    return {
        "x_values": [8100.0, 9200.0],
        "base_z_values": [-1100.0, -900.0],
    }


def _capture(function, args, kwargs):
    call_args = copy.deepcopy(args)
    call_kwargs = copy.deepcopy(kwargs)
    try:
        value = function(*call_args, **call_kwargs)
    except Exception as error:
        outcome = {
            "kind": "error",
            "type": type(error).__name__,
            "args": error.args,
        }
    else:
        outcome = {
            "kind": "return",
            "value": value,
        }
    return outcome, call_args, call_kwargs


def _run_two_tier_pipeline(namespace):
    """Mirror the calculation and interpolation order used by the command."""
    params = _base_params()

    stalls = _function(namespace, "calculate_section")(params)
    stalls = _function(
        namespace,
        "apply_stalls_rise_interpolation",
    )(
        params,
        stalls,
        2800.0,
        16000.0,
    )

    tier1_params = _function(
        namespace,
        "normalized_balcony_tier_params",
    )(params, 0)
    balcony1 = _function(
        namespace,
        "calculate_balcony_section",
    )(
        tier1_params,
        stalls,
        8000.0,
        tier_index=0,
    )
    balcony1 = _function(
        namespace,
        "apply_balcony_rise_interpolation",
    )(
        tier1_params,
        balcony1,
        stalls,
        8000.0,
        800.0,
    )

    tier2_params = _function(
        namespace,
        "normalized_balcony_tier_params",
    )(params, 1)
    tier2_params["first_row_distance"] = balcony1["railing_front_x"]
    balcony2 = _function(
        namespace,
        "calculate_balcony_section",
    )(
        tier2_params,
        balcony1,
        8000.0,
        tier_index=1,
    )
    balcony2 = _function(
        namespace,
        "apply_balcony_rise_interpolation",
    )(
        tier2_params,
        balcony2,
        balcony1,
        8000.0,
        600.0,
    )

    return {
        "stalls": stalls,
        "balcony_1": balcony1,
        "balcony_2": balcony2,
        "signatures": _function(
            namespace,
            "section_solver_signatures",
        )(params),
    }


class AuditoriumCalculationParityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.oracle, cls.oracle_tree = _load_ttest_oracle()
        cls.candidate_tree = _parse(SECTIONS_PATH)
        cls.stage_tree = _parse(STAGE_PATH)
        cls.seating_tree = _parse(SEATING_PATH)
        cls.constants_tree = _parse(CONSTANTS_PATH)
        cls.formatting_tree = _parse(FORMATTING_PATH)
        cls.geometry_metadata_tree = _parse(GEOMETRY_METADATA_PATH)
        cls.rhino_primitives_tree = _parse(RHINO_PRIMITIVES_PATH)
        cls.opening_geometry_tree = _parse(OPENING_GEOMETRY_PATH)
        cls.preview_palette_tree = _parse(PREVIEW_PALETTE_PATH)
        cls.stage_preview_geometry_tree = _parse(
            STAGE_PREVIEW_GEOMETRY_PATH
        )
        cls.section_preview_annotations_tree = _parse(
            SECTION_PREVIEW_ANNOTATIONS_PATH
        )
        cls.preview_conduit_tree = _parse(PREVIEW_CONDUIT_PATH)
        cls.preview_mesh_geometry_tree = _parse(
            PREVIEW_MESH_GEOMETRY_PATH
        )
        cls.chair_preview_geometry_tree = _parse(
            CHAIR_PREVIEW_GEOMETRY_PATH
        )
        cls.balcony_preview_geometry_tree = _parse(
            BALCONY_PREVIEW_GEOMETRY_PATH
        )
        cls.seat_preview_geometry_tree = _parse(
            SEAT_PREVIEW_GEOMETRY_PATH
        )
        cls.preview_geometry_tree = _parse(
            PREVIEW_GEOMETRY_PATH
        )
        cls.balcony_height_reference_tree = _parse(
            BALCONY_HEIGHT_REFERENCE_PATH
        )
        cls.seat_source_tree = _parse(SEAT_SOURCE_PATH)
        cls.floor_surface_geometry_tree = _parse(
            FLOOR_SURFACE_GEOMETRY_PATH
        )
        cls.document_baking_tree = _parse(DOCUMENT_BAKING_PATH)
        cls.section_result_dialogs_tree = _parse(
            SECTION_RESULT_DIALOGS_PATH
        )
        cls.section_interpolation_constants_tree = _parse(
            SECTION_INTERPOLATION_CONSTANTS_PATH
        )
        cls.proscenium_settings_dialog_tree = _parse(
            PROSCENIUM_SETTINGS_DIALOG_PATH
        )
        cls.balcony_settings_dialog_tree = _parse(
            BALCONY_SETTINGS_DIALOG_PATH
        )
        cls.main_dialog_tree = _parse(MAIN_DIALOG_PATH)
        cls.command_runtime_tree = _parse(COMMAND_RUNTIME_PATH)
        cls.auditorium_generator_init_tree = _parse(
            AUDITORIUM_GENERATOR_INIT_PATH
        )
        cls.auditorium_tree = _parse(AUDITORIUM_PATH)

    def assert_deep_parity(self, reference, candidate, path="root"):
        self.assertIs(
            type(reference),
            type(candidate),
            "{0}: type differs ({1!r} != {2!r})".format(
                path,
                type(reference),
                type(candidate),
            ),
        )

        if isinstance(reference, dict):
            self.assertEqual(
                set(reference),
                set(candidate),
                "{0}: dict keys differ".format(path),
            )
            for key in reference:
                self.assert_deep_parity(
                    reference[key],
                    candidate[key],
                    "{0}[{1!r}]".format(path, key),
                )
            return

        if isinstance(reference, (list, tuple)):
            self.assertEqual(
                len(reference),
                len(candidate),
                "{0}: sequence length differs".format(path),
            )
            for index, (left, right) in enumerate(
                zip(reference, candidate)
            ):
                self.assert_deep_parity(
                    left,
                    right,
                    "{0}[{1}]".format(path, index),
                )
            return

        if isinstance(reference, float):
            if math.isnan(reference):
                self.assertTrue(
                    math.isnan(candidate),
                    "{0}: expected NaN".format(path),
                )
            else:
                self.assertEqual(
                    reference.hex(),
                    candidate.hex(),
                    "{0}: float differs".format(path),
                )
            return

        self.assertEqual(reference, candidate, "{0}: value differs".format(path))

    def assert_call_parity(self, function_name, *args, **kwargs):
        reference_capture = _capture(
            _function(self.oracle, function_name),
            args,
            kwargs,
        )
        candidate_capture = _capture(
            _candidate_function(function_name),
            args,
            kwargs,
        )
        self.assert_deep_parity(
            reference_capture,
            candidate_capture,
            function_name,
        )
        return reference_capture[0], candidate_capture[0]

    def assert_success_parity(self, function_name, *args, **kwargs):
        reference, candidate = self.assert_call_parity(
            function_name,
            *args,
            **kwargs
        )
        self.assertEqual("return", reference["kind"])
        return reference["value"], candidate["value"]

    def test_ttest_golden_hash_is_fixed(self):
        actual = hashlib.sha256(TTEST_PATH.read_bytes()).hexdigest()
        self.assertEqual(EXPECTED_TTEST_SHA256, actual)

    def test_extracted_modules_have_no_rhino_or_eto_imports(self):
        forbidden_roots = {"Rhino", "Eto", "scriptcontext", "System"}
        module_trees = {
            "sections": self.candidate_tree,
            "stage": self.stage_tree,
            "seating": self.seating_tree,
            "constants": self.constants_tree,
            "formatting": self.formatting_tree,
            "geometry_metadata": self.geometry_metadata_tree,
        }
        for module_name, tree in module_trees.items():
            with self.subTest(module=module_name):
                imported_roots = set()
                for node in ast.walk(tree):
                    if isinstance(node, ast.Import):
                        imported_roots.update(
                            alias.name.split(".", 1)[0]
                            for alias in node.names
                        )
                    elif isinstance(node, ast.ImportFrom) and node.module:
                        imported_roots.add(node.module.split(".", 1)[0])
                self.assertFalse(forbidden_roots & imported_roots)

    def test_all_23_moved_functions_keep_signature_and_ast(self):
        oracle_nodes = _function_nodes(self.oracle_tree)
        candidate_nodes = _function_nodes(self.candidate_tree)
        intentionally_changed = {
            "balcony_result_is_displayable",
            "calculate_section",
            "calculate_balcony_section",
        }
        self.assertEqual(23, len(MOVED_FUNCTION_NAMES))

        for name in MOVED_FUNCTION_NAMES:
            with self.subTest(function=name):
                self.assertIn(name, oracle_nodes)
                self.assertIn(name, candidate_nodes)
                self.assertEqual(
                    str(inspect.signature(_function(self.oracle, name))),
                    str(inspect.signature(_function(sections, name))),
                )
                oracle_ast = ast.dump(
                    oracle_nodes[name],
                    include_attributes=False,
                )
                candidate_ast = ast.dump(
                    candidate_nodes[name],
                    include_attributes=False,
                )
                if name in intentionally_changed:
                    self.assertNotEqual(oracle_ast, candidate_ast)
                else:
                    self.assertEqual(oracle_ast, candidate_ast)

        for constant_name in SECTION_ORACLE_CONSTANT_NAMES:
            with self.subTest(constant=constant_name):
                self.assert_deep_parity(
                    self.oracle[constant_name],
                    getattr(sections, constant_name),
                    constant_name,
                )

    def test_second_wave_functions_and_stage_constant_keep_parity(self):
        oracle_nodes = _function_nodes(self.oracle_tree)
        candidate_nodes = {}
        candidate_nodes.update(_function_nodes(self.stage_tree))
        candidate_nodes.update(_function_nodes(self.seating_tree))

        self.assertEqual(6, len(SECOND_WAVE_FUNCTION_NAMES))
        for name in SECOND_WAVE_FUNCTION_NAMES:
            with self.subTest(function=name):
                self.assertIn(name, oracle_nodes)
                self.assertIn(name, candidate_nodes)
                self.assertEqual(
                    str(inspect.signature(_function(self.oracle, name))),
                    str(inspect.signature(_candidate_function(name))),
                )
                self.assertEqual(
                    ast.dump(
                        oracle_nodes[name],
                        include_attributes=False,
                    ),
                    ast.dump(
                        candidate_nodes[name],
                        include_attributes=False,
                    ),
                )

        oracle_assignments = _assignment_nodes(self.oracle_tree)
        candidate_assignments = _assignment_nodes(self.stage_tree)
        constant_name = "STAGE_EQUIPMENT_CLEARANCE"
        self.assertEqual(
            ast.dump(
                oracle_assignments[constant_name],
                include_attributes=False,
            ),
            ast.dump(
                candidate_assignments[constant_name],
                include_attributes=False,
            ),
        )
        self.assertEqual(2000.0, self.oracle[constant_name])
        self.assertEqual(
            self.oracle[constant_name],
            stage.STAGE_EQUIPMENT_CLEARANCE,
        )

    def test_third_wave_functions_keep_signature_and_ast(self):
        oracle_nodes = _function_nodes(self.oracle_tree)
        candidate_nodes = {}
        candidate_nodes.update(_function_nodes(self.formatting_tree))
        candidate_nodes.update(
            _function_nodes(self.geometry_metadata_tree)
        )

        self.assertEqual(6, len(THIRD_WAVE_FUNCTION_NAMES))
        for name in THIRD_WAVE_FUNCTION_NAMES:
            with self.subTest(function=name):
                self.assertIn(name, oracle_nodes)
                self.assertIn(name, candidate_nodes)
                self.assertEqual(
                    str(inspect.signature(_function(self.oracle, name))),
                    str(inspect.signature(_candidate_function(name))),
                )
                self.assertEqual(
                    ast.dump(
                        oracle_nodes[name],
                        include_attributes=False,
                    ),
                    ast.dump(
                        candidate_nodes[name],
                        include_attributes=False,
                    ),
                )

    def test_fourth_wave_rhino_helpers_keep_signature_and_ast(self):
        oracle_nodes = _function_nodes(self.oracle_tree)
        primitive_nodes = _function_nodes(self.rhino_primitives_tree)
        opening_nodes = _function_nodes(self.opening_geometry_tree)
        candidate_nodes = {}
        candidate_nodes.update(primitive_nodes)
        candidate_nodes.update(opening_nodes)

        self.assertEqual(8, len(FOURTH_WAVE_FUNCTION_NAMES))
        for name in FOURTH_WAVE_FUNCTION_NAMES:
            with self.subTest(function=name):
                self.assertIn(name, oracle_nodes)
                self.assertIn(name, candidate_nodes)
                self.assertEqual(
                    ast.dump(
                        oracle_nodes[name].args,
                        include_attributes=False,
                    ),
                    ast.dump(
                        candidate_nodes[name].args,
                        include_attributes=False,
                    ),
                )
                self.assertEqual(
                    ast.dump(
                        oracle_nodes[name],
                        include_attributes=False,
                    ),
                    ast.dump(
                        candidate_nodes[name],
                        include_attributes=False,
                    ),
                )

        main_nodes = _function_nodes(self.auditorium_tree)
        for name in FOURTH_WAVE_FUNCTION_NAMES:
            self.assertNotIn(name, main_nodes)

        imported_names = {}
        for node in self.auditorium_tree.body:
            if not isinstance(node, ast.ImportFrom):
                continue
            imported_names.setdefault(node.module, set()).update(
                alias.asname or alias.name
                for alias in node.names
            )
        self.assertEqual(
            set(FOURTH_WAVE_PRIMITIVE_FUNCTION_NAMES),
            imported_names["auditorium_generator.rhino_primitives"],
        )
        self.assertEqual(
            set(FOURTH_WAVE_OPENING_FUNCTION_NAMES),
            imported_names["auditorium_generator.opening_geometry"],
        )

        for module_name, tree in (
            ("rhino_primitives", self.rhino_primitives_tree),
            ("opening_geometry", self.opening_geometry_tree),
        ):
            with self.subTest(module=module_name):
                import_roots = set()
                for node in ast.walk(tree):
                    if isinstance(node, ast.Import):
                        import_roots.update(
                            alias.name.split(".", 1)[0]
                            for alias in node.names
                        )
                    elif isinstance(node, ast.ImportFrom) and node.module:
                        import_roots.add(node.module.split(".", 1)[0])
                self.assertEqual({"Rhino"}, import_roots)

    def test_fifth_wave_stage_preview_extraction_boundaries(self):
        oracle_nodes = _function_nodes(self.oracle_tree)
        candidate_nodes = _function_nodes(
            self.stage_preview_geometry_tree
        )
        main_nodes = _function_nodes(self.auditorium_tree)

        self.assertEqual(5, len(FIFTH_WAVE_FUNCTION_NAMES))
        for name in FIFTH_WAVE_FUNCTION_NAMES:
            with self.subTest(function=name):
                self.assertIn(name, oracle_nodes)
                self.assertIn(name, candidate_nodes)
                self.assertNotIn(name, main_nodes)
                self.assertEqual(
                    ast.dump(
                        oracle_nodes[name].args,
                        include_attributes=False,
                    ),
                    ast.dump(
                        candidate_nodes[name].args,
                        include_attributes=False,
                    ),
                )
                self.assertEqual(
                    ast.dump(
                        oracle_nodes[name],
                        include_attributes=False,
                    ),
                    ast.dump(
                        candidate_nodes[name],
                        include_attributes=False,
                    ),
                )

        oracle_assignments = _assignment_nodes(self.oracle_tree)
        palette_assignments = _assignment_nodes(
            self.preview_palette_tree
        )
        stage_preview_assignments = _assignment_nodes(
            self.stage_preview_geometry_tree
        )
        main_assignments = _assignment_nodes(self.auditorium_tree)

        self.assertEqual(24, len(PREVIEW_PALETTE_NAMES))
        for name in PREVIEW_PALETTE_NAMES:
            with self.subTest(palette=name):
                self.assertIn(name, oracle_assignments)
                self.assertIn(name, palette_assignments)
                self.assertNotIn(name, main_assignments)
                self.assertEqual(
                    ast.dump(
                        oracle_assignments[name],
                        include_attributes=False,
                    ),
                    ast.dump(
                        palette_assignments[name],
                        include_attributes=False,
                    ),
                )

        side_constant = "SIDE_STAGE_CLEARANCE"
        self.assertNotIn(side_constant, main_assignments)
        self.assertEqual(
            ast.dump(
                oracle_assignments[side_constant],
                include_attributes=False,
            ),
            ast.dump(
                stage_preview_assignments[side_constant],
                include_attributes=False,
            ),
        )

        main_imports = {}
        for node in self.auditorium_tree.body:
            if not isinstance(node, ast.ImportFrom):
                continue
            main_imports.setdefault(node.module, set()).update(
                alias.asname or alias.name
                for alias in node.names
            )
        self.assertEqual(
            set(PREVIEW_PALETTE_NAMES),
            main_imports["auditorium_generator.preview_palette"],
        )
        self.assertEqual(
            set(FIFTH_WAVE_FUNCTION_NAMES) | {side_constant},
            main_imports[
                "auditorium_generator.stage_preview_geometry"
            ],
        )

        palette_imports = {}
        for node in self.preview_palette_tree.body:
            if isinstance(node, ast.Import):
                for alias in node.names:
                    palette_imports.setdefault(
                        (0, alias.name),
                        set(),
                    ).add(alias.asname or alias.name)
            elif isinstance(node, ast.ImportFrom):
                palette_imports.setdefault(
                    (node.level, node.module),
                    set(),
                ).update(
                    alias.asname or alias.name
                    for alias in node.names
                )
        self.assertEqual(
            {(0, "System.Drawing"): {"Color"}},
            palette_imports,
        )

        stage_preview_imports = {}
        for node in self.stage_preview_geometry_tree.body:
            if isinstance(node, ast.Import):
                for alias in node.names:
                    stage_preview_imports.setdefault(
                        (0, alias.name),
                        set(),
                    ).add(alias.asname or alias.name)
            elif isinstance(node, ast.ImportFrom):
                stage_preview_imports.setdefault(
                    (node.level, node.module),
                    set(),
                ).update(
                    alias.asname or alias.name
                    for alias in node.names
                )
        self.assertEqual(
            {
                (
                    1,
                    "preview_palette",
                ): {
                    "PREVIEW_AUX_STAGE",
                    "PREVIEW_FLOOR",
                    "PREVIEW_GRID",
                    "PREVIEW_MAIN_STAGE",
                    "PREVIEW_ORCHESTRA_PIT",
                    "PREVIEW_STAGE_APRON",
                    "PREVIEW_STAGE_CLEARANCE",
                    "PREVIEW_STAGE_SECTION",
                    "PREVIEW_UNDERSTAGE",
                },
                (
                    1,
                    "rhino_primitives",
                ): {
                    "build_plan_rectangle",
                    "get_stage_directions",
                    "line_curve",
                    "point_at",
                    "stage_space_point",
                },
            },
            stage_preview_imports,
        )

    def test_fifth_wave_stage_preview_behavior_parity(self):
        def fake_get_stage_directions(audience_direction):
            return (
                ("stage-right", audience_direction),
                ("stage-back", audience_direction),
            )

        def fake_build_plan_rectangle(*args):
            return ("plan-rectangle", args)

        def fake_stage_space_point(*args):
            return ("stage-space-point", args)

        def fake_point_at(*args):
            return ("point-at", args)

        def fake_line_curve(start, end):
            return ("line-curve", start, end)

        fake_globals = {
            name: ("color", name)
            for name in PREVIEW_PALETTE_NAMES
            if name.startswith("PREVIEW_")
        }
        fake_globals.update(
            {
                "SIDE_STAGE_CLEARANCE": 2000.0,
                "build_plan_rectangle": fake_build_plan_rectangle,
                "get_stage_directions": fake_get_stage_directions,
                "line_curve": fake_line_curve,
                "point_at": fake_point_at,
                "stage_space_point": fake_stage_space_point,
            }
        )
        reference = _load_selected_functions(
            self.oracle_tree,
            FIFTH_WAVE_FUNCTION_NAMES,
            fake_globals,
        )
        candidate = _load_selected_functions(
            self.stage_preview_geometry_tree,
            FIFTH_WAVE_FUNCTION_NAMES,
            fake_globals,
        )

        all_on_params = {
            "main_stage_width": 20000.0,
            "main_stage_depth": 14400.0,
            "right_stage_enabled": True,
            "right_stage_width": 20000.0,
            "right_stage_depth": 14400.0,
            "left_stage_enabled": True,
            "left_stage_width": 20000.0,
            "left_stage_depth": 14400.0,
            "rear_stage_enabled": True,
            "rear_stage_width": 20000.0,
            "rear_stage_depth": 14400.0,
            "understage_enabled": True,
            "stage_apron_projection": 1200.0,
            "first_row_distance": 7000.0,
            "stage_height": 1100.0,
            "orchestra_pit_depth": 0.0,
        }
        dimensions = {
            "main_tower_top_z": 26000.0,
            "main_grid_z": 24000.0,
            "clearance_top_z": 10000.0,
            "clearance_grid_z": 8000.0,
            "right_top_z": 10000.0,
            "right_grid_z": 8000.0,
            "left_top_z": 10000.0,
            "left_grid_z": 8000.0,
            "rear_top_z": 10000.0,
            "rear_grid_z": 8000.0,
            "understage_floor_z": -8000.0,
            "understage_bottom_z": -10000.0,
        }
        stage_point = ("stage-origin",)
        audience_direction = ("audience-direction",)
        mm_scale = 0.001

        def assert_fake_call_parity(name, *args):
            reference_capture = _capture(
                reference[name],
                args,
                {},
            )
            candidate_capture = _capture(
                candidate[name],
                args,
                {},
            )
            self.assert_deep_parity(
                reference_capture,
                candidate_capture,
                name,
            )
            self.assertEqual(
                args,
                candidate_capture[1],
                "{0}: candidate mutated positional input".format(name),
            )
            self.assertEqual({}, candidate_capture[2])
            self.assertEqual(
                "return",
                candidate_capture[0]["kind"],
                "{0}: unexpected error".format(name),
            )
            return candidate_capture[0]["value"]

        layout = assert_fake_call_parity(
            "calculate_proscenium_space_layout",
            all_on_params,
        )
        plan = assert_fake_call_parity(
            "build_proscenium_plan_curves",
            stage_point,
            audience_direction,
            all_on_params,
            mm_scale,
        )
        stage_3d = assert_fake_call_parity(
            "build_stage_space_3d_curves",
            stage_point,
            audience_direction,
            all_on_params,
            dimensions,
            mm_scale,
        )
        section_2d = assert_fake_call_parity(
            "build_stage_section_2d_curves",
            stage_point,
            audience_direction,
            all_on_params,
            dimensions,
            mm_scale,
        )
        transition = assert_fake_call_parity(
            "build_stage_audience_transition_curves",
            stage_point,
            audience_direction,
            all_on_params,
            mm_scale,
        )

        self.assertEqual(
            [
                "MainStage",
                "RightStageClearance",
                "LeftStageClearance",
                "RightStage",
                "LeftStage",
                "RearStage",
            ],
            [space["name"] for space in layout],
        )
        self.assertEqual(6, len(plan))
        self.assertEqual(
            [space["name"] + "Plan" for space in layout],
            [entry[2] for entry in plan],
        )
        self.assertEqual(42, len(stage_3d))
        self.assertEqual(14, len(section_2d))
        self.assertEqual(
            [
                "StageApronSection",
                "StageFrontSection",
                "StageAudienceFloorSection",
            ],
            [entry[2] for entry in transition],
        )

        all_off_params = copy.deepcopy(all_on_params)
        all_off_params.update(
            {
                "right_stage_enabled": False,
                "left_stage_enabled": False,
                "rear_stage_enabled": False,
                "understage_enabled": False,
            }
        )
        off_layout = assert_fake_call_parity(
            "calculate_proscenium_space_layout",
            all_off_params,
        )
        off_plan = assert_fake_call_parity(
            "build_proscenium_plan_curves",
            stage_point,
            audience_direction,
            all_off_params,
            mm_scale,
        )
        off_3d = assert_fake_call_parity(
            "build_stage_space_3d_curves",
            stage_point,
            audience_direction,
            all_off_params,
            dimensions,
            mm_scale,
        )
        off_2d = assert_fake_call_parity(
            "build_stage_section_2d_curves",
            stage_point,
            audience_direction,
            all_off_params,
            dimensions,
            mm_scale,
        )
        self.assertEqual(3, len(off_layout))
        self.assertEqual(3, len(off_plan))
        self.assertEqual(18, len(off_3d))
        self.assertEqual(5, len(off_2d))

        pit_params = copy.deepcopy(all_on_params)
        pit_params["orchestra_pit_depth"] = 1800.0
        pit_transition = assert_fake_call_parity(
            "build_stage_audience_transition_curves",
            stage_point,
            audience_direction,
            pit_params,
            mm_scale,
        )
        self.assertEqual(
            [
                "StageApronSection",
                "OrchestraPitFront",
                "OrchestraPitBottom",
                "OrchestraPitRear",
            ],
            [entry[2] for entry in pit_transition],
        )

    def test_sixth_wave_annotation_extraction_boundaries(self):
        oracle_nodes = _function_nodes(self.oracle_tree)
        candidate_nodes = _function_nodes(
            self.section_preview_annotations_tree
        )
        main_nodes = _function_nodes(self.auditorium_tree)
        candidate_functions = _load_selected_functions(
            self.section_preview_annotations_tree,
            SIXTH_WAVE_FUNCTION_NAMES,
            {},
        )

        self.assertEqual(2, len(SIXTH_WAVE_FUNCTION_NAMES))
        for name in SIXTH_WAVE_FUNCTION_NAMES:
            with self.subTest(function=name):
                self.assertIn(name, oracle_nodes)
                self.assertIn(name, candidate_nodes)
                self.assertNotIn(name, main_nodes)
                self.assertEqual(
                    str(inspect.signature(self.oracle[name])),
                    str(inspect.signature(candidate_functions[name])),
                )
                self.assertEqual(
                    ast.dump(
                        oracle_nodes[name].args,
                        include_attributes=False,
                    ),
                    ast.dump(
                        candidate_nodes[name].args,
                        include_attributes=False,
                    ),
                )
                self.assertEqual(
                    ast.dump(
                        oracle_nodes[name],
                        include_attributes=False,
                    ),
                    ast.dump(
                        candidate_nodes[name],
                        include_attributes=False,
                    ),
                )

        main_imports = {}
        for node in self.auditorium_tree.body:
            if not isinstance(node, ast.ImportFrom):
                continue
            main_imports.setdefault(node.module, set()).update(
                alias.asname or alias.name
                for alias in node.names
            )
        self.assertEqual(
            set(SIXTH_WAVE_FUNCTION_NAMES),
            main_imports[
                "auditorium_generator.section_preview_annotations"
            ],
        )

        candidate_imports = {}
        for node in self.section_preview_annotations_tree.body:
            if isinstance(node, ast.Import):
                for alias in node.names:
                    candidate_imports.setdefault(
                        (0, alias.name),
                        set(),
                    ).add(alias.asname or alias.name)
            elif isinstance(node, ast.ImportFrom):
                candidate_imports.setdefault(
                    (node.level, node.module),
                    set(),
                ).update(
                    alias.asname or alias.name
                    for alias in node.names
                )
        self.assertEqual(
            {
                (0, "System.Drawing"): {"Color"},
                (
                    1,
                    "calculations.sections",
                ): {
                    "balcony_result_is_displayable",
                },
                (
                    1,
                    "formatting",
                ): {
                    "format_riser_height_label",
                    "format_section_height_dimension",
                },
                (
                    1,
                    "preview_palette",
                ): {
                    "PREVIEW_AISLE",
                    "PREVIEW_FLOOR",
                    "PREVIEW_SECTION_DIMENSION",
                    "PREVIEW_WARNING",
                },
                (
                    1,
                    "rhino_primitives",
                ): {
                    "line_curve",
                    "point_at",
                },
            },
            candidate_imports,
        )

    def test_sixth_wave_annotation_behavior_parity_and_contracts(self):
        class FakeColor(object):
            White = ("system-color", "White")
            Black = ("system-color", "Black")

        def fake_point_at(*args):
            return ("point-at", args)

        def fake_line_curve(start, end):
            return ("line-curve", start, end)

        preview_aisle = ("color", "PREVIEW_AISLE")
        preview_floor = ("color", "PREVIEW_FLOOR")
        preview_dimension = (
            "color",
            "PREVIEW_SECTION_DIMENSION",
        )
        preview_warning = ("color", "PREVIEW_WARNING")
        fake_globals = {
            "Color": FakeColor,
            "PREVIEW_AISLE": preview_aisle,
            "PREVIEW_FLOOR": preview_floor,
            "PREVIEW_SECTION_DIMENSION": preview_dimension,
            "PREVIEW_WARNING": preview_warning,
            "balcony_result_is_displayable": (
                sections.balcony_result_is_displayable
            ),
            "format_riser_height_label": (
                formatting.format_riser_height_label
            ),
            "format_section_height_dimension": (
                formatting.format_section_height_dimension
            ),
            "line_curve": fake_line_curve,
            "point_at": fake_point_at,
        }
        reference = _load_selected_functions(
            self.oracle_tree,
            SIXTH_WAVE_FUNCTION_NAMES,
            fake_globals,
        )
        candidate = _load_selected_functions(
            self.section_preview_annotations_tree,
            SIXTH_WAVE_FUNCTION_NAMES,
            fake_globals,
        )

        def assert_fake_call_parity(name, *args):
            reference_capture = _capture(
                reference[name],
                args,
                {},
            )
            candidate_capture = _capture(
                candidate[name],
                args,
                {},
            )
            self.assert_deep_parity(
                reference_capture,
                candidate_capture,
                name,
            )
            self.assertEqual(
                args,
                reference_capture[1],
                "{0}: oracle mutated positional input".format(name),
            )
            self.assertEqual(
                args,
                candidate_capture[1],
                "{0}: candidate mutated positional input".format(name),
            )
            self.assertEqual({}, reference_capture[2])
            self.assertEqual({}, candidate_capture[2])
            self.assertEqual(
                "return",
                candidate_capture[0]["kind"],
                "{0}: unexpected error".format(name),
            )
            return candidate_capture[0]["value"]

        stage_point = ("stage-origin",)
        audience_direction = ("audience-direction",)
        mm_scale = 0.001
        params = {
            "floor_type": "stepped",
            "row_pitch": 1100.0,
            "aisle_stair_tread_depth": 300.0,
            "aisle_width": 1000.0,
        }
        normal_stalls = {
            "x_values": [8100.0, 9200.0, 10300.0],
            "base_z_values": [-1100.0, -920.0, -730.0],
            "riser_values": [0.0, 180.0, 190.0],
            "violations": [False, False, True],
            "aisle_before_values": [False, False, False],
            "aisle_stair_tread_counts": [0, 0, 0],
            "aisle_stair_riser_heights": [0.0, 0.0, 0.0],
            "aisle_stair_run_values": [0.0, 0.0, 0.0],
        }

        normal_labels = assert_fake_call_parity(
            "build_riser_height_preview_labels",
            stage_point,
            audience_direction,
            params,
            normal_stalls,
            [],
            mm_scale,
        )
        self.assertEqual(2, len(normal_labels))
        self.assertEqual(
            ["H 180 mm", "H 190 mm"],
            [entry[1] for entry in normal_labels],
        )
        self.assertEqual(
            [
                (preview_floor, FakeColor.Black),
                (preview_warning, FakeColor.White),
            ],
            [(entry[2], entry[3]) for entry in normal_labels],
        )
        self.assertEqual(
            [(8650.0, -920.0), (9750.0, -730.0)],
            [
                (
                    entry[0][1][2],
                    entry[0][1][3],
                )
                for entry in normal_labels
            ],
        )

        cross_aisle_stalls = {
            "x_values": [8100.0, 9200.0, 11500.0, 12600.0],
            "base_z_values": [-1100.0, -920.0, -410.0, -230.0],
            "riser_values": [0.0, 180.0, 510.0, 180.0],
            "violations": [False, False, False, True],
            "aisle_before_values": [False, False, True, False],
            "aisle_stair_tread_counts": [0, 0, 2, 0],
            "aisle_stair_riser_heights": [
                0.0,
                0.0,
                170.0,
                0.0,
            ],
            "aisle_stair_run_values": [0.0, 0.0, 600.0, 0.0],
        }
        cross_aisle_labels = assert_fake_call_parity(
            "build_riser_height_preview_labels",
            stage_point,
            audience_direction,
            params,
            cross_aisle_stalls,
            [],
            mm_scale,
        )
        self.assertEqual(5, len(cross_aisle_labels))
        self.assertEqual(
            [
                "H 180 mm",
                "H 170 mm",
                "H 170 mm",
                "H 170 mm",
                "H 180 mm",
            ],
            [entry[1] for entry in cross_aisle_labels],
        )
        self.assertEqual(
            [
                preview_floor,
                preview_aisle,
                preview_aisle,
                preview_aisle,
                preview_warning,
            ],
            [entry[2] for entry in cross_aisle_labels],
        )
        self.assertEqual(
            [
                (8650.0, -920.0),
                (9950.0, -750.0),
                (10250.0, -580.0),
                (10950.0, -410.0),
                (12050.0, -230.0),
            ],
            [
                (
                    entry[0][1][2],
                    entry[0][1][3],
                )
                for entry in cross_aisle_labels
            ],
        )

        valid_balcony = {
            "lower_limit_violation": False,
            "x_values": [14000.0, 15100.0, 16200.0],
            "base_z_values": [3200.0, 3400.0, 3600.0],
            "riser_to_next_values": [200.0, 200.0, 0.0],
            "railing_front_x": 13750.0,
        }
        zero_balcony = copy.deepcopy(valid_balcony)
        zero_balcony["riser_to_next_values"] = [
            0.0,
            1e-9,
            0.0,
        ]
        hidden_balcony = copy.deepcopy(valid_balcony)
        hidden_balcony["lower_limit_violation"] = True
        recovered_balcony = copy.deepcopy(hidden_balcony)
        recovered_balcony["rise_interpolation_applied"] = True
        sloped_params = copy.deepcopy(params)
        sloped_params["floor_type"] = "sloped"

        zero_and_hidden_labels = assert_fake_call_parity(
            "build_riser_height_preview_labels",
            stage_point,
            audience_direction,
            sloped_params,
            normal_stalls,
            [None, zero_balcony, hidden_balcony],
            mm_scale,
        )
        self.assertEqual(2, len(zero_and_hidden_labels))
        self.assertEqual(
            ["H 200 mm", "H 200 mm"],
            [entry[1] for entry in zero_and_hidden_labels],
        )

        recovered_labels = assert_fake_call_parity(
            "build_riser_height_preview_labels",
            stage_point,
            audience_direction,
            sloped_params,
            normal_stalls,
            [hidden_balcony, recovered_balcony],
            mm_scale,
        )
        self.assertEqual(4, len(recovered_labels))
        self.assertEqual(
            ["H 200 mm"] * 4,
            [entry[1] for entry in recovered_labels],
        )
        self.assertTrue(
            all(
                entry[2:] == (preview_warning, FakeColor.White)
                for entry in recovered_labels
            )
        )

        second_balcony = {
            "lower_limit_violation": False,
            "x_values": [19000.0, 20100.0],
            "base_z_values": [7000.0, 7300.0],
            "riser_to_next_values": [300.0, 0.0],
            "railing_front_x": 18750.0,
        }
        dimension_cases = (
            (
                "zero-tier",
                [None, hidden_balcony],
                9,
                [
                    "1  H 8,400 mm",
                    "2  H 400 mm",
                    "3  H 3,930 mm",
                    "4  H 370 mm",
                ],
                19020.0,
            ),
            (
                "one-tier",
                [hidden_balcony, valid_balcony],
                13,
                [
                    "1  H 8,400 mm",
                    "2  H 400 mm",
                    "3  H 400 mm",
                    "4  H 400 mm",
                    "5  H 3,930 mm",
                    "6  H 370 mm",
                ],
                19020.0,
            ),
            (
                "two-tier",
                [valid_balcony, second_balcony],
                13,
                [
                    "1  H 4,700 mm",
                    "2  H 300 mm",
                    "3  H 3,400 mm",
                    "4  H 400 mm",
                    "5  H 3,930 mm",
                    "6  H 370 mm",
                ],
                22120.0,
            ),
        )
        for (
            case_name,
            balcony_results,
            expected_curve_count,
            expected_texts,
            expected_label_x,
        ) in dimension_cases:
            with self.subTest(dimension_case=case_name):
                curves, labels = assert_fake_call_parity(
                    "build_section_height_dimension_preview",
                    stage_point,
                    audience_direction,
                    params,
                    normal_stalls,
                    balcony_results,
                    12000.0,
                    18000.0,
                    mm_scale,
                )
                self.assertEqual(expected_curve_count, len(curves))
                self.assertEqual(expected_texts, [item[1] for item in labels])
                self.assertEqual(
                    expected_curve_count - len(labels),
                    len(labels) + 1,
                )
                self.assertTrue(
                    all(
                        entry[1:] == (preview_dimension, 1)
                        for entry in curves
                    )
                )
                self.assertTrue(
                    all(
                        entry[2:] == (
                            preview_dimension,
                            FakeColor.Black,
                        )
                        for entry in labels
                    )
                )
                self.assertEqual(
                    [expected_label_x] * len(labels),
                    [entry[0][1][2] for entry in labels],
                )

    def test_preview_conduit_extraction_boundaries(self):
        class_name = "AuditoriumPreviewConduit"
        oracle_node = _class_nodes(self.oracle_tree)[class_name]
        candidate_node = _class_nodes(
            self.preview_conduit_tree
        )[class_name]

        self.assertEqual(
            ast.dump(oracle_node, include_attributes=False),
            ast.dump(candidate_node, include_attributes=False),
        )
        self.assertNotIn(
            class_name,
            _class_nodes(self.auditorium_tree),
        )
        self.assertEqual(
            [
                "__init__",
                "set_geometry",
                "clear",
                "update_bounding_box",
                "CalculateBoundingBox",
                "CalculateBoundingBoxZoomExtents",
                "PostDrawObjects",
                "DrawForeground",
            ],
            [
                node.name
                for node in candidate_node.body
                if isinstance(node, ast.FunctionDef)
            ],
        )

        direct_imports = [
            node
            for node in self.auditorium_tree.body
            if (
                isinstance(node, ast.ImportFrom)
                and node.module
                == "auditorium_generator.preview_conduit"
            )
        ]
        self.assertEqual(1, len(direct_imports))
        self.assertEqual(
            [("AuditoriumPreviewConduit", None)],
            [
                (alias.name, alias.asname)
                for alias in direct_imports[0].names
            ],
        )

        candidate_imports = set()
        for node in self.preview_conduit_tree.body:
            if isinstance(node, ast.Import):
                candidate_imports.update(
                    (alias.name, alias.asname)
                    for alias in node.names
                )
            elif isinstance(node, ast.ImportFrom):
                self.fail("preview_conduit must use only direct imports")
        self.assertEqual(
            {
                ("Rhino", None),
                ("Rhino.Geometry", "rg"),
            },
            candidate_imports,
        )

        package_imports = {
            node.module
            for node in self.auditorium_generator_init_tree.body
            if isinstance(node, ast.ImportFrom)
        }
        self.assertNotIn("preview_conduit", package_imports)
        self.assertNotIn(
            class_name,
            _class_nodes(self.auditorium_generator_init_tree),
        )

    def test_preview_conduit_fake_rhino_behavior_parity(self):
        class FakeDisplayConduit(object):
            def __init__(self):
                self.base_init_calls = (
                    getattr(self, "base_init_calls", 0) + 1
                )

        class FakeDisplayMaterial(object):
            def __init__(self, color, transparency):
                self.color = color
                self.transparency = transparency

        class FakePointStyle(object):
            RoundControlPoint = "round-control-point"

        class FakeRhinoDisplay(object):
            DisplayConduit = FakeDisplayConduit
            DisplayMaterial = FakeDisplayMaterial
            PointStyle = FakePointStyle

        class FakeRhino(object):
            Display = FakeRhinoDisplay

        class FakeBoundingBoxMeta(type):
            @property
            def Empty(cls):
                return cls("empty", False)

        class FakeBoundingBox(
            object,
            metaclass=FakeBoundingBoxMeta
        ):
            def __init__(self, marker, is_valid):
                self.marker = marker
                self.IsValid = is_valid
                self.unions = []

            def Union(self, value):
                self.unions.append(value.marker)
                self.IsValid = True

            def snapshot(self):
                return (
                    self.marker,
                    self.IsValid,
                    tuple(self.unions),
                )

        class FakeGeometry(object):
            def __init__(self, marker, box_is_valid):
                self.marker = marker
                self.box_is_valid = box_is_valid
                self.bounding_box_requests = []

            def GetBoundingBox(self, accurate):
                self.bounding_box_requests.append(accurate)
                return FakeBoundingBox(
                    self.marker + "-box",
                    self.box_is_valid,
                )

        class FakePoint(object):
            def __init__(self, marker, is_valid):
                self.marker = marker
                self.IsValid = is_valid

        class FakeGeometryNamespace(object):
            BoundingBox = FakeBoundingBox

        class FakeDisplay(object):
            def __init__(self):
                self.calls = []

            def DrawMeshShaded(self, mesh, material):
                self.calls.append(
                    (
                        "mesh",
                        mesh.marker,
                        material.color,
                        material.transparency,
                    )
                )

            def DrawCurve(self, curve, color, thickness):
                self.calls.append(
                    ("curve", curve.marker, color, thickness)
                )

            def DrawPoint(self, point, style, size, color):
                self.calls.append(
                    ("point", point.marker, style, size, color)
                )

            def DrawDot(
                self,
                point,
                text,
                background_color,
                text_color,
            ):
                self.calls.append(
                    (
                        "dot",
                        point.marker,
                        text,
                        background_color,
                        text_color,
                    )
                )

        class FakeEventArgs(object):
            def __init__(self):
                self.Display = FakeDisplay()
                self.included_boxes = []

            def IncludeBoundingBox(self, box):
                self.included_boxes.append(box.snapshot())

        fake_globals = {
            "Rhino": FakeRhino,
            "rg": FakeGeometryNamespace,
        }
        reference_class = _load_selected_class(
            self.oracle_tree,
            "AuditoriumPreviewConduit",
            fake_globals,
        )
        candidate_class = _load_selected_class(
            self.preview_conduit_tree,
            "AuditoriumPreviewConduit",
            fake_globals,
        )

        def exercise(conduit_class):
            curve_valid = FakeGeometry("curve-valid", True)
            curve_invalid = FakeGeometry("curve-invalid", False)
            point_valid = FakePoint("point-valid", True)
            point_invalid = FakePoint("point-invalid", False)
            mesh_valid = FakeGeometry("mesh-valid", True)
            mesh_invalid = FakeGeometry("mesh-invalid", False)
            label_valid = FakePoint("label-valid", True)
            label_invalid = FakePoint("label-invalid", False)
            preview_data = {
                "preview_curves": [
                    (curve_valid, "curve-color", 2),
                    (None, "curve-none-color", 3),
                    (curve_invalid, "curve-invalid-color", 4),
                ],
                "preview_points": [
                    (point_valid, "point-color", 5),
                    (point_invalid, "point-invalid-color", 6),
                ],
                "preview_meshes": [
                    (mesh_valid, "mesh-default-color"),
                    (None, "mesh-none-color", 0.25),
                    (mesh_invalid, "mesh-alpha-color", 0.4),
                ],
                "preview_labels": [
                    (
                        label_valid,
                        "valid-label",
                        "valid-background",
                        "valid-text",
                    ),
                    (
                        label_invalid,
                        "invalid-label",
                        "invalid-background",
                        "invalid-text",
                    ),
                ],
            }
            conduit = conduit_class()
            set_result = conduit.set_geometry(preview_data)
            list_identity = (
                conduit.curves is preview_data["preview_curves"],
                conduit.points is preview_data["preview_points"],
                conduit.meshes is preview_data["preview_meshes"],
                conduit.labels is preview_data["preview_labels"],
            )

            bounding_event = FakeEventArgs()
            zoom_event = FakeEventArgs()
            draw_event = FakeEventArgs()
            method_results = (
                set_result,
                conduit.CalculateBoundingBox(bounding_event),
                conduit.CalculateBoundingBoxZoomExtents(zoom_event),
                conduit.PostDrawObjects(draw_event),
                conduit.DrawForeground(draw_event),
            )
            before_clear = {
                "base_init_calls": conduit.base_init_calls,
                "list_identity": list_identity,
                "bounding_box": conduit.bounding_box.snapshot(),
                "bounding_requests": (
                    tuple(curve_valid.bounding_box_requests),
                    tuple(curve_invalid.bounding_box_requests),
                    tuple(mesh_valid.bounding_box_requests),
                    tuple(mesh_invalid.bounding_box_requests),
                ),
                "included": (
                    tuple(bounding_event.included_boxes),
                    tuple(zoom_event.included_boxes),
                ),
                "draw_calls": tuple(draw_event.Display.calls),
                "method_results": method_results,
            }

            clear_result = conduit.clear()
            cleared_event = FakeEventArgs()
            cleared_results = (
                clear_result,
                conduit.CalculateBoundingBox(cleared_event),
                conduit.CalculateBoundingBoxZoomExtents(
                    cleared_event
                ),
                conduit.PostDrawObjects(cleared_event),
                conduit.DrawForeground(cleared_event),
            )
            after_clear = {
                "collections": (
                    conduit.curves,
                    conduit.points,
                    conduit.meshes,
                    conduit.labels,
                ),
                "bounding_box": conduit.bounding_box.snapshot(),
                "included": tuple(cleared_event.included_boxes),
                "draw_calls": tuple(cleared_event.Display.calls),
                "method_results": cleared_results,
            }
            return {
                "before_clear": before_clear,
                "after_clear": after_clear,
            }

        reference = exercise(reference_class)
        candidate = exercise(candidate_class)
        self.assert_deep_parity(reference, candidate)

        self.assertEqual(
            (
                "empty",
                True,
                (
                    "curve-valid-box",
                    "point-valid",
                    "mesh-valid-box",
                    "label-valid",
                ),
            ),
            candidate["before_clear"]["bounding_box"],
        )
        self.assertEqual(
            (True, True, True, True),
            candidate["before_clear"]["list_identity"],
        )
        self.assertEqual(
            ((True,), (True,), (True,), (True,)),
            candidate["before_clear"]["bounding_requests"],
        )
        self.assertEqual(
            (
                (
                    "mesh",
                    "mesh-valid",
                    "mesh-default-color",
                    0.0,
                ),
                (
                    "mesh",
                    "mesh-invalid",
                    "mesh-alpha-color",
                    0.4,
                ),
                ("curve", "curve-valid", "curve-color", 2),
                (
                    "curve",
                    "curve-invalid",
                    "curve-invalid-color",
                    4,
                ),
                (
                    "point",
                    "point-valid",
                    "round-control-point",
                    5,
                    "point-color",
                ),
                (
                    "point",
                    "point-invalid",
                    "round-control-point",
                    6,
                    "point-invalid-color",
                ),
                (
                    "dot",
                    "label-valid",
                    "valid-label",
                    "valid-background",
                    "valid-text",
                ),
                (
                    "dot",
                    "label-invalid",
                    "invalid-label",
                    "invalid-background",
                    "invalid-text",
                ),
            ),
            candidate["before_clear"]["draw_calls"],
        )
        self.assertEqual(
            ("empty", False, ()),
            candidate["after_clear"]["bounding_box"],
        )
        self.assertEqual(
            ([], [], [], []),
            candidate["after_clear"]["collections"],
        )
        self.assertEqual(
            (),
            candidate["after_clear"]["included"],
        )
        self.assertEqual(
            (),
            candidate["after_clear"]["draw_calls"],
        )

    def test_preview_mesh_geometry_extraction_boundaries(self):
        oracle_nodes = _function_nodes(self.oracle_tree)
        candidate_nodes = _function_nodes(
            self.preview_mesh_geometry_tree
        )
        main_nodes = _function_nodes(self.auditorium_tree)
        reference_functions = _load_selected_functions(
            self.oracle_tree,
            PREVIEW_MESH_FUNCTION_NAMES,
            {},
        )
        candidate_functions = _load_selected_functions(
            self.preview_mesh_geometry_tree,
            PREVIEW_MESH_FUNCTION_NAMES,
            {},
        )

        self.assertEqual(
            list(PREVIEW_MESH_FUNCTION_NAMES),
            [
                node.name
                for node in self.preview_mesh_geometry_tree.body
                if isinstance(node, ast.FunctionDef)
            ],
        )
        for name in PREVIEW_MESH_FUNCTION_NAMES:
            with self.subTest(function=name):
                self.assertEqual(
                    ast.dump(
                        oracle_nodes[name],
                        include_attributes=False,
                    ),
                    ast.dump(
                        candidate_nodes[name],
                        include_attributes=False,
                    ),
                )
                self.assertEqual(
                    str(inspect.signature(reference_functions[name])),
                    str(inspect.signature(candidate_functions[name])),
                )
                self.assertNotIn(name, main_nodes)

        direct_imports = [
            node
            for node in self.auditorium_tree.body
            if (
                isinstance(node, ast.ImportFrom)
                and node.module
                == "auditorium_generator.preview_mesh_geometry"
            )
        ]
        self.assertEqual(1, len(direct_imports))
        self.assertEqual(
            list(PREVIEW_MESH_FUNCTION_NAMES),
            [alias.name for alias in direct_imports[0].names],
        )
        self.assertTrue(
            all(alias.asname is None for alias in direct_imports[0].names)
        )

        candidate_imports = set()
        for node in self.preview_mesh_geometry_tree.body:
            if isinstance(node, ast.Import):
                candidate_imports.update(
                    (alias.name, alias.asname)
                    for alias in node.names
                )
            elif isinstance(node, ast.ImportFrom):
                self.fail(
                    "preview_mesh_geometry must use only direct imports"
                )
        self.assertEqual(
            {("Rhino.Geometry", "rg")},
            candidate_imports,
        )

        package_imports = {
            node.module
            for node in self.auditorium_generator_init_tree.body
            if isinstance(node, ast.ImportFrom)
        }
        self.assertNotIn("preview_mesh_geometry", package_imports)
        package_names = set(_function_nodes(
            self.auditorium_generator_init_tree
        ))
        self.assertFalse(
            set(PREVIEW_MESH_FUNCTION_NAMES) & package_names
        )

    def test_preview_mesh_geometry_fake_rhino_behavior_parity(self):
        def make_fake_rhino():
            class Runtime(object):
                calls = []
                mesh_instances = []

            class FakeFaces(object):
                def __init__(self, count):
                    self.Count = count

            class FakeNormals(object):
                def __init__(self, owner):
                    self.owner = owner
                    self.compute_calls = 0

                def ComputeNormals(self):
                    self.compute_calls += 1
                    self.owner.events.append(("normals",))
                    Runtime.calls.append(
                        ("normals", self.owner.marker)
                    )

            class FakeMesh(object):
                def __init__(
                    self,
                    marker="preview-target",
                    face_count=0,
                ):
                    self.marker = marker
                    self.Faces = FakeFaces(face_count)
                    self.Normals = FakeNormals(self)
                    self.compact_calls = 0
                    self.appended = []
                    self.events = []
                    Runtime.mesh_instances.append(self)

                def Append(self, mesh):
                    self.appended.append(mesh.marker)
                    self.Faces.Count += mesh.Faces.Count
                    event = (
                        "append",
                        mesh.marker,
                        mesh.Faces.Count,
                    )
                    self.events.append(event)
                    Runtime.calls.append(
                        (
                            "append",
                            self.marker,
                            mesh.marker,
                            mesh.Faces.Count,
                        )
                    )

                def Compact(self):
                    self.compact_calls += 1
                    self.events.append(("compact",))
                    Runtime.calls.append(
                        ("compact", self.marker)
                    )

                def snapshot(self):
                    return {
                        "marker": self.marker,
                        "faces": self.Faces.Count,
                        "appended": tuple(self.appended),
                        "normal_calls": (
                            self.Normals.compute_calls
                        ),
                        "compact_calls": self.compact_calls,
                        "events": tuple(self.events),
                    }

                @staticmethod
                def CreateFromBrep(brep, parameters):
                    Runtime.calls.append(
                        (
                            "create_from_brep",
                            brep.marker,
                            parameters,
                        )
                    )
                    return brep.meshes

                @staticmethod
                def CreateFromSubDControlNet(subd):
                    Runtime.calls.append(
                        ("create_from_subd", subd.marker)
                    )
                    return subd.mesh

            class FakeBrep(object):
                def __init__(self, marker, meshes):
                    self.marker = marker
                    self.meshes = meshes

                @staticmethod
                def CreateFromSurface(surface):
                    Runtime.calls.append(
                        ("create_from_surface", surface.marker)
                    )
                    return surface.brep

            class FakeExtrusion(object):
                def __init__(self, marker, brep):
                    self.marker = marker
                    self.brep = brep

                def ToBrep(self):
                    Runtime.calls.append(
                        ("to_brep", self.marker)
                    )
                    return self.brep

            class FakeSurface(object):
                def __init__(self, marker, brep):
                    self.marker = marker
                    self.brep = brep

            class FakeSubD(object):
                def __init__(self, marker, mesh):
                    self.marker = marker
                    self.mesh = mesh

            class FakeUnsupported(object):
                pass

            class FakeMeshingParameters(object):
                FastRenderMesh = "fast-render-mesh"

            class FakeGeometryNamespace(object):
                Mesh = FakeMesh
                Brep = FakeBrep
                Extrusion = FakeExtrusion
                Surface = FakeSurface
                SubD = FakeSubD
                MeshingParameters = FakeMeshingParameters

            fixtures = {
                "Runtime": Runtime,
                "Mesh": FakeMesh,
                "Brep": FakeBrep,
                "Extrusion": FakeExtrusion,
                "Surface": FakeSurface,
                "SubD": FakeSubD,
                "Unsupported": FakeUnsupported,
            }
            return {"rg": FakeGeometryNamespace}, fixtures

        def exercise(tree):
            fake_globals, fixtures = make_fake_rhino()
            loaded = _load_selected_functions(
                tree,
                PREVIEW_MESH_FUNCTION_NAMES,
                fake_globals,
            )
            append_geometry = loaded["append_geometry_to_mesh"]
            build_preview = loaded[
                "build_seat_source_preview_mesh"
            ]
            runtime = fixtures["Runtime"]
            mesh_type = fixtures["Mesh"]
            brep_type = fixtures["Brep"]
            extrusion_type = fixtures["Extrusion"]
            surface_type = fixtures["Surface"]
            subd_type = fixtures["SubD"]
            unsupported_type = fixtures["Unsupported"]

            append_inputs = (
                ("mesh", mesh_type("mesh", 2)),
                (
                    "brep",
                    brep_type(
                        "brep",
                        [
                            mesh_type("brep-a", 1),
                            None,
                            mesh_type("brep-b", 2),
                        ],
                    ),
                ),
                (
                    "extrusion",
                    extrusion_type(
                        "extrusion",
                        brep_type(
                            "extrusion-brep",
                            [mesh_type("extrusion-mesh", 3)],
                        ),
                    ),
                ),
                (
                    "surface",
                    surface_type(
                        "surface",
                        brep_type(
                            "surface-brep",
                            [mesh_type("surface-mesh", 4)],
                        ),
                    ),
                ),
                (
                    "subd",
                    subd_type(
                        "subd",
                        mesh_type("subd-mesh", 5),
                    ),
                ),
                ("subd-none", subd_type("subd-none", None)),
                ("unsupported", unsupported_type()),
                ("none", None),
                (
                    "brep-meshes-none",
                    brep_type("brep-meshes-none", None),
                ),
            )
            append_captures = []
            for label, geometry in append_inputs:
                target = mesh_type("target-" + label)
                call_start = len(runtime.calls)
                result = append_geometry(target, geometry)
                append_captures.append(
                    {
                        "label": label,
                        "returned_none": result is None,
                        "target": target.snapshot(),
                        "calls": tuple(
                            runtime.calls[call_start:]
                        ),
                    }
                )

            zero_inputs = [
                mesh_type("zero-source", 0),
                brep_type("zero-brep", None),
                unsupported_type(),
                None,
            ]
            instance_start = len(runtime.mesh_instances)
            call_start = len(runtime.calls)
            zero_result = build_preview(zero_inputs)
            zero_targets = runtime.mesh_instances[instance_start:]
            zero_target = zero_targets[0]
            zero_capture = {
                "created_targets": len(zero_targets),
                "result": (
                    "none"
                    if zero_result is None
                    else "target"
                    if zero_result is zero_target
                    else "other"
                ),
                "target": zero_target.snapshot(),
                "calls": tuple(runtime.calls[call_start:]),
            }

            nonzero_inputs = [
                mesh_type("mixed-direct", 2),
                brep_type(
                    "mixed-brep",
                    [
                        mesh_type("mixed-brep-a", 1),
                        None,
                        mesh_type("mixed-brep-b", 2),
                    ],
                ),
                extrusion_type(
                    "mixed-extrusion",
                    brep_type(
                        "mixed-extrusion-brep",
                        [mesh_type("mixed-extrusion-mesh", 3)],
                    ),
                ),
                surface_type(
                    "mixed-surface",
                    brep_type(
                        "mixed-surface-brep",
                        [mesh_type("mixed-surface-mesh", 4)],
                    ),
                ),
                subd_type(
                    "mixed-subd",
                    mesh_type("mixed-subd-mesh", 5),
                ),
                brep_type("mixed-brep-none", None),
                unsupported_type(),
                None,
            ]
            instance_start = len(runtime.mesh_instances)
            call_start = len(runtime.calls)
            nonzero_result = build_preview(nonzero_inputs)
            nonzero_targets = runtime.mesh_instances[instance_start:]
            nonzero_target = nonzero_targets[0]
            nonzero_capture = {
                "created_targets": len(nonzero_targets),
                "result": (
                    "none"
                    if nonzero_result is None
                    else "target"
                    if nonzero_result is nonzero_target
                    else "other"
                ),
                "target": nonzero_target.snapshot(),
                "calls": tuple(runtime.calls[call_start:]),
            }
            return {
                "append_cases": tuple(append_captures),
                "zero_build": zero_capture,
                "nonzero_build": nonzero_capture,
            }

        reference = exercise(self.oracle_tree)
        candidate = exercise(self.preview_mesh_geometry_tree)
        self.assert_deep_parity(reference, candidate)

        append_cases = {
            entry["label"]: entry
            for entry in candidate["append_cases"]
        }
        self.assertEqual(
            (
                "mesh",
                "brep",
                "extrusion",
                "surface",
                "subd",
                "subd-none",
                "unsupported",
                "none",
                "brep-meshes-none",
            ),
            tuple(
                entry["label"]
                for entry in candidate["append_cases"]
            ),
        )
        self.assertTrue(
            all(
                entry["returned_none"]
                for entry in candidate["append_cases"]
            )
        )
        self.assertEqual(
            ("mesh",),
            append_cases["mesh"]["target"]["appended"],
        )
        self.assertEqual(
            ("brep-a", "brep-b"),
            append_cases["brep"]["target"]["appended"],
        )
        self.assertEqual(
            ("extrusion-mesh",),
            append_cases["extrusion"]["target"]["appended"],
        )
        self.assertEqual(
            ("surface-mesh",),
            append_cases["surface"]["target"]["appended"],
        )
        self.assertEqual(
            ("subd-mesh",),
            append_cases["subd"]["target"]["appended"],
        )
        for label in (
            "subd-none",
            "unsupported",
            "none",
            "brep-meshes-none",
        ):
            self.assertEqual(
                (),
                append_cases[label]["target"]["appended"],
            )
        self.assertEqual(
            ("to_brep", "extrusion"),
            append_cases["extrusion"]["calls"][0],
        )
        self.assertEqual(
            ("create_from_surface", "surface"),
            append_cases["surface"]["calls"][0],
        )
        self.assertEqual(
            ("create_from_subd", "subd"),
            append_cases["subd"]["calls"][0],
        )
        self.assertEqual(
            (
                "create_from_brep",
                "brep-meshes-none",
                "fast-render-mesh",
            ),
            append_cases["brep-meshes-none"]["calls"][0],
        )

        zero_build = candidate["zero_build"]
        self.assertEqual(1, zero_build["created_targets"])
        self.assertEqual("none", zero_build["result"])
        self.assertEqual(0, zero_build["target"]["faces"])
        self.assertEqual(0, zero_build["target"]["normal_calls"])
        self.assertEqual(0, zero_build["target"]["compact_calls"])

        nonzero_build = candidate["nonzero_build"]
        self.assertEqual(1, nonzero_build["created_targets"])
        self.assertEqual("target", nonzero_build["result"])
        self.assertEqual(17, nonzero_build["target"]["faces"])
        self.assertEqual(
            (
                "mixed-direct",
                "mixed-brep-a",
                "mixed-brep-b",
                "mixed-extrusion-mesh",
                "mixed-surface-mesh",
                "mixed-subd-mesh",
            ),
            nonzero_build["target"]["appended"],
        )
        self.assertEqual(1, nonzero_build["target"]["normal_calls"])
        self.assertEqual(1, nonzero_build["target"]["compact_calls"])
        self.assertEqual(
            (("normals",), ("compact",)),
            nonzero_build["target"]["events"][-2:],
        )

    def test_chair_preview_geometry_extraction_boundaries(self):
        oracle_assignments = _assignment_nodes(self.oracle_tree)
        candidate_assignments = _assignment_nodes(
            self.chair_preview_geometry_tree
        )
        main_assignments = _assignment_nodes(self.auditorium_tree)

        self.assertEqual(
            set(CHAIR_PREVIEW_DATA_NAMES),
            set(candidate_assignments),
        )
        for name in CHAIR_PREVIEW_DATA_NAMES:
            with self.subTest(data=name):
                self.assertNotIn(name, main_assignments)
                self.assertEqual(
                    ast.dump(
                        oracle_assignments[name],
                        include_attributes=False,
                    ),
                    ast.dump(
                        candidate_assignments[name],
                        include_attributes=False,
                    ),
                )

        line_data = ast.literal_eval(
            candidate_assignments["CHAIR_LINE_DATA"].value
        )
        arc_data = ast.literal_eval(
            candidate_assignments["CHAIR_ARC_DATA"].value
        )
        self.assertEqual(80, len(line_data))
        self.assertTrue(all(len(entry) == 4 for entry in line_data))
        self.assertEqual(17, len(arc_data))
        self.assertTrue(all(len(entry) == 6 for entry in arc_data))

        oracle_nodes = _function_nodes(self.oracle_tree)
        candidate_nodes = _function_nodes(
            self.chair_preview_geometry_tree
        )
        main_nodes = _function_nodes(self.auditorium_tree)
        reference_functions = _load_selected_functions(
            self.oracle_tree,
            CHAIR_PREVIEW_FUNCTION_NAMES,
            {},
        )
        candidate_functions = _load_selected_functions(
            self.chair_preview_geometry_tree,
            CHAIR_PREVIEW_FUNCTION_NAMES,
            {},
        )
        self.assertEqual(
            list(CHAIR_PREVIEW_FUNCTION_NAMES),
            [
                node.name
                for node in self.chair_preview_geometry_tree.body
                if isinstance(node, ast.FunctionDef)
            ],
        )
        for name in CHAIR_PREVIEW_FUNCTION_NAMES:
            with self.subTest(function=name):
                self.assertNotIn(name, main_nodes)
                self.assertEqual(
                    ast.dump(
                        oracle_nodes[name],
                        include_attributes=False,
                    ),
                    ast.dump(
                        candidate_nodes[name],
                        include_attributes=False,
                    ),
                )
                self.assertEqual(
                    ast.dump(
                        oracle_nodes[name].args,
                        include_attributes=False,
                    ),
                    ast.dump(
                        candidate_nodes[name].args,
                        include_attributes=False,
                    ),
                )
                self.assertEqual(
                    str(inspect.signature(reference_functions[name])),
                    str(inspect.signature(candidate_functions[name])),
                )

        direct_imports = [
            node
            for node in self.auditorium_tree.body
            if (
                isinstance(node, ast.ImportFrom)
                and node.module
                == "auditorium_generator.chair_preview_geometry"
            )
        ]
        self.assertEqual(1, len(direct_imports))
        self.assertEqual(
            set(
                CHAIR_PREVIEW_DATA_NAMES
                + CHAIR_PREVIEW_FUNCTION_NAMES
            ),
            {alias.name for alias in direct_imports[0].names},
        )
        self.assertEqual(3, len(direct_imports[0].names))
        self.assertTrue(
            all(alias.asname is None for alias in direct_imports[0].names)
        )

        candidate_imports = set()
        for node in self.chair_preview_geometry_tree.body:
            if isinstance(node, ast.Import):
                candidate_imports.update(
                    (
                        "import",
                        0,
                        alias.name,
                        alias.asname,
                    )
                    for alias in node.names
                )
            elif isinstance(node, ast.ImportFrom):
                candidate_imports.add(
                    (
                        "from",
                        node.level,
                        node.module,
                        tuple(
                            (alias.name, alias.asname)
                            for alias in node.names
                        ),
                    )
                )
        self.assertEqual(
            {
                ("import", 0, "Rhino.Geometry", "rg"),
                (
                    "from",
                    1,
                    "rhino_primitives",
                    (("line_curve", None), ("point_at", None)),
                ),
            },
            candidate_imports,
        )

        package_reexports = set()
        for node in self.auditorium_generator_init_tree.body:
            if isinstance(node, ast.Import):
                package_reexports.update(
                    alias.name
                    for alias in node.names
                    if alias.name.endswith("chair_preview_geometry")
                )
            elif (
                isinstance(node, ast.ImportFrom)
                and node.module
                and node.module.endswith("chair_preview_geometry")
            ):
                package_reexports.update(
                    alias.asname or alias.name
                    for alias in node.names
                )
        self.assertEqual(set(), package_reexports)

    def test_chair_preview_geometry_fake_rhino_behavior_parity(self):
        line_fixture = [
            (1, 10, 2, 20),
            (-3, -30, -4, -40),
        ]
        arc_fixture = [
            (5, 50, 6, 60, 7, 70),
            (8, 80, 9, 90, 10, 100),
            (-11, -110, -12, -120, -13, -130),
        ]
        validity = (True, False, True)

        def exercise(tree):
            stage_point = {"marker": "stage"}
            audience_direction = ["audience", 1]
            runtime = {
                "point_calls": [],
                "line_calls": [],
                "arc_calls": [],
                "arc_curve_calls": [],
            }

            def fake_point_at(
                received_stage_point,
                received_audience_direction,
                row_x_mm,
                floor_z_mm,
                mm_scale,
            ):
                runtime["point_calls"].append(
                    (
                        received_stage_point is stage_point,
                        (
                            received_audience_direction
                            is audience_direction
                        ),
                        copy.deepcopy(received_stage_point),
                        copy.deepcopy(received_audience_direction),
                        row_x_mm,
                        floor_z_mm,
                        mm_scale,
                    )
                )
                return ("point", row_x_mm, floor_z_mm)

            def fake_line_curve(start, end):
                runtime["line_calls"].append((start, end))
                return ("line-curve", start, end)

            class FakeArc(object):
                def __init__(self, start, middle, end):
                    self.index = len(runtime["arc_calls"])
                    self.points = (start, middle, end)
                    self.IsValid = validity[self.index]
                    runtime["arc_calls"].append(
                        (self.index, self.points, self.IsValid)
                    )

            def fake_arc_curve(arc):
                runtime["arc_curve_calls"].append(arc.index)
                return ("arc-curve", arc.index, arc.points)

            class FakeRhinoGeometry(object):
                pass

            FakeRhinoGeometry.Arc = FakeArc
            FakeRhinoGeometry.ArcCurve = staticmethod(fake_arc_curve)

            chair_lines = copy.deepcopy(line_fixture)
            chair_arcs = copy.deepcopy(arc_fixture)
            loaded = _load_selected_functions(
                tree,
                CHAIR_PREVIEW_FUNCTION_NAMES,
                {
                    "CHAIR_LINE_DATA": chair_lines,
                    "CHAIR_ARC_DATA": chair_arcs,
                    "line_curve": fake_line_curve,
                    "point_at": fake_point_at,
                    "rg": FakeRhinoGeometry,
                },
            )
            call_args = (
                stage_point,
                audience_direction,
                1000.0,
                200.0,
                0.01,
            )
            inputs_before = copy.deepcopy(call_args)
            data_before = copy.deepcopy((chair_lines, chair_arcs))
            result = loaded["build_chair_curves"](*call_args)
            return {
                "result": tuple(result),
                "point_calls": tuple(runtime["point_calls"]),
                "line_calls": tuple(runtime["line_calls"]),
                "arc_calls": tuple(runtime["arc_calls"]),
                "arc_curve_calls": tuple(
                    runtime["arc_curve_calls"]
                ),
                "inputs_before": inputs_before,
                "inputs_after": copy.deepcopy(call_args),
                "data_before": data_before,
                "data_after": copy.deepcopy(
                    (chair_lines, chair_arcs)
                ),
            }

        reference = exercise(self.oracle_tree)
        candidate = exercise(self.chair_preview_geometry_tree)
        self.assert_deep_parity(reference, candidate)

        for capture in (reference, candidate):
            self.assertEqual(
                capture["inputs_before"],
                capture["inputs_after"],
            )
            self.assertEqual(
                capture["data_before"],
                capture["data_after"],
            )

        expected_coordinates = (
            (1001.0, 210.0),
            (1002.0, 220.0),
            (997.0, 170.0),
            (996.0, 160.0),
            (1005.0, 250.0),
            (1006.0, 260.0),
            (1007.0, 270.0),
            (1008.0, 280.0),
            (1009.0, 290.0),
            (1010.0, 300.0),
            (989.0, 90.0),
            (988.0, 80.0),
            (987.0, 70.0),
        )
        self.assertEqual(
            expected_coordinates,
            tuple(
                (call[4], call[5])
                for call in candidate["point_calls"]
            ),
        )
        self.assertTrue(
            all(
                call[0]
                and call[1]
                and call[2] == {"marker": "stage"}
                and call[3] == ["audience", 1]
                and call[6] == 0.01
                for call in candidate["point_calls"]
            )
        )

        points = tuple(
            ("point", x, z)
            for x, z in expected_coordinates
        )
        expected_line_calls = (
            (points[0], points[1]),
            (points[2], points[3]),
        )
        expected_arc_points = (
            points[4:7],
            points[7:10],
            points[10:13],
        )
        self.assertEqual(
            expected_line_calls,
            candidate["line_calls"],
        )
        self.assertEqual(
            (0, 1, 2),
            tuple(call[0] for call in candidate["arc_calls"]),
        )
        self.assertEqual(
            expected_arc_points,
            tuple(call[1] for call in candidate["arc_calls"]),
        )
        self.assertEqual(
            validity,
            tuple(call[2] for call in candidate["arc_calls"]),
        )
        self.assertEqual((0, 2), candidate["arc_curve_calls"])
        self.assertEqual(
            tuple(
                ("line-curve", start, end)
                for start, end in expected_line_calls
            )
            + (
                ("arc-curve", 0, expected_arc_points[0]),
                ("arc-curve", 2, expected_arc_points[2]),
            ),
            candidate["result"],
        )

    def test_balcony_preview_geometry_extraction_boundaries(self):
        oracle_nodes = _function_nodes(self.oracle_tree)
        candidate_nodes = _function_nodes(
            self.balcony_preview_geometry_tree
        )
        main_nodes = _function_nodes(self.auditorium_tree)
        reference_functions = _load_selected_functions(
            self.oracle_tree,
            BALCONY_PREVIEW_FUNCTION_NAMES,
            {},
        )
        candidate_functions = _load_selected_functions(
            self.balcony_preview_geometry_tree,
            BALCONY_PREVIEW_FUNCTION_NAMES,
            {},
        )

        self.assertEqual(
            list(BALCONY_PREVIEW_FUNCTION_NAMES),
            [
                node.name
                for node in self.balcony_preview_geometry_tree.body
                if isinstance(node, ast.FunctionDef)
            ],
        )
        for name in BALCONY_PREVIEW_FUNCTION_NAMES:
            with self.subTest(function=name):
                self.assertIn(name, oracle_nodes)
                self.assertIn(name, candidate_nodes)
                self.assertNotIn(name, main_nodes)
                self.assertEqual(
                    ast.dump(
                        oracle_nodes[name],
                        include_attributes=False,
                    ),
                    ast.dump(
                        candidate_nodes[name],
                        include_attributes=False,
                    ),
                )
                self.assertEqual(
                    ast.dump(
                        oracle_nodes[name].args,
                        include_attributes=False,
                    ),
                    ast.dump(
                        candidate_nodes[name].args,
                        include_attributes=False,
                    ),
                )
                self.assertEqual(
                    str(inspect.signature(reference_functions[name])),
                    str(inspect.signature(candidate_functions[name])),
                )

        direct_imports = [
            node
            for node in self.auditorium_tree.body
            if (
                isinstance(node, ast.ImportFrom)
                and node.module
                == "auditorium_generator.balcony_preview_geometry"
            )
        ]
        self.assertEqual(1, len(direct_imports))
        self.assertEqual(
            ("append_balcony_tier_geometry",),
            tuple(alias.name for alias in direct_imports[0].names),
        )
        self.assertTrue(
            all(alias.asname is None for alias in direct_imports[0].names)
        )

        candidate_imports = set()
        for node in self.balcony_preview_geometry_tree.body:
            if isinstance(node, ast.Import):
                candidate_imports.update(
                    (
                        "import",
                        0,
                        alias.name,
                        alias.asname,
                    )
                    for alias in node.names
                )
            elif isinstance(node, ast.ImportFrom):
                candidate_imports.add(
                    (
                        "from",
                        node.level,
                        node.module,
                        tuple(
                            (alias.name, alias.asname)
                            for alias in node.names
                        ),
                    )
                )
        self.assertEqual(
            {
                (
                    "from",
                    1,
                    "calculations.sections",
                    (("balcony_result_is_displayable", None),),
                ),
                (
                    "from",
                    1,
                    "chair_preview_geometry",
                    (("build_chair_curves", None),),
                ),
                (
                    "from",
                    1,
                    "preview_palette",
                    (
                        ("PREVIEW_AISLE", None),
                        ("PREVIEW_BALCONY", None),
                        ("PREVIEW_BALCONY_RAIL", None),
                        ("PREVIEW_BALCONY_SECOND", None),
                        ("PREVIEW_FULL_STAGE_SIGHT", None),
                        ("PREVIEW_SEAT", None),
                        ("PREVIEW_WARNING", None),
                    ),
                ),
                (
                    "from",
                    1,
                    "rhino_primitives",
                    (("line_curve", None), ("point_at", None)),
                ),
            },
            candidate_imports,
        )

        package_reexports = set()
        for node in self.auditorium_generator_init_tree.body:
            if isinstance(node, ast.Import):
                package_reexports.update(
                    alias.name
                    for alias in node.names
                    if alias.name.endswith(
                        "balcony_preview_geometry"
                    )
                )
            elif (
                isinstance(node, ast.ImportFrom)
                and node.module
                and node.module.endswith(
                    "balcony_preview_geometry"
                )
            ):
                package_reexports.update(
                    alias.asname or alias.name
                    for alias in node.names
                )
        self.assertEqual(set(), package_reexports)

    def test_balcony_preview_geometry_fake_behavior_parity(self):
        colors = {
            name: ("color", name)
            for name in (
                "PREVIEW_AISLE",
                "PREVIEW_BALCONY",
                "PREVIEW_BALCONY_RAIL",
                "PREVIEW_BALCONY_SECOND",
                "PREVIEW_FULL_STAGE_SIGHT",
                "PREVIEW_SEAT",
                "PREVIEW_WARNING",
            )
        }

        def balcony_result(
            tier_index,
            displayable=True,
            railing_collision=False,
            include_violations=True,
        ):
            result = {
                "displayable": displayable,
                "tier_index": tier_index,
                "x_values": [100.0, 200.0, 300.0],
                "base_z_values": [10.0, 20.0, 30.0],
                "eye_x_values": [110.0, 210.0, 310.0],
                "eye_z_values": [1010.0, 1020.0, 1030.0],
                "row_count": 3,
                "railing_front_x": 50.0,
                "railing_floor_z": 5.0,
                "railing_top_z": 900.0,
                "railing_rear_x": 60.0,
                "railing_sight_collision": railing_collision,
            }
            if include_violations:
                result["sightline_violations"] = [
                    False,
                    True,
                    False,
                ]
            return result

        scenarios = {
            "not_displayable": {
                "result": balcony_result(0, displayable=False),
                "params": {
                    "show_seats": True,
                    "show_eye_points": True,
                    "show_sightlines": True,
                    "aisle_width": 40.0,
                },
            },
            "tier_1_all_visible": {
                "result": balcony_result(0),
                "params": {
                    "show_seats": True,
                    "show_eye_points": True,
                    "show_sightlines": True,
                    "aisle_width": 40.0,
                },
            },
            "tier_2_default_sight_status": {
                "result": balcony_result(
                    1,
                    railing_collision=True,
                    include_violations=False,
                ),
                "params": {
                    "show_seats": False,
                    "show_eye_points": True,
                    "show_sightlines": True,
                    "aisle_width": 0.0,
                },
            },
        }

        def exercise(tree, scenario):
            result = copy.deepcopy(scenario["result"])
            params = copy.deepcopy(scenario["params"])
            stage_point = {"marker": "stage"}
            direction = ["audience", 1]
            stage_sight_point = ("sight-point", "lower")
            stage_upper_sight_point = ("sight-point", "upper")
            events = []

            def fake_is_displayable(received_result):
                events.append(
                    (
                        "display",
                        received_result is result,
                        received_result["tier_index"],
                        received_result["displayable"],
                    )
                )
                return received_result["displayable"]

            def fake_point_at(
                received_stage_point,
                received_direction,
                x_value,
                z_value,
                received_scale,
            ):
                events.append(
                    (
                        "point",
                        received_stage_point is stage_point,
                        received_direction is direction,
                        x_value,
                        z_value,
                        received_scale,
                    )
                )
                return ("point", x_value, z_value)

            def fake_line_curve(start, end):
                events.append(("line", start, end))
                return ("line", start, end)

            def fake_build_chair_curves(
                received_stage_point,
                received_direction,
                row_x,
                floor_z,
                received_scale,
            ):
                events.append(
                    (
                        "chair",
                        received_stage_point is stage_point,
                        received_direction is direction,
                        row_x,
                        floor_z,
                        received_scale,
                    )
                )
                return [
                    ("chair", row_x, floor_z, 0),
                    ("chair", row_x, floor_z, 1),
                ]

            fake_globals = dict(colors)
            fake_globals.update(
                {
                    "balcony_result_is_displayable": (
                        fake_is_displayable
                    ),
                    "build_chair_curves": fake_build_chair_curves,
                    "line_curve": fake_line_curve,
                    "point_at": fake_point_at,
                }
            )
            loaded = _load_selected_functions(
                tree,
                BALCONY_PREVIEW_FUNCTION_NAMES,
                fake_globals,
            )

            preview_curves = [("sentinel", "preview_curves")]
            preview_points = [("sentinel", "preview_points")]
            bake_curves = [("sentinel", "bake_curves")]
            bake_points = [("sentinel", "bake_points")]
            collection_objects = (
                preview_curves,
                preview_points,
                bake_curves,
                bake_points,
            )

            def input_snapshot():
                return {
                    "result": copy.deepcopy(result),
                    "params": copy.deepcopy(params),
                    "stage_point": copy.deepcopy(stage_point),
                    "direction": copy.deepcopy(direction),
                    "stage_sight_point": copy.deepcopy(
                        stage_sight_point
                    ),
                    "stage_upper_sight_point": copy.deepcopy(
                        stage_upper_sight_point
                    ),
                }

            inputs_before = input_snapshot()
            outputs_before = copy.deepcopy(collection_objects)
            returned = loaded[
                "append_balcony_tier_geometry"
            ](
                result,
                stage_point,
                direction,
                0.01,
                params,
                stage_sight_point,
                stage_upper_sight_point,
                preview_curves,
                preview_points,
                bake_curves,
                bake_points,
            )
            return {
                "returned": returned,
                "events": tuple(events),
                "inputs_before": inputs_before,
                "inputs_after": input_snapshot(),
                "outputs_before": outputs_before,
                "outputs": {
                    "preview_curves": copy.deepcopy(preview_curves),
                    "preview_points": copy.deepcopy(preview_points),
                    "bake_curves": copy.deepcopy(bake_curves),
                    "bake_points": copy.deepcopy(bake_points),
                },
                "list_identity_preserved": tuple(
                    current is original
                    for current, original in zip(
                        (
                            preview_curves,
                            preview_points,
                            bake_curves,
                            bake_points,
                        ),
                        collection_objects,
                    )
                ),
            }

        captures = {}
        for scenario_name, scenario in scenarios.items():
            with self.subTest(scenario=scenario_name):
                reference = exercise(self.oracle_tree, scenario)
                candidate = exercise(
                    self.balcony_preview_geometry_tree,
                    scenario,
                )
                self.assert_deep_parity(reference, candidate)
                self.assertIsNone(candidate["returned"])
                self.assertEqual(
                    candidate["inputs_before"],
                    candidate["inputs_after"],
                )
                self.assertEqual(
                    (True, True, True, True),
                    candidate["list_identity_preserved"],
                )
                captures[scenario_name] = candidate

        hidden = captures["not_displayable"]
        self.assertEqual(
            (("display", True, 0, False),),
            hidden["events"],
        )
        self.assertEqual(
            {
                "preview_curves": [
                    ("sentinel", "preview_curves")
                ],
                "preview_points": [
                    ("sentinel", "preview_points")
                ],
                "bake_curves": [("sentinel", "bake_curves")],
                "bake_points": [("sentinel", "bake_points")],
            },
            hidden["outputs"],
        )
        self.assertEqual(
            hidden["outputs_before"],
            tuple(hidden["outputs"].values()),
        )

        tier_1 = captures["tier_1_all_visible"]
        tier_1_outputs = tier_1["outputs"]
        self.assertEqual(
            (20, 4, 20, 4),
            tuple(
                len(tier_1_outputs[name])
                for name in (
                    "preview_curves",
                    "preview_points",
                    "bake_curves",
                    "bake_points",
                )
            ),
        )
        self.assertEqual(
            (
                "display",
                "point", "chair", "line", "line",
                "point", "chair", "line",
                "point", "chair", "line", "line",
                "point", "point", "point", "line", "line",
                "point", "line",
                "point", "point", "point", "line", "line",
                "point", "point", "point", "line", "line",
                "point", "point", "line",
            ),
            tuple(event[0] for event in tier_1["events"]),
        )
        self.assertEqual(
            (
                "Balcony01Chair",
                "Balcony01Chair",
                "Balcony01FullStageSightlineLower",
                "Balcony01FullStageSightlineUpper",
                "Balcony01Chair",
                "Balcony01Chair",
                "Balcony01Sightline",
                "Balcony01Chair",
                "Balcony01Chair",
                "Balcony01FullStageSightlineLower",
                "Balcony01FullStageSightlineUpper",
                "Balcony01RailingFront",
                "Balcony01RailingTop",
                "Balcony01Floor",
                "Balcony01Floor",
                "Balcony01Floor",
                "Balcony01Floor",
                "Balcony01Floor",
                "Balcony01RearAisle",
            ),
            tuple(
                entry[2]
                for entry in tier_1_outputs["bake_curves"][1:]
            ),
        )
        self.assertEqual(
            tuple(
                entry[0]
                for entry in tier_1_outputs["preview_curves"][1:]
            ),
            tuple(
                entry[0]
                for entry in tier_1_outputs["bake_curves"][1:]
            ),
        )
        self.assertEqual(
            (
                ("color", "PREVIEW_SEAT"),
                ("color", "PREVIEW_SEAT"),
                ("color", "PREVIEW_FULL_STAGE_SIGHT"),
                ("color", "PREVIEW_FULL_STAGE_SIGHT"),
                ("color", "PREVIEW_WARNING"),
                ("color", "PREVIEW_WARNING"),
                ("color", "PREVIEW_WARNING"),
                ("color", "PREVIEW_SEAT"),
                ("color", "PREVIEW_SEAT"),
                ("color", "PREVIEW_FULL_STAGE_SIGHT"),
                ("color", "PREVIEW_FULL_STAGE_SIGHT"),
                ("color", "PREVIEW_BALCONY_RAIL"),
                ("color", "PREVIEW_BALCONY_RAIL"),
                ("color", "PREVIEW_WARNING"),
                ("color", "PREVIEW_WARNING"),
                ("color", "PREVIEW_WARNING"),
                ("color", "PREVIEW_WARNING"),
                ("color", "PREVIEW_WARNING"),
                ("color", "PREVIEW_AISLE"),
            ),
            tuple(
                entry[1]
                for entry in tier_1_outputs["preview_curves"][1:]
            ),
        )
        self.assertEqual(
            (
                2, 2, 2, 2, 2, 2, 1, 2, 2, 2, 2,
                4, 4, 4, 4, 4, 4, 4, 4,
            ),
            tuple(
                entry[2]
                for entry in tier_1_outputs["preview_curves"][1:]
            ),
        )
        self.assertEqual(
            (
                (
                    ("point", 110.0, 1010.0),
                    ("color", "PREVIEW_BALCONY"),
                    5,
                ),
                (
                    ("point", 210.0, 1020.0),
                    ("color", "PREVIEW_WARNING"),
                    5,
                ),
                (
                    ("point", 310.0, 1030.0),
                    ("color", "PREVIEW_BALCONY"),
                    5,
                ),
            ),
            tuple(tier_1_outputs["preview_points"][1:]),
        )
        self.assertEqual(
            (
                "Balcony01SightPoint",
                "Balcony01SightPoint",
                "Balcony01SightPoint",
            ),
            tuple(
                entry[2]
                for entry in tier_1_outputs["bake_points"][1:]
            ),
        )
        self.assertEqual(
            tuple(
                entry[:2]
                for entry in tier_1_outputs["preview_points"][1:]
            ),
            tuple(
                entry[:2]
                for entry in tier_1_outputs["bake_points"][1:]
            ),
        )

        tier_2 = captures["tier_2_default_sight_status"]
        tier_2_outputs = tier_2["outputs"]
        self.assertEqual(
            (13, 4, 13, 4),
            tuple(
                len(tier_2_outputs[name])
                for name in (
                    "preview_curves",
                    "preview_points",
                    "bake_curves",
                    "bake_points",
                )
            ),
        )
        self.assertNotIn(
            "chair",
            tuple(event[0] for event in tier_2["events"]),
        )
        self.assertEqual(
            (
                "Balcony02FullStageSightlineLower",
                "Balcony02FullStageSightlineUpper",
                "Balcony02Sightline",
                "Balcony02FullStageSightlineLower",
                "Balcony02FullStageSightlineUpper",
                "Balcony02RailingFront",
                "Balcony02RailingTop",
                "Balcony02Floor",
                "Balcony02Floor",
                "Balcony02Floor",
                "Balcony02Floor",
                "Balcony02Floor",
            ),
            tuple(
                entry[2]
                for entry in tier_2_outputs["bake_curves"][1:]
            ),
        )
        self.assertNotIn(
            "Balcony02RearAisle",
            tuple(
                entry[2]
                for entry in tier_2_outputs["bake_curves"][1:]
            ),
        )
        self.assertEqual(
            (
                ("color", "PREVIEW_FULL_STAGE_SIGHT"),
                ("color", "PREVIEW_FULL_STAGE_SIGHT"),
                ("color", "PREVIEW_BALCONY_SECOND"),
                ("color", "PREVIEW_FULL_STAGE_SIGHT"),
                ("color", "PREVIEW_FULL_STAGE_SIGHT"),
                ("color", "PREVIEW_WARNING"),
                ("color", "PREVIEW_WARNING"),
                ("color", "PREVIEW_WARNING"),
                ("color", "PREVIEW_WARNING"),
                ("color", "PREVIEW_WARNING"),
                ("color", "PREVIEW_WARNING"),
                ("color", "PREVIEW_WARNING"),
            ),
            tuple(
                entry[1]
                for entry in tier_2_outputs["preview_curves"][1:]
            ),
        )
        self.assertEqual(
            (
                ("color", "PREVIEW_BALCONY_SECOND"),
                ("color", "PREVIEW_BALCONY_SECOND"),
                ("color", "PREVIEW_BALCONY_SECOND"),
            ),
            tuple(
                entry[1]
                for entry in tier_2_outputs["preview_points"][1:]
            ),
        )
        self.assertEqual(
            (
                "Balcony02SightPoint",
                "Balcony02SightPoint",
                "Balcony02SightPoint",
            ),
            tuple(
                entry[2]
                for entry in tier_2_outputs["bake_points"][1:]
            ),
        )

    def test_seat_preview_geometry_extraction_boundaries(self):
        oracle_assignments = _assignment_nodes(self.oracle_tree)
        candidate_assignments = _assignment_nodes(
            self.seat_preview_geometry_tree
        )
        main_assignments = _assignment_nodes(self.auditorium_tree)

        self.assertEqual(
            set(SEAT_PREVIEW_CONSTANT_NAMES),
            set(candidate_assignments),
        )
        for name in SEAT_PREVIEW_CONSTANT_NAMES:
            with self.subTest(constant=name):
                self.assertNotIn(name, main_assignments)
                self.assertEqual(
                    ast.dump(
                        oracle_assignments[name],
                        include_attributes=False,
                    ),
                    ast.dump(
                        candidate_assignments[name],
                        include_attributes=False,
                    ),
                )
                self.assertEqual(
                    self.oracle[name],
                    ast.literal_eval(candidate_assignments[name].value),
                )

        self.assertEqual(
            400.0,
            ast.literal_eval(
                candidate_assignments[
                    "SEAT_SOURCE_CHAIR_WIDTH"
                ].value
            ),
        )
        self.assertEqual(
            80.0,
            ast.literal_eval(
                candidate_assignments[
                    "SEAT_SOURCE_ARMREST_WIDTH"
                ].value
            ),
        )

        oracle_nodes = _function_nodes(self.oracle_tree)
        candidate_nodes = _function_nodes(
            self.seat_preview_geometry_tree
        )
        main_nodes = _function_nodes(self.auditorium_tree)
        reference_functions = _load_selected_functions(
            self.oracle_tree,
            SEAT_PREVIEW_FUNCTION_NAMES,
            {},
        )
        candidate_functions = _load_selected_functions(
            self.seat_preview_geometry_tree,
            SEAT_PREVIEW_FUNCTION_NAMES,
            {},
        )

        self.assertEqual(
            list(SEAT_PREVIEW_FUNCTION_NAMES),
            [
                node.name
                for node in self.seat_preview_geometry_tree.body
                if isinstance(node, ast.FunctionDef)
            ],
        )
        for name in SEAT_PREVIEW_FUNCTION_NAMES:
            with self.subTest(function=name):
                self.assertNotIn(name, main_nodes)
                self.assertEqual(
                    ast.dump(
                        oracle_nodes[name],
                        include_attributes=False,
                    ),
                    ast.dump(
                        candidate_nodes[name],
                        include_attributes=False,
                    ),
                )
                self.assertEqual(
                    ast.dump(
                        oracle_nodes[name].args,
                        include_attributes=False,
                    ),
                    ast.dump(
                        candidate_nodes[name].args,
                        include_attributes=False,
                    ),
                )
                self.assertEqual(
                    str(inspect.signature(reference_functions[name])),
                    str(inspect.signature(candidate_functions[name])),
                )

        direct_imports = [
            node
            for node in self.auditorium_tree.body
            if (
                isinstance(node, ast.ImportFrom)
                and node.module
                == "auditorium_generator.seat_preview_geometry"
            )
        ]
        self.assertEqual(1, len(direct_imports))
        self.assertEqual(
            (
                "SEAT_SOURCE_ARMREST_WIDTH",
                "SEAT_SOURCE_CHAIR_WIDTH",
                "build_3d_seat_module_geometry",
                "seat_module_transform",
            ),
            tuple(alias.name for alias in direct_imports[0].names),
        )
        self.assertTrue(
            all(alias.asname is None for alias in direct_imports[0].names)
        )

        candidate_imports = set()
        for node in self.seat_preview_geometry_tree.body:
            if isinstance(node, ast.Import):
                candidate_imports.update(
                    (
                        "import",
                        0,
                        alias.name,
                        alias.asname,
                    )
                    for alias in node.names
                )
            elif isinstance(node, ast.ImportFrom):
                candidate_imports.add(
                    (
                        "from",
                        node.level,
                        node.module,
                        tuple(
                            (alias.name, alias.asname)
                            for alias in node.names
                        ),
                    )
                )
        self.assertEqual(
            {
                ("import", 0, "Rhino.Geometry", "rg"),
                (
                    "from",
                    1,
                    "calculations.seating",
                    (("calculate_3d_seat_placements", None),),
                ),
                (
                    "from",
                    1,
                    "preview_palette",
                    (
                        ("PREVIEW_3D_ARMREST", None),
                        ("PREVIEW_3D_CHAIR", None),
                    ),
                ),
                (
                    "from",
                    1,
                    "rhino_primitives",
                    (
                        ("get_stage_directions", None),
                        ("point_at", None),
                    ),
                ),
            },
            candidate_imports,
        )

        package_reexports = set()
        for node in self.auditorium_generator_init_tree.body:
            if isinstance(node, ast.Import):
                package_reexports.update(
                    alias.name
                    for alias in node.names
                    if alias.name.endswith("seat_preview_geometry")
                )
            elif (
                isinstance(node, ast.ImportFrom)
                and node.module
                and node.module.endswith("seat_preview_geometry")
            ):
                package_reexports.update(
                    alias.asname or alias.name
                    for alias in node.names
                )
        self.assertEqual(set(), package_reexports)

    def test_seat_preview_geometry_fake_rhino_behavior_parity(self):
        chair_color = ("preview-color", "chair")
        armrest_color = ("preview-color", "armrest")
        placement_fixture = {
            "chair_placements": [
                {
                    "marker": "chair-0",
                    "row_x": 1000.0,
                    "floor_z": 200.0,
                    "lateral": -500.0,
                },
                {
                    "marker": "chair-1",
                    "row_x": 2000.0,
                    "floor_z": 400.0,
                    "lateral": 500.0,
                },
            ],
            "armrest_placements": [
                {
                    "marker": "armrest-0",
                    "row_x": 1000.0,
                    "floor_z": 200.0,
                    "lateral": -1000.0,
                },
                {
                    "marker": "armrest-1",
                    "row_x": 2000.0,
                    "floor_z": 400.0,
                    "lateral": 1000.0,
                },
            ],
            "chairs_per_row": 2,
            "armrests_per_row": 2,
            "sentinel": {"kept": [1, 2]},
        }

        def exercise(tree, include_source_meshes):
            runtime = {
                "calls": [],
                "aggregates": [],
            }

            class FakeVector(object):
                def __init__(self, x, y, z):
                    self.X = x
                    self.Y = y
                    self.Z = z

                def __mul__(self, scale):
                    return FakeVector(
                        self.X * scale,
                        self.Y * scale,
                        self.Z * scale,
                    )

                def snapshot(self):
                    return (self.X, self.Y, self.Z)

            class FakePoint(object):
                def __init__(self, x, y, z):
                    self.X = x
                    self.Y = y
                    self.Z = z

                def __iadd__(self, vector):
                    self.X += vector.X
                    self.Y += vector.Y
                    self.Z += vector.Z
                    return self

                def snapshot(self):
                    return (self.X, self.Y, self.Z)

            def matrix_snapshot(matrix):
                return tuple(
                    getattr(matrix, "M{0}{1}".format(row, column))
                    for row in range(4)
                    for column in range(4)
                )

            class FakeMatrix(object):
                def __init__(self):
                    for row in range(4):
                        for column in range(4):
                            setattr(
                                self,
                                "M{0}{1}".format(row, column),
                                1.0 if row == column else 0.0,
                            )

            class FakeTransformFactory(object):
                @property
                def Identity(self):
                    return FakeMatrix()

            class FakeFaces(object):
                def __init__(self, count):
                    self.Count = count

            class FakeNormals(object):
                def __init__(self, owner):
                    self.owner = owner
                    self.compute_calls = 0

                def ComputeNormals(self):
                    self.compute_calls += 1
                    runtime["calls"].append(
                        ("normals", self.owner.marker)
                    )

            class FakeMesh(object):
                def __init__(self, marker=None, face_count=0):
                    is_aggregate = marker is None
                    if is_aggregate:
                        marker = "aggregate-{0}".format(
                            len(runtime["aggregates"])
                        )
                    self.marker = marker
                    self.Faces = FakeFaces(face_count)
                    self.Normals = FakeNormals(self)
                    self.compact_calls = 0
                    self.appended = []
                    self.transforms = []
                    if is_aggregate:
                        runtime["aggregates"].append(self)

                def DuplicateMesh(self):
                    duplicate_index = 1 + sum(
                        1
                        for call in runtime["calls"]
                        if (
                            call[0] == "duplicate"
                            and call[1] == self.marker
                        )
                    )
                    duplicate = FakeMesh(
                        "{0}-copy-{1}".format(
                            self.marker,
                            duplicate_index,
                        ),
                        self.Faces.Count,
                    )
                    runtime["calls"].append(
                        (
                            "duplicate",
                            self.marker,
                            duplicate.marker,
                            self.Faces.Count,
                        )
                    )
                    return duplicate

                def Transform(self, transform):
                    snapshot = matrix_snapshot(transform)
                    self.transforms.append(snapshot)
                    runtime["calls"].append(
                        ("transform", self.marker, snapshot)
                    )

                def Append(self, mesh):
                    appended = (
                        mesh.marker,
                        mesh.Faces.Count,
                        tuple(mesh.transforms),
                    )
                    self.appended.append(appended)
                    self.Faces.Count += mesh.Faces.Count
                    runtime["calls"].append(
                        ("append", self.marker, appended)
                    )

                def Compact(self):
                    self.compact_calls += 1
                    runtime["calls"].append(
                        ("compact", self.marker)
                    )

                def snapshot(self):
                    return {
                        "marker": self.marker,
                        "faces": self.Faces.Count,
                        "appended": tuple(self.appended),
                        "normal_calls": self.Normals.compute_calls,
                        "compact_calls": self.compact_calls,
                        "transforms": tuple(self.transforms),
                    }

            class FakeVector3d(object):
                ZAxis = FakeVector(0.0, 0.0, 1.0)

            class FakeRhinoGeometry(object):
                pass

            FakeRhinoGeometry.Transform = FakeTransformFactory()
            FakeRhinoGeometry.Vector3d = FakeVector3d
            FakeRhinoGeometry.Mesh = FakeMesh

            stage_point = FakePoint(10.0, 20.0, 30.0)
            audience_direction = FakeVector(0.8, 0.6, 0.0)
            stage_right_direction = FakeVector(0.6, -0.8, 0.0)
            stage_back_direction = FakeVector(-0.8, -0.6, 0.0)
            params = {
                "seat_module_width": 550.0,
                "sentinel": ["params"],
            }
            section_result = {
                "x_values": [1000.0, 2000.0],
                "base_z_values": [200.0, 400.0],
                "sentinel": ["section"],
            }

            def fake_calculate_placements(
                received_params,
                received_section_result,
            ):
                runtime["calls"].append(
                    (
                        "calculate",
                        received_params is params,
                        received_section_result is section_result,
                        copy.deepcopy(received_params),
                        copy.deepcopy(received_section_result),
                    )
                )
                return copy.deepcopy(placement_fixture)

            def fake_get_stage_directions(received_direction):
                runtime["calls"].append(
                    (
                        "directions",
                        received_direction is audience_direction,
                        received_direction.snapshot(),
                    )
                )
                return stage_right_direction, stage_back_direction

            def fake_point_at(
                received_stage_point,
                received_direction,
                row_x_mm,
                floor_z_mm,
                mm_scale,
            ):
                runtime["calls"].append(
                    (
                        "point_at",
                        received_stage_point is stage_point,
                        received_direction is audience_direction,
                        row_x_mm,
                        floor_z_mm,
                        mm_scale,
                    )
                )
                return FakePoint(
                    (
                        received_stage_point.X
                        + received_direction.X * row_x_mm * mm_scale
                    ),
                    (
                        received_stage_point.Y
                        + received_direction.Y * row_x_mm * mm_scale
                    ),
                    received_stage_point.Z + floor_z_mm * mm_scale,
                )

            loaded = _load_selected_functions(
                tree,
                SEAT_PREVIEW_FUNCTION_NAMES,
                {
                    "SEAT_SOURCE_CHAIR_WIDTH": 400.0,
                    "SEAT_SOURCE_ARMREST_WIDTH": 80.0,
                    "PREVIEW_3D_CHAIR": chair_color,
                    "PREVIEW_3D_ARMREST": armrest_color,
                    "calculate_3d_seat_placements": (
                        fake_calculate_placements
                    ),
                    "get_stage_directions": fake_get_stage_directions,
                    "point_at": fake_point_at,
                    "rg": FakeRhinoGeometry,
                },
            )

            seat_source = {
                "chair": {
                    "preview_mesh": (
                        FakeMesh("chair-source", 2)
                        if include_source_meshes
                        else None
                    ),
                    "sentinel": ["chair-source"],
                },
                "armrest": {
                    "preview_mesh": (
                        FakeMesh("armrest-source", 3)
                        if include_source_meshes
                        else None
                    ),
                    "sentinel": ["armrest-source"],
                },
            }

            def seat_source_snapshot():
                return {
                    key: {
                        "preview_mesh": (
                            None
                            if value["preview_mesh"] is None
                            else value["preview_mesh"].snapshot()
                        ),
                        "sentinel": copy.deepcopy(value["sentinel"]),
                    }
                    for key, value in seat_source.items()
                }

            def input_snapshot():
                return {
                    "seat_source": seat_source_snapshot(),
                    "params": copy.deepcopy(params),
                    "section_result": copy.deepcopy(section_result),
                    "stage_point": stage_point.snapshot(),
                    "audience_direction": (
                        audience_direction.snapshot()
                    ),
                    "stage_right_direction": (
                        stage_right_direction.snapshot()
                    ),
                    "stage_back_direction": (
                        stage_back_direction.snapshot()
                    ),
                    "placement_fixture": copy.deepcopy(
                        placement_fixture
                    ),
                }

            inputs_before = input_snapshot()
            result = loaded["build_3d_seat_module_geometry"](
                seat_source,
                params,
                section_result,
                stage_point,
                audience_direction,
                0.01,
                placement_name="Tier1",
            )
            inputs_after = input_snapshot()

            normalized_result = {}
            for key, value in result.items():
                if key == "preview_meshes":
                    normalized_result[key] = tuple(
                        (mesh.snapshot(), color)
                        for mesh, color in value
                    )
                elif key == "bake_instances":
                    normalized_result[key] = tuple(
                        (
                            component,
                            matrix_snapshot(transform),
                            color,
                            name,
                        )
                        for component, transform, color, name in value
                    )
                else:
                    normalized_result[key] = copy.deepcopy(value)

            return {
                "result": normalized_result,
                "calls": tuple(runtime["calls"]),
                "aggregates": tuple(
                    mesh.snapshot()
                    for mesh in runtime["aggregates"]
                ),
                "inputs_before": inputs_before,
                "inputs_after": inputs_after,
            }

        reference_full = exercise(self.oracle_tree, True)
        candidate_full = exercise(
            self.seat_preview_geometry_tree,
            True,
        )
        reference_none = exercise(self.oracle_tree, False)
        candidate_none = exercise(
            self.seat_preview_geometry_tree,
            False,
        )
        self.assert_deep_parity(reference_full, candidate_full)
        self.assert_deep_parity(reference_none, candidate_none)

        for capture in (
            reference_full,
            candidate_full,
            reference_none,
            candidate_none,
        ):
            self.assertEqual(
                capture["inputs_before"],
                capture["inputs_after"],
            )

        full_result = candidate_full["result"]
        none_result = candidate_none["result"]
        self.assertEqual(
            set(placement_fixture)
            | {
                "preview_meshes",
                "bake_instances",
                "chair_x_scale",
                "target_chair_width",
                "placement_name",
            },
            set(full_result),
        )
        self.assertEqual(470.0, full_result["target_chair_width"])
        self.assertEqual(1.175, full_result["chair_x_scale"])
        self.assertEqual("Tier1", full_result["placement_name"])
        self.assertEqual(
            placement_fixture["chair_placements"],
            full_result["chair_placements"],
        )
        self.assertEqual(
            placement_fixture["armrest_placements"],
            full_result["armrest_placements"],
        )

        bake_instances = full_result["bake_instances"]
        self.assertEqual(
            ("chair", "chair", "armrest", "armrest"),
            tuple(entry[0] for entry in bake_instances),
        )
        self.assertEqual(
            (
                chair_color,
                chair_color,
                armrest_color,
                armrest_color,
            ),
            tuple(entry[2] for entry in bake_instances),
        )
        self.assertEqual(
            (
                "Tier1Chair3D",
                "Tier1Chair3D",
                "Tier1Armrest3D",
                "Tier1Armrest3D",
            ),
            tuple(entry[3] for entry in bake_instances),
        )

        def expected_matrix(local_x_scale, translation):
            return (
                0.6 * 0.01 * local_x_scale,
                0.8 * 0.01,
                0.0,
                translation[0],
                -0.8 * 0.01 * local_x_scale,
                0.6 * 0.01,
                0.0,
                translation[1],
                0.0,
                0.0,
                0.01,
                translation[2],
                0.0,
                0.0,
                0.0,
                1.0,
            )

        expected_matrices = (
            expected_matrix(1.175, (15.0, 30.0, 32.0)),
            expected_matrix(1.175, (29.0, 28.0, 34.0)),
            expected_matrix(1.0, (12.0, 34.0, 32.0)),
            expected_matrix(1.0, (32.0, 24.0, 34.0)),
        )
        for actual, expected in zip(
            (entry[1] for entry in bake_instances),
            expected_matrices,
        ):
            for actual_value, expected_value in zip(actual, expected):
                self.assertAlmostEqual(
                    expected_value,
                    actual_value,
                    places=12,
                )

        self.assertEqual(
            (chair_color, armrest_color),
            tuple(
                color
                for unused_mesh, color in full_result[
                    "preview_meshes"
                ]
            ),
        )
        chair_preview, armrest_preview = (
            mesh
            for mesh, unused_color in full_result["preview_meshes"]
        )
        self.assertEqual(4, chair_preview["faces"])
        self.assertEqual(6, armrest_preview["faces"])
        self.assertEqual(
            ("chair-source-copy-1", "chair-source-copy-2"),
            tuple(item[0] for item in chair_preview["appended"]),
        )
        self.assertEqual(
            ("armrest-source-copy-1", "armrest-source-copy-2"),
            tuple(item[0] for item in armrest_preview["appended"]),
        )
        for preview in (chair_preview, armrest_preview):
            self.assertEqual(1, preview["normal_calls"])
            self.assertEqual(1, preview["compact_calls"])

        self.assertEqual((), none_result["preview_meshes"])
        self.assertEqual(
            full_result["bake_instances"],
            none_result["bake_instances"],
        )
        self.assertEqual(2, len(candidate_none["aggregates"]))
        for aggregate in candidate_none["aggregates"]:
            self.assertEqual(0, aggregate["faces"])
            self.assertEqual((), aggregate["appended"])
            self.assertEqual(0, aggregate["normal_calls"])
            self.assertEqual(0, aggregate["compact_calls"])

        self.assertEqual(
            (
                (1000.0, 200.0, 0.01),
                (2000.0, 400.0, 0.01),
                (1000.0, 200.0, 0.01),
                (2000.0, 400.0, 0.01),
            ),
            tuple(
                call[3:]
                for call in candidate_full["calls"]
                if call[0] == "point_at"
            ),
        )

    def test_seat_source_extraction_boundaries(self):
        oracle_nodes = _function_nodes(self.oracle_tree)
        candidate_nodes = _function_nodes(self.seat_source_tree)
        main_nodes = _function_nodes(self.auditorium_tree)
        reference_functions = _load_selected_functions(
            self.oracle_tree,
            SEAT_SOURCE_FUNCTION_NAMES,
            {},
        )
        candidate_functions = _load_selected_functions(
            self.seat_source_tree,
            SEAT_SOURCE_FUNCTION_NAMES,
            {},
        )

        self.assertEqual(
            list(SEAT_SOURCE_FUNCTION_NAMES),
            [
                node.name
                for node in self.seat_source_tree.body
                if isinstance(node, ast.FunctionDef)
            ],
        )
        for name in SEAT_SOURCE_FUNCTION_NAMES:
            with self.subTest(function=name):
                self.assertIn(name, oracle_nodes)
                self.assertIn(name, candidate_nodes)
                self.assertNotIn(name, main_nodes)
                self.assertEqual(
                    ast.dump(
                        oracle_nodes[name],
                        include_attributes=False,
                    ),
                    ast.dump(
                        candidate_nodes[name],
                        include_attributes=False,
                    ),
                )
                self.assertEqual(
                    ast.dump(
                        oracle_nodes[name].args,
                        include_attributes=False,
                    ),
                    ast.dump(
                        candidate_nodes[name].args,
                        include_attributes=False,
                    ),
                )
                self.assertEqual(
                    str(inspect.signature(reference_functions[name])),
                    str(inspect.signature(candidate_functions[name])),
                )

        oracle_assignments = _assignment_nodes(self.oracle_tree)
        candidate_assignments = _assignment_nodes(
            self.seat_source_tree
        )
        main_assignments = _assignment_nodes(self.auditorium_tree)
        self.assertEqual(
            ast.dump(
                oracle_assignments["SEAT_SOURCE_FILE_NAME"],
                include_attributes=False,
            ),
            ast.dump(
                candidate_assignments["SEAT_SOURCE_FILE_NAME"],
                include_attributes=False,
            ),
        )
        self.assertNotIn("SEAT_SOURCE_FILE_NAME", main_assignments)
        self.assertIn("_MODULE_FILE_PATH", candidate_assignments)
        self.assertIn("__file__", candidate_assignments)

        direct_imports = [
            node
            for node in self.auditorium_tree.body
            if (
                isinstance(node, ast.ImportFrom)
                and node.module == "auditorium_generator.seat_source"
            )
        ]
        self.assertEqual(1, len(direct_imports))
        self.assertEqual(
            (
                "SEAT_SOURCE_FILE_NAME",
                "auditorium_seat_source_path",
                "choose_seat_source_components",
                "compact_component_name",
                "component_name_kind",
                "duplicate_file3dm_geometry",
                "file3dm_definition_geometry",
                "geometry_collection_bounding_box",
                "load_auditorium_seat_source",
                "normalize_seat_source_component",
                "source_component_candidate",
            ),
            tuple(alias.name for alias in direct_imports[0].names),
        )
        self.assertTrue(
            all(alias.asname is None for alias in direct_imports[0].names)
        )

        candidate_imports = set()
        for node in self.seat_source_tree.body:
            if isinstance(node, ast.Import):
                candidate_imports.update(
                    (
                        "import",
                        0,
                        alias.name,
                        alias.asname,
                    )
                    for alias in node.names
                )
            elif isinstance(node, ast.ImportFrom):
                candidate_imports.add(
                    (
                        "from",
                        node.level,
                        node.module,
                        tuple(
                            (alias.name, alias.asname)
                            for alias in node.names
                        ),
                    )
                )
        self.assertEqual(
            {
                ("import", 0, "os", None),
                ("import", 0, "Rhino", None),
                ("import", 0, "Rhino.Geometry", "rg"),
                (
                    "from",
                    1,
                    "preview_mesh_geometry",
                    (("build_seat_source_preview_mesh", None),),
                ),
                (
                    "from",
                    1,
                    "seat_preview_geometry",
                    (
                        ("SEAT_SOURCE_ARMREST_WIDTH", None),
                        ("SEAT_SOURCE_CHAIR_WIDTH", None),
                    ),
                ),
            },
            candidate_imports,
        )

        package_reexports = set()
        for node in self.auditorium_generator_init_tree.body:
            if isinstance(node, ast.Import):
                package_reexports.update(
                    alias.name
                    for alias in node.names
                    if alias.name.endswith("seat_source")
                )
            elif (
                isinstance(node, ast.ImportFrom)
                and node.module
                and node.module.endswith("seat_source")
            ):
                package_reexports.update(
                    alias.asname or alias.name
                    for alias in node.names
                )
        self.assertEqual(set(), package_reexports)

    def test_seat_source_fake_file3dm_behavior_parity(self):
        relocation_body = [
            node
            for node in self.seat_source_tree.body
            if (
                isinstance(node, ast.Assign)
                and _assigned_names(node)
                & {"SEAT_SOURCE_FILE_NAME", "_MODULE_FILE_PATH", "__file__"}
            )
        ]
        relocation_module = ast.fix_missing_locations(
            ast.Module(body=relocation_body, type_ignores=[])
        )
        relocation_globals = {
            "__builtins__": __builtins__,
            "__file__": str(SEAT_SOURCE_PATH),
            "os": os,
        }
        compiled_relocation = compile(
            relocation_module,
            "<seat-source-relocation>",
            "exec",
        )
        exec(compiled_relocation, relocation_globals)
        exec(compiled_relocation, relocation_globals)
        relocated_functions = _load_selected_functions(
            self.seat_source_tree,
            ("auditorium_seat_source_path",),
            relocation_globals,
        )
        expected_relocated_path = os.path.normpath(
            os.path.join(
                str(AUDITORIUM_PATH.parent),
                os.pardir,
                "AuditoriumSeat.3dm",
            )
        )
        self.assertEqual(
            expected_relocated_path,
            relocated_functions["auditorium_seat_source_path"](),
        )

        def exercise(tree):
            events = []

            class FakePoint(object):
                def __init__(self, x, z):
                    self.X = x
                    self.Z = z

                def snapshot(self):
                    return (self.X, self.Z)

            class FakeBoundingBox(object):
                def __init__(
                    self,
                    minimum_x=None,
                    maximum_x=None,
                    minimum_z=None,
                    maximum_z=None,
                ):
                    self.IsValid = minimum_x is not None
                    if self.IsValid:
                        self.Min = FakePoint(minimum_x, minimum_z)
                        self.Max = FakePoint(maximum_x, maximum_z)
                    else:
                        self.Min = FakePoint(0.0, 0.0)
                        self.Max = FakePoint(0.0, 0.0)

                def Union(self, other):
                    events.append(
                        ("union", self.snapshot(), other.snapshot())
                    )
                    if not other.IsValid:
                        return
                    if not self.IsValid:
                        self.IsValid = True
                        self.Min = FakePoint(
                            other.Min.X,
                            other.Min.Z,
                        )
                        self.Max = FakePoint(
                            other.Max.X,
                            other.Max.Z,
                        )
                        return
                    self.Min.X = min(self.Min.X, other.Min.X)
                    self.Min.Z = min(self.Min.Z, other.Min.Z)
                    self.Max.X = max(self.Max.X, other.Max.X)
                    self.Max.Z = max(self.Max.Z, other.Max.Z)

                def snapshot(self):
                    return (
                        self.IsValid,
                        self.Min.snapshot(),
                        self.Max.snapshot(),
                    )

            class FakeBoundingBoxSource(object):
                @property
                def Empty(self):
                    return FakeBoundingBox()

            class FakeGeometry(object):
                def __init__(
                    self,
                    marker,
                    minimum_x,
                    maximum_x,
                    minimum_z=0.0,
                    maximum_z=100.0,
                ):
                    self.marker = marker
                    self.minimum_x = minimum_x
                    self.maximum_x = maximum_x
                    self.minimum_z = minimum_z
                    self.maximum_z = maximum_z
                    self.transforms = []

                def Duplicate(self):
                    duplicate = FakeGeometry(
                        self.marker + ":copy",
                        self.minimum_x,
                        self.maximum_x,
                        self.minimum_z,
                        self.maximum_z,
                    )
                    duplicate.transforms = list(self.transforms)
                    events.append(
                        ("duplicate", self.marker, duplicate.marker)
                    )
                    return duplicate

                def Transform(self, transform):
                    self.transforms.append(transform)
                    if transform[0] == "scale":
                        factor = transform[1]
                        self.minimum_x *= factor
                        self.maximum_x *= factor
                        self.minimum_z *= factor
                        self.maximum_z *= factor
                    events.append(
                        ("transform", self.marker, transform)
                    )
                    return True

                def GetBoundingBox(self, accurate):
                    events.append(
                        ("bounding_box", self.marker, accurate)
                    )
                    return FakeBoundingBox(
                        self.minimum_x,
                        self.maximum_x,
                        self.minimum_z,
                        self.maximum_z,
                    )

                def snapshot(self):
                    return (
                        self.marker,
                        self.minimum_x,
                        self.maximum_x,
                        self.minimum_z,
                        self.maximum_z,
                        tuple(self.transforms),
                    )

            class FakeInstanceReference(object):
                def __init__(self, definition_id, transform):
                    self.ParentIdefId = definition_id
                    self.Xform = transform

            class FakeTransformSource(object):
                @staticmethod
                def Scale(origin, factor):
                    events.append(("scale", origin, factor))
                    return ("scale", factor)

            class FakePoint3d(object):
                Origin = ("origin",)

            class FakeGeometryApi(object):
                BoundingBox = FakeBoundingBoxSource()
                InstanceReferenceGeometry = FakeInstanceReference
                Point3d = FakePoint3d
                Transform = FakeTransformSource

            class FakeAttributes(object):
                def __init__(
                    self,
                    definition_object,
                    name="",
                    layer_index=0,
                ):
                    self.IsInstanceDefinitionObject = definition_object
                    self.Name = name
                    self.LayerIndex = layer_index

            class FakeFileObject(object):
                def __init__(self, geometry, attributes):
                    self.Geometry = geometry
                    self.Attributes = attributes

            class FakeDefinition(object):
                def __init__(self, definition_id, name, object_ids):
                    self.Id = definition_id
                    self.Name = name
                    self.object_ids = tuple(object_ids)

                def GetObjectIds(self):
                    events.append(
                        ("object_ids", self.Id, self.object_ids)
                    )
                    return self.object_ids

            class FakeDefinitions(list):
                def FindId(self, definition_id):
                    events.append(("find_definition", definition_id))
                    for definition in self:
                        if definition.Id == definition_id:
                            return definition
                    return None

            class FakeObjects(list):
                def __init__(self, entries):
                    list.__init__(
                        self,
                        [file_object for unused_id, file_object in entries],
                    )
                    self.by_id = dict(entries)

                def FindId(self, object_id):
                    events.append(("find_object", object_id))
                    return self.by_id.get(object_id)

            class FakeLayer(object):
                def __init__(self, index, name):
                    self.Index = index
                    self.Name = name

            class FakeSettings(object):
                ModelUnitSystem = "fixture-units"

            class FakeModel(object):
                def __init__(self, definitions, objects, layers):
                    self.Settings = FakeSettings()
                    self.AllInstanceDefinitions = FakeDefinitions(
                        definitions
                    )
                    self.Objects = FakeObjects(objects)
                    self.AllLayers = layers
                    self.dispose_calls = 0

                def Dispose(self):
                    self.dispose_calls += 1
                    events.append(("dispose", self.dispose_calls))

            chair_object = FakeFileObject(
                FakeGeometry("chair-source", -200.0, 200.0, -25.0),
                FakeAttributes(True),
            )
            armrest_object = FakeFileObject(
                FakeGeometry("armrest-source", -40.0, 40.0, 5.0),
                FakeAttributes(True),
            )
            decoration_object = FakeFileObject(
                FakeGeometry("decoration", 0.0, 10.0, 0.0, 10.0),
                FakeAttributes(False, "Decoration", 7),
            )
            definitions = [
                FakeDefinition("chair-id", "ChairBody", ["chair-object"]),
                FakeDefinition(
                    "armrest-id",
                    "Armrest",
                    ["armrest-object"],
                ),
            ]
            objects = [
                ("chair-object", chair_object),
                ("armrest-object", armrest_object),
                ("decoration-object", decoration_object),
            ]
            model = FakeModel(
                definitions,
                objects,
                [FakeLayer(7, "Misc")],
            )

            class FakeFile3dm(object):
                @staticmethod
                def Read(path):
                    events.append(("read", path))
                    return model

            class FakeFileIo(object):
                File3dm = FakeFile3dm

            class FakeRhinoMath(object):
                @staticmethod
                def UnitScale(source_units, target_units):
                    events.append(
                        ("unit_scale", source_units, target_units)
                    )
                    return 1.0

            class FakeUnitSystem(object):
                Millimeters = "millimeters"

            class FakeRhino(object):
                FileIO = FakeFileIo
                RhinoMath = FakeRhinoMath
                UnitSystem = FakeUnitSystem

            class FakePath(object):
                abspath = staticmethod(os.path.abspath)
                dirname = staticmethod(os.path.dirname)
                join = staticmethod(os.path.join)
                normpath = staticmethod(os.path.normpath)

                @staticmethod
                def isfile(path):
                    events.append(("isfile", path))
                    return True

            class FakeStat(object):
                st_mtime = 123456.75
                st_size = 275504

            class FakeOs(object):
                path = FakePath
                pardir = os.pardir

                @staticmethod
                def stat(path):
                    events.append(("stat", path))
                    return FakeStat()

            def fake_preview_mesh(geometries):
                snapshot = tuple(
                    geometry.snapshot()
                    for geometry in geometries
                )
                events.append(("preview_mesh", snapshot))
                return ("preview-mesh", snapshot)

            loaded = _load_selected_functions(
                tree,
                SEAT_SOURCE_FUNCTION_NAMES,
                {
                    "__file__": str(AUDITORIUM_PATH),
                    "os": FakeOs,
                    "Rhino": FakeRhino,
                    "rg": FakeGeometryApi,
                    "SEAT_SOURCE_FILE_NAME": "AuditoriumSeat.3dm",
                    "SEAT_SOURCE_CHAIR_WIDTH": 400.0,
                    "SEAT_SOURCE_ARMREST_WIDTH": 80.0,
                    "build_seat_source_preview_mesh": (
                        fake_preview_mesh
                    ),
                },
            )

            nested_leaf = FakeFileObject(
                FakeGeometry("nested-leaf", 0.0, 20.0),
                FakeAttributes(True),
            )
            nested_definition = FakeDefinition(
                "nested-id",
                "Nested",
                ["nested-object"],
            )
            nested_model = FakeModel(
                [nested_definition],
                [("nested-object", nested_leaf)],
                [],
            )
            nested_result = loaded[
                "duplicate_file3dm_geometry"
            ](
                nested_model,
                FakeInstanceReference(
                    "nested-id",
                    ("nested-transform", 12.0),
                ),
            )
            try:
                loaded["duplicate_file3dm_geometry"](
                    nested_model,
                    FakeInstanceReference(
                        "nested-id",
                        ("unused",),
                    ),
                    set(["nested-id"]),
                )
            except Exception as error:
                circular_error = (
                    type(error).__name__,
                    error.args,
                )
            else:
                circular_error = None

            helper_candidates = [
                {
                    "name": "plain component",
                    "key": "plain",
                    "width": 400.0,
                },
                {
                    "name": "팔걸이 01",
                    "key": "arm",
                    "width": 80.0,
                },
            ]
            helper_before = copy.deepcopy(helper_candidates)
            selected_pair = loaded[
                "choose_seat_source_components"
            ](helper_candidates)
            loaded_source = loaded[
                "load_auditorium_seat_source"
            ]()

            def box_snapshot(box):
                return box.snapshot()

            def component_snapshot(component):
                return {
                    "source_name": component["source_name"],
                    "geometries": tuple(
                        geometry.snapshot()
                        for geometry in component["geometries"]
                    ),
                    "width": component["width"],
                    "source_z_offset": component[
                        "source_z_offset"
                    ],
                    "bounding_box": box_snapshot(
                        component["bounding_box"]
                    ),
                    "preview_mesh": component["preview_mesh"],
                }

            return {
                "path_helper": loaded[
                    "auditorium_seat_source_path"
                ](),
                "compact_names": tuple(
                    loaded["compact_component_name"](name)
                    for name in (
                        None,
                        " Chair Body_01 ",
                        "팔 걸이-02",
                    )
                ),
                "component_kinds": tuple(
                    loaded["component_name_kind"](name)
                    for name in (
                        "Chair Body_01",
                        "팔 걸이-02",
                        "misc",
                    )
                ),
                "selected_pair": tuple(
                    candidate["key"]
                    for candidate in selected_pair
                ),
                "helper_input_before": helper_before,
                "helper_input_after": helper_candidates,
                "nested_result": tuple(
                    geometry.snapshot()
                    for geometry in nested_result
                ),
                "circular_error": circular_error,
                "loaded_source": {
                    "path": loaded_source["path"],
                    "signature": loaded_source["signature"],
                    "status": loaded_source["status"],
                    "chair": component_snapshot(
                        loaded_source["chair"]
                    ),
                    "armrest": component_snapshot(
                        loaded_source["armrest"]
                    ),
                },
                "dispose_calls": model.dispose_calls,
                "events": tuple(events),
            }

        reference = exercise(self.oracle_tree)
        candidate = exercise(self.seat_source_tree)
        self.assert_deep_parity(reference, candidate)

        expected_path = os.path.normpath(
            os.path.join(
                str(AUDITORIUM_PATH.parent),
                os.pardir,
                "AuditoriumSeat.3dm",
            )
        )
        self.assertEqual(expected_path, candidate["path_helper"])
        self.assertEqual(
            expected_path,
            candidate["loaded_source"]["path"],
        )
        self.assertEqual(
            ("chairbody01", "팔걸이02"),
            candidate["compact_names"][1:],
        )
        self.assertEqual(
            ("chair", "armrest", None),
            candidate["component_kinds"],
        )
        self.assertEqual(
            ("plain", "arm"),
            candidate["selected_pair"],
        )
        self.assertEqual(
            candidate["helper_input_before"],
            candidate["helper_input_after"],
        )
        self.assertEqual(
            ("ValueError", (
                "AuditoriumSeat.3dm contains a circular block reference.",
            )),
            candidate["circular_error"],
        )
        self.assertEqual(
            "123456_275504",
            candidate["loaded_source"]["signature"],
        )
        self.assertEqual(
            400.0,
            candidate["loaded_source"]["chair"]["width"],
        )
        self.assertEqual(
            80.0,
            candidate["loaded_source"]["armrest"]["width"],
        )
        self.assertEqual(
            -25.0,
            candidate["loaded_source"]["chair"][
                "source_z_offset"
            ],
        )
        self.assertEqual(1, candidate["dispose_calls"])

    def test_height_formatting_parity_and_boundaries(self):
        expected = {
            173.0: ("H 173 mm", "H 173 mm"),
            173.049: ("H 173 mm", "H 173 mm"),
            173.05: ("H 173.1 mm", "H 173.1 mm"),
            173.1: ("H 173.1 mm", "H 173.1 mm"),
            12345.0: ("H 12345 mm", "H 12,345 mm"),
            12345.1: ("H 12345.1 mm", "H 12,345.1 mm"),
        }
        for value, labels in expected.items():
            with self.subTest(value=value):
                _, riser_label = self.assert_success_parity(
                    "format_riser_height_label",
                    value,
                )
                _, section_label = self.assert_success_parity(
                    "format_section_height_dimension",
                    value,
                )
                self.assertEqual(labels[0], riser_label)
                self.assertEqual(labels[1], section_label)

        for value in ("173", None, float("nan"), float("inf")):
            for function_name in THIRD_WAVE_FORMATTING_FUNCTION_NAMES:
                with self.subTest(function=function_name, value=value):
                    reference, _ = self.assert_call_parity(
                        function_name,
                        value,
                    )
                    self.assertEqual("error", reference["kind"])

    def test_geometry_metadata_name_and_height_parity(self):
        surface_names = {
            "Floor": "StallsFloorSurface",
            "CrossAisle": "StallsCrossAisleSurface",
            "CrossAisleStairRiser": (
                "StallsCrossAisleStairRiserSurface"
            ),
            "CrossAisleStairTread": (
                "StallsCrossAisleStairTreadSurface"
            ),
            "CrossAisleStairFlatRun": (
                "StallsCrossAisleStairFlatRunSurface"
            ),
            "RearCrossAisle": "StallsRearAisleSurface",
            "Balcony01Floor": "Balcony01FloorSurface",
            "Balcony02RearAisle": "Balcony02RearAisleSurface",
            "balcony01Floor": None,
            "Balcony01Railing": None,
            "": None,
        }
        for curve_name, expected_name in surface_names.items():
            with self.subTest(curve_name=curve_name):
                _, candidate = self.assert_success_parity(
                    "section_floor_surface_name",
                    curve_name,
                )
                self.assertEqual(expected_name, candidate)

        envelope_cases = (
            ({"height_group": "main"}, "MainFlyTower"),
            (
                {"height_group": "clearance", "name": "RightStage"},
                "RightStageUpperSpace",
            ),
            (
                {"height_group": "unknown", "name": "Custom"},
                "CustomUpperSpace",
            ),
        )
        for space, expected_name in envelope_cases:
            before = copy.deepcopy(space)
            with self.subTest(space=space):
                _, candidate = self.assert_success_parity(
                    "stage_space_envelope_name",
                    space,
                )
                self.assertEqual(expected_name, candidate)
                geometry_metadata.stage_space_envelope_name(space)
                self.assertEqual(before, space)

        dimensions = {
            "main_tower_top_z": 26000.0,
            "clearance_top_z": 10000.0,
            "right_top_z": 9000.0,
            "custom_top_z": "unchanged",
        }
        top_cases = (
            ({"height_group": "main"}, 26000.0),
            ({"height_group": "clearance"}, 10000.0),
            ({"height_group": "right"}, 9000.0),
            ({"height_group": "custom"}, "unchanged"),
        )
        for space, expected_top in top_cases:
            with self.subTest(space=space):
                _, candidate = self.assert_success_parity(
                    "stage_space_top_z",
                    space,
                    dimensions,
                )
                self.assertEqual(expected_top, candidate)

        error_cases = (
            ("section_floor_surface_name", (None,)),
            ("stage_space_envelope_name", ({},)),
            (
                "stage_space_envelope_name",
                ({"height_group": "right"},),
            ),
            (
                "stage_space_top_z",
                ({"height_group": "rear"}, dimensions),
            ),
        )
        for function_name, args in error_cases:
            with self.subTest(function=function_name, args=args):
                reference, _ = self.assert_call_parity(
                    function_name,
                    *args
                )
                self.assertEqual("error", reference["kind"])

    def test_stage_edge_adjacency_parity_and_input_mutation(self):
        space = {
            "name": "Main",
            "min_x": 0.0,
            "max_x": 10.0,
            "min_y": 0.0,
            "max_y": 20.0,
            "top_z": 100.0,
        }
        spaces = [
            space,
            {
                "name": "Left",
                "min_x": -5.0,
                "max_x": 0.0,
                "min_y": 5.0,
                "max_y": 15.0,
                "top_z": 200.0,
            },
            {
                "name": "Right",
                "min_x": 10.0,
                "max_x": 15.0,
                "min_y": 10.0,
                "max_y": 25.0,
                "top_z": 300.0,
            },
            {
                "name": "Front",
                "min_x": 2.0,
                "max_x": 8.0,
                "min_y": -5.0,
                "max_y": 0.0,
                "top_z": 400.0,
            },
            {
                "name": "Back",
                "min_x": -2.0,
                "max_x": 4.0,
                "min_y": 20.0,
                "max_y": 30.0,
                "top_z": 500.0,
            },
        ]
        expected = {
            "left": ("y", 0.0, (0.0, 20.0), [(5.0, 15.0, 200.0)]),
            "right": (
                "y",
                10.0,
                (0.0, 20.0),
                [(10.0, 20.0, 300.0)],
            ),
            "front": (
                "x",
                0.0,
                (0.0, 10.0),
                [(2.0, 8.0, 400.0)],
            ),
            "back": (
                "x",
                20.0,
                (0.0, 10.0),
                [(0.0, 4.0, 500.0)],
            ),
        }
        space_before = copy.deepcopy(space)
        spaces_before = copy.deepcopy(spaces)
        for edge_name, expected_result in expected.items():
            with self.subTest(edge=edge_name):
                _, candidate = self.assert_success_parity(
                    "stage_edge_adjacencies",
                    space,
                    edge_name,
                    spaces,
                )
                self.assertEqual(expected_result, candidate)

        back_result = geometry_metadata.stage_edge_adjacencies(
            space,
            "back",
            spaces,
        )
        self.assertEqual(
            back_result,
            geometry_metadata.stage_edge_adjacencies(
                space,
                "typo",
                spaces,
            ),
        )
        self.assertEqual(
            back_result,
            geometry_metadata.stage_edge_adjacencies(
                space,
                None,
                spaces,
            ),
        )
        self.assertEqual(space_before, space)
        self.assertEqual(spaces_before, spaces)

        reference, _ = self.assert_call_parity(
            "stage_edge_adjacencies",
            space,
            "left",
            None,
        )
        self.assertEqual("error", reference["kind"])

    def test_stage_normal_boundaries_and_input_mutation(self):
        expected_defaults = _valid_stage_params()
        reference, candidate = self.assert_success_parity(
            "calculated_proscenium_defaults",
            12000.0,
            8000.0,
        )
        self.assertEqual(expected_defaults, candidate)
        self.assert_deep_parity(reference, candidate)

        for opening_width, opening_height in (
            (0.0, 0.0),
            (-1000.0, -500.0),
        ):
            with self.subTest(
                opening_width=opening_width,
                opening_height=opening_height,
            ):
                self.assert_success_parity(
                    "calculated_proscenium_defaults",
                    opening_width,
                    opening_height,
                )

        params = _valid_stage_params()
        params_before = copy.deepcopy(params)
        reference, candidate = self.assert_success_parity(
            "validate_proscenium_params",
            params,
            None,
        )
        self.assertIsNone(reference)
        self.assertIsNone(candidate)
        stage.validate_proscenium_params(params, None)
        self.assertEqual(params_before, params)

        params_3d = copy.deepcopy(params)
        params_3d["stage_preview_mode"] = "space_3d"
        self.assert_success_parity(
            "validate_proscenium_params",
            params_3d,
            12000.0,
        )

        disabled = copy.deepcopy(params)
        for prefix in ("right", "left", "rear"):
            disabled[prefix + "_stage_enabled"] = False
            disabled.pop(prefix + "_stage_width")
            disabled.pop(prefix + "_stage_depth")
            disabled.pop(prefix + "_stage_height")
        disabled["understage_enabled"] = False
        disabled.pop("understage_depth")
        disabled_before = copy.deepcopy(disabled)
        self.assert_success_parity(
            "validate_proscenium_params",
            disabled,
            None,
        )
        stage.validate_proscenium_params(disabled, None)
        self.assertEqual(disabled_before, disabled)

        params_before = copy.deepcopy(params)
        reference, candidate = self.assert_success_parity(
            "calculate_stage_section_dimensions",
            params,
            8000.0,
        )
        self.assertEqual(
            {
                "ph": 8000.0,
                "main_grid_z": 24000.0,
                "main_tower_top_z": 26000.0,
                "right_grid_z": 8000.0,
                "right_top_z": 10000.0,
                "left_grid_z": 8000.0,
                "left_top_z": 10000.0,
                "rear_grid_z": 8000.0,
                "rear_top_z": 10000.0,
                "clearance_grid_z": 8000.0,
                "clearance_top_z": 10000.0,
                "understage_floor_z": -8000.0,
                "understage_bottom_z": -10000.0,
                "auditorium_ceiling_z": 16000.0,
            },
            candidate,
        )
        self.assert_deep_parity(reference, candidate)
        stage.calculate_stage_section_dimensions(params, 8000.0)
        self.assertEqual(params_before, params)

        zero_levels = copy.deepcopy(params)
        for prefix in ("main", "right", "left", "rear"):
            zero_levels[prefix + "_stage_height"] = 0.0
        zero_levels["understage_depth"] = 0.0
        self.assert_success_parity(
            "calculate_stage_section_dimensions",
            zero_levels,
            0.0,
        )

    def test_stage_exception_parity_and_input_mutation(self):
        reference, _ = self.assert_call_parity(
            "calculated_proscenium_defaults",
            "12000",
            8000.0,
        )
        self.assertEqual("error", reference["kind"])

        invalid_values = (
            ("main_stage_width", 0.0),
            ("main_stage_depth", 0.0),
            ("main_stage_height", 2000.0),
            ("stage_preview_mode", "invalid"),
            ("right_stage_width", 0.0),
            ("understage_depth", 2000.0),
        )
        for key, value in invalid_values:
            params = _valid_stage_params()
            params[key] = value
            params_before = copy.deepcopy(params)
            with self.subTest(key=key, value=value):
                reference, _ = self.assert_call_parity(
                    "validate_proscenium_params",
                    params,
                    12000.0,
                )
                self.assertEqual("error", reference["kind"])
                with self.assertRaises(Exception):
                    stage.validate_proscenium_params(params, 12000.0)
                self.assertEqual(params_before, params)

        missing_main_width = _valid_stage_params()
        missing_main_width.pop("main_stage_width")
        reference, _ = self.assert_call_parity(
            "validate_proscenium_params",
            missing_main_width,
            12000.0,
        )
        self.assertEqual("error", reference["kind"])

        missing_height = _valid_stage_params()
        missing_height.pop("rear_stage_height")
        missing_before = copy.deepcopy(missing_height)
        reference, _ = self.assert_call_parity(
            "calculate_stage_section_dimensions",
            missing_height,
            8000.0,
        )
        self.assertEqual("error", reference["kind"])
        with self.assertRaises(Exception):
            stage.calculate_stage_section_dimensions(
                missing_height,
                8000.0,
            )
        self.assertEqual(missing_before, missing_height)

    def test_seating_placements_boundaries_and_input_mutation(self):
        params = _seat_params()
        section_result = _seat_section_result()
        params_before = copy.deepcopy(params)
        section_before = copy.deepcopy(section_result)

        reference, candidate = self.assert_success_parity(
            "calculate_3d_seat_placements",
            params,
            section_result,
        )
        self.assertEqual(32, candidate["chairs_per_row"])
        self.assertEqual(35, candidate["armrests_per_row"])
        self.assertEqual(20000.0, candidate["total_width"])
        self.assertEqual(64, len(candidate["chair_placements"]))
        self.assertEqual(70, len(candidate["armrest_placements"]))
        self.assertEqual(
            -9725.0,
            candidate["chair_placements"][0]["lateral"],
        )
        self.assertEqual(
            9725.0,
            candidate["chair_placements"][-1]["lateral"],
        )
        self.assertEqual(
            -10000.0,
            candidate["armrest_placements"][0]["lateral"],
        )
        self.assertEqual(
            10000.0,
            candidate["armrest_placements"][-1]["lateral"],
        )
        self.assert_deep_parity(reference, candidate)

        direct = seating.calculate_3d_seat_placements(
            params,
            section_result,
        )
        self.assertEqual(params_before, params)
        self.assertEqual(section_before, section_result)
        self.assertEqual(
            direct["total_width"],
            seating.calculate_seat_layout_width(params),
        )
        self.assert_success_parity(
            "calculate_seat_layout_width",
            params,
        )

        empty_params = _seat_params([])
        _, empty = self.assert_success_parity(
            "calculate_3d_seat_placements",
            empty_params,
            section_result,
        )
        self.assertEqual(0, empty["chairs_per_row"])
        self.assertEqual(0, empty["armrests_per_row"])
        self.assertEqual([], empty["chair_placements"])
        self.assertEqual([], empty["armrest_placements"])
        self.assertEqual(0.0, empty["total_width"])
        self.assert_success_parity(
            "calculate_seat_layout_width",
            empty_params,
        )

        zero_params = _seat_params([0])
        _, zero = self.assert_success_parity(
            "calculate_3d_seat_placements",
            zero_params,
            section_result,
        )
        self.assertEqual(0, zero["chairs_per_row"])
        self.assertEqual(1, zero["armrests_per_row"])
        self.assertEqual(0, len(zero["chair_placements"]))
        self.assertEqual(2, len(zero["armrest_placements"]))

        mismatched = {
            "x_values": [8100.0, 9200.0],
            "base_z_values": [-1100.0],
        }
        _, truncated = self.assert_success_parity(
            "calculate_3d_seat_placements",
            params,
            mismatched,
        )
        self.assertEqual(32, len(truncated["chair_placements"]))
        self.assertEqual(35, len(truncated["armrest_placements"]))
        self.assertEqual(
            {0},
            {
                placement["row_index"]
                for placement in truncated["chair_placements"]
            },
        )

    def test_seating_balcony_display_rules_and_helper_identity(self):
        self.assertIs(
            sections.balcony_result_is_displayable,
            seating.balcony_result_is_displayable,
        )

        params = {
            "row_count": 15,
            "seat_block_counts": [8, 16, 8],
        }
        balcony_results = [
            {
                "row_count": 4,
                "lower_limit_violation": False,
            },
            None,
            {
                "row_count": 2,
                "lower_limit_violation": True,
            },
            {
                "row_count": 3,
                "lower_limit_violation": True,
                "rise_interpolation_applied": True,
            },
        ]
        params_before = copy.deepcopy(params)
        balconies_before = copy.deepcopy(balcony_results)
        candidate = seating.calculate_total_3d_seat_count(
            params,
            balcony_results,
        )
        self.assertEqual(768, candidate)
        self.assertEqual(params_before, params)
        self.assertEqual(balconies_before, balcony_results)

        reference, candidate = self.assert_success_parity(
            "calculate_total_3d_seat_count",
            params,
            [],
        )
        self.assertEqual(480, reference)
        self.assertEqual(480, candidate)

    def test_seating_exception_parity_and_input_mutation(self):
        section_result = _seat_section_result()
        cases = (
            (
                "calculate_3d_seat_placements",
                (
                    {
                        "longitudinal_aisle_width": 1200.0,
                        "seat_block_counts": [8, 16, 8],
                    },
                    section_result,
                ),
            ),
            (
                "calculate_3d_seat_placements",
                (
                    {
                        "seat_module_width": 550.0,
                        "longitudinal_aisle_width": 1200.0,
                        "seat_block_counts": None,
                    },
                    section_result,
                ),
            ),
            (
                "calculate_total_3d_seat_count",
                (
                    {
                        "row_count": 15,
                        "seat_block_counts": [8, 16, 8],
                    },
                    None,
                ),
            ),
            (
                "calculate_total_3d_seat_count",
                (
                    {
                        "row_count": 15,
                        "seat_block_counts": [8, 16, 8],
                    },
                    [{}],
                ),
            ),
            (
                "calculate_total_3d_seat_count",
                (
                    {
                        "row_count": 15,
                        "seat_block_counts": [8, 16, 8],
                    },
                    [{"lower_limit_violation": False}],
                ),
            ),
            (
                "calculate_seat_layout_width",
                (
                    {
                        "seat_module_width": 550.0,
                        "seat_block_counts": [8, 16, 8],
                    },
                ),
            ),
        )
        for function_name, args in cases:
            with self.subTest(function=function_name, args=args):
                if function_name == "calculate_total_3d_seat_count":
                    candidate = _capture(
                        seating.calculate_total_3d_seat_count,
                        args,
                        {},
                    )[0]
                    self.assertEqual("error", candidate["kind"])
                else:
                    reference, _ = self.assert_call_parity(
                        function_name,
                        *args
                    )
                    self.assertEqual("error", reference["kind"])

        invalid_params = {
            "longitudinal_aisle_width": 1200.0,
            "seat_block_counts": [8, 16, 8],
        }
        invalid_before = copy.deepcopy(invalid_params)
        with self.assertRaises(Exception):
            seating.calculate_3d_seat_placements(
                invalid_params,
                section_result,
            )
        self.assertEqual(invalid_before, invalid_params)

    def test_numeric_and_small_helper_parity(self):
        for value in (
            173.0,
            173.00000000001,
            173.1,
            173.9,
            -2.2,
        ):
            with self.subTest(helper="ceil_to_integer_mm", value=value):
                self.assert_success_parity("ceil_to_integer_mm", value)

        for value in (
            1.0,
            "2.5",
            None,
            float("nan"),
            float("inf"),
            float("-inf"),
        ):
            with self.subTest(helper="is_finite_number", value=value):
                self.assert_success_parity("is_finite_number", value)

        self.assert_success_parity(
            "calculate_actual_sightline_status",
            [8000.0, 9100.0, 10200.0],
            [0.0, 210.0, 430.0],
            50.0,
            113.0,
        )
        self.assert_success_parity(
            "interpolate_front_anchored_z_values",
            [-1100.0, -600.0, 1700.0],
            2800.0,
            "stalls",
        )
        self.assert_success_parity(
            "interpolate_rear_anchored_z_values",
            [4764.0, 5171.0, 5583.0, 6000.0],
            800.0,
            "balcony",
        )

        for railing_t in (249.0, 250.0):
            self.assert_success_parity(
                "standard_balcony_railing_height",
                railing_t,
            )
        self.assert_success_parity(
            "balcony_height_from_stalls_rear",
            6000.0,
            1700.0,
        )
        self.assert_success_parity(
            "balcony_height_to_absolute",
            4300.0,
            1700.0,
        )

        display_cases = (
            (None, False),
            ({"lower_limit_violation": False}, True),
            ({"lower_limit_violation": True}, True),
            (
                {
                    "lower_limit_violation": True,
                    "rise_interpolation_applied": True,
                },
                True,
            ),
        )
        for result, expected in display_cases:
            self.assertEqual(
                expected,
                sections.balcony_result_is_displayable(result),
            )

    def test_stepped_and_sloped_stalls_parity(self):
        scenarios = (
            ("stepped", [15]),
            ("stepped", [5, 5, 5]),
            ("sloped", [5, 5, 5]),
        )
        for floor_type, groups in scenarios:
            params = _base_params(floor_type)
            params["row_group_counts"] = groups
            with self.subTest(floor_type=floor_type, groups=groups):
                if floor_type == "sloped":
                    reference, candidate = self.assert_success_parity(
                        "calculate_section",
                        params,
                    )
                    self.assertEqual(
                        reference["base_z_values"],
                        candidate["base_z_values"],
                    )
                else:
                    candidate = sections.calculate_section(params)
                    self.assertTrue(
                        any(
                            abs(riser - round(riser)) > 1e-8
                            for riser in candidate["riser_values"][1:]
                        )
                    )
                    self.assertFalse(
                        any(candidate["sightline_violations"])
                    )
                    for index in range(1, params["row_count"]):
                        self.assertGreaterEqual(
                            candidate[
                                "actual_sight_clearance_values"
                            ][index],
                            params["sight_clearance"] - 1e-8,
                        )
                        self.assertAlmostEqual(
                            candidate["riser_values"][index],
                            (
                                candidate["base_z_values"][index]
                                - candidate["base_z_values"][index - 1]
                            ),
                            places=10,
                        )
                        self.assertAlmostEqual(
                            candidate["slope_values"][index],
                            (
                                candidate["riser_values"][index]
                                / params["row_pitch"]
                            ),
                            places=12,
                        )

                if floor_type == "stepped" and groups == [5, 5, 5]:
                    self.assertEqual(8100.0, candidate["x_values"][0])
                    self.assertEqual(25800.0, candidate["x_values"][-1])
                    self.assertGreater(
                        candidate["base_z_values"][-1],
                        candidate["base_z_values"][0],
                    )
                    self.assertEqual(
                        1,
                        candidate["aisle_stair_tread_counts"][10],
                    )
                elif floor_type == "sloped":
                    self.assertEqual(25500.0, candidate["x_values"][-1])
                    self.assertAlmostEqual(
                        2768.2856306480553,
                        (
                            candidate["base_z_values"][-1]
                            - candidate["base_z_values"][0]
                        ),
                        places=10,
                    )

    def test_stalls_interpolation_parity_and_invariants(self):
        params = _base_params()
        candidate_stalls = sections.calculate_section(params)

        for target in (2800.0, 2810.0, 0.0):
            with self.subTest(target=target):
                reference, candidate = self.assert_success_parity(
                    "apply_stalls_rise_interpolation",
                    params,
                    candidate_stalls,
                    target,
                    16000.0,
                )
                self.assertEqual(
                    candidate_stalls["base_z_values"][0],
                    candidate["base_z_values"][0],
                )
                self.assertEqual(
                    target,
                    (
                        candidate["base_z_values"][-1]
                        - candidate["base_z_values"][0]
                    ),
                )
                self.assertEqual(
                    candidate_stalls["x_values"],
                    candidate["x_values"],
                )
                self.assertEqual(
                    candidate_stalls["aisle_stair_tread_counts"],
                    candidate["aisle_stair_tread_counts"],
                )
                self.assertEqual(
                    candidate_stalls["aisle_stair_run_values"],
                    candidate["aisle_stair_run_values"],
                )
                self.assert_deep_parity(reference, candidate)

        self.assert_success_parity(
            "add_stalls_ceiling_validation",
            candidate_stalls,
            16000.0,
        )

    def test_balcony_one_then_two_pipeline_parity(self):
        candidate = _run_two_tier_pipeline(sections)

        self.assertEqual(
            800.0,
            (
                candidate["balcony_1"]["base_z_values"][-1]
                - candidate["balcony_1"]["base_z_values"][0]
            ),
        )
        self.assertEqual(
            6000.0,
            candidate["balcony_1"]["base_z_values"][-1],
        )
        self.assertEqual(
            600.0,
            (
                candidate["balcony_2"]["base_z_values"][-1]
                - candidate["balcony_2"]["base_z_values"][0]
            ),
        )
        self.assertEqual(
            9000.0,
            candidate["balcony_2"]["base_z_values"][-1],
        )
        for result_key, target_rise in (
            ("balcony_1", 800.0),
            ("balcony_2", 600.0),
        ):
            result = candidate[result_key]
            row_count = result["row_count"]
            self.assertEqual(row_count, len(result["x_values"]))
            self.assertEqual(row_count, len(result["base_z_values"]))
            self.assertEqual(row_count, len(result["eye_z_values"]))
            self.assertEqual(
                row_count,
                len(result["riser_to_next_values"]),
            )
            self.assertEqual(target_rise, result["rise_interpolation_target"])
            self.assertEqual(0.0, result["riser_to_next_values"][-1])
            for index in range(row_count - 1):
                self.assertAlmostEqual(
                    result["riser_to_next_values"][index],
                    (
                        result["base_z_values"][index + 1]
                        - result["base_z_values"][index]
                    ),
                    places=10,
                )

        params = _base_params()
        raw_stalls = sections.calculate_section(params)
        tier1_params = sections.normalized_balcony_tier_params(
            params,
            0,
        )
        raw_balcony = sections.calculate_balcony_section(
            tier1_params,
            raw_stalls,
            8000.0,
            tier_index=0,
        )
        self.assertTrue(
            any(
                abs(riser - round(riser)) > 1e-8
                for riser in raw_balcony[
                    "riser_to_next_values"
                ][:-1]
            )
        )
        self.assertFalse(any(raw_balcony["sightline_violations"]))
        self.assertGreaterEqual(
            raw_balcony["minimum_sightline_clearance"],
            params["sight_clearance"] - 1e-8,
        )

    def test_exception_parity(self):
        invalid_targets = (
            ([0.0, 100.0], "not-a-number"),
            ([0.0, 100.0], -1.0),
            ([0.0, 100.0], float("nan")),
            ([0.0, 100.0], float("inf")),
            ([0.0], 10.0),
            ([0.0, 0.0], 10.0),
            ([0.0, float("nan")], 10.0),
        )
        for z_values, target in invalid_targets:
            with self.subTest(z_values=z_values, target=target):
                reference, _ = self.assert_call_parity(
                    "validate_section_rise_target",
                    z_values,
                    target,
                    "section",
                )
                self.assertEqual("error", reference["kind"])

        invalid_groups = _base_params()
        invalid_groups["row_group_counts"] = [5, 5]
        reference, _ = self.assert_call_parity(
            "calculate_section",
            invalid_groups,
        )
        self.assertEqual("error", reference["kind"])

        params = _base_params()
        stalls = _function(self.oracle, "calculate_section")(params)
        descending_z = list(stalls["base_z_values"])
        descending_z[1] = descending_z[0] - 1.0
        reference, _ = self.assert_call_parity(
            "rebuild_stalls_vertical_fields",
            params,
            stalls,
            descending_z,
        )
        self.assertEqual("error", reference["kind"])

        impossible_balcony = dict(params)
        impossible_balcony["balcony_row_count"] = 40
        reference, _ = self.assert_call_parity(
            "calculate_balcony_section",
            impossible_balcony,
            stalls,
            8000.0,
            False,
            0,
        )
        self.assertEqual("error", reference["kind"])

    def test_preview_geometry_extraction_boundaries(self):
        oracle_nodes = _function_nodes(self.oracle_tree)
        candidate_nodes = _function_nodes(self.preview_geometry_tree)
        main_nodes = _function_nodes(self.auditorium_tree)
        reference_functions = _load_selected_functions(
            self.oracle_tree,
            PREVIEW_GEOMETRY_FUNCTION_NAMES,
            {},
        )
        candidate_functions = _load_selected_functions(
            self.preview_geometry_tree,
            PREVIEW_GEOMETRY_FUNCTION_NAMES,
            {},
        )

        self.assertEqual(
            ["build_preview_geometry"],
            [
                node.name
                for node in self.preview_geometry_tree.body
                if isinstance(node, ast.FunctionDef)
            ],
        )
        reference_node = oracle_nodes["build_preview_geometry"]
        candidate_node = candidate_nodes["build_preview_geometry"]
        self.assertNotIn("build_preview_geometry", main_nodes)
        self.assertNotEqual(
            ast.dump(reference_node, include_attributes=False),
            ast.dump(candidate_node, include_attributes=False),
        )
        self.assertEqual(
            ast.dump(reference_node.args, include_attributes=False),
            ast.dump(candidate_node.args, include_attributes=False),
        )
        self.assertEqual(
            str(
                inspect.signature(
                    reference_functions["build_preview_geometry"]
                )
            ),
            str(
                inspect.signature(
                    candidate_functions["build_preview_geometry"]
                )
            ),
        )

        direct_imports = [
            node
            for node in self.auditorium_tree.body
            if (
                isinstance(node, ast.ImportFrom)
                and node.module == "auditorium_generator.preview_geometry"
            )
        ]
        self.assertEqual(1, len(direct_imports))
        self.assertEqual(
            (("build_preview_geometry", None),),
            tuple(
                (alias.name, alias.asname)
                for alias in direct_imports[0].names
            ),
        )

        child_imports = []
        imported_bindings = set()
        for node in self.preview_geometry_tree.body:
            if isinstance(node, ast.Import):
                child_imports.append(
                    (
                        "import",
                        tuple(
                            (alias.name, alias.asname)
                            for alias in node.names
                        ),
                    )
                )
                imported_bindings.update(
                    alias.asname or alias.name.split(".")[0]
                    for alias in node.names
                )
            elif isinstance(node, ast.ImportFrom):
                child_imports.append(
                    (
                        "from",
                        node.level,
                        node.module,
                        tuple(
                            (alias.name, alias.asname)
                            for alias in node.names
                        ),
                    )
                )
                imported_bindings.update(
                    alias.asname or alias.name
                    for alias in node.names
                )

        self.assertEqual(
            [
                ("import", (("Rhino.Geometry", "rg"),)),
                (
                    "from",
                    1,
                    "balcony_height_reference",
                    (
                        ("rebase_balcony_last_platform_z", None),
                        ("stalls_height_reference_z", None),
                    ),
                ),
                (
                    "from",
                    1,
                    "balcony_preview_geometry",
                    (("append_balcony_tier_geometry", None),),
                ),
                (
                    "from",
                    1,
                    "calculations.sections",
                    (
                        ("apply_balcony_rise_interpolation", None),
                        ("apply_stalls_rise_interpolation", None),
                        ("balcony_result_is_displayable", None),
                        ("calculate_balcony_section", None),
                        ("calculate_section", None),
                        ("normalized_balcony_tier_params", None),
                    ),
                ),
                (
                    "from",
                    1,
                    "calculations.stage",
                    (("calculate_stage_section_dimensions", None),),
                ),
                (
                    "from",
                    1,
                    "chair_preview_geometry",
                    (("build_chair_curves", None),),
                ),
                (
                    "from",
                    1,
                    "section_interpolation_constants",
                    (("SECTION_RISE_KEYS", None),),
                ),
                (
                    "from",
                    1,
                    "floor_surface_geometry",
                    (("build_floor_surface_geometry", None),),
                ),
                (
                    "from",
                    1,
                    "preview_palette",
                    (
                        ("PREVIEW_AISLE", None),
                        ("PREVIEW_AUDITORIUM_CEILING", None),
                        ("PREVIEW_BALCONY", None),
                        ("PREVIEW_BALCONY_RAIL", None),
                        ("PREVIEW_FLOOR", None),
                        ("PREVIEW_FULL_STAGE_SIGHT", None),
                        ("PREVIEW_POINT", None),
                        ("PREVIEW_REFERENCE", None),
                        ("PREVIEW_SEAT", None),
                        ("PREVIEW_SIGHT", None),
                        ("PREVIEW_WARNING", None),
                    ),
                ),
                (
                    "from",
                    1,
                    "rhino_primitives",
                    (
                        ("line_curve", None),
                        ("point_at", None),
                        ("unit_scale_from_mm", None),
                    ),
                ),
                (
                    "from",
                    1,
                    "seat_preview_geometry",
                    (("build_3d_seat_module_geometry", None),),
                ),
                (
                    "from",
                    1,
                    "section_preview_annotations",
                    (
                        ("build_riser_height_preview_labels", None),
                        (
                            "build_section_height_dimension_preview",
                            None,
                        ),
                    ),
                ),
                (
                    "from",
                    1,
                    "stage_preview_geometry",
                    (
                        ("build_proscenium_plan_curves", None),
                        (
                            "build_stage_audience_transition_curves",
                            None,
                        ),
                        ("build_stage_section_2d_curves", None),
                        ("build_stage_space_3d_curves", None),
                    ),
                ),
            ],
            child_imports,
        )

        called_names = {
            node.func.id
            for node in ast.walk(candidate_node)
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
            )
        }
        self.assertTrue(
            {
                "rebase_balcony_last_platform_z",
                "stalls_height_reference_z",
            }.issubset(called_names)
        )

        source = PREVIEW_GEOMETRY_PATH.read_text(
            encoding="utf-8-sig"
        )
        module_symbols = symtable.symtable(
            source,
            str(PREVIEW_GEOMETRY_PATH),
            "exec",
        )
        function_symbols = next(
            child
            for child in module_symbols.get_children()
            if child.get_name() == "build_preview_geometry"
        )
        global_references = {
            symbol.get_name()
            for symbol in function_symbols.get_symbols()
            if symbol.is_global() and symbol.is_referenced()
        }
        builtin_references = {
            "ValueError",
            "enumerate",
            "len",
            "max",
            "range",
        }
        self.assertEqual(
            imported_bindings | builtin_references,
            global_references,
        )

        return_nodes = [
            node
            for node in candidate_node.body
            if isinstance(node, ast.Return)
        ]
        self.assertEqual(1, len(return_nodes))
        self.assertIsInstance(return_nodes[0].value, ast.Dict)
        self.assertEqual(
            [
                "preview_curves",
                "preview_points",
                "preview_meshes",
                "preview_labels",
                "bake_curves",
                "bake_points",
                "bake_breps",
                "bake_instances",
                "seat_source",
                "seat_3d_calculation",
                "seat_3d_calculations",
                "floor_surface_calculation",
                "calculation",
                "balcony_calculation",
                "balcony_calculations",
                "balcony2_dependency_warning",
                "violation_rows",
                "slope_violation_rows",
                "sightline_violation_rows",
                "ceiling_violation_rows",
                "maximum_actual_slope",
                "total_depth",
                "total_rise",
                "direction",
                "stage_section_dimensions",
                "applied_section_rise_overrides",
            ],
            [
                key.value
                for key in return_nodes[0].value.keys
            ],
        )

        package_reexports = set()
        for node in self.auditorium_generator_init_tree.body:
            if isinstance(node, ast.Import):
                package_reexports.update(
                    alias.name
                    for alias in node.names
                    if alias.name.endswith("preview_geometry")
                )
            elif (
                isinstance(node, ast.ImportFrom)
                and node.module
                and node.module.endswith("preview_geometry")
            ):
                package_reexports.update(
                    alias.asname or alias.name
                    for alias in node.names
                )
        self.assertEqual(set(), package_reexports)

    def test_preview_geometry_minimal_and_error_behavior_parity(self):
        def exercise(tree, missing_3d_source=False):
            events = []

            class FakeVector(object):
                def __init__(self, value):
                    self.value = value
                    self.reversed = False
                    events.append(("vector", value))

                def Reverse(self):
                    self.reversed = not self.reversed
                    events.append(("reverse", self.reversed))

                def snapshot(self):
                    return (self.value, self.reversed)

            class FakeRg(object):
                Vector3d = FakeVector

            class FakeDoc(object):
                ModelAbsoluteTolerance = 0.01

            result_template = {
                "x_values": [10.0, 20.0],
                "eye_x_values": [11.0, 21.0],
                "base_z_values": [0.0, 2.0],
                "eye_z_values": [5.0, 7.0],
                "violations": [False, True],
                "slope_values": [0.0, 0.2],
                "aisle_before_values": [False, False],
                "aisle_stair_tread_counts": [0, 0],
                "aisle_stair_riser_heights": [0.0, 0.0],
                "aisle_stair_run_values": [0.0, 0.0],
                "slope_violations": [False, True],
                "sightline_violations": [False, True],
                "rise_interpolation_target": 2.0,
            }

            def fake_unit_scale(doc):
                events.append(("unit-scale", doc.ModelAbsoluteTolerance))
                return 1.0

            def fake_point_at(
                stage_point,
                direction,
                x_mm,
                z_mm,
                mm_scale,
            ):
                marker = (
                    "point",
                    stage_point,
                    direction.snapshot(),
                    x_mm,
                    z_mm,
                    mm_scale,
                )
                events.append(("point-at", x_mm, z_mm))
                return marker

            def fake_line_curve(start, end):
                marker = ("line", start, end)
                events.append(
                    (
                        "line",
                        start[3] if start[0] == "point" else start,
                        end[3] if end[0] == "point" else end,
                    )
                )
                return marker

            def fake_calculate_section(params):
                events.append(("calculate-section", params["row_count"]))
                return copy.deepcopy(result_template)

            def fake_apply_stalls(
                params,
                result,
                target,
                ceiling_z,
            ):
                events.append(
                    ("apply-stalls", target, ceiling_z)
                )
                return result

            def fake_normalized(params, tier_index):
                events.append(("normalize-balcony", tier_index))
                return {
                    "balcony_enabled": False,
                    "balcony_last_platform_z": 100.0,
                }

            def fake_stalls_height_reference(result):
                return result["base_z_values"][-1]

            def fake_rebase_balcony_height(
                stored_absolute_z,
                stalls_reference_z,
                effective_stalls_rear_z,
            ):
                return stored_absolute_z

            def fake_calculate_balcony(
                params,
                previous_result,
                opening_height,
                include_maximum=True,
                tier_index=0,
            ):
                events.append(
                    ("calculate-balcony", tier_index, opening_height)
                )
                return None

            def fake_apply_balcony(
                params,
                result,
                previous_result,
                opening_height,
                target,
            ):
                events.append(("apply-balcony", target))
                return result

            def fake_displayable(result):
                events.append(("displayable", result is not None))
                return False

            def fake_stage_dimensions(params, opening_height):
                events.append(("stage-dimensions", opening_height))
                return {"auditorium_ceiling_z": 30.0}

            def fake_stage_section(*args):
                events.append(("stage-section-2d",))
                return [
                    (
                        ("stage-section",),
                        "stage-color",
                        "Stage2D",
                    )
                ]

            def fake_transition(*args):
                events.append(("stage-transition",))
                return [
                    (
                        ("transition",),
                        "transition-color",
                        "Transition",
                    )
                ]

            def unexpected(name):
                def fail(*args, **kwargs):
                    events.append(("unexpected", name))
                    raise AssertionError(
                        "Unexpected dependency call: {0}".format(name)
                    )

                return fail

            dependencies = {
                "SECTION_RISE_KEYS": (
                    "stalls",
                    "balcony_1",
                    "balcony_2",
                ),
                "PREVIEW_AISLE": "aisle",
                "PREVIEW_AUDITORIUM_CEILING": "ceiling",
                "PREVIEW_BALCONY": "balcony",
                "PREVIEW_BALCONY_RAIL": "balcony-rail",
                "PREVIEW_FLOOR": "floor",
                "PREVIEW_FULL_STAGE_SIGHT": "full-sight",
                "PREVIEW_POINT": "point-color",
                "PREVIEW_REFERENCE": "reference",
                "PREVIEW_SEAT": "seat",
                "PREVIEW_SIGHT": "sight",
                "PREVIEW_WARNING": "warning",
                "append_balcony_tier_geometry": unexpected(
                    "append-balcony"
                ),
                "apply_balcony_rise_interpolation": (
                    fake_apply_balcony
                ),
                "apply_stalls_rise_interpolation": fake_apply_stalls,
                "balcony_result_is_displayable": fake_displayable,
                "build_3d_seat_module_geometry": unexpected(
                    "3d-seat"
                ),
                "build_chair_curves": unexpected("chair"),
                "build_floor_surface_geometry": unexpected(
                    "floor-surface"
                ),
                "build_proscenium_plan_curves": unexpected(
                    "stage-plan"
                ),
                "build_riser_height_preview_labels": unexpected(
                    "riser-labels"
                ),
                "build_section_height_dimension_preview": unexpected(
                    "section-dimension"
                ),
                "build_stage_audience_transition_curves": (
                    fake_transition
                ),
                "build_stage_section_2d_curves": fake_stage_section,
                "build_stage_space_3d_curves": unexpected(
                    "stage-space"
                ),
                "calculate_balcony_section": fake_calculate_balcony,
                "calculate_section": fake_calculate_section,
                "calculate_stage_section_dimensions": (
                    fake_stage_dimensions
                ),
                "line_curve": fake_line_curve,
                "normalized_balcony_tier_params": fake_normalized,
                "point_at": fake_point_at,
                "rebase_balcony_last_platform_z": (
                    fake_rebase_balcony_height
                ),
                "rg": FakeRg,
                "stalls_height_reference_z": (
                    fake_stalls_height_reference
                ),
                "unit_scale_from_mm": fake_unit_scale,
            }
            function = _load_selected_functions(
                tree,
                PREVIEW_GEOMETRY_FUNCTION_NAMES,
                dependencies,
            )["build_preview_geometry"]
            params = {
                "aisle_stair_tread_depth": 1.0,
                "aisle_width": 3.0,
                "flipped": False,
                "floor_type": "stepped",
                "row_count": 2,
                "row_pitch": 10.0,
                "show_3d_seats": missing_3d_source,
                "show_eye_points": False,
                "show_floor_surfaces": False,
                "show_riser_height_labels": False,
                "show_seats": False,
                "show_sightlines": False,
                "stage_preview_mode": "section_2d",
                "stage_sight_point_z": 1.0,
            }
            stage_data = {
                "default_direction": "audience",
                "opening_height": 8.0,
                "opening_width": 20.0,
                "stage_point": "stage-origin",
            }
            try:
                value = function(
                    stage_data,
                    params,
                    FakeDoc(),
                    None,
                    {"stalls": 2.0},
                )
            except Exception as error:
                outcome = (
                    "error",
                    type(error).__name__,
                    error.args,
                )
            else:
                value = dict(value)
                value["direction"] = value["direction"].snapshot()
                outcome = ("return", value)
            return events, outcome

        reference_events, reference_outcome = exercise(
            self.oracle_tree
        )
        candidate_events, candidate_outcome = exercise(
            self.preview_geometry_tree
        )
        self.assertEqual(reference_events, candidate_events)
        self.assert_deep_parity(
            reference_outcome,
            candidate_outcome,
        )
        self.assertEqual("return", candidate_outcome[0])
        returned = candidate_outcome[1]
        self.assertEqual(
            [
                "Stage2D",
                "Transition",
                "AuditoriumCeilingSection",
                "Floor",
                "Floor",
                "Floor",
                "RearCrossAisle",
                "AuditoriumRearWallSection",
            ],
            [item[2] for item in returned["bake_curves"]],
        )
        self.assertEqual(
            ["SightlineReference", "UpperSightlineReference"],
            [item[2] for item in returned["bake_points"]],
        )
        self.assertEqual([2], returned["violation_rows"])
        self.assertEqual(0.2, returned["maximum_actual_slope"])

        reference_events, reference_outcome = exercise(
            self.oracle_tree,
            missing_3d_source=True,
        )
        candidate_events, candidate_outcome = exercise(
            self.preview_geometry_tree,
            missing_3d_source=True,
        )
        self.assertEqual(reference_events, candidate_events)
        self.assertEqual(reference_outcome, candidate_outcome)
        self.assertEqual(
            (
                "error",
                "ValueError",
                (
                    "3D seat modules are enabled, but "
                    "AuditoriumSeat.3dm was not loaded.",
                ),
            ),
            candidate_outcome,
        )

    def test_balcony_height_reference_extraction_boundaries(self):
        candidate_nodes = _function_nodes(
            self.balcony_height_reference_tree
        )
        self.assertTrue(BALCONY_HEIGHT_REFERENCE_PATH.is_file())
        self.assertEqual(
            list(BALCONY_HEIGHT_REFERENCE_FUNCTION_NAMES),
            [
                node.name
                for node in self.balcony_height_reference_tree.body
                if isinstance(node, ast.FunctionDef)
            ],
        )
        self.assertEqual(
            set(BALCONY_HEIGHT_REFERENCE_FUNCTION_NAMES),
            set(candidate_nodes),
        )
        self.assertEqual(
            "(stalls_result)",
            str(
                inspect.signature(
                    balcony_height_reference.stalls_height_reference_z
                )
            ),
        )
        self.assertEqual(
            (
                "(stored_absolute_z, stalls_reference_z, "
                "effective_stalls_rear_z)"
            ),
            str(
                inspect.signature(
                    balcony_height_reference
                    .rebase_balcony_last_platform_z
                )
            ),
        )
        self.assertFalse(
            any(
                isinstance(node, (ast.Import, ast.ImportFrom))
                for node in self.balcony_height_reference_tree.body
            )
        )
        self.assertTrue(
            set(BALCONY_HEIGHT_REFERENCE_FUNCTION_NAMES).isdisjoint(
                _function_nodes(self.auditorium_tree)
            )
        )

        package_exports = {
            alias.name
            for node in self.auditorium_generator_init_tree.body
            if isinstance(node, ast.ImportFrom)
            for alias in node.names
        }
        self.assertTrue(
            set(BALCONY_HEIGHT_REFERENCE_FUNCTION_NAMES).isdisjoint(
                package_exports
            )
        )

    def test_balcony_height_reference_rebases_without_drift(self):
        raw_stalls = {
            "base_z_values": [-1100.0, 1700.0],
        }
        interpolated_stalls = {
            "base_z_values": [-1100.0, 2800.0],
            "rise_interpolation_applied": True,
            "rise_interpolation_original": 2800.0,
        }
        raw_before = copy.deepcopy(raw_stalls)
        interpolated_before = copy.deepcopy(interpolated_stalls)

        raw_reference_z = (
            balcony_height_reference.stalls_height_reference_z(
                raw_stalls
            )
        )
        interpolated_reference_z = (
            balcony_height_reference.stalls_height_reference_z(
                interpolated_stalls
            )
        )
        self.assertEqual(1700.0, raw_reference_z)
        self.assertEqual(1700.0, interpolated_reference_z)

        stored_balcony_z = 6000.0
        effective_rear_z = interpolated_stalls["base_z_values"][-1]
        effective_balcony_z = (
            balcony_height_reference.rebase_balcony_last_platform_z(
                stored_balcony_z,
                interpolated_reference_z,
                effective_rear_z,
            )
        )
        self.assertEqual(7100.0, effective_balcony_z)

        self.assertEqual(
            stored_balcony_z,
            balcony_height_reference.rebase_balcony_last_platform_z(
                stored_balcony_z,
                raw_reference_z,
                raw_stalls["base_z_values"][-1],
            ),
        )
        for unused_iteration in range(3):
            self.assertEqual(
                7100.0,
                balcony_height_reference
                .rebase_balcony_last_platform_z(
                    stored_balcony_z,
                    interpolated_reference_z,
                    effective_rear_z,
                ),
            )
        self.assertEqual(
            6000.0,
            balcony_height_reference.rebase_balcony_last_platform_z(
                stored_balcony_z,
                raw_reference_z,
                raw_stalls["base_z_values"][-1],
            ),
        )
        self.assertEqual(raw_before, raw_stalls)
        self.assertEqual(interpolated_before, interpolated_stalls)

    def test_preview_geometry_rebases_both_balconies_without_drift(self):
        class PipelineCaptured(Exception):
            pass

        class FakeVector(object):
            def __init__(self, value):
                self.value = value

            def Reverse(self):
                self.value = ("reversed", self.value)

        class FakeRg(object):
            Vector3d = FakeVector

        class FakeDoc(object):
            pass

        params = _base_params()
        params["flipped"] = False
        params_before = copy.deepcopy(params)
        stage_data = {
            "stage_point": ("stage-origin",),
            "default_direction": ("audience-direction",),
            "opening_width": 20000.0,
            "opening_height": 8000.0,
        }

        def exercise(stalls_override):
            trace = {
                "raw_stalls_rear_z": None,
                "effective_stalls_rear_z": None,
                "balconies": [],
            }

            def calculate_stalls(calculation_params):
                result = sections.calculate_section(
                    calculation_params
                )
                trace["raw_stalls_rear_z"] = (
                    result["base_z_values"][-1]
                )
                return result

            def apply_stalls(
                calculation_params,
                result,
                target_rise,
                auditorium_ceiling_z,
            ):
                rebuilt = sections.apply_stalls_rise_interpolation(
                    calculation_params,
                    result,
                    target_rise,
                    auditorium_ceiling_z,
                )
                trace["effective_stalls_rear_z"] = (
                    rebuilt["base_z_values"][-1]
                )
                return rebuilt

            def calculate_balcony(
                calculation_params,
                lower_result,
                opening_height_mm,
                include_maximum=True,
                tier_index=0,
            ):
                result = sections.calculate_balcony_section(
                    calculation_params,
                    lower_result,
                    opening_height_mm,
                    include_maximum,
                    tier_index,
                )
                trace["balconies"].append(
                    {
                        "tier_index": tier_index,
                        "parameter_last_z": calculation_params[
                            "balcony_last_platform_z"
                        ],
                        "calculated_last_z": (
                            result["base_z_values"][-1]
                        ),
                    }
                )
                return result

            def apply_balcony(
                calculation_params,
                result,
                lower_result,
                opening_height_mm,
                target_rise,
            ):
                rebuilt = (
                    sections.apply_balcony_rise_interpolation(
                        calculation_params,
                        result,
                        lower_result,
                        opening_height_mm,
                        target_rise,
                    )
                )
                trace["balconies"][-1]["applied_last_z"] = (
                    rebuilt["base_z_values"][-1]
                )
                if len(trace["balconies"]) == 2:
                    raise PipelineCaptured()
                return rebuilt

            dependencies = {
                "SECTION_RISE_KEYS": (
                    "stalls",
                    "balcony_1",
                    "balcony_2",
                ),
                "apply_balcony_rise_interpolation": apply_balcony,
                "apply_stalls_rise_interpolation": apply_stalls,
                "balcony_result_is_displayable": (
                    sections.balcony_result_is_displayable
                ),
                "calculate_balcony_section": calculate_balcony,
                "calculate_section": calculate_stalls,
                "normalized_balcony_tier_params": (
                    sections.normalized_balcony_tier_params
                ),
                "point_at": lambda *args: ("point", args),
                "rebase_balcony_last_platform_z": (
                    balcony_height_reference
                    .rebase_balcony_last_platform_z
                ),
                "rg": FakeRg,
                "stalls_height_reference_z": (
                    balcony_height_reference
                    .stalls_height_reference_z
                ),
                "unit_scale_from_mm": lambda doc: 1.0,
            }
            function = _load_selected_functions(
                self.preview_geometry_tree,
                PREVIEW_GEOMETRY_FUNCTION_NAMES,
                dependencies,
            )["build_preview_geometry"]
            with self.assertRaises(PipelineCaptured):
                function(
                    stage_data,
                    params,
                    FakeDoc(),
                    None,
                    {"stalls": stalls_override},
                )
            return trace

        raised = exercise(3900.0)
        changed = exercise(3000.0)
        reset = exercise(None)
        raised_again = exercise(3900.0)

        self.assertAlmostEqual(
            1693.987022623034,
            raised["raw_stalls_rear_z"],
            places=10,
        )
        self.assertEqual(2800.0, raised["effective_stalls_rear_z"])
        self.assertEqual([0, 1], [
            item["tier_index"] for item in raised["balconies"]
        ])
        for balcony, expected_last_z in zip(
            raised["balconies"],
            (7106.012977376966, 10106.012977376966),
        ):
            self.assertAlmostEqual(
                expected_last_z,
                balcony["parameter_last_z"],
                places=10,
            )
            self.assertEqual(
                balcony["parameter_last_z"],
                balcony["calculated_last_z"],
            )
            self.assertEqual(
                balcony["parameter_last_z"],
                balcony["applied_last_z"],
            )

        self.assertEqual(1900.0, changed["effective_stalls_rear_z"])
        for balcony, expected_last_z in zip(
            changed["balconies"],
            (6206.012977376966, 9206.012977376966),
        ):
            self.assertAlmostEqual(
                expected_last_z,
                balcony["parameter_last_z"],
                places=10,
            )

        self.assertEqual(
            reset["raw_stalls_rear_z"],
            reset["effective_stalls_rear_z"],
        )
        self.assertEqual(
            [6000.0, 9000.0],
            [
                item["parameter_last_z"]
                for item in reset["balconies"]
            ],
        )
        self.assertEqual(raised, raised_again)
        self.assertEqual(params_before, params)

    def test_floor_surface_geometry_extraction_boundaries(self):
        oracle_nodes = _function_nodes(self.oracle_tree)
        candidate_nodes = _function_nodes(
            self.floor_surface_geometry_tree
        )
        main_nodes = _function_nodes(self.auditorium_tree)
        reference_functions = _load_selected_functions(
            self.oracle_tree,
            FLOOR_SURFACE_FUNCTION_NAMES,
            {},
        )
        candidate_functions = _load_selected_functions(
            self.floor_surface_geometry_tree,
            FLOOR_SURFACE_FUNCTION_NAMES,
            {},
        )

        self.assertEqual(
            list(FLOOR_SURFACE_FUNCTION_NAMES),
            [
                node.name
                for node in self.floor_surface_geometry_tree.body
                if isinstance(node, ast.FunctionDef)
            ],
        )
        for name in FLOOR_SURFACE_FUNCTION_NAMES:
            with self.subTest(function=name):
                self.assertIn(name, oracle_nodes)
                self.assertIn(name, candidate_nodes)
                self.assertNotIn(name, main_nodes)
                self.assertEqual(
                    ast.dump(
                        oracle_nodes[name],
                        include_attributes=False,
                    ),
                    ast.dump(
                        candidate_nodes[name],
                        include_attributes=False,
                    ),
                )
                self.assertEqual(
                    ast.dump(
                        oracle_nodes[name].args,
                        include_attributes=False,
                    ),
                    ast.dump(
                        candidate_nodes[name].args,
                        include_attributes=False,
                    ),
                )
                self.assertEqual(
                    str(inspect.signature(reference_functions[name])),
                    str(inspect.signature(candidate_functions[name])),
                )

        direct_imports = [
            node
            for node in self.auditorium_tree.body
            if (
                isinstance(node, ast.ImportFrom)
                and node.module
                == "auditorium_generator.floor_surface_geometry"
            )
        ]
        self.assertEqual(1, len(direct_imports))
        self.assertEqual(
            (
                "append_floor_surface",
                "append_stage_envelope_surfaces",
                "append_understage_envelope_surfaces",
                "build_floor_surface_geometry",
                "create_stage_vertical_face",
                "extrude_section_curve_across_width",
            ),
            tuple(alias.name for alias in direct_imports[0].names),
        )
        self.assertTrue(
            all(alias.asname is None for alias in direct_imports[0].names)
        )

        candidate_imports = set()
        for node in self.floor_surface_geometry_tree.body:
            if isinstance(node, ast.Import):
                candidate_imports.update(
                    (
                        "import",
                        0,
                        alias.name,
                        alias.asname,
                    )
                    for alias in node.names
                )
            elif isinstance(node, ast.ImportFrom):
                candidate_imports.add(
                    (
                        "from",
                        node.level,
                        node.module,
                        tuple(
                            (alias.name, alias.asname)
                            for alias in node.names
                        ),
                    )
                )
        self.assertEqual(
            {
                ("import", 0, "Rhino.Geometry", "rg"),
                (
                    "from",
                    1,
                    "calculations.seating",
                    (("calculate_seat_layout_width", None),),
                ),
                (
                    "from",
                    1,
                    "geometry_metadata",
                    (
                        ("section_floor_surface_name", None),
                        ("stage_edge_adjacencies", None),
                        ("stage_space_envelope_name", None),
                        ("stage_space_top_z", None),
                    ),
                ),
                (
                    "from",
                    1,
                    "preview_mesh_geometry",
                    (("build_seat_source_preview_mesh", None),),
                ),
                (
                    "from",
                    1,
                    "preview_palette",
                    (
                        (
                            "FLOOR_SURFACE_PREVIEW_TRANSPARENCY",
                            None,
                        ),
                        ("PREVIEW_AUDITORIUM_CEILING", None),
                        ("PREVIEW_STAGE_SECTION", None),
                        ("PREVIEW_UNDERSTAGE", None),
                    ),
                ),
                (
                    "from",
                    1,
                    "rhino_primitives",
                    (
                        ("build_plan_rectangle", None),
                        ("get_stage_directions", None),
                        ("point_at", None),
                        ("stage_space_point", None),
                    ),
                ),
                (
                    "from",
                    1,
                    "seat_preview_geometry",
                    (("SEAT_SOURCE_ARMREST_WIDTH", None),),
                ),
                (
                    "from",
                    1,
                    "stage_preview_geometry",
                    (("calculate_proscenium_space_layout", None),),
                ),
            },
            candidate_imports,
        )

        package_reexports = set()
        for node in self.auditorium_generator_init_tree.body:
            if isinstance(node, ast.Import):
                package_reexports.update(
                    alias.name
                    for alias in node.names
                    if alias.name.endswith("floor_surface_geometry")
                )
            elif (
                isinstance(node, ast.ImportFrom)
                and node.module
                and node.module.endswith("floor_surface_geometry")
            ):
                package_reexports.update(
                    alias.asname or alias.name
                    for alias in node.names
                )
        self.assertEqual(set(), package_reexports)

    def test_floor_surface_helper_fake_behavior_parity(self):
        helper_names = (
            "extrude_section_curve_across_width",
            "append_floor_surface",
        )

        def exercise(tree):
            events = []

            class FakeVector(object):
                def __init__(self, name):
                    self.name = name

                def __mul__(self, scalar):
                    value = ("scaled-vector", self.name, scalar)
                    events.append(("vector-multiply", self.name, scalar))
                    return value

            class FakeCurve(object):
                def __init__(self, name):
                    self.name = name
                    self.transforms = []

                def DuplicateCurve(self):
                    events.append(("duplicate", self.name))
                    return FakeCurve(self.name + ":copy")

                def Transform(self, transform):
                    self.transforms.append(transform)
                    events.append(
                        ("curve-transform", self.name, transform)
                    )

            class FakeSurfaceResult(object):
                def __init__(self, marker):
                    self.marker = marker

                def ToBrep(self):
                    events.append(("to-brep", self.marker))
                    return ("brep", self.marker)

            class FakeSurfaceApi(object):
                @staticmethod
                def CreateExtrusion(curve, vector):
                    marker = (
                        curve.name,
                        tuple(curve.transforms),
                        vector,
                    )
                    events.append(("create-extrusion", marker))
                    if curve.name.startswith("no-surface"):
                        return None
                    return FakeSurfaceResult(marker)

            class FakeTransformApi(object):
                @staticmethod
                def Translation(vector):
                    events.append(("translation", vector))
                    return ("translation", vector)

            class FakeRg(object):
                Surface = FakeSurfaceApi
                Transform = FakeTransformApi

            def fake_build_preview_mesh(breps):
                events.append(("preview-mesh", tuple(breps)))
                if breps == ["brep-no-mesh"]:
                    return None
                return ("mesh", tuple(breps))

            loaded = _load_selected_functions(
                tree,
                helper_names,
                {
                    "FLOOR_SURFACE_PREVIEW_TRANSPARENCY": 67,
                    "build_seat_source_preview_mesh": (
                        fake_build_preview_mesh
                    ),
                    "rg": FakeRg,
                },
            )
            extrude = loaded[
                "extrude_section_curve_across_width"
            ]
            append = loaded["append_floor_surface"]
            direction = FakeVector("stage-right")

            no_curve_result = extrude(None, direction, 200.0, 0.5)
            zero_width_curve = FakeCurve("zero-width")
            zero_width_result = extrude(
                zero_width_curve,
                direction,
                0.0,
                0.5,
            )
            normal_curve = FakeCurve("normal")
            normal_result = extrude(
                normal_curve,
                direction,
                200.0,
                0.5,
            )
            no_surface_curve = FakeCurve("no-surface")
            no_surface_result = extrude(
                no_surface_curve,
                direction,
                200.0,
                0.5,
            )

            preview_meshes = [("sentinel", "preview")]
            bake_breps = [("sentinel", "bake")]
            append(
                None,
                "none-color",
                "NoneSurface",
                preview_meshes,
                bake_breps,
            )
            append(
                "brep-normal",
                "normal-color",
                "NormalSurface",
                preview_meshes,
                bake_breps,
            )
            append(
                "brep-no-mesh",
                "fallback-color",
                "FallbackSurface",
                preview_meshes,
                bake_breps,
            )
            return {
                "events": tuple(events),
                "extrusions": (
                    no_curve_result,
                    zero_width_result,
                    normal_result,
                    no_surface_result,
                ),
                "original_curve_transforms": (
                    tuple(zero_width_curve.transforms),
                    tuple(normal_curve.transforms),
                    tuple(no_surface_curve.transforms),
                ),
                "preview_meshes": tuple(preview_meshes),
                "bake_breps": tuple(bake_breps),
            }

        reference = exercise(self.oracle_tree)
        candidate = exercise(self.floor_surface_geometry_tree)
        self.assertEqual(reference, candidate)
        self.assertEqual(
            (None, None),
            candidate["extrusions"][:2],
        )
        self.assertIsNotNone(candidate["extrusions"][2])
        self.assertIsNone(candidate["extrusions"][3])
        self.assertEqual(
            ((), (), ()),
            candidate["original_curve_transforms"],
        )
        self.assertEqual(
            (
                ("sentinel", "preview"),
                (
                    ("mesh", ("brep-normal",)),
                    "normal-color",
                    67,
                ),
            ),
            candidate["preview_meshes"],
        )
        self.assertEqual(
            (
                ("sentinel", "bake"),
                (
                    "brep-normal",
                    "normal-color",
                    "NormalSurface",
                ),
                (
                    "brep-no-mesh",
                    "fallback-color",
                    "FallbackSurface",
                ),
            ),
            candidate["bake_breps"],
        )

    def test_floor_surface_full_output_order_fake_parity(self):
        def exercise(tree):
            events = []

            class FakeVector(object):
                def __init__(self, name):
                    self.name = name

                def __mul__(self, scalar):
                    value = ("scaled-vector", self.name, scalar)
                    events.append(("vector-multiply", self.name, scalar))
                    return value

            class FakePoint(object):
                def __init__(self, marker):
                    self.marker = marker

                def __add__(self, offset):
                    value = ("offset-point", self.marker, offset)
                    events.append(("point-add", self.marker, offset))
                    return value

            class FakeBrepApi(object):
                @staticmethod
                def CreatePlanarBreps(outline, tolerance):
                    events.append(
                        ("planar-breps", outline, tolerance)
                    )
                    return [("planar-brep", outline)]

                @staticmethod
                def CreateFromCornerPoints(
                    first,
                    second,
                    third,
                    fourth,
                    tolerance,
                ):
                    corners = (first, second, third, fourth)
                    events.append(
                        ("corner-brep", corners, tolerance)
                    )
                    return ("corner-brep", corners, tolerance)

            class FakeRg(object):
                Brep = FakeBrepApi

            spaces = (
                {
                    "name": "MainStage",
                    "plan_color": "main-color",
                    "min_x": -100.0,
                    "max_x": 100.0,
                    "min_y": 0.0,
                    "max_y": 200.0,
                },
                {
                    "name": "SideStage",
                    "plan_color": "side-color",
                    "min_x": 100.0,
                    "max_x": 180.0,
                    "min_y": 0.0,
                    "max_y": 150.0,
                },
            )

            def fake_get_stage_directions(audience_direction):
                events.append(
                    ("directions", audience_direction)
                )
                return FakeVector("stage-right"), "stage-back"

            def fake_stage_layout(params):
                events.append(
                    ("stage-layout", params["understage_enabled"])
                )
                return [dict(space) for space in spaces]

            def fake_plan_rectangle(
                stage_point,
                stage_right_direction,
                stage_back_direction,
                min_x,
                max_x,
                min_y,
                max_y,
                mm_scale,
                z_value=0.0,
            ):
                outline = (
                    "outline",
                    stage_point,
                    stage_right_direction.name,
                    stage_back_direction,
                    min_x,
                    max_x,
                    min_y,
                    max_y,
                    mm_scale,
                    z_value,
                )
                events.append(("plan-rectangle", outline))
                return outline

            def fake_append_surface(
                brep,
                color,
                name,
                preview_meshes,
                bake_breps,
            ):
                events.append(("append", name, color, brep))
                if brep is None:
                    return
                preview_meshes.append(("preview", name))
                bake_breps.append((brep, color, name))

            def fake_stage_envelope(
                stage_point,
                audience_direction,
                params,
                section_dimensions,
                opening_width_mm,
                opening_height_mm,
                mm_scale,
                absolute_tolerance,
                preview_meshes,
                bake_breps,
            ):
                events.append(("stage-envelope-helper",))
                fake_append_surface(
                    "stage-envelope-brep",
                    "stage-envelope-color",
                    "StageEnvelopeSentinel",
                    preview_meshes,
                    bake_breps,
                )

            def fake_understage_envelope(
                stage_point,
                audience_direction,
                params,
                section_dimensions,
                mm_scale,
                absolute_tolerance,
                preview_meshes,
                bake_breps,
            ):
                events.append(("understage-helper",))
                fake_append_surface(
                    "understage-brep",
                    "understage-color",
                    "UnderstageSentinel",
                    preview_meshes,
                    bake_breps,
                )

            floor_surface_names = {
                "StallsFloor": "StallsFloorSurface",
                "Balcony01Floor": "Balcony01FloorSurface",
            }

            def fake_floor_surface_name(curve_name):
                value = floor_surface_names.get(curve_name)
                events.append(
                    ("floor-surface-name", curve_name, value)
                )
                return value

            def fake_extrude(
                curve,
                stage_right_direction,
                width_mm,
                mm_scale,
            ):
                result = (
                    "extruded",
                    curve,
                    stage_right_direction.name,
                    width_mm,
                    mm_scale,
                )
                events.append(("extrude", curve, width_mm, mm_scale))
                return result

            def fake_point_at(
                stage_point,
                audience_direction,
                longitudinal_x,
                z_value,
                mm_scale,
            ):
                marker = (
                    stage_point,
                    audience_direction,
                    longitudinal_x,
                    z_value,
                    mm_scale,
                )
                events.append(("point-at", marker))
                return FakePoint(marker)

            loaded = _load_selected_functions(
                tree,
                ("build_floor_surface_geometry",),
                {
                    "PREVIEW_AUDITORIUM_CEILING": (
                        "auditorium-envelope-color"
                    ),
                    "SEAT_SOURCE_ARMREST_WIDTH": 50.0,
                    "append_floor_surface": fake_append_surface,
                    "append_stage_envelope_surfaces": (
                        fake_stage_envelope
                    ),
                    "append_understage_envelope_surfaces": (
                        fake_understage_envelope
                    ),
                    "build_plan_rectangle": fake_plan_rectangle,
                    "calculate_proscenium_space_layout": (
                        fake_stage_layout
                    ),
                    "calculate_seat_layout_width": (
                        lambda params: 3000.0
                    ),
                    "extrude_section_curve_across_width": (
                        fake_extrude
                    ),
                    "get_stage_directions": fake_get_stage_directions,
                    "point_at": fake_point_at,
                    "rg": FakeRg,
                    "section_floor_surface_name": (
                        fake_floor_surface_name
                    ),
                },
            )

            params = {
                "side_floor_margin": 100.0,
                "understage_enabled": True,
            }
            section_dimensions = {
                "auditorium_ceiling_z": 9000.0,
            }
            section_bake_curves = [
                (
                    "curve-transition-floor",
                    "transition-floor-color",
                    "StageAudienceFloorSection",
                ),
                (
                    "curve-railing-2",
                    "railing-2-color",
                    "Balcony02RailingTop",
                ),
                (
                    "curve-stalls",
                    "stalls-color",
                    "StallsFloor",
                ),
                (
                    "curve-pit-bottom",
                    "pit-color",
                    "OrchestraPitBottom",
                ),
                (
                    "curve-railing-1",
                    "railing-1-color",
                    "Balcony01RailingFront",
                ),
                (
                    "curve-balcony",
                    "balcony-color",
                    "Balcony01Floor",
                ),
                (
                    "curve-ignored",
                    "ignored-color",
                    "IgnoredSection",
                ),
            ]
            inputs_before = copy.deepcopy(
                (params, section_dimensions, section_bake_curves)
            )
            result = loaded["build_floor_surface_geometry"](
                "stage-point",
                "audience-direction",
                params,
                section_dimensions,
                12000.0,
                8000.0,
                25000.0,
                1200.0,
                0.01,
                0.1,
                section_bake_curves,
            )
            return {
                "events": tuple(events),
                "result": result,
                "inputs_after": (
                    params,
                    section_dimensions,
                    section_bake_curves,
                ),
                "inputs_before": inputs_before,
            }

        reference = exercise(self.oracle_tree)
        candidate = exercise(self.floor_surface_geometry_tree)
        self.assertEqual(reference, candidate)
        self.assertEqual(
            candidate["inputs_before"],
            candidate["inputs_after"],
        )
        self.assertEqual(
            3250.0,
            candidate["result"]["auditorium_floor_width"],
        )
        self.assertEqual(
            (
                "MainStageFloorSurface",
                "SideStageFloorSurface",
                "StageEnvelopeSentinel",
                "UnderstageSentinel",
                "StallsFloorSurface",
                "Balcony01FloorSurface",
                "Balcony02RailingTopSurface",
                "Balcony01RailingFrontSurface",
                "StageAudienceTransitionFloorSurface",
                "OrchestraPitBottomSurface",
                "AuditoriumCeilingSurface",
                "AuditoriumRearWallSurface",
            ),
            tuple(
                brep_entry[2]
                for brep_entry in candidate["result"]["bake_breps"]
            ),
        )
        self.assertEqual(
            (
                ("curve-stalls", 3250.0),
                ("curve-balcony", 3250.0),
                ("curve-railing-2", 3250.0),
                ("curve-railing-1", 3250.0),
                ("curve-transition-floor", 12000.0),
                ("curve-pit-bottom", 12000.0),
            ),
            tuple(
                (event[1], event[2])
                for event in candidate["events"]
                if event[0] == "extrude"
            ),
        )

    def test_document_baking_extraction_boundaries(self):
        oracle_nodes = _function_nodes(self.oracle_tree)
        candidate_nodes = _function_nodes(self.document_baking_tree)
        main_nodes = _function_nodes(self.auditorium_tree)
        reference_functions = _load_selected_functions(
            self.oracle_tree,
            DOCUMENT_BAKING_FUNCTION_NAMES,
            {},
        )
        candidate_functions = _load_selected_functions(
            self.document_baking_tree,
            DOCUMENT_BAKING_FUNCTION_NAMES,
            {},
        )

        self.assertEqual(
            list(DOCUMENT_BAKING_FUNCTION_NAMES),
            [
                node.name
                for node in self.document_baking_tree.body
                if isinstance(node, ast.FunctionDef)
            ],
        )
        for name in DOCUMENT_BAKING_FUNCTION_NAMES:
            with self.subTest(function=name):
                self.assertIn(name, oracle_nodes)
                self.assertIn(name, candidate_nodes)
                self.assertNotIn(name, main_nodes)
                self.assertEqual(
                    ast.dump(
                        oracle_nodes[name],
                        include_attributes=False,
                    ),
                    ast.dump(
                        candidate_nodes[name],
                        include_attributes=False,
                    ),
                )
                self.assertEqual(
                    ast.dump(
                        oracle_nodes[name].args,
                        include_attributes=False,
                    ),
                    ast.dump(
                        candidate_nodes[name].args,
                        include_attributes=False,
                    ),
                )
                self.assertEqual(
                    str(inspect.signature(reference_functions[name])),
                    str(inspect.signature(candidate_functions[name])),
                )

        direct_imports = [
            node
            for node in self.auditorium_tree.body
            if (
                isinstance(node, ast.ImportFrom)
                and node.module
                == "auditorium_generator.document_baking"
            )
        ]
        self.assertEqual(1, len(direct_imports))
        self.assertEqual(
            (
                "bake_preview",
                "create_attributes",
                "ensure_seat_instance_definition",
            ),
            tuple(alias.name for alias in direct_imports[0].names),
        )
        self.assertTrue(
            all(alias.asname is None for alias in direct_imports[0].names)
        )

        candidate_imports = set()
        for node in self.document_baking_tree.body:
            if isinstance(node, ast.Import):
                candidate_imports.update(
                    (
                        "import",
                        0,
                        alias.name,
                        alias.asname,
                    )
                    for alias in node.names
                )
            elif isinstance(node, ast.ImportFrom):
                candidate_imports.add(
                    (
                        "from",
                        node.level,
                        node.module,
                        tuple(
                            (alias.name, alias.asname)
                            for alias in node.names
                        ),
                    )
                )
        self.assertEqual(
            {
                ("import", 0, "Rhino.DocObjects", "rd"),
                ("import", 0, "Rhino.Geometry", "rg"),
                (
                    "from",
                    1,
                    "preview_palette",
                    (
                        ("PREVIEW_3D_ARMREST", None),
                        ("PREVIEW_3D_CHAIR", None),
                    ),
                ),
            },
            candidate_imports,
        )

        package_reexports = set()
        for node in self.auditorium_generator_init_tree.body:
            if isinstance(node, ast.Import):
                package_reexports.update(
                    alias.name
                    for alias in node.names
                    if alias.name.endswith("document_baking")
                )
            elif (
                isinstance(node, ast.ImportFrom)
                and node.module
                and node.module.endswith("document_baking")
            ):
                package_reexports.update(
                    alias.asname or alias.name
                    for alias in node.names
                )
        self.assertEqual(set(), package_reexports)

    def test_document_baking_fake_rhino_document_parity(self):
        def exercise(tree, scenario):
            events = []

            class FakeObjectAttributes(object):
                def __init__(self):
                    self.LayerIndex = None
                    self.ColorSource = None
                    self.ObjectColor = None
                    self.Name = None

            class FakeObjectColorSource(object):
                ColorFromObject = "color-from-object"

            class FakeRd(object):
                ObjectAttributes = FakeObjectAttributes
                ObjectColorSource = FakeObjectColorSource

            class FakePoint3d(object):
                Origin = "world-origin"

            class FakeRg(object):
                Point3d = FakePoint3d

            def attributes_snapshot(attributes):
                return (
                    attributes.LayerIndex,
                    attributes.ColorSource,
                    attributes.ObjectColor,
                    attributes.Name,
                )

            class FakeSourceGeometry(object):
                def __init__(self, name, returns_none=False):
                    self.name = name
                    self.returns_none = returns_none

                def Duplicate(self):
                    events.append(("duplicate", self.name))
                    if self.returns_none:
                        return None
                    return FakeDuplicateGeometry(self.name + ":copy")

            class FakeDuplicateGeometry(object):
                def __init__(self, name):
                    self.name = name

            class FakeDefinition(object):
                def __init__(self, index):
                    self.Index = index

            if scenario == "full":
                signature = "full-signature"
                curve_ids = ["curve-id"]
                brep_ids = ["brep-id"]
                point_ids = ["point-id"]
                instance_ids = [
                    "chair-instance-id",
                    "armrest-instance-id",
                ]
                definition_ids = [31, 32]
                existing_definitions = {}
                group_raises = False
                include_source = True
                bake_instances = [
                    (
                        "chair",
                        "chair-transform",
                        "chair-instance-color",
                        "ChairInstance",
                    ),
                    (
                        "armrest",
                        "armrest-transform",
                        "armrest-instance-color",
                        "ArmrestInstance",
                    ),
                ]
                bake_curves = [
                    (None, "skip-color", "SkippedCurve"),
                    ("curve", "curve-color", "Curve"),
                ]
                bake_breps = [
                    (None, "skip-color", "SkippedBrep"),
                    ("brep", "brep-color", "Brep"),
                ]
                bake_points = [
                    ("point", "point-color", "Point"),
                ]
            elif scenario == "reuse":
                signature = "existing-signature"
                curve_ids = []
                brep_ids = []
                point_ids = []
                instance_ids = [
                    "existing-chair-instance",
                    "existing-armrest-instance",
                ]
                definition_ids = []
                existing_definitions = {
                    (
                        "Elephant_AuditoriumSeat_ChairBody_"
                        "existing-signature"
                    ): 71,
                    (
                        "Elephant_AuditoriumSeat_Armrest_"
                        "existing-signature"
                    ): 72,
                }
                group_raises = False
                include_source = True
                bake_instances = [
                    (
                        "chair",
                        "chair-transform",
                        "chair-color",
                        "ExistingChair",
                    ),
                    (
                        "armrest",
                        "armrest-transform",
                        "armrest-color",
                        "ExistingArmrest",
                    ),
                ]
                bake_curves = []
                bake_breps = []
                bake_points = []
            elif scenario == "group-error":
                signature = "unused"
                curve_ids = ["curve-before-group-error"]
                brep_ids = []
                point_ids = []
                instance_ids = []
                definition_ids = []
                existing_definitions = {}
                group_raises = True
                include_source = False
                bake_instances = []
                bake_curves = [
                    ("curve", "curve-color", "Curve"),
                ]
                bake_breps = []
                bake_points = []
            elif scenario == "falsy-ids":
                signature = "unused"
                curve_ids = ["curve-ok", None]
                brep_ids = [False]
                point_ids = [0]
                instance_ids = []
                definition_ids = []
                existing_definitions = {}
                group_raises = False
                include_source = False
                bake_instances = []
                bake_curves = [
                    ("curve-ok", "curve-color", "CurveOk"),
                    ("curve-false", "curve-color", "CurveFalse"),
                ]
                bake_breps = [
                    ("brep-false", "brep-color", "BrepFalse"),
                ]
                bake_points = [
                    ("point-false", "point-color", "PointFalse"),
                ]
            elif scenario == "partial-missing-source":
                signature = "unused"
                curve_ids = ["curve-created-before-error"]
                brep_ids = []
                point_ids = []
                instance_ids = []
                definition_ids = []
                existing_definitions = {}
                group_raises = False
                include_source = False
                bake_instances = [
                    (
                        "chair",
                        "transform",
                        "instance-color",
                        "MissingSourceChair",
                    ),
                ]
                bake_curves = [
                    ("curve", "curve-color", "Curve"),
                ]
                bake_breps = []
                bake_points = []
            else:
                raise AssertionError(
                    "Unknown scenario: {0}".format(scenario)
                )

            class FakeLayers(object):
                CurrentLayerIndex = 19

            class FakeInstanceDefinitions(object):
                def Find(self, name, ignore_deleted):
                    events.append(
                        (
                            "definition-find",
                            name,
                            ignore_deleted,
                        )
                    )
                    index = existing_definitions.get(name)
                    if index is None:
                        return None
                    return FakeDefinition(index)

                def Add(
                    self,
                    name,
                    description,
                    origin,
                    geometries,
                    attributes,
                ):
                    index = definition_ids.pop(0)
                    events.append(
                        (
                            "definition-add",
                            name,
                            description,
                            origin,
                            tuple(
                                geometry.name
                                for geometry in geometries
                            ),
                            tuple(
                                attributes_snapshot(item)
                                for item in attributes
                            ),
                            index,
                        )
                    )
                    return index

            class FakeObjects(object):
                def AddCurve(self, curve, attributes):
                    object_id = curve_ids.pop(0)
                    events.append(
                        (
                            "add-curve",
                            curve,
                            attributes_snapshot(attributes),
                            object_id,
                        )
                    )
                    return object_id

                def AddBrep(self, brep, attributes):
                    object_id = brep_ids.pop(0)
                    events.append(
                        (
                            "add-brep",
                            brep,
                            attributes_snapshot(attributes),
                            object_id,
                        )
                    )
                    return object_id

                def AddPoint(self, point, attributes):
                    object_id = point_ids.pop(0)
                    events.append(
                        (
                            "add-point",
                            point,
                            attributes_snapshot(attributes),
                            object_id,
                        )
                    )
                    return object_id

                def AddInstanceObject(
                    self,
                    definition_index,
                    transform,
                    attributes,
                ):
                    object_id = instance_ids.pop(0)
                    events.append(
                        (
                            "add-instance",
                            definition_index,
                            transform,
                            attributes_snapshot(attributes),
                            object_id,
                        )
                    )
                    return object_id

            class FakeGroups(object):
                def Add(self, object_ids):
                    events.append(
                        ("group-add", tuple(object_ids))
                    )
                    if group_raises:
                        raise RuntimeError("group failure")
                    return 5

            class FakeViews(object):
                def Redraw(self):
                    events.append(("redraw",))

            class FakeDocument(object):
                def __init__(self):
                    self.Layers = FakeLayers()
                    self.InstanceDefinitions = (
                        FakeInstanceDefinitions()
                    )
                    self.Objects = FakeObjects()
                    self.Groups = FakeGroups()
                    self.Views = FakeViews()

            loaded = _load_selected_functions(
                tree,
                DOCUMENT_BAKING_FUNCTION_NAMES,
                {
                    "PREVIEW_3D_ARMREST": "armrest-preview-color",
                    "PREVIEW_3D_CHAIR": "chair-preview-color",
                    "rd": FakeRd,
                    "rg": FakeRg,
                },
            )
            preview_data = {
                "bake_curves": bake_curves,
                "bake_breps": bake_breps,
                "bake_points": bake_points,
                "bake_instances": bake_instances,
            }
            if include_source:
                preview_data["seat_source"] = {
                    "signature": signature,
                    "path": "C:/seat-source.3dm",
                    "chair": {
                        "geometries": [
                            FakeSourceGeometry("chair-geometry"),
                            FakeSourceGeometry(
                                "chair-skipped",
                                returns_none=True,
                            ),
                        ],
                    },
                    "armrest": {
                        "geometries": [
                            FakeSourceGeometry("armrest-geometry"),
                        ],
                    },
                }

            try:
                result = loaded["bake_preview"](
                    preview_data,
                    FakeDocument(),
                )
            except Exception as error:
                outcome = (
                    "error",
                    type(error).__name__,
                    error.args,
                )
            else:
                outcome = ("return", tuple(result))

            return {
                "events": tuple(events),
                "outcome": outcome,
            }

        results = {}
        for scenario in (
            "full",
            "reuse",
            "group-error",
            "falsy-ids",
            "partial-missing-source",
        ):
            with self.subTest(scenario=scenario):
                reference = exercise(self.oracle_tree, scenario)
                candidate = exercise(
                    self.document_baking_tree,
                    scenario,
                )
                self.assertEqual(reference, candidate)
                results[scenario] = candidate

        full = results["full"]
        self.assertEqual(
            (
                "add-curve",
                "add-brep",
                "add-point",
                "definition-find",
                "duplicate",
                "duplicate",
                "definition-add",
                "definition-find",
                "duplicate",
                "definition-add",
                "add-instance",
                "add-instance",
                "group-add",
                "redraw",
            ),
            tuple(event[0] for event in full["events"]),
        )
        self.assertEqual(
            (
                "return",
                (
                    "curve-id",
                    "brep-id",
                    "point-id",
                    "chair-instance-id",
                    "armrest-instance-id",
                ),
            ),
            full["outcome"],
        )
        self.assertEqual(
            (
                19,
                "color-from-object",
                "curve-color",
                "Curve",
            ),
            full["events"][0][2],
        )

        reuse = results["reuse"]
        self.assertEqual(
            (
                "definition-find",
                "definition-find",
                "add-instance",
                "add-instance",
                "group-add",
                "redraw",
            ),
            tuple(event[0] for event in reuse["events"]),
        )
        self.assertFalse(
            any(
                event[0] in ("duplicate", "definition-add")
                for event in reuse["events"]
            )
        )
        self.assertEqual(71, reuse["events"][2][1])
        self.assertEqual(72, reuse["events"][3][1])

        group_error = results["group-error"]
        self.assertEqual(
            ("group-add", "redraw"),
            tuple(
                event[0]
                for event in group_error["events"][-2:]
            ),
        )
        self.assertEqual(
            (
                "return",
                ("curve-before-group-error",),
            ),
            group_error["outcome"],
        )

        falsy_ids = results["falsy-ids"]
        self.assertEqual(
            ("return", ("curve-ok", 0)),
            falsy_ids["outcome"],
        )
        self.assertEqual(
            ("group-add", ("curve-ok",)),
            falsy_ids["events"][-2],
        )

        partial = results["partial-missing-source"]
        self.assertEqual(
            (
                "error",
                "ValueError",
                ("3D seat source data is missing during Bake.",),
            ),
            partial["outcome"],
        )
        self.assertEqual(
            ("add-curve",),
            tuple(event[0] for event in partial["events"]),
        )

    def test_section_result_dialog_extraction_boundaries(self):
        oracle_classes = _class_nodes(self.oracle_tree)
        candidate_classes = _class_nodes(
            self.section_result_dialogs_tree
        )
        main_classes = _class_nodes(self.auditorium_tree)

        for class_name in SECTION_RESULT_DIALOG_CLASS_NAMES:
            with self.subTest(class_name=class_name):
                self.assertIn(class_name, oracle_classes)
                self.assertIn(class_name, candidate_classes)
                self.assertNotIn(class_name, main_classes)
                self.assertEqual(
                    ast.dump(
                        oracle_classes[class_name],
                        include_attributes=False,
                    ),
                    ast.dump(
                        candidate_classes[class_name],
                        include_attributes=False,
                    ),
                )

                oracle_methods = {
                    node.name: node
                    for node in oracle_classes[class_name].body
                    if isinstance(node, ast.FunctionDef)
                }
                candidate_methods = {
                    node.name: node
                    for node in candidate_classes[class_name].body
                    if isinstance(node, ast.FunctionDef)
                }
                self.assertEqual(
                    set(oracle_methods),
                    set(candidate_methods),
                )
                for method_name in oracle_methods:
                    self.assertEqual(
                        ast.dump(
                            oracle_methods[method_name].args,
                            include_attributes=False,
                        ),
                        ast.dump(
                            candidate_methods[method_name].args,
                            include_attributes=False,
                        ),
                        "{0}.{1} signature changed".format(
                            class_name,
                            method_name,
                        ),
                    )

        direct_dialog_imports = [
            node
            for node in self.auditorium_tree.body
            if (
                isinstance(node, ast.ImportFrom)
                and node.level == 0
                and node.module
                == "auditorium_generator.section_result_dialogs"
            )
        ]
        self.assertEqual(1, len(direct_dialog_imports))
        self.assertEqual(
            set(SECTION_RESULT_DIALOG_CLASS_NAMES),
            {
                alias.name
                for alias in direct_dialog_imports[0].names
            },
        )

        oracle_assignments = _assignment_nodes(self.oracle_tree)
        constants_assignments = _assignment_nodes(
            self.section_interpolation_constants_tree
        )
        main_assignments = _assignment_nodes(self.auditorium_tree)
        dialog_assignments = _assignment_nodes(
            self.section_result_dialogs_tree
        )
        for constant_name in SECTION_RESULT_DIALOG_CONSTANT_NAMES:
            with self.subTest(constant_name=constant_name):
                self.assertEqual(
                    ast.dump(
                        oracle_assignments[constant_name],
                        include_attributes=False,
                    ),
                    ast.dump(
                        constants_assignments[constant_name],
                        include_attributes=False,
                    ),
                )
                self.assertNotIn(constant_name, main_assignments)
                self.assertNotIn(
                    constant_name,
                    dialog_assignments,
                )

        main_constant_imports = [
            node
            for node in self.auditorium_tree.body
            if (
                isinstance(node, ast.ImportFrom)
                and node.level == 0
                and node.module
                == "auditorium_generator.section_interpolation_constants"
            )
        ]
        self.assertEqual(1, len(main_constant_imports))
        self.assertTrue(
            set(SECTION_RESULT_DIALOG_CONSTANT_NAMES).issubset(
                {
                    alias.name
                    for alias in main_constant_imports[0].names
                }
            )
        )

        dialog_constant_imports = [
            node
            for node in self.section_result_dialogs_tree.body
            if (
                isinstance(node, ast.ImportFrom)
                and node.level == 1
                and node.module == "section_interpolation_constants"
            )
        ]
        self.assertEqual(1, len(dialog_constant_imports))
        self.assertEqual(
            set(SECTION_RESULT_DIALOG_CONSTANT_NAMES),
            {
                alias.name
                for alias in dialog_constant_imports[0].names
            },
        )

        package_exports = {
            alias.name
            for node in self.auditorium_generator_init_tree.body
            if isinstance(node, ast.ImportFrom)
            for alias in node.names
        }
        self.assertTrue(
            set(SECTION_RESULT_DIALOG_CLASS_NAMES).isdisjoint(
                package_exports
            )
        )
        self.assertTrue(
            set(SECTION_RESULT_DIALOG_CONSTANT_NAMES).isdisjoint(
                package_exports
            )
        )

    def test_section_result_dialog_selected_method_behavior_parity(self):
        def exercise(tree):
            events = []

            class FakeDialog(object):
                @classmethod
                def __class_getitem__(cls, item):
                    return cls

            class FakeForms(object):
                Dialog = FakeDialog

            class FakeBox(object):
                def __init__(self, text):
                    self.Text = text

            def fake_validate(z_values, target, label):
                events.append(
                    (
                        "validate",
                        tuple(z_values),
                        target,
                        label,
                    )
                )

            namespace = {
                "forms": FakeForms,
                "math": math,
                "SECTION_RISE_KEYS": (
                    "stalls",
                    "balcony_1",
                    "balcony_2",
                ),
                "SECTION_INTERPOLATION_WARNING_RATIO": 0.20,
                "validate_section_rise_target": fake_validate,
                "format_section_height_dimension": (
                    lambda value: "height:{0}".format(value)
                ),
            }
            interpolation_class = _load_selected_class(
                tree,
                "SectionDimensionInterpolationDialog",
                namespace,
            )
            calculated_class = _load_selected_class(
                tree,
                "CalculatedResultDialog",
                namespace,
            )

            formatting_dialog = object.__new__(
                interpolation_class
            )
            formatted_values = tuple(
                formatting_dialog.format_value(value)
                for value in (
                    170.0,
                    170.1254,
                    170.9999,
                    -0.0,
                )
            )

            sections = [
                {
                    "key": "stalls",
                    "label": "Stalls",
                    "current_rise": 176.25,
                    "editable": True,
                },
                {
                    "key": "balcony_1",
                    "label": "Balcony 1",
                    "current_rise": 183.75,
                    "editable": True,
                },
                {
                    "key": "balcony_2",
                    "label": "Balcony 2",
                    "current_rise": 191.0,
                    "editable": False,
                },
            ]
            rounding_dialog = object.__new__(
                interpolation_class
            )
            rounding_dialog.sections = sections
            rounding_dialog.target_boxes = {
                "stalls": FakeBox("unchanged"),
                "balcony_1": FakeBox("unchanged"),
                "balcony_2": FakeBox("locked"),
            }
            rounded_values = []
            for callback_name in (
                "on_round_down",
                "on_round_nearest",
                "on_round_up",
            ):
                rounding_dialog.target_boxes[
                    "stalls"
                ].Text = "unchanged"
                rounding_dialog.target_boxes[
                    "balcony_1"
                ].Text = "unchanged"
                rounding_dialog.target_boxes[
                    "balcony_2"
                ].Text = "locked"
                getattr(rounding_dialog, callback_name)(None, None)
                rounded_values.append(
                    (
                        callback_name,
                        tuple(
                            rounding_dialog.target_boxes[key].Text
                            for key in (
                                "stalls",
                                "balcony_1",
                                "balcony_2",
                            )
                        ),
                    )
                )

            reader = object.__new__(interpolation_class)
            reader.sections = [
                {
                    "key": "stalls",
                    "label": "Stalls",
                    "current_rise": 176.25,
                    "editable": True,
                },
                {
                    "key": "balcony_1",
                    "label": "Balcony 1",
                    "current_rise": 183.75,
                    "editable": False,
                },
            ]
            reader.target_boxes = {
                "stalls": FakeBox("1,234.5"),
                "balcony_1": FakeBox("ignored"),
            }
            read_targets = reader.read_targets()

            apply_dialog = object.__new__(interpolation_class)
            apply_dialog.sections = sections
            apply_dialog.target_boxes = {
                "stalls": FakeBox("180"),
                "balcony_1": FakeBox("190"),
                "balcony_2": FakeBox("ignored"),
            }
            apply_dialog.overrides = {
                "stalls": None,
                "balcony_1": 185.0,
                "balcony_2": 195.0,
            }
            apply_dialog.accepted = False
            apply_closes = []
            apply_dialog.Close = apply_closes.append
            apply_dialog.on_apply(None, None)
            apply_result = {
                "overrides": dict(apply_dialog.overrides),
                "accepted": apply_dialog.accepted,
                "closes": tuple(apply_closes),
            }

            reset_dialog = object.__new__(interpolation_class)
            reset_dialog.overrides = {
                "stalls": 180.0,
                "balcony_1": 190.0,
            }
            reset_dialog.accepted = False
            reset_closes = []
            reset_dialog.Close = reset_closes.append
            reset_dialog.on_reset(None, None)
            reset_result = {
                "overrides": dict(reset_dialog.overrides),
                "accepted": reset_dialog.accepted,
                "closes": tuple(reset_closes),
            }

            cancel_dialog = object.__new__(interpolation_class)
            cancel_dialog.accepted = True
            cancel_closes = []
            cancel_dialog.Close = cancel_closes.append
            cancel_dialog.on_cancel(None, None)
            cancel_result = {
                "accepted": cancel_dialog.accepted,
                "closes": tuple(cancel_closes),
            }

            calculated_dialog = object.__new__(calculated_class)
            calculated_closes = []
            calculated_dialog.Close = calculated_closes.append
            calculated_dialog.on_close(None, None)

            return {
                "formatted_values": formatted_values,
                "rounded_values": tuple(rounded_values),
                "read_targets": read_targets,
                "apply": apply_result,
                "reset": reset_result,
                "cancel": cancel_result,
                "calculated_closes": tuple(calculated_closes),
                "events": tuple(events),
            }

        reference = exercise(self.oracle_tree)
        candidate = exercise(self.section_result_dialogs_tree)
        self.assertEqual(reference, candidate)
        self.assertEqual(
            ("170", "170.125", "171", "0"),
            candidate["formatted_values"],
        )
        self.assertEqual(
            (
                ("on_round_down", ("170", "180", "locked")),
                ("on_round_nearest", ("180", "180", "locked")),
                ("on_round_up", ("180", "190", "locked")),
            ),
            candidate["rounded_values"],
        )
        self.assertEqual(
            {
                "stalls": 180.0,
                "balcony_1": 190.0,
                "balcony_2": 195.0,
            },
            candidate["apply"]["overrides"],
        )
        self.assertTrue(candidate["apply"]["accepted"])
        self.assertEqual((True,), candidate["apply"]["closes"])
        self.assertEqual(
            {
                "stalls": None,
                "balcony_1": None,
                "balcony_2": None,
            },
            candidate["reset"]["overrides"],
        )
        self.assertFalse(candidate["cancel"]["accepted"])
        self.assertEqual((False,), candidate["cancel"]["closes"])
        self.assertEqual((True,), candidate["calculated_closes"])

    def test_settings_dialog_extraction_boundaries(self):
        oracle_classes = _class_nodes(self.oracle_tree)
        main_classes = _class_nodes(self.auditorium_tree)
        module_specs = (
            (
                "ProsceniumSettingsDialog",
                self.proscenium_settings_dialog_tree,
                "auditorium_generator.proscenium_settings_dialog",
                {
                    "PROSCENIUM_PARAM_KEYS",
                    "ProsceniumSettingsDialog",
                },
            ),
            (
                "BalconySettingsDialog",
                self.balcony_settings_dialog_tree,
                "auditorium_generator.balcony_settings_dialog",
                {
                    "BALCONY_SETTINGS_VERSION",
                    "BalconySettingsDialog",
                },
            ),
        )

        for (
            class_name,
            candidate_tree,
            import_module,
            imported_names,
        ) in module_specs:
            with self.subTest(class_name=class_name):
                candidate_class = _class_nodes(candidate_tree)[
                    class_name
                ]
                self.assertNotIn(class_name, main_classes)
                oracle_class = oracle_classes[class_name]
                if class_name == "BalconySettingsDialog":
                    self.assertNotEqual(
                        ast.dump(
                            oracle_class,
                            include_attributes=False,
                        ),
                        ast.dump(
                            candidate_class,
                            include_attributes=False,
                        ),
                    )
                    self.assertEqual(
                        [
                            node.name
                            for node in oracle_class.body
                            if isinstance(node, ast.FunctionDef)
                        ],
                        [
                            node.name
                            for node in candidate_class.body
                            if isinstance(node, ast.FunctionDef)
                        ],
                    )
                    candidate_init = next(
                        node
                        for node in candidate_class.body
                        if (
                            isinstance(node, ast.FunctionDef)
                            and node.name == "__init__"
                        )
                    )
                    self.assertEqual(
                        [
                            "self",
                            "values",
                            "stalls_result",
                            "first_row_distance",
                            "opening_height_mm",
                            "stalls_rear_z",
                            "effective_stalls_rear_z",
                            "tier_index",
                            "live_preview_callback",
                        ],
                        [
                            argument.arg
                            for argument in candidate_init.args.args
                        ],
                    )
                else:
                    self.assertEqual(
                        ast.dump(
                            oracle_class,
                            include_attributes=False,
                        ),
                        ast.dump(
                            candidate_class,
                            include_attributes=False,
                        ),
                    )

                main_imports = [
                    node
                    for node in self.auditorium_tree.body
                    if (
                        isinstance(node, ast.ImportFrom)
                        and node.level == 0
                        and node.module == import_module
                    )
                ]
                self.assertEqual(1, len(main_imports))
                self.assertEqual(
                    imported_names,
                    {
                        alias.name
                        for alias in main_imports[0].names
                    },
                )

        oracle_assignments = _assignment_nodes(self.oracle_tree)
        main_assignments = _assignment_nodes(self.auditorium_tree)
        constant_specs = (
            (
                "PROSCENIUM_PARAM_KEYS",
                self.proscenium_settings_dialog_tree,
            ),
            (
                "BALCONY_SETTINGS_VERSION",
                self.balcony_settings_dialog_tree,
            ),
        )
        for constant_name, candidate_tree in constant_specs:
            with self.subTest(constant_name=constant_name):
                self.assertNotIn(constant_name, main_assignments)
                self.assertEqual(
                    ast.dump(
                        oracle_assignments[constant_name],
                        include_attributes=False,
                    ),
                    ast.dump(
                        _assignment_nodes(candidate_tree)[
                            constant_name
                        ],
                        include_attributes=False,
                    ),
                )

        proscenium_imports = [
            (
                node.level,
                node.module,
                {alias.name for alias in node.names},
            )
            for node in self.proscenium_settings_dialog_tree.body
            if isinstance(node, ast.ImportFrom)
        ]
        self.assertEqual(
            [
                (
                    1,
                    "calculations.stage",
                    {
                        "calculated_proscenium_defaults",
                        "validate_proscenium_params",
                    },
                ),
            ],
            proscenium_imports,
        )
        balcony_imports = [
            (
                node.level,
                node.module,
                {alias.name for alias in node.names},
            )
            for node in self.balcony_settings_dialog_tree.body
            if isinstance(node, ast.ImportFrom)
        ]
        self.assertEqual(
            [
                (
                    1,
                    "balcony_height_reference",
                    {"rebase_balcony_last_platform_z"},
                ),
                (1, "constants", {"BALCONY_TIER_KEY_MAPS"}),
                (
                    1,
                    "calculations.sections",
                    {
                        "balcony_height_from_stalls_rear",
                        "balcony_height_to_absolute",
                        "calculate_balcony_max_rows",
                        "normalized_balcony_tier_params",
                        "standard_balcony_railing_height",
                    },
                ),
            ],
            balcony_imports,
        )

        for candidate_tree in (
            self.proscenium_settings_dialog_tree,
            self.balcony_settings_dialog_tree,
        ):
            self.assertEqual(
                [
                    ("Eto.Forms", "forms"),
                    ("Eto.Drawing", "drawing"),
                ],
                [
                    (alias.name, alias.asname)
                    for node in candidate_tree.body
                    if isinstance(node, ast.Import)
                    for alias in node.names
                ],
            )

        body_indices = {
            id(node): index
            for index, node in enumerate(self.auditorium_tree.body)
        }
        eto_import_indices = [
            body_indices[id(node)]
            for node in self.auditorium_tree.body
            if (
                isinstance(node, ast.Import)
                and any(
                    alias.name in ("Eto.Forms", "Eto.Drawing")
                    for alias in node.names
                )
            )
        ]
        settings_import_indices = [
            body_indices[id(node)]
            for node in self.auditorium_tree.body
            if (
                isinstance(node, ast.ImportFrom)
                and node.module
                in (
                    "auditorium_generator."
                    "proscenium_settings_dialog",
                    "auditorium_generator.balcony_settings_dialog",
                )
            )
        ]
        self.assertEqual(2, len(eto_import_indices))
        self.assertEqual(2, len(settings_import_indices))
        self.assertGreater(
            min(settings_import_indices),
            max(eto_import_indices),
        )

        package_exports = {
            alias.name
            for node in self.auditorium_generator_init_tree.body
            if isinstance(node, ast.ImportFrom)
            for alias in node.names
        }
        self.assertTrue(
            set(SETTINGS_DIALOG_CLASS_NAMES).isdisjoint(
                package_exports
            )
        )
        self.assertTrue(
            set(SETTINGS_DIALOG_CONSTANT_NAMES).isdisjoint(
                package_exports
            )
        )

    def test_settings_dialog_event_and_live_preview_parity(self):
        class FakeDialog(object):
            @classmethod
            def __class_getitem__(cls, item):
                return cls

        class FakeKeys(object):
            Enter = "enter"

        class FakeForms(object):
            Dialog = FakeDialog
            Keys = FakeKeys

        class FakeEvent(object):
            def __init__(self, key):
                self.Key = key
                self.Handled = False

        class FakeLabel(object):
            def __init__(self, text):
                self.Text = text

        def exercise(tree, class_name):
            dialog_class = _load_selected_class(
                tree,
                class_name,
                {"forms": FakeForms},
            )
            event_calls = []
            event_dialog = object.__new__(dialog_class)
            event_dialog.try_live_preview = (
                lambda: event_calls.append("preview") or True
            )
            enter_event = FakeEvent(FakeKeys.Enter)
            other_event = FakeEvent("escape")
            event_dialog.on_text_box_key_down(
                None,
                enter_event,
            )
            event_dialog.on_text_box_key_down(
                None,
                other_event,
            )
            event_dialog.on_text_box_lost_focus(None, None)

            callback_calls = []
            live_dialog = object.__new__(dialog_class)
            live_dialog.warning_label = FakeLabel("old warning")
            if class_name == "ProsceniumSettingsDialog":
                live_dialog.values = {"old": 1}
                live_dialog.read_values = lambda: {
                    "stage_preview_mode": "section_2d",
                    "main_stage_width": 18000.0,
                }

                def preview_callback(values):
                    callback_calls.append(
                        ("preview", dict(values))
                    )
                    values["callback_mutation"] = True
                    return True

                live_dialog.preview_callback = preview_callback
            else:
                live_dialog.values = {"old": 1}
                live_dialog.tier_index = 1
                live_dialog.read_values = lambda: {
                    "balcony_enabled": True,
                    "balcony_row_count": 7,
                }
                live_dialog.external_values = (
                    lambda values: {
                        "balcony2_row_count": values[
                            "balcony_row_count"
                        ],
                    }
                )

                def live_preview_callback(tier_index, values):
                    callback_calls.append(
                        (
                            "preview",
                            tier_index,
                            dict(values),
                            dict(live_dialog.values),
                        )
                    )
                    return {"row_count": 7}

                def update_labels(values, result):
                    callback_calls.append(
                        (
                            "labels",
                            dict(values),
                            dict(result),
                        )
                    )

                live_dialog.live_preview_callback = (
                    live_preview_callback
                )
                live_dialog.update_labels = update_labels

            live_result = live_dialog.try_live_preview()
            return {
                "event_calls": tuple(event_calls),
                "enter_handled": enter_event.Handled,
                "other_handled": other_event.Handled,
                "live_result": live_result,
                "callback_calls": tuple(callback_calls),
                "values": dict(live_dialog.values),
                "warning": live_dialog.warning_label.Text,
            }

        candidates = {
            "ProsceniumSettingsDialog": (
                self.proscenium_settings_dialog_tree
            ),
            "BalconySettingsDialog": (
                self.balcony_settings_dialog_tree
            ),
        }
        for class_name, candidate_tree in candidates.items():
            with self.subTest(class_name=class_name):
                reference = exercise(
                    self.oracle_tree,
                    class_name,
                )
                candidate = exercise(
                    candidate_tree,
                    class_name,
                )
                self.assertEqual(reference, candidate)
                self.assertEqual(
                    ("preview", "preview"),
                    candidate["event_calls"],
                )
                self.assertTrue(candidate["enter_handled"])
                self.assertFalse(candidate["other_handled"])
                self.assertTrue(candidate["live_result"])

        proscenium_result = exercise(
            self.proscenium_settings_dialog_tree,
            "ProsceniumSettingsDialog",
        )
        self.assertNotIn(
            "callback_mutation",
            proscenium_result["values"],
        )
        self.assertEqual("", proscenium_result["warning"])

        balcony_result = exercise(
            self.balcony_settings_dialog_tree,
            "BalconySettingsDialog",
        )
        self.assertEqual(
            {
                "old": 1,
                "balcony_enabled": True,
                "balcony_row_count": 7,
            },
            balcony_result["values"],
        )

    def test_main_dialog_extraction_boundaries(self):
        oracle_classes = _class_nodes(self.oracle_tree)
        candidate_classes = _class_nodes(self.main_dialog_tree)
        main_classes = _class_nodes(self.auditorium_tree)

        self.assertIn("AuditoriumDialog", oracle_classes)
        self.assertIn("AuditoriumDialog", candidate_classes)
        self.assertNotIn("AuditoriumDialog", main_classes)
        self.assertNotEqual(
            ast.dump(
                oracle_classes["AuditoriumDialog"],
                include_attributes=False,
            ),
            ast.dump(
                candidate_classes["AuditoriumDialog"],
                include_attributes=False,
            ),
        )
        self.assertEqual(
            [
                node.name
                for node in oracle_classes["AuditoriumDialog"].body
                if isinstance(node, ast.FunctionDef)
            ],
            [
                node.name
                for node in candidate_classes["AuditoriumDialog"].body
                if isinstance(node, ast.FunctionDef)
            ],
        )
        open_balcony_method = next(
            node
            for node in candidate_classes["AuditoriumDialog"].body
            if (
                isinstance(node, ast.FunctionDef)
                and node.name == "open_balcony_settings"
            )
        )
        self.assertIn(
            "stalls_height_reference_z",
            {
                node.func.id
                for node in ast.walk(open_balcony_method)
                if (
                    isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Name)
                )
            },
        )
        height_reference_imports = [
            node
            for node in self.main_dialog_tree.body
            if (
                isinstance(node, ast.ImportFrom)
                and node.level == 1
                and node.module == "balcony_height_reference"
            )
        ]
        self.assertEqual(1, len(height_reference_imports))
        self.assertEqual(
            {"stalls_height_reference_z"},
            {
                alias.name
                for alias in height_reference_imports[0].names
            },
        )

        direct_dialog_imports = [
            node
            for node in self.auditorium_tree.body
            if (
                isinstance(node, ast.ImportFrom)
                and node.level == 0
                and node.module
                == "auditorium_generator.main_dialog"
            )
        ]
        self.assertEqual(1, len(direct_dialog_imports))
        self.assertEqual(
            {"AuditoriumDialog"},
            {
                alias.name
                for alias in direct_dialog_imports[0].names
            },
        )

        oracle_assignments = _assignment_nodes(self.oracle_tree)
        candidate_assignments = _assignment_nodes(
            self.main_dialog_tree
        )
        main_assignments = _assignment_nodes(self.auditorium_tree)
        for constant_name in MAIN_DIALOG_CONSTANT_NAMES:
            with self.subTest(constant_name=constant_name):
                self.assertIn(constant_name, oracle_assignments)
                self.assertIn(constant_name, candidate_assignments)
                self.assertNotIn(constant_name, main_assignments)
                self.assertEqual(
                    ast.dump(
                        oracle_assignments[constant_name],
                        include_attributes=False,
                    ),
                    ast.dump(
                        candidate_assignments[constant_name],
                        include_attributes=False,
                    ),
                )

        package_exports = {
            alias.name
            for node in self.auditorium_generator_init_tree.body
            if isinstance(node, ast.ImportFrom)
            for alias in node.names
        }
        self.assertNotIn("AuditoriumDialog", package_exports)
        self.assertTrue(
            set(MAIN_DIALOG_CONSTANT_NAMES).isdisjoint(
                package_exports
            )
        )

    def test_main_dialog_basic_event_behavior_parity(self):
        class FakeDialog(object):
            @classmethod
            def __class_getitem__(cls, item):
                return cls

        class FakeKeys(object):
            Enter = "enter"

        class FakeForms(object):
            Dialog = FakeDialog
            Keys = FakeKeys

        class FakeEvent(object):
            def __init__(self, key):
                self.Key = key
                self.Handled = False

        class FakeControl(object):
            def __init__(self, **values):
                self.__dict__.update(values)

        def exercise(tree):
            dialog_class = _load_selected_class(
                tree,
                "AuditoriumDialog",
                {"forms": FakeForms},
            )

            key_events = []
            key_dialog = object.__new__(dialog_class)
            key_dialog.update_preview = (
                lambda show_error=True: key_events.append(
                    ("update", show_error)
                )
            )
            enter_event = FakeEvent(FakeKeys.Enter)
            other_event = FakeEvent("escape")
            key_dialog.on_text_box_key_down(None, enter_event)
            key_dialog.on_text_box_key_down(None, other_event)

            option_events = []
            option_dialog = object.__new__(dialog_class)
            option_dialog.aisle_stair_tread_box = FakeControl(
                Enabled=None
            )
            option_dialog.stepped_radio = FakeControl(Checked=True)
            option_dialog.update_preview = (
                lambda show_error=True: option_events.append(
                    ("update", show_error)
                )
            )
            option_dialog.on_option_changed(None, None)
            enabled_when_checked = (
                option_dialog.aisle_stair_tread_box.Enabled
            )
            option_dialog.stepped_radio.Checked = False
            option_dialog.on_option_changed(None, None)
            enabled_when_unchecked = (
                option_dialog.aisle_stair_tread_box.Enabled
            )

            cancel_dialog = object.__new__(dialog_class)
            cancel_dialog.accepted = True
            cancel_closes = []
            cancel_dialog.Close = cancel_closes.append
            cancel_dialog.on_cancel(None, None)

            disable_events = []

            class FakeConduit(object):
                def __init__(self):
                    self._enabled = True

                @property
                def Enabled(self):
                    return self._enabled

                @Enabled.setter
                def Enabled(self, value):
                    self._enabled = value
                    disable_events.append(("enabled", value))

                def clear(self):
                    disable_events.append(("clear",))

            class FakeViews(object):
                def Redraw(self):
                    disable_events.append(("redraw",))

            disable_dialog = object.__new__(dialog_class)
            disable_dialog.conduit = FakeConduit()
            disable_dialog.doc = FakeControl(Views=FakeViews())
            disable_dialog.disable_preview()

            return {
                "key_events": tuple(key_events),
                "enter_handled": enter_event.Handled,
                "other_handled": other_event.Handled,
                "option_events": tuple(option_events),
                "option_enabled": (
                    enabled_when_checked,
                    enabled_when_unchecked,
                ),
                "cancel_accepted": cancel_dialog.accepted,
                "cancel_closes": tuple(cancel_closes),
                "disable_events": tuple(disable_events),
                "conduit_enabled": disable_dialog.conduit.Enabled,
            }

        reference = exercise(self.oracle_tree)
        candidate = exercise(self.main_dialog_tree)
        self.assertEqual(reference, candidate)
        self.assertEqual(
            (("update", True),),
            candidate["key_events"],
        )
        self.assertTrue(candidate["enter_handled"])
        self.assertFalse(candidate["other_handled"])
        self.assertEqual(
            (("update", False), ("update", False)),
            candidate["option_events"],
        )
        self.assertEqual(
            (True, False),
            candidate["option_enabled"],
        )
        self.assertFalse(candidate["cancel_accepted"])
        self.assertEqual((False,), candidate["cancel_closes"])
        self.assertEqual(
            (
                ("enabled", False),
                ("clear",),
                ("redraw",),
            ),
            candidate["disable_events"],
        )
        self.assertFalse(candidate["conduit_enabled"])

    def test_main_dialog_section_override_validity_parity(self):
        class FakeDialog(object):
            @classmethod
            def __class_getitem__(cls, item):
                return cls

        class FakeForms(object):
            Dialog = FakeDialog

        section_keys = (
            "stalls",
            "balcony_1",
            "balcony_2",
        )
        previous = {
            "stalls": "stalls-a",
            "balcony_1": "balcony-1-a",
            "balcony_2": "balcony-2-a",
        }
        scenarios = (
            (
                "no-previous",
                None,
                {
                    "stalls": "stalls-a",
                    "balcony_1": "balcony-1-a",
                    "balcony_2": "balcony-2-a",
                },
            ),
            (
                "stalls-changed",
                previous,
                {
                    "stalls": "stalls-b",
                    "balcony_1": "balcony-1-b",
                    "balcony_2": "balcony-2-b",
                },
            ),
            (
                "balcony-1-changed",
                previous,
                {
                    "stalls": "stalls-a",
                    "balcony_1": "balcony-1-b",
                    "balcony_2": "balcony-2-b",
                },
            ),
            (
                "balcony-2-changed",
                previous,
                {
                    "stalls": "stalls-a",
                    "balcony_1": "balcony-1-a",
                    "balcony_2": "balcony-2-b",
                },
            ),
            (
                "unchanged",
                previous,
                {
                    "stalls": "stalls-a",
                    "balcony_1": "balcony-1-a",
                    "balcony_2": "balcony-2-a",
                },
            ),
        )

        def exercise(tree):
            signature_calls = []

            def fake_section_solver_signatures(params):
                signature_calls.append(params["scenario"])
                return dict(params["signatures"])

            dialog_class = _load_selected_class(
                tree,
                "AuditoriumDialog",
                {
                    "forms": FakeForms,
                    "SECTION_RISE_KEYS": section_keys,
                    "section_solver_signatures": (
                        fake_section_solver_signatures
                    ),
                },
            )
            results = []
            for scenario_name, old_signatures, signatures in scenarios:
                dialog = object.__new__(dialog_class)
                dialog.section_rise_overrides = {
                    "stalls": 101.0,
                    "balcony_1": 202.0,
                    "balcony_2": 303.0,
                }
                dialog.section_solver_signatures = (
                    None
                    if old_signatures is None
                    else dict(old_signatures)
                )
                dialog.update_section_override_validity(
                    {
                        "scenario": scenario_name,
                        "signatures": signatures,
                    }
                )
                results.append(
                    (
                        scenario_name,
                        dict(dialog.section_rise_overrides),
                        dict(dialog.section_solver_signatures),
                    )
                )
            return tuple(results), tuple(signature_calls)

        reference = exercise(self.oracle_tree)
        candidate = exercise(self.main_dialog_tree)
        self.assertEqual(reference, candidate)

        results, signature_calls = candidate
        self.assertEqual(
            tuple(scenario[0] for scenario in scenarios),
            signature_calls,
        )
        overrides_by_scenario = {
            scenario_name: overrides
            for scenario_name, overrides, signatures in results
        }
        self.assertEqual(
            {
                "stalls": 101.0,
                "balcony_1": 202.0,
                "balcony_2": 303.0,
            },
            overrides_by_scenario["no-previous"],
        )
        self.assertEqual(
            {
                "stalls": None,
                "balcony_1": None,
                "balcony_2": None,
            },
            overrides_by_scenario["stalls-changed"],
        )
        self.assertEqual(
            {
                "stalls": 101.0,
                "balcony_1": None,
                "balcony_2": None,
            },
            overrides_by_scenario["balcony-1-changed"],
        )
        self.assertEqual(
            {
                "stalls": 101.0,
                "balcony_1": 202.0,
                "balcony_2": None,
            },
            overrides_by_scenario["balcony-2-changed"],
        )
        self.assertEqual(
            {
                "stalls": 101.0,
                "balcony_1": 202.0,
                "balcony_2": 303.0,
            },
            overrides_by_scenario["unchanged"],
        )

    def test_command_runtime_extraction_boundaries(self):
        oracle_nodes = _function_nodes(self.oracle_tree)
        candidate_nodes = _function_nodes(self.command_runtime_tree)
        auditorium_nodes = _function_nodes(self.auditorium_tree)
        reference_functions = _load_selected_functions(
            self.oracle_tree,
            COMMAND_RUNTIME_FUNCTION_NAMES,
            {},
        )
        candidate_functions = _load_selected_functions(
            self.command_runtime_tree,
            COMMAND_RUNTIME_FUNCTION_NAMES,
            {},
        )

        self.assertEqual(
            list(COMMAND_RUNTIME_FUNCTION_NAMES),
            [
                node.name
                for node in self.command_runtime_tree.body
                if isinstance(node, ast.FunctionDef)
            ],
        )
        for name in COMMAND_RUNTIME_FUNCTION_NAMES:
            with self.subTest(function=name):
                self.assertIn(name, oracle_nodes)
                self.assertIn(name, candidate_nodes)
                self.assertNotIn(name, auditorium_nodes)
                self.assertEqual(
                    ast.dump(
                        oracle_nodes[name],
                        include_attributes=False,
                    ),
                    ast.dump(
                        candidate_nodes[name],
                        include_attributes=False,
                    ),
                )
                self.assertEqual(
                    str(inspect.signature(reference_functions[name])),
                    str(inspect.signature(candidate_functions[name])),
                )

        self.assertEqual({}, auditorium_nodes)
        direct_main_imports = [
            node
            for node in self.auditorium_tree.body
            if (
                isinstance(node, ast.ImportFrom)
                and node.level == 0
                and node.module
                == "auditorium_generator.command_runtime"
                and any(
                    alias.name == "main"
                    for alias in node.names
                )
            )
        ]
        self.assertEqual(1, len(direct_main_imports))
        self.assertEqual(
            (("main", None),),
            tuple(
                (alias.name, alias.asname)
                for alias in direct_main_imports[0].names
            ),
        )

        self.assertIsInstance(self.oracle_tree.body[-1], ast.If)
        self.assertIsInstance(self.auditorium_tree.body[-1], ast.If)
        self.assertEqual(
            ast.dump(
                self.oracle_tree.body[-1],
                include_attributes=False,
            ),
            ast.dump(
                self.auditorium_tree.body[-1],
                include_attributes=False,
            ),
        )

    def test_command_runtime_selection_and_modal_fake_parity(self):
        def exercise(tree):
            selection_results = []
            for command_result in ("success", "cancel"):
                events = []

                class FakeCurve(object):
                    def DuplicateCurve(self):
                        events.append(("duplicate-curve",))
                        return "opening-curve-copy"

                class FakeReference(object):
                    def Curve(self):
                        events.append(("reference-curve",))
                        return FakeCurve()

                class FakeGetter(object):
                    def __init__(self):
                        self.GeometryFilter = None
                        self.SubObjectSelect = None

                    def SetCommandPrompt(self, prompt):
                        events.append(("set-prompt", prompt))

                    def EnablePreSelect(self, first, second):
                        events.append(
                            ("enable-preselect", first, second)
                        )

                    def Get(self):
                        events.append(("get",))

                    def CommandResult(self):
                        events.append(("command-result",))
                        return command_result

                    def Object(self, index):
                        events.append(("object", index))
                        return FakeReference()

                getter = FakeGetter()

                class FakeRic(object):
                    @staticmethod
                    def GetObject():
                        events.append(("get-object",))
                        return getter

                class FakeObjectType(object):
                    Curve = "curve-filter"

                class FakeRd(object):
                    ObjectType = FakeObjectType

                class FakeResult(object):
                    Success = "success"

                class FakeRc(object):
                    Result = FakeResult

                loaded = _load_selected_functions(
                    tree,
                    ("select_opening_curve",),
                    {
                        "ric": FakeRic,
                        "rd": FakeRd,
                        "rc": FakeRc,
                    },
                )
                result = loaded["select_opening_curve"]()
                selection_results.append(
                    {
                        "scenario": command_result,
                        "result": result,
                        "events": tuple(events),
                        "geometry_filter": getter.GeometryFilter,
                        "subobject_select": getter.SubObjectSelect,
                    }
                )

            modal_results = []
            for raises in (False, True):
                events = []

                class FakeEtoExtensions(object):
                    @staticmethod
                    def ShowSemiModal(dialog, doc, window):
                        events.append(
                            ("show-semi-modal", dialog.name, doc, window)
                        )
                        if raises:
                            raise RuntimeError("semi-modal unavailable")

                class FakeRhinoEtoApp(object):
                    MainWindow = "main-window"

                class FakeUI(object):
                    EtoExtensions = FakeEtoExtensions
                    RhinoEtoApp = FakeRhinoEtoApp

                class FakeRhino(object):
                    UI = FakeUI

                class FakeDialog(object):
                    name = "dialog"

                    def ShowModal(self, window):
                        events.append(("show-modal", window))

                loaded = _load_selected_functions(
                    tree,
                    ("show_dialog_semi_modal",),
                    {"Rhino": FakeRhino},
                )
                result = loaded["show_dialog_semi_modal"](
                    FakeDialog(),
                    "document",
                )
                modal_results.append(
                    {
                        "raises": raises,
                        "result": result,
                        "events": tuple(events),
                    }
                )

            return {
                "selection": tuple(selection_results),
                "modal": tuple(modal_results),
            }

        reference = exercise(self.oracle_tree)
        candidate = exercise(self.command_runtime_tree)
        self.assertEqual(reference, candidate)

        success, cancel = candidate["selection"]
        self.assertEqual("opening-curve-copy", success["result"])
        self.assertIsNone(cancel["result"])
        self.assertEqual("curve-filter", success["geometry_filter"])
        self.assertFalse(success["subobject_select"])
        self.assertEqual(
            (
                "get-object",
                "set-prompt",
                "enable-preselect",
                "get",
                "command-result",
                "object",
                "reference-curve",
                "duplicate-curve",
            ),
            tuple(event[0] for event in success["events"]),
        )
        self.assertEqual(
            (
                "get-object",
                "set-prompt",
                "enable-preselect",
                "get",
                "command-result",
            ),
            tuple(event[0] for event in cancel["events"]),
        )
        self.assertEqual(
            (
                ("show-semi-modal", "dialog", "document", "main-window"),
            ),
            candidate["modal"][0]["events"],
        )
        self.assertEqual(
            (
                ("show-semi-modal", "dialog", "document", "main-window"),
                ("show-modal", "main-window"),
            ),
            candidate["modal"][1]["events"],
        )

    def test_command_runtime_main_event_trace_fake_parity(self):
        scenarios = (
            "success",
            "dialog-cancel",
            "analyze-error",
            "seat-warning",
            "show-error",
        )

        def exercise(tree, scenario):
            events = []

            class FakeDialogs(object):
                @staticmethod
                def ShowMessageBox(message, title):
                    events.append(("message", message, title))

            class FakeUI(object):
                Dialogs = FakeDialogs

            class FakeRhinoDoc(object):
                ActiveDoc = "document"

            class FakeRhino(object):
                RhinoDoc = FakeRhinoDoc
                UI = FakeUI

            def fake_select_opening_curve():
                events.append(("select",))
                return "opening-curve"

            def fake_analyze_opening_rectangle(curve, doc):
                events.append(("analyze", curve, doc))
                if scenario == "analyze-error":
                    raise ValueError("invalid opening")
                return "stage-data"

            def fake_load_auditorium_seat_source():
                events.append(("load-seat-source",))
                if scenario == "seat-warning":
                    raise RuntimeError("seat source missing")
                return "seat-source"

            class FakeDialog(object):
                def __init__(self):
                    self.accepted = scenario != "dialog-cancel"
                    self.preview_data = (
                        "preview-data"
                        if self.accepted
                        else "cancelled-preview-data"
                    )

                def disable_preview(self):
                    events.append(("disable-preview",))

            def fake_auditorium_dialog(stage_data, doc, seat_source):
                events.append(
                    ("dialog", stage_data, doc, seat_source)
                )
                return FakeDialog()

            def fake_show_dialog_semi_modal(dialog, doc):
                events.append(("show-dialog", doc))
                if scenario == "show-error":
                    raise RuntimeError("dialog display failed")

            def fake_bake_preview(preview_data, doc):
                events.append(("bake", preview_data, doc))
                return "baked"

            loaded = _load_selected_functions(
                tree,
                ("main",),
                {
                    "Rhino": FakeRhino,
                    "select_opening_curve": (
                        fake_select_opening_curve
                    ),
                    "analyze_opening_rectangle": (
                        fake_analyze_opening_rectangle
                    ),
                    "load_auditorium_seat_source": (
                        fake_load_auditorium_seat_source
                    ),
                    "AuditoriumDialog": fake_auditorium_dialog,
                    "show_dialog_semi_modal": (
                        fake_show_dialog_semi_modal
                    ),
                    "bake_preview": fake_bake_preview,
                },
            )
            try:
                result = loaded["main"]()
            except Exception as error:
                outcome = (
                    "error",
                    type(error).__name__,
                    error.args,
                )
            else:
                outcome = ("return", result)
            return {
                "outcome": outcome,
                "events": tuple(events),
            }

        reference = {
            scenario: exercise(self.oracle_tree, scenario)
            for scenario in scenarios
        }
        candidate = {
            scenario: exercise(self.command_runtime_tree, scenario)
            for scenario in scenarios
        }
        self.assertEqual(reference, candidate)

        self.assertEqual(
            (
                "select",
                "analyze",
                "load-seat-source",
                "dialog",
                "show-dialog",
                "disable-preview",
                "bake",
            ),
            tuple(
                event[0]
                for event in candidate["success"]["events"]
            ),
        )
        self.assertEqual(
            (
                "select",
                "analyze",
                "load-seat-source",
                "dialog",
                "show-dialog",
                "disable-preview",
            ),
            tuple(
                event[0]
                for event in candidate["dialog-cancel"]["events"]
            ),
        )
        self.assertEqual(
            ("select", "analyze", "message"),
            tuple(
                event[0]
                for event in candidate["analyze-error"]["events"]
            ),
        )
        self.assertEqual(
            "Auditorium Section Generator",
            candidate["analyze-error"]["events"][-1][2],
        )
        self.assertEqual(
            (
                "select",
                "analyze",
                "load-seat-source",
                "message",
                "dialog",
                "show-dialog",
                "disable-preview",
                "bake",
            ),
            tuple(
                event[0]
                for event in candidate["seat-warning"]["events"]
            ),
        )
        self.assertEqual(
            "Auditorium 3D Seat Source",
            candidate["seat-warning"]["events"][3][2],
        )
        self.assertIsNone(
            candidate["seat-warning"]["events"][4][3]
        )
        self.assertEqual(
            (
                "select",
                "analyze",
                "load-seat-source",
                "dialog",
                "show-dialog",
                "disable-preview",
            ),
            tuple(
                event[0]
                for event in candidate["show-error"]["events"]
            ),
        )
        self.assertEqual(
            ("error", "RuntimeError", ("dialog display failed",)),
            candidate["show-error"]["outcome"],
        )

        bake_scenarios = tuple(
            scenario
            for scenario in scenarios
            if any(
                event[0] == "bake"
                for event in candidate[scenario]["events"]
            )
        )
        self.assertEqual(
            ("success", "seat-warning"),
            bake_scenarios,
        )

    def test_identity_contracts(self):
        for label, namespace in (
            ("oracle", self.oracle),
            ("candidate", sections),
        ):
            with self.subTest(namespace=label):
                params = _base_params()
                stalls = _function(
                    namespace,
                    "calculate_section",
                )(params)

                unchanged = _function(
                    namespace,
                    "add_stalls_ceiling_validation",
                )(stalls, None)
                self.assertIs(stalls, unchanged)

                unchanged = _function(
                    namespace,
                    "apply_stalls_rise_interpolation",
                )(params, stalls, None, None)
                self.assertIs(stalls, unchanged)

                with_ceiling = _function(
                    namespace,
                    "add_stalls_ceiling_validation",
                )(stalls, 16000.0)
                self.assertIsNot(stalls, with_ceiling)

                tier1_params = _function(
                    namespace,
                    "normalized_balcony_tier_params",
                )(params, 0)
                balcony = _function(
                    namespace,
                    "calculate_balcony_section",
                )(
                    tier1_params,
                    stalls,
                    8000.0,
                    include_maximum=False,
                    tier_index=0,
                )
                unchanged = _function(
                    namespace,
                    "apply_balcony_rise_interpolation",
                )(
                    tier1_params,
                    balcony,
                    stalls,
                    8000.0,
                    None,
                )
                self.assertIs(balcony, unchanged)

                disabled = _function(
                    namespace,
                    "apply_balcony_rise_interpolation",
                )(
                    tier1_params,
                    None,
                    stalls,
                    8000.0,
                    800.0,
                )
                self.assertIsNone(disabled)


if __name__ == "__main__":
    unittest.main()
