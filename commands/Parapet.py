# -*- coding: utf-8 -*-
import rhinoscriptsyntax as rs
import scriptcontext as sc
import Rhino
import System

# [1] 전체 객체의 프리뷰를 띄워주는 Conduit 클래스
class AllParapetConduit(Rhino.Display.DisplayConduit):
    def __init__(self):
        self.preview_breps = []
        self.color = System.Drawing.Color.FromArgb(150, 255, 100, 0)
        self.material = Rhino.Display.DisplayMaterial(self.color)

    def DrawForeground(self, e):
        if self.preview_breps:
            for brep in self.preview_breps:
                if brep:
                    e.Display.DrawBrepShaded(brep, self.material)
                    e.Display.DrawBrepWires(brep, System.Drawing.Color.DarkOrange)

# [2] 파라펫 형태를 기하학적으로 연산하는 핵심 함수
def generate_parapet_geometry(obj_id, thickness, height):
    brep = rs.coercebrep(obj_id)
    if not brep: return None
    
    top_face = None
    
    # 1. 가장 높은 윗면 찾기
    for face in brep.Faces:
        u_mid = face.Domain(0).Mid
        v_mid = face.Domain(1).Mid
        normal = face.NormalAt(u_mid, v_mid)
        
        if normal.Z > 0.95: 
            top_face = face
            break
            
    if not top_face: return None
    
    # 2. 윗면의 테두리 추출 및 오프셋 연산
    outer_crv = top_face.OuterLoop.To3dCurve()
    plane = Rhino.Geometry.Plane(top_face.PointAt(u_mid, v_mid), Rhino.Geometry.Vector3d.ZAxis)
    
    offset_crvs = outer_crv.Offset(plane, -thickness, sc.doc.ModelAbsoluteTolerance, Rhino.Geometry.CurveOffsetCornerStyle.Sharp)
    
    if not offset_crvs:
        offset_crvs = outer_crv.Offset(plane, thickness, sc.doc.ModelAbsoluteTolerance, Rhino.Geometry.CurveOffsetCornerStyle.Sharp)
        
    if not offset_crvs: return None
    inner_crv = offset_crvs[0]
    
    # 3. 돌출을 위한 밑면 생성
    base_srf = Rhino.Geometry.Brep.CreatePlanarBreps([outer_crv, inner_crv], sc.doc.ModelAbsoluteTolerance)
    if not base_srf: return None
    
    # 파라펫의 높이(height)값 만큼 밑면을 강제로 뚫고 내려가게 만듦
    translation = Rhino.Geometry.Transform.Translation(0, 0, -height)
    base_srf[0].Transform(translation)
    
    # 밑으로 height 만큼 내려갔으므로, 돌출 길이는 height * 2
    path_crv = Rhino.Geometry.LineCurve(Rhino.Geometry.Point3d(0,0,0), Rhino.Geometry.Point3d(0,0, height * 2))
    
    # 4. 솔리드 돌출 (Extrusion)
    parapet_solid = base_srf[0].Faces[0].CreateExtrusion(path_crv, True)
    
    if parapet_solid:
        # (안전장치 1) 돌출 결과물이 만약 뚜껑이 열린 상태라면 강제로 닫아줌
        if parapet_solid.SolidOrientation == Rhino.Geometry.BrepSolidOrientation.None:
            parapet_solid = parapet_solid.CapPlanarHoles(sc.doc.ModelAbsoluteTolerance)
            
        # 🔥 (안전장치 2) 빼기로 작동하는 원인 해결!
        # 솔리드 방향이 안팎이 뒤집힌 Negative(Inward) 상태인지 검사하고 교정함
        if parapet_solid.SolidOrientation == Rhino.Geometry.BrepSolidOrientation.Inward:
            parapet_solid.Flip() # 뒤집힌 솔리드를 정상(Outward) 방향으로 뒤집어줌
        
    return parapet_solid

# [3] 메인 실행 함수
def RunParapetGenerator():
    obj_ids = rs.GetObjects("파라펫을 생성할 매스들을 선택하세요", rs.filter.polysurface)
    if not obj_ids: return

    thickness = 0.5
    height = 1.2

    conduit = AllParapetConduit()
    conduit.Enabled = True
    sc.doc.Views.Redraw()

    try:
        while True:
            conduit.preview_breps = []
            for obj_id in obj_ids:
                p_brep = generate_parapet_geometry(obj_id, thickness, height)
                if p_brep:
                    conduit.preview_breps.append(p_brep)
            
            sc.doc.Views.Redraw()

            go = Rhino.Input.Custom.GetOption()
            go.SetCommandPrompt("파라펫 치수를 설정하세요 (엔터키를 누르면 적용됩니다)")
            go.AcceptNothing(True) 
            
            opt_T = Rhino.Input.Custom.OptionDouble(thickness)
            opt_H = Rhino.Input.Custom.OptionDouble(height)
            
            go.AddOptionDouble("Thickness", opt_T)
            go.AddOptionDouble("Height", opt_H)
            
            res = go.Get()
            
            if res == Rhino.Input.GetResult.Option:
                thickness = opt_T.CurrentValue
                height = opt_H.CurrentValue
                continue
            elif res == Rhino.Input.GetResult.Nothing:
                break
            else:
                return

    finally:
        conduit.Enabled = False
        sc.doc.Views.Redraw()

    # 4. 실제 생성 및 모델링 교체
    rs.EnableRedraw(False)
    success_count = 0
    
    for obj_id in obj_ids:
        base_brep = rs.coercebrep(obj_id)
        parapet_brep = generate_parapet_geometry(obj_id, thickness, height)
        
        if base_brep and parapet_brep:
            # 방향이 교정되었으므로 완벽하게 '더하기(Union)'로 작동!
            unioned = Rhino.Geometry.Brep.CreateBooleanUnion([base_brep, parapet_brep], sc.doc.ModelAbsoluteTolerance)
            
            if unioned and len(unioned) == 1:
                final_brep = unioned[0]
                
                # 동일 평면 병합(MergeCoplanarFaces)으로 절단선 제거
                final_brep.MergeCoplanarFaces(sc.doc.ModelAbsoluteTolerance, sc.doc.ModelAngleToleranceRadians)
                
                sc.doc.Objects.Replace(obj_id, final_brep)
                success_count += 1
            else:
                # 합치기 실패 시 그룹화 (안전장치)
                p_id = sc.doc.Objects.AddBrep(parapet_brep)
                group_name = rs.AddGroup()
                rs.AddObjectsToGroup([obj_id, p_id], group_name)
                success_count += 1
                
    rs.EnableRedraw(True)
    print("성공적으로 {}개의 객체에 파라펫 생성을 완료했습니다.".format(success_count))

if __name__ == "__main__":
    RunParapetGenerator()