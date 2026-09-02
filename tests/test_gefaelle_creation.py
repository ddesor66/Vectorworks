# -*- coding: utf-8 -*-
"""Creation regressions for transient Vectorworks PIO return values."""
from __future__ import absolute_import

import importlib
import math
import sys
import types
import unittest


class CreationAPI(types.ModuleType):
    def __init__(self):
        super(CreationAPI, self).__init__("vs")
        self.reset = []
        self.moves = []

    def GetLayer(self, _handle):
        return "LAYER"

    def GetLScale(self, _layer):
        return 1.0

    def GetSymRot(self, _handle):
        return 0.0

    def GetSymLoc(self, _handle):
        return (4.0, 5.0)

    def GetSymLoc3D(self, _handle):
        # Real VW 2026 can return this while the initial reset is pending.
        return None

    def GetLayerElevation(self, _layer):
        return (12000.0, 0.0)

    def HMove(self, _handle, dx, dy):
        self.moves.append((dx, dy))

    def Move3DObj(self, _handle, dx, dy, dz):
        self.moves.append((dx, dy, dz))

    def ResetObject(self, handle):
        self.reset.append(handle)


def load_modules(api):
    for name in tuple(sys.modules):
        if name == "PD_GefaelleTool" or name.startswith("PD_GefaelleTool."):
            del sys.modules[name]
    sys.modules["vs"] = api
    adapter = importlib.import_module("PD_GefaelleTool.vw_adapter")
    render = importlib.import_module("PD_GefaelleTool.live_render")
    grade = importlib.import_module("PD_GefaelleTool.grade_compat")
    geometry = importlib.import_module("PD_GefaelleTool.point_geometry")
    return adapter, render, grade, geometry


class GefaelleCreationTests(unittest.TestCase):
    def setUp(self):
        self.previous_vs = sys.modules.get("vs")

    def tearDown(self):
        for name in tuple(sys.modules):
            if name == "PD_GefaelleTool" or name.startswith("PD_GefaelleTool."):
                del sys.modules[name]
        if self.previous_vs is None:
            sys.modules.pop("vs", None)
        else:
            sys.modules["vs"] = self.previous_vs

    def test_missing_initial_pio_3d_location_uses_known_zero_z(self):
        api = CreationAPI()
        adapter, render, _grade, _geometry = load_modules(api)
        adapter.units_to_meters = lambda: 1.0
        result = render.context(
            "PIO", {"preferences": {"offset_mm": 2.5}, "text_angle": 0.0})
        self.assertEqual(12.0, result[-1])
        self.assertTrue(all(math.isfinite(value) for value in result[4]))

    def test_stake_sync_defers_matrix_check_when_reset_is_pending(self):
        api = CreationAPI()
        adapter, _render, grade, _geometry = load_modules(api)
        grade._configure = lambda _handle, _z: None
        grade._sync_position("STAKE", (4.0, 5.0), 8.75)
        self.assertEqual(["STAKE"], api.reset)
        self.assertEqual([], api.moves)
        self.assertIsNone(adapter.symbol_location_3d("STAKE"))

    def test_unreadable_layer_elevation_is_a_domain_error(self):
        api = CreationAPI()
        adapter, _render, _grade, _geometry = load_modules(api)
        api.GetLayerElevation = lambda _layer: None
        with self.assertRaisesRegex(Exception, "Ebenenhöhe"):
            adapter.layer_elevation_units("LAYER", 1.0)

    def test_3d_marker_reports_pending_symbol_position_as_domain_error(self):
        api = CreationAPI()
        _adapter, _render, _grade, geometry = load_modules(api)
        with self.assertRaisesRegex(Exception, "3D-Position des Punktsymbols"):
            geometry._symbol_xyz("SYMBOL")


if __name__ == "__main__":
    unittest.main()
