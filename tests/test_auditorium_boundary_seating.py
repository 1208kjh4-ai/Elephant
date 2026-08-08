# -*- coding: utf-8 -*-
"""Pure tests for chair placement inside custom auditorium boundaries."""

import ast
import copy
import math
import unittest
from pathlib import Path
from unittest import mock

from commands.auditorium_generator.calculations import seating


ROOT = Path(__file__).resolve().parents[1]
SEAT_PREVIEW_PATH = (
    ROOT
    / "commands"
    / "auditorium_generator"
    / "seat_preview_geometry.py"
)


def _params(block_counts):
    return {
        "seat_module_width": 100.0,
        "longitudinal_aisle_width": 50.0,
        "side_floor_margin": 0.0,
        "seat_block_counts": list(block_counts),
    }


def _section(row_count=1, x_start=1000.0):
    return {
        "x_values": [x_start + index * 1000.0 for index in range(row_count)],
        "base_z_values": [index * 200.0 for index in range(row_count)],
    }


def _row_values(placements, row_index=0):
    return [
        placement["lateral"]
        for placement in placements
        if placement["row_index"] == row_index
    ]


class CustomBoundarySeatingTests(unittest.TestCase):
    def test_no_boundary_path_retains_existing_records_and_positions(self):
        params = _params([2, 1])
        section = _section(2)
        before = copy.deepcopy((params, section))

        result = seating.calculate_3d_seat_placements(params, section)

        self.assertEqual(before, (params, section))
        self.assertEqual([2, 1], result["row_block_counts"][0])
        self.assertEqual([3, 3], result["chairs_per_row_values"])
        self.assertEqual([5, 5], result["armrests_per_row_values"])
        self.assertEqual(350.0, result["total_width"])
        self.assertEqual(
            [-125.0, -25.0, 125.0],
            _row_values(result["chair_placements"]),
        )
        self.assertNotIn("row_regions", result)
        self.assertTrue(all(
            "boundary_constrained" not in placement
            for placement in (
                result["chair_placements"]
                + result["armrest_placements"]
            )
        ))

    def test_convex_region_centers_fixed_blocks_and_keeps_full_modules(self):
        params = _params([2, 2])
        params["side_floor_margin"] = 20.0
        result = seating.calculate_3d_seat_placements(
            params,
            _section(),
            None,
            [[(960.0, 1540.0)]],
        )

        self.assertEqual([2, 2], result["row_block_counts"][0])
        self.assertEqual([4], result["chairs_per_row_values"])
        self.assertEqual([6], result["armrests_per_row_values"])
        self.assertEqual(
            [1075.0, 1175.0, 1325.0, 1425.0],
            _row_values(result["chair_placements"]),
        )
        self.assertEqual(530.0, result["row_total_widths"][0])
        self.assertEqual([(980.0, 1520.0)], result["row_regions"][0])
        self.assertTrue(all(
            placement["boundary_constrained"]
            for placement in (
                result["chair_placements"]
                + result["armrest_placements"]
            )
        ))

    def test_fixed_overflow_removes_only_non_fitting_seats(self):
        result = seating.calculate_3d_seat_placements(
            _params([6]),
            _section(),
            None,
            [[(-190.0, 190.0)]],
        )

        self.assertEqual([[2]], result["row_block_counts"])
        self.assertEqual([-50.0, 50.0], _row_values(
            result["chair_placements"]
        ))
        self.assertEqual(
            [-100.0, 0.0, 100.0],
            _row_values(result["armrest_placements"]),
        )
        self.assertEqual([280.0], result["row_total_widths"])

    def test_multi_interval_policy_margins_every_boundary_edge(self):
        params = _params([10])
        params["side_floor_margin"] = 40.0
        result = seating.calculate_3d_seat_placements(
            params,
            _section(),
            None,
            [[(-580.0, -60.0), (60.0, 580.0)]],
        )

        self.assertEqual(
            [
                -450.0,
                -350.0,
                -250.0,
                250.0,
                350.0,
                450.0,
            ],
            _row_values(result["chair_placements"]),
        )
        self.assertEqual([6], result["chairs_per_row_values"])
        self.assertEqual([8], result["armrests_per_row_values"])
        self.assertEqual(
            [(-540.0, -100.0), (100.0, 540.0)],
            result["row_regions"][0],
        )
        self.assertFalse(any(
            -60.0 < lateral < 60.0
            for lateral in _row_values(result["armrest_placements"])
        ))

    def test_auto_blocks_use_custom_rectangular_span(self):
        params = _params(["a", 2, "a"])
        params["longitudinal_aisle_width"] = 100.0
        params["side_floor_margin"] = 100.0

        resolved = seating.resolve_row_seat_block_counts(
            params,
            1000.0,
            None,
            [(-540.0, 540.0)],
        )
        result = seating.calculate_3d_seat_placements(
            params,
            _section(),
            None,
            [[(-540.0, 540.0)]],
        )

        self.assertEqual([2, 2, 2], resolved)
        self.assertEqual([[2, 2, 2]], result["row_block_counts"])
        self.assertEqual([6], result["chairs_per_row_values"])
        self.assertEqual(880.0, result["row_total_widths"][0])

    def test_narrow_custom_auto_row_falls_back_to_zero_auto_seats(self):
        params = _params(["a", 2, "a"])
        section = _section()
        row_regions = [[(-190.0, 190.0)]]

        resolved = seating.resolve_row_seat_block_counts(
            params,
            1000.0,
            None,
            row_regions[0],
        )
        placements = seating.calculate_3d_seat_placements(
            params,
            section,
            None,
            row_regions,
        )
        count = seating.calculate_3d_seat_count_for_row_regions(
            params,
            section,
            None,
            row_regions,
        )
        total = seating.calculate_total_3d_seat_count(
            params,
            section,
            [],
            None,
            [row_regions],
        )

        self.assertEqual([0, 2, 0], resolved)
        self.assertEqual([[0, 2, 0]], placements["row_block_counts"])
        self.assertEqual(2, len(placements["chair_placements"]))
        self.assertEqual(2, count)
        self.assertEqual(2, total)

        radial_params = _params(["a"])
        with self.assertRaisesRegex(ValueError, "radial row width"):
            seating.resolve_row_seat_block_counts(
                radial_params,
                0.0,
                {
                    "mode": "radial",
                    "radius": 1000.0,
                    "half_angle": 0.02,
                },
            )

    def test_empty_region_is_zero_seats_and_zero_armrests(self):
        params = _params([3, 3])
        result = seating.calculate_3d_seat_placements(
            params,
            _section(2),
            None,
            [[], [(-240.0, 240.0)]],
        )

        self.assertEqual([0, 2], result["chairs_per_row_values"])
        self.assertEqual([0, 4], result["armrests_per_row_values"])
        self.assertEqual([0.0, 330.0], result["row_total_widths"])

    def test_invalid_or_missing_row_regions_raise_clear_value_errors(self):
        params = _params([2])
        section = _section(2)
        cases = (
            ([[(0.0, 500.0)]], "exactly 2"),
            ([[(0.0, 500.0)], None], "missing"),
            ([[(0.0, math.nan)], [(0.0, 500.0)]], "finite"),
            ([[(500.0, 0.0)], [(0.0, 500.0)]], "right greater"),
        )
        for row_regions, message in cases:
            with self.subTest(row_regions=row_regions):
                with self.assertRaisesRegex(ValueError, message):
                    seating.calculate_3d_seat_placements(
                        params,
                        section,
                        None,
                        row_regions,
                    )

    def test_total_count_uses_actual_tier_placements(self):
        params = _params([4])
        stalls = _section(2)
        visible_balcony = _section(1, 5000.0)
        balcony_results = [visible_balcony, None]
        tier_regions = [
            [[(-240.0, 240.0)], []],
            [[(-140.0, 140.0)]],
            None,
        ]

        count = seating.calculate_total_3d_seat_count(
            params,
            stalls,
            balcony_results,
            None,
            tier_regions,
        )

        self.assertEqual(6, count)
        with self.assertRaisesRegex(ValueError, "exactly 3"):
            seating.calculate_total_3d_seat_count(
                params,
                stalls,
                balcony_results,
                None,
                tier_regions[:2],
            )

    def test_count_only_helper_matches_placements_for_all_region_modes(self):
        fixed_params = _params([6])
        automatic_params = _params(["a", 2, "a"])
        automatic_params["longitudinal_aisle_width"] = 100.0
        automatic_params["side_floor_margin"] = 100.0
        cases = (
            (
                fixed_params,
                _section(),
                None,
                [[(-190.0, 190.0)]],
            ),
            (
                _params([10]),
                _section(),
                None,
                [[(-580.0, -60.0), (60.0, 580.0)]],
            ),
            (
                _params([3, 3]),
                _section(3),
                None,
                [[], [(-240.0, 240.0)], [(-1000.0, 1000.0)]],
            ),
            (
                automatic_params,
                _section(2),
                None,
                [[(-540.0, 540.0)], [(-700.0, 700.0)]],
            ),
            (
                _params([8]),
                _section(),
                {
                    "mode": "radial",
                    "radius": 10000.0,
                    "half_angle": 0.2,
                },
                [[(-500.0, 500.0)]],
            ),
        )
        for params, section, layout_context, row_regions in cases:
            with self.subTest(
                blocks=params["seat_block_counts"],
                row_regions=row_regions,
            ):
                inputs_before = copy.deepcopy(
                    (params, section, layout_context, row_regions)
                )
                placements = seating.calculate_3d_seat_placements(
                    params,
                    section,
                    layout_context,
                    row_regions,
                )
                count = seating.calculate_3d_seat_count_for_row_regions(
                    params,
                    section,
                    layout_context,
                    row_regions,
                )
                self.assertEqual(
                    len(placements["chair_placements"]),
                    count,
                )
                self.assertEqual(
                    inputs_before,
                    (params, section, layout_context, row_regions),
                )

    def test_custom_total_does_not_build_chair_or_armrest_records(self):
        params = _params([4])
        stalls = _section(2)
        balcony = _section(1, 5000.0)
        tier_regions = [
            [[(-240.0, 240.0)], []],
            [[(-140.0, 140.0)]],
        ]

        with mock.patch.object(
            seating,
            "calculate_3d_seat_placements",
            side_effect=AssertionError(
                "The count-only path created placement records."
            ),
        ) as placement_builder:
            count = seating.calculate_total_3d_seat_count(
                params,
                stalls,
                [balcony],
                None,
                tier_regions,
            )

        self.assertEqual(6, count)
        placement_builder.assert_not_called()

    def test_preview_builder_exposes_regions_and_row_overrides(self):
        tree = ast.parse(SEAT_PREVIEW_PATH.read_text(encoding="utf-8"))
        functions = {
            node.name: node
            for node in tree.body
            if isinstance(node, ast.FunctionDef)
        }
        builder = functions["build_3d_seat_module_geometry"]

        self.assertEqual(
            ["row_regions", "row_overrides"],
            [argument.arg for argument in builder.args.args[-2:]],
        )
        self.assertIsInstance(builder.args.defaults[-2], ast.Constant)
        self.assertIsNone(builder.args.defaults[-2].value)
        self.assertIsInstance(builder.args.defaults[-1], ast.Constant)
        self.assertIsNone(builder.args.defaults[-1].value)
        placement_calls = [
            node
            for node in ast.walk(builder)
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "calculate_3d_seat_placements"
            )
        ]
        self.assertEqual([3, 3, 4, 4], sorted(
            len(call.args) for call in placement_calls
        ))
        self.assertEqual(
            2,
            sum(
                1
                for call in placement_calls
                if any(
                    keyword.arg == "row_overrides"
                    for keyword in call.keywords
                )
            ),
        )


if __name__ == "__main__":
    unittest.main()
