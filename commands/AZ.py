# -*- coding: utf-8 -*-
import Rhino
import scriptcontext as sc
import rhinoscriptsyntax as rs
import System

# 1. 고속 프리뷰 렌더링 (그대로 유지)
def draw_preview(display, info_list, target_H, target_Z, material, edge_color, line_weight):
    for info in info_list:
        base_pt = info['base_pt']
        current_H = info['current_H']
        geom = info['geom']
        
        if target_H is not None:
            final_H = target_H
        elif target_Z is not None:
            final_H = target_Z - base_pt.Z
        else:
            continue
            
        if abs(final_H) < 1e-6: continue
            
        scale_factor = final_H / current_H
        plane = Rhino.Geometry.Plane(base_pt, Rhino.Geometry.Vector3d.ZAxis)
        xform = Rhino.Geometry.Transform.Scale(plane, 1.0, 1.0, scale_factor)
        
        display.PushModelTransform(xform)
        if isinstance(geom, Rhino.Geometry.Brep):
            if material: display.DrawBrepShaded(geom, material)
            display.DrawBrepWires(geom, edge_color, line_weight)
        elif isinstance(geom, Rhino.Geometry.Mesh):
            if material: display.DrawMeshShaded(geom, material)
            display.DrawMeshWires(geom, edge_color, line_weight)
        elif isinstance(geom, Rhino.Geometry.Curve):
            display.DrawCurve(geom, edge_color, line_weight)
        display.PopModelTransform()

class ZScaleConduit(Rhino.Display.DisplayConduit):
    def __init__(self, objs_info):
        super(ZScaleConduit, self).__init__()
        self.objs_info = objs_info
        self.target_H = None
        self.target_Z = None
        self.material = Rhino.Display.DisplayMaterial()
        self.material.Diffuse = System.Drawing.Color.FromArgb(150, 255, 150, 0)
        self.material.Emission = System.Drawing.Color.FromArgb(50, 255, 150, 0)
        self.edge_color = System.Drawing.Color.Orange
        
    def DrawForeground(self, e):
        if self.target_H is None and self.target_Z is None: return
        draw_preview(e.Display, self.objs_info, self.target_H, self.target_Z, self.material, self.edge_color, 2)

def AutoZScaleInteractive():
    obj_ids = rs.GetObjects(u"Z축 높이를 조절할 객체들을 선택하세요", preselect=True)
    if not obj_ids: return
    
    objs_info = []
    # [수정] 원본 객체 속성 저장 (상태 복구용)
    original_attrs = {} 
    
    for obj_id in obj_ids:
        rh_obj = sc.doc.Objects.FindId(obj_id)
        if not rh_obj: continue
        
        bbox = rh_obj.Geometry.GetBoundingBox(True)
        if not bbox.IsValid: continue
        
        current_H = bbox.Max.Z - bbox.Min.Z
        if current_H < 1e-6: continue
        
        base_pt = Rhino.Geometry.Point3d((bbox.Min.X + bbox.Max.X)/2.0, (bbox.Min.Y + bbox.Max.Y)/2.0, bbox.Min.Z)
        
        geom = rh_obj.Geometry.Duplicate()
        geom_preview = geom.ToBrep(False) if isinstance(geom, Rhino.Geometry.Extrusion) else geom
            
        objs_info.append({'id': obj_id, 'geom': geom_preview, 'original_geom': geom, 'base_pt': base_pt, 'current_H': current_H})
        
    conduit = ZScaleConduit(objs_info)
    target_H = None
    target_Z = None
    
    try:
        conduit.Enabled = True
        sc.doc.Views.Redraw()
        
        while True:
            gp = Rhino.Input.Custom.GetPoint()
            prompt = u"윗면을 맞출 [참조점] 클릭 또는 [절대 높이] 입력 (취소: Esc, 적용: Enter)"
            gp.SetCommandPrompt(prompt)
            gp.AcceptNumber(True, False)
            gp.AcceptNothing(True) 
            
            def OnDynamicDraw(sender, e):
                draw_preview(e.Display, objs_info, None, e.CurrentPoint.Z, None, System.Drawing.Color.Red, 1)
            gp.DynamicDraw += OnDynamicDraw
            
            get_rc = gp.Get()
            
            if get_rc == Rhino.Input.GetResult.Cancel: break
            # 확정 (Enter)
            elif get_rc == Rhino.Input.GetResult.Nothing:
                if target_H is not None or target_Z is not None:
                    rs.EnableRedraw(False)
                    for info in objs_info:
                        final_H = target_H if target_H is not None else target_Z - info['base_pt'].Z
                        if abs(final_H) < 1e-6: continue
                        
                        scale_factor = final_H / info['current_H']
                        plane = Rhino.Geometry.Plane(info['base_pt'], Rhino.Geometry.Vector3d.ZAxis)
                        xform = Rhino.Geometry.Transform.Scale(plane, 1.0, 1.0, scale_factor)
                        
                        # 1. 원본 지오메트리 복사
                        new_geom = info['original_geom'].Duplicate()
                        
                        # 2. Extrusion일 경우 Brep으로 변환 (필수)
                        if isinstance(new_geom, Rhino.Geometry.Extrusion):
                            new_geom = new_geom.ToBrep(False)
                            
                        # 3. 변환 적용
                        new_geom.Transform(xform)
                        
                        # 4. 뒤집힘 보정
                        if scale_factor < 0:
                            if isinstance(new_geom, Rhino.Geometry.Brep): new_geom.Flip()
                            elif isinstance(new_geom, Rhino.Geometry.Mesh): new_geom.FlipNormals()
                        
                        # [핵심 수정] Replace 대신, 기존 객체의 Attributes를 가져와서 교체
                        old_rh_obj = sc.doc.Objects.FindId(info['id'])
                        if old_rh_obj:
                            attrs = old_rh_obj.Attributes # 기존 객체의 레이어, 재질 등 속성 복사
                            # 라이노 문서에서 객체 교체
                            sc.doc.Objects.Replace(info['id'], new_geom, attrs)
                        
                    rs.EnableRedraw(True)
                    print(u"Auto Z Scale 적용 완료!")
                break
            elif get_rc == Rhino.Input.GetResult.Number:
                target_H = gp.Number(); target_Z = None
                conduit.target_H = target_H; conduit.target_Z = None
                sc.doc.Views.Redraw()
            elif get_rc == Rhino.Input.GetResult.Point:
                target_Z = gp.Point().Z; target_H = None
                conduit.target_H = None; conduit.target_Z = target_Z
                sc.doc.Views.Redraw()
    finally:
        conduit.Enabled = False
        sc.doc.Views.Redraw()

if __name__ == "__main__":
    AutoZScaleInteractive()