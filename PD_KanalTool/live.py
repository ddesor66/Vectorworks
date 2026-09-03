# -*- coding: utf-8 -*-
"""Vectorworks 2026 PIO graph, 2D/3D rendering and transactional updates."""
from __future__ import absolute_import

import copy
import math
import re
import uuid

import vs

from . import label_layout
from . import core
from . import settings
from . import shaft_sheet
from . import stub_stationing
from . import terrain_rules
from . import ui
from . import vw_adapter as adapter
from PD_ToolsPD.ddvw.vw import site_model


sewer_settings = settings
sewer_ui = ui


ROLES = ("sewer_pipe", "sewer_shaft", "sewer_rigole", "sewer_label", "sewer_fitting",
         "sewer_floor_drain", "sewer_house_connection")
NODE_ROLES = ("sewer_shaft", "sewer_fitting", "sewer_floor_drain",
              "sewer_house_connection")
TEXT_COLOR = (0, 0, 0)
RENDER_OK = "ok"
RENDER_ERROR = "error"
_RENDER_RESULTS = {}
_PENDING_RENDER_CHECKS = set()

# Vectorworks object-association actions. A structural owner deletes its
# dependent object; the dependent object only resets a surviving owner when
# it is deleted directly. Keeping the two directions separate makes the
# normal Delete key safe for a connected network.
DELETE_WITH_OWNER = 4
RESET_ON_OWNER_DELETE = 5


def _render_key(handle):
    """Return a process-local key without writing into the PIO record.

    Writing a render marker with ``SetRField`` from the object's reset event
    schedules another reset in Vectorworks 2026.  That re-entered the current
    PIO while connection commands were still creating their objects and made
    both branch creation and shaft-to-shaft creation roll back.  Object names
    are stable and unique for every managed object, so they are the safest
    key at this API boundary.
    """
    try:
        name = _name(handle)
    except Exception:
        name = ""
    if name:
        return "name:" + name
    try:
        return "handle:%d" % int(handle)
    except (TypeError, ValueError):
        return "wrapper:%d" % id(handle)


def _record_render_result(handle, status, error=None):
    key = _render_key(handle)
    if key in _PENDING_RENDER_CHECKS:
        _RENDER_RESULTS[key] = (
            str(status), "" if error is None else str(error))


def _require_render_ok(handle):
    key = _render_key(handle)
    result = _RENDER_RESULTS.pop(key, None)
    _PENDING_RENDER_CHECKS.discard(key)
    if result and result[0] == RENDER_ERROR:
        detail = result[1]
        raise core.SewerError(
            "Kanalobjekt konnte nicht vollständig neu aufgebaut werden%s." %
            (": " + detail if detail else ""))
    # ResetObject is synchronous in the normal document path.  Vectorworks
    # can defer the reset while an OIP button callback is unwinding, though;
    # absence of a result is therefore not an error.  A later object reset
    # still shows its own explicit error marker and dialog.
    return bool(result and result[0] == RENDER_OK)


def _reset_checked(handle):
    """Reset one PIO and surface a synchronous render failure without re-entry."""
    key = _render_key(handle)
    _RENDER_RESULTS.pop(key, None)
    _PENDING_RENDER_CHECKS.add(key)
    vs.ResetObject(handle)
    return _require_render_ok(handle)


def _live():
    from . import live_objects
    return live_objects


def is_sewer_data(data):
    return isinstance(data, dict) and data.get("schema") == core.SCHEMA and data.get("role") in ROLES


def objects(role=None):
    return _live().objects(role)


def _rgb(value):
    try:
        result = tuple(max(0, min(65535, int(component))) for component in value)
    except (TypeError, ValueError):
        result = TEXT_COLOR
    return result if len(result) == 3 else TEXT_COLOR


def color_for(data, preferences):
    if data.get("role") == "sewer_rigole":
        return _rgb((data.get("rigole") or {}).get("fill_color"))
    payload = data.get("pipe") or data.get("shaft") or {}
    if data.get("role") in NODE_ROLES:
        pen_colors = preferences.get("shaft_pen_colors", preferences["colors"])
        return _rgb(payload.get("pen_color_override") or
                    payload.get("color_override") or pen_colors[payload["kind"]])
    return _rgb(payload.get("color_override") or preferences["colors"][payload["kind"]])


def shaft_graphics_for(shaft, preferences):
    """Return independent contour, fill and transparency for one shaft."""
    kind = shaft["kind"]
    pen_colors = preferences.get("shaft_pen_colors", preferences["colors"])
    fill_colors = preferences.get("shaft_fill_colors", pen_colors)
    transparencies = preferences.get(
        "shaft_fill_transparency_percent",
        {current_kind: 50.0 for current_kind in core.KINDS})
    pen = _rgb(shaft.get("pen_color_override") or
               shaft.get("color_override") or pen_colors[kind])
    fill = _rgb(shaft.get("fill_color_override") or fill_colors[kind])
    transparency = shaft.get("fill_transparency_percent_override")
    if transparency is None:
        transparency = transparencies.get(kind, 50.0)
    transparency = max(0.0, min(100.0, float(transparency)))
    return pen, fill, transparency


def class_name(value, preferences, suffix=""):
    if isinstance(value, dict) and "gross_volume_m3" in value:
        return "%s-Rigole%s" % (preferences["class_prefix"], suffix)
    if isinstance(value, dict) and "dn_mm" in value:
        return core.pipe_class_name(preferences["class_prefix"], value, suffix)
    kind = value.get("kind") if isinstance(value, dict) else value
    structure = value.get("structure_type", "round") if isinstance(value, dict) else "round"
    return core.structure_class_name(
        preferences["class_prefix"], kind, structure, suffix)


def cover_class_name(shaft, preferences, suffix=""):
    return core.cover_class_name(
        preferences["class_prefix"], shaft["kind"], suffix)


def label_class_name(owner_data, preferences, label_data=None):
    """Return the independent class for one component annotation."""
    role = owner_data.get("role")
    if role == "sewer_pipe":
        return core.pipe_label_class_name(
            preferences["text_class"], owner_data["pipe"])
    if role in NODE_ROLES:
        shaft = owner_data["shaft"]
        return core.structure_label_class_name(
            preferences["text_class"], shaft["kind"],
            shaft.get("structure_type", "round"),
            connection=(label_data or {}).get("label_kind") == "connection_height")
    if role == "sewer_rigole":
        return core.rigole_label_class_name(preferences["text_class"])
    return preferences["text_class"]


def axis_class_name(pipe, preferences):
    return core.pipe_class_name(preferences["class_prefix"], pipe, "-Achse")


def _ensure_class(name, color, fill=True, line_type=1, fill_color=None):
    fill_color = color if fill_color is None else fill_color
    vs.NameClass(name)
    vs.SetClUseGraphic(name, True)
    vs.SetClFPat(name, 1 if fill else 0)
    vs.SetClFillFore(name, fill_color)
    vs.SetClFillBack(name, fill_color)
    vs.SetClPenFore(name, color)
    vs.SetClPenBack(name, color)
    vs.SetClLSN(name, int(line_type))
    vs.SetClLW(name, 13)


def ensure_classes(preferences):
    active = str(vs.ActiveClass() or "")
    try:
        for kind in core.KINDS:
            color = _rgb(preferences.get(
                "shaft_pen_colors", preferences["colors"])[kind])
            fill_color = _rgb(preferences.get(
                "shaft_fill_colors", preferences.get(
                    "shaft_pen_colors", preferences["colors"]))[kind])
            for structure in core.STRUCTURE_TYPES:
                for suffix in ("", "_3D"):
                    name = core.structure_class_name(
                        preferences["class_prefix"], kind, structure, suffix)
                    _ensure_class(name, color, fill_color=fill_color)
                _ensure_class(core.structure_label_class_name(
                    preferences["text_class"], kind, structure), TEXT_COLOR,
                    fill=False)
            for suffix in ("", "_3D"):
                _ensure_class(core.cover_class_name(
                    preferences["class_prefix"], kind, suffix), color,
                    fill_color=fill_color)
            for structure in ("round", "special"):
                _ensure_class(core.structure_label_class_name(
                    preferences["text_class"], kind, structure, True),
                    TEXT_COLOR, fill=False)
        for suffix in ("", "_3D"):
            _ensure_class("%s-Rigole%s" % (preferences["class_prefix"], suffix),
                          (36000, 52000, 65535))
        _ensure_class(core.rigole_label_class_name(
            preferences["text_class"]), TEXT_COLOR, fill=False)
        vs.NameClass(preferences["text_class"])
        vs.SetClUseGraphic(preferences["text_class"], True)
        vs.SetClFPat(preferences["text_class"], 0)
        vs.SetClPenFore(preferences["text_class"], TEXT_COLOR)
        vs.SetClPenBack(preferences["text_class"], TEXT_COLOR)
        vs.NameClass(preferences["flow_arrow_class"])
        vs.SetClUseGraphic(preferences["flow_arrow_class"], True)
        vs.SetClFPat(preferences["flow_arrow_class"], 1)
        vs.SetClFillFore(preferences["flow_arrow_class"], TEXT_COLOR)
        vs.SetClFillBack(preferences["flow_arrow_class"], TEXT_COLOR)
        vs.SetClPenFore(preferences["flow_arrow_class"], TEXT_COLOR)
        vs.SetClPenBack(preferences["flow_arrow_class"], TEXT_COLOR)
        vs.SetClLW(preferences["flow_arrow_class"], 13)
    finally:
        if active:
            vs.NameClass(active)


def ensure_pipe_classes(pipe, preferences, color):
    active = str(vs.ActiveClass() or "")
    try:
        _ensure_class(class_name(pipe, preferences), color)
        _ensure_class(class_name(pipe, preferences, "_3D"), color)
        _ensure_class(axis_class_name(pipe, preferences), TEXT_COLOR, fill=False,
                      line_type=preferences["axis_line_type"])
        _ensure_class(core.pipe_label_class_name(
            preferences["text_class"], pipe), TEXT_COLOR, fill=False)
    finally:
        if active:
            vs.NameClass(active)


def _name(handle):
    return str(vs.GetName(handle) or "")


def _handle_by_id(prefix, identity):
    handle = vs.GetObject(prefix + str(identity))
    return handle if handle and int(vs.GetTypeN(handle) or 0) == 86 else None


def _remove_association(owner, kind, target):
    """Remove every duplicate of one exact association, returning its count."""
    if not hasattr(vs, "RemoveAssociation"):
        return 0
    removed = 0
    # Old files can contain duplicates from interrupted transactions. The
    # finite guard also protects against a defective host/mock implementation.
    for _index in range(32):
        if not owner or not target or not vs.RemoveAssociation(owner, kind, target):
            break
        removed += 1
    return removed


def _add_association(owner, kind, target, message):
    if not owner or not target or not vs.AddAssociation(owner, kind, target):
        raise core.SewerError(message)


def _sync_pipe_associations(handle, pipe, endpoint_handles=None):
    """Install deletion-safe bidirectional links for one holding."""
    identities = tuple(dict.fromkeys((pipe["start_id"], pipe["end_id"])))
    if endpoint_handles is None:
        endpoint_handles = {
            identity: _handle_by_id(core.SHAFT_PREFIX, identity)
            for identity in identities}
    endpoints = []
    for identity in identities:
        endpoint = endpoint_handles.get(identity)
        if not endpoint:
            raise core.SewerError(
                "Rohr-Schacht-Verknüpfung fehlt am Anschluss %s." % identity)
        endpoints.append(endpoint)
    # Remove the former shaft->pipe reset link and any duplicate of the new
    # graph before installing exactly one relationship in each direction.
    removed = []
    for endpoint in endpoints:
        for owner, kind, target in (
                (endpoint, RESET_ON_OWNER_DELETE, handle),
                (endpoint, DELETE_WITH_OWNER, handle),
                (handle, RESET_ON_OWNER_DELETE, endpoint)):
            for _index in range(_remove_association(owner, kind, target)):
                removed.append((owner, kind, target))
    added = []
    try:
        for endpoint in endpoints:
            _add_association(
                endpoint, DELETE_WITH_OWNER, handle,
                "Rohr-Schacht-Löschverknüpfung konnte nicht gespeichert werden.")
            added.append((endpoint, DELETE_WITH_OWNER, handle))
            _add_association(
                handle, RESET_ON_OWNER_DELETE, endpoint,
                "Rohr-Schacht-Aktualisierungsverknüpfung konnte nicht gespeichert werden.")
            added.append((handle, RESET_ON_OWNER_DELETE, endpoint))
    except Exception:
        for owner, kind, target in reversed(added):
            _remove_association(owner, kind, target)
        for owner, kind, target in removed:
            vs.AddAssociation(owner, kind, target)
        raise
    return tuple(endpoints)


def _sync_rigole_junction_association(rigole_handle, junction_handle):
    """Delete a rigole connection node with the rigole and refresh survivors."""
    removed = []
    for owner, kind, target in (
            (rigole_handle, RESET_ON_OWNER_DELETE, junction_handle),
            (rigole_handle, DELETE_WITH_OWNER, junction_handle),
            (junction_handle, RESET_ON_OWNER_DELETE, rigole_handle)):
        for _index in range(_remove_association(owner, kind, target)):
            removed.append((owner, kind, target))
    added = []
    try:
        _add_association(
            rigole_handle, DELETE_WITH_OWNER, junction_handle,
            "Rigolen-Anschlussknoten konnte nicht löschsicher verknüpft werden.")
        added.append((rigole_handle, DELETE_WITH_OWNER, junction_handle))
        _add_association(
            junction_handle, RESET_ON_OWNER_DELETE, rigole_handle,
            "Rigolen-Aktualisierungsverknüpfung konnte nicht gespeichert werden.")
        added.append((junction_handle, RESET_ON_OWNER_DELETE, rigole_handle))
    except Exception:
        for owner, kind, target in reversed(added):
            _remove_association(owner, kind, target)
        for owner, kind, target in removed:
            vs.AddAssociation(owner, kind, target)
        raise


def read_shaft(handle, data=None):
    data = data or _live().data_of(handle)
    if not is_sewer_data(data) or data["role"] not in NODE_ROLES:
        raise core.SewerError("Kanalschacht oder Kanalstutzen konnte nicht gelesen werden.")
    shaft = core.validate_shaft(data["shaft"], allow_hidden=True)
    if data["role"] == "sewer_fitting" and shaft["structure_type"] != "stub":
        raise core.SewerError("Als Stutzen geführtes Kanalbauteil besitzt ungültige Daten.")
    if (data["role"] == "sewer_floor_drain" and
            shaft["structure_type"] != "floor_drain"):
        raise core.SewerError("Als Bodenablauf geführtes Kanalbauteil besitzt ungültige Daten.")
    if (data["role"] == "sewer_house_connection" and
            shaft["structure_type"] != "house"):
        raise core.SewerError("Als Hausanschluss geführtes Kanalbauteil besitzt ungültige Daten.")
    if _name(handle) != core.SHAFT_PREFIX + shaft["id"]:
        raise core.SewerError("Schachtidentität wurde geändert oder kopiert.")
    factor = adapter.units_to_meters()
    location = adapter.symbol_location_2d(
        handle, (shaft["x_m"] / factor, shaft["y_m"] / factor))
    shaft["x_m"], shaft["y_m"] = float(location[0]) * factor, float(location[1]) * factor
    return core.validate_shaft(shaft, allow_hidden=True)


def read_rigole(handle, data=None):
    data = data or _live().data_of(handle)
    if not is_sewer_data(data) or data["role"] != "sewer_rigole":
        raise core.SewerError("Rigolenbauwerk konnte nicht gelesen werden.")
    rigole = core.validate_rigole(data["rigole"])
    if _name(handle) != core.RIGOLE_PREFIX + rigole["id"]:
        raise core.SewerError("Rigolenidentität wurde geändert oder kopiert.")
    factor = adapter.units_to_meters()
    location = adapter.symbol_location_2d(
        handle, (rigole["x_m"] / factor, rigole["y_m"] / factor))
    rigole["x_m"], rigole["y_m"] = (
        float(location[0]) * factor, float(location[1]) * factor)
    return core.validate_rigole(rigole)


def shaft_records():
    return tuple((handle, read_shaft(handle, data))
                 for handle, data in objects()
                 if data.get("role") in NODE_ROLES)


def rigole_records():
    return tuple((handle, read_rigole(handle, data))
                 for handle, data in objects("sewer_rigole"))


def _endpoints(pipe):
    start = _handle_by_id(core.SHAFT_PREFIX, pipe["start_id"])
    end = _handle_by_id(core.SHAFT_PREFIX, pipe["end_id"])
    if not start or not end:
        raise core.SewerError("Eine Kanalstrecke besitzt ein gelöschtes oder nicht verbundenes Ende.")
    return (start, read_shaft(start)), (end, read_shaft(end))


def _pipe_following_index():
    """Index valid raw pipes once by their stored flow start."""
    result = {}
    for _handle, raw in objects("sewer_pipe"):
        candidate = raw.get("pipe") if isinstance(raw, dict) else None
        if not isinstance(candidate, dict):
            continue
        try:
            candidate = core.validate_pipe(candidate)
        except core.SewerError:
            continue
        result.setdefault(candidate["start_id"], []).append(candidate)
    return result


def _holding_name_live(pipe, following_index=None):
    """Resolve a holding name without validating unrelated document objects."""
    current = core.validate_pipe(pipe)
    following_index = following_index if following_index is not None else _pipe_following_index()
    current_id = current["end_id"]
    visited = {current["id"]}
    while current_id:
        shaft_handle = _handle_by_id(core.SHAFT_PREFIX, current_id)
        if not shaft_handle:
            break
        shaft = read_shaft(shaft_handle)
        rigole_id = str(shaft.get("rigole_id") or "")
        if rigole_id:
            rigole_handle = _handle_by_id(core.RIGOLE_PREFIX, rigole_id)
            if rigole_handle:
                return "H-" + read_rigole(rigole_handle).get("name", rigole_id)
        if (shaft.get("visible", True) and
                shaft.get("structure_type") not in ("junction", "stub") and
                shaft.get("name")):
            return "H-" + shaft["name"]
        following = [candidate for candidate in following_index.get(current_id, ())
                     if candidate["id"] not in visited]
        if len(following) != 1:
            break
        current = following[0]
        visited.add(current["id"])
        current_id = current["end_id"]
    return current.get("name") or "H-" + str(current_id or current["end_id"])


def read_pipe(handle, data=None, following_index=None):
    data = data or _live().data_of(handle)
    if not is_sewer_data(data) or data["role"] != "sewer_pipe":
        raise core.SewerError("Kanalstrecke konnte nicht gelesen werden.")
    pipe = core.validate_pipe(data["pipe"])
    if _name(handle) != core.PIPE_PREFIX + pipe["id"]:
        raise core.SewerError("Rohridentität wurde geändert oder kopiert.")
    (_start_handle, start), (_end_handle, end) = _endpoints(pipe)
    pipe["length_m"] = math.dist((start["x_m"], start["y_m"]), (end["x_m"], end["y_m"]))
    pipe["name"] = _holding_name_live(pipe, following_index)
    return core.validate_pipe(pipe)


def pipe_records():
    rows = tuple(objects("sewer_pipe"))
    following_index = _pipe_following_index()
    return tuple((handle, read_pipe(handle, data, following_index)) for handle, data in rows)


def shaft_connection_views(shaft, clock_mode="plan_north", north_rotation_deg=0.0):
    """Derive every individual live connection without duplicating shaft data."""
    return shaft_sheet.derive_connections(
        shaft,
        tuple(pipe for _handle, pipe in pipe_records()),
        tuple(value for _handle, value in shaft_records()),
        clock_mode,
        north_rotation_deg,
    )


def _existing_names():
    return {shaft["name"] for _handle, shaft in shaft_records() if shaft["visible"]}


def _next_numbers():
    result = {kind: 1 for kind in core.KINDS}
    for name in _existing_names():
        match = re.fullmatch(r"(RW|SW|MW)\.(\d+)", name)
        if match:
            result[match.group(1)] = max(result[match.group(1)], int(match.group(2)) + 1)
    return result


def _next_named_number(prefix):
    pattern = re.compile(re.escape(str(prefix)) + r"\.(\d+)$", re.IGNORECASE)
    result = 1
    for name in _existing_names():
        match = pattern.fullmatch(name)
        if match:
            result = max(result, int(match.group(1)) + 1)
    return "%s.%03d" % (prefix, result)


def _next_rigole_name():
    result = 1
    pattern = re.compile(r"RIG\.(\d+)$", re.IGNORECASE)
    for _handle, data in objects("sewer_rigole"):
        match = pattern.fullmatch(str((data.get("rigole") or {}).get("name") or ""))
        if match:
            result = max(result, int(match.group(1)) + 1)
    return "RIG.%03d" % result


def selected_managed():
    result = {}
    for handle in adapter.selected_handles():
        data = _live().data_of(handle)
        if not is_sewer_data(data):
            continue
        if data["role"] == "sewer_label":
            handle = vs.GetObject(data["owner"])
            data = _live().data_of(handle)
        if is_sewer_data(data) and data["role"] != "sewer_label":
            result[_name(handle)] = (handle, data)
    return tuple(result.values())


def selected_source_paths():
    paths = []
    for handle in adapter.selected_handles():
        object_type = adapter.object_type(handle)
        if object_type not in (adapter.TYPE_LINE, adapter.TYPE_POLYGON, adapter.TYPE_POLYLINE):
            continue
        source = adapter.extract_path(handle)
        if source.get("curve"):
            raise core.SewerError(
                "Gebogene Polylinien müssen vor der Kanalumwandlung in gerade Teilstrecken zerlegt werden; "
                "die Originalkurve bleibt unverändert.")
        points = list(source["points"])
        if object_type in (adapter.TYPE_POLYGON, adapter.TYPE_POLYLINE) and vs.IsPolyClosed(handle):
            points.append(points[0])
        paths.append(core.path(points))
    return tuple(paths)


def _new_object(xy_m, role, payload, preferences, created):
    factor = adapter.units_to_meters()
    identity = payload["id"]
    prefixes = {"sewer_shaft": core.SHAFT_PREFIX,
                "sewer_fitting": core.SHAFT_PREFIX,
                "sewer_floor_drain": core.SHAFT_PREFIX,
                "sewer_house_connection": core.SHAFT_PREFIX,
                "sewer_pipe": core.PIPE_PREFIX,
                "sewer_rigole": core.RIGOLE_PREFIX}
    keys = {"sewer_shaft": "shaft", "sewer_fitting": "shaft",
            "sewer_floor_drain": "shaft", "sewer_house_connection": "shaft",
            "sewer_pipe": "pipe",
            "sewer_rigole": "rigole"}
    if role not in prefixes:
        raise core.SewerError("Unbekannter Kanalobjekttyp.")
    prefix = prefixes[role]
    data = {"schema": core.SCHEMA, "role": role,
            "preferences": copy.deepcopy(preferences),
            keys[role]: copy.deepcopy(payload)}
    handle = _live()._new_object((xy_m[0] / factor, xy_m[1] / factor), data,
                                 prefix + identity, created)
    return handle


def _node_role(shaft):
    """Return the persistent semantic role of one network node."""
    return {
        "stub": "sewer_fitting",
        "floor_drain": "sewer_floor_drain",
        "house": "sewer_house_connection",
    }.get(shaft.get("structure_type"), "sewer_shaft")


def _paper_offset_units(handle, preferences):
    factor = adapter.units_to_meters()
    scale = max(1.0, float(vs.GetLScale(vs.GetLayer(handle)) or 1.0))
    return preferences["text_offset_mm"] / 1000.0 * scale / factor


def _default_label_position(owner, data):
    factor = adapter.units_to_meters()
    preferences = data["preferences"]
    offset = _paper_offset_units(owner, preferences)
    if data["role"] in NODE_ROLES:
        shaft = read_shaft(owner, data)
        return (shaft["x_m"] / factor + core.shaft_outer_diameter_m(shaft) / factor / 2.0 + offset,
                shaft["y_m"] / factor + offset)
    if data["role"] == "sewer_rigole":
        rigole = read_rigole(owner, data)
        return rigole["x_m"] / factor, rigole["y_m"] / factor
    pipe = read_pipe(owner, data)
    (_a, start), (_b, end) = _endpoints(pipe)
    first = start["x_m"] / factor, start["y_m"] / factor
    second = end["x_m"] / factor, end["y_m"] / factor
    dx, dy = second[0] - first[0], second[1] - first[1]
    length = math.hypot(dx, dy)
    nx, ny = -dy / length, dx / length
    distance = pipe["dn_mm"] / 2000.0 / factor + offset
    return ((first[0] + second[0]) * 0.5 + nx * distance,
            (first[1] + second[1]) * 0.5 + ny * distance)


def _connection_label_position(shaft, row, index, factor):
    """Return the automatic world position of one shaft endpoint label."""
    base_radius_m = max(core.shaft_outer_diameter_m(shaft) * 0.5, 0.25)
    # Alternating radial spacing prevents coincident texts at nearby endpoints,
    # while every label still starts on its actual connection ray.
    offset_m = base_radius_m + 0.16 + (index % 2) * 0.07
    ux, uy = row["direction"]
    return (shaft["x_m"] / factor + ux * offset_m / factor,
            shaft["y_m"] / factor + uy * offset_m / factor)


def _connection_label_context(owner, owner_data, connection_id, include_hidden=False):
    """Resolve a persisted connection id to its current derived shaft row."""
    if owner_data.get("role") != "sewer_shaft":
        return None
    if not owner_data.get("preferences", {}).get(
            "shaft_connection_labels_visible", True):
        return None
    shaft = read_shaft(owner, owner_data)
    if (not shaft.get("visible", True) or
            shaft.get("structure_type", "round") not in ("round", "special")):
        return None
    rows = shaft_connection_views(shaft)
    for index, row in enumerate(rows):
        if row["connection_id"] == connection_id:
            counts = {
                role: sum(1 for candidate in rows if candidate["role"] == role)
                for role in ("in", "out")}
            return shaft, row, index, counts
    return None


def _label_default_position(owner, owner_data, label_data=None):
    """Return the automatic position for the primary or an endpoint label."""
    if (label_data or {}).get("label_kind") == "connection_height":
        context = _connection_label_context(
            owner, owner_data, label_data.get("connection_id", ""), True)
        if context:
            shaft, row, index, _counts = context
            return _connection_label_position(
                shaft, row, index, adapter.units_to_meters())
    return _default_label_position(owner, owner_data)


def _ensure_connection_height_labels(owner, data, created):
    """Create one independently movable label PIO per current shaft endpoint."""
    if data.get("role") != "sewer_shaft":
        return data
    if not data.get("preferences", {}).get(
            "shaft_connection_labels_visible", True):
        return data
    shaft = read_shaft(owner, data)
    if (not shaft.get("visible", True) or
            shaft.get("structure_type", "round") not in ("round", "special")):
        return data
    owner_name = _name(owner)
    rows = shaft_connection_views(shaft)
    labels = list(dict.fromkeys(data.get("labels", ())))
    factor = adapter.units_to_meters()
    for index, row in enumerate(rows):
        identity = str(uuid.uuid5(
            uuid.NAMESPACE_URL,
            owner_name + ":connection-height:" + row["connection_id"]))
        name = core.LABEL_PREFIX + identity
        label = vs.GetObject(name)
        if label:
            label_data = _live().data_of(label)
            if (not is_sewer_data(label_data) or
                    label_data.get("role") != "sewer_label" or
                    label_data.get("owner") != owner_name or
                    label_data.get("label_kind") != "connection_height" or
                    label_data.get("connection_id") != row["connection_id"]):
                raise core.SewerError(
                    "Name einer Zu-/Ablaufbeschriftung ist bereits belegt.")
        else:
            position = _connection_label_position(shaft, row, index, factor)
            payload = {
                "schema": core.SCHEMA, "role": "sewer_label", "id": identity,
                "owner": owner_name, "owner_role": "sewer_shaft",
                "label_kind": "connection_height",
                "connection_id": row["connection_id"],
                "auto_position": True,
                "auto_xy": [position[0], position[1]],
                "preferences": copy.deepcopy(data["preferences"]),
            }
            label = _live()._new_object(
                (position[0], position[1]), payload, name, created)
            layer = vs.GetLayer(owner)
            if (vs.GetParent(label) != layer and
                    (not vs.SetParent(label, layer) or vs.GetParent(label) != layer)):
                raise core.SewerError(
                    "Zu-/Ablaufbeschriftung konnte nicht auf der Objektebene angelegt werden.")
            if not vs.AddAssociation(owner, 4, label):
                raise core.SewerError(
                    "Verknüpfung der Zu-/Ablaufbeschriftung konnte nicht gespeichert werden.")
        if name not in labels:
            labels.append(name)
    updated = copy.deepcopy(data)
    updated["labels"] = labels
    if updated != data:
        _live().write_data(owner, updated)
    return updated


def ensure_label(owner, data, created):
    identity = str(uuid.uuid5(uuid.NAMESPACE_URL, _name(owner) + ":channel-label"))
    name = core.LABEL_PREFIX + identity
    label = vs.GetObject(name)
    if data.get("role") in NODE_ROLES:
        shaft = read_shaft(owner, data)
        if not core.shaft_primary_label_visible(
                shaft, shaft_connection_views(shaft)):
            # Existing files may already contain this generated label PIO.
            # Resetting it clears its old geometry while retaining the owner
            # association for safe cleanup with the node. New terminal nodes
            # do not create the redundant PIO at all.
            if label:
                vs.ResetObject(label)
            _ensure_connection_height_labels(owner, data, created)
            return None
    if label:
        label_data = _live().data_of(label)
        if not is_sewer_data(label_data) or label_data.get("owner") != _name(owner):
            raise core.SewerError("Name der Kanalbeschriftung ist bereits belegt.")
    else:
        position = _default_label_position(owner, data)
        payload = {"schema": core.SCHEMA, "role": "sewer_label", "id": identity,
                   "owner": _name(owner), "owner_role": data["role"],
                   "auto_position": True, "auto_xy": [position[0], position[1]],
                   "preferences": copy.deepcopy(data["preferences"])}
        label = _live()._new_object((position[0], position[1]), payload, name, created)
        layer = vs.GetLayer(owner)
        if vs.GetParent(label) != layer and (not vs.SetParent(label, layer) or vs.GetParent(label) != layer):
            raise core.SewerError("Kanalbeschriftung konnte nicht auf der Objektebene angelegt werden.")
        if not vs.AddAssociation(owner, 4, label):
            raise core.SewerError("Verknüpfung der Kanalbeschriftung konnte nicht gespeichert werden.")
    updated = copy.deepcopy(data)
    updated["labels"] = [name] + [
        value for value in data.get("labels", ()) if value != name]
    _live().write_data(owner, updated)
    updated = _ensure_connection_height_labels(owner, updated, created)
    return label


def _ensure_endpoint_labels(pipes, created, snapshots=None):
    """Reconcile labels at every existing real shaft touched by new pipes.

    New branches can terminate at an already existing shaft that is not part
    of the newly created object list.  Without this explicit pass its second
    inlet exists in the topology but the independent Z2 label PIO is missing.
    Stutzen are deliberately ignored here: their one fitting label belongs to
    the fitting itself and they are not shaft inlet/outlet annotations.
    """
    snapshots = snapshots if snapshots is not None else {}
    touched = []
    for identity in dict.fromkeys(
            endpoint for pipe in pipes
            for endpoint in (pipe["start_id"], pipe["end_id"])):
        handle = _handle_by_id(core.SHAFT_PREFIX, identity)
        if not handle:
            continue
        data = _live().data_of(handle)
        if not is_sewer_data(data) or data.get("role") != "sewer_shaft":
            continue
        shaft = read_shaft(handle, data)
        if (not shaft.get("visible", True) or
                shaft.get("structure_type", "round") not in ("round", "special")):
            continue
        if handle not in created and handle not in snapshots:
            snapshots[handle] = copy.deepcopy(data)
        ensure_label(handle, data, created)
        touched.append(handle)
    return tuple(dict.fromkeys(touched))


def _reset_labels(data):
    for name in data.get("labels", ()):
        handle = vs.GetObject(name)
        if handle:
            label_data = _live().data_of(handle)
            if label_data and label_data.get("auto_position", True):
                actual = adapter.symbol_location_2d(
                    handle, label_data.get("auto_xy"))
                old_auto = tuple(label_data.get("auto_xy", actual))
                if math.dist(actual, old_auto) > 1e-5:
                    label_data["auto_position"] = False
                    _live().write_data(handle, label_data)
                else:
                    owner = vs.GetObject(label_data.get("owner", ""))
                    owner_data = _live().data_of(owner)
                    if owner and is_sewer_data(owner_data):
                        target = _label_default_position(owner, owner_data, label_data)
                        vs.HMove(handle, target[0] - actual[0], target[1] - actual[1])
                        label_data["auto_xy"] = [target[0], target[1]]
                        _live().write_data(handle, label_data)
            vs.ResetObject(handle)


def create(paths, options, preferences):
    paths = tuple(core.path(value) for value in paths)
    if not paths:
        raise core.SewerError("Keine geeignete Kanalstrecke vorhanden.")
    preferences = settings.validate(preferences)
    ensure_classes(preferences)
    existing = tuple(shaft for _handle, shaft in shaft_records())
    built = core.build_network(paths, options, existing, _next_numbers())
    created = []
    existing_shaft_snapshots = {}
    try:
        shaft_handles = {}
        for shaft in built["shafts"]:
            handle = _new_object((shaft["x_m"], shaft["y_m"]), _node_role(shaft), shaft,
                                 preferences, created)
            shaft_handles[shaft["id"]] = handle
        for _handle, shaft in shaft_records():
            shaft_handles[shaft["id"]] = _handle
        pipe_handles = []
        for pipe in built["pipes"]:
            handle = _new_object((0.0, 0.0), "sewer_pipe", pipe, preferences, created)
            pipe_handles.append(handle)
            _sync_pipe_associations(handle, pipe, shaft_handles)
        owners = list(shaft_handles.values()) + pipe_handles
        existing_shaft_snapshots = {
            handle: copy.deepcopy(_live().data_of(handle))
            for handle in shaft_handles.values() if handle not in created}
        for owner in owners:
            data = _live().data_of(owner)
            if data["role"] == "sewer_shaft" and not data["shaft"]["visible"]:
                continue
            ensure_label(owner, data, created)
        touched_shafts = _ensure_endpoint_labels(
            built["pipes"], created, existing_shaft_snapshots)
        for handle in created:
            _reset_checked(handle)
        for shaft_handle in tuple(shaft_handles.values()) + touched_shafts:
            if shaft_handle not in created:
                _reset_checked(shaft_handle)
        validate_document(preferences)
    except Exception:
        for handle in reversed(created):
            if handle:
                vs.DelObject(handle)
        for existing_handle, snapshot in existing_shaft_snapshots.items():
            _live().write_data(existing_handle, snapshot)
            vs.ResetObject(existing_handle)
        raise
    vs.DSelectAll()
    for handle in pipe_handles:
        vs.SetSelect(handle)
    vs.ReDrawAll()
    return tuple(pipe_handles)


def create_rigole(point_m, values, preferences):
    """Create one managed rigole plus its initially centred movable label."""
    xy = core.point(point_m)
    preferences = sewer_settings.validate(preferences)
    ensure_classes(preferences)
    supplied = dict(values or {})
    supplied.update(schema=core.SCHEMA, id=str(uuid.uuid4()),
                    name=str(supplied.get("name") or _next_rigole_name()),
                    x_m=xy[0], y_m=xy[1], connections=[])
    rigole = core.validate_rigole(supplied)
    created = []
    vs.NameUndoEvent("PD Rigolenbauwerk einsetzen")
    try:
        handle = _new_object(xy, "sewer_rigole", rigole, preferences, created)
        ensure_label(handle, _live().data_of(handle), created)
        for created_handle in created:
            _reset_checked(created_handle)
    except Exception:
        for created_handle in reversed(created):
            if created_handle:
                vs.DelObject(created_handle)
        raise
    vs.DSelectAll()
    vs.SetSelect(handle)
    vs.ReDrawAll()
    return handle


def update_rigole(handle, changes, preferences):
    """Update engineering and appearance fields without changing identity."""
    data = _live().data_of(handle)
    original = read_rigole(handle, data)
    allowed = {
        "name", "length_m", "width_m", "height_m", "bottom_m",
        "terrain_top_m", "rotation_deg", "slope_angle_deg", "fill_color",
        "pen_color", "transparency_percent", "note",
    }
    updated = dict(original)
    updated.update({key: copy.deepcopy(value) for key, value in dict(changes or {}).items()
                    if key in allowed})
    updated = core.validate_rigole(updated)
    # Existing side references are dimensionless. Their positions therefore
    # remain valid after length, width or rotation changes.
    preferences = sewer_settings.validate(preferences)
    snapshot = copy.deepcopy(data)
    vs.NameUndoEvent("PD Rigolenbauwerk bearbeiten")
    try:
        _live().write_data(handle, dict(
            data, rigole=updated, preferences=copy.deepcopy(preferences)))
        _reset_checked(handle)
        _reset_labels(_live().data_of(handle))
    except Exception:
        _live().write_data(handle, snapshot)
        vs.ResetObject(handle)
        raise
    vs.ReDrawAll()
    return True


def connect_selected_shafts(handles, options, preferences):
    """Create one holding between exactly two existing visible shafts."""
    values = tuple(handles)
    if len(values) != 2:
        raise core.SewerError("Zum Verbinden genau zwei vorhandene Schächte markieren.")
    shaft_rows = []
    for handle in values:
        data = _live().data_of(handle)
        if not is_sewer_data(data) or data.get("role") != "sewer_shaft":
            raise core.SewerError("Zum Verbinden dürfen nur zwei Schächte markiert sein.")
        shaft_rows.append((handle, read_shaft(handle, data)))
    preferences = settings.validate(preferences)
    ensure_classes(preferences)
    pipe = core.pipe_between_shafts(
        shaft_rows[0][1], shaft_rows[1][1], options,
        (value for _handle, value in pipe_records()))
    prospective_pipes = [value for _handle, value in pipe_records()] + [pipe]
    prospective_shafts = [value for _handle, value in shaft_records()]
    core.validate_network(prospective_pipes, prospective_shafts)
    vs.NameUndoEvent("PD Zwei Schächte verbinden")
    created = []
    shaft_snapshots = {
        handle: copy.deepcopy(_live().data_of(handle))
        for handle, _shaft in shaft_rows}
    try:
        pipe_handle = _new_object((0.0, 0.0), "sewer_pipe", pipe, preferences, created)
        _associate_pipe(pipe_handle, pipe)
        ensure_label(pipe_handle, _live().data_of(pipe_handle), created)
        for shaft_handle, _shaft in shaft_rows:
            ensure_label(shaft_handle, _live().data_of(shaft_handle), created)
        for created_handle in created:
            _reset_checked(created_handle)
        for shaft_handle, _shaft in shaft_rows:
            _reset_checked(shaft_handle)
            _reset_labels(_live().data_of(shaft_handle))
        validate_document(preferences)
    except Exception:
        for created_handle in reversed(created):
            if created_handle:
                vs.DelObject(created_handle)
        for shaft_handle, _shaft in shaft_rows:
            _live().write_data(shaft_handle, shaft_snapshots[shaft_handle])
            vs.ResetObject(shaft_handle)
            _reset_labels(_live().data_of(shaft_handle))
        raise
    vs.DSelectAll()
    vs.SetSelect(pipe_handle)
    vs.ReDrawAll()
    return pipe_handle


def _detach_pipe_endpoint_associations(handle, data):
    """Detach every endpoint link before a controlled pipe replacement."""
    if not isinstance(data, dict) or data.get("role") != "sewer_pipe":
        return ()
    pipe = data.get("pipe")
    if not isinstance(pipe, dict):
        return ()
    detached = []
    for identity in dict.fromkeys((pipe.get("start_id"), pipe.get("end_id"))):
        if not identity:
            continue
        shaft_handle = _handle_by_id(core.SHAFT_PREFIX, identity)
        if not shaft_handle:
            continue
        for owner, kind, target in (
                (shaft_handle, DELETE_WITH_OWNER, handle),
                (shaft_handle, RESET_ON_OWNER_DELETE, handle),
                (handle, RESET_ON_OWNER_DELETE, shaft_handle)):
            for _index in range(_remove_association(owner, kind, target)):
                detached.append((owner, kind, target))
    return tuple(detached)


def _restore_pipe_endpoint_associations(handle, associations):
    """Restore exact endpoint links removed for a failed replacement."""
    failures = []
    for owner, kind, target in associations:
        if not owner or not target or not vs.AddAssociation(owner, kind, target):
            failures.append(_name(owner) if owner else "unbekanntes Kanalobjekt")
    return tuple(failures)


def _delete_with_labels(handle, data, verify=False):
    """Delete an owner and its dependent labels in Vectorworks-safe order.

    Vectorworks refuses to delete a channel owner while its kind-4 label PIO
    or a shaft-to-pipe association still exists.  Labels and incoming endpoint
    links therefore have to disappear first.  For verified replacement
    transactions, a rejected owner deletion recreates both dependencies before
    the caller rolls the newly created replacement objects back.
    """
    owner_name = _name(handle)
    label_names = tuple(str(name) for name in data.get("labels", ()))
    for name in label_names:
        label = vs.GetObject(name)
        if label:
            vs.DelObject(label)
    if verify:
        remaining = [name for name in label_names if vs.GetObject(name)]
        if remaining:
            raise core.SewerError(
                "Die alte Kanalbeschriftung konnte nicht gelöscht werden: %s"
                % ", ".join(remaining))

    detached_owners = _detach_pipe_endpoint_associations(handle, data)
    vs.DelObject(handle)
    if verify and owner_name and vs.GetObject(owner_name):
        restoration_errors = []
        association_errors = _restore_pipe_endpoint_associations(
            handle, detached_owners)
        if association_errors:
            restoration_errors.append(
                "Schachtverknüpfung (%s)" % ", ".join(association_errors))
        if is_sewer_data(data):
            restored = []
            try:
                ensure_label(handle, data, restored)
                for restored_handle in restored:
                    vs.ResetObject(restored_handle)
            except Exception:
                for restored_handle in reversed(restored):
                    if restored_handle:
                        vs.DelObject(restored_handle)
                restoration_errors.append("Beschriftung")
        if restoration_errors:
            raise core.SewerError(
                "Die alte Haltung blieb erhalten; Wiederherstellung fehlgeschlagen: %s."
                % ", ".join(restoration_errors))
        raise core.SewerError(
            "Die ersetzte Kanalhaltung konnte nicht gelöscht werden: %s" % owner_name)


def _associate_pipe(handle, pipe):
    return _sync_pipe_associations(handle, pipe)


def _stub_reference_updates(original, first, second):
    """Replace a split main-pipe id in every adjacent station reference."""
    updates = {}
    for shaft_handle, shaft in shaft_records():
        references = []
        if shaft.get("structure_type") == "stub" and shaft.get("stub"):
            references.append("stub")
        if shaft.get("connection_station"):
            references.append("connection_station")
        local_fields = [field for field in references
                        if original["id"] in shaft[field].get("main_pipe_ids", ())]
        axis_fields = [field for field in references
                       if original["id"] in shaft[field].get(
                           "station_pipe_ids", shaft[field].get("main_pipe_ids", ()))]
        if not local_fields and not axis_fields:
            continue
        value = copy.deepcopy(shaft)
        if local_fields:
            if shaft["id"] == original["start_id"]:
                replacement = first["id"]
            elif shaft["id"] == original["end_id"]:
                replacement = second["id"]
            else:
                raise core.SewerError(
                    "Eine bestehende Anschlussreferenz liegt nicht am Ende der geteilten Haltung.")
        for field in local_fields:
            value[field]["main_pipe_ids"] = [
                replacement if identity == original["id"] else identity
                for identity in value[field]["main_pipe_ids"]]
        for field in axis_fields:
            station_ids = shaft[field].get(
                "station_pipe_ids", shaft[field].get("main_pipe_ids", ()))
            expanded = []
            for identity in station_ids:
                if identity == original["id"]:
                    expanded.extend((first["id"], second["id"]))
                else:
                    expanded.append(identity)
            value[field]["station_pipe_ids"] = expanded
        updates[shaft_handle] = core.validate_shaft(value, allow_hidden=True)
    return updates


def _station_axis_link(axis_pipes, main_pipe_ids):
    """Return current end references for one unbranched holding axis."""
    axis_pipes = tuple(core.validate_pipe(pipe) for pipe in axis_pipes)
    main_pipe_ids = tuple(str(identity) for identity in main_pipe_ids)
    if len(main_pipe_ids) != 2 or any(
            identity not in {pipe["id"] for pipe in axis_pipes}
            for identity in main_pipe_ids):
        raise core.SewerError(
            "Die beiden Hauptarme der Anschlussstationierung fehlen in der Haltung.")
    degree = {}
    endpoint_rows = {}
    for pipe in axis_pipes:
        for identity, invert, role in (
                (pipe["start_id"], pipe["start_invert_m"], "start"),
                (pipe["end_id"], pipe["end_invert_m"], "end")):
            degree[identity] = degree.get(identity, 0) + 1
            endpoint_rows.setdefault(identity, []).append((invert, role))
    endpoint_ids = sorted(identity for identity, count in degree.items() if count == 1)
    if len(endpoint_ids) != 2:
        raise core.SewerError(
            "Die Endschächte der Haltung für die Anschlussstationierung sind nicht eindeutig.")

    def endpoint(identity):
        rows = endpoint_rows[identity]
        if len(rows) != 1:
            raise core.SewerError(
                "Die Endhöhe der Haltung für die Anschlussstationierung ist nicht eindeutig.")
        return identity, rows[0][0], rows[0][1]

    first_end, second_end = (endpoint(identity) for identity in endpoint_ids)
    if first_end[1] > second_end[1]:
        start, end = first_end, second_end
    elif second_end[1] > first_end[1]:
        start, end = second_end, first_end
    elif first_end[2] == "start" and second_end[2] == "end":
        start, end = first_end, second_end
    elif second_end[2] == "start" and first_end[2] == "end":
        start, end = second_end, first_end
    else:
        start, end = first_end, second_end
    return {
        "main_start_id": start[0], "main_end_id": end[0],
        "main_pipe_ids": list(main_pipe_ids),
        "station_pipe_ids": [pipe["id"] for pipe in axis_pipes],
    }


def _new_connection_station(original, first, second):
    """Link a new connection to the complete holding and both real ends."""
    _current, pipe_map, component = _holding_component(original)
    axis_pipes = [pipe_map[identity] for identity in component
                  if identity != original["id"]] + [first, second]
    return dict(
        _station_axis_link(axis_pipes, (first["id"], second["id"])),
        station_enabled=True,
        station_m=None, station_zero_id="",
        station_zero_name="", station_equal_inverts=False,
        station_basis="",
    )


def split_selected(handle, point_m, preferences):
    """Split one selected pipe at an interior click and add a connected shaft."""
    data = _live().data_of(handle)
    pipe = read_pipe(handle, data)
    (start_handle, start), (end_handle, end) = _endpoints(pipe)
    fraction, xy = core.project_on_pipe(
        (start["x_m"], start["y_m"]), (end["x_m"], end["y_m"]), point_m)
    shaft_id = str(uuid.uuid4())
    first, second = core.split_pipe(
        pipe, shaft_id, fraction, preserve_first_identity=True)
    stub_updates = _stub_reference_updates(pipe, first, second)
    ks_m = first["end_invert_m"]
    next_number = _next_numbers()[pipe["kind"]]
    shaft = core.validate_shaft({
        "schema": core.SCHEMA, "id": shaft_id, "kind": pipe["kind"],
        "name": "%s.%03d" % (pipe["kind"], next_number),
        "note": "",
        "x_m": xy[0], "y_m": xy[1], "kd_m": ks_m + preferences["cover_offset_m"],
        "ks_m": ks_m, "diameter_m": preferences["shaft_diameter_m"], "visible": True,
        "construction_material": preferences["shaft_construction_material"],
        "wall_thickness_m": preferences["shaft_wall_thickness_m"],
        "cover_diameter_m": preferences["shaft_cover_diameter_m"],
        "cover_symbol": preferences["shaft_cover_symbol"],
        "cover_placement": preferences["shaft_cover_placement"],
        "cover_rotation_deg": preferences["shaft_cover_rotation_deg"],
        "color_override": copy.deepcopy(pipe.get("color_override")),
    })
    prospective_pipes = [value for existing_handle, value in pipe_records()
                         if existing_handle != handle] + [first, second]
    prospective_shafts = [stub_updates.get(existing_handle, value)
                          for existing_handle, value in shaft_records()] + [shaft]
    core.validate_network(prospective_pipes, prospective_shafts)
    vs.NameUndoEvent("PD Kanalstrecke teilen")
    created = []
    owner_snapshot = copy.deepcopy(data)
    original_endpoint_handles = {
        pipe["start_id"]: start_handle, pipe["end_id"]: end_handle}
    owner_mutated = False
    snapshots = {existing_handle: copy.deepcopy(_live().data_of(existing_handle))
                 for existing_handle in stub_updates}
    try:
        shaft_handle = _new_object(xy, _node_role(shaft), shaft, preferences, created)
        pipe_handles = [handle]
        new_handle = _new_object(
            (0.0, 0.0), "sewer_pipe", second, preferences, created)
        pipe_handles.append(new_handle)
        _associate_pipe(new_handle, second)
        owner_mutated = True
        _detach_pipe_endpoint_associations(handle, owner_snapshot)
        _live().write_data(handle, dict(
            owner_snapshot, pipe=first,
            preferences=copy.deepcopy(preferences)))
        _sync_pipe_associations(handle, first, {
            first["start_id"]: start_handle, first["end_id"]: shaft_handle})
        for owner in (shaft_handle,) + tuple(pipe_handles):
            ensure_label(owner, _live().data_of(owner), created)
        touched_shafts = _ensure_endpoint_labels(
            (first, second), created, snapshots)
        for existing_handle, value in stub_updates.items():
            _live().write_data(existing_handle, dict(
                snapshots[existing_handle], shaft=value,
                preferences=copy.deepcopy(preferences)))
        for created_handle in created:
            _reset_checked(created_handle)
        _reset_checked(handle)
        for existing_handle in stub_updates:
            _reset_checked(existing_handle)
        for existing_handle in touched_shafts:
            if existing_handle not in stub_updates:
                _reset_checked(existing_handle)
    except Exception:
        if owner_mutated:
            _live().write_data(handle, owner_snapshot)
            _sync_pipe_associations(handle, pipe, original_endpoint_handles)
            vs.ResetObject(handle)
        for existing_handle, snapshot in snapshots.items():
            _live().write_data(existing_handle, snapshot)
            vs.ResetObject(existing_handle)
        for created_handle in reversed(created):
            if created_handle:
                vs.DelObject(created_handle)
        raise
    vs.DSelectAll()
    for pipe_handle in pipe_handles:
        vs.SetSelect(pipe_handle)
    vs.ReDrawAll()
    return tuple(pipe_handles)


def connect_branch(handle, point_m, branch_paths, options, preferences):
    """Split one pipe and add a height-matched branch in one transaction."""
    data = _live().data_of(handle)
    original = read_pipe(handle, data)
    (start_handle, start), (end_handle, end) = _endpoints(original)
    fraction, xy = core.project_on_pipe(
        (start["x_m"], start["y_m"]), (end["x_m"], end["y_m"]), point_m)
    paths = tuple(
        core.soften_connection_bends(value)
        if options.get("as_stub") else core.path(value)
        for value in branch_paths)
    if not paths or math.dist(paths[0][0], xy) > 0.001:
        raise core.SewerError("Die neue Leitung beginnt nicht am gewählten Anschlusspunkt.")
    shaft_id = str(uuid.uuid4())
    first, second = core.split_pipe(
        original, shaft_id, fraction, preserve_first_identity=True)
    stub_updates = _stub_reference_updates(original, first, second)
    station_reference = _new_connection_station(original, first, second)
    main_connection_invert = first["end_invert_m"]
    alignment = str(options.get("connection_alignment", "invert"))
    connection_invert = core.connection_invert(
        main_connection_invert, original["dn_mm"], options.get("dn_mm"), alignment)
    options = dict(options)
    if options.get("terminal_invert_m") is not None:
        options.update(kind=original["kind"], start_invert_m=options["terminal_invert_m"],
                       calculation_mode="end", calculation_value=connection_invert,
                       reverse_flow=True)
    else:
        options.update(kind=original["kind"], start_invert_m=connection_invert,
                       calculation_mode="start", reverse_flow=True)
    numbers = _next_numbers()
    shaft = core.validate_shaft({
        "schema": core.SCHEMA, "id": shaft_id, "kind": original["kind"],
        "name": core._shaft_name(original["kind"], numbers), "note": "",
        "x_m": xy[0], "y_m": xy[1],
        "kd_m": core.number(options.get("cover_height_m"), "Deckelhöhe"),
        "ks_m": min(main_connection_invert, connection_invert),
        "diameter_m": (0.0 if options.get("as_stub") else
                       core.number(options.get("shaft_diameter_m", 0.0), "Schachtdurchmesser")),
        "construction_material": core.shaft_construction_material(
            options.get("shaft_construction_material", "PP")),
        "wall_thickness_m": core.number(
            options.get("shaft_wall_thickness_m", core.DEFAULT_CONCRETE_WALL_THICKNESS_M),
            "Schachtwandstärke"),
        "cover_diameter_m": core.number(options.get("cover_diameter_m", 0.625),
                                        "Schachtdeckeldurchmesser"),
        "cover_symbol": str(options.get("cover_symbol") or ""),
        "cover_placement": str(options.get("cover_placement", "auto")),
        "cover_rotation_deg": core.number(options.get("cover_rotation_deg", 0.0),
                                          "Schachtdeckeldrehung"),
        "structure_type": "stub" if options.get("as_stub") else
                          ("round" if core.number(options.get("shaft_diameter_m", 0.0),
                                                  "Schachtdurchmesser") > 0.0 else "junction"),
        "special_outline_m": [], "drops": [],
        "stub": ({"alignment": alignment, "main_dn_mm": original["dn_mm"],
                  "branch_dn_mm": core._dn(options.get("dn_mm")),
                  "connection_invert_m": connection_invert,
                  **dict(station_reference, station_enabled=bool(
                      options.get("stub_stationing", True)))}
                 if options.get("as_stub") else None),
        # A normal manhole/junction placed on an existing holding is also a
        # holding connection. Its station therefore remains available even
        # though it is not represented by the specialised stub structure.
        "connection_station": (None if options.get("as_stub") else
                               copy.deepcopy(station_reference)),
        "visible": True, "color_override": copy.deepcopy(options.get("color_override")),
    })
    existing_shafts = tuple(value for _existing_handle, value in shaft_records()) + (shaft,)
    built = core.build_network(paths, options, existing_shafts, numbers)
    terminal = options.get("terminal")
    if terminal:
        terminal_xy = paths[0][-1]
        endpoint = min(
            built["shafts"],
            key=lambda value: math.dist((value["x_m"], value["y_m"]), terminal_xy))
        if math.dist((endpoint["x_m"], endpoint["y_m"]), terminal_xy) > 0.001:
            raise core.SewerError("Der freie Anschluss-Endpunkt konnte nicht zugeordnet werden.")
        endpoint.update(
            structure_type=terminal["structure_type"], visible=True,
            name=_next_named_number("ABL" if terminal["structure_type"] == "floor_drain" else "HA"),
            note="", diameter_m=0.0, special_outline_m=[], drops=[], stub=None,
            kd_m=terminal["terminal_top_m"], ks_m=terminal["terminal_invert_m"],
            terminal_length_m=terminal.get("terminal_length_m", 0.50),
            terminal_width_m=terminal.get("terminal_width_m", 0.30),
            terminal_height_m=terminal.get("terminal_height_m", 0.60),
            terminal_depth_m=terminal.get("terminal_height_m", 0.60),
            terminal_symbol=terminal.get("terminal_symbol", ""),
            terminal_symbol_has_3d=terminal.get("terminal_symbol_has_3d", False),
            terminal_label_visible=terminal.get("terminal_label_visible", True),
            terminal_label_point_size=terminal.get(
                "terminal_label_point_size", preferences["point_size"]))
        core.validate_shaft(endpoint, allow_hidden=True)
    elif options.get("as_stub"):
        # The free end remains a visible zero-diameter node so its separate,
        # line-parallel connection-height annotation can be moved. It is not a
        # shaft, however, and therefore must not receive the framed KS box.
        for terminal_xy in (value[-1] for value in paths):
            candidates = tuple(
                value for value in built["shafts"]
                if value.get("structure_type") == "round" and
                float(value.get("diameter_m", 0.0)) == 0.0)
            if not candidates:
                continue
            endpoint = min(
                candidates,
                key=lambda value: math.dist(
                    (value["x_m"], value["y_m"]), terminal_xy))
            if math.dist((endpoint["x_m"], endpoint["y_m"]), terminal_xy) <= 0.001:
                endpoint["primary_label_visible"] = False
    connected_values = []
    for pipe in built["pipes"]:
        if pipe["start_id"] == shaft_id:
            connected_values.append(pipe["start_invert_m"])
        if pipe["end_id"] == shaft_id:
            connected_values.append(pipe["end_invert_m"])
    if not connected_values or any(abs(value - connection_invert) > 0.001 for value in connected_values):
        raise core.SewerError(
            "Die neue Leitung muss am Bestand mit KS = %.2f m anschließen. Berechnungsrichtung prüfen." %
            connection_invert)
    new_shafts = (shaft,) + tuple(built["shafts"])
    new_pipes = (first, second) + tuple(built["pipes"])
    prospective_pipes = [value for existing_handle, value in pipe_records()
                         if existing_handle != handle] + list(new_pipes)
    prospective_shafts = [stub_updates.get(existing_handle, value)
                          for existing_handle, value in shaft_records()] + list(new_shafts)
    core.validate_network(prospective_pipes, prospective_shafts)
    preferences = sewer_settings.validate(preferences)
    ensure_classes(preferences)
    vs.NameUndoEvent("PD Leitung an Kanalstrecke anschließen")
    created = []
    owner_snapshot = copy.deepcopy(data)
    original_endpoint_handles = {
        original["start_id"]: start_handle,
        original["end_id"]: end_handle}
    owner_mutated = False
    snapshots = {existing_handle: copy.deepcopy(_live().data_of(existing_handle))
                 for existing_handle in stub_updates}
    try:
        shaft_handles = {value["id"]: existing_handle
                         for existing_handle, value in shaft_records()}
        for value in new_shafts:
            new_handle = _new_object((value["x_m"], value["y_m"]), _node_role(value),
                                     value, preferences, created)
            shaft_handles[value["id"]] = new_handle
        pipe_handles = [handle]
        for value in new_pipes[1:]:
            new_handle = _new_object((0.0, 0.0), "sewer_pipe", value, preferences, created)
            pipe_handles.append(new_handle)
            _sync_pipe_associations(new_handle, value, shaft_handles)
        owner_mutated = True
        _detach_pipe_endpoint_associations(handle, owner_snapshot)
        _live().write_data(handle, dict(
            owner_snapshot, pipe=first,
            preferences=copy.deepcopy(preferences)))
        _sync_pipe_associations(handle, first, shaft_handles)
        owners = [shaft_handles[value["id"]] for value in new_shafts if value["visible"]]
        # Every segment owns a label PIO. The label itself decides dynamically
        # whether this segment is the one representative of its complete
        # holding between real shafts. This remains correct after later splits.
        owners += pipe_handles
        for owner in owners:
            ensure_label(owner, _live().data_of(owner), created)
        touched_shafts = _ensure_endpoint_labels(
            new_pipes, created, snapshots)
        for existing_handle, value in stub_updates.items():
            _live().write_data(existing_handle, dict(
                snapshots[existing_handle], shaft=value,
                preferences=copy.deepcopy(preferences)))
        for created_handle in created:
            _reset_checked(created_handle)
        _reset_checked(handle)
        for existing_handle in stub_updates:
            _reset_checked(existing_handle)
        for existing_handle in touched_shafts:
            if existing_handle not in stub_updates:
                _reset_checked(existing_handle)
    except Exception:
        if owner_mutated:
            _live().write_data(handle, owner_snapshot)
            _sync_pipe_associations(
                handle, original, original_endpoint_handles)
            vs.ResetObject(handle)
        for existing_handle, snapshot in snapshots.items():
            _live().write_data(existing_handle, snapshot)
            vs.ResetObject(existing_handle)
        for created_handle in reversed(created):
            if created_handle:
                vs.DelObject(created_handle)
        raise
    for identity in (original["start_id"], original["end_id"]):
        existing_handle = _handle_by_id(core.SHAFT_PREFIX, identity)
        if existing_handle:
            vs.ResetObject(existing_handle)
    vs.DSelectAll()
    for pipe_handle in pipe_handles[2:]:
        vs.SetSelect(pipe_handle)
    vs.ReDrawAll()
    return tuple(pipe_handles[2:]), connection_invert


def connect_stub(handle, point_m, branch_paths, options, preferences):
    """Create a DIN plan fitting and a vertically aligned branch."""
    value = dict(options)
    value["as_stub"] = True
    value.setdefault("connection_alignment", "invert")
    value["shaft_diameter_m"] = 0.0
    return connect_branch(handle, point_m, branch_paths, value, preferences)


def pipe_at_point(point_m, tolerance_m=0.30):
    """Resolve one interior holding at a graphical endpoint."""
    candidates = []
    for handle, pipe in pipe_records():
        (_first_handle, first), (_second_handle, second) = _endpoints(pipe)
        try:
            _fraction, projected = core.project_on_pipe(
                (first["x_m"], first["y_m"]), (second["x_m"], second["y_m"]),
                point_m, tolerance_m)
        except core.SewerError:
            continue
        candidates.append((math.dist(tuple(point_m), projected), handle, pipe, projected))
    if not candidates:
        raise core.SewerError(
            "Der letzte Punkt liegt auf keiner bestehenden Kanalhaltung. Bitte auf der Hauptleitung doppelklicken.")
    candidates.sort(key=lambda row: row[0])
    if len(candidates) > 1 and abs(candidates[0][0] - candidates[1][0]) <= 1e-6:
        raise core.SewerError("Am Endpunkt liegen mehrere Haltungen. Bitte eindeutiger anklicken.")
    return candidates[0][1], candidates[0][2], candidates[0][3]


def nearest_cover_height(point_m):
    rows = [(math.dist(tuple(point_m), (shaft["x_m"], shaft["y_m"])), shaft["kd_m"])
            for _handle, shaft in shaft_records()
            if shaft["visible"] and shaft["structure_type"] in ("round", "special")]
    if not rows:
        raise core.SewerError(
            "Keine Schachtdeckelhöhe für die automatische Bodenablaufhöhe vorhanden.")
    return min(rows, key=lambda row: row[0])[1]


def connect_terminal(points, terminal, preferences):
    """Draw from a free terminal and connect only the last point to a pipe."""
    values = core.path(points)
    handle, main_pipe, projected = pipe_at_point(values[-1])
    # The main line is authoritative. This permits the same floor-drain and
    # house-connection workflow on RW, SW and MW without an avoidable dialog
    # mismatch after the user has already selected the physical host pipe.
    terminal = dict(terminal, kind=main_pipe["kind"])
    bottom = terminal.get("terminal_bottom_m")
    legacy_top = terminal.get("terminal_top_m")
    if terminal["structure_type"] == "floor_drain":
        height = core.number(
            terminal.get("terminal_height_m", terminal.get("terminal_depth_m", 0.60)),
            "Höhe des Bodenablaufs")
        if bottom is None and legacy_top is not None:
            top = core.number(legacy_top, "Oberkante des Bodenablaufs")
            terminal_invert = top - height
        elif bottom is None:
            top = nearest_cover_height(values[0])
            terminal_invert = top - height
        else:
            terminal_invert = core.number(bottom, "Unterkante des Bodenablaufs")
            top = terminal_invert + height
    else:
        terminal_invert = core.number(
            bottom if bottom is not None else legacy_top,
            "Höhe des Hausanschlusses")
        top = terminal_invert
    (_first_handle, first), (_second_handle, second) = _endpoints(main_pipe)
    fraction, _xy = core.project_on_pipe(
        (first["x_m"], first["y_m"]), (second["x_m"], second["y_m"]), projected)
    main_invert = main_pipe["start_invert_m"] + (
        main_pipe["end_invert_m"] - main_pipe["start_invert_m"]) * fraction
    target_invert = core.connection_invert(
        main_invert, main_pipe["dn_mm"], terminal["dn_mm"], terminal["alignment"])
    if terminal_invert + 1e-9 < target_invert:
        raise core.SewerError(
            "Der freie Anschluss liegt unter der Hauptleitung; ein gleichmäßiges Gefälle zum Kanal ist nicht möglich.")
    branch = (projected,) + tuple(reversed(values[:-1]))
    options = {
        "kind": main_pipe["kind"], "dn_mm": terminal["dn_mm"],
        "material": terminal["material"], "start_invert_m": terminal_invert,
        "terminal_invert_m": terminal_invert,
        "calculation_mode": "end", "calculation_value": target_invert,
        "cover_height_m": top, "shaft_diameter_m": 0.0, "shaft_mode": "endpoints",
        "cover_diameter_m": preferences["shaft_cover_diameter_m"],
        "cover_symbol": "", "cover_placement": "center", "cover_rotation_deg": 0.0,
        "join_style": preferences["join_style"],
        "fillet_radius_m": preferences["fillet_radius_m"],
        "flow_arrow_scale": preferences["flow_arrow_scale"],
        "label_layout": preferences["label_layout"], "label_width_m": 0.0,
        "label_rotation_deg": preferences["label_rotation_deg"],
        "draw_3d": preferences["draw_3d"],
        "graphics_mode": preferences["graphics_mode"],
        "line_type": preferences["single_line_type"],
        "connection_alignment": terminal["alignment"], "as_stub": True,
        "terminal": dict(terminal, terminal_top_m=top,
                         terminal_invert_m=terminal_invert),
    }
    return connect_branch(handle, projected, (branch,), options, preferences)


def replace_with_special(handle, source_polygon, preferences):
    """Replace one round plan body with a selected polygon transactionally."""
    data = _live().data_of(handle)
    shaft = read_shaft(handle, data)
    if shaft["structure_type"] not in ("round", "special"):
        raise core.SewerError("Nur ein runder Schacht oder Sonderschacht kann umgewandelt werden.")
    if adapter.object_type(source_polygon) not in (
            adapter.TYPE_POLYGON, adapter.TYPE_POLYLINE):
        raise core.SewerError(
            "Die gewählte Sonderschachtkontur ist nicht mehr vorhanden. "
            "Bitte ein geschlossenes Polygon oder eine geschlossene Polylinie erneut wählen.")
    try:
        closed = bool(vs.IsPolyClosed(source_polygon))
    except Exception as error:
        raise core.SewerError(
            "Die gewählte Sonderschachtkontur konnte nicht gelesen werden.") from error
    if not closed:
        raise core.SewerError("Die Kontur des Sonderschachts muss geschlossen sein.")
    source = adapter.extract_path(source_polygon)["points"]
    outline = core.special_outline(
        tuple((x - shaft["x_m"], y - shaft["y_m"]) for x, y in source))
    updated = core.validate_shaft(dict(
        shaft, structure_type="special", special_outline_m=list(outline)), allow_hidden=True)
    _commit_network_updates(
        {}, {handle: updated}, preferences, "PD Sonderschacht herstellen")
    # The network transaction already resets the shaft and every connected
    # pipe exactly once. A second reset here used to re-enter those PIOs while
    # the tracked source object was still current and made a repeated command
    # unstable. Consume the top-level construction contour only after the
    # complete network redraw; failure to remove this helper must not roll
    # back a successfully converted shaft.
    try:
        vs.SetDSelect(source_polygon)
        vs.DelObject(source_polygon)
    except Exception:
        pass
    vs.ReDrawAll()
    return updated


def set_drop(handle, value, preferences):
    data = _live().data_of(handle)
    shaft = read_shaft(handle, data)
    connected = {pipe["id"]: (pipe_handle, pipe)
                 for pipe_handle, pipe in _connected_pipes(shaft["id"])}
    selected = connected.get(value["pipe_id"])
    if selected is None:
        raise core.SewerError("Die gewählte Absturzhaltung ist nicht mehr mit dem Schacht verbunden.")
    pipe_handle, pipe = selected
    if pipe["end_id"] != shaft["id"]:
        raise core.SewerError("Ein Absturz kann nur an einer ankommenden Haltung angelegt werden.")
    upper = core.number(value.get("upper_invert_m"), "Obere Absturzhöhe")
    lower = core.number(value.get("lower_invert_m"), "Untere Absturzhöhe")
    if upper <= lower + 1e-6:
        raise core.SewerError(
            "Die obere Absturzhöhe muss eindeutig über der unteren Absturzhöhe liegen.")
    changed_pipe = dict(pipe, end_invert_m=upper)
    if core.pipe_flow_reversal_required(changed_pipe):
        raise core.SewerError(
            "Die obere Absturzhöhe liegt über der Sohle am vorherigen Schacht. "
            "Damit wäre die gewählte Haltung keine ankommende Leitung mehr.")
    changed_pipe = core.validate_pipe(changed_pipe)
    drops = [row for row in shaft.get("drops", ()) if row["pipe_id"] != value["pipe_id"]]
    drops.append({"pipe_id": value["pipe_id"], "upper_invert_m": upper,
                  "lower_invert_m": lower})
    updated = core.validate_shaft(dict(shaft, drops=drops), allow_hidden=True)
    _commit_network_updates(
        {pipe_handle: changed_pipe}, {handle: updated}, preferences,
        "PD Absturz vor Schacht")
    return updated


def connect_from_shaft(handle, branch_paths, options, preferences):
    """Add a new branch directly to one stable existing shaft object."""
    data = _live().data_of(handle)
    shaft = read_shaft(handle, data)
    paths = tuple(core.path(value) for value in branch_paths)
    start_xy = shaft["x_m"], shaft["y_m"]
    if not paths or math.dist(paths[0][0], start_xy) > 0.001:
        raise core.SewerError("Die neue Leitung beginnt nicht am gewählten Schacht.")
    connection_invert = shaft["ks_m"]
    anchored = dict(options)
    anchored.update(kind=shaft["kind"], start_invert_m=connection_invert,
                    calculation_mode="start", reverse_flow=True)
    numbers = _next_numbers()
    existing_shafts = tuple(value for _existing_handle, value in shaft_records())
    built = core.build_network(paths, anchored, existing_shafts, numbers)
    connected_values = []
    for pipe in built["pipes"]:
        if pipe["start_id"] == shaft["id"]:
            connected_values.append(pipe["start_invert_m"])
        if pipe["end_id"] == shaft["id"]:
            connected_values.append(pipe["end_invert_m"])
    if not connected_values or any(
            abs(value - connection_invert) > 0.001 for value in connected_values):
        raise core.SewerError(
            "Die neue Leitung konnte nicht höhengleich mit dem gewählten Schacht verbunden werden.")
    prospective_pipes = [value for _pipe_handle, value in pipe_records()] + list(built["pipes"])
    prospective_shafts = list(existing_shafts) + list(built["shafts"])
    core.validate_network(prospective_pipes, prospective_shafts)
    preferences = sewer_settings.validate(preferences)
    ensure_classes(preferences)
    vs.NameUndoEvent("PD Leitung an Kanalschacht anschließen")
    created = []
    endpoint_snapshots = {}
    try:
        shaft_handles = {value["id"]: existing_handle
                         for existing_handle, value in shaft_records()}
        for value in built["shafts"]:
            new_handle = _new_object((value["x_m"], value["y_m"]), _node_role(value),
                                     value, preferences, created)
            shaft_handles[value["id"]] = new_handle
        pipe_handles = []
        for value in built["pipes"]:
            new_handle = _new_object((0.0, 0.0), "sewer_pipe", value, preferences, created)
            pipe_handles.append(new_handle)
            _sync_pipe_associations(new_handle, value, shaft_handles)
        owners = [shaft_handles[value["id"]] for value in built["shafts"] if value["visible"]]
        owners.extend(pipe_handles)
        for owner in owners:
            ensure_label(owner, _live().data_of(owner), created)
        touched_shafts = _ensure_endpoint_labels(
            built["pipes"], created, endpoint_snapshots)
        for created_handle in created:
            _reset_checked(created_handle)
        for shaft_handle in touched_shafts:
            if shaft_handle not in created:
                _reset_checked(shaft_handle)
    except Exception:
        for created_handle in reversed(created):
            if created_handle:
                vs.DelObject(created_handle)
        for shaft_handle, snapshot in endpoint_snapshots.items():
            _live().write_data(shaft_handle, snapshot)
            vs.ResetObject(shaft_handle)
        raise
    vs.DSelectAll()
    for pipe_handle in pipe_handles:
        vs.SetSelect(pipe_handle)
    vs.ReDrawAll()
    return tuple(pipe_handles), connection_invert


def connect_from_rigole(handle, branch_paths, options, preferences):
    """Connect a new canal at a graphically chosen point of a rigole side."""
    rigole_data = _live().data_of(handle)
    rigole = read_rigole(handle, rigole_data)
    paths = tuple(core.path(value) for value in branch_paths)
    if not paths:
        raise core.SewerError("Keine Anschlussleitung zur Rigole gezeichnet.")
    attachment = core.project_on_rigole(rigole, paths[0][0])
    first_path = ((attachment["x_m"], attachment["y_m"]),) + tuple(paths[0][1:])
    paths = (core.path(first_path),) + paths[1:]
    connection_invert = core.number(
        options.get("rigole_connection_invert_m"), "Anschlusshöhe an der Rigole")
    if not rigole["bottom_m"] - 1e-9 <= connection_invert <= rigole["top_m"] + 1e-9:
        raise core.SewerError(
            "Die Anschlusshöhe muss zwischen UK und OK der Rigole liegen.")
    raw_slope = (options.get("calculation_value", 1.5)
                 if options.get("calculation_mode") in ("slope", "start") else 1.5)
    slope = max(0.0, core.number(raw_slope, "Gefälle der Rigolen-Anschlussleitung"))
    anchored = dict(options)
    anchored.update(
        start_invert_m=connection_invert,
        calculation_mode="start" if anchored.get("reverse_flow", True) else "slope",
        calculation_value=slope,
        shaft_mode=anchored.get("shaft_mode", "all"))
    node_id = str(uuid.uuid4())
    junction = core.validate_shaft({
        "schema": core.SCHEMA, "id": node_id, "kind": anchored.get("kind"),
        "name": "", "note": "", "x_m": attachment["x_m"],
        "y_m": attachment["y_m"], "kd_m": rigole["terrain_top_m"],
        "ks_m": connection_invert, "diameter_m": 0.0,
        "construction_material": "PP", "wall_thickness_m": 0.0,
        "cover_diameter_m": 0.625, "cover_symbol": "",
        "cover_placement": "center", "cover_rotation_deg": 0.0,
        "structure_type": "junction", "special_outline_m": [],
        "drops": [], "visible": False, "color_override": None,
        "rigole_id": rigole["id"],
    }, allow_hidden=True)
    existing_rows = tuple(shaft_records())
    existing_shafts = tuple(value for _existing_handle, value in existing_rows) + (junction,)
    built = core.build_network(paths, anchored, existing_shafts, _next_numbers())
    connected_values = []
    for pipe in built["pipes"]:
        if pipe["start_id"] == node_id:
            connected_values.append(pipe["start_invert_m"])
        if pipe["end_id"] == node_id:
            connected_values.append(pipe["end_invert_m"])
    if not connected_values or any(
            abs(value - connection_invert) > 0.001 for value in connected_values):
        raise core.SewerError(
            "Die Anschlussleitung konnte nicht mit der gewählten Rigolen-Anschlusshöhe aufgebaut werden.")
    prospective_pipes = [value for _pipe_handle, value in pipe_records()] + list(built["pipes"])
    prospective_shafts = list(existing_shafts) + list(built["shafts"])
    core.validate_network(prospective_pipes, prospective_shafts)
    preferences = sewer_settings.validate(preferences)
    ensure_classes(preferences)
    created = []
    snapshot = copy.deepcopy(rigole_data)
    endpoint_snapshots = {}
    vs.NameUndoEvent("PD Kanal an Rigole anschließen")
    try:
        shaft_handles = {value["id"]: existing_handle
                         for existing_handle, value in existing_rows}
        junction_handle = _new_object(
            (junction["x_m"], junction["y_m"]), _node_role(junction),
            junction, preferences, created)
        shaft_handles[node_id] = junction_handle
        for value in built["shafts"]:
            new_handle = _new_object((value["x_m"], value["y_m"]), _node_role(value),
                                     value, preferences, created)
            shaft_handles[value["id"]] = new_handle
        pipe_handles = []
        for value in built["pipes"]:
            new_handle = _new_object((0.0, 0.0), "sewer_pipe", value, preferences, created)
            pipe_handles.append(new_handle)
            _sync_pipe_associations(new_handle, value, shaft_handles)
        _sync_rigole_junction_association(handle, junction_handle)
        connections = list(rigole.get("connections", ()))
        connections.append({
            "node_id": node_id, "side": attachment["side"],
            "fraction": attachment["fraction"], "invert_m": connection_invert})
        updated_rigole = core.validate_rigole(dict(rigole, connections=connections))
        _live().write_data(handle, dict(
            rigole_data, rigole=updated_rigole,
            preferences=copy.deepcopy(preferences)))
        owners = [shaft_handles[value["id"]] for value in built["shafts"]
                  if value["visible"]]
        owners.extend(pipe_handles)
        for owner in owners:
            ensure_label(owner, _live().data_of(owner), created)
        touched_shafts = _ensure_endpoint_labels(
            built["pipes"], created, endpoint_snapshots)
        for created_handle in created:
            _reset_checked(created_handle)
        for shaft_handle in touched_shafts:
            if shaft_handle not in created:
                _reset_checked(shaft_handle)
        _reset_checked(handle)
    except Exception:
        _live().write_data(handle, snapshot)
        vs.ResetObject(handle)
        for created_handle in reversed(created):
            if created_handle:
                vs.DelObject(created_handle)
        for shaft_handle, shaft_snapshot in endpoint_snapshots.items():
            _live().write_data(shaft_handle, shaft_snapshot)
            vs.ResetObject(shaft_handle)
        raise
    vs.DSelectAll()
    for pipe_handle in pipe_handles:
        vs.SetSelect(pipe_handle)
    vs.ReDrawAll()
    return tuple(pipe_handles), connection_invert


def merge_selected(handles, preferences):
    """Merge two selected collinear pipes and remove their degree-two shaft."""
    if len(handles) != 2:
        raise core.SewerError("Zum Vereinigen genau zwei Kanalstrecken markieren.")
    rows = []
    for handle, data in handles:
        if data.get("role") != "sewer_pipe":
            raise core.SewerError("Zum Vereinigen genau zwei Kanalstrecken markieren.")
        rows.append((handle, data, read_pipe(handle, data)))
    shared_ids = (set((rows[0][2]["start_id"], rows[0][2]["end_id"])) &
                  set((rows[1][2]["start_id"], rows[1][2]["end_id"])))
    if len(shared_ids) != 1:
        raise core.SewerError("Die Kanalstrecken besitzen keinen eindeutigen gemeinsamen Knoten.")
    shared_id = next(iter(shared_ids))
    if len(_connected_pipes(shared_id)) != 2:
        raise core.SewerError("Ein Abzweigsschacht kann nicht durch Vereinigen entfernt werden.")
    outer_ids = [identity for _handle, _data, pipe_value in rows
                 for identity in (pipe_value["start_id"], pipe_value["end_id"])
                 if identity != shared_id]
    if len(outer_ids) != 2 or outer_ids[0] == outer_ids[1]:
        raise core.SewerError("Die gewählten Kanalstrecken bilden keine offene Folge.")
    shared = read_shaft(_handle_by_id(core.SHAFT_PREFIX, shared_id))
    outer = [read_shaft(_handle_by_id(core.SHAFT_PREFIX, identity)) for identity in outer_ids]
    via_length = sum(math.dist((shared["x_m"], shared["y_m"]),
                               (value["x_m"], value["y_m"])) for value in outer)
    direct_length = math.dist((outer[0]["x_m"], outer[0]["y_m"]),
                              (outer[1]["x_m"], outer[1]["y_m"]))
    if abs(via_length - direct_length) > 0.001:
        raise core.SewerError("Nur geradlinig aufeinanderfolgende Kanalstrecken können vereinigt werden.")
    merged = core.merge_pipes(rows[0][2], rows[1][2], shared_id)
    removed_handles = {rows[0][0], rows[1][0]}
    prospective_pipes = [value for existing_handle, value in pipe_records()
                         if existing_handle not in removed_handles] + [merged]
    prospective_shafts = [value for existing_handle, value in shaft_records()
                          if existing_handle != _handle_by_id(core.SHAFT_PREFIX, shared_id)]
    core.validate_network(prospective_pipes, prospective_shafts)
    vs.NameUndoEvent("PD Kanalstrecken vereinigen")
    created = []
    try:
        new_handle = _new_object((0.0, 0.0), "sewer_pipe", merged, preferences, created)
        _associate_pipe(new_handle, merged)
        ensure_label(new_handle, _live().data_of(new_handle), created)
        for created_handle in created:
            _reset_checked(created_handle)
    except Exception:
        for created_handle in reversed(created):
            if created_handle:
                vs.DelObject(created_handle)
        raise
    for old_handle, old_data, _pipe in rows:
        _delete_with_labels(old_handle, old_data)
    shared_handle = _handle_by_id(core.SHAFT_PREFIX, shared_id)
    _delete_with_labels(shared_handle, _live().data_of(shared_handle))
    vs.DSelectAll()
    vs.SetSelect(new_handle)
    vs.ReDrawAll()
    return new_handle


def delete_selected(handles):
    """Delete selected pipes; selected shafts also delete their connected pipes."""
    pipe_rows = {}
    shaft_rows = {}
    fitting_rows = {}
    terminal_rows = {}
    rigole_rows = {}
    for handle, data in handles:
        if data.get("role") == "sewer_pipe":
            pipe_rows[handle] = (data, read_pipe(handle, data))
        elif data.get("role") in NODE_ROLES:
            shaft = read_shaft(handle, data)
            if data.get("role") == "sewer_fitting":
                fitting_rows[handle] = (data, shaft)
            elif data.get("role") in (
                    "sewer_floor_drain", "sewer_house_connection"):
                terminal_rows[handle] = (data, shaft)
            else:
                shaft_rows[handle] = (data, shaft)
            for pipe_handle, pipe in _connected_pipes(shaft["id"]):
                pipe_rows[pipe_handle] = (_live().data_of(pipe_handle), pipe)
        elif data.get("role") == "sewer_rigole":
            rigole = read_rigole(handle, data)
            rigole_rows[handle] = (data, rigole)
            for connection in rigole.get("connections", ()):
                node_handle = _handle_by_id(core.SHAFT_PREFIX, connection["node_id"])
                if not node_handle:
                    continue
                node_data = _live().data_of(node_handle)
                node = read_shaft(node_handle, node_data)
                shaft_rows[node_handle] = (node_data, node)
                for pipe_handle, pipe in _connected_pipes(node["id"]):
                    pipe_rows[pipe_handle] = (_live().data_of(pipe_handle), pipe)
    if (not pipe_rows and not shaft_rows and not fitting_rows and
            not terminal_rows and not rigole_rows):
        raise core.SewerError("Keine löschbaren Kanalobjekte markiert.")
    remaining_pipes = [pipe for handle, pipe in pipe_records() if handle not in pipe_rows]
    removed_nodes = set(shaft_rows).union(fitting_rows).union(terminal_rows)
    remaining_shafts = [shaft for handle, shaft in shaft_records()
                        if handle not in removed_nodes]
    core.validate_network(remaining_pipes, remaining_shafts)
    affected_shaft_ids = {identity for _handle, (_data, pipe) in pipe_rows.items()
                          for identity in (pipe["start_id"], pipe["end_id"])}
    removed_shaft_ids = {
        shaft["id"] for rows in (shaft_rows, fitting_rows, terminal_rows)
        for _handle, (_data, shaft) in rows.items()}
    vs.NameUndoEvent("PD Kanalobjekte löschen")
    for handle, (data, _pipe) in pipe_rows.items():
        _delete_with_labels(handle, data)
    for handle, (data, _shaft) in shaft_rows.items():
        _delete_with_labels(handle, data)
    for handle, (data, _fitting) in fitting_rows.items():
        _delete_with_labels(handle, data)
    for handle, (data, _terminal) in terminal_rows.items():
        _delete_with_labels(handle, data)
    for handle, (data, _rigole) in rigole_rows.items():
        _delete_with_labels(handle, data)
    for identity in affected_shaft_ids - removed_shaft_ids:
        shaft_handle = _handle_by_id(core.SHAFT_PREFIX, identity)
        if shaft_handle:
            vs.ResetObject(shaft_handle)
    vs.ReDrawAll()
    return (len(pipe_rows), len(shaft_rows), len(fitting_rows),
            len(terminal_rows), len(rigole_rows))


def _set_graphics(handle, class_value, color, fill=True, opacity=100):
    vs.SetClass(handle, class_value)
    vs.SetPenFore(handle, color)
    vs.SetPenBack(handle, color)
    vs.SetFillFore(handle, color)
    vs.SetFillBack(handle, color)
    vs.SetFPat(handle, 1 if fill else 0)
    vs.SetOpacityN(handle, 100, int(opacity))


def _set_shaft_graphics(handle, class_value, pen_color, fill_color,
                        transparency_percent, fill=True):
    """Apply shaft graphics without making its contour transparent."""
    pen = _rgb(pen_color)
    fill_color = _rgb(fill_color)
    fill_opacity = int(round(
        100.0 - max(0.0, min(100.0, float(transparency_percent)))))
    vs.SetClass(handle, class_value)
    vs.SetPenFore(handle, pen)
    vs.SetPenBack(handle, pen)
    vs.SetFillFore(handle, fill_color)
    vs.SetFillBack(handle, fill_color)
    vs.SetFPat(handle, 1 if fill else 0)
    vs.SetOpacityN(handle, 100, fill_opacity if fill else 100)


def _set_rigole_graphics(handle, class_value, pen_color, fill_color,
                         transparency_percent):
    """Apply independent rigole outline/fill while keeping outlines at 100 %."""
    pen = _rgb(pen_color)
    fill = _rgb(fill_color)
    opacity = int(round(100.0 - max(0.0, min(100.0, transparency_percent))))
    vs.SetClass(handle, class_value)
    vs.SetPenFore(handle, pen)
    vs.SetPenBack(handle, pen)
    vs.SetFillFore(handle, fill)
    vs.SetFillBack(handle, fill)
    vs.SetFPat(handle, 1)
    vs.SetOpacityN(handle, 100, opacity)


def _draw_open_polyline(points, class_value, color, line_type=None):
    values = tuple(points)
    if len(values) < 2:
        return None
    vs.BeginPoly()
    for value in values:
        vs.AddPoint(value)
    vs.EndPoly()
    handle = vs.LNewObj()
    if not handle:
        raise core.SewerError("Rohrumgrenzung konnte nicht erzeugt werden.")
    _set_graphics(handle, class_value, color, fill=False, opacity=100)
    if line_type is not None:
        vs.SetLSN(handle, int(line_type))
    return handle


def _draw_band(first, second, width, class_value, color,
               start_width=None, end_width=None, cap_start=False, cap_end=False):
    dx, dy = second[0] - first[0], second[1] - first[1]
    length = math.hypot(dx, dy)
    if length <= 1e-9:
        raise core.SewerError("Kanalstrecke besitzt keine zeichnbare Länge.")
    ux, uy = dx / length, dy / length
    nx, ny = -uy, ux
    half_width = width * 0.5
    start_half = (width if start_width is None else start_width) * 0.5
    end_half = (width if end_width is None else end_width) * 0.5
    transition = min(max(width, 1e-9), length * 0.25)

    left = [(first[0] + nx * start_half, first[1] + ny * start_half)]
    right = [(first[0] - nx * start_half, first[1] - ny * start_half)]
    if abs(start_half - half_width) > 1e-9:
        left.append((first[0] + ux * transition + nx * half_width,
                     first[1] + uy * transition + ny * half_width))
        right.append((first[0] + ux * transition - nx * half_width,
                      first[1] + uy * transition - ny * half_width))
    if abs(end_half - half_width) > 1e-9:
        left.append((second[0] - ux * transition + nx * half_width,
                     second[1] - uy * transition + ny * half_width))
        right.append((second[0] - ux * transition - nx * half_width,
                      second[1] - uy * transition - ny * half_width))
    left.append((second[0] + nx * end_half, second[1] + ny * end_half))
    right.append((second[0] - nx * end_half, second[1] - ny * end_half))
    values = tuple(left + list(reversed(right)))
    vs.BeginPoly()
    for value in values:
        vs.AddPoint(value)
    vs.EndPoly()
    handle = vs.LNewObj()
    if not handle:
        raise core.SewerError("2D-Rohrdarstellung konnte nicht erzeugt werden.")
    vs.SetPolyClosed(handle, True)
    _set_graphics(handle, class_value, color, fill=True, opacity=50)
    # Draw the contractual 100 % outlines independently.  Omitting the end
    # edges prevents seams where a pipe continues through a rounded junction.
    vs.SetLSN(handle, 0)
    _draw_open_polyline(left, class_value, color)
    _draw_open_polyline(right, class_value, color)
    if cap_start:
        _draw_open_polyline((left[0], right[0]), class_value, color)
    if cap_end:
        _draw_open_polyline((left[-1], right[-1]), class_value, color)
    return handle


def _draw_flow_arrow(first, second, scale, factor, class_value):
    """Draw a solid plan arrow from the higher invert toward the lower invert."""
    dx, dy = second[0] - first[0], second[1] - first[1]
    distance = math.hypot(dx, dy)
    if distance <= 1e-9:
        raise core.SewerError("Fließrichtungspfeil besitzt keine zeichnbare Länge.")
    ux, uy = dx / distance, dy / distance
    nx, ny = -uy, ux
    arrow_length = min(0.80 * scale / factor, distance * 0.60)
    head_width = min(0.30 * scale / factor, arrow_length * 0.45)
    shaft_width = head_width * 0.28
    cx, cy = (first[0] + second[0]) * 0.5, (first[1] + second[1]) * 0.5
    tail = cx - ux * arrow_length * 0.5, cy - uy * arrow_length * 0.5
    head_base = cx + ux * arrow_length * 0.08, cy + uy * arrow_length * 0.08
    tip = cx + ux * arrow_length * 0.5, cy + uy * arrow_length * 0.5
    points = (
        (tail[0] + nx * shaft_width, tail[1] + ny * shaft_width),
        (head_base[0] + nx * shaft_width, head_base[1] + ny * shaft_width),
        (head_base[0] + nx * head_width, head_base[1] + ny * head_width),
        tip,
        (head_base[0] - nx * head_width, head_base[1] - ny * head_width),
        (head_base[0] - nx * shaft_width, head_base[1] - ny * shaft_width),
        (tail[0] - nx * shaft_width, tail[1] - ny * shaft_width),
    )
    vs.BeginPoly()
    for value in points:
        vs.AddPoint(value)
    vs.EndPoly()
    handle = vs.LNewObj()
    if not handle:
        raise core.SewerError("Fließrichtungspfeil konnte nicht erzeugt werden.")
    vs.SetPolyClosed(handle, True)
    _set_graphics(handle, class_value, TEXT_COLOR, fill=True, opacity=100)
    return handle


def _cross(first, second):
    return first[0] * second[1] - first[1] * second[0]


def _convex_hull(points):
    values = sorted(set((float(x), float(y)) for x, y in points))
    if len(values) <= 2:
        return values

    def turn(first, second, third):
        return _cross((second[0] - first[0], second[1] - first[1]),
                      (third[0] - second[0], third[1] - second[1]))
    lower = []
    for value in values:
        while len(lower) >= 2 and turn(lower[-2], lower[-1], value) <= 0:
            lower.pop()
        lower.append(value)
    upper = []
    for value in reversed(values):
        while len(upper) >= 2 and turn(upper[-2], upper[-1], value) <= 0:
            upper.pop()
        upper.append(value)
    return lower[:-1] + upper[:-1]


def _line_intersection(first, direction_first, second, direction_second):
    divisor = _cross(direction_first, direction_second)
    if abs(divisor) <= 1e-8:
        return None
    delta = second[0] - first[0], second[1] - first[1]
    station = _cross(delta, direction_second) / divisor
    return (first[0] + station * direction_first[0],
            first[1] + station * direction_first[1])


def _draw_join_polygon(points, class_value, color):
    values = _convex_hull(points)
    if len(values) < 3:
        return None
    vs.BeginPoly()
    for value in values:
        vs.AddPoint(value)
    vs.EndPoly()
    handle = vs.LNewObj()
    if not handle:
        raise core.SewerError("2D-Rohrverbindung konnte nicht erzeugt werden.")
    vs.SetPolyClosed(handle, True)
    _set_graphics(handle, class_value, color, fill=True, opacity=50)
    return handle


def _junction_rows(shaft):
    rows = []
    for pipe_handle, pipe in _connected_pipes(shaft["id"]):
        if pipe["kind"] != shaft["kind"]:
            continue
        other_id = pipe["end_id"] if pipe["start_id"] == shaft["id"] else pipe["start_id"]
        other_handle = _handle_by_id(core.SHAFT_PREFIX, other_id)
        if not other_handle:
            continue
        other = read_shaft(other_handle)
        dx, dy = other["x_m"] - shaft["x_m"], other["y_m"] - shaft["y_m"]
        length = math.hypot(dx, dy)
        if length <= 1e-9:
            continue
        rows.append({"handle": pipe_handle, "pipe": pipe,
                     "direction": (dx / length, dy / length), "length_m": length})
    return tuple(rows)


def _round_junction_geometry(shaft, factor, rows=None):
    rows = tuple(rows if rows is not None else _junction_rows(shaft))
    if len(rows) != 2 or any(row["pipe"]["join_style"] != "round" for row in rows):
        return None
    half_width = max(row["pipe"]["dn_mm"] for row in rows) / 2000.0 / factor
    radius = max(row["pipe"].get("fillet_radius_m", 0.20) for row in rows) / factor
    try:
        geometry = core.round_join_geometry(
            rows[0]["direction"], rows[1]["direction"], radius, half_width)
    except core.SewerError:
        return None
    if geometry is not None and geometry["trim"] * factor >= min(
            row["length_m"] for row in rows) * 0.49:
        return None
    return geometry


def _junction_is_straight(rows):
    if len(rows) != 2:
        return False
    first, second = rows[0]["direction"], rows[1]["direction"]
    return first[0] * second[0] + first[1] * second[1] <= -0.999999


def _draw_round_join(geometry, class_value, color):
    vs.BeginPoly()
    for value in geometry["fill"]:
        vs.AddPoint(value)
    vs.EndPoly()
    handle = vs.LNewObj()
    if not handle:
        raise core.SewerError("Ausgerundete 2D-Rohrverbindung konnte nicht erzeugt werden.")
    vs.SetPolyClosed(handle, True)
    _set_graphics(handle, class_value, color, fill=True, opacity=50)
    vs.SetLSN(handle, 0)
    _draw_open_polyline(geometry["outer"], class_value, color)
    _draw_open_polyline(geometry["inner"], class_value, color)
    return handle


def _draw_hidden_join(shaft, data):
    rows = _junction_rows(shaft)
    if len(rows) < 2:
        return
    preferences = data["preferences"]
    factor = adapter.units_to_meters()
    pipe_radius = max(row["pipe"]["dn_mm"] for row in rows) / 2000.0 / factor
    class_value = class_name(rows[0]["pipe"], preferences)
    ensure_pipe_classes(rows[0]["pipe"], preferences, color_for(data, preferences))
    color = color_for(data, preferences)
    styles = {row["pipe"]["join_style"] for row in rows}
    style = styles.pop() if len(styles) == 1 else "round"
    geometry = _round_junction_geometry(shaft, factor, rows)
    if style == "round" and geometry is not None:
        _draw_round_join(geometry, class_value, color)
        return
    if style == "round" and _junction_is_straight(rows):
        return
    if style == "round" or len(rows) != 2:
        radius = max(pipe_radius,
                     max(row["pipe"].get("fillet_radius_m", 0.20)
                         for row in rows) / factor)
        vs.Oval((-radius, radius), (radius, -radius))
        join = vs.LNewObj()
        if not join:
            raise core.SewerError("Runde 2D-Rohrverbindung konnte nicht erzeugt werden.")
        _set_graphics(join, class_value, color, fill=True, opacity=50)
        return
    radius = pipe_radius
    directions = []
    for row in rows:
        directions.append(row["direction"])
    endpoints = []
    normals = []
    for direction in directions:
        normal = -direction[1], direction[0]
        normals.append(normal)
        endpoints.extend(((normal[0] * radius, normal[1] * radius),
                          (-normal[0] * radius, -normal[1] * radius)))
    if style == "bevel":
        _draw_join_polygon(endpoints, class_value, color)
        return
    intersections = []
    for first_sign in (-1.0, 1.0):
        for second_sign in (-1.0, 1.0):
            first = normals[0][0] * radius * first_sign, normals[0][1] * radius * first_sign
            second = normals[1][0] * radius * second_sign, normals[1][1] * radius * second_sign
            value = _line_intersection(first, directions[0], second, directions[1])
            if value is not None and math.hypot(*value) <= radius * 4.0:
                intersections.append(value)
    _draw_join_polygon(intersections or endpoints, class_value, color)


def _center(value):
    # The official Vectorworks 2026 Python signature is ``(p, zValue)``;
    # generated API stubs flatten the same OUT parameters to ``(x, y, z)``.
    # Accept both representations because host builds expose both shapes.
    if (isinstance(value, (tuple, list)) and len(value) == 2 and
            isinstance(value[0], (tuple, list)) and len(value[0]) == 2):
        try:
            return float(value[0][0]), float(value[0][1]), float(value[1])
        except (TypeError, ValueError):
            pass
    if isinstance(value, (tuple, list)) and len(value) == 3:
        try:
            return tuple(float(component) for component in value)
        except (TypeError, ValueError):
            pass
    raise core.SewerError("3D-Mittelpunkt konnte nicht gelesen werden.")


def _connection_profile(shaft, pipe, width, factor):
    """Return center-line trim, end width and whether an end cap is needed."""
    if shaft.get("diameter_m", 0.0) <= 0.0 and shaft.get("structure_type") in (
            "round", "junction"):
        # A zero-diameter node is a closed pipe termination, never a hidden
        # junction that joins neighbouring pipe bands through the node.
        return 0.0, width, True
    if shaft.get("structure_type") == "special":
        other_id = pipe["end_id"] if pipe["start_id"] == shaft["id"] else pipe["start_id"]
        other_handle = _handle_by_id(core.SHAFT_PREFIX, other_id)
        if other_handle:
            other = read_shaft(other_handle)
            direction = other["x_m"] - shaft["x_m"], other["y_m"] - shaft["y_m"]
            distance = core.ray_polygon_distance(shaft["special_outline_m"], direction) / factor
            return max(0.0, distance), width, False
    if shaft.get("structure_type") == "floor_drain":
        other_id = pipe["end_id"] if pipe["start_id"] == shaft["id"] else pipe["start_id"]
        other_handle = _handle_by_id(core.SHAFT_PREFIX, other_id)
        if other_handle:
            other = read_shaft(other_handle)
            dx, dy = other["x_m"] - shaft["x_m"], other["y_m"] - shaft["y_m"]
            distance = math.hypot(dx, dy)
            if distance > 1e-9:
                ux, uy = dx / distance, dy / distance
                trim = (abs(ux) * shaft.get("terminal_length_m", 0.50) +
                        abs(uy) * shaft.get("terminal_width_m", 0.30)) * 0.5
                return trim / factor, width, False
        return max(shaft.get("terminal_length_m", 0.50),
                   shaft.get("terminal_width_m", 0.30)) * 0.5 / factor, width, False
    if shaft.get("structure_type") == "house":
        return 0.0, width, True
    if shaft.get("visible") and shaft["diameter_m"] > 0.0:
        radius = core.shaft_outer_diameter_m(shaft) / factor * 0.5
        end_width = min(width, radius * 2.0)
        half_width = end_width * 0.5
        return math.sqrt(max(0.0, radius * radius - half_width * half_width)), end_width, False

    rows = _junction_rows(shaft)
    if len(rows) <= 1:
        return 0.0, width, True
    geometry = _round_junction_geometry(shaft, factor, rows)
    if geometry is not None:
        return geometry["trim"], width, False
    if _junction_is_straight(rows):
        return 0.0, width, False
    styles = {row["pipe"]["join_style"] for row in rows}
    style = styles.pop() if len(styles) == 1 else "round"
    if style == "round":
        hub_radius = max(
            max(row["pipe"]["dn_mm"] for row in rows) / 2000.0 / factor,
            max(row["pipe"].get("fillet_radius_m", 0.20) for row in rows) / factor)
        return math.sqrt(max(0.0, hub_radius * hub_radius - (width * 0.5) ** 2)), width, False
    return 0.0, width, False


def _trim_plan_band(first, second, width, start, end, factor, pipe):
    """Terminate a band at shafts, closed ends, or tangent junction points."""
    dx, dy = second[0] - first[0], second[1] - first[1]
    length = math.hypot(dx, dy)
    if length <= 1e-9:
        return first, second, width, width, False, False
    ux, uy = dx / length, dy / length
    at_start, start_width, cap_start = _connection_profile(start, pipe, width, factor)
    at_end, end_width, cap_end = _connection_profile(end, pipe, width, factor)
    if at_start + at_end >= length - 1e-9:
        available = length * 0.45
        total = at_start + at_end
        if total > 1e-9:
            at_start *= available / total
            at_end *= available / total
    return ((first[0] + ux * at_start, first[1] + uy * at_start),
            (second[0] - ux * at_end, second[1] - uy * at_end),
            start_width, end_width, cap_start, cap_end)


def _mesh(faces, class_value, color, fill_color=None, fill_opacity=100):
    """Create a closed native mesh without relying on rotated extrudes."""
    prepared = []
    for face in faces:
        if len(face) < 3:
            raise core.SewerError("Eine 3D-Meshfläche besitzt zu wenige Punkte.")
        prepared.append(tuple(tuple(float(component) for component in point)
                              for point in face))
    previous = vs.LNewObj()
    vs.PushAttrs()
    try:
        vs.BeginMesh()
        for face in prepared:
            vs.BeginPoly3D()
            for point in face:
                vs.Add3DPt(point)
            vs.EndPoly3D()
        vs.EndMesh()
    finally:
        vs.PopAttrs()
    handle = vs.LNewObj()
    if not handle or handle == previous or int(vs.GetTypeN(handle) or 0) != 40:
        raise core.SewerError("Vectorworks konnte den 3D-Meshkörper nicht erzeugen.")
    # SetFPat/SetLSN/SetLW are intentionally not called for mesh type 40;
    # Vectorworks 2026 reports those calls as an incorrect object type.
    vs.SetClass(handle, class_value)
    vs.SetPenFore(handle, color)
    vs.SetPenBack(handle, color)
    fill_color = color if fill_color is None else fill_color
    vs.SetFillFore(handle, fill_color)
    vs.SetFillBack(handle, fill_color)
    vs.SetOpacityN(handle, 100, int(fill_opacity))
    return handle


def _ring(center, radius, first_axis, second_axis, segments=24):
    result = []
    for index in range(segments):
        angle = math.tau * index / segments
        result.append(tuple(
            center[coordinate] + radius * (
                first_axis[coordinate] * math.cos(angle) +
                second_axis[coordinate] * math.sin(angle))
            for coordinate in range(3)))
    return tuple(result)


def _cylinder_faces(first, second, radius, segments=24):
    vector = tuple(second[index] - first[index] for index in range(3))
    length = math.sqrt(sum(component * component for component in vector))
    if length <= 1e-9 or radius <= 0:
        raise core.SewerError("Ungültige 3D-Rohrgeometrie.")
    axis = tuple(component / length for component in vector)
    reference = (0.0, 0.0, 1.0) if abs(axis[2]) < 0.9 else (0.0, 1.0, 0.0)
    first_axis = (axis[1] * reference[2] - axis[2] * reference[1],
                  axis[2] * reference[0] - axis[0] * reference[2],
                  axis[0] * reference[1] - axis[1] * reference[0])
    magnitude = math.sqrt(sum(component * component for component in first_axis))
    first_axis = tuple(component / magnitude for component in first_axis)
    second_axis = (axis[1] * first_axis[2] - axis[2] * first_axis[1],
                   axis[2] * first_axis[0] - axis[0] * first_axis[2],
                   axis[0] * first_axis[1] - axis[1] * first_axis[0])
    bottom = _ring(first, radius, first_axis, second_axis, segments)
    top = _ring(second, radius, first_axis, second_axis, segments)
    faces = [tuple(reversed(bottom)), top]
    for index in range(segments):
        following = (index + 1) % segments
        faces.append((bottom[index], bottom[following], top[following], top[index]))
    return tuple(faces)


def _tube_faces(stations, segments=24):
    """Create one closed straight tube with optional tapered end stations."""
    values = tuple((tuple(center), float(radius)) for center, radius in stations)
    if len(values) < 2 or any(radius <= 0.0 for _center_value, radius in values):
        raise core.SewerError("Ungültige 3D-Rohrgeometrie.")
    first, second = values[0][0], values[-1][0]
    vector = tuple(second[index] - first[index] for index in range(3))
    length = math.sqrt(sum(component * component for component in vector))
    if length <= 1e-9:
        raise core.SewerError("Ungültige 3D-Rohrgeometrie.")
    axis = tuple(component / length for component in vector)
    reference = (0.0, 0.0, 1.0) if abs(axis[2]) < 0.9 else (0.0, 1.0, 0.0)
    first_axis = (axis[1] * reference[2] - axis[2] * reference[1],
                  axis[2] * reference[0] - axis[0] * reference[2],
                  axis[0] * reference[1] - axis[1] * reference[0])
    magnitude = math.sqrt(sum(component * component for component in first_axis))
    first_axis = tuple(component / magnitude for component in first_axis)
    second_axis = (axis[1] * first_axis[2] - axis[2] * first_axis[1],
                   axis[2] * first_axis[0] - axis[0] * first_axis[2],
                   axis[0] * first_axis[1] - axis[1] * first_axis[0])
    rings = tuple(_ring(center, radius, first_axis, second_axis, segments)
                  for center, radius in values)
    faces = [tuple(reversed(rings[0])), rings[-1]]
    for lower, upper in zip(rings, rings[1:]):
        for index in range(segments):
            following = (index + 1) % segments
            faces.append((lower[index], lower[following], upper[following], upper[index]))
    return tuple(faces)


def _hollow_tube_faces(stations, wall, segments=24):
    """Create a closed pipe wall with outside, inside and annular end faces."""
    values = tuple((tuple(center), float(radius)) for center, radius in stations)
    wall = float(wall)
    if wall <= 0.0 or any(radius <= wall for _center, radius in values):
        raise core.SewerError("Ungültige Wandstärke der 3D-Rohrgeometrie.")
    first, second = values[0][0], values[-1][0]
    vector = tuple(second[index] - first[index] for index in range(3))
    length = math.sqrt(sum(component * component for component in vector))
    if length <= 1e-9:
        raise core.SewerError("Ungültige 3D-Rohrgeometrie.")
    axis = tuple(component / length for component in vector)
    reference = (0.0, 0.0, 1.0) if abs(axis[2]) < 0.9 else (0.0, 1.0, 0.0)
    first_axis = (axis[1] * reference[2] - axis[2] * reference[1],
                  axis[2] * reference[0] - axis[0] * reference[2],
                  axis[0] * reference[1] - axis[1] * reference[0])
    magnitude = math.sqrt(sum(component * component for component in first_axis))
    first_axis = tuple(component / magnitude for component in first_axis)
    second_axis = (axis[1] * first_axis[2] - axis[2] * first_axis[1],
                   axis[2] * first_axis[0] - axis[0] * first_axis[2],
                   axis[0] * first_axis[1] - axis[1] * first_axis[0])
    outer = tuple(_ring(center, radius, first_axis, second_axis, segments)
                  for center, radius in values)
    inner = tuple(_ring(center, radius - wall, first_axis, second_axis, segments)
                  for center, radius in values)
    faces = []
    for lower, upper in zip(outer, outer[1:]):
        for index in range(segments):
            following = (index + 1) % segments
            faces.append((lower[index], lower[following], upper[following], upper[index]))
    for lower, upper in zip(inner, inner[1:]):
        for index in range(segments):
            following = (index + 1) % segments
            faces.append((lower[following], lower[index], upper[index], upper[following]))
    for outer_ring, inner_ring, reverse in (
            (outer[0], inner[0], True), (outer[-1], inner[-1], False)):
        for index in range(segments):
            following = (index + 1) % segments
            face = (outer_ring[index], inner_ring[index],
                    inner_ring[following], outer_ring[following])
            faces.append(tuple(reversed(face)) if reverse else face)
    return tuple(faces)


def _draw_pipe_3d(first, second, radius, class_value, color,
                  start_radius=None, end_radius=None, wall=None):
    start_radius = radius if start_radius is None else start_radius
    end_radius = radius if end_radius is None else end_radius
    vector = tuple(second[index] - first[index] for index in range(3))
    length = math.sqrt(sum(component * component for component in vector))
    if length <= 1e-9:
        raise core.SewerError("Ungültige 3D-Rohrgeometrie.")
    axis = tuple(component / length for component in vector)
    transition = min(radius * 2.0, length * 0.25)
    stations = [(first, start_radius)]
    if abs(start_radius - radius) > 1e-9:
        stations.append((tuple(first[index] + axis[index] * transition for index in range(3)), radius))
    if abs(end_radius - radius) > 1e-9:
        stations.append((tuple(second[index] - axis[index] * transition for index in range(3)), radius))
    stations.append((second, end_radius))
    faces = (_hollow_tube_faces(stations, wall)
             if wall is not None else _tube_faces(stations))
    return _mesh(faces, class_value, color)


def _layer_z_m(handle):
    value = vs.GetLayerElevation(vs.GetLayer(handle))
    try:
        return float(value[0]) / 1000.0
    except (TypeError, ValueError, IndexError) as error:
        raise core.SewerError("Ebenenhöhe konnte nicht gelesen werden.") from error


def _sync_rigole_connection_nodes(rigole, factor):
    """Keep attached hidden nodes on their dimensionless rigole-side anchors."""
    for connection in rigole.get("connections", ()):
        node_handle = _handle_by_id(core.SHAFT_PREFIX, connection["node_id"])
        if not node_handle:
            raise core.SewerError(
                "Ein Anschlussknoten der Rigole fehlt. Kanalnetz prüfen.")
        node_data = _live().data_of(node_handle)
        node = read_shaft(node_handle, node_data)
        target = core.rigole_connection_xy(
            rigole, connection["side"], connection["fraction"])
        distance = math.dist((node["x_m"], node["y_m"]), target)
        if distance <= 1e-8:
            continue
        dx, dy = target[0] - node["x_m"], target[1] - node["y_m"]
        moved = core.validate_shaft(dict(
            node, x_m=target[0], y_m=target[1],
            ks_m=connection["invert_m"], rigole_id=rigole["id"]),
            allow_hidden=True)
        _live().write_data(node_handle, dict(node_data, shaft=moved))
        vs.HMove(node_handle, dx / factor, dy / factor)
        _reset_checked(node_handle)
        for pipe_handle, _pipe in _connected_pipes(node["id"]):
            _reset_checked(pipe_handle)


def _closed_extrude(points, bottom, top):
    """Create one capped Vectorworks extrude from a closed polygon profile.

    ``BeginPoly`` follows Vectorworks' global open/closed polygon creation
    mode.  The former rigole implementation never switched that mode, so its
    four profile points produced only three extruded wall segments and no
    top/bottom caps.  Keep the closed mode tightly scoped and verify the
    documented extrude object type (24) before returning the body.
    """
    values = tuple(points)
    if len(values) < 3 or float(top) <= float(bottom):
        raise core.SewerError("Ungültige Abmessungen des 3D-Rigolenkörpers.")
    previous = vs.LNewObj()
    try:
        vs.BeginXtrd(float(bottom), float(top))
        vs.ClosePoly()
        try:
            vs.BeginPoly()
            for value in values:
                vs.AddPoint(value)
            vs.EndPoly()
        finally:
            # Never leak the global closed-polygon mode into pipe axes or
            # later user geometry created during the same reset.
            vs.OpenPoly()
        vs.EndXtrd()
    except Exception as error:
        try:
            vs.OpenPoly()
        except Exception:
            pass
        raise core.SewerError(
            "Der geschlossene 3D-Rigolenkörper konnte nicht erzeugt werden.") from error
    body = vs.LNewObj()
    if (not body or body == previous or
            int(vs.GetTypeN(body) or 0) != 24):
        raise core.SewerError(
            "Vectorworks hat für die Rigole keinen geschlossenen Extrusionskörper erzeugt.")
    return body


def draw_rigole(handle, data):
    """Draw one rotated rectangle and one closed 3D storage body."""
    rigole = read_rigole(handle, data)
    preferences = data["preferences"]
    ensure_classes(preferences)
    factor = adapter.units_to_meters()
    class_value = class_name(rigole, preferences)
    class_3d = class_name(rigole, preferences, "_3D")
    world_corners = core.rigole_corners(rigole)
    local = tuple(((x - rigole["x_m"]) / factor,
                   (y - rigole["y_m"]) / factor)
                  for x, y in world_corners)
    _set_rigole_graphics(
        handle, class_value, rigole["pen_color"], rigole["fill_color"],
        rigole["transparency_percent"])
    vs.BeginPoly()
    for value in local:
        vs.AddPoint(value)
    vs.EndPoly()
    plan = vs.LNewObj()
    if not plan:
        raise core.SewerError("2D-Rigole konnte nicht erzeugt werden.")
    vs.SetPolyClosed(plan, True)
    _set_rigole_graphics(
        plan, class_value, rigole["pen_color"], rigole["fill_color"],
        rigole["transparency_percent"])
    layer_z = _layer_z_m(handle)
    bottom = (rigole["bottom_m"] - layer_z) / factor
    top = (rigole["top_m"] - layer_z) / factor
    body = _closed_extrude(local, bottom, top)
    _set_rigole_graphics(
        body, class_3d, rigole["pen_color"], rigole["fill_color"],
        rigole["transparency_percent"])
    vs.ResetOrientation3D()
    _sync_rigole_connection_nodes(rigole, factor)
    updated = dict(data, rigole=rigole)
    _live().write_data(handle, updated)
    _reset_labels(updated)


def draw_pipe(handle, data):
    pipe = read_pipe(handle, data)
    (_start_handle, start), (_end_handle, end) = _endpoints(pipe)
    preferences = data["preferences"]
    ensure_classes(preferences)
    factor = adapter.units_to_meters()
    origin = adapter.symbol_location_2d(handle, (0.0, 0.0))
    first = (start["x_m"] / factor - origin[0], start["y_m"] / factor - origin[1])
    second = (end["x_m"] / factor - origin[0], end["y_m"] / factor - origin[1])
    color = color_for(data, preferences)
    width = pipe["outside_diameter_mm"] / 1000.0 / factor
    ensure_pipe_classes(pipe, preferences, color)
    class_value = class_name(pipe, preferences)
    _set_graphics(handle, class_value, color,
                  fill=pipe["graphics_mode"] == "double_line", opacity=50)
    (plan_first, plan_second, start_width, end_width,
     cap_start, cap_end) = _trim_plan_band(
         first, second, width, start, end, factor, pipe)
    if pipe["graphics_mode"] == "double_line":
        _draw_band(plan_first, plan_second, width, class_value, color,
                   start_width, end_width, cap_start, cap_end)
        _draw_open_polyline(
            (plan_first, plan_second), axis_class_name(pipe, preferences), TEXT_COLOR,
            pipe.get("axis_line_type", preferences["axis_line_type"]))
    else:
        _draw_open_polyline(
            (plan_first, plan_second), class_value, color, pipe["line_type"])
    # Pipe data is normally stored from the higher to the lower invert. Keep
    # this explicit so migrated data can never display an uphill arrow.
    arrow_first, arrow_second = plan_first, plan_second
    if pipe["start_invert_m"] < pipe["end_invert_m"]:
        arrow_first, arrow_second = arrow_second, arrow_first
    _draw_flow_arrow(arrow_first, arrow_second, pipe["flow_arrow_scale"], factor,
                     preferences["flow_arrow_class"])
    if pipe["draw_3d"]:
        layer_z = _layer_z_m(handle)
        axis_offset = core.pipe_axis_offset_m(pipe)
        full_length = math.dist(first, second)
        start_fraction = math.dist(first, plan_first) / full_length
        end_fraction = math.dist(first, plan_second) / full_length
        invert_delta = pipe["end_invert_m"] - pipe["start_invert_m"]
        first_invert = pipe["start_invert_m"] + invert_delta * start_fraction
        second_invert = pipe["start_invert_m"] + invert_delta * end_fraction
        first3d = (plan_first[0], plan_first[1],
                   (first_invert + axis_offset - layer_z) / factor)
        second3d = (plan_second[0], plan_second[1],
                    (second_invert + axis_offset - layer_z) / factor)
        outer_radius = pipe["outside_diameter_mm"] / 2000.0 / factor
        wall = pipe["wall_thickness_mm"] / 1000.0 / factor if pipe["hollow_3d"] else None
        _draw_pipe_3d(first3d, second3d, outer_radius,
                      class_name(pipe, preferences, "_3D"), color,
                      start_width * 0.5, end_width * 0.5, wall)
        vs.ResetOrientation3D()
    updated = dict(data, pipe=pipe)
    _live().write_data(handle, updated)
    _reset_labels(updated)


def _frustum_faces(bottom_center, bottom_radius, top_center, top_radius, segments=24):
    axes = (1.0, 0.0, 0.0), (0.0, 1.0, 0.0)
    bottom = _ring(bottom_center, bottom_radius, axes[0], axes[1], segments)
    top = _ring(top_center, top_radius, axes[0], axes[1], segments)
    faces = [tuple(reversed(bottom)), top]
    for index in range(segments):
        following = (index + 1) % segments
        faces.append((bottom[index], bottom[following], top[following], top[index]))
    return tuple(faces)


def _draw_shaft_3d(handle, shaft, class_value, pen_color, fill_color,
                   transparency_percent, factor, cover_class_value=None):
    layer_z = _layer_z_m(handle)
    z0 = (shaft["ks_m"] - layer_z) / factor
    z1 = (shaft["kd_m"] - layer_z) / factor
    radius = core.shaft_outer_diameter_m(shaft) / factor / 2.0
    cover_radius = shaft["cover_diameter_m"] / factor / 2.0
    if z1 <= z0:
        z1 = z0 + 0.01 / factor
    transition_height = min(0.60 / factor, z1 - z0)
    transition_bottom = z1 - transition_height
    if transition_bottom > z0 + 1e-9:
        vs.BeginXtrd(z0, transition_bottom)
        vs.Oval((-radius, radius), (radius, -radius))
        vs.EndXtrd()
        body = vs.LNewObj()
        if not body:
            raise core.SewerError("3D-Schachtkörper konnte nicht erzeugt werden.")
        _set_shaft_graphics(
            body, class_value, pen_color, fill_color,
            transparency_percent, fill=True)
    cover_center = _cover_center(shaft, factor)
    fill_opacity = int(round(100.0 - transparency_percent))
    _mesh(_frustum_faces(
        (0.0, 0.0, transition_bottom), radius,
        (cover_center[0], cover_center[1], z1), cover_radius),
        class_value, pen_color, fill_color, fill_opacity)
    cover = 0.05 / factor
    vs.BeginXtrd(z1, z1 + cover)
    vs.Oval(((cover_center[0] - cover_radius), (cover_center[1] + cover_radius)),
            ((cover_center[0] + cover_radius), (cover_center[1] - cover_radius)))
    vs.EndXtrd()
    lid = vs.LNewObj()
    if not lid:
        raise core.SewerError("3D-Schachtdeckel konnte nicht erzeugt werden.")
    _set_shaft_graphics(
        lid, cover_class_value or class_value, pen_color, fill_color,
        transparency_percent, fill=True)


def _connected_pipes(identity):
    return tuple((handle, pipe) for handle, pipe in pipe_records()
                 if identity in (pipe["start_id"], pipe["end_id"]))


def _refresh_stub_stationing(shaft):
    """Derive a station for every connection inserted into a main holding."""
    if (shaft.get("structure_type") == "stub" and
            shaft.get("stub", {}).get("station_enabled", False)):
        field = "stub"
    elif (shaft.get("connection_station") or {}).get("station_enabled", False):
        field = "connection_station"
    else:
        return shaft
    result = copy.deepcopy(shaft)
    reference = result[field]
    # Rebuild the axis from the two local main arms on every reset. Seeding
    # both arms deliberately crosses only this connection; _holding_component
    # then follows invisible bends and main arms at other fittings, while any
    # currently visible shaft forms a new station boundary. Besides keeping
    # moved geometry current, this upgrades legacy fitting data whose cached
    # station_pipe_ids contained only the two local arms.
    axis_map = {}
    for pipe_id in reference["main_pipe_ids"]:
        pipe_handle = _handle_by_id(core.PIPE_PREFIX, pipe_id)
        if not pipe_handle:
            raise core.SewerError("Hauptarm der Anschlussstationierung fehlt.")
        local_pipe = read_pipe(pipe_handle)
        _current, component_map, component = _holding_component(local_pipe)
        for identity in component:
            axis_map[identity] = component_map[identity]
    reference.update(_station_axis_link(
        tuple(axis_map.values()), reference["main_pipe_ids"]))
    start_handle = _handle_by_id(core.SHAFT_PREFIX, reference["main_start_id"])
    end_handle = _handle_by_id(core.SHAFT_PREFIX, reference["main_end_id"])
    if not start_handle or not end_handle:
        raise core.SewerError("Stationierungsnullpunkt des Haltungsanschlusses fehlt.")
    start = read_shaft(start_handle)
    end = read_shaft(end_handle)
    main_pipes = {}
    for pipe_id in reference.get("station_pipe_ids", reference["main_pipe_ids"]):
        pipe_handle = _handle_by_id(core.PIPE_PREFIX, pipe_id)
        if not pipe_handle:
            raise core.SewerError("Hauptleitung der Anschlussstationierung fehlt.")
        main_pipes[pipe_id] = read_pipe(pipe_handle)

    def invert_at(identity):
        values = []
        for pipe in main_pipes.values():
            if pipe["start_id"] == identity:
                values.append(pipe["start_invert_m"])
            if pipe["end_id"] == identity:
                values.append(pipe["end_invert_m"])
        if len(values) != 1:
            raise core.SewerError("Hauptleitungssohle der Anschlussstationierung ist nicht eindeutig.")
        return values[0]

    def axis_from(identity):
        points = []
        current = identity
        visited = set()
        while True:
            if current == result["id"]:
                node = result
            else:
                node_handle = _handle_by_id(core.SHAFT_PREFIX, current)
                if not node_handle:
                    raise core.SewerError(
                        "Ein Achsenknoten der Anschlussstationierung fehlt.")
                node = read_shaft(node_handle)
            points.append((node["x_m"], node["y_m"]))
            if current == result["id"]:
                return tuple(points)
            candidates = [pipe for pipe in main_pipes.values()
                          if pipe["id"] not in visited and current in (
                              pipe["start_id"], pipe["end_id"])]
            if len(candidates) != 1:
                raise core.SewerError(
                    "Die Achse der Anschlussstationierung ist nicht durchgängig eindeutig.")
            pipe = candidates[0]
            visited.add(pipe["id"])
            current = (pipe["end_id"] if pipe["start_id"] == current
                       else pipe["start_id"])

    try:
        station = stub_stationing.calculate(
            {"id": start["id"], "x_m": start["x_m"], "y_m": start["y_m"],
             "invert_m": invert_at(start["id"])},
            {"id": end["id"], "x_m": end["x_m"], "y_m": end["y_m"],
             "invert_m": invert_at(end["id"])},
            (result["x_m"], result["y_m"]),
            start_axis=axis_from(start["id"]),
            end_axis=axis_from(end["id"]))
    except stub_stationing.StubStationingError as error:
        raise core.SewerError(str(error)) from error
    zero = start if station["station_zero_id"] == start["id"] else end
    reference.update(station, station_zero_name=zero.get("name", ""))
    result[field] = reference
    return core.validate_shaft(result, allow_hidden=True)


def _downstream_pipes(identity, excluded_pipe_ids=()):
    """Return every pipe reachable in its stored flow direction."""
    root = str(identity)
    excluded = set(str(value) for value in excluded_pipe_ids)
    rows = tuple(pipe_records())
    result = {}
    pending = [root]
    visited_nodes = set()
    while pending:
        node = pending.pop(0)
        if node in visited_nodes:
            continue
        visited_nodes.add(node)
        for pipe_handle, pipe in rows:
            if pipe["id"] in excluded or pipe["start_id"] != node:
                continue
            if pipe["end_id"] == root:
                raise core.SewerError(
                    "Die automatische Höhenweiterführung ist in einem Kanalring nicht eindeutig.")
            result[pipe_handle] = pipe
            pending.append(pipe["end_id"])
    return tuple(result.items())


def _downstream_height_changes(rows, root_id, delta_m, mode):
    """Prepare downstream pipe changes without mutating document data."""
    delta = core.number(delta_m, "Höhenänderung")
    if mode not in ("shift", "slope"):
        raise core.SewerError("Ungültige Weiterführung der Kanalhöhen.")
    changed = {}
    for pipe_handle, pipe in rows:
        if mode == "slope" and pipe["start_id"] != root_id:
            continue
        value = dict(pipe)
        value["start_invert_m"] += delta
        if mode == "shift":
            value["end_invert_m"] += delta
        # A slope adjustment can deliberately lift the downstream start above
        # or below its former end.  Direction is confirmed and normalized by
        # the caller before the transaction is committed.
        changed[pipe_handle] = value
    return changed


def _confirmed_pipe_directions(pipe_updates):
    """Validate prospective pipes after one confirmation for all reversals."""
    updates = dict(pipe_updates)
    names = {shaft["id"]: (shaft.get("name") or shaft["id"])
             for _handle, shaft in shaft_records()}
    reversals = []
    for handle, pipe in updates.items():
        if core.pipe_flow_reversal_required(pipe):
            start_name = names.get(pipe.get("start_id"), pipe.get("start_id", "?"))
            end_name = names.get(pipe.get("end_id"), pipe.get("end_id", "?"))
            reversals.append((handle, "%s → %s wird zu %s → %s" %
                              (start_name, end_name, end_name, start_name)))
    if reversals and not sewer_ui.confirm_flow_reversal(
            tuple(description for _handle, description in reversals)):
        return None
    reversal_handles = {handle for handle, _description in reversals}
    result = {}
    for handle, pipe in updates.items():
        if handle in reversal_handles:
            result[handle], _reversed = core.orient_pipe_downhill(pipe)
        else:
            result[handle] = core.validate_pipe(pipe)
    return result


def edit_stub_alignment(handle, preferences):
    """Edit one fitting without treating it as a manhole."""
    data = _live().data_of(handle)
    shaft = read_shaft(handle, data)
    if shaft.get("structure_type") != "stub" or not shaft.get("stub"):
        raise core.SewerError("Das gewählte Kanalbauteil ist kein Stutzen.")
    alignment = sewer_ui.stub_alignment_dialog(
        shaft["stub"]["alignment"], editing=True)
    if alignment is None:
        return False
    connected = tuple(_connected_pipes(shaft["id"]))
    changed_shaft, changed_branch = core.change_stub_alignment(
        shaft, tuple(pipe for _pipe_handle, pipe in connected), alignment)
    pipe_handles = {pipe["id"]: pipe_handle for pipe_handle, pipe in connected}
    branch_handle = pipe_handles.get(changed_branch["id"])
    if not branch_handle:
        raise core.SewerError("Die Anschlussleitung des Stutzens fehlt.")
    pipe_updates = _confirmed_pipe_directions({branch_handle: changed_branch})
    if pipe_updates is None:
        return False
    _commit_network_updates(
        pipe_updates, {handle: changed_shaft}, preferences,
        "PD Kanalstutzen bearbeiten")
    return True


def edit_terminal(handle, preferences):
    """Edit one floor drain or house endpoint and its connected pipe height."""
    data = _live().data_of(handle)
    original = read_shaft(handle, data)
    if original.get("structure_type") not in ("floor_drain", "house"):
        raise core.SewerError("Das gewählte Objekt ist kein Bodenablauf oder Hausanschluss.")
    connected = _connected_pipes(original["id"])
    if len(connected) != 1:
        raise core.SewerError(
            "Ein Bodenablauf oder Hausanschluss muss genau eine Anschlussleitung besitzen.")
    updated = sewer_ui.terminal_properties_dialog(original, preferences)
    if updated is None:
        return False
    pipe_handle, pipe = connected[0]
    changed_pipe = copy.deepcopy(pipe)
    if pipe["start_id"] == original["id"]:
        changed_pipe["start_invert_m"] = updated["ks_m"]
    else:
        changed_pipe["end_invert_m"] = updated["ks_m"]
    pipe_updates = _confirmed_pipe_directions({pipe_handle: changed_pipe})
    if pipe_updates is None:
        return False
    _commit_network_updates(
        pipe_updates, {handle: updated}, preferences,
        "PD %s bearbeiten" % (
            "Bodenablauf" if updated["structure_type"] == "floor_drain"
            else "Hausanschluss"))
    return True


def edit_floor_drains(handles, preferences):
    """Apply one body size and optional library symbol to several drains."""
    requested = tuple(dict.fromkeys(tuple(handles or ())))
    if len(requested) < 2:
        raise core.SewerError(
            "Für die Mehrfachbearbeitung mindestens zwei Bodenabläufe markieren.")
    rows = []
    for handle in requested:
        data = _live().data_of(handle)
        if (not is_sewer_data(data) or
                data.get("role") != "sewer_floor_drain"):
            raise core.SewerError(
                "Für diese Mehrfachbearbeitung ausschließlich Bodenabläufe markieren.")
        rows.append((handle, read_shaft(handle, data)))
    choice = sewer_ui.floor_drain_batch_dialog(
        tuple(value for _handle, value in rows), preferences)
    if choice is None:
        return False
    updates = {}
    for handle, original in rows:
        changed = copy.deepcopy(original)
        changed.update(choice)
        changed["terminal_depth_m"] = changed["terminal_height_m"]
        # The connection elevation is the lower edge and remains individual.
        changed["kd_m"] = changed["ks_m"] + changed["terminal_height_m"]
        updates[handle] = core.validate_shaft(changed, allow_hidden=True)
    _commit_network_updates(
        {}, updates, preferences, "PD Bodenabläufe mehrfach bearbeiten")
    return True


def _cover_direction(shaft):
    angles = []
    for _pipe_handle, pipe in _connected_pipes(shaft["id"]):
        other_id = pipe["end_id"] if pipe["start_id"] == shaft["id"] else pipe["start_id"]
        other_handle = _handle_by_id(core.SHAFT_PREFIX, other_id)
        if not other_handle:
            continue
        other = read_shaft(other_handle)
        dx, dy = other["x_m"] - shaft["x_m"], other["y_m"] - shaft["y_m"]
        if math.hypot(dx, dy) > 1e-9:
            angles.append(math.degrees(math.atan2(dy, dx)))
    return core.largest_angular_gap_bisector(angles)


def _cover_center(shaft, factor):
    if shaft.get("structure_type") == "special":
        direction = _cover_direction(shaft)
        radians = math.radians(direction)
        dx, dy = math.cos(radians), math.sin(radians)
        support = core.ray_polygon_distance(
            shaft["special_outline_m"], (dx, dy)) / factor
        cover_radius = shaft["cover_diameter_m"] / factor * 0.5
        offset = 0.0 if shaft["cover_placement"] == "center" else max(0.0, support - cover_radius)
        return offset * dx, offset * dy
    radius = core.shaft_outer_diameter_m(shaft) / factor * 0.5
    cover_radius = shaft["cover_diameter_m"] / factor * 0.5
    direction = _cover_direction(shaft)
    offset = 0.0 if shaft["cover_placement"] == "center" else max(0.0, radius - cover_radius)
    radians = math.radians(direction)
    return offset * math.cos(radians), offset * math.sin(radians)


def _draw_shaft_cover(shaft, factor, class_value, color):
    cover_radius = shaft["cover_diameter_m"] / factor * 0.5
    center = _cover_center(shaft, factor)
    symbol_name = shaft.get("cover_symbol", "")
    definition = vs.GetObject(symbol_name) if symbol_name else None
    if definition and int(vs.GetTypeN(definition) or 0) == 16:
        vs.Symbol(symbol_name, center, shaft["cover_rotation_deg"])
        symbol = vs.LNewObj()
        if symbol and int(vs.GetTypeN(symbol) or 0) == 15:
            vs.SetClass(symbol, class_value)
            return symbol
    vs.Oval(((center[0] - cover_radius), (center[1] + cover_radius)),
            ((center[0] + cover_radius), (center[1] - cover_radius)))
    circle = vs.LNewObj()
    if not circle:
        raise core.SewerError("2D-Schachtdeckel konnte nicht erzeugt werden.")
    _set_graphics(circle, class_value, color, fill=False, opacity=100)
    return circle


def _draw_local_polygon(points, class_value, color, fill=True, opacity=50,
                        fill_color=None, transparency_percent=None):
    values = tuple(points)
    if len(values) < 3:
        raise core.SewerError("Bauwerkskontur besitzt zu wenige Punkte.")
    vs.BeginPoly()
    for value in values:
        vs.AddPoint(value)
    vs.EndPoly()
    handle = vs.LNewObj()
    if not handle:
        raise core.SewerError("Bauwerkskontur konnte nicht erzeugt werden.")
    vs.SetPolyClosed(handle, True)
    if fill_color is None:
        _set_graphics(handle, class_value, color, fill=fill, opacity=opacity)
    else:
        _set_shaft_graphics(
            handle, class_value, color, fill_color,
            transparency_percent if transparency_percent is not None
            else 100.0 - opacity, fill=fill)
    return handle


def _draw_special_shaft_3d(handle, shaft, class_value, pen_color, fill_color,
                           transparency_percent, factor,
                           cover_class_value=None):
    layer_z = _layer_z_m(handle)
    z0 = (shaft["ks_m"] - layer_z) / factor
    z1 = (shaft["kd_m"] - layer_z) / factor
    if z1 <= z0:
        z1 = z0 + 0.01 / factor
    cover_center = _cover_center(shaft, factor)
    cover_radius = shaft["cover_diameter_m"] / factor * 0.5
    outline = tuple((x / factor, y / factor) for x, y in shaft["special_outline_m"])
    transition_height = min(0.60 / factor, z1 - z0)
    transition_bottom = z1 - transition_height
    if transition_bottom > z0 + 1e-9:
        vs.BeginXtrd(z0, transition_bottom)
        vs.BeginPoly()
        for point in outline:
            vs.AddPoint(point)
        vs.EndPoly()
        vs.EndXtrd()
        body = vs.LNewObj()
        if not body:
            raise core.SewerError("3D-Sonderschacht konnte nicht erzeugt werden.")
        _set_shaft_graphics(
            body, class_value, pen_color, fill_color,
            transparency_percent, fill=True)
    fill_opacity = int(round(100.0 - transparency_percent))
    _mesh(_special_loft_faces(
        outline, cover_center, cover_radius, transition_bottom, z1),
        class_value, pen_color, fill_color, fill_opacity)
    vs.BeginXtrd(z1, z1 + 0.05 / factor)
    vs.Oval(((cover_center[0] - cover_radius), (cover_center[1] + cover_radius)),
            ((cover_center[0] + cover_radius), (cover_center[1] - cover_radius)))
    vs.EndXtrd()
    lid = vs.LNewObj()
    if not lid:
        raise core.SewerError("3D-Schachtdeckel des Sonderschachts konnte nicht erzeugt werden.")
    _set_shaft_graphics(
        lid, cover_class_value or class_value, pen_color, fill_color,
        transparency_percent, fill=True)


def _sample_closed_outline(points, count):
    values = tuple((float(x), float(y)) for x, y in points)
    lengths = tuple(math.dist(first, second)
                    for first, second in zip(values, values[1:] + values[:1]))
    total = sum(lengths)
    if len(values) < 3 or total <= 1e-9:
        raise core.SewerError("Ungültige 3D-Sonderschachtkontur.")
    result = []
    for index in range(int(count)):
        target = total * index / float(count)
        accumulated = 0.0
        for edge, (first, second) in enumerate(zip(values, values[1:] + values[:1])):
            following = accumulated + lengths[edge]
            if target <= following + 1e-12:
                ratio = 0.0 if lengths[edge] <= 1e-12 else (
                    target - accumulated) / lengths[edge]
                result.append((first[0] + (second[0] - first[0]) * ratio,
                               first[1] + (second[1] - first[1]) * ratio))
                break
            accumulated = following
    return tuple(result)


def _special_loft_faces(outline, cover_center, cover_radius, bottom_z, top_z,
                        segments=24):
    """Create a closed transition from any simple shaft outline to the lid ring."""
    values = tuple(outline)
    count = max(int(segments), len(values))
    sampled = _sample_closed_outline(values, count)
    area = sum(first[0] * second[1] - second[0] * first[1]
               for first, second in zip(sampled, sampled[1:] + sampled[:1]))
    direction = 1.0 if area >= 0.0 else -1.0
    first_angle = math.atan2(sampled[0][1] - cover_center[1],
                             sampled[0][0] - cover_center[0])
    bottom = tuple((x, y, bottom_z) for x, y in sampled)
    top = tuple((cover_center[0] + math.cos(
                    first_angle + direction * 2.0 * math.pi * index / count) * cover_radius,
                 cover_center[1] + math.sin(
                    first_angle + direction * 2.0 * math.pi * index / count) * cover_radius,
                 top_z)
                for index in range(count))
    faces = [tuple(reversed(bottom)), top]
    for index in range(count):
        following = (index + 1) % count
        faces.append((bottom[index], bottom[following], top[following], top[index]))
    return tuple(faces)


def _draw_floor_drain(handle, shaft, class_value, pen_color, fill_color,
                      transparency_percent, factor, draw_3d):
    length = shaft["terminal_length_m"] / factor
    width = shaft["terminal_width_m"] / factor
    symbol_name = shaft.get("terminal_symbol", "")
    definition = vs.GetObject(symbol_name) if symbol_name else None
    symbol_used = bool(definition and int(vs.GetTypeN(definition) or 0) == 16)
    if symbol_used:
        vs.Symbol(symbol_name, (0.0, 0.0), 0.0)
        symbol = vs.LNewObj()
        if symbol:
            vs.SetClass(symbol, class_value)
    half_length = length * 0.5
    half_width = width * 0.5
    if not symbol_used:
        vs.Rect((-half_length, half_width), (half_length, -half_width))
        square = vs.LNewObj()
        if not square:
            raise core.SewerError("2D-Bodenablauf konnte nicht erzeugt werden.")
        _set_shaft_graphics(
            square, class_value, pen_color, fill_color,
            transparency_percent, fill=True)
    if draw_3d and (not symbol_used or not shaft.get("terminal_symbol_has_3d", False)):
        layer_z = _layer_z_m(handle)
        z0 = (shaft["ks_m"] - layer_z) / factor
        z1 = (shaft["kd_m"] - layer_z) / factor
        vs.BeginXtrd(z0, max(z1, z0 + 0.01 / factor))
        vs.Rect((-half_length, half_width), (half_length, -half_width))
        vs.EndXtrd()
        body = vs.LNewObj()
        if not body:
            raise core.SewerError("3D-Bodenablaufkasten konnte nicht erzeugt werden.")
        _set_shaft_graphics(
            body, class_value, pen_color, fill_color,
            transparency_percent, fill=True)


def _draw_stub_symbol(shaft, data, class_value, color, factor):
    """Plan marker for a circular branch fitting at the main holding."""
    rows = _junction_rows(shaft)
    branch_dn = shaft["stub"]["branch_dn_mm"]
    main_ids = set(shaft["stub"].get("main_pipe_ids", ()))
    branch = next((row for row in rows if row["pipe"]["id"] not in main_ids), None)
    direction = branch["direction"] if branch else (1.0, 0.0)
    radius = max(0.08, branch_dn / 2000.0) / factor
    vs.Oval((-radius, radius), (radius, -radius))
    circle = vs.LNewObj()
    if not circle:
        raise core.SewerError("Stutzensymbol konnte nicht erzeugt werden.")
    _set_graphics(circle, class_value, color, fill=False, opacity=100)
    nx, ny = -direction[1], direction[0]
    start = direction[0] * radius, direction[1] * radius
    tip = direction[0] * radius * 2.4, direction[1] * radius * 2.4
    _draw_open_polyline((
        (start[0] + nx * radius * 0.65, start[1] + ny * radius * 0.65), tip,
        (start[0] - nx * radius * 0.65, start[1] - ny * radius * 0.65)),
        class_value, color)


def _draw_stub_3d(handle, shaft, data, factor):
    """Draw one continuous tee/wye fitting between all three pipe bodies.

    The pipe PIOs terminate at the fitting profile.  These overlapping arms
    bridge the two main segments and the branch in both plan and elevation,
    so no open pipe ends or detached short pieces remain in a 3D view.
    """
    rows = _junction_rows(shaft)
    main_ids = set(shaft.get("stub", {}).get("main_pipe_ids", ()))
    main_rows = [row for row in rows if row["pipe"]["id"] in main_ids]
    branch_rows = [row for row in rows if row["pipe"]["id"] not in main_ids]
    if len(main_rows) != 2 or len(branch_rows) != 1:
        return
    active_rows = [row for row in main_rows + branch_rows
                   if row["pipe"].get("draw_3d", True)]
    if len(active_rows) < 2:
        return
    preferences = data["preferences"]
    layer_z = _layer_z_m(handle)

    def axis_height(row):
        pipe = row["pipe"]
        invert = (pipe["start_invert_m"] if pipe["start_id"] == shaft["id"]
                  else pipe["end_invert_m"])
        return (invert + core.pipe_axis_offset_m(pipe) - layer_z) / factor

    main_z = sum(axis_height(row) for row in main_rows) / 2.0
    for row in active_rows:
        pipe = row["pipe"]
        color = color_for({"role": "sewer_pipe", "pipe": pipe}, preferences)
        ensure_pipe_classes(pipe, preferences, color)
        radius = pipe["outside_diameter_mm"] / 2000.0 / factor
        width = radius * 2.0
        trim, _end_width, _cap = _connection_profile(shaft, pipe, width, factor)
        # A slight overlap hides the capped end face of the adjacent pipe mesh
        # and produces a visually continuous fitting without boolean solids.
        arm = max(trim + 0.01 / factor, radius * 1.10)
        direction = row["direction"]
        end = (direction[0] * arm, direction[1] * arm, axis_height(row))
        start_radius = radius
        if row in branch_rows:
            main_radius = max(
                value["pipe"]["outside_diameter_mm"] / 2000.0 / factor
                for value in main_rows)
            start_radius = min(radius, main_radius) * 0.82
        _draw_pipe_3d(
            (0.0, 0.0, main_z), end, radius,
            class_name(pipe, preferences, "_3D"), color,
            start_radius=start_radius, end_radius=radius)


def _draw_drops(handle, shaft, preferences, class_value, color, factor):
    if not shaft.get("drops"):
        return
    layer_z = _layer_z_m(handle)
    connected = {pipe["id"]: pipe for _pipe_handle, pipe in _connected_pipes(shaft["id"])}
    for drop in shaft["drops"]:
        pipe = connected.get(drop["pipe_id"])
        if not pipe:
            continue
        other_id = pipe["start_id"] if pipe["end_id"] == shaft["id"] else pipe["end_id"]
        other_handle = _handle_by_id(core.SHAFT_PREFIX, other_id)
        if not other_handle:
            continue
        other = read_shaft(other_handle)
        dx, dy = other["x_m"] - shaft["x_m"], other["y_m"] - shaft["y_m"]
        length = math.hypot(dx, dy)
        if length <= 1e-9:
            continue
        ux, uy = dx / length, dy / length
        pipe_color = color_for({"role": "sewer_pipe", "pipe": pipe}, preferences)
        pipe_class = class_name(pipe, preferences)
        ensure_pipe_classes(pipe, preferences, pipe_color)
        outside_radius = pipe["outside_diameter_mm"] / 2000.0 / factor
        trim, _end_width, _cap = _connection_profile(
            shaft, pipe, outside_radius * 2.0, factor)
        distance = trim + max(outside_radius * 2.0, 0.20 / factor)
        center = ux * distance, uy * distance
        wall_point = ux * trim, uy * trim
        vs.Oval(((center[0] - outside_radius), (center[1] + outside_radius)),
                ((center[0] + outside_radius), (center[1] - outside_radius)))
        marker = vs.LNewObj()
        if marker:
            _set_graphics(marker, pipe_class, pipe_color, fill=False, opacity=100)
        _draw_open_polyline((wall_point, center), pipe_class, pipe_color)
        if pipe.get("draw_3d", preferences.get("draw_3d", True)):
            axis_offset = core.pipe_axis_offset_m(pipe)
            lower_z = (drop["lower_invert_m"] + axis_offset - layer_z) / factor
            upper_z = (drop["upper_invert_m"] + axis_offset - layer_z) / factor
            class_3d = class_name(pipe, preferences, "_3D")
            if upper_z > lower_z + 1e-9:
                # Upper inlet arm, external vertical fall and lower shaft arm
                # overlap at their axes to form one continuous drop assembly.
                _draw_pipe_3d(
                    (wall_point[0], wall_point[1], upper_z),
                    (center[0], center[1], upper_z),
                    outside_radius, class_3d, pipe_color)
                _draw_pipe_3d(
                    (center[0], center[1], lower_z),
                    (center[0], center[1], upper_z),
                    outside_radius, class_3d, pipe_color)
                _draw_pipe_3d(
                    (center[0], center[1], lower_z),
                    (wall_point[0], wall_point[1], lower_z),
                    outside_radius, class_3d, pipe_color)


def draw_shaft(handle, data):
    old = core.validate_shaft(data["shaft"], allow_hidden=True)
    shaft = read_shaft(handle, data)
    shaft = _refresh_stub_stationing(shaft)
    moved = math.dist((old["x_m"], old["y_m"]), (shaft["x_m"], shaft["y_m"])) > 1e-8
    preferences = data["preferences"]
    ensure_classes(preferences)
    factor = adapter.units_to_meters()
    radius = core.shaft_outer_diameter_m(shaft) / factor / 2.0
    pen_color, fill_color, transparency_percent = shaft_graphics_for(
        shaft, preferences)
    color = pen_color
    class_value = class_name(shaft, preferences)
    cover_value = cover_class_name(shaft, preferences)
    _set_shaft_graphics(
        handle, class_value, pen_color, fill_color,
        transparency_percent, fill=True)
    structure = shaft.get("structure_type", "round" if radius > 0.0 else "junction")
    if structure == "round" and shaft["visible"]:
        if radius > 0.0:
            vs.Oval((-radius, radius), (radius, -radius))
            circle = vs.LNewObj()
            if not circle:
                raise core.SewerError("2D-Schacht konnte nicht erzeugt werden.")
            _set_shaft_graphics(
                circle, class_value, pen_color, fill_color,
                transparency_percent, fill=True)
            if (shaft["construction_material"] == "concrete" and
                    shaft["wall_thickness_m"] > 0.0):
                inner_radius = shaft["diameter_m"] / factor * 0.5
                vs.Oval((-inner_radius, inner_radius), (inner_radius, -inner_radius))
                inner = vs.LNewObj()
                if not inner:
                    raise core.SewerError("Innere Betonschachtkontur konnte nicht erzeugt werden.")
                _set_graphics(inner, class_value, color, fill=False, opacity=100)
            _draw_shaft_cover(shaft, factor, cover_value, color)
            if preferences.get("draw_3d", True):
                _draw_shaft_3d(
                    handle, shaft, class_name(shaft, preferences, "_3D"),
                    pen_color, fill_color, transparency_percent, factor,
                    cover_class_name(shaft, preferences, "_3D"))
                vs.ResetOrientation3D()
    elif structure == "special" and shaft["visible"]:
        _draw_local_polygon(
            tuple((x / factor, y / factor) for x, y in shaft["special_outline_m"]),
            class_value, pen_color, fill=True,
            fill_color=fill_color,
            transparency_percent=transparency_percent)
        _draw_shaft_cover(shaft, factor, cover_value, color)
        if preferences.get("draw_3d", True):
            _draw_special_shaft_3d(
                handle, shaft, class_name(shaft, preferences, "_3D"),
                pen_color, fill_color, transparency_percent, factor,
                cover_class_name(shaft, preferences, "_3D"))
            vs.ResetOrientation3D()
    elif structure == "floor_drain" and shaft["visible"]:
        _draw_floor_drain(
            handle, shaft, class_value, pen_color, fill_color,
            transparency_percent, factor, preferences.get("draw_3d", True))
        vs.ResetOrientation3D()
    elif structure == "house" and shaft["visible"]:
        # The contractual plan representation has no terminal symbol.  The
        # capped branch pipe and its height label remain independently editable.
        pass
    elif structure == "stub":
        _draw_hidden_join(shaft, data)
        _draw_stub_symbol(shaft, data, class_value, color, factor)
        if any(row["pipe"].get("draw_3d", True) for row in _junction_rows(shaft)):
            _draw_stub_3d(handle, shaft, data, factor)
            vs.ResetOrientation3D()
    else:
        _draw_hidden_join(shaft, data)
    _draw_drops(handle, shaft, preferences, class_value, color, factor)
    updated = dict(data, shaft=shaft)
    _live().write_data(handle, updated)
    _reset_labels(updated)
    if moved:
        connected = _connected_pipes(shaft["id"])
        for pipe_handle, _pipe in connected:
            vs.ResetObject(pipe_handle)
            other_id = _pipe["end_id"] if _pipe["start_id"] == shaft["id"] else _pipe["start_id"]
            other_handle = _handle_by_id(core.SHAFT_PREFIX, other_id)
            if other_handle:
                vs.ResetObject(other_handle)
        _reset_holding_dependents(
            tuple(pipe for _pipe_handle, pipe in connected), handle)


def _pipe_anchor(pipe):
    (_a, start), (_b, end) = _endpoints(pipe)
    return ((start["x_m"] + end["x_m"]) * 0.5,
            (start["y_m"] + end["y_m"]) * 0.5)


def _holding_component(pipe):
    """Return the live pipe component that constitutes one real holding."""
    current = core.validate_pipe(pipe)
    pipe_map = {current["id"]: current}
    shaft_map = {}
    # This helper runs repeatedly while labels and stations are rebuilt. One
    # document traversal avoids a separate full scan for pipes, shafts and
    # fittings in large networks.
    for object_handle, data in objects():
        role = data.get("role") if isinstance(data, dict) else None
        if role is None and isinstance(data, dict):
            # Read-only compatibility for older fixtures/data. Persisted
            # objects always carry an explicit semantic role.
            role = ("sewer_pipe" if isinstance(data.get("pipe"), dict) else
                    _node_role(data["shaft"])
                    if isinstance(data.get("shaft"), dict) else None)
        if role == "sewer_pipe":
            try:
                value = core.validate_pipe(data["pipe"])
            except (KeyError, core.SewerError):
                continue
            pipe_map[value["id"]] = value
        elif role in NODE_ROLES:
            try:
                value = read_shaft(object_handle, data)
            except core.SewerError:
                continue
            shaft_map[value["id"]] = value
    at_node = {}
    for value in pipe_map.values():
        at_node.setdefault(value["start_id"], []).append(value["id"])
        at_node.setdefault(value["end_id"], []).append(value["id"])
    neighbours = {identity: set() for identity in pipe_map}
    for identity, pipe_ids in at_node.items():
        shaft = shaft_map.get(identity)
        pairs = ()
        if shaft and shaft.get("structure_type") == "stub":
            main_ids = [value for value in shaft.get("stub", {}).get("main_pipe_ids", ())
                        if value in pipe_map and value in pipe_ids]
            if len(main_ids) == 2:
                pairs = ((main_ids[0], main_ids[1]),)
        elif shaft and not shaft.get("visible", True) and len(pipe_ids) == 2:
            pairs = ((pipe_ids[0], pipe_ids[1]),)
        for first, second in pairs:
            neighbours[first].add(second)
            neighbours[second].add(first)
    component = set()
    pending = [current["id"]]
    while pending:
        identity = pending.pop()
        if identity in component:
            continue
        component.add(identity)
        pending.extend(neighbours.get(identity, ()) - component)
    return current, pipe_map, component


def _reset_holding_dependents(seed_pipes, current_shaft_handle=None):
    """Invalidate complete labels and stations after any axis-node move."""
    affected_pipe_ids = set()
    for pipe in seed_pipes:
        _current, _pipe_map, component = _holding_component(pipe)
        affected_pipe_ids.update(component)
    if not affected_pipe_ids:
        return
    for _pipe_handle, data in objects("sewer_pipe"):
        raw = data.get("pipe") if isinstance(data, dict) else None
        if isinstance(raw, dict) and raw.get("id") in affected_pipe_ids:
            _reset_labels(data)
    for shaft_handle in _station_dependent_shaft_handles(affected_pipe_ids):
        if shaft_handle != current_shaft_handle:
            vs.ResetObject(shaft_handle)


def _station_dependent_shaft_handles(affected_pipe_ids):
    """Find every station whose local or cached axis touches a holding."""
    affected_pipe_ids = set(str(identity) for identity in affected_pipe_ids)
    result = []
    for shaft_handle, shaft in shaft_records():
        references = []
        if shaft.get("structure_type") == "stub" and shaft.get("stub"):
            references.append(shaft["stub"])
        if shaft.get("connection_station"):
            references.append(shaft["connection_station"])
        if any(affected_pipe_ids.intersection(
                set(reference.get("main_pipe_ids", ())).union(
                    reference.get("station_pipe_ids", ())))
                for reference in references):
            result.append(shaft_handle)
    return tuple(result)


def _holding_label_pipe(pipe):
    """Return one dynamically labelled representative per real holding.

    Invisible two-way bends pass the holding through. At a stub, only its two
    recorded main-pipe arms pass through; the branch starts/ends its own
    holding. Visible shafts always separate holdings. This removes duplicate
    labels after repeated fitting splits without combining genuine holdings
    that have a visible intermediate shaft. Consequently a house connection
    or floor-drain branch receives one label regardless of its bend count.
    """
    current, pipe_map, component = _holding_component(pipe)

    def live_length(value):
        try:
            first_handle = _handle_by_id(core.SHAFT_PREFIX, value["start_id"])
            second_handle = _handle_by_id(core.SHAFT_PREFIX, value["end_id"])
            first = read_shaft(first_handle) if first_handle else None
            second = read_shaft(second_handle) if second_handle else None
            if first and second:
                return math.dist((first["x_m"], first["y_m"]),
                                 (second["x_m"], second["y_m"]))
        except core.SewerError:
            pass
        return value["length_m"]

    lengths = {identity: live_length(pipe_map[identity]) for identity in component}
    # Owner identity must not change merely because a bend moved and made a
    # different segment longer. All new/edited segments persist the same
    # holding-level presentation, so this deterministic owner keeps manual
    # label transforms stable across ordinary geometry updates.
    owner_id = max(component)
    result = dict(current)
    result["label_suppressed"] = current["id"] != owner_id
    result["label_length_m"] = sum(lengths.values())
    return core.validate_pipe(result)


def _create_text(text, angle, preferences, wrap_width=0.0, point_size=None,
                 class_value=None):
    vs.TextOrigin((0.0, 0.0))
    vs.CreateText(text)
    handle = vs.LNewObj()
    if not handle:
        raise core.SewerError("Kanalbeschriftung konnte nicht erzeugt werden.")
    vs.SetTextStyleRef(handle, 0)
    font_id = int(vs.GetFontID("Arial") or 0)
    if font_id:
        vs.SetTextFont(handle, 0, len(text), font_id)
    vs.SetTextSize(
        handle, 0, len(text),
        preferences["point_size"] if point_size is None else point_size)
    if wrap_width > 1e-9:
        vs.SetTextWidth(handle, wrap_width)
    vs.SetTextJust(handle, 2)
    vs.SetTextVertAlignN(handle, 3)
    vs.SetTextOrientation(handle, (0.0, 0.0), angle, False)
    vs.SetClass(handle, class_value or preferences["text_class"])
    vs.SetPenFore(handle, TEXT_COLOR)
    vs.SetFPat(handle, 0)
    return handle


def _bbox(value):
    """Normalize GetBBox's documented point pair and flattened stub form."""
    if (isinstance(value, (tuple, list)) and len(value) == 2 and
            all(isinstance(point, (tuple, list)) and len(point) == 2 for point in value)):
        points = value
    elif isinstance(value, (tuple, list)) and len(value) == 4:
        points = ((value[0], value[1]), (value[2], value[3]))
    else:
        raise core.SewerError("Textbegrenzung konnte nicht gelesen werden.")
    try:
        xs = [float(point[0]) for point in points]
        ys = [float(point[1]) for point in points]
    except (TypeError, ValueError) as error:
        raise core.SewerError("Textbegrenzung konnte nicht gelesen werden.") from error
    if not all(math.isfinite(value) for value in xs + ys):
        raise core.SewerError("Textbegrenzung ist ungültig.")
    return ((min(xs), min(ys)), (max(xs), max(ys)))


def _leader(anchor, box, preferences, padding, class_value=None):
    end = label_layout.leader_end(anchor, (box,), padding)
    if math.dist(anchor, end) <= 1e-9:
        return None
    vs.MoveTo(anchor)
    vs.LineTo(end)
    leader = vs.LNewObj()
    if leader:
        _set_graphics(
            leader, class_value or preferences["text_class"], TEXT_COLOR,
            fill=False, opacity=100)
    return leader


def _shaft_label_frame(box, preferences, padding, class_value=None):
    left = box[0][0] - padding
    bottom = box[0][1] - padding
    right = box[1][0] + padding
    top = box[1][1] + padding
    vs.Rect((left, top), (right, bottom))
    frame = vs.LNewObj()
    if not frame:
        raise core.SewerError("Beschriftungsrahmen konnte nicht erzeugt werden.")
    _set_graphics(
        frame, class_value or preferences["text_class"], TEXT_COLOR,
        fill=False, opacity=100)
    return frame, ((left, bottom), (right, top))


def draw_label(handle, data):
    owner = vs.GetObject(data["owner"])
    owner_data = _live().data_of(owner)
    if not owner or not is_sewer_data(owner_data) or _name(handle) not in owner_data.get("labels", ()):
        return
    preferences = owner_data["preferences"]
    ensure_classes(preferences)
    text_class = label_class_name(owner_data, preferences, data)
    active_class = str(vs.ActiveClass() or "")
    try:
        _ensure_class(text_class, TEXT_COLOR, fill=False)
    finally:
        if active_class:
            vs.NameClass(active_class)
    vs.SetClass(handle, text_class)
    factor = adapter.units_to_meters()
    default_position = _label_default_position(owner, owner_data, data)
    label_position = adapter.symbol_location_2d(
        handle, data.get("auto_xy", default_position))
    old_auto = tuple(data.get("auto_xy", label_position))
    if data.get("auto_position", True) and math.dist(label_position, old_auto) > 1e-5:
        data = dict(data, auto_position=False)
        _live().write_data(handle, data)
    angle = 0.0
    wrap_width = 0.0
    shaft_label = False
    shaft_name = ""
    pipe_name = ""
    point_size = None
    node_structure = ""
    if data.get("label_kind") == "connection_height":
        context = _connection_label_context(
            owner, owner_data, data.get("connection_id", ""))
        if not context:
            return
        shaft, row, _index, counts = context
        ux, uy = row["direction"]
        text = "%s KS %s m" % (
            core.connection_plan_name(
                row["role"], row["tag"], counts[row["role"]]),
            core.format_number(row["invert_m"], 2))
        angle = core.readable_line_angle(ux, uy)
        radius_m = max(core.shaft_outer_diameter_m(shaft) * 0.5, 0.25)
        anchor_m = (shaft["x_m"] + ux * radius_m,
                    shaft["y_m"] + uy * radius_m)
        point_size = preferences.get(
            "connection_point_size", preferences["point_size"])
    elif owner_data["role"] == "sewer_pipe":
        pipe = read_pipe(owner, owner_data)
        pipe = _holding_label_pipe(pipe)
        (_a, start), (_b, end) = _endpoints(pipe)
        # Reader direction follows the deep point while remaining line-parallel.
        high, low = ((start, end) if pipe["start_invert_m"] >= pipe["end_invert_m"] else (end, start))
        angle = math.degrees(math.atan2(low["y_m"] - high["y_m"], low["x_m"] - high["x_m"]))
        angle += pipe.get("label_rotation_deg", 0.0)
        text = core.pipe_label(pipe, preferences)
        pipe_name = pipe.get("name", "") if preferences.get("pipe_name_visible", True) else ""
        anchor_m = _pipe_anchor(pipe)
        wrap_width = pipe.get("label_width_m", 0.0) / factor
    elif owner_data["role"] in NODE_ROLES:
        shaft_label = True
        shaft = read_shaft(owner, owner_data)
        node_structure = shaft.get("structure_type", "")
        rows = shaft_connection_views(shaft)
        text = core.shaft_label(shaft, rows, preferences)
        shaft_name = shaft.get("name", "")
        anchor_m = shaft["x_m"], shaft["y_m"]
        if node_structure == "stub":
            point_size = preferences.get(
                "stub_height_point_size", preferences["point_size"])
        elif node_structure in ("floor_drain", "house"):
            point_size = shaft.get(
                "terminal_label_point_size",
                preferences.get("floor_drain_label_point_size",
                                preferences["point_size"]))
    elif owner_data["role"] == "sewer_rigole":
        shaft_label = True
        rigole = read_rigole(owner, owner_data)
        text = core.rigole_label(rigole, preferences)
        shaft_name = rigole.get("name", "")
        anchor_m = rigole["x_m"], rigole["y_m"]
    else:
        return
    if not text:
        return
    # Keep the line-parallel angle in the label object's local coordinates.
    # Rotating the parametric label with Vectorworks' normal Rotate command
    # now adds the user's angle instead of being cancelled during every reset.
    rotation = float(vs.GetSymRot(handle) or 0.0)
    text_handle = _create_text(
        text, angle, preferences, wrap_width, point_size=point_size,
        class_value=text_class)
    if pipe_name and text.startswith(pipe_name):
        vs.SetTextSize(
            text_handle, 0, len(pipe_name),
            preferences.get("pipe_name_point_size", preferences["point_size"]))
    if (shaft_label and shaft_name and text.startswith(shaft_name) and
            node_structure not in ("stub", "floor_drain", "house")):
        # Vectorworks text styles are bit flags: bold=1, underline=4.
        style = {"normal": 0, "bold": 1, "underline": 4,
                 "bold_underline": 5}[
                     preferences.get("shaft_name_text_style", "bold")]
        vs.SetTextSize(text_handle, 0, len(shaft_name),
                       preferences.get("shaft_name_point_size",
                                       preferences["point_size"]))
        vs.SetTextStyle(text_handle, 0, len(shaft_name), style)
    if node_structure == "stub":
        offset = 0
        for line in text.splitlines(True):
            content = line.rstrip("\r\n")
            size = (preferences.get("stub_station_point_size", preferences["point_size"])
                    if content.startswith("ST 0+") else
                    preferences.get("stub_height_point_size", preferences["point_size"]))
            if content:
                vs.SetTextSize(text_handle, offset, offset + len(content), size)
            offset += len(line)
    box = _bbox(vs.GetBBox(text_handle))
    scale = max(1.0, float(vs.GetLScale(vs.GetLayer(handle)) or 1.0))
    padding = 0.0008 * scale / factor
    anchor_world = (anchor_m[0] / factor - label_position[0],
                    anchor_m[1] / factor - label_position[1])
    radians = math.radians(-rotation)
    anchor = (anchor_world[0] * math.cos(radians) - anchor_world[1] * math.sin(radians),
              anchor_world[0] * math.sin(radians) + anchor_world[1] * math.cos(radians))
    if shaft_label:
        _frame, framed_box = _shaft_label_frame(
            box, preferences, padding, text_class)
        _leader(anchor, framed_box, preferences, 0.0, text_class)
    elif not data.get("auto_position", True) and math.dist(label_position, default_position) > 1e-5:
        _leader(anchor, box, preferences, padding, text_class)


def _unique_shaft_name(name, own_id=None):
    for _handle, shaft in shaft_records():
        if shaft["id"] != own_id and shaft["name"] == name:
            raise core.SewerError("Schachtbezeichnung %s ist bereits vorhanden." % name)


def _prepare_network_updates(pipe_updates, shaft_updates):
    """Validate a prospective network and derive every affected shaft soil."""
    pipe_updates = dict(pipe_updates)
    shaft_updates = dict(shaft_updates)
    pipe_rows = tuple(pipe_records())
    shaft_rows = tuple(shaft_records())
    original_pipes = {handle: pipe for handle, pipe in pipe_rows}
    original_shafts = {handle: shaft for handle, shaft in shaft_rows}
    final_pipes = {handle: core.validate_pipe(pipe_updates.get(handle, pipe))
                   for handle, pipe in pipe_rows}
    final_shafts = {handle: core.validate_shaft(
        shaft_updates.get(handle, shaft), allow_hidden=True)
                    for handle, shaft in shaft_rows}
    affected_ids = {identity for handle in pipe_updates
                    for identity in (original_pipes[handle]["start_id"],
                                     original_pipes[handle]["end_id"],
                                     final_pipes[handle]["start_id"],
                                     final_pipes[handle]["end_id"])}
    affected_ids.update(final_shafts[handle]["id"] for handle in shaft_updates)
    endpoint_values = {}
    for pipe in final_pipes.values():
        endpoint_values.setdefault(pipe["start_id"], []).append(pipe["start_invert_m"])
        endpoint_values.setdefault(pipe["end_id"], []).append(pipe["end_invert_m"])
    pipes_by_id = {pipe["id"]: pipe for pipe in final_pipes.values()}
    for shaft_handle, shaft in tuple(final_shafts.items()):
        if shaft["id"] not in affected_ids:
            continue
        drops = []
        for drop in shaft.get("drops", ()):
            incoming = pipes_by_id.get(drop["pipe_id"])
            # A confirmed flow reversal can turn the former inlet into an
            # outlet. Such a drop is no longer physically applicable.
            if not incoming or incoming["end_id"] != shaft["id"]:
                continue
            drops.append(dict(
                drop, upper_invert_m=incoming["end_invert_m"]))
        soil_values = list(endpoint_values.get(shaft["id"], ()))
        soil_values.extend(drop["lower_invert_m"] for drop in drops)
        value = dict(shaft, drops=drops)
        if soil_values:
            value["ks_m"] = min(soil_values)
        final_shafts[shaft_handle] = core.validate_shaft(value, allow_hidden=True)
    core.validate_network(tuple(final_pipes.values()), tuple(final_shafts.values()))
    return ({handle: value for handle, value in final_pipes.items()
             if value != original_pipes[handle]},
            {handle: value for handle, value in final_shafts.items()
             if value != original_shafts[handle]})


def _commit_network_updates(pipe_updates, shaft_updates, preferences, undo_name):
    requested_resets = list(dict.fromkeys(tuple(shaft_updates) + tuple(pipe_updates)))
    renamed_ids = set()
    for handle, updated in shaft_updates.items():
        original_data = _live().data_of(handle) or {}
        original = original_data.get("shaft") or {}
        if original.get("name") != updated.get("name"):
            renamed_ids.add(updated["id"])
    # Diameter, construction and cover changes alter every connected pipe trim
    # and the associated labels even when the pipe payload itself is unchanged.
    for updated in shaft_updates.values():
        for pipe_handle, _pipe in _connected_pipes(updated["id"]):
            if pipe_handle not in requested_resets:
                requested_resets.append(pipe_handle)
    # Direction changes alter inlet/outlet text and stub stationing at both
    # endpoint structures even when the shaft's numeric payload stays equal.
    for pipe_handle, updated in pipe_updates.items():
        original_data = _live().data_of(pipe_handle) or {}
        original = original_data.get("pipe") or {}
        for identity in tuple(dict.fromkeys(
                (original.get("start_id"), original.get("end_id"),
                 updated.get("start_id"), updated.get("end_id")))):
            if not identity:
                continue
            shaft_handle = _handle_by_id(core.SHAFT_PREFIX, identity)
            if shaft_handle and shaft_handle not in requested_resets:
                requested_resets.append(shaft_handle)
    # A station may refer to a remote segment of the same holding. Height
    # changes and confirmed flow reversals do not move geometry, so they do
    # not pass through draw_shaft's geometry-move invalidation. Reset every
    # dependent connection explicitly; its draw event then reconstructs the
    # current lower station zero, name and distance from the updated network.
    affected_station_pipe_ids = set()
    for pipe_handle, updated in pipe_updates.items():
        original_data = _live().data_of(pipe_handle) or {}
        original = original_data.get("pipe") or updated
        try:
            _current, _pipe_map, component = _holding_component(original)
            affected_station_pipe_ids.update(component)
        except core.SewerError:
            affected_station_pipe_ids.add(updated["id"])
    for shaft_handle in _station_dependent_shaft_handles(
            affected_station_pipe_ids):
        if shaft_handle not in requested_resets:
            requested_resets.append(shaft_handle)
    if renamed_ids:
        # Holding names may pass through invisible bends and stubs. Redraw the
        # complete connected component after a shaft rename so no upstream
        # segment keeps an obsolete H-<Schachtname> label.
        pipe_rows = tuple(pipe_records())
        component_nodes = set(renamed_ids)
        changed = True
        while changed:
            changed = False
            for pipe_handle, pipe in pipe_rows:
                if pipe["start_id"] in component_nodes or pipe["end_id"] in component_nodes:
                    before = len(component_nodes)
                    component_nodes.update((pipe["start_id"], pipe["end_id"]))
                    changed = changed or len(component_nodes) != before
                    if pipe_handle not in requested_resets:
                        requested_resets.append(pipe_handle)
    requested_resets = tuple(requested_resets)
    pipes, shafts = _prepare_network_updates(pipe_updates, shaft_updates)
    rows = tuple(dict.fromkeys(tuple(shafts) + tuple(pipes)))
    reset_handles = tuple(dict.fromkeys(rows + requested_resets))
    snapshots = {handle: copy.deepcopy(_live().data_of(handle))
                 for handle in reset_handles}
    created_labels = []
    vs.NameUndoEvent(undo_name)
    try:
        for handle, value in shafts.items():
            _live().write_data(handle, dict(
                snapshots[handle], role=_node_role(value), shaft=value,
                preferences=copy.deepcopy(preferences)))
        for handle, value in pipes.items():
            _live().write_data(handle, dict(
                snapshots[handle], pipe=value, preferences=copy.deepcopy(preferences)))
        # Endpoint heights are individual PIO labels.  Reconcile them before
        # resetting the owning shafts so an old drawing is migrated as soon as
        # one of its heights is edited, without creating objects from a PIO
        # reset callback (which is re-entrant in Vectorworks 2026).
        for handle in reset_handles:
            current = _live().data_of(handle)
            if (current and current.get("role") == "sewer_shaft" and
                    current.get("labels")):
                _ensure_connection_height_labels(
                    handle, current, created_labels)
        for handle in reset_handles:
            if handle not in pipes and handle not in shafts:
                _live().write_data(handle, snapshots[handle])
            _reset_checked(handle)
    except Exception:
        for label in reversed(created_labels):
            if label:
                vs.DelObject(label)
        for handle, snapshot in snapshots.items():
            _live().write_data(handle, snapshot)
            vs.ResetObject(handle)
        raise
    vs.ReDrawAll()
    return len(pipes), len(shafts)


def align_shaft_covers_to_site_model(handles=None, model_name="", tin_type=2):
    """Set only selected shaft-cover elevations to a site-model surface.

    All terrain elevations and all resulting shaft mappings are validated
    before the first document write.  This deliberately bypasses the normal
    network-height update path because that path is allowed to derive shaft
    inverts from connected pipes; a cover adjustment must never do so.
    ``handles=None`` processes every visible round/special shaft, while an
    explicit sequence rejects non-shaft or non-cover objects.
    """
    explicit = handles is not None
    source_handles = (handles if handles is not None else
                      (handle for handle, _shaft in shaft_records()))
    requested = tuple(dict.fromkeys(source_handles))
    rows = []
    for handle in requested:
        data = _live().data_of(handle)
        if not is_sewer_data(data) or data.get("role") != "sewer_shaft":
            if explicit:
                raise core.SewerError("Für den DGM-Abgleich nur Kanalschächte wählen.")
            continue
        persisted = core.validate_shaft(data["shaft"], allow_hidden=True)
        current = read_shaft(handle, data)
        if math.dist((persisted["x_m"], persisted["y_m"]),
                     (current["x_m"], current["y_m"])) > 1e-8:
            raise core.SewerError(
                "Ein Schacht besitzt noch eine nicht abgeschlossene Lageänderung. "
                "Zeichnung zuerst aktualisieren; DGM-Abgleich wurde nicht begonnen.")
        shaft = persisted
        if not terrain_rules.supports_terrain_cover(shaft):
            if explicit:
                raise core.SewerError(
                    "Nur sichtbare runde Schächte und Sonderschächte besitzen einen anpassbaren Schachtdeckel.")
            continue
        rows.append((handle, data, shaft))
    if not rows:
        raise core.SewerError("Keine anpassbaren Schachtdeckel gefunden.")

    try:
        elevations, selected_model = site_model.sample_meters(
            tuple((shaft["x_m"], shaft["y_m"]) for _handle, _data, shaft in rows),
            adapter.units_to_meters(), int(tin_type), str(model_name or ""), True)
        planned_shafts = terrain_rules.plan_cover_updates(
            tuple(shaft for _handle, _data, shaft in rows), elevations)
    except (site_model.SiteModelError, terrain_rules.TerrainRuleError) as error:
        raise core.SewerError(str(error)) from error

    shaft_snapshots = {handle: copy.deepcopy(data) for handle, data, _shaft in rows}
    pipe_snapshots = {handle: copy.deepcopy(data) for handle, data in objects("sewer_pipe")}
    vs.NameUndoEvent("PD Schachtdeckel an Geländemodell anpassen")
    try:
        for (handle, data, _old), shaft in zip(rows, planned_shafts):
            _live().write_data(handle, dict(data, shaft=shaft))
        for handle, _data, _shaft in rows:
            vs.ResetObject(handle)

        # A cover-only operation is contractually forbidden from changing a
        # shaft invert or any persisted pipe.  Verify that invariant even
        # after the parametric resets and roll the complete batch back if a
        # later object event ever violates it.
        for (handle, _data, old), planned in zip(rows, planned_shafts):
            persisted = _live().data_of(handle)
            current = core.validate_shaft(persisted["shaft"], allow_hidden=True)
            if abs(current["ks_m"] - old["ks_m"]) > 1e-9 or current != core.validate_shaft(
                    planned, allow_hidden=True):
                raise core.SewerError(
                    "DGM-Abgleich hätte weitere Schachtdaten verändert; Änderung wurde zurückgenommen.")
        if any(_live().data_of(handle) != snapshot
               for handle, snapshot in pipe_snapshots.items()):
            raise core.SewerError(
                "DGM-Abgleich hätte Kanaldaten verändert; Änderung wurde zurückgenommen.")
    except Exception:
        for handle, snapshot in shaft_snapshots.items():
            _live().write_data(handle, snapshot)
            vs.ResetObject(handle)
        for handle, snapshot in pipe_snapshots.items():
            if _live().data_of(handle) != snapshot:
                _live().write_data(handle, snapshot)
                vs.ResetObject(handle)
        raise
    vs.ReDrawAll()
    return {"shafts": len(rows), "model_name": selected_model, "tin_type": int(tin_type)}


def network_component(handle):
    """Return the connected shaft/pipe component containing ``handle``."""
    data = _live().data_of(handle)
    if data and data.get("role") == "sewer_label":
        handle = vs.GetObject(data.get("owner", ""))
        data = _live().data_of(handle)
    if (not is_sewer_data(data) or
            (data["role"] != "sewer_pipe" and data["role"] not in NODE_ROLES)):
        raise core.SewerError("Kein Kanalnetz gewählt.")
    all_pipes = tuple(pipe_records())
    all_shafts = {shaft["id"]: (shaft_handle, shaft) for shaft_handle, shaft in shaft_records()}
    if data["role"] == "sewer_pipe":
        pipe = read_pipe(handle, data)
        pending = [pipe["start_id"], pipe["end_id"]]
    else:
        pending = [read_shaft(handle, data)["id"]]
    identities = set()
    pipe_ids = set()
    while pending:
        identity = pending.pop()
        if identity in identities:
            continue
        identities.add(identity)
        for pipe_handle, pipe in all_pipes:
            if identity not in (pipe["start_id"], pipe["end_id"]):
                continue
            pipe_ids.add(pipe["id"])
            other = pipe["end_id"] if pipe["start_id"] == identity else pipe["start_id"]
            if other not in identities:
                pending.append(other)
    shaft_rows = tuple(all_shafts[identity] for identity in identities if identity in all_shafts)
    pipe_rows = tuple((pipe_handle, pipe) for pipe_handle, pipe in all_pipes if pipe["id"] in pipe_ids)
    return shaft_rows, pipe_rows


def network_components(handles):
    """Return the union of all connected components touched by ``handles``."""
    shaft_rows = {}
    pipe_rows = {}
    for handle in handles:
        component_shafts, component_pipes = network_component(handle)
        for row_handle, value in component_shafts:
            shaft_rows[value["id"]] = (row_handle, value)
        for row_handle, value in component_pipes:
            pipe_rows[value["id"]] = (row_handle, value)
    if not shaft_rows and not pipe_rows:
        raise core.SewerError("Kein Kanalnetz gewählt.")
    return tuple(shaft_rows.values()), tuple(pipe_rows.values())


def edit_network_chain(handles, preferences):
    """Edit several slopes and shaft elevations as one transactional change."""
    targets = tuple(handles) if isinstance(handles, (tuple, list)) else (handles,)
    shaft_rows, pipe_rows = network_components(targets)
    by_key = ({("shaft", value["id"]): row_handle for row_handle, value in shaft_rows} |
              {("pipe", value["id"]): row_handle for row_handle, value in pipe_rows})

    def highlight(selections):
        vs.DSelectAll()
        for role, identity in selections:
            target = by_key.get((role, identity))
            if target:
                vs.SetSelect(target)
        vs.ReDrawAll()
    try:
        choice = sewer_ui.network_chain_dialog(
            tuple(value for _handle, value in shaft_rows),
            tuple(value for _handle, value in pipe_rows), highlight)
    finally:
        vs.DSelectAll()
        for target in targets:
            if target:
                vs.SetSelect(target)
        vs.ReDrawAll()
    if choice is None:
        return False
    changed_shafts = {value["id"]: value for value in choice[0]}
    changed_pipes = {value["id"]: value for value in choice[1]}
    core.validate_network(tuple(changed_pipes.values()), tuple(changed_shafts.values()))
    rows = list(shaft_rows) + list(pipe_rows)
    snapshots = {row_handle: copy.deepcopy(_live().data_of(row_handle)) for row_handle, _value in rows}
    vs.NameUndoEvent("PD Kanalkette bearbeiten")
    try:
        for row_handle, old in shaft_rows:
            _live().write_data(row_handle, dict(snapshots[row_handle],
                                                shaft=changed_shafts[old["id"]],
                                                preferences=copy.deepcopy(preferences)))
        for row_handle, old in pipe_rows:
            _live().write_data(row_handle, dict(snapshots[row_handle],
                                                pipe=changed_pipes[old["id"]],
                                                preferences=copy.deepcopy(preferences)))
        validate_document(preferences)
        for row_handle, _old in rows:
            vs.ResetObject(row_handle)
    except Exception:
        for row_handle, data in snapshots.items():
            _live().write_data(row_handle, data)
            vs.ResetObject(row_handle)
        raise
    vs.ReDrawAll()
    return True


def _shaft_inlet_dialog_rows(shaft, connected):
    """Describe each inlet with its stable pipe id and graphical Z tag."""
    current_by_id = {
        pipe["id"]: pipe for _pipe_handle, pipe in connected
        if pipe["end_id"] == shaft["id"]}
    rows = []
    seen = set()
    for view in shaft_connection_views(shaft):
        pipe = current_by_id.get(view["pipe_id"])
        if view["role"] != "in" or pipe is None:
            continue
        rows.append({
            "pipe_id": pipe["id"],
            "connection_id": view["connection_id"],
            "tag": view["tag"],
            "pipe_name": view.get("pipe_name") or pipe.get("name", ""),
            "invert_m": pipe["end_invert_m"],
        })
        seen.add(pipe["id"])
    # A local fallback keeps editing possible if a connection view from an
    # older file lacks display metadata. The pipe id remains the update key.
    for pipe_id in sorted(set(current_by_id) - seen):
        pipe = current_by_id[pipe_id]
        rows.append({
            "pipe_id": pipe_id,
            "connection_id": "%s:end" % pipe_id,
            "tag": "Z%d" % (len(rows) + 1),
            "pipe_name": pipe.get("name", ""),
            "invert_m": pipe["end_invert_m"],
        })
    return tuple(rows)


def _chosen_inlet_height(choice, pipe):
    """Return one selected inlet height without changing sibling inlets."""
    values = choice.get("inlet_inverts_m")
    if isinstance(values, dict) and pipe["id"] in values:
        return core.number(values[pipe["id"]], "Zulaufsohle")
    if choice.get("inlet_changed", True):
        return core.number(choice["inlet_invert_m"], "Zulaufsohle")
    return pipe["end_invert_m"]


def edit(handle, preferences):
    data = _live().data_of(handle)
    if data and data["role"] == "sewer_label":
        handle = vs.GetObject(data["owner"])
        data = _live().data_of(handle)
    if not is_sewer_data(data):
        raise core.SewerError("Kein Kanalobjekt gewählt.")
    if data["role"] in NODE_ROLES:
        node = read_shaft(handle, data)
        if node.get("structure_type") == "stub":
            return edit_stub_alignment(handle, preferences)
        if node.get("structure_type") in ("floor_drain", "house"):
            return edit_terminal(handle, preferences)
    if data["role"] == "sewer_pipe":
        original = read_pipe(handle, data)
        initial = dict(original, calculation_mode="end", calculation_value=original["end_invert_m"],
                       cover_height_m=original["start_invert_m"] + preferences["cover_offset_m"],
                       shaft_diameter_m=preferences["shaft_diameter_m"], shaft_mode="all")
        values = sewer_ui.pipe_properties_dialog(preferences, initial)
        if values is None:
            return False
        # Preserve the physically entered endpoint elevations long enough to
        # ask before an implied direction reversal.  Final validation happens
        # in _confirmed_pipe_directions below.
        updated = core.update_pipe(
            original, original["length_m"], values, allow_flow_reversal=True)
        if values.get("reverse_flow"):
            updated["start_id"], updated["end_id"] = updated["end_id"], updated["start_id"]
            updated = core.validate_pipe(updated)
        pipe_updates = _confirmed_pipe_directions({handle: updated})
        if pipe_updates is None:
            return False
        updated = pipe_updates[handle]
        delta = updated["end_invert_m"] - original["end_invert_m"]
        if (updated["end_id"] == original["end_id"] and abs(delta) > 1e-9):
            following = _downstream_pipes(updated["end_id"], (updated["id"],))
            if following:
                propagation = sewer_ui.downstream_height_dialog(delta, len(following))
                if propagation is None:
                    return False
                pipe_updates.update(_downstream_height_changes(
                    following, updated["end_id"], delta, propagation))
        if len(pipe_updates) > 1:
            pipe_updates = _confirmed_pipe_directions(pipe_updates)
            if pipe_updates is None:
                return False
        # Layout and wrapping describe the single holding label, not merely
        # the geometric segment that happened to be clicked. Propagate both
        # fields through invisible bends up to the next real terminal. This
        # guarantees one consistently one- or two-line label for floor drains
        # and house connections even when their route contains many bends.
        _current, _pipe_map, holding_ids = _holding_component(original)
        for related_handle, related_pipe in pipe_records():
            if related_pipe["id"] not in holding_ids:
                continue
            base = pipe_updates.get(related_handle, related_pipe)
            pipe_updates[related_handle] = core.validate_pipe(dict(
                base, label_layout=updated["label_layout"],
                label_width_m=updated["label_width_m"],
                label_rotation_deg=updated["label_rotation_deg"]))
        _commit_network_updates(pipe_updates, {}, preferences, "PD Kanalstrecke bearbeiten")
        return True
    if data["role"] in NODE_ROLES:
        original = read_shaft(handle, data)
        connected = _connected_pipes(original["id"])
        inlet_rows = _shaft_inlet_dialog_rows(original, connected)
        outgoing = tuple(pipe["start_invert_m"] for _pipe_handle, pipe in connected
                         if pipe["start_id"] == original["id"])
        choice = sewer_ui.shaft_dialog(original, preferences, inlet_rows, outgoing)
        if choice is None:
            return False
        updated = choice["shaft"]
        _unique_shaft_name(updated["name"], original["id"])
        changed_pipes = {}
        old_outlet = min(outgoing) if outgoing else choice["outlet_invert_m"]
        outlet_changed = choice.get("outlet_changed", True)
        delta = choice["outlet_invert_m"] - old_outlet if outlet_changed else 0.0
        following = _downstream_pipes(original["id"]) if abs(delta) > 1e-9 else ()
        propagation = "slope"
        if following:
            propagation = sewer_ui.downstream_height_dialog(delta, len(following))
            if propagation is None:
                return False
            if propagation == "shift" and any(
                    abs(value - old_outlet) > 1e-6 for value in outgoing):
                raise core.SewerError(
                    "Die vorhandenen Ablaufsohlen sind unterschiedlich. "
                    "Bitte 'Gefälle der nächsten Haltung ändern' wählen oder die Haltungen einzeln bearbeiten.")
            changed_pipes.update(_downstream_height_changes(
                following, original["id"], delta, propagation))
        for pipe_handle, pipe in connected:
            changed = dict(changed_pipes.get(pipe_handle, pipe))
            if pipe["end_id"] == original["id"]:
                changed["end_invert_m"] = _chosen_inlet_height(choice, pipe)
            if outlet_changed and pipe["start_id"] == original["id"]:
                changed["start_invert_m"] = choice["outlet_invert_m"]
            if changed != pipe:
                changed_pipes[pipe_handle] = changed
        changed_pipes = _confirmed_pipe_directions(changed_pipes)
        if changed_pipes is None:
            return False
        _commit_network_updates(
            changed_pipes, {handle: updated}, preferences, "PD Kanalschacht bearbeiten")
        return True
    return False


def edit_shafts(handles, preferences):
    """Stage full individual dialogs for several shafts and commit once.

    Every selected shaft keeps its own name, heights and construction data.
    The user receives the same complete editor as for a single shaft, once per
    selected shaft.  Nothing is written when any dialog is cancelled or when
    the prospective network is invalid.
    """
    requested = tuple(dict.fromkeys(tuple(handles or ())))
    if len(requested) < 2:
        raise core.SewerError("Für die Mehrfachbearbeitung mindestens zwei Schächte markieren.")
    rows = []
    for handle in requested:
        data = _live().data_of(handle)
        if not is_sewer_data(data) or data.get("role") != "sewer_shaft":
            raise core.SewerError("Für die Mehrfachbearbeitung ausschließlich Kanalschächte markieren.")
        shaft = read_shaft(handle, data)
        if (not shaft.get("visible", True) or
                shaft.get("structure_type", "round") not in ("round", "special")):
            raise core.SewerError("Nur sichtbare runde Schächte und Sonderschächte gemeinsam bearbeiten.")
        rows.append((handle, shaft))

    pipe_rows = tuple(pipe_records())
    staged_pipes = {}
    shaft_updates = {}
    for handle, original in rows:
        connected = []
        for pipe_handle, persisted in pipe_rows:
            pipe = staged_pipes.get(pipe_handle, persisted)
            if original["id"] in (pipe["start_id"], pipe["end_id"]):
                connected.append((pipe_handle, pipe))
        inlet_rows = _shaft_inlet_dialog_rows(original, connected)
        outgoing = tuple(pipe["start_invert_m"] for _pipe_handle, pipe in connected
                         if pipe["start_id"] == original["id"])
        choice = sewer_ui.shaft_dialog(original, preferences, inlet_rows, outgoing)
        if choice is None:
            return False
        shaft_updates[handle] = choice["shaft"]
        outlet_changed = choice.get("outlet_changed", True)
        old_outlet = min(outgoing) if outgoing else choice["outlet_invert_m"]
        delta = choice["outlet_invert_m"] - old_outlet if outlet_changed else 0.0
        if abs(delta) > 1e-9:
            following = tuple(
                (pipe_handle, staged_pipes.get(pipe_handle, pipe))
                for pipe_handle, pipe in _downstream_pipes(original["id"]))
            if following:
                propagation = sewer_ui.downstream_height_dialog(delta, len(following))
                if propagation is None:
                    return False
                if propagation == "shift" and any(
                        abs(value - old_outlet) > 1e-6 for value in outgoing):
                    raise core.SewerError(
                        "Die vorhandenen Ablaufsohlen sind unterschiedlich. "
                        "Bitte 'Gefälle der nächsten Haltung ändern' wählen.")
                staged_pipes.update(_downstream_height_changes(
                    following, original["id"], delta, propagation))
        for pipe_handle, pipe in connected:
            changed = copy.deepcopy(staged_pipes.get(pipe_handle, pipe))
            if pipe["end_id"] == original["id"]:
                changed["end_invert_m"] = _chosen_inlet_height(choice, pipe)
            if outlet_changed and pipe["start_id"] == original["id"]:
                changed["start_invert_m"] = choice["outlet_invert_m"]
            if changed != pipe:
                staged_pipes[pipe_handle] = changed

    # Validate names and every other shaft/pipe invariant before prompting for
    # a possible flow reversal and before touching the document.
    prospective_shafts = [shaft_updates.get(handle, shaft)
                          for handle, shaft in shaft_records()]
    prospective_pipes = [staged_pipes.get(handle, pipe)
                         for handle, pipe in pipe_rows]
    directions = {}
    for pipe_handle, pipe in zip((row[0] for row in pipe_rows), prospective_pipes):
        if pipe_handle in staged_pipes:
            directions[pipe_handle] = pipe
    directions = _confirmed_pipe_directions(directions)
    if directions is None:
        return False
    final_pipes = [directions.get(handle, pipe)
                   for handle, pipe in pipe_rows]
    core.validate_network(final_pipes, prospective_shafts)
    _commit_network_updates(
        directions, shaft_updates, preferences, "PD Mehrere Kanalschächte bearbeiten")
    return True


def batch_edit(handles, preferences):
    pipes = [(handle, data, read_pipe(handle, data)) for handle, data in handles
             if data["role"] == "sewer_pipe"]
    if not pipes:
        raise core.SewerError("Für die Sammeländerung Kanalstrecken markieren.")
    changes = sewer_ui.batch_pipe_dialog(preferences)
    if changes is None or not changes:
        return 0
    snapshots = [(handle, copy.deepcopy(data)) for handle, data, _pipe in pipes]
    try:
        for handle, data, pipe in pipes:
            pipe.update(copy.deepcopy(changes))
            pipe = core.validate_pipe(pipe)
            _live().write_data(handle, dict(data, pipe=pipe, preferences=copy.deepcopy(preferences)))
            vs.ResetObject(handle)
    except Exception:
        for handle, data in snapshots:
            _live().write_data(handle, data)
            vs.ResetObject(handle)
        raise
    return len(pipes)


def _preference_targets(selected, scope):
    """Resolve an explicit preference-update scope without changing data."""
    scope = str(scope or "save")
    if scope not in ("selection", "systems", "drawing"):
        raise core.SewerError("Ungültiger Aktualisierungsumfang der Kanaleinstellungen.")
    rows = tuple((handle, data) for handle, data in objects()
                 if (data.get("role") in NODE_ROLES or
                     data.get("role") in ("sewer_pipe", "sewer_rigole")))
    if scope == "drawing":
        return rows
    selected_handles = {handle for handle, _data in tuple(selected or ())}
    chosen = tuple(row for row in rows if row[0] in selected_handles)
    if not chosen:
        raise core.SewerError(
            "Für diese Aktualisierung zuerst mindestens eine Haltung oder einen Schacht markieren.")
    if scope == "selection":
        return chosen

    # A system is a topologically connected component.  This remains correct
    # when older files used only the channel kind (RW/SW/MW) as network_id.
    node_ids = set()
    for _handle, data in chosen:
        if data["role"] in NODE_ROLES:
            node_ids.add(data["shaft"]["id"])
        elif data["role"] == "sewer_pipe":
            node_ids.update((data["pipe"]["start_id"], data["pipe"]["end_id"]))
        else:
            node_ids.update(connection["node_id"]
                            for connection in data["rigole"].get("connections", ()))
    changed = True
    while changed:
        changed = False
        for _handle, data in rows:
            if data["role"] != "sewer_pipe":
                continue
            pipe = data["pipe"]
            if pipe["start_id"] in node_ids or pipe["end_id"] in node_ids:
                before = len(node_ids)
                node_ids.update((pipe["start_id"], pipe["end_id"]))
                changed = changed or len(node_ids) != before
    return tuple(
        (handle, data) for handle, data in rows
        if ((data["role"] == "sewer_pipe" and
             data["pipe"]["start_id"] in node_ids and
             data["pipe"]["end_id"] in node_ids) or
            (data["role"] in NODE_ROLES and data["shaft"]["id"] in node_ids) or
            (data["role"] == "sewer_rigole" and any(
                connection["node_id"] in node_ids
                for connection in data["rigole"].get("connections", ())))))


def _data_with_preferences(data, preferences):
    """Apply only global drawing standards; preserve engineering object data."""
    updated = copy.deepcopy(data)
    updated["preferences"] = copy.deepcopy(preferences)
    if updated["role"] == "sewer_pipe":
        pipe = copy.deepcopy(updated["pipe"])
        pipe.update({
            "fillet_radius_m": preferences["fillet_radius_m"],
            "flow_arrow_scale": preferences["flow_arrow_scale"],
            "graphics_mode": preferences["graphics_mode"],
            "line_type": preferences["single_line_type"],
            "axis_line_type": preferences["axis_line_type"],
        })
        updated["pipe"] = core.validate_pipe(pipe)
    elif updated["role"] in NODE_ROLES:
        shaft = copy.deepcopy(updated["shaft"])
        if (shaft.get("visible", True) and
                shaft.get("structure_type", "round") in ("round", "special") and
                float(shaft.get("diameter_m", 0.0)) > 0.0):
            shaft.update({
                "construction_material": preferences["shaft_construction_material"],
                "wall_thickness_m": preferences["shaft_wall_thickness_m"],
                "cover_diameter_m": preferences["shaft_cover_diameter_m"],
                "cover_symbol": preferences["shaft_cover_symbol"],
                "cover_placement": preferences["shaft_cover_placement"],
                "cover_rotation_deg": preferences["shaft_cover_rotation_deg"],
            })
        elif shaft.get("structure_type") == "floor_drain":
            shaft.update({
                "terminal_label_visible": preferences["floor_drain_label_visible"],
                "terminal_label_point_size": preferences["floor_drain_label_point_size"],
            })
        updated["shaft"] = core.validate_shaft(shaft, allow_hidden=True)
        updated["role"] = _node_role(updated["shaft"])
    elif updated["role"] == "sewer_rigole":
        updated["rigole"] = core.validate_rigole(updated["rigole"])
    return updated


def apply_preferences(preferences, selected=None, scope="drawing"):
    """Transactionally redraw a selection, connected systems or the document."""
    preferences = sewer_settings.validate(preferences)
    targets = _preference_targets(selected, scope)
    if not targets:
        raise core.SewerError("Keine Kanalobjekte zum Aktualisieren gefunden.")
    ensure_classes(preferences)
    snapshots = {handle: copy.deepcopy(data) for handle, data in targets}
    planned = {handle: _data_with_preferences(data, preferences)
               for handle, data in targets}
    affected_nodes = set()
    for data in planned.values():
        if data["role"] in NODE_ROLES:
            affected_nodes.add(data["shaft"]["id"])
        elif data["role"] == "sewer_pipe":
            affected_nodes.update((data["pipe"]["start_id"], data["pipe"]["end_id"]))
        else:
            affected_nodes.update(connection["node_id"]
                                  for connection in data["rigole"].get("connections", ()))
    redraw = set(planned)
    created_labels = []
    # Pipe trims and hidden junction fillets depend on their neighbouring
    # object.  Redraw those dependants without applying their standards.
    for handle, data in objects():
        if data.get("role") == "sewer_pipe":
            pipe = data["pipe"]
            if pipe["start_id"] in affected_nodes or pipe["end_id"] in affected_nodes:
                redraw.add(handle)
        elif (data.get("role") in NODE_ROLES and
              data["shaft"]["id"] in affected_nodes):
            redraw.add(handle)
    rollback_snapshots = dict(snapshots)
    for handle in redraw:
        rollback_snapshots.setdefault(
            handle, copy.deepcopy(_live().data_of(handle)))
    vs.NameUndoEvent("PD Kanaleinstellungen anwenden")
    try:
        for handle, data in planned.items():
            _live().write_data(handle, data)
        for handle in redraw:
            current = _live().data_of(handle)
            if (current and current.get("role") == "sewer_shaft" and
                    current.get("labels")):
                _ensure_connection_height_labels(
                    handle, current, created_labels)
        for handle in redraw:
            vs.ResetObject(handle)
    except Exception:
        for label in reversed(created_labels):
            if label:
                vs.DelObject(label)
        for handle, data in rollback_snapshots.items():
            _live().write_data(handle, data)
            vs.ResetObject(handle)
        raise
    vs.ReDrawAll()
    return len(planned)


def apply_standard_colors(preferences):
    count = 0
    for handle, data in objects():
        if data["role"] != "sewer_pipe" and data["role"] not in NODE_ROLES:
            continue
        # Store the current system standards on every managed object.  Any
        # explicit pipe or shaft overrides remain in their payload and thus
        # continue to take precedence during the redraw.
        _live().write_data(handle, dict(data, preferences=copy.deepcopy(preferences)))
        vs.ResetObject(handle)
        _reset_labels(data)
        count += 1
    return count


def validate_document(preferences=None):
    preferences = sewer_settings.validate(preferences or sewer_settings.load())
    pipes = tuple(pipe for _handle, pipe in pipe_records())
    shafts = tuple(shaft for _handle, shaft in shaft_records())
    rigoles = tuple(rigole for _handle, rigole in rigole_records())
    core.validate_network(pipes, shafts)
    errors = []
    for pipe in pipes:
        if pipe["dn_mm"] not in preferences["dns"]:
            errors.append("DN %d ist nicht in der aktuellen Auswahlliste." % pipe["dn_mm"])
        if pipe["material"] not in preferences["materials"]:
            errors.append("Material %s ist nicht in der aktuellen Auswahlliste." % pipe["material"])
    for shaft in shafts:
        connected = []
        for pipe in pipes:
            if pipe["start_id"] == shaft["id"]:
                connected.append(pipe["start_invert_m"])
            if pipe["end_id"] == shaft["id"]:
                connected.append(pipe["end_invert_m"])
        if connected and abs(shaft["ks_m"] - min(connected)) > 0.001:
            errors.append("Schacht %s: KS stimmt nicht mit der tiefsten Rohrsohle überein." %
                          (shaft["name"] or shaft["id"]))
    shaft_index = {shaft["id"]: shaft for shaft in shafts}
    for rigole in rigoles:
        for connection in rigole.get("connections", ()):
            node = shaft_index.get(connection["node_id"])
            if not node:
                errors.append("Rigole %s: Anschlussknoten fehlt." % rigole["name"])
                continue
            expected = core.rigole_connection_xy(
                rigole, connection["side"], connection["fraction"])
            if math.dist((node["x_m"], node["y_m"]), expected) > 0.001:
                errors.append("Rigole %s: Anschlussknoten liegt nicht auf der Rigolenkante." %
                              rigole["name"])
            if abs(node["ks_m"] - connection["invert_m"]) > 0.001:
                errors.append("Rigole %s: Anschlusshöhe und Knoten-Sohlhöhe unterscheiden sich." %
                              rigole["name"])
    if errors:
        raise core.SewerError("\n".join(sorted(set(errors))))
    fittings = [value for value in shafts
                if value.get("structure_type") == "stub"]
    floor_drains = [value for value in shafts
                    if value.get("structure_type") == "floor_drain"]
    house_connections = [value for value in shafts
                         if value.get("structure_type") == "house"]
    visible_shafts = [value for value in shafts
                      if value.get("visible") and
                      value.get("structure_type") in ("round", "special")]
    junctions = [value for value in shafts
                 if value.get("structure_type") == "junction"]
    return {"pipes": len(pipes), "shafts": len(visible_shafts),
            "fittings": len(fittings), "nodes": len(junctions),
            "floor_drains": len(floor_drains),
            "house_connections": len(house_connections),
            "rigoles": len(rigoles), "errors": ()}


def _clone_translation_m(handle, role, payload):
    factor = adapter.units_to_meters()
    location = adapter.symbol_location_2d(handle, (0.0, 0.0))
    current = location[0] * factor, location[1] * factor
    if role in NODE_ROLES + ("sewer_rigole",):
        return current[0] - payload["x_m"], current[1] - payload["y_m"]
    return current


def _repair_shaft_clone(handle, data, translation=None):
    payload = copy.deepcopy(data["shaft"])
    old_id = payload.get("clone_origin_id") or payload["id"]
    translation = translation or _clone_translation_m(handle, "sewer_shaft", payload)
    payload["id"] = str(uuid.uuid4())
    payload["clone_origin_id"] = str(old_id)
    payload["clone_translation_m"] = [float(translation[0]), float(translation[1])]
    payload["x_m"] = float(payload["x_m"]) + float(translation[0])
    payload["y_m"] = float(payload["y_m"]) + float(translation[1])
    if payload["visible"]:
        prefix = {"floor_drain": "ABL", "house": "HA"}.get(
            payload.get("structure_type"), payload["kind"])
        next_number = 1
        pattern = re.compile(r"%s\.(\d+)$" % re.escape(prefix), re.IGNORECASE)
        for _peer, peer_data in objects():
            if peer_data.get("role") not in NODE_ROLES:
                continue
            peer = peer_data.get("shaft") or {}
            match = pattern.fullmatch(str(peer.get("name") or ""))
            if match:
                next_number = max(next_number, int(match.group(1)) + 1)
        payload["name"] = "%s.%03d" % (prefix, next_number)
    changed = dict(data, shaft=payload, labels=[])
    vs.SetName(handle, core.SHAFT_PREFIX + payload["id"])
    _live().write_data(handle, changed)
    _retarget_cloned_references(translation)
    created = []
    ensure_label(handle, changed, created)
    for label in created:
        vs.ResetObject(label)
    return _live().data_of(handle)


def _same_clone_translation(payload, translation, tolerance=1e-5):
    stored = payload.get("clone_translation_m")
    if not isinstance(stored, (tuple, list)) or len(stored) < 2:
        return False
    try:
        return math.dist(tuple(float(value) for value in stored[:2]), translation) <= tolerance
    except (TypeError, ValueError):
        return False


def _retarget_cloned_references(translation):
    """Rewrite every resolvable copied-network reference for one translation."""
    rows = tuple(objects())
    shaft_map, pipe_map, shaft_names = {}, {}, {}
    for _handle, row in rows:
        payload = row.get("shaft") or row.get("pipe") or {}
        if not _same_clone_translation(payload, translation):
            continue
        old_id = str(payload.get("clone_origin_id") or "")
        new_id = str(payload.get("id") or "")
        if not old_id or not new_id:
            continue
        if row.get("role") in NODE_ROLES:
            shaft_map[old_id] = new_id
            shaft_names[new_id] = str(payload.get("name") or "")
        elif row.get("role") == "sewer_pipe":
            pipe_map[old_id] = new_id

    def map_station(value):
        if not isinstance(value, dict):
            return value
        result = copy.deepcopy(value)
        for key in ("main_start_id", "main_end_id", "station_zero_id"):
            if result.get(key) in shaft_map:
                result[key] = shaft_map[result[key]]
        for key in ("main_pipe_ids", "station_pipe_ids"):
            if isinstance(result.get(key), (tuple, list)):
                result[key] = [pipe_map.get(identity, identity)
                               for identity in result[key]]
        if result.get("station_zero_id") in shaft_names:
            result["station_zero_name"] = shaft_names[result["station_zero_id"]]
        return result

    for handle, row in rows:
        payload_key = "shaft" if row.get("role") in NODE_ROLES else "pipe"
        payload = copy.deepcopy(row.get(payload_key) or {})
        if not _same_clone_translation(payload, translation):
            continue
        before = copy.deepcopy(payload)
        if payload_key == "pipe":
            for key in ("start_id", "end_id"):
                if payload.get(key) in shaft_map:
                    payload[key] = shaft_map[payload[key]]
        else:
            payload["stub"] = map_station(payload.get("stub"))
            payload["connection_station"] = map_station(
                payload.get("connection_station"))
            if isinstance(payload.get("drops"), list):
                payload["drops"] = [dict(
                    drop, pipe_id=pipe_map.get(drop.get("pipe_id"), drop.get("pipe_id")))
                    if isinstance(drop, dict) else drop for drop in payload["drops"]]
        if payload != before:
            _live().write_data(handle, dict(row, **{payload_key: payload}))


def _cloned_endpoint_id(old_id, translation):
    tolerance = 1e-5
    pending = []
    for shaft_handle, shaft_data in objects():
        if shaft_data.get("role") not in NODE_ROLES:
            continue
        payload = shaft_data.get("shaft") or {}
        stored_translation = payload.get("clone_translation_m")
        if (payload.get("clone_origin_id") == old_id and
                isinstance(stored_translation, (tuple, list)) and
                len(stored_translation) >= 2 and
                math.dist(tuple(float(value) for value in stored_translation[:2]),
                          translation) <= tolerance):
            return payload["id"]
        if payload.get("id") == old_id and _name(shaft_handle) != core.SHAFT_PREFIX + old_id:
            try:
                candidate_translation = _clone_translation_m(
                    shaft_handle, "sewer_shaft", payload)
            except core.SewerError:
                continue
            if math.dist(candidate_translation, translation) <= tolerance:
                pending.append((shaft_handle, shaft_data, candidate_translation))
    if len(pending) == 1:
        repaired = _repair_shaft_clone(*pending[0])
        return repaired["shaft"]["id"]
    if len(pending) > 1:
        raise core.SewerError(
            "Kopierte Kanalanlage ist nicht eindeutig. Bitte Kopieren rückgängig machen und erneut einfügen.")
    return None


def _repair_duplicate(handle, data):
    payload_keys = {"sewer_shaft": "shaft", "sewer_fitting": "shaft",
                    "sewer_floor_drain": "shaft",
                    "sewer_house_connection": "shaft",
                    "sewer_pipe": "pipe",
                    "sewer_rigole": "rigole"}
    prefixes = {"sewer_shaft": core.SHAFT_PREFIX,
                "sewer_fitting": core.SHAFT_PREFIX,
                "sewer_floor_drain": core.SHAFT_PREFIX,
                "sewer_house_connection": core.SHAFT_PREFIX,
                "sewer_pipe": core.PIPE_PREFIX,
                "sewer_rigole": core.RIGOLE_PREFIX}
    payload_key = payload_keys[data["role"]]
    payload = copy.deepcopy(data[payload_key])
    if data["role"] in NODE_ROLES:
        desired_role = _node_role(payload)
        legacy_floor_name = re.fullmatch(
            r"BA\.(\d+)", str(payload.get("name") or ""), re.IGNORECASE)
        if legacy_floor_name:
            requested_name = "ABL.%03d" % int(legacy_floor_name.group(1))
            names = _existing_names() - {payload.get("name")}
            payload["name"] = (requested_name if requested_name not in names
                               else _next_named_number("ABL"))
        if data["role"] != desired_role or legacy_floor_name:
            # Migrate legacy drawings lazily and transaction-free during the
            # object's normal reset. Identity and geometry stay unchanged;
            # only the semantic role/name becomes explicit.
            data = dict(data, role=desired_role, shaft=payload)
            _live().write_data(handle, data)
    prefix = prefixes[data["role"]]
    expected = prefix + payload["id"]
    if _name(handle) == expected:
        return data
    if not vs.GetObject(expected):
        vs.SetName(handle, expected)
        return data
    if data["role"] in NODE_ROLES:
        return _repair_shaft_clone(handle, data)
    if data["role"] == "sewer_rigole":
        factor = adapter.units_to_meters()
        location = adapter.symbol_location_2d(
            handle, (payload["x_m"] / factor, payload["y_m"] / factor))
        payload.update(
            id=str(uuid.uuid4()), name=_next_rigole_name(),
            x_m=float(location[0]) * factor, y_m=float(location[1]) * factor,
            connections=[])
        payload = core.validate_rigole(payload)
        data = dict(data, rigole=payload, labels=[])
        vs.SetName(handle, core.RIGOLE_PREFIX + payload["id"])
        _live().write_data(handle, data)
        created = []
        ensure_label(handle, data, created)
        for label in created:
            vs.ResetObject(label)
        return _live().data_of(handle)
    translation = _clone_translation_m(handle, "sewer_pipe", payload)
    start_id = _cloned_endpoint_id(payload["start_id"], translation)
    end_id = _cloned_endpoint_id(payload["end_id"], translation)
    if not start_id or not end_id:
        raise core.SewerError(
            "Eine kopierte Haltung kann nicht mit den Originalschächten verbunden werden. "
            "Bitte die vollständige Anlage einschließlich beider Schächte kopieren.")
    payload["clone_origin_id"] = payload["id"]
    payload["clone_translation_m"] = [float(translation[0]), float(translation[1])]
    payload["id"] = str(uuid.uuid4())
    payload["start_id"], payload["end_id"] = start_id, end_id
    data = dict(data, **{payload_key: payload}, labels=[])
    vs.SetName(handle, prefix + payload["id"])
    _live().write_data(handle, data)
    _retarget_cloned_references(translation)
    created = []
    ensure_label(handle, data, created)
    for label in created:
        vs.ResetObject(label)
    return _live().data_of(handle)


def reset():
    ok, plugin, handle, _record, _wall = vs.GetCustomObjectInfo()
    if not ok or plugin != _live().PLUGIN or not handle:
        return
    data = _live().data_of(handle)
    if not is_sewer_data(data):
        return
    vs.SetParameterVisibility(handle, "Daten", False)
    vs.EnableParameter(handle, "Nummer", False)
    vs.EnableParameter(handle, "Hoehe_m", False)
    try:
        if data["role"] == "sewer_label":
            draw_label(handle, data)
            _record_render_result(handle, RENDER_OK)
            return
        data = _repair_duplicate(handle, data)
        if data["role"] == "sewer_pipe":
            # Reset also migrates holdings saved by older releases from the
            # unsafe shaft->pipe reset relationship to the deletion-safe graph.
            if isinstance(data.get("pipe"), dict):
                _sync_pipe_associations(handle, core.validate_pipe(data["pipe"]))
            draw_pipe(handle, data)
        elif data["role"] in NODE_ROLES:
            draw_shaft(handle, data)
        elif data["role"] == "sewer_rigole":
            rigole = read_rigole(handle, data)
            valid_connections = []
            for connection in rigole.get("connections", ()):
                junction = _handle_by_id(core.SHAFT_PREFIX, connection["node_id"])
                if not junction:
                    continue
                _sync_rigole_junction_association(handle, junction)
                valid_connections.append(connection)
            if len(valid_connections) != len(rigole.get("connections", ())):
                rigole = core.validate_rigole(dict(
                    rigole, connections=valid_connections))
                data = dict(data, rigole=rigole)
                _live().write_data(handle, data)
            draw_rigole(handle, data)
        _record_render_result(handle, RENDER_OK)
    except Exception as error:
        _record_render_result(handle, RENDER_ERROR, error)
        vs.TextOrigin((0.0, 0.0))
        vs.CreateText("KANAL PRÜFEN: " + str(error))
        adapter.alert("Kanalanlage konnte nicht neu aufgebaut werden: %s" % error)
