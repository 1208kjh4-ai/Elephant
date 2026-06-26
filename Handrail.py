# -*- coding: utf-8 -*-
import Rhino
import Rhino.Geometry as rg
import scriptcontext as sc
import rhinoscriptsyntax as rs
import Eto.Forms as forms
import Eto.Drawing as drawing
import System

# --- [1] 실시간 화면 표시 엔진 (DisplayConduit) ---
class RailingPreviewConduit(Rhino.Display.DisplayConduit):
    def __init__(self):
        super(RailingPreviewConduit, self).__init__()
        self.preview_breps = []
        self.preview_color = System.Drawing.Color.Indigo
        self.wire_color = System.Drawing.Color.LightGray

    def UpdateGeometry(self, breps):
        self.preview_breps = breps

    def CalculateBoundingBox(self, e):
        if not self.preview_breps:
            return
        bbox = rg.BoundingBox.Empty
        for b in self.preview_breps:
            bbox.Union(b.GetBoundingBox(True))
        e.IncludeInBoundingBox(bbox)

    def PostDrawObjects(self, e):
        if not self.preview_breps:
            return
        display_mat = Rhino.Display.DisplayMaterial(self.preview_color)
        for b in self.preview_breps:
            e.Display.DrawBrepShaded(b, display_mat)
            e.Display.DrawBrepWires(b, self.wire_color, 1)


# --- [2] 지오메트리 계산 엔진 ---
class RailingEngine:
    def __init__(self, base_curve):
        self.base_curve = base_curve
        self.doc = Rhino.RhinoDoc.ActiveDoc
        self.tol = self.doc.ModelAbsoluteTolerance
        
        self.post_radius = 30.0
        self.member_radius = 30.0
        self.sub_member_radius = 20.0

    def calculate_geometry(self, total_height, post_interval, bottom_gap_on, post_on, panel_type, bar_qty, handrail_type, panel_rails_on, panel_gap):
        out_general = []
        out_panels = []
        
        bottom_gap_val = 200.0 if bottom_gap_on else 0.0
        handrail_gap = 0.0
        if handrail_type == 1: 
            handrail_gap = 150.0
            
        panel_height = total_height - bottom_gap_val - handrail_gap
        if panel_height < 10: panel_height = 10 
        
        z_bottom = bottom_gap_val
        z_panel_top = z_bottom + panel_height
        z_handrail = total_height

        crv_length = self.base_curve.GetLength()
        
        span_count = int(round(crv_length / post_interval))
        if span_count < 1: span_count = 1
        if span_count > 300: span_count = 300 
        
        divide_params = self.base_curve.DivideByCount(span_count, True)
        divide_points = [self.base_curve.PointAt(t) for t in divide_params]
        
        if post_on:
            for pt in divide_points:
                post_cyl = rg.Cylinder(rg.Circle(rg.Plane(pt, rg.Vector3d.ZAxis), self.post_radius), total_height)
                out_general.append(post_cyl.ToBrep(True, True))
                
        spans = []
        for i in range(span_count):
            t0 = divide_params[i]
            t1 = divide_params[i+1]
            sub_crv = self.base_curve.Trim(t0, t1)
            if not sub_crv: continue
                
            # 💡 [수정된 논리] 음수 연장 방식 대신, 길이를 재서 직접 잘라내는(Trim) 방식 적용
            if not post_on and panel_gap > 0: 
                sub_len = sub_crv.GetLength()
                if sub_len > panel_gap:
                    # 양 끝에서 gap/2 만큼 떨어진 파라미터(위치)를 찾음
                    success0, pt0_t = sub_crv.LengthParameter(panel_gap / 2.0)
                    success1, pt1_t = sub_crv.LengthParameter(sub_len - (panel_gap / 2.0))
                    # 해당 파라미터 기준으로 커브를 잘라냄
                    if success0 and success1 and pt0_t < pt1_t:
                        sub_crv = sub_crv.Trim(pt0_t, pt1_t)
            
            if sub_crv: spans.append(sub_crv)

        for span_crv in spans:
            if panel_rails_on:
                for z_val in [z_bottom, z_panel_top]:
                    bar_crv = span_crv.Duplicate()
                    bar_crv.Translate(rg.Vector3d(0, 0, z_val)) 
                    out_general.extend(self.create_pipe(bar_crv, self.sub_member_radius))
            
            if panel_type == 0: 
                base_panel_crv = span_crv.Duplicate()
                base_panel_crv.Translate(rg.Vector3d(0, 0, z_bottom))
                thickness = 10.0
                
                try:
                    t_mid = base_panel_crv.Domain.Mid
                    vec_t = base_panel_crv.TangentAt(t_mid)
                    vec_n = rg.Vector3d.CrossProduct(vec_t, rg.Vector3d.ZAxis)
                    
                    if vec_n.Length < 1e-6: 
                        vec_n = rg.Vector3d.XAxis
                    vec_n.Unitize()
                    
                    crv_right = base_panel_crv.Duplicate()
                    crv_right.Translate(vec_n * thickness)
                    
                    crv_left = base_panel_crv.Duplicate()
                    crv_left.Translate(vec_n * -thickness)
                    crv_left.Reverse() 
                    
                    line1 = rg.Line(crv_right.PointAtEnd, crv_left.PointAtStart).ToNurbsCurve()
                    line2 = rg.Line(crv_left.PointAtEnd, crv_right.PointAtStart).ToNurbsCurve()
                    
                    joined = rg.Curve.JoinCurves([crv_right, line1, crv_left, line2])
                    if joined and joined[0].IsClosed:
                        extrusion_srf = rg.Surface.CreateExtrusion(joined[0], rg.Vector3d(0, 0, panel_height))
                        if extrusion_srf:
                            wall_brep = extrusion_srf.ToBrep()
                            capped = wall_brep.CapPlanarHoles(self.tol)
                            if capped:
                                out_panels.append(capped)
                            else:
                                out_panels.append(wall_brep)
                                
                except Exception as e:
                    srf = rg.Surface.CreateExtrusion(base_panel_crv, rg.Vector3d(0, 0, panel_height))
                    if srf: out_panels.append(srf.ToBrep())
                    
            elif panel_type == 1: 
                if bar_qty > 0:
                    step_z = panel_height / (bar_qty + 1)
                    for i in range(1, bar_qty + 1):
                        bar_z = z_bottom + (step_z * i)
                        h_bar_crv = span_crv.Duplicate()
                        h_bar_crv.Translate(rg.Vector3d(0, 0, bar_z))
                        out_general.extend(self.create_pipe(h_bar_crv, self.sub_member_radius))
                        
            elif panel_type == 2: 
                if bar_qty > 0:
                    v_params = span_crv.DivideByCount(bar_qty + 1, True)
                    for t in v_params[1:-1]:
                        pt = span_crv.PointAt(t)
                        p0 = pt + rg.Vector3d(0, 0, z_bottom) 
                        v_cyl = rg.Cylinder(rg.Circle(rg.Plane(p0, rg.Vector3d.ZAxis), self.sub_member_radius), panel_height)
                        out_general.append(v_cyl.ToBrep(True, True))

        if handrail_type == 1:
            hr_crv = self.base_curve.Duplicate()
            hr_crv.Translate(rg.Vector3d(0, 0, z_handrail))
            out_general.extend(self.create_pipe(hr_crv, self.member_radius))

        return out_general, out_panels

    def create_pipe(self, curve, radius):
        pipes = rg.Brep.CreatePipe(curve, radius, False, rg.PipeCapMode.Flat, True, self.tol, self.doc.ModelAngleToleranceRadians)
        return pipes if pipes else []


# --- [3] 실시간 제어 창 (Eto Modeless Form) ---
class RailingModelessDialog(forms.Form):
    def __init__(self):
        super(RailingModelessDialog, self).__init__()
        self.base_curve = None
        self.engine = None
        self.conduit = RailingPreviewConduit()
        
        self.bake_general = []
        self.bake_panels = []
        
        self.Title = "난간 생성기"
        self.Padding = drawing.Padding(12)
        self.Resizable = True
        self.Topmost = True 

        # Sticky 메모리 불러오기
        def_height = sc.sticky.get("RLG_Height", 1200)
        def_interval = sc.sticky.get("RLG_Interval", 1500)
        def_gap = sc.sticky.get("RLG_Gap", 20.0)
        def_btm_gap = sc.sticky.get("RLG_BtmGap", True)
        def_post = sc.sticky.get("RLG_Post", False) 
        def_panel_rails = sc.sticky.get("RLG_PanelRails", True)
        def_panel_type = sc.sticky.get("RLG_PanelType", 0)
        def_bar_qty = sc.sticky.get("RLG_BarQty", 5)
        def_handrail = sc.sticky.get("RLG_Handrail", 1)

        self.nud_height = forms.NumericStepper(Value=def_height, DecimalPlaces=0, Increment=50, MinValue=300, MaxValue=3000)
        self.nud_interval = forms.NumericStepper(Value=def_interval, DecimalPlaces=0, Increment=100, MinValue=300, MaxValue=5000)
        self.btn_apply_interval = forms.Button(Text="적용")
        
        self.nud_gap = forms.NumericStepper(Value=def_gap, DecimalPlaces=0, Increment=5, MinValue=0, MaxValue=500)
        
        self.chk_bottom_gap = forms.CheckBox(Text="바닥 띄움 (200mm)", Checked=def_btm_gap)
        self.chk_post = forms.CheckBox(Text="기둥 생성 (R=30)", Checked=def_post)
        self.chk_panel_rails = forms.CheckBox(Text="패널 상/하단 레일 생성", Checked=def_panel_rails)
        
        self.cb_panel_type = forms.DropDown()
        self.cb_panel_type.DataStore = ["01. 솔리드 (Solid)", "02. 가로 바 (Horizontal)", "03. 세로 바 (Vertical)"]
        self.cb_panel_type.SelectedIndex = def_panel_type
        
        self.nud_bar_qty = forms.NumericStepper(Value=def_bar_qty, DecimalPlaces=0, Increment=1, MinValue=0, MaxValue=50)
        
        self.cb_handrail = forms.DropDown()
        self.cb_handrail.DataStore = ["없음", "기본"] 
        self.cb_handrail.SelectedIndex = def_handrail

        self.btn_create = forms.Button(Text="생성")
        self.btn_cancel = forms.Button(Text="취소")

        # 이벤트 바인딩
        self.nud_height.ValueChanged += self.RefreshPreview
        self.btn_apply_interval.Click += self.RefreshPreview 
        self.chk_bottom_gap.CheckedChanged += self.RefreshPreview
        self.chk_post.CheckedChanged += self.RefreshPreview
        self.chk_panel_rails.CheckedChanged += self.RefreshPreview
        self.nud_gap.ValueChanged += self.RefreshPreview 
        self.cb_panel_type.SelectedIndexChanged += self.RefreshPreview
        self.nud_bar_qty.ValueChanged += self.RefreshPreview
        self.cb_handrail.SelectedIndexChanged += self.RefreshPreview

        self.btn_create.Click += self.OnCreateClick
        self.btn_cancel.Click += self.OnCancelClick
        self.Closed += self.OnFormClosed

        interval_layout = forms.StackLayout(Orientation=forms.Orientation.Horizontal, Spacing=5)
        interval_layout.Items.Add(self.nud_interval)
        interval_layout.Items.Add(self.btn_apply_interval)

        layout = forms.DynamicLayout()
        layout.Spacing = drawing.Size(6, 6)
        
        layout.AddRow(forms.Label(Text="난간 총 높이:"), self.nud_height)
        layout.AddRow(forms.Label(Text="기둥 간격:"), interval_layout)
        layout.AddRow(None)
        layout.AddRow(self.chk_post)
        layout.AddRow(forms.Label(Text="└ 기둥 OFF시 간격:"), self.nud_gap) 
        layout.AddRow(None)
        layout.AddRow(self.chk_bottom_gap)
        layout.AddRow(self.chk_panel_rails)
        layout.AddRow(None)
        layout.AddRow(forms.Label(Text="패널 타입:"), self.cb_panel_type)
        layout.AddRow(forms.Label(Text="바 개수:"), self.nud_bar_qty)
        layout.AddRow(None)
        layout.AddRow(forms.Label(Text="손잡이 유형:"), self.cb_handrail)
        layout.AddRow(None)
        layout.AddRow(self.btn_create, self.btn_cancel)

        self.Content = layout

    def save_settings_to_sticky(self):
        sc.sticky["RLG_Height"] = float(self.nud_height.Value)
        sc.sticky["RLG_Interval"] = float(self.nud_interval.Value)
        sc.sticky["RLG_Gap"] = float(self.nud_gap.Value) 
        sc.sticky["RLG_BtmGap"] = self.chk_bottom_gap.Checked
        sc.sticky["RLG_Post"] = self.chk_post.Checked
        sc.sticky["RLG_PanelRails"] = self.chk_panel_rails.Checked
        sc.sticky["RLG_PanelType"] = self.cb_panel_type.SelectedIndex
        sc.sticky["RLG_BarQty"] = int(self.nud_bar_qty.Value)
        sc.sticky["RLG_Handrail"] = self.cb_handrail.SelectedIndex

    def setup_curve(self, base_curve):
        self.base_curve = base_curve
        self.engine = RailingEngine(base_curve)
        self.conduit.Enabled = True
        self.RefreshPreview(None, None)

    def RefreshPreview(self, sender, e):
        if self.engine is None: return 
        self.save_settings_to_sticky()
            
        gen_breps, pan_breps = self.engine.calculate_geometry(
            total_height=float(self.nud_height.Value),
            post_interval=float(self.nud_interval.Value),
            bottom_gap_on=self.chk_bottom_gap.Checked,
            post_on=self.chk_post.Checked,
            panel_type=self.cb_panel_type.SelectedIndex,
            bar_qty=int(self.nud_bar_qty.Value),
            handrail_type=self.cb_handrail.SelectedIndex,
            panel_rails_on=self.chk_panel_rails.Checked,
            panel_gap=float(self.nud_gap.Value) 
        )
        
        self.bake_general = gen_breps
        self.bake_panels = pan_breps
        
        self.conduit.UpdateGeometry(gen_breps + pan_breps)
        Rhino.RhinoDoc.ActiveDoc.Views.Redraw()

    def OnCreateClick(self, sender, e):
        self.save_settings_to_sticky()
        self.conduit.Enabled = False 
        rs.EnableRedraw(False)
        
        layer_main = "Railing_Result"
        if not rs.IsLayer(layer_main):
            rs.AddLayer(layer_main, System.Drawing.Color.DarkSlateGray)
            
        layer_panel = "Handrail_Panel"
        if not rs.IsLayer(layer_panel):
            rs.AddLayer(layer_panel, System.Drawing.Color.LightSteelBlue)
            
        group_name = rs.AddGroup()
            
        for b in self.bake_general:
            obj_id = sc.doc.Objects.AddBrep(b)
            rs.ObjectLayer(obj_id, layer_main)
            if group_name: rs.AddObjectToGroup(obj_id, group_name)
            
        for b in self.bake_panels:
            obj_id = sc.doc.Objects.AddBrep(b)
            rs.ObjectLayer(obj_id, layer_panel)
            if group_name: rs.AddObjectToGroup(obj_id, group_name)
            
        rs.EnableRedraw(True)
        Rhino.RhinoDoc.ActiveDoc.Views.Redraw()
        print("난간 생성이 완료되었습니다!")
        self.Close()

    def OnCancelClick(self, sender, e):
        self.save_settings_to_sticky()
        self.Close()

    def OnFormClosed(self, sender, e):
        self.conduit.Enabled = False
        Rhino.RhinoDoc.ActiveDoc.Views.Redraw()


def main():
    crv_id = rs.GetObject("베이스 커브 선택.", rs.filter.curve)
    if not crv_id: return
    
    base_curve = rs.coercecurve(crv_id)
    if not base_curve: return

    dlg = RailingModelessDialog()
    dlg.setup_curve(base_curve)
    
    dlg.Owner = Rhino.UI.RhinoEtoApp.MainWindow
    dlg.Show()

if __name__ == "__main__":
    main()