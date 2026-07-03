# -*- coding: utf-8 -*-
import Rhino
import Rhino.Geometry as rg
import scriptcontext as sc
import rhinoscriptsyntax as rs
import Eto.Forms as forms
import Eto.Drawing as drawing
import System
import math

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
        self.edit_object_ids = []
        
        self.bake_stair_breps = []
        self.bake_hr_breps = []
        self.bake_hr_curves = []
        
        self.Title = "원형 계단 수정" if self.edit_id else "원형 계단 생성기"
        self.Padding = drawing.Padding(12)
        self.Resizable = True
        self.Topmost = True 

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
        self.cb_stair_type.SelectedIndex = int(def_type)
        
        self.cb_handrail = forms.DropDown()
        self.cb_handrail.DataStore = ["없음", "가이드 라인", "솔리드 난간", "03. 철골"]
        self.cb_handrail.SelectedIndex = int(def_handrail)
        
        self.nud_hr_height = forms.NumericStepper(Value=float(def_hr_height), DecimalPlaces=0, Increment=50, MinValue=300, MaxValue=3000)
        self.nud_turns = forms.NumericStepper(Value=int(def_turns), DecimalPlaces=0, Increment=1, MinValue=0, MaxValue=10)
        self.chk_flip = forms.CheckBox(Text="회전 방향 뒤집기 (Flip)", Checked=bool(def_flip))

        self.btn_create = forms.Button(Text="수정" if self.edit_id else "생성")
        self.btn_cancel = forms.Button(Text="취소")

        self.chk_pole.CheckedChanged += self.RefreshPreview
        self.nud_r_inner.ValueChanged += self.RefreshPreview
        self.nud_width.ValueChanged += self.RefreshPreview
        self.cb_stair_type.SelectedIndexChanged += self.RefreshPreview
        self.cb_handrail.SelectedIndexChanged += self.RefreshPreview
        self.nud_hr_height.ValueChanged += self.RefreshPreview
        self.nud_turns.ValueChanged += self.RefreshPreview
        self.chk_flip.CheckedChanged += self.RefreshPreview

        self.btn_create.Click += self.OnCreateClick
        self.btn_cancel.Click += self.OnCancelClick
        self.Closed += self.OnFormClosed

        layout = forms.DynamicLayout()
        layout.Spacing = drawing.Size(8, 8)
        
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
        layout.AddRow(self.btn_create, self.btn_cancel)

        self.Content = layout

    def apply_edit_context(self, initial_settings, edit_id, edit_object_ids):
        """Apply saved metadata after creating the Eto Form.
        This avoids passing arguments directly into forms.Form constructor,
        which can fail in Rhino/IronPython with: takes at most 2 arguments.
        """
        self.initial_settings = initial_settings if initial_settings else {}
        self.edit_id = edit_id
        self.edit_object_ids = edit_object_ids if edit_object_ids else []

        self.Title = "원형 계단 수정" if self.edit_id else "원형 계단 생성기"
        self.btn_create.Text = "수정" if self.edit_id else "생성"

        self.chk_pole.Checked = bool(self.initial_settings.get("has_pole", self.chk_pole.Checked))
        self.nud_r_inner.Value = float(self.initial_settings.get("r_inner", self.nud_r_inner.Value))
        self.nud_width.Value = float(self.initial_settings.get("stair_width", self.nud_width.Value))

        stair_type = _safe_int(self.initial_settings.get("stair_type", self.cb_stair_type.SelectedIndex), self.cb_stair_type.SelectedIndex)
        if stair_type < 0: stair_type = 0
        if stair_type > 1: stair_type = 1
        self.cb_stair_type.SelectedIndex = stair_type

        handrail_type = _safe_int(self.initial_settings.get("handrail_type", self.cb_handrail.SelectedIndex), self.cb_handrail.SelectedIndex)
        if handrail_type < 0: handrail_type = 0
        if handrail_type > 3: handrail_type = 3
        self.cb_handrail.SelectedIndex = handrail_type

        self.nud_hr_height.Value = float(self.initial_settings.get("hr_height", self.nud_hr_height.Value))
        self.nud_turns.Value = int(self.initial_settings.get("turn_count", self.nud_turns.Value))
        self.chk_flip.Checked = bool(self.initial_settings.get("is_flipped", self.chk_flip.Checked))

    def get_current_settings(self):
        return {
            "has_pole": self.chk_pole.Checked,
            "r_inner": float(self.nud_r_inner.Value),
            "stair_width": float(self.nud_width.Value),
            "stair_type": self.cb_stair_type.SelectedIndex,
            "handrail_type": self.cb_handrail.SelectedIndex,
            "hr_height": float(self.nud_hr_height.Value),
            "turn_count": int(self.nud_turns.Value),
            "is_flipped": self.chk_flip.Checked
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

    def build_metadata(self, spiral_id, settings):
        data = {}
        data["id"] = spiral_id
        if self.engine:
            data.update(self.engine.ToSavedData())
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
        
        self.bake_stair_breps = stair_b
        self.bake_hr_breps = hr_b
        self.bake_hr_curves = hr_c
        
        self.conduit.UpdateGeometry(stair_b + hr_b, hr_c)
        Rhino.RhinoDoc.ActiveDoc.Views.Redraw()

    def OnCreateClick(self, sender, e):
        settings = self.save_settings()
        self.conduit.Enabled = False 
        spiral_id = self.edit_id if self.edit_id else str(System.Guid.NewGuid())
        metadata = self.build_metadata(spiral_id, settings)
        new_object_ids = []
        
        try:
            rs.EnableRedraw(False)
            
            layer_stair = "Stair_Spiral"
            layer_handrail = "Railing_BaseCrv"
            
            if not rs.IsLayer(layer_stair): 
                rs.AddLayer(layer_stair, System.Drawing.Color.DimGray)
            if not rs.IsLayer(layer_handrail): 
                rs.AddLayer(layer_handrail, System.Drawing.Color.LightSlateGray)
                
            group_name = rs.AddGroup()
                
            for b in self.bake_stair_breps:
                if b and b.IsValid:
                    obj_id = sc.doc.Objects.AddBrep(b)
                    if obj_id and obj_id != System.Guid.Empty:
                        rs.ObjectLayer(obj_id, layer_stair)
                        _set_user_texts(obj_id, metadata)
                        if group_name: rs.AddObjectToGroup(obj_id, group_name)
                        new_object_ids.append(obj_id)
            
            for b in self.bake_hr_breps:
                if b and b.IsValid:
                    obj_id = sc.doc.Objects.AddBrep(b)
                    if obj_id and obj_id != System.Guid.Empty:
                        rs.ObjectLayer(obj_id, layer_handrail)
                        _set_user_texts(obj_id, metadata)
                        if group_name: rs.AddObjectToGroup(obj_id, group_name)
                        new_object_ids.append(obj_id)
                        
            for c in self.bake_hr_curves:
                if c and c.IsValid:
                    obj_id = sc.doc.Objects.AddCurve(c)
                    if obj_id and obj_id != System.Guid.Empty:
                        rs.ObjectLayer(obj_id, layer_handrail)
                        _set_user_texts(obj_id, metadata)
                        if group_name: rs.AddObjectToGroup(obj_id, group_name)
                        new_object_ids.append(obj_id)

            if self.edit_id and new_object_ids:
                _delete_objects_safe(self.edit_object_ids)
                print("원형 계단 수정이 완료되었습니다!")
            else:
                print("원형 계단 생성이 완료되었습니다!")
        except Exception as ex:
            print("Bake 처리 중 오류 발생:", ex)
        finally:
            rs.EnableRedraw(True)
            Rhino.RhinoDoc.ActiveDoc.Views.Redraw()
            self.Close()

    def OnCancelClick(self, sender, e):
        self.save_settings()
        self.Close()

    def OnFormClosed(self, sender, e):
        self.conduit.Enabled = False
        Rhino.RhinoDoc.ActiveDoc.Views.Redraw()


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
                object_ids = _collect_spiral_object_ids(spiral_id)
                return {
                    "mode": "edit",
                    "data": data,
                    "spiral_id": spiral_id,
                    "object_ids": object_ids
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
        engine = SpiralStairEngine.FromSavedData(result["data"])
        if engine.center_pt is None:
            rs.MessageBox("선택한 원형 계단의 저장 정보를 읽을 수 없습니다.", 0, "수정 오류")
            return
        initial_settings = _settings_from_saved_data(result["data"])
        dlg = SpiralStairDialog()
        dlg.apply_edit_context(initial_settings, result["spiral_id"], result["object_ids"])
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
