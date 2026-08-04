# -*- coding: utf-8 -*-
import os
import re

import Rhino
import Rhino.Geometry as rg
import System

from .errors import RoadTextError
from .hangul import HangulDecomposer
from .pictograms import PICTOGRAM_LAYER_NAMES


class RoadGlyphLibrary(object):
    """Validate and cache Hangul and English glyphs from one 3dm file."""

    HANGUL_PATTERN = re.compile(r"^\d{2}[A-F][012]$")
    ENGLISH_PATTERN = re.compile(r"^EN_[A-Z]$")
    SYMBOL_PATTERN = re.compile(r"^SY_(?:DASH|COLON)$")
    PICTOGRAM_PATTERN = re.compile(r"^PI_[A-Z][A-Z_]*$")
    OPTIONAL_COMPOUND_LAYERS = set([
        "{0}{1}0".format(code, layout)
        for code in HangulDecomposer.COMPOUND_VOWELS
        for layout in ("D", "F")
    ])

    def __init__(self, path):
        self.path = path
        self.glyphs = {}
        self.errors = []
        self.warnings = []
        self.loaded = False

    @classmethod
    def required_hangul_layer_names(cls):
        names = set()

        for code in HangulDecomposer.CHO_CODES:
            for layout in ("A", "B", "C", "D", "E", "F"):
                names.add("{0}{1}1".format(code, layout))

        for code in HangulDecomposer.JONG_CODES:
            if code is None:
                continue
            for layout in ("C", "E", "F"):
                names.add("{0}{1}2".format(code, layout))

        for code in ("31", "32", "33", "34", "35", "36", "37", "38", "39"):
            for layout in ("A", "C"):
                names.add("{0}{1}0".format(code, layout))

        for code in ("31", "32", "35", "36", "39"):
            for layout in ("D", "F"):
                names.add("{0}{1}0".format(code, layout))

        for code in ("40", "41", "42", "43", "44"):
            for layout in ("B", "E"):
                names.add("{0}{1}0".format(code, layout))

        for code in ("40", "42", "44"):
            for layout in ("D", "F"):
                names.add("{0}{1}0".format(code, layout))

        return names

    @classmethod
    def required_english_layer_names(cls):
        return set(["EN_{0}".format(chr(code)) for code in range(65, 91)])

    @classmethod
    def required_symbol_layer_names(cls):
        return set(["SY_DASH", "SY_COLON"])

    @classmethod
    def required_pictogram_layer_names(cls):
        return set(PICTOGRAM_LAYER_NAMES)

    @classmethod
    def compound_layer_options(cls):
        options = {}
        for compound_code in sorted(HangulDecomposer.COMPOUND_COMPONENTS):
            component_codes = HangulDecomposer.COMPOUND_COMPONENTS[
                compound_code
            ]
            for layout in ("D", "F"):
                complete_name = "{0}{1}0".format(compound_code, layout)
                options[complete_name] = [
                    "{0}{1}0".format(component_codes[0], layout),
                    "{0}{1}0".format(component_codes[1], layout),
                ]
        return options

    @classmethod
    def required_layer_names(cls):
        return (
            cls.required_hangul_layer_names()
            | cls.required_english_layer_names()
            | cls.required_symbol_layer_names()
            | cls.required_pictogram_layer_names()
        )

    def _add_error(self, layer_name, message):
        self.errors.append(u"[ERROR] {0} : {1}".format(layer_name, message))

    def _add_warning(self, layer_name, message):
        self.warnings.append(u"[WARNING] {0} : {1}".format(layer_name, message))

    @staticmethod
    def _empty_record(layer_name):
        return {
            "name": layer_name,
            "curves": [],
            "bases": [],
            "extra_count": 0,
            "base_nonpoint_count": 0,
        }

    @staticmethod
    def _record_is_usable(record):
        return (
            record is not None
            and len(record["bases"]) == 1
            and len(record["curves"]) > 0
            and record["base_nonpoint_count"] == 0
        )

    @classmethod
    def _is_glyph_layer(cls, layer_name):
        return bool(
            cls.HANGUL_PATTERN.match(layer_name)
            or cls.ENGLISH_PATTERN.match(layer_name)
            or cls.SYMBOL_PATTERN.match(layer_name)
            or cls.PICTOGRAM_PATTERN.match(layer_name)
        )

    @classmethod
    def _cell_width(cls, layer_name):
        if layer_name == "SY_COLON":
            return 500.0
        return 1000.0

    def _warn_if_outside_master_cell(self, layer_name, record):
        if not self._record_is_usable(record):
            return
        if self.PICTOGRAM_PATTERN.match(layer_name):
            return

        bbox = rg.BoundingBox.Empty
        for curve in record["curves"]:
            bbox.Union(curve.GetBoundingBox(True))
        if not bbox.IsValid:
            return

        base = record["bases"][0]
        min_x = bbox.Min.X - base.X
        min_y = bbox.Min.Y - base.Y
        max_x = bbox.Max.X - base.X
        max_y = bbox.Max.Y - base.Y
        cell_width = self._cell_width(layer_name)
        cell_tolerance = 100.0

        if (
            min_x < -cell_tolerance
            or min_y < -cell_tolerance
            or max_x > cell_width + cell_tolerance
            or max_y > 3000.0 + cell_tolerance
        ):
            self._add_warning(
                layer_name,
                u"Curve BoundingBox가 {0:g} × 3000 셀을 크게 벗어납니다.".format(
                    cell_width
                )
            )

    def _cache_normalized_glyph(self, layer_name, record):
        if not self._record_is_usable(record):
            return

        base = record["bases"][0]
        move = rg.Transform.Translation(-base.X, -base.Y, -base.Z)
        normalized = []

        for source_curve in record["curves"]:
            curve = source_curve.DuplicateCurve()
            if curve is None:
                continue
            curve.Transform(move)
            normalized.append(curve)

        if normalized:
            self.glyphs[layer_name] = normalized

    def _collect_layers(self, model):
        records_by_index = {}
        records_by_name = {}
        name_counts = {}

        for layer in model.Layers:
            layer_name = layer.Name or u""
            if not self._is_glyph_layer(layer_name):
                if (
                    (layer_name and layer_name[0].isdigit())
                    or layer_name.startswith("EN_")
                    or layer_name.startswith("SY_")
                    or layer_name.startswith("PI_")
                ):
                    self._add_error(
                        layer_name,
                        u"글리프 레이어 이름 형식이 아닙니다."
                    )
                continue

            if layer.ParentLayerId != System.Guid.Empty:
                self._add_error(layer_name, u"최상위 단일 레이어가 아닙니다.")

            record = self._empty_record(layer_name)
            records_by_index[layer.Index] = record
            records_by_name[layer_name] = record
            name_counts[layer_name] = name_counts.get(layer_name, 0) + 1

        for layer_name in name_counts:
            if name_counts[layer_name] > 1:
                self._add_error(
                    layer_name,
                    u"동일한 레이어 이름이 {0}개 존재합니다.".format(
                        name_counts[layer_name]
                    )
                )

        return records_by_index, records_by_name

    def _collect_objects(self, model, records_by_index):
        for file_object in model.Objects:
            layer_index = file_object.Attributes.LayerIndex
            record = records_by_index.get(layer_index)
            if record is None:
                continue

            geometry = file_object.Geometry
            object_name = file_object.Attributes.Name or u""
            is_point = isinstance(geometry, rg.Point)
            is_curve = isinstance(geometry, rg.Curve)

            if object_name == "BASE" and not is_point:
                record["base_nonpoint_count"] += 1

            if is_point:
                if object_name == "BASE":
                    record["bases"].append(geometry.Location)
                else:
                    record["extra_count"] += 1
            elif is_curve:
                duplicate = geometry.DuplicateCurve()
                if duplicate is not None:
                    record["curves"].append(duplicate)
            else:
                record["extra_count"] += 1

    def _validate_required_record(self, layer_name, record):
        if record is None:
            self._add_error(layer_name, u"필수 레이어가 없습니다.")
            return

        if record["base_nonpoint_count"] > 0:
            self._add_error(layer_name, u"BASE 이름 객체가 Point가 아닙니다.")
        if len(record["bases"]) == 0:
            self._add_error(layer_name, u"BASE Point가 없습니다.")
        elif len(record["bases"]) > 1:
            self._add_error(
                layer_name,
                u"BASE Point가 {0}개 있습니다.".format(len(record["bases"]))
            )
        elif abs(record["bases"][0].Z) > 0.001:
            self._add_warning(layer_name, u"BASE의 Z값이 0이 아닙니다.")

        if not record["curves"]:
            self._add_error(layer_name, u"Curve가 없습니다.")
        if record["extra_count"] > 0:
            self._add_warning(
                layer_name,
                u"Curve/BASE 외 객체가 {0}개 있습니다.".format(
                    record["extra_count"]
                )
            )
        self._warn_if_outside_master_cell(layer_name, record)

    def _validate_compound_vowels(self, records_by_name):
        validated_components = set()
        for complete_name in sorted(self.compound_layer_options()):
            component_names = self.compound_layer_options()[complete_name]
            complete_record = records_by_name.get(complete_name)

            if self._record_is_usable(complete_record):
                self._validate_required_record(complete_name, complete_record)
                if all([
                    self._record_is_usable(records_by_name.get(name))
                    for name in component_names
                ]):
                    self._add_warning(
                        complete_name,
                        u"완성 복합모음과 부품 조합이 함께 있어 완성 글리프를 우선 사용합니다."
                    )
                continue

            if complete_record is not None:
                self._add_warning(
                    complete_name,
                    u"완성 복합모음 글리프가 유효하지 않아 부품 조합을 사용합니다."
                )

            for component_name in component_names:
                if component_name in validated_components:
                    continue
                self._validate_required_record(
                    component_name,
                    records_by_name.get(component_name)
                )
                validated_components.add(component_name)

    def load_and_validate(self):
        self.glyphs = {}
        self.errors = []
        self.warnings = []
        self.loaded = True

        if not os.path.exists(self.path):
            self._add_error(
                u"리소스",
                u"파일을 찾을 수 없습니다: {0}".format(self.path)
            )
            return False

        try:
            model = Rhino.FileIO.File3dm.Read(self.path)
        except Exception as error:
            self._add_error(u"리소스", u"3dm 읽기 실패: {0}".format(error))
            return False

        if model is None:
            self._add_error(u"리소스", u"3dm 읽기 결과가 비어 있습니다.")
            return False

        try:
            records_by_index, records_by_name = self._collect_layers(model)
            self._collect_objects(model, records_by_index)

            hangul_names = self.required_hangul_layer_names()
            english_names = self.required_english_layer_names()
            symbol_names = self.required_symbol_layer_names()
            pictogram_names = self.required_pictogram_layer_names()
            if len(hangul_names) != 239:
                self._add_error(
                    u"내부 규칙",
                    u"필수 한글 레이어 계산 결과가 239개가 아닙니다: {0}".format(
                        len(hangul_names)
                    )
                )
            if len(english_names) != 26:
                self._add_error(
                    u"내부 규칙",
                    u"필수 영문 레이어 계산 결과가 26개가 아닙니다: {0}".format(
                        len(english_names)
                    )
                )
            if len(symbol_names) != 2:
                self._add_error(
                    u"내부 규칙",
                    u"필수 기호 레이어 계산 결과가 2개가 아닙니다: {0}".format(
                        len(symbol_names)
                    )
                )
            if len(pictogram_names) != 6:
                self._add_error(
                    u"내부 규칙",
                    u"필수 픽토그램 레이어 계산 결과가 6개가 아닙니다: {0}".format(
                        len(pictogram_names)
                    )
                )

            required_names = (
                hangul_names
                | english_names
                | symbol_names
                | pictogram_names
            )
            compound_options = self.compound_layer_options()
            compound_component_names = set()
            for component_names in compound_options.values():
                compound_component_names.update(component_names)

            always_required_names = required_names - compound_component_names
            for layer_name in sorted(always_required_names):
                self._validate_required_record(
                    layer_name,
                    records_by_name.get(layer_name)
                )

            self._validate_compound_vowels(records_by_name)

            known_names = required_names | self.OPTIONAL_COMPOUND_LAYERS
            for layer_name in sorted(records_by_name):
                if layer_name not in known_names:
                    self._add_warning(
                        layer_name,
                        u"현재 조합 규칙에서 사용하지 않는 여분 레이어입니다."
                    )

            for layer_name in records_by_name:
                self._cache_normalized_glyph(
                    layer_name,
                    records_by_name[layer_name]
                )
        finally:
            try:
                model.Dispose()
            except Exception:
                pass

        return len(self.errors) == 0

    def has_glyph(self, layer_name):
        return layer_name in self.glyphs

    def duplicate_glyph(self, layer_name):
        source_curves = self.glyphs.get(layer_name)
        if not source_curves:
            return []
        return [curve.DuplicateCurve() for curve in source_curves]

    def error_report(self, max_items=30):
        if not self.errors:
            return u""

        shown = self.errors[:max_items]
        lines = [u"도로문자 글리프 라이브러리 검수에 실패했습니다.", u""]
        lines.extend(shown)
        if len(self.errors) > max_items:
            lines.append(u"... 외 {0}개 오류".format(len(self.errors) - max_items))
        lines.extend([u"", u"리소스 파일: {0}".format(self.path)])
        return u"\n".join(lines)
