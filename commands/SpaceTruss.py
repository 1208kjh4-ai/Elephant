# -*- coding: utf-8 -*-
import System
import Rhino
import Rhino.Geometry as rg
import Eto.Forms as forms
import Eto.Drawing as drawing
import rhinoscriptsyntax as rs
import scriptcontext as sc

class SpaceTrussConduit(Rhino.Display.DisplayConduit):
    def __init__(self):
        super(SpaceTrussConduit, self).__init__()
        self.lines = []
        self.spheres = []
        self.color_pipe = System.Drawing.Color.DimGray
        self.color_sphere = System.Drawing.Color.Tomato
        self.rad_sphere = 0.0
        
    def DrawForeground(self, e):
        if self.lines:
            for line in self.lines:
                e.Display.DrawLine(line, self.color_pipe, 2)
        
        if self.spheres and self.rad_sphere > 0:
            for pt in self.spheres:
                sphere = rg.Sphere(pt, self.rad_sphere)
                e.Display.DrawSphere(sphere, self.color_sphere)

class SpaceTrussDialog(forms.Form):
    def __init__(self):
        super(SpaceTrussDialog, self).__init__()
        
    def SetupUI(self, base_surfaces):
        self.base_surfaces = base_surfaces 
        self.conduit = SpaceTrussConduit()
        self.conduit.Enabled = True
        
        self.preview_lines = []
        self.preview_nodes = []
        
        self.update_timer = forms.UITimer()
        self.update_timer.Interval = 0.2 
        self.update_timer.Elapsed += self.OnTimerElapsed
        
        self.Title = "Elephant Tools: 스페이스 트러스 (Multi-Surface)"
        self.Padding = drawing.Padding(10)
        self.Resizable = False
        self.Owner = Rhino.UI.RhinoEtoApp.MainWindow
        self.Topmost = True
        
        def_u = sc.sticky.get("SPTRUSS_U", 5)
        def_v = sc.sticky.get("SPTRUSS_V", 5)
        def_depth = sc.sticky.get("SPTRUSS_depth", 500)
        def_out = sc.sticky.get("SPTRUSS_out", "01. 커브 추출")
        def_rad = sc.sticky.get("SPTRUSS_rad", 30)
        def_sph = sc.sticky.get("SPTRUSS_sph", True)
        def_sph_rad = sc.sticky.get("SPTRUSS_sph_rad", 50)
        
        self.nud_u = forms.NumericUpDown(Value=def_u, MinValue=1, MaxValue=100, DecimalPlaces=0)
        self.nud_v = forms.NumericUpDown(Value=def_v, MinValue=1, MaxValue=100, DecimalPlaces=0)
        
        self.lbl_depth = forms.Label(Text="트러스 두께 (깊이):")
        self.nud_depth = forms.NumericUpDown(Value=def_depth, MinValue=-10000, MaxValue=10000, DecimalPlaces=0)
        self.nud_depth.Enabled = (len(self.base_surfaces) == 1)
        
        self.cb_output = forms.DropDown()
        self.cb_output.DataStore = ["01. 커브 추출", "02. 일반 파이프", "03. 멀티 파이프 (SubD)"]
        self.cb_output.SelectedValue = def_out
        
        self.nud_rad = forms.NumericUpDown(Value=def_rad, MinValue=1, MaxValue=1000, DecimalPlaces=0)
        self.nud_rad.Enabled = not ("커브" in def_out)
        
        self.chk_sphere = forms.CheckBox(Text="노드 조인트(Sphere) 생성", Checked=def_sph)
        self.nud_sph_rad = forms.NumericUpDown(Value=def_sph_rad, MinValue=1, MaxValue=2000, DecimalPlaces=0)
        self.nud_sph_rad.Enabled = bool(def_sph)
        
        self.cb_output.SelectedIndexChanged += self.OnOutputTypeChanged
        self.chk_sphere.CheckedChanged += self.OnSphereCheckedChanged
        
        self.nud_u.ValueChanged += self.OnUpdatePreview
        self.nud_v.ValueChanged += self.OnUpdatePreview
        self.nud_depth.ValueChanged += self.OnUpdatePreview
        self.nud_rad.ValueChanged += self.OnUpdatePreview
        self.nud_sph_rad.ValueChanged += self.OnUpdatePreview
        self.Closed += self.OnFormClosed 
        
        self.btn_ok = forms.Button(Text="생성하기")
        self.btn_ok.Click += self.OnOKButtonClick
        self.btn_cancel = forms.Button(Text="취소")
        self.btn_cancel.Click += self.OnCancelButtonClick
        
        layout = forms.DynamicLayout()
        layout.Spacing = drawing.Size(5, 10)
        
        # ⚠️ f-string 대신 파이썬 2.7 호환 안전한 문자열 결합으로 수정 완료
        layout.AddRow(forms.Label(Text="입력 서피스: " + str(len(self.base_surfaces)) + "개"), None)
        
        layout.AddRow(forms.Label(Text="U 분할:"), self.nud_u)
        layout.AddRow(forms.Label(Text="V 분할:"), self.nud_v)
        layout.AddRow(self.lbl_depth, self.nud_depth)
        layout.AddRow(None) 
        layout.AddRow(forms.Label(Text="프레임 출력:"), self.cb_output)
        layout.AddRow(forms.Label(Text="파이프 반지름:"), self.nud_rad)
        layout.AddRow(None)
        layout.AddRow(self.chk_sphere, None)
        layout.AddRow(forms.Label(Text="조인트 반지름:"), self.nud_sph_rad)
        layout.AddRow(None) 
        layout.AddRow(self.btn_ok, self.btn_cancel)
        
        self.Content = layout
        self.RunUpdateGeometry() 

    def OnOutputTypeChanged(self, sender, e):
        if "멀티" in self.cb_output.SelectedValue:
            msg = "주의 : 스페이스 트러스는 선의 개수가 매우 많아\n멀티파이프 연산 시 시간이 오래 걸릴 수 있습니다.\n진행하시겠습니까?"
            res = forms.MessageBox.Show(msg, "경고", forms.MessageBoxButtons.YesNo, forms.MessageBoxType.Warning)
            if res == forms.DialogResult.No:
                self.cb_output.SelectedIndex = 0 
                return
        self.nud_rad.Enabled = not ("커브" in self.cb_output.SelectedValue)
        self.OnUpdatePreview(None, None)
        
    def OnSphereCheckedChanged(self, sender, e):
        self.nud_sph_rad.Enabled = bool(self.chk_sphere.Checked)
        self.OnUpdatePreview(None, None)

    def OnUpdatePreview(self, sender, e):
        self.update_timer.Stop()
        self.update_timer.Start()
        
    def OnTimerElapsed(self, sender, e):
        self.update_timer.Stop()
        self.RunUpdateGeometry()
        
    def RunUpdateGeometry(self):
        lines, nodes = self.GenerateSpaceTrussLogic()
        self.preview_lines = lines
        self.preview_nodes = nodes
        
        self.conduit.lines = lines
        if bool(self.chk_sphere.Checked):
            self.conduit.spheres = nodes
            self.conduit.rad_sphere = float(self.nud_sph_rad.Value)
        else:
            self.conduit.spheres = []
            
        Rhino.RhinoDoc.ActiveDoc.Views.Redraw()
        
    def GenerateSpaceTrussLogic(self):
        div_u = int(self.nud_u.Value)
        div_v = int(self.nud_v.Value)
        depth = float(self.nud_depth.Value)
        
        lines = []
        all_nodes = []
        grids = []
        
        layer_count = max(2, len(self.base_surfaces))
        
        for s_idx in range(layer_count):
            srf = self.base_surfaces[s_idx] if s_idx < len(self.base_surfaces) else self.base_surfaces[0]
            
            dom_u = srf.Domain(0)
            dom_v = srf.Domain(1)
            is_shifted = (s_idx % 2 == 1) 
            
            grid_layer = []
            if is_shifted:
                for i in range(div_u):
                    row = []
                    u_mid = dom_u.Min + (dom_u.Max - dom_u.Min) * ((i + 0.5) / div_u)
                    for j in range(div_v):
                        v_mid = dom_v.Min + (dom_v.Max - dom_v.Min) * ((j + 0.5) / div_v)
                        pt = srf.PointAt(u_mid, v_mid)
                        
                        if len(self.base_surfaces) == 1:
                            normal = srf.NormalAt(u_mid, v_mid)
                            pt = pt - normal * depth
                            
                        row.append(pt)
                        all_nodes.append(pt)
                    grid_layer.append(row)
            else:
                for i in range(div_u + 1):
                    row = []
                    u_param = dom_u.Min + (dom_u.Max - dom_u.Min) * (float(i) / div_u)
                    for j in range(div_v + 1):
                        v_param = dom_v.Min + (dom_v.Max - dom_v.Min) * (float(j) / div_v)
                        pt = srf.PointAt(u_param, v_param)
                        row.append(pt)
                        all_nodes.append(pt)
                    grid_layer.append(row)
            grids.append(grid_layer)
            
        for layer_idx, grid in enumerate(grids):
            is_shifted = (layer_idx % 2 == 1)
            u_len = div_u if is_shifted else div_u + 1
            v_len = div_v if is_shifted else div_v + 1
            
            for i in range(u_len):
                for j in range(v_len):
                    if i < u_len - 1: lines.append(rg.Line(grid[i][j], grid[i+1][j]))
                    if j < v_len - 1: lines.append(rg.Line(grid[i][j], grid[i][j+1]))
                    
        for layer_idx in range(len(grids) - 1):
            grid_top = grids[layer_idx]
            grid_bot = grids[layer_idx + 1]
            
            if layer_idx % 2 == 0:
                for i in range(div_u):
                    for j in range(div_v):
                        bot_pt = grid_bot[i][j]
                        lines.append(rg.Line(bot_pt, grid_top[i][j]))
                        lines.append(rg.Line(bot_pt, grid_top[i+1][j]))
                        lines.append(rg.Line(bot_pt, grid_top[i][j+1]))
                        lines.append(rg.Line(bot_pt, grid_top[i+1][j+1]))
            else:
                for i in range(div_u):
                    for j in range(div_v):
                        top_pt = grid_top[i][j]
                        lines.append(rg.Line(top_pt, grid_bot[i][j]))
                        lines.append(rg.Line(top_pt, grid_bot[i+1][j]))
                        lines.append(rg.Line(top_pt, grid_bot[i][j+1]))
                        lines.append(rg.Line(top_pt, grid_bot[i+1][j+1]))

        return lines, all_nodes

    def OnOKButtonClick(self, sender, e):
        sc.sticky["SPTRUSS_U"] = self.nud_u.Value
        sc.sticky["SPTRUSS_V"] = self.nud_v.Value
        sc.sticky["SPTRUSS_depth"] = self.nud_depth.Value
        sc.sticky["SPTRUSS_out"] = self.cb_output.SelectedValue
        sc.sticky["SPTRUSS_rad"] = self.nud_rad.Value
        sc.sticky["SPTRUSS_sph"] = bool(self.chk_sphere.Checked)
        sc.sticky["SPTRUSS_sph_rad"] = self.nud_sph_rad.Value
        
        output_type = self.cb_output.SelectedValue
        radius = float(self.nud_rad.Value)
        make_spheres = bool(self.chk_sphere.Checked)
        sph_rad = float(self.nud_sph_rad.Value)
        baked_ids = []
        
        rs.EnableRedraw(False)
        
        if "커브" in output_type:
            for line in self.preview_lines:
                guid = Rhino.RhinoDoc.ActiveDoc.Objects.AddLine(line)
                if guid: baked_ids.append(guid)
                
        elif "일반" in output_type:
            tol = Rhino.RhinoDoc.ActiveDoc.ModelAbsoluteTolerance
            ang_tol = Rhino.RhinoDoc.ActiveDoc.ModelAngleToleranceRadians
            for line in self.preview_lines:
                crv = rg.LineCurve(line)
                breps = rg.Brep.CreatePipe(crv, radius, False, Rhino.Geometry.PipeCapMode.Flat, True, tol, ang_tol)
                if breps:
                    for b in breps:
                        guid = Rhino.RhinoDoc.ActiveDoc.Objects.AddBrep(b)
                        if guid: baked_ids.append(guid)
                        
        elif "멀티" in output_type:
            try:
                import ghpythonlib.components as ghcomp
                curves = [rg.LineCurve(line) for line in self.preview_lines]
                subd_res = ghcomp.MultiPipe(curves, radius, 0, 1)
                
                if subd_res:
                    if type(subd_res) is list or type(subd_res) is tuple:
                        for sd in subd_res:
                            guid = Rhino.RhinoDoc.ActiveDoc.Objects.AddSubD(sd)
                            if guid: baked_ids.append(guid)
                    else:
                        guid = Rhino.RhinoDoc.ActiveDoc.Objects.AddSubD(subd_res)
                        if guid: baked_ids.append(guid)
            except Exception as ex:
                print("⚠️ 멀티파이프 연산에 실패하여 커브 모드로 생성합니다. (" + str(ex) + ")")
                for line in self.preview_lines:
                    guid = Rhino.RhinoDoc.ActiveDoc.Objects.AddLine(line)
                    if guid: baked_ids.append(guid)

        if make_spheres and sph_rad > 0:
            for pt in self.preview_nodes:
                sphere = rg.Sphere(pt, sph_rad)
                guid = Rhino.RhinoDoc.ActiveDoc.Objects.AddBrep(sphere.ToBrep())
                if guid: baked_ids.append(guid)

        if baked_ids:
            group_name = rs.AddGroup() 
            if group_name:
                rs.AddObjectsToGroup(baked_ids, group_name)

        rs.EnableRedraw(True)
        print("성공적으로 스페이스 트러스가 생성되었습니다! 🐘🛠️")
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
    srf_ids = rs.GetObjects("스페이스 트러스를 생성할 곡면이나 평면(Surface)을 1~3개 선택하세요 (위층부터 순서대로).", 
                            rs.filter.surface, minimum_count=1, maximum_count=3, preselect=True)
    if not srf_ids: return
    
    base_surfaces = [rs.coercesurface(id) for id in srf_ids]
    
    dialog = SpaceTrussDialog()
    dialog.SetupUI(base_surfaces)
    dialog.Show()

if __name__ == "__main__":
    main()