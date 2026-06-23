# -*- coding: utf-8 -*-
import Rhino
import Rhino.Geometry as rg
import Rhino.Display as rd
import Eto.Forms as forms
import Eto.Drawing as drawing
import rhinoscriptsyntax as rs
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

    def DrawForeground(self, e):
        for name, brep in self.preview_breps:
            if not brep or not brep.IsValid: continue
            if name == "frame": e.Display.DrawBrepShaded(brep, self.frame_material)
            elif name == "panel": e.Display.DrawBrepShaded(brep, self.panel_material)
            e.Display.DrawBrepWires(brep, System.Drawing.Color.Black, 1)

# ==============================================================================
# [2. 여닫이 세부 설정 창]
# ==============================================================================
class SwingDoorDialog(forms.Dialog[bool]):
    def __init__(self, base_plane, width, height):
        self.Title = "세부 설정"
        self.Padding = drawing.Padding(20)
        self.base_plane = base_plane
        self.width = width
        self.height = height
        
        self.conduit = DoorPreviewConduit()
        self.conduit.Enabled = True

        # UI 요소들
        self.rb_count_1 = forms.RadioButton(Text="일반형"); self.rb_count_1.Checked = True
        self.rb_count_2 = forms.RadioButton(self.rb_count_1, Text="양문형")
        self.txt_thick = forms.TextBox(Text="30")
        self.txt_depth = forms.TextBox(Text="200")
        
        # 슬라이더 및 라벨
        self.sli_open = forms.Slider(MinValue=-90, MaxValue=90, Value=0)
        self.lbl_open_val = forms.Label(Text="0°")
        
        self.cb_flip = forms.CheckBox(Text="뒤집기")

        # 레이아웃 구성
        layout = forms.DynamicLayout()
        layout.AddRow("여닫이 개수:", self.rb_count_1, self.rb_count_2)
        layout.AddRow("문틀 두께:", self.txt_thick)
        layout.AddRow("문틀 깊이:", self.txt_depth)
        
        open_layout = forms.DynamicLayout()
        open_layout.BeginHorizontal()
        open_layout.Add(self.sli_open, True, False)
        open_layout.Add(self.lbl_open_val)
        open_layout.EndHorizontal()
        layout.AddRow("개방 각도:", open_layout)
        
        layout.AddRow(self.cb_flip)
        
        btn_ok = forms.Button(Text="생성"); btn_ok.Click += lambda s,e: self.Close(True)
        layout.AddRow(btn_ok)
        self.Content = layout

        # 이벤트 연결
        self.rb_count_1.CheckedChanged += lambda s,e: self.UpdatePreview()
        self.rb_count_2.CheckedChanged += lambda s,e: self.UpdatePreview()
        self.cb_flip.CheckedChanged += lambda s,e: self.UpdatePreview()
        self.txt_thick.TextChanged += lambda s,e: self.UpdatePreview()
        self.txt_depth.TextChanged += lambda s,e: self.UpdatePreview()
        self.sli_open.ValueChanged += self.OnSliderChanged

        self.UpdatePreview()

    def OnSliderChanged(self, s, e):
        self.lbl_open_val.Text = "{}°".format(self.sli_open.Value)
        self.UpdatePreview()

    def GenerateGeometry(self):
        W, H = self.width, self.height
        T = float(self.txt_thick.Text or 30)
        D = float(self.txt_depth.Text or 200)
        angle = math.radians(self.sli_open.Value)
        is_double = self.rb_count_2.Checked
        
        parts = []
        # 프레임 (3개의 박스)
        parts.append(("frame", rg.Box(rg.Plane.WorldXY, rg.Interval(0, T), rg.Interval(0, D), rg.Interval(0, H)).ToBrep()))
        parts.append(("frame", rg.Box(rg.Plane.WorldXY, rg.Interval(W - T, W), rg.Interval(0, D), rg.Interval(0, H)).ToBrep()))
        parts.append(("frame", rg.Box(rg.Plane.WorldXY, rg.Interval(T, W - T), rg.Interval(0, D), rg.Interval(H - T, H)).ToBrep()))
        
        # 패널
        p_w = (W - (2*T)) if not is_double else (W - (2*T))/2.0
        p_h = H - T
        
        pivot_l = rg.Point3d(T, 0, 0)
        panel_l = rg.Box(rg.Plane.WorldXY, rg.Interval(T, T + p_w), rg.Interval(0, 30), rg.Interval(0, p_h)).ToBrep()
        panel_l.Rotate(angle, rg.Vector3d.ZAxis, pivot_l)
        parts.append(("panel", panel_l))
        
        if is_double:
            pivot_r = rg.Point3d(W - T, 0, 0)
            panel_r = rg.Box(rg.Plane.WorldXY, rg.Interval(W - T - p_w, W - T), rg.Interval(0, 30), rg.Interval(0, p_h)).ToBrep()
            panel_r.Rotate(-angle, rg.Vector3d.ZAxis, pivot_r)
            parts.append(("panel", panel_r))

        xform = rg.Transform.PlaneToPlane(rg.Plane.WorldXY, self.base_plane)
        if self.cb_flip.Checked: xform = xform * rg.Transform.Scale(rg.Plane.WorldXY, 1, -1, 1)
        
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

# ==============================================================================
# [3. 메인 실행부]
# ==============================================================================
def main():
    go = Rhino.Input.Custom.GetObject()
    go.SetCommandPrompt("개구부의 두 수직 모서리를 선택하세요.")
    go.GeometryFilter = Rhino.DocObjects.ObjectType.Curve | Rhino.DocObjects.ObjectType.EdgeFilter
    go.SubObjectSelect = True
    go.GetMultiple(2, 2)
    
    if go.CommandResult() != Rhino.Commands.Result.Success: 
        return
    
    crv1, crv2 = go.Object(0).Curve(), go.Object(1).Curve()
    
    def get_b(c): 
        return c.PointAtEnd if c.PointAtStart.Z > c.PointAtEnd.Z else c.PointAtStart
    
    p1_b, p2_b = get_b(crv1), get_b(crv2)
    
    if p1_b.X > p2_b.X: p1_b, p2_b = p2_b, p1_b
    
    origin = p1_b
    z_vec = crv1.PointAtEnd - crv1.PointAtStart if crv1.PointAtStart.Z < crv1.PointAtEnd.Z else crv1.PointAtStart - crv1.PointAtEnd
    height = z_vec.Length
    z_vec.Unitize()
    x_vec = p2_b - p1_b
    width = x_vec.Length
    x_vec.Unitize()
    base_plane = rg.Plane(origin, x_vec, rg.Vector3d.CrossProduct(z_vec, x_vec))

    dlg = SwingDoorDialog(base_plane, width, height)
    if Rhino.UI.EtoExtensions.ShowSemiModal(dlg, Rhino.RhinoDoc.ActiveDoc, Rhino.UI.RhinoEtoApp.MainWindow):
        rs.EnableRedraw(False)
        
        frames = []
        panels = []
        for name, brep in dlg.GenerateGeometry():
            if name == "frame": frames.append(brep)
            elif name == "panel": panels.append(brep)
            
        final_objs = []
        # 프레임 Boolean Union
        if frames:
            union_frames = rg.Brep.CreateBooleanUnion(frames, Rhino.RhinoDoc.ActiveDoc.ModelAbsoluteTolerance)
            if union_frames:
                for b in union_frames: final_objs.append(Rhino.RhinoDoc.ActiveDoc.Objects.AddBrep(b))
            else:
                for b in frames: final_objs.append(Rhino.RhinoDoc.ActiveDoc.Objects.AddBrep(b))
        
        # 패널 추가
        for p in panels:
            final_objs.append(Rhino.RhinoDoc.ActiveDoc.Objects.AddBrep(p))
            
        # 모든 객체 그룹화
        if final_objs:
            group_name = rs.AddGroup()
            rs.AddObjectsToGroup(final_objs, group_name)
            
        rs.EnableRedraw(True)
        Rhino.RhinoDoc.ActiveDoc.Views.Redraw()

if __name__ == "__main__":
    main()