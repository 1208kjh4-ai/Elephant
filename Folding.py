# -*- coding: utf-8 -*-
import Rhino
import Rhino.Geometry as rg
import Rhino.Display as rd
import Eto.Forms as forms
import Eto.Drawing as drawing
import rhinoscriptsyntax as rs
import scriptcontext as sc
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
        
        btn_ok = forms.Button(Text="생성")
        btn_ok.Click += self.OnOkClicked
        
        btn_cancel = forms.Button(Text="취소")
        btn_cancel.Click += lambda s,e: self.Close(False)
        
        self.layout.AddRow(btn_ok, btn_cancel)
        self.Content = self.layout
        
        self.Shown += lambda s, e: self.UpdatePreview()

    def SetupUI(self):
        s = sc.sticky.get("FoldingDoor_Settings", {})
        
        self.num_panels = forms.NumericStepper(Value=s.get("num_panels", 4), MinValue=2, MaxValue=18)
        
        self.rb_open_1 = forms.RadioButton(Text="한쪽 열림")
        self.rb_open_2 = forms.RadioButton(self.rb_open_1, Text="양쪽 열림")
        if s.get("is_single_open", True): self.rb_open_1.Checked = True
        else: self.rb_open_2.Checked = True
        
        self.rb_threshold_on = forms.RadioButton(Text="있음")
        self.rb_threshold_off = forms.RadioButton(self.rb_threshold_on, Text="없음")
        if s.get("has_threshold", True): self.rb_threshold_on.Checked = True
        else: self.rb_threshold_off.Checked = True
        
        self.txt_t = forms.TextBox(Text=s.get("frame_t", "30"))
        self.txt_d = forms.TextBox(Text=s.get("frame_d", "200"))
        self.txt_pframe_t = forms.TextBox(Text=s.get("pframe_t", "60"))
        
        self.cb_flip = forms.CheckBox(Text="뒤집기", Checked=s.get("flip", False))
        self.cb_union = forms.CheckBox(Text="프레임 결합", Checked=s.get("union", False)) 
        
        self.sli_open = forms.Slider(MinValue=0, MaxValue=100, Value=s.get("open_ratio", 0))
        self.lbl_open = forms.Label(Text=str(self.sli_open.Value) + "%") # f-string 에러 수정됨
        
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
        self.sli_open.ValueChanged += lambda s,e: (setattr(self.lbl_open, 'Text', str(self.sli_open.Value) + "%"), self.UpdatePreview())
            
        self.layout.AddRow(forms.Label(Text="문 개수:"), self.num_panels)
        self.layout.AddRow(forms.Label(Text="열림 방식:"), self.rb_open_1, self.rb_open_2)
        self.layout.AddRow(forms.Label(Text="문턱 유무:"), self.rb_threshold_on, self.rb_threshold_off)
        self.layout.AddRow(forms.Label(Text="문틀 두께(mm):"), self.txt_t)
        self.layout.AddRow(forms.Label(Text="문틀 깊이(mm):"), self.txt_d)
        self.layout.AddRow(forms.Label(Text="프레임 두께(mm):"), self.txt_pframe_t)
        self.layout.AddRow(self.cb_flip, self.cb_union) 
        self.layout.AddRow(forms.Label(Text="열림 정도(0~100%):"), self.sli_open, self.lbl_open)

    def OnOkClicked(self, sender, e):
        sc.sticky["FoldingDoor_Settings"] = {
            "num_panels": self.num_panels.Value,
            "is_single_open": self.rb_open_1.Checked,
            "has_threshold": self.rb_threshold_on.Checked,
            "frame_t": self.txt_t.Text,
            "frame_d": self.txt_d.Text,
            "pframe_t": self.txt_pframe_t.Text,
            "flip": self.cb_flip.Checked,
            "union": self.cb_union.Checked,
            "open_ratio": self.sli_open.Value
        }
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
        panel_count = int(self.num_panels.Value)
        do_union = self.cb_union.Checked 
        is_bi_parting = self.rb_open_2.Checked
        
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
        p_h = z_end - z_start
        
        total_inner_w = W - (2 * T_frame)
        p_w = total_inner_w / panel_count
        
        max_angle = math.radians(85)
        theta = max_angle * open_ratio
        
        def make_box(ix, iy, iz):
            return rg.Box(rg.Plane.WorldXY, ix, iy, iz).ToBrep()

        if is_bi_parting:
            left_count = panel_count // 2
            right_count = panel_count - left_count
        else:
            left_count = panel_count
            right_count = 0

        for group_idx, count in enumerate([left_count, right_count]):
            if count == 0: continue
            
            P_hinge = rg.Point3d(0, 0, 0)

            for i in range(count):
                start_idx = len(parts)

                if i % 2 == 0:
                    alpha_i = -theta
                    local_pivot = rg.Point3d(0, 0, 0)
                    next_local_pivot = rg.Point3d(p_w, T_pdepth, 0)
                else:
                    alpha_i = theta
                    local_pivot = rg.Point3d(0, T_pdepth, 0)
                    next_local_pivot = rg.Point3d(p_w, 0, 0)

                panel_frames = []
                iy_frame = rg.Interval(0, T_pdepth)
                glass_y_offset = (T_pdepth - T_glass) / 2.0
                iy_glass = rg.Interval(glass_y_offset, glass_y_offset + T_glass)
                
                if do_union:
                    panel_frames.append(make_box(rg.Interval(0, p_w), iy_frame, rg.Interval(0, T_pframe))) 
                    panel_frames.append(make_box(rg.Interval(0, p_w), iy_frame, rg.Interval(p_h - T_pframe, p_h))) 
                    panel_frames.append(make_box(rg.Interval(0, T_pframe), iy_frame, rg.Interval(0, p_h))) 
                    panel_frames.append(make_box(rg.Interval(p_w - T_pframe, p_w), iy_frame, rg.Interval(0, p_h))) 
                    
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
                
                parts.append(("glass", make_box(rg.Interval(T_pframe, p_w - T_pframe), iy_glass, rg.Interval(T_pframe, p_h - T_pframe))))

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
                
                if group_idx == 1:
                    center_x = T_frame + total_inner_w / 2.0
                    mirror_plane = rg.Plane(rg.Point3d(center_x, 0, 0), rg.Vector3d.XAxis)
                    mirror_xform = rg.Transform.Mirror(mirror_plane)
                    final_panel_xform = mirror_xform * final_panel_xform
                
                for j in range(start_idx, len(parts)):
                    parts[j][1].Transform(final_panel_xform)
                    
                next_hinge_rotated = rg.Point3d(next_local_pivot)
                next_hinge_rotated.Transform(rot_xform)
                P_hinge = rg.Point3d(next_hinge_rotated.X + tx, next_hinge_rotated.Y + ty, next_hinge_rotated.Z + tz)

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
# [3] 3D 자유 직사각형 함수 (CPlane 무관)
# ==============================================================================
def get_3pt_rectangle_custom():
    # 1. 첫 번째 점 (시작점)
    gp1 = Rhino.Input.Custom.GetPoint()
    gp1.SetCommandPrompt("첫 번째 코너를 지정하세요 (시작점)")
    if gp1.Get() != Rhino.Input.GetResult.Point: return None
    p1 = gp1.Point()
    
    # 2. 두 번째 점 (폭 방향)
    gp2 = Rhino.Input.Custom.GetPoint()
    gp2.SetCommandPrompt("두 번째 코너를 지정하세요 (문 폭 및 방향)")
    gp2.SetBasePoint(p1, True)
    gp2.DrawLineFromPoint(p1, True)
    if gp2.Get() != Rhino.Input.GetResult.Point: return None
    p2 = gp2.Point()
    
    x_vec = p2 - p1
    width = x_vec.Length
    if width < 1e-4: return None
    
    x_dir = rg.Vector3d(x_vec)
    x_dir.Unitize()
    
    # 세 번째 점을 찍을 때 실시간으로 사각형을 미리 보여주는 이벤트
    def OnDynamicDraw(sender, e):
        cur_pt = e.CurrentPoint
        v = cur_pt - p1
        dot = v.X * x_dir.X + v.Y * x_dir.Y + v.Z * x_dir.Z
        z_vec = v - (x_dir * dot) # 수직 방향(높이) 성분만 추출
        
        p3 = p2 + z_vec
        p4 = p1 + z_vec
        e.Display.DrawPolyline([p1, p2, p3, p4, p1], System.Drawing.Color.Black, 2)
        
    # 3. 세 번째 점 (높이 방향)
    gp3 = Rhino.Input.Custom.GetPoint()
    gp3.SetCommandPrompt("세 번째 코너를 지정하세요 (문 높이)")
    gp3.SetBasePoint(p1, True)
    gp3.DynamicDraw += OnDynamicDraw
    if gp3.Get() != Rhino.Input.GetResult.Point: return None
    cur_pt = gp3.Point()
    
    v = cur_pt - p1
    dot = v.X * x_dir.X + v.Y * x_dir.Y + v.Z * x_dir.Z
    z_vec = v - (x_dir * dot)
    height = z_vec.Length
    
    if height < 1e-4: return None
    
    z_dir = rg.Vector3d(z_vec)
    z_dir.Unitize()
    
    # X와 Z를 외적하여 Y방향(문의 깊이/두께 방향) 도출
    y_dir = rg.Vector3d.CrossProduct(z_dir, x_dir)
    y_dir.Unitize()
    
    # (폭, 깊이, 높이) 순으로 매핑되는 평면 생성
    base_plane = rg.Plane(p1, x_dir, y_dir)
    
    return base_plane, width, height

# ==============================================================================
# [4] 메인 실행부
# ==============================================================================
def main():
    go = Rhino.Input.Custom.GetObject()
    go.SetCommandPrompt("두 수직 모서리를 선택하세요.")
    go.GeometryFilter = Rhino.DocObjects.ObjectType.Curve | Rhino.DocObjects.ObjectType.EdgeFilter
    go.SubObjectSelect = True 
    
    opt_rect_idx = go.AddOption("Rectangle")

    base_plane = None
    width = 0.0
    height = 0.0

    while True:
        get_rc = go.GetMultiple(1, 2)
        
        if get_rc == Rhino.Input.GetResult.Cancel:
            return
            
        # 3점 직사각형 옵션 클릭 시
        if get_rc == Rhino.Input.GetResult.Option:
            if go.Option().Index == opt_rect_idx:
                result = get_3pt_rectangle_custom()
                if result:
                    base_plane, width, height = result
                    break
                else:
                    return # 도중에 ESC를 누르면 스크립트 종료
                    
        # 기존 선 2개 선택 모드
        elif get_rc == Rhino.Input.GetResult.Object:
            if go.ObjectCount == 2:
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
                break
            else:
                rs.MessageBox("두 개의 모서리를 모두 선택해야 합니다.", 0, "선택 오류")
                go.ClearObjects()
                continue
                
    if base_plane is not None and width > 0 and height > 0:
        dlg = FoldingDoorDialog(base_plane, width, height)
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