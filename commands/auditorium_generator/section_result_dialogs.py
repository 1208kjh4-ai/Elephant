# -*- coding: utf-8 -*-
"""Section-rise interpolation and calculated-result dialogs."""

import math

import Eto.Forms as forms
import Eto.Drawing as drawing

from .calculations.sections import (
    is_finite_number,
    validate_section_rise_target,
)
from .section_interpolation_constants import (
    SECTION_INTERPOLATION_WARNING_RATIO,
    SECTION_RISE_KEYS,
)
from .formatting import format_section_height_dimension


class SectionDimensionInterpolationDialog(forms.Dialog[bool]):
    def __init__(
        self,
        sections,
        overrides,
        live_preview_callback=None
    ):
        forms.Dialog[bool].__init__(self)

        self.sections = list(sections)
        self.overrides = dict(overrides)
        self.live_preview_callback = live_preview_callback
        self.target_boxes = {}
        self.current_labels = {}
        self.accepted = False

        self.Title = "Section Dimension Control"
        self.ClientSize = drawing.Size(620, 360)
        self.Padding = drawing.Padding(12)
        self.Resizable = True

        layout = forms.DynamicLayout()
        layout.Spacing = drawing.Size(8, 8)
        layout.AddRow(
            self.make_header("Section interval"),
            self.make_header("Current height"),
            self.make_header("Target height (mm)")
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
            target_box.KeyDown += self.on_target_box_key_down
            self.target_boxes[section["key"]] = target_box
            current_label = forms.Label()
            current_label.Text = format_section_height_dimension(
                section["current_rise"]
            )
            current_label.VerticalAlignment = (
                forms.VerticalAlignment.Center
            )
            self.current_labels[section["key"]] = current_label
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
        rounding_row.Items.Add(forms.StackLayoutItem(round_down_button))
        rounding_row.Items.Add(
            forms.StackLayoutItem(round_nearest_button)
        )
        rounding_row.Items.Add(forms.StackLayoutItem(round_up_button))
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
        action_row.Items.Add(forms.StackLayoutItem(reset_button))
        action_row.Items.Add(forms.StackLayoutItem(apply_button))
        action_row.Items.Add(forms.StackLayoutItem(cancel_button))
        layout.AddRow(action_row)
        self.Content = layout
        self._enter_applied_snapshot = self.target_text_snapshot()

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
            target = max(
                target,
                float(section.get("minimum_target", 0.0))
            )
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
            if section.get("kind") == "ceiling_clear_height":
                if not is_finite_number(target):
                    raise ValueError(
                        "Rear platform-to-ceiling height must be a "
                        "finite number."
                    )
                target = max(
                    0.0,
                    target,
                    float(section.get("minimum_target", 0.0))
                )
                self.target_boxes[section["key"]].Text = (
                    self.format_value(target)
                )
            else:
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
            "Section Dimension Control",
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

    def target_text_snapshot(self):
        return tuple(
            (
                section["key"],
                self.target_boxes[section["key"]].Text
            )
            for section in self.sections
            if section["editable"]
        )

    def synchronize_sections(self, sections):
        incoming_by_key = {
            section["key"]: dict(section)
            for section in sections
        }
        current_keys = [section["key"] for section in self.sections]
        if set(incoming_by_key) != set(current_keys):
            raise ValueError(
                "The available section intervals changed while applying."
            )
        self.sections = [
            incoming_by_key[key] for key in current_keys
        ]
        for section in self.sections:
            key = section["key"]
            self.current_labels[key].Text = (
                format_section_height_dimension(
                    section["current_rise"]
                )
            )
            self.target_boxes[key].Enabled = bool(section["editable"])

    def try_apply(self, close_dialog):
        try:
            targets = self.read_targets()
            if not self.confirm_large_changes(targets):
                return False

            updated_overrides = dict(self.overrides)
            updated_overrides.update(targets)
            live_preview_callback = getattr(
                self,
                "live_preview_callback",
                None
            )
            if live_preview_callback is not None:
                applied_result = live_preview_callback(
                    dict(updated_overrides)
                )
                if applied_result is None:
                    raise ValueError(
                        "Section preview could not be updated."
                    )
                applied_sections = None
                if (
                    isinstance(applied_result, dict)
                    and "overrides" in applied_result
                ):
                    updated_overrides = dict(
                        applied_result["overrides"]
                    )
                    applied_sections = applied_result.get("sections")
                else:
                    updated_overrides = dict(applied_result)
                if applied_sections is not None:
                    self.synchronize_sections(applied_sections)

            self.overrides = updated_overrides
            for section in self.sections:
                key = section["key"]
                applied_value = self.overrides.get(key)
                if (
                    section["editable"]
                    and applied_value is not None
                ):
                    self.target_boxes[key].Text = self.format_value(
                        applied_value
                    )
            self._enter_applied_snapshot = (
                self.target_text_snapshot()
            )
            if close_dialog:
                self.accepted = True
                self.Close(True)
            return True
        except Exception as error:
            forms.MessageBox.Show(
                self,
                str(error),
                "Section Dimension Control",
                forms.MessageBoxButtons.OK,
                forms.MessageBoxType.Warning
            )
            return False

    def on_target_box_key_down(self, sender, event_args):
        if event_args.Key == forms.Keys.Enter:
            event_args.Handled = True
            if (
                self.target_text_snapshot()
                == self._enter_applied_snapshot
            ):
                self.accepted = True
                self.Close(True)
                return
            self.try_apply(close_dialog=False)

    def on_apply(self, sender, event_args):
        self.try_apply(close_dialog=True)

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
        button_row.Items.Add(forms.StackLayoutItem(close_button))

        layout = forms.DynamicLayout()
        layout.Spacing = drawing.Size(6, 6)
        layout.AddRow(result_area)
        layout.AddRow(warning_area)
        layout.AddRow(button_row)
        self.Content = layout

    def on_close(self, sender, event_args):
        self.Close(True)
