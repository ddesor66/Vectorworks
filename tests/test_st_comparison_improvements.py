# -*- coding: utf-8 -*-
import unittest
import sys
import types

from PD_KanalTool import core as sewer_core
from PD_KanalLeitungMengen import core as report_core

sys.modules.setdefault("vs", types.ModuleType("vs"))
from PD_KanalTool import live as sewer_live


class PipeWallTests(unittest.TestCase):
    def _pipe(self):
        return {
            "schema": 1, "id": "P1", "start_id": "S1", "end_id": "S2",
            "kind": "RW", "dn_mm": 300, "outside_diameter_mm": 355,
            "outside_diameter_explicit": True, "wall_thickness_mm": 27.5,
            "hollow_3d": True, "material": "PP", "start_invert_m": 100.0,
            "end_invert_m": 99.0, "length_m": 50.0,
        }

    def test_wall_and_hollow_state_are_normalized(self):
        pipe = sewer_core.validate_pipe(self._pipe())
        self.assertEqual(pipe["wall_thickness_mm"], 27.5)
        self.assertTrue(pipe["hollow_3d"])
        self.assertAlmostEqual(pipe["slope_percent"], 2.0)

    def test_wall_must_fit_inside_outside_diameter(self):
        pipe = self._pipe()
        pipe["wall_thickness_mm"] = 180.0
        with self.assertRaises(sewer_core.SewerError):
            sewer_core.validate_pipe(pipe)

    def test_hollow_mesh_has_outer_inner_and_annular_faces(self):
        faces = sewer_live._hollow_tube_faces(
            (((0.0, 0.0, 0.0), 0.20), ((1.0, 0.0, 0.0), 0.20)),
            0.02, segments=8)
        self.assertEqual(len(faces), 32)
        self.assertTrue(all(len(face) == 4 for face in faces))


class ReportTests(unittest.TestCase):
    def test_report_contains_coordinates_axis_and_wall(self):
        pipe = PipeWallTests()._pipe()
        shafts = (
            {"id": "S1", "name": "RW.001", "kind": "RW", "visible": False,
             "x_m": 10.0, "y_m": 20.0, "kd_m": 102.0, "ks_m": 100.0},
            {"id": "S2", "name": "RW.002", "kind": "RW", "visible": False,
             "x_m": 60.0, "y_m": 20.0, "kd_m": 101.0, "ks_m": 99.0},
        )
        row = report_core.analyze((sewer_core.validate_pipe(pipe),), shafts, ())["canals"][0]
        self.assertEqual((row["start_x_m"], row["start_y_m"]), (10.0, 20.0))
        self.assertEqual((row["end_x_m"], row["end_y_m"]), (60.0, 20.0))
        self.assertAlmostEqual(row["start_axis_m"], 100.15)
        self.assertAlmostEqual(row["end_axis_m"], 99.15)
        self.assertEqual(row["wall_thickness_mm"], 27.5)
        self.assertTrue(row["hollow_3d"])


if __name__ == "__main__":
    unittest.main()
