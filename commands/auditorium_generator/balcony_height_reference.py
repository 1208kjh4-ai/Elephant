# -*- coding: utf-8 -*-
"""Keep balcony heights relative to the un-interpolated stalls rear row."""


def stalls_height_reference_z(stalls_result):
    """Return the stalls rear Z used when the stored balcony height was set."""
    if stalls_result.get("rise_interpolation_applied", False):
        return (
            float(stalls_result["base_z_values"][0])
            + float(stalls_result["rise_interpolation_original"])
        )
    return float(stalls_result["base_z_values"][-1])


def rebase_balcony_last_platform_z(
    stored_absolute_z,
    stalls_reference_z,
    effective_stalls_rear_z
):
    """Move a stored balcony Z with the current interpolated stalls rear."""
    relative_height = (
        float(stored_absolute_z) - float(stalls_reference_z)
    )
    return float(effective_stalls_rear_z) + relative_height
