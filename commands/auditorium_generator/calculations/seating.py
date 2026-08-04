# -*- coding: utf-8 -*-
"""Pure auditorium seat-layout and placement calculations."""

import math

from .sections import balcony_result_is_displayable


AUTO_SEAT_BLOCK = "a"
MAXIMUM_3D_CHAIR_COUNT = 10000
MAXIMUM_SEATS_PER_ROW = 500
_INTERVAL_TOLERANCE = 1e-9
# AuditoriumSeat.3dm uses an 80 mm shared armrest centered on each
# nominal seat-cell boundary. Keep half of it inside every row region.
_SHARED_ARMREST_WIDTH = 80.0
_SHARED_ARMREST_HALF_WIDTH = _SHARED_ARMREST_WIDTH * 0.5
try:
    _INTEGER_TYPES = (int, long)
except NameError:
    _INTEGER_TYPES = (int,)


def _is_finite_number(value):
    """Return finite-number status without requiring math.isfinite()."""
    try:
        number = float(value)
    except Exception:
        return False
    return not math.isnan(number) and not math.isinf(number)


def _normalize_lateral_intervals(row_lateral_intervals):
    """Validate, sort, and union one row's lateral intervals."""
    if row_lateral_intervals is None:
        raise ValueError("A custom-boundary row region is missing.")
    if isinstance(row_lateral_intervals, (str, bytes)):
        raise ValueError(
            "A row region must be a list of (left, right) intervals."
        )

    try:
        source_intervals = list(row_lateral_intervals)
    except Exception:
        raise ValueError(
            "A row region must be a list of (left, right) intervals."
        )

    normalized = []
    for interval_index, interval in enumerate(source_intervals):
        if isinstance(interval, (str, bytes)):
            raise ValueError(
                "Row interval {0} must contain left and right "
                "millimeter values.".format(interval_index + 1)
            )
        try:
            values = list(interval)
        except Exception:
            raise ValueError(
                "Row interval {0} must contain left and right "
                "millimeter values.".format(interval_index + 1)
            )
        if len(values) != 2:
            raise ValueError(
                "Row interval {0} must contain exactly two values."
                .format(interval_index + 1)
            )
        left, right = values
        if not _is_finite_number(left) or not _is_finite_number(right):
            raise ValueError(
                "Row interval {0} must contain finite values."
                .format(interval_index + 1)
            )
        left = float(left)
        right = float(right)
        if right - left <= _INTERVAL_TOLERANCE:
            raise ValueError(
                "Row interval {0} must have right greater than left."
                .format(interval_index + 1)
            )
        normalized.append((left, right))

    normalized.sort(key=lambda item: (item[0], item[1]))
    merged = []
    for left, right in normalized:
        if (
            merged
            and left <= merged[-1][1] + _INTERVAL_TOLERANCE
        ):
            merged[-1] = (
                merged[-1][0],
                max(merged[-1][1], right),
            )
        else:
            merged.append((left, right))
    return merged


def _usable_lateral_intervals(params, row_lateral_intervals):
    """Apply the side margin at every custom-boundary interval edge."""
    intervals = _normalize_lateral_intervals(row_lateral_intervals)
    if not intervals:
        return []

    try:
        side_margin = float(params["side_floor_margin"])
    except Exception:
        raise ValueError(
            "Custom-boundary seating requires a side floor margin."
        )
    if not _is_finite_number(side_margin) or side_margin < 0.0:
        raise ValueError(
            "The side floor margin must be a finite non-negative value."
        )

    usable = []
    for left, right in intervals:
        clipped_left = left + side_margin
        clipped_right = right - side_margin
        if clipped_right - clipped_left > _INTERVAL_TOLERANCE:
            usable.append((clipped_left, clipped_right))
    return usable


def _normalize_row_regions(row_regions, row_count):
    """Return validated row regions parallel to the generated seat rows."""
    if row_regions is None:
        raise ValueError("Custom-boundary row regions are missing.")
    if isinstance(row_regions, (str, bytes)):
        raise ValueError(
            "Custom-boundary row regions must be provided per row."
        )
    try:
        regions = list(row_regions)
    except Exception:
        raise ValueError(
            "Custom-boundary row regions must be provided per row."
        )
    if len(regions) != row_count:
        raise ValueError(
            "Custom-boundary row regions must contain exactly {0} "
            "row entr{1}; received {2}.".format(
                row_count,
                "y" if row_count == 1 else "ies",
                len(regions),
            )
        )
    return [
        _normalize_lateral_intervals(region)
        for region in regions
    ]


def _footprint_fits_interval(left, right, intervals):
    footprint_left = left - _SHARED_ARMREST_HALF_WIDTH
    footprint_right = right + _SHARED_ARMREST_HALF_WIDTH
    for interval_left, interval_right in intervals:
        if (
            footprint_left >= interval_left - _INTERVAL_TOLERANCE
            and footprint_right <= interval_right + _INTERVAL_TOLERANCE
        ):
            return True
    return False


def seat_blocks_have_auto(block_counts):
    return any(
        str(value).strip().lower() == AUTO_SEAT_BLOCK
        for value in block_counts
    )


def _normalize_seat_block_rule(block_values, source_label):
    """Return one validated row rule while preserving ``'a'`` tokens."""
    if isinstance(block_values, (str, bytes)):
        raise ValueError(
            "{0} must be a list of seat-block values.".format(
                source_label
            )
        )
    try:
        values = list(block_values)
    except Exception:
        raise ValueError(
            "{0} must be a list of seat-block values.".format(
                source_label
            )
        )

    normalized = []
    for value in values:
        if str(value).strip().lower() == AUTO_SEAT_BLOCK:
            normalized.append(AUTO_SEAT_BLOCK)
            continue
        try:
            count = int(value)
        except Exception:
            raise ValueError(
                "{0} contains an invalid seat-block value: {1}."
                .format(source_label, value)
            )
        if count < 0:
            raise ValueError(
                "{0} seat-block values cannot be negative."
                .format(source_label)
            )
        normalized.append(count)
    return normalized


def _row_rule_values(params, row_index=None, row_overrides=None):
    """Return ``(rule_values, is_override)`` for one zero-based row."""
    if row_overrides is not None:
        if (
            isinstance(row_overrides, (str, bytes))
            or not hasattr(row_overrides, "keys")
        ):
            raise ValueError("Row overrides must be a row-index mapping.")
        try:
            has_overrides = len(row_overrides) > 0
        except Exception:
            raise ValueError("Row overrides must be a row-index mapping.")
        if has_overrides and row_index is None:
            raise ValueError(
                "A row index is required when row overrides are supplied."
            )
        if row_index is not None:
            try:
                has_row_override = row_index in row_overrides
            except Exception:
                raise ValueError(
                    "Row overrides must be a row-index mapping."
                )
            if has_row_override:
                override_values = _normalize_seat_block_rule(
                    row_overrides[row_index],
                    "Row {0} override".format(row_index + 1),
                )
                default_values = _normalize_seat_block_rule(
                    params["seat_block_counts"],
                    "Default seat-block rule",
                )
                if (
                    override_values
                    and len(override_values) != len(default_values)
                ):
                    raise ValueError(
                        "Row {0} override must contain exactly {1} "
                        "seat blocks.".format(
                            row_index + 1,
                            len(default_values),
                        )
                    )
                fixed_total = sum(
                    int(value)
                    for value in override_values
                    if str(value).strip().lower() != AUTO_SEAT_BLOCK
                )
                if fixed_total > MAXIMUM_SEATS_PER_ROW:
                    raise ValueError(
                        "Row {0} fixed seat blocks may contain at most "
                        "{1} seats.".format(
                            row_index + 1,
                            MAXIMUM_SEATS_PER_ROW,
                        )
                    )
                return (
                    override_values,
                    True,
                )

    return (
        _normalize_seat_block_rule(
            params["seat_block_counts"],
            "Default seat-block rule",
        ),
        False,
    )


def resolve_row_seat_block_counts(
    params,
    row_x,
    layout_context=None,
    row_lateral_intervals=None,
    row_overrides=None,
    row_index=None
):
    """Resolve integer block counts for one plan-constrained row.

    ``row_lateral_intervals`` is one row's custom-boundary result in
    millimeters. When supplied it also enables automatic blocks in a
    rectangular layout.
    """
    block_values, unused_is_override = _row_rule_values(
        params,
        row_index,
        row_overrides,
    )
    if not block_values:
        return []
    has_auto = seat_blocks_have_auto(block_values)
    radial_mode = (
        layout_context is not None
        and layout_context.get("mode") == "radial"
    )
    custom_boundary_mode = row_lateral_intervals is not None
    if has_auto and not radial_mode and not custom_boundary_mode:
        raise ValueError(
            "Automatic seat blocks ('a') require a valid Radial "
            "plan radius."
        )

    if not radial_mode and not custom_boundary_mode:
        return [int(value) for value in block_values]

    module_width = float(params["seat_module_width"])
    aisle_width = float(params["longitudinal_aisle_width"])
    block_gap_width = max(len(block_values) - 1, 0) * aisle_width
    if custom_boundary_mode:
        usable_intervals = _usable_lateral_intervals(
            params,
            row_lateral_intervals,
        )
        if not usable_intervals:
            return [
                0
                if str(value).strip().lower() == AUTO_SEAT_BLOCK
                else int(value)
                for value in block_values
            ]
        available_arc_width = (
            usable_intervals[-1][1]
            - usable_intervals[0][0]
        )
        # Every interval edge already includes its side margin. Interior
        # gaps are retained and individual seat footprints are filtered
        # against the resulting disconnected usable regions later.
        side_margin = 0.0
    else:
        side_margin = float(params["side_floor_margin"])
        row_radius = (
            float(layout_context["radius"])
            + float(row_x)
        )
        available_arc_width = (
            2.0
            * float(layout_context["half_angle"])
            * row_radius
        )
    available_seat_width = (
        available_arc_width
        - side_margin * 2.0
        - block_gap_width
    )
    if custom_boundary_mode:
        available_seat_width -= _SHARED_ARMREST_WIDTH
    seat_capacity = int(
        math.floor(
            max(available_seat_width, 0.0) / module_width
            + 1e-9
        )
    )
    seat_capacity = min(seat_capacity, MAXIMUM_SEATS_PER_ROW)

    fixed_total = sum(
        int(value)
        for value in block_values
        if str(value).strip().lower() != AUTO_SEAT_BLOCK
    )
    if fixed_total > seat_capacity and not custom_boundary_mode:
        raise ValueError(
            "The fixed seat blocks, aisles, and side margins do not "
            "fit on radial row {0:.1f} mm.".format(row_x)
        )

    if not has_auto:
        return [int(value) for value in block_values]

    auto_count = sum(
        1
        for value in block_values
        if str(value).strip().lower() == AUTO_SEAT_BLOCK
    )
    seats_per_auto_block = (
        seat_capacity - fixed_total
    ) // auto_count
    if seats_per_auto_block < 1:
        if custom_boundary_mode:
            return [
                0
                if str(value).strip().lower() == AUTO_SEAT_BLOCK
                else int(value)
                for value in block_values
            ]
        raise ValueError(
            "There is not enough radial row width to place at least "
            "one seat in every automatic ('a') block."
        )

    return [
        seats_per_auto_block
        if str(value).strip().lower() == AUTO_SEAT_BLOCK
        else int(value)
        for value in block_values
    ]


def _summarize_resolved_row(
    params,
    block_counts,
    usable_intervals=None
):
    """Return placed counts and occupied width without placement records."""
    module_width = float(params["seat_module_width"])
    aisle_width = float(params["longitudinal_aisle_width"])
    total_width = (
        sum(count * module_width for count in block_counts)
        + max(len(block_counts) - 1, 0) * aisle_width
    )
    if usable_intervals:
        row_center = (
            usable_intervals[0][0]
            + usable_intervals[-1][1]
        ) * 0.5
    else:
        row_center = 0.0
    block_boundary = row_center - total_width * 0.5

    placed_block_counts = []
    row_armrest_laterals = []
    for block_index, block_count in enumerate(block_counts):
        if usable_intervals is None:
            placed_count = block_count
            if block_count > 0:
                row_armrest_laterals.extend(
                    block_boundary + armrest_index * module_width
                    for armrest_index in range(block_count + 1)
                )
        else:
            kept_seat_indices = []
            for seat_index in range(block_count):
                seat_left = block_boundary + seat_index * module_width
                if _footprint_fits_interval(
                    seat_left,
                    seat_left + module_width,
                    usable_intervals,
                ):
                    kept_seat_indices.append(seat_index)
            placed_count = len(kept_seat_indices)
            kept_armrest_indices = sorted(set(
                armrest_index
                for seat_index in kept_seat_indices
                for armrest_index in (seat_index, seat_index + 1)
            ))
            row_armrest_laterals.extend(
                block_boundary + armrest_index * module_width
                for armrest_index in kept_armrest_indices
            )
        placed_block_counts.append(placed_count)
        block_boundary += block_count * module_width
        if block_index < len(block_counts) - 1:
            block_boundary += aisle_width

    if usable_intervals is None:
        occupied_width = total_width if block_counts else 0.0
    elif row_armrest_laterals:
        occupied_width = (
            max(row_armrest_laterals)
            - min(row_armrest_laterals)
            + _SHARED_ARMREST_WIDTH
        )
    else:
        occupied_width = 0.0
    return placed_block_counts, occupied_width


def calculate_tier_row_layouts(
    params,
    section_result,
    layout_context=None,
    row_regions=None,
    row_overrides=None
):
    """Resolve lightweight, UI-friendly seating data for every tier row.

    Missing override keys use ``params['seat_block_counts']``. An explicit
    empty override list produces an empty row. Custom-boundary rows report
    the actually placeable counts after footprint clipping.
    """
    row_pairs = list(
        zip(
            section_result["x_values"],
            section_result["base_z_values"],
        )
    )
    normalized_row_regions = None
    if row_regions is not None:
        normalized_row_regions = _normalize_row_regions(
            row_regions,
            len(row_pairs),
        )
    default_rule_values = _normalize_seat_block_rule(
        params["seat_block_counts"],
        "Default seat-block rule",
    )

    layouts = []
    for row_index, (row_x, floor_z) in enumerate(row_pairs):
        rule_values, is_override = _row_rule_values(
            params,
            row_index,
            row_overrides,
        )
        row_region = (
            normalized_row_regions[row_index]
            if normalized_row_regions is not None
            else None
        )
        usable_intervals = (
            _usable_lateral_intervals(params, row_region)
            if row_region is not None
            else None
        )
        resolved_block_counts = resolve_row_seat_block_counts(
            params,
            row_x,
            layout_context,
            row_region,
            row_overrides=row_overrides,
            row_index=row_index,
        )
        placed_block_counts, row_total_width = _summarize_resolved_row(
            params,
            resolved_block_counts,
            usable_intervals,
        )
        is_empty = is_override and not rule_values
        if is_empty:
            status = "empty"
        elif is_override:
            status = "override"
        else:
            status = "automatic"
        layouts.append({
            "row_index": row_index,
            "row_x": row_x,
            "floor_z": floor_z,
            "default_rule_values": list(default_rule_values),
            "rule_values": list(rule_values),
            "resolved_block_counts": list(resolved_block_counts),
            "placed_block_counts": list(placed_block_counts),
            "seat_count": sum(placed_block_counts),
            "row_total_width": row_total_width,
            "automatic": not is_override,
            "override": is_override and not is_empty,
            "empty": is_empty,
            "status": status,
            "has_auto": seat_blocks_have_auto(rule_values),
        })
    return layouts


def calculate_3d_seat_placements(
    params,
    section_result,
    layout_context=None,
    row_regions=None,
    row_overrides=None
):
    """Create chair and shared-armrest placement records.

    ``row_regions`` must be parallel to the effective section rows. Each
    entry is a list of lateral ``(left, right)`` millimeter intervals.
    """
    module_width = params["seat_module_width"]
    aisle_width = params["longitudinal_aisle_width"]

    row_pairs = list(
        zip(
            section_result["x_values"],
            section_result["base_z_values"]
        )
    )
    normalized_row_regions = None
    if row_regions is not None:
        normalized_row_regions = _normalize_row_regions(
            row_regions,
            len(row_pairs),
        )

    chair_placements = []
    armrest_placements = []
    row_block_counts = []
    row_total_widths = []
    normalized_usable_row_regions = []
    for row_index, (row_x, floor_z) in enumerate(row_pairs):
        usable_intervals = None
        if normalized_row_regions is not None:
            usable_intervals = _usable_lateral_intervals(
                params,
                normalized_row_regions[row_index],
            )
            normalized_usable_row_regions.append(usable_intervals)

        block_counts = resolve_row_seat_block_counts(
            params,
            row_x,
            layout_context,
            (
                normalized_row_regions[row_index]
                if normalized_row_regions is not None
                else None
            ),
            row_overrides=row_overrides,
            row_index=row_index,
        )
        total_module_width = sum(
            count * module_width
            for count in block_counts
        )
        total_width = (
            total_module_width
            + max(len(block_counts) - 1, 0) * aisle_width
        )
        if usable_intervals:
            row_center = (
                usable_intervals[0][0]
                + usable_intervals[-1][1]
            ) * 0.5
        else:
            row_center = 0.0
        left_boundary = row_center - total_width * 0.5
        actual_block_counts = []
        row_armrest_laterals = []
        block_boundary = left_boundary
        for block_index, block_count in enumerate(block_counts):
            kept_seat_indices = []
            for seat_index in range(block_count):
                seat_left = (
                    block_boundary + seat_index * module_width
                )
                seat_right = seat_left + module_width
                if (
                    usable_intervals is not None
                    and not _footprint_fits_interval(
                        seat_left,
                        seat_right,
                        usable_intervals,
                    )
                ):
                    continue
                kept_seat_indices.append(seat_index)
                chair_placement = {
                    "row_index": row_index,
                    "block_index": block_index,
                    "seat_index": seat_index,
                    "row_x": row_x,
                    "floor_z": floor_z,
                    "lateral": (
                        block_boundary
                        + (seat_index + 0.5) * module_width
                    ),
                }
                if usable_intervals is not None:
                    chair_placement["boundary_constrained"] = True
                chair_placements.append(chair_placement)
            actual_block_counts.append(len(kept_seat_indices))
            if usable_intervals is None:
                kept_armrest_indices = (
                    range(block_count + 1)
                    if block_count > 0
                    else ()
                )
            else:
                kept_armrest_indices = sorted(set(
                    armrest_index
                    for seat_index in kept_seat_indices
                    for armrest_index in (seat_index, seat_index + 1)
                ))
            for armrest_index in kept_armrest_indices:
                armrest_lateral = (
                    block_boundary
                    + armrest_index * module_width
                )
                armrest_placement = {
                    "row_index": row_index,
                    "block_index": block_index,
                    "armrest_index": armrest_index,
                    "row_x": row_x,
                    "floor_z": floor_z,
                    "lateral": armrest_lateral,
                }
                if usable_intervals is not None:
                    armrest_placement["boundary_constrained"] = True
                armrest_placements.append(armrest_placement)
                row_armrest_laterals.append(armrest_lateral)
            block_boundary += block_count * module_width
            if block_index < len(block_counts) - 1:
                block_boundary += aisle_width

        if usable_intervals is None:
            row_block_counts.append(block_counts)
            row_total_widths.append(total_width)
        else:
            row_block_counts.append(actual_block_counts)
            if row_armrest_laterals:
                row_total_widths.append(
                    max(row_armrest_laterals)
                    - min(row_armrest_laterals)
                    + _SHARED_ARMREST_WIDTH
                )
            else:
                row_total_widths.append(0.0)

    chairs_per_row_values = [
        sum(block_counts)
        for block_counts in row_block_counts
    ]
    if normalized_row_regions is None:
        armrests_per_row_values = [
            sum(block_counts)
            + sum(1 for count in block_counts if count > 0)
            for block_counts in row_block_counts
        ]
    else:
        armrests_per_row_values = [
            sum(
                1
                for placement in armrest_placements
                if placement["row_index"] == row_index
            )
            for row_index in range(len(row_pairs))
        ]
    result = {
        "chair_placements": chair_placements,
        "armrest_placements": armrest_placements,
        "chairs_per_row": (
            max(chairs_per_row_values)
            if chairs_per_row_values
            else 0
        ),
        "chairs_per_row_values": chairs_per_row_values,
        "armrests_per_row": (
            max(armrests_per_row_values)
            if armrests_per_row_values
            else 0
        ),
        "armrests_per_row_values": armrests_per_row_values,
        "row_block_counts": row_block_counts,
        "row_total_widths": row_total_widths,
        "total_width": max(row_total_widths) if row_total_widths else 0.0,
    }
    if normalized_row_regions is not None:
        result["row_regions"] = normalized_usable_row_regions
    return result


def calculate_3d_seat_count_for_row_regions(
    params,
    section_result,
    layout_context=None,
    row_regions=None,
    row_overrides=None
):
    """Count custom-boundary seats without constructing placement records."""
    row_pairs = list(
        zip(
            section_result["x_values"],
            section_result["base_z_values"]
        )
    )
    normalized_row_regions = _normalize_row_regions(
        row_regions,
        len(row_pairs),
    )
    module_width = params["seat_module_width"]
    aisle_width = params["longitudinal_aisle_width"]

    total_count = 0
    for row_index, (row_x, unused_floor_z) in enumerate(row_pairs):
        row_region = normalized_row_regions[row_index]
        usable_intervals = _usable_lateral_intervals(
            params,
            row_region,
        )
        block_counts = resolve_row_seat_block_counts(
            params,
            row_x,
            layout_context,
            row_region,
            row_overrides=row_overrides,
            row_index=row_index,
        )
        if not usable_intervals:
            continue

        total_width = (
            sum(count * module_width for count in block_counts)
            + max(len(block_counts) - 1, 0) * aisle_width
        )
        row_center = (
            usable_intervals[0][0]
            + usable_intervals[-1][1]
        ) * 0.5
        block_boundary = row_center - total_width * 0.5
        for block_index, block_count in enumerate(block_counts):
            for seat_index in range(block_count):
                seat_left = (
                    block_boundary + seat_index * module_width
                )
                if _footprint_fits_interval(
                    seat_left,
                    seat_left + module_width,
                    usable_intervals,
                ):
                    total_count += 1
            block_boundary += block_count * module_width
            if block_index < len(block_counts) - 1:
                block_boundary += aisle_width
    return total_count


def _normalize_tier_row_overrides(tier_row_overrides, balcony_count):
    """Return overrides parallel to stalls plus balcony-result slots."""
    expected_count = 1 + balcony_count
    if tier_row_overrides is None:
        return [None] * expected_count
    if isinstance(tier_row_overrides, (str, bytes)):
        raise ValueError(
            "Tier row overrides must be a tier mapping or sequence."
        )

    if hasattr(tier_row_overrides, "keys"):
        normalized = [None] * expected_count
        aliases = {
            "stalls": 0,
            "stall": 0,
            "balcony1": 1,
            "balcony_1": 1,
            "balcony 1": 1,
            "b1": 1,
            "balcony2": 2,
            "balcony_2": 2,
            "balcony 2": 2,
            "b2": 2,
        }
        for key in tier_row_overrides.keys():
            if isinstance(key, _INTEGER_TYPES):
                tier_index = key
            else:
                tier_index = aliases.get(str(key).strip().lower())
            if tier_index is None or not 0 <= tier_index < expected_count:
                raise ValueError(
                    "Unknown tier row-override key: {0}.".format(key)
                )
            normalized[tier_index] = tier_row_overrides[key]
        return normalized

    try:
        normalized = list(tier_row_overrides)
    except Exception:
        raise ValueError(
            "Tier row overrides must be a tier mapping or sequence."
        )
    if len(normalized) != expected_count:
        raise ValueError(
            "Tier row overrides must contain exactly {0} entries; "
            "received {1}.".format(expected_count, len(normalized))
        )
    return normalized


def normalize_tier_row_overrides(tier_row_overrides, balcony_count=2):
    """Return a canonical tier-key mapping for every seating consumer."""
    normalized = _normalize_tier_row_overrides(
        tier_row_overrides,
        balcony_count,
    )
    result = {"stalls": normalized[0]}
    for balcony_index in range(balcony_count):
        result["balcony_{0}".format(balcony_index + 1)] = (
            normalized[balcony_index + 1]
        )
    return result


def tier_row_override_fit_issues(
    row_layouts_by_tier,
    tier_row_overrides,
    balcony_count=2,
):
    """Report fixed override blocks clipped by a custom boundary.

    Automatic ``a`` blocks may legitimately resolve to the available row
    capacity.  Positive fixed blocks must be placed exactly as requested.
    """
    overrides = normalize_tier_row_overrides(
        tier_row_overrides,
        balcony_count,
    )
    layouts_source = (
        row_layouts_by_tier
        if hasattr(row_layouts_by_tier, "get")
        else {}
    )
    issues = []
    tier_keys = ["stalls"] + [
        "balcony_{0}".format(index + 1)
        for index in range(balcony_count)
    ]
    for tier_key in tier_keys:
        tier_overrides = overrides.get(tier_key)
        if not hasattr(tier_overrides, "items"):
            continue
        row_lookup = {}
        for fallback_index, row_layout in enumerate(
            layouts_source.get(tier_key, [])
        ):
            if not hasattr(row_layout, "get"):
                continue
            row_index = int(
                row_layout.get("row_index", fallback_index)
            )
            row_lookup[row_index] = row_layout

        for raw_row_index, raw_rule in tier_overrides.items():
            try:
                row_index = int(raw_row_index)
            except Exception:
                continue
            row_layout = row_lookup.get(row_index)
            if row_layout is None:
                continue
            rule_values = _normalize_seat_block_rule(
                raw_rule,
                "Row {0} override".format(row_index + 1),
            )
            if not rule_values:
                continue
            placed = list(
                row_layout.get("placed_block_counts", [])
            )
            clipped_blocks = []
            for block_index, rule_value in enumerate(rule_values):
                if str(rule_value).strip().lower() == AUTO_SEAT_BLOCK:
                    continue
                placed_count = (
                    int(placed[block_index])
                    if block_index < len(placed)
                    else 0
                )
                requested_count = int(rule_value)
                if placed_count != requested_count:
                    clipped_blocks.append({
                        "block_index": block_index,
                        "requested_count": requested_count,
                        "placed_count": placed_count,
                    })
            if clipped_blocks:
                issues.append({
                    "tier_key": tier_key,
                    "row_index": row_index,
                    "rule_values": list(rule_values),
                    "resolved_block_counts": list(
                        row_layout.get("resolved_block_counts", [])
                    ),
                    "placed_block_counts": placed,
                    "clipped_blocks": clipped_blocks,
                })
    return issues


def calculate_total_3d_seat_count(
    params,
    section_result,
    balcony_results=None,
    layout_context=None,
    tier_row_regions=None,
    tier_row_overrides=None
):
    """Count actual seats across the stalls and generated balconies.

    ``tier_row_regions`` is parallel to ``[stalls] + balcony_results``.
    Entries for inactive balcony results are retained as placeholders.
    """
    if balcony_results is None:
        # Backward-compatible fixed-block call:
        # calculate_total_3d_seat_count(params, balcony_results)
        if tier_row_regions is not None:
            raise ValueError(
                "Custom-boundary seat totals require the stalls "
                "section result and balcony result list."
            )
        if tier_row_overrides is not None:
            raise ValueError(
                "Row-override seat totals require the stalls section "
                "result and balcony result list."
            )
        balcony_results = section_result
        if seat_blocks_have_auto(params["seat_block_counts"]):
            raise ValueError(
                "Automatic seat totals require the stalls section "
                "result and Radial layout context."
            )
        valid_row_count = int(params["row_count"])
        for balcony_result in balcony_results:
            if balcony_result_is_displayable(balcony_result):
                valid_row_count += int(balcony_result["row_count"])
        return (
            valid_row_count
            * sum(int(value) for value in params["seat_block_counts"])
        )

    tier_overrides = _normalize_tier_row_overrides(
        tier_row_overrides,
        len(balcony_results),
    )

    if tier_row_regions is not None:
        if isinstance(tier_row_regions, (str, bytes)):
            raise ValueError(
                "Tier row regions must be provided for the stalls "
                "and each balcony result."
            )
        try:
            tier_regions = list(tier_row_regions)
        except Exception:
            raise ValueError(
                "Tier row regions must be provided for the stalls "
                "and each balcony result."
            )
        expected_tier_count = 1 + len(balcony_results)
        if len(tier_regions) != expected_tier_count:
            raise ValueError(
                "Tier row regions must contain exactly {0} entries; "
                "received {1}.".format(
                    expected_tier_count,
                    len(tier_regions),
                )
            )

        total = calculate_3d_seat_count_for_row_regions(
            params,
            section_result,
            layout_context,
            tier_regions[0],
            tier_overrides[0],
        )
        for balcony_index, balcony_result in enumerate(
            balcony_results
        ):
            if not balcony_result_is_displayable(balcony_result):
                continue
            total += calculate_3d_seat_count_for_row_regions(
                params,
                balcony_result,
                layout_context,
                tier_regions[balcony_index + 1],
                tier_overrides[balcony_index + 1],
            )
        return total

    total = sum(
        sum(
            resolve_row_seat_block_counts(
                params,
                row_x,
                layout_context,
                row_overrides=tier_overrides[0],
                row_index=row_index,
            )
        )
        for row_index, row_x in enumerate(section_result["x_values"])
    )
    for balcony_index, balcony_result in enumerate(balcony_results):
        if not balcony_result_is_displayable(balcony_result):
            continue
        total += sum(
            sum(
                resolve_row_seat_block_counts(
                    params,
                    row_x,
                    layout_context,
                    row_overrides=(
                        tier_overrides[balcony_index + 1]
                    ),
                    row_index=row_index,
                )
            )
            for row_index, row_x in enumerate(
                balcony_result["x_values"]
            )
        )
    return total


def calculate_seat_layout_width(params):
    block_counts = params["seat_block_counts"]
    if seat_blocks_have_auto(block_counts):
        raise ValueError(
            "Automatic seat blocks ('a') require a Radial plan."
        )
    return (
        sum(int(value) for value in block_counts)
        * params["seat_module_width"]
        + max(len(block_counts) - 1, 0)
        * params["longitudinal_aisle_width"]
    )
