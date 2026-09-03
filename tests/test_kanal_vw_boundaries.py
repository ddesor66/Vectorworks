# -*- coding: utf-8 -*-
"""Regression tests for Vectorworks return values and sheet-page setup."""
from __future__ import absolute_import

import importlib
import sys
import types
import unittest
from unittest import mock


def load_module(fake_vs, module_name):
    sys.modules["vs"] = fake_vs
    for name in tuple(sys.modules):
        if name == "PD_KanalTool" or name.startswith("PD_KanalTool."):
            sys.modules.pop(name, None)
    return importlib.import_module(module_name)


class TrackAPI(object):
    def __init__(self, result):
        self.result = result
        self.help = []

    def SetTempToolHelpStr(self, value):
        self.help.append(value)

    def TrackObject(self, predicate):
        del predicate
        return self.result


class PolygonTrackAPI(TrackAPI):
    def __init__(self, result, top_level=True, live=True):
        super(PolygonTrackAPI, self).__init__(result)
        self.top_level = bool(top_level)
        self.live = bool(live)

    def GetTypeN(self, handle):
        return 5 if self.live and handle == "POLYGON" else 0

    def GetParent(self, handle):
        del handle
        return "LAYER" if self.top_level else "PIO"

    def GetLayer(self, handle):
        del handle
        return "LAYER"


class PageAPI(object):
    def __init__(self, portrait_report=False, portrait_drawing_rect=False,
                 units_to_meters=1.0, printable_scale=(1.0, 1.0)):
        self.values = {}
        self.repaginate = False
        self.drawing_rect = None
        self.portrait_report = bool(portrait_report)
        self.portrait_drawing_rect = bool(portrait_drawing_rect)
        self.units_to_meters = float(units_to_meters)
        self.printable_scale = tuple(float(value) for value in printable_scale)
        self.active_layer = None
        self.deleted = []

    def CreateLayer(self, name, layer_type):
        self.active_layer = (str(name), int(layer_type))
        return "SHEET"

    def Layer(self, name):
        self.active_layer = str(name)

    def DelObject(self, handle):
        self.deleted.append(handle)

    def SetDrawingRect(self, width, height):
        self.drawing_rect = (float(width), float(height))

    def SetObjectVariableReal(self, layer, selector, value):
        self.values[(layer, int(selector))] = float(value)

    def SetObjectVariableBoolean(self, layer, selector, value):
        if int(selector) == 156:
            self.repaginate = bool(value)

    def TBB_GetPageArea(self, layer):
        if self.portrait_report:
            return 8.2633, 11.6933
        if not self.repaginate:
            return 8.2677, 11.6929
        return (self.values[(layer, 165)],
                self.values[(layer, 166)])

    def GetDrawingSizeRectN(self, layer):
        del layer
        width, height = self.drawing_rect
        if self.portrait_drawing_rect:
            width, height = height, width
        width *= self.printable_scale[0]
        height *= self.printable_scale[1]
        width_units = width * 0.0254 / self.units_to_meters
        height_units = height * 0.0254 / self.units_to_meters
        return ((-width_units / 2.0, height_units / 2.0),
                (width_units / 2.0, -height_units / 2.0))


class PDFAPI(object):
    def __init__(self, layer_names):
        self.layers = {name: "LAYER-" + name for name in layer_names}
        self.active = None
        self.calls = []
        self.closed = 0

    def AcquireExportPDFSettingsAndLocation(self, separate):
        self.calls.append(("acquire", bool(separate)))
        return True

    def OpenPDFDocument(self, name):
        self.calls.append(("open", str(name)))
        return True

    def GetLayerByName(self, name):
        return self.layers.get(str(name))

    def Layer(self, name):
        self.active = str(name)
        self.calls.append(("layer", self.active))

    def ExportPDFPages(self, saved_view_name):
        self.calls.append(("export", self.active, str(saved_view_name)))
        return 0

    def ClosePDFDocument(self):
        self.closed += 1
        self.calls.append(("close",))


class DeleteAPI(object):
    def __init__(self, keep_owner=False, keep_label=False,
                 blocked_by_label=False):
        self.objects = {"PIPE": "PIPE", "LABEL": "LABEL",
                        "START": "START", "END": "END"}
        self.keep_owner = bool(keep_owner)
        self.keep_label = bool(keep_label)
        self.blocked_by_label = bool(blocked_by_label)
        self.reset = []
        self.associations = {}

    def GetName(self, handle):
        return str(handle)

    def GetObject(self, name):
        return self.objects.get(str(name))

    def DelObject(self, handle):
        if (str(handle) == "PIPE" and
                (self.keep_owner or
                 (self.blocked_by_label and "LABEL" in self.objects) or
                 any((5, "PIPE") in rows
                     for rows in self.associations.values()))):
            return
        if str(handle) == "LABEL" and self.keep_label:
            return
        self.objects.pop(str(handle), None)

    def ResetObject(self, handle):
        self.reset.append(str(handle))

    def GetTypeN(self, handle):
        return 86 if handle in self.objects.values() else 0

    def RemoveAssociation(self, owner, kind, target):
        row = (int(kind), str(target))
        rows = self.associations.setdefault(str(owner), [])
        if row not in rows:
            return False
        rows.remove(row)
        return True

    def AddAssociation(self, owner, kind, target):
        row = (int(kind), str(target))
        rows = self.associations.setdefault(str(owner), [])
        if row not in rows:
            rows.append(row)
        return True


class ConnectionLabelAPI(object):
    def __init__(self):
        self.names = {"OWNER": "PD-KAN-S-shaft-1"}
        self.objects = {"PD-KAN-S-shaft-1": "OWNER"}
        self.parents = {"OWNER": "LAYER"}
        self.reset = []

    def GetName(self, handle):
        return self.names.get(handle, "")

    def GetObject(self, name):
        return self.objects.get(str(name))

    def GetLayer(self, handle):
        del handle
        return "LAYER"

    def GetParent(self, handle):
        return self.parents.get(handle)

    def SetParent(self, handle, parent):
        self.parents[handle] = parent
        return True

    def AddAssociation(self, owner, kind, label):
        return owner == "OWNER" and kind == 4 and bool(label)

    def HMove(self, handle, dx, dy):
        del handle, dx, dy

    def ResetObject(self, handle):
        self.reset.append(handle)


class ShaftGraphicsAPI(object):
    def __init__(self):
        self.calls = []

    def __getattr__(self, name):
        if name.startswith("Set"):
            return lambda *args: self.calls.append((name,) + args)
        return lambda *args: None


class VectorworksBoundaryTests(unittest.TestCase):
    def test_shaft_fill_transparency_keeps_contour_opaque(self):
        api = ShaftGraphicsAPI()
        live = load_module(api, "PD_KanalTool.live")
        live._set_shaft_graphics(
            "SHAFT", "PD-KAN-RW-Schacht",
            (100, 200, 300), (400, 500, 600), 35.0)
        self.assertIn(
            ("SetPenFore", "SHAFT", (100, 200, 300)), api.calls)
        self.assertIn(
            ("SetFillFore", "SHAFT", (400, 500, 600)), api.calls)
        self.assertIn(("SetOpacityN", "SHAFT", 100, 65), api.calls)
        preferences = {
            "colors": {"RW": [1, 1, 1]},
            "shaft_pen_colors": {"RW": [10, 20, 30]},
            "shaft_fill_colors": {"RW": [40, 50, 60]},
            "shaft_fill_transparency_percent": {"RW": 25.0},
        }
        self.assertEqual(
            ((10, 20, 30), (40, 50, 60), 25.0),
            live.shaft_graphics_for({"kind": "RW"}, preferences))

    def test_track_object_none_is_a_clean_cancel(self):
        api = TrackAPI(None)
        adapter = load_module(api, "PD_KanalTool.vw_adapter")
        self.assertIsNone(adapter.pick_object(lambda _handle: True, "Objekt wählen"))
        self.assertEqual(["Objekt wählen", ""], api.help)

    def test_track_object_accepts_documented_and_scalar_return_shapes(self):
        for value, expected in ((('HANDLE', (1.0, 2.0, 0.0)), 'HANDLE'),
                                ('HANDLE', 'HANDLE')):
            api = TrackAPI(value)
            adapter = load_module(api, "PD_KanalTool.vw_adapter")
            self.assertEqual(expected, adapter.pick_object(lambda _handle: True, "Auswahl"))

    def test_special_polygon_picker_rejects_stale_and_pio_child_handles(self):
        for api in (PolygonTrackAPI("POLYGON", live=False),
                    PolygonTrackAPI("POLYGON", top_level=False)):
            adapter = load_module(api, "PD_KanalTool.vw_adapter")
            self.assertIsNone(adapter.pick_polygon())

    def test_special_polygon_picker_accepts_top_level_live_geometry(self):
        api = PolygonTrackAPI(("POLYGON", (1.0, 2.0, 0.0)))
        adapter = load_module(api, "PD_KanalTool.vw_adapter")
        self.assertEqual("POLYGON", adapter.pick_polygon())

    def test_special_conversion_is_repeatable_without_double_pipe_resets(self):
        deleted = []
        deselected = []
        commits = []
        api = types.SimpleNamespace(
            GetTypeN=lambda handle: 5 if str(handle).startswith("POLY") else 86,
            IsPolyClosed=lambda _handle: True,
            SetDSelect=deselected.append,
            DelObject=deleted.append,
            ReDrawAll=lambda: None)
        live = load_module(api, "PD_KanalTool.live")
        store = types.SimpleNamespace(data_of=lambda _handle: {"role": "sewer_shaft"})
        shaft = {"id": "s1", "structure_type": "round", "x_m": 10.0, "y_m": 20.0}
        with mock.patch.object(live, "_live", return_value=store), mock.patch.object(
                live, "read_shaft", return_value=shaft), mock.patch.object(
                live.adapter, "extract_path", return_value={
                    "points": ((9.0, 19.0), (11.0, 19.0), (11.0, 21.0), (9.0, 21.0))}), mock.patch.object(
                live.core, "validate_shaft", side_effect=lambda value, allow_hidden=False: value), mock.patch.object(
                live, "_commit_network_updates",
                side_effect=lambda pipes, shafts, preferences, name: commits.append(
                    (pipes, shafts, preferences, name))):
            live.replace_with_special("SHAFT", "POLY1", {"draw_3d": True})
            live.replace_with_special("SHAFT", "POLY2", {"draw_3d": True})
        self.assertEqual(["POLY1", "POLY2"], deselected)
        self.assertEqual(["POLY1", "POLY2"], deleted)
        self.assertEqual(2, len(commits))

    def test_failed_special_conversion_keeps_source_contour_for_retry(self):
        deleted = []
        api = types.SimpleNamespace(
            GetTypeN=lambda handle: 5 if handle == "POLYGON" else 86,
            IsPolyClosed=lambda _handle: True,
            SetDSelect=lambda _handle: None,
            DelObject=deleted.append,
            ReDrawAll=lambda: None)
        live = load_module(api, "PD_KanalTool.live")
        store = types.SimpleNamespace(data_of=lambda _handle: {"role": "sewer_shaft"})
        shaft = {"id": "s1", "structure_type": "round", "x_m": 0.0, "y_m": 0.0}
        with mock.patch.object(live, "_live", return_value=store), mock.patch.object(
                live, "read_shaft", return_value=shaft), mock.patch.object(
                live.adapter, "extract_path", return_value={
                    "points": ((-1.0, -1.0), (1.0, -1.0), (1.0, 1.0), (-1.0, 1.0))}), mock.patch.object(
                live.core, "validate_shaft", side_effect=lambda value, allow_hidden=False: value), mock.patch.object(
                live, "_commit_network_updates", side_effect=live.core.SewerError("Renderfehler")):
            with self.assertRaisesRegex(live.core.SewerError, "Renderfehler"):
                live.replace_with_special("SHAFT", "POLYGON", {})
        self.assertEqual([], deleted)

    def test_sheet_page_sets_all_native_dimensions_before_validation(self):
        api = PageAPI()
        sheets = load_module(api, "PD_KanalTool.shaft_sheets_vw")
        actual = sheets._set_sheet_page_size(
            "LAYER", *sheets.A4_LANDSCAPE_INCHES, units_to_meters=1.0)
        self.assertAlmostEqual(sheets.A4_LANDSCAPE_INCHES[0], actual[0])
        self.assertAlmostEqual(sheets.A4_LANDSCAPE_INCHES[1], actual[1])
        self.assertEqual(sheets.A4_LANDSCAPE_INCHES, api.drawing_rect)
        self.assertTrue(api.repaginate)
        self.assertEqual(
            {165, 166, 167, 168},
            {selector for layer, selector in api.values if layer == "LAYER"})
        for selector, expected in ((165, sheets.A4_LANDSCAPE_INCHES[0]),
                                   (166, sheets.A4_LANDSCAPE_INCHES[1]),
                                   (167, sheets.A4_LANDSCAPE_INCHES[0]),
                                   (168, sheets.A4_LANDSCAPE_INCHES[1])):
            self.assertAlmostEqual(expected, api.values[("LAYER", selector)])

    def test_sheet_page_is_independent_of_metric_document_unit(self):
        for factor in (1.0, 0.01, 0.001):
            api = PageAPI(units_to_meters=factor)
            sheets = load_module(api, "PD_KanalTool.shaft_sheets_vw")
            actual = sheets._set_sheet_page_size(
                "LAYER", *sheets.A4_LANDSCAPE_INCHES,
                units_to_meters=factor)
            self.assertEqual(sheets.A4_LANDSCAPE_INCHES, actual)
            self.assertEqual(sheets.A4_LANDSCAPE_INCHES, api.drawing_rect)
            self.assertAlmostEqual(
                sheets.A4_LANDSCAPE_INCHES[0], api.values[("LAYER", 165)])

    def test_sheet_page_accepts_vw_printer_portrait_report_for_same_a4_medium(self):
        api = PageAPI(
            portrait_report=True, printable_scale=(0.96, 0.90))
        sheets = load_module(api, "PD_KanalTool.shaft_sheets_vw")
        actual = sheets._set_sheet_page_size(
            "LAYER", *sheets.A4_LANDSCAPE_INCHES, units_to_meters=1.0)
        self.assertEqual(sheets.A4_LANDSCAPE_INCHES, actual)
        self.assertEqual(sheets.A4_LANDSCAPE_INCHES, api.drawing_rect)

    def test_sheet_creation_continues_to_render_for_vw_portrait_a4_report(self):
        api = PageAPI(portrait_report=True)
        sheets = load_module(api, "PD_KanalTool.shaft_sheets_vw")
        sheets.adapter.units_to_meters = lambda: 1.0
        rendered = []
        sheets._render_page = lambda *args: rendered.append(args)
        result = sheets._create_sheet_layer(
            "TMP", {"name": "RW.001"}, (), {}, {})
        self.assertEqual("SHEET", result)
        self.assertEqual(1, len(rendered))
        self.assertEqual([], api.deleted)

    def test_sheet_page_rejects_portrait_drawing_rectangle(self):
        api = PageAPI(portrait_report=True, portrait_drawing_rect=True)
        sheets = load_module(api, "PD_KanalTool.shaft_sheets_vw")
        with self.assertRaisesRegex(Exception, "Zeichenrahmen"):
            sheets._set_sheet_page_size(
                "LAYER", *sheets.A4_LANDSCAPE_INCHES,
                units_to_meters=1.0)

    def test_pdf_export_activates_each_sheet_and_uses_chosen_common_file(self):
        api = PDFAPI(("PD-Schachtblatt-RW.001", "PD-Schachtblatt-RW.002"))
        sheets = load_module(api, "PD_KanalTool.shaft_sheets_vw")
        self.assertTrue(sheets.export_pdf(
            ("PD-Schachtblatt-RW.001", "PD-Schachtblatt-RW.002"),
            "Projekt Schachtblätter"))
        self.assertEqual(
            [("export", "PD-Schachtblatt-RW.001", "PD-Schachtblatt-RW.001"),
             ("export", "PD-Schachtblatt-RW.002", "PD-Schachtblatt-RW.002")],
            [call for call in api.calls if call[0] == "export"])
        self.assertIn(("open", ""), api.calls)
        self.assertEqual("PD-Schachtblatt-RW.001", api.active)
        self.assertEqual(1, api.closed)

    def test_verified_replacement_delete_removes_pipe_and_label(self):
        api = DeleteAPI()
        live = load_module(api, "PD_KanalTool.live")
        live._delete_with_labels("PIPE", {"labels": ["LABEL"]}, verify=True)
        self.assertNotIn("PIPE", api.objects)
        self.assertNotIn("LABEL", api.objects)

    def test_replacement_deletes_dependent_label_before_owner(self):
        api = DeleteAPI(blocked_by_label=True)
        live = load_module(api, "PD_KanalTool.live")
        live._delete_with_labels("PIPE", {"labels": ["LABEL"]}, verify=True)
        self.assertNotIn("PIPE", api.objects)
        self.assertNotIn("LABEL", api.objects)

    def test_replacement_detaches_both_endpoint_shafts_before_old_pipe(self):
        api = DeleteAPI()
        api.objects.update({
            "PD-KAN-S-start": "START", "PD-KAN-S-end": "END"})
        api.associations = {
            "START": [(4, "PIPE")], "END": [(4, "PIPE")],
            "PIPE": [(5, "START"), (5, "END")]}
        live = load_module(api, "PD_KanalTool.live")
        data = {
            "schema": live.core.SCHEMA, "role": "sewer_pipe",
            "pipe": {"start_id": "start", "end_id": "end"},
            "labels": ["LABEL"],
        }
        live._delete_with_labels("PIPE", data, verify=True)
        self.assertNotIn("PIPE", api.objects)
        self.assertEqual([], api.associations["START"])
        self.assertEqual([], api.associations["END"])
        self.assertEqual([], api.associations["PIPE"])

    def test_failed_replacement_restores_both_endpoint_associations(self):
        api = DeleteAPI(keep_owner=True)
        api.objects.update({
            "PD-KAN-S-start": "START", "PD-KAN-S-end": "END"})
        api.associations = {
            "START": [(4, "PIPE")], "END": [(4, "PIPE")],
            "PIPE": [(5, "START"), (5, "END")]}
        live = load_module(api, "PD_KanalTool.live")
        live.is_sewer_data = lambda _data: True
        live.ensure_label = lambda _owner, _data, _created: "LABEL"
        data = {
            "schema": live.core.SCHEMA, "role": "sewer_pipe",
            "pipe": {"start_id": "start", "end_id": "end"},
            "labels": [],
        }
        with self.assertRaisesRegex(Exception, "konnte nicht gelöscht werden"):
            live._delete_with_labels("PIPE", data, verify=True)
        self.assertEqual([(4, "PIPE")], api.associations["START"])
        self.assertEqual([(4, "PIPE")], api.associations["END"])
        self.assertEqual([(5, "START"), (5, "END")], api.associations["PIPE"])

    def test_pipe_links_delete_with_shaft_but_only_reset_surviving_endpoints(self):
        api = DeleteAPI()
        api.objects.update({
            "PD-KAN-S-start": "START", "PD-KAN-S-end": "END"})
        # Simulate an old release's unsafe reset relationships. Synchronising
        # must remove those and install one exact link in each direction.
        api.associations = {
            "START": [(5, "PIPE")], "END": [(5, "PIPE")], "PIPE": []}
        live = load_module(api, "PD_KanalTool.live")
        live._sync_pipe_associations(
            "PIPE", {"start_id": "start", "end_id": "end"})
        self.assertEqual([(4, "PIPE")], api.associations["START"])
        self.assertEqual([(4, "PIPE")], api.associations["END"])
        self.assertEqual([(5, "START"), (5, "END")], api.associations["PIPE"])

    def test_verified_replacement_delete_rejects_remaining_old_pipe(self):
        api = DeleteAPI(keep_owner=True)
        live = load_module(api, "PD_KanalTool.live")
        live.is_sewer_data = lambda _data: True
        def restore_label(_owner, _data, created):
            api.objects["LABEL"] = "LABEL"
            created.append("LABEL")
            return "LABEL"
        live.ensure_label = restore_label
        with self.assertRaisesRegex(Exception, "konnte nicht gelöscht werden"):
            live._delete_with_labels("PIPE", {"labels": ["LABEL"]}, verify=True)
        self.assertIn("PIPE", api.objects)
        self.assertIn("LABEL", api.objects)
        self.assertEqual(["LABEL"], api.reset)

    def test_failed_label_restoration_removes_partial_recovery_object(self):
        api = DeleteAPI(keep_owner=True)
        live = load_module(api, "PD_KanalTool.live")
        live.is_sewer_data = lambda _data: True
        def fail_after_creation(_owner, _data, created):
            api.objects["RECOVERY"] = "RECOVERY"
            created.append("RECOVERY")
            raise RuntimeError("association failed")
        live.ensure_label = fail_after_creation
        with self.assertRaisesRegex(Exception, "Wiederherstellung fehlgeschlagen"):
            live._delete_with_labels("PIPE", {"labels": ["LABEL"]}, verify=True)
        self.assertIn("PIPE", api.objects)
        self.assertNotIn("RECOVERY", api.objects)

    def test_verified_replacement_delete_reports_remaining_old_label(self):
        api = DeleteAPI(keep_label=True)
        live = load_module(api, "PD_KanalTool.live")
        with self.assertRaisesRegex(Exception, "LABEL$"):
            live._delete_with_labels("PIPE", {"labels": ["LABEL"]}, verify=True)
        self.assertIn("PIPE", api.objects)
        self.assertIn("LABEL", api.objects)

    def test_shaft_endpoint_heights_are_independent_movable_label_objects(self):
        api = ConnectionLabelAPI()
        live = load_module(api, "PD_KanalTool.live")
        settings = importlib.import_module("PD_KanalTool.settings")
        preferences = settings.validate({"connection_point_size": 11.0})
        owner_data = {
            "schema": live.core.SCHEMA,
            "role": "sewer_shaft",
            "shaft": {"id": "shaft-1"},
            "labels": ["PRIMARY"],
            "preferences": preferences,
        }

        class Store(object):
            def __init__(self):
                self.data = {"OWNER": owner_data}

            def data_of(self, handle):
                return self.data.get(handle)

            def write_data(self, handle, data):
                self.data[handle] = data

            def _new_object(self, xy, data, name, created):
                handle = "LABEL-%d" % (len(created) + 1)
                api.names[handle] = name
                api.objects[name] = handle
                api.parents[handle] = "LAYER"
                self.data[handle] = data
                created.append(handle)
                return handle

        store = Store()
        live._live = lambda: store
        live.adapter.units_to_meters = lambda: 1.0
        shaft = {
            "id": "shaft-1", "x_m": 10.0, "y_m": 20.0,
            "visible": True, "structure_type": "round",
        }
        rows = (
            {"connection_id": "p1:start", "role": "out", "tag": "A1",
             "invert_m": 97.95, "direction": (1.0, 0.0)},
            {"connection_id": "p2:end", "role": "in", "tag": "Z1",
             "invert_m": 97.85, "direction": (0.0, 1.0)},
        )
        live.read_shaft = lambda _owner, _data=None: shaft
        live.shaft_connection_views = lambda _shaft: rows
        live.core.shaft_outer_diameter_m = lambda _shaft: 1.0

        created = []
        updated = live._ensure_connection_height_labels(
            "OWNER", owner_data, created)
        self.assertEqual(2, len(created))
        self.assertEqual(3, len(updated["labels"]))
        for handle, row in zip(created, rows):
            label_data = store.data[handle]
            self.assertEqual("connection_height", label_data["label_kind"])
            self.assertEqual(row["connection_id"], label_data["connection_id"])
            self.assertTrue(label_data["auto_position"])

        # Moving only one label turns off its automatic placement.  A later
        # shaft reset therefore does not pull the text back onto the shaft.
        moved = created[0]
        auto_xy = store.data[moved]["auto_xy"]
        live.adapter.symbol_location_2d = lambda handle, fallback: (
            (auto_xy[0] + 2.0, auto_xy[1] + 1.0)
            if handle == moved else tuple(fallback))
        live._reset_labels(updated)
        self.assertFalse(store.data[moved]["auto_position"])
        self.assertIn(moved, api.reset)


if __name__ == "__main__":
    unittest.main()
