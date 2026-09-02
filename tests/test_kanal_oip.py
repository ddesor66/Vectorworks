# -*- coding: utf-8 -*-
"""Object-Info-Palette regression checks for the channel object."""
from __future__ import absolute_import

import importlib
import sys
import unittest


class OIPAPI(object):
    def __init__(self, event=5, button=0):
        self.event = event
        self.button = button
        self.widgets = []
        self.selected = []
        self.deselected = 0
        self.result = None

    def vsoGetEventInfo(self):
        return self.event, self.button

    def SetObjPropVS(self, *_args):
        return None

    def SetObjPropCharVS(self, *_args):
        return None

    def vsoInsertAllParams(self):
        return None

    def vsoAppendWidget(self, kind, widget, title, data):
        self.widgets.append((kind, widget, title, data))

    def GetCustomObjectInfo(self):
        return True, "PD KAN Objekt", "TARGET", None, None

    def DSelectAll(self):
        self.deselected += 1

    def SetSelect(self, handle):
        self.selected.append(handle)

    def GetName(self, handle):
        return str(handle)

    def vsoSetEventResult(self, value):
        self.result = value

    def AlrtDialog(self, value):
        raise AssertionError(value)


def load_events(api):
    sys.modules["vs"] = api
    for name in tuple(sys.modules):
        if name == "PD_KanalTool" or name.startswith("PD_KanalTool."):
            sys.modules.pop(name, None)
    return importlib.import_module("PD_KanalTool.object_events")


class KanalOIPTests(unittest.TestCase):
    def test_oip_contains_connect_shafts_merge_and_delete_once(self):
        api = OIPAPI()
        events = load_events(api)
        events.run()
        titles = [row[2] for row in api.widgets]
        self.assertEqual(len(titles), len(set(titles)))
        self.assertTrue(any("weiterem Schacht verbinden" in title for title in titles))
        self.assertTrue(any("Zwei Haltungen vereinigen" in title for title in titles))
        self.assertTrue(any("Kanalobjekte löschen" in title for title in titles))
        self.assertFalse(any("Voreinstellungen" in title for title in titles))

    def test_connect_shafts_button_preserves_selection_and_routes_action(self):
        api = OIPAPI(event=35)
        events = load_events(api)
        api.button = events.CONNECT_SHAFTS
        events.owner = lambda _handle: ("TARGET", {"role": "sewer_shaft"})
        events.live.selected_managed = lambda: (
            ("TARGET", {"role": "sewer_shaft"}),
            ("SECOND", {"role": "sewer_shaft"}),
        )
        actions = []
        events.app.run = lambda action=None: actions.append(action)
        events.run()
        self.assertEqual(["connect_shafts"], actions)
        self.assertEqual(0, api.deselected)
        self.assertEqual([], api.selected)
        self.assertEqual(0, api.result)

    def test_delete_button_routes_selected_object_delete(self):
        api = OIPAPI(event=35)
        events = load_events(api)
        api.button = events.DELETE
        events.owner = lambda _handle: ("TARGET", {"role": "sewer_pipe"})
        events.live.selected_managed = lambda: ()
        actions = []
        events.app.run = lambda action=None: actions.append(action)
        events.run()
        self.assertEqual(["delete"], actions)
        self.assertEqual(0, api.deselected)
        self.assertEqual(["TARGET"], api.selected)


if __name__ == "__main__":
    unittest.main()
