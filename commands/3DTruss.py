# -*- coding: utf-8 -*-
import System
import Rhino
import Rhino.Geometry as rg
import Rhino.Geometry.Intersect as rgi
import Eto.Forms as forms
import Eto.Drawing as drawing
import rhinoscriptsyntax as rs
import scriptcontext as sc

class TrussPreviewConduit(Rhino.Display.DisplayConduit):
    def __init__(self):
        super(TrussPreviewConduit, self).__init__()
        self.lines = []
        self.breps = []
        self.color_web = System.Drawing.Color.Red
        self.material = Rhino.Display.DisplayMaterial(self.color_web)
        self.material.Transparency = 0.2
        
    def DrawForeground(self, e):
        if self.lines:
            for line in self.lines:
                e.Display.DrawLine(line, self.color_web, 2)
        if self.breps:
            for brep in self.breps:
                e.Display.DrawBrepShaded(brep, self.material)

class TrussGeneratorDialog(forms.Form):
    def __init__(self):
        super(TrussGeneratorDialog, self).__init__()
        
    def SetupUI(self, base_curves):
        self.base_curves = base_curves
        self.conduit = TrussPreviewConduit()
        self.conduit.Enabled = True
        self.preview_lines = []
        
        self.update_timer = forms.UITimer()
        self.update_timer.Interval = 0.15 
        self.update_timer.Elapsed += self.OnTimerElapsed
        
        self.Title = "Elephant Tools: 트러스 생성기"
        self.Padding = drawing.Padding(10)
        self.Resizable = False
        self.Owner = Rhino.UI.RhinoEtoApp.MainWindow
        self.Topmost = True
        
        default_div = sc.sticky.get("TRUSS_div", 10)
        default_tier = sc.sticky.get("TRUSS_tier", 0)
        default_type = sc.sticky.get("TRUSS_type", "01. 프랫 (Pratt)")
        default_out = sc.sticky.get("TRUSS_out", "01. 커브 추출")
        default_rad = sc.sticky.get("TRUSS_rad", 30)
        
        self.lbl_div = forms.Label(Text="분할 개수:")
        self.nud_div = forms.NumericUpDown(Value=default_div, MinValue=2, MaxValue=100, DecimalPlaces=0)
        self.nud_div.Width = 150
        
        self.lbl_tier = forms.Label(Text="수평 단 개수 (1=1/2분할):")
        self.nud_tier = forms.NumericUpDown(Value=default_tier, MinValue=0, MaxValue=20, DecimalPlaces=0)
        self.nud_tier.Width = 150
        
        self.lbl_type = forms.Label(Text="트러스 종류:")
        self.cb_type = forms.DropDown()
        self.cb_type.DataStore = ["01. 프랫 (Pratt)", "02. 하우 (Howe)", "03. 와렌 (Warren)", "04. 더블 와렌 (Double Warren)"]
        self.cb_type.SelectedValue = default_type
        self.cb_type.Width = 150
        
        self.lbl_output = forms.Label(Text="출력 형태:")
        self.cb_output = forms.DropDown()
        self.cb_output.DataStore = ["01. 커브 추출", "02. 일반 파이프", "03. 멀티 파이프 (SubD)"]
        self.cb_output.SelectedValue = default_out
        self.cb_output.Width = 150
        
        self.lbl_rad = forms.Label(Text="파이프 두께 (반지름):")
        self.nud_rad = forms.NumericUpDown(Value=default_rad, MinValue=1, MaxValue=1000, DecimalPlaces=0)
        self.nud_rad.Width = 150
        self.nud_rad.Enabled = not ("커브" in default_out)
        
        self.cb_output.SelectedIndexChanged += self.OnOutputTypeChanged
        self.nud_div.ValueChanged += self.OnUpdatePreview
        self.nud_tier.ValueChanged += self.OnUpdatePreview
        self.cb_type.SelectedIndexChanged += self.OnUpdatePreview
        self.nud_rad.ValueChanged += self.OnUpdatePreview
        self.Closed += self.OnFormClosed 
        
        self.btn_ok = forms.Button(Text="생성하기")
        self.btn_ok.Click += self.OnOKButtonClick
        
        self.btn_cancel = forms.Button(Text="취소")
        self.btn_cancel.Click += self.OnCancelButtonClick
        
        layout = forms.DynamicLayout()
        layout.Spacing = drawing.Size(5, 10)
        
        layout.AddRow(self.lbl_div, self.nud_div)
        layout.AddRow(self.lbl_tier, self.nud_tier)
        layout.AddRow(self.lbl_type, self.cb_type)
        layout.AddRow(None) 
        layout.AddRow(self.lbl_output, self.cb_output)
        layout.AddRow(self.lbl_rad, self.nud_rad)
        layout.AddRow(None) 
        layout.AddRow(self.btn_ok, self.btn_cancel)
        
        self.Content = layout
        self.RunUpdateGeometry() 

    def OnOutputTypeChanged(self, sender, e):
        if "멀티" in self.cb_output.SelectedValue:
            msg = "주의 : 멀티파이프 옵션 사용 시, 선 개수에 따라 연산 부하가 크게 발생할 수 있습니다.\n작업 파일을 먼저 저장하신 후 진행하시길 권장합니다.\n\n해당 옵션을 켜시겠습니까?\n(예(Y): 켜기 / 아니요(N): 취소)"
            res = forms.MessageBox.Show(msg, "Elephant Tools: 경고", forms.MessageBoxButtons.YesNo, forms.MessageBoxType.Warning)
            
            if res == forms.DialogResult.No:
                self.cb_output.SelectedIndex = 0 
                return
                
        self.nud_rad.Enabled = not ("커브" in self.cb_output.SelectedValue)
        self.OnUpdatePreview(None, None)

    def OnUpdatePreview(self, sender, e):
        self.update_timer.Stop()
        self.update_timer.Start()
        
    def OnTimerElapsed(self, sender, e):
        self.update_timer.Stop()
        self.RunUpdateGeometry()
        
    def RunUpdateGeometry(self):
        output_type = self.cb_output.SelectedValue
        radius = float(self.nud_rad.Value)
        
        self.preview_lines = self.GenerateTrussLines()
        self.conduit.lines = []
        self.conduit.breps = []
        
        if "커브" in output_type:
            self.conduit.lines = self.preview_lines
        else:
            tol = Rhino.RhinoDoc.ActiveDoc.ModelAbsoluteTolerance
            ang_tol = Rhino.RhinoDoc.ActiveDoc.ModelAngleToleranceRadians
            preview_breps = []
            for line in self.preview_lines:
                crv = rg.LineCurve(line)
                b_array = rg.Brep.CreatePipe(crv, radius, False, Rhino.Geometry.PipeCapMode.Flat, True, tol, ang_tol)
                if b_array:
                    preview_breps.extend(b_array)
            self.conduit.breps = preview_breps
            
        Rhino.RhinoDoc.ActiveDoc.Views.Redraw()
        
    def ShatterLinesForMultiPipe(self, lines):
        """멀티파이프의 노드 연산을 돕기 위해 교차하는 선들을 정확히 잘라주는 전처리 함수"""
        intersect_tol = 1e-3
        shattered_curves = []
        
        for i in range(len(lines)):
            lineA = lines[i]
            t_vals = []
            for j in range(len(lines)):
                if i == j: continue
                lineB = lines[j]
                # 두 무한 직선 사이의 최단 거리 매개변수 추출
                res, a, b = rgi.Intersection.LineLine(lineA, lineB)
                if res:
                    # 선분 길이 내부에서 교차하는지 검사 (시작과 끝 1e-4 여유 마진)
                    if 1e-4 < a < 1.0 - 1e-4 and -1e-4 <= b <= 1.0 + 1e-4:
                        ptA = lineA.PointAt(a)
                        ptB = lineB.PointAt(b)
                        # 실제로 공간상에서 두 선이 맞닿아 있는지 확인
                        if ptA.DistanceTo(ptB) <= intersect_tol:
                            t_vals.append(a)

            if t_vals:
                # 중복 파라미터 필터링
                clean_t = []
                for t in sorted(t_vals):
                    if not clean_t or abs(t - clean_t[-1]) > 1e-4:
                        clean_t.append(t)

                # 교차점 파라미터대로 점을 찍어서 여러 개의 선분으로 쪼개기
                pts = [lineA.PointAt(0.0)]
                for t in clean_t:
                    pts.append(lineA.PointAt(t))
                pts.append(lineA.PointAt(1.0))

                for k in range(len(pts)-1):
                    # 오차 범위 내의 너무 짧은 찌꺼기 선분 방지
                    if pts[k].DistanceTo(pts[k+1]) > intersect_tol:
                        shattered_curves.append(rg.LineCurve(pts[k], pts[k+1]))
            else:
                # 교차점이 없으면 원본 선 그대로 보존
                shattered_curves.append(rg.LineCurve(lineA))
                
        return shattered_curves

    def OnOKButtonClick(self, sender, e):
        sc.sticky["TRUSS_div"] = self.nud_div.Value
        sc.sticky["TRUSS_tier"] = self.nud_tier.Value
        sc.sticky["TRUSS_type"] = self.cb_type.SelectedValue
        sc.sticky["TRUSS_out"] = self.cb_output.SelectedValue
        sc.sticky["TRUSS_rad"] = self.nud_rad.Value
        
        output_type = self.cb_output.SelectedValue
        radius = float(self.nud_rad.Value)
        baked_ids = []
        
        rs.EnableRedraw(False)
        
        if "커브" in output_type:
            for line in self.preview_lines:
                crv = rg.LineCurve(line)
                guid = Rhino.RhinoDoc.ActiveDoc.Objects.AddCurve(crv)
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
                
                # 🎯 핵심: 프리뷰 선들을 교차점에서 모두 분할(Shatter)하여 노드 최적화
                shattered_curves = self.ShatterLinesForMultiPipe(self.preview_lines)
                
                # 잘라진 선분들로 멀티파이프 연산
                subd_res = ghcomp.MultiPipe(shattered_curves, radius, 0, 1)
                
                if subd_res:
                    if type(subd_res) is list or type(subd_res) is tuple:
                        for sd in subd_res:
                            guid = Rhino.RhinoDoc.ActiveDoc.Objects.AddSubD(sd)
                            if guid: baked_ids.append(guid)
                    else:
                        guid = Rhino.RhinoDoc.ActiveDoc.Objects.AddSubD(subd_res)
                        if guid: baked_ids.append(guid)
            except Exception as ex:
                print("⚠️ 멀티파이프 연산에 실패하여 일반 파이프 모드로 대체 생성합니다. (" + str(ex) + ")")
                tol = Rhino.RhinoDoc.ActiveDoc.ModelAbsoluteTolerance
                ang_tol = Rhino.RhinoDoc.ActiveDoc.ModelAngleToleranceRadians
                # 대체 모드에서는 분할되지 않은 원본 선을 사용하여 매끄러운 파이프를 유지합니다.
                for line in self.preview_lines:
                    crv = rg.LineCurve(line)
                    breps = rg.Brep.CreatePipe(crv, radius, False, Rhino.Geometry.PipeCapMode.Flat, True, tol, ang_tol)
                    if breps:
                        for b in breps:
                            guid = Rhino.RhinoDoc.ActiveDoc.Objects.AddBrep(b)
                            if guid: baked_ids.append(guid)

        if baked_ids:
            group_name = rs.AddGroup() 
            if group_name:
                rs.AddObjectsToGroup(baked_ids, group_name)

        rs.EnableRedraw(True)
        print("성공적으로 트러스가 생성되었습니다! 🐘🛠️")
        self.Close()
        
    def OnCancelButtonClick(self, sender, e):
        self.Close()
        
    def OnFormClosed(self, sender, e):
        self.conduit.Enabled = False
        Rhino.RhinoDoc.ActiveDoc.Views.Redraw()
        if self.update_timer:
            self.update_timer.Stop()
            self.update_timer.Dispose()
        
    def GenerateTrussLines(self):
        div = int(self.nud_div.Value)
        tier = int(self.nud_tier.Value)
        truss_type = self.cb_type.SelectedValue
        lines = []
        
        aligned_curves = [self.base_curves[0]]
        for i in range(1, len(self.base_curves)):
            prev_crv = aligned_curves[-1]
            curr_crv = self.base_curves[i].DuplicateCurve()
            
            p1_s = prev_crv.PointAtStart
            p1_e = prev_crv.PointAtEnd
            p2_s = curr_crv.PointAtStart
            p2_e = curr_crv.PointAtEnd
            
            if p1_s.DistanceTo(p2_e) + p1_e.DistanceTo(p2_s) < p1_s.DistanceTo(p2_s) + p1_e.DistanceTo(p2_e):
                curr_crv.Reverse()
            aligned_curves.append(curr_crv)
            
        for i in range(len(aligned_curves)-1):
            c1 = aligned_curves[i]
            c2 = aligned_curves[i+1]
            is_closed = c1.IsClosed 
            
            pts1, pts2 = [], []
            t_vals1 = list(c1.DivideByCount(div, True))
            t_vals2 = list(c2.DivideByCount(div, True))
            
            for t in t_vals1: pts1.append(c1.PointAt(t))
            if is_closed and len(pts1) == div: pts1.append(pts1[0])
                
            for t in t_vals2: pts2.append(c2.PointAt(t))
            if is_closed and len(pts2) == div: pts2.append(pts2[0])
                
            if truss_type == "03. 와렌 (Warren)" and i % 2 == 1:
                pts1, pts2 = pts2, pts1
                
            for c in range(len(pts1) - 1):
                lines.append(rg.Line(pts1[c], pts1[c+1]))
                lines.append(rg.Line(pts2[c], pts2[c+1]))
                
            web_lines = []
            for c in range(len(pts1) - 1):
                p00 = pts1[c]       
                p10 = pts1[c+1]     
                p01 = pts2[c]       
                p11 = pts2[c+1]     
                
                is_left_half = (c < div / 2.0)
                
                if truss_type == "01. 프랫 (Pratt)":
                    web_lines.append((p00, p01))
                    if c == len(pts1) - 2: web_lines.append((p10, p11))
                    if is_left_half: web_lines.append((p10, p01))
                    else: web_lines.append((p00, p11))            
                        
                elif truss_type == "02. 하우 (Howe)":
                    web_lines.append((p00, p01)) 
                    if c == len(pts1) - 2: web_lines.append((p10, p11))
                    if is_left_half: web_lines.append((p00, p11)) 
                    else: web_lines.append((p10, p01))            
                        
                elif truss_type == "03. 와렌 (Warren)":
                    if c == 0 and not is_closed: web_lines.append((p00, p01))
                    if c == len(pts1) - 2 and not is_closed: web_lines.append((p10, p11))
                    if c % 2 == 0: web_lines.append((p00, p11)) 
                    else: web_lines.append((p10, p01))          
                        
                elif truss_type == "04. 더블 와렌 (Double Warren)":
                    if c == 0 and not is_closed: web_lines.append((p00, p01))
                    if c == len(pts1) - 2 and not is_closed: web_lines.append((p10, p11))
                    web_lines.append((p00, p11))
                    web_lines.append((p10, p01))
            
            for bot, top in web_lines:
                lines.append(rg.Line(bot, top))
                
            for t_idx in range(1, tier + 1):
                ratio = float(t_idx) / float(tier + 1)
                tier_pts = []
                
                if not is_closed:
                    tier_pts.append(pts1[0] + (pts2[0] - pts1[0]) * ratio)
                
                for bot, top in web_lines:
                    pt = bot + (top - bot) * ratio
                    tier_pts.append(pt)
                    
                if not is_closed:
                    tier_pts.append(pts1[-1] + (pts2[-1] - pts1[-1]) * ratio)
                
                clean_pts = []
                for pt in tier_pts:
                    if not clean_pts or pt.DistanceTo(clean_pts[-1]) > Rhino.RhinoMath.ZeroTolerance:
                        clean_pts.append(pt)
                
                for k in range(len(clean_pts) - 1):
                    lines.append(rg.Line(clean_pts[k], clean_pts[k+1]))

        return lines

def main():
    crv_ids = rs.GetObjects("트러스 기준 커브를 순서대로 2개 이상 선택하세요.", rs.filter.curve, preselect=True)
    if not crv_ids or len(crv_ids) < 2:
        print("최소 2개 이상의 커브를 선택해야 합니다.")
        return
        
    base_curves = [rs.coercecurve(id) for id in crv_ids]
    
    dialog = TrussGeneratorDialog()
    dialog.SetupUI(base_curves)
    dialog.Show()

if __name__ == "__main__":
    main()