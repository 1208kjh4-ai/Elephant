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
        self.frame_mat = rd.DisplayMaterial(System.Drawing.Color.Indigo)
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
# [2] 폴딩도어 전용 다이얼로그
# ==============================================================================
class FoldingDoorDialog(forms.Dialog[bool]):
    def __init__(self, base_plane, width, height):
        self.Title = "세부 설정"
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
        # 폴딩도어는 자유로운 개수 설정이 필요하므로 Stepper 사용
        self.num_panels = forms.NumericStepper(Value=4, MinValue=2, MaxValue=12)
        
        # 열림 방식 옵션 추가
        self.rb_open_1 = forms.RadioButton(Text="한쪽 열림")
        self.rb_open_2 = forms.RadioButton(self.rb_open_1, Text="양쪽 열림")
        self.rb_open_1.Checked = True
        
        self.rb_threshold_on = forms.RadioButton(Text="있음")
        self.rb_threshold_off = forms.RadioButton(self.rb_threshold_on, Text="없음")
        self.rb_threshold_on.Checked = True
        
        self.txt_t = forms.TextBox(Text="30")
        self.txt_d = forms.TextBox(Text="200")
        
        # 문짝 프레임 두께 입력을 위한 텍스트 박스 추가
        self.txt_pframe_t = forms.TextBox(Text="60")
        
        self.cb_flip = forms.CheckBox(Text="뒤집기", Checked=False)
        self.cb_union = forms.CheckBox(Text="프레임 결합 (Boolean Union)", Checked=True) 
        self.sli_open = forms.Slider(MinValue=0, MaxValue=100, Value=0)
        self.lbl_open = forms.Label(Text="0%")
        
        # 이벤트 연결
        self.num_panels.ValueChanged += lambda s,e: self.UpdatePreview()
        self.rb_open_1.CheckedChanged += lambda s,e: self.UpdatePreview()
        self.rb_open_2.CheckedChanged += lambda s,e: self.UpdatePreview()
        self.rb_threshold_on.CheckedChanged += lambda s,e: self.UpdatePreview()
        self.rb_threshold_off.CheckedChanged += lambda s,e: self.UpdatePreview()
        self.cb_flip.CheckedChanged += lambda s,e: self.UpdatePreview()
        self.cb_union.CheckedChanged += lambda s,e: self.UpdatePreview()
        self.txt_t.TextChanged += lambda s,e: self.UpdatePreview()
        self.txt_d.TextChanged += lambda s,e: self.UpdatePreview()
        self.txt_pframe_t.TextChanged += lambda s,e: self.UpdatePreview() 
        self.sli_open.ValueChanged += lambda s,e: (setattr(self.lbl_open, 'Text', str(self.sli_open.Value)+"%"), self.UpdatePreview())
            
        # 레이아웃 배치
        self.layout.AddRow(forms.Label(Text="문 개수:"), self.num_panels)
        self.layout.AddRow(forms.Label(Text="열림 방식:"), self.rb_open_1, self.rb_open_2)
        self.layout.AddRow(forms.Label(Text="문턱:"), self.rb_threshold_on, self.rb_threshold_off)
        self.layout.AddRow(forms.Label(Text="문틀 두께(mm):"), self.txt_t)
        self.layout.AddRow(forms.Label(Text="문틀 깊이(mm):"), self.txt_d)
        self.layout.AddRow(forms.Label(Text="문 프레임 두께(mm):"), self.txt_pframe_t)
        self.layout.AddRow(self.cb_flip, self.cb_union) 
        self.layout.AddRow(forms.Label(Text="열림 정도(0~100%):"), self.sli_open, self.lbl_open)

    def GetSafeFloat(self, text, default):
        try: return float(text)
        except: return default

    def UpdatePreview(self):
        self.conduit.preview_breps = self.GenerateGeometry()
        Rhino.RhinoDoc.ActiveDoc.Views.Redraw()

    def GenerateGeometry(self):
        W, H = self.width, self.height
        T_frame = self.GetSafeFloat(self.txt_t.Text, 30.0)
        D_frame = self.GetSafeFloat(self.txt_d.Text, 200.0)
        
        has_threshold = self.rb_threshold_on.Checked
        panel_count = int(self.num_panels.Value)
        do_union = self.cb_union.Checked 
        is_bi_parting = self.rb_open_2.Checked # 양방향 열림 여부
        
        T_pframe = self.GetSafeFloat(self.txt_pframe_t.Text, 60.0)
        T_pdepth = 30.0 # 문짝 자체의 깊이
        T_glass = 10.0  # 유리의 두께
        
        open_ratio = self.sli_open.Value / 100.0
        
        parts = []
        tol = Rhino.RhinoDoc.ActiveDoc.ModelAbsoluteTolerance 
        
        # ==========================================
        # [1] 전체 문틀 생성 (Boolean Union 처리)
        # ==========================================
        outer_frames = []
        outer_frames.append(rg.Box(rg.Plane.WorldXY, rg.Interval(0, T_frame), rg.Interval(0, D_frame), rg.Interval(0, H)).ToBrep())
        outer_frames.append(rg.Box(rg.Plane.WorldXY, rg.Interval(W - T_frame, W), rg.Interval(0, D_frame), rg.Interval(0, H)).ToBrep())
        
        if do_union:
            outer_frames.append(rg.Box(rg.Plane.WorldXY, rg.Interval(0, W), rg.Interval(0, D_frame), rg.Interval(H - T_frame, H)).ToBrep())
            if has_threshold:
                outer_frames.append(rg.Box(rg.Plane.WorldXY, rg.Interval(0, W), rg.Interval(0, D_frame), rg.Interval(0, T_frame)).ToBrep())
        else:
            outer_frames.append(rg.Box(rg.Plane.WorldXY, rg.Interval(T_frame, W - T_frame), rg.Interval(0, D_frame), rg.Interval(H - T_frame, H)).ToBrep())
            if has_threshold:
                outer_frames.append(rg.Box(rg.Plane.WorldXY, rg.Interval(T_frame, W - T_frame), rg.Interval(0, D_frame), rg.Interval(0, T_frame)).ToBrep())

        if do_union:
            unioned_outer = rg.Brep.CreateBooleanUnion(outer_frames, tol)
            if unioned_outer and len(unioned_outer) > 0:
                for b in unioned_outer: parts.append(("frame", b))
            else:
                for b in outer_frames: parts.append(("frame", b))
        else:
            for b in outer_frames: parts.append(("frame", b))

        # ==========================================
        # [2] 폴딩도어 개별 문짝 및 각도 계산
        # ==========================================
        z_start = T_frame if has_threshold else 0.0
        z_end = H - T_frame
        p_h = z_end - z_start
        
        total_inner_w = W - (2 * T_frame)
        p_w = total_inner_w / panel_count
        
        # 완전 접힘 방지를 위해 최대 각도는 85도로 제한
        max_angle = math.radians(85)
        theta = max_angle * open_ratio
        
        def make_box(ix, iy, iz):
            return rg.Box(rg.Plane.WorldXY, ix, iy, iz).ToBrep()

        # 양방향 열림일 경우, 그룹을 좌/우로 분할
        if is_bi_parting:
            left_count = panel_count // 2
            right_count = panel_count - left_count
        else:
            left_count = panel_count
            right_count = 0

        # 좌측 그룹(group_idx=0)과 우측 그룹(group_idx=1) 순차 생성
        for group_idx, count in enumerate([left_count, right_count]):
            if count == 0: continue
            
            P_hinge = rg.Point3d(0, 0, 0) # 시작 기준 힌지 (앞면)

            for i in range(count):
                start_idx = len(parts)

                # 지그재그 교차 힌지 위치 및 각도 설정 (바깥쪽으로 접힘)
                if i % 2 == 0:
                    alpha_i = -theta
                    local_pivot = rg.Point3d(0, 0, 0)
                    next_local_pivot = rg.Point3d(p_w, T_pdepth, 0)
                else:
                    alpha_i = theta
                    local_pivot = rg.Point3d(0, T_pdepth, 0)
                    next_local_pivot = rg.Point3d(p_w, 0, 0)

                # 원점(Origin)을 기준으로 기본 문짝 생성
                panel_frames = []
                
                iy_frame = rg.Interval(0, T_pdepth)
                glass_y_offset = (T_pdepth - T_glass) / 2.0
                iy_glass = rg.Interval(glass_y_offset, glass_y_offset + T_glass)
                
                if do_union:
                    panel_frames.append(make_box(rg.Interval(0, p_w), iy_frame, rg.Interval(0, T_pframe))) # 하
                    panel_frames.append(make_box(rg.Interval(0, p_w), iy_frame, rg.Interval(p_h - T_pframe, p_h))) # 상
                    panel_frames.append(make_box(rg.Interval(0, T_pframe), iy_frame, rg.Interval(0, p_h))) # 좌
                    panel_frames.append(make_box(rg.Interval(p_w - T_pframe, p_w), iy_frame, rg.Interval(0, p_h))) # 우
                    
                    unioned_panel = rg.Brep.CreateBooleanUnion(panel_frames, tol)
                    if unioned_panel and len(unioned_panel) > 0:
                        for b in unioned_panel: parts.append(("frame", b))
                    else:
                        for b in panel_frames: parts.append(("frame", b))
                else:
                    panel_frames.append(make_box(rg.Interval(0, p_w), iy_frame, rg.Interval(0, T_pframe))) 
                    panel_frames.append(make_box(rg.Interval(0, p_w), iy_frame, rg.Interval(p_h - T_pframe, p_h))) 
                    panel_frames.append(make_box(rg.Interval(0, T_pframe), iy_frame, rg.Interval(T_pframe, p_h - T_pframe))) 
                    panel_frames.append(make_box(rg.Interval(p_w - T_pframe, p_w), iy_frame, rg.Interval(T_pframe, p_h - T_pframe))) 
                    for b in panel_frames: parts.append(("frame", b))
                
                # 내부 유리 생성
                parts.append(("glass", make_box(rg.Interval(T_pframe, p_w - T_pframe), iy_glass, rg.Interval(T_pframe, p_h - T_pframe))))

                # [3] 이동 및 회전 변환 적용
                rot_xform = rg.Transform.Rotation(alpha_i, rg.Vector3d.ZAxis, rg.Point3d.Origin)
                
                rotated_pivot = rg.Point3d(local_pivot)
                rotated_pivot.Transform(rot_xform)
                
                tx = P_hinge.X - rotated_pivot.X
                ty = P_hinge.Y - rotated_pivot.Y
                tz = P_hinge.Z - rotated_pivot.Z
                trans_xform = rg.Transform.Translation(tx, ty, tz)
                
                panel_xform = trans_xform * rot_xform
                
                offset_xform = rg.Transform.Translation(T_frame, (D_frame - T_pdepth)/2.0, z_start)
                final_panel_xform = offset_xform * panel_xform
                
                # 💡 [핵심] 우측 그룹(group_idx == 1)인 경우, 생성 후 개구부 중앙을 기준으로 거울(Mirror) 변환 적용
                if group_idx == 1:
                    center_x = T_frame + total_inner_w / 2.0
                    mirror_plane = rg.Plane(rg.Point3d(center_x, 0, 0), rg.Vector3d.XAxis)
                    mirror_xform = rg.Transform.Mirror(mirror_plane)
                    final_panel_xform = mirror_xform * final_panel_xform
                
                # 방금 추가된 문짝 조각들에 변환 적용
                for j in range(start_idx, len(parts)):
                    parts[j][1].Transform(final_panel_xform)
                    
                # 다음 문짝을 위한 힌지 업데이트
                next_hinge_rotated = rg.Point3d(next_local_pivot)
                next_hinge_rotated.Transform(rot_xform)
                P_hinge = rg.Point3d(next_hinge_rotated.X + tx, next_hinge_rotated.Y + ty, next_hinge_rotated.Z + tz)

        # ==========================================
        # [4] 공간 전체 변환 및 반전(Flip)
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
    
    dlg = FoldingDoorDialog(base_plane, width, height)
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