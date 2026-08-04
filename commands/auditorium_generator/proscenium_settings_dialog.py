# -*- coding: utf-8 -*-
"""Eto dialog for editing proscenium and stage-space settings."""

import Eto.Forms as forms
import Eto.Drawing as drawing

from .calculations.stage import (
    calculated_proscenium_defaults,
    is_proscenium_stage,
    validate_proscenium_params,
)


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
        self.stage_type = values.get("stage_type", "proscenium")
        self.preview_callback = preview_callback
        self.values = {
            key: values[key]
            for key in PROSCENIUM_PARAM_KEYS
        }
        self.accepted = False

        self.Title = "프로시니엄 / 무대공간 설정"
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

        stage_type_label = forms.Label()
        stage_type_label.Text = (
            "Stage type: Proscenium"
            if is_proscenium_stage({"stage_type": self.stage_type})
            else (
                "Stage type: Open / Podium "
                "(flytower and auxiliary stages are disabled)"
            )
        )
        left_right_label = forms.Label()
        left_right_label.Text = (
            "Right / left are defined from the audience looking "
            "toward the stage."
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
        preview_row.Items.Add(
            forms.StackLayoutItem(self.section_2d_radio)
        )
        preview_row.Items.Add(
            forms.StackLayoutItem(self.space_3d_radio)
        )

        main_layout = forms.DynamicLayout()
        main_layout.Spacing = drawing.Size(8, 8)

        main_layout.AddRow(self.make_header("기준"))
        main_layout.AddRow(opening_label)
        main_layout.AddRow(stage_type_label)
        main_layout.AddRow(left_right_label)
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
                "오른무대 (관객 기준)",
                (self.right_yes_radio, self.right_no_radio),
                self.right_width_box,
                self.right_depth_box,
                self.right_height_box
            )
        )
        main_layout.AddRow(
            self.make_dimension_row(
                "왼무대 (관객 기준)",
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
        button_row.Items.Add(
            forms.StackLayoutItem(self.formula_button)
        )
        button_row.Items.Add(forms.StackLayoutItem(self.ok_button))
        button_row.Items.Add(forms.StackLayoutItem(self.cancel_button))
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
            row.Items.Add(forms.StackLayoutItem(name_label))

        if radios:
            yes_radio, no_radio = radios
            row.Items.Add(forms.StackLayoutItem(yes_radio))
            row.Items.Add(forms.StackLayoutItem(no_radio))

        row.Items.Add(forms.StackLayoutItem(self.make_label("폭")))
        row.Items.Add(forms.StackLayoutItem(width_box))
        row.Items.Add(forms.StackLayoutItem(self.make_label("깊이")))
        row.Items.Add(forms.StackLayoutItem(depth_box))
        row.Items.Add(forms.StackLayoutItem(self.make_label("높이")))
        row.Items.Add(forms.StackLayoutItem(height_box))
        row.Items.Add(forms.StackLayoutItem(self.make_label("mm")))
        return row

    def make_understage_row(self):
        row = forms.StackLayout()
        row.Orientation = forms.Orientation.Horizontal
        row.Spacing = 8
        name_label = self.make_label("하부무대")
        name_label.Width = 155
        row.Items.Add(forms.StackLayoutItem(name_label))
        row.Items.Add(
            forms.StackLayoutItem(self.understage_yes_radio)
        )
        row.Items.Add(
            forms.StackLayoutItem(self.understage_no_radio)
        )
        row.Items.Add(
            forms.StackLayoutItem(self.make_label("Z 깊이"))
        )
        row.Items.Add(forms.StackLayoutItem(self.understage_depth_box))
        row.Items.Add(forms.StackLayoutItem(self.make_label("mm")))
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
        validation_values = dict(values)
        validation_values["stage_type"] = self.stage_type
        validate_proscenium_params(
            validation_values,
            self.opening_width_mm
        )
        return values

    def update_enabled_state(self):
        proscenium_enabled = is_proscenium_stage({
            "stage_type": self.stage_type,
        })
        right_enabled = (
            proscenium_enabled
            and bool(self.right_yes_radio.Checked)
        )
        left_enabled = (
            proscenium_enabled
            and bool(self.left_yes_radio.Checked)
        )
        rear_enabled = (
            proscenium_enabled
            and bool(self.rear_yes_radio.Checked)
        )
        understage_enabled = bool(self.understage_yes_radio.Checked)

        self.main_height_box.Enabled = proscenium_enabled
        for radio in (
            self.right_yes_radio,
            self.right_no_radio,
            self.left_yes_radio,
            self.left_no_radio,
            self.rear_yes_radio,
            self.rear_no_radio,
        ):
            radio.Enabled = proscenium_enabled
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
