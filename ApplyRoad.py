# -*- coding: utf-8 -*-
"""
Road_Z_Interpolator_Rhino8_v4.py

Purpose
-------
Selected road border curves are lifted onto existing 3D contour curves.
This script is intentionally separated from the SHP loader.

Version 4 change:
- Output split road segments instead of joining them back into one curve.
- Preserve original road curve vertices/control points inside each split segment.
- Name same-elevation segments by contour elevation, for example ELEV_20 instead of 20_to_20.
- Put flat/same-elevation segments on a separate layer: GIS_Road_Z_Flat.

Workflow
--------
1. Collect all 3D contour curves from layer "GIS_Contour_3D".
   If the layer is not found or empty, the user is asked to select contour curves.
2. User selects one or more road border curves.
3. For each selected road curve:
   - Project road and contours to XY for intersection tests.
   - Find intersections between the selected road curve and the 3D contours.
   - Use contour Z values as anchor heights.
   - Interpolate Z along the road curve between anchor points.
4. Bake split result curves to:
   - GIS_Road_Z_OK
   - GIS_Road_Z_Check
   - GIS_Road_Z_Failed

Notes
-----
- This script does NOT process all road curves automatically.
- It only processes the road curves selected by the user.
- Mesh generation is not included.
- Designed for Rhino 8 Python / RhinoCommon.
"""

import math
import System
import Rhino
import Rhino.Geometry as rg
import Rhino.DocObjects as rd
import scriptcontext as sc
import rhinoscriptsyntax as rs

# -----------------------------------------------------------------------------
# Settings
# -----------------------------------------------------------------------------
CONTOUR_LAYER_NAME = "GIS_Contour_3D"
OUTPUT_LAYER_OK = "GIS_Road_Z_OK"
OUTPUT_LAYER_FLAT = "GIS_Road_Z_Flat"
OUTPUT_LAYER_CHECK = "GIS_Road_Z_Check"
OUTPUT_LAYER_FAILED = "GIS_Road_Z_Failed"

CONTOUR_INTERVAL = 5.0           # The user's contour data is fixed at 5m intervals.
MAX_Z_JUMP_FOR_OK = 5.01         # If an anchor-to-anchor Z jump is larger than this, mark as CHECK.
DEFAULT_TOLERANCE = 0.01         # XY intersection tolerance. Adjust if GIS scale requires it.
STATION_MERGE_TOL = 0.05         # Distance tolerance along road curve for merging duplicate anchors.
FALLBACK_SAMPLE_SPACING = 3.0    # Last-resort only when no original points can be extracted.
MAX_FALLBACK_SAMPLE_COUNT = 1500
SAMPLE_DUP_TOL = 1e-7            # Very small tolerance: do not merge legitimate close road vertices.

# -----------------------------------------------------------------------------
# Utility
# -----------------------------------------------------------------------------
def ensure_layer(layer_name, color):
    if rs.IsLayer(layer_name):
        return sc.doc.Layers.Find(layer_name, True)
    return rs.AddLayer(layer_name, color)


def add_curve_to_layer(curve, layer_name, color, name=None):
    layer_index = ensure_layer(layer_name, color)
    attr = rd.ObjectAttributes()
    attr.LayerIndex = layer_index
    if name:
        attr.Name = name
    return sc.doc.Objects.AddCurve(curve, attr)


def project_curve_to_xy(curve):
    if curve is None:
        return None
    c = curve.DuplicateCurve()
    if c is None:
        return None
    xf = rg.Transform.PlanarProjection(rg.Plane.WorldXY)
    c.Transform(xf)
    return c


def contour_elevation(curve):
    """Return representative Z value of a 3D contour curve."""
    bbox = curve.GetBoundingBox(True)
    return bbox.Center.Z


def bbox_overlap(a, b):
    if not a.IsValid or not b.IsValid:
        return True
    if a.Max.X < b.Min.X or a.Min.X > b.Max.X:
        return False
    if a.Max.Y < b.Min.Y or a.Min.Y > b.Max.Y:
        return False
    return True


def length_at_parameter(curve, t):
    domain = curve.Domain
    if t <= domain.T0:
        return 0.0
    if t >= domain.T1:
        return curve.GetLength()
    try:
        return curve.GetLength(rg.Interval(domain.T0, t))
    except:
        # Fallback approximation if interval length query fails.
        total = curve.GetLength()
        denom = domain.T1 - domain.T0
        if abs(denom) < 1e-12:
            return 0.0
        return total * ((t - domain.T0) / denom)


def curve_is_closed(curve):
    try:
        return curve.IsClosed
    except:
        return False


def point2d_key(pt, tol):
    return (int(round(pt.X / tol)), int(round(pt.Y / tol)))

# -----------------------------------------------------------------------------
# Contour collection
# -----------------------------------------------------------------------------
def get_contour_objects():
    ids = []
    if rs.IsLayer(CONTOUR_LAYER_NAME):
        layer_ids = rs.ObjectsByLayer(CONTOUR_LAYER_NAME, False)
        if layer_ids:
            ids = [obj_id for obj_id in layer_ids if rs.IsCurve(obj_id)]

    if not ids:
        ids = rs.GetObjects(
            u"GIS_Contour_3D 레이어를 찾지 못했습니다. 3D 등고선 커브들을 선택하세요.",
            rs.filter.curve,
            preselect=True
        )
        if not ids:
            return []

    contours = []
    for obj_id in ids:
        crv = rs.coercecurve(obj_id)
        if not crv:
            continue
        crv2d = project_curve_to_xy(crv)
        if not crv2d:
            continue
        z = contour_elevation(crv)
        bbox2d = crv2d.GetBoundingBox(True)
        contours.append({
            "id": obj_id,
            "curve3d": crv,
            "curve2d": crv2d,
            "z": z,
            "bbox2d": bbox2d
        })
    return contours

# -----------------------------------------------------------------------------
# Intersection anchors
# -----------------------------------------------------------------------------
def add_anchor(anchors, road2d, t, z, tol):
    pt = road2d.PointAt(t)
    station = length_at_parameter(road2d, t)
    anchors.append({
        "t": t,
        "station": station,
        "point": rg.Point3d(pt.X, pt.Y, 0.0),
        "z": z
    })


def collect_road_contour_anchors(road2d, contours, tol):
    anchors = []
    road_bbox = road2d.GetBoundingBox(True)
    road_bbox.Inflate(tol * 10.0)

    tested_count = 0
    for cdata in contours:
        if not bbox_overlap(road_bbox, cdata["bbox2d"]):
            continue
        tested_count += 1
        try:
            events = rg.Intersect.Intersection.CurveCurve(
                road2d,
                cdata["curve2d"],
                tol,
                tol
            )
        except Exception as ex:
            print(u"교차 계산 실패 contour: {}".format(ex))
            continue

        if not events:
            continue

        for ev in events:
            try:
                if ev.IsPoint:
                    add_anchor(anchors, road2d, ev.ParameterA, cdata["z"], tol)
                elif ev.IsOverlap:
                    # If the road overlaps a contour, use overlap endpoints as height anchors.
                    iv = ev.OverlapA
                    add_anchor(anchors, road2d, iv.T0, cdata["z"], tol)
                    add_anchor(anchors, road2d, iv.T1, cdata["z"], tol)
            except Exception as ex:
                print(u"교차 이벤트 처리 실패: {}".format(ex))

    return merge_duplicate_anchors(anchors, road2d.GetLength(), curve_is_closed(road2d), STATION_MERGE_TOL), tested_count


def merge_duplicate_anchors(anchors, total_len, is_closed, station_tol):
    if not anchors:
        return []

    anchors = sorted(anchors, key=lambda a: a["station"])
    groups = []
    current = [anchors[0]]

    for a in anchors[1:]:
        if abs(a["station"] - current[-1]["station"]) <= station_tol:
            current.append(a)
        else:
            groups.append(current)
            current = [a]
    groups.append(current)

    # Merge seam anchors for closed curves: station near 0 and station near total length.
    if is_closed and len(groups) > 1:
        first_station = groups[0][0]["station"]
        last_station = groups[-1][-1]["station"]
        if first_station <= station_tol and (total_len - last_station) <= station_tol:
            merged = groups[-1] + groups[0]
            groups = [merged] + groups[1:-1]

    merged_anchors = []
    for g in groups:
        avg_station = sum([x["station"] for x in g]) / float(len(g))
        # If merged at seam, force station 0.
        if is_closed:
            has_near_start = any([x["station"] <= station_tol for x in g])
            has_near_end = any([(total_len - x["station"]) <= station_tol for x in g])
            if has_near_start and has_near_end:
                avg_station = 0.0

        avg_z = sum([x["z"] for x in g]) / float(len(g))
        # Use first point projected at average station where possible.
        t = parameter_at_length_safe(g[0], avg_station)
        merged_anchors.append({
            "station": avg_station,
            "z": avg_z,
            "raw_count": len(g)
        })

    merged_anchors = sorted(merged_anchors, key=lambda a: a["station"])
    return merged_anchors


def parameter_at_length_safe(anchor, station):
    # Placeholder retained for compatibility; not used downstream.
    return anchor.get("t", 0.0)

# -----------------------------------------------------------------------------
# Sampling and interpolation
# -----------------------------------------------------------------------------
def _append_sample_from_point(samples, curve, pt, source="original"):
    """Append a curve point using its station along the curve."""
    try:
        rc, t = curve.ClosestPoint(pt)
        if not rc:
            return False
        station = length_at_parameter(curve, t)
        p = curve.PointAt(t)
        samples.append({
            "station": station,
            "point": rg.Point3d(p.X, p.Y, 0.0),
            "source": source
        })
        return True
    except:
        return False


def _extract_polyline_points_from_curve(curve):
    """Return original polyline-like points without re-dividing the curve."""
    pts = []

    # 1. Direct polyline extraction. This is the main case for SHP/GIS border curves.
    pl = rg.Polyline()
    try:
        if curve.TryGetPolyline(pl) and pl.Count >= 2:
            return [rg.Point3d(pl[i]) for i in range(pl.Count)]
    except:
        pass

    # 2. PolyCurve: preserve each segment's endpoints / polyline vertices.
    try:
        pc = curve if isinstance(curve, rg.PolyCurve) else None
    except:
        pc = None

    if pc:
        try:
            segs = pc.DuplicateSegments()
            for seg in segs:
                seg_pts = _extract_polyline_points_from_curve(seg)
                if not seg_pts:
                    continue
                if pts and pts[-1].DistanceTo(seg_pts[0]) <= SAMPLE_DUP_TOL:
                    pts.extend(seg_pts[1:])
                else:
                    pts.extend(seg_pts)
            if len(pts) >= 2:
                return pts
        except:
            pass

    # 3. LineCurve fallback: use exact endpoints.
    try:
        line = curve.Line
        if line.IsValid:
            return [line.From, line.To]
    except:
        pass

    # 4. Degree-1 NurbsCurve: control points are on the curve and represent the original polyline.
    try:
        nc = curve.ToNurbsCurve()
        if nc and nc.Degree == 1 and nc.Points.Count >= 2:
            return [nc.Points[i].Location for i in range(nc.Points.Count)]
    except:
        pass

    return []


def original_road_sample_points(road2d):
    """Extract interpolation samples from the selected road curve itself.

    The goal is to keep the user's selected road curve vertices as-is. We do not
    divide by count/length unless the curve has no extractable original points.
    """
    samples = []
    is_closed = curve_is_closed(road2d)
    pts = _extract_polyline_points_from_curve(road2d)

    if pts:
        # For closed polylines, remove the repeated seam point here.
        # build_interpolated_curve() will append the first point again at the end.
        if is_closed and len(pts) > 2 and pts[0].DistanceTo(pts[-1]) <= DEFAULT_TOLERANCE:
            pts = pts[:-1]
        for pt in pts:
            _append_sample_from_point(samples, road2d, pt, "original")
        return samples

    # Last resort only: non-polyline curves. This may add points, but avoids failure.
    total_len = road2d.GetLength()
    length = max(total_len, 0.001)
    count = int(math.ceil(length / FALLBACK_SAMPLE_SPACING))
    count = max(8, min(MAX_FALLBACK_SAMPLE_COUNT, count))
    try:
        params = road2d.DivideByCount(count, True)
    except:
        params = None
    if params:
        for t in params:
            pt = road2d.PointAt(t)
            station = length_at_parameter(road2d, t)
            samples.append({"station": station, "point": rg.Point3d(pt.X, pt.Y, 0.0), "source": "fallback"})
    else:
        d = road2d.Domain
        for t in [d.T0, d.T1]:
            pt = road2d.PointAt(t)
            station = length_at_parameter(road2d, t)
            samples.append({"station": station, "point": rg.Point3d(pt.X, pt.Y, 0.0), "source": "fallback"})
    return samples


def road_sample_points(road2d, anchors):
    """Return sorted station/point samples.

    Original road vertices are preserved. Contour-intersection anchor points are
    inserted as additional samples so the lifted curve still hits contour levels.
    """
    total_len = road2d.GetLength()
    is_closed = curve_is_closed(road2d)

    # 1. Preserve original road vertices/control points.
    samples = original_road_sample_points(road2d)

    # 2. Add contour intersection anchor locations as extra samples.
    for a in anchors:
        try:
            t = parameter_at_length(road2d, a["station"])
            pt = road2d.PointAt(t)
            samples.append({
                "station": a["station"],
                "point": rg.Point3d(pt.X, pt.Y, 0.0),
                "source": "anchor"
            })
        except:
            pass

    # 3. Ensure endpoints for open curves without removing intermediate points.
    if not is_closed:
        d = road2d.Domain
        for t in [d.T0, d.T1]:
            pt = road2d.PointAt(t)
            station = length_at_parameter(road2d, t)
            samples.append({
                "station": station,
                "point": rg.Point3d(pt.X, pt.Y, 0.0),
                "source": "endpoint"
            })

    return merge_duplicate_samples(samples, total_len, is_closed)


def parameter_at_length(curve, target_length):
    total = curve.GetLength()
    if target_length <= 0.0:
        return curve.Domain.T0
    if target_length >= total:
        return curve.Domain.T1
    try:
        rc, t = curve.LengthParameter(target_length)
        if rc:
            return t
    except:
        pass
    # Approximate fallback by domain ratio.
    d = curve.Domain
    return d.T0 + (d.T1 - d.T0) * (target_length / total)


def merge_duplicate_samples(samples, total_len, is_closed):
    """Remove only true duplicate samples.

    v1 used STATION_MERGE_TOL, which could merge close but legitimate GIS vertices.
    v2 keeps original points and only removes essentially identical stations.
    If an anchor and an original vertex fall at the same station, the original
    vertex is kept.
    """
    if not samples:
        return []

    normalized = []
    for s in samples:
        station = s["station"]
        if is_closed and abs(station - total_len) <= DEFAULT_TOLERANCE:
            station = 0.0
        normalized.append({
            "station": station,
            "point": s["point"],
            "source": s.get("source", "sample")
        })

    normalized = sorted(normalized, key=lambda x: x["station"])
    result = []

    def priority(src):
        if src == "original":
            return 0
        if src == "endpoint":
            return 1
        if src == "anchor":
            return 2
        return 3

    for s in normalized:
        if not result:
            result.append(s)
            continue

        last = result[-1]
        same_station = abs(s["station"] - last["station"]) <= SAMPLE_DUP_TOL
        same_point = s["point"].DistanceTo(last["point"]) <= DEFAULT_TOLERANCE * 0.1

        if same_station or same_point:
            # Keep the sample that better represents the original road geometry.
            if priority(s.get("source")) < priority(last.get("source")):
                result[-1] = s
            continue
        result.append(s)

    return sorted(result, key=lambda x: x["station"])


def interpolate_z(station, anchors, total_len, is_closed):
    if not anchors:
        return None
    if len(anchors) == 1:
        return anchors[0]["z"]

    anchors = sorted(anchors, key=lambda a: a["station"])

    if not is_closed:
        if station <= anchors[0]["station"]:
            return anchors[0]["z"]
        if station >= anchors[-1]["station"]:
            return anchors[-1]["z"]

        for i in range(len(anchors) - 1):
            a = anchors[i]
            b = anchors[i + 1]
            if a["station"] <= station <= b["station"]:
                span = b["station"] - a["station"]
                if abs(span) < 1e-9:
                    return a["z"]
                ratio = (station - a["station"]) / span
                return a["z"] + (b["z"] - a["z"]) * ratio
        return anchors[-1]["z"]

    # Closed curve: circular interpolation.
    s = station % total_len if total_len > 0 else station
    for i in range(len(anchors)):
        a = anchors[i]
        b = anchors[(i + 1) % len(anchors)]
        a_s = a["station"]
        b_s = b["station"]

        if i < len(anchors) - 1:
            if a_s <= s <= b_s:
                span = b_s - a_s
                if abs(span) < 1e-9:
                    return a["z"]
                ratio = (s - a_s) / span
                return a["z"] + (b["z"] - a["z"]) * ratio
        else:
            # Wrap segment: last anchor -> first anchor + total_len.
            b_s_wrap = b_s + total_len
            s_wrap = s
            if s_wrap < a_s:
                s_wrap += total_len
            if a_s <= s_wrap <= b_s_wrap:
                span = b_s_wrap - a_s
                if abs(span) < 1e-9:
                    return a["z"]
                ratio = (s_wrap - a_s) / span
                return a["z"] + (b["z"] - a["z"]) * ratio

    return anchors[0]["z"]


def build_interpolated_curve(road2d, anchors, tol):
    total_len = road2d.GetLength()
    is_closed = curve_is_closed(road2d)
    samples = road_sample_points(road2d, anchors)

    if len(samples) < 2:
        return None

    pts3d = []
    for s in samples:
        z = interpolate_z(s["station"], anchors, total_len, is_closed)
        if z is None:
            return None
        p = s["point"]
        pts3d.append(rg.Point3d(p.X, p.Y, z))

    if is_closed and len(pts3d) >= 3:
        if pts3d[0].DistanceTo(pts3d[-1]) > tol:
            pts3d.append(rg.Point3d(pts3d[0]))

    if len(pts3d) == 2:
        return rg.LineCurve(pts3d[0], pts3d[1])

    poly = rg.Polyline(pts3d)
    if not poly.IsValid:
        return None
    return poly.ToNurbsCurve()

# -----------------------------------------------------------------------------
# Split-segment interpolation
# -----------------------------------------------------------------------------
def format_elevation(z):
    try:
        if abs(float(z) - round(float(z))) < 1e-6:
            return str(int(round(float(z))))
        return ("{:.2f}".format(float(z))).rstrip('0').rstrip('.')
    except:
        return str(z)


def z_is_same(a, b, tol=0.01):
    return abs(float(a) - float(b)) <= tol


def point_at_station(curve, station):
    total_len = curve.GetLength()
    if total_len <= 0:
        t = curve.Domain.T0
    else:
        s = station
        if curve_is_closed(curve):
            s = s % total_len
        else:
            s = max(0.0, min(total_len, s))
        t = parameter_at_length(curve, s)
    p = curve.PointAt(t)
    return rg.Point3d(p.X, p.Y, 0.0)


def make_anchor_point_sample(road2d, station, z, label):
    return {
        "station": station,
        "point": point_at_station(road2d, station),
        "z": z,
        "source": label
    }


def collect_samples_for_interval(road2d, samples, s0, s1, z0, z1, is_closed):
    """Collect original road samples that lie inside an interval.

    For closed roads, s1 may be larger than total_len in the wrap interval.
    Samples are copied without reducing the original vertex count. End anchors are
    always inserted explicitly.
    """
    total_len = road2d.GetLength()
    result = []

    # Explicit segment start.
    result.append(make_anchor_point_sample(road2d, s0, z0, "segment_start"))

    for smp in samples:
        s = smp["station"]
        candidates = [s]
        if is_closed:
            candidates.append(s + total_len)

        chosen = None
        for c in candidates:
            if c > s0 + SAMPLE_DUP_TOL and c < s1 - SAMPLE_DUP_TOL:
                chosen = c
                break
        if chosen is None:
            continue

        result.append({
            "station": chosen,
            "point": rg.Point3d(smp["point"]),
            "source": smp.get("source", "sample")
        })

    # Explicit segment end.
    result.append(make_anchor_point_sample(road2d, s1, z1, "segment_end"))
    result = sorted(result, key=lambda x: x["station"])

    # Remove true duplicates only. Do not remove normal close GIS vertices.
    cleaned = []
    for r in result:
        if not cleaned:
            cleaned.append(r)
            continue
        last = cleaned[-1]
        if abs(r["station"] - last["station"]) <= SAMPLE_DUP_TOL:
            cleaned[-1] = r
            continue
        if r["point"].DistanceTo(last["point"]) <= DEFAULT_TOLERANCE * 0.1:
            # Prefer explicit segment endpoints over ordinary samples.
            if r.get("source") in ["segment_start", "segment_end"]:
                cleaned[-1] = r
            continue
        cleaned.append(r)

    return cleaned


def interpolate_between(station, s0, s1, z0, z1):
    span = s1 - s0
    if abs(span) < 1e-9:
        return z0
    ratio = (station - s0) / span
    return z0 + (z1 - z0) * ratio


def build_segment_curve(road2d, samples, s0, s1, z0, z1, is_closed, tol):
    seg_samples = collect_samples_for_interval(road2d, samples, s0, s1, z0, z1, is_closed)
    if len(seg_samples) < 2:
        return None

    pts3d = []
    for smp in seg_samples:
        z = interpolate_between(smp["station"], s0, s1, z0, z1)
        p = smp["point"]
        pts3d.append(rg.Point3d(p.X, p.Y, z))

    # Remove duplicate consecutive points, but preserve legitimate original vertices.
    cleaned = []
    for p in pts3d:
        if cleaned and p.DistanceTo(cleaned[-1]) <= tol * 0.1:
            continue
        cleaned.append(p)

    if len(cleaned) < 2:
        return None
    if len(cleaned) == 2:
        return rg.LineCurve(cleaned[0], cleaned[1])

    poly = rg.Polyline(cleaned)
    if not poly.IsValid:
        return None
    return poly.ToNurbsCurve()


def segment_display_name(road_index, segment_index, z0, z1):
    if z_is_same(z0, z1):
        return "RoadZ_{:03d}_{:03d}_ELEV_{}".format(
            road_index,
            segment_index,
            format_elevation(z0)
        )
    return "RoadZ_{:03d}_{:03d}_{}_to_{}".format(
        road_index,
        segment_index,
        format_elevation(z0),
        format_elevation(z1)
    )


def segment_status(z0, z1, is_extension=False, single_anchor=False):
    if z_is_same(z0, z1):
        elev = format_elevation(z0)
        if single_anchor:
            return "FLAT", u"교차점 1개: 전체 커브를 ELEV_{} 평탄 처리".format(elev)
        if is_extension:
            return "FLAT", u"등고 교차점 바깥 ELEV_{} 평평한 연장 구간".format(elev)
        return "FLAT", u"ELEV_{} 평평한 구간".format(elev)

    if is_extension:
        return "CHECK", u"등고 교차점 바깥 연장 구간"
    dz = abs(z1 - z0)
    if dz > MAX_Z_JUMP_FOR_OK:
        return "CHECK", u"구간 높이 차이 {:.2f}m".format(dz)
    return "OK", u"정상"


def make_intervals_from_anchors(road2d, anchors):
    """Return intervals to generate as split curves.

    Each interval dict has:
        s0, s1, z0, z1, extension, single_anchor

    Open roads preserve sections before the first anchor and after the last anchor
    as constant-height extension segments. Closed roads are split between every
    consecutive anchor, including the wrap segment.
    """
    total_len = road2d.GetLength()
    is_closed = curve_is_closed(road2d)
    anchors = sorted(anchors, key=lambda a: a["station"])
    intervals = []

    if not anchors:
        return intervals

    if len(anchors) == 1:
        intervals.append({
            "s0": 0.0,
            "s1": total_len,
            "z0": anchors[0]["z"],
            "z1": anchors[0]["z"],
            "extension": True,
            "single_anchor": True
        })
        return intervals

    if not is_closed:
        first = anchors[0]
        last = anchors[-1]

        if first["station"] > SAMPLE_DUP_TOL:
            intervals.append({
                "s0": 0.0,
                "s1": first["station"],
                "z0": first["z"],
                "z1": first["z"],
                "extension": True,
                "single_anchor": False
            })

        for i in range(len(anchors) - 1):
            a = anchors[i]
            b = anchors[i + 1]
            if b["station"] - a["station"] <= SAMPLE_DUP_TOL:
                continue
            intervals.append({
                "s0": a["station"],
                "s1": b["station"],
                "z0": a["z"],
                "z1": b["z"],
                "extension": False,
                "single_anchor": False
            })

        if total_len - last["station"] > SAMPLE_DUP_TOL:
            intervals.append({
                "s0": last["station"],
                "s1": total_len,
                "z0": last["z"],
                "z1": last["z"],
                "extension": True,
                "single_anchor": False
            })

        return intervals

    # Closed road: anchor-to-anchor, including wrap segment.
    for i in range(len(anchors)):
        a = anchors[i]
        b = anchors[(i + 1) % len(anchors)]
        s0 = a["station"]
        s1 = b["station"]
        if i == len(anchors) - 1:
            s1 += total_len
        if s1 - s0 <= SAMPLE_DUP_TOL:
            continue
        intervals.append({
            "s0": s0,
            "s1": s1,
            "z0": a["z"],
            "z1": b["z"],
            "extension": False,
            "single_anchor": False
        })

    return intervals


# -----------------------------------------------------------------------------
# Main process
# -----------------------------------------------------------------------------
def process_road_curve_split(obj_id, contours, tol, road_index):
    road = rs.coercecurve(obj_id)
    if not road:
        return [], u"도로 커브를 읽지 못함"

    road2d = project_curve_to_xy(road)
    if not road2d:
        return [], u"도로 커브 XY 투영 실패"

    anchors, tested_count = collect_road_contour_anchors(road2d, contours, tol)
    if not anchors:
        return [{
            "status": "FAILED",
            "curve": road2d,
            "name": "RoadZ_{:03d}_FAILED_NoAnchor".format(road_index),
            "info": u"등고선과 교차점 없음 / contours tested: {}".format(tested_count)
        }], u"등고선과 교차점 없음"

    samples = road_sample_points(road2d, anchors)
    intervals = make_intervals_from_anchors(road2d, anchors)
    is_closed = curve_is_closed(road2d)

    results = []
    for seg_index, iv in enumerate(intervals, 1):
        z0 = iv["z0"]
        z1 = iv["z1"]
        crv = build_segment_curve(
            road2d,
            samples,
            iv["s0"],
            iv["s1"],
            z0,
            z1,
            is_closed,
            tol
        )
        status, msg = segment_status(z0, z1, iv.get("extension", False), iv.get("single_anchor", False))
        name = segment_display_name(road_index, seg_index, z0, z1)

        if not crv:
            status = "FAILED"
            crv = road2d
            msg = u"Split 구간 3D 커브 생성 실패"
            name = "RoadZ_{:03d}_{:03d}_FAILED".format(road_index, seg_index)

        results.append({
            "status": status,
            "curve": crv,
            "name": name,
            "info": msg
        })

    summary = u"anchors: {} / split segments: {} / contours tested: {}".format(
        len(anchors),
        len(results),
        tested_count
    )
    return results, summary


def main():
    tol = rs.GetReal(u"교차 허용오차를 입력하세요", DEFAULT_TOLERANCE, 0.0001)
    if tol is None:
        return

    contours = get_contour_objects()
    if not contours:
        rs.MessageBox(u"사용 가능한 3D 등고선 커브가 없습니다.")
        return

    rs.MessageBox(u"3D 등고선 {}개를 불러왔습니다.\n이제 Z 보간할 도로 커브를 선택하세요.".format(len(contours)))

    road_ids = rs.GetObjects(
        u"Z 보간할 도로 커브를 선택하세요. 선택한 커브만 계산합니다.",
        rs.filter.curve,
        preselect=True
    )
    if not road_ids:
        return

    ensure_layer(OUTPUT_LAYER_OK, System.Drawing.Color.DeepSkyBlue)
    ensure_layer(OUTPUT_LAYER_FLAT, System.Drawing.Color.LimeGreen)
    ensure_layer(OUTPUT_LAYER_CHECK, System.Drawing.Color.Orange)
    ensure_layer(OUTPUT_LAYER_FAILED, System.Drawing.Color.Red)

    rs.EnableRedraw(False)

    ok_count = 0
    flat_count = 0
    check_count = 0
    failed_count = 0
    total_segment_count = 0

    for road_index, obj_id in enumerate(road_ids, 1):
        try:
            segments, summary = process_road_curve_split(obj_id, contours, tol, road_index)
            print(u"[Road {} / {}] {}".format(road_index, len(road_ids), summary))

            for seg in segments:
                status = seg["status"]
                crv = seg["curve"]
                name = seg["name"]
                info = seg["info"]
                total_segment_count += 1

                if status == "OK":
                    add_curve_to_layer(crv, OUTPUT_LAYER_OK, System.Drawing.Color.DeepSkyBlue, name)
                    ok_count += 1
                elif status == "FLAT":
                    add_curve_to_layer(crv, OUTPUT_LAYER_FLAT, System.Drawing.Color.LimeGreen, name)
                    flat_count += 1
                elif status == "CHECK":
                    add_curve_to_layer(crv, OUTPUT_LAYER_CHECK, System.Drawing.Color.Orange, name)
                    check_count += 1
                else:
                    if crv:
                        add_curve_to_layer(crv, OUTPUT_LAYER_FAILED, System.Drawing.Color.Red, name)
                    failed_count += 1
                print(u"    - {} : {} : {}".format(status, name, info))

        except Exception as ex:
            failed_count += 1
            print(u"[Road {} / {}] FAILED : {}".format(road_index, len(road_ids), ex))

    rs.EnableRedraw(True)
    sc.doc.Views.Redraw()

    rs.MessageBox(
        u"도로 Z 보간 완료\n\nSplit 구간: {}개\nOK: {}개\nFlat: {}개\nCheck: {}개\nFailed: {}개".format(
            total_segment_count,
            ok_count,
            flat_count,
            check_count,
            failed_count
        )
    )


if __name__ == "__main__":
    main()
