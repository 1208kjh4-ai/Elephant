# -*- coding: utf-8 -*-
"""Validation and plan-containment helpers for an auditorium boundary."""

import Rhino.Geometry as rg


_PARALLEL_ANGLE_TOLERANCE = 1e-8


def _normalized_tolerance(absolute_tolerance):
    try:
        tolerance = float(absolute_tolerance)
    except Exception:
        raise ValueError(
            "The auditorium boundary tolerance must be a finite number."
        )
    if (
        tolerance != tolerance
        or tolerance == float("inf")
        or tolerance == float("-inf")
    ):
        raise ValueError(
            "The auditorium boundary tolerance must be a finite number."
        )
    if tolerance <= 0.0:
        raise ValueError(
            "The auditorium boundary tolerance must be greater than zero."
        )
    return tolerance


def _copy_valid_point(point, label):
    if point is None:
        raise ValueError("{0} is required.".format(label))
    try:
        copied_point = rg.Point3d(point)
    except Exception:
        raise ValueError("{0} is not a valid point.".format(label))
    if not copied_point.IsValid:
        raise ValueError("{0} is not a valid point.".format(label))
    return copied_point


def _horizontal_plane(datum_point):
    datum = _copy_valid_point(
        datum_point,
        "The auditorium boundary datum point",
    )
    plane = rg.Plane(
        datum,
        rg.Vector3d.XAxis,
        rg.Vector3d.YAxis,
    )
    if not plane.IsValid:
        raise ValueError(
            "The horizontal auditorium boundary plane could not be created."
        )
    return plane


def _try_get_curve_plane(curve, tolerance):
    try:
        result = curve.TryGetPlane(tolerance)
    except TypeError:
        try:
            result = curve.TryGetPlane()
        except Exception:
            return False, None
    except Exception:
        return False, None

    if isinstance(result, tuple) and len(result) >= 2:
        return bool(result[0]), result[1]
    try:
        if len(result) >= 2:
            return bool(result[0]), result[1]
    except Exception:
        pass
    return False, None


def _collection_count(items):
    try:
        return int(items.Count)
    except Exception:
        return len(items)


def _curve_area(curve, tolerance):
    try:
        area_properties = rg.AreaMassProperties.Compute(
            curve,
            tolerance,
        )
    except Exception:
        area_properties = None
    if area_properties is None:
        raise ValueError(
            "The auditorium boundary area could not be calculated."
        )

    try:
        area = float(area_properties.Area)
    except Exception:
        area = float("nan")
    finally:
        try:
            area_properties.Dispose()
        except Exception:
            pass

    if (
        area != area
        or area == float("inf")
        or area == float("-inf")
        or area <= tolerance * tolerance
    ):
        raise ValueError(
            "The auditorium boundary must enclose a nontrivial positive area."
        )
    return area


def _normalize_boundary_data(curve, datum_point, absolute_tolerance):
    if curve is None:
        raise ValueError("An auditorium boundary curve is required.")

    tolerance = _normalized_tolerance(absolute_tolerance)
    try:
        curve_is_valid = bool(curve.IsValid)
    except Exception:
        curve_is_valid = False
    if not curve_is_valid:
        raise ValueError("The auditorium boundary curve is not valid.")

    try:
        curve_is_closed = bool(curve.IsClosed)
    except Exception:
        curve_is_closed = False
    if not curve_is_closed:
        raise ValueError("The auditorium boundary curve must be closed.")

    is_planar, source_plane = _try_get_curve_plane(curve, tolerance)
    if (
        not is_planar
        or source_plane is None
        or not source_plane.IsValid
    ):
        raise ValueError("The auditorium boundary curve must be planar.")

    try:
        parallel_direction = source_plane.Normal.IsParallelTo(
            rg.Vector3d.ZAxis,
            _PARALLEL_ANGLE_TOLERANCE,
        )
    except Exception:
        parallel_direction = 0
    if parallel_direction == 0:
        raise ValueError(
            "The auditorium boundary plane must be horizontal."
        )

    plane = _horizontal_plane(datum_point)
    try:
        duplicate = curve.DuplicateCurve()
    except Exception:
        duplicate = None
    if duplicate is None:
        raise ValueError(
            "The auditorium boundary curve could not be duplicated."
        )

    try:
        normalized_curve = rg.Curve.ProjectToPlane(duplicate, plane)
    except Exception:
        normalized_curve = None
    if normalized_curve is None:
        raise ValueError(
            "The auditorium boundary curve could not be projected "
            "to the horizontal datum plane."
        )
    if not normalized_curve.IsValid or not normalized_curve.IsClosed:
        raise ValueError(
            "The projected auditorium boundary is not a valid closed curve."
        )

    try:
        self_intersections = rg.Intersect.Intersection.CurveSelf(
            normalized_curve,
            tolerance,
        )
    except Exception:
        self_intersections = None
    if self_intersections is None:
        raise ValueError(
            "The auditorium boundary self-intersection check failed."
        )
    if _collection_count(self_intersections) > 0:
        raise ValueError(
            "The auditorium boundary curve must not intersect itself."
        )

    area = _curve_area(normalized_curve, tolerance)
    try:
        bounding_box = normalized_curve.GetBoundingBox(True)
    except Exception:
        bounding_box = None
    if bounding_box is None or not bounding_box.IsValid:
        raise ValueError(
            "The auditorium boundary bounding box could not be calculated."
        )

    return {
        "curve": normalized_curve,
        "plane": plane,
        "bbox": bounding_box,
        "area": area,
        "tolerance": tolerance,
    }


def normalize_boundary_curve(curve, datum_point, absolute_tolerance):
    """Return a validated copy projected to the datum point's XY plane."""
    return _normalize_boundary_data(
        curve,
        datum_point,
        absolute_tolerance,
    )["curve"]


def build_boundary_context(curve, datum_point, absolute_tolerance):
    """Build immutable-by-convention plan data for an optional boundary."""
    if curve is None:
        return None
    return _normalize_boundary_data(
        curve,
        datum_point,
        absolute_tolerance,
    )


def _containment_context_values(context):
    try:
        curve = context["curve"]
        plane = context["plane"]
        tolerance = _normalized_tolerance(context["tolerance"])
    except (KeyError, TypeError):
        raise ValueError("The auditorium boundary context is incomplete.")
    if curve is None or plane is None:
        raise ValueError("The auditorium boundary context is incomplete.")
    return curve, plane, tolerance


def boundary_contains_point(context, point, include_boundary=True):
    """Return whether a point's plan projection lies inside the boundary."""
    if context is None:
        return True

    curve, plane, tolerance = _containment_context_values(context)
    test_point = _copy_valid_point(point, "The boundary test point")
    try:
        planar_point = plane.ClosestPoint(test_point)
    except Exception:
        raise ValueError(
            "The boundary test point could not be projected to the plan."
        )
    if planar_point is None or not planar_point.IsValid:
        raise ValueError(
            "The boundary test point could not be projected to the plan."
        )

    try:
        containment = curve.Contains(
            planar_point,
            plane,
            tolerance,
        )
    except Exception:
        raise ValueError(
            "The auditorium boundary containment check failed."
        )

    if containment == rg.PointContainment.Inside:
        return True
    if containment == rg.PointContainment.Coincident:
        return bool(include_boundary)
    if containment == rg.PointContainment.Outside:
        return False
    raise ValueError(
        "The auditorium boundary containment could not be determined."
    )


def boundary_contains_points(context, points, include_boundary=True):
    """Return True when every point's plan projection is in the boundary."""
    if context is None:
        return True
    if points is None:
        raise ValueError("Boundary test points are required.")
    try:
        iterator = iter(points)
    except TypeError:
        raise ValueError("Boundary test points must be an iterable collection.")

    for point in iterator:
        if not boundary_contains_point(
            context,
            point,
            include_boundary,
        ):
            return False
    return True
