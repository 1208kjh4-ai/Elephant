# -*- coding: utf-8 -*-
import Rhino
import Rhino.Geometry as rg
import scriptcontext as sc
import rhinoscriptsyntax as rs
import Eto.Forms as forms
import Eto.Drawing as drawing
import System
import math
import os
import json

# ==============================================================================
# [0] Editable Spiral Stair metadata helpers
# ==============================================================================
META_TYPE_KEY = "SS_EDIT_TYPE"
META_TYPE_VAL = "SpiralStair"
META_ID_KEY = "SS_ID"
META_PREFIX = "SS_"


def _bool_to_text(value):
    return "1" if value else "0"


def _text_to_bool(value, default=False):
    if value is None:
        return default
    value = str(value).strip().lower()
    return value in ["1", "true", "yes", "y", "on"]


def _safe_float(value, default=0.0):
    try:
        return float(value)
    except:
        return default


def _safe_int(value, default=0):
    try:
        return int(float(value))
    except:
        return default


def _pt_to_text(pt):
    return "{0},{1},{2}".format(float(pt.X), float(pt.Y), float(pt.Z))


def _vec_to_text(vec):
    return "{0},{1},{2}".format(float(vec.X), float(vec.Y), float(vec.Z))


def _text_to_pt(text):
    vals = str(text).split(",")
    if len(vals) < 3:
        return rg.Point3d.Unset
    return rg.Point3d(_safe_float(vals[0]), _safe_float(vals[1]), _safe_float(vals[2]))


def _text_to_vec(text):
    vals = str(text).split(",")
    if len(vals) < 3:
        return rg.Vector3d.Unset
    return rg.Vector3d(_safe_float(vals[0]), _safe_float(vals[1]), _safe_float(vals[2]))


def _set_user_texts(obj_id, data):
    if not obj_id or obj_id == System.Guid.Empty:
        return
    rs.SetUserText(obj_id, META_TYPE_KEY, META_TYPE_VAL)
    for key, value in data.items():
        rs.SetUserText(obj_id, META_PREFIX + key, str(value))


def _get_user_text(obj_id, key, default=None):
    try:
        val = rs.GetUserText(obj_id, key)
        return default if val is None else val
    except:
        return default


def _load_spiral_data_from_object(obj_id):
    if not obj_id:
        return None
    if _get_user_text(obj_id, META_TYPE_KEY) != META_TYPE_VAL:
        return None

    data = {}
    keys = [
        "id", "center", "z_bottom", "z_top", "total_height", "vec_start", "vec_end", "base_angle",
        "has_pole", "r_inner", "stair_width", "handrail_type", "hr_height", "stair_type", "turn_count", "is_flipped"
    ]
    for key in keys:
        data[key] = _get_user_text(obj_id, META_PREFIX + key)

    if not data.get("id"):
        return None
    return data


def _collect_spiral_object_ids(spiral_id):
    result = []
    try:
        all_ids = rs.AllObjects()
    except:
        all_ids = []

    if not all_ids:
        return result

    for obj_id in all_ids:
        if _get_user_text(obj_id, META_TYPE_KEY) == META_TYPE_VAL:
            if _get_user_text(obj_id, META_PREFIX + "id") == spiral_id:
                result.append(obj_id)
    return result


def _delete_objects_safe(obj_ids):
    if not obj_ids:
        return
    valid_ids = []
    for obj_id in obj_ids:
        if obj_id and rs.IsObject(obj_id):
            valid_ids.append(obj_id)
    if valid_ids:
        rs.DeleteObjects(valid_ids)


# ==============================================================================
# [0-1] Preset / linked edit / transform helpers
# ==============================================================================
def _get_appdata_dir():
    root = os.environ.get("APPDATA") or os.path.expanduser("~")
    folder = os.path.join(root, "ElephantTools")
    if not os.path.exists(folder):
        try:
            os.makedirs(folder)
        except:
            pass
    return folder


def _get_preset_path():
    return os.path.join(_get_appdata_dir(), "SpiralStairPresets.json")


def _load_presets():
    path = _get_preset_path()
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception as ex:
        print("프리셋 로드 오류:", ex)
        return {}


def _save_presets(presets):
    path = _get_preset_path()
    try:
        with open(path, "w") as f:
            json.dump(presets, f, indent=2, sort_keys=True)
        return True
    except Exception as ex:
        print("프리셋 저장 오류:", ex)
        return False


def _clamp_index(value, min_value, max_value, default_value):
    idx = _safe_int(value, default_value)
    if idx < min_value: idx = min_value
    if idx > max_value: idx = max_value
    return idx


def _duplicate_brep(brep):
    try:
        return brep.DuplicateBrep()
    except:
        try:
            return brep.Duplicate()
        except:
            return None


def _duplicate_curve(curve):
    try:
        return curve.DuplicateCurve()
    except:
        try:
            return curve.Duplicate()
        except:
            return None


def _geometry_from_object(obj_id):
    try:
        brep = rs.coercebrep(obj_id)
        if brep:
            return "brep", brep
    except:
        pass
    try:
        curve = rs.coercecurve(obj_id)
        if curve:
            return "curve", curve
    except:
        pass
    return None, None


def _generate_reference_parts(engine, settings):
    if engine is None or settings is None:
        return []
    stair_b, hr_b, hr_c = engine.calculate_geometry(
        has_pole=bool(settings.get("has_pole", True)),
        r_inner=float(settings.get("r_inner", 150.0)),
        stair_width=float(settings.get("stair_width", 1200.0)),
        handrail_type=_safe_int(settings.get("handrail_type", 3), 3),
        hr_height=float(settings.get("hr_height", 1500.0)),
        stair_type=_safe_int(settings.get("stair_type", 0), 0),
        turn_count=_safe_int(settings.get("turn_count", 0), 0),
        is_flipped=bool(settings.get("is_flipped", False))
    )
    parts = []
    for b in stair_b:
        if b and b.IsValid: parts.append(("stair_brep", "brep", b))
    for b in hr_b:
        if b and b.IsValid: parts.append(("handrail_brep", "brep", b))
    for c in hr_c:
        if c and c.IsValid: parts.append(("handrail_curve", "curve", c))
    return parts


def _find_non_collinear_brep_indices(brep):
    try:
        pts = [v.Location for v in brep.Vertices]
    except:
        return None
    n = len(pts)
    if n < 3:
        return None
    for i in range(n):
        for j in range(i + 1, n):
            v1 = pts[j] - pts[i]
            if v1.Length < 1e-6:
                continue
            for k in range(j + 1, n):
                v2 = pts[k] - pts[i]
                if v2.Length < 1e-6:
                    continue
                cross = rg.Vector3d.CrossProduct(v1, v2)
                if cross.Length > 1e-6:
                    return i, j, k
    return None


def _brep_vertex_match_error(ref_brep, cur_brep, xform):
    try:
        if ref_brep.Vertices.Count != cur_brep.Vertices.Count:
            return None
        n = ref_brep.Vertices.Count
        if n == 0:
            return None
        max_dist = 0.0
        total = 0.0
        for i in range(n):
            p = rg.Point3d(ref_brep.Vertices[i].Location)
            p.Transform(xform)
            q = cur_brep.Vertices[i].Location
            d = p.DistanceTo(q)
            if d > max_dist: max_dist = d
            total += d
        return max_dist + (total / float(n))
    except:
        return None


def _compute_brep_xform(ref_brep, cur_brep):
    try:
        if not ref_brep or not cur_brep:
            return None, None
        if ref_brep.Vertices.Count != cur_brep.Vertices.Count or ref_brep.Vertices.Count < 3:
            return None, None
        idx = _find_non_collinear_brep_indices(ref_brep)
        if not idx:
            return None, None
        i, j, k = idx
        ref_plane = rg.Plane(ref_brep.Vertices[i].Location, ref_brep.Vertices[j].Location, ref_brep.Vertices[k].Location)
        cur_plane = rg.Plane(cur_brep.Vertices[i].Location, cur_brep.Vertices[j].Location, cur_brep.Vertices[k].Location)
        if not ref_plane.IsValid or not cur_plane.IsValid:
            return None, None
        xform = rg.Transform.PlaneToPlane(ref_plane, cur_plane)
        err = _brep_vertex_match_error(ref_brep, cur_brep, xform)
        if err is None:
            return None, None
        tol = max(sc.doc.ModelAbsoluteTolerance * 20.0, 1.0)
        if err <= tol:
            return xform, err
        return None, err
    except:
        return None, None


def _curve_sample_points(curve, count=7):
    pts = []
    try:
        dom = curve.Domain
        for i in range(count):
            t = dom.T0 + (dom.T1 - dom.T0) * (i / float(count - 1))
            pts.append(curve.PointAt(t))
    except:
        pass
    return pts


def _curve_error(ref_curve, cur_curve, xform):
    ref_pts = _curve_sample_points(ref_curve, 9)
    cur_pts = _curve_sample_points(cur_curve, 9)
    if len(ref_pts) != len(cur_pts) or not ref_pts:
        return None
    max_dist = 0.0
    total = 0.0
    for p, q in zip(ref_pts, cur_pts):
        pp = rg.Point3d(p)
        pp.Transform(xform)
        d = pp.DistanceTo(q)
        if d > max_dist: max_dist = d
        total += d
    return max_dist + (total / float(len(ref_pts)))


def _compute_curve_xform(ref_curve, cur_curve):
    try:
        ref_pts = _curve_sample_points(ref_curve, 5)
        cur_pts = _curve_sample_points(cur_curve, 5)
        if len(ref_pts) < 3 or len(cur_pts) < 3:
            return None, None
        # Prefer start, mid, end. If nearly collinear, try other samples.
        candidate_indices = [(0, 2, 4), (0, 1, 3), (1, 2, 4)]
        best = None
        for i, j, k in candidate_indices:
            ref_plane = rg.Plane(ref_pts[i], ref_pts[j], ref_pts[k])
            cur_plane = rg.Plane(cur_pts[i], cur_pts[j], cur_pts[k])
            if not ref_plane.IsValid or not cur_plane.IsValid:
                continue
            xform = rg.Transform.PlaneToPlane(ref_plane, cur_plane)
            err = _curve_error(ref_curve, cur_curve, xform)
            if err is None:
                continue
            if best is None or err < best[1]:
                best = (xform, err)
        if best is None:
            return None, None
        tol = max(sc.doc.ModelAbsoluteTolerance * 50.0, 5.0)
        if best[1] <= tol:
            return best[0], best[1]
        return None, best[1]
    except:
        return None, None


def _find_xform_from_parts_to_object(reference_parts, obj_id):
    geom_type, geom = _geometry_from_object(obj_id)
    if not geom_type or not geom:
        return None
    best = None
    for name, ref_type, ref_geom in reference_parts:
        if geom_type != ref_type:
            continue
        if geom_type == "brep":
            xform, err = _compute_brep_xform(ref_geom, geom)
        else:
            xform, err = _compute_curve_xform(ref_geom, geom)
        if xform is not None and err is not None:
            if best is None or err < best[1]:
                best = (xform, err)
    return best[0] if best else None


def _transform_parts(parts, xform):
    transformed = []
    for name, geom_type, geom in parts:
        if geom_type == "brep":
            dup = _duplicate_brep(geom)
        else:
            dup = _duplicate_curve(geom)
        if dup:
            dup.Transform(xform)
            transformed.append((name, geom_type, dup))
    return transformed


def _get_object_group_keys(obj_id):
    try:
        groups = rs.ObjectGroups(obj_id)
        if groups:
            return list(groups)
    except:
        pass
    return []


def _collect_spiral_sets_by_group(spiral_id):
    all_ids = _collect_spiral_object_ids(spiral_id)
    grouped = {}
    no_group = []
    for obj_id in all_ids:
        groups = _get_object_group_keys(obj_id)
        if groups:
            key = groups[0]
            if key not in grouped:
                grouped[key] = []
            grouped[key].append(obj_id)
        else:
            no_group.append(obj_id)

    sets = []
    for key in sorted(grouped.keys()):
        sets.append({"key": key, "object_ids": grouped[key]})
    if no_group:
        # Fallback: ungrouped linked objects cannot be reliably split, so keep them together.
        sets.append({"key": "__ungrouped__", "object_ids": no_group})
    return sets


def _get_selected_set_key(selected_id):
    groups = _get_object_group_keys(selected_id)
    if groups:
        return groups[0]
    return "__ungrouped__"


def _make_identity_transform():
    return rg.Transform.Identity

# --- [1] 실시간 화면 표시 엔진 ---
class SpiralStairPreviewConduit(Rhino.Display.DisplayConduit):
    def __init__(self):
        super(SpiralStairPreviewConduit, self).__init__()
        self.preview_breps = []
        self.preview_curves = []
        self.mat_solid = Rhino.Display.DisplayMaterial(System.Drawing.Color.LightGray)
        self.wire_color = System.Drawing.Color.DarkGray

    def UpdateGeometry(self, breps, curves):
        self.preview_breps = breps
        self.preview_curves = curves

    def CalculateBoundingBox(self, e):
        if not self.preview_breps and not self.preview_curves:
            return
        bbox = rg.BoundingBox.Empty
        for b in self.preview_breps:
            if b and b.IsValid: bbox.Union(b.GetBoundingBox(True))
        for c in self.preview_curves:
            if c and c.IsValid: bbox.Union(c.GetBoundingBox(True))
        e.IncludeInBoundingBox(bbox)

    def PostDrawObjects(self, e):
        if self.preview_breps:
            for b in self.preview_breps:
                if b and b.IsValid:
                    e.Display.DrawBrepShaded(b, self.mat_solid)
                    e.Display.DrawBrepWires(b, self.wire_color, 1)
        if self.preview_curves:
            for c in self.preview_curves:
                if c and c.IsValid:
                    e.Display.DrawCurve(c, System.Drawing.Color.Red, 2)


# --- [2] 지오메트리 계산 엔진 ---
class SpiralStairEngine:
    def __init__(self, crv1=None, crv2=None):
        self.crv1 = crv1
        self.crv2 = crv2
        self.doc = Rhino.RhinoDoc.ActiveDoc
        self.tol = self.doc.ModelAbsoluteTolerance
        
        self.center_pt = None
        self.z_bottom = 0.0
        self.z_top = 0.0
        self.total_height = 0.0
        self.vec_start = None
        self.vec_end = None
        self.base_angle = 0.0
        
        if self.crv1 is not None and self.crv2 is not None:
            self.analyze_inputs()

    @classmethod
    def FromSavedData(cls, data):
        engine = cls(None, None)
        engine.center_pt = _text_to_pt(data.get("center"))
        engine.z_bottom = _safe_float(data.get("z_bottom"), 0.0)
        engine.z_top = _safe_float(data.get("z_top"), 0.0)
        engine.total_height = _safe_float(data.get("total_height"), abs(engine.z_top - engine.z_bottom))
        engine.vec_start = _text_to_vec(data.get("vec_start"))
        engine.vec_end = _text_to_vec(data.get("vec_end"))
        if engine.vec_start and engine.vec_start.IsValid and engine.vec_start.Length > 0:
            engine.vec_start.Unitize()
        if engine.vec_end and engine.vec_end.IsValid and engine.vec_end.Length > 0:
            engine.vec_end.Unitize()
        engine.base_angle = _safe_float(data.get("base_angle"), 0.0)
        if engine.center_pt == rg.Point3d.Unset or not engine.vec_start or not engine.vec_end:
            engine.center_pt = None
        return engine

    def ToSavedData(self):
        return {
            "center": _pt_to_text(self.center_pt),
            "z_bottom": self.z_bottom,
            "z_top": self.z_top,
            "total_height": self.total_height,
            "vec_start": _vec_to_text(self.vec_start),
            "vec_end": _vec_to_text(self.vec_end),
            "base_angle": self.base_angle
        }

    def Transformed(self, xform):
        """Return a new engine transformed by a copy/move/rotation xform.
        The generator assumes a vertical world-Z stair. This supports normal CAD use cases:
        move, copy, and rotate in plan, plus vertical translation.
        """
        engine = SpiralStairEngine(None, None)
        if self.center_pt is None:
            return engine

        center_xy = rg.Point3d(self.center_pt.X, self.center_pt.Y, 0.0)
        bottom_pt = rg.Point3d(self.center_pt.X, self.center_pt.Y, self.z_bottom)
        top_pt = rg.Point3d(self.center_pt.X, self.center_pt.Y, self.z_top)
        center_xy.Transform(xform)
        bottom_pt.Transform(xform)
        top_pt.Transform(xform)

        engine.center_pt = rg.Point3d(center_xy.X, center_xy.Y, 0.0)
        engine.z_bottom = bottom_pt.Z
        engine.z_top = top_pt.Z
        engine.total_height = abs(engine.z_top - engine.z_bottom)

        v_start = rg.Vector3d(self.vec_start)
        v_end = rg.Vector3d(self.vec_end)
        v_start.Transform(xform)
        v_end.Transform(xform)
        v_start.Z = 0.0
        v_end.Z = 0.0
        if v_start.Length > 1e-9: v_start.Unitize()
        if v_end.Length > 1e-9: v_end.Unitize()
        engine.vec_start = v_start
        engine.vec_end = v_end
        engine.base_angle = rg.Vector3d.VectorAngle(engine.vec_start, engine.vec_end, rg.Plane.WorldXY)
        return engine

    def analyze_inputs(self):
        p1_start = rg.Point3d(self.crv1.PointAtStart.X, self.crv1.PointAtStart.Y, 0)
        p1_end = rg.Point3d(self.crv1.PointAtEnd.X, self.crv1.PointAtEnd.Y, 0)
        line1 = rg.Line(p1_start, p1_end)

        p2_start = rg.Point3d(self.crv2.PointAtStart.X, self.crv2.PointAtStart.Y, 0)
        p2_end = rg.Point3d(self.crv2.PointAtEnd.X, self.crv2.PointAtEnd.Y, 0)
        line2 = rg.Line(p2_start, p2_end)

        success, a, b = Rhino.Geometry.Intersect.Intersection.LineLine(line1, line2)
        if success:
            self.center_pt = line1.PointAt(a)
        else:
            manual_pt = rs.GetPoint("두 커브가 평행합니다. 원형 계단의 중심점을 직접 클릭하세요")
            if manual_pt:
                self.center_pt = rg.Point3d(manual_pt.X, manual_pt.Y, 0)
            else:
                self.center_pt = None
                return

        z1 = (self.crv1.PointAtStart.Z + self.crv1.PointAtEnd.Z) / 2.0
        z2 = (self.crv2.PointAtStart.Z + self.crv2.PointAtEnd.Z) / 2.0
        
        if z1 <= z2:
            self.z_bottom, self.z_top = z1, z2
            bottom_crv, top_crv = self.crv1, self.crv2
        else:
            self.z_bottom, self.z_top = z2, z1
            bottom_crv, top_crv = self.crv2, self.crv1
            
        self.total_height = abs(self.z_top - self.z_bottom)

        pt_b_mid = rg.Point3d(bottom_crv.Domain.Mid, 0, 0)
        success_b, pt_b = bottom_crv.LengthParameter(bottom_crv.GetLength()/2)
        if success_b: pt_b_mid = rg.Point3d(bottom_crv.PointAt(pt_b).X, bottom_crv.PointAt(pt_b).Y, 0)
        
        pt_t_mid = rg.Point3d(top_crv.Domain.Mid, 0, 0)
        success_t, pt_t = top_crv.LengthParameter(top_crv.GetLength()/2)
        if success_t: pt_t_mid = rg.Point3d(top_crv.PointAt(pt_t).X, top_crv.PointAt(pt_t).Y, 0)

        self.vec_start = pt_b_mid - self.center_pt
        self.vec_end = pt_t_mid - self.center_pt
        
        self.vec_start.Unitize()
        self.vec_end.Unitize()

        self.base_angle = rg.Vector3d.VectorAngle(self.vec_start, self.vec_end, rg.Plane.WorldXY)

    def calculate_geometry(self, has_pole, r_inner, stair_width, handrail_type, hr_height, stair_type, turn_count, is_flipped):
        stair_breps = []
        hr_breps = []
        hr_curves = []
        
        r_outer = r_inner + stair_width 
        
        if self.center_pt is None or self.total_height < 1.0:
            return stair_breps, hr_breps, hr_curves

        total_angle = self.base_angle
        if is_flipped:
            if self.base_angle > 0.001: 
                total_angle = (2 * math.pi) - self.base_angle
            else:
                total_angle = 2 * math.pi
        
        total_angle += (turn_count * 2 * math.pi)
        
        rot_axis = rg.Vector3d.ZAxis if not is_flipped else -rg.Vector3d.ZAxis
        y_axis = rg.Vector3d.CrossProduct(rot_axis, self.vec_start)
        y_axis.Unitize()
        
        step_count = int(math.ceil(self.total_height / 175.0))
        if step_count < 1: step_count = 1
        actual_riser = self.total_height / step_count
        angle_per_step = total_angle / step_count

        # 1. Center Pole 생성
        if has_pole:
            pole_circle = rg.Circle(rg.Plane(self.center_pt + rg.Vector3d(0,0,self.z_bottom), rg.Vector3d.ZAxis), r_inner)
            pole_cyl = rg.Cylinder(pole_circle, self.total_height + (1000 if handrail_type > 0 else 0))
            if pole_cyl: stair_breps.append(pole_cyl.ToBrep(True, True))

        # 2. 계단(Step) 본체 생성
        step_thickness = actual_riser if stair_type == 0 else 30.0 
        
        pts_top_inner = []
        pts_top_outer = []
        pts_bottom_inner = []
        pts_bottom_outer = []

        for i in range(step_count):
            z_current = self.z_bottom + (i * actual_riser)
            tread_z = z_current + actual_riser 
            
            angle_current = i * angle_per_step
            sweep_angle = angle_per_step + 0.01

            tread_origin = self.center_pt + rg.Vector3d(0, 0, tread_z)
            tread_plane = rg.Plane(tread_origin, self.vec_start, y_axis)
            tread_plane.Rotate(angle_current, tread_plane.ZAxis, tread_plane.Origin)

            arc_inner = rg.Arc(tread_plane, r_inner, sweep_angle)
            arc_outer = rg.Arc(tread_plane, r_outer, sweep_angle)
            c_inner = rg.ArcCurve(arc_inner)
            c_outer = rg.ArcCurve(arc_outer)
            c_outer.Reverse()
            
            l1 = rg.Line(c_inner.PointAtEnd, c_outer.PointAtStart).ToNurbsCurve()
            l2 = rg.Line(c_outer.PointAtEnd, c_inner.PointAtStart).ToNurbsCurve()
            
            joined_crvs = rg.Curve.JoinCurves([c_inner, l1, c_outer, l2])
            if joined_crvs:
                step_crv = joined_crvs[0]
                extrusion = rg.Surface.CreateExtrusion(step_crv, rg.Vector3d(0,0, -step_thickness))
                if extrusion: 
                    ext_brep = extrusion.ToBrep()
                    capped = ext_brep.CapPlanarHoles(self.tol)
                    stair_breps.append(capped if capped else ext_brep)
                
            if stair_type == 0:
                base_origin = self.center_pt + rg.Vector3d(0, 0, z_current)
                base_plane = rg.Plane(base_origin, self.vec_start, y_axis)
                base_plane.Rotate(angle_current, base_plane.ZAxis, base_plane.Origin)
                
                pt_in = base_plane.Origin + (base_plane.XAxis * r_inner)
                pt_out = base_plane.Origin + (base_plane.XAxis * r_outer)
                
                slab_thickness = (actual_riser) + 50.0 
                
                pts_top_inner.append(pt_in)
                pts_top_outer.append(pt_out)
                pts_bottom_inner.append(pt_in - rg.Vector3d(0, 0, slab_thickness))
                pts_bottom_outer.append(pt_out - rg.Vector3d(0, 0, slab_thickness))
                
                if i == step_count - 1:
                    end_plane = rg.Plane(base_origin + rg.Vector3d(0,0,actual_riser), self.vec_start, y_axis)
                    end_plane.Rotate(angle_current + angle_per_step, end_plane.ZAxis, end_plane.Origin)
                    pt_in_end = end_plane.Origin + (end_plane.XAxis * r_inner)
                    pt_out_end = end_plane.Origin + (end_plane.XAxis * r_outer)
                    
                    pts_top_inner.append(pt_in_end)
                    pts_top_outer.append(pt_out_end)
                    pts_bottom_inner.append(pt_in_end - rg.Vector3d(0, 0, slab_thickness))
                    pts_bottom_outer.append(pt_out_end - rg.Vector3d(0, 0, slab_thickness))

        if stair_type == 0 and len(pts_bottom_inner) > 2:
            crv_btm_in = rg.Curve.CreateInterpolatedCurve(pts_bottom_inner, 3)
            crv_btm_out = rg.Curve.CreateInterpolatedCurve(pts_bottom_outer, 3)
            crv_top_in = rg.Curve.CreateInterpolatedCurve(pts_top_inner, 3)
            crv_top_out = rg.Curve.CreateInterpolatedCurve(pts_top_outer, 3)
            
            if crv_btm_in and crv_btm_out and crv_top_in and crv_top_out:
                srf_bottom = rg.Brep.CreateFromLoft([crv_btm_in, crv_btm_out], rg.Point3d.Unset, rg.Point3d.Unset, rg.LoftType.Normal, False)
                srf_top = rg.Brep.CreateFromLoft([crv_top_in, crv_top_out], rg.Point3d.Unset, rg.Point3d.Unset, rg.LoftType.Normal, False)
                srf_inner = rg.Brep.CreateFromLoft([crv_btm_in, crv_top_in], rg.Point3d.Unset, rg.Point3d.Unset, rg.LoftType.Normal, False)
                srf_outer = rg.Brep.CreateFromLoft([crv_btm_out, crv_top_out], rg.Point3d.Unset, rg.Point3d.Unset, rg.LoftType.Normal, False)
                
                parts = []
                if srf_bottom: parts.append(srf_bottom[0])
                if srf_top: parts.append(srf_top[0])
                if srf_inner: parts.append(srf_inner[0])
                if srf_outer: parts.append(srf_outer[0])
                
                if parts:
                    joined_base = rg.Brep.JoinBreps(parts, self.tol)
                    if joined_base:
                        for b in joined_base:
                            capped = b.CapPlanarHoles(self.tol)
                            stair_breps.append(capped if capped else b)

        # 3. 난간(Handrail) / 스트링거(Stringer) 생성
        if handrail_type > 0:
            
            # --- [솔리드 난간 제어 변수 (Type 2)] ---
            hr_height_top = hr_height  
            hr_height_btm = -(actual_riser+100)    
            hr_thickness = 50.0        
            
            # --- [ㄷ형강 스트링거 제어 변수 (Type 3)] ---
            str_H = actual_riser*2.0        
            str_B = 120.0        
            str_t = 30.0         
            str_Z_offset = (actual_riser*0.5)-50   
            
            pts_spiral_in_base = []
            pts_spiral_out_base = []
            
            pts_spiral_in_str_top = []
            pts_spiral_out_str_top = []
            
            profiles_hr_in = []
            profiles_hr_out = []
            profiles_str_in = []
            profiles_str_out = []
            
            def get_c_profile(origin, v_u, v_f, h, b, t_val):
                pt0 = origin + v_u * (h/2.0)
                pt1 = pt0 + v_f * b
                pt2 = pt1 - v_u * t_val
                pt3 = origin + v_u * (h/2.0 - t_val) + v_f * t_val
                pt4 = origin - v_u * (h/2.0 - t_val) + v_f * t_val
                pt5 = origin - v_u * (h/2.0) + v_f * b + v_u * t_val
                pt6 = origin - v_u * (h/2.0) + v_f * b
                pt7 = origin - v_u * (h/2.0)
                return rg.Polyline([pt0, pt1, pt2, pt3, pt4, pt5, pt6, pt7, pt0]).ToNurbsCurve()

            div_count = step_count * 4
            for i in range(div_count + 1):
                t = i / float(div_count)
                curr_angle = t * total_angle
                curr_z_base = self.z_bottom + (t * self.total_height)
                
                vec_rot = rg.Vector3d(self.vec_start) 
                vec_rot.Rotate(curr_angle, rot_axis)
                
                pt_in_base = self.center_pt + (vec_rot * r_inner) + rg.Vector3d(0,0,curr_z_base)
                pt_out_base = self.center_pt + (vec_rot * r_outer) + rg.Vector3d(0,0,curr_z_base)
                
                pts_spiral_in_base.append(pt_in_base)
                pts_spiral_out_base.append(pt_out_base)
                
                # [Type 2] 솔리드 난간 프로파일
                if handrail_type == 2:
                    p_in_btm = pt_in_base + rg.Vector3d(0,0, hr_height_btm)
                    p_in_top = pt_in_base + rg.Vector3d(0,0, hr_height_top)
                    p_in_off_top = self.center_pt + (vec_rot * (r_inner - hr_thickness)) + rg.Vector3d(0,0,curr_z_base + hr_height_top)
                    p_in_off_btm = self.center_pt + (vec_rot * (r_inner - hr_thickness)) + rg.Vector3d(0,0,curr_z_base + hr_height_btm)
                    poly_in = rg.Polyline([p_in_btm, p_in_top, p_in_off_top, p_in_off_btm, p_in_btm])
                    profiles_hr_in.append(poly_in.ToNurbsCurve())
                    
                    p_out_btm = pt_out_base + rg.Vector3d(0,0, hr_height_btm)
                    p_out_top = pt_out_base + rg.Vector3d(0,0, hr_height_top)
                    p_out_off_top = self.center_pt + (vec_rot * (r_outer + hr_thickness)) + rg.Vector3d(0,0,curr_z_base + hr_height_top)
                    p_out_off_btm = self.center_pt + (vec_rot * (r_outer + hr_thickness)) + rg.Vector3d(0,0,curr_z_base + hr_height_btm)
                    poly_out = rg.Polyline([p_out_btm, p_out_top, p_out_off_top, p_out_off_btm, p_out_btm])
                    profiles_hr_out.append(poly_out.ToNurbsCurve())

                # [Type 3] ㄷ형강 스트링거 프로파일
                if handrail_type == 3:
                    str_origin_in = pt_in_base + rg.Vector3d(0, 0, str_Z_offset)
                    str_origin_out = pt_out_base + rg.Vector3d(0, 0, str_Z_offset)
                    
                    v_up = rg.Vector3d.ZAxis
                    v_flange_out = vec_rot             
                    v_flange_in = -vec_rot             
                    
                    profiles_str_in.append(get_c_profile(str_origin_in, v_up, v_flange_in, str_H, str_B, str_t))
                    profiles_str_out.append(get_c_profile(str_origin_out, v_up, v_flange_out, str_H, str_B, str_t))
                    
                    pt_in_guide = str_origin_in + rg.Vector3d(0,0, str_H/2.0) + v_flange_in * (str_B * 0.5)
                    pt_out_guide = str_origin_out + rg.Vector3d(0,0, str_H/2.0) + v_flange_out * (str_B * 0.5)
                    
                    pts_spiral_in_str_top.append(pt_in_guide)
                    pts_spiral_out_str_top.append(pt_out_guide)

            if handrail_type == 1:
                crv_in = rg.Curve.CreateInterpolatedCurve(pts_spiral_in_base, 3)
                crv_out = rg.Curve.CreateInterpolatedCurve(pts_spiral_out_base, 3)
                if crv_in: hr_curves.append(crv_in)
                if crv_out: hr_curves.append(crv_out)
                
            elif handrail_type == 2:
                loft_in = rg.Brep.CreateFromLoft(profiles_hr_in, rg.Point3d.Unset, rg.Point3d.Unset, rg.LoftType.Normal, False)
                if loft_in:
                    capped_in = loft_in[0].CapPlanarHoles(self.tol)
                    hr_breps.append(capped_in if capped_in else loft_in[0])
                    
                loft_out = rg.Brep.CreateFromLoft(profiles_hr_out, rg.Point3d.Unset, rg.Point3d.Unset, rg.LoftType.Normal, False)
                if loft_out:
                    capped_out = loft_out[0].CapPlanarHoles(self.tol)
                    hr_breps.append(capped_out if capped_out else loft_out[0])

            elif handrail_type == 3:
                loft_str_in = rg.Brep.CreateFromLoft(profiles_str_in, rg.Point3d.Unset, rg.Point3d.Unset, rg.LoftType.Normal, False)
                if loft_str_in:
                    capped_in = loft_str_in[0].CapPlanarHoles(self.tol)
                    hr_breps.append(capped_in if capped_in else loft_str_in[0])
                    
                loft_str_out = rg.Brep.CreateFromLoft(profiles_str_out, rg.Point3d.Unset, rg.Point3d.Unset, rg.LoftType.Normal, False)
                if loft_str_out:
                    capped_out = loft_str_out[0].CapPlanarHoles(self.tol)
                    hr_breps.append(capped_out if capped_out else loft_str_out[0])
                    
                crv_in_top = rg.Curve.CreateInterpolatedCurve(pts_spiral_in_str_top, 3)
                crv_out_top = rg.Curve.CreateInterpolatedCurve(pts_spiral_out_str_top, 3)
                if crv_in_top: hr_curves.append(crv_in_top)
                if crv_out_top: hr_curves.append(crv_out_top)

        return stair_breps, hr_breps, hr_curves


# --- [3] 실시간 제어 창 (Eto Modeless Form) ---
class SpiralStairDialog(forms.Form):
    def __init__(self):
        super(SpiralStairDialog, self).__init__()
        self.engine = None
        self.conduit = SpiralStairPreviewConduit()
        self.initial_settings = {}
        self.edit_id = None
        self.edit_sets = []
        self.selected_set = None
        self._closing_preview = False

        self.Title = "원형 계단 생성기"
        self.Padding = drawing.Padding(12)
        self.Resizable = True
        self.Topmost = True
        self.ClientSize = drawing.Size(360, 520)

        self.presets = _load_presets()

        def_pole = self.initial_settings.get("has_pole", sc.sticky.get("SP_Pole", True))
        def_r_inner = self.initial_settings.get("r_inner", sc.sticky.get("SP_RInner", 150))
        def_width = self.initial_settings.get("stair_width", sc.sticky.get("SP_Width", 1200))
        def_type = self.initial_settings.get("stair_type", sc.sticky.get("SP_Type", 0))
        def_handrail = self.initial_settings.get("handrail_type", sc.sticky.get("SP_Handrail", 3))
        def_hr_height = self.initial_settings.get("hr_height", sc.sticky.get("SP_HrHeight", 1500))
        def_turns = self.initial_settings.get("turn_count", sc.sticky.get("SP_Turns", 0))
        def_flip = self.initial_settings.get("is_flipped", sc.sticky.get("SP_Flip", False))

        self.chk_pole = forms.CheckBox(Text="중심 기둥 생성", Checked=bool(def_pole))
        self.nud_r_inner = forms.NumericStepper(Value=float(def_r_inner), DecimalPlaces=0, Increment=50, MinValue=0, MaxValue=99999)
        self.nud_width = forms.NumericStepper(Value=float(def_width), DecimalPlaces=0, Increment=100, MinValue=300, MaxValue=99999)

        self.cb_stair_type = forms.DropDown()
        self.cb_stair_type.DataStore = ["01. 솔리드 계단", "02. 계단 발판만"]
        self.cb_stair_type.SelectedIndex = _clamp_index(def_type, 0, 1, 0)

        self.cb_handrail = forms.DropDown()
        self.cb_handrail.DataStore = ["없음", "가이드 라인", "솔리드 난간", "03. 철골"]
        self.cb_handrail.SelectedIndex = _clamp_index(def_handrail, 0, 3, 3)

        self.nud_hr_height = forms.NumericStepper(Value=float(def_hr_height), DecimalPlaces=0, Increment=50, MinValue=300, MaxValue=3000)
        self.nud_turns = forms.NumericStepper(Value=int(def_turns), DecimalPlaces=0, Increment=1, MinValue=0, MaxValue=10)
        self.chk_flip = forms.CheckBox(Text="회전 방향 뒤집기 (Flip)", Checked=bool(def_flip))

        self.chk_update_linked = forms.CheckBox(Text="같은 ID 복사본도 함께 수정", Checked=True)
        self.chk_update_linked.Enabled = False
        self.lbl_linked_info = forms.Label(Text="")

        self.dd_preset = forms.DropDown()
        self.txt_preset_name = forms.TextBox()
        self.txt_preset_name.Width = 120
        self.btn_preset_load = forms.Button(Text="불러오기")
        self.btn_preset_save = forms.Button(Text="저장")
        self.btn_preset_delete = forms.Button(Text="삭제")

        self.btn_create = forms.Button(Text="생성")
        self.btn_cancel = forms.Button(Text="취소")

        self.chk_pole.CheckedChanged += self.RefreshPreview
        self.nud_r_inner.ValueChanged += self.RefreshPreview
        self.nud_width.ValueChanged += self.RefreshPreview
        self.cb_stair_type.SelectedIndexChanged += self.RefreshPreview
        self.cb_handrail.SelectedIndexChanged += self.RefreshPreview
        self.nud_hr_height.ValueChanged += self.RefreshPreview
        self.nud_turns.ValueChanged += self.RefreshPreview
        self.chk_flip.CheckedChanged += self.RefreshPreview

        self.btn_preset_load.Click += self.OnPresetLoad
        self.btn_preset_save.Click += self.OnPresetSave
        self.btn_preset_delete.Click += self.OnPresetDelete
        self.dd_preset.SelectedIndexChanged += self.OnPresetSelectionChanged

        self.btn_create.Click += self.OnCreateClick
        self.btn_cancel.Click += self.OnCancelClick
        self.Closed += self.OnFormClosed

        layout = forms.DynamicLayout()
        layout.Spacing = drawing.Size(8, 8)

        preset_layout = forms.DynamicLayout(DefaultSpacing=drawing.Size(5, 5))
        preset_layout.AddRow(forms.Label(Text="프리셋:"), self.dd_preset, self.btn_preset_load)
        preset_layout.AddRow(forms.Label(Text="프리셋 이름:"), self.txt_preset_name, self.btn_preset_save, self.btn_preset_delete)
        layout.AddRow(preset_layout)
        layout.AddRow(None)

        layout.AddRow(self.chk_pole)
        layout.AddRow(forms.Label(Text="내부 반지름:"), self.nud_r_inner)
        layout.AddRow(forms.Label(Text="계단 폭:"), self.nud_width)
        layout.AddRow(None)
        layout.AddRow(forms.Label(Text="구조 타입:"), self.cb_stair_type)
        layout.AddRow(None)
        layout.AddRow(forms.Label(Text="난간 타입:"), self.cb_handrail)
        layout.AddRow(forms.Label(Text="난간 높이:"), self.nud_hr_height)
        layout.AddRow(None)
        layout.AddRow(forms.Label(Text="돌음 횟수 추가:"), self.nud_turns)
        layout.AddRow(self.chk_flip)
        layout.AddRow(None)
        layout.AddRow(self.chk_update_linked)
        layout.AddRow(self.lbl_linked_info)
        layout.AddRow(None)
        layout.AddRow(self.btn_create, self.btn_cancel)

        self.Content = layout
        self.RefreshPresetDropdown()

    def RefreshPresetDropdown(self):
        names = sorted(self.presets.keys())
        self.dd_preset.DataStore = names
        if names:
            self.dd_preset.SelectedIndex = 0
        else:
            self.dd_preset.SelectedIndex = -1

    def _selected_preset_name(self):
        try:
            idx = self.dd_preset.SelectedIndex
            names = sorted(self.presets.keys())
            if idx >= 0 and idx < len(names):
                return names[idx]
        except:
            pass
        return None

    def OnPresetSelectionChanged(self, sender, e):
        name = self._selected_preset_name()
        if name:
            self.txt_preset_name.Text = name

    def ApplySettingsToUI(self, settings):
        if not settings:
            return
        self.chk_pole.Checked = bool(settings.get("has_pole", self.chk_pole.Checked))
        self.nud_r_inner.Value = float(settings.get("r_inner", self.nud_r_inner.Value))
        self.nud_width.Value = float(settings.get("stair_width", self.nud_width.Value))
        self.cb_stair_type.SelectedIndex = _clamp_index(settings.get("stair_type", self.cb_stair_type.SelectedIndex), 0, 1, self.cb_stair_type.SelectedIndex)
        self.cb_handrail.SelectedIndex = _clamp_index(settings.get("handrail_type", self.cb_handrail.SelectedIndex), 0, 3, self.cb_handrail.SelectedIndex)
        self.nud_hr_height.Value = float(settings.get("hr_height", self.nud_hr_height.Value))
        self.nud_turns.Value = _clamp_index(settings.get("turn_count", self.nud_turns.Value), 0, 10, self.nud_turns.Value)
        self.chk_flip.Checked = bool(settings.get("is_flipped", self.chk_flip.Checked))
        self.RefreshPreview(None, None)

    def OnPresetLoad(self, sender, e):
        name = self._selected_preset_name()
        if not name:
            rs.MessageBox("불러올 프리셋을 선택하세요.", 0, "프리셋")
            return
        settings = self.presets.get(name)
        if not settings:
            rs.MessageBox("선택한 프리셋 데이터를 읽을 수 없습니다.", 0, "프리셋 오류")
            return
        self.ApplySettingsToUI(settings)

    def OnPresetSave(self, sender, e):
        name = str(self.txt_preset_name.Text).strip()
        if not name:
            rs.MessageBox("프리셋 이름을 입력하세요.", 0, "프리셋")
            return
        if name in self.presets:
            rc = rs.MessageBox("같은 이름의 프리셋이 이미 있습니다.\n현재 값으로 덮어쓰시겠습니까?", 4, "프리셋 덮어쓰기")
            if rc not in [6, True]:
                return
        self.presets[name] = self.get_current_settings()
        if _save_presets(self.presets):
            self.RefreshPresetDropdown()
            names = sorted(self.presets.keys())
            try:
                self.dd_preset.SelectedIndex = names.index(name)
            except:
                pass

    def OnPresetDelete(self, sender, e):
        name = self._selected_preset_name()
        if not name:
            rs.MessageBox("삭제할 프리셋을 선택하세요.", 0, "프리셋")
            return
        rc = rs.MessageBox("'{0}' 프리셋을 삭제하시겠습니까?".format(name), 4, "프리셋 삭제")
        if rc not in [6, True]:
            return
        if name in self.presets:
            del self.presets[name]
        _save_presets(self.presets)
        self.txt_preset_name.Text = ""
        self.RefreshPresetDropdown()

    def apply_edit_context(self, initial_settings, edit_id, edit_sets):
        """Apply saved metadata after creating the Eto Form.
        edit_sets contains current copy sets and xforms from the selected set.
        """
        self.initial_settings = initial_settings if initial_settings else {}
        self.edit_id = edit_id
        self.edit_sets = edit_sets if edit_sets else []
        self.selected_set = None
        for edit_set in self.edit_sets:
            if edit_set.get("is_selected"):
                self.selected_set = edit_set
                break
        if self.selected_set is None and self.edit_sets:
            self.selected_set = self.edit_sets[0]

        self.Title = "원형 계단 수정" if self.edit_id else "원형 계단 생성기"
        self.btn_create.Text = "수정" if self.edit_id else "생성"
        self.chk_update_linked.Enabled = bool(self.edit_id and len(self.edit_sets) > 1)
        self.chk_update_linked.Checked = bool(self.edit_id and len(self.edit_sets) > 1)
        if self.edit_id:
            self.lbl_linked_info.Text = "감지된 복사본 세트: {0}개".format(max(1, len(self.edit_sets)))
        else:
            self.lbl_linked_info.Text = ""

        self.ApplySettingsToUI(self.initial_settings)

    def get_current_settings(self):
        return {
            "has_pole": bool(self.chk_pole.Checked),
            "r_inner": float(self.nud_r_inner.Value),
            "stair_width": float(self.nud_width.Value),
            "stair_type": int(self.cb_stair_type.SelectedIndex),
            "handrail_type": int(self.cb_handrail.SelectedIndex),
            "hr_height": float(self.nud_hr_height.Value),
            "turn_count": int(self.nud_turns.Value),
            "is_flipped": bool(self.chk_flip.Checked)
        }

    def save_settings(self):
        settings = self.get_current_settings()
        sc.sticky["SP_Pole"] = settings["has_pole"]
        sc.sticky["SP_RInner"] = settings["r_inner"]
        sc.sticky["SP_Width"] = settings["stair_width"]
        sc.sticky["SP_Type"] = settings["stair_type"]
        sc.sticky["SP_Handrail"] = settings["handrail_type"]
        sc.sticky["SP_HrHeight"] = settings["hr_height"]
        sc.sticky["SP_Turns"] = settings["turn_count"]
        sc.sticky["SP_Flip"] = settings["is_flipped"]
        return settings

    def build_metadata_for_engine(self, engine, spiral_id, settings):
        data = {}
        data["id"] = spiral_id
        if engine:
            data.update(engine.ToSavedData())
        data["has_pole"] = _bool_to_text(settings["has_pole"])
        data["r_inner"] = settings["r_inner"]
        data["stair_width"] = settings["stair_width"]
        data["handrail_type"] = settings["handrail_type"]
        data["hr_height"] = settings["hr_height"]
        data["stair_type"] = settings["stair_type"]
        data["turn_count"] = settings["turn_count"]
        data["is_flipped"] = _bool_to_text(settings["is_flipped"])
        return data

    def setup_engine(self, engine):
        self.engine = engine
        self.conduit.Enabled = True
        self.RefreshPreview(None, None)

    def RefreshPreview(self, sender, e):
        if self.engine is None:
            return

        self.nud_hr_height.Enabled = (self.cb_handrail.SelectedIndex == 2)

        stair_b, hr_b, hr_c = self.engine.calculate_geometry(
            has_pole=self.chk_pole.Checked,
            r_inner=float(self.nud_r_inner.Value),
            stair_width=float(self.nud_width.Value),
            handrail_type=self.cb_handrail.SelectedIndex,
            hr_height=float(self.nud_hr_height.Value),
            stair_type=self.cb_stair_type.SelectedIndex,
            turn_count=int(self.nud_turns.Value),
            is_flipped=self.chk_flip.Checked
        )

        self.conduit.UpdateGeometry(stair_b + hr_b, hr_c)
        Rhino.RhinoDoc.ActiveDoc.Views.Redraw()

    def ClosePreview(self):
        if self._closing_preview:
            return
        self._closing_preview = True
        try:
            self.conduit.UpdateGeometry([], [])
            self.conduit.Enabled = False
            Rhino.RhinoDoc.ActiveDoc.Views.Redraw()
        except:
            pass

    def _ensure_layers(self):
        layer_stair = "Stair_Spiral"
        layer_handrail = "Railing_BaseCrv"
        if not rs.IsLayer(layer_stair):
            rs.AddLayer(layer_stair, System.Drawing.Color.DimGray)
        if not rs.IsLayer(layer_handrail):
            rs.AddLayer(layer_handrail, System.Drawing.Color.LightSlateGray)
        return layer_stair, layer_handrail

    def _bake_engine_set(self, engine, settings, spiral_id):
        layer_stair, layer_handrail = self._ensure_layers()
        metadata = self.build_metadata_for_engine(engine, spiral_id, settings)
        group_name = rs.AddGroup()
        new_object_ids = []
        parts = _generate_reference_parts(engine, settings)

        for part_name, geom_type, geom in parts:
            obj_id = None
            if geom_type == "brep":
                obj_id = sc.doc.Objects.AddBrep(geom)
            elif geom_type == "curve":
                obj_id = sc.doc.Objects.AddCurve(geom)

            if obj_id and obj_id != System.Guid.Empty:
                if part_name == "stair_brep":
                    rs.ObjectLayer(obj_id, layer_stair)
                else:
                    rs.ObjectLayer(obj_id, layer_handrail)
                _set_user_texts(obj_id, metadata)
                if group_name:
                    rs.AddObjectToGroup(obj_id, group_name)
                new_object_ids.append(obj_id)
        return new_object_ids

    def _get_target_sets_for_edit(self):
        if not self.edit_id:
            return []
        if self.chk_update_linked.Checked:
            return self.edit_sets if self.edit_sets else []
        if self.selected_set:
            return [self.selected_set]
        if self.edit_sets:
            return [self.edit_sets[0]]
        return []

    def OnCreateClick(self, sender, e):
        settings = self.save_settings()
        self.ClosePreview()

        try:
            rs.EnableRedraw(False)

            if self.edit_id:
                target_sets = self._get_target_sets_for_edit()
                if not target_sets:
                    target_sets = [{"object_ids": [], "xform": rg.Transform.Identity, "is_selected": True}]

                old_ids = []
                for edit_set in target_sets:
                    old_ids.extend(edit_set.get("object_ids", []))
                _delete_objects_safe(old_ids)

                # Linked edit keeps the ID. Independent edit splits the selected copy into a new family.
                if self.chk_update_linked.Checked:
                    target_spiral_id = self.edit_id
                else:
                    target_spiral_id = str(System.Guid.NewGuid())

                baked_count = 0
                for edit_set in target_sets:
                    xform = edit_set.get("xform", rg.Transform.Identity)
                    engine_for_set = self.engine.Transformed(xform)
                    baked_count += len(self._bake_engine_set(engine_for_set, settings, target_spiral_id))

                if self.chk_update_linked.Checked and len(target_sets) > 1:
                    print("원형 계단 복사본 {0}개 세트가 함께 수정되었습니다.".format(len(target_sets)))
                else:
                    print("원형 계단 수정이 완료되었습니다!")
            else:
                spiral_id = str(System.Guid.NewGuid())
                self._bake_engine_set(self.engine, settings, spiral_id)
                print("원형 계단 생성이 완료되었습니다!")

        except Exception as ex:
            print("Bake 처리 중 오류 발생:", ex)
        finally:
            rs.EnableRedraw(True)
            Rhino.RhinoDoc.ActiveDoc.Views.Redraw()
            self.Close()

    def OnCancelClick(self, sender, e):
        self.save_settings()
        self.ClosePreview()
        self.Close()

    def OnFormClosed(self, sender, e):
        self.ClosePreview()


# --- [4] 입력 및 자동 수정/신규 생성 분기 ---
def _settings_from_saved_data(data):
    return {
        "has_pole": _text_to_bool(data.get("has_pole"), True),
        "r_inner": _safe_float(data.get("r_inner"), 150.0),
        "stair_width": _safe_float(data.get("stair_width"), 1200.0),
        "handrail_type": _safe_int(data.get("handrail_type"), 3),
        "hr_height": _safe_float(data.get("hr_height"), 1500.0),
        "stair_type": _safe_int(data.get("stair_type"), 0),
        "turn_count": _safe_int(data.get("turn_count"), 0),
        "is_flipped": _text_to_bool(data.get("is_flipped"), False)
    }


def _find_xform_for_selected_set(old_engine, old_settings, selected_id, set_ids):
    old_parts = _generate_reference_parts(old_engine, old_settings)
    xform = _find_xform_from_parts_to_object(old_parts, selected_id)
    if xform is not None:
        return xform

    # If the user selected a curve or a Boolean-unioned part that does not match cleanly,
    # try other objects in the same group/set.
    for obj_id in set_ids:
        xform = _find_xform_from_parts_to_object(old_parts, obj_id)
        if xform is not None:
            return xform
    return rg.Transform.Identity


def _build_edit_context(data, selected_id):
    """Resolve current selected copy position and linked-copy transforms.
    Returns current_engine_for_selected_set, edit_sets.
    """
    old_engine = SpiralStairEngine.FromSavedData(data)
    old_settings = _settings_from_saved_data(data)
    spiral_id = data.get("id")

    all_sets = _collect_spiral_sets_by_group(spiral_id)
    selected_key = _get_selected_set_key(selected_id)
    selected_set_ids = []
    for edit_set in all_sets:
        if edit_set.get("key") == selected_key or selected_id in edit_set.get("object_ids", []):
            selected_set_ids = edit_set.get("object_ids", [])
            break
    if not selected_set_ids:
        selected_set_ids = [selected_id]

    xform_old_to_selected = _find_xform_for_selected_set(old_engine, old_settings, selected_id, selected_set_ids)
    selected_engine = old_engine.Transformed(xform_old_to_selected)

    selected_reference_parts = _generate_reference_parts(selected_engine, old_settings)
    edit_sets = []
    has_selected = False

    for edit_set in all_sets:
        ids = edit_set.get("object_ids", [])
        is_selected = selected_id in ids or edit_set.get("key") == selected_key
        if is_selected:
            edit_sets.append({
                "key": edit_set.get("key"),
                "object_ids": ids,
                "xform": rg.Transform.Identity,
                "is_selected": True
            })
            has_selected = True
            continue

        xform = None
        for obj_id in ids:
            xform = _find_xform_from_parts_to_object(selected_reference_parts, obj_id)
            if xform is not None:
                break
        if xform is not None:
            edit_sets.append({
                "key": edit_set.get("key"),
                "object_ids": ids,
                "xform": xform,
                "is_selected": False
            })

    if not has_selected:
        edit_sets.insert(0, {
            "key": selected_key,
            "object_ids": selected_set_ids,
            "xform": rg.Transform.Identity,
            "is_selected": True
        })

    return selected_engine, edit_sets


def _get_second_curve():
    go = Rhino.Input.Custom.GetObject()
    go.SetCommandPrompt("새 원형 계단의 두 번째 기준 커브를 선택하세요.")
    go.GeometryFilter = Rhino.DocObjects.ObjectType.Curve
    go.SubObjectSelect = False
    go.EnablePreSelect(False, True)
    res = go.Get()
    if res != Rhino.Input.GetResult.Object:
        return None
    obj_ref = go.Object(0)
    return obj_ref.Curve()


def _get_auto_input():
    while True:
        go = Rhino.Input.Custom.GetObject()
        go.SetCommandPrompt("수정할 원형 계단 객체 1개 또는 새 계단의 기준 커브 2개를 선택하세요.")
        go.GeometryFilter = Rhino.DocObjects.ObjectType.Curve | Rhino.DocObjects.ObjectType.Brep
        go.SubObjectSelect = False
        go.EnablePreSelect(False, True)
        res = go.GetMultiple(1, 2)
        
        if res == Rhino.Input.GetResult.Cancel:
            return None
        if res != Rhino.Input.GetResult.Object:
            return None

        # 1. 생성된 원형 계단 객체인지 먼저 검사
        for i in range(go.ObjectCount):
            obj_ref = go.Object(i)
            data = _load_spiral_data_from_object(obj_ref.ObjectId)
            if data:
                spiral_id = data.get("id")
                return {
                    "mode": "edit",
                    "data": data,
                    "spiral_id": spiral_id,
                    "selected_id": obj_ref.ObjectId
                }

        # 2. 기존 원형 계단이 아니면 새 기준 커브 입력으로 처리
        curves = []
        for i in range(go.ObjectCount):
            obj_ref = go.Object(i)
            crv = obj_ref.Curve()
            if crv:
                curves.append(crv)

        if len(curves) == 2:
            return {"mode": "create", "curves": curves}
        elif len(curves) == 1:
            second = _get_second_curve()
            if second:
                return {"mode": "create", "curves": [curves[0], second]}
            return None
        else:
            rs.MessageBox("기존 원형 계단 객체 또는 기준 커브를 선택해야 합니다.", 0, "선택 오류")
            rs.UnselectAllObjects()
            continue


# --- [5] 메인 실행 함수 ---
def main():
    rs.Prompt("기존 원형 계단을 선택하면 수정하고, 일반 커브 2개를 선택하면 새로 생성합니다.")
    result = _get_auto_input()
    if not result:
        return

    if result["mode"] == "edit":
        selected_id = result.get("selected_id")
        try:
            engine, edit_sets = _build_edit_context(result["data"], selected_id)
        except Exception as ex:
            print("수정 컨텍스트 계산 오류:", ex)
            engine = SpiralStairEngine.FromSavedData(result["data"])
            edit_sets = [{"object_ids": _collect_spiral_object_ids(result["spiral_id"]), "xform": rg.Transform.Identity, "is_selected": True}]

        if engine.center_pt is None:
            rs.MessageBox("선택한 원형 계단의 저장 정보를 읽을 수 없습니다.", 0, "수정 오류")
            return
        initial_settings = _settings_from_saved_data(result["data"])
        dlg = SpiralStairDialog()
        dlg.apply_edit_context(initial_settings, result["spiral_id"], edit_sets)
    else:
        crv1 = result["curves"][0]
        crv2 = result["curves"][1]
        engine = SpiralStairEngine(crv1, crv2)
        if engine.center_pt is None:
            return
        dlg = SpiralStairDialog()

    dlg.setup_engine(engine)
    dlg.Owner = Rhino.UI.RhinoEtoApp.MainWindow
    dlg.Show()


if __name__ == "__main__":
    main()
