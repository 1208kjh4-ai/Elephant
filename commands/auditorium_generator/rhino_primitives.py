# -*- coding: utf-8 -*-
"""Foundational Rhino geometry helpers for the auditorium command."""

import Rhino
import Rhino.Geometry as rg


def unit_scale_from_mm(doc):
    """Return model-unit length corresponding to 1 millimeter."""
    return Rhino.RhinoMath.UnitScale(
        Rhino.UnitSystem.Millimeters,
        doc.ModelUnitSystem
    )


def point_at(stage_point, audience_direction, x_mm, z_mm, mm_scale):
    return (
        stage_point
        + audience_direction * (x_mm * mm_scale)
        + rg.Vector3d.ZAxis * (z_mm * mm_scale)
    )


def line_curve(point_a, point_b):
    return rg.LineCurve(point_a, point_b)


def stage_space_point(
    stage_point,
    stage_right_direction,
    stage_back_direction,
    x_mm,
    y_mm,
    z_mm,
    mm_scale
):
    return (
        stage_point
        + stage_right_direction * (x_mm * mm_scale)
        + stage_back_direction * (y_mm * mm_scale)
        + rg.Vector3d.ZAxis * (z_mm * mm_scale)
    )


def build_plan_rectangle(
    stage_point,
    stage_right_direction,
    stage_back_direction,
    min_x_mm,
    max_x_mm,
    min_y_mm,
    max_y_mm,
    mm_scale,
    z_mm=0.0
):
    """Create a closed rectangle at a stage-relative Z level."""
    def plan_point(x_mm, y_mm):
        return stage_space_point(
            stage_point,
            stage_right_direction,
            stage_back_direction,
            x_mm,
            y_mm,
            z_mm,
            mm_scale
        )

    points = [
        plan_point(min_x_mm, min_y_mm),
        plan_point(max_x_mm, min_y_mm),
        plan_point(max_x_mm, max_y_mm),
        plan_point(min_x_mm, max_y_mm),
        plan_point(min_x_mm, min_y_mm),
    ]
    return rg.PolylineCurve(points)


def get_stage_directions(audience_direction):
    """Return audience-view right and stage-back unit vectors.

    Left/right is defined from the audience looking toward the stage. For an
    audience direction pointing from the stage toward the seats, that right
    vector is ``World Z x audience_direction``.
    """
    stage_back_direction = rg.Vector3d(audience_direction)
    stage_back_direction.Reverse()

    audience_view_right_direction = rg.Vector3d.CrossProduct(
        rg.Vector3d.ZAxis,
        audience_direction
    )
    if not audience_view_right_direction.Unitize():
        raise ValueError("무대 평면의 좌우 방향을 계산할 수 없습니다.")

    return audience_view_right_direction, stage_back_direction
