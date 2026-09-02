"""One independently editable native parametric stair; no external object registry."""

import math
from dataclasses import replace

import vs

from ..core.stair import (
    StairError,
    StairSpec,
    adjusted_note_position,
    calculate,
    decode,
    encode,
    note_anchor,
)
from . import stair_dialog, stair_draw, stair_source

PLUGIN_NAME = "PD Treppe"
DATA_FIELD = "Daten"
CONTROL_FIELDS = ("ControlPoint01X", "ControlPoint01Y")
EDIT_BUTTON = 1001
RESET_TEXT_BUTTON = 1002
PATH_BUTTON = 1003
# Vectorworks SDK 2026: MiniCadCallBacks.h, ParametricSpecialEditMessage::kAction.
SPECIAL_EDIT_EVENT = 7


def is_stair(handle):
    if not handle or vs.GetTypeN(handle) != 86:
        return False
    record = vs.GetParametricRecord(handle)
    return bool(record) and vs.GetName(record) == PLUGIN_NAME


def read(handle):
    raw = vs.GetRField(handle, PLUGIN_NAME, DATA_FIELD)
    return decode(raw) if raw else (StairSpec(), None)


def _store(handle, spec, anchor):
    value = encode(spec, anchor)
    old = vs.GetRField(handle, PLUGIN_NAME, DATA_FIELD)
    vs.SetRField(handle, PLUGIN_NAME, DATA_FIELD, value)
    if vs.GetRField(handle, PLUGIN_NAME, DATA_FIELD) != value:
        vs.SetRField(handle, PLUGIN_NAME, DATA_FIELD, old)
        raise StairError("Vectorworks konnte die Treppendaten nicht vollständig speichern.")


def _point(handle):
    factor = stair_draw.units_per_metre()
    point = []
    for field in CONTROL_FIELDS:
        valid, value = vs.ValidNumStr(vs.GetRField(handle, PLUGIN_NAME, field))
        if not valid or not math.isfinite(float(value)):
            raise StairError("Der native Text-Kontrollpunkt ist nicht korrekt eingerichtet.")
        point.append(float(value) / factor)
    return tuple(point)


def _set_point(handle, point):
    # Explicit metre suffix avoids document-unit and decimal-precision ambiguities.
    for field, value in zip(CONTROL_FIELDS, point):
        vs.SetRField(handle, PLUGIN_NAME, field, f"{value:.12f} m")
    actual = _point(handle)
    if math.dist(actual, point) > 1e-7:
        raise StairError("Die Textposition konnte nicht korrekt gespeichert werden.")


def edit_object(handle):
    if not is_stair(handle):
        raise StairError("Bitte genau eine PD Treppe auswählen.")
    spec, anchor = read(handle)
    changed = stair_dialog.edit(spec)
    if changed is None:
        return False
    vs.NameUndoEvent("PD Treppe bearbeiten")
    _store(handle, changed, anchor)
    vs.ResetObject(handle)
    vs.ReDrawAll()
    return True


def reset_note(handle):
    spec, _anchor = read(handle)
    anchor = note_anchor(calculate(spec), stair_draw.layer_scale(handle))
    _set_point(handle, anchor)
    _store(handle, spec, anchor)
    vs.ResetObject(handle)
    vs.ReDrawAll()


def replace_path(handle):
    """Choose a new read-only source path and move the PIO to its origin."""
    selected = stair_source.pick()
    if selected is None:
        return False
    path, origin = selected
    spec, anchor = read(handle)
    changed = replace(spec, path_points=path)
    calculate(changed)  # Validate the complete stair before changing the PIO.
    old_location = tuple(vs.GetSymLoc(handle))
    dx, dy = origin[0] - old_location[0], origin[1] - old_location[1]
    vs.NameUndoEvent("PD Treppe – Lauflinie ersetzen")
    try:
        _store(handle, changed, anchor)
        vs.HMove(handle, dx, dy)
        if math.dist(tuple(vs.GetSymLoc(handle)), tuple(origin)) > 1e-7:
            raise StairError("Die Treppe konnte nicht an den Anfang der Lauflinie verschoben werden.")
        vs.ResetObject(handle)
        vs.ReDrawAll()
        return True
    except Exception:
        # HMove is a procedure and can fail after changing the object. Read
        # the actual location and restore from that value instead of assuming
        # that the requested displacement was completed exactly once.
        try:
            current = tuple(vs.GetSymLoc(handle))
            rollback = old_location[0] - current[0], old_location[1] - current[1]
            if math.hypot(*rollback) > 1e-10:
                vs.HMove(handle, *rollback)
        finally:
            _store(handle, spec, anchor)
            vs.ResetObject(handle)
        raise


def regenerate(handle):
    spec, previous_anchor = read(handle)
    result = calculate(spec)
    scale = stair_draw.layer_scale(handle)
    current = _point(handle) if previous_anchor is not None else None
    position = adjusted_note_position(result, scale, current, previous_anchor)
    anchor = note_anchor(result, scale)
    # No geometry is created until all parameters and the native control point are validated.
    _set_point(handle, position)
    _store(handle, spec, anchor)
    vs.SetCntrlPtVis(handle, 1, spec.show_note)
    vs.SetParameterVisibility(handle, DATA_FIELD, False)
    stair_draw.draw(result, handle, position)


def run():
    event, button = vs.vsoGetEventInfo()
    if event == 5:  # kObjOnInitXProperties; official Object Events reference.
        vs.SetObjPropVS(2, True)  # Layer-scale-dependent annotations.
        vs.SetObjPropVS(7, True)  # Prevent accidental insertion in walls.
        vs.SetObjPropVS(8, True)  # Custom Object Info widgets.
        vs.vsoInsertAllParams()  # Retain native control-point coordinate widgets and grips.
        vs.SetObjPropCharVS(3, chr(1))  # Custom double-click editor.
        vs.vsoAppendWidget(12, EDIT_BUTTON, "Treppe bearbeiten…", 0)
        vs.vsoAppendWidget(12, RESET_TEXT_BUTTON, "Textposition zurücksetzen", 0)
        vs.vsoAppendWidget(12, PATH_BUTTON, "Lauflinie neu auswählen…", 0)
        return
    valid, _name, handle, _record, _wall = vs.GetCustomObjectInfo()
    if not valid or not handle:
        return
    try:
        if event == 3:
            regenerate(handle)
        elif event == SPECIAL_EDIT_EVENT or (event == 35 and button == EDIT_BUTTON):
            changed = edit_object(handle)
            vs.vsoSetEventResult(0 if changed else -5)
        elif event == 35 and button == RESET_TEXT_BUTTON:
            reset_note(handle)
            vs.vsoSetEventResult(0)
        elif event == 35 and button == PATH_BUTTON:
            changed = replace_path(handle)
            vs.vsoSetEventResult(0 if changed else -5)
    except Exception as exc:
        vs.AlrtDialog("PD Treppe: " + str(exc) + "\nGegebenenfalls mit Rückgängig zurücksetzen.")
        raise
