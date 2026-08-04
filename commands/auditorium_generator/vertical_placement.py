# -*- coding: utf-8 -*-
"""Pure vertical-placement calculations for auditorium geometry."""


def _finite_float(value, label):
    try:
        numeric = float(value)
    except Exception:
        raise ValueError("{0} must be a finite number.".format(label))
    if (
        numeric != numeric
        or numeric == float("inf")
        or numeric == float("-inf")
    ):
        raise ValueError("{0} must be a finite number.".format(label))
    return numeric


def calculate_vertical_placement(
    datum_z_model_units,
    mm_scale,
    stage_height_mm,
    stalls_rear_local_z_mm,
    target_world_z_mm=None,
):
    """Return the datum shift needed to place the stalls rear at World Z.

    ``stalls_rear_local_z_mm`` is measured from the opening-bottom/stage
    reference point.  Moving the datum instead of modifying section heights
    keeps every relative dimension and sightline calculation unchanged.
    """
    datum_z = _finite_float(
        datum_z_model_units,
        "Audience datum Z",
    )
    scale = _finite_float(mm_scale, "Millimeter unit scale")
    stage_height = _finite_float(stage_height_mm, "Stage height")
    rear_local_z = _finite_float(
        stalls_rear_local_z_mm,
        "Stalls rear local Z",
    )
    if scale <= 0.0:
        raise ValueError(
            "Millimeter unit scale must be greater than zero."
        )

    unshifted_rear_world_z_mm = (
        datum_z / scale + stage_height + rear_local_z
    )
    if target_world_z_mm is None:
        target_z = unshifted_rear_world_z_mm
        override_applied = False
    else:
        target_z = _finite_float(
            target_world_z_mm,
            "Stalls rear World Z",
        )
        override_applied = True

    vertical_offset_mm = target_z - unshifted_rear_world_z_mm
    vertical_offset_model_units = vertical_offset_mm * scale
    placed_datum_z_model_units = (
        datum_z + vertical_offset_model_units
    )

    return {
        "override_applied": override_applied,
        "unshifted_rear_world_z_mm": unshifted_rear_world_z_mm,
        "vertical_offset_mm": vertical_offset_mm,
        "vertical_offset_model_units": vertical_offset_model_units,
        "placed_datum_z_model_units": placed_datum_z_model_units,
        "actual_rear_world_z_mm": target_z,
    }
