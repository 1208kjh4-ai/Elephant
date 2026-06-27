# -*- coding: utf-8 -*-
import Rhino
import Rhino.Geometry as rg
import scriptcontext as sc
import Eto.Forms as forms
import Eto.Drawing as drawing
import math
import rhinoscriptsyntax as rs
import System

# -------------------------------------------------------------------------
# 1. 기하학 엔진: 직육면체(Brep)에서 OBB(회전된 바운딩 박스) 추출
# -------------------------------------------------------------------------
def get_obb_from_box(brep):
    """직육면체에서 기준 평면(Plane)과 3축 길이(Extrusion, X, Y)를 추출합니다."""
    # 만약 정육면체/직육면체(6면)가 아닐 경우 월드 좌표 바운딩 박스로 임시 대체
    faces = list(brep.Faces)
    if len(faces) != 6:
        bbox = brep.GetBoundingBox(True)
        return rg.Plane.WorldXY, bbox.Max.Z - bbox.Min.Z, bbox.Max.X - bbox.Min.X, bbox.Max.Y - bbox.Min.Y

    # [에러 수정된 부분] 꼭짓점(Vertex)에서 연결된 엣지의 "인덱스"를 먼저 찾은 후 객체로 변환합니다.
    v = brep.Vertices[0]
    edge_indices = v.EdgeIndices()
    edges = [brep.Edges[idx] for idx in edge_indices]

    if len(edges) != 3:
        bbox = brep.GetBoundingBox(True)
        return rg.Plane.WorldXY, bbox.Max.Z - bbox.Min.Z, bbox.Max.X - bbox.Min.X, bbox.Max.Y - bbox.Min.Y

    v_pt = v.Location
    e_data = []
    for e in edges:
        crv = e.ToNurbsCurve()
        length = crv.GetLength()
        # 점의 위치에 따라 벡터 방향 보정
        if crv.PointAtStart.DistanceTo(v_pt) < 0.001:
            vec = crv.TangentAtStart
        else:
            vec = -crv.TangentAtEnd
        e_data.append((length, vec))

    # 가장 긴 길이를 압출 방향(Z축)으로 설정하기 위해 정렬
    e_data.sort(key=lambda x: x[0], reverse=True)
    long_len, long_vec = e_data[0]
    dim_x, vec_x = e_data[1]
    dim_y, vec_y = e_data[2]

    # 중심점 계산
    amp = rg.AreaMassProperties.Compute(brep)
    center = amp.Centroid if amp else brep.GetBoundingBox(True).Center

    # 프로파일이 그려질 평면(Plane) 생성
    plane = rg.Plane(center, vec_x, vec_y)
    # 평면의 Z축이 가장 긴 벡터(long_vec)와 일치하도록 방향 조정
    if plane.ZAxis * long_vec < 0:
        plane = rg.Plane(center, vec_y, vec_x)
        dim_x, dim_y = dim_y, dim_x

    return plane, long_len, dim_x, dim_y

# -------------------------------------------------------------------------
# 2. 기하학 엔진: 단면 커브 생성 및 솔리드 압출
# -------------------------------------------------------------------------
def generate_steel_member(brep, p_type, t1, t2, flip_x, flip_y, angle):
    # 1. 박스에서 방향과 치수 추출
    plane, length, dim_x, dim_y = get_obb_from_box(brep)
    
    # 2. 각도(0, 90, 180, 270)에 따라 H(높이)와 B(폭) 매칭
    # 90도 돌아가면 박스의 가로/세로 매칭이 바뀜
    if angle % 180 == 0:
        B, H = dim_x, dim_y
    else:
        B, H = dim_y, dim_x

    # 기하학 오류 방지: 두께가 폭/높이보다 크지 않게 제한
    t1 = min(t1, B * 0.9)
    t2 = min(t2, H * 0.45)

    pts = []
    # 단면 2D 점 좌표 생성 (중심 0,0 기준)
    if p_type == "H형강 (H-Beam)":
        pts = [
            rg.Point3d(-B/2, -H/2, 0), rg.Point3d(B/2, -H/2, 0),
            rg.Point3d(B/2, -H/2 + t2, 0), rg.Point3d(t1/2, -H/2 + t2, 0),
            rg.Point3d(t1/2, H/2 - t2, 0), rg.Point3d(B/2, H/2 - t2, 0),
            rg.Point3d(B/2, H/2, 0), rg.Point3d(-B/2, H/2, 0),
            rg.Point3d(-B/2, H/2 - t2, 0), rg.Point3d(-t1/2, H/2 - t2, 0),
            rg.Point3d(-t1/2, -H/2 + t2, 0), rg.Point3d(-B/2, -H/2 + t2, 0),
            rg.Point3d(-B/2, -H/2, 0)
        ]
    elif p_type == "ㄷ형강 (C-Channel)":
        pts = [
            rg.Point3d(-B/2, -H/2, 0), rg.Point3d(B/2, -H/2, 0),
            rg.Point3d(B/2, -H/2 + t2, 0), rg.Point3d(-B/2 + t1, -H/2 + t2, 0),
            rg.Point3d(-B/2 + t1, H/2 - t2, 0), rg.Point3d(B/2, H/2 - t2, 0),
            rg.Point3d(B/2, H/2, 0), rg.Point3d(-B/2, H/2, 0),
            rg.Point3d(-B/2, -H/2, 0)
        ]
    elif p_type == "L형강 (L-Plate)":
        pts = [
            rg.Point3d(-B/2, -H/2, 0), rg.Point3d(B/2, -H/2, 0),
            rg.Point3d(B/2, -H/2 + t2, 0), rg.Point3d(-B/2 + t1, -H/2 + t2, 0),
            rg.Point3d(-B/2 + t1, H/2, 0), rg.Point3d(-B/2, H/2, 0),
            rg.Point3d(-B/2, -H/2, 0)
        ]

    # 3. Flip 적용 (X축, Y축 반전)
    if flip_x:
        for p in pts: p.X = -p.X
    if flip_y:
        for p in pts: p.Y = -p.Y

    # 4. Rotation 90도 단위 회전 적용
    rad = math.radians(angle)
    for p in pts:
        nx = p.X * math.cos(rad) - p.Y * math.sin(rad)
        ny = p.X * math.sin(rad) + p.Y * math.cos(rad)
        p.X, p.Y = nx, ny

    # 5. 3D 평면으로 변환
    curve_pts = [plane.PointAt(p.X, p.Y, 0) for p in pts]
    polyline = rg.Polyline(curve_pts)
    curve = polyline.ToNurbsCurve()

    # 6. 박스 전체 길이만큼 압출 (중앙 기준이므로 -Z 방향으로 절반 이동 후 압출)
    curve.Translate(-plane.ZAxis * (length / 2))
    srf = rg.Surface.CreateExtrusion(curve, plane.ZAxis * length)
    if srf:
        brep_ext = srf.ToBrep()
        cap = brep_ext.CapPlanarHoles(sc.doc.ModelAbsoluteTolerance)
        return cap if cap else brep_ext
    return None

# -------------------------------------------------------------------------
# 3. 프리뷰 컨두잇 (실시간 시각화)
# -------------------------------------------------------------------------
class SteelPreviewConduit(Rhino.Display.DisplayConduit):
    def __init__(self):
        self.breps = []
        self.color = System.Drawing.Color.FromArgb(180, 100, 150, 200) # 철골 느낌의 푸른 회색
        self.material = Rhino.Display.DisplayMaterial(self.color)
        
    def CalculateBoundingBox(self, e):
        for b in self.breps:
            e.IncludeBoundingBox(b.GetBoundingBox(False))
            
    def DrawForeground(self, e):
        for b in self.breps:
            e.Display.DrawBrepShaded(b, self.material)
            e.Display.DrawBrepWires(b, System.Drawing.Color.Black, 1)

# -------------------------------------------------------------------------
# 4. UI 및 컨트롤러 (Eto.Forms)
# -------------------------------------------------------------------------
class SteelConverterDialog(forms.Form):
    def __init__(self):
        # [수정 1] 인자 없이 부모 클래스(.NET)를 아주 깨끗하게 먼저 초기화합니다.
        forms.Form.__init__(self) 
        
        self.Title = "철골 부재 자동 변환기"
        self.ClientSize = drawing.Size(350, 320)
        self.Padding = drawing.Padding(10)
        self.Resizable = False
        
        # 빈 값으로 초기 세팅
        self.original_breps = []
        self.original_ids = []
        self.current_angle = 0
        
        self.conduit = SteelPreviewConduit()
        self.conduit.Enabled = False # 프리뷰는 잠시 꺼둡니다.
        
    # [수정 2] 데이터를 안전하게 팝업창 안으로 밀어넣고 UI를 켜는 전용 함수 추가
    def SetupData(self, original_breps, original_ids):
        self.original_breps = original_breps
        self.original_ids = original_ids
        
        self.CreateUI()
        self.LoadSticky() # 이전 설정값 불러오기
        
        self.conduit.Enabled = True # 데이터가 들어왔으니 프리뷰 가동
        self.UpdatePreview()
        
    def CreateUI(self):
        layout = forms.DynamicLayout()
        layout.Spacing = drawing.Size(5, 5)

        # 프로파일 타입
        self.dd_profile = forms.DropDown()
        self.dd_profile.DataStore = ["H형강 (H-Beam)", "ㄷ형강 (C-Channel)", "L형강 (L-Plate)"]
        self.dd_profile.SelectedIndex = 0
        self.dd_profile.SelectedIndexChanged += self.OnUIChange
        layout.AddRow("부재 프로파일:", self.dd_profile)
        
        # 두께 설정
        self.num_t1 = forms.NumericStepper(Value=6.5, DecimalPlaces=1, Increment=0.5)
        self.num_t1.ValueChanged += self.OnUIChange
        layout.AddRow("Web 두께 (t1):", self.num_t1)
        
        self.num_t2 = forms.NumericStepper(Value=9.0, DecimalPlaces=1, Increment=0.5)
        self.num_t2.ValueChanged += self.OnUIChange
        layout.AddRow("Flange 두께 (t2):", self.num_t2)
        
        # [수정된 부분] AddSeparator()를 삭제하고 빈 행으로 여백(여유 공간)을 생성합니다.
        layout.AddRow(None)
        
        # 방향 제어
        self.lbl_angle = forms.Label(Text="현재 회전각: 0도")
        self.btn_rotate = forms.Button(Text="🔄 90도 회전하기")
        self.btn_rotate.Click += self.OnRotateClick
        layout.AddRow(self.lbl_angle, self.btn_rotate)
        
        self.chk_flip_x = forms.CheckBox(Text="X축 뒤집기 (Flip X)")
        self.chk_flip_x.CheckedChanged += self.OnUIChange
        self.chk_flip_y = forms.CheckBox(Text="Y축 뒤집기 (Flip Y)")
        self.chk_flip_y.CheckedChanged += self.OnUIChange
        layout.AddRow(self.chk_flip_x, self.chk_flip_y)
        
        layout.AddRow(None)
        
        # 버튼
        self.btn_ok = forms.Button(Text="생성 및 원본 교체")
        self.btn_ok.Click += self.OnOKClick
        self.btn_cancel = forms.Button(Text="취소")
        self.btn_cancel.Click += self.OnCancelClick
        
        btn_layout = forms.DynamicLayout(DefaultSpacing=drawing.Size(5, 5))
        btn_layout.AddRow(None, self.btn_ok, self.btn_cancel)
        layout.AddRow(btn_layout)
        
        self.Content = layout

    def LoadSticky(self):
        if "Steel_Type" in sc.sticky: self.dd_profile.SelectedIndex = sc.sticky["Steel_Type"]
        if "Steel_t1" in sc.sticky: self.num_t1.Value = sc.sticky["Steel_t1"]
        if "Steel_t2" in sc.sticky: self.num_t2.Value = sc.sticky["Steel_t2"]
        if "Steel_FlipX" in sc.sticky: self.chk_flip_x.Checked = sc.sticky["Steel_FlipX"]
        if "Steel_FlipY" in sc.sticky: self.chk_flip_y.Checked = sc.sticky["Steel_FlipY"]
        if "Steel_Angle" in sc.sticky: 
            self.current_angle = sc.sticky["Steel_Angle"]
            self.lbl_angle.Text = "현재 회전각: {}도".format(self.current_angle)

    def SaveSticky(self):
        sc.sticky["Steel_Type"] = self.dd_profile.SelectedIndex
        sc.sticky["Steel_t1"] = self.num_t1.Value
        sc.sticky["Steel_t2"] = self.num_t2.Value
        sc.sticky["Steel_FlipX"] = self.chk_flip_x.Checked
        sc.sticky["Steel_FlipY"] = self.chk_flip_y.Checked
        sc.sticky["Steel_Angle"] = self.current_angle

    def OnUIChange(self, sender, e):
        self.UpdatePreview()

    def OnRotateClick(self, sender, e):
        self.current_angle = (self.current_angle + 90) % 360
        self.lbl_angle.Text = "현재 회전각: {}도".format(self.current_angle)
        self.UpdatePreview()

    def UpdatePreview(self):
        p_type = self.dd_profile.SelectedValue
        t1 = self.num_t1.Value
        t2 = self.num_t2.Value
        flip_x = self.chk_flip_x.Checked
        flip_y = self.chk_flip_y.Checked
        angle = self.current_angle
        
        self.conduit.breps = []
        for b in self.original_breps:
            steel_brep = generate_steel_member(b, p_type, t1, t2, flip_x, flip_y, angle)
            if steel_brep:
                self.conduit.breps.append(steel_brep)
                
        sc.doc.Views.Redraw()

    def OnOKClick(self, sender, e):
        self.SaveSticky() # 설정값 저장
        self.conduit.Enabled = False
        
        # 1. 새 철골 부재 Bake
        for b in self.conduit.breps:
            sc.doc.Objects.AddBrep(b)
            
        # 2. 원본 가매스(Box) 삭제
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
# 5. 실행 함수 (이 부분을 아래 코드로 교체하세요)
# -------------------------------------------------------------------------
def main():
    # 1. 사용자에게 직육면체 다중 선택 받기
    obj_ids = rs.GetObjects("철골 부재로 변환할 직육면체(가매스)들을 모두 선택하세요.", rs.filter.polysurface)
    if not obj_ids: return

    breps = [rs.coercebrep(id) for id in obj_ids]
    
    # 2. 다이얼로그 실행 [수정됨]
    # ShowModal() 대신 윈도우 인스턴스를 직접 보여주는 방식으로 변경합니다.
    dialog = SteelConverterDialog()
    dialog.SetupData(breps, obj_ids)
    
    # Show()를 사용하면 환경 설정에 상관없이 무조건 팝업이 출력됩니다.
    dialog.Topmost = True  # 항상 위에 표시
    dialog.Show()

if __name__ == "__main__":
    main()