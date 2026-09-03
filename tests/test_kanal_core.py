# -*- coding: utf-8 -*-
"""Focused regression tests for channel shaft labels and shaft connections."""
from __future__ import absolute_import

import unittest

from PD_KanalTool import core, settings


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
    def test_shaft_graphic_overrides_are_independently_validated(self):
        value = core.validate_shaft(dict(
            shaft("s1", "RW.001", 0.0, 100.0),
            pen_color_override=[100, 200, 300],
            fill_color_override=[400, 500, 600],
            fill_transparency_percent_override=35.0), allow_hidden=True)
        self.assertEqual([100, 200, 300], value["pen_color_override"])
        self.assertEqual([100, 200, 300], value["color_override"])
        self.assertEqual([400, 500, 600], value["fill_color_override"])
        self.assertEqual(35.0, value["fill_transparency_percent_override"])
        with self.assertRaises(core.SewerError):
            core.validate_shaft(dict(
                value, fill_transparency_percent_override=101.0),
                allow_hidden=True)

    def test_system_shaft_graphics_have_separate_validated_defaults(self):
        value = settings.validate({
            "shaft_pen_colors": {"RW": [1, 2, 3]},
            "shaft_fill_colors": {"RW": [4, 5, 6]},
            "shaft_fill_transparency_percent": {"RW": 25.0},
        })
        self.assertEqual([1, 2, 3], value["shaft_pen_colors"]["RW"])
        self.assertEqual([4, 5, 6], value["shaft_fill_colors"]["RW"])
        self.assertEqual(25.0, value["shaft_fill_transparency_percent"]["RW"])
        with self.assertRaises(core.SewerError):
            settings.validate({
                "shaft_fill_transparency_percent": {"RW": -1.0}})
        migrated = settings.validate({"colors": {"RW": [7, 8, 9]}})
        self.assertEqual([7, 8, 9], migrated["shaft_pen_colors"]["RW"])
        self.assertEqual([7, 8, 9], migrated["shaft_fill_colors"]["RW"])

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

    def test_shaft_label_lists_every_inlet_before_every_outlet(self):
        value = shaft("s1", "RW.001", 0.0, 100.0)
        # Geometric angle order can interleave inlet and outlet connections.
        endpoints = (
            {"tag": "Z1", "role": "in", "invert_m": 100.20,
             "dn_mm": 300, "material": "STB", "bearing_deg": 10.0},
            {"tag": "A1", "role": "out", "invert_m": 100.00,
             "dn_mm": 300, "material": "STB", "bearing_deg": 90.0},
            {"tag": "Z2", "role": "in", "invert_m": 100.10,
             "dn_mm": 250, "material": "PP", "bearing_deg": 180.0},
        )
        lines = core.shaft_label(value, endpoints, preferences()).splitlines()
        self.assertLess(
            lines.index("Z1 Zulauf | KS = 100,20 m"),
            lines.index("Z2 Zulauf | KS = 100,10 m"))
        self.assertLess(
            lines.index("Z2 Zulauf | KS = 100,10 m"),
            lines.index("Ablauf | KS = 100,00 m"))

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

    def test_zero_diameter_shaft_has_only_one_invert_row(self):
        value = core.validate_shaft(dict(
            shaft("s1", "RW.001", 0.0, 100.0), diameter_m=0.0),
            allow_hidden=True)
        label = core.shaft_label(
            value,
            ({"tag": "Z1", "role": "in", "invert_m": 100.2,
              "dn_mm": 300, "material": "STB", "bearing_deg": 10.0},
             {"tag": "A1", "role": "out", "invert_m": 100.0,
              "dn_mm": 300, "material": "STB", "bearing_deg": 190.0}),
            preferences())
        self.assertEqual(1, sum(line.startswith("KS =") for line in label.splitlines()))
        self.assertNotIn("Zulauf", label)
        self.assertNotIn("Ablauf", label)

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
    def test_component_and_annotation_classes_are_separate_by_type(self):
        first = shaft("s1", "RW.001", 0.0, 100.0)
        second = shaft("s2", "RW.002", 10.0, 99.0)
        value = core.pipe_between_shafts(
            first, second, connection_options(), identity_factory=lambda: "p1")
        self.assertEqual(
            "PD-KAN-RW-DN300-STB",
            core.pipe_class_name("PD-KAN", value))
        self.assertEqual(
            "PD-TX-Kanal-RW-DN300-STB-Haltung",
            core.pipe_label_class_name("PD-TX-Kanal", value))
        self.assertEqual(
            "PD-KAN-RW-Kanalstutzen",
            core.structure_class_name("PD-KAN", "RW", "stub"))
        self.assertEqual(
            "PD-TX-Kanal-RW-Kanalstutzen",
            core.structure_label_class_name(
                "PD-TX-Kanal", "RW", "stub"))
        self.assertEqual(
            "PD-KAN-RW-Schachtdeckel_3D",
            core.cover_class_name("PD-KAN", "RW", "_3D"))

    def test_stub_alignment_can_be_changed_without_changing_main_arms(self):
        first = shaft("s1", "RW.001", 0.0, 100.0)
        end = shaft("s2", "RW.002", 10.0, 99.0)
        branch_start = core.validate_shaft(dict(
            shaft("s3", "RW.003", 5.0, 100.0), y_m=5.0),
            allow_hidden=True)
        fitting = core.validate_shaft(dict(
            shaft("stub", "RW.099", 5.0, 99.5),
            diameter_m=0.0, structure_type="stub",
            stub={"alignment": "invert", "main_dn_mm": 300,
                  "branch_dn_mm": 150, "connection_invert_m": 99.5,
                  "station_enabled": False, "main_start_id": "",
                  "main_end_id": "", "main_pipe_ids": ["ma", "mb"]}),
            allow_hidden=True)
        main_a = core.pipe_between_shafts(
            first, fitting, connection_options(), identity_factory=lambda: "ma")
        main_b = core.pipe_between_shafts(
            fitting, end, connection_options(), identity_factory=lambda: "mb")
        branch_options = dict(
            connection_options(), dn_mm=150, outside_diameter_mm=150)
        branch = core.pipe_between_shafts(
            branch_start, fitting, branch_options,
            identity_factory=lambda: "branch")

        changed, changed_branch = core.change_stub_alignment(
            fitting, (main_a, main_b, branch), "crown")

        self.assertEqual("crown", changed["stub"]["alignment"])
        self.assertAlmostEqual(99.65, changed["stub"]["connection_invert_m"])
        self.assertAlmostEqual(99.65, changed_branch["end_invert_m"])
        self.assertEqual(main_a, core.validate_pipe(main_a))
        self.assertEqual(main_b, core.validate_pipe(main_b))

    def test_special_outline_rejects_self_intersection(self):
        with self.assertRaisesRegex(core.SewerError, "überschneiden"):
            core.special_outline(((0.0, 0.0), (4.0, 4.0),
                                  (0.0, 3.0), (3.0, 0.0)))

    def test_pipe_axis_uses_real_inner_radius(self):
        first = shaft("s1", "RW.001", 0.0, 100.0)
        second = shaft("s2", "RW.002", 10.0, 99.0)
        value = core.pipe_between_shafts(
            first, second, connection_options(), identity_factory=lambda: "p1")
        self.assertAlmostEqual(0.14, core.pipe_axis_offset_m(value))

    def test_split_can_reuse_active_owner_identity(self):
        first_shaft = shaft("s1", "RW.001", 0.0, 100.0)
        second_shaft = shaft("s2", "RW.002", 10.0, 99.0)
        original = core.pipe_between_shafts(
            first_shaft, second_shaft, connection_options(),
            identity_factory=lambda: "existing-pipe")
        first, second = core.split_pipe(
            original, "new-junction", 0.4,
            identity_factory=lambda: "new-second-pipe",
            preserve_first_identity=True)
        self.assertEqual("existing-pipe", first["id"])
        self.assertEqual("new-second-pipe", second["id"])
        self.assertEqual(("s1", "new-junction"),
                         (first["start_id"], first["end_id"]))
        self.assertEqual(("new-junction", "s2"),
                         (second["start_id"], second["end_id"]))
        self.assertAlmostEqual(original["length_m"],
                               first["length_m"] + second["length_m"])

    def test_network_rejects_duplicate_pipe_ids_and_mixed_endpoint_kind(self):
        first = shaft("s1", "RW.001", 0.0, 100.0)
        second = shaft("s2", "RW.002", 10.0, 99.0)
        value = core.pipe_between_shafts(
            first, second, connection_options(), identity_factory=lambda: "p1")
        with self.assertRaisesRegex(core.SewerError, "doppelt"):
            core.validate_network((value, dict(value)), (first, second))
        wrong = core.validate_shaft(dict(second, kind="SW"), allow_hidden=True)
        with self.assertRaisesRegex(core.SewerError, "Kanalart"):
            core.validate_network((value,), (first, wrong))
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
        self.assertTrue(core.pipe_label(value, shown).startswith("H-RW.002\n"))
        self.assertFalse(core.pipe_label(value, hidden).startswith("H-RW.002"))
        self.assertEqual(2, len(core.pipe_label(value, shown).splitlines()))
        self.assertEqual(1, len(core.pipe_label(value, hidden).splitlines()))

    def test_geometric_branch_segments_have_one_two_line_total_label(self):
        first = shaft("s1", "RW.001", 0.0, 100.0)
        second = shaft("s2", "RW.002", 10.0, 99.0)
        value = core.pipe_between_shafts(
            first, second, connection_options(), identity_factory=lambda: "p1")
        value.update(name="H-RW.002", label_layout="two_line", label_length_m=12.5,
                     label_rotation_deg=37.5)
        value = core.validate_pipe(value)
        shown = dict(preferences(), pipe_name_visible=True)
        self.assertEqual(3, len(core.pipe_label(value, shown).splitlines()))
        self.assertEqual("H-RW.002", core.pipe_label(value, shown).splitlines()[0])
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
