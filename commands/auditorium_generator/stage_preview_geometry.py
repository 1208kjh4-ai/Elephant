# -*- coding: utf-8 -*-
"""Rhino curve builders for proscenium and stage previews."""

from .calculations.stage import is_proscenium_stage
from .preview_palette import (
    PREVIEW_AUX_STAGE,
    PREVIEW_FLOOR,
    PREVIEW_GRID,
    PREVIEW_MAIN_STAGE,
    PREVIEW_ORCHESTRA_PIT,
    PREVIEW_STAGE_APRON,
    PREVIEW_STAGE_CLEARANCE,
    PREVIEW_STAGE_SECTION,
    PREVIEW_UNDERSTAGE,
)
from .rhino_primitives import (
    build_plan_rectangle,
    get_stage_directions,
    line_curve,
    point_at,
    stage_space_point,
)


SIDE_STAGE_CLEARANCE = 2000.0

def calculate_proscenium_space_layout(params):
    """Return shared plan bounds for every active proscenium space."""
    main_width = params["main_stage_width"]
    main_depth = params["main_stage_depth"]
    half_main_width = main_width * 0.5

    spaces = [
        {
            "name": "MainStage",
            "plan_color": PREVIEW_MAIN_STAGE,
            "section_type": "main",
            "height_group": "main",
            "min_x": -half_main_width,
            "max_x": half_main_width,
            "min_y": 0.0,
            "max_y": main_depth,
        },
    ]

    if not is_proscenium_stage(params):
        return spaces

    spaces.extend(
        [
            {
                "name": "RightStageClearance",
                "plan_color": PREVIEW_STAGE_CLEARANCE,
                "section_type": "aux",
                "height_group": "clearance",
                "min_x": half_main_width,
                "max_x": half_main_width + SIDE_STAGE_CLEARANCE,
                "min_y": 0.0,
                "max_y": main_depth,
            },
            {
                "name": "LeftStageClearance",
                "plan_color": PREVIEW_STAGE_CLEARANCE,
                "section_type": "aux",
                "height_group": "clearance",
                "min_x": -half_main_width - SIDE_STAGE_CLEARANCE,
                "max_x": -half_main_width,
                "min_y": 0.0,
                "max_y": main_depth,
            },
        ]
    )

    if params["right_stage_enabled"]:
        spaces.append(
            {
                "name": "RightStage",
                "plan_color": PREVIEW_AUX_STAGE,
                "section_type": "aux",
                "height_group": "right",
                "min_x": half_main_width + SIDE_STAGE_CLEARANCE,
                "max_x": (
                    half_main_width
                    + SIDE_STAGE_CLEARANCE
                    + params["right_stage_width"]
                ),
                "min_y": 0.0,
                "max_y": params["right_stage_depth"],
            }
        )

    if params["left_stage_enabled"]:
        spaces.append(
            {
                "name": "LeftStage",
                "plan_color": PREVIEW_AUX_STAGE,
                "section_type": "aux",
                "height_group": "left",
                "min_x": (
                    -half_main_width
                    - SIDE_STAGE_CLEARANCE
                    - params["left_stage_width"]
                ),
                "max_x": -half_main_width - SIDE_STAGE_CLEARANCE,
                "min_y": 0.0,
                "max_y": params["left_stage_depth"],
            }
        )

    if params["rear_stage_enabled"]:
        half_rear_width = params["rear_stage_width"] * 0.5
        spaces.append(
            {
                "name": "RearStage",
                "plan_color": PREVIEW_AUX_STAGE,
                "section_type": "aux",
                "height_group": "rear",
                "min_x": -half_rear_width,
                "max_x": half_rear_width,
                "min_y": main_depth,
                "max_y": main_depth + params["rear_stage_depth"],
            }
        )

    return spaces


def build_proscenium_plan_curves(
    stage_point,
    audience_direction,
    params,
    mm_scale
):
    """
    Build main, clearance, side and rear stage-space plan outlines.

    Stage right/left follow the audience viewpoint while facing the stage.
    The main stage front edge lies on the proscenium opening plane.
    """
    stage_right_direction, stage_back_direction = get_stage_directions(
        audience_direction
    )

    stage_curves = []
    for space in calculate_proscenium_space_layout(params):
        curve = build_plan_rectangle(
            stage_point,
            stage_right_direction,
            stage_back_direction,
            space["min_x"],
            space["max_x"],
            space["min_y"],
            space["max_y"],
            mm_scale
        )
        stage_curves.append(
            (curve, space["plan_color"], space["name"] + "Plan")
        )

    return stage_curves


def build_proscenium_opening_frame_curves(
    stage_point,
    audience_direction,
    params,
    opening_width_mm,
    opening_height_mm,
    mm_scale
):
    """Build the editable PW x PH opening frame in proscenium mode."""
    if not is_proscenium_stage(params):
        return []

    audience_view_right, stage_back_direction = get_stage_directions(
        audience_direction
    )
    half_width = opening_width_mm * 0.5

    left_bottom = stage_space_point(
        stage_point,
        audience_view_right,
        stage_back_direction,
        -half_width,
        0.0,
        0.0,
        mm_scale
    )
    right_bottom = stage_space_point(
        stage_point,
        audience_view_right,
        stage_back_direction,
        half_width,
        0.0,
        0.0,
        mm_scale
    )
    left_top = stage_space_point(
        stage_point,
        audience_view_right,
        stage_back_direction,
        -half_width,
        0.0,
        opening_height_mm,
        mm_scale
    )
    right_top = stage_space_point(
        stage_point,
        audience_view_right,
        stage_back_direction,
        half_width,
        0.0,
        opening_height_mm,
        mm_scale
    )

    return [
        (
            line_curve(left_bottom, right_bottom),
            PREVIEW_STAGE_SECTION,
            "ProsceniumOpeningBottom",
        ),
        (
            line_curve(left_top, right_top),
            PREVIEW_STAGE_SECTION,
            "ProsceniumOpeningTop",
        ),
        (
            line_curve(left_bottom, left_top),
            PREVIEW_STAGE_SECTION,
            "ProsceniumOpeningLeft",
        ),
        (
            line_curve(right_bottom, right_top),
            PREVIEW_STAGE_SECTION,
            "ProsceniumOpeningRight",
        ),
    ]


def build_stage_space_3d_curves(
    stage_point,
    audience_direction,
    params,
    section_dimensions,
    mm_scale
):
    """Build stage volume, grid and understage wireframe curves."""
    stage_right_direction, stage_back_direction = get_stage_directions(
        audience_direction
    )
    spaces = calculate_proscenium_space_layout(params)
    section_curves = []

    upper_spaces = (
        spaces
        if is_proscenium_stage(params)
        else ()
    )
    for space in upper_spaces:
        height_group = space["height_group"]
        if height_group == "main":
            top_z = section_dimensions["main_tower_top_z"]
            grid_z = section_dimensions["main_grid_z"]
            section_name = "MainFlyTower"
        elif height_group == "clearance":
            top_z = section_dimensions["clearance_top_z"]
            grid_z = section_dimensions["clearance_grid_z"]
            section_name = space["name"] + "UpperSpace"
        else:
            top_z = section_dimensions[height_group + "_top_z"]
            grid_z = section_dimensions[height_group + "_grid_z"]
            section_name = space["name"] + "UpperSpace"

        top_curve = build_plan_rectangle(
            stage_point,
            stage_right_direction,
            stage_back_direction,
            space["min_x"],
            space["max_x"],
            space["min_y"],
            space["max_y"],
            mm_scale,
            top_z
        )
        grid_curve = build_plan_rectangle(
            stage_point,
            stage_right_direction,
            stage_back_direction,
            space["min_x"],
            space["max_x"],
            space["min_y"],
            space["max_y"],
            mm_scale,
            grid_z
        )
        section_curves.append(
            (top_curve, PREVIEW_STAGE_SECTION, section_name + "Top")
        )
        section_curves.append(
            (grid_curve, PREVIEW_GRID, section_name + "Grid")
        )

        corners = (
            (space["min_x"], space["min_y"]),
            (space["max_x"], space["min_y"]),
            (space["max_x"], space["max_y"]),
            (space["min_x"], space["max_y"]),
        )
        for x_mm, y_mm in corners:
            floor_point = stage_space_point(
                stage_point,
                stage_right_direction,
                stage_back_direction,
                x_mm,
                y_mm,
                0.0,
                mm_scale
            )
            top_point = stage_space_point(
                stage_point,
                stage_right_direction,
                stage_back_direction,
                x_mm,
                y_mm,
                top_z,
                mm_scale
            )
            section_curves.append(
                (
                    line_curve(floor_point, top_point),
                    PREVIEW_STAGE_SECTION,
                    section_name + "Edge",
                )
            )

    if not params["understage_enabled"]:
        return section_curves

    main_space = spaces[0]
    understage_floor_z = section_dimensions["understage_floor_z"]
    understage_bottom_z = section_dimensions["understage_bottom_z"]

    understage_floor = build_plan_rectangle(
        stage_point,
        stage_right_direction,
        stage_back_direction,
        main_space["min_x"],
        main_space["max_x"],
        main_space["min_y"],
        main_space["max_y"],
        mm_scale,
        understage_floor_z
    )
    understage_bottom = build_plan_rectangle(
        stage_point,
        stage_right_direction,
        stage_back_direction,
        main_space["min_x"],
        main_space["max_x"],
        main_space["min_y"],
        main_space["max_y"],
        mm_scale,
        understage_bottom_z
    )
    section_curves.append(
        (
            understage_floor,
            PREVIEW_GRID,
            "MainUnderstageEquipmentFloor",
        )
    )
    section_curves.append(
        (
            understage_bottom,
            PREVIEW_UNDERSTAGE,
            "MainUnderstageBottom",
        )
    )

    main_corners = (
        (main_space["min_x"], main_space["min_y"]),
        (main_space["max_x"], main_space["min_y"]),
        (main_space["max_x"], main_space["max_y"]),
        (main_space["min_x"], main_space["max_y"]),
    )
    for x_mm, y_mm in main_corners:
        stage_floor_point = stage_space_point(
            stage_point,
            stage_right_direction,
            stage_back_direction,
            x_mm,
            y_mm,
            0.0,
            mm_scale
        )
        bottom_point = stage_space_point(
            stage_point,
            stage_right_direction,
            stage_back_direction,
            x_mm,
            y_mm,
            understage_bottom_z,
            mm_scale
        )
        section_curves.append(
            (
                line_curve(stage_floor_point, bottom_point),
                PREVIEW_UNDERSTAGE,
                "MainUnderstageEdge",
            )
        )

    return section_curves


def build_stage_section_2d_curves(
    stage_point,
    audience_direction,
    params,
    section_dimensions,
    mm_scale
):
    """Build the central audience-main-rear-stage longitudinal section."""
    section_curves = []

    def section_point(x_mm, z_mm):
        return point_at(
            stage_point,
            audience_direction,
            x_mm,
            z_mm,
            mm_scale
        )

    def add_upper_profile(
        front_x,
        back_x,
        top_z,
        grid_z,
        prefix,
        floor_color
    ):
        floor_front = section_point(front_x, 0.0)
        floor_back = section_point(back_x, 0.0)
        top_front = section_point(front_x, top_z)
        top_back = section_point(back_x, top_z)
        grid_front = section_point(front_x, grid_z)
        grid_back = section_point(back_x, grid_z)

        section_curves.extend(
            [
                (
                    line_curve(floor_front, floor_back),
                    floor_color,
                    prefix + "Floor",
                ),
                (
                    line_curve(top_front, top_back),
                    PREVIEW_STAGE_SECTION,
                    prefix + "Top",
                ),
                (
                    line_curve(floor_front, top_front),
                    PREVIEW_STAGE_SECTION,
                    prefix + "FrontEdge",
                ),
                (
                    line_curve(floor_back, top_back),
                    PREVIEW_STAGE_SECTION,
                    prefix + "BackEdge",
                ),
                (
                    line_curve(grid_front, grid_back),
                    PREVIEW_GRID,
                    prefix + "Grid",
                ),
            ]
        )

    main_back_x = -params["main_stage_depth"]
    if is_proscenium_stage(params):
        add_upper_profile(
            0.0,
            main_back_x,
            section_dimensions["main_tower_top_z"],
            section_dimensions["main_grid_z"],
            "MainFlyTowerSection",
            PREVIEW_MAIN_STAGE
        )
        if params["rear_stage_enabled"]:
            rear_back_x = main_back_x - params["rear_stage_depth"]
            add_upper_profile(
                main_back_x,
                rear_back_x,
                section_dimensions["rear_top_z"],
                section_dimensions["rear_grid_z"],
                "RearStageSection",
                PREVIEW_AUX_STAGE
            )
    else:
        section_curves.append(
            (
                line_curve(
                    section_point(0.0, 0.0),
                    section_point(main_back_x, 0.0),
                ),
                PREVIEW_MAIN_STAGE,
                "MainStageSectionFloor",
            )
        )

    if params["understage_enabled"]:
        bottom_z = section_dimensions["understage_bottom_z"]
        equipment_floor_z = section_dimensions["understage_floor_z"]
        bottom_front = section_point(0.0, bottom_z)
        bottom_back = section_point(main_back_x, bottom_z)
        floor_front = section_point(0.0, 0.0)
        floor_back = section_point(main_back_x, 0.0)
        equipment_front = section_point(0.0, equipment_floor_z)
        equipment_back = section_point(
            main_back_x,
            equipment_floor_z
        )

        section_curves.extend(
            [
                (
                    line_curve(bottom_front, bottom_back),
                    PREVIEW_UNDERSTAGE,
                    "MainUnderstageSectionBottom",
                ),
                (
                    line_curve(floor_front, bottom_front),
                    PREVIEW_UNDERSTAGE,
                    "MainUnderstageSectionFrontEdge",
                ),
                (
                    line_curve(floor_back, bottom_back),
                    PREVIEW_UNDERSTAGE,
                    "MainUnderstageSectionBackEdge",
                ),
                (
                    line_curve(equipment_front, equipment_back),
                    PREVIEW_GRID,
                    "MainUnderstageSectionEquipmentFloor",
                ),
            ]
        )

    return section_curves


def build_stage_audience_transition_curves(
    stage_point,
    audience_direction,
    params,
    mm_scale
):
    """Build the apron and optional orchestra-pit central section."""
    stage_reference_x = params.get("stage_reference_x", 0.0)
    apron_x = (
        stage_reference_x + params["stage_apron_projection"]
    )
    platform_start_x = params["first_row_distance"]
    first_floor_z = -params["stage_height"]
    pit_depth = params["orchestra_pit_depth"]
    pit_floor_z = first_floor_z - pit_depth
    curves = []

    def section_point(x_mm, z_mm):
        return point_at(
            stage_point,
            audience_direction,
            x_mm,
            z_mm,
            mm_scale
        )

    stage_origin = section_point(stage_reference_x, 0.0)
    apron_end = section_point(apron_x, 0.0)
    if apron_x > 1e-8:
        curves.append(
            (
                line_curve(stage_origin, apron_end),
                PREVIEW_STAGE_APRON,
                "StageApronSection",
            )
        )

    if pit_depth > 1e-8:
        pit_front = section_point(apron_x, pit_floor_z)
        pit_rear = section_point(platform_start_x, pit_floor_z)
        first_platform = section_point(
            platform_start_x,
            first_floor_z
        )

        curves.append(
            (
                line_curve(apron_end, pit_front),
                PREVIEW_ORCHESTRA_PIT,
                "OrchestraPitFront",
            )
        )
        if platform_start_x - apron_x > 1e-8:
            curves.append(
                (
                    line_curve(pit_front, pit_rear),
                    PREVIEW_ORCHESTRA_PIT,
                    "OrchestraPitBottom",
                )
            )
        curves.append(
            (
                line_curve(pit_rear, first_platform),
                PREVIEW_ORCHESTRA_PIT,
                "OrchestraPitRear",
            )
        )
    else:
        apron_floor = section_point(apron_x, first_floor_z)
        first_platform = section_point(
            platform_start_x,
            first_floor_z
        )
        if abs(first_floor_z) > 1e-8:
            curves.append(
                (
                    line_curve(apron_end, apron_floor),
                    PREVIEW_STAGE_APRON,
                    "StageFrontSection",
                )
            )
        if platform_start_x - apron_x > 1e-8:
            curves.append(
                (
                    line_curve(apron_floor, first_platform),
                    PREVIEW_FLOOR,
                    "StageAudienceFloorSection",
                )
            )

    return curves
