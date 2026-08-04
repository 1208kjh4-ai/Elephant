# -*- coding: utf-8 -*-
"""Radial auditorium plan calculations and Rhino geometry helpers."""

import math

import Rhino.Geometry as rg

from .rhino_primitives import get_stage_directions


RADIAL_RADIUS_TOLERANCE = 1e-8


def normalize_plan_layout_radius(radius_mm, opening_width_mm):
    """Return 0 for rectangular mode or a valid chord radius."""
    try:
        radius = float(radius_mm)
    except Exception:
        raise ValueError("Plan layout radius must be a number.")

    if math.isnan(radius) or math.isinf(radius) or radius < 0.0:
        raise ValueError(
            "Plan layout radius must be zero or a positive finite value."
        )

    minimum_radius = float(opening_width_mm) * 0.5
    if radius < minimum_radius - RADIAL_RADIUS_TOLERANCE:
        return 0.0
    return max(radius, minimum_radius)


def build_plan_layout_context(
    stage_point,
    audience_direction,
    opening_width_mm,
    radius_mm,
    mm_scale
):
    """Build the rectangular/radial plan datum shared by all geometry."""
    effective_radius = normalize_plan_layout_radius(
        radius_mm,
        opening_width_mm
    )
    audience_view_right_direction, unused_stage_back = get_stage_directions(
        audience_direction
    )

    if effective_radius <= RADIAL_RADIUS_TOLERANCE:
        return {
            "mode": "rectangular",
            "radius": 0.0,
            "minimum_radius": opening_width_mm * 0.5,
            "half_angle": 0.0,
            "center_offset": 0.0,
            "sagitta": 0.0,
            "center_point": rg.Point3d(stage_point),
            "reference_mid_point": rg.Point3d(stage_point),
            "opening_stage_point": rg.Point3d(stage_point),
            "audience_direction": rg.Vector3d(audience_direction),
            "audience_view_right_direction": rg.Vector3d(
                audience_view_right_direction
            ),
            # Compatibility alias for existing preview/build consumers.
            "stage_right_direction": rg.Vector3d(
                audience_view_right_direction
            ),
        }

    half_chord = opening_width_mm * 0.5
    center_offset = math.sqrt(
        max(
            effective_radius * effective_radius
            - half_chord * half_chord,
            0.0
        )
    )
    half_angle = math.asin(
        min(1.0, half_chord / effective_radius)
    )
    center_point = (
        stage_point
        - audience_direction * (center_offset * mm_scale)
    )
    sagitta = effective_radius - center_offset
    reference_mid_point = (
        center_point
        + audience_direction * (effective_radius * mm_scale)
    )
    return {
        "mode": "radial",
        "radius": effective_radius,
        "minimum_radius": half_chord,
        "half_angle": half_angle,
        "center_offset": center_offset,
        "sagitta": sagitta,
        "center_point": rg.Point3d(center_point),
        "reference_mid_point": rg.Point3d(reference_mid_point),
        "opening_stage_point": rg.Point3d(stage_point),
        "audience_direction": rg.Vector3d(audience_direction),
        "audience_view_right_direction": rg.Vector3d(
            audience_view_right_direction
        ),
        # Compatibility alias for existing preview/build consumers.
        "stage_right_direction": rg.Vector3d(
            audience_view_right_direction
        ),
    }


def radial_point(context, radius_mm, angle_radians, z_mm, mm_scale):
    """Return a model point in the radial layout coordinate system."""
    radial_direction = rg.Vector3d(context["audience_direction"])
    radial_direction.Rotate(
        float(angle_radians),
        rg.Vector3d.ZAxis
    )
    return (
        context["center_point"]
        + radial_direction * (float(radius_mm) * mm_scale)
        + rg.Vector3d.ZAxis * (float(z_mm) * mm_scale)
    )


def radial_frame(context, radius_mm, angle_radians, z_mm, mm_scale):
    """Return origin, tangent and outward vectors at a radial seat point."""
    outward = rg.Vector3d(context["audience_direction"])
    outward.Rotate(float(angle_radians), rg.Vector3d.ZAxis)
    tangent = rg.Vector3d(context["audience_view_right_direction"])
    tangent.Rotate(float(angle_radians), rg.Vector3d.ZAxis)
    origin = radial_point(
        context,
        radius_mm,
        angle_radians,
        z_mm,
        mm_scale
    )
    return origin, tangent, outward


def build_radial_arc(
    context,
    radius_mm,
    z_mm,
    mm_scale
):
    """Create an arc over the opening-defined angular domain."""
    if (
        context["mode"] != "radial"
        or radius_mm <= RADIAL_RADIUS_TOLERANCE
    ):
        return None

    half_angle = context["half_angle"]
    start = radial_point(
        context,
        radius_mm,
        -half_angle,
        z_mm,
        mm_scale
    )
    middle = radial_point(
        context,
        radius_mm,
        0.0,
        z_mm,
        mm_scale
    )
    end = radial_point(
        context,
        radius_mm,
        half_angle,
        z_mm,
        mm_scale
    )
    arc = rg.Arc(start, middle, end)
    return arc.ToNurbsCurve() if arc.IsValid else None


def build_radial_side_line(
    context,
    start_radius_mm,
    end_radius_mm,
    angle_radians,
    start_z_mm,
    end_z_mm,
    mm_scale
):
    return rg.LineCurve(
        radial_point(
            context,
            start_radius_mm,
            angle_radians,
            start_z_mm,
            mm_scale
        ),
        radial_point(
            context,
            end_radius_mm,
            angle_radians,
            end_z_mm,
            mm_scale
        )
    )


def sweep_section_curve_radially(
    curve,
    context,
    start_angle=None,
    end_angle=None,
):
    """Revolve a central longitudinal section curve over an angular domain.

    Omitting the optional angles preserves the opening-defined auditorium
    sweep used by the original generator.  A custom plan boundary can request
    a wider source surface and trim it afterwards without changing that
    legacy path.
    """
    if curve is None or context["mode"] != "radial":
        return None

    if start_angle is None:
        start_angle = -context["half_angle"]
    if end_angle is None:
        end_angle = context["half_angle"]

    axis_start = rg.Point3d(context["center_point"])
    axis_end = axis_start + rg.Vector3d.ZAxis
    axis = rg.Line(axis_start, axis_end)
    duplicated_curve = curve.DuplicateCurve()
    # Keep the explicit angular domain even for a full revolution.  The
    # custom-boundary source uses -pi..pi so its seam stays at the rear of the
    # radial layout instead of crossing the stage opening at angle zero.
    surface = rg.RevSurface.Create(
        duplicated_curve,
        axis,
        float(start_angle),
        float(end_angle)
    )
    return surface.ToBrep() if surface is not None else None


def radial_available_arc_length(context, radius_mm):
    if context["mode"] != "radial":
        return 0.0
    return 2.0 * context["half_angle"] * float(radius_mm)


def radial_available_chord_width(context, radius_mm):
    if context["mode"] != "radial":
        return 0.0
    return (
        2.0
        * float(radius_mm)
        * math.sin(context["half_angle"])
    )
