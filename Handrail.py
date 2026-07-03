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
# Editable Railing metadata keys
# ==============================================================================
META_TOOL = "RLG_Tool"
META_TOOL_VALUE = "EditableRailing"
META_ID = "RLG_Id"
META_ROLE = "RLG_Role"
META_BASE_CURVE_ID = "RLG_BaseCurveId"
META_BASE_CURVE_POINTS = "RLG_BaseCurvePoints"

SETTING_KEYS = [
    "RLG_Height",
    "RLG_Interval",
    "RLG_Gap",
    "RLG_BtmGap",
    "RLG_Post",
    "RLG_PanelRails",
    "RLG_PanelType",
    "RLG_BarQty",
    "RLG_Handrail"
]

# --- [0] Utility functions for editable data ---
def safe_float(value, default):
    try:
        if value is None: return default
        return float(value)
    except:
        return default


def safe_int(value, default):
    try:
        if value is None: return default
        return int(float(value))
    except:
        return default


def safe_bool(value, default=False):
    if value is None: return default
    s = str(value).strip().lower()
    return s in ["true", "1", "yes", "y", "on"]


def clamp_index(value, minimum, maximum, default):
    try:
        v = int(value)
        if v < minimum: return minimum
        if v > maximum: return maximum
        return v
    except:
        return default


def set_object_user_data(obj_id, data):
    """Attach persistent UserText to a Rhino object."""
    if not obj_id or obj_id == System.Guid.Empty:
        return
    rh_obj = sc.doc.Objects.Find(obj_id)
    if not rh_obj:
        return
    for k, v in data.items():
        try:
            rh_obj.Attributes.SetUserString(k, str(v))
        except:
            pass
    rh_obj.CommitChanges()


def get_object_user_data(rh_obj, key, default=None):
    if not rh_obj:
        return default
    try:
        v = rh_obj.Attributes.GetUserString(key)
        if v is None or v == "": return default
        return v
    except:
        return default


def curve_to_points_string(curve):
    """Fallback storage for the base curve. The hidden base-curve object is primary."""
    if not curve:
        return ""
    pts = []
    try:
        length = curve.GetLength()
        div_count = int(math.ceil(length / 250.0))
        if div_count < 8: div_count = 8
        if div_count > 240: div_count = 240
        params = curve.DivideByCount(div_count, True)
        if params:
            for t in params:
                pts.append(curve.PointAt(t))
    except:
        pass
    if not pts:
        try:
            pts = [curve.PointAtStart, curve.PointAtEnd]
        except:
            pts = []
    chunks = []
    for p in pts:
        chunks.append("{0:.6f},{1:.6f},{2:.6f}".format(p.X, p.Y, p.Z))
    return ";".join(chunks)


def points_string_to_curve(text):
    if not text:
        return None
    pts = []
    try:
        for chunk in text.split(";"):
            vals = chunk.split(",")
            if len(vals) != 3:
                continue
            pts.append(rg.Point3d(float(vals[0]), float(vals[1]), float(vals[2])))
    except:
        return None
    if len(pts) < 2:
        return None
    try:
        polyline = rg.Polyline(pts)
        return polyline.ToNurbsCurve()
    except:
        return None


def ensure_layer(layer_name, color):
    if not rs.IsLayer(layer_name):
        rs.AddLayer(layer_name, color)


def find_base_curve_by_id(base_curve_id):
    if not base_curve_id:
        return None
    try:
        guid = System.Guid(str(base_curve_id))
        rh_obj = sc.doc.Objects.Find(guid)
        if rh_obj and rh_obj.Geometry:
            crv = rh_obj.Geometry
            if isinstance(crv, rg.Curve):
                return crv.DuplicateCurve()
            try:
                return crv.DuplicateCurve()
            except:
                return None
    except:
        return None
    return None


def create_or_update_base_curve_object(base_curve, railing_id, existing_base_curve_id, sample_points):
    """Create a hidden helper curve used for later editing. Reuse it in edit mode if possible."""
    if existing_base_curve_id:
        existing_curve = find_base_curve_by_id(existing_base_curve_id)
        if existing_curve:
            rh_obj = sc.doc.Objects.Find(System.Guid(str(existing_base_curve_id)))
            if rh_obj:
                data = {
                    META_TOOL: META_TOOL_VALUE,
                    META_ID: railing_id,
                    META_ROLE: "base_curve",
                    META_BASE_CURVE_ID: existing_base_curve_id,
                    META_BASE_CURVE_POINTS: sample_points
                }
                set_object_user_data(rh_obj.Id, data)
            return existing_base_curve_id

    ensure_layer("Railing_BaseCrv", System.Drawing.Color.DarkGray)
    obj_id = sc.doc.Objects.AddCurve(base_curve)
    if obj_id and obj_id != System.Guid.Empty:
        try:
            rs.ObjectLayer(obj_id, "Railing_BaseCrv")
        except:
            pass
        data = {
            META_TOOL: META_TOOL_VALUE,
            META_ID: railing_id,
            META_ROLE: "base_curve",
            META_BASE_CURVE_ID: str(obj_id),
            META_BASE_CURVE_POINTS: sample_points
        }
        set_object_user_data(obj_id, data)
        try:
            rs.HideObject(obj_id)
        except:
            pass
        return str(obj_id)
    return ""


def collect_railing_object_ids(railing_id):
    """Collect all generated objects sharing the same railing id. Hidden base curve is returned separately."""
    generated_ids = []
    base_curve_id = ""
    try:
        settings = Rhino.DocObjects.ObjectEnumeratorSettings()
        settings.NormalObjects = True
        settings.HiddenObjects = True
        settings.LockedObjects = True
        settings.DeletedObjects = False
        all_objects = sc.doc.Objects.GetObjectList(settings)
    except:
        all_objects = sc.doc.Objects

    for rh_obj in all_objects:
        try:
            rid = get_object_user_data(rh_obj, META_ID, "")
            if rid != railing_id:
                continue
            role = get_object_user_data(rh_obj, META_ROLE, "")
            if role == "base_curve":
                base_curve_id = str(rh_obj.Id)
            else:
                generated_ids.append(rh_obj.Id)
        except:
            pass
    return generated_ids, base_curve_id


def delete_objects(object_ids):
    for oid in object_ids:
        try:
            sc.doc.Objects.Delete(oid, True)
        except:
            try:
                rs.DeleteObject(oid)
            except:
                pass


def settings_from_object(rh_obj):
    if not rh_obj:
        return None
    if get_object_user_data(rh_obj, META_TOOL, "") != META_TOOL_VALUE:
        return None
    railing_id = get_object_user_data(rh_obj, META_ID, "")
    if not railing_id:
        return None

    settings = {}
    for key in SETTING_KEYS:
        settings[key] = get_object_user_data(rh_obj, key, None)

    settings[META_ID] = railing_id
    settings[META_BASE_CURVE_ID] = get_object_user_data(rh_obj, META_BASE_CURVE_ID, "")
    settings[META_BASE_CURVE_POINTS] = get_object_user_data(rh_obj, META_BASE_CURVE_POINTS, "")
    return settings


# --- [1] 실시간 화면 표시 엔진 (DisplayConduit) ---
class RailingPreviewConduit(Rhino.Display.DisplayConduit):
    def __init__(self):
        super(RailingPreviewConduit, self).__init__()
        self.preview_breps = []
        self.preview_color = System.Drawing.Color.Indigo
        self.wire_color = System.Drawing.Color.LightGray

    def UpdateGeometry(self, breps):
        self.preview_breps = breps

    def CalculateBoundingBox(self, e):
        if not self.preview_breps:
            return
        bbox = rg.BoundingBox.Empty
        for b in self.preview_breps:
            if b and b.IsValid:
                bbox.Union(b.GetBoundingBox(True))
        e.IncludeInBoundingBox(bbox)

    def PostDrawObjects(self, e):
        if not self.preview_breps:
            return
        display_mat = Rhino.Display.DisplayMaterial(self.preview_color)
        for b in self.preview_breps:
            if b and b.IsValid:
                e.Display.DrawBrepShaded(b, display_mat)
                e.Display.DrawBrepWires(b, self.wire_color, 1)


# --- [2] 지오메트리 계산 엔진 ---
class RailingEngine:
    def __init__(self, base_curve):
        self.base_curve = base_curve
        self.doc = Rhino.RhinoDoc.ActiveDoc
        self.tol = self.doc.ModelAbsoluteTolerance
        
        self.post_radius = 30.0
        self.member_radius = 30.0
        self.sub_member_radius = 20.0

    def calculate_geometry(self, total_height, post_interval, bottom_gap_on, post_on, panel_type, bar_qty, handrail_type, panel_rails_on, panel_gap):
        out_general = []
        out_panels = []
        
        bottom_gap_val = 200.0 if bottom_gap_on else 0.0
        handrail_gap = 0.0
        if handrail_type == 1: 
            handrail_gap = 150.0
            
        panel_height = total_height - bottom_gap_val - handrail_gap
        if panel_height < 10: panel_height = 10 
        
        z_bottom = bottom_gap_val
        z_panel_top = z_bottom + panel_height
        z_handrail = total_height

        segments = self.base_curve.DuplicateSegments()
        if not segments or len(segments) == 0:
            segments = [self.base_curve]

        post_points = []
        spans = []

        for seg in segments:
            seg_len = seg.GetLength()
            span_count = int(round(seg_len / post_interval))
            if span_count < 1: span_count = 1
            if span_count > 300: span_count = 300 
            
            div_params = seg.DivideByCount(span_count, True)
            if not div_params: continue

            if post_on:
                for t in div_params:
                    pt = seg.PointAt(t)
                    is_dup = False
                    for existing_pt in post_points:
                        if pt.DistanceTo(existing_pt) < 1.0:
                            is_dup = True
                            break
                    
                    if not is_dup:
                        post_points.append(pt)
                        post_cyl = rg.Cylinder(rg.Circle(rg.Plane(pt, rg.Vector3d.ZAxis), self.post_radius), total_height)
                        out_general.append(post_cyl.ToBrep(True, True))

            if seg.IsClosed:
                parts = seg.Split(div_params)
                if parts: spans.extend(parts)
            else:
                for i in range(len(div_params)-1):
                    part = seg.Trim(div_params[i], div_params[i+1])
                    if part: spans.append(part)

        final_spans = []
        for span in spans:
            if not post_on and panel_gap > 0: 
                sub_len = span.GetLength()
                if sub_len > panel_gap:
                    success0, pt0_t = span.LengthParameter(panel_gap / 2.0)
                    success1, pt1_t = span.LengthParameter(sub_len - (panel_gap / 2.0))
                    if success0 and success1 and pt0_t < pt1_t:
                        trimmed = span.Trim(pt0_t, pt1_t)
                        if trimmed: final_spans.append(trimmed)
            else:
                final_spans.append(span)

        for span_crv in final_spans:
            if panel_rails_on:
                for z_val in [z_bottom, z_panel_top]:
                    bar_crv = span_crv.Duplicate()
                    bar_crv.Translate(rg.Vector3d(0, 0, z_val)) 
                    out_general.extend(self.create_pipe(bar_crv, self.sub_member_radius))
            
            if panel_type == 0: 
                base_panel_crv = span_crv.Duplicate()
                base_panel_crv.Translate(rg.Vector3d(0, 0, z_bottom))
                thickness = 10.0
                success_solid = False
                
                try:
                    plane = rg.Plane.WorldXY
                    c1_arr = base_panel_crv.Offset(plane, thickness/2.0, self.tol, rg.CurveOffsetCornerStyle.Sharp)
                    c2_arr = base_panel_crv.Offset(plane, -thickness/2.0, self.tol, rg.CurveOffsetCornerStyle.Sharp)

                    if c1_arr and c2_arr and len(c1_arr) == 1 and len(c2_arr) == 1:
                        c1 = c1_arr[0]
                        c2 = c2_arr[0]
                        c2.Reverse()
                        
                        l1 = rg.Line(c1.PointAtEnd, c2.PointAtStart).ToNurbsCurve()
                        l2 = rg.Line(c2.PointAtEnd, c1.PointAtStart).ToNurbsCurve()
                        
                        joined = rg.Curve.JoinCurves([c1, l1, c2, l2], self.tol * 2)
                        if joined and joined[0].IsClosed:
                            extrusion_srf = rg.Surface.CreateExtrusion(joined[0], rg.Vector3d(0, 0, panel_height))
                            if extrusion_srf:
                                brep = extrusion_srf.ToBrep()
                                capped = brep.CapPlanarHoles(self.tol)
                                if capped:
                                    out_panels.append(capped)
                                    success_solid = True
                                else:
                                    out_panels.append(brep)
                                    success_solid = True
                except:
                    pass
                    
                if not success_solid:
                    try:
                        t_mid = base_panel_crv.Domain.Mid
                        vec_t = base_panel_crv.TangentAt(t_mid)
                        vec_n = rg.Vector3d.CrossProduct(vec_t, rg.Vector3d.ZAxis)
                        
                        if vec_n.Length < 1e-6: vec_n = rg.Vector3d.XAxis
                        vec_n.Unitize()
                        
                        crv_right = base_panel_crv.Duplicate()
                        crv_right.Translate(vec_n * (thickness/2.0))
                        
                        crv_left = base_panel_crv.Duplicate()
                        crv_left.Translate(vec_n * -(thickness/2.0))
                        crv_left.Reverse() 
                        
                        line1 = rg.Line(crv_right.PointAtEnd, crv_left.PointAtStart).ToNurbsCurve()
                        line2 = rg.Line(crv_left.PointAtEnd, crv_right.PointAtStart).ToNurbsCurve()
                        
                        joined = rg.Curve.JoinCurves([crv_right, line1, crv_left, line2])
                        if joined and joined[0].IsClosed:
                            extrusion_srf = rg.Surface.CreateExtrusion(joined[0], rg.Vector3d(0, 0, panel_height))
                            if extrusion_srf:
                                wall_brep = extrusion_srf.ToBrep()
                                capped = wall_brep.CapPlanarHoles(self.tol)
                                if capped:
                                    out_panels.append(capped)
                                    success_solid = True
                    except:
                        pass
                
                if not success_solid:
                    srf = rg.Surface.CreateExtrusion(base_panel_crv, rg.Vector3d(0, 0, panel_height))
                    if srf: out_panels.append(srf.ToBrep())
                    
            elif panel_type == 1: 
                if bar_qty > 0:
                    step_z = panel_height / (bar_qty + 1)
                    for i in range(1, bar_qty + 1):
                        bar_z = z_bottom + (step_z * i)
                        h_bar_crv = span_crv.Duplicate()
                        h_bar_crv.Translate(rg.Vector3d(0, 0, bar_z))
                        out_general.extend(self.create_pipe(h_bar_crv, self.sub_member_radius))
                        
            elif panel_type == 2: 
                if bar_qty > 0:
                    v_params = span_crv.DivideByCount(bar_qty + 1, True)
                    if v_params:
                        for t in v_params[1:-1]:
                            pt = span_crv.PointAt(t)
                            p0 = pt + rg.Vector3d(0, 0, z_bottom) 
                            v_cyl = rg.Cylinder(rg.Circle(rg.Plane(p0, rg.Vector3d.ZAxis), self.sub_member_radius), panel_height)
                            out_general.append(v_cyl.ToBrep(True, True))

        if handrail_type == 1:
            hr_crv = self.base_curve.Duplicate()
            hr_crv.Translate(rg.Vector3d(0, 0, z_handrail))
            out_general.extend(self.create_pipe(hr_crv, self.member_radius))

        return out_general, out_panels

    def create_pipe(self, curve, radius):
        pipes = rg.Brep.CreatePipe(curve, radius, False, rg.PipeCapMode.Flat, True, self.tol, self.doc.ModelAngleToleranceRadians)
        return list(pipes) if pipes else []


# --- [3] 실시간 제어 창 (Eto Modeless Form) ---
class RailingModelessDialog(forms.Form):
    def __init__(self):
        super(RailingModelessDialog, self).__init__()
        self.base_curve = None
        self.engine = None
        self.conduit = RailingPreviewConduit()
        
        self.bake_general = []
        self.bake_panels = []
        
        self.edit_id = None
        self.edit_object_ids = []
        self.base_curve_id = ""
        self.base_curve_points = ""
        self.is_edit_mode = False
        
        self.Title = "난간 생성기"
        self.Padding = drawing.Padding(12)
        self.Resizable = True
        self.Topmost = True 

        def_height = sc.sticky.get("RLG_Height", 1200)
        def_interval = sc.sticky.get("RLG_Interval", 1500)
        def_gap = sc.sticky.get("RLG_Gap", 20.0)
        def_btm_gap = sc.sticky.get("RLG_BtmGap", True)
        def_post = sc.sticky.get("RLG_Post", False) 
        def_panel_rails = sc.sticky.get("RLG_PanelRails", True)
        def_panel_type = sc.sticky.get("RLG_PanelType", 0)
        def_bar_qty = sc.sticky.get("RLG_BarQty", 5)
        def_handrail = sc.sticky.get("RLG_Handrail", 1)

        self.nud_height = forms.NumericStepper(Value=def_height, DecimalPlaces=0, Increment=50, MinValue=300, MaxValue=3000)
        self.nud_interval = forms.NumericStepper(Value=def_interval, DecimalPlaces=0, Increment=100, MinValue=300, MaxValue=5000)
        self.btn_apply_interval = forms.Button(Text="적용")
        
        self.nud_gap = forms.NumericStepper(Value=def_gap, DecimalPlaces=0, Increment=5, MinValue=0, MaxValue=500)
        
        self.chk_bottom_gap = forms.CheckBox(Text="바닥 띄움 (200mm)", Checked=def_btm_gap)
        self.chk_post = forms.CheckBox(Text="기둥 생성 (R=30)", Checked=def_post)
        self.chk_panel_rails = forms.CheckBox(Text="패널 상/하단 레일 생성", Checked=def_panel_rails)
        
        self.cb_panel_type = forms.DropDown()
        self.cb_panel_type.DataStore = ["01. 솔리드 (Solid)", "02. 가로 바 (Horizontal)", "03. 세로 바 (Vertical)"]
        self.cb_panel_type.SelectedIndex = def_panel_type
        
        self.nud_bar_qty = forms.NumericStepper(Value=def_bar_qty, DecimalPlaces=0, Increment=1, MinValue=0, MaxValue=50)
        
        self.cb_handrail = forms.DropDown()
        self.cb_handrail.DataStore = ["없음", "기본"] 
        self.cb_handrail.SelectedIndex = def_handrail

        self.btn_create = forms.Button(Text="생성")
        self.btn_cancel = forms.Button(Text="취소")

        self.nud_height.ValueChanged += self.RefreshPreview
        self.btn_apply_interval.Click += self.RefreshPreview 
        self.chk_bottom_gap.CheckedChanged += self.RefreshPreview
        self.chk_post.CheckedChanged += self.RefreshPreview
        self.chk_panel_rails.CheckedChanged += self.RefreshPreview
        self.nud_gap.ValueChanged += self.RefreshPreview 
        self.cb_panel_type.SelectedIndexChanged += self.RefreshPreview
        self.nud_bar_qty.ValueChanged += self.RefreshPreview
        self.cb_handrail.SelectedIndexChanged += self.RefreshPreview

        self.btn_create.Click += self.OnCreateClick
        self.btn_cancel.Click += self.OnCancelClick
        self.Closed += self.OnFormClosed

        interval_layout = forms.StackLayout(Orientation=forms.Orientation.Horizontal, Spacing=5)
        interval_layout.Items.Add(self.nud_interval)
        interval_layout.Items.Add(self.btn_apply_interval)

        layout = forms.DynamicLayout()
        layout.Spacing = drawing.Size(6, 6)
        
        layout.AddRow(forms.Label(Text="난간 총 높이:"), self.nud_height)
        layout.AddRow(forms.Label(Text="기둥 간격:"), interval_layout)
        layout.AddRow(None)
        layout.AddRow(self.chk_post)
        layout.AddRow(forms.Label(Text="└ 기둥 OFF시 간격:"), self.nud_gap) 
        layout.AddRow(None)
        layout.AddRow(self.chk_bottom_gap)
        layout.AddRow(self.chk_panel_rails)
        layout.AddRow(None)
        layout.AddRow(forms.Label(Text="패널 타입:"), self.cb_panel_type)
        layout.AddRow(forms.Label(Text="바 개수:"), self.nud_bar_qty)
        layout.AddRow(None)
        layout.AddRow(forms.Label(Text="손잡이 유형:"), self.cb_handrail)
        layout.AddRow(None)
        layout.AddRow(self.btn_create, self.btn_cancel)

        self.Content = layout

    def get_current_settings(self):
        return {
            "RLG_Height": float(self.nud_height.Value),
            "RLG_Interval": float(self.nud_interval.Value),
            "RLG_Gap": float(self.nud_gap.Value),
            "RLG_BtmGap": self.chk_bottom_gap.Checked,
            "RLG_Post": self.chk_post.Checked,
            "RLG_PanelRails": self.chk_panel_rails.Checked,
            "RLG_PanelType": self.cb_panel_type.SelectedIndex,
            "RLG_BarQty": int(self.nud_bar_qty.Value),
            "RLG_Handrail": self.cb_handrail.SelectedIndex
        }

    def save_settings_to_sticky(self):
        s = self.get_current_settings()
        for k, v in s.items():
            sc.sticky[k] = v

    def apply_settings(self, settings):
        if not settings:
            return
        self.nud_height.Value = safe_float(settings.get("RLG_Height"), 1200)
        self.nud_interval.Value = safe_float(settings.get("RLG_Interval"), 1500)
        self.nud_gap.Value = safe_float(settings.get("RLG_Gap"), 20.0)
        self.chk_bottom_gap.Checked = safe_bool(settings.get("RLG_BtmGap"), True)
        self.chk_post.Checked = safe_bool(settings.get("RLG_Post"), False)
        self.chk_panel_rails.Checked = safe_bool(settings.get("RLG_PanelRails"), True)
        self.cb_panel_type.SelectedIndex = clamp_index(settings.get("RLG_PanelType"), 0, 2, 0)
        self.nud_bar_qty.Value = safe_int(settings.get("RLG_BarQty"), 5)
        self.cb_handrail.SelectedIndex = clamp_index(settings.get("RLG_Handrail"), 0, 1, 1)

    def setup_curve(self, base_curve, initial_settings=None, edit_id=None, edit_object_ids=None, base_curve_id=None):
        self.base_curve = base_curve
        self.engine = RailingEngine(base_curve)
        self.edit_id = edit_id
        self.edit_object_ids = edit_object_ids if edit_object_ids else []
        self.base_curve_id = base_curve_id if base_curve_id else ""
        self.base_curve_points = curve_to_points_string(base_curve)
        self.is_edit_mode = edit_id is not None and edit_id != ""
        
        if self.is_edit_mode:
            self.Title = "난간 수정기"
            self.btn_create.Text = "수정"
        else:
            self.Title = "난간 생성기"
            self.btn_create.Text = "생성"
            
        if initial_settings:
            self.apply_settings(initial_settings)
            
        self.conduit.Enabled = True
        self.RefreshPreview(None, None)

    def RefreshPreview(self, sender, e):
        if self.engine is None: return 
        self.save_settings_to_sticky()
            
        gen_breps, pan_breps = self.engine.calculate_geometry(
            total_height=float(self.nud_height.Value),
            post_interval=float(self.nud_interval.Value),
            bottom_gap_on=self.chk_bottom_gap.Checked,
            post_on=self.chk_post.Checked,
            panel_type=self.cb_panel_type.SelectedIndex,
            bar_qty=int(self.nud_bar_qty.Value),
            handrail_type=self.cb_handrail.SelectedIndex,
            panel_rails_on=self.chk_panel_rails.Checked,
            panel_gap=float(self.nud_gap.Value) 
        )
        
        self.bake_general = gen_breps
        self.bake_panels = pan_breps
        
        self.conduit.UpdateGeometry(gen_breps + pan_breps)
        Rhino.RhinoDoc.ActiveDoc.Views.Redraw()

    def make_metadata(self, railing_id, base_curve_id, role):
        data = {
            META_TOOL: META_TOOL_VALUE,
            META_ID: railing_id,
            META_ROLE: role,
            META_BASE_CURVE_ID: base_curve_id,
            META_BASE_CURVE_POINTS: self.base_curve_points
        }
        settings = self.get_current_settings()
        for k, v in settings.items():
            data[k] = v
        return data

    def OnCreateClick(self, sender, e):
        self.save_settings_to_sticky()
        self.conduit.Enabled = False 
        rs.EnableRedraw(False)
        
        try:
            if self.is_edit_mode:
                railing_id = self.edit_id
            else:
                railing_id = str(System.Guid.NewGuid())

            base_curve_id = create_or_update_base_curve_object(
                self.base_curve,
                railing_id,
                self.base_curve_id,
                self.base_curve_points
            )

            # In edit mode, delete only generated objects. The hidden base curve is preserved/reused.
            if self.is_edit_mode and self.edit_object_ids:
                delete_objects(self.edit_object_ids)
            
            layer_main = "Railing_Result"
            if not rs.IsLayer(layer_main):
                rs.AddLayer(layer_main, System.Drawing.Color.DarkSlateGray)
                
            layer_panel = "Handrail_Panel"
            if not rs.IsLayer(layer_panel):
                rs.AddLayer(layer_panel, System.Drawing.Color.LightSteelBlue)
                
            group_name = rs.AddGroup()
                
            for b in self.bake_general:
                if not b or not b.IsValid:
                    continue
                obj_id = sc.doc.Objects.AddBrep(b)
                if obj_id and obj_id != System.Guid.Empty:
                    rs.ObjectLayer(obj_id, layer_main)
                    set_object_user_data(obj_id, self.make_metadata(railing_id, base_curve_id, "general"))
                    if group_name: rs.AddObjectToGroup(obj_id, group_name)
                
            for b in self.bake_panels:
                if not b or not b.IsValid:
                    continue
                obj_id = sc.doc.Objects.AddBrep(b)
                if obj_id and obj_id != System.Guid.Empty:
                    rs.ObjectLayer(obj_id, layer_panel)
                    set_object_user_data(obj_id, self.make_metadata(railing_id, base_curve_id, "panel"))
                    if group_name: rs.AddObjectToGroup(obj_id, group_name)
                
            if self.is_edit_mode:
                print("난간 수정이 완료되었습니다!")
            else:
                print("난간 생성이 완료되었습니다!")
        except Exception as ex:
            print("난간 Bake 처리 중 오류 발생:", ex)
        finally:
            rs.EnableRedraw(True)
            Rhino.RhinoDoc.ActiveDoc.Views.Redraw()
            self.Close()

    def OnCancelClick(self, sender, e):
        self.save_settings_to_sticky()
        self.Close()

    def OnFormClosed(self, sender, e):
        self.conduit.Enabled = False
        Rhino.RhinoDoc.ActiveDoc.Views.Redraw()
        try:
            if sc.sticky.get("RLG_ACTIVE_DIALOG") == self:
                sc.sticky.Remove("RLG_ACTIVE_DIALOG")
        except:
            pass


# --- [4] 메인 실행 함수: 기존 난간 선택 시 자동 수정, 일반 커브/모서리 선택 시 신규 생성 ---
def main():
    go = Rhino.Input.Custom.GetObject()
    go.SetCommandPrompt("수정할 난간 객체 또는 새 기준 커브/모서리 선택")
    go.GeometryFilter = Rhino.DocObjects.ObjectType.AnyObject
    go.SubObjectSelect = True  
    go.AcceptNothing(True)
    try:
        go.EnablePreSelect(False, True)
    except:
        pass
    
    opt_polyline = go.AddOption("Polyline")
    opt_curve = go.AddOption("Curve")
    
    base_curve = None
    edit_settings = None
    edit_id = None
    edit_object_ids = []
    base_curve_id = ""
    target_layer = "Railing_BaseCrv"
    
    while True:
        get_rc = go.Get()
        
        if get_rc == Rhino.Input.GetResult.Object:
            obj_ref = go.Object(0)
            rh_obj = obj_ref.Object()
            
            # 1) Existing editable railing object selected: edit mode.
            edit_settings = settings_from_object(rh_obj)
            if edit_settings:
                edit_id = edit_settings.get(META_ID, "")
                edit_object_ids, found_base_curve_id = collect_railing_object_ids(edit_id)
                base_curve_id = edit_settings.get(META_BASE_CURVE_ID, "") or found_base_curve_id
                base_curve = find_base_curve_by_id(base_curve_id)
                
                if base_curve is None:
                    base_curve = points_string_to_curve(edit_settings.get(META_BASE_CURVE_POINTS, ""))
                    if base_curve is None:
                        rs.MessageBox("저장된 기준 커브를 찾을 수 없습니다. 이 난간은 수정할 수 없습니다.", 0, "수정 오류")
                        return
                break
            
            # 2) Normal curve or edge selected: new creation mode.
            crv = None
            try:
                crv = obj_ref.Curve()
            except:
                crv = None
            if crv:
                base_curve = crv.DuplicateCurve()
                break
            
            rs.MessageBox("선택한 객체는 편집 가능한 난간도 아니고 기준 커브도 아닙니다.", 0, "선택 오류")
            try:
                rs.UnselectAllObjects()
                go.ClearObjects()
            except:
                pass
            go.SetCommandPrompt("수정할 난간 객체 또는 새 기준 커브/모서리 선택")
            continue
            
        elif get_rc == Rhino.Input.GetResult.Option:
            opt_idx = go.Option().Index
            
            # [DrawPolyline 옵션]
            if opt_idx == opt_polyline:
                rs.UnselectAllObjects()
                if rs.Command("_Polyline"):
                    created = rs.LastCreatedObjects()
                    if created:
                        if not rs.IsLayer(target_layer):
                            rs.AddLayer(target_layer, System.Drawing.Color.DarkGray)
                        rs.ObjectLayer(created[0], target_layer)
                        base_curve = rs.coercecurve(created[0]).DuplicateCurve()
                        break
                    
            # [DrawCurve 옵션]
            elif opt_idx == opt_curve:
                rs.UnselectAllObjects()
                if rs.Command("_Curve"):
                    created = rs.LastCreatedObjects()
                    if created:
                        if not rs.IsLayer(target_layer):
                            rs.AddLayer(target_layer, System.Drawing.Color.DarkGray)
                        rs.ObjectLayer(created[0], target_layer)
                        base_curve = rs.coercecurve(created[0]).DuplicateCurve()
                        break
                        
            go.SetCommandPrompt("다시 선택하거나 옵션을 선택하세요")
            continue
            
        else:
            break

    if not base_curve:
        return

    dlg = RailingModelessDialog()
    dlg.setup_curve(
        base_curve,
        initial_settings=edit_settings,
        edit_id=edit_id,
        edit_object_ids=edit_object_ids,
        base_curve_id=base_curve_id
    )
    
    dlg.Owner = Rhino.UI.RhinoEtoApp.MainWindow
    sc.sticky["RLG_ACTIVE_DIALOG"] = dlg
    dlg.Show()

if __name__ == "__main__":
    main()
