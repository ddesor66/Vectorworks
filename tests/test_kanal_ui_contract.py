# -*- coding: utf-8 -*-
"""Native-dialog contract tests using a strict, small Vectorworks API double."""
from __future__ import absolute_import

import importlib
import sys
import unittest


class DialogAPI(object):
    def __init__(self):
        self.next_dialog = 100
        self.controls = {}
        self.text = {}
        self.boolean = {}
        self.choices = {}
        self.choice_calls = []
        self.choice_selection = {}
        self.lb_rows = {}
        self.lb_selection = {}
        self.multi_select = {}
        self.tab_panes = {}
        self.group_first = {}
        self.colors = {}
        self.line_types = {}
        self.questions = []
        self.yn_result = True
        self.on_run = None

    def _dialog(self):
        self.next_dialog += 1
        self.controls[self.next_dialog] = {1, 2}
        return self.next_dialog

    def _control(self, dialog, item):
        if item in self.controls[dialog]:
            raise AssertionError("duplicate control %s" % item)
        self.controls[dialog].add(item)

    def _require(self, dialog, *items):
        if any(item not in self.controls.get(dialog, ()) for item in items):
            raise AssertionError("layout references a missing control")

    def CreateResizableLayout(self, *args):
        del args
        return self._dialog()

    def CreateEditText(self, dialog, item, value, width):
        del width
        self._control(dialog, item)
        self.text[(dialog, item)] = str(value)

    def CreateGroupBox(self, dialog, item, title, framed):
        del title, framed
        self._control(dialog, item)

    def CreateTabControl(self, dialog, item):
        self._control(dialog, item)
        self.tab_panes[(dialog, item)] = []

    def CreateTabPane(self, dialog, item, group):
        self._require(dialog, item, group)
        self.tab_panes[(dialog, item)].append(group)

    def CreateLB(self, dialog, item, width, height):
        del width, height
        self._control(dialog, item)
        self.lb_rows[(dialog, item)] = []
        self.lb_selection[(dialog, item)] = set()

    def __getattr__(self, name):
        if name.startswith("Create"):
            def create(dialog, item, *args):
                del args
                self._control(dialog, item)
            return create
        if name.startswith("Set") or name.startswith("Enable"):
            return lambda *args, **kwargs: None
        if name.startswith("Get"):
            return lambda *args, **kwargs: None
        return lambda *args, **kwargs: None

    def SetFirstLayoutItem(self, dialog, item):
        self._require(dialog, item)

    def SetFirstGroupItem(self, dialog, group, item):
        self._require(dialog, group, item)
        self.group_first[(dialog, group)] = item

    def SetBelowItem(self, dialog, first, second, *args):
        del args
        self._require(dialog, first, second)

    def SetRightItem(self, dialog, first, second, *args):
        del args
        self._require(dialog, first, second)

    def SetEdgeBinding(self, dialog, item, *args):
        del args
        self._require(dialog, item)

    def SetItemText(self, dialog, item, value):
        self._require(dialog, item)
        self.text[(dialog, item)] = str(value)

    def GetItemText(self, dialog, item):
        self._require(dialog, item)
        return self.text.get((dialog, item), "")

    def SetBooleanItem(self, dialog, item, value):
        self._require(dialog, item)
        self.boolean[(dialog, item)] = bool(value)

    def GetBooleanItem(self, dialog, item):
        self._require(dialog, item)
        return self.boolean.get((dialog, item), False)

    def AddChoice(self, dialog, item, value, index):
        self._require(dialog, item)
        self.choices.setdefault((dialog, item), {})[int(index)] = str(value)
        self.choice_calls.append((dialog, item, str(value), int(index)))

    def SelectChoice(self, dialog, item, index, selected):
        self._require(dialog, item)
        if selected:
            self.choice_selection[(dialog, item)] = int(index)

    def GetSelectedChoiceIndex(self, dialog, item, fallback=0):
        self._require(dialog, item)
        return self.choice_selection.get((dialog, item), fallback)

    def RGBToColorIndex(self, red, green, blue):
        return int(red), int(green), int(blue)

    def ColorIndexToRGB(self, value):
        return value

    def SetColorChoice(self, dialog, item, value):
        self._require(dialog, item)
        self.colors[(dialog, item)] = value

    def GetColorChoice(self, dialog, item):
        self._require(dialog, item)
        return self.colors[(dialog, item)]

    def SetLineTypeChoice(self, dialog, item, value):
        self._require(dialog, item)
        self.line_types[(dialog, item)] = int(value)

    def GetLineTypeChoice(self, dialog, item):
        self._require(dialog, item)
        return self.line_types[(dialog, item)]

    def InsertLBColumn(self, dialog, item, column, title, width):
        del column, title, width
        self._require(dialog, item)

    def InsertLBItem(self, dialog, item, row, value):
        self._require(dialog, item)
        values = self.lb_rows[(dialog, item)]
        values.insert(row, [str(value)])
        return row

    def SetLBItemInfo(self, dialog, item, row, column, value, image):
        del image
        values = self.lb_rows[(dialog, item)][row]
        while len(values) <= column:
            values.append("")
        values[column] = str(value)
        return True

    def DeleteAllLBItems(self, dialog, item):
        self.lb_rows[(dialog, item)] = []
        self.lb_selection[(dialog, item)] = set()

    def SetLBSelection(self, dialog, item, first, last, selected):
        values = self.lb_selection[(dialog, item)]
        for row in range(first, last + 1):
            if selected:
                values.add(row)
            else:
                values.discard(row)

    def IsLBItemSelected(self, dialog, item, row):
        return row in self.lb_selection[(dialog, item)]

    def EnableLBSingleLineSelection(self, dialog, item, single):
        self.multi_select[(dialog, item)] = not bool(single)

    def VerifyLayout(self, dialog):
        return dialog in self.controls

    def GetLayoutDialogSize(self, dialog):
        self._require(dialog, 1, 2)
        return None

    def GetScreen(self):
        return None

    def RunLayoutDialog(self, dialog, handler):
        handler(12255, 0)
        if self.on_run:
            return self.on_run(dialog, handler)
        return 2

    def YNDialog(self, message):
        self.questions.append(str(message))
        return self.yn_result


def load_ui(fake):
    sys.modules["vs"] = fake
    for name in tuple(sys.modules):
        if name == "PD_KanalTool" or name.startswith("PD_KanalTool."):
            sys.modules.pop(name, None)
    return importlib.import_module("PD_KanalTool.ui")


def shaft(identity, name, x_m, ks_m):
    return {
        "schema": 1, "id": identity, "kind": "RW", "name": name,
        "x_m": x_m, "y_m": 0.0, "kd_m": ks_m + 1.5, "ks_m": ks_m,
        "diameter_m": 1.0, "visible": True,
    }


def pipe(identity, start, end, start_m, end_m):
    return {
        "schema": 1, "id": identity, "network_id": "RW", "kind": "RW", "name": "",
        "start_id": start, "end_id": end, "dn_mm": 300, "material": "STB",
        "start_invert_m": start_m, "end_invert_m": end_m, "length_m": 10.0,
        "slope_percent": 1.0, "join_style": "round", "fillet_radius_m": 0.2,
        "flow_arrow_scale": 1.0, "label_layout": "one_line", "label_width_m": 0.0,
        "draw_3d": True, "graphics_mode": "double_line", "line_type": 1,
        "axis_line_type": 2, "color_override": None,
    }


class KanalDialogTests(unittest.TestCase):
    def test_preferences_use_three_compact_tabs_and_return_update_scope(self):
        api = DialogAPI()

        def accept(dialog, handler):
            self.assertEqual([101, 102, 103], api.tab_panes[(dialog, 100)])
            self.assertEqual({101, 102, 103}, {
                group for current_dialog, group in api.group_first
                if current_dialog == dialog})
            # Apply the saved settings to the connected system of the selection.
            api.choice_selection[(dialog, 50)] = 2
            return handler(1, 0)

        api.on_run = accept
        ui = load_ui(api)
        settings = importlib.import_module("PD_KanalTool.settings").validate({})
        updated, scope = ui.preferences_dialog(settings)
        self.assertEqual("systems", scope)
        self.assertEqual(10.0, updated["shaft_name_point_size"])
        self.assertEqual("bold", updated["shaft_name_text_style"])

    def test_preference_system_scope_follows_only_connected_component(self):
        api = DialogAPI()
        load_ui(api)
        live = importlib.import_module("PD_KanalTool.live")
        rows = (
            ("S1", {"role": "sewer_shaft", "shaft": shaft("s1", "RW.001", 0.0, 100.0)}),
            ("S2", {"role": "sewer_shaft", "shaft": shaft("s2", "RW.002", 10.0, 99.9)}),
            ("S3", {"role": "sewer_shaft", "shaft": shaft("s3", "RW.003", 20.0, 99.8)}),
            ("S4", {"role": "sewer_shaft", "shaft": shaft("s4", "RW.004", 100.0, 99.0)}),
            ("S5", {"role": "sewer_shaft", "shaft": shaft("s5", "RW.005", 110.0, 98.9)}),
            ("P1", {"role": "sewer_pipe", "pipe": pipe("p1", "s1", "s2", 100.0, 99.9)}),
            ("P2", {"role": "sewer_pipe", "pipe": pipe("p2", "s2", "s3", 99.9, 99.8)}),
            ("P3", {"role": "sewer_pipe", "pipe": pipe("p3", "s4", "s5", 99.0, 98.9)}),
        )
        live.objects = lambda role=None: tuple(
            row for row in rows if role is None or row[1]["role"] == role)
        targets = live._preference_targets((rows[5],), "systems")
        self.assertEqual({"S1", "S2", "S3", "P1", "P2"},
                         {handle for handle, _data in targets})

    def test_preference_update_preserves_engineering_pipe_values(self):
        api = DialogAPI()
        load_ui(api)
        live = importlib.import_module("PD_KanalTool.live")
        settings = importlib.import_module("PD_KanalTool.settings")
        preferences = settings.validate({
            "graphics_mode": "single_line",
            "single_line_type": 7,
            "axis_line_type": 9,
            "fillet_radius_m": 0.4,
            "flow_arrow_scale": 1.8,
        })
        original = pipe("p1", "s1", "s2", 100.0, 99.9)
        data = {"schema": 1, "role": "sewer_pipe", "pipe": original,
                "preferences": settings.validate({})}
        updated = live._data_with_preferences(data, preferences)
        for key in ("dn_mm", "material", "start_invert_m", "end_invert_m",
                    "start_id", "end_id"):
            self.assertEqual(original[key], updated["pipe"][key])
        self.assertEqual("single_line", updated["pipe"]["graphics_mode"])
        self.assertEqual(7, updated["pipe"]["line_type"])
        self.assertEqual(9, updated["pipe"]["axis_line_type"])
        self.assertEqual(0.4, updated["pipe"]["fillet_radius_m"])
        self.assertEqual(1.8, updated["pipe"]["flow_arrow_scale"])

    def test_home_contains_only_unique_creation_and_global_actions(self):
        api = DialogAPI()

        def accept(dialog, handler):
            choices = api.choices[(dialog, 13)]
            self.assertEqual(7, len(choices))
            self.assertEqual(len(choices), len(set(choices.values())))
            self.assertFalse(any("schacht" in title.lower() and "verbinden" in title.lower()
                                 for title in choices.values()))
            self.assertFalse(any("lösch" in title.lower() for title in choices.values()))
            # A repeated native INIT event must not append every choice again.
            handler(12255, 0)
            calls = [row for row in api.choice_calls
                     if row[0] == dialog and row[1] == 13]
            self.assertEqual(7, len(calls))
            api.choice_selection[(dialog, 13)] = 0
            return handler(1, 0)

        api.on_run = accept
        ui = load_ui(api)
        self.assertEqual("draw", ui.home_dialog(
            0, 2, selected_shaft_count=2, selected_pipe_count=0))

    def test_connection_uses_selected_shaft_then_graphically_picks_second(self):
        api = DialogAPI()
        load_ui(api)
        app = importlib.import_module("PD_KanalTool.app")
        prompts = []
        handles = app._connection_shaft_handles(
            (("S1", {"role": "sewer_shaft"}),),
            lambda prompt: prompts.append(prompt) or "S2")
        self.assertEqual(("S1", "S2"), handles)
        self.assertEqual(1, len(prompts))
        self.assertIn("ZWEITER SCHACHT", prompts[0])

    def test_connection_rejects_same_shaft_twice(self):
        api = DialogAPI()
        load_ui(api)
        app = importlib.import_module("PD_KanalTool.app")
        with self.assertRaisesRegex(Exception, "unterschiedliche Schächte"):
            app._connection_shaft_handles(
                (("S1", {"role": "sewer_shaft"}),), lambda _prompt: "S1")

    def test_compact_connection_dialog_returns_defaults(self):
        api = DialogAPI()
        api.on_run = lambda _dialog, handler: handler(1, 0)
        ui = load_ui(api)
        settings = importlib.import_module("PD_KanalTool.settings").validate({})
        result = ui.shaft_connection_dialog(
            shaft("s1", "RW.001", 0.0, 100.0),
            shaft("s2", "RW.002", 10.0, 99.0), settings)
        self.assertEqual(300, result["dn_mm"])
        self.assertEqual("STB", result["material"])
        self.assertEqual("double_line", result["graphics_mode"])
        self.assertEqual(10.0, result["wall_thickness_mm"])
        self.assertTrue(result["hollow_3d"])
        self.assertTrue(result["draw_3d"])

    def test_chain_accepts_two_holdings_and_applies_common_slope(self):
        api = DialogAPI()
        highlighted = []

        def accept(dialog, handler):
            self.assertTrue(api.multi_select[(dialog, 13)])
            # Three shafts precede the two holding rows.
            api.SetLBSelection(dialog, 13, 0, 4, False)
            api.SetLBSelection(dialog, 13, 3, 4, True)
            handler(13, 0)
            api.SetItemText(dialog, 19, "2,5")
            handler(22, 0)
            return handler(1, 0)

        api.on_run = accept
        ui = load_ui(api)
        result = ui.network_chain_dialog(
            (shaft("s1", "RW.001", 0.0, 100.0),
             shaft("s2", "RW.002", 10.0, 99.9),
             shaft("s3", "RW.003", 20.0, 99.8)),
            (pipe("p1", "s1", "s2", 100.0, 99.9),
             pipe("p2", "s2", "s3", 99.9, 99.8)),
            lambda rows: highlighted.append(rows))
        self.assertEqual([2.5, 2.5], [value["slope_percent"] for value in result[1]])
        self.assertIn((("pipe", "p1"), ("pipe", "p2")), highlighted)

    def test_chain_confirms_and_applies_height_induced_flow_reversal(self):
        api = DialogAPI()

        def accept(dialog, handler):
            api.SetLBSelection(dialog, 13, 0, 2, False)
            api.SetLBSelection(dialog, 13, 0, 0, True)
            handler(13, 0)
            api.SetItemText(dialog, 17, "98,0")
            handler(22, 0)
            return handler(1, 0)

        api.on_run = accept
        ui = load_ui(api)
        result = ui.network_chain_dialog(
            (shaft("s1", "RW.001", 0.0, 100.0),
             shaft("s2", "RW.002", 10.0, 99.0)),
            (pipe("p1", "s1", "s2", 100.0, 99.0),))
        updated = result[1][0]
        self.assertEqual(("s2", "s1"), (updated["start_id"], updated["end_id"]))
        self.assertEqual((99.0, 98.0),
                         (updated["start_invert_m"], updated["end_invert_m"]))
        self.assertEqual(1, len(api.questions))
        self.assertIn("Fließrichtung", api.questions[0])
        self.assertIn("RW.001 → RW.002 wird zu RW.002 → RW.001", api.questions[0])

    def test_chain_rejects_height_induced_flow_reversal_without_confirmation(self):
        api = DialogAPI()
        api.yn_result = False

        def decline(dialog, handler):
            api.SetLBSelection(dialog, 13, 0, 2, False)
            api.SetLBSelection(dialog, 13, 0, 0, True)
            handler(13, 0)
            api.SetItemText(dialog, 17, "98,0")
            handler(22, 0)
            return 2

        api.on_run = decline
        ui = load_ui(api)
        result = ui.network_chain_dialog(
            (shaft("s1", "RW.001", 0.0, 100.0),
             shaft("s2", "RW.002", 10.0, 99.0)),
            (pipe("p1", "s1", "s2", 100.0, 99.0),))
        self.assertIsNone(result)
        self.assertEqual(1, len(api.questions))


if __name__ == "__main__":
    unittest.main()
