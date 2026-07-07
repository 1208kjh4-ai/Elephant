# -*- coding: utf-8 -*-
import Rhino
import Rhino.Geometry as rg
import Rhino.Display as rd
import Rhino.UI
import Eto.Forms as forms
import Eto.Drawing as drawing
import rhinoscriptsyntax as rs
import scriptcontext as sc
import System
import math

# ==============================================================================
# [1. 프리뷰 컨딧] - 린터 경고 및 라이노 8 추상 클래스 에러 해결
# ==============================================================================
class ParkingPreviewConduit(rd.DisplayConduit):
    def __init__(self):
        # 명시적 super 호출로 린터 빨간 점과 실행 에러 동시 해결
        super(ParkingPreviewConduit, self).__init__()
        self.stalls = []
        self.paths = []
        self.stall_color = System.Drawing.Color.DodgerBlue
        self.road_color = System.Drawing.Color.FromArgb(150, 255, 255, 255)

    def DrawForeground(self, e):
        # 미리보기 화면 출력
        if self.paths:
            for p in self.paths: e.Display.DrawCurve(p, self.road_color, 1)
        if self.stalls:
            for s in self.stalls: e.Display.DrawCurve(s.ToNurbsCurve(), self.stall_color, 2)

# ==============================================================================
# [2. 통합 UI 및 설계 엔진]
# ==============================================================================
class ArchitectParkingForm(forms.Form):
    def __init__(self):
        super(ArchitectParkingForm, self).__init__()
        self.Title = "건축 그리드 기반 AI 주차 설계 (최종본)"
        self.Padding = drawing.Padding(20)
        self.Resizable = False
        self.Topmost = True
        self.Owner = Rhino.UI.RhinoEtoApp.MainWindow

    def SetupData(self, b_id, o_ids, ent_pt):
        self.b_id = b_id
        self.o_ids = o_ids
        self.ent_pt = ent_pt
        
        # 컨딧 활성화
        self.conduit = ParkingPreviewConduit()
        self.conduit.Enabled = True
        
        # [라이노 8 대응] 속성 분리 생성
        self.lbl_info = forms.Label()
        self.lbl_info.Text = "진입점과 대지 각도를 분석하여 최적의 그리드를 생성합니다."
        self.lbl_info.TextAlignment = forms.TextAlignment.Center

        self.btn_run = forms.Button()
        self.btn_run.Text = "설계 최적화 및 적용"
        self.btn_run.Height = 40
        self.btn_run.Click += self.Run
        
        layout = forms.DynamicLayout()
        layout.Spacing = drawing.Size(10, 10)
        layout.AddRow(self.lbl_info)
        layout.AddRow(self.btn_run)
        self.Content = layout

    def Run(self, s, e):
        boundary = rs.coercecurve(self.b_id)
        obstacles = [rs.coercecurve(oid) for oid in self.o_ids]
        
        # 1. 지향성 분석 (가장 긴 변의 방향 추출)
        max_l = 0
        best_vec = rg.Vector3d.XAxis
        segments = boundary.DuplicateSegments()
        if segments:
            for seg in segments:
                if seg.GetLength() > max_l:
                    max_l = seg.GetLength()
                    best_vec = seg.TangentAtStart
        
        # 2. 메인 도로 및 지선 방향(16m 모듈) 설정
        cross_vec = rg.Vector3d(best_vec)
        cross_vec.Rotate(math.pi/2, rg.Vector3d.ZAxis)
        
        paths = []
        final_stalls = []
        interval = 16000 # 16,000mm 주차 모듈
        
        # 3. 그리드 생성 및 장애물 회피 연산
        for i in range(-25, 26):
            offset_pt = self.ent_pt + cross_vec * (i * interval)
            aisle_line = rg.Line(offset_pt - best_vec*1000000, offset_pt + best_vec*1000000).ToNurbsCurve()
            
            # 대지 경계 내 구간 추출
            evs = rg.Intersect.Intersection.CurveCurve(aisle_line, boundary, 0.1, 0.1)
            if evs.Count >= 2:
                ts_a = sorted([ev.ParameterA for ev in evs])
                trimmed = aisle_line.Trim(ts_a[0], ts_a[-1])
                
                # 건물(장애물) 구간은 도로 끊기
                segs = trimmed.DuplicateSegments() if trimmed.SpanCount > 1 else [trimmed]
                for seg in segs:
                    mid_pt = seg.PointAt(0.5)
                    is_blocked = False
                    for obs in obstacles:
                        if obs.Contains(mid_pt, rg.Plane.WorldXY, 1.0) == rg.PointContainment.Inside:
                            is_blocked = True; break
                    
                    if not is_blocked:
                        paths.append(seg)
                        # 주차 칸(2.5x5.0) 배치
                        t_vals = seg.DivideByLength(2500, True)
                        if t_vals:
                            for t in t_vals:
                                pt, tan = seg.PointAt(t), seg.TangentAt(t)
                                norm = rg.Vector3d(tan); norm.Rotate(math.pi/2, rg.Vector3d.ZAxis)
                                for side in [1, -1]:
                                    rect = rg.Rectangle3d(rg.Plane(pt + norm*side*3000, tan, norm*side), rg.Interval(0,2500), rg.Interval(0,5000))
                                    # 대지 내부 & 건물 외부 조건 필터링
                                    if boundary.Contains(rect.Center, rg.Plane.WorldXY, 1.0) == rg.PointContainment.Inside:
                                        if not any(o.Contains(rect.Center, rg.Plane.WorldXY, 1.0) == rg.PointContainment.Inside for o in obstacles):
                                            final_stalls.append(rect)

        # 4. Bake (레이어 자동 생성 및 객체 저장)
        sc.doc.BeginUndoRecord("AI Grid Parking")
        lp, lr = "Parking_Stalls", "Parking_Roads"
        if not rs.IsLayer(lp): rs.AddLayer(lp, (30, 144, 255))
        if not rs.IsLayer(lr): rs.AddLayer(lr, (200, 200, 200))
        
        for p in paths:
            oid = sc.doc.Objects.AddCurve(p); rs.ObjectLayer(oid, lr)
        for r in final_stalls:
            oid = sc.doc.Objects.AddCurve(r.ToNurbsCurve()); rs.ObjectLayer(oid, lp)
            
        sc.doc.Views.Redraw()
        self.Close()

    def OnClosed(self, e):
        self.conduit.Enabled = False
        sc.doc.Views.Redraw()
        # super 호출로 깔끔한 종료 처리
        super(ArchitectParkingForm, self).OnClosed(e)

# ==============================================================================
# [3. 실행 메인 함수]
# ==============================================================================
def main():
    b_ref = rs.GetCurveObject("1. 대지 경계선을 선택하세요", preselect=False)
    if not b_ref: return
    
    o_refs = rs.GetObjects("2. 장애물(건물)들을 선택하세요 (없으면 엔터)", filter=4)
    if o_refs is None: o_refs = []
    
    p_pt = rs.GetPoint("3. 진출입구 위치를 클릭하세요")
    if not p_pt: return
    
    form = ArchitectParkingForm()
    form.SetupData(b_ref[0], o_refs, p_pt)
    form.Show()

if __name__ == "__main__":
    main()