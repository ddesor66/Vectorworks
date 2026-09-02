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
CLASS_CONTROL_TEXT = "PD-GB-Kontrolle-Text"
CLASS_CONTROL_LINE = "PD-GB-Kontrolle-Linie"
COLOR_SOURCE_POINT = (0, 50000, 0)
COLOR_SOURCE_LINE = (0, 60000, 12000)
COLOR_CONTROL_TEXT = (50000, 0, 50000)
COLOR_CONTROL_LINE = (60000, 18000, 0)
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


def _walk_object_list(first):
    """Walk one native Vectorworks object list without callback cutoffs."""
    result = []
    seen = set()
    handle = first
    while handle and handle not in seen:
        seen.add(handle)
        result.append(handle)
        handle = vs.NextObj(handle)
    return tuple(result)


def _document_layers():
    """Return every document layer through the native linked layer list."""
    result = []
    seen = set()
    try:
        layer = vs.FLayer()
        while layer and layer not in seen:
            seen.add(layer)
            result.append(layer)
            layer = vs.NextLayer(layer)
    except (AttributeError, TypeError):
        return ()
    return tuple(result)


def _layer_object_list(layer):
    """Return top-level objects of one layer through FInLayer/NextObj."""
    try:
        return _walk_object_list(vs.FInLayer(layer))
    except (AttributeError, TypeError):
        return ()


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
        return False
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
        return False
    try:
        vs.ForEachObjectInLayer(collect_if_selected, 0, 2, 1)
    except (AttributeError, TypeError):
        pass
    # Do not depend on callback or criteria enumeration for large DWG imports.
    # FLayer/FInLayer/NextObj expose the native linked lists directly and have
    # no observed 1,024/2,928-object cutoff. Inspect every top-level object in
    # every working layer against its actual selection flag.
    try:
        for layer in _document_layers():
            for handle in _layer_object_list(layer):
                if vs.Selected(handle):
                    collect(handle)
    except (AttributeError, TypeError):
        pass
    # This also covers an active edit context whose object list is not exposed
    # as a normal document layer.
    try:
        for handle in _walk_object_list(vs.FActLayer()):
            if vs.Selected(handle):
                collect(handle)
    except (AttributeError, TypeError):
        pass
    return tuple(result)


def selected_object_count():
    """Return Vectorworks' own selection count for consistency diagnostics."""
    try:
        # Unlike Count((SEL=TRUE)), this native function is documented to
        # return the selected-object total across all working layers.
        return max(0, int(vs.NumSelectedObjects() or 0))
    except (AttributeError, TypeError, ValueError):
        pass
    try:
        return max(0, int(vs.Count("(SEL=TRUE)") or 0))
    except (AttributeError, TypeError, ValueError):
        return 0


def active_layer_handles():
    """Return every top-level source on the active layer without callbacks."""
    try:
        direct = _walk_object_list(vs.FActLayer())
    except (AttributeError, TypeError):
        direct = ()
    if direct:
        # Keep containers here. _source_elements expands their members once
        # while retaining the correct parent transformation and context.
        return direct
    result = []
    seen = set()

    def collect(handle):
        try:
            is_group = int(vs.GetTypeN(handle) or 0) == TYPE_GROUP
        except (KeyError, TypeError, ValueError):
            is_group = False
        if handle and not is_group and handle not in seen:
            seen.add(handle)
            result.append(handle)
        return False
    try:
        # objOptions 0 = all objects; traversal 2 = deep container members.
        # Group shells are omitted so members are processed exactly once;
        # layerOptions 0 = active layer only.
        vs.ForEachObjectInLayer(collect, 0, 2, 0)
    except (AttributeError, TypeError) as error:
        raise core.TerrainError(
            "Die Objekte der aktiven Ebene konnten nicht vollständig gelesen werden.") from error
    return tuple(result)


def object_layer_handles(handles):
    """Return all top-level sources on every layer represented by ``handles``."""
    layers = []
    seen_layers = set()
    for handle in tuple(handles or ()):
        try:
            layer = vs.GetLayer(handle)
        except (AttributeError, TypeError):
            layer = None
        if layer and layer not in seen_layers:
            seen_layers.add(layer)
            layers.append(layer)
    if not layers:
        return ()
    # Primary path: traverse the layer's linked object list directly. This is
    # the path that includes imported 2D text and line objects omitted by the
    # callback-based deep traversal in large survey drawings.
    direct = []
    direct_seen = set()
    for layer in layers:
        for handle in _layer_object_list(layer):
            if handle and handle not in direct_seen:
                direct_seen.add(handle)
                direct.append(handle)
    if direct:
        return tuple(direct)
    result = []
    seen = set()

    def collect(handle):
        try:
            layer = vs.GetLayer(handle)
        except (AttributeError, TypeError):
            layer = None
        try:
            is_group = int(vs.GetTypeN(handle) or 0) == TYPE_GROUP
        except (KeyError, TypeError, ValueError):
            is_group = False
        if layer in layers and handle and not is_group and handle not in seen:
            seen.add(handle)
            result.append(handle)
        return False
    try:
        # Full document and deep container traversal. Group shells are filtered
        # out, leaving every contained text, line and 3D polygon exactly once.
        vs.ForEachObjectInLayer(collect, 0, 2, 1)
    except (AttributeError, TypeError) as error:
        raise core.TerrainError(
            "Die Ebenen der markierten Objekte konnten nicht vollständig gelesen werden.") from error
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


def source_handle_types(handles):
    """Describe every input handle by its native Vectorworks object type."""
    result = []
    for handle in tuple(handles or ()):
        try:
            object_type = int(vs.GetTypeN(handle) or 0)
        except (AttributeError, TypeError, ValueError):
            object_type = 0
        result.append({"type": object_type,
                       "type_name": object_type_name(object_type)})
    return tuple(result)


def _with_source_type(elements, object_type, source_handle=None):
    """Attach the originating native type, including recursively read members."""
    result = []
    for raw in tuple(elements or ()):
        element = dict(raw)
        element.setdefault("source_type", object_type)
        element.setdefault("source_type_name", object_type_name(object_type))
        if source_handle:
            element.setdefault("source_handle", source_handle)
        result.append(element)
    return tuple(result)


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


def _entity_matrix(handle):
    """Return one validated planar-object transform in document units.

    Vectorworks stores imported layer/screen-plane geometry in local object
    coordinates. ``GetSegPt*`` and ``GetPolyPt`` can therefore return values
    relative to the object's own plane while the entity matrix contains the
    real document position and orientation. Text has no ``GetTextOrigin``
    function in the Vectorworks 2026 Python API; its matrix offset is the
    insertion point.
    """
    try:
        matrix = vs.GetEntityMatrix(handle)
    except (AttributeError, TypeError, ValueError):
        return None
    if not isinstance(matrix, (tuple, list)) or len(matrix) < 5 or not matrix[0]:
        return None
    offset = matrix[1]
    if not isinstance(offset, (tuple, list)) or len(offset) < 3:
        return None
    try:
        values = (float(offset[0]), float(offset[1]), float(offset[2]),
                  float(matrix[2]), float(matrix[3]), float(matrix[4]))
    except (TypeError, ValueError, IndexError):
        return None
    if not all(math.isfinite(value) for value in values):
        return None
    return values


def _transform_planar_point(handle, point, layer_z=0.0):
    """Transform one local planar point to document XYZ coordinates."""
    try:
        x_value = float(point[0])
        y_value = float(point[1])
        z_value = float(point[2]) if len(point) > 2 else 0.0
    except (TypeError, ValueError, IndexError):
        return None
    matrix = _entity_matrix(handle)
    if matrix is None:
        return (x_value, y_value, z_value + float(layer_z))
    offset_x, offset_y, offset_z, rotate_x, rotate_y, rotate_z = matrix
    angle_x = math.radians(rotate_x)
    angle_y = math.radians(rotate_y)
    angle_z = math.radians(rotate_z)
    cosine, sine = math.cos(angle_x), math.sin(angle_x)
    y_value, z_value = (y_value * cosine - z_value * sine,
                        y_value * sine + z_value * cosine)
    cosine, sine = math.cos(angle_y), math.sin(angle_y)
    x_value, z_value = (x_value * cosine + z_value * sine,
                        -x_value * sine + z_value * cosine)
    cosine, sine = math.cos(angle_z), math.sin(angle_z)
    x_value, y_value = (x_value * cosine - y_value * sine,
                        x_value * sine + y_value * cosine)
    return (x_value + offset_x, y_value + offset_y,
            z_value + offset_z + float(layer_z))


def _planar_points(handle, points, layer_z, factor):
    """Transform and scale a sequence of local 2D/3D points."""
    result = []
    for point in points:
        transformed = _transform_planar_point(handle, point, layer_z)
        if transformed is None:
            return ()
        result.append(tuple(value * factor for value in transformed))
    return tuple(result)


def _planar_height_at_xy(handle, x_value, y_value, layer_z=0.0):
    """Evaluate the entity plane at one document XY coordinate.

    Vectorworks returns line, locus, text-centre and polygon coordinates in
    document XY even when the entity plane is tilted.  The matrix angles
    describe that plane; applying the full matrix a second time corrupts XY.
    """
    matrix = _entity_matrix(handle)
    if matrix is None:
        return float(layer_z)
    offset_x, offset_y, offset_z, rotate_x, rotate_y, rotate_z = matrix
    # Rotate the local plane normal (0, 0, 1) by X, then Y, then Z.
    angle_x = math.radians(rotate_x)
    angle_y = math.radians(rotate_y)
    angle_z = math.radians(rotate_z)
    normal_x = math.sin(angle_y) * math.cos(angle_x)
    normal_y = -math.sin(angle_x)
    normal_z = math.cos(angle_y) * math.cos(angle_x)
    cosine, sine = math.cos(angle_z), math.sin(angle_z)
    normal_x, normal_y = (normal_x * cosine - normal_y * sine,
                          normal_x * sine + normal_y * cosine)
    if abs(normal_z) <= 1e-9:
        return offset_z + float(layer_z)
    return (offset_z - (
        normal_x * (float(x_value) - offset_x) +
        normal_y * (float(y_value) - offset_y)) / normal_z +
        float(layer_z))


def _document_xy_planar_points(handle, points, layer_z, factor):
    """Attach the entity-plane Z to document-XY planar coordinates."""
    result = []
    for point in points:
        try:
            x_value, y_value = float(point[0]), float(point[1])
        except (TypeError, ValueError, IndexError):
            return ()
        z_value = _planar_height_at_xy(handle, x_value, y_value, layer_z)
        result.append((x_value * factor, y_value * factor, z_value * factor))
    return tuple(result)


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
    # Imported planar objects must be transformed before they can be used as
    # DGM input. Calling Get3DCntr on these types both loses their real XY
    # position and raises a Vectorworks modal error for many DWG entities.
    if object_type == TYPE_LOCUS_2D:
        try:
            x_value, y_value = vs.GetLocPt(handle)
        except (AttributeError, TypeError, ValueError):
            return None
        points = _document_xy_planar_points(
            handle, ((float(x_value), float(y_value), 0.0),), layer_z, factor)
        return {"id": identifier, "kind": "point",
                "points": points,
                "class": class_name, "layer": layer_name}
    if object_type == TYPE_TEXT:
        matrix = _entity_matrix(handle)
        try:
            center = vs.HCenter(handle)
            x_world, y_world = float(center[0]), float(center[1])
        except (AttributeError, TypeError, ValueError, IndexError):
            return None
        z_world = _planar_height_at_xy(handle, x_world, y_world, layer_z)
        # Only a real entity-matrix Z is authoritative. At the base plane,
        # an unambiguous numeric survey label remains the best elevation.
        if matrix is not None and abs(z_world - layer_z) > 1e-9:
            z_value = z_world * factor
            height_source = "object_matrix"
        else:
            text_height = _numeric_text_height_m(handle)
            if text_height is not None:
                z_value = text_height
                height_source = "text_content"
            else:
                z_value = z_world * factor
                height_source = "layer_elevation"
        return {"id": identifier, "kind": "point",
                "points": ((x_world * factor, y_world * factor, z_value),),
                "class": class_name, "layer": layer_name,
                "height_source": height_source}
    if object_type == TYPE_LINE:
        first, second = vs.GetSegPt1(handle), vs.GetSegPt2(handle)
        points = _document_xy_planar_points(
            handle,
            ((float(first[0]), float(first[1]), 0.0),
             (float(second[0]), float(second[1]), 0.0)),
            layer_z, factor)
        return {"id": identifier, "kind": "breakline", "points": points,
                "class": class_name, "layer": layer_name}
    if object_type in (TYPE_POLYGON, TYPE_POLYLINE):
        points = _document_xy_planar_points(
            handle,
            tuple((float(x), float(y), 0.0)
                  for x, y in (vs.GetPolyPt(handle, index)
                               for index in range(
                                   1, int(vs.GetVertNum(handle) or 0) + 1))),
            layer_z, factor)
        return {"id": identifier,
                "kind": "contour" if vs.IsPolyClosed(handle) else "breakline",
                "points": points, "class": class_name, "layer": layer_name}
    if object_type in (TYPE_ARC, TYPE_FREEHAND):
        points_2d = _sample_2d_path(handle, chord_tolerance_m / factor)
        if not points_2d and object_type == TYPE_ARC:
            points_2d = _sample_circular_arc(handle, chord_tolerance_m / factor)
        if points_2d:
            transformed_points = (
                _planar_points(
                    handle, tuple((x, y, 0.0) for x, y in points_2d),
                    layer_z, factor)
                if object_type == TYPE_ARC else
                _document_xy_planar_points(
                    handle, tuple((x, y, 0.0) for x, y in points_2d),
                    layer_z, factor))
            return {"id": identifier, "kind": "curve",
                    "points": transformed_points,
                    "class": class_name, "layer": layer_name}
    # Spatial types without a dedicated converter still contribute their 3D
    # centre. This is deliberately after all planar branches above.
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
    if object_type == TYPE_LINE:
        # Imported DWG lines are inconsistent: GetSegPt* may return either
        # document XY or a second, georeferenced coordinate space in the same
        # drawing. Vectorworks' native conversion resolves both variants to
        # their actual 3D endpoints. Work only on a temporary duplicate.
        converted = _converted_3d_elements(handle, factor)
        if converted:
            return _with_source_type(converted, object_type, handle)
    if object_type == TYPE_MESH:
        values = _mesh_source_elements(handle, factor)
        if values:
            return _with_source_type(values, object_type, handle)
        fallback = _source_element(handle, factor, chord_tolerance_m)
        return _with_source_type((fallback,) if fallback else (), object_type, handle)
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
            return _with_source_type(({
                "id": identifier, "kind": "breakline", "points": points,
                "class": class_name, "layer": layer_name,
            },), object_type, handle)
        fallback = _source_element(handle, factor, chord_tolerance_m)
        return _with_source_type((fallback,) if fallback else (), object_type, handle)
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
        return _with_source_type((fallback,) if fallback else (), object_type, handle)
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
            return _with_source_type(converted, object_type, handle)
    element = _source_element(handle, factor, chord_tolerance_m)
    if element:
        return _with_source_type((element,), object_type, handle)
    if object_type == TYPE_PARAMETRIC:
        return _with_source_type(
            _converted_3d_elements(handle, factor), object_type, handle)
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
            object_type = int(vs.GetTypeN(handle) or 0)
            for raw in elements:
                element = dict(raw)
                element.setdefault("source_type", object_type)
                element.setdefault("source_type_name", object_type_name(object_type))
                element.setdefault("source_handle", handle)
                result.append(element)
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


def _criterion_literal(value):
    return str(value or "").replace("'", "''")


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


def _create_control_copies(review, control_layer):
    """Duplicate readable source texts and lines onto a visual QA layer."""
    created = []
    seen_sources = set()
    counts = {"texts": 0, "lines": 0}
    for element in review.get("usable", ()):
        object_type = element.get("source_type")
        if object_type not in (TYPE_TEXT, TYPE_LINE):
            continue
        source = element.get("source_handle")
        if not source or source in seen_sources:
            continue
        seen_sources.add(source)
        try:
            # Keep the absolute 3D position when the source and control layers
            # have different layer elevations.
            duplicate = vs.CreateDuplicateObjN(source, control_layer, False)
        except (AttributeError, TypeError):
            try:
                duplicate = vs.CreateDuplicateObject(source, control_layer)
            except (AttributeError, TypeError):
                duplicate = None
        if not duplicate:
            raise core.TerrainError(
                "%s konnte nicht auf die Kontrollebene kopiert werden."
                % object_type_name(object_type))
        created.append(duplicate)
        # Duplicating a selected source can copy its selection state. Do not
        # leave a 2D control object selected for the native DGM command.
        vs.SetDSelect(duplicate)
        if int(vs.GetTypeN(duplicate) or 0) != object_type:
            raise core.TerrainError(
                "Die Kontrollkopie hat nicht mehr den ursprünglichen Objekttyp %s."
                % object_type_name(object_type))
        try:
            duplicate_layer = vs.GetLayer(duplicate)
        except (AttributeError, TypeError):
            duplicate_layer = control_layer
        if duplicate_layer and duplicate_layer != control_layer:
            raise core.TerrainError(
                "%s wurde nicht auf der Kontrollebene abgelegt."
                % object_type_name(object_type))
        if object_type == TYPE_TEXT:
            counts["texts"] += 1
            vs.SetClass(duplicate, CLASS_CONTROL_TEXT)
            vs.SetPenFore(duplicate, COLOR_CONTROL_TEXT)
            vs.SetFillFore(duplicate, COLOR_CONTROL_TEXT)
        else:
            counts["lines"] += 1
            vs.SetClass(duplicate, CLASS_CONTROL_LINE)
            vs.SetPenFore(duplicate, COLOR_CONTROL_LINE)
            vs.SetLW(duplicate, 40)
    return tuple(created), counts


def _deselect_all_document_objects():
    """Deselect every placed object independently of the layer options."""
    deselected = 0

    def deselect_chain(handle, ancestry=()):
        nonlocal deselected
        seen = set()
        while handle and handle not in seen:
            seen.add(handle)
            vs.SetDSelect(handle)
            deselected += 1
            if int(vs.GetTypeN(handle) or 0) == TYPE_GROUP:
                identity = _identifier(handle)
                if identity not in ancestry:
                    child = vs.FInGroup(handle)
                    if child:
                        deselect_chain(child, ancestry + (identity,))
            handle = vs.NextObj(handle)

    for document_layer in _document_layers():
        first = vs.FInLayer(document_layer)
        if first:
            deselect_chain(first)
    return deselected


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
    control_layer = None
    created = []
    control_created = []
    completed = False
    # Native site-model triangulation becomes numerically unstable at typical
    # German survey coordinates (millions of metres from Vectorworks' internal
    # origin). Build the source geometry in internal-origin coordinates;
    # Vectorworks' document georeference presents those values at world XY.
    all_points = tuple(
        point for element in review["usable"] for point in element["points"])
    anchor_x = (min(point[0] for point in all_points) +
                max(point[0] for point in all_points)) * 0.5
    anchor_y = (min(point[1] for point in all_points) +
                max(point[1] for point in all_points)) * 0.5
    _ensure_class(CLASS_SOURCE_POINT, (0, 45000, 0))
    _ensure_class(CLASS_SOURCE_LINE, (0, 25000, 50000))
    _ensure_class(CLASS_CONTROL_TEXT, COLOR_CONTROL_TEXT)
    _ensure_class(CLASS_CONTROL_LINE, COLOR_CONTROL_LINE)
    try:
        layer = vs.CreateLayer(target_name, 1)
        if not layer:
            raise core.TerrainError("Die Quelldaten-Ebene konnte nicht angelegt werden.")
        vs.Layer(target_name)
        layer_z = _layer_z_units(layer, factor)
        for element in review["usable"]:
            if element["kind"] == "point":
                x, y, z = element["points"][0]
                vs.Locus3D(((x - anchor_x) / factor,
                            (y - anchor_y) / factor,
                            z / factor - layer_z))
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
                        vs.Add3DPt(((x - anchor_x) / factor,
                                    (y - anchor_y) / factor,
                                    z / factor - layer_z))
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
                vs.SetLW(handle, 40)
        if len(created) != review["usable_count"]:
            raise core.TerrainError("Nicht alle Quelldaten wurden erzeugt.")
        control_name = _unique_name(target_name + "-Kontrolle")
        control_layer = vs.CreateLayer(control_name, 1)
        if not control_layer:
            raise core.TerrainError("Die Kontrollebene konnte nicht angelegt werden.")
        control_created, control_counts = _create_control_copies(review, control_layer)
        # The native DGM command must receive only the normalized 3D sources.
        # DSelectAll only affects the active layer under common layer options,
        # so remove every stale source/control selection explicitly first.
        vs.Layer(target_name)
        _deselect_all_document_objects()
        layer_value = _criterion_literal(target_name)
        layer_criterion = "(L='%s')" % layer_value
        # Select the verified handles themselves. This bypasses both the
        # criteria callback limit and any stale cross-layer selection state.
        for handle in created:
            vs.SetSelect(handle)
        expected_points = sum(1 for value in review["usable"]
                              if value["kind"] == "point")
        expected_lines = review["usable_count"] - expected_points
        try:
            actual_points = int(vs.Count(
                "((L='%s') & (T=%d))" % (layer_value, TYPE_LOCUS_3D)) or 0)
            actual_lines = int(vs.Count(
                "((L='%s') & (T=%d))" % (layer_value, TYPE_POLYGON_3D)) or 0)
            actual_selected = int(vs.Count(
                "((L='%s') & (SEL=TRUE))" % layer_value) or 0)
            selection_verified = True
        except (AttributeError, TypeError, ValueError):
            actual_points = expected_points
            actual_lines = expected_lines
            actual_selected = sum(1 for handle in created if vs.Selected(handle))
            selection_verified = False
        if actual_points != expected_points or actual_lines != expected_lines:
            raise core.TerrainError(
                "Die grafische Ausgabe ist unvollständig: erwartet %d Punkte und %d Linien, "
                "gefunden %d Punkte und %d Linien."
                % (expected_points, expected_lines, actual_points, actual_lines))
        if selection_verified and actual_selected != len(created):
            raise core.TerrainError(
                "Die Ausgabe wurde erzeugt, aber nur %d von %d Quellobjekten tatsächlich markiert."
                % (actual_selected, len(created)))
        handle_selected = sum(1 for handle in created if vs.Selected(handle))
        if handle_selected != len(created):
            raise core.TerrainError(
                "Nur %d von %d erzeugten 3D-Quellen sind direkt markiert."
                % (handle_selected, len(created)))
        control_selected = sum(1 for handle in control_created if vs.Selected(handle))
        document_selected = selected_object_count()
        if control_selected or document_selected != len(created):
            raise core.TerrainError(
                "Die DGM-Auswahl ist nicht eindeutig: %d Quellen erwartet, "
                "%d Dokumentobjekte und %d Kontrollkopien sind markiert."
                % (len(created), document_selected, control_selected))
        verification = {
            "points": actual_points, "lines": actual_lines,
            "selected": document_selected, "selection_verified": selection_verified,
            "control_layer": control_name,
            "control_texts": control_counts["texts"],
            "control_lines": control_counts["lines"],
            "control_total": len(control_created),
            "xy_anchor_m": (anchor_x, anchor_y),
            "xy_normalized": True,
        }
        vs.NameUndoEvent("PD Gelände-Quelldaten vorbereiten")
        vs.ReDrawAll()
        completed = True
        return target_name, tuple(created), verification
    except Exception:
        for handle in control_created:
            if handle:
                vs.DelObject(handle)
        if control_layer:
            vs.DelObject(control_layer)
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


def create_site_model_from_selected_sources(model_name, model_class,
                                            xy_anchor_m=None):
    """Run Vectorworks' native source-data command and reveal its new model.

    The command itself remains native so Vectorworks owns the triangulation and
    presents its normal settings dialog.  Once that modal command returns, the
    newly created site-model PIO is found independently of names, assigned the
    requested class/name, made visible and selected for an unambiguous result.
    """
    existing_ids = set(_identifier(handle) for handle, _name in site_models())
    try:
        # Universal workspace command name and first chunk item:
        # "Geländemodell aus Ausgangsdaten" in the German Landmark workspace.
        vs.DoMenuTextByName("DTM6 Menu", 1)
    except (AttributeError, TypeError) as error:
        raise core.TerrainError(
            "Der native Befehl „Geländemodell aus Ausgangsdaten“ konnte nicht "
            "gestartet werden: %s" % error)

    created = tuple(
        handle for handle, _name in site_models()
        if _identifier(handle) not in existing_ids)
    if not created:
        return None
    handle = created[-1]

    anchor = tuple(xy_anchor_m or (0.0, 0.0))
    # Vectorworks' Python geometry coordinates are relative to its internal
    # origin, while the OIP and document rulers expose the georeferenced user
    # coordinates.  The local source values therefore already appear at their
    # correct world position.  Applying the anchor as an object translation
    # would add the georeference twice.

    desired_name = str(model_name or "").strip() or "DGM Bestand"
    named_object = vs.GetObject(desired_name)
    if named_object and _identifier(named_object) != _identifier(handle):
        desired_name = _unique_name(desired_name)
    if str(vs.GetName(handle) or "").strip() != desired_name:
        vs.SetName(handle, desired_name)
    actual_name = str(vs.GetName(handle) or "").strip()
    if actual_name != desired_name:
        raise core.TerrainError(
            "Das erzeugte Geländemodell konnte nicht eindeutig benannt werden.")

    desired_class = ensure_class(model_class)
    vs.SetClass(handle, desired_class)
    if str(vs.GetClass(handle) or "") != desired_class:
        raise core.TerrainError(
            "Die Klasse des erzeugten Geländemodells konnte nicht gesetzt werden.")
    previous_class = str(vs.ActiveClass() or "")
    try:
        vs.NameClass(desired_class)
        # Vectorworks 2026 requires the class name even when that class is
        # already active.  Calling ShowClass without it only writes an error to
        # ErrorOut.txt and misleadingly lets the Python script continue.
        vs.ShowClass(desired_class)
    finally:
        if previous_class and previous_class != desired_class:
            vs.NameClass(previous_class)

    # A visible class is still suppressed when the document is set to
    # "Active class only".  This is common in imported survey drawings and
    # was the reason a completely valid, selected DGM appeared as an empty
    # drawing window.  Focus the result with permissive view options and also
    # reveal classes used by the PIO's generated display geometry.
    try:
        vs.SetClassOptions(5)
    except (AttributeError, TypeError):
        pass

    seen_objects = set()
    shown_classes = {desired_class}

    def reveal_object_classes(candidate):
        while candidate and candidate not in seen_objects:
            seen_objects.add(candidate)
            try:
                class_name = str(vs.GetClass(candidate) or "")
                if class_name and class_name not in shown_classes:
                    vs.ShowClass(class_name)
                    shown_classes.add(class_name)
            except (AttributeError, TypeError):
                pass
            try:
                child = vs.FInGroup(candidate)
            except (AttributeError, TypeError):
                child = None
            if child:
                reveal_object_classes(child)
            try:
                candidate = vs.NextObj(candidate)
            except (AttributeError, TypeError):
                candidate = None

    reveal_object_classes(handle)

    layer_handle = vs.GetLayer(handle)
    layer_name = str(vs.GetLName(layer_handle) or "") if layer_handle else ""
    if layer_name:
        vs.Layer(layer_name)
        vs.ShowLayer()
        try:
            vs.SetLayerOptions(5)
        except (AttributeError, TypeError):
            pass

    _deselect_all_document_objects()
    vs.SetSelect(handle)
    vs.SetSelect(handle)
    if not vs.Selected(handle):
        raise core.TerrainError(
            "Das erzeugte Geländemodell ist vorhanden, konnte aber nicht markiert werden.")
    if not vs.DTM6_IsObjectReady(handle):
        vs.ResetObject(handle)
    if not vs.DTM6_IsObjectReady(handle):
        raise core.TerrainError(
            "Das erzeugte Geländemodell ist vorhanden, aber noch nicht auswertbar.")
    vs.ReDrawAll()
    try:
        # A freshly returned DTM has no reliable bounding box until its PIO is
        # ready and the document has redrawn. Only then can Vectorworks zoom
        # to the selected model.
        vs.DoMenuTextByName("Fit to Objects", 0)
    except (AttributeError, TypeError):
        pass
    vs.ReDrawAll()
    return {
        "handle": handle,
        "name": actual_name,
        "class": desired_class,
        "layer": layer_name,
        "ready": True,
        "selected": True,
        "xy_anchor_m": anchor,
    }


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
