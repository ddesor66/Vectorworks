# -*- coding: utf-8 -*-
"""OIP controls and double-click editing for independent channel objects."""

from __future__ import absolute_import

import vs

from . import app, core, live, live_objects, settings


EDIT = 2001
DRAW = 2002
HOME = 2003
CONNECT = 2004
SPLIT = 2005
STUB = 2006
SPECIAL = 2007
DROP = 2008
TERRAIN = 2009
SHEETS = 2010
VALIDATE = 2011
QUANTITIES = 2012
SETTINGS = 2013


def owner(handle):
    data = live_objects.data_of(handle)
    if data and data.get("role") == "sewer_label":
        handle = vs.GetObject(data.get("owner", ""))
        data = live_objects.data_of(handle)
    if not live.is_sewer_data(data):
        raise core.SewerError("Das zugehörige Kanalobjekt fehlt.")
    return handle, data


def run():
    event, button = vs.vsoGetEventInfo()
    if event == 5:
        vs.SetObjPropVS(7, True)
        vs.SetObjPropVS(8, True)
        vs.vsoInsertAllParams()
        vs.SetObjPropCharVS(3, chr(1))
        for widget, title in (
                (EDIT, "Kanalnetz / Kette bearbeiten…"),
                (DRAW, "Neue Kanalanlage durch Punkte zeichnen…"),
                (HOME, "Kanaltool öffnen…"),
                (CONNECT, "Neuen Kanalstrang anschließen…"),
                (SPLIT, "Schacht in Haltung einsetzen…"),
                (STUB, "Kanalstutzen herstellen…"),
                (SPECIAL, "Schacht in Sonderschacht umwandeln…"),
                (DROP, "Absturz vor Schacht bearbeiten…"),
                (TERRAIN, "Schachtdeckel an Geländemodell anpassen…"),
                (SHEETS, "Schachtblätter erstellen…"),
                (VALIDATE, "Kanalnetz prüfen"),
                (QUANTITIES, "Massenermittlung / Excel…"),
                (SETTINGS, "Kanal-Voreinstellungen…")):
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
        target, _data = owner(handle)
        vs.DSelectAll()
        vs.SetSelect(target)
        if event == 7 or button == EDIT:
            changed = live.edit_network_chain(target, settings.load())
            if changed:
                from PD_KanalLeitungMengen import reporting as quantity_reporting
                quantity_reporting.refresh_existing(force=True)
            vs.vsoSetEventResult(0 if changed else -5)
            return
        actions = {
            DRAW: "draw", HOME: None, CONNECT: "connect", SPLIT: "split",
            STUB: "stub", SPECIAL: "special", DROP: "drop",
            TERRAIN: "terrain_covers", SHEETS: "shaft_sheets",
            VALIDATE: "validate", QUANTITIES: "quantities", SETTINGS: "settings",
        }
        app.run(actions.get(button))
        vs.vsoSetEventResult(0)
    except Exception as error:
        vs.AlrtDialog("Kanaltool: " + str(error))
        vs.vsoSetEventResult(-5)
