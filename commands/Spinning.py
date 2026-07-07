# -*- coding: utf-8 -*-
import Rhino
import Rhino.Geometry as rg
import Rhino.Display as rd
import Eto.Forms as forms
import Eto.Drawing as drawing
import rhinoscriptsyntax as rs
import System
import math

# ==============================================================================
# [1] 독립형 미리보기 엔진 (실시간 변화 반영)
# ==============================================================================
class DoorPreviewConduit(rd.DisplayConduit):
    def __init__(self):
        rd.DisplayConduit.__init__(self)
        self.preview_breps = []
        self.frame_mat = rd.DisplayMaterial(System.Drawing.Color.LightGray)
        # 유리를 표현하기 위해 약간 투명한 푸른빛 재질 사용
        self.glass_mat = rd.DisplayMaterial(System.Drawing.Color.AliceBlue)
        self.glass_mat.Transparency = 0.5 

    def DrawForeground(self, e):
        for name, brep in self.preview_breps:
            if brep and brep.IsValid:
                mat = self.glass_mat if name == "glass" else self.frame_mat
                e.Display.DrawBrepShaded(brep, mat)
                e.Display.DrawBrepWires(brep, System.Drawing.Color.Black, 1)

# ==============================================================================
# [2] 회전문 전용 다이얼로그
# ==============================================================================
class RevolvingDoorDialog(forms.Dialog[bool]):
    def __init__(self, base_plane, width, height):
        self.Title = "회전문 세부 설정"
        self.base_plane, self.width, self.height = base_plane, width, height
        self.conduit = DoorPreviewConduit()
        self.conduit.Enabled = True
        
        self.layout = forms.DynamicLayout(Spacing=drawing.Size(5, 8), Padding=20)
        self.SetupUI()
        self.layout.AddRow(None)
        
        btn_ok = forms.Button(Text="생성"); btn_ok.Click += lambda s,e: self.Close(True)
        btn_cancel = forms.Button(Text="취소"); btn_cancel.Click += lambda s,e: self.Close(False)
        self.layout.AddRow(btn_ok, btn_cancel)
        self.Content = self.layout
        
        # 창이 완전히 열린 직후에 프리뷰 강제 업데이트
        self.Shown += lambda s, e: self.UpdatePreview()

    def SetupUI(self):
        # 날개 개수 (3짝 / 4짝)
        self.rb_wings_3 = forms.RadioButton(Text="3짝 (120° 간격)")
        self.rb_wings_4 = forms.RadioButton(self.rb_wings_3, Text="4짝 (90° 간격)")
        self.rb_wings_4.Checked = True
        
        # 치수 입력 텍스트 박스
        self.txt_t = forms.TextBox(Text="40") # 외곽 프레임 두께
        self.txt_pole = forms.TextBox(Text="50") # 중심축 반지름
        self.txt_pframe_t = forms.TextBox(Text="40") # 날개 프레임 두께
        self.txt_d = forms.TextBox(Text="200") # 외곽 프레임 깊이
        
        # 옵션 체크박스
        self.cb_flip = forms.CheckBox(Text="안팎 뒤집기 (Flip)", Checked=False)
        self.cb_union = forms.CheckBox(Text="프레임 결합 (Boolean Union)", Checked=True) 
        
        # 회전 슬라이더 (0~360도)
        self.sli_rot = forms.Slider(MinValue=0, MaxValue=360, Value=0)
        self.lbl_rot = forms.Label(Text="0°")
        
        # 이벤트 연결
        self.rb_wings_3.CheckedChanged += lambda s,e: self.UpdatePreview()
        self.rb_wings_4.CheckedChanged += lambda s,e: self.UpdatePreview()
        self.cb_flip.CheckedChanged += lambda s,e: self.UpdatePreview()
        self.cb_union.CheckedChanged += lambda s,e: self.UpdatePreview()
        self.txt_t.TextChanged += lambda s,e: self.UpdatePreview()
        self.txt_pole.TextChanged += lambda s,e: self.UpdatePreview()
        self.txt_pframe_t.TextChanged += lambda s,e: self.UpdatePreview()
        self.txt_d.TextChanged += lambda s,e: self.UpdatePreview()
        self.sli_rot.ValueChanged += lambda s,e: (setattr(self.lbl_rot, 'Text', str(self.sli_rot.Value)+"°"), self.UpdatePreview())
            
        # 레이아웃 배치
        self.layout.AddRow(forms.Label(Text="날개 개수:"), self.rb_wings_3, self.rb_wings_4)
        self.layout.AddRow(forms.Label(Text="외곽 프레임 두께(mm):"), self.txt_t)
        self.layout.AddRow(forms.Label(Text="외곽 프레임 깊이(mm):"), self.txt_d)
        self.layout.AddRow(forms.Label(Text="중심축 반지름(mm):"), self.txt_pole)
        self.layout.AddRow(forms.Label(Text="날개 프레임 두께(mm):"), self.txt_pframe_t)
        self.layout.AddRow(self.cb_flip, self.cb_union) 
        self.layout.AddRow(forms.Label(Text="문 회전(0~360°):"), self.sli_rot, self.lbl_rot)

    def GetSafeFloat(self, text, default):
        try: return float(text)
        except: return default

    def UpdatePreview(self):
        self.conduit.preview_breps = self.GenerateGeometry()
        Rhino.RhinoDoc.ActiveDoc.Views.Redraw()

    def make_arc_brep(self, center, r_in, r_out, a_start, a_end, z_start, z_end):
        """곡면 프레임(호 형태의 솔리드)를 생성하는 헬퍼 함수"""
        a1 = math.radians(a_start)
        a2 = math.radians(a_end)
        angle = a2 - a1
        
        plane = rg.Plane.WorldXY
        plane.Origin = center
        plane.Rotate(a1, rg.Vector3d.ZAxis) # 시작 각도로 평면 회전
        
        # 두 개의 호와 선을 연결하여 닫힌 커브 생성
        arc_out = rg.Arc(plane, r_out, angle)
        arc_in = rg.Arc(plane, r_in, angle)
        
        c_out = rg.ArcCurve(arc_out)
        c_in = rg.ArcCurve(arc_in)
        c_in.Reverse()
        
        l1 = rg.LineCurve(c_out.PointAtEnd, c_in.PointAtStart)
        l2 = rg.LineCurve(c_in.PointAtEnd, c_out.PointAtStart)
        
        joined = rg.Curve.JoinCurves([c_out, l1, c_in, l2], 0.001)
        if not joined: return None
        
        extrusion = rg.Extrusion.Create(joined[0], z_end - z_start, True)
        if extrusion:
            brep = extrusion.ToBrep()
            if brep:
                brep.Translate(rg.Vector3d(0, 0, z_start))
                return brep
        return None

    def GenerateGeometry(self):
        W, H = self.width, self.height
        T_frame = self.GetSafeFloat(self.txt_t.Text, 40.0)
        D_frame = self.GetSafeFloat(self.txt_d.Text, 200.0)
        R_pole = self.GetSafeFloat(self.txt_pole.Text, 50.0)
        T_pframe = self.GetSafeFloat(self.txt_pframe_t.Text, 40.0)
        T_glass = 10.0
        
        N_wings = 4 if self.rb_wings_4.Checked else 3
        rot_angle = math.radians(self.sli_rot.Value)
        do_union = self.cb_union.Checked
        has_threshold = False # 회전문은 기본적으로 하부 문턱을 생성하지 않음
        
        R = W / 2.0
        # 💡 [수정됨] 중심점의 Y좌표를 0으로 설정하여 회전문을 전체적으로 바깥쪽으로 당김
        center_pt = rg.Point3d(W/2.0, 0, 0)
        
        drum_h = max(100.0, T_frame * 2) # 상단 원형 지붕(Drum)의 높이
        door_h = H - drum_h
        
        parts = []
        tol = Rhino.RhinoDoc.ActiveDoc.ModelAbsoluteTolerance 
        
        # ==========================================
        # [1] 전체 문틀 (외곽 원통 인클로저 및 중심축)
        # ==========================================
        outer_frames = []
        
        # 💡 [수정됨] 직사각형 외곽 프레임도 중심(Y=0)을 기준으로 배치되도록 구간 수정
        iy_outer = rg.Interval(-D_frame/2.0, D_frame/2.0)
        
        outer_frames.append(rg.Box(rg.Plane.WorldXY, rg.Interval(0, T_frame), iy_outer, rg.Interval(0, H)).ToBrep())
        outer_frames.append(rg.Box(rg.Plane.WorldXY, rg.Interval(W - T_frame, W), iy_outer, rg.Interval(0, H)).ToBrep())
        
        if do_union:
            outer_frames.append(rg.Box(rg.Plane.WorldXY, rg.Interval(0, W), iy_outer, rg.Interval(H - T_frame, H)).ToBrep())
        else:
            outer_frames.append(rg.Box(rg.Plane.WorldXY, rg.Interval(T_frame, W - T_frame), iy_outer, rg.Interval(H - T_frame, H)).ToBrep())

        # 상단 원형 지붕 (Drum)
        drum_c = rg.Circle(rg.Plane.WorldXY, center_pt, R)
        drum_ext = rg.Extrusion.Create(drum_c.ToNurbsCurve(), drum_h, True)
        if drum_ext:
            drum_b = drum_ext.ToBrep()
            drum_b.Translate(rg.Vector3d(0, 0, door_h))
            outer_frames.append(drum_b)
            
        # 중심축 (Pole)
        pole_c = rg.Circle(rg.Plane.WorldXY, center_pt, R_pole)
        pole_ext = rg.Extrusion.Create(pole_c.ToNurbsCurve(), door_h + (10 if do_union else 0), True)
        if pole_ext:
            outer_frames.append(pole_ext.ToBrep())

        # 곡면 외벽 (우측: -40~40도, 좌측: 140~220도)
        def add_arc_wall(a_start, a_end):
            # 하부 곡선 프레임 (Union 오버랩 고려)
            h_bottom = T_frame + (1 if do_union else 0)
            b_bottom = self.make_arc_brep(center_pt, R - T_frame, R, a_start, a_end, 0, h_bottom)
            if b_bottom: outer_frames.append(b_bottom)
            
            # 수직 기둥 (양끝)
            b_post1 = self.make_arc_brep(center_pt, R - T_frame, R, a_start, a_start + 2, T_frame, door_h + (10 if do_union else 0))
            if b_post1: outer_frames.append(b_post1)
            b_post2 = self.make_arc_brep(center_pt, R - T_frame, R, a_end - 2, a_end, T_frame, door_h + (10 if do_union else 0))
            if b_post2: outer_frames.append(b_post2)
            
            # 곡면 유리
            mid_r = R - T_frame / 2.0
            g_in = mid_r - T_glass / 2.0
            g_out = mid_r + T_glass / 2.0
            g_b = self.make_arc_brep(center_pt, g_in, g_out, a_start + 2, a_end - 2, T_frame, door_h)
            if g_b: parts.append(("glass", g_b))

        add_arc_wall(-40, 40)   # 우측 외벽
        add_arc_wall(140, 220)  # 좌측 외벽
        
        if do_union and len(outer_frames) > 0:
            unioned_outer = rg.Brep.CreateBooleanUnion(outer_frames, tol)
            if unioned_outer and len(unioned_outer) > 0:
                for b in unioned_outer: parts.append(("frame", b))
            else:
                for b in outer_frames: parts.append(("frame", b))
        else:
            for b in outer_frames: parts.append(("frame", b))

        # ==========================================
        # [2] 회전 날개 (Wings)
        # ==========================================
        def make_box(ix, iy, iz):
            return rg.Box(rg.Plane.WorldXY, ix, iy, iz).ToBrep()
            
        for i in range(N_wings):
            wing_frames = []
            x0 = R_pole
            x1 = R - 10.0 # 외벽과 닿지 않도록 10mm 유격
            
            # 프레임 교차 결합(Union)을 위해 Z축을 교차시킴
            # 하단 프레임
            wing_frames.append(make_box(rg.Interval(x0, x1), rg.Interval(-T_pframe/2, T_pframe/2), rg.Interval(0, T_pframe)))
            # 상단 프레임
            wing_frames.append(make_box(rg.Interval(x0, x1), rg.Interval(-T_pframe/2, T_pframe/2), rg.Interval(door_h - T_pframe, door_h)))
            # 안쪽 세로 프레임
            wing_frames.append(make_box(rg.Interval(x0, x0 + T_pframe), rg.Interval(-T_pframe/2, T_pframe/2), rg.Interval(0, door_h)))
            # 바깥쪽 세로 프레임
            wing_frames.append(make_box(rg.Interval(x1 - T_pframe, x1), rg.Interval(-T_pframe/2, T_pframe/2), rg.Interval(0, door_h)))
            
            wing_breps = []
            if do_union:
                u_wing = rg.Brep.CreateBooleanUnion(wing_frames, tol)
                if u_wing and len(u_wing) > 0:
                    wing_breps.extend(u_wing)
                else:
                    wing_breps.extend(wing_frames)
            else:
                wing_breps.extend(wing_frames)
                
            # 중앙 유리
            glass_b = make_box(rg.Interval(x0 + T_pframe, x1 - T_pframe), rg.Interval(-T_glass/2, T_glass/2), rg.Interval(T_pframe, door_h - T_pframe))
            
            # 날개 회전 및 이동 변환
            angle = rot_angle + i * (2.0 * math.pi / N_wings)
            rot_xform = rg.Transform.Rotation(angle, rg.Vector3d.ZAxis, rg.Point3d.Origin)
            
            # 💡 [수정됨] 날개의 중심점 이동 변환도 Y=0으로 일치시킴
            trans_xform = rg.Transform.Translation(W/2.0, 0, 0)
            wing_xform = trans_xform * rot_xform
            
            for b in wing_breps:
                b.Transform(wing_xform)
                parts.append(("frame", b))
                
            glass_b.Transform(wing_xform)
            parts.append(("glass", glass_b))
            
        # ==========================================
        # [3] 공간 전체 변환 및 반전(Flip)
        # ==========================================
        global_xform = rg.Transform.PlaneToPlane(rg.Plane.WorldXY, rg.Plane(self.base_plane))
        if self.cb_flip.Checked:
            global_xform = global_xform * rg.Transform.Scale(rg.Plane.WorldXY, 1.0, -1.0, 1.0)
            
        final_parts = []
        for n, b in parts:
            b.Transform(global_xform)
            final_parts.append((n, b))
            
        return final_parts

    def OnClosed(self, e):
        self.conduit.Enabled = False
        Rhino.RhinoDoc.ActiveDoc.Views.Redraw()

# ==============================================================================
# [3] 메인 실행부 (모서리 직접 선택 기능 포함)
# ==============================================================================
def main():
    go = Rhino.Input.Custom.GetObject()
    go.SetCommandPrompt("개구부의 두 수직 모서리(Edge)를 선택하세요. (순서 무관)")
    go.GeometryFilter = Rhino.DocObjects.ObjectType.Curve | Rhino.DocObjects.ObjectType.EdgeFilter
    go.SubObjectSelect = True 
    go.GetMultiple(2, 2)
    
    if go.CommandResult() != Rhino.Commands.Result.Success:
        return
        
    c1, c2 = go.Object(0).Curve(), go.Object(1).Curve()
    
    def get_bottom_top(c):
        s, e = c.PointAtStart, c.PointAtEnd
        return (e, s) if s.Z > e.Z else (s, e)
        
    p1_b, p1_t = get_bottom_top(c1)
    p2_b, p2_t = get_bottom_top(c2)
    
    if p1_b.X > p2_b.X or (abs(p1_b.X - p2_b.X) < 1e-4 and p1_b.Y > p2_b.Y):
        p1_b, p2_b = p2_b, p1_b
        p1_t, p2_t = p2_t, p1_t
        
    z_vec = (p1_t - p1_b); height = z_vec.Length; z_vec.Unitize()
    x_vec = (p2_b - p1_b); width = x_vec.Length; x_vec.Unitize()
    y_vec = Rhino.Geometry.Vector3d.CrossProduct(z_vec, x_vec); y_vec.Unitize()
    
    base_plane = rg.Plane(p1_b, x_vec, y_vec)
    
    dlg = RevolvingDoorDialog(base_plane, width, height)
    rc = Rhino.UI.EtoExtensions.ShowSemiModal(dlg, Rhino.RhinoDoc.ActiveDoc, Rhino.UI.RhinoEtoApp.MainWindow)
    
    if rc:
        rs.EnableRedraw(False)
        
        # 새 그룹 생성
        group_name = rs.AddGroup()
        baked_object_ids = []
        
        for name, brep in dlg.GenerateGeometry():
            obj_id = Rhino.RhinoDoc.ActiveDoc.Objects.AddBrep(brep)
            baked_object_ids.append(obj_id) # 생성된 객체 ID 수집
            
            layer_name = "Door_" + name
            if not rs.IsLayer(layer_name): rs.AddLayer(layer_name)
            rs.ObjectLayer(obj_id, layer_name)
            
            if name == "frame": rs.ObjectColor(obj_id, [150, 150, 150])
            elif name == "glass": rs.ObjectColor(obj_id, [200, 230, 255])
            
        # 생성된 객체들을 모두 앞서 만든 그룹에 추가
        if baked_object_ids:
            rs.AddObjectsToGroup(baked_object_ids, group_name)
            
        rs.EnableRedraw(True)

if __name__ == "__main__":
    main()