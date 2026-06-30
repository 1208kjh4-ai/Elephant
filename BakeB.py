# -*- coding: utf-8 -*-
import rhinoscriptsyntax as rs
import Rhino
import Rhino.Geometry as rg
import scriptcontext as sc
import System

# Eto UI 모듈
import Eto.Forms as forms
import Eto.Drawing as drawing

try:
    import shapefile
except ImportError:
    rs.MessageBox(u"shapefile.py 모듈을 찾을 수 없습니다.\n해당 파일을 라이노 scripts 폴더에 넣어주세요.")
    shapefile = None

# -------------------------------------------------------------------------
# 1. 프리뷰 렌더링 엔진 (전체 객체 렌더링)
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
        
        # [수정됨] 제한 없이 모든 커브를 순회하며 프리뷰 메쉬 생성
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
                    # 프리뷰 화면에 보여주기 위한 임시 가벼운 메쉬
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
# 2. 메인 UI 
# -------------------------------------------------------------------------
class ShpMassDialog(forms.Dialog[bool]):
    def __init__(self, shp_path):
        self.Title = u"Elephant_Tools - SHP 매스 변환기 v3.3"
        self.Padding = drawing.Padding(20)
        self.Resizable = False
        self.ClientSize = drawing.Size(400, 200) # UI 크기를 넉넉하게 키움
        
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
                    u_f = f.decode('cp949', 'ignore')
                    self.fields.append(u_f)
                except:
                    self.fields.append(unicode(f))
            else:
                self.fields.append(unicode(f))
        
        rs.Prompt(u"기하학 데이터를 해석하는 중입니다... 전체 데이터를 불러옵니다.")
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
        # [수정됨] 층수 필드 선택 레이블 강조
        self.lbl_field = forms.Label(Text=u"📌 1. 층수 데이터 필드(레이어) 선택:")
        self.cmb_field = forms.DropDown()
        self.cmb_field.DataStore = self.fields
        
        default_idx = 0
        for i, f in enumerate(self.fields):
            if "FLR" in f.upper() or u"층" in f:
                default_idx = i
                break
        self.cmb_field.SelectedIndex = default_idx
        self.cmb_field.SelectedIndexChanged += self.on_value_changed
        
        self.lbl_height = forms.Label(Text=u"📐 2. 기준 층고 입력 (현재 단위와 1:1 매칭):")
        self.nud_height = forms.NumericStepper()
        self.nud_height.DecimalPlaces = 1
        self.nud_height.Increment = 0.5
        self.nud_height.Value = 3.0 
        self.nud_height.ValueChanged += self.on_value_changed
        
        self.btn_ok = forms.Button(Text=u"Brep(솔리드) 생성하기")
        self.btn_ok.Click += self.on_ok
        self.btn_cancel = forms.Button(Text=u"취소")
        self.btn_cancel.Click += self.on_cancel
        
        layout = forms.DynamicLayout()
        layout.Spacing = drawing.Size(10, 15)
        layout.AddRow(self.lbl_field, self.cmb_field)
        layout.AddRow(self.lbl_height, self.nud_height)
        layout.Add(None)
        layout.AddRow(self.btn_ok, self.btn_cancel)
        
        self.Content = layout

    def setup_preview(self):
        # [수정됨] 제한 없이 모든 커브를 Conduit에 넘김
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
                self.all_floors_data.append(0)
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

    def on_ok(self, sender, e):
        self.Close(True)

    def on_cancel(self, sender, e):
        self.Close(False)

    def OnClosed(self, e):
        if self.conduit:
            self.conduit.Enabled = False
            self.conduit = None
        sc.doc.Views.Redraw()
        super(ShpMassDialog, self).OnClosed(e)

# -------------------------------------------------------------------------
# 3. 메인 실행 및 Brep Bake 엔지니어링
# -------------------------------------------------------------------------
def main():
    shp_path = rs.OpenFileName(u"건물 SHP 파일을 선택하세요", "Shapefiles (*.shp)|*.shp||")
    if not shp_path: return
    
    dialog = ShpMassDialog(shp_path)
    result = dialog.ShowModal(Rhino.UI.RhinoEtoApp.MainWindow)
    
    if result:
        field_idx = dialog.cmb_field.SelectedIndex
        floor_height_val = dialog.nud_height.Value 
        
        rs.EnableRedraw(False)
        generated_count = 0
        
        for i, crv in enumerate(dialog.all_curves):
            if not crv: continue
            
            rec = dialog.records[i]
            try:
                floors = float(rec[field_idx])
                if floors <= 0: floors = 1.0
            except:
                floors = 1.0
                
            total_height = floors * floor_height_val
            
            rc, plane = crv.TryGetPlane()
            if rc and plane.ZAxis.Z < 0:
                crv.Reverse()
                
            extrusion = rg.Extrusion.Create(crv, total_height, True)
            
            if extrusion:
                # [수정됨] 최종 결과물을 Mesh가 아닌 무거운 형태의 완벽한 Brep(폴리서피스)으로 출력!
                brep = extrusion.ToBrep(False)
                if brep:
                    sc.doc.Objects.AddBrep(brep)
                    generated_count += 1
                
        rs.EnableRedraw(True)
        rs.MessageBox(u"총 {} 개의 건물 Brep(폴리서피스)이 성공적으로 빌드되었습니다! 🏙️".format(generated_count))

if __name__ == "__main__":
    main()