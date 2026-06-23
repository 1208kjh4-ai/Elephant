# -*- coding: utf-8 -*-
import Rhino
import Rhino.Geometry as rg
import Rhino.Display as rd
import Rhino.UI
import Eto.Forms as forms
import Eto.Drawing as drawing
import rhinoscriptsyntax as rs
import scriptcontext as sc
import System
import os
import random
import math

# ==============================================================================
# [1. 외부 3dm 파일 로더]
# ==============================================================================
def load_tree_library(file_name):
    script_dir = os.path.dirname(os.path.realpath(__file__))
    file_path = os.path.join(script_dir, file_name)
    if not os.path.exists(file_path): return None

    f3dm = Rhino.FileIO.File3dm.Read(file_path)
    library = {"SoftWood": [], "HardWood": []}
    for obj in f3dm.Objects:
        name = obj.Attributes.Name
        if not name: continue
        geom = obj.Geometry.Duplicate()
        if name.startswith("SoftWood"): library["SoftWood"].append(geom)
        elif name.startswith("HardWood"): library["HardWood"].append(geom)
    return library

# ==============================================================================
# [2. 프리뷰 컨딧 - 라이노 7/8 공용 초기화]
# ==============================================================================
class TreePreviewConduit(rd.DisplayConduit):
    def __init__(self):
        # super() 대신 클래스 명시 호출 (Rhino 8 Python 3 에러 방지)
        rd.DisplayConduit.__init__(self)
        self.points = []
        self.geometries = []
        self.pt_color = System.Drawing.Color.OrangeRed
        self.tree_color = System.Drawing.Color.SeaGreen 

    def DrawShaded(self, e):
        material = rd.DisplayMaterial(self.tree_color, 0.4)
        for g in self.geometries:
            if isinstance(g, rg.Mesh): e.Display.DrawMeshShaded(g, material)
            elif isinstance(g, rg.Brep): e.Display.DrawBrepShaded(g, material)

    def DrawForeground(self, e):
        for pt in self.points:
            e.Display.DrawPoint(pt, rd.PointStyle.ControlPoint, 5, self.pt_color)
        for g in self.geometries:
            if isinstance(g, rg.Mesh): e.Display.DrawMeshWires(g, self.tree_color, 1)
            elif isinstance(g, rg.Brep): e.Display.DrawBrepWires(g, self.tree_color, 1)

# ==============================================================================
# [3. 통합 UI 마스터 폼 (경량화 및 호환성 버전)]
# ==============================================================================
class TreeMasterForm(forms.Form):
    def __init__(self):
        # Rhino 8 에러 방지용 명시적 초기화
        forms.Form.__init__(self)
        
        self.Title = "나무 배치 마스터 (v7 & v8 공용)"
        self.Padding = drawing.Padding(20)
        self.Resizable = False
        self.Topmost = True 
        self.Owner = Rhino.UI.RhinoEtoApp.MainWindow

    def SetupData(self, geometry, library):
        self.target_geom = geometry
        self.is_curve = isinstance(geometry, rg.Curve)
        self.library = library
        self.conduit = TreePreviewConduit()
        self.conduit.Enabled = True
        
        # UI 레이블 및 슬라이더 생성
        self.lbl_main = forms.Label()
        self.slider_main = forms.Slider()
        
        if self.is_curve:
            self.lbl_main.Text = "배치 간격 (mm):"
            self.slider_main.MinValue = 500; self.slider_main.MaxValue = 30000; self.slider_main.Value = 5000
        else:
            self.lbl_main.Text = "시도 개수 (개):"
            self.slider_main.MinValue = 1; self.slider_main.MaxValue = 1000; self.slider_main.Value = 100

        self.lbl_seed = forms.Label(); self.lbl_seed.Text = "배치 시드 (Seed):"
        self.slider_seed = forms.Slider(); self.slider_seed.MinValue = 0; self.slider_seed.MaxValue = 100; self.slider_seed.Value = 1

        self.lbl_scale_title = forms.Label(); self.lbl_scale_title.Text = "--- 스케일 범위 조절 ---"
        self.lbl_scale_min = forms.Label(); self.lbl_scale_min.Text = "최소 스케일: 0.7x"
        self.slider_min_scale = forms.Slider(); self.slider_min_scale.MinValue = 1; self.slider_min_scale.MaxValue = 200; self.slider_min_scale.Value = 70
        self.lbl_scale_max = forms.Label(); self.lbl_scale_max.Text = "최대 스케일: 1.3x"
        self.slider_max_scale = forms.Slider(); self.slider_max_scale.MinValue = 1; self.slider_max_scale.MaxValue = 200; self.slider_max_scale.Value = 130

        self.cb_soft = forms.CheckBox(); self.cb_soft.Text = "SoftWood (3종)"; self.cb_soft.Checked = True
        self.cb_hard = forms.CheckBox(); self.cb_hard.Text = "HardWood (6종)"; self.cb_hard.Checked = True

        self.btn_bake = forms.Button(); self.btn_bake.Text = "Bake"; self.btn_bake.Height = 40

        # 이벤트 연결
        self.slider_main.ValueChanged += self.UpdateAll
        self.slider_seed.ValueChanged += self.UpdateAll
        self.slider_min_scale.ValueChanged += self.OnScaleSliderChanged
        self.slider_max_scale.ValueChanged += self.OnScaleSliderChanged
        self.cb_soft.CheckedChanged += self.UpdateAll
        self.cb_hard.CheckedChanged += self.UpdateAll
        self.btn_bake.Click += self.OnBakeClick

        layout = forms.DynamicLayout(); layout.Spacing = drawing.Size(10, 10)
        layout.AddRow(self.lbl_main, self.slider_main)
        layout.AddRow(self.lbl_seed, self.slider_seed)
        layout.AddRow(None)
        layout.AddRow(self.lbl_scale_title)
        layout.AddRow(self.lbl_scale_min, self.slider_min_scale)
        layout.AddRow(self.lbl_scale_max, self.slider_max_scale)
        layout.AddRow(None)
        layout.AddRow(self.cb_soft); layout.AddRow(self.cb_hard)
        layout.AddRow(None); layout.AddRow(self.btn_bake)
        self.Content = layout
        self.UpdateAll(None, None)

    def OnScaleSliderChanged(self, s, e):
        if self.slider_min_scale.Value > self.slider_max_scale.Value:
            if s == self.slider_min_scale: self.slider_max_scale.Value = self.slider_min_scale.Value
            else: self.slider_min_scale.Value = self.slider_max_scale.Value
        self.lbl_scale_min.Text = "최소 스케일: {}x".format(self.slider_min_scale.Value / 100.0)
        self.lbl_scale_max.Text = "최대 스케일: {}x".format(self.slider_max_scale.Value / 100.0)
        self.UpdateAll(None, None)

    def UpdateAll(self, s, e):
        val = self.slider_main.Value
        seed = self.slider_seed.Value
        random.seed(seed)
        s_min, s_max = self.slider_min_scale.Value / 100.0, self.slider_max_scale.Value / 100.0
        
        new_points = []
        if self.is_curve:
            self.lbl_main.Text = "배치 간격: {} mm".format(val)
            t_params = self.target_geom.DivideByLength(val, True)
            if t_params: new_points = [self.target_geom.PointAt(t) for t in t_params]
            else: new_points.append(self.target_geom.PointAtStart)
        else:
            self.lbl_main.Text = "시도 개수: {} 개".format(val)
            u_dom, v_dom = self.target_geom.Domain(0), self.target_geom.Domain(1)
            for _ in range(val):
                u = random.uniform(u_dom.Min, u_dom.Max)
                v = random.uniform(v_dom.Min, v_dom.Max)
                if self.target_geom.IsPointOnFace(u, v) != rg.PointFaceRelation.Exterior:
                    new_points.append(self.target_geom.PointAt(u, v))
        
        self.conduit.points = new_points
        active_pool = []
        if self.cb_soft.Checked: active_pool.extend(self.library["SoftWood"])
        if self.cb_hard.Checked: active_pool.extend(self.library["HardWood"])
        
        new_geoms = []
        if active_pool:
            for pt in new_points:
                source = random.choice(active_pool)
                scale = random.uniform(s_min, s_max)
                angle = random.uniform(0, 2 * math.pi)
                target_plane = rg.Plane(pt, rg.Vector3d.ZAxis)
                xform_move = rg.Transform.PlaneToPlane(rg.Plane.WorldXY, target_plane)
                xform_rot = rg.Transform.Rotation(angle, rg.Vector3d.ZAxis, pt)
                xform_scale = rg.Transform.Scale(pt, scale)
                temp_geom = source.Duplicate()
                temp_geom.Transform(xform_rot * xform_scale * xform_move)
                new_geoms.append(temp_geom)
        
        self.conduit.geometries = new_geoms
        sc.doc.Views.Redraw()

    def OnBakeClick(self, s, e):
        if not self.conduit.geometries: return
        layer_name = "Tree"
        layer_index = sc.doc.Layers.FindByFullPath(layer_name, -1)
        if layer_index < 0:
            new_layer = Rhino.DocObjects.Layer()
            new_layer.Name = layer_name; new_layer.Color = System.Drawing.Color.SeaGreen
            layer_index = sc.doc.Layers.Add(new_layer)
        rs.EnableRedraw(False)
        for g in self.conduit.geometries:
            obj_id = sc.doc.Objects.AddMesh(g) if isinstance(g, rg.Mesh) else sc.doc.Objects.AddBrep(g)
            if obj_id:
                obj = sc.doc.Objects.FindId(obj_id)
                obj.Attributes.LayerIndex = layer_index
                obj.CommitChanges()
        rs.EnableRedraw(True); self.Close()

    def OnClosed(self, e):
        self.conduit.Enabled = False
        sc.doc.Views.Redraw()
        # Rhino 8 에러 방지용 명시적 호출
        forms.Form.OnClosed(self, e)

def main():
    tree_lib = load_tree_library("Source.3dm")
    if not tree_lib:
        rs.MessageBox("'Source.3dm' 파일을 찾을 수 없습니다.")
        return
    go = Rhino.Input.Custom.GetObject()
    go.SetCommandPrompt("면 또는 커브를 선택하세요")
    go.GeometryFilter = Rhino.DocObjects.ObjectType.Surface | Rhino.DocObjects.ObjectType.Curve
    go.Get()
    if go.CommandResult() != Rhino.Commands.Result.Success: return
    obj_ref = go.Object(0)
    selected_geom = obj_ref.Face() if obj_ref.Surface() else obj_ref.Curve()

    if selected_geom:
        form = TreeMasterForm()
        form.SetupData(selected_geom, tree_lib)
        form.Show()

if __name__ == "__main__":
    main()