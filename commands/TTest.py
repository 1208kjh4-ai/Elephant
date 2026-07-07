# -*- coding: utf-8 -*-
from __future__ import division

import math
import System
import clr

clr.AddReference("Eto")
clr.AddReference("Rhino.UI")

import Rhino
import Rhino.Geometry as rg
import Rhino.UI
import Eto.Forms as forms
import Eto.Drawing as drawing
import rhinoscriptsyntax as rs
import scriptcontext as sc
import System.Drawing as SD


# ============================================================
# Hanok Roof Generator
# Rhino 8 / IronPython 2.7
#
# Features:
# - Gable / Hipped / Hip-Gable roof
# - Curved eaves
# - Numerical input UI
# - Apply Preview button
# - Enter key applies preview
# - Modeless Eto Form
# ============================================================


# ============================================================
# Basic Utilities
# ============================================================

def tol():
    return sc.doc.ModelAbsoluteTolerance


def dot(a, b):
    return a.X * b.X + a.Y * b.Y + a.Z * b.Z


def unit(v):
    vv = rg.Vector3d(v.X, v.Y, v.Z)
    if not vv.Unitize():
        raise Exception("Failed to unitize vector.")
    return vv


def avg_pts(pts):
    x = 0.0
    y = 0.0
    z = 0.0

    for p in pts:
        x += p.X
        y += p.Y
        z += p.Z

    n = float(len(pts))
    return rg.Point3d(x / n, y / n, z / n)


def lerp(p0, p1, t):
    return rg.Point3d(
        p0.X + (p1.X - p0.X) * t,
        p0.Y + (p1.Y - p0.Y) * t,
        p0.Z + (p1.Z - p0.Z) * t
    )


def clean_poly_pts(pts):
    result = []
    t = tol()

    for p in pts:
        pp = rg.Point3d(p)

        if not result:
            result.append(pp)
        else:
            if result[-1].DistanceTo(pp) > t:
                result.append(pp)

    if len(result) > 1:
        if result[0].DistanceTo(result[-1]) <= t:
            result.pop()

    return result


def ensure_layer(name, color):
    if not rs.IsLayer(name):
        rs.AddLayer(name, color)


def delete_ids(ids):
    if not ids:
        return

    for obj_id in ids:
        try:
            if obj_id and rs.IsObject(obj_id):
                rs.DeleteObject(obj_id)
        except:
            pass


# ============================================================
# Rectangle Input
# ============================================================

def get_rect_corners(curve_id):
    if not rs.IsCurve(curve_id):
        raise Exception("Selected object is not a curve.")

    if not rs.IsCurveClosed(curve_id):
        raise Exception("Selected curve must be closed.")

    crv = rs.coercecurve(curve_id)

    if crv is None:
        raise Exception("Cannot read selected curve.")

    if not crv.IsPlanar(tol()):
        raise Exception("Selected curve must be planar.")

    pts = rs.PolylineVertices(curve_id)

    if pts is None:
        raise Exception("Selected curve must be a closed rectangular polyline.")

    pts = clean_poly_pts(pts)

    if len(pts) != 4:
        raise Exception("Selected polyline must have exactly 4 corner points.")

    check_rect(pts)

    return pts


def check_rect(pts):
    lengths = []

    for i in range(4):
        a = pts[i]
        b = pts[(i + 1) % 4]
        c = pts[(i + 2) % 4]

        v1 = b - a
        v2 = c - b

        l1 = v1.Length
        l2 = v2.Length

        if l1 <= tol() or l2 <= tol():
            raise Exception("Rectangle has zero-length edge.")

        d = abs(dot(v1, v2)) / (l1 * l2)

        if d > 0.05:
            raise Exception("Selected polyline is not close enough to a rectangle.")

        lengths.append(l1)

    if abs(lengths[0] - lengths[2]) / max(lengths[0], lengths[2]) > 0.05:
        raise Exception("Opposite edges are not similar enough.")

    if abs(lengths[1] - lengths[3]) / max(lengths[1], lengths[3]) > 0.05:
        raise Exception("Opposite edges are not similar enough.")


# ============================================================
# Local Coordinate Frame
# ============================================================

class Frame(object):
    def __init__(self, origin, x, y, z, length, width):
        self.origin = origin
        self.x = x
        self.y = y
        self.z = z
        self.length = length
        self.width = width

    def to_world(self, p):
        return rg.Point3d(
            self.origin.X + self.x.X * p.X + self.y.X * p.Y + self.z.X * p.Z,
            self.origin.Y + self.x.Y * p.X + self.y.Y * p.Y + self.z.Y * p.Z,
            self.origin.Z + self.x.Z * p.X + self.y.Z * p.Y + self.z.Z * p.Z
        )


def make_frame(pts):
    e0 = pts[1] - pts[0]
    e1 = pts[2] - pts[1]

    len0 = e0.Length
    len1 = e1.Length

    normal = unit(rg.Vector3d.CrossProduct(e0, e1))

    if dot(normal, rg.Vector3d(0, 0, 1)) < 0:
        normal = rg.Vector3d(-normal.X, -normal.Y, -normal.Z)

    if len0 >= len1:
        x = unit(e0)
        length = len0
        width = len1
    else:
        x = unit(e1)
        length = len1
        width = len0

    y = unit(rg.Vector3d.CrossProduct(normal, x))
    origin = avg_pts(pts)

    return Frame(origin, x, y, normal, length, width)


# ============================================================
# Parameters
# ============================================================

class Params(object):
    def __init__(self, frame):
        w = frame.width

        self.roof_type = "hip_gable"

        self.height = w * 0.45
        self.eave = w * 0.12

        self.ridge_ratio = 0.55
        self.gable_width_ratio = 0.70
        self.gable_z_ratio = 0.45

        self.corner_lift = w * 0.04
        self.eave_sag = w * 0.02
        self.surface_sag = w * 0.03
        self.thickness = w * 0.04

        self.u_seg = 24
        self.v_seg = 6

        self.guides = True


# ============================================================
# Roof Shape Functions
# ============================================================

def roof_size(frame, par):
    return frame.length + par.eave * 2.0, frame.width + par.eave * 2.0


def base_corners(L, W):
    A = rg.Point3d(-L / 2.0, -W / 2.0, 0.0)
    B = rg.Point3d( L / 2.0, -W / 2.0, 0.0)
    C = rg.Point3d( L / 2.0,  W / 2.0, 0.0)
    D = rg.Point3d(-L / 2.0,  W / 2.0, 0.0)

    return A, B, C, D


def corner_lift_value(x, y, L, W, amount):
    if amount <= 0:
        return 0.0

    hx = L * 0.5
    hy = W * 0.5

    if hx <= 0 or hy <= 0:
        return 0.0

    ux = abs(x) / hx
    uy = abs(y) / hy

    return amount * math.pow(ux * uy, 1.5)


def eave_point(p0, p1, t, L, W, par, use_curve):
    p = lerp(p0, p1, t)

    if use_curve:
        lift = corner_lift_value(p.X, p.Y, L, W, par.corner_lift)
        sag = par.eave_sag * math.sin(math.pi * t)
        p.Z = lift - sag

    return p


def sag_point(p, v, par):
    if par.surface_sag <= 0:
        return p

    sag = par.surface_sag * math.sin(math.pi * v)
    return rg.Point3d(p.X, p.Y, p.Z - sag)


# ============================================================
# Mesh Helpers
# ============================================================

def vi(mesh, frame, p):
    return mesh.Vertices.Add(frame.to_world(p))


def quad(mesh, a, b, c, d):
    mesh.Faces.AddFace(a, b, c, d)


def tri(mesh, a, b, c):
    mesh.Faces.AddFace(a, b, c)


def finish_mesh(mesh):
    try:
        mesh.Faces.CullDegenerateFaces()
    except:
        pass

    try:
        mesh.FaceNormals.ComputeFaceNormals()
    except:
        pass

    try:
        mesh.UnifyNormals()
    except:
        pass

    try:
        mesh.Normals.ComputeNormals()
    except:
        pass

    mesh.Compact()
    return mesh


def ruled_quad(mesh, frame, p00, p10, p01, p11, L, W, par, bottom_eave):
    u_count = max(2, int(par.u_seg))
    v_count = max(1, int(par.v_seg))

    grid = []

    for i in range(u_count + 1):
        u = float(i) / float(u_count)

        bottom = eave_point(p00, p10, u, L, W, par, bottom_eave)
        top = eave_point(p01, p11, u, L, W, par, False)

        col = []

        for j in range(v_count + 1):
            v = float(j) / float(v_count)
            p = lerp(bottom, top, v)
            p = sag_point(p, v, par)
            col.append(vi(mesh, frame, p))

        grid.append(col)

    for i in range(u_count):
        for j in range(v_count):
            quad(
                mesh,
                grid[i][j],
                grid[i + 1][j],
                grid[i + 1][j + 1],
                grid[i][j + 1]
            )


def ruled_tri(mesh, frame, e0, e1, apex, L, W, par, bottom_eave):
    u_count = max(2, int(par.u_seg))
    v_count = max(1, int(par.v_seg))

    rows = []

    for j in range(v_count):
        v = float(j) / float(v_count)
        row = []

        for i in range(u_count + 1):
            u = float(i) / float(u_count)
            ep = eave_point(e0, e1, u, L, W, par, bottom_eave)
            p = lerp(ep, apex, v)
            p = sag_point(p, v, par)
            row.append(vi(mesh, frame, p))

        rows.append(row)

    apex_id = vi(mesh, frame, apex)

    for j in range(v_count - 1):
        for i in range(u_count):
            quad(
                mesh,
                rows[j][i],
                rows[j][i + 1],
                rows[j + 1][i + 1],
                rows[j + 1][i]
            )

    last = rows[-1]

    for i in range(u_count):
        tri(mesh, last[i], last[i + 1], apex_id)


# ============================================================
# Roof Builders
# ============================================================

def build_gable(frame, par):
    mesh = rg.Mesh()

    L, W = roof_size(frame, par)
    A, B, C, D = base_corners(L, W)

    R0 = rg.Point3d(-L / 2.0, 0.0, par.height)
    R1 = rg.Point3d( L / 2.0, 0.0, par.height)

    ruled_quad(mesh, frame, A, B, R0, R1, L, W, par, True)
    ruled_quad(mesh, frame, D, C, R0, R1, L, W, par, True)
    ruled_tri(mesh, frame, A, D, R0, L, W, par, True)
    ruled_tri(mesh, frame, B, C, R1, L, W, par, True)

    guide = {
        "L": L,
        "W": W,
        "ridge": [R0, R1],
        "edges": [[A, R0], [D, R0], [B, R1], [C, R1]],
        "eave": [A, B, C, D, A]
    }

    return finish_mesh(mesh), guide


def build_hipped(frame, par):
    mesh = rg.Mesh()

    L, W = roof_size(frame, par)
    A, B, C, D = base_corners(L, W)

    r = L * par.ridge_ratio

    R0 = rg.Point3d(-r / 2.0, 0.0, par.height)
    R1 = rg.Point3d( r / 2.0, 0.0, par.height)

    ruled_quad(mesh, frame, A, B, R0, R1, L, W, par, True)
    ruled_quad(mesh, frame, D, C, R0, R1, L, W, par, True)
    ruled_tri(mesh, frame, A, D, R0, L, W, par, True)
    ruled_tri(mesh, frame, B, C, R1, L, W, par, True)

    guide = {
        "L": L,
        "W": W,
        "ridge": [R0, R1],
        "edges": [[A, R0], [D, R0], [B, R1], [C, R1]],
        "eave": [A, B, C, D, A]
    }

    return finish_mesh(mesh), guide


def build_hip_gable(frame, par):
    mesh = rg.Mesh()

    L, W = roof_size(frame, par)
    A, B, C, D = base_corners(L, W)

    r = L * par.ridge_ratio
    gw = W * par.gable_width_ratio
    gz = par.height * par.gable_z_ratio

    R0 = rg.Point3d(-r / 2.0, 0.0, par.height)
    R1 = rg.Point3d( r / 2.0, 0.0, par.height)

    G0S = rg.Point3d(-r / 2.0, -gw / 2.0, gz)
    G0N = rg.Point3d(-r / 2.0,  gw / 2.0, gz)

    G1S = rg.Point3d( r / 2.0, -gw / 2.0, gz)
    G1N = rg.Point3d( r / 2.0,  gw / 2.0, gz)

    ruled_quad(mesh, frame, A, B, G0S, G1S, L, W, par, True)
    ruled_quad(mesh, frame, G0S, G1S, R0, R1, L, W, par, False)

    ruled_quad(mesh, frame, D, C, G0N, G1N, L, W, par, True)
    ruled_quad(mesh, frame, G0N, G1N, R0, R1, L, W, par, False)

    ruled_quad(mesh, frame, A, D, G0S, G0N, L, W, par, True)
    ruled_quad(mesh, frame, B, C, G1S, G1N, L, W, par, True)

    ruled_tri(mesh, frame, G0S, G0N, R0, L, W, par, False)
    ruled_tri(mesh, frame, G1S, G1N, R1, L, W, par, False)

    guide = {
        "L": L,
        "W": W,
        "ridge": [R0, R1],
        "edges": [
            [G0S, R0], [G0N, R0],
            [G1S, R1], [G1N, R1],
            [A, G0S], [D, G0N],
            [B, G1S], [C, G1N]
        ],
        "gable_left": [G0S, R0, G0N, G0S],
        "gable_right": [G1S, R1, G1N, G1S],
        "eave": [A, B, C, D, A]
    }

    return finish_mesh(mesh), guide


def build_roof(frame, par):
    if par.roof_type == "gable":
        return build_gable(frame, par)

    if par.roof_type == "hipped":
        return build_hipped(frame, par)

    return build_hip_gable(frame, par)


# ============================================================
# Fascia / Guide Curves
# ============================================================

def sample_edge(p0, p1, L, W, par, count, include_start):
    pts = []
    start = 0

    if not include_start:
        start = 1

    for i in range(start, count + 1):
        t = float(i) / float(count)
        pts.append(eave_point(p0, p1, t, L, W, par, True))

    return pts


def sample_eave_loop(L, W, par):
    A, B, C, D = base_corners(L, W)
    count = max(4, int(par.u_seg))

    pts = []
    pts.extend(sample_edge(A, B, L, W, par, count, True))
    pts.extend(sample_edge(B, C, L, W, par, count, False))
    pts.extend(sample_edge(C, D, L, W, par, count, False))
    pts.extend(sample_edge(D, A, L, W, par, count, False))

    return pts


def build_fascia(frame, par):
    if par.thickness <= 0:
        return None

    L, W = roof_size(frame, par)
    loop = sample_eave_loop(L, W, par)

    if len(loop) < 4:
        return None

    mesh = rg.Mesh()
    n = len(loop)

    for i in range(n):
        p0 = loop[i]
        p1 = loop[(i + 1) % n]

        q0 = rg.Point3d(p0.X, p0.Y, p0.Z - par.thickness)
        q1 = rg.Point3d(p1.X, p1.Y, p1.Z - par.thickness)

        a = vi(mesh, frame, p0)
        b = vi(mesh, frame, p1)
        c = vi(mesh, frame, q1)
        d = vi(mesh, frame, q0)

        quad(mesh, a, b, c, d)

    return finish_mesh(mesh)


def add_mesh(mesh, layer, color, name):
    ensure_layer(layer, color)

    obj_id = sc.doc.Objects.AddMesh(mesh)

    if obj_id == System.Guid.Empty:
        return None

    try:
        rs.ObjectLayer(obj_id, layer)
        rs.ObjectColor(obj_id, color)
        rs.ObjectName(obj_id, name)
    except:
        pass

    return obj_id


def add_curve(frame, pts, layer, color, name):
    ensure_layer(layer, color)

    wpts = []

    for p in pts:
        wpts.append(frame.to_world(p))

    pl = rg.Polyline(wpts)

    if not pl.IsValid:
        return None

    obj_id = sc.doc.Objects.AddCurve(pl.ToNurbsCurve())

    if obj_id == System.Guid.Empty:
        return None

    try:
        rs.ObjectLayer(obj_id, layer)
        rs.ObjectColor(obj_id, color)
        rs.ObjectName(obj_id, name)
    except:
        pass

    return obj_id


def add_guides(frame, par, guide):
    layer = "HanokRoof_Guide"
    color = SD.Color.DarkRed

    add_curve(frame, guide["ridge"], layer, color, "Hanok_Ridge")

    for e in guide["edges"]:
        add_curve(frame, e, layer, color, "Hanok_HipLine")

    if "gable_left" in guide:
        add_curve(frame, guide["gable_left"], layer, color, "Hanok_Gable_Left")

    if "gable_right" in guide:
        add_curve(frame, guide["gable_right"], layer, color, "Hanok_Gable_Right")

    eave = sample_eave_loop(guide["L"], guide["W"], par)

    if eave:
        eave.append(eave[0])
        add_curve(frame, eave, layer, color, "Hanok_Curved_Eave")


# ============================================================
# Preview Manager
# ============================================================

class Preview(object):
    def __init__(self):
        self.ids = []

    def clear(self):
        rs.EnableRedraw(False)

        try:
            delete_ids(self.ids)
            self.ids = []
        finally:
            rs.EnableRedraw(True)
            sc.doc.Views.Redraw()

    def update(self, frame, par):
        rs.EnableRedraw(False)

        try:
            delete_ids(self.ids)
            self.ids = []

            roof, guide = build_roof(frame, par)
            fascia = build_fascia(frame, par)

            rid = add_mesh(
                roof,
                "HanokRoof_PREVIEW",
                SD.Color.FromArgb(160, 110, 70),
                "HanokRoof_PREVIEW_Roof"
            )

            if rid:
                self.ids.append(rid)

            if fascia:
                fid = add_mesh(
                    fascia,
                    "HanokRoof_PREVIEW",
                    SD.Color.FromArgb(120, 80, 50),
                    "HanokRoof_PREVIEW_Fascia"
                )

                if fid:
                    self.ids.append(fid)

        finally:
            rs.EnableRedraw(True)
            sc.doc.Views.Redraw()


# ============================================================
# Numerical Input Row
# ============================================================

class NumberRow(object):
    def __init__(self, title, value, suffix, apply_callback):
        self.title = title
        self.suffix = suffix
        self.apply_callback = apply_callback

        self.label = forms.Label()
        self.label.Text = title

        self.textbox = forms.TextBox()
        self.textbox.Width = 90
        self.textbox.Text = self.format_value(value)

        self.unit_label = forms.Label()
        self.unit_label.Text = suffix
        self.unit_label.Width = 45

        self.textbox.KeyDown += self.on_key_down

    def format_value(self, value):
        try:
            v = float(value)

            if abs(v - int(v)) < 0.000001:
                return str(int(v))

            return str(round(v, 3))

        except:
            return str(value)

    def on_key_down(self, sender, e):
        try:
            key_name = str(e.Key)

            if key_name == "Enter" or key_name == "Return":
                if self.apply_callback:
                    self.apply_callback()

                e.Handled = True

        except:
            pass

    def value(self, default_value):
        text = self.textbox.Text

        try:
            return float(text)
        except:
            self.textbox.Text = self.format_value(default_value)
            return float(default_value)


# ============================================================
# Modeless Eto Form
# ============================================================

class HanokRoofForm(forms.Form):
    def __init__(self):
        forms.Form.__init__(self)

        self.frame = None
        self.par = None
        self.preview = Preview()

        self.ready = False
        self.accepted = False

    def setup(self, frame):
        self.frame = frame
        self.par = Params(frame)

        self.Title = "Hanok Roof Generator"
        self.Padding = drawing.Padding(10)
        self.Resizable = False

        try:
            self.Owner = Rhino.UI.RhinoEtoApp.MainWindow
        except:
            pass

        self.make_controls()
        self.make_layout()
        self.bind_events()

        self.ready = True
        self.apply_preview()

    def make_controls(self):
        self.roof_types = ["gable", "hipped", "hip_gable"]

        self.type_combo = forms.ComboBox()
        self.type_combo.DataStore = self.roof_types
        self.type_combo.SelectedIndex = 2

        self.height = NumberRow("Roof Height", 45, "%W", self.apply_preview)
        self.eave = NumberRow("Eave Offset", 12, "%W", self.apply_preview)

        self.ridge = NumberRow("Ridge Ratio", 55, "%", self.apply_preview)
        self.gable_w = NumberRow("Gable Width", 70, "%", self.apply_preview)
        self.gable_z = NumberRow("Gable Height", 45, "%", self.apply_preview)

        self.corner = NumberRow("Corner Lift", 4, "%W", self.apply_preview)
        self.eave_sag = NumberRow("Eave Sag", 2, "%W", self.apply_preview)
        self.surface_sag = NumberRow("Surface Sag", 3, "%W", self.apply_preview)
        self.thickness = NumberRow("Fascia Thickness", 4, "%W", self.apply_preview)

        self.u_seg = NumberRow("Length Segments", 24, "", self.apply_preview)
        self.v_seg = NumberRow("Slope Segments", 6, "", self.apply_preview)

        self.preview_check = forms.CheckBox()
        self.preview_check.Text = "Live preview"
        self.preview_check.Checked = True

        self.guide_check = forms.CheckBox()
        self.guide_check.Text = "Add guide curves"
        self.guide_check.Checked = True

        self.apply_button = forms.Button()
        self.apply_button.Text = "Apply Preview"

        self.ok = forms.Button()
        self.ok.Text = "OK"

        self.cancel = forms.Button()
        self.cancel.Text = "Cancel"

    def make_layout(self):
        layout = forms.DynamicLayout()
        layout.Padding = drawing.Padding(8)
        layout.Spacing = drawing.Size(5, 5)

        title = forms.Label()
        title.Text = "Hanok Roof Parameters"

        note = forms.Label()
        note.Text = "Type a value, then press Enter or Apply Preview."

        layout.AddRow(title)
        layout.AddRow(note)
        layout.AddRow(None)

        roof_type_label = forms.Label()
        roof_type_label.Text = "Roof Type"
        layout.AddRow(roof_type_label, self.type_combo)

        self.add_number_row(layout, self.height)
        self.add_number_row(layout, self.eave)
        self.add_number_row(layout, self.ridge)

        layout.AddRow(None)

        self.add_number_row(layout, self.gable_w)
        self.add_number_row(layout, self.gable_z)

        layout.AddRow(None)

        self.add_number_row(layout, self.corner)
        self.add_number_row(layout, self.eave_sag)
        self.add_number_row(layout, self.surface_sag)
        self.add_number_row(layout, self.thickness)

        layout.AddRow(None)

        self.add_number_row(layout, self.u_seg)
        self.add_number_row(layout, self.v_seg)

        layout.AddRow(None)

        layout.AddRow(self.preview_check)
        layout.AddRow(self.guide_check)

        layout.AddRow(None)

        apply_row = forms.StackLayout()
        apply_row.Orientation = forms.Orientation.Horizontal
        apply_row.Spacing = 5
        apply_row.Items.Add(self.apply_button)

        layout.AddRow(None, apply_row)

        layout.AddRow(None)

        button_row = forms.StackLayout()
        button_row.Orientation = forms.Orientation.Horizontal
        button_row.Spacing = 5
        button_row.Items.Add(self.ok)
        button_row.Items.Add(self.cancel)

        layout.AddRow(None, button_row)

        self.Content = layout

    def add_number_row(self, layout, row):
        layout.AddRow(row.label, row.textbox, row.unit_label)

    def bind_events(self):
        self.apply_button.Click += self.on_apply
        self.preview_check.CheckedChanged += self.on_preview_toggle

        self.ok.Click += self.on_ok
        self.cancel.Click += self.on_cancel

        self.Closing += self.on_closing
        self.Closed += self.on_closed

    def read_ui(self):
        idx = self.type_combo.SelectedIndex

        if idx < 0:
            idx = 2

        w = self.frame.width

        self.par.roof_type = self.roof_types[idx]

        height_pct = self.height.value(45)
        eave_pct = self.eave.value(12)

        ridge_pct = self.ridge.value(55)
        gable_w_pct = self.gable_w.value(70)
        gable_z_pct = self.gable_z.value(45)

        corner_pct = self.corner.value(4)
        eave_sag_pct = self.eave_sag.value(2)
        surface_sag_pct = self.surface_sag.value(3)
        thickness_pct = self.thickness.value(4)

        u_value = self.u_seg.value(24)
        v_value = self.v_seg.value(6)

        height_pct = max(1.0, min(height_pct, 300.0))
        eave_pct = max(0.0, min(eave_pct, 200.0))

        ridge_pct = max(5.0, min(ridge_pct, 100.0))
        gable_w_pct = max(10.0, min(gable_w_pct, 100.0))
        gable_z_pct = max(5.0, min(gable_z_pct, 95.0))

        corner_pct = max(0.0, min(corner_pct, 100.0))
        eave_sag_pct = max(0.0, min(eave_sag_pct, 100.0))
        surface_sag_pct = max(0.0, min(surface_sag_pct, 100.0))
        thickness_pct = max(0.0, min(thickness_pct, 100.0))

        u_value = int(max(4, min(u_value, 120)))
        v_value = int(max(1, min(v_value, 48)))

        self.par.height = w * height_pct / 100.0
        self.par.eave = w * eave_pct / 100.0

        self.par.ridge_ratio = ridge_pct / 100.0
        self.par.gable_width_ratio = gable_w_pct / 100.0
        self.par.gable_z_ratio = gable_z_pct / 100.0

        self.par.corner_lift = w * corner_pct / 100.0
        self.par.eave_sag = w * eave_sag_pct / 100.0
        self.par.surface_sag = w * surface_sag_pct / 100.0
        self.par.thickness = w * thickness_pct / 100.0

        self.par.u_seg = u_value
        self.par.v_seg = v_value

        self.par.guides = bool(self.guide_check.Checked)

        self.height.textbox.Text = self.height.format_value(height_pct)
        self.eave.textbox.Text = self.eave.format_value(eave_pct)

        self.ridge.textbox.Text = self.ridge.format_value(ridge_pct)
        self.gable_w.textbox.Text = self.gable_w.format_value(gable_w_pct)
        self.gable_z.textbox.Text = self.gable_z.format_value(gable_z_pct)

        self.corner.textbox.Text = self.corner.format_value(corner_pct)
        self.eave_sag.textbox.Text = self.eave_sag.format_value(eave_sag_pct)
        self.surface_sag.textbox.Text = self.surface_sag.format_value(surface_sag_pct)
        self.thickness.textbox.Text = self.thickness.format_value(thickness_pct)

        self.u_seg.textbox.Text = self.u_seg.format_value(u_value)
        self.v_seg.textbox.Text = self.v_seg.format_value(v_value)

    def on_apply(self, sender, e):
        self.apply_preview()

    def on_preview_toggle(self, sender, e):
        if bool(self.preview_check.Checked):
            self.apply_preview()
        else:
            self.preview.clear()

    def apply_preview(self):
        if not self.ready:
            return

        if not bool(self.preview_check.Checked):
            return

        try:
            self.read_ui()
            self.preview.update(self.frame, self.par)

        except Exception as ex:
            forms.MessageBox.Show(
                "Preview failed:\n" + str(ex),
                "Hanok Roof Generator"
            )

    def create_final(self):
        self.read_ui()

        roof, guide = build_roof(self.frame, self.par)
        fascia = build_fascia(self.frame, self.par)

        add_mesh(
            roof,
            "HanokRoof_Mesh",
            SD.Color.FromArgb(145, 92, 55),
            "HanokRoof_Roof"
        )

        if fascia:
            add_mesh(
                fascia,
                "HanokRoof_Fascia",
                SD.Color.FromArgb(110, 70, 42),
                "HanokRoof_EaveFascia"
            )

        if self.par.guides:
            add_guides(self.frame, self.par, guide)

        sc.doc.Views.Redraw()

    def on_ok(self, sender, e):
        try:
            self.accepted = True
            self.preview.clear()
            self.create_final()
            self.Close()

        except Exception as ex:
            forms.MessageBox.Show(
                "Failed to create roof:\n" + str(ex),
                "Hanok Roof Generator"
            )

    def on_cancel(self, sender, e):
        self.accepted = False
        self.preview.clear()
        self.Close()

    def on_closing(self, sender, e):
        if not self.accepted:
            self.preview.clear()

    def on_closed(self, sender, e):
        key = "HanokRoofGenerator_Form"

        try:
            if key in sc.sticky:
                del sc.sticky[key]
        except:
            pass


# ============================================================
# Main
# ============================================================

def main():
    key = "HanokRoofGenerator_Form"

    try:
        if key in sc.sticky:
            old = sc.sticky[key]

            if old:
                old.Close()

            del sc.sticky[key]
    except:
        pass

    curve_id = rs.GetObject(
        "Select closed rectangular polyline for Hanok roof",
        rs.filter.curve,
        True,
        True
    )

    if not curve_id:
        return

    try:
        corners = get_rect_corners(curve_id)
        frame = make_frame(corners)

        form = HanokRoofForm()
        form.setup(frame)

        try:
            form.Owner = Rhino.UI.RhinoEtoApp.MainWindow
        except:
            pass

        form.Show()

        sc.sticky[key] = form

    except Exception as ex:
        print "Hanok roof generator failed:"
        print str(ex)

        forms.MessageBox.Show(
            "Hanok roof generator failed:\n" + str(ex),
            "Hanok Roof Generator"
        )


if __name__ == "__main__":
    main()
