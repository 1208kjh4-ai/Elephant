# -*- coding: utf-8 -*-
"""
CoreStair.py
Rhino 8 / IronPython 2.7

Rectangle-based multi-floor core stair generator.

Main features
-------------
- Select an existing four-line rectangle or draw one with three points.
- Vertically projects selected rectangles to World XY at their minimum Z.
- One to three turns per floor, equal riser counts for every flight.
- Alternating two-lane flights with full-width end/turn landings.
- Multi-floor repetition with automatic direction/lane continuity.
- Stepped upper surface and directly connected sloped underside.
- Semi-modal Eto settings window and wireframe DisplayConduit preview.
- Same-floor, non-adjacent-flight volume collision detection.
- Optional Boolean Union by floor.
- Session-only last-setting memory through scriptcontext.sticky.

The script is intentionally distributed as one file.
"""

import math

import Rhino
import Rhino.Geometry as rg
import Rhino.Input.Custom as ric
import Rhino.DocObjects as rdo
import Rhino.Display as rdisplay
import Rhino.UI
import scriptcontext as sc
import System

import Eto.Forms as forms
import Eto.Drawing as drawing

from System.Drawing import Color
from Rhino.UI import RhinoEtoApp, EtoExtensions

try:
    unicode
except NameError:
    unicode = str


# =============================================================================
# Constants
# =============================================================================

COMMAND_NAME = "CoreStair"
STICKY_KEY = "ElephantTools.CoreStair.LastSettings.v1"
BUILD_TAG = "2026-07-28-union-normalize-7"

MIN_STAIR_WIDTH_MM = 600.0
MIN_LANDING_DEPTH_MM = 600.0
MIN_TREAD_DEPTH_MM = 150.0
MIN_SLAB_THICKNESS_MM = 50.0
MIN_SEGMENT_RISER_COUNT = 2
MIN_CENTER_GAP_MM = 0.0

DEFAULT_FLOOR_HEIGHT_MM = 4000.0
DEFAULT_CENTER_GAP_MM = 100.0
DEFAULT_TARGET_RISER_MM = 170.0
DEFAULT_SLAB_THICKNESS_MM = 200.0
DEFAULT_TURN_COUNT = 1
DEFAULT_FLOOR_COUNT = 1

COLLISION_TOLERANCE_VOLUME_MULTIPLIER = 1000.0
COLLISION_VOLUME_RATIO = 1.0e-8

BASIS_GAP = "gap"
BASIS_WIDTH = "width"
BASIS_TARGET_RISER = "target_riser"
BASIS_SEGMENT_RISERS = "segment_risers"

PREVIEW_NORMAL_COLOR = Color.FromArgb(40, 125, 220)
PREVIEW_COLLISION_COLOR = Color.Red
PREVIEW_BOUNDARY_COLOR = Color.FromArgb(130, 130, 130)

INPUT_SPECS = (
    ("floor_height", u"층고", "float", False),
    ("floor_count", u"층수", "integer", 1),
    ("target_riser", u"목표 단높이", "float", False),
    ("segment_risers", u"구간 챌판 수", "integer", MIN_SEGMENT_RISER_COUNT),
    ("stair_width", u"계단 폭", "float", False),
    ("center_gap", u"중앙 간격", "float", True),
    ("landing_depth", u"계단참 깊이", "float", False),
    ("slab_thickness", u"슬래브 두께", "float", False),
)

TEXT_FIELD_KEYS = tuple(spec[0] for spec in INPUT_SPECS)

RESULT_SPECS = (
    ("flights", u"Flight 수", "flight_count", False),
    ("total_risers", u"전체 챌판 수", "total_risers", False),
    ("actual_riser", u"실제 단높이", "actual_riser", True),
    ("tread_depth", u"디딤판 깊이", "tread_depth", True),
    ("total_height", u"전체 생성 높이", "total_height", True),
)

FLOOR_RECORD_SPECS = (
    ("flights", "Flight", "flight_index", u"Flight"),
    ("landings", "Landing", "landing_index", u"계단참"),
)


# =============================================================================
# Exceptions
# =============================================================================

class CoreStairError(Exception):
    pass


class NumericInputError(CoreStairError):
    def __init__(self, field_key, message):
        CoreStairError.__init__(self, message)
        self.field_key = field_key
        self.message = message


class GeometryConstraintError(CoreStairError):
    pass


class UserGenerationCancel(CoreStairError):
    pass


# =============================================================================
# Unit, formatting, and UI helpers
# =============================================================================

def _doc():
    return sc.doc


def _model_tolerance():
    doc = _doc()
    if doc is None:
        return 0.01
    return max(float(doc.ModelAbsoluteTolerance), 1.0e-9)


def _model_angle_tolerance():
    doc = _doc()
    if doc is None:
        return math.radians(1.0)
    try:
        return max(float(doc.ModelAngleToleranceRadians), 1.0e-9)
    except Exception:
        return math.radians(1.0)


def _unit_scale(from_unit, to_unit):
    try:
        return float(Rhino.RhinoMath.UnitScale(from_unit, to_unit))
    except Exception:
        return 1.0


def _mm_to_doc(value_mm):
    doc = _doc()
    if doc is None:
        return float(value_mm)
    return float(value_mm) * _unit_scale(
        Rhino.UnitSystem.Millimeters, doc.ModelUnitSystem
    )


def _doc_to_mm(value_doc):
    doc = _doc()
    if doc is None:
        return float(value_doc)
    return float(value_doc) * _unit_scale(
        doc.ModelUnitSystem, Rhino.UnitSystem.Millimeters
    )


def _distance_precision():
    doc = _doc()
    if doc is None:
        return 3
    try:
        return max(0, min(8, int(doc.ModelDistanceDisplayPrecision)))
    except Exception:
        return 3


def _format_number(value):
    precision = _distance_precision()
    text = ("{0:.%df}" % precision).format(float(value))
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    if text == "-0":
        text = "0"
    return text


def _format_integer(value):
    return str(int(value))


def _unit_label():
    doc = _doc()
    if doc is None:
        return "unit"
    unit = doc.ModelUnitSystem
    mapping = {
        Rhino.UnitSystem.Millimeters: "mm",
        Rhino.UnitSystem.Centimeters: "cm",
        Rhino.UnitSystem.Meters: "m",
        Rhino.UnitSystem.Kilometers: "km",
        Rhino.UnitSystem.Inches: "in",
        Rhino.UnitSystem.Feet: "ft",
        Rhino.UnitSystem.Yards: "yd",
        Rhino.UnitSystem.Miles: "mi",
    }
    return mapping.get(unit, "unit")


def _round_half_up_positive(value):
    return int(math.floor(float(value) + 0.5))


def _show_message(message, title=COMMAND_NAME):
    Rhino.UI.Dialogs.ShowMessage(unicode(message), unicode(title))


def _write_line(message):
    try:
        Rhino.RhinoApp.WriteLine(unicode(message))
    except Exception:
        pass


def _ask_yes_no(owner, message, title):
    try:
        result = forms.MessageBox.Show(
            owner,
            unicode(message),
            unicode(title),
            forms.MessageBoxButtons.YesNo,
            forms.MessageBoxType.Warning,
        )
        return result == forms.DialogResult.Yes
    except Exception:
        # Fallback through Windows Forms if Eto overload differs by Rhino build.
        try:
            import System.Windows.Forms as winforms
            result = winforms.MessageBox.Show(
                unicode(message),
                unicode(title),
                winforms.MessageBoxButtons.YesNo,
                winforms.MessageBoxIcon.Warning,
            )
            return result == winforms.DialogResult.Yes
        except Exception:
            return False


def _safe_escape_pressed():
    try:
        # EscapeKeyPressed is a .NET event, so converting it to bool always
        # reports True. scriptcontext.escape_test returns the actual key state.
        return bool(sc.escape_test(False))
    except Exception:
        return False


def _copy_point(point):
    return rg.Point3d(point.X, point.Y, point.Z)


def _copy_vector(vector):
    return rg.Vector3d(vector.X, vector.Y, vector.Z)


def _unitized(vector, fallback=None):
    result = _copy_vector(vector)
    if result.Length <= 1.0e-12:
        if fallback is None:
            fallback = rg.Vector3d.XAxis
        result = _copy_vector(fallback)
    result.Unitize()
    return result


def _average_points(points):
    count = float(len(points))
    return rg.Point3d(
        sum([point.X for point in points]) / count,
        sum([point.Y for point in points]) / count,
        sum([point.Z for point in points]) / count,
    )


def _vector_dot(a, b):
    return a.X * b.X + a.Y * b.Y + a.Z * b.Z


def _nearly_equal(a, b, tolerance):
    return abs(float(a) - float(b)) <= float(tolerance)


# =============================================================================
# Rectangle input and local coordinate system
# =============================================================================

class RectangleInfo(object):
    def __init__(self, center, x_axis, y_axis, length, width, base_z, boundary_curve):
        self.center = _copy_point(center)
        self.base_x_axis = _unitized(x_axis, rg.Vector3d.XAxis)
        self.base_y_axis = _unitized(y_axis, rg.Vector3d.YAxis)
        self.base_length = float(length)
        self.base_width = float(width)
        self.base_z = float(base_z)
        self.boundary_curve = boundary_curve.DuplicateCurve()

    def oriented(self, rotated_90):
        if not rotated_90:
            x_axis = _copy_vector(self.base_x_axis)
            y_axis = _copy_vector(self.base_y_axis)
            length = self.base_length
            width = self.base_width
        else:
            x_axis = _copy_vector(self.base_y_axis)
            x_axis = _orient_axis_to_positive_world(x_axis)
            y_axis = rg.Vector3d.CrossProduct(rg.Vector3d.ZAxis, x_axis)
            y_axis.Unitize()
            length = self.base_width
            width = self.base_length

        origin = (
            self.center
            - x_axis * (length * 0.5)
            - y_axis * (width * 0.5)
        )
        return OrientedRectangle(
            self,
            origin,
            x_axis,
            y_axis,
            length,
            width,
            self.base_z,
        )


class OrientedRectangle(object):
    def __init__(self, source, origin, x_axis, y_axis, length, width, base_z):
        self.source = source
        self.origin = _copy_point(origin)
        self.x_axis = _unitized(x_axis, rg.Vector3d.XAxis)
        self.y_axis = _unitized(y_axis, rg.Vector3d.YAxis)
        self.length = float(length)
        self.width = float(width)
        self.base_z = float(base_z)

    def point(self, x, y, z_offset=0.0):
        return rg.Point3d(
            self.origin.X + self.x_axis.X * x + self.y_axis.X * y,
            self.origin.Y + self.x_axis.Y * x + self.y_axis.Y * y,
            self.base_z + z_offset,
        )

    def plane(self):
        return rg.Plane(self.origin, self.x_axis, self.y_axis)

    def footprint_curve(self):
        points = [
            self.point(0.0, 0.0, 0.0),
            self.point(self.length, 0.0, 0.0),
            self.point(self.length, self.width, 0.0),
            self.point(0.0, self.width, 0.0),
            self.point(0.0, 0.0, 0.0),
        ]
        return rg.PolylineCurve(points)


class RectangleSource(object):
    def __init__(self, rect_info, is_new, source_curve=None, source_id=None):
        self.rect_info = rect_info
        self.is_new = bool(is_new)
        self.source_curve = source_curve.DuplicateCurve() if source_curve else None
        self.source_id = source_id


def _orient_axis_to_positive_world(axis):
    axis = _unitized(axis, rg.Vector3d.XAxis)
    dot_x = axis.X
    dot_y = axis.Y
    if abs(dot_x) >= abs(dot_y):
        if dot_x < 0.0:
            axis.Reverse()
    else:
        if dot_y < 0.0:
            axis.Reverse()
    return axis


def _try_line_from_curve(curve):
    if curve is None:
        return False, rg.Line.Unset

    try:
        tolerance = _model_tolerance()
        if not curve.IsLinear(tolerance):
            return False, rg.Line.Unset
        line = rg.Line(curve.PointAtStart, curve.PointAtEnd)
        if line.IsValid and line.Length > tolerance:
            return True, line
    except Exception:
        pass
    return False, rg.Line.Unset


def _extract_four_line_segments(curve):
    try:
        segments = list(curve.DuplicateSegments())
    except Exception:
        segments = []

    if len(segments) != 4:
        return None, u"정확히 4개의 직선 세그먼트로 구성된 닫힌 커브가 필요합니다."

    lines = []
    for index, segment in enumerate(segments):
        success, line = _try_line_from_curve(segment)
        if not success:
            return None, u"{0}번째 세그먼트가 직선이 아닙니다.".format(index + 1)
        lines.append(line)
    return lines, None


def analyze_rectangle_curve(curve):
    if curve is None:
        return None, u"직사각형 커브가 없습니다."
    if not curve.IsClosed:
        return None, u"닫힌 직사각형 커브만 사용할 수 있습니다."

    lines, error = _extract_four_line_segments(curve)
    if error:
        return None, error

    tolerance = _model_tolerance()
    source_points = [line.From for line in lines]
    minimum_z = min([point.Z for point in source_points] + [line.To.Z for line in lines])
    points = [rg.Point3d(point.X, point.Y, minimum_z) for point in source_points]

    # Verify projected segment continuity and create projected edge vectors.
    vectors = []
    lengths = []
    for index in range(4):
        point_a = points[index]
        point_b = points[(index + 1) % 4]
        vector = rg.Vector3d(point_b - point_a)
        vector.Z = 0.0
        length = vector.Length
        if length <= tolerance * 10.0:
            return None, u"직사각형 변의 길이가 모델 공차보다 너무 작습니다."
        vectors.append(vector)
        lengths.append(length)

    unit_vectors = [_unitized(vector) for vector in vectors]
    angular_tolerance = max(1.0e-7, tolerance / max(lengths))
    length_tolerance = max(tolerance * 5.0, max(lengths) * 1.0e-7)

    for index in range(4):
        next_index = (index + 1) % 4
        if abs(_vector_dot(unit_vectors[index], unit_vectors[next_index])) > angular_tolerance:
            return None, u"투영된 커브의 인접 변이 직각이 아닙니다."

    if abs(abs(_vector_dot(unit_vectors[0], unit_vectors[2])) - 1.0) > angular_tolerance:
        return None, u"투영된 커브의 마주 보는 변이 평행하지 않습니다."
    if abs(abs(_vector_dot(unit_vectors[1], unit_vectors[3])) - 1.0) > angular_tolerance:
        return None, u"투영된 커브의 마주 보는 변이 평행하지 않습니다."
    if not _nearly_equal(lengths[0], lengths[2], length_tolerance):
        return None, u"투영된 커브의 마주 보는 변 길이가 다릅니다."
    if not _nearly_equal(lengths[1], lengths[3], length_tolerance):
        return None, u"투영된 커브의 마주 보는 변 길이가 다릅니다."

    cross = rg.Vector3d.CrossProduct(unit_vectors[0], unit_vectors[1])
    if abs(cross.Z) <= angular_tolerance:
        return None, u"투영된 직사각형의 면적이 0에 가깝습니다."

    center = _average_points(points)
    pair_0 = (lengths[0] + lengths[2]) * 0.5
    pair_1 = (lengths[1] + lengths[3]) * 0.5
    square_tolerance = max(length_tolerance, max(pair_0, pair_1) * 1.0e-6)

    if pair_0 > pair_1 + square_tolerance:
        travel_axis = unit_vectors[0]
        length = pair_0
        width = pair_1
    elif pair_1 > pair_0 + square_tolerance:
        travel_axis = unit_vectors[1]
        length = pair_1
        width = pair_0
    else:
        # Square: choose the edge direction closer to World +X as travel axis.
        candidate_0 = unit_vectors[0]
        candidate_1 = unit_vectors[1]
        if abs(candidate_0.X) >= abs(candidate_1.X):
            travel_axis = candidate_0
            length = pair_0
            width = pair_1
        else:
            travel_axis = candidate_1
            length = pair_1
            width = pair_0

    travel_axis = _orient_axis_to_positive_world(travel_axis)
    width_axis = rg.Vector3d.CrossProduct(rg.Vector3d.ZAxis, travel_axis)
    width_axis.Unitize()

    projected_points = list(points)
    projected_points.append(points[0])
    projected_curve = rg.PolylineCurve(projected_points)

    return RectangleInfo(
        center,
        travel_axis,
        width_axis,
        length,
        width,
        minimum_z,
        projected_curve,
    ), None


def _make_rectangle_curve_from_three_points(point_0, point_1, point_2):
    base_z = point_0.Z
    p0 = rg.Point3d(point_0.X, point_0.Y, base_z)
    p1 = rg.Point3d(point_1.X, point_1.Y, base_z)
    raw_x = rg.Vector3d(p1 - p0)
    raw_x.Z = 0.0
    if raw_x.Length <= _model_tolerance() * 10.0:
        return None, u"첫 번째 변의 길이가 너무 짧습니다."
    x_axis = _unitized(raw_x)
    y_axis = rg.Vector3d.CrossProduct(rg.Vector3d.ZAxis, x_axis)
    y_axis.Unitize()

    p2_flat = rg.Point3d(point_2.X, point_2.Y, base_z)
    raw_width = rg.Vector3d(p2_flat - p0)
    signed_width = _vector_dot(raw_width, y_axis)
    if abs(signed_width) <= _model_tolerance() * 10.0:
        return None, u"직사각형 폭이 너무 작습니다."
    if signed_width < 0.0:
        y_axis.Reverse()
        signed_width = -signed_width

    length = raw_x.Length
    width = signed_width
    q0 = p0
    q1 = p0 + x_axis * length
    q2 = q1 + y_axis * width
    q3 = p0 + y_axis * width
    return rg.PolylineCurve([q0, q1, q2, q3, q0]), None


def _draw_three_point_rectangle():
    first_getter = ric.GetPoint()
    first_getter.SetCommandPrompt(u"직사각형의 첫 번째 모서리를 지정하세요")
    first_getter.Get()
    if first_getter.CommandResult() != Rhino.Commands.Result.Success:
        return None
    point_0 = first_getter.Point()

    second_getter = ric.GetPoint()
    second_getter.SetCommandPrompt(u"계단 기준 방향과 길이를 지정하세요")
    second_getter.SetBasePoint(point_0, True)
    second_getter.DrawLineFromPoint(point_0, True)
    second_getter.Get()
    if second_getter.CommandResult() != Rhino.Commands.Result.Success:
        return None
    point_1 = second_getter.Point()

    base_z = point_0.Z
    flat_0 = rg.Point3d(point_0.X, point_0.Y, base_z)
    flat_1 = rg.Point3d(point_1.X, point_1.Y, base_z)
    x_vector = rg.Vector3d(flat_1 - flat_0)
    x_vector.Z = 0.0
    if x_vector.Length <= _model_tolerance() * 10.0:
        _show_message(u"첫 번째 변의 길이가 너무 짧습니다.", u"CoreStair 입력 오류")
        return None
    x_axis = _unitized(x_vector)
    y_axis = rg.Vector3d.CrossProduct(rg.Vector3d.ZAxis, x_axis)
    y_axis.Unitize()

    third_getter = ric.GetPoint()
    third_getter.SetCommandPrompt(u"직사각형 폭을 지정하세요")
    third_getter.SetBasePoint(point_0, True)

    def draw_rectangle(sender, event):
        try:
            current = rg.Point3d(event.CurrentPoint.X, event.CurrentPoint.Y, base_z)
            width_vector = rg.Vector3d(current - flat_0)
            signed_width = _vector_dot(width_vector, y_axis)
            local_y = _copy_vector(y_axis)
            if signed_width < 0.0:
                local_y.Reverse()
                signed_width = -signed_width
            q0 = flat_0
            q1 = flat_1
            q2 = q1 + local_y * signed_width
            q3 = q0 + local_y * signed_width
            polyline = rg.Polyline([q0, q1, q2, q3, q0])
            event.Display.DrawPolyline(polyline, PREVIEW_NORMAL_COLOR, 1)
        except Exception:
            pass

    third_getter.DynamicDraw += draw_rectangle
    try:
        third_getter.Get()
    finally:
        try:
            third_getter.DynamicDraw -= draw_rectangle
        except Exception:
            pass

    if third_getter.CommandResult() != Rhino.Commands.Result.Success:
        return None

    curve, error = _make_rectangle_curve_from_three_points(
        point_0, point_1, third_getter.Point()
    )
    if error:
        _show_message(error, u"CoreStair 입력 오류")
        return None
    return curve


def request_rectangle_source():
    while True:
        getter = ric.GetObject()
        getter.SetCommandPrompt(u"닫힌 직사각형을 선택하거나 DrawRectangle 옵션을 선택하세요")
        getter.GeometryFilter = rdo.ObjectType.Curve
        getter.SubObjectSelect = False
        getter.GroupSelect = False
        getter.EnablePreSelect(True, True)
        draw_option_index = getter.AddOption("DrawRectangle")
        getter.Get()

        result = getter.Result()
        command_result = getter.CommandResult()

        if result == Rhino.Input.GetResult.Option:
            try:
                selected_option = getter.Option().Index
            except Exception:
                selected_option = draw_option_index
            if selected_option == draw_option_index:
                drawn_curve = _draw_three_point_rectangle()
                if drawn_curve is None:
                    if command_result == Rhino.Commands.Result.Cancel:
                        return None
                    continue
                rect_info, error = analyze_rectangle_curve(drawn_curve)
                if error:
                    _show_message(error, u"CoreStair 직사각형 오류")
                    continue
                return RectangleSource(rect_info, True, drawn_curve, None)

        if command_result == Rhino.Commands.Result.Cancel:
            return None
        if command_result != Rhino.Commands.Result.Success:
            return None

        obj_ref = getter.Object(0)
        curve = obj_ref.Curve()
        if curve is None:
            sc.doc.Objects.UnselectAll()
            sc.doc.Views.Redraw()
            _show_message(u"선택한 객체가 유효한 커브가 아닙니다.", u"CoreStair 직사각형 오류")
            continue

        rect_info, error = analyze_rectangle_curve(curve)
        if error:
            sc.doc.Objects.UnselectAll()
            sc.doc.Views.Redraw()
            _show_message(
                error + u"\n다른 직사각형을 선택하거나 다시 그려 주세요.",
                u"CoreStair 직사각형 오류",
            )
            continue
        return RectangleSource(rect_info, False, None, obj_ref.ObjectId)


# =============================================================================
# Settings
# =============================================================================

class CoreStairSettings(object):
    def __init__(self):
        self.floor_height = _mm_to_doc(DEFAULT_FLOOR_HEIGHT_MM)
        self.floor_count = DEFAULT_FLOOR_COUNT
        self.target_riser = _mm_to_doc(DEFAULT_TARGET_RISER_MM)
        self.segment_risers = 0
        self.riser_basis = BASIS_TARGET_RISER

        self.stair_width = 0.0
        self.center_gap = _mm_to_doc(DEFAULT_CENTER_GAP_MM)
        self.width_basis = BASIS_GAP
        self.landing_depth = None
        self.slab_thickness = _mm_to_doc(DEFAULT_SLAB_THICKNESS_MM)

        self.turn_count = DEFAULT_TURN_COUNT
        self.include_floor_landings = True
        self.join_per_floor = True

        # Direction states reset for every command.
        self.rotated_90 = False
        self.start_far = False
        self.start_right = False
        self.z_flipped = False

    def copy(self):
        other = CoreStairSettings()
        other.__dict__.update(self.__dict__)
        return other


def _identity(value):
    return value


PERSISTED_SETTING_SPECS = (
    ("floor_height", "floor_height_mm", DEFAULT_FLOOR_HEIGHT_MM, float, _mm_to_doc, _doc_to_mm),
    ("floor_count", "floor_count", DEFAULT_FLOOR_COUNT, int, _identity, int),
    ("target_riser", "target_riser_mm", DEFAULT_TARGET_RISER_MM, float, _mm_to_doc, _doc_to_mm),
    ("segment_risers", "segment_risers", 0, int, _identity, int),
    ("riser_basis", "riser_basis", BASIS_TARGET_RISER, _identity, _identity, _identity),
    ("stair_width", "stair_width_mm", 0.0, float, _mm_to_doc, _doc_to_mm),
    ("center_gap", "center_gap_mm", DEFAULT_CENTER_GAP_MM, float, _mm_to_doc, _doc_to_mm),
    ("width_basis", "width_basis", BASIS_GAP, _identity, _identity, _identity),
    (
        "slab_thickness",
        "slab_thickness_mm",
        DEFAULT_SLAB_THICKNESS_MM,
        float,
        _mm_to_doc,
        _doc_to_mm,
    ),
    ("turn_count", "turn_count", DEFAULT_TURN_COUNT, int, _identity, int),
    ("include_floor_landings", "include_floor_landings", True, bool, _identity, bool),
    ("join_per_floor", "join_per_floor", True, bool, _identity, bool),
)


def _load_last_settings():
    settings = CoreStairSettings()
    data = sc.sticky.get(STICKY_KEY)
    if not isinstance(data, dict):
        return settings, False

    try:
        for (
            attribute,
            key,
            default,
            cast,
            from_storage,
            _to_storage,
        ) in PERSISTED_SETTING_SPECS:
            setattr(settings, attribute, from_storage(cast(data.get(key, default))))

        landing_depth_mm = data.get("landing_depth_mm", None)
        settings.landing_depth = (
            _mm_to_doc(float(landing_depth_mm))
            if landing_depth_mm is not None
            else None
        )
    except Exception:
        return CoreStairSettings(), False

    return settings, True


def _save_last_settings(settings):
    data = {}
    for attribute, key, _default, _cast, _from_storage, to_storage in PERSISTED_SETTING_SPECS:
        data[key] = to_storage(getattr(settings, attribute))
    data["landing_depth_mm"] = _doc_to_mm(settings.landing_depth)
    sc.sticky[STICKY_KEY] = data


# =============================================================================
# Geometry creation helpers
# =============================================================================

def _make_oriented_box(rect, x0, x1, y0, y1, z0, z1):
    if (
        abs(x1 - x0) <= 1.0e-12
        or abs(y1 - y0) <= 1.0e-12
        or abs(z1 - z0) <= 1.0e-12
    ):
        return None

    plane = rect.plane()
    box = rg.Box(
        plane,
        rg.Interval(min(x0, x1), max(x0, x1)),
        rg.Interval(min(y0, y1), max(y0, y1)),
        rg.Interval(min(z0, z1), max(z0, z1)),
    )
    if not box.IsValid:
        return None
    return box.ToBrep()


def _make_landing(rect, settings, far_side, upper_level, z_sign):
    if far_side:
        x0 = rect.length - settings.landing_depth
        x1 = rect.length
    else:
        x0 = 0.0
        x1 = settings.landing_depth
    return _make_oriented_box(
        rect,
        x0,
        x1,
        0.0,
        rect.width,
        z_sign * (upper_level - settings.slab_thickness),
        z_sign * upper_level,
    )


def _landing_record(brep, floor_number, landing_index, kind):
    return {
        "brep": brep,
        "floor": floor_number,
        "landing_index": landing_index,
        "kind": kind,
    }


def _iter_floor_records(floor_record):
    for collection_key, kind, index_key, display_name in FLOOR_RECORD_SPECS:
        for record in floor_record[collection_key]:
            yield record, kind, index_key, display_name


def _make_extruded_profile(points, extrusion_vector, tolerance):
    if len(points) < 4:
        return None
    closed_points = list(points)
    if closed_points[0].DistanceTo(closed_points[-1]) > tolerance:
        closed_points.append(closed_points[0])
    curve = rg.PolylineCurve(closed_points)

    try:
        brep = rg.Brep.CreateFromExtrusion(curve, extrusion_vector, True)
        if brep is not None and brep.IsValid:
            return brep
    except Exception:
        pass

    try:
        surface = rg.Surface.CreateExtrusion(curve, extrusion_vector)
        if surface is None:
            return None
        brep = surface.ToBrep()
        capped = brep.CapPlanarHoles(tolerance)
        if capped is not None and capped.IsValid:
            return capped
        if brep.IsValid:
            return brep
    except Exception:
        pass
    return None


def _flight_brep(rect, x_start, x_end, y_start, width, lower_level, upper_level,
                 segment_risers, slab_thickness, z_sign, extend_under_landing):
    tolerance = _model_tolerance()
    run = abs(x_end - x_start)
    tread_count = segment_risers - 1
    if tread_count <= 0 or run <= tolerance:
        return None

    direction = 1.0 if x_end >= x_start else -1.0
    tread_depth = run / float(tread_count)
    riser_height = (upper_level - lower_level) / float(segment_risers)

    def point_at(distance, level):
        x = x_start + direction * distance
        z = z_sign * level
        return rect.point(x, y_start, z)

    profile = []
    profile.append(point_at(0.0, lower_level))

    current_level = lower_level + riser_height
    profile.append(point_at(0.0, current_level))

    for tread_index in range(tread_count):
        distance = (tread_index + 1) * tread_depth
        profile.append(point_at(distance, current_level))
        if tread_index < tread_count - 1:
            current_level += riser_height
            profile.append(point_at(distance, current_level))

    # Final riser arrives exactly at the destination landing surface.
    profile.append(point_at(run, upper_level))

    lower_under_level = lower_level - slab_thickness
    under_distance = run
    if extend_under_landing:
        # Continue one going into the landing. The sloped soffit then meets the
        # horizontal landing underside without a vertical closure at the joint.
        under_distance += tread_depth
        profile.append(point_at(under_distance, upper_level))
        upper_under_level = upper_level - slab_thickness
    else:
        # With no destination landing, close the parallel soffit at the flight.
        upper_under_level = (
            lower_under_level + tread_count * riser_height
        )

    profile.append(point_at(under_distance, upper_under_level))
    profile.append(point_at(0.0, lower_under_level))
    profile.append(point_at(0.0, lower_level))

    extrusion = rect.y_axis * width
    return _make_extruded_profile(profile, extrusion, tolerance)


def _volume_of_brep(brep):
    if brep is None:
        return 0.0
    try:
        properties = rg.VolumeMassProperties.Compute(brep)
        if properties is None:
            return 0.0
        return abs(float(properties.Volume))
    except Exception:
        return 0.0


def _bounding_boxes_overlap(box_a, box_b, tolerance):
    if not box_a.IsValid or not box_b.IsValid:
        return True
    if box_a.Max.X < box_b.Min.X - tolerance or box_b.Max.X < box_a.Min.X - tolerance:
        return False
    if box_a.Max.Y < box_b.Min.Y - tolerance or box_b.Max.Y < box_a.Min.Y - tolerance:
        return False
    if box_a.Max.Z < box_b.Min.Z - tolerance or box_b.Max.Z < box_a.Min.Z - tolerance:
        return False
    return True


def _check_collision_pair(brep_a, brep_b, floor_number, flight_a, flight_b):
    tolerance = _model_tolerance()
    box_a = brep_a.GetBoundingBox(True)
    box_b = brep_b.GetBoundingBox(True)
    if not _bounding_boxes_overlap(box_a, box_b, tolerance):
        return False, False

    volume_a = _volume_of_brep(brep_a)
    volume_b = _volume_of_brep(brep_b)
    threshold = max(
        (tolerance ** 3) * COLLISION_TOLERANCE_VOLUME_MULTIPLIER,
        min(volume_a, volume_b) * COLLISION_VOLUME_RATIO,
    )

    try:
        intersections = rg.Brep.CreateBooleanIntersection(
            brep_a, brep_b, tolerance
        )
    except Exception as error:
        _write_line(
            u"CoreStair: {0:02d}층 Flight {1} ↔ Flight {2} 충돌 검사를 완료하지 못했습니다: {3}".format(
                floor_number, flight_a, flight_b, error
            )
        )
        return False, True

    if intersections is None:
        _write_line(
            u"CoreStair: {0:02d}층 Flight {1} ↔ Flight {2} 충돌 검사를 완료하지 못했습니다.".format(
                floor_number, flight_a, flight_b
            )
        )
        return False, True

    for intersection in intersections:
        if _volume_of_brep(intersection) > threshold:
            return True, False
    return False, False


def _find_collisions(floor_records):
    collisions = []
    check_failures = []
    cache = {}

    for floor_record in floor_records:
        flights = floor_record["flights"]
        # Floors repeat one of two congruent start patterns. Reuse the expensive
        # Boolean result for the same parity and local flight pair.
        floor_parity = flights[0]["global_index"] % 2
        for index_a in range(len(flights)):
            for index_b in range(index_a + 1, len(flights)):
                if abs(index_b - index_a) <= 1:
                    continue

                cache_key = (floor_parity, index_a, index_b)
                if cache_key not in cache:
                    cache[cache_key] = _check_collision_pair(
                        flights[index_a]["brep"],
                        flights[index_b]["brep"],
                        floor_record["floor"],
                        flights[index_a]["flight_index"],
                        flights[index_b]["flight_index"],
                    )
                collides, check_failed = cache[cache_key]
                pair = (
                    floor_record["floor"],
                    flights[index_a]["flight_index"],
                    flights[index_b]["flight_index"],
                )
                if check_failed:
                    check_failures.append(pair)
                if collides:
                    flights[index_a]["collision"] = True
                    flights[index_b]["collision"] = True
                    collisions.append(pair)

    return collisions, check_failures


def _build_core_stair(rect, settings):
    flight_count = settings.turn_count + 1
    total_risers = settings.segment_risers * flight_count
    actual_riser = settings.floor_height / float(total_risers)
    flight_height = settings.floor_height / float(flight_count)
    run_length = rect.length - 2.0 * settings.landing_depth
    tread_count = settings.segment_risers - 1
    tread_depth = run_length / float(tread_count)
    z_sign = -1.0 if settings.z_flipped else 1.0

    left_y = 0.0
    right_y = settings.stair_width + settings.center_gap
    lane_starts = [left_y, right_y]

    floor_records = []
    all_flights = []
    all_landings = []

    global_flight_index = 0
    for floor_index in range(settings.floor_count):
        floor_number = floor_index + 1
        floor_base = floor_index * settings.floor_height
        floor_flights = []
        floor_landings = []

        # Very bottom floor landing is owned only by the first floor.
        first_side_far = bool(settings.start_far)
        if global_flight_index % 2 == 1:
            first_side_far = not first_side_far

        if floor_index == 0 and settings.include_floor_landings:
            landing = _make_landing(rect, settings, first_side_far, 0.0, z_sign)
            if landing is None:
                raise GeometryConstraintError(u"최하부 층 계단참 형상 생성에 실패했습니다.")
            floor_landings.append(
                _landing_record(landing, floor_number, 1, "floor_bottom")
            )

        for local_flight_index in range(flight_count):
            global_index = floor_index * flight_count + local_flight_index
            lane_index = global_index % 2
            if settings.start_right:
                lane_index = 1 - lane_index
            y_start = lane_starts[lane_index]

            start_far = bool(settings.start_far)
            if global_index % 2 == 1:
                start_far = not start_far

            if start_far:
                x_start = rect.length - settings.landing_depth
                x_end = settings.landing_depth
            else:
                x_start = settings.landing_depth
                x_end = rect.length - settings.landing_depth

            lower_level = floor_base + local_flight_index * flight_height
            upper_level = floor_base + (local_flight_index + 1) * flight_height
            is_last_flight = local_flight_index == flight_count - 1
            create_destination_landing = (
                (not is_last_flight) or settings.include_floor_landings
            )

            flight = _flight_brep(
                rect,
                x_start,
                x_end,
                y_start,
                settings.stair_width,
                lower_level,
                upper_level,
                settings.segment_risers,
                settings.slab_thickness,
                z_sign,
                create_destination_landing,
            )
            if flight is None or not flight.IsValid:
                raise GeometryConstraintError(
                    u"{0:02d}층 Flight {1} 형상 생성에 실패했습니다.".format(
                        floor_number, local_flight_index + 1
                    )
                )

            record = {
                "brep": flight,
                "floor": floor_number,
                "flight_index": local_flight_index + 1,
                "global_index": global_index,
                "collision": False,
            }
            floor_flights.append(record)
            all_flights.append(record)

            if create_destination_landing:
                destination_far = not start_far
                landing = _make_landing(
                    rect, settings, destination_far, upper_level, z_sign
                )
                if landing is None:
                    raise GeometryConstraintError(
                        u"{0:02d}층 계단참 형상 생성에 실패했습니다.".format(floor_number)
                    )
                floor_landings.append(
                    _landing_record(
                        landing,
                        floor_number,
                        len(floor_landings) + 1,
                        "floor_upper" if is_last_flight else "turn",
                    )
                )
                all_landings.append(floor_landings[-1])

        floor_records.append({
            "floor": floor_number,
            "flights": floor_flights,
            "landings": floor_landings,
        })
        global_flight_index += flight_count

    collisions, collision_check_failures = _find_collisions(floor_records)

    return {
        "rect": rect,
        "settings": settings.copy(),
        "floors": floor_records,
        "flights": all_flights,
        "landings": all_landings,
        "collisions": collisions,
        "collision_check_failures": collision_check_failures,
        "flight_count": flight_count,
        "total_risers": total_risers,
        "actual_riser": actual_riser,
        "tread_depth": tread_depth,
        "total_height": settings.floor_height * settings.floor_count,
    }


# =============================================================================
# Preview conduit
# =============================================================================

class CoreStairPreviewConduit(rdisplay.DisplayConduit):
    def __init__(self, rectangle_source):
        rdisplay.DisplayConduit.__init__(self)
        self.rectangle_source = rectangle_source
        self.preview_data = None

    def update_rectangle(self, rectangle_source):
        self.rectangle_source = rectangle_source
        sc.doc.Views.Redraw()

    def update_preview(self, preview_data):
        self.preview_data = preview_data
        sc.doc.Views.Redraw()

    def clear_stair_preview(self):
        self.preview_data = None
        sc.doc.Views.Redraw()

    def _boundary_curve(self):
        if self.preview_data is not None:
            return self.preview_data["rect"].footprint_curve()
        if self.rectangle_source is not None:
            return self.rectangle_source.rect_info.boundary_curve.DuplicateCurve()
        return None

    def CalculateBoundingBox(self, event):
        boundary = self._boundary_curve()
        if boundary is not None:
            event.IncludeBoundingBox(boundary.GetBoundingBox(True))
        if self.preview_data is None:
            return
        for floor_record in self.preview_data["floors"]:
            for record, _kind, _index_key, _display_name in _iter_floor_records(
                floor_record
            ):
                event.IncludeBoundingBox(record["brep"].GetBoundingBox(True))

    def PostDrawObjects(self, event):
        boundary = self._boundary_curve()
        if boundary is not None:
            event.Display.DrawCurve(boundary, PREVIEW_BOUNDARY_COLOR, 1)

        if self.preview_data is None:
            return

        for floor_record in self.preview_data["floors"]:
            for record, kind, _index_key, _display_name in _iter_floor_records(
                floor_record
            ):
                collision = kind == "Flight" and record.get("collision")
                self._draw_brep_edges(
                    event.Display,
                    record["brep"],
                    PREVIEW_COLLISION_COLOR if collision else PREVIEW_NORMAL_COLOR,
                    3 if collision else 1,
                )

    def _draw_brep_edges(self, display, brep, color, thickness):
        try:
            display.DrawBrepWires(brep, color, thickness)
        except Exception:
            pass


# =============================================================================
# Settings validation and automatic adjustment
# =============================================================================

def _enforce_minimum(settings, field_name, minimum, label, adjustments):
    current = getattr(settings, field_name)
    if current >= minimum:
        return
    setattr(settings, field_name, minimum)
    adjustments.append(
        u"{0}: {1} → {2}".format(
            label,
            _format_number(current),
            _format_number(minimum),
        )
    )


def _validate_and_adjust(rect, raw_settings, landing_was_unset=False):
    settings = raw_settings.copy()
    adjustments = []

    min_stair_width = _mm_to_doc(MIN_STAIR_WIDTH_MM)
    min_landing = _mm_to_doc(MIN_LANDING_DEPTH_MM)
    min_tread = _mm_to_doc(MIN_TREAD_DEPTH_MM)
    min_slab = _mm_to_doc(MIN_SLAB_THICKNESS_MM)

    flight_count = settings.turn_count + 1

    if settings.riser_basis == BASIS_TARGET_RISER:
        calculated = _round_half_up_positive(
            settings.floor_height / settings.target_riser / float(flight_count)
        )
        settings.segment_risers = max(MIN_SEGMENT_RISER_COUNT, calculated)
    else:
        settings.segment_risers = max(
            MIN_SEGMENT_RISER_COUNT, int(settings.segment_risers)
        )

    if settings.width_basis == BASIS_GAP:
        settings.center_gap = max(_mm_to_doc(MIN_CENTER_GAP_MM), settings.center_gap)
        settings.stair_width = (rect.width - settings.center_gap) * 0.5
        if settings.stair_width < min_stair_width:
            raise GeometryConstraintError(
                u"현재 중앙 간격을 유지하면 계단 폭이 최소 기준 {0}보다 작아집니다.".format(
                    _format_number(min_stair_width)
                )
            )
    else:
        _enforce_minimum(
            settings,
            "stair_width",
            min_stair_width,
            u"최소 계단 폭 확보",
            adjustments,
        )

        settings.center_gap = rect.width - 2.0 * settings.stair_width
        if settings.center_gap < 0.0:
            old_gap = settings.center_gap
            settings.center_gap = 0.0
            maximum_width = rect.width * 0.5
            if settings.stair_width > maximum_width:
                old_width = settings.stair_width
                settings.stair_width = maximum_width
                adjustments.append(
                    u"직사각형 폭에 맞춰 계단 폭 조정: {0} → {1}".format(
                        _format_number(old_width), _format_number(settings.stair_width)
                    )
                )
            if old_gap < 0.0:
                adjustments.append(u"중앙 간격을 0으로 조정했습니다.")

        if settings.stair_width < min_stair_width:
            raise GeometryConstraintError(
                u"직사각형 전체 폭이 두 개의 최소 계단 폭을 수용하지 못합니다."
            )

    if landing_was_unset or settings.landing_depth is None:
        settings.landing_depth = settings.stair_width

    _enforce_minimum(
        settings,
        "landing_depth",
        min_landing,
        u"최소 계단참 깊이 확보",
        adjustments,
    )
    _enforce_minimum(
        settings,
        "slab_thickness",
        min_slab,
        u"최소 슬래브 두께 확보",
        adjustments,
    )

    tread_count = settings.segment_risers - 1
    minimum_run = min_tread * tread_count
    maximum_landing = (rect.length - minimum_run) * 0.5

    if maximum_landing < min_landing:
        raise GeometryConstraintError(
            u"직사각형 길이가 최소 계단참 깊이와 최소 디딤판 깊이를 동시에 확보하지 못합니다."
        )

    minimum_extension_landing = rect.length / float(tread_count + 2)
    if minimum_extension_landing > maximum_landing + _model_tolerance():
        raise GeometryConstraintError(
            u"계단참 안에서 하부 경사선을 연장할 공간이 부족합니다."
        )
    _enforce_minimum(
        settings,
        "landing_depth",
        minimum_extension_landing,
        u"하부 경사 연장 공간 확보",
        adjustments,
    )

    if settings.landing_depth > maximum_landing:
        old_value = settings.landing_depth
        settings.landing_depth = maximum_landing
        adjustments.append(
            u"최소 디딤판 깊이 확보를 위해 계단참 깊이 조정: {0} → {1}".format(
                _format_number(old_value), _format_number(settings.landing_depth)
            )
        )

    run_length = rect.length - 2.0 * settings.landing_depth
    if run_length <= 0.0:
        raise GeometryConstraintError(u"계단 진행 길이가 0 이하입니다.")
    tread_depth = run_length / float(tread_count)
    if tread_depth + _model_tolerance() < min_tread:
        raise GeometryConstraintError(
            u"디딤판 깊이가 최소 기준 {0}보다 작습니다.".format(
                _format_number(min_tread)
            )
        )

    # Exact width equation is enforced after every adjustment.
    settings.center_gap = rect.width - 2.0 * settings.stair_width
    if settings.center_gap < -_model_tolerance():
        raise GeometryConstraintError(u"계단 폭과 중앙 간격이 직사각형 폭을 초과합니다.")
    if settings.center_gap < 0.0:
        settings.center_gap = 0.0

    return settings, adjustments


# =============================================================================
# Eto dialog
# =============================================================================

class CoreStairDialog(forms.Dialog[bool]):
    def __init__(self, rectangle_source, settings, has_sticky, conduit):
        forms.Dialog[bool].__init__(self)
        try:
            EtoExtensions.UseRhinoStyle(self)
        except Exception:
            pass

        self.Title = u"Core Stair"
        self.Padding = drawing.Padding(12)
        self.Resizable = True
        self.ClientSize = drawing.Size(650, 760)

        self.rectangle_source = rectangle_source
        self.settings = settings.copy()
        self.has_sticky = bool(has_sticky)
        self.conduit = conduit
        self.preview_data = None
        self.result_settings = None
        self.result_preview_data = None

        self._initial_preview_done = False
        self._suppress_text_events = False
        self._last_width_edit = None
        self._last_riser_edit = None
        self._shown_adjustment_keys = set()
        self._confirmed_large_floor_count = None
        self._last_valid_texts = {}

        self.unit_text = _unit_label()

        self._build_controls()
        self._build_layout()
        self._bind_events()
        self._write_settings_to_controls(self.settings)
        self.Shown += self._on_shown

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _text_box(self, width=120):
        box = forms.TextBox()
        box.Width = width
        return box

    def _basis_label(self):
        label = forms.Label(Text=u"자동")
        label.Width = 42
        return label

    def _unit_widget(self):
        return forms.Label(Text=self.unit_text)

    def _build_controls(self):
        self.reselect_button = forms.Button(Text=u"직사각형 다시 지정")
        self.rectangle_info_label = forms.Label()

        for field_key in TEXT_FIELD_KEYS:
            setattr(self, field_key + "_box", self._text_box())

        self.pick_height_button = forms.Button(Text=u"두 점으로 층고 지정")
        self.landing_equal_button = forms.Button(Text=u"계단 폭과 같게")

        for field_key in (
            "target_riser",
            "segment_risers",
            "stair_width",
            "center_gap",
        ):
            setattr(self, field_key + "_basis_label", self._basis_label())

        self.turn_combo = forms.ComboBox()
        self.turn_combo.DataStore = [u"1회", u"2회", u"3회"]
        self.turn_combo.Width = 120

        self.floor_landing_check = forms.CheckBox(Text=u"층 계단참 생성")
        self.join_check = forms.CheckBox(Text=u"층별 계단 솔리드 결합")

        self.rotate_button = forms.Button(Text=u"90° 방향 전환")
        self.start_button = forms.Button()
        self.left_right_button = forms.Button()
        self.z_button = forms.Button()

        for field_key, _label, _data_key, _has_unit in RESULT_SPECS:
            setattr(self, "result_" + field_key, forms.Label())
        self.status_label = forms.Label()
        self.status_label.Height = 52

        self.preview_button = forms.Button(Text=u"미리보기 갱신")
        self.create_button = forms.Button(Text=u"생성")
        self.cancel_button = forms.Button(Text=u"취소")
        self.AbortButton = self.cancel_button

    def _group(self, title, content):
        group = forms.GroupBox(Text=title)
        group.Padding = drawing.Padding(10)
        group.Content = content
        return group

    def _build_layout(self):
        input_layout = forms.DynamicLayout()
        input_layout.Spacing = drawing.Size(6, 6)
        input_layout.AddRow(self.rectangle_info_label)
        input_layout.AddRow(self.reselect_button, None)

        basic_layout = forms.DynamicLayout()
        basic_layout.Spacing = drawing.Size(6, 6)
        basic_layout.AddRow(
            forms.Label(Text=u"층고"),
            self.floor_height_box,
            self._unit_widget(),
            self.pick_height_button,
            None,
        )
        basic_layout.AddRow(forms.Label(Text=u"층수"), self.floor_count_box, None)
        basic_layout.AddRow(
            forms.Label(Text=u"목표 단높이"),
            self.target_riser_box,
            self._unit_widget(),
            self.target_riser_basis_label,
            None,
        )
        basic_layout.AddRow(
            forms.Label(Text=u"구간 챌판 수"),
            self.segment_risers_box,
            self.segment_risers_basis_label,
            None,
        )

        plan_layout = forms.DynamicLayout()
        plan_layout.Spacing = drawing.Size(6, 6)
        plan_layout.AddRow(
            forms.Label(Text=u"계단 폭"),
            self.stair_width_box,
            self._unit_widget(),
            self.stair_width_basis_label,
            None,
        )
        plan_layout.AddRow(
            forms.Label(Text=u"중앙 간격"),
            self.center_gap_box,
            self._unit_widget(),
            self.center_gap_basis_label,
            None,
        )
        plan_layout.AddRow(
            forms.Label(Text=u"계단참 깊이"),
            self.landing_depth_box,
            self._unit_widget(),
            self.landing_equal_button,
            None,
        )
        plan_layout.AddRow(
            forms.Label(Text=u"슬래브 두께"),
            self.slab_thickness_box,
            self._unit_widget(),
            None,
        )

        option_layout = forms.DynamicLayout()
        option_layout.Spacing = drawing.Size(6, 6)
        option_layout.AddRow(forms.Label(Text=u"방향 전환 횟수"), self.turn_combo, None)
        option_layout.AddRow(self.floor_landing_check)
        option_layout.AddRow(self.join_check)

        direction_layout = forms.DynamicLayout()
        direction_layout.Spacing = drawing.Size(6, 6)
        direction_layout.AddRow(self.rotate_button, self.start_button)
        direction_layout.AddRow(self.left_right_button, self.z_button)

        result_layout = forms.DynamicLayout()
        result_layout.Spacing = drawing.Size(4, 4)
        for field_key, _label, _data_key, _has_unit in RESULT_SPECS:
            result_layout.AddRow(getattr(self, "result_" + field_key))
        result_layout.AddRow(self.status_label)

        main = forms.DynamicLayout()
        main.Spacing = drawing.Size(8, 8)
        main.AddRow(self._group(u"입력 직사각형", input_layout))
        main.AddRow(self._group(u"기본 설정", basic_layout))
        main.AddRow(self._group(u"평면 및 슬래브", plan_layout))
        main.AddRow(self._group(u"생성 옵션", option_layout))
        main.AddRow(self._group(u"방향", direction_layout))
        main.AddRow(self._group(u"계산 결과", result_layout))
        main.AddRow(None, self.preview_button, self.create_button, self.cancel_button)

        scroll = forms.Scrollable()
        scroll.Content = main
        scroll.ExpandContentWidth = True
        self.Content = scroll

    def _bind_events(self):
        self._boxes = dict(
            (field_key, getattr(self, field_key + "_box"))
            for field_key in TEXT_FIELD_KEYS
        )

        for field_key in TEXT_FIELD_KEYS:
            box = self._boxes[field_key]
            box.TextChanged += self._make_text_changed_handler(field_key)
            box.KeyDown += self._on_text_key_down

        self.reselect_button.Click += self._on_reselect
        self.pick_height_button.Click += self._on_pick_height
        self.landing_equal_button.Click += self._on_landing_equal
        self.turn_combo.SelectedIndexChanged += self._on_immediate_option_changed
        self.floor_landing_check.CheckedChanged += self._on_immediate_option_changed
        self.join_check.CheckedChanged += self._on_immediate_option_changed

        self.rotate_button.Click += self._on_rotate
        self.start_button.Click += self._on_start_flip
        self.left_right_button.Click += self._on_left_right_flip
        self.z_button.Click += self._on_z_flip

        self.preview_button.Click += self._on_preview
        self.create_button.Click += self._on_create
        self.cancel_button.Click += self._on_cancel

    def _make_text_changed_handler(self, field_key):
        def handler(sender, event):
            if self._suppress_text_events:
                return
            self._shown_adjustment_keys.clear()
            if field_key == "floor_count":
                self._confirmed_large_floor_count = None
            if field_key in ("stair_width", "center_gap"):
                self._last_width_edit = field_key
            if field_key in ("target_riser", "segment_risers"):
                self._last_riser_edit = field_key
        return handler

    # ------------------------------------------------------------------
    # Control synchronization
    # ------------------------------------------------------------------

    def _set_box_text(self, field_key, text):
        was_suppressed = self._suppress_text_events
        self._suppress_text_events = True
        try:
            self._boxes[field_key].Text = unicode(text)
        finally:
            self._suppress_text_events = was_suppressed

    def _write_settings_to_controls(self, settings):
        values = {
            "floor_height": _format_number(settings.floor_height),
            "floor_count": _format_integer(settings.floor_count),
            "target_riser": _format_number(settings.target_riser),
            "segment_risers": _format_integer(
                max(settings.segment_risers, MIN_SEGMENT_RISER_COUNT)
            ),
            "stair_width": _format_number(max(settings.stair_width, 0.0)),
            "center_gap": _format_number(max(settings.center_gap, 0.0)),
            "landing_depth": _format_number(
                settings.landing_depth
                if settings.landing_depth is not None
                else 0.0
            ),
            "slab_thickness": _format_number(settings.slab_thickness),
        }

        was_suppressed = self._suppress_text_events
        self._suppress_text_events = True
        try:
            for field_key in TEXT_FIELD_KEYS:
                self._boxes[field_key].Text = unicode(values[field_key])
            self.turn_combo.SelectedIndex = max(0, min(2, settings.turn_count - 1))
            self.floor_landing_check.Checked = settings.include_floor_landings
            self.join_check.Checked = settings.join_per_floor
        finally:
            self._suppress_text_events = was_suppressed

        self._last_valid_texts = dict(
            (field_key, self._boxes[field_key].Text)
            for field_key in TEXT_FIELD_KEYS
        )
        self._update_basis_labels()
        self._update_rectangle_label()
        self._update_direction_buttons()

    def _update_basis_labels(self):
        self.stair_width_basis_label.Text = (
            u"기준" if self.settings.width_basis == BASIS_WIDTH else u"자동"
        )
        self.center_gap_basis_label.Text = (
            u"기준" if self.settings.width_basis == BASIS_GAP else u"자동"
        )
        self.target_riser_basis_label.Text = (
            u"기준" if self.settings.riser_basis == BASIS_TARGET_RISER else u"자동"
        )
        self.segment_risers_basis_label.Text = (
            u"기준" if self.settings.riser_basis == BASIS_SEGMENT_RISERS else u"자동"
        )

    def _update_rectangle_label(self):
        rect = self.rectangle_source.rect_info.oriented(self.settings.rotated_90)
        source_text = u"새로 그린 직사각형" if self.rectangle_source.is_new else u"선택한 직사각형"
        self.rectangle_info_label.Text = (
            u"{0}  |  길이 {1} {3}  |  폭 {2} {3}".format(
                source_text,
                _format_number(rect.length),
                _format_number(rect.width),
                self.unit_text,
            )
        )

    def _update_direction_buttons(self):
        self.rotate_button.Text = (
            u"90° 방향 전환: 적용" if self.settings.rotated_90 else u"90° 방향 전환: 기본"
        )
        self.start_button.Text = (
            u"시작 위치: 먼쪽" if self.settings.start_far else u"시작 위치: 가까운쪽"
        )
        self.left_right_button.Text = (
            u"첫 Flight: 오른쪽" if self.settings.start_right else u"첫 Flight: 왼쪽"
        )
        self.z_button.Text = (
            u"Z 방향: -Z" if self.settings.z_flipped else u"Z 방향: +Z"
        )

    def _clear_results(self, message):
        for field_key, label, _data_key, _has_unit in RESULT_SPECS:
            getattr(self, "result_" + field_key).Text = u"{0}: -".format(label)
        self.status_label.Text = unicode(message)

    def _update_results(self, preview_data):
        for field_key, label, data_key, has_unit in RESULT_SPECS:
            value = preview_data[data_key]
            if has_unit:
                value = u"{0} {1}".format(_format_number(value), self.unit_text)
            getattr(self, "result_" + field_key).Text = u"{0}: {1}".format(
                label, value
            )

        if preview_data["collisions"]:
            self.status_label.Text = u"오류: 동일 층의 비인접 Flight가 충돌합니다."
        elif preview_data["collision_check_failures"]:
            self.status_label.Text = u"일부 충돌 검사를 완료하지 못했습니다. 생성은 허용됩니다."
        else:
            self.status_label.Text = u"정상"

    # ------------------------------------------------------------------
    # Parsing
    # ------------------------------------------------------------------

    def _restore_invalid_field(self, field_key):
        previous = self._last_valid_texts.get(field_key)
        if previous is not None:
            self._set_box_text(field_key, previous)

    def _parse_float(self, field_key, label, allow_zero=False):
        text = self._boxes[field_key].Text.strip()
        try:
            value = float(text)
        except Exception:
            raise NumericInputError(field_key, u"{0}은 숫자로 입력해야 합니다.".format(label))
        if value < 0.0 or (not allow_zero and value == 0.0):
            message = u"{0}은 0 이상이어야 합니다." if allow_zero else u"{0}은 0보다 커야 합니다."
            raise NumericInputError(field_key, message.format(label))
        return value

    def _parse_integer(self, field_key, label, minimum):
        text = self._boxes[field_key].Text.strip()
        try:
            raw = float(text)
        except Exception:
            raise NumericInputError(field_key, u"{0}은 숫자로 입력해야 합니다.".format(label))
        rounded = _round_half_up_positive(raw)
        if rounded < int(minimum):
            raise NumericInputError(
                field_key,
                u"{0}은 {1} 이상이어야 합니다.".format(label, minimum),
            )
        return rounded

    def _read_raw_settings(self):
        result = self.settings.copy()

        for field_key, label, value_type, limit in INPUT_SPECS:
            if value_type == "integer":
                value = self._parse_integer(field_key, label, limit)
            else:
                value = self._parse_float(field_key, label, limit)
            setattr(result, field_key, value)

        if self._last_width_edit == "stair_width":
            result.width_basis = BASIS_WIDTH
        elif self._last_width_edit == "center_gap":
            result.width_basis = BASIS_GAP

        if self._last_riser_edit == "target_riser":
            result.riser_basis = BASIS_TARGET_RISER
        elif self._last_riser_edit == "segment_risers":
            result.riser_basis = BASIS_SEGMENT_RISERS

        result.turn_count = max(1, min(3, self.turn_combo.SelectedIndex + 1))
        result.include_floor_landings = bool(self.floor_landing_check.Checked)
        result.join_per_floor = bool(self.join_check.Checked)

        if result.floor_count > 20 and result.floor_count != self._confirmed_large_floor_count:
            accepted = _ask_yes_no(
                self,
                u"{0}개 층 전체를 미리보기하고 생성합니다. 계속하시겠습니까?".format(
                    result.floor_count
                ),
                u"CoreStair 고층 생성 확인",
            )
            if not accepted:
                raise NumericInputError(
                    "floor_count",
                    u"층수 입력이 취소되었습니다.",
                )
            self._confirmed_large_floor_count = result.floor_count

        return result

    # ------------------------------------------------------------------
    # Preview application
    # ------------------------------------------------------------------

    def _show_adjustments_once(self, adjustments):
        if not adjustments:
            return
        key = tuple(adjustments)
        if key in self._shown_adjustment_keys:
            return
        self._shown_adjustment_keys.add(key)
        _show_message(
            u"자동 보정 내용\n\n" + u"\n".join([u"• " + item for item in adjustments]),
            u"CoreStair 자동 보정",
        )

    def _apply_current_inputs(self, show_numeric_errors, show_adjustments, create_attempt=False):
        try:
            raw_settings = self._read_raw_settings()
        except NumericInputError as error:
            self._restore_invalid_field(error.field_key)
            if show_numeric_errors:
                _show_message(error.message, u"CoreStair 입력 오류")
            return False, False

        rect = self.rectangle_source.rect_info.oriented(raw_settings.rotated_90)

        try:
            adjusted_settings, adjustments = _validate_and_adjust(
                rect,
                raw_settings,
                landing_was_unset=False,
            )
            preview_data = _build_core_stair(rect, adjusted_settings)
        except GeometryConstraintError as error:
            self.preview_data = None
            self.conduit.clear_stair_preview()
            self._clear_results(u"오류: {0}".format(error))
            if create_attempt:
                _show_message(unicode(error), u"CoreStair 생성 불가")
            return False, False
        except Exception as error:
            self.preview_data = None
            self.conduit.clear_stair_preview()
            self._clear_results(u"형상 계산 오류: {0}".format(error))
            if show_numeric_errors or create_attempt:
                _show_message(unicode(error), u"CoreStair 미리보기 오류")
            return False, False

        self.settings = adjusted_settings
        self.preview_data = preview_data
        self._last_width_edit = None
        self._last_riser_edit = None
        self._write_settings_to_controls(adjusted_settings)
        self.conduit.update_preview(preview_data)
        self._update_results(preview_data)

        if adjustments:
            if show_adjustments:
                self._show_adjustments_once(adjustments)
            if create_attempt:
                return True, True
        return True, False

    # ------------------------------------------------------------------
    # Events
    # ------------------------------------------------------------------

    def _on_shown(self, sender, event):
        if self._initial_preview_done:
            return
        self._initial_preview_done = True

        # First command execution without sticky: calculate width from 100 mm gap,
        # then use that stair width as the initial landing depth.
        rect = self.rectangle_source.rect_info.oriented(self.settings.rotated_90)
        if self.settings.width_basis == BASIS_GAP:
            self.settings.stair_width = (rect.width - self.settings.center_gap) * 0.5
        if not self.has_sticky or self.settings.landing_depth is None:
            self.settings.landing_depth = self.settings.stair_width

        # Initialize segment riser display before the full calculation.
        flight_count = self.settings.turn_count + 1
        if self.settings.riser_basis == BASIS_TARGET_RISER:
            self.settings.segment_risers = max(
                MIN_SEGMENT_RISER_COUNT,
                _round_half_up_positive(
                    self.settings.floor_height
                    / self.settings.target_riser
                    / float(flight_count)
                ),
            )

        self._write_settings_to_controls(self.settings)
        self._apply_current_inputs(True, True, False)

    def _on_text_key_down(self, sender, event):
        try:
            is_enter = event.Key == forms.Keys.Enter
        except Exception:
            is_enter = False
        if not is_enter:
            return
        try:
            event.Handled = True
        except Exception:
            pass
        self._apply_current_inputs(True, True, False)

    def _on_preview(self, sender, event):
        self._apply_current_inputs(True, True, False)

    def _on_immediate_option_changed(self, sender, event):
        if self._suppress_text_events or not self._initial_preview_done:
            return
        self._shown_adjustment_keys.clear()
        self._apply_current_inputs(True, True, False)

    def _toggle_direction(self, field_name, clear_adjustments=False):
        setattr(self.settings, field_name, not getattr(self.settings, field_name))
        if clear_adjustments:
            self._shown_adjustment_keys.clear()
        self._update_direction_buttons()
        self._apply_current_inputs(True, True, False)

    def _on_rotate(self, sender, event):
        self._toggle_direction("rotated_90", True)

    def _on_start_flip(self, sender, event):
        self._toggle_direction("start_far")

    def _on_left_right_flip(self, sender, event):
        self._toggle_direction("start_right")

    def _on_z_flip(self, sender, event):
        self._toggle_direction("z_flipped")

    def _on_landing_equal(self, sender, event):
        try:
            stair_width = float(self.stair_width_box.Text)
        except Exception:
            self._restore_invalid_field("stair_width")
            _show_message(u"계단 폭을 먼저 올바르게 입력하세요.", u"CoreStair 입력 오류")
            return
        self._set_box_text("landing_depth", _format_number(stair_width))
        self._shown_adjustment_keys.clear()
        self._apply_current_inputs(True, True, False)

    def _on_pick_height(self, sender, event):
        self.Visible = False
        try:
            getter_0 = ric.GetPoint()
            getter_0.SetCommandPrompt(u"층고 기준 첫 번째 점을 지정하세요")
            getter_0.Get()
            if getter_0.CommandResult() != Rhino.Commands.Result.Success:
                return
            point_0 = getter_0.Point()

            getter_1 = ric.GetPoint()
            getter_1.SetCommandPrompt(u"층고 기준 두 번째 점을 지정하세요")
            getter_1.SetBasePoint(point_0, True)
            getter_1.DrawLineFromPoint(point_0, True)
            getter_1.Get()
            if getter_1.CommandResult() != Rhino.Commands.Result.Success:
                return
            point_1 = getter_1.Point()
            height = abs(point_1.Z - point_0.Z)
            if height <= _model_tolerance():
                _show_message(u"두 점의 Z 높이 차이가 너무 작습니다.", u"CoreStair 층고 입력")
                return
            self._set_box_text("floor_height", _format_number(height))
            self._shown_adjustment_keys.clear()
        finally:
            self.Visible = True
            try:
                self.BringToFront()
            except Exception:
                pass
        self._apply_current_inputs(True, True, False)

    def _on_reselect(self, sender, event):
        if not self._apply_current_inputs(True, True, False)[0]:
            return

        previous_source = self.rectangle_source
        previous_settings = self.settings.copy()
        previous_preview = self.preview_data

        self.Visible = False
        new_source = None
        try:
            new_source = request_rectangle_source()
        finally:
            self.Visible = True
            try:
                self.BringToFront()
            except Exception:
                pass

        if new_source is None:
            self.rectangle_source = previous_source
            self.settings = previous_settings
            self.preview_data = previous_preview
            self.conduit.update_rectangle(previous_source)
            self.conduit.update_preview(previous_preview)
            self._write_settings_to_controls(previous_settings)
            self._update_results(previous_preview)
            return

        self.rectangle_source = new_source
        self.settings = previous_settings
        self._shown_adjustment_keys.clear()
        self.conduit.update_rectangle(new_source)
        self._update_rectangle_label()
        self._apply_current_inputs(True, True, False)

    def _collision_message(self, collisions):
        lines = []
        for floor_number, flight_a, flight_b in collisions:
            lines.append(
                u"{0:02d}층: Flight {1} ↔ Flight {2}".format(
                    floor_number, flight_a, flight_b
                )
            )
        return u"동일 층의 비인접 Flight 충돌이 확인되었습니다.\n\n" + u"\n".join(lines)

    def _on_create(self, sender, event):
        success, adjusted_during_create = self._apply_current_inputs(
            True, True, True
        )
        if not success:
            return
        if adjusted_during_create:
            # The user must inspect the updated preview and press Create again.
            return
        if self.preview_data.get("collisions"):
            _show_message(
                self._collision_message(self.preview_data["collisions"]),
                u"CoreStair 생성 차단",
            )
            return

        self.result_settings = self.settings.copy()
        self.result_preview_data = self.preview_data
        self.conduit.clear_stair_preview()
        self.Close(True)

    def _on_cancel(self, sender, event):
        self.conduit.clear_stair_preview()
        self.Close(False)


# =============================================================================
# Semi-modal runner
# =============================================================================

def show_semi_modal(dialog):
    try:
        parent = RhinoEtoApp.MainWindowForDocument(sc.doc)
    except Exception:
        parent = RhinoEtoApp.MainWindow
    return EtoExtensions.ShowSemiModal(dialog, sc.doc, parent)


def request_settings(rectangle_source):
    settings, has_sticky = _load_last_settings()
    conduit = CoreStairPreviewConduit(rectangle_source)
    conduit.Enabled = True
    sc.doc.Views.Redraw()
    try:
        dialog = CoreStairDialog(
            rectangle_source,
            settings,
            has_sticky,
            conduit,
        )
        accepted = bool(show_semi_modal(dialog))
        if not accepted:
            return None, None, None
        return dialog.result_settings, dialog.result_preview_data, dialog.rectangle_source
    finally:
        conduit.Enabled = False
        sc.doc.Views.Redraw()


# =============================================================================
# Document output
# =============================================================================

def _active_layer_attributes(name):
    attributes = rdo.ObjectAttributes()
    attributes.LayerIndex = sc.doc.Layers.CurrentLayerIndex
    attributes.Name = name
    try:
        attributes.ColorSource = rdo.ObjectColorSource.ColorFromLayer
    except Exception:
        pass
    return attributes


def _unique_group_name(base_name):
    name = base_name
    suffix = 2
    while True:
        try:
            existing = sc.doc.Groups.FindName(name)
        except Exception:
            existing = None
        if existing is None:
            return name
        name = "{0}_{1:02d}".format(base_name, suffix)
        suffix += 1


def _add_group(name, object_ids):
    valid_ids = [object_id for object_id in object_ids if object_id != System.Guid.Empty]
    if not valid_ids:
        return -1
    group_name = _unique_group_name(name)
    group_index = sc.doc.Groups.Add(group_name)
    if group_index >= 0:
        sc.doc.Groups.AddToGroup(group_index, valid_ids)
    return group_index


def _prepare_brep_for_boolean(brep):
    if brep is None:
        return None

    try:
        prepared = brep.DuplicateBrep()
        if prepared is None:
            return None

        # AddBrep normally performs these repairs before Rhino commands see
        # the geometry. Do the same for the in-memory Boolean inputs.
        prepared.Faces.SplitKinkyFaces(_model_angle_tolerance(), True)

        if (
            not prepared.IsValid
            or not prepared.IsSolid
            or not prepared.IsManifold
        ):
            return None

        if prepared.SolidOrientation == rg.BrepSolidOrientation.Inward:
            prepared.Flip()

        if prepared.SolidOrientation != rg.BrepSolidOrientation.Outward:
            return None
        if (
            not prepared.IsValid
            or not prepared.IsSolid
            or not prepared.IsManifold
        ):
            return None
        return prepared
    except Exception:
        return None


def _bounding_box_contains(outer_box, inner_box, tolerance):
    if not outer_box.IsValid or not inner_box.IsValid:
        return False
    return (
        outer_box.Min.X <= inner_box.Min.X + tolerance
        and outer_box.Min.Y <= inner_box.Min.Y + tolerance
        and outer_box.Min.Z <= inner_box.Min.Z + tolerance
        and outer_box.Max.X >= inner_box.Max.X - tolerance
        and outer_box.Max.Y >= inner_box.Max.Y - tolerance
        and outer_box.Max.Z >= inner_box.Max.Z - tolerance
    )


def _point_inside_solid(brep, tolerance):
    try:
        success, point = brep.GetPointInside(tolerance)
        if success:
            return point
    except Exception:
        pass

    # The mass centroid is a useful fallback for convex inputs and boxes.
    try:
        properties = rg.VolumeMassProperties.Compute(brep)
        if properties is not None:
            point = properties.Centroid
            if brep.IsPointInside(point, tolerance, False):
                return point
    except Exception:
        pass
    return None


def _boolean_result_contains_inputs(result, inputs, tolerance):
    try:
        result_box = result.GetBoundingBox(True)
        for brep in inputs:
            if not _bounding_box_contains(
                result_box, brep.GetBoundingBox(True), tolerance
            ):
                return False

            point = _point_inside_solid(brep, tolerance)
            if point is None or not result.IsPointInside(
                point, tolerance, False
            ):
                return False
        return True
    except Exception:
        return False


def _try_union_floor(floor_record):
    raw_geometry = [
        record["brep"]
        for record, _kind, _index_key, _display_name in _iter_floor_records(
            floor_record
        )
    ]

    if not raw_geometry:
        return None

    geometry = []
    for brep in raw_geometry:
        prepared = _prepare_brep_for_boolean(brep)
        if prepared is None:
            return None
        geometry.append(prepared)

    tolerance = _model_tolerance()
    try:
        union = rg.Brep.CreateBooleanUnion(geometry, tolerance, True)
    except Exception:
        union = None

    if not union or len(union) != 1:
        return None

    result = _prepare_brep_for_boolean(union[0])
    if (
        result is not None
        and _boolean_result_contains_inputs(result, geometry, tolerance)
    ):
        return result

    _write_line(
        u"CoreStair: {0:02d}층 Boolean Union 부분 결과를 거부하고 "
        u"개별 솔리드로 전환합니다.".format(floor_record["floor"])
    )
    return None


def _add_boundary_if_new(rectangle_source):
    if not rectangle_source.is_new or rectangle_source.source_curve is None:
        return System.Guid.Empty
    attributes = _active_layer_attributes("CoreStair_Boundary")
    return sc.doc.Objects.AddCurve(rectangle_source.source_curve, attributes)


def _delete_objects(object_ids):
    for object_id in object_ids:
        try:
            sc.doc.Objects.Delete(object_id, True)
        except Exception:
            pass


def _add_floor_individual(floor_record):
    floor_number = floor_record["floor"]
    floor_object_ids = []
    try:
        for record, kind, index_key, display_name in _iter_floor_records(floor_record):
            if _safe_escape_pressed():
                raise UserGenerationCancel(
                    u"사용자가 {0:02d}층 {1} 생성 중 작업을 중단했습니다.".format(
                        floor_number, display_name
                    )
                )
            name = "CoreStair_F{0:02d}_{1}_{2:02d}".format(
                floor_number, kind, record[index_key]
            )
            object_id = sc.doc.Objects.AddBrep(
                record["brep"], _active_layer_attributes(name)
            )
            if object_id == System.Guid.Empty:
                raise CoreStairError(u"{0} 객체 추가에 실패했습니다.".format(name))
            floor_object_ids.append(object_id)
        return floor_object_ids
    except Exception:
        # A floor is committed only after every object on that floor is added.
        # Objects from the currently failing floor are removed; completed floors remain.
        _delete_objects(floor_object_ids)
        raise


def add_core_stair_to_document(preview_data, settings, rectangle_source):
    undo_record = sc.doc.BeginUndoRecord("Create CoreStair")
    stair_object_ids = []
    boundary_id = System.Guid.Empty
    union_failed_floors = []
    completed_floors = []
    incomplete = False
    failure_message = None
    cancelled_by_user = False

    try:
        boundary_id = _add_boundary_if_new(rectangle_source)
        if rectangle_source.is_new and boundary_id == System.Guid.Empty:
            raise CoreStairError(u"새로 그린 기준 직사각형을 문서에 추가하지 못했습니다.")

        for floor_record in preview_data["floors"]:
            floor_number = floor_record["floor"]
            if _safe_escape_pressed():
                cancelled_by_user = True
                raise UserGenerationCancel(
                    u"사용자가 {0:02d}층 생성 전에 작업을 중단했습니다.".format(floor_number)
                )

            floor_object_ids = []
            try:
                if settings.join_per_floor:
                    union_brep = _try_union_floor(floor_record)
                    if union_brep is not None:
                        if _safe_escape_pressed():
                            cancelled_by_user = True
                            raise UserGenerationCancel(
                                u"사용자가 {0:02d}층 객체 추가 전에 작업을 중단했습니다.".format(
                                    floor_number
                                )
                            )
                        name = "CoreStair_Floor_{0:02d}".format(floor_number)
                        object_id = sc.doc.Objects.AddBrep(
                            union_brep, _active_layer_attributes(name)
                        )
                        if object_id == System.Guid.Empty:
                            raise CoreStairError(u"{0} 객체 추가에 실패했습니다.".format(name))
                        floor_object_ids.append(object_id)
                    else:
                        union_failed_floors.append(floor_number)
                        floor_object_ids = _add_floor_individual(floor_record)
                else:
                    floor_object_ids = _add_floor_individual(floor_record)
            except Exception as error:
                if isinstance(error, UserGenerationCancel):
                    cancelled_by_user = True
                _delete_objects(floor_object_ids)
                raise

            stair_object_ids.extend(floor_object_ids)
            completed_floors.append(floor_number)

    except Exception as error:
        incomplete = True
        failure_message = unicode(error)
    finally:
        try:
            if stair_object_ids:
                _add_group(
                    "CoreStair_Incomplete" if incomplete else "CoreStair",
                    stair_object_ids,
                )
        finally:
            sc.doc.EndUndoRecord(undo_record)

    sc.doc.Objects.UnselectAll()
    sc.doc.Views.Redraw()

    return {
        "stair_object_ids": stair_object_ids,
        "boundary_id": boundary_id,
        "union_failed_floors": union_failed_floors,
        "completed_floors": completed_floors,
        "incomplete": incomplete,
        "cancelled_by_user": cancelled_by_user,
        "failure_message": failure_message,
    }


# =============================================================================
# Main command
# =============================================================================

def run_core_stair():
    source_path = globals().get("__file__", u"<editor buffer>")
    _write_line(
        u"CoreStair build {0} | source: {1}".format(BUILD_TAG, source_path)
    )

    rectangle_source = request_rectangle_source()
    if rectangle_source is None:
        return Rhino.Commands.Result.Cancel

    settings, preview_data, rectangle_source = request_settings(rectangle_source)
    if settings is None or preview_data is None or rectangle_source is None:
        return Rhino.Commands.Result.Cancel

    result = add_core_stair_to_document(
        preview_data,
        settings,
        rectangle_source,
    )

    if result["incomplete"]:
        completed_text = (
            u", ".join([u"{0:02d}".format(value) for value in result["completed_floors"]])
            if result["completed_floors"]
            else u"없음"
        )
        message = (
            u"CoreStair 생성이 완료되지 않았습니다.\n"
            u"완료된 층: {0}\n"
            u"부분 결과 그룹: CoreStair_Incomplete\n"
            u"사유: {1}"
        ).format(completed_text, result["failure_message"] or u"알 수 없는 오류")
        _write_line(message.replace("\n", " | "))
        _show_message(message, u"CoreStair 부분 생성")
        return (
            Rhino.Commands.Result.Cancel
            if result["cancelled_by_user"]
            else Rhino.Commands.Result.Failure
        )

    if not result["stair_object_ids"]:
        _show_message(u"문서에 추가된 계단 객체가 없습니다.", u"CoreStair 생성 오류")
        return Rhino.Commands.Result.Failure

    _save_last_settings(settings)

    completion = u"CoreStair 생성 완료: {0}개 층, {1}개 Flight".format(
        settings.floor_count,
        preview_data["flight_count"] * settings.floor_count,
    )
    _write_line(completion)

    if result["union_failed_floors"]:
        failed_text = u", ".join([
            u"{0:02d}".format(value) for value in result["union_failed_floors"]
        ])
        warning = (
            u"CoreStair 생성은 완료되었습니다.\n"
            u"Boolean Union 실패 층: {0}\n"
            u"해당 층은 개별 Closed Brep으로 유지되었습니다."
        ).format(failed_text)
        _write_line(warning.replace("\n", " | "))
        _show_message(warning, u"CoreStair 생성 특이사항")

    return Rhino.Commands.Result.Success


if __name__ == "__main__":
    run_core_stair()
