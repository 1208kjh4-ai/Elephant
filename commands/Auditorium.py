# -*- coding: utf-8 -*-
"""
Elephant Tools - Auditorium Section Generator (Initial Version)
Target: Rhino 8 Python / RhinoCommon / Eto.Forms

Workflow
--------
1. Pick the audience-view left and right ends of a horizontal datum line.
2. The line midpoint and elevation define the lowest audience-floor datum.
3. Enter PW, PH, stage type, and auditorium parameters in the Eto dialog.
4. Preview stepped or sloped seating sections.
5. Press Flip to reverse the auditorium direction.
6. Press OK to bake the preview geometry.

Important stepped-floor rule
----------------------------
Initial riser heights keep their full floating-point precision. Optional
section-height interpolation is applied only after the sightline solution.
"""

import os
import sys

_SCRIPT_PATH = globals().get("__file__")
_COMMANDS_DIR = (
    os.path.dirname(os.path.realpath(_SCRIPT_PATH))
    if _SCRIPT_PATH
    else None
)
if _COMMANDS_DIR and _COMMANDS_DIR not in sys.path:
    sys.path.insert(0, _COMMANDS_DIR)

_AUDITORIUM_MODULE_PREFIX = "auditorium_generator"
for _module_name in tuple(sys.modules):
    if (
        _module_name == _AUDITORIUM_MODULE_PREFIX
        or _module_name.startswith(_AUDITORIUM_MODULE_PREFIX + ".")
    ):
        del sys.modules[_module_name]

from auditorium_generator.constants import (
    AISLE_STAIR_TARGET_RISER_HEIGHT,
    BALCONY_TIER_KEY_MAPS,
    CHAIR_FRONT_X,
    CHAIR_SIGHT_POINT_X,
    CHAIR_TOP_Z,
)
from auditorium_generator.calculations.sections import (
    add_stalls_ceiling_validation,
    apply_balcony_rise_interpolation,
    apply_stalls_rise_interpolation,
    balcony_height_from_stalls_rear,
    balcony_height_to_absolute,
    balcony_result_is_displayable,
    balcony_solver_signature,
    calculate_actual_sightline_status,
    calculate_balcony_max_rows,
    calculate_balcony_section,
    calculate_balcony_spatial_max_rows,
    calculate_section,
    ceil_to_integer_mm,
    interpolate_front_anchored_z_values,
    interpolate_rear_anchored_z_values,
    is_finite_number,
    normalized_balcony_tier_params,
    rebuild_balcony_vertical_fields,
    rebuild_stalls_vertical_fields,
    section_solver_signatures,
    stalls_solver_signature,
    standard_balcony_railing_height,
    validate_section_rise_target,
)
from auditorium_generator.calculations.seating import (
    AUTO_SEAT_BLOCK,
    MAXIMUM_3D_CHAIR_COUNT,
    calculate_3d_seat_placements,
    calculate_seat_layout_width,
    calculate_total_3d_seat_count,
    resolve_row_seat_block_counts,
    seat_blocks_have_auto,
)
from auditorium_generator.balcony_preview_geometry import (
    append_balcony_tier_geometry,
)
from auditorium_generator.auditorium_boundary import (
    boundary_contains_point,
    boundary_contains_points,
    build_boundary_context,
    normalize_boundary_curve,
)
from auditorium_generator.boundary_row_layout import (
    build_tier_row_regions,
    curve_segments_inside_boundary,
    radial_row_segments,
    radial_segment_lateral_intervals,
    rectangular_row_segments,
    segment_lateral_intervals,
)
from auditorium_generator.boundary_surface_geometry import (
    build_boundary_ceiling_brep,
    build_boundary_perimeter_wall_brep,
    build_boundary_vertical_cutter,
    calculate_boundary_max_radius,
    calculate_boundary_plan_extents,
    extrude_wall_curve,
    split_brep_inside_boundary,
)
from auditorium_generator.calculations.stage import (
    DEFAULT_OPENING_HEIGHT,
    MIN_OPENING_HEIGHT,
    STAGE_EQUIPMENT_CLEARANCE,
    STAGE_TYPE_OPEN_PODIUM,
    STAGE_TYPE_PROSCENIUM,
    calculated_proscenium_defaults,
    calculate_stage_section_dimensions,
    is_proscenium_stage,
    validate_proscenium_params,
    validate_stage_reference_dimensions,
)
from auditorium_generator.chair_preview_geometry import (
    CHAIR_ARC_DATA,
    CHAIR_LINE_DATA,
    build_chair_curves,
)
from auditorium_generator.compatibility import almost_equal
from auditorium_generator.document_baking import (
    bake_preview,
    create_attributes,
    ensure_seat_instance_definition,
)
from auditorium_generator.formatting import (
    format_riser_height_label,
    format_section_height_dimension,
)
from auditorium_generator.floor_surface_geometry import (
    append_floor_surface,
    append_stage_envelope_surfaces,
    append_understage_envelope_surfaces,
    build_audience_boundary_wall_breps,
    build_floor_surface_geometry,
    build_radial_chord_to_arc_surface,
    create_stage_vertical_face,
    extrude_section_curve_across_width,
)
from auditorium_generator.geometry_metadata import (
    section_floor_surface_name,
    stage_edge_adjacencies,
    stage_space_envelope_name,
    stage_space_top_z,
)
from auditorium_generator.main_dialog import AuditoriumDialog
from auditorium_generator.preview_conduit import AuditoriumPreviewConduit
from auditorium_generator.preview_mesh_geometry import (
    append_geometry_to_mesh,
    build_seat_source_preview_mesh,
)
from auditorium_generator.preview_geometry import (
    build_preview_geometry,
)
from auditorium_generator.preview_palette import (
    FLOOR_SURFACE_PREVIEW_TRANSPARENCY,
    PREVIEW_3D_ARMREST,
    PREVIEW_3D_CHAIR,
    PREVIEW_AISLE,
    PREVIEW_AUDITORIUM_CEILING,
    PREVIEW_AUX_STAGE,
    PREVIEW_BALCONY,
    PREVIEW_BALCONY_RAIL,
    PREVIEW_BALCONY_SECOND,
    PREVIEW_FLOOR,
    PREVIEW_FULL_STAGE_SIGHT,
    PREVIEW_GRID,
    PREVIEW_MAIN_STAGE,
    PREVIEW_ORCHESTRA_PIT,
    PREVIEW_POINT,
    PREVIEW_REFERENCE,
    PREVIEW_SEAT,
    PREVIEW_SECTION_DIMENSION,
    PREVIEW_SIGHT,
    PREVIEW_STAGE_APRON,
    PREVIEW_STAGE_CLEARANCE,
    PREVIEW_STAGE_SECTION,
    PREVIEW_UNDERSTAGE,
    PREVIEW_WARNING,
)
from auditorium_generator.opening_geometry import (
    analyze_reference_baseline,
    analyze_opening_rectangle,
    get_curve_plane,
)
from auditorium_generator.rhino_primitives import (
    build_plan_rectangle,
    get_stage_directions,
    line_curve,
    point_at,
    stage_space_point,
    unit_scale_from_mm,
)
from auditorium_generator.radial_layout import (
    build_plan_layout_context,
    build_radial_arc,
    build_radial_side_line,
    normalize_plan_layout_radius,
    radial_available_arc_length,
    radial_available_chord_width,
    radial_frame,
    radial_point,
    sweep_section_curve_radially,
)
from auditorium_generator.section_preview_annotations import (
    build_riser_height_preview_labels,
    build_section_height_dimension_preview,
)
from auditorium_generator.section_interpolation_constants import (
    SECTION_INTERPOLATION_WARNING_RATIO,
    SECTION_RISE_KEYS,
)
from auditorium_generator.section_result_dialogs import (
    CalculatedResultDialog,
    SectionDimensionInterpolationDialog,
)
from auditorium_generator.seat_preview_geometry import (
    SEAT_SOURCE_ARMREST_WIDTH,
    SEAT_SOURCE_CHAIR_WIDTH,
    SEAT_WIREFRAME_PREVIEW_THRESHOLD,
    build_3d_seat_module_geometry,
    seat_module_transform,
)
from auditorium_generator.seat_source import (
    SEAT_SOURCE_FILE_NAME,
    auditorium_seat_source_path,
    choose_seat_source_components,
    compact_component_name,
    component_name_kind,
    duplicate_file3dm_geometry,
    file3dm_definition_geometry,
    geometry_collection_bounding_box,
    load_auditorium_seat_source,
    normalize_seat_source_component,
    source_component_candidate,
)
from auditorium_generator.stage_preview_geometry import (
    SIDE_STAGE_CLEARANCE,
    build_proscenium_opening_frame_curves,
    build_proscenium_plan_curves,
    build_stage_audience_transition_curves,
    build_stage_section_2d_curves,
    build_stage_space_3d_curves,
    calculate_proscenium_space_layout,
)

import scriptcontext as sc
import Rhino
import Rhino.Geometry as rg
import Rhino.DocObjects as rd
import Rhino.Input as ri
import Rhino.Input.Custom as ric
import Rhino.Commands as rc
import Rhino.UI
import Eto.Forms as forms
import Eto.Drawing as drawing
from auditorium_generator.proscenium_settings_dialog import (
    PROSCENIUM_PARAM_KEYS,
    ProsceniumSettingsDialog,
)
from auditorium_generator.balcony_settings_dialog import (
    BALCONY_SETTINGS_VERSION,
    BalconySettingsDialog,
)
from System.Drawing import Color

import auditorium_generator.command_runtime as _command_runtime
from auditorium_generator.command_runtime import main

select_opening_curve = _command_runtime.select_opening_curve
select_reference_baseline = _command_runtime.select_reference_baseline
select_optional_auditorium_boundary = (
    _command_runtime.select_optional_auditorium_boundary
)
show_dialog_semi_modal = _command_runtime.show_dialog_semi_modal


if __name__ == "__main__":
    main()
