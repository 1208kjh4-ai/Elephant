# -*- coding: utf-8 -*-
"""3D chair and armrest placement geometry for auditorium previews."""

import Rhino.Geometry as rg

from .calculations.seating import calculate_3d_seat_placements
from .preview_palette import PREVIEW_3D_ARMREST, PREVIEW_3D_CHAIR
from .rhino_primitives import get_stage_directions, point_at
from .radial_layout import radial_frame


SEAT_SOURCE_CHAIR_WIDTH = 400.0
SEAT_SOURCE_ARMREST_WIDTH = 80.0
SEAT_CURVE_PREVIEW_THRESHOLD = 1000
# Retain the old public name for compatibility with older callers.
SEAT_WIREFRAME_PREVIEW_THRESHOLD = SEAT_CURVE_PREVIEW_THRESHOLD


def seat_module_transform(
    stage_point,
    audience_direction,
    stage_right_direction,
    placement,
    mm_scale,
    local_x_scale=1.0,
    layout_context=None
):
    """Map seat-local X/Y/Z to auditorium lateral/longitudinal/vertical."""
    if (
        layout_context is not None
        and layout_context.get("mode") == "radial"
    ):
        row_radius = (
            layout_context["radius"]
            + float(placement["row_x"])
        )
        if row_radius <= 1e-8:
            raise ValueError(
                "Radial seat row radius must be greater than zero."
            )
        seat_angle = float(placement["lateral"]) / row_radius
        if (
            not placement.get("boundary_constrained", False)
            and abs(seat_angle)
            > layout_context["half_angle"] + 1e-8
        ):
            raise ValueError(
                "The fixed seat blocks do not fit inside the radial "
                "opening angle. Increase the radius/offset or reduce "
                "the seats per row."
            )
        origin, local_right, local_rear = radial_frame(
            layout_context,
            row_radius,
            seat_angle,
            placement["floor_z"],
            mm_scale
        )
    else:
        origin = point_at(
            stage_point,
            audience_direction,
            placement["row_x"],
            placement["floor_z"],
            mm_scale
        )
        origin += stage_right_direction * (
            placement["lateral"] * mm_scale
        )
        local_right = stage_right_direction
        local_rear = audience_direction

    transform = rg.Transform.Identity
    transform.M00 = local_right.X * mm_scale * local_x_scale
    transform.M10 = local_right.Y * mm_scale * local_x_scale
    transform.M20 = local_right.Z * mm_scale * local_x_scale
    transform.M01 = local_rear.X * mm_scale
    transform.M11 = local_rear.Y * mm_scale
    transform.M21 = local_rear.Z * mm_scale
    transform.M02 = rg.Vector3d.ZAxis.X * mm_scale
    transform.M12 = rg.Vector3d.ZAxis.Y * mm_scale
    transform.M22 = rg.Vector3d.ZAxis.Z * mm_scale
    transform.M03 = origin.X
    transform.M13 = origin.Y
    transform.M23 = origin.Z
    return transform


def build_3d_seat_module_geometry(
    seat_source,
    params,
    section_result,
    stage_point,
    audience_direction,
    mm_scale,
    placement_name="Stalls",
    layout_context=None,
    curve_block_preview=False,
    row_regions=None,
    row_overrides=None
):
    if row_regions is None:
        # Keep the established no-boundary call path byte-for-byte
        # compatible with older injected calculation callbacks.
        if row_overrides is None:
            placement_result = calculate_3d_seat_placements(
                params,
                section_result,
                layout_context,
            )
        else:
            placement_result = calculate_3d_seat_placements(
                params,
                section_result,
                layout_context,
                row_overrides=row_overrides,
            )
    else:
        if row_overrides is None:
            placement_result = calculate_3d_seat_placements(
                params,
                section_result,
                layout_context,
                row_regions,
            )
        else:
            placement_result = calculate_3d_seat_placements(
                params,
                section_result,
                layout_context,
                row_regions,
                row_overrides=row_overrides,
            )
    stage_right_direction, unused_stage_back = get_stage_directions(
        audience_direction
    )
    target_chair_width = (
        params["seat_module_width"] - SEAT_SOURCE_ARMREST_WIDTH
    )
    chair_x_scale = (
        target_chair_width / SEAT_SOURCE_CHAIR_WIDTH
    )

    preview_meshes = []
    preview_wire_meshes = []
    preview_curves = []
    bake_instances = []
    chair_preview = rg.Mesh()
    armrest_preview = rg.Mesh()

    chair_preview_component_key = (
        "chair_curve" if curve_block_preview else "chair"
    )
    armrest_preview_component_key = (
        "armrest_curve" if curve_block_preview else "armrest"
    )
    chair_component = seat_source.get(
        chair_preview_component_key
    )
    armrest_component = seat_source.get(
        armrest_preview_component_key
    )
    if chair_component is None or armrest_component is None:
        raise ValueError(
            "AuditoriumSeat.3dm requires TT_ChairBody_Crv and "
            "TT_Armrest_Crv for previews above {0:,} seats."
            .format(SEAT_CURVE_PREVIEW_THRESHOLD)
        )

    for placement in placement_result["chair_placements"]:
        transform = seat_module_transform(
            stage_point,
            audience_direction,
            stage_right_direction,
            placement,
            mm_scale,
            chair_x_scale,
            layout_context
        )
        if curve_block_preview:
            for source_curve in chair_component["preview_curves"]:
                transformed_curve = source_curve.DuplicateCurve()
                if transformed_curve is None:
                    continue
                transformed_curve.Transform(transform)
                preview_curves.append(
                    (transformed_curve, PREVIEW_3D_CHAIR, 1)
                )
        else:
            source_mesh = chair_component["preview_mesh"]
            if source_mesh is not None:
                transformed_mesh = source_mesh.DuplicateMesh()
                transformed_mesh.Transform(transform)
                chair_preview.Append(transformed_mesh)
        bake_instances.append(
            (
                "chair",
                transform,
                PREVIEW_3D_CHAIR,
                placement_name + "Chair3D",
            )
        )

    for placement in placement_result["armrest_placements"]:
        transform = seat_module_transform(
            stage_point,
            audience_direction,
            stage_right_direction,
            placement,
            mm_scale,
            1.0,
            layout_context
        )
        if curve_block_preview:
            for source_curve in armrest_component["preview_curves"]:
                transformed_curve = source_curve.DuplicateCurve()
                if transformed_curve is None:
                    continue
                transformed_curve.Transform(transform)
                preview_curves.append(
                    (transformed_curve, PREVIEW_3D_ARMREST, 1)
                )
        else:
            source_mesh = armrest_component["preview_mesh"]
            if source_mesh is not None:
                transformed_mesh = source_mesh.DuplicateMesh()
                transformed_mesh.Transform(transform)
                armrest_preview.Append(transformed_mesh)
        bake_instances.append(
            (
                "armrest",
                transform,
                PREVIEW_3D_ARMREST,
                placement_name + "Armrest3D",
            )
        )

    if not curve_block_preview and chair_preview.Faces.Count > 0:
        chair_preview.Normals.ComputeNormals()
        chair_preview.Compact()
        preview_meshes.append((chair_preview, PREVIEW_3D_CHAIR))
    if not curve_block_preview and armrest_preview.Faces.Count > 0:
        armrest_preview.Normals.ComputeNormals()
        armrest_preview.Compact()
        preview_meshes.append(
            (armrest_preview, PREVIEW_3D_ARMREST)
        )

    placement_result["preview_curves"] = preview_curves
    placement_result["preview_meshes"] = preview_meshes
    placement_result["preview_wire_meshes"] = preview_wire_meshes
    placement_result["bake_instances"] = bake_instances
    placement_result["chair_x_scale"] = chair_x_scale
    placement_result["target_chair_width"] = target_chair_width
    placement_result["placement_name"] = placement_name
    placement_result["preview_mode"] = (
        "curve_blocks" if curve_block_preview else "shaded"
    )
    return placement_result
