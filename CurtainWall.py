# -*- coding: utf-8 -*-
import Rhino
import Rhino.Geometry as rg
import Rhino.Display as rd
import Eto.Forms as forms
import Eto.Drawing as drawing
import rhinoscriptsyntax as rs
import scriptcontext as sc  # 💡 [추가] 설정값을 기억하기 위한 모듈
import System
import math

# ==============================================================================
# [1. 통합 미리보기 엔진]
# ==============================================================================
class CurtainWallConduit(rd.DisplayConduit):
    def __init__(self):
        rd.DisplayConduit.__init__(self)
        self.preview_frames = []
        self.preview_glass = None
        self.arrow_brep = None
        self.frame_mat = rd.DisplayMaterial(System.Drawing.Color.Indigo)
        self.glass_mat = rd.DisplayMaterial(System.Drawing.Color.LightSkyBlue)
        self.glass_mat.Transparency = 0.6 
        self.glass_mat.Emission = System.Drawing.Color.LightCyan
        self.arrow_mat = rd.DisplayMaterial(System.Drawing.Color.Red)
        self.arrow_mat.Transparency = 0.2

    def DrawForeground(self, e):
        for brep in self.preview_frames:
            if brep and brep.IsValid:
                e.Display.DrawBrepShaded(brep, self.frame_mat)
                e.Display.DrawBrepWires(brep, System.Drawing.Color.Black, 1)
        if self.preview_glass and self.preview_glass.IsValid:
            e.Display.DrawBrepShaded(self.preview_glass, self.glass_mat)
        if self.arrow_brep and self.arrow_brep.IsValid:
            e.Display.DrawBrepShaded(self.arrow_brep, self.arrow_mat)
            e.Display.DrawBrepWires(self.arrow_brep, System.Drawing.Color.Maroon, 3)

# ==============================================================================
# [2. 커튼월 세부 설정 창]
# ==============================================================================
class CurtainWallDialog(forms.Dialog[bool]):
    def __init__(self, base_curve):
        self.Title = "커튼월 생성기"
        self.Padding = drawing.Padding(20)
        self.Resizable = True
        self.Topmost = True 
        self.base_curve = base_curve
        self.conduit = CurtainWallConduit()
        self.conduit.Enabled = True

        # 💡 [추가] 이전에 저장된 설정값이 있는지 확인하는 헬퍼 함수
        def get_sticky(key, default):
            return sc.sticky[key] if key in sc.sticky else default

        # 💡 [수정] 기본값 대신 get_sticky()를 사용하여 이전 값 불러오기
        self.txt_height = forms.TextBox(Text=str(get_sticky("cw_height", "4000")))
        self.txt_v_space = forms.TextBox(Text=str(get_sticky("cw_v_space", "1000")))
        self.txt_v_space.Width = 50
        self.btn_apply_v = forms.Button(Text="확인")
        self.btn_apply_v.Width = 30
        self.txt_h_space = forms.TextBox(Text=str(get_sticky("cw_h_space", "1000, 3000")))
        self.txt_floors = forms.TextBox(Text=str(get_sticky("cw_floors", "1")))     
        self.txt_floors.Width = 100      
        self.cb_flip = forms.CheckBox(Text="방향 뒤집기 (Flip)")
        self.cb_flip.Checked = get_sticky("cw_flip", False)
        
        self.m_thick = forms.TextBox(Text=str(get_sticky("cw_m_thick", "50")))
        self.m_depth = forms.TextBox(Text=str(get_sticky("cw_m_depth", "150")))
        self.m_extrude = forms.TextBox(Text=str(get_sticky("cw_m_extrude", "100")))
        
        self.t_thick = forms.TextBox(Text=str(get_sticky("cw_t_thick", "50")))
        self.t_depth = forms.TextBox(Text=str(get_sticky("cw_t_depth", "100")))
        self.t_extrude = forms.TextBox(Text=str(get_sticky("cw_t_extrude", "0")))

        v_layout = forms.DynamicLayout()
        v_layout.BeginHorizontal()
        v_layout.Add(self.txt_v_space, True, False)
        v_layout.Add(self.btn_apply_v, False, False)
        v_layout.EndHorizontal()

        layout = forms.DynamicLayout()
        layout.AddRow(forms.Label(Text="[기본 설정]", Font=drawing.Font("맑은 고딕", 10, drawing.FontStyle.Bold)))
        layout.AddRow("기준 층 높이:", self.txt_height, "층 수 (Floor):", self.txt_floors)
        layout.AddRow("멀리언 간격:", v_layout, self.cb_flip)
        layout.AddRow("트랜섬 높이 (쉼표 구분):", self.txt_h_space)
        layout.AddRow(None) 
        layout.AddRow(forms.Label(Text="[멀리언]", Font=drawing.Font("맑은 고딕", 10, drawing.FontStyle.Bold)))
        layout.AddRow("두께 (Thickness):", self.m_thick)
        layout.AddRow("깊이 (Depth):", self.m_depth, "돌출 (Extrude):", self.m_extrude)
        layout.AddRow(None)
        layout.AddRow(forms.Label(Text="[트랜섬]", Font=drawing.Font("맑은 고딕", 10, drawing.FontStyle.Bold)))
        layout.AddRow("두께 (Thickness):", self.t_thick)
        layout.AddRow("깊이 (Depth):", self.t_depth, "돌출 (Extrude):", self.t_extrude)
        layout.AddRow(None)
        
        # 💡 [수정] 확인 버튼 클릭 시 현재 입력된 값들을 sticky에 저장
        btn_ok = forms.Button(Text="생성하기")
        def on_ok(sender, e):
            sc.sticky["cw_height"] = self.txt_height.Text
            sc.sticky["cw_v_space"] = self.txt_v_space.Text
            sc.sticky["cw_h_space"] = self.txt_h_space.Text
            sc.sticky["cw_floors"] = self.txt_floors.Text
            sc.sticky["cw_flip"] = self.cb_flip.Checked
            sc.sticky["cw_m_thick"] = self.m_thick.Text
            sc.sticky["cw_m_depth"] = self.m_depth.Text
            sc.sticky["cw_m_extrude"] = self.m_extrude.Text
            sc.sticky["cw_t_thick"] = self.t_thick.Text
            sc.sticky["cw_t_depth"] = self.t_depth.Text
            sc.sticky["cw_t_extrude"] = self.t_extrude.Text
            self.Close(True)
            
        btn_ok.Click += on_ok
        
        layout.AddRow(btn_ok)
        self.Content = layout

        for ctrl in [self.txt_height, self.txt_h_space, self.txt_floors, self.m_thick, self.m_depth, self.m_extrude, self.t_thick, self.t_depth, self.t_extrude]: 
            ctrl.TextChanged += lambda s,e: self.Update()
        self.cb_flip.CheckedChanged += lambda s,e: self.Update()
        self.btn_apply_v.Click += lambda s,e: self.Update()
        self.txt_v_space.KeyDown += lambda s,e: self.Update() if e.Key == forms.Keys.Enter else None
        self.Update()

    def get_float(self, textbox, default_val):
        try: return float(textbox.Text)
        except: return default_val

    def get_int(self, textbox, default_val):
        try: return int(textbox.Text)
        except: return default_val

    def create_offset_solid(self, base_curve, target_outer, target_inner, dist_outer_mag, dist_inner_mag, height):
        def get_offset(curve, target_pt, dist_mag):
            if abs(dist_mag) < 0.001: 
                c = curve.DuplicateCurve()
                if c.PointAtStart.DistanceTo(target_pt) > c.PointAtEnd.DistanceTo(target_pt): c.Reverse()
                return c
            c1_arr = curve.Offset(rg.Plane.WorldXY, dist_mag, 0.01, rg.CurveOffsetCornerStyle.Sharp)
            c2_arr = curve.Offset(rg.Plane.WorldXY, -dist_mag, 0.01, rg.CurveOffsetCornerStyle.Sharp)
            c1 = rg.Curve.JoinCurves(c1_arr)[0] if c1_arr and len(c1_arr)>0 else None
            c2 = rg.Curve.JoinCurves(c2_arr)[0] if c2_arr and len(c2_arr)>0 else None
            def dist_to_target(c):
                if not c: return 9999999
                return min(c.PointAtStart.DistanceTo(target_pt), c.PointAtEnd.DistanceTo(target_pt))
            best_c = c1 if dist_to_target(c1) < dist_to_target(c2) else c2
            if not best_c: return None
            if best_c.PointAtStart.DistanceTo(target_pt) > best_c.PointAtEnd.DistanceTo(target_pt): best_c.Reverse()
            return best_c

        crv_outer = get_offset(base_curve, target_outer, dist_outer_mag)
        crv_inner = get_offset(base_curve, target_inner, dist_inner_mag)
        if not crv_outer or not crv_inner: return None
        
        l1 = rg.LineCurve(crv_outer.PointAtStart, crv_inner.PointAtStart)
        l2 = rg.LineCurve(crv_inner.PointAtEnd, crv_outer.PointAtEnd)
        
        joined = rg.Curve.JoinCurves([crv_outer, l1, crv_inner, l2])
        if joined and len(joined) > 0:
            base_face = joined[0]
            if base_face.ClosedCurveOrientation(rg.Plane.WorldXY) == rg.CurveOrientation.Clockwise: base_face.Reverse()
            solid = rg.Extrusion.Create(base_face, height, True)
            return solid.ToBrep() if solid else None
        return None

    def GenerateGeometry(self):
        H = self.get_float(self.txt_height, 3000.0)
        V_Space = max(100.0, self.get_float(self.txt_v_space, 1200.0))
        floors = max(1, self.get_int(self.txt_floors, 1))
        
        mT, mD, mE = self.get_float(self.m_thick, 50), self.get_float(self.m_depth, 150), self.get_float(self.m_extrude, 20)
        tT, tD, tE = self.get_float(self.t_thick, 50), self.get_float(self.t_depth, 100), self.get_float(self.t_extrude, 0)
        
        flip_dir = -1.0 if self.cb_flip.Checked else 1.0
        GLASS_THICK = 30.0 # 유리 두께

        transom_heights = []
        for token in self.txt_h_space.Text.split(','):
            try:
                val = float(token.strip())
                if 0 < val < H: transom_heights.append(val)
            except: pass

        divisions = max(1, int(round(self.base_curve.GetLength() / V_Space)))
        params = self.base_curve.DivideByCount(divisions, True)
        params = list(params) if params else [self.base_curve.Domain.Min, self.base_curve.Domain.Max]

        pts, inward_normals = [], []
        for t in params:
            pt = self.base_curve.PointAt(t)
            tan = self.base_curve.TangentAt(t)
            normal = rg.Vector3d.CrossProduct(tan, rg.Vector3d.ZAxis)
            normal.Unitize()
            inward_normals.append(normal * flip_dir)
            pts.append(pt)

        # 💡 [핵심] 유리와 프레임 시작점 오프셋 조정
        pt0, n0 = pts[0], inward_normals[0]
        glass_target_outer = pt0 
        glass_target_inner = pt0 + (n0 * GLASS_THICK)
        
        transom_target_outer = pt0 + n0 * (GLASS_THICK - tE)
        transom_target_inner = pt0 + n0 * (GLASS_THICK + tD)

        single_floor_frames = []
        for i in range(len(pts)):
            pt = pts[i]
            n = inward_normals[i]
            base_origin = pt + (n * GLASS_THICK)
            m_plane = rg.Plane(base_origin, rg.Vector3d.CrossProduct(n, rg.Vector3d.ZAxis), n)
            m_box = rg.Box(m_plane, rg.Interval(-mT/2, mT/2), rg.Interval(-mE, mD), rg.Interval(0, H))
            single_floor_frames.append(m_box.ToBrep())

        t_base_brep = self.create_offset_solid(self.base_curve, transom_target_outer, transom_target_inner, abs(GLASS_THICK - tE), abs(GLASS_THICK + tD), tT)
        if t_base_brep:
            for current_z in transom_heights:
                dup = t_base_brep.DuplicateBrep()
                dup.Translate(rg.Vector3d(0, 0, current_z - tT/2))
                single_floor_frames.append(dup)

        repeated_frames = []
        for f in range(floors):
            xform = rg.Transform.Translation(rg.Vector3d(0, 0, f * H))
            for brep in single_floor_frames:
                if brep:
                    dup = brep.DuplicateBrep()
                    dup.Transform(xform)
                    repeated_frames.append(dup)

        glass_brep = self.create_offset_solid(self.base_curve, glass_target_outer, glass_target_inner, 0.0, GLASS_THICK, H * floors)

        # 화살표 계산
        mid_pt = self.base_curve.PointAt(self.base_curve.Domain.Mid)
        mid_normal = rg.Vector3d.CrossProduct(self.base_curve.TangentAt(self.base_curve.Domain.Mid), rg.Vector3d.ZAxis) * (-1.0 * flip_dir)
        mid_normal.Unitize()
        right_dir = rg.Vector3d.CrossProduct(mid_normal, rg.Vector3d.ZAxis)
        
        base_pt = mid_pt + rg.Vector3d(0, 0, 100)
        neck_pt = base_pt + mid_normal * 3000.0
        
        arrow_poly = rg.Polyline([
            base_pt - right_dir * 250, base_pt + right_dir * 250,
            neck_pt + right_dir * 250, neck_pt + right_dir * 600,
            neck_pt + mid_normal * 1039.23,
            neck_pt - right_dir * 600, neck_pt - right_dir * 250,
            base_pt - right_dir * 250
        ])
        arrow_breps = rg.Brep.CreatePlanarBreps(rg.PolylineCurve(arrow_poly), 0.01)
        self.arrow_brep = arrow_breps[0] if arrow_breps else None

        return repeated_frames, glass_brep, self.arrow_brep

    def Update(self):
        frames, glass, arrow = self.GenerateGeometry()
        self.conduit.preview_frames = frames
        self.conduit.preview_glass = glass
        self.conduit.arrow_brep = arrow
        Rhino.RhinoDoc.ActiveDoc.Views.Redraw()

    def OnClosing(self, e):
        self.conduit.Enabled = False
        self.conduit.preview_frames = []
        self.conduit.preview_glass = None
        self.conduit.arrow_brep = None
        Rhino.RhinoDoc.ActiveDoc.Views.Redraw()
        super(CurtainWallDialog, self).OnClosing(e)
        
def ensure_custom_layer(name, color):
    doc = Rhino.RhinoDoc.ActiveDoc
    idx = doc.Layers.Find(name, True)
    if idx < 0:
        l = Rhino.DocObjects.Layer()
        l.Name = name
        l.Color = color
        idx = doc.Layers.Add(l)
    return idx

def main():
    crv_id = rs.GetObject("베이스 커브 선택", rs.filter.curve)
    if not crv_id: return
    base_curve = rs.coercecurve(crv_id)
    dlg = CurtainWallDialog(base_curve)
    if Rhino.UI.EtoExtensions.ShowSemiModal(dlg, Rhino.RhinoDoc.ActiveDoc, Rhino.UI.RhinoEtoApp.MainWindow):
        rs.EnableRedraw(False)
        frames, glass, _ = dlg.GenerateGeometry()
        final_objs = []
        frame_idx = ensure_custom_layer("Door_Frame", System.Drawing.Color.DarkGray)
        glass_idx = ensure_custom_layer("Door_Glass", System.Drawing.Color.LightSkyBlue)
        
        if frames:
            union = rg.Brep.CreateBooleanUnion(frames, Rhino.RhinoDoc.ActiveDoc.ModelAbsoluteTolerance)
            for b in (union if union else frames):
                attr = Rhino.DocObjects.ObjectAttributes()
                attr.LayerIndex = frame_idx
                final_objs.append(Rhino.RhinoDoc.ActiveDoc.Objects.AddBrep(b, attr))
        
        if glass and glass.IsValid:
            attr = Rhino.DocObjects.ObjectAttributes()
            attr.LayerIndex = glass_idx
            final_objs.append(Rhino.RhinoDoc.ActiveDoc.Objects.AddBrep(glass, attr))
            
        if final_objs: rs.AddObjectsToGroup(final_objs, rs.AddGroup())
        rs.EnableRedraw(True)
        Rhino.RhinoDoc.ActiveDoc.Views.Redraw()

if __name__ == "__main__":
    main()