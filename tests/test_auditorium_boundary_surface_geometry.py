# -*- coding: utf-8 -*-
"""Rhino-free tests for auditorium boundary surface and split helpers."""

import ast
import math
import unittest
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]
SURFACE_PATH = (
    ROOT
    / "commands"
    / "auditorium_generator"
    / "boundary_surface_geometry.py"
)


class FakePoint(object):
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
            raise TypeError("Point requires one point or three coordinates")

    @property
    def IsValid(self):
        return all(
            value == value
            and value != float("inf")
            and value != float("-inf")
            for value in (self.X, self.Y, self.Z)
        )


class FakeVector(object):
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
            raise TypeError("Vector requires one vector or three coordinates")

    def Unitize(self):
        length = math.sqrt(
            self.X * self.X + self.Y * self.Y + self.Z * self.Z
        )
        if length <= 1e-12:
            return False
        self.X /= length
        self.Y /= length
        self.Z /= length
        return True

    def IsParallelTo(self, other, angle_tolerance):
        if angle_tolerance <= 0.0:
            return 0
        cross_x = self.Y * other.Z - self.Z * other.Y
        cross_y = self.Z * other.X - self.X * other.Z
        cross_z = self.X * other.Y - self.Y * other.X
        if math.sqrt(
            cross_x * cross_x + cross_y * cross_y + cross_z * cross_z
        ) > 1e-8:
            return 0
        dot = self.X * other.X + self.Y * other.Y + self.Z * other.Z
        return 1 if dot >= 0.0 else -1


class FakeVector3dApi(FakeVector):
    @staticmethod
    def CrossProduct(a, b):
        return FakeVector(
            a.Y * b.Z - a.Z * b.Y,
            a.Z * b.X - a.X * b.Z,
            a.X * b.Y - a.Y * b.X,
        )


FakeVector3dApi.XAxis = FakeVector(1.0, 0.0, 0.0)
FakeVector3dApi.YAxis = FakeVector(0.0, 1.0, 0.0)
FakeVector3dApi.ZAxis = FakeVector(0.0, 0.0, 1.0)


class FakePlane(object):
    def __init__(self, origin, x_axis, y_axis):
        self.Origin = FakePoint(origin)
        self.XAxis = FakeVector(x_axis)
        self.YAxis = FakeVector(y_axis)
        self.Normal = FakeVector3dApi.CrossProduct(
            self.XAxis,
            self.YAxis,
        )
        self.Normal.Unitize()
        self.IsValid = self.Origin.IsValid


class FakeBoundingBox(object):
    def __init__(self, minimum, maximum, valid=True):
        self.Min = FakePoint(minimum)
        self.Max = FakePoint(maximum)
        self.Center = FakePoint(
            (self.Min.X + self.Max.X) * 0.5,
            (self.Min.Y + self.Max.Y) * 0.5,
            (self.Min.Z + self.Max.Z) * 0.5,
        )
        self.IsValid = bool(valid)


class FakeCurve(object):
    def __init__(
        self,
        z_value=0.0,
        bbox_factory=None,
        is_valid=True,
        is_closed=True,
        transform_succeeds=True,
        planar_result="valid",
        extrusion_fails=False,
        plane_is_planar=True,
        plane_parallel=True,
    ):
        self.z_value = float(z_value)
        self.bbox_factory = bbox_factory
        self.IsValid = bool(is_valid)
        self.IsClosed = bool(is_closed)
        self.transform_succeeds = bool(transform_succeeds)
        self.planar_result = planar_result
        self.extrusion_fails = bool(extrusion_fails)
        self.plane_is_planar = bool(plane_is_planar)
        self.plane_parallel = bool(plane_parallel)
        self.duplicate_calls = 0
        self.last_duplicate = None
        self.transform_calls = []
        self.bbox_calls = []
        self.mutations = []

    def clone(self):
        return FakeCurve(
            z_value=self.z_value,
            bbox_factory=self.bbox_factory,
            is_valid=self.IsValid,
            is_closed=self.IsClosed,
            transform_succeeds=self.transform_succeeds,
            planar_result=self.planar_result,
            extrusion_fails=self.extrusion_fails,
            plane_is_planar=self.plane_is_planar,
            plane_parallel=self.plane_parallel,
        )

    def DuplicateCurve(self):
        self.duplicate_calls += 1
        self.last_duplicate = self.clone()
        return self.last_duplicate

    def Transform(self, transform):
        self.transform_calls.append(transform)
        if not self.transform_succeeds:
            return False
        self.z_value += transform.vector.Z
        return True

    def GetBoundingBox(self, plane):
        self.bbox_calls.append(plane)
        if self.bbox_factory is None:
            return FakeBoundingBox(
                FakePoint(-10.0, -10.0, 0.0),
                FakePoint(10.0, 10.0, 0.0),
            )
        return self.bbox_factory(plane)

    def TryGetPlane(self, *args):
        x_axis = FakeVector(1.0, 0.0, 0.0)
        y_axis = (
            FakeVector(0.0, 1.0, 0.0)
            if self.plane_parallel
            else FakeVector(0.0, 0.0, 1.0)
        )
        return self.plane_is_planar, FakePlane(
            FakePoint(0.0, 0.0, self.z_value),
            x_axis,
            y_axis,
        )


class FakeMassProperties(object):
    def __init__(self, centroid):
        self.Centroid = FakePoint(centroid)
        self.disposed = False

    def Dispose(self):
        self.disposed = True


class FakeBrep(object):
    def __init__(
        self,
        name,
        valid=True,
        solid=False,
        area_centroid=None,
        volume_centroid=None,
        bbox=None,
        split_result=None,
        split_raises=False,
        trim_result=None,
        trim_raises=True,
        duplicate_fails=False,
    ):
        self.name = name
        self.IsValid = bool(valid)
        self.IsSolid = bool(solid)
        self.area_centroid = area_centroid
        self.volume_centroid = volume_centroid
        self.bbox = bbox or FakeBoundingBox(
            FakePoint(-1.0, -1.0, -1.0),
            FakePoint(1.0, 1.0, 1.0),
        )
        self.split_result = split_result
        self.split_raises = bool(split_raises)
        self.trim_result = trim_result
        self.trim_raises = bool(trim_raises)
        self.duplicate_fails = bool(duplicate_fails)
        self.duplicate_calls = 0
        self.last_duplicate = None
        self.split_calls = []
        self.trim_calls = []
        self.mutations = []
        self.disposed = False

    def clone(self):
        return FakeBrep(
            self.name + "-copy",
            valid=self.IsValid,
            solid=self.IsSolid,
            area_centroid=self.area_centroid,
            volume_centroid=self.volume_centroid,
            bbox=self.bbox,
            split_result=self.split_result,
            split_raises=self.split_raises,
            trim_result=self.trim_result,
            trim_raises=self.trim_raises,
            duplicate_fails=self.duplicate_fails,
        )

    def DuplicateBrep(self):
        self.duplicate_calls += 1
        if self.duplicate_fails:
            return None
        self.last_duplicate = self.clone()
        return self.last_duplicate

    def Split(self, cutter, tolerance):
        self.split_calls.append((cutter, tolerance))
        if self.split_raises:
            raise RuntimeError("split failed")
        return self.split_result

    def Trim(self, cutter, tolerance):
        self.trim_calls.append((cutter, tolerance))
        if self.trim_raises:
            raise RuntimeError("trim failed")
        return self.trim_result

    def GetBoundingBox(self, accurate):
        if accurate is not True:
            raise AssertionError("accurate bbox expected")
        return self.bbox

    def Dispose(self):
        self.disposed = True


class FakeTransformApi(object):
    calls = []

    @classmethod
    def Translation(cls, vector):
        transform = SimpleNamespace(vector=FakeVector(vector))
        cls.calls.append(transform)
        return transform


class FakeBrepApi(object):
    planar_calls = []

    @classmethod
    def CreatePlanarBreps(cls, curve, tolerance):
        cls.planar_calls.append((curve, tolerance))
        if curve.planar_result == "none":
            return None
        if curve.planar_result == "multiple":
            return [FakeBrep("a"), FakeBrep("b")]
        if curve.planar_result == "invalid":
            return [FakeBrep("invalid", valid=False)]
        return [FakeBrep("ceiling")]


class FakeExtrusion(object):
    def __init__(self, cap):
        self.cap = bool(cap)
        self.disposed = False

    def ToBrep(self):
        return FakeBrep(
            "solid-cutter" if self.cap else "perimeter-wall",
            solid=self.cap,
        )

    def Dispose(self):
        self.disposed = True


class FakeExtrusionApi(object):
    calls = []
    results = []

    @classmethod
    def Create(cls, profile, plane, height, cap):
        cls.calls.append((profile, plane, height, cap))
        if profile.extrusion_fails:
            return None
        extrusion = FakeExtrusion(cap)
        cls.results.append(extrusion)
        return extrusion


class FakeSurface(object):
    def __init__(self):
        self.disposed = False

    def ToBrep(self):
        return FakeBrep("segment-wall", solid=False)

    def Dispose(self):
        self.disposed = True


class FakeSurfaceApi(object):
    calls = []
    results = []

    @classmethod
    def CreateExtrusion(cls, profile, vector):
        cls.calls.append((profile, vector))
        if profile.extrusion_fails:
            return None
        surface = FakeSurface()
        cls.results.append(surface)
        return surface


class FakeVolumeMassPropertiesApi(object):
    calls = []
    results = []

    @classmethod
    def Compute(cls, brep):
        cls.calls.append(brep)
        if brep.volume_centroid is None:
            return None
        result = FakeMassProperties(brep.volume_centroid)
        cls.results.append(result)
        return result


class FakeAreaMassPropertiesApi(object):
    calls = []
    results = []

    @classmethod
    def Compute(cls, brep):
        cls.calls.append(brep)
        if brep.area_centroid is None:
            return None
        result = FakeMassProperties(brep.area_centroid)
        cls.results.append(result)
        return result


FAKE_RG = SimpleNamespace(
    Point3d=FakePoint,
    Vector3d=FakeVector3dApi,
    Plane=FakePlane,
    Transform=FakeTransformApi,
    Brep=FakeBrepApi,
    Extrusion=FakeExtrusionApi,
    Surface=FakeSurfaceApi,
    VolumeMassProperties=FakeVolumeMassPropertiesApi,
    AreaMassProperties=FakeAreaMassPropertiesApi,
)


def load_surface_module(containment=None):
    tree = ast.parse(
        SURFACE_PATH.read_text(encoding="utf-8-sig"),
        filename=str(SURFACE_PATH),
    )
    body = [
        node
        for node in tree.body
        if not isinstance(node, (ast.Import, ast.ImportFrom))
    ]
    selected = ast.fix_missing_locations(
        ast.Module(body=body, type_ignores=[])
    )
    containment_calls = []

    if containment is None:
        containment = lambda point: point.X >= 0.0

    def boundary_contains_point(
        context,
        point,
        include_boundary=True,
    ):
        containment_calls.append((context, point, include_boundary))
        return containment(point)

    namespace = {
        "__builtins__": __builtins__,
        "rg": FAKE_RG,
        "boundary_contains_point": boundary_contains_point,
    }
    exec(compile(selected, str(SURFACE_PATH), "exec"), namespace)
    namespace["containment_calls"] = containment_calls
    return namespace


def make_context(curve=None, z_value=5.0, tolerance=0.01):
    curve = curve or FakeCurve(z_value=z_value)
    plane = FakePlane(
        FakePoint(0.0, 0.0, z_value),
        FakeVector3dApi.XAxis,
        FakeVector3dApi.YAxis,
    )
    return {
        "curve": curve,
        "plane": plane,
        "bbox": curve.GetBoundingBox(plane),
        "area": 100.0,
        "tolerance": tolerance,
    }


class BoundaryPlanMeasurementTests(unittest.TestCase):
    def setUp(self):
        self.loaded = load_surface_module()

    def test_stage_local_extents_and_radial_radius_are_scaled(self):
        def bbox_for_plane(plane):
            if plane.Origin.X == 999.0:
                return FakeBoundingBox(
                    FakePoint(-300.0, -400.0, 0.0),
                    FakePoint(500.0, 200.0, 0.0),
                )
            return FakeBoundingBox(
                FakePoint(-200.0, -600.0, 0.0),
                FakePoint(1800.0, 1000.0, 0.0),
            )

        curve = FakeCurve(bbox_factory=bbox_for_plane)
        context = make_context(curve)
        direction = FakeVector(0.0, 2.0, 7.0)

        result = self.loaded["calculate_boundary_plan_extents"](
            context,
            FakePoint(10.0, 20.0, 5.0),
            direction,
            2.0,
            radial_center_point=FakePoint(999.0, 0.0, 5.0),
        )

        self.assertEqual(result["min_longitudinal_mm"], -100.0)
        self.assertEqual(result["max_longitudinal_mm"], 900.0)
        self.assertEqual(result["min_lateral_mm"], -300.0)
        self.assertEqual(result["max_lateral_mm"], 500.0)
        self.assertEqual(result["longitudinal_span_mm"], 1000.0)
        self.assertEqual(result["lateral_span_mm"], 800.0)
        self.assertAlmostEqual(
            result["max_radius_mm"],
            math.sqrt(500.0 ** 2 + 400.0 ** 2) / 2.0,
        )
        local_plane = curve.bbox_calls[-2]
        self.assertAlmostEqual(local_plane.XAxis.X, 0.0)
        self.assertAlmostEqual(local_plane.XAxis.Y, 1.0)
        self.assertAlmostEqual(local_plane.YAxis.X, -1.0)
        self.assertAlmostEqual(local_plane.YAxis.Y, 0.0)
        self.assertEqual((direction.X, direction.Y, direction.Z), (0.0, 2.0, 7.0))
        self.assertEqual(curve.mutations, [])

    def test_bad_scale_direction_and_bbox_raise_value_errors(self):
        context = make_context()
        calculate = self.loaded["calculate_boundary_plan_extents"]
        with self.assertRaisesRegex(ValueError, "Millimeter scale"):
            calculate(
                context,
                FakePoint(0.0, 0.0, 0.0),
                FakeVector(1.0, 0.0, 0.0),
                0.0,
            )
        with self.assertRaisesRegex(ValueError, "horizontal component"):
            calculate(
                context,
                FakePoint(0.0, 0.0, 0.0),
                FakeVector(0.0, 0.0, 1.0),
                1.0,
            )

        invalid_bbox_curve = FakeCurve(
            bbox_factory=lambda plane: FakeBoundingBox(
                FakePoint(0.0, 0.0, 0.0),
                FakePoint(1.0, 1.0, 0.0),
                valid=False,
            )
        )
        with self.assertRaisesRegex(ValueError, "bounding box"):
            calculate(
                make_context(invalid_bbox_curve),
                FakePoint(0.0, 0.0, 0.0),
                FakeVector(1.0, 0.0, 0.0),
                1.0,
            )


class BoundarySurfaceConstructionTests(unittest.TestCase):
    def setUp(self):
        FakeTransformApi.calls = []
        FakeBrepApi.planar_calls = []
        FakeExtrusionApi.calls = []
        FakeExtrusionApi.results = []
        FakeSurfaceApi.calls = []
        FakeSurfaceApi.results = []
        self.loaded = load_surface_module()

    def test_ceiling_uses_moved_duplicate_and_preserves_source(self):
        source = FakeCurve(z_value=5.0)
        context = make_context(source, z_value=5.0)

        ceiling = self.loaded["build_boundary_ceiling_brep"](
            context,
            105.0,
            absolute_tolerance=0.02,
        )

        self.assertEqual(ceiling.name, "ceiling")
        self.assertEqual(source.z_value, 5.0)
        self.assertEqual(source.mutations, [])
        self.assertEqual(source.duplicate_calls, 1)
        moved_curve, tolerance = FakeBrepApi.planar_calls[0]
        self.assertIs(moved_curve, source.last_duplicate)
        self.assertEqual(moved_curve.z_value, 105.0)
        self.assertEqual(tolerance, 0.02)

    def test_ceiling_failure_is_reported(self):
        for result in ("none", "multiple", "invalid"):
            with self.subTest(result=result):
                source = FakeCurve(planar_result=result)
                with self.assertRaisesRegex(ValueError, "ceiling"):
                    self.loaded["build_boundary_ceiling_brep"](
                        make_context(source),
                        100.0,
                    )

    def test_cutter_and_perimeter_wall_use_explicit_upward_extrusions(self):
        source = FakeCurve(z_value=5.0)
        context = make_context(source, z_value=5.0)

        cutter = self.loaded["build_boundary_vertical_cutter"](
            context,
            -10.0,
            90.0,
        )
        wall = self.loaded["build_boundary_perimeter_wall_brep"](
            context,
            -20.0,
            180.0,
        )

        self.assertTrue(cutter.IsSolid)
        self.assertFalse(wall.IsSolid)
        cutter_profile, cutter_plane, cutter_height, cutter_cap = (
            FakeExtrusionApi.calls[0]
        )
        self.assertEqual(cutter_profile.z_value, -10.0)
        self.assertEqual(cutter_plane.Origin.Z, -10.0)
        self.assertEqual(cutter_height, 100.0)
        self.assertTrue(cutter_cap)
        self.assertEqual(FakeExtrusionApi.calls[1][2:], (200.0, False))
        self.assertTrue(all(item.disposed for item in FakeExtrusionApi.results))
        self.assertEqual(source.z_value, 5.0)
        self.assertEqual(source.mutations, [])

    def test_vertical_extrusion_rejects_short_span_and_creation_failure(self):
        context = make_context()
        with self.assertRaisesRegex(ValueError, "must exceed"):
            self.loaded["build_boundary_vertical_cutter"](
                context,
                10.0,
                10.005,
            )

        failing_curve = FakeCurve(extrusion_fails=True)
        with self.assertRaisesRegex(ValueError, "could not be created"):
            self.loaded["build_boundary_vertical_cutter"](
                make_context(failing_curve),
                0.0,
                10.0,
            )

    def test_open_curve_can_be_extruded_as_only_one_wall_segment(self):
        source = FakeCurve(
            z_value=30.0,
            is_closed=False,
        )

        wall = self.loaded["extrude_wall_curve"](
            source,
            -100.0,
            200.0,
            0.01,
        )

        self.assertEqual(wall.name, "segment-wall")
        self.assertFalse(wall.IsSolid)
        self.assertEqual(source.z_value, 30.0)
        self.assertEqual(source.mutations, [])
        self.assertEqual(source.duplicate_calls, 1)
        profile, vector = FakeSurfaceApi.calls[0]
        self.assertIs(profile, source.last_duplicate)
        self.assertEqual(profile.z_value, -100.0)
        self.assertEqual((vector.X, vector.Y, vector.Z), (0.0, 0.0, 300.0))
        self.assertTrue(FakeSurfaceApi.results[0].disposed)

    def test_wall_curve_must_be_planar_and_horizontal(self):
        for curve, message in (
            (FakeCurve(plane_is_planar=False), "planar"),
            (FakeCurve(plane_parallel=False), "horizontal"),
        ):
            with self.subTest(message=message):
                with self.assertRaisesRegex(ValueError, message):
                    self.loaded["extrude_wall_curve"](
                        curve,
                        0.0,
                        100.0,
                        0.01,
                    )


class BoundaryBrepSplitTests(unittest.TestCase):
    def setUp(self):
        FakeVolumeMassPropertiesApi.calls = []
        FakeVolumeMassPropertiesApi.results = []
        FakeAreaMassPropertiesApi.calls = []
        FakeAreaMassPropertiesApi.results = []
        self.loaded = load_surface_module()
        self.context = make_context()
        self.cutter = FakeBrep("cutter", solid=True)

    def test_split_filters_by_piece_centroid_without_mutating_source(self):
        inside = FakeBrep(
            "inside",
            area_centroid=FakePoint(10.0, 0.0, 50.0),
        )
        outside = FakeBrep(
            "outside",
            area_centroid=FakePoint(-10.0, 0.0, 50.0),
        )
        source = FakeBrep(
            "source",
            split_result=[inside, outside],
            area_centroid=FakePoint(0.0, 0.0, 0.0),
        )

        kept = self.loaded["split_brep_inside_boundary"](
            source,
            self.cutter,
            self.context,
            absolute_tolerance=0.03,
        )

        self.assertEqual(kept, [inside])
        self.assertFalse(inside.disposed)
        self.assertTrue(outside.disposed)
        self.assertEqual(source.split_calls, [])
        self.assertEqual(source.mutations, [])
        self.assertEqual(source.duplicate_calls, 1)
        self.assertEqual(
            source.last_duplicate.split_calls,
            [(self.cutter, 0.03)],
        )
        self.assertTrue(source.last_duplicate.disposed)
        self.assertEqual(len(self.loaded["containment_calls"]), 2)
        self.assertTrue(
            all(call[2] is True for call in self.loaded["containment_calls"])
        )
        self.assertTrue(
            all(item.disposed for item in FakeAreaMassPropertiesApi.results)
        )

    def test_oriented_trim_is_preferred_without_centroid_filtering(self):
        concave_inside = FakeBrep(
            "concave-inside",
            area_centroid=FakePoint(-100.0, 0.0, 0.0),
        )
        source = FakeBrep(
            "source",
            trim_result=[concave_inside],
            trim_raises=False,
            split_result=[],
        )

        kept = self.loaded["split_brep_inside_boundary"](
            source,
            self.cutter,
            self.context,
            absolute_tolerance=0.02,
        )

        self.assertEqual([concave_inside], kept)
        self.assertEqual(
            [(self.cutter, 0.02)],
            source.last_duplicate.trim_calls,
        )
        self.assertEqual([], source.last_duplicate.split_calls)
        self.assertEqual([], self.loaded["containment_calls"])
        self.assertTrue(source.last_duplicate.disposed)

    def test_split_failure_and_empty_result_use_duplicate_centroid(self):
        source_inside = FakeBrep(
            "inside-source",
            split_raises=True,
            area_centroid=FakePoint(2.0, 0.0, 0.0),
        )
        kept = self.loaded["split_brep_inside_boundary"](
            source_inside,
            self.cutter,
            self.context,
        )
        self.assertEqual(kept, [source_inside.last_duplicate])

        source_outside = FakeBrep(
            "outside-source",
            split_result=[],
            area_centroid=FakePoint(-2.0, 0.0, 0.0),
        )
        kept = self.loaded["split_brep_inside_boundary"](
            source_outside,
            self.cutter,
            self.context,
        )
        self.assertEqual(kept, [])
        self.assertTrue(source_outside.last_duplicate.disposed)

    def test_centroid_uses_volume_then_bbox_fallback(self):
        solid = FakeBrep(
            "solid",
            solid=True,
            volume_centroid=FakePoint(4.0, 0.0, 0.0),
        )
        bbox_piece = FakeBrep(
            "bbox-piece",
            bbox=FakeBoundingBox(
                FakePoint(2.0, -1.0, 0.0),
                FakePoint(6.0, 1.0, 10.0),
            ),
        )
        source = FakeBrep(
            "source",
            split_result=[solid, bbox_piece],
        )

        kept = self.loaded["split_brep_inside_boundary"](
            source,
            self.cutter,
            self.context,
        )

        self.assertEqual(kept, [solid, bbox_piece])
        self.assertEqual(FakeVolumeMassPropertiesApi.calls, [solid])
        self.assertNotIn(solid, FakeAreaMassPropertiesApi.calls)
        self.assertTrue(FakeVolumeMassPropertiesApi.results[0].disposed)

    def test_invalid_breps_and_duplicate_failure_raise(self):
        split = self.loaded["split_brep_inside_boundary"]
        with self.assertRaisesRegex(ValueError, "source Brep"):
            split(None, self.cutter, self.context)
        with self.assertRaisesRegex(ValueError, "cutter Brep"):
            split(FakeBrep("source"), None, self.context)
        with self.assertRaisesRegex(ValueError, "Source Brep is not valid"):
            split(
                FakeBrep("source", valid=False),
                self.cutter,
                self.context,
            )
        with self.assertRaisesRegex(ValueError, "could not be duplicated"):
            split(
                FakeBrep("source", duplicate_fails=True),
                self.cutter,
                self.context,
            )


if __name__ == "__main__":
    unittest.main()
