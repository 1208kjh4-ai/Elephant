# -*- coding: utf-8 -*-
import Rhino
import Rhino.Geometry as rg
import Rhino.Display as rd
import rhinoscriptsyntax as rs
import scriptcontext as sc
import System
import System.Drawing
from System.Drawing import Color

# 에디터 경고 방지용
EMPTY = None

# [1. 실시간 프리뷰 클래스]
class LanePreviewConduit(rd.DisplayConduit):
    def __init__(self):
        rd.DisplayConduit.__init__(self)
        self.preview_curves = []
        self.color = System.Drawing.Color.Red

    def update_curves(self, curves):
        self.preview_curves = curves

    def DrawForeground(self, e):
        if self.preview_curves:
            for crv in self.preview_curves:
                e.Display.DrawCurve(crv, self.color, 2)

# [2. 레이어 생성 함수]
def ensure_layer(layer_name):
    if not rs.IsLayer(layer_name):
        rs.AddLayer(layer_name)
    return layer_name


def bake_lane_marking_curves(curves, lane_type):
    """결과 커브에 레이어/색상 속성을 미리 적용해 빠르게 생성합니다."""
    if not curves:
        return []

    Rhino.RhinoApp.WriteLine(
        u"차선 커브 {0}개를 생성하는 중입니다...".format(
            len(curves)
        )
    )

    layer_name = (
        "점선_Lane"
        if lane_type in ["Dashed", "Guide"]
        else "실선_Lane"
    )
    document = Rhino.RhinoDoc.ActiveDoc
    ensure_layer(layer_name)
    layer_index = document.Layers.FindByFullPath(
        layer_name,
        -1
    )

    if layer_index < 0:
        Rhino.RhinoApp.WriteLine(
            u"차선 레이어를 찾거나 생성하지 못했습니다: {0}".format(
                layer_name
            )
        )
        return []

    attributes = Rhino.DocObjects.ObjectAttributes()
    attributes.LayerIndex = layer_index
    attributes.ColorSource = (
        Rhino.DocObjects.ObjectColorSource.ColorFromObject
    )
    attributes.ObjectColor = (
        System.Drawing.Color.Yellow
        if lane_type == "Center"
        else System.Drawing.Color.White
    )

    created_ids = []
    undo_record = document.BeginUndoRecord(
        "Create {0} Lane Marking".format(lane_type)
    )
    failed = False

    rs.EnableRedraw(False)

    try:
        for curve in curves:
            object_id = document.Objects.AddCurve(
                curve,
                attributes
            )

            if object_id == System.Guid.Empty:
                failed = True
                break

            created_ids.append(object_id)

    except Exception as error:
        failed = True
        Rhino.RhinoApp.WriteLine(
            u"차선 커브 생성 중 오류: {0}".format(error)
        )

    finally:
        if failed:
            for object_id in created_ids:
                document.Objects.Delete(object_id, True)
            created_ids = []

        if undo_record > 0:
            document.EndUndoRecord(undo_record)

        rs.EnableRedraw(True)
        document.Views.Redraw()

    return created_ids


# [3. 단일 커브 차선 계산]
def calculate_single_lane(curve, lane_type):    
    if curve == EMPTY: return []
    results = []
    dash_len, gap_len, offset_dist, is_solid, is_double = 0, 0, 0, False, False

    if lane_type == "Dashed": dash_len, gap_len, offset_dist = 3000, 3000, 75
    elif lane_type == "Guide": dash_len, gap_len, offset_dist = 1000, 1000, 100
    elif lane_type == "Solid": is_solid, offset_dist = True, 75
    elif lane_type == "Center": is_solid, offset_dist, is_double = True, 75, True
    elif lane_type == "Stop": is_solid, offset_dist = True, 225

    segments = []
    if is_solid:
        segments = [curve]
    else:
        total_dist = dash_len + gap_len
        t_params = curve.DivideByLength(total_dist, True)
        if t_params == EMPTY: return []
        for t_start in list(t_params):
            dist_at_t = curve.GetLength(rg.Interval(curve.Domain.T0, t_start))
            success, t_end = curve.LengthParameter(dist_at_t + dash_len)
            if success:
                sub = curve.Trim(t_start, t_end)
                if sub: segments.append(sub)

    plane = rg.Plane.WorldXY
    
    # [수정 1] 코너 스타일을 Sharp(1)로 변경하여 꺾인 부분의 교차점을 뾰족하고 깔끔하게 연장
    style = rg.CurveOffsetCornerStyle.Sharp 
    
    # [수정 2] 쪼개진 오프셋 커브들을 안전하게 하나로 합쳐주는 헬퍼 함수
    def safe_offset_join(offset_result):
        if not offset_result: return None
        if len(offset_result) == 1: return offset_result[0]
        
        joined = rg.Curve.JoinCurves(offset_result)
        return joined[0] if joined else None

    for seg in segments:
        offset_curves = []
        if is_double:
            for d in [75, 225, -75, -225]:
                raw_offset = seg.Offset(plane, d, 0.1, style)
                joined_curve = safe_offset_join(raw_offset)
                if joined_curve:
                    offset_curves.append(joined_curve)
        else:
            raw_s1 = seg.Offset(plane, offset_dist, 0.1, style)
            raw_s2 = seg.Offset(plane, -offset_dist, 0.1, style)
            
            j1 = safe_offset_join(raw_s1)
            j2 = safe_offset_join(raw_s2)
            
            if j1 and j2: 
                offset_curves.extend([j1, j2])

        # [수정 3] 안전하게 하나로 이어져 형태가 온전한 커브의 양 끝단만 닫아줌
        for i in range(0, len(offset_curves), 2):
            if i + 1 >= len(offset_curves): break # 짝이 안 맞을 경우 대비
            
            c1, c2 = offset_curves[i], offset_curves[i+1]
            l1 = rg.LineCurve(c1.PointAtStart, c2.PointAtStart)
            l2 = rg.LineCurve(c1.PointAtEnd, c2.PointAtEnd)
            joined = rg.Curve.JoinCurves([c1, l2, c2, l1])
            if joined: results.extend(joined)
            
    return results

# =============================================================================
# [4. DrawLine: 도로 차선 기준선 생성 도구]
# TTest.py에서 검증한 기능을 Lane.py 내부 기능으로 이식한 코드입니다.
# =============================================================================

EDGE_OFFSET_MM = 500.0
DEFAULT_LANE_COUNT = 4
MAX_LANE_COUNT = 100

INPUT_COLOR = Color.FromArgb(255, 170, 0)
OUTER_EDGE_COLOR = Color.FromArgb(255, 170, 0)
PREVIEW_COLOR = Color.FromArgb(0, 220, 255)


def millimeters_to_model_units(value_mm):
    """밀리미터 값을 현재 Rhino 문서 단위로 변환합니다."""
    scale = Rhino.RhinoMath.UnitScale(
        Rhino.UnitSystem.Millimeters,
        sc.doc.ModelUnitSystem
    )
    return value_mm * scale


def copy_points(points):
    return [Rhino.Geometry.Point3d(point) for point in points]


def reverse_points(points):
    result = copy_points(points)
    result.reverse()
    return result


def remove_consecutive_duplicate_points(points):
    tolerance = sc.doc.ModelAbsoluteTolerance
    cleaned = []

    for point in points:
        point = Rhino.Geometry.Point3d(point)

        if not cleaned:
            cleaned.append(point)
            continue

        if cleaned[-1].DistanceTo(point) > tolerance:
            cleaned.append(point)

    return cleaned


def polyline_length(points):
    total = 0.0

    for index in range(len(points) - 1):
        total += points[index].DistanceTo(points[index + 1])

    return total


def polyline_is_valid(points):
    if points is None:
        return False

    points = remove_consecutive_duplicate_points(points)

    if len(points) < 2:
        return False

    return polyline_length(points) > sc.doc.ModelAbsoluteTolerance


def points_to_polyline(points):
    return Rhino.Geometry.Polyline(copy_points(points))


def points_to_polyline_curve(points):
    return Rhino.Geometry.PolylineCurve(points_to_polyline(points))


def interpolate_point(point_a, point_b, parameter):
    return point_a + ((point_b - point_a) * parameter)


def draw_temporary_polylines(display, polylines, color, thickness):
    if not polylines:
        return

    for points in polylines:
        if not polyline_is_valid(points):
            continue

        curve = points_to_polyline_curve(points)
        display.DrawCurve(curve, color, thickness)


class LaneBasePreviewConduit(Rhino.Display.DisplayConduit):
    """주황색 입력/내부 기준선과 청록색 결과선을 표시합니다."""

    def __init__(
        self,
        input_polylines=None,
        outer_polylines=None,
        lane_polylines=None
    ):
        Rhino.Display.DisplayConduit.__init__(self)

        self.input_polylines = input_polylines or []
        self.outer_polylines = outer_polylines or []
        self.lane_polylines = lane_polylines or []

    def set_geometry(
        self,
        input_polylines,
        outer_polylines,
        lane_polylines
    ):
        self.input_polylines = input_polylines or []
        self.outer_polylines = outer_polylines or []
        self.lane_polylines = lane_polylines or []

    def _all_polylines(self):
        return (
            self.input_polylines
            + self.outer_polylines
            + self.lane_polylines
        )

    def CalculateBoundingBox(self, event_args):
        bbox = Rhino.Geometry.BoundingBox.Empty

        for points in self._all_polylines():
            for point in points:
                bbox.Union(point)

        if bbox.IsValid:
            event_args.IncludeBoundingBox(bbox)

    def DrawForeground(self, event_args):
        draw_temporary_polylines(
            event_args.Display,
            self.input_polylines,
            INPUT_COLOR,
            2
        )
        draw_temporary_polylines(
            event_args.Display,
            self.outer_polylines,
            OUTER_EDGE_COLOR,
            1
        )
        draw_temporary_polylines(
            event_args.Display,
            self.lane_polylines,
            PREVIEW_COLOR,
            3
        )


def get_point(prompt, fixed_polylines=None, base_point=None):
    fixed_polylines = fixed_polylines or []

    getter = Rhino.Input.Custom.GetPoint()
    getter.SetCommandPrompt(prompt)
    getter.DynamicDrawColor = INPUT_COLOR

    if base_point is not None:
        getter.SetBasePoint(base_point, True)

    def on_dynamic_draw(sender, args):
        draw_temporary_polylines(
            args.Display,
            fixed_polylines,
            INPUT_COLOR,
            2
        )

        if base_point is not None:
            args.Display.DrawLine(
                base_point,
                args.CurrentPoint,
                INPUT_COLOR,
                3
            )

    if fixed_polylines or base_point is not None:
        getter.DynamicDraw += on_dynamic_draw

    result = getter.Get()

    if result != Rhino.Input.GetResult.Point:
        return None

    return getter.Point()


def get_temporary_line(line_number, fixed_polylines=None):
    fixed_polylines = fixed_polylines or []

    start = get_point(
        u"{0}번째 횡단선의 시작점을 지정하세요".format(line_number),
        fixed_polylines=fixed_polylines
    )

    if start is None:
        return None

    end = get_point(
        u"{0}번째 횡단선의 끝점을 지정하세요".format(line_number),
        fixed_polylines=fixed_polylines,
        base_point=start
    )

    if end is None:
        return None

    points = remove_consecutive_duplicate_points([start, end])

    if not polyline_is_valid(points):
        Rhino.RhinoApp.WriteLine(u"횡단선의 길이가 너무 짧습니다.")
        return None

    return points


def get_temporary_open_polyline(label_text, fixed_polylines=None):
    fixed_polylines = fixed_polylines or []
    points = []

    while True:
        getter = Rhino.Input.Custom.GetPoint()
        getter.DynamicDrawColor = INPUT_COLOR

        if not points:
            getter.SetCommandPrompt(
                u"{0}의 시작점을 지정하세요".format(label_text)
            )
        else:
            getter.SetCommandPrompt(
                u"{0}의 다음 점을 지정하세요. Enter=완료".format(
                    label_text
                )
            )
            getter.SetBasePoint(points[-1], True)

        if len(points) >= 2:
            getter.AcceptNothing(True)

        undo_index = -1
        if points:
            undo_index = getter.AddOption("Undo")

        def on_dynamic_draw(sender, args):
            draw_temporary_polylines(
                args.Display,
                fixed_polylines,
                INPUT_COLOR,
                2
            )

            if len(points) >= 2:
                draw_temporary_polylines(
                    args.Display,
                    [points],
                    INPUT_COLOR,
                    2
                )

            if points:
                args.Display.DrawLine(
                    points[-1],
                    args.CurrentPoint,
                    INPUT_COLOR,
                    3
                )

        getter.DynamicDraw += on_dynamic_draw
        result = getter.Get()

        if result == Rhino.Input.GetResult.Point:
            point = getter.Point()

            if points and (
                points[-1].DistanceTo(point)
                <= sc.doc.ModelAbsoluteTolerance
            ):
                Rhino.RhinoApp.WriteLine(
                    u"이전 점과 너무 가까운 점은 추가할 수 없습니다."
                )
                continue

            points.append(point)
            continue

        if result == Rhino.Input.GetResult.Nothing:
            points = remove_consecutive_duplicate_points(points)

            if polyline_is_valid(points):
                return points

            Rhino.RhinoApp.WriteLine(
                u"폴리라인은 최소 두 개의 서로 다른 점이 필요합니다."
            )
            continue

        if result == Rhino.Input.GetResult.Option:
            if getter.OptionIndex() == undo_index and points:
                points.pop()
                continue

        return None


def align_side_polyline_directions(points_a, points_b):
    direct_length = (
        points_a[0].DistanceTo(points_b[0])
        + points_a[-1].DistanceTo(points_b[-1])
    )
    reversed_length = (
        points_a[0].DistanceTo(points_b[-1])
        + points_a[-1].DistanceTo(points_b[0])
    )

    if direct_length <= reversed_length:
        return copy_points(points_a), copy_points(points_b)

    return copy_points(points_a), reverse_points(points_b)


def cumulative_lengths(points):
    lengths = [0.0]
    total = 0.0

    for index in range(len(points) - 1):
        total += points[index].DistanceTo(points[index + 1])
        lengths.append(total)

    return lengths


def normalized_vertex_parameters(points):
    lengths = cumulative_lengths(points)
    total = lengths[-1]

    if total <= sc.doc.ModelAbsoluteTolerance:
        return [0.0, 1.0]

    return [length / total for length in lengths]


def merge_normalized_parameters(points_a, points_b):
    raw_values = (
        normalized_vertex_parameters(points_a)
        + normalized_vertex_parameters(points_b)
    )
    raw_values.append(0.0)
    raw_values.append(1.0)
    raw_values.sort()

    merged = []
    parameter_tolerance = 1.0e-9

    for value in raw_values:
        value = max(0.0, min(1.0, value))

        if not merged:
            merged.append(value)
            continue

        if abs(value - merged[-1]) > parameter_tolerance:
            merged.append(value)

    if merged[0] != 0.0:
        merged.insert(0, 0.0)

    if merged[-1] != 1.0:
        merged.append(1.0)

    return merged


def point_at_normalized_polyline_length(points, parameter):
    parameter = max(0.0, min(1.0, parameter))

    if parameter <= 0.0:
        return Rhino.Geometry.Point3d(points[0])

    if parameter >= 1.0:
        return Rhino.Geometry.Point3d(points[-1])

    lengths = cumulative_lengths(points)
    total = lengths[-1]

    if total <= sc.doc.ModelAbsoluteTolerance:
        return Rhino.Geometry.Point3d(points[0])

    target = total * parameter

    for index in range(len(points) - 1):
        segment_start = lengths[index]
        segment_end = lengths[index + 1]

        if target <= segment_end:
            segment_length = segment_end - segment_start

            if segment_length <= sc.doc.ModelAbsoluteTolerance:
                return Rhino.Geometry.Point3d(points[index])

            local_parameter = (
                (target - segment_start) / segment_length
            )
            return interpolate_point(
                points[index],
                points[index + 1],
                local_parameter
            )

    return Rhino.Geometry.Point3d(points[-1])


def validation_sample_parameters(points_a, points_b):
    base_parameters = merge_normalized_parameters(points_a, points_b)
    samples = list(base_parameters)

    for index in range(len(base_parameters) - 1):
        midpoint = (
            base_parameters[index]
            + base_parameters[index + 1]
        ) * 0.5
        samples.append(midpoint)

    samples.sort()
    return samples


def validate_side_polylines(points_a, points_b):
    if not polyline_is_valid(points_a):
        return False, u"좌측 기준 폴리라인이 유효하지 않습니다."

    if not polyline_is_valid(points_b):
        return False, u"우측 기준 폴리라인이 유효하지 않습니다."

    minimum_width = sc.doc.ModelAbsoluteTolerance
    samples = validation_sample_parameters(points_a, points_b)
    previous_width_vector = None

    for parameter in samples:
        point_a = point_at_normalized_polyline_length(
            points_a,
            parameter
        )
        point_b = point_at_normalized_polyline_length(
            points_b,
            parameter
        )

        width_vector = point_b - point_a
        width = width_vector.Length

        if width <= minimum_width:
            return (
                False,
                u"좌·우 기준선이 서로 만나거나 지나치게 가까운 구간이 있습니다."
            )

        if previous_width_vector is not None:
            dot = Rhino.Geometry.Vector3d.Multiply(
                previous_width_vector,
                width_vector
            )

            if dot < 0.0:
                return (
                    False,
                    u"좌·우 기준선의 대응 방향이 뒤집히는 구간이 있습니다."
                )

        previous_width_vector = width_vector

    return True, None


def create_inset_side_polylines(side_a, side_b, edge_offset):
    side_a, side_b = align_side_polyline_directions(
        side_a,
        side_b
    )

    valid, message = validate_side_polylines(side_a, side_b)

    if not valid:
        return False, [], [], message

    parameters = merge_normalized_parameters(side_a, side_b)
    sampled_parameters = list(parameters)

    for index in range(len(parameters) - 1):
        sampled_parameters.append(
            (parameters[index] + parameters[index + 1]) * 0.5
        )

    sampled_parameters.sort()
    unique_parameters = []
    parameter_tolerance = 1.0e-9

    for parameter in sampled_parameters:
        if (
            not unique_parameters
            or abs(parameter - unique_parameters[-1])
            > parameter_tolerance
        ):
            unique_parameters.append(parameter)

    inset_a = []
    inset_b = []
    minimum_width = (
        edge_offset * 2.0
        + sc.doc.ModelAbsoluteTolerance
    )

    for parameter in unique_parameters:
        point_a = point_at_normalized_polyline_length(
            side_a,
            parameter
        )
        point_b = point_at_normalized_polyline_length(
            side_b,
            parameter
        )

        inward = point_b - point_a
        width = inward.Length

        if width <= minimum_width:
            return (
                False,
                [],
                [],
                u"도로 폭이 너무 좁은 구간이 있습니다. "
                u"좌우에서 각각 500mm를 확보할 수 없습니다."
            )

        if not inward.Unitize():
            return (
                False,
                [],
                [],
                u"좌·우 기준선의 폭 방향 계산에 실패했습니다."
            )

        move = inward * edge_offset
        inset_a.append(point_a + move)
        inset_b.append(point_b - move)

    inset_a = remove_consecutive_duplicate_points(inset_a)
    inset_b = remove_consecutive_duplicate_points(inset_b)

    if not polyline_is_valid(inset_a):
        return (
            False,
            [],
            [],
            u"좌측 500mm 내부 기준 폴리라인 생성에 실패했습니다."
        )

    if not polyline_is_valid(inset_b):
        return (
            False,
            [],
            [],
            u"우측 500mm 내부 기준 폴리라인 생성에 실패했습니다."
        )

    valid, message = validate_side_polylines(inset_a, inset_b)

    if not valid:
        return (
            False,
            [],
            [],
            u"500mm 내부 기준선 계산 후 도로 영역이 유효하지 않습니다. "
            + message
        )

    return True, inset_a, inset_b, None


def build_lane_polylines_from_side_polylines(
    side_a,
    side_b,
    lane_count
):
    if lane_count < 1:
        return False, [], u"차선 수는 1 이상이어야 합니다."

    side_a, side_b = align_side_polyline_directions(
        side_a,
        side_b
    )
    valid, message = validate_side_polylines(side_a, side_b)

    if not valid:
        return False, [], message

    length_parameters = merge_normalized_parameters(side_a, side_b)
    sampled_a = [
        point_at_normalized_polyline_length(side_a, parameter)
        for parameter in length_parameters
    ]
    sampled_b = [
        point_at_normalized_polyline_length(side_b, parameter)
        for parameter in length_parameters
    ]

    lane_polylines = []

    for lane_index in range(lane_count + 1):
        width_parameter = float(lane_index) / float(lane_count)
        lane_points = []

        for point_a, point_b in zip(sampled_a, sampled_b):
            lane_points.append(
                interpolate_point(
                    point_a,
                    point_b,
                    width_parameter
                )
            )

        lane_points = remove_consecutive_duplicate_points(
            lane_points
        )

        if not polyline_is_valid(lane_points):
            return (
                False,
                [],
                u"차선 기준 폴리라인 생성에 실패했습니다."
            )

        lane_polylines.append(lane_points)

    return True, lane_polylines, None


def build_lane_polylines_from_outer_side_polylines(
    side_a,
    side_b,
    lane_count,
    edge_offset
):
    success, inset_a, inset_b, message = (
        create_inset_side_polylines(
            side_a,
            side_b,
            edge_offset
        )
    )

    if not success:
        return False, [], [], message

    success, lane_polylines, message = (
        build_lane_polylines_from_side_polylines(
            inset_a,
            inset_b,
            lane_count
        )
    )

    if not success:
        return False, [], [inset_a, inset_b], message

    return True, lane_polylines, [inset_a, inset_b], None


def pair_crossline_endpoints(cross_line_a, cross_line_b):
    direct_length = (
        cross_line_a[0].DistanceTo(cross_line_b[0])
        + cross_line_a[-1].DistanceTo(cross_line_b[-1])
    )
    reversed_length = (
        cross_line_a[0].DistanceTo(cross_line_b[-1])
        + cross_line_a[-1].DistanceTo(cross_line_b[0])
    )

    if direct_length <= reversed_length:
        side_a = [cross_line_a[0], cross_line_b[0]]
        side_b = [cross_line_a[-1], cross_line_b[-1]]
    else:
        side_a = [cross_line_a[0], cross_line_b[-1]]
        side_b = [cross_line_a[-1], cross_line_b[0]]

    return align_side_polyline_directions(side_a, side_b)


def create_inset_straight_side_lines(side_a, side_b, edge_offset):
    midpoint_a = interpolate_point(side_a[0], side_a[-1], 0.5)
    midpoint_b = interpolate_point(side_b[0], side_b[-1], 0.5)
    inward = midpoint_b - midpoint_a

    if not inward.Unitize():
        return None, None

    move = inward * edge_offset
    inset_a = [
        side_a[0] + move,
        side_a[-1] + move
    ]
    inset_b = [
        side_b[0] - move,
        side_b[-1] - move
    ]

    return align_side_polyline_directions(inset_a, inset_b)


def validate_crossline_generated_sides(
    side_a,
    side_b,
    edge_offset
):
    side_a, side_b = align_side_polyline_directions(side_a, side_b)
    minimum_width = (
        edge_offset * 2.0
        + sc.doc.ModelAbsoluteTolerance
    )

    for parameter in [0.0, 0.5, 1.0]:
        point_a = point_at_normalized_polyline_length(
            side_a,
            parameter
        )
        point_b = point_at_normalized_polyline_length(
            side_b,
            parameter
        )

        if point_a.DistanceTo(point_b) <= minimum_width:
            return (
                False,
                u"도로 폭이 너무 좁습니다. 양쪽 500mm 여유를 확보할 수 없습니다."
            )

    return True, None


def build_lane_lines_from_cross_lines(
    cross_line_a,
    cross_line_b,
    lane_count,
    edge_offset
):
    side_a, side_b = pair_crossline_endpoints(
        cross_line_a,
        cross_line_b
    )
    valid, message = validate_crossline_generated_sides(
        side_a,
        side_b,
        edge_offset
    )

    if not valid:
        return False, [], [side_a, side_b], message

    inset_a, inset_b = create_inset_straight_side_lines(
        side_a,
        side_b,
        edge_offset
    )

    if inset_a is None or inset_b is None:
        return (
            False,
            [],
            [side_a, side_b],
            u"안쪽 기준선 계산에 실패했습니다."
        )

    success, lane_polylines, message = (
        build_lane_polylines_from_side_polylines(
            inset_a,
            inset_b,
            lane_count
        )
    )

    if not success:
        return False, [], [side_a, side_b], message

    return True, lane_polylines, [side_a, side_b], None


def object_to_open_polyline_points(object_id):
    if not object_id:
        return None, u"객체를 찾을 수 없습니다."

    if not rs.IsCurve(object_id):
        return None, u"커브 객체만 선택할 수 있습니다."

    if rs.IsCurveClosed(object_id):
        return None, u"닫힌 커브는 기준선으로 사용할 수 없습니다."

    if rs.IsLine(object_id):
        points = [
            rs.CurveStartPoint(object_id),
            rs.CurveEndPoint(object_id)
        ]
        return remove_consecutive_duplicate_points(points), None

    if rs.IsPolyline(object_id):
        points = rs.PolylineVertices(object_id)

        if points:
            points = remove_consecutive_duplicate_points(points)

            if polyline_is_valid(points):
                return points, None

    return (
        None,
        u"Line 또는 열린 Polyline만 선택할 수 있습니다."
    )


def select_existing_side_polyline(prompt, forbidden_id=None):
    while True:
        object_id = rs.GetObject(
            prompt,
            rs.filter.curve,
            preselect=False,
            select=False
        )

        if not object_id:
            return None

        if forbidden_id and object_id == forbidden_id:
            Rhino.RhinoApp.WriteLine(
                u"같은 객체를 두 번 선택할 수 없습니다."
            )
            continue

        points, message = object_to_open_polyline_points(object_id)

        if points is None:
            Rhino.RhinoApp.WriteLine(message)
            continue

        return object_id, points


def get_input_mode():
    getter = Rhino.Input.Custom.GetOption()
    getter.SetCommandPrompt(u"입력 방식을 선택하세요")
    getter.AcceptNothing(True)

    cross_index = getter.AddOption("CrossLines")
    side_index = getter.AddOption("SideLines")
    cancel_index = getter.AddOption("Cancel")

    result = getter.Get()

    if result == Rhino.Input.GetResult.Nothing:
        return "cross"

    if result == Rhino.Input.GetResult.Cancel:
        return None

    if result != Rhino.Input.GetResult.Option:
        return None

    option_index = getter.OptionIndex()

    if option_index == cross_index:
        return "cross"

    if option_index == side_index:
        return "sides"

    if option_index == cancel_index:
        return None

    return None


def get_side_input_method():
    getter = Rhino.Input.Custom.GetOption()
    getter.SetCommandPrompt(
        u"좌·우 기준선 입력 방식을 선택하세요"
    )
    getter.AcceptNothing(True)

    draw_index = getter.AddOption("DrawPolyline")
    select_index = getter.AddOption("Select")
    cancel_index = getter.AddOption("Cancel")

    result = getter.Get()

    if result == Rhino.Input.GetResult.Nothing:
        return "draw"

    if result == Rhino.Input.GetResult.Cancel:
        return None

    if result != Rhino.Input.GetResult.Option:
        return None

    option_index = getter.OptionIndex()

    if option_index == draw_index:
        return "draw"

    if option_index == select_index:
        return "select"

    if option_index == cancel_index:
        return None

    return None


def get_lane_count(default_value):
    result, value = Rhino.Input.RhinoGet.GetInteger(
        u"왕복 기준 전체 차선 수를 입력하세요",
        True,
        int(default_value),
        1,
        MAX_LANE_COUNT
    )

    if result != Rhino.Commands.Result.Success:
        return None

    return int(value)


def get_lane_base_preview_action():
    getter = Rhino.Input.Custom.GetOption()
    getter.SetCommandPrompt(
        u"차선 기준선을 확인하세요. Enter=확인"
    )
    getter.AcceptNothing(True)

    confirm_index = getter.AddOption("Confirm")
    lanes_index = getter.AddOption("Lanes")
    cancel_index = getter.AddOption("Cancel")

    result = getter.Get()

    if result == Rhino.Input.GetResult.Nothing:
        return "confirm"

    if result == Rhino.Input.GetResult.Cancel:
        return "cancel"

    if result != Rhino.Input.GetResult.Option:
        return "cancel"

    option_index = getter.OptionIndex()

    if option_index == confirm_index:
        return "confirm"

    if option_index == lanes_index:
        return "lanes"

    if option_index == cancel_index:
        return "cancel"

    return "cancel"


def get_crossline_inputs():
    cross_line_a = get_temporary_line(1)

    if cross_line_a is None:
        return None

    cross_line_b = get_temporary_line(
        2,
        fixed_polylines=[cross_line_a]
    )

    if cross_line_b is None:
        return None

    return {
        "mode": "cross",
        "input_polylines": [
            cross_line_a,
            cross_line_b
        ],
        "cross_line_a": cross_line_a,
        "cross_line_b": cross_line_b
    }


def get_side_inputs_by_drawing():
    side_a = get_temporary_open_polyline(
        u"좌측 기준 폴리라인"
    )

    if side_a is None:
        return None

    side_b = get_temporary_open_polyline(
        u"우측 기준 폴리라인",
        fixed_polylines=[side_a]
    )

    if side_b is None:
        return None

    return {
        "mode": "sides_draw",
        "input_polylines": [side_a, side_b],
        "side_a": side_a,
        "side_b": side_b
    }


def get_side_inputs_by_selection():
    selected_a = select_existing_side_polyline(
        u"좌측 기준선이 될 Line 또는 열린 Polyline을 선택하세요"
    )

    if selected_a is None:
        return None

    id_a, side_a = selected_a
    selected_b = select_existing_side_polyline(
        u"우측 기준선이 될 Line 또는 열린 Polyline을 선택하세요",
        forbidden_id=id_a
    )

    if selected_b is None:
        return None

    id_b, side_b = selected_b

    return {
        "mode": "sides_select",
        "input_polylines": [side_a, side_b],
        "side_a": side_a,
        "side_b": side_b,
        "selected_ids": [id_a, id_b]
    }


def get_all_lane_base_inputs():
    input_mode = get_input_mode()

    if input_mode is None:
        return None

    if input_mode == "cross":
        return get_crossline_inputs()

    side_method = get_side_input_method()

    if side_method is None:
        return None

    if side_method == "draw":
        return get_side_inputs_by_drawing()

    return get_side_inputs_by_selection()


def build_lane_base_preview_geometry(
    source_data,
    lane_count,
    edge_offset
):
    mode = source_data["mode"]
    input_polylines = source_data["input_polylines"]

    if mode == "cross":
        success, lane_polylines, outer_polylines, message = (
            build_lane_lines_from_cross_lines(
                source_data["cross_line_a"],
                source_data["cross_line_b"],
                lane_count,
                edge_offset
            )
        )
        return (
            success,
            input_polylines,
            outer_polylines,
            lane_polylines,
            message
        )

    success, lane_polylines, inset_polylines, message = (
        build_lane_polylines_from_outer_side_polylines(
            source_data["side_a"],
            source_data["side_b"],
            lane_count,
            edge_offset
        )
    )

    if not success:
        return (
            False,
            input_polylines,
            inset_polylines,
            [],
            message
        )

    return (
        True,
        input_polylines,
        inset_polylines,
        lane_polylines,
        None
    )


def add_lane_base_polylines_to_current_layer(polylines):
    attributes = Rhino.DocObjects.ObjectAttributes()
    attributes.LayerIndex = sc.doc.Layers.CurrentLayerIndex

    created_ids = []
    undo_record = sc.doc.BeginUndoRecord(
        "Create Road Lane Base"
    )

    try:
        for points in polylines:
            polyline = points_to_polyline(points)
            object_id = sc.doc.Objects.AddPolyline(
                polyline,
                attributes
            )

            if object_id == System.Guid.Empty:
                for created_id in created_ids:
                    sc.doc.Objects.Delete(created_id, True)

                return []

            created_ids.append(object_id)

    finally:
        if undo_record > 0:
            sc.doc.EndUndoRecord(undo_record)

    return created_ids


def run_lane_base_draw_tool():
    """DrawLine 옵션에서 실행되는 독립적인 기준선 생성 과정입니다."""
    document = sc.doc
    source_data = get_all_lane_base_inputs()

    if source_data is None:
        return Rhino.Commands.Result.Cancel

    lane_count = get_lane_count(DEFAULT_LANE_COUNT)

    if lane_count is None:
        return Rhino.Commands.Result.Cancel

    edge_offset = millimeters_to_model_units(
        EDGE_OFFSET_MM
    )

    (
        success,
        input_polylines,
        outer_polylines,
        lane_polylines,
        message
    ) = build_lane_base_preview_geometry(
        source_data,
        lane_count,
        edge_offset
    )

    if not success:
        Rhino.RhinoApp.WriteLine(message)
        return Rhino.Commands.Result.Failure

    conduit = LaneBasePreviewConduit(
        input_polylines=input_polylines,
        outer_polylines=outer_polylines,
        lane_polylines=lane_polylines
    )
    conduit.Enabled = True
    document.Views.Redraw()
    action = "cancel"

    try:
        while True:
            action = get_lane_base_preview_action()

            if action == "confirm":
                break

            if action == "cancel":
                break

            if action == "lanes":
                new_lane_count = get_lane_count(lane_count)

                if new_lane_count is None:
                    continue

                (
                    success,
                    input_polylines,
                    outer_polylines,
                    lane_polylines,
                    message
                ) = build_lane_base_preview_geometry(
                    source_data,
                    new_lane_count,
                    edge_offset
                )

                if not success:
                    Rhino.RhinoApp.WriteLine(message)
                    continue

                lane_count = new_lane_count
                conduit.set_geometry(
                    input_polylines,
                    outer_polylines,
                    lane_polylines
                )
                document.Views.Redraw()

    finally:
        conduit.Enabled = False
        document.Views.Redraw()

    if action != "confirm":
        Rhino.RhinoApp.WriteLine(
            u"차선 기준선 생성을 취소했습니다."
        )
        return Rhino.Commands.Result.Cancel

    created_ids = add_lane_base_polylines_to_current_layer(
        lane_polylines
    )

    if len(created_ids) != len(lane_polylines):
        Rhino.RhinoApp.WriteLine(
            u"차선 기준선 객체 생성에 실패했습니다."
        )
        document.Views.Redraw()
        return Rhino.Commands.Result.Failure

    document.Views.Redraw()
    Rhino.RhinoApp.WriteLine(
        u"완료: 왕복 {0}차선 기준선 {1}개를 현재 레이어에 생성했습니다.".format(
            lane_count,
            len(created_ids)
        )
    )

    return Rhino.Commands.Result.Success


def get_lane_source_curves_or_action():
    """기존 커브를 선택하거나 DrawLine 기준선 생성 모드로 전환합니다."""
    getter = Rhino.Input.Custom.GetObject()
    getter.SetCommandPrompt(
        u"대상 커브들을 선택하세요. DrawLine=차선 기준선 생성"
    )
    getter.GeometryFilter = Rhino.DocObjects.ObjectType.Curve
    getter.AcceptNothing(True)
    draw_line_index = getter.AddOption("DrawLine")

    result = getter.GetMultiple(1, 0)

    if result == Rhino.Input.GetResult.Option:
        if getter.OptionIndex() == draw_line_index:
            return "draw_line", []
        return "retry", []

    if result != Rhino.Input.GetResult.Object:
        return "exit", []

    source_curves = []

    for index in range(getter.ObjectCount):
        try:
            curve = getter.Object(index).Curve()
        except:
            curve = None

        if curve:
            source_curves.append(curve.DuplicateCurve())

    if not source_curves:
        return "retry", []

    # 선택 커브는 복제본으로 계산하므로 원본 선택을 즉시 해제합니다.
    # 생성 후 첫 단계로 돌아갈 때 같은 커브가 자동으로 다시 잡히는 것을 방지합니다.
    rs.UnselectAllObjects()
    Rhino.RhinoDoc.ActiveDoc.Views.Redraw()

    return "curves", source_curves


# [5. 메인 실행 루프]
def run_lane_tool():
    while True:
        # 1단계: 기존 커브 선택 또는 DrawLine 기준선 생성
        input_action, source_curves = get_lane_source_curves_or_action()

        if input_action == "draw_line":
            run_lane_base_draw_tool()
            # 생성된 기준선은 자동 선택하지 않고 첫 커브 선택 단계로 돌아갑니다.
            continue

        if input_action == "retry":
            continue

        if input_action == "exit":
            print(">> 작업을 종료합니다.")
            break

        conduit = LanePreviewConduit()
        conduit.Enabled = True
        
        # 시작 시 기본값을 'Dashed'로 설정하고 즉시 프리뷰 계산
        current_type = "Dashed"
        current_all_previews = []
        for source_curve in source_curves:
            current_all_previews.extend(
                calculate_single_lane(source_curve, current_type)
            )
        
        conduit.update_curves(current_all_previews)
        Rhino.RhinoDoc.ActiveDoc.Views.Redraw()

        try:
            while True:
                go = Rhino.Input.Custom.GetOption()
                go.SetCommandPrompt("종류 클릭 후 'Enter'로 확정 (현재 기본값: Dashed)")
                optDashed = go.AddOption("Dashed")
                optGuide = go.AddOption("Guide")
                optSolid = go.AddOption("Solid")
                optCenter = go.AddOption("Center")
                optStop = go.AddOption("Stop")
                
                go.AcceptNothing(True) 
                res = go.Get()

                if res == Rhino.Input.GetResult.Option:
                    idx = go.OptionIndex()
                    if idx == optDashed: current_type = "Dashed"
                    elif idx == optGuide: current_type = "Guide"
                    elif idx == optSolid: current_type = "Solid"
                    elif idx == optCenter: current_type = "Center"
                    elif idx == optStop: current_type = "Stop"
                    
                    # 옵션 변경 시 프리뷰 업데이트
                    current_all_previews = []
                    for source_curve in source_curves:
                        current_all_previews.extend(
                            calculate_single_lane(
                                source_curve,
                                current_type
                            )
                        )
                    
                    conduit.update_curves(current_all_previews)
                    Rhino.RhinoDoc.ActiveDoc.Views.Redraw()
                    continue

                elif res == Rhino.Input.GetResult.Nothing:
                    # 현재 프리뷰 상태 그대로 생성
                    if current_all_previews:
                        conduit.Enabled = False
                        Rhino.RhinoDoc.ActiveDoc.Views.Redraw()
                        created_ids = bake_lane_marking_curves(
                            current_all_previews,
                            current_type
                        )

                        if len(created_ids) == len(
                            current_all_previews
                        ):
                            print(
                                ">> {0} 생성 완료 ({1}개). "
                                "다음 커브를 선택하세요.".format(
                                    current_type,
                                    len(created_ids)
                                )
                            )
                        else:
                            print(
                                ">> 차선 생성에 실패했습니다. "
                                "입력 커브와 문서 상태를 확인하세요."
                            )
                    break

                elif res == Rhino.Input.GetResult.Cancel:
                    print(">> 작업을 종료합니다.")
                    return

                else:
                    return
        finally:
            conduit.Enabled = False
            Rhino.RhinoDoc.ActiveDoc.Views.Redraw()

if __name__ == "__main__":
    run_lane_tool()
