# -*- coding: utf-8 -*-
"""Rhino command point input, dialog launch, and bake orchestration."""

import Rhino
import Rhino.Geometry as rg
import Rhino.Input.Custom as ric
import Rhino.Commands as rc
import Rhino.UI

from .main_dialog import AuditoriumDialog
from .auditorium_boundary import normalize_boundary_curve
from .opening_geometry import analyze_reference_baseline
from .seat_source import load_auditorium_seat_source
from .document_baking import bake_preview


def select_reference_baseline(doc=None):
    """
    Get the audience-floor reference line from two points.

    Point order is audience-view left, then audience-view right. The second
    point is constrained to the horizontal plane through the first point.
    """
    if doc is None:
        doc = Rhino.RhinoDoc.ActiveDoc

    first_getter = ric.GetPoint()
    first_getter.SetCommandPrompt(
        "Reference line: pick the LEFT point as viewed from the audience "
        "toward the stage"
    )
    first_getter.Get()
    if first_getter.CommandResult() != rc.Result.Success:
        return None

    reference_start = rg.Point3d(first_getter.Point())

    second_getter = ric.GetPoint()
    second_getter.SetCommandPrompt(
        "Reference line: pick the RIGHT point as viewed from the audience "
        "toward the stage"
    )
    second_getter.SetBasePoint(reference_start, True)
    second_getter.DrawLineFromPoint(reference_start, True)
    horizontal_plane = rg.Plane(reference_start, rg.Vector3d.ZAxis)
    second_getter.Constrain(horizontal_plane, False)
    second_getter.Get()
    if second_getter.CommandResult() != rc.Result.Success:
        return None

    reference_end = rg.Point3d(second_getter.Point())

    # Constrain() normally makes these equal. Keep a strict validation here so
    # scripted or future alternate input paths cannot introduce a sloped datum.
    tolerance = 1e-6
    if doc is not None:
        tolerance = max(float(doc.ModelAbsoluteTolerance), tolerance)
    if abs(reference_end.Z - reference_start.Z) > tolerance:
        raise ValueError(
            "The reference line must be horizontal. "
            "Choose both points on the same Z level."
        )
    reference_end.Z = reference_start.Z

    return reference_start, reference_end


def select_opening_curve():
    """
    Compatibility wrapper for scripts importing the previous selector name.

    It now performs the two-point baseline input and returns a LineCurve.
    """
    points = select_reference_baseline(Rhino.RhinoDoc.ActiveDoc)
    if points is None:
        return None
    return rg.LineCurve(points[0], points[1])


def select_optional_auditorium_boundary(doc, datum_point):
    """Legacy standalone boundary picker retained for compatibility.

    The command now opens the main dialog immediately after the reference
    baseline; new boundary selection is handled from that dialog.
    """
    getter = ric.GetObject()
    getter.SetCommandPrompt(
        "Select a closed auditorium boundary curve, or press Enter to skip"
    )
    getter.GeometryFilter = Rhino.DocObjects.ObjectType.Curve
    getter.AcceptNothing(True)

    result = getter.Get()
    if result == Rhino.Input.GetResult.Nothing:
        return True, None
    if result != Rhino.Input.GetResult.Object:
        return False, None

    object_reference = getter.Object(0)
    curve = None if object_reference is None else object_reference.Curve()
    if curve is None:
        return False, None

    tolerance = max(float(doc.ModelAbsoluteTolerance), 1e-6)
    try:
        boundary_curve = normalize_boundary_curve(
            curve,
            datum_point,
            tolerance,
        )
    except Exception as error:
        Rhino.UI.Dialogs.ShowMessageBox(
            str(error),
            "Auditorium Boundary"
        )
        return False, None

    if boundary_curve is None:
        return False, None
    return True, boundary_curve


def show_dialog_semi_modal(dialog, doc):
    try:
        Rhino.UI.EtoExtensions.ShowSemiModal(
            dialog,
            doc,
            Rhino.UI.RhinoEtoApp.MainWindow
        )
    except Exception:
        dialog.ShowModal(Rhino.UI.RhinoEtoApp.MainWindow)


def main():
    doc = Rhino.RhinoDoc.ActiveDoc
    if doc is None:
        return

    try:
        reference_points = select_reference_baseline(doc)
        if reference_points is None:
            return
        stage_data = analyze_reference_baseline(
            reference_points[0],
            reference_points[1],
            doc,
        )
    except Exception as error:
        Rhino.UI.Dialogs.ShowMessageBox(
            str(error),
            "Auditorium Section Generator"
        )
        return

    seat_source = None
    try:
        seat_source = load_auditorium_seat_source()
    except Exception as error:
        Rhino.UI.Dialogs.ShowMessageBox(
            (
                "The 3D seat source could not be loaded.\n\n{0}\n\n"
                "The section generator will remain available without "
                "3D seat modules."
            ).format(error),
            "Auditorium 3D Seat Source"
        )

    dialog = AuditoriumDialog(stage_data, doc, seat_source)

    try:
        show_dialog_semi_modal(dialog, doc)
    finally:
        dialog.disable_preview()

    if not dialog.accepted or dialog.preview_data is None:
        return

    bake_preview(dialog.preview_data, doc)
