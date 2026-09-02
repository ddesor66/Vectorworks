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


ROLES = ("sewer_pipe", "sewer_shaft", "sewer_label", "sewer_fitting")
TEXT_COLOR = (0, 0, 0)


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
    payload = data.get("pipe") or data.get("shaft") or {}
    return _rgb(payload.get("color_override") or preferences["colors"][payload["kind"]])


def class_name(value, preferences, suffix=""):
    if isinstance(value, dict) and "dn_mm" in value:
        return core.pipe_class_name(preferences["class_prefix"], value, suffix)
    kind = value.get("kind") if isinstance(value, dict) else value
    return "%s-%s-Schacht%s" % (preferences["class_prefix"], kind, suffix)


def axis_class_name(pipe, preferences):
    return core.pipe_class_name(preferences["class_prefix"], pipe, "-Achse")


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


def ensure_classes(preferences):
    active = str(vs.ActiveClass() or "")
    try:
        for kind in core.KINDS:
            color = _rgb(preferences["colors"][kind])
            for suffix in ("", "_3D"):
                name = class_name(kind, preferences, suffix)
                _ensure_class(name, color)
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
    _ensure_class(class_name(pipe, preferences), color)
    _ensure_class(class_name(pipe, preferences, "_3D"), color)
    _ensure_class(axis_class_name(pipe, preferences), TEXT_COLOR, fill=False,
                  line_type=preferences["axis_line_type"])


def _name(handle):
    return str(vs.GetName(handle) or "")


def _handle_by_id(prefix, identity):
    handle = vs.GetObject(prefix + str(identity))
    return handle if handle and int(vs.GetTypeN(handle) or 0) == 86 else None


def read_shaft(handle, data=None):
    data = data or _live().data_of(handle)
    if not is_sewer_data(data) or data["role"] != "sewer_shaft":
        raise core.SewerError("Kanalschacht konnte nicht gelesen werden.")
    shaft = core.validate_shaft(data["shaft"], allow_hidden=True)
    if _name(handle) != core.SHAFT_PREFIX + shaft["id"]:
        raise core.SewerError("Schachtidentität wurde geändert oder kopiert.")
    factor = adapter.units_to_meters()
    location = vs.GetSymLoc(handle)
    shaft["x_m"], shaft["y_m"] = float(location[0]) * factor, float(location[1]) * factor
    return core.validate_shaft(shaft, allow_hidden=True)


def shaft_records():
    return tuple((handle, read_shaft(handle, data))
                 for handle, data in objects("sewer_shaft"))


def _endpoints(pipe):
    start = _handle_by_id(core.SHAFT_PREFIX, pipe["start_id"])
    end = _handle_by_id(core.SHAFT_PREFIX, pipe["end_id"])
    if not start or not end:
        raise core.SewerError("Eine Kanalstrecke besitzt ein gelöschtes oder nicht verbundenes Ende.")
    return (start, read_shaft(start)), (end, read_shaft(end))


def read_pipe(handle, data=None):
    data = data or _live().data_of(handle)
    if not is_sewer_data(data) or data["role"] != "sewer_pipe":
        raise core.SewerError("Kanalstrecke konnte nicht gelesen werden.")
    pipe = core.validate_pipe(data["pipe"])
    if _name(handle) != core.PIPE_PREFIX + pipe["id"]:
        raise core.SewerError("Rohridentität wurde geändert oder kopiert.")
    (_start_handle, start), (_end_handle, end) = _endpoints(pipe)
    pipe["length_m"] = math.dist((start["x_m"], start["y_m"]), (end["x_m"], end["y_m"]))
    return core.validate_pipe(pipe)


def pipe_records():
    return tuple((handle, read_pipe(handle, data)) for handle, data in objects("sewer_pipe"))


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
    prefix = core.SHAFT_PREFIX if role == "sewer_shaft" else core.PIPE_PREFIX
    data = {"schema": core.SCHEMA, "role": role,
            "preferences": copy.deepcopy(preferences),
            "shaft" if role == "sewer_shaft" else "pipe": copy.deepcopy(payload)}
    handle = _live()._new_object((xy_m[0] / factor, xy_m[1] / factor), data,
                                 prefix + identity, created)
    return handle


def _paper_offset_units(handle, preferences):
    factor = adapter.units_to_meters()
    scale = max(1.0, float(vs.GetLScale(vs.GetLayer(handle)) or 1.0))
    return preferences["text_offset_mm"] / 1000.0 * scale / factor


def _default_label_position(owner, data):
    factor = adapter.units_to_meters()
    preferences = data["preferences"]
    offset = _paper_offset_units(owner, preferences)
    if data["role"] == "sewer_shaft":
        shaft = read_shaft(owner, data)
        return (shaft["x_m"] / factor + core.shaft_outer_diameter_m(shaft) / factor / 2.0 + offset,
                shaft["y_m"] / factor + offset)
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


def ensure_label(owner, data, created):
    identity = str(uuid.uuid5(uuid.NAMESPACE_URL, _name(owner) + ":channel-label"))
    name = core.LABEL_PREFIX + identity
    label = vs.GetObject(name)
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
    updated["labels"] = [name]
    _live().write_data(owner, updated)
    return label


def _reset_labels(data):
    for name in data.get("labels", ()):
        handle = vs.GetObject(name)
        if handle:
            label_data = _live().data_of(handle)
            if label_data and label_data.get("auto_position", True):
                old_auto = tuple(label_data.get("auto_xy", vs.GetSymLoc(handle)))
                actual = tuple(vs.GetSymLoc(handle))
                if math.dist(actual, old_auto) > 1e-5:
                    label_data["auto_position"] = False
                    _live().write_data(handle, label_data)
                else:
                    owner = vs.GetObject(label_data.get("owner", ""))
                    owner_data = _live().data_of(owner)
                    if owner and is_sewer_data(owner_data):
                        target = _default_label_position(owner, owner_data)
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
    try:
        shaft_handles = {}
        for shaft in built["shafts"]:
            handle = _new_object((shaft["x_m"], shaft["y_m"]), "sewer_shaft", shaft,
                                 preferences, created)
            shaft_handles[shaft["id"]] = handle
        for _handle, shaft in shaft_records():
            shaft_handles[shaft["id"]] = _handle
        pipe_handles = []
        for pipe in built["pipes"]:
            handle = _new_object((0.0, 0.0), "sewer_pipe", pipe, preferences, created)
            pipe_handles.append(handle)
            for identity in (pipe["start_id"], pipe["end_id"]):
                if not vs.AddAssociation(shaft_handles[identity], 5, handle):
                    raise core.SewerError("Rohr-Schacht-Verknüpfung konnte nicht gespeichert werden.")
        owners = list(shaft_handles.values()) + pipe_handles
        for owner in owners:
            data = _live().data_of(owner)
            if data["role"] == "sewer_shaft" and not data["shaft"]["visible"]:
                continue
            ensure_label(owner, data, created)
        for handle in created:
            vs.ResetObject(handle)
        for shaft_handle in shaft_handles.values():
            if shaft_handle not in created:
                vs.ResetObject(shaft_handle)
        validate_document(preferences)
    except Exception:
        for handle in reversed(created):
            if handle:
                vs.DelObject(handle)
        raise
    vs.DSelectAll()
    for handle in pipe_handles:
        vs.SetSelect(handle)
    vs.ReDrawAll()
    return tuple(pipe_handles)


def _delete_with_labels(handle, data):
    for name in data.get("labels", ()):
        label = vs.GetObject(name)
        if label:
            vs.DelObject(label)
    vs.DelObject(handle)


def _associate_pipe(handle, pipe):
    for identity in (pipe["start_id"], pipe["end_id"]):
        shaft_handle = _handle_by_id(core.SHAFT_PREFIX, identity)
        if not shaft_handle or not vs.AddAssociation(shaft_handle, 5, handle):
            raise core.SewerError("Rohr-Schacht-Verknüpfung konnte nicht gespeichert werden.")


def split_selected(handle, point_m, preferences):
    """Split one selected pipe at an interior click and add a connected shaft."""
    data = _live().data_of(handle)
    pipe = read_pipe(handle, data)
    (_start_handle, start), (_end_handle, end) = _endpoints(pipe)
    fraction, xy = core.project_on_pipe(
        (start["x_m"], start["y_m"]), (end["x_m"], end["y_m"]), point_m)
    shaft_id = str(uuid.uuid4())
    first, second = core.split_pipe(pipe, shaft_id, fraction)
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
    prospective_shafts = [value for _existing_handle, value in shaft_records()] + [shaft]
    core.validate_network(prospective_pipes, prospective_shafts)
    vs.NameUndoEvent("PD Kanalstrecke teilen")
    created = []
    try:
        shaft_handle = _new_object(xy, "sewer_shaft", shaft, preferences, created)
        pipe_handles = []
        for value in (first, second):
            new_handle = _new_object((0.0, 0.0), "sewer_pipe", value, preferences, created)
            pipe_handles.append(new_handle)
            _associate_pipe(new_handle, value)
        for owner in (shaft_handle,) + tuple(pipe_handles):
            ensure_label(owner, _live().data_of(owner), created)
        for created_handle in created:
            vs.ResetObject(created_handle)
    except Exception:
        for created_handle in reversed(created):
            if created_handle:
                vs.DelObject(created_handle)
        raise
    _delete_with_labels(handle, data)
    vs.DSelectAll()
    for pipe_handle in pipe_handles:
        vs.SetSelect(pipe_handle)
    vs.ReDrawAll()
    return tuple(pipe_handles)


def connect_branch(handle, point_m, branch_paths, options, preferences):
    """Split one pipe and add a height-matched branch in one transaction."""
    data = _live().data_of(handle)
    original = read_pipe(handle, data)
    (_start_handle, start), (_end_handle, end) = _endpoints(original)
    fraction, xy = core.project_on_pipe(
        (start["x_m"], start["y_m"]), (end["x_m"], end["y_m"]), point_m)
    paths = tuple(core.path(value) for value in branch_paths)
    if not paths or math.dist(paths[0][0], xy) > 0.001:
        raise core.SewerError("Die neue Leitung beginnt nicht am gewählten Anschlusspunkt.")
    shaft_id = str(uuid.uuid4())
    first, second = core.split_pipe(original, shaft_id, fraction)
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
                  "station_enabled": bool(options.get("stub_stationing", True)),
                  "main_start_id": original["start_id"],
                  "main_end_id": original["end_id"],
                  "main_pipe_ids": [first["id"], second["id"]],
                  "station_m": None, "station_zero_id": "",
                  "station_zero_name": "", "station_equal_inverts": False,
                  "station_basis": ""}
                 if options.get("as_stub") else None),
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
            name=_next_named_number("BA" if terminal["structure_type"] == "floor_drain" else "HA"),
            note="", diameter_m=0.0, special_outline_m=[], drops=[], stub=None,
            kd_m=terminal["terminal_top_m"], ks_m=terminal["terminal_invert_m"],
            terminal_width_m=terminal.get("terminal_width_m", 0.30),
            terminal_depth_m=terminal.get("terminal_depth_m", 0.60),
            terminal_symbol=terminal.get("terminal_symbol", ""),
            terminal_symbol_has_3d=terminal.get("terminal_symbol_has_3d", False))
        core.validate_shaft(endpoint, allow_hidden=True)
    connected_values = []
    for pipe in built["pipes"]:
        if pipe["start_id"] == shaft_id:
            connected_values.append(pipe["start_invert_m"])
        if pipe["end_id"] == shaft_id:
            connected_values.append(pipe["end_invert_m"])
    if not connected_values or any(abs(value - connection_invert) > 0.001 for value in connected_values):
        raise core.SewerError(
            "Die neue Leitung muss am Bestand mit KS = %.3f m anschließen. Berechnungsrichtung prüfen." %
            connection_invert)
    new_shafts = (shaft,) + tuple(built["shafts"])
    new_pipes = (first, second) + tuple(built["pipes"])
    prospective_pipes = [value for existing_handle, value in pipe_records()
                         if existing_handle != handle] + list(new_pipes)
    prospective_shafts = [value for _existing_handle, value in shaft_records()] + list(new_shafts)
    core.validate_network(prospective_pipes, prospective_shafts)
    preferences = sewer_settings.validate(preferences)
    ensure_classes(preferences)
    vs.NameUndoEvent("PD Leitung an Kanalstrecke anschließen")
    created = []
    try:
        shaft_handles = {value["id"]: existing_handle
                         for existing_handle, value in shaft_records()}
        for value in new_shafts:
            new_handle = _new_object((value["x_m"], value["y_m"]), "sewer_shaft",
                                     value, preferences, created)
            shaft_handles[value["id"]] = new_handle
        pipe_handles = []
        for value in new_pipes:
            new_handle = _new_object((0.0, 0.0), "sewer_pipe", value, preferences, created)
            pipe_handles.append(new_handle)
            for identity in (value["start_id"], value["end_id"]):
                if not vs.AddAssociation(shaft_handles[identity], 5, new_handle):
                    raise core.SewerError("Rohr-Schacht-Verknüpfung konnte nicht gespeichert werden.")
        owners = [shaft_handles[value["id"]] for value in new_shafts if value["visible"]] + pipe_handles
        for owner in owners:
            ensure_label(owner, _live().data_of(owner), created)
        for created_handle in created:
            vs.ResetObject(created_handle)
    except Exception:
        for created_handle in reversed(created):
            if created_handle:
                vs.DelObject(created_handle)
        raise
    _delete_with_labels(handle, data)
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
    if terminal["kind"] != main_pipe["kind"]:
        raise core.SewerError(
            "Anschlussart %s passt nicht zur gewählten Hauptleitung %s." %
            (terminal["kind"], main_pipe["kind"]))
    top = terminal.get("terminal_top_m")
    if terminal["structure_type"] == "floor_drain":
        top = nearest_cover_height(values[0]) if top is None else core.number(top, "Oberkante Ablauf")
        terminal_invert = top - core.number(terminal["terminal_depth_m"], "Tiefe des Bodenablaufs")
    else:
        top = core.number(top, "Höhe des Hausanschlusses")
        terminal_invert = top
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
        "draw_3d": preferences["draw_3d"],
        "graphics_mode": preferences["graphics_mode"],
        "line_type": preferences["single_line_type"],
        "connection_alignment": terminal["alignment"], "as_stub": True,
        "terminal": dict(terminal, terminal_top_m=top, terminal_invert_m=terminal_invert),
    }
    return connect_branch(handle, projected, (branch,), options, preferences)


def replace_with_special(handle, source_polygon, preferences):
    """Replace one round plan body with a selected polygon transactionally."""
    data = _live().data_of(handle)
    shaft = read_shaft(handle, data)
    if shaft["structure_type"] not in ("round", "special"):
        raise core.SewerError("Nur ein runder Schacht oder Sonderschacht kann umgewandelt werden.")
    source = adapter.extract_path(source_polygon)["points"]
    if not vs.IsPolyClosed(source_polygon):
        raise core.SewerError("Die Kontur des Sonderschachts muss geschlossen sein.")
    outline = core.special_outline(
        tuple((x - shaft["x_m"], y - shaft["y_m"]) for x, y in source))
    updated = core.validate_shaft(dict(
        shaft, structure_type="special", special_outline_m=list(outline)), allow_hidden=True)
    snapshot = copy.deepcopy(data)
    vs.NameUndoEvent("PD Sonderschacht herstellen")
    try:
        _live().write_data(handle, dict(data, shaft=updated,
                                       preferences=copy.deepcopy(preferences)))
        vs.ResetObject(handle)
    except Exception:
        _live().write_data(handle, snapshot)
        vs.ResetObject(handle)
        raise
    # The clicked construction polygon has been consumed by the new live
    # shaft. Undo restores both the former shaft and the polygon.
    vs.DelObject(source_polygon)
    for pipe_handle, _pipe in _connected_pipes(shaft["id"]):
        vs.ResetObject(pipe_handle)
    vs.ReDrawAll()
    return updated


def set_drop(handle, value, preferences):
    data = _live().data_of(handle)
    shaft = read_shaft(handle, data)
    connected = {pipe["id"] for _pipe_handle, pipe in _connected_pipes(shaft["id"])}
    if value["pipe_id"] not in connected:
        raise core.SewerError("Die gewählte Absturzhaltung ist nicht mehr mit dem Schacht verbunden.")
    drops = [row for row in shaft.get("drops", ()) if row["pipe_id"] != value["pipe_id"]]
    drops.append(dict(value))
    updated = core.validate_shaft(dict(shaft, drops=drops), allow_hidden=True)
    _commit_network_updates({}, {handle: updated}, preferences, "PD Absturz vor Schacht")
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
    try:
        shaft_handles = {value["id"]: existing_handle
                         for existing_handle, value in shaft_records()}
        for value in built["shafts"]:
            new_handle = _new_object((value["x_m"], value["y_m"]), "sewer_shaft",
                                     value, preferences, created)
            shaft_handles[value["id"]] = new_handle
        pipe_handles = []
        for value in built["pipes"]:
            new_handle = _new_object((0.0, 0.0), "sewer_pipe", value, preferences, created)
            pipe_handles.append(new_handle)
            for identity in (value["start_id"], value["end_id"]):
                endpoint = shaft_handles.get(identity)
                if not endpoint or not vs.AddAssociation(endpoint, 5, new_handle):
                    raise core.SewerError("Rohr-Schacht-Verknüpfung konnte nicht gespeichert werden.")
        owners = [shaft_handles[value["id"]] for value in built["shafts"] if value["visible"]]
        owners.extend(pipe_handles)
        for owner in owners:
            ensure_label(owner, _live().data_of(owner), created)
        for created_handle in created:
            vs.ResetObject(created_handle)
        vs.ResetObject(handle)
    except Exception:
        for created_handle in reversed(created):
            if created_handle:
                vs.DelObject(created_handle)
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
            vs.ResetObject(created_handle)
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
    for handle, data in handles:
        if data.get("role") == "sewer_pipe":
            pipe_rows[handle] = (data, read_pipe(handle, data))
        elif data.get("role") == "sewer_shaft":
            shaft = read_shaft(handle, data)
            shaft_rows[handle] = (data, shaft)
            for pipe_handle, pipe in _connected_pipes(shaft["id"]):
                pipe_rows[pipe_handle] = (_live().data_of(pipe_handle), pipe)
    if not pipe_rows and not shaft_rows:
        raise core.SewerError("Keine löschbaren Kanalobjekte markiert.")
    remaining_pipes = [pipe for handle, pipe in pipe_records() if handle not in pipe_rows]
    remaining_shafts = [shaft for handle, shaft in shaft_records() if handle not in shaft_rows]
    core.validate_network(remaining_pipes, remaining_shafts)
    affected_shaft_ids = {identity for _handle, (_data, pipe) in pipe_rows.items()
                          for identity in (pipe["start_id"], pipe["end_id"])}
    removed_shaft_ids = {shaft["id"] for _handle, (_data, shaft) in shaft_rows.items()}
    vs.NameUndoEvent("PD Kanalobjekte löschen")
    for handle, (data, _pipe) in pipe_rows.items():
        _delete_with_labels(handle, data)
    for handle, (data, _shaft) in shaft_rows.items():
        _delete_with_labels(handle, data)
    for identity in affected_shaft_ids - removed_shaft_ids:
        shaft_handle = _handle_by_id(core.SHAFT_PREFIX, identity)
        if shaft_handle:
            vs.ResetObject(shaft_handle)
    vs.ReDrawAll()
    return len(pipe_rows), len(shaft_rows)


def _set_graphics(handle, class_value, color, fill=True, opacity=100):
    vs.SetClass(handle, class_value)
    vs.SetPenFore(handle, color)
    vs.SetPenBack(handle, color)
    vs.SetFillFore(handle, color)
    vs.SetFillBack(handle, color)
    vs.SetFPat(handle, 1 if fill else 0)
    vs.SetOpacityN(handle, 100, int(opacity))


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
    if shaft.get("structure_type") == "special":
        other_id = pipe["end_id"] if pipe["start_id"] == shaft["id"] else pipe["start_id"]
        other_handle = _handle_by_id(core.SHAFT_PREFIX, other_id)
        if other_handle:
            other = read_shaft(other_handle)
            direction = other["x_m"] - shaft["x_m"], other["y_m"] - shaft["y_m"]
            distance = core.ray_polygon_distance(shaft["special_outline_m"], direction) / factor
            return max(0.0, distance), width, False
    if shaft.get("structure_type") == "floor_drain":
        return shaft.get("terminal_width_m", 0.30) * 0.5 / factor, width, False
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


def _mesh(faces, class_value, color):
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
    vs.SetFillFore(handle, color)
    vs.SetFillBack(handle, color)
    vs.SetOpacity(handle, 100)
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


def _draw_pipe_3d(first, second, radius, class_value, color,
                  start_radius=None, end_radius=None):
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
    return _mesh(_tube_faces(stations), class_value, color)


def _layer_z_m(handle):
    value = vs.GetLayerElevation(vs.GetLayer(handle))
    try:
        return float(value[0]) / 1000.0
    except (TypeError, ValueError, IndexError) as error:
        raise core.SewerError("Ebenenhöhe konnte nicht gelesen werden.") from error


def draw_pipe(handle, data):
    pipe = read_pipe(handle, data)
    (_start_handle, start), (_end_handle, end) = _endpoints(pipe)
    preferences = data["preferences"]
    ensure_classes(preferences)
    factor = adapter.units_to_meters()
    origin = vs.GetSymLoc(handle)
    first = (start["x_m"] / factor - origin[0], start["y_m"] / factor - origin[1])
    second = (end["x_m"] / factor - origin[0], end["y_m"] / factor - origin[1])
    color = color_for(data, preferences)
    width = pipe["dn_mm"] / 1000.0 / factor
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
        axis_offset = pipe["dn_mm"] / 2000.0
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
        _draw_pipe_3d(first3d, second3d, pipe["dn_mm"] / 2000.0 / factor,
                      class_name(pipe, preferences, "_3D"), color,
                      start_width * 0.5, end_width * 0.5)
        vs.ResetOrientation3D()
    updated = dict(data, pipe=pipe)
    _live().write_data(handle, updated)
    _reset_labels(updated)
    for identity in (pipe["start_id"], pipe["end_id"]):
        shaft_handle = _handle_by_id(core.SHAFT_PREFIX, identity)
        shaft_data = _live().data_of(shaft_handle) if shaft_handle else None
        if (is_sewer_data(shaft_data) and shaft_data.get("role") == "sewer_shaft" and
                shaft_data.get("shaft", {}).get("structure_type") == "stub" and
                pipe["id"] in shaft_data["shaft"].get("stub", {}).get("main_pipe_ids", ())):
            vs.ResetObject(shaft_handle)


def _frustum_faces(bottom_center, bottom_radius, top_center, top_radius, segments=24):
    axes = (1.0, 0.0, 0.0), (0.0, 1.0, 0.0)
    bottom = _ring(bottom_center, bottom_radius, axes[0], axes[1], segments)
    top = _ring(top_center, top_radius, axes[0], axes[1], segments)
    faces = [tuple(reversed(bottom)), top]
    for index in range(segments):
        following = (index + 1) % segments
        faces.append((bottom[index], bottom[following], top[following], top[index]))
    return tuple(faces)


def _draw_shaft_3d(handle, shaft, class_value, color, factor):
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
        _set_graphics(body, class_value, color, fill=True, opacity=100)
    cover_center = _cover_center(shaft, factor)
    _mesh(_frustum_faces(
        (0.0, 0.0, transition_bottom), radius,
        (cover_center[0], cover_center[1], z1), cover_radius), class_value, color)
    cover = 0.05 / factor
    vs.BeginXtrd(z1, z1 + cover)
    vs.Oval(((cover_center[0] - cover_radius), (cover_center[1] + cover_radius)),
            ((cover_center[0] + cover_radius), (cover_center[1] - cover_radius)))
    vs.EndXtrd()
    lid = vs.LNewObj()
    if not lid:
        raise core.SewerError("3D-Schachtdeckel konnte nicht erzeugt werden.")
    _set_graphics(lid, class_value, color, fill=True, opacity=100)


def _connected_pipes(identity):
    return tuple((handle, pipe) for handle, pipe in pipe_records()
                 if identity in (pipe["start_id"], pipe["end_id"]))


def _refresh_stub_stationing(shaft):
    """Derive a fitting station from current main geometry and inverts."""
    if shaft.get("structure_type") != "stub" or not shaft.get("stub", {}).get(
            "station_enabled", False):
        return shaft
    result = copy.deepcopy(shaft)
    stub = result["stub"]
    start_handle = _handle_by_id(core.SHAFT_PREFIX, stub["main_start_id"])
    end_handle = _handle_by_id(core.SHAFT_PREFIX, stub["main_end_id"])
    if not start_handle or not end_handle:
        raise core.SewerError("Stationierungsnullpunkt des Kanalstutzens fehlt.")
    start = read_shaft(start_handle)
    end = read_shaft(end_handle)
    main_pipes = {}
    for pipe_id in stub["main_pipe_ids"]:
        pipe_handle = _handle_by_id(core.PIPE_PREFIX, pipe_id)
        if not pipe_handle:
            raise core.SewerError("Hauptleitung der Stutzenstationierung fehlt.")
        main_pipes[pipe_id] = read_pipe(pipe_handle)

    def invert_at(identity):
        values = []
        for pipe in main_pipes.values():
            if pipe["start_id"] == identity:
                values.append(pipe["start_invert_m"])
            if pipe["end_id"] == identity:
                values.append(pipe["end_invert_m"])
        if len(values) != 1:
            raise core.SewerError("Hauptleitungssohle der Stutzenstationierung ist nicht eindeutig.")
        return values[0]

    try:
        station = stub_stationing.calculate(
            {"id": start["id"], "x_m": start["x_m"], "y_m": start["y_m"],
             "invert_m": invert_at(start["id"])},
            {"id": end["id"], "x_m": end["x_m"], "y_m": end["y_m"],
             "invert_m": invert_at(end["id"])},
            (result["x_m"], result["y_m"]),
            start_axis=((start["x_m"], start["y_m"]),
                        (result["x_m"], result["y_m"])),
            end_axis=((end["x_m"], end["y_m"]),
                      (result["x_m"], result["y_m"])))
    except stub_stationing.StubStationingError as error:
        raise core.SewerError(str(error)) from error
    zero = start if station["station_zero_id"] == start["id"] else end
    stub.update(station, station_zero_name=zero.get("name", ""))
    result["stub"] = stub
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
        changed[pipe_handle] = core.validate_pipe(value)
    return changed


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
        support = max(x * dx + y * dy for x, y in shaft["special_outline_m"]) / factor
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


def _draw_local_polygon(points, class_value, color, fill=True, opacity=50):
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
    _set_graphics(handle, class_value, color, fill=fill, opacity=opacity)
    return handle


def _draw_special_shaft_3d(handle, shaft, class_value, color, factor):
    layer_z = _layer_z_m(handle)
    z0 = (shaft["ks_m"] - layer_z) / factor
    z1 = (shaft["kd_m"] - layer_z) / factor
    if z1 <= z0:
        z1 = z0 + 0.01 / factor
    vs.BeginXtrd(z0, z1)
    vs.BeginPoly()
    for x, y in shaft["special_outline_m"]:
        vs.AddPoint((x / factor, y / factor))
    vs.EndPoly()
    vs.EndXtrd()
    body = vs.LNewObj()
    if not body:
        raise core.SewerError("3D-Sonderschacht konnte nicht erzeugt werden.")
    _set_graphics(body, class_value, color, fill=True, opacity=100)
    cover_center = _cover_center(shaft, factor)
    cover_radius = shaft["cover_diameter_m"] / factor * 0.5
    vs.BeginXtrd(z1, z1 + 0.05 / factor)
    vs.Oval(((cover_center[0] - cover_radius), (cover_center[1] + cover_radius)),
            ((cover_center[0] + cover_radius), (cover_center[1] - cover_radius)))
    vs.EndXtrd()
    lid = vs.LNewObj()
    if not lid:
        raise core.SewerError("3D-Schachtdeckel des Sonderschachts konnte nicht erzeugt werden.")
    _set_graphics(lid, class_value, color, fill=True, opacity=100)


def _draw_floor_drain(handle, shaft, class_value, color, factor, draw_3d):
    width = shaft["terminal_width_m"] / factor
    symbol_name = shaft.get("terminal_symbol", "")
    definition = vs.GetObject(symbol_name) if symbol_name else None
    symbol_used = bool(definition and int(vs.GetTypeN(definition) or 0) == 16)
    if symbol_used:
        vs.Symbol(symbol_name, (0.0, 0.0), 0.0)
        symbol = vs.LNewObj()
        if symbol:
            vs.SetClass(symbol, class_value)
    half = width * 0.5
    if not symbol_used:
        vs.Rect((-half, half), (half, -half))
        square = vs.LNewObj()
        if not square:
            raise core.SewerError("2D-Bodenablauf konnte nicht erzeugt werden.")
        _set_graphics(square, class_value, color, fill=True, opacity=50)
    if draw_3d and (not symbol_used or not shaft.get("terminal_symbol_has_3d", False)):
        layer_z = _layer_z_m(handle)
        z0 = (shaft["ks_m"] - layer_z) / factor
        z1 = (shaft["kd_m"] - layer_z) / factor
        vs.BeginXtrd(z0, max(z1, z0 + 0.01 / factor))
        vs.Rect((-half, half), (half, -half))
        vs.EndXtrd()
        body = vs.LNewObj()
        if not body:
            raise core.SewerError("3D-Bodenablaufkasten konnte nicht erzeugt werden.")
        _set_graphics(body, class_value, color, fill=True, opacity=100)


def _draw_stub_symbol(shaft, data, class_value, color, factor):
    """Plan marker for a circular branch fitting at the main holding."""
    rows = _junction_rows(shaft)
    branch_dn = shaft["stub"]["branch_dn_mm"]
    branch = next((row for row in rows if row["pipe"]["dn_mm"] == branch_dn), None)
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
        distance = (max(core.shaft_outer_diameter_m(shaft) * 0.5, 0.20) + 0.20) / factor
        center = ux * distance, uy * distance
        radius = pipe["dn_mm"] / 2000.0 / factor
        vs.Oval(((center[0] - radius), (center[1] + radius)),
                ((center[0] + radius), (center[1] - radius)))
        marker = vs.LNewObj()
        if marker:
            _set_graphics(marker, class_value, color, fill=False, opacity=100)
        if pipe.get("draw_3d", preferences.get("draw_3d", True)):
            first = (center[0], center[1],
                     (drop["lower_invert_m"] + pipe["dn_mm"] / 2000.0 - layer_z) / factor)
            second = (center[0], center[1],
                      (drop["upper_invert_m"] + pipe["dn_mm"] / 2000.0 - layer_z) / factor)
            if second[2] > first[2] + 1e-9:
                _draw_pipe_3d(first, second, radius,
                              class_name(pipe, preferences, "_3D"), color)


def draw_shaft(handle, data):
    old = core.validate_shaft(data["shaft"], allow_hidden=True)
    shaft = read_shaft(handle, data)
    shaft = _refresh_stub_stationing(shaft)
    moved = math.dist((old["x_m"], old["y_m"]), (shaft["x_m"], shaft["y_m"])) > 1e-8
    preferences = data["preferences"]
    ensure_classes(preferences)
    factor = adapter.units_to_meters()
    radius = core.shaft_outer_diameter_m(shaft) / factor / 2.0
    color = color_for(data, preferences)
    class_value = class_name(shaft, preferences)
    _set_graphics(handle, class_value, color, fill=True, opacity=50)
    structure = shaft.get("structure_type", "round" if radius > 0.0 else "junction")
    if structure == "round" and shaft["visible"]:
        if radius > 0.0:
            vs.Oval((-radius, radius), (radius, -radius))
            circle = vs.LNewObj()
            if not circle:
                raise core.SewerError("2D-Schacht konnte nicht erzeugt werden.")
            _set_graphics(circle, class_value, color, fill=True, opacity=50)
            if (shaft["construction_material"] == "concrete" and
                    shaft["wall_thickness_m"] > 0.0):
                inner_radius = shaft["diameter_m"] / factor * 0.5
                vs.Oval((-inner_radius, inner_radius), (inner_radius, -inner_radius))
                inner = vs.LNewObj()
                if not inner:
                    raise core.SewerError("Innere Betonschachtkontur konnte nicht erzeugt werden.")
                _set_graphics(inner, class_value, color, fill=False, opacity=100)
            _draw_shaft_cover(shaft, factor, class_value, color)
            if preferences.get("draw_3d", True):
                _draw_shaft_3d(handle, shaft, class_name(shaft, preferences, "_3D"), color, factor)
                vs.ResetOrientation3D()
    elif structure == "special" and shaft["visible"]:
        _draw_local_polygon(
            tuple((x / factor, y / factor) for x, y in shaft["special_outline_m"]),
            class_value, color, fill=True, opacity=50)
        _draw_shaft_cover(shaft, factor, class_value, color)
        if preferences.get("draw_3d", True):
            _draw_special_shaft_3d(
                handle, shaft, class_name(shaft, preferences, "_3D"), color, factor)
            vs.ResetOrientation3D()
    elif structure == "floor_drain" and shaft["visible"]:
        _draw_floor_drain(
            handle, shaft, class_value, color, factor, preferences.get("draw_3d", True))
        vs.ResetOrientation3D()
    elif structure == "house" and shaft["visible"]:
        # The contractual plan representation has no terminal symbol.  The
        # capped branch pipe and its height label remain independently editable.
        pass
    elif structure == "stub":
        _draw_hidden_join(shaft, data)
        _draw_stub_symbol(shaft, data, class_value, color, factor)
    else:
        _draw_hidden_join(shaft, data)
    _draw_drops(handle, shaft, preferences, class_value, color, factor)
    if shaft["visible"] and structure in ("round", "special"):
        _draw_connection_height_labels(shaft, preferences, factor)
    updated = dict(data, shaft=shaft)
    _live().write_data(handle, updated)
    _reset_labels(updated)
    if moved:
        for pipe_handle, _pipe in _connected_pipes(shaft["id"]):
            vs.ResetObject(pipe_handle)
            other_id = _pipe["end_id"] if _pipe["start_id"] == shaft["id"] else _pipe["start_id"]
            other_handle = _handle_by_id(core.SHAFT_PREFIX, other_id)
            if other_handle:
                vs.ResetObject(other_handle)


def _pipe_anchor(pipe):
    (_a, start), (_b, end) = _endpoints(pipe)
    return ((start["x_m"] + end["x_m"]) * 0.5,
            (start["y_m"] + end["y_m"]) * 0.5)


def _create_text(text, angle, preferences, wrap_width=0.0):
    vs.TextOrigin((0.0, 0.0))
    vs.CreateText(text)
    handle = vs.LNewObj()
    if not handle:
        raise core.SewerError("Kanalbeschriftung konnte nicht erzeugt werden.")
    vs.SetTextStyleRef(handle, 0)
    font_id = int(vs.GetFontID("Arial") or 0)
    if font_id:
        vs.SetTextFont(handle, 0, len(text), font_id)
    vs.SetTextSize(handle, 0, len(text), preferences["point_size"])
    if wrap_width > 1e-9:
        vs.SetTextWidth(handle, wrap_width)
    vs.SetTextJust(handle, 2)
    vs.SetTextVertAlignN(handle, 3)
    vs.SetTextOrientation(handle, (0.0, 0.0), angle, False)
    vs.SetClass(handle, preferences["text_class"])
    vs.SetPenFore(handle, TEXT_COLOR)
    vs.SetFPat(handle, 0)
    return handle


def _draw_connection_height_labels(shaft, preferences, factor):
    """Label every differing endpoint height directly at its pipe direction."""
    rows = shaft_connection_views(shaft)
    if len({round(row["invert_m"], 9) for row in rows}) <= 1:
        return
    base_radius_m = max(core.shaft_outer_diameter_m(shaft) * 0.5, 0.25)
    for index, row in enumerate(rows):
        ux, uy = row["direction"]
        # Stagger close labels radially while retaining the exact connection ray.
        offset_m = base_radius_m + 0.16 + (index % 2) * 0.07
        x, y = ux * offset_m / factor, uy * offset_m / factor
        text = "%s KS %s m" % (
            row["tag"], core.format_number(row["invert_m"], preferences["height_decimals"]))
        text_handle = _create_text(text, 0.0, preferences)
        vs.HMove(text_handle, x, y)


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


def _leader(anchor, box, preferences, padding):
    end = label_layout.leader_end(anchor, (box,), padding)
    if math.dist(anchor, end) <= 1e-9:
        return None
    vs.MoveTo(anchor)
    vs.LineTo(end)
    leader = vs.LNewObj()
    if leader:
        _set_graphics(leader, preferences["text_class"], TEXT_COLOR, fill=False, opacity=100)
    return leader


def _shaft_label_frame(box, preferences, padding):
    left = box[0][0] - padding
    bottom = box[0][1] - padding
    right = box[1][0] + padding
    top = box[1][1] + padding
    vs.Rect((left, top), (right, bottom))
    frame = vs.LNewObj()
    if not frame:
        raise core.SewerError("Beschriftungsrahmen konnte nicht erzeugt werden.")
    _set_graphics(frame, preferences["text_class"], TEXT_COLOR, fill=False, opacity=100)
    return frame, ((left, bottom), (right, top))


def draw_label(handle, data):
    owner = vs.GetObject(data["owner"])
    owner_data = _live().data_of(owner)
    if not owner or not is_sewer_data(owner_data) or _name(handle) not in owner_data.get("labels", ()):
        return
    preferences = owner_data["preferences"]
    ensure_classes(preferences)
    factor = adapter.units_to_meters()
    label_position = vs.GetSymLoc(handle)
    default_position = _default_label_position(owner, owner_data)
    old_auto = tuple(data.get("auto_xy", label_position))
    if data.get("auto_position", True) and math.dist(label_position, old_auto) > 1e-5:
        data = dict(data, auto_position=False)
        _live().write_data(handle, data)
    angle = 0.0
    wrap_width = 0.0
    shaft_label = False
    if owner_data["role"] == "sewer_pipe":
        pipe = read_pipe(owner, owner_data)
        (_a, start), (_b, end) = _endpoints(pipe)
        # Reader direction follows the deep point while remaining line-parallel.
        high, low = ((start, end) if pipe["start_invert_m"] >= pipe["end_invert_m"] else (end, start))
        angle = math.degrees(math.atan2(low["y_m"] - high["y_m"], low["x_m"] - high["x_m"]))
        text = core.pipe_label(pipe, preferences)
        anchor_m = _pipe_anchor(pipe)
        wrap_width = pipe.get("label_width_m", 0.0) / factor
    else:
        shaft_label = True
        shaft = read_shaft(owner, owner_data)
        rows = shaft_connection_views(shaft)
        text = core.shaft_label(shaft, rows, preferences)
        anchor_m = shaft["x_m"], shaft["y_m"]
    if not text:
        return
    text_handle = _create_text(
        text, angle - float(vs.GetSymRot(handle) or 0.0), preferences, wrap_width)
    box = _bbox(vs.GetBBox(text_handle))
    scale = max(1.0, float(vs.GetLScale(vs.GetLayer(handle)) or 1.0))
    padding = 0.0008 * scale / factor
    anchor = (anchor_m[0] / factor - label_position[0],
              anchor_m[1] / factor - label_position[1])
    if shaft_label:
        _frame, framed_box = _shaft_label_frame(box, preferences, padding)
        _leader(anchor, framed_box, preferences, 0.0)
    elif not data.get("auto_position", True) and math.dist(label_position, default_position) > 1e-5:
        _leader(anchor, box, preferences, padding)


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
    for shaft_handle, shaft in tuple(final_shafts.items()):
        if shaft["id"] in affected_ids and endpoint_values.get(shaft["id"]):
            value = dict(shaft, ks_m=min(endpoint_values[shaft["id"]]))
            final_shafts[shaft_handle] = core.validate_shaft(value, allow_hidden=True)
    core.validate_network(tuple(final_pipes.values()), tuple(final_shafts.values()))
    return ({handle: value for handle, value in final_pipes.items()
             if value != original_pipes[handle]},
            {handle: value for handle, value in final_shafts.items()
             if value != original_shafts[handle]})


def _commit_network_updates(pipe_updates, shaft_updates, preferences, undo_name):
    requested_resets = tuple(dict.fromkeys(tuple(shaft_updates) + tuple(pipe_updates)))
    pipes, shafts = _prepare_network_updates(pipe_updates, shaft_updates)
    rows = tuple(dict.fromkeys(tuple(shafts) + tuple(pipes)))
    snapshots = {handle: copy.deepcopy(_live().data_of(handle)) for handle in rows}
    vs.NameUndoEvent(undo_name)
    try:
        for handle, value in shafts.items():
            _live().write_data(handle, dict(
                snapshots[handle], shaft=value, preferences=copy.deepcopy(preferences)))
        for handle, value in pipes.items():
            _live().write_data(handle, dict(
                snapshots[handle], pipe=value, preferences=copy.deepcopy(preferences)))
        for handle in tuple(dict.fromkeys(rows + requested_resets)):
            vs.ResetObject(handle)
    except Exception:
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
    if not is_sewer_data(data) or data["role"] not in ("sewer_pipe", "sewer_shaft"):
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


def edit_network_chain(handle, preferences):
    """Edit several slopes and shaft elevations as one transactional change."""
    shaft_rows, pipe_rows = network_component(handle)
    by_key = ({("shaft", value["id"]): row_handle for row_handle, value in shaft_rows} |
              {("pipe", value["id"]): row_handle for row_handle, value in pipe_rows})

    def highlight(role, identity):
        target = by_key.get((role, identity))
        if target:
            vs.DSelectAll()
            vs.SetSelect(target)
            vs.ReDrawAll()
    try:
        choice = sewer_ui.network_chain_dialog(
            tuple(value for _handle, value in shaft_rows),
            tuple(value for _handle, value in pipe_rows), highlight)
    finally:
        vs.DSelectAll()
        vs.SetSelect(handle)
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


def edit(handle, preferences):
    data = _live().data_of(handle)
    if data and data["role"] == "sewer_label":
        handle = vs.GetObject(data["owner"])
        data = _live().data_of(handle)
    if not is_sewer_data(data):
        raise core.SewerError("Kein Kanalobjekt gewählt.")
    if data["role"] == "sewer_pipe":
        original = read_pipe(handle, data)
        initial = dict(original, calculation_mode="end", calculation_value=original["end_invert_m"],
                       cover_height_m=original["start_invert_m"] + preferences["cover_offset_m"],
                       shaft_diameter_m=preferences["shaft_diameter_m"], shaft_mode="all")
        values = sewer_ui.pipe_properties_dialog(preferences, initial)
        if values is None:
            return False
        updated = core.update_pipe(original, original["length_m"], values)
        if values.get("reverse_flow"):
            updated["start_id"], updated["end_id"] = updated["end_id"], updated["start_id"]
            updated = core.validate_pipe(updated)
        pipe_updates = {handle: updated}
        delta = updated["end_invert_m"] - original["end_invert_m"]
        if (updated["end_id"] == original["end_id"] and abs(delta) > 1e-9):
            following = _downstream_pipes(updated["end_id"], (updated["id"],))
            if following:
                propagation = sewer_ui.downstream_height_dialog(delta, len(following))
                if propagation is None:
                    return False
                pipe_updates.update(_downstream_height_changes(
                    following, updated["end_id"], delta, propagation))
        _commit_network_updates(pipe_updates, {}, preferences, "PD Kanalstrecke bearbeiten")
        return True
    if data["role"] == "sewer_shaft":
        original = read_shaft(handle, data)
        connected = _connected_pipes(original["id"])
        incoming = tuple(pipe["end_invert_m"] for _pipe_handle, pipe in connected
                         if pipe["end_id"] == original["id"])
        outgoing = tuple(pipe["start_invert_m"] for _pipe_handle, pipe in connected
                         if pipe["start_id"] == original["id"])
        choice = sewer_ui.shaft_dialog(original, preferences, incoming, outgoing)
        if choice is None:
            return False
        updated = choice["shaft"]
        _unique_shaft_name(updated["name"], original["id"])
        changed_pipes = {}
        old_outlet = min(outgoing) if outgoing else choice["outlet_invert_m"]
        delta = choice["outlet_invert_m"] - old_outlet
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
                changed["end_invert_m"] = choice["inlet_invert_m"]
            if pipe["start_id"] == original["id"]:
                changed["start_invert_m"] = choice["outlet_invert_m"]
            changed_pipes[pipe_handle] = core.validate_pipe(changed)
        _commit_network_updates(
            changed_pipes, {handle: updated}, preferences, "PD Kanalschacht bearbeiten")
        return True
    return False


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


def apply_standard_colors(preferences):
    count = 0
    for handle, data in objects():
        if data["role"] not in ("sewer_pipe", "sewer_shaft"):
            continue
        payload = data.get("pipe") or data.get("shaft")
        if payload.get("color_override") is None:
            _live().write_data(handle, dict(data, preferences=copy.deepcopy(preferences)))
            vs.ResetObject(handle)
            _reset_labels(data)
            count += 1
    return count


def validate_document(preferences=None):
    preferences = sewer_settings.validate(preferences or sewer_settings.load())
    pipes = tuple(pipe for _handle, pipe in pipe_records())
    shafts = tuple(shaft for _handle, shaft in shaft_records())
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
    if errors:
        raise core.SewerError("\n".join(sorted(set(errors))))
    return {"pipes": len(pipes), "shafts": len([value for value in shafts if value["visible"]]),
            "nodes": len(shafts), "errors": ()}


def _repair_duplicate(handle, data):
    payload_key = "shaft" if data["role"] == "sewer_shaft" else "pipe"
    payload = copy.deepcopy(data[payload_key])
    prefix = core.SHAFT_PREFIX if data["role"] == "sewer_shaft" else core.PIPE_PREFIX
    expected = prefix + payload["id"]
    if _name(handle) == expected:
        return data
    if not vs.GetObject(expected):
        vs.SetName(handle, expected)
        return data
    payload["id"] = str(uuid.uuid4())
    if data["role"] == "sewer_shaft" and payload["visible"]:
        next_number = _next_numbers()[payload["kind"]]
        payload["name"] = "%s.%03d" % (payload["kind"], next_number)
    data = dict(data, **{payload_key: payload}, labels=[])
    vs.SetName(handle, prefix + payload["id"])
    _live().write_data(handle, data)
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
            return
        data = _repair_duplicate(handle, data)
        if data["role"] == "sewer_pipe":
            draw_pipe(handle, data)
        elif data["role"] == "sewer_shaft":
            draw_shaft(handle, data)
    except Exception as error:
        vs.TextOrigin((0.0, 0.0))
        vs.CreateText("KANAL PRÜFEN: " + str(error))
        adapter.alert("Kanalanlage konnte nicht neu aufgebaut werden: %s" % error)
