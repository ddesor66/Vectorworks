# -*- coding: utf-8 -*-
"""OIP controls and double-click editing for independent channel objects."""

from __future__ import absolute_import

import vs

from . import app, core, live, live_objects, settings


EDIT = 2001
HOME = 2003
CONNECT = 2004
SPLIT = 2005
STUB = 2006
SPECIAL = 2007
DROP = 2008
TERRAIN = 2009
SHEETS = 2010
CONNECT_SHAFTS = 2014
MERGE = 2015
DELETE = 2016


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
                (CONNECT, "Neuen Kanalstrang anschließen…"),
                (CONNECT_SHAFTS, "Schacht mit weiterem Schacht verbinden…"),
                (SPLIT, "Schacht in Haltung einsetzen…"),
                (STUB, "Kanalstutzen herstellen…"),
                (SPECIAL, "Schacht in Sonderschacht umwandeln…"),
                (DROP, "Absturz vor Schacht bearbeiten…"),
                (MERGE, "Zwei Haltungen vereinigen…"),
                (TERRAIN, "Schachtdeckel an Geländemodell anpassen…"),
                (SHEETS, "Schachtblätter erstellen…"),
                (DELETE, "Ausgewählte Kanalobjekte löschen…"),
                (HOME, "Weitere Kanalbefehle…")):
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
        if event == 7 or button == EDIT:
            selected = [row_handle for row_handle, _row_data in live.selected_managed()]
            selected_names = {str(vs.GetName(row_handle) or "") for row_handle in selected}
            if str(vs.GetName(target) or "") not in selected_names:
                selected.append(target)
            changed = live.edit_network_chain(tuple(selected), settings.load())
            if changed:
                from PD_KanalLeitungMengen import reporting as quantity_reporting
                quantity_reporting.refresh_existing(force=True)
            vs.vsoSetEventResult(0 if changed else -5)
            return
        # Multi-object commands keep the current document selection. All
        # other buttons operate solely on the OIP owner to avoid accidental
        # edits of unrelated objects.
        preserve_selection = button in (
            CONNECT_SHAFTS, MERGE, DELETE, SHEETS, TERRAIN)
        if not preserve_selection:
            vs.DSelectAll()
        selected_names = {
            str(vs.GetName(row_handle) or "")
            for row_handle, _row_data in live.selected_managed()}
        if str(vs.GetName(target) or "") not in selected_names:
            vs.SetSelect(target)
        actions = {
            HOME: None, CONNECT: "connect", CONNECT_SHAFTS: "connect_shafts",
            SPLIT: "split",
            STUB: "stub", SPECIAL: "special", DROP: "drop",
            MERGE: "merge", DELETE: "delete",
            TERRAIN: "terrain_covers", SHEETS: "shaft_sheets",
        }
        app.run(actions.get(button))
        vs.vsoSetEventResult(0)
    except Exception as error:
        vs.AlrtDialog("Kanaltool: " + str(error))
        vs.vsoSetEventResult(-5)
