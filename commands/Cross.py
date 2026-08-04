# -*- coding: utf-8 -*-
import Rhino
import Rhino.Geometry as rg
import Rhino.Display as rd
import rhinoscriptsyntax as rs
import System.Drawing

# [1. 통합 미리보기 컨딧]
class MultiCrosswalkPreviewConduit(rd.DisplayConduit):
    def __init__(self, curves):
        rd.DisplayConduit.__init__(self)
        self.preview_curves = curves
        self.color = System.Drawing.Color.Red

    def DrawForeground(self, e):
        if self.preview_curves:
            for crv in self.preview_curves:
                e.Display.DrawCurve(crv, self.color, 2)

# [2. 화살표 커브 생성 함수]
def get_arrow_geometry(base_pt, direction, right_vec):
    plane = rg.Plane(base_pt, right_vec, direction)
    half_bw, half_hw = 80.0, 180.0
    pts = [
        rg.Point3d(-half_bw, -200, 0), rg.Point3d(half_bw, -200, 0),
        rg.Point3d(half_bw, 0, 0), rg.Point3d(half_hw, 0, 0),
        rg.Point3d(0, 250, 0), 
        rg.Point3d(-half_hw, 0, 0), rg.Point3d(-half_bw, 0, 0),
        rg.Point3d(-half_bw, -200, 0)
    ]
    polyline = rg.Polyline(pts).ToPolylineCurve()
    xform = rg.Transform.PlaneToPlane(rg.Plane.WorldXY, plane)
    polyline.Transform(xform)
    return polyline


# [3. 3점 직사각형 / 평행사변형 입력]
def make_projected_rectangle_curve_from_3pts(
    p0,
    p1,
    p2,
    show_error=False
):
    p0 = rg.Point3d(p0)
    p1 = rg.Point3d(p1)
    p2 = rg.Point3d(p2)

    base_z = p0.Z
    p0.Z = base_z
    p1.Z = base_z
    p2.Z = base_z

    tolerance = max(
        Rhino.RhinoDoc.ActiveDoc.ModelAbsoluteTolerance,
        1.0e-6
    )
    length_vec = rg.Vector3d(p1 - p0)
    length_vec.Z = 0.0

    if length_vec.Length <= tolerance:
        if show_error:
            rs.MessageBox(
                "직사각형 길이가 너무 짧습니다.",
                48,
                "입력 오류"
            )
        return None

    direction = rg.Vector3d(length_vec)
    direction.Unitize()

    raw_width = rg.Vector3d(p2 - p1)
    raw_width.Z = 0.0
    projection = rg.Vector3d.Multiply(
        raw_width,
        direction
    )
    width_vec = raw_width - direction * projection

    if width_vec.Length <= tolerance:
        raw_width = rg.Vector3d(p2 - p0)
        raw_width.Z = 0.0
        projection = rg.Vector3d.Multiply(
            raw_width,
            direction
        )
        width_vec = raw_width - direction * projection

    if width_vec.Length <= tolerance:
        if show_error:
            rs.MessageBox(
                "직사각형 폭이 너무 좁습니다.",
                48,
                "입력 오류"
            )
        return None

    p2_rect = p1 + width_vec
    p3_rect = p0 + width_vec
    return rg.Polyline(
        [p0, p1, p2_rect, p3_rect, p0]
    ).ToPolylineCurve()


def make_parallelogram_curve_from_3pts(
    p0,
    p1,
    p2,
    show_error=False
):
    p0 = rg.Point3d(p0)
    p1 = rg.Point3d(p1)
    p2 = rg.Point3d(p2)

    base_z = p0.Z
    p0.Z = base_z
    p1.Z = base_z
    p2.Z = base_z

    tolerance = max(
        Rhino.RhinoDoc.ActiveDoc.ModelAbsoluteTolerance,
        1.0e-6
    )
    length_vec = rg.Vector3d(p1 - p0)
    length_vec.Z = 0.0

    if length_vec.Length <= tolerance:
        if show_error:
            rs.MessageBox(
                "평행사변형 길이가 너무 짧습니다.",
                48,
                "입력 오류"
            )
        return None

    direction = rg.Vector3d(length_vec)
    direction.Unitize()

    side_vec = rg.Vector3d(p2 - p1)
    side_vec.Z = 0.0
    side_height_vec = (
        side_vec
        - direction
        * rg.Vector3d.Multiply(side_vec, direction)
    )

    if side_height_vec.Length <= tolerance:
        if show_error:
            rs.MessageBox(
                "평행사변형 폭이 너무 좁습니다.",
                48,
                "입력 오류"
            )
        return None

    p3 = p0 + side_vec
    return rg.Polyline(
        [p0, p1, p2, p3, p0]
    ).ToPolylineCurve()


def get_point_with_line_preview(prompt, base_pt):
    getter = Rhino.Input.Custom.GetPoint()
    getter.SetCommandPrompt(prompt)
    getter.SetBasePoint(base_pt, True)

    def on_dynamic_draw(sender, event_args):
        current = rg.Point3d(event_args.CurrentPoint)
        current.Z = base_pt.Z
        event_args.Display.DrawLine(
            base_pt,
            current,
            System.Drawing.Color.Gold,
            3
        )

    getter.DynamicDraw += on_dynamic_draw
    result = getter.Get()

    if result != Rhino.Input.GetResult.Point:
        return None

    return getter.Point()


def get_point_with_rectangle_preview(prompt, p0, p1):
    getter = Rhino.Input.Custom.GetPoint()
    getter.SetCommandPrompt(prompt)
    getter.SetBasePoint(p1, True)

    def on_dynamic_draw(sender, event_args):
        current = event_args.CurrentPoint
        curve = make_projected_rectangle_curve_from_3pts(
            p0,
            p1,
            current,
            False
        )

        if curve:
            event_args.Display.DrawCurve(
                curve,
                System.Drawing.Color.Gold,
                3
            )

    getter.DynamicDraw += on_dynamic_draw
    result = getter.Get()

    if result != Rhino.Input.GetResult.Point:
        return None

    return getter.Point()


def get_point_with_parallelogram_preview(prompt, p0, p1):
    getter = Rhino.Input.Custom.GetPoint()
    getter.SetCommandPrompt(prompt)
    getter.SetBasePoint(p1, True)

    def on_dynamic_draw(sender, event_args):
        current = event_args.CurrentPoint
        curve = make_parallelogram_curve_from_3pts(
            p0,
            p1,
            current,
            False
        )

        if curve:
            event_args.Display.DrawCurve(
                curve,
                System.Drawing.Color.Gold,
                3
            )

    getter.DynamicDraw += on_dynamic_draw
    result = getter.Get()

    if result != Rhino.Input.GetResult.Point:
        return None

    return getter.Point()


def draw_rectangle_curve_from_points():
    getter = Rhino.Input.Custom.GetPoint()
    getter.SetCommandPrompt(
        "횡단보도 직사각형의 첫 번째 모서리점을 클릭하세요"
    )

    if getter.Get() != Rhino.Input.GetResult.Point:
        return None

    p0 = getter.Point()
    p1 = get_point_with_line_preview(
        "길이 방향의 두 번째 모서리점을 클릭하세요",
        p0
    )

    if p1 is None:
        return None

    p2 = get_point_with_rectangle_preview(
        "폭 방향의 세 번째 점을 클릭하세요",
        p0,
        p1
    )

    if p2 is None:
        return None

    return make_projected_rectangle_curve_from_3pts(
        p0,
        p1,
        p2,
        True
    )


def draw_parallelogram_curve_from_points():
    getter = Rhino.Input.Custom.GetPoint()
    getter.SetCommandPrompt(
        "횡단보도 평행사변형의 첫 번째 모서리점을 클릭하세요"
    )

    if getter.Get() != Rhino.Input.GetResult.Point:
        return None

    p0 = getter.Point()
    p1 = get_point_with_line_preview(
        "길이 방향의 두 번째 모서리점을 클릭하세요",
        p0
    )

    if p1 is None:
        return None

    p2 = get_point_with_parallelogram_preview(
        "기울어진 폭 방향의 세 번째 모서리점을 클릭하세요",
        p0,
        p1
    )

    if p2 is None:
        return None

    return make_parallelogram_curve_from_3pts(
        p0,
        p1,
        p2,
        True
    )


def get_crosswalk_target_curves():
    getter = Rhino.Input.Custom.GetObject()
    getter.SetCommandPrompt(
        "횡단보도 사각형들을 선택하세요. Draw=직사각형 / Parallelogram=평행사변형"
    )
    getter.GeometryFilter = Rhino.DocObjects.ObjectType.Curve
    getter.AcceptNothing(True)
    draw_index = getter.AddOption("Draw")
    parallelogram_index = getter.AddOption("Parallelogram")

    result = getter.GetMultiple(1, 0)

    if result == Rhino.Input.GetResult.Option:
        if getter.OptionIndex() == draw_index:
            curve = draw_rectangle_curve_from_points()
            return [curve] if curve else []
        if getter.OptionIndex() == parallelogram_index:
            curve = draw_parallelogram_curve_from_points()
            return [curve] if curve else []
        return []

    if result != Rhino.Input.GetResult.Object:
        return None

    curves = []

    for index in range(getter.ObjectCount):
        try:
            curve = getter.Object(index).Curve()
        except:
            curve = None

        if curve:
            curves.append(curve.DuplicateCurve())

    rs.UnselectAllObjects()
    Rhino.RhinoDoc.ActiveDoc.Views.Redraw()
    return curves


# [4. 개별 횡단보도 계산 엔진]
def point_at_crosswalk_coordinates(
    origin,
    length_direction,
    side_vector,
    width,
    x,
    y
):
    return (
        origin
        + length_direction * x
        + side_vector * (y / width)
    )


def make_crosswalk_polyline(
    origin,
    length_direction,
    side_vector,
    width,
    coordinates
):
    points = [
        point_at_crosswalk_coordinates(
            origin,
            length_direction,
            side_vector,
            width,
            x,
            y
        )
        for x, y in coordinates
    ]
    return rg.Polyline(points).ToPolylineCurve()


def calculate_crosswalk_curves(polyline_source):
    if hasattr(polyline_source, "TryGetPolyline"):
        curve = polyline_source
    else:
        curve = rs.coercecurve(polyline_source)

    if not curve:
        return []

    success, pl = curve.TryGetPolyline()
    if not success:
        return []

    pts = list(pl)
    if len(pts) != 5:
        return []

    tolerance = max(
        Rhino.RhinoDoc.ActiveDoc.ModelAbsoluteTolerance,
        1.0e-6
    )
    d01 = pts[0].DistanceTo(pts[1])
    d12 = pts[1].DistanceTo(pts[2])

    if d01 >= d12:
        origin_pt = rg.Point3d(pts[0])
        length_vec = rg.Vector3d(pts[1] - pts[0])
        side_vec = rg.Vector3d(pts[2] - pts[1])
    else:
        origin_pt = rg.Point3d(pts[1])
        length_vec = rg.Vector3d(pts[2] - pts[1])
        side_vec = rg.Vector3d(pts[0] - pts[1])

    actual_length = length_vec.Length
    if actual_length <= tolerance:
        return []

    l_vec = rg.Vector3d(length_vec)
    l_vec.Unitize()

    right_vec = rg.Vector3d.CrossProduct(
        l_vec,
        rg.Vector3d.ZAxis
    )
    if not right_vec.Unitize():
        return []

    # 입력 방향과 관계없이 기존 화살표 진행 방향을 유지하도록
    # 폭 벡터가 right_vec 쪽을 향하게 기준 모서리를 정규화한다.
    if rg.Vector3d.Multiply(side_vec, right_vec) < 0.0:
        origin_pt = origin_pt + side_vec
        side_vec.Reverse()

    side_parallel = (
        l_vec
        * rg.Vector3d.Multiply(side_vec, l_vec)
    )
    side_height_vec = side_vec - side_parallel
    width = side_height_vec.Length
    if width <= tolerance:
        return []

    stripe_w, gap_w = 450.0, 450.0

    if width < 4000:  # 일반형
        simple_curves = []
        current_dist = 0

        while current_dist + stripe_w <= actual_length:
            next_dist = current_dist + stripe_w
            stripe_curve = make_crosswalk_polyline(
                origin_pt,
                l_vec,
                side_vec,
                width,
                [
                    (current_dist, 0.0),
                    (next_dist, 0.0),
                    (next_dist, width),
                    (current_dist, width),
                    (current_dist, 0.0)
                ]
            )
            simple_curves.append(stripe_curve)
            current_dist += (stripe_w + gap_w)

        return simple_curves

    else:  # 지그재그형
        center_gap, half_len = 450.0, actual_length / 2.0
        bar_h = (width - center_gap) / 2.0
        lane_start_y = (width + center_gap) / 2.0
        temp_bars = []
        current_offset = 0

        while current_offset + stripe_w <= half_len:
            x1 = half_len - current_offset
            x0 = x1 - stripe_w
            temp_bars.append({
                'x0': x0,
                'x1': x1
            })
            current_offset += stripe_w

        upper_lane_bars = []
        total_count = len(temp_bars)
        is_odd_total = (total_count % 2 != 0)
        present_in_bottom = []

        for i in range(total_count):
            should_move = (
                (i % 2 == 0)
                if is_odd_total
                else (i % 2 != 0)
            )
            x0 = temp_bars[i]['x0']
            x1 = temp_bars[i]['x1']

            if should_move:
                x0, x1 = (
                    actual_length - x1,
                    actual_length - x0
                )
            else:
                present_in_bottom.append(i)

            upper_lane_bars.append([
                (x0, lane_start_y),
                (x1, lane_start_y),
                (x1, width),
                (x0, width),
                (x0, lane_start_y)
            ])

        last_idx = present_in_bottom[-1] if present_in_bottom else -1
        zone_top_x = (
            temp_bars[last_idx]['x0']
            if last_idx != -1
            else half_len
        )
        arrow_x = zone_top_x / 2.0

        final_curves = []

        for coordinates in upper_lane_bars:
            upper_curve = make_crosswalk_polyline(
                origin_pt,
                l_vec,
                side_vec,
                width,
                coordinates
            )
            lower_coordinates = [
                (actual_length - x, width - y)
                for x, y in coordinates
            ]
            lower_curve = make_crosswalk_polyline(
                origin_pt,
                l_vec,
                side_vec,
                width,
                lower_coordinates
            )
            final_curves.append(upper_curve)
            final_curves.append(lower_curve)

        # 화살표 중심은 평행사변형 좌표를 따르지만 형상에는
        # 전단 변형을 적용하지 않아 원래 폭과 비율을 유지한다.
        for ratio in [1 / 3.0, 2 / 3.0]:
            arrow_y = lane_start_y + bar_h * ratio
            upper_arrow_pt = point_at_crosswalk_coordinates(
                origin_pt,
                l_vec,
                side_vec,
                width,
                arrow_x,
                arrow_y
            )
            lower_arrow_pt = point_at_crosswalk_coordinates(
                origin_pt,
                l_vec,
                side_vec,
                width,
                actual_length - arrow_x,
                width - arrow_y
            )
            final_curves.append(
                get_arrow_geometry(
                    upper_arrow_pt,
                    l_vec,
                    right_vec
                )
            )
            final_curves.append(
                get_arrow_geometry(
                    lower_arrow_pt,
                    -l_vec,
                    -right_vec
                )
            )

        return final_curves

# [5. 메인 실행 루프]
def main():
    while True:
        # 01. 여러 사각형 선택 또는 3점 직사각형/평행사변형 입력
        target_curves = get_crosswalk_target_curves()
        if target_curves is None:
            break
        if not target_curves:
            continue

        # 02. 전체 커브 계산
        all_combined_curves = []
        for target_curve in target_curves:
            curves = calculate_crosswalk_curves(target_curve)
            if curves:
                all_combined_curves.extend(curves)

        if not all_combined_curves:
            print(">> 계산된 커브가 없습니다.")
            continue

        # 03. 미리보기 컨딧 켜기
        conduit = MultiCrosswalkPreviewConduit(all_combined_curves)
        conduit.Enabled = True
        Rhino.RhinoDoc.ActiveDoc.Views.Redraw()

        # 04. 사용자 확정 입력 (버그 방지를 위해 조건문 수정)
        prompt = "{0}개의 횡단보도 미리보기 중 - [Enter] 확정생성 / [ESC] 취소".format(len(target_curves))
        res = rs.GetString(prompt)
        
        # rs.GetString은 Enter 시 빈 문자열("") 혹은 기본값을 반환함
        # ESC를 누르면 None을 반환함
        if res is not None: 
            # ESC가 아닌 모든 입력(Enter 포함)에 대해 생성 진행
            rs.EnableRedraw(False)
            layer_name = "Crosswalk_Crv"
            if not rs.IsLayer(layer_name):
                rs.AddLayer(layer_name, System.Drawing.Color.White)
            
            baked_count = 0
            for c in all_combined_curves:
                obj_id = Rhino.RhinoDoc.ActiveDoc.Objects.AddCurve(c)
                if obj_id:
                    rs.ObjectLayer(obj_id, layer_name)
                    rs.ObjectColor(obj_id, [255, 255, 255])
                    baked_count += 1
            
            rs.EnableRedraw(True)
            Rhino.RhinoDoc.ActiveDoc.Views.Redraw()
            print(">> {0}개의 객체가 '{1}' 레이어에 생성되었습니다.".format(baked_count, layer_name))
        else:
            print(">> 생성이 취소되었습니다.")

        # 05. 미리보기 컨딧 끄고 루프 재시작
        conduit.Enabled = False
        Rhino.RhinoDoc.ActiveDoc.Views.Redraw()

if __name__ == "__main__":
    main()
