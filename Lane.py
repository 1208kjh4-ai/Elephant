# -*- coding: utf-8 -*-
import Rhino
import Rhino.Geometry as rg
import Rhino.Display as rd
import rhinoscriptsyntax as rs
import System.Drawing

# 에디터 경고 방지용
EMPTY = None

# [1. 실시간 프리뷰 클래스]
class LanePreviewConduit(rd.DisplayConduit):
    def __init__(self):
        rd.DisplayConduit.__init__(self)
        self.preview_curves = []
        self.color = System.Drawing.Color.Red

    def update_curves(self, curves):
        self.preview_curves = curves

    def DrawForeground(self, e):
        if self.preview_curves:
            for crv in self.preview_curves:
                e.Display.DrawCurve(crv, self.color, 2)

# [2. 레이어 생성 함수]
def ensure_layer(layer_name):
    if not rs.IsLayer(layer_name):
        rs.AddLayer(layer_name)
    return layer_name

# [3. 단일 커브 차선 계산]
def calculate_single_lane(curve, lane_type):    
    if curve == EMPTY: return []
    results = []
    dash_len, gap_len, offset_dist, is_solid, is_double = 0, 0, 0, False, False

    if lane_type == "Dashed": dash_len, gap_len, offset_dist = 3000, 3000, 75
    elif lane_type == "Guide": dash_len, gap_len, offset_dist = 1000, 1000, 100
    elif lane_type == "Solid": is_solid, offset_dist = True, 75
    elif lane_type == "Center": is_solid, offset_dist, is_double = True, 75, True
    elif lane_type == "Stop": is_solid, offset_dist = True, 225

    segments = []
    if is_solid:
        segments = [curve]
    else:
        total_dist = dash_len + gap_len
        t_params = curve.DivideByLength(total_dist, True)
        if t_params == EMPTY: return []
        for t_start in list(t_params):
            dist_at_t = curve.GetLength(rg.Interval(curve.Domain.T0, t_start))
            success, t_end = curve.LengthParameter(dist_at_t + dash_len)
            if success:
                sub = curve.Trim(t_start, t_end)
                if sub: segments.append(sub)

    plane = rg.Plane.WorldXY
    
    # [수정 1] 코너 스타일을 Sharp(1)로 변경하여 꺾인 부분의 교차점을 뾰족하고 깔끔하게 연장
    style = rg.CurveOffsetCornerStyle.Sharp 
    
    # [수정 2] 쪼개진 오프셋 커브들을 안전하게 하나로 합쳐주는 헬퍼 함수
    def safe_offset_join(offset_result):
        if not offset_result: return None
        if len(offset_result) == 1: return offset_result[0]
        
        joined = rg.Curve.JoinCurves(offset_result)
        return joined[0] if joined else None

    for seg in segments:
        offset_curves = []
        if is_double:
            for d in [75, 225, -75, -225]:
                raw_offset = seg.Offset(plane, d, 0.1, style)
                joined_curve = safe_offset_join(raw_offset)
                if joined_curve:
                    offset_curves.append(joined_curve)
        else:
            raw_s1 = seg.Offset(plane, offset_dist, 0.1, style)
            raw_s2 = seg.Offset(plane, -offset_dist, 0.1, style)
            
            j1 = safe_offset_join(raw_s1)
            j2 = safe_offset_join(raw_s2)
            
            if j1 and j2: 
                offset_curves.extend([j1, j2])

        # [수정 3] 안전하게 하나로 이어져 형태가 온전한 커브의 양 끝단만 닫아줌
        for i in range(0, len(offset_curves), 2):
            if i + 1 >= len(offset_curves): break # 짝이 안 맞을 경우 대비
            
            c1, c2 = offset_curves[i], offset_curves[i+1]
            l1 = rg.LineCurve(c1.PointAtStart, c2.PointAtStart)
            l2 = rg.LineCurve(c1.PointAtEnd, c2.PointAtEnd)
            joined = rg.Curve.JoinCurves([c1, l2, c2, l1])
            if joined: results.extend(joined)
            
    return results

# [4. 메인 실행 루프]
def run_lane_tool():
    while True:
        # 1단계: 커브 선택
        target_ids = rs.GetObjects("대상 커브들을 선택하세요 (종료하려면 Enter 또는 ESC)", rs.filter.curve)
        if target_ids == EMPTY: 
            print(">> 작업을 종료합니다.")
            break
        
        source_curves = [rs.coercecurve(tid) for tid in target_ids]
        conduit = LanePreviewConduit()
        conduit.Enabled = True
        
        # 시작 시 기본값을 'Dashed'로 설정하고 즉시 프리뷰 계산
        current_type = "Dashed"
        current_all_previews = []
        for sc in source_curves:
            current_all_previews.extend(calculate_single_lane(sc, current_type))
        
        conduit.update_curves(current_all_previews)
        Rhino.RhinoDoc.ActiveDoc.Views.Redraw()

        try:
            while True:
                go = Rhino.Input.Custom.GetOption()
                go.SetCommandPrompt("종류 클릭 후 'Enter'로 확정 (현재 기본값: Dashed)")
                optDashed = go.AddOption("Dashed")
                optGuide = go.AddOption("Guide")
                optSolid = go.AddOption("Solid")
                optCenter = go.AddOption("Center")
                optStop = go.AddOption("Stop")
                
                go.AcceptNothing(True) 
                res = go.Get()

                if res == Rhino.Input.GetResult.Option:
                    idx = go.OptionIndex()
                    if idx == optDashed: current_type = "Dashed"
                    elif idx == optGuide: current_type = "Guide"
                    elif idx == optSolid: current_type = "Solid"
                    elif idx == optCenter: current_type = "Center"
                    elif idx == optStop: current_type = "Stop"
                    
                    # 옵션 변경 시 프리뷰 업데이트
                    current_all_previews = []
                    for sc in source_curves:
                        current_all_previews.extend(calculate_single_lane(sc, current_type))
                    
                    conduit.update_curves(current_all_previews)
                    Rhino.RhinoDoc.ActiveDoc.Views.Redraw()
                    continue

                elif res == Rhino.Input.GetResult.Nothing:
                    # 현재 프리뷰 상태 그대로 생성
                    if current_all_previews:
                        layer_name = "점선_Lane" if current_type in ["Dashed", "Guide"] else "실선_Lane"
                        color = [255, 255, 0] if current_type == "Center" else [255, 255, 255]
                        ensure_layer(layer_name)
                        for c in current_all_previews:
                            obj_id = Rhino.RhinoDoc.ActiveDoc.Objects.AddCurve(c)
                            rs.ObjectLayer(obj_id, layer_name)
                            rs.ObjectColor(obj_id, color)
                        print(">> {0} 생성 완료. 다음 커브를 선택하세요.".format(current_type))
                    break
                else:
                    break
        finally:
            conduit.Enabled = False
            Rhino.RhinoDoc.ActiveDoc.Views.Redraw()

if __name__ == "__main__":
    run_lane_tool()