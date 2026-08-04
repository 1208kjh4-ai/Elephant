# -*- coding: utf-8 -*-
"""Row-by-row seat-layout adjustment dialog.

The dialog deliberately keeps draft edits separate from committed overrides.
Valid draft text is sent to ``draft_preview_callback`` after a short delay so
only the plan preview needs to change.  A row's Apply button then sends the
same override set to ``apply_callback`` for the full auditorium update.

Callback contract
-----------------
``draft_preview_callback(overrides)`` may return updated ``tier_layouts`` or
``None``.  Exceptions are shown in the warning line and prevent Apply.

``apply_callback(overrides)`` may return ``False`` for failure, ``True`` or
``None`` for success, updated ``tier_layouts`` for success, or
``(success, tier_layouts, message)``.  Exceptions are treated as failure.

``restore_preview_callback()`` is called when an unapplied edit is cancelled
or the dialog is closed.  Edits that have already been applied are retained.
"""

import re

import Eto.Forms as forms
import Eto.Drawing as drawing


TIER_ORDER = (
    ("stalls", "Stalls"),
    ("balcony_1", "Balcony 1"),
    ("balcony_2", "Balcony 2"),
)

MAX_FIXED_SEATS_PER_ROW = 500
PREVIEW_DEBOUNCE_SECONDS = 0.30

try:
    STRING_TYPES = (basestring,)
except NameError:
    STRING_TYPES = (str,)

try:
    INTEGER_TYPES = (int, long)
except NameError:
    INTEGER_TYPES = (int,)


def clone_plain_data(value):
    """Copy nested Python containers without depending on ``copy.deepcopy``."""
    if isinstance(value, dict):
        return dict(
            (clone_plain_data(key), clone_plain_data(item))
            for key, item in value.items()
        )
    if isinstance(value, list):
        return [clone_plain_data(item) for item in value]
    if isinstance(value, tuple):
        return tuple(clone_plain_data(item) for item in value)
    return value


def _strip_optional_brackets(text):
    stripped = text.strip()
    if not stripped:
        raise ValueError("Enter a seat rule or 'empty'.")

    opening = stripped[0]
    closing = stripped[-1]
    bracket_pairs = {"[": "]", "(": ")"}
    if opening in bracket_pairs:
        if closing != bracket_pairs[opening]:
            raise ValueError("The opening and closing brackets do not match.")
        stripped = stripped[1:-1].strip()
    elif closing in ("]", ")"):
        raise ValueError("The opening and closing brackets do not match.")
    return stripped


def parse_row_rule(text, expected_block_count=None):
    """Parse ``12,a,12`` / ``[12,8,12]`` / ``empty`` into a list.

    Positive integer blocks and ``a`` are accepted.  An empty row is
    represented by ``[]`` and must be written as the whole value ``empty``.
    The sum of the fixed blocks may not exceed 500 seats.
    """
    if text is None:
        raise ValueError("Enter a seat rule or 'empty'.")

    body = _strip_optional_brackets(str(text))
    if body.lower() == "empty":
        return []

    raw_tokens = body.split(",")
    if not raw_tokens or any(not token.strip() for token in raw_tokens):
        raise ValueError(
            "Separate every block with a comma, for example 12,a,12."
        )

    values = []
    fixed_total = 0
    for raw_token in raw_tokens:
        token = raw_token.strip().lower()
        if token == "a":
            values.append("a")
            continue
        if not re.match(r"^[0-9]+$", token):
            raise ValueError(
                "Each block must be a positive integer or 'a'."
            )
        number = int(token)
        if number <= 0:
            raise ValueError(
                "Zero is only allowed by setting the whole row to 'empty'."
            )
        fixed_total += number
        values.append(number)

    if expected_block_count is not None:
        expected = int(expected_block_count)
        if expected > 0 and len(values) != expected:
            raise ValueError(
                "This row must contain exactly {0} seat blocks.".format(
                    expected
                )
            )

    if fixed_total > MAX_FIXED_SEATS_PER_ROW:
        raise ValueError(
            "The fixed blocks may contain at most {0} seats per row.".format(
                MAX_FIXED_SEATS_PER_ROW
            )
        )
    return values


def format_row_rule(values):
    """Return the canonical display text for a parsed row rule."""
    if values is None:
        return "[empty]"
    if isinstance(values, STRING_TYPES):
        try:
            values = parse_row_rule(values)
        except Exception:
            return str(values)
    try:
        items = list(values)
    except Exception:
        return str(values)
    if not items:
        return "[empty]"
    return "[{0}]".format(
        ",".join(str(item).lower() for item in items)
    )


def _normalise_override_value(value):
    if isinstance(value, STRING_TYPES):
        return parse_row_rule(value)
    if value is None:
        return []
    values = list(value)
    if not values:
        return []
    return parse_row_rule(
        ",".join(str(item) for item in values)
    )


def _normalise_overrides(overrides):
    normalised = {}
    source = overrides if isinstance(overrides, dict) else {}
    for tier_key, unused_title in TIER_ORDER:
        tier_source = source.get(tier_key, {})
        tier_result = {}
        if isinstance(tier_source, dict):
            for raw_row_index, raw_value in tier_source.items():
                try:
                    row_index = int(raw_row_index)
                    tier_result[row_index] = _normalise_override_value(
                        raw_value
                    )
                except Exception:
                    # Keep the dialog usable when it receives stale data.  A
                    # newly edited value will always be validated strictly.
                    tier_result[raw_row_index] = clone_plain_data(raw_value)
        normalised[tier_key] = tier_result
    return normalised


class SeatLayoutAdjustmentDialog(forms.Dialog[bool]):
    """Scrollable three-tier editor for row-specific seat rules."""

    def __init__(
        self,
        tier_layouts,
        committed_overrides,
        draft_preview_callback,
        apply_callback,
        restore_preview_callback,
        active_row_preview_callback=None,
    ):
        forms.Dialog[bool].__init__(self)

        self.tier_layouts = clone_plain_data(tier_layouts or {})
        self.committed_overrides = _normalise_overrides(
            committed_overrides
        )
        self.draft_preview_callback = draft_preview_callback
        self.apply_callback = apply_callback
        self.restore_preview_callback = restore_preview_callback
        self.active_row_preview_callback = active_row_preview_callback

        self.accepted = False
        self.row_controls = {}
        self._active_key = None
        self._active_force_auto = False
        self._active_draft_overrides = None
        self._previewed_draft_overrides = None
        self._draft_tier_layouts = None
        self._pending_draft_overrides = None
        self._suppress_text_events = False
        self._closed = False

        self.Title = "Auditorium Seat Layout Adjustment"
        self.ClientSize = drawing.Size(940, 650)
        self.Padding = drawing.Padding(12)
        self.Resizable = True

        self.preview_timer = forms.UITimer()
        self.preview_timer.Interval = PREVIEW_DEBOUNCE_SECONDS
        self.preview_timer.Elapsed += self.on_preview_timer_elapsed

        self.warning_label = forms.Label()
        self.warning_label.TextColor = drawing.Color(210, 35, 35)
        self.warning_label.Wrap = forms.WrapMode.Word

        self.tab_control = forms.TabControl()
        self.tab_control.Height = 510
        self._build_tabs()

        instruction_label = forms.Label()
        instruction_label.Text = (
            "Edit one row at a time. Valid draft values update Plan Preview "
            "first; Apply commits them to the full 3D auditorium. "
            "Allowed input: positive integers, a, or whole-row empty."
        )
        instruction_label.Wrap = forms.WrapMode.Word

        self.close_button = forms.Button()
        self.close_button.Text = "Close"
        self.close_button.Width = 90
        self.close_button.Click += self.on_close
        self.AbortButton = self.close_button

        close_row = forms.StackLayout()
        close_row.Orientation = forms.Orientation.Horizontal
        close_row.HorizontalContentAlignment = (
            forms.HorizontalAlignment.Right
        )
        close_row.Items.Add(forms.StackLayoutItem(self.close_button))

        layout = forms.DynamicLayout()
        layout.Spacing = drawing.Size(8, 8)
        layout.AddRow(instruction_label)
        layout.AddRow(self.tab_control)
        layout.AddRow(self.warning_label)
        layout.AddRow(close_row)
        self.Content = layout

        self.Closed += self.on_closed

    # ------------------------------------------------------------------ UI

    def _build_tabs(self):
        for tier_key, title in TIER_ORDER:
            page = forms.TabPage()
            page.Text = title
            page.Content = self._build_tier_content(tier_key)
            self.tab_control.Pages.Add(page)

    def _tier_rows_and_state(self, tier_key, layouts=None):
        source_layouts = self.tier_layouts if layouts is None else layouts
        source = source_layouts.get(tier_key) if isinstance(
            source_layouts,
            dict
        ) else None

        if source is None:
            return False, [], "This tier is not active."

        if isinstance(source, dict):
            active = bool(source.get("enabled", source.get("active", True)))
            rows = source.get("rows", source.get("layouts", []))
            if not active:
                return False, [], "This tier is not active."
        else:
            rows = source

        try:
            rows = list(rows)
        except Exception:
            rows = []
        if not rows:
            return True, [], "No seat rows are available for this tier."
        return True, rows, ""

    def _ordered_rows(self, rows):
        indexed = []
        for fallback_index, metadata in enumerate(rows):
            row = metadata if isinstance(metadata, dict) else {}
            try:
                row_index = int(row.get("row_index", fallback_index))
            except Exception:
                row_index = fallback_index
            indexed.append((row_index, fallback_index, row))
        indexed.sort(key=lambda item: (item[0], item[1]))
        return [(item[0], item[2]) for item in indexed]

    def _build_tier_content(self, tier_key):
        active, rows, message = self._tier_rows_and_state(tier_key)
        content = forms.DynamicLayout()
        content.Padding = drawing.Padding(8)
        content.Spacing = drawing.Size(5, 6)

        if not active or not rows:
            label = forms.Label()
            label.Text = message
            label.TextColor = drawing.Color(105, 105, 105)
            content.AddRow(label)
        else:
            content.AddRow(self._make_tier_header())
            for row_index, metadata in self._ordered_rows(rows):
                content.AddRow(
                    self._make_row_controls(tier_key, row_index, metadata)
                )

        scrollable = forms.Scrollable()
        scrollable.Content = content
        return scrollable

    def _make_tier_header(self):
        row = forms.StackLayout()
        row.Orientation = forms.Orientation.Horizontal
        row.Spacing = 6
        row.Items.Add(self._fixed_item(self._make_header("Row"), 62))
        row.Items.Add(self._fixed_item(self._make_header("Layout"), 190))
        row.Items.Add(self._fixed_item(self._make_header("Resolved"), 190))
        row.Items.Add(self._fixed_item(self._make_header("Edit / Apply"), 82))
        row.Items.Add(self._fixed_item(self._make_header("Draft"), 76))
        row.Items.Add(self._fixed_item(self._make_header("Automatic"), 92))
        row.Items.Add(self._fixed_item(self._make_header("Empty"), 82))
        return row

    def _make_header(self, text):
        label = forms.Label()
        label.Text = text
        label.VerticalAlignment = forms.VerticalAlignment.Center
        try:
            label.Font = drawing.Font(
                label.Font.FamilyName,
                label.Font.Size,
                drawing.FontStyle.Bold
            )
        except Exception:
            pass
        return label

    def _fixed_item(self, control, width):
        control.Width = width
        return forms.StackLayoutItem(control)

    def _make_row_controls(self, tier_key, row_index, metadata):
        key = (tier_key, row_index)
        row_label = forms.Label()
        row_label.Text = "Row {0}".format(row_index + 1)
        row_label.VerticalAlignment = forms.VerticalAlignment.Center

        text_box = forms.TextBox()
        text_box.Text = self._locked_row_text(tier_key, row_index, metadata)
        text_box.ReadOnly = True

        resolved_label = forms.Label()
        resolved_label.Text = self._resolved_row_text(metadata)
        resolved_label.VerticalAlignment = forms.VerticalAlignment.Center

        edit_button = forms.Button()
        edit_button.Text = "Edit"
        edit_button.Enabled = self._row_is_editable(
            tier_key,
            row_index,
            metadata
        )

        cancel_button = forms.Button()
        cancel_button.Text = "Cancel"
        cancel_button.Enabled = False

        auto_button = forms.Button()
        auto_button.Text = "Reset Auto"
        auto_button.Enabled = False

        empty_button = forms.Button()
        empty_button.Text = "Set Empty"
        empty_button.Enabled = False

        handlers = {
            "edit": self._make_edit_handler(key),
            "cancel": self._make_cancel_handler(key),
            "auto": self._make_auto_handler(key),
            "empty": self._make_empty_handler(key),
            "text": self._make_text_handler(key),
            "key": self._make_key_handler(key),
        }
        edit_button.Click += handlers["edit"]
        cancel_button.Click += handlers["cancel"]
        auto_button.Click += handlers["auto"]
        empty_button.Click += handlers["empty"]
        text_box.TextChanged += handlers["text"]
        text_box.KeyDown += handlers["key"]

        self.row_controls[key] = {
            "metadata": metadata,
            "row_label": row_label,
            "text_box": text_box,
            "resolved_label": resolved_label,
            "edit_button": edit_button,
            "cancel_button": cancel_button,
            "auto_button": auto_button,
            "empty_button": empty_button,
            "handlers": handlers,
        }
        has_override, unused_override = self._lookup_override(
            self.committed_overrides,
            tier_key,
            row_index,
        )
        self._set_locked_style(text_box, modified=has_override)

        row = forms.StackLayout()
        row.Orientation = forms.Orientation.Horizontal
        row.Spacing = 6
        row.Items.Add(self._fixed_item(row_label, 62))
        row.Items.Add(self._fixed_item(text_box, 190))
        row.Items.Add(self._fixed_item(resolved_label, 190))
        row.Items.Add(self._fixed_item(edit_button, 82))
        row.Items.Add(self._fixed_item(cancel_button, 76))
        row.Items.Add(self._fixed_item(auto_button, 92))
        row.Items.Add(self._fixed_item(empty_button, 82))
        return row

    def _set_locked_style(self, text_box, modified=False):
        text_box.ReadOnly = True
        try:
            # Keep read-only rows visually light.  Disabling the TextBox (or
            # using the platform's default read-only background) can turn it
            # almost black in Rhino's dark theme, so lock only the editing
            # behaviour and set both colours explicitly.
            text_box.BackgroundColor = drawing.Colors.White
            text_box.TextColor = (
                drawing.Colors.DodgerBlue
                if modified
                else drawing.Colors.Gray
            )
        except Exception:
            pass

    def _set_edit_style(self, text_box, modified=False):
        text_box.ReadOnly = False
        try:
            text_box.BackgroundColor = drawing.Colors.White
            text_box.TextColor = (
                drawing.Colors.DodgerBlue
                if modified
                else drawing.Colors.Black
            )
        except Exception:
            pass

    def _set_draft_style(self, text_box):
        """Mark a user-authored or button-authored draft in blue."""
        text_box.ReadOnly = False
        try:
            text_box.BackgroundColor = drawing.Colors.White
            text_box.TextColor = drawing.Colors.DodgerBlue
        except Exception:
            pass

    # ---------------------------------------------------------- row metadata

    def _metadata_values(self, metadata, key):
        if not isinstance(metadata, dict):
            return None
        value = metadata.get(key)
        if value is None:
            return None
        if isinstance(value, STRING_TYPES):
            try:
                return parse_row_rule(value)
            except Exception:
                return value
        try:
            return list(value)
        except Exception:
            return value

    def _lookup_override(self, overrides, tier_key, row_index):
        if not isinstance(overrides, dict):
            return False, None
        tier_values = overrides.get(tier_key, {})
        if not isinstance(tier_values, dict):
            return False, None
        if row_index in tier_values:
            return True, tier_values[row_index]
        string_index = str(row_index)
        if string_index in tier_values:
            return True, tier_values[string_index]
        return False, None

    def _set_override(self, overrides, tier_key, row_index, values):
        if tier_key not in overrides or not isinstance(
            overrides[tier_key],
            dict
        ):
            overrides[tier_key] = {}
        overrides[tier_key].pop(str(row_index), None)
        overrides[tier_key][row_index] = clone_plain_data(values)

    def _remove_override(self, overrides, tier_key, row_index):
        tier_values = overrides.get(tier_key, {})
        if isinstance(tier_values, dict):
            tier_values.pop(row_index, None)
            tier_values.pop(str(row_index), None)

    def _base_rule(self, metadata):
        rule = self._metadata_values(metadata, "rule_values")
        if rule is not None:
            return rule
        resolved = self._metadata_values(metadata, "resolved_block_counts")
        if resolved is not None:
            return resolved
        placed = self._metadata_values(metadata, "placed_block_counts")
        if placed is not None:
            return placed
        return []

    def _automatic_rule(self, tier_key, metadata):
        """Find the tier's automatic topology, including for empty overrides."""
        default_rule = self._metadata_values(
            metadata,
            "default_rule_values",
        )
        try:
            if default_rule is not None and len(default_rule) > 0:
                return default_rule
        except Exception:
            pass

        # Backward-compatible metadata may not expose the global rule.  Look
        # for it on neighbouring rows before considering an actual row rule,
        # because that rule may itself be a manual override.
        unused_active, rows, unused_message = self._tier_rows_and_state(
            tier_key
        )
        for unused_index, candidate in self._ordered_rows(rows):
            candidate_default = self._metadata_values(
                candidate,
                "default_rule_values",
            )
            try:
                if (
                    candidate_default is not None
                    and len(candidate_default) > 0
                ):
                    return candidate_default
            except Exception:
                continue
        for unused_index, candidate in self._ordered_rows(rows):
            candidate_is_automatic = bool(
                candidate.get("automatic", False)
                if isinstance(candidate, dict)
                else False
            )
            candidate_status = str(
                candidate.get("status", "")
                if isinstance(candidate, dict)
                else ""
            ).strip().lower()
            if not candidate_is_automatic and candidate_status != "automatic":
                continue
            candidate_rule = self._metadata_values(
                candidate,
                "rule_values"
            )
            try:
                if candidate_rule is not None and len(candidate_rule) > 0:
                    return candidate_rule
            except Exception:
                continue
        return []

    def _expected_block_count(self, tier_key, metadata):
        base = self._automatic_rule(tier_key, metadata)
        try:
            return len(base)
        except Exception:
            return 0

    def _locked_row_text(self, tier_key, row_index, metadata):
        has_override, override = self._lookup_override(
            self.committed_overrides,
            tier_key,
            row_index
        )
        if has_override:
            return format_row_rule(override)
        rule = self._metadata_values(metadata, "rule_values")
        if rule is not None:
            return format_row_rule(rule)
        resolved = self._metadata_values(metadata, "resolved_block_counts")
        if resolved is not None:
            return format_row_rule(resolved)
        placed = self._metadata_values(metadata, "placed_block_counts")
        if placed is not None:
            return format_row_rule(placed)
        return format_row_rule(self._base_rule(metadata))

    def _edit_row_text(self, tier_key, row_index, metadata):
        has_override, override = self._lookup_override(
            self.committed_overrides,
            tier_key,
            row_index
        )
        if has_override:
            return format_row_rule(override)
        return format_row_rule(self._base_rule(metadata))

    def _resolved_row_text(self, metadata):
        resolved = self._metadata_values(metadata, "placed_block_counts")
        if resolved is None:
            resolved = self._metadata_values(
                metadata,
                "resolved_block_counts"
            )
        text = format_row_rule(resolved) if resolved is not None else "-"
        state = ""
        if isinstance(metadata, dict):
            state = str(
                metadata.get("state", metadata.get("status", "")) or ""
            ).strip()
        if state and state.lower() not in ("active", "ok", "placed"):
            return "{0}  ({1})".format(text, state)
        return text

    def _row_is_editable(self, tier_key, row_index, metadata):
        has_override, unused_value = self._lookup_override(
            self.committed_overrides,
            tier_key,
            row_index
        )
        state = ""
        if isinstance(metadata, dict):
            state = str(
                metadata.get("state", metadata.get("status", "")) or ""
            ).strip().lower()
        blocked_states = (
            "inactive",
            "disabled",
            "unavailable",
            "outside",
            "outside_boundary",
            "out_of_bounds",
            "no_capacity",
            "invalid",
        )
        if state in blocked_states:
            return False
        if state == "empty" and not has_override:
            return False

        # Do not infer editability from a currently empty placement.  In a
        # custom boundary a smaller fixed rule can sometimes fit even when
        # the automatic/default rule places no chairs.  Only an explicit
        # metadata state is authoritative enough to block editing.
        # Keep explicit overrides editable even when every row in the tier is
        # empty and no neighbouring row can reveal the automatic topology.
        # Reset Auto can still remove the override; the seating solver then
        # restores the global block rule during the draft preview.
        return has_override or (
            self._expected_block_count(tier_key, metadata) > 0
        )

    def _find_metadata(self, tier_key, row_index, layouts=None):
        unused_active, rows, unused_message = self._tier_rows_and_state(
            tier_key,
            layouts
        )
        for candidate_index, metadata in self._ordered_rows(rows):
            if candidate_index == row_index:
                return metadata
        return None

    # ---------------------------------------------------------- event makers

    def _make_edit_handler(self, key):
        def handler(sender, event):
            self.on_edit_or_apply(key)
        return handler

    def _make_cancel_handler(self, key):
        def handler(sender, event):
            self.on_cancel_row(key)
        return handler

    def _make_auto_handler(self, key):
        def handler(sender, event):
            self.on_reset_auto(key)
        return handler

    def _make_empty_handler(self, key):
        def handler(sender, event):
            self.on_set_empty(key)
        return handler

    def _make_text_handler(self, key):
        def handler(sender, event):
            self.on_row_text_changed(key)
        return handler

    def _make_key_handler(self, key):
        def handler(sender, event):
            if event.Key == forms.Keys.Enter:
                self.on_edit_or_apply(key)
                event.Handled = True
            elif event.Key == forms.Keys.Escape:
                if self._active_key == key:
                    self.on_cancel_row(key)
                    event.Handled = True
        return handler

    # ------------------------------------------------------------- edit flow

    def on_edit_or_apply(self, key):
        if self._active_key == key:
            self._apply_active_row()
        else:
            self._begin_edit(key)

    def _begin_edit(self, key):
        if self._active_key is not None:
            self._show_warning(
                "Apply or cancel the current draft before editing another row."
            )
            return
        controls = self.row_controls.get(key)
        if controls is None or not controls["edit_button"].Enabled:
            return

        tier_key, row_index = key
        metadata = controls["metadata"]
        has_override, unused_override = self._lookup_override(
            self.committed_overrides,
            tier_key,
            row_index
        )
        self._active_key = key
        self._active_force_auto = not has_override
        self._active_draft_overrides = clone_plain_data(
            self.committed_overrides
        )
        self._previewed_draft_overrides = None
        self._draft_tier_layouts = None
        self._pending_draft_overrides = None

        self._suppress_text_events = True
        controls["text_box"].Text = self._edit_row_text(
            tier_key,
            row_index,
            metadata
        )
        self._suppress_text_events = False
        self._set_edit_style(
            controls["text_box"],
            modified=has_override,
        )
        controls["edit_button"].Text = "Apply"
        controls["cancel_button"].Enabled = True
        controls["auto_button"].Enabled = True
        controls["empty_button"].Enabled = True
        self._set_other_edit_buttons_enabled(False, except_key=key)
        try:
            controls["text_box"].Focus()
            controls["text_box"].SelectAll()
        except Exception:
            pass
        if self._notify_active_row_preview(key):
            self._show_status(
                "Draft mode: valid input is shown in Plan Preview before "
                "Apply. The active row is highlighted in red."
            )

    def _set_other_edit_buttons_enabled(self, enabled, except_key=None):
        for key, controls in self.row_controls.items():
            if key == except_key:
                continue
            controls["edit_button"].Enabled = bool(enabled) and (
                self._row_is_editable(
                    key[0],
                    key[1],
                    controls["metadata"]
                )
            )

    def on_row_text_changed(self, key):
        if self._suppress_text_events or self._active_key != key:
            return
        self._active_force_auto = False
        self._set_draft_style(
            self.row_controls[key]["text_box"]
        )
        self._queue_active_preview()

    def _read_active_draft(self):
        if self._active_key is None:
            raise ValueError("No row is being edited.")
        tier_key, row_index = self._active_key
        controls = self.row_controls[self._active_key]
        metadata = controls["metadata"]
        draft = clone_plain_data(self.committed_overrides)
        if self._active_force_auto:
            # Reset Auto is a mode, not a literal row rule.  Removing the
            # override lets the solver recover the global topology even when
            # every current row is empty and that topology is not in metadata.
            self._remove_override(draft, tier_key, row_index)
            return draft

        expected_block_count = self._expected_block_count(
            tier_key,
            metadata
        )
        values = parse_row_rule(
            controls["text_box"].Text,
            expected_block_count
        )
        if (
            expected_block_count <= 0
            and values
        ):
            raise ValueError(
                "The automatic block topology is unavailable. Use Reset "
                "Auto before entering a custom rule."
            )
        self._set_override(draft, tier_key, row_index, values)
        return draft

    def _queue_active_preview(self):
        self.preview_timer.Stop()
        try:
            draft = self._read_active_draft()
        except Exception as error:
            self._active_draft_overrides = None
            self._pending_draft_overrides = None
            self._previewed_draft_overrides = None
            self.row_controls[self._active_key]["edit_button"].Enabled = False
            self._show_warning(str(error))
            return

        self._active_draft_overrides = clone_plain_data(draft)
        self._pending_draft_overrides = clone_plain_data(draft)
        self._previewed_draft_overrides = None
        self.row_controls[self._active_key]["edit_button"].Enabled = True
        self._show_status("Waiting to update Plan Preview...")
        self.preview_timer.Start()

    def on_preview_timer_elapsed(self, sender, event):
        self.preview_timer.Stop()
        if self._active_key is None or self._pending_draft_overrides is None:
            return
        draft = clone_plain_data(self._pending_draft_overrides)
        self._pending_draft_overrides = None
        self._run_draft_preview(draft)

    def _run_draft_preview(self, draft):
        if self._active_key is None:
            return False
        controls = self.row_controls[self._active_key]
        controls["edit_button"].Enabled = False
        self._show_status("Updating Plan Preview...")
        try:
            result = None
            if self.draft_preview_callback is not None:
                result = self.draft_preview_callback(
                    clone_plain_data(draft)
                )
            if result is False:
                raise ValueError("Plan Preview rejected this row layout.")
            if result is not None:
                if not isinstance(result, dict):
                    raise ValueError(
                        "Plan Preview returned an invalid tier layout result."
                    )
                self._draft_tier_layouts = clone_plain_data(result)
                self._update_active_resolved_label(result)
            else:
                self._draft_tier_layouts = None
                self._update_active_resolved_label(None, draft=draft)
            self._active_draft_overrides = clone_plain_data(draft)
            self._previewed_draft_overrides = clone_plain_data(draft)
            controls["edit_button"].Enabled = True
            self._show_status(
                "Plan Preview updated. Click Apply to update the full auditorium."
            )
            return True
        except Exception as error:
            self._previewed_draft_overrides = None
            controls["edit_button"].Enabled = False
            self._show_warning("Plan Preview: {0}".format(error))
            return False

    def _update_active_resolved_label(self, layouts, draft=None):
        if self._active_key is None:
            return
        tier_key, row_index = self._active_key
        controls = self.row_controls[self._active_key]
        if layouts is not None:
            metadata = self._find_metadata(tier_key, row_index, layouts)
            if metadata is not None:
                controls["resolved_label"].Text = self._resolved_row_text(
                    metadata
                )
                return

        if draft is not None:
            has_override, values = self._lookup_override(
                draft,
                tier_key,
                row_index
            )
            if has_override and values is not None:
                controls["resolved_label"].Text = format_row_rule(values)
                return
        controls["resolved_label"].Text = "Updated in Plan Preview"

    def _apply_active_row(self):
        if self._active_key is None:
            return
        self.preview_timer.Stop()
        self._pending_draft_overrides = None
        try:
            draft = self._read_active_draft()
        except Exception as error:
            self._show_warning(str(error))
            return

        if self._previewed_draft_overrides != draft:
            if not self._run_draft_preview(draft):
                return

        try:
            result = None
            if self.apply_callback is not None:
                result = self.apply_callback(clone_plain_data(draft))
            success, updated_layouts, message = self._interpret_apply_result(
                result
            )
            if not success:
                raise ValueError(message or "The full auditorium update failed.")
        except Exception as error:
            # The committed dictionary is intentionally untouched.  The draft
            # plan remains visible so the user can adjust or cancel it.
            self._show_warning("Apply: {0}".format(error))
            return

        self.committed_overrides = clone_plain_data(draft)
        if updated_layouts is not None:
            self.tier_layouts = clone_plain_data(updated_layouts)
        elif self._draft_tier_layouts is not None:
            self.tier_layouts = clone_plain_data(self._draft_tier_layouts)

        applied_key = self._active_key
        self.accepted = True
        self._finish_edit(applied_key, restore_preview=False)
        self._refresh_existing_rows()
        self._show_status(message or "Row layout applied to the full auditorium.")

    def _interpret_apply_result(self, result):
        if result is False:
            return False, None, ""
        if result is None or result is True:
            return True, None, ""

        if isinstance(result, (tuple, list)):
            if not result:
                return True, None, ""
            success = bool(result[0])
            layouts = result[1] if len(result) > 1 else None
            message = result[2] if len(result) > 2 else ""
            if layouts is not None and not isinstance(layouts, dict):
                layouts = None
            return success, layouts, str(message or "")

        if isinstance(result, dict):
            if "success" in result:
                success = bool(result.get("success"))
                layouts = result.get(
                    "tier_layouts",
                    result.get("layouts")
                )
                message = result.get("message", result.get("error", ""))
                return success, layouts, str(message or "")
            return True, result, ""

        return bool(result), None, ""

    def on_reset_auto(self, key):
        if self._active_key != key:
            return
        controls = self.row_controls[key]
        self._active_force_auto = True
        automatic_rule = self._automatic_rule(
            key[0],
            controls["metadata"]
        )
        self._set_active_text(
            (
                format_row_rule(automatic_rule)
                if automatic_rule
                else "[automatic]"
            )
        )
        self._set_draft_style(controls["text_box"])
        self._queue_active_preview()

    def on_set_empty(self, key):
        if self._active_key != key:
            return
        self._active_force_auto = False
        self._set_active_text("[empty]")
        self._set_draft_style(
            self.row_controls[key]["text_box"]
        )
        self._queue_active_preview()

    def _set_active_text(self, text):
        if self._active_key is None:
            return
        self._suppress_text_events = True
        self.row_controls[self._active_key]["text_box"].Text = text
        self._suppress_text_events = False

    def on_cancel_row(self, key):
        if self._active_key != key:
            return
        restored = self._finish_edit(key, restore_preview=True)
        if restored:
            self._show_status("Draft cancelled. Plan Preview restored.")

    def _finish_edit(self, key, restore_preview):
        self.preview_timer.Stop()
        restored = True
        if restore_preview:
            restored = self._restore_preview()
            if not restored:
                # Keep the active draft editable when its visible Plan state
                # could not be replaced by the committed preview.
                return False
        self._notify_active_row_preview(None)

        controls = self.row_controls.get(key)
        if controls is not None:
            metadata = self._find_metadata(key[0], key[1])
            if metadata is None:
                metadata = controls["metadata"]
            else:
                controls["metadata"] = metadata
            self._suppress_text_events = True
            controls["text_box"].Text = self._locked_row_text(
                key[0],
                key[1],
                metadata
            )
            self._suppress_text_events = False
            controls["resolved_label"].Text = (
                self._resolved_row_text(metadata)
            )
            has_override, unused_override = self._lookup_override(
                self.committed_overrides,
                key[0],
                key[1],
            )
            self._set_locked_style(
                controls["text_box"],
                modified=has_override,
            )
            controls["edit_button"].Text = "Edit"
            controls["edit_button"].Enabled = self._row_is_editable(
                key[0],
                key[1],
                metadata
            )
            controls["cancel_button"].Enabled = False
            controls["auto_button"].Enabled = False
            controls["empty_button"].Enabled = False

        self._active_key = None
        self._active_force_auto = False
        self._active_draft_overrides = None
        self._previewed_draft_overrides = None
        self._draft_tier_layouts = None
        self._pending_draft_overrides = None
        self._set_other_edit_buttons_enabled(True)
        return restored

    def _refresh_existing_rows(self):
        for key, controls in self.row_controls.items():
            metadata = self._find_metadata(key[0], key[1])
            if metadata is None:
                continue
            controls["metadata"] = metadata
            self._suppress_text_events = True
            controls["text_box"].Text = self._locked_row_text(
                key[0],
                key[1],
                metadata
            )
            self._suppress_text_events = False
            controls["resolved_label"].Text = self._resolved_row_text(metadata)
            controls["edit_button"].Enabled = self._row_is_editable(
                key[0],
                key[1],
                metadata
            )

    # ------------------------------------------------------------ close/help

    def _restore_preview(self):
        try:
            if self.restore_preview_callback is not None:
                self.restore_preview_callback()
            return True
        except Exception as error:
            self._show_warning("Restore Plan Preview: {0}".format(error))
            return False

    def _notify_active_row_preview(self, key):
        try:
            if self.active_row_preview_callback is not None:
                self.active_row_preview_callback(key)
            return True
        except Exception as error:
            self._show_warning(
                "Highlight Plan Preview: {0}".format(error)
            )
            return False

    def _show_warning(self, message):
        self.warning_label.TextColor = drawing.Color(210, 35, 35)
        self.warning_label.Text = str(message or "")

    def _show_status(self, message):
        self.warning_label.TextColor = drawing.Color(70, 105, 70)
        self.warning_label.Text = str(message or "")

    def on_close(self, sender, event):
        if self._active_key is not None:
            if not self._finish_edit(
                self._active_key,
                restore_preview=True,
            ):
                return
        self.Close(True)

    def on_closed(self, sender, event):
        if self._closed:
            return
        self._closed = True
        self.preview_timer.Stop()
        if self._active_key is not None:
            # Covers the window close button as well as Eto's AbortButton.
            self._restore_preview()
            self._notify_active_row_preview(None)
            self._active_key = None
