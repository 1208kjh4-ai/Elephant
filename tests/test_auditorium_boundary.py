# -*- coding: utf-8 -*-
"""Rhino-free tests for the optional auditorium plan-boundary core."""

import ast
import unittest
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]
BOUNDARY_PATH = (
    ROOT
    / "commands"
    / "auditorium_generator"
    / "auditorium_boundary.py"
)


class _FakePoint3d(object):
    def __init__(self, *args):
        if len(args) == 1:
            source = args[0]
            self.X = float(source.X)
            self.Y = float(source.Y)
            self.Z = float(source.Z)
        elif len(args) == 3:
            self.X = float(args[0])
            self.Y = float(args[1])
            self.Z = float(args[2])
        else:
            raise TypeError("Point3d expects one point or three coordinates")

    @property
    def IsValid(self):
        coordinates = (self.X, self.Y, self.Z)
        return all(
            value == value
            and value != float("inf")
            and value != float("-inf")
            for value in coordinates
        )


class _FakeVector(object):
    def __init__(self, name, parallel_to_z=0):
        self.name = name
        self.parallel_to_z = int(parallel_to_z)

    def IsParallelTo(self, other, angle_tolerance):
        if other is not _FakeVector3d.ZAxis:
            return 0
        if angle_tolerance <= 0.0:
            return 0
        return self.parallel_to_z


class _FakeVector3d(object):
    XAxis = _FakeVector("x")
    YAxis = _FakeVector("y")
    ZAxis = _FakeVector("z", parallel_to_z=1)


class _FakePlane(object):
    def __init__(self, origin, x_axis, y_axis):
        self.Origin = _FakePoint3d(origin)
        self.XAxis = x_axis
        self.YAxis = y_axis
        self.Normal = _FakeVector("horizontal", parallel_to_z=1)
        self.IsValid = self.Origin.IsValid
        self.closest_point_calls = []

    def ClosestPoint(self, point):
        copied = _FakePoint3d(point.X, point.Y, self.Origin.Z)
        self.closest_point_calls.append((point, copied))
        return copied


class _FakeBoundingBox(object):
    def __init__(self, valid=True):
        self.IsValid = bool(valid)


class _FakeAreaProperties(object):
    def __init__(self, area):
        self.Area = area
        self.disposed = False

    def Dispose(self):
        self.disposed = True


class _FakeCurve(object):
    def __init__(
        self,
        is_valid=True,
        is_closed=True,
        is_planar=True,
        parallel_direction=1,
        z_value=25.0,
        intersections=None,
        area=2400.0,
        projection_fails=False,
        bbox_valid=True,
        contains_result="inside",
    ):
        self.IsValid = bool(is_valid)
        self.IsClosed = bool(is_closed)
        self.is_planar = bool(is_planar)
        self.parallel_direction = int(parallel_direction)
        self.z_value = float(z_value)
        self.intersections = (
            [] if intersections is None else intersections
        )
        self.area = area
        self.projection_fails = bool(projection_fails)
        self.bbox_valid = bool(bbox_valid)
        self.contains_result = contains_result
        self.try_get_plane_calls = []
        self.duplicate_calls = 0
        self.last_duplicate = None
        self.contains_calls = []
        self.mutations = []

    def _clone(self):
        clone = _FakeCurve(
            is_valid=self.IsValid,
            is_closed=self.IsClosed,
            is_planar=self.is_planar,
            parallel_direction=self.parallel_direction,
            z_value=self.z_value,
            intersections=self.intersections,
            area=self.area,
            projection_fails=self.projection_fails,
            bbox_valid=self.bbox_valid,
            contains_result=self.contains_result,
        )
        return clone

    def TryGetPlane(self, *args):
        self.try_get_plane_calls.append(args)
        plane = SimpleNamespace(
            IsValid=True,
            Normal=_FakeVector(
                "source-normal",
                parallel_to_z=self.parallel_direction,
            ),
        )
        return self.is_planar, plane

    def DuplicateCurve(self):
        self.duplicate_calls += 1
        self.last_duplicate = self._clone()
        return self.last_duplicate

    def GetBoundingBox(self, accurate):
        if accurate is not True:
            raise AssertionError("an accurate bounding box was expected")
        return _FakeBoundingBox(self.bbox_valid)

    def Contains(self, point, plane, tolerance):
        self.contains_calls.append((point, plane, tolerance))
        if callable(self.contains_result):
            return self.contains_result(point)
        return self.contains_result


class _FakeCurveApi(object):
    projection_calls = []

    @classmethod
    def ProjectToPlane(cls, curve, plane):
        cls.projection_calls.append((curve, plane))
        if curve.projection_fails:
            return None
        projected = curve._clone()
        projected.z_value = plane.Origin.Z
        projected.projected_from = curve
        return projected


class _FakeIntersectionApi(object):
    calls = []

    @classmethod
    def CurveSelf(cls, curve, tolerance):
        cls.calls.append((curve, tolerance))
        return curve.intersections


class _FakeAreaMassPropertiesApi(object):
    calls = []
    results = []

    @classmethod
    def Compute(cls, curve, tolerance):
        cls.calls.append((curve, tolerance))
        if curve.area is None:
            return None
        result = _FakeAreaProperties(curve.area)
        cls.results.append(result)
        return result


class _FakePointContainment(object):
    Inside = "inside"
    Coincident = "coincident"
    Outside = "outside"
    Unset = "unset"


FAKE_RG = SimpleNamespace(
    Point3d=_FakePoint3d,
    Vector3d=_FakeVector3d,
    Plane=_FakePlane,
    Curve=_FakeCurveApi,
    AreaMassProperties=_FakeAreaMassPropertiesApi,
    Intersect=SimpleNamespace(
        Intersection=_FakeIntersectionApi,
    ),
    PointContainment=_FakePointContainment,
)


def _load_boundary_module():
    tree = ast.parse(
        BOUNDARY_PATH.read_text(encoding="utf-8-sig"),
        filename=str(BOUNDARY_PATH),
    )
    body = [
        node
        for node in tree.body
        if not isinstance(node, (ast.Import, ast.ImportFrom))
    ]
    selected = ast.fix_missing_locations(
        ast.Module(body=body, type_ignores=[])
    )
    namespace = {
        "__builtins__": __builtins__,
        "rg": FAKE_RG,
    }
    exec(compile(selected, str(BOUNDARY_PATH), "exec"), namespace)
    return namespace


class AuditoriumBoundaryNormalizationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = _load_boundary_module()

    def setUp(self):
        _FakeCurveApi.projection_calls = []
        _FakeIntersectionApi.calls = []
        _FakeAreaMassPropertiesApi.calls = []
        _FakeAreaMassPropertiesApi.results = []
        self.datum = _FakePoint3d(100.0, 200.0, 375.0)

    def normalize(self, curve, tolerance=0.01):
        return self.module["normalize_boundary_curve"](
            curve,
            self.datum,
            tolerance,
        )

    def test_valid_curve_is_copied_and_projected_without_mutating_source(self):
        source = _FakeCurve(z_value=42.0, parallel_direction=-1)
        source_state = (source.z_value, list(source.mutations))

        normalized = self.normalize(source)

        self.assertIsNot(normalized, source)
        self.assertIsNot(normalized, source.last_duplicate)
        self.assertEqual(source.duplicate_calls, 1)
        self.assertIs(
            _FakeCurveApi.projection_calls[0][0],
            source.last_duplicate,
        )
        self.assertEqual(normalized.z_value, self.datum.Z)
        self.assertEqual(
            (source.z_value, source.mutations),
            source_state,
        )
        self.assertEqual(source.try_get_plane_calls, [(0.01,)])
        self.assertIs(
            _FakeIntersectionApi.calls[0][0],
            normalized,
        )
        self.assertTrue(_FakeAreaMassPropertiesApi.results[0].disposed)

    def test_build_context_contains_normalized_plan_metadata(self):
        source = _FakeCurve(area=9876.5)

        context = self.module["build_boundary_context"](
            source,
            self.datum,
            0.025,
        )

        self.assertEqual(
            set(context),
            {"curve", "plane", "bbox", "area", "tolerance"},
        )
        self.assertIsNot(context["curve"], source)
        self.assertEqual(context["curve"].z_value, self.datum.Z)
        self.assertEqual(context["plane"].Origin.Z, self.datum.Z)
        self.assertTrue(context["bbox"].IsValid)
        self.assertEqual(context["area"], 9876.5)
        self.assertEqual(context["tolerance"], 0.025)

    def test_none_boundary_builds_no_context(self):
        context = self.module["build_boundary_context"](
            None,
            None,
            None,
        )
        self.assertIsNone(context)

    def test_basic_invalid_boundaries_raise_clear_value_errors(self):
        invalid_cases = (
            (None, "required"),
            (_FakeCurve(is_valid=False), "not valid"),
            (_FakeCurve(is_closed=False), "closed"),
            (_FakeCurve(is_planar=False), "planar"),
            (_FakeCurve(parallel_direction=0), "horizontal"),
            (_FakeCurve(intersections=[object()]), "intersect itself"),
            (_FakeCurve(area=0.0001), "positive area"),
            (_FakeCurve(projection_fails=True), "projected"),
            (_FakeCurve(bbox_valid=False), "bounding box"),
        )
        for curve, expected_text in invalid_cases:
            with self.subTest(expected_text=expected_text):
                with self.assertRaisesRegex(ValueError, expected_text):
                    self.normalize(curve)

    def test_invalid_tolerance_and_datum_are_rejected(self):
        invalid_tolerances = (0.0, -0.1, float("nan"), float("inf"))
        for tolerance in invalid_tolerances:
            with self.subTest(tolerance=tolerance):
                with self.assertRaisesRegex(ValueError, "tolerance"):
                    self.normalize(_FakeCurve(), tolerance)

        with self.assertRaisesRegex(ValueError, "datum point"):
            self.module["normalize_boundary_curve"](
                _FakeCurve(),
                _FakePoint3d(float("nan"), 0.0, 0.0),
                0.01,
            )

    def test_plane_query_failures_are_reported_as_validation_errors(self):
        class PlaneQueryFailure(object):
            IsValid = True
            IsClosed = True

            def TryGetPlane(self, *args):
                if args:
                    raise TypeError("tolerance overload unavailable")
                raise RuntimeError("plane query failed")

        with self.assertRaisesRegex(ValueError, "planar"):
            self.normalize(PlaneQueryFailure())


class AuditoriumBoundaryContainmentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = _load_boundary_module()

    def make_context(self, result):
        curve = _FakeCurve(contains_result=result)
        plane = _FakePlane(
            _FakePoint3d(0.0, 0.0, 125.0),
            _FakeVector3d.XAxis,
            _FakeVector3d.YAxis,
        )
        return {
            "curve": curve,
            "plane": plane,
            "bbox": _FakeBoundingBox(),
            "area": 100.0,
            "tolerance": 0.01,
        }

    def test_point_is_projected_to_plan_before_inside_test(self):
        context = self.make_context(_FakePointContainment.Inside)
        source_point = _FakePoint3d(2.0, 3.0, 9000.0)

        contained = self.module["boundary_contains_point"](
            context,
            source_point,
        )

        self.assertTrue(contained)
        tested_point, tested_plane, tolerance = (
            context["curve"].contains_calls[0]
        )
        self.assertEqual((tested_point.X, tested_point.Y), (2.0, 3.0))
        self.assertEqual(tested_point.Z, 125.0)
        self.assertIs(tested_plane, context["plane"])
        self.assertEqual(tolerance, 0.01)
        self.assertEqual(source_point.Z, 9000.0)

    def test_boundary_coincidence_respects_include_boundary(self):
        context = self.make_context(_FakePointContainment.Coincident)
        point = _FakePoint3d(0.0, 0.0, 0.0)

        self.assertTrue(
            self.module["boundary_contains_point"](context, point)
        )
        self.assertFalse(
            self.module["boundary_contains_point"](
                context,
                point,
                include_boundary=False,
            )
        )

    def test_outside_and_unset_results_are_distinct(self):
        point = _FakePoint3d(0.0, 0.0, 0.0)
        outside = self.make_context(_FakePointContainment.Outside)
        self.assertFalse(
            self.module["boundary_contains_point"](outside, point)
        )

        unset = self.make_context(_FakePointContainment.Unset)
        with self.assertRaisesRegex(ValueError, "could not be determined"):
            self.module["boundary_contains_point"](unset, point)

    def test_points_requires_every_point_to_be_contained(self):
        def result_for_point(point):
            if point.X < 0.0:
                return _FakePointContainment.Outside
            return _FakePointContainment.Inside

        context = self.make_context(result_for_point)
        contains_points = self.module["boundary_contains_points"]

        self.assertTrue(
            contains_points(
                context,
                [_FakePoint3d(1.0, 0.0, 1.0),
                 _FakePoint3d(2.0, 0.0, 2.0)],
            )
        )
        self.assertFalse(
            contains_points(
                context,
                [_FakePoint3d(1.0, 0.0, 1.0),
                 _FakePoint3d(-1.0, 0.0, 2.0)],
            )
        )
        self.assertTrue(contains_points(context, []))

    def test_no_context_is_an_unrestricted_boundary(self):
        self.assertTrue(
            self.module["boundary_contains_point"](None, None)
        )
        self.assertTrue(
            self.module["boundary_contains_points"](None, None)
        )

    def test_invalid_points_and_contexts_raise_value_errors(self):
        context = self.make_context(_FakePointContainment.Inside)
        with self.assertRaisesRegex(ValueError, "test point"):
            self.module["boundary_contains_point"](context, None)
        with self.assertRaisesRegex(ValueError, "test points"):
            self.module["boundary_contains_points"](context, None)
        with self.assertRaisesRegex(ValueError, "incomplete"):
            self.module["boundary_contains_point"](
                {},
                _FakePoint3d(0.0, 0.0, 0.0),
            )


if __name__ == "__main__":
    unittest.main()
