# -*- coding: utf-8 -*-
import Rhino
import Rhino.Geometry as rg
import Rhino.Display as rd
import Eto.Forms as forms
import Eto.Drawing as drawing
import rhinoscriptsyntax as rs
import scriptcontext as sc
import math
import System

# ==============================================================================
# [1. 통합 미리보기 엔진]
# ==============================================================================
class DoorPreviewConduit(rd.DisplayConduit):
    def __init__(self):
        rd.DisplayConduit.__init__(self)
        self.preview_breps = []
        self.frame_material = rd.DisplayMaterial(System.Drawing.Color.Indigo)
        self.panel_material = rd.DisplayMaterial(System.Drawing.Color.LightGray)
        self.glass_material = rd.DisplayMaterial(System.Drawing.Color.LightSkyBlue, 0.5)
        self.hardware_material = rd.DisplayMaterial(System.Drawing.Color.DarkGray)

    def DrawForeground(self, e):
        for name, brep in self.preview_breps:
            if not brep or not brep.IsValid: continue
            
            if name == "frame": 
                e.Display.DrawBrepShaded(brep, self.frame_material)
            elif name == "panel": 
                e.Display.DrawBrepShaded(brep, self.panel_material)
            elif name == "glass": 
                e.Display.DrawBrepShaded(brep, self.glass_material)
            elif name == "hardware": 
                e.Display.DrawBrepShaded(brep, self.hardware_material)
                
            e.Display.DrawBrepWires(brep, System.Drawing.Color.Black, 1)

# ==============================================================================
# [2. 여닫이 세부 설정 창]
# ==============================================================================
class SwingDoorDialog(forms.Dialog[bool]):
    def __init__(self, base_plane, width, height):
        self.Title = "문 세부 설정"
        self.Padding = drawing.Padding(20)
        self.base_plane = base_plane
        self.width = width
        self.height = height
        self.Resizable = True
        self.Topmost = True 
        
        self.conduit = DoorPreviewConduit()
        self.conduit.Enabled = True

        s = sc.sticky.get("SwingDoor_Settings", {})

        self.rb_style_solid = forms.RadioButton(Text="솔리드 문")
        self.rb_style_glass = forms.RadioButton(self.rb_style_solid, Text="유리 문")
        if s.get("is_glass", False): self.rb_style_glass.Checked = True
        else: self.rb_style_solid.Checked = True

        # [추가] 유리문 프레임 세부 옵션
        self.dd_glass_frame = forms.DropDown()
        self.dd_glass_frame.DataStore = ["0. 상하좌우 프레임", "1. 상하 프레임", "2. 프레임 없음"]
        self.dd_glass_frame.SelectedIndex = s.get("glass_frame_type", 0)
        self.dd_glass_frame.Enabled = self.rb_style_glass.Checked

        self.rb_count_1 = forms.RadioButton(Text="일반형")
        self.rb_count_2 = forms.RadioButton(self.rb_count_1, Text="양문형")
        if s.get("is_double", False): self.rb_count_2.Checked = True
        else: self.rb_count_1.Checked = True

        self.dd_handle = forms.DropDown()
        self.dd_handle.DataStore = ["0. 없음", "1. 원형", "2. 레버형", "3. Push 형", "4. 수직 바", "5. 수직, 수평 바"]
        self.dd_handle.SelectedIndex = s.get("handle_type", 0)

        self.txt_thick = forms.TextBox(Text=s.get("thick", "30"))
        self.txt_depth = forms.TextBox(Text=s.get("depth", "200"))
        self.txt_panel_frame = forms.TextBox(Text=s.get("panel_frame", "80")) 
        
        self.sli_open = forms.Slider(MinValue=-90, MaxValue=90, Value=s.get("open_val", 0))
        self.lbl_open_val = forms.Label(Text=str(self.sli_open.Value) + "°")
        
        self.cb_flip = forms.CheckBox(Text="뒤집기", Checked=s.get("flip", False))

        layout = forms.DynamicLayout()
        layout.AddRow("문 스타일:", self.rb_style_solid, self.rb_style_glass)
        layout.AddRow("유리문 프레임:", self.dd_glass_frame) # [추가] UI에 반영
        layout.AddRow("여닫이 개수:", self.rb_count_1, self.rb_count_2)
        layout.AddRow("손잡이 형태:", self.dd_handle)
        layout.AddRow(forms.Label(), forms.Label())
        
        layout.AddRow("문틀 두께:", self.txt_thick)
        layout.AddRow("문틀 깊이:", self.txt_depth)
        layout.AddRow("프레임 두께:", self.txt_panel_frame)
        
        open_layout = forms.DynamicLayout()
        open_layout.BeginHorizontal()
        open_layout.Add(self.sli_open, True, False)
        open_layout.Add(self.lbl_open_val)
        open_layout.EndHorizontal()
        layout.AddRow("개방 각도:", open_layout)
        
        layout.AddRow(self.cb_flip)
        
        btn_ok = forms.Button(Text="생성")
        btn_ok.Click += self.OnOkClicked
        layout.AddRow(btn_ok)
        self.Content = layout

        # [추가] 유리문 스타일 선택 시에만 프레임 옵션 활성화
        def OnStyleChanged(sender, e):
            self.dd_glass_frame.Enabled = self.rb_style_glass.Checked
            self.UpdatePreview()

        self.rb_style_solid.CheckedChanged += OnStyleChanged
        self.rb_style_glass.CheckedChanged += OnStyleChanged
        self.dd_glass_frame.SelectedIndexChanged += lambda sender,e: self.UpdatePreview()

        self.rb_count_1.CheckedChanged += lambda sender,e: self.UpdatePreview()
        self.rb_count_2.CheckedChanged += lambda sender,e: self.UpdatePreview()
        self.cb_flip.CheckedChanged += lambda sender,e: self.UpdatePreview()
        self.dd_handle.SelectedIndexChanged += lambda sender,e: self.UpdatePreview()
        
        self.txt_thick.TextChanged += lambda sender,e: self.UpdatePreview()
        self.txt_depth.TextChanged += lambda sender,e: self.UpdatePreview()
        self.txt_panel_frame.TextChanged += lambda sender,e: self.UpdatePreview()
        self.sli_open.ValueChanged += self.OnSliderChanged

        self.UpdatePreview()

    def OnSliderChanged(self, sender, e):
        self.lbl_open_val.Text = str(self.sli_open.Value) + "°"
        self.UpdatePreview()

    def OnOkClicked(self, sender, e):
        sc.sticky["SwingDoor_Settings"] = {
            "is_glass": self.rb_style_glass.Checked,
            "glass_frame_type": self.dd_glass_frame.SelectedIndex, # [추가]
            "is_double": self.rb_count_2.Checked,
            "handle_type": self.dd_handle.SelectedIndex,
            "thick": self.txt_thick.Text,
            "depth": self.txt_depth.Text,
            "panel_frame": self.txt_panel_frame.Text,
            "open_val": self.sli_open.Value,
            "flip": self.cb_flip.Checked
        }
        self.Close(True)

    def GenerateGeometry(self):
        W, H = self.width, self.height
        try: T = float(self.txt_thick.Text)
        except: T = 30.0
        try: D = float(self.txt_depth.Text)
        except: D = 200.0
        try: pf_w = float(self.txt_panel_frame.Text)
        except: pf_w = 80.0
        
        angle = math.radians(self.sli_open.Value)
        is_double = self.rb_count_2.Checked
        is_glass_door = self.rb_style_glass.Checked
        handle_idx = self.dd_handle.SelectedIndex
        
        parts = []
        
        # 문틀
        parts.append(("frame", rg.Box(rg.Plane.WorldXY, rg.Interval(0, T), rg.Interval(0, D), rg.Interval(0, H)).ToBrep()))
        parts.append(("frame", rg.Box(rg.Plane.WorldXY, rg.Interval(W - T, W), rg.Interval(0, D), rg.Interval(0, H)).ToBrep()))
        parts.append(("frame", rg.Box(rg.Plane.WorldXY, rg.Interval(T, W - T), rg.Interval(0, D), rg.Interval(H - T, H)).ToBrep()))
        
        p_w = (W - (2*T)) if not is_double else (W - (2*T))/2.0
        p_h = H - T
        
        def make_cyl(pt, dir_vec, r, h):
            plane = rg.Plane(pt, dir_vec)
            return rg.Cylinder(rg.Circle(plane, r), h).ToBrep(True, True)

        def make_u_bar(p1, p2, normal, stand_off, pipe_r, corner_r):
            vec_T = p2 - p1
            if vec_T.Length < 0.1: return []
            vec_T.Unitize()
            n_vec = rg.Vector3d(normal)
            n_vec.Unitize()
            
            s1 = p1 + n_vec * (stand_off - corner_r)
            e1 = p1 + n_vec * stand_off + vec_T * corner_r
            a1 = rg.Arc(s1, n_vec, e1).ToNurbsCurve()
            
            s2 = p2 + n_vec * stand_off - vec_T * corner_r
            e2 = p2 + n_vec * (stand_off - corner_r)
            a2 = rg.Arc(s2, vec_T, e2).ToNurbsCurve()
            
            joined = rg.Curve.JoinCurves([rg.LineCurve(p1, s1), a1, rg.LineCurve(e1, s2), a2, rg.LineCurve(e2, p2)])
            if joined:
                pipes = rg.Brep.CreatePipe(joined[0], pipe_r, False, rg.PipeCapMode.Flat, True, 0.01, 0.01)
                if pipes: return pipes
            return []
        
        def make_pi_bar(p1, p2, normal, stand_off, pipe_r, pi_inset):
            vec_T = p2 - p1
            l = vec_T.Length
            if l < 0.1: return []
            vec_T.Unitize()
            n_vec = rg.Vector3d(normal)
            n_vec.Unitize()
            
            res = []
            p_start = p1 + n_vec * stand_off
            res.append(make_cyl(p_start, vec_T, pipe_r, l))
            
            st1_pt = p1 + vec_T * pi_inset
            res.append(make_cyl(st1_pt, n_vec, pipe_r, stand_off))
            
            st2_pt = p2 - vec_T * pi_inset
            res.append(make_cyl(st2_pt, n_vec, pipe_r, stand_off))
            
            return res

        def make_panel(px, width, height, rot_angle, pivot):
            panel_parts = []
            
            knob_z = 950.0          
            knob_inset = 100.0       
            knob_head_r = 25.0      
            knob_stem_r = 10.0      
            knob_standoff = 30.0    

            lever_z = 950.0         
            lever_inset = 100.0      
            lever_len = 150.0       
            lever_r = 10.0          
            lever_standoff = 40.0   

            push_z = 1000.0         
            push_gap = 100.0        
            push_r = 15.0           
            push_standoff = 50.0    
            push_corner_r = 20.0    

            vbar_z = (height/2)-100          
            vbar_inset = 150       
            vbar_len = 1000.0        
            vbar_r = 15.0           
            vbar_standoff = 50.0    
            vbar_pi_inset = 200    

            asy_h_z = 950.0         
            asy_inset = 150.0      
            asy_v_gap_bottom = 950.0 
            asy_v_gap_top = 1250.0   
            asy_push_gap = asy_inset    
            asy_r = 15.0            
            asy_standoff = 50.0     
            asy_corner_r = 20.0     

            # 문짝 BRep 생성
            b_outer = rg.Box(rg.Plane.WorldXY, rg.Interval(px, px + width), rg.Interval(0, 30), rg.Interval(0, height)).ToBrep()
            
            if not is_glass_door:
                b_outer.Rotate(rot_angle, rg.Vector3d.ZAxis, pivot)
                panel_parts.append(("panel", b_outer))
            else:
                safe_pf_w = min(pf_w, width * 0.45, height * 0.45)
                glass_frame_idx = self.dd_glass_frame.SelectedIndex
                
                # [수정] 옵션에 따른 유리/프레임 분기 처리
                if glass_frame_idx == 0: 
                    # 0. 상하좌우 프레임
                    b_inner = rg.Box(rg.Plane.WorldXY, rg.Interval(px + safe_pf_w, px + width - safe_pf_w), rg.Interval(-10, 40), rg.Interval(safe_pf_w, height - safe_pf_w)).ToBrep()
                    diff = rg.Brep.CreateBooleanDifference(b_outer, b_inner, 0.001)
                    b_frame = diff[0] if (diff and len(diff) > 0) else b_outer
                    b_frame.Rotate(rot_angle, rg.Vector3d.ZAxis, pivot)
                    panel_parts.append(("panel", b_frame))
                    
                    b_glass = rg.Box(rg.Plane.WorldXY, rg.Interval(px + safe_pf_w, px + width - safe_pf_w), rg.Interval(10, 20), rg.Interval(safe_pf_w, height - safe_pf_w)).ToBrep()
                    b_glass.Rotate(rot_angle, rg.Vector3d.ZAxis, pivot)
                    panel_parts.append(("glass", b_glass))

                elif glass_frame_idx == 1: 
                    # 1. 상하 프레임 (좌우는 유리만 노출)
                    b_frame_bottom = rg.Box(rg.Plane.WorldXY, rg.Interval(px, px + width), rg.Interval(0, 30), rg.Interval(0, safe_pf_w)).ToBrep()
                    b_frame_bottom.Rotate(rot_angle, rg.Vector3d.ZAxis, pivot)
                    panel_parts.append(("panel", b_frame_bottom))

                    b_frame_top = rg.Box(rg.Plane.WorldXY, rg.Interval(px, px + width), rg.Interval(0, 30), rg.Interval(height - safe_pf_w, height)).ToBrep()
                    b_frame_top.Rotate(rot_angle, rg.Vector3d.ZAxis, pivot)
                    panel_parts.append(("panel", b_frame_top))

                    b_glass = rg.Box(rg.Plane.WorldXY, rg.Interval(px, px + width), rg.Interval(10, 20), rg.Interval(safe_pf_w, height - safe_pf_w)).ToBrep()
                    b_glass.Rotate(rot_angle, rg.Vector3d.ZAxis, pivot)
                    panel_parts.append(("glass", b_glass))

                elif glass_frame_idx == 2: 
                    # 2. 프레임 없음 (12t 두께의 순수 강화유리 형태)
                    b_glass = rg.Box(rg.Plane.WorldXY, rg.Interval(px, px + width), rg.Interval(0, 30), rg.Interval(0, height)).ToBrep()
                    b_glass.Rotate(rot_angle, rg.Vector3d.ZAxis, pivot)
                    panel_parts.append(("glass", b_glass))

            # 손잡이 로직
            if handle_idx > 0:
                hw_list = []
                is_left_hinge = (abs(pivot.X - px) < 1.0)
                hinge_dir = rg.Vector3d(-1,0,0) if is_left_hinge else rg.Vector3d(1,0,0)

                if handle_idx == 1:
                    hx = (px + width - knob_inset) if is_left_hinge else (px + knob_inset)
                    hw_list.append(make_cyl(rg.Point3d(hx, 0, knob_z), rg.Vector3d(0,-1,0), knob_stem_r, knob_standoff))
                    hw_list.append(make_cyl(rg.Point3d(hx, -knob_standoff+10, knob_z), rg.Vector3d(0,-1,0), knob_head_r, 10))
                    hw_list.append(make_cyl(rg.Point3d(hx, 30, knob_z), rg.Vector3d(0,1,0), knob_stem_r, knob_standoff))
                    hw_list.append(make_cyl(rg.Point3d(hx, 30+knob_standoff-10, knob_z), rg.Vector3d(0,1,0), knob_head_r, 10))
                
                elif handle_idx == 2:
                    hx = (px + width - lever_inset) if is_left_hinge else (px + lever_inset)
                    hw_list.append(make_cyl(rg.Point3d(hx, 0, lever_z), rg.Vector3d(0,-1,0), lever_r, lever_standoff))
                    hw_list.append(make_cyl(rg.Point3d(hx, -lever_standoff+5, lever_z), hinge_dir, lever_r, lever_len))
                    hw_list.append(make_cyl(rg.Point3d(hx, 30, lever_z), rg.Vector3d(0,1,0), lever_r, lever_standoff))
                    hw_list.append(make_cyl(rg.Point3d(hx, 30+lever_standoff-5, lever_z), hinge_dir, lever_r, lever_len))
                
                elif handle_idx == 3:
                    p1 = rg.Point3d(px + push_gap, 30, push_z)
                    p2 = rg.Point3d(px + width - push_gap, 30, push_z)
                    hw_list.extend(make_u_bar(p1, p2, rg.Vector3d(0,1,0), push_standoff, push_r, push_corner_r))

                elif handle_idx == 4:
                    hx = (px + width - vbar_inset) if is_left_hinge else (px + vbar_inset)
                    p1_f = rg.Point3d(hx, 0, vbar_z - vbar_len/2)
                    p2_f = rg.Point3d(hx, 0, vbar_z + vbar_len/2)
                    hw_list.extend(make_pi_bar(p1_f, p2_f, rg.Vector3d(0,-1,0), vbar_standoff, vbar_r, vbar_pi_inset))
                    
                    p1_b = rg.Point3d(hx, 30, vbar_z - vbar_len/2)
                    p2_b = rg.Point3d(hx, 30, vbar_z + vbar_len/2)
                    hw_list.extend(make_pi_bar(p1_b, p2_b, rg.Vector3d(0,1,0), vbar_standoff, vbar_r, vbar_pi_inset))

                elif handle_idx == 5:
                    hx = (px + width - asy_inset) if is_left_hinge else (px + asy_inset)
                    p1_f = rg.Point3d(hx, 0, asy_v_gap_bottom)           
                    p2_f = rg.Point3d(hx, 0, asy_v_gap_top)     
                    hw_list.extend(make_u_bar(p1_f, p2_f, rg.Vector3d(0,-1,0), asy_standoff, asy_r, asy_corner_r))
                    
                    p1_b = rg.Point3d(px + asy_push_gap, 30, asy_h_z)
                    p2_b = rg.Point3d(px + width - asy_push_gap, 30, asy_h_z)
                    hw_list.extend(make_u_bar(p1_b, p2_b, rg.Vector3d(0,1,0), asy_standoff, asy_r, asy_corner_r))

                for h_brep in hw_list:
                    if h_brep and h_brep.IsValid:
                        h_brep.Rotate(rot_angle, rg.Vector3d.ZAxis, pivot)
                        panel_parts.append(("hardware", h_brep))

            return panel_parts

        # 왼쪽 문짝
        pivot_l = rg.Point3d(T, 0, 0)
        parts.extend(make_panel(T, p_w, p_h, angle, pivot_l))
        
        # 오른쪽 문짝 (양문형)
        if is_double:
            pivot_r = rg.Point3d(W - T, 0, 0)
            parts.extend(make_panel(W - T - p_w, p_w, p_h, -angle, pivot_r))

        xform = rg.Transform.PlaneToPlane(rg.Plane.WorldXY, self.base_plane)
        if self.cb_flip.Checked: 
            xform = xform * rg.Transform.Scale(rg.Plane.WorldXY, 1, -1, 1)
        
        final = []
        for n, b in parts:
            b.Transform(xform)
            final.append((n, b))
        return final

    def UpdatePreview(self):
        self.conduit.preview_breps = self.GenerateGeometry()
        Rhino.RhinoDoc.ActiveDoc.Views.Redraw()

    def OnClosed(self, e):
        self.conduit.Enabled = False
        Rhino.RhinoDoc.ActiveDoc.Views.Redraw()

def get_3pt_rectangle_custom():
    gp1 = Rhino.Input.Custom.GetPoint()
    gp1.SetCommandPrompt("첫 번째 코너를 지정하세요 (시작점)")
    if gp1.Get() != Rhino.Input.GetResult.Point: return None
    p1 = gp1.Point()
    
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
    
    def OnDynamicDraw(sender, e):
        cur_pt = e.CurrentPoint
        v = cur_pt - p1
        dot = v.X * x_dir.X + v.Y * x_dir.Y + v.Z * x_dir.Z
        z_vec = v - (x_dir * dot)
        p3 = p2 + z_vec
        p4 = p1 + z_vec
        e.Display.DrawPolyline([p1, p2, p3, p4, p1], System.Drawing.Color.Black, 2)
        
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
    y_dir = rg.Vector3d.CrossProduct(z_dir, x_dir)
    y_dir.Unitize()
    
    base_plane = rg.Plane(p1, x_dir, y_dir)
    return base_plane, width, height

def main():
    go = Rhino.Input.Custom.GetObject()
    go.SetCommandPrompt("개구부의 두 수직 모서리를 선택하세요.")
    go.GeometryFilter = Rhino.DocObjects.ObjectType.Curve | Rhino.DocObjects.ObjectType.EdgeFilter
    go.SubObjectSelect = True
    
    opt_rect_idx = go.AddOption("Rectangle")
    base_plane = None
    width = 0.0
    height = 0.0

    while True:
        get_rc = go.GetMultiple(1, 2)
        if get_rc == Rhino.Input.GetResult.Cancel: return
            
        if get_rc == Rhino.Input.GetResult.Option:
            if go.Option().Index == opt_rect_idx:
                result = get_3pt_rectangle_custom()
                if result:
                    base_plane, width, height = result
                    break
                else: return 
                    
        elif get_rc == Rhino.Input.GetResult.Object:
            if go.ObjectCount == 2:
                crv1, crv2 = go.Object(0).Curve(), go.Object(1).Curve()
                def get_b(c): return c.PointAtEnd if c.PointAtStart.Z > c.PointAtEnd.Z else c.PointAtStart
                p1_b, p2_b = get_b(crv1), get_b(crv2)
                
                if p1_b.X > p2_b.X or (abs(p1_b.X - p2_b.X) < 1e-4 and p1_b.Y > p2_b.Y): 
                    p1_b, p2_b = p2_b, p1_b
                
                origin = p1_b
                z_vec = crv1.PointAtEnd - crv1.PointAtStart if crv1.PointAtStart.Z < crv1.PointAtEnd.Z else crv1.PointAtStart - crv1.PointAtEnd
                height = z_vec.Length
                z_vec.Unitize()
                
                x_vec = p2_b - p1_b
                width = x_vec.Length
                x_vec.Unitize()
                
                base_plane = rg.Plane(origin, x_vec, rg.Vector3d.CrossProduct(z_vec, x_vec))
                break
            else:
                rs.MessageBox("두 개의 모서리를 모두 선택해야 합니다.", 0, "선택 오류")
                go.ClearObjects()
                continue

    if base_plane is not None and width > 0 and height > 0:
        dlg = SwingDoorDialog(base_plane, width, height)
        if Rhino.UI.EtoExtensions.ShowSemiModal(dlg, Rhino.RhinoDoc.ActiveDoc, Rhino.UI.RhinoEtoApp.MainWindow):
            rs.EnableRedraw(False)
            
            frames = []
            panels = []
            glasses = []
            hardwares = []
            
            for name, brep in dlg.GenerateGeometry():
                if name == "frame": frames.append(brep)
                elif name == "panel": panels.append(brep)
                elif name == "glass": glasses.append(brep)
                elif name == "hardware": hardwares.append(brep)
                
            final_objs = []
            
            layer_frame = "Door_frame"
            layer_glass = "Door_glass"
            layer_hw = "Door_hardware"
            
            if not rs.IsLayer(layer_frame): rs.AddLayer(layer_frame, System.Drawing.Color.Indigo)
            if not rs.IsLayer(layer_glass): rs.AddLayer(layer_glass, System.Drawing.Color.LightSkyBlue)
            if not rs.IsLayer(layer_hw): rs.AddLayer(layer_hw, System.Drawing.Color.DarkGray)
            
            if frames:
                union_frames = rg.Brep.CreateBooleanUnion(frames, Rhino.RhinoDoc.ActiveDoc.ModelAbsoluteTolerance)
                if union_frames:
                    for b in union_frames: 
                        obj_id = Rhino.RhinoDoc.ActiveDoc.Objects.AddBrep(b)
                        if obj_id:
                            rs.ObjectLayer(obj_id, layer_frame)
                            final_objs.append(obj_id)
                else:
                    for b in frames: 
                        obj_id = Rhino.RhinoDoc.ActiveDoc.Objects.AddBrep(b)
                        if obj_id:
                            rs.ObjectLayer(obj_id, layer_frame)
                            final_objs.append(obj_id)
            
            for p in panels:
                obj_id = Rhino.RhinoDoc.ActiveDoc.Objects.AddBrep(p)
                if obj_id:
                    rs.ObjectLayer(obj_id, layer_frame)
                    final_objs.append(obj_id)
                
            for g in glasses:
                obj_id = Rhino.RhinoDoc.ActiveDoc.Objects.AddBrep(g)
                if obj_id:
                    rs.ObjectLayer(obj_id, layer_glass)
                    final_objs.append(obj_id)
                    
            for hw in hardwares:
                obj_id = Rhino.RhinoDoc.ActiveDoc.Objects.AddBrep(hw)
                if obj_id:
                    rs.ObjectLayer(obj_id, layer_hw)
                    final_objs.append(obj_id)
                
            if final_objs:
                group_name = rs.AddGroup()
                rs.AddObjectsToGroup(final_objs, group_name)
                
            rs.EnableRedraw(True)
            Rhino.RhinoDoc.ActiveDoc.Views.Redraw()

if __name__ == "__main__":
    main()