# -*- coding: utf-8 -*-
"""OIP controls and double-click editing for persistent utility routes."""
from __future__ import absolute_import

import vs

from . import app
from . import live
from . import live_objects


EDIT = 2001
HOME = 2002
CHAIN = 2003
TERRAIN = 2004


def run():
    event, button = vs.vsoGetEventInfo()
    if event == 5:
        vs.SetObjPropVS(7, True)
        vs.SetObjPropVS(8, True)
        vs.vsoInsertAllParams()
        vs.SetObjPropCharVS(3, chr(1))
        for widget, title in (
                (EDIT, "Leitungstrasse bearbeiten…"),
                (CHAIN, "Höhenkette bearbeiten…"),
                (TERRAIN, "Unter Geländemodell aktualisieren…"),
                (HOME, "Kanal- und Leitungstool öffnen…")):
            vs.vsoAppendWidget(12, widget, title, 0)
        return
    if event == 3:
        live.reset()
        try:
            from PD_KanalLeitungMengen import reporting as quantity_reporting
            quantity_reporting.refresh_existing()
        except Exception:
            pass
        return
    if event not in (7, 35):
        return
    valid, name, handle, _record, _wall = vs.GetCustomObjectInfo()
    if not valid or name != live_objects.PLUGIN or not handle:
        return
    try:
        vs.DSelectAll()
        vs.SetSelect(handle)
        if event == 7 or button == EDIT:
            app.run("edit")
        elif button == CHAIN:
            app.run("chain")
        elif button == TERRAIN:
            app.run("terrain")
        elif button == HOME:
            from PD_KanalLeitungTool import app as common_app
            common_app.run()
        vs.vsoSetEventResult(0)
    except Exception as error:
        vs.AlrtDialog("Leitungstool: " + str(error))
        vs.vsoSetEventResult(-5)
