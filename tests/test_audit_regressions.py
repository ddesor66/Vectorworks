# -*- coding: utf-8 -*-
"""Regression coverage for cross-module audit findings."""
from __future__ import absolute_import

import copy
import importlib
import json
import sys
import types
import unittest
from unittest import mock

sys.modules.setdefault("vs", types.ModuleType("vs"))

from PD_GefaelleTool import core as slope_core
from PD_KanalTool import shaft_sheet
from PD_LeitungsTool import core as utility_core
from PD_LeitungsTool import settings as utility_settings


class SlopeBoundaryTests(unittest.TestCase):
    def test_incomplete_point_is_a_controlled_domain_error(self):
        chain = slope_core.make_chain(
            ((0.0, 0.0), (1.0, 0.0)), 100.0, "slope", 1.0)
        chain["points"][1].pop("y_m")
        with self.assertRaises(slope_core.SlopeError):
            slope_core.validate_chain(chain)

    def test_curve_vertex_none_is_a_controlled_domain_error(self):
        adapter = importlib.import_module("PD_GefaelleTool.vw_adapter")
        api = types.SimpleNamespace(
            GetVertNum=lambda _handle: 2,
            GetPolylineVertex=lambda _handle, _index: None)
        with mock.patch.object(adapter, "vs", api):
            with self.assertRaisesRegex(slope_core.SlopeError, "nicht bereitgestellt"):
                adapter._curve_vertices(1, 1.0)

    def test_cancelled_graphical_height_pick_is_clean(self):
        adapter = importlib.import_module("PD_GefaelleTool.vw_adapter")
        called = []
        with mock.patch.object(adapter, "vs", types.SimpleNamespace(
                SetTempToolHelpStr=lambda _text: None,
                TrackObject=lambda _predicate: None)):
            self.assertIsNone(adapter.pick_height_object(called.append))
        self.assertEqual([], called)

    def test_enter_completes_native_slope_point_tool(self):
        point_tool = importlib.import_module("PD_GefaelleTool.point_tool")
        results = []
        api = types.SimpleNamespace(
            vstGetEventInfo=lambda: (point_tool.ACTION_GET_STATUS, 0, 0),
            vstNumPts=lambda: 2,
            vstGetCurrPt2D=lambda: (10.0, 0.0),
            KeyDown=lambda: (True, point_tool.KEY_RETURN),
            vstSetEventResult=results.append)
        state = dict(points=[(0.0, 0.0)], accepted=[1], native_count=1,
                     factor=1.0, done=False, callback=lambda _points: None,
                     help_text="", undo_name="Test", minimum_points=2)
        with mock.patch.object(point_tool, "vs", api):
            point_tool._session = state
            point_tool.run()
        self.assertTrue(state["done"])
        self.assertEqual(point_tool.TOOL_COMPLETED, results[-1])
        point_tool.cancel()

    def test_single_height_point_can_complete_with_enter(self):
        point_tool = importlib.import_module("PD_GefaelleTool.point_tool")
        results = []
        api = types.SimpleNamespace(
            vstGetEventInfo=lambda: (point_tool.ACTION_GET_STATUS, 0, 0),
            vstNumPts=lambda: 1,
            vstGetCurrPt2D=lambda: (2.0, 3.0),
            KeyDown=lambda: (True, point_tool.KEY_RETURN),
            vstSetEventResult=results.append)
        state = dict(points=[], accepted=[], native_count=0, factor=1.0,
                     done=False, callback=lambda _points: None, help_text="",
                     undo_name="Test", minimum_points=1)
        with mock.patch.object(point_tool, "vs", api):
            point_tool._session = state
            point_tool.run()
        self.assertTrue(state["done"])
        self.assertEqual(point_tool.TOOL_COMPLETED, results[-1])
        point_tool.cancel()


class ShaftSheetStressTests(unittest.TestCase):
    def _connections(self):
        return tuple({"connection_id": "c%02d" % index, "tag": "Z%d" % index,
                      "bearing_deg": 5.0 + index * 0.2,
                      "invert_m": 100.0 - index * 0.001}
                     for index in range(24))

    def test_twenty_four_connections_use_columns_and_stay_in_plan_frame(self):
        rows = shaft_sheet.plan_label_layout(
            self._connections(), center=(85.5, 84.0), shaft_radius_mm=17.0,
            left_x=28.0, right_x=143.0, min_gap_mm=7.0)
        self.assertEqual(24, len(rows))
        self.assertGreater(max(row["column"] for row in rows), 0)
        self.assertTrue(all(34.0 <= row["label"][1] <= 133.0 for row in rows))

    def test_twenty_four_connections_use_two_section_banks_in_bounds(self):
        rows = shaft_sheet.section_label_layout(
            self._connections(), top_mm=62.0, bottom_mm=116.0)
        self.assertEqual({"left", "right"}, {row["side"] for row in rows})
        self.assertTrue(all(62.0 <= row["baseline_mm"] <= 116.0 for row in rows))


class SewerGeometryTests(unittest.TestCase):
    def test_special_shaft_loft_reaches_a_real_circular_cover_ring(self):
        live = importlib.import_module("PD_KanalTool.live")
        center = (0.35, -0.10)
        faces = live._special_loft_faces(
            ((-2.0, -1.0), (2.0, -1.0), (1.0, 1.5), (-1.5, 1.0)),
            center, 0.3125, 99.4, 100.0)
        top = faces[1]
        self.assertGreaterEqual(len(top), 24)
        self.assertTrue(all(abs(((point[0] - center[0]) ** 2 +
                                 (point[1] - center[1]) ** 2) ** 0.5 - 0.3125) < 1e-9
                            for point in top))
        self.assertTrue(all(point[2] == 100.0 for point in top))

    def test_zero_diameter_connection_is_capped(self):
        live = importlib.import_module("PD_KanalTool.live")
        trim, width, capped = live._connection_profile(
            {"diameter_m": 0.0, "structure_type": "round"}, {}, 0.3, 1.0)
        self.assertEqual((0.0, 0.3, True), (trim, width, capped))


class SewerResetRegressionTests(unittest.TestCase):
    def setUp(self):
        self.live = importlib.import_module("PD_KanalTool.live")
        self.live._RENDER_RESULTS.clear()
        self.live._PENDING_RENDER_CHECKS.clear()

    def tearDown(self):
        self.live._RENDER_RESULTS.clear()
        self.live._PENDING_RENDER_CHECKS.clear()

    def test_reset_event_does_not_write_a_render_marker_into_the_pio(self):
        data = {"schema": self.live.core.SCHEMA, "role": "sewer_pipe"}

        class Store(object):
            PLUGIN = "PD KAN Objekt"

            def data_of(self, _handle):
                return data

            def write_data(self, _handle, _value):
                raise AssertionError("reset must not SetRField a render marker")

        api = types.SimpleNamespace(
            GetCustomObjectInfo=lambda: (True, Store.PLUGIN, "P1", None, None),
            GetName=lambda _handle: "PD-KAN-Rohr-p1",
            SetParameterVisibility=lambda *_args: None,
            EnableParameter=lambda *_args: None,
            TextOrigin=lambda *_args: None,
            CreateText=lambda *_args: None)
        with mock.patch.object(self.live, "vs", api), mock.patch.object(
                self.live, "_live", return_value=Store()), mock.patch.object(
                self.live, "_repair_duplicate", return_value=data), mock.patch.object(
                self.live, "draw_pipe", return_value=None):
            self.live.reset()

    def test_checked_reset_surfaces_synchronous_failure_without_record_write(self):
        api = types.SimpleNamespace(GetName=lambda _handle: "PD-KAN-Rohr-p1")

        def reset(handle):
            self.live._record_render_result(handle, self.live.RENDER_ERROR, "Testfehler")

        api.ResetObject = reset
        with mock.patch.object(self.live, "vs", api):
            with self.assertRaisesRegex(self.live.core.SewerError, "Testfehler"):
                self.live._reset_checked("P1")

    def test_deferred_oip_reset_is_not_mistaken_for_a_render_failure(self):
        api = types.SimpleNamespace(
            GetName=lambda _handle: "PD-KAN-Schacht-s1",
            ResetObject=lambda _handle: None)
        with mock.patch.object(self.live, "vs", api):
            self.assertFalse(self.live._reset_checked("S1"))
        self.assertFalse(self.live._PENDING_RENDER_CHECKS)


class SewerAsyncQuantityTests(unittest.TestCase):
    def test_native_completion_marks_report_dirty_without_synchronous_rebuild(self):
        app = importlib.import_module("PD_KanalTool.app")
        reporting = importlib.import_module("PD_KanalLeitungMengen.reporting")
        events = []
        callback = app._with_quantity_refresh(
            lambda value: events.append(("geometry", value)) or "created")
        with mock.patch.object(
                reporting, "begin_changes", side_effect=lambda: events.append("begin")), mock.patch.object(
                reporting, "end_changes",
                side_effect=lambda refresh=False, mark_dirty=False:
                events.append(("end", refresh, mark_dirty))):
            self.assertEqual("created", callback("branch"))
        self.assertEqual(
            ["begin", ("geometry", "branch"), ("end", False, True)], events)


class SewerCloneTests(unittest.TestCase):
    def test_copied_pipe_retargets_both_copied_shafts(self):
        live = importlib.import_module("PD_KanalTool.live")
        core = importlib.import_module("PD_KanalTool.core")
        shaft1 = {"id": "s1", "name": "RW.001", "kind": "RW", "visible": True,
                  "x_m": 0.0, "y_m": 0.0,
                  "connection_station": {"main_start_id": "s1", "main_end_id": "s2",
                                         "main_pipe_ids": ["p1"],
                                         "station_pipe_ids": ["p1"],
                                         "station_zero_id": "s2",
                                         "station_zero_name": "RW.002"}}
        shaft2 = {"id": "s2", "name": "RW.002", "kind": "RW", "visible": True,
                  "x_m": 10.0, "y_m": 0.0}
        pipe = {"id": "p1", "start_id": "s1", "end_id": "s2"}
        store = {
            "OS1": {"role": "sewer_shaft", "shaft": copy.deepcopy(shaft1)},
            "OS2": {"role": "sewer_shaft", "shaft": copy.deepcopy(shaft2)},
            "OP": {"role": "sewer_pipe", "pipe": copy.deepcopy(pipe)},
            "CS1": {"role": "sewer_shaft", "shaft": copy.deepcopy(shaft1)},
            "CS2": {"role": "sewer_shaft", "shaft": copy.deepcopy(shaft2)},
            "CP": {"role": "sewer_pipe", "pipe": copy.deepcopy(pipe)},
        }
        names = {
            "OS1": core.SHAFT_PREFIX + "s1", "OS2": core.SHAFT_PREFIX + "s2",
            "OP": core.PIPE_PREFIX + "p1", "CS1": "Kopie Schacht 1",
            "CS2": "Kopie Schacht 2", "CP": "Kopie Haltung",
        }
        locations = {"OS1": (0.0, 0.0), "OS2": (10.0, 0.0), "OP": (0.0, 0.0),
                     "CS1": (20.0, 5.0), "CS2": (30.0, 5.0), "CP": (20.0, 5.0)}

        class Store(object):
            PLUGIN = "PD KAN Objekt"

            def data_of(self, handle):
                return store.get(handle)

            def write_data(self, handle, data):
                store[handle] = data

        api = types.SimpleNamespace(
            GetName=lambda handle: names.get(handle, ""),
            SetName=lambda handle, value: names.__setitem__(handle, value),
            GetObject=lambda value: next(
                (handle for handle, name in names.items() if name == value), None),
            ResetObject=lambda _handle: None)
        object_rows = lambda role=None: tuple(
            (handle, data) for handle, data in store.items()
            if role is None or data.get("role") == role)
        with mock.patch.object(live, "vs", api), mock.patch.object(
                live, "_live", return_value=Store()), mock.patch.object(
                live, "objects", side_effect=object_rows), mock.patch.object(
                live.adapter, "units_to_meters", return_value=1.0), mock.patch.object(
                live.adapter, "symbol_location_2d",
                side_effect=lambda handle, _fallback: locations[handle]), mock.patch.object(
                live, "ensure_label", return_value=None):
            changed = live._repair_duplicate("CP", store["CP"])
        cloned_pipe = changed["pipe"]
        self.assertNotEqual("p1", cloned_pipe["id"])
        self.assertEqual(store["CS1"]["shaft"]["id"], cloned_pipe["start_id"])
        self.assertEqual(store["CS2"]["shaft"]["id"], cloned_pipe["end_id"])
        self.assertNotIn(cloned_pipe["start_id"], ("s1", "s2"))
        self.assertNotIn(cloned_pipe["end_id"], ("s1", "s2"))
        cloned_station = store["CS1"]["shaft"]["connection_station"]
        self.assertEqual(cloned_pipe["id"], cloned_station["main_pipe_ids"][0])
        self.assertEqual(cloned_pipe["end_id"], cloned_station["station_zero_id"])
        self.assertEqual(store["CS2"]["shaft"]["name"],
                         cloned_station["station_zero_name"])


class UtilityCoreTests(unittest.TestCase):
    def _options(self):
        value = copy.deepcopy(utility_settings.DEFAULTS)
        utility_type = value["default_type"]
        dn = value["default_dn_mm"]
        value.update(
            utility_type=utility_type, route_name="Test", description="",
            material=value["default_material"], dns_mm=[dn],
            outside_diameters_mm=[dn], outside_diameters_explicit=False,
            line_color=value["colors"][utility_type])
        for key in ("colors", "types", "materials", "dns", "class_prefix",
                    "axis_class", "fitting_class", "text_class"):
            value.pop(key, None)
        return value

    def test_unconfirmed_outside_diameter_stays_unconfirmed(self):
        outside, explicit = utility_core.outside_diameters(
            "114,3", (100,), 1, explicit=False)
        self.assertEqual((100.0,), outside)
        self.assertFalse(explicit)

    def test_height_chain_is_authoritative_for_stored_slope(self):
        route = utility_core.new_route(((0.0, 0.0), (10.0, 0.0)), self._options(),
                                       identity_factory=lambda: "r1")
        route["route_heights_m"] = ((100.0, 95.0),)
        route["heights_m"] = (100.0, 95.0)
        route["slope_percent"] = 2.0
        normalized = utility_core.validate_route(route)
        self.assertEqual(50.0, normalized["slope_percent"])

    def test_custom_type_and_label_styles_are_persistent(self):
        preferences = utility_settings.validate(dict(
            utility_settings.DEFAULTS,
            types=list(utility_core.UTILITY_TYPES) + ["Telekommunikation"]))
        self.assertIn("Telekommunikation", preferences["types"])
        options = self._options()
        options.update(utility_type="Telekommunikation", line_color=[0, 0, 0],
                       label_bold=True, label_underline=True,
                       label_rotation_deg=35.0, label_layout="two_line")
        route = utility_core.new_route(((0.0, 0.0), (10.0, 0.0)), options,
                                       identity_factory=lambda: "r2")
        self.assertTrue(route["label_bold"])
        self.assertTrue(route["label_underline"])
        self.assertEqual(35.0, route["label_rotation_deg"])
        self.assertEqual("two_line", route["label_layout"])

    def test_continuous_3d_tube_has_only_two_end_caps(self):
        live = importlib.import_module("PD_LeitungsTool.live")
        faces = live._tube_path_faces(
            ((0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (1.0, 1.0, 0.1)),
            0.1, segments=12)
        self.assertEqual(2 + 2 * 12, len(faces))
        self.assertEqual(12, len(faces[0]))
        self.assertEqual(12, len(faces[1]))

    def test_route_standards_preserve_engineering_data(self):
        live = importlib.import_module("PD_LeitungsTool.live")
        preferences = utility_settings.validate({
            "graphics_mode": "double_line", "regular_label": True,
            "label_text": "NEU", "font_size_pt": 12.0,
            "colors": dict(utility_settings.DEFAULT_COLORS,
                           Trinkwasser=[11, 22, 33]),
        })
        route = utility_core.new_route(
            ((0.0, 0.0), (10.0, 0.0)), self._options(),
            identity_factory=lambda: "standards")
        updated = live._route_with_preferences(route, preferences)
        self.assertEqual(route["id"], updated["id"])
        self.assertEqual(route["points_m"], updated["points_m"])
        self.assertEqual(route["dns_mm"], updated["dns_mm"])
        self.assertEqual(route["material"], updated["material"])
        self.assertEqual(route["route_heights_m"], updated["route_heights_m"])
        self.assertEqual("double_line", updated["graphics_mode"])
        self.assertEqual("NEU", updated["label_text"])
        self.assertEqual((11, 22, 33), updated["line_color"])

    def test_complete_route_options_become_saved_defaults(self):
        app = importlib.import_module("PD_LeitungsTool.app")
        preferences = utility_settings.validate({})
        options = app._options(preferences)
        options.update(
            graphics_mode="double_line", draw_3d=False,
            label_layout="two_line", font_size_pt=13.0,
            line_color=[100, 200, 300])
        updated = app._preferences_from_options(preferences, options)
        self.assertEqual("double_line", updated["graphics_mode"])
        self.assertFalse(updated["draw_3d"])
        self.assertEqual("two_line", updated["label_layout"])
        self.assertEqual(13.0, updated["font_size_pt"])
        self.assertEqual([100, 200, 300],
                         updated["colors"][updated["default_type"]])

    def test_multi_route_update_resets_once_and_redraws_once(self):
        live = importlib.import_module("PD_LeitungsTool.live")
        preferences = utility_settings.validate({})
        first = utility_core.new_route(
            ((0.0, 0.0), (5.0, 0.0)), self._options(),
            identity_factory=lambda: "first")
        second = utility_core.new_route(
            ((0.0, 1.0), (5.0, 1.0)), self._options(),
            identity_factory=lambda: "second")
        store = {
            "A": {"schema": utility_core.SCHEMA, "role": "utility_route",
                  "route": first, "preferences": preferences},
            "B": {"schema": utility_core.SCHEMA, "role": "utility_route",
                  "route": second, "preferences": preferences},
        }

        class Store(object):
            def data_of(self, handle):
                return store.get(handle)

            def write_data(self, handle, data):
                store[handle] = copy.deepcopy(data)

        resets = []
        redraws = []

        def reset(handle):
            resets.append(handle)
            store[handle]["render_status"] = {"state": live.RENDER_OK, "message": ""}

        api = types.SimpleNamespace(
            NameUndoEvent=lambda _name: None, ResetObject=reset,
            ReDrawAll=lambda: redraws.append(True))
        changed_first = dict(first, label_text="A")
        changed_second = dict(second, label_text="B")
        with mock.patch.object(live, "vs", api), mock.patch.object(
                live, "_objects", return_value=Store()):
            count = live.update_many(
                (("A", changed_first), ("B", changed_second)), preferences)
        self.assertEqual(2, count)
        self.assertEqual(["A", "B"], resets)
        self.assertEqual([True], redraws)
        self.assertEqual("A", store["A"]["route"]["label_text"])
        self.assertEqual("B", store["B"]["route"]["label_text"])


class UtilityPersistenceTests(unittest.TestCase):
    def test_valid_json_list_is_reported_as_domain_error(self):
        module = importlib.import_module("PD_LeitungsTool.live_objects")
        api = types.SimpleNamespace(
            GetTypeN=lambda _handle: 86,
            GetParametricRecord=lambda _handle: 1,
            GetName=lambda _handle: module.PLUGIN,
            GetRField=lambda _handle, _plugin, _field: json.dumps([]))
        with mock.patch.object(module, "vs", api):
            with self.assertRaisesRegex(utility_core.UtilityError, "Objekt erwartet"):
                module.data_of(1)


if __name__ == "__main__":
    unittest.main()
