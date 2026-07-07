# -*- coding: utf-8 -*-
import os
import sys
import rhinoscriptsyntax as rs
import Rhino
import Rhino.Geometry as rg
import scriptcontext as sc
import System
import random

# Eto UI 모듈
import Eto.Forms as forms
import Eto.Drawing as drawing

ELEPHANT_DIR = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
if ELEPHANT_DIR not in sys.path:
    sys.path.insert(0, ELEPHANT_DIR)

try:
    import shapefile
except ImportError:
    rs.MessageBox(u"shapefile.py 모듈을 찾을 수 없습니다.\nshapefile.py가 Elephant 폴더 바로 아래에 있는지 확인해주세요.")
    shapefile = None

# -------------------------------------------------------------------------
# 1. 프리뷰 렌더링 엔진 (Display Conduit)
# -------------------------------------------------------------------------
class MassPreviewConduit(Rhino.Display.DisplayConduit):
    def __init__(self, all_curves):
        super(MassPreviewConduit, self).__init__()
        self.all_curves = all_curves 
        self.floors_data = []              
        self.floor_height_val = 3.0 
        
        self.material = Rhino.Display.DisplayMaterial(System.Drawing.Color.DarkOrange, 0.6)
        self.meshes = []
        self.bbox = rg.BoundingBox.Empty
        
    def update_preview(self, floors_data, floor_height_val):
        self.floors_data = floors_data
        self.floor_height_val = floor_height_val
        self.meshes = []
        self.bbox = rg.BoundingBox.Empty
        
        for i, crv in enumerate(self.all_curves):
            if not crv: continue
            
            flr = self.floors_data[i]
            height = flr * self.floor_height_val
            
            rc, plane = crv.TryGetPlane()
            if rc and plane.ZAxis.Z < 0:
                crv.Reverse()
            
            ext = rg.Extrusion.Create(crv, height, True)
            if ext:
                brep = ext.ToBrep(False)
                if brep:
                    meshes = rg.Mesh.CreateFromBrep(brep, rg.MeshingParameters.FastRenderMesh)
                    if meshes:
                        for m in meshes:
                            self.meshes.append(m)
                            self.bbox.Union(m.GetBoundingBox(True))
                    
    def CalculateBoundingBox(self, e):
        e.IncludeBoundingBox(self.bbox)

    def DrawForeground(self, e):
        for mesh in self.meshes:
            e.Display.DrawMeshShaded(mesh, self.material)
            e.Display.DrawMeshWires(mesh, System.Drawing.Color.Black)

# -------------------------------------------------------------------------
# 2. 메인 UI 및 데이터 프로세서
# -------------------------------------------------------------------------
class ShpMassDialog(forms.Dialog[bool]):
    def __init__(self, shp_path):
        self.Title = u"SHP 건물 생성기"
        self.Padding = drawing.Padding(20)
        self.Resizable = False
        self.ClientSize = drawing.Size(445, 270) 
        
        self.shp_path = shp_path
        self.sf = None
        self.fields = []
        self.records = []
        self.all_curves = []
        self.all_floors_data = [] 
        
        self.conduit = None
        
        if not self.load_shp_data():
            self.Close(False)
            return
            
        self.setup_ui()
        self.setup_preview()
        
    def load_shp_data(self):
        encodings = ['cp949', 'euc-kr', 'utf-8']
        for enc in encodings:
            try:
                self.sf = shapefile.Reader(self.shp_path, encoding=enc)
                self.records = self.sf.records()
                break
            except:
                pass
                
        if not self.sf:
            rs.MessageBox(u"SHP 파일을 읽거나 한글 인코딩을 해석하는 데 실패했습니다.")
            return False
            
        raw_fields = [f[0] for f in self.sf.fields[1:]]
        self.fields = []
        for f in raw_fields:
            if isinstance(f, str):
                try:
                    self.fields.append(f.decode('cp949', 'ignore'))
                except:
                    self.fields.append(unicode(f))
            else:
                self.fields.append(unicode(f))
        
        rs.Prompt(u"SHP 기하학 데이터 로딩 중...")
        shapes = self.sf.shapes()
        overall_bbox = rg.BoundingBox.Empty
        
        for s in shapes:
            pts = s.points
            if len(pts) < 3:
                self.all_curves.append(None)
                continue
            r_pts = [rg.Point3d(p[0], p[1], 0) for p in pts]
            if r_pts[0].DistanceTo(r_pts[-1]) > 0.001:
                r_pts.append(r_pts[0])
            crv = rg.Polyline(r_pts).ToNurbsCurve()
            self.all_curves.append(crv)
            overall_bbox.Union(crv.GetBoundingBox(True))
            
        if overall_bbox.IsValid:
            overall_bbox.Inflate(overall_bbox.Diagonal.Length * 0.1)
            rs.ZoomBoundingBox(overall_bbox)
            
        return True
        
    def setup_ui(self):
        self.lbl_field = forms.Label(Text=u"📌 1. 층수 레이어 선택:")
        self.cmb_field = forms.DropDown()
        self.cmb_field.DataStore = self.fields
        default_idx = 0
        for i, f in enumerate(self.fields):
            if "FLR" in f.upper() or u"층" in f:
                default_idx = i
                break
        self.cmb_field.SelectedIndex = default_idx
        self.cmb_field.SelectedIndexChanged += self.on_value_changed
        
        self.lbl_height = forms.Label(Text=u"📐 2. 층고 입력 (m 단위):")
        self.nud_height = forms.NumericStepper()
        self.nud_height.DecimalPlaces = 1
        self.nud_height.Increment = 0.5
        self.nud_height.Value = 3.0 
        self.nud_height.ValueChanged += self.on_value_changed
        
        self.lbl_layer_mode = forms.Label(Text=u"📂 3. 레이어 분류 방식:")
        self.cmb_layer_mode = forms.DropDown()
        self.cmb_layer_mode.DataStore = [u"단일 레이어", u"속성 레이어"]
        self.cmb_layer_mode.SelectedIndex = 0
        self.cmb_layer_mode.SelectedIndexChanged += self.toggle_layer_pickers
        
        self.lbl_split_field = forms.Label(Text=u"🏷️ 4. 분류값 선택:")
        self.cmb_split_field = forms.DropDown()
        self.cmb_split_field.DataStore = self.fields
        self.cmb_split_field.SelectedIndex = 0
        
        # [신규 추가] 랜덤 색상 옵션이 포함된 3가지 모드
        self.lbl_grad_type = forms.Label(Text=u"🌈 5. 색상 모드 선택:")
        self.cmb_grad_type = forms.DropDown()
        self.cmb_grad_type.DataStore = [u"2단계 그라데이션", u"3단계 그라데이션", u"랜덤 색상"]
        self.cmb_grad_type.SelectedIndex = 0
        self.cmb_grad_type.SelectedIndexChanged += self.toggle_layer_pickers
        
        # 3개의 컬러 픽커 세팅
        self.lbl_color = forms.Label(Text=u"🎨 6. 색상 설정:")
        self.picker_start = forms.ColorPicker()
        self.picker_start.Value = drawing.Colors.Blue 
        
        self.picker_mid = forms.ColorPicker()
        self.picker_mid.Value = drawing.Colors.Yellow 
        
        self.picker_end = forms.ColorPicker()
        self.picker_end.Value = drawing.Colors.Red    
        
        self.mid_container = forms.StackLayout(Orientation=forms.Orientation.Horizontal, Spacing=5)
        self.mid_container.Items.Add(self.picker_mid)
        self.mid_container.Items.Add(forms.Label(Text=u" ➡️ "))
        
        color_layout = forms.StackLayout(Orientation=forms.Orientation.Horizontal, Spacing=5)
        color_layout.Items.Add(self.picker_start)
        color_layout.Items.Add(forms.Label(Text=u" ➡️ "))
        color_layout.Items.Add(self.mid_container)
        color_layout.Items.Add(self.picker_end)
        
        self.btn_ok = forms.Button(Text=u"Brep(솔리드) 생성하기")
        self.btn_ok.Click += self.on_ok
        self.btn_cancel = forms.Button(Text=u"취소")
        self.btn_cancel.Click += self.on_cancel
        
        layout = forms.DynamicLayout()
        layout.Spacing = drawing.Size(10, 12)
        layout.AddRow(self.lbl_field, self.cmb_field)
        layout.AddRow(self.lbl_height, self.nud_height)
        layout.AddRow(self.lbl_layer_mode, self.cmb_layer_mode)
        layout.AddRow(self.lbl_split_field, self.cmb_split_field)
        layout.AddRow(self.lbl_grad_type, self.cmb_grad_type)
        layout.AddRow(self.lbl_color, color_layout)
        layout.Add(None)
        layout.AddRow(self.btn_ok, self.btn_cancel)
        
        self.Content = layout
        self.refresh_layer_ui_state()

    def toggle_layer_pickers(self, sender, e):
        self.refresh_layer_ui_state()
        
    def refresh_layer_ui_state(self):
        is_split = (self.cmb_layer_mode.SelectedIndex == 1)
        grad_mode = self.cmb_grad_type.SelectedIndex
        is_3step = (grad_mode == 1)
        is_random = (grad_mode == 2) # 랜덤 모드 확인
        
        # 분리 모드일 때만 활성화
        self.lbl_split_field.Enabled = is_split
        self.cmb_split_field.Enabled = is_split
        self.lbl_grad_type.Enabled = is_split
        self.cmb_grad_type.Enabled = is_split
        
        # [신규 추가] 랜덤 색상이 아닐 때만 컬러 픽커 켜기
        use_pickers = is_split and not is_random
        self.lbl_color.Enabled = use_pickers
        self.picker_start.Enabled = use_pickers
        self.picker_end.Enabled = use_pickers
        
        # 3단계 그라데이션일 때만 중간 컬러 픽커 켜기
        self.mid_container.Visible = is_3step
        self.picker_mid.Enabled = is_split and is_3step

    def setup_preview(self):
        self.conduit = MassPreviewConduit(self.all_curves)
        self.conduit.Enabled = True
        self.update_preview_data()

    def update_preview_data(self):
        if not self.conduit: return
        field_idx = self.cmb_field.SelectedIndex
        floor_h_val = self.nud_height.Value
        
        self.all_floors_data = []
        for i in range(len(self.all_curves)):
            if self.all_curves[i] is None:
                self.all_floors_data.append(0.0)
                continue
            rec = self.records[i]
            try:
                floors = float(rec[field_idx])
                if floors <= 0: floors = 1.0
            except:
                floors = 1.0
            self.all_floors_data.append(floors)
            
        self.conduit.update_preview(self.all_floors_data, floor_h_val)
        sc.doc.Views.Redraw()

    def on_value_changed(self, sender, e):
        self.update_preview_data()

    def on_ok(self, sender, e): self.Close(True)
    def on_cancel(self, sender, e): self.Close(False)

    def OnClosed(self, e):
        if self.conduit:
            self.conduit.Enabled = False
            self.conduit = None
        sc.doc.Views.Redraw()
        super(ShpMassDialog, self).OnClosed(e)

# -------------------------------------------------------------------------
# 3. 색상 그라데이션 수학적 보간 함수
# -------------------------------------------------------------------------
def get_gradient_color(c_start, c_mid, c_end, factor, steps):
    if steps == 2:
        r = int(c_start.R + (c_end.R - c_start.R) * factor)
        g = int(c_start.G + (c_end.G - c_start.G) * factor)
        b = int(c_start.B + (c_end.B - c_start.B) * factor)
    else:
        if factor <= 0.5:
            f = factor * 2.0
            r = int(c_start.R + (c_mid.R - c_start.R) * f)
            g = int(c_start.G + (c_mid.G - c_start.G) * f)
            b = int(c_start.B + (c_mid.B - c_start.B) * f)
        else:
            f = (factor - 0.5) * 2.0
            r = int(c_mid.R + (c_end.R - c_mid.R) * f)
            g = int(c_mid.G + (c_end.G - c_mid.G) * f)
            b = int(c_mid.B + (c_end.B - c_mid.B) * f)
            
    r = max(0, min(255, r))
    g = max(0, min(255, g))
    b = max(0, min(255, b))
    
    return System.Drawing.Color.FromArgb(r, g, b)

# -------------------------------------------------------------------------
# 4. 메인 런처 및 렌더 재질(Material) 통합 생성 엔진
# -------------------------------------------------------------------------
def main():
    shp_path = rs.OpenFileName(u"건물 SHP 파일을 선택하세요", "Shapefiles (*.shp)|*.shp||")
    if not shp_path: return
    
    dialog = ShpMassDialog(shp_path)
    result = dialog.ShowModal(Rhino.UI.RhinoEtoApp.MainWindow)
    
    if result:
        calc_field_idx = dialog.cmb_field.SelectedIndex   
        split_field_idx = dialog.cmb_split_field.SelectedIndex 
        floor_height_val = dialog.nud_height.Value 
        layer_mode = dialog.cmb_layer_mode.SelectedIndex 
        
        grad_mode = dialog.cmb_grad_type.SelectedIndex
        grad_steps = 2 if grad_mode == 0 else 3
        
        split_field_name = dialog.fields[split_field_idx]
        
        c1 = dialog.picker_start.Value
        c2 = dialog.picker_mid.Value
        c3 = dialog.picker_end.Value
        
        sys_c_start = System.Drawing.Color.FromArgb(int(c1.R*255), int(c1.G*255), int(c1.B*255))
        sys_c_mid = System.Drawing.Color.FromArgb(int(c2.R*255), int(c2.G*255), int(c2.B*255))
        sys_c_end = System.Drawing.Color.FromArgb(int(c3.R*255), int(c3.G*255), int(c3.B*255))
        
        rs.EnableRedraw(False)
        generated_count = 0
        
        layer_map = {}
        if layer_mode == 1:
            raw_split_values = []
            for i in range(len(dialog.all_curves)):
                if dialog.all_curves[i] is not None:
                    val = dialog.records[i][split_field_idx]
                    if isinstance(val, str):
                        val = val.decode('cp949', 'ignore').strip()
                    else:
                        val = unicode(val).strip()
                    raw_split_values.append(val)
                    
            unique_vals = list(set(raw_split_values))
            
            try:
                unique_vals = sorted(unique_vals, key=lambda x: float(x))
            except:
                unique_vals = sorted(unique_vals)
                
            total_elements = len(unique_vals)
            
            # 레이어 및 재질별 색상 분배 로직
            for idx, val in enumerate(unique_vals):
                
                # [신규 추가] 랜덤 색상 로직
                if grad_mode == 2:
                    # 너무 어둡거나 밝은 색(형광) 방지를 위해 40~220 범위로 제한
                    rand_r = random.randint(40, 220)
                    rand_g = random.randint(40, 220)
                    rand_b = random.randint(40, 220)
                    target_color = System.Drawing.Color.FromArgb(rand_r, rand_g, rand_b)
                else:
                    factor = float(idx) / float(total_elements - 1) if total_elements > 1 else 0.0
                    target_color = get_gradient_color(sys_c_start, sys_c_mid, sys_c_end, factor, grad_steps)
                
                try:
                    if float(val) == int(float(val)):
                        val = unicode(int(float(val)))
                except:
                    pass
                    
                independent_layer_name = u"{}_{}".format(split_field_name, val)
                
                if not rs.IsLayer(independent_layer_name):
                    rs.AddLayer(independent_layer_name, target_color)
                
                layer_idx = sc.doc.Layers.Find(independent_layer_name, True)
                if layer_idx >= 0:
                    layer = sc.doc.Layers[layer_idx]
                    mat_name = independent_layer_name + u"_Material"
                    
                    mat_idx = sc.doc.Materials.Find(mat_name, True)
                    if mat_idx < 0:
                        mat = Rhino.DocObjects.Material()
                        mat.DiffuseColor = target_color
                        mat.Name = mat_name
                        mat_idx = sc.doc.Materials.Add(mat) 
                    
                    layer.RenderMaterialIndex = mat_idx
                    layer.CommitChanges()
                
                layer_map[val] = independent_layer_name
                
        else:
            if not rs.IsLayer(u"건물"):
                rs.AddLayer(u"건물", System.Drawing.Color.Gray)
                
            layer_idx = sc.doc.Layers.Find(u"건물", True)
            if layer_idx >= 0:
                layer = sc.doc.Layers[layer_idx]
                mat_name = u"건물_Material"
                mat_idx = sc.doc.Materials.Find(mat_name, True)
                if mat_idx < 0:
                    mat = Rhino.DocObjects.Material()
                    mat.DiffuseColor = System.Drawing.Color.Gray
                    mat.Name = mat_name
                    mat_idx = sc.doc.Materials.Add(mat)
                layer.RenderMaterialIndex = mat_idx
                layer.CommitChanges()

        for i, crv in enumerate(dialog.all_curves):
            if not crv: continue
            
            floors = dialog.all_floors_data[i]
            total_height = floors * floor_height_val
            
            rc, plane = crv.TryGetPlane()
            if rc and plane.ZAxis.Z < 0:
                crv.Reverse()
                
            extrusion = rg.Extrusion.Create(crv, total_height, True)
            
            if extrusion:
                brep = extrusion.ToBrep(False)
                if brep:
                    attr = Rhino.DocObjects.ObjectAttributes()
                    attr.MaterialSource = Rhino.DocObjects.ObjectMaterialSource.MaterialFromLayer
                    
                    if layer_mode == 0:
                        target_layer = u"건물"
                    else:
                        current_building_val = dialog.records[i][split_field_idx]
                        if isinstance(current_building_val, str):
                            current_building_val = current_building_val.decode('cp949', 'ignore').strip()
                        else:
                            current_building_val = unicode(current_building_val).strip()
                            
                        try:
                            if float(current_building_val) == int(float(current_building_val)):
                                current_building_val = unicode(int(float(current_building_val)))
                        except:
                            pass
                            
                        target_layer = layer_map[current_building_val]
                    
                    layer_idx = sc.doc.Layers.Find(target_layer, True)
                    if layer_idx >= 0:
                        attr.LayerIndex = layer_idx
                    else:
                        attr.LayerIndex = sc.doc.Layers.Add(target_layer, System.Drawing.Color.Gray)
                    
                    sc.doc.Objects.AddBrep(brep, attr)
                    generated_count += 1
                
        rs.EnableRedraw(True)
        rs.MessageBox(u"총 {} 개의 건물이 생성 되었습니다!".format(generated_count))

if __name__ == "__main__":
    layer_map = {} 
    main()
