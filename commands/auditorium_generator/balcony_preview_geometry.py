# -*- coding: utf-8 -*-
"""Preview and bake curves for one calculated balcony tier."""

from .calculations.sections import balcony_result_is_displayable
from .chair_preview_geometry import build_chair_curves
from .preview_palette import (
    PREVIEW_AISLE,
    PREVIEW_BALCONY,
    PREVIEW_BALCONY_RAIL,
    PREVIEW_BALCONY_SECOND,
    PREVIEW_FULL_STAGE_SIGHT,
    PREVIEW_SEAT,
    PREVIEW_WARNING,
)
from .rhino_primitives import line_curve, point_at


def append_balcony_tier_geometry(
    balcony_result,
    stage_point,
    direction,
    mm_scale,
    params,
    stage_sight_point,
    stage_upper_sight_point,
    preview_curves,
    preview_points,
    bake_curves,
    bake_points
):
    """Append one calculated balcony tier to preview and bake collections."""
    tier_number = balcony_result["tier_index"] + 1
    name_prefix = "Balcony{0:02d}".format(tier_number)
    tier_color = (
        PREVIEW_BALCONY
        if tier_number == 1
        else PREVIEW_BALCONY_SECOND
    )

    if not balcony_result_is_displayable(balcony_result):
        return

    x_values = balcony_result["x_values"]
    base_z_values = balcony_result["base_z_values"]
    eye_x_values = balcony_result["eye_x_values"]
    eye_z_values = balcony_result["eye_z_values"]
    row_count = balcony_result["row_count"]
    sightline_violations = balcony_result.get(
        "sightline_violations",
        [False] * row_count
    )
    floor_color = PREVIEW_WARNING
    seat_row_layouts = params.get("seat_row_layouts")

    for index in range(row_count):
        row_warning = sightline_violations[index]
        chair_color = PREVIEW_WARNING if row_warning else PREVIEW_SEAT
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
            and (
                seat_row_layouts is None
                or index >= len(seat_row_layouts)
                or seat_row_layouts[index].get("seat_count", 0) > 0
            )
        ):
            for chair_curve in build_chair_curves(
                stage_point,
                direction,
                x_values[index],
                base_z_values[index],
                mm_scale
            ):
                preview_curves.append((chair_curve, chair_color, 2))
                bake_curves.append(
                    (
                        chair_curve,
                        chair_color,
                        name_prefix + "Chair",
                    )
                )
        if params["show_eye_points"]:
            point_color = PREVIEW_WARNING if row_warning else tier_color
            preview_points.append((eye_point, point_color, 5))
            bake_points.append(
                (eye_point, point_color, name_prefix + "SightPoint")
            )
        if params["show_sightlines"]:
            is_end_row = index == 0 or index == row_count - 1
            sight_color = (
                PREVIEW_WARNING
                if row_warning
                else (
                    PREVIEW_FULL_STAGE_SIGHT
                    if is_end_row
                    else tier_color
                )
            )
            lower_line = line_curve(stage_sight_point, eye_point)
            preview_curves.append(
                (lower_line, sight_color, 2 if is_end_row else 1)
            )
            bake_curves.append(
                (
                    lower_line,
                    sight_color,
                    (
                        name_prefix + "FullStageSightlineLower"
                        if is_end_row
                        else name_prefix + "Sightline"
                    ),
                )
            )
            if is_end_row:
                upper_line = line_curve(
                    stage_upper_sight_point,
                    eye_point
                )
                preview_curves.append(
                    (upper_line, PREVIEW_FULL_STAGE_SIGHT, 2)
                )
                bake_curves.append(
                    (
                        upper_line,
                        PREVIEW_FULL_STAGE_SIGHT,
                        name_prefix + "FullStageSightlineUpper",
                    )
                )

    rail_floor = point_at(
        stage_point,
        direction,
        balcony_result["railing_front_x"],
        balcony_result["railing_floor_z"],
        mm_scale
    )
    rail_front_top = point_at(
        stage_point,
        direction,
        balcony_result["railing_front_x"],
        balcony_result["railing_top_z"],
        mm_scale
    )
    rail_rear_top = point_at(
        stage_point,
        direction,
        balcony_result["railing_rear_x"],
        balcony_result["railing_top_z"],
        mm_scale
    )
    rail_color = (
        PREVIEW_WARNING
        if balcony_result["railing_sight_collision"]
        else PREVIEW_BALCONY_RAIL
    )
    for curve, suffix in (
        (line_curve(rail_floor, rail_front_top), "RailingFront"),
        (line_curve(rail_front_top, rail_rear_top), "RailingTop"),
    ):
        preview_curves.append((curve, rail_color, 4))
        bake_curves.append(
            (curve, rail_color, name_prefix + suffix)
        )

    first_platform_end = point_at(
        stage_point,
        direction,
        x_values[0],
        base_z_values[0],
        mm_scale
    )
    first_platform = line_curve(rail_floor, first_platform_end)
    preview_curves.append((first_platform, floor_color, 4))
    bake_curves.append(
        (first_platform, floor_color, name_prefix + "Floor")
    )

    for index in range(1, row_count):
        riser_x = x_values[index - 1]
        riser_start = point_at(
            stage_point,
            direction,
            riser_x,
            base_z_values[index - 1],
            mm_scale
        )
        riser_end = point_at(
            stage_point,
            direction,
            riser_x,
            base_z_values[index],
            mm_scale
        )
        platform_end = point_at(
            stage_point,
            direction,
            x_values[index],
            base_z_values[index],
            mm_scale
        )
        riser_curve = line_curve(riser_start, riser_end)
        platform_curve = line_curve(riser_end, platform_end)
        preview_curves.append((riser_curve, floor_color, 4))
        preview_curves.append((platform_curve, floor_color, 4))
        bake_curves.append(
            (riser_curve, floor_color, name_prefix + "Floor")
        )
        bake_curves.append(
            (platform_curve, floor_color, name_prefix + "Floor")
        )

    rear_aisle_width = params["aisle_width"]
    if rear_aisle_width > 1e-8:
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
                name_prefix + "RearAisle",
            )
        )
