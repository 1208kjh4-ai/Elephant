# -*- coding: utf-8 -*-
import System
import Rhino
import Rhino.Geometry as rg
import Eto.Forms as forms
import Eto.Drawing as drawing
import rhinoscriptsyntax as rs
import scriptcontext as sc
import math

class HBeamTrussConduit(Rhino.Display.DisplayConduit):
    def __init__(self):
        super(HBeamTrussConduit, self).__init__()
        self.lines = []
        self.breps = [] # 3D 프리뷰용 솔리드 리스트 추가
        self.color_line = System.Drawing.Color.DodgerBlue
        self.material = Rhino.Display.DisplayMaterial(self.color_line)
        self.material.Transparency = 0.1 # 솔리드 약간 투명하게
        
    def DrawForeground(self, e):
        # 솔리드가 없을 때만 선으로 표시 (Fallback)
        if self.lines and not self.breps:
            for line in self.lines:
                e.Display.DrawLine(line, self.color_line, 3)
                
        # 3D 솔리드 H형강 프리뷰 렌더링
        if self.breps:
            for brep in self.breps:
                # 면 렌더링
                e.Display.DrawBrepShaded(brep, self.material)
                # 검은색 테두리 라인 렌더링 (형태 뚜렷하게 구분)
                e.Display.DrawBrepWires(brep, System.Drawing.Color.Black)

class HBeamTrussDialog(forms.Form):
    def __init__(self):
        super(HBeamTrussDialog, self).__init__()
        
    def SetupUI(self, base_curves):
        self.base_curves = base_curves
        self.conduit = HBeamTrussConduit()
        self.conduit.Enabled = True
        self.preview_lines = []
        
        self.update_timer = forms.UITimer()
        self.update_timer.Interval = 0.15 
        self.update_timer.Elapsed += self.OnTimerElapsed
        
        self.Title = "Elephant Tools: H형강 트러스 생성기 V2"
        self.Padding = drawing.Padding(15)
        self.Resizable = False
        self.Owner = Rhino.UI.RhinoEtoApp.MainWindow
        self.Topmost = True
        
        def_div = sc.sticky.get("H_TRUSS_div", 10)
        def_type = sc.sticky.get("H_TRUSS_type", "03. 와렌 (Warren)") 
        def_H = sc.sticky.get("H_TRUSS_H", 200)
        def_B = sc.sticky.get("H_TRUSS_B", 200)
        def_t = sc.sticky.get("H_TRUSS_t", 10)
        def_flip = sc.sticky.get("H_TRUSS_flip", False)
        
        self.nud_div = forms.NumericUpDown(Value=def_div, MinValue=2, MaxValue=100, DecimalPlaces=0)
        self.cb_type = forms.DropDown()
        self.cb_type.DataStore = ["01. 프랫 (Pratt)", "02. 하우 (Howe)", "03. 와렌 (Warren)", "04. 더블 와렌 (Double Warren)"]
        self.cb_type.SelectedValue = def_type
        
        self.nud_H = forms.NumericUpDown(Value=def_H, MinValue=50, MaxValue=2000, DecimalPlaces=0)
        self.nud_B = forms.NumericUpDown(Value=def_B, MinValue=50, MaxValue=2000, DecimalPlaces=0)
        self.nud_t = forms.NumericUpDown(Value=def_t, MinValue=0, MaxValue=100, DecimalPlaces=1)
        
        self.chk_flip = forms.CheckBox(Text="방향 뒤집기 (Flip)", Checked=def_flip)
        
        control_layout = forms.DynamicLayout()
        control_layout.Spacing = drawing.Size(5, 10)
        control_layout.AddRow(forms.Label(Text="트러스 분할 수:"), self.nud_div)
        control_layout.AddRow(forms.Label(Text="트러스 유형:"), self.cb_type)
        control_layout.AddRow(None)
        control_layout.AddRow(forms.Label(Text="H (전체 높이):"), self.nud_H)
        control_layout.AddRow(forms.Label(Text="B (플랜지 폭):"), self.nud_B)
        control_layout.AddRow(forms.Label(Text="t (0=각관):"), self.nud_t)
        control_layout.AddRow(None)
        control_layout.AddRow(self.chk_flip, None)
        
        self.canvas = forms.Drawable()
        self.canvas.Size = drawing.Size(200, 200)
        self.canvas.Paint += self.OnPaintCanvas 
        
        canvas_box = forms.GroupBox(Text="단면 프리뷰")
        canvas_box.Padding = drawing.Padding(5)
        canvas_box.Content = self.canvas
        
        self.nud_div.ValueChanged += self.OnUpdatePreview
        self.cb_type.SelectedIndexChanged += self.OnUpdatePreview
        self.nud_H.ValueChanged += self.OnUpdatePreview
        self.nud_B.ValueChanged += self.OnUpdatePreview
        self.nud_t.ValueChanged += self.OnUpdatePreview
        self.chk_flip.CheckedChanged += self.OnUpdatePreview
        self.Closed += self.OnFormClosed 
        
        self.btn_ok = forms.Button(Text="생성하기")
        self.btn_ok.Click += self.OnOKButtonClick
        self.btn_cancel = forms.Button(Text="취소")
        self.btn_cancel.Click += self.OnCancelButtonClick
        
        main_layout = forms.DynamicLayout()
        main_layout.Spacing = drawing.Size(15, 15)
        main_layout.AddRow(control_layout, canvas_box)
        main_layout.AddRow(None)
        main_layout.AddRow(self.btn_ok, self.btn_cancel)
        
        self.Content = main_layout
        self.RunUpdateGeometry() 

    def OnPaintCanvas(self, sender, e):
        try:
            g = e.Graphics
            w, h = sender.Width, sender.Height
            if w <= 0 or h <= 0: return
            
            g.FillRectangle(drawing.Colors.WhiteSmoke, 0, 0, w, h)
            
            pen_grid = drawing.Pen(drawing.Colors.LightGray, 1)
            pen_grid.DashStyle = drawing.DashStyles.Dash
            g.DrawLine(pen_grid, 0, h/2, w, h/2)
            g.DrawLine(pen_grid, w/2, 0, w/2, h)
            
            val_H = float(self.nud_H.Value)
            val_B = float(self.nud_B.Value)
            val_t = float(self.nud_t.Value)
            
            # 꼬임 방지를 위해 두께를 폭과 높이의 절반-0.1 까지만 제한
            if val_t > 0.01:
                val_t = min(val_t, val_H/2.0 - 0.1, val_B/2.0 - 0.1)
            
            scale = 160.0 / max(val_H, val_B)
            def pt(x, y): return drawing.PointF(float(w/2 + x * scale), float(h/2 - y * scale))
            
            if val_t <= 0.01:
                pts = [
                    pt(val_B/2, val_H/2), pt(-val_B/2, val_H/2),
                    pt(-val_B/2, -val_H/2), pt(val_B/2, -val_H/2)
                ]
            else:
                pts = [
                    pt(val_B/2, val_H/2),        pt(-val_B/2, val_H/2),
                    pt(-val_B/2, val_H/2-val_t), pt(-val_t/2, val_H/2-val_t),
                    pt(-val_t/2, -val_H/2+val_t),pt(-val_B/2, -val_H/2+val_t),
                    pt(-val_B/2, -val_H/2),      pt(val_B/2, -val_H/2),
                    pt(val_B/2, -val_H/2+val_t), pt(val_t/2, -val_H/2+val_t),
                    pt(val_t/2, val_H/2-val_t),  pt(val_B/2, val_H/2-val_t)
                ]
            
            color_fill = drawing.Color(70.0/255.0, 130.0/255.0, 180.0/255.0, 0.8)
            color_stroke = drawing.Color(20.0/255.0, 50.0/255.0, 80.0/255.0, 1.0)
            
            # [수정] 오류 원천 차단: GraphicsPath를 사용하여 점을 하나씩 수동으로 이어 붙임
            path = drawing.GraphicsPath()
            for i in range(len(pts)):
                path.AddLine(pts[i], pts[(i+1) % len(pts)])
            path.CloseFigure()
            
            g.FillPath(color_fill, path)
            g.DrawPath(drawing.Pen(color_stroke, 1.5), path)
            
        except Exception as ex:
            print("Canvas Draw Error: " + str(ex))

    def OnUpdatePreview(self, sender, e):
        self.canvas.Invalidate() 
        self.update_timer.Stop()
        self.update_timer.Start()
        
    def OnTimerElapsed(self, sender, e):
        self.update_timer.Stop()
        self.RunUpdateGeometry()
        
    def RunUpdateGeometry(self):
        # 1. 뼈대 생성
        self.preview_lines = self.GenerateTrussLines()
        self.conduit.lines = self.preview_lines
        
        # 2. 실시간 솔리드 3D 렌더링 로직 추가
        val_H = float(self.nud_H.Value)
        val_B = float(self.nud_B.Value)
        val_t = float(self.nud_t.Value)
        is_flipped = bool(self.chk_flip.Checked)
        
        c1 = self.base_curves[0].DuplicateCurve()
        c2 = self.base_curves[1].DuplicateCurve()
        truss_normal, _, _ = self.GetTrussNormal(c1, c2)
        
        preview_breps = []
        for line in self.preview_lines:
            brep = self.CreateHBeamBrep(line, val_H, val_B, val_t, truss_normal, is_flipped)
            if brep:
                preview_breps.append(brep)
                
        self.conduit.breps = preview_breps
        Rhino.RhinoDoc.ActiveDoc.Views.Redraw()
        
    def GetTrussNormal(self, c1, c2):
        v_span = c2.PointAtStart - c1.PointAtStart
        v_tan = c1.TangentAt(c1.Domain.Min)
        truss_normal = rg.Vector3d.CrossProduct(v_tan, v_span)
        if truss_normal.Length < 1e-5: truss_normal = rg.Vector3d.ZAxis
        truss_normal.Unitize()
        return truss_normal, v_span, v_tan
        
    def GenerateTrussLines(self):
        div = int(self.nud_div.Value)
        val_H = float(self.nud_H.Value)
        truss_type = self.cb_type.SelectedValue
        if not truss_type: truss_type = "03. 와렌 (Warren)" 
            
        lines = []
        c1 = self.base_curves[0].DuplicateCurve()
        c2 = self.base_curves[1].DuplicateCurve()
        
        p1_s, p1_e = c1.PointAtStart, c1.PointAtEnd
        p2_s, p2_e = c2.PointAtStart, c2.PointAtEnd
        if p1_s.DistanceTo(p2_e) + p1_e.DistanceTo(p2_s) < p1_s.DistanceTo(p2_s) + p1_e.DistanceTo(p2_e):
            c2.Reverse()

        truss_normal, v_span, v_tan = self.GetTrussNormal(c1, c2)
        v_inward = rg.Vector3d.CrossProduct(truss_normal, v_tan)
        v_inward.Unitize()
        if v_inward * v_span < 0: v_inward.Reverse() 
        
        c1.Translate(v_inward * (val_H / 2.0))
        c2.Translate(-v_inward * (val_H / 2.0))
            
        is_closed = c1.IsClosed 
        
        t_vals1 = c1.DivideByCount(div, True)
        t_vals2 = c2.DivideByCount(div, True)
        if not t_vals1 or not t_vals2: return []
            
        t_vals1 = list(t_vals1)
        t_vals2 = list(t_vals2)
        pts1, pts2 = [], []
        
        for t in t_vals1: pts1.append(c1.PointAt(t))
        if is_closed and len(pts1) == div: pts1.append(pts1[0])
            
        for t in t_vals2: pts2.append(c2.PointAt(t))
        if is_closed and len(pts2) == div: pts2.append(pts2[0])
            
        for c in range(len(pts1) - 1):
            lines.append(rg.Line(pts1[c], pts1[c+1]))
            lines.append(rg.Line(pts2[c], pts2[c+1]))
            
        for c in range(len(pts1) - 1):
            p00 = pts1[c]       
            p10 = pts1[c+1]     
            p01 = pts2[c]       
            p11 = pts2[c+1]     
            
            is_left_half = (c < div / 2.0)
            
            if "프랫" in truss_type:
                lines.append(rg.Line(p00, p01))
                if c == len(pts1) - 2: lines.append(rg.Line(p10, p11))
                if is_left_half: lines.append(rg.Line(p01, p10))
                else: lines.append(rg.Line(p00, p11))            
                    
            elif "하우" in truss_type:
                lines.append(rg.Line(p00, p01)) 
                if c == len(pts1) - 2: lines.append(rg.Line(p10, p11))
                if is_left_half: lines.append(rg.Line(p00, p11)) 
                else: lines.append(rg.Line(p01, p10))            
                    
            elif "와렌" in truss_type:
                if c == 0 and not is_closed: lines.append(rg.Line(p00, p01))
                if c == len(pts1) - 2 and not is_closed: lines.append(rg.Line(p10, p11))
                if c % 2 == 0: lines.append(rg.Line(p00, p11)) 
                else: lines.append(rg.Line(p01, p10))          
                    
            elif "더블 와렌" in truss_type:
                if c == 0 and not is_closed: lines.append(rg.Line(p00, p01))
                if c == len(pts1) - 2 and not is_closed: lines.append(rg.Line(p10, p11))
                lines.append(rg.Line(p00, p11))
                lines.append(rg.Line(p01, p10))
        return lines
        
    def CreateHBeamBrep(self, line, H, B, t, truss_normal, is_flipped):
        v_dir = line.Direction
        if v_dir.Length < 1e-5: return None
        
        Z = v_dir
        X = truss_normal
        Y = rg.Vector3d.CrossProduct(Z, X)
        
        if Y.Length < 1e-5:
            X = rg.Vector3d.ZAxis if abs(Z.Z) < 0.9 else rg.Vector3d.XAxis
            Y = rg.Vector3d.CrossProduct(Z, X)
            
        Y.Unitize()
        X = rg.Vector3d.CrossProduct(Y, Z)
        X.Unitize()
        
        plane = rg.Plane(line.From, X, Y)
        
        flip_dir = 1.0 if is_flipped else -1.0
        plane.Origin = plane.Origin + X * (B / 2.0 * flip_dir)
        
        if t <= 0.01:
            pts = [
                plane.PointAt(B/2, H/2), plane.PointAt(-B/2, H/2),
                plane.PointAt(-B/2, -H/2), plane.PointAt(B/2, -H/2),
                plane.PointAt(B/2, H/2)
            ]
        else:
            t = min(t, H/2.0 - 0.1, B/2.0 - 0.1) 
            pts = [
                plane.PointAt(B/2, H/2),        plane.PointAt(-B/2, H/2),
                plane.PointAt(-B/2, H/2-t),     plane.PointAt(-t/2, H/2-t),
                plane.PointAt(-t/2, -H/2+t),    plane.PointAt(-B/2, -H/2+t),
                plane.PointAt(-B/2, -H/2),      plane.PointAt(B/2, -H/2),
                plane.PointAt(B/2, -H/2+t),     plane.PointAt(t/2, -H/2+t),
                plane.PointAt(t/2, H/2-t),      plane.PointAt(B/2, H/2-t),
                plane.PointAt(B/2, H/2) 
            ]
        
        crv = rg.Polyline(pts).ToNurbsCurve()
        extrusion = rg.Extrusion.Create(crv, line.Length, True)
        if extrusion:
            return extrusion.ToBrep()
        return None

    def OnOKButtonClick(self, sender, e):
        sc.sticky["H_TRUSS_div"] = self.nud_div.Value
        sc.sticky["H_TRUSS_type"] = self.cb_type.SelectedValue
        sc.sticky["H_TRUSS_H"] = self.nud_H.Value
        sc.sticky["H_TRUSS_B"] = self.nud_B.Value
        sc.sticky["H_TRUSS_t"] = self.nud_t.Value
        sc.sticky["H_TRUSS_flip"] = bool(self.chk_flip.Checked)
        
        val_H = float(self.nud_H.Value)
        val_B = float(self.nud_B.Value)
        val_t = float(self.nud_t.Value)
        is_flipped = bool(self.chk_flip.Checked)
        
        c1 = self.base_curves[0].DuplicateCurve()
        c2 = self.base_curves[1].DuplicateCurve()
        truss_normal, _, _ = self.GetTrussNormal(c1, c2)
        
        baked_ids = []
        rs.EnableRedraw(False)
        
        for line in self.preview_lines:
            brep = self.CreateHBeamBrep(line, val_H, val_B, val_t, truss_normal, is_flipped)
            if brep:
                guid = Rhino.RhinoDoc.ActiveDoc.Objects.AddBrep(brep)
                if guid: baked_ids.append(guid)

        if baked_ids:
            group_name = rs.AddGroup() 
            if group_name:
                rs.AddObjectsToGroup(baked_ids, group_name)

        rs.EnableRedraw(True)
        print("성공적으로 H형강 트러스가 생성되었습니다! 🐘🛠️")
        self.Close()
        
    def OnCancelButtonClick(self, sender, e):
        self.Close()
        
    def OnFormClosed(self, sender, e):
        self.conduit.Enabled = False
        Rhino.RhinoDoc.ActiveDoc.Views.Redraw()
        if self.update_timer:
            self.update_timer.Stop()
            self.update_timer.Dispose()

def main():
    crv_ids = rs.GetObjects("H형강 트러스를 생성할 기준 커브 2개를 순서대로 선택하세요.", rs.filter.curve, minimum_count=2, maximum_count=2, preselect=True)
    if not crv_ids or len(crv_ids) != 2:
        return
        
    base_curves = [rs.coercecurve(id) for id in crv_ids]
    
    dialog = HBeamTrussDialog()
    dialog.SetupUI(base_curves)
    dialog.Show()

if __name__ == "__main__":
    main()