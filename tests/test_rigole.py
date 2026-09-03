# -*- coding: utf-8 -*-
"""Pure regression tests for managed canal rigoles and their quantities."""
from __future__ import absolute_import

import math
import os
import sys
import tempfile
import types
import unittest
import xml.etree.ElementTree as element_tree
import zipfile
from unittest import mock


sys.modules.setdefault("vs", types.ModuleType("vs"))

from PD_KanalTool import core as canal_core
from PD_KanalTool import live as canal_live
from PD_KanalLeitungMengen import core as quantity_core
from PD_KanalLeitungMengen import reporting


def rigole(**changes):
    value = {
        "schema": canal_core.SCHEMA,
        "id": "rig-1",
        "name": "RIG.001",
        "x_m": 10.0,
        "y_m": 20.0,
        "length_m": 10.0,
        "width_m": 3.0,
        "height_m": 1.0,
        "bottom_m": 99.0,
        "terrain_top_m": 101.0,
        "rotation_deg": 0.0,
        "slope_angle_deg": 60.0,
        "fill_color": [36000, 52000, 65535],
        "pen_color": [0, 20000, 50000],
        "transparency_percent": 50.0,
        "note": "Rückhaltung Bauabschnitt 1",
        "connections": [],
    }
    value.update(changes)
    return canal_core.validate_rigole(value)


class RigoleCoreTests(unittest.TestCase):
    def test_volume_and_label_use_the_managed_source_data(self):
        value = rigole(connections=[{
            "node_id": "node-1", "side": "right", "fraction": 0.25,
            "invert_m": 99.4,
        }])
        self.assertAlmostEqual(30.0, value["gross_volume_m3"])
        self.assertAlmostEqual(28.5, value["storage_volume_m3"])
        self.assertAlmostEqual(100.0, value["top_m"])
        label = canal_core.rigole_label(
            value, {"height_decimals": 2, "length_decimals": 2})
        self.assertIn("Rückhaltung Bauabschnitt 1", label)
        self.assertIn("Rigolenvolumen = 30,00 m³", label)
        self.assertIn("Rückhaltevolumen (95 % FV) = 28,50 m³", label)
        self.assertIn("Anschluss 1 | KS = 99,40 m", label)

    def test_terrain_must_not_cut_through_rigole(self):
        with self.assertRaisesRegex(canal_core.SewerError, "Oberkante Gelände"):
            rigole(terrain_top_m=99.5)

    def test_rotated_graphical_pick_roundtrips_as_side_and_fraction(self):
        value = rigole(rotation_deg=90.0)
        expected = canal_core.rigole_connection_xy(value, "right", 0.5)
        selected = canal_core.project_on_rigole(value, expected, tolerance_m=0.01)
        self.assertEqual("right", selected["side"])
        self.assertAlmostEqual(0.5, selected["fraction"])
        self.assertAlmostEqual(expected[0], selected["x_m"])
        self.assertAlmostEqual(expected[1], selected["y_m"])

    def test_click_away_from_body_is_rejected(self):
        with self.assertRaisesRegex(canal_core.SewerError, "Anschlusspunkt"):
            canal_core.project_on_rigole(rigole(), (100.0, 100.0), 0.10)

    def test_new_canal_is_height_locked_to_selected_rigole_side(self):
        value = rigole(x_m=0.0, y_m=0.0)
        selected = canal_core.project_on_rigole(value, (5.0, 0.75), 0.01)
        node = canal_core.validate_shaft({
            "schema": canal_core.SCHEMA, "id": "rigole-node", "kind": "RW",
            "name": "", "note": "", "x_m": selected["x_m"],
            "y_m": selected["y_m"], "kd_m": 101.0, "ks_m": 99.4,
            "diameter_m": 0.0, "construction_material": "PP",
            "wall_thickness_m": 0.0, "cover_diameter_m": 0.625,
            "cover_symbol": "", "cover_placement": "center",
            "cover_rotation_deg": 0.0, "structure_type": "junction",
            "special_outline_m": [], "drops": [], "visible": False,
            "color_override": None, "rigole_id": value["id"],
        }, allow_hidden=True)
        identifiers = iter(("outer-node", "pipe-1"))
        built = canal_core.build_network(
            (((selected["x_m"], selected["y_m"]), (15.0, 0.75)),), {
                "kind": "RW", "dn_mm": 150, "material": "PP",
                "start_invert_m": 99.4, "calculation_mode": "start",
                "calculation_value": 1.0, "reverse_flow": True,
                "cover_height_m": 101.0, "shaft_diameter_m": 1.0,
                "shaft_construction_material": "PP",
                "shaft_wall_thickness_m": 0.0, "cover_diameter_m": 0.625,
                "cover_symbol": "", "cover_placement": "center",
                "cover_rotation_deg": 0.0, "shaft_mode": "endpoints",
                "join_style": "round", "fillet_radius_m": 0.2,
                "flow_arrow_scale": 1.0, "label_layout": "one_line",
                "label_width_m": 0.0, "draw_3d": True,
                "graphics_mode": "double_line",
            }, existing_shafts=(node,), next_numbers={"RW": 1},
            identity_factory=lambda: next(identifiers))
        self.assertEqual(1, len(built["pipes"]))
        pipe = built["pipes"][0]
        self.assertEqual("rigole-node", pipe["end_id"])
        self.assertAlmostEqual(99.4, pipe["end_invert_m"])
        self.assertGreater(pipe["start_invert_m"], pipe["end_invert_m"])


class RigoleVectorworksGeometryTests(unittest.TestCase):
    class ExtrudeAPI(object):
        def __init__(self, result_type=24):
            self.events = []
            self.last = "PLAN"
            self.result_type = int(result_type)

        def LNewObj(self):
            return self.last

        def BeginXtrd(self, bottom, top):
            self.events.append(("begin_extrude", bottom, top))

        def ClosePoly(self):
            self.events.append("close_mode")

        def BeginPoly(self):
            self.events.append("begin_polygon")

        def AddPoint(self, point):
            self.events.append(("point", tuple(point)))

        def EndPoly(self):
            self.events.append("end_polygon")

        def OpenPoly(self):
            self.events.append("open_mode")

        def EndXtrd(self):
            self.events.append("end_extrude")
            self.last = "BODY"

        def GetTypeN(self, handle):
            return self.result_type if handle == "BODY" else 5

    def test_3d_rigole_uses_closed_profile_and_returns_native_extrude(self):
        api = self.ExtrudeAPI()
        with mock.patch.object(canal_live, "vs", api):
            body = canal_live._closed_extrude(
                ((-5.0, -1.5), (5.0, -1.5), (5.0, 1.5), (-5.0, 1.5)),
                99.0, 100.0)
        self.assertEqual("BODY", body)
        self.assertLess(api.events.index("close_mode"),
                        api.events.index("begin_polygon"))
        self.assertLess(api.events.index("end_polygon"),
                        api.events.index("open_mode"))
        self.assertLess(api.events.index("open_mode"),
                        api.events.index("end_extrude"))
        self.assertEqual(4, len([event for event in api.events
                               if isinstance(event, tuple) and event[0] == "point"]))

    def test_3d_rigole_rejects_non_extrude_result(self):
        api = self.ExtrudeAPI(result_type=21)
        with mock.patch.object(canal_live, "vs", api):
            with self.assertRaisesRegex(canal_core.SewerError, "keinen geschlossenen"):
                canal_live._closed_extrude(
                    ((-1.0, -1.0), (1.0, -1.0), (1.0, 1.0), (-1.0, 1.0)),
                    0.0, 1.0)


class RigoleQuantityTests(unittest.TestCase):
    def test_sloped_pit_and_backfill_are_auditable(self):
        value = rigole()
        result = quantity_core.rigole_earthwork(value)
        tangent = math.tan(math.radians(60.0))
        expected = (11.0 * 4.0 * 2.0 +
                    (11.0 + 4.0) / tangent * 2.0 ** 2 +
                    4.0 / 3.0 / tangent ** 2 * 2.0 ** 3)
        self.assertAlmostEqual(expected, result["excavation_volume_m3"])
        self.assertAlmostEqual(expected - 30.0, result["backfill_volume_m3"])
        self.assertAlmostEqual(28.5, result["storage_volume_m3"])
        self.assertAlmostEqual(11.0 + 4.0 / tangent, result["top_length_m"])

    def test_45_degree_pit_is_larger_and_pavement_reduces_backfill(self):
        sixty = quantity_core.rigole_earthwork(rigole(slope_angle_deg=60.0))
        forty_five = quantity_core.rigole_earthwork(
            rigole(slope_angle_deg=45.0), True, 0.20)
        self.assertGreater(
            forty_five["excavation_volume_m3"], sixty["excavation_volume_m3"])
        self.assertGreater(forty_five["pavement_volume_m3"], 0.0)
        self.assertAlmostEqual(
            forty_five["excavation_volume_m3"] -
            forty_five["gross_volume_m3"] - forty_five["pavement_volume_m3"],
            forty_five["backfill_volume_m3"])

    def test_analysis_and_excel_specs_contain_rigole_and_pavement(self):
        report = quantity_core.analyze(
            (), (), (), rigoles=(rigole(),),
            include_pavement=True, pavement_thickness_m=0.20)
        report["metadata"] = {
            "document": "Rigolentest.vwx", "created": "03.09.2026 12:00",
            "standard": "DIN EN 1610", "shoring": "Verbaute Gräben",
            "pavement": "berücksichtigt; 0,20 m",
        }
        self.assertEqual(1, report["totals"]["rigole_count"])
        self.assertAlmostEqual(30.0, report["totals"]["rigole_gross_volume_m3"])
        self.assertAlmostEqual(28.5, report["totals"]["rigole_storage_volume_m3"])
        self.assertGreater(report["totals"]["pavement_total_m3"], 0.0)
        self.assertEqual("03_Rigolen", reporting.detail_sheets(report)[2]["name"])
        visible = repr(reporting.xlsx_sheets(report))
        self.assertIn("RIG.001", visible)
        self.assertIn("Wasservolumen 95 %", visible)
        self.assertIn("Oberbau gesamt", visible)

    def test_rigole_excel_export_is_valid_ooxml(self):
        report = quantity_core.analyze(
            (), (), (), rigoles=(rigole(),),
            include_pavement=True, pavement_thickness_m=0.20)
        report["metadata"] = {
            "document": "Rigolentest.vwx", "created": "03.09.2026 12:00",
            "standard": "DIN EN 1610", "shoring": "Verbaute Gräben",
            "pavement": "berücksichtigt; 0,20 m",
        }
        with tempfile.TemporaryDirectory() as directory:
            target = os.path.join(directory, "Rigolen-Mengen.xlsx")
            reporting.export_xlsx(target, report)
            with zipfile.ZipFile(target) as archive:
                self.assertIsNone(archive.testzip())
                self.assertEqual(9, len([
                    name for name in archive.namelist()
                    if name.startswith("xl/worksheets/sheet")]))
                for name in archive.namelist():
                    if name.endswith(".xml"):
                        element_tree.fromstring(archive.read(name))


if __name__ == "__main__":
    unittest.main()
