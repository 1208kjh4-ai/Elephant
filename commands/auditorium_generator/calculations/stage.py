# -*- coding: utf-8 -*-
"""Pure proscenium and stage-section calculations."""


STAGE_EQUIPMENT_CLEARANCE = 2000.0

DEFAULT_OPENING_HEIGHT = 6000.0

MIN_OPENING_HEIGHT = 3000.0

STAGE_TYPE_PROSCENIUM = "proscenium"

STAGE_TYPE_OPEN_PODIUM = "open_podium"

STAGE_TYPES = (
    STAGE_TYPE_PROSCENIUM,
    STAGE_TYPE_OPEN_PODIUM,
)


def _is_finite_number(value):
    """Return finite-number status without relying on math.isfinite()."""
    numeric_value = float(value)
    return (
        numeric_value == numeric_value
        and numeric_value != float("inf")
        and numeric_value != float("-inf")
    )


def is_proscenium_stage(params):
    """Return True when the flytower/proscenium envelope is enabled."""
    return params.get(
        "stage_type",
        STAGE_TYPE_PROSCENIUM,
    ) == STAGE_TYPE_PROSCENIUM


def validate_stage_reference_dimensions(opening_width_mm, opening_height_mm):
    """Validate the editable PW/PH values shared by every stage type."""
    if not _is_finite_number(opening_width_mm):
        raise ValueError("Reference width PW must be a finite number.")
    if not _is_finite_number(opening_height_mm):
        raise ValueError("Reference height PH must be a finite number.")
    if opening_width_mm <= 0.0:
        raise ValueError("Reference width PW must be greater than zero.")
    if opening_height_mm < MIN_OPENING_HEIGHT:
        raise ValueError(
            "Reference height PH must be at least {0:,.0f} mm."
            .format(MIN_OPENING_HEIGHT)
        )


def calculated_proscenium_defaults(opening_width_mm, opening_height_mm):
    """
    Return the initial proscenium stage-space dimensions in millimeters.

    The source document defines the main-stage width as PW + 8 m. The
    requested initial depth rule is PW * 1.2. Optional stage spaces start
    enabled and receive the same calculated dimensions for later editing.
    """
    calculated_width = opening_width_mm + 8000.0
    calculated_depth = opening_width_mm * 1.2
    calculated_main_height = (
        opening_height_mm * 3.0 + STAGE_EQUIPMENT_CLEARANCE
    )
    calculated_aux_height = (
        opening_height_mm + STAGE_EQUIPMENT_CLEARANCE
    )
    calculated_understage_depth = (
        opening_height_mm + STAGE_EQUIPMENT_CLEARANCE
    )
    return {
        "stage_preview_mode": "section_2d",
        "main_stage_width": calculated_width,
        "main_stage_depth": calculated_depth,
        "main_stage_height": calculated_main_height,
        "right_stage_enabled": True,
        "right_stage_width": calculated_width,
        "right_stage_depth": calculated_depth,
        "right_stage_height": calculated_aux_height,
        "left_stage_enabled": True,
        "left_stage_width": calculated_width,
        "left_stage_depth": calculated_depth,
        "left_stage_height": calculated_aux_height,
        "rear_stage_enabled": True,
        "rear_stage_width": calculated_width,
        "rear_stage_depth": calculated_depth,
        "rear_stage_height": calculated_aux_height,
        "understage_enabled": True,
        "understage_depth": calculated_understage_depth,
    }


def validate_proscenium_params(params, opening_width_mm):
    """Validate editable stage-space dimensions without changing them."""
    if params.get("stage_type", STAGE_TYPE_PROSCENIUM) not in STAGE_TYPES:
        raise ValueError("Choose a valid stage type.")

    if not is_proscenium_stage(params):
        if params["main_stage_width"] <= 0.0:
            raise ValueError(
                "Main stage width must be greater than zero."
            )
        if params["main_stage_depth"] <= 0.0:
            raise ValueError(
                "Main stage depth must be greater than zero."
            )
        if params["stage_preview_mode"] not in (
            "section_2d",
            "space_3d",
        ):
            raise ValueError("Choose a valid stage preview mode.")
        if (
            params["understage_enabled"]
            and params["understage_depth"]
            <= STAGE_EQUIPMENT_CLEARANCE
        ):
            raise ValueError(
                "Understage depth must be greater than 2,000 mm."
            )
        return

    if params["main_stage_width"] <= 0.0:
        raise ValueError("주무대 폭은 0보다 커야 합니다.")
    if params["main_stage_depth"] <= 0.0:
        raise ValueError("주무대 깊이는 0보다 커야 합니다.")
    if params["main_stage_height"] <= STAGE_EQUIPMENT_CLEARANCE:
        raise ValueError("주무대 높이는 2,000 mm보다 커야 합니다.")
    if params["stage_preview_mode"] not in ("section_2d", "space_3d"):
        raise ValueError("무대 프리뷰 방식을 다시 선택해 주세요.")

    optional_stages = (
        ("오른무대", "right"),
        ("왼무대", "left"),
        ("뒷무대", "rear"),
    )
    for label, prefix in optional_stages:
        if not params[prefix + "_stage_enabled"]:
            continue
        if params[prefix + "_stage_width"] <= 0.0:
            raise ValueError("{0} 폭은 0보다 커야 합니다.".format(label))
        if params[prefix + "_stage_depth"] <= 0.0:
            raise ValueError("{0} 깊이는 0보다 커야 합니다.".format(label))
        if (
            params[prefix + "_stage_height"]
            <= STAGE_EQUIPMENT_CLEARANCE
        ):
            raise ValueError(
                "{0} 높이는 2,000 mm보다 커야 합니다.".format(label)
            )

    if params["understage_enabled"]:
        if params["understage_depth"] <= STAGE_EQUIPMENT_CLEARANCE:
            raise ValueError("하부무대 Z 깊이는 2,000 mm보다 커야 합니다.")


def calculate_stage_section_dimensions(params, opening_height_mm):
    """Return editable stage and PH-based auditorium levels in millimeters."""
    ph = opening_height_mm
    understage_depth = params["understage_depth"]
    return {
        "ph": ph,
        "main_grid_z": (
            params["main_stage_height"] - STAGE_EQUIPMENT_CLEARANCE
        ),
        "main_tower_top_z": params["main_stage_height"],
        "right_grid_z": (
            params["right_stage_height"] - STAGE_EQUIPMENT_CLEARANCE
        ),
        "right_top_z": params["right_stage_height"],
        "left_grid_z": (
            params["left_stage_height"] - STAGE_EQUIPMENT_CLEARANCE
        ),
        "left_top_z": params["left_stage_height"],
        "rear_grid_z": (
            params["rear_stage_height"] - STAGE_EQUIPMENT_CLEARANCE
        ),
        "rear_top_z": params["rear_stage_height"],
        "clearance_grid_z": ph,
        "clearance_top_z": ph + STAGE_EQUIPMENT_CLEARANCE,
        "understage_floor_z": (
            -understage_depth + STAGE_EQUIPMENT_CLEARANCE
        ),
        "understage_bottom_z": -understage_depth,
        "auditorium_ceiling_z": ph * 2.0,
    }
