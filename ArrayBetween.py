# -*- coding: utf-8 -*-
import Rhino
import Rhino.Geometry as rg
import Rhino.Display as rd
import Rhino.UI
import Rhino.Input.Custom as ric
import Rhino.DocObjects as rdo
import Eto.Forms as forms
import Eto.Drawing as drawing
import rhinoscriptsyntax as rs
import math
import System

# ==============================================================================
# [1. 실시간 프리뷰를 위한 Display Conduit 클래스]
# ==============================================================================
class PreviewConduit(rd.DisplayConduit):
    def __init__(self):
        super(PreviewConduit, self).__init__()
        self.breps = []
        self.material = rd.DisplayMaterial()
        self.material.Diffuse = System.Drawing.Color.LightSkyBlue
        self.material.Transparency = 0.3

    def DrawShaded(self, e):
        for brep in self.breps:
            e.Display.DrawBrepShaded(brep, self.material)

    def DrawForeground(self, e):
        for brep in self.breps:
            e.Display.DrawBrepWires(brep, System.Drawing.Color.DarkBlue, 2)

# ==============================================================================
# [2. Eto Forms UI 다이얼로그 클래스 (배열 전용)]
# ==============================================================================
class ArrayDialog(forms.Form): 
    def __init__(self):
        super(ArrayDialog, self).__init__()
        self.Title = "실시간 다중 배열(Array) 툴"
        self.Padding = drawing.Padding(15)
        self.Resizable = False
        
        self.Topmost = True 
        self.Owner = Rhino.UI.RhinoEtoApp.MainWindow

    def SetupData(self, base_brep, p1, p2, default_n):
        self.base_brep = base_brep
        self.P1 = rg.Point3d(p1.X, p1.Y, p1.Z)
        self.P2 = rg.Point3d(p2.X, p2.Y, p2.Z)
        
        # 시작점과 끝점을 연결하는 전체 벡터
        self.vector_total = self.P2 - self.P1
        
        self.preview_breps = []
        self.conduit = PreviewConduit()
        self.conduit.Enabled = True
        
        self.lbl_count = forms.Label()
        self.lbl_count.Font = drawing.Font("Malgun Gothic", 10, drawing.FontStyle.Bold)
        
        self.slider = forms.Slider()
        self.slider.MinValue = 1
        self.slider.MaxValue = 100 
        self.slider.Value = default_n
        self.slider.Width = 250
        self.slider.ValueChanged += self.OnSliderChanged
        self.slider.KeyDown += self.OnKeyDown 
        
        # [수정됨] Rhino 8 호환을 위해 괄호 안의 Text 속성을 밖으로 뺐습니다.
        self.btn_ok = forms.Button()
        self.btn_ok.Text = "확인 (생성)"
        self.btn_ok.Click += self.OnOk
        
        self.btn_cancel = forms.Button()
        self.btn_cancel.Text = "취소"
        self.btn_cancel.Click += self.OnCancel

        self.KeyDown += self.OnKeyDown

        layout = forms.DynamicLayout()
        layout.Spacing = drawing.Size(10, 10)
        layout.AddRow(self.lbl_count)
        layout.AddRow(self.slider)
        layout.AddRow(None)
        
        btn_layout = forms.DynamicLayout()
        btn_layout.BeginHorizontal()
        btn_layout.Add(None, True)
        btn_layout.Add(self.btn_ok)
        btn_layout.Add(self.btn_cancel)
        btn_layout.EndHorizontal()
        
        layout.AddRow(btn_layout)
        self.Content = layout

        self.UpdateGeometry()

    def OnKeyDown(self, sender, e):
        if e.Key == forms.Keys.Enter:
            self.OnOk(None, None)
            e.Handled = True
        elif e.Key == forms.Keys.Escape:
            self.OnCancel(None, None)
            e.Handled = True

    def OnOk(self, sender, e):
        if self.preview_breps:
            for brep in self.preview_breps:
                Rhino.RhinoDoc.ActiveDoc.Objects.AddBrep(brep)
            Rhino.RhinoDoc.ActiveDoc.Views.Redraw()
        self.Close()

    def OnCancel(self, sender, e):
        self.Close()

    def GenerateArray(self, N):
        step_vec = self.vector_total / float(N)
        arrayed_breps = []
        
        for i in range(1, N + 1):
            move_vec = step_vec * float(i)
            new_brep = self.base_brep.Duplicate()
            new_brep.Translate(move_vec)
            arrayed_breps.append(new_brep)
            
        return arrayed_breps

    def UpdateGeometry(self):
        N = int(self.slider.Value)
        self.lbl_count.Text = "배열 개수: {} 개".format(N)
        self.preview_breps = self.GenerateArray(N)
        self.conduit.breps = self.preview_breps
        Rhino.RhinoDoc.ActiveDoc.Views.Redraw()

    def OnSliderChanged(self, sender, e):
        self.UpdateGeometry()

    def OnClosed(self, e):
        self.conduit.Enabled = False
        Rhino.RhinoDoc.ActiveDoc.Views.Redraw()
        super(ArrayDialog, self).OnClosed(e)

# ==============================================================================
# [3. 메인 실행부]
# ==============================================================================
def main():
    O1 = rs.GetObject("배열(Array)할 기준 솔리드나 서피스를 선택하세요", rs.filter.surface | rs.filter.polysurface)
    if not O1: return
    
    base_brep = rs.coercebrep(O1)

    P1 = rs.GetPoint("시작점(Start Point)을 지정하세요")
    if not P1: return
    
    P2 = rs.GetPoint("끝점(End Point)을 지정하세요")
    if not P2: return
    
    if P1.DistanceTo(P2) < 0.001:
        rs.MessageBox("시작점과 끝점이 너무 가깝습니다.")
        return

    default_n = 5

    dialog = ArrayDialog()
    dialog.SetupData(base_brep, P1, P2, default_n)
    dialog.Show()

if __name__ == "__main__":
    main()