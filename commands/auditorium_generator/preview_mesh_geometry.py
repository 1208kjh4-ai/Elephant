# -*- coding: utf-8 -*-
"""Rhino mesh helpers shared by auditorium preview geometry."""

import Rhino.Geometry as rg


def append_geometry_to_mesh(target_mesh, geometry):
    if isinstance(geometry, rg.Mesh):
        target_mesh.Append(geometry)
        return

    brep = None
    if isinstance(geometry, rg.Brep):
        brep = geometry
    elif isinstance(geometry, rg.Extrusion):
        brep = geometry.ToBrep()
    elif isinstance(geometry, rg.Surface):
        brep = rg.Brep.CreateFromSurface(geometry)

    if brep is not None:
        meshes = rg.Mesh.CreateFromBrep(
            brep,
            rg.MeshingParameters.FastRenderMesh
        )
        if meshes:
            for mesh in meshes:
                if mesh is not None:
                    target_mesh.Append(mesh)
        return

    if isinstance(geometry, rg.SubD):
        mesh = rg.Mesh.CreateFromSubDControlNet(geometry)
        if mesh is not None:
            target_mesh.Append(mesh)


def build_seat_source_preview_mesh(geometries):
    preview_mesh = rg.Mesh()
    for geometry in geometries:
        append_geometry_to_mesh(preview_mesh, geometry)
    if preview_mesh.Faces.Count == 0:
        return None
    preview_mesh.Normals.ComputeNormals()
    preview_mesh.Compact()
    return preview_mesh
