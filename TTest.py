# -*- coding: utf-8 -*-
import rhinoscriptsyntax as rs
import Rhino
import scriptcontext as sc
import Rhino.Geometry as rg
import System

def create_parapet_geometry(brep, thickness, height):
    """건물 매스에서 윗면을 찾아 파라펫을 생성하는 핵심 로직"""
    tol = sc.doc.ModelAbsoluteTolerance
    top_faces = []
    
    # 1. 윗면(Z축 방향을 보는 면) 자동 찾기 (수정된 안전한 로직)
    for face in brep.Faces:
        if face.IsPlanar():
            res, plane = face.TryGetPlane()
            # 평면이 Z축과 평행한지 확인 (위든 아래든 평평한 면인지 확인)
            if res and plane.ZAxis.IsParallelTo(rg.Vector3d.ZAxis, 0.01) != 0:
                # 면의 실제 법선(Normal) 방향 검사
                u = face.Domain(0).Mid
                v = face.Domain(1).Mid
                normal = face.NormalAt(u, v) # 에러가 났던 Evaluate 대신 안전한 NormalAt 사용!
                
                # 서피스의 방향이 뒤집혀 있다면 법선도 뒤집어줌
                if face.OrientationIsReversed:
                    normal = -normal
                normal.Unitize()
                
                # 최종적으로 법선 벡터가 완벽히 위(+Z)를 향하는 면만 추출
                if normal.Z > 0.9: 
                    top_faces.append(face)
    
    parapets = []
    vec_up = rg.Vector3d(0, 0, height)
    
    # 2. 각 윗면마다 파라펫 솔리드 생성
    for face in top_faces:
        outer_loop = face.OuterLoop
        if not outer_loop: continue
        outer_crv = outer_loop.To3dCurve()
        res, plane = face.TryGetPlane()
        
        # 안쪽으로 오프셋 (양쪽으로 튕겨보고 길이가 짧아진 것을 안쪽으로 판정)
        c1_list = outer_crv.Offset(plane, thickness, tol, rg.CurveOffsetCornerStyle.Sharp)
        c2_list = outer_crv.Offset(plane, -thickness, tol, rg.CurveOffsetCornerStyle.Sharp)
        
        def get_joined(c_list):
            if not c_list: return None
            if len(c_list) == 1: return c_list[0]
            joined = rg.Curve.JoinCurves(c_list)
            return joined[0] if joined else None
            
        c1 = get_joined(c1_list)
        c2 = get_joined(c2_list)
        
        inner_crv = None
        if c1 and c2:
            inner_crv = c1 if c1.GetLength() < c2.GetLength() else c2
        elif c1: inner_crv = c1
        elif c2: inner_crv = c2
        if not inner_crv: continue # 오프셋 실패시 패스
        
        # 바닥면, 윗면, 내/외벽을 직접 만들어 완벽한 솔리드(Solid)로 조립
        crvs_base = [outer_crv, inner_crv]
        base_srf = rg.Brep.CreatePlanarBreps(crvs_base, tol)
        
        outer_crv_top = outer_crv.Duplicate()
        outer_crv_top.Translate(vec_up)
        inner_crv_top = inner_crv.Duplicate()
        inner_crv_top.Translate(vec_up)
        top_srf = rg.Brep.CreatePlanarBreps([outer_crv_top, inner_crv_top], tol)
        
        outer_wall = rg.Surface.CreateExtrusion(outer_crv, vec_up).ToBrep()
        inner_wall = rg.Surface.CreateExtrusion(inner_crv, vec_up).ToBrep()
        
        pieces = [outer_wall, inner_wall]
        if base_srf: pieces.extend(base_srf)
        if top_srf: pieces.extend(top_srf)
        
        joined = rg.Brep.JoinBreps(pieces, tol)
        if joined:
            parapets.append(joined[0])
            
    if not parapets:
        return None
        
    # 3. 원본 매스와 융합 (Boolean Union)
    union_res = rg.Brep.CreateBooleanUnion([brep] + parapets, tol)
    if union_res and len(union_res) > 0:
        return union_res[0] # 융합 성공
    else:
        return parapets # 융합 실패시 개별 파라펫 덩어리들 반환 (안전장치)


class ParapetPreviewConduit(Rhino.Display.DisplayConduit):
    """실시간 프리뷰(가상 렌더링)를 그리는 엔진"""
    def __init__(self, sample_breps):
        self.sample_breps = sample_breps
        self.thickness = 200.0
        self.height = 1200.0
        self.preview_geometries = []
        self.material = Rhino.Display.DisplayMaterial(System.Drawing.Color.Orange)
        self.material.Transparency = 0.3
        self.Update()
        
    def Update(self):
        self.preview_geometries = []
        for b in self.sample_breps:
            res = create_parapet_geometry(b, self.thickness, self.height)
            if res:
                if isinstance(res, rg.Brep):
                    self.preview_geometries.append(res)
                elif isinstance(res, list):
                    self.preview_geometries.extend(res)
                    
    def DrawForeground(self, e):
        # 주황색 반투명 프리뷰 출력
        for geo in self.preview_geometries:
            e.Display.DrawBrepShaded(geo, self.material)
            e.Display.DrawBrepWires(geo, System.Drawing.Color.DarkOrange)


def main():
    # 1. 대상 객체 선택
    go = Rhino.Input.Custom.GetObject()
    go.SetCommandPrompt("파라펫을 생성할 건물 매스(Polysurface)들을 선택하세요")
    go.GeometryFilter = Rhino.DocObjects.ObjectType.Brep | Rhino.DocObjects.ObjectType.Extrusion
    go.GetMultiple(1, 0)
    if go.CommandResult() != Rhino.Commands.Result.Success: return
    
    refs = go.Objects()
    all_breps = [r.Brep() for r in refs]
    all_ids = [r.ObjectId for r in refs]
    
    # 2. 성능을 위한 프리뷰 샘플링 (최대 50개 제한)
    sample_limit = min(50, len(all_breps))
    sample_breps = all_breps[:sample_limit]
    
    thickness = 200.0
    height = 1200.0
    
    # 프리뷰 엔진 가동
    conduit = ParapetPreviewConduit(sample_breps)
    conduit.Enabled = True
    sc.doc.Views.Redraw()
    
    try:
        # 3. 명령어 창 (CLI) 옵션 루프
        while True:
            opt = Rhino.Input.Custom.GetOption()
            opt.SetCommandPrompt("설정을 확인하고 엔터를 누르면 생성됩니다 (미리보기 최대 50개)")
            opt.AcceptNothing(True) # 엔터키 입력 허용
            
            op_thick = Rhino.Input.Custom.OptionDouble(thickness)
            op_height = Rhino.Input.Custom.OptionDouble(height)
            
            opt.AddOptionDouble("Thickness", op_thick)
            opt.AddOptionDouble("Height", op_height)
            
            res = opt.Get()
            
            if res == Rhino.Input.GetResult.Option: # 값을 수정했을 때
                thickness = op_thick.CurrentValue
                height = op_height.CurrentValue
                conduit.thickness = thickness
                conduit.height = height
                conduit.Update() # 프리뷰 갱신
                sc.doc.Views.Redraw()
                continue
            elif res == Rhino.Input.GetResult.Nothing: # 엔터를 쳤을 때
                break 
            else: # ESC 등을 눌러 취소했을 때
                conduit.Enabled = False
                sc.doc.Views.Redraw()
                return
    finally:
        conduit.Enabled = False
        sc.doc.Views.Redraw()
        
    # 4. 전체 일괄 생성 (Batch Processing)
    rs.EnableRedraw(False)
    total = len(all_breps)
    success_count = 0
    
    for i, brep in enumerate(all_breps):
        # 10개마다 진행률 표시
        if i % 10 == 0:
            Rhino.RhinoApp.SetCommandPrompt("생성 중... {}% 완료".format(int((float(i)/total)*100)))
        
        result = create_parapet_geometry(brep, thickness, height)
        if result:
            if isinstance(result, rg.Brep):
                # 융합 성공! Replace를 통해 깔끔하게 덮어쓰기 (Undo 완벽 지원)
                sc.doc.Objects.Replace(all_ids[i], result)
            elif isinstance(result, list):
                # 융합 실패시: 원본을 유지하고 파라펫과 그룹화 시킴
                group_index = sc.doc.Groups.Add()
                sc.doc.Groups.AddToGroup(group_index, all_ids[i])
                for p in result:
                    p_id = sc.doc.Objects.AddBrep(p)
                    sc.doc.Groups.AddToGroup(group_index, p_id)
            success_count += 1
            
    rs.EnableRedraw(True)
    Rhino.RhinoApp.SetCommandPrompt("파라펫 생성 완료: {}/{} 개 성공".format(success_count, total))

if __name__ == "__main__":
    main()