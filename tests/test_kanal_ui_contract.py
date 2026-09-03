# -*- coding: utf-8 -*-
"""Native-dialog contract tests using a strict, small Vectorworks API double."""
from __future__ import absolute_import

import importlib
import sys
import unittest
from unittest import mock


class DialogAPI(object):
    def __init__(self):
        self.next_dialog = 100
        self.controls = {}
        self.text = {}
        self.edit_widths = {}
        self.boolean = {}
        self.choices = {}
        self.choice_calls = []
        self.choice_selection = {}
        self.lb_rows = {}
        self.lb_selection = {}
        self.multi_select = {}
        self.tab_panes = {}
        self.group_first = {}
        self.below_items = []
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
        self._control(dialog, item)
        self.text[(dialog, item)] = str(value)
        self.edit_widths[(dialog, item)] = int(width)

    def CreateEditTextBox(self, dialog, item, value, width, height):
        del height
        self._control(dialog, item)
        self.text[(dialog, item)] = str(value)
        self.edit_widths[(dialog, item)] = int(width)

    def CreateStaticText(self, dialog, item, value, width):
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
        self.below_items.append((dialog, first, second))

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


def load_ui(fake, package="PD_KanalTool"):
    sys.modules["vs"] = fake
    for name in tuple(sys.modules):
        if name == package or name.startswith(package + "."):
            sys.modules.pop(name, None)
    return importlib.import_module(package + ".ui")


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
    def test_related_tool_dialog_helpers_stay_inside_small_screen(self):
        api = DialogAPI()
        sizes = {}
        positions = {}
        api.GetScreen = lambda: (0, 0, 800, 500)
        api.SetLayoutDialogSize = lambda dialog, width, height: sizes.update(
            {dialog: (int(width), int(height))})
        api.GetLayoutDialogSize = lambda dialog: sizes.get(dialog, (1200, 900))
        api.SetLayoutDialogPosition = lambda dialog, x, y: positions.update(
            {dialog: (int(x), int(y))})
        for package, helper_name in (
                ("PD_KanalTool", "_right_side_position"),
                ("PD_LeitungsTool", "_right_side_position"),
                ("PD_GefaelleTool", "_right_side_position"),
                ("PD_KanalLeitungTool", "_fit_dialog"),
                ("PD_KanalLeitungMengen", "_fit_dialog")):
            sys.modules["vs"] = api
            for name in tuple(sys.modules):
                if name == package or name.startswith(package + "."):
                    sys.modules.pop(name, None)
            module = importlib.import_module(package + ".ui")
            dialog = api.CreateResizableLayout("Test", True, "OK", "Abbrechen")
            getattr(module, helper_name)(dialog, (1200, 900))
            width, height = sizes[dialog]
            x, y = positions[dialog]
            self.assertLessEqual(width, 776, package)
            self.assertLessEqual(height, 452, package)
            self.assertGreaterEqual(x, 12, package)
            self.assertGreaterEqual(y, 12, package)
            self.assertLessEqual(x + width, 788, package)
            self.assertLessEqual(y + height, 488, package)

    def test_rigole_dialog_preserves_multiline_note_and_fits_screen(self):
        api = DialogAPI()
        api.on_run = lambda _dialog, handler: handler(1, 0)
        sizes = {}
        api.GetScreen = lambda: (0, 0, 1366, 768)
        api.SetLayoutDialogSize = lambda dialog, width, height: sizes.update(
            {dialog: (int(width), int(height))})
        api.GetLayoutDialogSize = lambda dialog: sizes.get(dialog, (900, 900))
        api.SetLayoutDialogPosition = lambda *_args: None
        ui = load_ui(api)
        initial = {
            "schema": 1, "id": "rig-1", "name": "RIG.001",
            "x_m": 0.0, "y_m": 0.0, "length_m": 10.0, "width_m": 3.0,
            "height_m": 1.0, "bottom_m": 99.0, "terrain_top_m": 101.0,
            "rotation_deg": 15.0, "slope_angle_deg": 60.0,
            "fill_color": [36000, 52000, 65535],
            "pen_color": [0, 20000, 50000], "transparency_percent": 40.0,
            "note": "Zeile 1\nZeile 2", "connections": [],
        }
        result = ui.rigole_dialog(initial)
        self.assertEqual("Zeile 1\nZeile 2", result["note"])
        self.assertEqual(52, api.edit_widths[(api.next_dialog, 30)])
        self.assertLessEqual(sizes[api.next_dialog][1], 720)

    def test_unchanged_shaft_dialog_preserves_distinct_connection_heights(self):
        api = DialogAPI()
        api.on_run = lambda _dialog, handler: handler(1, 0)
        ui = load_ui(api)
        core = importlib.import_module("PD_KanalTool.core")
        settings = importlib.import_module("PD_KanalTool.settings").validate({})
        current = core.validate_shaft(
            shaft("s1", "RW.001", 0.0, 100.0), allow_hidden=True)
        choice = ui.shaft_dialog(current, settings, (100.2, 100.1), (100.0,))
        self.assertFalse(choice["inlet_changed"])
        self.assertFalse(choice["outlet_changed"])

    def test_shaft_dialog_edits_z2_without_changing_z1(self):
        api = DialogAPI()

        def accept(dialog, handler):
            self.assertIn("Z1", api.text[(dialog, 100)])
            self.assertIn("H-RW.002", api.text[(dialog, 100)])
            self.assertIn("ΔA +20,0 cm", api.text[(dialog, 100)])
            self.assertIn("Z2", api.text[(dialog, 102)])
            self.assertIn("H-RW.003", api.text[(dialog, 102)])
            self.assertIn("ΔA +10,0 cm", api.text[(dialog, 102)])
            api.SetItemText(dialog, 103, "99,95")
            handler(103, 0)
            self.assertIn("ΔA -5,0 cm", api.text[(dialog, 102)])
            api.SetItemText(dialog, 35, "99,90")
            handler(35, 0)
            self.assertIn("ΔA +30,0 cm", api.text[(dialog, 100)])
            self.assertIn("ΔA +5,0 cm", api.text[(dialog, 102)])
            api.SetItemText(dialog, 35, "100,0")
            handler(35, 0)
            return handler(1, 0)

        api.on_run = accept
        ui = load_ui(api)
        core = importlib.import_module("PD_KanalTool.core")
        settings = importlib.import_module("PD_KanalTool.settings").validate({})
        current = core.validate_shaft(
            shaft("s1", "RW.001", 0.0, 100.0), allow_hidden=True)
        choice = ui.shaft_dialog(current, settings, (
            {"pipe_id": "p1", "tag": "Z1", "pipe_name": "H-RW.002",
             "invert_m": 100.20},
            {"pipe_id": "p2", "tag": "Z2", "pipe_name": "H-RW.003",
             "invert_m": 100.10},
        ), (100.0,))
        self.assertEqual(100.20, choice["inlet_inverts_m"]["p1"])
        self.assertEqual(99.95, choice["inlet_inverts_m"]["p2"])
        self.assertFalse(choice["inlet_changed_by_pipe"]["p1"])
        self.assertTrue(choice["inlet_changed_by_pipe"]["p2"])
        self.assertEqual(99.95, choice["shaft"]["ks_m"])

    def test_shaft_edit_changes_only_the_selected_inlet_pipe(self):
        api = DialogAPI()
        load_ui(api)
        live = importlib.import_module("PD_KanalTool.live")
        core = importlib.import_module("PD_KanalTool.core")
        preferences = importlib.import_module("PD_KanalTool.settings").validate({})
        current = core.validate_shaft(
            shaft("s3", "RW.003", 20.0, 100.0), allow_hidden=True)
        pipes = (
            ("P1", core.validate_pipe(pipe("p1", "s1", "s3", 100.4, 100.2))),
            ("P2", core.validate_pipe(pipe("p2", "s2", "s3", 100.3, 100.1))),
            ("P3", core.validate_pipe(pipe("p3", "s3", "s4", 100.0, 99.9))),
        )

        class Store(object):
            @staticmethod
            def data_of(_handle):
                return {"schema": core.SCHEMA, "role": "sewer_shaft", "shaft": current}

        choice = {
            "shaft": core.validate_shaft(dict(current, ks_m=99.95), allow_hidden=True),
            "inlet_invert_m": 99.95,
            "inlet_inverts_m": {"p1": 100.2, "p2": 99.95},
            "inlet_changed": True,
            "outlet_invert_m": 100.0,
            "outlet_changed": False,
        }
        commits = []
        with mock.patch.object(live, "_live", return_value=Store()), mock.patch.object(
                live, "read_shaft", return_value=dict(current)), mock.patch.object(
                live, "_connected_pipes", return_value=pipes), mock.patch.object(
                live, "_shaft_inlet_dialog_rows", return_value=(
                    {"pipe_id": "p1", "tag": "Z1", "invert_m": 100.2},
                    {"pipe_id": "p2", "tag": "Z2", "invert_m": 100.1},
                )), mock.patch.object(
                live.sewer_ui, "shaft_dialog", return_value=choice), mock.patch.object(
                live, "_unique_shaft_name", return_value=None), mock.patch.object(
                live, "_confirmed_pipe_directions", side_effect=lambda values: values), mock.patch.object(
                live, "_commit_network_updates",
                side_effect=lambda pipe_updates, shaft_updates, current_preferences, undo: commits.append(
                    (pipe_updates, shaft_updates, current_preferences, undo))):
            self.assertTrue(live.edit("S3", preferences))
        self.assertEqual({"P2"}, set(commits[0][0]))
        self.assertEqual(100.2, commits[0][0].get("P1", pipes[0][1])["end_invert_m"])
        self.assertEqual(99.95, commits[0][0]["P2"]["end_invert_m"])

    def test_shaft_dialog_preserves_note_and_uses_compact_text_fields(self):
        api = DialogAPI()
        api.on_run = lambda _dialog, handler: handler(1, 0)
        ui = load_ui(api)
        core = importlib.import_module("PD_KanalTool.core")
        current = core.validate_shaft(dict(
            shaft("s1", "RW.001", 0.0, 100.0), note="RW33"),
            allow_hidden=True)
        choice = ui.shaft_dialog(
            current,
            importlib.import_module("PD_KanalTool.settings").validate({}),
            (100.0,), (100.0,))
        self.assertEqual("RW33", choice["shaft"]["note"])
        dialog = api.next_dialog
        self.assertEqual(24, api.edit_widths[(dialog, 33)])
        self.assertEqual(24, api.edit_widths[(dialog, 43)])

    def test_shaft_dialog_with_many_inlets_fits_small_screen(self):
        api = DialogAPI()
        api.on_run = lambda _dialog, handler: handler(1, 0)
        sizes = {}
        positions = {}
        api.GetScreen = lambda: (0, 0, 1024, 600)
        api.SetLayoutDialogSize = lambda dialog, width, height: sizes.update(
            {dialog: (int(width), int(height))})
        api.GetLayoutDialogSize = lambda dialog: sizes.get(dialog, (900, 900))
        api.SetLayoutDialogPosition = lambda dialog, x, y: positions.update(
            {dialog: (int(x), int(y))})
        ui = load_ui(api)
        core = importlib.import_module("PD_KanalTool.core")
        current = core.validate_shaft(
            shaft("s1", "RW.001", 0.0, 100.0), allow_hidden=True)
        self.assertIsNotNone(ui.shaft_dialog(
            current,
            importlib.import_module("PD_KanalTool.settings").validate({}),
            tuple(
                {"pipe_id": "p%d" % index, "tag": "Z%d" % index,
                 "pipe_name": "H-RW.%03d" % (index + 1),
                 "invert_m": 100.0 - index / 100.0}
                for index in range(1, 21)),
            (99.7,)))
        dialog = api.next_dialog
        width, height = sizes[dialog]
        x, y = positions[dialog]
        self.assertEqual([51, 52, 53, 54], api.tab_panes[(dialog, 50)])
        self.assertEqual(
            20, sum((dialog, item) in api.edit_widths
                    for item in range(101, 140, 2)))
        self.assertTrue(all(item not in api.controls[dialog] for item in (46, 47, 48, 49)))
        self.assertIn((dialog, 133, 34), api.below_items)
        self.assertLessEqual(width, 1000)
        self.assertLessEqual(height, 552)
        self.assertGreaterEqual(x, 12)
        self.assertGreaterEqual(y, 12)
        self.assertLessEqual(y + height, 588)

    def test_preferences_use_compact_tabs_and_return_update_scope(self):
        api = DialogAPI()

        def accept(dialog, handler):
            self.assertEqual([101, 105, 102, 104, 103], api.tab_panes[(dialog, 100)])
            self.assertEqual({101, 102, 103, 104, 105}, {
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
        self.assertTrue(updated["pipe_name_visible"])
        self.assertEqual(9.0, updated["pipe_name_point_size"])
        self.assertEqual(9.0, updated["connection_point_size"])
        self.assertTrue(updated["shaft_connection_labels_visible"])
        self.assertEqual([0, 26000, 65535], updated["shaft_pen_colors"]["RW"])
        self.assertEqual([0, 26000, 65535], updated["shaft_fill_colors"]["RW"])
        self.assertEqual(50.0, updated["shaft_fill_transparency_percent"]["RW"])

    def test_preferences_can_hide_independent_shaft_connection_labels(self):
        api = DialogAPI()

        def accept(dialog, handler):
            api.boolean[(dialog, 74)] = False
            return handler(1, 0)

        api.on_run = accept
        ui = load_ui(api)
        preferences = importlib.import_module("PD_KanalTool.settings").validate({})
        updated, _scope = ui.preferences_dialog(preferences)
        self.assertFalse(updated["shaft_connection_labels_visible"])
        live = importlib.import_module("PD_KanalTool.live")
        self.assertIsNone(live._connection_label_context(
            None, {"role": "sewer_shaft", "preferences": updated}, "P1:end"))

    def test_all_tool_height_fields_show_exactly_two_decimals(self):
        api = DialogAPI()
        sewer_ui = load_ui(api)
        sewer_settings = importlib.import_module("PD_KanalTool.settings").validate(
            {"height_decimals": 6})
        self.assertEqual(2, sewer_settings["height_decimals"])
        sewer_ui.shaft_dialog(
            shaft("s1", "RW.001", 0.0, 99.734), sewer_settings,
            ({"pipe_id": "p1", "tag": "Z1", "pipe_name": "H-RW.001",
              "invert_m": 99.876},), (99.734,))
        dialog = api.next_dialog
        self.assertEqual("101,23", api.text[(dialog, 16)])
        self.assertEqual("99,88", api.text[(dialog, 101)])
        self.assertEqual("99,73", api.text[(dialog, 35)])

        api = DialogAPI()
        utility_ui = load_ui(api, "PD_LeitungsTool")
        utility_settings = importlib.import_module("PD_LeitungsTool.settings").validate(
            {"start_height_m": 100.126})
        utility_ui.route_dialog(utility_settings)
        self.assertEqual("100,13", api.text[(api.next_dialog, 43)])

        api = DialogAPI()
        slope_ui = load_ui(api, "PD_GefaelleTool")
        slope_settings = importlib.import_module("PD_GefaelleTool.settings").validate(
            {"height_decimals": 6})
        self.assertEqual(2, slope_settings["height_decimals"])
        slope_ui.single_point_dialog(1, "Standard", default_height=98.766)
        self.assertEqual("98,77", api.text[(api.next_dialog, 12)])
        labels = importlib.import_module("PD_GefaelleTool.label_format")
        self.assertEqual("H=98,77m", labels.annotation(
            "height", 98.766, {"height_decimals": 6}))

    def test_shaft_dialog_can_override_contour_fill_and_transparency(self):
        api = DialogAPI()

        def accept(dialog, handler):
            api.boolean[(dialog, 21)] = True
            api.colors[(dialog, 22)] = (100, 200, 300)
            api.boolean[(dialog, 55)] = True
            api.colors[(dialog, 56)] = (400, 500, 600)
            api.text[(dialog, 58)] = "35"
            return handler(1, 0)

        api.on_run = accept
        ui = load_ui(api)
        settings = importlib.import_module("PD_KanalTool.settings").validate({})
        current = importlib.import_module("PD_KanalTool.core").validate_shaft(
            shaft("s1", "RW.001", 0.0, 100.0), allow_hidden=True)
        choice = ui.shaft_dialog(current, settings, (), ())
        self.assertEqual([100, 200, 300], choice["shaft"]["pen_color_override"])
        self.assertEqual([100, 200, 300], choice["shaft"]["color_override"])
        self.assertEqual([400, 500, 600], choice["shaft"]["fill_color_override"])
        self.assertEqual(
            35.0, choice["shaft"]["fill_transparency_percent_override"])

    def test_preferences_apply_single_line_to_existing_drawing_by_default(self):
        api = DialogAPI()

        def accept(dialog, handler):
            # The user changes only the drawing mode.  With existing channel
            # objects, the caller-selected drawing scope must already be
            # active; no second, easily missed scope choice is required.
            self.assertEqual(3, api.choice_selection[(dialog, 50)])
            api.choice_selection[(dialog, 40)] = 1
            return handler(1, 0)

        api.on_run = accept
        ui = load_ui(api)
        settings = importlib.import_module("PD_KanalTool.settings").validate({})
        updated, scope = ui.preferences_dialog(settings, "drawing")
        self.assertEqual("single_line", updated["graphics_mode"])
        self.assertEqual("drawing", scope)

    def test_settings_default_scope_prefers_selection_then_drawing(self):
        api = DialogAPI()
        load_ui(api)
        app = importlib.import_module("PD_KanalTool.app")
        self.assertEqual("selection", app._preference_default_scope((("P1", {}),), True))
        self.assertEqual(
            "systems",
            app._preference_default_scope((("S1", {"role": "sewer_shaft"}),), True))
        self.assertEqual("drawing", app._preference_default_scope((), True))
        self.assertEqual("save", app._preference_default_scope((), False))

    def test_multiple_selected_shafts_use_complete_shaft_editing(self):
        api = DialogAPI()
        load_ui(api)
        app = importlib.import_module("PD_KanalTool.app")
        preferences = importlib.import_module("PD_KanalTool.settings").validate({})
        managed = (
            ("S1", {"role": "sewer_shaft"}),
            ("S2", {"role": "sewer_shaft"}),
        )
        calls = []
        app.sewer_live.edit_shafts = lambda handles, current: (
            calls.append((tuple(handles), current)) or True)
        app.adapter.alert = lambda _message: None
        app._edit(preferences, managed)
        self.assertEqual(("S1", "S2"), calls[0][0])

    def test_multiple_shaft_dialogs_stage_properties_and_pipe_ends_once(self):
        api = DialogAPI()
        load_ui(api)
        live = importlib.import_module("PD_KanalTool.live")
        core = importlib.import_module("PD_KanalTool.core")
        preferences = importlib.import_module("PD_KanalTool.settings").validate({})
        shafts = {
            "S1": core.validate_shaft(shaft("s1", "RW.001", 0.0, 100.0), allow_hidden=True),
            "S2": core.validate_shaft(shaft("s2", "RW.002", 10.0, 99.9), allow_hidden=True),
        }
        pipes = {"P1": core.validate_pipe(pipe("p1", "s1", "s2", 100.0, 99.9))}

        class Store(object):
            @staticmethod
            def data_of(handle):
                return {"schema": 1, "role": "sewer_shaft", "shaft": shafts[handle]}

        live._live = lambda: Store()
        live.read_shaft = lambda handle, data=None: dict(shafts[handle])
        live.shaft_records = lambda: tuple(shafts.items())
        live.pipe_records = lambda: tuple(pipes.items())
        choices = iter((
            {"shaft": core.validate_shaft(dict(shafts["S1"], diameter_m=1.2), allow_hidden=True),
             "inlet_invert_m": 100.0, "outlet_invert_m": 100.0},
            {"shaft": core.validate_shaft(dict(shafts["S2"], construction_material="PP",
                                                wall_thickness_m=0.0), allow_hidden=True),
             "inlet_invert_m": 99.8, "outlet_invert_m": 99.9},
        ))
        live.sewer_ui.shaft_dialog = lambda *_args: next(choices)
        live._confirmed_pipe_directions = lambda values: values
        commits = []
        live._commit_network_updates = lambda pipe_updates, shaft_updates, current, undo: (
            commits.append((pipe_updates, shaft_updates, current, undo)))

        self.assertTrue(live.edit_shafts(("S1", "S2"), preferences))
        self.assertEqual(1, len(commits))
        self.assertEqual(100.0, commits[0][0]["P1"]["start_invert_m"])
        self.assertEqual(99.8, commits[0][0]["P1"]["end_invert_m"])
        self.assertEqual(1.2, commits[0][1]["S1"]["diameter_m"])
        self.assertEqual("PP", commits[0][1]["S2"]["construction_material"])

    def test_drop_updates_incoming_holding_and_stores_one_valid_drop(self):
        api = DialogAPI()
        load_ui(api)
        live = importlib.import_module("PD_KanalTool.live")
        core = importlib.import_module("PD_KanalTool.core")
        preferences = importlib.import_module("PD_KanalTool.settings").validate({})
        current_shaft = core.validate_shaft(
            shaft("s2", "RW.002", 10.0, 99.0), allow_hidden=True)
        current_pipe = core.validate_pipe(pipe("p1", "s1", "s2", 100.0, 99.5))

        class Store(object):
            @staticmethod
            def data_of(_handle):
                return {"schema": 1, "role": "sewer_shaft", "shaft": current_shaft}

        live._live = lambda: Store()
        live.read_shaft = lambda *_args: dict(current_shaft)
        live._connected_pipes = lambda _identity: (("P1", current_pipe),)
        commits = []
        live._commit_network_updates = lambda pipes, shafts, current, undo: (
            commits.append((pipes, shafts, current, undo)))
        live.set_drop(
            "S2", {"pipe_id": "p1", "upper_invert_m": 99.4,
                   "lower_invert_m": 99.0}, preferences)
        self.assertEqual(99.4, commits[0][0]["P1"]["end_invert_m"])
        self.assertEqual("p1", commits[0][1]["S2"]["drops"][0]["pipe_id"])
        with self.assertRaisesRegex(core.SewerError, "eindeutig über"):
            live.set_drop(
                "S2", {"pipe_id": "p1", "upper_invert_m": 99.0,
                       "lower_invert_m": 99.0}, preferences)

    def test_stub_and_drop_build_continuous_three_arm_3d_geometry(self):
        api = DialogAPI()
        load_ui(api)
        live = importlib.import_module("PD_KanalTool.live")
        core = importlib.import_module("PD_KanalTool.core")
        preferences = importlib.import_module("PD_KanalTool.settings").validate({})
        main_a = core.validate_pipe(pipe("ma", "s1", "stub", 100.0, 99.5))
        main_b = core.validate_pipe(pipe("mb", "stub", "s2", 99.5, 99.0))
        branch = core.validate_pipe(dict(
            pipe("br", "s3", "stub", 99.8, 99.5), dn_mm=150,
            outside_diameter_mm=150))
        rows = (
            {"pipe": main_a, "direction": (-1.0, 0.0), "length_m": 5.0},
            {"pipe": main_b, "direction": (1.0, 0.0), "length_m": 5.0},
            {"pipe": branch, "direction": (0.0, 1.0), "length_m": 3.0},
        )
        current_shaft = core.validate_shaft(dict(
            shaft("stub", "RW.099", 5.0, 99.5), diameter_m=0.0,
            structure_type="stub",
            stub={"alignment": "invert", "main_dn_mm": 300,
                  "branch_dn_mm": 150, "connection_invert_m": 99.5,
                  "station_enabled": False, "main_start_id": "",
                  "main_end_id": "", "main_pipe_ids": ["ma", "mb"]}),
            allow_hidden=True)
        live._junction_rows = lambda _shaft: rows
        live._layer_z_m = lambda _handle: 0.0
        live._connection_profile = lambda *_args: (0.2, 0.3, False)
        live.color_for = lambda *_args: (0, 0, 65535)
        live.ensure_pipe_classes = lambda *_args: None
        live.class_name = lambda value, _prefs, suffix="": value["id"] + suffix
        meshes = []
        live._draw_pipe_3d = lambda *args, **kwargs: meshes.append((args, kwargs))
        live._draw_stub_3d(
            "STUB", current_shaft,
            {"role": "sewer_shaft", "shaft": current_shaft,
             "preferences": preferences}, 1.0)
        self.assertEqual(3, len(meshes))
        self.assertEqual({meshes[0][0][0], meshes[1][0][0], meshes[2][0][0]},
                         {meshes[0][0][0]})
        branch_2d = core.validate_pipe(dict(branch, draw_3d=False))
        live._junction_rows = lambda _shaft: (rows[0], rows[1], dict(
            rows[2], pipe=branch_2d))
        meshes[:] = []
        live._draw_stub_3d(
            "STUB", current_shaft,
            {"role": "sewer_shaft", "shaft": current_shaft,
             "preferences": preferences}, 1.0)
        self.assertEqual(2, len(meshes))

        live._connected_pipes = lambda _identity: (("P1", main_a),)
        live._handle_by_id = lambda _prefix, _identity: "OTHER"
        live.read_shaft = lambda *_args: core.validate_shaft(
            shaft("s1", "RW.001", 0.0, 100.0), allow_hidden=True)
        live._draw_open_polyline = lambda *_args, **_kwargs: None
        live._set_graphics = lambda *_args, **_kwargs: None
        meshes[:] = []
        drop_shaft = core.validate_shaft(dict(
            shaft("stub", "RW.002", 5.0, 99.0),
            drops=[{"pipe_id": "ma", "upper_invert_m": 99.5,
                    "lower_invert_m": 99.0}]), allow_hidden=True)
        live._draw_drops(
            "S2", drop_shaft, preferences, "SHAFT", (0, 0, 65535), 1.0)
        self.assertEqual(3, len(meshes))

    def test_dynamic_labels_cross_hidden_bends_but_stop_at_real_shafts(self):
        api = DialogAPI()
        load_ui(api)
        live = importlib.import_module("PD_KanalTool.live")
        core = importlib.import_module("PD_KanalTool.core")
        shafts = {
            "s1": core.validate_shaft(shaft("s1", "RW.001", 0.0, 100.0), allow_hidden=True),
            "j": core.validate_shaft(dict(
                shaft("j", "", 4.0, 99.6), visible=False, diameter_m=0.0,
                structure_type="junction"), allow_hidden=True),
            "s2": core.validate_shaft(shaft("s2", "RW.002", 10.0, 99.0), allow_hidden=True),
        }
        p1 = core.validate_pipe(dict(pipe("p1", "s1", "j", 100.0, 99.6), length_m=4.0))
        p2 = core.validate_pipe(dict(pipe("p2", "j", "s2", 99.6, 99.0), length_m=6.0))
        pipe_data = (("P1", {"pipe": p1}), ("P2", {"pipe": p2}))
        shaft_data = tuple((identity, {"shaft": value}) for identity, value in shafts.items())
        live.objects = lambda role=None: pipe_data if role == "sewer_pipe" else shaft_data
        live._handle_by_id = lambda _prefix, identity: identity
        live.read_shaft = lambda handle, _data=None: dict(shafts[handle])
        self.assertTrue(live._holding_label_pipe(p1)["label_suppressed"])
        labelled = live._holding_label_pipe(p2)
        self.assertFalse(labelled["label_suppressed"])
        self.assertAlmostEqual(10.0, labelled["label_length_m"])

        shafts["j"] = core.validate_shaft(dict(
            shafts["j"], name="RW.010", visible=True, diameter_m=1.0,
            structure_type="round"), allow_hidden=True)
        self.assertFalse(live._holding_label_pipe(p1)["label_suppressed"])
        self.assertAlmostEqual(4.0, live._holding_label_pipe(p1)["label_length_m"])
        self.assertFalse(live._holding_label_pipe(p2)["label_suppressed"])
        self.assertAlmostEqual(6.0, live._holding_label_pipe(p2)["label_length_m"])

    def test_repeated_split_retargets_existing_stub_main_reference(self):
        api = DialogAPI()
        load_ui(api)
        live = importlib.import_module("PD_KanalTool.live")
        core = importlib.import_module("PD_KanalTool.core")
        existing_stub = core.validate_shaft(dict(
            shaft("stub", "RW.099", 10.0, 99.0), diameter_m=0.0,
            structure_type="stub",
            stub={"alignment": "invert", "main_dn_mm": 300,
                  "branch_dn_mm": 150, "connection_invert_m": 99.0,
                  "station_enabled": False, "main_start_id": "",
                  "main_end_id": "", "main_pipe_ids": ["old", "next"]}),
            allow_hidden=True)
        original = core.validate_pipe(pipe("old", "s1", "stub", 100.0, 99.0))
        first, second = core.split_pipe(
            original, "new", 0.5, identity_factory=iter(("a", "b")).__next__)
        live.shaft_records = lambda: (("STUB", existing_stub),)
        updated = live._stub_reference_updates(original, first, second)
        self.assertEqual(["b", "next"], updated["STUB"]["stub"]["main_pipe_ids"])

    def test_repeated_split_retargets_normal_connection_station(self):
        api = DialogAPI()
        load_ui(api)
        live = importlib.import_module("PD_KanalTool.live")
        core = importlib.import_module("PD_KanalTool.core")
        connection = core.validate_shaft(dict(
            shaft("connection", "RW.010", 10.0, 99.0),
            connection_station={
                "station_enabled": True,
                "main_start_id": "s1", "main_end_id": "s2",
                "main_pipe_ids": ["old", "next"],
                "station_m": 10.0, "station_zero_id": "s2",
                "station_zero_name": "RW.002",
                "station_equal_inverts": False,
                "station_basis": "lower_invert",
            }), allow_hidden=True)
        original = core.validate_pipe(pipe("old", "s1", "connection", 100.0, 99.0))
        first, second = core.split_pipe(
            original, "new", 0.5, identity_factory=iter(("a", "b")).__next__)
        live.shaft_records = lambda: (("CONNECTION", connection),)
        updated = live._stub_reference_updates(original, first, second)
        self.assertEqual(
            ["b", "next"],
            updated["CONNECTION"]["connection_station"]["main_pipe_ids"])
        self.assertEqual(
            ["a", "b", "next"],
            updated["CONNECTION"]["connection_station"]["station_pipe_ids"])

    def test_normal_holding_connection_station_refreshes_from_lower_shaft(self):
        api = DialogAPI()
        load_ui(api)
        live = importlib.import_module("PD_KanalTool.live")
        core = importlib.import_module("PD_KanalTool.core")
        shafts = {
            "s1": core.validate_shaft(shaft("s1", "RW.001", 0.0, 100.0), allow_hidden=True),
            "s2": core.validate_shaft(shaft("s2", "RW.002", 10.0, 99.0), allow_hidden=True),
        }
        connection = core.validate_shaft(dict(
            shaft("connection", "RW.010", 4.0, 99.6),
            connection_station={
                "station_enabled": True,
                "main_start_id": "s1", "main_end_id": "s2",
                "main_pipe_ids": ["p1", "p2"],
                "station_m": None, "station_zero_id": "",
                "station_zero_name": "",
                "station_equal_inverts": False, "station_basis": "",
            }), allow_hidden=True)
        pipes = {
            "p1": core.validate_pipe(dict(
                pipe("p1", "s1", "connection", 100.0, 99.6), length_m=4.0)),
            "p2": core.validate_pipe(dict(
                pipe("p2", "connection", "s2", 99.6, 99.0), length_m=6.0)),
        }
        all_shafts = dict(shafts, connection=connection)
        live.objects = lambda role=None: (
            tuple((identity, {"pipe": value}) for identity, value in pipes.items())
            if role == "sewer_pipe" else
            tuple((identity, {"shaft": value}) for identity, value in all_shafts.items()))
        live._handle_by_id = lambda prefix, identity: identity
        live.read_shaft = lambda handle, data=None: all_shafts[handle]
        live.read_pipe = lambda handle, data=None: pipes[handle]
        refreshed = live._refresh_stub_stationing(connection)
        station = refreshed["connection_station"]
        self.assertAlmostEqual(6.0, station["station_m"])
        self.assertEqual("s2", station["station_zero_id"])
        self.assertEqual("RW.002", station["station_zero_name"])

    def test_connection_station_uses_complete_bent_holding_axis(self):
        api = DialogAPI()
        load_ui(api)
        live = importlib.import_module("PD_KanalTool.live")
        core = importlib.import_module("PD_KanalTool.core")
        shafts = {
            "s1": core.validate_shaft(shaft("s1", "RW.001", 0.0, 100.0), allow_hidden=True),
            "j1": core.validate_shaft(dict(
                shaft("j1", "", 2.0, 99.8), y_m=3.0, visible=False,
                diameter_m=0.0, structure_type="junction"), allow_hidden=True),
            "j2": core.validate_shaft(dict(
                shaft("j2", "", 8.0, 99.3), y_m=3.0, visible=False,
                diameter_m=0.0, structure_type="junction"), allow_hidden=True),
            "s2": core.validate_shaft(shaft("s2", "RW.002", 10.0, 99.0), allow_hidden=True),
        }
        connection = core.validate_shaft(dict(
            shaft("connection", "RW.010", 4.0, 99.6), y_m=3.0,
            connection_station={
                "station_enabled": True,
                "main_start_id": "s1", "main_end_id": "s2",
                "main_pipe_ids": ["p2", "p3"],
                "station_m": None, "station_zero_id": "",
                "station_zero_name": "", "station_equal_inverts": False,
                "station_basis": "",
            }), allow_hidden=True)
        pipes = {
            "p1": core.validate_pipe(dict(
                pipe("p1", "s1", "j1", 100.0, 99.8), length_m=3.6055512755)),
            "p2": core.validate_pipe(dict(
                pipe("p2", "j1", "connection", 99.8, 99.6), length_m=2.0)),
            "p3": core.validate_pipe(dict(
                pipe("p3", "connection", "j2", 99.6, 99.3), length_m=4.0)),
            "p4": core.validate_pipe(dict(
                pipe("p4", "j2", "s2", 99.3, 99.0), length_m=3.6055512755)),
        }
        all_shafts = dict(shafts, connection=connection)
        live.objects = lambda role=None: (
            tuple((identity, {"pipe": value}) for identity, value in pipes.items())
            if role == "sewer_pipe" else
            tuple((identity, {"shaft": value}) for identity, value in all_shafts.items()))
        live._handle_by_id = lambda prefix, identity: identity
        live.read_shaft = lambda handle, data=None: all_shafts[handle]
        live.read_pipe = lambda handle, data=None: pipes[handle]
        refreshed = live._refresh_stub_stationing(connection)
        self.assertAlmostEqual(
            4.0 + 3.6055512755,
            refreshed["connection_station"]["station_m"], places=8)

    def test_visible_inserted_shaft_becomes_new_station_boundary(self):
        api = DialogAPI()
        load_ui(api)
        live = importlib.import_module("PD_KanalTool.live")
        core = importlib.import_module("PD_KanalTool.core")
        shafts = {
            "s1": core.validate_shaft(shaft("s1", "RW.001", 0.0, 100.0), allow_hidden=True),
            "new": core.validate_shaft(shaft("new", "RW.010", 8.0, 99.2), allow_hidden=True),
            "s2": core.validate_shaft(shaft("s2", "RW.002", 10.0, 99.0), allow_hidden=True),
        }
        connection = core.validate_shaft(dict(
            shaft("connection", "RW.099", 4.0, 99.6), diameter_m=0.0,
            structure_type="stub",
            stub={
                "alignment": "invert", "main_dn_mm": 300,
                "branch_dn_mm": 150, "connection_invert_m": 99.6,
                "station_enabled": True,
                "main_start_id": "s1", "main_end_id": "s2",
                "main_pipe_ids": ["p1", "p2"],
                "station_pipe_ids": ["p1", "p2", "p3"],
                "station_m": 6.0, "station_zero_id": "s2",
                "station_zero_name": "RW.002",
                "station_equal_inverts": False,
                "station_basis": "lower_invert",
            }), allow_hidden=True)
        pipes = {
            "p1": core.validate_pipe(dict(
                pipe("p1", "s1", "connection", 100.0, 99.6), length_m=4.0)),
            "p2": core.validate_pipe(dict(
                pipe("p2", "connection", "new", 99.6, 99.2), length_m=4.0)),
            "p3": core.validate_pipe(dict(
                pipe("p3", "new", "s2", 99.2, 99.0), length_m=2.0)),
        }
        all_shafts = dict(shafts, connection=connection)
        live.objects = lambda role=None: (
            tuple((identity, {"pipe": value}) for identity, value in pipes.items())
            if role == "sewer_pipe" else
            tuple((identity, {"shaft": value}) for identity, value in all_shafts.items()))
        live._handle_by_id = lambda prefix, identity: identity
        live.read_shaft = lambda handle, data=None: all_shafts[handle]
        live.read_pipe = lambda handle, data=None: pipes[handle]
        refreshed = live._refresh_stub_stationing(connection)
        station = refreshed["stub"]
        self.assertEqual("new", station["station_zero_id"])
        self.assertEqual("RW.010", station["station_zero_name"])
        self.assertEqual({"p1", "p2"}, set(station["station_pipe_ids"]))
        self.assertAlmostEqual(4.0, station["station_m"])

    def test_house_or_floor_branch_has_one_label_across_all_hidden_bends(self):
        api = DialogAPI()
        load_ui(api)
        live = importlib.import_module("PD_KanalTool.live")
        core = importlib.import_module("PD_KanalTool.core")
        shafts = {
            "stub": core.validate_shaft(dict(
                shaft("stub", "RW.099", 0.0, 99.0), diameter_m=0.0,
                structure_type="stub",
                stub={"alignment": "invert", "main_dn_mm": 300,
                      "branch_dn_mm": 150, "connection_invert_m": 99.0,
                      "station_enabled": False, "main_start_id": "",
                      "main_end_id": "", "main_pipe_ids": []}), allow_hidden=True),
            "j1": core.validate_shaft(dict(
                shaft("j1", "", 3.0, 99.1), visible=False, diameter_m=0.0,
                structure_type="junction"), allow_hidden=True),
            "j2": core.validate_shaft(dict(
                shaft("j2", "", 7.0, 99.2), visible=False, diameter_m=0.0,
                structure_type="junction"), allow_hidden=True),
            "house": core.validate_shaft(dict(
                shaft("house", "HA.001", 12.0, 99.3), diameter_m=0.0,
                structure_type="house"), allow_hidden=True),
        }
        pipes = (
            core.validate_pipe(dict(
                pipe("b1", "house", "j2", 99.3, 99.2), length_m=5.0,
                label_layout="two_line")),
            core.validate_pipe(dict(
                pipe("b2", "j2", "j1", 99.2, 99.1), length_m=4.0,
                label_layout="two_line")),
            core.validate_pipe(dict(
                pipe("b3", "j1", "stub", 99.1, 99.0), length_m=3.0,
                label_layout="two_line")),
        )
        live.objects = lambda role=None: (
            tuple((value["id"], {"pipe": value}) for value in pipes)
            if role == "sewer_pipe" else
            tuple((identity, {"shaft": value}) for identity, value in shafts.items()))
        live._handle_by_id = lambda _prefix, identity: identity
        live.read_shaft = lambda handle, _data=None: shafts[handle]
        labelled = [live._holding_label_pipe(value) for value in pipes]
        shown = [value for value in labelled if not value["label_suppressed"]]
        self.assertEqual(1, len(shown))
        self.assertAlmostEqual(12.0, shown[0]["label_length_m"])
        self.assertEqual("two_line", shown[0]["label_layout"])

    def test_moved_axis_node_invalidates_complete_label_and_remote_station(self):
        api = DialogAPI()
        load_ui(api)
        live = importlib.import_module("PD_KanalTool.live")
        core = importlib.import_module("PD_KanalTool.core")
        shafts = {
            "s1": core.validate_shaft(shaft("s1", "RW.001", 0.0, 100.0), allow_hidden=True),
            "j": core.validate_shaft(dict(
                shaft("j", "", 3.0, 99.7), visible=False, diameter_m=0.0,
                structure_type="junction"), allow_hidden=True),
            "c": core.validate_shaft(dict(
                shaft("c", "RW.099", 7.0, 99.3), diameter_m=0.0,
                structure_type="stub",
                stub={"alignment": "invert", "main_dn_mm": 300,
                      "branch_dn_mm": 150, "connection_invert_m": 99.3,
                      "station_enabled": True, "main_start_id": "s1",
                      "main_end_id": "s2", "main_pipe_ids": ["p2", "p3"],
                      "station_pipe_ids": ["p1", "p2", "p3"],
                      "station_m": 3.0, "station_zero_id": "s2",
                      "station_zero_name": "RW.002",
                      "station_equal_inverts": False,
                      "station_basis": "lower_invert"}), allow_hidden=True),
            "s2": core.validate_shaft(shaft("s2", "RW.002", 10.0, 99.0), allow_hidden=True),
        }
        pipes = {
            "p1": core.validate_pipe(dict(
                pipe("p1", "s1", "j", 100.0, 99.7), length_m=3.0)),
            "p2": core.validate_pipe(dict(
                pipe("p2", "j", "c", 99.7, 99.3), length_m=4.0)),
            "p3": core.validate_pipe(dict(
                pipe("p3", "c", "s2", 99.3, 99.0), length_m=3.0)),
        }
        pipe_data = tuple((identity, {"role": "sewer_pipe", "pipe": value})
                          for identity, value in pipes.items())
        shaft_data = tuple((identity.upper(), {"role": "sewer_shaft", "shaft": value})
                           for identity, value in shafts.items())
        live.objects = lambda role=None: (
            pipe_data if role == "sewer_pipe" else shaft_data)
        live.shaft_records = lambda: tuple(
            (handle, data["shaft"]) for handle, data in shaft_data)
        live.read_shaft = lambda handle, data=None: shafts[handle.lower()]
        reset_labels = []
        reset_objects = []
        live._reset_labels = lambda data: reset_labels.append(data["pipe"]["id"])
        api.ResetObject = lambda handle: reset_objects.append(handle)
        live._reset_holding_dependents((pipes["p1"],), "J")
        self.assertEqual({"p1", "p2", "p3"}, set(reset_labels))
        self.assertIn("C", reset_objects)

    def test_remote_height_update_invalidates_dependent_station(self):
        api = DialogAPI()
        load_ui(api)
        live = importlib.import_module("PD_KanalTool.live")
        core = importlib.import_module("PD_KanalTool.core")
        shafts = {
            "s1": core.validate_shaft(
                shaft("s1", "RW.001", 0.0, 100.0), allow_hidden=True),
            "j": core.validate_shaft(dict(
                shaft("j", "", 3.0, 99.7), visible=False,
                diameter_m=0.0, structure_type="junction"), allow_hidden=True),
            "c": core.validate_shaft(dict(
                shaft("c", "RW.099", 7.0, 99.3), diameter_m=0.0,
                structure_type="stub",
                stub={"alignment": "invert", "main_dn_mm": 300,
                      "branch_dn_mm": 150, "connection_invert_m": 99.3,
                      "station_enabled": True, "main_start_id": "s1",
                      "main_end_id": "s2", "main_pipe_ids": ["p2", "p3"],
                      "station_pipe_ids": ["p1", "p2", "p3"],
                      "station_m": 3.0, "station_zero_id": "s2",
                      "station_zero_name": "RW.002",
                      "station_equal_inverts": False,
                      "station_basis": "lower_invert"}), allow_hidden=True),
            "s2": core.validate_shaft(
                shaft("s2", "RW.002", 10.0, 99.0), allow_hidden=True),
        }
        pipes = {
            "p1": core.validate_pipe(dict(
                pipe("p1", "s1", "j", 100.0, 99.7), length_m=3.0)),
            "p2": core.validate_pipe(dict(
                pipe("p2", "j", "c", 99.7, 99.3), length_m=4.0)),
            "p3": core.validate_pipe(dict(
                pipe("p3", "c", "s2", 99.3, 99.0), length_m=3.0)),
        }
        store = {}
        for identity, value in pipes.items():
            store[identity.upper()] = {"role": "sewer_pipe", "pipe": value}
        for identity, value in shafts.items():
            store[identity.upper()] = {"role": "sewer_shaft", "shaft": value}

        class Store(object):
            def data_of(self, handle):
                return store.get(handle)

            def write_data(self, handle, data):
                store[handle] = data

        live._live = lambda: Store()
        live.objects = lambda role=None: tuple(
            (handle, data) for handle, data in store.items()
            if data.get("role") == role)
        live.pipe_records = lambda: tuple(
            (handle, data["pipe"]) for handle, data in store.items()
            if data.get("role") == "sewer_pipe")
        live.shaft_records = lambda: tuple(
            (handle, data["shaft"]) for handle, data in store.items()
            if data.get("role") == "sewer_shaft")
        live._handle_by_id = lambda _prefix, identity: identity.upper()
        # Keep this contract test focused on reset propagation; validation and
        # flow reversal are covered by the network-update tests below.
        live._prepare_network_updates = lambda pipe_updates, shaft_updates: (
            pipe_updates, shaft_updates)
        resets = []
        def reset(handle):
            resets.append(handle)
            store[handle]["render_status"] = "ok"
            store[handle]["render_error"] = ""
        api.ResetObject = reset
        api.ReDrawAll = lambda: None
        api.NameUndoEvent = lambda _name: None
        changed = dict(pipes["p1"], start_invert_m=100.1)
        live._commit_network_updates(
            {"P1": changed}, {}, {"channel_type": "RW"},
            "PD Test Höhenänderung")
        self.assertIn("C", resets)

    def test_network_update_keeps_drop_attached_and_lower_soil(self):
        api = DialogAPI()
        load_ui(api)
        live = importlib.import_module("PD_KanalTool.live")
        core = importlib.import_module("PD_KanalTool.core")
        first = core.validate_shaft(shaft("s1", "RW.001", 0.0, 100.0), allow_hidden=True)
        second = core.validate_shaft(dict(
            shaft("s2", "RW.002", 10.0, 99.0),
            drops=[{"pipe_id": "p1", "upper_invert_m": 99.5,
                    "lower_invert_m": 99.0}]), allow_hidden=True)
        current_pipe = core.validate_pipe(pipe("p1", "s1", "s2", 100.0, 99.5))
        live.pipe_records = lambda: (("P1", current_pipe),)
        live.shaft_records = lambda: (("S1", first), ("S2", second))
        pipes, shafts = live._prepare_network_updates(
            {"P1": core.validate_pipe(dict(current_pipe, end_invert_m=99.4))}, {})
        self.assertEqual(99.4, pipes["P1"]["end_invert_m"])
        self.assertEqual(99.4, shafts["S2"]["drops"][0]["upper_invert_m"])
        self.assertEqual(99.0, shafts["S2"]["ks_m"])

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
            self.assertEqual(8, len(choices))
            self.assertEqual(len(choices), len(set(choices.values())))
            self.assertFalse(any("schacht" in title.lower() and "verbinden" in title.lower()
                                 for title in choices.values()))
            self.assertFalse(any("lösch" in title.lower() for title in choices.values()))
            # A repeated native INIT event must not append every choice again.
            handler(12255, 0)
            calls = [row for row in api.choice_calls
                     if row[0] == dialog and row[1] == 13]
            self.assertEqual(8, len(calls))
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

    def test_pipe_dialog_exposes_persistent_label_rotation(self):
        api = DialogAPI()
        api.on_run = lambda _dialog, handler: handler(1, 0)
        ui = load_ui(api)
        settings = importlib.import_module("PD_KanalTool.settings").validate({
            "label_rotation_deg": 27.5})
        result = ui.pipe_properties_dialog(settings, editing=False)
        self.assertEqual(27.5, result["label_rotation_deg"])
        self.assertTrue(any("Beschriftungsdrehung" in value
                            for value in api.text.values()))

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
