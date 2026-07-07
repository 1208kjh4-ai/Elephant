# -*- coding: utf-8 -*-
import rhinoscriptsyntax as rs
import Rhino
import scriptcontext as sc
import Rhino.Geometry as rg

def get_bb_bottom_corners(brep):
    """객체의 BoundingBox를 기반으로 하단 4개 꼭짓점을 반환합니다."""
    bbox = brep.GetBoundingBox(True)
    corners = bbox.GetCorners()
    min_z = min([p.Z for p in corners])
    bottom_corners = [p for p in corners if abs(p.Z - min_z) < 0.001]
    return bottom_corners

def drop_objects():
    # 1. 객체 선택 (Brep, Mesh, Extrusion 모두 허용)
    objs = rs.GetObjects("배치할 객체들을 선택하세요", 8+16+32) 
    if not objs: return

    # 2. 기준점 옵션 설정 (CLI 기반)
    get_opt = Rhino.Input.Custom.GetOption()
    get_opt.SetCommandPrompt("배치 옵션을 설정하세요")
    opt_index = get_opt.AddOptionList("AnchorMode", ["Center", "BB_Corners", "Vertices"], 0)
    
    get_opt.Get()
    
    # 선택 결과 가져오기
    chosen_mode_index = get_opt.OptionIndex()
    mode_names = ["Center", "BB_Corners", "Vertices"]
    anchor_mode = mode_names[chosen_mode_index]

    # 3. 타겟 지형 선택 (★ 메쉬(32) 추가 허용!)
    target = rs.GetObject("타겟 지형(서피스 또는 메쉬)을 선택하세요", 8+16+32)
    if not target: return

    rs.EnableRedraw(False)
    
    # 4. Step 1: 벡터 계산 (Batch Processing)
    vectors = []
    total = len(objs)
    geom = rs.coercegeometry(target) # 타겟 지오메트리 추출
    
    for i, obj_id in enumerate(objs):
        # 명령어 창에 진행 상황 표시
        if i % 10 == 0: 
            Rhino.RhinoApp.SetCommandPrompt("계산 중... {}% 완료".format(int((float(i)/total)*100)))
        
        # 낙하할 객체 데이터 추출
        obj_geom = rs.coercegeometry(obj_id)
        
        # 기준점(Anchor) 리스트 추출
        pts = []
        if anchor_mode == "Center":
            bbox = obj_geom.GetBoundingBox(True)
            pts = [bbox.Center]
        elif anchor_mode == "BB_Corners":
            pts = get_bb_bottom_corners(obj_geom)
        else: # Vertices
            # 객체가 메쉬인 경우와 Brep인 경우를 나누어 정점(Vertex) 추출
            if isinstance(obj_geom, rg.Mesh):
                pts = [rg.Point3d(v) for v in obj_geom.Vertices]
            else:
                pts = [v.Location for v in obj_geom.Vertices] 

        # Raycasting 로직 (가장 긴 낙하 거리 찾기)
        max_dist = 0
        try:
            for pt in pts:
                ray = rg.Ray3d(pt, rg.Vector3d(0, 0, -1)) # 아래쪽(-Z) 방향 광선
                
                # ★ 타겟이 메쉬(Mesh)일 경우의 엔진
                if isinstance(geom, rg.Mesh):
                    param = rg.Intersect.Intersection.MeshRay(geom, ray)
                    if param >= 0.0: # 교차했을 경우 (param 값이 곧 거리입니다)
                        if param > max_dist: max_dist = param
                
                # ★ 타겟이 서피스/폴리서피스(Brep)일 경우의 엔진
                else:
                    inter = rg.Intersect.Intersection.RayShoot(ray, [geom], 1)
                    if inter:
                        dist = pt.Z - inter[0].Z
                        if dist > max_dist: max_dist = dist
            
            vectors.append(rg.Vector3d(0, 0, -max_dist))
        except:
            vectors.append(rg.Vector3d(0, 0, 0)) # 에러 발생 시 제자리 안착

    # 5. Step 2: 한번에 이동
    for i, obj_id in enumerate(objs):
        if vectors[i].Z != 0: # 0벡터(허공에 뜬 객체)는 무시하여 연산력 최적화
            rs.MoveObject(obj_id, vectors[i])

    rs.EnableRedraw(True)
    Rhino.RhinoApp.SetCommandPrompt("배치 완료: {}개의 객체".format(total))

if __name__ == "__main__":
    drop_objects()