# -*- coding: utf-8 -*-
"""Main Eto dialog for the auditorium section generator."""

import math

import Rhino
import Rhino.Input.Custom as ric
import scriptcontext as sc
import Eto.Forms as forms
import Eto.Drawing as drawing
from Rhino.UI import EtoExtensions

from .balcony_height_reference import stalls_height_reference_z
from .auditorium_boundary import normalize_boundary_curve
from .constants import (
    BALCONY_TIER_KEY_MAPS,
    CHAIR_SIGHT_POINT_X,
    MAX_BALCONY_ROW_COUNT,
)
from .calculations.sections import (
    balcony_result_is_displayable,
    is_finite_number,
    normalized_balcony_tier_params,
    section_solver_signatures,
    standard_balcony_railing_height,
)
from .calculations.seating import (
    MAXIMUM_3D_CHAIR_COUNT,
    seat_blocks_have_auto,
    tier_row_override_fit_issues,
)
from .calculations.stage import (
    DEFAULT_OPENING_HEIGHT,
    MIN_OPENING_HEIGHT,
    STAGE_TYPE_OPEN_PODIUM,
    STAGE_TYPE_PROSCENIUM,
    calculated_proscenium_defaults,
    is_proscenium_stage,
    validate_proscenium_params,
    validate_stage_reference_dimensions,
)
from .formatting import format_section_height_dimension
from .document_baking import bake_plan_preview
from .preview_conduit import AuditoriumPreviewConduit
from .preview_geometry import build_preview_geometry
from .plan_preview_geometry import build_plan_preview_geometry
from .radial_layout import normalize_plan_layout_radius
from .rhino_primitives import unit_scale_from_mm
from .seat_preview_geometry import (
    SEAT_CURVE_PREVIEW_THRESHOLD,
    SEAT_SOURCE_ARMREST_WIDTH,
)
from .section_interpolation_constants import (
    SECTION_RISE_KEYS,
    SEATING_RISE_KEYS,
)
from .balcony_settings_dialog import BalconySettingsDialog
from .proscenium_settings_dialog import (
    PROSCENIUM_PARAM_KEYS,
    ProsceniumSettingsDialog,
)
from .section_result_dialogs import (
    CalculatedResultDialog,
    SectionDimensionInterpolationDialog,
)
from .seat_layout_adjustment_dialog import (
    SeatLayoutAdjustmentDialog,
    clone_plain_data,
    parse_row_rule,
)


STICKY_KEY = "Elephant_AuditoriumSectionGenerator_v1"

# Row-level seat edits are kept beside the normal dialog defaults in
# ``scriptcontext.sticky``.  They are never restored automatically: a saved
# layout is only offered as a row-by-row template when the editor first opens.
SEAT_ROW_OVERRIDE_STATE_KEY = "_seat_row_override_state"
SEAT_ROW_OVERRIDE_STATE_VERSION = 2

PROSCENIUM_SETTINGS_VERSION = 3

AUDITORIUM_DEFAULTS_VERSION = 10

DEFAULT_FIRST_PLATFORM_START_DISTANCE = 7000.0

CHAIR_SIGHT_POINT_Z = 1123.991949

BALCONY_PARAM_KEYS = tuple(
    actual_key
    for key_map in BALCONY_TIER_KEY_MAPS
    for actual_key in key_map.values()
)

DEFAULTS = {
    "opening_width": 0.0,
    "opening_height": DEFAULT_OPENING_HEIGHT,
    "stage_type": STAGE_TYPE_PROSCENIUM,
    "stage_height": 1100.0,
    "auditorium_ceiling_clear_height": 5000.0,
    "stalls_rear_world_z": None,
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
    "balcony_longitudinal_offset": 0.0,
    # Stored as height above the effective stalls rear platform.
    "balcony_last_platform_z": 5000.0,
    "balcony_row_count": 1,
    "balcony_row_pitch": 1100.0,
    "balcony_railing_t": 250.0,
    "balcony_railing_w": 530.0,
    "balcony_railing_h": 750.0,
    "balcony_settings_version": 0,
    "balcony2_enabled": False,
    "balcony2_longitudinal_offset": 0.0,
    # Balcony 2 uses the same stalls-rear datum as Balcony 1.
    "balcony2_last_platform_z": 10000.0,
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
    "plan_layout_radius": 0.0,
}

FORMULA_STAGE_DIMENSION_KEYS = (
    "main_stage_width",
    "main_stage_depth",
    "main_stage_height",
    "right_stage_width",
    "right_stage_depth",
    "right_stage_height",
    "left_stage_width",
    "left_stage_depth",
    "left_stage_height",
    "rear_stage_width",
    "rear_stage_depth",
    "rear_stage_height",
    "understage_depth",
)


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
        self.plan_conduit = AuditoriumPreviewConduit()
        self.plan_conduit.Enabled = True
        self.plan_preview_enabled = False
        self.plan_preview_data = None
        self.plan_preview_error = None
        self.last_preview_params = None
        self.seat_row_overrides = {
            "stalls": {},
            "balcony_1": {},
            "balcony_2": {},
        }
        self.seat_layout_active_row = None
        self.seat_layout_saved_prompt_shown = False
        self.seat_row_overrides_user_modified = False

        mm_scale = unit_scale_from_mm(doc)
        self.reference_width_mm = (
            stage_data.get(
                "reference_width",
                stage_data["opening_width"],
            )
            / mm_scale
        )
        self.opening_width_mm = self.reference_width_mm
        self.opening_height_mm = DEFAULT_OPENING_HEIGHT

        saved = sc.sticky.get(STICKY_KEY, {})
        if not isinstance(saved, dict):
            saved = {}
        else:
            saved = dict(saved)
        self.saved_seat_row_override_state = clone_plain_data(
            saved.pop(SEAT_ROW_OVERRIDE_STATE_KEY, None)
        )
        self.formula_reference_width_mm = float(
            saved.get("opening_width", self.reference_width_mm)
        )
        self.formula_reference_height_mm = float(
            saved.get("opening_height", DEFAULT_OPENING_HEIGHT)
        )
        self.values = dict(DEFAULTS)
        self.values.update(
            calculated_proscenium_defaults(
                self.opening_width_mm,
                self.opening_height_mm
            )
        )
        self.values.update(saved)
        saved_auditorium_defaults_version = saved.get(
            "auditorium_defaults_version",
            0,
        )
        # A World-Z target belongs to the current model/datum selection.  Do
        # not carry it into another command run through application sticky.
        self.values["stalls_rear_world_z"] = None
        # PW belongs to the newly picked datum line and must never be restored
        # from a previous command. PH and the remaining settings may be sticky.
        self.values["opening_width"] = self.reference_width_mm
        if saved_auditorium_defaults_version < 8:
            self.values["opening_height"] = DEFAULT_OPENING_HEIGHT
            self.values["stage_type"] = STAGE_TYPE_PROSCENIUM
        self.opening_width_mm = float(self.values["opening_width"])
        self.opening_height_mm = float(self.values["opening_height"])
        if "row_groups" not in saved:
            saved_row_count = saved.get(
                "row_count",
                DEFAULTS["row_count"]
            )
            self.values["row_groups"] = str(int(saved_row_count))
        if saved_auditorium_defaults_version < 2:
            self.values["stage_height"] = DEFAULTS["stage_height"]
            self.values["first_row_distance"] = DEFAULTS[
                "first_row_distance"
            ]
            self.values["row_pitch"] = DEFAULTS["row_pitch"]
        if saved_auditorium_defaults_version < 3:
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
        if saved_auditorium_defaults_version < 4:
            self.values["show_3d_seats"] = False
        if saved_auditorium_defaults_version < 5:
            self.values["side_floor_margin"] = DEFAULTS[
                "side_floor_margin"
            ]
            self.values["show_floor_surfaces"] = DEFAULTS[
                "show_floor_surfaces"
            ]
        if saved_auditorium_defaults_version < 6:
            self.values["show_riser_height_labels"] = DEFAULTS[
                "show_riser_height_labels"
            ]
        if saved_auditorium_defaults_version < 7:
            self.values["plan_layout_radius"] = DEFAULTS[
                "plan_layout_radius"
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
            self.values["balcony_row_pitch"] = self.values[
                "row_pitch"
            ]
            self.values["balcony_railing_h"] = (
                standard_balcony_railing_height(
                    self.values["balcony_railing_t"]
                )
            )
        if saved.get("balcony2_settings_version", 0) < 1:
            self.values["balcony2_row_pitch"] = self.values[
                "row_pitch"
            ]
            self.values["balcony2_railing_h"] = (
                standard_balcony_railing_height(
                    self.values["balcony2_railing_t"]
                )
            )
        if saved.get("auditorium_defaults_version", 0) < 10:
            # Version 10 changes these stored values from stage-relative
            # absolute Z values to offsets above the effective stalls rear.
            # Resetting once is safer than interpreting an old absolute Z as
            # a new offset.
            self.values["auditorium_ceiling_clear_height"] = 5000.0
            self.values["balcony_last_platform_z"] = 5000.0
            self.values["balcony2_last_platform_z"] = 10000.0

        self.Title = "Elephant Tools - Auditorium Section Generator"
        self.ClientSize = drawing.Size(520, 680)
        self.Padding = drawing.Padding(12)
        self.Resizable = True

        self.opening_width_box = self.make_text_box("opening_width")
        self.opening_height_box = self.make_text_box("opening_height")
        self.stage_height_box = self.make_text_box("stage_height")
        self.auditorium_ceiling_clear_height_box = self.make_text_box(
            "auditorium_ceiling_clear_height"
        )
        self.stalls_rear_world_z_box = self.make_text_box(
            "stalls_rear_world_z"
        )
        self.balcony_height_box = self.make_text_box(
            "balcony_last_platform_z"
        )
        self.balcony2_height_box = self.make_text_box(
            "balcony2_last_platform_z"
        )
        self.balcony_height_box.Width = 92
        self.balcony2_height_box.Width = 92
        self.first_distance_box = self.make_text_box("first_row_distance")
        self.plan_layout_radius_box = self.make_text_box(
            "plan_layout_radius"
        )
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

        datum_point = stage_data.get(
            "audience_datum_point",
            stage_data["stage_point"],
        )
        self.opening_value_label.Text = (
            "Reference line: {0:.1f} mm / "
            "floor datum Z: {1:.1f} mm".format(
                self.reference_width_mm,
                datum_point.Z / mm_scale,
            )
        )

        self.proscenium_stage_radio = forms.RadioButton()
        self.proscenium_stage_radio.Text = "Proscenium"
        self.open_podium_radio = forms.RadioButton(
            self.proscenium_stage_radio
        )
        self.open_podium_radio.Text = "Open / Podium"
        if (
            self.values.get("stage_type", STAGE_TYPE_PROSCENIUM)
            == STAGE_TYPE_OPEN_PODIUM
        ):
            self.open_podium_radio.Checked = True
        else:
            self.proscenium_stage_radio.Checked = True

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

        self.balcony_max_button = forms.Button()
        self.balcony_max_button.Text = "Max 적용"
        self.balcony_max_button.Width = 96
        self.balcony_max_button.Enabled = False

        self.balcony2_max_button = forms.Button()
        self.balcony2_max_button.Text = "Max 적용"
        self.balcony2_max_button.Width = 96
        self.balcony2_max_button.Enabled = False

        self.section_interpolation_button = forms.Button()
        self.section_interpolation_button.Text = (
            "Section Dimension Control"
        )

        self.section_10mm_up_button = forms.Button()
        self.section_10mm_up_button.Text = "10 mm Up"
        self.section_10mm_up_button.Width = 96

        self.section_reset_button = forms.Button()
        self.section_reset_button.Text = "Reset"
        self.section_reset_button.Width = 96

        self.boundary_status_label = forms.Label()
        self.boundary_status_label.VerticalAlignment = (
            forms.VerticalAlignment.Center
        )
        self.boundary_select_button = forms.Button()
        self.boundary_select_button.Width = 112
        self.boundary_clear_button = forms.Button()
        self.boundary_clear_button.Text = "Clear Boundary"
        self.boundary_clear_button.Width = 112

        self.pick_stalls_rear_world_z_button = forms.Button()
        self.pick_stalls_rear_world_z_button.Text = "Pick Z"

        self.update_button = forms.Button()
        self.update_button.Text = "Update Preview"

        self.plan_preview_button = forms.Button()
        self.plan_preview_button.Text = "Plan Preview"
        self.plan_preview_button.Width = 112
        self.plan_preview_button.Enabled = self.plan_preview_is_available()
        if not self.plan_preview_button.Enabled:
            self.plan_preview_button.ToolTip = str(
                (
                    self.seat_source.get("plan_error")
                    if self.seat_source is not None
                    else None
                )
                or (
                    "AuditoriumSeat.3dm requires TT_ChairBody_Plan and "
                    "TT_Armrest_Plan."
                )
            )

        self.bake_plan_preview_button = forms.Button()
        self.bake_plan_preview_button.Text = "Bake Plan Preview"
        self.bake_plan_preview_button.Width = 140
        self.bake_plan_preview_button.Enabled = False
        self.bake_plan_preview_button.ToolTip = (
            "Bake the visible Plan Preview curves to the current layer. "
            "Screen labels remain preview-only."
        )

        self.seat_layout_adjustment_button = forms.Button()
        self.seat_layout_adjustment_button.Text = (
            "Seat Layout Adjustment"
        )
        self.seat_layout_adjustment_button.Width = 178
        self.seat_layout_adjustment_button.Enabled = (
            self.plan_preview_is_available()
        )
        if not self.seat_layout_adjustment_button.Enabled:
            self.seat_layout_adjustment_button.ToolTip = (
                self.plan_preview_button.ToolTip
            )

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
        self.balcony_max_button.Click += self.on_apply_balcony_max
        self.balcony2_max_button.Click += self.on_apply_balcony2_max
        self.section_interpolation_button.Click += (
            self.on_section_dimension_interpolation
        )
        self.section_10mm_up_button.Click += self.on_section_10mm_up
        self.section_reset_button.Click += self.on_section_reset
        self.boundary_select_button.Click += (
            self.on_select_auditorium_boundary
        )
        self.boundary_clear_button.Click += (
            self.on_clear_auditorium_boundary
        )
        self.pick_stalls_rear_world_z_button.Click += (
            self.on_pick_stalls_rear_world_z
        )
        self.update_button.Click += self.on_update
        self.plan_preview_button.Click += self.on_plan_preview
        self.bake_plan_preview_button.Click += (
            self.on_bake_plan_preview
        )
        self.seat_layout_adjustment_button.Click += (
            self.on_seat_layout_adjustment
        )
        self.result_button.Click += self.on_show_result
        self.ok_button.Click += self.on_ok
        self.cancel_button.Click += self.on_cancel

        self.proscenium_stage_radio.CheckedChanged += (
            self.on_option_changed
        )
        self.open_podium_radio.CheckedChanged += self.on_option_changed
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
        self.opening_width_box.LostFocus += (
            self.on_opening_box_lost_focus
        )
        self.opening_height_box.LostFocus += (
            self.on_opening_box_lost_focus
        )
        self.update_boundary_status()

        main_layout = forms.DynamicLayout()
        main_layout.Spacing = drawing.Size(6, 6)

        main_layout.AddRow(self.make_header("Opening"))
        main_layout.AddRow(self.opening_value_label)
        main_layout.AddRow(
            self.make_field_label("Reference width PW (mm)"),
            self.opening_width_box
        )
        main_layout.AddRow(
            self.make_field_label(
                "Reference height PH (min. {0:.0f} mm)"
                .format(MIN_OPENING_HEIGHT)
            ),
            self.opening_height_box
        )
        stage_type_row = forms.StackLayout()
        stage_type_row.Orientation = forms.Orientation.Horizontal
        stage_type_row.Spacing = 16
        stage_type_row.Items.Add(
            forms.StackLayoutItem(self.proscenium_stage_radio)
        )
        stage_type_row.Items.Add(
            forms.StackLayoutItem(self.open_podium_radio)
        )
        main_layout.AddRow(
            self.make_field_label("Stage type"),
            stage_type_row
        )
        boundary_control_row = forms.StackLayout()
        boundary_control_row.Orientation = forms.Orientation.Horizontal
        boundary_control_row.Spacing = 6
        boundary_control_row.Items.Add(
            forms.StackLayoutItem(self.boundary_status_label, True)
        )
        boundary_control_row.Items.Add(
            forms.StackLayoutItem(self.boundary_select_button)
        )
        boundary_control_row.Items.Add(
            forms.StackLayoutItem(self.boundary_clear_button)
        )
        main_layout.AddRow(boundary_control_row)
        main_layout.AddRow(self.proscenium_button)

        balcony1_quick_row = forms.StackLayout()
        balcony1_quick_row.Orientation = forms.Orientation.Horizontal
        balcony1_quick_row.Spacing = 6
        balcony1_quick_row.Items.Add(
            forms.StackLayoutItem(self.balcony_button, True)
        )
        balcony1_quick_row.Items.Add(
            forms.StackLayoutItem(self.balcony_height_box)
        )
        balcony1_quick_row.Items.Add(
            forms.StackLayoutItem(self.balcony_max_button)
        )
        main_layout.AddRow(balcony1_quick_row)

        balcony2_quick_row = forms.StackLayout()
        balcony2_quick_row.Orientation = forms.Orientation.Horizontal
        balcony2_quick_row.Spacing = 6
        balcony2_quick_row.Items.Add(
            forms.StackLayoutItem(self.balcony2_button, True)
        )
        balcony2_quick_row.Items.Add(
            forms.StackLayoutItem(self.balcony2_height_box)
        )
        balcony2_quick_row.Items.Add(
            forms.StackLayoutItem(self.balcony2_max_button)
        )
        main_layout.AddRow(balcony2_quick_row)

        section_quick_row = forms.StackLayout()
        section_quick_row.Orientation = forms.Orientation.Horizontal
        section_quick_row.Spacing = 6
        section_quick_row.Items.Add(
            forms.StackLayoutItem(
                self.section_interpolation_button,
                True
            )
        )
        section_quick_row.Items.Add(
            forms.StackLayoutItem(self.section_10mm_up_button)
        )
        section_quick_row.Items.Add(
            forms.StackLayoutItem(self.section_reset_button)
        )
        main_layout.AddRow(section_quick_row)
        main_layout.AddRow(None)

        main_layout.AddRow(self.make_header("Geometry / Seating Inputs"))
        main_layout.AddRow(self.make_field_label("Stage height (mm)"), self.stage_height_box)
        main_layout.AddRow(
            self.make_field_label(
                "Ceiling clear height above highest rear platform (mm)"
            ),
            self.auditorium_ceiling_clear_height_box
        )
        stalls_rear_world_z_row = forms.StackLayout()
        stalls_rear_world_z_row.Orientation = (
            forms.Orientation.Horizontal
        )
        stalls_rear_world_z_row.Spacing = 6
        stalls_rear_world_z_row.Items.Add(
            forms.StackLayoutItem(self.stalls_rear_world_z_box, True)
        )
        stalls_rear_world_z_row.Items.Add(
            forms.StackLayoutItem(self.pick_stalls_rear_world_z_button)
        )
        main_layout.AddRow(
            self.make_field_label(
                "Stalls rear World Z (mm, blank = datum)"
            ),
            stalls_rear_world_z_row
        )
        main_layout.AddRow(
            self.make_field_label(
                "Stage/reference arc to first platform start (mm)"
            ),
            self.first_distance_box
        )
        main_layout.AddRow(
            self.make_field_label(
                "Plan radius (0 = rectangular, min. PW / 2)"
            ),
            self.plan_layout_radius_box
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
            self.make_field_label(
                "Seat blocks per row (e.g. 8,16,8 or 8,a,8)"
            ),
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
        floor_row.Items.Add(
            forms.StackLayoutItem(self.stepped_radio)
        )
        floor_row.Items.Add(
            forms.StackLayoutItem(self.sloped_radio)
        )
        main_layout.AddRow(floor_row)
        main_layout.AddRow(None)

        main_layout.AddRow(self.make_header("Preview"))
        main_layout.AddRow(self.show_seats_check)
        main_layout.AddRow(self.show_riser_height_labels_check)
        main_layout.AddRow(self.show_sightlines_check)
        main_layout.AddRow(self.show_eye_points_check)
        plan_button_row = forms.StackLayout()
        plan_button_row.Orientation = forms.Orientation.Horizontal
        plan_button_row.Spacing = 8
        plan_button_row.Items.Add(
            forms.StackLayoutItem(self.plan_preview_button)
        )
        plan_button_row.Items.Add(
            forms.StackLayoutItem(self.bake_plan_preview_button)
        )
        plan_button_row.Items.Add(
            forms.StackLayoutItem(self.seat_layout_adjustment_button)
        )
        main_layout.AddRow(plan_button_row)

        preview_button_row = forms.StackLayout()
        preview_button_row.Orientation = forms.Orientation.Horizontal
        preview_button_row.Spacing = 8
        preview_button_row.Items.Add(
            forms.StackLayoutItem(self.flip_button)
        )
        preview_button_row.Items.Add(
            forms.StackLayoutItem(self.update_button)
        )
        preview_button_row.Items.Add(
            forms.StackLayoutItem(self.result_button)
        )
        main_layout.AddRow(preview_button_row)
        main_layout.AddRow(None)

        button_row = forms.StackLayout()
        button_row.Orientation = forms.Orientation.Horizontal
        button_row.HorizontalContentAlignment = (
            forms.HorizontalAlignment.Right
        )
        button_row.Spacing = 8
        button_row.Items.Add(forms.StackLayoutItem(self.ok_button))
        button_row.Items.Add(forms.StackLayoutItem(self.cancel_button))
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
        box.Text = "" if value is None else str(value)
        return box

    def stage_values_for_opening(
        self,
        opening_width_mm,
        opening_height_mm
    ):
        """
        Update only dimensions that still match their previous formula value.

        This keeps formula-derived defaults responsive to edited PW/PH while
        preserving every stage dimension the user has customized.
        """
        previous_defaults = calculated_proscenium_defaults(
            self.formula_reference_width_mm,
            self.formula_reference_height_mm
        )
        new_defaults = calculated_proscenium_defaults(
            opening_width_mm,
            opening_height_mm
        )
        adjusted = dict(self.values)
        for key in FORMULA_STAGE_DIMENSION_KEYS:
            try:
                current_value = float(adjusted[key])
                previous_value = float(previous_defaults[key])
            except Exception:
                continue
            if abs(current_value - previous_value) <= 1e-8:
                adjusted[key] = new_defaults[key]
        return adjusted

    def all_text_boxes(self):
        return [
            self.opening_width_box,
            self.opening_height_box,
            self.stage_height_box,
            self.auditorium_ceiling_clear_height_box,
            self.stalls_rear_world_z_box,
            self.balcony_height_box,
            self.balcony2_height_box,
            self.first_distance_box,
            self.plan_layout_radius_box,
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

    def parse_optional_float(self, text_box, label):
        text = text_box.Text.strip().replace(",", "")
        if not text:
            return None
        try:
            value = float(text)
        except Exception:
            raise ValueError(
                "{0} 값을 숫자로 입력하거나 비워 주세요.".format(label)
            )
        if not is_finite_number(value):
            raise ValueError(
                "{0} 값은 유한한 숫자여야 합니다.".format(label)
            )
        return value

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
                "Seat blocks must use positive integers or 'a', such "
                "as 8,16,8 or 8,a,8."
            )

        block_counts = []
        for part in parts:
            if part.lower() == "a":
                block_counts.append("a")
                continue
            try:
                numeric_value = float(part)
            except Exception:
                raise ValueError(
                    "Seat blocks must use positive integers or 'a', "
                    "such as 8,16,8 or 8,a,8."
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

        fixed_seat_count = sum(
            value
            for value in block_counts
            if value != "a"
        )
        if fixed_seat_count > 500:
            raise ValueError(
                "Fixed seats per row must be 500 or fewer."
            )

        return (
            block_counts,
            ",".join(str(value) for value in block_counts)
        )

    def read_params(self):
        row_group_counts, row_groups = self.parse_row_groups()
        seat_block_counts, seat_blocks = self.parse_seat_blocks()
        opening_width_mm = self.parse_float(
            self.opening_width_box,
            "Reference width PW"
        )
        opening_height_mm = self.parse_float(
            self.opening_height_box,
            "Reference height PH"
        )
        validate_stage_reference_dimensions(
            opening_width_mm,
            opening_height_mm
        )
        stage_type = (
            STAGE_TYPE_OPEN_PODIUM
            if self.open_podium_radio.Checked
            else STAGE_TYPE_PROSCENIUM
        )
        stage_values = self.stage_values_for_opening(
            opening_width_mm,
            opening_height_mm
        )
        entered_plan_radius = self.parse_float(
            self.plan_layout_radius_box,
            "평면 원호 반지름"
        )
        effective_plan_radius = normalize_plan_layout_radius(
            entered_plan_radius,
            opening_width_mm
        )
        if (
            entered_plan_radius > 0.0
            and effective_plan_radius <= 0.0
        ):
            self.plan_layout_radius_box.Text = "0"
        if (
            seat_blocks_have_auto(seat_block_counts)
            and effective_plan_radius <= 0.0
            and self.stage_data.get("auditorium_boundary_curve") is None
        ):
            raise ValueError(
                "Automatic seat blocks ('a') require a custom auditorium "
                "boundary or a valid Radial plan radius of at least PW / 2."
            )
        balcony_height = self.parse_float(
            self.balcony_height_box,
            "발코니 1 기준 높이"
        )
        balcony2_height = self.parse_float(
            self.balcony2_height_box,
            "발코니 2 기준 높이"
        )
        if not is_finite_number(balcony_height) or balcony_height <= 0.0:
            raise ValueError(
                "발코니 1 기준 높이는 0보다 큰 유한한 숫자여야 합니다."
            )
        if (
            not is_finite_number(balcony2_height)
            or balcony2_height <= 0.0
        ):
            raise ValueError(
                "발코니 2 기준 높이는 0보다 큰 유한한 숫자여야 합니다."
            )
        self.values["balcony_last_platform_z"] = balcony_height
        self.values["balcony2_last_platform_z"] = balcony2_height
        params = {
            "opening_width": opening_width_mm,
            "opening_height": opening_height_mm,
            "stage_type": stage_type,
            "stage_height": self.parse_float(
                self.stage_height_box, "무대 높이"
            ),
            "auditorium_ceiling_clear_height": self.parse_float(
                self.auditorium_ceiling_clear_height_box,
                "천장 순높이"
            ),
            "stalls_rear_world_z": self.parse_optional_float(
                self.stalls_rear_world_z_box,
                "하부 객석 마지막 단 World Z"
            ),
            "first_row_distance": self.parse_float(
                self.first_distance_box, "첫 번째 단 시작 거리"
            ),
            "plan_layout_radius": effective_plan_radius,
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
            params[key] = stage_values[key]
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
        if (
            not is_finite_number(
                params["auditorium_ceiling_clear_height"]
            )
            or params["auditorium_ceiling_clear_height"] <= 0.0
        ):
            raise ValueError("천장 순높이는 0보다 커야 합니다.")
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
        if (
            not seat_blocks_have_auto(params["seat_block_counts"])
            and not self.has_seat_row_overrides()
        ):
            total_3d_chairs = (
                total_3d_rows
                * sum(
                    int(value)
                    for value in params["seat_block_counts"]
                )
            )
            if (
                params["show_3d_seats"]
                and total_3d_chairs > MAXIMUM_3D_CHAIR_COUNT
                and self.stage_data.get("auditorium_boundary_curve") is None
            ):
                raise ValueError(
                    "3D chair count exceeds the {0} chair preview "
                    "limit.".format(MAXIMUM_3D_CHAIR_COUNT)
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
                or balcony_row_count > MAX_BALCONY_ROW_COUNT
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
            balcony_offset = tier_params[
                "balcony_longitudinal_offset"
            ]
            if not is_finite_number(balcony_offset):
                raise ValueError(
                    "{0} longitudinal offset must be a finite "
                    "number.".format(tier_name)
                )
            actual_offset_key = BALCONY_TIER_KEY_MAPS[tier_index][
                "balcony_longitudinal_offset"
            ]
            params[actual_offset_key] = float(balcony_offset)
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

        validate_proscenium_params(params, opening_width_mm)
        self.opening_width_mm = opening_width_mm
        self.opening_height_mm = opening_height_mm
        self.formula_reference_width_mm = opening_width_mm
        self.formula_reference_height_mm = opening_height_mm
        return params

    def has_seat_row_overrides(self):
        return any(
            bool(self.seat_row_overrides.get(tier_key))
            for tier_key in ("stalls", "balcony_1", "balcony_2")
        )

    def normalized_seat_row_overrides(self, params, source=None):
        """Return valid overrides for the current rows and block topology."""
        expected_block_count = len(params.get("seat_block_counts", []))
        result = {
            "stalls": {},
            "balcony_1": {},
            "balcony_2": {},
        }
        row_limits = {
            "stalls": int(params.get("row_count", 0)),
            "balcony_1": int(params.get("balcony_row_count", 0)),
            "balcony_2": int(params.get("balcony2_row_count", 0)),
        }
        if source is None:
            source = self.seat_row_overrides
        if not isinstance(source, dict):
            return result

        for tier_key in result:
            tier_source = source.get(tier_key, {})
            if not isinstance(tier_source, dict):
                continue
            for raw_row_index, raw_values in tier_source.items():
                try:
                    row_index = int(raw_row_index)
                except Exception:
                    continue
                if (
                    row_index < 0
                    or row_index >= row_limits[tier_key]
                ):
                    continue

                # Re-parse persisted values rather than trusting sticky data.
                # ``[]`` is the explicit empty-row rule; every non-empty rule
                # must keep the current aisle/block topology.
                try:
                    if raw_values is None:
                        continue
                    if hasattr(raw_values, "strip"):
                        values = parse_row_rule(
                            raw_values,
                            expected_block_count,
                        )
                    else:
                        values = list(raw_values)
                        if values:
                            values = parse_row_rule(
                                ",".join(str(value) for value in values),
                                expected_block_count,
                            )
                        else:
                            values = []
                except Exception:
                    continue
                result[tier_key][row_index] = clone_plain_data(values)
        return result

    def saved_seat_row_override_template(self):
        """Return the stored manual layout template, if it has any rows."""
        state = self.saved_seat_row_override_state
        if not isinstance(state, dict):
            return None
        overrides = state.get("overrides")
        if not isinstance(overrides, dict):
            return None
        for tier_key in ("stalls", "balcony_1", "balcony_2"):
            tier = overrides.get(tier_key, {})
            if isinstance(tier, dict) and tier:
                return clone_plain_data(overrides)
        return None

    def seat_row_override_entry_count(self, overrides):
        if not isinstance(overrides, dict):
            return 0
        return sum(
            len(overrides.get(tier_key, {}))
            for tier_key in ("stalls", "balcony_1", "balcony_2")
            if isinstance(overrides.get(tier_key, {}), dict)
        )

    def update_section_override_validity(self, params):
        current_signatures = section_solver_signatures(params)
        previous = self.section_solver_signatures

        if previous is not None:
            if current_signatures["stalls"] != previous["stalls"]:
                for key in SEATING_RISE_KEYS:
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
            candidate_seat_row_overrides = (
                self.normalized_seat_row_overrides(
                    params
                )
            )
            params["seat_row_overrides"] = clone_plain_data(
                candidate_seat_row_overrides
            )
            self.values.update(params)
            self.update_section_override_validity(params)

            preview_data = build_preview_geometry(
                self.stage_data,
                params,
                self.doc,
                self.seat_source,
                dict(self.section_rise_overrides)
            )
            self.update_balcony_max_buttons(preview_data)
            self.conduit.set_geometry(preview_data)
            if not self.refresh_plan_preview(
                params,
                preview_data,
                show_error=False,
            ):
                raise ValueError(
                    self.plan_preview_error
                    or "Plan Preview could not be updated."
                )
            total_3d_seats = preview_data["total_seat_count"]
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
            datum_offset = params["stage_height"]
            right_level_text = (
                "{0:.1f} / {1:.1f} mm".format(
                    datum_offset + section["right_top_z"],
                    datum_offset + section["right_grid_z"]
                )
                if params["right_stage_enabled"]
                else "Off"
            )
            left_level_text = (
                "{0:.1f} / {1:.1f} mm".format(
                    datum_offset + section["left_top_z"],
                    datum_offset + section["left_grid_z"]
                )
                if params["left_stage_enabled"]
                else "Off"
            )
            rear_level_text = (
                "{0:.1f} / {1:.1f} mm".format(
                    datum_offset + section["rear_top_z"],
                    datum_offset + section["rear_grid_z"]
                )
                if params["rear_stage_enabled"]
                else "Off"
            )
            understage_text = (
                "{0:.1f} / {1:.1f} mm".format(
                    datum_offset + section["understage_bottom_z"],
                    datum_offset + section["understage_floor_z"]
                )
                if params["understage_enabled"]
                else "Off"
            )
            self.result_text = (
                "Total depth: {0:.1f} mm\n"
                "Total rise: {1:.1f} mm\n"
                "Maximum calculated slope: {2}\n"
                "Stage preview: {3}\n"
                "Stage type: {4}\n"
                "PW / PH: {5:.1f} / {6:.1f} mm\n"
                "Stage floor elevation from audience datum: {7:.1f} mm\n"
                "Upper sight reference elevation: {8:.1f} mm\n"
                "Understage bottom / equipment floor elevation: {9}\n"
                "Auditorium ceiling elevation: {10:.1f} mm".format(
                    preview_data["total_depth"],
                    preview_data["total_rise"],
                    slope_text,
                    preview_mode_text,
                    (
                        "Proscenium"
                        if is_proscenium_stage(params)
                        else "Open / Podium"
                    ),
                    params["opening_width"],
                    section["ph"],
                    datum_offset,
                    datum_offset + section["ph"],
                    understage_text,
                    datum_offset + section["auditorium_ceiling_z"]
                )
            )
            vertical_placement = preview_data["vertical_placement"]
            self.result_text += (
                "\nStalls rear World Z: {0:.1f} mm"
            ).format(
                vertical_placement["actual_rear_world_z_mm"]
            )
            if vertical_placement["override_applied"]:
                self.result_text += (
                    " / auditorium vertical shift {0:+.1f} mm"
                ).format(
                    vertical_placement["vertical_offset_mm"]
                )
            if is_proscenium_stage(params):
                self.result_text += (
                    "\nMain top / grid elevation: {0:.1f} / {1:.1f} mm"
                    "\nRight top / grid elevation: {2}"
                    "\nLeft top / grid elevation: {3}"
                    "\nRear top / grid elevation: {4}"
                ).format(
                    datum_offset + section["main_tower_top_z"],
                    datum_offset + section["main_grid_z"],
                    right_level_text,
                    left_level_text,
                    rear_level_text,
                )
            else:
                self.result_text += (
                    "\nProscenium vertical envelope: Off"
                    "\nMain platform width / depth: {0:.1f} / {1:.1f} mm"
                ).format(
                    params["main_stage_width"],
                    params["main_stage_depth"],
                )
            layout_context = preview_data["plan_layout"]
            if layout_context["mode"] == "radial":
                self.result_text += (
                    "\nPlan layout: Radial / radius {0:.1f} mm / "
                    "included angle {1:.2f} deg"
                ).format(
                    layout_context["radius"],
                    math.degrees(
                        layout_context["half_angle"] * 2.0
                    )
                )
            else:
                self.result_text += "\nPlan layout: Rectangular"
            if preview_data.get("auditorium_boundary") is not None:
                self.result_text += " / Custom boundary"
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
            ceiling_calculation = preview_data["auditorium_ceiling"]
            self.result_text += (
                "\nRear platform-to-ceiling height ({0}): {1:.1f} mm"
            ).format(
                ceiling_calculation["reference_tier_label"],
                ceiling_calculation["actual_clear_height"]
            )
            if ceiling_calculation["clamped_to_opening_top"]:
                self.result_text += (
                    " / clamped to opening top"
                )
            self.result_text += (
                "\nBalcony longitudinal offsets "
                "(+ rear / - stage): B1 {0:.1f} / B2 {1:.1f} mm"
            ).format(
                params["balcony_longitudinal_offset"],
                params["balcony2_longitudinal_offset"]
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
                if (
                    preview_data["seat_3d_preview_mode"]
                    == "curve_blocks"
                ):
                    self.result_text += (
                        "\n3D seat preview: Source curve blocks "
                        "(more than {0:,} seats)"
                    ).format(SEAT_CURVE_PREVIEW_THRESHOLD)
                else:
                    self.result_text += "\n3D seat preview: Shaded"
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
                        balcony_result["base_z_values"][-1],
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
            for fit_issue in preview_data.get(
                "seat_row_override_fit_issues",
                [],
            ):
                warning_messages.append(
                    self.seat_row_fit_issue_message(fit_issue)
                )
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

            # Commit session override pruning and the new preview only after
            # the complete auditorium/result/Plan update succeeds.
            self.seat_row_overrides = candidate_seat_row_overrides
            self.preview_data = preview_data
            self.last_preview_params = clone_plain_data(params)
            self.doc.Views.Redraw()
            return True

        except Exception as error:
            self.warning_text = str(error)
            self.update_balcony_max_buttons(None)
            self.total_3d_seat_count_label.Text = "Total seats: -"
            self.conduit.clear()
            self.plan_preview_data = None
            self.plan_conduit.clear()
            self.update_plan_bake_button()
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

    def update_boundary_status(self):
        has_boundary = (
            self.stage_data.get("auditorium_boundary_curve") is not None
        )
        self.boundary_status_label.Text = (
            "Plan boundary: Selected"
            if has_boundary
            else "Plan boundary: None"
        )
        self.boundary_select_button.Text = (
            "Change Boundary" if has_boundary else "Select Boundary"
        )
        self.boundary_clear_button.Enabled = has_boundary

    def pick_auditorium_boundary(self, sender, event_args):
        try:
            getter = ric.GetObject()
            getter.SetCommandPrompt(
                "프리뷰에 적용할 닫힌 평면 객석 경계 커브를 선택하세요"
            )
            getter.GeometryFilter = Rhino.DocObjects.ObjectType.Curve
            try:
                getter.AcceptNothing(True)
            except Exception:
                pass
            result = getter.Get()
            if result != Rhino.Input.GetResult.Object:
                return

            object_reference = getter.Object(0)
            curve = (
                None
                if object_reference is None
                else object_reference.Curve()
            )
            if curve is None:
                return

            datum_point = self.stage_data.get("audience_datum_point")
            if datum_point is None:
                datum_point = self.stage_data["stage_point"]
            tolerance = max(
                float(self.doc.ModelAbsoluteTolerance),
                1e-6,
            )
            boundary_curve = normalize_boundary_curve(
                curve,
                datum_point,
                tolerance,
            )
            self.stage_data["auditorium_boundary_curve"] = (
                boundary_curve
            )
            self.update_boundary_status()
            self.update_preview(show_error=True)
        except Exception as error:
            forms.MessageBox.Show(
                self,
                str(error),
                "Auditorium Boundary",
                forms.MessageBoxButtons.OK,
                forms.MessageBoxType.Warning
            )

    def on_select_auditorium_boundary(self, sender, event_args):
        EtoExtensions.PushPickButton(
            self,
            self.pick_auditorium_boundary
        )

    def on_clear_auditorium_boundary(self, sender, event_args):
        self.stage_data.pop("auditorium_boundary_curve", None)
        self.update_boundary_status()
        self.update_preview(show_error=True)

    def pick_stalls_rear_world_z(self, sender, event_args):
        try:
            getter = ric.GetPoint()
            getter.SetCommandPrompt(
                "하부 객석 마지막 단에 맞출 기준 Z점을 지정하세요"
            )
            try:
                getter.PermitObjectSnap(True)
            except Exception:
                pass
            result = getter.Get()
            if result != Rhino.Input.GetResult.Point:
                return
            mm_scale = unit_scale_from_mm(self.doc)
            picked_z_mm = getter.Point().Z / mm_scale
            self.stalls_rear_world_z_box.Text = "{0:.3f}".format(
                picked_z_mm
            )
            self.update_preview(show_error=True)
        except Exception as error:
            forms.MessageBox.Show(
                self,
                str(error),
                "Stalls Rear World Z",
                forms.MessageBoxButtons.OK,
                forms.MessageBoxType.Warning
            )

    def on_pick_stalls_rear_world_z(self, sender, event_args):
        EtoExtensions.PushPickButton(
            self,
            self.pick_stalls_rear_world_z
        )

    def on_opening_box_lost_focus(self, sender, event_args):
        self.update_preview(show_error=False)

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

    def plan_preview_is_available(self):
        return bool(
            self.seat_source is not None
            and self.seat_source.get("chair_plan") is not None
            and self.seat_source.get("armrest_plan") is not None
        )

    def update_plan_bake_button(self):
        plan_curves = (
            self.plan_preview_data.get("preview_curves", [])
            if self.plan_preview_data is not None
            else []
        )
        self.bake_plan_preview_button.Enabled = bool(
            self.plan_preview_enabled and plan_curves
        )

    def refresh_plan_preview(
        self,
        params,
        preview_data,
        show_error=False,
    ):
        if not self.plan_preview_enabled:
            self.plan_preview_data = None
            self.plan_preview_error = None
            self.plan_conduit.clear()
            self.update_plan_bake_button()
            return True

        try:
            if not self.plan_preview_is_available():
                raise ValueError(
                    "AuditoriumSeat.3dm requires TT_ChairBody_Plan and "
                    "TT_Armrest_Plan for Plan Preview."
                )
            plan_preview_data = build_plan_preview_geometry(
                preview_data,
                params,
                self.doc,
                self.seat_source,
            )
            self.plan_preview_data = plan_preview_data
            self.plan_preview_error = None
            self.plan_conduit.set_geometry(plan_preview_data)
            self.update_plan_bake_button()
            return True
        except Exception as error:
            self.plan_preview_data = None
            self.plan_preview_error = str(error)
            self.plan_conduit.clear()
            self.plan_preview_enabled = False
            self.plan_preview_button.Text = "Plan Preview"
            self.update_plan_bake_button()
            if show_error:
                forms.MessageBox.Show(
                    self,
                    str(error),
                    "Auditorium Plan Preview",
                    forms.MessageBoxButtons.OK,
                    forms.MessageBoxType.Warning,
                )
            return False

    def on_plan_preview(self, sender, event_args):
        if self.plan_preview_enabled:
            self.plan_preview_enabled = False
            self.plan_preview_button.Text = "Plan Preview"
            self.plan_preview_data = None
            self.plan_preview_error = None
            self.plan_conduit.clear()
            self.update_plan_bake_button()
            self.doc.Views.Redraw()
            return

        if not self.plan_preview_is_available():
            forms.MessageBox.Show(
                self,
                (
                    "AuditoriumSeat.3dm requires TT_ChairBody_Plan and "
                    "TT_Armrest_Plan."
                ),
                "Auditorium Plan Preview",
                forms.MessageBoxButtons.OK,
                forms.MessageBoxType.Warning,
            )
            return

        self.plan_preview_enabled = True
        self.plan_preview_button.Text = "Hide Plan Preview"
        if not self.update_preview(show_error=True):
            self.plan_preview_enabled = False
            self.plan_preview_button.Text = "Plan Preview"
            self.plan_preview_data = None
            self.plan_conduit.clear()
            self.update_plan_bake_button()
            self.doc.Views.Redraw()
            return
        if self.plan_preview_error is not None:
            self.plan_preview_enabled = False
            self.plan_preview_button.Text = "Plan Preview"
            self.plan_preview_data = None
            self.plan_conduit.clear()
            self.update_plan_bake_button()
            self.doc.Views.Redraw()

    def on_bake_plan_preview(self, sender, event_args):
        try:
            if not self.plan_preview_enabled:
                raise ValueError(
                    "Turn on Plan Preview before using Bake Plan Preview."
                )
            if not self.update_preview(show_error=True):
                return
            if self.plan_preview_data is None:
                raise ValueError("A valid Plan Preview is required for Bake.")

            added_ids = bake_plan_preview(
                self.plan_preview_data,
                self.doc,
            )
            if not added_ids:
                raise ValueError(
                    "Plan Preview did not contain any curves to Bake."
                )
            Rhino.RhinoApp.WriteLine(
                (
                    "ElephantTools: {0:,} Plan Preview curves baked "
                    "to the current layer."
                ).format(len(added_ids))
            )
        except Exception as error:
            forms.MessageBox.Show(
                self,
                str(error),
                "Auditorium Plan Preview Bake",
                forms.MessageBoxButtons.OK,
                forms.MessageBoxType.Warning,
            )

    def seat_layouts_from_plan_preview(self, plan_preview_data):
        layouts = {
            "stalls": [],
            "balcony_1": [],
            "balcony_2": [],
        }
        metadata = plan_preview_data.get("tier_metadata", [])
        for slot, tier_key in enumerate(
            ("stalls", "balcony_1", "balcony_2")
        ):
            tier_metadata = (
                metadata[slot]
                if slot < len(metadata)
                else None
            )
            if tier_metadata is not None:
                layouts[tier_key] = clone_plain_data(
                    tier_metadata.get("row_layouts", [])
                )
        return layouts

    def seat_row_fit_issue_message(self, issue):
        tier_labels = {
            "stalls": "Stalls",
            "balcony_1": "Balcony 1",
            "balcony_2": "Balcony 2",
        }
        return (
            "{0} Row {1} fixed layout no longer fits the current "
            "boundary: rule {2}, placed {3}. Adjust the row before OK."
        ).format(
            tier_labels.get(issue.get("tier_key"), "Seating"),
            int(issue.get("row_index", 0)) + 1,
            issue.get("rule_values", []),
            issue.get("placed_block_counts", []),
        )

    def validate_draft_row_fit(self, plan_preview_data, overrides):
        """Reject fixed row rules that a custom boundary clips."""
        layouts_by_tier = self.seat_layouts_from_plan_preview(
            plan_preview_data
        )
        tier_labels = {
            "stalls": "Stalls",
            "balcony_1": "Balcony 1",
            "balcony_2": "Balcony 2",
        }
        issues = tier_row_override_fit_issues(
            layouts_by_tier,
            overrides,
            2,
        )
        changed_issues = []
        for issue in issues:
            tier_key = issue["tier_key"]
            row_index = issue["row_index"]
            draft_tier = overrides.get(tier_key, {})
            committed_tier = self.seat_row_overrides.get(
                tier_key,
                {},
            )
            draft_has_row = row_index in draft_tier
            committed_has_row = row_index in committed_tier
            draft_rule = (
                list(draft_tier[row_index])
                if draft_has_row
                else None
            )
            committed_rule = (
                list(committed_tier[row_index])
                if committed_has_row
                else None
            )
            if (
                draft_has_row != committed_has_row
                or draft_rule != committed_rule
            ):
                changed_issues.append(issue)
        if changed_issues:
            issue = changed_issues[0]
            tier_key = issue["tier_key"]
            raise ValueError(
                "{0} Row {1} does not fit inside the current "
                "auditorium boundary. Requested {2}; available "
                "placement {3}.".format(
                    tier_labels[tier_key],
                    issue["row_index"] + 1,
                    issue["resolved_block_counts"],
                    issue["placed_block_counts"],
                )
            )

    def build_plan_preview_for_row_overrides(
        self,
        overrides,
        validate_fit=True,
        highlighted_row=None,
    ):
        if self.preview_data is None or self.last_preview_params is None:
            raise ValueError(
                "Update the auditorium preview before editing seat rows."
            )
        if not self.plan_preview_is_available():
            raise ValueError(
                "AuditoriumSeat.3dm requires TT_ChairBody_Plan and "
                "TT_Armrest_Plan."
            )

        draft_overrides = clone_plain_data(overrides)
        params = clone_plain_data(self.last_preview_params)
        params["seat_row_overrides"] = clone_plain_data(
            draft_overrides
        )
        plan_preview_data = build_plan_preview_geometry(
            self.preview_data,
            params,
            self.doc,
            self.seat_source,
            draft_overrides,
            highlighted_row,
        )
        if validate_fit:
            self.validate_draft_row_fit(
                plan_preview_data,
                draft_overrides,
            )
        return plan_preview_data

    def on_draft_seat_layout_preview(self, overrides):
        plan_preview_data = self.build_plan_preview_for_row_overrides(
            overrides,
            highlighted_row=self.seat_layout_active_row,
        )
        self.plan_preview_enabled = True
        self.plan_preview_button.Text = "Hide Plan Preview"
        self.plan_preview_data = plan_preview_data
        self.plan_preview_error = None
        self.plan_conduit.set_geometry(plan_preview_data)
        self.update_plan_bake_button()
        self.doc.Views.Redraw()
        return self.seat_layouts_from_plan_preview(plan_preview_data)

    def on_seat_layout_active_row_changed(self, active_key):
        self.seat_layout_active_row = active_key
        if active_key is None or not self.plan_preview_enabled:
            return
        plan_preview_data = self.build_plan_preview_for_row_overrides(
            self.seat_row_overrides,
            validate_fit=False,
            highlighted_row=active_key,
        )
        self.plan_preview_data = plan_preview_data
        self.plan_preview_error = None
        self.plan_conduit.set_geometry(plan_preview_data)
        self.update_plan_bake_button()
        self.doc.Views.Redraw()
        return self.seat_layouts_from_plan_preview(plan_preview_data)

    def restore_committed_seat_plan_preview(self):
        if not self.plan_preview_enabled:
            return
        plan_preview_data = self.build_plan_preview_for_row_overrides(
            self.seat_row_overrides,
            validate_fit=False,
        )
        self.plan_preview_data = plan_preview_data
        self.plan_preview_error = None
        self.plan_conduit.set_geometry(plan_preview_data)
        self.update_plan_bake_button()
        self.doc.Views.Redraw()

    def on_apply_seat_layout_overrides(self, overrides):
        # Revalidate against the current plan immediately before committing.
        self.on_draft_seat_layout_preview(overrides)

        previous_overrides = clone_plain_data(self.seat_row_overrides)
        overrides_changed = previous_overrides != overrides
        plan_was_enabled = self.plan_preview_enabled
        self.seat_row_overrides = clone_plain_data(overrides)
        if not self.update_preview(show_error=False):
            apply_error = self.warning_text
            self.seat_row_overrides = previous_overrides
            self.plan_preview_enabled = plan_was_enabled
            self.plan_preview_button.Text = (
                "Hide Plan Preview"
                if plan_was_enabled
                else "Plan Preview"
            )
            self.update_preview(show_error=False)
            # The row editor intentionally remains in draft mode after a
            # failed full update.  Rebuild that draft plan as well so its
            # active row stays highlighted instead of being replaced by the
            # unhighlighted committed plan from the rollback above.
            if plan_was_enabled:
                try:
                    self.on_draft_seat_layout_preview(overrides)
                except Exception:
                    # Preserve the original full-update error.  The editor's
                    # Cancel action can still restore the committed preview.
                    pass
            raise ValueError(apply_error)

        if overrides_changed:
            self.seat_row_overrides_user_modified = True
        return clone_plain_data(
            self.preview_data.get("seat_row_layouts", {})
        )

    def plan_compatible_saved_seat_row_overrides(self, saved_overrides):
        """Keep only saved rows that can be used by the current plan."""
        params = clone_plain_data(self.last_preview_params or {})
        candidate = self.normalized_seat_row_overrides(
            params,
            saved_overrides,
        )

        # A disabled tier has no current rows to receive a saved rule.
        if not bool(params.get("balcony_enabled", False)):
            candidate["balcony_1"] = {}
        if not bool(params.get("balcony2_enabled", False)):
            candidate["balcony_2"] = {}

        # ``a`` requires a boundary or a valid radial layout.  A saved auto
        # block that lacks either context is incompatible for this run only.
        supports_auto = (
            self.stage_data.get("auditorium_boundary_curve") is not None
            or float(params.get("plan_layout_radius", 0.0)) > 0.0
        )
        if not supports_auto:
            for tier_key in candidate:
                for row_index, values in list(
                    candidate[tier_key].items()
                ):
                    if "a" in values:
                        del candidate[tier_key][row_index]

        if not self.has_any_seat_row_overrides(candidate):
            return candidate

        try:
            plan_data = self.build_plan_preview_for_row_overrides(
                candidate,
                validate_fit=False,
            )
        except Exception:
            # If one stale row prevents a bulk preview, retry row by row so
            # unrelated valid rows can still be loaded.
            accepted = {
                "stalls": {},
                "balcony_1": {},
                "balcony_2": {},
            }
            for tier_key in ("stalls", "balcony_1", "balcony_2"):
                for row_index in sorted(candidate[tier_key]):
                    trial = clone_plain_data(accepted)
                    trial[tier_key][row_index] = clone_plain_data(
                        candidate[tier_key][row_index]
                    )
                    try:
                        trial_plan = (
                            self.build_plan_preview_for_row_overrides(
                                trial,
                                validate_fit=False,
                            )
                        )
                        issues = tier_row_override_fit_issues(
                            self.seat_layouts_from_plan_preview(trial_plan),
                            trial,
                            2,
                        )
                        if issues:
                            continue
                    except Exception:
                        continue
                    accepted = trial
            return accepted

        issues = tier_row_override_fit_issues(
            self.seat_layouts_from_plan_preview(plan_data),
            candidate,
            2,
        )
        for issue in issues:
            tier_key = issue.get("tier_key")
            row_index = int(issue.get("row_index", -1))
            if tier_key in candidate:
                candidate[tier_key].pop(row_index, None)
        return candidate

    def has_any_seat_row_overrides(self, overrides):
        if not isinstance(overrides, dict):
            return False
        return any(
            bool(overrides.get(tier_key))
            for tier_key in ("stalls", "balcony_1", "balcony_2")
        )

    def load_saved_seat_row_override_template(self, saved_overrides):
        """Apply compatible saved rows and leave all other rows automatic."""
        requested_count = self.seat_row_override_entry_count(
            saved_overrides
        )
        compatible = self.plan_compatible_saved_seat_row_overrides(
            saved_overrides
        )
        loaded_count = self.seat_row_override_entry_count(compatible)

        previous_overrides = clone_plain_data(self.seat_row_overrides)
        self.seat_row_overrides = clone_plain_data(compatible)
        if not self.update_preview(show_error=False):
            load_error = self.warning_text
            self.seat_row_overrides = previous_overrides
            self.update_preview(show_error=False)
            raise ValueError(load_error)

        return loaded_count, max(0, requested_count - loaded_count)

    def offer_saved_seat_row_override_template(self):
        """Ask once per command whether to load the stored row template."""
        if self.seat_layout_saved_prompt_shown:
            return
        saved_overrides = self.saved_seat_row_override_template()
        if saved_overrides is None:
            return

        self.seat_layout_saved_prompt_shown = True
        result = forms.MessageBox.Show(
            self,
            (
                "A saved row configuration is available.\n\n"
                "Load its compatible rows? Rows that do not match the "
                "current tiers, row count, block topology, radial/boundary "
                "conditions, or available space will remain automatic."
            ),
            "Load Saved Auditorium Row Configuration",
            forms.MessageBoxButtons.YesNo,
            forms.MessageBoxType.Question,
        )
        if result != forms.DialogResult.Yes:
            return

        try:
            loaded_count, skipped_count = (
                self.load_saved_seat_row_override_template(
                    saved_overrides
                )
            )
        except Exception as error:
            forms.MessageBox.Show(
                self,
                (
                    "The saved configuration could not be loaded. "
                    "The current automatic layout was kept.\n\n{0}"
                ).format(error),
                "Load Saved Auditorium Row Configuration",
                forms.MessageBoxButtons.OK,
                forms.MessageBoxType.Warning,
            )
            return

        if skipped_count > 0 or loaded_count == 0:
            forms.MessageBox.Show(
                self,
                (
                    "Loaded {0} compatible row(s).\n"
                    "Kept {1} incompatible row(s) automatic."
                ).format(loaded_count, skipped_count),
                "Load Saved Auditorium Row Configuration",
                forms.MessageBoxButtons.OK,
                (
                    forms.MessageBoxType.Information
                    if loaded_count > 0
                    else forms.MessageBoxType.Warning
                ),
            )

    def on_seat_layout_adjustment(self, sender, event_args):
        if not self.plan_preview_is_available():
            forms.MessageBox.Show(
                self,
                (
                    "AuditoriumSeat.3dm requires TT_ChairBody_Plan and "
                    "TT_Armrest_Plan."
                ),
                "Auditorium Seat Layout Adjustment",
                forms.MessageBoxButtons.OK,
                forms.MessageBoxType.Warning,
            )
            return
        if not self.update_preview(show_error=True):
            return

        self.plan_preview_enabled = True
        self.plan_preview_button.Text = "Hide Plan Preview"
        if not self.refresh_plan_preview(
            self.last_preview_params,
            self.preview_data,
            show_error=True,
        ):
            return

        self.offer_saved_seat_row_override_template()

        dialog = SeatLayoutAdjustmentDialog(
            self.preview_data.get("seat_row_layouts", {}),
            clone_plain_data(self.seat_row_overrides),
            self.on_draft_seat_layout_preview,
            self.on_apply_seat_layout_overrides,
            self.restore_committed_seat_plan_preview,
            self.on_seat_layout_active_row_changed,
        )
        try:
            # Rhino semi-modal dialogs keep the command context alive while
            # still allowing viewport orbit, pan, and zoom for inspecting the
            # Draft Plan Preview.
            EtoExtensions.ShowSemiModal(
                dialog,
                self.doc,
                self,
            )
        finally:
            self.seat_layout_active_row = None
            if self.plan_preview_enabled:
                try:
                    self.restore_committed_seat_plan_preview()
                except Exception as error:
                    self.plan_preview_data = None
                    self.plan_preview_error = str(error)
                    self.plan_conduit.clear()
                    self.update_plan_bake_button()
                    self.doc.Views.Redraw()

    def on_proscenium_live_preview(self, values):
        self.values.update(values)
        return self.update_preview(show_error=False)

    def on_edit_proscenium(self, sender, event_args):
        if not self.update_preview(show_error=True):
            return
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

    def sync_balcony_height_boxes_from_values(self):
        self.balcony_height_box.Text = str(
            self.values["balcony_last_platform_z"]
        )
        self.balcony2_height_box.Text = str(
            self.values["balcony2_last_platform_z"]
        )

    def update_balcony_max_buttons(self, preview_data):
        results = (
            preview_data.get("balcony_calculations", [None, None])
            if preview_data is not None
            else [None, None]
        )
        states = []
        for tier_index in range(2):
            result = (
                results[tier_index]
                if tier_index < len(results)
                else None
            )
            if not balcony_result_is_displayable(result):
                states.append(("Max 적용 불가", False))
                continue
            maximum_rows = int(result["maximum_rows"])
            if maximum_rows < 1:
                states.append(("Max 적용 불가", False))
                continue
            states.append((
                "Max {0} 적용".format(maximum_rows),
                True,
            ))

        self.balcony_max_button.Text = states[0][0]
        self.balcony_max_button.Enabled = states[0][1]
        self.balcony2_max_button.Text = states[1][0]
        self.balcony2_max_button.Enabled = states[1][1]

    def apply_balcony_max_rows(self, tier_index, row_count_key):
        if not self.update_preview(show_error=True):
            return
        balcony_results = self.preview_data["balcony_calculations"]
        result = balcony_results[tier_index]
        if not balcony_result_is_displayable(result):
            forms.MessageBox.Show(
                self,
                "발코니 {0}의 최대 열 수를 계산할 수 없습니다."
                .format(tier_index + 1),
                "Balcony Maximum Rows",
                forms.MessageBoxButtons.OK,
                forms.MessageBoxType.Warning
            )
            return
        maximum_rows = int(result["maximum_rows"])
        if maximum_rows < 1:
            return
        self.values[row_count_key] = maximum_rows
        self.update_preview(show_error=True)

    def on_apply_balcony_max(self, sender, event_args):
        self.apply_balcony_max_rows(0, "balcony_row_count")

    def on_apply_balcony2_max(self, sender, event_args):
        self.apply_balcony_max_rows(1, "balcony2_row_count")

    def on_balcony_live_preview(self, tier_index, values):
        self.values.update(values)
        self.sync_balcony_height_boxes_from_values()
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

    def on_section_10mm_up(self, sender, event_args):
        if not self.update_preview(show_error=True):
            return
        original_overrides = dict(self.section_rise_overrides)
        updated_overrides = dict(self.section_rise_overrides)
        for section in self.section_interpolation_rows():
            if not section["editable"]:
                continue
            target = math.ceil(
                float(section["current_rise"]) / 10.0
            ) * 10.0
            target = max(
                target,
                float(section.get("minimum_target", 0.0))
            )
            updated_overrides[section["key"]] = target
        self.section_rise_overrides = updated_overrides
        if not self.update_preview(show_error=True):
            self.section_rise_overrides = original_overrides
            self.update_preview(show_error=False)

    def on_section_reset(self, sender, event_args):
        self.section_rise_overrides = {
            key: None for key in SEATING_RISE_KEYS
        }
        self.update_preview(show_error=True)

    def on_section_dimension_interpolation(self, sender, event_args):
        if not self.update_preview(show_error=True):
            return

        original_overrides = dict(self.section_rise_overrides)
        original_signatures = dict(self.section_solver_signatures)
        dialog = SectionDimensionInterpolationDialog(
            self.section_interpolation_rows(),
            dict(self.section_rise_overrides),
            self.on_section_dimension_live_preview
        )
        dialog.ShowModal(self)
        if not dialog.accepted:
            self.section_rise_overrides = original_overrides
            self.section_solver_signatures = original_signatures
            self.update_preview(show_error=False)
            return

        self.section_rise_overrides = dict(dialog.overrides)
        if not self.update_preview(show_error=True):
            self.section_rise_overrides = original_overrides
            self.section_solver_signatures = original_signatures
            self.update_preview(show_error=False)

    def on_section_dimension_live_preview(self, overrides):
        previous_overrides = dict(self.section_rise_overrides)
        previous_signatures = dict(self.section_solver_signatures)
        try:
            self.section_rise_overrides = dict(overrides)
            if not self.update_preview(show_error=False):
                raise ValueError(
                    self.warning_text
                    or "Section preview could not be updated."
                )
            sections = self.section_interpolation_rows()
            return {
                "overrides": dict(self.section_rise_overrides),
                "sections": sections,
            }
        except Exception:
            self.section_rise_overrides = previous_overrides
            self.section_solver_signatures = previous_signatures
            try:
                self.update_preview(show_error=False)
            except Exception:
                pass
            raise

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
        stalls_calculation = self.preview_data["calculation"]
        stalls_reference_z = stalls_height_reference_z(
            stalls_calculation
        )
        effective_stalls_rear_z = stalls_calculation[
            "base_z_values"
        ][-1]
        dialog = BalconySettingsDialog(
            self.values,
            lower_result,
            first_limit_x,
            self.opening_height_mm,
            stalls_reference_z,
            effective_stalls_rear_z,
            stalls_calculation["x_values"][-1],
            tier_index,
            self.on_balcony_live_preview
        )
        dialog.ShowModal(self)

        if not dialog.accepted:
            self.values.update(original_values)
            self.sync_balcony_height_boxes_from_values()
            self.section_rise_overrides = original_overrides
            self.section_solver_signatures = original_signatures
            self.update_preview(show_error=False)
            return

        self.values.update(dialog.external_values())
        self.sync_balcony_height_boxes_from_values()
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

        fit_issues = self.preview_data.get(
            "seat_row_override_fit_issues",
            [],
        )
        if fit_issues:
            forms.MessageBox.Show(
                self,
                self.seat_row_fit_issue_message(fit_issues[0]),
                "Auditorium Seat Layout Adjustment",
                forms.MessageBoxButtons.OK,
                forms.MessageBoxType.Warning,
            )
            return

        params = self.read_params()
        saved_params = dict(params)
        saved_params["stalls_rear_world_z"] = None
        if self.seat_row_overrides_user_modified:
            saved_overrides = self.normalized_seat_row_overrides(params)
        else:
            # Declining or merely previewing a saved template must not erase
            # it.  A successfully applied row edit replaces the template;
            # applying Reset Auto to every row therefore clears it naturally.
            saved_overrides = self.saved_seat_row_override_template()
        if self.has_any_seat_row_overrides(saved_overrides):
            saved_params[SEAT_ROW_OVERRIDE_STATE_KEY] = {
                "version": SEAT_ROW_OVERRIDE_STATE_VERSION,
                "overrides": clone_plain_data(saved_overrides),
            }
        sc.sticky[STICKY_KEY] = saved_params
        self.accepted = True
        self.Close(True)

    def on_cancel(self, sender, event_args):
        self.accepted = False
        self.Close(False)

    def disable_preview(self):
        self.conduit.Enabled = False
        self.conduit.clear()
        self.plan_conduit.Enabled = False
        self.plan_conduit.clear()
        self.bake_plan_preview_button.Enabled = False
        self.doc.Views.Redraw()
