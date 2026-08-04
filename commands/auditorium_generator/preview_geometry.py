# -*- coding: utf-8 -*-
"""Build the complete auditorium preview geometry."""

import Rhino.Geometry as rg

from .balcony_height_reference import (
    rebase_balcony_last_platform_z,
    stalls_height_reference_z,
)
from .balcony_preview_geometry import append_balcony_tier_geometry
from .auditorium_boundary import build_boundary_context
from .boundary_row_layout import build_tier_row_regions
from .calculations.sections import (
    CHAIR_TOP_Z,
    add_balcony_ceiling_validation,
    add_stalls_ceiling_validation,
    apply_balcony_rise_interpolation,
    apply_stalls_rise_interpolation,
    balcony_result_is_displayable,
    calculate_auditorium_ceiling,
    calculate_balcony_section,
    calculate_section,
    normalized_balcony_tier_params,
)
from .calculations.seating import (
    MAXIMUM_3D_CHAIR_COUNT,
    calculate_seat_layout_width,
    calculate_tier_row_layouts,
    calculate_total_3d_seat_count,
    normalize_tier_row_overrides,
    tier_row_override_fit_issues,
)
from .calculations.stage import calculate_stage_section_dimensions
from .chair_preview_geometry import build_chair_curves
from .section_interpolation_constants import SECTION_RISE_KEYS
from .floor_surface_geometry import build_floor_surface_geometry
from .preview_palette import (
    PREVIEW_AISLE,
    PREVIEW_AUDITORIUM_CEILING,
    PREVIEW_BALCONY,
    PREVIEW_BALCONY_RAIL,
    PREVIEW_FLOOR,
    PREVIEW_FULL_STAGE_SIGHT,
    PREVIEW_POINT,
    PREVIEW_REFERENCE,
    PREVIEW_SEAT,
    PREVIEW_SIGHT,
    PREVIEW_STAGE_APRON,
    PREVIEW_WARNING,
)
from .rhino_primitives import (
    line_curve,
    point_at,
    unit_scale_from_mm,
)
from .radial_layout import (
    build_plan_layout_context,
    build_radial_arc,
    build_radial_side_line,
)
from .seat_preview_geometry import (
    SEAT_CURVE_PREVIEW_THRESHOLD,
    build_3d_seat_module_geometry,
)
from .section_preview_annotations import (
    build_riser_height_preview_labels,
    build_section_height_dimension_preview,
)
from .stage_preview_geometry import (
    build_proscenium_opening_frame_curves,
    build_proscenium_plan_curves,
    build_stage_audience_transition_curves,
    build_stage_section_2d_curves,
    build_stage_space_3d_curves,
)
from .vertical_placement import calculate_vertical_placement


def build_preview_geometry(
    stage_data,
    params,
    doc,
    seat_source=None,
    section_rise_overrides=None
):
    """Build preview and bake geometry without adding it to the document."""
    rise_overrides = {
        key: None for key in SECTION_RISE_KEYS
    }
    if section_rise_overrides:
        rise_overrides.update(section_rise_overrides)

    mm_scale = unit_scale_from_mm(doc)
    audience_datum_point = rg.Point3d(
        stage_data.get(
            "audience_datum_point",
            stage_data["stage_point"],
        )
    )
    calculation_params = dict(params)
    calculation_params["stage_reference_x"] = 0.0
    raw_result = calculate_section(calculation_params)
    stalls_reference_z = stalls_height_reference_z(raw_result)
    result = apply_stalls_rise_interpolation(
        calculation_params,
        raw_result,
        rise_overrides["stalls"],
        None
    )
    effective_stalls_rear_z = result["base_z_values"][-1]
    vertical_placement = calculate_vertical_placement(
        audience_datum_point.Z,
        mm_scale,
        params["stage_height"],
        effective_stalls_rear_z,
        params.get("stalls_rear_world_z"),
    )
    audience_datum_point.Z = vertical_placement[
        "placed_datum_z_model_units"
    ]
    opening_stage_point = (
        rg.Point3d(audience_datum_point)
        + rg.Vector3d.ZAxis
        * (params["stage_height"] * mm_scale)
    )

    direction = rg.Vector3d(stage_data["default_direction"])
    if params["flipped"]:
        direction.Reverse()

    opening_width_mm = params["opening_width"]
    opening_height_mm = params["opening_height"]
    layout_context = build_plan_layout_context(
        opening_stage_point,
        direction,
        opening_width_mm,
        params.get("plan_layout_radius", 0.0),
        mm_scale
    )
    boundary_context = build_boundary_context(
        stage_data.get("auditorium_boundary_curve"),
        audience_datum_point,
        max(float(doc.ModelAbsoluteTolerance), 1e-6),
    )
    # The circle center remains the revolution axis. The central
    # longitudinal section and lower sight target start at the midpoint
    # of the reference arc. The upper target stays on the midpoint of
    # the actual opening-top chord.
    stage_point = layout_context["reference_mid_point"]
    stage_sight_point = point_at(
        stage_point,
        direction,
        0.0,
        params["stage_sight_point_z"],
        mm_scale
    )
    stage_upper_sight_point = point_at(
        opening_stage_point,
        direction,
        0.0,
        opening_height_mm,
        mm_scale
    )

    balcony_tier1_params = normalized_balcony_tier_params(
        calculation_params,
        0
    )
    balcony_tier1_params["balcony_rear_reference_x"] = (
        result["x_values"][-1]
    )
    balcony_tier1_params["balcony_last_platform_z"] = (
        # The compatibility helper accepts a stage-relative absolute Z.
        # Adding the raw stalls rear converts the stored offset before the
        # helper moves it to the effective (possibly interpolated) rear.
        rebase_balcony_last_platform_z(
            balcony_tier1_params["balcony_last_platform_z"]
            + stalls_reference_z,
            stalls_reference_z,
            effective_stalls_rear_z
        )
    )
    balcony_result = calculate_balcony_section(
        balcony_tier1_params,
        result,
        opening_height_mm
    )
    balcony_result = apply_balcony_rise_interpolation(
        balcony_tier1_params,
        balcony_result,
        result,
        opening_height_mm,
        rise_overrides["balcony_1"]
    )
    balcony2_result = None
    balcony2_dependency_warning = False
    balcony_tier2_params = normalized_balcony_tier_params(
        calculation_params,
        1
    )
    balcony_tier2_params["balcony_rear_reference_x"] = (
        result["x_values"][-1]
    )
    balcony_tier2_params["balcony_last_platform_z"] = (
        # Balcony 2 is also stored relative to the stalls rear, not B1.
        rebase_balcony_last_platform_z(
            balcony_tier2_params["balcony_last_platform_z"]
            + stalls_reference_z,
            stalls_reference_z,
            effective_stalls_rear_z
        )
    )
    if balcony_tier2_params["balcony_enabled"]:
        if (
            not balcony_result_is_displayable(balcony_result)
        ):
            balcony2_dependency_warning = True
        else:
            balcony_tier2_params["first_row_distance"] = (
                balcony_result["railing_front_x"]
            )
            balcony2_result = calculate_balcony_section(
                balcony_tier2_params,
                balcony_result,
                opening_height_mm,
                tier_index=1
            )
            balcony2_result = apply_balcony_rise_interpolation(
                balcony_tier2_params,
                balcony2_result,
                balcony_result,
                opening_height_mm,
                rise_overrides["balcony_2"]
            )
    balcony_results = [balcony_result, balcony2_result]
    balcony_tier_params = [
        balcony_tier1_params,
        balcony_tier2_params,
    ]
    ceiling_calculation = calculate_auditorium_ceiling(
        opening_height_mm,
        result,
        balcony_results,
        params["auditorium_ceiling_clear_height"]
    )
    auditorium_ceiling_z = ceiling_calculation["ceiling_z"]
    result = add_stalls_ceiling_validation(
        result,
        auditorium_ceiling_z
    )
    balcony_result = add_balcony_ceiling_validation(
        balcony_result,
        auditorium_ceiling_z
    )
    balcony2_result = add_balcony_ceiling_validation(
        balcony2_result,
        auditorium_ceiling_z
    )
    balcony_results = [balcony_result, balcony2_result]
    boundary_tier_row_regions = None
    tier_row_intervals = None
    if boundary_context is not None:
        boundary_tier_row_regions = [
            build_tier_row_regions(
                boundary_context,
                layout_context,
                result,
                mm_scale,
                params["row_pitch"],
            )
        ]
        for tier_index, tier_result in enumerate(balcony_results):
            boundary_tier_row_regions.append(
                build_tier_row_regions(
                    boundary_context,
                    layout_context,
                    tier_result,
                    mm_scale,
                    balcony_tier_params[tier_index][
                        "balcony_row_pitch"
                    ],
                )
                if balcony_result_is_displayable(tier_result)
                else None
            )
        tier_row_intervals = [
            (
                [row_region["intervals"] for row_region in tier_regions]
                if tier_regions is not None
                else None
            )
            for tier_regions in boundary_tier_row_regions
        ]

    row_overrides_by_tier = normalize_tier_row_overrides(
        params.get("seat_row_overrides"),
        len(balcony_results),
    )
    seat_row_layouts = {
        "stalls": [],
        "balcony_1": [],
        "balcony_2": [],
    }
    seating_layout_specs = [
        ("stalls", result, 0),
        ("balcony_1", balcony_results[0], 1),
        ("balcony_2", balcony_results[1], 2),
    ]
    for tier_key, tier_result, tier_slot in seating_layout_specs:
        if (
            tier_slot > 0
            and not balcony_result_is_displayable(tier_result)
        ):
            continue
        tier_regions = (
            tier_row_intervals[tier_slot]
            if tier_row_intervals is not None
            else None
        )
        seat_row_layouts[tier_key] = calculate_tier_row_layouts(
            params,
            tier_result,
            layout_context,
            tier_regions,
            row_overrides=row_overrides_by_tier.get(tier_key),
        )

    # Empty rows retain platform and sightline calculations, but there is no
    # physical chair there to collide with the auditorium ceiling.
    stalls_active_indices = [
        index
        for index, row_layout in enumerate(seat_row_layouts["stalls"])
        if int(row_layout.get("seat_count", 0)) > 0
    ]
    result = dict(result)
    original_ceiling_violations = list(
        result.get(
            "ceiling_violations",
            [False] * len(result.get("base_z_values", [])),
        )
    )
    active_index_set = set(stalls_active_indices)
    result["ceiling_violations"] = [
        bool(is_violation and index in active_index_set)
        for index, is_violation in enumerate(
            original_ceiling_violations
        )
    ]
    result["ceiling_violation"] = any(
        result["ceiling_violations"]
    )
    if stalls_active_indices:
        clearance_values = result.get("ceiling_clearance_values", [])
        active_clearances = [
            clearance_values[index]
            for index in stalls_active_indices
            if index < len(clearance_values)
        ]
        if active_clearances:
            result["ceiling_clearance"] = min(active_clearances)
        result["highest_chair_z"] = max(
            result["base_z_values"][index] + CHAIR_TOP_Z
            for index in stalls_active_indices
        )
    else:
        result["ceiling_clearance"] = None
        result["highest_chair_z"] = None

    masked_balcony_results = []
    for tier_index, tier_result in enumerate(balcony_results):
        if not balcony_result_is_displayable(tier_result):
            masked_balcony_results.append(tier_result)
            continue
        tier_key = "balcony_{0}".format(tier_index + 1)
        active_indices = [
            index
            for index, row_layout in enumerate(
                seat_row_layouts[tier_key]
            )
            if int(row_layout.get("seat_count", 0)) > 0
        ]
        rebuilt_tier_result = dict(tier_result)
        if active_indices:
            highest_chair_z = max(
                tier_result["base_z_values"][index] + CHAIR_TOP_Z
                for index in active_indices
            )
            ceiling_clearance = auditorium_ceiling_z - highest_chair_z
            rebuilt_tier_result["highest_chair_z"] = highest_chair_z
            rebuilt_tier_result["ceiling_clearance"] = ceiling_clearance
            rebuilt_tier_result["ceiling_violation"] = (
                ceiling_clearance < -1e-8
            )
        else:
            rebuilt_tier_result["ceiling_violation"] = False
        masked_balcony_results.append(rebuilt_tier_result)
    balcony_results = masked_balcony_results
    balcony_result = balcony_results[0]
    balcony2_result = balcony_results[1]

    seat_layout_max_width_by_tier = {}
    default_rectangular_seating_width = None
    if (
        boundary_context is None
        and layout_context.get("mode") != "radial"
    ):
        default_rectangular_seating_width = (
            calculate_seat_layout_width(params)
        )
    for tier_key, tier_layouts in seat_row_layouts.items():
        tier_width = max(
            [
                float(row_layout.get("row_total_width", 0.0))
                for row_layout in tier_layouts
            ]
            or [0.0]
        )
        if (
            tier_layouts
            and tier_width <= 1e-9
            and default_rectangular_seating_width is not None
        ):
            # An all-empty tier keeps its platform footprint even though it
            # contributes no chairs, armrests, or seat count.
            tier_width = default_rectangular_seating_width
        seat_layout_max_width_by_tier[tier_key] = tier_width
    seat_layout_max_width = max(
        list(seat_layout_max_width_by_tier.values()) or [0.0]
    )
    seat_row_fit_issues = tier_row_override_fit_issues(
        seat_row_layouts,
        row_overrides_by_tier,
        len(balcony_results),
    )
    section_dimensions = calculate_stage_section_dimensions(
        params,
        opening_height_mm
    )
    section_dimensions["auditorium_ceiling_z"] = (
        auditorium_ceiling_z
    )
    if tier_row_intervals is None:
        total_seat_count = calculate_total_3d_seat_count(
            params,
            result,
            balcony_results,
            layout_context,
            tier_row_overrides=row_overrides_by_tier,
        )
    else:
        total_seat_count = calculate_total_3d_seat_count(
            params,
            result,
            balcony_results,
            layout_context,
            tier_row_intervals,
            tier_row_overrides=row_overrides_by_tier,
        )
    if (
        params.get("show_3d_seats", False)
        and total_seat_count > MAXIMUM_3D_CHAIR_COUNT
    ):
        raise ValueError(
            "3D chair count exceeds the {0} chair preview limit."
            .format(MAXIMUM_3D_CHAIR_COUNT)
        )

    x_values = result["x_values"]
    eye_x_values = result["eye_x_values"]
    base_z_values = result["base_z_values"]
    eye_z_values = result["eye_z_values"]
    ceiling_violations = result.get(
        "ceiling_violations",
        [False] * len(result["violations"])
    )
    violations = [
        result["violations"][index] or ceiling_violations[index]
        for index in range(len(result["violations"]))
    ]
    slope_values = result["slope_values"]
    aisle_before_values = result["aisle_before_values"]
    aisle_stair_tread_counts = result["aisle_stair_tread_counts"]
    aisle_stair_riser_heights = result[
        "aisle_stair_riser_heights"
    ]
    aisle_stair_run_values = result["aisle_stair_run_values"]

    row_pitch = params["row_pitch"]
    rear_aisle_width = params["aisle_width"]
    aisle_stair_tread_depth = params["aisle_stair_tread_depth"]
    row_count = params["row_count"]
    stepped = params["floor_type"] == "stepped"
    tier_rear_edges = [x_values[-1] + rear_aisle_width]
    tier_rear_edges.extend(
        balcony["x_values"][-1] + rear_aisle_width
        for balcony in balcony_results
        if balcony_result_is_displayable(balcony)
    )
    rear_wall_x = max(tier_rear_edges)

    preview_curves = []
    preview_points = []
    preview_meshes = []
    preview_wire_meshes = []
    preview_labels = []
    bake_curves = []
    bake_points = []
    bake_breps = []
    bake_instances = []
    seat_3d_result = None
    seat_3d_results = []
    floor_surface_result = None
    seat_3d_preview_mode = "off"
    show_radial_row_guides = bool(
        params.get("show_floor_surfaces", False)
        or params.get("show_3d_seats", False)
    )

    if boundary_context is not None:
        boundary_preview_curve = boundary_context["curve"].DuplicateCurve()
        if boundary_preview_curve is not None:
            preview_curves.append(
                (boundary_preview_curve, PREVIEW_REFERENCE, 2)
            )

    if layout_context["mode"] == "radial":
        reference_arc = build_radial_arc(
            layout_context,
            layout_context["radius"],
            0.0,
            mm_scale
        )
        if reference_arc is not None:
            preview_curves.append(
                (reference_arc, PREVIEW_STAGE_APRON, 3)
            )
            bake_curves.append(
                (
                    reference_arc,
                    PREVIEW_STAGE_APRON,
                    "RadialReferenceArc",
                )
            )

        radial_tiers = [("Stalls", result, 0)]
        for tier_index, tier_result in enumerate(balcony_results):
            if balcony_result_is_displayable(tier_result):
                radial_tiers.append(
                    (
                        "Balcony{0:02d}".format(tier_index + 1),
                        tier_result,
                        tier_index + 1,
                    )
                )
        for tier_name, tier_result, tier_slot in radial_tiers:
            for row_index, (row_x, floor_z) in enumerate(
                zip(
                    tier_result["x_values"],
                    tier_result["base_z_values"]
                )
            ):
                row_curves = []
                if boundary_tier_row_regions is not None:
                    target_world_z = (
                        stage_point.Z + floor_z * mm_scale
                    )
                    boundary_world_z = (
                        boundary_context["plane"].Origin.Z
                    )
                    height_translation = rg.Transform.Translation(
                        rg.Vector3d.ZAxis
                        * (target_world_z - boundary_world_z)
                    )
                    for source_segment in boundary_tier_row_regions[
                        tier_slot
                    ][row_index]["segments"]:
                        row_segment = source_segment.DuplicateCurve()
                        if row_segment is None:
                            continue
                        row_segment.Transform(height_translation)
                        row_curves.append(row_segment)
                else:
                    row_arc = build_radial_arc(
                        layout_context,
                        layout_context["radius"] + row_x,
                        floor_z,
                        mm_scale
                    )
                    if row_arc is not None:
                        row_curves.append(row_arc)
                row_color = (
                    PREVIEW_FLOOR
                    if tier_name == "Stalls"
                    else PREVIEW_BALCONY
                )
                for row_curve in row_curves:
                    if show_radial_row_guides:
                        preview_curves.append(
                            (row_curve, row_color, 2)
                        )
                    bake_curves.append(
                        (
                            row_curve,
                            row_color,
                            tier_name + "RadialRow",
                        )
                    )

        if boundary_context is None:
            outer_radius = layout_context["radius"] + rear_wall_x
            for side_angle in (
                -layout_context["half_angle"],
                layout_context["half_angle"],
            ):
                boundary = build_radial_side_line(
                    layout_context,
                    layout_context["radius"],
                    outer_radius,
                    side_angle,
                    0.0,
                    0.0,
                    mm_scale
                )
                preview_curves.append(
                    (boundary, PREVIEW_AUDITORIUM_CEILING, 1)
                )
                bake_curves.append(
                    (
                        boundary,
                        PREVIEW_AUDITORIUM_CEILING,
                        "RadialPlanBoundary",
                    )
                )

    if params.get("show_riser_height_labels", False):
        preview_labels = build_riser_height_preview_labels(
            stage_point,
            direction,
            params,
            result,
            balcony_results,
            mm_scale
        )

    if params.get("show_3d_seats", False):
        if seat_source is None:
            raise ValueError(
                "3D seat modules are enabled, but AuditoriumSeat.3dm "
                "was not loaded."
            )
        seat_curve_block_preview = (
            total_seat_count
            > SEAT_CURVE_PREVIEW_THRESHOLD
        )
        seat_3d_preview_mode = (
            (
                "curve_blocks"
                if seat_curve_block_preview
                else "shaded"
            )
        )
        seating_tiers = [("Stalls", result, 0, "stalls")]
        for tier_index, tier_result in enumerate(
            balcony_results
        ):
            if not balcony_result_is_displayable(tier_result):
                continue
            seating_tiers.append(
                    (
                        "Balcony{0:02d}".format(tier_index + 1),
                        tier_result,
                        tier_index + 1,
                        "balcony_{0}".format(tier_index + 1),
                    )
                )

        for (
            placement_name,
            tier_result,
            tier_slot,
            tier_override_key,
        ) in seating_tiers:
            tier_3d_result = build_3d_seat_module_geometry(
                seat_source,
                params,
                tier_result,
                stage_point,
                direction,
                mm_scale,
                placement_name,
                layout_context,
                seat_curve_block_preview,
                (
                    tier_row_intervals[tier_slot]
                    if tier_row_intervals is not None
                    else None
                ),
                row_overrides_by_tier.get(tier_override_key),
            )
            seat_3d_results.append(tier_3d_result)
            preview_curves.extend(
                tier_3d_result["preview_curves"]
            )
            preview_meshes.extend(
                tier_3d_result["preview_meshes"]
            )
            preview_wire_meshes.extend(
                tier_3d_result["preview_wire_meshes"]
            )
            bake_instances.extend(
                tier_3d_result["bake_instances"]
            )
        seat_3d_result = seat_3d_results[0]

    if params.get("show_riser_height_labels", False):
        dimension_curves, dimension_labels = (
            build_section_height_dimension_preview(
                stage_point,
                direction,
                params,
                result,
                balcony_results,
                section_dimensions["auditorium_ceiling_z"],
                rear_wall_x,
                mm_scale
            )
        )
        preview_curves.extend(dimension_curves)
        preview_labels.extend(dimension_labels)

    opening_frame_curves = build_proscenium_opening_frame_curves(
        opening_stage_point,
        direction,
        params,
        opening_width_mm,
        opening_height_mm,
        mm_scale
    )
    for frame_curve, frame_color, frame_name in opening_frame_curves:
        preview_curves.append((frame_curve, frame_color, 3))
        bake_curves.append((frame_curve, frame_color, frame_name))

    if params["stage_preview_mode"] == "space_3d":
        stage_plan_curves = build_proscenium_plan_curves(
            opening_stage_point,
            direction,
            params,
            mm_scale
        )
        for stage_curve, stage_color, stage_name in stage_plan_curves:
            preview_curves.append((stage_curve, stage_color, 3))
            bake_curves.append((stage_curve, stage_color, stage_name))

        stage_section_curves = build_stage_space_3d_curves(
            opening_stage_point,
            direction,
            params,
            section_dimensions,
            mm_scale
        )
    else:
        stage_section_curves = build_stage_section_2d_curves(
            opening_stage_point,
            direction,
            params,
            section_dimensions,
            mm_scale
        )

    for section_curve, section_color, section_name in stage_section_curves:
        preview_curves.append((section_curve, section_color, 2))
        bake_curves.append(
            (section_curve, section_color, section_name)
        )

    transition_curves = build_stage_audience_transition_curves(
        stage_point,
        direction,
        calculation_params,
        mm_scale
    )
    for transition_curve, transition_color, transition_name in (
        transition_curves
    ):
        preview_curves.append(
            (transition_curve, transition_color, 3)
        )
        bake_curves.append(
            (transition_curve, transition_color, transition_name)
        )

    # Auditorium ceiling line in the central longitudinal section.
    ceiling_start = point_at(
        stage_point,
        direction,
        calculation_params["stage_reference_x"],
        auditorium_ceiling_z,
        mm_scale
    )
    ceiling_end = point_at(
        stage_point,
        direction,
        rear_wall_x,
        auditorium_ceiling_z,
        mm_scale
    )
    ceiling_curve = line_curve(ceiling_start, ceiling_end)
    preview_curves.append(
        (ceiling_curve, PREVIEW_AUDITORIUM_CEILING, 2)
    )
    bake_curves.append(
        (
            ceiling_curve,
            PREVIEW_AUDITORIUM_CEILING,
            "AuditoriumCeilingSection",
        )
    )

    # Lower editable target and upper opening-center target.
    preview_points.append((stage_sight_point, PREVIEW_REFERENCE, 6))
    bake_points.append(
        (stage_sight_point, PREVIEW_REFERENCE, "SightlineReference")
    )
    preview_points.append(
        (stage_upper_sight_point, PREVIEW_FULL_STAGE_SIGHT, 6)
    )
    bake_points.append(
        (
            stage_upper_sight_point,
            PREVIEW_FULL_STAGE_SIGHT,
            "UpperSightlineReference",
        )
    )

    # Embedded chairs, eye points and sightlines
    for index in range(row_count):
        row_color = (
            PREVIEW_WARNING if violations[index] else PREVIEW_SEAT
        )
        eye_point = point_at(
            stage_point,
            direction,
            eye_x_values[index],
            eye_z_values[index],
            mm_scale
        )

        if (
            params["show_seats"]
            and not params.get("show_3d_seats", False)
            and seat_row_layouts["stalls"][index].get(
                "seat_count",
                0,
            ) > 0
        ):
            chair_curves = build_chair_curves(
                stage_point,
                direction,
                x_values[index],
                base_z_values[index],
                mm_scale
            )
            for chair_curve in chair_curves:
                preview_curves.append((chair_curve, row_color, 2))
                bake_curves.append(
                    (chair_curve, row_color, "Chair")
                )

        if params["show_eye_points"]:
            point_color = PREVIEW_WARNING if violations[index] else PREVIEW_POINT
            preview_points.append((eye_point, point_color, 5))
            bake_points.append((eye_point, point_color, "SightPoint"))

        if params["show_sightlines"]:
            is_end_row = index == 0 or index == row_count - 1
            sight_color = (
                PREVIEW_FULL_STAGE_SIGHT
                if is_end_row
                else (
                    PREVIEW_WARNING
                    if violations[index]
                    else PREVIEW_SIGHT
                )
            )
            sightline = line_curve(stage_sight_point, eye_point)
            preview_curves.append(
                (sightline, sight_color, 2 if is_end_row else 1)
            )
            bake_curves.append(
                (
                    sightline,
                    sight_color,
                    (
                        "FullStageSightlineLower"
                        if is_end_row
                        else "Sightline"
                    ),
                )
            )

            if is_end_row:
                upper_sightline = line_curve(
                    stage_upper_sight_point,
                    eye_point
                )
                preview_curves.append(
                    (
                        upper_sightline,
                        PREVIEW_FULL_STAGE_SIGHT,
                        2,
                    )
                )
                bake_curves.append(
                    (
                        upper_sightline,
                        PREVIEW_FULL_STAGE_SIGHT,
                        "FullStageSightlineUpper",
                    )
                )

    if (
        balcony_result_is_displayable(balcony_result)
    ):
        balcony_x_values = balcony_result["x_values"]
        balcony_base_z_values = balcony_result["base_z_values"]
        balcony_eye_x_values = balcony_result["eye_x_values"]
        balcony_eye_z_values = balcony_result["eye_z_values"]
        balcony_row_count = balcony_result["row_count"]
        balcony_sightline_violations = balcony_result.get(
            "sightline_violations",
            [False] * balcony_row_count
        )
        balcony_color = PREVIEW_BALCONY
        balcony_floor_color = PREVIEW_WARNING

        for index in range(balcony_row_count):
            row_warning = balcony_sightline_violations[index]
            chair_color = (
                PREVIEW_WARNING if row_warning else PREVIEW_SEAT
            )
            eye_point = point_at(
                stage_point,
                direction,
                balcony_eye_x_values[index],
                balcony_eye_z_values[index],
                mm_scale
            )

            if (
                params["show_seats"]
                and not params.get("show_3d_seats", False)
                and seat_row_layouts["balcony_1"][index].get(
                    "seat_count",
                    0,
                ) > 0
            ):
                chair_curves = build_chair_curves(
                    stage_point,
                    direction,
                    balcony_x_values[index],
                    balcony_base_z_values[index],
                    mm_scale
                )
                for chair_curve in chair_curves:
                    preview_curves.append(
                        (chair_curve, chair_color, 2)
                    )
                    bake_curves.append(
                        (
                            chair_curve,
                            chair_color,
                            "Balcony01Chair",
                        )
                    )

            if params["show_eye_points"]:
                point_color = (
                    PREVIEW_WARNING if row_warning else balcony_color
                )
                preview_points.append(
                    (eye_point, point_color, 5)
                )
                bake_points.append(
                    (eye_point, point_color, "Balcony01SightPoint")
                )

            if params["show_sightlines"]:
                is_end_row = (
                    index == 0
                    or index == balcony_row_count - 1
                )
                sight_color = (
                    PREVIEW_WARNING
                    if row_warning
                    else (
                        PREVIEW_FULL_STAGE_SIGHT
                        if is_end_row
                        else balcony_color
                    )
                )
                lower_sightline = line_curve(
                    stage_sight_point,
                    eye_point
                )
                preview_curves.append(
                    (
                        lower_sightline,
                        sight_color,
                        2 if is_end_row else 1,
                    )
                )
                bake_curves.append(
                    (
                        lower_sightline,
                        sight_color,
                        (
                            "Balcony01FullStageSightlineLower"
                            if is_end_row
                            else "Balcony01Sightline"
                        ),
                    )
                )

                if is_end_row:
                    upper_sightline = line_curve(
                        stage_upper_sight_point,
                        eye_point
                    )
                    preview_curves.append(
                        (
                            upper_sightline,
                            PREVIEW_FULL_STAGE_SIGHT,
                            2,
                        )
                    )
                    bake_curves.append(
                        (
                            upper_sightline,
                            PREVIEW_FULL_STAGE_SIGHT,
                            "Balcony01FullStageSightlineUpper",
                        )
                    )

        railing_front_floor = point_at(
            stage_point,
            direction,
            balcony_result["railing_front_x"],
            balcony_result["railing_floor_z"],
            mm_scale
        )
        railing_front_top = point_at(
            stage_point,
            direction,
            balcony_result["railing_front_x"],
            balcony_result["railing_top_z"],
            mm_scale
        )
        railing_rear_top = point_at(
            stage_point,
            direction,
            balcony_result["railing_rear_x"],
            balcony_result["railing_top_z"],
            mm_scale
        )
        railing_color = (
            PREVIEW_WARNING
            if balcony_result["railing_sight_collision"]
            else PREVIEW_BALCONY_RAIL
        )
        for railing_curve, railing_name in (
            (
                line_curve(railing_front_floor, railing_front_top),
                "Balcony01RailingFront",
            ),
            (
                line_curve(railing_front_top, railing_rear_top),
                "Balcony01RailingTop",
            ),
        ):
            preview_curves.append(
                (railing_curve, railing_color, 4)
            )
            bake_curves.append(
                (railing_curve, railing_color, railing_name)
            )

        first_platform_end = point_at(
            stage_point,
            direction,
            balcony_x_values[0],
            balcony_base_z_values[0],
            mm_scale
        )
        first_platform = line_curve(
            railing_front_floor,
            first_platform_end
        )
        preview_curves.append(
            (first_platform, balcony_floor_color, 4)
        )
        bake_curves.append(
            (
                first_platform,
                balcony_floor_color,
                "Balcony01Floor",
            )
        )

        for index in range(1, balcony_row_count):
            riser_x = balcony_x_values[index - 1]
            riser_start = point_at(
                stage_point,
                direction,
                riser_x,
                balcony_base_z_values[index - 1],
                mm_scale
            )
            riser_end = point_at(
                stage_point,
                direction,
                riser_x,
                balcony_base_z_values[index],
                mm_scale
            )
            platform_end = point_at(
                stage_point,
                direction,
                balcony_x_values[index],
                balcony_base_z_values[index],
                mm_scale
            )
            riser_curve = line_curve(riser_start, riser_end)
            platform_curve = line_curve(riser_end, platform_end)
            preview_curves.append(
                (riser_curve, balcony_floor_color, 4)
            )
            preview_curves.append(
                (platform_curve, balcony_floor_color, 4)
            )
            bake_curves.append(
                (
                    riser_curve,
                    balcony_floor_color,
                    "Balcony01Floor",
                )
            )
            bake_curves.append(
                (
                    platform_curve,
                    balcony_floor_color,
                    "Balcony01Floor",
                )
            )

        rear_aisle_width = params["aisle_width"]
        if rear_aisle_width > 1e-8:
            rear_aisle_start = point_at(
                stage_point,
                direction,
                balcony_x_values[-1],
                balcony_base_z_values[-1],
                mm_scale
            )
            rear_aisle_end = point_at(
                stage_point,
                direction,
                balcony_x_values[-1] + rear_aisle_width,
                balcony_base_z_values[-1],
                mm_scale
            )
            rear_aisle_curve = line_curve(
                rear_aisle_start,
                rear_aisle_end
            )
            preview_curves.append(
                (rear_aisle_curve, PREVIEW_AISLE, 4)
            )
            bake_curves.append(
                (
                    rear_aisle_curve,
                    PREVIEW_AISLE,
                    "Balcony01RearAisle",
                )
            )

    if balcony2_result is not None:
        balcony2_preview_params = dict(balcony_tier2_params)
        balcony2_preview_params["seat_row_layouts"] = (
            seat_row_layouts["balcony_2"]
        )
        append_balcony_tier_geometry(
            balcony2_result,
            stage_point,
            direction,
            mm_scale,
            balcony2_preview_params,
            stage_sight_point,
            stage_upper_sight_point,
            preview_curves,
            preview_points,
            bake_curves,
            bake_points
        )

    # Keep each configured rear aisle at its requested width, then bridge
    # any remaining distance to the shared auditorium rear wall.  Balcony
    # longitudinal offsets can otherwise leave the forward tier floating
    # short of that wall.
    for tier_index, tier_result in enumerate(balcony_results):
        if not balcony_result_is_displayable(tier_result):
            continue
        rear_floor_start_x = (
            tier_result["x_values"][-1] + rear_aisle_width
        )
        if rear_wall_x - rear_floor_start_x <= 1e-8:
            continue
        rear_floor_z = tier_result["base_z_values"][-1]
        rear_floor_start = point_at(
            stage_point,
            direction,
            rear_floor_start_x,
            rear_floor_z,
            mm_scale
        )
        rear_floor_end = point_at(
            stage_point,
            direction,
            rear_wall_x,
            rear_floor_z,
            mm_scale
        )
        rear_floor_curve = line_curve(
            rear_floor_start,
            rear_floor_end
        )
        rear_floor_name = (
            "Balcony{0:02d}RearFloorClosure".format(
                tier_index + 1
            )
        )
        preview_curves.append(
            (rear_floor_curve, PREVIEW_FLOOR, 3)
        )
        bake_curves.append(
            (rear_floor_curve, PREVIEW_FLOOR, rear_floor_name)
        )

    # Floor geometry
    if stepped:
        for index in range(row_count):
            # Each chair's rear-bottom origin sits on the rear edge of its
            # platform. The preceding row pitch extends toward the stage.
            start_x = x_values[index] - row_pitch
            end_x = x_values[index]

            p0 = point_at(
                stage_point, direction, start_x, base_z_values[index], mm_scale
            )
            p1 = point_at(
                stage_point, direction, end_x, base_z_values[index], mm_scale
            )

            platform_color = (
                PREVIEW_WARNING if violations[index] else PREVIEW_FLOOR
            )
            platform = line_curve(p0, p1)
            preview_curves.append((platform, platform_color, 3))
            bake_curves.append((platform, platform_color, "Floor"))

            if index < row_count - 1:
                next_index = index + 1
                riser_x = end_x
                riser_start = p1

                if aisle_before_values[next_index]:
                    stair_run = aisle_stair_run_values[next_index]
                    aisle_end_x = (
                        x_values[next_index] - row_pitch - stair_run
                    )
                    if aisle_end_x - end_x > 1e-8:
                        aisle_end = point_at(
                            stage_point,
                            direction,
                            aisle_end_x,
                            base_z_values[index],
                            mm_scale
                        )
                        aisle_curve = line_curve(p1, aisle_end)
                        preview_curves.append(
                            (aisle_curve, PREVIEW_AISLE, 4)
                        )
                        bake_curves.append(
                            (aisle_curve, PREVIEW_AISLE, "CrossAisle")
                        )
                        riser_start = aisle_end
                    else:
                        aisle_end = p1

                    stair_tread_count = (
                        aisle_stair_tread_counts[next_index]
                    )
                    stair_riser_height = (
                        aisle_stair_riser_heights[next_index]
                    )
                    stair_color = (
                        PREVIEW_WARNING
                        if violations[next_index]
                        else PREVIEW_AISLE
                    )
                    stair_x = aisle_end_x
                    stair_z = base_z_values[index]

                    if (
                        base_z_values[next_index] - stair_z
                        > 1e-8
                    ):
                        for stair_index in range(
                            stair_tread_count + 1
                        ):
                            next_stair_z = (
                                base_z_values[next_index]
                                if stair_index == stair_tread_count
                                else (
                                    base_z_values[index]
                                    + stair_riser_height
                                    * (stair_index + 1)
                                )
                            )
                            stair_riser_start = point_at(
                                stage_point,
                                direction,
                                stair_x,
                                stair_z,
                                mm_scale
                            )
                            stair_riser_end = point_at(
                                stage_point,
                                direction,
                                stair_x,
                                next_stair_z,
                                mm_scale
                            )
                            stair_riser = line_curve(
                                stair_riser_start,
                                stair_riser_end
                            )
                            preview_curves.append(
                                (stair_riser, stair_color, 4)
                            )
                            bake_curves.append(
                                (
                                    stair_riser,
                                    stair_color,
                                    "CrossAisleStairRiser",
                                )
                            )
                            stair_z = next_stair_z

                            if stair_index < stair_tread_count:
                                next_stair_x = (
                                    stair_x
                                    + aisle_stair_tread_depth
                                )
                                stair_tread_start = point_at(
                                    stage_point,
                                    direction,
                                    stair_x,
                                    stair_z,
                                    mm_scale
                                )
                                stair_tread_end = point_at(
                                    stage_point,
                                    direction,
                                    next_stair_x,
                                    stair_z,
                                    mm_scale
                                )
                                stair_tread = line_curve(
                                    stair_tread_start,
                                    stair_tread_end
                                )
                                preview_curves.append(
                                    (stair_tread, stair_color, 4)
                                )
                                bake_curves.append(
                                    (
                                        stair_tread,
                                        stair_color,
                                        "CrossAisleStairTread",
                                    )
                                )
                                stair_x = next_stair_x
                    elif stair_run > 1e-8:
                        # A zero-rise interpolation keeps the original stair
                        # run as one continuous horizontal aisle segment.
                        flat_run_end = point_at(
                            stage_point,
                            direction,
                            aisle_end_x + stair_run,
                            stair_z,
                            mm_scale
                        )
                        flat_run = line_curve(aisle_end, flat_run_end)
                        preview_curves.append(
                            (flat_run, stair_color, 4)
                        )
                        bake_curves.append(
                            (
                                flat_run,
                                stair_color,
                                "CrossAisleStairFlatRun",
                            )
                        )
                    continue

                if (
                    base_z_values[next_index]
                    - base_z_values[index]
                    > 1e-8
                ):
                    p2 = point_at(
                        stage_point,
                        direction,
                        riser_x,
                        base_z_values[next_index],
                        mm_scale
                    )
                    riser_color = (
                        PREVIEW_WARNING
                        if violations[next_index]
                        else PREVIEW_FLOOR
                    )
                    riser = line_curve(riser_start, p2)
                    preview_curves.append((riser, riser_color, 3))
                    bake_curves.append((riser, riser_color, "Floor"))
    else:
        # Extend the first slope toward the stage by one complete row pitch.
        if row_count == 1:
            first_slope = 0.0
        else:
            first_slope = slope_values[1]

        front_x = x_values[0] - row_pitch
        front_z = base_z_values[0] - row_pitch * first_slope
        p0 = point_at(stage_point, direction, front_x, front_z, mm_scale)
        p1 = point_at(
            stage_point,
            direction,
            x_values[0],
            base_z_values[0],
            mm_scale
        )
        front_color = (
            PREVIEW_WARNING
            if row_count > 1 and violations[1]
            else PREVIEW_FLOOR
        )
        front_extension = line_curve(p0, p1)
        preview_curves.append((front_extension, front_color, 3))
        bake_curves.append((front_extension, front_color, "Floor"))

        for index in range(1, row_count):
            p0 = point_at(
                stage_point,
                direction,
                x_values[index - 1],
                base_z_values[index - 1],
                mm_scale
            )
            if aisle_before_values[index]:
                aisle_end_x = x_values[index] - row_pitch
                if aisle_end_x - x_values[index - 1] > 1e-8:
                    aisle_end = point_at(
                        stage_point,
                        direction,
                        aisle_end_x,
                        base_z_values[index - 1],
                        mm_scale
                    )
                    aisle_curve = line_curve(p0, aisle_end)
                    preview_curves.append(
                        (aisle_curve, PREVIEW_AISLE, 4)
                    )
                    bake_curves.append(
                        (aisle_curve, PREVIEW_AISLE, "CrossAisle")
                    )
                    p0 = aisle_end

            p1 = point_at(
                stage_point,
                direction,
                x_values[index],
                base_z_values[index],
                mm_scale
            )
            segment_color = (
                PREVIEW_WARNING if violations[index] else PREVIEW_FLOOR
            )
            segment = line_curve(p0, p1)
            preview_curves.append((segment, segment_color, 3))
            bake_curves.append((segment, segment_color, "Floor"))

    # Preserve one more full cross-aisle behind the last row, then close the
    # rear of the auditorium section visually up to the ceiling.
    rear_aisle_start = point_at(
        stage_point,
        direction,
        x_values[-1],
        base_z_values[-1],
        mm_scale
    )
    rear_aisle_end = point_at(
        stage_point,
        direction,
        x_values[-1] + rear_aisle_width,
        base_z_values[-1],
        mm_scale
    )
    if rear_aisle_width > 1e-8:
        rear_aisle_curve = line_curve(
            rear_aisle_start,
            rear_aisle_end
        )
        preview_curves.append(
            (rear_aisle_curve, PREVIEW_AISLE, 4)
        )
        bake_curves.append(
            (rear_aisle_curve, PREVIEW_AISLE, "RearCrossAisle")
        )

    rear_wall_floor_point = point_at(
        stage_point,
        direction,
        rear_wall_x,
        base_z_values[-1],
        mm_scale
    )
    stalls_rear_aisle_x = x_values[-1] + rear_aisle_width
    if rear_wall_x - stalls_rear_aisle_x > 1e-8:
        rear_floor_closure = line_curve(
            rear_aisle_end,
            rear_wall_floor_point
        )
        preview_curves.append(
            (rear_floor_closure, PREVIEW_FLOOR, 3)
        )
        bake_curves.append(
            (
                rear_floor_closure,
                PREVIEW_FLOOR,
                "AuditoriumRearFloorClosure",
            )
        )

    rear_ceiling_point = point_at(
        stage_point,
        direction,
        rear_wall_x,
        auditorium_ceiling_z,
        mm_scale
    )
    rear_wall_curve = line_curve(
        rear_wall_floor_point,
        rear_ceiling_point
    )
    preview_curves.append(
        (rear_wall_curve, PREVIEW_AUDITORIUM_CEILING, 3)
    )
    bake_curves.append(
        (
            rear_wall_curve,
            PREVIEW_AUDITORIUM_CEILING,
            "AuditoriumRearWallSection",
        )
    )

    violation_rows = [
        index + 1
        for index, is_violation in enumerate(violations)
        if is_violation
    ]
    slope_violation_rows = [
        index + 1
        for index, is_violation in enumerate(
            result["slope_violations"]
        )
        if is_violation
    ]
    sightline_violation_rows = [
        index + 1
        for index, is_violation in enumerate(
            result["sightline_violations"]
        )
        if is_violation
    ]
    ceiling_violation_rows = [
        index + 1
        for index, is_violation in enumerate(ceiling_violations)
        if is_violation
    ]

    maximum_actual_slope = max(result["slope_values"])
    total_depth = (
        rear_wall_x - (x_values[0] - row_pitch)
        if row_count > 0
        else 0.0
    )
    total_rise = (
        base_z_values[-1] - base_z_values[0]
        if row_count > 0
        else 0.0
    )

    if params.get("show_floor_surfaces", False):
        floor_surface_params = dict(params)
        floor_surface_params["seat_layout_max_width"] = (
            seat_layout_max_width
        )
        floor_surface_params["seat_layout_max_width_by_tier"] = dict(
            seat_layout_max_width_by_tier
        )
        floor_builder_args = (
            stage_point,
            direction,
            floor_surface_params,
            section_dimensions,
            opening_width_mm,
            opening_height_mm,
            rear_wall_x,
            base_z_values[-1],
            mm_scale,
            doc.ModelAbsoluteTolerance,
            bake_curves,
            layout_context,
            opening_stage_point,
        )
        if boundary_context is None:
            floor_surface_result = build_floor_surface_geometry(
                *floor_builder_args
            )
        else:
            floor_surface_result = build_floor_surface_geometry(
                *(floor_builder_args + (boundary_context,))
            )
        preview_meshes[0:0] = floor_surface_result[
            "preview_meshes"
        ]
        bake_breps.extend(floor_surface_result["bake_breps"])

    return {
        "preview_curves": preview_curves,
        "preview_points": preview_points,
        "preview_meshes": preview_meshes,
        "preview_wire_meshes": preview_wire_meshes,
        "preview_labels": preview_labels,
        "bake_curves": bake_curves,
        "bake_points": bake_points,
        "bake_breps": bake_breps,
        "bake_instances": bake_instances,
        "seat_source": seat_source,
        "seat_3d_calculation": seat_3d_result,
        "seat_3d_calculations": seat_3d_results,
        "seat_row_layouts": seat_row_layouts,
        "seat_row_override_fit_issues": seat_row_fit_issues,
        "seat_layout_max_width": seat_layout_max_width,
        "seat_layout_max_width_by_tier": (
            seat_layout_max_width_by_tier
        ),
        "floor_surface_calculation": floor_surface_result,
        "calculation": result,
        "balcony_calculation": balcony_result,
        "balcony_calculations": balcony_results,
        "balcony2_dependency_warning": balcony2_dependency_warning,
        "violation_rows": violation_rows,
        "slope_violation_rows": slope_violation_rows,
        "sightline_violation_rows": sightline_violation_rows,
        "ceiling_violation_rows": ceiling_violation_rows,
        "maximum_actual_slope": maximum_actual_slope,
        "total_depth": total_depth,
        "total_rise": total_rise,
        "direction": direction,
        "vertical_placement": vertical_placement,
        "audience_datum_point": rg.Point3d(audience_datum_point),
        "opening_stage_point": rg.Point3d(opening_stage_point),
        "plan_layout": layout_context,
        "auditorium_boundary": boundary_context,
        "boundary_tier_row_regions": boundary_tier_row_regions,
        "rear_wall_x": rear_wall_x,
        "auditorium_ceiling": ceiling_calculation,
        "total_seat_count": total_seat_count,
        "seat_3d_preview_mode": seat_3d_preview_mode,
        "stage_section_dimensions": section_dimensions,
        "applied_section_rise_overrides": {
            "stalls": result.get("rise_interpolation_target"),
            "balcony_1": (
                balcony_result.get("rise_interpolation_target")
                if balcony_result is not None
                else None
            ),
            "balcony_2": (
                balcony2_result.get("rise_interpolation_target")
                if balcony2_result is not None
                else None
            ),
        },
    }
