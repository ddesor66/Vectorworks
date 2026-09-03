# -*- coding: utf-8 -*-
"""Persistent Vectorworks representation of complete utility routes."""
from __future__ import absolute_import

import copy
import math
import uuid

import vs

from PD_KanalTool import live as native_graphics
from PD_KanalTool import vw_adapter as adapter
from PD_ToolsPD.ddvw.vw import site_model

from . import core
from . import settings


TEXT_COLOR = (0, 0, 0)
RENDER_PENDING = "pending"
RENDER_OK = "ok"
RENDER_ERROR = "error"


def _objects():
    from . import live_objects
    return live_objects


def _rgb(value):
    try:
        result = tuple(max(0, min(65535, int(component))) for component in value)
    except (TypeError, ValueError):
        result = TEXT_COLOR
    return result if len(result) == 3 else TEXT_COLOR


def _ensure_class(name, color, fill=True, line_type=1):
    vs.NameClass(name)
    vs.SetClUseGraphic(name, True)
    vs.SetClFPat(name, 1 if fill else 0)
    vs.SetClFillFore(name, color)
    vs.SetClFillBack(name, color)
    vs.SetClPenFore(name, color)
    vs.SetClPenBack(name, color)
    vs.SetClLSN(name, int(line_type))
    vs.SetClLW(name, 13)


def ensure_classes(route, preferences):
    active = str(vs.ActiveClass() or "")
    try:
        color = _rgb(route["line_color"])
        for dn_mm in sorted(set(route["dns_mm"])):
            for suffix in ("", "_3D"):
                _ensure_class(core.line_class_name(
                    preferences["class_prefix"], route["utility_type"], dn_mm, suffix), color)
        _ensure_class(preferences["axis_class"], TEXT_COLOR, fill=False,
                      line_type=route["axis_line_type"])
        _ensure_class(preferences["fitting_class"], color, fill=False)
        _ensure_class(preferences["text_class"], _rgb(route["text_color"]), fill=False)
    finally:
        if active:
            vs.NameClass(active)


def selected_source_paths():
    rows = []
    for handle in adapter.selected_handles():
        if adapter.object_type(handle) not in (
                adapter.TYPE_LINE, adapter.TYPE_POLYGON, adapter.TYPE_POLYLINE):
            continue
        source = adapter.extract_path(handle)
        points = list(source["points"])
        if adapter.object_type(handle) in (adapter.TYPE_POLYGON, adapter.TYPE_POLYLINE):
            if vs.IsPolyClosed(handle):
                raise core.UtilityError(
                    "Geschlossene Polygone sind keine Leitungstrassen. Bitte eine offene Linie oder Polylinie wählen.")
        rows.append(core.path(points))
    return tuple(rows)


def selected_managed():
    result = {}
    for handle in adapter.selected_handles():
        data = _objects().data_of(handle)
        if data:
            result[str(vs.GetName(handle) or "")] = (handle, data)
    return tuple(result.values())


def all_managed():
    return tuple(_objects().objects())


def _route_name(identity):
    return core.ROUTE_PREFIX + str(identity)


def _with_render_status(data, state, message=""):
    result = copy.deepcopy(data)
    result["render_status"] = {
        "state": str(state),
        "message": str(message or "")[:1000],
    }
    return result


def _require_render_ok(handle):
    current = _objects().data_of(handle)
    status = current.get("render_status", {}) if current else {}
    if status.get("state") != RENDER_OK:
        detail = status.get("message") or "Vectorworks hat den Neuaufbau nicht bestätigt."
        raise core.UtilityError("Leitungsdarstellung fehlgeschlagen: %s" % detail)


def read_route(handle, data=None, persist_move=True):
    data = data or _objects().data_of(handle)
    if not data:
        raise core.UtilityError("Leitungstrasse konnte nicht gelesen werden.")
    route = core.validate_route(data["route"])
    if str(vs.GetName(handle) or "") != _route_name(route["id"]):
        raise core.UtilityError("Leitungstrassenidentität wurde geändert oder kopiert.")
    factor = adapter.units_to_meters()
    fallback_origin = data.get("origin_m", route["points_m"][0])
    location = adapter.symbol_location_2d(
        handle, (fallback_origin[0] / factor, fallback_origin[1] / factor))
    current_origin = float(location[0]) * factor, float(location[1]) * factor
    stored_origin = tuple(data.get("origin_m", current_origin))
    current_rotation = float(vs.GetSymRot(handle) or 0.0)
    stored_rotation = float(data.get("rotation_deg", current_rotation))
    rotation_delta = current_rotation - stored_rotation
    translation = (current_origin[0] - stored_origin[0],
                   current_origin[1] - stored_origin[1])
    if math.hypot(*translation) > 1e-9 or abs(rotation_delta) > 1e-9:
        angle = math.radians(rotation_delta)
        cosine, sine = math.cos(angle), math.sin(angle)

        def transformed(point):
            dx, dy = point[0] - stored_origin[0], point[1] - stored_origin[1]
            return (current_origin[0] + dx * cosine - dy * sine,
                    current_origin[1] + dx * sine + dy * cosine)
        route["points_m"] = tuple(transformed(point) for point in route["points_m"])
        route = core.validate_route(route)
        if route["elevation_mode"] == "surface_cover":
            route = surface_route(route, False)
        if persist_move:
            _objects().write_data(handle, dict(
                data, route=route, origin_m=current_origin,
                rotation_deg=current_rotation))
    return route


def create(paths, options, preferences):
    preferences = settings.validate(preferences)
    values = tuple(core.path(row) for row in paths)
    if not values:
        raise core.UtilityError("Es wurde keine Leitungstrasse gezeichnet.")
    prepared = [core.new_route(row, options) for row in values]
    prepared = [surface_route(route, True) if route["elevation_mode"] == "surface_cover"
                else route for route in prepared]
    for route in prepared:
        core.render_route_paths(route)
    created = []
    handles = []
    factor = adapter.units_to_meters()
    vs.NameUndoEvent("PD Leitungstrasse anlegen")
    try:
        for route in prepared:
            origin = route["points_m"][0]
            data = {
                "schema": core.SCHEMA,
                "role": _objects().ROLE,
                "route": route,
                "origin_m": origin,
                "rotation_deg": 0.0,
                "preferences": copy.deepcopy(preferences),
            }
            data = _with_render_status(data, RENDER_PENDING)
            handle = _objects().new_object(
                (origin[0] / factor, origin[1] / factor), data,
                _route_name(route["id"]), created)
            handles.append(handle)
        for handle in created:
            vs.ResetObject(handle)
            _require_render_ok(handle)
    except Exception:
        for handle in reversed(created):
            if handle:
                vs.DelObject(handle)
        raise
    vs.DSelectAll()
    for handle in handles:
        vs.SetSelect(handle)
    vs.ReDrawAll()
    return tuple(handles)


def object_preferences(handle):
    data = _objects().data_of(handle)
    if not data:
        raise core.UtilityError("Keine Leitungstrasse gewählt.")
    return settings.validate(data.get("preferences"))


def update(handle, route, preferences=None, undo_name="PD Leitungstrasse bearbeiten"):
    data = _objects().data_of(handle)
    if not data:
        raise core.UtilityError("Keine Leitungstrasse gewählt.")
    normalized = core.validate_route(route)
    # Fail before persistent PIO data is replaced.  Reset-event handlers must
    # remain non-throwing in Vectorworks, so every deterministic render rule is
    # exercised here while the old valid object is still intact.
    core.render_route_paths(normalized)
    snapshot = copy.deepcopy(data)
    vs.NameUndoEvent(undo_name)
    try:
        stored_preferences = settings.validate(
            data.get("preferences") if preferences is None else preferences)
        changed = dict(data, route=normalized,
                       preferences=copy.deepcopy(stored_preferences))
        _objects().write_data(
            handle, _with_render_status(changed, RENDER_PENDING))
        vs.ResetObject(handle)
        _require_render_ok(handle)
    except Exception as error:
        try:
            _objects().write_data(
                handle, _with_render_status(snapshot, RENDER_PENDING))
            vs.ResetObject(handle)
            _require_render_ok(handle)
        except Exception as rollback_error:
            raise core.UtilityError(
                "Leitung konnte nicht aktualisiert und auch nicht vollständig "
                "wiederhergestellt werden: %s / %s" %
                (error, rollback_error)) from rollback_error
        raise
    vs.ReDrawAll()
    return normalized


def update_many(updates, preferences=None,
                undo_name="PD Leitungstrassen gemeinsam bearbeiten"):
    """Update several routes as one verified and rollback-safe transaction."""
    rows = tuple(updates or ())
    if not rows:
        raise core.UtilityError("Keine Leitungstrassen zum Aktualisieren übergeben.")
    prepared = []
    snapshots = {}
    for handle, route in rows:
        data = _objects().data_of(handle)
        if not data:
            raise core.UtilityError("Eine markierte Leitungstrasse konnte nicht gelesen werden.")
        normalized = core.validate_route(route)
        core.render_route_paths(normalized)
        snapshots[handle] = copy.deepcopy(data)
        stored_preferences = settings.validate(
            data.get("preferences") if preferences is None else preferences)
        prepared.append((handle, normalized, stored_preferences))
    vs.NameUndoEvent(undo_name)
    try:
        for handle, normalized, stored_preferences in prepared:
            changed = dict(
                snapshots[handle], route=normalized,
                preferences=copy.deepcopy(stored_preferences))
            _objects().write_data(
                handle, _with_render_status(changed, RENDER_PENDING))
        for handle, _normalized, _stored_preferences in prepared:
            vs.ResetObject(handle)
            _require_render_ok(handle)
    except Exception as error:
        rollback_errors = []
        for handle, snapshot in snapshots.items():
            try:
                _objects().write_data(
                    handle, _with_render_status(snapshot, RENDER_PENDING))
                vs.ResetObject(handle)
                _require_render_ok(handle)
            except Exception as rollback_error:
                rollback_errors.append(str(rollback_error))
        if rollback_errors:
            raise core.UtilityError(
                "Leitungstrassen konnten nicht aktualisiert und nicht vollständig "
                "wiederhergestellt werden: %s / %s"
                % (error, "; ".join(rollback_errors)))
        raise
    vs.ReDrawAll()
    return len(prepared)


_PREFERENCE_ROUTE_FIELDS = frozenset((
    "graphics_mode", "line_type", "axis_line_type", "round_corners",
    "fillet_radius_m", "show_fittings", "label_bend_angles", "show_heights",
    "regular_label", "label_text", "label_interval_m", "label_frame",
    "label_fill", "label_bold", "label_underline", "label_rotation_deg",
    "label_layout", "font_name", "font_size_pt", "draw_3d", "text_color",
    "frame_color", "fill_color",
))


def _route_with_preferences(route, preferences):
    """Apply drawing standards while preserving engineering route values."""
    result = copy.deepcopy(route)
    for key in _PREFERENCE_ROUTE_FIELDS:
        result[key] = copy.deepcopy(preferences[key])
    result["line_color"] = copy.deepcopy(
        preferences["colors"].get(result["utility_type"], result["line_color"]))
    return core.validate_route(result)


def apply_preferences(preferences, selected=None, scope="drawing"):
    """Redraw selected systems or every utility route with saved standards."""
    preferences = settings.validate(preferences)
    scope = str(scope or "save")
    if scope not in ("selection", "drawing"):
        raise core.UtilityError("Ungültiger Aktualisierungsumfang der Leitungsstandards.")
    rows = all_managed()
    if scope == "selection":
        selected_handles = {handle for handle, _data in tuple(selected or ())}
        rows = tuple(row for row in rows if row[0] in selected_handles)
        if not rows:
            raise core.UtilityError(
                "Für diese Aktualisierung zuerst mindestens eine Leitungstrasse markieren.")
    elif not rows:
        raise core.UtilityError("Keine Leitungstrassen zum Aktualisieren gefunden.")
    ensure_classes_for_routes = []
    updates = []
    for handle, data in rows:
        route = _route_with_preferences(read_route(handle, data), preferences)
        ensure_classes_for_routes.append(route)
        updates.append((handle, route))
    for route in ensure_classes_for_routes:
        ensure_classes(route, preferences)
    return update_many(
        updates, preferences, "PD Leitungsstandards anwenden")


def delete(handles):
    if not handles:
        raise core.UtilityError("Keine Leitungstrasse markiert.")
    vs.NameUndoEvent("PD Leitungstrasse löschen")
    for handle, data in handles:
        if data:
            vs.DelObject(handle)
    vs.ReDrawAll()
    return len(handles)


def surface_route(route, allow_pick=True):
    """Prepare every line height before any document object is mutated."""
    route = core.validate_route(route)
    factor = adapter.units_to_meters()
    control_paths = core.control_route_paths(route)
    outside = route.get("outside_diameters_mm", route["dns_mm"])
    height_rows = []
    profile_station_rows = []
    profile_height_rows = []
    profile_surface_rows = []
    model_name = route.get("surface_model_name", "")
    for index, points in enumerate(control_paths):
        elevations, selected_name = site_model.sample_meters(
            points, factor, route["surface_tin_type"], model_name, allow_pick)
        model_name = selected_name
        height_rows.append(core.surface_cover_heights(
            elevations, route["dns_mm"][index], route["cover_depth_m"], outside[index]))
    for index, (render_points, render_stations) in enumerate(core.render_route_paths(route)):
        sample_points, sample_stations = core.densify_path(
            render_points, render_stations, 1.0)
        elevations, selected_name = site_model.sample_meters(
            sample_points, factor, route["surface_tin_type"], model_name, allow_pick)
        model_name = selected_name
        profile_station_rows.append(sample_stations)
        profile_surface_rows.append(tuple(elevations))
        profile_height_rows.append(core.surface_cover_heights(
            elevations, route["dns_mm"][index], route["cover_depth_m"], outside[index]))
    route["route_heights_m"] = height_rows
    route["heights_m"] = height_rows[0]
    route["surface_profile_stations_m"] = profile_station_rows
    route["surface_profile_heights_m"] = profile_height_rows
    route["surface_profile_surface_m"] = profile_surface_rows
    route["surface_model_name"] = model_name
    route["elevation_mode"] = "surface_cover"
    return core.validate_route(route)


def refresh_surface(handle, preferences=None, allow_pick=True):
    data = _objects().data_of(handle)
    route = surface_route(read_route(handle, data), allow_pick)
    return update(handle, route, preferences, "PD Leitungshöhen aus Geländemodell")


def update_height(handle, route_index, point_index, height_m, preferences=None):
    return update(handle, core.update_height(
        read_route(handle), point_index, height_m, route_index), preferences,
        "PD Leitungshöhenkette bearbeiten")


def _draw_band_path(points, width, class_value, color):
    left = core.offset_path(points, width * 0.5)
    right = core.offset_path(points, -width * 0.5)
    vs.BeginPoly()
    for point in left + tuple(reversed(right)):
        vs.AddPoint(point)
    vs.EndPoly()
    band = vs.LNewObj()
    if not band:
        raise core.UtilityError("Doppelliniengrafik konnte nicht erzeugt werden.")
    vs.SetPolyClosed(band, True)
    native_graphics._set_graphics(band, class_value, color, fill=True, opacity=50)
    vs.SetLSN(band, 0)
    native_graphics._draw_open_polyline(left, class_value, color)
    native_graphics._draw_open_polyline(right, class_value, color)
    native_graphics._draw_open_polyline((left[0], right[0]), class_value, color)
    native_graphics._draw_open_polyline((left[-1], right[-1]), class_value, color)


def _text(value, xy, angle, route, preferences, factor, frame=False, fill=False):
    text = str(value)
    if route.get("label_layout") == "two_line" and "|" in text:
        text = text.replace("|", "\n", 1)
    vs.TextOrigin(xy)
    vs.CreateText(text)
    handle = vs.LNewObj()
    if not handle:
        raise core.UtilityError("Leitungsbeschriftung konnte nicht erzeugt werden.")
    vs.SetTextStyleRef(handle, 0)
    font_id = int(vs.GetFontID(route["font_name"]) or 0)
    if not font_id:
        raise core.UtilityError(
            "Die gewählte Schriftart ist in Vectorworks nicht verfügbar: %s" %
            route["font_name"])
    vs.SetTextFont(handle, 0, len(text), font_id)
    vs.SetTextSize(handle, 0, len(text), route["font_size_pt"])
    style = (1 if route.get("label_bold") else 0) | (
        4 if route.get("label_underline") else 0)
    vs.SetTextStyle(handle, 0, len(text), style)
    vs.SetTextJust(handle, 2)
    vs.SetTextVertAlignN(handle, 3)
    vs.SetClass(handle, preferences["text_class"])
    vs.SetPenFore(handle, _rgb(route["text_color"]))
    vs.SetFPat(handle, 0)
    vs.SetOpacityN(handle, 100, 100)
    if not (frame or fill):
        vs.HRotate(handle, xy, angle)
        return handle
    box = native_graphics._bbox(vs.GetBBox(handle))
    padding = 0.0015 / factor
    vs.Rect((box[0][0] - padding, box[1][1] + padding),
            (box[1][0] + padding, box[0][1] - padding))
    rectangle = vs.LNewObj()
    if not rectangle:
        raise core.UtilityError("Beschriftungsrahmen konnte nicht erzeugt werden.")
    vs.SetClass(rectangle, preferences["text_class"])
    vs.SetPenFore(rectangle, _rgb(route["frame_color"]))
    vs.SetPenBack(rectangle, _rgb(route["frame_color"]))
    vs.SetFillFore(rectangle, _rgb(route["fill_color"]))
    vs.SetFillBack(rectangle, _rgb(route["fill_color"]))
    vs.SetFPat(rectangle, 1 if fill else 0)
    vs.SetOpacityN(rectangle, 100, 100)
    vs.HRotate(handle, xy, angle)
    vs.HRotate(rectangle, xy, angle)
    vs.HMoveBackward(rectangle, False)
    return handle


def _point_at_station(points, station_values, target):
    for index in range(len(station_values) - 1):
        if target <= station_values[index + 1] + 1e-9:
            length = station_values[index + 1] - station_values[index]
            ratio = 0.0 if length <= 1e-12 else (
                target - station_values[index]) / length
            first, second = points[index], points[index + 1]
            return (first[0] + (second[0] - first[0]) * ratio,
                    first[1] + (second[1] - first[1]) * ratio)
    return points[-1]


def _draw_fittings(route, origin, preferences, factor, rotation_deg=0.0):
    if not route["show_fittings"]:
        return
    color = _rgb(route["line_color"])
    radius = max(0.08, max(route["outside_diameters_mm"]) / 2000.0) / factor
    effective, station_values = core.rounded_path(
        route["points_m"], route["fillet_radius_m"], route["round_corners"])
    for station, angle, _corner in core.bend_rows(route["points_m"]):
        point_m = _point_at_station(effective, station_values, station)
        point = _to_local(point_m, origin, rotation_deg, factor)
        vs.Oval(((point[0] - radius), (point[1] + radius)),
                ((point[0] + radius), (point[1] - radius)))
        marker = vs.LNewObj()
        if marker:
            native_graphics._set_graphics(
                marker, preferences["fitting_class"], color, fill=False, opacity=100)
        if route["label_bend_angles"]:
            _text("%.1f°" % angle, (point[0] + radius * 1.4, point[1] + radius * 1.4),
                  -rotation_deg, route, preferences, factor)


def _tube_path_faces(points, radius, segments=24):
    """Build one watertight tube along a polyline using transported frames."""
    values = tuple(tuple(float(component) for component in point) for point in points)
    if len(values) < 2 or radius <= 0.0:
        raise core.UtilityError("Ungültige 3D-Leitungsgeometrie.")

    def unit(vector):
        length = math.sqrt(sum(component * component for component in vector))
        if length <= 1e-12:
            raise core.UtilityError("3D-Leitung enthält einen Abschnitt ohne Länge.")
        return tuple(component / length for component in vector)

    def cross(first, second):
        return (first[1] * second[2] - first[2] * second[1],
                first[2] * second[0] - first[0] * second[2],
                first[0] * second[1] - first[1] * second[0])

    segment_tangents = [unit(tuple(second[i] - first[i] for i in range(3)))
                        for first, second in zip(values, values[1:])]
    tangents = [segment_tangents[0]]
    for before, after in zip(segment_tangents, segment_tangents[1:]):
        combined = tuple(before[i] + after[i] for i in range(3))
        tangents.append(unit(combined))
    tangents.append(segment_tangents[-1])
    reference = (0.0, 0.0, 1.0) if abs(tangents[0][2]) < 0.9 else (0.0, 1.0, 0.0)
    first_axis = unit(cross(tangents[0], reference))
    rings = []
    for center, tangent in zip(values, tangents):
        projection = tuple(first_axis[i] - tangent[i] * sum(
            first_axis[j] * tangent[j] for j in range(3)) for i in range(3))
        try:
            first_axis = unit(projection)
        except core.UtilityError:
            first_axis = unit(cross(tangent, reference))
        second_axis = unit(cross(tangent, first_axis))
        rings.append(native_graphics._ring(
            center, radius, first_axis, second_axis, segments))
    faces = [tuple(reversed(rings[0])), rings[-1]]
    for lower, upper in zip(rings, rings[1:]):
        for index in range(segments):
            following = (index + 1) % segments
            faces.append((lower[index], lower[following], upper[following], upper[index]))
    return tuple(faces)


def _draw_pipe_path_3d(points, radius, class_value, color):
    return native_graphics._mesh(
        _tube_path_faces(points, radius), class_value, color)


def _to_local(point_m, origin_document, rotation_deg, factor):
    dx = point_m[0] / factor - origin_document[0]
    dy = point_m[1] / factor - origin_document[1]
    angle = math.radians(-float(rotation_deg))
    cosine, sine = math.cos(angle), math.sin(angle)
    return dx * cosine - dy * sine, dx * sine + dy * cosine


def _repair_duplicate(handle, data):
    route = core.validate_route(data["route"])
    expected = _route_name(route["id"])
    if str(vs.GetName(handle) or "") == expected:
        return data
    if not vs.GetObject(expected):
        vs.SetName(handle, expected)
        return data
    route["id"] = str(uuid.uuid4())
    changed = dict(data, route=route)
    vs.SetName(handle, _route_name(route["id"]))
    _objects().write_data(handle, changed)
    return changed


def draw(handle, data):
    data = _repair_duplicate(handle, data)
    route = read_route(handle, data)
    preferences = settings.validate(data.get("preferences"))
    ensure_classes(route, preferences)
    factor = adapter.units_to_meters()
    origin_m = data.get("origin_m", route["points_m"][0])
    origin = adapter.symbol_location_2d(
        handle, (origin_m[0] / factor, origin_m[1] / factor))
    rotation = float(vs.GetSymRot(handle) or 0.0)
    route_paths = core.render_route_paths(route)
    color = _rgb(route["line_color"])
    control_stations = core.stations(route["points_m"])
    layer_z = native_graphics._layer_z_m(handle)
    for index, path_row in enumerate(route_paths):
        dense_m, dense_stations = path_row
        dense = tuple(_to_local(point, origin, rotation, factor) for point in dense_m)
        dn = route["dns_mm"][index]
        class_value = core.line_class_name(
            preferences["class_prefix"], route["utility_type"], dn)
        if route["graphics_mode"] == "double_line":
            outside = route.get("outside_diameters_mm", route["dns_mm"])[index]
            _draw_band_path(dense, outside / 1000.0 / factor, class_value, color)
            native_graphics._draw_open_polyline(
                dense, preferences["axis_class"], TEXT_COLOR, route["axis_line_type"])
        else:
            native_graphics._draw_open_polyline(dense, class_value, color, route["line_type"])
        if route["draw_3d"]:
            if route.get("surface_profile_stations_m"):
                height_stations = route["surface_profile_stations_m"][index]
                heights = route["surface_profile_heights_m"][index]
            else:
                height_stations = control_stations
                heights = route["route_heights_m"][index]
            radius = route.get("outside_diameters_mm", route["dns_mm"])[index] / 2000.0 / factor
            class_3d = core.line_class_name(
                preferences["class_prefix"], route["utility_type"], dn, "_3D")
            path_3d = []
            for point, station in zip(dense, dense_stations):
                z_value = core.height_at(height_stations, heights, station)
                path_3d.append((point[0], point[1], (z_value - layer_z) / factor))
            _draw_pipe_path_3d(path_3d, radius, class_3d, color)
        if route["show_heights"]:
            control_path_m = core.control_route_paths(route)[index]
            for point_m, height in zip(control_path_m, route["route_heights_m"][index]):
                xy = _to_local(point_m, origin, rotation, factor)
                _text("L%d  %.2f m" % (index + 1, height), xy, -rotation,
                      route, preferences, factor)
    if route["regular_label"]:
        reference_m, _stations = core.rounded_path(
            route["points_m"], route["fillet_radius_m"], route["round_corners"])
        for _station, xy_m, angle in core.sample_path(reference_m, route["label_interval_m"]):
            xy = _to_local(xy_m, origin, rotation, factor)
            _text(route["label_text"], xy,
                  angle - rotation + route.get("label_rotation_deg", 0.0),
                  route, preferences, factor,
                  route["label_frame"], route["label_fill"])
    _draw_fittings(route, origin, preferences, factor, rotation)
    vs.ResetOrientation3D()
    rendered = dict(data, route=route, preferences=preferences,
                    origin_m=(origin[0] * factor, origin[1] * factor),
                    rotation_deg=rotation)
    _objects().write_data(handle, _with_render_status(rendered, RENDER_OK))


def validate_document():
    rows = []
    for handle, data in _objects().objects():
        rows.append(read_route(handle, data))
    data_errors = tuple(_objects().object_errors())
    if data_errors:
        raise core.UtilityError(
            "Beschädigte Leitungstrassen wurden gefunden:\n" +
            "\n".join("• " + value for value in data_errors))
    length_2d = 0.0
    length_3d = 0.0
    covers = []
    cover_shortfalls = 0
    for route in rows:
        control_stations = core.stations(route["points_m"])
        for index, (points, point_stations) in enumerate(core.render_route_paths(route)):
            length_2d += core.stations(points)[-1]
            if route.get("surface_profile_stations_m"):
                height_stations = route["surface_profile_stations_m"][index]
                heights = route["surface_profile_heights_m"][index]
            else:
                height_stations = control_stations
                heights = route["route_heights_m"][index]
            for first, second, station_a, station_b in zip(
                    points, points[1:], point_stations, point_stations[1:]):
                delta_z = (core.height_at(height_stations, heights, station_b) -
                           core.height_at(height_stations, heights, station_a))
                length_3d += math.hypot(math.dist(first, second), delta_z)
            if route.get("surface_profile_surface_m"):
                radius = route["outside_diameters_mm"][index] / 2000.0
                route_covers = tuple(
                    surface - axis - radius for surface, axis in zip(
                        route["surface_profile_surface_m"][index],
                        route["surface_profile_heights_m"][index]))
                covers.extend(route_covers)
                cover_shortfalls += sum(
                    value + 1e-6 < route["cover_depth_m"] for value in route_covers)
    report = {
        "routes": len(rows),
        "lines": sum(route["count"] for route in rows),
        "length_2d_m": length_2d,
        "length_3d_m": length_3d,
        "bends": sum(len(core.bend_rows(route["points_m"])) for route in rows),
        "cover_samples": len(covers),
        "cover_shortfalls": cover_shortfalls,
    }
    report["minimum_cover_m"] = min(covers) if covers else None
    report["maximum_cover_m"] = max(covers) if covers else None
    return report


def reset():
    ok, plugin, handle, _record, _wall = vs.GetCustomObjectInfo()
    if not ok or plugin != _objects().PLUGIN or not handle:
        return
    data = _objects().data_of(handle)
    if not data:
        return
    vs.SetParameterVisibility(handle, "Daten", False)
    vs.EnableParameter(handle, "Nummer", False)
    vs.EnableParameter(handle, "Hoehe_m", False)
    try:
        draw(handle, data)
    except Exception as error:
        try:
            _objects().write_data(
                handle, _with_render_status(data, RENDER_ERROR, error))
        except Exception:
            pass
        vs.TextOrigin((0.0, 0.0))
        vs.CreateText("LEITUNG PRÜFEN: " + str(error))
        adapter.alert("Leitungstrasse konnte nicht neu aufgebaut werden: %s" % error)
