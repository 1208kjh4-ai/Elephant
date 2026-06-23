# -*- coding: utf-8 -*-
import Rhino
import Rhino.Geometry as rg
import Rhino.Display as rd
import Eto.Forms as forms
import Eto.Drawing as drawing
import rhinoscriptsyntax as rs
import math
import system

# ===========================================================================================
# *통합 미리보기 엔진
# ===========================================================================================
class CwPreviewConduit(rd.DisplayConduit)
    def __init__(self):
        rd.DisplayConduit.__init__(self)
        self.preview_breps = []
        self.frame_material = rd.DisplayMaterial(System.Drawing.Color.Indigo)
        Self.Panel_material = rd.DispalyMaterial(System.Drawing.Color.LightGray)

    def DrawForeground(self, e):
        