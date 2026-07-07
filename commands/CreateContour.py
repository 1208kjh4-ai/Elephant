# -*- coding: utf-8 -*-
from __future__ import print_function

import os
import re
import sys

ELEPHANT_DIR = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
if ELEPHANT_DIR not in sys.path:
    sys.path.insert(0, ELEPHANT_DIR)

import rhinoscriptsyntax as rs
import Rhino
import Rhino.Geometry as rg
import Rhino.DocObjects as rd
import scriptcontext as sc
import System

import Eto.Forms as forms
import Eto.Drawing as drawing

try:
    import shapefile
except ImportError:
    rs.MessageBox(u"shapefile.py 모듈을 찾을 수 없습니다.\nshapefile.py가 Elephant 폴더 바로 아래에 있는지 확인해주세요.")
    shapefile = None

try:
    unicode
except NameError:
    unicode = str

try:
    bytes
except NameError:
    bytes = str


# =============================================================================
# Text / DBF encoding utilities
# =============================================================================

def text_quality_score(text):
    if text is None:
        return -9999
    try:
        s = unicode(text)
    except Exception:
        return -9999

    score = 0.0
    if u"占" in s or u"쏙" in s or u"옙" in s or u"�" in s:
        score -= 20.0

    for ch in s:
        o = ord(ch)
        if (0xAC00 <= o <= 0xD7A3) or (0x1100 <= o <= 0x11FF) or (0x3130 <= o <= 0x318F):
            score += 6.0
        elif ch.isalnum() or ch in u" _-./()[]{}":
            score += 0.3
        elif ch in u"�ÃÂ¤¥µíêë¹º¼½¾¿ÀÁÇÐÑØÙÚÛÜÝÞß占쏙옙":
            score -= 2.5
        elif 0x80 <= o <= 0x9F:
            score -= 4.0
        elif o > 127:
            score -= 0.3
    return score


def repair_mojibake(text):
    if text is None:
        return u""
    try:
        s = unicode(text)
    except Exception:
        return u""

    candidates = [s]
    for src in ['latin1', 'cp1252']:
        for dst in ['cp949', 'euc-kr', 'utf-8']:
            try:
                candidates.append(s.encode(src, 'strict').decode(dst, 'strict'))
            except Exception:
                pass

    best = candidates[0]
    best_score = text_quality_score(best)
    for c in candidates[1:]:
        score = text_quality_score(c)
        if score > best_score:
            best = c
            best_score = score
    return best


def to_unicode(value, preferred_encoding=None):
    if value is None:
        return u""

    if isinstance(value, bytes) and not isinstance(value, unicode):
        encodings = []
        if preferred_encoding:
            encodings.append(preferred_encoding)
        encodings.extend(['cp949', 'euc-kr', 'utf-8', 'utf-8-sig', 'latin1'])

        best = u""
        best_score = -9999
        for enc in encodings:
            try:
                decoded = value.decode(enc, 'ignore')
                repaired = repair_mojibake(decoded)
                score = text_quality_score(repaired)
                if score > best_score:
                    best = repaired
                    best_score = score
            except Exception:
                pass
        return best

    try:
        return repair_mojibake(unicode(value))
    except Exception:
        return u""


def to_float(value, default=None):
    if value is None:
        return default
    try:
        if isinstance(value, str):
            value = value.strip()
        return float(value)
    except Exception:
        try:
            return float(to_unicode(value).strip())
        except Exception:
            return default


# =============================================================================
# Geometry / Rhino helpers
# =============================================================================

def distance_xy(a, b):
    return rg.Point3d(a.X, a.Y, 0.0).DistanceTo(rg.Point3d(b.X, b.Y, 0.0))


def is_same_xy(a, b, tol):
    return distance_xy(a, b) <= tol


def clean_points(points, tol):
    cleaned = []
    for pt in points:
        if not cleaned or distance_xy(cleaned[-1], pt) > tol:
            cleaned.append(pt)
    return cleaned


def points_to_curve(points):
    if not points or len(points) < 2:
        return None
    try:
        return rg.Polyline(points).ToNurbsCurve()
    except Exception:
        return None


def sanitize_layer_name(name):
    if not name:
        return u"Layer"
    s = to_unicode(name)
    s = re.sub(u"[\\/:*?\"<>|]", u"_", s)
    s = s.strip()
    if not s:
        s = u"Layer"
    if len(s) > 80:
        s = s[:80]
    return s


def make_layer(layer_name, color):
    if not rs.IsLayer(layer_name):
        rs.AddLayer(layer_name, color)
    return sc.doc.Layers.Find(layer_name, True)


def add_curve_to_layer(curve, layer_name, color, name=None):
    if curve is None:
        return None
    layer_index = make_layer(layer_name, color)
    attr = rd.ObjectAttributes()
    attr.LayerIndex = layer_index
    if name:
        attr.Name = name
    return sc.doc.Objects.AddCurve(curve, attr)


def add_brep_to_layer(brep, layer_name, color, name=None):
    if brep is None:
        return None
    layer_index = make_layer(layer_name, color)
    attr = rd.ObjectAttributes()
    attr.LayerIndex = layer_index
    if name:
        attr.Name = name
    return sc.doc.Objects.AddBrep(brep, attr)


def duplicate_curve_safe(curve):
    if curve is None:
        return None
    try:
        return curve.DuplicateCurve()
    except Exception:
        return curve


def duplicate_brep_safe(brep):
    if brep is None:
        return None
    try:
        return brep.DuplicateBrep()
    except Exception:
        return brep


def ensure_curve_closed(curve, tol):
    if curve is None:
        return None
    crv = duplicate_curve_safe(curve)
    if crv is None:
        return None

    try:
        if crv.IsClosed:
            return crv
    except Exception:
        pass

    try:
        if crv.PointAtStart.DistanceTo(crv.PointAtEnd) <= tol:
            try:
                crv.MakeClosed(tol)
            except Exception:
                pass
    except Exception:
        pass

    try:
        if crv.IsClosed:
            return crv
    except Exception:
        pass
    return None


def curve_bbox_center_xy(curve):
    if curve is None:
        return (0.0, 0.0)
    try:
        bb = curve.GetBoundingBox(True)
        c = bb.Center
        return (c.X, c.Y)
    except Exception:
        return (0.0, 0.0)


def brep_bbox_center_xy(brep):
    if brep is None:
        return (0.0, 0.0)
    try:
        bb = brep.GetBoundingBox(True)
        c = bb.Center
        return (c.X, c.Y)
    except Exception:
        return (0.0, 0.0)


def join_curves_safely(curves, tol):
    clean = []
    for c in curves:
        if c is None:
            continue
        try:
            if c.IsValid:
                clean.append(c)
        except Exception:
            pass
    if not clean:
        return []
    if len(clean) == 1:
        return clean

    try:
        arr = System.Array[rg.Curve](clean)
        joined = rg.Curve.JoinCurves(arr, tol)
        if joined:
            return list(joined)
    except Exception:
        pass

    try:
        joined = rg.Curve.JoinCurves(clean, tol)
        if joined:
            return list(joined)
    except Exception:
        pass

    return clean


# =============================================================================
# SHP reader
# =============================================================================

class ShpData(object):
    def __init__(self, path, reader, fields, records, shapes, encoding):
        self.path = path
        self.reader = reader
        self.fields = fields
        self.records = records
        self.shapes = shapes
        self.encoding = encoding


def make_shp_reader(path, encoding):
    try:
        return shapefile.Reader(path, encoding=encoding, encodingErrors='strict')
    except TypeError:
        return shapefile.Reader(path, encoding=encoding)


def shp_decoding_score(fields, records):
    samples = []
    samples.extend(fields)
    try:
        limit = min(len(records), 20)
        for i in range(limit):
            rec = records[i]
            for v in rec:
                if isinstance(v, unicode):
                    samples.append(v)
                elif isinstance(v, bytes):
                    samples.append(to_unicode(v))
    except Exception:
        pass

    if not samples:
        return -9999
    return sum(text_quality_score(x) for x in samples) / float(len(samples))


def read_shp(path):
    if shapefile is None:
        return None

    encodings = ['cp949', 'euc-kr', 'utf-8', 'utf-8-sig', 'latin1']
    candidates = []
    last_error = None

    for enc in encodings:
        try:
            sf = make_shp_reader(path, enc)
            records = sf.records()
            shapes = sf.shapes()
            raw_fields = [f[0] for f in sf.fields[1:]]
            fields = [to_unicode(f, enc) for f in raw_fields]
            score = shp_decoding_score(fields, records)
            candidates.append((score, enc, sf, fields, records, shapes))
        except Exception as e:
            last_error = e

    if not candidates:
        rs.MessageBox(u"SHP 파일을 읽는 데 실패했습니다.\n{}\n\n{}".format(path, last_error))
        return None

    candidates.sort(key=lambda x: x[0], reverse=True)
    score, enc, sf, fields, records, shapes = candidates[0]
    return ShpData(path, sf, fields, records, shapes, enc)


def shape_is_polygon(shape):
    try:
        return "POLYGON" in shape.shapeTypeName.upper()
    except Exception:
        pass
    try:
        return int(shape.shapeType) in [5, 15, 25, 31]
    except Exception:
        return False


def shape_parts_to_point_lists(shape, force_close_polygon=True, tol=0.001):
    pts_raw = shape.points
    if not pts_raw or len(pts_raw) < 2:
        return []

    try:
        parts = list(shape.parts)
    except Exception:
        parts = [0]
    parts.append(len(pts_raw))

    result = []
    for i in range(len(parts) - 1):
        start = parts[i]
        end = parts[i + 1]
        if end - start < 2:
            continue

        pts = []
        for p in pts_raw[start:end]:
            try:
                pts.append(rg.Point3d(float(p[0]), float(p[1]), 0.0))
            except Exception:
                pass

        pts = clean_points(pts, tol)
        if len(pts) < 2:
            continue

        if force_close_polygon and shape_is_polygon(shape):
            if not is_same_xy(pts[0], pts[-1], tol):
                pts.append(rg.Point3d(pts[0].X, pts[0].Y, 0.0))

        result.append(pts)

    return result


# =============================================================================
# Data containers
# =============================================================================

class ContourData(object):
    def __init__(self, curve_3d, elevation, source_index, part_index):
        self.curve_3d = curve_3d
        self.elevation = elevation
        self.source_index = source_index
        self.part_index = part_index


class RoadRawBorderData(object):
    def __init__(self, curve_2d, source_path, source_index, part_index, is_closed):
        self.curve_2d = curve_2d
        self.source_path = source_path
        self.source_name = os.path.splitext(os.path.basename(source_path))[0]
        self.source_index = source_index
        self.part_index = part_index
        self.is_closed = is_closed


class RoadSurfaceData(object):
    def __init__(self, brep, source_path, source_index, brep_index):
        self.brep = brep
        self.source_path = source_path
        self.source_name = os.path.splitext(os.path.basename(source_path))[0]
        self.source_index = source_index
        self.brep_index = brep_index


class RoadDupBorderData(object):
    def __init__(self, curve_2d, border_index, joined_surface_count=0):
        self.curve_2d = curve_2d
        self.border_index = border_index
        self.joined_surface_count = joined_surface_count


# =============================================================================
# Contour / road builders
# =============================================================================

def build_contours(shp_data, height_field_index, tol):
    contours = []
    if shp_data is None:
        return contours

    for shape_index, shape in enumerate(shp_data.shapes):
        if shape_index >= len(shp_data.records):
            continue
        record = shp_data.records[shape_index]
        if height_field_index < 0 or height_field_index >= len(record):
            continue

        elevation = to_float(record[height_field_index], None)
        if elevation is None:
            continue

        point_lists = shape_parts_to_point_lists(shape, force_close_polygon=False, tol=tol)
        for part_index, pts2d in enumerate(point_lists):
            pts3d = [rg.Point3d(p.X, p.Y, elevation) for p in pts2d]
            crv3d = points_to_curve(pts3d)
            if crv3d:
                contours.append(ContourData(crv3d, elevation, shape_index, part_index))

    return contours


def try_create_planar_breps_from_curves(curves, tol):
    if not curves:
        return []

    clean = []
    for c in curves:
        closed = ensure_curve_closed(c, tol)
        if closed:
            clean.append(closed)

    if not clean:
        return []

    # Best case: give all rings of one SHP polygon to CreatePlanarBreps together.
    # This lets Rhino detect inner loops/holes when the ring nesting is valid.
    try:
        arr = System.Array[rg.Curve](clean)
        breps = rg.Brep.CreatePlanarBreps(arr, tol)
        if breps:
            return [b for b in breps if b is not None]
    except Exception:
        pass

    try:
        breps = rg.Brep.CreatePlanarBreps(clean, tol)
        if breps:
            return [b for b in breps if b is not None]
    except Exception:
        pass

    # Fallback: create surfaces one ring at a time.
    out = []
    for c in clean:
        try:
            arr = System.Array[rg.Curve]([c])
            breps = rg.Brep.CreatePlanarBreps(arr, tol)
            if breps:
                out.extend([b for b in breps if b is not None])
                continue
        except Exception:
            pass
        try:
            breps = rg.Brep.CreatePlanarBreps([c], tol)
            if breps:
                out.extend([b for b in breps if b is not None])
        except Exception:
            pass
    return out


def build_road_surfaces_from_shp_paths(paths, tol):
    raw_borders = []
    surfaces = []
    failed_paths = []
    failed_surface_shapes = 0
    non_polygon_shapes = 0

    for path in paths:
        shp_data = read_shp(path)
        if shp_data is None:
            failed_paths.append(path)
            continue

        for shape_index, shape in enumerate(shp_data.shapes):
            if not shape_is_polygon(shape):
                non_polygon_shapes += 1

            point_lists = shape_parts_to_point_lists(shape, force_close_polygon=True, tol=tol)
            ring_curves = []

            for part_index, pts in enumerate(point_lists):
                if len(pts) < 4:
                    continue
                is_closed = is_same_xy(pts[0], pts[-1], tol)
                crv = points_to_curve([rg.Point3d(p.X, p.Y, 0.0) for p in pts])
                if crv:
                    closed = ensure_curve_closed(crv, tol)
                    if closed:
                        ring_curves.append(closed)
                        raw_borders.append(RoadRawBorderData(closed, path, shape_index, part_index, True))
                    else:
                        raw_borders.append(RoadRawBorderData(crv, path, shape_index, part_index, is_closed))

            if not ring_curves:
                failed_surface_shapes += 1
                continue

            breps = try_create_planar_breps_from_curves(ring_curves, tol)
            if not breps:
                failed_surface_shapes += 1
                continue

            for bi, brep in enumerate(breps):
                surfaces.append(RoadSurfaceData(brep, path, shape_index, bi))

    return raw_borders, surfaces, failed_paths, failed_surface_shapes, non_polygon_shapes


# =============================================================================
# Join + DupBorder / Naked border extraction
# =============================================================================

def chunk_items(items, chunk_size):
    chunk_size = max(2, int(chunk_size))
    for i in range(0, len(items), chunk_size):
        yield items[i:i + chunk_size]


def try_join_breps(breps, tol):
    clean = []
    for b in breps:
        if b is None:
            continue
        dup = duplicate_brep_safe(b)
        if dup:
            clean.append(dup)

    if not clean:
        return []
    if len(clean) == 1:
        return clean

    try:
        arr = System.Array[rg.Brep](clean)
        joined = rg.Brep.JoinBreps(arr, tol)
        if joined:
            return [b for b in joined if b is not None]
    except Exception:
        pass

    try:
        joined = rg.Brep.JoinBreps(clean, tol)
        if joined:
            return [b for b in joined if b is not None]
    except Exception:
        pass

    return clean


def join_breps_safely(surface_data, tol, chunk_size=200, max_passes=5):
    source = []
    for s in surface_data:
        if s and s.brep:
            source.append(s.brep)

    source = sorted(source, key=brep_bbox_center_xy)
    if not source:
        return []

    current = source
    chunk_size = max(2, int(chunk_size))

    for _pass in range(max(1, int(max_passes))):
        next_breps = []
        for chunk in chunk_items(current, chunk_size):
            res = try_join_breps(chunk, tol)
            if res:
                next_breps.extend(res)
            else:
                next_breps.extend(chunk)

        next_breps = [b for b in next_breps if b is not None]
        next_breps = sorted(next_breps, key=brep_bbox_center_xy)

        if not next_breps:
            break

        if len(next_breps) >= len(current):
            # One final attempt when the set is not too large.
            if 1 < len(next_breps) <= chunk_size * 2:
                final_res = try_join_breps(next_breps, tol)
                if final_res:
                    next_breps = final_res
            current = next_breps
            break

        current = next_breps

    return [b for b in current if b is not None]


def duplicate_brep_border_curves(brep, tol):
    if brep is None:
        return []

    edge_curves = []

    # Rhino's DupBorder behavior is closest to naked edge duplication after joining.
    try:
        curves = brep.DuplicateNakedEdgeCurves(True, True)
        if curves:
            edge_curves.extend([c for c in curves if c is not None])
    except Exception:
        pass

    # Fallback only. This can include more than Naked edges depending on Brep structure,
    # so it is used only when DuplicateNakedEdgeCurves is not available/failed.
    if not edge_curves:
        try:
            for loop in brep.Loops:
                try:
                    c = loop.To3dCurve()
                    if c:
                        edge_curves.append(c)
                except Exception:
                    pass
        except Exception:
            pass

    if not edge_curves:
        return []

    joined = join_curves_safely(edge_curves, tol)
    result = []
    for c in joined:
        if c is None:
            continue
        try:
            if c.IsValid:
                result.append(c)
        except Exception:
            pass
    return result


def extract_dup_borders_from_surfaces(surface_data, tol, chunk_size):
    joined_breps = join_breps_safely(surface_data, tol, chunk_size=chunk_size, max_passes=5)
    border_data = []
    idx = 0
    for brep in joined_breps:
        curves = duplicate_brep_border_curves(brep, tol)
        for crv in curves:
            if crv:
                border_data.append(RoadDupBorderData(crv, idx, joined_surface_count=len(joined_breps)))
                idx += 1
    return border_data, joined_breps


# =============================================================================
# Preview conduit
# =============================================================================

class LayerPreviewConduit(Rhino.Display.DisplayConduit):
    def __init__(self):
        Rhino.Display.DisplayConduit.__init__(self)
        self.contours = []
        self.raw_roads = []
        self.dup_borders = []
        self.bbox = rg.BoundingBox.Empty
        self.color_contour = System.Drawing.Color.FromArgb(120, 120, 120)
        self.color_raw = System.Drawing.Color.DeepSkyBlue
        self.color_dup = System.Drawing.Color.Orange

    def update(self, contours, raw_roads, dup_borders=None, show_contours=True, show_raw=True, show_dup=True):
        self.contours = []
        self.raw_roads = []
        self.dup_borders = []
        self.bbox = rg.BoundingBox.Empty

        if show_contours:
            for c in contours:
                if c.curve_3d:
                    self.contours.append(c.curve_3d)
                    self.bbox.Union(c.curve_3d.GetBoundingBox(True))

        if show_raw:
            for r in raw_roads:
                if r.curve_2d:
                    self.raw_roads.append(r.curve_2d)
                    self.bbox.Union(r.curve_2d.GetBoundingBox(True))

        if show_dup and dup_borders:
            for d in dup_borders:
                if d.curve_2d:
                    self.dup_borders.append(d.curve_2d)
                    self.bbox.Union(d.curve_2d.GetBoundingBox(True))

        sc.doc.Views.Redraw()

    def CalculateBoundingBox(self, e):
        if self.bbox.IsValid:
            e.IncludeBoundingBox(self.bbox)

    def DrawForeground(self, e):
        for crv in self.contours:
            e.Display.DrawCurve(crv, self.color_contour, 1)
        for crv in self.raw_roads:
            e.Display.DrawCurve(crv, self.color_raw, 1)
        for crv in self.dup_borders:
            e.Display.DrawCurve(crv, self.color_dup, 3)


# =============================================================================
# Baking
# =============================================================================

def bake_contours(contours):
    count = 0
    layer_name = u"GIS_Contour_3D"
    color = System.Drawing.Color.FromArgb(120, 120, 120)

    for c in contours:
        if not c.curve_3d:
            continue
        obj_id = add_curve_to_layer(c.curve_3d, layer_name, color, u"Contour_{:.3f}".format(c.elevation))
        if obj_id:
            try:
                rs.SetUserText(obj_id, "Elevation", str(c.elevation))
                rs.SetUserText(obj_id, "SourceShapeIndex", str(c.source_index))
                rs.SetUserText(obj_id, "SourcePartIndex", str(c.part_index))
            except Exception:
                pass
            count += 1
    return count


def bake_raw_road_borders(raw_roads):
    count = 0
    color = System.Drawing.Color.DeepSkyBlue

    for r in raw_roads:
        if not r.curve_2d:
            continue
        base = sanitize_layer_name(r.source_name)
        layer_name = u"GIS_Road_Raw_Border_{}".format(base)
        name = u"RoadRawBorder_{}_part{}".format(r.source_index, r.part_index)
        obj_id = add_curve_to_layer(r.curve_2d, layer_name, color, name)
        if obj_id:
            try:
                rs.SetUserText(obj_id, "SourceSHP", r.source_path)
                rs.SetUserText(obj_id, "SourceShapeIndex", str(r.source_index))
                rs.SetUserText(obj_id, "SourcePartIndex", str(r.part_index))
                rs.SetUserText(obj_id, "IsClosed", str(r.is_closed))
                rs.SetUserText(obj_id, "ZInterpolation", "None")
                rs.SetUserText(obj_id, "BorderMode", "RawPolygonRing")
            except Exception:
                pass
            count += 1
    return count


def bake_dup_borders(dup_borders):
    count = 0
    color = System.Drawing.Color.Orange
    layer_name = u"GIS_Road_DupBorder"

    for d in dup_borders:
        if not d.curve_2d:
            continue
        name = u"RoadDupBorder_{}".format(d.border_index)
        obj_id = add_curve_to_layer(d.curve_2d, layer_name, color, name)
        if obj_id:
            try:
                rs.SetUserText(obj_id, "BorderMode", "JoinBreps_DuplicateNakedBorder")
                rs.SetUserText(obj_id, "JoinedSurfaceCount", str(d.joined_surface_count))
                rs.SetUserText(obj_id, "ZInterpolation", "None")
            except Exception:
                pass
            count += 1
    return count


def bake_surfaces(surfaces):
    count = 0
    color = System.Drawing.Color.FromArgb(180, 180, 180)
    layer_name = u"GIS_Road_Surface_Temp"

    for s in surfaces:
        if not s.brep:
            continue
        name = u"RoadSurface_{}_{}".format(s.source_index, s.brep_index)
        obj_id = add_brep_to_layer(s.brep, layer_name, color, name)
        if obj_id:
            try:
                rs.SetUserText(obj_id, "SourceSHP", s.source_path)
                rs.SetUserText(obj_id, "SourceShapeIndex", str(s.source_index))
                rs.SetUserText(obj_id, "BrepIndex", str(s.brep_index))
                rs.SetUserText(obj_id, "TemporaryRoadSurface", "True")
            except Exception:
                pass
            count += 1
    return count


def bake_all(contours, raw_roads, dup_borders, surfaces, bake_c=True, bake_raw=True, bake_dup=True, bake_surf=False):
    rs.EnableRedraw(False)
    c_count = 0
    raw_count = 0
    dup_count = 0
    surf_count = 0
    try:
        if bake_c:
            c_count = bake_contours(contours)
        if bake_raw:
            raw_count = bake_raw_road_borders(raw_roads)
        if bake_dup:
            dup_count = bake_dup_borders(dup_borders)
        if bake_surf:
            surf_count = bake_surfaces(surfaces)
    finally:
        rs.EnableRedraw(True)
        sc.doc.Views.Redraw()
    return c_count, raw_count, dup_count, surf_count


# =============================================================================
# Modeless UI controller
# =============================================================================

class ContourRoadLayerLoaderController(object):
    def __init__(self, contour_shp):
        self.contour_shp = contour_shp
        self.contours = []
        self.raw_roads = []
        self.road_surfaces = []
        self.dup_borders = []
        self.joined_surfaces = []
        self.failed_surface_shapes = 0
        self.non_polygon_shapes = 0
        self.road_paths = []
        self.conduit = LayerPreviewConduit()
        self.conduit.Enabled = True
        self._closed = False
        self._rebuilding = False

        self.form = forms.Form()
        self.form.Title = u"등고선 만들기"
        self.form.Padding = drawing.Padding(18)
        self.form.Resizable = True
        self.form.ClientSize = drawing.Size(650, 390)

        self.setup_ui()
        try:
            self.form.Closed += self.on_closed
        except Exception:
            pass

        self.rebuild_contours()
        self.update_preview()
        self.update_status()

    def setup_ui(self):
        self.cmb_height = forms.DropDown()
        self.cmb_height.DataStore = self.contour_shp.fields
        self.cmb_height.SelectedIndex = self.default_height_field_index()
        self.cmb_height.SelectedIndexChanged += self.on_height_field_changed

        self.nud_tol = forms.NumericStepper()
        self.nud_tol.DecimalPlaces = 3
        self.nud_tol.Increment = 0.05
        self.nud_tol.MinValue = 0.001
        self.nud_tol.MaxValue = 1000.0
        self.nud_tol.Value = 0.1
        self.nud_tol.ValueChanged += self.on_tolerance_changed

        self.nud_join_chunk = forms.NumericStepper()
        self.nud_join_chunk.DecimalPlaces = 0
        self.nud_join_chunk.Increment = 25
        self.nud_join_chunk.MinValue = 5
        self.nud_join_chunk.MaxValue = 1000
        self.nud_join_chunk.Value = 200

        self.chk_preview_contours = forms.CheckBox(Text=u"등고선 프리뷰")
        self.chk_preview_contours.Checked = True
        self.chk_preview_contours.CheckedChanged += self.on_preview_option_changed

        self.chk_preview_raw = forms.CheckBox(Text=u"원본 도로 경계 프리뷰")
        self.chk_preview_raw.Checked = True
        self.chk_preview_raw.CheckedChanged += self.on_preview_option_changed

        self.chk_preview_dup = forms.CheckBox(Text=u"DupBorder 경계 프리뷰")
        self.chk_preview_dup.Checked = True
        self.chk_preview_dup.CheckedChanged += self.on_preview_option_changed

        self.chk_bake_contours = forms.CheckBox(Text=u"3D 등고선 Bake")
        self.chk_bake_contours.Checked = True

        self.chk_bake_raw = forms.CheckBox(Text=u"원본 도로 경계 Bake")
        self.chk_bake_raw.Checked = False

        self.chk_bake_dup = forms.CheckBox(Text=u"DupBorder 도로 경계 Bake")
        self.chk_bake_dup.Checked = True

        self.chk_bake_surface = forms.CheckBox(Text=u"도로 면 Bake(확인용)")
        self.chk_bake_surface.Checked = False

        self.btn_add_roads = forms.Button(Text=u"도로 Polygon 레이어 추가")
        self.btn_add_roads.Click += self.on_add_roads

        self.btn_extract_border = forms.Button(Text=u"Join 후 DupBorder 추출")
        self.btn_extract_border.Click += self.on_extract_border

        self.btn_clear_border = forms.Button(Text=u"DupBorder 결과 초기화")
        self.btn_clear_border.Click += self.on_clear_border

        self.btn_clear_roads = forms.Button(Text=u"도로 레이어 초기화")
        self.btn_clear_roads.Click += self.on_clear_roads

        self.btn_bake = forms.Button(Text=u"현재 데이터 Bake")
        self.btn_bake.Click += self.on_bake

        self.btn_bake_close = forms.Button(Text=u"Bake 후 닫기")
        self.btn_bake_close.Click += self.on_bake_close

        self.btn_close = forms.Button(Text=u"닫기")
        self.btn_close.Click += self.on_close_button

        self.lbl_status = forms.Label(Text=u"")
        self.lbl_status.Wrap = forms.WrapMode.Word

        layout = forms.DynamicLayout()
        layout.Spacing = drawing.Size(10, 10)
        layout.AddRow(forms.Label(Text=u"01. 등고 높이 필드"), self.cmb_height)
        layout.AddRow(forms.Label(Text=u"02. 허용오차"), self.nud_tol)
        layout.AddRow(forms.Label(Text=u"03. Join 묶음 크기"), self.nud_join_chunk)
        layout.AddRow(self.chk_preview_contours, self.chk_preview_raw, self.chk_preview_dup)
        layout.AddRow(self.chk_bake_contours, self.chk_bake_raw, self.chk_bake_dup, self.chk_bake_surface)
        layout.AddRow(self.btn_add_roads, self.btn_extract_border, self.btn_clear_border, self.btn_clear_roads)
        layout.Add(None)
        layout.AddRow(None, self.btn_bake, self.btn_bake_close, self.btn_close)
        self.form.Content = layout

    def default_height_field_index(self):
        candidates = [u"ELEV", u"EL", u"HEIGHT", u"CONTOUR", u"고도", u"표고", u"등고", u"등고수치"]
        for i, field in enumerate(self.contour_shp.fields):
            f = field.upper()
            for c in candidates:
                if c.upper() in f:
                    return i
        return 0 if self.contour_shp.fields else -1

    def tolerance(self):
        try:
            return float(self.nud_tol.Value)
        except Exception:
            return 0.1

    def join_chunk_size(self):
        try:
            return int(self.nud_join_chunk.Value)
        except Exception:
            return 200

    def rebuild_contours(self):
        if self._rebuilding:
            return
        self._rebuilding = True
        try:
            self.contours = build_contours(self.contour_shp, self.cmb_height.SelectedIndex, self.tolerance())
        finally:
            self._rebuilding = False

    def update_preview(self):
        show_c = bool(self.chk_preview_contours.Checked)
        show_raw = bool(self.chk_preview_raw.Checked)
        show_dup = bool(self.chk_preview_dup.Checked)
        self.conduit.update(self.contours, self.raw_roads, self.dup_borders, show_c, show_raw, show_dup)

    def update_status(self):
        enc = getattr(self.contour_shp, 'encoding', u'?')
        self.lbl_status.Text = u"등고선: {}개 / 원본 도로 경계: {}개 / 도로 면: {}개 / DupBorder 경계: {}개 / 도로 SHP: {}개\nDBF 인코딩: {}\n도로 면 생성 실패 Shape: {}개 / Polygon이 아닌 Shape: {}개 / Join 결과 Brep: {}개\n도로 Z 보간: 비활성화. 현재 단계에서는 도로를 2D 경계로만 불러오고 DupBorder 경계를 추출합니다.".format(
            len(self.contours),
            len(self.raw_roads),
            len(self.road_surfaces),
            len(self.dup_borders),
            len(self.road_paths),
            enc,
            self.failed_surface_shapes,
            self.non_polygon_shapes,
            len(self.joined_surfaces)
        )

    def on_height_field_changed(self, sender, e):
        self.rebuild_contours()
        self.update_preview()
        self.update_status()

    def on_tolerance_changed(self, sender, e):
        self.rebuild_contours()
        # 도로는 이미 읽은 SHP 기반이므로 허용오차 변경 시 자동 재구성하지 않는다.
        # 필요하면 도로 초기화 후 다시 불러오는 방식이 안전하다.
        self.update_preview()
        self.update_status()

    def on_preview_option_changed(self, sender, e):
        self.update_preview()

    def on_add_roads(self, sender, e):
        paths = rs.OpenFileNames(u"도로 Polygon SHP 파일들을 선택하세요", "Shapefiles (*.shp)|*.shp||")
        if not paths:
            return
        if isinstance(paths, str):
            paths = [paths]
        else:
            try:
                paths = list(paths)
            except Exception:
                paths = [paths]

        new_raw, new_surfaces, failed, failed_shapes, non_polygon = build_road_surfaces_from_shp_paths(paths, self.tolerance())
        if not new_raw and not new_surfaces:
            rs.MessageBox(u"선택한 도로 SHP에서 사용할 수 있는 Polygon 경계/면을 읽지 못했습니다.\nZ 보간은 실행하지 않았습니다.")
            return

        self.road_paths.extend(paths)
        self.raw_roads.extend(new_raw)
        self.road_surfaces.extend(new_surfaces)
        self.failed_surface_shapes += failed_shapes
        self.non_polygon_shapes += non_polygon
        self.dup_borders = []
        self.joined_surfaces = []
        self.update_preview()
        self.update_status()

        if failed:
            rs.MessageBox(u"일부 도로 SHP를 읽지 못했습니다.\n\n{}".format(u"\n".join(failed)))

    def on_extract_border(self, sender, e):
        if not self.road_surfaces:
            rs.MessageBox(u"먼저 '도로 Polygon 레이어 추가'로 도로 SHP를 불러오세요.")
            return

        self.lbl_status.Text = u"Join 후 DupBorder 경계 추출 중... 데이터가 많으면 시간이 걸릴 수 있습니다."
        sc.doc.Views.Redraw()

        try:
            self.dup_borders, self.joined_surfaces = extract_dup_borders_from_surfaces(
                self.road_surfaces,
                self.tolerance(),
                self.join_chunk_size()
            )
        except Exception as ex:
            rs.MessageBox(u"Join 후 DupBorder 추출 중 오류가 발생했습니다.\n원본 도로 경계/면 데이터는 유지됩니다.\n\n{}".format(ex))
            self.dup_borders = []
            self.joined_surfaces = []

        self.update_preview()
        self.update_status()

        if not self.dup_borders:
            rs.MessageBox(u"DupBorder 결과가 생성되지 않았습니다.\n도로 Polygon 면 생성 여부와 허용오차를 확인하세요.")

    def on_clear_border(self, sender, e):
        self.dup_borders = []
        self.joined_surfaces = []
        self.update_preview()
        self.update_status()

    def on_clear_roads(self, sender, e):
        self.raw_roads = []
        self.road_surfaces = []
        self.dup_borders = []
        self.joined_surfaces = []
        self.failed_surface_shapes = 0
        self.non_polygon_shapes = 0
        self.road_paths = []
        self.update_preview()
        self.update_status()

    def do_bake(self):
        return bake_all(
            self.contours,
            self.raw_roads,
            self.dup_borders,
            self.road_surfaces,
            bake_c=bool(self.chk_bake_contours.Checked),
            bake_raw=bool(self.chk_bake_raw.Checked),
            bake_dup=bool(self.chk_bake_dup.Checked),
            bake_surf=bool(self.chk_bake_surface.Checked)
        )

    def on_bake(self, sender, e):
        c_count, raw_count, dup_count, surf_count = self.do_bake()
        rs.MessageBox(u"Bake 완료\n\n3D 등고선: {}개\n원본 도로 경계: {}개\nDupBorder 도로 경계: {}개\n도로 면(확인용): {}개".format(c_count, raw_count, dup_count, surf_count))

    def on_bake_close(self, sender, e):
        c_count, raw_count, dup_count, surf_count = self.do_bake()
        rs.MessageBox(u"Bake 완료\n\n3D 등고선: {}개\n원본 도로 경계: {}개\nDupBorder 도로 경계: {}개\n도로 면(확인용): {}개".format(c_count, raw_count, dup_count, surf_count))
        self.close()

    def on_close_button(self, sender, e):
        self.close()

    def cleanup(self):
        if self._closed:
            return
        self._closed = True
        if self.conduit:
            self.conduit.Enabled = False
            self.conduit = None
        try:
            sticky_key = "ContourRoadLayerLoader_Rhino8_v11_Controller"
            if sc.sticky.get(sticky_key) is self:
                del sc.sticky[sticky_key]
        except Exception:
            pass
        sc.doc.Views.Redraw()

    def close(self):
        try:
            self.cleanup()
        finally:
            try:
                self.form.Close()
            except Exception:
                pass

    def on_closed(self, sender, e):
        self.cleanup()

    def show(self):
        try:
            self.form.Show(Rhino.UI.RhinoEtoApp.MainWindow)
        except Exception:
            try:
                self.form.Owner = Rhino.UI.RhinoEtoApp.MainWindow
            except Exception:
                pass
            self.form.Show()
        try:
            self.form.BringToFront()
        except Exception:
            pass


# =============================================================================
# Main
# =============================================================================

def main():
    if shapefile is None:
        return

    contour_path = rs.OpenFileName(u"등고선 SHP 파일을 선택하세요", "Shapefiles (*.shp)|*.shp||")
    if not contour_path:
        return

    contour_shp = read_shp(contour_path)
    if contour_shp is None:
        return

    if not contour_shp.fields:
        rs.MessageBox(u"등고선 SHP의 속성 필드를 읽을 수 없습니다. DBF 파일이 함께 있는지 확인하세요.")
        return

    sticky_key = "ContourRoadLayerLoader_Rhino8_v11_Controller"
    try:
        old = sc.sticky.get(sticky_key)
        if old:
            try:
                old.close()
            except Exception:
                pass
    except Exception:
        pass

    controller = ContourRoadLayerLoaderController(contour_shp)
    sc.sticky[sticky_key] = controller
    controller.show()


if __name__ == "__main__":
    main()
