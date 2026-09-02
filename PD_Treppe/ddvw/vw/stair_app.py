"""Menu entry: edit one selected stair or collect inputs and place a new stair."""

import math
from dataclasses import replace

import vs

from ..core.stair import StairError, StairSpec, calculate
from . import stair_dialog, stair_draw, stair_object, stair_source

_point_callback = None
_point_token = None


def _xy(point):
    if not isinstance(point, (tuple, list)) or len(point) < 2:
        raise StairError("Vectorworks hat keinen gültigen Einfügepunkt geliefert.")
    xy = tuple(float(value) for value in point[:2])
    if not all(math.isfinite(value) and abs(value) < 1e90 for value in xy):
        raise StairError("Vectorworks hat keinen gültigen Einfügepunkt geliefert.")
    return xy


def pick_insertion(spec):
    """Collect only a point during native tool events; create after tool cleanup.

    VW2026's Python temp tool is asynchronous. Retain the callback strongly;
    GetPt plus nested PIO creation crashed in the native insertion regression.
    Events 105/104/4 follow the already native-verified PD temp-tool contract.
    """
    global _point_callback, _point_token
    token = object()
    _point_token = token
    state = dict(point=None, complete=False, error=None)
    hint = "PD Treppe: Untere linke Ecke anklicken. Esc: abbrechen."

    def callback(action, _msg1, _msg2):
        global _point_token
        if _point_token is not token:
            return 0
        try:
            if action == 3:
                vs.vstSetHelpString(hint)
            elif action == 105 and state["point"] is None:
                state["point"] = _xy(vs.vstGetCurrPt2D())
            elif action == 104:
                state["complete"] = state["point"] is not None and not state["error"]
            elif action == 4:
                _point_token = None
                vs.SetTempToolHelpStr("")
                if state["error"]:
                    vs.AlrtDialog("PD Treppe: " + state["error"])
                elif state["complete"]:
                    preview_loop(spec, state["point"])
                return 0
            return 0 if state["point"] is not None or state["error"] else 1
        except Exception as exc:
            state["error"] = str(exc)
            if action == 4:
                _point_token = None
                vs.AlrtDialog("PD Treppe konnte nicht angelegt werden:\n" + str(exc))
            return 0

    _point_callback = callback
    vs.SetTempToolHelpStr(hint)
    try:
        vs.RunTempTool(False, callback)
    except Exception:
        _point_token = None
        vs.SetTempToolHelpStr("")
        raise


def create(spec, point, angle=0.0):
    spec = calculate(spec).spec
    point = _xy(point)
    # Resolve document units before starting a mutation.
    stair_draw.units_per_metre()
    vs.NameUndoEvent("PD Treppe anlegen")
    handle = vs.CreateCustomObjectN(stair_object.PLUGIN_NAME, point, angle, False)
    if not stair_object.is_stair(handle):
        raise StairError("Das native Objekt „PD Treppe.vso“ fehlt "
                         "oder ist nicht korrekt registriert.")
    try:
        stair_object._store(handle, spec, None)
        vs.ResetObject(handle)
    except Exception:
        # Only this newly created object is removed; never an existing stair or drawing.
        vs.DelObject(handle)
        raise
    vs.DSelectAll()
    vs.SetSelect(handle)
    vs.ReDrawAll()
    return handle


def preview_loop(spec, origin):
    """Keep a dashed drawing preview visible until accepted or cancelled."""
    current = calculate(spec).spec
    origin = _xy(origin)
    while True:
        result = calculate(current)
        group = stair_draw.preview(result, origin)
        vs.ReDrawAll()
        try:
            decision = stair_dialog.confirm_preview(result)
        finally:
            if group:
                vs.DelObject(group)
            vs.ReDrawAll()
        if decision == "accept":
            return create(current, origin)
        if decision != "edit":
            return None
        changed = stair_dialog.edit(current)
        if changed is None:
            return None
        current = changed


def run(insertion_point=None):
    global _point_token
    _point_token = None  # Ignore cleanup from an abandoned previous invocation.
    try:
        handle = vs.FSActLayer()
        if handle and stair_object.is_stair(handle):
            if vs.NextSObj(handle):
                raise StairError("Zum Bearbeiten bitte nur eine Treppe markieren.")
            stair_object.edit_object(handle)
            return
        initial, origin = StairSpec(), None
        if handle:
            if vs.NextSObj(handle):
                raise StairError("Bitte nur eine Ausgangslinie auswählen.")
            path, origin = stair_source.extract(handle)
            initial = replace(initial, path_points=path)
        else:
            mode = stair_dialog.source_mode()
            if mode is None:
                return
            if mode == "path":
                selected = stair_source.pick()
                if selected is None:
                    return
                path, origin = selected
                initial = replace(initial, path_points=path)
        spec = stair_dialog.edit(initial)
        if spec is None:
            return
        if origin is not None or insertion_point is not None:
            preview_loop(spec, origin if origin is not None else insertion_point)
            return
        pick_insertion(spec)
    except StairError as exc:
        vs.AlrtDialog(str(exc))


def run_tool():
    """Use the clicked path when present; otherwise use the click as insertion."""
    try:
        point = _xy(vs.vstGetCurrPt2D())
    except (StairError, TypeError, ValueError) as exc:
        vs.AlrtDialog("PD Treppe: " + str(exc))
        return
    try:
        source = vs.PickObject(point)
        initial, origin = StairSpec(), point
        if stair_source.is_supported(source):
            path, origin = stair_source.extract(source)
            initial = replace(initial, path_points=path)
        spec = stair_dialog.edit(initial)
        if spec is not None:
            preview_loop(spec, origin)
    except StairError as exc:
        vs.AlrtDialog("PD Treppe: " + str(exc))
