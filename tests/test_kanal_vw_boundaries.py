# -*- coding: utf-8 -*-
"""Regression tests for Vectorworks return values and sheet-page setup."""
from __future__ import absolute_import

import importlib
import sys
import unittest


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


class PageAPI(object):
    def __init__(self, portrait_report=False, portrait_drawing_rect=False):
        self.values = {}
        self.repaginate = False
        self.drawing_rect = None
        self.portrait_report = bool(portrait_report)
        self.portrait_drawing_rect = bool(portrait_drawing_rect)
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
        # Selectors 165/166 are document lengths; the test document uses m.
        return (self.values[(layer, 165)] / 0.0254,
                self.values[(layer, 166)] / 0.0254)

    def GetDrawingSizeRectN(self, layer):
        del layer
        width, height = self.drawing_rect
        if self.portrait_drawing_rect:
            width, height = height, width
        width_units = width * 0.0254
        height_units = height * 0.0254
        return ((-width_units / 2.0, height_units / 2.0),
                (width_units / 2.0, -height_units / 2.0))


class DeleteAPI(object):
    def __init__(self, keep_owner=False, keep_label=False,
                 blocked_by_label=False):
        self.objects = {"PIPE": "PIPE", "LABEL": "LABEL",
                        "START": "START", "END": "END"}
        self.keep_owner = bool(keep_owner)
        self.keep_label = bool(keep_label)
        self.blocked_by_label = bool(blocked_by_label)
        self.reset = []

    def GetName(self, handle):
        return str(handle)

    def GetObject(self, name):
        return self.objects.get(str(name))

    def DelObject(self, handle):
        if (str(handle) == "PIPE" and
                (self.keep_owner or
                 (self.blocked_by_label and "LABEL" in self.objects))):
            return
        if str(handle) == "LABEL" and self.keep_label:
            return
        self.objects.pop(str(handle), None)

    def ResetObject(self, handle):
        self.reset.append(str(handle))


class VectorworksBoundaryTests(unittest.TestCase):
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
            {165, 166},
            {selector for layer, selector in api.values if layer == "LAYER"})

    def test_sheet_page_accepts_vw_printer_portrait_report_for_same_a4_medium(self):
        api = PageAPI(portrait_report=True)
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


if __name__ == "__main__":
    unittest.main()
