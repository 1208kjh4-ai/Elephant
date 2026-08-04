# -*- coding: utf-8 -*-
"""Rhino-free tests for custom-boundary row clipping primitives."""

import ast
import copy
import math
import unittest
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = (
    ROOT
    / "commands"
    / "auditorium_generator"
    / "boundary_row_layout.py"
)


class FakeVector(object):
    def __init__(self, x=0.0, y=0.0, z=0.0):
        if isinstance(x, FakeVector):
            self.X, self.Y, self.Z = x.X, x.Y, x.Z
        elif hasattr(x, "X") and y == 0.0 and z == 0.0:
            self.X, self.Y, self.Z = float(x.X), float(x.Y), float(x.Z)
        else:
            self.X, self.Y, self.Z = float(x), float(y), float(z)

    @property
    def Length(self):
        return math.sqrt(self.X ** 2 + self.Y ** 2 + self.Z ** 2)

    def Unitize(self):
        length = self.Length
        if length <= 1e-14:
            return False
        self.X /= length
        self.Y /= length
        self.Z /= length
        return True

    def __mul__(self, value):
        return FakeVector(self.X * value, self.Y * value, self.Z * value)

    def __rmul__(self, value):
        return self * value

    def __sub__(self, other):
        return FakeVector(
            self.X - other.X,
            self.Y - other.Y,
            self.Z - other.Z,
        )

    @staticmethod
    def Multiply(vector_a, vector_b):
        return (
            vector_a.X * vector_b.X
            + vector_a.Y * vector_b.Y
            + vector_a.Z * vector_b.Z
        )

    @staticmethod
    def CrossProduct(vector_a, vector_b):
        return FakeVector(
            vector_a.Y * vector_b.Z - vector_a.Z * vector_b.Y,
            vector_a.Z * vector_b.X - vector_a.X * vector_b.Z,
            vector_a.X * vector_b.Y - vector_a.Y * vector_b.X,
        )


class FakePoint(object):
    def __init__(self, x, y=0.0, z=0.0):
        self.X = float(x)
        self.Y = float(y)
        self.Z = float(z)

    def __add__(self, vector):
        return FakePoint(
            self.X + vector.X,
            self.Y + vector.Y,
            self.Z + vector.Z,
        )

    def __sub__(self, other):
        if isinstance(other, FakePoint):
            return FakeVector(
                self.X - other.X,
                self.Y - other.Y,
                self.Z - other.Z,
            )
        return FakePoint(
            self.X - other.X,
            self.Y - other.Y,
            self.Z - other.Z,
        )

    def DistanceTo(self, other):
        return (self - other).Length


class FakeInterval(object):
    def __init__(self, t0, t1):
        self.T0 = float(t0)
        self.T1 = float(t1)


class FakeLineCurve(object):
    def __init__(self, start, end, source=None):
        self.start = start
        self.end = end
        self.Domain = FakeInterval(0.0, 1.0)
        self.source = source if source is not None else self
        self.duplicate_calls = 0
        self.trim_calls = []

    @property
    def PointAtStart(self):
        return self.start

    @property
    def PointAtEnd(self):
        return self.end

    def PointAt(self, parameter):
        ratio = float(parameter)
        return FakePoint(
            self.start.X + (self.end.X - self.start.X) * ratio,
            self.start.Y + (self.end.Y - self.start.Y) * ratio,
            self.start.Z + (self.end.Z - self.start.Z) * ratio,
        )

    def DuplicateCurve(self):
        self.duplicate_calls += 1
        return FakeLineCurve(self.start, self.end, source=self.source)

    def Trim(self, interval):
        self.trim_calls.append((interval.T0, interval.T1))
        return FakeLineCurve(
            self.PointAt(interval.T0),
            self.PointAt(interval.T1),
            source=self.source,
        )

    def GetLength(self):
        return self.start.DistanceTo(self.end)


class FakeCircleCurve(object):
    def __init__(
        self,
        plane,
        radius,
        domain=None,
        source=None,
        is_closed=None,
    ):
        self.plane = plane
        self.radius = float(radius)
        self.Domain = domain or FakeInterval(0.0, math.pi * 2.0)
        self.source = source if source is not None else self
        if is_closed is None:
            is_closed = abs(
                (self.Domain.T1 - self.Domain.T0) - math.pi * 2.0
            ) <= 1e-10
        self.IsClosed = bool(is_closed)
        self.duplicate_calls = 0
        self.trim_calls = []

    @property
    def PointAtStart(self):
        return self.PointAt(self.Domain.T0)

    @property
    def PointAtEnd(self):
        return self.PointAt(self.Domain.T1)

    def PointAt(self, parameter):
        return (
            self.plane.Origin
            + self.plane.XAxis * (math.cos(parameter) * self.radius)
            + self.plane.YAxis * (math.sin(parameter) * self.radius)
        )

    def DuplicateCurve(self):
        self.duplicate_calls += 1
        return FakeCircleCurve(
            self.plane,
            self.radius,
            FakeInterval(self.Domain.T0, self.Domain.T1),
            source=self.source,
            is_closed=self.IsClosed,
        )

    def Trim(self, interval):
        self.trim_calls.append((interval.T0, interval.T1))
        return FakeCircleCurve(
            self.plane,
            self.radius,
            FakeInterval(interval.T0, interval.T1),
            source=self.source,
            is_closed=False,
        )

    def GetLength(self):
        return self.radius * abs(self.Domain.T1 - self.Domain.T0)


class FakeCircle(object):
    def __init__(self, plane, radius):
        self.Plane = plane
        self.Radius = float(radius)
        self.IsValid = self.Radius > 0.0

    def ToNurbsCurve(self):
        return FakeCircleCurve(self.Plane, self.Radius)


class FakeEvent(object):
    def __init__(self, parameter=None, overlap=None):
        self.IsPoint = parameter is not None
        self.IsOverlap = overlap is not None
        self.ParameterA = parameter
        self.OverlapA = (
            FakeInterval(*overlap) if overlap is not None else None
        )


class FakeBoundary(object):
    def __init__(
        self,
        inside_ranges=(),
        coincident_ranges=(),
        events=(),
        contains_function=None,
    ):
        self.inside_ranges = list(inside_ranges)
        self.coincident_ranges = list(coincident_ranges)
        self.events = events if callable(events) else list(events)
        self.contains_function = contains_function
        self.contains_points = []

    def Contains(self, point, _plane, _tolerance):
        self.contains_points.append(point)
        if self.contains_function is not None:
            return self.contains_function(point)
        for start, end in self.coincident_ranges:
            if start <= point.X <= end:
                return "coincident"
        for start, end in self.inside_ranges:
            if start <= point.X <= end:
                return "inside"
        return "outside"


class FakePlane(object):
    def __init__(self, origin=None, x_axis=None, y_axis=None):
        self.Origin = origin or FakePoint(0.0, 0.0, 0.0)
        self.XAxis = x_axis or FakeVector(1.0, 0.0, 0.0)
        self.YAxis = y_axis or FakeVector(0.0, 1.0, 0.0)
        self.Normal = FakeVector.CrossProduct(self.XAxis, self.YAxis)
        self.Normal.Unitize()
        self.IsValid = True

    def ClosestPoint(self, point):
        return FakePoint(point.X, point.Y, 0.0)


class FakeBoundingBox(object):
    def __init__(self, center, diagonal_length):
        self.IsValid = True
        self.Center = center
        self.Diagonal = FakeVector(diagonal_length, 0.0, 0.0)


class FakeIntersectionApi(object):
    fail = False

    @classmethod
    def CurveCurve(
        cls,
        _candidate,
        boundary,
        _intersection_tolerance,
        _overlap_tolerance,
    ):
        if cls.fail:
            raise Exception("fake intersection failure")
        if callable(boundary.events):
            return boundary.events(_candidate)
        return boundary.events


def _fake_rg():
    FakeVector.ZAxis = FakeVector(0.0, 0.0, 1.0)
    return SimpleNamespace(
        Circle=FakeCircle,
        Interval=FakeInterval,
        LineCurve=FakeLineCurve,
        Plane=FakePlane,
        Vector3d=FakeVector,
        PointContainment=SimpleNamespace(
            Inside="inside",
            Coincident="coincident",
        ),
        Intersect=SimpleNamespace(
            Intersection=FakeIntersectionApi,
        ),
    )


def _load_module_functions(trackers=None):
    trackers = trackers if trackers is not None else {}

    def get_stage_directions(audience_direction):
        trackers["directions"] = trackers.get("directions", 0) + 1
        self_copy = FakeVector(audience_direction)
        return FakeVector(1.0, 0.0, 0.0), self_copy

    def point_at(
        stage_point,
        audience_direction,
        x_mm,
        z_mm,
        mm_scale,
    ):
        trackers["point_at"] = (
            float(x_mm),
            float(z_mm),
            float(mm_scale),
        )
        return (
            stage_point
            + audience_direction * (x_mm * mm_scale)
            + FakeVector(0.0, 0.0, z_mm * mm_scale)
        )

    tree = ast.parse(MODULE_PATH.read_text(encoding="utf-8"), str(MODULE_PATH))
    body = [
        node
        for node in tree.body
        if not isinstance(node, (ast.Import, ast.ImportFrom))
    ]
    module = ast.Module(body=body, type_ignores=[])
    ast.fix_missing_locations(module)
    namespace = {
        "math": math,
        "rg": _fake_rg(),
        "get_stage_directions": get_stage_directions,
        "point_at": point_at,
    }
    exec(compile(module, str(MODULE_PATH), "exec"), namespace)
    return namespace


def _context(boundary, tolerance=1e-6, bbox=None):
    return {
        "curve": boundary,
        "plane": FakePlane(),
        "bbox": bbox or FakeBoundingBox(FakePoint(0.0), 20.0),
        "tolerance": tolerance,
    }


def _point_event_for_x(x_value, candidate_start=-5.0, candidate_end=5.0):
    parameter = (x_value - candidate_start) / (
        candidate_end - candidate_start
    )
    return FakeEvent(parameter=parameter)


class BoundaryCurveSegmentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.loaded = _load_module_functions()
        cls.clip = staticmethod(
            cls.loaded["curve_segments_inside_boundary"]
        )

    def setUp(self):
        FakeIntersectionApi.fail = False

    def test_convex_boundary_returns_one_trimmed_segment(self):
        boundary = FakeBoundary(
            inside_ranges=[(-2.0, 2.0)],
            events=[
                _point_event_for_x(-2.0),
                _point_event_for_x(2.0),
            ],
        )
        candidate = FakeLineCurve(FakePoint(-5.0), FakePoint(5.0))

        segments = self.clip(_context(boundary), candidate)

        self.assertEqual(len(segments), 1)
        self.assertAlmostEqual(segments[0].PointAtStart.X, -2.0)
        self.assertAlmostEqual(segments[0].PointAtEnd.X, 2.0)
        self.assertEqual(candidate.trim_calls, [(0.3, 0.7)])
        self.assertAlmostEqual(candidate.start.X, -5.0)
        self.assertAlmostEqual(candidate.end.X, 5.0)

    def test_concave_boundary_returns_multiple_ordered_segments(self):
        boundary = FakeBoundary(
            inside_ranges=[(-4.0, -2.0), (1.0, 3.0)],
            events=[
                _point_event_for_x(3.0),
                _point_event_for_x(-2.0),
                _point_event_for_x(-4.0),
                _point_event_for_x(1.0),
            ],
        )
        candidate = FakeLineCurve(FakePoint(-5.0), FakePoint(5.0))

        segments = self.clip(_context(boundary), candidate)

        self.assertEqual(
            [
                (round(item.PointAtStart.X, 7), round(item.PointAtEnd.X, 7))
                for item in segments
            ],
            [(-4.0, -2.0), (1.0, 3.0)],
        )

    def test_tangent_duplicate_parameters_do_not_create_slivers(self):
        boundary = FakeBoundary(
            inside_ranges=[(-2.0, 2.0)],
            events=[
                FakeEvent(parameter=0.3),
                FakeEvent(parameter=0.30000000000001),
                FakeEvent(parameter=0.5),
                FakeEvent(parameter=0.5),
                FakeEvent(parameter=0.7),
            ],
        )
        candidate = FakeLineCurve(FakePoint(-5.0), FakePoint(5.0))

        segments = self.clip(_context(boundary), candidate)

        self.assertEqual(len(segments), 2)
        self.assertAlmostEqual(segments[0].PointAtStart.X, -2.0)
        self.assertAlmostEqual(segments[0].PointAtEnd.X, 0.0)
        self.assertAlmostEqual(segments[1].PointAtStart.X, 0.0)
        self.assertAlmostEqual(segments[1].PointAtEnd.X, 2.0)
        self.assertEqual(len(candidate.trim_calls), 2)

    def test_overlap_endpoints_are_used_and_coincident_segment_is_kept(self):
        boundary = FakeBoundary(
            coincident_ranges=[(-2.0, 2.0)],
            events=[FakeEvent(overlap=(0.3, 0.7))],
        )
        candidate = FakeLineCurve(FakePoint(-5.0), FakePoint(5.0))

        segments = self.clip(_context(boundary), candidate)

        self.assertEqual(len(segments), 1)
        self.assertAlmostEqual(segments[0].PointAtStart.X, -2.0)
        self.assertAlmostEqual(segments[0].PointAtEnd.X, 2.0)

    def test_no_intersections_duplicates_whole_curve_when_inside(self):
        boundary = FakeBoundary(
            inside_ranges=[(-10.0, 10.0)],
            events=[],
        )
        candidate = FakeLineCurve(FakePoint(-5.0), FakePoint(5.0))

        segments = self.clip(_context(boundary), candidate)

        self.assertEqual(len(segments), 1)
        self.assertIsNot(segments[0], candidate)
        self.assertEqual(candidate.duplicate_calls, 1)
        self.assertEqual(candidate.trim_calls, [])

    def test_no_intersections_returns_empty_when_outside(self):
        boundary = FakeBoundary(inside_ranges=[], events=[])
        candidate = FakeLineCurve(FakePoint(-5.0), FakePoint(5.0))

        self.assertEqual(self.clip(_context(boundary), candidate), [])
        self.assertEqual(candidate.duplicate_calls, 0)
        self.assertEqual(candidate.trim_calls, [])

    def test_intersection_failure_has_clear_error(self):
        FakeIntersectionApi.fail = True
        boundary = FakeBoundary()
        candidate = FakeLineCurve(FakePoint(-5.0), FakePoint(5.0))

        with self.assertRaisesRegex(
            RuntimeError,
            "Boundary and row curve intersection failed",
        ):
            self.clip(_context(boundary), candidate)


class RectangularRowAndIntervalTests(unittest.TestCase):
    def setUp(self):
        FakeIntersectionApi.fail = False
        self.trackers = {}
        self.loaded = _load_module_functions(self.trackers)

    def test_rectangular_row_uses_stage_coordinates_and_boundary_plane(self):
        boundary = FakeBoundary(
            inside_ranges=[(-10.0, 10.0)],
            events=[
                FakeEvent(parameter=0.25),
                FakeEvent(parameter=0.75),
            ],
        )
        context = _context(
            boundary,
            tolerance=0.01,
            bbox=FakeBoundingBox(FakePoint(0.0, 6.0, 0.0), 20.0),
        )

        segments = self.loaded["rectangular_row_segments"](
            context,
            FakePoint(0.0, 0.0, 5.0),
            FakeVector(0.0, 1.0, 0.0),
            3.0,
            2.0,
        )

        self.assertEqual(self.trackers["directions"], 1)
        self.assertEqual(self.trackers["point_at"], (3.0, 0.0, 2.0))
        self.assertEqual(len(segments), 1)
        self.assertAlmostEqual(segments[0].PointAtStart.X, -10.05)
        self.assertAlmostEqual(segments[0].PointAtEnd.X, 10.05)
        self.assertAlmostEqual(segments[0].PointAtStart.Y, 6.0)
        self.assertAlmostEqual(segments[0].PointAtEnd.Y, 6.0)
        self.assertAlmostEqual(segments[0].PointAtStart.Z, 0.0)
        self.assertAlmostEqual(segments[0].PointAtEnd.Z, 0.0)

    def test_lateral_intervals_are_normalized_sorted_and_scaled(self):
        segments = [
            FakeLineCurve(FakePoint(3.0), FakePoint(1.0)),
            FakeLineCurve(FakePoint(-4.0), FakePoint(-2.0)),
            FakeLineCurve(FakePoint(0.0), FakePoint(1e-10)),
        ]
        lateral = FakeVector(2.0, 0.0, 0.0)

        intervals = self.loaded["segment_lateral_intervals"](
            segments,
            FakePoint(0.0),
            lateral,
            0.5,
        )

        self.assertEqual(intervals, [(-8.0, -4.0), (2.0, 6.0)])
        self.assertEqual((lateral.X, lateral.Y, lateral.Z), (2.0, 0.0, 0.0))

    def test_missing_context_value_has_clear_error(self):
        with self.assertRaisesRegex(
            ValueError,
            "missing required value: curve",
        ):
            self.loaded["curve_segments_inside_boundary"](
                {"plane": FakePlane(), "tolerance": 0.01},
                FakeLineCurve(FakePoint(-1.0), FakePoint(1.0)),
            )


def _radial_layout(radius=10.0, center=None):
    return {
        "mode": "radial",
        "radius": float(radius),
        "center_point": center or FakePoint(0.0, 0.0, 7.0),
        "reference_mid_point": FakePoint(0.0, radius, 7.0),
        "audience_direction": FakeVector(0.0, 1.0, 0.0),
        "audience_view_right_direction": FakeVector(-1.0, 0.0, 0.0),
    }


def _rear_seam_circle(radius):
    plane = FakePlane(
        FakePoint(0.0, 0.0, 0.0),
        FakeVector(0.0, -1.0, 0.0),
        FakeVector(1.0, 0.0, 0.0),
    )
    return FakeCircleCurve(plane, radius)


class RadialRowSegmentTests(unittest.TestCase):
    def setUp(self):
        FakeIntersectionApi.fail = False
        self.loaded = _load_module_functions()

    def test_full_circle_is_clipped_with_seam_opposite_audience(self):
        boundary = FakeBoundary(
            contains_function=lambda point: (
                "inside" if point.Y >= -1e-8 else "outside"
            ),
            events=[
                FakeEvent(parameter=math.pi * 0.5),
                FakeEvent(parameter=math.pi * 1.5),
            ],
        )

        segments = self.loaded["radial_row_segments"](
            _context(boundary, tolerance=0.01),
            _radial_layout(radius=10.0),
            5.0,
            2.0,
        )

        self.assertEqual(len(segments), 1)
        segment = segments[0]
        source = segment.source
        self.assertAlmostEqual(source.radius, 30.0)
        self.assertAlmostEqual(source.plane.Origin.Z, 0.0)
        self.assertAlmostEqual(source.plane.XAxis.X, 0.0)
        self.assertAlmostEqual(source.plane.XAxis.Y, -1.0)
        self.assertAlmostEqual(source.PointAtStart.X, 0.0)
        self.assertAlmostEqual(source.PointAtStart.Y, -30.0)
        self.assertAlmostEqual(segment.PointAtStart.X, 30.0)
        self.assertAlmostEqual(segment.PointAtStart.Y, 0.0)
        self.assertAlmostEqual(segment.PointAtEnd.X, -30.0)
        self.assertAlmostEqual(segment.PointAtEnd.Y, 0.0)
        self.assertAlmostEqual(segment.PointAtStart.Z, 0.0)
        self.assertAlmostEqual(segment.PointAtEnd.Z, 0.0)

    def test_whole_circle_inside_survives_coincident_domain_endpoints(self):
        boundary = FakeBoundary(
            contains_function=lambda _point: "inside",
            events=[],
        )

        segments = self.loaded["radial_row_segments"](
            _context(boundary),
            _radial_layout(radius=10.0),
            0.0,
            1.0,
        )

        self.assertEqual(len(segments), 1)
        self.assertTrue(segments[0].IsClosed)
        self.assertAlmostEqual(segments[0].GetLength(), math.pi * 20.0)

    def test_radial_intervals_use_signed_angle_times_row_radius(self):
        circle = _rear_seam_circle(10.0)
        forward_segment = circle.Trim(
            FakeInterval(math.pi * 2.0 / 3.0, math.pi * 7.0 / 6.0)
        )
        rear_seam_segment = circle.Trim(
            FakeInterval(0.0, math.pi / 18.0)
        )

        intervals = self.loaded["radial_segment_lateral_intervals"](
            [forward_segment, rear_seam_segment],
            _radial_layout(radius=10.0, center=FakePoint(0.0, 0.0, 0.0)),
            0.0,
            1.0,
        )

        self.assertEqual(len(intervals), 2)
        self.assertAlmostEqual(intervals[0][0], -math.pi * 10.0)
        self.assertAlmostEqual(intervals[0][1], -math.pi * 85.0 / 9.0)
        self.assertAlmostEqual(intervals[1][0], -math.pi * 10.0 / 3.0)
        self.assertAlmostEqual(intervals[1][1], math.pi * 5.0 / 3.0)

    def test_closed_radial_segment_maps_to_full_signed_interval(self):
        intervals = self.loaded["radial_segment_lateral_intervals"](
            [_rear_seam_circle(12.0)],
            _radial_layout(radius=12.0, center=FakePoint(0.0, 0.0, 0.0)),
            0.0,
            1.0,
        )

        self.assertEqual(len(intervals), 1)
        self.assertAlmostEqual(intervals[0][0], -math.pi * 12.0)
        self.assertAlmostEqual(intervals[0][1], math.pi * 12.0)


class TierRowRegionBuilderTests(unittest.TestCase):
    def setUp(self):
        FakeIntersectionApi.fail = False
        self.loaded = _load_module_functions()
        self.boundary = FakeBoundary()
        self.context = _context(self.boundary)

    def test_rectangular_builder_returns_one_stable_record_per_row(self):
        calls = []

        def fake_segments(context, stage, direction, row_x, scale):
            calls.append(("segments", context, stage, direction, row_x, scale))
            return ["rect-{0}".format(row_x)]

        def fake_intervals(segments, center, lateral, scale):
            calls.append(
                ("intervals", tuple(segments), center, lateral, scale)
            )
            return [(-float(center.Y), float(center.Y))]

        self.loaded["rectangular_row_segments"] = fake_segments
        self.loaded["segment_lateral_intervals"] = fake_intervals
        layout = {
            "mode": "rectangular",
            "reference_mid_point": FakePoint(1.0, 2.0, 5.0),
            "audience_direction": FakeVector(0.0, 1.0, 0.0),
        }
        tier = {
            "x_values": [3.0, 5.0],
            "base_z_values": [100.0, 140.0],
        }

        regions = self.loaded["build_tier_row_regions"](
            self.context,
            layout,
            tier,
            2.0,
        )

        self.assertEqual(
            [
                {
                    "row_index": 0,
                    "row_x": 3.0,
                    "floor_z": 100.0,
                    "segments": ["rect-3.0"],
                    "intervals": [(-8.0, 8.0)],
                },
                {
                    "row_index": 1,
                    "row_x": 5.0,
                    "floor_z": 140.0,
                    "segments": ["rect-5.0"],
                    "intervals": [(-12.0, 12.0)],
                },
            ],
            regions,
        )
        self.assertEqual(tier["x_values"], [3.0, 5.0])
        self.assertEqual(tier["base_z_values"], [100.0, 140.0])
        self.assertEqual(
            [call[0] for call in calls],
            ["segments", "intervals", "segments", "intervals"],
        )

    def test_radial_builder_dispatches_segments_and_intervals(self):
        calls = []

        def fake_segments(context, layout, row_x, scale):
            calls.append(("segments", context, layout, row_x, scale))
            return ["arc-{0}".format(row_x)]

        def fake_intervals(segments, layout, row_x, scale):
            calls.append(
                ("intervals", tuple(segments), layout, row_x, scale)
            )
            return [(row_x * -10.0, row_x * 10.0)]

        self.loaded["radial_row_segments"] = fake_segments
        self.loaded["radial_segment_lateral_intervals"] = fake_intervals
        layout = _radial_layout()

        regions = self.loaded["build_tier_row_regions"](
            self.context,
            layout,
            {"x_values": [4.0], "base_z_values": [250.0]},
            0.5,
        )

        self.assertEqual(
            regions,
            [
                {
                    "row_index": 0,
                    "row_x": 4.0,
                    "floor_z": 250.0,
                    "segments": ["arc-4.0"],
                    "intervals": [(-40.0, 40.0)],
                }
            ],
        )
        self.assertEqual(
            [call[0] for call in calls],
            ["segments", "intervals"],
        )

    def test_builder_requires_boundary_and_matching_tier_arrays(self):
        layout = _radial_layout()
        with self.assertRaisesRegex(ValueError, "Boundary context"):
            self.loaded["build_tier_row_regions"](
                None,
                layout,
                {"x_values": [], "base_z_values": []},
                1.0,
            )
        with self.assertRaisesRegex(ValueError, "equal lengths"):
            self.loaded["build_tier_row_regions"](
                self.context,
                layout,
                {"x_values": [1.0], "base_z_values": []},
                1.0,
            )

    def test_rectangular_footprint_intersects_all_depth_samples(self):
        segment_calls = []
        intervals_by_x = {
            10.0: [(-10.0, 10.0)],
            8.0: [(-8.0, 9.0)],
            6.0: [(-7.0, 7.0)],
        }

        def fake_segments(_context, _stage, _direction, row_x, _scale):
            segment_calls.append(row_x)
            return [("rect-guide", row_x)]

        def fake_intervals(segments, _center, _lateral, _scale):
            return list(intervals_by_x[segments[0][1]])

        self.loaded["rectangular_row_segments"] = fake_segments
        self.loaded["segment_lateral_intervals"] = fake_intervals
        layout = {
            "mode": "rectangular",
            "reference_mid_point": FakePoint(0.0, 0.0, 5.0),
            "audience_direction": FakeVector(0.0, 1.0, 0.0),
        }

        regions = self.loaded["build_tier_row_regions"](
            self.context,
            layout,
            {"x_values": [10.0], "base_z_values": [120.0]},
            1.0,
            footprint_depth_mm=4.0,
            footprint_sample_count=3,
        )

        self.assertEqual(segment_calls, [10.0, 8.0, 6.0])
        self.assertEqual(regions[0]["segments"], [("rect-guide", 10.0)])
        self.assertEqual(regions[0]["intervals"], [(-7.0, 7.0)])

    def test_radial_footprint_rebases_angles_to_anchor_radius(self):
        segment_calls = []
        angular_intervals = {
            5.0: (-0.8, 0.8),
            3.0: (-0.5, 0.7),
            1.0: (-0.6, 0.4),
        }

        def fake_segments(_context, _layout, row_x, _scale):
            segment_calls.append(row_x)
            return [("radial-guide", row_x)]

        def fake_intervals(segments, layout, row_x, _scale):
            self.assertEqual(segments, [("radial-guide", row_x)])
            row_radius = layout["radius"] + row_x
            angle_start, angle_end = angular_intervals[row_x]
            return [
                (
                    angle_start * row_radius,
                    angle_end * row_radius,
                )
            ]

        self.loaded["radial_row_segments"] = fake_segments
        self.loaded["radial_segment_lateral_intervals"] = fake_intervals

        regions = self.loaded["build_tier_row_regions"](
            self.context,
            _radial_layout(radius=10.0),
            {"x_values": [5.0], "base_z_values": [220.0]},
            1.0,
            footprint_depth_mm=4.0,
            footprint_sample_count=3,
        )

        self.assertEqual(segment_calls, [5.0, 3.0, 1.0])
        self.assertEqual(regions[0]["segments"], [("radial-guide", 5.0)])
        self.assertEqual(len(regions[0]["intervals"]), 1)
        self.assertAlmostEqual(regions[0]["intervals"][0][0], -7.5)
        self.assertAlmostEqual(regions[0]["intervals"][0][1], 6.0)

    def test_footprint_minimum_samples_include_both_depth_ends(self):
        sample_rows = []

        def fake_segments(_context, _stage, _direction, row_x, _scale):
            sample_rows.append(row_x)
            return [("guide", row_x)]

        self.loaded["rectangular_row_segments"] = fake_segments
        self.loaded["segment_lateral_intervals"] = (
            lambda *_args: [(-1.0, 1.0)]
        )
        layout = {
            "mode": "rectangular",
            "reference_mid_point": FakePoint(0.0),
            "audience_direction": FakeVector(0.0, 1.0, 0.0),
        }

        self.loaded["build_tier_row_regions"](
            self.context,
            layout,
            {"x_values": [10.0], "base_z_values": [0.0]},
            1.0,
            footprint_depth_mm=4.0,
            footprint_sample_count=1,
        )

        self.assertEqual(sample_rows, [10.0, 6.0])

    def test_empty_footprint_intersection_keeps_anchor_guide(self):
        self.loaded["rectangular_row_segments"] = (
            lambda _context, _stage, _direction, row_x, _scale: [row_x]
        )
        self.loaded["segment_lateral_intervals"] = (
            lambda segments, *_args: (
                [(-2.0, 2.0)] if segments[0] == 10.0 else [(5.0, 8.0)]
            )
        )
        layout = {
            "mode": "rectangular",
            "reference_mid_point": FakePoint(0.0),
            "audience_direction": FakeVector(0.0, 1.0, 0.0),
        }

        regions = self.loaded["build_tier_row_regions"](
            self.context,
            layout,
            {"x_values": [10.0], "base_z_values": [0.0]},
            1.0,
            footprint_depth_mm=2.0,
            footprint_sample_count=2,
        )

        self.assertEqual(regions[0]["segments"], [10.0])
        self.assertEqual(regions[0]["intervals"], [])


class IntervalSetIntersectionTests(unittest.TestCase):
    def setUp(self):
        self.loaded = _load_module_functions()
        self.intersect = self.loaded["intersect_interval_sets"]

    def test_multiple_interval_sets_intersect_as_unions(self):
        sources = [
            [(-10.0, -2.0), (0.0, 10.0)],
            [(-8.0, 3.0), (5.0, 12.0)],
            [(-9.0, -4.0), (1.0, 8.0)],
        ]
        before = copy.deepcopy(sources)

        result = self.intersect(sources)

        self.assertEqual(result, [(-8.0, -4.0), (1.0, 3.0), (5.0, 8.0)])
        self.assertEqual(sources, before)

    def test_intersection_normalizes_reversed_overlaps_and_slivers(self):
        result = self.intersect(
            [
                [
                    (10.0, 0.0),
                    (20.0, 25.0),
                    (25.0, 30.0),
                    (5.0, 5.0 + 1e-10),
                ],
                [(-1.0, 3.0), (2.0, 8.0), (22.0, 28.0)],
            ]
        )

        self.assertEqual(result, [(0.0, 8.0), (22.0, 28.0)])

    def test_empty_source_or_disjoint_sets_return_empty(self):
        self.assertEqual(self.intersect([]), [])
        self.assertEqual(self.intersect([[(-1.0, 1.0)], []]), [])
        self.assertEqual(
            self.intersect([[(-1.0, 1.0)], [(2.0, 3.0)]]),
            [],
        )


if __name__ == "__main__":
    unittest.main()
