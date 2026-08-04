# -*- coding: utf-8 -*-
"""Balcony settings dialog for the auditorium generator."""

import Eto.Forms as forms
import Eto.Drawing as drawing

from .balcony_height_reference import rebase_balcony_last_platform_z
from .constants import (
    BALCONY_TIER_KEY_MAPS,
    MAX_BALCONY_ROW_COUNT,
)
from .calculations.sections import (
    calculate_balcony_max_rows,
    is_finite_number,
    normalized_balcony_tier_params,
    standard_balcony_railing_height,
)


BALCONY_SETTINGS_VERSION = 3


class BalconySettingsDialog(forms.Dialog[bool]):
    def __init__(
        self,
        values,
        stalls_result,
        first_row_distance,
        opening_height_mm,
        stalls_rear_z,
        effective_stalls_rear_z,
        rear_reference_x,
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
        self.effective_stalls_rear_z = float(
            effective_stalls_rear_z
        )
        self.rear_reference_x = float(rear_reference_x)
        self.live_preview_callback = live_preview_callback
        self.accepted = False
        self._enter_close_armed = False
        self._text_changed_since_enter = False
        self._enter_text_snapshot = None

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
        if saved_balcony_version < 3:
            self.values["balcony_longitudinal_offset"] = 0.0
            self.values["balcony_settings_version"] = (
                BALCONY_SETTINGS_VERSION
            )

        self.Title = "발코니 {0} 설정".format(tier_index + 1)
        self.ClientSize = drawing.Size(500, 540)
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
            self.values["balcony_last_platform_z"]
        )
        self.row_count_box = self.make_text_box("balcony_row_count")
        self.row_pitch_box = self.make_text_box("balcony_row_pitch")
        self.longitudinal_offset_box = self.make_text_box(
            "balcony_longitudinal_offset"
        )
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
            text_box.TextChanged += self.on_text_box_text_changed
            text_box.KeyDown += self.on_text_box_key_down
            text_box.LostFocus += self.on_text_box_lost_focus

        layout = forms.DynamicLayout()
        layout.Spacing = drawing.Size(6, 6)

        enabled_row = forms.StackLayout()
        enabled_row.Orientation = forms.Orientation.Horizontal
        enabled_row.Spacing = 12
        enabled_row.Items.Add(
            forms.StackLayoutItem(self.enabled_yes_radio)
        )
        enabled_row.Items.Add(
            forms.StackLayoutItem(self.enabled_no_radio)
        )
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
        layout.AddRow(
            self.make_label(
                "Offset from stalls rear (mm, + rear / - stage)"
            ),
            self.longitudinal_offset_box
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
        button_row.Items.Add(forms.StackLayoutItem(self.ok_button))
        button_row.Items.Add(forms.StackLayoutItem(self.cancel_button))
        layout.AddRow(None)
        layout.AddRow(button_row)
        self.Content = layout

        self.update_enabled_state()
        self.try_live_preview()
        self._enter_text_snapshot = self.text_box_snapshot()

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
            self.longitudinal_offset_box,
            self.railing_t_box,
            self.railing_w_box,
            self.railing_h_box,
        ]

    def text_box_snapshot(self):
        if not hasattr(self, "last_platform_z_box"):
            return None
        return tuple(
            str(text_box.Text)
            for text_box in self.all_text_boxes()
        )

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
            or integer_value > MAX_BALCONY_ROW_COUNT
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
            "balcony_last_platform_z": relative_last_platform_z,
            "balcony_row_count": self.parse_row_count(),
            "balcony_row_pitch": self.parse_float(
                self.row_pitch_box,
                "발코니 열 간격"
            ),
            "balcony_longitudinal_offset": self.parse_float(
                self.longitudinal_offset_box,
                "Balcony longitudinal offset"
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
        if values["balcony_row_pitch"] <= 0.0:
            raise ValueError("발코니 열 간격은 0보다 커야 합니다.")
        if not is_finite_number(
            values["balcony_longitudinal_offset"]
        ):
            raise ValueError(
                "Balcony longitudinal offset must be a finite number."
            )
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
        last_platform_key = self.key_map["balcony_last_platform_z"]
        # Convert the stored stalls-rear offset into the absolute local Z
        # required by the balcony solver without changing the saved value.
        params[last_platform_key] = rebase_balcony_last_platform_z(
            params[last_platform_key] + self.stalls_rear_z,
            self.stalls_rear_z,
            self.effective_stalls_rear_z
        )
        params["first_row_distance"] = self.first_row_distance
        normalized = normalized_balcony_tier_params(
            params,
            self.tier_index
        )
        normalized["balcony_rear_reference_x"] = (
            self.rear_reference_x
        )
        return normalized

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
            event_args.Handled = True
            current_snapshot = self.text_box_snapshot()
            close_is_armed = getattr(
                self,
                "_enter_close_armed",
                False
            )
            text_changed = getattr(
                self,
                "_text_changed_since_enter",
                False
            )
            applied_snapshot = getattr(
                self,
                "_enter_text_snapshot",
                current_snapshot
            )

            if (
                close_is_armed
                and not text_changed
                and current_snapshot == applied_snapshot
            ):
                self.accepted = True
                self.Close(True)
                return

            if text_changed or current_snapshot != applied_snapshot:
                if self.try_live_preview():
                    self._enter_text_snapshot = (
                        self.text_box_snapshot()
                    )
                    self._text_changed_since_enter = False
                    self._enter_close_armed = True
                else:
                    self._enter_close_armed = False
                return

            self.on_ok(sender, event_args)

    def on_text_box_text_changed(self, sender, event_args):
        self.invalidate_enter_close()

    def invalidate_enter_close(self):
        self._text_changed_since_enter = True
        self._enter_close_armed = False

    def on_text_box_lost_focus(self, sender, event_args):
        if not self.try_live_preview():
            self.invalidate_enter_close()

    def on_option_changed(self, sender, event_args):
        self.invalidate_enter_close()
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
