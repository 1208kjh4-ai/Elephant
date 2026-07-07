# -*- coding: utf-8 -*-
import Rhino
import Rhino.Geometry as rg
import Rhino.Display as rd
import rhinoscriptsyntax as rs
import System.Drawing
import math

# [1. 통합 미리보기 컨딧]
class MultiCrosswalkPreviewConduit(rd.DisplayConduit):
    def __init__(self, curves):
        rd.DisplayConduit.__init__(self)
        self.preview_curves = curves
        self.color = System.Drawing.Color.Red

    def DrawForeground(self, e):
        if self.preview_curves:
            for crv in self.preview_curves:
                e.Display.DrawCurve(crv, self.color, 2)

# [2. 화살표 커브 생성 함수]
def get_arrow_geometry(base_pt, direction, right_vec):
    plane = rg.Plane(base_pt, right_vec, direction)
    half_bw, half_hw = 80.0, 180.0
    pts = [
        rg.Point3d(-half_bw, -200, 0), rg.Point3d(half_bw, -200, 0),
        rg.Point3d(half_bw, 0, 0), rg.Point3d(half_hw, 0, 0),
        rg.Point3d(0, 250, 0), 
        rg.Point3d(-half_hw, 0, 0), rg.Point3d(-half_bw, 0, 0),
        rg.Point3d(-half_bw, -200, 0)
    ]
    polyline = rg.Polyline(pts).ToPolylineCurve()
    xform = rg.Transform.PlaneToPlane(rg.Plane.WorldXY, plane)
    polyline.Transform(xform)
    return polyline

# [3. 개별 횡단보도 계산 엔진]
def calculate_crosswalk_curves(polyline_id):
    curve = rs.coercecurve(polyline_id)
    if not curve: return []
    amp = rg.AreaMassProperties.Compute(curve)
    center_pt = amp.Centroid
    _, pl = curve.TryGetPolyline()
    pts = list(pl)
    d01, d12 = pts[0].DistanceTo(pts[1]), pts[1].DistanceTo(pts[2])
    if d01 >= d12:
        l_vec, width = (pts[1] - pts[0]), d12
    else:
        l_vec, width = (pts[2] - pts[1]), d01
    l_vec.Unitize()
    right_vec = rg.Vector3d.CrossProduct(l_vec, rg.Vector3d.ZAxis); right_vec.Unitize()
    actual_length = d01 if d01 >= d12 else d12
    stripe_w, gap_w = 450.0, 450.0

    if width < 4000: # 일반형
        simple_curves = []
        start_edge_pt = center_pt - l_vec * (actual_length / 2.0)
        origin_pt = start_edge_pt - right_vec * (width / 2.0)
        current_dist = 0
        while current_dist + stripe_w <= actual_length:
            p1 = origin_pt + l_vec * current_dist
            stripe_rect = rg.Polyline([p1, p1+l_vec*stripe_w, p1+l_vec*stripe_w+right_vec*width, p1+right_vec*width, p1]).ToPolylineCurve()
            simple_curves.append(stripe_rect)
            current_dist += (stripe_w + gap_w)
        return simple_curves
    else: # 지그재그형
        center_gap, half_len = 450.0, actual_length / 2.0
        bar_h = (width - center_gap) / 2.0
        lane_right_center_pt = center_pt + right_vec * (center_gap / 2.0)
        br_origin = lane_right_center_pt - l_vec * half_len
        temp_bars = []
        current_offset = 0
        while current_offset + stripe_w <= half_len:
            p_top_near = lane_right_center_pt - l_vec * current_offset
            p_bot_near = p_top_near - l_vec * stripe_w
            bar_rect = rg.Polyline([p_bot_near, p_top_near, p_top_near+right_vec*bar_h, p_bot_near+right_vec*bar_h, p_bot_near]).ToPolylineCurve()
            temp_bars.append({'curve': bar_rect, 'bottom_near_pt': p_bot_near})
            current_offset += stripe_w
        right_lane_curves = []
        total_count = len(temp_bars)
        is_odd_total = (total_count % 2 != 0)
        mirror_xform = rg.Transform.Mirror(rg.Plane(lane_right_center_pt, l_vec))
        present_in_bottom = []
        for i in range(total_count):
            should_move = (i % 2 == 0) if is_odd_total else (i % 2 != 0)
            bar_crv = temp_bars[i]['curve'].DuplicateCurve()
            if should_move: bar_crv.Transform(mirror_xform)
            else: present_in_bottom.append(i)
            right_lane_curves.append(bar_crv)
        last_idx = present_in_bottom[-1] if present_in_bottom else -1
        zone_top_pt = temp_bars[last_idx]['bottom_near_pt'] if last_idx != -1 else lane_right_center_pt
        mid_l_pos = (zone_top_pt + br_origin) / 2.0
        for ratio in [1/3.0, 2/3.0]:
            right_lane_curves.append(get_arrow_geometry(mid_l_pos + right_vec * (bar_h * ratio), l_vec, right_vec))
        final_curves = []
        rotate_xform = rg.Transform.Rotation(math.pi, center_pt)
        for crv in right_lane_curves:
            final_curves.append(crv)
            mirrored = crv.DuplicateCurve(); mirrored.Transform(rotate_xform); final_curves.append(mirrored)
        return final_curves

# [4. 메인 실행 루프]
def main():
    while True:
        # 01. 여러 사각형 일괄 선택
        target_ids = rs.GetObjects("횡단보도 직사각형들을 선택하세요 (ESC: 종료)", 4)
        if not target_ids: break

        # 02. 전체 커브 계산
        all_combined_curves = []
        for tid in target_ids:
            curves = calculate_crosswalk_curves(tid)
            if curves:
                all_combined_curves.extend(curves)

        if not all_combined_curves:
            print(">> 계산된 커브가 없습니다.")
            continue

        # 03. 미리보기 컨딧 켜기
        conduit = MultiCrosswalkPreviewConduit(all_combined_curves)
        conduit.Enabled = True
        Rhino.RhinoDoc.ActiveDoc.Views.Redraw()

        # 04. 사용자 확정 입력 (버그 방지를 위해 조건문 수정)
        prompt = "{0}개의 횡단보도 미리보기 중 - [Enter] 확정생성 / [ESC] 취소".format(len(target_ids))
        res = rs.GetString(prompt)
        
        # rs.GetString은 Enter 시 빈 문자열("") 혹은 기본값을 반환함
        # ESC를 누르면 None을 반환함
        if res is not None: 
            # ESC가 아닌 모든 입력(Enter 포함)에 대해 생성 진행
            rs.EnableRedraw(False)
            layer_name = "Crosswalk_Crv"
            if not rs.IsLayer(layer_name):
                rs.AddLayer(layer_name, System.Drawing.Color.White)
            
            baked_count = 0
            for c in all_combined_curves:
                obj_id = Rhino.RhinoDoc.ActiveDoc.Objects.AddCurve(c)
                if obj_id:
                    rs.ObjectLayer(obj_id, layer_name)
                    rs.ObjectColor(obj_id, [255, 255, 255])
                    baked_count += 1
            
            rs.EnableRedraw(True)
            Rhino.RhinoDoc.ActiveDoc.Views.Redraw()
            print(">> {0}개의 객체가 '{1}' 레이어에 생성되었습니다.".format(baked_count, layer_name))
        else:
            print(">> 생성이 취소되었습니다.")

        # 05. 미리보기 컨딧 끄고 루프 재시작
        conduit.Enabled = False
        Rhino.RhinoDoc.ActiveDoc.Views.Redraw()

if __name__ == "__main__":
    main()