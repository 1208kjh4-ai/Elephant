# -*- coding: utf-8 -*-
"""Rhino display conduit for auditorium preview data."""

import Rhino
import Rhino.Geometry as rg


class AuditoriumPreviewConduit(Rhino.Display.DisplayConduit):
    def __init__(self):
        Rhino.Display.DisplayConduit.__init__(self)
        self.curves = []
        self.points = []
        self.meshes = []
        self.wire_meshes = []
        self.labels = []
        self.bounding_box = rg.BoundingBox.Empty

    def set_geometry(self, preview_data):
        self.curves = preview_data.get("preview_curves", [])
        self.points = preview_data.get("preview_points", [])
        self.meshes = preview_data.get("preview_meshes", [])
        self.wire_meshes = preview_data.get(
            "preview_wire_meshes",
            []
        )
        self.labels = preview_data.get("preview_labels", [])
        self.update_bounding_box()

    def clear(self):
        self.curves = []
        self.points = []
        self.meshes = []
        self.wire_meshes = []
        self.labels = []
        self.bounding_box = rg.BoundingBox.Empty

    def update_bounding_box(self):
        bounding_box = rg.BoundingBox.Empty

        for curve, color, thickness in self.curves:
            if curve is None:
                continue
            curve_box = curve.GetBoundingBox(True)
            if curve_box.IsValid:
                bounding_box.Union(curve_box)

        for point, color, size in self.points:
            if point.IsValid:
                bounding_box.Union(point)

        for mesh_entry in self.meshes:
            mesh = mesh_entry[0]
            if mesh is None:
                continue
            mesh_box = mesh.GetBoundingBox(True)
            if mesh_box.IsValid:
                bounding_box.Union(mesh_box)

        for mesh_entry in self.wire_meshes:
            mesh = mesh_entry[0]
            if mesh is None:
                continue
            mesh_box = mesh.GetBoundingBox(True)
            if mesh_box.IsValid:
                bounding_box.Union(mesh_box)

        for point, text, background_color, text_color in self.labels:
            if point.IsValid:
                bounding_box.Union(point)

        self.bounding_box = bounding_box

    def CalculateBoundingBox(self, event_args):
        if self.bounding_box.IsValid:
            event_args.IncludeBoundingBox(self.bounding_box)

    def CalculateBoundingBoxZoomExtents(self, event_args):
        if self.bounding_box.IsValid:
            event_args.IncludeBoundingBox(self.bounding_box)

    def PostDrawObjects(self, event_args):
        for mesh_entry in self.meshes:
            mesh = mesh_entry[0]
            color = mesh_entry[1]
            transparency = (
                mesh_entry[2]
                if len(mesh_entry) > 2
                else 0.0
            )
            if mesh is None:
                continue
            material = Rhino.Display.DisplayMaterial(
                color,
                transparency
            )
            event_args.Display.DrawMeshShaded(mesh, material)

        for mesh, color in self.wire_meshes:
            if mesh is not None:
                event_args.Display.DrawMeshWires(mesh, color)

    def DrawForeground(self, event_args):
        for curve, color, thickness in self.curves:
            if curve is not None:
                event_args.Display.DrawCurve(curve, color, thickness)

        for point, color, size in self.points:
            event_args.Display.DrawPoint(
                point,
                Rhino.Display.PointStyle.RoundControlPoint,
                size,
                color
            )

        for point, text, background_color, text_color in self.labels:
            event_args.Display.DrawDot(
                point,
                text,
                background_color,
                text_color
            )
