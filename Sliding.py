# -*- coding: utf-8 -*-
import Rhino
import Rhino.Geometry as rg
import Rhino.Display as rd
import Eto.Forms as forms
import Eto.Drawing as drawing
import rhinoscriptsyntax as rs
import System

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
# [2] 미닫이문 전용 다이얼로그
# ==============================================================================
class SlidingDoorDialog(forms.Dialog[bool]):
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
        # UI 요소 생성
        self.rb_cnt_2 = forms.RadioButton(Text="2개")
        self.rb_cnt_4 = forms.RadioButton(self.rb_cnt_2, Text="4개")
        self.rb_cnt_2.Checked = True
        
        self.rb_threshold_on = forms.RadioButton(Text="있음")
        self.rb_threshold_off = forms.RadioButton(self.rb_threshold_on, Text="없음")
        self.rb_threshold_on.Checked = True
        
        self.txt_t = forms.TextBox(Text="30")
        self.txt_d = forms.TextBox(Text="200")
        
        # 문짝 프레임 두께 입력을 위한 텍스트 박스 추가
        self.txt_pframe_t = forms.TextBox(Text="60")
        
        self.cb_flip = forms.CheckBox(Text="뒤집기", Checked=False)
        self.cb_union = forms.CheckBox(Text="프레임 결합 (Boolean Union)", Checked=True) # 솔리드 결합 옵션
        self.sli_open = forms.Slider(MinValue=0, MaxValue=100, Value=0)
        self.lbl_open = forms.Label(Text="0%")
        
        # 이벤트 연결
        self.rb_cnt_2.CheckedChanged += lambda s,e: self.UpdatePreview()
        self.rb_cnt_4.CheckedChanged += lambda s,e: self.UpdatePreview()
        self.rb_threshold_on.CheckedChanged += lambda s,e: self.UpdatePreview()
        self.rb_threshold_off.CheckedChanged += lambda s,e: self.UpdatePreview()
        self.cb_flip.CheckedChanged += lambda s,e: self.UpdatePreview()
        self.cb_union.CheckedChanged += lambda s,e: self.UpdatePreview()
        self.txt_t.TextChanged += lambda s,e: self.UpdatePreview()
        self.txt_d.TextChanged += lambda s,e: self.UpdatePreview()
        self.txt_pframe_t.TextChanged += lambda s,e: self.UpdatePreview() 
        self.sli_open.ValueChanged += lambda s,e: (setattr(self.lbl_open, 'Text', str(self.sli_open.Value)+"%"), self.UpdatePreview())
            
        # 레이아웃 배치
        self.layout.AddRow(forms.Label(Text="문 개수:"), self.rb_cnt_2, self.rb_cnt_4)
        self.layout.AddRow(forms.Label(Text="문턱:"), self.rb_threshold_on, self.rb_threshold_off)
        self.layout.AddRow(forms.Label(Text="문틀 두께(mm):"), self.txt_t)
        self.layout.AddRow(forms.Label(Text="문틀 깊이(mm):"), self.txt_d)
        self.layout.AddRow(forms.Label(Text="문 프레임 두께(mm):"), self.txt_pframe_t)
        self.layout.AddRow(self.cb_flip, self.cb_union) # 체크박스 나란히 배치
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
        panel_count = 4 if self.rb_cnt_4.Checked else 2
        do_union = self.cb_union.Checked # 결합 옵션 상태 가져오기
        
        # 문짝 프레임 너비(정면에서 보이는 두께) 및 문짝 깊이(두께)
        T_pframe = self.GetSafeFloat(self.txt_pframe_t.Text, 60.0)
        T_pdepth = 30.0 # 문짝 자체의 깊이 (프레임 깊이)
        T_glass = 10.0  # 유리의 두께
        
        open_ratio = self.sli_open.Value / 100.0
        
        parts = []
        tol = Rhino.RhinoDoc.ActiveDoc.ModelAbsoluteTolerance 
        
        # [1] 전체 문틀 생성
        outer_frames = []
        # 좌우 프레임
        outer_frames.append(rg.Box(rg.Plane.WorldXY, rg.Interval(0, T_frame), rg.Interval(0, D_frame), rg.Interval(0, H)).ToBrep())
        outer_frames.append(rg.Box(rg.Plane.WorldXY, rg.Interval(W - T_frame, W), rg.Interval(0, D_frame), rg.Interval(0, H)).ToBrep())
        
        # 결합을 위해 상단/하단 프레임의 X길이를 조절
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
                for b in unioned_outer:
                    parts.append(("frame", b))
            else:
                for b in outer_frames:
                    parts.append(("frame", b))
        else:
            for b in outer_frames:
                parts.append(("frame", b))

        # [2] 문짝 위치 및 크기 계산
        z_start = T_frame if has_threshold else 0.0
        z_end = H - T_frame
        
        y_coords = [30.0, 60.0] if panel_count == 2 else [30.0, 60.0, 60.0, 30.0]
        
        total_w = W - (2 * T_frame)
        
        num_overlaps = 2 if panel_count == 4 else 1
        p_w = (total_w + num_overlaps * T_pframe) / panel_count
        
        if panel_count == 2:
            x_starts = [T_frame, T_frame + p_w - T_pframe]
        else:
            x_starts = [
                T_frame, 
                T_frame + p_w - T_pframe, 
                T_frame + 2 * p_w - T_pframe,
                T_frame + 3 * p_w - 2 * T_pframe
            ]
        
        # [3] 개별 문짝(프레임 + 유리) 생성
        for i in range(panel_count):
            x_start = x_starts[i]
            
            is_moving = (panel_count == 2 and i == 0) or (panel_count == 4 and (i == 1 or i == 2))
            move_x = open_ratio * (p_w - T_pframe) * (1 if i % 2 == 0 else -1) if is_moving else 0
            
            x0 = x_start + move_x
            x1 = x0 + p_w
            y_s = y_coords[i]
            
            def make_box(ix, iy, iz):
                return rg.Box(rg.Plane.WorldXY, ix, iy, iz).ToBrep()
            
            iy_frame = rg.Interval(y_s, y_s + T_pdepth)
            glass_y_offset = (T_pdepth - T_glass) / 2.0
            iy_glass = rg.Interval(y_s + glass_y_offset, y_s + glass_y_offset + T_glass)
            
            panel_frames = []
            
            if do_union:
                panel_frames.append(make_box(rg.Interval(x0, x1), iy_frame, rg.Interval(z_start, z_start + T_pframe))) # 하
                panel_frames.append(make_box(rg.Interval(x0, x1), iy_frame, rg.Interval(z_end - T_pframe, z_end))) # 상
                panel_frames.append(make_box(rg.Interval(x0, x0 + T_pframe), iy_frame, rg.Interval(z_start, z_end))) # 좌
                panel_frames.append(make_box(rg.Interval(x1 - T_pframe, x1), iy_frame, rg.Interval(z_start, z_end))) # 우
                
                unioned_panel = rg.Brep.CreateBooleanUnion(panel_frames, tol)
                if unioned_panel and len(unioned_panel) > 0:
                    for b in unioned_panel:
                        parts.append(("frame", b))
                else:
                    for b in panel_frames:
                        parts.append(("frame", b))
            else:
                # 결합 안할 때는 겹치지 않게 정확하게 나눔
                panel_frames.append(make_box(rg.Interval(x0, x1), iy_frame, rg.Interval(z_start, z_start + T_pframe))) # 하
                panel_frames.append(make_box(rg.Interval(x0, x1), iy_frame, rg.Interval(z_end - T_pframe, z_end))) # 상
                panel_frames.append(make_box(rg.Interval(x0, x0 + T_pframe), iy_frame, rg.Interval(z_start + T_pframe, z_end - T_pframe))) # 좌
                panel_frames.append(make_box(rg.Interval(x1 - T_pframe, x1), iy_frame, rg.Interval(z_start + T_pframe, z_end - T_pframe))) # 우
                for b in panel_frames:
                    parts.append(("frame", b))
            
            # 내부 유리 생성
            parts.append(("glass", make_box(rg.Interval(x0 + T_pframe, x1 - T_pframe), iy_glass, rg.Interval(z_start + T_pframe, z_end - T_pframe))))
            
        # [4] 공간 변환 및 반전(Flip)
        xform = rg.Transform.PlaneToPlane(rg.Plane.WorldXY, rg.Plane(self.base_plane))
        if self.cb_flip.Checked:
            xform = xform * rg.Transform.Scale(rg.Plane.WorldXY, 1.0, -1.0, 1.0)
            
        final_parts = []
        for n, b in parts:
            b.Transform(xform)
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
    go.SetCommandPrompt("개구부의 두 수직 모서리를 선택하세요.")
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
    
    dlg = SlidingDoorDialog(base_plane, width, height)
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