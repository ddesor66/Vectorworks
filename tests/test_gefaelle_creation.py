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

    def test_missing_initial_pio_2d_location_uses_known_local_origin(self):
        api = CreationAPI()
        api.GetSymLoc = lambda _handle: None
        adapter, render, _grade, _geometry = load_modules(api)
        adapter.units_to_meters = lambda: 1.0
        result = render.context(
            "PIO", {"preferences": {"offset_mm": 2.5}, "text_angle": 0.0})
        self.assertEqual((0.0, 0.0), result[4])
        self.assertEqual(12.0, result[-1])

    def test_chain_render_completes_when_initial_2d_location_is_pending(self):
        api = CreationAPI()
        api.GetSymLoc = lambda _handle: None
        adapter, render, _grade, _geometry = load_modules(api)
        adapter.units_to_meters = lambda: 1.0
        adapter.layer_elevation_units = lambda _layer, _factor: 0.0
        lines = []
        adapter._create_line = lambda first, second, _style: lines.append((first, second))
        chain = {
            "points": [
                {"number": 1, "x_m": 2.0, "y_m": 3.0, "height_m": 100.0},
                {"number": 2, "x_m": 7.0, "y_m": 3.0, "height_m": 99.9},
            ],
            "mode": "manual",
            "value": 0.0,
            "level": "Standard",
            "layer_name": "GEF-Standard",
        }
        data = {
            "preferences": {
                "offset_mm": 2.5,
                "classes": {"line": {"name": "GEF-Linie", "color": [0, 0, 0]}},
            },
            "output": {"mode": "2d"},
            "text_angle": 0.0,
            "separate_labels": True,
        }
        render.draw_chain("PIO", data, chain)
        self.assertEqual([((2.0, 3.0), (7.0, 3.0))], lines)

    def test_missing_initial_stake_2d_location_uses_creation_coordinate(self):
        api = CreationAPI()
        api.GetSymLoc = lambda _handle: None
        adapter, _render, grade, _geometry = load_modules(api)
        grade._configure = lambda _handle, _z: None
        grade._sync_position("STAKE", (4.0, 5.0), 8.75)
        self.assertEqual(["STAKE"], api.reset)
        self.assertEqual([], api.moves)

    def test_unreadable_established_2d_location_is_a_domain_error(self):
        api = CreationAPI()
        api.GetSymLoc = lambda _handle: None
        adapter, _render, _grade, _geometry = load_modules(api)
        with self.assertRaisesRegex(Exception, "2D-Einfügeposition"):
            adapter.symbol_location_2d("PIO")

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

    def test_3d_chain_never_sends_native_stakes_to_pd_label_creation(self):
        api = CreationAPI()
        adapter, _render, grade, _geometry = load_modules(api)
        live = importlib.import_module("PD_GefaelleTool.live_objects")
        core = importlib.import_module("PD_GefaelleTool.core")

        names = {}
        handles = {}
        payloads = {}
        resets = []
        labelled = []
        associations = []

        api.ActLayer = lambda: "SOURCE-LAYER"
        api.GetLName = lambda layer: layer
        api.Layer = lambda _name: None
        api.GetName = lambda handle: names.get(handle, "")
        api.GetObject = lambda name: handles.get(name)
        api.AddAssociation = lambda owner, kind, target: (
            associations.append((owner, kind, target)) or True)
        api.HMoveForward = lambda *_args: None
        api.ResetObject = lambda handle: resets.append(handle)
        api.DSelectAll = lambda: None
        api.SetSelect = lambda _handle: None
        api.ReDrawAll = lambda: None

        adapter.chain_records = lambda: ()
        adapter._activate_layer = lambda _name: True
        adapter.units_to_meters = lambda: 1.0
        adapter.write_chain = lambda *_args: None
        live._find_points = lambda: {}
        live._display = lambda _chain, preferences: {
            "preferences": preferences,
            "output": {"mode": "3d"},
            "symbols": {},
            "text_angle": 0.0,
        }

        serial = [0]

        def new_object(_xy, data, name, created):
            serial[0] += 1
            handle = "PD-%d" % serial[0]
            names[handle] = name
            handles[name] = handle
            payloads[handle] = data
            created.append(handle)
            return handle

        live._new_object = new_object
        live._set_point_fields = lambda *_args: None
        live.data_of = lambda handle: payloads.get(handle)
        live.read_chain = lambda _handle: chain

        def native_stake(_owner, _data, point, created):
            created.append("STAKE-%d" % point["number"])

        grade.ensure = native_stake

        def label(owner, data, _created):
            # This line reproduces the old crash if a native Stake leaks in:
            # its payload is None and therefore cannot be subscripted.
            labelled.append((owner, data["role"]))

        live.live_labels.ensure = label
        chain = core.make_chain(
            ((0.0, 0.0), (10.0, 0.0)), 100.0, "slope", 1.0,
            start_number=1, level="Test")

        live.create(chain, {"point_output": {"mode": "3d"}})

        self.assertEqual(["point", "point", "chain"],
                         [role for _handle, role in labelled])
        self.assertFalse(any(handle.startswith("STAKE-")
                             for handle, _role in labelled))
        self.assertIn("STAKE-1", resets)
        self.assertIn("STAKE-2", resets)
        self.assertIn(("PD-1", 4, "PD-3"), associations)
        self.assertIn(("PD-3", 5, "PD-1"), associations)
        self.assertIn(("PD-2", 4, "PD-3"), associations)
        self.assertIn(("PD-3", 5, "PD-2"), associations)


if __name__ == "__main__":
    unittest.main()
