# -*- coding: utf-8 -*-
"""Build preview and bake surfaces for auditorium floors and envelopes."""

import math

import Rhino.Geometry as rg

from .boundary_surface_geometry import (
    build_boundary_ceiling_brep,
    build_boundary_vertical_cutter,
    calculate_boundary_plan_extents,
    extrude_wall_curve,
    split_brep_inside_boundary,
)
from .calculations.seating import calculate_seat_layout_width
from .calculations.stage import is_proscenium_stage
from .geometry_metadata import (
    section_floor_surface_name,
    stage_edge_adjacencies,
    stage_space_envelope_name,
    stage_space_top_z,
)
from .preview_mesh_geometry import build_seat_source_preview_mesh
from .preview_palette import (
    FLOOR_SURFACE_PREVIEW_TRANSPARENCY,
    PREVIEW_AUDITORIUM_CEILING,
    PREVIEW_FLOOR,
    PREVIEW_STAGE_APRON,
    PREVIEW_STAGE_SECTION,
    PREVIEW_UNDERSTAGE,
)
from .rhino_primitives import (
    build_plan_rectangle,
    get_stage_directions,
    point_at,
    stage_space_point,
)
from .seat_preview_geometry import SEAT_SOURCE_ARMREST_WIDTH
from .stage_preview_geometry import calculate_proscenium_space_layout
from .radial_layout import (
    build_radial_arc,
    build_radial_side_line,
    radial_available_chord_width,
    radial_point,
    sweep_section_curve_radially,
)


def extrude_section_curve_across_width(
    curve,
    stage_right_direction,
    width_mm,
    mm_scale
):
    if curve is None or width_mm <= 1e-8:
        return None

    half_width = width_mm * 0.5 * mm_scale
    start_curve = curve.DuplicateCurve()
    start_curve.Transform(
        rg.Transform.Translation(
            stage_right_direction * -half_width
        )
    )
    extrusion_vector = stage_right_direction * (
        width_mm * mm_scale
    )
    surface = rg.Surface.CreateExtrusion(
        start_curve,
        extrusion_vector
    )
    return surface.ToBrep() if surface is not None else None


def append_floor_surface(
    brep,
    color,
    name,
    preview_meshes,
    bake_breps
):
    if brep is None:
        return
    preview_mesh = build_seat_source_preview_mesh([brep])
    if preview_mesh is not None:
        preview_meshes.append(
            (
                preview_mesh,
                color,
                FLOOR_SURFACE_PREVIEW_TRANSPARENCY,
            )
        )
    bake_breps.append((brep, color, name))


def build_audience_boundary_wall_breps(
    boundary_context,
    stage_point,
    audience_direction,
    min_world_z,
    max_world_z,
    absolute_tolerance,
):
    """Build perimeter walls while leaving the stage interface open."""
    boundary_curve = boundary_context["curve"]
    boundary_plane = boundary_context["plane"]
    boundary_box = boundary_context["bbox"]
    tolerance = max(
        float(boundary_context["tolerance"]),
        float(absolute_tolerance),
    )

    forward = rg.Vector3d(audience_direction)
    forward.Z = 0.0
    if not forward.Unitize():
        raise ValueError(
            "Audience direction must have a horizontal component."
        )
    lateral = rg.Vector3d.CrossProduct(rg.Vector3d.ZAxis, forward)
    if not lateral.Unitize():
        raise ValueError("Audience lateral direction could not be built.")
    stage_plan_point = boundary_plane.ClosestPoint(stage_point)
    splitter_extent = (
        float(boundary_box.Diagonal.Length)
        + float(stage_plan_point.DistanceTo(boundary_box.Center))
        + tolerance * 10.0
    )
    stage_interface = rg.LineCurve(
        stage_plan_point - lateral * splitter_extent,
        stage_plan_point + lateral * splitter_extent,
    )

    # Keep the closed-curve seam away from the stage interface. Otherwise a
    # front-edge intersection can coincide with both domain ends, leaving
    # only one usable split parameter and accidentally restoring that wall.
    working_curve = boundary_curve.DuplicateCurve()
    if working_curve is None:
        raise ValueError("Auditorium boundary wall curve could not be copied.")
    try:
        extreme_parameters = working_curve.ExtremeParameters(forward)
        rear_parameter = max(
            extreme_parameters,
            key=lambda parameter: rg.Vector3d.Multiply(
                rg.Vector3d(
                    working_curve.PointAt(parameter) - stage_plan_point
                ),
                forward,
            ),
        )
        working_curve.ChangeClosedCurveSeam(rear_parameter)
    except Exception:
        pass

    try:
        events = rg.Intersect.Intersection.CurveCurve(
            working_curve,
            stage_interface,
            tolerance,
            tolerance,
        )
    except Exception as error:
        raise ValueError(
            "Auditorium boundary wall split failed: {0}".format(error)
        )

    split_parameters = []
    if events is not None:
        for event in events:
            if event.IsOverlap:
                split_parameters.extend(
                    (event.OverlapA.T0, event.OverlapA.T1)
                )
            elif event.IsPoint:
                split_parameters.append(event.ParameterA)
    domain = working_curve.Domain
    raw_split_parameters = sorted(
        float(parameter)
        for parameter in split_parameters
        if (
            float(parameter) > float(domain.T0) + 1e-12
            and float(parameter) < float(domain.T1) - 1e-12
        )
    )
    parameter_tolerance = max(
        abs(float(domain.T1) - float(domain.T0)) * 1e-10,
        1e-12,
    )
    split_parameters = []
    for parameter in raw_split_parameters:
        if (
            split_parameters
            and abs(parameter - split_parameters[-1])
            <= parameter_tolerance
        ):
            continue
        split_parameters.append(parameter)

    if split_parameters:
        try:
            candidate_curves = working_curve.Split(split_parameters)
        except Exception:
            candidate_curves = None
    else:
        candidate_curves = None
    if not candidate_curves:
        duplicate = working_curve.DuplicateCurve()
        candidate_curves = [] if duplicate is None else [duplicate]

    walls = []
    for candidate_curve in candidate_curves:
        if candidate_curve is None:
            continue
        candidate_domain = candidate_curve.Domain
        middle_point = candidate_curve.PointAt(
            (
                float(candidate_domain.T0)
                + float(candidate_domain.T1)
            )
            * 0.5
        )
        longitudinal = rg.Vector3d.Multiply(
            rg.Vector3d(middle_point - stage_plan_point),
            forward,
        )
        # Curves on or behind the stage interface remain open so the
        # proscenium/apron transition is never sealed by the audience shell.
        if longitudinal <= tolerance:
            continue
        walls.append(
            extrude_wall_curve(
                candidate_curve,
                min_world_z,
                max_world_z,
                tolerance,
            )
        )
    return walls


def build_radial_chord_to_arc_surface(
    layout_context,
    outer_radius_mm,
    z_mm,
    mm_scale,
    absolute_tolerance
):
    """Build one planar radial surface from the opening chord to an arc."""
    if (
        layout_context is None
        or layout_context.get("mode") != "radial"
    ):
        return None

    inner_radius_mm = float(layout_context["radius"])
    outer_radius_mm = float(outer_radius_mm)
    if outer_radius_mm < inner_radius_mm - 1e-8:
        return None
    outer_radius_mm = max(outer_radius_mm, inner_radius_mm)

    half_angle = float(layout_context["half_angle"])
    inner_start = radial_point(
        layout_context,
        inner_radius_mm,
        -half_angle,
        z_mm,
        mm_scale
    )
    inner_end = radial_point(
        layout_context,
        inner_radius_mm,
        half_angle,
        z_mm,
        mm_scale
    )
    outer_arc = build_radial_arc(
        layout_context,
        outer_radius_mm,
        z_mm,
        mm_scale
    )
    if outer_arc is None:
        return None

    boundary_curves = []
    if outer_radius_mm - inner_radius_mm > 1e-8:
        boundary_curves.append(
            build_radial_side_line(
                layout_context,
                inner_radius_mm,
                outer_radius_mm,
                -half_angle,
                z_mm,
                z_mm,
                mm_scale
            )
        )
    boundary_curves.append(outer_arc)
    if outer_radius_mm - inner_radius_mm > 1e-8:
        boundary_curves.append(
            build_radial_side_line(
                layout_context,
                outer_radius_mm,
                inner_radius_mm,
                half_angle,
                z_mm,
                z_mm,
                mm_scale
            )
        )
    boundary_curves.append(rg.LineCurve(inner_end, inner_start))

    try:
        joined_curves = rg.Curve.JoinCurves(
            boundary_curves,
            absolute_tolerance
        )
    except Exception:
        return None
    if (
        joined_curves is None
        or len(joined_curves) != 1
        or not joined_curves[0].IsClosed
    ):
        return None
    try:
        planar_breps = rg.Brep.CreatePlanarBreps(
            joined_curves[0],
            absolute_tolerance
        )
    except Exception:
        return None
    if (
        planar_breps is None
        or len(planar_breps) != 1
        or not planar_breps[0].IsValid
    ):
        return None
    return planar_breps[0]


def calculate_orchestra_pit_side_transition_domains(
    radial_mode,
    boundary_extents,
    opening_width_mm,
    layout_context=None,
):
    """Return source domains beside, but never across, the pit opening."""
    if radial_mode:
        if layout_context is None:
            return ()
        half_angle = min(
            abs(float(layout_context["half_angle"])),
            math.pi,
        )
        return tuple(
            domain
            for domain in (
                (-math.pi, -half_angle),
                (half_angle, math.pi),
            )
            if domain[1] - domain[0] > 1e-8
        )

    if boundary_extents is None:
        return ()
    half_opening_width = max(float(opening_width_mm), 0.0) * 0.5
    minimum_lateral = float(boundary_extents["min_lateral_mm"])
    maximum_lateral = float(boundary_extents["max_lateral_mm"])
    return tuple(
        domain
        for domain in (
            (
                minimum_lateral,
                min(-half_opening_width, maximum_lateral),
            ),
            (
                max(half_opening_width, minimum_lateral),
                maximum_lateral,
            ),
        )
        if domain[1] - domain[0] > 1e-8
    )


def build_orchestra_pit_side_transition_source_breps(
    stage_point,
    audience_direction,
    params,
    opening_width_mm,
    boundary_extents,
    layout_context,
    mm_scale,
    absolute_tolerance,
):
    """Build floor-level sources beside a custom-boundary orchestra pit."""
    pit_depth = float(params.get("orchestra_pit_depth", 0.0))
    if pit_depth <= 1e-8:
        return []

    apron_x = (
        float(params.get("stage_reference_x", 0.0))
        + float(params["stage_apron_projection"])
    )
    platform_start_x = float(params["first_row_distance"])
    if platform_start_x - apron_x <= 1e-8:
        return []

    first_floor_z = -float(params["stage_height"])
    radial_mode = (
        layout_context is not None
        and layout_context.get("mode") == "radial"
    )
    domains = calculate_orchestra_pit_side_transition_domains(
        radial_mode,
        boundary_extents,
        opening_width_mm,
        layout_context,
    )
    if not domains:
        return []

    if radial_mode:
        section_curve = rg.LineCurve(
            point_at(
                stage_point,
                audience_direction,
                apron_x,
                first_floor_z,
                mm_scale,
            ),
            point_at(
                stage_point,
                audience_direction,
                platform_start_x,
                first_floor_z,
                mm_scale,
            ),
        )
        breps = []
        for domain_start, domain_end in domains:
            brep = sweep_section_curve_radially(
                section_curve,
                layout_context,
                domain_start,
                domain_end,
            )
            if brep is None:
                raise ValueError(
                    "A radial orchestra-pit side floor could not be "
                    "generated."
                )
            breps.append(brep)
        return breps

    stage_right_direction, unused_stage_back = get_stage_directions(
        audience_direction
    )

    def floor_point(longitudinal_x, lateral_y):
        return (
            point_at(
                stage_point,
                audience_direction,
                longitudinal_x,
                first_floor_z,
                mm_scale,
            )
            + stage_right_direction * (lateral_y * mm_scale)
        )

    breps = []
    for lateral_start, lateral_end in domains:
        brep = rg.Brep.CreateFromCornerPoints(
            floor_point(apron_x, lateral_start),
            floor_point(platform_start_x, lateral_start),
            floor_point(platform_start_x, lateral_end),
            floor_point(apron_x, lateral_end),
            absolute_tolerance,
        )
        if brep is None:
            raise ValueError(
                "A rectangular orchestra-pit side floor could not be "
                "generated."
            )
        breps.append(brep)
    return breps


def create_stage_vertical_face(
    stage_point,
    stage_right_direction,
    stage_back_direction,
    axis,
    constant_value,
    interval_start,
    interval_end,
    bottom_z,
    top_z,
    mm_scale,
    absolute_tolerance
):
    if (
        interval_end - interval_start <= 1e-8
        or top_z - bottom_z <= 1e-8
    ):
        return None

    if axis == "x":
        coordinates = (
            (interval_start, constant_value),
            (interval_end, constant_value),
        )
    else:
        coordinates = (
            (constant_value, interval_start),
            (constant_value, interval_end),
        )

    lower_start = stage_space_point(
        stage_point,
        stage_right_direction,
        stage_back_direction,
        coordinates[0][0],
        coordinates[0][1],
        bottom_z,
        mm_scale
    )
    lower_end = stage_space_point(
        stage_point,
        stage_right_direction,
        stage_back_direction,
        coordinates[1][0],
        coordinates[1][1],
        bottom_z,
        mm_scale
    )
    upper_end = stage_space_point(
        stage_point,
        stage_right_direction,
        stage_back_direction,
        coordinates[1][0],
        coordinates[1][1],
        top_z,
        mm_scale
    )
    upper_start = stage_space_point(
        stage_point,
        stage_right_direction,
        stage_back_direction,
        coordinates[0][0],
        coordinates[0][1],
        top_z,
        mm_scale
    )
    return rg.Brep.CreateFromCornerPoints(
        lower_start,
        lower_end,
        upper_end,
        upper_start,
        absolute_tolerance
    )


def append_stage_envelope_surfaces(
    stage_point,
    audience_direction,
    params,
    section_dimensions,
    opening_width_mm,
    opening_height_mm,
    mm_scale,
    absolute_tolerance,
    preview_meshes,
    bake_breps
):
    if not is_proscenium_stage(params):
        return

    stage_right_direction, stage_back_direction = get_stage_directions(
        audience_direction
    )
    spaces = calculate_proscenium_space_layout(params)
    for space in spaces:
        space["top_z"] = stage_space_top_z(
            space,
            section_dimensions
        )

    for space in spaces:
        envelope_name = stage_space_envelope_name(space)
        roof_outline = build_plan_rectangle(
            stage_point,
            stage_right_direction,
            stage_back_direction,
            space["min_x"],
            space["max_x"],
            space["min_y"],
            space["max_y"],
            mm_scale,
            space["top_z"]
        )
        roof_breps = rg.Brep.CreatePlanarBreps(
            roof_outline,
            absolute_tolerance
        )
        if roof_breps:
            for roof_brep in roof_breps:
                append_floor_surface(
                    roof_brep,
                    PREVIEW_STAGE_SECTION,
                    envelope_name + "RoofSurface",
                    preview_meshes,
                    bake_breps
                )

        for edge_name in ("left", "right", "front", "back"):
            if space["name"] == "MainStage" and edge_name == "front":
                continue
            axis, coordinate, interval, overlaps = (
                stage_edge_adjacencies(
                    space,
                    edge_name,
                    spaces
                )
            )
            cut_values = [interval[0], interval[1]]
            for overlap_start, overlap_end, adjacent_top in overlaps:
                cut_values.extend([overlap_start, overlap_end])
            cut_values = sorted(set(cut_values))

            for cut_index in range(len(cut_values) - 1):
                interval_start = cut_values[cut_index]
                interval_end = cut_values[cut_index + 1]
                if interval_end - interval_start <= 1e-8:
                    continue
                midpoint = (interval_start + interval_end) * 0.5
                adjacent_heights = [
                    adjacent_top
                    for overlap_start, overlap_end, adjacent_top in (
                        overlaps
                    )
                    if (
                        midpoint >= overlap_start - 1e-8
                        and midpoint <= overlap_end + 1e-8
                    )
                ]
                bottom_z = (
                    max(adjacent_heights)
                    if adjacent_heights
                    else 0.0
                )
                face = create_stage_vertical_face(
                    stage_point,
                    stage_right_direction,
                    stage_back_direction,
                    axis,
                    coordinate,
                    interval_start,
                    interval_end,
                    bottom_z,
                    space["top_z"],
                    mm_scale,
                    absolute_tolerance
                )
                append_floor_surface(
                    face,
                    PREVIEW_STAGE_SECTION,
                    envelope_name + "WallSurface",
                    preview_meshes,
                    bake_breps
                )

    main_space = spaces[0]
    main_top_z = main_space["top_z"]
    half_opening_width = opening_width_mm * 0.5
    proscenium_segments = (
        (
            main_space["min_x"],
            -half_opening_width,
            0.0,
            main_top_z,
        ),
        (
            half_opening_width,
            main_space["max_x"],
            0.0,
            main_top_z,
        ),
        (
            -half_opening_width,
            half_opening_width,
            opening_height_mm,
            main_top_z,
        ),
    )
    for x_start, x_end, bottom_z, top_z in proscenium_segments:
        face = create_stage_vertical_face(
            stage_point,
            stage_right_direction,
            stage_back_direction,
            "x",
            0.0,
            max(x_start, main_space["min_x"]),
            min(x_end, main_space["max_x"]),
            bottom_z,
            top_z,
            mm_scale,
            absolute_tolerance
        )
        append_floor_surface(
            face,
            PREVIEW_STAGE_SECTION,
            "ProsceniumWallSurface",
            preview_meshes,
            bake_breps
        )


def append_understage_envelope_surfaces(
    stage_point,
    audience_direction,
    params,
    section_dimensions,
    mm_scale,
    absolute_tolerance,
    preview_meshes,
    bake_breps
):
    if not params["understage_enabled"]:
        return

    stage_right_direction, stage_back_direction = get_stage_directions(
        audience_direction
    )
    main_space = calculate_proscenium_space_layout(params)[0]
    bottom_z = section_dimensions["understage_bottom_z"]
    bottom_outline = build_plan_rectangle(
        stage_point,
        stage_right_direction,
        stage_back_direction,
        main_space["min_x"],
        main_space["max_x"],
        main_space["min_y"],
        main_space["max_y"],
        mm_scale,
        bottom_z
    )
    bottom_breps = rg.Brep.CreatePlanarBreps(
        bottom_outline,
        absolute_tolerance
    )
    if bottom_breps:
        for bottom_brep in bottom_breps:
            append_floor_surface(
                bottom_brep,
                PREVIEW_UNDERSTAGE,
                "MainUnderstageBottomSurface",
                preview_meshes,
                bake_breps
            )

    edge_definitions = (
        (
            "y",
            main_space["min_x"],
            main_space["min_y"],
            main_space["max_y"],
        ),
        (
            "y",
            main_space["max_x"],
            main_space["min_y"],
            main_space["max_y"],
        ),
        (
            "x",
            main_space["min_y"],
            main_space["min_x"],
            main_space["max_x"],
        ),
        (
            "x",
            main_space["max_y"],
            main_space["min_x"],
            main_space["max_x"],
        ),
    )
    for axis, constant_value, start_value, end_value in (
        edge_definitions
    ):
        wall = create_stage_vertical_face(
            stage_point,
            stage_right_direction,
            stage_back_direction,
            axis,
            constant_value,
            start_value,
            end_value,
            bottom_z,
            0.0,
            mm_scale,
            absolute_tolerance
        )
        append_floor_surface(
            wall,
            PREVIEW_UNDERSTAGE,
            "MainUnderstageWallSurface",
            preview_meshes,
            bake_breps
        )


def build_floor_surface_geometry(
    stage_point,
    audience_direction,
    params,
    section_dimensions,
    opening_width_mm,
    opening_height_mm,
    rear_wall_x,
    rear_floor_z,
    mm_scale,
    absolute_tolerance,
    section_bake_curves,
    layout_context=None,
    opening_stage_point=None,
    boundary_context=None,
):
    """Build stage, auditorium floor and section-envelope surfaces."""
    preview_meshes = []
    bake_breps = []
    stage_right_direction, stage_back_direction = get_stage_directions(
        audience_direction
    )
    radial_mode = (
        layout_context is not None
        and layout_context.get("mode") == "radial"
    )
    custom_boundary = boundary_context is not None
    stage_surface_point = (
        opening_stage_point
        if opening_stage_point is not None
        else stage_point
    )

    for space in calculate_proscenium_space_layout(params):
        outline = build_plan_rectangle(
            stage_surface_point,
            stage_right_direction,
            stage_back_direction,
            space["min_x"],
            space["max_x"],
            space["min_y"],
            space["max_y"],
            mm_scale
        )
        planar_breps = rg.Brep.CreatePlanarBreps(
            outline,
            absolute_tolerance
        )
        if not planar_breps:
            continue
        for brep in planar_breps:
            append_floor_surface(
                brep,
                space["plan_color"],
                space["name"] + "FloorSurface",
                preview_meshes,
                bake_breps
            )

    append_stage_envelope_surfaces(
        stage_surface_point,
        audience_direction,
        params,
        section_dimensions,
        opening_width_mm,
        opening_height_mm,
        mm_scale,
        absolute_tolerance,
        preview_meshes,
        bake_breps
    )
    append_understage_envelope_surfaces(
        stage_surface_point,
        audience_direction,
        params,
        section_dimensions,
        mm_scale,
        absolute_tolerance,
        preview_meshes,
        bake_breps
    )

    boundary_extents = None
    boundary_cutter = None
    if custom_boundary:
        boundary_extents = calculate_boundary_plan_extents(
            boundary_context,
            stage_point,
            audience_direction,
            mm_scale,
            (
                layout_context["center_point"]
                if radial_mode
                else None
            ),
        )
        ceiling_world_z = (
            stage_point.Z
            + section_dimensions["auditorium_ceiling_z"] * mm_scale
        )
        boundary_datum_z = float(
            boundary_context["plane"].Origin.Z
        )
        cutter_padding = max(
            abs(ceiling_world_z - boundary_datum_z),
            1000.0 * mm_scale,
        )
        boundary_cutter = build_boundary_vertical_cutter(
            boundary_context,
            min(boundary_datum_z, stage_point.Z) - cutter_padding,
            max(ceiling_world_z, stage_point.Z) + cutter_padding,
            absolute_tolerance,
        )

    tier_floor_widths = {}
    if radial_mode and not custom_boundary:
        floor_width = radial_available_chord_width(
            layout_context,
            layout_context["radius"] + rear_wall_x
        )
    elif not custom_boundary:
        seating_width_override = params.get(
            "seat_layout_max_width"
        )
        seating_width = (
            float(seating_width_override)
            if seating_width_override is not None
            else calculate_seat_layout_width(params)
        )
        floor_width = (
            seating_width
            + SEAT_SOURCE_ARMREST_WIDTH
            + params["side_floor_margin"] * 2.0
        )
        tier_seating_widths = params.get(
            "seat_layout_max_width_by_tier"
        )
        if hasattr(tier_seating_widths, "get"):
            for tier_key in ("stalls", "balcony_1", "balcony_2"):
                tier_seating_width = tier_seating_widths.get(tier_key)
                if tier_seating_width is None:
                    tier_floor_widths[tier_key] = floor_width
                    continue
                tier_floor_widths[tier_key] = (
                    float(tier_seating_width)
                    + SEAT_SOURCE_ARMREST_WIDTH
                    + params["side_floor_margin"] * 2.0
                )
            if tier_floor_widths:
                floor_width = max(
                    [floor_width] + list(tier_floor_widths.values())
                )
    else:
        lateral_min = boundary_extents["min_lateral_mm"]
        lateral_max = boundary_extents["max_lateral_mm"]
        floor_width = boundary_extents["lateral_span_mm"]
        source_half_width = max(abs(lateral_min), abs(lateral_max))
        source_half_width += absolute_tolerance / mm_scale * 10.0
        source_floor_width = source_half_width * 2.0

    def tier_floor_width(curve_name):
        if curve_name.startswith("Balcony01"):
            return tier_floor_widths.get("balcony_1", floor_width)
        if curve_name.startswith("Balcony02"):
            return tier_floor_widths.get("balcony_2", floor_width)
        return tier_floor_widths.get("stalls", floor_width)

    def build_auditorium_source_surface(
        section_curve,
        source_width=None
    ):
        if radial_mode:
            if custom_boundary:
                return sweep_section_curve_radially(
                    section_curve,
                    layout_context,
                    -math.pi,
                    math.pi,
                )
            return sweep_section_curve_radially(
                section_curve,
                layout_context,
            )
        return extrude_section_curve_across_width(
            section_curve,
            stage_right_direction,
            (
                source_floor_width
                if custom_boundary
                else (
                    floor_width if source_width is None else source_width
                )
            ),
            mm_scale,
        )

    def append_auditorium_surface(brep, color, name):
        if not custom_boundary:
            append_floor_surface(
                brep,
                color,
                name,
                preview_meshes,
                bake_breps,
            )
            return
        if brep is None:
            raise ValueError(
                "Custom-boundary source surface could not be generated: "
                "{0}.".format(name)
            )
        try:
            clipped_breps = split_brep_inside_boundary(
                brep,
                boundary_cutter,
                boundary_context,
                absolute_tolerance,
            )
        finally:
            try:
                brep.Dispose()
            except Exception:
                pass
        for clipped_brep in clipped_breps:
            append_floor_surface(
                clipped_brep,
                color,
                name,
                preview_meshes,
                bake_breps,
            )

    for curve, color, curve_name in section_bake_curves:
        surface_name = section_floor_surface_name(curve_name)
        if surface_name is None:
            continue
        brep = build_auditorium_source_surface(
            curve,
            tier_floor_width(curve_name),
        )
        append_auditorium_surface(
            brep,
            color,
            surface_name,
        )

    railing_surface_names = {
        "Balcony01RailingFront": (
            "Balcony01RailingFrontSurface"
        ),
        "Balcony01RailingTop": "Balcony01RailingTopSurface",
        "Balcony02RailingFront": (
            "Balcony02RailingFrontSurface"
        ),
        "Balcony02RailingTop": "Balcony02RailingTopSurface",
    }
    for curve, color, curve_name in section_bake_curves:
        surface_name = railing_surface_names.get(curve_name)
        if surface_name is None:
            continue
        brep = build_auditorium_source_surface(
            curve,
            tier_floor_width(curve_name),
        )
        append_auditorium_surface(
            brep,
            color,
            surface_name,
        )

    transition_surface_names = {
        "StageApronSection": "StageApronSurface",
        "OrchestraPitFront": "OrchestraPitFrontWallSurface",
        "OrchestraPitBottom": "OrchestraPitBottomSurface",
        "OrchestraPitRear": "OrchestraPitRearWallSurface",
        "StageFrontSection": "StageFrontWallSurface",
        "StageAudienceFloorSection": (
            "StageAudienceTransitionFloorSurface"
        ),
    }
    stage_apron_brep = None
    if radial_mode:
        try:
            stage_apron_brep = build_radial_chord_to_arc_surface(
                layout_context,
                (
                    layout_context["radius"]
                    + max(
                        float(params["stage_apron_projection"]),
                        0.0
                    )
                ),
                0.0,
                mm_scale,
                absolute_tolerance
            )
        except Exception:
            stage_apron_brep = None
    for curve, color, curve_name in section_bake_curves:
        surface_name = transition_surface_names.get(curve_name)
        if surface_name is None:
            continue
        if (
            radial_mode
            and curve_name == "StageApronSection"
            and stage_apron_brep is not None
        ):
            continue
        if (
            custom_boundary
            and curve_name == "StageAudienceFloorSection"
        ):
            append_auditorium_surface(
                build_auditorium_source_surface(curve),
                color,
                surface_name,
            )
            continue
        brep = (
            sweep_section_curve_radially(curve, layout_context)
            if radial_mode
            else extrude_section_curve_across_width(
                curve,
                stage_right_direction,
                opening_width_mm,
                mm_scale
            )
        )
        append_floor_surface(
            brep,
            color,
            surface_name,
            preview_meshes,
            bake_breps
        )

    if (
        custom_boundary
        and float(params.get("orchestra_pit_depth", 0.0)) > 1e-8
    ):
        pit_side_transition_breps = (
            build_orchestra_pit_side_transition_source_breps(
                stage_point,
                audience_direction,
                params,
                opening_width_mm,
                boundary_extents,
                layout_context,
                mm_scale,
                absolute_tolerance,
            )
        )
        for side_index, pit_side_transition_brep in enumerate(
            pit_side_transition_breps
        ):
            append_auditorium_surface(
                pit_side_transition_brep,
                PREVIEW_FLOOR,
                (
                    "OrchestraPitSideTransition"
                    "{0:02d}Surface".format(side_index + 1)
                ),
            )

    if custom_boundary:
        if radial_mode:
            source_rear_extent = (
                boundary_extents["max_radius_mm"]
                - float(layout_context["radius"])
            )
        else:
            source_rear_extent = boundary_extents[
                "max_longitudinal_mm"
            ]
        if source_rear_extent - rear_wall_x > 1e-8:
            rear_floor_levels = [float(rear_floor_z)]
            for curve, unused_color, curve_name in section_bake_curves:
                if not (
                    curve_name == "RearCrossAisle"
                    or curve_name.endswith("RearAisle")
                    or curve_name.endswith("RearFloorClosure")
                ):
                    continue
                try:
                    curve_z = (
                        float(curve.PointAtEnd.Z) - float(stage_point.Z)
                    ) / mm_scale
                except Exception:
                    continue
                if not any(
                    abs(curve_z - existing_z) <= 1e-8
                    for existing_z in rear_floor_levels
                ):
                    rear_floor_levels.append(curve_z)

            for extension_index, floor_z in enumerate(
                rear_floor_levels
            ):
                extension_curve = rg.LineCurve(
                    point_at(
                        stage_point,
                        audience_direction,
                        rear_wall_x,
                        floor_z,
                        mm_scale,
                    ),
                    point_at(
                        stage_point,
                        audience_direction,
                        source_rear_extent,
                        floor_z,
                        mm_scale,
                    ),
                )
                append_auditorium_surface(
                    build_auditorium_source_surface(extension_curve),
                    PREVIEW_FLOOR,
                    (
                        "AuditoriumBoundaryRearFloorExtension"
                        "{0:02d}Surface".format(extension_index + 1)
                    ),
                )

    if radial_mode and custom_boundary:
        append_floor_surface(
            stage_apron_brep,
            PREVIEW_STAGE_APRON,
            "StageApronSurface",
            preview_meshes,
            bake_breps,
        )

    if custom_boundary:
        ceiling_brep = build_boundary_ceiling_brep(
            boundary_context,
            ceiling_world_z,
            absolute_tolerance,
        )
        append_floor_surface(
            ceiling_brep,
            PREVIEW_AUDITORIUM_CEILING,
            "AuditoriumCeilingSurface",
            preview_meshes,
            bake_breps,
        )
        boundary_walls = build_audience_boundary_wall_breps(
            boundary_context,
            stage_surface_point,
            audience_direction,
            boundary_datum_z,
            ceiling_world_z,
            absolute_tolerance,
        )
        for wall_index, boundary_wall in enumerate(boundary_walls):
            append_floor_surface(
                boundary_wall,
                PREVIEW_AUDITORIUM_CEILING,
                "AuditoriumBoundaryWall{0:02d}Surface".format(
                    wall_index + 1
                ),
                preview_meshes,
                bake_breps,
            )
        try:
            boundary_cutter.Dispose()
        except Exception:
            pass
        return {
            "preview_meshes": preview_meshes,
            "bake_breps": bake_breps,
            "auditorium_floor_width": floor_width,
            "auditorium_boundary_applied": True,
            "auditorium_boundary_extents": boundary_extents,
        }

    if radial_mode:
        append_floor_surface(
            stage_apron_brep,
            PREVIEW_STAGE_APRON,
            "StageApronSurface",
            preview_meshes,
            bake_breps
        )

        envelope_surface_names = {
            "AuditoriumCeilingSection": (
                "AuditoriumCeilingSurface"
            ),
            "AuditoriumRearWallSection": (
                "AuditoriumRearWallSurface"
            ),
        }
        try:
            ceiling_brep = build_radial_chord_to_arc_surface(
                layout_context,
                layout_context["radius"] + rear_wall_x,
                section_dimensions["auditorium_ceiling_z"],
                mm_scale,
                absolute_tolerance
            )
        except Exception:
            ceiling_brep = None
        for curve, color, curve_name in section_bake_curves:
            surface_name = envelope_surface_names.get(curve_name)
            if surface_name is None:
                continue
            if (
                curve_name == "AuditoriumCeilingSection"
                and ceiling_brep is not None
            ):
                continue
            append_floor_surface(
                sweep_section_curve_radially(
                    curve,
                    layout_context
                ),
                color,
                surface_name,
                preview_meshes,
                bake_breps
            )
        append_floor_surface(
            ceiling_brep,
            PREVIEW_AUDITORIUM_CEILING,
            "AuditoriumCeilingSurface",
            preview_meshes,
            bake_breps
        )
        return {
            "preview_meshes": preview_meshes,
            "bake_breps": bake_breps,
            "auditorium_floor_width": (
                radial_available_chord_width(
                    layout_context,
                    layout_context["radius"] + rear_wall_x
                )
            ),
            "auditorium_boundary_applied": False,
        }

    half_floor_width = floor_width * 0.5

    def auditorium_point(longitudinal_x, lateral_y, z_value):
        center_point = point_at(
            stage_point,
            audience_direction,
            longitudinal_x,
            z_value,
            mm_scale
        )
        return (
            center_point
            + stage_right_direction * (lateral_y * mm_scale)
        )

    auditorium_ceiling_z = section_dimensions[
        "auditorium_ceiling_z"
    ]
    ceiling_brep = rg.Brep.CreateFromCornerPoints(
        auditorium_point(
            0.0,
            -half_floor_width,
            auditorium_ceiling_z
        ),
        auditorium_point(
            rear_wall_x,
            -half_floor_width,
            auditorium_ceiling_z
        ),
        auditorium_point(
            rear_wall_x,
            half_floor_width,
            auditorium_ceiling_z
        ),
        auditorium_point(
            0.0,
            half_floor_width,
            auditorium_ceiling_z
        ),
        absolute_tolerance
    )
    append_floor_surface(
        ceiling_brep,
        PREVIEW_AUDITORIUM_CEILING,
        "AuditoriumCeilingSurface",
        preview_meshes,
        bake_breps
    )

    rear_wall_brep = rg.Brep.CreateFromCornerPoints(
        auditorium_point(
            rear_wall_x,
            -half_floor_width,
            rear_floor_z
        ),
        auditorium_point(
            rear_wall_x,
            half_floor_width,
            rear_floor_z
        ),
        auditorium_point(
            rear_wall_x,
            half_floor_width,
            auditorium_ceiling_z
        ),
        auditorium_point(
            rear_wall_x,
            -half_floor_width,
            auditorium_ceiling_z
        ),
        absolute_tolerance
    )
    append_floor_surface(
        rear_wall_brep,
        PREVIEW_AUDITORIUM_CEILING,
        "AuditoriumRearWallSurface",
        preview_meshes,
        bake_breps
    )

    return {
        "preview_meshes": preview_meshes,
        "bake_breps": bake_breps,
        "auditorium_floor_width": floor_width,
        "auditorium_boundary_applied": False,
    }
