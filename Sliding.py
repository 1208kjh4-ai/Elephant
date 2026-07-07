# -*- coding: utf-8 -*-
import Rhino
import Rhino.Geometry as rg
import Rhino.Display as rd
import Eto.Forms as forms
import Eto.Drawing as drawing
import rhinoscriptsyntax as rs
import scriptcontext as sc
import System
import json
import os

# ==============================================================================
# 미닫이문 식별 / 재수정용 UserText Key
# ==============================================================================
DOOR_DATA_KEY = "SlidingDoor_Data"
DOOR_ID_KEY = "SlidingDoor_Id"
DOOR_PART_KEY = "SlidingDoor_Part"

# ==============================================================================
# [0] 저장 / 불러오기 유틸리티
# ==============================================================================
def _point_to_list(p):
    return [float(p.X), float(p.Y), float(p.Z)]


def _vector_to_list(v):
    return [float(v.X), float(v.Y), float(v.Z)]


def _list_to_point(values):
    return rg.Point3d(float(values[0]), float(values[1]), float(values[2]))


def _list_to_vector(values):
    return rg.Vector3d(float(values[0]), float(values[1]), float(values[2]))


def plane_to_data(plane):
    return {
        "origin": _point_to_list(plane.Origin),
        "xaxis": _vector_to_list(plane.XAxis),
        "yaxis": _vector_to_list(plane.YAxis)
    }


def plane_from_data(data):
    return rg.Plane(
        _list_to_point(data["origin"]),
        _list_to_vector(data["xaxis"]),
        _list_to_vector(data["yaxis"])
    )


def read_door_data_from_object(obj_id):
    try:
        raw = rs.GetUserText(obj_id, DOOR_DATA_KEY)
    except:
        raw = None

    if not raw:
        return None

    try:
        data = json.loads(raw)
    except:
        return None

    if not isinstance(data, dict):
        return None

    if data.get("type") != "SlidingDoor":
        return None

    if "base_plane" not in data or "width" not in data or "height" not in data:
        return None

    return data


def _try_get_edit_data_from_getobject(go):
    try:
        obj_ref = go.Object(0)
    except:
        return None

    # 일반 객체 선택 또는 SubObject/Edge 선택 모두 parent ObjectId에서 UserText를 읽는다.
    try:
        obj_id = obj_ref.ObjectId
    except:
        obj_id = None

    if obj_id:
        data = read_door_data_from_object(obj_id)
        if data:
            data["_selected_id"] = obj_id
            return data

    try:
        rh_obj = obj_ref.Object()
    except:
        rh_obj = None

    if rh_obj:
        try:
            data = read_door_data_from_object(rh_obj.Id)
            if data:
                data["_selected_id"] = rh_obj.Id
                return data
        except:
            pass

    return None


def find_existing_door_from_selection():
    selected = rs.SelectedObjects()
    if not selected:
        return None

    for obj_id in selected:
        data = read_door_data_from_object(obj_id)
        if data:
            data["_selected_id"] = obj_id
            return data

    return None


def find_all_objects_by_door_id(door_id):
    result = []
    all_objects = rs.AllObjects()
    if not all_objects:
        return result

    for obj_id in all_objects:
        try:
            stored_id = rs.GetUserText(obj_id, DOOR_ID_KEY)
        except:
            stored_id = None

        if stored_id == door_id:
            result.append(obj_id)

    return result


def make_door_data_string(door_id, base_plane, width, height, settings):
    data = {
        "type": "SlidingDoor",
        "version": 1,
        "door_id": door_id,
        "base_plane": plane_to_data(base_plane),
        "width": float(width),
        "height": float(height),
        "settings": settings
    }
    return json.dumps(data)


def clear_selection_and_redraw():
    # 선택 오류 후 같은 객체가 pre-select 상태로 남아 있으면
    # GetObject가 같은 객체를 반복해서 받아 메시지 박스가 계속 뜰 수 있다.
    try:
        rs.UnselectAllObjects()
    except:
        pass
    try:
        Rhino.RhinoDoc.ActiveDoc.Views.Redraw()
    except:
        pass

# ==============================================================================
# [0-1] 프리셋 / Transform / 세트 판별 유틸리티
# ==============================================================================
def _get_appdata_folder():
    try:
        base = os.environ.get("APPDATA", None)
        if not base:
            base = os.path.expanduser("~")
        folder = os.path.join(base, "ElephantTools")
        if not os.path.exists(folder):
            os.makedirs(folder)
        return folder
    except:
        return None


def _get_preset_file_path():
    folder = _get_appdata_folder()
    if not folder:
        return None
    return os.path.join(folder, "SlidingDoorPresets.json")


def load_sliding_presets():
    path = _get_preset_file_path()
    if not path or not os.path.exists(path):
        return {}
    try:
        with open(path, "r") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except:
        return {}


def save_sliding_presets(presets):
    path = _get_preset_file_path()
    if not path:
        return False
    try:
        with open(path, "w") as f:
            json.dump(presets, f, indent=2, sort_keys=True)
        return True
    except Exception as ex:
        print("SlidingDoor preset save error:", ex)
        return False


def _safe_bool(value, default=False):
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in ["1", "true", "yes", "y", "on"]


def _safe_int(value, default=0):
    try:
        return int(float(value))
    except:
        return default


def _safe_float(value, default=0.0):
    try:
        return float(value)
    except:
        return default


def _clamp(value, low, high):
    return max(low, min(high, value))


def _normalize_sliding_settings(settings):
    s = dict(settings or {})
    panel_count = _safe_int(s.get("panel_count", 2), 2)
    if panel_count not in [2, 3, 4]:
        panel_count = 2
    open_value = _clamp(_safe_int(s.get("open_value", 0), 0), 0, 100)

    return {
        "panel_count": panel_count,
        "has_threshold": _safe_bool(s.get("has_threshold", True), True),
        "frame_t": str(s.get("frame_t", "30")),
        "frame_d": str(s.get("frame_d", "200")),
        "pframe_t": str(s.get("pframe_t", "60")),
        "flip": _safe_bool(s.get("flip", False), False),
        "union": _safe_bool(s.get("union", False), False),
        "open_value": int(open_value)
    }


def get_brep_from_id(obj_id):
    try:
        return rs.coercebrep(obj_id)
    except:
        try:
            return rs.coercebrep(System.Guid(str(obj_id)))
        except:
            return None


def get_object_bbox_center(obj_id):
    brep = get_brep_from_id(obj_id)
    if not brep:
        return None
    try:
        return brep.GetBoundingBox(True).Center
    except:
        return None


def _unique_object_ids(ids):
    result = []
    seen = set()
    for obj_id in ids or []:
        key = str(obj_id)
        if key not in seen:
            seen.add(key)
            result.append(obj_id)
    return result


def _delete_object_ids(ids):
    for obj_id in _unique_object_ids(ids):
        try:
            sc.doc.Objects.Delete(System.Guid(str(obj_id)), True)
        except:
            try:
                rs.DeleteObject(obj_id)
            except:
                pass


def generate_sliding_door_geometry(base_plane, width, height, settings):
    settings = _normalize_sliding_settings(settings)

    W, H = float(width), float(height)
    T_frame = _safe_float(settings.get("frame_t"), 30.0)
    D_frame = _safe_float(settings.get("frame_d"), 200.0)

    has_threshold = _safe_bool(settings.get("has_threshold"), True)
    do_union = _safe_bool(settings.get("union"), False)
    panel_count = _safe_int(settings.get("panel_count"), 2)
    if panel_count not in [2, 3, 4]:
        panel_count = 2

    T_pframe = _safe_float(settings.get("pframe_t"), 60.0)
    T_pdepth = 30.0
    T_glass = 10.0

    open_ratio = _clamp(_safe_int(settings.get("open_value"), 0), 0, 100) / 100.0
    parts = []
    tol = Rhino.RhinoDoc.ActiveDoc.ModelAbsoluteTolerance

    outer_frames = []
    outer_frames.append(rg.Box(rg.Plane.WorldXY, rg.Interval(0, T_frame), rg.Interval(0, D_frame), rg.Interval(0, H)).ToBrep())
    outer_frames.append(rg.Box(rg.Plane.WorldXY, rg.Interval(W - T_frame, W), rg.Interval(0, D_frame), rg.Interval(0, H)).ToBrep())

    if do_union:
        outer_frames.append(rg.Box(rg.Plane.WorldXY, rg.Interval(0, W), rg.Interval(0, D_frame), rg.Interval(H - T_frame, H)).ToBrep())
        if has_threshold:
            outer_frames.append(rg.Box(rg.Plane.WorldXY, rg.Interval(0, W), rg.Interval(0, D_frame), rg.Interval(0, T_frame)).ToBrep())
    else:
        outer_frames.append(rg.Box(rg.Plane.WorldXY, rg.Interval(T_frame, W - T_frame), rg.Interval(0, D_frame), rg.Interval(H - T_frame, H)).ToBrep())
        if has_threshold:
            outer_frames.append(rg.Box(rg.Plane.WorldXY, rg.Interval(T_frame, W - T_frame), rg.Interval(0, D_frame), rg.Interval(0, T_frame)).ToBrep())

    if do_union:
        unioned_outer = rg.Brep.CreateBooleanUnion(outer_frames, tol)
        if unioned_outer and len(unioned_outer) > 0:
            for b in unioned_outer:
                parts.append(("frame", b))
        else:
            for b in outer_frames:
                parts.append(("frame", b))
    else:
        for b in outer_frames:
            parts.append(("frame", b))

    z_start = T_frame if has_threshold else 0.0
    z_end = H - T_frame
    total_w = W - (2 * T_frame)

    num_overlaps = 2 if panel_count in [3, 4] else 1
    p_w = (total_w + num_overlaps * T_pframe) / panel_count

    if panel_count == 2:
        y_coords = [30.0, 60.0]
        x_starts = [T_frame, T_frame + p_w - T_pframe]
    elif panel_count == 3:
        y_coords = [30.0, 60.0, 90.0]
        x_starts = [T_frame, T_frame + p_w - T_pframe, T_frame + 2 * p_w - 2 * T_pframe]
    else:
        y_coords = [30.0, 60.0, 60.0, 30.0]
        x_starts = [T_frame, T_frame + p_w - T_pframe, T_frame + 2 * p_w - T_pframe, T_frame + 3 * p_w - 2 * T_pframe]

    def make_box(ix, iy, iz):
        return rg.Box(rg.Plane.WorldXY, ix, iy, iz).ToBrep()

    for i in range(panel_count):
        x_start = x_starts[i]
        move_x = 0

        if panel_count == 2:
            if i == 0:
                move_x = open_ratio * (p_w - T_pframe)
        elif panel_count == 3:
            if i == 0:
                move_x = open_ratio * 2 * (p_w - T_pframe)
            elif i == 1:
                move_x = open_ratio * 1 * (p_w - T_pframe)
        elif panel_count == 4:
            if i == 1 or i == 2:
                move_x = open_ratio * (p_w - T_pframe) * (1 if i % 2 == 0 else -1)

        x0 = x_start + move_x
        x1 = x0 + p_w
        y_s = y_coords[i]

        iy_frame = rg.Interval(y_s, y_s + T_pdepth)
        glass_y_offset = (T_pdepth - T_glass) / 2.0
        iy_glass = rg.Interval(y_s + glass_y_offset, y_s + glass_y_offset + T_glass)

        panel_frames = []

        if do_union:
            panel_frames.append(make_box(rg.Interval(x0, x1), iy_frame, rg.Interval(z_start, z_start + T_pframe)))
            panel_frames.append(make_box(rg.Interval(x0, x1), iy_frame, rg.Interval(z_end - T_pframe, z_end)))
            panel_frames.append(make_box(rg.Interval(x0, x0 + T_pframe), iy_frame, rg.Interval(z_start, z_end)))
            panel_frames.append(make_box(rg.Interval(x1 - T_pframe, x1), iy_frame, rg.Interval(z_start, z_end)))

            unioned_panel = rg.Brep.CreateBooleanUnion(panel_frames, tol)
            if unioned_panel and len(unioned_panel) > 0:
                for b in unioned_panel:
                    parts.append(("frame", b))
            else:
                for b in panel_frames:
                    parts.append(("frame", b))
        else:
            panel_frames.append(make_box(rg.Interval(x0, x1), iy_frame, rg.Interval(z_start, z_start + T_pframe)))
            panel_frames.append(make_box(rg.Interval(x0, x1), iy_frame, rg.Interval(z_end - T_pframe, z_end)))
            panel_frames.append(make_box(rg.Interval(x0, x0 + T_pframe), iy_frame, rg.Interval(z_start + T_pframe, z_end - T_pframe)))
            panel_frames.append(make_box(rg.Interval(x1 - T_pframe, x1), iy_frame, rg.Interval(z_start + T_pframe, z_end - T_pframe)))
            for b in panel_frames:
                parts.append(("frame", b))

        parts.append(("glass", make_box(rg.Interval(x0 + T_pframe, x1 - T_pframe), iy_glass, rg.Interval(z_start + T_pframe, z_end - T_pframe))))

    xform = rg.Transform.PlaneToPlane(rg.Plane.WorldXY, rg.Plane(base_plane))
    if _safe_bool(settings.get("flip"), False):
        xform = xform * rg.Transform.Scale(rg.Plane.WorldXY, 1.0, -1.0, 1.0)

    final_parts = []
    for name, brep in parts:
        brep.Transform(xform)
        final_parts.append((name, brep))

    return final_parts


def _find_three_non_collinear_indices(points):
    count = len(points)
    for i in range(count):
        for j in range(count):
            if j == i:
                continue
            v1 = points[j] - points[i]
            if v1.Length < 1e-6:
                continue
            for k in range(count):
                if k == i or k == j:
                    continue
                v2 = points[k] - points[i]
                if v2.Length < 1e-6:
                    continue
                cross = rg.Vector3d.CrossProduct(v1, v2)
                if cross.Length > 1e-6:
                    return i, j, k
    return None


def _brep_vertex_points(brep):
    try:
        return [v.Location for v in brep.Vertices]
    except:
        return []


def _average_vertex_error(ref_brep, cur_brep, xform):
    ref_pts = _brep_vertex_points(ref_brep)
    cur_pts = _brep_vertex_points(cur_brep)
    if len(ref_pts) != len(cur_pts) or len(ref_pts) < 3:
        return None
    total = 0.0
    for i in range(len(ref_pts)):
        p = rg.Point3d(ref_pts[i])
        p.Transform(xform)
        total += p.DistanceTo(cur_pts[i])
    return total / float(len(ref_pts))


def _direct_brep_vertex_error(ref_brep, cur_brep):
    """이미 같은 좌표계에 놓인 두 Brep가 실제로 같은 위치인지 직접 비교한다.
    주의: 여기서는 두 객체 사이의 추가 Transform을 다시 계산하지 않는다.
    복사본 수정 시 원본까지 삭제되는 문제를 막기 위한 핵심 비교 함수다.
    """
    ref_pts = _brep_vertex_points(ref_brep)
    cur_pts = _brep_vertex_points(cur_brep)
    if len(ref_pts) != len(cur_pts) or len(ref_pts) < 3:
        return None
    total = 0.0
    for i in range(len(ref_pts)):
        total += ref_pts[i].DistanceTo(cur_pts[i])
    return total / float(len(ref_pts))


def _geometry_match_tolerance(width=None, height=None):
    try:
        doc_tol = Rhino.RhinoDoc.ActiveDoc.ModelAbsoluteTolerance
    except:
        doc_tol = 0.01
    return max(1.0, doc_tol * 20.0)


def _score_xform_against_current_objects(door_id, ref_parts, xform):
    """후보 Transform이 현재 문 세트 전체와 얼마나 잘 맞는지 점수화한다.
    같은 door_id를 가진 원본/복사본이 함께 있어도, 변환된 기준 형상과 같은 위치에 있는 객체만 카운트한다.
    """
    if not door_id or xform is None or not ref_parts:
        return 0, None

    tol = _geometry_match_tolerance()
    candidates = find_all_objects_by_door_id(door_id)
    matched_ids = []
    total_error = 0.0

    for obj_id in candidates:
        cur_brep = get_brep_from_id(obj_id)
        if not cur_brep:
            continue
        try:
            part_name = rs.GetUserText(obj_id, DOOR_PART_KEY)
        except:
            part_name = None

        best_error = None
        for ref_name, ref_brep in ref_parts:
            if part_name and ref_name != part_name:
                continue
            dup = ref_brep.DuplicateBrep()
            dup.Transform(xform)
            error = _direct_brep_vertex_error(dup, cur_brep)
            if error is None:
                continue
            if best_error is None or error < best_error:
                best_error = error

        if best_error is not None and best_error <= tol:
            matched_ids.append(obj_id)
            total_error += best_error

    if not matched_ids:
        return 0, None
    return len(_unique_object_ids(matched_ids)), total_error / float(len(matched_ids))


def _compute_brep_transform_by_vertices(ref_brep, cur_brep):
    ref_pts = _brep_vertex_points(ref_brep)
    cur_pts = _brep_vertex_points(cur_brep)

    if len(ref_pts) != len(cur_pts) or len(ref_pts) < 3:
        return None, None

    idxs = _find_three_non_collinear_indices(ref_pts)
    if not idxs:
        return None, None

    i, j, k = idxs
    try:
        ref_plane = rg.Plane(ref_pts[i], ref_pts[j], ref_pts[k])
        cur_plane = rg.Plane(cur_pts[i], cur_pts[j], cur_pts[k])
        xform = rg.Transform.PlaneToPlane(ref_plane, cur_plane)
        error = _average_vertex_error(ref_brep, cur_brep, xform)
        return xform, error
    except:
        return None, None


def _resolve_current_edit_data(edit_data):
    if not edit_data:
        return edit_data, None

    selected_id = edit_data.get("_selected_id", None)
    if not selected_id:
        return edit_data, None

    current_brep = get_brep_from_id(selected_id)
    if not current_brep:
        return edit_data, None

    try:
        base_plane = plane_from_data(edit_data["base_plane"])
        width = float(edit_data["width"])
        height = float(edit_data["height"])
        settings = edit_data.get("settings", {})
    except:
        return edit_data, None

    try:
        selected_part = rs.GetUserText(selected_id, DOOR_PART_KEY)
    except:
        selected_part = None

    ref_parts = generate_sliding_door_geometry(base_plane, width, height, settings)
    door_id = edit_data.get("door_id", None)
    tol = _geometry_match_tolerance(width, height)

    # 선택 객체 하나만 기준으로 하면 좌우 프레임처럼 같은 형상이 여러 개 있는 경우
    # 잘못된 기준 부품에서 Transform이 만들어질 수 있다.
    # 그래서 가능한 Transform 후보들을 만든 뒤, 현재 문 세트 전체와 가장 많이 직접 일치하는 후보를 선택한다.
    candidates = []
    for part_name, ref_brep in ref_parts:
        if selected_part and part_name != selected_part:
            continue
        xform, error = _compute_brep_transform_by_vertices(ref_brep, current_brep)
        if xform is None or error is None or error > tol:
            continue
        score, score_error = _score_xform_against_current_objects(door_id, ref_parts, xform)
        candidates.append((score, score_error if score_error is not None else error, error, xform))

    # 같은 part에서 실패하면 전체 후보를 대상으로 한 번 더 시도한다.
    if not candidates:
        for part_name, ref_brep in ref_parts:
            xform, error = _compute_brep_transform_by_vertices(ref_brep, current_brep)
            if xform is None or error is None or error > tol:
                continue
            score, score_error = _score_xform_against_current_objects(door_id, ref_parts, xform)
            candidates.append((score, score_error if score_error is not None else error, error, xform))

    if not candidates:
        return edit_data, None

    # score가 높은 후보가 현재 복사본 세트와 가장 잘 맞는다.
    # 동점이면 전체 오차와 선택 객체 오차가 작은 쪽을 선택한다.
    candidates.sort(key=lambda item: (-item[0], item[1], item[2]))
    best_score, best_score_error, best_error, best_xform = candidates[0]

    if best_xform is None or best_error is None or best_error > tol:
        return edit_data, None

    new_plane = rg.Plane(base_plane)
    new_plane.Transform(best_xform)

    resolved = dict(edit_data)
    resolved["base_plane"] = plane_to_data(new_plane)
    resolved["_original_base_plane"] = plane_to_data(base_plane)
    resolved["_edit_xform"] = best_xform
    resolved["_reference_parts"] = ref_parts
    resolved["_edit_match_score"] = best_score
    return resolved, best_xform


def _get_group_sliding_object_ids(selected_id, door_id):
    ids = []
    if not selected_id or not door_id:
        return ids

    group_names = []
    try:
        group_names = rs.ObjectGroups(selected_id) or []
    except:
        group_names = []

    for group_name in group_names:
        try:
            group_ids = rs.ObjectsByGroup(group_name) or []
        except:
            group_ids = []
        for obj_id in group_ids:
            try:
                if rs.GetUserText(obj_id, DOOR_ID_KEY) == door_id:
                    ids.append(obj_id)
            except:
                pass

    return _unique_object_ids(ids)


def _get_transform_matched_sliding_object_ids(edit_data):
    ids = []
    if not edit_data:
        return ids

    door_id = edit_data.get("door_id", None)
    xform = edit_data.get("_edit_xform", None)
    ref_parts = edit_data.get("_reference_parts", None)

    if not door_id or xform is None or not ref_parts:
        return ids

    tol = _geometry_match_tolerance(edit_data.get("width", None), edit_data.get("height", None))
    candidates = find_all_objects_by_door_id(door_id)

    for obj_id in candidates:
        cur_brep = get_brep_from_id(obj_id)
        if not cur_brep:
            continue

        try:
            part_name = rs.GetUserText(obj_id, DOOR_PART_KEY)
        except:
            part_name = None

        best_error = None
        for ref_name, ref_brep in ref_parts:
            if part_name and ref_name != part_name:
                continue
            dup = ref_brep.DuplicateBrep()
            dup.Transform(xform)
            # 중요: 여기서는 다시 Transform을 계산하지 않는다.
            # 변환된 기준 형상과 현재 후보 객체가 같은 위치인지 직접 비교해야 원본이 같이 삭제되지 않는다.
            error = _direct_brep_vertex_error(dup, cur_brep)
            if error is None:
                continue
            if best_error is None or error < best_error:
                best_error = error

        if best_error is not None and best_error <= tol:
            ids.append(obj_id)

    return _unique_object_ids(ids)


def _get_spatial_sliding_object_ids(edit_data, selected_id):
    ids = []
    if not edit_data or not selected_id:
        return ids

    door_id = edit_data.get("door_id", None)
    if not door_id:
        return ids

    selected_center = get_object_bbox_center(selected_id)
    if not selected_center:
        return ids

    try:
        width = float(edit_data.get("width", 0.0))
        height = float(edit_data.get("height", 0.0))
        settings = _normalize_sliding_settings(edit_data.get("settings", {}))
        depth = _safe_float(settings.get("frame_d"), 200.0)
        threshold = max(width, height, depth) * 1.25
    except:
        threshold = 3000.0

    for obj_id in find_all_objects_by_door_id(door_id):
        center = get_object_bbox_center(obj_id)
        if center and center.DistanceTo(selected_center) <= threshold:
            ids.append(obj_id)

    return _unique_object_ids(ids)


def _filter_ids_near_selected(ids, selected_id, edit_data):
    if not ids or not selected_id:
        return []
    selected_center = get_object_bbox_center(selected_id)
    if not selected_center:
        return ids
    try:
        width = float(edit_data.get("width", 0.0))
        height = float(edit_data.get("height", 0.0))
        settings = _normalize_sliding_settings(edit_data.get("settings", {}))
        depth = _safe_float(settings.get("frame_d"), 200.0)
        threshold = max(width, height, depth) * 1.10
    except:
        threshold = 2500.0
    result = []
    for obj_id in ids:
        center = get_object_bbox_center(obj_id)
        if center and center.DistanceTo(selected_center) <= threshold:
            result.append(obj_id)
    return _unique_object_ids(result)


def get_current_sliding_set_ids(edit_data):
    if not edit_data:
        return []

    selected_id = edit_data.get("_selected_id", None)
    door_id = edit_data.get("door_id", None)

    # 1순위: 현재 선택 객체에서 역산한 Transform과 직접 일치하는 객체만 삭제한다.
    # 이 결과가 있으면 group/spatial 결과를 더하지 않는다. 복사본이 원본과 같은 그룹/door_id를 공유할 수 있기 때문이다.
    transform_ids = _get_transform_matched_sliding_object_ids(edit_data)
    if transform_ids:
        if selected_id:
            transform_ids.append(selected_id)
        return _unique_object_ids(transform_ids)

    # 2순위 fallback: Transform 계산이 실패한 경우에만 그룹을 사용한다.
    # 단, 그룹 복사가 같은 그룹명을 공유할 수 있으므로 선택 객체 주변으로 한 번 더 필터링한다.
    group_ids = _get_group_sliding_object_ids(selected_id, door_id)
    if group_ids:
        filtered = _filter_ids_near_selected(group_ids, selected_id, edit_data)
        if filtered:
            return _unique_object_ids(filtered + ([selected_id] if selected_id else []))

    # 3순위 fallback: 공간 기준. 이 역시 Transform 실패 시에만 사용한다.
    spatial_ids = _get_spatial_sliding_object_ids(edit_data, selected_id)
    if spatial_ids:
        if selected_id:
            spatial_ids.append(selected_id)
        return _unique_object_ids(spatial_ids)

    return [selected_id] if selected_id else []



# ==============================================================================
# [1] 독립형 미리보기 엔진 (실시간 변화 반영)
# ==============================================================================
class DoorPreviewConduit(rd.DisplayConduit):
    def __init__(self):
        rd.DisplayConduit.__init__(self)
        self.preview_breps = []
        self.frame_mat = rd.DisplayMaterial(System.Drawing.Color.Indigo)
        self.glass_mat = rd.DisplayMaterial(System.Drawing.Color.AliceBlue)
        self.glass_mat.Transparency = 0.5

    def DrawForeground(self, e):
        for name, brep in self.preview_breps:
            if brep and brep.IsValid:
                mat = self.glass_mat if name == "glass" else self.frame_mat
                e.Display.DrawBrepShaded(brep, mat)
                e.Display.DrawBrepWires(brep, System.Drawing.Color.Black, 1)

# ==============================================================================
# [2] 미닫이문 전용 다이얼로그 (설정 저장/로드 및 수정 모드 지원)
# ==============================================================================
class SlidingDoorDialog(forms.Dialog[bool]):
    def __init__(self, base_plane, width, height, initial_settings=None, edit_mode=False):
        self.edit_mode = edit_mode
        self.Title = "미닫이문 수정" if edit_mode else "세부 설정"
        self.base_plane, self.width, self.height = base_plane, width, height
        self.initial_settings = initial_settings or None
        self.conduit = DoorPreviewConduit()
        self.conduit.Enabled = True

        self.default_settings = {
            "panel_count": 2,
            "has_threshold": True,
            "frame_t": "30",
            "frame_d": "200",
            "pframe_t": "60",
            "flip": False,
            "union": False,
            "open_value": 0
        }

        if self.initial_settings:
            self.saved_settings = _normalize_sliding_settings(self.initial_settings)
        else:
            self.saved_settings = _normalize_sliding_settings(sc.sticky.get("SlidingDoor_Settings", self.default_settings))

        self.presets = load_sliding_presets()

        self.layout = forms.DynamicLayout(Spacing=drawing.Size(5, 8), Padding=20)
        self.SetupPresetUI()
        self.layout.AddRow(None)
        self.SetupUI()
        self.layout.AddRow(None)

        btn_ok = forms.Button(Text="수정" if edit_mode else "생성")
        btn_ok.Click += self.OnOkClick

        btn_cancel = forms.Button(Text="취소")
        btn_cancel.Click += self.OnCancelClick

        self.layout.AddRow(btn_ok, btn_cancel)
        self.Content = self.layout

        self.Shown += lambda s, e: self.UpdatePreview()

    def SetupPresetUI(self):
        self.dd_preset = forms.DropDown()
        self.dd_preset.Width = 150
        self.txt_preset_name = forms.TextBox()
        self.txt_preset_name.Width = 150

        self.btn_preset_load = forms.Button(Text="불러오기")
        self.btn_preset_save = forms.Button(Text="저장")
        self.btn_preset_delete = forms.Button(Text="삭제")

        self.btn_preset_load.Click += self.OnPresetLoad
        self.btn_preset_save.Click += self.OnPresetSave
        self.btn_preset_delete.Click += self.OnPresetDelete

        self.RefreshPresetDropdown()

        self.layout.AddRow(forms.Label(Text="프리셋 목록:"), self.dd_preset, self.btn_preset_load)
        self.layout.AddRow(forms.Label(Text="프리셋 이름:"), self.txt_preset_name, self.btn_preset_save, self.btn_preset_delete)

    def RefreshPresetDropdown(self, select_name=None):
        names = sorted(self.presets.keys())
        self.dd_preset.DataStore = names
        if names:
            if select_name in names:
                self.dd_preset.SelectedIndex = names.index(select_name)
            else:
                self.dd_preset.SelectedIndex = 0
        else:
            self.dd_preset.SelectedIndex = -1

    def GetSelectedPresetName(self):
        try:
            value = self.dd_preset.SelectedValue
            if value is not None and str(value).strip():
                return str(value).strip()
        except:
            pass
        text = str(self.txt_preset_name.Text).strip()
        return text if text else None

    def ApplySettingsToUI(self, settings):
        settings = _normalize_sliding_settings(settings)

        cnt = settings.get("panel_count", 2)
        self.rb_cnt_2.Checked = (cnt == 2)
        self.rb_cnt_3.Checked = (cnt == 3)
        self.rb_cnt_4.Checked = (cnt == 4)

        has_threshold = settings.get("has_threshold", True)
        self.rb_threshold_on.Checked = bool(has_threshold)
        self.rb_threshold_off.Checked = not bool(has_threshold)

        self.txt_t.Text = str(settings.get("frame_t", "30"))
        self.txt_d.Text = str(settings.get("frame_d", "200"))
        self.txt_pframe_t.Text = str(settings.get("pframe_t", "60"))

        self.cb_flip.Checked = bool(settings.get("flip", False))
        self.cb_union.Checked = bool(settings.get("union", False))

        open_value = _clamp(_safe_int(settings.get("open_value", 0), 0), 0, 100)
        self.sli_open.Value = int(open_value)
        self.lbl_open.Text = str(int(open_value)) + "%"

        self.UpdatePreview()

    def OnPresetLoad(self, sender, e):
        name = self.GetSelectedPresetName()
        if not name or name not in self.presets:
            rs.MessageBox("불러올 프리셋을 선택하세요.", 0, "프리셋")
            return

        self.txt_preset_name.Text = name
        self.ApplySettingsToUI(self.presets[name])

    def OnPresetSave(self, sender, e):
        name = str(self.txt_preset_name.Text).strip()
        if not name:
            rs.MessageBox("프리셋 이름을 입력하세요.", 0, "프리셋")
            return

        if name in self.presets:
            rc = rs.MessageBox("같은 이름의 프리셋이 이미 있습니다.\n현재 값으로 덮어쓰시겠습니까?", 4, "프리셋 저장")
            if rc != 6:
                return

        self.presets[name] = self.GetSettingsDict()
        if save_sliding_presets(self.presets):
            self.RefreshPresetDropdown(name)
        else:
            rs.MessageBox("프리셋 저장에 실패했습니다.", 0, "프리셋 저장")

    def OnPresetDelete(self, sender, e):
        name = self.GetSelectedPresetName()
        if not name or name not in self.presets:
            rs.MessageBox("삭제할 프리셋을 선택하세요.", 0, "프리셋")
            return

        rc = rs.MessageBox("'{}' 프리셋을 삭제하시겠습니까?".format(name), 4, "프리셋 삭제")
        if rc != 6:
            return

        try:
            del self.presets[name]
        except:
            pass

        if save_sliding_presets(self.presets):
            self.txt_preset_name.Text = ""
            self.RefreshPresetDropdown()
        else:
            rs.MessageBox("프리셋 삭제 저장에 실패했습니다.", 0, "프리셋 삭제")

    def SetupUI(self):
        # 1. 문 개수 라디오 버튼 세팅 및 로드
        self.rb_cnt_2 = forms.RadioButton(Text="2개")
        self.rb_cnt_3 = forms.RadioButton(self.rb_cnt_2, Text="3개")
        self.rb_cnt_4 = forms.RadioButton(self.rb_cnt_2, Text="4개")

        saved_cnt = int(self.saved_settings.get("panel_count", 2))
        if saved_cnt == 2:
            self.rb_cnt_2.Checked = True
        elif saved_cnt == 3:
            self.rb_cnt_3.Checked = True
        elif saved_cnt == 4:
            self.rb_cnt_4.Checked = True
        else:
            self.rb_cnt_2.Checked = True

        # 2. 문턱 라디오 버튼 세팅 및 로드
        self.rb_threshold_on = forms.RadioButton(Text="있음")
        self.rb_threshold_off = forms.RadioButton(self.rb_threshold_on, Text="없음")
        if self.saved_settings.get("has_threshold", True):
            self.rb_threshold_on.Checked = True
        else:
            self.rb_threshold_off.Checked = True

        # 3. 텍스트 박스 세팅, 너비 고정(50) 및 로드
        self.txt_t = forms.TextBox(Text=str(self.saved_settings.get("frame_t", "30")))
        self.txt_t.Width = 50
        self.txt_d = forms.TextBox(Text=str(self.saved_settings.get("frame_d", "200")))
        self.txt_d.Width = 50
        self.txt_pframe_t = forms.TextBox(Text=str(self.saved_settings.get("pframe_t", "60")))
        self.txt_pframe_t.Width = 50

        # 4. 체크박스 및 슬라이더 세팅 및 로드
        self.cb_flip = forms.CheckBox(Text="뒤집기", Checked=bool(self.saved_settings.get("flip", False)))
        self.cb_union = forms.CheckBox(Text="프레임 결합", Checked=bool(self.saved_settings.get("union", False)))

        saved_open = _clamp(int(self.saved_settings.get("open_value", 0)), 0, 100)
        self.sli_open = forms.Slider(MinValue=0, MaxValue=100, Value=saved_open)
        self.lbl_open = forms.Label(Text=str(saved_open) + "%")

        # 이벤트 연결
        self.rb_cnt_2.CheckedChanged += lambda s,e: self.UpdatePreview()
        self.rb_cnt_3.CheckedChanged += lambda s,e: self.UpdatePreview()
        self.rb_cnt_4.CheckedChanged += lambda s,e: self.UpdatePreview()
        self.rb_threshold_on.CheckedChanged += lambda s,e: self.UpdatePreview()
        self.rb_threshold_off.CheckedChanged += lambda s,e: self.UpdatePreview()
        self.cb_flip.CheckedChanged += lambda s,e: self.UpdatePreview()
        self.cb_union.CheckedChanged += lambda s,e: self.UpdatePreview()
        self.txt_t.TextChanged += lambda s,e: self.UpdatePreview()
        self.txt_d.TextChanged += lambda s,e: self.UpdatePreview()
        self.txt_pframe_t.TextChanged += lambda s,e: self.UpdatePreview()
        self.sli_open.ValueChanged += lambda s,e: (setattr(self.lbl_open, 'Text', str(self.sli_open.Value)+"%"), self.UpdatePreview())

        self.layout.AddRow(forms.Label(Text="문 개수:"), self.rb_cnt_2, self.rb_cnt_3, self.rb_cnt_4)
        self.layout.AddRow(forms.Label(Text="문턱:"), self.rb_threshold_on, self.rb_threshold_off)
        self.layout.AddRow(forms.Label(Text="문틀 두께(mm):"), self.txt_t)
        self.layout.AddRow(forms.Label(Text="문틀 깊이(mm):"), self.txt_d)
        self.layout.AddRow(forms.Label(Text="프레임 두께(mm):"), self.txt_pframe_t)
        self.layout.AddRow(self.cb_flip, self.cb_union)
        self.layout.AddRow(forms.Label(Text="열림 정도(0~100%):"), self.sli_open, self.lbl_open)

    def GetSettingsDict(self):
        if self.rb_cnt_2.Checked:
            current_cnt = 2
        elif self.rb_cnt_4.Checked:
            current_cnt = 4
        else:
            current_cnt = 3

        return _normalize_sliding_settings({
            "panel_count": int(current_cnt),
            "has_threshold": bool(self.rb_threshold_on.Checked),
            "frame_t": str(self.txt_t.Text),
            "frame_d": str(self.txt_d.Text),
            "pframe_t": str(self.txt_pframe_t.Text),
            "flip": bool(self.cb_flip.Checked),
            "union": bool(self.cb_union.Checked),
            "open_value": int(self.sli_open.Value)
        })

    def OnOkClick(self, sender, args):
        current_settings = self.GetSettingsDict()
        sc.sticky["SlidingDoor_Settings"] = current_settings
        self.ClosePreview()
        self.Close(True)

    def OnCancelClick(self, sender, args):
        self.ClosePreview()
        self.Close(False)

    def GetSafeFloat(self, text, default):
        try:
            return float(text)
        except:
            return default

    def UpdatePreview(self):
        try:
            self.conduit.preview_breps = self.GenerateGeometry()
            Rhino.RhinoDoc.ActiveDoc.Views.Redraw()
        except Exception as ex:
            print("SlidingDoor preview error:", ex)

    def GenerateGeometry(self):
        return generate_sliding_door_geometry(self.base_plane, self.width, self.height, self.GetSettingsDict())

    def ClosePreview(self):
        try:
            self.conduit.Enabled = False
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
            super(SlidingDoorDialog, self).OnClosed(e)
        except:
            pass

# ==============================================================================
# [3] 입력 방식 분기 처리용 로직
# ==============================================================================
def process_two_curves(c1, c2):
    def get_bottom_top(c):
        s, e = c.PointAtStart, c.PointAtEnd
        return (e, s) if s.Z > e.Z else (s, e)

    try:
        p1_b, p1_t = get_bottom_top(c1)
        p2_b, p2_t = get_bottom_top(c2)
    except:
        return None

    if p1_b.X > p2_b.X or (abs(p1_b.X - p2_b.X) < 1e-4 and p1_b.Y > p2_b.Y):
        p1_b, p2_b = p2_b, p1_b
        p1_t, p2_t = p2_t, p1_t

    z_vec = (p1_t - p1_b)
    height = z_vec.Length
    if height < 1e-4:
        return None
    z_vec.Unitize()

    x_vec = (p2_b - p1_b)
    width = x_vec.Length
    if width < 1e-4:
        return None
    x_vec.Unitize()

    y_vec = Rhino.Geometry.Vector3d.CrossProduct(z_vec, x_vec)
    if y_vec.Length < 1e-4:
        return None
    y_vec.Unitize()

    base_plane = rg.Plane(p1_b, x_vec, y_vec)
    return base_plane, width, height


def get_3point_rectangle():
    gp1 = Rhino.Input.Custom.GetPoint()
    gp1.SetCommandPrompt("직사각형의 첫 번째 구석점을 지정하세요.")
    if gp1.Get() != Rhino.Input.GetResult.Point:
        return None, 0, 0
    p1 = gp1.Point()

    gp2 = Rhino.Input.Custom.GetPoint()
    gp2.SetCommandPrompt("두 번째 점을 지정하세요 (너비 방향).")
    gp2.SetBasePoint(p1, True)
    gp2.DrawLineFromPoint(p1, True)
    if gp2.Get() != Rhino.Input.GetResult.Point:
        return None, 0, 0
    p2 = gp2.Point()

    x_vec = p2 - p1
    width = x_vec.Length
    if width < 1e-4:
        return None, 0, 0
    x_vec.Unitize()

    gp3 = Rhino.Input.Custom.GetPoint()
    gp3.SetCommandPrompt("세 번째 점을 지정하세요 (높이 방향).")
    gp3.SetBasePoint(p2, True)

    def DynamicRectangleDraw(sender, args):
        current_pt = args.CurrentPoint
        v13 = current_pt - p1
        proj_len = v13 * x_vec
        z_dir = v13 - (x_vec * proj_len)
        p4 = p1 + z_dir
        p3_projected = p2 + z_dir
        args.Display.DrawLine(p1, p2, System.Drawing.Color.DarkRed, 2)
        args.Display.DrawLine(p2, p3_projected, System.Drawing.Color.DarkRed, 2)
        args.Display.DrawLine(p3_projected, p4, System.Drawing.Color.DarkRed, 2)
        args.Display.DrawLine(p4, p1, System.Drawing.Color.DarkRed, 2)

    gp3.DynamicDraw += DynamicRectangleDraw
    if gp3.Get() != Rhino.Input.GetResult.Point:
        return None, 0, 0
    p3 = gp3.Point()

    v13 = p3 - p1
    proj_len = v13 * x_vec
    z_vec = v13 - (x_vec * proj_len)
    height = z_vec.Length
    if height < 1e-4:
        return None, 0, 0
    z_vec.Unitize()

    y_vec = Rhino.Geometry.Vector3d.CrossProduct(z_vec, x_vec)
    if y_vec.Length < 1e-4:
        return None, 0, 0
    y_vec.Unitize()

    base_plane = rg.Plane(p1, x_vec, y_vec)
    return base_plane, width, height


def get_door_target_from_user():
    while True:
        # 첫 번째 선택에서 자동 판별한다.
        # - 미닫이문 데이터가 있는 Brep/객체: 즉시 수정 모드
        # - 일반 커브/엣지: 신규 생성용 첫 번째 수직 모서리로 보고 두 번째 모서리를 이어서 받음
        go1 = Rhino.Input.Custom.GetObject()
        go1.SetCommandPrompt("수정할 미닫이문 선택, 혹은 개구부의 수직 모서리 선택. Rectangle 옵션 사용 가능.")
        go1.GeometryFilter = Rhino.DocObjects.ObjectType.Curve | Rhino.DocObjects.ObjectType.EdgeFilter | Rhino.DocObjects.ObjectType.Brep
        go1.SubObjectSelect = True
        try:
            go1.EnablePreSelect(False, True)
        except:
            pass
        try:
            go1.GroupSelect = False
        except:
            pass

        opt_rect = go1.AddOption("Rectangle")
        res = go1.Get()

        if res == Rhino.Input.GetResult.Cancel:
            return None

        if res == Rhino.Input.GetResult.Option:
            if go1.Option().Index == opt_rect:
                base_plane, width, height = get_3point_rectangle()
                if base_plane is not None:
                    return {"mode": "new", "base_plane": base_plane, "width": width, "height": height}
                return None

        if res != Rhino.Input.GetResult.Object:
            return None

        # 기존 미닫이문 객체라면 별도 Edit/New 질문 없이 바로 수정 팝업으로 넘어간다.
        edit_data = _try_get_edit_data_from_getobject(go1)
        if edit_data:
            return {"mode": "edit", "edit_data": edit_data}

        # 미닫이문이 아니면 신규 생성용 첫 번째 모서리로 해석한다.
        try:
            c1 = go1.Object(0).Curve()
        except:
            c1 = None

        if not c1:
            rs.MessageBox("선택한 객체에서 미닫이문 데이터를 찾지 못했습니다.\n수정하려면 이 스크립트로 생성된 미닫이문의 프레임 또는 유리 객체를 선택하세요.\n새로 만들려면 수직 모서리/커브를 선택하세요.", 0, "선택 오류")
            clear_selection_and_redraw()
            continue

        go2 = Rhino.Input.Custom.GetObject()
        go2.SetCommandPrompt("두 번째 수직 모서리를 선택하세요.")
        go2.GeometryFilter = Rhino.DocObjects.ObjectType.Curve | Rhino.DocObjects.ObjectType.EdgeFilter
        go2.SubObjectSelect = True
        try:
            go2.EnablePreSelect(False, True)
        except:
            pass
        try:
            go2.GroupSelect = False
        except:
            pass

        res2 = go2.Get()
        if res2 == Rhino.Input.GetResult.Cancel:
            return None

        if res2 != Rhino.Input.GetResult.Object:
            return None

        try:
            c2 = go2.Object(0).Curve()
        except:
            c2 = None

        result = process_two_curves(c1, c2)
        if result:
            base_plane, width, height = result
            return {"mode": "new", "base_plane": base_plane, "width": width, "height": height}

        rs.MessageBox("새로 생성하려면 두 개의 수직 모서리/커브를 선택해야 합니다.\n다시 선택해 주세요.", 0, "선택 오류")
        clear_selection_and_redraw()

    return None

# ==============================================================================
# [4] Bake / Update
# ==============================================================================
def bake_or_update_sliding_door(dlg, edit_data=None):
    if edit_data and edit_data.get("door_id"):
        # 복사본까지 같은 door_id를 공유할 수 있으므로,
        # 수정 시에는 선택된 현재 세트만 삭제하고 새 door_id를 부여한다.
        door_id = str(System.Guid.NewGuid())
        old_object_ids = get_current_sliding_set_ids(edit_data)
    else:
        door_id = str(System.Guid.NewGuid())
        old_object_ids = []

    settings = dlg.GetSettingsDict()
    data_string = make_door_data_string(door_id, dlg.base_plane, dlg.width, dlg.height, settings)

    rs.EnableRedraw(False)

    # 수정 모드에서는 현재 선택된 미닫이문 세트만 삭제한 뒤 다시 생성한다.
    # 패널 수처럼 객체 개수가 달라지는 설정도 안전하게 반영된다.
    if old_object_ids:
        _delete_object_ids(old_object_ids)

    group_name = rs.AddGroup()
    baked_object_ids = []

    for name, brep in dlg.GenerateGeometry():
        obj_id = Rhino.RhinoDoc.ActiveDoc.Objects.AddBrep(brep)
        baked_object_ids.append(obj_id)

        # 기존 스크립트의 레이어명을 유지한다.
        layer_name = "Door_" + name
        if not rs.IsLayer(layer_name):
            rs.AddLayer(layer_name)
        rs.ObjectLayer(obj_id, layer_name)

        if name == "frame":
            rs.ObjectColor(obj_id, [150, 150, 150])
        elif name == "glass":
            rs.ObjectColor(obj_id, [200, 230, 255])

        # 다음 실행 때 선택해서 다시 수정할 수 있도록 모든 구성 객체에 동일한 데이터 저장
        rs.SetUserText(obj_id, DOOR_DATA_KEY, data_string)
        rs.SetUserText(obj_id, DOOR_ID_KEY, door_id)
        rs.SetUserText(obj_id, DOOR_PART_KEY, name)

    if baked_object_ids:
        rs.AddObjectsToGroup(baked_object_ids, group_name)
        rs.UnselectAllObjects()
        rs.SelectObjects(baked_object_ids)

    rs.EnableRedraw(True)
    Rhino.RhinoDoc.ActiveDoc.Views.Redraw()

# ==============================================================================
# [5] 메인 실행부
# ==============================================================================
def main():
    # 1) 실행 전에 이미 이 스크립트로 생성된 미닫이문 객체가 선택되어 있으면 즉시 수정 모드
    edit_data = find_existing_door_from_selection()

    if edit_data:
        try:
            base_plane = plane_from_data(edit_data["base_plane"])
            width = float(edit_data["width"])
            height = float(edit_data["height"])
            settings = edit_data.get("settings", {})
        except:
            rs.MessageBox("선택한 미닫이문의 저장 데이터가 손상되어 수정할 수 없습니다.", 0, "데이터 오류")
            return

        edit_data, _ = _resolve_current_edit_data(edit_data)
        try:
            base_plane = plane_from_data(edit_data["base_plane"])
        except:
            pass

        dlg = SlidingDoorDialog(base_plane, width, height, settings, True)
        try:
            rc = Rhino.UI.EtoExtensions.ShowSemiModal(dlg, Rhino.RhinoDoc.ActiveDoc, Rhino.UI.RhinoEtoApp.MainWindow)
        finally:
            try: dlg.ClosePreview()
            except: pass

        if rc:
            bake_or_update_sliding_door(dlg, edit_data)
        return

    # 선택된 객체가 있었지만 editable sliding door가 아니면,
    # 아래 GetObject 단계에서 같은 객체가 자동으로 다시 잡히지 않도록 비운다.
    if rs.SelectedObjects():
        clear_selection_and_redraw()

    # 2) 실행 후 사용자가 선택하는 객체를 보고 자동 판별
    #    - 미닫이문 객체: 수정
    #    - 수직 모서리/커브 2개 또는 Rectangle: 신규 생성
    target = get_door_target_from_user()
    if not target:
        return

    if target.get("mode") == "edit":
        edit_data = target.get("edit_data")
        try:
            base_plane = plane_from_data(edit_data["base_plane"])
            width = float(edit_data["width"])
            height = float(edit_data["height"])
            settings = edit_data.get("settings", {})
        except:
            rs.MessageBox("선택한 미닫이문의 저장 데이터가 손상되어 수정할 수 없습니다.", 0, "데이터 오류")
            return

        edit_data, _ = _resolve_current_edit_data(edit_data)
        try:
            base_plane = plane_from_data(edit_data["base_plane"])
        except:
            pass

        dlg = SlidingDoorDialog(base_plane, width, height, settings, True)
        try:
            rc = Rhino.UI.EtoExtensions.ShowSemiModal(dlg, Rhino.RhinoDoc.ActiveDoc, Rhino.UI.RhinoEtoApp.MainWindow)
        finally:
            try: dlg.ClosePreview()
            except: pass

        if rc:
            bake_or_update_sliding_door(dlg, edit_data)
        return

    if target.get("mode") == "new":
        base_plane = target.get("base_plane")
        width = target.get("width")
        height = target.get("height")

        dlg = SlidingDoorDialog(base_plane, width, height, None, False)
        try:
            rc = Rhino.UI.EtoExtensions.ShowSemiModal(dlg, Rhino.RhinoDoc.ActiveDoc, Rhino.UI.RhinoEtoApp.MainWindow)
        finally:
            try: dlg.ClosePreview()
            except: pass

        if rc:
            bake_or_update_sliding_door(dlg, None)

if __name__ == "__main__":
    main()
