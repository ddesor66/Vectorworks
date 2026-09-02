"""Native Object Info controls and double-click editing for existing live PIOs."""
import vs

from . import app, core, live_objects as live


EDIT = 1001
BUTTONS = (
    (1002, 1, "Gefällelinie zeichnen…"),
    (1003, 12, "Einzelnen Höhenpunkt setzen…"),
    (1004, 13, "Höhenpunkte verbinden…"),
    (1005, 2, "An Höhenpunkt weiterzeichnen…"),
    (1006, 10, "Höhenpunkt in Verbindung einfügen…"),
    (1007, 4, "Segmentgefälle ändern…"),
    (1008, 8, "2D / 3D und Geländewirkung…"),
    (1009, 9, "Geländedaten bereitstellen…"),
    (1010, 5, "Darstellung aktualisieren"),
    (1011, 7, "Voreinstellungen…"),
    (1012, 0, "Markierte Ausgangslinie verwenden…"),
    (1013, 6, "Alle Gefälle neu zeichnen"),
)


def owner(handle):
    data = live.data_of(handle)
    if data and data["role"] == "label":
        handle = vs.GetObject(data["owner"])
        data = live.data_of(handle)
    if not data:
        raise core.SlopeError("Das zugehörige Gefälleobjekt fehlt.")
    return handle, data


def edit_point(handle, data):
    point = live.read_point(handle, data)
    text = vs.StrDialog("Höhe von Punkt P:%d in Metern:" % point["number"], str(point["height_m"]))
    if vs.DidCancel():
        return False
    height = core._number(str(text).replace(",", "."), "Höhe")
    previous = vs.GetRField(handle, live.PLUGIN, "Hoehe_m")
    vs.NameUndoEvent("PD Gefällepunkthöhe bearbeiten")
    try:
        vs.SetRField(handle, live.PLUGIN, "Hoehe_m", str(height))
        live.read_point(handle, data)
        vs.ResetObject(handle)
    except Exception:
        vs.SetRField(handle, live.PLUGIN, "Hoehe_m", previous)
        vs.ResetObject(handle)
        raise
    vs.ReDrawAll()
    return True


def edit(handle):
    target, data = owner(handle)
    vs.DSelectAll()
    vs.SetSelect(target)
    if data["role"] == "point":
        return edit_point(target, data)
    app.run(11)
    return True


def run():
    event, button = vs.vsoGetEventInfo()
    if event == 5:
        vs.SetObjPropVS(7, True)
        vs.SetObjPropVS(8, True)
        vs.vsoInsertAllParams()
        vs.SetObjPropCharVS(3, chr(1))
        vs.vsoAppendWidget(12, EDIT, "Gefälle bearbeiten…", 0)
        for widget, _action, title in BUTTONS:
            vs.vsoAppendWidget(12, widget, title, 0)
        return
    if event == 3:
        live.reset()
        return
    if event not in (7, 35):
        return
    valid, name, handle, _record, _wall = vs.GetCustomObjectInfo()
    if not valid or name != live.PLUGIN or not handle:
        return
    try:
        target, data = owner(handle)
        if event == 7:
            changed = edit(handle)
            vs.vsoSetEventResult(0 if changed else -5)
            return
        if button == EDIT:
            app.run(11)
            vs.vsoSetEventResult(0)
            return
        action = next((action for widget, action, _title in BUTTONS if widget == button), None)
        if action is not None:
            if action != 0:  # Keep the user's source-line selection for this action.
                target, _data = owner(handle)
                vs.DSelectAll()
                vs.SetSelect(target)
            app.run(action)
            vs.vsoSetEventResult(0)
    except Exception as error:
        vs.AlrtDialog("Gefälle bearbeiten: " + str(error))
        vs.vsoSetEventResult(-5)
