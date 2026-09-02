# -*- coding: utf-8 -*-
"""Verified Vectorworks 2026 boundary, source, site-model and output adapter."""
from __future__ import absolute_import

import json
import math
import re
import uuid

import vs

from PD_ToolsPD.ddvw.vw import site_model

from . import core


TYPE_LINE = 2
TYPE_ARC = 6
TYPE_FREEHAND = 8
TYPE_LOCUS_3D = 9
TYPE_TEXT = 10
TYPE_POLYGON = 5
TYPE_POLYLINE = 21
TYPE_POLYGON_3D = 25
TYPE_GROUP = 11
TYPE_SYMBOL = 15
TYPE_LOCUS_2D = 17
TYPE_MESH = 40
TYPE_PARAMETRIC = 86
TYPE_NURBS_CURVE = 111
OBJECT_TYPE_NAMES = {
    2: "Linie", 3: "Rechteck", 4: "Oval", 5: "Polygon", 6: "Bogen",
    8: "Freihandlinie", 9: "3D-Punkt", 10: "Text", 11: "Gruppe",
    13: "Abgerundetes Rechteck", 15: "Symbol", 17: "2D-Punkt",
    21: "Polylinie", 24: "Extrusionskörper", 25: "3D-Polygon",
    40: "Mesh", 63: "Bemaßung", 86: "Plug-in-Objekt",
    111: "NURBS-Kurve", 113: "NURBS-Fläche",
}
MODEL_RECORD = "PD_GB_Modell"
MODEL_FIELD = "Daten"
OUTPUT_RECORD = "PD_GB_Ausgabe"
OUTPUT_FIELD = "Daten"
CLASS_SOURCE_POINT = "PD-GB-Quelldaten-Punkt"
CLASS_SOURCE_LINE = "PD-GB-Quelldaten-Bruchkante"
COLOR_SOURCE_POINT = (0, 50000, 0)
COLOR_SOURCE_LINE = (0, 35000, 55000)
TEXT_NUMBER = re.compile(r"(?<![0-9.,])[-+]?\d+(?:[.,]\d+)?(?![0-9.,])")
CLASS_PIT = "PD-GB-Baugrube"
CLASS_SLOPE = "PD-GB-Boeschung"
CLASS_HATCH = "PD-GB-Boeschungsschraffur"
CLASS_CONFLICT = "PD-GB-Konflikt"
CLASS_GRID = "PD-GB-Raster"
CLASS_CUT = "PD-GB-Abtrag"
CLASS_FILL = "PD-GB-Auftrag"
CLASS_TEXT = "PD-GB-Text"
CLASS_NO_DATA = "PD-GB-Keine-Daten"


def alert(message):
    try:
        vs.AlertInform(str(message), "", False)
    except Exception:
        vs.AlrtDialog(str(message))


def confirm(question, advice=""):
    return int(vs.AlertQuestion(str(question), str(advice), 0, "Weiter", "Abbrechen", "", "")) == 1


def units_to_meters():
    values = vs.GetUnits()
    try:
        units_per_inch = float(values[3])
    except (TypeError, ValueError, IndexError) as error:
        raise core.TerrainError("Dokumenteinheiten konnten nicht gelesen werden.") from error
    if not math.isfinite(units_per_inch) or units_per_inch <= 0.0:
        raise core.TerrainError("Die Dokumenteinheiten sind ungültig.")
    return 0.0254 / units_per_inch


def _layer_z_units(handle, factor):
    layer = vs.GetLayer(handle)
    if not layer:
        return 0.0
    value = vs.GetLayerElevation(layer)
    try:
        return float(value[0]) / 1000.0 / factor
    except (TypeError, ValueError, IndexError):
        return 0.0


def selected_handles():
    result = []
    seen = set()

    def collect(handle):
        # The SEL criterion is authoritative. Calling Selected(handle) again
        # drops many imported/highlighted objects although Vectorworks counts
        # them in the current selection (observed with large DWG surveys).
        if handle and handle not in seen:
            seen.add(handle)
            result.append(handle)
    vs.ForEachObject(collect, "(SEL=TRUE)")
    # Some imported DWG selections are only partially returned by criteria.
    # Merge Vectorworks' selected-object chain on the active layer as a second,
    # independent source. This is read-only and preserves selection order.
    try:
        handle = vs.FSActLayer()
        visited_chain = set()
        while handle and handle not in visited_chain:
            visited_chain.add(handle)
            collect(handle)
            handle = vs.NextSObj(handle)
    except (AttributeError, TypeError):
        pass
    # Authoritative full-document fallback: selected objects only (2), deep
    # container traversal (2), all layers (1). This reaches selections spanning
    # design layers and imported containers that the two faster paths omit.
    try:
        vs.ForEachObjectInLayer(collect, 2, 2, 1)
    except (AttributeError, TypeError):
        pass
    # Large imported selections can be truncated by all selection iterators
    # (1,024 handles observed). Enumerate every object and inspect its selection
    # flag individually so no selected 3D source is lost at that iterator limit.
    def collect_if_selected(handle):
        try:
            if vs.Selected(handle):
                collect(handle)
        except (AttributeError, TypeError):
            pass
    try:
        vs.ForEachObjectInLayer(collect_if_selected, 0, 2, 1)
    except (AttributeError, TypeError):
        pass
    return tuple(result)


def selected_object_count():
    """Return Vectorworks' own selection count for consistency diagnostics."""
    try:
        return max(0, int(vs.Count("(SEL=TRUE)") or 0))
    except (AttributeError, TypeError, ValueError):
        return 0


def active_layer_handles():
    """Return every object on the active layer, including nested containers."""
    result = []
    seen = set()

    def collect(handle):
        if handle and handle not in seen:
            seen.add(handle)
            result.append(handle)
    try:
        # objOptions 0 = all objects; traversal 2 = groups deeply;
        # layerOptions 0 = active layer only.
        vs.ForEachObjectInLayer(collect, 0, 2, 0)
    except (AttributeError, TypeError) as error:
        raise core.TerrainError(
            "Die Objekte der aktiven Ebene konnten nicht vollständig gelesen werden.") from error
    return tuple(result)


def _identifier(handle):
    value = str(vs.GetObjectUuid(handle) or "").strip()
    return value or str(vs.GetName(handle) or "Objekt")


def _context(handle):
    layer = vs.GetLayer(handle)
    return str(vs.GetClass(handle) or ""), str(vs.GetLName(layer) if layer else "")


def object_label(handle):
    name = str(vs.GetName(handle) or "").strip()
    class_name, layer_name = _context(handle)
    return name or "%s / %s" % (layer_name or "Ebene ?", class_name or "Klasse ?")


def object_type_name(value):
    number = int(value or 0)
    return OBJECT_TYPE_NAMES.get(number, "Objekttyp %d" % number)


def _sample_2d_path(handle, tolerance_doc):
    length = float(vs.HLength(handle) or 0.0)
    if length <= 0.0:
        return ()
    segments = max(1, min(10000, int(math.ceil(length / max(tolerance_doc, 1e-9)))))
    result = []
    for index in range(segments + 1):
        value = vs.PointAlongPoly(handle, length * index / segments)
        if not isinstance(value, (tuple, list)) or len(value) < 2 or not value[0]:
            return ()
        point = value[1]
        if not isinstance(point, (tuple, list)) or len(point) < 2:
            return ()
        result.append((float(point[0]), float(point[1])))
    return tuple(result)


def _sample_circular_arc(handle, tolerance_doc):
    """Fallback for imported arcs rejected by HLength/PointAlongPoly."""
    try:
        center = vs.HCenter(handle)
        first = vs.GetSegPt1(handle)
        _start_angle, sweep_angle = vs.GetArc(handle)
        radius = math.hypot(float(first[0]) - float(center[0]),
                            float(first[1]) - float(center[1]))
        sweep = math.radians(float(sweep_angle))
        if radius <= 0.0 or abs(sweep) <= 1e-12:
            return ()
        segments = max(1, min(10000, int(math.ceil(
            abs(radius * sweep) / max(tolerance_doc, 1e-9)))))
        start = math.atan2(float(first[1]) - float(center[1]),
                           float(first[0]) - float(center[0]))
        return tuple((float(center[0]) + radius * math.cos(start + sweep * index / segments),
                      float(center[1]) + radius * math.sin(start + sweep * index / segments))
                     for index in range(segments + 1))
    except (AttributeError, TypeError, ValueError, IndexError):
        return ()


def _numeric_text_height_m(handle):
    """Read one unambiguous elevation from a text such as '102.65' or 'H=102,65'."""
    try:
        value = str(vs.GetText(handle) or "").strip()
    except (AttributeError, TypeError):
        return None
    matches = TEXT_NUMBER.findall(value)
    if len(matches) != 1:
        return None
    try:
        height = float(matches[0].replace(",", "."))
    except (TypeError, ValueError):
        return None
    return height if math.isfinite(height) and abs(height) <= 100000.0 else None


def _source_element(handle, factor, chord_tolerance_m):
    object_type = int(vs.GetTypeN(handle) or 0)
    identifier = _identifier(handle)
    class_name, layer_name = _context(handle)
    layer_z = _layer_z_units(handle, factor)
    if object_type == TYPE_LOCUS_3D:
        x, y, z = vs.GetLocus3D(handle)
        return {"id": identifier, "kind": "point",
                "points": ((x * factor, y * factor, (z + layer_z) * factor),),
                "class": class_name, "layer": layer_name}
    if object_type == TYPE_POLYGON_3D:
        # GetPolyPt3D returns the effective Z including the layer elevation.
        points = tuple((float(x) * factor, float(y) * factor, float(z) * factor)
                       for x, y, z in (vs.GetPolyPt3D(handle, index)
                       for index in range(int(vs.GetVertNum(handle) or 0))))
        return {"id": identifier,
                "kind": "contour" if vs.IsPolyClosed(handle) else "breakline",
                "points": points, "class": class_name, "layer": layer_name}
    if object_type in (TYPE_PARAMETRIC, TYPE_SYMBOL):
        try:
            record = vs.GetParametricRecord(handle)
            plug_in = str(vs.GetName(record) if record else "").casefold()
        except (AttributeError, TypeError):
            plug_in = ""
        if (object_type == TYPE_SYMBOL or "stake" in plug_in or
                "vermessung" in plug_in or "survey" in plug_in or
                "hoehe" in plug_in or "höhe" in plug_in or
                "point" in plug_in or "punkt" in plug_in):
            try:
                x, y, z = vs.GetSymLoc3D(handle)
                return {"id": identifier, "kind": "point",
                        "points": ((x * factor, y * factor, (z + layer_z) * factor),),
                        "class": class_name, "layer": layer_name}
            except (AttributeError, TypeError, ValueError):
                pass
    # Imported 2D and layer-plane geometry often has no 3D centre although its
    # layer elevation is a valid terrain height. Do not reject it for that.
    has_3d_center = False
    try:
        center = vs.Get3DCntr(handle)
        if not isinstance(center, (tuple, list)) or len(center) < 3:
            raise ValueError("kein 3D-Mittelpunkt")
        z_value = (float(center[2]) + layer_z) * factor
        has_3d_center = True
    except (TypeError, ValueError, IndexError):
        center = (0.0, 0.0, 0.0)
        z_value = layer_z * factor
    if object_type == TYPE_LOCUS_2D:
        try:
            x_value, y_value = vs.GetLocPt(handle)
        except (AttributeError, TypeError, ValueError):
            return None
        return {"id": identifier, "kind": "point",
                "points": ((float(x_value) * factor, float(y_value) * factor, z_value),),
                "class": class_name, "layer": layer_name}
    if object_type == TYPE_TEXT:
        try:
            origin = vs.GetTextOrigin(handle)
            x_value, y_value = float(origin[0]), float(origin[1])
        except (AttributeError, TypeError, ValueError, IndexError):
            x_value, y_value = float(center[0]), float(center[1])
        text_height = _numeric_text_height_m(handle)
        layer_height_m = layer_z * factor
        if (text_height is not None and
                (not has_3d_center or abs(z_value - layer_height_m) <= 1e-9)):
            z_value = text_height
        return {"id": identifier, "kind": "point",
                "points": ((x_value * factor, y_value * factor, z_value),),
                "class": class_name, "layer": layer_name}
    if object_type == TYPE_LINE:
        first, second = vs.GetSegPt1(handle), vs.GetSegPt2(handle)
        points = ((float(first[0]) * factor, float(first[1]) * factor, z_value),
                  (float(second[0]) * factor, float(second[1]) * factor, z_value))
        return {"id": identifier, "kind": "breakline", "points": points,
                "class": class_name, "layer": layer_name}
    if object_type in (TYPE_POLYGON, TYPE_POLYLINE):
        points = tuple((float(x) * factor, float(y) * factor, z_value)
                       for x, y in (vs.GetPolyPt(handle, index)
                                    for index in range(
                                        1, int(vs.GetVertNum(handle) or 0) + 1)))
        return {"id": identifier,
                "kind": "contour" if vs.IsPolyClosed(handle) else "breakline",
                "points": points, "class": class_name, "layer": layer_name}
    if object_type in (TYPE_ARC, TYPE_FREEHAND):
        points_2d = _sample_2d_path(handle, chord_tolerance_m / factor)
        if not points_2d and object_type == TYPE_ARC:
            points_2d = _sample_circular_arc(handle, chord_tolerance_m / factor)
        if points_2d:
            return {"id": identifier, "kind": "curve",
                    "points": tuple((x * factor, y * factor, z_value) for x, y in points_2d),
                    "class": class_name, "layer": layer_name}
    # Any remaining selected object that Vectorworks locates in 3D still
    # contributes a terrain support point instead of being discarded solely
    # because its imported object type has no dedicated converter.
    if has_3d_center:
        return {"id": identifier, "kind": "point",
                "points": ((float(center[0]) * factor, float(center[1]) * factor,
                            z_value),),
                "class": class_name, "layer": layer_name}
    return None


def _mesh_source_elements(handle, factor):
    """Expose every mesh vertex as an independent terrain source point."""
    identifier = _identifier(handle)
    class_name, layer_name = _context(handle)
    result = []
    try:
        count = int(vs.GetMeshVertsCnt(handle) or 0)
    except Exception:
        count = 0
    for index in range(max(0, count)):
        try:
            x, y, z = vs.GetMeshVertex(handle, index)
            point = (float(x) * factor, float(y) * factor,
                     float(z) * factor)
        except (TypeError, ValueError, IndexError):
            continue
        result.append({"id": "%s / Meshpunkt %d" % (identifier, index + 1),
                       "kind": "point", "points": (point,),
                       "class": class_name, "layer": layer_name})
    return tuple(result)


def _contained_handles(handle):
    """Iterate direct members of a group without altering the source object."""
    child = vs.FInGroup(handle)
    seen = set()
    while child and child not in seen:
        seen.add(child)
        yield child
        child = vs.NextObj(child)


def _converted_3d_elements(handle, factor):
    """Read full 3D polygon geometry from a temporary converted duplicate."""
    duplicate = None
    converted = None
    result = []
    identifier = _identifier(handle)
    class_name, layer_name = _context(handle)

    def candidates(root):
        yield root
        if int(vs.GetTypeN(root) or 0) == TYPE_GROUP:
            for child in _contained_handles(root):
                for nested in candidates(child):
                    yield nested

    try:
        duplicate = vs.HDuplicate(handle, 0.0, 0.0)
        if not duplicate:
            return ()
        converted = vs.ConvertTo3DPolys(duplicate)
        if not converted:
            return ()
        for candidate in candidates(converted):
            if int(vs.GetTypeN(candidate) or 0) != TYPE_POLYGON_3D:
                continue
            points = tuple((float(x) * factor, float(y) * factor, float(z) * factor)
                           for x, y, z in (vs.GetPolyPt3D(candidate, index)
                           for index in range(int(vs.GetVertNum(candidate) or 0))))
            if len(points) < 2:
                continue
            result.append({
                "id": "%s / 3D-Geometrie %d" % (identifier, len(result) + 1),
                "kind": "contour" if vs.IsPolyClosed(candidate) else "breakline",
                "points": points, "class": class_name, "layer": layer_name,
            })
        return tuple(result)
    except Exception:
        return ()
    finally:
        try:
            if converted:
                vs.DelObject(converted)
            elif duplicate:
                vs.DelObject(duplicate)
        except Exception:
            pass


def _source_elements(handle, factor, chord_tolerance_m, ancestry=()):
    """Expand containers and vertex collections into normalized source elements."""
    object_type = int(vs.GetTypeN(handle) or 0)
    if object_type == TYPE_MESH:
        values = _mesh_source_elements(handle, factor)
        if values:
            return values
        fallback = _source_element(handle, factor, chord_tolerance_m)
        return (fallback,) if fallback else ()
    if object_type == TYPE_NURBS_CURVE:
        identifier = _identifier(handle)
        class_name, layer_name = _context(handle)
        try:
            points = tuple(tuple(float(value) * factor
                                 for value in vs.GetPolyPt3D(handle, index))
                           for index in range(int(vs.GetVertNum(handle) or 0)))
        except (TypeError, ValueError, IndexError):
            points = ()
        if len(points) >= 2:
            return ({"id": identifier, "kind": "breakline", "points": points,
                     "class": class_name, "layer": layer_name},)
        fallback = _source_element(handle, factor, chord_tolerance_m)
        return (fallback,) if fallback else ()
    if object_type == TYPE_GROUP:
        identity = _identifier(handle)
        if identity in ancestry:
            return ()
        result = []
        for child in _contained_handles(handle):
            result.extend(_source_elements(
                child, factor, chord_tolerance_m, ancestry + (identity,)))
        if result:
            return tuple(result)
        fallback = _source_element(handle, factor, chord_tolerance_m)
        return (fallback,) if fallback else ()
    # Symbol instances, solids, rectangles, ovals, dimensions and other
    # imported spatial types must contribute their actual polygon geometry,
    # not merely one generic centre point.
    direct_types = {
        TYPE_LINE, TYPE_ARC, TYPE_FREEHAND, TYPE_LOCUS_3D, TYPE_TEXT,
        TYPE_POLYGON, TYPE_POLYLINE, TYPE_POLYGON_3D, TYPE_LOCUS_2D,
        TYPE_PARAMETRIC,
    }
    if object_type not in direct_types:
        converted = _converted_3d_elements(handle, factor)
        if converted:
            return converted
    element = _source_element(handle, factor, chord_tolerance_m)
    if element:
        return (element,)
    if object_type == TYPE_PARAMETRIC:
        return _converted_3d_elements(handle, factor)
    return ()


def selected_boundary(handles=None):
    factor = units_to_meters()
    for handle in handles or selected_handles():
        object_type = int(vs.GetTypeN(handle) or 0)
        if object_type in (TYPE_POLYGON, TYPE_POLYLINE) and vs.IsPolyClosed(handle):
            points = tuple((float(x) * factor, float(y) * factor)
                           for x, y in (vs.GetPolyPt(handle, index)
                                        for index in range(
                                            1, int(vs.GetVertNum(handle) or 0) + 1)))
            return handle, core.normalize_polygon(points)
    return None, None


def selected_boundaries(handles=None):
    values = []
    remaining = tuple(handles or selected_handles())
    for handle in remaining:
        found_handle, polygon = selected_boundary((handle,))
        if found_handle and polygon:
            values.append((found_handle, polygon))
    return tuple(values)


def extract_selected_sources(chord_tolerance_m=core.DEFAULT_CHORD_TOLERANCE_M,
                             ignore_handle=None):
    return extract_sources(selected_handles(), chord_tolerance_m, ignore_handle)


def extract_sources(handles, chord_tolerance_m=core.DEFAULT_CHORD_TOLERANCE_M,
                    ignore_handle=None):
    factor = units_to_meters()
    result, unsupported = [], []
    for handle in tuple(handles or ()):
        if handle == ignore_handle:
            continue
        try:
            elements = _source_elements(handle, factor, chord_tolerance_m)
        except Exception as error:
            object_type = int(vs.GetTypeN(handle) or 0)
            unsupported.append(dict(
                id=_identifier(handle), type=object_type,
                type_name=object_type_name(object_type), error=str(error)))
            continue
        if elements:
            result.extend(elements)
        else:
            object_type = int(vs.GetTypeN(handle) or 0)
            unsupported.append(dict(id=_identifier(handle), type=object_type,
                                    type_name=object_type_name(object_type)))
    return tuple(result), tuple(unsupported)


def _ensure_class(name, color):
    active = str(vs.ActiveClass() or "")
    if not vs.GetObject(name):
        vs.NameClass(name)
    handle = vs.GetObject(name)
    if not handle:
        raise core.TerrainError("Klasse konnte nicht angelegt werden: " + name)
    try:
        vs.SetPenFore(handle, tuple(color))
        vs.SetFillFore(handle, tuple(color))
    finally:
        if active and vs.ActiveClass() != active:
            vs.NameClass(active)


def ensure_class(name):
    value = str(name or "").strip()
    if not value:
        raise core.TerrainError("Der gewünschte Klassenname fehlt.")
    _ensure_class(value, (0, 0, 0))
    return value


def _unique_name(base):
    base = str(base or "PD-GB-Ausgabe").strip() or "PD-GB-Ausgabe"
    if not vs.GetObject(base):
        return base
    index = 2
    while vs.GetObject("%s-%d" % (base, index)):
        index += 1
    return "%s-%d" % (base, index)


def _record(name, field):
    if not vs.GetObject(name):
        vs.NewField(name, field, "", 4, 0)
    if not vs.GetObject(name):
        raise core.TerrainError("Datensatz konnte nicht angelegt werden: " + name)


def _write_record(handle, name, field, data):
    _record(name, field)
    if not vs.GetRField(handle, name, field):
        vs.SetRecord(handle, name)
    payload = json.dumps(data, ensure_ascii=True, sort_keys=True,
                         separators=(",", ":"), allow_nan=False)
    previous = str(vs.GetRField(handle, name, field) or "")
    vs.SetRField(handle, name, field, payload)
    if str(vs.GetRField(handle, name, field) or "") != payload:
        vs.SetRField(handle, name, field, previous)
        raise core.TerrainError("Objektdaten konnten nicht verifiziert werden.")


def _read_record(handle, name, field):
    raw = str(vs.GetRField(handle, name, field) or "")
    if not raw:
        return None
    try:
        value = json.loads(raw)
    except (TypeError, ValueError):
        return None
    return value if isinstance(value, dict) else None


def create_source_layer(review, layer_name="PD-GB-Quelldaten"):
    if review.get("blocking_count"):
        raise core.TerrainError("Die Quelldaten enthalten noch blockierende Konflikte.")
    if not review.get("usable"):
        raise core.TerrainError("Keine verwendbaren Quelldaten vorhanden.")
    factor = units_to_meters()
    target_name = _unique_name(layer_name)
    previous_layer = str(vs.GetLName(vs.ActLayer()) or "")
    previous_class = str(vs.ActiveClass() or "")
    layer = None
    created = []
    completed = False
    _ensure_class(CLASS_SOURCE_POINT, (0, 45000, 0))
    _ensure_class(CLASS_SOURCE_LINE, (0, 25000, 50000))
    try:
        layer = vs.CreateLayer(target_name, 1)
        if not layer:
            raise core.TerrainError("Die Quelldaten-Ebene konnte nicht angelegt werden.")
        vs.Layer(target_name)
        layer_z = _layer_z_units(layer, factor)
        for element in review["usable"]:
            if element["kind"] == "point":
                x, y, z = element["points"][0]
                vs.Locus3D((x / factor, y / factor, z / factor - layer_z))
                handle = vs.LNewObj()
                if handle:
                    created.append(handle)
                if not handle or vs.GetTypeN(handle) != TYPE_LOCUS_3D:
                    raise core.TerrainError("3D-Quellpunkt konnte nicht erzeugt werden.")
                vs.SetClass(handle, CLASS_SOURCE_POINT)
                vs.SetPenFore(handle, COLOR_SOURCE_POINT)
            else:
                vs.BeginPoly3D()
                try:
                    for x, y, z in element["points"]:
                        vs.Add3DPt((x / factor, y / factor, z / factor - layer_z))
                finally:
                    vs.EndPoly3D()
                handle = vs.LNewObj()
                if handle:
                    created.append(handle)
                if not handle or vs.GetTypeN(handle) != TYPE_POLYGON_3D:
                    raise core.TerrainError("3D-Bruchkante konnte nicht erzeugt werden.")
                vs.SetPolyClosed(handle, element["kind"] == "contour")
                vs.SetFPat(handle, 0)
                vs.SetClass(handle, CLASS_SOURCE_LINE)
                vs.SetPenFore(handle, COLOR_SOURCE_LINE)
                vs.SetLW(handle, 20)
        if len(created) != review["usable_count"]:
            raise core.TerrainError("Nicht alle Quelldaten wurden erzeugt.")
        vs.DSelectAll()
        for handle in created:
            vs.SetSelect(handle)
        vs.NameUndoEvent("PD Gelände-Quelldaten vorbereiten")
        vs.ReDrawAll()
        completed = True
        return target_name, tuple(created)
    except Exception:
        for handle in created:
            if handle:
                vs.DelObject(handle)
        if layer:
            vs.DelObject(layer)
        raise
    finally:
        if not completed and previous_layer:
            vs.Layer(previous_layer)
        if previous_class and vs.ActiveClass() != previous_class:
            vs.NameClass(previous_class)


def site_models():
    result = []

    def collect(handle):
        if vs.DTM6_IsDTM6Object(handle):
            result.append((handle, str(vs.GetName(handle) or "").strip()))
    vs.ForEachObject(collect, "ALL")
    return tuple(sorted(result, key=lambda row: (row[1].casefold(), str(row[0]))))


def model_by_name(name):
    handle = vs.GetObject(str(name or ""))
    if not handle or not vs.DTM6_IsDTM6Object(handle):
        raise core.TerrainError("Geländemodell nicht gefunden: " + str(name))
    if not vs.DTM6_IsObjectReady(handle):
        vs.ResetObject(handle)
    if not vs.DTM6_IsObjectReady(handle):
        raise core.TerrainError("Das Geländemodell ist noch nicht auswertbar: " + str(name))
    return handle


def model_metadata(handle):
    value = _read_record(handle, MODEL_RECORD, MODEL_FIELD)
    return value if value and value.get("schema") == core.SCHEMA else None


def register_model(handle, variant_name, role, reference_name="", priority=0,
                   managed_variant=False):
    if not handle or not vs.DTM6_IsDTM6Object(handle):
        raise core.TerrainError("Nur ein natives Vectorworks-Geländemodell kann registriert werden.")
    model_name = str(vs.GetName(handle) or "").strip()
    if not model_name:
        raise core.TerrainError("Das Geländemodell muss zuerst einen eindeutigen Namen erhalten.")
    data = {
        "schema": core.SCHEMA,
        "id": str(uuid.uuid4()),
        "variant_name": str(variant_name or model_name).strip(),
        "role": "bestand" if str(role).casefold() == "bestand" else "soll",
        "model_name": model_name,
        "reference_name": str(reference_name or ""),
        "priority": int(priority),
        "managed_variant": bool(managed_variant),
    }
    _write_record(handle, MODEL_RECORD, MODEL_FIELD, data)
    vs.NameUndoEvent("PD Geländemodell registrieren")
    return data


def duplicate_variant(source_name, new_model_name, variant_name):
    source = model_by_name(source_name)
    name = str(new_model_name or "").strip()
    if not name or vs.GetObject(name):
        raise core.TerrainError("Der neue Geländemodellname fehlt oder ist bereits vergeben.")
    duplicate = vs.HDuplicate(source, 0.0, 0.0)
    if not duplicate or not vs.DTM6_IsDTM6Object(duplicate):
        if duplicate:
            vs.DelObject(duplicate)
        raise core.TerrainError("Vectorworks konnte keine unabhängige Geländemodellkopie erzeugen.")
    try:
        vs.SetName(duplicate, name)
        if vs.GetObject(name) != duplicate:
            raise core.TerrainError("Die Geländemodellkopie konnte nicht eindeutig benannt werden.")
        data = register_model(duplicate, variant_name or name, "soll", source_name, 0, True)
        vs.NameUndoEvent("PD Sollvariante duplizieren")
        return duplicate, data
    except Exception:
        vs.DelObject(duplicate)
        raise


def delete_managed_variant(model_name):
    handle = model_by_name(model_name)
    data = model_metadata(handle)
    if not data or not data.get("managed_variant") or data.get("role") != "soll":
        raise core.TerrainError("Nur eine vom Modul erzeugte Sollkopie darf hier gelöscht werden.")
    vs.DelObject(handle)
    vs.NameUndoEvent("PD Sollvariante löschen")


def sampler(handle, tin_type=2):
    factor = units_to_meters()

    def elevation(x_m, y_m):
        try:
            return site_model.elevation(handle, (x_m / factor, y_m / factor), tin_type) * factor
        except site_model.SiteModelError:
            return None
    return elevation


def _create_2d_polygon(points, factor, closed, class_name):
    vs.BeginPoly()
    try:
        for x, y in points:
            vs.AddPoint((x / factor, y / factor))
    finally:
        vs.EndPoly()
    handle = vs.LNewObj()
    if not handle or vs.GetTypeN(handle) not in (TYPE_POLYGON, TYPE_POLYLINE):
        raise core.TerrainError("2D-Geometrie konnte nicht erzeugt werden.")
    vs.SetPolyClosed(handle, bool(closed))
    vs.SetClass(handle, class_name)
    vs.SetFPat(handle, 0)
    return handle


def _create_line(first, second, factor, class_name):
    vs.MoveTo((first[0] / factor, first[1] / factor))
    vs.LineTo((second[0] / factor, second[1] / factor))
    handle = vs.LNewObj()
    if not handle:
        raise core.TerrainError("Linie konnte nicht erzeugt werden.")
    vs.SetClass(handle, class_name)
    return handle


def _create_poly3d(points, factor, layer_z, closed, class_name):
    vs.BeginPoly3D()
    try:
        for x, y, z in points:
            vs.Add3DPt((x / factor, y / factor, z / factor - layer_z))
    finally:
        vs.EndPoly3D()
    handle = vs.LNewObj()
    if not handle or vs.GetTypeN(handle) != TYPE_POLYGON_3D:
        raise core.TerrainError("3D-Geometrie konnte nicht erzeugt werden.")
    vs.SetPolyClosed(handle, bool(closed))
    vs.SetClass(handle, class_name)
    vs.SetFPat(handle, 0)
    return handle


def create_excavation_output(result, name, hatch_spacing_m=1.0, short_ratio=0.5,
                             create_modifier=True):
    factor = units_to_meters()
    previous_class = str(vs.ActiveClass() or "")
    _ensure_class(CLASS_PIT, (0, 0, 0))
    _ensure_class(CLASS_SLOPE, (25000, 25000, 25000))
    _ensure_class(CLASS_HATCH, (22000, 22000, 22000))
    _ensure_class(CLASS_CONFLICT, (65535, 0, 0))
    group = None
    group_opened = False
    modifier_created = False
    try:
        vs.BeginGroup()
        group_opened = True
        try:
            base_name = str(name or "PD-GB-Baugrube").strip() or "PD-GB-Baugrube"
            lower_2d = _create_2d_polygon(
                tuple(value[:2] for value in result["lower_edge"]), factor, True, CLASS_PIT)
            vs.SetName(lower_2d, _unique_name(base_name + "-Unterkante-2D"))
            upper_2d = _create_2d_polygon(
                tuple(value[:2] for value in result["upper_edge"]), factor, True,
                CLASS_SLOPE if result["status"] == "valid" else CLASS_CONFLICT)
            vs.SetName(upper_2d, _unique_name(base_name + "-Oberkante-2D"))
            for hatch in core.hatch_lines(result["lower_edge"], result["upper_edge"],
                                           hatch_spacing_m, short_ratio):
                _create_line(hatch["start"], hatch["end"], factor, CLASS_HATCH)
            layer_z = _layer_z_units(vs.ActLayer(), factor)
            pad = _create_poly3d(result["lower_edge"], factor, layer_z, True, CLASS_PIT)
            vs.SetName(pad, _unique_name(base_name + "-Unterkante-3D"))
            if create_modifier:
                before = str(vs.GetClass(pad) or "")
                vs.SetPadAttrs(pad)
                modifier_created = bool(vs.GetClass(pad) and vs.GetClass(pad) != before)
                if not modifier_created:
                    raise core.TerrainError("Vectorworks hat den nativen Sohlen-Modifikator nicht übernommen.")
            upper_3d = _create_poly3d(
                result["upper_edge"], factor, layer_z, True,
                CLASS_SLOPE if result["status"] == "valid" else CLASS_CONFLICT)
            vs.SetName(upper_3d, _unique_name(base_name + "-Oberkante-3D"))
            for conflict in result["conflicts"]:
                index = max(0, min(len(result["lower_edge"]) - 1, int(conflict["edge"]) - 1))
                _create_line(result["lower_edge"][index], conflict["point"], factor, CLASS_CONFLICT)
        finally:
            if group_opened:
                vs.EndGroup()
                group_opened = False
                group = vs.LNewObj()
        if not group or vs.GetTypeN(group) != 11:
            raise core.TerrainError("Baugruben-Ausgabegruppe konnte nicht erzeugt werden.")
        vs.SetClass(group, CLASS_PIT)
        vs.SetName(group, _unique_name(name or "PD-GB-Baugrube"))
        _write_record(group, OUTPUT_RECORD, OUTPUT_FIELD, {
            "schema": core.SCHEMA, "kind": "excavation", "result": result,
            "hatch_spacing_m": float(hatch_spacing_m), "short_ratio": float(short_ratio),
            "modifier_created": modifier_created,
        })
        vs.NameUndoEvent("PD Baugrube und Böschung anlegen")
        vs.ReDrawAll()
        return group
    except Exception:
        if group:
            vs.DelObject(group)
        raise
    finally:
        if previous_class and vs.ActiveClass() != previous_class:
            vs.NameClass(previous_class)


def create_comparison_output(result, boundary, reference_name, comparison_name,
                             decimals=2, label_text_size_pt=8.0, label_limit=5000):
    factor = units_to_meters()
    _ensure_class(CLASS_GRID, (25000, 25000, 25000))
    _ensure_class(CLASS_CUT, (65535, 0, 0))
    _ensure_class(CLASS_FILL, (0, 25000, 65535))
    _ensure_class(CLASS_TEXT, (0, 0, 0))
    _ensure_class(CLASS_NO_DATA, (35000, 35000, 35000))
    group = None
    group_opened = False
    try:
        vs.BeginGroup()
        group_opened = True
        try:
            _create_2d_polygon(boundary, factor, True, CLASS_GRID)
            for first, second in core.zero_segments(result):
                _create_line(first, second, factor, CLASS_GRID)
            display = tuple((cell, cell["delta_m"]) for cell in result["cells"]) + \
                tuple((cell, None) for cell in result.get("no_data", ()))
            stride = max(1, int(math.ceil(len(display) / max(1, int(label_limit)))))
            for index, (cell, value) in enumerate(display):
                if index % stride:
                    continue
                text = ("keine Daten" if value is None else
                        ("+" if value > 0.0 else "") + ("%.*f" % (int(decimals), value)))
                vs.CreateText(text)
                handle = vs.LNewObj()
                if not handle:
                    raise core.TerrainError("Rasterbeschriftung konnte nicht erzeugt werden.")
                vs.TextOrigin((cell["x_m"] / factor, cell["y_m"] / factor))
                vs.SetTextJust(handle, 2)
                vs.SetTextVerticalAlign(handle, 3)
                vs.SetTextSize(handle, 0, len(text), float(label_text_size_pt))
                text_class = (CLASS_NO_DATA if value is None else CLASS_FILL if value > 0.0
                              else CLASS_CUT if value < 0.0 else CLASS_TEXT)
                vs.SetClass(handle, text_class)
        finally:
            if group_opened:
                vs.EndGroup()
                group_opened = False
                group = vs.LNewObj()
        if not group or vs.GetTypeN(group) != 11:
            raise core.TerrainError("Rasterplan-Gruppe konnte nicht erzeugt werden.")
        name = _unique_name("PD-GB-Vergleich-%s-%s" % (reference_name, comparison_name))
        vs.SetName(group, name)
        vs.SetClass(group, CLASS_GRID)
        audit = {key: value for key, value in result.items() if key not in ("cells", "no_data")}
        _write_record(group, OUTPUT_RECORD, OUTPUT_FIELD, {
            "schema": core.SCHEMA, "kind": "comparison", "reference": reference_name,
            "comparison": comparison_name, "boundary": boundary, "result": audit,
            "label_text_size_pt": float(label_text_size_pt),
        })
        vs.NameUndoEvent("PD Gelände vergleichen und Rasterplan anlegen")
        vs.ReDrawAll()
        return group
    except Exception:
        if group:
            vs.DelObject(group)
        raise


def output_data(handle):
    return _read_record(handle, OUTPUT_RECORD, OUTPUT_FIELD)
