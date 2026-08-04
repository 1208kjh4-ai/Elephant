# -*- coding: utf-8 -*-

import Rhino.DocObjects as rd
import Rhino.Geometry as rg

from .preview_palette import PREVIEW_3D_ARMREST, PREVIEW_3D_CHAIR


SEAT_COMPONENT_METADATA = {
    "chair": ("ChairBody3D", PREVIEW_3D_CHAIR),
    "armrest": ("Armrest3D", PREVIEW_3D_ARMREST),
    "chair_curve": ("ChairBodyCurve", PREVIEW_3D_CHAIR),
    "armrest_curve": ("ArmrestCurve", PREVIEW_3D_ARMREST),
}


def create_attributes(doc, color, name):
    attributes = rd.ObjectAttributes()
    attributes.LayerIndex = doc.Layers.CurrentLayerIndex
    attributes.ColorSource = rd.ObjectColorSource.ColorFromObject
    attributes.ObjectColor = color
    attributes.Name = name
    return attributes


def _group_added_objects(doc, added_ids):
    """Best-effort grouping shared by the auditorium bake operations."""
    try:
        valid_ids = [object_id for object_id in added_ids if object_id]
        if valid_ids:
            doc.Groups.Add(valid_ids)
    except Exception:
        pass


def bake_plan_preview(plan_preview_data, doc):
    """Bake the visible Plan Preview curves to the current Rhino layer."""
    if plan_preview_data is None:
        raise ValueError("A valid Plan Preview is required for Bake.")

    added_ids = []
    for curve, color, unused_thickness in plan_preview_data.get(
        "preview_curves",
        [],
    ):
        if curve is None:
            continue
        attributes = create_attributes(
            doc,
            color,
            "AuditoriumPlanPreview",
        )
        object_id = doc.Objects.AddCurve(curve, attributes)
        if object_id:
            added_ids.append(object_id)

    _group_added_objects(doc, added_ids)
    doc.Views.Redraw()
    return added_ids


def ensure_seat_instance_definition(doc, seat_source, component_key):
    if component_key not in SEAT_COMPONENT_METADATA:
        raise ValueError(
            "Unsupported seat source component: {0}".format(
                component_key
            )
        )
    component = seat_source[component_key]
    if component is None:
        raise ValueError(
            "{0} is missing from AuditoriumSeat.3dm.".format(
                component_key
            )
        )
    component_label, color = SEAT_COMPONENT_METADATA[
        component_key
    ]
    definition_name = (
        "Elephant_AuditoriumSeat_{0}_{1}".format(
            component_label,
            seat_source["signature"]
        )
    )
    existing = doc.InstanceDefinitions.Find(definition_name, True)
    if existing is not None:
        return existing.Index

    geometries = []
    attributes = []
    for geometry in component["geometries"]:
        duplicate = geometry.Duplicate()
        if duplicate is None:
            continue
        geometries.append(duplicate)
        attributes.append(
            create_attributes(
                doc,
                color,
                component_label
            )
        )

    if not geometries:
        raise ValueError(
            "{0} source has no geometry to bake.".format(
                component_label
            )
        )

    definition_index = doc.InstanceDefinitions.Add(
        definition_name,
        "Loaded from {0}".format(seat_source["path"]),
        rg.Point3d.Origin,
        geometries,
        attributes
    )
    if definition_index < 0:
        raise ValueError(
            "Could not create the {0} block definition.".format(
                component_label
            )
        )
    return definition_index


def bake_preview(preview_data, doc):
    added_ids = []

    for curve, color, name in preview_data["bake_curves"]:
        if curve is None:
            continue
        attributes = create_attributes(doc, color, name)
        object_id = doc.Objects.AddCurve(curve, attributes)
        if object_id:
            added_ids.append(object_id)

    for brep, color, name in preview_data.get("bake_breps", []):
        if brep is None:
            continue
        attributes = create_attributes(doc, color, name)
        object_id = doc.Objects.AddBrep(brep, attributes)
        if object_id:
            added_ids.append(object_id)

    for point, color, name in preview_data["bake_points"]:
        attributes = create_attributes(doc, color, name)
        object_id = doc.Objects.AddPoint(point, attributes)
        added_ids.append(object_id)

    bake_instances = preview_data.get("bake_instances", [])
    if bake_instances:
        seat_source = preview_data.get("seat_source")
        if seat_source is None:
            raise ValueError(
                "3D seat source data is missing during Bake."
            )
        component_keys = []
        for component_key, unused_transform, unused_color, unused_name in (
            bake_instances
        ):
            if component_key not in component_keys:
                component_keys.append(component_key)
        definition_indices = {}
        for component_key in component_keys:
            definition_indices[component_key] = (
                ensure_seat_instance_definition(
                    doc,
                    seat_source,
                    component_key
                )
            )
        for component_key, transform, color, name in bake_instances:
            attributes = create_attributes(doc, color, name)
            object_id = doc.Objects.AddInstanceObject(
                definition_indices[component_key],
                transform,
                attributes
            )
            if object_id:
                added_ids.append(object_id)

    # Try to group all generated objects. Failure does not affect creation.
    _group_added_objects(doc, added_ids)

    doc.Views.Redraw()
    return added_ids
