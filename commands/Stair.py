# -*- coding: utf-8 -*-
import os
import sys

import Rhino
import Rhino.Geometry as rg
import Rhino.Display as rd
import Rhino.UI
import Rhino.Input.Custom as ric
import Rhino.DocObjects as rdo
import Eto.Forms as forms
import Eto.Drawing as drawing
import rhinoscriptsyntax as rs
import System

SCRIPT_PATH = globals().get("__file__")
COMMANDS_DIR = (
    os.path.dirname(os.path.realpath(SCRIPT_PATH))
    if SCRIPT_PATH
    else None
)
if COMMANDS_DIR and COMMANDS_DIR not in sys.path:
    sys.path.insert(0, COMMANDS_DIR)


MIN_STEP_COUNT = 1
MAX_STEP_COUNT = 100

CALC_BY_TREADS = 0
CALC_BY_TREADS_PLUS_ONE = 1


def parse_step_count(value):
    """Return a validated integer tread count from the dialog TextBox."""
    text = u"{0}".format(value).strip()
    try:
        step_count = int(text)
    except Exception:
        raise ValueError(u"계단 단수는 정수로 입력해야 합니다.")

    if step_count < MIN_STEP_COUNT or step_count > MAX_STEP_COUNT:
        raise ValueError(
            u"계단 단수는 {0}~{1} 사이로 입력해야 합니다.".format(
                MIN_STEP_COUNT,
                MAX_STEP_COUNT,
            )
        )
    return step_count


def calculate_landing_count(vertical_height, horizontal_length):
    """Return an automatic landing count and whether run length blocked it."""
    candidate_count = int(vertical_height // 3000.0)
    if candidate_count > 0 and horizontal_length <= candidate_count * 1200.0:
        return 0, True
    return candidate_count, False


def calculate_stair_layout(step_count, flight_count, calc_mode, per_flight):
    """Calculate flight tread counts and risers from the active input mode."""
    if flight_count < 1:
        raise ValueError(u"계단 구간 수는 1 이상이어야 합니다.")
    if not per_flight and flight_count != 1:
        raise ValueError(u"전체 단수 입력은 계단참이 없는 경우에만 사용할 수 있습니다.")
    if calc_mode not in (CALC_BY_TREADS, CALC_BY_TREADS_PLUS_ONE):
        calc_mode = CALC_BY_TREADS

    if per_flight:
        flight_counts = [step_count for unused_index in range(flight_count)]
    else:
        flight_counts = [step_count]
    total_steps = sum(flight_counts)
    top_offset_count = 1 if calc_mode == CALC_BY_TREADS_PLUS_ONE else 0
    riser_count = total_steps + top_offset_count
    return total_steps, flight_counts, riser_count, top_offset_count


def calculate_riser_metrics(vertical_height, riser_count, top_offset_count):
    """Return one riser height and the highest-tread offset from the top."""
    riser_height = vertical_height / float(riser_count)
    return riser_height, riser_height * top_offset_count


def calculate_top_offset_transform(
    start_x,
    start_y,
    end_x,
    end_y,
    start_offset,
    end_offset,
):
    """Return affine Z coefficients that match different endpoint offsets."""
    width_x = end_x - start_x
    width_y = end_y - start_y
    width_squared = (width_x * width_x) + (width_y * width_y)
    if width_squared < 0.000001:
        raise ValueError(
            u"상부 기준선 폭이 너무 작아 좌우 단높이 차이를 적용할 수 없습니다."
        )

    offset_delta = end_offset - start_offset
    m20 = -(offset_delta * width_x / width_squared)
    m21 = -(offset_delta * width_y / width_squared)
    m23 = -start_offset - (m20 * start_x) - (m21 * start_y)
    return m20, m21, m23


def run_stair_module(module_name, entry_point):
    """Load a stair tool only when its command-line option is selected."""
    try:
        module = __import__(module_name)
        runner = getattr(module, entry_point)
        return runner()
    except Exception as error:
        message = u"{0} 실행 중 오류가 발생했습니다.\n{1}".format(
            module_name,
            error,
        )
        Rhino.RhinoApp.WriteLine(message.replace("\n", " | "))
        rs.MessageBox(message, 16, u"계단 도구 실행 오류")
        return Rhino.Commands.Result.Failure


# ==============================================================================
# [프리뷰 전용] 3D 솔리드 및 난간 가이드 실시간 표시 Conduit
# ==============================================================================
class StairPreviewConduit(rd.DisplayConduit):
    def __init__(self):
        super(StairPreviewConduit, self).__init__()
        self.breps = []
        self.meshes = []
        self.railing_lines = [] 
        self.material = rd.DisplayMaterial()
        self.material.Diffuse = System.Drawing.Color.LightSkyBlue 
        self.material.Transparency = 0.3

    def DrawShaded(self, e):
        for mesh in self.meshes:
            e.Display.DrawMeshShaded(mesh, self.material)

    def DrawForeground(self, e):
        for brep in self.breps:
            e.Display.DrawBrepWires(brep, System.Drawing.Color.DarkBlue, 2)
        for crv in self.railing_lines:
            if crv: e.Display.DrawCurve(crv, System.Drawing.Color.Gold, 4)

# ==============================================================================
# [UI 다이얼로그] 메인 계단 생성 팝업
# ==============================================================================
class StairGeneratorDialog(forms.Form):
    def __init__(self):
        super(StairGeneratorDialog, self).__init__()
        self.Title = "계단 생성기 옵션"
        self.Padding = drawing.Padding(15)
        self.Resizable = False
        self.Topmost = True 
        self.Owner = Rhino.UI.RhinoEtoApp.MainWindow
        self.ClientSize = drawing.Size(520, 360)

    def SetupData(self, top_crv, bot_crv, default_n):
        self.top_crv = top_crv
        self.bot_crv = bot_crv
        self.p_top_start = top_crv.PointAtStart
        self.p_bot_start = bot_crv.PointAtStart
        self.p_top_end = top_crv.PointAtEnd
        self.p_bot_end = bot_crv.PointAtEnd

        diff_z = abs(self.p_top_start.Z - self.p_bot_start.Z)
        horizontal_run = rg.Vector3d(
            self.p_bot_start.X - self.p_top_start.X,
            self.p_bot_start.Y - self.p_top_start.Y,
            0,
        ).Length
        landing_count, _length_blocked = calculate_landing_count(
            diff_z,
            horizontal_run,
        )
        flight_height = diff_z / float(landing_count + 1)
        self.non_landing_step_count = default_n
        self.landing_step_count = min(
            MAX_STEP_COUNT,
            max(MIN_STEP_COUNT, int(flight_height // 180.0)),
        )
        self._step_input_uses_per_flight = False
        
        self.conduit = StairPreviewConduit()
        self.conduit.Enabled = True
        self.final_breps = []
        self.guide_s = None
        self.guide_e = None
        self.stair_top_crv = self.top_crv
        self._pending_top_crv = None

        self.cmb_type = forms.ComboBox()
        self.cmb_type.DataStore = ["솔리드 계단 (Solid)", "지그재그 계단 (ZigZag)", "철골 계단 (Steel)"]
        self.cmb_type.SelectedIndex = 0
        self.cmb_type.SelectedIndexChanged += self.OnTypeChanged

        self.lbl_thick = forms.Label(Text=" 디딤판 두께 (mm):")
        self.lbl_thick.Visible = False
        
        self.num_thick = forms.NumericStepper()
        self.num_thick.Value = 150
        self.num_thick.MinValue = 10
        self.num_thick.MaxValue = 1000
        self.num_thick.Visible = False
        self.num_thick.ValueChanged += self.OnOptionChanged

        self.lbl_info = forms.Label()
        self.lbl_info.Font = drawing.Font("Malgun Gothic", 10, drawing.FontStyle.Bold)
        self.lbl_info.Height = 45
        
        self.chk_landing = forms.CheckBox(Text=" 계단참 생성")
        self.chk_landing.Checked = False
        self.chk_landing.CheckedChanged += self.OnLandingChanged

        self.chk_railing = forms.CheckBox(Text=" 난간 기준선 생성")
        self.chk_railing.Checked = True
        self.chk_railing.CheckedChanged += self.OnOptionChanged

        self.step_count_box = forms.TextBox(Text=str(default_n))
        self.step_count_box.Width = 100
        self.step_count_box.KeyDown += self.OnStepCountKeyDown
        self.step_count_box.LostFocus += self.OnStepCountLostFocus
        self.step_count_label = forms.Label(Text="계단 단수:")

        self.calc_list = forms.RadioButtonList()
        self.calc_list.DataStore = [
            u"층고 ÷ 총 단수 (마지막 단 = 상부 바닥)",
            u"층고 ÷ (총 단수 + 1) (마지막 단 = 상부 바닥보다 한 단 낮음)",
        ]
        self.calc_list.Orientation = forms.Orientation.Vertical
        self.calc_list.Spacing = drawing.Size(4, 4)
        self.calc_list.SelectedIndex = CALC_BY_TREADS
        self.calc_list.SelectedIndexChanged += self.OnCalculationModeChanged
        
        self.btn_ok = forms.Button(Text="생성")
        self.btn_ok.Click += self.OnOk
        
        self.btn_cancel = forms.Button(Text="취소")
        self.btn_cancel.Click += self.OnCancel

        layout = forms.DynamicLayout()
        layout.Spacing = drawing.Size(10, 10)
        layout.AddRow(forms.Label(Text="계단 타입:"), self.cmb_type)
        layout.AddRow(self.lbl_thick, self.num_thick)
        layout.AddRow(self.chk_landing, self.chk_railing)
        layout.AddRow(self.step_count_label, self.step_count_box)
        layout.AddRow(forms.Label(Text="단 높이 계산 방식:"))
        layout.AddRow(self.calc_list)
        layout.AddRow(self.lbl_info)
        layout.AddRow(None) 
        
        btn_layout = forms.DynamicLayout()
        btn_layout.BeginHorizontal()
        btn_layout.Add(None, True) 
        btn_layout.Add(self.btn_ok)
        btn_layout.Add(self.btn_cancel)
        btn_layout.EndHorizontal()
        
        layout.AddRow(btn_layout)
        self.Content = layout

        self.KeyDown += self.OnKeyDown

        self.UpdatePreview()

    @staticmethod
    def DisposeGeometry(geometry):
        if geometry is None:
            return
        try:
            geometry.Dispose()
        except Exception:
            pass

    def DisposeCurrentPreview(self):
        if hasattr(self, "conduit"):
            for mesh in self.conduit.meshes:
                self.DisposeGeometry(mesh)
            self.conduit.meshes = []
            self.conduit.breps = []
            self.conduit.railing_lines = []

        for brep in getattr(self, "final_breps", []):
            self.DisposeGeometry(brep)
        self.final_breps = []

        self.DisposeGeometry(getattr(self, "guide_s", None))
        self.DisposeGeometry(getattr(self, "guide_e", None))
        self.guide_s = None
        self.guide_e = None

        stair_top_crv = getattr(self, "stair_top_crv", None)
        if stair_top_crv is not None and stair_top_crv is not self.top_crv:
            self.DisposeGeometry(stair_top_crv)
        self.stair_top_crv = self.top_crv

        pending_top_crv = getattr(self, "_pending_top_crv", None)
        if pending_top_crv is not None and pending_top_crv is not self.top_crv:
            self.DisposeGeometry(pending_top_crv)
        self._pending_top_crv = None

    def OnTypeChanged(self, sender, e):
        idx = self.cmb_type.SelectedIndex
        if idx == 0:
            self.lbl_thick.Visible = False
            self.num_thick.Visible = False
        elif idx == 1:
            self.lbl_thick.Text = " 지그재그 두께 (mm):"
            self.lbl_thick.Visible = True
            self.num_thick.Visible = True
        elif idx == 2:
            self.lbl_thick.Text = " 디딤판 두께 (mm):"
            self.num_thick.Value = 30 
            self.lbl_thick.Visible = True
            self.num_thick.Visible = True
            
        self.UpdatePreview()

    def OnLandingChanged(self, sender, e):
        use_landing = bool(self.chk_landing.Checked)
        try:
            current_value = parse_step_count(self.step_count_box.Text)
        except Exception:
            current_value = None

        if use_landing and not self._step_input_uses_per_flight:
            if current_value is not None:
                self.non_landing_step_count = current_value
            self.step_count_box.Text = str(self.landing_step_count)
            self.step_count_label.Text = u"구간당 단수:"
        elif not use_landing and self._step_input_uses_per_flight:
            if current_value is not None:
                self.landing_step_count = current_value
            self.step_count_box.Text = str(self.non_landing_step_count)
            self.step_count_label.Text = u"계단 단수:"

        self._step_input_uses_per_flight = use_landing
        self.UpdatePreview()

    def OnCalculationModeChanged(self, sender, e):
        self.UpdatePreview()

    def RememberStepCount(self):
        try:
            value = parse_step_count(self.step_count_box.Text)
        except Exception:
            return
        if self._step_input_uses_per_flight:
            self.landing_step_count = value
        else:
            self.non_landing_step_count = value

    def OnStepCountKeyDown(self, sender, e):
        if e.Key == forms.Keys.Enter:
            self.RememberStepCount()
            self.UpdatePreview(show_error=True)
            e.Handled = True
        elif e.Key == forms.Keys.Escape:
            self.OnCancel(sender, e)
            e.Handled = True
        elif e.Key == forms.Keys.Space:
            e.Handled = True

    def OnStepCountLostFocus(self, sender, e):
        self.RememberStepCount()
        self.UpdatePreview()

    def OnKeyDown(self, sender, e):
        if e.Key == forms.Keys.Escape:
            self.OnCancel(sender, e)
            e.Handled = True
        elif e.Key == forms.Keys.Enter or e.Key == forms.Keys.Space:
            self.OnOk(sender, e)
            e.Handled = True

    # ==========================================================================
    # [엔진 1] 계단 기본 뼈대 라인 추출 (공통)
    # ==========================================================================
    def create_offset_top_curve(self, start_offset, end_offset):
        if abs(start_offset) < 0.001 and abs(end_offset) < 0.001:
            return self.top_crv

        offset_curve = self.top_crv.DuplicateCurve()
        offset_delta = end_offset - start_offset
        if abs(offset_delta) < 0.001:
            offset_curve.Translate(rg.Vector3d(0, 0, -start_offset))
            return offset_curve

        start = self.top_crv.PointAtStart
        end = self.top_crv.PointAtEnd
        try:
            m20, m21, m23 = calculate_top_offset_transform(
                start.X,
                start.Y,
                end.X,
                end.Y,
                start_offset,
                end_offset,
            )
        except Exception:
            offset_curve.Dispose()
            raise

        transform = rg.Transform.Identity
        transform.M20 = m20
        transform.M21 = m21
        transform.M23 = m23
        if not offset_curve.Transform(transform):
            offset_curve.Dispose()
            raise ValueError(u"마지막 단 높이에 맞춰 상부 기준선을 이동하지 못했습니다.")
        return offset_curve

    def create_profiles(
        self,
        p_t,
        p_b,
        flight_counts,
        riser_height,
        stair_type,
        thickness,
    ):
        v_diag = rg.Vector3d(p_b - p_t)
        u_xy = rg.Vector3d(v_diag.X, v_diag.Y, 0)
        if u_xy.Length < 0.001: u_xy = rg.Vector3d(1, 0, 0)
        else: u_xy.Unitize()

        total_steps = sum(flight_counts)
        flight_count = len(flight_counts)
        landing_count = flight_count - 1
        v_down = rg.Vector3d(0, 0, -riser_height)
        tread_len = (
            rg.Vector3d(v_diag.X, v_diag.Y, 0).Length
            - (landing_count * 1200.0)
        ) / float(total_steps)
        v_tread = u_xy * tread_len
        v_land = u_xy * 1200.0

        pts_main = [p_t]
        pts_guide = [p_t]
        temp_curr = p_t
        bottom_pts = [temp_curr + v_down]
        flight_nosing_pairs = []

        for i, step_count in enumerate(flight_counts):
            f_start = temp_curr + v_tread
            for unused_index in range(step_count):
                p_nose = temp_curr + v_tread
                pts_main.append(p_nose)
                f_end = p_nose
                temp_curr = p_nose + v_down
                pts_main.append(temp_curr)

            landing_guide_entry = temp_curr + v_tread
            flight_nosing_pairs.append((f_start, f_end, landing_guide_entry))

            if i < flight_count - 1:
                bottom_pts.append(temp_curr + v_down)
                temp_curr = temp_curr + v_land
                pts_main.append(temp_curr)
                bottom_pts.append(temp_curr + v_down)
            else:
                bottom_pts.append(temp_curr - v_tread)

        def append_guide_point(point):
            if pts_guide[-1].DistanceTo(point) > 0.001:
                pts_guide.append(point)

        append_guide_point(flight_nosing_pairs[0][0])
        for i, nosing_pair in enumerate(flight_nosing_pairs):
            _p_start, p_end, landing_entry = nosing_pair
            if i < flight_count - 1:
                append_guide_point(landing_entry)
                append_guide_point(flight_nosing_pairs[i + 1][0])
            else:
                append_guide_point(p_end)

        final_guide = rg.Polyline(pts_guide).ToPolylineCurve()
        full_prof = None
        
        if stair_type == 0: # Solid
            full_prof = rg.Polyline(pts_main + list(reversed(bottom_pts)) + [p_t]).ToPolylineCurve()
        elif stair_type == 1: # ZigZag
            shift_vec = -u_xy * thickness + rg.Vector3d(0, 0, -thickness)
            pts_bot_zig = [p + shift_vec for p in pts_main]
            full_prof = rg.Polyline(pts_main + list(reversed(pts_bot_zig)) + [pts_main[0]]).ToPolylineCurve()
            
        return full_prof, final_guide, pts_main

    # ==========================================================================
    # [엔진 2] 철골 계단 부품(디딤판, C형강) 생성
    # ==========================================================================
    def generate_steel_treads(self, pts_start, pts_end, thickness):
        tread_breps = []
        vec_thick = rg.Vector3d(0, 0, -thickness)
        tol = Rhino.RhinoDoc.ActiveDoc.ModelAbsoluteTolerance
        
        for i in range(len(pts_start)-1):
            p1_s, p2_s = pts_start[i], pts_start[i+1]
            p1_e, p2_e = pts_end[i], pts_end[i+1]
            
            if abs(p1_s.Z - p2_s.Z) < 1.0:
                p1sb, p2sb = p1_s + vec_thick, p2_s + vec_thick
                p1eb, p2eb = p1_e + vec_thick, p2_e + vec_thick
                
                faces = [
                    rg.Brep.CreateFromCornerPoints(p1_s, p2_s, p2_e, p1_e, tol),
                    rg.Brep.CreateFromCornerPoints(p1sb, p2sb, p2eb, p1eb, tol),
                    rg.Brep.CreateFromCornerPoints(p1_s, p2_s, p2sb, p1sb, tol),
                    rg.Brep.CreateFromCornerPoints(p2_s, p2_e, p2eb, p2sb, tol),
                    rg.Brep.CreateFromCornerPoints(p2_e, p1_e, p1eb, p2eb, tol),
                    rg.Brep.CreateFromCornerPoints(p1_e, p1_s, p1sb, p1eb, tol)
                ]
                
                valid_faces = [f for f in faces if f is not None]
                if len(valid_faces) == 6:
                    joined = rg.Brep.JoinBreps(valid_faces, tol)
                    if joined and len(joined) > 0:
                        tread_breps.append(joined[0])
                        
        return tread_breps

    def make_stringer(self, path_crv, outward_vec, H, B, t):
        vec_X = rg.Vector3d(outward_vec.X, outward_vec.Y, 0)
        if vec_X.Length < 0.001: return None
        vec_X.Unitize()
        
        vec_Y = rg.Vector3d.ZAxis 
        plane = rg.Plane(path_crv.PointAtStart, vec_X, vec_Y)
        
        pts = [
            rg.Point3d(-B, 0, 0),          
            rg.Point3d(0, 0, 0),           
            rg.Point3d(0, -t, 0),          
            rg.Point3d(-B + t, -t, 0),     
            rg.Point3d(-B + t, -(H-t), 0), 
            rg.Point3d(0, -(H-t), 0),      
            rg.Point3d(0, -H, 0),          
            rg.Point3d(-B, -H, 0),         
            rg.Point3d(-B, 0, 0)           
        ]
        
        pts_3d = [plane.PointAt(p.X, p.Y) for p in pts]
        prof_crv = rg.Polyline(pts_3d).ToPolylineCurve()
        
        path_bot = path_crv.DuplicateCurve()
        path_bot.Translate(rg.Vector3d(0, 0, -H)) 
        
        sweep = rg.SweepTwoRail()
        sweep.SweepTolerance = Rhino.RhinoDoc.ActiveDoc.ModelAbsoluteTolerance
        
        res = sweep.PerformSweep(path_crv, path_bot, [prof_crv])
        
        if not res or len(res) == 0:
            sweep1 = rg.SweepOneRail()
            sweep1.SweepTolerance = Rhino.RhinoDoc.ActiveDoc.ModelAbsoluteTolerance
            res = sweep1.PerformSweep(path_crv, prof_crv)
            
        if res and len(res) > 0:
            joined = rg.Brep.JoinBreps(res, Rhino.RhinoDoc.ActiveDoc.ModelAbsoluteTolerance)
            if joined and len(joined) > 0:
                solid = joined[0].CapPlanarHoles(Rhino.RhinoDoc.ActiveDoc.ModelAbsoluteTolerance)
                return solid if solid else joined[0]
            else:
                solid = res[0].CapPlanarHoles(Rhino.RhinoDoc.ActiveDoc.ModelAbsoluteTolerance)
                return solid if solid else res[0]
                
        return None

    # ==========================================================================
    # [지오메트리 마스터] 선택된 타입에 맞춰 분기 계산
    # ==========================================================================
    def generate_stairs(self):
        doc = Rhino.RhinoDoc.ActiveDoc
        tol = doc.ModelAbsoluteTolerance
        
        use_landing = bool(self.chk_landing.Checked)
        stair_type = self.cmb_type.SelectedIndex
        thickness = self.num_thick.Value
        step_count = parse_step_count(self.step_count_box.Text)
        calc_mode = self.calc_list.SelectedIndex

        diff_z_global = abs(self.p_top_start.Z - self.p_bot_start.Z)
        diff_z_end = abs(self.p_top_end.Z - self.p_bot_end.Z)
        v_xy_start = rg.Vector3d(self.p_bot_start.X - self.p_top_start.X, self.p_bot_start.Y - self.p_top_start.Y, 0)
        
        K = 0
        self.warning_msg = ""
        if use_landing:
            K, length_blocked = calculate_landing_count(
                diff_z_global,
                v_xy_start.Length,
            )
            if length_blocked:
                self.warning_msg = " (수평 길이 부족으로 참 생성 불가)"

        F = K + 1
        (
            total_steps,
            flight_counts,
            riser_count,
            top_offset_count,
        ) = calculate_stair_layout(
            step_count,
            F,
            calc_mode,
            use_landing,
        )

        self.current_input_step_count = step_count
        self.current_total_steps = total_steps
        self.current_K = K
        self.current_flight_counts = flight_counts
        self.current_riser_count = riser_count
        self.current_calc_mode = calc_mode

        # --- [추가/수정 포인트] 한 단 높이를 구해서 str_H에 적용 ---
        c_rh, highest_tread_offset = calculate_riser_metrics(
            diff_z_global,
            riser_count,
            top_offset_count,
        )
        end_riser_height, end_tread_offset = calculate_riser_metrics(
            diff_z_end,
            riser_count,
            top_offset_count,
        )
        self.current_riser_height = c_rh
        self.current_highest_tread_offset = highest_tread_offset

        stair_top_crv = self.create_offset_top_curve(
            highest_tread_offset,
            end_tread_offset,
        )
        if stair_top_crv is not self.top_crv:
            self._pending_top_crv = stair_top_crv
        stair_top_start = stair_top_crv.PointAtStart
        stair_top_end = stair_top_crv.PointAtEnd
        
        str_H = c_rh*2.0
        str_B = 120.0         
        str_t = 30.0          
        str_Zoffset = c_rh*0.5 # 스트링거를 디딤판 아래로 얼마나 내릴지도 동적으로 연동 가능
        # --------------------------------------------------------

        prof_start, guide_start, pts_s = self.create_profiles(
            stair_top_start,
            self.p_bot_start,
            flight_counts,
            c_rh,
            stair_type,
            thickness,
        )
        prof_end, guide_end, pts_e = self.create_profiles(
            stair_top_end,
            self.p_bot_end,
            flight_counts,
            end_riser_height,
            stair_type,
            thickness,
        )
        
        result_breps = []
        
        if stair_type in [0, 1]: 
            sweep = rg.SweepTwoRail()
            if hasattr(sweep, "MaintainHeight"):
                sweep.MaintainHeight = True 
            sweep.SweepTolerance = tol
            sweep_results = sweep.PerformSweep(stair_top_crv, self.bot_crv, [prof_start, prof_end])
            
            if sweep_results:
                joined = rg.Brep.JoinBreps(sweep_results, tol)
                if joined and len(joined) > 0:
                    solid = joined[0].CapPlanarHoles(tol)
                    result_brep = solid if solid else joined[0]
                    result_brep.Faces.SplitKinkyFaces(doc.ModelAngleToleranceRadians, True)
                    result_breps.append(result_brep)
                    
        elif stair_type == 2: # Steel
            vec_width = self.p_top_end - self.p_top_start
            vec_width.Z = 0
            vec_width.Unitize()
            
            pts_s_shifted = [p + vec_width * str_B for p in pts_s]
            pts_e_shifted = [p - vec_width * str_B for p in pts_e]
            
            treads = self.generate_steel_treads(pts_s_shifted, pts_e_shifted, thickness)
            result_breps.extend(treads)
            
            path_str_start = guide_start.DuplicateCurve()
            path_str_start.Translate(rg.Vector3d(0, 0, str_Zoffset))
            
            path_str_end = guide_end.DuplicateCurve()
            path_str_end.Translate(rg.Vector3d(0, 0, str_Zoffset))
            
            str_t_brep = self.make_stringer(path_str_start, -vec_width, str_H, str_B, str_t)
            str_b_brep = self.make_stringer(path_str_end, vec_width, str_H, str_B, str_t)
            
            if str_t_brep: result_breps.append(str_t_brep)
            if str_b_brep: result_breps.append(str_b_brep)
                
        self._pending_top_crv = None
        return result_breps, guide_start, guide_end, stair_top_crv

    def UpdatePreview(self, show_error=False):
        try:
            final_breps, guide_s, guide_e, stair_top_crv = self.generate_stairs()
            if not final_breps:
                if guide_s:
                    guide_s.Dispose()
                if guide_e:
                    guide_e.Dispose()
                if stair_top_crv is not self.top_crv:
                    stair_top_crv.Dispose()
                raise ValueError(u"계단 형상을 생성하지 못했습니다. 입력 기준선을 확인해 주세요.")
        except Exception as error:
            pending_top_crv = getattr(self, "_pending_top_crv", None)
            if pending_top_crv is not None and pending_top_crv is not self.top_crv:
                self.DisposeGeometry(pending_top_crv)
            self._pending_top_crv = None
            self.lbl_info.Text = u"입력 오류: {0}".format(error)
            if show_error:
                rs.MessageBox(
                    u"{0}".format(error),
                    48,
                    u"계단 설정 확인",
                )
            Rhino.RhinoDoc.ActiveDoc.Views.Redraw()
            return False

        self.DisposeCurrentPreview()
        self.final_breps = final_breps
        self.guide_s = guide_s
        self.guide_e = guide_e
        self.stair_top_crv = stair_top_crv
        
        preview_meshes = []
        for b in self.final_breps:
            if b:
                meshes = rg.Mesh.CreateFromBrep(b, rg.MeshingParameters.Default)
                if meshes: preview_meshes.extend(meshes)
                
        self.conduit.breps = self.final_breps
        self.conduit.meshes = preview_meshes
        
        if self.chk_railing.Checked:
            self.conduit.railing_lines = [self.guide_s, self.guide_e]
        else:
            self.conduit.railing_lines = []

        h_s = self.current_riser_height
        highest_tread_text = u"상부 바닥"
        if self.current_calc_mode == CALC_BY_TREADS_PLUS_ONE:
            highest_tread_text = u"상부 바닥 - {0:.1f}".format(
                self.current_highest_tread_offset
            )
        if bool(self.chk_landing.Checked):
            msg = (
                u"총 {0}단 | 구간당 {1}단 | 참: {2}개\n"
                u"챌판: {3}개 | 단 높이: {4:.1f} | 마지막 단: {5}"
            ).format(
                self.current_total_steps,
                self.current_input_step_count,
                self.current_K,
                self.current_riser_count,
                h_s,
                highest_tread_text,
            )
            if self.warning_msg: msg += self.warning_msg
            self.lbl_info.Text = msg
        else:
            self.lbl_info.Text = (
                u"계단: {0}단 | 챌판: {1}개 | 단 높이: {2:.1f}\n"
                u"마지막 단: {3}"
            ).format(
                self.current_total_steps,
                self.current_riser_count,
                h_s,
                highest_tread_text,
            )

        Rhino.RhinoDoc.ActiveDoc.Views.Redraw()
        return True

    def OnOptionChanged(self, sender, e):
        self.UpdatePreview()

    def OnOk(self, sender, e):
        if not self.UpdatePreview(show_error=True):
            return
        self.conduit.Enabled = False
        doc = Rhino.RhinoDoc.ActiveDoc
        doc.Views.RedrawEnabled = False
        undo_id = doc.BeginUndoRecord("Stair & Railing Bake")
        
        # [핵심 추가] 생성되는 객체들의 ID(Guid)를 수집할 빈 리스트 생성
        added_guids = []
        
        try:
            for brep in self.final_breps:
                if brep:
                    guid = doc.Objects.AddBrep(brep)
                    if guid != System.Guid.Empty:
                        added_guids.append(guid) # 솔리드 객체 ID 추가
                
            if self.chk_railing.Checked and self.guide_s and self.guide_e:
                tol = doc.ModelAbsoluteTolerance
                sw = rg.SweepTwoRail()
                if hasattr(sw, "MaintainHeight"):
                    sw.MaintainHeight = True
                sw.SweepTolerance = tol
                res_r = sw.PerformSweep(
                    self.stair_top_crv,
                    self.bot_crv,
                    [self.guide_s, self.guide_e],
                )
                
                if res_r:
                    for b in res_r:
                        for edge in b.Edges:
                            p_start = edge.EdgeCurve.PointAtStart
                            p_end = edge.EdgeCurve.PointAtEnd
                            
                            is_start_cap = (p_start.DistanceTo(self.stair_top_crv.PointAtStart) < tol and p_end.DistanceTo(self.bot_crv.PointAtStart) < tol) or \
                                           (p_start.DistanceTo(self.bot_crv.PointAtStart) < tol and p_end.DistanceTo(self.stair_top_crv.PointAtStart) < tol)
                                           
                            is_end_cap = (p_start.DistanceTo(self.stair_top_crv.PointAtEnd) < tol and p_end.DistanceTo(self.bot_crv.PointAtEnd) < tol) or \
                                         (p_start.DistanceTo(self.bot_crv.PointAtEnd) < tol and p_end.DistanceTo(self.stair_top_crv.PointAtEnd) < tol)

                            if not is_start_cap and not is_end_cap:
                                guid = doc.Objects.AddCurve(edge.EdgeCurve.DuplicateCurve())
                                if guid != System.Guid.Empty:
                                    added_guids.append(guid) # 선 객체 ID 추가

            # [핵심 추가] 수집된 객체들이 있다면, 새로운 그룹을 하나 파서 모두 편입
            if added_guids:
                group_index = doc.Groups.Add() # 그룹 생성
                for guid in added_guids:
                    doc.Groups.AddToGroup(group_index, guid) # 그룹에 요소 편입
                                    
        finally:
            doc.EndUndoRecord(undo_id)
            doc.Views.RedrawEnabled = True
            doc.Views.Redraw()
            self.Close()

    def OnCancel(self, sender, e):
        self.Close()

    def OnClosed(self, e):
        self.conduit.Enabled = False
        self.DisposeCurrentPreview()
        Rhino.RhinoDoc.ActiveDoc.Views.Redraw()
        super(StairGeneratorDialog, self).OnClosed(e)

# ==============================================================================
# [Phase 1] 메인 실행부 및 입력 옵션 제어
# ==============================================================================
def main():
    doc = Rhino.RhinoDoc.ActiveDoc

    opts = ["SelectCurves", "DrawLine", "SelPlanCrv", "CreateCoreStair"]
    res = rs.GetString("계단 생성 기준을 선택하세요", "SelectCurves", opts)
    
    if not res: return

    if res == "SelPlanCrv":
        return run_stair_module("CustomStair", "run_custom_stair")

    if res == "CreateCoreStair":
        return run_stair_module("CoreStair", "run_core_stair")
    
    c1, c2 = None, None

    if res == "SelectCurves":
        go = ric.GetObject()
        go.SetCommandPrompt("계단의 상부 라인과 하부 라인을 선택하세요 (커브 또는 모서리)")
        go.GeometryFilter = rdo.ObjectType.Curve | rdo.ObjectType.EdgeFilter
        go.SubObjectSelect = True 
        go.GetMultiple(2, 2)
        
        if go.CommandResult() != Rhino.Commands.Result.Success: return
        c1 = go.Object(0).Curve().DuplicateCurve()
        c2 = go.Object(1).Curve().DuplicateCurve()

    elif res == "DrawLine":
        pt1 = rs.GetPoint("첫 번째 선의 시작점을 클릭하세요")
        if not pt1: return
        pt2 = rs.GetPoint("첫 번째 선의 끝점을 클릭하세요", pt1)
        if not pt2: return
        
        pt3 = rs.GetPoint("두 번째 선의 시작점을 클릭하세요")
        if not pt3: return
        pt4 = rs.GetPoint("두 번째 선의 끝점을 클릭하세요", pt3)
        if not pt4: return
        
        c1 = rg.LineCurve(pt1, pt2)
        c2 = rg.LineCurve(pt3, pt4)


    if not c1 or not c2: return

    if c1.IsClosed or c2.IsClosed:
        rs.MessageBox("닫힌 커브는 지원하지 않습니다. 열린 커브를 기준으로 해주세요.", 48, "경고")
        return

    if c1.PointAtStart.Z < c1.PointAtEnd.Z: c1.Reverse()
    if c2.PointAtStart.Z < c2.PointAtEnd.Z: c2.Reverse()

    if c1.PointAtStart.Z > c2.PointAtStart.Z:
        top_crv, bot_crv = c1, c2
    else:
        top_crv, bot_crv = c2, c1

    ts = top_crv.PointAtStart
    bs = bot_crv.PointAtStart
    be = bot_crv.PointAtEnd
    if ts.DistanceTo(bs) > ts.DistanceTo(be):
        bot_crv.Reverse()

    diff_z = abs(top_crv.PointAtStart.Z - bot_crv.PointAtStart.Z)
    if diff_z < 0.1:
        rs.MessageBox("높이 차이가 너무 작습니다.", 48, "오류")
        return
        
    default_n = min(
        MAX_STEP_COUNT,
        max(MIN_STEP_COUNT, int(diff_z // 180.0)),
    )

    dialog = StairGeneratorDialog()
    dialog.SetupData(top_crv, bot_crv, default_n)
    dialog.Show()

if __name__ == "__main__":
    main()
