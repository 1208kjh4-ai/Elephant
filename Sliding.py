# -*- coding: utf-8 -*-
import Rhino
import Rhino.Geometry as rg
import Rhino.Display as rd
import Eto.Forms as forms
import Eto.Drawing as drawing
import rhinoscriptsyntax as rs
import scriptcontext as sc  # [추가] 라이노 메모리(sticky) 접근을 위한 모듈
import System

# ==============================================================================
# [1] 독립형 미리보기 엔진 (실시간 변화 반영)
# ==============================================================================
class DoorPreviewConduit(rd.DisplayConduit):
    def __init__(self):
        rd.DisplayConduit.__init__(self)
        self.preview_breps = []
        self.frame_mat = rd.DisplayMaterial(System.Drawing.Color.Indigo)
        self.glass_mat = rd.DisplayMaterial(System.Drawing.Color.AliceBlue)
        self.glass_mat.Transparency = 0.5 

    def DrawForeground(self, e):
        for name, brep in self.preview_breps:
            if brep and brep.IsValid:
                mat = self.glass_mat if name == "glass" else self.frame_mat
                e.Display.DrawBrepShaded(brep, mat)
                e.Display.DrawBrepWires(brep, System.Drawing.Color.Black, 1)

# ==============================================================================
# [2] 미닫이문 전용 다이얼로그 (설정 저장/로드 및 크기 수정 반영)
# ==============================================================================
class SlidingDoorDialog(forms.Dialog[bool]):
    def __init__(self, base_plane, width, height):
        self.Title = "세부 설정"
        self.base_plane, self.width, self.height = base_plane, width, height
        self.conduit = DoorPreviewConduit()
        self.conduit.Enabled = True
        
        # [기억 기능] 저장된 값이 없으면 사용할 기본값 정의
        self.default_settings = {
            "panel_count": 2,
            "has_threshold": True,
            "frame_t": "30",
            "frame_d": "200",
            "pframe_t": "60",
            "flip": False,
            "union": False,
            "open_value": 0
        }
        # sticky 메모리에서 설정을 불러옴 (없으면 기본값 사용)
        self.saved_settings = sc.sticky.get("SlidingDoor_Settings", self.default_settings)
        
        self.layout = forms.DynamicLayout(Spacing=drawing.Size(5, 8), Padding=20)
        self.SetupUI()
        self.layout.AddRow(None)
        
        # [수정] OK 버튼을 누르면 설정을 저장하는 전용 함수(OnOkClick)를 거치도록 연결
        btn_ok = forms.Button(Text="생성")
        btn_ok.Click += self.OnOkClick
        
        btn_cancel = forms.Button(Text="취소")
        btn_cancel.Click += lambda s,e: self.Close(False)
        
        self.layout.AddRow(btn_ok, btn_cancel)
        self.Content = self.layout
        
        self.Shown += lambda s, e: self.UpdatePreview()

    def SetupUI(self):
        # 1. 문 개수 라디오 버튼 세팅 및 로드
        self.rb_cnt_2 = forms.RadioButton(Text="2개")
        self.rb_cnt_3 = forms.RadioButton(self.rb_cnt_2, Text="3개")
        self.rb_cnt_4 = forms.RadioButton(self.rb_cnt_2, Text="4개")
        
        saved_cnt = self.saved_settings.get("panel_count", 3)
        if saved_cnt == 2: self.rb_cnt_2.Checked = True
        elif saved_cnt == 4: self.rb_cnt_4.Checked = True
        else: self.rb_cnt_2.Checked = True
        
        # 2. 문턱 라디오 버튼 세팅 및 로드
        self.rb_threshold_on = forms.RadioButton(Text="있음")
        self.rb_threshold_off = forms.RadioButton(self.rb_threshold_on, Text="없음")
        if self.saved_settings.get("has_threshold", True): self.rb_threshold_on.Checked = True
        else: self.rb_threshold_off.Checked = True
        
        # 3. 텍스트 박스 세팅, 너비 고정(50) 및 로드
        self.txt_t = forms.TextBox(Text=str(self.saved_settings.get("frame_t", "30")))
        self.txt_t.Width = 50
        self.txt_d = forms.TextBox(Text=str(self.saved_settings.get("frame_d", "200")))
        self.txt_d.Width = 50
        self.txt_pframe_t = forms.TextBox(Text=str(self.saved_settings.get("pframe_t", "60")))
        self.txt_pframe_t.Width = 50
        
        # 4. 체크박스 및 슬라이더 세팅 및 로드
        self.cb_flip = forms.CheckBox(Text="뒤집기", Checked=self.saved_settings.get("flip", False))
        self.cb_union = forms.CheckBox(Text="프레임 결합", Checked=self.saved_settings.get("union", False))
        
        saved_open = self.saved_settings.get("open_value", 0)
        self.sli_open = forms.Slider(MinValue=0, MaxValue=100, Value=saved_open)
        self.lbl_open = forms.Label(Text=str(saved_open) + "%")
        
        # 이벤트 연결
        self.rb_cnt_2.CheckedChanged += lambda s,e: self.UpdatePreview()
        self.rb_cnt_3.CheckedChanged += lambda s,e: self.UpdatePreview()
        self.rb_cnt_4.CheckedChanged += lambda s,e: self.UpdatePreview()
        self.rb_threshold_on.CheckedChanged += lambda s,e: self.UpdatePreview()
        self.rb_threshold_off.CheckedChanged += lambda s,e: self.UpdatePreview()
        self.cb_flip.CheckedChanged += lambda s,e: self.UpdatePreview()
        self.cb_union.CheckedChanged += lambda s,e: self.UpdatePreview()
        self.txt_t.TextChanged += lambda s,e: self.UpdatePreview()
        self.txt_d.TextChanged += lambda s,e: self.UpdatePreview()
        self.txt_pframe_t.TextChanged += lambda s,e: self.UpdatePreview() 
        self.sli_open.ValueChanged += lambda s,e: (setattr(self.lbl_open, 'Text', str(self.sli_open.Value)+"%"), self.UpdatePreview())
            
        # [수정 반영] 텍스트 박스 행 끝에 None을 배치하여 강제 늘어남 현상 방지 (정렬 최적화)
        self.layout.AddRow(forms.Label(Text="문 개수:"), self.rb_cnt_2, self.rb_cnt_3, self.rb_cnt_4)
        self.layout.AddRow(forms.Label(Text="문턱:"), self.rb_threshold_on, self.rb_threshold_off)
        self.layout.AddRow(forms.Label(Text="문틀 두께(mm):"), self.txt_t)
        self.layout.AddRow(forms.Label(Text="문틀 깊이(mm):"), self.txt_d)
        self.layout.AddRow(forms.Label(Text="프레임 두께(mm):"), self.txt_pframe_t)
        self.layout.AddRow(self.cb_flip, self.cb_union)
        self.layout.AddRow(forms.Label(Text="열림 정도(0~100%):"), self.sli_open, self.lbl_open)

    def OnOkClick(self, sender, args):
        """ [신규 함수] 생성 버튼 클릭 시 현재 입력 항목들을 메모리에 저장하고 창을 닫음 """
        if self.rb_cnt_2.Checked: current_cnt = 2
        elif self.rb_cnt_4.Checked: current_cnt = 4
        else: current_cnt = 3
        
        # 현재 값 딕셔너리 구성
        current_settings = {
            "panel_count": current_cnt,
            "has_threshold": self.rb_threshold_on.Checked,
            "frame_t": self.txt_t.Text,
            "frame_d": self.txt_d.Text,
            "pframe_t": self.txt_pframe_t.Text,
            "flip": self.cb_flip.Checked,
            "union": self.cb_union.Checked,
            "open_value": self.sli_open.Value
        }
        
        # 라이노 sticky 사전에 데이터 덮어쓰기 저장
        sc.sticky["SlidingDoor_Settings"] = current_settings
        self.Close(True)

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
        do_union = self.cb_union.Checked
        
        if self.rb_cnt_4.Checked: panel_count = 4
        elif self.rb_cnt_3.Checked: panel_count = 3
        else: panel_count = 2
        
        T_pframe = self.GetSafeFloat(self.txt_pframe_t.Text, 60.0)
        T_pdepth = 30.0
        T_glass = 10.0
        
        open_ratio = self.sli_open.Value / 100.0
        parts = []
        tol = Rhino.RhinoDoc.ActiveDoc.ModelAbsoluteTolerance 
        
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

        z_start = T_frame if has_threshold else 0.0
        z_end = H - T_frame
        total_w = W - (2 * T_frame)
        
        num_overlaps = 2 if panel_count in [3, 4] else 1
        p_w = (total_w + num_overlaps * T_pframe) / panel_count
        
        if panel_count == 2:
            y_coords = [30.0, 60.0]
            x_starts = [T_frame, T_frame + p_w - T_pframe]
        elif panel_count == 3:
            y_coords = [30.0, 60.0, 90.0]
            x_starts = [T_frame, T_frame + p_w - T_pframe, T_frame + 2 * p_w - 2 * T_pframe]
        else:
            y_coords = [30.0, 60.0, 60.0, 30.0]
            x_starts = [T_frame, T_frame + p_w - T_pframe, T_frame + 2 * p_w - T_pframe, T_frame + 3 * p_w - 2 * T_pframe]
        
        for i in range(panel_count):
            x_start = x_starts[i]
            move_x = 0
            
            if panel_count == 2:
                if i == 0: move_x = open_ratio * (p_w - T_pframe)
            elif panel_count == 3:
                if i == 0: move_x = open_ratio * 2 * (p_w - T_pframe)
                elif i == 1: move_x = open_ratio * 1 * (p_w - T_pframe)
            elif panel_count == 4:
                if i == 1 or i == 2:
                    move_x = open_ratio * (p_w - T_pframe) * (1 if i % 2 == 0 else -1)
            
            x0 = x_start + move_x
            x1 = x0 + p_w
            y_s = y_coords[i]
            
            def make_box(ix, iy, iz): return rg.Box(rg.Plane.WorldXY, ix, iy, iz).ToBrep()
            
            iy_frame = rg.Interval(y_s, y_s + T_pdepth)
            glass_y_offset = (T_pdepth - T_glass) / 2.0
            iy_glass = rg.Interval(y_s + glass_y_offset, y_s + glass_y_offset + T_glass)
            
            panel_frames = []
            
            if do_union:
                panel_frames.append(make_box(rg.Interval(x0, x1), iy_frame, rg.Interval(z_start, z_start + T_pframe))) 
                panel_frames.append(make_box(rg.Interval(x0, x1), iy_frame, rg.Interval(z_end - T_pframe, z_end))) 
                panel_frames.append(make_box(rg.Interval(x0, x0 + T_pframe), iy_frame, rg.Interval(z_start, z_end))) 
                panel_frames.append(make_box(rg.Interval(x1 - T_pframe, x1), iy_frame, rg.Interval(z_start, z_end))) 
                
                unioned_panel = rg.Brep.CreateBooleanUnion(panel_frames, tol)
                if unioned_panel and len(unioned_panel) > 0:
                    for b in unioned_panel: parts.append(("frame", b))
                else:
                    for b in panel_frames: parts.append(("frame", b))
            else:
                panel_frames.append(make_box(rg.Interval(x0, x1), iy_frame, rg.Interval(z_start, z_start + T_pframe))) 
                panel_frames.append(make_box(rg.Interval(x0, x1), iy_frame, rg.Interval(z_end - T_pframe, z_end))) 
                panel_frames.append(make_box(rg.Interval(x0, x0 + T_pframe), iy_frame, rg.Interval(z_start + T_pframe, z_end - T_pframe))) 
                panel_frames.append(make_box(rg.Interval(x1 - T_pframe, x1), iy_frame, rg.Interval(z_start + T_pframe, z_end - T_pframe))) 
                for b in panel_frames: parts.append(("frame", b))
            
            parts.append(("glass", make_box(rg.Interval(x0 + T_pframe, x1 - T_pframe), iy_glass, rg.Interval(z_start + T_pframe, z_end - T_pframe))))
            
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
# [3] 입력 방식 분기 처리용 로직
# ==============================================================================
def process_two_curves(c1, c2):
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
    return base_plane, width, height


def get_3point_rectangle():
    gp1 = Rhino.Input.Custom.GetPoint()
    gp1.SetCommandPrompt("직사각형의 첫 번째 구석점을 지정하세요.")
    if gp1.Get() != Rhino.Input.GetResult.Point: return None, 0, 0
    p1 = gp1.Point()
    
    gp2 = Rhino.Input.Custom.GetPoint()
    gp2.SetCommandPrompt("두 번째 점을 지정하세요 (너비 방향).")
    gp2.SetBasePoint(p1, True)
    gp2.DrawLineFromPoint(p1, True)
    if gp2.Get() != Rhino.Input.GetResult.Point: return None, 0, 0
    p2 = gp2.Point()
    
    x_vec = p2 - p1
    width = x_vec.Length
    if width < 1e-4: return None, 0, 0
    x_vec.Unitize()
    
    gp3 = Rhino.Input.Custom.GetPoint()
    gp3.SetCommandPrompt("세 번째 점을 지정하세요 (높이 방향).")
    gp3.SetBasePoint(p2, True)
    
    def DynamicRectangleDraw(sender, args):
        current_pt = args.CurrentPoint
        v13 = current_pt - p1
        proj_len = v13 * x_vec
        z_dir = v13 - (x_vec * proj_len)
        p4 = p1 + z_dir
        p3_projected = p2 + z_dir
        args.Display.DrawLine(p1, p2, System.Drawing.Color.DarkRed, 2)
        args.Display.DrawLine(p2, p3_projected, System.Drawing.Color.DarkRed, 2)
        args.Display.DrawLine(p3_projected, p4, System.Drawing.Color.DarkRed, 2)
        args.Display.DrawLine(p4, p1, System.Drawing.Color.DarkRed, 2)
        
    gp3.DynamicDraw += DynamicRectangleDraw
    if gp3.Get() != Rhino.Input.GetResult.Point: return None, 0, 0
    p3 = gp3.Point()
    
    v13 = p3 - p1
    proj_len = v13 * x_vec
    z_vec = v13 - (x_vec * proj_len)
    height = z_vec.Length
    if height < 1e-4: return None, 0, 0
    z_vec.Unitize()
    
    y_vec = Rhino.Geometry.Vector3d.CrossProduct(z_vec, x_vec)
    y_vec.Unitize()
    
    base_plane = rg.Plane(p1, x_vec, y_vec)
    return base_plane, width, height


# ==============================================================================
# [4] 메인 실행부 (기본 모서리 선택 + 명령행 직사각형 옵션 전환 포함)
# ==============================================================================
def main():
    go = Rhino.Input.Custom.GetObject()
    go.SetCommandPrompt("개구부의 두 수직 모서리를 선택하거나 옵션을 고르세요.")
    go.GeometryFilter = Rhino.DocObjects.ObjectType.Curve | Rhino.DocObjects.ObjectType.EdgeFilter
    go.SubObjectSelect = True 
    
    opt_rect = go.AddOption("Rectangle")
    
    base_plane = None
    width = 0
    height = 0
    
    while True:
        res = go.GetMultiple(2, 2)
        
        if res == Rhino.Input.GetResult.Option:
            if go.Option().Index == opt_rect:
                base_plane, width, height = get_3point_rectangle()
                if base_plane is not None:
                    break
                else:
                    go.ClearObjects()
                    continue
                    
        elif res == Rhino.Input.GetResult.Object:
            if go.ObjectCount == 2:
                c1 = go.Object(0).Curve()
                c2 = go.Object(1).Curve()
                base_plane, width, height = process_two_curves(c1, c2)
                break
        else:
            return
            
    dlg = SlidingDoorDialog(base_plane, width, height)
    rc = Rhino.UI.EtoExtensions.ShowSemiModal(dlg, Rhino.RhinoDoc.ActiveDoc, Rhino.UI.RhinoEtoApp.MainWindow)
    
    if rc:
        rs.EnableRedraw(False)
        group_name = rs.AddGroup()
        baked_object_ids = []
        
        for name, brep in dlg.GenerateGeometry():
            obj_id = Rhino.RhinoDoc.ActiveDoc.Objects.AddBrep(brep)
            baked_object_ids.append(obj_id)
            
            layer_name = "Door_" + name
            if not rs.IsLayer(layer_name): rs.AddLayer(layer_name)
            rs.ObjectLayer(obj_id, layer_name)
            
            if name == "frame": rs.ObjectColor(obj_id, [150, 150, 150])
            elif name == "glass": rs.ObjectColor(obj_id, [200, 230, 255])
            
        if baked_object_ids:
            rs.AddObjectsToGroup(baked_object_ids, group_name)
            
        rs.EnableRedraw(True)

if __name__ == "__main__":
    main()