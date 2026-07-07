# -*- coding: utf-8 -*-
import rhinoscriptsyntax as rs
import Rhino.Geometry as rg
import scriptcontext as sc

def smooth_curve_slope_multiple():
    # 1. 다중 커브 선택
    curve_ids = rs.GetObjects("높이를 부드럽게 정렬할 열린 커브(Open Curve)들을 모두 선택하세요", rs.filter.curve)
    if not curve_ids: return

    success_count = 0
    fail_count = 0

    for curve_id in curve_ids:
        if rs.IsCurveClosed(curve_id):
            fail_count += 1
            continue

        curve_geo = rs.coercecurve(curve_id)
        if not curve_geo:
            fail_count += 1
            continue

        nurbs_curve = curve_geo.ToNurbsCurve()
        cv_count = nurbs_curve.Points.Count

        if cv_count <= 1:
            fail_count += 1
            continue

        # 3. 🚨 수정된 부분: XY 평면(Z=0)에 투영된 상태라고 가정하고 2D 누적 거리 계산
        total_length = 0.0
        accumulated_lengths = [0.0]

        for i in range(1, cv_count):
            pt_prev = nurbs_curve.Points[i-1].Location
            pt_curr = nurbs_curve.Points[i].Location
            
            # Z값을 강제로 0으로 만든 가상의 2D 포인트를 생성하여 거리를 잰다
            pt_prev_2d = rg.Point3d(pt_prev.X, pt_prev.Y, 0)
            pt_curr_2d = rg.Point3d(pt_curr.X, pt_curr.Y, 0)
            
            dist = pt_curr_2d.DistanceTo(pt_prev_2d)
            total_length += dist
            accumulated_lengths.append(total_length)

        if total_length == 0:
            fail_count += 1
            continue

        # 4. 시작점과 끝점의 실제 높이값(Z) 추출
        start_z = nurbs_curve.Points[0].Location.Z
        end_z = nurbs_curve.Points[cv_count - 1].Location.Z 
        delta_z = end_z - start_z 

        # 5. 각 제어점들의 Z값을 2D 거리에 비례하여 부드럽게 재설정
        for i in range(cv_count):
            ratio = accumulated_lengths[i] / total_length
            new_z = start_z + (delta_z * ratio)
            
            cv = nurbs_curve.Points[i]
            pt = cv.Location
            nurbs_curve.Points.SetPoint(i, pt.X, pt.Y, new_z)

        # 6. 기존 객체 교체
        sc.doc.Objects.Replace(curve_id, nurbs_curve)
        success_count += 1

    sc.doc.Views.Redraw()
    
    if fail_count > 0:
        print("작업 완료: {}개 성공, {}개 제외 (닫힌 커브 등)".format(success_count, fail_count))
    else:
        print("작업 완료: 총 {}개 커브의 높이가 단 한 번의 계산으로 완벽하게 재조정되었습니다!".format(success_count))

if __name__ == "__main__":
    smooth_curve_slope_multiple()