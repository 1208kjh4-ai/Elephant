# -*- coding: utf-8 -*-
"""
Elephant Tools - Auditorium Section Generator (Initial Version)
Target: Rhino 8 Python / RhinoCommon / Eto.Forms

Workflow
--------
1. Select a closed rectangular curve standing vertically.
2. The midpoint of the lowest edge becomes the stage reference point.
3. Enter auditorium parameters in the Eto dialog.
4. Preview stepped or sloped seating sections.
5. Press Flip to reverse the auditorium direction.
6. Press OK to bake the preview geometry.

Important stepped-floor rule
----------------------------
Each calculated riser height keeps its integer millimeter value and any
fractional part is rounded upward:
    173.0 mm -> 173 mm
    173.1 mm -> 174 mm
    173.9 mm -> 174 mm
"""

import math
import os
import scriptcontext as sc
import Rhino
import Rhino.Geometry as rg
import Rhino.DocObjects as rd
import Rhino.Input as ri
import Rhino.Input.Custom as ric
import Rhino.Commands as rc
import Rhino.UI
import Eto.Forms as forms
import Eto.Drawing as drawing
from System.Drawing import Color


STICKY_KEY = "Elephant_AuditoriumSectionGenerator_v1"
PROSCENIUM_SETTINGS_VERSION = 3
AUDITORIUM_DEFAULTS_VERSION = 6
BALCONY_SETTINGS_VERSION = 2
SIDE_STAGE_CLEARANCE = 2000.0
STAGE_EQUIPMENT_CLEARANCE = 2000.0
DEFAULT_FIRST_PLATFORM_START_DISTANCE = 7000.0
AISLE_STAIR_TARGET_RISER_HEIGHT = 170.0
CHAIR_SIGHT_POINT_X = -180.0
CHAIR_SIGHT_POINT_Z = 1123.991949
CHAIR_FRONT_X = -853.804758
CHAIR_TOP_Z = 1237.912957
SEAT_SOURCE_CHAIR_WIDTH = 400.0
SEAT_SOURCE_ARMREST_WIDTH = 80.0
SEAT_SOURCE_FILE_NAME = "AuditoriumSeat.3dm"
MAXIMUM_3D_CHAIR_COUNT = 10000
SECTION_RISE_KEYS = ("stalls", "balcony_1", "balcony_2")
SECTION_INTERPOLATION_WARNING_RATIO = 0.20

PREVIEW_FLOOR = Color.FromArgb(35, 170, 220)
PREVIEW_SEAT = Color.FromArgb(105, 200, 255)
PREVIEW_SIGHT = Color.FromArgb(115, 155, 255)
PREVIEW_POINT = Color.FromArgb(255, 210, 70)
PREVIEW_WARNING = Color.FromArgb(235, 55, 55)
PREVIEW_REFERENCE = Color.FromArgb(255, 90, 20)
PREVIEW_FULL_STAGE_SIGHT = Color.FromArgb(255, 145, 35)
PREVIEW_MAIN_STAGE = Color.FromArgb(230, 125, 35)
PREVIEW_AUX_STAGE = Color.FromArgb(175, 95, 210)
PREVIEW_STAGE_CLEARANCE = Color.FromArgb(245, 195, 70)
PREVIEW_STAGE_SECTION = Color.FromArgb(80, 210, 125)
PREVIEW_GRID = Color.FromArgb(245, 80, 185)
PREVIEW_UNDERSTAGE = Color.FromArgb(70, 205, 220)
PREVIEW_AUDITORIUM_CEILING = Color.FromArgb(150, 225, 245)
PREVIEW_STAGE_APRON = Color.FromArgb(240, 145, 55)
PREVIEW_ORCHESTRA_PIT = Color.FromArgb(75, 180, 235)
PREVIEW_AISLE = Color.FromArgb(245, 185, 65)
PREVIEW_BALCONY = Color.FromArgb(155, 115, 235)
PREVIEW_BALCONY_SECOND = Color.FromArgb(90, 185, 235)
PREVIEW_BALCONY_RAIL = Color.FromArgb(255, 175, 45)
PREVIEW_SECTION_DIMENSION = Color.FromArgb(70, 205, 80)
PREVIEW_3D_CHAIR = Color.FromArgb(105, 200, 255)
PREVIEW_3D_ARMREST = Color.FromArgb(75, 105, 135)
FLOOR_SURFACE_PREVIEW_TRANSPARENCY = 0.55

PROSCENIUM_PARAM_KEYS = (
    "stage_preview_mode",
    "main_stage_width",
    "main_stage_depth",
    "main_stage_height",
    "right_stage_enabled",
    "right_stage_width",
    "right_stage_depth",
    "right_stage_height",
    "left_stage_enabled",
    "left_stage_width",
    "left_stage_depth",
    "left_stage_height",
    "rear_stage_enabled",
    "rear_stage_width",
    "rear_stage_depth",
    "rear_stage_height",
    "understage_enabled",
    "understage_depth",
)

BALCONY_TIER_KEY_MAPS = (
    {
        "balcony_enabled": "balcony_enabled",
        "balcony_last_platform_z": "balcony_last_platform_z",
        "balcony_row_count": "balcony_row_count",
        "balcony_row_pitch": "balcony_row_pitch",
        "balcony_railing_t": "balcony_railing_t",
        "balcony_railing_w": "balcony_railing_w",
        "balcony_railing_h": "balcony_railing_h",
        "balcony_settings_version": "balcony_settings_version",
    },
    {
        "balcony_enabled": "balcony2_enabled",
        "balcony_last_platform_z": "balcony2_last_platform_z",
        "balcony_row_count": "balcony2_row_count",
        "balcony_row_pitch": "balcony2_row_pitch",
        "balcony_railing_t": "balcony2_railing_t",
        "balcony_railing_w": "balcony2_railing_w",
        "balcony_railing_h": "balcony2_railing_h",
        "balcony_settings_version": "balcony2_settings_version",
    },
)
BALCONY_PARAM_KEYS = tuple(
    actual_key
    for key_map in BALCONY_TIER_KEY_MAPS
    for actual_key in key_map.values()
)

# Embedded from ForCheck/AuditoriumChair.3dm.
# Coordinates are millimeters in the chair's local XZ plane. The chair's
# rear-bottom insertion point is (0, 0); negative X points toward the stage.
CHAIR_LINE_DATA = [
    (109.441597, 887.151248, -16.497809, 395.987567),
    (-35.421780, 731.709456, -67.748089, 611.914299),
    (109.441597, 887.151248, 113.852888, 1004.061321),
    (72.965946, 1030.006384, 88.874478, 1030.003958),
    (23.296782, 949.931034, 24.709211, 981.920831),
    (-10.799997, 493.737709, -59.233190, 506.156476),
    (-533.598594, 332.163906, -527.956858, 406.951410),
    (-501.147112, 430.000000, -386.621654, 421.360558),
    (-510.550004, 305.354159, -366.335303, 294.475053),
    (-327.677687, 173.391841, -144.557456, 173.391841),
    (-10.799997, 493.737709, -134.835307, 10.000000),
    (-59.233190, 506.156476, -186.452800, 10.000000),
    (-81.371572, 10.000000, -81.371572, 0.000000),
    (-241.867298, 10.000000, -241.867298, 0.000000),
    (-241.867298, 10.000000, -81.371572, 10.000000),
    (-557.677469, 436.787874, -613.365783, 78.479349),
    (-676.961206, 456.537391, -736.753610, 83.817485),
    (-667.790572, -0.000017, -667.526169, 20.508689),
    (-606.102288, 46.053704, -611.715745, -0.000017),
    (-853.804758, 12.686526, -851.172124, -0.000017),
    (-766.189012, -0.000017, -667.526169, 20.508689),
    (-706.173836, 82.494510, -853.804758, 12.686526),
    (-736.753610, 83.817485, -613.365783, 78.479349),
    (-614.100833, 78.511149, -606.102288, 46.053704),
    (-727.267668, 53.630744, -737.791411, 67.543990),
    (-727.267668, 53.630744, -650.820850, 80.099770),
    (-398.866663, 629.165992, -420.721870, 627.745933),
    (-541.589181, 569.584826, -386.069834, 568.442548),
    (-421.929483, 686.148786, -420.721870, 627.745933),
    (-421.929483, 686.148786, -511.720883, 647.891992),
    (-431.795720, 612.714909, -421.128749, 642.426059),
    (-475.617640, 581.995521, -431.795720, 612.714909),
    (-557.677469, 436.787874, -503.128776, 428.963496),
    (-582.196916, 567.755860, -541.589181, 569.584826),
    (-543.139798, 590.608880, -537.353806, 579.046103),
    (-511.720883, 647.891992, -543.139798, 590.608880),
    (-537.353806, 579.046103, -475.617640, 581.995521),
    (-178.554690, 643.480927, -227.343432, 640.310842),
    (-178.554690, 643.480927, -143.864902, 656.378849),
    (-224.778426, 734.211105, -421.929483, 686.148786),
    (-11.842996, 806.825925, -77.992015, 614.294832),
    (1.716694, 883.641718, -11.842996, 806.825925),
    (-221.634809, 838.182009, -259.017571, 725.864141),
    (-191.912526, 1144.040320, -223.058830, 1092.564153),
    (-223.058830, 1092.564153, -197.203102, 1090.250121),
    (-131.918741, 964.433298, -221.634809, 838.182009),
    (-10.179724, 1212.952351, 13.140247, 1177.999481),
    (-52.932967, 1233.341492, -10.179724, 1212.952351),
    (-179.358464, 1132.148872, -180.641536, 1115.835025),
    (-191.912526, 1144.040320, -195.060025, 1108.871897),
    (-18.422003, 956.712001, 1.716694, 883.641718),
    (-37.061129, 988.494298, -18.422003, 956.712001),
    (-131.918741, 964.433298, -37.061129, 988.494298),
    (-194.072254, 1226.246781, -196.143849, 1200.584942),
    (-196.143849, 1200.584942, -178.587513, 1187.389339),
    (-132.182271, 1143.433328, -178.587513, 1187.389339),
    (-128.353293, 1237.912957, -194.072254, 1226.246781),
    (-99.743684, 1238.287542, -52.932967, 1233.341492),
    (-128.353293, 1237.912957, -99.743684, 1238.287542),
    (13.140247, 1177.999481, 15.165020, 1126.014812),
    (15.165020, 1126.014812, 8.593754, 1086.411991),
    (8.593754, 1086.411991, -17.496580, 1038.939896),
    (-60.305627, 1131.915339, -47.784738, 1119.438799),
    (-132.182271, 1143.433328, -104.470998, 1129.435084),
    (-76.694745, 1126.568562, -60.305627, 1131.915339),
    (-17.496580, 1038.939896, -40.058924, 1016.265267),
    (-40.058924, 1016.265267, -59.957008, 1044.223418),
    (-40.058924, 1016.265267, -37.061129, 988.494298),
    (-162.165567, 1121.990179, -180.641536, 1115.835025),
    (-93.920817, 1086.471975, -76.694745, 1126.568562),
    (-104.470998, 1129.435084, -109.222093, 1084.813201),
    (-59.957008, 1044.223418, -77.405703, 1062.195437),
    (-109.222093, 1084.813201, -93.920817, 1086.471975),
    (-187.059107, 1151.036301, -151.419667, 1140.392690),
    (-183.656688, 1134.688546, -162.165567, 1121.990179),
    (-171.698239, 1001.458494, -136.339674, 1001.536223),
    (-136.339674, 1001.536223, -131.918741, 964.433298),
    (-136.339674, 1001.536223, -91.496144, 1042.590761),
    (-24.915187, 845.103653, -143.864902, 656.378849),
    (-136.343544, 892.775524, -224.778426, 734.211105),
]

CHAIR_ARC_DATA = [
    (-2.920470, 808.081844, -21.825110, 771.025089,
     -35.421780, 731.709456),
    (-2.920470, 808.081844, 22.944049, 876.648833,
     23.296782, 949.931034),
    (113.852888, 1004.061321, 106.879847, 1022.343780,
     88.874478, 1030.003958),
    (72.788380, 1030.000000, 39.318317, 1015.390894,
     24.709211, 981.920831),
    (-44.365699, 362.831470, -26.655294, 376.235382,
     -16.497809, 395.987567),
    (-47.677370, 507.875227, 13.525044, 537.726628,
     -16.326357, 598.929041),
    (-501.147112, 430.000000, -519.325504, 424.028185,
     -527.956858, 406.951410),
    (-394.379564, 635.337626, -401.815058, 609.484001,
     -381.495427, 591.854223),
    (-357.651840, 653.862311, -377.205489, 646.958883,
     -394.379564, 635.337626),
    (-47.677370, 507.875227, -212.486833, 558.210538,
     -381.495427, 591.854223),
    (-16.326357, 598.929041, -185.564303, 635.248579,
     -357.651840, 653.862311),
    (-533.598594, 332.163906, -527.626779, 313.985513,
     -510.550004, 305.354159),
    (-383.584321, 592.161224, -382.064320, 379.247627,
     -327.677687, 173.391841),
    (-582.196916, 567.755860, -651.363836, 530.708459,
     -676.961206, 456.537391),
    (-195.060025, 1108.871897, -193.166233, 1053.036558,
     -171.698239, 1001.458494),
    (-178.587513, 1187.389339, -189.119393, 1166.904232,
     -191.912526, 1144.040320),
    (-89.026188, 1056.508595, -58.010294, 1081.161200,
     -47.784738, 1119.438799),
]


DEFAULTS = {
    "stage_height": 1100.0,
    "first_row_distance": DEFAULT_FIRST_PLATFORM_START_DISTANCE,
    "stage_apron_projection": 1200.0,
    "orchestra_pit_depth": 0.0,
    "row_pitch": 1100.0,
    "stage_sight_point_z": 50.0,
    "sight_point_z": CHAIR_SIGHT_POINT_Z,
    "sight_clearance": 113.0,
    "row_count": 15,
    "row_groups": "15",
    "aisle_width": 1000.0,
    "aisle_stair_tread_depth": 300.0,
    "balcony_enabled": False,
    "balcony_last_platform_z": 6000.0,
    "balcony_row_count": 1,
    "balcony_row_pitch": 1100.0,
    "balcony_railing_t": 250.0,
    "balcony_railing_w": 530.0,
    "balcony_railing_h": 750.0,
    "balcony_settings_version": 0,
    "balcony2_enabled": False,
    "balcony2_last_platform_z": 9000.0,
    "balcony2_row_count": 1,
    "balcony2_row_pitch": 1100.0,
    "balcony2_railing_t": 250.0,
    "balcony2_railing_w": 530.0,
    "balcony2_railing_h": 750.0,
    "balcony2_settings_version": 0,
    "max_slope_denominator": 12.0,
    "floor_type": "stepped",
    "flipped": False,
    "show_sightlines": True,
    "show_eye_points": True,
    "show_seats": True,
    "show_3d_seats": False,
    "seat_module_width": 550.0,
    "seat_blocks": "8,16,8",
    "longitudinal_aisle_width": 1200.0,
    "side_floor_margin": 1200.0,
    "show_floor_surfaces": False,
    "show_riser_height_labels": True,
}


def calculated_proscenium_defaults(opening_width_mm, opening_height_mm):
    """
    Return the initial proscenium stage-space dimensions in millimeters.

    The source document defines the main-stage width as PW + 8 m. The
    requested initial depth rule is PW * 1.2. Optional stage spaces start
    enabled and receive the same calculated dimensions for later editing.
    """
    calculated_width = opening_width_mm + 8000.0
    calculated_depth = opening_width_mm * 1.2
    calculated_main_height = (
        opening_height_mm * 3.0 + STAGE_EQUIPMENT_CLEARANCE
    )
    calculated_aux_height = (
        opening_height_mm + STAGE_EQUIPMENT_CLEARANCE
    )
    calculated_understage_depth = (
        opening_height_mm + STAGE_EQUIPMENT_CLEARANCE
    )
    return {
        "stage_preview_mode": "section_2d",
        "main_stage_width": calculated_width,
        "main_stage_depth": calculated_depth,
        "main_stage_height": calculated_main_height,
        "right_stage_enabled": True,
        "right_stage_width": calculated_width,
        "right_stage_depth": calculated_depth,
        "right_stage_height": calculated_aux_height,
        "left_stage_enabled": True,
        "left_stage_width": calculated_width,
        "left_stage_depth": calculated_depth,
        "left_stage_height": calculated_aux_height,
        "rear_stage_enabled": True,
        "rear_stage_width": calculated_width,
        "rear_stage_depth": calculated_depth,
        "rear_stage_height": calculated_aux_height,
        "understage_enabled": True,
        "understage_depth": calculated_understage_depth,
    }


def validate_proscenium_params(params, opening_width_mm):
    """Validate editable stage-space dimensions without changing them."""
    if params["main_stage_width"] <= 0.0:
        raise ValueError("주무대 폭은 0보다 커야 합니다.")
    if params["main_stage_depth"] <= 0.0:
        raise ValueError("주무대 깊이는 0보다 커야 합니다.")
    if params["main_stage_height"] <= STAGE_EQUIPMENT_CLEARANCE:
        raise ValueError("주무대 높이는 2,000 mm보다 커야 합니다.")
    if params["stage_preview_mode"] not in ("section_2d", "space_3d"):
        raise ValueError("무대 프리뷰 방식을 다시 선택해 주세요.")

    optional_stages = (
        ("오른무대", "right"),
        ("왼무대", "left"),
        ("뒷무대", "rear"),
    )
    for label, prefix in optional_stages:
        if not params[prefix + "_stage_enabled"]:
            continue
        if params[prefix + "_stage_width"] <= 0.0:
            raise ValueError("{0} 폭은 0보다 커야 합니다.".format(label))
        if params[prefix + "_stage_depth"] <= 0.0:
            raise ValueError("{0} 깊이는 0보다 커야 합니다.".format(label))
        if (
            params[prefix + "_stage_height"]
            <= STAGE_EQUIPMENT_CLEARANCE
        ):
            raise ValueError(
                "{0} 높이는 2,000 mm보다 커야 합니다.".format(label)
            )

    if params["understage_enabled"]:
        if params["understage_depth"] <= STAGE_EQUIPMENT_CLEARANCE:
            raise ValueError("하부무대 Z 깊이는 2,000 mm보다 커야 합니다.")


def calculate_stage_section_dimensions(params, opening_height_mm):
    """Return editable stage and PH-based auditorium levels in millimeters."""
    ph = opening_height_mm
    understage_depth = params["understage_depth"]
    return {
        "ph": ph,
        "main_grid_z": (
            params["main_stage_height"] - STAGE_EQUIPMENT_CLEARANCE
        ),
        "main_tower_top_z": params["main_stage_height"],
        "right_grid_z": (
            params["right_stage_height"] - STAGE_EQUIPMENT_CLEARANCE
        ),
        "right_top_z": params["right_stage_height"],
        "left_grid_z": (
            params["left_stage_height"] - STAGE_EQUIPMENT_CLEARANCE
        ),
        "left_top_z": params["left_stage_height"],
        "rear_grid_z": (
            params["rear_stage_height"] - STAGE_EQUIPMENT_CLEARANCE
        ),
        "rear_top_z": params["rear_stage_height"],
        "clearance_grid_z": ph,
        "clearance_top_z": ph + STAGE_EQUIPMENT_CLEARANCE,
        "understage_floor_z": (
            -understage_depth + STAGE_EQUIPMENT_CLEARANCE
        ),
        "understage_bottom_z": -understage_depth,
        "auditorium_ceiling_z": ph * 2.0,
    }


def unit_scale_from_mm(doc):
    """Return model-unit length corresponding to 1 millimeter."""
    return Rhino.RhinoMath.UnitScale(
        Rhino.UnitSystem.Millimeters,
        doc.ModelUnitSystem
    )


def almost_equal(a, b, tolerance=1e-8):
    return abs(a - b) <= tolerance


def is_finite_number(value):
    """Return finite-number status across Rhino Python runtimes."""
    try:
        number = float(value)
    except Exception:
        return False
    return not math.isnan(number) and not math.isinf(number)


def ceil_to_integer_mm(value):
    """
    Round a millimeter value upward only when it has a fractional part.

    Floating-point noise close to an integer is suppressed so that
    173.00000000001 does not become 174.
    """
    nearest = round(value)
    if abs(value - nearest) <= 1e-8:
        return float(nearest)
    return float(math.ceil(value))


def point_at(stage_point, audience_direction, x_mm, z_mm, mm_scale):
    return (
        stage_point
        + audience_direction * (x_mm * mm_scale)
        + rg.Vector3d.ZAxis * (z_mm * mm_scale)
    )


def line_curve(point_a, point_b):
    return rg.LineCurve(point_a, point_b)


def stage_space_point(
    stage_point,
    stage_right_direction,
    stage_back_direction,
    x_mm,
    y_mm,
    z_mm,
    mm_scale
):
    return (
        stage_point
        + stage_right_direction * (x_mm * mm_scale)
        + stage_back_direction * (y_mm * mm_scale)
        + rg.Vector3d.ZAxis * (z_mm * mm_scale)
    )


def build_plan_rectangle(
    stage_point,
    stage_right_direction,
    stage_back_direction,
    min_x_mm,
    max_x_mm,
    min_y_mm,
    max_y_mm,
    mm_scale,
    z_mm=0.0
):
    """Create a closed rectangle at a stage-relative Z level."""
    def plan_point(x_mm, y_mm):
        return stage_space_point(
            stage_point,
            stage_right_direction,
            stage_back_direction,
            x_mm,
            y_mm,
            z_mm,
            mm_scale
        )

    points = [
        plan_point(min_x_mm, min_y_mm),
        plan_point(max_x_mm, min_y_mm),
        plan_point(max_x_mm, max_y_mm),
        plan_point(min_x_mm, max_y_mm),
        plan_point(min_x_mm, min_y_mm),
    ]
    return rg.PolylineCurve(points)


def get_stage_directions(audience_direction):
    """Return stage-right and stage-back unit vectors."""
    stage_back_direction = rg.Vector3d(audience_direction)
    stage_back_direction.Reverse()

    stage_right_direction = rg.Vector3d.CrossProduct(
        audience_direction,
        rg.Vector3d.ZAxis
    )
    if not stage_right_direction.Unitize():
        raise ValueError("무대 평면의 좌우 방향을 계산할 수 없습니다.")

    return stage_right_direction, stage_back_direction


def calculate_proscenium_space_layout(params):
    """Return shared plan bounds for every active proscenium space."""
    main_width = params["main_stage_width"]
    main_depth = params["main_stage_depth"]
    half_main_width = main_width * 0.5

    spaces = [
        {
            "name": "MainStage",
            "plan_color": PREVIEW_MAIN_STAGE,
            "section_type": "main",
            "height_group": "main",
            "min_x": -half_main_width,
            "max_x": half_main_width,
            "min_y": 0.0,
            "max_y": main_depth,
        },
        {
            "name": "RightStageClearance",
            "plan_color": PREVIEW_STAGE_CLEARANCE,
            "section_type": "aux",
            "height_group": "clearance",
            "min_x": half_main_width,
            "max_x": half_main_width + SIDE_STAGE_CLEARANCE,
            "min_y": 0.0,
            "max_y": main_depth,
        },
        {
            "name": "LeftStageClearance",
            "plan_color": PREVIEW_STAGE_CLEARANCE,
            "section_type": "aux",
            "height_group": "clearance",
            "min_x": -half_main_width - SIDE_STAGE_CLEARANCE,
            "max_x": -half_main_width,
            "min_y": 0.0,
            "max_y": main_depth,
        },
    ]

    if params["right_stage_enabled"]:
        spaces.append(
            {
                "name": "RightStage",
                "plan_color": PREVIEW_AUX_STAGE,
                "section_type": "aux",
                "height_group": "right",
                "min_x": half_main_width + SIDE_STAGE_CLEARANCE,
                "max_x": (
                    half_main_width
                    + SIDE_STAGE_CLEARANCE
                    + params["right_stage_width"]
                ),
                "min_y": 0.0,
                "max_y": params["right_stage_depth"],
            }
        )

    if params["left_stage_enabled"]:
        spaces.append(
            {
                "name": "LeftStage",
                "plan_color": PREVIEW_AUX_STAGE,
                "section_type": "aux",
                "height_group": "left",
                "min_x": (
                    -half_main_width
                    - SIDE_STAGE_CLEARANCE
                    - params["left_stage_width"]
                ),
                "max_x": -half_main_width - SIDE_STAGE_CLEARANCE,
                "min_y": 0.0,
                "max_y": params["left_stage_depth"],
            }
        )

    if params["rear_stage_enabled"]:
        half_rear_width = params["rear_stage_width"] * 0.5
        spaces.append(
            {
                "name": "RearStage",
                "plan_color": PREVIEW_AUX_STAGE,
                "section_type": "aux",
                "height_group": "rear",
                "min_x": -half_rear_width,
                "max_x": half_rear_width,
                "min_y": main_depth,
                "max_y": main_depth + params["rear_stage_depth"],
            }
        )

    return spaces


def build_proscenium_plan_curves(
    stage_point,
    audience_direction,
    params,
    mm_scale
):
    """
    Build main, clearance, side and rear stage-space plan outlines.

    Stage right/left follow the performer's viewpoint while facing the
    audience. The main stage front edge lies on the proscenium opening plane.
    """
    stage_right_direction, stage_back_direction = get_stage_directions(
        audience_direction
    )

    stage_curves = []
    for space in calculate_proscenium_space_layout(params):
        curve = build_plan_rectangle(
            stage_point,
            stage_right_direction,
            stage_back_direction,
            space["min_x"],
            space["max_x"],
            space["min_y"],
            space["max_y"],
            mm_scale
        )
        stage_curves.append(
            (curve, space["plan_color"], space["name"] + "Plan")
        )

    return stage_curves


def build_stage_space_3d_curves(
    stage_point,
    audience_direction,
    params,
    section_dimensions,
    mm_scale
):
    """Build stage volume, grid and understage wireframe curves."""
    stage_right_direction, stage_back_direction = get_stage_directions(
        audience_direction
    )
    spaces = calculate_proscenium_space_layout(params)
    section_curves = []

    for space in spaces:
        height_group = space["height_group"]
        if height_group == "main":
            top_z = section_dimensions["main_tower_top_z"]
            grid_z = section_dimensions["main_grid_z"]
            section_name = "MainFlyTower"
        elif height_group == "clearance":
            top_z = section_dimensions["clearance_top_z"]
            grid_z = section_dimensions["clearance_grid_z"]
            section_name = space["name"] + "UpperSpace"
        else:
            top_z = section_dimensions[height_group + "_top_z"]
            grid_z = section_dimensions[height_group + "_grid_z"]
            section_name = space["name"] + "UpperSpace"

        top_curve = build_plan_rectangle(
            stage_point,
            stage_right_direction,
            stage_back_direction,
            space["min_x"],
            space["max_x"],
            space["min_y"],
            space["max_y"],
            mm_scale,
            top_z
        )
        grid_curve = build_plan_rectangle(
            stage_point,
            stage_right_direction,
            stage_back_direction,
            space["min_x"],
            space["max_x"],
            space["min_y"],
            space["max_y"],
            mm_scale,
            grid_z
        )
        section_curves.append(
            (top_curve, PREVIEW_STAGE_SECTION, section_name + "Top")
        )
        section_curves.append(
            (grid_curve, PREVIEW_GRID, section_name + "Grid")
        )

        corners = (
            (space["min_x"], space["min_y"]),
            (space["max_x"], space["min_y"]),
            (space["max_x"], space["max_y"]),
            (space["min_x"], space["max_y"]),
        )
        for x_mm, y_mm in corners:
            floor_point = stage_space_point(
                stage_point,
                stage_right_direction,
                stage_back_direction,
                x_mm,
                y_mm,
                0.0,
                mm_scale
            )
            top_point = stage_space_point(
                stage_point,
                stage_right_direction,
                stage_back_direction,
                x_mm,
                y_mm,
                top_z,
                mm_scale
            )
            section_curves.append(
                (
                    line_curve(floor_point, top_point),
                    PREVIEW_STAGE_SECTION,
                    section_name + "Edge",
                )
            )

    if not params["understage_enabled"]:
        return section_curves

    main_space = spaces[0]
    understage_floor_z = section_dimensions["understage_floor_z"]
    understage_bottom_z = section_dimensions["understage_bottom_z"]

    understage_floor = build_plan_rectangle(
        stage_point,
        stage_right_direction,
        stage_back_direction,
        main_space["min_x"],
        main_space["max_x"],
        main_space["min_y"],
        main_space["max_y"],
        mm_scale,
        understage_floor_z
    )
    understage_bottom = build_plan_rectangle(
        stage_point,
        stage_right_direction,
        stage_back_direction,
        main_space["min_x"],
        main_space["max_x"],
        main_space["min_y"],
        main_space["max_y"],
        mm_scale,
        understage_bottom_z
    )
    section_curves.append(
        (
            understage_floor,
            PREVIEW_GRID,
            "MainUnderstageEquipmentFloor",
        )
    )
    section_curves.append(
        (
            understage_bottom,
            PREVIEW_UNDERSTAGE,
            "MainUnderstageBottom",
        )
    )

    main_corners = (
        (main_space["min_x"], main_space["min_y"]),
        (main_space["max_x"], main_space["min_y"]),
        (main_space["max_x"], main_space["max_y"]),
        (main_space["min_x"], main_space["max_y"]),
    )
    for x_mm, y_mm in main_corners:
        stage_floor_point = stage_space_point(
            stage_point,
            stage_right_direction,
            stage_back_direction,
            x_mm,
            y_mm,
            0.0,
            mm_scale
        )
        bottom_point = stage_space_point(
            stage_point,
            stage_right_direction,
            stage_back_direction,
            x_mm,
            y_mm,
            understage_bottom_z,
            mm_scale
        )
        section_curves.append(
            (
                line_curve(stage_floor_point, bottom_point),
                PREVIEW_UNDERSTAGE,
                "MainUnderstageEdge",
            )
        )

    return section_curves


def build_stage_section_2d_curves(
    stage_point,
    audience_direction,
    params,
    section_dimensions,
    mm_scale
):
    """Build the central audience-main-rear-stage longitudinal section."""
    section_curves = []

    def section_point(x_mm, z_mm):
        return point_at(
            stage_point,
            audience_direction,
            x_mm,
            z_mm,
            mm_scale
        )

    def add_upper_profile(
        front_x,
        back_x,
        top_z,
        grid_z,
        prefix,
        floor_color
    ):
        floor_front = section_point(front_x, 0.0)
        floor_back = section_point(back_x, 0.0)
        top_front = section_point(front_x, top_z)
        top_back = section_point(back_x, top_z)
        grid_front = section_point(front_x, grid_z)
        grid_back = section_point(back_x, grid_z)

        section_curves.extend(
            [
                (
                    line_curve(floor_front, floor_back),
                    floor_color,
                    prefix + "Floor",
                ),
                (
                    line_curve(top_front, top_back),
                    PREVIEW_STAGE_SECTION,
                    prefix + "Top",
                ),
                (
                    line_curve(floor_front, top_front),
                    PREVIEW_STAGE_SECTION,
                    prefix + "FrontEdge",
                ),
                (
                    line_curve(floor_back, top_back),
                    PREVIEW_STAGE_SECTION,
                    prefix + "BackEdge",
                ),
                (
                    line_curve(grid_front, grid_back),
                    PREVIEW_GRID,
                    prefix + "Grid",
                ),
            ]
        )

    main_back_x = -params["main_stage_depth"]
    add_upper_profile(
        0.0,
        main_back_x,
        section_dimensions["main_tower_top_z"],
        section_dimensions["main_grid_z"],
        "MainFlyTowerSection",
        PREVIEW_MAIN_STAGE
    )

    if params["rear_stage_enabled"]:
        rear_back_x = main_back_x - params["rear_stage_depth"]
        add_upper_profile(
            main_back_x,
            rear_back_x,
            section_dimensions["rear_top_z"],
            section_dimensions["rear_grid_z"],
            "RearStageSection",
            PREVIEW_AUX_STAGE
        )

    if params["understage_enabled"]:
        bottom_z = section_dimensions["understage_bottom_z"]
        equipment_floor_z = section_dimensions["understage_floor_z"]
        bottom_front = section_point(0.0, bottom_z)
        bottom_back = section_point(main_back_x, bottom_z)
        floor_front = section_point(0.0, 0.0)
        floor_back = section_point(main_back_x, 0.0)
        equipment_front = section_point(0.0, equipment_floor_z)
        equipment_back = section_point(
            main_back_x,
            equipment_floor_z
        )

        section_curves.extend(
            [
                (
                    line_curve(bottom_front, bottom_back),
                    PREVIEW_UNDERSTAGE,
                    "MainUnderstageSectionBottom",
                ),
                (
                    line_curve(floor_front, bottom_front),
                    PREVIEW_UNDERSTAGE,
                    "MainUnderstageSectionFrontEdge",
                ),
                (
                    line_curve(floor_back, bottom_back),
                    PREVIEW_UNDERSTAGE,
                    "MainUnderstageSectionBackEdge",
                ),
                (
                    line_curve(equipment_front, equipment_back),
                    PREVIEW_GRID,
                    "MainUnderstageSectionEquipmentFloor",
                ),
            ]
        )

    return section_curves


def build_stage_audience_transition_curves(
    stage_point,
    audience_direction,
    params,
    mm_scale
):
    """Build the apron and optional orchestra-pit central section."""
    apron_x = params["stage_apron_projection"]
    platform_start_x = params["first_row_distance"]
    first_floor_z = -params["stage_height"]
    pit_depth = params["orchestra_pit_depth"]
    pit_floor_z = first_floor_z - pit_depth
    curves = []

    def section_point(x_mm, z_mm):
        return point_at(
            stage_point,
            audience_direction,
            x_mm,
            z_mm,
            mm_scale
        )

    stage_origin = section_point(0.0, 0.0)
    apron_end = section_point(apron_x, 0.0)
    if apron_x > 1e-8:
        curves.append(
            (
                line_curve(stage_origin, apron_end),
                PREVIEW_STAGE_APRON,
                "StageApronSection",
            )
        )

    if pit_depth > 1e-8:
        pit_front = section_point(apron_x, pit_floor_z)
        pit_rear = section_point(platform_start_x, pit_floor_z)
        first_platform = section_point(
            platform_start_x,
            first_floor_z
        )

        curves.append(
            (
                line_curve(apron_end, pit_front),
                PREVIEW_ORCHESTRA_PIT,
                "OrchestraPitFront",
            )
        )
        if platform_start_x - apron_x > 1e-8:
            curves.append(
                (
                    line_curve(pit_front, pit_rear),
                    PREVIEW_ORCHESTRA_PIT,
                    "OrchestraPitBottom",
                )
            )
        curves.append(
            (
                line_curve(pit_rear, first_platform),
                PREVIEW_ORCHESTRA_PIT,
                "OrchestraPitRear",
            )
        )
    else:
        apron_floor = section_point(apron_x, first_floor_z)
        first_platform = section_point(
            platform_start_x,
            first_floor_z
        )
        if abs(first_floor_z) > 1e-8:
            curves.append(
                (
                    line_curve(apron_end, apron_floor),
                    PREVIEW_STAGE_APRON,
                    "StageFrontSection",
                )
            )
        if platform_start_x - apron_x > 1e-8:
            curves.append(
                (
                    line_curve(apron_floor, first_platform),
                    PREVIEW_FLOOR,
                    "StageAudienceFloorSection",
                )
            )

    return curves


def build_chair_curves(
    stage_point,
    audience_direction,
    row_x_mm,
    floor_z_mm,
    mm_scale
):
    """Create one embedded chair at its rear-bottom row insertion point."""
    def chair_point(local_x_mm, local_z_mm):
        return point_at(
            stage_point,
            audience_direction,
            row_x_mm + local_x_mm,
            floor_z_mm + local_z_mm,
            mm_scale
        )

    curves = []

    for x0, z0, x1, z1 in CHAIR_LINE_DATA:
        curves.append(
            line_curve(chair_point(x0, z0), chair_point(x1, z1))
        )

    for x0, z0, xm, zm, x1, z1 in CHAIR_ARC_DATA:
        arc = rg.Arc(
            chair_point(x0, z0),
            chair_point(xm, zm),
            chair_point(x1, z1)
        )
        if arc.IsValid:
            curves.append(rg.ArcCurve(arc))

    return curves


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
    }


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


def choose_seat_source_components(candidates):
    if len(candidates) < 2:
        raise ValueError(
            "AuditoriumSeat.3dm requires separate chair-body and "
            "armrest objects or block definitions."
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
    for chair_candidate in candidates:
        for armrest_candidate in candidates:
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

    chair_candidate, armrest_candidate = best_pair
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
            "AuditoriumSeat.3dm source dimensions do not match: {0}.".format(
                ", ".join(dimension_errors)
            )
        )

    return chair_candidate, armrest_candidate


def normalize_seat_source_component(candidate):
    """Preserve the source block's authored local origin and orientation."""
    geometries = [
        geometry.Duplicate()
        for geometry in candidate["geometries"]
        if geometry is not None
    ]
    source_box = geometry_collection_bounding_box(geometries)
    return {
        "source_name": candidate["name"],
        "geometries": geometries,
        "width": source_box.Max.X - source_box.Min.X,
        "source_z_offset": source_box.Min.Z,
        "bounding_box": source_box,
        "preview_mesh": build_seat_source_preview_mesh(geometries),
    }


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
        for definition in model.AllInstanceDefinitions:
            geometries = file3dm_definition_geometry(model, definition)
            candidate = source_component_candidate(
                definition.Name,
                "definition:{0}".format(definition.Id),
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

        chair_candidate, armrest_candidate = (
            choose_seat_source_components(candidates)
        )
        chair_component = normalize_seat_source_component(
            chair_candidate
        )
        armrest_component = normalize_seat_source_component(
            armrest_candidate
        )

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
            "status": (
                "{0}: chair {1} ({2:.1f} mm), "
                "armrest {3} ({4:.1f} mm)"
            ).format(
                SEAT_SOURCE_FILE_NAME,
                chair_component["source_name"],
                chair_component["width"],
                armrest_component["source_name"],
                armrest_component["width"]
            ),
        }
    finally:
        model.Dispose()


def calculate_3d_seat_placements(params, section_result):
    """Create stalls chair and shared-armrest placement records."""
    module_width = params["seat_module_width"]
    aisle_width = params["longitudinal_aisle_width"]
    block_counts = params["seat_block_counts"]
    total_module_width = sum(
        count * module_width
        for count in block_counts
    )
    total_width = (
        total_module_width
        + max(len(block_counts) - 1, 0) * aisle_width
    )
    left_boundary = -total_width * 0.5

    chair_placements = []
    armrest_placements = []
    for row_index, (row_x, floor_z) in enumerate(
        zip(
            section_result["x_values"],
            section_result["base_z_values"]
        )
    ):
        block_boundary = left_boundary
        for block_index, block_count in enumerate(block_counts):
            for seat_index in range(block_count):
                chair_placements.append({
                    "row_index": row_index,
                    "block_index": block_index,
                    "seat_index": seat_index,
                    "row_x": row_x,
                    "floor_z": floor_z,
                    "lateral": (
                        block_boundary
                        + (seat_index + 0.5) * module_width
                    ),
                })
            for armrest_index in range(block_count + 1):
                armrest_placements.append({
                    "row_index": row_index,
                    "block_index": block_index,
                    "armrest_index": armrest_index,
                    "row_x": row_x,
                    "floor_z": floor_z,
                    "lateral": (
                        block_boundary
                        + armrest_index * module_width
                    ),
                })
            block_boundary += block_count * module_width
            if block_index < len(block_counts) - 1:
                block_boundary += aisle_width

    return {
        "chair_placements": chair_placements,
        "armrest_placements": armrest_placements,
        "chairs_per_row": sum(block_counts),
        "armrests_per_row": (
            sum(block_counts) + len(block_counts)
        ),
        "total_width": total_width,
    }


def calculate_total_3d_seat_count(params, balcony_results):
    """Count seats across the stalls and every valid generated balcony."""
    valid_row_count = params["row_count"]
    for balcony_result in balcony_results:
        if not balcony_result_is_displayable(balcony_result):
            continue
        valid_row_count += balcony_result["row_count"]

    seats_per_row = sum(params["seat_block_counts"])
    return valid_row_count * seats_per_row


def format_riser_height_label(height_mm):
    rounded_height = round(height_mm)
    if abs(height_mm - rounded_height) <= 0.05:
        return "H {0:.0f} mm".format(height_mm)
    return "H {0:.1f} mm".format(height_mm)


def build_riser_height_preview_labels(
    stage_point,
    audience_direction,
    params,
    stalls_result,
    balcony_results,
    mm_scale
):
    """Build screen-facing preview labels; these are never baked."""
    labels = []

    def add_label(
        riser_x,
        bottom_z,
        riser_height,
        upper_platform_depth,
        background_color,
        text_color
    ):
        if riser_height <= 1e-8:
            return
        label_point = point_at(
            stage_point,
            audience_direction,
            riser_x + upper_platform_depth * 0.5,
            bottom_z + riser_height,
            mm_scale
        )
        labels.append(
            (
                label_point,
                format_riser_height_label(riser_height),
                background_color,
                text_color,
            )
        )

    if params["floor_type"] == "stepped":
        x_values = stalls_result["x_values"]
        base_z_values = stalls_result["base_z_values"]
        riser_values = stalls_result["riser_values"]
        violations = stalls_result["violations"]
        aisle_before_values = stalls_result["aisle_before_values"]
        stair_tread_counts = stalls_result[
            "aisle_stair_tread_counts"
        ]
        stair_riser_heights = stalls_result[
            "aisle_stair_riser_heights"
        ]
        stair_run_values = stalls_result[
            "aisle_stair_run_values"
        ]
        row_pitch = params["row_pitch"]
        tread_depth = params["aisle_stair_tread_depth"]

        for index in range(1, len(x_values)):
            if aisle_before_values[index]:
                tread_count = stair_tread_counts[index]
                riser_height = stair_riser_heights[index]
                if riser_height <= 1e-8:
                    continue
                stair_x = (
                    x_values[index]
                    - row_pitch
                    - stair_run_values[index]
                )
                stair_z = base_z_values[index - 1]
                label_color = (
                    PREVIEW_WARNING
                    if violations[index]
                    else PREVIEW_AISLE
                )
                label_text_color = (
                    Color.White
                    if violations[index]
                    else Color.Black
                )
                for stair_index in range(tread_count + 1):
                    add_label(
                        stair_x,
                        stair_z,
                        riser_height,
                        (
                            tread_depth
                            if stair_index < tread_count
                            else row_pitch
                        ),
                        label_color,
                        label_text_color
                    )
                    stair_z += riser_height
                    if stair_index < tread_count:
                        stair_x += tread_depth
                continue

            add_label(
                x_values[index - 1],
                base_z_values[index - 1],
                riser_values[index],
                row_pitch,
                (
                    PREVIEW_WARNING
                    if violations[index]
                    else PREVIEW_FLOOR
                ),
                Color.White if violations[index] else Color.Black
            )

    for balcony_result in balcony_results:
        if not balcony_result_is_displayable(balcony_result):
            continue
        x_values = balcony_result["x_values"]
        base_z_values = balcony_result["base_z_values"]
        riser_values = balcony_result["riser_to_next_values"]
        for index in range(len(x_values) - 1):
            add_label(
                x_values[index],
                base_z_values[index],
                riser_values[index],
                x_values[index + 1] - x_values[index],
                PREVIEW_WARNING,
                Color.White
            )

    return labels


def format_section_height_dimension(height_mm):
    rounded_height = round(height_mm)
    if abs(height_mm - rounded_height) <= 0.05:
        return "H {0:,.0f} mm".format(height_mm)
    return "H {0:,.1f} mm".format(height_mm)


def build_section_height_dimension_preview(
    stage_point,
    audience_direction,
    params,
    stalls_result,
    balcony_results,
    auditorium_ceiling_z,
    rear_wall_x,
    mm_scale
):
    """Build preview-only outer height dimensions for seating tiers."""
    valid_balconies = [
        result
        for result in balcony_results
        if balcony_result_is_displayable(result)
    ]

    levels = [
        {
            "source_x": rear_wall_x,
            "z": auditorium_ceiling_z,
        }
    ]
    for balcony_result in reversed(valid_balconies):
        levels.extend(
            (
                {
                    "source_x": (
                        balcony_result["x_values"][-1]
                        + params["aisle_width"]
                    ),
                    "z": balcony_result["base_z_values"][-1],
                },
                {
                    "source_x": balcony_result[
                        "railing_front_x"
                    ],
                    "z": balcony_result["base_z_values"][0],
                },
            )
        )

    levels.extend(
        (
            {
                "source_x": rear_wall_x,
                "z": stalls_result["base_z_values"][-1],
            },
            {
                "source_x": (
                    stalls_result["x_values"][0]
                    - params["row_pitch"]
                ),
                "z": stalls_result["base_z_values"][0],
            },
        )
    )

    dimension_offset = max(
        900.0,
        params["aisle_width"] * 0.75
    )
    dimension_x = max(
        [rear_wall_x]
        + [level["source_x"] for level in levels]
    ) + dimension_offset

    curves = []
    labels = []
    for level in levels:
        extension_start = point_at(
            stage_point,
            audience_direction,
            level["source_x"],
            level["z"],
            mm_scale
        )
        extension_end = point_at(
            stage_point,
            audience_direction,
            dimension_x,
            level["z"],
            mm_scale
        )
        curves.append(
            (
                line_curve(extension_start, extension_end),
                PREVIEW_SECTION_DIMENSION,
                1,
            )
        )

    for index in range(len(levels) - 1):
        upper_z = levels[index]["z"]
        lower_z = levels[index + 1]["z"]
        upper_point = point_at(
            stage_point,
            audience_direction,
            dimension_x,
            upper_z,
            mm_scale
        )
        lower_point = point_at(
            stage_point,
            audience_direction,
            dimension_x,
            lower_z,
            mm_scale
        )
        curves.append(
            (
                line_curve(upper_point, lower_point),
                PREVIEW_SECTION_DIMENSION,
                1,
            )
        )
        label_point = point_at(
            stage_point,
            audience_direction,
            dimension_x + 120.0,
            (upper_z + lower_z) * 0.5,
            mm_scale
        )
        labels.append(
            (
                label_point,
                "{0}  {1}".format(
                    index + 1,
                    format_section_height_dimension(
                        abs(upper_z - lower_z)
                    )
                ),
                PREVIEW_SECTION_DIMENSION,
                Color.Black,
            )
        )

    return curves, labels


def seat_module_transform(
    stage_point,
    audience_direction,
    stage_right_direction,
    placement,
    mm_scale,
    local_x_scale=1.0
):
    """Map seat-local X/Y/Z to auditorium lateral/longitudinal/vertical."""
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

    transform = rg.Transform.Identity
    transform.M00 = stage_right_direction.X * mm_scale * local_x_scale
    transform.M10 = stage_right_direction.Y * mm_scale * local_x_scale
    transform.M20 = stage_right_direction.Z * mm_scale * local_x_scale
    transform.M01 = audience_direction.X * mm_scale
    transform.M11 = audience_direction.Y * mm_scale
    transform.M21 = audience_direction.Z * mm_scale
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
    placement_name="Stalls"
):
    placement_result = calculate_3d_seat_placements(
        params,
        section_result
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
    bake_instances = []
    chair_preview = rg.Mesh()
    armrest_preview = rg.Mesh()

    for placement in placement_result["chair_placements"]:
        transform = seat_module_transform(
            stage_point,
            audience_direction,
            stage_right_direction,
            placement,
            mm_scale,
            chair_x_scale
        )
        source_mesh = seat_source["chair"]["preview_mesh"]
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
            mm_scale
        )
        source_mesh = seat_source["armrest"]["preview_mesh"]
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

    if chair_preview.Faces.Count > 0:
        chair_preview.Normals.ComputeNormals()
        chair_preview.Compact()
        preview_meshes.append(
            (chair_preview, PREVIEW_3D_CHAIR)
        )
    if armrest_preview.Faces.Count > 0:
        armrest_preview.Normals.ComputeNormals()
        armrest_preview.Compact()
        preview_meshes.append(
            (armrest_preview, PREVIEW_3D_ARMREST)
        )

    placement_result["preview_meshes"] = preview_meshes
    placement_result["bake_instances"] = bake_instances
    placement_result["chair_x_scale"] = chair_x_scale
    placement_result["target_chair_width"] = target_chair_width
    placement_result["placement_name"] = placement_name
    return placement_result


def calculate_seat_layout_width(params):
    block_counts = params["seat_block_counts"]
    return (
        sum(block_counts) * params["seat_module_width"]
        + max(len(block_counts) - 1, 0)
        * params["longitudinal_aisle_width"]
    )


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
    }
    if curve_name in stalls_names:
        return stalls_names[curve_name]
    if (
        curve_name.startswith("Balcony")
        and (
            curve_name.endswith("Floor")
            or curve_name.endswith("RearAisle")
        )
    ):
        return curve_name + "Surface"
    return None


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
    section_bake_curves
):
    """Build stage, auditorium floor and section-envelope surfaces."""
    preview_meshes = []
    bake_breps = []
    stage_right_direction, stage_back_direction = get_stage_directions(
        audience_direction
    )

    for space in calculate_proscenium_space_layout(params):
        outline = build_plan_rectangle(
            stage_point,
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
    )
    append_understage_envelope_surfaces(
        stage_point,
        audience_direction,
        params,
        section_dimensions,
        mm_scale,
        absolute_tolerance,
        preview_meshes,
        bake_breps
    )

    seating_width = calculate_seat_layout_width(params)
    floor_width = (
        seating_width
        + SEAT_SOURCE_ARMREST_WIDTH
        + params["side_floor_margin"] * 2.0
    )
    for curve, color, curve_name in section_bake_curves:
        surface_name = section_floor_surface_name(curve_name)
        if surface_name is None:
            continue
        brep = extrude_section_curve_across_width(
            curve,
            stage_right_direction,
            floor_width,
            mm_scale
        )
        append_floor_surface(
            brep,
            color,
            surface_name,
            preview_meshes,
            bake_breps
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
        brep = extrude_section_curve_across_width(
            curve,
            stage_right_direction,
            floor_width,
            mm_scale
        )
        append_floor_surface(
            brep,
            color,
            surface_name,
            preview_meshes,
            bake_breps
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
    for curve, color, curve_name in section_bake_curves:
        surface_name = transition_surface_names.get(curve_name)
        if surface_name is None:
            continue
        brep = extrude_section_curve_across_width(
            curve,
            stage_right_direction,
            opening_width_mm,
            mm_scale
        )
        append_floor_surface(
            brep,
            color,
            surface_name,
            preview_meshes,
            bake_breps
        )

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
    }


def get_curve_plane(curve):
    try:
        result = curve.TryGetPlane()
        if isinstance(result, tuple):
            return result[0], result[1]
        return False, rg.Plane.Unset
    except Exception:
        return False, rg.Plane.Unset


def analyze_opening_rectangle(curve, doc):
    """
    Validate a four-sided planar vertical rectangle and return:
        stage_point: midpoint of the lowest edge
        default_direction: horizontal plane normal
        width: opening width in model units
        height: opening height in model units
    """
    if curve is None or not curve.IsClosed:
        raise ValueError("선택한 커브는 닫힌 직사각형이어야 합니다.")

    segments = curve.DuplicateSegments()
    if not segments or len(segments) != 4:
        raise ValueError("4개의 선분으로 이루어진 직사각형을 선택해 주세요.")

    tolerance = max(doc.ModelAbsoluteTolerance, 1e-6)
    linear_segments = []
    all_points = []

    for segment in segments:
        if segment is None or not segment.IsLinear(tolerance):
            raise ValueError("직사각형의 모든 변은 직선이어야 합니다.")
        line = rg.Line(segment.PointAtStart, segment.PointAtEnd)
        linear_segments.append(line)
        all_points.append(line.From)
        all_points.append(line.To)

    plane_ok, plane = get_curve_plane(curve)
    if not plane_ok:
        raise ValueError("선택한 직사각형은 하나의 평면 위에 있어야 합니다.")

    normal = rg.Vector3d(plane.Normal)
    horizontal_normal = rg.Vector3d(normal.X, normal.Y, 0.0)
    if not horizontal_normal.Unitize():
        raise ValueError("XY 평면에 수직으로 서 있는 직사각형을 선택해 주세요.")

    # A vertical opening plane has a nearly horizontal normal.
    if abs(normal * rg.Vector3d.ZAxis) > 0.05:
        raise ValueError("개구부 직사각형은 XY 평면에 수직으로 서 있어야 합니다.")

    bottom_line = min(
        linear_segments,
        key=lambda item: (item.From.Z + item.To.Z) * 0.5
    )

    if abs(bottom_line.From.Z - bottom_line.To.Z) > tolerance * 10.0:
        raise ValueError("개구부 직사각형의 최하단 선분은 수평이어야 합니다.")

    bottom_vector = bottom_line.Direction
    if not bottom_vector.Unitize():
        raise ValueError("개구부 하단 선분의 길이가 너무 짧습니다.")

    if abs(bottom_vector * rg.Vector3d.ZAxis) > 0.01:
        raise ValueError("개구부 직사각형의 하단 선분은 수평이어야 합니다.")

    min_z = min(point.Z for point in all_points)
    max_z = max(point.Z for point in all_points)
    opening_height = max_z - min_z
    opening_width = bottom_line.Length

    if opening_width <= tolerance or opening_height <= tolerance:
        raise ValueError("개구부 직사각형의 폭 또는 높이가 유효하지 않습니다.")

    stage_point = bottom_line.PointAt(0.5)

    return {
        "stage_point": stage_point,
        "default_direction": horizontal_normal,
        "opening_width": opening_width,
        "opening_height": opening_height,
    }


def calculate_actual_sightline_status(
    eye_x_values,
    eye_z_values,
    sight_target_z,
    required_clearance
):
    """Return actual vertical clearance and violations for each rear row."""
    row_count = len(eye_x_values)
    clearance_values = [None] * row_count
    violations = [False] * row_count

    for index in range(1, row_count):
        current_eye_x = eye_x_values[index]
        if current_eye_x <= 1e-12:
            clearance_values[index] = float("-inf")
            violations[index] = True
            continue

        line_z_at_previous_eye = (
            sight_target_z
            + (eye_x_values[index - 1] / current_eye_x)
            * (eye_z_values[index] - sight_target_z)
        )
        actual_clearance = (
            line_z_at_previous_eye - eye_z_values[index - 1]
        )
        clearance_values[index] = actual_clearance
        violations[index] = (
            actual_clearance < required_clearance - 1e-8
        )

    return clearance_values, violations


def validate_section_rise_target(z_values, target_rise, section_label):
    """Validate and normalize a requested non-negative total rise."""
    try:
        target = float(target_rise)
    except Exception:
        raise ValueError(
            "{0} 목표 상승 높이를 숫자로 입력해 주세요.".format(
                section_label
            )
        )

    if math.isnan(target) or math.isinf(target) or target < 0.0:
        raise ValueError(
            "{0} 목표 상승 높이는 0 이상의 유한한 값이어야 합니다.".format(
                section_label
            )
        )
    if len(z_values) < 2:
        raise ValueError(
            "{0}은 두 열 이상일 때만 보간할 수 있습니다.".format(
                section_label
            )
        )
    if not all(is_finite_number(value) for value in z_values):
        raise ValueError(
            "{0}의 기존 플랫폼 높이에 유효하지 않은 값이 있습니다.".format(
                section_label
            )
        )

    current_rise = z_values[-1] - z_values[0]
    if not is_finite_number(current_rise) or current_rise <= 1e-12:
        raise ValueError(
            "{0}의 현재 상승 높이가 0이어서 보간할 수 없습니다.".format(
                section_label
            )
        )

    return target, current_rise


def interpolate_front_anchored_z_values(
    z_values,
    target_rise,
    section_label
):
    """Scale tier heights while fixing the first platform."""
    target, current_rise = validate_section_rise_target(
        z_values,
        target_rise,
        section_label
    )
    first_z = z_values[0]
    interpolated = [
        first_z
        + target * ((z_value - first_z) / current_rise)
        for z_value in z_values
    ]
    interpolated[0] = first_z
    interpolated[-1] = first_z + target
    if (
        not all(is_finite_number(value) for value in interpolated)
        or abs(
            (interpolated[-1] - interpolated[0]) - target
        ) > max(1e-8, abs(target) * 1e-12)
    ):
        raise ValueError(
            "{0} 목표 상승 높이를 수치적으로 표현할 수 없습니다.".format(
                section_label
            )
        )
    return interpolated, current_rise


def interpolate_rear_anchored_z_values(
    z_values,
    target_rise,
    section_label
):
    """Scale tier heights while fixing the last platform."""
    target, current_rise = validate_section_rise_target(
        z_values,
        target_rise,
        section_label
    )
    last_z = z_values[-1]
    interpolated = [
        last_z
        - target * ((last_z - z_value) / current_rise)
        for z_value in z_values
    ]
    interpolated[0] = last_z - target
    interpolated[-1] = last_z
    if (
        not all(is_finite_number(value) for value in interpolated)
        or abs(
            (interpolated[-1] - interpolated[0]) - target
        ) > max(1e-8, abs(target) * 1e-12)
    ):
        raise ValueError(
            "{0} 목표 상승 높이를 수치적으로 표현할 수 없습니다.".format(
                section_label
            )
        )
    return interpolated, current_rise


def rebuild_stalls_vertical_fields(params, result, base_z_values):
    """Recompute stalls fields that depend on platform elevations."""
    rebuilt = dict(result)
    row_count = len(base_z_values)
    pitch = params["row_pitch"]
    sight_point_z = params["sight_point_z"]
    maximum_slope = 1.0 / params["max_slope_denominator"]

    new_base_z_values = list(base_z_values)
    eye_z_values = [
        z_value + sight_point_z for z_value in new_base_z_values
    ]
    riser_values = [0.0] * row_count
    slope_values = [0.0] * row_count
    slope_violations = [False] * row_count

    for index in range(1, row_count):
        riser = new_base_z_values[index] - new_base_z_values[index - 1]
        if riser < -1e-8:
            raise ValueError(
                "일반 객석 보간 결과에서 뒤쪽 단이 앞쪽보다 낮아졌습니다."
            )
        riser = max(0.0, riser)
        slope = riser / pitch
        riser_values[index] = riser
        slope_values[index] = slope
        slope_violations[index] = slope > maximum_slope + 1e-10

    actual_clearances, sightline_violations = (
        calculate_actual_sightline_status(
            result["eye_x_values"],
            eye_z_values,
            params["stage_sight_point_z"],
            params["sight_clearance"]
        )
    )
    combined_violations = [
        slope_violations[index] or sightline_violations[index]
        for index in range(row_count)
    ]

    stair_tread_counts = result["aisle_stair_tread_counts"]
    aisle_before_values = result["aisle_before_values"]
    stair_riser_heights = [0.0] * row_count
    for index in range(1, row_count):
        if aisle_before_values[index] and riser_values[index] > 1e-8:
            stair_riser_heights[index] = (
                riser_values[index] / (stair_tread_counts[index] + 1)
            )

    rebuilt["maximum_slope"] = maximum_slope
    rebuilt["base_z_values"] = new_base_z_values
    rebuilt["eye_z_values"] = eye_z_values
    rebuilt["riser_values"] = riser_values
    rebuilt["slope_values"] = slope_values
    rebuilt["slope_violations"] = slope_violations
    rebuilt["actual_sight_clearance_values"] = actual_clearances
    rebuilt["sightline_violations"] = sightline_violations
    rebuilt["violations"] = combined_violations
    rebuilt["aisle_stair_riser_heights"] = stair_riser_heights
    return rebuilt


def add_stalls_ceiling_validation(result, auditorium_ceiling_z):
    """Add per-row chair clearance checks against the auditorium ceiling."""
    if auditorium_ceiling_z is None:
        return result

    rebuilt = dict(result)
    highest_chair_z_values = [
        z_value + CHAIR_TOP_Z
        for z_value in result["base_z_values"]
    ]
    ceiling_clearance_values = [
        auditorium_ceiling_z - chair_z
        for chair_z in highest_chair_z_values
    ]
    ceiling_violations = [
        clearance < -1e-8
        for clearance in ceiling_clearance_values
    ]
    rebuilt["highest_chair_z"] = max(highest_chair_z_values)
    rebuilt["ceiling_clearance_values"] = ceiling_clearance_values
    rebuilt["ceiling_clearance"] = min(ceiling_clearance_values)
    rebuilt["ceiling_violations"] = ceiling_violations
    rebuilt["ceiling_violation"] = any(ceiling_violations)
    return rebuilt


def apply_stalls_rise_interpolation(
    params,
    result,
    target_rise,
    auditorium_ceiling_z=None
):
    """Apply a front-anchored total-rise override to the stalls result."""
    if target_rise is None:
        return add_stalls_ceiling_validation(
            result,
            auditorium_ceiling_z
        )

    base_z_values, original_rise = interpolate_front_anchored_z_values(
        result["base_z_values"],
        target_rise,
        "일반 객석"
    )
    rebuilt = rebuild_stalls_vertical_fields(
        params,
        result,
        base_z_values
    )
    rebuilt["rise_interpolation_applied"] = True
    rebuilt["rise_interpolation_original"] = original_rise
    rebuilt["rise_interpolation_target"] = float(target_rise)
    return add_stalls_ceiling_validation(
        rebuilt,
        auditorium_ceiling_z
    )


def stalls_solver_signature(params):
    """Return only inputs that change the stalls X/Z sightline solution."""
    return (
        float(params["stage_height"]),
        float(params["first_row_distance"]),
        float(params["row_pitch"]),
        float(params["stage_sight_point_z"]),
        float(params["sight_point_z"]),
        float(params["sight_clearance"]),
        tuple(int(value) for value in params["row_group_counts"]),
        float(params["aisle_width"]),
        float(params["aisle_stair_tread_depth"]),
        str(params["floor_type"]),
    )


def balcony_solver_signature(params, tier_index):
    """Return only inputs that change one balcony tier's seat elevations."""
    tier_params = normalized_balcony_tier_params(params, tier_index)
    return (
        bool(tier_params["balcony_enabled"]),
        int(tier_params["balcony_row_count"]),
        float(tier_params["balcony_row_pitch"]),
        float(tier_params["balcony_last_platform_z"]),
    )


def section_solver_signatures(params):
    return {
        "stalls": stalls_solver_signature(params),
        "balcony_1": balcony_solver_signature(params, 0),
        "balcony_2": balcony_solver_signature(params, 1),
    }


def balcony_result_is_displayable(result):
    """Keep an interpolated tier visible so its validation can be reviewed."""
    return (
        result is not None
        and (
            not result["lower_limit_violation"]
            or result.get("rise_interpolation_applied", False)
        )
    )


def calculate_section(params):
    """
    Calculate all row positions in millimeters relative to the stage point.

    Vertical coordinate 0 = stage reference point / opening bottom midpoint.
    Horizontal coordinate 0 = stage reference point.
    """
    stage_height = params["stage_height"]
    first_distance = params["first_row_distance"]
    pitch = params["row_pitch"]
    stage_sight_point_z = params["stage_sight_point_z"]
    sight_point_z = params["sight_point_z"]
    clearance = params["sight_clearance"]
    row_count = params["row_count"]
    row_group_counts = params.get("row_group_counts", [row_count])
    aisle_width = params.get("aisle_width", 0.0)
    aisle_stair_tread_depth = params.get(
        "aisle_stair_tread_depth",
        300.0
    )
    denominator = params["max_slope_denominator"]
    stepped = params["floor_type"] == "stepped"

    if sum(row_group_counts) != row_count:
        raise ValueError("좌석 그룹 열 수와 전체 열 수가 일치하지 않습니다.")

    aisle_before_indices = set()
    accumulated_rows = 0
    for group_count in row_group_counts[:-1]:
        accumulated_rows += group_count
        aisle_before_indices.add(accumulated_rows)

    maximum_slope = 1.0 / denominator
    sight_target_z = stage_sight_point_z

    row_x_values = []
    eye_x_values = []
    base_z_values = []
    eye_z_values = []
    riser_values = [0.0]
    slope_values = [0.0]
    violations = [False]
    aisle_before_values = [False] * row_count
    aisle_stair_tread_counts = [0] * row_count
    aisle_stair_riser_heights = [0.0] * row_count
    aisle_stair_run_values = [0.0] * row_count

    # First Row Distance locates the stage-side start of the first platform.
    # The chair's rear-bottom origin sits at that platform's rear edge.
    first_row_x = first_distance + pitch
    first_eye_x = first_row_x + CHAIR_SIGHT_POINT_X
    first_base_z = -stage_height
    first_eye_z = first_base_z + sight_point_z

    row_x_values.append(first_row_x)
    eye_x_values.append(first_eye_x)
    base_z_values.append(first_base_z)
    eye_z_values.append(first_eye_z)

    accumulated_aisle_width = 0.0
    accumulated_stair_run = 0.0
    for index in range(1, row_count):
        aisle_before = index in aisle_before_indices
        if aisle_before:
            accumulated_aisle_width += aisle_width
            aisle_before_values[index] = True

        previous_eye_x = eye_x_values[index - 1]
        base_current_row_x = (
            first_distance
            + pitch * (index + 1)
            + accumulated_aisle_width
            + accumulated_stair_run
        )
        previous_eye_z = eye_z_values[index - 1]

        stair_tread_count = 0
        for stair_iteration in range(50):
            candidate_stair_run = (
                stair_tread_count * aisle_stair_tread_depth
                if stepped and aisle_before
                else 0.0
            )
            current_row_x = base_current_row_x + candidate_stair_run
            current_eye_x = current_row_x + CHAIR_SIGHT_POINT_X

            # The new sightline from the raised stage target must pass the
            # previous eye position plus the specified vertical clearance.
            target_height_at_previous_row = previous_eye_z + clearance
            ideal_eye_z = (
                sight_target_z
                + (current_eye_x / previous_eye_x)
                * (target_height_at_previous_row - sight_target_z)
            )
            ideal_base_z = ideal_eye_z - sight_point_z

            # Auditorium floors must not descend toward the rear.
            ideal_base_z = max(
                ideal_base_z,
                base_z_values[index - 1]
            )
            raw_riser = ideal_base_z - base_z_values[index - 1]

            if stepped:
                applied_riser = ceil_to_integer_mm(raw_riser)
                current_base_z = (
                    base_z_values[index - 1] + applied_riser
                )
                current_eye_z = current_base_z + sight_point_z
            else:
                applied_riser = raw_riser
                current_base_z = ideal_base_z
                current_eye_z = current_base_z + sight_point_z

            if not (stepped and aisle_before):
                break

            if applied_riser <= 1e-8:
                updated_tread_count = 0
            else:
                # Positive-value half-up rounding avoids Python's
                # banker's-rounding behavior at .5.
                stair_riser_count = max(
                    1,
                    int(
                        math.floor(
                            applied_riser
                            / AISLE_STAIR_TARGET_RISER_HEIGHT
                            + 0.5
                        )
                    )
                )
                updated_tread_count = stair_riser_count - 1

            if updated_tread_count == stair_tread_count:
                break
            stair_tread_count = updated_tread_count
        else:
            raise ValueError(
                "통로 계단 수와 시야 계산이 안정된 값에 도달하지 못했습니다."
            )

        if stepped and aisle_before:
            stair_run = stair_tread_count * aisle_stair_tread_depth
            accumulated_stair_run += stair_run
            aisle_stair_tread_counts[index] = stair_tread_count
            aisle_stair_run_values[index] = stair_run
            if applied_riser > 1e-8:
                aisle_stair_riser_heights[index] = (
                    applied_riser / (stair_tread_count + 1)
                )

        slope = applied_riser / pitch
        violation = slope > maximum_slope + 1e-10

        row_x_values.append(current_row_x)
        eye_x_values.append(current_eye_x)
        base_z_values.append(current_base_z)
        eye_z_values.append(current_eye_z)
        riser_values.append(applied_riser)
        slope_values.append(slope)
        violations.append(violation)

    slope_violations = list(violations)
    actual_clearances, sightline_violations = (
        calculate_actual_sightline_status(
            eye_x_values,
            eye_z_values,
            sight_target_z,
            clearance
        )
    )
    combined_violations = [
        slope_violations[index] or sightline_violations[index]
        for index in range(row_count)
    ]

    return {
        "pitch": pitch,
        "maximum_slope": maximum_slope,
        "sight_target_z": sight_target_z,
        "x_values": row_x_values,
        "eye_x_values": eye_x_values,
        "base_z_values": base_z_values,
        "eye_z_values": eye_z_values,
        "riser_values": riser_values,
        "slope_values": slope_values,
        "slope_violations": slope_violations,
        "actual_sight_clearance_values": actual_clearances,
        "sightline_violations": sightline_violations,
        "violations": combined_violations,
        "aisle_before_values": aisle_before_values,
        "aisle_before_indices": sorted(aisle_before_indices),
        "aisle_stair_tread_counts": aisle_stair_tread_counts,
        "aisle_stair_riser_heights": aisle_stair_riser_heights,
        "aisle_stair_run_values": aisle_stair_run_values,
    }


def standard_balcony_railing_height(railing_t):
    """Return the supplied t-based balcony railing reference height."""
    return 800.0 if railing_t < 250.0 else 750.0


def balcony_height_from_stalls_rear(
    absolute_height,
    stalls_rear_z
):
    """Convert an internal stage-relative Z to the balcony UI datum."""
    return float(absolute_height) - float(stalls_rear_z)


def balcony_height_to_absolute(
    relative_height,
    stalls_rear_z
):
    """Convert a balcony UI height back to the internal stage datum."""
    return float(stalls_rear_z) + float(relative_height)


def normalized_balcony_tier_params(params, tier_index):
    """Map a stored balcony tier to the canonical calculation keys."""
    normalized = dict(params)
    key_map = BALCONY_TIER_KEY_MAPS[tier_index]
    for canonical_key, actual_key in key_map.items():
        normalized[canonical_key] = params[actual_key]
    return normalized


def calculate_balcony_spatial_max_rows(params, stalls_result):
    """Return the longest balcony that stays behind the stalls front limit."""
    rear_row_x = stalls_result["x_values"][-1]
    pitch = params["balcony_row_pitch"]
    railing_t = params["balcony_railing_t"]
    railing_w = params["balcony_railing_w"]

    # The embedded chair origin is at its rear. Keep the actual chair front
    # behind the railing cap and the requested clear distance w.
    minimum_first_row_origin_x = (
        params["first_row_distance"]
        + railing_t
        + railing_w
        - CHAIR_FRONT_X
    )
    available_run = rear_row_x - minimum_first_row_origin_x
    if available_run < 0.0:
        return 1
    return max(1, int(math.floor(available_run / pitch)) + 1)


def calculate_balcony_max_rows(
    params,
    stalls_result,
    opening_height_mm,
    tier_index=0
):
    """Return the longest balcony that also stays above its lower limit."""
    spatial_maximum = calculate_balcony_spatial_max_rows(
        params,
        stalls_result
    )
    for row_count in range(spatial_maximum, 0, -1):
        candidate_params = dict(params)
        candidate_params["balcony_enabled"] = True
        candidate_params["balcony_row_count"] = row_count
        candidate = calculate_balcony_section(
            candidate_params,
            stalls_result,
            opening_height_mm,
            include_maximum=False,
            tier_index=tier_index
        )
        if not candidate["lower_limit_violation"]:
            return row_count
    return 0


def calculate_balcony_section(
    params,
    stalls_result,
    opening_height_mm,
    include_maximum=True,
    tier_index=0
):
    """Calculate a rear-anchored balcony backward toward the stage."""
    if not params.get("balcony_enabled", False):
        return None

    row_count = params["balcony_row_count"]
    pitch = params["balcony_row_pitch"]
    last_platform_z = params["balcony_last_platform_z"]
    sight_target_z = params["stage_sight_point_z"]
    sight_point_z = params["sight_point_z"]
    clearance = params["sight_clearance"]
    railing_t = params["balcony_railing_t"]
    railing_w = params["balcony_railing_w"]
    railing_h = params["balcony_railing_h"]

    rear_row_x = stalls_result["x_values"][-1]
    row_x_values = [
        rear_row_x - pitch * (row_count - 1 - index)
        for index in range(row_count)
    ]
    eye_x_values = [
        row_x + CHAIR_SIGHT_POINT_X
        for row_x in row_x_values
    ]
    if eye_x_values[0] <= 0.0:
        raise ValueError(
            "발코니 첫 열 시각점은 무대 기준점보다 객석 방향에 "
            "있어야 합니다."
        )

    base_z_values = [0.0] * row_count
    eye_z_values = [0.0] * row_count
    riser_to_next_values = [0.0] * row_count
    slope_to_next_values = [0.0] * row_count

    base_z_values[-1] = last_platform_z
    eye_z_values[-1] = last_platform_z + sight_point_z

    for index in range(row_count - 2, -1, -1):
        current_index = index + 1
        ideal_previous_eye_z = (
            sight_target_z
            + (
                eye_x_values[index]
                / eye_x_values[current_index]
            )
            * (
                eye_z_values[current_index]
                - sight_target_z
            )
            - clearance
        )
        ideal_previous_base_z = (
            ideal_previous_eye_z - sight_point_z
        )
        ideal_previous_base_z = min(
            ideal_previous_base_z,
            base_z_values[current_index]
        )
        raw_riser = (
            base_z_values[current_index]
            - ideal_previous_base_z
        )
        applied_riser = ceil_to_integer_mm(raw_riser)
        base_z_values[index] = (
            base_z_values[current_index] - applied_riser
        )
        eye_z_values[index] = (
            base_z_values[index] + sight_point_z
        )
        riser_to_next_values[index] = applied_riser
        slope_to_next_values[index] = applied_riser / pitch

    maximum_slope = max(slope_to_next_values)
    maximum_angle_degrees = math.degrees(math.atan(maximum_slope))
    first_chair_front_x = row_x_values[0] + CHAIR_FRONT_X
    railing_front_x = (
        first_chair_front_x - railing_w - railing_t
    )
    railing_rear_x = railing_front_x + railing_t
    railing_floor_z = base_z_values[0]
    railing_top_z = railing_floor_z + railing_h

    line_z_at_railing = (
        sight_target_z
        + (railing_front_x / eye_x_values[0])
        * (eye_z_values[0] - sight_target_z)
    )
    allowable_railing_h = line_z_at_railing - railing_floor_z
    railing_sight_collision = (
        railing_front_x <= 0.0
        or railing_h > allowable_railing_h + 1e-8
    )
    front_limit_violation = (
        railing_front_x < params["first_row_distance"] - 1e-8
    )

    lower_stalls_eye_x = stalls_result["eye_x_values"][-1]
    lower_stalls_eye_z = stalls_result["eye_z_values"][-1]

    def lower_limit_z_at(x_value):
        return (
            opening_height_mm
            + (x_value / lower_stalls_eye_x)
            * (lower_stalls_eye_z - opening_height_mm)
        )

    lower_limit_checks = [
        (
            railing_front_x,
            railing_floor_z,
            railing_floor_z - lower_limit_z_at(railing_front_x),
        )
    ]
    for row_x, base_z in zip(row_x_values, base_z_values):
        lower_limit_checks.append(
            (
                row_x,
                base_z,
                base_z - lower_limit_z_at(row_x),
            )
        )
    minimum_lower_limit_clearance = min(
        check[2] for check in lower_limit_checks
    )
    lower_limit_violation = (
        minimum_lower_limit_clearance < -1e-8
    )
    highest_chair_z = max(base_z_values) + CHAIR_TOP_Z
    auditorium_ceiling_z = opening_height_mm * 2.0
    ceiling_clearance = auditorium_ceiling_z - highest_chair_z
    ceiling_violation = ceiling_clearance < -1e-8
    maximum_rows = (
        calculate_balcony_max_rows(
            params,
            stalls_result,
            opening_height_mm,
            tier_index=tier_index
        )
        if include_maximum
        else None
    )
    actual_clearances, sightline_violations = (
        calculate_actual_sightline_status(
            eye_x_values,
            eye_z_values,
            sight_target_z,
            clearance
        )
    )
    clearance_to_next_values = actual_clearances[1:] + [None]
    valid_clearances = [
        value for value in actual_clearances if value is not None
    ]

    return {
        "tier_index": tier_index,
        "row_count": row_count,
        "maximum_rows": maximum_rows,
        "x_values": row_x_values,
        "eye_x_values": eye_x_values,
        "base_z_values": base_z_values,
        "eye_z_values": eye_z_values,
        "riser_to_next_values": riser_to_next_values,
        "slope_to_next_values": slope_to_next_values,
        "sightline_clearance_to_next_values": (
            clearance_to_next_values
        ),
        "sightline_violations": sightline_violations,
        "minimum_sightline_clearance": (
            min(valid_clearances) if valid_clearances else None
        ),
        "sightline_violation": any(sightline_violations),
        "maximum_angle_degrees": maximum_angle_degrees,
        "angle_violation": maximum_angle_degrees > 35.0 + 1e-8,
        "first_chair_front_x": first_chair_front_x,
        "railing_front_x": railing_front_x,
        "railing_rear_x": railing_rear_x,
        "railing_floor_z": railing_floor_z,
        "railing_top_z": railing_top_z,
        "standard_railing_h": standard_balcony_railing_height(
            railing_t
        ),
        "allowable_railing_h": allowable_railing_h,
        "railing_sight_collision": railing_sight_collision,
        "front_limit_violation": front_limit_violation,
        "lower_limit_start_x": 0.0,
        "lower_limit_start_z": opening_height_mm,
        "lower_limit_end_x": lower_stalls_eye_x,
        "lower_limit_end_z": lower_stalls_eye_z,
        "minimum_lower_limit_clearance": (
            minimum_lower_limit_clearance
        ),
        "lower_limit_violation": lower_limit_violation,
        "highest_chair_z": highest_chair_z,
        "ceiling_clearance": ceiling_clearance,
        "ceiling_violation": ceiling_violation,
    }


def rebuild_balcony_vertical_fields(
    params,
    result,
    lower_result,
    opening_height_mm,
    base_z_values
):
    """Recompute balcony validation fields after a rear-anchored edit."""
    rebuilt = dict(result)
    row_count = len(base_z_values)
    pitch = params["balcony_row_pitch"]
    sight_target_z = params["stage_sight_point_z"]
    sight_point_z = params["sight_point_z"]
    clearance = params["sight_clearance"]
    railing_t = params["balcony_railing_t"]
    railing_w = params["balcony_railing_w"]
    railing_h = params["balcony_railing_h"]
    row_x_values = result["x_values"]
    eye_x_values = result["eye_x_values"]
    new_base_z_values = list(base_z_values)
    eye_z_values = [
        z_value + sight_point_z for z_value in new_base_z_values
    ]
    riser_to_next_values = [0.0] * row_count
    slope_to_next_values = [0.0] * row_count

    for index in range(row_count - 1):
        riser = new_base_z_values[index + 1] - new_base_z_values[index]
        if riser < -1e-8:
            raise ValueError(
                "발코니 보간 결과에서 뒤쪽 단이 앞쪽보다 낮아졌습니다."
            )
        riser = max(0.0, riser)
        run = row_x_values[index + 1] - row_x_values[index]
        if run <= 1e-12:
            raise ValueError("발코니 열 간격이 유효하지 않습니다.")
        riser_to_next_values[index] = riser
        slope_to_next_values[index] = riser / run

    maximum_slope = max(slope_to_next_values)
    maximum_angle_degrees = math.degrees(math.atan(maximum_slope))
    first_chair_front_x = row_x_values[0] + CHAIR_FRONT_X
    railing_front_x = first_chair_front_x - railing_w - railing_t
    railing_rear_x = railing_front_x + railing_t
    railing_floor_z = new_base_z_values[0]
    railing_top_z = railing_floor_z + railing_h
    line_z_at_railing = (
        sight_target_z
        + (railing_front_x / eye_x_values[0])
        * (eye_z_values[0] - sight_target_z)
    )
    allowable_railing_h = line_z_at_railing - railing_floor_z
    railing_sight_collision = (
        railing_front_x <= 0.0
        or railing_h > allowable_railing_h + 1e-8
    )
    front_limit_violation = (
        railing_front_x < params["first_row_distance"] - 1e-8
    )

    lower_eye_x = lower_result["eye_x_values"][-1]
    lower_eye_z = lower_result["eye_z_values"][-1]

    def lower_limit_z_at(x_value):
        return (
            opening_height_mm
            + (x_value / lower_eye_x)
            * (lower_eye_z - opening_height_mm)
        )

    lower_limit_checks = [
        (
            railing_front_x,
            railing_floor_z,
            railing_floor_z - lower_limit_z_at(railing_front_x),
        )
    ]
    for row_x, base_z in zip(row_x_values, new_base_z_values):
        lower_limit_checks.append(
            (row_x, base_z, base_z - lower_limit_z_at(row_x))
        )
    minimum_lower_limit_clearance = min(
        check[2] for check in lower_limit_checks
    )
    lower_limit_violation = minimum_lower_limit_clearance < -1e-8
    highest_chair_z = max(new_base_z_values) + CHAIR_TOP_Z
    auditorium_ceiling_z = opening_height_mm * 2.0
    ceiling_clearance = auditorium_ceiling_z - highest_chair_z
    ceiling_violation = ceiling_clearance < -1e-8

    actual_clearances, sightline_violations = (
        calculate_actual_sightline_status(
            eye_x_values,
            eye_z_values,
            sight_target_z,
            clearance
        )
    )
    valid_clearances = [
        value for value in actual_clearances if value is not None
    ]

    rebuilt["base_z_values"] = new_base_z_values
    rebuilt["eye_z_values"] = eye_z_values
    rebuilt["riser_to_next_values"] = riser_to_next_values
    rebuilt["slope_to_next_values"] = slope_to_next_values
    rebuilt["sightline_clearance_to_next_values"] = (
        actual_clearances[1:] + [None]
    )
    rebuilt["sightline_violations"] = sightline_violations
    rebuilt["minimum_sightline_clearance"] = (
        min(valid_clearances) if valid_clearances else None
    )
    rebuilt["sightline_violation"] = any(sightline_violations)
    rebuilt["maximum_angle_degrees"] = maximum_angle_degrees
    rebuilt["angle_violation"] = maximum_angle_degrees > 35.0 + 1e-8
    rebuilt["first_chair_front_x"] = first_chair_front_x
    rebuilt["railing_front_x"] = railing_front_x
    rebuilt["railing_rear_x"] = railing_rear_x
    rebuilt["railing_floor_z"] = railing_floor_z
    rebuilt["railing_top_z"] = railing_top_z
    rebuilt["standard_railing_h"] = standard_balcony_railing_height(
        railing_t
    )
    rebuilt["allowable_railing_h"] = allowable_railing_h
    rebuilt["railing_sight_collision"] = railing_sight_collision
    rebuilt["front_limit_violation"] = front_limit_violation
    rebuilt["lower_limit_start_x"] = 0.0
    rebuilt["lower_limit_start_z"] = opening_height_mm
    rebuilt["lower_limit_end_x"] = lower_eye_x
    rebuilt["lower_limit_end_z"] = lower_eye_z
    rebuilt["minimum_lower_limit_clearance"] = (
        minimum_lower_limit_clearance
    )
    rebuilt["lower_limit_violation"] = lower_limit_violation
    rebuilt["highest_chair_z"] = highest_chair_z
    rebuilt["ceiling_clearance"] = ceiling_clearance
    rebuilt["ceiling_violation"] = ceiling_violation
    return rebuilt


def apply_balcony_rise_interpolation(
    params,
    result,
    lower_result,
    opening_height_mm,
    target_rise
):
    """Apply a rear-anchored total-rise override to one balcony tier."""
    if result is None or target_rise is None:
        return result

    tier_label = "발코니 {0}".format(result["tier_index"] + 1)
    base_z_values, original_rise = interpolate_rear_anchored_z_values(
        result["base_z_values"],
        target_rise,
        tier_label
    )
    rebuilt = rebuild_balcony_vertical_fields(
        params,
        result,
        lower_result,
        opening_height_mm,
        base_z_values
    )
    rebuilt["rise_interpolation_applied"] = True
    rebuilt["rise_interpolation_original"] = original_rise
    rebuilt["rise_interpolation_target"] = float(target_rise)
    return rebuilt


def append_balcony_tier_geometry(
    balcony_result,
    stage_point,
    direction,
    mm_scale,
    params,
    stage_sight_point,
    stage_upper_sight_point,
    preview_curves,
    preview_points,
    bake_curves,
    bake_points
):
    """Append one calculated balcony tier to preview and bake collections."""
    tier_number = balcony_result["tier_index"] + 1
    name_prefix = "Balcony{0:02d}".format(tier_number)
    tier_color = (
        PREVIEW_BALCONY
        if tier_number == 1
        else PREVIEW_BALCONY_SECOND
    )

    if not balcony_result_is_displayable(balcony_result):
        return

    x_values = balcony_result["x_values"]
    base_z_values = balcony_result["base_z_values"]
    eye_x_values = balcony_result["eye_x_values"]
    eye_z_values = balcony_result["eye_z_values"]
    row_count = balcony_result["row_count"]
    sightline_violations = balcony_result.get(
        "sightline_violations",
        [False] * row_count
    )
    floor_color = PREVIEW_WARNING

    for index in range(row_count):
        row_warning = sightline_violations[index]
        chair_color = PREVIEW_WARNING if row_warning else PREVIEW_SEAT
        eye_point = point_at(
            stage_point,
            direction,
            eye_x_values[index],
            eye_z_values[index],
            mm_scale
        )
        if params["show_seats"]:
            for chair_curve in build_chair_curves(
                stage_point,
                direction,
                x_values[index],
                base_z_values[index],
                mm_scale
            ):
                preview_curves.append((chair_curve, chair_color, 2))
                bake_curves.append(
                    (
                        chair_curve,
                        chair_color,
                        name_prefix + "Chair",
                    )
                )
        if params["show_eye_points"]:
            point_color = PREVIEW_WARNING if row_warning else tier_color
            preview_points.append((eye_point, point_color, 5))
            bake_points.append(
                (eye_point, point_color, name_prefix + "SightPoint")
            )
        if params["show_sightlines"]:
            is_end_row = index == 0 or index == row_count - 1
            sight_color = (
                PREVIEW_WARNING
                if row_warning
                else (
                    PREVIEW_FULL_STAGE_SIGHT
                    if is_end_row
                    else tier_color
                )
            )
            lower_line = line_curve(stage_sight_point, eye_point)
            preview_curves.append(
                (lower_line, sight_color, 2 if is_end_row else 1)
            )
            bake_curves.append(
                (
                    lower_line,
                    sight_color,
                    (
                        name_prefix + "FullStageSightlineLower"
                        if is_end_row
                        else name_prefix + "Sightline"
                    ),
                )
            )
            if is_end_row:
                upper_line = line_curve(
                    stage_upper_sight_point,
                    eye_point
                )
                preview_curves.append(
                    (upper_line, PREVIEW_FULL_STAGE_SIGHT, 2)
                )
                bake_curves.append(
                    (
                        upper_line,
                        PREVIEW_FULL_STAGE_SIGHT,
                        name_prefix + "FullStageSightlineUpper",
                    )
                )

    rail_floor = point_at(
        stage_point,
        direction,
        balcony_result["railing_front_x"],
        balcony_result["railing_floor_z"],
        mm_scale
    )
    rail_front_top = point_at(
        stage_point,
        direction,
        balcony_result["railing_front_x"],
        balcony_result["railing_top_z"],
        mm_scale
    )
    rail_rear_top = point_at(
        stage_point,
        direction,
        balcony_result["railing_rear_x"],
        balcony_result["railing_top_z"],
        mm_scale
    )
    rail_color = (
        PREVIEW_WARNING
        if balcony_result["railing_sight_collision"]
        else PREVIEW_BALCONY_RAIL
    )
    for curve, suffix in (
        (line_curve(rail_floor, rail_front_top), "RailingFront"),
        (line_curve(rail_front_top, rail_rear_top), "RailingTop"),
    ):
        preview_curves.append((curve, rail_color, 4))
        bake_curves.append(
            (curve, rail_color, name_prefix + suffix)
        )

    first_platform_end = point_at(
        stage_point,
        direction,
        x_values[0],
        base_z_values[0],
        mm_scale
    )
    first_platform = line_curve(rail_floor, first_platform_end)
    preview_curves.append((first_platform, floor_color, 4))
    bake_curves.append(
        (first_platform, floor_color, name_prefix + "Floor")
    )

    for index in range(1, row_count):
        riser_x = x_values[index - 1]
        riser_start = point_at(
            stage_point,
            direction,
            riser_x,
            base_z_values[index - 1],
            mm_scale
        )
        riser_end = point_at(
            stage_point,
            direction,
            riser_x,
            base_z_values[index],
            mm_scale
        )
        platform_end = point_at(
            stage_point,
            direction,
            x_values[index],
            base_z_values[index],
            mm_scale
        )
        riser_curve = line_curve(riser_start, riser_end)
        platform_curve = line_curve(riser_end, platform_end)
        preview_curves.append((riser_curve, floor_color, 4))
        preview_curves.append((platform_curve, floor_color, 4))
        bake_curves.append(
            (riser_curve, floor_color, name_prefix + "Floor")
        )
        bake_curves.append(
            (platform_curve, floor_color, name_prefix + "Floor")
        )

    rear_aisle_width = params["aisle_width"]
    if rear_aisle_width > 1e-8:
        rear_aisle_start = point_at(
            stage_point,
            direction,
            x_values[-1],
            base_z_values[-1],
            mm_scale
        )
        rear_aisle_end = point_at(
            stage_point,
            direction,
            x_values[-1] + rear_aisle_width,
            base_z_values[-1],
            mm_scale
        )
        rear_aisle_curve = line_curve(
            rear_aisle_start,
            rear_aisle_end
        )
        preview_curves.append(
            (rear_aisle_curve, PREVIEW_AISLE, 4)
        )
        bake_curves.append(
            (
                rear_aisle_curve,
                PREVIEW_AISLE,
                name_prefix + "RearAisle",
            )
        )


def build_preview_geometry(
    stage_data,
    params,
    doc,
    seat_source=None,
    section_rise_overrides=None
):
    """Build preview and bake geometry without adding it to the document."""
    rise_overrides = {
        key: None for key in SECTION_RISE_KEYS
    }
    if section_rise_overrides:
        rise_overrides.update(section_rise_overrides)

    mm_scale = unit_scale_from_mm(doc)
    stage_point = stage_data["stage_point"]

    direction = rg.Vector3d(stage_data["default_direction"])
    if params["flipped"]:
        direction.Reverse()

    opening_width_mm = stage_data["opening_width"] / mm_scale
    opening_height_mm = stage_data["opening_height"] / mm_scale
    stage_sight_point = point_at(
        stage_point,
        direction,
        0.0,
        params["stage_sight_point_z"],
        mm_scale
    )
    stage_upper_sight_point = point_at(
        stage_point,
        direction,
        0.0,
        opening_height_mm,
        mm_scale
    )

    result = calculate_section(params)
    result = apply_stalls_rise_interpolation(
        params,
        result,
        rise_overrides["stalls"],
        opening_height_mm * 2.0
    )
    balcony_tier1_params = normalized_balcony_tier_params(params, 0)
    balcony_result = calculate_balcony_section(
        balcony_tier1_params,
        result,
        opening_height_mm
    )
    balcony_result = apply_balcony_rise_interpolation(
        balcony_tier1_params,
        balcony_result,
        result,
        opening_height_mm,
        rise_overrides["balcony_1"]
    )
    balcony2_result = None
    balcony2_dependency_warning = False
    balcony_tier2_params = normalized_balcony_tier_params(params, 1)
    if balcony_tier2_params["balcony_enabled"]:
        if (
            not balcony_result_is_displayable(balcony_result)
        ):
            balcony2_dependency_warning = True
        else:
            balcony_tier2_params["first_row_distance"] = (
                balcony_result["railing_front_x"]
            )
            balcony2_result = calculate_balcony_section(
                balcony_tier2_params,
                balcony_result,
                opening_height_mm,
                tier_index=1
            )
            balcony2_result = apply_balcony_rise_interpolation(
                balcony_tier2_params,
                balcony2_result,
                balcony_result,
                opening_height_mm,
                rise_overrides["balcony_2"]
            )
    balcony_results = [balcony_result, balcony2_result]

    x_values = result["x_values"]
    eye_x_values = result["eye_x_values"]
    base_z_values = result["base_z_values"]
    eye_z_values = result["eye_z_values"]
    ceiling_violations = result.get(
        "ceiling_violations",
        [False] * len(result["violations"])
    )
    violations = [
        result["violations"][index] or ceiling_violations[index]
        for index in range(len(result["violations"]))
    ]
    slope_values = result["slope_values"]
    aisle_before_values = result["aisle_before_values"]
    aisle_stair_tread_counts = result["aisle_stair_tread_counts"]
    aisle_stair_riser_heights = result[
        "aisle_stair_riser_heights"
    ]
    aisle_stair_run_values = result["aisle_stair_run_values"]

    row_pitch = params["row_pitch"]
    rear_aisle_width = params["aisle_width"]
    aisle_stair_tread_depth = params["aisle_stair_tread_depth"]
    row_count = params["row_count"]
    stepped = params["floor_type"] == "stepped"
    rear_wall_x = x_values[-1] + rear_aisle_width

    preview_curves = []
    preview_points = []
    preview_meshes = []
    preview_labels = []
    bake_curves = []
    bake_points = []
    bake_breps = []
    bake_instances = []
    seat_3d_result = None
    seat_3d_results = []
    floor_surface_result = None

    if params.get("show_riser_height_labels", False):
        preview_labels = build_riser_height_preview_labels(
            stage_point,
            direction,
            params,
            result,
            balcony_results,
            mm_scale
        )

    if params.get("show_3d_seats", False):
        if seat_source is None:
            raise ValueError(
                "3D seat modules are enabled, but AuditoriumSeat.3dm "
                "was not loaded."
            )
        seating_tiers = [("Stalls", result)]
        for tier_index, tier_result in enumerate(
            balcony_results
        ):
            if not balcony_result_is_displayable(tier_result):
                continue
            seating_tiers.append(
                (
                    "Balcony{0:02d}".format(tier_index + 1),
                    tier_result,
                )
            )

        for placement_name, tier_result in seating_tiers:
            tier_3d_result = build_3d_seat_module_geometry(
                seat_source,
                params,
                tier_result,
                stage_point,
                direction,
                mm_scale,
                placement_name
            )
            seat_3d_results.append(tier_3d_result)
            preview_meshes.extend(
                tier_3d_result["preview_meshes"]
            )
            bake_instances.extend(
                tier_3d_result["bake_instances"]
            )
        seat_3d_result = seat_3d_results[0]

    section_dimensions = calculate_stage_section_dimensions(
        params,
        opening_height_mm
    )
    if params.get("show_riser_height_labels", False):
        dimension_curves, dimension_labels = (
            build_section_height_dimension_preview(
                stage_point,
                direction,
                params,
                result,
                balcony_results,
                section_dimensions["auditorium_ceiling_z"],
                rear_wall_x,
                mm_scale
            )
        )
        preview_curves.extend(dimension_curves)
        preview_labels.extend(dimension_labels)

    if params["stage_preview_mode"] == "space_3d":
        stage_plan_curves = build_proscenium_plan_curves(
            stage_point,
            direction,
            params,
            mm_scale
        )
        for stage_curve, stage_color, stage_name in stage_plan_curves:
            preview_curves.append((stage_curve, stage_color, 3))
            bake_curves.append((stage_curve, stage_color, stage_name))

        stage_section_curves = build_stage_space_3d_curves(
            stage_point,
            direction,
            params,
            section_dimensions,
            mm_scale
        )
    else:
        stage_section_curves = build_stage_section_2d_curves(
            stage_point,
            direction,
            params,
            section_dimensions,
            mm_scale
        )

    for section_curve, section_color, section_name in stage_section_curves:
        preview_curves.append((section_curve, section_color, 2))
        bake_curves.append(
            (section_curve, section_color, section_name)
        )

    transition_curves = build_stage_audience_transition_curves(
        stage_point,
        direction,
        params,
        mm_scale
    )
    for transition_curve, transition_color, transition_name in (
        transition_curves
    ):
        preview_curves.append(
            (transition_curve, transition_color, 3)
        )
        bake_curves.append(
            (transition_curve, transition_color, transition_name)
        )

    # Auditorium ceiling line in the central longitudinal section.
    auditorium_ceiling_z = section_dimensions["auditorium_ceiling_z"]
    ceiling_start = point_at(
        stage_point,
        direction,
        0.0,
        auditorium_ceiling_z,
        mm_scale
    )
    ceiling_end = point_at(
        stage_point,
        direction,
        rear_wall_x,
        auditorium_ceiling_z,
        mm_scale
    )
    ceiling_curve = line_curve(ceiling_start, ceiling_end)
    preview_curves.append(
        (ceiling_curve, PREVIEW_AUDITORIUM_CEILING, 2)
    )
    bake_curves.append(
        (
            ceiling_curve,
            PREVIEW_AUDITORIUM_CEILING,
            "AuditoriumCeilingSection",
        )
    )

    # Lower editable target and upper opening-center target.
    preview_points.append((stage_sight_point, PREVIEW_REFERENCE, 6))
    bake_points.append(
        (stage_sight_point, PREVIEW_REFERENCE, "SightlineReference")
    )
    preview_points.append(
        (stage_upper_sight_point, PREVIEW_FULL_STAGE_SIGHT, 6)
    )
    bake_points.append(
        (
            stage_upper_sight_point,
            PREVIEW_FULL_STAGE_SIGHT,
            "UpperSightlineReference",
        )
    )

    # Embedded chairs, eye points and sightlines
    for index in range(row_count):
        row_color = (
            PREVIEW_WARNING if violations[index] else PREVIEW_SEAT
        )
        eye_point = point_at(
            stage_point,
            direction,
            eye_x_values[index],
            eye_z_values[index],
            mm_scale
        )

        if params["show_seats"]:
            chair_curves = build_chair_curves(
                stage_point,
                direction,
                x_values[index],
                base_z_values[index],
                mm_scale
            )
            for chair_curve in chair_curves:
                preview_curves.append((chair_curve, row_color, 2))
                bake_curves.append(
                    (chair_curve, row_color, "Chair")
                )

        if params["show_eye_points"]:
            point_color = PREVIEW_WARNING if violations[index] else PREVIEW_POINT
            preview_points.append((eye_point, point_color, 5))
            bake_points.append((eye_point, point_color, "SightPoint"))

        if params["show_sightlines"]:
            is_end_row = index == 0 or index == row_count - 1
            sight_color = (
                PREVIEW_FULL_STAGE_SIGHT
                if is_end_row
                else (
                    PREVIEW_WARNING
                    if violations[index]
                    else PREVIEW_SIGHT
                )
            )
            sightline = line_curve(stage_sight_point, eye_point)
            preview_curves.append(
                (sightline, sight_color, 2 if is_end_row else 1)
            )
            bake_curves.append(
                (
                    sightline,
                    sight_color,
                    (
                        "FullStageSightlineLower"
                        if is_end_row
                        else "Sightline"
                    ),
                )
            )

            if is_end_row:
                upper_sightline = line_curve(
                    stage_upper_sight_point,
                    eye_point
                )
                preview_curves.append(
                    (
                        upper_sightline,
                        PREVIEW_FULL_STAGE_SIGHT,
                        2,
                    )
                )
                bake_curves.append(
                    (
                        upper_sightline,
                        PREVIEW_FULL_STAGE_SIGHT,
                        "FullStageSightlineUpper",
                    )
                )

    if (
        balcony_result_is_displayable(balcony_result)
    ):
        balcony_x_values = balcony_result["x_values"]
        balcony_base_z_values = balcony_result["base_z_values"]
        balcony_eye_x_values = balcony_result["eye_x_values"]
        balcony_eye_z_values = balcony_result["eye_z_values"]
        balcony_row_count = balcony_result["row_count"]
        balcony_sightline_violations = balcony_result.get(
            "sightline_violations",
            [False] * balcony_row_count
        )
        balcony_color = PREVIEW_BALCONY
        balcony_floor_color = PREVIEW_WARNING

        for index in range(balcony_row_count):
            row_warning = balcony_sightline_violations[index]
            chair_color = (
                PREVIEW_WARNING if row_warning else PREVIEW_SEAT
            )
            eye_point = point_at(
                stage_point,
                direction,
                balcony_eye_x_values[index],
                balcony_eye_z_values[index],
                mm_scale
            )

            if params["show_seats"]:
                chair_curves = build_chair_curves(
                    stage_point,
                    direction,
                    balcony_x_values[index],
                    balcony_base_z_values[index],
                    mm_scale
                )
                for chair_curve in chair_curves:
                    preview_curves.append(
                        (chair_curve, chair_color, 2)
                    )
                    bake_curves.append(
                        (
                            chair_curve,
                            chair_color,
                            "Balcony01Chair",
                        )
                    )

            if params["show_eye_points"]:
                point_color = (
                    PREVIEW_WARNING if row_warning else balcony_color
                )
                preview_points.append(
                    (eye_point, point_color, 5)
                )
                bake_points.append(
                    (eye_point, point_color, "Balcony01SightPoint")
                )

            if params["show_sightlines"]:
                is_end_row = (
                    index == 0
                    or index == balcony_row_count - 1
                )
                sight_color = (
                    PREVIEW_WARNING
                    if row_warning
                    else (
                        PREVIEW_FULL_STAGE_SIGHT
                        if is_end_row
                        else balcony_color
                    )
                )
                lower_sightline = line_curve(
                    stage_sight_point,
                    eye_point
                )
                preview_curves.append(
                    (
                        lower_sightline,
                        sight_color,
                        2 if is_end_row else 1,
                    )
                )
                bake_curves.append(
                    (
                        lower_sightline,
                        sight_color,
                        (
                            "Balcony01FullStageSightlineLower"
                            if is_end_row
                            else "Balcony01Sightline"
                        ),
                    )
                )

                if is_end_row:
                    upper_sightline = line_curve(
                        stage_upper_sight_point,
                        eye_point
                    )
                    preview_curves.append(
                        (
                            upper_sightline,
                            PREVIEW_FULL_STAGE_SIGHT,
                            2,
                        )
                    )
                    bake_curves.append(
                        (
                            upper_sightline,
                            PREVIEW_FULL_STAGE_SIGHT,
                            "Balcony01FullStageSightlineUpper",
                        )
                    )

        railing_front_floor = point_at(
            stage_point,
            direction,
            balcony_result["railing_front_x"],
            balcony_result["railing_floor_z"],
            mm_scale
        )
        railing_front_top = point_at(
            stage_point,
            direction,
            balcony_result["railing_front_x"],
            balcony_result["railing_top_z"],
            mm_scale
        )
        railing_rear_top = point_at(
            stage_point,
            direction,
            balcony_result["railing_rear_x"],
            balcony_result["railing_top_z"],
            mm_scale
        )
        railing_color = (
            PREVIEW_WARNING
            if balcony_result["railing_sight_collision"]
            else PREVIEW_BALCONY_RAIL
        )
        for railing_curve, railing_name in (
            (
                line_curve(railing_front_floor, railing_front_top),
                "Balcony01RailingFront",
            ),
            (
                line_curve(railing_front_top, railing_rear_top),
                "Balcony01RailingTop",
            ),
        ):
            preview_curves.append(
                (railing_curve, railing_color, 4)
            )
            bake_curves.append(
                (railing_curve, railing_color, railing_name)
            )

        first_platform_end = point_at(
            stage_point,
            direction,
            balcony_x_values[0],
            balcony_base_z_values[0],
            mm_scale
        )
        first_platform = line_curve(
            railing_front_floor,
            first_platform_end
        )
        preview_curves.append(
            (first_platform, balcony_floor_color, 4)
        )
        bake_curves.append(
            (
                first_platform,
                balcony_floor_color,
                "Balcony01Floor",
            )
        )

        for index in range(1, balcony_row_count):
            riser_x = balcony_x_values[index - 1]
            riser_start = point_at(
                stage_point,
                direction,
                riser_x,
                balcony_base_z_values[index - 1],
                mm_scale
            )
            riser_end = point_at(
                stage_point,
                direction,
                riser_x,
                balcony_base_z_values[index],
                mm_scale
            )
            platform_end = point_at(
                stage_point,
                direction,
                balcony_x_values[index],
                balcony_base_z_values[index],
                mm_scale
            )
            riser_curve = line_curve(riser_start, riser_end)
            platform_curve = line_curve(riser_end, platform_end)
            preview_curves.append(
                (riser_curve, balcony_floor_color, 4)
            )
            preview_curves.append(
                (platform_curve, balcony_floor_color, 4)
            )
            bake_curves.append(
                (
                    riser_curve,
                    balcony_floor_color,
                    "Balcony01Floor",
                )
            )
            bake_curves.append(
                (
                    platform_curve,
                    balcony_floor_color,
                    "Balcony01Floor",
                )
            )

        rear_aisle_width = params["aisle_width"]
        if rear_aisle_width > 1e-8:
            rear_aisle_start = point_at(
                stage_point,
                direction,
                balcony_x_values[-1],
                balcony_base_z_values[-1],
                mm_scale
            )
            rear_aisle_end = point_at(
                stage_point,
                direction,
                balcony_x_values[-1] + rear_aisle_width,
                balcony_base_z_values[-1],
                mm_scale
            )
            rear_aisle_curve = line_curve(
                rear_aisle_start,
                rear_aisle_end
            )
            preview_curves.append(
                (rear_aisle_curve, PREVIEW_AISLE, 4)
            )
            bake_curves.append(
                (
                    rear_aisle_curve,
                    PREVIEW_AISLE,
                    "Balcony01RearAisle",
                )
            )

    if balcony2_result is not None:
        append_balcony_tier_geometry(
            balcony2_result,
            stage_point,
            direction,
            mm_scale,
            balcony_tier2_params,
            stage_sight_point,
            stage_upper_sight_point,
            preview_curves,
            preview_points,
            bake_curves,
            bake_points
        )

    # Floor geometry
    if stepped:
        for index in range(row_count):
            # Each chair's rear-bottom origin sits on the rear edge of its
            # platform. The preceding row pitch extends toward the stage.
            start_x = x_values[index] - row_pitch
            end_x = x_values[index]

            p0 = point_at(
                stage_point, direction, start_x, base_z_values[index], mm_scale
            )
            p1 = point_at(
                stage_point, direction, end_x, base_z_values[index], mm_scale
            )

            platform_color = (
                PREVIEW_WARNING if violations[index] else PREVIEW_FLOOR
            )
            platform = line_curve(p0, p1)
            preview_curves.append((platform, platform_color, 3))
            bake_curves.append((platform, platform_color, "Floor"))

            if index < row_count - 1:
                next_index = index + 1
                riser_x = end_x
                riser_start = p1

                if aisle_before_values[next_index]:
                    stair_run = aisle_stair_run_values[next_index]
                    aisle_end_x = (
                        x_values[next_index] - row_pitch - stair_run
                    )
                    if aisle_end_x - end_x > 1e-8:
                        aisle_end = point_at(
                            stage_point,
                            direction,
                            aisle_end_x,
                            base_z_values[index],
                            mm_scale
                        )
                        aisle_curve = line_curve(p1, aisle_end)
                        preview_curves.append(
                            (aisle_curve, PREVIEW_AISLE, 4)
                        )
                        bake_curves.append(
                            (aisle_curve, PREVIEW_AISLE, "CrossAisle")
                        )
                        riser_start = aisle_end
                    else:
                        aisle_end = p1

                    stair_tread_count = (
                        aisle_stair_tread_counts[next_index]
                    )
                    stair_riser_height = (
                        aisle_stair_riser_heights[next_index]
                    )
                    stair_color = (
                        PREVIEW_WARNING
                        if violations[next_index]
                        else PREVIEW_AISLE
                    )
                    stair_x = aisle_end_x
                    stair_z = base_z_values[index]

                    if (
                        base_z_values[next_index] - stair_z
                        > 1e-8
                    ):
                        for stair_index in range(
                            stair_tread_count + 1
                        ):
                            next_stair_z = (
                                base_z_values[next_index]
                                if stair_index == stair_tread_count
                                else (
                                    base_z_values[index]
                                    + stair_riser_height
                                    * (stair_index + 1)
                                )
                            )
                            stair_riser_start = point_at(
                                stage_point,
                                direction,
                                stair_x,
                                stair_z,
                                mm_scale
                            )
                            stair_riser_end = point_at(
                                stage_point,
                                direction,
                                stair_x,
                                next_stair_z,
                                mm_scale
                            )
                            stair_riser = line_curve(
                                stair_riser_start,
                                stair_riser_end
                            )
                            preview_curves.append(
                                (stair_riser, stair_color, 4)
                            )
                            bake_curves.append(
                                (
                                    stair_riser,
                                    stair_color,
                                    "CrossAisleStairRiser",
                                )
                            )
                            stair_z = next_stair_z

                            if stair_index < stair_tread_count:
                                next_stair_x = (
                                    stair_x
                                    + aisle_stair_tread_depth
                                )
                                stair_tread_start = point_at(
                                    stage_point,
                                    direction,
                                    stair_x,
                                    stair_z,
                                    mm_scale
                                )
                                stair_tread_end = point_at(
                                    stage_point,
                                    direction,
                                    next_stair_x,
                                    stair_z,
                                    mm_scale
                                )
                                stair_tread = line_curve(
                                    stair_tread_start,
                                    stair_tread_end
                                )
                                preview_curves.append(
                                    (stair_tread, stair_color, 4)
                                )
                                bake_curves.append(
                                    (
                                        stair_tread,
                                        stair_color,
                                        "CrossAisleStairTread",
                                    )
                                )
                                stair_x = next_stair_x
                    elif stair_run > 1e-8:
                        # A zero-rise interpolation keeps the original stair
                        # run as one continuous horizontal aisle segment.
                        flat_run_end = point_at(
                            stage_point,
                            direction,
                            aisle_end_x + stair_run,
                            stair_z,
                            mm_scale
                        )
                        flat_run = line_curve(aisle_end, flat_run_end)
                        preview_curves.append(
                            (flat_run, stair_color, 4)
                        )
                        bake_curves.append(
                            (
                                flat_run,
                                stair_color,
                                "CrossAisleStairFlatRun",
                            )
                        )
                    continue

                if (
                    base_z_values[next_index]
                    - base_z_values[index]
                    > 1e-8
                ):
                    p2 = point_at(
                        stage_point,
                        direction,
                        riser_x,
                        base_z_values[next_index],
                        mm_scale
                    )
                    riser_color = (
                        PREVIEW_WARNING
                        if violations[next_index]
                        else PREVIEW_FLOOR
                    )
                    riser = line_curve(riser_start, p2)
                    preview_curves.append((riser, riser_color, 3))
                    bake_curves.append((riser, riser_color, "Floor"))
    else:
        # Extend the first slope toward the stage by one complete row pitch.
        if row_count == 1:
            first_slope = 0.0
        else:
            first_slope = slope_values[1]

        front_x = x_values[0] - row_pitch
        front_z = base_z_values[0] - row_pitch * first_slope
        p0 = point_at(stage_point, direction, front_x, front_z, mm_scale)
        p1 = point_at(
            stage_point,
            direction,
            x_values[0],
            base_z_values[0],
            mm_scale
        )
        front_color = (
            PREVIEW_WARNING
            if row_count > 1 and violations[1]
            else PREVIEW_FLOOR
        )
        front_extension = line_curve(p0, p1)
        preview_curves.append((front_extension, front_color, 3))
        bake_curves.append((front_extension, front_color, "Floor"))

        for index in range(1, row_count):
            p0 = point_at(
                stage_point,
                direction,
                x_values[index - 1],
                base_z_values[index - 1],
                mm_scale
            )
            if aisle_before_values[index]:
                aisle_end_x = x_values[index] - row_pitch
                if aisle_end_x - x_values[index - 1] > 1e-8:
                    aisle_end = point_at(
                        stage_point,
                        direction,
                        aisle_end_x,
                        base_z_values[index - 1],
                        mm_scale
                    )
                    aisle_curve = line_curve(p0, aisle_end)
                    preview_curves.append(
                        (aisle_curve, PREVIEW_AISLE, 4)
                    )
                    bake_curves.append(
                        (aisle_curve, PREVIEW_AISLE, "CrossAisle")
                    )
                    p0 = aisle_end

            p1 = point_at(
                stage_point,
                direction,
                x_values[index],
                base_z_values[index],
                mm_scale
            )
            segment_color = (
                PREVIEW_WARNING if violations[index] else PREVIEW_FLOOR
            )
            segment = line_curve(p0, p1)
            preview_curves.append((segment, segment_color, 3))
            bake_curves.append((segment, segment_color, "Floor"))

    # Preserve one more full cross-aisle behind the last row, then close the
    # rear of the auditorium section visually up to the ceiling.
    rear_aisle_start = point_at(
        stage_point,
        direction,
        x_values[-1],
        base_z_values[-1],
        mm_scale
    )
    rear_aisle_end = point_at(
        stage_point,
        direction,
        rear_wall_x,
        base_z_values[-1],
        mm_scale
    )
    if rear_aisle_width > 1e-8:
        rear_aisle_curve = line_curve(
            rear_aisle_start,
            rear_aisle_end
        )
        preview_curves.append(
            (rear_aisle_curve, PREVIEW_AISLE, 4)
        )
        bake_curves.append(
            (rear_aisle_curve, PREVIEW_AISLE, "RearCrossAisle")
        )

    rear_ceiling_point = point_at(
        stage_point,
        direction,
        rear_wall_x,
        auditorium_ceiling_z,
        mm_scale
    )
    rear_wall_curve = line_curve(
        rear_aisle_end,
        rear_ceiling_point
    )
    preview_curves.append(
        (rear_wall_curve, PREVIEW_AUDITORIUM_CEILING, 3)
    )
    bake_curves.append(
        (
            rear_wall_curve,
            PREVIEW_AUDITORIUM_CEILING,
            "AuditoriumRearWallSection",
        )
    )

    violation_rows = [
        index + 1
        for index, is_violation in enumerate(violations)
        if is_violation
    ]
    slope_violation_rows = [
        index + 1
        for index, is_violation in enumerate(
            result["slope_violations"]
        )
        if is_violation
    ]
    sightline_violation_rows = [
        index + 1
        for index, is_violation in enumerate(
            result["sightline_violations"]
        )
        if is_violation
    ]
    ceiling_violation_rows = [
        index + 1
        for index, is_violation in enumerate(ceiling_violations)
        if is_violation
    ]

    maximum_actual_slope = max(result["slope_values"])
    total_depth = (
        x_values[-1] - x_values[0] + row_pitch + rear_aisle_width
        if row_count > 0
        else 0.0
    )
    total_rise = (
        base_z_values[-1] - base_z_values[0]
        if row_count > 0
        else 0.0
    )

    if params.get("show_floor_surfaces", False):
        floor_surface_result = build_floor_surface_geometry(
            stage_point,
            direction,
            params,
            section_dimensions,
            opening_width_mm,
            opening_height_mm,
            rear_wall_x,
            base_z_values[-1],
            mm_scale,
            doc.ModelAbsoluteTolerance,
            bake_curves
        )
        preview_meshes[0:0] = floor_surface_result[
            "preview_meshes"
        ]
        bake_breps.extend(floor_surface_result["bake_breps"])

    return {
        "preview_curves": preview_curves,
        "preview_points": preview_points,
        "preview_meshes": preview_meshes,
        "preview_labels": preview_labels,
        "bake_curves": bake_curves,
        "bake_points": bake_points,
        "bake_breps": bake_breps,
        "bake_instances": bake_instances,
        "seat_source": seat_source,
        "seat_3d_calculation": seat_3d_result,
        "seat_3d_calculations": seat_3d_results,
        "floor_surface_calculation": floor_surface_result,
        "calculation": result,
        "balcony_calculation": balcony_result,
        "balcony_calculations": balcony_results,
        "balcony2_dependency_warning": balcony2_dependency_warning,
        "violation_rows": violation_rows,
        "slope_violation_rows": slope_violation_rows,
        "sightline_violation_rows": sightline_violation_rows,
        "ceiling_violation_rows": ceiling_violation_rows,
        "maximum_actual_slope": maximum_actual_slope,
        "total_depth": total_depth,
        "total_rise": total_rise,
        "direction": direction,
        "stage_section_dimensions": section_dimensions,
        "applied_section_rise_overrides": {
            "stalls": result.get("rise_interpolation_target"),
            "balcony_1": (
                balcony_result.get("rise_interpolation_target")
                if balcony_result is not None
                else None
            ),
            "balcony_2": (
                balcony2_result.get("rise_interpolation_target")
                if balcony2_result is not None
                else None
            ),
        },
    }


class AuditoriumPreviewConduit(Rhino.Display.DisplayConduit):
    def __init__(self):
        Rhino.Display.DisplayConduit.__init__(self)
        self.curves = []
        self.points = []
        self.meshes = []
        self.labels = []
        self.bounding_box = rg.BoundingBox.Empty

    def set_geometry(self, preview_data):
        self.curves = preview_data.get("preview_curves", [])
        self.points = preview_data.get("preview_points", [])
        self.meshes = preview_data.get("preview_meshes", [])
        self.labels = preview_data.get("preview_labels", [])
        self.update_bounding_box()

    def clear(self):
        self.curves = []
        self.points = []
        self.meshes = []
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


class ProsceniumSettingsDialog(forms.Dialog[bool]):
    """Edit stage-space plan, height, understage and preview settings."""
    def __init__(
        self,
        values,
        opening_width_mm,
        opening_height_mm,
        preview_callback=None
    ):
        forms.Dialog[bool].__init__(self)

        self.opening_width_mm = opening_width_mm
        self.opening_height_mm = opening_height_mm
        self.preview_callback = preview_callback
        self.values = {
            key: values[key]
            for key in PROSCENIUM_PARAM_KEYS
        }
        self.accepted = False

        self.Title = "프로시니엄 무대공간 설정"
        self.ClientSize = drawing.Size(980, 620)
        self.Padding = drawing.Padding(12)
        self.Resizable = True

        self.section_2d_radio = forms.RadioButton()
        self.section_2d_radio.Text = "2D 중앙 종단면"
        self.space_3d_radio = forms.RadioButton(self.section_2d_radio)
        self.space_3d_radio.Text = "3D 공간 커브"
        if self.values["stage_preview_mode"] == "space_3d":
            self.space_3d_radio.Checked = True
        else:
            self.section_2d_radio.Checked = True

        self.main_width_box = self.make_text_box(
            self.values["main_stage_width"]
        )
        self.main_depth_box = self.make_text_box(
            self.values["main_stage_depth"]
        )
        self.main_height_box = self.make_text_box(
            self.values["main_stage_height"]
        )

        (
            self.right_yes_radio,
            self.right_no_radio,
        ) = self.make_radio_pair(self.values["right_stage_enabled"])
        self.right_width_box = self.make_text_box(
            self.values["right_stage_width"]
        )
        self.right_depth_box = self.make_text_box(
            self.values["right_stage_depth"]
        )
        self.right_height_box = self.make_text_box(
            self.values["right_stage_height"]
        )

        (
            self.left_yes_radio,
            self.left_no_radio,
        ) = self.make_radio_pair(self.values["left_stage_enabled"])
        self.left_width_box = self.make_text_box(
            self.values["left_stage_width"]
        )
        self.left_depth_box = self.make_text_box(
            self.values["left_stage_depth"]
        )
        self.left_height_box = self.make_text_box(
            self.values["left_stage_height"]
        )

        (
            self.rear_yes_radio,
            self.rear_no_radio,
        ) = self.make_radio_pair(self.values["rear_stage_enabled"])
        self.rear_width_box = self.make_text_box(
            self.values["rear_stage_width"]
        )
        self.rear_depth_box = self.make_text_box(
            self.values["rear_stage_depth"]
        )
        self.rear_height_box = self.make_text_box(
            self.values["rear_stage_height"]
        )

        (
            self.understage_yes_radio,
            self.understage_no_radio,
        ) = self.make_radio_pair(self.values["understage_enabled"])
        self.understage_depth_box = self.make_text_box(
            self.values["understage_depth"]
        )

        for radio in (
            self.right_yes_radio,
            self.right_no_radio,
            self.left_yes_radio,
            self.left_no_radio,
            self.rear_yes_radio,
            self.rear_no_radio,
            self.understage_yes_radio,
            self.understage_no_radio,
        ):
            radio.CheckedChanged += self.on_stage_option_changed
        self.section_2d_radio.CheckedChanged += (
            self.on_preview_mode_changed
        )
        self.space_3d_radio.CheckedChanged += (
            self.on_preview_mode_changed
        )

        for text_box in self.all_value_boxes():
            text_box.KeyDown += self.on_text_box_key_down
            text_box.LostFocus += self.on_text_box_lost_focus

        self.warning_label = forms.Label()
        self.warning_label.TextColor = drawing.Color(210, 35, 35)

        self.formula_button = forms.Button()
        self.formula_button.Text = "계산 치수 적용"
        self.formula_button.Click += self.on_apply_formula

        self.ok_button = forms.Button()
        self.ok_button.Text = "확인"
        self.ok_button.Click += self.on_ok

        self.cancel_button = forms.Button()
        self.cancel_button.Text = "취소"
        self.cancel_button.Click += self.on_cancel

        self.DefaultButton = self.ok_button
        self.AbortButton = self.cancel_button

        opening_label = forms.Label()
        opening_label.Text = (
            "개구부 PW × PH: {0:.1f} × {1:.1f} mm".format(
                self.opening_width_mm,
                self.opening_height_mm
            )
        )

        formula_label = forms.Label()
        formula_label.Text = (
            "평면 기본값: 폭 = PW + 8,000 / 깊이 = PW × 1.2\n"
            "높이 기본값: 주무대 = PH × 3 + 2,000 / "
            "좌·우·뒷무대 = PH + 2,000 / 하부무대 = PH + 2,000\n"
            "각 상부 그리드와 하부 설비 바닥은 끝면에서 2,000 mm 이격"
        )

        preview_row = forms.StackLayout()
        preview_row.Orientation = forms.Orientation.Horizontal
        preview_row.Spacing = 20
        preview_row.Items.Add(self.section_2d_radio)
        preview_row.Items.Add(self.space_3d_radio)

        main_layout = forms.DynamicLayout()
        main_layout.Spacing = drawing.Size(8, 8)

        main_layout.AddRow(self.make_header("기준"))
        main_layout.AddRow(opening_label)
        main_layout.AddRow(formula_label)
        main_layout.AddRow(None)

        main_layout.AddRow(self.make_header("프리뷰 방식"))
        main_layout.AddRow(preview_row)
        main_layout.AddRow(None)

        main_layout.AddRow(self.make_header("주무대"))
        main_layout.AddRow(
            self.make_dimension_row(
                None,
                None,
                self.main_width_box,
                self.main_depth_box,
                self.main_height_box
            )
        )
        main_layout.AddRow(None)

        main_layout.AddRow(self.make_header("선택 무대"))
        main_layout.AddRow(
            self.make_dimension_row(
                "오른무대 (배우 기준)",
                (self.right_yes_radio, self.right_no_radio),
                self.right_width_box,
                self.right_depth_box,
                self.right_height_box
            )
        )
        main_layout.AddRow(
            self.make_dimension_row(
                "왼무대 (배우 기준)",
                (self.left_yes_radio, self.left_no_radio),
                self.left_width_box,
                self.left_depth_box,
                self.left_height_box
            )
        )
        main_layout.AddRow(
            self.make_dimension_row(
                "뒷무대",
                (self.rear_yes_radio, self.rear_no_radio),
                self.rear_width_box,
                self.rear_depth_box,
                self.rear_height_box
            )
        )
        main_layout.AddRow(None)

        main_layout.AddRow(self.make_header("하부무대"))
        main_layout.AddRow(self.make_understage_row())
        main_layout.AddRow(None)
        main_layout.AddRow(self.warning_label)

        button_row = forms.StackLayout()
        button_row.Orientation = forms.Orientation.Horizontal
        button_row.HorizontalContentAlignment = (
            forms.HorizontalAlignment.Right
        )
        button_row.Spacing = 8
        button_row.Items.Add(self.formula_button)
        button_row.Items.Add(self.ok_button)
        button_row.Items.Add(self.cancel_button)
        main_layout.AddRow(button_row)

        scrollable = forms.Scrollable()
        scrollable.Content = main_layout
        self.Content = scrollable
        self.update_enabled_state()

    def make_header(self, text):
        label = forms.Label()
        label.Text = text
        try:
            label.Font = drawing.Font(
                label.Font.FamilyName,
                label.Font.Size,
                drawing.FontStyle.Bold
            )
        except Exception:
            pass
        return label

    def make_label(self, text):
        label = forms.Label()
        label.Text = text
        label.VerticalAlignment = forms.VerticalAlignment.Center
        return label

    def make_text_box(self, value):
        box = forms.TextBox()
        box.Text = "{0:.1f}".format(float(value))
        box.Width = 95
        return box

    def all_value_boxes(self):
        return [
            self.main_width_box,
            self.main_depth_box,
            self.main_height_box,
            self.right_width_box,
            self.right_depth_box,
            self.right_height_box,
            self.left_width_box,
            self.left_depth_box,
            self.left_height_box,
            self.rear_width_box,
            self.rear_depth_box,
            self.rear_height_box,
            self.understage_depth_box,
        ]

    def make_radio_pair(self, enabled):
        yes_radio = forms.RadioButton()
        yes_radio.Text = "있음"
        no_radio = forms.RadioButton(yes_radio)
        no_radio.Text = "없음"

        if enabled:
            yes_radio.Checked = True
        else:
            no_radio.Checked = True

        return yes_radio, no_radio

    def make_dimension_row(
        self,
        stage_label,
        radios,
        width_box,
        depth_box,
        height_box
    ):
        row = forms.StackLayout()
        row.Orientation = forms.Orientation.Horizontal
        row.Spacing = 8

        if stage_label:
            name_label = self.make_label(stage_label)
            name_label.Width = 155
            row.Items.Add(name_label)

        if radios:
            yes_radio, no_radio = radios
            row.Items.Add(yes_radio)
            row.Items.Add(no_radio)

        row.Items.Add(self.make_label("폭"))
        row.Items.Add(width_box)
        row.Items.Add(self.make_label("깊이"))
        row.Items.Add(depth_box)
        row.Items.Add(self.make_label("높이"))
        row.Items.Add(height_box)
        row.Items.Add(self.make_label("mm"))
        return row

    def make_understage_row(self):
        row = forms.StackLayout()
        row.Orientation = forms.Orientation.Horizontal
        row.Spacing = 8
        name_label = self.make_label("하부무대")
        name_label.Width = 155
        row.Items.Add(name_label)
        row.Items.Add(self.understage_yes_radio)
        row.Items.Add(self.understage_no_radio)
        row.Items.Add(self.make_label("Z 깊이"))
        row.Items.Add(self.understage_depth_box)
        row.Items.Add(self.make_label("mm"))
        return row

    def parse_float(self, text_box, label):
        try:
            text = text_box.Text.strip().replace(",", "")
            return float(text)
        except Exception:
            raise ValueError("{0} 값을 숫자로 입력해 주세요.".format(label))

    def parse_optional_float(self, text_box, label, enabled, key):
        if enabled:
            return self.parse_float(text_box, label)
        try:
            return self.parse_float(text_box, label)
        except Exception:
            return float(self.values[key])

    def read_values(self):
        right_enabled = bool(self.right_yes_radio.Checked)
        left_enabled = bool(self.left_yes_radio.Checked)
        rear_enabled = bool(self.rear_yes_radio.Checked)
        understage_enabled = bool(self.understage_yes_radio.Checked)

        values = {
            "stage_preview_mode": (
                "space_3d"
                if self.space_3d_radio.Checked
                else "section_2d"
            ),
            "main_stage_width": self.parse_float(
                self.main_width_box, "주무대 폭"
            ),
            "main_stage_depth": self.parse_float(
                self.main_depth_box, "주무대 깊이"
            ),
            "main_stage_height": self.parse_float(
                self.main_height_box, "주무대 높이"
            ),
            "right_stage_enabled": right_enabled,
            "right_stage_width": self.parse_optional_float(
                self.right_width_box,
                "오른무대 폭",
                right_enabled,
                "right_stage_width"
            ),
            "right_stage_depth": self.parse_optional_float(
                self.right_depth_box,
                "오른무대 깊이",
                right_enabled,
                "right_stage_depth"
            ),
            "right_stage_height": self.parse_optional_float(
                self.right_height_box,
                "오른무대 높이",
                right_enabled,
                "right_stage_height"
            ),
            "left_stage_enabled": left_enabled,
            "left_stage_width": self.parse_optional_float(
                self.left_width_box,
                "왼무대 폭",
                left_enabled,
                "left_stage_width"
            ),
            "left_stage_depth": self.parse_optional_float(
                self.left_depth_box,
                "왼무대 깊이",
                left_enabled,
                "left_stage_depth"
            ),
            "left_stage_height": self.parse_optional_float(
                self.left_height_box,
                "왼무대 높이",
                left_enabled,
                "left_stage_height"
            ),
            "rear_stage_enabled": rear_enabled,
            "rear_stage_width": self.parse_optional_float(
                self.rear_width_box,
                "뒷무대 폭",
                rear_enabled,
                "rear_stage_width"
            ),
            "rear_stage_depth": self.parse_optional_float(
                self.rear_depth_box,
                "뒷무대 깊이",
                rear_enabled,
                "rear_stage_depth"
            ),
            "rear_stage_height": self.parse_optional_float(
                self.rear_height_box,
                "뒷무대 높이",
                rear_enabled,
                "rear_stage_height"
            ),
            "understage_enabled": understage_enabled,
            "understage_depth": self.parse_optional_float(
                self.understage_depth_box,
                "하부무대 Z 깊이",
                understage_enabled,
                "understage_depth"
            ),
        }
        validate_proscenium_params(values, self.opening_width_mm)
        return values

    def update_enabled_state(self):
        right_enabled = bool(self.right_yes_radio.Checked)
        left_enabled = bool(self.left_yes_radio.Checked)
        rear_enabled = bool(self.rear_yes_radio.Checked)
        understage_enabled = bool(self.understage_yes_radio.Checked)

        for box in (
            self.right_width_box,
            self.right_depth_box,
            self.right_height_box,
        ):
            box.Enabled = right_enabled
        for box in (
            self.left_width_box,
            self.left_depth_box,
            self.left_height_box,
        ):
            box.Enabled = left_enabled
        for box in (
            self.rear_width_box,
            self.rear_depth_box,
            self.rear_height_box,
        ):
            box.Enabled = rear_enabled
        self.understage_depth_box.Enabled = understage_enabled

    def on_stage_option_changed(self, sender, event_args):
        self.update_enabled_state()
        self.try_live_preview()

    def on_preview_mode_changed(self, sender, event_args):
        self.try_live_preview()

    def on_text_box_key_down(self, sender, event_args):
        if event_args.Key == forms.Keys.Enter:
            self.try_live_preview()
            event_args.Handled = True

    def on_text_box_lost_focus(self, sender, event_args):
        self.try_live_preview()

    def try_live_preview(self):
        try:
            values = self.read_values()
        except Exception as error:
            self.warning_label.Text = str(error)
            return False

        if self.preview_callback is not None:
            try:
                preview_ok = self.preview_callback(dict(values))
            except Exception as error:
                self.warning_label.Text = str(error)
                return False
            if preview_ok is False:
                self.warning_label.Text = (
                    "프리뷰를 갱신할 수 없습니다. 기본 창의 입력값도 "
                    "확인해 주세요."
                )
                return False

        self.values = values
        self.warning_label.Text = ""
        return True

    def on_apply_formula(self, sender, event_args):
        calculated = calculated_proscenium_defaults(
            self.opening_width_mm,
            self.opening_height_mm
        )
        for key, box in (
            ("main_stage_width", self.main_width_box),
            ("main_stage_depth", self.main_depth_box),
            ("main_stage_height", self.main_height_box),
            ("right_stage_width", self.right_width_box),
            ("right_stage_depth", self.right_depth_box),
            ("right_stage_height", self.right_height_box),
            ("left_stage_width", self.left_width_box),
            ("left_stage_depth", self.left_depth_box),
            ("left_stage_height", self.left_height_box),
            ("rear_stage_width", self.rear_width_box),
            ("rear_stage_depth", self.rear_depth_box),
            ("rear_stage_height", self.rear_height_box),
            ("understage_depth", self.understage_depth_box),
        ):
            box.Text = str(calculated[key])
        self.try_live_preview()

    def on_ok(self, sender, event_args):
        if not self.try_live_preview():
            forms.MessageBox.Show(
                self,
                self.warning_label.Text,
                "프로시니엄 무대공간 설정",
                forms.MessageBoxButtons.OK,
                forms.MessageBoxType.Warning
            )
            return

        self.accepted = True
        self.Close(True)

    def on_cancel(self, sender, event_args):
        self.accepted = False
        self.Close(False)


class BalconySettingsDialog(forms.Dialog[bool]):
    def __init__(
        self,
        values,
        stalls_result,
        first_row_distance,
        opening_height_mm,
        stalls_rear_z,
        tier_index,
        live_preview_callback
    ):
        forms.Dialog[bool].__init__(self)

        self.base_calculation_params = dict(values)
        self.tier_index = tier_index
        self.key_map = BALCONY_TIER_KEY_MAPS[tier_index]
        self.values = {
            canonical_key: values[actual_key]
            for canonical_key, actual_key in self.key_map.items()
        }
        self.stalls_result = stalls_result
        self.first_row_distance = first_row_distance
        self.opening_height_mm = opening_height_mm
        self.stalls_rear_z = float(stalls_rear_z)
        self.live_preview_callback = live_preview_callback
        self.accepted = False

        saved_balcony_version = self.values.get(
            "balcony_settings_version",
            0
        )
        if saved_balcony_version < 1:
            self.values["balcony_railing_h"] = (
                standard_balcony_railing_height(
                    self.values["balcony_railing_t"]
                )
            )
        if saved_balcony_version < 2:
            self.values["balcony_row_count"] = max(
                1,
                self.calculate_maximum_rows(self.values)
            )
            self.values["balcony_settings_version"] = (
                BALCONY_SETTINGS_VERSION
            )

        self.Title = "발코니 {0} 설정".format(tier_index + 1)
        self.ClientSize = drawing.Size(470, 500)
        self.Padding = drawing.Padding(12)
        self.Resizable = True

        self.enabled_yes_radio = forms.RadioButton()
        self.enabled_yes_radio.Text = "On"
        self.enabled_no_radio = forms.RadioButton(
            self.enabled_yes_radio
        )
        self.enabled_no_radio.Text = "Off"
        if self.values["balcony_enabled"]:
            self.enabled_yes_radio.Checked = True
        else:
            self.enabled_no_radio.Checked = True

        self.last_platform_z_box = forms.TextBox()
        self.last_platform_z_box.Text = str(
            balcony_height_from_stalls_rear(
                self.values["balcony_last_platform_z"],
                self.stalls_rear_z
            )
        )
        self.row_count_box = self.make_text_box("balcony_row_count")
        self.row_pitch_box = self.make_text_box("balcony_row_pitch")
        self.railing_t_box = self.make_text_box("balcony_railing_t")
        self.railing_w_box = self.make_text_box("balcony_railing_w")
        self.railing_h_box = self.make_text_box("balcony_railing_h")

        self.maximum_rows_label = forms.Label()
        self.standard_height_label = forms.Label()
        self.calculation_label = forms.Label()
        self.warning_label = forms.Label()
        self.warning_label.TextColor = drawing.Color(210, 35, 35)

        self.maximum_rows_button = forms.Button()
        self.maximum_rows_button.Text = "최대 열 수 적용"
        self.standard_height_button = forms.Button()
        self.standard_height_button.Text = "기준 h 적용"
        self.ok_button = forms.Button()
        self.ok_button.Text = "OK"
        self.cancel_button = forms.Button()
        self.cancel_button.Text = "Cancel"

        self.DefaultButton = self.ok_button
        self.AbortButton = self.cancel_button

        self.enabled_yes_radio.CheckedChanged += self.on_option_changed
        self.enabled_no_radio.CheckedChanged += self.on_option_changed
        self.maximum_rows_button.Click += self.on_maximum_rows
        self.standard_height_button.Click += self.on_standard_height
        self.ok_button.Click += self.on_ok
        self.cancel_button.Click += self.on_cancel

        for text_box in self.all_text_boxes():
            text_box.KeyDown += self.on_text_box_key_down
            text_box.LostFocus += self.on_text_box_lost_focus

        layout = forms.DynamicLayout()
        layout.Spacing = drawing.Size(6, 6)

        enabled_row = forms.StackLayout()
        enabled_row.Orientation = forms.Orientation.Horizontal
        enabled_row.Spacing = 12
        enabled_row.Items.Add(self.enabled_yes_radio)
        enabled_row.Items.Add(self.enabled_no_radio)
        layout.AddRow(self.make_label("Balcony"), enabled_row)
        layout.AddRow(
            self.make_label(
                "Last platform above stalls rear = 0 (mm)"
            ),
            self.last_platform_z_box
        )
        layout.AddRow(
            self.make_label("Balcony rows"),
            self.row_count_box
        )
        layout.AddRow(self.maximum_rows_button)
        layout.AddRow(self.maximum_rows_label)
        layout.AddRow(
            self.make_label("Row pitch (mm)"),
            self.row_pitch_box
        )
        layout.AddRow(None)
        layout.AddRow(self.make_header("Front railing"))
        layout.AddRow(
            self.make_label("t (mm)"),
            self.railing_t_box
        )
        layout.AddRow(
            self.make_label("w (mm)"),
            self.railing_w_box
        )
        layout.AddRow(
            self.make_label("h (mm)"),
            self.railing_h_box
        )
        layout.AddRow(self.standard_height_button)
        layout.AddRow(self.standard_height_label)
        layout.AddRow(None)
        layout.AddRow(self.make_header("Calculated check"))
        layout.AddRow(self.calculation_label)
        layout.AddRow(self.warning_label)

        button_row = forms.StackLayout()
        button_row.Orientation = forms.Orientation.Horizontal
        button_row.HorizontalContentAlignment = (
            forms.HorizontalAlignment.Right
        )
        button_row.Spacing = 8
        button_row.Items.Add(self.ok_button)
        button_row.Items.Add(self.cancel_button)
        layout.AddRow(None)
        layout.AddRow(button_row)
        self.Content = layout

        self.update_enabled_state()
        self.try_live_preview()

    def make_header(self, text):
        label = forms.Label()
        label.Text = text
        try:
            label.Font = drawing.Font(
                label.Font.FamilyName,
                label.Font.Size,
                drawing.FontStyle.Bold
            )
        except Exception:
            pass
        return label

    def make_label(self, text):
        label = forms.Label()
        label.Text = text
        label.VerticalAlignment = forms.VerticalAlignment.Center
        return label

    def make_text_box(self, key):
        box = forms.TextBox()
        box.Text = str(self.values[key])
        return box

    def all_text_boxes(self):
        return [
            self.last_platform_z_box,
            self.row_count_box,
            self.row_pitch_box,
            self.railing_t_box,
            self.railing_w_box,
            self.railing_h_box,
        ]

    def parse_float(self, text_box, label):
        try:
            return float(text_box.Text.strip().replace(",", ""))
        except Exception:
            raise ValueError(
                "{0} 값을 숫자로 입력해 주세요.".format(label)
            )

    def parse_row_count(self):
        value = self.parse_float(
            self.row_count_box,
            "발코니 열 수"
        )
        integer_value = int(value)
        if (
            integer_value < 1
            or integer_value > 500
            or abs(value - integer_value) > 1e-8
        ):
            raise ValueError(
                "발코니 열 수는 1~500 범위의 정수여야 합니다."
            )
        return integer_value

    def read_values(self):
        relative_last_platform_z = self.parse_float(
            self.last_platform_z_box,
            "Last platform height from stalls rear"
        )
        values = {
            "balcony_enabled": bool(
                self.enabled_yes_radio.Checked
            ),
            "balcony_last_platform_z": self.parse_float(
                self.last_platform_z_box,
                "마지막 플랫폼 Z"
            ),
            "balcony_row_count": self.parse_row_count(),
            "balcony_row_pitch": self.parse_float(
                self.row_pitch_box,
                "발코니 열 간격"
            ),
            "balcony_railing_t": self.parse_float(
                self.railing_t_box,
                "난간 t"
            ),
            "balcony_railing_w": self.parse_float(
                self.railing_w_box,
                "난간 w"
            ),
            "balcony_railing_h": self.parse_float(
                self.railing_h_box,
                "난간 h"
            ),
            "balcony_settings_version": BALCONY_SETTINGS_VERSION,
        }
        if relative_last_platform_z <= 0.0:
            raise ValueError(
                "Last platform height above the stalls rear row "
                "must be greater than 0."
            )
        values["balcony_last_platform_z"] = (
            balcony_height_to_absolute(
                relative_last_platform_z,
                self.stalls_rear_z
            )
        )
        if values["balcony_last_platform_z"] <= 0.0:
            raise ValueError(
                "마지막 플랫폼 Z는 0보다 커야 합니다."
            )
        if values["balcony_row_pitch"] <= 0.0:
            raise ValueError("발코니 열 간격은 0보다 커야 합니다.")
        if values["balcony_railing_t"] < 0.0:
            raise ValueError("난간 t는 0 이상이어야 합니다.")
        if values["balcony_railing_w"] < 0.0:
            raise ValueError("난간 w는 0 이상이어야 합니다.")
        if values["balcony_railing_h"] <= 0.0:
            raise ValueError("난간 h는 0보다 커야 합니다.")
        return values

    def maximum_row_params(self, values):
        params = dict(self.base_calculation_params)
        params.update(self.external_values(values))
        params["first_row_distance"] = self.first_row_distance
        return normalized_balcony_tier_params(
            params,
            self.tier_index
        )

    def external_values(self, values=None):
        source = self.values if values is None else values
        return {
            actual_key: source[canonical_key]
            for canonical_key, actual_key in self.key_map.items()
        }

    def calculate_maximum_rows(self, values):
        return calculate_balcony_max_rows(
            self.maximum_row_params(values),
            self.stalls_result,
            self.opening_height_mm,
            tier_index=self.tier_index
        )

    def update_enabled_state(self):
        enabled = bool(self.enabled_yes_radio.Checked)
        for text_box in self.all_text_boxes():
            text_box.Enabled = enabled
        self.maximum_rows_button.Enabled = enabled
        self.standard_height_button.Enabled = enabled

    def update_labels(self, values, balcony_result):
        maximum_rows = self.calculate_maximum_rows(values)
        standard_h = standard_balcony_railing_height(
            values["balcony_railing_t"]
        )
        self.maximum_rows_label.Text = (
            "Calculated maximum rows: {0}".format(maximum_rows)
        )
        self.standard_height_label.Text = (
            "Reference h from t: {0:.1f} mm".format(standard_h)
        )

        if not values["balcony_enabled"]:
            self.calculation_label.Text = "Balcony preview: Off"
            self.warning_label.Text = ""
            return
        if balcony_result is None:
            return

        angle_status = (
            "WARNING"
            if balcony_result["angle_violation"]
            else "PASS"
        )
        railing_status = (
            "WARNING"
            if balcony_result["railing_sight_collision"]
            else "PASS"
        )
        lower_limit_status = (
            "WARNING"
            if balcony_result["lower_limit_violation"]
            else "PASS"
        )
        ceiling_status = (
            "WARNING"
            if balcony_result["ceiling_violation"]
            else "PASS"
        )
        self.calculation_label.Text = (
            "Maximum rake angle: {0:.2f}° / {1}\n"
            "Railing sightline: {2}\n"
            "Sightline-allowable h: {3:.1f} mm\n"
            "Balcony lower limit: {4} / {5:.1f} mm\n"
            "Ceiling clearance: {6} / {7:.1f} mm".format(
                balcony_result["maximum_angle_degrees"],
                angle_status,
                railing_status,
                balcony_result["allowable_railing_h"],
                lower_limit_status,
                balcony_result["minimum_lower_limit_clearance"],
                ceiling_status,
                balcony_result["ceiling_clearance"]
            )
        )
        minimum_sightline_clearance = balcony_result.get(
            "minimum_sightline_clearance"
        )
        if minimum_sightline_clearance is None:
            seat_sightline_text = "N/A"
        else:
            seat_sightline_text = (
                "{0:.1f} mm / required {1:.1f} mm / {2}"
            ).format(
                minimum_sightline_clearance,
                self.base_calculation_params["sight_clearance"],
                (
                    "WARNING"
                    if balcony_result.get(
                        "sightline_violation",
                        False
                    )
                    else "PASS"
                )
            )
        self.calculation_label.Text += (
            "\nSeat sightline clearance: " + seat_sightline_text
        )

        warnings = []
        if values["balcony_row_count"] > maximum_rows:
            warnings.append(
                "입력 열 수가 계산된 최대 열 수를 초과합니다."
            )
        if balcony_result["angle_violation"]:
            warnings.append("발코니 경사각이 35°를 초과합니다.")
        if balcony_result["railing_sight_collision"]:
            warnings.append(
                "첫 열 하부 시야선이 난간 상단과 충돌합니다."
            )
        if balcony_result.get("sightline_violation", False):
            warnings.append(
                "보간된 발코니 좌석의 시야 여유가 기준보다 작습니다."
            )
        if balcony_result["lower_limit_violation"]:
            warnings.append(
                "발코니가 계산된 하한선 아래로 내려갑니다."
            )
        if balcony_result["ceiling_violation"]:
            warnings.append(
                "발코니 의자 상단이 객석 천장선을 초과합니다."
            )
        self.warning_label.Text = "\n".join(warnings)

    def try_live_preview(self):
        try:
            values = self.read_values()
            self.values.update(values)
            balcony_result = self.live_preview_callback(
                self.tier_index,
                self.external_values(values)
            )
            if values["balcony_enabled"] and balcony_result is None:
                raise ValueError(
                    "Balcony preview could not be updated."
                )
            self.update_labels(values, balcony_result)
            return True
        except Exception as error:
            self.warning_label.Text = str(error)
            return False

    def on_text_box_key_down(self, sender, event_args):
        if event_args.Key == forms.Keys.Enter:
            self.try_live_preview()
            event_args.Handled = True

    def on_text_box_lost_focus(self, sender, event_args):
        self.try_live_preview()

    def on_option_changed(self, sender, event_args):
        self.update_enabled_state()
        self.try_live_preview()

    def on_maximum_rows(self, sender, event_args):
        try:
            values = self.read_values()
            maximum_rows = self.calculate_maximum_rows(values)
            if maximum_rows < 1:
                raise ValueError(
                    "현재 마지막 플랫폼 Z에서는 하한선을 만족하는 "
                    "발코니 열을 생성할 수 없습니다."
                )
            self.row_count_box.Text = str(maximum_rows)
            self.try_live_preview()
        except Exception as error:
            self.warning_label.Text = str(error)

    def on_standard_height(self, sender, event_args):
        try:
            railing_t = self.parse_float(
                self.railing_t_box,
                "난간 t"
            )
            self.railing_h_box.Text = str(
                standard_balcony_railing_height(railing_t)
            )
            self.try_live_preview()
        except Exception as error:
            self.warning_label.Text = str(error)

    def on_ok(self, sender, event_args):
        if not self.try_live_preview():
            forms.MessageBox.Show(
                self,
                self.warning_label.Text,
                "발코니석 설정",
                forms.MessageBoxButtons.OK,
                forms.MessageBoxType.Warning
            )
            return
        self.accepted = True
        self.Close(True)

    def on_cancel(self, sender, event_args):
        self.accepted = False
        self.Close(False)


class SectionDimensionInterpolationDialog(forms.Dialog[bool]):
    def __init__(self, sections, overrides):
        forms.Dialog[bool].__init__(self)

        self.sections = list(sections)
        self.overrides = dict(overrides)
        self.target_boxes = {}
        self.accepted = False

        self.Title = "Section Dimension Interpolation"
        self.ClientSize = drawing.Size(560, 320)
        self.Padding = drawing.Padding(12)
        self.Resizable = True

        layout = forms.DynamicLayout()
        layout.Spacing = drawing.Size(8, 8)
        layout.AddRow(
            self.make_header("Seating tier"),
            self.make_header("Current rise"),
            self.make_header("Target rise (mm)")
        )

        for section in self.sections:
            target_box = forms.TextBox()
            existing_target = self.overrides.get(section["key"])
            target_value = (
                existing_target
                if existing_target is not None
                else section["current_rise"]
            )
            target_box.Text = self.format_value(target_value)
            target_box.Enabled = bool(section["editable"])
            self.target_boxes[section["key"]] = target_box
            current_label = forms.Label()
            current_label.Text = format_section_height_dimension(
                section["current_rise"]
            )
            current_label.VerticalAlignment = (
                forms.VerticalAlignment.Center
            )
            name_label = forms.Label()
            name_label.Text = section["label"]
            name_label.VerticalAlignment = forms.VerticalAlignment.Center
            layout.AddRow(name_label, current_label, target_box)

        layout.AddRow(None)

        round_down_button = forms.Button()
        round_down_button.Text = "10 mm Down"
        round_down_button.Click += self.on_round_down
        round_nearest_button = forms.Button()
        round_nearest_button.Text = "10 mm Round"
        round_nearest_button.Click += self.on_round_nearest
        round_up_button = forms.Button()
        round_up_button.Text = "10 mm Up"
        round_up_button.Click += self.on_round_up

        rounding_row = forms.StackLayout()
        rounding_row.Orientation = forms.Orientation.Horizontal
        rounding_row.Spacing = 8
        rounding_row.Items.Add(round_down_button)
        rounding_row.Items.Add(round_nearest_button)
        rounding_row.Items.Add(round_up_button)
        layout.AddRow(rounding_row)

        reset_button = forms.Button()
        reset_button.Text = "Reset"
        reset_button.Click += self.on_reset
        apply_button = forms.Button()
        apply_button.Text = "Apply"
        apply_button.Click += self.on_apply
        cancel_button = forms.Button()
        cancel_button.Text = "Cancel"
        cancel_button.Click += self.on_cancel
        self.DefaultButton = apply_button
        self.AbortButton = cancel_button

        action_row = forms.StackLayout()
        action_row.Orientation = forms.Orientation.Horizontal
        action_row.HorizontalContentAlignment = (
            forms.HorizontalAlignment.Right
        )
        action_row.Spacing = 8
        action_row.Items.Add(reset_button)
        action_row.Items.Add(apply_button)
        action_row.Items.Add(cancel_button)
        layout.AddRow(action_row)
        self.Content = layout

    def make_header(self, text):
        label = forms.Label()
        label.Text = text
        try:
            label.Font = drawing.Font(
                label.Font.FamilyName,
                label.Font.Size,
                drawing.FontStyle.Bold
            )
        except Exception:
            pass
        return label

    def format_value(self, value):
        rounded = round(float(value))
        if abs(float(value) - rounded) <= 1e-8:
            return str(int(rounded))
        return "{0:.3f}".format(float(value)).rstrip("0").rstrip(".")

    def set_rounded_targets(self, mode):
        for section in self.sections:
            if not section["editable"]:
                continue
            current_rise = section["current_rise"]
            if mode == "down":
                target = math.floor(current_rise / 10.0) * 10.0
            elif mode == "up":
                target = math.ceil(current_rise / 10.0) * 10.0
            else:
                target = math.floor(current_rise / 10.0 + 0.5) * 10.0
            self.target_boxes[section["key"]].Text = self.format_value(
                target
            )

    def read_targets(self):
        targets = {}
        for section in self.sections:
            if not section["editable"]:
                continue
            text = (
                self.target_boxes[section["key"]]
                .Text.strip()
                .replace(",", "")
            )
            try:
                target = float(text)
            except Exception:
                raise ValueError(
                    "{0} 목표값을 숫자로 입력해 주세요.".format(
                        section["label"]
                    )
                )
            validate_section_rise_target(
                [0.0, section["current_rise"]],
                target,
                section["label"]
            )
            targets[section["key"]] = target
        return targets

    def confirm_large_changes(self, targets):
        large_sections = []
        aisle_stair_warning = False
        for section in self.sections:
            target = targets.get(section["key"])
            current = section["current_rise"]
            if target is None or current <= 1e-12:
                continue
            ratio = abs(target - current) / current
            if ratio >= SECTION_INTERPOLATION_WARNING_RATIO:
                large_sections.append(section["label"])
                aisle_stair_warning = (
                    aisle_stair_warning
                    or section.get("has_aisle_stairs", False)
                )

        if not large_sections:
            return True

        stair_note = (
            "\n\n횡단 통로 계단의 디딤판 수와 길이는 유지되고 "
            "단높이가 재분배됩니다. 적용 후 단높이를 확인해 주세요."
            if aisle_stair_warning
            else ""
        )
        result = forms.MessageBox.Show(
            self,
            (
                "다음 영역의 목표 상승 높이가 현재값과 20% 이상 "
                "차이 납니다:\n{0}{1}\n\n계속 적용하시겠습니까?"
            ).format(
                ", ".join(large_sections),
                stair_note
            ),
            "Section Dimension Interpolation",
            forms.MessageBoxButtons.YesNo,
            forms.MessageBoxType.Warning
        )
        return result == forms.DialogResult.Yes

    def on_round_down(self, sender, event_args):
        self.set_rounded_targets("down")

    def on_round_nearest(self, sender, event_args):
        self.set_rounded_targets("nearest")

    def on_round_up(self, sender, event_args):
        self.set_rounded_targets("up")

    def on_apply(self, sender, event_args):
        try:
            targets = self.read_targets()
            if not self.confirm_large_changes(targets):
                return
            self.overrides.update(targets)
            self.accepted = True
            self.Close(True)
        except Exception as error:
            forms.MessageBox.Show(
                self,
                str(error),
                "Section Dimension Interpolation",
                forms.MessageBoxButtons.OK,
                forms.MessageBoxType.Warning
            )

    def on_reset(self, sender, event_args):
        self.overrides = {
            key: None for key in SECTION_RISE_KEYS
        }
        self.accepted = True
        self.Close(True)

    def on_cancel(self, sender, event_args):
        self.accepted = False
        self.Close(False)


class CalculatedResultDialog(forms.Dialog[bool]):
    def __init__(self, result_text, warning_text):
        forms.Dialog[bool].__init__(self)

        self.Title = "Calculated Result"
        self.ClientSize = drawing.Size(560, 460)
        self.Padding = drawing.Padding(12)
        self.Resizable = True

        result_area = forms.TextArea()
        result_area.Text = result_text
        result_area.ReadOnly = True
        result_area.Wrap = True

        warning_area = forms.TextArea()
        warning_area.Text = warning_text
        warning_area.ReadOnly = True
        warning_area.Wrap = True
        warning_area.Height = 90

        close_button = forms.Button()
        close_button.Text = "Close"
        close_button.Click += self.on_close
        self.DefaultButton = close_button
        self.AbortButton = close_button

        button_row = forms.StackLayout()
        button_row.Orientation = forms.Orientation.Horizontal
        button_row.HorizontalContentAlignment = (
            forms.HorizontalAlignment.Right
        )
        button_row.Items.Add(close_button)

        layout = forms.DynamicLayout()
        layout.Spacing = drawing.Size(6, 6)
        layout.AddRow(result_area)
        layout.AddRow(warning_area)
        layout.AddRow(button_row)
        self.Content = layout

    def on_close(self, sender, event_args):
        self.Close(True)


class AuditoriumDialog(forms.Dialog[bool]):
    def __init__(self, stage_data, doc, seat_source=None):
        forms.Dialog[bool].__init__(self)

        self.stage_data = stage_data
        self.doc = doc
        self.seat_source = seat_source
        self.preview_data = None
        self.accepted = False
        self.section_rise_overrides = {
            key: None for key in SECTION_RISE_KEYS
        }
        self.section_solver_signatures = None
        self.conduit = AuditoriumPreviewConduit()
        self.conduit.Enabled = True

        mm_scale = unit_scale_from_mm(doc)
        self.opening_width_mm = stage_data["opening_width"] / mm_scale
        self.opening_height_mm = stage_data["opening_height"] / mm_scale

        saved = sc.sticky.get(STICKY_KEY, {})
        self.values = dict(DEFAULTS)
        self.values.update(
            calculated_proscenium_defaults(
                self.opening_width_mm,
                self.opening_height_mm
            )
        )
        self.values.update(saved)
        if "row_groups" not in saved:
            saved_row_count = saved.get(
                "row_count",
                DEFAULTS["row_count"]
            )
            self.values["row_groups"] = str(int(saved_row_count))
        if saved.get("auditorium_defaults_version", 0) < 2:
            self.values["stage_height"] = DEFAULTS["stage_height"]
            self.values["first_row_distance"] = DEFAULTS[
                "first_row_distance"
            ]
            self.values["row_pitch"] = DEFAULTS["row_pitch"]
        if saved.get("auditorium_defaults_version", 0) < 3:
            self.values["show_3d_seats"] = bool(
                seat_source is not None
            )
            self.values["seat_module_width"] = DEFAULTS[
                "seat_module_width"
            ]
            self.values["seat_blocks"] = DEFAULTS["seat_blocks"]
            self.values["longitudinal_aisle_width"] = DEFAULTS[
                "longitudinal_aisle_width"
            ]
        if saved.get("auditorium_defaults_version", 0) < 4:
            self.values["show_3d_seats"] = False
        if saved.get("auditorium_defaults_version", 0) < 5:
            self.values["side_floor_margin"] = DEFAULTS[
                "side_floor_margin"
            ]
            self.values["show_floor_surfaces"] = DEFAULTS[
                "show_floor_surfaces"
            ]
        if saved.get("auditorium_defaults_version", 0) < 6:
            self.values["show_riser_height_labels"] = DEFAULTS[
                "show_riser_height_labels"
            ]
        self.values["auditorium_defaults_version"] = (
            AUDITORIUM_DEFAULTS_VERSION
        )
        saved_settings_version = saved.get(
            "proscenium_settings_version",
            0
        )
        if saved_settings_version < 2:
            self.values["right_stage_enabled"] = True
            self.values["left_stage_enabled"] = True
            self.values["rear_stage_enabled"] = True
        if saved_settings_version < 3:
            self.values["stage_preview_mode"] = "section_2d"
            self.values["understage_enabled"] = True
        self.values["proscenium_settings_version"] = (
            PROSCENIUM_SETTINGS_VERSION
        )
        if saved.get("balcony_settings_version", 0) < 1:
            self.values["balcony_last_platform_z"] = (
                self.opening_height_mm
            )
            self.values["balcony_row_pitch"] = self.values[
                "row_pitch"
            ]
            self.values["balcony_railing_h"] = (
                standard_balcony_railing_height(
                    self.values["balcony_railing_t"]
                )
            )
        if saved.get("balcony2_settings_version", 0) < 1:
            self.values["balcony2_last_platform_z"] = (
                self.opening_height_mm * 1.5
            )
            self.values["balcony2_row_pitch"] = self.values[
                "row_pitch"
            ]
            self.values["balcony2_railing_h"] = (
                standard_balcony_railing_height(
                    self.values["balcony2_railing_t"]
                )
            )

        self.Title = "Elephant Tools - Auditorium Section Generator"
        self.ClientSize = drawing.Size(520, 680)
        self.Padding = drawing.Padding(12)
        self.Resizable = True

        self.stage_height_box = self.make_text_box("stage_height")
        self.first_distance_box = self.make_text_box("first_row_distance")
        self.apron_projection_box = self.make_text_box(
            "stage_apron_projection"
        )
        self.pit_depth_box = self.make_text_box(
            "orchestra_pit_depth"
        )
        self.row_pitch_box = self.make_text_box("row_pitch")
        self.stage_sight_z_box = self.make_text_box(
            "stage_sight_point_z"
        )
        self.sight_z_box = self.make_text_box("sight_point_z")
        self.clearance_box = self.make_text_box("sight_clearance")
        self.row_groups_box = self.make_text_box("row_groups")
        self.aisle_width_box = self.make_text_box("aisle_width")
        self.aisle_stair_tread_box = self.make_text_box(
            "aisle_stair_tread_depth"
        )
        self.seat_module_width_box = self.make_text_box(
            "seat_module_width"
        )
        self.seat_blocks_box = self.make_text_box("seat_blocks")
        self.longitudinal_aisle_width_box = self.make_text_box(
            "longitudinal_aisle_width"
        )
        self.side_floor_margin_box = self.make_text_box(
            "side_floor_margin"
        )
        self.total_3d_seat_count_label = forms.Label()
        self.total_3d_seat_count_label.Text = "Total seats: -"
        self.slope_denominator_box = self.make_text_box(
            "max_slope_denominator"
        )

        self.opening_value_label = forms.Label()
        self.result_text = ""
        self.warning_text = ""

        self.opening_value_label.Text = (
            "Opening: {0:.1f} × {1:.1f} mm".format(
                self.opening_width_mm,
                self.opening_height_mm
            )
        )

        self.stepped_radio = forms.RadioButton()
        self.stepped_radio.Text = "Stepped"
        self.sloped_radio = forms.RadioButton(self.stepped_radio)
        self.sloped_radio.Text = "Sloped"

        if self.values.get("floor_type", "stepped") == "sloped":
            self.sloped_radio.Checked = True
        else:
            self.stepped_radio.Checked = True
        self.aisle_stair_tread_box.Enabled = bool(
            self.stepped_radio.Checked
        )

        self.show_sightlines_check = forms.CheckBox()
        self.show_sightlines_check.Text = "Show sightlines"
        self.show_sightlines_check.Checked = bool(
            self.values.get("show_sightlines", True)
        )

        self.show_eye_points_check = forms.CheckBox()
        self.show_eye_points_check.Text = "Show sight points"
        self.show_eye_points_check.Checked = bool(
            self.values.get("show_eye_points", True)
        )

        self.show_seats_check = forms.CheckBox()
        self.show_seats_check.Text = "Show chairs"
        self.show_seats_check.Checked = bool(
            self.values.get("show_seats", True)
        )

        self.show_riser_height_labels_check = forms.CheckBox()
        self.show_riser_height_labels_check.Text = (
            "Show riser / section dimensions"
        )
        self.show_riser_height_labels_check.Checked = bool(
            self.values.get("show_riser_height_labels", True)
        )

        self.show_3d_seats_check = forms.CheckBox()
        self.show_3d_seats_check.Text = "Show 3D seat modules (all tiers)"
        self.show_3d_seats_check.Checked = bool(
            self.values.get("show_3d_seats", False)
            and seat_source is not None
        )
        self.show_3d_seats_check.Enabled = bool(
            seat_source is not None
        )

        self.show_floor_surfaces_check = forms.CheckBox()
        self.show_floor_surfaces_check.Text = "Show floor surfaces"
        self.show_floor_surfaces_check.Checked = bool(
            self.values.get("show_floor_surfaces", False)
        )

        self.flip_button = forms.Button()
        self.flip_button.Text = "Flip Direction"

        self.proscenium_button = forms.Button()
        self.proscenium_button.Text = "프로시니엄 수정"

        self.balcony_button = forms.Button()
        self.balcony_button.Text = "발코니 1 설정"

        self.balcony2_button = forms.Button()
        self.balcony2_button.Text = "발코니 2 설정"

        self.section_interpolation_button = forms.Button()
        self.section_interpolation_button.Text = (
            "Section Dimension Interpolation"
        )

        self.update_button = forms.Button()
        self.update_button.Text = "Update Preview"

        self.result_button = forms.Button()
        self.result_button.Text = "Calculated Result"

        self.ok_button = forms.Button()
        self.ok_button.Text = "OK"

        self.cancel_button = forms.Button()
        self.cancel_button.Text = "Cancel"

        self.AbortButton = self.cancel_button

        self.flip_button.Click += self.on_flip
        self.proscenium_button.Click += self.on_edit_proscenium
        self.balcony_button.Click += self.on_edit_balcony
        self.balcony2_button.Click += self.on_edit_balcony2
        self.section_interpolation_button.Click += (
            self.on_section_dimension_interpolation
        )
        self.update_button.Click += self.on_update
        self.result_button.Click += self.on_show_result
        self.ok_button.Click += self.on_ok
        self.cancel_button.Click += self.on_cancel

        self.stepped_radio.CheckedChanged += self.on_option_changed
        self.sloped_radio.CheckedChanged += self.on_option_changed
        self.show_sightlines_check.CheckedChanged += self.on_option_changed
        self.show_eye_points_check.CheckedChanged += self.on_option_changed
        self.show_seats_check.CheckedChanged += self.on_option_changed
        self.show_riser_height_labels_check.CheckedChanged += (
            self.on_option_changed
        )
        self.show_3d_seats_check.CheckedChanged += self.on_option_changed
        self.show_floor_surfaces_check.CheckedChanged += (
            self.on_option_changed
        )

        for text_box in self.all_text_boxes():
            text_box.KeyDown += self.on_text_box_key_down

        main_layout = forms.DynamicLayout()
        main_layout.Spacing = drawing.Size(6, 6)

        main_layout.AddRow(self.make_header("Opening"))
        main_layout.AddRow(self.opening_value_label)
        main_layout.AddRow(self.proscenium_button)
        main_layout.AddRow(self.balcony_button)
        main_layout.AddRow(self.balcony2_button)
        main_layout.AddRow(self.section_interpolation_button)
        main_layout.AddRow(None)

        main_layout.AddRow(self.make_header("Geometry / Seating Inputs"))
        main_layout.AddRow(self.make_field_label("Stage height (mm)"), self.stage_height_box)
        main_layout.AddRow(
            self.make_field_label(
                "Stage point to first platform start (mm)"
            ),
            self.first_distance_box
        )
        main_layout.AddRow(
            self.make_field_label("Step width / row pitch (mm)"),
            self.row_pitch_box
        )
        main_layout.AddRow(
            self.make_field_label("Row groups (e.g. 12,12,12)"),
            self.row_groups_box
        )
        main_layout.AddRow(
            self.make_field_label("Cross-aisle width (mm)"),
            self.aisle_width_box
        )
        main_layout.AddRow(
            self.make_field_label("Aisle stair tread (mm)"),
            self.aisle_stair_tread_box
        )
        main_layout.AddRow(None)

        main_layout.AddRow(self.make_header("3D Seat Modules"))
        main_layout.AddRow(
            self.make_field_label("Seat module width (mm)"),
            self.seat_module_width_box
        )
        main_layout.AddRow(
            self.make_field_label("Seat blocks per row (e.g. 8,16,8)"),
            self.seat_blocks_box
        )
        main_layout.AddRow(
            self.make_field_label("Longitudinal aisle width (mm)"),
            self.longitudinal_aisle_width_box
        )
        main_layout.AddRow(self.total_3d_seat_count_label)
        main_layout.AddRow(
            self.make_field_label("Side floor margin each side (mm)"),
            self.side_floor_margin_box
        )
        main_layout.AddRow(self.show_3d_seats_check)
        main_layout.AddRow(self.show_floor_surfaces_check)
        main_layout.AddRow(None)

        main_layout.AddRow(
            self.make_header("Stage / Audience Transition")
        )
        main_layout.AddRow(
            self.make_field_label("Stage apron projection (mm)"),
            self.apron_projection_box
        )
        main_layout.AddRow(
            self.make_field_label(
                "Orchestra pit depth below audience floor (mm)"
            ),
            self.pit_depth_box
        )
        main_layout.AddRow(None)

        main_layout.AddRow(self.make_header("Sightline Inputs"))
        main_layout.AddRow(
            self.make_field_label("Stage sight target height (mm)"),
            self.stage_sight_z_box
        )
        main_layout.AddRow(
            self.make_field_label("Chair sight point Z (mm)"),
            self.sight_z_box
        )
        main_layout.AddRow(
            self.make_field_label("Sightline clearance (mm)"),
            self.clearance_box
        )
        main_layout.AddRow(
            self.make_field_label("Maximum slope 1 /"),
            self.slope_denominator_box
        )
        main_layout.AddRow(None)

        main_layout.AddRow(self.make_header("Floor Type"))
        floor_row = forms.StackLayout()
        floor_row.Orientation = forms.Orientation.Horizontal
        floor_row.Spacing = 16
        floor_row.Items.Add(self.stepped_radio)
        floor_row.Items.Add(self.sloped_radio)
        main_layout.AddRow(floor_row)
        main_layout.AddRow(None)

        main_layout.AddRow(self.make_header("Preview"))
        main_layout.AddRow(self.show_seats_check)
        main_layout.AddRow(self.show_riser_height_labels_check)
        main_layout.AddRow(self.show_sightlines_check)
        main_layout.AddRow(self.show_eye_points_check)

        preview_button_row = forms.StackLayout()
        preview_button_row.Orientation = forms.Orientation.Horizontal
        preview_button_row.Spacing = 8
        preview_button_row.Items.Add(self.flip_button)
        preview_button_row.Items.Add(self.update_button)
        preview_button_row.Items.Add(self.result_button)
        main_layout.AddRow(preview_button_row)
        main_layout.AddRow(None)

        button_row = forms.StackLayout()
        button_row.Orientation = forms.Orientation.Horizontal
        button_row.HorizontalContentAlignment = (
            forms.HorizontalAlignment.Right
        )
        button_row.Spacing = 8
        button_row.Items.Add(self.ok_button)
        button_row.Items.Add(self.cancel_button)
        main_layout.AddRow(button_row)

        scrollable = forms.Scrollable()
        scrollable.Content = main_layout
        self.Content = scrollable

        self.update_preview(show_error=False)

    def make_header(self, text):
        label = forms.Label()
        label.Text = text
        try:
            label.Font = drawing.Font(
                label.Font.FamilyName,
                label.Font.Size,
                drawing.FontStyle.Bold
            )
        except Exception:
            pass
        return label

    def make_field_label(self, text):
        label = forms.Label()
        label.Text = text
        label.VerticalAlignment = forms.VerticalAlignment.Center
        return label

    def make_text_box(self, key):
        box = forms.TextBox()
        value = self.values.get(key, DEFAULTS[key])
        box.Text = str(value)
        return box

    def all_text_boxes(self):
        return [
            self.stage_height_box,
            self.first_distance_box,
            self.row_pitch_box,
            self.apron_projection_box,
            self.pit_depth_box,
            self.stage_sight_z_box,
            self.sight_z_box,
            self.clearance_box,
            self.row_groups_box,
            self.aisle_width_box,
            self.aisle_stair_tread_box,
            self.seat_module_width_box,
            self.seat_blocks_box,
            self.longitudinal_aisle_width_box,
            self.side_floor_margin_box,
            self.slope_denominator_box,
        ]

    def parse_float(self, text_box, label):
        try:
            text = text_box.Text.strip().replace(",", "")
            return float(text)
        except Exception:
            raise ValueError("{0} 값을 숫자로 입력해 주세요.".format(label))

    def parse_row_groups(self):
        text = self.row_groups_box.Text.strip().replace("，", ",")
        parts = [part.strip() for part in text.split(",")]
        if not parts or any(not part for part in parts):
            raise ValueError(
                "좌석 열 구성은 12,12,12처럼 양의 정수로 입력해 주세요."
            )

        group_counts = []
        for part in parts:
            try:
                numeric_value = float(part)
            except Exception:
                raise ValueError(
                    "좌석 열 구성은 12,12,12처럼 양의 정수로 "
                    "입력해 주세요."
                )
            integer_value = int(numeric_value)
            if (
                integer_value <= 0
                or abs(numeric_value - integer_value) > 1e-8
            ):
                raise ValueError(
                    "각 좌석 그룹의 열 수는 1 이상의 정수여야 합니다."
                )
            group_counts.append(integer_value)

        total_rows = sum(group_counts)
        if total_rows > 500:
            raise ValueError("전체 좌석 열 수는 500 이하이어야 합니다.")

        canonical_text = ",".join(
            str(value) for value in group_counts
        )
        return group_counts, canonical_text

    def parse_seat_blocks(self):
        text = self.seat_blocks_box.Text.strip().replace("，", ",")
        parts = [part.strip() for part in text.split(",")]
        if not parts or any(not part for part in parts):
            raise ValueError(
                "Seat blocks must use positive integers such as 8,16,8."
            )

        block_counts = []
        for part in parts:
            try:
                numeric_value = float(part)
            except Exception:
                raise ValueError(
                    "Seat blocks must use positive integers such as "
                    "8,16,8."
                )
            integer_value = int(numeric_value)
            if (
                integer_value <= 0
                or abs(numeric_value - integer_value) > 1e-8
            ):
                raise ValueError(
                    "Every seat block count must be a positive integer."
                )
            block_counts.append(integer_value)

        if sum(block_counts) > 500:
            raise ValueError("Seats per row must be 500 or fewer.")

        return (
            block_counts,
            ",".join(str(value) for value in block_counts)
        )

    def read_params(self):
        row_group_counts, row_groups = self.parse_row_groups()
        seat_block_counts, seat_blocks = self.parse_seat_blocks()
        params = {
            "stage_height": self.parse_float(
                self.stage_height_box, "무대 높이"
            ),
            "first_row_distance": self.parse_float(
                self.first_distance_box, "첫 번째 단 시작 거리"
            ),
            "stage_apron_projection": self.parse_float(
                self.apron_projection_box, "무대 돌출값"
            ),
            "orchestra_pit_depth": self.parse_float(
                self.pit_depth_box, "오케스트라 피트 Z 깊이"
            ),
            "row_pitch": self.parse_float(
                self.row_pitch_box, "한 단 너비"
            ),
            "stage_sight_point_z": self.parse_float(
                self.stage_sight_z_box, "무대 시야 기준점 높이"
            ),
            "sight_point_z": self.parse_float(
                self.sight_z_box, "좌석 시각점 Z"
            ),
            "sight_clearance": self.parse_float(
                self.clearance_box, "시야 여유값"
            ),
            "row_count": sum(row_group_counts),
            "row_groups": row_groups,
            "row_group_counts": row_group_counts,
            "aisle_width": self.parse_float(
                self.aisle_width_box, "횡단 통로 폭"
            ),
            "aisle_stair_tread_depth": self.parse_float(
                self.aisle_stair_tread_box,
                "통로 계단 디딤판 깊이"
            ),
            "seat_module_width": self.parse_float(
                self.seat_module_width_box,
                "좌석 모듈 폭"
            ),
            "seat_blocks": seat_blocks,
            "seat_block_counts": seat_block_counts,
            "longitudinal_aisle_width": self.parse_float(
                self.longitudinal_aisle_width_box,
                "종방향 통로 폭"
            ),
            "side_floor_margin": self.parse_float(
                self.side_floor_margin_box,
                "좌우 바닥 여유 폭"
            ),
            "max_slope_denominator": self.parse_float(
                self.slope_denominator_box, "최대 경사 분모"
            ),
            "floor_type": (
                "sloped" if self.sloped_radio.Checked else "stepped"
            ),
            "flipped": bool(self.values.get("flipped", False)),
            "show_sightlines": bool(self.show_sightlines_check.Checked),
            "show_eye_points": bool(self.show_eye_points_check.Checked),
            "show_seats": bool(self.show_seats_check.Checked),
            "show_riser_height_labels": bool(
                self.show_riser_height_labels_check.Checked
            ),
            "show_3d_seats": bool(
                self.show_3d_seats_check.Checked
            ),
            "show_floor_surfaces": bool(
                self.show_floor_surfaces_check.Checked
            ),
        }
        for key in PROSCENIUM_PARAM_KEYS:
            params[key] = self.values[key]
        for key in BALCONY_PARAM_KEYS:
            params[key] = self.values[key]
        params["proscenium_settings_version"] = (
            PROSCENIUM_SETTINGS_VERSION
        )
        params["auditorium_defaults_version"] = (
            AUDITORIUM_DEFAULTS_VERSION
        )

        if params["stage_height"] < 0.0:
            raise ValueError("무대 높이는 0 이상이어야 합니다.")
        if params["first_row_distance"] <= 0.0:
            raise ValueError("첫 번째 단 시작 거리는 0보다 커야 합니다.")
        if params["stage_apron_projection"] < 0.0:
            raise ValueError("무대 돌출값은 0 이상이어야 합니다.")
        if (
            params["stage_apron_projection"]
            > params["first_row_distance"]
        ):
            raise ValueError(
                "무대 돌출값은 첫 플랫폼 시작 거리보다 클 수 없습니다."
            )
        if params["orchestra_pit_depth"] < 0.0:
            raise ValueError(
                "오케스트라 피트 Z 깊이는 0 이상이어야 합니다."
            )
        if params["row_pitch"] <= 0.0:
            raise ValueError("한 단 너비는 0보다 커야 합니다.")
        first_sight_x = (
            params["first_row_distance"]
            + params["row_pitch"]
            + CHAIR_SIGHT_POINT_X
        )
        if first_sight_x <= 0.0:
            raise ValueError(
                "첫 번째 SightDot은 무대 시각선 기준점보다 "
                "객석 방향에 있어야 합니다."
            )
        if params["stage_sight_point_z"] < 0.0:
            raise ValueError("무대 시야 기준점 높이는 0 이상이어야 합니다.")
        if params["sight_point_z"] <= 0.0:
            raise ValueError("좌석 시각점 Z는 0보다 커야 합니다.")
        if params["sight_clearance"] < 0.0:
            raise ValueError("시야 여유값은 0 이상이어야 합니다.")
        if params["aisle_width"] < 0.0:
            raise ValueError("횡단 통로 폭은 0 이상이어야 합니다.")
        if params["aisle_stair_tread_depth"] <= 0.0:
            raise ValueError(
                "통로 계단 디딤판 깊이는 0보다 커야 합니다."
            )
        if (
            params["seat_module_width"]
            <= SEAT_SOURCE_ARMREST_WIDTH
        ):
            raise ValueError(
                "Seat module width must be greater than the fixed "
                "80 mm armrest width."
            )
        if params["longitudinal_aisle_width"] < 0.0:
            raise ValueError(
                "Longitudinal aisle width must be zero or greater."
            )
        if params["side_floor_margin"] < 0.0:
            raise ValueError(
                "Side floor margin must be zero or greater."
            )
        total_3d_rows = params["row_count"]
        for tier_index in range(len(BALCONY_TIER_KEY_MAPS)):
            tier_params = normalized_balcony_tier_params(
                params,
                tier_index
            )
            if tier_params["balcony_enabled"]:
                total_3d_rows += int(
                    tier_params["balcony_row_count"]
                )
        total_3d_chairs = (
            total_3d_rows * sum(params["seat_block_counts"])
        )
        if (
            params["show_3d_seats"]
            and total_3d_chairs > MAXIMUM_3D_CHAIR_COUNT
        ):
            raise ValueError(
                "3D chair count exceeds the {0} chair preview limit.".format(
                    MAXIMUM_3D_CHAIR_COUNT
                )
            )
        if params["show_3d_seats"] and self.seat_source is None:
            raise ValueError(
                "AuditoriumSeat.3dm is not available."
            )
        if params["max_slope_denominator"] <= 0.0:
            raise ValueError("최대 경사 분모는 0보다 커야 합니다.")
        for tier_index in range(len(BALCONY_TIER_KEY_MAPS)):
            tier_params = normalized_balcony_tier_params(
                params,
                tier_index
            )
            balcony_row_count = tier_params["balcony_row_count"]
            tier_name = "발코니 {0}".format(tier_index + 1)
            if (
                int(balcony_row_count) != balcony_row_count
                or balcony_row_count < 1
                or balcony_row_count > 500
            ):
                raise ValueError(
                    "{0} 열 수는 1~500 범위의 정수여야 합니다.".format(
                        tier_name
                    )
                )
            actual_row_key = BALCONY_TIER_KEY_MAPS[tier_index][
                "balcony_row_count"
            ]
            params[actual_row_key] = int(balcony_row_count)
            if tier_params["balcony_last_platform_z"] <= 0.0:
                raise ValueError(
                    "{0} 마지막 플랫폼 Z는 0보다 커야 합니다.".format(
                        tier_name
                    )
                )
            if tier_params["balcony_row_pitch"] <= 0.0:
                raise ValueError(
                    "{0} 열 간격은 0보다 커야 합니다.".format(
                        tier_name
                    )
                )
            if tier_params["balcony_railing_t"] < 0.0:
                raise ValueError(
                    "{0} 난간 t는 0 이상이어야 합니다.".format(
                        tier_name
                    )
                )
            if tier_params["balcony_railing_w"] < 0.0:
                raise ValueError(
                    "{0} 난간 w는 0 이상이어야 합니다.".format(
                        tier_name
                    )
                )
            if tier_params["balcony_railing_h"] <= 0.0:
                raise ValueError(
                    "{0} 난간 h는 0보다 커야 합니다.".format(
                        tier_name
                    )
                )

        validate_proscenium_params(params, self.opening_width_mm)
        return params

    def update_section_override_validity(self, params):
        current_signatures = section_solver_signatures(params)
        previous = self.section_solver_signatures

        if previous is not None:
            if current_signatures["stalls"] != previous["stalls"]:
                for key in SECTION_RISE_KEYS:
                    self.section_rise_overrides[key] = None
            elif (
                current_signatures["balcony_1"]
                != previous["balcony_1"]
            ):
                self.section_rise_overrides["balcony_1"] = None
                self.section_rise_overrides["balcony_2"] = None
            elif (
                current_signatures["balcony_2"]
                != previous["balcony_2"]
            ):
                self.section_rise_overrides["balcony_2"] = None

        self.section_solver_signatures = current_signatures

    def update_preview(self, show_error=True):
        try:
            params = self.read_params()
            self.values.update(params)
            self.update_section_override_validity(params)

            preview_data = build_preview_geometry(
                self.stage_data,
                params,
                self.doc,
                self.seat_source,
                dict(self.section_rise_overrides)
            )
            self.preview_data = preview_data
            self.conduit.set_geometry(preview_data)
            total_3d_seats = calculate_total_3d_seat_count(
                params,
                preview_data["balcony_calculations"]
            )
            self.total_3d_seat_count_label.Text = (
                "Total seats: {0:,}".format(total_3d_seats)
            )

            max_slope = preview_data["maximum_actual_slope"]
            if max_slope <= 1e-12:
                slope_text = "0"
            else:
                slope_text = "1 / {0:.2f}".format(1.0 / max_slope)

            section = preview_data["stage_section_dimensions"]
            preview_mode_text = (
                "3D space curves"
                if params["stage_preview_mode"] == "space_3d"
                else "2D central longitudinal section"
            )
            right_level_text = (
                "{0:.1f} / {1:.1f} mm".format(
                    section["right_top_z"],
                    section["right_grid_z"]
                )
                if params["right_stage_enabled"]
                else "Off"
            )
            left_level_text = (
                "{0:.1f} / {1:.1f} mm".format(
                    section["left_top_z"],
                    section["left_grid_z"]
                )
                if params["left_stage_enabled"]
                else "Off"
            )
            rear_level_text = (
                "{0:.1f} / {1:.1f} mm".format(
                    section["rear_top_z"],
                    section["rear_grid_z"]
                )
                if params["rear_stage_enabled"]
                else "Off"
            )
            understage_text = (
                "{0:.1f} / {1:.1f} mm".format(
                    section["understage_bottom_z"],
                    section["understage_floor_z"]
                )
                if params["understage_enabled"]
                else "Off"
            )
            self.result_text = (
                "Total depth: {0:.1f} mm\n"
                "Total rise: {1:.1f} mm\n"
                "Maximum calculated slope: {2}\n"
                "Stage preview: {3}\n"
                "PH: {4:.1f} mm\n"
                "Main top / grid: {5:.1f} / {6:.1f} mm\n"
                "Right top / grid: {7}\n"
                "Left top / grid: {8}\n"
                "Rear top / grid: {9}\n"
                "Understage bottom / equipment floor: {10}\n"
                "Auditorium ceiling: {11:.1f} mm".format(
                    preview_data["total_depth"],
                    preview_data["total_rise"],
                    slope_text,
                    preview_mode_text,
                    section["ph"],
                    section["main_tower_top_z"],
                    section["main_grid_z"],
                    right_level_text,
                    left_level_text,
                    rear_level_text,
                    understage_text,
                    section["auditorium_ceiling_z"]
                )
            )
            self.result_text += (
                "\nStage apron / pit depth below audience floor: "
                "{0:.1f} / {1:.1f} mm".format(
                    params["stage_apron_projection"],
                    params["orchestra_pit_depth"]
                )
            )
            stalls_ceiling_clearance = preview_data[
                "calculation"
            ].get("ceiling_clearance")
            if stalls_ceiling_clearance is not None:
                self.result_text += (
                    "\nStalls minimum chair-to-ceiling clearance: "
                    "{0:.1f} mm"
                ).format(stalls_ceiling_clearance)
            applied_rises = preview_data[
                "applied_section_rise_overrides"
            ]
            applied_rise_parts = []
            for key, label in (
                ("stalls", "Stalls"),
                ("balcony_1", "Balcony 1"),
                ("balcony_2", "Balcony 2"),
            ):
                target = applied_rises.get(key)
                if target is not None:
                    applied_rise_parts.append(
                        "{0}: {1}".format(
                            label,
                            format_section_height_dimension(target)
                        )
                    )
            if applied_rise_parts:
                self.result_text += (
                    "\nInterpolated section rise: "
                    + " / ".join(applied_rise_parts)
                )
            self.result_text += (
                "\nRow groups / total rows: {0} / {1}\n"
                "Internal cross aisles: {2} × {3:.1f} mm\n"
                "Rear cross aisle: 1 × {3:.1f} mm".format(
                    params["row_groups"],
                    params["row_count"],
                    max(len(params["row_group_counts"]) - 1, 0),
                    params["aisle_width"]
                )
            )
            seat_3d_results = preview_data["seat_3d_calculations"]
            if seat_3d_results:
                self.result_text += (
                    "\n3D seat blocks: {0}\n"
                    "Seat module / chair body width: "
                    "{1:.1f} / {2:.1f} mm\n"
                    "Longitudinal aisle width: {3:.1f} mm"
                ).format(
                    params["seat_blocks"],
                    params["seat_module_width"],
                    seat_3d_results[0]["target_chair_width"],
                    params["longitudinal_aisle_width"],
                )
                for tier_3d_result in seat_3d_results:
                    placement_name = tier_3d_result["placement_name"]
                    if placement_name.startswith("Balcony"):
                        tier_label = "Balcony {0}".format(
                            int(placement_name[-2:])
                        )
                    else:
                        tier_label = "Stalls"
                    self.result_text += (
                        "\n{0} 3D chairs / shared armrests / width: "
                        "{1} / {2} / {3:.1f} mm"
                    ).format(
                        tier_label,
                        len(tier_3d_result["chair_placements"]),
                        len(tier_3d_result["armrest_placements"]),
                        tier_3d_result["total_width"]
                    )
            floor_surface_result = preview_data[
                "floor_surface_calculation"
            ]
            if floor_surface_result is not None:
                self.result_text += (
                    "\nFloor surfaces / auditorium floor width: "
                    "{0} / {1:.1f} mm"
                ).format(
                    len(floor_surface_result["bake_breps"]),
                    floor_surface_result["auditorium_floor_width"]
                )
            aisle_indices = preview_data["calculation"][
                "aisle_before_indices"
            ]
            if params["floor_type"] == "stepped" and aisle_indices:
                stair_details = []
                for aisle_number, row_index in enumerate(
                    aisle_indices,
                    1
                ):
                    tread_count = preview_data["calculation"][
                        "aisle_stair_tread_counts"
                    ][row_index]
                    riser_height = preview_data["calculation"][
                        "aisle_stair_riser_heights"
                    ][row_index]
                    stair_run = preview_data["calculation"][
                        "aisle_stair_run_values"
                    ][row_index]
                    stair_details.append(
                        "Aisle {0}: {1} added treads, "
                        "{2:.1f} mm risers, {3:.1f} mm run".format(
                            aisle_number,
                            tread_count,
                            riser_height,
                            stair_run
                        )
                    )
                self.result_text += (
                    "\nAisle stair tread depth: {0:.1f} mm\n{1}".format(
                        params["aisle_stair_tread_depth"],
                        "\n".join(stair_details)
                    )
                )
            elif aisle_indices:
                self.result_text += (
                    "\nAisle stairs: not applied to Sloped floor."
                )

            balcony_results = preview_data["balcony_calculations"]
            for tier_index, balcony_result in enumerate(
                balcony_results
            ):
                if balcony_result is None:
                    continue
                tier_params = normalized_balcony_tier_params(
                    params,
                    tier_index
                )
                self.result_text += (
                    "\nBalcony {0} rows / calculated maximum: {1} / {2}\n"
                    "Balcony {0} last platform Z: {3:.1f} mm\n"
                    "Balcony {0} maximum rake angle: {4:.2f}°\n"
                    "Balcony {0} railing t / w / h: "
                    "{5:.1f} / {6:.1f} / {7:.1f} mm\n"
                    "Reference h / sightline-allowable h: "
                    "{8:.1f} / {9:.1f} mm\n"
                    "Lower-limit / ceiling clearance: "
                    "{10:.1f} / {11:.1f} mm".format(
                        tier_index + 1,
                        balcony_result["row_count"],
                        balcony_result["maximum_rows"],
                        tier_params["balcony_last_platform_z"],
                        balcony_result["maximum_angle_degrees"],
                        tier_params["balcony_railing_t"],
                        tier_params["balcony_railing_w"],
                        tier_params["balcony_railing_h"],
                        balcony_result["standard_railing_h"],
                        balcony_result["allowable_railing_h"],
                        balcony_result[
                            "minimum_lower_limit_clearance"
                        ],
                        balcony_result["ceiling_clearance"]
                    )
                )

            warning_messages = []
            slope_violation_rows = preview_data[
                "slope_violation_rows"
            ]
            if slope_violation_rows:
                warning_messages.append((
                    "Slope limit exceeded at rows: {0}\n"
                    "Exceeded floor curves and chairs are red."
                ).format(
                    ", ".join(
                        str(row) for row in slope_violation_rows
                    )
                ))
            sightline_violation_rows = preview_data[
                "sightline_violation_rows"
            ]
            if sightline_violation_rows:
                warning_messages.append((
                    "Sightline clearance is insufficient at rows: {0}."
                ).format(
                    ", ".join(
                        str(row) for row in sightline_violation_rows
                    )
                ))
            ceiling_violation_rows = preview_data[
                "ceiling_violation_rows"
            ]
            if ceiling_violation_rows:
                warning_messages.append((
                    "Stalls chairs exceed the auditorium ceiling at "
                    "rows: {0}."
                ).format(
                    ", ".join(
                        str(row) for row in ceiling_violation_rows
                    )
                ))
            for tier_index, balcony_result in enumerate(
                balcony_results
            ):
                if balcony_result is None:
                    continue
                tier_label = "Balcony {0}".format(tier_index + 1)
                if balcony_result["angle_violation"]:
                    warning_messages.append(
                        tier_label + " rake angle exceeds 35°."
                    )
                if balcony_result.get("sightline_violation", False):
                    warning_messages.append(
                        tier_label
                        + " has insufficient interpolated sightline "
                        "clearance."
                    )
                if balcony_result["railing_sight_collision"]:
                    warning_messages.append(
                        tier_label + " first-row sightline intersects "
                        "the railing top."
                    )
                if balcony_result["front_limit_violation"]:
                    warning_messages.append(
                        tier_label
                        + " rows exceed the calculated front limit."
                    )
                if balcony_result["lower_limit_violation"]:
                    warning_messages.append(
                        tier_label
                        + " is below the calculated lower limit."
                    )
                if balcony_result["ceiling_violation"]:
                    warning_messages.append(
                        tier_label + " chairs exceed the ceiling line."
                    )
            if preview_data["balcony2_dependency_warning"]:
                warning_messages.append(
                    "Balcony 2 requires a valid Balcony 1."
                )
            self.warning_text = (
                "\n".join(warning_messages)
                if warning_messages
                else "No section validation warning."
            )

            self.doc.Views.Redraw()
            return True

        except Exception as error:
            self.warning_text = str(error)
            self.total_3d_seat_count_label.Text = "Total seats: -"
            self.conduit.clear()
            self.doc.Views.Redraw()

            if show_error:
                forms.MessageBox.Show(
                    self,
                    str(error),
                    "Auditorium Section Generator",
                    forms.MessageBoxButtons.OK,
                    forms.MessageBoxType.Warning
                )
            return False

    def on_text_box_key_down(self, sender, event_args):
        if event_args.Key == forms.Keys.Enter:
            self.update_preview(show_error=True)
            event_args.Handled = True

    def on_option_changed(self, sender, event_args):
        self.aisle_stair_tread_box.Enabled = bool(
            self.stepped_radio.Checked
        )
        self.update_preview(show_error=False)

    def on_flip(self, sender, event_args):
        self.values["flipped"] = not bool(
            self.values.get("flipped", False)
        )
        self.update_preview(show_error=True)

    def on_proscenium_live_preview(self, values):
        self.values.update(values)
        return self.update_preview(show_error=False)

    def on_edit_proscenium(self, sender, event_args):
        original_values = {
            key: self.values[key]
            for key in PROSCENIUM_PARAM_KEYS
        }
        dialog = ProsceniumSettingsDialog(
            self.values,
            self.opening_width_mm,
            self.opening_height_mm,
            self.on_proscenium_live_preview
        )
        dialog.ShowModal(self)

        if not dialog.accepted:
            self.values.update(original_values)
            self.update_preview(show_error=False)
            return

        self.values.update(dialog.values)
        self.update_preview(show_error=True)

    def on_balcony_live_preview(self, tier_index, values):
        self.values.update(values)
        if not self.update_preview(show_error=False):
            return None
        return self.preview_data["balcony_calculations"][tier_index]

    def on_edit_balcony(self, sender, event_args):
        self.open_balcony_settings(0)

    def on_edit_balcony2(self, sender, event_args):
        self.open_balcony_settings(1)

    def section_interpolation_rows(self):
        rows = []
        stalls_result = self.preview_data["calculation"]
        stalls_rise = (
            stalls_result["base_z_values"][-1]
            - stalls_result["base_z_values"][0]
        )
        rows.append({
            "key": "stalls",
            "label": "Stalls",
            "current_rise": stalls_rise,
            "editable": (
                len(stalls_result["base_z_values"]) >= 2
                and stalls_rise > 1e-12
            ),
            "has_aisle_stairs": bool(
                stalls_result["aisle_before_indices"]
                and self.values["floor_type"] == "stepped"
            ),
        })

        for tier_index, balcony_result in enumerate(
            self.preview_data["balcony_calculations"]
        ):
            if not balcony_result_is_displayable(balcony_result):
                continue
            tier_rise = (
                balcony_result["base_z_values"][-1]
                - balcony_result["base_z_values"][0]
            )
            rows.append({
                "key": "balcony_{0}".format(tier_index + 1),
                "label": "Balcony {0}".format(tier_index + 1),
                "current_rise": tier_rise,
                "editable": (
                    len(balcony_result["base_z_values"]) >= 2
                    and tier_rise > 1e-12
                ),
            })

        return rows

    def on_section_dimension_interpolation(self, sender, event_args):
        if not self.update_preview(show_error=True):
            return

        dialog = SectionDimensionInterpolationDialog(
            self.section_interpolation_rows(),
            dict(self.section_rise_overrides)
        )
        dialog.ShowModal(self)
        if not dialog.accepted:
            return

        original_overrides = dict(self.section_rise_overrides)
        self.section_rise_overrides = dict(dialog.overrides)
        if not self.update_preview(show_error=True):
            self.section_rise_overrides = original_overrides
            self.update_preview(show_error=False)

    def open_balcony_settings(self, tier_index):
        if not self.update_preview(show_error=True):
            return

        if tier_index == 0:
            lower_result = self.preview_data["calculation"]
            first_limit_x = self.values["first_row_distance"]
        else:
            lower_result = self.preview_data["balcony_calculations"][0]
            if (
                not balcony_result_is_displayable(lower_result)
            ):
                forms.MessageBox.Show(
                    self,
                    "발코니 2를 설정하려면 발코니 1이 먼저 "
                    "정상적으로 생성되어야 합니다.",
                    "발코니 2 설정",
                    forms.MessageBoxButtons.OK,
                    forms.MessageBoxType.Warning
                )
                return
            first_limit_x = lower_result["railing_front_x"]

        tier_keys = tuple(
            BALCONY_TIER_KEY_MAPS[tier_index].values()
        )
        original_values = {
            key: self.values[key]
            for key in tier_keys
        }
        original_overrides = dict(self.section_rise_overrides)
        original_signatures = dict(self.section_solver_signatures)
        dialog = BalconySettingsDialog(
            self.values,
            lower_result,
            first_limit_x,
            self.opening_height_mm,
            self.preview_data["calculation"][
                "base_z_values"
            ][-1],
            tier_index,
            self.on_balcony_live_preview
        )
        dialog.ShowModal(self)

        if not dialog.accepted:
            self.values.update(original_values)
            self.section_rise_overrides = original_overrides
            self.section_solver_signatures = original_signatures
            self.update_preview(show_error=False)
            return

        self.values.update(dialog.external_values())
        self.update_preview(show_error=True)

    def on_update(self, sender, event_args):
        self.update_preview(show_error=True)

    def on_show_result(self, sender, event_args):
        if not self.update_preview(show_error=True):
            return

        dialog = CalculatedResultDialog(
            self.result_text,
            self.warning_text
        )
        dialog.ShowModal(self)

    def on_ok(self, sender, event_args):
        if not self.update_preview(show_error=True):
            return

        params = self.read_params()
        sc.sticky[STICKY_KEY] = dict(params)
        self.accepted = True
        self.Close(True)

    def on_cancel(self, sender, event_args):
        self.accepted = False
        self.Close(False)

    def disable_preview(self):
        self.conduit.Enabled = False
        self.conduit.clear()
        self.doc.Views.Redraw()


def create_attributes(doc, color, name):
    attributes = rd.ObjectAttributes()
    attributes.LayerIndex = doc.Layers.CurrentLayerIndex
    attributes.ColorSource = rd.ObjectColorSource.ColorFromObject
    attributes.ObjectColor = color
    attributes.Name = name
    return attributes


def ensure_seat_instance_definition(doc, seat_source, component_key):
    component = seat_source[component_key]
    component_label = (
        "ChairBody" if component_key == "chair" else "Armrest"
    )
    definition_name = "Elephant_AuditoriumSeat_{0}_{1}".format(
        component_label,
        seat_source["signature"]
    )
    existing = doc.InstanceDefinitions.Find(definition_name, True)
    if existing is not None:
        return existing.Index

    color = (
        PREVIEW_3D_CHAIR
        if component_key == "chair"
        else PREVIEW_3D_ARMREST
    )
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
        definition_indices = {
            "chair": ensure_seat_instance_definition(
                doc,
                seat_source,
                "chair"
            ),
            "armrest": ensure_seat_instance_definition(
                doc,
                seat_source,
                "armrest"
            ),
        }
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
    try:
        valid_ids = [object_id for object_id in added_ids if object_id]
        if valid_ids:
            doc.Groups.Add(valid_ids)
    except Exception:
        pass

    doc.Views.Redraw()
    return added_ids


def select_opening_curve():
    getter = ric.GetObject()
    getter.SetCommandPrompt(
        "프로시니엄 개구부를 나타내는 수직 직사각형 커브를 선택하세요"
    )
    getter.GeometryFilter = rd.ObjectType.Curve
    getter.SubObjectSelect = False
    getter.EnablePreSelect(True, True)
    getter.Get()

    if getter.CommandResult() != rc.Result.Success:
        return None

    reference = getter.Object(0)
    curve = reference.Curve()
    if curve is None:
        return None

    return curve.DuplicateCurve()


def show_dialog_semi_modal(dialog, doc):
    try:
        Rhino.UI.EtoExtensions.ShowSemiModal(
            dialog,
            doc,
            Rhino.UI.RhinoEtoApp.MainWindow
        )
    except Exception:
        dialog.ShowModal(Rhino.UI.RhinoEtoApp.MainWindow)


def main():
    doc = Rhino.RhinoDoc.ActiveDoc
    if doc is None:
        return

    opening_curve = select_opening_curve()
    if opening_curve is None:
        return

    try:
        stage_data = analyze_opening_rectangle(opening_curve, doc)
    except Exception as error:
        Rhino.UI.Dialogs.ShowMessageBox(
            str(error),
            "Auditorium Section Generator"
        )
        return

    seat_source = None
    try:
        seat_source = load_auditorium_seat_source()
    except Exception as error:
        Rhino.UI.Dialogs.ShowMessageBox(
            (
                "The 3D seat source could not be loaded.\n\n{0}\n\n"
                "The section generator will remain available without "
                "3D seat modules."
            ).format(error),
            "Auditorium 3D Seat Source"
        )

    dialog = AuditoriumDialog(stage_data, doc, seat_source)

    try:
        show_dialog_semi_modal(dialog, doc)
    finally:
        dialog.disable_preview()

    if not dialog.accepted or dialog.preview_data is None:
        return

    bake_preview(dialog.preview_data, doc)


if __name__ == "__main__":
    main()
