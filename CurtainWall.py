# -*- coding: utf-8 -*-
import Rhino
import Rhino.Geometry as rg
import Rhino.Display as rd
import Eto.Forms as forms
import Eto.Drawing as drawing
import rhinoscriptsyntax as rs
import scriptcontext as sc
import System
import math
import os
import json

# ==============================================================================
# Editable CurtainWall metadata keys
# ==============================================================================
META_TOOL = "CW_Tool"
META_TOOL_VALUE = "EditableCurtainWall"
META_ID = "CW_Id"
META_ROLE = "CW_Role"
META_BASE_CURVE_ID = "CW_BaseCurveId"
META_BASE_CURVE_POINTS = "CW_BaseCurvePoints"

SETTING_KEYS = [
    "cw_height",
    "cw_v_space",
    "cw_h_space",
    "cw_floors",
    "cw_flip",
    "cw_m_thick",
    "cw_m_depth",
    "cw_m_extrude",
    "cw_t_thick",
    "cw_t_depth",
    "cw_t_extrude"
]

DEFAULT_SETTINGS = {
    "cw_height": "4000",
    "cw_v_space": "1000",
    "cw_h_space": "1000, 3000",
    "cw_floors": "1",
    "cw_flip": False,
    "cw_m_thick": "50",
    "cw_m_depth": "150",
    "cw_m_extrude": "100",
    "cw_t_thick": "50",
    "cw_t_depth": "100",
    "cw_t_extrude": "0"
}

# ==============================================================================
# [0] Common utility / metadata / preset functions
# ==============================================================================
def safe_bool(value, default=False):
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    s = str(value).strip().lower()
    return s in ["true", "1", "yes", "y", "on"]


def safe_float(value, default):
    try:
        if value is None:
            return default
        return float(value)
    except:
        return default


def safe_int(value, default):
    try:
        if value is None:
            return default
        return int(float(value))
    except:
        return default


def ensure_layer(layer_name, color):
    if not rs.IsLayer(layer_name):
        rs.AddLayer(layer_name, color)


def ensure_custom_layer(name, color):
    doc = Rhino.RhinoDoc.ActiveDoc
    idx = doc.Layers.Find(name, True)
    if idx < 0:
        layer = Rhino.DocObjects.Layer()
        layer.Name = name
        layer.Color = color
        idx = doc.Layers.Add(layer)
    return idx


def set_object_user_data(obj_id, data):
    if not obj_id or obj_id == System.Guid.Empty:
        return
    rh_obj = sc.doc.Objects.Find(obj_id)
    if not rh_obj:
        return
    for k, v in data.items():
        try:
            rh_obj.Attributes.SetUserString(k, str(v))
        except:
            pass
    rh_obj.CommitChanges()


def get_object_user_data(rh_obj, key, default=None):
    if not rh_obj:
        return default
    try:
        value = rh_obj.Attributes.GetUserString(key)
        if value is None or value == "":
            return default
        return value
    except:
        return default


def curve_to_points_string(curve):
    """Fallback storage for the base curve. The hidden base curve object is primary."""
    if not curve:
        return ""
    pts = []
    try:
        length = curve.GetLength()
        div_count = int(math.ceil(length / 250.0))
        if div_count < 8:
            div_count = 8
        if div_count > 300:
            div_count = 300
        params = curve.DivideByCount(div_count, True)
        if params:
            for t in params:
                pts.append(curve.PointAt(t))
    except:
        pass
    if not pts:
        try:
            pts = [curve.PointAtStart, curve.PointAtEnd]
        except:
            pts = []

    chunks = []
    for p in pts:
        chunks.append("{0:.6f},{1:.6f},{2:.6f}".format(p.X, p.Y, p.Z))
    return ";".join(chunks)


def points_string_to_curve(text):
    if not text:
        return None
    pts = []
    try:
        for chunk in text.split(";"):
            vals = chunk.split(",")
            if len(vals) != 3:
                continue
            pts.append(rg.Point3d(float(vals[0]), float(vals[1]), float(vals[2])))
    except:
        return None
    if len(pts) < 2:
        return None
    try:
        polyline = rg.Polyline(pts)
        return polyline.ToNurbsCurve()
    except:
        return None


def find_base_curve_by_id(base_curve_id):
    if not base_curve_id:
        return None
    try:
        guid = System.Guid(str(base_curve_id))
        rh_obj = sc.doc.Objects.Find(guid)
        if rh_obj and rh_obj.Geometry:
            geom = rh_obj.Geometry
            if isinstance(geom, rg.Curve):
                return geom.DuplicateCurve()
            try:
                return geom.DuplicateCurve()
            except:
                return None
    except:
        return None
    return None


def _build_metadata(curtain_id, role, base_curve_id, base_curve_points, settings):
    data = {
        META_TOOL: META_TOOL_VALUE,
        META_ID: curtain_id,
        META_ROLE: role,
        META_BASE_CURVE_ID: base_curve_id,
        META_BASE_CURVE_POINTS: base_curve_points
    }
    for key in SETTING_KEYS:
        data[key] = settings.get(key, DEFAULT_SETTINGS.get(key, ""))
    return data


def create_or_update_base_curve_object(base_curve, curtain_id, existing_base_curve_id, sample_points, settings):
    """Create a hidden helper curve used for later editing. Reuse it in edit mode if possible."""
    if existing_base_curve_id:
        existing_curve = find_base_curve_by_id(existing_base_curve_id)
        if existing_curve:
            rh_obj = sc.doc.Objects.Find(System.Guid(str(existing_base_curve_id)))
            if rh_obj:
                set_object_user_data(
                    rh_obj.Id,
                    _build_metadata(curtain_id, "base_curve", existing_base_curve_id, sample_points, settings)
                )
            return existing_base_curve_id

    ensure_layer("CurtainWall_BaseCrv", System.Drawing.Color.DarkGray)
    obj_id = sc.doc.Objects.AddCurve(base_curve)
    if obj_id and obj_id != System.Guid.Empty:
        try:
            rs.ObjectLayer(obj_id, "CurtainWall_BaseCrv")
        except:
            pass
        set_object_user_data(
            obj_id,
            _build_metadata(curtain_id, "base_curve", str(obj_id), sample_points, settings)
        )
        try:
            rs.HideObject(obj_id)
        except:
            pass
        return str(obj_id)
    return ""


def collect_curtainwall_object_ids(curtain_id):
    """Collect generated objects sharing one CurtainWall id. Hidden base curve is returned separately."""
    generated_ids = []
    base_curve_id = ""
    try:
        enum_settings = Rhino.DocObjects.ObjectEnumeratorSettings()
        enum_settings.NormalObjects = True
        enum_settings.HiddenObjects = True
        enum_settings.LockedObjects = True
        enum_settings.DeletedObjects = False
        all_objects = sc.doc.Objects.GetObjectList(enum_settings)
    except:
        all_objects = sc.doc.Objects

    for rh_obj in all_objects:
        try:
            tool = get_object_user_data(rh_obj, META_TOOL, "")
            if tool != META_TOOL_VALUE:
                continue
            cid = get_object_user_data(rh_obj, META_ID, "")
            if cid != curtain_id:
                continue
            role = get_object_user_data(rh_obj, META_ROLE, "")
            if role == "base_curve":
                base_curve_id = str(rh_obj.Id)
            else:
                generated_ids.append(rh_obj.Id)
        except:
            pass
    return generated_ids, base_curve_id


def delete_objects_safe(object_ids):
    if not object_ids:
        return
    for oid in object_ids:
        try:
            sc.doc.Objects.Delete(oid, True)
        except:
            try:
                rs.DeleteObject(oid)
            except:
                pass


def settings_from_object(rh_obj):
    if not rh_obj:
        return None
    if get_object_user_data(rh_obj, META_TOOL, "") != META_TOOL_VALUE:
        return None
    curtain_id = get_object_user_data(rh_obj, META_ID, "")
    if not curtain_id:
        return None

    settings = {}
    for key in SETTING_KEYS:
        settings[key] = get_object_user_data(rh_obj, key, DEFAULT_SETTINGS.get(key, ""))

    settings[META_ID] = curtain_id
    settings[META_BASE_CURVE_ID] = get_object_user_data(rh_obj, META_BASE_CURVE_ID, "")
    settings[META_BASE_CURVE_POINTS] = get_object_user_data(rh_obj, META_BASE_CURVE_POINTS, "")
    return settings


def get_preset_file_path():
    appdata = os.environ.get("APPDATA")
    if appdata:
        root = os.path.join(appdata, "ElephantTools")
    else:
        root = os.path.join(os.path.expanduser("~"), "ElephantTools")
    if not os.path.isdir(root):
        try:
            os.makedirs(root)
        except:
            pass
    return os.path.join(root, "CurtainWallPresets.json")


def load_presets():
    path = get_preset_file_path()
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r") as f:
            data = json.load(f)
        if isinstance(data, dict):
            return data
    except:
        pass
    return {}


def save_presets(presets):
    path = get_preset_file_path()
    try:
        with open(path, "w") as f:
            json.dump(presets, f, indent=2, sort_keys=True)
        return True
    except Exception as ex:
        print("프리셋 저장 오류:", ex)
        return False

# ==============================================================================
# [1. 통합 미리보기 엔진]
# ==============================================================================
class CurtainWallConduit(rd.DisplayConduit):
    def __init__(self):
        rd.DisplayConduit.__init__(self)
        self.preview_frames = []
        self.preview_glass = None
        self.arrow_brep = None
        self.frame_mat = rd.DisplayMaterial(System.Drawing.Color.Indigo)
        self.glass_mat = rd.DisplayMaterial(System.Drawing.Color.LightSkyBlue)
        self.glass_mat.Transparency = 0.6
        self.glass_mat.Emission = System.Drawing.Color.LightCyan
        self.arrow_mat = rd.DisplayMaterial(System.Drawing.Color.Red)
        self.arrow_mat.Transparency = 0.2

    def DrawForeground(self, e):
        for brep in self.preview_frames:
            if brep and brep.IsValid:
                e.Display.DrawBrepShaded(brep, self.frame_mat)
                e.Display.DrawBrepWires(brep, System.Drawing.Color.Black, 1)
        if self.preview_glass and self.preview_glass.IsValid:
            e.Display.DrawBrepShaded(self.preview_glass, self.glass_mat)
        if self.arrow_brep and self.arrow_brep.IsValid:
            e.Display.DrawBrepShaded(self.arrow_brep, self.arrow_mat)
            e.Display.DrawBrepWires(self.arrow_brep, System.Drawing.Color.Maroon, 3)

# ==============================================================================
# [2. 커튼월 세부 설정 창]
# ==============================================================================
class CurtainWallDialog(forms.Dialog[bool]):
    def __init__(self, base_curve, initial_settings=None, edit_mode=False):
        self.edit_mode = edit_mode
        self.Title = "커튼월 수정기" if edit_mode else "커튼월 생성기"
        self.Padding = drawing.Padding(20)
        self.Resizable = True
        self.Topmost = True
        self.base_curve = base_curve
        self.conduit = CurtainWallConduit()
        self.conduit.Enabled = True
        self._closed_preview = False

        self.presets = load_presets()
        self._preset_names = []

        self.initial_settings = initial_settings if initial_settings else None
        settings = self._initial_or_sticky_settings()

        self.txt_height = forms.TextBox(Text=str(settings.get("cw_height", DEFAULT_SETTINGS["cw_height"])))
        self.txt_v_space = forms.TextBox(Text=str(settings.get("cw_v_space", DEFAULT_SETTINGS["cw_v_space"])))
        self.txt_v_space.Width = 50
        self.btn_apply_v = forms.Button(Text="확인")
        self.btn_apply_v.Width = 30
        self.txt_h_space = forms.TextBox(Text=str(settings.get("cw_h_space", DEFAULT_SETTINGS["cw_h_space"])))
        self.txt_floors = forms.TextBox(Text=str(settings.get("cw_floors", DEFAULT_SETTINGS["cw_floors"])))
        self.txt_floors.Width = 100
        self.cb_flip = forms.CheckBox(Text="방향 뒤집기 (Flip)")
        self.cb_flip.Checked = safe_bool(settings.get("cw_flip", DEFAULT_SETTINGS["cw_flip"]), False)

        self.m_thick = forms.TextBox(Text=str(settings.get("cw_m_thick", DEFAULT_SETTINGS["cw_m_thick"])))
        self.m_depth = forms.TextBox(Text=str(settings.get("cw_m_depth", DEFAULT_SETTINGS["cw_m_depth"])))
        self.m_extrude = forms.TextBox(Text=str(settings.get("cw_m_extrude", DEFAULT_SETTINGS["cw_m_extrude"])))

        self.t_thick = forms.TextBox(Text=str(settings.get("cw_t_thick", DEFAULT_SETTINGS["cw_t_thick"])))
        self.t_depth = forms.TextBox(Text=str(settings.get("cw_t_depth", DEFAULT_SETTINGS["cw_t_depth"])))
        self.t_extrude = forms.TextBox(Text=str(settings.get("cw_t_extrude", DEFAULT_SETTINGS["cw_t_extrude"])))

        self.dd_preset = forms.DropDown()
        self.txt_preset_name = forms.TextBox()
        self.txt_preset_name.Width = 150
        self.btn_preset_load = forms.Button(Text="불러오기")
        self.btn_preset_save = forms.Button(Text="저장")
        self.btn_preset_delete = forms.Button(Text="삭제")
        self.RefreshPresetDropdown()

        v_layout = forms.DynamicLayout()
        v_layout.BeginHorizontal()
        v_layout.Add(self.txt_v_space, True, False)
        v_layout.Add(self.btn_apply_v, False, False)
        v_layout.EndHorizontal()

        layout = forms.DynamicLayout()
        layout.Spacing = drawing.Size(6, 6)

        layout.AddRow(forms.Label(Text="[프리셋 설정]", Font=drawing.Font("맑은 고딕", 10, drawing.FontStyle.Bold)))
        layout.AddRow("프리셋 목록:", self.dd_preset, self.btn_preset_load)
        layout.AddRow("프리셋 이름:", self.txt_preset_name, self.btn_preset_save, self.btn_preset_delete)
        layout.AddRow(None)

        layout.AddRow(forms.Label(Text="[기본 설정]", Font=drawing.Font("맑은 고딕", 10, drawing.FontStyle.Bold)))
        layout.AddRow("기준 층 높이:", self.txt_height, "층 수 (Floor):", self.txt_floors)
        layout.AddRow("멀리언 간격:", v_layout, self.cb_flip)
        layout.AddRow("트랜섬 높이 (쉼표 구분):", self.txt_h_space)
        layout.AddRow(None)
        layout.AddRow(forms.Label(Text="[멀리언]", Font=drawing.Font("맑은 고딕", 10, drawing.FontStyle.Bold)))
        layout.AddRow("두께 (Thickness):", self.m_thick)
        layout.AddRow("깊이 (Depth):", self.m_depth, "돌출 (Extrude):", self.m_extrude)
        layout.AddRow(None)
        layout.AddRow(forms.Label(Text="[트랜섬]", Font=drawing.Font("맑은 고딕", 10, drawing.FontStyle.Bold)))
        layout.AddRow("두께 (Thickness):", self.t_thick)
        layout.AddRow("깊이 (Depth):", self.t_depth, "돌출 (Extrude):", self.t_extrude)
        layout.AddRow(None)

        self.btn_ok = forms.Button(Text="수정하기" if edit_mode else "생성하기")
        self.btn_cancel = forms.Button(Text="취소")
        self.btn_ok.Click += self.OnOkClick
        self.btn_cancel.Click += self.OnCancelClick
        layout.AddRow(self.btn_ok, self.btn_cancel)

        self.Content = layout

        self.dd_preset.SelectedIndexChanged += self.OnPresetSelected
        self.btn_preset_load.Click += self.OnPresetLoad
        self.btn_preset_save.Click += self.OnPresetSave
        self.btn_preset_delete.Click += self.OnPresetDelete

        for ctrl in [self.txt_height, self.txt_h_space, self.txt_floors, self.m_thick, self.m_depth, self.m_extrude, self.t_thick, self.t_depth, self.t_extrude]:
            ctrl.TextChanged += lambda s, e: self.Update()
        self.cb_flip.CheckedChanged += lambda s, e: self.Update()
        self.btn_apply_v.Click += lambda s, e: self.Update()
        self.txt_v_space.KeyDown += lambda s, e: self.Update() if e.Key == forms.Keys.Enter else None
        self.Update()

    def _initial_or_sticky_settings(self):
        if self.initial_settings:
            return self.initial_settings
        settings = {}
        for key in SETTING_KEYS:
            if key in sc.sticky:
                settings[key] = sc.sticky[key]
            else:
                settings[key] = DEFAULT_SETTINGS.get(key, "")
        return settings

    def GetCurrentSettings(self):
        return {
            "cw_height": str(self.txt_height.Text),
            "cw_v_space": str(self.txt_v_space.Text),
            "cw_h_space": str(self.txt_h_space.Text),
            "cw_floors": str(self.txt_floors.Text),
            "cw_flip": bool(self.cb_flip.Checked),
            "cw_m_thick": str(self.m_thick.Text),
            "cw_m_depth": str(self.m_depth.Text),
            "cw_m_extrude": str(self.m_extrude.Text),
            "cw_t_thick": str(self.t_thick.Text),
            "cw_t_depth": str(self.t_depth.Text),
            "cw_t_extrude": str(self.t_extrude.Text)
        }

    def ApplySettings(self, settings):
        if not settings:
            return
        self.txt_height.Text = str(settings.get("cw_height", DEFAULT_SETTINGS["cw_height"]))
        self.txt_v_space.Text = str(settings.get("cw_v_space", DEFAULT_SETTINGS["cw_v_space"]))
        self.txt_h_space.Text = str(settings.get("cw_h_space", DEFAULT_SETTINGS["cw_h_space"]))
        self.txt_floors.Text = str(settings.get("cw_floors", DEFAULT_SETTINGS["cw_floors"]))
        self.cb_flip.Checked = safe_bool(settings.get("cw_flip", DEFAULT_SETTINGS["cw_flip"]), False)
        self.m_thick.Text = str(settings.get("cw_m_thick", DEFAULT_SETTINGS["cw_m_thick"]))
        self.m_depth.Text = str(settings.get("cw_m_depth", DEFAULT_SETTINGS["cw_m_depth"]))
        self.m_extrude.Text = str(settings.get("cw_m_extrude", DEFAULT_SETTINGS["cw_m_extrude"]))
        self.t_thick.Text = str(settings.get("cw_t_thick", DEFAULT_SETTINGS["cw_t_thick"]))
        self.t_depth.Text = str(settings.get("cw_t_depth", DEFAULT_SETTINGS["cw_t_depth"]))
        self.t_extrude.Text = str(settings.get("cw_t_extrude", DEFAULT_SETTINGS["cw_t_extrude"]))
        self.Update()

    def SaveSticky(self):
        settings = self.GetCurrentSettings()
        for key, value in settings.items():
            sc.sticky[key] = value
        return settings

    def RefreshPresetDropdown(self):
        self.presets = load_presets()
        self._preset_names = sorted(self.presets.keys())
        self.dd_preset.DataStore = self._preset_names
        if self._preset_names:
            self.dd_preset.SelectedIndex = 0
            self.txt_preset_name.Text = self._preset_names[0]
        else:
            self.dd_preset.SelectedIndex = -1
            self.txt_preset_name.Text = ""

    def _selected_preset_name(self):
        try:
            idx = self.dd_preset.SelectedIndex
            if idx is not None and idx >= 0 and idx < len(self._preset_names):
                return self._preset_names[idx]
        except:
            pass
        return ""

    def OnPresetSelected(self, sender, e):
        name = self._selected_preset_name()
        if name:
            self.txt_preset_name.Text = name

    def OnPresetLoad(self, sender, e):
        name = self._selected_preset_name()
        if not name or name not in self.presets:
            rs.MessageBox("불러올 프리셋을 선택하세요.", 0, "프리셋")
            return
        self.ApplySettings(self.presets.get(name, {}))

    def OnPresetSave(self, sender, e):
        name = str(self.txt_preset_name.Text).strip()
        if not name:
            rs.MessageBox("프리셋 이름을 입력하세요.", 0, "프리셋")
            return
        if name in self.presets:
            rc = rs.MessageBox("같은 이름의 프리셋이 이미 있습니다.\n현재 값으로 덮어쓰시겠습니까?", 4, "프리셋 덮어쓰기")
            if rc != 6:
                return
        self.presets[name] = self.GetCurrentSettings()
        if save_presets(self.presets):
            self.RefreshPresetDropdown()
            try:
                self.dd_preset.SelectedIndex = self._preset_names.index(name)
                self.txt_preset_name.Text = name
            except:
                pass

    def OnPresetDelete(self, sender, e):
        name = self._selected_preset_name()
        if not name:
            name = str(self.txt_preset_name.Text).strip()
        if not name or name not in self.presets:
            rs.MessageBox("삭제할 프리셋을 선택하세요.", 0, "프리셋")
            return
        rc = rs.MessageBox("'{0}' 프리셋을 삭제하시겠습니까?".format(name), 4, "프리셋 삭제")
        if rc != 6:
            return
        try:
            del self.presets[name]
        except:
            pass
        if save_presets(self.presets):
            self.RefreshPresetDropdown()

    def ClosePreview(self):
        if self._closed_preview:
            return
        self._closed_preview = True
        try:
            self.conduit.Enabled = False
            self.conduit.preview_frames = []
            self.conduit.preview_glass = None
            self.conduit.arrow_brep = None
            Rhino.RhinoDoc.ActiveDoc.Views.Redraw()
        except:
            pass

    def OnOkClick(self, sender, e):
        self.SaveSticky()
        self.ClosePreview()
        self.Close(True)

    def OnCancelClick(self, sender, e):
        self.SaveSticky()
        self.ClosePreview()
        self.Close(False)

    def get_float(self, textbox, default_val):
        try:
            return float(textbox.Text)
        except:
            return default_val

    def get_int(self, textbox, default_val):
        try:
            return int(float(textbox.Text))
        except:
            return default_val

    def create_offset_solid(self, base_curve, target_outer, target_inner, dist_outer_mag, dist_inner_mag, height):
        def get_offset(curve, target_pt, dist_mag):
            if abs(dist_mag) < 0.001:
                c = curve.DuplicateCurve()
                if c.PointAtStart.DistanceTo(target_pt) > c.PointAtEnd.DistanceTo(target_pt):
                    c.Reverse()
                return c
            c1_arr = curve.Offset(rg.Plane.WorldXY, dist_mag, 0.01, rg.CurveOffsetCornerStyle.Sharp)
            c2_arr = curve.Offset(rg.Plane.WorldXY, -dist_mag, 0.01, rg.CurveOffsetCornerStyle.Sharp)
            c1 = rg.Curve.JoinCurves(c1_arr)[0] if c1_arr and len(c1_arr) > 0 else None
            c2 = rg.Curve.JoinCurves(c2_arr)[0] if c2_arr and len(c2_arr) > 0 else None

            def dist_to_target(c):
                if not c:
                    return 9999999
                return min(c.PointAtStart.DistanceTo(target_pt), c.PointAtEnd.DistanceTo(target_pt))

            best_c = c1 if dist_to_target(c1) < dist_to_target(c2) else c2
            if not best_c:
                return None
            if best_c.PointAtStart.DistanceTo(target_pt) > best_c.PointAtEnd.DistanceTo(target_pt):
                best_c.Reverse()
            return best_c

        crv_outer = get_offset(base_curve, target_outer, dist_outer_mag)
        crv_inner = get_offset(base_curve, target_inner, dist_inner_mag)
        if not crv_outer or not crv_inner:
            return None

        l1 = rg.LineCurve(crv_outer.PointAtStart, crv_inner.PointAtStart)
        l2 = rg.LineCurve(crv_inner.PointAtEnd, crv_outer.PointAtEnd)

        joined = rg.Curve.JoinCurves([crv_outer, l1, crv_inner, l2])
        if joined and len(joined) > 0:
            base_face = joined[0]
            if base_face.ClosedCurveOrientation(rg.Plane.WorldXY) == rg.CurveOrientation.Clockwise:
                base_face.Reverse()
            solid = rg.Extrusion.Create(base_face, height, True)
            return solid.ToBrep() if solid else None
        return None

    def GenerateGeometry(self):
        H = self.get_float(self.txt_height, 3000.0)
        V_Space = max(100.0, self.get_float(self.txt_v_space, 1200.0))
        floors = max(1, self.get_int(self.txt_floors, 1))

        mT = self.get_float(self.m_thick, 50)
        mD = self.get_float(self.m_depth, 150)
        mE = self.get_float(self.m_extrude, 20)
        tT = self.get_float(self.t_thick, 50)
        tD = self.get_float(self.t_depth, 100)
        tE = self.get_float(self.t_extrude, 0)

        flip_dir = -1.0 if self.cb_flip.Checked else 1.0
        GLASS_THICK = 30.0

        transom_heights = []
        for token in self.txt_h_space.Text.split(','):
            try:
                val = float(token.strip())
                if 0 < val < H:
                    transom_heights.append(val)
            except:
                pass

        divisions = max(1, int(round(self.base_curve.GetLength() / V_Space)))
        params = self.base_curve.DivideByCount(divisions, True)
        params = list(params) if params else [self.base_curve.Domain.Min, self.base_curve.Domain.Max]

        pts = []
        inward_normals = []
        for t in params:
            pt = self.base_curve.PointAt(t)
            tan = self.base_curve.TangentAt(t)
            normal = rg.Vector3d.CrossProduct(tan, rg.Vector3d.ZAxis)
            if normal.Length < 1e-9:
                normal = rg.Vector3d.YAxis
            normal.Unitize()
            inward_normals.append(normal * flip_dir)
            pts.append(pt)

        if not pts:
            return [], None, None

        pt0 = pts[0]
        n0 = inward_normals[0]
        glass_target_outer = pt0
        glass_target_inner = pt0 + (n0 * GLASS_THICK)

        transom_target_outer = pt0 + n0 * (GLASS_THICK - tE)
        transom_target_inner = pt0 + n0 * (GLASS_THICK + tD)

        single_floor_frames = []
        for i in range(len(pts)):
            pt = pts[i]
            n = inward_normals[i]
            base_origin = pt + (n * GLASS_THICK)
            x_axis = rg.Vector3d.CrossProduct(n, rg.Vector3d.ZAxis)
            if x_axis.Length < 1e-9:
                x_axis = rg.Vector3d.XAxis
            x_axis.Unitize()
            m_plane = rg.Plane(base_origin, x_axis, n)
            m_box = rg.Box(m_plane, rg.Interval(-mT / 2.0, mT / 2.0), rg.Interval(-mE, mD), rg.Interval(0, H))
            single_floor_frames.append(m_box.ToBrep())

        t_base_brep = self.create_offset_solid(self.base_curve, transom_target_outer, transom_target_inner, abs(GLASS_THICK - tE), abs(GLASS_THICK + tD), tT)
        if t_base_brep:
            for current_z in transom_heights:
                dup = t_base_brep.DuplicateBrep()
                dup.Translate(rg.Vector3d(0, 0, current_z - tT / 2.0))
                single_floor_frames.append(dup)

        repeated_frames = []
        for f in range(floors):
            xform = rg.Transform.Translation(rg.Vector3d(0, 0, f * H))
            for brep in single_floor_frames:
                if brep:
                    dup = brep.DuplicateBrep()
                    dup.Transform(xform)
                    repeated_frames.append(dup)

        glass_brep = self.create_offset_solid(self.base_curve, glass_target_outer, glass_target_inner, 0.0, GLASS_THICK, H * floors)

        mid_pt = self.base_curve.PointAt(self.base_curve.Domain.Mid)
        mid_tan = self.base_curve.TangentAt(self.base_curve.Domain.Mid)
        mid_normal = rg.Vector3d.CrossProduct(mid_tan, rg.Vector3d.ZAxis) * (-1.0 * flip_dir)
        if mid_normal.Length < 1e-9:
            mid_normal = rg.Vector3d.YAxis
        mid_normal.Unitize()
        right_dir = rg.Vector3d.CrossProduct(mid_normal, rg.Vector3d.ZAxis)
        if right_dir.Length < 1e-9:
            right_dir = rg.Vector3d.XAxis
        right_dir.Unitize()

        base_pt = mid_pt + rg.Vector3d(0, 0, 100)
        neck_pt = base_pt + mid_normal * 3000.0

        arrow_poly = rg.Polyline([
            base_pt - right_dir * 250,
            base_pt + right_dir * 250,
            neck_pt + right_dir * 250,
            neck_pt + right_dir * 600,
            neck_pt + mid_normal * 1039.23,
            neck_pt - right_dir * 600,
            neck_pt - right_dir * 250,
            base_pt - right_dir * 250
        ])
        arrow_breps = rg.Brep.CreatePlanarBreps(rg.PolylineCurve(arrow_poly), 0.01)
        self.arrow_brep = arrow_breps[0] if arrow_breps else None

        return repeated_frames, glass_brep, self.arrow_brep

    def Update(self):
        frames, glass, arrow = self.GenerateGeometry()
        self.conduit.preview_frames = frames
        self.conduit.preview_glass = glass
        self.conduit.arrow_brep = arrow
        Rhino.RhinoDoc.ActiveDoc.Views.Redraw()

    def OnClosing(self, e):
        self.ClosePreview()
        super(CurtainWallDialog, self).OnClosing(e)


def bake_or_update_curtainwall(dlg, edit_context=None):
    edit_context = edit_context if edit_context else {}
    is_edit = bool(edit_context.get("curtain_id"))
    curtain_id = edit_context.get("curtain_id") if is_edit else str(System.Guid.NewGuid())
    old_object_ids = edit_context.get("object_ids", []) if is_edit else []
    existing_base_curve_id = edit_context.get("base_curve_id", "") if is_edit else ""

    settings = dlg.GetCurrentSettings()
    base_curve_points = curve_to_points_string(dlg.base_curve)
    base_curve_id = create_or_update_base_curve_object(
        dlg.base_curve,
        curtain_id,
        existing_base_curve_id,
        base_curve_points,
        settings
    )

    frames, glass, _ = dlg.GenerateGeometry()
    final_objs = []
    frame_idx = ensure_custom_layer("Door_Frame", System.Drawing.Color.DarkGray)
    glass_idx = ensure_custom_layer("Door_Glass", System.Drawing.Color.LightSkyBlue)

    rs.EnableRedraw(False)
    try:
        if is_edit and old_object_ids:
            delete_objects_safe(old_object_ids)

        if frames:
            union = rg.Brep.CreateBooleanUnion(frames, Rhino.RhinoDoc.ActiveDoc.ModelAbsoluteTolerance)
            frame_breps = union if union else frames
            for b in frame_breps:
                if not b or not b.IsValid:
                    continue
                attr = Rhino.DocObjects.ObjectAttributes()
                attr.LayerIndex = frame_idx
                obj_id = Rhino.RhinoDoc.ActiveDoc.Objects.AddBrep(b, attr)
                if obj_id and obj_id != System.Guid.Empty:
                    set_object_user_data(obj_id, _build_metadata(curtain_id, "frame", base_curve_id, base_curve_points, settings))
                    final_objs.append(obj_id)

        if glass and glass.IsValid:
            attr = Rhino.DocObjects.ObjectAttributes()
            attr.LayerIndex = glass_idx
            obj_id = Rhino.RhinoDoc.ActiveDoc.Objects.AddBrep(glass, attr)
            if obj_id and obj_id != System.Guid.Empty:
                set_object_user_data(obj_id, _build_metadata(curtain_id, "glass", base_curve_id, base_curve_points, settings))
                final_objs.append(obj_id)

        if final_objs:
            group_name = rs.AddGroup()
            rs.AddObjectsToGroup(final_objs, group_name)
            rs.UnselectAllObjects()
            rs.SelectObjects(final_objs)

    finally:
        rs.EnableRedraw(True)
        Rhino.RhinoDoc.ActiveDoc.Views.Redraw()

    return final_objs


def get_curtainwall_target_from_user():
    while True:
        go = Rhino.Input.Custom.GetObject()
        go.SetCommandPrompt("수정할 커튼월 객체 또는 새 베이스 커브/모서리 선택")
        go.GeometryFilter = Rhino.DocObjects.ObjectType.AnyObject
        go.SubObjectSelect = True
        try:
            go.EnablePreSelect(False, True)
        except:
            pass
        try:
            go.GroupSelect = False
        except:
            pass

        get_rc = go.Get()
        if get_rc == Rhino.Input.GetResult.Cancel:
            return None
        if get_rc != Rhino.Input.GetResult.Object:
            return None

        obj_ref = go.Object(0)
        rh_obj = None
        try:
            rh_obj = obj_ref.Object()
        except:
            rh_obj = None

        edit_settings = settings_from_object(rh_obj)
        if edit_settings:
            curtain_id = edit_settings.get(META_ID, "")
            object_ids, found_base_curve_id = collect_curtainwall_object_ids(curtain_id)
            base_curve_id = edit_settings.get(META_BASE_CURVE_ID, "") or found_base_curve_id
            base_curve = find_base_curve_by_id(base_curve_id)

            if base_curve is None:
                base_curve = points_string_to_curve(edit_settings.get(META_BASE_CURVE_POINTS, ""))
                if base_curve is None:
                    rs.MessageBox("저장된 기준 커브를 찾을 수 없습니다. 이 커튼월은 수정할 수 없습니다.", 0, "수정 오류")
                    return None

            return {
                "mode": "edit",
                "base_curve": base_curve,
                "settings": edit_settings,
                "curtain_id": curtain_id,
                "object_ids": object_ids,
                "base_curve_id": base_curve_id
            }

        crv = None
        try:
            crv = obj_ref.Curve()
        except:
            crv = None
        if crv:
            return {"mode": "new", "base_curve": crv.DuplicateCurve()}

        rs.MessageBox("선택한 객체는 편집 가능한 커튼월도 아니고 기준 커브도 아닙니다.", 0, "선택 오류")
        try:
            rs.UnselectAllObjects()
            go.ClearObjects()
        except:
            pass


def main():
    target = get_curtainwall_target_from_user()
    if not target:
        return

    if target.get("mode") == "edit":
        dlg = CurtainWallDialog(target.get("base_curve"), target.get("settings"), True)
        rc = Rhino.UI.EtoExtensions.ShowSemiModal(dlg, Rhino.RhinoDoc.ActiveDoc, Rhino.UI.RhinoEtoApp.MainWindow)
        dlg.ClosePreview()
        if rc:
            bake_or_update_curtainwall(dlg, {
                "curtain_id": target.get("curtain_id"),
                "object_ids": target.get("object_ids", []),
                "base_curve_id": target.get("base_curve_id", "")
            })
        return

    if target.get("mode") == "new":
        dlg = CurtainWallDialog(target.get("base_curve"), None, False)
        rc = Rhino.UI.EtoExtensions.ShowSemiModal(dlg, Rhino.RhinoDoc.ActiveDoc, Rhino.UI.RhinoEtoApp.MainWindow)
        dlg.ClosePreview()
        if rc:
            bake_or_update_curtainwall(dlg, None)


if __name__ == "__main__":
    main()
