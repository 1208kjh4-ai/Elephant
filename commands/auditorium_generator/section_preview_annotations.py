# -*- coding: utf-8 -*-
"""Preview-only riser labels and outer section dimensions."""

from System.Drawing import Color

from .calculations.sections import balcony_result_is_displayable
from .formatting import (
    format_riser_height_label,
    format_section_height_dimension,
)
from .preview_palette import (
    PREVIEW_AISLE,
    PREVIEW_FLOOR,
    PREVIEW_SECTION_DIMENSION,
    PREVIEW_WARNING,
)
from .rhino_primitives import line_curve, point_at


def build_riser_height_preview_labels(
    stage_point,
    audience_direction,
    params,
    stalls_result,
    balcony_results,
    mm_scale
):
    """Build screen-facing preview labels; these are never baked."""
    labels = []

    def add_label(
        riser_x,
        bottom_z,
        riser_height,
        upper_platform_depth,
        background_color,
        text_color
    ):
        if riser_height <= 1e-8:
            return
        label_point = point_at(
            stage_point,
            audience_direction,
            riser_x + upper_platform_depth * 0.5,
            bottom_z + riser_height,
            mm_scale
        )
        labels.append(
            (
                label_point,
                format_riser_height_label(riser_height),
                background_color,
                text_color,
            )
        )

    if params["floor_type"] == "stepped":
        x_values = stalls_result["x_values"]
        base_z_values = stalls_result["base_z_values"]
        riser_values = stalls_result["riser_values"]
        violations = stalls_result["violations"]
        aisle_before_values = stalls_result["aisle_before_values"]
        stair_tread_counts = stalls_result[
            "aisle_stair_tread_counts"
        ]
        stair_riser_heights = stalls_result[
            "aisle_stair_riser_heights"
        ]
        stair_run_values = stalls_result[
            "aisle_stair_run_values"
        ]
        row_pitch = params["row_pitch"]
        tread_depth = params["aisle_stair_tread_depth"]

        for index in range(1, len(x_values)):
            if aisle_before_values[index]:
                tread_count = stair_tread_counts[index]
                riser_height = stair_riser_heights[index]
                if riser_height <= 1e-8:
                    continue
                stair_x = (
                    x_values[index]
                    - row_pitch
                    - stair_run_values[index]
                )
                stair_z = base_z_values[index - 1]
                label_color = (
                    PREVIEW_WARNING
                    if violations[index]
                    else PREVIEW_AISLE
                )
                label_text_color = (
                    Color.White
                    if violations[index]
                    else Color.Black
                )
                for stair_index in range(tread_count + 1):
                    add_label(
                        stair_x,
                        stair_z,
                        riser_height,
                        (
                            tread_depth
                            if stair_index < tread_count
                            else row_pitch
                        ),
                        label_color,
                        label_text_color
                    )
                    stair_z += riser_height
                    if stair_index < tread_count:
                        stair_x += tread_depth
                continue

            add_label(
                x_values[index - 1],
                base_z_values[index - 1],
                riser_values[index],
                row_pitch,
                (
                    PREVIEW_WARNING
                    if violations[index]
                    else PREVIEW_FLOOR
                ),
                Color.White if violations[index] else Color.Black
            )

    for balcony_result in balcony_results:
        if not balcony_result_is_displayable(balcony_result):
            continue
        x_values = balcony_result["x_values"]
        base_z_values = balcony_result["base_z_values"]
        riser_values = balcony_result["riser_to_next_values"]
        for index in range(len(x_values) - 1):
            add_label(
                x_values[index],
                base_z_values[index],
                riser_values[index],
                x_values[index + 1] - x_values[index],
                PREVIEW_WARNING,
                Color.White
            )

    return labels


def build_section_height_dimension_preview(
    stage_point,
    audience_direction,
    params,
    stalls_result,
    balcony_results,
    auditorium_ceiling_z,
    rear_wall_x,
    mm_scale
):
    """Build preview-only outer height dimensions for seating tiers."""
    valid_balconies = [
        result
        for result in balcony_results
        if balcony_result_is_displayable(result)
    ]

    levels = [
        {
            "source_x": rear_wall_x,
            "z": auditorium_ceiling_z,
        }
    ]
    for balcony_result in reversed(valid_balconies):
        levels.extend(
            (
                {
                    "source_x": (
                        balcony_result["x_values"][-1]
                        + params["aisle_width"]
                    ),
                    "z": balcony_result["base_z_values"][-1],
                },
                {
                    "source_x": balcony_result[
                        "railing_front_x"
                    ],
                    "z": balcony_result["base_z_values"][0],
                },
            )
        )

    levels.extend(
        (
            {
                "source_x": (
                    stalls_result["x_values"][-1]
                    + params["aisle_width"]
                ),
                "z": stalls_result["base_z_values"][-1],
            },
            {
                "source_x": (
                    stalls_result["x_values"][0]
                    - params["row_pitch"]
                ),
                "z": stalls_result["base_z_values"][0],
            },
        )
    )

    dimension_offset = max(
        900.0,
        params["aisle_width"] * 0.75
    )
    dimension_x = max(
        [rear_wall_x]
        + [level["source_x"] for level in levels]
    ) + dimension_offset

    curves = []
    labels = []
    for level in levels:
        extension_start = point_at(
            stage_point,
            audience_direction,
            level["source_x"],
            level["z"],
            mm_scale
        )
        extension_end = point_at(
            stage_point,
            audience_direction,
            dimension_x,
            level["z"],
            mm_scale
        )
        curves.append(
            (
                line_curve(extension_start, extension_end),
                PREVIEW_SECTION_DIMENSION,
                1,
            )
        )

    for index in range(len(levels) - 1):
        upper_z = levels[index]["z"]
        lower_z = levels[index + 1]["z"]
        upper_point = point_at(
            stage_point,
            audience_direction,
            dimension_x,
            upper_z,
            mm_scale
        )
        lower_point = point_at(
            stage_point,
            audience_direction,
            dimension_x,
            lower_z,
            mm_scale
        )
        curves.append(
            (
                line_curve(upper_point, lower_point),
                PREVIEW_SECTION_DIMENSION,
                1,
            )
        )
        label_point = point_at(
            stage_point,
            audience_direction,
            dimension_x + 120.0,
            (upper_z + lower_z) * 0.5,
            mm_scale
        )
        labels.append(
            (
                label_point,
                "{0}  {1}".format(
                    index + 1,
                    format_section_height_dimension(
                        abs(upper_z - lower_z)
                    )
                ),
                PREVIEW_SECTION_DIMENSION,
                Color.Black,
            )
        )

    return curves, labels
