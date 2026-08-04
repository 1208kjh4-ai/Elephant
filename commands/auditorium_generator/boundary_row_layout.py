# -*- coding: utf-8 -*-
"""Clip auditorium row curves to a custom plan boundary."""

import math

import Rhino.Geometry as rg

from .rhino_primitives import get_stage_directions, point_at


_PARAMETER_EPSILON = 1e-12
_MIN_INTERVAL_MM = 1e-8


def _context_value(boundary_context, key):
    if boundary_context is None or not hasattr(boundary_context, "get"):
        raise ValueError("Boundary context must be a dictionary-like object.")
    value = boundary_context.get(key)
    if value is None:
        raise ValueError(
            "Boundary context is missing required value: {0}.".format(key)
        )
    return value


def _positive_number(value, label):
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise ValueError("{0} must be a positive number.".format(label))
    if (
        number != number
        or number == float("inf")
        or number == float("-inf")
    ):
        raise ValueError("{0} must be a finite number.".format(label))
    if number <= 0.0:
        raise ValueError("{0} must be greater than zero.".format(label))
    return number


def _finite_number(value, label):
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise ValueError("{0} must be a number.".format(label))
    if (
        number != number
        or number == float("inf")
        or number == float("-inf")
    ):
        raise ValueError("{0} must be a finite number.".format(label))
    return number


def _layout_value(layout_context, key):
    if layout_context is None or not hasattr(layout_context, "get"):
        raise ValueError("Plan layout context must be a dictionary-like object.")
    value = layout_context.get(key)
    if value is None:
        raise ValueError(
            "Plan layout context is missing required value: {0}.".format(key)
        )
    return value


def _curve_domain(curve):
    try:
        domain = curve.Domain
        domain_start = float(domain.T0)
        domain_end = float(domain.T1)
    except Exception as error:
        raise ValueError(
            "Candidate curve does not have a valid parameter domain: {0}".format(
                error
            )
        )
    if domain_end <= domain_start:
        raise ValueError("Candidate curve parameter domain must be increasing.")
    return domain_start, domain_end


def _point_distance(point_a, point_b):
    try:
        return float(point_a.DistanceTo(point_b))
    except Exception:
        try:
            return float((point_a - point_b).Length)
        except Exception:
            return None


def _parameters_are_close(curve, parameter_a, parameter_b, tolerance):
    parameter_scale = max(
        1.0,
        abs(float(parameter_a)),
        abs(float(parameter_b)),
    )
    if abs(parameter_b - parameter_a) <= (
        _PARAMETER_EPSILON * parameter_scale
    ):
        return True

    try:
        point_a = curve.PointAt(parameter_a)
        point_b = curve.PointAt(parameter_b)
    except Exception:
        return False
    distance = _point_distance(point_a, point_b)
    return distance is not None and distance <= tolerance


def _unique_curve_parameters(curve, parameters, tolerance, domain):
    domain_start, domain_end = domain
    clamped = []
    for parameter in parameters:
        try:
            value = float(parameter)
        except (TypeError, ValueError):
            continue
        value = min(domain_end, max(domain_start, value))
        clamped.append(value)

    clamped.sort()
    unique = [domain_start]
    for value in clamped:
        parameter_scale = max(1.0, abs(domain_start), abs(domain_end))
        if abs(value - domain_start) <= (
            _PARAMETER_EPSILON * parameter_scale
        ):
            continue
        if abs(value - domain_end) <= (
            _PARAMETER_EPSILON * parameter_scale
        ):
            continue
        if _parameters_are_close(
            curve,
            unique[-1],
            value,
            tolerance,
        ):
            continue
        unique.append(value)

    if (
        len(unique) > 1
        and _parameters_are_close(
            curve,
            unique[-1],
            domain_end,
            tolerance,
        )
    ):
        unique.pop()
    # Closed curves have coincident domain endpoints.  Preserve both parameter
    # values explicitly so a wholly contained full circle remains one segment.
    unique.append(domain_end)
    return unique


def _intersection_parameters(candidate_curve, boundary_curve, tolerance):
    try:
        events = rg.Intersect.Intersection.CurveCurve(
            candidate_curve,
            boundary_curve,
            tolerance,
            tolerance,
        )
    except Exception as error:
        raise RuntimeError(
            "Boundary and row curve intersection failed: {0}".format(error)
        )

    parameters = []
    if events is None:
        return parameters

    for event in events:
        try:
            if event.IsOverlap:
                overlap = event.OverlapA
                parameters.extend((overlap.T0, overlap.T1))
            elif event.IsPoint:
                parameters.append(event.ParameterA)
        except Exception as error:
            raise RuntimeError(
                "Boundary intersection event could not be read: {0}".format(
                    error
                )
            )
    return parameters


def _point_is_inside_or_coincident(boundary_curve, plane, point, tolerance):
    try:
        containment = boundary_curve.Contains(point, plane, tolerance)
    except Exception as error:
        raise RuntimeError(
            "Boundary containment test failed: {0}".format(error)
        )
    return containment in (
        rg.PointContainment.Inside,
        rg.PointContainment.Coincident,
    )


def _trimmed_curve(candidate_curve, parameter_start, parameter_end, domain):
    domain_start, domain_end = domain
    if (
        abs(parameter_start - domain_start) <= _PARAMETER_EPSILON
        and abs(parameter_end - domain_end) <= _PARAMETER_EPSILON
    ):
        try:
            duplicate = candidate_curve.DuplicateCurve()
        except Exception as error:
            raise RuntimeError(
                "Candidate curve could not be duplicated: {0}".format(error)
            )
        if duplicate is None:
            raise RuntimeError("Candidate curve duplication returned no curve.")
        return duplicate

    try:
        segment = candidate_curve.Trim(
            rg.Interval(parameter_start, parameter_end)
        )
    except Exception as error:
        raise RuntimeError(
            "Candidate curve could not be trimmed: {0}".format(error)
        )
    if segment is None:
        raise RuntimeError("Candidate curve trimming returned no curve.")
    return segment


def _curve_is_tolerance_sliver(curve, tolerance):
    try:
        return float(curve.GetLength()) <= tolerance
    except Exception as error:
        raise RuntimeError(
            "Trimmed row curve length could not be measured: {0}".format(error)
        )


def curve_segments_inside_boundary(boundary_context, candidate_curve):
    """Return candidate-curve portions inside or coincident with a boundary.

    Returned curves are ordered along ``candidate_curve``.  Neither the input
    boundary nor the candidate curve is modified.
    """
    boundary_curve = _context_value(boundary_context, "curve")
    plane = _context_value(boundary_context, "plane")
    tolerance = _positive_number(
        _context_value(boundary_context, "tolerance"),
        "Boundary tolerance",
    )
    if candidate_curve is None:
        raise ValueError("Candidate row curve is required.")

    domain = _curve_domain(candidate_curve)
    parameters = [domain[0], domain[1]]
    parameters.extend(
        _intersection_parameters(
            candidate_curve,
            boundary_curve,
            tolerance,
        )
    )
    parameters = _unique_curve_parameters(
        candidate_curve,
        parameters,
        tolerance,
        domain,
    )

    segments = []
    for index in range(len(parameters) - 1):
        parameter_start = parameters[index]
        parameter_end = parameters[index + 1]
        is_full_domain = (
            abs(parameter_start - domain[0]) <= _PARAMETER_EPSILON
            and abs(parameter_end - domain[1]) <= _PARAMETER_EPSILON
        )
        if (
            not is_full_domain
            and _parameters_are_close(
                candidate_curve,
                parameter_start,
                parameter_end,
                tolerance,
            )
        ):
            continue

        middle_parameter = (parameter_start + parameter_end) * 0.5
        try:
            middle_point = candidate_curve.PointAt(middle_parameter)
        except Exception as error:
            raise RuntimeError(
                "Candidate row midpoint could not be evaluated: {0}".format(
                    error
                )
            )
        if not _point_is_inside_or_coincident(
            boundary_curve,
            plane,
            middle_point,
            tolerance,
        ):
            continue

        segment = _trimmed_curve(
            candidate_curve,
            parameter_start,
            parameter_end,
            domain,
        )
        if _curve_is_tolerance_sliver(segment, tolerance):
            continue
        segments.append(segment)
    return segments


def _project_vector_to_plane(vector, plane):
    try:
        projected = rg.Vector3d(vector)
        normal = rg.Vector3d(plane.Normal)
        if not normal.Unitize():
            raise ValueError("Boundary plane normal is invalid.")
        normal_component = rg.Vector3d.Multiply(projected, normal)
        projected = projected - normal * normal_component
        if not projected.Unitize():
            raise ValueError(
                "Audience lateral direction is perpendicular to the boundary plane."
            )
        return projected
    except ValueError:
        raise
    except Exception as error:
        raise ValueError(
            "Audience lateral direction could not be projected: {0}".format(
                error
            )
        )


def _bounding_box_line_extent(bbox, center_point, tolerance):
    try:
        if hasattr(bbox, "IsValid") and not bbox.IsValid:
            raise ValueError("Boundary bounding box is invalid.")
        diagonal_length = float(bbox.Diagonal.Length)
        center_distance = float(center_point.DistanceTo(bbox.Center))
    except ValueError:
        raise
    except Exception as error:
        raise ValueError(
            "Boundary bounding box could not be measured: {0}".format(error)
        )
    if diagonal_length <= tolerance:
        raise ValueError("Boundary bounding box is too small to build a row.")
    return center_distance + diagonal_length + tolerance * 10.0


def rectangular_row_segments(
    boundary_context,
    stage_point,
    audience_direction,
    row_x_mm,
    mm_scale,
):
    """Build a long lateral row line and clip it to the custom boundary."""
    plane = _context_value(boundary_context, "plane")
    bbox = _context_value(boundary_context, "bbox")
    tolerance = _positive_number(
        _context_value(boundary_context, "tolerance"),
        "Boundary tolerance",
    )
    scale = _positive_number(mm_scale, "Millimeter scale")
    try:
        row_distance = float(row_x_mm)
    except (TypeError, ValueError):
        raise ValueError("Row distance must be a number.")

    lateral_direction, _stage_back_direction = get_stage_directions(
        audience_direction
    )
    lateral_direction = _project_vector_to_plane(
        lateral_direction,
        plane,
    )
    try:
        row_center = point_at(
            stage_point,
            audience_direction,
            row_distance,
            0.0,
            scale,
        )
        row_center = plane.ClosestPoint(row_center)
    except Exception as error:
        raise ValueError(
            "Row center could not be placed on the boundary plane: {0}".format(
                error
            )
        )

    extent = _bounding_box_line_extent(bbox, row_center, tolerance)
    candidate_curve = rg.LineCurve(
        row_center - lateral_direction * extent,
        row_center + lateral_direction * extent,
    )
    return curve_segments_inside_boundary(
        boundary_context,
        candidate_curve,
    )


def _circle_plane_with_rear_seam(
    boundary_plane,
    center_point,
    audience_direction,
):
    forward = _project_vector_to_plane(
        audience_direction,
        boundary_plane,
    )
    seam_direction = forward * -1.0
    try:
        normal = rg.Vector3d(boundary_plane.Normal)
        if not normal.Unitize():
            raise ValueError("Boundary plane normal is invalid.")
        circle_y_direction = rg.Vector3d.CrossProduct(
            normal,
            seam_direction,
        )
        if not circle_y_direction.Unitize():
            raise ValueError("Radial row circle axes are invalid.")
        circle_plane = rg.Plane(
            center_point,
            seam_direction,
            circle_y_direction,
        )
    except ValueError:
        raise
    except Exception as error:
        raise ValueError(
            "Radial row circle plane could not be constructed: {0}".format(
                error
            )
        )
    if hasattr(circle_plane, "IsValid") and not circle_plane.IsValid:
        raise ValueError("Radial row circle plane is invalid.")
    return circle_plane


def radial_row_segments(
    boundary_context,
    layout_context,
    row_x_mm,
    mm_scale,
):
    """Build a full radial row circle and clip it to the custom boundary.

    The circle seam lies opposite the audience direction so ordinary seating
    regions around the forward axis do not cross the closed-curve seam.
    """
    plane = _context_value(boundary_context, "plane")
    tolerance = _positive_number(
        _context_value(boundary_context, "tolerance"),
        "Boundary tolerance",
    )
    if _layout_value(layout_context, "mode") != "radial":
        raise ValueError("Radial row segments require radial plan layout mode.")
    scale = _positive_number(mm_scale, "Millimeter scale")
    row_distance = _finite_number(row_x_mm, "Row distance")
    base_radius = _finite_number(
        _layout_value(layout_context, "radius"),
        "Plan layout radius",
    )
    row_radius_mm = base_radius + row_distance
    row_radius_model = row_radius_mm * scale
    if row_radius_model <= tolerance:
        raise ValueError(
            "Radial row radius must be larger than the boundary tolerance."
        )

    try:
        center_point = plane.ClosestPoint(
            _layout_value(layout_context, "center_point")
        )
    except Exception as error:
        raise ValueError(
            "Radial row center could not be placed on the boundary plane: "
            "{0}".format(error)
        )
    circle_plane = _circle_plane_with_rear_seam(
        plane,
        center_point,
        _layout_value(layout_context, "audience_direction"),
    )

    try:
        circle = rg.Circle(circle_plane, row_radius_model)
        if hasattr(circle, "IsValid") and not circle.IsValid:
            raise ValueError("Radial row circle is invalid.")
        candidate_curve = circle.ToNurbsCurve()
    except ValueError:
        raise
    except Exception as error:
        raise RuntimeError(
            "Radial row circle could not be created: {0}".format(error)
        )
    if candidate_curve is None:
        raise RuntimeError("Radial row circle conversion returned no curve.")
    return curve_segments_inside_boundary(
        boundary_context,
        candidate_curve,
    )


def segment_lateral_intervals(
    segments,
    center_point,
    lateral_direction,
    mm_scale,
):
    """Return sorted lateral-coordinate intervals for straight row segments."""
    if segments is None:
        raise ValueError("Row segments are required.")
    if center_point is None:
        raise ValueError("Row center point is required.")
    scale = _positive_number(mm_scale, "Millimeter scale")
    try:
        unit_lateral = rg.Vector3d(lateral_direction)
        if not unit_lateral.Unitize():
            raise ValueError("Lateral direction must be nonzero.")
    except ValueError:
        raise
    except Exception as error:
        raise ValueError(
            "Lateral direction is invalid: {0}".format(error)
        )

    intervals = []
    for segment in segments:
        if segment is None:
            continue
        try:
            start_offset = rg.Vector3d(segment.PointAtStart - center_point)
            end_offset = rg.Vector3d(segment.PointAtEnd - center_point)
            start_mm = (
                rg.Vector3d.Multiply(start_offset, unit_lateral) / scale
            )
            end_mm = rg.Vector3d.Multiply(end_offset, unit_lateral) / scale
        except Exception as error:
            raise ValueError(
                "Row segment endpoints could not be projected laterally: {0}".format(
                    error
                )
            )
        interval_start = min(start_mm, end_mm)
        interval_end = max(start_mm, end_mm)
        if interval_end - interval_start <= _MIN_INTERVAL_MM:
            continue
        intervals.append((interval_start, interval_end))

    intervals.sort(key=lambda interval: (interval[0], interval[1]))
    return intervals


def _signed_angle_from_forward(
    point,
    center_point,
    forward_direction,
    plane_normal,
):
    try:
        radial_direction = rg.Vector3d(point - center_point)
        radial_direction = radial_direction - plane_normal * (
            rg.Vector3d.Multiply(radial_direction, plane_normal)
        )
        if not radial_direction.Unitize():
            raise ValueError("Radial segment endpoint lies at the row center.")
        cross_product = rg.Vector3d.CrossProduct(
            forward_direction,
            radial_direction,
        )
        sine_value = rg.Vector3d.Multiply(
            cross_product,
            plane_normal,
        )
        cosine_value = rg.Vector3d.Multiply(
            forward_direction,
            radial_direction,
        )
    except ValueError:
        raise
    except Exception as error:
        raise ValueError(
            "Radial segment angle could not be measured: {0}".format(error)
        )
    return math.atan2(sine_value, cosine_value)


def _angle_nearest_reference(angle, reference_angle):
    candidates = (
        angle - math.pi * 2.0,
        angle,
        angle + math.pi * 2.0,
    )
    return min(
        candidates,
        key=lambda candidate: abs(candidate - reference_angle),
    )


def _segment_middle_point(segment):
    try:
        domain = segment.Domain
        return segment.PointAt((float(domain.T0) + float(domain.T1)) * 0.5)
    except Exception as error:
        raise ValueError(
            "Radial segment midpoint could not be evaluated: {0}".format(
                error
            )
        )


def radial_segment_lateral_intervals(
    segments,
    layout_context,
    row_x_mm,
    mm_scale,
):
    """Return signed arc-length intervals in millimeters for radial rows."""
    if segments is None:
        raise ValueError("Radial row segments are required.")
    if _layout_value(layout_context, "mode") != "radial":
        raise ValueError("Radial intervals require radial plan layout mode.")
    _positive_number(mm_scale, "Millimeter scale")
    row_distance = _finite_number(row_x_mm, "Row distance")
    row_radius_mm = _finite_number(
        _layout_value(layout_context, "radius"),
        "Plan layout radius",
    ) + row_distance
    if row_radius_mm <= 0.0:
        raise ValueError("Radial row radius must be greater than zero.")

    center_point = _layout_value(layout_context, "center_point")
    try:
        forward_direction = rg.Vector3d(
            _layout_value(layout_context, "audience_direction")
        )
        if not forward_direction.Unitize():
            raise ValueError("Audience direction must be nonzero.")
        lateral_direction = rg.Vector3d(
            _layout_value(
                layout_context,
                "audience_view_right_direction",
            )
        )
        if not lateral_direction.Unitize():
            raise ValueError("Audience lateral direction must be nonzero.")
        plane_normal = rg.Vector3d.CrossProduct(
            forward_direction,
            lateral_direction,
        )
        if not plane_normal.Unitize():
            raise ValueError("Radial plan directions are parallel.")
    except ValueError:
        raise
    except Exception as error:
        raise ValueError(
            "Radial plan directions are invalid: {0}".format(error)
        )

    intervals = []
    for segment in segments:
        if segment is None:
            continue
        try:
            is_closed = bool(segment.IsClosed)
        except Exception:
            is_closed = False
        if is_closed:
            intervals.append(
                (-math.pi * row_radius_mm, math.pi * row_radius_mm)
            )
            continue

        middle_angle = _signed_angle_from_forward(
            _segment_middle_point(segment),
            center_point,
            forward_direction,
            plane_normal,
        )
        start_angle = _signed_angle_from_forward(
            segment.PointAtStart,
            center_point,
            forward_direction,
            plane_normal,
        )
        end_angle = _signed_angle_from_forward(
            segment.PointAtEnd,
            center_point,
            forward_direction,
            plane_normal,
        )
        start_angle = _angle_nearest_reference(
            start_angle,
            middle_angle,
        )
        end_angle = _angle_nearest_reference(
            end_angle,
            middle_angle,
        )
        angle_start = min(start_angle, end_angle)
        angle_end = max(start_angle, end_angle)

        while angle_end > math.pi + _PARAMETER_EPSILON:
            angle_start -= math.pi * 2.0
            angle_end -= math.pi * 2.0
        while angle_start < -math.pi - _PARAMETER_EPSILON:
            angle_start += math.pi * 2.0
            angle_end += math.pi * 2.0
        angle_start = max(-math.pi, angle_start)
        angle_end = min(math.pi, angle_end)

        interval_start = angle_start * row_radius_mm
        interval_end = angle_end * row_radius_mm
        if interval_end - interval_start <= _MIN_INTERVAL_MM:
            continue
        intervals.append((interval_start, interval_end))

    intervals.sort(key=lambda interval: (interval[0], interval[1]))
    return intervals


def _normalized_interval_set(intervals, tolerance_mm):
    if intervals is None:
        raise ValueError("An interval set cannot be None.")
    normalized = []
    for interval in intervals:
        try:
            if len(interval) != 2:
                raise ValueError
            value_a = _finite_number(interval[0], "Interval endpoint")
            value_b = _finite_number(interval[1], "Interval endpoint")
        except (TypeError, ValueError):
            raise ValueError(
                "Each lateral interval must contain two finite numbers."
            )
        interval_start = min(value_a, value_b)
        interval_end = max(value_a, value_b)
        if interval_end - interval_start <= tolerance_mm:
            continue
        normalized.append((interval_start, interval_end))

    normalized.sort(key=lambda interval: (interval[0], interval[1]))
    merged = []
    for interval_start, interval_end in normalized:
        if (
            merged
            and interval_start <= merged[-1][1] + tolerance_mm
        ):
            merged[-1] = (
                merged[-1][0],
                max(merged[-1][1], interval_end),
            )
        else:
            merged.append((interval_start, interval_end))
    return merged


def intersect_interval_sets(interval_sets, tolerance_mm=_MIN_INTERVAL_MM):
    """Return the deterministic set intersection of lateral intervals.

    This helper is geometry-free and does not mutate any source interval set.
    Overlapping intervals within each source set are treated as one union.
    """
    if interval_sets is None:
        raise ValueError("Interval sets are required.")
    tolerance = _finite_number(
        tolerance_mm,
        "Interval intersection tolerance",
    )
    if tolerance < 0.0:
        raise ValueError(
            "Interval intersection tolerance cannot be negative."
        )

    source_sets = list(interval_sets)
    if not source_sets:
        return []
    current = _normalized_interval_set(source_sets[0], tolerance)
    for source_set in source_sets[1:]:
        other = _normalized_interval_set(source_set, tolerance)
        intersections = []
        current_index = 0
        other_index = 0
        while current_index < len(current) and other_index < len(other):
            current_interval = current[current_index]
            other_interval = other[other_index]
            overlap_start = max(
                current_interval[0],
                other_interval[0],
            )
            overlap_end = min(
                current_interval[1],
                other_interval[1],
            )
            if overlap_end - overlap_start > tolerance:
                intersections.append((overlap_start, overlap_end))

            if current_interval[1] < other_interval[1] - tolerance:
                current_index += 1
            elif other_interval[1] < current_interval[1] - tolerance:
                other_index += 1
            else:
                current_index += 1
                other_index += 1
        current = _normalized_interval_set(intersections, tolerance)
        if not current:
            return []
    return current


def _footprint_row_samples(
    row_x,
    footprint_depth_mm,
    footprint_sample_count,
):
    depth = _finite_number(
        footprint_depth_mm,
        "Seat footprint depth",
    )
    if depth < 0.0:
        raise ValueError("Seat footprint depth cannot be negative.")
    if depth <= 0.0:
        return [row_x]

    sample_count_value = _finite_number(
        footprint_sample_count,
        "Seat footprint sample count",
    )
    sample_count = int(sample_count_value)
    if abs(sample_count_value - sample_count) > _PARAMETER_EPSILON:
        raise ValueError("Seat footprint sample count must be an integer.")
    sample_count = max(2, sample_count)
    return [
        row_x
        - depth * float(sample_index) / float(sample_count - 1)
        for sample_index in range(sample_count)
    ]


def _rectangular_row_data(
    boundary_context,
    boundary_plane,
    stage_point,
    audience_direction,
    lateral_direction,
    row_x,
    mm_scale,
):
    segments = rectangular_row_segments(
        boundary_context,
        stage_point,
        audience_direction,
        row_x,
        mm_scale,
    )
    try:
        center_point = boundary_plane.ClosestPoint(
            point_at(
                stage_point,
                audience_direction,
                row_x,
                0.0,
                mm_scale,
            )
        )
    except Exception as error:
        raise ValueError(
            "Row center could not be placed on the boundary plane: "
            "{0}".format(error)
        )
    intervals = segment_lateral_intervals(
        segments,
        center_point,
        lateral_direction,
        mm_scale,
    )
    return segments, intervals


def _radial_row_data(
    boundary_context,
    layout_context,
    row_x,
    mm_scale,
):
    segments = radial_row_segments(
        boundary_context,
        layout_context,
        row_x,
        mm_scale,
    )
    intervals = radial_segment_lateral_intervals(
        segments,
        layout_context,
        row_x,
        mm_scale,
    )
    return segments, intervals


def _radial_intervals_at_anchor_radius(
    intervals,
    sample_radius_mm,
    anchor_radius_mm,
):
    sample_radius = _positive_number(
        sample_radius_mm,
        "Sample row radius",
    )
    anchor_radius = _positive_number(
        anchor_radius_mm,
        "Anchor row radius",
    )
    radius_ratio = anchor_radius / sample_radius
    return [
        (
            float(interval[0]) * radius_ratio,
            float(interval[1]) * radius_ratio,
        )
        for interval in intervals
    ]


def _tier_values(tier_result):
    if tier_result is None or not hasattr(tier_result, "get"):
        raise ValueError("Tier calculation result must be dictionary-like.")
    try:
        row_x_values = list(tier_result["x_values"])
        floor_z_values = list(tier_result["base_z_values"])
    except (KeyError, TypeError):
        raise ValueError(
            "Tier calculation result requires x_values and base_z_values."
        )
    if len(row_x_values) != len(floor_z_values):
        raise ValueError(
            "Tier row distances and floor heights must have equal lengths."
        )
    return row_x_values, floor_z_values


def build_tier_row_regions(
    boundary_context,
    layout_context,
    tier_result,
    mm_scale,
    footprint_depth_mm=0.0,
    footprint_sample_count=5,
):
    """Build boundary-clipped placement regions for every row in one tier."""
    boundary_plane = _context_value(boundary_context, "plane")
    _context_value(boundary_context, "curve")
    _context_value(boundary_context, "tolerance")
    scale = _positive_number(mm_scale, "Millimeter scale")
    mode = _layout_value(layout_context, "mode")
    if mode not in ("rectangular", "radial"):
        raise ValueError("Unsupported plan layout mode: {0}.".format(mode))
    row_x_values, floor_z_values = _tier_values(tier_result)

    stage_point = None
    audience_direction = None
    lateral_direction = None
    if mode == "rectangular":
        stage_point = _layout_value(
            layout_context,
            "reference_mid_point",
        )
        audience_direction = _layout_value(
            layout_context,
            "audience_direction",
        )
        lateral_direction, _stage_back = get_stage_directions(
            audience_direction
        )
        lateral_direction = _project_vector_to_plane(
            lateral_direction,
            boundary_plane,
        )

    regions = []
    for row_index, values in enumerate(
        zip(row_x_values, floor_z_values)
    ):
        row_x = _finite_number(values[0], "Row distance")
        floor_z = _finite_number(values[1], "Row floor height")
        sample_x_values = _footprint_row_samples(
            row_x,
            footprint_depth_mm,
            footprint_sample_count,
        )
        if mode == "radial":
            segments, intervals = _radial_row_data(
                boundary_context,
                layout_context,
                row_x,
                scale,
            )
        else:
            segments, intervals = _rectangular_row_data(
                boundary_context,
                boundary_plane,
                stage_point,
                audience_direction,
                lateral_direction,
                row_x,
                scale,
            )

        if len(sample_x_values) > 1:
            interval_sets = [intervals]
            anchor_radius = None
            if mode == "radial":
                anchor_radius = _finite_number(
                    _layout_value(layout_context, "radius"),
                    "Plan layout radius",
                ) + row_x
            for sample_x in sample_x_values[1:]:
                if mode == "radial":
                    _sample_segments, sample_intervals = _radial_row_data(
                        boundary_context,
                        layout_context,
                        sample_x,
                        scale,
                    )
                    sample_radius = _finite_number(
                        _layout_value(layout_context, "radius"),
                        "Plan layout radius",
                    ) + sample_x
                    sample_intervals = _radial_intervals_at_anchor_radius(
                        sample_intervals,
                        sample_radius,
                        anchor_radius,
                    )
                else:
                    _sample_segments, sample_intervals = (
                        _rectangular_row_data(
                            boundary_context,
                            boundary_plane,
                            stage_point,
                            audience_direction,
                            lateral_direction,
                            sample_x,
                            scale,
                        )
                    )
                interval_sets.append(sample_intervals)
            intervals = intersect_interval_sets(interval_sets)
        regions.append(
            {
                "row_index": row_index,
                "row_x": row_x,
                "floor_z": floor_z,
                "segments": segments,
                "intervals": intervals,
            }
        )
    return regions
