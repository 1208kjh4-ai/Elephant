# -*- coding: utf-8 -*-
import unicodedata

from .errors import RoadTextError


class HangulDecomposer(object):
    """Decompose modern precomposed Hangul into road-font glyph codes."""

    CHO_CODES = [
        "01", "15", "02", "03", "16", "04", "05", "06", "17", "07",
        "18", "08", "09", "19", "10", "11", "12", "13", "14"
    ]
    CHO_JAMOS = [
        u"ㄱ", u"ㄲ", u"ㄴ", u"ㄷ", u"ㄸ", u"ㄹ", u"ㅁ", u"ㅂ", u"ㅃ",
        u"ㅅ", u"ㅆ", u"ㅇ", u"ㅈ", u"ㅉ", u"ㅊ", u"ㅋ", u"ㅌ", u"ㅍ",
        u"ㅎ"
    ]
    JUNG_CODES = [
        "31", "32", "33", "34", "35", "36", "37", "38", "40", "45",
        "46", "47", "41", "42", "48", "49", "50", "43", "44", "51",
        "39"
    ]
    JUNG_JAMOS = [
        u"ㅏ", u"ㅐ", u"ㅑ", u"ㅒ", u"ㅓ", u"ㅔ", u"ㅕ", u"ㅖ", u"ㅗ",
        u"ㅘ", u"ㅙ", u"ㅚ", u"ㅛ", u"ㅜ", u"ㅝ", u"ㅞ", u"ㅟ", u"ㅠ",
        u"ㅡ", u"ㅢ", u"ㅣ"
    ]
    JONG_CODES = [
        None, "01", "15", "20", "02", "21", "22", "03", "04", "23",
        "24", "25", "26", "27", "28", "29", "05", "06", "30", "07",
        "18", "08", "09", "10", "11", "12", "13", "14"
    ]
    JONG_JAMOS = [
        None, u"ㄱ", u"ㄲ", u"ㄳ", u"ㄴ", u"ㄵ", u"ㄶ", u"ㄷ", u"ㄹ",
        u"ㄺ", u"ㄻ", u"ㄼ", u"ㄽ", u"ㄾ", u"ㄿ", u"ㅀ", u"ㅁ", u"ㅂ",
        u"ㅄ", u"ㅅ", u"ㅆ", u"ㅇ", u"ㅈ", u"ㅊ", u"ㅋ", u"ㅌ", u"ㅍ",
        u"ㅎ"
    ]

    VERTICAL_VOWELS = set([
        "31", "32", "33", "34", "35", "36", "37", "38", "39"
    ])
    HORIZONTAL_VOWELS = set(["40", "41", "42", "43", "44"])
    COMPOUND_VOWELS = set(["45", "46", "47", "48", "49", "50", "51"])
    COMPOUND_COMPONENTS = {
        "45": ("40", "31"),
        "46": ("40", "32"),
        "47": ("40", "39"),
        "48": ("42", "35"),
        "49": ("42", "36"),
        "50": ("42", "39"),
        "51": ("44", "39"),
    }

    @classmethod
    def normalize_text(cls, text):
        if text is None:
            return u""
        return unicodedata.normalize("NFC", u"{0}".format(text))

    @classmethod
    def get_layout_type(cls, jung_code, has_jong):
        if jung_code in cls.VERTICAL_VOWELS:
            return "C" if has_jong else "A"
        if jung_code in cls.HORIZONTAL_VOWELS:
            return "E" if has_jong else "B"
        if jung_code in cls.COMPOUND_VOWELS:
            return "F" if has_jong else "D"
        raise RoadTextError(
            u"지원하지 않는 중성 코드입니다: {0}".format(jung_code)
        )

    @classmethod
    def decompose_syllable(cls, char):
        codepoint = ord(char)
        if codepoint < 0xAC00 or codepoint > 0xD7A3:
            raise RoadTextError(
                u"지원하지 않는 한글 문자입니다.\n\n"
                u"문자: {0}\nUnicode: U+{1:04X}".format(char, codepoint)
            )

        value = codepoint - 0xAC00
        cho_index = value // 588
        jung_index = (value % 588) // 28
        jong_index = value % 28
        has_jong = jong_index != 0
        jung_code = cls.JUNG_CODES[jung_index]

        return {
            "char": char,
            "cho_code": cls.CHO_CODES[cho_index],
            "cho_jamo": cls.CHO_JAMOS[cho_index],
            "jung_code": jung_code,
            "jung_jamo": cls.JUNG_JAMOS[jung_index],
            "jong_code": cls.JONG_CODES[jong_index],
            "jong_jamo": cls.JONG_JAMOS[jong_index],
            "has_jong": has_jong,
            "layout": cls.get_layout_type(jung_code, has_jong),
        }

