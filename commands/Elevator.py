# -*- coding: utf-8 -*-
import Rhino
import Rhino.Geometry as rg
import Rhino.Display as rd
import Rhino.Input.Custom as ric
import Rhino.DocObjects as rdo
import Rhino.UI
import Eto.Forms as forms
import Eto.Drawing as drawing
import rhinoscriptsyntax as rs
import scriptcontext as sc
import System
import math
import json

# ==============================================================================
# Glass Elevator Generator for Rhino 7 / Rhino 8 Python
# ------------------------------------------------------------------------------
# v1
# - SelectRectangle is default; DrawRectangle option is available.
# - Rectangle is used as the outer shaft reference line.
# - Floor levels are local Z values relative to the rectangle base Z.
# - Door zone height is one shared value for all floors.
# - Existing slab height extraction uses selected objects' bounding-box Max.Z.
# - Door types are assigned per floor bay with F/B/T codes. Door direction: 0 / 90 / 180 / 270.
# - Glass is generated as 30mm solid panels.
# - Glass frame option: framed / frameless.
# - Framed glass: 50x50 mullions, 100x100 corner mullions, glass inset 50mm.
# - Frameless glass: glass outer face matches shaft reference line, panel gap 20mm.
# - Structural beam spec H/B/t; columns use max(H, B) square size and share t.
# - H/t steel mode is represented by composed H-section boxes.
# - Door opening depth is calculated to the structural inner face.
# - Car is generated inside the shaft and moves with a live slider.
# - Static preview updates only by Enter / Apply. Car slider updates car preview only.
# - Preview uses DisplayConduit; Bake creates actual Rhino objects by layers.
# - Beam length is direction-aware: horizontal beams contact column web, vertical beams contact column flange.
# ===============================================================================

# Fixed values
GLASS_STRUCTURE_GAP = 50.0
GLASS_THICKNESS = 30.0
GLASS_PANEL_GAP = 20.0
GLASS_MULLION_SIZE = 50.0
GLASS_CORNER_MULLION_SIZE = 100.0
DOOR_FRAME_THICKNESS = 30.0
CAR_CLEARANCE = 150.0
CAR_FRAME_SIZE = 50.0
CAR_FLOOR_THICKNESS = 1000.0
CAR_CEILING_THICKNESS = 1000.0
STRUCTURE_BEAM_DROP = 30.0
LEVEL_MERGE_TOLERANCE = 10.0
MIN_SPANDREL_HEIGHT = 300.0

METADATA_KEY = "ElephantGlassElevatorState"
LAST_STATE_KEY = "ElephantGlassElevatorLastState"
ITEM_INDEX_KEY = "ElephantGlassElevatorItemIndex"

DOOR_CODE_FRONT = "F"
DOOR_CODE_BACK = "B"
DOOR_CODE_THROUGH = "T"
DOOR_CODE_NONE = "N"
VALID_DOOR_CODES = [DOOR_CODE_FRONT, DOOR_CODE_BACK, DOOR_CODE_THROUGH, DOOR_CODE_NONE]

# Layers
LAYER_GLASS = "El_Glass"
LAYER_FRAME = "El_Frame"
LAYER_DOOR = "El_Door"
LAYER_COLUMN = "El_Column"
LAYER_BEAM = "El_Beam"
LAYER_CAR = "El_Car"
LAYER_CAP = "El_Cap"

CAP_TYPE_SOLID = "Solid"
CAP_TYPE_GLASS = "Glass"
CAP_TYPE_NONE = "None"

SIDE_FRONT = 0
SIDE_RIGHT = 1
SIDE_BACK = 2
SIDE_LEFT = 3

# ==============================================================================
# Utility
# ==============================================================================
def _dot(a, b):
    return a.X * b.X + a.Y * b.Y + a.Z * b.Z


def _neg(vec):
    return rg.Vector3d(-vec.X, -vec.Y, -vec.Z)


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
    x = y = z = 0.0
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


def get_rectangle_info(crv):
    if not crv:
        return False, None, "커브가 없습니다."
    if not crv.IsClosed:
        return False, None, "닫힌 직사각형 커브만 지원합니다."

    pts = _try_get_polyline_points(crv)
    if len(pts) < 4:
        return False, None, "직사각형 꼭짓점을 추출하지 못했습니다."

    pts = pts[:4]
    base_z = pts[0].Z
    flat_pts = []
    for p in pts:
        q = rg.Point3d(p.X, p.Y, base_z)
        flat_pts.append(q)

    center = _average_point(flat_pts)

    edges = []
    for i in range(4):
        p0 = flat_pts[i]
        p1 = flat_pts[(i + 1) % 4]
        v = rg.Vector3d(p1 - p0)
        v.Z = 0.0
        edges.append((i, v.Length, v))

    edges_sorted = sorted(edges, key=lambda item: item[1], reverse=True)
    long_index, length, dir_vec = edges_sorted[0]

    if length < 100.0:
        return False, None, "직사각형 길이가 너무 짧습니다."

    width_vec = rg.Vector3d(flat_pts[(long_index + 2) % 4] - flat_pts[(long_index + 1) % 4])
    width_vec.Z = 0.0
    width = width_vec.Length
    if width < 100.0:
        return False, None, "직사각형 폭이 너무 좁습니다."

    u = _safe_unitize(dir_vec, rg.Vector3d(1, 0, 0))
    v = _safe_unitize(width_vec, rg.Vector3d(0, 1, 0))

    cross = rg.Vector3d.CrossProduct(u, v)
    if cross.Z < 0:
        v.Reverse()

    info = {
        "curve": crv.DuplicateCurve(),
        "center": center,
        "u": u,
        "v": v,
        "length": float(length),
        "width": float(width),
        "base_z": float(base_z)
    }
    return True, info, ""


def local_to_world(rect, x, y, z):
    c = rect["center"]
    u = rect["u"]
    v = rect["v"]
    return rg.Point3d(
        c.X + u.X * x + v.X * y,
        c.Y + u.Y * x + v.Y * y,
        rect["base_z"] + z
    )


def make_rectangle_curve_from_info(rect):
    half_l = rect["length"] * 0.5
    half_w = rect["width"] * 0.5
    pts = [
        local_to_world(rect, -half_l, half_w, 0.0),
        local_to_world(rect, half_l, half_w, 0.0),
        local_to_world(rect, half_l, -half_w, 0.0),
        local_to_world(rect, -half_l, -half_w, 0.0),
        local_to_world(rect, -half_l, half_w, 0.0)
    ]
    return rg.Polyline(pts).ToNurbsCurve()


def _point_to_data(point):
    return [float(point.X), float(point.Y), float(point.Z)]


def _vector_to_data(vector):
    return [float(vector.X), float(vector.Y), float(vector.Z)]


def _point_from_data(data):
    return rg.Point3d(float(data[0]), float(data[1]), float(data[2]))


def _vector_from_data(data):
    return rg.Vector3d(float(data[0]), float(data[1]), float(data[2]))


def rect_info_to_data(rect):
    return {
        "center": _point_to_data(rect["center"]),
        "u": _vector_to_data(rect["u"]),
        "v": _vector_to_data(rect["v"]),
        "length": float(rect["length"]),
        "width": float(rect["width"]),
        "base_z": float(rect["base_z"])
    }


def rect_info_from_data(data):
    rect = {
        "center": _point_from_data(data["center"]),
        "u": _vector_from_data(data["u"]),
        "v": _vector_from_data(data["v"]),
        "length": float(data["length"]),
        "width": float(data["width"]),
        "base_z": float(data["base_z"])
    }
    rect["curve"] = make_rectangle_curve_from_info(rect)
    return rect


def normalize_door_codes(codes, floor_count, legacy_door_type=None):
    floor_count = max(1, int(floor_count))
    if not codes:
        fill = DOOR_CODE_THROUGH if legacy_door_type == "Through" else DOOR_CODE_FRONT
        codes = [fill] * floor_count
    cleaned = []
    for code in codes:
        c = str(code).strip().upper()
        if c not in VALID_DOOR_CODES:
            c = DOOR_CODE_FRONT
        cleaned.append(c)
    while len(cleaned) < floor_count:
        cleaned.append(DOOR_CODE_FRONT)
    return cleaned[:floor_count]


def normalize_params(params):
    defaults = GlassElevatorDialog.default_params_static()
    if params:
        for key, value in params.items():
            if key != "beam_r":
                defaults[key] = value
    if "beam_r" in defaults:
        del defaults["beam_r"]
    floor_count = max(1, len(defaults.get("floor_levels", [])) - 1)
    defaults["door_codes"] = normalize_door_codes(
        defaults.get("door_codes", []),
        floor_count,
        defaults.get("door_type", None)
    )
    return defaults


def get_car_z_from_params(params):
    levels = sorted(params["floor_levels"])
    min_z = levels[0]
    max_z = levels[-2] if len(levels) >= 2 else min_z
    if max_z < min_z:
        max_z = min_z
    ratio = float(params.get("car_slider", 0)) / 1000.0
    return min_z + (max_z - min_z) * ratio


def make_state(rect, params):
    return {
        "version": 1,
        "rect": rect_info_to_data(rect),
        "params": normalize_params(params)
    }


def encode_state(rect, params):
    return json.dumps(make_state(rect, params), ensure_ascii=False)


def decode_state(text):
    if not text:
        return None
    try:
        state = json.loads(text)
        rect = rect_info_from_data(state["rect"])
        params = normalize_params(state.get("params", {}))
        return rect, params
    except:
        return None


def remember_state(rect, params):
    if not rect or not params:
        return
    try:
        sc.sticky[LAST_STATE_KEY] = encode_state(rect, params)
    except:
        pass


def get_last_params():
    try:
        text = ""
        if sc.sticky.has_key(LAST_STATE_KEY):
            text = sc.sticky[LAST_STATE_KEY]
        state = decode_state(text)
        if state:
            return state[1]
    except:
        pass
    return None


def get_state_from_object(obj):
    if not obj:
        return None
    try:
        return decode_state(obj.Attributes.GetUserString(METADATA_KEY))
    except:
        return None


def get_generated_group_member_ids(doc, obj):
    ids = []
    if not doc or not obj:
        return ids
    try:
        group_indices = obj.Attributes.GetGroupList()
    except:
        group_indices = None
    if group_indices:
        for group_index in group_indices:
            try:
                members = doc.Groups.GroupMembers(group_index)
            except:
                members = None
            if not members:
                continue
            for member in members:
                try:
                    if member.Attributes.GetUserString(METADATA_KEY):
                        ids.append(member.Id)
                except:
                    pass
    if not ids:
        try:
            ids.append(obj.Id)
        except:
            pass
    unique = []
    seen = set()
    for gid in ids:
        key = str(gid)
        if key not in seen:
            unique.append(gid)
            seen.add(key)
    return unique


def _find_doc_object(doc, gid):
    try:
        return doc.Objects.FindId(gid)
    except:
        try:
            return doc.Objects.Find(gid)
        except:
            return None


def _brep_center(brep):
    if not brep:
        return None
    try:
        bbox = brep.GetBoundingBox(True)
        if bbox.IsValid:
            return bbox.Center
    except:
        pass
    return None


def _doc_object_center(obj):
    if not obj or not obj.Geometry:
        return None
    return _brep_center(obj.Geometry)


def _item_index_from_object(obj):
    try:
        text = obj.Attributes.GetUserString(ITEM_INDEX_KEY)
        if text is None or text == "":
            return None
        return int(text)
    except:
        return None


def _fit_planar_rigid_transform(original_points, current_points):
    if not original_points or not current_points or len(original_points) != len(current_points):
        return None
    count = len(original_points)
    ox = sum([p.X for p in original_points]) / float(count)
    oy = sum([p.Y for p in original_points]) / float(count)
    oz = sum([p.Z for p in original_points]) / float(count)
    cx = sum([p.X for p in current_points]) / float(count)
    cy = sum([p.Y for p in current_points]) / float(count)
    cz = sum([p.Z for p in current_points]) / float(count)

    dot_sum = 0.0
    cross_sum = 0.0
    for op, cp in zip(original_points, current_points):
        ax = op.X - ox
        ay = op.Y - oy
        bx = cp.X - cx
        by = cp.Y - cy
        dot_sum += ax * bx + ay * by
        cross_sum += ax * by - ay * bx

    angle = math.atan2(cross_sum, dot_sum) if abs(dot_sum) > 0.000001 or abs(cross_sum) > 0.000001 else 0.0
    cos_a = math.cos(angle)
    sin_a = math.sin(angle)
    return {
        "orig_center": rg.Point3d(ox, oy, oz),
        "cur_center": rg.Point3d(cx, cy, cz),
        "cos": cos_a,
        "sin": sin_a
    }


def _transform_point_xy(point, xform):
    oc = xform["orig_center"]
    cc = xform["cur_center"]
    dx = point.X - oc.X
    dy = point.Y - oc.Y
    return rg.Point3d(
        cc.X + xform["cos"] * dx - xform["sin"] * dy,
        cc.Y + xform["sin"] * dx + xform["cos"] * dy,
        point.Z + (cc.Z - oc.Z)
    )


def _transform_vector_xy(vector, xform):
    return rg.Vector3d(
        xform["cos"] * vector.X - xform["sin"] * vector.Y,
        xform["sin"] * vector.X + xform["cos"] * vector.Y,
        vector.Z
    )


def transform_rect_from_current_objects(doc, rect, params, target_ids):
    if not target_ids:
        return rect
    try:
        car_z = get_car_z_from_params(params)
        original_items = build_static_geometry(rect, params) + create_car_geometry(rect, params, car_z)
    except:
        return rect

    current_by_index = {}
    for gid in target_ids:
        obj = _find_doc_object(doc, gid)
        idx = _item_index_from_object(obj)
        if idx is None:
            continue
        center = _doc_object_center(obj)
        if center:
            current_by_index[idx] = center

    original_points = []
    current_points = []
    for idx, current_center in current_by_index.items():
        if idx < 0 or idx >= len(original_items):
            continue
        original_center = _brep_center(original_items[idx].get("brep", None))
        if not original_center:
            continue
        original_points.append(original_center)
        current_points.append(current_center)

    if len(original_points) < 2:
        return rect
    xform = _fit_planar_rigid_transform(original_points, current_points)
    if not xform:
        return rect

    transformed = dict(rect)
    transformed["center"] = _transform_point_xy(rect["center"], xform)
    transformed["u"] = _safe_unitize(_transform_vector_xy(rect["u"], xform), rect["u"])
    transformed["v"] = _safe_unitize(_transform_vector_xy(rect["v"], xform), rect["v"])
    transformed["base_z"] = float(rect["base_z"]) + (xform["cur_center"].Z - xform["orig_center"].Z)
    transformed["curve"] = make_rectangle_curve_from_info(transformed)
    return transformed


def get_side_data(rect, side):
    half_l = rect["length"] * 0.5
    half_w = rect["width"] * 0.5
    u = rect["u"]
    v = rect["v"]

    if side == SIDE_FRONT:
        return {
            "side": side,
            "tangent": rg.Vector3d(u),
            "outward": rg.Vector3d(v),
            "inward": _neg(v),
            "constant_axis": "y",
            "constant": half_w,
            "start_coord": -half_l,
            "width": rect["length"]
        }
    if side == SIDE_RIGHT:
        return {
            "side": side,
            "tangent": _neg(v),
            "outward": rg.Vector3d(u),
            "inward": _neg(u),
            "constant_axis": "x",
            "constant": half_l,
            "start_coord": half_w,
            "width": rect["width"]
        }
    if side == SIDE_BACK:
        return {
            "side": side,
            "tangent": _neg(u),
            "outward": _neg(v),
            "inward": rg.Vector3d(v),
            "constant_axis": "y",
            "constant": -half_w,
            "start_coord": half_l,
            "width": rect["length"]
        }
    # SIDE_LEFT
    return {
        "side": side,
        "tangent": rg.Vector3d(v),
        "outward": _neg(u),
        "inward": rg.Vector3d(u),
        "constant_axis": "x",
        "constant": -half_l,
        "start_coord": -half_w,
        "width": rect["width"]
    }


def side_point(rect, side_data, along, inward_offset, z):
    # along is distance from the side start point along side_data["tangent"].
    tangent = side_data["tangent"]
    inward = side_data["inward"]
    side = side_data["side"]
    half_l = rect["length"] * 0.5
    half_w = rect["width"] * 0.5

    if side == SIDE_FRONT:
        base_x = -half_l
        base_y = half_w
        x = base_x + along
        y = base_y
    elif side == SIDE_RIGHT:
        base_x = half_l
        base_y = half_w
        x = base_x
        y = base_y - along
    elif side == SIDE_BACK:
        base_x = half_l
        base_y = -half_w
        x = base_x - along
        y = base_y
    else:
        base_x = -half_l
        base_y = -half_w
        x = base_x
        y = base_y + along

    p = local_to_world(rect, x, y, z)
    return p + inward * inward_offset


def _make_box(center, x_axis, y_axis, z_axis, sx, sy, sz):
    if sx <= 0.001 or sy <= 0.001 or sz <= 0.001:
        return None
    ax = _safe_unitize(x_axis, rg.Vector3d(1, 0, 0))
    ay = _safe_unitize(y_axis, rg.Vector3d(0, 1, 0))
    az = _safe_unitize(z_axis, rg.Vector3d(0, 0, 1))
    c = rg.Point3d(center)
    hx = sx * 0.5
    hy = sy * 0.5
    hz = sz * 0.5

    p000 = c - ax * hx - ay * hy - az * hz
    p100 = c + ax * hx - ay * hy - az * hz
    p110 = c + ax * hx + ay * hy - az * hz
    p010 = c - ax * hx + ay * hy - az * hz
    p001 = c - ax * hx - ay * hy + az * hz
    p101 = c + ax * hx - ay * hy + az * hz
    p111 = c + ax * hx + ay * hy + az * hz
    p011 = c - ax * hx + ay * hy + az * hz

    faces = []
    tol = Rhino.RhinoDoc.ActiveDoc.ModelAbsoluteTolerance if Rhino.RhinoDoc.ActiveDoc else 0.01
    try:
        faces.append(rg.Brep.CreateFromCornerPoints(p000, p100, p110, p010, tol))
        faces.append(rg.Brep.CreateFromCornerPoints(p001, p011, p111, p101, tol))
        faces.append(rg.Brep.CreateFromCornerPoints(p000, p001, p101, p100, tol))
        faces.append(rg.Brep.CreateFromCornerPoints(p100, p101, p111, p110, tol))
        faces.append(rg.Brep.CreateFromCornerPoints(p110, p111, p011, p010, tol))
        faces.append(rg.Brep.CreateFromCornerPoints(p010, p011, p001, p000, tol))
        faces = [f for f in faces if f]
        joined = rg.Brep.JoinBreps(faces, tol)
        if joined and len(joined) > 0:
            return joined[0]
    except:
        pass
    return None


def add_item(items, layer, brep):
    if brep:
        items.append({"layer": layer, "brep": brep})


def ensure_layer(doc, layer_name):
    idx = doc.Layers.FindByFullPath(layer_name, True)
    if idx >= 0:
        return idx
    layer = rdo.Layer()
    layer.Name = layer_name
    return doc.Layers.Add(layer)


def add_brep_to_layer(doc, brep, layer_name, state_json=None, item_index=None):
    layer_index = ensure_layer(doc, layer_name)
    attr = rdo.ObjectAttributes()
    attr.LayerIndex = layer_index
    if state_json:
        try:
            attr.SetUserString(METADATA_KEY, state_json)
        except:
            pass
    if item_index is not None:
        try:
            attr.SetUserString(ITEM_INDEX_KEY, str(int(item_index)))
        except:
            pass
    return doc.Objects.AddBrep(brep, attr)

# ==============================================================================
# Geometry generation: glass / frames
# ==============================================================================
def get_glass_inset(params):
    if params.get("use_glass_frame", True):
        return GLASS_MULLION_SIZE
    return 0.0


def get_structure_outer_offset(params):
    # Structure must not touch the glass. The gap is measured after the glass inner face.
    glass_inset = get_glass_inset(params)
    return glass_inset + GLASS_THICKNESS + GLASS_STRUCTURE_GAP


def get_column_size(params):
    return max(params["beam_H"], params["beam_B"])


def get_structure_inner_offset(params):
    return get_structure_outer_offset(params) + get_column_size(params)


def create_glass_panel(items, rect, side_data, along_center, panel_width, z0, z1, glass_inset):
    if panel_width <= 1.0 or z1 <= z0:
        return
    zmid = (z0 + z1) * 0.5
    h = z1 - z0
    p_outer = side_point(rect, side_data, along_center, glass_inset, zmid)
    center = p_outer + side_data["inward"] * (GLASS_THICKNESS * 0.5)
    brep = _make_box(center, side_data["tangent"], side_data["inward"], rg.Vector3d.ZAxis,
                     panel_width, GLASS_THICKNESS, h)
    add_item(items, LAYER_GLASS, brep)


def create_frame_member(items, rect, side_data, along_center, member_width, depth, z0, z1):
    if z1 <= z0:
        return
    wall_width = side_data["width"]
    half_member = member_width * 0.5
    if wall_width > member_width:
        along_center = min(max(along_center, half_member), wall_width - half_member)
    else:
        along_center = wall_width * 0.5
    zmid = (z0 + z1) * 0.5
    h = z1 - z0
    p_outer = side_point(rect, side_data, along_center, 0.0, zmid)
    center = p_outer + side_data["inward"] * (depth * 0.5)
    brep = _make_box(center, side_data["tangent"], side_data["inward"], rg.Vector3d.ZAxis,
                     member_width, depth, h)
    add_item(items, LAYER_FRAME, brep)


def create_top_frame(items, rect, side_data, z_top):
    width = side_data["width"]
    along_center = width * 0.5
    p_outer = side_point(rect, side_data, along_center, 0.0, z_top - GLASS_MULLION_SIZE * 0.5)
    center = p_outer + side_data["inward"] * (GLASS_MULLION_SIZE * 0.5)
    brep = _make_box(center, side_data["tangent"], side_data["inward"], rg.Vector3d.ZAxis,
                     width, GLASS_MULLION_SIZE, GLASS_MULLION_SIZE)
    add_item(items, LAYER_FRAME, brep)


def create_glass_wall(items, rect, side, z0, z1, params):
    if z1 <= z0:
        return
    side_data = get_side_data(rect, side)
    wall_width = side_data["width"]
    n = max(1, int(params["glass_divisions"]))

    if params.get("use_glass_frame", True):
        # Framed type: vertical frame list 0..n, but the last position is not generated.
        segment = wall_width / float(n)
        for i in range(n + 1):
            if i == n:
                continue
            if i == 0:
                frame_w = GLASS_CORNER_MULLION_SIZE
                frame_depth = GLASS_CORNER_MULLION_SIZE
            else:
                frame_w = GLASS_MULLION_SIZE
                frame_depth = GLASS_MULLION_SIZE
            along = i * segment
            create_frame_member(items, rect, side_data, along, frame_w, frame_depth, z0, z1)

        create_top_frame(items, rect, side_data, z1)

        # Glass panels are fitted between the theoretical frame positions.
        for i in range(n):
            start = i * segment
            end = (i + 1) * segment
            start_frame = GLASS_CORNER_MULLION_SIZE if i == 0 else GLASS_MULLION_SIZE
            end_frame = GLASS_CORNER_MULLION_SIZE if i == n - 1 else GLASS_MULLION_SIZE
            panel_start = start + (start_frame if i == 0 else start_frame * 0.5)
            panel_end = end - (end_frame if i == n - 1 else end_frame * 0.5)
            panel_w = panel_end - panel_start
            if panel_w <= 1.0:
                continue
            along_center = (panel_start + panel_end) * 0.5
            create_glass_panel(items, rect, side_data, along_center, panel_w, z0, z1, GLASS_MULLION_SIZE)
    else:
        # Frameless type: glass outer face matches the shaft reference line.
        total_gap = GLASS_PANEL_GAP * float(max(0, n - 1))
        panel_w = (wall_width - total_gap) / float(n)
        if panel_w <= 1.0:
            return
        pos = 0.0
        for i in range(n):
            along_center = pos + panel_w * 0.5
            create_glass_panel(items, rect, side_data, along_center, panel_w, z0, z1, 0.0)
            pos += panel_w + GLASS_PANEL_GAP


def create_solid_cap(items, rect, z_top, params):
    thickness = max(1.0, float(params.get("cap_thickness", 200.0)))
    center = local_to_world(rect, 0.0, 0.0, z_top + thickness * 0.5)
    brep = _make_box(center, rect["u"], rect["v"], rg.Vector3d.ZAxis,
                     rect["length"], rect["width"], thickness)
    add_item(items, LAYER_CAP, brep)


def create_glass_cap(items, rect, z_top, params):
    n = max(1, int(params.get("glass_divisions", 1)))
    length = rect["length"]
    width = rect["width"]
    half_l = length * 0.5
    half_w = width * 0.5
    z_glass = z_top + GLASS_THICKNESS * 0.5
    u = rect["u"]
    v = rect["v"]

    if params.get("use_glass_frame", True):
        perimeter = min(GLASS_CORNER_MULLION_SIZE, length * 0.5, width * 0.5)
        frame_h = GLASS_MULLION_SIZE
        z_frame = z_top + frame_h * 0.5

        frame_specs = [
            (0.0, half_w - perimeter * 0.5, length, perimeter),
            (0.0, -half_w + perimeter * 0.5, length, perimeter),
            (-half_l + perimeter * 0.5, 0.0, perimeter, max(1.0, width - 2.0 * perimeter)),
            (half_l - perimeter * 0.5, 0.0, perimeter, max(1.0, width - 2.0 * perimeter))
        ]
        for x, y, sx, sy in frame_specs:
            center = local_to_world(rect, x, y, z_frame)
            add_item(items, LAYER_FRAME, _make_box(center, u, v, rg.Vector3d.ZAxis, sx, sy, frame_h))

        inner_l = length - 2.0 * perimeter
        inner_w = width - 2.0 * perimeter
        if inner_l <= 1.0 or inner_w <= 1.0:
            return

        segment = inner_l / float(n)
        for i in range(1, n):
            x = -half_l + perimeter + segment * float(i)
            center = local_to_world(rect, x, 0.0, z_frame)
            add_item(items, LAYER_FRAME, _make_box(center, u, v, rg.Vector3d.ZAxis,
                                                   GLASS_MULLION_SIZE, inner_w, frame_h))

        for i in range(n):
            start = -half_l + perimeter + segment * float(i)
            end = -half_l + perimeter + segment * float(i + 1)
            if i > 0:
                start += GLASS_MULLION_SIZE * 0.5
            if i < n - 1:
                end -= GLASS_MULLION_SIZE * 0.5
            panel_l = end - start
            if panel_l <= 1.0:
                continue
            center = local_to_world(rect, (start + end) * 0.5, 0.0, z_glass)
            add_item(items, LAYER_GLASS, _make_box(center, u, v, rg.Vector3d.ZAxis,
                                                   panel_l, inner_w, GLASS_THICKNESS))
    else:
        total_gap = GLASS_PANEL_GAP * float(max(0, n - 1))
        panel_l = (length - total_gap) / float(n)
        if panel_l <= 1.0:
            return
        x = -half_l
        for i in range(n):
            center_x = x + panel_l * 0.5
            center = local_to_world(rect, center_x, 0.0, z_glass)
            add_item(items, LAYER_GLASS, _make_box(center, u, v, rg.Vector3d.ZAxis,
                                                   panel_l, width, GLASS_THICKNESS))
            x += panel_l + GLASS_PANEL_GAP


def create_top_cap(items, rect, z_top, params):
    cap_type = params.get("cap_type", CAP_TYPE_NONE)
    if cap_type == CAP_TYPE_SOLID:
        create_solid_cap(items, rect, z_top, params)
    elif cap_type == CAP_TYPE_GLASS:
        create_glass_cap(items, rect, z_top, params)


def create_door_wall(items, rect, side, z0, z1, params):
    if z1 <= z0:
        return
    side_data = get_side_data(rect, side)
    wall_width = side_data["width"]
    glass_width = min(max(0.0, params["door_side_glass_width"]), wall_width * 0.45)
    door_width = wall_width - glass_width * 2.0
    if door_width < 600.0:
        door_width = max(200.0, wall_width * 0.6)
        glass_width = (wall_width - door_width) * 0.5

    glass_inset = get_glass_inset(params)
    opening_depth = get_structure_inner_offset(params)

    # Side glass panels
    if glass_width > 1.0:
        create_glass_panel(items, rect, side_data, glass_width * 0.5, glass_width, z0, z1, glass_inset)
        create_glass_panel(items, rect, side_data, wall_width - glass_width * 0.5, glass_width, z0, z1, glass_inset)

    # Optional corner frame and top frame continuity when framed glass is enabled.
    if params.get("use_glass_frame", True):
        create_frame_member(items, rect, side_data, 0.0, GLASS_CORNER_MULLION_SIZE,
                            GLASS_CORNER_MULLION_SIZE, z0, z1)
        create_top_frame(items, rect, side_data, z1)

    # Door opening coordinates, centered in the wall.
    opening_start = glass_width
    opening_end = wall_width - glass_width
    opening_center = (opening_start + opening_end) * 0.5

    # ㄷ-shaped portal frame: left jamb, right jamb, top header.
    frame_t = DOOR_FRAME_THICKNESS
    jamb_h = z1 - z0
    left_center_along = opening_start - frame_t * 0.5
    right_center_along = opening_end + frame_t * 0.5
    zmid = (z0 + z1) * 0.5

    for along in [left_center_along, right_center_along]:
        p_outer = side_point(rect, side_data, along, 0.0, zmid)
        center = p_outer + side_data["inward"] * (opening_depth * 0.5)
        brep = _make_box(center, side_data["tangent"], side_data["inward"], rg.Vector3d.ZAxis,
                         frame_t, opening_depth, jamb_h)
        add_item(items, LAYER_FRAME, brep)

    top_center_along = opening_center
    top_width = door_width + frame_t * 2.0
    p_outer = side_point(rect, side_data, top_center_along, 0.0, z1 - frame_t * 0.5)
    center = p_outer + side_data["inward"] * (opening_depth * 0.5)
    brep = _make_box(center, side_data["tangent"], side_data["inward"], rg.Vector3d.ZAxis,
                     top_width, opening_depth, frame_t)
    add_item(items, LAYER_FRAME, brep)

    p_outer = side_point(rect, side_data, top_center_along, 0.0, z0 - frame_t * 0.5)
    center = p_outer + side_data["inward"] * (opening_depth * 0.5)
    brep = _make_box(center, side_data["tangent"], side_data["inward"], rg.Vector3d.ZAxis,
                     top_width, opening_depth, frame_t)
    add_item(items, LAYER_FRAME, brep)

    # Recessed elevator door panels at structural inner face.
    door_t = 30.0
    gap = 10.0
    leaf_w = max(10.0, (door_width - gap) * 0.5)
    for sign in [-1.0, 1.0]:
        along = opening_center + sign * (leaf_w * 0.5 + gap * 0.25)
        p_face = side_point(rect, side_data, along, opening_depth, zmid)
        center = p_face + side_data["inward"] * (door_t * 0.5)
        brep = _make_box(center, side_data["tangent"], side_data["inward"], rg.Vector3d.ZAxis,
                         leaf_w, door_t, jamb_h)
        add_item(items, LAYER_DOOR, brep)

    # Center door line / mullion
    p_face = side_point(rect, side_data, opening_center, opening_depth, zmid)
    center = p_face + side_data["inward"] * (door_t * 0.5)
    brep = _make_box(center, side_data["tangent"], side_data["inward"], rg.Vector3d.ZAxis,
                     12.0, door_t + 2.0, jamb_h)
    add_item(items, LAYER_FRAME, brep)

# ==============================================================================
# Geometry generation: structural members
# ==============================================================================
def create_rect_member(items, layer, center, axis_len, axis_depth, axis_z, length, depth, height):
    brep = _make_box(center, axis_len, axis_depth, axis_z, length, depth, height)
    add_item(items, layer, brep)


def create_h_beam(items, center, axis_len, axis_depth, length, H, B, t):
    # Beam length along axis_len, cross-section: B in depth direction, H vertical.
    t = max(1.0, min(t, H * 0.45, B * 0.45))
    web_h = max(1.0, H - 2.0 * t)
    # z origin center is entire section center. Beam top/bottom are +/- H/2.
    top_c = center + rg.Vector3d.ZAxis * (H * 0.5 - t * 0.5)
    bot_c = center - rg.Vector3d.ZAxis * (H * 0.5 - t * 0.5)
    web_c = center
    create_rect_member(items, LAYER_BEAM, top_c, axis_len, axis_depth, rg.Vector3d.ZAxis, length, B, t)
    create_rect_member(items, LAYER_BEAM, bot_c, axis_len, axis_depth, rg.Vector3d.ZAxis, length, B, t)
    create_rect_member(items, LAYER_BEAM, web_c, axis_len, axis_depth, rg.Vector3d.ZAxis, length, t, web_h)


def create_h_column(items, center, axis_x, axis_y, height, size, t):
    # Column H-section extruded vertically. axis_x/axis_y define local profile axes.
    t = max(1.0, min(t, size * 0.45))
    web_h = max(1.0, size - 2.0 * t)
    flange1_c = center + axis_y * (size * 0.5 - t * 0.5)
    flange2_c = center - axis_y * (size * 0.5 - t * 0.5)
    create_rect_member(items, LAYER_COLUMN, flange1_c, axis_x, axis_y, rg.Vector3d.ZAxis, size, t, height)
    create_rect_member(items, LAYER_COLUMN, flange2_c, axis_x, axis_y, rg.Vector3d.ZAxis, size, t, height)
    create_rect_member(items, LAYER_COLUMN, center, axis_x, axis_y, rg.Vector3d.ZAxis, t, web_h, height)


def create_structure_beam_ring(items, rect, z_center, params):
    col_size = get_column_size(params)
    outer = get_structure_outer_offset(params)
    offset_center = outer + col_size * 0.5
    half_l = rect["length"] * 0.5
    half_w = rect["width"] * 0.5
    u = rect["u"]
    v = rect["v"]
    use_h = params["beam_t"] > 0.0
    t = params["beam_t"]
    beam_H = params["beam_H"]
    beam_B = params["beam_B"]

    # Beam length rule, top-view 기준:
    # - Front / Back beams are horizontal beams. They touch the column web.
    # - Left / Right beams are vertical beams. They touch the column flange.
    # The base span below is the distance between column centerlines.
    span_horizontal = max(1.0, rect["length"] - 2.0 * offset_center)
    span_vertical = max(1.0, rect["width"] - 2.0 * offset_center)

    vertical_beam_length = span_vertical - col_size
    if t > 0.0:
        # Use the effective column web thickness used by H-column generation.
        contact_t = max(1.0, min(t, col_size * 0.45))
        horizontal_beam_length = (span_horizontal - col_size) + (col_size - contact_t)
    else:
        contact_t = 0.0
        horizontal_beam_length = span_horizontal - col_size

    horizontal_beam_length = max(1.0, horizontal_beam_length)
    vertical_beam_length = max(1.0, vertical_beam_length)

    beam_specs = [
        # Front / Back: horizontal beams, 좌우 방향, column web contact rule.
        (0.0, half_w - offset_center, u, v, horizontal_beam_length),
        # Right / Left: vertical beams, 앞뒤 방향, column flange contact rule.
        (half_l - offset_center, 0.0, _neg(v), u, vertical_beam_length),
        (0.0, -half_w + offset_center, _neg(u), _neg(v), horizontal_beam_length),
        (-half_l + offset_center, 0.0, v, _neg(u), vertical_beam_length)
    ]
    for x, y, axis_len, axis_depth, length in beam_specs:
        c = local_to_world(rect, x, y, z_center)
        if use_h:
            create_h_beam(items, c, axis_len, axis_depth, length, beam_H, beam_B, t)
        else:
            create_rect_member(items, LAYER_BEAM, c, axis_len, axis_depth, rg.Vector3d.ZAxis,
                               length, beam_B, beam_H)


def create_structure_for_bay(items, rect, z0, z1, params):
    if z1 <= z0:
        return
    col_size = get_column_size(params)
    outer = get_structure_outer_offset(params)
    offset_center = outer + col_size * 0.5
    half_l = rect["length"] * 0.5
    half_w = rect["width"] * 0.5
    u = rect["u"]
    v = rect["v"]
    h = z1 - z0
    zmid = (z0 + z1) * 0.5

    use_h = params["beam_t"] > 0.0
    t = params["beam_t"]

    # Columns at four corners.
    corner_locals = [
        (-half_l + offset_center, half_w - offset_center),
        (half_l - offset_center, half_w - offset_center),
        (half_l - offset_center, -half_w + offset_center),
        (-half_l + offset_center, -half_w + offset_center)
    ]
    for x, y in corner_locals:
        c = local_to_world(rect, x, y, zmid)
        if use_h:
            create_h_column(items, c, u, v, h, col_size, t)
        else:
            create_rect_member(items, LAYER_COLUMN, c, u, v, rg.Vector3d.ZAxis, col_size, col_size, h)

    # Beams: top face is lowered from z1 by a fixed offset.
    beam_H = params["beam_H"]
    z_center = z1 - STRUCTURE_BEAM_DROP - beam_H * 0.5
    create_structure_beam_ring(items, rect, z_center, params)

# ==============================================================================
# Geometry generation: Car
# ==============================================================================
def create_car_geometry(rect, params, car_z0):
    items = []
    car_h = params["door_zone_height"]
    if car_h <= 100.0:
        return items

    inner_offset = get_structure_inner_offset(params)
    car_inset = inner_offset + CAR_CLEARANCE
    car_w = rect["length"] - car_inset * 2.0
    car_d = rect["width"] - car_inset * 2.0
    if car_w <= 300.0 or car_d <= 300.0:
        return items

    u = rect["u"]
    v = rect["v"]
    center_xy = local_to_world(rect, 0.0, 0.0, 0.0)
    floor_t = max(1.0, float(params.get("car_floor_thickness", CAR_FLOOR_THICKNESS)))
    ceiling_t = max(1.0, float(params.get("car_ceiling_thickness", CAR_CEILING_THICKNESS)))

    # Floor grows downward from car_z0; ceiling grows upward from car_z0 + car_h.
    floor_c = rg.Point3d(center_xy.X, center_xy.Y, rect["base_z"] + car_z0 - floor_t * 0.5)
    ceil_c = rg.Point3d(center_xy.X, center_xy.Y, rect["base_z"] + car_z0 + car_h + ceiling_t * 0.5)
    add_item(items, LAYER_CAR, _make_box(floor_c, u, v, rg.Vector3d.ZAxis, car_w, car_d, floor_t))
    add_item(items, LAYER_CAR, _make_box(ceil_c, u, v, rg.Vector3d.ZAxis, car_w, car_d, ceiling_t))

    wall_z0 = car_z0
    wall_z1 = car_z0 + car_h
    if wall_z1 <= wall_z0:
        return items
    wall_h = wall_z1 - wall_z0
    zmid = (wall_z0 + wall_z1) * 0.5
    car_half_l = car_w * 0.5
    car_half_w = car_d * 0.5

    # Local helper for car side point.
    def car_point(x, y, z):
        c = rect["center"]
        return rg.Point3d(c.X + u.X * x + v.X * y, c.Y + u.Y * x + v.Y * y, rect["base_z"] + z)

    front_side = int(params["door_direction_index"])
    door_sides = get_car_door_sides(params)

    # Door width follows shaft door width but is clamped to car wall.
    door_side_glass = params["door_side_glass_width"]
    door_ref_side = door_sides[0] if door_sides else front_side
    shaft_front_width = rect["length"] if door_ref_side in [SIDE_FRONT, SIDE_BACK] else rect["width"]
    shaft_door_width = max(600.0, shaft_front_width - 2.0 * door_side_glass)

    # Four car walls / doors
    side_defs = [
        (SIDE_FRONT, car_w, car_half_w, u, _neg(v), "front"),
        (SIDE_RIGHT, car_d, car_half_l, _neg(v), _neg(u), "right"),
        (SIDE_BACK, car_w, -car_half_w, _neg(u), v, "back"),
        (SIDE_LEFT, car_d, -car_half_l, v, u, "left")
    ]

    for side, side_width, const_val, tangent, inward, name in side_defs:
        is_door = side in door_sides
        if side == SIDE_FRONT:
            base = car_point(0.0, car_half_w, zmid)
        elif side == SIDE_RIGHT:
            base = car_point(car_half_l, 0.0, zmid)
        elif side == SIDE_BACK:
            base = car_point(0.0, -car_half_w, zmid)
        else:
            base = car_point(-car_half_l, 0.0, zmid)

        if is_door:
            door_w = min(shaft_door_width, max(300.0, side_width - 300.0))
            leaf_w = (door_w - 10.0) * 0.5
            for sign in [-1.0, 1.0]:
                c = base + tangent * (sign * (leaf_w * 0.5 + 2.5)) + inward * (GLASS_THICKNESS * 0.5)
                add_item(items, LAYER_CAR, _make_box(c, tangent, inward, rg.Vector3d.ZAxis,
                                                     leaf_w, GLASS_THICKNESS, wall_h))
            c = base + inward * (GLASS_THICKNESS * 0.5)
            add_item(items, LAYER_CAR, _make_box(c, tangent, inward, rg.Vector3d.ZAxis,
                                                 12.0, GLASS_THICKNESS + 2.0, wall_h))
        else:
            c = base + inward * (GLASS_THICKNESS * 0.5)
            add_item(items, LAYER_CAR, _make_box(c, tangent, inward, rg.Vector3d.ZAxis,
                                                 side_width, GLASS_THICKNESS, wall_h))

    # Car corner frames.
    corner_h = car_h + floor_t + ceiling_t
    corner_zmid = car_z0 + (car_h + ceiling_t - floor_t) * 0.5
    corners = [
        (-car_half_l, -car_half_w),
        (car_half_l, -car_half_w),
        (car_half_l, car_half_w),
        (-car_half_l, car_half_w)
    ]
    for x, y in corners:
        c = car_point(x, y, corner_zmid)
        add_item(items, LAYER_CAR, _make_box(c, u, v, rg.Vector3d.ZAxis,
                                             CAR_FRAME_SIZE, CAR_FRAME_SIZE, corner_h))

    return items

# ==============================================================================
# Geometry generation: full static model
# ==============================================================================
def get_door_code_for_bay(params, bay_index):
    floor_count = max(1, len(params.get("floor_levels", [])) - 1)
    codes = normalize_door_codes(params.get("door_codes", []), floor_count, params.get("door_type", None))
    if bay_index < 0:
        bay_index = 0
    if bay_index >= len(codes):
        bay_index = len(codes) - 1
    return codes[bay_index]


def get_bay_index_from_z(params, z_value):
    levels = sorted(params["floor_levels"])
    if len(levels) < 2:
        return 0
    for i in range(len(levels) - 1):
        if z_value < levels[i + 1]:
            return i
    return max(0, len(levels) - 2)


def get_door_sides(params, bay_index=0):
    front_side = int(params["door_direction_index"])
    code = get_door_code_for_bay(params, bay_index)
    if code == DOOR_CODE_NONE:
        return []
    if code == DOOR_CODE_BACK:
        return [(front_side + 2) % 4]
    if code == DOOR_CODE_THROUGH:
        return [front_side, (front_side + 2) % 4]
    return [front_side]


def get_car_door_sides(params):
    front_side = int(params["door_direction_index"])
    back_side = (front_side + 2) % 4
    floor_count = max(1, len(params.get("floor_levels", [])) - 1)
    codes = normalize_door_codes(params.get("door_codes", []), floor_count, params.get("door_type", None))

    if DOOR_CODE_THROUGH in codes:
        return [front_side, back_side]

    sides = []
    if DOOR_CODE_FRONT in codes:
        sides.append(front_side)
    if DOOR_CODE_BACK in codes:
        sides.append(back_side)
    return sides


def build_static_geometry(rect, params):
    items = []
    floor_levels = params["floor_levels"]
    door_h = params["door_zone_height"]

    for i in range(len(floor_levels) - 1):
        z_floor = floor_levels[i]
        z_next = floor_levels[i + 1]
        z_door_top = z_floor + door_h
        door_sides = get_door_sides(params, i)

        # Door zone: door walls or glass walls.
        for side in [SIDE_FRONT, SIDE_RIGHT, SIDE_BACK, SIDE_LEFT]:
            if side in door_sides:
                create_door_wall(items, rect, side, z_floor, z_door_top, params)
            else:
                create_glass_wall(items, rect, side, z_floor, z_door_top, params)

        # Spandrel zone: all glass.
        if z_next > z_door_top:
            for side in [SIDE_FRONT, SIDE_RIGHT, SIDE_BACK, SIDE_LEFT]:
                create_glass_wall(items, rect, side, z_door_top, z_next, params)

        # Structure module: columns + upper beams.
        create_structure_for_bay(items, rect, z_floor, z_next, params)
        if z_next > z_door_top:
            create_structure_beam_ring(items, rect, z_door_top + params["beam_H"] * 0.5, params)

    create_top_cap(items, rect, max(floor_levels), params)
    return items

# ==============================================================================
# Preview conduit
# ==============================================================================
class GlassElevatorPreviewConduit(rd.DisplayConduit):
    def __init__(self):
        super(GlassElevatorPreviewConduit, self).__init__()
        self.static_items = []
        self.car_items = []
        self.materials = {}
        self._init_materials()

    def _make_mat(self, color, transparency):
        m = rd.DisplayMaterial()
        m.Diffuse = color
        m.Transparency = transparency
        return m

    def _init_materials(self):
        self.materials[LAYER_GLASS] = self._make_mat(System.Drawing.Color.LightSkyBlue, 0.65)
        self.materials[LAYER_FRAME] = self._make_mat(System.Drawing.Color.DimGray, 0.10)
        self.materials[LAYER_DOOR] = self._make_mat(System.Drawing.Color.Silver, 0.30)
        self.materials[LAYER_COLUMN] = self._make_mat(System.Drawing.Color.DarkGray, 0.05)
        self.materials[LAYER_BEAM] = self._make_mat(System.Drawing.Color.Gray, 0.05)
        self.materials[LAYER_CAR] = self._make_mat(System.Drawing.Color.LightSteelBlue, 0.35)
        self.materials[LAYER_CAP] = self._make_mat(System.Drawing.Color.Gainsboro, 0.10)

    def SetStaticGeometry(self, items):
        self.static_items = items if items else []

    def SetCarGeometry(self, items):
        self.car_items = items if items else []

    def _draw_items(self, e, items):
        for item in items:
            brep = item.get("brep", None)
            layer = item.get("layer", "")
            if not brep:
                continue
            mat = self.materials.get(layer, self.materials[LAYER_FRAME])
            try:
                e.Display.DrawBrepShaded(brep, mat)
            except:
                pass

    def _draw_wires(self, e, items):
        for item in items:
            brep = item.get("brep", None)
            layer = item.get("layer", "")
            if not brep:
                continue
            if layer == LAYER_GLASS:
                color = System.Drawing.Color.DeepSkyBlue
            elif layer == LAYER_CAR:
                color = System.Drawing.Color.RoyalBlue
            else:
                color = System.Drawing.Color.Black
            try:
                e.Display.DrawBrepWires(brep, color, 1)
            except:
                pass

    def DrawShaded(self, e):
        self._draw_items(e, self.static_items)
        self._draw_items(e, self.car_items)

    def DrawForeground(self, e):
        self._draw_wires(e, self.static_items)
        self._draw_wires(e, self.car_items)

# ==============================================================================
# UI dialog
# ==============================================================================
class GlassElevatorDialog(forms.Form):
    def __init__(self):
        forms.Form.__init__(self)
        self.Title = "유리 엘리베이터 생성기"
        self.Padding = drawing.Padding(12)
        self.Resizable = True
        self.Topmost = False
        self.Owner = Rhino.UI.RhinoEtoApp.MainWindow
        self.ClientSize = drawing.Size(560, 620)

        self.rect = None
        self.conduit = None
        self.static_items = []
        self.car_items = []
        self.params = self.default_params()
        self.door_direction_index = int(self.params["door_direction_index"])
        self.textboxes = {}
        self._suppress_slider = False
        self.edit_target_ids = []

    def SetupData(self, rect_info, params=None, edit_target_ids=None):
        self.rect = rect_info
        if params:
            self.params = normalize_params(params)
        self.door_direction_index = int(self.params["door_direction_index"])
        self.edit_target_ids = edit_target_ids if edit_target_ids else []
        if self.edit_target_ids:
            self.Title = "유리 엘리베이터 수정"
        self.conduit = GlassElevatorPreviewConduit()
        self.conduit.Enabled = True
        self._build_ui()
        self.UpdatePreview()

    def default_params(self):
        return self.default_params_static()

    @staticmethod
    def default_params_static():
        return {
            "floor_levels": [0.0, 4000.0, 8000.0, 12000.0],
            "door_zone_height": 2400.0,
            "door_type": "Single",
            "door_codes": [DOOR_CODE_FRONT, DOOR_CODE_FRONT, DOOR_CODE_FRONT],
            "door_direction_index": 0,
            "door_side_glass_width": 600.0,
            "beam_H": 200.0,
            "beam_B": 150.0,
            "beam_t": 0.0,
            "use_glass_frame": True,
            "glass_divisions": 4,
            "cap_type": CAP_TYPE_SOLID,
            "cap_thickness": 200.0,
            "car_floor_thickness": CAR_FLOOR_THICKNESS,
            "car_ceiling_thickness": CAR_CEILING_THICKNESS,
            "car_slider": 0
        }

    def _make_textbox(self, key, width=120):
        tb = forms.TextBox()
        tb.Text = str(self.params[key])
        tb.Width = width
        tb.KeyDown += self.OnTextBoxKeyDown
        self.textboxes[key] = tb
        return tb

    def _label(self, text):
        label = forms.Label()
        label.Text = text
        return label

    def _button(self, text):
        button = forms.Button()
        button.Text = text
        return button

    def _groupbox(self, text):
        group = forms.GroupBox()
        group.Text = text
        return group

    def _textbox_with_text(self, text, width=None):
        tb = forms.TextBox()
        tb.Text = text
        if width is not None:
            tb.Width = width
        return tb

    def _checkbox(self, text):
        checkbox = forms.CheckBox()
        checkbox.Text = text
        return checkbox

    def _door_direction_text(self):
        labels = ["0° Front", "90° Right", "180° Back", "270° Left"]
        return labels[int(self.door_direction_index) % len(labels)]

    def _build_ui(self):
        layout = forms.DynamicLayout()
        layout.Spacing = drawing.Size(6, 6)

        title = self._label("유리 엘리베이터 생성 옵션")
        title.Font = drawing.Font("Malgun Gothic", 11, drawing.FontStyle.Bold)
        layout.AddRow(title)
        layout.AddRow(self._label("기준 Rectangle: {:.1f} x {:.1f} mm / base Z {:.1f}".format(
            self.rect["length"], self.rect["width"], self.rect["base_z"])))
        layout.AddRow(None)

        # Floor settings
        floor_group = self._groupbox("층 구성")
        floor_layout = forms.DynamicLayout()
        floor_layout.Spacing = drawing.Size(5, 5)

        self.tb_floor_count = self._textbox_with_text("3")
        self.tb_floor_count.Width = 80
        self.tb_floor_height = self._textbox_with_text("4000")
        self.tb_floor_height.Width = 100
        self.tb_floor_count.KeyDown += self.OnTextBoxKeyDown
        self.tb_floor_height.KeyDown += self.OnTextBoxKeyDown
        self.btn_make_levels = self._button("기본 층고로 생성")
        self.btn_make_levels.Click += self.OnMakeDefaultLevels

        row_default = forms.DynamicLayout()
        row_default.BeginHorizontal()
        row_default.Add(self._label("층 수:"))
        row_default.Add(self.tb_floor_count)
        row_default.Add(self._label("기본 층고:"))
        row_default.Add(self.tb_floor_height)
        row_default.Add(self.btn_make_levels)
        row_default.EndHorizontal()
        floor_layout.AddRow(row_default)

        self.ta_levels = forms.TextArea()
        self.ta_levels.Text = self.format_levels(self.params["floor_levels"])
        self.ta_levels.Height = 90
        self.ta_levels.KeyDown += self.OnLevelsKeyDown
        floor_layout.AddRow(self._label("층 바닥 레벨 리스트 (Rectangle 기준 상대 Z, mm):"))
        floor_layout.AddRow(self.ta_levels)

        self.tb_door_zone_height = self._make_textbox("door_zone_height")
        floor_layout.AddRow(self._label("공통 문 구간 높이 (mm):"), self.tb_door_zone_height)

        self.btn_pick_slabs = self._button("기존 슬래브에서 높이 추출")
        self.btn_pick_slabs.Click += self.OnPickSlabHeights
        floor_layout.AddRow(self.btn_pick_slabs)

        self.ta_door_codes = forms.TextArea()
        self.ta_door_codes.Text = self.format_door_codes(self.params.get("door_codes", []))
        self.ta_door_codes.Height = 45
        self.ta_door_codes.KeyDown += self.OnLevelsKeyDown
        floor_layout.AddRow(self._label("층별 문 타입 리스트 (F=정면, B=후면, T=양쪽, N=문 없음):"))
        floor_layout.AddRow(self.ta_door_codes)
        floor_group.Content = floor_layout
        layout.AddRow(floor_group)

        # Door settings
        door_group = self._groupbox("문 설정")
        door_layout = forms.DynamicLayout()
        door_layout.Spacing = drawing.Size(5, 5)
        self.lbl_door_dir = self._label(self._door_direction_text())
        self.btn_rotate_door = self._button("회전")
        self.btn_rotate_door.Width = 80
        self.btn_rotate_door.Click += self.OnRotateDoorDirection
        self.tb_door_side_glass_width = self._make_textbox("door_side_glass_width")
        door_layout.AddRow(self._label("문 방향:"), self.lbl_door_dir, self.btn_rotate_door)
        door_layout.AddRow(self._label("문 양옆 유리 폭 (mm):"), self.tb_door_side_glass_width)
        door_group.Content = door_layout
        layout.AddRow(door_group)

        # Structure settings
        struct_group = self._groupbox("구조 규격 - 보 기준")
        struct_layout = forms.DynamicLayout()
        struct_layout.Spacing = drawing.Size(5, 5)
        self.tb_beam_H = self._make_textbox("beam_H")
        self.tb_beam_B = self._make_textbox("beam_B")
        self.tb_beam_t = self._make_textbox("beam_t")
        struct_layout.AddRow(self._label("보 H (mm):"), self.tb_beam_H)
        struct_layout.AddRow(self._label("보 B (mm):"), self.tb_beam_B)
        struct_layout.AddRow(self._label("t (0이면 직사각형):"), self.tb_beam_t)
        struct_layout.AddRow(self._label("기둥 규격 = max(H, B) 정사각 / t 공유"))
        struct_group.Content = struct_layout
        layout.AddRow(struct_group)

        # Glass settings
        glass_group = self._groupbox("유리 설정")
        glass_layout = forms.DynamicLayout()
        glass_layout.Spacing = drawing.Size(5, 5)
        self.chk_glass_frame = self._checkbox(" 프레임 O")
        self.chk_glass_frame.Checked = bool(self.params.get("use_glass_frame", True))
        self.chk_glass_frame.CheckedChanged += self.OnBasicOptionChanged
        self.tb_glass_divisions = self._make_textbox("glass_divisions")
        glass_layout.AddRow(self.chk_glass_frame)
        glass_layout.AddRow(self._label("폭 방향 분할 개수:"), self.tb_glass_divisions)
        glass_group.Content = glass_layout
        layout.AddRow(glass_group)

        # Top cap settings
        cap_group = self._groupbox("상부 뚜껑")
        cap_layout = forms.DynamicLayout()
        cap_layout.Spacing = drawing.Size(5, 5)
        self.rbl_cap_type = forms.RadioButtonList()
        self.rbl_cap_type.DataStore = ["솔리드", "유리", "생성하지 않음"]
        if self.params["cap_type"] == CAP_TYPE_GLASS:
            self.rbl_cap_type.SelectedIndex = 1
        elif self.params["cap_type"] == CAP_TYPE_NONE:
            self.rbl_cap_type.SelectedIndex = 2
        else:
            self.rbl_cap_type.SelectedIndex = 0
        try:
            self.rbl_cap_type.Orientation = forms.Orientation.Horizontal
        except:
            pass
        self.rbl_cap_type.SelectedIndexChanged += self.OnBasicOptionChanged
        self.tb_cap_thickness = self._make_textbox("cap_thickness")
        cap_layout.AddRow(self._label("타입:"), self.rbl_cap_type)
        cap_layout.AddRow(self._label("솔리드 두께 - 위 방향 (mm):"), self.tb_cap_thickness)
        cap_group.Content = cap_layout
        layout.AddRow(cap_group)

        # Car slider
        car_group = self._groupbox("Car 위치")
        car_layout = forms.DynamicLayout()
        car_layout.Spacing = drawing.Size(5, 5)
        self.slider_car = forms.Slider()
        self.slider_car.MinValue = 0
        self.slider_car.MaxValue = 1000
        self.slider_car.Value = int(max(0, min(1000, int(self.params.get("car_slider", 0)))))
        self.slider_car.ValueChanged += self.OnCarSliderChanged
        self.lbl_car = self._label("Car 위치: 0%")
        self.tb_car_floor_thickness = self._make_textbox("car_floor_thickness")
        self.tb_car_ceiling_thickness = self._make_textbox("car_ceiling_thickness")
        car_layout.AddRow(self._label("바닥 두께 - 아래 방향 (mm):"), self.tb_car_floor_thickness)
        car_layout.AddRow(self._label("천장 두께 - 위 방향 (mm):"), self.tb_car_ceiling_thickness)
        car_layout.AddRow(self.slider_car)
        car_layout.AddRow(self.lbl_car)
        car_group.Content = car_layout
        layout.AddRow(car_group)

        self.lbl_info = self._label("")
        self.lbl_info.Font = drawing.Font("Malgun Gothic", 9, drawing.FontStyle.Bold)
        layout.AddRow(self.lbl_info)

        btn_layout = forms.DynamicLayout()
        btn_layout.BeginHorizontal()
        btn_layout.Add(None, True)
        self.btn_apply = self._button("적용")
        self.btn_apply.Click += self.OnApply
        self.btn_bake = self._button("수정 적용" if self.edit_target_ids else "생성")
        self.btn_bake.Click += self.OnBake
        self.btn_cancel = self._button("취소")
        self.btn_cancel.Click += self.OnCancel
        btn_layout.Add(self.btn_apply)
        btn_layout.Add(self.btn_bake)
        btn_layout.Add(self.btn_cancel)
        btn_layout.EndHorizontal()

        scroll = forms.Scrollable()
        scroll.Content = layout
        scroll.Height = 540
        try:
            scroll.ExpandContentWidth = True
        except:
            pass
        outer_layout = forms.DynamicLayout()
        outer_layout.Spacing = drawing.Size(6, 6)
        outer_layout.AddRow(scroll)
        outer_layout.AddRow(btn_layout)
        self.Content = outer_layout
        self.KeyDown += self.OnDialogKeyDown

    def format_levels(self, levels):
        return "\n".join([str(round(v, 3)).rstrip('0').rstrip('.') for v in levels])

    def format_door_codes(self, codes):
        floor_count = max(1, len(self.params.get("floor_levels", [])) - 1)
        return "".join(normalize_door_codes(codes, floor_count, self.params.get("door_type", None)))

    def parse_levels(self):
        text = self.ta_levels.Text.replace(",", "\n").replace(";", "\n")
        vals = []
        for line in text.splitlines():
            s = line.strip()
            if not s:
                continue
            vals.append(float(s))
        vals = sorted(vals)
        return merge_levels(vals, LEVEL_MERGE_TOLERANCE)

    def parse_door_codes(self, floor_count):
        text = self.ta_door_codes.Text.upper()
        for ch in ["(", ")", "[", "]", "{", "}", ";", "\n", "\r", "\t"]:
            text = text.replace(ch, ",")
        parts = [p.strip() for p in text.split(",") if p.strip()]
        if len(parts) == 1 and len(parts[0]) > 1:
            parts = [ch for ch in parts[0] if ch.strip()]
        for code in parts:
            if code not in VALID_DOOR_CODES:
                raise Exception("층별 문 타입은 F, B, T, N만 사용할 수 있습니다.")
        return normalize_door_codes(parts, floor_count)

    def set_default_door_codes_for_levels(self, levels):
        count = max(1, len(levels) - 1)
        self.ta_door_codes.Text = self.format_door_codes([DOOR_CODE_FRONT] * count)

    def read_ui_params(self, show_error=True):
        try:
            p = dict(self.params)
            p["floor_levels"] = self.parse_levels()
            p["door_codes"] = self.parse_door_codes(max(1, len(p["floor_levels"]) - 1))
            for key, tb in self.textboxes.items():
                text = tb.Text.strip().replace(",", "")
                if key == "glass_divisions":
                    p[key] = int(float(text))
                else:
                    p[key] = float(text)
            p["door_direction_index"] = int(getattr(self, "door_direction_index", 0)) % 4
            p["use_glass_frame"] = bool(self.chk_glass_frame.Checked)
            cap_index = self.rbl_cap_type.SelectedIndex
            if cap_index == 1:
                p["cap_type"] = CAP_TYPE_GLASS
            elif cap_index == 2:
                p["cap_type"] = CAP_TYPE_NONE
            else:
                p["cap_type"] = CAP_TYPE_SOLID
            p["car_slider"] = int(self.slider_car.Value)
            return p
        except Exception as ex:
            if show_error:
                rs.MessageBox("입력값을 확인해주세요.\n{}".format(str(ex)), 48, "입력 오류")
            return None

    def validate_params(self, p, show_error=True):
        msg = ""
        if not p or len(p["floor_levels"]) < 2:
            msg = "층 바닥 레벨은 최소 2개 이상 필요합니다."
        else:
            levels = p["floor_levels"]
            for i in range(len(levels) - 1):
                if levels[i + 1] <= levels[i]:
                    msg = "층 바닥 레벨은 오름차순이어야 합니다."
                    break
                floor_h = levels[i + 1] - levels[i]
                if p["door_zone_height"] + MIN_SPANDREL_HEIGHT > floor_h:
                    msg = "문 구간 높이가 너무 큽니다. 최소 스팬드럴 {}mm를 확보해야 합니다.".format(MIN_SPANDREL_HEIGHT)
                    break
        if not msg:
            if p["door_zone_height"] <= 100.0:
                msg = "문 구간 높이가 너무 작습니다."
            elif p["beam_H"] <= 1.0 or p["beam_B"] <= 1.0:
                msg = "보 H/B 값은 0보다 커야 합니다."
            elif p["glass_divisions"] < 1:
                msg = "유리 분할 개수는 1 이상이어야 합니다."
            elif p["door_side_glass_width"] < 0:
                msg = "문 양옆 유리 폭은 0 이상이어야 합니다."
            elif p["cap_thickness"] <= 0.0:
                msg = "상부 뚜껑 두께는 0보다 커야 합니다."
            elif p["car_floor_thickness"] <= 0.0 or p["car_ceiling_thickness"] <= 0.0:
                msg = "Car 바닥/천장 두께는 0보다 커야 합니다."

        if msg:
            if show_error:
                rs.MessageBox(msg, 48, "입력 오류")
            return False
        return True

    def get_car_z_from_slider(self, params):
        levels = sorted(params["floor_levels"])
        min_z = levels[0]
        max_z = levels[-2] if len(levels) >= 2 else min_z
        if max_z < min_z:
            max_z = min_z
        ratio = float(self.slider_car.Value) / 1000.0
        return min_z + (max_z - min_z) * ratio

    def UpdatePreview(self):
        p = self.read_ui_params(True)
        if not p or not self.validate_params(p, True):
            return
        self.params = p
        remember_state(self.rect, self.params)
        try:
            self.static_items = build_static_geometry(self.rect, self.params)
            car_z = self.get_car_z_from_slider(self.params)
            self.car_items = create_car_geometry(self.rect, self.params, car_z)
            self.conduit.SetStaticGeometry(self.static_items)
            self.conduit.SetCarGeometry(self.car_items)
            self.update_info_label()
            Rhino.RhinoDoc.ActiveDoc.Views.Redraw()
        except Exception as ex:
            rs.MessageBox("프리뷰 생성 중 오류가 발생했습니다.\n{}".format(str(ex)), 48, "오류")

    def UpdateCarPreviewOnly(self):
        if not self.params:
            return
        try:
            car_z = self.get_car_z_from_slider(self.params)
            self.car_items = create_car_geometry(self.rect, self.params, car_z)
            self.conduit.SetCarGeometry(self.car_items)
            pct = int(round(float(self.slider_car.Value) / 10.0))
            self.lbl_car.Text = "Car 위치: {}% / Z {:.1f}".format(pct, car_z)
            self.params["car_slider"] = int(self.slider_car.Value)
            remember_state(self.rect, self.params)
            Rhino.RhinoDoc.ActiveDoc.Views.Redraw()
        except:
            pass

    def update_info_label(self):
        count_static = len(self.static_items)
        count_car = len(self.car_items)
        col = get_column_size(self.params)
        opening = get_structure_inner_offset(self.params)
        self.lbl_info.Text = "프리뷰 객체: Static {} / Car {} | 기둥 {:.1f}x{:.1f} | 개구부 깊이 {:.1f}mm".format(
            count_static, count_car, col, col, opening)
        self.UpdateCarPreviewOnly()

    def OnTextBoxKeyDown(self, sender, e):
        try:
            if e.Key == forms.Keys.Enter:
                self.UpdatePreview()
                e.Handled = True
        except:
            pass

    def OnLevelsKeyDown(self, sender, e):
        try:
            if e.Control and e.Key == forms.Keys.Enter:
                self.UpdatePreview()
                e.Handled = True
        except:
            pass

    def OnDialogKeyDown(self, sender, e):
        try:
            if e.Key == forms.Keys.Escape:
                self.Close()
        except:
            pass

    def OnBasicOptionChanged(self, sender, e):
        self.UpdatePreview()

    def OnRotateDoorDirection(self, sender, e):
        self.door_direction_index = (int(self.door_direction_index) + 1) % 4
        self.lbl_door_dir.Text = self._door_direction_text()
        self.UpdatePreview()

    def OnApply(self, sender, e):
        self.UpdatePreview()

    def OnMakeDefaultLevels(self, sender, e):
        try:
            count = int(float(self.tb_floor_count.Text.strip()))
            height = float(self.tb_floor_height.Text.strip())
            if count < 1 or height <= 0:
                raise Exception("층 수와 층고를 확인해주세요.")
            levels = []
            for i in range(count + 1):
                levels.append(height * float(i))
            self.ta_levels.Text = self.format_levels(levels)
            self.set_default_door_codes_for_levels(levels)
            self.UpdatePreview()
        except Exception as ex:
            rs.MessageBox(str(ex), 48, "입력 오류")

    def OnPickSlabHeights(self, sender, e):
        try:
            self.Hide()
        except:
            pass
        try:
            go = ric.GetObject()
            go.SetCommandPrompt("층 슬래브 객체들을 선택하세요. BoundingBox 상단 Z를 층 레벨로 사용합니다.")
            go.GeometryFilter = rdo.ObjectType.AnyObject
            go.SubObjectSelect = False
            go.EnablePreSelect(True, True)
            res = go.GetMultiple(1, 0)
            if res != Rhino.Input.GetResult.Object:
                try:
                    self.Show()
                except:
                    pass
                return
            levels = []
            for i in range(go.ObjectCount):
                obj = go.Object(i).Object()
                if not obj:
                    continue
                try:
                    bbox = obj.Geometry.GetBoundingBox(True)
                    if bbox.IsValid:
                        local_z = bbox.Max.Z - self.rect["base_z"]
                        levels.append(local_z)
                except:
                    pass
            if not levels:
                rs.MessageBox("선택 객체에서 높이값을 추출하지 못했습니다.", 48, "오류")
            else:
                levels = sorted(levels)
                levels = merge_levels(levels, LEVEL_MERGE_TOLERANCE)
                has_zero = False
                for v in levels:
                    if abs(v) <= LEVEL_MERGE_TOLERANCE:
                        has_zero = True
                        break
                if not has_zero:
                    levels.insert(0, 0.0)
                levels = merge_levels(sorted(levels), LEVEL_MERGE_TOLERANCE)
                self.ta_levels.Text = self.format_levels(levels)
                self.set_default_door_codes_for_levels(levels)
                self.UpdatePreview()
        except Exception as ex:
            rs.MessageBox("슬래브 높이 추출 중 오류가 발생했습니다.\n{}".format(str(ex)), 48, "오류")
        finally:
            try:
                self.Show()
                self.BringToFront()
            except:
                pass

    def OnCarSliderChanged(self, sender, e):
        self.UpdateCarPreviewOnly()

    def OnBake(self, sender, e):
        p = self.read_ui_params(True)
        if not p or not self.validate_params(p, True):
            return
        self.params = p
        self.static_items = build_static_geometry(self.rect, self.params)
        car_z = self.get_car_z_from_slider(self.params)
        self.car_items = create_car_geometry(self.rect, self.params, car_z)
        all_items = self.static_items + self.car_items
        if not all_items:
            rs.MessageBox("생성할 객체가 없습니다.", 48, "오류")
            return

        doc = Rhino.RhinoDoc.ActiveDoc
        state_json = encode_state(self.rect, self.params)
        undo_name = "Glass Elevator Edit" if self.edit_target_ids else "Glass Elevator Generator"
        undo_id = doc.BeginUndoRecord(undo_name)
        guids = []
        try:
            doc.Views.RedrawEnabled = False
            for gid in self.edit_target_ids:
                try:
                    doc.Objects.Delete(gid, True)
                except:
                    pass
            for item_index, item in enumerate(all_items):
                gid = add_brep_to_layer(doc, item["brep"], item["layer"], state_json, item_index)
                if gid != System.Guid.Empty:
                    guids.append(gid)
            if guids:
                group_index = doc.Groups.Add("GlassElevator")
                for gid in guids:
                    doc.Groups.AddToGroup(group_index, gid)
            remember_state(self.rect, self.params)
        finally:
            doc.EndUndoRecord(undo_id)
            doc.Views.RedrawEnabled = True
            doc.Views.Redraw()
        self.Close()

    def OnCancel(self, sender, e):
        self.Close()

    def OnClosed(self, e):
        if hasattr(self, 'conduit') and self.conduit:
            self.conduit.Enabled = False
        Rhino.RhinoDoc.ActiveDoc.Views.Redraw()
        try:
            if sc.sticky.has_key("GlassElevatorDialog"):
                sc.sticky.Remove("GlassElevatorDialog")
        except:
            pass
        super(GlassElevatorDialog, self).OnClosed(e)

# ==============================================================================
# Level helper
# ==============================================================================
def merge_levels(levels, tol):
    vals = []
    for v in sorted(levels):
        if not vals:
            vals.append(float(v))
        else:
            if abs(float(v) - vals[-1]) <= tol:
                vals[-1] = (vals[-1] + float(v)) * 0.5
            else:
                vals.append(float(v))
    return vals

# ==============================================================================
# Input helpers: DrawRectangle
# ==============================================================================
def make_projected_rectangle_curve_from_3pts(p0, p1, p2, show_error=False):
    p0 = rg.Point3d(p0)
    p1 = rg.Point3d(p1)
    p2 = rg.Point3d(p2)

    base_z = p0.Z
    p0.Z = base_z
    p1.Z = base_z
    p2.Z = base_z

    length_vec = rg.Vector3d(p1 - p0)
    length_vec.Z = 0.0
    if length_vec.Length < 100.0:
        if show_error:
            rs.MessageBox("직사각형 길이가 너무 짧습니다.", 48, "입력 오류")
        return None
    direction = _safe_unitize(length_vec, rg.Vector3d(1, 0, 0))

    raw_width = rg.Vector3d(p2 - p1)
    raw_width.Z = 0.0
    width_vec = raw_width - direction * _dot(raw_width, direction)
    if width_vec.Length < 100.0:
        raw_width = rg.Vector3d(p2 - p0)
        raw_width.Z = 0.0
        width_vec = raw_width - direction * _dot(raw_width, direction)
    if width_vec.Length < 100.0:
        if show_error:
            rs.MessageBox("직사각형 폭이 너무 좁습니다.", 48, "입력 오류")
        return None

    p2_rect = p1 + width_vec
    p3_rect = p0 + width_vec
    pts = [p0, p1, p2_rect, p3_rect, p0]
    return rg.Polyline(pts).ToPolylineCurve()


def get_point_with_line_preview(prompt, base_pt):
    gp = ric.GetPoint()
    gp.SetCommandPrompt(prompt)
    try:
        gp.SetBasePoint(base_pt, True)
        gp.DrawLineFromPoint(base_pt, True)
    except:
        pass

    def on_dynamic_draw(sender, e):
        try:
            pt = rg.Point3d(e.CurrentPoint)
            pt.Z = base_pt.Z
            a = rg.Point3d(base_pt.X, base_pt.Y, base_pt.Z)
            e.Display.DrawLine(a, pt, System.Drawing.Color.Gold, 2)
        except:
            pass

    gp.DynamicDraw += on_dynamic_draw
    res = gp.Get()
    if res != Rhino.Input.GetResult.Point:
        return None
    return gp.Point()


def get_point_with_rectangle_preview(prompt, p0, p1):
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
            else:
                a = rg.Point3d(p0.X, p0.Y, p0.Z)
                b = rg.Point3d(p1.X, p1.Y, p0.Z)
                c = rg.Point3d(current.X, current.Y, p0.Z)
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
    gp0 = ric.GetPoint()
    gp0.SetCommandPrompt("유리 엘리베이터 기준 Rectangle 첫 번째 모서리점을 클릭하세요")
    res0 = gp0.Get()
    if res0 != Rhino.Input.GetResult.Point:
        return None
    p0 = gp0.Point()

    p1 = get_point_with_line_preview("기준 방향이 될 두 번째 모서리점을 클릭하세요", p0)
    if not p1:
        return None

    p2 = get_point_with_rectangle_preview("깊이 방향 점을 클릭하세요", p0, p1)
    if not p2:
        return None

    return make_projected_rectangle_curve_from_3pts(p0, p1, p2, True)

# ==============================================================================
# Main
# ==============================================================================
def get_edit_state_from_objref(doc, objref):
    try:
        obj = objref.Object()
    except:
        obj = None
    state = get_state_from_object(obj)
    if not state:
        return None
    rect_info, params = state
    target_ids = get_generated_group_member_ids(doc, obj)
    rect_info = transform_rect_from_current_objects(doc, rect_info, params, target_ids)
    return rect_info, params, target_ids


def main():
    doc = Rhino.RhinoDoc.ActiveDoc

    base_crv = None
    edit_state = None
    go = ric.GetObject()
    go.SetCommandPrompt("유리 엘리베이터 외곽 Rectangle 또는 기존 GlassElevator 객체를 선택하세요. DrawRectangle 옵션도 사용할 수 있습니다.")
    go.GeometryFilter = rdo.ObjectType.AnyObject
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
                base_crv = draw_rectangle_curve_from_points()
                if not base_crv:
                    return
                break
            continue

        if result == Rhino.Input.GetResult.Object:
            objref = go.Object(0)
            edit_state = get_edit_state_from_objref(doc, objref)
            if edit_state:
                break
            try:
                crv = objref.Curve()
            except:
                crv = None
            if not crv:
                rs.MessageBox("Rectangle 커브 또는 저장된 GlassElevator 객체를 선택해주세요.", 48, "오류")
                return
            base_crv = crv.DuplicateCurve()
            break

        if go.CommandResult() != Rhino.Commands.Result.Success:
            return
        return

    edit_target_ids = []
    params = get_last_params()
    if edit_state:
        rect_info, params, edit_target_ids = edit_state
    else:
        ok, rect_info, msg = get_rectangle_info(base_crv)
        if not ok:
            rs.MessageBox(msg, 48, "Rectangle 인식 실패")
            return

    dialog = GlassElevatorDialog()
    dialog.SetupData(rect_info, params, edit_target_ids)
    sc.sticky["GlassElevatorDialog"] = dialog
    dialog.Show()


if __name__ == "__main__":
    main()
