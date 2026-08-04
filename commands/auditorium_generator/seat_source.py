# -*- coding: utf-8 -*-
"""Load and validate the external auditorium seat source model."""

import os

import Rhino
import Rhino.Geometry as rg

from .preview_mesh_geometry import build_seat_source_preview_mesh
from .seat_preview_geometry import (
    SEAT_SOURCE_ARMREST_WIDTH,
    SEAT_SOURCE_CHAIR_WIDTH,
)


SEAT_SOURCE_FILE_NAME = "AuditoriumSeat.3dm"
SEAT_SOURCE_DEFINITION_NAMES = {
    "solid": {
        "chair": ("ttchairbody",),
        "armrest": ("ttarmrest",),
    },
    "curve": {
        "chair": ("ttchairbodycrv",),
        "armrest": (
            "ttarmrestcrv",
            # Accept the earlier proposed spelling as a compatibility alias.
            "ttarmsetcrv",
        ),
    },
}
SEAT_SOURCE_PLAN_DEFINITION_NAMES = {
    "chair": "TT_ChairBody_Plan",
    "armrest": "TT_Armrest_Plan",
}

# Keep the command-relative path contract of the original function while its
# exact implementation lives one package directory below Auditorium.py.
_MODULE_FILE_PATH = globals().get("_MODULE_FILE_PATH", __file__)
__file__ = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(_MODULE_FILE_PATH))),
    "Auditorium.py",
)


def auditorium_seat_source_path():
    """Return the default external 3D chair-module source path."""
    return os.path.normpath(
        os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            os.pardir,
            SEAT_SOURCE_FILE_NAME
        )
    )


def duplicate_file3dm_geometry(model, geometry, visited_ids=None):
    """Duplicate geometry and recursively flatten nested block references."""
    if geometry is None:
        return []

    if not isinstance(geometry, rg.InstanceReferenceGeometry):
        duplicate = geometry.Duplicate()
        return [duplicate] if duplicate is not None else []

    if visited_ids is None:
        visited_ids = set()
    definition_id = geometry.ParentIdefId
    if definition_id in visited_ids:
        raise ValueError(
            "AuditoriumSeat.3dm contains a circular block reference."
        )

    definition = model.AllInstanceDefinitions.FindId(definition_id)
    if definition is None:
        return []

    nested_visited = set(visited_ids)
    nested_visited.add(definition_id)
    flattened = []
    for object_id in definition.GetObjectIds():
        file_object = model.Objects.FindId(object_id)
        if file_object is None:
            continue
        for duplicate in duplicate_file3dm_geometry(
            model,
            file_object.Geometry,
            nested_visited
        ):
            duplicate.Transform(geometry.Xform)
            flattened.append(duplicate)
    return flattened


def file3dm_definition_geometry(model, definition):
    geometries = []
    visited_ids = set([definition.Id])
    for object_id in definition.GetObjectIds():
        file_object = model.Objects.FindId(object_id)
        if file_object is None:
            continue
        geometries.extend(
            duplicate_file3dm_geometry(
                model,
                file_object.Geometry,
                visited_ids
            )
        )
    return geometries


def geometry_collection_bounding_box(geometries):
    bounding_box = rg.BoundingBox.Empty
    for geometry in geometries:
        if geometry is None:
            continue
        geometry_box = geometry.GetBoundingBox(True)
        if geometry_box.IsValid:
            bounding_box.Union(geometry_box)
    return bounding_box


def source_component_candidate(name, key, geometries, unit_to_mm):
    converted = []
    unit_transform = rg.Transform.Scale(
        rg.Point3d.Origin,
        unit_to_mm
    )
    for geometry in geometries:
        if geometry is None:
            continue
        duplicate = geometry.Duplicate()
        if duplicate is None:
            continue
        duplicate.Transform(unit_transform)
        converted.append(duplicate)

    bounding_box = geometry_collection_bounding_box(converted)
    if not converted or not bounding_box.IsValid:
        return None

    return {
        "name": name or key,
        "key": key,
        "geometries": converted,
        "width": bounding_box.Max.X - bounding_box.Min.X,
        "representation": (
            "curve"
            if all(
                isinstance(geometry, rg.Curve)
                for geometry in converted
            )
            else "solid"
        ),
    }


def exact_plan_definition_kind(name):
    """Return the component kind for an exact plan block definition name."""
    normalized_name = (name or "").strip().lower()
    for kind, expected_name in SEAT_SOURCE_PLAN_DEFINITION_NAMES.items():
        if normalized_name == expected_name.lower():
            return kind
    return None


def source_plan_curve_candidate(name, key, geometries, unit_to_mm):
    """Create a plan candidate from only the curves in an exact plan block."""
    plan_curves = [
        geometry
        for geometry in geometries
        if isinstance(geometry, rg.Curve)
    ]
    return source_component_candidate(
        name,
        key,
        plan_curves,
        unit_to_mm
    )


def compact_component_name(name):
    return "".join(
        character
        for character in (name or "").lower()
        if character.isalnum()
    )


def component_name_kind(name):
    compact_name = compact_component_name(name)
    if any(
        token in compact_name
        for token in ("armrest", "arm", "팔걸이")
    ):
        return "armrest"
    if any(
        token in compact_name
        for token in ("chairbody", "chair", "seat", "의자")
    ):
        return "chair"
    return None


def exact_named_candidate(candidates, representation, kind):
    expected_names = SEAT_SOURCE_DEFINITION_NAMES[
        representation
    ][kind]
    matches = [
        candidate
        for candidate in candidates
        if (
            candidate["representation"] == representation
            and compact_component_name(candidate["name"])
            in expected_names
        )
    ]
    if not matches:
        return None

    # A block definition is the preferred source contract. Object/layer
    # groups remain supported for backward compatibility.
    matches.sort(
        key=lambda candidate: (
            0
            if candidate["key"].startswith("definition:")
            else 1,
            candidate["key"],
        )
    )
    return matches[0]


def validate_seat_source_pair(chair_candidate, armrest_candidate):
    dimension_errors = []
    if abs(
        chair_candidate["width"] - SEAT_SOURCE_CHAIR_WIDTH
    ) > 5.0:
        dimension_errors.append(
            "chair X width {0:.1f} mm (expected 400 mm)".format(
                chair_candidate["width"]
            )
        )
    if abs(
        armrest_candidate["width"] - SEAT_SOURCE_ARMREST_WIDTH
    ) > 5.0:
        dimension_errors.append(
            "armrest X width {0:.1f} mm (expected 80 mm)".format(
                armrest_candidate["width"]
            )
        )
    if dimension_errors:
        raise ValueError(
            "AuditoriumSeat.3dm source dimensions do not match: {0}."
            .format(", ".join(dimension_errors))
        )
    return chair_candidate, armrest_candidate


def choose_seat_source_components(candidates, representation="solid"):
    representation_candidates = [
        candidate
        for candidate in candidates
        if candidate["representation"] == representation
    ]
    if len(representation_candidates) < 2:
        raise ValueError(
            "AuditoriumSeat.3dm requires separate {0} chair-body and "
            "armrest objects or block definitions.".format(
                representation
            )
        )

    exact_chair = exact_named_candidate(
        representation_candidates,
        representation,
        "chair"
    )
    exact_armrest = exact_named_candidate(
        representation_candidates,
        representation,
        "armrest"
    )
    if exact_chair is not None and exact_armrest is not None:
        return validate_seat_source_pair(
            exact_chair,
            exact_armrest
        )

    expected_widths = {
        "chair": SEAT_SOURCE_CHAIR_WIDTH,
        "armrest": SEAT_SOURCE_ARMREST_WIDTH,
    }

    def candidate_score(candidate, kind):
        expected = expected_widths[kind]
        dimensional_score = abs(candidate["width"] - expected) / expected
        named_kind = component_name_kind(candidate["name"])
        if named_kind == kind:
            return dimensional_score - 2.0
        if named_kind is not None:
            return dimensional_score + 5.0
        return dimensional_score

    best_pair = None
    best_score = None
    for chair_candidate in representation_candidates:
        for armrest_candidate in representation_candidates:
            if chair_candidate["key"] == armrest_candidate["key"]:
                continue
            score = (
                candidate_score(chair_candidate, "chair")
                + candidate_score(armrest_candidate, "armrest")
            )
            if best_score is None or score < best_score:
                best_score = score
                best_pair = (chair_candidate, armrest_candidate)

    if best_pair is None:
        raise ValueError(
            "Chair-body and armrest source components could not be separated."
        )

    return validate_seat_source_pair(*best_pair)


def normalize_seat_source_component(
    candidate,
    build_preview_mesh=True
):
    """Preserve the source block's authored local origin and orientation."""
    geometries = [
        geometry.Duplicate()
        for geometry in candidate["geometries"]
        if geometry is not None
    ]
    source_box = geometry_collection_bounding_box(geometries)
    preview_curves = []
    if candidate["representation"] == "curve":
        source_curves = [
            geometry
            for geometry in geometries
            if isinstance(geometry, rg.Curve)
        ]
        try:
            joined_curves = rg.Curve.JoinCurves(
                source_curves,
                0.01
            )
        except Exception:
            joined_curves = None
        preview_curves = (
            list(joined_curves)
            if joined_curves
            else source_curves
        )

    return {
        "source_name": candidate["name"],
        "representation": candidate["representation"],
        "geometries": geometries,
        "width": source_box.Max.X - source_box.Min.X,
        "source_z_offset": source_box.Min.Z,
        "bounding_box": source_box,
        "preview_mesh": (
            build_seat_source_preview_mesh(geometries)
            if build_preview_mesh
            else None
        ),
        "preview_curves": preview_curves,
    }


def load_auditorium_seat_source():
    """Load and validate the external chair-body and armrest modules."""
    source_path = auditorium_seat_source_path()
    if not os.path.isfile(source_path):
        raise ValueError(
            "3D seat source file was not found: {0}".format(source_path)
        )

    model = Rhino.FileIO.File3dm.Read(source_path)
    if model is None:
        raise ValueError(
            "AuditoriumSeat.3dm could not be read by Rhino."
        )

    try:
        source_units = model.Settings.ModelUnitSystem
        unit_to_mm = Rhino.RhinoMath.UnitScale(
            source_units,
            Rhino.UnitSystem.Millimeters
        )
        if unit_to_mm <= 0.0:
            raise ValueError(
                "AuditoriumSeat.3dm has an unsupported model unit."
            )

        candidates = []
        plan_candidates = {}
        plan_error = None
        for definition in model.AllInstanceDefinitions:
            geometries = file3dm_definition_geometry(model, definition)
            definition_key = "definition:{0}".format(definition.Id)
            plan_kind = exact_plan_definition_kind(definition.Name)
            if plan_kind is not None:
                try:
                    plan_candidate = source_plan_curve_candidate(
                        definition.Name,
                        definition_key,
                        geometries,
                        unit_to_mm
                    )
                    if plan_candidate is None:
                        raise ValueError(
                            "AuditoriumSeat.3dm plan block {0} must "
                            "contain curve geometry.".format(
                                SEAT_SOURCE_PLAN_DEFINITION_NAMES[
                                    plan_kind
                                ]
                            )
                        )
                    plan_candidates[plan_kind] = plan_candidate
                except Exception as error:
                    if plan_error is None:
                        plan_error = str(error)
                # Exact Plan definitions are never eligible as the legacy
                # solid/curve seat source, even when the Plan data is bad.
                continue

            candidate = source_component_candidate(
                definition.Name,
                definition_key,
                geometries,
                unit_to_mm
            )
            if candidate is not None:
                candidates.append(candidate)

        layer_names = {}
        for layer in model.AllLayers:
            layer_names[layer.Index] = layer.Name

        named_groups = {}
        layer_groups = {}
        for file_object in model.Objects:
            attributes = file_object.Attributes
            if attributes.IsInstanceDefinitionObject:
                continue
            object_name = (attributes.Name or "").strip()
            if object_name:
                named_groups.setdefault(object_name, []).extend(
                    duplicate_file3dm_geometry(
                        model,
                        file_object.Geometry
                    )
                )
            layer_name = layer_names.get(
                attributes.LayerIndex,
                ""
            )
            if layer_name:
                layer_groups.setdefault(layer_name, []).extend(
                    duplicate_file3dm_geometry(
                        model,
                        file_object.Geometry
                    )
                )

        for prefix, groups in (
            ("object", named_groups),
            ("layer", layer_groups),
        ):
            for name, geometries in groups.items():
                candidate = source_component_candidate(
                    name,
                    "{0}:{1}".format(prefix, name),
                    geometries,
                    unit_to_mm
                )
                if candidate is not None:
                    candidates.append(candidate)

        plan_candidate_keys = set(
            candidate["key"]
            for candidate in plan_candidates.values()
        )
        seat_candidates = [
            candidate
            for candidate in candidates
            if candidate["key"] not in plan_candidate_keys
        ]

        chair_candidate, armrest_candidate = (
            choose_seat_source_components(
                seat_candidates,
                "solid"
            )
        )
        chair_component = normalize_seat_source_component(
            chair_candidate
        )
        armrest_component = normalize_seat_source_component(
            armrest_candidate
        )

        curve_candidates = [
            candidate
            for candidate in seat_candidates
            if candidate["representation"] == "curve"
        ]
        chair_curve_component = None
        armrest_curve_component = None
        if curve_candidates:
            (
                chair_curve_candidate,
                armrest_curve_candidate,
            ) = choose_seat_source_components(
                curve_candidates,
                "curve"
            )
            chair_curve_component = normalize_seat_source_component(
                chair_curve_candidate,
                build_preview_mesh=False
            )
            armrest_curve_component = normalize_seat_source_component(
                armrest_curve_candidate,
                build_preview_mesh=False
            )

        chair_plan_component = None
        armrest_plan_component = None
        if plan_error is None:
            missing_plan_kinds = [
                kind
                for kind in ("chair", "armrest")
                if kind not in plan_candidates
            ]
            if missing_plan_kinds:
                missing_plan_names = [
                    SEAT_SOURCE_PLAN_DEFINITION_NAMES[kind]
                    for kind in missing_plan_kinds
                ]
                plan_error = (
                    "AuditoriumSeat.3dm plan source requires both exact "
                    "block definitions {0} and {1}; missing {2}.".format(
                        SEAT_SOURCE_PLAN_DEFINITION_NAMES["chair"],
                        SEAT_SOURCE_PLAN_DEFINITION_NAMES["armrest"],
                        ", ".join(missing_plan_names)
                    )
                )
            else:
                try:
                    chair_plan_candidate, armrest_plan_candidate = (
                        validate_seat_source_pair(
                            plan_candidates["chair"],
                            plan_candidates["armrest"]
                        )
                    )
                    chair_plan_component = (
                        normalize_seat_source_component(
                            chair_plan_candidate,
                            build_preview_mesh=False
                        )
                    )
                    armrest_plan_component = (
                        normalize_seat_source_component(
                            armrest_plan_candidate,
                            build_preview_mesh=False
                        )
                    )
                except Exception as error:
                    plan_error = str(error)
                    chair_plan_component = None
                    armrest_plan_component = None

        if plan_error is not None:
            plan_status = "unavailable: {0}".format(plan_error)
        elif (
            chair_plan_component is not None
            and armrest_plan_component is not None
        ):
            plan_status = "{0} / {1}".format(
                chair_plan_component["source_name"],
                armrest_plan_component["source_name"]
            )
        else:
            plan_status = "not available"

        file_info = os.stat(source_path)
        signature = "{0}_{1}".format(
            int(file_info.st_mtime),
            file_info.st_size
        )
        return {
            "path": source_path,
            "signature": signature,
            "chair": chair_component,
            "armrest": armrest_component,
            "chair_curve": chair_curve_component,
            "armrest_curve": armrest_curve_component,
            "chair_plan": chair_plan_component,
            "armrest_plan": armrest_plan_component,
            "plan_error": plan_error,
            "status": (
                "{0}: chair {1} ({2:.1f} mm), "
                "armrest {3} ({4:.1f} mm), curves {5}, plans {6}"
            ).format(
                SEAT_SOURCE_FILE_NAME,
                chair_component["source_name"],
                chair_component["width"],
                armrest_component["source_name"],
                armrest_component["width"],
                (
                    "{0} / {1}".format(
                        chair_curve_component["source_name"],
                        armrest_curve_component["source_name"]
                    )
                    if (
                        chair_curve_component is not None
                        and armrest_curve_component is not None
                    )
                    else "not available"
                ),
                plan_status
            ),
        }
    finally:
        model.Dispose()
