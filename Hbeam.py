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
def generate_steel_member(brep, p_type, t1, t2, r, ax, ay, az, custom_length=None):
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
        
    if custom_length is not None:
        L = custom_length

    if B < 0.001 or H < 0.001 or L < 0.001: return None, None, None
    
    t1_val = min(t1, B * 0.9)
    t2_val = min(t2, H * 0.45)
    
    # ---------------------------------------------------------------------
    # r값이 형태를 파고들지 않도록 안전 한계선(Clamp) 자동 계산
    # ---------------------------------------------------------------------
    max_r = 0
    if p_type == "H형강 (H-Beam)":
        max_r = min((H - 2*t2_val)/2.0, (B - t1_val)/2.0)
    elif p_type == "ㄷ형강 (C-Channel)":
        max_r = min((H - 2*t2_val)/2.0, B - t1_val)
    elif p_type == "L형강 (L-Plate)":
        max_r = min(H - t2_val, B - t1_val)
    elif p_type == "T형강 (T-Beam)":
        max_r = min(H - t2_val, (B - t1_val)/2.0)
        
    # 버그를 막기 위해 최대 허용치의 98%까지만 허용
    r_val = min(r, max_r * 0.98) 
    if r_val < 0: r_val = 0
    
    # ---------------------------------------------------------------------
    # 모든 프로파일은 완벽한 반시계 방향(CCW)으로 좌표점 구성
    # ---------------------------------------------------------------------
    pts = []
    if p_type == "H형강 (H-Beam)":
        pts = [
            rg.Point3d(-B/2, -H/2, 0), rg.Point3d(B/2, -H/2, 0),
            rg.Point3d(B/2, -H/2 + t2_val, 0), rg.Point3d(t1_val/2, -H/2 + t2_val, 0),
            rg.Point3d(t1_val/2, H/2 - t2_val, 0), rg.Point3d(B/2, H/2 - t2_val, 0),
            rg.Point3d(B/2, H/2, 0), rg.Point3d(-B/2, H/2, 0),
            rg.Point3d(-B/2, H/2 - t2_val, 0), rg.Point3d(-t1_val/2, H/2 - t2_val, 0),
            rg.Point3d(-t1_val/2, -H/2 + t2_val, 0), rg.Point3d(-B/2, -H/2 + t2_val, 0),
            rg.Point3d(-B/2, -H/2, 0)
        ]
    elif p_type == "ㄷ형강 (C-Channel)":
        pts = [
            rg.Point3d(-B/2, -H/2, 0), rg.Point3d(B/2, -H/2, 0),
            rg.Point3d(B/2, -H/2 + t2_val, 0), rg.Point3d(-B/2 + t1_val, -H/2 + t2_val, 0),
            rg.Point3d(-B/2 + t1_val, H/2 - t2_val, 0), rg.Point3d(B/2, H/2 - t2_val, 0),
            rg.Point3d(B/2, H/2, 0), rg.Point3d(-B/2, H/2, 0),
            rg.Point3d(-B/2, -H/2, 0)
        ]
    elif p_type == "L형강 (L-Plate)":
        pts = [
            rg.Point3d(-B/2, -H/2, 0), rg.Point3d(B/2, -H/2, 0),
            rg.Point3d(B/2, -H/2 + t2_val, 0), rg.Point3d(-B/2 + t1_val, -H/2 + t2_val, 0),
            rg.Point3d(-B/2 + t1_val, H/2, 0), rg.Point3d(-B/2, H/2, 0),
            rg.Point3d(-B/2, -H/2, 0)
        ]
    elif p_type == "T형강 (T-Beam)":
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
        
        self.Title = "철골 부재 3축 변환기"
        self.ClientSize = drawing.Size(350, 520) 
        self.Padding = drawing.Padding(10)
        self.Resizable = False
        self.Topmost = True
        
        try:
            self.script_dir = os.path.dirname(os.path.realpath(__file__))
        except NameError:
            self.script_dir = None
        
        self.gizmo_radius_factor = 0.04
        self.gizmo_height_factor = 1.0   
        self.gizmo_text_offset = 1.2     
        self.gizmo_min_size = 100        
        self.gizmo_max_size = 2000       
        
        self.original_breps = []
        self.original_ids = []
        
        self.angle_x = 0
        self.angle_y = 0
        self.angle_z = 0
        self.custom_length = None 
        
        self.conduit = SteelPreviewConduit()
        self.conduit.Enabled = False
        
    def SetupData(self, original_breps, original_ids):
        self.original_breps = original_breps
        self.original_ids = original_ids
        
        self.CreateUI()
        self.LoadSticky()
        
        _, axes = get_obb_data(self.original_breps[0])
        init_L = max([length for vec, length in axes])
        self.lbl_length.Text = "인식된 길이: {:.1f} mm".format(init_L)
        
        self.conduit.Enabled = True
        self.UpdatePreview()
        
    def CreateUI(self):
        layout = forms.DynamicLayout()
        layout.Spacing = drawing.Size(5, 5)

        self.dd_profile = forms.DropDown()
        self.dd_profile.DataStore = ["H형강 (H-Beam)", "ㄷ형강 (C-Channel)", "L형강 (L-Plate)", "T형강 (T-Beam)"]
        self.dd_profile.SelectedIndex = 0
        self.dd_profile.SelectedIndexChanged += self.OnUIChange
        layout.AddRow("부재 프로파일:", self.dd_profile)
        
        self.image_view = forms.ImageView()
        self.image_view.Size = drawing.Size(120, 120) 
        
        img_layout = forms.DynamicLayout()
        img_layout.AddRow(None, self.image_view, None) 
        layout.AddRow(img_layout)
        
        self.num_t1 = forms.NumericStepper(Value=6.5, DecimalPlaces=1, Increment=0.5)
        self.num_t1.ValueChanged += self.OnUIChange
        layout.AddRow("Web 두께 (t1):", self.num_t1)
        
        self.num_t2 = forms.NumericStepper(Value=9.0, DecimalPlaces=1, Increment=0.5)
        self.num_t2.ValueChanged += self.OnUIChange
        layout.AddRow("Flange 두께 (t2):", self.num_t2)
        
        # --- r값 컨트롤러 추가 ---
        self.num_r = forms.NumericStepper(Value=13.0, DecimalPlaces=1, Increment=1.0)
        self.num_r.ValueChanged += self.OnUIChange
        layout.AddRow("Fillet 반경 (r):", self.num_r)
        
        layout.AddRow(None)
        
        layout.AddRow(forms.Label(Text="📏 압출 길이 보정:"))
        self.lbl_length = forms.Label(Text="인식된 길이: 계산 대기중...")
        btn_reset_len = forms.Button(Text="길이 재설정 (2점 클릭)")
        btn_reset_len.Click += self.OnResetLengthClick
        layout.AddRow(self.lbl_length, btn_reset_len)

        layout.AddRow(None)
        
        layout.AddRow(forms.Label(Text="📐 방향 제어 (축별 회전):"))
        btn_rot_x = forms.Button(Text="🔄 X축 (Red) 회전")
        btn_rot_x.Click += self.OnRotX
        self.lbl_rot_x = forms.Label(Text="0도")
        layout.AddRow(btn_rot_x, self.lbl_rot_x)
        
        btn_rot_y = forms.Button(Text="🔄 Y축 (Green) 회전")
        btn_rot_y.Click += self.OnRotY
        self.lbl_rot_y = forms.Label(Text="0도")
        layout.AddRow(btn_rot_y, self.lbl_rot_y)
        
        btn_rot_z = forms.Button(Text="🔄 Z축 (Blue) 회전")
        btn_rot_z.Click += self.OnRotZ
        self.lbl_rot_z = forms.Label(Text="0도")
        layout.AddRow(btn_rot_z, self.lbl_rot_z)
        
        layout.AddRow(None)
        
        self.btn_ok = forms.Button(Text="생성 및 원본 교체")
        self.btn_ok.Click += self.OnOKClick
        self.btn_cancel = forms.Button(Text="취소")
        self.btn_cancel.Click += self.OnCancelClick
        
        btn_layout = forms.DynamicLayout(DefaultSpacing=drawing.Size(5, 5))
        btn_layout.AddRow(None, self.btn_ok, self.btn_cancel)
        layout.AddRow(btn_layout)
        
        self.Content = layout

    def UpdateProfileImage(self):
        if not self.script_dir: return 
        
        file_map = {
            "H형강 (H-Beam)": "H-Beam.png",
            "ㄷ형강 (C-Channel)": "C-Channel.png",
            "L형강 (L-Plate)": "L-Plate.png",
            "T형강 (T-Beam)": "T-Beam.png"
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
            pt1 = rs.GetPoint("압출할 길이의 '시작점'을 클릭하세요.")
            if pt1:
                pt2 = rs.GetPoint("압출할 길이의 '끝점'을 클릭하세요.", pt1)
                if pt2:
                    dist = pt1.DistanceTo(pt2)
                    self.custom_length = dist 
                    self.lbl_length.Text = "수동 지정: {:.1f} mm".format(dist)
        except Exception as ex:
            print(ex)
        finally:
            self.Visible = True
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
        
        self.conduit.breps = []
        self.conduit.gizmo_breps = []
        self.conduit.gizmo_texts = []
        
        for b in self.original_breps:
            result = generate_steel_member(b, p_type, t1, t2, r, self.angle_x, self.angle_y, self.angle_z, self.custom_length)
            
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
        for b in self.conduit.breps:
            sc.doc.Objects.AddBrep(b)
        for bid in self.original_ids:
            sc.doc.Objects.Delete(bid, True)
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
def main():
    go = Rhino.Input.Custom.GetOption()
    go.SetCommandPrompt("철골 부재를 생성할 기준을 선택하세요")
    op_select = go.AddOption("SelectExisting")
    op_draw = go.AddOption("Draw3PointBox")
    
    get_rc = go.Get()
    
    if get_rc != Rhino.Input.GetResult.Option:
        return
        
    obj_ids = []
    
    if go.Option().EnglishName == "SelectExisting":
        obj_ids = rs.GetObjects("철골 부재로 변환할 직육면체들을 모두 선택하세요.", rs.filter.polysurface)
        if not obj_ids: return
        
    elif go.Option().EnglishName == "Draw3PointBox":
        rs.Command("-_Box _3Point Pause Pause Pause Pause")
        new_objs = rs.LastCreatedObjects()
        if new_objs:
            obj_ids = new_objs
        else:
            print("박스 생성이 취소되었거나 실패했습니다.")
            return

    breps = [rs.coercebrep(id) for id in obj_ids]
    if not breps: return
    
    dialog = SteelConverterDialog()
    dialog.SetupData(breps, obj_ids)
    dialog.Show()

if __name__ == "__main__":
    main()