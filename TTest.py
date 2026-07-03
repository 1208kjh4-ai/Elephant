# -*- coding: utf-8 -*-
import Rhino
import Rhino.Geometry as rg
import scriptcontext as sc
import Eto.Forms as forms
import Eto.Drawing as drawing
import math
import rhinoscriptsyntax as rs
import System
import os
import uuid

# -------------------------------------------------------------------------
# 0. 편집 기능용 메타데이터 유틸리티
# -------------------------------------------------------------------------
STEEL_KIND_KEY = "Steel_Edit_Kind"
STEEL_ID_KEY = "Steel_Edit_ID"
STEEL_SOURCE_ID_KEY = "Steel_Edit_SourceID"

def _guid_to_str(g):
    return str(g)

def _set_user_text(obj_id, key, value):
    try:
        rs.SetUserText(obj_id, key, str(value))
    except Exception as ex:
        print("UserText 저장 오류:", ex)

def _get_user_text(obj_id, key, default=None):
    try:
        val = rs.GetUserText(obj_id, key)
        return val if val is not None else default
    except:
        return default

def _to_bool(value, default=False):
    if value is None: return default
    return str(value).lower() in ["true", "1", "yes", "y"]

def _to_int(value, default=0):
    try: return int(float(value))
    except: return default

def _to_float(value, default=0.0):
    try: return float(value)
    except: return default

def _get_doc_object(obj_id):
    try:
        return sc.doc.Objects.Find(System.Guid(str(obj_id)))
    except:
        try:
            return sc.doc.Objects.Find(obj_id)
        except:
            return None

def _get_brep_from_id(obj_id):
    try:
        return rs.coercebrep(System.Guid(str(obj_id)))
    except:
        try:
            return rs.coercebrep(obj_id)
        except:
            return None

def _ensure_layer(layer_name, color=None, visible=True):
    if not rs.IsLayer(layer_name):
        if color: rs.AddLayer(layer_name, color)
        else: rs.AddLayer(layer_name)
    try: rs.LayerVisible(layer_name, visible)
    except: pass

def _make_hidden_source_copy(source_brep, steel_id):
    layer_name = "Steel_EditSource"
    _ensure_layer(layer_name, System.Drawing.Color.DarkGray, False)
    dup = source_brep.DuplicateBrep() if hasattr(source_brep, "DuplicateBrep") else source_brep.Duplicate()
    src_id = sc.doc.Objects.AddBrep(dup)
    if src_id and src_id != System.Guid.Empty:
        try: rs.ObjectLayer(src_id, layer_name)
        except: pass
        _set_user_text(src_id, STEEL_KIND_KEY, "source")
        _set_user_text(src_id, STEEL_ID_KEY, steel_id)
        try: sc.doc.Objects.Hide(src_id, True)
        except: pass
        return src_id
    return None

def _find_output_ids_by_steel_id(steel_id):
    ids = []
    try:
        all_ids = rs.AllObjects(False) or []
    except:
        all_ids = []
    for oid in all_ids:
        if _get_user_text(oid, STEEL_KIND_KEY) == "output" and _get_user_text(oid, STEEL_ID_KEY) == steel_id:
            ids.append(oid)
    return ids

def _read_steel_settings(obj_id):
    if _get_user_text(obj_id, STEEL_KIND_KEY) != "output":
        return None
    steel_id = _get_user_text(obj_id, STEEL_ID_KEY)
    source_id = _get_user_text(obj_id, STEEL_SOURCE_ID_KEY)
    if not steel_id or not source_id:
        return None
    settings = {
        "steel_id": steel_id,
        "source_id": source_id,
        "profile_index": _to_int(_get_user_text(obj_id, "Steel_ProfileIndex"), 0),
        "t1": _to_float(_get_user_text(obj_id, "Steel_t1"), 20.0),
        "t2": _to_float(_get_user_text(obj_id, "Steel_t2"), 30.0),
        "r": _to_float(_get_user_text(obj_id, "Steel_r"), 20.0),
        "rot_x": _to_int(_get_user_text(obj_id, "Steel_RotX"), 0),
        "rot_y": _to_int(_get_user_text(obj_id, "Steel_RotY"), 0),
        "rot_z": _to_int(_get_user_text(obj_id, "Steel_RotZ"), 0),
        "custom_length": _get_user_text(obj_id, "Steel_CustomLength"),
        "custom_b": _get_user_text(obj_id, "Steel_CustomB"),
        "custom_h": _get_user_text(obj_id, "Steel_CustomH")
    }
    if settings["custom_length"] in [None, "", "None"]:
        settings["custom_length"] = None
    else:
        settings["custom_length"] = _to_float(settings["custom_length"], None)

    if settings["custom_b"] in [None, "", "None"]:
        settings["custom_b"] = None
    else:
        settings["custom_b"] = _to_float(settings["custom_b"], None)

    if settings["custom_h"] in [None, "", "None"]:
        settings["custom_h"] = None
    else:
        settings["custom_h"] = _to_float(settings["custom_h"], None)
    return settings

def _write_steel_settings(obj_id, steel_id, source_id, settings):
    _set_user_text(obj_id, STEEL_KIND_KEY, "output")
    _set_user_text(obj_id, STEEL_ID_KEY, steel_id)
    _set_user_text(obj_id, STEEL_SOURCE_ID_KEY, _guid_to_str(source_id))
    _set_user_text(obj_id, "Steel_ProfileIndex", settings.get("profile_index", 0))
    _set_user_text(obj_id, "Steel_t1", settings.get("t1", 20.0))
    _set_user_text(obj_id, "Steel_t2", settings.get("t2", 30.0))
    _set_user_text(obj_id, "Steel_r", settings.get("r", 20.0))
    _set_user_text(obj_id, "Steel_RotX", settings.get("rot_x", 0))
    _set_user_text(obj_id, "Steel_RotY", settings.get("rot_y", 0))
    _set_user_text(obj_id, "Steel_RotZ", settings.get("rot_z", 0))
    cl = settings.get("custom_length", None)
    _set_user_text(obj_id, "Steel_CustomLength", "" if cl is None else cl)
    cb = settings.get("custom_b", None)
    _set_user_text(obj_id, "Steel_CustomB", "" if cb is None else cb)
    ch = settings.get("custom_h", None)
    _set_user_text(obj_id, "Steel_CustomH", "" if ch is None else ch)


# -------------------------------------------------------------------------
# 1. 기하학 엔진: 직육면체(Brep)에서 중심과 3축 길이(OBB) 완벽 추출
# -------------------------------------------------------------------------
def get_obb_data(brep):
    faces = list(brep.Faces)
    if len(faces) != 6:
        bbox = brep.GetBoundingBox(True)
        center = bbox.Center
        return center, [
            (rg.Vector3d.XAxis, bbox.Max.X - bbox.Min.X),
            (rg.Vector3d.YAxis, bbox.Max.Y - bbox.Min.Y),
            (rg.Vector3d.ZAxis, bbox.Max.Z - bbox.Min.Z)
        ]

    v = brep.Vertices[0]
    edge_indices = v.EdgeIndices()
    edges = [brep.Edges[idx] for idx in edge_indices]

    if len(edges) != 3:
        bbox = brep.GetBoundingBox(True)
        center = bbox.Center
        return center, [
            (rg.Vector3d.XAxis, bbox.Max.X - bbox.Min.X),
            (rg.Vector3d.YAxis, bbox.Max.Y - bbox.Min.Y),
            (rg.Vector3d.ZAxis, bbox.Max.Z - bbox.Min.Z)
        ]

    v_pt = v.Location
    axes = []
    for e in edges:
        crv = e.ToNurbsCurve()
        length = crv.GetLength()
        if crv.PointAtStart.DistanceTo(v_pt) < 0.001:
            vec = crv.TangentAtStart
        else:
            vec = -crv.TangentAtEnd
        vec.Unitize()
        axes.append((vec, length))

    amp = rg.AreaMassProperties.Compute(brep)
    center = amp.Centroid if amp else brep.GetBoundingBox(True).Center

    return center, axes

# -------------------------------------------------------------------------
# 2. 기하학 엔진: 3차원 평면 회전, r값 연산 및 솔리드 압출
# -------------------------------------------------------------------------
def generate_steel_member(brep, p_type, t1, t2, r, ax, ay, az, custom_length=None, custom_B=None, custom_H=None):
    center, axes = get_obb_data(brep)
    
    axes.sort(key=lambda x: x[1], reverse=True)
    vec_z, len_z = axes[0]
    vec_x, len_x = axes[1]
    vec_y, len_y = axes[2]
    
    plane = rg.Plane(center, vec_x, vec_y)
    if plane.ZAxis * vec_z < 0:
        plane = rg.Plane(center, vec_y, vec_x)
        
    gizmo_plane = rg.Plane(plane)
        
    if ax != 0: plane.Rotate(math.radians(ax), gizmo_plane.XAxis, center)
    if ay != 0: plane.Rotate(math.radians(ay), gizmo_plane.YAxis, center)
    if az != 0: plane.Rotate(math.radians(az), gizmo_plane.ZAxis, center)
    
    B = H = L = 0.0
    for vec, length in axes:
        if abs(vec * plane.XAxis) > 0.9: B = length
        elif abs(vec * plane.YAxis) > 0.9: H = length
        elif abs(vec * plane.ZAxis) > 0.9: L = length
        
    if custom_B is not None and custom_B > 0:
        B = custom_B
    if custom_H is not None and custom_H > 0:
        H = custom_H
    if custom_length is not None and custom_length > 0:
        L = custom_length

    if B < 0.001 or H < 0.001 or L < 0.001: return None, None, None
    
    t1_val = min(t1, B * 0.9)
    t2_val = min(t2, H * 0.45)
    
    # ---------------------------------------------------------------------
    # r값이 형태를 파고들지 않도록 안전 한계선(Clamp) 자동 계산
    # ---------------------------------------------------------------------
    max_r = 0
    if p_type == "H-Beam":
        max_r = min((H - 2*t2_val)/2.0, (B - t1_val)/2.0)
    elif p_type == "C-Channel":
        max_r = min((H - 2*t2_val)/2.0, B - t1_val)
    elif p_type == "L-Plate":
        max_r = min(H - t2_val, B - t1_val)
    elif p_type == "T-Beam":
        max_r = min(H - t2_val, (B - t1_val)/2.0)
        
    # 버그를 막기 위해 최대 허용치의 98%까지만 허용
    r_val = min(r, max_r * 0.98) 
    if r_val < 0: r_val = 0
    
    # ---------------------------------------------------------------------
    # 모든 프로파일은 완벽한 반시계 방향(CCW)으로 좌표점 구성
    # ---------------------------------------------------------------------
    pts = []
    if p_type == "H-Beam":
        pts = [
            rg.Point3d(-B/2, -H/2, 0), rg.Point3d(B/2, -H/2, 0),
            rg.Point3d(B/2, -H/2 + t2_val, 0), rg.Point3d(t1_val/2, -H/2 + t2_val, 0),
            rg.Point3d(t1_val/2, H/2 - t2_val, 0), rg.Point3d(B/2, H/2 - t2_val, 0),
            rg.Point3d(B/2, H/2, 0), rg.Point3d(-B/2, H/2, 0),
            rg.Point3d(-B/2, H/2 - t2_val, 0), rg.Point3d(-t1_val/2, H/2 - t2_val, 0),
            rg.Point3d(-t1_val/2, -H/2 + t2_val, 0), rg.Point3d(-B/2, -H/2 + t2_val, 0),
            rg.Point3d(-B/2, -H/2, 0)
        ]
    elif p_type == "C-Channel":
        pts = [
            rg.Point3d(-B/2, -H/2, 0), rg.Point3d(B/2, -H/2, 0),
            rg.Point3d(B/2, -H/2 + t2_val, 0), rg.Point3d(-B/2 + t1_val, -H/2 + t2_val, 0),
            rg.Point3d(-B/2 + t1_val, H/2 - t2_val, 0), rg.Point3d(B/2, H/2 - t2_val, 0),
            rg.Point3d(B/2, H/2, 0), rg.Point3d(-B/2, H/2, 0),
            rg.Point3d(-B/2, -H/2, 0)
        ]
    elif p_type == "L-Plate":
        pts = [
            rg.Point3d(-B/2, -H/2, 0), rg.Point3d(B/2, -H/2, 0),
            rg.Point3d(B/2, -H/2 + t2_val, 0), rg.Point3d(-B/2 + t1_val, -H/2 + t2_val, 0),
            rg.Point3d(-B/2 + t1_val, H/2, 0), rg.Point3d(-B/2, H/2, 0),
            rg.Point3d(-B/2, -H/2, 0)
        ]
    elif p_type == "T-Beam":
        # T형강도 외적 연산을 위해 완벽한 CCW 순서로 재정렬
        pts = [
            rg.Point3d(-t1_val/2, -H/2, 0), rg.Point3d(t1_val/2, -H/2, 0),
            rg.Point3d(t1_val/2, H/2 - t2_val, 0), rg.Point3d(B/2, H/2 - t2_val, 0),
            rg.Point3d(B/2, H/2, 0), rg.Point3d(-B/2, H/2, 0),
            rg.Point3d(-B/2, H/2 - t2_val, 0), rg.Point3d(-t1_val/2, H/2 - t2_val, 0),
            rg.Point3d(-t1_val/2, -H/2, 0)
        ]

    curve_pts = [plane.PointAt(p.X, p.Y, 0) for p in pts]
    
    # ---------------------------------------------------------------------
    # [핵심] 지능형 안쪽 모서리(Inner Corner) 추적 및 Arc 삽입 엔진
    # ---------------------------------------------------------------------
    if r_val <= 0.001:
        # r값이 없으면 기존처럼 직선형 프로파일 생성
        curve = rg.Polyline(curve_pts).ToNurbsCurve()
    else:
        corners = []
        n = len(curve_pts) - 1
        
        for i in range(n):
            p_curr = curve_pts[i]
            p_prev = curve_pts[i-1]
            p_next = curve_pts[(i+1)%n]
            
            v_in = p_curr - p_prev
            v_out = p_next - p_curr
            v_in.Unitize()
            v_out.Unitize()
            
            # 벡터 외적을 통해 안쪽 코너 판별 (진행 방향 대비 우회전하는 곳)
            cross_vec = rg.Vector3d.CrossProduct(v_in, v_out)
            z_dot = cross_vec * plane.ZAxis
            
            if z_dot < -0.5: # 안쪽 모서리(Inner Corner) 감지됨!
                p_start = p_curr - v_in * r_val
                p_end = p_curr + v_out * r_val
                arc = rg.Arc(p_start, v_in, p_end)
                corners.append({'type': 'fillet', 'p_start': p_start, 'p_end': p_end, 'arc': arc})
            else: # 바깥쪽 모서리는 직각(Sharp) 유지
                corners.append({'type': 'sharp', 'p_start': p_curr, 'p_end': p_curr})
                
        polycurve = rg.PolyCurve()
        for i in range(n):
            c_curr = corners[i]
            c_next = corners[(i+1)%n]
            
            if c_curr['type'] == 'fillet':
                polycurve.Append(c_curr['arc'])
                
            line = rg.Line(c_curr['p_end'], c_next['p_start'])
            if line.Length > 0.001:
                polycurve.Append(line)
                
        if not polycurve.IsClosed:
            polycurve.MakeClosed(0.001)
            
        curve = polycurve.ToNurbsCurve()
    # ---------------------------------------------------------------------

    curve.Translate(-plane.ZAxis * (L / 2))
    srf = rg.Surface.CreateExtrusion(curve, plane.ZAxis * L)
    
    if srf:
        brep_ext = srf.ToBrep()
        cap = brep_ext.CapPlanarHoles(sc.doc.ModelAbsoluteTolerance)
        final_brep = cap if cap else brep_ext
        return final_brep, gizmo_plane, max(B, H) 
    return None, None, None

# -------------------------------------------------------------------------
# 3. 프리뷰 컨두잇 (철골 부재 + 직관적인 3D 축 기즈모 렌더링)
# -------------------------------------------------------------------------
class SteelPreviewConduit(Rhino.Display.DisplayConduit):
    def __init__(self):
        self.breps = []
        self.gizmo_breps = [] 
        self.gizmo_texts = [] 
        
        self.color = System.Drawing.Color.FromArgb(180, 100, 150, 200)
        self.material = Rhino.Display.DisplayMaterial(self.color)
        
        self.mat_x = Rhino.Display.DisplayMaterial(System.Drawing.Color.Red)
        self.mat_y = Rhino.Display.DisplayMaterial(System.Drawing.Color.LimeGreen)
        self.mat_z = Rhino.Display.DisplayMaterial(System.Drawing.Color.DodgerBlue)
        self.mat_w = Rhino.Display.DisplayMaterial(System.Drawing.Color.White)
        
    def CalculateBoundingBox(self, e):
        for b in self.breps:
            e.IncludeBoundingBox(b.GetBoundingBox(False))
        for gb, _ in self.gizmo_breps:
            e.IncludeBoundingBox(gb.GetBoundingBox(False))
            
    def DrawForeground(self, e):
        for b in self.breps:
            e.Display.DrawBrepShaded(b, self.material)
            e.Display.DrawBrepWires(b, System.Drawing.Color.Black, 1)

        try: e.Display.DepthTestingEnabled = False
        except: pass

        for gb, mat in self.gizmo_breps:
            e.Display.DrawBrepShaded(gb, mat)
            
        for txt, color, pt in self.gizmo_texts:
            e.Display.Draw2dText(txt, color, pt, True, 24) 
            
        try: e.Display.DepthTestingEnabled = True
        except: pass

# -------------------------------------------------------------------------
# 4. UI 및 컨트롤러 (Eto.Forms)
# -------------------------------------------------------------------------
class SteelConverterDialog(forms.Form):
    def __init__(self):
        forms.Form.__init__(self) 
        
        self.Title = "철골 생성기"
        self.ClientSize = drawing.Size(320, 570) 
        self.Padding = drawing.Padding(10)
        self.Resizable = True
        self.Topmost = True
        
        try:
            self.script_dir = os.path.dirname(os.path.realpath(__file__))
        except NameError:
            self.script_dir = None
        
        self.gizmo_radius_factor = 0.04
        self.gizmo_height_factor = 1.0   
        self.gizmo_text_offset = 1.2     
        self.gizmo_min_size = 400        
        self.gizmo_max_size = 400       
        
        self.original_breps = []
        self.original_ids = []
        self.edit_mode = False
        self.edit_settings = None
        self.edit_output_ids = []
        self.source_ids = []
        self.output_layer = None
        
        self.angle_x = 0
        self.angle_y = 0
        self.angle_z = 0
        self.custom_length = None 
        self.custom_B = None
        self.custom_H = None
        
        self.conduit = SteelPreviewConduit()
        self.conduit.Enabled = False
        
    def SetupData(self, original_breps, original_ids, edit_settings=None, edit_output_ids=None, source_ids=None, output_layer=None):
        self.original_breps = original_breps
        self.original_ids = original_ids
        self.edit_settings = edit_settings
        self.edit_mode = edit_settings is not None
        self.edit_output_ids = edit_output_ids if edit_output_ids else []
        self.source_ids = source_ids if source_ids else []
        self.output_layer = output_layer
        
        self.CreateUI()
        if self.edit_mode:
            self.LoadEditSettings(edit_settings)
            self.btn_ok.Text = "수정"
            self.Title = "철골 수정기"
        else:
            self.LoadSticky()
        
        _, axes = get_obb_data(self.original_breps[0])
        axes_sorted = sorted(axes, key=lambda x: x[1], reverse=True)
        init_L = axes_sorted[0][1]
        init_B = axes_sorted[1][1] if len(axes_sorted) > 1 else 0.0
        init_H = axes_sorted[2][1] if len(axes_sorted) > 2 else 0.0
        if self.custom_length is not None:
            self.lbl_length.Text = "길이: {:.1f} mm".format(float(self.custom_length))
        else:
            self.lbl_length.Text = "인식된 길이: {:.1f} mm".format(init_L)
        self.lbl_xy_auto.Text = "자동 X/Y: {:.1f} / {:.1f} mm".format(init_B, init_H)
        
        self.conduit.Enabled = True
        self.UpdatePreview()
        
    def CreateUI(self):
        layout = forms.DynamicLayout()
        layout.Spacing = drawing.Size(5, 5)

        self.dd_profile = forms.DropDown()
        self.dd_profile.DataStore = ["H-Beam", "C-Channel", "L-Plate", "T-Beam"]
        self.dd_profile.SelectedIndex = 0
        self.dd_profile.SelectedIndexChanged += self.OnUIChange
        layout.AddRow("부재 형상:", self.dd_profile)
        
        self.image_view = forms.ImageView()
        self.image_view.Size = drawing.Size(120, 120) 
        
        img_layout = forms.DynamicLayout()
        img_layout.AddRow(None, self.image_view, None) 
        layout.AddRow(img_layout)
        
        self.num_t1 = forms.NumericStepper(Value=20.0, DecimalPlaces=1, Increment=0.5)
        self.num_t1.ValueChanged += self.OnUIChange
        layout.AddRow("Web 두께 (t1):", self.num_t1)
        
        self.num_t2 = forms.NumericStepper(Value=30.0, DecimalPlaces=1, Increment=0.5)
        self.num_t2.ValueChanged += self.OnUIChange
        layout.AddRow("Flange 두께 (t2):", self.num_t2)
        
        # --- r값 컨트롤러 추가 ---
        self.num_r = forms.NumericStepper(Value=20.0, DecimalPlaces=1, Increment=1.0)
        self.num_r.ValueChanged += self.OnUIChange
        layout.AddRow("Fillet 반경 (r):", self.num_r)
        
        layout.AddRow(None)
        
        layout.AddRow(forms.Label(Text="📏 형상 길이 보정:"))
        self.lbl_length = forms.Label(Text="길이: 계산 대기중...")
        btn_reset_len = forms.Button(Text="길이 재설정")
        btn_reset_len.Click += self.OnResetLengthClick
        layout.AddRow(self.lbl_length, btn_reset_len)

        layout.AddRow(None)
        layout.AddRow(forms.Label(Text="📐 단면 X/Y 크기 수동 입력:"))
        self.lbl_xy_auto = forms.Label(Text="자동 X/Y: 계산 대기중...")
        layout.AddRow(self.lbl_xy_auto)
        self.txt_custom_b = forms.TextBox(Text="")
        self.txt_custom_b.Width = 80
        self.txt_custom_h = forms.TextBox(Text="")
        self.txt_custom_h.Width = 80
        self.txt_custom_b.TextChanged += self.OnManualSizeTextChanged
        self.txt_custom_h.TextChanged += self.OnManualSizeTextChanged
        layout.AddRow(forms.Label(Text="X 크기(B):"), self.txt_custom_b, forms.Label(Text="비우면 자동"))
        layout.AddRow(forms.Label(Text="Y 크기(H):"), self.txt_custom_h, forms.Label(Text="비우면 자동"))

        layout.AddRow(None)
        
        layout.AddRow(forms.Label(Text="📐 방향 제어 (축 회전):"))
        btn_rot_x = forms.Button(Text="🔄 X축 회전")
        btn_rot_x.Click += self.OnRotX
        self.lbl_rot_x = forms.Label(Text="0도")
        layout.AddRow(btn_rot_x, self.lbl_rot_x)
        
        btn_rot_y = forms.Button(Text="🔄 Y축 회전")
        btn_rot_y.Click += self.OnRotY
        self.lbl_rot_y = forms.Label(Text="0도")
        layout.AddRow(btn_rot_y, self.lbl_rot_y)
        
        btn_rot_z = forms.Button(Text="🔄 Z축 회전")
        btn_rot_z.Click += self.OnRotZ
        self.lbl_rot_z = forms.Label(Text="0도")
        layout.AddRow(btn_rot_z, self.lbl_rot_z)
        
        self.btn_ok = forms.Button(Text="확인")
        self.btn_ok.Click += self.OnOKClick
        self.btn_cancel = forms.Button(Text="취소")
        self.btn_cancel.Click += self.OnCancelClick
        
        btn_layout = forms.DynamicLayout(DefaultSpacing=drawing.Size(5, 5))
        btn_layout.AddRow(self.btn_ok, self.btn_cancel)
        layout.AddRow(btn_layout)

        layout.AddRow(None)
        
        self.Content = layout

    def UpdateProfileImage(self):
        if not self.script_dir: return 
        
        file_map = {
            "H-Beam": "H-Beam.png",
            "C-Channel": "C-Channel.png",
            "L-Plate": "L-Plate.png",
            "T-Beam": "T-Beam.png"
        }
        
        sel_val = self.dd_profile.SelectedValue
        file_name = file_map.get(sel_val, "")
        img_path = os.path.join(self.script_dir, "icons", file_name)
        
        if os.path.exists(img_path):
            try:
                self.image_view.Image = drawing.Bitmap(img_path)
            except Exception as e:
                print("이미지 렌더링 오류:", e)
        else:
            self.image_view.Image = None 

    def OnResetLengthClick(self, sender, e):
        self.Visible = False
        try:
            pt1 = rs.GetPoint("길이의 '시작점'을 클릭하세요.")
            if pt1:
                pt2 = rs.GetPoint("길이의 '끝점'을 클릭하세요.", pt1)
                if pt2:
                    dist = pt1.DistanceTo(pt2)
                    self.custom_length = dist 
                    self.lbl_length.Text = "길이: {:.1f} mm".format(dist)
        except Exception as ex:
            print(ex)
        finally:
            self.Visible = True
            self.UpdatePreview()

    def _parse_optional_float(self, text):
        try:
            if text is None: return None
            text = str(text).strip()
            if text == "": return None
            value = float(text)
            if value <= 0: return None
            return value
        except:
            return None

    def OnManualSizeTextChanged(self, sender, e):
        self.custom_B = self._parse_optional_float(self.txt_custom_b.Text)
        self.custom_H = self._parse_optional_float(self.txt_custom_h.Text)
        self.UpdatePreview()

    def LoadSticky(self):
        if "Steel_Type" in sc.sticky: self.dd_profile.SelectedIndex = sc.sticky["Steel_Type"]
        if "Steel_t1" in sc.sticky: self.num_t1.Value = sc.sticky["Steel_t1"]
        if "Steel_t2" in sc.sticky: self.num_t2.Value = sc.sticky["Steel_t2"]
        if "Steel_r" in sc.sticky: self.num_r.Value = sc.sticky["Steel_r"] # r값 불러오기
        if "Steel_RotX" in sc.sticky: 
            self.angle_x = sc.sticky["Steel_RotX"]
            self.lbl_rot_x.Text = "{}도".format(self.angle_x)
        if "Steel_RotY" in sc.sticky: 
            self.angle_y = sc.sticky["Steel_RotY"]
            self.lbl_rot_y.Text = "{}도".format(self.angle_y)
        if "Steel_RotZ" in sc.sticky: 
            self.angle_z = sc.sticky["Steel_RotZ"]
            self.lbl_rot_z.Text = "{}도".format(self.angle_z)

    def LoadEditSettings(self, settings):
        if not settings: return
        self.dd_profile.SelectedIndex = int(settings.get("profile_index", 0))
        self.num_t1.Value = float(settings.get("t1", 20.0))
        self.num_t2.Value = float(settings.get("t2", 30.0))
        self.num_r.Value = float(settings.get("r", 20.0))
        self.angle_x = int(settings.get("rot_x", 0))
        self.angle_y = int(settings.get("rot_y", 0))
        self.angle_z = int(settings.get("rot_z", 0))
        self.custom_length = settings.get("custom_length", None)
        self.custom_B = settings.get("custom_b", None)
        self.custom_H = settings.get("custom_h", None)
        if self.custom_B is not None:
            self.txt_custom_b.Text = "{:.1f}".format(float(self.custom_B))
        if self.custom_H is not None:
            self.txt_custom_h.Text = "{:.1f}".format(float(self.custom_H))
        self.lbl_rot_x.Text = "{}도".format(self.angle_x)
        self.lbl_rot_y.Text = "{}도".format(self.angle_y)
        self.lbl_rot_z.Text = "{}도".format(self.angle_z)

    def CurrentSettings(self):
        return {
            "profile_index": int(self.dd_profile.SelectedIndex),
            "t1": float(self.num_t1.Value),
            "t2": float(self.num_t2.Value),
            "r": float(self.num_r.Value),
            "rot_x": int(self.angle_x),
            "rot_y": int(self.angle_y),
            "rot_z": int(self.angle_z),
            "custom_length": self.custom_length,
            "custom_b": self.custom_B,
            "custom_h": self.custom_H
        }

    def SaveSticky(self):
        sc.sticky["Steel_Type"] = self.dd_profile.SelectedIndex
        sc.sticky["Steel_t1"] = self.num_t1.Value
        sc.sticky["Steel_t2"] = self.num_t2.Value
        sc.sticky["Steel_r"] = self.num_r.Value # r값 저장
        sc.sticky["Steel_RotX"] = self.angle_x
        sc.sticky["Steel_RotY"] = self.angle_y
        sc.sticky["Steel_RotZ"] = self.angle_z

    def OnUIChange(self, sender, e):
        self.UpdatePreview()

    def OnRotX(self, sender, e):
        self.angle_x = (self.angle_x + 90) % 360
        self.lbl_rot_x.Text = "{}도".format(self.angle_x)
        self.UpdatePreview()
        
    def OnRotY(self, sender, e):
        self.angle_y = (self.angle_y + 90) % 360
        self.lbl_rot_y.Text = "{}도".format(self.angle_y)
        self.UpdatePreview()
        
    def OnRotZ(self, sender, e):
        self.angle_z = (self.angle_z + 90) % 360
        self.lbl_rot_z.Text = "{}도".format(self.angle_z)
        self.UpdatePreview()

    def UpdatePreview(self):
        self.UpdateProfileImage() 
        
        p_type = self.dd_profile.SelectedValue
        t1 = self.num_t1.Value
        t2 = self.num_t2.Value
        r = self.num_r.Value # 뷰포트 업데이트 시 r값 전달
        self.custom_B = self._parse_optional_float(self.txt_custom_b.Text)
        self.custom_H = self._parse_optional_float(self.txt_custom_h.Text)
        
        self.conduit.breps = []
        self.conduit.gizmo_breps = []
        self.conduit.gizmo_texts = []
        
        for b in self.original_breps:
            result = generate_steel_member(b, p_type, t1, t2, r, self.angle_x, self.angle_y, self.angle_z, self.custom_length, self.custom_B, self.custom_H)
            
            if result and result[0]:
                steel_brep, gizmo_plane, max_dim = result
                self.conduit.breps.append(steel_brep)
                
                size = max_dim * 1.5
                if size < self.gizmo_min_size: size = self.gizmo_min_size
                elif size > self.gizmo_max_size: size = self.gizmo_max_size 
                
                radius = size * self.gizmo_radius_factor   
                cyl_h = size * self.gizmo_height_factor     
                
                sphere = rg.Sphere(gizmo_plane.Origin, radius * 2.0).ToBrep()
                if sphere: self.conduit.gizmo_breps.append((sphere, self.conduit.mat_w))
                
                axes_info = [
                    (gizmo_plane.XAxis, self.conduit.mat_x, System.Drawing.Color.Red, "X"),
                    (gizmo_plane.YAxis, self.conduit.mat_y, System.Drawing.Color.LimeGreen, "Y"),
                    (gizmo_plane.ZAxis, self.conduit.mat_z, System.Drawing.Color.DodgerBlue, "Z")
                ]
                
                for vec, mat, color, text in axes_info:
                    cyl_plane = rg.Plane(gizmo_plane.Origin, vec)
                    cyl = rg.Cylinder(rg.Circle(cyl_plane, radius), cyl_h).ToBrep(True, True)
                    if cyl: self.conduit.gizmo_breps.append((cyl, mat))
                    
                    text_pt = gizmo_plane.Origin + vec * (size * self.gizmo_text_offset)
                    self.conduit.gizmo_texts.append((text, color, text_pt))
                    
        sc.doc.Views.Redraw()

    def OnOKClick(self, sender, e):
        self.SaveSticky()
        self.conduit.Enabled = False
        settings = self.CurrentSettings()
        new_output_ids = []

        for i, b in enumerate(self.conduit.breps):
            if not b: continue

            if self.edit_mode:
                if self.edit_settings and self.edit_settings.get("steel_id", None):
                    steel_id = self.edit_settings.get("steel_id")
                else:
                    steel_id = str(uuid.uuid4())
                source_id = self.source_ids[i] if i < len(self.source_ids) else (self.source_ids[0] if self.source_ids else None)
                if not source_id:
                    source_id = _make_hidden_source_copy(self.original_breps[i], steel_id)
            else:
                steel_id = str(uuid.uuid4())
                source_id = _make_hidden_source_copy(self.original_breps[i], steel_id)

            obj_id = sc.doc.Objects.AddBrep(b)
            if obj_id and obj_id != System.Guid.Empty:
                if self.output_layer and rs.IsLayer(self.output_layer):
                    try: rs.ObjectLayer(obj_id, self.output_layer)
                    except: pass
                if source_id:
                    _write_steel_settings(obj_id, steel_id, source_id, settings)
                new_output_ids.append(obj_id)

        if self.edit_mode:
            for old_id in self.edit_output_ids:
                try: sc.doc.Objects.Delete(System.Guid(str(old_id)), True)
                except:
                    try: sc.doc.Objects.Delete(old_id, True)
                    except: pass
        else:
            for bid in self.original_ids:
                try: sc.doc.Objects.Delete(bid, True)
                except: pass

        sc.doc.Views.Redraw()
        self.Close()

    def OnCancelClick(self, sender, e):
        self.conduit.Enabled = False
        sc.doc.Views.Redraw()
        self.Close()
        
    def OnClosed(self, e):
        self.conduit.Enabled = False
        sc.doc.Views.Redraw()
        super(SteelConverterDialog, self).OnClosed(e)

# -------------------------------------------------------------------------
# 5. 실행 함수
# -------------------------------------------------------------------------
def _open_dialog_for_new(obj_ids):
    breps = [rs.coercebrep(id) for id in obj_ids]
    breps = [b for b in breps if b]
    if not breps: return

    dialog = SteelConverterDialog()
    dialog.SetupData(breps, obj_ids)
    dialog.Owner = Rhino.UI.RhinoEtoApp.MainWindow
    dialog.Show()

def _open_dialog_for_edit(selected_id):
    settings = _read_steel_settings(selected_id)
    if not settings:
        return False

    source_id = settings.get("source_id", None)
    source_brep = _get_brep_from_id(source_id)
    if not source_brep:
        rs.MessageBox("편집용 기준 박스 정보를 찾을 수 없습니다.\n이 객체는 다시 수정할 수 없습니다.", 0, "수정 오류")
        return True

    steel_id = settings.get("steel_id")
    output_ids = _find_output_ids_by_steel_id(steel_id)
    if not output_ids:
        output_ids = [selected_id]

    try:
        output_layer = rs.ObjectLayer(selected_id)
    except:
        output_layer = None

    dialog = SteelConverterDialog()
    dialog.SetupData([source_brep], [], edit_settings=settings, edit_output_ids=output_ids, source_ids=[source_id], output_layer=output_layer)
    dialog.Owner = Rhino.UI.RhinoEtoApp.MainWindow
    dialog.Show()
    return True

def main():
    go = Rhino.Input.Custom.GetObject()
    go.SetCommandPrompt("수정할 철골 부재를 선택하거나, 변환할 직육면체를 선택하세요")
    go.GeometryFilter = Rhino.DocObjects.ObjectType.Brep
    go.SubObjectSelect = False
    go.EnablePreSelect(False, True)

    opt_draw = go.AddOption("Draw3PointBox")
    opt_multi = go.AddOption("SelectMultipleBoxes")

    get_rc = go.Get()

    if get_rc == Rhino.Input.GetResult.Option:
        if go.Option().Index == opt_draw:
            rs.UnselectAllObjects()
            rs.Command("-_Box _3Point Pause Pause Pause Pause")
            new_objs = rs.LastCreatedObjects()
            if new_objs:
                _open_dialog_for_new(new_objs)
            else:
                print("박스 생성이 취소되었거나 실패했습니다.")
            return

        elif go.Option().Index == opt_multi:
            rs.UnselectAllObjects()
            obj_ids = rs.GetObjects("변환할 직육면체들을 선택하세요.", rs.filter.polysurface)
            if obj_ids:
                _open_dialog_for_new(obj_ids)
            return

    elif get_rc == Rhino.Input.GetResult.Object:
        obj_ref = go.Object(0)
        obj_id = obj_ref.ObjectId

        if _open_dialog_for_edit(obj_id):
            return

        brep = obj_ref.Brep()
        if not brep:
            rs.MessageBox("선택한 객체에서 Brep 정보를 읽을 수 없습니다.", 0, "선택 오류")
            return

        if len(list(brep.Faces)) != 6:
            rs.MessageBox("이 객체에는 편집용 데이터가 없습니다.\n새 철골 부재로 변환하려면 6면 직육면체를 선택하거나 Draw3PointBox 옵션을 사용하세요.", 0, "선택 오류")
            return

        _open_dialog_for_new([obj_id])
        return

    return

if __name__ == "__main__":
    main()