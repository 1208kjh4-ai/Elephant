# -*- coding: utf-8 -*-
"""Geometry validation for the audience-floor reference baseline."""

import Rhino.Geometry as rg


def get_curve_plane(curve):
    """Backward-compatible plane query used by older Auditorium scripts."""
    try:
        result = curve.TryGetPlane()
        if isinstance(result, tuple):
            return result[0], result[1]
        return False, rg.Plane.Unset
    except Exception:
        return False, rg.Plane.Unset


def _model_tolerance(doc):
    if doc is None:
        return 1e-6
    return max(float(doc.ModelAbsoluteTolerance), 1e-6)


def analyze_reference_baseline(reference_start, reference_end, doc):
    """
    Validate the two-point audience datum baseline.

    Point order is defined from the audience's view toward the stage:
        reference_start: audience-view left
        reference_end: audience-view right

    The returned datum point is the midpoint of the line at the lowest
    audience-floor elevation. ``default_direction`` points from the stage
    toward the audience.
    """
    if reference_start is None or reference_end is None:
        raise ValueError("Both reference-line points are required.")

    start = rg.Point3d(reference_start)
    end = rg.Point3d(reference_end)
    if not start.IsValid or not end.IsValid:
        raise ValueError("The reference-line points are not valid.")

    tolerance = _model_tolerance(doc)
    if abs(end.Z - start.Z) > tolerance:
        raise ValueError(
            "The reference line must be horizontal. "
            "Choose the second point on the same Z level as the first point."
        )

    # Remove insignificant input noise after the strict tolerance check so all
    # downstream geometry shares one exact audience-floor elevation.
    end.Z = start.Z

    reference_vector = end - start
    reference_width = reference_vector.Length
    if reference_width <= tolerance:
        raise ValueError(
            "The reference line is too short. "
            "Choose two distinct points farther apart than the model tolerance."
        )

    audience_view_right = rg.Vector3d(reference_vector)
    if not audience_view_right.Unitize():
        raise ValueError("The reference-line direction could not be determined.")

    default_direction = rg.Vector3d.CrossProduct(
        audience_view_right,
        rg.Vector3d.ZAxis,
    )
    if not default_direction.Unitize():
        raise ValueError("The default audience direction could not be determined.")

    audience_datum_point = rg.Point3d(
        (start.X + end.X) * 0.5,
        (start.Y + end.Y) * 0.5,
        start.Z,
    )

    return {
        "audience_datum_point": audience_datum_point,
        "reference_start": start,
        "reference_end": end,
        "reference_width": reference_width,
        "audience_view_right_direction": audience_view_right,
        "default_direction": default_direction,
        # Compatibility keys used by the current preview/dialog pipeline.
        "stage_point": audience_datum_point,
        "opening_width": reference_width,
    }


def analyze_opening_rectangle(curve, doc):
    """
    Backward-compatible analyzer surface.

    New commands pass a two-point LineCurve. A legacy four-sided rectangular
    opening is still accepted so external scripts importing the old function
    do not fail abruptly. Only its lowest horizontal edge is used; opening
    height is deliberately not returned because PH is now a dialog input.
    """
    if curve is None:
        raise ValueError("A reference line is required.")

    tolerance = _model_tolerance(doc)

    if not curve.IsClosed and curve.IsLinear(tolerance):
        return analyze_reference_baseline(
            curve.PointAtStart,
            curve.PointAtEnd,
            doc,
        )

    if not curve.IsClosed:
        raise ValueError(
            "The reference geometry must be a straight line defined by two points."
        )

    segments = curve.DuplicateSegments()
    if not segments or len(segments) != 4:
        raise ValueError(
            "Legacy opening geometry must be a four-sided rectangle."
        )

    lines = []
    for segment in segments:
        if segment is None or not segment.IsLinear(tolerance):
            raise ValueError(
                "Every edge of the legacy opening rectangle must be straight."
            )
        lines.append(rg.Line(segment.PointAtStart, segment.PointAtEnd))

    bottom = min(lines, key=lambda line: (line.From.Z + line.To.Z) * 0.5)
    if abs(bottom.From.Z - bottom.To.Z) > tolerance:
        raise ValueError(
            "The bottom edge of the legacy opening rectangle must be horizontal."
        )

    return analyze_reference_baseline(bottom.From, bottom.To, doc)
