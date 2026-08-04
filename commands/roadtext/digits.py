# -*- coding: utf-8 -*-
import io
import json
import os

import Rhino.Geometry as rg

from .errors import RoadTextError


COMMANDS_DIR = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
ELEPHANT_DIR = os.path.dirname(COMMANDS_DIR)
DIGIT_DATA_PATH = os.path.join(ELEPHANT_DIR, "RoadMarkDB.json")
REQUIRED_DIGITS = set(u"0123456789")

_DIGIT_DATA = None


def reset_digit_data():
    global _DIGIT_DATA
    _DIGIT_DATA = None


def _validate_digit_data(digits):
    if not isinstance(digits, dict):
        raise RoadTextError(u"숫자 데이터 형식이 올바르지 않습니다.")

    missing = sorted(REQUIRED_DIGITS - set(digits.keys()))
    if missing:
        raise RoadTextError(
            u"숫자 데이터가 누락되었습니다: {0}".format(u", ".join(missing))
        )

    for digit in sorted(REQUIRED_DIGITS):
        polylines = digits.get(digit)
        if not isinstance(polylines, list) or not polylines:
            raise RoadTextError(
                u"숫자 {0}의 Curve 데이터가 없습니다.".format(digit)
            )
        for polyline in polylines:
            if not isinstance(polyline, list) or len(polyline) < 2:
                raise RoadTextError(
                    u"숫자 {0}의 Polyline 데이터가 올바르지 않습니다.".format(
                        digit
                    )
                )
            for point in polyline:
                if not isinstance(point, list) or len(point) < 2:
                    raise RoadTextError(
                        u"숫자 {0}의 Point 데이터가 올바르지 않습니다.".format(
                            digit
                        )
                    )


def get_digit_data():
    global _DIGIT_DATA

    if _DIGIT_DATA is None:
        if not os.path.exists(DIGIT_DATA_PATH):
            raise RoadTextError(
                u"기존 숫자 데이터 파일을 찾을 수 없습니다.\n\n{0}".format(
                    DIGIT_DATA_PATH
                )
            )
        try:
            with io.open(DIGIT_DATA_PATH, "r", encoding="utf-8") as stream:
                document = json.load(stream)
        except Exception as error:
            raise RoadTextError(
                u"기존 숫자 데이터 파일을 읽지 못했습니다.\n\n{0}".format(
                    error
                )
            )

        digits = document.get("DIGITS") if isinstance(document, dict) else None
        _validate_digit_data(digits)
        _DIGIT_DATA = digits

    return _DIGIT_DATA


def has_digit(char):
    return char in get_digit_data()


def create_digit_curves(char):
    polylines = get_digit_data().get(char)
    if not polylines:
        return []

    curves = []
    for polyline in polylines:
        points = []
        for coordinates in polyline:
            z_value = coordinates[2] if len(coordinates) > 2 else 0.0
            points.append(
                rg.Point3d(
                    float(coordinates[0]),
                    float(coordinates[1]),
                    float(z_value)
                )
            )
        curves.append(rg.Polyline(points).ToPolylineCurve())
    return curves

