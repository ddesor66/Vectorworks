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
    def __init__(self):
        self.values = {}
        self.repaginate = False
        self.drawing_rect = None

    def SetDrawingRect(self, width, height):
        self.drawing_rect = (float(width), float(height))

    def SetObjectVariableReal(self, layer, selector, value):
        self.values[(layer, int(selector))] = float(value)

    def SetObjectVariableBoolean(self, layer, selector, value):
        if int(selector) == 156:
            self.repaginate = bool(value)

    def TBB_GetPageArea(self, layer):
        if not self.repaginate:
            return 8.2677, 11.6929
        # Selectors 165/166 are document lengths; the test document uses m.
        return (self.values[(layer, 165)] / 0.0254,
                self.values[(layer, 166)] / 0.0254)


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


if __name__ == "__main__":
    unittest.main()
