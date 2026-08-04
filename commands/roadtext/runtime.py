# -*- coding: utf-8 -*-
import os

import Rhino

from .digits import reset_digit_data
from .errors import RoadTextError
from .library import RoadGlyphLibrary


COMMANDS_DIR = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
ELEPHANT_DIR = os.path.dirname(COMMANDS_DIR)
ROAD_FONT_PATH = os.path.join(ELEPHANT_DIR, "korroadfont.3dm")

_ROAD_GLYPH_LIBRARY = None


def reset_road_glyph_library():
    global _ROAD_GLYPH_LIBRARY
    _ROAD_GLYPH_LIBRARY = None
    reset_digit_data()


def get_road_glyph_library():
    global _ROAD_GLYPH_LIBRARY

    if _ROAD_GLYPH_LIBRARY is None:
        library = RoadGlyphLibrary(ROAD_FONT_PATH)
        library.load_and_validate()
        _ROAD_GLYPH_LIBRARY = library

        for warning in library.warnings:
            Rhino.RhinoApp.WriteLine(warning)

        if not library.errors:
            Rhino.RhinoApp.WriteLine(
                u"[OK] 한글 {0}개, 영문 {1}개, 기호 {2}개, 픽토그램 {3}개 레이어 확인 완료".format(
                    len(library.required_hangul_layer_names()),
                    len(library.required_english_layer_names()),
                    len(library.required_symbol_layer_names()),
                    len(library.required_pictogram_layer_names())
                )
            )

    if _ROAD_GLYPH_LIBRARY.errors:
        raise RoadTextError(_ROAD_GLYPH_LIBRARY.error_report())

    return _ROAD_GLYPH_LIBRARY
