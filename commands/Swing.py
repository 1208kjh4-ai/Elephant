# -*- coding: utf-8 -*-
import Rhino
import Rhino.Geometry as rg
import Rhino.Display as rd
import Eto.Forms as forms
import Eto.Drawing as drawing
import rhinoscriptsyntax as rs
import scriptcontext as sc
import math
import System
import os
import json
import codecs

# ==============================================================================
# [0. 수정 기능용 메타데이터 키]
# 생성된 객체마다 같은 Door ID와 설정값을 UserText로 저장합니다.
# 다음 실행 시 선택 객체의 UserText를 읽어 수정 모드로 자동 진입합니다.
# ==============================================================================
TOOL_NAME = "SwingDoorEditable"
META_PREFIX = "SwingDoor_Edit_"
KEY_TOOL = META_PREFIX + "Tool"
KEY_ID = META_PREFIX + "Id"
KEY_BASE_PLANE = META_PREFIX + "BasePlane"
KEY_WIDTH = META_PREFIX + "Width"
KEY_HEIGHT = META_PREFIX + "Height"
KEY_PART = META_PREFIX + "Part"
PRESET_FILE_NAME = "SwingDoorPresets.json"
PRESET_FOLDER_NAME = "ElephantTools"


# ==============================================================================
# [1. 통합 미리보기 엔진]
# ==============================================================================
class DoorPreviewConduit(rd.DisplayConduit):
    def __init__(self):
        rd.DisplayConduit.__init__(self)
        self.preview_breps = []
        self.frame_material = rd.DisplayMaterial(System.Drawing.Color.Indigo)
        self.panel_material = rd.DisplayMaterial(System.Drawing.Color.LightGray)
        self.glass_material = rd.DisplayMaterial(System.Drawing.Color.LightSkyBlue, 0.5)
        self.hardware_material = rd.DisplayMaterial(System.Drawing.Color.DarkGray)

    def DrawForeground(self, e):
        for name, brep in self.preview_breps:
            if not brep or not brep.IsValid: continue
            
            if name == "frame": 
                e.Display.DrawBrepShaded(brep, self.frame_material)
            elif name == "panel": 
                e.Display.DrawBrepShaded(brep, self.panel_material)
            elif name == "glass": 
                e.Display.DrawBrepShaded(brep, self.glass_material)
            elif name == "hardware": 
                e.Display.DrawBrepShaded(brep, self.hardware_material)
                
            e.Display.DrawBrepWires(brep, System.Drawing.Color.Black, 1)

# ==============================================================================
# [2. 여닫이 세부 설정 창]
# ==============================================================================
class SwingDoorDialog(forms.Dialog[bool]):
    def __init__(self, base_plane, width, height, initial_settings=None, edit_mode=False):
        self.edit_mode = edit_mode
        self.Title = "문 세부 설정 - 수정" if edit_mode else "문 세부 설정"
        self.Padding = drawing.Padding(20)
        self.base_plane = base_plane
        self.width = width
        self.height = height
        self.Resizable = True
        self.Topmost = True
        self.ClientSize = drawing.Size(430, 370)
        self._preview_closed = False
        self._suppress_preview_update = False
        
        self.conduit = DoorPreviewConduit()
        self.conduit.Enabled = True

        s = initial_settings if initial_settings is not None else sc.sticky.get("SwingDoor_Settings", {})
        s = _normalize_swing_settings(s)
        self.presets = _load_swing_presets()

        self.dd_door_style = forms.DropDown()
        self.dd_door_style.DataStore = ["0. 솔리드 문", "1. 유리 문"]
        self.dd_door_style.SelectedIndex = 1 if s.get("is_glass", False) else 0

        # [추가] 유리문 프레임 세부 옵션
        self.dd_glass_frame = forms.DropDown()
        self.dd_glass_frame.DataStore = ["0. 상하좌우 프레임", "1. 상하 프레임", "2. 프레임 없음"]
        self.dd_glass_frame.SelectedIndex = s.get("glass_frame_type", 0)
        self.dd_glass_frame.Enabled = (self.dd_door_style.SelectedIndex == 1)

        self.dd_door_count = forms.DropDown()
        self.dd_door_count.DataStore = ["0. 일반형", "1. 양문형"]
        self.dd_door_count.SelectedIndex = 1 if s.get("is_double", False) else 0

        self.dd_handle = forms.DropDown()
        self.dd_handle.DataStore = ["0. 없음", "1. 원형", "2. 레버형", "3. Push 형", "4. 수직 바", "5. 수직, 수평 바"]
        self.dd_handle.SelectedIndex = s.get("handle_type", 0)

        self.txt_thick = forms.TextBox(Text=s.get("thick", "30"))
        self.txt_depth = forms.TextBox(Text=s.get("depth", "200"))
        self.txt_panel_frame = forms.TextBox(Text=s.get("panel_frame", "80")) 
        
        self._syncing_open_value = False
        open_init = self.NormalizeOpenAngle(s.get("open_val", 0))
        self.sli_open = forms.Slider(MinValue=-90, MaxValue=90, Value=open_init)
        self.txt_open_val = forms.TextBox(Text=str(open_init))
        self.txt_open_val.Width = 50
        self.lbl_open_unit = forms.Label(Text="°")
        
        self.cb_flip = forms.CheckBox(Text="뒤집기", Checked=s.get("flip", False))

        # [추가] 사용자 프리셋 UI
        self.dd_preset = forms.DropDown()
        self.dd_preset.Width = 190
        self.txt_preset_name = forms.TextBox()
        self.txt_preset_name.Width = 150
        self.btn_preset_load = forms.Button(Text="불러오기")
        self.btn_preset_save = forms.Button(Text="저장")
        self.btn_preset_delete = forms.Button(Text="삭제")
        self._refresh_preset_dropdown()

        layout = forms.DynamicLayout()
        layout.Spacing = drawing.Size(5, 5)

        preset_load_layout = forms.DynamicLayout()
        preset_load_layout.BeginHorizontal()
        preset_load_layout.Add(self.dd_preset, True, False)
        preset_load_layout.Add(self.btn_preset_load, False, False)
        preset_load_layout.EndHorizontal()
        layout.AddRow("프리셋 목록:", preset_load_layout)

        preset_save_layout = forms.DynamicLayout()
        preset_save_layout.BeginHorizontal()
        preset_save_layout.Add(self.txt_preset_name, True, False)
        preset_save_layout.Add(self.btn_preset_save, False, False)
        preset_save_layout.Add(self.btn_preset_delete, False, False)
        preset_save_layout.EndHorizontal()
        layout.AddRow("프리셋 이름:", preset_save_layout)
        layout.AddRow(forms.Label(), forms.Label())

        layout.AddRow("문 스타일:", self.dd_door_style)
        layout.AddRow("유리문 프레임:", self.dd_glass_frame) # [추가] UI에 반영
        layout.AddRow("여닫이 개수:", self.dd_door_count)
        layout.AddRow("손잡이 형태:", self.dd_handle)
        layout.AddRow(forms.Label(), forms.Label())
        
        layout.AddRow("문틀 두께:", self.txt_thick)
        layout.AddRow("문틀 깊이:", self.txt_depth)
        layout.AddRow("프레임 두께:", self.txt_panel_frame)
        
        open_layout = forms.DynamicLayout()
        open_layout.BeginHorizontal()
        open_layout.Add(self.sli_open, True, False)
        open_layout.Add(self.txt_open_val, False, False)
        open_layout.Add(self.lbl_open_unit)
        open_layout.EndHorizontal()
        layout.AddRow("개방 각도:", open_layout)
        
        layout.AddRow(self.cb_flip)
        
        btn_ok = forms.Button(Text=("수정" if self.edit_mode else "생성"))
        btn_ok.Click += self.OnOkClicked
        layout.AddRow(btn_ok)
        self.Content = layout

        # [추가] 유리문 스타일 선택 시에만 프레임 옵션 활성화
        def OnStyleChanged(sender, e):
            self.dd_glass_frame.Enabled = (self.dd_door_style.SelectedIndex == 1)
            self.UpdatePreview()

        self.dd_door_style.SelectedIndexChanged += OnStyleChanged
        self.dd_glass_frame.SelectedIndexChanged += lambda sender,e: self.UpdatePreview()

        self.dd_door_count.SelectedIndexChanged += lambda sender,e: self.UpdatePreview()
        self.cb_flip.CheckedChanged += lambda sender,e: self.UpdatePreview()
        self.dd_handle.SelectedIndexChanged += lambda sender,e: self.UpdatePreview()
        
        self.txt_thick.TextChanged += lambda sender,e: self.UpdatePreview()
        self.txt_depth.TextChanged += lambda sender,e: self.UpdatePreview()
        self.txt_panel_frame.TextChanged += lambda sender,e: self.UpdatePreview()
        self.sli_open.ValueChanged += self.OnSliderChanged
        self.txt_open_val.TextChanged += self.OnOpenTextChanged

        self.dd_preset.SelectedIndexChanged += self.OnPresetSelectedChanged
        self.btn_preset_load.Click += self.OnPresetLoadClicked
        self.btn_preset_save.Click += self.OnPresetSaveClicked
        self.btn_preset_delete.Click += self.OnPresetDeleteClicked

        self.UpdatePreview()

    def NormalizeOpenAngle(self, value):
        try:
            angle = int(round(float(value)))
        except:
            angle = 0
        if angle < -90: angle = -90
        if angle > 90: angle = 90
        return angle

    def GetOpenAngleValue(self):
        try:
            text = self.txt_open_val.Text.strip()
            if text in ["", "-", "+"]:
                raise Exception()
            return self.NormalizeOpenAngle(text)
        except:
            return self.NormalizeOpenAngle(self.sli_open.Value)

    def OnSliderChanged(self, sender, e):
        if self._syncing_open_value: return
        angle = self.NormalizeOpenAngle(self.sli_open.Value)
        self._syncing_open_value = True
        self.txt_open_val.Text = str(angle)
        self._syncing_open_value = False
        self.UpdatePreview()

    def OnOpenTextChanged(self, sender, e):
        if self._syncing_open_value: return
        text = self.txt_open_val.Text.strip()
        if text in ["", "-", "+"]:
            return
        try:
            angle = int(round(float(text)))
        except:
            return
        angle = self.NormalizeOpenAngle(angle)
        self._syncing_open_value = True
        if self.sli_open.Value != angle:
            self.sli_open.Value = angle
        if text != str(angle):
            self.txt_open_val.Text = str(angle)
        self._syncing_open_value = False
        self.UpdatePreview()

    def GetCurrentSettings(self):
        return {
            "is_glass": bool(self.dd_door_style.SelectedIndex == 1),
            "glass_frame_type": int(self.dd_glass_frame.SelectedIndex),
            "is_double": bool(self.dd_door_count.SelectedIndex == 1),
            "handle_type": int(self.dd_handle.SelectedIndex),
            "thick": str(self.txt_thick.Text),
            "depth": str(self.txt_depth.Text),
            "panel_frame": str(self.txt_panel_frame.Text),
            "open_val": int(self.GetOpenAngleValue()),
            "flip": bool(self.cb_flip.Checked)
        }

    def ApplySettingsToUI(self, settings):
        s = _normalize_swing_settings(settings)
        self._suppress_preview_update = True
        try:
            self.dd_door_style.SelectedIndex = 1 if s.get("is_glass", False) else 0

            self.dd_glass_frame.SelectedIndex = _clamp_int(s.get("glass_frame_type", 0), 0, 2)

            self.dd_door_count.SelectedIndex = 1 if s.get("is_double", False) else 0

            self.dd_handle.SelectedIndex = _clamp_int(s.get("handle_type", 0), 0, 5)
            self.txt_thick.Text = str(s.get("thick", "30"))
            self.txt_depth.Text = str(s.get("depth", "200"))
            self.txt_panel_frame.Text = str(s.get("panel_frame", "80"))
            self.cb_flip.Checked = bool(s.get("flip", False))

            angle = self.NormalizeOpenAngle(s.get("open_val", 0))
            self._syncing_open_value = True
            self.sli_open.Value = angle
            self.txt_open_val.Text = str(angle)
            self._syncing_open_value = False

            self.dd_glass_frame.Enabled = (self.dd_door_style.SelectedIndex == 1)
        finally:
            self._suppress_preview_update = False
        self.UpdatePreview()

    def _refresh_preset_dropdown(self, selected_name=None):
        names = sorted(self.presets.keys()) if self.presets else []
        data = ["<프리셋 선택>"] + names
        self.dd_preset.DataStore = data
        if selected_name and selected_name in names:
            self.dd_preset.SelectedIndex = names.index(selected_name) + 1
            self.txt_preset_name.Text = selected_name
        else:
            self.dd_preset.SelectedIndex = 0

    def _selected_preset_name(self):
        try:
            idx = int(self.dd_preset.SelectedIndex)
        except:
            idx = 0
        if idx <= 0:
            return None
        try:
            return str(self.dd_preset.SelectedValue)
        except:
            try:
                return str(self.dd_preset.DataStore[idx])
            except:
                return None

    def OnPresetSelectedChanged(self, sender, e):
        name = self._selected_preset_name()
        if name:
            self.txt_preset_name.Text = name

    def OnPresetLoadClicked(self, sender, e):
        name = self._selected_preset_name()
        if not name:
            name = str(self.txt_preset_name.Text).strip()
        if not name or name not in self.presets:
            rs.MessageBox("불러올 프리셋을 선택하세요.", 0, "프리셋")
            return
        self.ApplySettingsToUI(self.presets[name])

    def OnPresetSaveClicked(self, sender, e):
        name = str(self.txt_preset_name.Text).strip()
        if not name:
            rs.MessageBox("프리셋 이름을 입력하세요.", 0, "프리셋 저장")
            return

        if name in self.presets:
            rc = rs.MessageBox("같은 이름의 프리셋이 이미 있습니다.\n현재 값으로 덮어쓰시겠습니까?", 4, "프리셋 저장")
            if rc != 6:
                return

        self.presets[name] = self.GetCurrentSettings()
        if _save_swing_presets(self.presets):
            self._refresh_preset_dropdown(name)
        else:
            rs.MessageBox("프리셋 저장에 실패했습니다.", 0, "프리셋 저장 오류")

    def OnPresetDeleteClicked(self, sender, e):
        name = self._selected_preset_name()
        if not name:
            name = str(self.txt_preset_name.Text).strip()
        if not name or name not in self.presets:
            rs.MessageBox("삭제할 프리셋을 선택하세요.", 0, "프리셋 삭제")
            return

        rc = rs.MessageBox("'{}' 프리셋을 삭제하시겠습니까?".format(name), 4, "프리셋 삭제")
        if rc != 6:
            return

        try:
            del self.presets[name]
        except:
            pass
        if _save_swing_presets(self.presets):
            self.txt_preset_name.Text = ""
            self._refresh_preset_dropdown()
        else:
            rs.MessageBox("프리셋 삭제 저장에 실패했습니다.", 0, "프리셋 삭제 오류")

    def OnOkClicked(self, sender, e):
        angle = self.GetOpenAngleValue()
        self._syncing_open_value = True
        self.sli_open.Value = angle
        self.txt_open_val.Text = str(angle)
        self._syncing_open_value = False
        settings = self.GetCurrentSettings()
        sc.sticky["SwingDoor_Settings"] = settings
        self.ClosePreview()
        self.Close(True)

    def GenerateGeometry(self):
        W, H = self.width, self.height
        try: T = float(self.txt_thick.Text)
        except: T = 30.0
        try: D = float(self.txt_depth.Text)
        except: D = 200.0
        try: pf_w = float(self.txt_panel_frame.Text)
        except: pf_w = 80.0
        
        angle = math.radians(self.GetOpenAngleValue())
        is_double = bool(self.dd_door_count.SelectedIndex == 1)
        is_glass_door = bool(self.dd_door_style.SelectedIndex == 1)
        handle_idx = self.dd_handle.SelectedIndex
        
        parts = []
        
        # 문틀
        parts.append(("frame", rg.Box(rg.Plane.WorldXY, rg.Interval(0, T), rg.Interval(0, D), rg.Interval(0, H)).ToBrep()))
        parts.append(("frame", rg.Box(rg.Plane.WorldXY, rg.Interval(W - T, W), rg.Interval(0, D), rg.Interval(0, H)).ToBrep()))
        parts.append(("frame", rg.Box(rg.Plane.WorldXY, rg.Interval(T, W - T), rg.Interval(0, D), rg.Interval(H - T, H)).ToBrep()))
        
        p_w = (W - (2*T)) if not is_double else (W - (2*T))/2.0
        p_h = H - T
        
        def make_cyl(pt, dir_vec, r, h):
            plane = rg.Plane(pt, dir_vec)
            return rg.Cylinder(rg.Circle(plane, r), h).ToBrep(True, True)

        def make_u_bar(p1, p2, normal, stand_off, pipe_r, corner_r):
            vec_T = p2 - p1
            if vec_T.Length < 0.1: return []
            vec_T.Unitize()
            n_vec = rg.Vector3d(normal)
            n_vec.Unitize()
            
            s1 = p1 + n_vec * (stand_off - corner_r)
            e1 = p1 + n_vec * stand_off + vec_T * corner_r
            a1 = rg.Arc(s1, n_vec, e1).ToNurbsCurve()
            
            s2 = p2 + n_vec * stand_off - vec_T * corner_r
            e2 = p2 + n_vec * (stand_off - corner_r)
            a2 = rg.Arc(s2, vec_T, e2).ToNurbsCurve()
            
            joined = rg.Curve.JoinCurves([rg.LineCurve(p1, s1), a1, rg.LineCurve(e1, s2), a2, rg.LineCurve(e2, p2)])
            if joined:
                pipes = rg.Brep.CreatePipe(joined[0], pipe_r, False, rg.PipeCapMode.Flat, True, 0.01, 0.01)
                if pipes: return pipes
            return []
        
        def make_pi_bar(p1, p2, normal, stand_off, pipe_r, pi_inset):
            vec_T = p2 - p1
            l = vec_T.Length
            if l < 0.1: return []
            vec_T.Unitize()
            n_vec = rg.Vector3d(normal)
            n_vec.Unitize()
            
            res = []
            p_start = p1 + n_vec * stand_off
            res.append(make_cyl(p_start, vec_T, pipe_r, l))
            
            st1_pt = p1 + vec_T * pi_inset
            res.append(make_cyl(st1_pt, n_vec, pipe_r, stand_off))
            
            st2_pt = p2 - vec_T * pi_inset
            res.append(make_cyl(st2_pt, n_vec, pipe_r, stand_off))
            
            return res

        def make_panel(px, width, height, rot_angle, pivot):
            panel_parts = []
            
            knob_z = 950.0          
            knob_inset = 100.0       
            knob_head_r = 25.0      
            knob_stem_r = 10.0      
            knob_standoff = 30.0    

            lever_z = 950.0         
            lever_inset = 100.0      
            lever_len = 150.0       
            lever_r = 10.0          
            lever_standoff = 40.0   

            push_z = 1000.0         
            push_gap = 100.0        
            push_r = 15.0           
            push_standoff = 50.0    
            push_corner_r = 20.0    

            vbar_z = (height/2)-100          
            vbar_inset = 150       
            vbar_len = 1000.0        
            vbar_r = 15.0           
            vbar_standoff = 50.0    
            vbar_pi_inset = 200    

            asy_h_z = 950.0         
            asy_inset = 150.0      
            asy_v_gap_bottom = 950.0 
            asy_v_gap_top = 1250.0   
            asy_push_gap = asy_inset    
            asy_r = 15.0            
            asy_standoff = 50.0     
            asy_corner_r = 20.0     

            # 문짝 BRep 생성
            b_outer = rg.Box(rg.Plane.WorldXY, rg.Interval(px, px + width), rg.Interval(0, 30), rg.Interval(0, height)).ToBrep()
            
            if not is_glass_door:
                b_outer.Rotate(rot_angle, rg.Vector3d.ZAxis, pivot)
                panel_parts.append(("panel", b_outer))
            else:
                safe_pf_w = min(pf_w, width * 0.45, height * 0.45)
                glass_frame_idx = self.dd_glass_frame.SelectedIndex
                
                # [수정] 옵션에 따른 유리/프레임 분기 처리
                if glass_frame_idx == 0: 
                    # 0. 상하좌우 프레임
                    b_inner = rg.Box(rg.Plane.WorldXY, rg.Interval(px + safe_pf_w, px + width - safe_pf_w), rg.Interval(-10, 40), rg.Interval(safe_pf_w, height - safe_pf_w)).ToBrep()
                    diff = rg.Brep.CreateBooleanDifference(b_outer, b_inner, 0.001)
                    b_frame = diff[0] if (diff and len(diff) > 0) else b_outer
                    b_frame.Rotate(rot_angle, rg.Vector3d.ZAxis, pivot)
                    panel_parts.append(("panel", b_frame))
                    
                    b_glass = rg.Box(rg.Plane.WorldXY, rg.Interval(px + safe_pf_w, px + width - safe_pf_w), rg.Interval(10, 20), rg.Interval(safe_pf_w, height - safe_pf_w)).ToBrep()
                    b_glass.Rotate(rot_angle, rg.Vector3d.ZAxis, pivot)
                    panel_parts.append(("glass", b_glass))

                elif glass_frame_idx == 1: 
                    # 1. 상하 프레임 (좌우는 유리만 노출)
                    b_frame_bottom = rg.Box(rg.Plane.WorldXY, rg.Interval(px, px + width), rg.Interval(0, 30), rg.Interval(0, safe_pf_w)).ToBrep()
                    b_frame_bottom.Rotate(rot_angle, rg.Vector3d.ZAxis, pivot)
                    panel_parts.append(("panel", b_frame_bottom))

                    b_frame_top = rg.Box(rg.Plane.WorldXY, rg.Interval(px, px + width), rg.Interval(0, 30), rg.Interval(height - safe_pf_w, height)).ToBrep()
                    b_frame_top.Rotate(rot_angle, rg.Vector3d.ZAxis, pivot)
                    panel_parts.append(("panel", b_frame_top))

                    b_glass = rg.Box(rg.Plane.WorldXY, rg.Interval(px, px + width), rg.Interval(10, 20), rg.Interval(safe_pf_w, height - safe_pf_w)).ToBrep()
                    b_glass.Rotate(rot_angle, rg.Vector3d.ZAxis, pivot)
                    panel_parts.append(("glass", b_glass))

                elif glass_frame_idx == 2: 
                    # 2. 프레임 없음 (12t 두께의 순수 강화유리 형태)
                    b_glass = rg.Box(rg.Plane.WorldXY, rg.Interval(px, px + width), rg.Interval(0, 30), rg.Interval(0, height)).ToBrep()
                    b_glass.Rotate(rot_angle, rg.Vector3d.ZAxis, pivot)
                    panel_parts.append(("glass", b_glass))

            # 손잡이 로직
            if handle_idx > 0:
                hw_list = []
                is_left_hinge = (abs(pivot.X - px) < 1.0)
                hinge_dir = rg.Vector3d(-1,0,0) if is_left_hinge else rg.Vector3d(1,0,0)

                if handle_idx == 1:
                    hx = (px + width - knob_inset) if is_left_hinge else (px + knob_inset)
                    hw_list.append(make_cyl(rg.Point3d(hx, 0, knob_z), rg.Vector3d(0,-1,0), knob_stem_r, knob_standoff))
                    hw_list.append(make_cyl(rg.Point3d(hx, -knob_standoff+10, knob_z), rg.Vector3d(0,-1,0), knob_head_r, 10))
                    hw_list.append(make_cyl(rg.Point3d(hx, 30, knob_z), rg.Vector3d(0,1,0), knob_stem_r, knob_standoff))
                    hw_list.append(make_cyl(rg.Point3d(hx, 30+knob_standoff-10, knob_z), rg.Vector3d(0,1,0), knob_head_r, 10))
                
                elif handle_idx == 2:
                    hx = (px + width - lever_inset) if is_left_hinge else (px + lever_inset)
                    hw_list.append(make_cyl(rg.Point3d(hx, 0, lever_z), rg.Vector3d(0,-1,0), lever_r, lever_standoff))
                    hw_list.append(make_cyl(rg.Point3d(hx, -lever_standoff+5, lever_z), hinge_dir, lever_r, lever_len))
                    hw_list.append(make_cyl(rg.Point3d(hx, 30, lever_z), rg.Vector3d(0,1,0), lever_r, lever_standoff))
                    hw_list.append(make_cyl(rg.Point3d(hx, 30+lever_standoff-5, lever_z), hinge_dir, lever_r, lever_len))
                
                elif handle_idx == 3:
                    p1 = rg.Point3d(px + push_gap, 30, push_z)
                    p2 = rg.Point3d(px + width - push_gap, 30, push_z)
                    hw_list.extend(make_u_bar(p1, p2, rg.Vector3d(0,1,0), push_standoff, push_r, push_corner_r))

                elif handle_idx == 4:
                    hx = (px + width - vbar_inset) if is_left_hinge else (px + vbar_inset)
                    p1_f = rg.Point3d(hx, 0, vbar_z - vbar_len/2)
                    p2_f = rg.Point3d(hx, 0, vbar_z + vbar_len/2)
                    hw_list.extend(make_pi_bar(p1_f, p2_f, rg.Vector3d(0,-1,0), vbar_standoff, vbar_r, vbar_pi_inset))
                    
                    p1_b = rg.Point3d(hx, 30, vbar_z - vbar_len/2)
                    p2_b = rg.Point3d(hx, 30, vbar_z + vbar_len/2)
                    hw_list.extend(make_pi_bar(p1_b, p2_b, rg.Vector3d(0,1,0), vbar_standoff, vbar_r, vbar_pi_inset))

                elif handle_idx == 5:
                    hx = (px + width - asy_inset) if is_left_hinge else (px + asy_inset)
                    p1_f = rg.Point3d(hx, 0, asy_v_gap_bottom)           
                    p2_f = rg.Point3d(hx, 0, asy_v_gap_top)     
                    hw_list.extend(make_u_bar(p1_f, p2_f, rg.Vector3d(0,-1,0), asy_standoff, asy_r, asy_corner_r))
                    
                    p1_b = rg.Point3d(px + asy_push_gap, 30, asy_h_z)
                    p2_b = rg.Point3d(px + width - asy_push_gap, 30, asy_h_z)
                    hw_list.extend(make_u_bar(p1_b, p2_b, rg.Vector3d(0,1,0), asy_standoff, asy_r, asy_corner_r))

                for h_brep in hw_list:
                    if h_brep and h_brep.IsValid:
                        h_brep.Rotate(rot_angle, rg.Vector3d.ZAxis, pivot)
                        panel_parts.append(("hardware", h_brep))

            return panel_parts

        # 왼쪽 문짝
        pivot_l = rg.Point3d(T, 0, 0)
        parts.extend(make_panel(T, p_w, p_h, angle, pivot_l))
        
        # 오른쪽 문짝 (양문형)
        if is_double:
            pivot_r = rg.Point3d(W - T, 0, 0)
            parts.extend(make_panel(W - T - p_w, p_w, p_h, -angle, pivot_r))

        xform = rg.Transform.PlaneToPlane(rg.Plane.WorldXY, self.base_plane)
        if self.cb_flip.Checked: 
            xform = xform * rg.Transform.Scale(rg.Plane.WorldXY, 1, -1, 1)
        
        final = []
        for n, b in parts:
            b.Transform(xform)
            final.append((n, b))
        return final

    def UpdatePreview(self):
        if getattr(self, "_preview_closed", False):
            return
        if getattr(self, "_suppress_preview_update", False):
            return
        try:
            self.conduit.preview_breps = self.GenerateGeometry()
        except Exception as ex:
            print("문 프리뷰 갱신 오류:", ex)
            try:
                self.conduit.preview_breps = []
            except:
                pass
        try:
            Rhino.RhinoDoc.ActiveDoc.Views.Redraw()
        except:
            pass

    def ClosePreview(self):
        if getattr(self, "_preview_closed", False):
            return
        self._preview_closed = True
        try:
            self.conduit.Enabled = False
        except:
            pass
        try:
            self.conduit.preview_breps = []
        except:
            pass
        try:
            Rhino.RhinoDoc.ActiveDoc.Views.Redraw()
        except:
            pass

    def OnClosed(self, e):
        self.ClosePreview()
        try:
            super(SwingDoorDialog, self).OnClosed(e)
        except:
            pass

def bool_to_text(value):
    return "1" if value else "0"


def text_to_bool(value, default=False):
    if value is None: return default
    v = str(value).strip().lower()
    return v in ["1", "true", "yes", "y", "on"]


def text_to_int(value, default=0):
    try: return int(float(value))
    except: return default


def text_to_float(value, default=0.0):
    try: return float(value)
    except: return default


def plane_to_text(plane):
    vals = [
        plane.Origin.X, plane.Origin.Y, plane.Origin.Z,
        plane.XAxis.X, plane.XAxis.Y, plane.XAxis.Z,
        plane.YAxis.X, plane.YAxis.Y, plane.YAxis.Z
    ]
    return ",".join([str(float(v)) for v in vals])


def text_to_plane(value):
    try:
        vals = [float(x) for x in value.split(",")]
        if len(vals) != 9: return None
        origin = rg.Point3d(vals[0], vals[1], vals[2])
        x_axis = rg.Vector3d(vals[3], vals[4], vals[5])
        y_axis = rg.Vector3d(vals[6], vals[7], vals[8])
        if x_axis.Length < 1e-6 or y_axis.Length < 1e-6: return None
        x_axis.Unitize()
        y_axis.Unitize()
        return rg.Plane(origin, x_axis, y_axis)
    except:
        return None


def safe_get_user_text(obj_id, key):
    try:
        return rs.GetUserText(obj_id, key)
    except:
        return None


def safe_set_user_text(obj_id, key, value):
    try:
        rs.SetUserText(obj_id, key, str(value))
    except:
        pass


def object_ref_id(obj_ref):
    try:
        return obj_ref.ObjectId
    except:
        return None


def get_curve_from_objref(obj_ref):
    try:
        c = obj_ref.Curve()
        if c: return c
    except:
        pass
    return None


def _clamp_int(value, min_value, max_value):
    try:
        v = int(float(value))
    except:
        v = min_value
    if v < min_value: v = min_value
    if v > max_value: v = max_value
    return v


def _normalize_swing_settings(settings):
    if not settings:
        settings = {}
    return {
        "is_glass": text_to_bool(settings.get("is_glass", False), False),
        "glass_frame_type": _clamp_int(settings.get("glass_frame_type", 0), 0, 2),
        "is_double": text_to_bool(settings.get("is_double", False), False),
        "handle_type": _clamp_int(settings.get("handle_type", 0), 0, 5),
        "thick": str(settings.get("thick", "30")),
        "depth": str(settings.get("depth", "200")),
        "panel_frame": str(settings.get("panel_frame", "80")),
        "open_val": _clamp_int(settings.get("open_val", 0), -90, 90),
        "flip": text_to_bool(settings.get("flip", False), False)
    }


def _get_swing_preset_path():
    base = os.environ.get("APPDATA")
    if not base:
        try:
            base = os.path.expanduser("~")
        except:
            base = None
    if not base:
        base = os.getcwd()

    folder = os.path.join(base, PRESET_FOLDER_NAME)
    try:
        if not os.path.isdir(folder):
            os.makedirs(folder)
    except Exception as ex:
        print("프리셋 폴더 생성 오류:", ex)
    return os.path.join(folder, PRESET_FILE_NAME)


def _load_swing_presets():
    path = _get_swing_preset_path()
    if not os.path.exists(path):
        return {}
    try:
        with codecs.open(path, "r", "utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return {}
        presets = {}
        for name, settings in data.items():
            if not name or not isinstance(settings, dict):
                continue
            presets[str(name)] = _normalize_swing_settings(settings)
        return presets
    except Exception as ex:
        print("프리셋 불러오기 오류:", ex)
        return {}


def _save_swing_presets(presets):
    path = _get_swing_preset_path()
    try:
        clean = {}
        for name, settings in presets.items():
            if not name:
                continue
            clean[str(name)] = _normalize_swing_settings(settings)
        text = json.dumps(clean, ensure_ascii=False, indent=2, sort_keys=True)
        with codecs.open(path, "w", "utf-8") as f:
            f.write(text)
        return True
    except Exception as ex:
        print("프리셋 저장 오류:", ex)
        return False


# ==============================================================================
# [4-A. 이동/회전/복사 후 수정 보정 유틸리티]
# 저장된 기준 형상과 현재 선택 객체를 비교해 현재 Transform을 역산합니다.
# ==============================================================================
class _FakeTextBox(object):
    def __init__(self, text):
        self.Text = str(text)


class _FakeCheckBox(object):
    def __init__(self, checked):
        self.Checked = bool(checked)


class _FakeDropDown(object):
    def __init__(self, selected_index):
        self.SelectedIndex = int(selected_index)


class _SwingDoorGeometryContext(object):
    def __init__(self, base_plane, width, height, settings):
        settings = _normalize_swing_settings(settings)
        self.base_plane = rg.Plane(base_plane)
        self.width = float(width)
        self.height = float(height)
        self.cb_flip = _FakeCheckBox(settings.get("flip", False))
        self.dd_door_style = _FakeDropDown(1 if settings.get("is_glass", False) else 0)
        self.dd_door_count = _FakeDropDown(1 if settings.get("is_double", False) else 0)
        self.dd_glass_frame = _FakeDropDown(settings.get("glass_frame_type", 0))
        self.dd_handle = _FakeDropDown(settings.get("handle_type", 0))
        self.txt_thick = _FakeTextBox(settings.get("thick", "30"))
        self.txt_depth = _FakeTextBox(settings.get("depth", "200"))
        self.txt_panel_frame = _FakeTextBox(settings.get("panel_frame", "80"))
        self._open_val = settings.get("open_val", 0)

    def GetOpenAngleValue(self):
        try:
            angle = int(round(float(self._open_val)))
        except:
            angle = 0
        if angle < -90: angle = -90
        if angle > 90: angle = 90
        return angle


def _generate_reference_raw_parts(base_plane, width, height, settings):
    """UI를 열지 않고 기존 GenerateGeometry 로직만 재사용해 기준 형상을 생성합니다."""
    ctx = _SwingDoorGeometryContext(base_plane, width, height, settings)
    try:
        return SwingDoorDialog.GenerateGeometry(ctx)
    except TypeError:
        # IronPython 2.x unbound-method compatibility
        return SwingDoorDialog.GenerateGeometry.im_func(ctx)
    except Exception as ex:
        print("기준 문 형상 생성 오류:", ex)
        return []


def _generate_reference_baked_parts(base_plane, width, height, settings):
    """bake_swing_door와 최대한 같은 구조로 기준 부품 목록을 생성합니다."""
    frames = []
    panels = []
    glasses = []
    hardwares = []

    for name, brep in _generate_reference_raw_parts(base_plane, width, height, settings):
        if not brep or not brep.IsValid: continue
        if name == "frame": frames.append(brep)
        elif name == "panel": panels.append(brep)
        elif name == "glass": glasses.append(brep)
        elif name == "hardware": hardwares.append(brep)

    result = []
    if frames:
        try:
            union_frames = rg.Brep.CreateBooleanUnion(frames, Rhino.RhinoDoc.ActiveDoc.ModelAbsoluteTolerance)
        except:
            union_frames = None
        if union_frames:
            for b in union_frames:
                if b and b.IsValid: result.append(("frame", b))
        else:
            for b in frames:
                if b and b.IsValid: result.append(("frame", b))

    for b in panels:
        if b and b.IsValid: result.append(("panel", b))
    for b in glasses:
        if b and b.IsValid: result.append(("glass", b))
    for b in hardwares:
        if b and b.IsValid: result.append(("hardware", b))
    return result


def _get_brep_from_id(obj_id):
    try:
        return rs.coercebrep(obj_id)
    except:
        try:
            return rs.coercebrep(System.Guid(str(obj_id)))
        except:
            return None


def _get_brep_vertices(brep):
    pts = []
    if not brep: return pts
    try:
        count = brep.Vertices.Count
    except:
        try: count = len(brep.Vertices)
        except: count = 0
    for i in range(count):
        try:
            pts.append(rg.Point3d(brep.Vertices[i].Location))
        except:
            pass
    return pts


def _matching_tolerance(width, height):
    try: doc_tol = Rhino.RhinoDoc.ActiveDoc.ModelAbsoluteTolerance
    except: doc_tol = 0.001
    try: dim_tol = max(float(width), float(height)) * 0.001
    except: dim_tol = 0.0
    return max(doc_tol * 50.0, dim_tol, 1.0)


def _find_non_collinear_indices(points, tol):
    n = len(points)
    if n < 3: return None
    limit = min(n, 80)
    for i in range(limit):
        for j in range(i + 1, limit):
            v1 = points[j] - points[i]
            if v1.Length <= tol: continue
            for k in range(j + 1, limit):
                v2 = points[k] - points[i]
                if v2.Length <= tol: continue
                cross = rg.Vector3d.CrossProduct(v1, v2)
                if cross.Length > tol:
                    return i, j, k
    return None


def _plane_from_indexed_points(points, indices, tol):
    if not indices: return None
    p0 = points[indices[0]]
    p1 = points[indices[1]]
    p2 = points[indices[2]]
    x_axis = p1 - p0
    y_axis = p2 - p0
    if x_axis.Length <= tol or y_axis.Length <= tol: return None
    cross = rg.Vector3d.CrossProduct(x_axis, y_axis)
    if cross.Length <= tol: return None
    try:
        return rg.Plane(p0, x_axis, y_axis)
    except:
        return None


def _direct_brep_match_error(ref_brep, current_brep):
    ref_pts = _get_brep_vertices(ref_brep)
    cur_pts = _get_brep_vertices(current_brep)
    if len(ref_pts) < 3 or len(ref_pts) != len(cur_pts):
        return None
    max_err = 0.0
    for i in range(len(ref_pts)):
        d = ref_pts[i].DistanceTo(cur_pts[i])
        if d > max_err: max_err = d
    return max_err


def _compute_brep_transform_by_vertices(ref_brep, current_brep, width, height):
    ref_pts = _get_brep_vertices(ref_brep)
    cur_pts = _get_brep_vertices(current_brep)
    if len(ref_pts) < 3 or len(ref_pts) != len(cur_pts):
        return None, None

    tol = max(Rhino.RhinoDoc.ActiveDoc.ModelAbsoluteTolerance, 0.001)
    indices = _find_non_collinear_indices(ref_pts, tol)
    if not indices: return None, None

    ref_plane = _plane_from_indexed_points(ref_pts, indices, tol)
    cur_plane = _plane_from_indexed_points(cur_pts, indices, tol)
    if not ref_plane or not cur_plane: return None, None

    try:
        xform = rg.Transform.PlaneToPlane(ref_plane, cur_plane)
    except:
        return None, None

    max_err = 0.0
    for i in range(len(ref_pts)):
        p = rg.Point3d(ref_pts[i])
        p.Transform(xform)
        d = p.DistanceTo(cur_pts[i])
        if d > max_err: max_err = d

    if max_err > _matching_tolerance(width, height):
        return None, max_err
    return xform, max_err


def _resolve_current_edit_transform(selected_id, selected_part, base_plane, width, height, settings):
    """저장된 기준 문 형상에서 현재 선택 객체까지의 Transform을 계산합니다."""
    current_brep = _get_brep_from_id(selected_id)
    if not current_brep:
        return rg.Plane(base_plane), None

    ref_parts = _generate_reference_baked_parts(base_plane, width, height, settings)
    best_xform = None
    best_err = None

    for part_name, ref_brep in ref_parts:
        if selected_part and part_name != selected_part:
            continue
        xform, err = _compute_brep_transform_by_vertices(ref_brep, current_brep, width, height)
        if xform is None:
            continue
        if best_err is None or err < best_err:
            best_err = err
            best_xform = xform

    if best_xform:
        corrected_plane = rg.Plane(base_plane)
        corrected_plane.Transform(best_xform)
        return corrected_plane, best_xform

    return rg.Plane(base_plane), None


def _same_guid_like(a, b):
    return str(a).lower() == str(b).lower()


def _unique_object_ids(ids):
    result = []
    seen = set()
    for oid in ids or []:
        key = str(oid).lower()
        if key in seen:
            continue
        seen.add(key)
        result.append(oid)
    return result


def _filter_ids_near_selected(ids, selected_id, width, height, factor=1.75):
    """같은 Door ID가 복사본 간에 공유될 때 원본 세트까지 삭제되는 것을 줄이기 위한 공간 필터입니다."""
    selected_center = _get_bbox_center(selected_id)
    if not selected_center:
        return _unique_object_ids(ids)
    try:
        threshold = max(float(width), float(height)) * float(factor)
    except:
        threshold = 3500.0

    result = []
    for oid in ids or []:
        c = _get_bbox_center(oid)
        if c and c.DistanceTo(selected_center) <= threshold:
            result.append(oid)

    if not any(_same_guid_like(oid, selected_id) for oid in result):
        result.append(selected_id)
    return _unique_object_ids(result)


def _get_group_swing_object_ids(door_id, selected_id, width=None, height=None):
    try:
        groups = rs.ObjectGroups(selected_id) or []
    except:
        groups = []

    result = []
    for group_name in groups:
        try:
            group_ids = rs.ObjectsByGroup(group_name) or []
        except:
            group_ids = []
        for oid in group_ids:
            if safe_get_user_text(oid, KEY_TOOL) == TOOL_NAME and safe_get_user_text(oid, KEY_ID) == door_id:
                result.append(oid)

    result = _unique_object_ids(result)
    if width is not None and height is not None:
        result = _filter_ids_near_selected(result, selected_id, width, height, 1.75)
    return result


def _get_bbox_center(obj_id):
    try:
        bbox = rs.BoundingBox(obj_id)
        if bbox:
            sx = sy = sz = 0.0
            for p in bbox:
                sx += p.X; sy += p.Y; sz += p.Z
            return rg.Point3d(sx / len(bbox), sy / len(bbox), sz / len(bbox))
    except:
        pass
    return None


def _get_spatial_swing_object_ids(door_id, selected_id, width, height):
    selected_center = _get_bbox_center(selected_id)
    if not selected_center: return [selected_id]
    try:
        threshold = max(float(width), float(height)) * 1.35
    except:
        threshold = 3000.0

    ids = []
    for oid in get_swing_object_ids(door_id):
        c = _get_bbox_center(oid)
        if c and c.DistanceTo(selected_center) <= threshold:
            ids.append(oid)
    if not ids:
        ids = [selected_id]
    return ids


def _get_transform_matched_swing_object_ids(door_id, selected_id, base_plane, width, height, settings, xform):
    if not xform:
        return []
    all_ids = get_swing_object_ids(door_id)
    if not all_ids:
        return []

    ref_parts = _generate_reference_baked_parts(base_plane, width, height, settings)
    tol = _matching_tolerance(width, height)
    matched = []

    for oid in all_ids:
        current_brep = _get_brep_from_id(oid)
        if not current_brep: continue
        current_part = safe_get_user_text(oid, KEY_PART)
        for ref_part, ref_brep in ref_parts:
            if current_part and ref_part != current_part:
                continue
            dup = ref_brep.DuplicateBrep()
            dup.Transform(xform)
            err = _direct_brep_match_error(dup, current_brep)
            if err is not None and err <= tol:
                matched.append(oid)
                break

    if not any(_same_guid_like(oid, selected_id) for oid in matched):
        matched.append(selected_id)
    return matched


def get_current_swing_set_ids(door_id, selected_id, base_plane, width, height, settings, xform=None):
    """복사된 같은 Door ID 중에서 현재 선택된 문 세트만 찾습니다.

    손잡이는 Pipe 기반 Brep라 vertex matching이 frame/panel보다 불안정할 수 있습니다.
    그래서 Rhino Group을 먼저 사용하고, Transform 매칭 결과는 공간 필터 결과와 합쳐서
    hardware 객체가 삭제 대상에서 빠지는 상황을 줄입니다.
    """
    grouped = _get_group_swing_object_ids(door_id, selected_id, width, height)
    if grouped and len(grouped) >= 2:
        return grouped

    matched = _get_transform_matched_swing_object_ids(door_id, selected_id, base_plane, width, height, settings, xform)
    spatial = _get_spatial_swing_object_ids(door_id, selected_id, width, height)

    combined = []
    if matched:
        combined.extend(matched)
    if spatial:
        combined.extend(spatial)
    if grouped:
        combined.extend(grouped)

    combined = _filter_ids_near_selected(combined, selected_id, width, height, 1.75)
    if combined:
        return combined
    return [selected_id]


def load_swing_data_from_objref(obj_ref):
    obj_id = object_ref_id(obj_ref)
    if not obj_id: return None
    if safe_get_user_text(obj_id, KEY_TOOL) != TOOL_NAME: return None

    door_id = safe_get_user_text(obj_id, KEY_ID)
    base_plane = text_to_plane(safe_get_user_text(obj_id, KEY_BASE_PLANE))
    width = text_to_float(safe_get_user_text(obj_id, KEY_WIDTH), 0.0)
    height = text_to_float(safe_get_user_text(obj_id, KEY_HEIGHT), 0.0)

    if not door_id or base_plane is None or width <= 0 or height <= 0:
        return None

    settings = {
        "is_glass": text_to_bool(safe_get_user_text(obj_id, META_PREFIX + "is_glass"), False),
        "glass_frame_type": text_to_int(safe_get_user_text(obj_id, META_PREFIX + "glass_frame_type"), 0),
        "is_double": text_to_bool(safe_get_user_text(obj_id, META_PREFIX + "is_double"), False),
        "handle_type": text_to_int(safe_get_user_text(obj_id, META_PREFIX + "handle_type"), 0),
        "thick": safe_get_user_text(obj_id, META_PREFIX + "thick") or "30",
        "depth": safe_get_user_text(obj_id, META_PREFIX + "depth") or "200",
        "panel_frame": safe_get_user_text(obj_id, META_PREFIX + "panel_frame") or "80",
        "open_val": text_to_int(safe_get_user_text(obj_id, META_PREFIX + "open_val"), 0),
        "flip": text_to_bool(safe_get_user_text(obj_id, META_PREFIX + "flip"), False)
    }
    settings = _normalize_swing_settings(settings)

    selected_part = safe_get_user_text(obj_id, KEY_PART) or ""
    original_base_plane = rg.Plane(base_plane)
    corrected_base_plane, edit_xform = _resolve_current_edit_transform(
        obj_id, selected_part, original_base_plane, width, height, settings
    )
    edit_object_ids = get_current_swing_set_ids(
        door_id, obj_id, original_base_plane, width, height, settings, edit_xform
    )

    return {
        "mode": "edit",
        "door_id": door_id,
        "selected_id": obj_id,
        "selected_part": selected_part,
        "edit_object_ids": edit_object_ids,
        "base_plane": corrected_base_plane,
        "width": width,
        "height": height,
        "settings": settings
    }


def get_swing_object_ids(door_id):
    ids = []
    all_ids = rs.AllObjects()
    if not all_ids: return ids
    for obj_id in all_ids:
        if safe_get_user_text(obj_id, KEY_TOOL) == TOOL_NAME and safe_get_user_text(obj_id, KEY_ID) == door_id:
            ids.append(obj_id)
    return ids


def delete_swing_object_ids(obj_ids):
    """DeleteObjects가 일부 객체를 놓치는 경우를 줄이기 위한 개별 삭제 루틴입니다."""
    ids = _unique_object_ids(obj_ids)
    if not ids:
        return
    try:
        rs.UnselectAllObjects()
    except:
        pass
    for oid in ids:
        try:
            rs.UnlockObject(oid)
        except:
            pass
        try:
            rs.ShowObject(oid)
        except:
            pass
        try:
            Rhino.RhinoDoc.ActiveDoc.Objects.Delete(System.Guid(str(oid)), True)
        except:
            try:
                rs.DeleteObject(oid)
            except:
                pass


def save_swing_metadata(obj_id, door_id, part_name, base_plane, width, height, settings):
    safe_set_user_text(obj_id, KEY_TOOL, TOOL_NAME)
    safe_set_user_text(obj_id, KEY_ID, door_id)
    safe_set_user_text(obj_id, KEY_PART, part_name)
    safe_set_user_text(obj_id, KEY_BASE_PLANE, plane_to_text(base_plane))
    safe_set_user_text(obj_id, KEY_WIDTH, width)
    safe_set_user_text(obj_id, KEY_HEIGHT, height)

    for key, value in settings.items():
        if isinstance(value, bool):
            safe_set_user_text(obj_id, META_PREFIX + key, bool_to_text(value))
        else:
            safe_set_user_text(obj_id, META_PREFIX + key, value)

    try:
        rs.ObjectName(obj_id, "SwingDoor_" + str(door_id)[:8] + "_" + part_name)
    except:
        pass


def process_two_curves(crv1, crv2):
    if crv1 is None or crv2 is None: return None

    def get_bottom_top(c):
        s = c.PointAtStart
        e = c.PointAtEnd
        return (e, s) if s.Z > e.Z else (s, e)

    p1_b, p1_t = get_bottom_top(crv1)
    p2_b, p2_t = get_bottom_top(crv2)

    if p1_b.X > p2_b.X or (abs(p1_b.X - p2_b.X) < 1e-4 and p1_b.Y > p2_b.Y):
        p1_b, p2_b = p2_b, p1_b
        p1_t, p2_t = p2_t, p1_t

    z_vec = p1_t - p1_b
    height = z_vec.Length
    if height < 1e-4: return None
    z_vec.Unitize()

    x_vec = p2_b - p1_b
    width = x_vec.Length
    if width < 1e-4: return None
    x_vec.Unitize()

    y_vec = rg.Vector3d.CrossProduct(z_vec, x_vec)
    if y_vec.Length < 1e-4: return None
    y_vec.Unitize()

    base_plane = rg.Plane(p1_b, x_vec, y_vec)
    return base_plane, width, height


def get_second_vertical_curve():
    go2 = Rhino.Input.Custom.GetObject()
    go2.SetCommandPrompt("두 번째 수직 모서리를 선택하세요.")
    go2.GeometryFilter = Rhino.DocObjects.ObjectType.Curve | Rhino.DocObjects.ObjectType.EdgeFilter
    go2.SubObjectSelect = True
    go2.EnablePreSelect(False, True)

    rc = go2.Get()
    if rc != Rhino.Input.GetResult.Object: return None
    return get_curve_from_objref(go2.Object(0))


def bake_swing_door(dlg, door_id):
    frames = []
    panels = []
    glasses = []
    hardwares = []

    for name, brep in dlg.GenerateGeometry():
        if name == "frame": frames.append(brep)
        elif name == "panel": panels.append(brep)
        elif name == "glass": glasses.append(brep)
        elif name == "hardware": hardwares.append(brep)

    final_objs = []

    layer_frame = "Door_frame"
    layer_glass = "Door_glass"
    layer_hw = "Door_hardware"

    if not rs.IsLayer(layer_frame): rs.AddLayer(layer_frame, System.Drawing.Color.Indigo)
    if not rs.IsLayer(layer_glass): rs.AddLayer(layer_glass, System.Drawing.Color.LightSkyBlue)
    if not rs.IsLayer(layer_hw): rs.AddLayer(layer_hw, System.Drawing.Color.DarkGray)

    settings = dlg.GetCurrentSettings()

    if frames:
        union_frames = rg.Brep.CreateBooleanUnion(frames, Rhino.RhinoDoc.ActiveDoc.ModelAbsoluteTolerance)
        if union_frames:
            for b in union_frames:
                obj_id = Rhino.RhinoDoc.ActiveDoc.Objects.AddBrep(b)
                if obj_id:
                    rs.ObjectLayer(obj_id, layer_frame)
                    save_swing_metadata(obj_id, door_id, "frame", dlg.base_plane, dlg.width, dlg.height, settings)
                    final_objs.append(obj_id)
        else:
            for b in frames:
                obj_id = Rhino.RhinoDoc.ActiveDoc.Objects.AddBrep(b)
                if obj_id:
                    rs.ObjectLayer(obj_id, layer_frame)
                    save_swing_metadata(obj_id, door_id, "frame", dlg.base_plane, dlg.width, dlg.height, settings)
                    final_objs.append(obj_id)

    for p in panels:
        obj_id = Rhino.RhinoDoc.ActiveDoc.Objects.AddBrep(p)
        if obj_id:
            rs.ObjectLayer(obj_id, layer_frame)
            save_swing_metadata(obj_id, door_id, "panel", dlg.base_plane, dlg.width, dlg.height, settings)
            final_objs.append(obj_id)

    for g in glasses:
        obj_id = Rhino.RhinoDoc.ActiveDoc.Objects.AddBrep(g)
        if obj_id:
            rs.ObjectLayer(obj_id, layer_glass)
            save_swing_metadata(obj_id, door_id, "glass", dlg.base_plane, dlg.width, dlg.height, settings)
            final_objs.append(obj_id)

    for hw in hardwares:
        obj_id = Rhino.RhinoDoc.ActiveDoc.Objects.AddBrep(hw)
        if obj_id:
            rs.ObjectLayer(obj_id, layer_hw)
            save_swing_metadata(obj_id, door_id, "hardware", dlg.base_plane, dlg.width, dlg.height, settings)
            final_objs.append(obj_id)

    if final_objs:
        group_name = rs.AddGroup()
        rs.AddObjectsToGroup(final_objs, group_name)

    return final_objs


def get_3pt_rectangle_custom():
    gp1 = Rhino.Input.Custom.GetPoint()
    gp1.SetCommandPrompt("첫 번째 코너를 지정하세요 (시작점)")
    if gp1.Get() != Rhino.Input.GetResult.Point: return None
    p1 = gp1.Point()
    
    gp2 = Rhino.Input.Custom.GetPoint()
    gp2.SetCommandPrompt("두 번째 코너를 지정하세요 (문 폭 및 방향)")
    gp2.SetBasePoint(p1, True)
    gp2.DrawLineFromPoint(p1, True)
    if gp2.Get() != Rhino.Input.GetResult.Point: return None
    p2 = gp2.Point()
    
    x_vec = p2 - p1
    width = x_vec.Length
    if width < 1e-4: return None
    
    x_dir = rg.Vector3d(x_vec)
    x_dir.Unitize()
    
    def OnDynamicDraw(sender, e):
        cur_pt = e.CurrentPoint
        v = cur_pt - p1
        dot = v.X * x_dir.X + v.Y * x_dir.Y + v.Z * x_dir.Z
        z_vec = v - (x_dir * dot)
        p3 = p2 + z_vec
        p4 = p1 + z_vec
        e.Display.DrawPolyline([p1, p2, p3, p4, p1], System.Drawing.Color.Black, 2)
        
    gp3 = Rhino.Input.Custom.GetPoint()
    gp3.SetCommandPrompt("세 번째 코너를 지정하세요 (문 높이)")
    gp3.SetBasePoint(p1, True)
    gp3.DynamicDraw += OnDynamicDraw
    if gp3.Get() != Rhino.Input.GetResult.Point: return None
    cur_pt = gp3.Point()
    
    v = cur_pt - p1
    dot = v.X * x_dir.X + v.Y * x_dir.Y + v.Z * x_dir.Z
    z_vec = v - (x_dir * dot)
    height = z_vec.Length
    
    if height < 1e-4: return None
    
    z_dir = rg.Vector3d(z_vec)
    z_dir.Unitize()
    y_dir = rg.Vector3d.CrossProduct(z_dir, x_dir)
    y_dir.Unitize()
    
    base_plane = rg.Plane(p1, x_dir, y_dir)
    return base_plane, width, height

def get_input_context():
    while True:
        go = Rhino.Input.Custom.GetObject()
        go.SetCommandPrompt("수정할 여닫이문 객체 또는 신규 생성을 위한 수직 모서리를 선택하세요.")
        go.GeometryFilter = Rhino.DocObjects.ObjectType.AnyObject | Rhino.DocObjects.ObjectType.EdgeFilter
        go.SubObjectSelect = True
        go.EnablePreSelect(False, True)

        opt_rect_idx = go.AddOption("Rectangle")
        get_rc = go.GetMultiple(1, 2)

        if get_rc == Rhino.Input.GetResult.Cancel:
            return None

        if get_rc == Rhino.Input.GetResult.Option:
            if go.Option().Index == opt_rect_idx:
                result = get_3pt_rectangle_custom()
                if result:
                    base_plane, width, height = result
                    return {
                        "mode": "new",
                        "door_id": None,
                        "base_plane": base_plane,
                        "width": width,
                        "height": height,
                        "settings": None
                    }
                else:
                    return None

        elif get_rc == Rhino.Input.GetResult.Object:
            # 1개든 2개든, 선택 객체 중 수정 가능한 여닫이문 데이터가 있으면 수정 모드 우선
            for i in range(go.ObjectCount):
                data = load_swing_data_from_objref(go.Object(i))
                if data:
                    return data

            # 수정 객체가 아니면 신규 생성용 수직 모서리로 해석
            if go.ObjectCount == 2:
                crv1 = get_curve_from_objref(go.Object(0))
                crv2 = get_curve_from_objref(go.Object(1))
                result = process_two_curves(crv1, crv2)
                if result:
                    base_plane, width, height = result
                    return {
                        "mode": "new",
                        "door_id": None,
                        "base_plane": base_plane,
                        "width": width,
                        "height": height,
                        "settings": None
                    }

            elif go.ObjectCount == 1:
                crv1 = get_curve_from_objref(go.Object(0))
                if crv1:
                    crv2 = get_second_vertical_curve()
                    result = process_two_curves(crv1, crv2)
                    if result:
                        base_plane, width, height = result
                        return {
                            "mode": "new",
                            "door_id": None,
                            "base_plane": base_plane,
                            "width": width,
                            "height": height,
                            "settings": None
                        }
                    else:
                        return None

            rs.MessageBox(
                "선택한 객체는 수정 가능한 여닫이문이 아닙니다.\n\n"
                "수정하려면 이 스크립트로 생성된 여닫이문 객체를 선택하세요.\n"
                "새로 만들려면 두 개의 수직 모서리 또는 Rectangle 옵션을 사용하세요.",
                0,
                "선택 오류"
            )
            rs.UnselectAllObjects()
            go.ClearObjects()
            continue


def main():
    input_data = get_input_context()
    if not input_data: return

    base_plane = input_data["base_plane"]
    width = input_data["width"]
    height = input_data["height"]
    edit_mode = (input_data["mode"] == "edit")
    initial_settings = input_data["settings"]
    door_id = input_data["door_id"]
    edit_object_ids = input_data.get("edit_object_ids", []) if input_data else []

    if base_plane is None or width <= 0 or height <= 0:
        return

    dlg = SwingDoorDialog(base_plane, width, height, initial_settings, edit_mode)
    dialog_result = False
    try:
        dialog_result = Rhino.UI.EtoExtensions.ShowSemiModal(dlg, Rhino.RhinoDoc.ActiveDoc, Rhino.UI.RhinoEtoApp.MainWindow)
    finally:
        try:
            dlg.ClosePreview()
        except:
            pass

    if dialog_result:
        rs.EnableRedraw(False)
        try:
            if edit_mode and door_id:
                old_ids = edit_object_ids if edit_object_ids else []
                if not old_ids:
                    old_ids = get_swing_object_ids(door_id)
                if old_ids:
                    delete_swing_object_ids(old_ids)
                # 복사본과 원본이 같은 Door ID를 공유하지 않도록 수정 후에는 새 ID를 부여합니다.
                door_id = System.Guid.NewGuid().ToString()
            else:
                door_id = System.Guid.NewGuid().ToString()

            bake_swing_door(dlg, door_id)
        finally:
            rs.EnableRedraw(True)
            Rhino.RhinoDoc.ActiveDoc.Views.Redraw()

if __name__ == "__main__":
    main()