# -*- coding: utf-8 -*-
"""Pure stalls, balcony, sightline, and interpolation calculations."""

import math

from ..constants import (
    AISLE_STAIR_TARGET_RISER_HEIGHT,
    BALCONY_TIER_KEY_MAPS,
    CHAIR_FRONT_X,
    CHAIR_SIGHT_POINT_X,
    CHAIR_TOP_Z,
    MAX_BALCONY_ROW_COUNT,
)


def is_finite_number(value):
    """Return finite-number status across Rhino Python runtimes."""
    try:
        number = float(value)
    except Exception:
        return False
    return not math.isnan(number) and not math.isinf(number)


def ceil_to_integer_mm(value):
    """
    Round a millimeter value upward only when it has a fractional part.

    Floating-point noise close to an integer is suppressed so that
    173.00000000001 does not become 174.
    """
    nearest = round(value)
    if abs(value - nearest) <= 1e-8:
        return float(nearest)
    return float(math.ceil(value))


def calculate_actual_sightline_status(
    eye_x_values,
    eye_z_values,
    sight_target_z,
    required_clearance
):
    """Return actual vertical clearance and violations for each rear row."""
    row_count = len(eye_x_values)
    clearance_values = [None] * row_count
    violations = [False] * row_count

    for index in range(1, row_count):
        current_eye_x = eye_x_values[index]
        if current_eye_x <= 1e-12:
            clearance_values[index] = float("-inf")
            violations[index] = True
            continue

        line_z_at_previous_eye = (
            sight_target_z
            + (eye_x_values[index - 1] / current_eye_x)
            * (eye_z_values[index] - sight_target_z)
        )
        actual_clearance = (
            line_z_at_previous_eye - eye_z_values[index - 1]
        )
        clearance_values[index] = actual_clearance
        violations[index] = (
            actual_clearance < required_clearance - 1e-8
        )

    return clearance_values, violations


def validate_section_rise_target(z_values, target_rise, section_label):
    """Validate and normalize a requested non-negative total rise."""
    try:
        target = float(target_rise)
    except Exception:
        raise ValueError(
            "{0} 목표 상승 높이를 숫자로 입력해 주세요.".format(
                section_label
            )
        )

    if math.isnan(target) or math.isinf(target) or target < 0.0:
        raise ValueError(
            "{0} 목표 상승 높이는 0 이상의 유한한 값이어야 합니다.".format(
                section_label
            )
        )
    if len(z_values) < 2:
        raise ValueError(
            "{0}은 두 열 이상일 때만 보간할 수 있습니다.".format(
                section_label
            )
        )
    if not all(is_finite_number(value) for value in z_values):
        raise ValueError(
            "{0}의 기존 플랫폼 높이에 유효하지 않은 값이 있습니다.".format(
                section_label
            )
        )

    current_rise = z_values[-1] - z_values[0]
    if not is_finite_number(current_rise) or current_rise <= 1e-12:
        raise ValueError(
            "{0}의 현재 상승 높이가 0이어서 보간할 수 없습니다.".format(
                section_label
            )
        )

    return target, current_rise


def interpolate_front_anchored_z_values(
    z_values,
    target_rise,
    section_label
):
    """Scale tier heights while fixing the first platform."""
    target, current_rise = validate_section_rise_target(
        z_values,
        target_rise,
        section_label
    )
    first_z = z_values[0]
    interpolated = [
        first_z
        + target * ((z_value - first_z) / current_rise)
        for z_value in z_values
    ]
    interpolated[0] = first_z
    interpolated[-1] = first_z + target
    if (
        not all(is_finite_number(value) for value in interpolated)
        or abs(
            (interpolated[-1] - interpolated[0]) - target
        ) > max(1e-8, abs(target) * 1e-12)
    ):
        raise ValueError(
            "{0} 목표 상승 높이를 수치적으로 표현할 수 없습니다.".format(
                section_label
            )
        )
    return interpolated, current_rise


def interpolate_rear_anchored_z_values(
    z_values,
    target_rise,
    section_label
):
    """Scale tier heights while fixing the last platform."""
    target, current_rise = validate_section_rise_target(
        z_values,
        target_rise,
        section_label
    )
    last_z = z_values[-1]
    interpolated = [
        last_z
        - target * ((last_z - z_value) / current_rise)
        for z_value in z_values
    ]
    interpolated[0] = last_z - target
    interpolated[-1] = last_z
    if (
        not all(is_finite_number(value) for value in interpolated)
        or abs(
            (interpolated[-1] - interpolated[0]) - target
        ) > max(1e-8, abs(target) * 1e-12)
    ):
        raise ValueError(
            "{0} 목표 상승 높이를 수치적으로 표현할 수 없습니다.".format(
                section_label
            )
        )
    return interpolated, current_rise


def rebuild_stalls_vertical_fields(params, result, base_z_values):
    """Recompute stalls fields that depend on platform elevations."""
    rebuilt = dict(result)
    row_count = len(base_z_values)
    pitch = params["row_pitch"]
    sight_point_z = params["sight_point_z"]
    maximum_slope = 1.0 / params["max_slope_denominator"]

    new_base_z_values = list(base_z_values)
    eye_z_values = [
        z_value + sight_point_z for z_value in new_base_z_values
    ]
    riser_values = [0.0] * row_count
    slope_values = [0.0] * row_count
    slope_violations = [False] * row_count

    for index in range(1, row_count):
        riser = new_base_z_values[index] - new_base_z_values[index - 1]
        if riser < -1e-8:
            raise ValueError(
                "일반 객석 보간 결과에서 뒤쪽 단이 앞쪽보다 낮아졌습니다."
            )
        riser = max(0.0, riser)
        slope = riser / pitch
        riser_values[index] = riser
        slope_values[index] = slope
        slope_violations[index] = slope > maximum_slope + 1e-10

    actual_clearances, sightline_violations = (
        calculate_actual_sightline_status(
            result["eye_x_values"],
            eye_z_values,
            params["stage_sight_point_z"],
            params["sight_clearance"]
        )
    )
    combined_violations = [
        slope_violations[index] or sightline_violations[index]
        for index in range(row_count)
    ]

    stair_tread_counts = result["aisle_stair_tread_counts"]
    aisle_before_values = result["aisle_before_values"]
    stair_riser_heights = [0.0] * row_count
    for index in range(1, row_count):
        if aisle_before_values[index] and riser_values[index] > 1e-8:
            stair_riser_heights[index] = (
                riser_values[index] / (stair_tread_counts[index] + 1)
            )

    rebuilt["maximum_slope"] = maximum_slope
    rebuilt["base_z_values"] = new_base_z_values
    rebuilt["eye_z_values"] = eye_z_values
    rebuilt["riser_values"] = riser_values
    rebuilt["slope_values"] = slope_values
    rebuilt["slope_violations"] = slope_violations
    rebuilt["actual_sight_clearance_values"] = actual_clearances
    rebuilt["sightline_violations"] = sightline_violations
    rebuilt["violations"] = combined_violations
    rebuilt["aisle_stair_riser_heights"] = stair_riser_heights
    return rebuilt


def add_stalls_ceiling_validation(result, auditorium_ceiling_z):
    """Add per-row chair clearance checks against the auditorium ceiling."""
    if auditorium_ceiling_z is None:
        return result

    rebuilt = dict(result)
    highest_chair_z_values = [
        z_value + CHAIR_TOP_Z
        for z_value in result["base_z_values"]
    ]
    ceiling_clearance_values = [
        auditorium_ceiling_z - chair_z
        for chair_z in highest_chair_z_values
    ]
    ceiling_violations = [
        clearance < -1e-8
        for clearance in ceiling_clearance_values
    ]
    rebuilt["highest_chair_z"] = max(highest_chair_z_values)
    rebuilt["ceiling_clearance_values"] = ceiling_clearance_values
    rebuilt["ceiling_clearance"] = min(ceiling_clearance_values)
    rebuilt["ceiling_violations"] = ceiling_violations
    rebuilt["ceiling_violation"] = any(ceiling_violations)
    return rebuilt


def add_balcony_ceiling_validation(result, auditorium_ceiling_z):
    """Update one balcony's chair clearance against the final ceiling."""
    if result is None or auditorium_ceiling_z is None:
        return result

    rebuilt = dict(result)
    highest_chair_z = (
        max(result["base_z_values"]) + CHAIR_TOP_Z
    )
    ceiling_clearance = auditorium_ceiling_z - highest_chair_z
    rebuilt["highest_chair_z"] = highest_chair_z
    rebuilt["ceiling_clearance"] = ceiling_clearance
    rebuilt["ceiling_violation"] = ceiling_clearance < -1e-8
    return rebuilt


def apply_stalls_rise_interpolation(
    params,
    result,
    target_rise,
    auditorium_ceiling_z=None
):
    """Apply a front-anchored total-rise override to the stalls result."""
    if target_rise is None:
        return add_stalls_ceiling_validation(
            result,
            auditorium_ceiling_z
        )

    base_z_values, original_rise = interpolate_front_anchored_z_values(
        result["base_z_values"],
        target_rise,
        "일반 객석"
    )
    rebuilt = rebuild_stalls_vertical_fields(
        params,
        result,
        base_z_values
    )
    rebuilt["rise_interpolation_applied"] = True
    rebuilt["rise_interpolation_original"] = original_rise
    rebuilt["rise_interpolation_target"] = float(target_rise)
    return add_stalls_ceiling_validation(
        rebuilt,
        auditorium_ceiling_z
    )


def stalls_solver_signature(params):
    """Return only inputs that change the stalls X/Z sightline solution."""
    return (
        float(params["stage_height"]),
        float(params["first_row_distance"]),
        float(params["row_pitch"]),
        float(params["stage_sight_point_z"]),
        float(params["sight_point_z"]),
        float(params["sight_clearance"]),
        tuple(int(value) for value in params["row_group_counts"]),
        float(params["aisle_width"]),
        float(params["aisle_stair_tread_depth"]),
        str(params["floor_type"]),
    )


def balcony_solver_signature(params, tier_index):
    """Return only inputs that change one balcony tier's seat elevations."""
    tier_params = normalized_balcony_tier_params(params, tier_index)
    return (
        bool(tier_params["balcony_enabled"]),
        int(tier_params["balcony_row_count"]),
        float(tier_params["balcony_row_pitch"]),
        float(tier_params.get("balcony_longitudinal_offset", 0.0)),
        float(tier_params["balcony_last_platform_z"]),
        float(params.get("opening_height", 0.0)),
    )


def section_solver_signatures(params):
    return {
        "stalls": stalls_solver_signature(params),
        "balcony_1": balcony_solver_signature(params, 0),
        "balcony_2": balcony_solver_signature(params, 1),
    }


def balcony_result_is_displayable(result):
    """Return whether a balcony calculation produced previewable geometry."""
    return result is not None


def calculate_auditorium_ceiling(
    opening_height_mm,
    stalls_result,
    balcony_results,
    target_clear_height=None
):
    """
    Resolve the ceiling from the highest active tier's rear platform.

    A user target is a clear vertical interval from that platform. The
    resulting ceiling can never fall below the opening top.
    """
    active_result = stalls_result
    active_key = "stalls"
    active_label = "Stalls"
    for tier_index, balcony_result in enumerate(balcony_results):
        if not balcony_result_is_displayable(balcony_result):
            continue
        active_result = balcony_result
        active_key = "balcony_{0}".format(tier_index + 1)
        active_label = "Balcony {0}".format(tier_index + 1)

    reference_z = float(active_result["base_z_values"][-1])
    minimum_clear_height = max(
        0.0,
        float(opening_height_mm) - reference_z
    )

    if target_clear_height is None:
        formula_ceiling_z = float(opening_height_mm) * 2.0
        requested_clear_height = max(
            0.0,
            formula_ceiling_z - reference_z
        )
    else:
        if not is_finite_number(target_clear_height):
            raise ValueError(
                "Rear platform-to-ceiling height must be a finite "
                "number."
            )
        requested_clear_height = float(target_clear_height)
        if requested_clear_height < 0.0:
            requested_clear_height = 0.0

    actual_clear_height = max(
        requested_clear_height,
        minimum_clear_height
    )
    ceiling_z = reference_z + actual_clear_height
    # Preserve the exact opening-top datum at the clamp boundary.
    ceiling_z = max(ceiling_z, float(opening_height_mm))
    actual_clear_height = ceiling_z - reference_z

    return {
        "reference_tier_key": active_key,
        "reference_tier_label": active_label,
        "reference_platform_z": reference_z,
        "requested_clear_height": requested_clear_height,
        "minimum_clear_height": minimum_clear_height,
        "actual_clear_height": actual_clear_height,
        "ceiling_z": ceiling_z,
        "clamped_to_opening_top": (
            actual_clear_height
            > requested_clear_height + 1e-8
        ),
        "override_applied": target_clear_height is not None,
    }


def calculate_section(params):
    """
    Calculate all row positions in millimeters relative to the stage point.

    Vertical coordinate 0 = stage reference point / opening bottom midpoint.
    Horizontal coordinate 0 = stage reference point.
    """
    stage_height = params["stage_height"]
    first_distance = params["first_row_distance"]
    pitch = params["row_pitch"]
    stage_sight_point_z = params["stage_sight_point_z"]
    sight_point_z = params["sight_point_z"]
    clearance = params["sight_clearance"]
    row_count = params["row_count"]
    row_group_counts = params.get("row_group_counts", [row_count])
    aisle_width = params.get("aisle_width", 0.0)
    aisle_stair_tread_depth = params.get(
        "aisle_stair_tread_depth",
        300.0
    )
    denominator = params["max_slope_denominator"]
    stepped = params["floor_type"] == "stepped"

    if sum(row_group_counts) != row_count:
        raise ValueError("좌석 그룹 열 수와 전체 열 수가 일치하지 않습니다.")

    aisle_before_indices = set()
    accumulated_rows = 0
    for group_count in row_group_counts[:-1]:
        accumulated_rows += group_count
        aisle_before_indices.add(accumulated_rows)

    maximum_slope = 1.0 / denominator
    sight_target_z = stage_sight_point_z

    row_x_values = []
    eye_x_values = []
    base_z_values = []
    eye_z_values = []
    riser_values = [0.0]
    slope_values = [0.0]
    violations = [False]
    aisle_before_values = [False] * row_count
    aisle_stair_tread_counts = [0] * row_count
    aisle_stair_riser_heights = [0.0] * row_count
    aisle_stair_run_values = [0.0] * row_count

    # First Row Distance locates the stage-side start of the first platform.
    # The chair's rear-bottom origin sits at that platform's rear edge.
    first_row_x = first_distance + pitch
    first_eye_x = first_row_x + CHAIR_SIGHT_POINT_X
    first_base_z = -stage_height
    first_eye_z = first_base_z + sight_point_z

    row_x_values.append(first_row_x)
    eye_x_values.append(first_eye_x)
    base_z_values.append(first_base_z)
    eye_z_values.append(first_eye_z)

    accumulated_aisle_width = 0.0
    accumulated_stair_run = 0.0
    for index in range(1, row_count):
        aisle_before = index in aisle_before_indices
        if aisle_before:
            accumulated_aisle_width += aisle_width
            aisle_before_values[index] = True

        previous_eye_x = eye_x_values[index - 1]
        base_current_row_x = (
            first_distance
            + pitch * (index + 1)
            + accumulated_aisle_width
            + accumulated_stair_run
        )
        previous_eye_z = eye_z_values[index - 1]

        stair_tread_count = 0
        for stair_iteration in range(50):
            candidate_stair_run = (
                stair_tread_count * aisle_stair_tread_depth
                if stepped and aisle_before
                else 0.0
            )
            current_row_x = base_current_row_x + candidate_stair_run
            current_eye_x = current_row_x + CHAIR_SIGHT_POINT_X

            # The new sightline from the raised stage target must pass the
            # previous eye position plus the specified vertical clearance.
            target_height_at_previous_row = previous_eye_z + clearance
            ideal_eye_z = (
                sight_target_z
                + (current_eye_x / previous_eye_x)
                * (target_height_at_previous_row - sight_target_z)
            )
            ideal_base_z = ideal_eye_z - sight_point_z

            # Auditorium floors must not descend toward the rear.
            ideal_base_z = max(
                ideal_base_z,
                base_z_values[index - 1]
            )
            raw_riser = ideal_base_z - base_z_values[index - 1]

            if stepped:
                applied_riser = raw_riser
                current_base_z = (
                    base_z_values[index - 1] + applied_riser
                )
                current_eye_z = current_base_z + sight_point_z
            else:
                applied_riser = raw_riser
                current_base_z = ideal_base_z
                current_eye_z = current_base_z + sight_point_z

            if not (stepped and aisle_before):
                break

            if applied_riser <= 1e-8:
                updated_tread_count = 0
            else:
                # Positive-value half-up rounding avoids Python's
                # banker's-rounding behavior at .5.
                stair_riser_count = max(
                    1,
                    int(
                        math.floor(
                            applied_riser
                            / AISLE_STAIR_TARGET_RISER_HEIGHT
                            + 0.5
                        )
                    )
                )
                updated_tread_count = stair_riser_count - 1

            if updated_tread_count == stair_tread_count:
                break
            stair_tread_count = updated_tread_count
        else:
            raise ValueError(
                "통로 계단 수와 시야 계산이 안정된 값에 도달하지 못했습니다."
            )

        if stepped and aisle_before:
            stair_run = stair_tread_count * aisle_stair_tread_depth
            accumulated_stair_run += stair_run
            aisle_stair_tread_counts[index] = stair_tread_count
            aisle_stair_run_values[index] = stair_run
            if applied_riser > 1e-8:
                aisle_stair_riser_heights[index] = (
                    applied_riser / (stair_tread_count + 1)
                )

        slope = applied_riser / pitch
        violation = slope > maximum_slope + 1e-10

        row_x_values.append(current_row_x)
        eye_x_values.append(current_eye_x)
        base_z_values.append(current_base_z)
        eye_z_values.append(current_eye_z)
        riser_values.append(applied_riser)
        slope_values.append(slope)
        violations.append(violation)

    slope_violations = list(violations)
    actual_clearances, sightline_violations = (
        calculate_actual_sightline_status(
            eye_x_values,
            eye_z_values,
            sight_target_z,
            clearance
        )
    )
    combined_violations = [
        slope_violations[index] or sightline_violations[index]
        for index in range(row_count)
    ]

    return {
        "pitch": pitch,
        "maximum_slope": maximum_slope,
        "sight_target_z": sight_target_z,
        "x_values": row_x_values,
        "eye_x_values": eye_x_values,
        "base_z_values": base_z_values,
        "eye_z_values": eye_z_values,
        "riser_values": riser_values,
        "slope_values": slope_values,
        "slope_violations": slope_violations,
        "actual_sight_clearance_values": actual_clearances,
        "sightline_violations": sightline_violations,
        "violations": combined_violations,
        "aisle_before_values": aisle_before_values,
        "aisle_before_indices": sorted(aisle_before_indices),
        "aisle_stair_tread_counts": aisle_stair_tread_counts,
        "aisle_stair_riser_heights": aisle_stair_riser_heights,
        "aisle_stair_run_values": aisle_stair_run_values,
    }


def standard_balcony_railing_height(railing_t):
    """Return the supplied t-based balcony railing reference height."""
    return 800.0 if railing_t < 250.0 else 750.0


def balcony_height_from_stalls_rear(
    absolute_height,
    stalls_rear_z
):
    """Convert an internal stage-relative Z to the balcony UI datum."""
    return float(absolute_height) - float(stalls_rear_z)


def balcony_height_to_absolute(
    relative_height,
    stalls_rear_z
):
    """Convert a balcony UI height back to the internal stage datum."""
    return float(stalls_rear_z) + float(relative_height)


def normalized_balcony_tier_params(params, tier_index):
    """Map a stored balcony tier to the canonical calculation keys."""
    normalized = dict(params)
    key_map = BALCONY_TIER_KEY_MAPS[tier_index]
    for canonical_key, actual_key in key_map.items():
        if canonical_key == "balcony_longitudinal_offset":
            normalized[canonical_key] = params.get(actual_key, 0.0)
        else:
            normalized[canonical_key] = params[actual_key]
    return normalized


def balcony_rear_row_x(params, lower_result):
    """Return a tier rear-row X using the shared stalls datum."""
    reference_x = params.get(
        "balcony_rear_reference_x",
        lower_result["x_values"][-1]
    )
    offset = params.get("balcony_longitudinal_offset", 0.0)
    if not is_finite_number(reference_x) or not is_finite_number(offset):
        raise ValueError(
            "Balcony longitudinal offset must be a finite number."
        )
    return float(reference_x) + float(offset)


def calculate_balcony_spatial_max_rows(params, stalls_result):
    """Return the longest balcony that stays behind the stalls front limit."""
    rear_row_x = balcony_rear_row_x(params, stalls_result)
    pitch = params["balcony_row_pitch"]
    railing_t = params["balcony_railing_t"]
    railing_w = params["balcony_railing_w"]

    # The embedded chair origin is at its rear. Keep the actual chair front
    # behind the railing cap and the requested clear distance w.
    minimum_first_row_origin_x = (
        params["first_row_distance"]
        + railing_t
        + railing_w
        - CHAIR_FRONT_X
    )
    available_run = rear_row_x - minimum_first_row_origin_x
    if available_run < -1e-8:
        return 0
    return min(
        MAX_BALCONY_ROW_COUNT,
        max(1, int(math.floor(available_run / pitch)) + 1)
    )


def calculate_balcony_max_rows(
    params,
    stalls_result,
    opening_height_mm,
    tier_index=0
):
    """Return the longest balcony that also stays above its lower limit."""
    spatial_maximum = calculate_balcony_spatial_max_rows(
        params,
        stalls_result
    )
    for row_count in range(spatial_maximum, 0, -1):
        candidate_params = dict(params)
        candidate_params["balcony_enabled"] = True
        candidate_params["balcony_row_count"] = row_count
        candidate = calculate_balcony_section(
            candidate_params,
            stalls_result,
            opening_height_mm,
            include_maximum=False,
            tier_index=tier_index
        )
        if (
            not candidate["lower_limit_violation"]
            and not candidate["front_limit_violation"]
        ):
            return row_count
    return 0


def calculate_balcony_section(
    params,
    stalls_result,
    opening_height_mm,
    include_maximum=True,
    tier_index=0
):
    """Calculate a rear-anchored balcony backward toward the stage."""
    if not params.get("balcony_enabled", False):
        return None

    row_count = params["balcony_row_count"]
    pitch = params["balcony_row_pitch"]
    last_platform_z = params["balcony_last_platform_z"]
    sight_target_z = params["stage_sight_point_z"]
    sight_point_z = params["sight_point_z"]
    clearance = params["sight_clearance"]
    railing_t = params["balcony_railing_t"]
    railing_w = params["balcony_railing_w"]
    railing_h = params["balcony_railing_h"]

    rear_row_x = balcony_rear_row_x(params, stalls_result)
    row_x_values = [
        rear_row_x - pitch * (row_count - 1 - index)
        for index in range(row_count)
    ]
    eye_x_values = [
        row_x + CHAIR_SIGHT_POINT_X
        for row_x in row_x_values
    ]
    if eye_x_values[0] <= 0.0:
        raise ValueError(
            "발코니 첫 열 시각점은 무대 기준점보다 객석 방향에 "
            "있어야 합니다."
        )

    base_z_values = [0.0] * row_count
    eye_z_values = [0.0] * row_count
    riser_to_next_values = [0.0] * row_count
    slope_to_next_values = [0.0] * row_count

    base_z_values[-1] = last_platform_z
    eye_z_values[-1] = last_platform_z + sight_point_z

    for index in range(row_count - 2, -1, -1):
        current_index = index + 1
        ideal_previous_eye_z = (
            sight_target_z
            + (
                eye_x_values[index]
                / eye_x_values[current_index]
            )
            * (
                eye_z_values[current_index]
                - sight_target_z
            )
            - clearance
        )
        ideal_previous_base_z = (
            ideal_previous_eye_z - sight_point_z
        )
        ideal_previous_base_z = min(
            ideal_previous_base_z,
            base_z_values[current_index]
        )
        raw_riser = (
            base_z_values[current_index]
            - ideal_previous_base_z
        )
        applied_riser = raw_riser
        base_z_values[index] = (
            base_z_values[current_index] - applied_riser
        )
        eye_z_values[index] = (
            base_z_values[index] + sight_point_z
        )
        riser_to_next_values[index] = applied_riser
        slope_to_next_values[index] = applied_riser / pitch

    maximum_slope = max(slope_to_next_values)
    maximum_angle_degrees = math.degrees(math.atan(maximum_slope))
    first_chair_front_x = row_x_values[0] + CHAIR_FRONT_X
    railing_front_x = (
        first_chair_front_x - railing_w - railing_t
    )
    railing_rear_x = railing_front_x + railing_t
    railing_floor_z = base_z_values[0]
    railing_top_z = railing_floor_z + railing_h

    line_z_at_railing = (
        sight_target_z
        + (railing_front_x / eye_x_values[0])
        * (eye_z_values[0] - sight_target_z)
    )
    allowable_railing_h = line_z_at_railing - railing_floor_z
    railing_sight_collision = (
        railing_front_x <= 0.0
        or railing_h > allowable_railing_h + 1e-8
    )
    front_limit_violation = (
        railing_front_x < params["first_row_distance"] - 1e-8
    )

    lower_stalls_eye_x = stalls_result["eye_x_values"][-1]
    lower_stalls_eye_z = stalls_result["eye_z_values"][-1]

    def lower_limit_z_at(x_value):
        return (
            opening_height_mm
            + (x_value / lower_stalls_eye_x)
            * (lower_stalls_eye_z - opening_height_mm)
        )

    lower_limit_checks = [
        (
            railing_front_x,
            railing_floor_z,
            railing_floor_z - lower_limit_z_at(railing_front_x),
        )
    ]
    for row_x, base_z in zip(row_x_values, base_z_values):
        lower_limit_checks.append(
            (
                row_x,
                base_z,
                base_z - lower_limit_z_at(row_x),
            )
        )
    minimum_lower_limit_clearance = min(
        check[2] for check in lower_limit_checks
    )
    lower_limit_violation = (
        minimum_lower_limit_clearance < -1e-8
    )
    highest_chair_z = max(base_z_values) + CHAIR_TOP_Z
    auditorium_ceiling_z = opening_height_mm * 2.0
    ceiling_clearance = auditorium_ceiling_z - highest_chair_z
    ceiling_violation = ceiling_clearance < -1e-8
    maximum_rows = (
        calculate_balcony_max_rows(
            params,
            stalls_result,
            opening_height_mm,
            tier_index=tier_index
        )
        if include_maximum
        else None
    )
    actual_clearances, sightline_violations = (
        calculate_actual_sightline_status(
            eye_x_values,
            eye_z_values,
            sight_target_z,
            clearance
        )
    )
    clearance_to_next_values = actual_clearances[1:] + [None]
    valid_clearances = [
        value for value in actual_clearances if value is not None
    ]

    return {
        "tier_index": tier_index,
        "longitudinal_offset": float(
            params.get("balcony_longitudinal_offset", 0.0)
        ),
        "row_count": row_count,
        "maximum_rows": maximum_rows,
        "x_values": row_x_values,
        "eye_x_values": eye_x_values,
        "base_z_values": base_z_values,
        "eye_z_values": eye_z_values,
        "riser_to_next_values": riser_to_next_values,
        "slope_to_next_values": slope_to_next_values,
        "sightline_clearance_to_next_values": (
            clearance_to_next_values
        ),
        "sightline_violations": sightline_violations,
        "minimum_sightline_clearance": (
            min(valid_clearances) if valid_clearances else None
        ),
        "sightline_violation": any(sightline_violations),
        "maximum_angle_degrees": maximum_angle_degrees,
        "angle_violation": maximum_angle_degrees > 35.0 + 1e-8,
        "first_chair_front_x": first_chair_front_x,
        "railing_front_x": railing_front_x,
        "railing_rear_x": railing_rear_x,
        "railing_floor_z": railing_floor_z,
        "railing_top_z": railing_top_z,
        "standard_railing_h": standard_balcony_railing_height(
            railing_t
        ),
        "allowable_railing_h": allowable_railing_h,
        "railing_sight_collision": railing_sight_collision,
        "front_limit_violation": front_limit_violation,
        "lower_limit_start_x": 0.0,
        "lower_limit_start_z": opening_height_mm,
        "lower_limit_end_x": lower_stalls_eye_x,
        "lower_limit_end_z": lower_stalls_eye_z,
        "minimum_lower_limit_clearance": (
            minimum_lower_limit_clearance
        ),
        "lower_limit_violation": lower_limit_violation,
        "highest_chair_z": highest_chair_z,
        "ceiling_clearance": ceiling_clearance,
        "ceiling_violation": ceiling_violation,
    }


def rebuild_balcony_vertical_fields(
    params,
    result,
    lower_result,
    opening_height_mm,
    base_z_values
):
    """Recompute balcony validation fields after a rear-anchored edit."""
    rebuilt = dict(result)
    row_count = len(base_z_values)
    pitch = params["balcony_row_pitch"]
    sight_target_z = params["stage_sight_point_z"]
    sight_point_z = params["sight_point_z"]
    clearance = params["sight_clearance"]
    railing_t = params["balcony_railing_t"]
    railing_w = params["balcony_railing_w"]
    railing_h = params["balcony_railing_h"]
    row_x_values = result["x_values"]
    eye_x_values = result["eye_x_values"]
    new_base_z_values = list(base_z_values)
    eye_z_values = [
        z_value + sight_point_z for z_value in new_base_z_values
    ]
    riser_to_next_values = [0.0] * row_count
    slope_to_next_values = [0.0] * row_count

    for index in range(row_count - 1):
        riser = new_base_z_values[index + 1] - new_base_z_values[index]
        if riser < -1e-8:
            raise ValueError(
                "발코니 보간 결과에서 뒤쪽 단이 앞쪽보다 낮아졌습니다."
            )
        riser = max(0.0, riser)
        run = row_x_values[index + 1] - row_x_values[index]
        if run <= 1e-12:
            raise ValueError("발코니 열 간격이 유효하지 않습니다.")
        riser_to_next_values[index] = riser
        slope_to_next_values[index] = riser / run

    maximum_slope = max(slope_to_next_values)
    maximum_angle_degrees = math.degrees(math.atan(maximum_slope))
    first_chair_front_x = row_x_values[0] + CHAIR_FRONT_X
    railing_front_x = first_chair_front_x - railing_w - railing_t
    railing_rear_x = railing_front_x + railing_t
    railing_floor_z = new_base_z_values[0]
    railing_top_z = railing_floor_z + railing_h
    line_z_at_railing = (
        sight_target_z
        + (railing_front_x / eye_x_values[0])
        * (eye_z_values[0] - sight_target_z)
    )
    allowable_railing_h = line_z_at_railing - railing_floor_z
    railing_sight_collision = (
        railing_front_x <= 0.0
        or railing_h > allowable_railing_h + 1e-8
    )
    front_limit_violation = (
        railing_front_x < params["first_row_distance"] - 1e-8
    )

    lower_eye_x = lower_result["eye_x_values"][-1]
    lower_eye_z = lower_result["eye_z_values"][-1]

    def lower_limit_z_at(x_value):
        return (
            opening_height_mm
            + (x_value / lower_eye_x)
            * (lower_eye_z - opening_height_mm)
        )

    lower_limit_checks = [
        (
            railing_front_x,
            railing_floor_z,
            railing_floor_z - lower_limit_z_at(railing_front_x),
        )
    ]
    for row_x, base_z in zip(row_x_values, new_base_z_values):
        lower_limit_checks.append(
            (row_x, base_z, base_z - lower_limit_z_at(row_x))
        )
    minimum_lower_limit_clearance = min(
        check[2] for check in lower_limit_checks
    )
    lower_limit_violation = minimum_lower_limit_clearance < -1e-8
    highest_chair_z = max(new_base_z_values) + CHAIR_TOP_Z
    auditorium_ceiling_z = opening_height_mm * 2.0
    ceiling_clearance = auditorium_ceiling_z - highest_chair_z
    ceiling_violation = ceiling_clearance < -1e-8

    actual_clearances, sightline_violations = (
        calculate_actual_sightline_status(
            eye_x_values,
            eye_z_values,
            sight_target_z,
            clearance
        )
    )
    valid_clearances = [
        value for value in actual_clearances if value is not None
    ]

    rebuilt["base_z_values"] = new_base_z_values
    rebuilt["eye_z_values"] = eye_z_values
    rebuilt["riser_to_next_values"] = riser_to_next_values
    rebuilt["slope_to_next_values"] = slope_to_next_values
    rebuilt["sightline_clearance_to_next_values"] = (
        actual_clearances[1:] + [None]
    )
    rebuilt["sightline_violations"] = sightline_violations
    rebuilt["minimum_sightline_clearance"] = (
        min(valid_clearances) if valid_clearances else None
    )
    rebuilt["sightline_violation"] = any(sightline_violations)
    rebuilt["maximum_angle_degrees"] = maximum_angle_degrees
    rebuilt["angle_violation"] = maximum_angle_degrees > 35.0 + 1e-8
    rebuilt["first_chair_front_x"] = first_chair_front_x
    rebuilt["railing_front_x"] = railing_front_x
    rebuilt["railing_rear_x"] = railing_rear_x
    rebuilt["railing_floor_z"] = railing_floor_z
    rebuilt["railing_top_z"] = railing_top_z
    rebuilt["standard_railing_h"] = standard_balcony_railing_height(
        railing_t
    )
    rebuilt["allowable_railing_h"] = allowable_railing_h
    rebuilt["railing_sight_collision"] = railing_sight_collision
    rebuilt["front_limit_violation"] = front_limit_violation
    rebuilt["lower_limit_start_x"] = 0.0
    rebuilt["lower_limit_start_z"] = opening_height_mm
    rebuilt["lower_limit_end_x"] = lower_eye_x
    rebuilt["lower_limit_end_z"] = lower_eye_z
    rebuilt["minimum_lower_limit_clearance"] = (
        minimum_lower_limit_clearance
    )
    rebuilt["lower_limit_violation"] = lower_limit_violation
    rebuilt["highest_chair_z"] = highest_chair_z
    rebuilt["ceiling_clearance"] = ceiling_clearance
    rebuilt["ceiling_violation"] = ceiling_violation
    return rebuilt


def apply_balcony_rise_interpolation(
    params,
    result,
    lower_result,
    opening_height_mm,
    target_rise
):
    """Apply a rear-anchored total-rise override to one balcony tier."""
    if result is None or target_rise is None:
        return result

    tier_label = "발코니 {0}".format(result["tier_index"] + 1)
    base_z_values, original_rise = interpolate_rear_anchored_z_values(
        result["base_z_values"],
        target_rise,
        tier_label
    )
    rebuilt = rebuild_balcony_vertical_fields(
        params,
        result,
        lower_result,
        opening_height_mm,
        base_z_values
    )
    rebuilt["rise_interpolation_applied"] = True
    rebuilt["rise_interpolation_original"] = original_rise
    rebuilt["rise_interpolation_target"] = float(target_rise)
    return rebuilt
