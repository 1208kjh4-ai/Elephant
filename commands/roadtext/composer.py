# -*- coding: utf-8 -*-
import os

import Rhino.Geometry as rg

from .digits import create_digit_curves
from .errors import RoadTextError
from .hangul import HangulDecomposer


HYPHEN_VARIANTS = {
    u"\u2010": u"-",  # hyphen
    u"\u2011": u"-",  # non-breaking hyphen
    u"\u2013": u"-",  # en dash
    u"\u2014": u"-",  # em dash
    u"\u2212": u"-",  # minus sign
    u"\uFF0D": u"-",  # full-width hyphen
}

COLON_VARIANTS = {
    u"\uFF1A": u":",  # full-width colon
}


class RoadTextComposer(object):
    """Compose Hangul, English, digits, and spaces in one ordered run."""

    HANGUL_ADVANCE = 1000.0
    ENGLISH_ADVANCE = 1000.0
    DIGIT_ADVANCE = 1000.0
    SPACE_ADVANCE = 500.0
    CELL_HEIGHT = 3000.0
    LINE_GAP = 500.0

    TYPE_HANGUL = "HANGUL"
    TYPE_ENGLISH = "ENGLISH"
    TYPE_DIGIT = "DIGIT"
    TYPE_SYMBOL = "SYMBOL"
    TYPE_SPACE = "SPACE"
    TYPE_UNSUPPORTED = "UNSUPPORTED"

    SYMBOL_LAYERS = {
        u"-": "SY_DASH",
        u":": "SY_COLON",
    }
    SYMBOL_ADVANCES = {
        u"-": 1000.0,
        u":": 500.0,
    }

    def __init__(self, library):
        self.library = library

    @staticmethod
    def normalize_text(text):
        normalized = HangulDecomposer.normalize_text(text)
        characters = []
        for char in normalized:
            char = HYPHEN_VARIANTS.get(char, char)
            char = COLON_VARIANTS.get(char, char)
            if u"a" <= char <= u"z":
                characters.append(char.upper())
            else:
                characters.append(char)
        return (
            u"".join(characters)
            .replace(u"\r\n", u"\n")
            .replace(u"\r", u"\n")
        )

    @classmethod
    def classify_character(cls, char):
        codepoint = ord(char)
        if 0xAC00 <= codepoint <= 0xD7A3:
            return cls.TYPE_HANGUL
        if u"A" <= char <= u"Z":
            return cls.TYPE_ENGLISH
        if u"0" <= char <= u"9":
            return cls.TYPE_DIGIT
        if char in cls.SYMBOL_LAYERS:
            return cls.TYPE_SYMBOL
        if char == u" ":
            return cls.TYPE_SPACE
        return cls.TYPE_UNSUPPORTED

    def _required_vowel_layers(self, info):
        jung_code = info["jung_code"]
        layout = info["layout"]
        complete_name = "{0}{1}0".format(jung_code, layout)

        if (
            jung_code in HangulDecomposer.COMPOUND_COMPONENTS
            and self.library.has_glyph(complete_name)
        ):
            return [complete_name]

        if jung_code in HangulDecomposer.COMPOUND_COMPONENTS:
            component_codes = HangulDecomposer.COMPOUND_COMPONENTS[jung_code]
            return [
                "{0}{1}0".format(component_codes[0], layout),
                "{0}{1}0".format(component_codes[1], layout),
            ]

        return [complete_name]

    def _missing_hangul_glyph_error(self, info, layer_name):
        jong_jamo = info["jong_jamo"] if info["jong_jamo"] else u"없음"
        return RoadTextError(
            u"도로문자 생성에 필요한 한글 글리프가 없습니다.\n\n"
            u"입력 문자: {0}\n"
            u"초성: {1}\n"
            u"중성: {2}\n"
            u"종성: {3}\n"
            u"조합 유형: {4}\n"
            u"누락 레이어: {5}\n"
            u"리소스 파일: {6}".format(
                info["char"],
                info["cho_jamo"],
                info["jung_jamo"],
                jong_jamo,
                info["layout"],
                layer_name,
                os.path.basename(self.library.path),
            )
        )

    def _compose_hangul(self, char):
        info = HangulDecomposer.decompose_syllable(char)
        layout = info["layout"]
        layer_names = ["{0}{1}1".format(info["cho_code"], layout)]
        layer_names.extend(self._required_vowel_layers(info))
        if info["has_jong"]:
            layer_names.append("{0}{1}2".format(info["jong_code"], layout))

        curves = []
        for layer_name in layer_names:
            glyph_curves = self.library.duplicate_glyph(layer_name)
            if not glyph_curves:
                raise self._missing_hangul_glyph_error(info, layer_name)
            curves.extend(glyph_curves)
        return curves

    def _compose_english(self, char):
        layer_name = "EN_{0}".format(char)
        curves = self.library.duplicate_glyph(layer_name)
        if not curves:
            raise RoadTextError(
                u"도로문자 생성에 필요한 영문 글리프가 없습니다.\n\n"
                u"입력 문자: {0}\n"
                u"누락 레이어: {1}\n"
                u"리소스 파일: {2}".format(
                    char,
                    layer_name,
                    os.path.basename(self.library.path),
                )
            )
        return curves

    def _compose_symbol(self, char):
        layer_name = self.SYMBOL_LAYERS[char]
        curves = self.library.duplicate_glyph(layer_name)
        if not curves:
            raise RoadTextError(
                u"도로문자 생성에 필요한 기호 글리프가 없습니다.\n\n"
                u"입력 문자: {0}\n"
                u"누락 레이어: {1}\n"
                u"리소스 파일: {2}".format(
                    char,
                    layer_name,
                    os.path.basename(self.library.path),
                )
            )
        return curves

    def compose_character(self, char):
        character_type = self.classify_character(char)

        if character_type == self.TYPE_HANGUL:
            curves = self._compose_hangul(char)
            advance_width = self.HANGUL_ADVANCE
        elif character_type == self.TYPE_ENGLISH:
            curves = self._compose_english(char)
            advance_width = self.ENGLISH_ADVANCE
        elif character_type == self.TYPE_DIGIT:
            curves = create_digit_curves(char)
            if not curves:
                raise RoadTextError(
                    u"기존 숫자 Curve 데이터를 찾을 수 없습니다.\n\n"
                    u"입력 문자: {0}".format(char)
                )
            advance_width = self.DIGIT_ADVANCE
        elif character_type == self.TYPE_SYMBOL:
            curves = self._compose_symbol(char)
            advance_width = self.SYMBOL_ADVANCES[char]
        elif character_type == self.TYPE_SPACE:
            curves = []
            advance_width = self.SPACE_ADVANCE
        else:
            return None

        return {
            "curves": curves,
            "advance_width": advance_width,
            "character": char,
            "character_type": character_type,
        }

    @staticmethod
    def _unsupported_character_error(char, position, line_number=None):
        if line_number is not None:
            location = u"줄: {0}\n문자 위치: {1}".format(
                line_number,
                position
            )
        else:
            location = u"문자열 위치: {0}".format(position)
        return RoadTextError(
            u"지원하지 않는 문자가 포함되어 있습니다.\n\n"
            u"{0}\n"
            u"문자: {1}\n"
            u"Unicode: U+{2:04X}".format(location, char, ord(char))
        )

    def _compose_line(
        self,
        text_line,
        line_number,
        baseline_y,
        target_width,
        alignment,
        letter_gap
    ):
        glyph_items = []
        natural_width = 0.0
        for index, char in enumerate(text_line):
            item = self.compose_character(char)
            if item is None:
                raise self._unsupported_character_error(
                    char,
                    index + 1,
                    line_number
                )
            glyph_items.append(item)
            natural_width += item["advance_width"]

        if not glyph_items:
            return []

        if len(glyph_items) > 1:
            natural_width += letter_gap * (len(glyph_items) - 1)

        layout_width = natural_width
        layout_gap = letter_gap
        if (
            alignment == "justify"
            and target_width is not None
            and target_width > natural_width
            and len(glyph_items) > 1
        ):
            layout_gap += (
                (target_width - natural_width) / (len(glyph_items) - 1)
            )
            layout_width = target_width

        curves = []
        cursor_x = -layout_width / 2.0
        for item_index, item in enumerate(glyph_items):
            move = rg.Transform.Translation(cursor_x, baseline_y, 0.0)
            for curve in item["curves"]:
                curve.Transform(move)
                curves.append(curve)
            cursor_x += item["advance_width"]
            if item_index < len(glyph_items) - 1:
                cursor_x += layout_gap

        if target_width is not None and layout_width > target_width:
            scale_x = target_width / layout_width
            scale = rg.Transform.Scale(
                rg.Plane.WorldXY,
                scale_x,
                1.0,
                1.0
            )
            for curve in curves:
                curve.Transform(scale)

        return curves

    def compose_text(
        self,
        text,
        target_width=None,
        alignment="center",
        letter_gap=0.0
    ):
        if alignment not in ("center", "justify"):
            raise RoadTextError(
                u"지원하지 않는 문자 정렬 방식입니다: {0}".format(alignment)
            )
        if letter_gap is None:
            letter_gap = 0.0
        if letter_gap < 0.0:
            raise RoadTextError(u"자간은 0 이상이어야 합니다.")
        if target_width is not None and target_width <= 0.0:
            raise RoadTextError(u"목표 폭은 0보다 커야 합니다.")

        normalized = (
            self.normalize_text(text)
            .replace(u"\r\n", u"\n")
            .replace(u"\r", u"\n")
        )
        if not normalized:
            raise RoadTextError(u"도로문자 문자열을 입력해주세요.")
        if not normalized.strip():
            raise RoadTextError(u"공백만 있는 문자열은 생성할 수 없습니다.")

        curves = []
        text_lines = normalized.split(u"\n")
        block_height = (
            len(text_lines) * self.CELL_HEIGHT
            + max(0, len(text_lines) - 1) * self.LINE_GAP
        )

        for line_index, text_line in enumerate(text_lines):
            baseline_y = (
                block_height / 2.0
                - self.CELL_HEIGHT
                - line_index * (self.CELL_HEIGHT + self.LINE_GAP)
            )
            curves.extend(
                self._compose_line(
                    text_line,
                    line_index + 1,
                    baseline_y,
                    target_width,
                    alignment,
                    letter_gap
                )
            )

        if not curves:
            raise RoadTextError(u"생성할 수 있는 도로문자 Curve가 없습니다.")

        return curves
