# -*- coding: utf-8 -*-
"""Defensive Vectorworks 2026 adapter.

Only this module imports ``vs``.  Geometry and naming rules stay testable in
the pure core modules.
"""

from __future__ import absolute_import

import hashlib
import math
import os
import time

import vs

from .core_quantities import (
    ObjectFact,
    ObjectKind,
    Path2D,
    Point2D,
    SourceKey,
)


VIS_VISIBLE = 0
VIS_HIDDEN = -1
VIS_GRAY = 2

TYPE_LINE = 2
TYPE_RECTANGLE = 3
TYPE_OVAL = 4
TYPE_POLYGON = 5
TYPE_ARC = 6
TYPE_GROUP = 11
TYPE_ROUNDED_RECTANGLE = 13
TYPE_SYMBOL = 15
TYPE_SYMBOL_DEFINITION = 16
TYPE_POLYLINE = 21
TYPE_VIEWPORT = 122
TYPE_RECORD_FORMAT = 47

# Resource/control nodes can carry a class but are not placed drawing
# elements. They must never make a class or layer appear occupied.
NON_DRAWING_OBJECT_TYPES = frozenset((
    0, TYPE_SYMBOL_DEFINITION, 18, 19, 31, 41, TYPE_RECORD_FORMAT,
    48, 49, 51, 66,
))

VP_NEEDS_UPDATE = 1004

# Curved polylines are sampled without creating temporary Vectorworks
# geometry.  Vectorworks 2026 documents PointAlongPolyN(h, dist, epsilon) as a
# non-mutating distance-along-poly query.  The adaptive chord check below must
# meet this deviation in SI units; otherwise no comparison path is returned.
CURVE_SAMPLE_TOLERANCE_M = 0.0001
CURVE_SAMPLE_SEED_SPAN_M = 2.0
CURVE_SAMPLE_MIN_SEGMENTS = 16
CURVE_SAMPLE_MAX_POINTS = 16385
CURVE_SAMPLE_MAX_REFINEMENTS = 12

_NO_DEFAULT = object()


def _call(name, *args, **kwargs):
    default = kwargs.pop("default", _NO_DEFAULT)
    try:
        return getattr(vs, name)(*args)
    except Exception:
        if default is _NO_DEFAULT:
            raise
        return default


def alert(message, title=None):
    text = str(message)
    if title:
        text = str(title) + "\n\n" + text
    _call("AlrtDialog", text)


def info(message):
    _call("Message", str(message))


def redraw():
    if _call("ReDrawAll", default=None) is None:
        _call("ReDraw")


def document_key():
    path = str(_call("GetFPathName", default="") or "").strip()
    if path:
        return os.path.normcase(os.path.abspath(path))
    name = str(_call("GetFName", default="Unbenannt") or "Unbenannt")
    return "UNSAVED:" + name


def document_path():
    return str(_call("GetFPathName", default="") or "").strip()


def choose_save_path(prompt, default_name):
    value = _call("PutFile", str(prompt), str(default_name), default="")
    if bool(_call("DidCancel", default=False)):
        return ""
    return str(value or "").strip()


def now_timestamp():
    return int(time.time())


def _attached_record_names(handle, strict=False):
    names = set()
    query = (lambda name, *args, **kw: getattr(vs, name)(*args)) if strict else _call
    count = int(query("NumRecords", handle, default=0) or 0)
    for index in range(1, count + 1):
        record = query("GetRecord", handle, index, default=None)
        if not record:
            if strict:
                raise RuntimeError("Ein vorhandener Objektdatensatz konnte nicht gelesen werden.")
            continue
        name = str(query("GetName", record, default="") or "")
        if strict and not name:
            raise RuntimeError("Der Name eines vorhandenen Objektdatensatzes ist nicht lesbar.")
        if name:
            names.add(name)
    return names


def _ensure_record_format(record_name, field_specs):
    """Create or extend one visible Vectorworks record format."""

    record_name = str(record_name or "").strip()
    if not record_name:
        raise ValueError("Der Name der Vectorworks-Datenbank fehlt.")
    record = _call("GetObject", record_name, default=None)
    if record and int(_call("GetTypeN", record, default=0) or 0) != TYPE_RECORD_FORMAT:
        raise RuntimeError(
            "Im Dokument existiert bereits eine andere Ressource mit dem "
            "Namen „%s“." % record_name)
    existing = set()
    if record:
        for index in range(1, int(_call("NumFields", record, default=0) or 0) + 1):
            name = str(_call("GetFldName", record, index, default="") or "")
            if name:
                existing.add(name)
    for field_name, default_value, field_type, field_flag in field_specs:
        if field_name not in existing:
            _call(
                "NewField", record_name, str(field_name), str(default_value),
                int(field_type), int(field_flag))
    record = _call("GetObject", record_name, default=None)
    if (not record or
            int(_call("GetTypeN", record, default=0) or 0) != TYPE_RECORD_FORMAT):
        raise RuntimeError(
            "Das Vectorworks-Datenbankformat „%s“ konnte nicht erstellt "
            "werden." % record_name)
    actual = set(
        str(_call("GetFldName", record, index, default="") or "")
        for index in range(
            1, int(_call("NumFields", record, default=0) or 0) + 1)
    )
    missing = [spec[0] for spec in field_specs if spec[0] not in actual]
    if missing:
        raise RuntimeError(
            "Im Vectorworks-Datenbankformat fehlen Felder: %s" %
            ", ".join(missing))
    return record


def write_object_records(record_name, field_specs, values_by_object_id):
    """Attach and verify mass records; restore every touched object on error."""

    field_specs = tuple(field_specs or ())
    field_names = tuple(spec[0] for spec in field_specs)
    if not field_specs or len(set(field_names)) != len(field_names):
        raise ValueError("Die Vectorworks-Datenbankfelder sind ungültig.")
    _ensure_record_format(record_name, field_specs)

    snapshots = []
    missing_ids = []
    linked = 0
    try:
        for object_id in sorted(values_by_object_id, key=str):
            handle = _call("GetObjectByUuid", str(object_id), default=None)
            if not handle:
                missing_ids.append(str(object_id))
                continue
            had_record = record_name in _attached_record_names(handle, strict=True)
            previous = dict(
                (field_name, _record_value(
                    handle, record_name, field_name))
                for field_name in field_names
            ) if had_record else {}
            snapshots.append((handle, had_record, previous))
            if not had_record:
                vs.SetRecord(handle, record_name)
                if record_name not in _attached_record_names(handle, strict=True):
                    raise RuntimeError(
                        "Die Datenbank konnte nicht mit Objekt %s verknüpft "
                        "werden." % object_id)
            supplied = values_by_object_id[object_id]
            for field_name, default_value, _field_type, _field_flag in field_specs:
                value = str(supplied.get(field_name, default_value) or "")
                vs.SetRField(handle, record_name, field_name, value)
                actual = str(vs.GetRField(handle, record_name, field_name))
                if actual != value:
                    raise RuntimeError(
                        "Das Datenbankfeld „%s“ konnte für Objekt %s nicht "
                        "bestätigt werden." % (field_name, object_id))
            linked += 1
    except Exception as error:
        rollback_errors = []
        for handle, had_record, previous in reversed(snapshots):
            try:
                if had_record:
                    for field_name, value in previous.items():
                        vs.SetRField(handle, record_name, field_name, value)
                        if str(vs.GetRField(handle, record_name, field_name)) != value:
                            raise RuntimeError("Rücklesen fehlgeschlagen: " + field_name)
                else:
                    vs.DelRecord(handle, record_name)
                    if record_name in _attached_record_names(handle, strict=True):
                        raise RuntimeError("Neue Verknüpfung blieb bestehen.")
            except Exception as rollback_error:
                rollback_errors.append(str(rollback_error))
        detail = ""
        if rollback_errors:
            detail = " Rücksetzung unvollständig: " + "; ".join(rollback_errors)
        raise RuntimeError(
            "Die objektbezogene Vectorworks-Datenbank konnte nicht vollständig "
            "geschrieben werden: %s.%s" % (error, detail))
    redraw()
    return {
        "record_name": str(record_name),
        "linked": linked,
        "missing_ids": tuple(missing_ids),
    }


def class_names():
    count = int(_call("ClassNum", default=0) or 0)
    values = []
    for index in range(1, count + 1):
        name = str(_call("ClassList", index, default="") or "")
        if name:
            values.append(name)
    return tuple(sorted(set(values), key=lambda value: value.casefold()))


def layer_records():
    records = []
    handle = _call("FLayer")
    seen = set()
    while handle and str(handle) not in seen:
        seen.add(str(handle))
        # Selector 154 == 1 identifies a design layer. Sheet layers are not
        # valid quantity/filter targets for this tool suite.
        if int(_call("GetObjectVariableInt", handle, 154, default=1) or 0) != 1:
            handle = _call("NextLayer", handle)
            continue
        name = str(_call("GetLName", handle, default="") or "")
        if name:
            layer_id = object_uuid(handle) or "LAYER:" + name
            visibility = int(_call("GetLVis", handle, default=VIS_VISIBLE))
            records.append({
                "id": layer_id,
                "name": name,
                "visibility": visibility,
                "handle": handle,
            })
        handle = _call("NextLayer", handle)
    records.sort(key=lambda item: item["name"].casefold())
    return tuple(records)


def layer_names():
    return tuple(record["name"] for record in layer_records())


def occupied_class_layer_names():
    """Return only classes and design layers containing placed objects.

    Group contents are visited recursively because their child objects may
    use classes different from the enclosing group.  Empty design layers,
    unused classes and resource definitions never enter the selection lists.
    """
    classes = set()
    layers = set()
    visited = set()

    def visit_chain(handle, layer_name):
        while handle:
            marker = str(handle)
            if marker in visited:
                break
            visited.add(marker)
            object_type = int(_call("GetTypeN", handle, default=0) or 0)
            if object_type not in NON_DRAWING_OBJECT_TYPES:
                class_name = str(
                    _call("GetClass", handle, default="") or "").strip()
                if class_name:
                    classes.add(class_name)
                if layer_name:
                    layers.add(layer_name)
            if object_type == TYPE_GROUP:
                child = _call("FInGroup", handle, default=None)
                if child:
                    visit_chain(child, layer_name)
            handle = _call("NextObj", handle, default=None)

    for record in layer_records():
        first = _call("FInLayer", record["handle"], default=None)
        if first:
            visit_chain(first, record["name"])
    return (
        tuple(sorted(classes, key=str.casefold)),
        tuple(sorted(layers, key=str.casefold)),
    )


def all_layer_names():
    """Return design and sheet layer names for active-layer restoration."""
    values = []
    handle = _call("FLayer")
    seen = set()
    while handle and str(handle) not in seen:
        seen.add(str(handle))
        name = str(_call("GetLName", handle, default="") or "")
        if name:
            values.append(name)
        handle = _call("NextLayer", handle)
    return tuple(values)


def object_uuid(handle):
    value = str(_call("GetObjectUuid", handle, default="") or "")
    return value.strip()


def active_layer_name():
    handle = _call("ActLayer")
    return str(_call("GetLName", handle, default="") or "") if handle else ""


def active_class_name():
    return str(_call("ActiveClass", default="") or "")


def selected_viewports():
    """Return selected viewport handles without changing the selection."""
    values = []

    def collect(handle):
        if int(_call("GetTypeN", handle, default=0) or 0) == TYPE_VIEWPORT:
            values.append(handle)
        return False

    _call("ForEachObject", collect, "((SEL=TRUE) & (T=VIEWPORT))")
    return tuple(values)


def _viewport_visibility_snapshot(viewport):
    classes = {}
    for name in class_names():
        result = _call(
            "GetVPClassVisibility", viewport, name,
            default=(False, VIS_HIDDEN))
        if isinstance(result, (tuple, list)) and len(result) >= 2 and result[0]:
            classes[name] = int(result[1])
    layers = {}
    for record in layer_records():
        result = _call(
            "GetVPLayerVisibility", viewport, record["handle"],
            default=(False, VIS_HIDDEN))
        if isinstance(result, (tuple, list)) and len(result) >= 2 and result[0]:
            layers[record["name"]] = int(result[1])
    return {
        "uuid": object_uuid(viewport),
        "classes": classes,
        "layers": layers,
    }


def _set_viewport_visibility(viewport, classes, layers):
    """Apply exact class/layer override maps to one existing viewport."""
    available_classes = set(class_names())
    records = dict((record["name"], record) for record in layer_records())
    for name, visibility in classes.items():
        if name in available_classes:
            if not _call(
                    "SetVPClassVisibility", viewport, name, int(visibility),
                    default=False):
                raise RuntimeError(
                    "Ansichtsbereich-Klassensichtbarkeit konnte nicht gesetzt werden: "
                    + name)
    for name, visibility in layers.items():
        record = records.get(name)
        if record is not None:
            if not _call(
                    "SetVPLayerVisibility", viewport, record["handle"],
                    int(visibility), default=False):
                raise RuntimeError(
                    "Ansichtsbereich-Ebenensichtbarkeit konnte nicht gesetzt werden: "
                    + name)
    _call("SetObjectVariableBoolean", viewport, VP_NEEDS_UPDATE, True)


def capture_visibility():
    snapshot = {
        "classes": dict(
            (name, int(_call("GetCVis", name, default=VIS_VISIBLE)))
            for name in class_names()
        ),
        "layers": dict(
            (record["name"], int(record["visibility"]))
            for record in layer_records()
        ),
        "active_class": active_class_name(),
        "active_layer": active_layer_name(),
        "class_options": int(_call("GetClassOptions", default=5) or 5),
        "layer_options": int(_call("GetLayerOptions", default=5) or 5),
    }
    viewports = selected_viewports()
    if len(viewports) == 1:
        snapshot["viewport"] = _viewport_visibility_snapshot(viewports[0])
    return snapshot


def _set_class_visibility(name, visibility):
    if visibility == VIS_HIDDEN:
        _call("HideClass", name)
    elif visibility == VIS_GRAY:
        _call("GrayClass", name)
    else:
        _call("ShowClass", name)


def _activate_layer(name):
    handle = _call("GetLayerByName", name)
    if not handle:
        return False
    _call("Layer", name)
    return True


def activate_design_layer(name):
    """Activate an existing design layer without ever creating a new one."""
    if name not in set(layer_names()):
        return False
    return _activate_layer(name)


def _set_layer_visibility(name, visibility):
    # Vectorworks 2026 exposes layer visibility through the active-layer
    # ShowLayer/HideLayer/GrayLayer procedures, not a stable SetLVis call.
    if not _activate_layer(name):
        return False
    if visibility == VIS_HIDDEN:
        _call("HideLayer")
    elif visibility == VIS_GRAY:
        _call("GrayLayer")
    else:
        _call("ShowLayer")
    return True


def apply_visibility_snapshot(snapshot):
    available_classes = set(class_names())
    available_layers = set(layer_names())
    all_available_layers = set(all_layer_names())
    target_layer = snapshot.get("active_layer")
    if target_layer not in all_available_layers:
        target_layer = next(iter(sorted(available_layers)), "")
    target_class = snapshot.get("active_class")
    if target_class not in available_classes:
        target_class = next(iter(sorted(available_classes)), "")

    # Keep one valid layer active while other states are changed.
    if target_layer:
        _activate_layer(target_layer)
        _call("ShowLayer")
    if target_class:
        _call("ShowClass", target_class)
        _call("NameClass", target_class)

    for name, visibility in snapshot.get("classes", {}).items():
        if name in available_classes and name != target_class:
            _set_class_visibility(name, int(visibility))
    for name, visibility in snapshot.get("layers", {}).items():
        if name in available_layers and name != target_layer:
            _set_layer_visibility(name, int(visibility))

    if target_layer in available_layers:
        _set_layer_visibility(target_layer, int(
            snapshot.get("layers", {}).get(target_layer, VIS_VISIBLE)))
    if target_layer:
        _activate_layer(target_layer)
    if target_class:
        _set_class_visibility(target_class, int(
            snapshot.get("classes", {}).get(target_class, VIS_VISIBLE)))
        _call("NameClass", target_class)
    _call("SetClassOptions", int(snapshot.get("class_options", 5)))
    _call("SetLayerOptions", int(snapshot.get("layer_options", 5)))
    viewport_state = snapshot.get("viewport")
    if isinstance(viewport_state, dict):
        viewport = _call(
            "GetObjectByUuid", str(viewport_state.get("uuid") or ""),
            default=None)
        if (viewport and
                int(_call("GetTypeN", viewport, default=0) or 0) == TYPE_VIEWPORT):
            _set_viewport_visibility(
                viewport,
                viewport_state.get("classes") or {},
                viewport_state.get("layers") or {},
            )
    redraw()


def apply_visibility_action(selected_classes, selected_layers, action,
                            affect_classes=True, affect_layers=True):
    """Apply show/hide/toggle/only to exact resolved names."""
    selected_classes = set(selected_classes)
    selected_layers = set(selected_layers)
    all_classes = class_names()
    layers = layer_records()
    all_layers = tuple(record["name"] for record in layers)
    action = str(action)

    if action not in ("only", "hide", "show", "toggle"):
        raise ValueError("Unbekannte Sichtbarkeitsaktion: " + action)

    if affect_classes and action == "only" and not selected_classes:
        raise ValueError("Keine Klasse für 'nur Auswahl sichtbar' gewählt.")
    if affect_layers and action == "only" and not selected_layers:
        raise ValueError("Keine Ebene für 'nur Auswahl sichtbar' gewählt.")

    class_current = dict(
        (name, int(_call("GetCVis", name, default=VIS_VISIBLE)))
        for name in all_classes)
    layer_current = dict(
        (record["name"], int(record["visibility"])) for record in layers)
    class_options = int(_call("GetClassOptions", default=5) or 5)
    layer_options = int(_call("GetLayerOptions", default=5) or 5)
    viewports = selected_viewports()
    viewport = viewports[0] if len(viewports) == 1 else None
    viewport_state = (_viewport_visibility_snapshot(viewport)
                      if viewport else None)

    def build_plan(names, current, selected):
        plan = dict(current)
        for name in names:
            if action == "only":
                plan[name] = VIS_VISIBLE if name in selected else VIS_HIDDEN
            elif name not in selected:
                continue
            elif action == "show":
                plan[name] = VIS_VISIBLE
            elif action == "hide":
                plan[name] = VIS_HIDDEN
            else:  # toggle
                plan[name] = (VIS_HIDDEN if current[name] != VIS_HIDDEN
                              else VIS_VISIBLE)
        return plan

    class_plan = (build_plan(all_classes, class_current, selected_classes)
                  if affect_classes else class_current)
    layer_plan = (build_plan(all_layers, layer_current, selected_layers)
                  if affect_layers else layer_current)
    if viewport_state is not None:
        viewport_class_current = dict(
            (name, viewport_state["classes"].get(name, class_current[name]))
            for name in all_classes)
        viewport_layer_current = dict(
            (name, viewport_state["layers"].get(name, layer_current[name]))
            for name in all_layers)
        viewport_class_plan = (
            build_plan(all_classes, viewport_class_current, selected_classes)
            if affect_classes else {})
        viewport_layer_plan = (
            build_plan(all_layers, viewport_layer_current, selected_layers)
            if affect_layers else {})

    def valid_active(current_name, names, plan, kind, external_names=()):
        if current_name in external_names:
            return current_name
        if current_name in plan and plan[current_name] != VIS_HIDDEN:
            return current_name
        candidates = sorted(
            (name for name in names if plan.get(name) != VIS_HIDDEN),
            key=str.casefold)
        if candidates:
            return candidates[0]
        external = sorted(set(external_names), key=str.casefold)
        if external:
            return external[0]
        raise ValueError(
            "Vectorworks benötigt immer eine sichtbare aktive %s. "
            "Die gewählte Aktion würde alle %s ausblenden." % (kind, kind))

    target_class = (valid_active(active_class_name(), all_classes,
                                 class_plan, "Klasse")
                    if affect_classes else active_class_name())
    target_layer = (valid_active(active_layer_name(), all_layers,
                                 layer_plan, "Konstruktionsebene",
                                 set(all_layer_names()) - set(all_layers))
                    if affect_layers else active_layer_name())

    # Activate valid visible targets before hiding the previous active items.
    if affect_classes and target_class:
        _set_class_visibility(target_class, VIS_VISIBLE)
        _call("NameClass", target_class)
    if affect_layers and target_layer in layer_plan:
        _activate_layer(target_layer)
        _call("ShowLayer")

    if affect_classes:
        for name in all_classes:
            _set_class_visibility(name, class_plan[name])

    if affect_layers:
        for name in all_layers:
            _set_layer_visibility(name, layer_plan[name])

    if target_layer:
        _activate_layer(target_layer)
    if target_class:
        _call("NameClass", target_class)
    if viewport is not None:
        _set_viewport_visibility(
            viewport,
            viewport_class_plan,
            viewport_layer_plan,
        )
    if action == "only" and affect_classes:
        _call("SetClassOptions", 5)
    elif (affect_classes and action in ("show", "toggle") and
          any(name != target_class and
              class_plan.get(name) == VIS_VISIBLE
              for name in selected_classes) and
          class_options in (1, 2, 6)):
        # Active-only/gray global modes would keep a newly shown class hidden
        # or gray.  Option 3 is the least-permissive true "show others" mode.
        _call("SetClassOptions", 3)
    if action == "only" and affect_layers:
        _call("SetLayerOptions", 5)
    elif (affect_layers and action in ("show", "toggle") and
          any(name != target_layer and
              layer_plan.get(name) == VIS_VISIBLE
              for name in selected_layers) and
          layer_options in (1, 2, 6)):
        _call("SetLayerOptions", 3)
    redraw()


def selected_class_layer_names():
    classes = set()
    layers = set()
    design_layers = set(layer_names())
    seen = set()

    def add_viewport_sources(viewport):
        state = _viewport_visibility_snapshot(viewport)
        classes.update(
            name for name, visibility in state["classes"].items()
            if int(visibility) != VIS_HIDDEN)
        layers.update(
            name for name, visibility in state["layers"].items()
            if int(visibility) != VIS_HIDDEN)

    def add_design_object(handle):
        marker = str(handle)
        if marker in seen:
            return
        seen.add(marker)
        object_type = int(_call("GetTypeN", handle, default=0) or 0)
        if object_type == TYPE_VIEWPORT:
            add_viewport_sources(handle)
            return
        layer = _call("GetLayer", handle)
        layer_name = str(_call("GetLName", layer, default="") or "") if layer else ""
        if layer_name not in design_layers:
            return
        class_name = str(_call("GetClass", handle, default="") or "")
        if class_name:
            classes.add(class_name)
        layers.add(layer_name)
        if object_type == TYPE_GROUP:
            child = _call("FInGroup", handle)
            while child:
                add_design_object(child)
                child = _call("NextObj", child)

    def collect(handle):
        add_design_object(handle)
        return False

    try:
        vs.ForEachObject(collect, "(SEL=TRUE)")
    except Exception:
        try:
            vs.ForEachObjectInLayer(collect, 2, 2, 1)
        except Exception:
            pass
    return (
        tuple(sorted(classes, key=str.casefold)),
        tuple(sorted(layers, key=str.casefold)),
    )


def object_class_layer_names(object_ids):
    """Resolve current classes/design layers for UUIDs without mutation."""
    classes = set()
    layers = set()
    design_layers = set(layer_names())
    for object_id in object_ids:
        handle = _call("GetObjectByUuid", object_id)
        if not handle:
            continue
        class_name = str(_call("GetClass", handle, default="") or "")
        layer = _call("GetLayer", handle)
        layer_name = (str(_call("GetLName", layer, default="") or "")
                      if layer else "")
        if class_name:
            classes.add(class_name)
        if layer_name in design_layers:
            layers.add(layer_name)
    return (
        tuple(sorted(classes, key=str.casefold)),
        tuple(sorted(layers, key=str.casefold)),
    )


def _units_to_si():
    values = _call("GetUnits", default=None)
    try:
        units_per_inch = float(values[3])
    except (TypeError, ValueError, IndexError):
        units_per_inch = 0.0254
    if not math.isfinite(units_per_inch) or units_per_inch <= 0:
        units_per_inch = 0.0254
    length_factor = 0.0254 / units_per_inch
    return length_factor, length_factor * length_factor


def _point(value):
    if isinstance(value, (tuple, list)) and len(value) >= 2:
        try:
            x = float(value[0])
            y = float(value[1])
        except (TypeError, ValueError):
            return None
        if math.isfinite(x) and math.isfinite(y):
            return x, y
    return None


def _line_points(handle):
    first = _point(_call("GetSegPt1", handle))
    second = _point(_call("GetSegPt2", handle))
    if first is not None and second is not None:
        return first, second
    first = _point(_call("Get2DPt", handle, 0))
    second = _point(_call("Get2DPt", handle, 1))
    if first is not None and second is not None:
        return first, second
    return None


def _poly_points(handle, object_type):
    count = int(_call("GetVertNum", handle, default=0) or 0)
    if count < 2:
        return (), False
    points = []
    curved = False
    for index in range(1, count + 1):
        if object_type == TYPE_POLYLINE:
            raw = _call("GetPolylineVertex", handle, index)
            point = _point(raw[0]) if isinstance(raw, (tuple, list)) and raw else None
            if isinstance(raw, (tuple, list)) and len(raw) > 1:
                try:
                    curved = curved or int(raw[1]) != 0
                except (TypeError, ValueError):
                    curved = True
        else:
            point = _point(_call("GetPolyPt", handle, index))
            if point is None:
                point = _point(_call("Get2DPt", handle, index - 1))
        if point is None:
            return (), curved
        points.append(point)
    return tuple(points), curved


class _CurveSamplingError(RuntimeError):
    pass


def _point_segment_distance(point, first, second):
    delta_x = second[0] - first[0]
    delta_y = second[1] - first[1]
    squared_length = delta_x * delta_x + delta_y * delta_y
    if squared_length <= 0.0:
        return math.hypot(point[0] - first[0], point[1] - first[1])
    factor = ((point[0] - first[0]) * delta_x
              + (point[1] - first[1]) * delta_y) / squared_length
    factor = min(1.0, max(0.0, factor))
    projected_x = first[0] + factor * delta_x
    projected_y = first[1] + factor * delta_y
    return math.hypot(point[0] - projected_x, point[1] - projected_y)


def _next_power_of_two(value):
    value = max(1, int(value))
    return 1 << (value - 1).bit_length()


def _sample_curved_poly(handle, raw_points, perimeter, length_factor, closed):
    """Approximate a curved 2D poly with an explicitly verified tolerance.

    The installed Vectorworks 2026 Script Reference documents
    ``PointAlongPolyN(h, dist, epsilon) -> (BOOLEAN, pt, tangent)`` and
    ``HPerimN`` as the more accurate polyline perimeter query.  Sampling uses
    only those read-only calls.  Starting with deterministic, power-of-two
    arclength intervals, every interval is checked at its quarter, midpoint
    and three-quarter stations.  The arc/chord test uses the triangle-
    inequality bound ``h <= 0.5 * sqrt(s**2 - c**2)``.  It therefore bounds
    *every* point of an interval by 0.1 mm, including oscillations hidden
    between the sampled stations.  Quarter stations remain a useful early
    rejection for ordinary S/Bezier segments whose midpoint crosses the
    chord.
    Refinement is global so identical reversed curves get the same stations.

    A failed API query or an unresolved interval raises instead of returning a
    coarse path.  The caller then keeps the native quantity but blocks any
    automatic exact/parallel reduction for that object.
    """

    try:
        perimeter = float(perimeter)
        length_factor = float(length_factor)
    except (TypeError, ValueError):
        raise _CurveSamplingError("ungültige Kurvenlänge")
    if (not math.isfinite(perimeter) or perimeter <= 0.0
            or not math.isfinite(length_factor) or length_factor <= 0.0):
        raise _CurveSamplingError("ungültige Kurvenlänge")

    tolerance_doc = CURVE_SAMPLE_TOLERANCE_M / length_factor
    seed_span_doc = CURVE_SAMPLE_SEED_SPAN_M / length_factor
    required_segments = max(
        CURVE_SAMPLE_MIN_SEGMENTS,
        int(math.ceil(perimeter / seed_span_doc)),
    )
    segment_count = _next_power_of_two(required_segments)
    if segment_count + 1 > CURVE_SAMPLE_MAX_POINTS:
        raise _CurveSamplingError("Kurve überschreitet das sichere Punktlimit")

    start_point = raw_points[0] if raw_points else None
    end_point = (start_point if closed else raw_points[-1]) if raw_points else None
    if start_point is None or end_point is None:
        raise _CurveSamplingError("Kurvenendpunkte fehlen")

    def point_at(distance):
        if distance <= tolerance_doc:
            return start_point
        if perimeter - distance <= tolerance_doc:
            return end_point
        try:
            result = _call("PointAlongPolyN", handle, distance, tolerance_doc)
        except Exception as error:
            raise _CurveSamplingError(
                "PointAlongPolyN-Aufruf fehlgeschlagen: %s" % str(error))
        if not isinstance(result, (tuple, list)) or len(result) < 2 or not bool(result[0]):
            raise _CurveSamplingError("PointAlongPolyN lieferte keinen Punkt")
        point = _point(result[1])
        if point is None:
            raise _CurveSamplingError("PointAlongPolyN lieferte ungültige Koordinaten")
        return point

    # Uniform global refinement makes the representation independent of the
    # original vertex subdivision.  It also gives the core parallel checker a
    # stable station correspondence for offset curves.
    for _refinement in range(CURVE_SAMPLE_MAX_REFINEMENTS + 1):
        if segment_count + 1 > CURVE_SAMPLE_MAX_POINTS:
            raise _CurveSamplingError("Kurve überschreitet das sichere Punktlimit")
        step = perimeter / float(segment_count)
        # Four sub-stations per interval provide a real recursive interval
        # check instead of the unsafe single-midpoint test.  Global doubling
        # repeats the same check on each half interval until all pass.
        check_divisions = 4
        query_point_count = segment_count * check_divisions + 1
        if query_point_count > CURVE_SAMPLE_MAX_POINTS:
            raise _CurveSamplingError(
                "Kurve überschreitet das sichere Abfragelimit")
        check_step = step / float(check_divisions)
        check_points = [
            point_at(check_step * index)
            for index in range(query_point_count)
        ]
        points = check_points[::check_divisions]
        within_tolerance = True
        for index in range(segment_count):
            first = points[index]
            second = points[index + 1]
            chord = math.hypot(second[0] - first[0], second[1] - first[1])
            arc_chord_excess = max(0.0, step - chord)
            # For any point P on an A-B curve with total arclength s, chord
            # c and perpendicular distance h from AB:
            #   s >= |A-P| + |P-B| >= sqrt(c^2 + 4h^2).
            # Requiring s-c below this stable threshold proves h <= epsilon;
            # a fixed ``s-c <= epsilon`` check cannot provide that guarantee.
            maximum_excess = (
                4.0 * tolerance_doc * tolerance_doc /
                (math.sqrt(chord * chord
                           + 4.0 * tolerance_doc * tolerance_doc) + chord)
            )
            offset = index * check_divisions
            deviations = (
                _point_segment_distance(
                    check_points[offset + station], first, second)
                for station in range(1, check_divisions)
            )
            if (any(value > tolerance_doc for value in deviations)
                    or arc_chord_excess > maximum_excess):
                within_tolerance = False
                break
        if within_tolerance:
            if closed and len(points) > 1:
                points.pop()
            minimum = 3 if closed else 2
            if len(points) < minimum:
                raise _CurveSamplingError("zu wenige Kurvenstützpunkte")
            return tuple(points)
        segment_count *= 2
    raise _CurveSamplingError("Abweichung konnte nicht sicher eingehalten werden")


def _source_key(handle, element_kind="geometry", element_name="Geometrie"):
    class_name = str(_call("GetClass", handle, default="") or "None") or "None"
    layer = _call("GetLayer", handle)
    layer_name = str(_call("GetLName", layer, default="") or "Unbekannte Ebene")
    layer_id = object_uuid(layer) if layer else ""
    return SourceKey(
        class_name, layer_id or "LAYER:" + layer_name, layer_name,
        element_kind, element_name)


def _fact_id(handle):
    return object_uuid(handle) or "HANDLE:" + str(handle)


_STRUCTURE_TYPE_LABELS = {
    TYPE_LINE: "Linie",
    TYPE_RECTANGLE: "Rechteck",
    TYPE_OVAL: "Kreis/Oval",
    TYPE_POLYGON: "Polygon",
    TYPE_ARC: "Kreisbogen",
    TYPE_GROUP: "Gruppe",
    TYPE_ROUNDED_RECTANGLE: "Abgerundetes Rechteck",
    TYPE_SYMBOL: "Symbol",
    TYPE_POLYLINE: "Polylinie",
}


def _group_structure(handle, length_factor, area_factor, ancestors=()):
    """Return a translation-independent structural signature and summary.

    Vectorworks groups have no definition resource comparable to a symbol.
    A user-assigned object name is therefore the primary group type.  For an
    unnamed group this signature groups repeated copies with the same direct
    content, dimensions and nested structure without using object UUIDs or
    insertion coordinates.
    """

    identity = _fact_id(handle)
    if identity in ancestors:
        return (("cycle",),), ("verschachtelte Gruppe",)
    entries = []
    labels = []
    child = _call("FInGroup", handle, default=None)
    seen = set()
    while child and str(child) not in seen:
        seen.add(str(child))
        object_type = int(_call("GetTypeN", child, default=0) or 0)
        class_name = str(_call("GetClass", child, default="") or "None")
        if object_type == TYPE_SYMBOL:
            symbol_name = str(
                _call("GetSymName", child, default="") or
                "Unbenanntes Symbol")
            entries.append(("symbol", symbol_name, class_name))
            labels.append("Symbol " + symbol_name)
        elif object_type == TYPE_GROUP:
            nested_name = str(_call("GetName", child, default="") or "").strip()
            if nested_name:
                entries.append(("group-name", nested_name, class_name))
                labels.append("Gruppe " + nested_name)
            else:
                nested, _nested_labels = _group_structure(
                    child, length_factor, area_factor,
                    tuple(ancestors) + (identity,))
                entries.append(("group", nested, class_name))
                labels.append("verschachtelte Gruppe")
        else:
            length = max(
                0.0,
                float(_call("HPerimN", child, default=0.0) or 0.0)
                * length_factor,
            )
            if length <= 0.0:
                length = max(
                    0.0,
                    float(_call("HLength", child, default=0.0) or 0.0)
                    * length_factor,
                )
            area = max(
                0.0,
                abs(float(_call("HAreaN", child, default=0.0) or 0.0))
                * area_factor,
            )
            entries.append((
                "object", object_type, class_name,
                round(length, 6), round(area, 6)))
            labels.append(
                _STRUCTURE_TYPE_LABELS.get(
                    object_type, "Objekttyp %d" % object_type))
        child = _call("NextObj", child, default=None)
    return tuple(sorted(entries, key=repr)), tuple(labels)


def _group_type_name(handle, length_factor, area_factor):
    assigned_name = str(_call("GetName", handle, default="") or "").strip()
    if assigned_name:
        return assigned_name
    structure, labels = _group_structure(handle, length_factor, area_factor)
    digest = hashlib.sha256(
        repr(structure).encode("utf-8")).hexdigest()[:8].upper()
    counts = {}
    for label in labels:
        counts[label] = counts.get(label, 0) + 1
    summary = ", ".join(
        ("%d× %s" % (count, label)) if count != 1 else label
        for label, count in sorted(counts.items(), key=lambda item: item[0].casefold())
    )
    if not summary:
        summary = "leer"
    if len(summary) > 58:
        summary = summary[:55].rstrip() + "…"
    return "%s [%s]" % (summary, digest)


def _axis_aligned_rectangle_path(handle, length_factor, measured_length_m):
    """Return a safe rectangle path only when its projected box is exact.

    ``GetBBox`` is documented as a screen-plane projection.  A rotated or
    otherwise transformed rectangle can therefore have a larger bounding-box
    perimeter than its actual perimeter.  The native ``HPerimN`` value is the
    guard that prevents such a projection from entering duplicate/parallel
    analysis as invented geometry.
    """

    bounds = _call("GetBBox", handle, default=None)
    if not isinstance(bounds, (tuple, list)) or len(bounds) != 2:
        return None
    try:
        first, second = bounds
        x1, y1 = float(first[0]), float(first[1])
        x2, y2 = float(second[0]), float(second[1])
    except (TypeError, ValueError, IndexError):
        return None
    if not all(math.isfinite(value) for value in (x1, y1, x2, y2)):
        return None
    left, right = sorted((x1 * length_factor, x2 * length_factor))
    bottom, top = sorted((y1 * length_factor, y2 * length_factor))
    if right - left <= 0.0 or top - bottom <= 0.0:
        return None
    path = Path2D(
        (
            Point2D(left, bottom),
            Point2D(right, bottom),
            Point2D(right, top),
            Point2D(left, top),
        ),
        True,
    )
    allowed_error = max(0.0001, measured_length_m * 0.000001)
    if abs(path.length_m - measured_length_m) > allowed_error:
        return None
    return path


def _measurement(handle, api, factor, warnings, fallback=0.0):
    try:
        raw = getattr(vs, api)(handle)
        if raw is None or isinstance(raw, bool):
            raise ValueError("kein Messwert")
        value = abs(float(raw)) * factor
        if not math.isfinite(value):
            raise ValueError("nicht endlicher Messwert")
        return value
    except Exception:
        warnings.append(
            "%s: Messwert nicht lesbar%s" %
            (api, "; geometrischer Ersatzwert" if fallback else
             "; 0 ist kein bestätigter Messwert"))
        return fallback


def _record_value(handle, record_name, field_name):
    value = vs.GetRField(handle, record_name, field_name)
    if value is None:
        raise RuntimeError("Datenbankfeld nicht lesbar: " + field_name)
    return str(value)


def _make_fact(handle, parent_ids, length_factor, area_factor):
    object_type = int(_call("GetTypeN", handle, default=0) or 0)
    fact_id = _fact_id(handle)
    warnings = []
    if object_type == TYPE_GROUP:
        source_key = _source_key(
            handle, "group",
            _group_type_name(handle, length_factor, area_factor))
        return ObjectFact(fact_id, source_key, ObjectKind.GROUP,
                          parent_ids=tuple(parent_ids))
    if object_type == TYPE_SYMBOL:
        symbol_name = str(_call("GetSymName", handle, default="") or "").strip()
        if not symbol_name:
            # Unknown symbol names must not merge unrelated placed resources.
            symbol_name = "Unbenanntes Symbol [%s]" % fact_id[-8:]
        source_key = _source_key(handle, "symbol", symbol_name)
        return ObjectFact(fact_id, source_key, ObjectKind.SYMBOL,
                          parent_ids=tuple(parent_ids))
    source_key = _source_key(handle)
    if object_type == TYPE_LINE:
        raw_points = _line_points(handle)
        if raw_points is None:
            warnings.append("Linienendpunkte konnten nicht gelesen werden")
            return ObjectFact(
                fact_id, source_key, ObjectKind.LINE,
                length_m=_measurement(handle, "HLength", length_factor, warnings),
                area_m2=0.0, parent_ids=tuple(parent_ids), warnings=tuple(warnings))
        path = Path2D(tuple(Point2D(x * length_factor, y * length_factor)
                            for x, y in raw_points), False)
        return ObjectFact(
            fact_id, source_key, ObjectKind.LINE, path=path,
            length_m=_measurement(handle, "HLength", length_factor, warnings, path.length_m),
            area_m2=0.0, parent_ids=tuple(parent_ids), warnings=tuple(warnings))
    native_2d_kinds = {
        TYPE_RECTANGLE: ObjectKind.RECTANGLE,
        TYPE_OVAL: ObjectKind.OVAL,
        TYPE_ARC: ObjectKind.ARC,
        TYPE_ROUNDED_RECTANGLE: ObjectKind.ROUNDED_RECTANGLE,
    }
    if object_type in native_2d_kinds:
        length = _measurement(handle, "HPerimN", length_factor, warnings)
        area = _measurement(handle, "HAreaN", area_factor, warnings)
        path = (
            _axis_aligned_rectangle_path(handle, length_factor, length)
            if object_type == TYPE_RECTANGLE
            else None
        )
        return ObjectFact(
            fact_id,
            source_key,
            native_2d_kinds[object_type],
            path=path,
            length_m=length,
            area_m2=area,
            parent_ids=tuple(parent_ids),
            warnings=tuple(warnings),
        )
    if object_type in (TYPE_POLYGON, TYPE_POLYLINE):
        raw_points, curved = _poly_points(handle, object_type)
        closed = bool(_call("IsPolyClosed", handle,
                            default=(object_type == TYPE_POLYGON)))
        raw_perimeter = _measurement(handle, "HPerimN", 1.0, warnings)
        path = None
        if raw_points and not curved and len(raw_points) >= (3 if closed else 2):
            path = Path2D(tuple(Point2D(x * length_factor, y * length_factor)
                                for x, y in raw_points), closed)
        if curved:
            try:
                sampled_points = _sample_curved_poly(
                    handle, raw_points, raw_perimeter, length_factor, closed)
                path = Path2D(
                    tuple(Point2D(x * length_factor, y * length_factor)
                          for x, y in sampled_points),
                    closed,
                )
                warnings.append(
                    "Kurvenprüfung: adaptive PointAlongPolyN-Abtastung "
                    "mit höchstens 0,1 mm Abweichung")
            except _CurveSamplingError as error:
                warnings.append(
                    "Kurvenprüfung blockiert: %s; keine automatische "
                    "Dubletten-/Parallelreduktion für dieses Objekt"
                    % str(error))
        length = raw_perimeter * length_factor
        if length <= 0.0 and path is not None:
            length = path.length_m
        area = (_measurement(handle, "HAreaN", area_factor, warnings)
                if closed else 0.0)
        return ObjectFact(
            fact_id, source_key,
            ObjectKind.POLYGON if object_type == TYPE_POLYGON else ObjectKind.POLYLINE,
            path=path, length_m=length, area_m2=area,
            parent_ids=tuple(parent_ids), warnings=tuple(warnings))
    if object_type == TYPE_SYMBOL_DEFINITION:
        return None
    generic_length = max(
        0.0,
        float(_call("HPerimN", handle, default=0.0) or 0.0)
        * length_factor,
    )
    if generic_length <= 0.0:
        generic_length = max(
            0.0,
            float(_call("HLength", handle, default=0.0) or 0.0)
            * length_factor,
        )
    generic_area = max(
        0.0,
        abs(float(_call("HAreaN", handle, default=0.0) or 0.0))
        * area_factor,
    )
    if generic_length > 0.0 or generic_area > 0.0:
        return ObjectFact(
            fact_id,
            source_key,
            ObjectKind.GENERIC_GEOMETRY,
            length_m=generic_length,
            area_m2=generic_area,
            parent_ids=tuple(parent_ids),
        )
    return ObjectFact(
        fact_id, source_key, ObjectKind.UNSUPPORTED,
        parent_ids=tuple(parent_ids),
        warnings=("Nicht ausgewerteter Vectorworks-Objekttyp %d" % object_type,))


def collect_object_facts(selected_classes=None, selected_layers=None):
    """Collect placed objects from every design layer, including groups.

    Symbol instances are counted as symbols and their definitions are not
    traversed, preventing definition/instance double counting.
    """
    class_filter = set(selected_classes or ())
    layer_filter = set(selected_layers or ())
    length_factor, area_factor = _units_to_si()
    facts = []
    skipped = {}

    def visit(handle, parents):
        while handle:
            object_type = int(_call("GetTypeN", handle, default=0) or 0)
            if object_type in NON_DRAWING_OBJECT_TYPES:
                handle = _call("NextObj", handle)
                continue
            source_key = _source_key(handle)
            included = ((not class_filter or source_key.class_name in class_filter) and
                        (not layer_filter or source_key.layer_name in layer_filter))
            fact = _make_fact(handle, parents, length_factor, area_factor)
            if fact is not None and included:
                facts.append(fact)
                if fact.kind == ObjectKind.UNSUPPORTED:
                    skipped[object_type] = skipped.get(object_type, 0) + 1
            elif fact is None and included and object_type != TYPE_SYMBOL_DEFINITION:
                skipped[object_type] = skipped.get(object_type, 0) + 1
            if object_type == TYPE_GROUP:
                group_id = _fact_id(handle)
                child = _call("FInGroup", handle)
                if child:
                    visit(child, tuple(parents) + (group_id,))
            handle = _call("NextObj", handle)

    layer = _call("FLayer")
    seen_layers = set()
    while layer and str(layer) not in seen_layers:
        seen_layers.add(str(layer))
        # Keep collection consistent with ``layer_names`` and the dialog's
        # explicit wording "Konstruktionsebene".  Sheet-layer annotations and
        # viewports must not silently enter a design-layer quantity result.
        if int(_call("GetObjectVariableInt", layer, 154, default=1) or 0) != 1:
            layer = _call("NextLayer", layer)
            continue
        first = _call("FInLayer", layer)
        if first:
            visit(first, ())
        layer = _call("NextLayer", layer)
    return tuple(facts), dict(sorted(skipped.items()))


def select_object_ids(object_ids, extra_parent_ids=()):
    # DSelectAll is layer-option dependent and can leave stale selections on
    # other layers. Traverse every placed object explicitly instead.
    def deselect_chain(handle):
        while handle:
            _call("SetDSelect", handle)
            if int(_call("GetTypeN", handle, default=0) or 0) == TYPE_GROUP:
                child = _call("FInGroup", handle)
                if child:
                    deselect_chain(child)
            handle = _call("NextObj", handle)

    layer = _call("FLayer")
    seen_layers = set()
    while layer and str(layer) not in seen_layers:
        seen_layers.add(str(layer))
        first = _call("FInLayer", layer)
        if first:
            deselect_chain(first)
        layer = _call("NextLayer", layer)
    selected = 0
    for object_id in list(object_ids) + list(extra_parent_ids):
        handle = _call("GetObjectByUuid", object_id)
        if handle:
            _call("SetSelect", handle)
            selected += 1
    redraw()
    return selected


def rename_classes(steps):
    """Apply core RenameStep values and verify each resulting class name."""
    for step in steps:
        result = _call("RenameClass", step.old_name, step.new_name)
        current = set(class_names())
        if (result is False or step.new_name not in current or
                step.old_name in current):
            raise RuntimeError(
                "Klasse konnte nicht umbenannt werden: %s → %s" %
                (step.old_name, step.new_name))
