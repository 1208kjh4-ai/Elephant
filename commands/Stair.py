# -*- coding: utf-8 -*-
import Rhino
import Rhino.Geometry as rg
import Rhino.Display as rd
import Rhino.UI
import Rhino.Input.Custom as ric
import Rhino.DocObjects as rdo
import Eto.Forms as forms
import Eto.Drawing as drawing
import rhinoscriptsyntax as rs
import System

# ==============================================================================
# [프리뷰 전용] 3D 솔리드 및 난간 가이드 실시간 표시 Conduit
# ==============================================================================
class StairPreviewConduit(rd.DisplayConduit):
    def __init__(self):
        super(StairPreviewConduit, self).__init__()
        self.breps = []
        self.meshes = []
        self.railing_lines = [] 
        self.material = rd.DisplayMaterial()
        self.material.Diffuse = System.Drawing.Color.LightSkyBlue 
        self.material.Transparency = 0.3

    def DrawShaded(self, e):
        for mesh in self.meshes:
            e.Display.DrawMeshShaded(mesh, self.material)

    def DrawForeground(self, e):
        for brep in self.breps:
            e.Display.DrawBrepWires(brep, System.Drawing.Color.DarkBlue, 2)
        for crv in self.railing_lines:
            if crv: e.Display.DrawCurve(crv, System.Drawing.Color.Gold, 4)

# ==============================================================================
# [UI 다이얼로그] 메인 계단 생성 팝업
# ==============================================================================
class StairGeneratorDialog(forms.Form):
    def __init__(self):
        super(StairGeneratorDialog, self).__init__()
        self.Title = "계단 생성기 옵션"
        self.Padding = drawing.Padding(15)
        self.Resizable = False
        self.Topmost = True 
        self.Owner = Rhino.UI.RhinoEtoApp.MainWindow
        self.ClientSize = drawing.Size(420, 260)

    def SetupData(self, top_crv, bot_crv, default_n):
        self.top_crv = top_crv
        self.bot_crv = bot_crv
        self.p_top_start = top_crv.PointAtStart
        self.p_bot_start = bot_crv.PointAtStart
        self.p_top_end = top_crv.PointAtEnd
        self.p_bot_end = bot_crv.PointAtEnd
        
        self.conduit = StairPreviewConduit()
        self.conduit.Enabled = True
        self.final_breps = []
        self.guide_s = None
        self.guide_e = None

        self.cmb_type = forms.ComboBox()
        self.cmb_type.DataStore = ["솔리드 계단 (Solid)", "지그재그 계단 (ZigZag)", "철골 계단 (Steel)"]
        self.cmb_type.SelectedIndex = 0
        self.cmb_type.SelectedIndexChanged += self.OnTypeChanged

        self.lbl_thick = forms.Label(Text=" 디딤판 두께 (mm):")
        self.lbl_thick.Visible = False
        
        self.num_thick = forms.NumericStepper()
        self.num_thick.Value = 150
        self.num_thick.MinValue = 10
        self.num_thick.MaxValue = 1000
        self.num_thick.Visible = False
        self.num_thick.ValueChanged += self.OnSliderChanged

        self.lbl_info = forms.Label()
        self.lbl_info.Font = drawing.Font("Malgun Gothic", 10, drawing.FontStyle.Bold)
        
        self.chk_landing = forms.CheckBox(Text=" 계단참 생성")
        self.chk_landing.Checked = False
        self.chk_landing.CheckedChanged += self.OnLandingChanged

        self.chk_railing = forms.CheckBox(Text=" 난간 기준선 생성")
        self.chk_railing.Checked = True
        self.chk_railing.CheckedChanged += self.OnSliderChanged

        self.slider = forms.Slider()
        self.slider.MinValue = 1
        self.slider.MaxValue = 100
        self.slider.Value = default_n
        self.slider.Width = 380 
        self.slider.ValueChanged += self.OnSliderChanged
        
        self.btn_ok = forms.Button(Text="생성")
        self.btn_ok.Click += self.OnOk
        
        self.btn_cancel = forms.Button(Text="취소")
        self.btn_cancel.Click += self.OnCancel

        layout = forms.DynamicLayout()
        layout.Spacing = drawing.Size(10, 10)
        layout.AddRow(forms.Label(Text="계단 타입:"), self.cmb_type)
        layout.AddRow(self.lbl_thick, self.num_thick)
        layout.AddRow(self.chk_landing, self.chk_railing)
        layout.AddRow(self.lbl_info)
        layout.AddRow(self.slider)
        layout.AddRow(None) 
        
        btn_layout = forms.DynamicLayout()
        btn_layout.BeginHorizontal()
        btn_layout.Add(None, True) 
        btn_layout.Add(self.btn_ok)
        btn_layout.Add(self.btn_cancel)
        btn_layout.EndHorizontal()
        
        layout.AddRow(btn_layout)
        self.Content = layout

        self.KeyDown += self.OnKeyDown
        self.slider.KeyDown += self.OnKeyDown 

        self.UpdatePreview()

    def OnTypeChanged(self, sender, e):
        idx = self.cmb_type.SelectedIndex
        if idx == 0:
            self.lbl_thick.Visible = False
            self.num_thick.Visible = False
        elif idx == 1:
            self.lbl_thick.Text = " 지그재그 두께 (mm):"
            self.lbl_thick.Visible = True
            self.num_thick.Visible = True
        elif idx == 2:
            self.lbl_thick.Text = " 디딤판 두께 (mm):"
            self.num_thick.Value = 30 
            self.lbl_thick.Visible = True
            self.num_thick.Visible = True
            
        self.UpdatePreview()

    def OnLandingChanged(self, sender, e):
        use_landing = bool(self.chk_landing.Checked)
        self.slider.Enabled = not use_landing 
        self.UpdatePreview()

    def OnKeyDown(self, sender, e):
        if e.Key == forms.Keys.Escape:
            self.OnCancel(sender, e)
            e.Handled = True
        elif e.Key == forms.Keys.Enter or e.Key == forms.Keys.Space:
            self.OnOk(sender, e)
            e.Handled = True

    # ==========================================================================
    # [엔진 1] 계단 기본 뼈대 라인 추출 (공통)
    # ==========================================================================
    def create_profiles(self, p_t, p_b, K, F, N_f, stair_type, thickness):
        v_diag = rg.Vector3d(p_b - p_t)
        u_xy = rg.Vector3d(v_diag.X, v_diag.Y, 0)
        if u_xy.Length < 0.001: u_xy = rg.Vector3d(1, 0, 0)
        else: u_xy.Unitize()
        diff_z = abs(p_t.Z - p_b.Z)
        
        v_down = rg.Vector3d(0, 0, -(diff_z / float(F * N_f)))
        tread_len = ((rg.Vector3d(v_diag.X, v_diag.Y, 0).Length - (K * 1200.0)) / float(F)) / float(N_f)
        v_tread = u_xy * tread_len
        v_land = u_xy * 1200.0

        pts_main = [p_t]
        pts_guide = [p_t] 
        bottom_pts = [p_t + v_down]
        
        temp_curr = p_t
        flight_nosing_pairs = []
        landing_z_levels = []

        for i in range(F):
            f_start = temp_curr + v_tread
            for j in range(N_f):
                p_nose = temp_curr + v_tread
                pts_main.append(p_nose)
                f_end = p_nose 
                temp_curr = p_nose + v_down
                pts_main.append(temp_curr)
            
            flight_nosing_pairs.append((f_start, f_end))
            
            if i < F - 1:
                bottom_pts.append(temp_curr + v_down)
                landing_z_levels.append(temp_curr.Z)
                temp_curr = temp_curr + v_land
                pts_main.append(temp_curr)
                bottom_pts.append(temp_curr + v_down)
            else:
                bottom_pts.append(temp_curr - v_tread)

        pts_guide.append(flight_nosing_pairs[0][0]) 
        for i in range(F):
            p1, p2 = flight_nosing_pairs[i]
            if i < F - 1:
                z_floor = landing_z_levels[i]
                t_down = (z_floor - p1.Z) / (p2.Z - p1.Z)
                pts_guide.append(p1 + (p2 - p1) * t_down)
                p3, p4 = flight_nosing_pairs[i+1]
                t_up = (z_floor - p3.Z) / (p4.Z - p3.Z)
                pts_guide.append(p3 + (p4 - p3) * t_up)
            else:
                pts_guide.append(p2)

        final_guide = rg.Polyline(pts_guide).ToPolylineCurve()
        full_prof = None
        
        if stair_type == 0: # Solid
            full_prof = rg.Polyline(pts_main + list(reversed(bottom_pts)) + [p_t]).ToPolylineCurve()
        elif stair_type == 1: # ZigZag
            shift_vec = -u_xy * thickness + rg.Vector3d(0, 0, -thickness)
            pts_bot_zig = [p + shift_vec for p in pts_main]
            full_prof = rg.Polyline(pts_main + list(reversed(pts_bot_zig)) + [pts_main[0]]).ToPolylineCurve()
            
        return full_prof, final_guide, pts_main

    # ==========================================================================
    # [엔진 2] 철골 계단 부품(디딤판, C형강) 생성
    # ==========================================================================
    def generate_steel_treads(self, pts_start, pts_end, thickness):
        tread_breps = []
        vec_thick = rg.Vector3d(0, 0, -thickness)
        tol = Rhino.RhinoDoc.ActiveDoc.ModelAbsoluteTolerance
        
        for i in range(len(pts_start)-1):
            p1_s, p2_s = pts_start[i], pts_start[i+1]
            p1_e, p2_e = pts_end[i], pts_end[i+1]
            
            if abs(p1_s.Z - p2_s.Z) < 1.0:
                p1sb, p2sb = p1_s + vec_thick, p2_s + vec_thick
                p1eb, p2eb = p1_e + vec_thick, p2_e + vec_thick
                
                faces = [
                    rg.Brep.CreateFromCornerPoints(p1_s, p2_s, p2_e, p1_e, tol),
                    rg.Brep.CreateFromCornerPoints(p1sb, p2sb, p2eb, p1eb, tol),
                    rg.Brep.CreateFromCornerPoints(p1_s, p2_s, p2sb, p1sb, tol),
                    rg.Brep.CreateFromCornerPoints(p2_s, p2_e, p2eb, p2sb, tol),
                    rg.Brep.CreateFromCornerPoints(p2_e, p1_e, p1eb, p2eb, tol),
                    rg.Brep.CreateFromCornerPoints(p1_e, p1_s, p1sb, p1eb, tol)
                ]
                
                valid_faces = [f for f in faces if f is not None]
                if len(valid_faces) == 6:
                    joined = rg.Brep.JoinBreps(valid_faces, tol)
                    if joined and len(joined) > 0:
                        tread_breps.append(joined[0])
                        
        return tread_breps

    def make_stringer(self, path_crv, outward_vec, H, B, t):
        vec_X = rg.Vector3d(outward_vec.X, outward_vec.Y, 0)
        if vec_X.Length < 0.001: return None
        vec_X.Unitize()
        
        vec_Y = rg.Vector3d.ZAxis 
        plane = rg.Plane(path_crv.PointAtStart, vec_X, vec_Y)
        
        pts = [
            rg.Point3d(-B, 0, 0),          
            rg.Point3d(0, 0, 0),           
            rg.Point3d(0, -t, 0),          
            rg.Point3d(-B + t, -t, 0),     
            rg.Point3d(-B + t, -(H-t), 0), 
            rg.Point3d(0, -(H-t), 0),      
            rg.Point3d(0, -H, 0),          
            rg.Point3d(-B, -H, 0),         
            rg.Point3d(-B, 0, 0)           
        ]
        
        pts_3d = [plane.PointAt(p.X, p.Y) for p in pts]
        prof_crv = rg.Polyline(pts_3d).ToPolylineCurve()
        
        path_bot = path_crv.DuplicateCurve()
        path_bot.Translate(rg.Vector3d(0, 0, -H)) 
        
        sweep = rg.SweepTwoRail()
        sweep.SweepTolerance = Rhino.RhinoDoc.ActiveDoc.ModelAbsoluteTolerance
        
        res = sweep.PerformSweep(path_crv, path_bot, [prof_crv])
        
        if not res or len(res) == 0:
            sweep1 = rg.SweepOneRail()
            sweep1.SweepTolerance = Rhino.RhinoDoc.ActiveDoc.ModelAbsoluteTolerance
            res = sweep1.PerformSweep(path_crv, prof_crv)
            
        if res and len(res) > 0:
            joined = rg.Brep.JoinBreps(res, Rhino.RhinoDoc.ActiveDoc.ModelAbsoluteTolerance)
            if joined and len(joined) > 0:
                solid = joined[0].CapPlanarHoles(Rhino.RhinoDoc.ActiveDoc.ModelAbsoluteTolerance)
                return solid if solid else joined[0]
            else:
                solid = res[0].CapPlanarHoles(Rhino.RhinoDoc.ActiveDoc.ModelAbsoluteTolerance)
                return solid if solid else res[0]
                
        return None

    # ==========================================================================
    # [지오메트리 마스터] 선택된 타입에 맞춰 분기 계산
    # ==========================================================================
    def generate_stairs(self):
        doc = Rhino.RhinoDoc.ActiveDoc
        tol = doc.ModelAbsoluteTolerance
        
        use_landing = bool(self.chk_landing.Checked)
        stair_type = self.cmb_type.SelectedIndex
        thickness = self.num_thick.Value
        
        
        diff_z_global = abs(self.p_top_start.Z - self.p_bot_start.Z)
        v_xy_start = rg.Vector3d(self.p_bot_start.X - self.p_top_start.X, self.p_bot_start.Y - self.p_top_start.Y, 0)
        
        K = 0 
        self.warning_msg = ""
        if use_landing:
            K = int(diff_z_global // 3000.0)
            if v_xy_start.Length <= K * 1200.0:
                K = 0
                self.warning_msg = " (수평 길이 부족으로 참 생성 불가)"
                
        F = K + 1 
        if use_landing:
            h_f = diff_z_global / float(F)
            N_f = max(1, int(h_f // 180.0)) 
        else:
            N_f = int(self.slider.Value) 
            
        self.current_total_steps = N_f * F
        self.current_K = K
        self.current_N_f = N_f

        # --- [추가/수정 포인트] 한 단 높이를 구해서 str_H에 적용 ---
        c_rh = diff_z_global / float(self.current_total_steps) # 한 단의 실제 높이 연산
        
        str_H = c_rh*2.0
        str_B = 120.0         
        str_t = 30.0          
        str_Zoffset = c_rh*0.5 # 스트링거를 디딤판 아래로 얼마나 내릴지도 동적으로 연동 가능
        # --------------------------------------------------------

        prof_start, guide_start, pts_s = self.create_profiles(self.p_top_start, self.p_bot_start, K, F, N_f, stair_type, thickness)
        prof_end, guide_end, pts_e = self.create_profiles(self.p_top_end, self.p_bot_end, K, F, N_f, stair_type, thickness)
        
        result_breps = []
        
        if stair_type in [0, 1]: 
            sweep = rg.SweepTwoRail()
            if hasattr(sweep, "MaintainHeight"):
                sweep.MaintainHeight = True 
            sweep.SweepTolerance = tol
            sweep_results = sweep.PerformSweep(self.top_crv, self.bot_crv, [prof_start, prof_end])
            
            if sweep_results:
                joined = rg.Brep.JoinBreps(sweep_results, tol)
                if joined and len(joined) > 0:
                    solid = joined[0].CapPlanarHoles(tol)
                    result_brep = solid if solid else joined[0]
                    result_brep.Faces.SplitKinkyFaces(doc.ModelAngleToleranceRadians, True)
                    result_breps.append(result_brep)
                    
        elif stair_type == 2: # Steel
            vec_width = self.p_top_end - self.p_top_start
            vec_width.Z = 0
            vec_width.Unitize()
            
            pts_s_shifted = [p + vec_width * str_B for p in pts_s]
            pts_e_shifted = [p - vec_width * str_B for p in pts_e]
            
            treads = self.generate_steel_treads(pts_s_shifted, pts_e_shifted, thickness)
            result_breps.extend(treads)
            
            path_str_start = guide_start.DuplicateCurve()
            path_str_start.Translate(rg.Vector3d(0, 0, str_Zoffset))
            
            path_str_end = guide_end.DuplicateCurve()
            path_str_end.Translate(rg.Vector3d(0, 0, str_Zoffset))
            
            str_t_brep = self.make_stringer(path_str_start, -vec_width, str_H, str_B, str_t)
            str_b_brep = self.make_stringer(path_str_end, vec_width, str_H, str_B, str_t)
            
            if str_t_brep: result_breps.append(str_t_brep)
            if str_b_brep: result_breps.append(str_b_brep)
                
        return result_breps, guide_start, guide_end

    def UpdatePreview(self):
        if hasattr(self, 'conduit'):
            for m in self.conduit.meshes: 
                if m: m.Dispose()
            for b in self.conduit.breps: 
                if b: b.Dispose()
            for c in self.conduit.railing_lines: 
                if c: c.Dispose()

        self.final_breps, self.guide_s, self.guide_e = self.generate_stairs()
        
        preview_meshes = []
        for b in self.final_breps:
            if b:
                meshes = rg.Mesh.CreateFromBrep(b, rg.MeshingParameters.Default)
                if meshes: preview_meshes.extend(meshes)
                
        self.conduit.breps = self.final_breps
        self.conduit.meshes = preview_meshes
        
        if self.chk_railing.Checked:
            self.conduit.railing_lines = [self.guide_s, self.guide_e]
        else:
            self.conduit.railing_lines = []
        
        h_s = abs(self.p_top_start.Z - self.p_bot_start.Z) / float(self.current_total_steps)
        if bool(self.chk_landing.Checked):
            msg = "총 {}단 (구간당 {}단) | 참: {}개 | 단 높이: {:.1f}".format(self.current_total_steps, self.current_N_f, self.current_K, h_s)
            if self.warning_msg: msg += self.warning_msg
            self.lbl_info.Text = msg
        else:
            self.lbl_info.Text = "계단 개수: {} 개 | 단 높이: {:.1f}".format(self.current_total_steps, h_s)
        
        Rhino.RhinoDoc.ActiveDoc.Views.Redraw()

    def OnSliderChanged(self, sender, e):
        self.UpdatePreview()

    def OnOk(self, sender, e):
        self.conduit.Enabled = False
        doc = Rhino.RhinoDoc.ActiveDoc
        doc.Views.RedrawEnabled = False
        undo_id = doc.BeginUndoRecord("Stair & Railing Bake")
        
        # [핵심 추가] 생성되는 객체들의 ID(Guid)를 수집할 빈 리스트 생성
        added_guids = []
        
        try:
            for brep in self.final_breps:
                if brep:
                    guid = doc.Objects.AddBrep(brep)
                    if guid != System.Guid.Empty:
                        added_guids.append(guid) # 솔리드 객체 ID 추가
                
            if self.chk_railing.Checked and self.guide_s and self.guide_e:
                tol = doc.ModelAbsoluteTolerance
                sw = rg.SweepTwoRail()
                if hasattr(sw, "MaintainHeight"):
                    sw.MaintainHeight = True
                sw.SweepTolerance = tol
                res_r = sw.PerformSweep(self.top_crv, self.bot_crv, [self.guide_s, self.guide_e])
                
                if res_r:
                    for b in res_r:
                        for edge in b.Edges:
                            p_start = edge.EdgeCurve.PointAtStart
                            p_end = edge.EdgeCurve.PointAtEnd
                            
                            is_start_cap = (p_start.DistanceTo(self.top_crv.PointAtStart) < tol and p_end.DistanceTo(self.bot_crv.PointAtStart) < tol) or \
                                           (p_start.DistanceTo(self.bot_crv.PointAtStart) < tol and p_end.DistanceTo(self.top_crv.PointAtStart) < tol)
                                           
                            is_end_cap = (p_start.DistanceTo(self.top_crv.PointAtEnd) < tol and p_end.DistanceTo(self.bot_crv.PointAtEnd) < tol) or \
                                         (p_start.DistanceTo(self.bot_crv.PointAtEnd) < tol and p_end.DistanceTo(self.top_crv.PointAtEnd) < tol)

                            if not is_start_cap and not is_end_cap:
                                guid = doc.Objects.AddCurve(edge.EdgeCurve.DuplicateCurve())
                                if guid != System.Guid.Empty:
                                    added_guids.append(guid) # 선 객체 ID 추가

            # [핵심 추가] 수집된 객체들이 있다면, 새로운 그룹을 하나 파서 모두 편입
            if added_guids:
                group_index = doc.Groups.Add() # 그룹 생성
                for guid in added_guids:
                    doc.Groups.AddToGroup(group_index, guid) # 그룹에 요소 편입
                                    
        finally:
            doc.EndUndoRecord(undo_id)
            doc.Views.RedrawEnabled = True
            doc.Views.Redraw()
            self.Close()

    def OnCancel(self, sender, e):
        self.Close()

    def OnClosed(self, e):
        self.conduit.Enabled = False
        Rhino.RhinoDoc.ActiveDoc.Views.Redraw()
        super(StairGeneratorDialog, self).OnClosed(e)

# ==============================================================================
# [Phase 1] 메인 실행부 및 입력 옵션 제어
# ==============================================================================
def main():
    doc = Rhino.RhinoDoc.ActiveDoc
    
    if not doc.Path:
        res = rs.MessageBox("크래시 등 예기치 못한 종료에 대비하여\n작업 전 파일을 먼저 저장하시겠습니까?", 4 + 32, "안전 장치 (저장 권장)")
        if res == 6:
            rs.Command("_Save", True)
    elif doc.Modified:
        rs.Command("_-Save _Enter", False)
        print("[안전 장치] 작업 보호를 위해 현재 파일이 자동 저장되었습니다.")

    opts = ["SelectCurves", "DrawLine"]
    res = rs.GetString("계단 생성 기준을 선택하세요", "SelectCurves", opts)
    
    if not res: return
    
    c1, c2 = None, None

    if res == "SelectCurves":
        go = ric.GetObject()
        go.SetCommandPrompt("계단의 상부 라인과 하부 라인을 선택하세요 (커브 또는 모서리)")
        go.GeometryFilter = rdo.ObjectType.Curve | rdo.ObjectType.EdgeFilter
        go.SubObjectSelect = True 
        go.GetMultiple(2, 2)
        
        if go.CommandResult() != Rhino.Commands.Result.Success: return
        c1 = go.Object(0).Curve().DuplicateCurve()
        c2 = go.Object(1).Curve().DuplicateCurve()

    elif res == "DrawLine":
        pt1 = rs.GetPoint("첫 번째 선의 시작점을 클릭하세요")
        if not pt1: return
        pt2 = rs.GetPoint("첫 번째 선의 끝점을 클릭하세요", pt1)
        if not pt2: return
        
        pt3 = rs.GetPoint("두 번째 선의 시작점을 클릭하세요")
        if not pt3: return
        pt4 = rs.GetPoint("두 번째 선의 끝점을 클릭하세요", pt3)
        if not pt4: return
        
        c1 = rg.LineCurve(pt1, pt2)
        c2 = rg.LineCurve(pt3, pt4)


    if not c1 or not c2: return

    if c1.IsClosed or c2.IsClosed:
        rs.MessageBox("닫힌 커브는 지원하지 않습니다. 열린 커브를 기준으로 해주세요.", 48, "경고")
        return

    if c1.PointAtStart.Z < c1.PointAtEnd.Z: c1.Reverse()
    if c2.PointAtStart.Z < c2.PointAtEnd.Z: c2.Reverse()

    if c1.PointAtStart.Z > c2.PointAtStart.Z:
        top_crv, bot_crv = c1, c2
    else:
        top_crv, bot_crv = c2, c1

    ts = top_crv.PointAtStart
    bs = bot_crv.PointAtStart
    be = bot_crv.PointAtEnd
    if ts.DistanceTo(bs) > ts.DistanceTo(be):
        bot_crv.Reverse()

    diff_z = abs(top_crv.PointAtStart.Z - bot_crv.PointAtStart.Z)
    if diff_z < 0.1:
        rs.MessageBox("높이 차이가 너무 작습니다.", 48, "오류")
        return
        
    default_n = max(1, int(diff_z // 180.0))

    dialog = StairGeneratorDialog()
    dialog.SetupData(top_crv, bot_crv, default_n)
    dialog.Show()

if __name__ == "__main__":
    main()