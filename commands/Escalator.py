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
import System
import math

# ==============================================================================
# Escalator Generator for Rhino Python
# ------------------------------------------------------------------------------
# v14
# - Closed rectangle input: long edge = direction, short edge = total width
# - Stable TextBox numeric inputs: values apply only by Enter or [Apply]
# - Fixed step pitch: user cannot edit it
# - Central tread body is one continuous zigzag solid
# - Body is split into left/right side casings, not a full-width solid
# - Glass balustrade end arcs corrected to the intended return direction
# - Handrail uses a horizontal capsule section: 75 x 30 mm
# - Landing plates removed
# - Central tread, glass balustrade, and handrail are always generated
# - Side casing/skirt width is fixed at 150 mm
# - Glass balustrade/handrail offset within side casing is user-adjustable from 0.0 to 1.0
# - Bake creates categorized layers with Es_ prefix
# - One shared balustrade fillet value is applied to both lower/upper corners
# - Glass balustrade end return radius is fixed to half of balustrade height
# - Fixed internal values are hidden from the UI
# - Initial input supports selecting an existing rectangle or drawing a new rectangle by points
# - Rise value can be measured from two picked points by Z difference
# - Direction reverse remains available
# - SelectRectangle is the default initial rectangle input mode
# - DrawRectangle projects picked points to the XY plane at the lowest picked Z value
# - DrawRectangle now shows a live preview while points are being picked
# - SelectRectangle is now the immediate default: script goes directly into object selection, while DrawRectangle remains a command option
# - Mandatory simple infill/underside cover panels are generated as Es_Body to close the open gap between the side casings
# - Mode selector added: Escalator / MovingWalk
# - If an escalator cannot be meaningfully generated because the rise is too small, it automatically switches to MovingWalk
# - MovingWalk supports zero rise and creates a continuous ramp/flat moving surface instead of stair treads
# - DrawRectangle now detects the Z difference between the highest and lowest original rectangle corners and uses it as the initial rise
# ===============================================================================

STEP_PITCH = 400.0
SIDE_CASING_WIDTH = 150.0
SKIRT_WIDTH = 150.0
HANDRAIL_MAJOR = 75.0
HANDRAIL_MINOR = 30.0
HANDRAIL_HALF_MINOR = HANDRAIL_MINOR * 0.5

MODE_ESCALATOR = "Escalator"
MODE_MOVING_WALK = "MovingWalk"
MIN_ESCALATOR_TOTAL_RISE = 600.0
MIN_ESCALATOR_STEP_RISE = 80.0

LAYER_TREAD = "Es_Tread"
LAYER_BODY = "Es_Body"
LAYER_GLASS = "Es_Glass"
LAYER_HANDRAIL = "Es_Handrail"

# ==============================================================================
# [Preview] Display Conduit
# ==============================================================================
class EscalatorPreviewConduit(rd.DisplayConduit):
    def __init__(self):
        super(EscalatorPreviewConduit, self).__init__()
        self.breps = []
        self.meshes = []
        self.curves = []
        self.material = rd.DisplayMaterial()
        self.material.Diffuse = System.Drawing.Color.LightSkyBlue
        self.material.Transparency = 0.35

    def DrawShaded(self, e):
        for mesh in self.meshes:
            if mesh:
                e.Display.DrawMeshShaded(mesh, self.material)

    def DrawForeground(self, e):
        for brep in self.breps:
            if brep:
                e.Display.DrawBrepWires(brep, System.Drawing.Color.DarkBlue, 2)
        for crv in self.curves:
            if crv:
                e.Display.DrawCurve(crv, System.Drawing.Color.Gold, 2)


# ==============================================================================
# [Utility]
# ==============================================================================
def _dot(a, b):
    return a.X * b.X + a.Y * b.Y + a.Z * b.Z


def _safe_unitize(vec, fallback=None):
    v = rg.Vector3d(vec)
    if v.Length < 0.001:
        if fallback:
            v = rg.Vector3d(fallback)
        else:
            v = rg.Vector3d(1, 0, 0)
    v.Unitize()
    return v


def _average_point(points):
    x, y, z = 0.0, 0.0, 0.0
    for p in points:
        x += p.X
        y += p.Y
        z += p.Z
    n = float(len(points))
    return rg.Point3d(x / n, y / n, z / n)


def _remove_duplicate_last(points, tol=0.001):
    pts = list(points)
    if len(pts) > 1 and pts[0].DistanceTo(pts[-1]) < tol:
        pts.pop()
    return pts


def _try_get_polyline_points(crv):
    pts = []

    try:
        rc, pl = crv.TryGetPolyline()
        if rc:
            pts = [p for p in pl]
            pts = _remove_duplicate_last(pts)
            if len(pts) >= 4:
                return pts
    except:
        try:
            pl = rg.Polyline()
            if crv.TryGetPolyline(pl):
                pts = [p for p in pl]
                pts = _remove_duplicate_last(pts)
                if len(pts) >= 4:
                    return pts
        except:
            pass

    try:
        segs = crv.DuplicateSegments()
        if segs and len(segs) >= 4:
            pts = []
            for seg in segs:
                pts.append(seg.PointAtStart)
            pts = _remove_duplicate_last(pts)
            if len(pts) >= 4:
                return pts
    except:
        pass

    try:
        div_params = crv.DivideByCount(4, False)
        if div_params:
            return [crv.PointAt(t) for t in div_params]
    except:
        pass

    return []


def get_rectangle_frame(crv):
    if not crv:
        return False, None, None, None, 0.0, 0.0, "커브가 없습니다."

    if not crv.IsClosed:
        return False, None, None, None, 0.0, 0.0, "닫힌 직사각형 커브만 지원합니다."

    pts = _try_get_polyline_points(crv)
    if len(pts) < 4:
        return False, None, None, None, 0.0, 0.0, "직사각형 꼭짓점을 추출하지 못했습니다."

    pts = pts[:4]
    center = _average_point(pts)

    edges = []
    for i in range(4):
        p0 = pts[i]
        p1 = pts[(i + 1) % 4]
        v = rg.Vector3d(p1 - p0)
        v.Z = 0.0
        edges.append((i, v.Length, v))

    edges_sorted = sorted(edges, key=lambda item: item[1], reverse=True)
    long_index, length, dir_vec = edges_sorted[0]

    if length < 1.0:
        return False, None, None, None, 0.0, 0.0, "직사각형 길이가 너무 짧습니다."

    width_vec = rg.Vector3d(pts[(long_index + 2) % 4] - pts[(long_index + 1) % 4])
    width_vec.Z = 0.0
    width = width_vec.Length

    if width < 1.0:
        return False, None, None, None, 0.0, 0.0, "직사각형 폭이 너무 좁습니다."

    dir_vec = _safe_unitize(dir_vec, rg.Vector3d(1, 0, 0))
    width_vec = _safe_unitize(width_vec, rg.Vector3d(0, 1, 0))

    cross = rg.Vector3d.CrossProduct(dir_vec, width_vec)
    if cross.Z < 0:
        width_vec.Reverse()

    center.Z = pts[0].Z
    return True, center, dir_vec, width_vec, length, width, ""


def _append_line(polycurve, p0, p1, tol):
    if p0.DistanceTo(p1) > tol:
        polycurve.Append(rg.LineCurve(p0, p1))


def _append_curve(polycurve, crv):
    if crv:
        polycurve.Append(crv)


def _signed_angle(v0, v1, axis):
    angle = rg.Vector3d.VectorAngle(v0, v1)
    c = rg.Vector3d.CrossProduct(v0, v1)
    if _dot(c, axis) < 0.0:
        angle = -angle
    return angle


def _make_arc_from_center(start_pt, end_pt, center_pt, axis, tol):
    v0 = rg.Vector3d(start_pt - center_pt)
    v1 = rg.Vector3d(end_pt - center_pt)
    if v0.Length < tol or v1.Length < tol:
        return rg.LineCurve(start_pt, end_pt)

    axis = _safe_unitize(axis, rg.Vector3d.ZAxis)
    angle = _signed_angle(v0, v1, axis)

    mid_pt = rg.Point3d(start_pt)
    xform = rg.Transform.Rotation(angle * 0.5, axis, center_pt)
    mid_pt.Transform(xform)

    try:
        arc = rg.Arc(start_pt, mid_pt, end_pt)
        if arc.IsValid:
            return rg.ArcCurve(arc)
    except:
        pass

    return rg.LineCurve(start_pt, end_pt)


def make_filleted_path_curve(path_pts, fillet_radii, tol):
    """
    path_pts는 p0,p1,p2,p3 구조를 기본으로 한다.
    fillet_radii는 내부 코너 p1,p2에 적용되는 반경 리스트다.
    값이 0이면 원래 코너를 유지한다.
    """
    if not path_pts or len(path_pts) < 2:
        return None

    if len(path_pts) == 2:
        return rg.LineCurve(path_pts[0], path_pts[1])

    segments = rg.PolyCurve()
    current = path_pts[0]

    for i in range(1, len(path_pts) - 1):
        p_prev = path_pts[i - 1]
        p = path_pts[i]
        p_next = path_pts[i + 1]

        radius = 0.0
        if i - 1 < len(fillet_radii):
            radius = max(0.0, float(fillet_radii[i - 1]))

        v_in = rg.Vector3d(p - p_prev)
        v_out = rg.Vector3d(p_next - p)
        len_in = v_in.Length
        len_out = v_out.Length

        if radius <= tol or len_in < tol or len_out < tol:
            _append_line(segments, current, p, tol)
            current = p
            continue

        v_in.Unitize()
        v_out.Unitize()
        u_prev = -v_in
        u_next = rg.Vector3d(v_out)
        phi = rg.Vector3d.VectorAngle(u_prev, u_next)

        if phi < 0.05 or abs(math.pi - phi) < 0.05:
            _append_line(segments, current, p, tol)
            current = p
            continue

        tangent_dist = radius / math.tan(phi * 0.5)
        max_dist = min(len_in, len_out) * 0.45
        if tangent_dist > max_dist:
            tangent_dist = max_dist
            radius = tangent_dist * math.tan(phi * 0.5)

        if radius <= tol or tangent_dist <= tol:
            _append_line(segments, current, p, tol)
            current = p
            continue

        t1 = p - v_in * tangent_dist
        t2 = p + v_out * tangent_dist

        bis = u_prev + u_next
        if bis.Length < tol:
            _append_line(segments, current, p, tol)
            current = p
            continue
        bis.Unitize()

        center_dist = radius / math.sin(phi * 0.5)
        center = p + bis * center_dist
        axis = rg.Vector3d.CrossProduct(v_in, v_out)
        if axis.Length < tol:
            _append_line(segments, current, p, tol)
            current = p
            continue
        axis.Unitize()

        _append_line(segments, current, t1, tol)
        arc_crv = _make_arc_from_center(t1, t2, center, axis, tol)
        _append_curve(segments, arc_crv)
        current = t2

    _append_line(segments, current, path_pts[-1], tol)
    return segments


def make_inward_cap_arc(start_pt, end_pt, inward_vec, radius, tol):
    """
    두 점을 잇는 원호를 만든다. 원호의 bulge는 inward_vec 방향으로 들어간다.
    start/end의 chord 길이에 비해 radius가 작으면 자동으로 최소 반경으로 보정한다.
    """
    chord = start_pt.DistanceTo(end_pt)
    if chord < tol:
        return None

    inward = _safe_unitize(inward_vec, rg.Vector3d(1, 0, 0))
    r = max(float(radius), chord * 0.5 + tol)
    half = chord * 0.5
    try:
        sagitta = r - math.sqrt(max(0.0, r * r - half * half))
    except:
        sagitta = half

    # 반경이 매우 클 경우 sagitta가 거의 0이 되므로 최소 시각값을 둔다.
    if sagitta < tol:
        sagitta = tol

    mid = rg.Point3d(
        (start_pt.X + end_pt.X) * 0.5,
        (start_pt.Y + end_pt.Y) * 0.5,
        (start_pt.Z + end_pt.Z) * 0.5
    ) + inward * sagitta

    try:
        arc = rg.Arc(start_pt, mid, end_pt)
        if arc.IsValid:
            return rg.ArcCurve(arc)
    except:
        pass

    return rg.LineCurve(start_pt, end_pt)


def make_closed_step_profile(top_pts, side_vec, side_offset, depth, tol):
    pts_top = [p + side_vec * side_offset for p in top_pts]
    pts_bottom = [p + side_vec * side_offset + rg.Vector3d(0, 0, -depth) for p in reversed(top_pts)]
    pts = pts_top + pts_bottom + [pts_top[0]]
    return rg.Polyline(pts).ToPolylineCurve()


def make_closed_ramp_profile(path_pts, side_vec, side_offset, depth, fillet, tol):
    """Closed side profile for a moving walk: continuous flat/ramp top surface with thickness."""
    top_pts = [p + side_vec * side_offset for p in path_pts]
    bot_pts = [p + side_vec * side_offset + rg.Vector3d(0, 0, -depth) for p in path_pts]

    top_crv = make_filleted_path_curve(top_pts, [fillet, fillet], tol)
    bot_crv = make_filleted_path_curve(bot_pts, [fillet, fillet], tol)
    if not top_crv or not bot_crv:
        return None

    bot_rev = bot_crv.DuplicateCurve()
    bot_rev.Reverse()

    profile = rg.PolyCurve()
    profile.Append(top_crv)
    _append_line(profile, top_pts[-1], bot_pts[-1], tol)
    profile.Append(bot_rev)
    _append_line(profile, bot_pts[0], top_pts[0], tol)
    return profile


def make_closed_body_profile(path_pts, side_vec, side_offset, top_offset, depth, lower_fillet, upper_fillet, tol):
    top_pts = [p + side_vec * side_offset + rg.Vector3d(0, 0, top_offset) for p in path_pts]
    bot_pts = [p + side_vec * side_offset + rg.Vector3d(0, 0, top_offset - depth) for p in path_pts]

    top_crv = make_filleted_path_curve(top_pts, [lower_fillet, upper_fillet], tol)
    bot_crv = make_filleted_path_curve(bot_pts, [lower_fillet, upper_fillet], tol)
    if not top_crv or not bot_crv:
        return None

    bot_rev = bot_crv.DuplicateCurve()
    bot_rev.Reverse()

    profile = rg.PolyCurve()
    profile.Append(top_crv)
    _append_line(profile, top_pts[-1], bot_pts[-1], tol)
    profile.Append(bot_rev)
    _append_line(profile, bot_pts[0], top_pts[0], tol)
    return profile


def loft_between_profiles(profile_a, profile_b, tol):
    result = []
    if not profile_a or not profile_b:
        return result

    try:
        lofts = rg.Brep.CreateFromLoft(
            [profile_a, profile_b],
            rg.Point3d.Unset,
            rg.Point3d.Unset,
            rg.LoftType.Normal,
            False
        )
        if lofts:
            for b in lofts:
                if b:
                    capped = b.CapPlanarHoles(tol)
                    if capped:
                        try:
                            capped.Faces.SplitKinkyFaces(Rhino.RhinoDoc.ActiveDoc.ModelAngleToleranceRadians, True)
                        except:
                            pass
                        result.append(capped)
                    else:
                        result.append(b)
    except:
        pass

    return result


def make_glass_panel_and_rail_curve(path_pts, side_vec, side_offset, direction, glass_gap, glass_height, end_radius, lower_fillet, upper_fillet, tol):
    move = side_vec * side_offset
    z_gap = rg.Vector3d(0, 0, glass_gap)
    z_height = rg.Vector3d(0, 0, glass_height)

    lower_pts = [p + move + z_gap for p in path_pts]
    upper_pts = [p + move + z_gap + z_height for p in path_pts]

    lower_crv = make_filleted_path_curve(lower_pts, [lower_fillet, upper_fillet], tol)
    upper_crv = make_filleted_path_curve(upper_pts, [lower_fillet, upper_fillet], tol)

    if not lower_crv or not upper_crv:
        return None, None

    # Corrected return direction:
    # - Start newel arc returns toward the start side.
    # - End newel arc returns toward the end side.
    # This prevents the side profile from appearing flipped.
    start_arc_up = make_inward_cap_arc(lower_pts[0], upper_pts[0], -direction, end_radius, tol)
    start_arc_down = make_inward_cap_arc(upper_pts[0], lower_pts[0], -direction, end_radius, tol)
    end_arc_down = make_inward_cap_arc(upper_pts[-1], lower_pts[-1], direction, end_radius, tol)
    end_arc_up = make_inward_cap_arc(lower_pts[-1], upper_pts[-1], direction, end_radius, tol)

    # Glass closed profile: lower path -> end cap -> reversed upper path -> start cap
    upper_rev = upper_crv.DuplicateCurve()
    upper_rev.Reverse()

    profile = rg.PolyCurve()
    profile.Append(lower_crv)
    if end_arc_up:
        profile.Append(end_arc_up)
    profile.Append(upper_rev)
    if start_arc_down:
        profile.Append(start_arc_down)

    panel = None
    try:
        breps = rg.Brep.CreatePlanarBreps(profile, tol)
        if breps and len(breps) > 0:
            panel = breps[0]
    except:
        panel = None

    # Handrail rail curve: start cap upward -> upper path -> end cap downward.
    rail_curve = rg.PolyCurve()
    if start_arc_up:
        rail_curve.Append(start_arc_up)
    rail_curve.Append(upper_crv)
    if end_arc_down:
        rail_curve.Append(end_arc_down)

    return panel, rail_curve


def make_capsule_profile(center_pt, tangent_vec, width_vec, major, minor, tol):
    """
    Handrail cross section: sideways capsule, major direction along width_vec.
    The profile plane is perpendicular to tangent_vec.
    """
    tangent = _safe_unitize(tangent_vec, rg.Vector3d(1, 0, 0))
    x_axis = _safe_unitize(width_vec, rg.Vector3d(0, 1, 0))

    # Ensure x_axis is perpendicular to tangent.
    x_axis = x_axis - tangent * _dot(x_axis, tangent)
    if x_axis.Length < tol:
        x_axis = rg.Vector3d.CrossProduct(rg.Vector3d.ZAxis, tangent)
    x_axis = _safe_unitize(x_axis, rg.Vector3d(0, 1, 0))

    y_axis = rg.Vector3d.CrossProduct(tangent, x_axis)
    y_axis = _safe_unitize(y_axis, rg.Vector3d.ZAxis)

    plane = rg.Plane(center_pt, x_axis, y_axis)

    r = minor * 0.5
    straight = max(0.0, major - minor)
    a = straight * 0.5

    # Points on a horizontal capsule in local plane coordinates.
    left_top = plane.PointAt(-a, r)
    right_top = plane.PointAt(a, r)
    right_mid = plane.PointAt(a + r, 0)
    right_bottom = plane.PointAt(a, -r)
    left_bottom = plane.PointAt(-a, -r)
    left_mid = plane.PointAt(-a - r, 0)

    pc = rg.PolyCurve()
    _append_line(pc, left_top, right_top, tol)

    try:
        arc_r = rg.Arc(right_top, right_mid, right_bottom)
        pc.Append(rg.ArcCurve(arc_r))
    except:
        _append_line(pc, right_top, right_bottom, tol)

    _append_line(pc, right_bottom, left_bottom, tol)

    try:
        arc_l = rg.Arc(left_bottom, left_mid, left_top)
        pc.Append(rg.ArcCurve(arc_l))
    except:
        _append_line(pc, left_bottom, left_top, tol)

    return pc


def make_capsule_handrail(rail_curve, width_vec, tol):
    breps = []
    if not rail_curve:
        return breps

    try:
        t0 = rail_curve.Domain.T0
        tangent = rail_curve.TangentAt(t0)
        start_pt = rail_curve.PointAtStart
        profile = make_capsule_profile(start_pt, tangent, width_vec, HANDRAIL_MAJOR, HANDRAIL_MINOR, tol)
        if not profile:
            return breps

        sweep = rg.SweepOneRail()
        sweep.SweepTolerance = tol
        sweep.AngleToleranceRadians = Rhino.RhinoDoc.ActiveDoc.ModelAngleToleranceRadians
        result = sweep.PerformSweep(rail_curve, profile)

        if result:
            joined = rg.Brep.JoinBreps(result, tol)
            source = joined if joined else result
            for b in source:
                if b:
                    capped = b.CapPlanarHoles(tol)
                    breps.append(capped if capped else b)
    except:
        # Fallback: this keeps the script usable even if a Rhino version rejects the capsule sweep.
        try:
            pipes = rg.Brep.CreatePipe(
                rail_curve,
                HANDRAIL_HALF_MINOR,
                False,
                rg.PipeCapMode.Flat,
                True,
                tol,
                Rhino.RhinoDoc.ActiveDoc.ModelAngleToleranceRadians
            )
            if pipes:
                for p in pipes:
                    if p:
                        breps.append(p)
        except:
            pass

    return breps


def ensure_layer(doc, layer_name):
    """Create/get a Rhino layer and return its index."""
    index = doc.Layers.FindByFullPath(layer_name, -1)
    if index < 0:
        index = doc.Layers.Find(layer_name, True)
    if index < 0:
        layer = rdo.Layer()
        layer.Name = layer_name
        index = doc.Layers.Add(layer)
    return index


def add_brep_to_layer(doc, brep, layer_name):
    layer_index = ensure_layer(doc, layer_name)
    attr = rdo.ObjectAttributes()
    attr.LayerIndex = layer_index
    return doc.Objects.AddBrep(brep, attr)


# ==============================================================================
# [UI Dialog]
# ==============================================================================
class EscalatorGeneratorDialog(forms.Form):
    def __init__(self):
        super(EscalatorGeneratorDialog, self).__init__()
        self.Title = "에스컬레이터 / 무빙워크 생성기 옵션"
        self.Padding = drawing.Padding(15)
        self.Resizable = False
        self.Topmost = True
        self.Owner = Rhino.UI.RhinoEtoApp.MainWindow
        self.ClientSize = drawing.Size(500, 465)

    def SetupData(self, base_crv, center, dir_vec, width_vec, rect_length, rect_width, initial_rise=None):
        self.base_crv = base_crv
        self.center = center
        self.dir_vec = dir_vec
        self.width_vec = width_vec
        self.rect_length = rect_length
        self.rect_width = rect_width

        self.conduit = EscalatorPreviewConduit()
        self.conduit.Enabled = True
        self.final_breps = []
        self.final_curves = []
        self.final_items = []
        self.warning_msg = ""
        self.current_mode = MODE_ESCALATOR
        self.auto_switched_to_movingwalk = False
        self._suppress_mode_event = False

        self.values = {
            "rise": 4500.0,
            "bottom_landing": 1500.0,
            "top_landing": 1500.0,
            "body_depth": 900.0,
            "bal_height": 900.0,
            "glass_gap": 120.0,
            "rail_offset_factor": 0.5,
            "rail_fillet": 600.0
        }

        self.initial_rise_detected = False
        self.initial_rise_value = None
        try:
            if initial_rise is not None and float(initial_rise) > 1.0:
                self.values["rise"] = min(20000.0, max(0.0, float(initial_rise)))
                self.initial_rise_detected = True
                self.initial_rise_value = self.values["rise"]
        except:
            pass

        self.textboxes = {}

        self.rbl_mode = forms.RadioButtonList()
        self.rbl_mode.DataStore = ["에스컬레이터", "무빙워크"]
        self.rbl_mode.SelectedIndex = 0
        try:
            self.rbl_mode.Orientation = forms.Orientation.Horizontal
        except:
            pass
        self.rbl_mode.SelectedIndexChanged += self.OnModeChanged

        self.tb_rise = self._make_textbox("rise")
        self.tb_bottom_landing = self._make_textbox("bottom_landing")
        self.tb_top_landing = self._make_textbox("top_landing")
        self.tb_body_depth = self._make_textbox("body_depth")
        self.tb_bal_height = self._make_textbox("bal_height")
        self.tb_glass_gap = self._make_textbox("glass_gap")
        self.tb_rail_offset_factor = self._make_textbox("rail_offset_factor")
        self.tb_rail_fillet = self._make_textbox("rail_fillet")

        self.btn_pick_rise = forms.Button(Text="두 점으로 입력")
        self.btn_pick_rise.Click += self.OnPickRise

        self.chk_reverse = forms.CheckBox(Text=" 진행 방향 반전")
        self.chk_reverse.Checked = False
        self.chk_reverse.CheckedChanged += self.OnReverseChanged

        self.lbl_info = forms.Label()
        self.lbl_info.Font = drawing.Font("Malgun Gothic", 9, drawing.FontStyle.Bold)

        self.btn_apply = forms.Button(Text="적용")
        self.btn_apply.Click += self.OnApply

        self.btn_ok = forms.Button(Text="생성")
        self.btn_ok.Click += self.OnOk

        self.btn_cancel = forms.Button(Text="취소")
        self.btn_cancel.Click += self.OnCancel

        layout = forms.DynamicLayout()
        layout.Spacing = drawing.Size(8, 8)

        layout.AddRow(forms.Label(Text="생성 타입:"), self.rbl_mode)
        layout.AddRow(None)

        layout.AddRow(forms.Label(Text="선택 직사각형 길이:"), forms.Label(Text="{:.1f} mm".format(self.rect_length)))
        layout.AddRow(forms.Label(Text="선택 직사각형 폭:"), forms.Label(Text="{:.1f} mm".format(self.rect_width)))
        layout.AddRow(None)

        rise_layout = forms.DynamicLayout()
        rise_layout.BeginHorizontal()
        rise_layout.Add(self.tb_rise)
        rise_layout.Add(self.btn_pick_rise)
        rise_layout.EndHorizontal()
        layout.AddRow(forms.Label(Text="층고 / 상승 높이 (mm):"), rise_layout)
        layout.AddRow(forms.Label(Text="하부 수평부 길이 (mm):"), self.tb_bottom_landing)
        layout.AddRow(forms.Label(Text="상부 수평부 길이 (mm):"), self.tb_top_landing)
        layout.AddRow(forms.Label(Text="본체 깊이 (mm):"), self.tb_body_depth)
        layout.AddRow(forms.Label(Text="난간 높이 (mm):"), self.tb_bal_height)
        layout.AddRow(forms.Label(Text="유리난간 하부 이격값 (mm):"), self.tb_glass_gap)
        layout.AddRow(forms.Label(Text="난간 Offset 비율 (0.0~1.0):"), self.tb_rail_offset_factor)
        layout.AddRow(forms.Label(Text="난간 Fillet 값 (mm):"), self.tb_rail_fillet)
        layout.AddRow(None)

        layout.AddRow(self.chk_reverse)
        layout.AddRow(None)
        layout.AddRow(self.lbl_info)
        layout.AddRow(None)

        btn_layout = forms.DynamicLayout()
        btn_layout.BeginHorizontal()
        btn_layout.Add(None, True)
        btn_layout.Add(self.btn_apply)
        btn_layout.Add(self.btn_ok)
        btn_layout.Add(self.btn_cancel)
        btn_layout.EndHorizontal()
        layout.AddRow(btn_layout)

        self.Content = layout
        self.KeyDown += self.OnDialogKeyDown

        self.UpdatePreview()

    def _make_textbox(self, key):
        tb = forms.TextBox()
        tb.Text = str(self.values[key])
        tb.Width = 150
        tb.KeyDown += self.OnTextBoxKeyDown
        self.textboxes[key] = tb
        return tb

    def _parse_textbox_values(self, show_error=True):
        parsed = {}
        try:
            for key, tb in self.textboxes.items():
                text = tb.Text.strip().replace(",", "")
                parsed[key] = float(text)
        except Exception as ex:
            if show_error:
                rs.MessageBox("숫자 입력값을 확인해주세요.\n{}".format(str(ex)), 48, "입력 오류")
            return False

        # Validation and clamps
        if parsed["rise"] < 0.0:
            parsed["rise"] = 0.0
        if parsed["rise"] > 20000.0:
            parsed["rise"] = 20000.0

        for k in ["bottom_landing", "top_landing"]:
            if parsed[k] < 0.0:
                parsed[k] = 0.0
            if parsed[k] > self.rect_length:
                parsed[k] = self.rect_length

        if parsed["body_depth"] < 100.0:
            parsed["body_depth"] = 100.0
        if parsed["body_depth"] > 5000.0:
            parsed["body_depth"] = 5000.0

        if parsed["bal_height"] < 300.0:
            parsed["bal_height"] = 300.0
        if parsed["bal_height"] > 2500.0:
            parsed["bal_height"] = 2500.0

        if parsed["glass_gap"] < 0.0:
            parsed["glass_gap"] = 0.0
        if parsed["glass_gap"] > 1000.0:
            parsed["glass_gap"] = 1000.0

        if parsed["rail_offset_factor"] < 0.0:
            parsed["rail_offset_factor"] = 0.0
        if parsed["rail_offset_factor"] > 1.0:
            parsed["rail_offset_factor"] = 1.0

        if parsed["rail_fillet"] < 0.0:
            parsed["rail_fillet"] = 0.0
        if parsed["rail_fillet"] > 5000.0:
            parsed["rail_fillet"] = 5000.0

        self.values = parsed
        self._sync_textboxes_to_values()
        return True

    def _sync_textboxes_to_values(self):
        for key, tb in self.textboxes.items():
            tb.Text = "{:.1f}".format(self.values[key])

    def get_selected_mode(self):
        try:
            if self.rbl_mode.SelectedIndex == 1:
                return MODE_MOVING_WALK
        except:
            pass
        return MODE_ESCALATOR

    def set_selected_mode(self, mode):
        self._suppress_mode_event = True
        try:
            self.rbl_mode.SelectedIndex = 1 if mode == MODE_MOVING_WALK else 0
        except:
            pass
        self._suppress_mode_event = False
        self.current_mode = mode

    def is_escalator_feasible(self, rise, slope_run):
        if rise < MIN_ESCALATOR_TOTAL_RISE:
            return False, "총 높이차가 {:.0f}mm 미만".format(MIN_ESCALATOR_TOTAL_RISE)
        step_count = max(1, int(round(slope_run / STEP_PITCH)))
        actual_rise = rise / float(step_count)
        if actual_rise < MIN_ESCALATOR_STEP_RISE:
            return False, "실제 단높이가 {:.0f}mm 미만".format(MIN_ESCALATOR_STEP_RISE)
        return True, ""

    # --------------------------------------------------------------------------
    # Geometry base
    # --------------------------------------------------------------------------
    def get_current_vectors(self):
        direction = rg.Vector3d(self.dir_vec)
        width_vec = rg.Vector3d(self.width_vec)
        if bool(self.chk_reverse.Checked):
            direction.Reverse()
            width_vec.Reverse()
        return direction, width_vec

    def create_center_path_points(self):
        direction, width_vec = self.get_current_vectors()
        rise = self.values["rise"]
        bottom_landing = self.values["bottom_landing"]
        top_landing = self.values["top_landing"]

        available_len = float(self.rect_length)
        slope_run = available_len - bottom_landing - top_landing

        self.warning_msg = ""
        if slope_run < 300.0:
            slope_run = 300.0
            self.warning_msg = "경고: 수평부 길이가 너무 길어 경사부를 최소 300mm로 보정했습니다."

        p0 = self.center - direction * (available_len * 0.5)
        p0.Z = self.center.Z
        p1 = p0 + direction * bottom_landing
        p2 = p1 + direction * slope_run + rg.Vector3d(0, 0, rise)
        p3 = p2 + direction * top_landing

        angle = math.degrees(math.atan2(rise, slope_run))
        return [p0, p1, p2, p3], angle, slope_run

    def create_step_top_points(self, path_pts, slope_run):
        direction, width_vec = self.get_current_vectors()
        p0, p1, p2, p3 = path_pts
        rise = self.values["rise"]
        n = max(1, int(round(slope_run / STEP_PITCH)))
        actual_run = slope_run / float(n)
        actual_rise = rise / float(n)

        pts = [p0]
        if p0.DistanceTo(p1) > 0.001:
            pts.append(p1)

        current = rg.Point3d(p1)
        for i in range(n):
            nose = current + direction * actual_run
            pts.append(nose)
            current = nose + rg.Vector3d(0, 0, actual_rise)
            pts.append(current)

        # Numerical cleanup: make sure final slope point is exactly p2.
        pts[-1] = p2
        if p2.DistanceTo(p3) > 0.001:
            pts.append(p3)

        return pts, n, actual_run, actual_rise

    # --------------------------------------------------------------------------
    # Geometry parts
    # --------------------------------------------------------------------------
    def create_central_step_solid(self, top_pts):
        tol = Rhino.RhinoDoc.ActiveDoc.ModelAbsoluteTolerance
        direction, width_vec = self.get_current_vectors()
        side_margin = SIDE_CASING_WIDTH
        inner_width = max(300.0, self.rect_width - side_margin * 2.0)
        half_inner = inner_width * 0.5

        profile_a = make_closed_step_profile(top_pts, width_vec, -half_inner, STEP_PITCH, tol)
        profile_b = make_closed_step_profile(top_pts, width_vec, half_inner, STEP_PITCH, tol)
        return loft_between_profiles(profile_a, profile_b, tol)

    def create_central_moving_walk_solid(self, path_pts):
        tol = Rhino.RhinoDoc.ActiveDoc.ModelAbsoluteTolerance
        direction, width_vec = self.get_current_vectors()
        side_margin = SIDE_CASING_WIDTH
        inner_width = max(300.0, self.rect_width - side_margin * 2.0)
        half_inner = inner_width * 0.5
        fillet = self.values.get("rail_fillet", 0.0)

        profile_a = make_closed_ramp_profile(path_pts, width_vec, -half_inner, STEP_PITCH, fillet, tol)
        profile_b = make_closed_ramp_profile(path_pts, width_vec, half_inner, STEP_PITCH, fillet, tol)
        return loft_between_profiles(profile_a, profile_b, tol)

    def create_side_casings(self, path_pts):
        tol = Rhino.RhinoDoc.ActiveDoc.ModelAbsoluteTolerance
        direction, width_vec = self.get_current_vectors()
        side_margin = SIDE_CASING_WIDTH
        half_total = self.rect_width * 0.5
        inner_width = max(300.0, self.rect_width - side_margin * 2.0)
        half_inner = inner_width * 0.5

        body_depth = self.values["body_depth"]
        rail_fillet = self.values["rail_fillet"]

        # Requested: body is lifted by glass gap + handrail radius.
        # For the fixed capsule handrail, the effective radius is HANDRAIL_MINOR / 2.
        body_top_offset = self.values["glass_gap"] + HANDRAIL_HALF_MINOR

        breps = []

        # Left casing: from central tread edge to selected rectangle outer edge.
        if half_total - half_inner > 1.0:
            left_inner = half_inner
            left_outer = half_total
            prof_li = make_closed_body_profile(path_pts, width_vec, left_inner, body_top_offset, body_depth, rail_fillet, rail_fillet, tol)
            prof_lo = make_closed_body_profile(path_pts, width_vec, left_outer, body_top_offset, body_depth, rail_fillet, rail_fillet, tol)
            breps.extend(loft_between_profiles(prof_li, prof_lo, tol))

            right_inner = -half_inner
            right_outer = -half_total
            prof_ri = make_closed_body_profile(path_pts, width_vec, right_inner, body_top_offset, body_depth, rail_fillet, rail_fillet, tol)
            prof_ro = make_closed_body_profile(path_pts, width_vec, right_outer, body_top_offset, body_depth, rail_fillet, rail_fillet, tol)
            breps.extend(loft_between_profiles(prof_ri, prof_ro, tol))

        return breps

    def create_infill_panels(self, path_pts):
        """Create mandatory simple cover panels treated as Es_Body.
        A-type solution: flat planar panels only, no additional UI option.
        - Inner side cover panels close the exposed profile at both inner casing faces.
        - Underside cover panel spans between the two inner casing faces along the lower body edge.
        """
        tol = Rhino.RhinoDoc.ActiveDoc.ModelAbsoluteTolerance
        direction, width_vec = self.get_current_vectors()

        side_margin = SIDE_CASING_WIDTH
        inner_width = max(300.0, self.rect_width - side_margin * 2.0)
        half_inner = inner_width * 0.5

        body_depth = self.values["body_depth"]
        rail_fillet = self.values["rail_fillet"]
        body_top_offset = self.values["glass_gap"] + HANDRAIL_HALF_MINOR
        body_bottom_offset = body_top_offset - body_depth

        panels = []

        # 1) Inner side cover panels.
        # These are the flat panels visible at the inside face of the left/right body casing.
        for side in [1.0, -1.0]:
            profile = make_closed_body_profile(
                path_pts,
                width_vec,
                half_inner * side,
                body_top_offset,
                body_depth,
                rail_fillet,
                rail_fillet,
                tol
            )
            if profile:
                try:
                    breps = rg.Brep.CreatePlanarBreps(profile, tol)
                    if breps:
                        for b in breps:
                            if b:
                                panels.append(b)
                except:
                    pass

        # 2) Simple underside cover panel.
        # This closes the bottom gap across the central zone between both inner casing faces.
        left_bottom_pts = [p + width_vec * (-half_inner) + rg.Vector3d(0, 0, body_bottom_offset) for p in path_pts]
        right_bottom_pts = [p + width_vec * (half_inner) + rg.Vector3d(0, 0, body_bottom_offset) for p in path_pts]

        left_bottom_crv = make_filleted_path_curve(left_bottom_pts, [rail_fillet, rail_fillet], tol)
        right_bottom_crv = make_filleted_path_curve(right_bottom_pts, [rail_fillet, rail_fillet], tol)

        if left_bottom_crv and right_bottom_crv:
            try:
                lofts = rg.Brep.CreateFromLoft(
                    [left_bottom_crv, right_bottom_crv],
                    rg.Point3d.Unset,
                    rg.Point3d.Unset,
                    rg.LoftType.Normal,
                    False
                )
                if lofts:
                    for b in lofts:
                        if b:
                            panels.append(b)
            except:
                pass

        return panels

    def create_glass_and_handrails(self, path_pts):
        tol = Rhino.RhinoDoc.ActiveDoc.ModelAbsoluteTolerance
        direction, width_vec = self.get_current_vectors()

        side_margin = SIDE_CASING_WIDTH
        inner_width = max(300.0, self.rect_width - side_margin * 2.0)
        half_inner = inner_width * 0.5

        # User-adjustable offset within the side casing.
        # 0.0 = inner edge of side casing, 0.5 = center, 1.0 = outer edge.
        offset_factor = self.values.get("rail_offset_factor", 0.5)
        glass_side_offset = half_inner + side_margin * offset_factor
        max_offset = self.rect_width * 0.5 - 20.0
        if glass_side_offset > max_offset:
            glass_side_offset = max_offset

        glass_breps = []
        handrail_breps = []
        curves = []

        for side in [1.0, -1.0]:
            panel, rail_crv = make_glass_panel_and_rail_curve(
                path_pts,
                width_vec,
                glass_side_offset * side,
                direction,
                self.values["glass_gap"],
                self.values["bal_height"],
                self.values["bal_height"] * 0.5,
                self.values["rail_fillet"],
                self.values["rail_fillet"],
                tol
            )
            if panel:
                glass_breps.append(panel)
            if rail_crv:
                hr = make_capsule_handrail(rail_crv, width_vec, tol)
                handrail_breps.extend(hr)
                curves.append(rail_crv)

        return glass_breps, handrail_breps, curves

    def generate_escalator(self):
        path_pts, angle, slope_run = self.create_center_path_points()
        requested_mode = self.get_selected_mode()
        effective_mode = requested_mode
        self.auto_switched_to_movingwalk = False

        if requested_mode == MODE_ESCALATOR:
            feasible, reason = self.is_escalator_feasible(self.values["rise"], slope_run)
            if not feasible:
                effective_mode = MODE_MOVING_WALK
                self.auto_switched_to_movingwalk = True
                self.set_selected_mode(MODE_MOVING_WALK)
                if self.warning_msg:
                    self.warning_msg += "\n"
                self.warning_msg += "높이차가 작아 무빙워크로 자동 전환했습니다. ({})".format(reason)

        result_breps = []
        result_curves = []
        result_items = []

        if effective_mode == MODE_ESCALATOR:
            top_pts, step_count, actual_run, actual_rise = self.create_step_top_points(path_pts, slope_run)
            tread_breps = self.create_central_step_solid(top_pts)
        else:
            step_count = 0
            actual_run = 0.0
            actual_rise = 0.0
            tread_breps = self.create_central_moving_walk_solid(path_pts)

        body_breps = self.create_side_casings(path_pts)
        infill_breps = self.create_infill_panels(path_pts)
        glass_breps, handrail_breps, rail_curves = self.create_glass_and_handrails(path_pts)

        for b in tread_breps:
            result_items.append((b, LAYER_TREAD))
        for b in body_breps:
            result_items.append((b, LAYER_BODY))
        for b in infill_breps:
            result_items.append((b, LAYER_BODY))
        for b in glass_breps:
            result_items.append((b, LAYER_GLASS))
        for b in handrail_breps:
            result_items.append((b, LAYER_HANDRAIL))

        result_breps.extend(tread_breps)
        result_breps.extend(body_breps)
        result_breps.extend(infill_breps)
        result_breps.extend(glass_breps)
        result_breps.extend(handrail_breps)

        # Preview-only reference curves. They are not baked.
        result_curves.extend(rail_curves)

        self.current_mode = effective_mode
        self.current_angle = angle
        self.current_slope_run = slope_run
        self.current_steps = step_count
        self.current_actual_run = actual_run
        self.current_actual_rise = actual_rise
        self.final_items = result_items

        return result_breps, result_curves

    # --------------------------------------------------------------------------
    # Preview / Event
    # --------------------------------------------------------------------------
    def UpdatePreview(self):
        if hasattr(self, 'conduit'):
            for m in self.conduit.meshes:
                if m: m.Dispose()
            for b in self.conduit.breps:
                if b: b.Dispose()
            for c in self.conduit.curves:
                if c: c.Dispose()

        self.final_breps, self.final_curves = self.generate_escalator()

        preview_meshes = []
        for b in self.final_breps:
            if b:
                meshes = rg.Mesh.CreateFromBrep(b, rg.MeshingParameters.Default)
                if meshes:
                    preview_meshes.extend(meshes)

        self.conduit.breps = self.final_breps
        self.conduit.meshes = preview_meshes
        self.conduit.curves = self.final_curves

        mode_label = "에스컬레이터" if self.current_mode == MODE_ESCALATOR else "무빙워크"
        if self.current_mode == MODE_ESCALATOR:
            msg = "{} | 자동 경사각: {:.2f}° | 경사 수평길이: {:.1f}mm | 계단 수: {} | 실제 단높이: {:.1f}mm".format(
                mode_label,
                self.current_angle,
                self.current_slope_run,
                self.current_steps,
                self.current_actual_rise
            )
        else:
            msg = "{} | 경사각: {:.2f}° | 경사 수평길이: {:.1f}mm".format(
                mode_label,
                self.current_angle,
                self.current_slope_run
            )
        if self.initial_rise_detected:
            msg += "\nDrawRectangle 입력 Z 차이 자동 감지: {:.1f}mm".format(self.initial_rise_value)
        if self.warning_msg:
            msg += "\n" + self.warning_msg
        self.lbl_info.Text = msg

        Rhino.RhinoDoc.ActiveDoc.Views.Redraw()

    def OnPickRise(self, sender, e):
        """Set rise by picking two points and using their Z-value difference."""
        was_topmost = self.Topmost
        try:
            self.Topmost = False
        except:
            pass

        try:
            try:
                self.Visible = False
            except:
                try:
                    self.Hide()
                except:
                    pass

            p1 = rs.GetPoint("층고 기준 첫 번째 점을 클릭하세요")
            if not p1:
                return
            p2 = rs.GetPoint("층고 기준 두 번째 점을 클릭하세요")
            if not p2:
                return

            pt1 = rg.Point3d(p1)
            pt2 = rg.Point3d(p2)
            dz = abs(pt2.Z - pt1.Z)

            self.tb_rise.Text = "{:.1f}".format(dz)
            if self._parse_textbox_values(True):
                self.UpdatePreview()

        finally:
            try:
                self.Visible = True
            except:
                try:
                    self.Show()
                except:
                    pass
            try:
                self.Topmost = was_topmost
                self.BringToFront()
            except:
                pass

    def OnModeChanged(self, sender, e):
        if self._suppress_mode_event:
            return
        self.current_mode = self.get_selected_mode()
        if self._parse_textbox_values(True):
            self.UpdatePreview()

    def OnApply(self, sender, e):
        if self._parse_textbox_values(True):
            self.UpdatePreview()

    def OnReverseChanged(self, sender, e):
        self.UpdatePreview()

    def OnTextBoxKeyDown(self, sender, e):
        if e.Key == forms.Keys.Enter:
            if self._parse_textbox_values(True):
                self.UpdatePreview()
            e.Handled = True
        elif e.Key == forms.Keys.Escape:
            self.OnCancel(sender, e)
            e.Handled = True

    def OnDialogKeyDown(self, sender, e):
        if e.Key == forms.Keys.Escape:
            self.OnCancel(sender, e)
            e.Handled = True

    def OnOk(self, sender, e):
        if not self._parse_textbox_values(True):
            return
        self.UpdatePreview()

        self.conduit.Enabled = False
        doc = Rhino.RhinoDoc.ActiveDoc
        doc.Views.RedrawEnabled = False
        undo_id = doc.BeginUndoRecord("Escalator / MovingWalk Generator Bake")
        added_guids = []

        try:
            bake_items = self.final_items if self.final_items else [(b, LAYER_BODY) for b in self.final_breps]

            for brep, layer_name in bake_items:
                if brep:
                    guid = add_brep_to_layer(doc, brep, layer_name)
                    if guid != System.Guid.Empty:
                        added_guids.append(guid)

            if added_guids:
                group_index = doc.Groups.Add()
                for guid in added_guids:
                    doc.Groups.AddToGroup(group_index, guid)

        finally:
            doc.EndUndoRecord(undo_id)
            doc.Views.RedrawEnabled = True
            doc.Views.Redraw()
            self.Close()

    def OnCancel(self, sender, e):
        self.Close()

    def OnClosed(self, e):
        if hasattr(self, 'conduit'):
            self.conduit.Enabled = False
        Rhino.RhinoDoc.ActiveDoc.Views.Redraw()
        super(EscalatorGeneratorDialog, self).OnClosed(e)


# ==============================================================================
# [Input Helpers]
# ==============================================================================
def make_projected_rectangle_curve_from_3pts(p0, p1, p2, show_error=False):
    """Build a horizontal rectangle curve from three points.
    p0 -> p1 defines the length direction.
    p2 defines width by perpendicular projection in XY.
    The rectangle is projected to the XY plane at the lowest picked/current Z.
    """
    p0 = rg.Point3d(p0)
    p1 = rg.Point3d(p1)
    p2 = rg.Point3d(p2)

    base_z = min(p0.Z, p1.Z, p2.Z)
    p0.Z = base_z
    p1.Z = base_z
    p2.Z = base_z

    length_vec = rg.Vector3d(p1 - p0)
    length_vec.Z = 0.0
    if length_vec.Length < 1.0:
        if show_error:
            rs.MessageBox("직사각형 길이가 너무 짧습니다.", 48, "입력 오류")
        return None

    direction = _safe_unitize(length_vec, rg.Vector3d(1, 0, 0))

    raw_width = rg.Vector3d(p2 - p1)
    raw_width.Z = 0.0
    width_vec = raw_width - direction * _dot(raw_width, direction)

    if width_vec.Length < 1.0:
        raw_width = rg.Vector3d(p2 - p0)
        raw_width.Z = 0.0
        width_vec = raw_width - direction * _dot(raw_width, direction)

    if width_vec.Length < 1.0:
        if show_error:
            rs.MessageBox("직사각형 폭이 너무 좁습니다.", 48, "입력 오류")
        return None

    p2_rect = p1 + width_vec
    p3_rect = p0 + width_vec
    pts = [p0, p1, p2_rect, p3_rect, p0]
    return rg.Polyline(pts).ToPolylineCurve()


def calculate_auto_rise_from_3pts(p0, p1, p2):
    """Return Z difference between the highest and lowest original 3D rectangle corners.
    p0 -> p1 is the first edge, and p2 is the adjacent third corner/reference point.
    The fourth original corner is inferred before XY projection so vertical intent is preserved.
    """
    try:
        q0 = rg.Point3d(p0)
        q1 = rg.Point3d(p1)
        q2 = rg.Point3d(p2)
        q3 = q0 + rg.Vector3d(q2 - q1)
        zs = [q0.Z, q1.Z, q2.Z, q3.Z]
        return max(zs) - min(zs)
    except:
        return 0.0


def get_point_with_line_preview(prompt, base_pt):
    """Pick a point while previewing the first rectangle edge."""
    gp = ric.GetPoint()
    gp.SetCommandPrompt(prompt)
    try:
        gp.SetBasePoint(base_pt, True)
        gp.DrawLineFromPoint(base_pt, True)
    except:
        pass

    def on_dynamic_draw(sender, e):
        try:
            pt = e.CurrentPoint
            base_z = min(base_pt.Z, pt.Z)
            a = rg.Point3d(base_pt.X, base_pt.Y, base_z)
            b = rg.Point3d(pt.X, pt.Y, base_z)
            e.Display.DrawLine(a, b, System.Drawing.Color.Gold, 2)
        except:
            pass

    gp.DynamicDraw += on_dynamic_draw
    res = gp.Get()
    if res != Rhino.Input.GetResult.Point:
        return None
    return gp.Point()


def get_point_with_rectangle_preview(prompt, p0, p1):
    """Pick a third point while previewing the resulting projected rectangle."""
    gp = ric.GetPoint()
    gp.SetCommandPrompt(prompt)
    try:
        gp.SetBasePoint(p1, True)
        gp.DrawLineFromPoint(p1, True)
    except:
        pass

    def on_dynamic_draw(sender, e):
        try:
            current = e.CurrentPoint
            crv = make_projected_rectangle_curve_from_3pts(p0, p1, current, False)
            if crv:
                e.Display.DrawCurve(crv, System.Drawing.Color.Gold, 3)
                # Also draw a faint diagonal from the second point to the current mouse point.
                # This helps the user understand which side is being used as the width reference.
                base_z = min(p0.Z, p1.Z, current.Z)
                b = rg.Point3d(p1.X, p1.Y, base_z)
                c = rg.Point3d(current.X, current.Y, base_z)
                e.Display.DrawLine(b, c, System.Drawing.Color.LightYellow, 1)
            else:
                base_z = min(p0.Z, p1.Z, current.Z)
                a = rg.Point3d(p0.X, p0.Y, base_z)
                b = rg.Point3d(p1.X, p1.Y, base_z)
                c = rg.Point3d(current.X, current.Y, base_z)
                e.Display.DrawLine(a, b, System.Drawing.Color.Gold, 2)
                e.Display.DrawLine(b, c, System.Drawing.Color.LightYellow, 1)
        except:
            pass

    gp.DynamicDraw += on_dynamic_draw
    res = gp.Get()
    if res != Rhino.Input.GetResult.Point:
        return None
    return gp.Point()


def draw_rectangle_curve_from_points():
    """Create a planar rectangle curve by three picked points.
    p0 -> p1 defines the first edge, p2 defines the width direction.
    During p1/p2 picking, a live preview is shown in the viewport.
    The result is projected to the XY plane at the lowest picked Z value.
    Return value: (projected_curve, auto_rise), where auto_rise is calculated from the original 3D corner Z range.
    """
    gp0 = ric.GetPoint()
    gp0.SetCommandPrompt("직사각형 첫 번째 모서리점을 클릭하세요")
    res0 = gp0.Get()
    if res0 != Rhino.Input.GetResult.Point:
        return None
    p0 = gp0.Point()

    p1 = get_point_with_line_preview("진행 방향이 될 두 번째 모서리점을 클릭하세요", p0)
    if not p1:
        return None

    p2 = get_point_with_rectangle_preview("폭 방향 점을 클릭하세요", p0, p1)
    if not p2:
        return None

    base_crv = make_projected_rectangle_curve_from_3pts(p0, p1, p2, True)
    if not base_crv:
        return None

    auto_rise = calculate_auto_rise_from_3pts(p0, p1, p2)
    return base_crv, auto_rise


# ==============================================================================
# [Main]
# ==============================================================================
def main():
    doc = Rhino.RhinoDoc.ActiveDoc

    if not doc.Path:
        res = rs.MessageBox("크래시 등 예기치 못한 종료에 대비하여\n작업 전 파일을 먼저 저장하시겠습니까?", 4 + 32, "안전 장치 (저장 권장)")
        if res == 6:
            rs.Command("_Save", True)
    elif doc.Modified:
        rs.Command("_-Save _Enter", False)
        print("[안전 장치] 작업 보호를 위해 현재 파일이 자동 저장되었습니다.")

    base_crv = None
    initial_rise = None

    # --------------------------------------------------------------------------
    # Default behavior is SelectRectangle without an extra Enter confirmation.
    # The command immediately waits for a rectangle object selection.
    # DrawRectangle is available as a command-line option during the selection prompt.
    # --------------------------------------------------------------------------
    go = ric.GetObject()
    go.SetCommandPrompt("에스컬레이터 평면 직사각형을 선택하세요. 또는 DrawRectangle 옵션으로 새 직사각형을 그리세요")
    go.GeometryFilter = rdo.ObjectType.Curve
    go.SubObjectSelect = False
    opt_draw = go.AddOption("DrawRectangle")

    while True:
        result = go.Get()

        if result == Rhino.Input.GetResult.Option:
            try:
                opt_index = go.Option().Index
            except:
                opt_index = -1

            if opt_index == opt_draw:
                draw_result = draw_rectangle_curve_from_points()
                if not draw_result:
                    return
                base_crv, initial_rise = draw_result
                break

            continue

        if result == Rhino.Input.GetResult.Object:
            objref = go.Object(0)
            crv = objref.Curve()
            if not crv:
                rs.MessageBox("커브를 인식하지 못했습니다.", 48, "오류")
                return

            base_crv = crv.DuplicateCurve()
            break

        if go.CommandResult() != Rhino.Commands.Result.Success:
            return

        return

    ok, center, dir_vec, width_vec, length, width, msg = get_rectangle_frame(base_crv)
    if not ok:
        rs.MessageBox(msg, 48, "직사각형 인식 실패")
        return

    dialog = EscalatorGeneratorDialog()
    dialog.SetupData(base_crv, center, dir_vec, width_vec, length, width, initial_rise)
    dialog.Show()


if __name__ == "__main__":
    main()
