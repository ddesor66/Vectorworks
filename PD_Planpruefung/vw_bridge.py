# -*- coding: utf-8 -*-
"""Narrow, defensive adapter around the documented Vectorworks 2026 vs API."""

from __future__ import absolute_import

import math

import vs

from . import core_geometry as geometry


TYPE_LINE = 2
TYPE_RECTANGLE = 3
TYPE_OVAL = 4
TYPE_POLYGON = 5
TYPE_ARC = 6
TYPE_TEXT = 10
TYPE_GROUP = 11
TYPE_SYMBOL = 15
TYPE_ROUNDED_RECTANGLE = 13
TYPE_POLYLINE = 21
TYPE_SYMBOL_DEFINITION = 16
NON_DRAWING_OBJECT_TYPES = frozenset((
    0, TYPE_SYMBOL_DEFINITION, 18, 19, 31, 41, 47, 48, 49, 51, 66,
))
TYPE_LABELS = {
    TYPE_LINE: "Linie", TYPE_RECTANGLE: "Rechteck",
    TYPE_OVAL: "Kreis/Oval", TYPE_POLYGON: "Polygon",
    TYPE_ARC: "Kreisbogen", TYPE_TEXT: "Text", TYPE_GROUP: "Gruppe",
    TYPE_SYMBOL: "Symbol", TYPE_ROUNDED_RECTANGLE: "Abgerundetes Rechteck",
    TYPE_POLYLINE: "Polylinie",
}
ANNOTATION_LAYER = "Automatische Beschriftung"
BATCH_PREFIX = "PD_Beschriftung_"
LABEL_RECORD = "PD_Beschriftungsdaten"
LABEL_CONFIG_FIELD = "Konfiguration"
LAST_DUPLICATE_SKIPPED = 0
LAST_DUPLICATE_SCANNED = 0


def call(name, *args, **kwargs):
    default = kwargs.pop("default", None)
    function = getattr(vs, name, None)
    if function is None:
        return default
    try:
        value = function(*args)
        return default if value is None and default is not None else value
    except Exception:
        return default


def alert(message, title="PD Planprüfung"):
    try:
        vs.AlertInform(str(message), "", False)
    except Exception:
        vs.AlrtDialog(str(message))


def redraw():
    call("ReDrawAll")


def units_to_meters():
    values = call("GetUnits", default=None)
    try:
        units_per_inch = float(values[3])
    except (TypeError, ValueError, IndexError) as error:
        raise RuntimeError("Dokumenteinheiten konnten nicht gelesen werden.") from error
    if not math.isfinite(units_per_inch) or units_per_inch <= 0.0:
        raise RuntimeError("Ungültige Dokumenteinheiten; Prüfung abgebrochen.")
    return 0.0254 / units_per_inch


def point(value):
    if isinstance(value, (tuple, list)) and len(value) >= 2:
        try:
            return float(value[0]), float(value[1])
        except (TypeError, ValueError):
            return None
    return None


def bbox(handle):
    raw = call("GetBBox", handle, default=None)
    if not isinstance(raw, (tuple, list)) or len(raw) != 2:
        return None
    try:
        return geometry.bbox_normalized(raw)
    except (TypeError, ValueError, IndexError):
        return None


def line_points(handle):
    first, second = point(call("GetSegPt1", handle)), point(call("GetSegPt2", handle))
    if first is not None and second is not None:
        return first, second
    return ()


def poly_points(handle, object_type):
    count = int(call("GetVertNum", handle, default=0) or 0)
    values = []
    curved = False
    for index in range(1, count + 1):
        if object_type == TYPE_POLYLINE:
            raw = call("GetPolylineVertex", handle, index, default=None)
            candidate = point(raw[0]) if isinstance(raw, (tuple, list)) and raw else None
            if isinstance(raw, (tuple, list)) and len(raw) > 1:
                try:
                    curved = curved or int(raw[1]) != 0
                except (TypeError, ValueError):
                    curved = True
        else:
            candidate = point(call("GetPolyPt", handle, index, default=None))
        if candidate is None:
            return (), curved
        values.append(candidate)
    return tuple(values), curved


def layer_records():
    result = []
    layer = call("FLayer", default=None)
    seen = set()
    while layer and str(layer) not in seen:
        seen.add(str(layer))
        if int(call("GetObjectVariableInt", layer, 154, default=1) or 0) == 1:
            result.append((layer, str(call("GetLName", layer, default="") or "")))
        layer = call("NextLayer", layer, default=None)
    return tuple(result)


def iter_top_objects(exclude_annotation=False):
    for layer, layer_name in layer_records():
        if exclude_annotation and layer_name == ANNOTATION_LAYER:
            continue
        handle = call("FInLayer", layer, default=None)
        seen = set()
        while handle and str(handle) not in seen:
            seen.add(str(handle))
            yield handle, layer_name
            handle = call("NextObj", handle, default=None)


def iter_label_source_objects():
    """Yield label sources while excluding only managed label batches.

    Ordinary geometry may legitimately be drawn on the output layer.  Earlier
    releases skipped the complete layer and therefore hid those objects from
    both the occupied-class list and labeling.
    """
    for handle, layer_name in iter_top_objects(exclude_annotation=False):
        name = str(call("GetName", handle, default="") or "")
        if layer_name == ANNOTATION_LAYER and name.startswith(BATCH_PREFIX):
            continue
        yield handle, layer_name


def occupied_class_layers():
    counts = {}
    visited = set()

    def add_object(handle, layer_name):
        if not handle:
            return
        marker = str(handle)
        if marker in visited:
            return
        visited.add(marker)
        object_type = int(call("GetTypeN", handle, default=0) or 0)
        if object_type not in NON_DRAWING_OBJECT_TYPES:
            class_name = str(call("GetClass", handle, default="") or "")
            if class_name and layer_name:
                key = (class_name, layer_name)
                counts[key] = counts.get(key, 0) + 1
        if object_type == TYPE_GROUP:
            child = call("FInGroup", handle, default=None)
            while child:
                add_object(child, layer_name)
                child = call("NextObj", child, default=None)

    for handle, layer_name in iter_label_source_objects():
        add_object(handle, layer_name)
    return tuple(sorted(
        ((key[0], key[1], count) for key, count in counts.items()),
        key=lambda row: (row[0].casefold(), row[1].casefold())))


def class_names_with_objects():
    return tuple(sorted(
        set(row[0] for row in occupied_class_layers()), key=str.casefold))


def selected_class_layer_names():
    """Return classes/layers of drawing objects selected before a dialog.

    Vectorworks documents ``TrackObject`` as a one-object interactive call.
    Running it from a modal dialog callback is not a supported interaction
    chain. The labeling workflow therefore uses the normal selection tool
    first and reads the resulting selection here before opening its dialog.
    Selected groups contribute both their container class and the classes of
    their placed children, matching the visibility and quantity tools.
    """
    classes = set()
    layers = set()
    design_layers = set(name for _handle, name in layer_records() if name)
    seen = set()

    def add_object(handle):
        if not handle:
            return
        marker = str(handle)
        if marker in seen:
            return
        seen.add(marker)
        layer = call("GetLayer", handle, default=None)
        layer_name = (str(call("GetLName", layer, default="") or "")
                      if layer else "")
        if layer_name not in design_layers:
            return
        class_name = str(call("GetClass", handle, default="") or "").strip()
        if class_name:
            classes.add(class_name)
        layers.add(layer_name)
        if int(call("GetTypeN", handle, default=0) or 0) == TYPE_GROUP:
            child = call("FInGroup", handle, default=None)
            while child:
                add_object(child)
                child = call("NextObj", child, default=None)

    def collect(handle):
        add_object(handle)

    try:
        vs.ForEachObject(collect, "(SEL=TRUE)")
    except Exception:
        # This fallback also covers hosts that reject the criteria parser
        # while a group or symbol edit context is active.
        for handle, _layer_name in iter_top_objects():
            if bool(call("Selected", handle, default=False)):
                add_object(handle)
    return (
        tuple(sorted(classes, key=str.casefold)),
        tuple(sorted(layers, key=str.casefold)),
    )


def object_record(handle, layer_name):
    object_type = int(call("GetTypeN", handle, default=0) or 0)
    class_name = str(call("GetClass", handle, default="Keine") or "Keine")
    bounds = bbox(handle)
    points = ()
    closed = False
    curved = False
    if object_type == TYPE_LINE:
        points = line_points(handle)
    elif object_type in (TYPE_POLYGON, TYPE_POLYLINE):
        points, curved = poly_points(handle, object_type)
        closed = bool(call("IsPolyClosed", handle,
                           default=(object_type == TYPE_POLYGON)))
    return {
        "handle": handle, "type": object_type,
        "type_label": TYPE_LABELS.get(object_type, "Objekt %d" % object_type),
        "class_name": class_name, "layer_name": layer_name,
        "bbox": bounds, "points": tuple(points), "closed": closed,
        "curved": curved,
        "area": abs(float(call("HAreaN", handle, default=0.0) or 0.0)),
        "perimeter": abs(float(call("HPerimN", handle, default=0.0) or 0.0)),
    }


def _q(value, tolerance):
    try:
        return geometry.quantize(float(value), tolerance)
    except (TypeError, ValueError):
        return 0


def _child_signatures(group, tolerance, ancestry):
    marker = str(group)
    if marker in ancestry:
        return None
    values = []
    child = call("FInGroup", group, default=None)
    seen = set()
    while child and str(child) not in seen:
        seen.add(str(child))
        signature = object_signature(child, tolerance, ancestry + (marker,))
        if signature is None:
            return None
        values.append(signature)
        child = call("NextObj", child, default=None)
    return tuple(sorted(values, key=repr))


def object_signature(handle, tolerance, ancestry=()):
    object_type = int(call("GetTypeN", handle, default=0) or 0)
    class_name = str(call("GetClass", handle, default="Keine") or "Keine")
    bounds = bbox(handle)
    box = geometry.bbox_signature(bounds, tolerance) if bounds else ()
    angle = _q(call("HAngle", handle, default=0.0), 0.0001)
    if object_type == TYPE_LINE:
        points = line_points(handle)
        if len(points) != 2 or not all(math.isfinite(v) for p in points for v in p):
            return None
        return (class_name, "path", False, False,
                geometry.canonical_path(points, False, tolerance))
    if object_type in (TYPE_POLYGON, TYPE_POLYLINE):
        points, curved = poly_points(handle, object_type)
        if len(points) < 2 or not all(math.isfinite(v) for p in points for v in p):
            return None
        closed = bool(call("IsPolyClosed", handle,
                           default=(object_type == TYPE_POLYGON)))
        if curved:
            # Curve control vertices are not interchangeable with straight
            # corners. Do not simplify collinear Bezier/cubic control points.
            vertices = []
            for index in range(1, len(points) + 1):
                raw = call("GetPolylineVertex", handle, index, default=None)
                if not isinstance(raw, (tuple, list)) or len(raw) < 3:
                    return None
                try:
                    radius = float(raw[2])
                    if not math.isfinite(radius):
                        return None
                    vertices.append((geometry.quantized_point(points[index - 1], tolerance),
                                     int(raw[1]), _q(radius, tolerance)))
                except (TypeError, ValueError):
                    return None
            return (class_name, "typed_curve", closed, tuple(vertices))
        return (class_name, "path", closed, curved,
                geometry.canonical_path(points, closed, tolerance))
    if object_type == TYPE_TEXT:
        orientation = call("GetTextOrientation", handle, default=None)
        return (class_name, "text", str(call("GetText", handle, default="") or ""),
                box, repr(orientation))
    if object_type == TYPE_SYMBOL:
        location = point(call("GetSymLoc", handle, default=None)) or (0.0, 0.0)
        return (class_name, "symbol", str(call("GetSymName", handle, default="") or ""),
                geometry.quantized_point(location, tolerance), box, angle)
    if object_type == TYPE_GROUP:
        children = _child_signatures(handle, tolerance, ancestry)
        if not children:
            return None
        return (class_name, "group", box,
                children)
    if not bounds or object_type not in (TYPE_RECTANGLE, TYPE_OVAL):
        # Bounding box + area is not proof of equality for arbitrary objects,
        # rounded corners, arcs, plug-ins or solids.
        return None
    return (class_name, "object", object_type, box, angle,
            _q(call("HAreaN", handle, default=0.0), tolerance * tolerance),
            _q(call("HPerimN", handle, default=0.0), tolerance),
            str(call("GetName", handle, default="") or ""))


def duplicate_sets(tolerance_m=0.0001):
    global LAST_DUPLICATE_SKIPPED, LAST_DUPLICATE_SCANNED
    LAST_DUPLICATE_SKIPPED = LAST_DUPLICATE_SCANNED = 0
    factor = units_to_meters()
    tolerance = float(tolerance_m) / factor
    grouped = {}
    # Duplicate checking applies to the complete drawing.  The annotation
    # layer is excluded only while collecting source geometry for automatic
    # labels; users can also draw or copy ordinary geometry on that layer.
    for handle, layer_name in iter_top_objects(exclude_annotation=False):
        object_type = int(call("GetTypeN", handle, default=0) or 0)
        if object_type == TYPE_SYMBOL_DEFINITION:
            continue
        LAST_DUPLICATE_SCANNED += 1
        try:
            signature = object_signature(handle, tolerance)
        except (ValueError, TypeError, RuntimeError):
            signature = None
        if signature is None:
            LAST_DUPLICATE_SKIPPED += 1
            continue
        grouped.setdefault(signature, []).append(object_record(handle, layer_name))
    result = [tuple(records) for records in grouped.values() if len(records) > 1]
    return tuple(sorted(result, key=lambda group: (
        group[0]["class_name"].casefold(), group[0]["type_label"],
        repr(object_signature(group[0]["handle"], tolerance)))))


def deselect_all_objects():
    vs.DSelectAll()


def select_and_fit(records):
    deselect_all_objects()
    selected = 0
    for record in records:
        if record.get("handle"):
            call("SetSelect", record["handle"])
            selected += 1
    if selected:
        call("DoMenuTextByName", "Fit To Objects", 0)
    redraw()
    return selected


def delete_duplicates(records):
    deleted = 0
    for record in tuple(records)[1:]:
        handle = record.get("handle")
        if not handle:
            continue
        try:
            vs.DelObject(handle)
            record["handle"] = None
            deleted += 1
        except Exception:
            continue
    redraw()
    return deleted


def ensure_annotation_layer():
    existing = call("GetObject", ANNOTATION_LAYER, default=None)
    if existing and int(call("GetTypeN", existing, default=0) or 0) == 31:
        return existing
    return call("CreateLayer", ANNOTATION_LAYER, 1, default=None)


def collect_label_records(selected_classes, selected_layers=None):
    selected = set(selected_classes)
    layers = None if selected_layers is None else set(selected_layers)
    result = []
    for handle, layer_name in iter_label_source_objects():
        record = object_record(handle, layer_name)
        if (record["class_name"] in selected and
                (layers is None or layer_name in layers)):
            result.append(record)
    return tuple(result)


def path_label_positions(record, spacing):
    """Return exact on-path points and tangent angles for line-like objects."""
    points = tuple(record.get("points", ()))
    closed = bool(record.get("closed"))
    object_type = int(record.get("type", 0) or 0)
    if object_type == TYPE_LINE:
        return geometry.repeated_path_positions(points, spacing, False)
    length = abs(float(record.get("perimeter", 0.0) or 0.0))
    if object_type not in (TYPE_POLYGON, TYPE_POLYLINE) or length <= 1.0e-12:
        if record.get("curved"):
            return ()
        return geometry.repeated_path_positions(points, spacing, closed)
    spacing = max(float(spacing), length / 50.0, 1.0e-9)
    count = max(1, int(math.floor(length / spacing)))
    step = length / float(count)
    values = []
    for index in range(count):
        raw = call("PointAlongPolyN", record.get("handle"),
                   (index + 0.5) * step, max(length * 1.0e-7, 1.0e-9), default=None)
        if not isinstance(raw, (tuple, list)) or len(raw) < 3 or not raw[0]:
            return ()
        candidate = point(raw[1])
        tangent = point(raw[2])
        if (candidate is None or tangent is None or
                not all(math.isfinite(value) for value in candidate + tangent) or
                math.hypot(*tangent) <= 1.0e-12):
            return ()
        values.append((candidate, math.degrees(math.atan2(
            tangent[1], tangent[0]))))
    return tuple(values)


def active_layer_name():
    layer = call("ActLayer", default=None)
    return str(call("GetLName", layer, default="") or "") if layer else ""


def activate_layer(name):
    return call("Layer", str(name), default=None)


def active_layer_scale():
    layer = call("ActLayer", default=None)
    try:
        return max(1.0, float(call("GetLScale", layer, default=1.0) or 1.0))
    except (TypeError, ValueError):
        return 1.0


def _rgb(value, fallback):
    try:
        values = tuple(max(0, min(65535, int(component)))
                       for component in value)
    except (TypeError, ValueError):
        return tuple(fallback)
    return values if len(values) == 3 else tuple(fallback)


def create_text(label, origin, angle, point_size, class_name,
                text_color=(0, 0, 0), solid_fill=False,
                fill_color=(65535, 65535, 65535)):
    value = str(label)
    vs.TextOrigin(origin)
    vs.CreateText(value)
    handle = vs.LNewObj()
    if not handle:
        raise RuntimeError("Vectorworks hat kein Textobjekt erzeugt.")
    vs.SetTextStyleRef(handle, 0)
    font_id = int(vs.GetFontID("Arial") or 0)
    if font_id > 0:
        vs.SetTextFont(handle, 0, len(value), font_id)
    vs.SetTextSize(handle, 0, len(value), float(point_size))
    vs.SetTextStyle(handle, 0, len(value), 0)
    vs.SetTextJust(handle, 2)
    vs.SetTextVertAlignN(handle, 3)
    vs.SetTextOrientation(handle, origin, float(angle), False)
    vs.SetClass(handle, class_name)
    vs.SetPenFore(handle, _rgb(text_color, (0, 0, 0)))
    if solid_fill:
        color = _rgb(fill_color, (65535, 65535, 65535))
        vs.SetFPat(handle, 1)
        vs.SetFillFore(handle, color)
        vs.SetFillBack(handle, color)
    else:
        vs.SetFPat(handle, 0)
    return handle


def create_label_frame(origin, angle, width, height, frame_shape,
                       class_name, pen_color=(0, 0, 0),
                       fill_color=(65535, 65535, 65535)):
    """Create a filled circle or rotated rectangle centered on a label."""
    frame_shape = int(frame_shape or 0)
    if frame_shape == 0:
        return None
    x, y = float(origin[0]), float(origin[1])
    width, height = max(0.0, float(width)), max(0.0, float(height))
    if frame_shape == 1:
        radius = max(width, height) * 0.5
        vs.Oval((x - radius, y - radius), (x + radius, y + radius))
    elif frame_shape == 2:
        radians = math.radians(float(angle))
        ux, uy = math.cos(radians), math.sin(radians)
        vx, vy = -uy, ux
        corner_x = x - ux * width * 0.5 - vx * height * 0.5
        corner_y = y - uy * width * 0.5 - vy * height * 0.5
        vs.RectangleN(corner_x, corner_y, ux, uy, width, height)
    else:
        raise ValueError("Unbekannte Rahmenform: %s" % frame_shape)
    handle = vs.LNewObj()
    if not handle:
        raise RuntimeError("Vectorworks hat keinen Beschriftungsrahmen erzeugt.")
    line_color = _rgb(pen_color, (0, 0, 0))
    area_color = _rgb(fill_color, (65535, 65535, 65535))
    vs.SetClass(handle, class_name)
    vs.SetLSN(handle, 2)
    vs.SetPenFore(handle, line_color)
    vs.SetFPat(handle, 1)
    vs.SetFillFore(handle, area_color)
    vs.SetFillBack(handle, area_color)
    return handle


def write_label_metadata(group_handle, payload):
    """Attach verified persistent configuration to a label batch group."""
    record = call("GetObject", LABEL_RECORD, default=None)
    if not record:
        vs.NewField(LABEL_RECORD, LABEL_CONFIG_FIELD, "", 4, 0)
        record = call("GetObject", LABEL_RECORD, default=None)
    if not record:
        raise RuntimeError("Beschriftungsdatenbank konnte nicht erstellt werden.")
    vs.SetRecord(group_handle, LABEL_RECORD)
    vs.SetRField(group_handle, LABEL_RECORD, LABEL_CONFIG_FIELD, str(payload))
    stored = str(vs.GetRField(
        group_handle, LABEL_RECORD, LABEL_CONFIG_FIELD) or "")
    if stored != str(payload):
        raise RuntimeError("Beschriftungseinstellungen konnten nicht gespeichert werden.")


def read_label_metadata(group_handle):
    if not group_handle:
        return ""
    return str(call("GetRField", group_handle, LABEL_RECORD,
                    LABEL_CONFIG_FIELD, default="") or "")


def create_label_batch(placements, options, batch_name, metadata=""):
    placements = tuple(placements)
    if not placements:
        raise ValueError("Es wurden keine Beschriftungen zum Erzeugen übergeben.")
    names = tuple(batch_name if index == 0 else batch_name + "-L%05d" % index
                  for index in range(len(placements)))
    for name in names:
        if vs.GetObject(name):
            raise RuntimeError("Ein Beschriftungsname ist bereits vergeben: " + name)
    previous_layer = active_layer_name()
    layer = ensure_annotation_layer()
    if not layer:
        raise RuntimeError("Ebene 'Automatische Beschriftung' konnte nicht erstellt werden.")
    activate_layer(ANNOTATION_LAYER)
    created = 0
    group_handle = None
    native_labels = []
    try:
        from PD_ToolsPD.ddvw.vw import label_object
        for index, placement in enumerate(placements):
            try:
                vs.BeginGroup()
                try:
                    create_label_frame(
                        placement["point"], placement["angle"],
                        placement.get("frame_width", 0.0),
                        placement.get("frame_height", 0.0),
                        options.get("frame_shape", 0),
                        placement["class_name"],
                        options.get("frame_pen_color", (0, 0, 0)),
                        options.get("frame_fill_color", (65535, 65535, 65535)))
                    text = create_text(
                        placement["text"], placement["point"],
                        placement["angle"], options["point_size"],
                        placement["class_name"],
                        options.get("text_color", (0, 0, 0)),
                        options.get("solid_fill", False),
                        options.get("fill_color", (65535, 65535, 65535)))
                    if not text:
                        raise RuntimeError("Vectorworks hat keinen Beschriftungstext erzeugt.")
                finally:
                    vs.EndGroup()
                    group_handle = vs.LNewObj()
                if not group_handle:
                    raise RuntimeError("Vectorworks hat keine Beschriftungsgruppe erzeugt.")
                vs.SetClass(group_handle, placement["class_name"])
                vs.SetName(group_handle, names[index])
                if vs.GetName(group_handle) != names[index]:
                    raise RuntimeError("Beschriftungsname konnte nicht gesetzt werden: " + names[index])
                if metadata:
                    write_label_metadata(group_handle, metadata)
                native = label_object.convert(group_handle, batch_name)
                group_handle = None  # Source group was committed and deleted.
                native_labels.append(native)
                created += 1
            except Exception:
                if group_handle:
                    try:
                        vs.DelObject(group_handle)
                    except Exception:
                        pass
                    group_handle = None
                for native in native_labels:
                    try:
                        vs.DelObject(native)
                    except Exception:
                        pass
                native_labels = []
                raise
    finally:
        if previous_layer:
            activate_layer(previous_layer)
    redraw()
    return created, native_labels[0]


def delete_label_batch(name, handle):
    """Delete one exact batch and verify that its named object is gone."""
    if not handle:
        return False
    from PD_ToolsPD.ddvw.vw import label_object
    if label_object.batch_of(handle) == name:
        for member in label_object.batch_members(name):
            vs.DelObject(member)
        redraw()
        return not label_object.batch_members(name)
    try:
        vs.DelObject(handle)
    except Exception:
        return False
    redraw()
    return not bool(call("GetObject", str(name), default=None))


def last_label_batch():
    from PD_ToolsPD.ddvw.vw import label_object
    candidates = []
    for layer, layer_name in layer_records():
        if layer_name != ANNOTATION_LAYER:
            continue
        handle = call("FInLayer", layer, default=None)
        seen = set()
        while handle and str(handle) not in seen:
            seen.add(str(handle))
            name = str(call("GetName", handle, default="") or "")
            name = label_object.batch_of(handle) or name
            if name.startswith(BATCH_PREFIX):
                candidates.append((name, handle))
            handle = call("NextObj", handle, default=None)
    return max(candidates, key=lambda item: item[0]) if candidates else None


def delete_last_label_batch():
    candidate = last_label_batch()
    if not candidate:
        return None
    return candidate[0] if delete_label_batch(*candidate) else None
