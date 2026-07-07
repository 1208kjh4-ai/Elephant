# -*- coding: utf-8 -*-
import rhinoscriptsyntax as rs
import Rhino.Geometry as rg
import scriptcontext as sc

def drop_and_smooth_curve():
    # 1. 대상 커브 선택
    curve_ids = rs.GetObjects("양 끝점을 지형에 꽂고 높이를 정렬할 열린 커브들을 선택하세요", rs.filter.curve)
    if not curve_ids: return

    # 2. 장면 내 모든 장애물 객체(서피스, 메쉬, 커브) 수집
    all_objs = rs.NormalObjects()
    obstacle_ids = [obj for obj in all_objs if obj not in curve_ids]
    breps, meshes, curves = [], [], []
    for obj_id in obstacle_ids:
        if rs.IsPolysurface(obj_id) or rs.IsSurface(obj_id):
            breps.append(rs.coercebrep(obj_id))
        elif rs.IsMesh(obj_id):
            meshes.append(rs.coercemesh(obj_id))
        elif rs.IsCurve(obj_id):
            curves.append(rs.coercecurve(obj_id))

    success_count = 0
    tol = sc.doc.ModelAbsoluteTolerance

    for curve_id in curve_ids:
        if rs.IsCurveClosed(curve_id): continue
        
        nc = rs.coercecurve(curve_id).ToNurbsCurve()
        cv_count = nc.Points.Count
        if cv_count < 2: continue

        # 3. 양 끝점의 충돌 지점 계산 (Z 투사)
        start_pt = nc.Points[0].Location
        end_pt = nc.Points[cv_count - 1].Location
        
        new_start_z = find_hit_z(start_pt, breps, meshes, curves, tol)
        new_end_z = find_hit_z(end_pt, breps, meshes, curves, tol)

        # 4. 양 끝점의 Z값 갱신
        nc.Points.SetPoint(0, start_pt.X, start_pt.Y, new_start_z)
        nc.Points.SetPoint(cv_count - 1, end_pt.X, end_pt.Y, new_end_z)

        # 5. 이제 변경된 양 끝점 Z값을 기준으로 중간 제어점들의 높이 재보간
        # 전체 길이 계산 (가상의 다각형 기준)
        total_len = 0.0
        acc_lens = [0.0]
        for i in range(1, cv_count):
            dist = nc.Points[i].Location.DistanceTo(nc.Points[i-1].Location)
            total_len += dist
            acc_lens.append(total_len)
        
        if total_len > 0:
            for i in range(1, cv_count - 1):
                ratio = acc_lens[i] / total_len
                # 새로 결정된 양 끝점의 Z를 바탕으로 선형 보간
                smooth_z = new_start_z + (new_end_z - new_start_z) * ratio
                nc.Points.SetPoint(i, nc.Points[i].Location.X, nc.Points[i].Location.Y, smooth_z)

        sc.doc.Objects.Replace(curve_id, nc)
        success_count += 1

    sc.doc.Views.Redraw()
    print("성공: {}개의 커브 양 끝점이 지형에 꽂히고 높이가 정렬되었습니다.".format(success_count))

def find_hit_z(pt, breps, meshes, curves, tol):
    # 하향 Ray 생성 (pt에서 아래로 무한히)
    ray = rg.Line(pt, rg.Point3d(pt.X, pt.Y, -100000)) # 충분히 긴 거리
    ray_crv = rg.LineCurve(ray)
    highest_z = 0.0 # XY평면(Z=0)이 최소 높이

    # 서피스/메쉬/커브 충돌 검사
    for b in breps:
        hit = rg.Intersect.Intersection.CurveBrep(ray_crv, b, tol)
        if hit[1]: 
            for p in hit[1]: highest_z = max(highest_z, p.Z)
    for m in meshes:
        hit = rg.Intersect.Intersection.MeshLine(m, ray.Line)
        if hit: 
            for p in hit: highest_z = max(highest_z, p.Z)
    for c in curves:
        events = rg.Intersect.Intersection.CurveCurve(ray_crv, c, tol, 0.0)
        if events:
            for e in events: highest_z = max(highest_z, e.PointA.Z)
            
    return highest_z

if __name__ == "__main__":
    drop_and_smooth_curve()