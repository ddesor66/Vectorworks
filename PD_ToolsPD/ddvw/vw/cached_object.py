"""Native path PIO shell retaining a private copy of existing drawing geometry.

Only reset events copy the profile into the regenerable PIO container. Conversion
builds and verifies a replacement before the caller commits the old object.
"""
import json
import math
import uuid

import vs


DATA = "Daten"
EDIT = 1001


def read(handle, plugin):
    raw = vs.GetRField(handle, plugin, DATA)
    if not raw:
        return None
    data = json.loads(raw)
    if not isinstance(data, dict) or data.get("schema") != 1:
        raise ValueError("Unbekanntes Format des intelligenten PD-Objekts.")
    return data


def store(handle, plugin, data):
    raw = json.dumps(data, ensure_ascii=True, allow_nan=False, sort_keys=True)
    vs.SetRField(handle, plugin, DATA, raw)
    if vs.GetRField(handle, plugin, DATA) != raw:
        raise RuntimeError("Die Objektdaten konnten nicht vollständig gespeichert werden.")


def children(group):
    result, seen = [], set()
    child = vs.FInGroup(group)
    while child:
        key = str(child)
        if key in seen:
            raise RuntimeError("Ungültige Objektfolge in der Geometrie.")
        seen.add(key)
        result.append(child)
        child = vs.NextObj(child)
    return result


def profile(handle):
    group = vs.GetCustomObjectProfileGroup(handle)
    if not group or not children(group):
        raise RuntimeError("Die gesicherte Objektgeometrie fehlt.")
    return group


def regenerate(handle, plugin):
    original = vs.GetCustomObjectProfileGroup(handle)
    if not original and read(handle, plugin) is None:
        return  # Initial creation before parameters and profile are assigned.
    original = profile(handle)
    if not vs.CreateDuplicateObject(original, handle):
        raise RuntimeError("Die gespeicherte Geometrie konnte nicht angezeigt werden.")
    vs.SetParameterVisibility(handle, DATA, False)


def copy_records(source, target):
    for index in range(1, vs.NumRecords(source) + 1):
        record = vs.GetRecord(source, index)
        name = vs.GetName(record)
        vs.SetRecord(target, name)
        for field_index in range(1, vs.NumFields(record) + 1):
            field = vs.GetFldName(record, field_index)
            value = vs.GetRField(source, name, field)
            vs.SetRField(target, name, field, value)
            if vs.GetRField(target, name, field) != value:
                raise RuntimeError("Datensatz konnte nicht übernommen werden: " + name)


def align_profile(handle, source_box, origin):
    """VW centers an adopted profile; restore its original local drawing basis."""
    stored = profile(handle)
    vs.ResetBBox(stored)
    (left, top), (right, bottom) = source_box
    (pl, pt), (pr, pb) = vs.GetBBox(stored)
    tolerance = max(1e-7, abs(right-left)*1e-8, abs(top-bottom)*1e-8)
    if abs((pr-pl)-(right-left)) > tolerance or abs((pt-pb)-(top-bottom)) > tolerance:
        raise RuntimeError("Die Übernahme würde die Größe verändern; abgebrochen.")
    vs.HMove(stored, left-origin[0]-pl, bottom-origin[1]-pb)
    vs.ResetBBox(stored)
    actual = vs.GetBBox(stored)
    expected = tuple(tuple(v-origin[i] for i, v in enumerate(point)) for point in source_box)
    if any(abs(a-b) > tolerance for p, q in zip(actual, expected) for a, b in zip(p, q)):
        raise RuntimeError("Die Übernahme würde die Lage verändern; abgebrochen.")


def prepare(group, plugin, data):
    """Create a verified native replacement; never delete/rename the source."""
    if not group or vs.GetTypeN(group) != 11 or not children(group):
        raise ValueError("Nur eine nicht leere Zeichnungsgruppe kann übernommen werden.")
    (left, top), (right, bottom) = vs.GetBBox(group)
    if not all(math.isfinite(v) for v in (left, top, right, bottom)):
        raise ValueError("Die Geometrie hat ungültige Koordinaten.")
    origin = (left, bottom)
    payload = dict(data, schema=1, origin=list(origin))
    parent = vs.GetParent(group)
    clone = path = handle = None
    try:
        clone = vs.CreateDuplicateObject(group, parent)
        if not clone:
            raise RuntimeError("Die Sicherungskopie der Gruppe konnte nicht erstellt werden.")
        vs.HMove(clone, -origin[0], -origin[1])
        vs.BeginPoly()
        vs.AddPoint(origin)
        vs.AddPoint((origin[0] + 1.0, origin[1]))
        vs.EndPoly()
        path = vs.LNewObj()
        if not path:
            raise RuntimeError("Der native Objektpfad konnte nicht erstellt werden.")
        vs.SetFPat(path, 0)
        if not vs.DefineCustomObj(plugin, 0):
            raise RuntimeError("Die native Objektdefinition fehlt: " + plugin)
        handle = vs.CreateCustomObjectPath(plugin, path, clone)
        if handle:
            # CreateCustomObjectPath adopts both staging objects. Their handles
            # must not be queried or deleted after the PIO becomes their owner.
            path = clone = None
        if not handle or vs.GetTypeN(handle) != 86:
            raise RuntimeError("Der native PD-Objekttyp ist nicht korrekt installiert: " + plugin)
        if vs.GetParent(handle) != parent and not vs.SetParent(handle, parent):
            raise RuntimeError("Die ursprüngliche Ebene konnte nicht übernommen werden.")
        vs.SetClass(handle, vs.GetClass(group))
        copy_records(group, handle)
        store(handle, plugin, payload)
        align_profile(handle, ((left, top), (right, bottom)), origin)
        # PIO ResetObject is deferred in VW2026. Check the persisted geometry
        # and transform, not the still-empty display cache of the new PIO.
        local_box = vs.GetBBox(profile(handle))
        insertion = vs.GetSymLoc(handle)
        actual = tuple(tuple(v + insertion[i] for i, v in enumerate(point)) for point in local_box)
        expected = ((left, top), (right, bottom))
        tolerance = max(1e-7, abs(right-left)*1e-8, abs(top-bottom)*1e-8)
        if any(abs(a-b) > tolerance for p, q in zip(actual, expected) for a, b in zip(p, q)):
            raise RuntimeError("Die Übernahme würde die Lage oder Größe verändern; abgebrochen. "
                               "Soll=%r, Ist=%r" % (expected, actual))
        vs.ResetObject(handle)
        return handle
    except Exception:
        if handle:
            vs.DelObject(handle)
        # Only staging objects not adopted by a successfully returned PIO remain
        # ours. Never follow stale child handles after deleting that PIO.
        for temporary in (clone, path):
            if temporary and vs.GetTypeN(temporary) != 0 and vs.GetParent(temporary) == parent:
                vs.DelObject(temporary)
        raise


def commit(group, replacement):
    """Delete exactly the old group after the replacement passed validation."""
    name = vs.GetName(group)
    backup_name = "PD-Übernahme-" + uuid.uuid4().hex
    if name:
        vs.SetName(group, backup_name)
        try:
            vs.SetName(replacement, name)
            if vs.GetName(replacement) != name:
                raise RuntimeError("Der ursprüngliche Objektname konnte nicht übernommen werden.")
        except Exception:
            vs.SetName(replacement, "")
            vs.SetName(group, name)
            raise
    try:
        vs.DelObject(group)
        if name and vs.GetObject(backup_name):
            raise RuntimeError("Die ursprüngliche Gruppe konnte nicht ersetzt werden.")
    except Exception:
        if name:
            vs.SetName(replacement, "")
            vs.SetName(group, name)
        raise
    vs.SetSelect(replacement)
    return replacement


def initialize(button_text):
    vs.SetObjPropVS(7, True)  # no wall insertion
    vs.SetObjPropVS(8, True)  # custom Object Info palette
    vs.SetObjPropCharVS(3, chr(1))  # native special edit / double-click event
    vs.SetObjPropCharVS(11, chr(2))  # hide internal path vertex controls
    vs.vsoAppendWidget(12, EDIT, button_text, 0)


def event(plugin, edit):
    action, button = vs.vsoGetEventInfo()
    if action == 5:
        initialize("Beschriftung bearbeiten…" if plugin == "PD Beschriftungsobjekt" else "Mauer bearbeiten…")
        return
    valid, name, handle, _record, _wall = vs.GetCustomObjectInfo()
    if not valid or name != plugin or not handle:
        return
    try:
        if action == 3:
            regenerate(handle, plugin)
        elif action == 7 or (action == 35 and button == EDIT):
            changed = edit(handle)
            vs.vsoSetEventResult(0 if changed else -5)
    except Exception as error:
        vs.AlrtDialog(plugin + ": " + str(error))
        if action != 3:
            vs.vsoSetEventResult(-5)
        else:
            raise
