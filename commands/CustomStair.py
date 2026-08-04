# -*- coding: utf-8 -*-
"""
CustomStair.py
Rhino 8 / IronPython 2.7

Creates a free-form stair from one closed outer boundary and multiple open
riser/divider curves selected together.

Core workflow:
    Select curves -> classify -> normalize to a local XY plane
    -> build Boolean regions -> build adjacency graph -> order regions
    -> preview -> create stair geometry.
"""

import math

import Rhino
import Rhino.Geometry as rg
import Rhino.Input.Custom as ric
import Rhino.DocObjects as rdo
import Rhino.Display as rdisplay
import Rhino.UI
import scriptcontext as sc
import System

import Eto.Forms as forms
import Eto.Drawing as drawing

from System.Drawing import Color
from Rhino.UI import RhinoEtoApp, EtoExtensions


COMMAND_NAME = "CustomStair"
OUTPUT_LAYER = "CustomStair"
STICKY_KEY = "ElephantTools.CustomStair.LastSettings"

MODE_SURFACE = 0
MODE_FIXED_THICKNESS = 1
MODE_FILLED_MASS = 2

CALC_BY_TREADS = 0
CALC_BY_TREADS_PLUS_ONE = 1


# -----------------------------------------------------------------------------
# Data containers
# -----------------------------------------------------------------------------

class StairRegion(object):
    def __init__(self, region_id, curves, brep, centroid, area):
        self.id = region_id
        self.curves = [c.DuplicateCurve() for c in curves]
        self.brep = brep.DuplicateBrep()
        self.centroid = rg.Point3d(centroid)
        self.area = area
        self.neighbors = set()


class StairAnalysis(object):
    def __init__(self):
        self.is_valid = False
        self.errors = []
        self.warnings = []
        self.bad_divider_indices = set()

        self.source_ids = []
        self.outer_source_id = None
        self.divider_source_ids = []

        self.original_plane = rg.Plane.WorldXY
        self.to_xy = rg.Transform.Identity
        self.from_xy = rg.Transform.Identity

        self.outer = None
        self.dividers = []
        self.regions = []
        self.edges = []
        self.divider_edges = {}
        self.ordered_region_ids = []
        self.offset_epsilon = 0.0


class StairSettings(object):
    def __init__(self):
        self.floor_height = 3000.0
        self.calc_mode = CALC_BY_TREADS_PLUS_ONE
        self.geometry_mode = MODE_FIXED_THICKNESS
        self.tread_thickness = 50.0
        self.flipped = False
        self.z_flipped = False

    def copy(self):
        other = StairSettings()
        other.floor_height = self.floor_height
        other.calc_mode = self.calc_mode
        other.geometry_mode = self.geometry_mode
        other.tread_thickness = self.tread_thickness
        other.flipped = self.flipped
        other.z_flipped = self.z_flipped
        return other


# -----------------------------------------------------------------------------
# General helpers
# -----------------------------------------------------------------------------

def _show_message(message, title=COMMAND_NAME):
    Rhino.UI.Dialogs.ShowMessage(message, title)


def _try_get_plane(curve, tolerance):
    try:
        ok, plane = curve.TryGetPlane(tolerance)
        return ok, plane
    except Exception:
        try:
            ok, plane = curve.TryGetPlane()
            return ok, plane
        except Exception:
            return False, rg.Plane.Unset


def _point_containment(curve, point, tolerance):
    try:
        return curve.Contains(point, rg.Plane.WorldXY, tolerance)
    except Exception:
        return curve.Contains(point)


def _is_inside_closed_curve(curve, point, tolerance, allow_coincident=True):
    containment = _point_containment(curve, point, tolerance)
    if containment == rg.PointContainment.Inside:
        return True
    if allow_coincident and containment == rg.PointContainment.Coincident:
        return True
    return False


def _region_contains(region, point, tolerance):
    if not region.curves:
        return False
    if not _is_inside_closed_curve(region.curves[0], point, tolerance, False):
        return False
    # RegionCurves returns the outer boundary first, then possible holes.
    for hole in region.curves[1:]:
        if _is_inside_closed_curve(hole, point, tolerance, True):
            return False
    return True


def _find_region_index(regions, point, tolerance):
    for index, region in enumerate(regions):
        if _region_contains(region, point, tolerance):
            return index
    return None


def _curve_parameter_is_endpoint(curve, parameter, point, tolerance):
    endpoint_tolerance = max(tolerance * 5.0, 1e-8)
    if point.DistanceTo(curve.PointAtStart) <= endpoint_tolerance:
        return True
    if point.DistanceTo(curve.PointAtEnd) <= endpoint_tolerance:
        return True
    domain = curve.Domain
    parameter_span = max(abs(domain.Length), 1.0)
    if abs(parameter - domain.T0) <= parameter_span * 1e-9:
        return True
    if abs(parameter - domain.T1) <= parameter_span * 1e-9:
        return True
    return False


def _unique_sorted_parameters(parameters, domain):
    values = []
    parameter_tolerance = max(abs(domain.Length) * 1e-10, 1e-12)
    for value in sorted(parameters):
        if value < domain.T0 - parameter_tolerance:
            continue
        if value > domain.T1 + parameter_tolerance:
            continue
        if not values or abs(value - values[-1]) > parameter_tolerance:
            values.append(value)
    return values


def _get_intersection_parameter_a(event):
    try:
        return event.ParameterA
    except Exception:
        return None


def _snap_curve_endpoint(curve, at_start, target):
    try:
        if at_start:
            if curve.SetStartPoint(target):
                return curve
        else:
            if curve.SetEndPoint(target):
                return curve
    except Exception:
        pass

    try:
        nurbs = curve.ToNurbsCurve()
        if at_start:
            nurbs.SetStartPoint(target)
        else:
            nurbs.SetEndPoint(target)
        return nurbs
    except Exception:
        return curve


def _snap_divider_endpoints(dividers, outer, tolerance):
    snap_tolerance = tolerance * 2.0
    snapped = []

    # Snap near-boundary endpoints to the boundary.
    for divider in dividers:
        current = divider.DuplicateCurve()
        for at_start in (True, False):
            point = current.PointAtStart if at_start else current.PointAtEnd
            try:
                ok, parameter = outer.ClosestPoint(point)
            except Exception:
                ok = False
                parameter = None
            if ok:
                target = outer.PointAt(parameter)
                if point.DistanceTo(target) <= snap_tolerance:
                    current = _snap_curve_endpoint(current, at_start, target)
        snapped.append(current)

    # Cluster divider endpoints that are already within tolerance.
    endpoint_records = []
    for index, curve in enumerate(snapped):
        endpoint_records.append([index, True, curve.PointAtStart])
        endpoint_records.append([index, False, curve.PointAtEnd])

    used = set()
    for record_index, record in enumerate(endpoint_records):
        if record_index in used:
            continue
        cluster = [record_index]
        used.add(record_index)
        base_point = record[2]
        for other_index in range(record_index + 1, len(endpoint_records)):
            if other_index in used:
                continue
            if base_point.DistanceTo(endpoint_records[other_index][2]) <= snap_tolerance:
                cluster.append(other_index)
                used.add(other_index)
        if len(cluster) < 2:
            continue

        sum_x = 0.0
        sum_y = 0.0
        sum_z = 0.0
        for item_index in cluster:
            point = endpoint_records[item_index][2]
            sum_x += point.X
            sum_y += point.Y
            sum_z += point.Z
        count = float(len(cluster))
        average = rg.Point3d(sum_x / count, sum_y / count, sum_z / count)

        for item_index in cluster:
            divider_index, at_start, _ = endpoint_records[item_index]
            snapped[divider_index] = _snap_curve_endpoint(
                snapped[divider_index], at_start, average
            )

    return snapped


def _clip_dividers_to_outer(dividers, outer, tolerance, analysis):
    """Return one analysis-only curve segment inside the outer loop per divider."""
    clipped = []

    for divider_index, divider in enumerate(dividers):
        parameters = [divider.Domain.T0, divider.Domain.T1]
        overlaps_outer = False
        try:
            intersections = rg.Intersect.Intersection.CurveCurve(
                divider, outer, tolerance, tolerance
            )
        except Exception:
            intersections = None

        if intersections:
            for event in intersections:
                try:
                    if event.IsOverlap:
                        overlaps_outer = True
                        parameters.append(event.OverlapA.T0)
                        parameters.append(event.OverlapA.T1)
                    elif event.IsPoint:
                        parameter = _get_intersection_parameter_a(event)
                        if parameter is not None:
                            parameters.append(parameter)
                except Exception:
                    parameter = _get_intersection_parameter_a(event)
                    if parameter is not None:
                        parameters.append(parameter)

        if overlaps_outer:
            analysis.bad_divider_indices.add(divider_index)
            analysis.errors.append(
                u"단차선 {0}번이 계단 외곽선과 일부 겹쳐 있습니다.".format(
                    divider_index + 1
                )
            )
            clipped.append(divider.DuplicateCurve())
            continue

        parameters = _unique_sorted_parameters(parameters, divider.Domain)
        inside_segments = []
        for parameter_index in range(len(parameters) - 1):
            parameter_a = parameters[parameter_index]
            parameter_b = parameters[parameter_index + 1]
            if abs(parameter_b - parameter_a) <= 1e-12:
                continue

            middle_parameter = (parameter_a + parameter_b) * 0.5
            middle_point = divider.PointAt(middle_parameter)
            if not _is_inside_closed_curve(outer, middle_point, tolerance, False):
                continue

            try:
                segment = divider.Trim(rg.Interval(parameter_a, parameter_b))
            except Exception:
                segment = None
            if segment is None:
                continue
            try:
                if segment.GetLength() <= tolerance:
                    continue
            except Exception:
                pass
            inside_segments.append(segment)

        if not inside_segments:
            analysis.bad_divider_indices.add(divider_index)
            analysis.errors.append(
                u"단차선 {0}번에서 외곽선 내부 구간을 찾지 못했습니다.".format(
                    divider_index + 1
                )
            )
            clipped.append(divider.DuplicateCurve())
            continue

        if len(inside_segments) > 1:
            analysis.bad_divider_indices.add(divider_index)
            analysis.errors.append(
                u"단차선 {0}번이 외곽 영역을 여러 구간으로 통과합니다.".format(
                    divider_index + 1
                )
            )
            clipped.append(divider.DuplicateCurve())
            continue

        clipped.append(inside_segments[0])

    return clipped


def _curve_world_copy(local_curve, from_xy):
    copy_curve = local_curve.DuplicateCurve()
    copy_curve.Transform(from_xy)
    return copy_curve


def _brep_world_copy(local_brep, from_xy):
    copy_brep = local_brep.DuplicateBrep()
    copy_brep.Transform(from_xy)
    return copy_brep


def _ensure_output_layer(doc):
    layer_index = -1
    try:
        layer_index = doc.Layers.FindByFullPath(OUTPUT_LAYER, -1)
    except Exception:
        try:
            existing = doc.Layers.FindName(OUTPUT_LAYER)
            layer_index = existing.Index if existing is not None else -1
        except Exception:
            layer_index = -1
    if layer_index >= 0:
        return layer_index
    layer = rdo.Layer()
    layer.Name = OUTPUT_LAYER
    layer.Color = Color.FromArgb(180, 180, 180)
    return doc.Layers.Add(layer)


def _load_last_settings():
    settings = StairSettings()
    data = sc.sticky.get(STICKY_KEY)
    if not isinstance(data, dict):
        return settings
    try:
        settings.floor_height = float(data.get("floor_height", settings.floor_height))
        settings.calc_mode = int(data.get("calc_mode", settings.calc_mode))
        settings.geometry_mode = int(data.get("geometry_mode", settings.geometry_mode))
        settings.tread_thickness = float(data.get("tread_thickness", settings.tread_thickness))
    except Exception:
        pass
    settings.flipped = False
    settings.z_flipped = False
    return settings


def _save_last_settings(settings):
    sc.sticky[STICKY_KEY] = {
        "floor_height": settings.floor_height,
        "calc_mode": settings.calc_mode,
        "geometry_mode": settings.geometry_mode,
        "tread_thickness": settings.tread_thickness,
    }


# -----------------------------------------------------------------------------
# Input collection and source reading
# -----------------------------------------------------------------------------

def select_input_curves():
    getter = ric.GetObject()
    getter.SetCommandPrompt(
        u"닫힌 계단 외곽선 1개와 열린 단차선들을 함께 선택하세요"
    )
    getter.GeometryFilter = rdo.ObjectType.Curve
    getter.SubObjectSelect = False
    getter.GroupSelect = True
    getter.EnablePreSelect(True, True)
    getter.GetMultiple(2, 0)

    if getter.CommandResult() != Rhino.Commands.Result.Success:
        return None

    object_ids = []
    for index in range(getter.ObjectCount):
        object_ids.append(getter.Object(index).ObjectId)
    return object_ids


def read_source_curves(object_ids):
    records = []
    missing = []
    for object_id in object_ids:
        rhino_object = sc.doc.Objects.FindId(object_id)
        if rhino_object is None or not isinstance(rhino_object.Geometry, rg.Curve):
            missing.append(object_id)
            continue
        records.append((object_id, rhino_object.Geometry.DuplicateCurve()))
    return records, missing


# -----------------------------------------------------------------------------
# Analysis engine
# -----------------------------------------------------------------------------

def _validate_divider_intersections(dividers, tolerance, analysis):
    for index_a in range(len(dividers)):
        curve_a = dividers[index_a]
        for index_b in range(index_a + 1, len(dividers)):
            curve_b = dividers[index_b]
            try:
                intersections = rg.Intersect.Intersection.CurveCurve(
                    curve_a, curve_b, tolerance, tolerance
                )
            except Exception:
                intersections = None

            if not intersections:
                continue

            for event in intersections:
                try:
                    is_overlap = event.IsOverlap
                except Exception:
                    is_overlap = False

                if is_overlap:
                    analysis.bad_divider_indices.add(index_a)
                    analysis.bad_divider_indices.add(index_b)
                    analysis.errors.append(
                        u"단차선 {0}번과 {1}번이 겹쳐 있습니다.".format(
                            index_a + 1, index_b + 1
                        )
                    )
                    continue

                try:
                    is_point = event.IsPoint
                except Exception:
                    is_point = True

                if not is_point:
                    continue

                try:
                    point_a = event.PointA
                except Exception:
                    point_a = curve_a.PointAt(event.ParameterA)
                try:
                    point_b = event.PointB
                except Exception:
                    point_b = curve_b.PointAt(event.ParameterB)

                endpoint_a = _curve_parameter_is_endpoint(
                    curve_a, event.ParameterA, point_a, tolerance
                )
                endpoint_b = _curve_parameter_is_endpoint(
                    curve_b, event.ParameterB, point_b, tolerance
                )

                # Only endpoint-to-endpoint meetings are accepted.
                if not (endpoint_a and endpoint_b):
                    analysis.bad_divider_indices.add(index_a)
                    analysis.bad_divider_indices.add(index_b)
                    analysis.errors.append(
                        u"단차선 {0}번과 {1}번이 끝점 이외의 위치에서 교차합니다.".format(
                            index_a + 1, index_b + 1
                        )
                    )


def _largest_brep(breps):
    best = None
    best_area = -1.0
    for brep in breps or []:
        properties = rg.AreaMassProperties.Compute(brep)
        area = properties.Area if properties is not None else 0.0
        if area > best_area:
            best = brep
            best_area = area
    return best


def _create_outer_planar_brep(outer, tolerance):
    base_tolerance = max(tolerance, 1e-9)
    for attempt_tolerance in (
        base_tolerance,
        base_tolerance * 2.1,
        base_tolerance * 5.0,
    ):
        try:
            breps = rg.Brep.CreatePlanarBreps([outer], attempt_tolerance)
        except Exception:
            breps = None
        if breps:
            return _largest_brep(breps), attempt_tolerance
    return None, None


def _split_outer_face(base_brep, dividers, tolerance):
    base_tolerance = max(tolerance, 1e-9)
    best_result = None
    best_face_count = 0
    best_tolerance = None

    for attempt_tolerance in (
        base_tolerance,
        base_tolerance * 2.1,
        base_tolerance * 5.0,
    ):
        try:
            split_brep = base_brep.Faces[0].Split(
                dividers, attempt_tolerance
            )
        except Exception:
            split_brep = None
        if split_brep is None:
            continue

        face_count = split_brep.Faces.Count
        if face_count > best_face_count:
            best_result = split_brep
            best_face_count = face_count
            best_tolerance = attempt_tolerance

    return best_result, best_tolerance


def _closed_curve_from_loop(loop, tolerance):
    try:
        curve = loop.To3dCurve()
    except Exception:
        curve = None
    if curve is None:
        return None
    if not curve.IsClosed:
        try:
            curve.MakeClosed(tolerance)
        except Exception:
            pass
    return curve if curve.IsClosed else None


def _region_curves_from_face(face, tolerance):
    outer_loop = face.OuterLoop
    if outer_loop is None:
        return []

    outer_curve = _closed_curve_from_loop(outer_loop, tolerance)
    if outer_curve is None:
        return []

    curves = [outer_curve]
    for loop in face.Loops:
        if loop.LoopIndex == outer_loop.LoopIndex:
            continue
        curve = _closed_curve_from_loop(loop, tolerance)
        if curve is None:
            return []
        curves.append(curve)
    return curves


def _build_split_regions(outer, dividers, tolerance, analysis):
    base_brep, outer_tolerance = _create_outer_planar_brep(
        outer, tolerance
    )
    if base_brep is None or base_brep.Faces.Count == 0:
        analysis.errors.append(
            u"닫힌 외곽선으로 평면 면을 생성하지 못했습니다."
        )
        return []

    split_brep, split_tolerance = _split_outer_face(
        base_brep, dividers, tolerance
    )
    if split_brep is None or split_brep.Faces.Count <= 1:
        analysis.errors.append(
            u"외곽 평면 면을 단차선으로 분할하지 못했습니다. "
            u"단차선이 외곽 경계까지 닿는지 확인해 주세요."
        )
        return []

    if outer_tolerance is not None and outer_tolerance > tolerance:
        analysis.warnings.append(
            u"외곽 평면 면 생성에 확대 공차를 사용했습니다."
        )
    if split_tolerance is not None and split_tolerance > tolerance:
        analysis.warnings.append(
            u"평면 면 분할에 확대 공차를 사용했습니다."
        )

    regions = []
    boundary_failures = 0
    property_failures = 0
    small_regions = 0
    minimum_area = max(tolerance * tolerance * 100.0, 1e-10)
    loop_tolerance = max(tolerance * 5.0, 1e-9)

    for face in split_brep.Faces:
        try:
            face_brep = face.DuplicateFace(False)
        except Exception:
            face_brep = None
        if face_brep is None:
            property_failures += 1
            continue

        region_curves = _region_curves_from_face(
            face, loop_tolerance
        )
        if not region_curves:
            boundary_failures += 1
            continue

        properties = rg.AreaMassProperties.Compute(face_brep)
        if properties is None:
            property_failures += 1
            continue
        area = properties.Area
        if area <= minimum_area:
            small_regions += 1
            continue

        regions.append(
            StairRegion(
                len(regions),
                region_curves,
                face_brep,
                properties.Centroid,
                area,
            )
        )

    if not regions:
        analysis.errors.append(
            u"분할된 면에서 유효한 디딤판 영역을 만들지 못했습니다. "
            u"분할 Face: {0}, 경계 추출 실패: {1}, 면적 계산 실패: {2}, "
            u"최소 면적 미만: {3}.".format(
                split_brep.Faces.Count,
                boundary_failures,
                property_failures,
                small_regions,
            )
        )
    elif boundary_failures or property_failures or small_regions:
        analysis.warnings.append(
            u"일부 분할 면을 제외했습니다. 경계 실패: {0}, 면적 실패: {1}, "
            u"최소 면적 미만: {2}.".format(
                boundary_failures,
                property_failures,
                small_regions,
            )
        )
    return regions


def _collect_divider_parameters(divider_index, dividers, outer, tolerance):
    divider = dividers[divider_index]
    parameters = [divider.Domain.T0, divider.Domain.T1]
    cutters = [outer]
    for index, other in enumerate(dividers):
        if index != divider_index:
            cutters.append(other)

    for cutter in cutters:
        try:
            intersections = rg.Intersect.Intersection.CurveCurve(
                divider, cutter, tolerance, tolerance
            )
        except Exception:
            intersections = None
        if not intersections:
            continue
        for event in intersections:
            try:
                if event.IsPoint:
                    parameter = _get_intersection_parameter_a(event)
                    if parameter is not None:
                        parameters.append(parameter)
                elif event.IsOverlap:
                    try:
                        parameters.append(event.OverlapA.T0)
                        parameters.append(event.OverlapA.T1)
                    except Exception:
                        pass
            except Exception:
                parameter = _get_intersection_parameter_a(event)
                if parameter is not None:
                    parameters.append(parameter)

    return _unique_sorted_parameters(parameters, divider.Domain)


def _build_adjacency(outer, dividers, regions, tolerance, analysis):
    bbox = outer.GetBoundingBox(True)
    diagonal = bbox.Diagonal.Length if bbox.IsValid else 1.0
    epsilon = max(tolerance * 20.0, diagonal * 1e-6)
    analysis.offset_epsilon = epsilon

    edge_set = set()
    divider_edges = {}

    for divider_index, divider in enumerate(dividers):
        parameters = _collect_divider_parameters(
            divider_index, dividers, outer, tolerance
        )
        local_pairs = set()

        if len(parameters) < 2:
            analysis.bad_divider_indices.add(divider_index)
            analysis.errors.append(
                u"단차선 {0}번에서 사용할 수 있는 구간을 찾지 못했습니다.".format(divider_index + 1)
            )
            continue

        for parameter_index in range(len(parameters) - 1):
            parameter_a = parameters[parameter_index]
            parameter_b = parameters[parameter_index + 1]
            if abs(parameter_b - parameter_a) <= 1e-12:
                continue
            middle_parameter = (parameter_a + parameter_b) * 0.5
            point = divider.PointAt(middle_parameter)
            if not _is_inside_closed_curve(outer, point, tolerance, False):
                continue

            tangent = divider.TangentAt(middle_parameter)
            tangent.Z = 0.0
            if not tangent.Unitize():
                continue
            normal = rg.Vector3d(-tangent.Y, tangent.X, 0.0)
            if not normal.Unitize():
                continue

            left_point = point + normal * epsilon
            right_point = point - normal * epsilon
            left_region = _find_region_index(regions, left_point, tolerance)
            right_region = _find_region_index(regions, right_point, tolerance)

            if left_region is None or right_region is None:
                # Retry with a smaller offset for narrow treads.
                smaller = max(tolerance * 3.0, epsilon * 0.2)
                left_point = point + normal * smaller
                right_point = point - normal * smaller
                left_region = _find_region_index(regions, left_point, tolerance)
                right_region = _find_region_index(regions, right_point, tolerance)

            if left_region is None or right_region is None:
                continue
            if left_region == right_region:
                continue

            pair = tuple(sorted((left_region, right_region)))
            local_pairs.add(pair)

        if not local_pairs:
            analysis.bad_divider_indices.add(divider_index)
            analysis.errors.append(
                u"단차선 {0}번이 계단 외곽 영역을 둘로 나누지 못합니다.".format(
                    divider_index + 1
                )
            )
            continue

        if len(local_pairs) > 1:
            analysis.bad_divider_indices.add(divider_index)
            analysis.errors.append(
                u"단차선 {0}번이 여러 영역 전이를 동시에 만듭니다. 커브를 나누거나 수정해 주세요.".format(
                    divider_index + 1
                )
            )
            continue

        pair = list(local_pairs)[0]
        divider_edges[divider_index] = pair
        edge_set.add(pair)

    for region in regions:
        region.neighbors = set()

    for region_a, region_b in edge_set:
        regions[region_a].neighbors.add(region_b)
        regions[region_b].neighbors.add(region_a)

    return sorted(edge_set), divider_edges


def _validate_graph(regions, edges, analysis):
    region_count = len(regions)
    if region_count < 2:
        analysis.errors.append(u"최소 2개의 디딤판 영역이 필요합니다.")
        return []

    degrees = [len(region.neighbors) for region in regions]
    if max(degrees) > 2:
        analysis.errors.append(
            u"분할 영역이 세 방향 이상으로 분기됩니다. 분기형 계단은 현재 지원하지 않습니다."
        )

    endpoints = [index for index, degree in enumerate(degrees) if degree == 1]
    isolated = [index for index, degree in enumerate(degrees) if degree == 0]
    if isolated:
        analysis.errors.append(
            u"계단 경로와 연결되지 않은 디딤판 영역이 있습니다: {0}.".format(
                ", ".join([str(index + 1) for index in isolated])
            )
        )

    if len(edges) != region_count - 1:
        analysis.errors.append(
            u"영역 연결 구조가 하나의 열린 경로가 아닙니다. 영역: {0}, 연결: {1}.".format(
                region_count, len(edges)
            )
        )

    if len(endpoints) != 2:
        analysis.errors.append(
            u"계단 경로에는 정확히 두 개의 끝이 필요합니다. 현재 {0}개가 확인되었습니다.".format(
                len(endpoints)
            )
        )

    # Connectivity check.
    visited = set()
    stack = [0]
    while stack:
        current = stack.pop()
        if current in visited:
            continue
        visited.add(current)
        stack.extend(list(regions[current].neighbors - visited))
    if len(visited) != region_count:
        analysis.errors.append(u"모든 디딤판 영역이 하나로 연결되어 있지 않습니다.")

    if analysis.errors:
        return []

    # Deterministic arbitrary start; the dialog provides Flip.
    endpoints.sort(key=lambda index: (
        regions[index].centroid.X,
        regions[index].centroid.Y,
        regions[index].centroid.Z,
    ))
    start = endpoints[0]

    ordered = []
    previous = None
    current = start
    while current is not None:
        ordered.append(current)
        next_candidates = [
            neighbor for neighbor in regions[current].neighbors
            if neighbor != previous
        ]
        if not next_candidates:
            break
        if len(next_candidates) > 1:
            analysis.errors.append(u"디딤판 순서를 계산하는 중 불명확한 분기가 발견되었습니다.")
            return []
        previous, current = current, next_candidates[0]

    if len(ordered) != region_count:
        analysis.errors.append(u"전체 디딤판 순서를 계산하지 못했습니다.")
        return []

    return ordered


def analyze_stair(object_ids):
    analysis = StairAnalysis()
    analysis.source_ids = list(object_ids)
    tolerance = sc.doc.ModelAbsoluteTolerance

    records, missing = read_source_curves(object_ids)
    if missing:
        analysis.errors.append(
            u"선택한 커브 중 일부가 삭제되었습니다. 계단 평면을 다시 선택해 주세요."
        )
        return analysis

    closed_records = [(object_id, curve) for object_id, curve in records if curve.IsClosed]
    open_records = [(object_id, curve) for object_id, curve in records if not curve.IsClosed]

    if len(closed_records) != 1:
        analysis.errors.append(
            u"닫힌 외곽선은 정확히 1개여야 합니다. 현재 닫힌 커브: {0}개.".format(
                len(closed_records)
            )
        )
        return analysis
    if not open_records:
        analysis.errors.append(u"열린 단차선을 1개 이상 선택해야 합니다.")
        return analysis

    outer_source_id, outer_source = closed_records[0]
    analysis.outer_source_id = outer_source_id
    analysis.divider_source_ids = [record[0] for record in open_records]

    ok, plane = _try_get_plane(outer_source, tolerance)
    if not ok:
        analysis.errors.append(u"닫힌 외곽선이 평면 커브가 아닙니다.")
        return analysis

    for object_id, curve in records:
        try:
            in_plane = curve.IsInPlane(plane, tolerance * 5.0)
        except Exception:
            in_plane = False
        if not in_plane:
            analysis.errors.append(
                u"모든 선택 커브는 외곽선과 같은 평면에 있어야 합니다."
            )
            return analysis

    analysis.original_plane = plane
    analysis.to_xy = rg.Transform.PlaneToPlane(plane, rg.Plane.WorldXY)
    analysis.from_xy = rg.Transform.PlaneToPlane(rg.Plane.WorldXY, plane)

    outer_projected = rg.Curve.ProjectToPlane(outer_source, plane)
    if outer_projected is None:
        analysis.errors.append(u"외곽선을 기준 평면에 투영하지 못했습니다.")
        return analysis
    outer_projected.Transform(analysis.to_xy)

    divider_projected = []
    for object_id, source_curve in open_records:
        projected = rg.Curve.ProjectToPlane(source_curve, plane)
        if projected is None:
            analysis.errors.append(u"단차선 하나를 계단 기준 평면에 투영하지 못했습니다.")
            return analysis
        projected.Transform(analysis.to_xy)
        divider_projected.append(projected)

    if not outer_projected.IsClosed:
        analysis.errors.append(u"평면 정규화 후 외곽선이 열린 커브가 되었습니다.")
        return analysis

    try:
        orientation = outer_projected.ClosedCurveOrientation()
        if orientation == rg.CurveOrientation.Undefined:
            analysis.errors.append(
                u"외곽선이 자기 교차하거나 유효하지 않은 닫힌 커브입니다."
            )
            return analysis
    except Exception:
        pass

    divider_projected = _snap_divider_endpoints(
        divider_projected, outer_projected, tolerance
    )
    divider_projected = _clip_dividers_to_outer(
        divider_projected, outer_projected, tolerance, analysis
    )
    # Trimming creates new endpoints at the outer boundary. Snap the analysis
    # copies once more to remove tiny gaps before splitting the planar face.
    divider_projected = _snap_divider_endpoints(
        divider_projected, outer_projected, tolerance
    )

    analysis.outer = outer_projected
    analysis.dividers = divider_projected

    if analysis.errors:
        return analysis

    _validate_divider_intersections(divider_projected, tolerance, analysis)
    if analysis.errors:
        return analysis

    analysis.regions = _build_split_regions(
        outer_projected, divider_projected, tolerance, analysis
    )
    if analysis.errors:
        return analysis

    analysis.edges, analysis.divider_edges = _build_adjacency(
        outer_projected, divider_projected, analysis.regions, tolerance, analysis
    )
    if analysis.errors:
        return analysis

    analysis.ordered_region_ids = _validate_graph(
        analysis.regions, analysis.edges, analysis
    )
    if analysis.errors:
        return analysis

    analysis.is_valid = True
    return analysis


# -----------------------------------------------------------------------------
# Geometry generation
# -----------------------------------------------------------------------------

def calculate_riser_data(region_count, settings):
    if settings.calc_mode == CALC_BY_TREADS:
        riser_count = region_count
    else:
        riser_count = region_count + 1
    riser_height = settings.floor_height / float(riser_count)
    return riser_count, riser_height


def ordered_region_ids(analysis, settings):
    ids = list(analysis.ordered_region_ids)
    if settings.flipped:
        ids.reverse()
    return ids


def _translated_curves(curves, z_value):
    transform = rg.Transform.Translation(0.0, 0.0, z_value)
    result = []
    for curve in curves:
        copy_curve = curve.DuplicateCurve()
        copy_curve.Transform(transform)
        result.append(copy_curve)
    return result


def _create_planar_region(curves, z_value, tolerance):
    moved_curves = _translated_curves(curves, z_value)
    try:
        breps = rg.Brep.CreatePlanarBreps(moved_curves, tolerance)
    except Exception:
        breps = None
    if not breps:
        return None
    if len(breps) == 1:
        return breps[0]
    # Select the largest result if an unexpected multiple result occurs.
    best = None
    best_area = -1.0
    for brep in breps:
        properties = rg.AreaMassProperties.Compute(brep)
        area = properties.Area if properties else 0.0
        if area > best_area:
            best_area = area
            best = brep
    return best


def _manual_extrude_region(curves, top_z, bottom_z, tolerance):
    if abs(top_z - bottom_z) <= tolerance:
        return _create_planar_region(curves, top_z, tolerance)

    top_curves = _translated_curves(curves, top_z)
    bottom_curves = _translated_curves(curves, bottom_z)

    top_breps = rg.Brep.CreatePlanarBreps(top_curves, tolerance)
    bottom_breps = rg.Brep.CreatePlanarBreps(bottom_curves, tolerance)
    if not top_breps or not bottom_breps:
        return None

    pieces = [top_breps[0], bottom_breps[0]]
    vector = rg.Vector3d(0.0, 0.0, top_z - bottom_z)
    for bottom_curve in bottom_curves:
        try:
            surface = rg.Surface.CreateExtrusion(bottom_curve, vector)
            if surface is not None:
                pieces.append(surface.ToBrep())
        except Exception:
            pass

    try:
        joined = rg.Brep.JoinBreps(pieces, tolerance)
    except Exception:
        joined = None

    if joined:
        for candidate in joined:
            if candidate.IsSolid:
                return candidate
        if len(joined) == 1:
            return joined[0]

    # Fallback: extrude the trimmed face directly.
    top_region = top_breps[0]
    try:
        centroid_properties = rg.AreaMassProperties.Compute(top_region)
        centroid = centroid_properties.Centroid
        path = rg.LineCurve(
            centroid,
            centroid + rg.Vector3d(0.0, 0.0, bottom_z - top_z)
        )
        direct = top_region.Faces[0].CreateExtrusion(path, True)
        if direct is not None:
            return direct
    except Exception:
        pass

    return None


def build_stair_geometry(analysis, settings):
    tolerance = sc.doc.ModelAbsoluteTolerance
    sequence = ordered_region_ids(analysis, settings)
    riser_count, riser_height = calculate_riser_data(len(sequence), settings)

    local_geometry = []
    failures = []
    z_sign = -1.0 if settings.z_flipped else 1.0

    for order_index, region_id in enumerate(sequence):
        region = analysis.regions[region_id]
        tread_z = z_sign * (order_index + 1) * riser_height

        if settings.geometry_mode == MODE_SURFACE:
            geometry = _create_planar_region(region.curves, tread_z, tolerance)
        elif settings.geometry_mode == MODE_FIXED_THICKNESS:
            thickness_z = tread_z - z_sign * settings.tread_thickness
            geometry = _manual_extrude_region(
                region.curves, tread_z, thickness_z, tolerance
            )
        else:
            geometry = _manual_extrude_region(
                region.curves, tread_z, 0.0, tolerance
            )

        if geometry is None:
            failures.append(order_index + 1)
            continue
        local_geometry.append(geometry)

    union_warning = None
    if settings.geometry_mode == MODE_FILLED_MASS and local_geometry:
        try:
            unioned = rg.Brep.CreateBooleanUnion(local_geometry, tolerance)
        except Exception:
            try:
                unioned = rg.Brep.CreateBooleanUnion(local_geometry, tolerance, True)
            except Exception:
                unioned = None
        if unioned:
            local_geometry = list(unioned)
        else:
            union_warning = (
                u"Boolean Union에 실패하여 개별 채움 솔리드로 유지합니다."
            )

    world_geometry = []
    for brep in local_geometry:
        world_geometry.append(_brep_world_copy(brep, analysis.from_xy))

    return {
        "geometry": world_geometry,
        "failures": failures,
        "union_warning": union_warning,
        "riser_count": riser_count,
        "riser_height": riser_height,
        "sequence": sequence,
    }


# -----------------------------------------------------------------------------
# Display conduits
# -----------------------------------------------------------------------------

class StairPreviewConduit(rdisplay.DisplayConduit):
    def __init__(self, analysis):
        rdisplay.DisplayConduit.__init__(self)
        self.analysis = analysis
        self.settings = StairSettings()
        self.preview_data = None
        self.normal_color = Color.FromArgb(70, 150, 240)
        self.wire_color = Color.FromArgb(30, 80, 150)
        self.text_color = Color.FromArgb(20, 20, 20)
        self.arrow_color = Color.FromArgb(230, 120, 20)
        self.error_color = Color.Red

    def update(self, settings, preview_data):
        self.settings = settings.copy()
        self.preview_data = preview_data
        sc.doc.Views.Redraw()

    def CalculateBoundingBox(self, e):
        if self.preview_data:
            for brep in self.preview_data.get("geometry", []):
                e.IncludeBoundingBox(brep.GetBoundingBox(True))
        if self.analysis.outer is not None:
            curve = _curve_world_copy(self.analysis.outer, self.analysis.from_xy)
            e.IncludeBoundingBox(curve.GetBoundingBox(True))

    def PostDrawObjects(self, e):
        if not self.preview_data:
            return

        try:
            material = rdisplay.DisplayMaterial(self.normal_color)
            material.Transparency = 0.58
        except Exception:
            material = None
        for brep in self.preview_data.get("geometry", []):
            try:
                if material is not None:
                    e.Display.DrawBrepShaded(brep, material)
                e.Display.DrawBrepWires(brep, self.wire_color, 1)
            except Exception:
                pass

        sequence = self.preview_data.get("sequence", [])
        _, riser_height = calculate_riser_data(len(sequence), self.settings)
        z_sign = -1.0 if self.settings.z_flipped else 1.0
        local_points = []
        for order_index, region_id in enumerate(sequence):
            region = self.analysis.regions[region_id]
            tread_z = z_sign * (order_index + 1) * riser_height
            label_offset = z_sign * max(riser_height * 0.08, 1.0)
            local_point = rg.Point3d(
                region.centroid.X,
                region.centroid.Y,
                tread_z + label_offset,
            )
            world_point = rg.Point3d(local_point)
            world_point.Transform(self.analysis.from_xy)
            local_points.append(world_point)

            text_plane = rg.Plane(
                world_point,
                self.analysis.original_plane.XAxis,
                self.analysis.original_plane.YAxis,
            )
            text_height = max(riser_height * 0.22, sc.doc.ModelAbsoluteTolerance * 100.0)
            try:
                e.Display.Draw3dText(
                    str(order_index + 1),
                    self.text_color,
                    text_plane,
                    text_height,
                    "Arial",
                )
            except Exception:
                pass

        for index in range(len(local_points) - 1):
            self._draw_arrow(e.Display, local_points[index], local_points[index + 1])

    def _draw_arrow(self, display, start, end):
        vector = end - start
        length = vector.Length
        if length <= sc.doc.ModelAbsoluteTolerance:
            return
        direction = rg.Vector3d(vector)
        direction.Unitize()
        arrow_end = start + direction * (length * 0.82)
        display.DrawLine(rg.Line(start, arrow_end), self.arrow_color, 2)

        side = rg.Vector3d.CrossProduct(self.analysis.original_plane.ZAxis, direction)
        if not side.Unitize():
            return
        head_length = min(length * 0.18, max(length * 0.08, sc.doc.ModelAbsoluteTolerance * 30.0))
        back = arrow_end - direction * head_length
        left = back + side * (head_length * 0.45)
        right = back - side * (head_length * 0.45)
        display.DrawLine(rg.Line(arrow_end, left), self.arrow_color, 2)
        display.DrawLine(rg.Line(arrow_end, right), self.arrow_color, 2)


class ErrorPreviewConduit(rdisplay.DisplayConduit):
    def __init__(self, analysis):
        rdisplay.DisplayConduit.__init__(self)
        self.analysis = analysis
        self.red = Color.Red
        self.gray = Color.FromArgb(100, 100, 100)

    def CalculateBoundingBox(self, e):
        curves = self._curves_to_draw()
        for curve in curves:
            e.IncludeBoundingBox(curve.GetBoundingBox(True))

    def PostDrawObjects(self, e):
        if self.analysis.outer is not None:
            outer_world = _curve_world_copy(
                self.analysis.outer, self.analysis.from_xy
            )
            e.Display.DrawCurve(outer_world, self.gray, 2)

        for index, divider in enumerate(self.analysis.dividers):
            world_curve = _curve_world_copy(divider, self.analysis.from_xy)
            color = self.red if self._is_bad(index) else self.gray
            thickness = 4 if self._is_bad(index) else 1
            e.Display.DrawCurve(world_curve, color, thickness)

    def _is_bad(self, index):
        if self.analysis.bad_divider_indices:
            return index in self.analysis.bad_divider_indices
        return bool(self.analysis.errors)

    def _curves_to_draw(self):
        curves = []
        if self.analysis.outer is not None:
            curves.append(_curve_world_copy(
                self.analysis.outer, self.analysis.from_xy
            ))
        for divider in self.analysis.dividers:
            curves.append(_curve_world_copy(divider, self.analysis.from_xy))
        return curves


# -----------------------------------------------------------------------------
# Eto dialogs
# -----------------------------------------------------------------------------

class AnalysisErrorDialog(forms.Dialog[bool]):
    def __init__(self, analysis):
        forms.Dialog[bool].__init__(self)
        try:
            EtoExtensions.UseRhinoStyle(self)
        except Exception:
            pass
        self.Title = u"Custom Stair - 평면 분석 오류"
        self.Padding = drawing.Padding(12)
        self.Resizable = True
        self.ClientSize = drawing.Size(520, 320)

        title = forms.Label()
        title.Text = u"계단 평면을 정상적으로 해석하지 못했습니다."

        instruction = forms.Label()
        instruction.Text = (
            u"문제가 있는 단차선은 빨간색으로 표시됩니다. Rhino에서 원본 커브를 "
            u"수정한 다음 ‘다시 분석’을 누르세요."
        )

        error_text = forms.TextArea()
        error_text.ReadOnly = True
        lines = []
        for index, error in enumerate(analysis.errors):
            lines.append(u"{0}. {1}".format(index + 1, error))
        error_text.Text = u"\n".join(lines)

        self.DefaultButton = forms.Button(Text=u"다시 분석")
        self.DefaultButton.Click += self._on_retry
        self.AbortButton = forms.Button(Text=u"취소")
        self.AbortButton.Click += self._on_cancel

        layout = forms.DynamicLayout()
        layout.Spacing = drawing.Size(8, 8)
        layout.AddRow(title)
        layout.AddRow(instruction)
        layout.AddRow(error_text)
        layout.AddRow(None, self.DefaultButton, self.AbortButton)
        self.Content = layout

    def _on_retry(self, sender, event):
        self.Close(True)

    def _on_cancel(self, sender, event):
        self.Close(False)


class StairSettingsDialog(forms.Dialog[bool]):
    def __init__(self, analysis, settings, conduit):
        forms.Dialog[bool].__init__(self)
        try:
            EtoExtensions.UseRhinoStyle(self)
        except Exception:
            pass
        self.analysis = analysis
        self.settings = settings.copy()
        self.conduit = conduit
        self.preview_data = None
        self.result_settings = None

        self.Title = u"Custom Stair"
        self.Padding = drawing.Padding(12)
        self.Resizable = True
        self.ClientSize = drawing.Size(600, 420)

        self.region_label = forms.Label()
        self.region_label.Text = u"인식된 디딤판 영역: {0}개".format(
            len(analysis.regions)
        )

        self.height_box = forms.TextBox(Text=str(self.settings.floor_height))
        self.height_box.Width = 130
        self.height_box.KeyDown += self._on_textbox_key_down

        self.pick_height_button = forms.Button(Text=u"두 점으로 입력")
        self.pick_height_button.Click += self._on_pick_height

        self.calc_list = forms.RadioButtonList()
        self.calc_list.DataStore = [
            u"층고 ÷ 디딤판 수 (마지막 디딤판 = 상부 바닥)",
            u"층고 ÷ (디딤판 수 + 1)",
        ]
        self.calc_list.Orientation = forms.Orientation.Vertical
        self.calc_list.Spacing = drawing.Size(4, 4)
        self.calc_list.SelectedIndex = self.settings.calc_mode
        self.calc_list.SelectedIndexChanged += self._on_calc_changed

        self.mode_list = forms.RadioButtonList()
        self.mode_list.DataStore = [
            u"디딤판 면만 생성",
            u"고정 두께 디딤판 솔리드",
            u"기준면까지 채운 계단 매스",
        ]
        self.mode_list.Orientation = forms.Orientation.Vertical
        self.mode_list.Spacing = drawing.Size(4, 4)
        self.mode_list.SelectedIndex = self.settings.geometry_mode
        self.mode_list.SelectedIndexChanged += self._on_mode_changed

        self.thickness_box = forms.TextBox(Text=str(self.settings.tread_thickness))
        self.thickness_box.Width = 130
        self.thickness_box.KeyDown += self._on_textbox_key_down

        self.flip_button = forms.Button(Text=u"방향 Flip")
        self.flip_button.Click += self._on_flip

        self.z_flip_button = forms.Button(Text=u"Z 방향 Flip")
        self.z_flip_button.Click += self._on_z_flip

        self.preview_button = forms.Button(Text=u"미리보기 갱신")
        self.preview_button.Click += self._on_preview

        self.status_label = forms.Label()
        self.status_label.Height = 92

        # Do not assign this button to Dialog.DefaultButton. Otherwise Enter in
        # a numeric TextBox closes the dialog and creates the stair.
        self.create_button = forms.Button(Text=u"생성")
        self.create_button.Click += self._on_create
        self.AbortButton = forms.Button(Text=u"취소")
        self.AbortButton.Click += self._on_cancel

        height_layout = forms.DynamicLayout()
        height_layout.Spacing = drawing.Size(5, 0)
        height_layout.BeginHorizontal()
        height_layout.Add(self.height_box)
        height_layout.Add(self.pick_height_button)
        height_layout.EndHorizontal()

        layout = forms.DynamicLayout()
        layout.Spacing = drawing.Size(7, 7)
        layout.AddRow(self.region_label)
        layout.AddRow(forms.Label(Text=u"전체 층고"), height_layout)
        layout.AddRow(forms.Label(Text=u"단 높이 계산 방식"))
        layout.AddRow(self.calc_list)
        layout.AddRow(forms.Label(Text=u"생성 형식"))
        layout.AddRow(self.mode_list)
        layout.AddSeparateRow(forms.Label(Text=u"디딤판 두께"), self.thickness_box, None)
        layout.AddSeparateRow(
            self.flip_button, self.z_flip_button, self.preview_button, None
        )
        layout.AddRow(self.status_label)
        layout.AddRow(None, self.create_button, self.AbortButton)
        self.Content = layout

        self._update_thickness_enabled()
        self._update_preview(show_error=False)

    def _selected_mode(self):
        index = self.mode_list.SelectedIndex
        if index not in (MODE_SURFACE, MODE_FIXED_THICKNESS, MODE_FILLED_MASS):
            return MODE_FIXED_THICKNESS
        return index

    def _parse_settings(self):
        try:
            floor_height = float(self.height_box.Text)
        except Exception:
            raise ValueError(u"전체 층고는 숫자로 입력해야 합니다.")
        if floor_height <= 0.0:
            raise ValueError(u"전체 층고는 0보다 커야 합니다.")

        mode = self._selected_mode()
        try:
            thickness = float(self.thickness_box.Text)
        except Exception:
            raise ValueError(u"디딤판 두께는 숫자로 입력해야 합니다.")
        if mode == MODE_FIXED_THICKNESS and thickness <= 0.0:
            raise ValueError(u"디딤판 두께는 0보다 커야 합니다.")

        calc_mode = self.calc_list.SelectedIndex
        if calc_mode not in (CALC_BY_TREADS, CALC_BY_TREADS_PLUS_ONE):
            calc_mode = CALC_BY_TREADS_PLUS_ONE

        settings = self.settings.copy()
        settings.floor_height = floor_height
        settings.calc_mode = calc_mode
        settings.geometry_mode = mode
        settings.tread_thickness = thickness
        return settings

    def _update_thickness_enabled(self):
        self.thickness_box.Enabled = self._selected_mode() == MODE_FIXED_THICKNESS

    def _on_mode_changed(self, sender, event):
        self._update_thickness_enabled()
        self._update_preview(show_error=True)

    def _on_calc_changed(self, sender, event):
        self._update_preview(show_error=True)

    def _on_textbox_key_down(self, sender, event):
        if event.Key == forms.Keys.Enter:
            self._update_preview(show_error=True)
            event.Handled = True

    def _get_view_point(self, prompt, base_point=None):
        getter = ric.GetPoint()
        getter.SetCommandPrompt(prompt)
        if base_point is not None:
            getter.SetBasePoint(base_point, True)
            getter.DrawLineFromPoint(base_point, True)
        result = getter.Get()
        if result != Rhino.Input.GetResult.Point:
            return None
        return getter.Point()

    def _pick_height_points(self, sender, event):
        try:
            first = self._get_view_point(u"층고 기준 첫 번째 점을 지정하세요")
            if first is None:
                return
            second = self._get_view_point(
                u"층고 기준 두 번째 점을 지정하세요", first
            )
            if second is None:
                return

            distance = first.DistanceTo(second)
            if distance <= sc.doc.ModelAbsoluteTolerance:
                _show_message(
                    u"두 점 사이 거리는 0보다 커야 합니다.",
                    u"Custom Stair - 층고 입력",
                )
                return

            self.height_box.Text = u"{0:.3f}".format(distance)
            self._update_preview(show_error=True)
        except Exception as error:
            _show_message(
                u"두 점 층고 입력 중 오류가 발생했습니다.\n{0}".format(error),
                u"Custom Stair - 층고 입력",
            )

    def _on_pick_height(self, sender, event):
        EtoExtensions.PushPickButton(self, self._pick_height_points)

    def _on_flip(self, sender, event):
        self.settings.flipped = not self.settings.flipped
        self._update_preview(show_error=True)

    def _on_z_flip(self, sender, event):
        self.settings.z_flipped = not self.settings.z_flipped
        self._update_preview(show_error=True)

    def _on_preview(self, sender, event):
        self._update_preview(show_error=True)

    def _update_preview(self, show_error):
        try:
            settings = self._parse_settings()
            settings.flipped = self.settings.flipped
            settings.z_flipped = self.settings.z_flipped
            preview_data = build_stair_geometry(self.analysis, settings)
            if preview_data["failures"]:
                raise ValueError(
                    u"형상 생성에 실패한 디딤판: {0}".format(
                        ", ".join([str(value) for value in preview_data["failures"]])
                    )
                )

            self.settings = settings
            self.preview_data = preview_data
            self.conduit.update(settings, preview_data)

            final_tread_height = len(preview_data["sequence"]) * preview_data["riser_height"]
            direction_text = u"반전" if settings.flipped else u"기본"
            z_direction_text = u"반전 (-Z)" if settings.z_flipped else u"기본 (+Z)"
            status = (
                u"챌판 수: {0}    단 높이: {1:.3f}\n"
                u"최고 디딤판 높이: {2:.3f}    방향: {3}\n"
                u"Z 방향: {4}"
            ).format(
                preview_data["riser_count"],
                preview_data["riser_height"],
                final_tread_height,
                direction_text,
                z_direction_text,
            )
            if preview_data["union_warning"]:
                status += u"\nBoolean Union 실패: 개별 솔리드로 유지됩니다."
            if preview_data["riser_height"] > 220.0 or preview_data["riser_height"] < 100.0:
                status += u"\n계산된 단 높이를 확인해 주세요."
            self.status_label.Text = status
            return True
        except Exception as error:
            self.status_label.Text = u"{0}".format(error)
            if show_error:
                _show_message(u"{0}".format(error), u"Custom Stair 미리보기")
            return False

    def _on_create(self, sender, event):
        if not self._update_preview(show_error=True):
            return
        self.result_settings = self.settings.copy()
        self.Close(True)

    def _on_cancel(self, sender, event):
        self.Close(False)


# -----------------------------------------------------------------------------
# Dialog runners and document output
# -----------------------------------------------------------------------------

def show_semi_modal(dialog):
    try:
        parent = RhinoEtoApp.MainWindowForDocument(sc.doc)
    except Exception:
        parent = RhinoEtoApp.MainWindow
    return EtoExtensions.ShowSemiModal(dialog, sc.doc, parent)


def request_error_retry(analysis):
    conduit = ErrorPreviewConduit(analysis)
    conduit.Enabled = True
    sc.doc.Views.Redraw()
    try:
        dialog = AnalysisErrorDialog(analysis)
        return bool(show_semi_modal(dialog))
    finally:
        conduit.Enabled = False
        sc.doc.Views.Redraw()


def request_settings(analysis):
    settings = _load_last_settings()
    conduit = StairPreviewConduit(analysis)
    conduit.Enabled = True
    sc.doc.Views.Redraw()
    try:
        dialog = StairSettingsDialog(analysis, settings, conduit)
        accepted = bool(show_semi_modal(dialog))
        if not accepted:
            return None, None
        return dialog.result_settings, dialog.preview_data
    finally:
        conduit.Enabled = False
        sc.doc.Views.Redraw()


def add_stair_to_document(preview_data):
    geometry = preview_data.get("geometry", [])
    if not geometry:
        return []

    layer_index = _ensure_output_layer(sc.doc)
    attributes = rdo.ObjectAttributes()
    attributes.LayerIndex = layer_index
    attributes.Name = "CustomStair"

    undo_record = sc.doc.BeginUndoRecord("Create Custom Stair")
    object_ids = []
    try:
        for brep in geometry:
            object_id = sc.doc.Objects.AddBrep(brep, attributes)
            if object_id != System.Guid.Empty:
                object_ids.append(object_id)

        if len(object_ids) > 1:
            group_index = sc.doc.Groups.Add("CustomStair")
            if group_index >= 0:
                sc.doc.Groups.AddToGroup(group_index, object_ids)
    finally:
        sc.doc.EndUndoRecord(undo_record)

    sc.doc.Views.Redraw()
    return object_ids


# -----------------------------------------------------------------------------
# Main command
# -----------------------------------------------------------------------------

def run_custom_stair():
    object_ids = select_input_curves()
    if not object_ids:
        return Rhino.Commands.Result.Cancel

    while True:
        analysis = analyze_stair(object_ids)
        if analysis.is_valid:
            break

        # Classification/planarity errors may have no drawable local geometry.
        if analysis.outer is None and not analysis.dividers:
            message = "\n".join(analysis.errors)
            _show_message(message, u"Custom Stair - 입력 오류")
            return Rhino.Commands.Result.Failure

        retry = request_error_retry(analysis)
        if not retry:
            return Rhino.Commands.Result.Cancel

    settings, preview_data = request_settings(analysis)
    if settings is None or preview_data is None:
        return Rhino.Commands.Result.Cancel

    object_ids = add_stair_to_document(preview_data)
    if not object_ids:
        _show_message(u"문서에 추가할 계단 형상이 생성되지 않았습니다.")
        return Rhino.Commands.Result.Failure

    _save_last_settings(settings)

    message = u"Custom Stair 생성 완료: {0}개 객체.".format(len(object_ids))
    if preview_data.get("union_warning"):
        message += "\n" + preview_data["union_warning"]
    Rhino.RhinoApp.WriteLine(message)
    return Rhino.Commands.Result.Success


if __name__ == "__main__":
    run_custom_stair()
