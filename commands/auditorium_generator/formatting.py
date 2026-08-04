# -*- coding: utf-8 -*-
"""Pure text formatting helpers for auditorium dimensions."""


def format_riser_height_label(height_mm):
    rounded_height = round(height_mm)
    if abs(height_mm - rounded_height) <= 0.05:
        return "H {0:.0f} mm".format(height_mm)
    return "H {0:.1f} mm".format(height_mm)


def format_section_height_dimension(height_mm):
    rounded_height = round(height_mm)
    if abs(height_mm - rounded_height) <= 0.05:
        return "H {0:,.0f} mm".format(height_mm)
    return "H {0:,.1f} mm".format(height_mm)
