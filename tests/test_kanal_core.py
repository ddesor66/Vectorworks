# -*- coding: utf-8 -*-
"""Focused regression tests for channel shaft labels and shaft connections."""
from __future__ import absolute_import

import unittest

from PD_KanalTool import core


def shaft(identity, name, x_m, ks_m, material="concrete", construction_label=None):
    value = {
        "schema": core.SCHEMA,
        "id": identity,
        "kind": "RW",
        "name": name,
        "note": "",
        "x_m": x_m,
        "y_m": 0.0,
        "kd_m": ks_m + 1.5,
        "ks_m": ks_m,
        "diameter_m": 1.0,
        "construction_material": material,
        "wall_thickness_m": 0.15,
        "cover_diameter_m": 0.625,
        "cover_symbol": "",
        "cover_placement": "auto",
        "cover_rotation_deg": 0.0,
        "structure_type": "round",
        "special_outline_m": [],
        "drops": [{"pipe_id": "drop-1", "upper_invert_m": ks_m + 0.5,
                   "lower_invert_m": ks_m}],
        "visible": True,
        "color_override": None,
    }
    if construction_label is not None:
        value["construction_label"] = construction_label
    return core.validate_shaft(value, allow_hidden=True)


def preferences():
    return {"height_decimals": 2, "length_decimals": 2,
            "slope_decimals": 2}


def connection_options():
    return {
        "kind": "RW",
        "dn_mm": 300,
        "outside_diameter_mm": 300,
        "outside_diameter_explicit": False,
        "material": "STB",
        "shaft_diameter_m": 1.0,
        "shaft_construction_material": "concrete",
        "shaft_wall_thickness_m": 0.15,
        "cover_diameter_m": 0.625,
        "cover_symbol": "",
        "cover_placement": "auto",
        "cover_rotation_deg": 0.0,
        "join_style": "round",
        "fillet_radius_m": 0.2,
        "flow_arrow_scale": 1.0,
        "label_layout": "one_line",
        "label_width_m": 0.0,
        "draw_3d": True,
        "graphics_mode": "double_line",
        "line_type": 1,
        "axis_line_type": 2,
        "color_override": None,
    }


class ShaftLabelTests(unittest.TestCase):
    def test_compact_concrete_label_has_only_requested_rows(self):
        value = shaft("s1", "RW.001", 0.0, 100.0)
        endpoints = (
            {"tag": "Z1", "role": "in", "invert_m": 100.20,
             "dn_mm": 300, "material": "STB", "bearing_deg": 11.1},
            {"tag": "A1", "role": "out", "invert_m": 100.00,
             "dn_mm": 300, "material": "STB", "bearing_deg": 191.1},
        )
        self.assertEqual(
            core.shaft_label(value, endpoints, preferences()),
            "RW.001\n"
            "Bauart: B\n"
            "D.= 1,00 m\n"
            "KD = 101,50 m\n"
            "Zulauf | KS = 100,20 m\n"
            "Ablauf | KS = 100,00 m\n"
            "Tiefe = 1,50 m")
        self.assertNotIn("STB", core.shaft_label(value, endpoints, preferences()))

    def test_multiple_inlets_are_numbered_only_when_heights_differ(self):
        value = shaft("s1", "RW.001", 0.0, 100.0)
        endpoints = (
            {"tag": "Z1", "role": "in", "invert_m": 100.20,
             "dn_mm": 300, "material": "STB", "bearing_deg": 10.0},
            {"tag": "Z2", "role": "in", "invert_m": 100.10,
             "dn_mm": 250, "material": "PVC", "bearing_deg": 80.0},
            {"tag": "A1", "role": "out", "invert_m": 100.00,
             "dn_mm": 300, "material": "STB", "bearing_deg": 190.0},
        )
        label = core.shaft_label(value, endpoints, preferences())
        self.assertIn("Z1 Zulauf | KS = 100,20 m", label)
        self.assertIn("Z2 Zulauf | KS = 100,10 m", label)
        self.assertIn("Ablauf | KS = 100,00 m", label)
        self.assertNotIn("A1 Ablauf", label)
        self.assertNotIn("STB", label)
        self.assertNotIn("PVC", label)

    def test_connection_text_angles_follow_pipe_and_remain_readable(self):
        self.assertAlmostEqual(0.0, core.readable_line_angle(1.0, 0.0))
        self.assertAlmostEqual(0.0, core.readable_line_angle(-1.0, 0.0))
        self.assertAlmostEqual(45.0, core.readable_line_angle(1.0, 1.0))
        self.assertAlmostEqual(45.0, core.readable_line_angle(-1.0, -1.0))
        self.assertAlmostEqual(90.0, core.readable_line_angle(0.0, 1.0))
        with self.assertRaises(core.SewerError):
            core.readable_line_angle(0.0, 0.0)

    def test_pp_and_free_construction_labels(self):
        self.assertEqual(shaft("s1", "RW.001", 0.0, 100.0, "PP")["construction_label"], "PP")
        self.assertEqual(
            shaft("s2", "RW.002", 5.0, 99.0, "concrete", "Drosselschacht")[
                "construction_label"],
            "Drosselschacht")
        with self.assertRaises(core.SewerError):
            shaft("s3", "RW.003", 10.0, 98.0, "PP", "PP\nungültig")

    def test_equal_height_connections_show_one_common_invert(self):
        value = shaft("s1", "RW.001", 0.0, 100.0)
        label = core.shaft_label(
            value, (("in", 100.0), ("out", 100.0)), preferences())
        self.assertNotIn("Zulauf", label)
        self.assertNotIn("Ablauf", label)
        self.assertIn("KS = 100,00 m", label)
        self.assertEqual(6, len(label.splitlines()))

    def test_supplementary_text_is_directly_below_shaft_name(self):
        value = core.validate_shaft(dict(
            shaft("s1", "RW.001", 0.0, 100.0),
            note="Drosselschacht 4,0 l/s"), allow_hidden=True)
        lines = core.shaft_label(value, (), preferences()).splitlines()
        self.assertEqual("RW.001", lines[0])
        self.assertEqual("Drosselschacht 4,0 l/s", lines[1])
        self.assertEqual("Bauart: B", lines[2])

    def test_holding_connection_station_is_part_of_normal_shaft_label(self):
        value = core.validate_shaft(dict(
            shaft("connection", "RW.010", 4.0, 99.6),
            connection_station={
                "station_enabled": True,
                "main_start_id": "s1", "main_end_id": "s2",
                "main_pipe_ids": ["p1", "p2"],
                "station_m": 6.0, "station_zero_id": "s2",
                "station_zero_name": "RW.002",
                "station_equal_inverts": False,
                "station_basis": "lower_invert",
            }), allow_hidden=True)
        label = core.shaft_label(value, (), preferences())
        self.assertIn("Station = 6,00 m ab RW.002", label)

    def test_connection_names_reject_invalid_roles(self):
        self.assertEqual("Zulauf", core.connection_plan_name("in", "Z1", 1))
        self.assertEqual("Z1 Zulauf", core.connection_plan_name("in", "Z1", 2))
        self.assertEqual("Ablauf", core.connection_plan_name("out", "A1", 1))
        with self.assertRaises(core.SewerError):
            core.connection_plan_name("side", "S1", 1)


class ShaftConnectionTests(unittest.TestCase):
    def test_holding_name_uses_visible_downstream_shaft(self):
        first = shaft("s1", "RW.001", 0.0, 100.0)
        bend = dict(shaft("bend", "BEND", 5.0, 99.5),
                    name="", visible=False, diameter_m=0.0,
                    structure_type="junction")
        bend = core.validate_shaft(bend, allow_hidden=True)
        end = shaft("s2", "RW.002", 10.0, 99.0)
        def segment(identity, start_id, end_id, start_m, end_m):
            value = dict(connection_options())
            value.update(schema=core.SCHEMA, id=identity, network_id="RW", name="",
                         start_id=start_id, end_id=end_id,
                         start_invert_m=start_m, end_invert_m=end_m,
                         length_m=5.0)
            return core.validate_pipe(value)
        first_pipe = segment("p1", "s1", "bend", 100.0, 99.5)
        second_pipe = segment("p2", "bend", "s2", 99.5, 99.0)
        self.assertEqual(
            "H-RW.002",
            core.holding_name(first_pipe, (first, bend, end),
                              (first_pipe, second_pipe)))

    def test_holding_name_can_be_hidden_without_changing_technical_label(self):
        first = shaft("s1", "RW.001", 0.0, 100.0)
        second = shaft("s2", "RW.002", 10.0, 99.0)
        value = core.pipe_between_shafts(
            first, second, connection_options(), identity_factory=lambda: "p1")
        value = dict(value, name=core.holding_name(value, (first, second)))
        shown = dict(preferences(), pipe_name_visible=True)
        hidden = dict(preferences(), pipe_name_visible=False)
        self.assertTrue(core.pipe_label(value, shown).startswith("H-RW.002 | "))
        self.assertFalse(core.pipe_label(value, hidden).startswith("H-RW.002"))

    def test_geometric_branch_segments_have_one_two_line_total_label(self):
        first = shaft("s1", "RW.001", 0.0, 100.0)
        second = shaft("s2", "RW.002", 10.0, 99.0)
        value = core.pipe_between_shafts(
            first, second, connection_options(), identity_factory=lambda: "p1")
        value.update(name="H-RW.002", label_layout="two_line", label_length_m=12.5,
                     label_rotation_deg=37.5)
        value = core.validate_pipe(value)
        shown = dict(preferences(), pipe_name_visible=True)
        self.assertEqual(2, len(core.pipe_label(value, shown).splitlines()))
        self.assertIn("12,50 m", core.pipe_label(value, shown))
        self.assertEqual(37.5, value["label_rotation_deg"])
        value.update(label_suppressed=True)
        self.assertEqual("", core.pipe_label(value, shown))

    def test_stub_is_not_a_holding_name_terminal(self):
        first = shaft("s1", "RW.001", 0.0, 100.0)
        fitting = dict(shaft("stub", "RW.099", 5.0, 99.5),
                       structure_type="stub", diameter_m=0.0,
                       stub={"alignment": "invert", "main_dn_mm": 300,
                             "branch_dn_mm": 150, "connection_invert_m": 99.5,
                             "station_enabled": False, "main_start_id": "",
                             "main_end_id": "", "main_pipe_ids": []})
        fitting = core.validate_shaft(fitting, allow_hidden=True)
        end = shaft("s2", "RW.002", 10.0, 99.0)
        options = connection_options()
        first_pipe = core.pipe_between_shafts(
            first, fitting, options, identity_factory=lambda: "p1")
        second_pipe = core.pipe_between_shafts(
            fitting, end, options, identity_factory=lambda: "p2")
        self.assertEqual(
            "H-RW.002",
            core.holding_name(first_pipe, (first, fitting, end),
                              (first_pipe, second_pipe)))

    def test_orients_height_changed_pipe_downhill_without_moving_endpoints(self):
        first = shaft("s1", "RW.001", 0.0, 100.0)
        second = shaft("s2", "RW.002", 10.0, 99.0)
        original = core.pipe_between_shafts(
            first, second, connection_options(), identity_factory=lambda: "pipe-1")
        changed = dict(original, start_invert_m=98.0, end_invert_m=99.0)
        self.assertTrue(core.pipe_flow_reversal_required(changed))
        oriented, reversed_flow = core.orient_pipe_downhill(changed)
        self.assertTrue(reversed_flow)
        self.assertEqual(("s2", "s1"), (oriented["start_id"], oriented["end_id"]))
        self.assertEqual((99.0, 98.0),
                         (oriented["start_invert_m"], oriented["end_invert_m"]))

    def test_pipe_edit_can_stage_reversal_before_confirmation(self):
        first = shaft("s1", "RW.001", 0.0, 100.0)
        second = shaft("s2", "RW.002", 10.0, 99.0)
        original = core.pipe_between_shafts(
            first, second, connection_options(), identity_factory=lambda: "pipe-1")
        candidate = core.update_pipe(
            original, 10.0,
            {"calculation_mode": "end", "start_invert_m": 98.0,
             "calculation_value": 99.0},
            allow_flow_reversal=True)
        self.assertTrue(core.pipe_flow_reversal_required(candidate))
        with self.assertRaisesRegex(core.SewerError, "Fließrichtung"):
            core.update_pipe(
                original, 10.0,
                {"calculation_mode": "end", "start_invert_m": 98.0,
                 "calculation_value": 99.0})

    def test_builds_one_downhill_pipe_without_new_shafts(self):
        lower = shaft("low", "RW.002", 10.0, 99.0)
        higher = shaft("high", "RW.001", 0.0, 100.0)
        pipe = core.pipe_between_shafts(
            lower, higher, connection_options(), identity_factory=lambda: "pipe-1")
        self.assertEqual(pipe["id"], "pipe-1")
        self.assertEqual(pipe["start_id"], "high")
        self.assertEqual(pipe["end_id"], "low")
        self.assertAlmostEqual(pipe["length_m"], 10.0)
        self.assertAlmostEqual(pipe["slope_percent"], 10.0)

    def test_rejects_existing_connection(self):
        first = shaft("s1", "RW.001", 0.0, 100.0)
        second = shaft("s2", "RW.002", 10.0, 99.0)
        existing = core.pipe_between_shafts(
            first, second, connection_options(), identity_factory=lambda: "existing")
        with self.assertRaisesRegex(core.SewerError, "bereits"):
            core.pipe_between_shafts(
                first, second, connection_options(), (existing,),
                identity_factory=lambda: "duplicate")

    def test_rejects_different_channel_kinds(self):
        first = shaft("s1", "RW.001", 0.0, 100.0)
        second = dict(shaft("s2", "RW.002", 10.0, 99.0), kind="SW")
        with self.assertRaisesRegex(core.SewerError, "unterschiedlicher Kanalart"):
            core.pipe_between_shafts(first, second, connection_options())


if __name__ == "__main__":
    unittest.main()
