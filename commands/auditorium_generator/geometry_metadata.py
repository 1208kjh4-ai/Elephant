# -*- coding: utf-8 -*-
"""Pure naming and adjacency helpers for generated geometry."""


def section_floor_surface_name(curve_name):
    stalls_names = {
        "Floor": "StallsFloorSurface",
        "CrossAisle": "StallsCrossAisleSurface",
        "CrossAisleStairRiser": (
            "StallsCrossAisleStairRiserSurface"
        ),
        "CrossAisleStairTread": (
            "StallsCrossAisleStairTreadSurface"
        ),
        "CrossAisleStairFlatRun": (
            "StallsCrossAisleStairFlatRunSurface"
        ),
        "RearCrossAisle": "StallsRearAisleSurface",
        "AuditoriumRearFloorClosure": (
            "AuditoriumRearFloorClosureSurface"
        ),
    }
    if curve_name in stalls_names:
        return stalls_names[curve_name]
    if (
        curve_name.startswith("Balcony")
        and (
            curve_name.endswith("Floor")
            or curve_name.endswith("RearAisle")
            or curve_name.endswith("RearFloorClosure")
        )
    ):
        return curve_name + "Surface"
    return None


def stage_space_envelope_name(space):
    if space["height_group"] == "main":
        return "MainFlyTower"
    if space["height_group"] == "clearance":
        return space["name"] + "UpperSpace"
    return space["name"] + "UpperSpace"


def stage_space_top_z(space, section_dimensions):
    height_group = space["height_group"]
    if height_group == "main":
        return section_dimensions["main_tower_top_z"]
    if height_group == "clearance":
        return section_dimensions["clearance_top_z"]
    return section_dimensions[height_group + "_top_z"]


def stage_edge_adjacencies(space, edge_name, spaces):
    tolerance = 1e-8
    if edge_name == "left":
        coordinate = space["min_x"]
        interval = (space["min_y"], space["max_y"])
        opposite_key = "max_x"
        axis = "y"
    elif edge_name == "right":
        coordinate = space["max_x"]
        interval = (space["min_y"], space["max_y"])
        opposite_key = "min_x"
        axis = "y"
    elif edge_name == "front":
        coordinate = space["min_y"]
        interval = (space["min_x"], space["max_x"])
        opposite_key = "max_y"
        axis = "x"
    else:
        coordinate = space["max_y"]
        interval = (space["min_x"], space["max_x"])
        opposite_key = "min_y"
        axis = "x"

    overlaps = []
    for other_space in spaces:
        if other_space is space:
            continue
        if abs(other_space[opposite_key] - coordinate) > tolerance:
            continue
        if axis == "y":
            other_interval = (
                other_space["min_y"],
                other_space["max_y"],
            )
        else:
            other_interval = (
                other_space["min_x"],
                other_space["max_x"],
            )
        overlap_start = max(interval[0], other_interval[0])
        overlap_end = min(interval[1], other_interval[1])
        if overlap_end - overlap_start > tolerance:
            overlaps.append(
                (
                    overlap_start,
                    overlap_end,
                    other_space["top_z"],
                )
            )

    return axis, coordinate, interval, overlaps
