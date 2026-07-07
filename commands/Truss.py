# -*- coding: utf-8 -*-
import Rhino
import Rhino.Geometry as rg
import scriptcontext as sc
import Eto.Drawing as drawing
import Eto.Forms as forms
import System
import math

# ==============================================================================
# 1. 실시간 프리뷰를 위한 Display Conduit
# ==============================================================================
class TrussPreviewConduit(Rhino.Display.DisplayConduit):
    def __init__(self):
        super(TrussPreviewConduit, self).__init__()
        self.joint_meshes = []
        self.member_meshes = []
        
        self.mat_joint = Rhino.Display.DisplayMaterial()
        self.mat_joint.Diffuse = System.Drawing.Color.DarkSlateGray
        
        self.mat_member = Rhino.Display.DisplayMaterial()
        self.mat_member.Diffuse = System.Drawing.Color.LightSteelBlue

    def update_meshes(self, joints, members):
        self.dispose_meshes()
        mp = Rhino.Geometry.MeshingParameters.FastRenderMesh
        
        for b in joints:
            meshes = rg.Mesh.CreateFromBrep(b, mp)
            if meshes: self.joint_meshes.extend(meshes)
            
        for b in members:
            meshes = rg.Mesh.CreateFromBrep(b, mp)
            if meshes: self.member_meshes.extend(meshes)

    def dispose_meshes(self):
        for m in self.joint_meshes: m.Dispose()
        for m in self.member_meshes: m.Dispose()
        self.joint_meshes = []
        self.member_meshes = []

    def DrawForeground(self, e):
        for m in self.joint_meshes:
            e.Display.DrawMeshShaded(m, self.mat_joint)
        for m in self.member_meshes:
            e.Display.DrawMeshShaded(m, self.mat_member)

# ==============================================================================
# 2. 메인 생성 로직 엔진 
# ==============================================================================
def generate_truss(crv0, crv1, result_type, pattern_type, div_cnt, thick, depth, node_r, fillet_mult, is_flipped):
    tol = sc.doc.ModelAbsoluteTolerance
    
    c0 = crv0.DuplicateCurve()
    c1 = crv1.DuplicateCurve()
    
    if c0.PointAtStart.DistanceTo(c1.PointAtEnd) < c0.PointAtStart.DistanceTo(c1.PointAtStart):
        c1.Reverse()
        
    p0_start, p0_end = c0.PointAtStart, c0.PointAtEnd
    p1_start, p1_end = c1.PointAtStart, c1.PointAtEnd
    
    all_corner_pts = [p0_start, p0_end, p1_end, p1_start]
    rc, plane = rg.Plane.FitPlaneToPoints(all_corner_pts)
    
    c1_rev = c1.DuplicateCurve()
    c1_rev.Reverse()
    l1 = rg.Line(p0_end, p1_end).ToNurbsCurve()
    l2 = rg.Line(p1_start, p0_start).ToNurbsCurve()
    
    joined = rg.Curve.JoinCurves([c0, l1, c1_rev, l2], tol)
    if not joined: return [], []
    outer_crv = joined[0]
    
    def get_offset(curve, dist, plane, tol, style, inward=True):
        o1 = curve.Offset(plane, dist, tol, style)
        o2 = curve.Offset(plane, -dist, tol, style)
        c1_off = o1[0] if (o1 and len(o1)>0) else None
        c2_off = o2[0] if (o2 and len(o2)>0) else None
        if c1_off and c2_off:
            if inward: return c1_off if c1_off.GetLength() < c2_off.GetLength() else c2_off
            else:      return c1_off if c1_off.GetLength() > c2_off.GetLength() else c2_off
        return c1_off or c2_off

    inner_crv = get_offset(outer_crv, thick/2.0, plane, tol, rg.CurveOffsetCornerStyle.Sharp, inward=True)
    if not inner_crv: return [], []

    segments = inner_crv.DuplicateSegments()
    if segments and len(segments) > 0:
        mid0 = c0.PointAtNormalizedLength(0.5)
        mid1 = c1.PointAtNormalizedLength(0.5)
        safe_crv0 = min(segments, key=lambda s: s.PointAtNormalizedLength(0.5).DistanceTo(mid0))
        safe_crv1 = min(segments, key=lambda s: s.PointAtNormalizedLength(0.5).DistanceTo(mid1))
    else:
        safe_crv0 = get_offset(c0, thick/2.0, plane, tol, rg.CurveOffsetCornerStyle.Sharp, inward=True)
        safe_crv1 = get_offset(c1, thick/2.0, plane, tol, rg.CurveOffsetCornerStyle.Sharp, inward=True)
        
    if safe_crv0.PointAtStart.DistanceTo(p0_start) > safe_crv0.PointAtStart.DistanceTo(p0_end):
        safe_crv0.Reverse()
    if safe_crv1.PointAtStart.DistanceTo(p1_start) > safe_crv1.PointAtStart.DistanceTo(p1_end):
        safe_crv1.Reverse()
        
    pts0 = list(safe_crv0.DivideByCount(div_cnt, True))
    pts1 = list(safe_crv1.DivideByCount(div_cnt, True))
    
    if not pts0 or not pts1: return [], []
    pts0 = [safe_crv0.PointAt(t) for t in pts0]
    pts1 = [safe_crv1.PointAt(t) for t in pts1]
    
    tris = []
    for i in range(div_cnt):
        p00, p01 = pts0[i], pts0[i+1]
        p10, p11 = pts1[i], pts1[i+1]
        
        if pattern_type == 0: 
            t1 = rg.Polyline([p00, p10, p11, p00]).ToNurbsCurve()
            t2 = rg.Polyline([p00, p11, p01, p00]).ToNurbsCurve()
            tris.extend([t1, t2])
        elif pattern_type == 1: 
            line1 = rg.Line(p00, p11)
            line2 = rg.Line(p10, p01)
            rc, a, b = rg.Intersect.Intersection.LineLine(line1, line2)
            center = line1.PointAt(a) if rc else (p00 + p01 + p10 + p11) / 4.0
            
            t1 = rg.Polyline([p00, p10, center, p00]).ToNurbsCurve()
            t2 = rg.Polyline([p10, p11, center, p10]).ToNurbsCurve()
            t3 = rg.Polyline([p11, p01, center, p11]).ToNurbsCurve()
            t4 = rg.Polyline([p01, p00, center, p01]).ToNurbsCurve()
            tris.extend([t1, t2, t3, t4])
        elif pattern_type == 2: 
            if i % 2 == 0:
                t1 = rg.Polyline([p00, p10, p11, p00]).ToNurbsCurve()
                t2 = rg.Polyline([p00, p11, p01, p00]).ToNurbsCurve()
            else:
                t1 = rg.Polyline([p00, p10, p01, p00]).ToNurbsCurve()
                t2 = rg.Polyline([p10, p11, p01, p10]).ToNurbsCurve()
            tris.extend([t1, t2])

    # 💡 [사용자 제안 핵심 알고리즘] 각도 비례형 가변 필렛 함수
    def apply_variable_fillet(crv, mult):
        rc, poly = crv.TryGetPolyline()
        if not rc or poly.Count < 4: return crv
        n = poly.Count - 1
        
        radii = []
        tangents = []
        for i in range(n):
            p_prev = poly[(i - 1) % n]
            p_curr = poly[i]
            p_next = poly[(i + 1) % n]
            
            v1 = p_prev - p_curr
            v2 = p_next - p_curr
            L1, L2 = v1.Length, v2.Length
            
            if L1 < tol or L2 < tol:
                radii.append(0); tangents.append(0); continue
                
            ang_rad = rg.Vector3d.VectorAngle(v1, v2)
            ang_deg = math.degrees(ang_rad)
            
            # 사용자 공식: 반지름(R) = 각도(deg) * 상수(mult)
            r = ang_deg * mult
            
            # 뼈대가 얇아지거나 꼬이는 것을 방지하기 위한 안전 장치 (Segment 길이의 48% 제한)
            t_max = min(L1, L2) * 0.48
            if 0.01 < ang_rad < math.pi * 0.99:
                tan_half = math.tan(ang_rad / 2.0)
                r_max = t_max * tan_half
                if r > r_max: r = r_max
                t = r / tan_half
            else:
                r, t = 0, 0
                
            radii.append(r); tangents.append(t)
            
        crvs_to_join = []
        for i in range(n):
            p_curr = poly[i]
            p_next = poly[(i + 1) % n]
            t_curr, t_next = tangents[i], tangents[(i + 1) % n]
            
            v = p_next - p_curr
            if v.Length < tol: continue
            v.Unitize()
            
            # 필렛을 제외한 남은 직선 구간 생성
            pt_start = p_curr + v * t_curr
            pt_end = p_next - v * t_next
            if pt_start.DistanceTo(pt_end) > tol:
                crvs_to_join.append(rg.Line(pt_start, pt_end).ToNurbsCurve())
                
            # 다음 모서리의 필렛(Arc) 호 생성
            r_next = radii[(i+1)%n]
            if r_next > tol:
                p_nn = poly[(i + 2) % n]
                v_in = p_curr - p_next
                v_in.Unitize()
                v_out = p_nn - p_next
                v_out.Unitize()
                
                pt_arc_start = p_next + v_in * t_next
                pt_arc_end = p_next + v_out * t_next
                
                if pt_arc_start.DistanceTo(pt_arc_end) > tol:
                    arc = rg.Arc(pt_arc_start, v_in * -1, pt_arc_end)
                    crvs_to_join.append(arc.ToNurbsCurve())

        joined = rg.Curve.JoinCurves(crvs_to_join, tol * 10)
        if joined and len(joined) > 0:
            joined_crv = joined[0]
            if not joined_crv.IsClosed: joined_crv.MakeClosed(tol * 10)
            return joined_crv
        return crv

    holes = []
    for t in tris:
        valid_c = get_offset(t, thick/2.0, plane, tol, rg.CurveOffsetCornerStyle.Sharp, inward=True)
        if valid_c and valid_c.IsClosed:
            if result_type in [0, 2] and fillet_mult > 0:
                # 💡 가변 필렛(Variable Fillet) 적용!
                valid_c = apply_variable_fillet(valid_c, fillet_mult)
            holes.append(valid_c)

    base_breps = rg.Brep.CreatePlanarBreps([outer_crv] + holes, tol)
    if not base_breps: return [], []
    base_brep = base_breps[0]

    vec = plane.Normal * (-depth if is_flipped else depth)

    def extrude_2d_brep(b):
        edges = rg.Curve.JoinCurves(b.DuplicateNakedEdgeCurves(True, False), tol)
        walls = [rg.Surface.CreateExtrusion(c, vec).ToBrep() for c in edges if c]
        walls.append(b)
        btop = b.DuplicateBrep()
        btop.Transform(rg.Transform.Translation(vec))
        walls.append(btop)
        joined = rg.Brep.JoinBreps(walls, tol)
        if joined:
            return joined[0] 
        return b

    if result_type == 0:
        return [extrude_2d_brep(base_brep)], []

    safe_all_pts = []
    unique_lines = []
    midpoints = []

    for t in tris:
        rc, poly = t.TryGetPolyline()
        if rc:
            for i in range(poly.Count - 1):
                pA = poly[i]
                pB = poly[i+1]
                
                dup_pt = False
                for sp in safe_all_pts:
                    if pA.DistanceTo(sp) < tol:
                        dup_pt = True
                        break
                if not dup_pt: safe_all_pts.append(pA)

                if pA.DistanceTo(pB) < tol: continue
                line = rg.Line(pA, pB)
                mid = line.PointAt(0.5)
                
                is_dup = False
                for m in midpoints:
                    if m.DistanceTo(mid) < tol:
                        is_dup = True
                        break
                if not is_dup:
                    midpoints.append(mid)
                    unique_lines.append(line)

    cutters = System.Collections.Generic.List[rg.Curve]()
    for line in unique_lines:
        L = line.Length
        if L < node_r * 2.1: continue
        
        v = line.To - line.From
        v.Unitize()
        perp = rg.Vector3d.CrossProduct(v, plane.ZAxis)
        perp.Unitize()
        cut_dist = thick * 1.5 

        pt1 = line.From + v * node_r
        c1 = rg.Line(pt1 - perp * cut_dist, pt1 + perp * cut_dist).ToNurbsCurve()
        cutters.Add(c1)

        pt2 = line.To - v * node_r
        c2 = rg.Line(pt2 - perp * cut_dist, pt2 + perp * cut_dist).ToNurbsCurve()
        cutters.Add(c2)
        
    split_breps = base_brep.Split(cutters, tol)
    if not split_breps:
        return [extrude_2d_brep(base_brep)], []

    joints_2d = []
    members_2d = []
    
    for b in split_breps:
        amp = rg.AreaMassProperties.Compute(b)
        center = amp.Centroid if amp else b.GetBoundingBox(True).Center
        
        min_dist = min([center.DistanceTo(p) for p in safe_all_pts])
        if min_dist < node_r * 1.2:
            joints_2d.append(b)
        else:
            members_2d.append(b)

    final_joints = [extrude_2d_brep(j) for j in joints_2d]
    final_members = [extrude_2d_brep(m) for m in members_2d]

    return final_joints, final_members

# ==============================================================================
# 3. 사용자 UI 팝업창 
# ==============================================================================
class TrussModelessDialog(forms.Form):
    def __init__(self):
        super(TrussModelessDialog, self).__init__()
        self.Title = "지능형 파라메트릭 트러스 생성기"
        self.ClientSize = drawing.Size(340, 480) 
        self.Padding = drawing.Padding(10)
        self.Resizable = False
        self.Topmost = True

        self.crv0 = None
        self.crv1 = None

        self.conduit = TrussPreviewConduit()
        self.conduit.Enabled = True
        
        self.timer = forms.UITimer()
        self.timer.Interval = 0.2
        self.timer.Elapsed += self.on_timer_elapsed

        self.final_joints = []
        self.final_members = []
        
        self.setup_ui()

    def set_curves(self, c0, c1):
        self.crv0 = c0
        self.crv1 = c1
        self.update_preview()

    def setup_ui(self):
        def get_val(key, default): return sc.sticky[key] if key in sc.sticky else default

        self.rb_type = forms.RadioButtonList()
        self.rb_type.Orientation = forms.Orientation.Vertical
        self.rb_type.Items.Add("Solid Truss (통짜 솔리드 - 필렛 연동)")
        self.rb_type.Items.Add("Joint Divided (직선 절단/분리)")
        self.rb_type.Items.Add("Fillet Joint (직선 절단 + 내부 필렛)")
        self.rb_type.SelectedIndex = get_val("TRUSS_TYPE", 2)
        self.rb_type.SelectedIndexChanged += self.on_value_changed

        self.rb_pattern = forms.RadioButtonList()
        self.rb_pattern.Orientation = forms.Orientation.Horizontal
        self.rb_pattern.Items.Add("단방향(N)")
        self.rb_pattern.Items.Add("교차형(X)")
        self.rb_pattern.Items.Add("지그재그(V)")
        self.rb_pattern.SelectedIndex = get_val("TRUSS_PATTERN", 1)
        self.rb_pattern.SelectedIndexChanged += self.on_value_changed

        self.nud_div = forms.NumericUpDown(Value=get_val("TRUSS_DIV", 6), MinValue=1, MaximumDecimalPlaces=0, Width=100)
        self.nud_thick = forms.NumericUpDown(Value=get_val("TRUSS_THICK", 30.0), MinValue=1.0, DecimalPlaces=1, Width=100)
        self.nud_depth = forms.NumericUpDown(Value=get_val("TRUSS_DEPTH", 50.0), MinValue=1.0, DecimalPlaces=1, Width=100)
        self.nud_noder = forms.NumericUpDown(Value=get_val("TRUSS_NODER", 80.0), MinValue=5.0, DecimalPlaces=1, Width=100)
        
        # 💡 [핵심 UI 수정] 절대 수치가 아닌 '각도 비례 계수(Multiplier)'로 컨트롤!
        self.nud_fillet = forms.NumericUpDown(Value=get_val("TRUSS_FILLET_MULT", 0.5), MinValue=0.0, MaxValue=5.0, DecimalPlaces=2, Increment=0.1, Width=100)
        
        self.chk_flip = forms.CheckBox(Text="돌출 방향 반전 (Flip)")
        self.chk_flip.Checked = get_val("TRUSS_FLIP", False)

        controls = [self.nud_div, self.nud_thick, self.nud_depth, self.nud_noder, self.nud_fillet, self.chk_flip]
        for ctrl in controls: 
            if isinstance(ctrl, forms.CheckBox):
                ctrl.CheckedChanged += self.on_value_changed
            else:
                ctrl.ValueChanged += self.on_value_changed

        layout = forms.DynamicLayout()
        layout.Spacing = drawing.Size(5, 10)
        
        layout.AddRow(forms.Label(Text="▶ 출력 방식"))
        layout.AddRow(self.rb_type)
        layout.AddRow(forms.Label(Text=" "))
        layout.AddRow(forms.Label(Text="▶ 트러스 패턴"))
        layout.AddRow(self.rb_pattern)
        layout.AddRow(forms.Label(Text=" "))
        
        layout.AddRow(forms.Label(Text="분할 개수 (Divisions):"), self.nud_div)
        layout.AddRow(forms.Label(Text="부재 두께 (Thickness):"), self.nud_thick)
        layout.AddRow(forms.Label(Text="돌출 깊이 (Depth):"), self.nud_depth)
        layout.AddRow(forms.Label(Text=" "), self.chk_flip)
        layout.AddRow(forms.Label(Text="노드 반경 (Node Radius):"), self.nud_noder)
        layout.AddRow(forms.Label(Text="각도 비례 계수 (Angle × k):"), self.nud_fillet) # 텍스트 라벨 변경
        layout.AddRow(None)

        btn_create = forms.Button(Text="생성 및 창 닫기", Height=30)
        btn_create.Click += self.on_create_click
        layout.AddRow(btn_create)

        self.Content = layout

    def on_value_changed(self, sender, e):
        self.timer.Start()

    def on_timer_elapsed(self, sender, e):
        self.timer.Stop()
        self.update_preview()

    def update_preview(self):
        if not self.crv0 or not self.crv1: return 
        
        joints, members = generate_truss(
            self.crv0, self.crv1, 
            self.rb_type.SelectedIndex,
            self.rb_pattern.SelectedIndex,
            int(self.nud_div.Value), 
            self.nud_thick.Value, 
            self.nud_depth.Value, 
            self.nud_noder.Value, 
            self.nud_fillet.Value, # 0.0 ~ 5.0 계수 전달
            self.chk_flip.Checked
        )
        self.final_joints = joints
        self.final_members = members
        self.conduit.update_meshes(joints, members)
        sc.doc.Views.Redraw()

    def save_sticky(self):
        sc.sticky["TRUSS_TYPE"] = self.rb_type.SelectedIndex
        sc.sticky["TRUSS_PATTERN"] = self.rb_pattern.SelectedIndex
        sc.sticky["TRUSS_DIV"] = int(self.nud_div.Value)
        sc.sticky["TRUSS_THICK"] = self.nud_thick.Value
        sc.sticky["TRUSS_DEPTH"] = self.nud_depth.Value
        sc.sticky["TRUSS_NODER"] = self.nud_noder.Value
        sc.sticky["TRUSS_FILLET_MULT"] = self.nud_fillet.Value
        sc.sticky["TRUSS_FLIP"] = self.chk_flip.Checked

    def on_create_click(self, sender, e):
        self.save_sticky()
        
        rs_joint = Rhino.DocObjects.Layer.GetDefaultLayerProperties()
        rs_joint.Name = "Truss_Joint"
        rs_joint.Color = System.Drawing.Color.DarkSlateGray
        l_joint = sc.doc.Layers.Add(rs_joint)

        rs_mem = Rhino.DocObjects.Layer.GetDefaultLayerProperties()
        rs_mem.Name = "Truss_Member"
        rs_mem.Color = System.Drawing.Color.LightSteelBlue
        l_mem = sc.doc.Layers.Add(rs_mem)

        for b in self.final_joints:
            attr = Rhino.DocObjects.ObjectAttributes()
            attr.LayerIndex = l_joint
            sc.doc.Objects.AddBrep(b, attr)
            
        for b in self.final_members:
            attr = Rhino.DocObjects.ObjectAttributes()
            attr.LayerIndex = l_mem
            sc.doc.Objects.AddBrep(b, attr)

        self.Close()

    def OnClosed(self, e):
        self.conduit.Enabled = False
        self.conduit.dispose_meshes()
        sc.doc.Views.Redraw()
        super(TrussModelessDialog, self).OnClosed(e)

# ==============================================================================
# 4. 스크립트 실행 트리거
# ==============================================================================
def main():
    import rhinoscriptsyntax as rs
    curves = rs.GetObjects("트러스의 기준이 될 커브 2개를 선택하세요.", rs.filter.curve, preselect=True)
    if not curves or len(curves) != 2:
        rs.MessageBox("반드시 2개의 커브를 선택해야 합니다.")
        return
        
    crv0 = rs.coercecurve(curves[0])
    crv1 = rs.coercecurve(curves[1])
    
    dlg = TrussModelessDialog()
    dlg.set_curves(crv0, crv1)
    dlg.Show()

if __name__ == "__main__":
    main()