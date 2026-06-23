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
# [1. 실시간 프리뷰 컨딧 - v7/v8 공용 초기화]
# ==============================================================================
class ParkingMasterConduit(rd.DisplayConduit):
    def __init__(self):
        # super() 대신 명시적으로 부모 클래스 초기화
        rd.DisplayConduit.__init__(self)
        self.stalls = []      
        self.road_lines = []  
        self.stall_color = System.Drawing.Color.DodgerBlue
        self.road_color = System.Drawing.Color.FromArgb(120, 255, 255, 255)

    def DrawForeground(self, e):
        if self.road_lines:
            for line in self.road_lines:
                e.Display.DrawCurve(line, self.road_color, 1)
        if self.stalls:
            for rect in self.stalls:
                e.Display.DrawCurve(rect.ToNurbsCurve(), self.stall_color, 2)
                e.Display.DrawPoint(rect.Center, rd.PointStyle.X, 3, self.stall_color)

# ==============================================================================
# [2. 통합 UI 폼 - v7/v8 공용 초기화]
# ==============================================================================
class ParkingMasterForm(forms.Form):
    def __init__(self):
        # Rhino 8 Python 3 에러 방지를 위한 명시적 호출
        forms.Form.__init__(self)
        
        self.Title = "주차 배치 마스터 (v7 & v8 공용)"
        self.Padding = drawing.Padding(20)
        self.Resizable = False
        self.Topmost = True
        self.Owner = Rhino.UI.RhinoEtoApp.MainWindow

    def SetupData(self, boundary_id, path_ids):
        self.boundary_id = boundary_id
        self.path_ids = path_ids
        self.conduit = ParkingMasterConduit()
        self.conduit.Enabled = True
        
        # 규격 고정 (mm)
        self.stall_w = 2500; self.stall_l = 5000; self.road_offset = 3000 

        # UI 요소 생성
        self.lbl_info = forms.Label()
        self.lbl_info.Text = "총 배치 대수: - 대"
        self.lbl_info.TextAlignment = forms.TextAlignment.Center
        
        self.btn_reselect = forms.Button()
        self.btn_reselect.Text = "📁 차로 커브 다시 선택"
        
        self.btn_refresh = forms.Button()
        self.btn_refresh.Text = "🔄 변경사항 적용 (재생성)"
        
        self.btn_bake = forms.Button()
        self.btn_bake.Text = "주차장 확정 (Bake)"

        # 이벤트 연결
        self.btn_reselect.Click += self.OnReselectPaths
        self.btn_refresh.Click += self.UpdateLayout
        self.btn_bake.Click += self.OnBakeClick

        layout = forms.DynamicLayout()
        layout.Spacing = drawing.Size(10, 10)
        layout.AddRow(self.btn_reselect)
        layout.AddRow(self.btn_refresh)
        layout.AddRow(self.lbl_info)
        layout.AddRow(self.btn_bake)
        self.Content = layout
        
        self.UpdateLayout(None, None)

    def OnReselectPaths(self, s, e):
        new_ids = rs.GetObjects("새로운 차로 [중심선]들을 선택하세요", filter=4, preselect=False)
        if new_ids:
            self.path_ids = new_ids
            self.UpdateLayout(None, None)

    def UpdateLayout(self, s, e):
        boundary = rs.coercecurve(self.boundary_id)
        path_curves = [rs.coercecurve(pid) for pid in self.path_ids if rs.IsObject(pid)]
        if not boundary or not path_curves: return

        self.conduit.road_lines = []
        candidates = [] 
        
        for p_idx, crv in enumerate(path_curves):
            # 도로 경계선 생성
            off_l = crv.Offset(rg.Plane.WorldXY, self.road_offset, 0.1, rg.CurveOffsetCornerStyle.Round)
            off_r = crv.Offset(rg.Plane.WorldXY, -self.road_offset, 0.1, rg.CurveOffsetCornerStyle.Round)
            if off_l: self.conduit.road_lines.extend(off_l)
            if off_r: self.conduit.road_lines.extend(off_r)

            segments = crv.DuplicateSegments()
            if not segments: segments = [crv]

            for seg in segments:
                t_params = seg.DivideByLength(self.stall_w, True)
                if not t_params: continue
                for t in t_params:
                    pt, tangent = seg.PointAt(t), seg.TangentAt(t)
                    normal = rg.Vector3d(tangent); normal.Rotate(math.pi/2, rg.Vector3d.ZAxis)
                    for s_val in [1, -1]:
                        curr_normal = normal * s_val
                        start_pt = pt + (curr_normal * self.road_offset)
                        plane = rg.Plane(start_pt, tangent, curr_normal)
                        rect = rg.Rectangle3d(plane, rg.Interval(0, self.stall_w), rg.Interval(0, self.stall_l))
                        
                        if self.is_basic_legal(rect, boundary, path_curves):
                            candidates.append({'geom': rect, 'parent_id': p_idx})

        # [지능형 간섭 제거 - 완충 영역 적용]
        final_stalls = []
        for i, cand in enumerate(candidates):
            is_valid = True
            for confirmed in final_stalls:
                if cand['parent_id'] == confirmed['parent_id']:
                    continue
                if self.check_smart_collision(cand['geom'], confirmed['geom']):
                    is_valid = False
                    break
            
            if is_valid:
                final_stalls.append(cand)

        self.conduit.stalls = [c['geom'] for c in final_stalls]
        self.lbl_info.Text = "총 배치 대수: {} 대".format(len(self.conduit.stalls))
        sc.doc.Views.Redraw()

    def is_basic_legal(self, rect, boundary, paths):
        # .Corner(i) 메서드 사용으로 RhinoCommon 객체 접근 안정화
        for i in range(4):
            cp = rect.Corner(i)
            if boundary.Contains(cp, rg.Plane.WorldXY, 1.0) == rg.PointContainment.Outside:
                return False
        
        check_pts = [rect.Corner(2), rect.Corner(3), rect.Center]
        for p in check_pts:
            for path in paths:
                res, t_closest = path.ClosestPoint(p)
                if p.DistanceTo(path.PointAt(t_closest)) < (self.road_offset - 10):
                    return False
        return True

    def check_smart_collision(self, rect_a, rect_b):
        offset = 50 
        test_rect_a = rg.Rectangle3d(rect_a.Plane, 
                                     rg.Interval(offset, self.stall_w - offset), 
                                     rg.Interval(offset, self.stall_l - offset))
        test_rect_b = rg.Rectangle3d(rect_b.Plane, 
                                     rg.Interval(offset, self.stall_w - offset), 
                                     rg.Interval(offset, self.stall_l - offset))
        
        crv_a = test_rect_a.ToNurbsCurve()
        crv_b = test_rect_b.ToNurbsCurve()
        
        relation = rg.Curve.PlanarClosedCurveRelationship(crv_a, crv_b, rg.Plane.WorldXY, 1.0)
        if relation != rg.RegionContainment.Disjoint:
            return True
        return False

    def OnBakeClick(self, s, e):
        if not self.conduit.stalls: return
        sc.doc.BeginUndoRecord("Bake Smart Parking")
        layer_p, layer_r = "Parking_Stalls", "Parking_Road"
        if not rs.IsLayer(layer_p): rs.AddLayer(layer_p, System.Drawing.Color.DodgerBlue)
        if not rs.IsLayer(layer_r): rs.AddLayer(layer_r, System.Drawing.Color.Gray)
        rs.EnableRedraw(False)
        for rect in self.conduit.stalls:
            oid = sc.doc.Objects.AddCurve(rect.ToNurbsCurve()); rs.ObjectLayer(oid, layer_p)
        for crv in self.conduit.road_lines:
            oid = sc.doc.Objects.AddCurve(crv); rs.ObjectLayer(oid, layer_r)
        rs.EnableRedraw(True); sc.doc.Views.Redraw(); self.Close()

    def OnClosed(self, e):
        self.conduit.Enabled = False
        sc.doc.Views.Redraw()
        # super() 대신 부모 클래스 명시하여 닫기 처리
        forms.Form.OnClosed(self, e)

def main():
    b_id = rs.GetCurveObject("주차장 [경계선]을 선택하세요", preselect=False)
    if not b_id: return
    p_ids = rs.GetObjects("차로 [중심선]들을 선택하세요", filter=4, preselect=False)
    if not p_ids: return
    form = ParkingMasterForm()
    form.SetupData(b_id[0], p_ids)
    form.Show()

if __name__ == "__main__":
    main()