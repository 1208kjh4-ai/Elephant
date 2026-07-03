# -*- coding: utf-8 -*-
import rhinoscriptsyntax as rs
import Rhino
import Rhino.Geometry as rg
import Rhino.Display as rd
import Eto.Forms as forms
import Eto.Drawing as drawing
import rhinoscriptsyntax as rs
import scriptcontext as sc
import System
import math

STICKY_KEY = "Elephant_Folding_Settings"

# ==============================================================================
# [1] 독립형 미리보기 엔진 (실시간 변화 반영)
# ==============================================================================
class DoorPreviewConduit(rd.DisplayConduit):
    def __init__(self):
        rd.DisplayConduit.__init__(self)
        self.preview_breps = []
        self.frame_mat = rd.DisplayMaterial(System.Drawing.Color.Indigo)
        self.glass_mat = rd.DisplayMaterial(System.Drawing.Color.AliceBlue)
        self.glass_mat.Transparency = 0.5 

    def DrawForeground(self, e):
        for name, brep in self.preview_breps:
            if brep and brep.IsValid:
                mat = self.glass_mat if name == "glass" else self.frame_mat
                e.Display.DrawBrepShaded(brep, mat)
                e.Display.DrawBrepWires(brep, System.Drawing.Color.Black, 1)

# ==============================================================================
# [2] 폴딩도어 전용 다이얼로그 (생성 & 편집 모드 지원)
# ==============================================================================
class FoldingDoorDialog(forms.Dialog[bool]):
    def __init__(self, base_plane, width, height, edit_mode=False, edit_data=None):
        self.Title = "폴딩도어 편집" if edit_mode else "폴딩도어 생성"
        self.ClientSize = drawing.Size(300, 250)
        self.Padding = drawing.Padding(10)
        self.Resizable = False
        
        self.base_plane = base_plane
        self.width = width
        self.height = height
        self.conduit = DoorPreviewConduit()
        self.conduit.Enabled = True
        
        self.edit_mode = edit_mode
        self.edit_data = edit_data
        
        self.setup_ui()
        self.load_settings()
        self.UpdatePreview(None, None)

    def setup_ui(self):
        self.sli_count = forms.Slider(MinValue=2, MaxValue=10, Value=4)
        self.txt_thick = forms.TextBox(Text="40")
        self.txt_depth = forms.TextBox(Text="100")
        self.sli_angle = forms.Slider(MinValue=0, MaxValue=90, Value=0)
        self.chk_flip = forms.CheckBox(Text="열림 방향 뒤집기")
        
        layout = forms.DynamicLayout()
        layout.Spacing = drawing.Size(5, 5)
        layout.AddRow("문짝 개수:", self.sli_count)
        layout.AddRow("프레임 두께:", self.txt_thick)
        layout.AddRow("프레임 깊이:", self.txt_depth)
        layout.AddRow("열림 각도 (0~90):", self.sli_angle)
        layout.AddRow("", self.chk_flip)
        
        self.btn_ok = forms.Button(Text="수정 적용" if self.edit_mode else "생성하기")
        self.btn_cancel = forms.Button(Text="취소")
        
        self.btn_ok.Click += self.OnOKButtonClick
        self.btn_cancel.Click += self.OnCancelButtonClick
        
        self.sli_count.ValueChanged += self.UpdatePreview
        self.txt_thick.TextChanged += self.UpdatePreview
        self.txt_depth.TextChanged += self.UpdatePreview
        self.sli_angle.ValueChanged += self.UpdatePreview
        self.chk_flip.CheckedChanged += self.UpdatePreview
        
        layout.AddRow(self.btn_ok, self.btn_cancel)
        layout.Add(None)
        self.Content = layout

    def load_settings(self):
        # 편집 모드일 경우 객체에 내장된 데이터를, 신규 생성일 경우 Sticky 메모리를 불러옴
        if self.edit_mode and self.edit_data:
            self.sli_count.Value = int(self.edit_data.get("Count", 4))
            self.txt_thick.Text = str(self.edit_data.get("Thick", 40))
            self.txt_depth.Text = str(self.edit_data.get("Depth", 100))
            self.sli_angle.Value = int(self.edit_data.get("Angle", 0))
            self.chk_flip.Checked = (self.edit_data.get("Flip", "False") == "True")
        else:
            if sc.sticky.has_key(STICKY_KEY):
                saved = sc.sticky[STICKY_KEY]
                self.sli_count.Value = saved.get("Count", 4)
                self.txt_thick.Text = str(saved.get("Thick", 40))
                self.txt_depth.Text = str(saved.get("Depth", 100))
                self.sli_angle.Value = saved.get("Angle", 0)
                self.chk_flip.Checked = saved.get("Flip", False)

    def save_settings(self):
        try: t = float(self.txt_thick.Text)
        except: t = 40
        try: d = float(self.txt_depth.Text)
        except: d = 100
        sc.sticky[STICKY_KEY] = {
            "Count": self.sli_count.Value,
            "Thick": t,
            "Depth": d,
            "Angle": self.sli_angle.Value,
            "Flip": self.chk_flip.Checked == True
        }

    def OnOKButtonClick(self, sender, e):
        if not self.edit_mode: self.save_settings()
        self.conduit.Enabled = False
        self.Close(True)

    def OnCancelButtonClick(self, sender, e):
        self.conduit.Enabled = False
        self.Close(False)
        
    def UpdatePreview(self, sender, e):
        self.conduit.preview_breps = self.GenerateGeometry()
        Rhino.RhinoDoc.ActiveDoc.Views.Redraw()
        
    def GenerateGeometry(self):
        try: thick = float(self.txt_thick.Text)
        except: thick = 40
        try: depth = float(self.txt_depth.Text)
        except: depth = 100
        count = self.sli_count.Value
        angle_rad = math.radians(self.sli_angle.Value)
        flip = (self.chk_flip.Checked == True)
        
        panel_width = self.width / count
        breps = []
        
        y_dir = self.base_plane.YAxis
        if flip: y_dir = -y_dir
        current_pt = self.base_plane.Origin
        
        # 지그재그(아코디언) 형태 회전 연산
        for i in range(count):
            sign = 1 if i % 2 == 0 else -1
            current_angle = angle_rad * sign
            
            panel_x = self.base_plane.XAxis
            panel_x.Rotate(current_angle, self.base_plane.ZAxis)
            panel_y = rg.Vector3d.CrossProduct(self.base_plane.ZAxis, panel_x)
            
            panel_plane = rg.Plane(current_pt, panel_x, panel_y)
            
            # Frame
            box_frame = rg.Box(panel_plane, 
                               rg.Interval(0, panel_width), 
                               rg.Interval(-depth/2, depth/2), 
                               rg.Interval(0, self.height))
            
            # Glass Hole
            box_hole = rg.Box(panel_plane, 
                              rg.Interval(thick, panel_width - thick), 
                              rg.Interval(-depth, depth), 
                              rg.Interval(thick, self.height - thick))
            
            frame_brep = rg.Brep.CreateFromBox(box_frame)
            hole_brep = rg.Brep.CreateFromBox(box_hole)
            
            final_frames = rg.Brep.CreateBooleanDifference(frame_brep, hole_brep, 0.01)
            if final_frames and len(final_frames) > 0:
                breps.append(("frame", final_frames[0]))
            else:
                breps.append(("frame", frame_brep))
                
            # Glass
            box_glass = rg.Box(panel_plane, 
                               rg.Interval(thick, panel_width - thick), 
                               rg.Interval(-5, 5), # 10mm glass
                               rg.Interval(thick, self.height - thick))
            glass_brep = rg.Brep.CreateFromBox(box_glass)
            breps.append(("glass", glass_brep))
            
            current_pt = current_pt + (panel_x * panel_width)

        return breps

# ==============================================================================
# [3] 유틸리티 및 메인 실행부 (생성/편집 모드 분기)
# ==============================================================================
def serialize_vector(v): return "{},{},{}".format(v.X, v.Y, v.Z)
def deserialize_vector(s): 
    pts = s.split(",")
    return rg.Vector3d(float(pts[0]), float(pts[1]), float(pts[2]))

def serialize_point(p): return "{},{},{}".format(p.X, p.Y, p.Z)
def deserialize_point(s):
    pts = s.split(",")
    return rg.Point3d(float(pts[0]), float(pts[1]), float(pts[2]))

def ensure_layer(name, color):
    # 💡 버그 픽스 완료: 문자열(GUID)이 아닌 정수형(int) 인덱스를 반환하도록 수정
    if not rs.IsLayer(name): rs.AddLayer(name, color)
    layer = sc.doc.Layers.FindName(name)
    return layer.Index if layer is not None else -1

def main():
    go = Rhino.Input.Custom.GetObject()
    go.SetCommandPrompt("문 모서리(2개) 선택, 또는 [기존 폴딩도어]를 클릭하세요.")
    go.GeometryFilter = Rhino.DocObjects.ObjectType.Curve | Rhino.DocObjects.ObjectType.Brep | Rhino.DocObjects.ObjectType.EdgeFilter
    
    op_rect = Rhino.Input.Custom.OptionToggle(False, "Off", "On")
    go.AddOptionToggle("DrawRectangle3Pt", op_rect)
    go.SubObjectSelect = True

    while True:
        res = go.GetMultiple(1, 2)
        if res == Rhino.Input.GetResult.Cancel: return
            
        # [옵션 1] 3점 직사각형 모드
        if res == Rhino.Input.GetResult.Option:
            if op_rect.CurrentValue:
                pt1 = rs.GetPoint("첫 번째 코너를 선택하세요")
                if not pt1: return
                pt2 = rs.GetPoint("폭(Width)을 지정할 점을 선택하세요", pt1)
                if not pt2: return
                pt3 = rs.GetPoint("높이(Height)를 지정할 점을 선택하세요", pt2)
                if not pt3: return
                
                x_vec = pt2 - pt1; width = x_vec.Length; x_vec.Unitize()
                z_vec = pt3 - pt2; height = z_vec.Length; z_vec.Unitize()
                y_vec = rg.Vector3d.CrossProduct(z_vec, x_vec); y_vec.Unitize()
                base_plane = rg.Plane(pt1, x_vec, y_vec)
                
                run_dialog(base_plane, width, height, False, None, None)
                return
            continue
            
        if res == Rhino.Input.GetResult.Object:
            objs = [go.Object(i) for i in range(go.ObjectCount)]
            
            # [옵션 2] 편집 모드 (기존 객체 선택)
            if len(objs) == 1:
                obj_id = objs[0].ObjectId
                if rs.GetUserText(obj_id, "ObjectType") == "Elephant_FoldingDoor":
                    edit_data = {
                        "Count": rs.GetUserText(obj_id, "DoorCount"),
                        "Thick": rs.GetUserText(obj_id, "FrameThick"),
                        "Depth": rs.GetUserText(obj_id, "FrameDepth"),
                        "Angle": rs.GetUserText(obj_id, "OpenAngle"),
                        "Flip": rs.GetUserText(obj_id, "FlipState")
                    }
                    width = float(rs.GetUserText(obj_id, "BaseWidth"))
                    height = float(rs.GetUserText(obj_id, "BaseHeight"))
                    
                    origin = deserialize_point(rs.GetUserText(obj_id, "Plane_O"))
                    x_axis = deserialize_vector(rs.GetUserText(obj_id, "Plane_X"))
                    y_axis = deserialize_vector(rs.GetUserText(obj_id, "Plane_Y"))
                    base_plane = rg.Plane(origin, x_axis, y_axis)
                    
                    groups = rs.ObjectGroups(obj_id)
                    old_group = groups[0] if groups else None
                    
                    run_dialog(base_plane, width, height, True, edit_data, old_group)
                    return
            
            # [옵션 3] 신규 생성 모드 (수직 커브 2개 선택)
            if len(objs) == 2:
                crv1 = objs[0].Curve(); crv2 = objs[1].Curve()
                if not crv1 or not crv2:
                    rs.MessageBox("수직 커브 2개를 선택해야 합니다.")
                    return
                    
                def get_b(c): return c.PointAtEnd if c.PointAtStart.Z > c.PointAtEnd.Z else c.PointAtStart
                p1_b, p2_b = get_b(crv1), get_b(crv2)
                
                if p1_b.X > p2_b.X: p1_b, p2_b = p2_b, p1_b; crv1, crv2 = crv2, crv1
                
                origin = p1_b
                z_vec = crv1.PointAtEnd - crv1.PointAtStart if crv1.PointAtStart.Z < crv1.PointAtEnd.Z else crv1.PointAtStart - crv1.PointAtEnd
                height = z_vec.Length; z_vec.Unitize()
                
                x_vec = p2_b - p1_b; width = x_vec.Length; x_vec.Unitize()
                y_vec = rg.Vector3d.CrossProduct(z_vec, x_vec); y_vec.Unitize()
                base_plane = rg.Plane(origin, x_vec, y_vec)
                
                run_dialog(base_plane, width, height, False, None, None)
                return
            
            rs.MessageBox("유효한 객체가 아닙니다. [폴딩도어 1개] 또는 [기준 커브 2개]를 선택하세요.")
            go.ClearObjects()

def run_dialog(base_plane, width, height, is_edit, edit_data, old_group):
    dlg = FoldingDoorDialog(base_plane, width, height, is_edit, edit_data)
    rc = Rhino.UI.EtoExtensions.ShowSemiModal(dlg, Rhino.RhinoDoc.ActiveDoc, Rhino.UI.RhinoEtoApp.MainWindow)
    
    if rc:
        rs.EnableRedraw(False)
        
        # 편집 모드: 기존 그룹을 통째로 삭제
        if is_edit and old_group:
            old_objs = rs.ObjectsByGroup(old_group)
            if old_objs: rs.DeleteObjects(old_objs)
                
        # 새 객체 Bake 및 그룹화
        group_name = rs.AddGroup()
        l_frame = ensure_layer("Door_Frame", System.Drawing.Color.Gray)
        l_glass = ensure_layer("Door_Glass", System.Drawing.Color.LightBlue)
        
        for name, brep in dlg.GenerateGeometry():
            attr = Rhino.DocObjects.ObjectAttributes()
            attr.LayerIndex = l_frame if name == "frame" else l_glass
            obj_id = Rhino.RhinoDoc.ActiveDoc.Objects.AddBrep(brep, attr)
            rs.AddObjectsToGroup(obj_id, group_name)
            
            # 파라메트릭 데이터(User String) 심기 🧬
            rs.SetUserText(obj_id, "ObjectType", "Elephant_FoldingDoor")
            rs.SetUserText(obj_id, "DoorCount", str(dlg.sli_count.Value))
            rs.SetUserText(obj_id, "FrameThick", str(dlg.txt_thick.Text))
            rs.SetUserText(obj_id, "FrameDepth", str(dlg.txt_depth.Text))
            rs.SetUserText(obj_id, "OpenAngle", str(dlg.sli_angle.Value))
            rs.SetUserText(obj_id, "FlipState", str(dlg.chk_flip.Checked == True))
            
            rs.SetUserText(obj_id, "BaseWidth", str(width))
            rs.SetUserText(obj_id, "BaseHeight", str(height))
            rs.SetUserText(obj_id, "Plane_O", serialize_point(base_plane.Origin))
            rs.SetUserText(obj_id, "Plane_X", serialize_vector(base_plane.XAxis))
            rs.SetUserText(obj_id, "Plane_Y", serialize_vector(base_plane.YAxis))
            
        rs.EnableRedraw(True)

if __name__ == "__main__":
    main()