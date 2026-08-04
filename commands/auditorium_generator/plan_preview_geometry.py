# -*- coding: utf-8 -*-
"""Flattened, tier-separated auditorium plan preview geometry."""

import Rhino.Geometry as rg
from System.Drawing import Color

from .boundary_row_layout import (
    curve_segments_inside_boundary,
    radial_segment_lateral_intervals,
    radial_row_segments,
    rectangular_row_segments,
    segment_lateral_intervals,
)
from .calculations.seating import (
    MAXIMUM_3D_CHAIR_COUNT,
    calculate_3d_seat_placements,
    calculate_seat_layout_width,
    calculate_tier_row_layouts,
    normalize_tier_row_overrides,
    resolve_row_seat_block_counts,
)
from .calculations.sections import balcony_result_is_displayable
from .preview_palette import (
    PREVIEW_3D_ARMREST,
    PREVIEW_3D_CHAIR,
    PREVIEW_AISLE,
    PREVIEW_BALCONY,
    PREVIEW_BALCONY_RAIL,
    PREVIEW_BALCONY_SECOND,
    PREVIEW_FLOOR,
    PREVIEW_ORCHESTRA_PIT,
    PREVIEW_PLAN_ROW_GUIDE,
    PREVIEW_REFERENCE,
    PREVIEW_SECTION_DIMENSION,
    PREVIEW_STAGE_APRON,
    PREVIEW_WARNING,
)
from .radial_layout import (
    build_radial_arc,
    build_radial_side_line,
    radial_frame,
    radial_point,
)
from .rhino_primitives import get_stage_directions, unit_scale_from_mm
from .seat_preview_geometry import (
    SEAT_SOURCE_ARMREST_WIDTH,
    SEAT_SOURCE_CHAIR_WIDTH,
    seat_module_transform,
)


PLAN_TIER_OFFSET_FACTORS = (1.2, 2.4, 3.6)
PLAN_LABEL_CLEARANCE_MM = 500.0
PLAN_ROW_LABEL_CLEARANCE_MM = 250.0
PLAN_CLEARANCE_TICK_HALF_MM = 75.0
PLAN_CURVE_TOLERANCE = 1e-8


def _duplicate_curve(curve):
    if curve is None:
        return None
    try:
        return curve.DuplicateCurve()
    except Exception:
        duplicate = curve.Duplicate()
        return duplicate if isinstance(duplicate, rg.Curve) else None


def _project_curve(curve, projection):
    duplicate = _duplicate_curve(curve)
    if duplicate is None:
        return None
    if not duplicate.Transform(projection):
        return None
    return duplicate


def _transform_curve(curve, transform):
    duplicate = _duplicate_curve(curve)
    if duplicate is None:
        return None
    if not duplicate.Transform(transform):
        return None
    return duplicate


def _curve_domain_midpoint(curve):
    domain = curve.Domain
    return curve.PointAt((float(domain.T0) + float(domain.T1)) * 0.5)


def _curve_closest_parameter(curve, point):
    try:
        result = curve.ClosestPoint(point)
    except Exception:
        return None
    if isinstance(result, tuple):
        if len(result) < 2 or not result[0]:
            return None
        return float(result[1])
    return None


def _tier_longitudinal_coordinate_mm(
    point,
    layout_context,
    mm_scale,
):
    if layout_context["mode"] == "radial":
        center = layout_context["center_point"]
        offset = rg.Vector3d(point - center)
        offset.Z = 0.0
        return (
            float(offset.Length) / mm_scale
            - float(layout_context["radius"])
        )
    offset = rg.Vector3d(
        point - layout_context["reference_mid_point"]
    )
    return (
        rg.Vector3d.Multiply(
            offset,
            layout_context["audience_direction"],
        )
        / mm_scale
    )


def _tier_boundary_parts(
    boundary_context,
    layout_context,
    front_x,
    rear_x,
    half_width_mm,
    mm_scale,
):
    """Return exact boundary-side pieces between a tier's front and rear."""
    boundary_curve = boundary_context.get("curve")
    if boundary_curve is None:
        return []
    source = _duplicate_curve(boundary_curve)
    if source is None:
        return []

    parameters = []
    for row_x in (front_x, rear_x):
        row_segments = _row_curves(
            layout_context,
            boundary_context,
            row_x,
            half_width_mm,
            mm_scale,
        )
        for segment in row_segments:
            for point in (segment.PointAtStart, segment.PointAtEnd):
                parameter = _curve_closest_parameter(source, point)
                if parameter is None:
                    continue
                if not any(
                    abs(parameter - value) <= 1e-9
                    for value in parameters
                ):
                    parameters.append(parameter)

    pieces = None
    if parameters:
        try:
            pieces = source.Split(sorted(parameters))
        except Exception:
            pieces = None
    candidates = list(pieces) if pieces else [source]
    tolerance_mm = (
        max(float(boundary_context.get("tolerance", 1e-6)), 1e-6)
        / mm_scale
    )
    kept = []
    for piece in candidates:
        if piece is None:
            continue
        try:
            midpoint = _curve_domain_midpoint(piece)
            coordinate = _tier_longitudinal_coordinate_mm(
                midpoint,
                layout_context,
                mm_scale,
            )
        except Exception:
            continue
        if (
            coordinate >= float(front_x) - tolerance_mm
            and coordinate <= float(rear_x) + tolerance_mm
        ):
            kept.append(piece)
    return kept


def _layout_point(
    layout_context,
    row_x_mm,
    lateral_mm,
    mm_scale,
):
    if layout_context["mode"] == "radial":
        radius_mm = float(layout_context["radius"]) + float(row_x_mm)
        if radius_mm <= PLAN_CURVE_TOLERANCE:
            raise ValueError("Plan row radius must be greater than zero.")
        angle = float(lateral_mm) / radius_mm
        return radial_point(
            layout_context,
            radius_mm,
            angle,
            0.0,
            mm_scale,
        )
    return (
        layout_context["reference_mid_point"]
        + layout_context["audience_direction"]
        * (float(row_x_mm) * mm_scale)
        + layout_context["audience_view_right_direction"]
        * (float(lateral_mm) * mm_scale)
    )


def _row_curves(
    layout_context,
    boundary_context,
    row_x_mm,
    half_width_mm,
    mm_scale,
):
    if boundary_context is not None:
        if layout_context["mode"] == "radial":
            return radial_row_segments(
                boundary_context,
                layout_context,
                row_x_mm,
                mm_scale,
            )
        return rectangular_row_segments(
            boundary_context,
            layout_context["reference_mid_point"],
            layout_context["audience_direction"],
            row_x_mm,
            mm_scale,
        )

    if layout_context["mode"] == "radial":
        curve = build_radial_arc(
            layout_context,
            float(layout_context["radius"]) + float(row_x_mm),
            0.0,
            mm_scale,
        )
        return [curve] if curve is not None else []

    center = _layout_point(
        layout_context,
        row_x_mm,
        0.0,
        mm_scale,
    )
    right = layout_context["audience_view_right_direction"]
    half_width_model = float(half_width_mm) * mm_scale
    return [
        rg.LineCurve(
            center - right * half_width_model,
            center + right * half_width_model,
        )
    ]


def _tier_row_reference_curves(
    layout_context,
    boundary_context,
    tier_regions,
    row_index,
    row_x_mm,
    half_width_mm,
    mm_scale,
):
    """Return the wall-to-wall datum curve pieces for one seating row."""
    if tier_regions is not None and row_index < len(tier_regions):
        region = tier_regions[row_index]
        if hasattr(region, "get") and "segments" in region:
            segments = region.get("segments")
            if segments is not None:
                return [segment for segment in segments if segment is not None]
    return _row_curves(
        layout_context,
        boundary_context,
        row_x_mm,
        half_width_mm,
        mm_scale,
    )


def _append_row_reference_guides(
    target,
    tier_result,
    layout_context,
    boundary_context,
    tier_regions,
    half_width_mm,
    projection,
    mm_scale,
    highlighted_row_index=None,
):
    """Draw every platform rear/riser datum and return its source curves."""
    source_rows = []
    for row_index, row_x in enumerate(tier_result["x_values"]):
        row_curves = _tier_row_reference_curves(
            layout_context,
            boundary_context,
            tier_regions,
            row_index,
            row_x,
            half_width_mm,
            mm_scale,
        )
        source_rows.append(row_curves)
        _append_projected_curves(
            target,
            row_curves,
            projection,
            (
                PREVIEW_WARNING
                if row_index == highlighted_row_index
                else PREVIEW_PLAN_ROW_GUIDE
            ),
            1,
        )
    return source_rows


def _row_wall_intervals(
    row_curves,
    layout_context,
    boundary_context,
    row_x_mm,
    floor_half_width_mm,
    mm_scale,
):
    """Return actual wall intervals at the row datum in lateral millimeters."""
    if boundary_context is not None:
        if layout_context["mode"] == "radial":
            return radial_segment_lateral_intervals(
                row_curves,
                layout_context,
                row_x_mm,
                mm_scale,
            )
        return segment_lateral_intervals(
            row_curves,
            _layout_point(layout_context, row_x_mm, 0.0, mm_scale),
            layout_context["audience_view_right_direction"],
            mm_scale,
        )

    if layout_context["mode"] == "radial":
        row_radius = float(layout_context["radius"]) + float(row_x_mm)
        lateral_extent = row_radius * float(layout_context["half_angle"])
        return [(-lateral_extent, lateral_extent)]
    return [(-float(floor_half_width_mm), float(floor_half_width_mm))]


def _row_interval_curve(
    layout_context,
    row_x_mm,
    start_lateral_mm,
    end_lateral_mm,
    mm_scale,
):
    """Build a straight or radial curve over a signed lateral interval."""
    if abs(float(end_lateral_mm) - float(start_lateral_mm)) <= (
        PLAN_CURVE_TOLERANCE
    ):
        return None
    if layout_context["mode"] != "radial":
        return rg.LineCurve(
            _layout_point(
                layout_context,
                row_x_mm,
                start_lateral_mm,
                mm_scale,
            ),
            _layout_point(
                layout_context,
                row_x_mm,
                end_lateral_mm,
                mm_scale,
            ),
        )

    radius_mm = float(layout_context["radius"]) + float(row_x_mm)
    if radius_mm <= PLAN_CURVE_TOLERANCE:
        return None
    start_angle = float(start_lateral_mm) / radius_mm
    end_angle = float(end_lateral_mm) / radius_mm
    middle_angle = (start_angle + end_angle) * 0.5
    try:
        arc = rg.Arc(
            radial_point(
                layout_context,
                radius_mm,
                start_angle,
                0.0,
                mm_scale,
            ),
            radial_point(
                layout_context,
                radius_mm,
                middle_angle,
                0.0,
                mm_scale,
            ),
            radial_point(
                layout_context,
                radius_mm,
                end_angle,
                0.0,
                mm_scale,
            ),
        )
    except Exception:
        return None
    return arc.ToNurbsCurve() if arc.IsValid else None


def _row_dimension_tick(
    layout_context,
    row_x_mm,
    lateral_mm,
    mm_scale,
):
    """Build a short tick normal to one row datum."""
    if layout_context["mode"] == "radial":
        radius_mm = float(layout_context["radius"]) + float(row_x_mm)
        angle = float(lateral_mm) / radius_mm
        origin, unused_tangent, normal = radial_frame(
            layout_context,
            radius_mm,
            angle,
            0.0,
            mm_scale,
        )
    else:
        origin = _layout_point(
            layout_context,
            row_x_mm,
            lateral_mm,
            mm_scale,
        )
        normal = rg.Vector3d(layout_context["audience_direction"])
    if not normal.Unitize():
        return None
    half_length = PLAN_CLEARANCE_TICK_HALF_MM * mm_scale
    return rg.LineCurve(
        origin - normal * half_length,
        origin + normal * half_length,
    )


def _append_projected_curves(
    target,
    curves,
    projection,
    color,
    thickness,
):
    for curve in curves:
        projected = _project_curve(curve, projection)
        if projected is not None:
            target.append((projected, color, thickness))


def _append_opening_reference(
    target,
    preview_data,
    params,
    projection,
    stage_right_direction,
    mm_scale,
):
    opening_point = rg.Point3d(preview_data["opening_stage_point"])
    half_width = float(params["opening_width"]) * mm_scale * 0.5
    opening_curve = rg.LineCurve(
        opening_point - stage_right_direction * half_width,
        opening_point + stage_right_direction * half_width,
    )
    _append_projected_curves(
        target,
        [opening_curve],
        projection,
        PREVIEW_REFERENCE,
        4,
    )


def _rectangular_floor_outline(
    layout_context,
    front_x,
    rear_x,
    half_width_mm,
    mm_scale,
):
    points = [
        _layout_point(
            layout_context,
            front_x,
            -half_width_mm,
            mm_scale,
        ),
        _layout_point(
            layout_context,
            rear_x,
            -half_width_mm,
            mm_scale,
        ),
        _layout_point(
            layout_context,
            rear_x,
            half_width_mm,
            mm_scale,
        ),
        _layout_point(
            layout_context,
            front_x,
            half_width_mm,
            mm_scale,
        ),
    ]
    points.append(points[0])
    return [rg.PolylineCurve(points)]


def _radial_floor_outline(
    layout_context,
    front_x,
    rear_x,
    mm_scale,
):
    front_radius = float(layout_context["radius"]) + float(front_x)
    rear_radius = float(layout_context["radius"]) + float(rear_x)
    curves = []
    front_arc = build_radial_arc(
        layout_context,
        front_radius,
        0.0,
        mm_scale,
    )
    rear_arc = build_radial_arc(
        layout_context,
        rear_radius,
        0.0,
        mm_scale,
    )
    if front_arc is not None:
        curves.append(front_arc)
    if rear_arc is not None:
        curves.append(rear_arc)
    for angle in (
        -float(layout_context["half_angle"]),
        float(layout_context["half_angle"]),
    ):
        curves.append(
            build_radial_side_line(
                layout_context,
                front_radius,
                rear_radius,
                angle,
                0.0,
                0.0,
                mm_scale,
            )
        )
    return curves


def _append_floor_outline(
    target,
    preview_data,
    layout_context,
    boundary_context,
    front_x,
    rear_x,
    half_width_mm,
    projection,
    floor_color,
    mm_scale,
):
    if rear_x <= front_x + PLAN_CURVE_TOLERANCE:
        return
    if boundary_context is not None:
        boundary_parts = _tier_boundary_parts(
            boundary_context,
            layout_context,
            front_x,
            rear_x,
            half_width_mm,
            mm_scale,
        )
        _append_projected_curves(
            target,
            boundary_parts,
            projection,
            floor_color,
            3,
        )
        for row_x in (front_x, rear_x):
            _append_projected_curves(
                target,
                _row_curves(
                    layout_context,
                    boundary_context,
                    row_x,
                    half_width_mm,
                    mm_scale,
                ),
                projection,
                floor_color,
                3,
            )
        return

    outline_curves = (
        _radial_floor_outline(
            layout_context,
            front_x,
            rear_x,
            mm_scale,
        )
        if layout_context["mode"] == "radial"
        else _rectangular_floor_outline(
            layout_context,
            front_x,
            rear_x,
            half_width_mm,
            mm_scale,
        )
    )
    _append_projected_curves(
        target,
        outline_curves,
        projection,
        floor_color,
        3,
    )


def _append_stalls_transition(
    target,
    preview_data,
    params,
    layout_context,
    boundary_context,
    floor_half_width_mm,
    projection,
    stage_right_direction,
    mm_scale,
):
    opening_point = rg.Point3d(preview_data["opening_stage_point"])
    opening_half_width_mm = float(params["opening_width"]) * 0.5
    first_platform_x = float(params["first_row_distance"])

    if layout_context["mode"] == "rectangular" and boundary_context is None:
        right = stage_right_direction
        opening_half_model = opening_half_width_mm * mm_scale
        floor_half_model = floor_half_width_mm * mm_scale
        platform_center = _layout_point(
            layout_context,
            first_platform_x,
            0.0,
            mm_scale,
        )
        curves = [
            rg.LineCurve(
                opening_point - right * opening_half_model,
                platform_center - right * opening_half_model,
            ),
            rg.LineCurve(
                opening_point + right * opening_half_model,
                platform_center + right * opening_half_model,
            ),
        ]
        if (
            abs(floor_half_width_mm - opening_half_width_mm)
            > 1e-8
        ):
            curves.extend(
                [
                    rg.LineCurve(
                        platform_center - right * opening_half_model,
                        platform_center - right * floor_half_model,
                    ),
                    rg.LineCurve(
                        platform_center + right * opening_half_model,
                        platform_center + right * floor_half_model,
                    ),
                ]
            )
        _append_projected_curves(
            target,
            curves,
            projection,
            PREVIEW_FLOOR,
            3,
        )
    elif layout_context["mode"] == "radial" and boundary_context is None:
        transition_outline = _row_curves(
            layout_context,
            None,
            0.0,
            0.0,
            mm_scale,
        )
        for angle in (
            -float(layout_context["half_angle"]),
            float(layout_context["half_angle"]),
        ):
            transition_outline.append(
                build_radial_side_line(
                    layout_context,
                    float(layout_context["radius"]),
                    float(layout_context["radius"]) + first_platform_x,
                    angle,
                    0.0,
                    0.0,
                    mm_scale,
                )
            )
        _append_projected_curves(
            target,
            transition_outline,
            projection,
            PREVIEW_FLOOR,
            3,
        )

    apron_x = max(float(params.get("stage_apron_projection", 0.0)), 0.0)
    transition_rows = []
    if apron_x > 1e-8:
        transition_rows.append((apron_x, PREVIEW_STAGE_APRON))
    if first_platform_x > apron_x + 1e-8:
        transition_rows.append(
            (
                first_platform_x,
                (
                    PREVIEW_ORCHESTRA_PIT
                    if float(params.get("orchestra_pit_depth", 0.0)) > 1e-8
                    else PREVIEW_FLOOR
                ),
            )
        )
    for row_x, color in transition_rows:
        _append_projected_curves(
            target,
            _row_curves(
                layout_context,
                boundary_context,
                row_x,
                opening_half_width_mm,
                mm_scale,
            ),
            projection,
            color,
            2,
        )


def _usable_row_intervals(tier_regions, params, row_index):
    if tier_regions is None:
        return None
    if row_index >= len(tier_regions):
        return []
    region = tier_regions[row_index]
    intervals = region.get("intervals", []) if hasattr(region, "get") else region
    intervals = list(intervals)
    if not intervals:
        return []
    margin = float(params.get("side_floor_margin", 0.0))
    usable = []
    for left, right in intervals:
        clipped_left = float(left) + margin
        clipped_right = float(right) - margin
        if clipped_right > clipped_left + PLAN_CURVE_TOLERANCE:
            usable.append((clipped_left, clipped_right))
    return usable


def _row_block_layout(
    params,
    layout_context,
    row_x,
    tier_regions,
    row_index,
    row_overrides,
):
    raw_intervals = None
    if tier_regions is not None:
        region = tier_regions[row_index]
        raw_intervals = (
            region.get("intervals", [])
            if hasattr(region, "get")
            else region
        )
    counts = resolve_row_seat_block_counts(
        params,
        row_x,
        layout_context,
        raw_intervals,
        row_overrides=row_overrides,
        row_index=row_index,
    )
    module_width = float(params["seat_module_width"])
    aisle_width = float(params["longitudinal_aisle_width"])
    total_width = (
        sum(int(count) * module_width for count in counts)
        + max(len(counts) - 1, 0) * aisle_width
    )
    usable_intervals = _usable_row_intervals(
        tier_regions,
        params,
        row_index,
    )
    if usable_intervals:
        center = (usable_intervals[0][0] + usable_intervals[-1][1]) * 0.5
    else:
        center = 0.0
    cursor = center - total_width * 0.5
    aisle_pairs = []
    for block_index, block_count in enumerate(counts[:-1]):
        cursor += int(block_count) * module_width
        aisle_pairs.append((cursor, cursor + aisle_width))
        cursor += aisle_width
    return aisle_pairs


def _polyline_from_points(points):
    valid_points = [point for point in points if point is not None]
    if len(valid_points) < 2:
        return None
    return rg.PolylineCurve(valid_points)


def _append_longitudinal_aisles(
    target,
    params,
    tier_result,
    layout_context,
    boundary_context,
    tier_regions,
    front_x,
    rear_x,
    projection,
    mm_scale,
    row_overrides,
):
    row_x_values = list(tier_result["x_values"])
    if not row_x_values:
        return
    row_aisles = [
        _row_block_layout(
            params,
            layout_context,
            row_x,
            tier_regions,
            row_index,
            row_overrides,
        )
        for row_index, row_x in enumerate(row_x_values)
    ]
    aisle_count = (
        max(len(values) for values in row_aisles)
        if row_aisles
        else 0
    )
    for aisle_index in range(aisle_count):
        for edge_index in (0, 1):
            runs = []
            current_run = []
            for row_index, row_x in enumerate(row_x_values):
                if aisle_index >= len(row_aisles[row_index]):
                    if current_run:
                        runs.append(current_run)
                        current_run = []
                    continue
                lateral = row_aisles[row_index][aisle_index][edge_index]
                current_run.append((row_index, row_x, lateral))
            if current_run:
                runs.append(current_run)

            for run in runs:
                first_index, first_row_x, first_lateral = run[0]
                last_index, last_row_x, last_lateral = run[-1]
                run_front_x = (
                    front_x
                    if first_index == 0
                    else (
                        float(row_x_values[first_index - 1])
                        + float(first_row_x)
                    ) * 0.5
                )
                run_rear_x = (
                    rear_x
                    if last_index == len(row_x_values) - 1
                    else (
                        float(last_row_x)
                        + float(row_x_values[last_index + 1])
                    ) * 0.5
                )
                points = [
                    _layout_point(
                        layout_context,
                        run_front_x,
                        first_lateral,
                        mm_scale,
                    )
                ]
                for unused_row_index, row_x, lateral in run:
                    points.append(
                        _layout_point(
                            layout_context,
                            row_x,
                            lateral,
                            mm_scale,
                        )
                    )
                points.append(
                    _layout_point(
                        layout_context,
                        run_rear_x,
                        last_lateral,
                        mm_scale,
                    )
                )
                aisle_curve = _polyline_from_points(points)
                if aisle_curve is None:
                    continue
                aisle_curves = [aisle_curve]
                if boundary_context is not None:
                    try:
                        flattened_aisle = _project_curve(
                            aisle_curve,
                            projection,
                        )
                        aisle_curves = curve_segments_inside_boundary(
                            boundary_context,
                            flattened_aisle,
                        )
                    except Exception:
                        aisle_curves = []
                _append_projected_curves(
                    target,
                    aisle_curves,
                    projection,
                    PREVIEW_AISLE,
                    2,
                )


def _append_cross_and_rear_aisles(
    target,
    params,
    tier_result,
    layout_context,
    boundary_context,
    half_width_mm,
    projection,
    mm_scale,
    stalls=False,
):
    x_values = list(tier_result["x_values"])
    if not x_values:
        return
    row_pitch = float(
        params["row_pitch"]
        if stalls
        else params["balcony_row_pitch"]
    )
    if stalls:
        aisle_before = tier_result.get(
            "aisle_before_values",
            [False] * len(x_values),
        )
        for index in range(1, len(x_values)):
            if not aisle_before[index]:
                continue
            aisle_front_x = float(x_values[index - 1])
            aisle_rear_x = float(x_values[index]) - row_pitch
            for row_x in (aisle_front_x, aisle_rear_x):
                _append_projected_curves(
                    target,
                    _row_curves(
                        layout_context,
                        boundary_context,
                        row_x,
                        half_width_mm,
                        mm_scale,
                    ),
                    projection,
                    PREVIEW_AISLE,
                    2,
                )

    rear_aisle_width = float(params.get("aisle_width", 0.0))
    if rear_aisle_width <= 1e-8:
        return
    for row_x in (x_values[-1], x_values[-1] + rear_aisle_width):
        _append_projected_curves(
            target,
            _row_curves(
                layout_context,
                boundary_context,
                row_x,
                half_width_mm,
                mm_scale,
            ),
            projection,
            PREVIEW_AISLE,
            2,
        )


def _append_balcony_railing(
    target,
    balcony_result,
    layout_context,
    boundary_context,
    half_width_mm,
    projection,
    mm_scale,
):
    front_x = float(balcony_result["railing_front_x"])
    rear_x = float(balcony_result["railing_rear_x"])
    for row_x in (front_x, rear_x):
        _append_projected_curves(
            target,
            _row_curves(
                layout_context,
                boundary_context,
                row_x,
                half_width_mm,
                mm_scale,
            ),
            projection,
            PREVIEW_BALCONY_RAIL,
            4,
        )
    if boundary_context is not None:
        boundary_sides = _tier_boundary_parts(
            boundary_context,
            layout_context,
            front_x,
            rear_x,
            half_width_mm,
            mm_scale,
        )
        _append_projected_curves(
            target,
            boundary_sides,
            projection,
            PREVIEW_BALCONY_RAIL,
            4,
        )
        return
    if layout_context["mode"] == "radial":
        for angle in (
            -float(layout_context["half_angle"]),
            float(layout_context["half_angle"]),
        ):
            side = build_radial_side_line(
                layout_context,
                float(layout_context["radius"]) + front_x,
                float(layout_context["radius"]) + rear_x,
                angle,
                0.0,
                0.0,
                mm_scale,
            )
            _append_projected_curves(
                target,
                [side],
                projection,
                PREVIEW_BALCONY_RAIL,
                4,
            )
        return
    for lateral in (-half_width_mm, half_width_mm):
        side = rg.LineCurve(
            _layout_point(
                layout_context,
                front_x,
                lateral,
                mm_scale,
            ),
            _layout_point(
                layout_context,
                rear_x,
                lateral,
                mm_scale,
            ),
        )
        _append_projected_curves(
            target,
            [side],
            projection,
            PREVIEW_BALCONY_RAIL,
            4,
        )


def _tier_regions(preview_data, tier_slot):
    all_regions = preview_data.get("boundary_tier_row_regions")
    if all_regions is None or tier_slot >= len(all_regions):
        return None
    return all_regions[tier_slot]


def _tier_intervals(tier_regions):
    if tier_regions is None:
        return None
    return [
        (
            region.get("intervals", [])
            if hasattr(region, "get")
            else region
        )
        for region in tier_regions
    ]


def _append_plan_seats(
    target,
    seat_source,
    params,
    tier_result,
    layout_context,
    tier_regions,
    stage_point,
    audience_direction,
    stage_right_direction,
    projection,
    mm_scale,
    row_overrides,
    highlighted_row_index=None,
):
    intervals = _tier_intervals(tier_regions)
    if intervals is None:
        placement_result = calculate_3d_seat_placements(
            params,
            tier_result,
            layout_context,
            row_overrides=row_overrides,
        )
    else:
        placement_result = calculate_3d_seat_placements(
            params,
            tier_result,
            layout_context,
            intervals,
            row_overrides=row_overrides,
        )

    chair_plan = seat_source["chair_plan"]
    armrest_plan = seat_source["armrest_plan"]
    target_chair_width = (
        float(params["seat_module_width"])
        - SEAT_SOURCE_ARMREST_WIDTH
    )
    chair_x_scale = target_chair_width / SEAT_SOURCE_CHAIR_WIDTH

    for placement in placement_result["chair_placements"]:
        chair_color = (
            PREVIEW_WARNING
            if int(placement["row_index"]) == highlighted_row_index
            else PREVIEW_3D_CHAIR
        )
        transform = seat_module_transform(
            stage_point,
            audience_direction,
            stage_right_direction,
            placement,
            mm_scale,
            chair_x_scale,
            layout_context,
        )
        for source_curve in chair_plan["preview_curves"]:
            transformed = _transform_curve(source_curve, transform)
            projected = _project_curve(transformed, projection)
            if projected is not None:
                target.append((projected, chair_color, 1))

    for placement in placement_result["armrest_placements"]:
        armrest_color = (
            PREVIEW_WARNING
            if int(placement["row_index"]) == highlighted_row_index
            else PREVIEW_3D_ARMREST
        )
        transform = seat_module_transform(
            stage_point,
            audience_direction,
            stage_right_direction,
            placement,
            mm_scale,
            1.0,
            layout_context,
        )
        for source_curve in armrest_plan["preview_curves"]:
            transformed = _transform_curve(source_curve, transform)
            projected = _project_curve(transformed, projection)
            if projected is not None:
                target.append((projected, armrest_color, 1))
    return placement_result


def _occupied_row_extents(params, placement_result):
    """Return the physical plan extents of chairs and armrests by row."""
    extents = {}

    def include(row_index, center_lateral, half_width):
        left = float(center_lateral) - float(half_width)
        right = float(center_lateral) + float(half_width)
        row_extent = extents.get(row_index)
        if row_extent is None:
            extents[row_index] = {
                "left": left,
                "right": right,
                "left_anchor": float(center_lateral),
                "right_anchor": float(center_lateral),
            }
            return
        if left < row_extent["left"]:
            row_extent["left"] = left
            row_extent["left_anchor"] = float(center_lateral)
        if right > row_extent["right"]:
            row_extent["right"] = right
            row_extent["right_anchor"] = float(center_lateral)

    chair_width = (
        float(params["seat_module_width"])
        - SEAT_SOURCE_ARMREST_WIDTH
    )
    chair_half_width = max(chair_width, 0.0) * 0.5
    for placement in placement_result["chair_placements"]:
        include(
            int(placement["row_index"]),
            placement["lateral"],
            chair_half_width,
        )
    armrest_half_width = SEAT_SOURCE_ARMREST_WIDTH * 0.5
    for placement in placement_result["armrest_placements"]:
        include(
            int(placement["row_index"]),
            placement["lateral"],
            armrest_half_width,
        )
    return extents


def _nearest_wall_interval(intervals, anchor_lateral):
    """Find the wall segment containing, or nearest to, a seat anchor."""
    best_interval = None
    best_distance = None
    anchor_lateral = float(anchor_lateral)
    for interval in intervals:
        left = float(interval[0])
        right = float(interval[1])
        if right < left:
            left, right = right, left
        if (
            anchor_lateral >= left - PLAN_CURVE_TOLERANCE
            and anchor_lateral <= right + PLAN_CURVE_TOLERANCE
        ):
            return (left, right)
        distance = min(
            abs(anchor_lateral - left),
            abs(anchor_lateral - right),
        )
        if best_distance is None or distance < best_distance:
            best_distance = distance
            best_interval = (left, right)
    return best_interval


def _append_row_clearance_annotations(
    target,
    params,
    tier_result,
    layout_context,
    boundary_context,
    row_source_curves,
    floor_half_width_mm,
    placement_result,
    projection,
    mm_scale,
    highlighted_row_index=None,
):
    """Draw actual left/right wall-to-seat distances for occupied rows."""
    occupied_extents = _occupied_row_extents(params, placement_result)
    row_clearances = []
    for row_index, row_x in enumerate(tier_result["x_values"]):
        row_extent = occupied_extents.get(row_index)
        clearance = {
            "row_index": row_index,
            "row_x": float(row_x),
            "occupied": row_extent is not None,
            "left_mm": None,
            "right_mm": None,
        }
        if row_extent is None:
            row_clearances.append(clearance)
            continue
        try:
            wall_intervals = _row_wall_intervals(
                row_source_curves[row_index],
                layout_context,
                boundary_context,
                row_x,
                floor_half_width_mm,
                mm_scale,
            )
        except Exception:
            wall_intervals = []
        left_interval = _nearest_wall_interval(
            wall_intervals,
            row_extent["left_anchor"],
        )
        right_interval = _nearest_wall_interval(
            wall_intervals,
            row_extent["right_anchor"],
        )
        if left_interval is None or right_interval is None:
            clearance["occupied"] = False
            row_clearances.append(clearance)
            continue

        left_wall = float(left_interval[0])
        right_wall = float(right_interval[1])
        left_seat = float(row_extent["left"])
        right_seat = float(row_extent["right"])
        clearance.update(
            {
                "left_wall_lateral": left_wall,
                "left_seat_lateral": left_seat,
                "right_seat_lateral": right_seat,
                "right_wall_lateral": right_wall,
                "left_mm": left_seat - left_wall,
                "right_mm": right_wall - right_seat,
            }
        )
        row_clearances.append(clearance)

    for clearance in row_clearances:
        if not clearance.get("occupied", False):
            continue
        row_index = clearance["row_index"]
        row_x = clearance["row_x"]
        side_values = (
            (
                clearance["left_wall_lateral"],
                clearance["left_seat_lateral"],
                clearance["left_mm"],
            ),
            (
                clearance["right_seat_lateral"],
                clearance["right_wall_lateral"],
                clearance["right_mm"],
            ),
        )
        for start_lateral, end_lateral, distance_mm in side_values:
            is_warning = distance_mm < -PLAN_CURVE_TOLERANCE
            use_warning_color = (
                row_index == highlighted_row_index or is_warning
            )
            color = (
                PREVIEW_WARNING
                if use_warning_color
                else PREVIEW_SECTION_DIMENSION
            )
            dimension_curves = [
                _row_interval_curve(
                    layout_context,
                    row_x,
                    start_lateral,
                    end_lateral,
                    mm_scale,
                ),
                _row_dimension_tick(
                    layout_context,
                    row_x,
                    start_lateral,
                    mm_scale,
                ),
            ]
            if (
                abs(float(end_lateral) - float(start_lateral))
                > PLAN_CURVE_TOLERANCE
            ):
                dimension_curves.append(
                    _row_dimension_tick(
                        layout_context,
                        row_x,
                        end_lateral,
                        mm_scale,
                    )
                )
            _append_projected_curves(
                target,
                dimension_curves,
                projection,
                color,
                1,
            )
    return row_clearances


def _row_left_lateral_mm(
    params,
    layout_context,
    tier_regions,
    row_index,
    row_x,
    floor_half_width_mm,
    occupied_left_edges,
):
    """Return the plan-left edge of one row in lateral millimeters.

    Lateral positive follows ``audience_view_right_direction`` (local +X),
    so the left edge seen by an audience member facing the stage is always
    the minimum lateral value.  Occupied rows follow their actual seat and
    armrest extents; empty rows fall back to the usable boundary or tier
    edge so their row number remains visible.
    """
    if row_index in occupied_left_edges:
        return occupied_left_edges[row_index]

    usable_intervals = _usable_row_intervals(
        tier_regions,
        params,
        row_index,
    )
    if usable_intervals:
        return min(float(interval[0]) for interval in usable_intervals)

    if tier_regions is not None and row_index < len(tier_regions):
        region = tier_regions[row_index]
        raw_intervals = (
            region.get("intervals", [])
            if hasattr(region, "get")
            else region
        )
        if raw_intervals:
            return min(float(interval[0]) for interval in raw_intervals)

    if layout_context["mode"] == "radial":
        row_radius = float(layout_context["radius"]) + float(row_x)
        return -row_radius * float(layout_context["half_angle"])
    return -float(floor_half_width_mm)


def _build_row_number_labels(
    params,
    tier_result,
    layout_context,
    tier_regions,
    floor_half_width_mm,
    placement_result,
    projection,
    mm_scale,
):
    """Build 1-based row-number anchors at each row's plan-left end."""
    occupied_left_edges = dict(
        (
            row_index,
            row_extent["left"],
        )
        for row_index, row_extent in _occupied_row_extents(
            params,
            placement_result,
        ).items()
    )

    labels = []
    for row_index, row_x in enumerate(tier_result["x_values"]):
        left_lateral = _row_left_lateral_mm(
            params,
            layout_context,
            tier_regions,
            row_index,
            row_x,
            floor_half_width_mm,
            occupied_left_edges,
        )
        label_point = _layout_point(
            layout_context,
            row_x,
            left_lateral - PLAN_ROW_LABEL_CLEARANCE_MM,
            mm_scale,
        )
        label_point.Transform(projection)
        labels.append((label_point, str(row_index + 1), row_index))
    return labels


def _local_bounding_box(curve_entries, world_to_local):
    bounding_box = rg.BoundingBox.Empty
    for curve, unused_color, unused_thickness in curve_entries:
        local_curve = _transform_curve(curve, world_to_local)
        if local_curve is None:
            continue
        curve_box = local_curve.GetBoundingBox(True)
        if curve_box.IsValid:
            bounding_box.Union(curve_box)
    return bounding_box


def _translated_entries(curve_entries, translation):
    translated = []
    for curve, color, thickness in curve_entries:
        moved = _transform_curve(curve, translation)
        if moved is not None:
            translated.append((moved, color, thickness))
    return translated


def _tier_floor_half_width(
    params,
    boundary_context,
    layout_context,
    row_layouts=None,
):
    if (
        boundary_context is not None
        or layout_context["mode"] == "radial"
    ):
        return 0.0
    if row_layouts is None:
        seat_layout_width = calculate_seat_layout_width(params)
    else:
        row_widths = [
            float(layout.get("row_total_width", 0.0))
            for layout in row_layouts
        ]
        seat_layout_width = max(row_widths) if row_widths else 0.0
        if row_layouts and seat_layout_width <= 1e-9:
            # Empty removes chairs/armrests, not the tier platform itself.
            seat_layout_width = calculate_seat_layout_width(params)
    return (
        seat_layout_width
        + SEAT_SOURCE_ARMREST_WIDTH
        + float(params.get("side_floor_margin", 0.0)) * 2.0
    ) * 0.5


def build_plan_preview_geometry(
    preview_data,
    params,
    doc,
    seat_source,
    row_overrides_by_tier=None,
    highlighted_row=None,
):
    """Build preview-only, flattened plan drawings for every seating tier."""
    if preview_data is None:
        raise ValueError("A valid auditorium preview is required.")
    if seat_source is None:
        raise ValueError("AuditoriumSeat.3dm is required for Plan Preview.")
    if (
        seat_source.get("chair_plan") is None
        or seat_source.get("armrest_plan") is None
    ):
        raise ValueError(
            "AuditoriumSeat.3dm requires TT_ChairBody_Plan and "
            "TT_Armrest_Plan for Plan Preview."
        )

    if row_overrides_by_tier is None:
        row_overrides_by_tier = params.get("seat_row_overrides")
    row_overrides_by_tier = normalize_tier_row_overrides(
        row_overrides_by_tier,
        2,
    )
    highlighted_tier_key = None
    highlighted_row_index = None
    if highlighted_row is not None:
        try:
            highlighted_tier_key = str(highlighted_row[0])
            highlighted_row_index = int(highlighted_row[1])
        except Exception:
            highlighted_tier_key = None
            highlighted_row_index = None

    mm_scale = unit_scale_from_mm(doc)
    layout_context = preview_data["plan_layout"]
    boundary_context = preview_data.get("auditorium_boundary")
    audience_direction = rg.Vector3d(preview_data["direction"])
    if not audience_direction.Unitize():
        raise ValueError("The auditorium direction is invalid.")
    stage_right_direction, unused_stage_back = get_stage_directions(
        audience_direction
    )
    stage_point = rg.Point3d(layout_context["reference_mid_point"])
    opening_point = rg.Point3d(preview_data["opening_stage_point"])
    plan_z = float(preview_data["audience_datum_point"].Z)
    projection_plane = rg.Plane(
        rg.Point3d(opening_point.X, opening_point.Y, plan_z),
        rg.Vector3d.ZAxis,
    )
    projection = rg.Transform.PlanarProjection(projection_plane)

    opening_direction = rg.Vector3d(audience_direction)
    opening_direction.Reverse()
    local_plane = rg.Plane(
        rg.Point3d(opening_point.X, opening_point.Y, plan_z),
        stage_right_direction,
        opening_direction,
    )
    world_to_local = rg.Transform.PlaneToPlane(
        local_plane,
        rg.Plane.WorldXY,
    )

    balcony_results = list(preview_data.get("balcony_calculations", []))
    tier_specs = [
        {
            "slot": 0,
            "label": "Stalls",
            "result": preview_data["calculation"],
            "floor_color": PREVIEW_FLOOR,
            "params": params,
            "override_key": "stalls",
        },
        {
            "slot": 1,
            "label": "Balcony 1",
            "result": balcony_results[0] if len(balcony_results) > 0 else None,
            "floor_color": PREVIEW_BALCONY,
            "params": dict(
                params,
                balcony_row_pitch=params.get("balcony_row_pitch"),
            ),
            "override_key": "balcony_1",
        },
        {
            "slot": 2,
            "label": "Balcony 2",
            "result": balcony_results[1] if len(balcony_results) > 1 else None,
            "floor_color": PREVIEW_BALCONY_SECOND,
            "params": dict(
                params,
                balcony_row_pitch=params.get("balcony2_row_pitch"),
            ),
            "override_key": "balcony_2",
        },
    ]

    total_seat_count = 0
    for spec in tier_specs:
        tier_result = spec["result"]
        if spec["slot"] > 0 and not balcony_result_is_displayable(tier_result):
            spec["row_layouts"] = []
            continue
        tier_regions = _tier_regions(preview_data, spec["slot"])
        intervals = _tier_intervals(tier_regions)
        row_overrides = row_overrides_by_tier.get(spec["override_key"])
        row_layouts = calculate_tier_row_layouts(
            spec["params"],
            tier_result,
            layout_context,
            intervals,
            row_overrides=row_overrides,
        )
        spec["row_layouts"] = row_layouts
        spec["row_overrides"] = row_overrides
        total_seat_count += sum(
            int(layout.get("seat_count", 0))
            for layout in row_layouts
        )

    if total_seat_count > MAXIMUM_3D_CHAIR_COUNT:
        raise ValueError(
            "Plan Preview seat count exceeds the {0:,} seat preview "
            "limit. Reduce the row or seat count before opening the plan."
            .format(MAXIMUM_3D_CHAIR_COUNT)
        )

    raw_tiers = [None, None, None]
    raw_seat_tiers = [None, None, None]
    raw_row_labels = [None, None, None]
    tier_metadata = [None, None, None]
    for spec in tier_specs:
        tier_result = spec["result"]
        if spec["slot"] > 0 and not balcony_result_is_displayable(tier_result):
            continue
        tier_params = spec["params"]
        row_layouts = spec["row_layouts"]
        row_overrides = spec.get("row_overrides")
        tier_regions = _tier_regions(preview_data, spec["slot"])
        floor_half_width_mm = _tier_floor_half_width(
            tier_params,
            boundary_context,
            layout_context,
            row_layouts,
        )
        active_row_index = (
            highlighted_row_index
            if spec["override_key"] == highlighted_tier_key
            else None
        )
        curves = []
        _append_opening_reference(
            curves,
            preview_data,
            params,
            projection,
            stage_right_direction,
            mm_scale,
        )

        x_values = list(tier_result["x_values"])
        if not x_values:
            continue
        if spec["slot"] == 0:
            floor_front_x = (
                0.0
                if boundary_context is not None
                else float(params["first_row_distance"])
            )
            aisle_front_x = float(params["first_row_distance"])
            _append_stalls_transition(
                curves,
                preview_data,
                params,
                layout_context,
                boundary_context,
                floor_half_width_mm,
                projection,
                stage_right_direction,
                mm_scale,
            )
        else:
            floor_front_x = float(tier_result["railing_front_x"])
            aisle_front_x = floor_front_x
        floor_rear_x = float(x_values[-1]) + float(
            params.get("aisle_width", 0.0)
        )

        _append_floor_outline(
            curves,
            preview_data,
            layout_context,
            boundary_context,
            floor_front_x,
            floor_rear_x,
            floor_half_width_mm,
            projection,
            spec["floor_color"],
            mm_scale,
        )
        row_source_curves = _append_row_reference_guides(
            curves,
            tier_result,
            layout_context,
            boundary_context,
            tier_regions,
            floor_half_width_mm,
            projection,
            mm_scale,
            active_row_index,
        )
        seat_curve_start = len(curves)
        placement_result = _append_plan_seats(
            curves,
            seat_source,
            tier_params,
            tier_result,
            layout_context,
            tier_regions,
            stage_point,
            audience_direction,
            stage_right_direction,
            projection,
            mm_scale,
            row_overrides,
            active_row_index,
        )
        raw_seat_tiers[spec["slot"]] = list(
            curves[seat_curve_start:]
        )
        row_clearances = _append_row_clearance_annotations(
            curves,
            tier_params,
            tier_result,
            layout_context,
            boundary_context,
            row_source_curves,
            floor_half_width_mm,
            placement_result,
            projection,
            mm_scale,
            active_row_index,
        )
        raw_row_labels[spec["slot"]] = _build_row_number_labels(
            tier_params,
            tier_result,
            layout_context,
            tier_regions,
            floor_half_width_mm,
            placement_result,
            projection,
            mm_scale,
        )
        _append_longitudinal_aisles(
            curves,
            tier_params,
            tier_result,
            layout_context,
            boundary_context,
            tier_regions,
            aisle_front_x,
            floor_rear_x,
            projection,
            mm_scale,
            row_overrides,
        )
        _append_cross_and_rear_aisles(
            curves,
            tier_params,
            tier_result,
            layout_context,
            boundary_context,
            floor_half_width_mm,
            projection,
            mm_scale,
            stalls=(spec["slot"] == 0),
        )
        if spec["slot"] > 0:
            _append_balcony_railing(
                curves,
                tier_result,
                layout_context,
                boundary_context,
                floor_half_width_mm,
                projection,
                mm_scale,
            )

        raw_tiers[spec["slot"]] = curves
        tier_metadata[spec["slot"]] = {
            "label": spec["label"],
            "seat_count": len(placement_result["chair_placements"]),
            "row_count": len(x_values),
            "floor_front_x": floor_front_x,
            "floor_rear_x": floor_rear_x,
            "row_layouts": row_layouts,
            "row_clearances": row_clearances,
        }

    all_raw_curves = [
        entry
        for tier_curves in raw_tiers
        if tier_curves is not None
        for entry in tier_curves
    ]
    all_raw_seat_curves = [
        entry
        for tier_curves in raw_seat_tiers
        if tier_curves is not None
        for entry in tier_curves
    ]
    # Offset W is intentionally based only on the actual chair and armrest
    # plan curves.  Floor/aisle/railing outlines and the opening reference
    # remain visible in each preview, but do not enlarge the spacing datum.
    raw_box = _local_bounding_box(
        all_raw_seat_curves,
        world_to_local,
    )
    if not raw_box.IsValid:
        # With every tier explicitly empty there is no physical seat width
        # from which to derive W.  Keep the preview usable with a geometry
        # fallback while preserving chair-only spacing whenever seats exist.
        raw_box = _local_bounding_box(all_raw_curves, world_to_local)
    if not raw_box.IsValid:
        raise ValueError("Plan Preview did not produce valid geometry.")
    plan_width = float(raw_box.Max.X - raw_box.Min.X)
    if plan_width <= max(float(doc.ModelAbsoluteTolerance), 1e-6):
        raise ValueError("Plan Preview bounding-box width is too small.")

    preview_curves = []
    preview_labels = []
    tier_offsets = [None, None, None]
    tier_boxes = [None, None, None]
    label_colors = (
        PREVIEW_FLOOR,
        PREVIEW_BALCONY,
        PREVIEW_BALCONY_SECOND,
    )
    for slot, tier_curves in enumerate(raw_tiers):
        if tier_curves is None:
            continue
        offset_distance = PLAN_TIER_OFFSET_FACTORS[slot] * plan_width
        translation_vector = stage_right_direction * (-offset_distance)
        translation = rg.Transform.Translation(translation_vector)
        translated = _translated_entries(tier_curves, translation)
        preview_curves.extend(translated)
        tier_offsets[slot] = offset_distance

        for row_label_point, row_label_text, row_index in (
            raw_row_labels[slot] or []
        ):
            translated_label_point = rg.Point3d(row_label_point)
            translated_label_point.Transform(translation)
            preview_labels.append(
                (
                    translated_label_point,
                    row_label_text,
                    (
                        PREVIEW_WARNING
                        if (
                            highlighted_tier_key
                            == tier_specs[slot]["override_key"]
                            and row_index == highlighted_row_index
                        )
                        else label_colors[slot]
                    ),
                    Color.White,
                )
            )

        local_box = _local_bounding_box(tier_curves, world_to_local)
        if local_box.IsValid:
            tier_boxes[slot] = {
                "min_x": float(local_box.Min.X),
                "max_x": float(local_box.Max.X),
                "min_y": float(local_box.Min.Y),
                "max_y": float(local_box.Max.Y),
            }
            label_point = local_plane.PointAt(
                float(local_box.Min.X),
                float(local_box.Max.Y) + PLAN_LABEL_CLEARANCE_MM * mm_scale,
            )
            label_point.Transform(translation)
            metadata = tier_metadata[slot]
            preview_labels.append(
                (
                    label_point,
                    "{0} / {1:,} seats".format(
                        metadata["label"],
                        metadata["seat_count"],
                    ),
                    label_colors[slot],
                    Color.White,
                )
            )

    return {
        "preview_curves": preview_curves,
        "preview_points": [],
        "preview_meshes": [],
        "preview_wire_meshes": [],
        "preview_labels": preview_labels,
        "plan_width": plan_width,
        "tier_offsets": tier_offsets,
        "tier_bounding_boxes": tier_boxes,
        "tier_metadata": tier_metadata,
        "local_plane": local_plane,
    }
