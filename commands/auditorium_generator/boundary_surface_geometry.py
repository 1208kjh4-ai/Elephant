# -*- coding: utf-8 -*-
"""Surface and Brep helpers for an optional auditorium plan boundary."""

import Rhino.Geometry as rg

from .auditorium_boundary import boundary_contains_point


def _finite_number(value, label):
    try:
        number = float(value)
    except Exception:
        raise ValueError("{0} must be a finite number.".format(label))
    if (
        number != number
        or number == float("inf")
        or number == float("-inf")
    ):
        raise ValueError("{0} must be a finite number.".format(label))
    return number


def _positive_number(value, label):
    number = _finite_number(value, label)
    if number <= 0.0:
        raise ValueError("{0} must be greater than zero.".format(label))
    return number


def _context_value(boundary_context, key):
    if boundary_context is None or not hasattr(boundary_context, "get"):
        raise ValueError("Boundary context must be a dictionary-like object.")
    value = boundary_context.get(key)
    if value is None:
        raise ValueError(
            "Boundary context is missing required value: {0}.".format(key)
        )
    return value


def _boundary_curve(boundary_context):
    curve = _context_value(boundary_context, "curve")
    try:
        is_valid = bool(curve.IsValid)
        is_closed = bool(curve.IsClosed)
    except Exception:
        is_valid = False
        is_closed = False
    if not is_valid or not is_closed:
        raise ValueError(
            "Boundary context curve must be a valid closed curve."
        )
    return curve


def _boundary_plane(boundary_context):
    plane = _context_value(boundary_context, "plane")
    try:
        is_valid = bool(plane.IsValid)
    except Exception:
        is_valid = False
    if not is_valid:
        raise ValueError("Boundary context plane is not valid.")
    return plane


def _resolved_tolerance(boundary_context, absolute_tolerance):
    value = (
        _context_value(boundary_context, "tolerance")
        if absolute_tolerance is None
        else absolute_tolerance
    )
    return _positive_number(value, "Boundary tolerance")


def _copy_valid_point(point, label):
    if point is None:
        raise ValueError("{0} is required.".format(label))
    try:
        copied = rg.Point3d(point)
    except Exception:
        raise ValueError("{0} is not a valid point.".format(label))
    if not copied.IsValid:
        raise ValueError("{0} is not a valid point.".format(label))
    return copied


def _horizontal_unit_vector(vector, label):
    if vector is None:
        raise ValueError("{0} is required.".format(label))
    try:
        copied = rg.Vector3d(vector)
        copied.Z = 0.0
        if not copied.Unitize():
            raise ValueError(
                "{0} must have a nonzero horizontal component.".format(
                    label
                )
            )
    except ValueError:
        raise
    except Exception:
        raise ValueError("{0} is not a valid vector.".format(label))
    return copied


def _local_bbox(curve, plane, label):
    try:
        bbox = curve.GetBoundingBox(plane)
    except Exception as error:
        raise ValueError(
            "{0} bounding box could not be calculated: {1}".format(
                label,
                error,
            )
        )
    if bbox is None or not bbox.IsValid:
        raise ValueError("{0} bounding box is not valid.".format(label))
    return bbox


def calculate_boundary_max_radius(
    boundary_context,
    radial_center_point,
    mm_scale,
):
    """Return a conservative boundary-enclosing radius in millimeters.

    The farthest corner of a tight, radial-center-based planar bounding box is
    used.  This can be slightly larger than the mathematical curve maximum,
    which is intentional for candidate-geometry and cutter construction.
    """
    curve = _boundary_curve(boundary_context)
    center = _copy_valid_point(
        radial_center_point,
        "Radial center point",
    )
    scale = _positive_number(mm_scale, "Millimeter scale")
    radial_plane = rg.Plane(
        center,
        rg.Vector3d.XAxis,
        rg.Vector3d.YAxis,
    )
    if not radial_plane.IsValid:
        raise ValueError("Radial measurement plane could not be created.")
    bbox = _local_bbox(curve, radial_plane, "Boundary radial")
    try:
        maximum_x = max(abs(float(bbox.Min.X)), abs(float(bbox.Max.X)))
        maximum_y = max(abs(float(bbox.Min.Y)), abs(float(bbox.Max.Y)))
        radius = (maximum_x * maximum_x + maximum_y * maximum_y) ** 0.5
    except Exception:
        raise ValueError("Boundary radial bounding box could not be measured.")
    return radius / scale


def calculate_boundary_plan_extents(
    boundary_context,
    stage_point,
    audience_direction,
    mm_scale,
    radial_center_point=None,
):
    """Return stage-local longitudinal and lateral extents in millimeters."""
    curve = _boundary_curve(boundary_context)
    origin = _copy_valid_point(stage_point, "Stage point")
    scale = _positive_number(mm_scale, "Millimeter scale")
    longitudinal = _horizontal_unit_vector(
        audience_direction,
        "Audience direction",
    )
    try:
        lateral = rg.Vector3d.CrossProduct(
            rg.Vector3d.ZAxis,
            longitudinal,
        )
        if not lateral.Unitize():
            raise ValueError
        local_plane = rg.Plane(origin, longitudinal, lateral)
    except Exception:
        raise ValueError(
            "Stage-local auditorium measurement plane could not be created."
        )
    if not local_plane.IsValid:
        raise ValueError(
            "Stage-local auditorium measurement plane is not valid."
        )

    bbox = _local_bbox(curve, local_plane, "Boundary stage-local")
    try:
        minimum_longitudinal = float(bbox.Min.X) / scale
        maximum_longitudinal = float(bbox.Max.X) / scale
        minimum_lateral = float(bbox.Min.Y) / scale
        maximum_lateral = float(bbox.Max.Y) / scale
    except Exception:
        raise ValueError(
            "Boundary stage-local bounding box could not be measured."
        )

    result = {
        "min_longitudinal_mm": minimum_longitudinal,
        "max_longitudinal_mm": maximum_longitudinal,
        "min_lateral_mm": minimum_lateral,
        "max_lateral_mm": maximum_lateral,
        "longitudinal_span_mm": (
            maximum_longitudinal - minimum_longitudinal
        ),
        "lateral_span_mm": maximum_lateral - minimum_lateral,
    }
    if radial_center_point is not None:
        result["max_radius_mm"] = calculate_boundary_max_radius(
            boundary_context,
            radial_center_point,
            scale,
        )
    return result


def _curve_at_world_z(boundary_context, world_z):
    curve = _boundary_curve(boundary_context)
    plane = _boundary_plane(boundary_context)
    target_z = _finite_number(world_z, "Target world Z")
    try:
        duplicate = curve.DuplicateCurve()
    except Exception:
        duplicate = None
    if duplicate is None:
        raise ValueError("Boundary curve could not be duplicated.")

    try:
        translation = rg.Transform.Translation(
            rg.Vector3d(
                0.0,
                0.0,
                target_z - float(plane.Origin.Z),
            )
        )
        transformed = duplicate.Transform(translation)
    except Exception:
        transformed = False
    if not transformed:
        raise ValueError("Boundary curve could not be moved to target world Z.")
    if not duplicate.IsValid or not duplicate.IsClosed:
        raise ValueError(
            "Moved boundary curve is not a valid closed curve."
        )
    return duplicate


def build_boundary_ceiling_brep(
    boundary_context,
    world_z,
    absolute_tolerance=None,
):
    """Create one planar ceiling Brep from the boundary at a world Z."""
    tolerance = _resolved_tolerance(
        boundary_context,
        absolute_tolerance,
    )
    ceiling_curve = _curve_at_world_z(boundary_context, world_z)
    try:
        planar_breps = rg.Brep.CreatePlanarBreps(
            ceiling_curve,
            tolerance,
        )
    except Exception:
        planar_breps = None
    if planar_breps is None or len(planar_breps) != 1:
        raise ValueError(
            "Boundary ceiling could not be created as one planar Brep."
        )
    ceiling_brep = planar_breps[0]
    if ceiling_brep is None or not ceiling_brep.IsValid:
        raise ValueError("Boundary ceiling Brep is not valid.")
    return ceiling_brep


def _build_vertical_extrusion(
    boundary_context,
    min_world_z,
    max_world_z,
    cap,
    absolute_tolerance=None,
):
    minimum_z = _finite_number(min_world_z, "Minimum world Z")
    maximum_z = _finite_number(max_world_z, "Maximum world Z")
    tolerance = _resolved_tolerance(
        boundary_context,
        absolute_tolerance,
    )
    if maximum_z - minimum_z <= tolerance:
        raise ValueError(
            "Maximum world Z must exceed minimum world Z by more than "
            "the boundary tolerance."
        )

    profile = _curve_at_world_z(boundary_context, minimum_z)
    context_plane = _boundary_plane(boundary_context)
    try:
        extrusion_origin = rg.Point3d(
            context_plane.Origin.X,
            context_plane.Origin.Y,
            minimum_z,
        )
        extrusion_plane = rg.Plane(
            extrusion_origin,
            context_plane.XAxis,
            context_plane.YAxis,
        )
        extrusion = rg.Extrusion.Create(
            profile,
            extrusion_plane,
            maximum_z - minimum_z,
            bool(cap),
        )
    except Exception:
        extrusion = None
    if extrusion is None:
        raise ValueError("Boundary vertical extrusion could not be created.")
    try:
        brep = extrusion.ToBrep()
    except Exception:
        brep = None
    finally:
        try:
            extrusion.Dispose()
        except Exception:
            pass
    if brep is None or not brep.IsValid:
        raise ValueError("Boundary vertical extrusion Brep is not valid.")
    return brep


def build_boundary_vertical_cutter(
    boundary_context,
    min_world_z,
    max_world_z,
    absolute_tolerance=None,
):
    """Create a capped vertical boundary solid suitable for Brep splitting."""
    cutter = _build_vertical_extrusion(
        boundary_context,
        min_world_z,
        max_world_z,
        True,
        absolute_tolerance,
    )
    if not cutter.IsSolid:
        raise ValueError("Boundary vertical cutter is not a closed solid.")
    try:
        if cutter.SolidOrientation == rg.BrepSolidOrientation.Inward:
            cutter.Flip()
    except Exception:
        # Rhino-created capped extrusions normally arrive outward-oriented.
        # Older test doubles and unusual geometry may not expose orientation.
        pass
    return cutter


def build_boundary_perimeter_wall_brep(
    boundary_context,
    min_world_z,
    max_world_z,
    absolute_tolerance=None,
):
    """Create the full closed perimeter wall shell without top or bottom.

    No opening or stage-interface policy is applied here.  Integration code
    must decide whether and where this complete wall shell should be trimmed.
    """
    return _build_vertical_extrusion(
        boundary_context,
        min_world_z,
        max_world_z,
        False,
        absolute_tolerance,
    )


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
    try:
        if len(result) >= 2:
            return bool(result[0]), result[1]
    except Exception:
        pass
    return False, None


def extrude_wall_curve(
    curve,
    min_world_z,
    max_world_z,
    absolute_tolerance,
):
    """Extrude one horizontal open or closed curve as a vertical wall Brep.

    A closed input produces the complete perimeter wall shell.  An open input
    produces only that segment's wall, allowing integration code to omit the
    stage opening before calling this helper.  No caps are added.
    """
    if curve is None:
        raise ValueError("A wall source curve is required.")
    try:
        curve_is_valid = bool(curve.IsValid)
    except Exception:
        curve_is_valid = False
    if not curve_is_valid:
        raise ValueError("Wall source curve is not valid.")

    tolerance = _positive_number(
        absolute_tolerance,
        "Wall extrusion tolerance",
    )
    minimum_z = _finite_number(min_world_z, "Minimum world Z")
    maximum_z = _finite_number(max_world_z, "Maximum world Z")
    if maximum_z - minimum_z <= tolerance:
        raise ValueError(
            "Maximum world Z must exceed minimum world Z by more than "
            "the wall extrusion tolerance."
        )

    is_planar, source_plane = _try_get_curve_plane(curve, tolerance)
    if (
        not is_planar
        or source_plane is None
        or not source_plane.IsValid
    ):
        raise ValueError("Wall source curve must be planar.")
    try:
        parallel = source_plane.Normal.IsParallelTo(
            rg.Vector3d.ZAxis,
            1e-8,
        )
    except Exception:
        parallel = 0
    if parallel == 0:
        raise ValueError("Wall source curve must lie in a horizontal plane.")

    try:
        profile = curve.DuplicateCurve()
    except Exception:
        profile = None
    if profile is None:
        raise ValueError("Wall source curve could not be duplicated.")
    try:
        move_to_minimum = rg.Transform.Translation(
            rg.Vector3d(
                0.0,
                0.0,
                minimum_z - float(source_plane.Origin.Z),
            )
        )
        moved = profile.Transform(move_to_minimum)
    except Exception:
        moved = False
    if not moved:
        raise ValueError("Wall source curve could not be moved vertically.")

    try:
        surface = rg.Surface.CreateExtrusion(
            profile,
            rg.Vector3d(0.0, 0.0, maximum_z - minimum_z),
        )
    except Exception:
        surface = None
    if surface is None:
        raise ValueError("Vertical wall surface could not be created.")
    try:
        wall_brep = surface.ToBrep()
    except Exception:
        wall_brep = None
    finally:
        try:
            surface.Dispose()
        except Exception:
            pass
    if wall_brep is None or not wall_brep.IsValid:
        raise ValueError("Vertical wall Brep is not valid.")
    return wall_brep


def _mass_properties_centroid(properties):
    if properties is None:
        return None
    try:
        centroid = rg.Point3d(properties.Centroid)
        return centroid if centroid.IsValid else None
    except Exception:
        return None
    finally:
        try:
            properties.Dispose()
        except Exception:
            pass


def _representative_brep_centroid(brep):
    try:
        is_solid = bool(brep.IsSolid)
    except Exception:
        is_solid = False
    if is_solid:
        try:
            volume_properties = rg.VolumeMassProperties.Compute(brep)
        except Exception:
            volume_properties = None
        centroid = _mass_properties_centroid(volume_properties)
        if centroid is not None:
            return centroid

    try:
        area_properties = rg.AreaMassProperties.Compute(brep)
    except Exception:
        area_properties = None
    centroid = _mass_properties_centroid(area_properties)
    if centroid is not None:
        return centroid

    bbox = None
    try:
        bbox = brep.GetBoundingBox(True)
        centroid = rg.Point3d(bbox.Center)
    except Exception:
        centroid = None
    if (
        bbox is None
        or not bbox.IsValid
        or centroid is None
        or not centroid.IsValid
    ):
        raise ValueError("Brep representative centroid could not be calculated.")
    return centroid


def _dispose_geometry(geometry):
    try:
        geometry.Dispose()
    except Exception:
        pass


def split_brep_inside_boundary(
    source_brep,
    cutter_brep,
    boundary_context,
    absolute_tolerance=None,
):
    """Trim a Brep to the boundary, with split/centroid compatibility fallback.

    Rhino's oriented closed-cutter trim is attempted on a duplicate first.
    If trimming fails, splitting and representative-centroid classification
    preserve compatibility with surfaces that do not support that operation.
    """
    if source_brep is None:
        raise ValueError("A source Brep is required.")
    if cutter_brep is None:
        raise ValueError("A boundary cutter Brep is required.")
    try:
        source_is_valid = bool(source_brep.IsValid)
        cutter_is_valid = bool(cutter_brep.IsValid)
    except Exception:
        source_is_valid = False
        cutter_is_valid = False
    if not source_is_valid:
        raise ValueError("Source Brep is not valid.")
    if not cutter_is_valid:
        raise ValueError("Boundary cutter Brep is not valid.")

    tolerance = _resolved_tolerance(
        boundary_context,
        absolute_tolerance,
    )
    try:
        duplicate = source_brep.DuplicateBrep()
    except Exception:
        duplicate = None
    if duplicate is None or not duplicate.IsValid:
        raise ValueError("Source Brep could not be duplicated.")

    # RhinoCommon's oriented Brep.Trim keeps the portion inside a closed
    # cutter directly. This is more reliable for concave boundaries than
    # selecting Split pieces by a single centroid. Keep the older split path
    # only as a compatibility fallback for trim failures.
    try:
        trimmed_pieces = duplicate.Trim(cutter_brep, tolerance)
    except Exception:
        trimmed_pieces = None
    valid_trimmed_pieces = []
    if trimmed_pieces:
        for piece in trimmed_pieces:
            try:
                if piece is not None and piece.IsValid:
                    valid_trimmed_pieces.append(piece)
            except Exception:
                continue
    if valid_trimmed_pieces:
        try:
            duplicate.Dispose()
        except Exception:
            pass
        return valid_trimmed_pieces

    try:
        split_pieces = duplicate.Split(cutter_brep, tolerance)
    except Exception:
        split_pieces = None
    candidates = []
    if split_pieces:
        for piece in split_pieces:
            try:
                if piece is not None and piece.IsValid:
                    candidates.append(piece)
                elif piece is not None:
                    _dispose_geometry(piece)
            except Exception:
                if piece is not None:
                    _dispose_geometry(piece)
                continue
    if not candidates:
        candidates = [duplicate]
    elif not any(piece is duplicate for piece in candidates):
        _dispose_geometry(duplicate)

    inside_pieces = []
    for piece in candidates:
        centroid = _representative_brep_centroid(piece)
        if boundary_contains_point(
            boundary_context,
            centroid,
            include_boundary=True,
        ):
            inside_pieces.append(piece)
        else:
            _dispose_geometry(piece)
    return inside_pieces
