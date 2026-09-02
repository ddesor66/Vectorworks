# -*- coding: utf-8 -*-
"""Pure channel-network model, calculations and validation (SI units)."""
from __future__ import absolute_import

import copy
import math
import uuid


SCHEMA = 1
KINDS = ("RW", "SW", "MW")
DEFAULT_DNS = (50, 70, 100, 125, 150, 200, 250, 300, 350, 400,
               500, 600, 700, 800, 900, 1000)
DEFAULT_MATERIALS = ("PP", "KG", "B", "STZ", "STB")
GRAPHICS_MODES = ("single_line", "double_line")
CONNECTION_ALIGNMENTS = ("invert", "axis", "springline", "crown")
STRUCTURE_TYPES = ("round", "special", "junction", "stub", "floor_drain", "house")
SHAFT_CONSTRUCTION_MATERIALS = ("PP", "concrete")
DEFAULT_CONCRETE_WALL_THICKNESS_M = 0.15
SHAFT_PREFIX = "PD-KAN-S-"
PIPE_PREFIX = "PD-KAN-R-"
LABEL_PREFIX = "PD-KAN-T-"


class SewerError(ValueError):
    pass


def shaft_construction_material(value):
    text = str(value or "PP").strip()
    aliases = {"pp": "PP", "beton": "concrete", "concrete": "concrete"}
    result = aliases.get(text.casefold())
    if result not in SHAFT_CONSTRUCTION_MATERIALS:
        raise SewerError("Schachtbauart muss PP oder Beton sein.")
    return result


def shaft_construction_material_label(value):
    return "PP-Schacht" if shaft_construction_material(value) == "PP" else "Betonschacht"


def shaft_outer_diameter_m(shaft):
    """Return the physical outside diameter from clear inside dimensions."""
    if not isinstance(shaft, dict):
        raise SewerError("Schachtdaten fehlen für die Außendurchmesserberechnung.")
    diameter = number(shaft.get("diameter_m", 0.0), "Lichter Schachtinnendurchmesser")
    material = shaft_construction_material(shaft.get("construction_material", "PP"))
    default_wall = DEFAULT_CONCRETE_WALL_THICKNESS_M if material == "concrete" else 0.0
    wall = number(shaft.get("wall_thickness_m", default_wall), "Schachtwandstärke")
    if (diameter <= 0.0 or material == "PP" or
            shaft.get("structure_type") == "special"):
        wall = 0.0
    return diameter + 2.0 * wall


def number(value, label):
    try:
        result = float(value)
    except (TypeError, ValueError) as error:
        raise SewerError("%s ist keine gültige Zahl." % label) from error
    if not math.isfinite(result):
        raise SewerError("%s muss endlich sein." % label)
    return result


def point(value):
    if not isinstance(value, (tuple, list)) or len(value) != 2:
        raise SewerError("Ungültiger Kanalpunkt.")
    return number(value[0], "X-Koordinate"), number(value[1], "Y-Koordinate")


def path(points):
    result = tuple(point(value) for value in points)
    if len(result) < 2:
        raise SewerError("Eine Kanalstrecke benötigt mindestens zwei Punkte.")
    for first, second in zip(result, result[1:]):
        if math.dist(first, second) <= 1e-6:
            raise SewerError("Aufeinanderfolgende Kanalpunkte müssen verschieden sein.")
    return result


def path_lengths(points):
    points = path(points)
    lengths = tuple(math.dist(first, second) for first, second in zip(points, points[1:]))
    total = sum(lengths)
    if not math.isfinite(total) or total <= 1e-6:
        raise SewerError("Die Kanallänge ist ungültig.")
    return lengths, total


def elevation_series(points, start_invert_m, mode, value):
    """Return invert elevations in drawing order and the positive slope."""
    lengths, total = path_lengths(points)
    start = number(start_invert_m, "Anfangssohle")
    value = number(value, "Endsohle/Gefälle")
    if mode == "slope":
        slope = value
        end = start - total * slope / 100.0
    elif mode == "start":
        # In this mode the first numeric argument is the known end invert.
        slope = value
        end = start
        start = end + total * slope / 100.0
    elif mode == "end":
        end = value
        slope = (start - end) / total * 100.0
    else:
        raise SewerError("Unbekannte Höhenberechnung.")
    if slope < -1e-9:
        raise SewerError(
            "Das Gefälle verläuft entgegen der Fließrichtung. Zeichenrichtung umkehren oder Höhen korrigieren.")
    slope = max(0.0, slope)
    elevations = [start]
    station = 0.0
    for length in lengths:
        station += length
        elevations.append(start - station * slope / 100.0)
    elevations[-1] = end
    return tuple(elevations), slope


def slope_percent(start_invert_m, end_invert_m, length_m):
    length = number(length_m, "Länge")
    if length <= 1e-6:
        raise SewerError("Die Kanallänge muss größer als null sein.")
    return (number(start_invert_m, "Anfangssohle") -
            number(end_invert_m, "Endsohle")) / length * 100.0


def _kind(value):
    result = str(value or "").strip().upper()
    if result not in KINDS:
        raise SewerError("Kanalart muss RW, SW oder MW sein.")
    return result


def _material(value):
    result = str(value or "").strip().upper()
    if not result or len(result) > 32 or any(char in result for char in "\r\n\t|;"):
        raise SewerError("Ungültiges Kanalrohrmaterial.")
    return result


def _dn(value):
    result = number(value, "Nenndurchmesser")
    if not result.is_integer() or not 1 <= result <= 10000:
        raise SewerError("DN muss eine ganze Zahl zwischen 1 und 10000 mm sein.")
    return int(result)


def _identity(value, label):
    result = str(value or "").strip()
    if not result:
        raise SewerError("%s fehlt." % label)
    return result


def class_token(value, label):
    """Return a stable, Vectorworks-safe class-name component."""
    result = str(value or "").strip().replace("/", "-").replace("\\", "-")
    result = "-".join(part for part in result.replace(" ", "-").split("-") if part)
    if not result or len(result) > 48 or any(char in result for char in "\r\n\t:"):
        raise SewerError("%s ist kein gültiger Klassenbestandteil." % label)
    return result


def pipe_class_name(prefix, pipe, suffix=""):
    """One class per channel kind, nominal diameter and material."""
    value = validate_pipe(pipe)
    return "%s-%s-DN%d-%s%s" % (
        class_token(prefix, "Kanal-Klassenpräfix"), value["kind"], value["dn_mm"],
        class_token(value["material"], "Material"), str(suffix))


def connection_invert(main_invert_m, main_dn_mm, branch_dn_mm, alignment):
    """Calculate branch invert for the requested circular-pipe alignment."""
    main = number(main_invert_m, "Sohlhöhe der Hauptleitung")
    main_diameter = _dn(main_dn_mm) / 1000.0
    branch_diameter = _dn(branch_dn_mm) / 1000.0
    mode = str(alignment or "invert")
    if mode not in CONNECTION_ALIGNMENTS:
        raise SewerError("Unbekannte Anschlussart des Kanalstutzens.")
    if mode == "invert":
        return main
    if mode in ("axis", "springline"):
        # At a circular pipe the geometrical springline lies on its axis.
        return main + (main_diameter - branch_diameter) * 0.5
    return main + main_diameter - branch_diameter


def connection_alignment_label(value):
    labels = {"invert": "Sohlgleich", "axis": "Achsgleich",
              "springline": "Kämpfergleich", "crown": "Scheitelgleich"}
    try:
        return labels[str(value)]
    except KeyError as error:
        raise SewerError("Unbekannte Anschlussart des Kanalstutzens.") from error


def polygon_area(points):
    values = tuple(point(value) for value in points)
    if len(values) < 3:
        raise SewerError("Ein Sonderschacht benötigt mindestens drei Eckpunkte.")
    area = sum(first[0] * second[1] - second[0] * first[1]
               for first, second in zip(values, values[1:] + values[:1])) * 0.5
    if abs(area) <= 1e-6:
        raise SewerError("Die Kontur des Sonderschachts besitzt keine Fläche.")
    return area


def special_outline(points):
    values = tuple(point(value) for value in points)
    polygon_area(values)
    if len(set(values)) != len(values):
        raise SewerError("Die Kontur des Sonderschachts enthält doppelte Eckpunkte.")
    return values


def ray_polygon_distance(points, direction):
    """Distance from local origin to the nearest polygon edge on one ray."""
    values = special_outline(points)
    dx, dy = point(direction)
    length = math.hypot(dx, dy)
    if length <= 1e-9:
        raise SewerError("Ungültige Anschlussrichtung am Sonderschacht.")
    dx, dy = dx / length, dy / length
    hits = []
    for first, second in zip(values, values[1:] + values[:1]):
        ex, ey = second[0] - first[0], second[1] - first[1]
        divisor = dx * ey - dy * ex
        if abs(divisor) <= 1e-12:
            continue
        ray = (first[0] * ey - first[1] * ex) / divisor
        edge = (first[0] * dy - first[1] * dx) / divisor
        if ray >= 0.0 and -1e-9 <= edge <= 1.0 + 1e-9:
            hits.append(ray)
    if not hits:
        raise SewerError("Der Einfügepunkt liegt nicht innerhalb der Sonderschachtkontur.")
    return min(hits)


def _find_node(nodes, xy, kind, tolerance_m):
    for node in nodes:
        if node["kind"] == kind and math.dist((node["x_m"], node["y_m"]), xy) <= tolerance_m:
            return node
    return None


def _shaft_name(kind, next_numbers):
    number_value = int(next_numbers.get(kind, 1))
    next_numbers[kind] = number_value + 1
    return "%s.%03d" % (kind, number_value)


def largest_angular_gap_bisector(angles_deg):
    """Return the direction centered in the largest free angular sector."""
    values = sorted({number(value, "Kanalwinkel") % 360.0 for value in angles_deg})
    if not values:
        return 0.0
    if len(values) == 1:
        return (values[0] + 180.0) % 360.0
    best_start, best_gap = values[0], -1.0
    for index, start in enumerate(values):
        end = values[(index + 1) % len(values)]
        gap = (end - start) % 360.0
        if gap > best_gap:
            best_start, best_gap = start, gap
    return (best_start + best_gap * 0.5) % 360.0


def build_network(paths, options, existing_shafts=(), next_numbers=None,
                  identity_factory=None, tolerance_m=0.001):
    """Build connected straight pipes and nodes without touching Vectorworks."""
    if not isinstance(options, dict):
        raise SewerError("Kanaleinstellungen fehlen.")
    kind = _kind(options.get("kind"))
    dn_mm = _dn(options.get("dn_mm"))
    outside_diameter_mm = number(
        options.get("outside_diameter_mm", dn_mm), "Rohraußendurchmesser")
    if not 0.0 < outside_diameter_mm <= 20000.0:
        raise SewerError("Der Rohraußendurchmesser muss größer als null und höchstens 20000 mm sein.")
    material = _material(options.get("material"))
    shaft_mode = str(options.get("shaft_mode", "all"))
    if shaft_mode not in ("all", "endpoints", "manual"):
        raise SewerError("Ungültige Schachterzeugung.")
    join_style = str(options.get("join_style", "round"))
    if join_style not in ("round", "bevel", "miter"):
        raise SewerError("Ungültige Verbindung der Außenlinien.")
    fillet_radius_m = number(options.get("fillet_radius_m", 0.20), "Ausrundungsradius")
    if not 0.01 <= fillet_radius_m <= 20.0:
        raise SewerError("Ausrundungsradius muss zwischen 0,01 m und 20,00 m liegen.")
    factory = identity_factory or (lambda: str(uuid.uuid4()))
    next_numbers = dict(next_numbers or {})
    nodes = [copy.deepcopy(value) for value in existing_shafts]
    existing_ids = {value["id"] for value in nodes}
    new_nodes = []
    pipes = []
    endpoint_ids = set()
    degree = {}
    for raw_points in paths:
        values = list(path(raw_points))
        if options.get("reverse_flow"):
            values.reverse()
        elevations, _slope = elevation_series(
            values, options.get("start_invert_m"), options.get("calculation_mode"),
            options.get("calculation_value"))
        node_rows = []
        for xy, elevation in zip(values, elevations):
            node = _find_node(nodes, xy, kind, tolerance_m)
            if node is None:
                identity = factory()
                node = {
                    "schema": SCHEMA,
                    "id": _identity(identity, "Schachtidentität"),
                    "kind": kind,
                    "name": "",
                    "note": "",
                    "x_m": xy[0],
                    "y_m": xy[1],
                    "kd_m": number(options.get("cover_height_m"), "Deckelhöhe"),
                    "ks_m": elevation,
                    "diameter_m": number(options.get("shaft_diameter_m", 1.0), "Schachtdurchmesser"),
                    "construction_material": shaft_construction_material(
                        options.get("shaft_construction_material", "PP")),
                    "wall_thickness_m": number(
                        options.get("shaft_wall_thickness_m",
                                    DEFAULT_CONCRETE_WALL_THICKNESS_M),
                        "Schachtwandstärke"),
                    "cover_diameter_m": number(options.get("cover_diameter_m", 0.625),
                                               "Schachtdeckeldurchmesser"),
                    "cover_symbol": str(options.get("cover_symbol") or "").strip(),
                    "cover_placement": str(options.get("cover_placement", "auto")),
                    "cover_rotation_deg": number(options.get("cover_rotation_deg", 0.0),
                                                 "Schachtdeckeldrehung"),
                    "structure_type": "junction",
                    "special_outline_m": [],
                    "drops": [],
                    "visible": False,
                    "color_override": copy.deepcopy(options.get("color_override")),
                }
                if node["diameter_m"] < 0.0:
                    raise SewerError("Der Schachtdurchmesser darf nicht negativ sein.")
                nodes.append(node)
                new_nodes.append(node)
            else:
                node["ks_m"] = min(number(node["ks_m"], "Schachtsohle"), elevation)
            node_rows.append(node)
        endpoint_ids.update((node_rows[0]["id"], node_rows[-1]["id"]))
        for index, (start, end) in enumerate(zip(node_rows, node_rows[1:])):
            length = math.dist((start["x_m"], start["y_m"]), (end["x_m"], end["y_m"]))
            pipe_id = _identity(factory(), "Rohridentität")
            pipe = {
                "schema": SCHEMA,
                "id": pipe_id,
                "network_id": str(options.get("network_id") or kind),
                "kind": kind,
                "name": str(options.get("name") or "").strip(),
                "start_id": start["id"],
                "end_id": end["id"],
                "dn_mm": dn_mm,
                "outside_diameter_mm": outside_diameter_mm,
                "outside_diameter_explicit": bool(
                    options.get("outside_diameter_explicit", "outside_diameter_mm" in options)),
                "wall_thickness_mm": number(
                    options.get("wall_thickness_mm", 10.0), "Rohrwandstärke"),
                "hollow_3d": bool(options.get("hollow_3d", True)),
                "material": material,
                "start_invert_m": elevations[index],
                "end_invert_m": elevations[index + 1],
                "length_m": length,
                "slope_percent": slope_percent(elevations[index], elevations[index + 1], length),
                "join_style": join_style,
                "fillet_radius_m": fillet_radius_m,
                "flow_arrow_scale": number(
                    options.get("flow_arrow_scale", 1.0), "Fließrichtungspfeil-Skalierung"),
                "label_layout": str(options.get("label_layout", "one_line")),
                "label_width_m": number(options.get("label_width_m", 0.0), "Beschriftungsbreite"),
                "draw_3d": bool(options.get("draw_3d", True)),
                "graphics_mode": str(options.get("graphics_mode", "double_line")),
                "line_type": int(options.get("line_type", 1)),
                "axis_line_type": int(options.get("axis_line_type", 2)),
                "color_override": copy.deepcopy(options.get("color_override")),
            }
            pipes.append(validate_pipe(pipe))
            degree[start["id"]] = degree.get(start["id"], 0) + 1
            degree[end["id"]] = degree.get(end["id"], 0) + 1
    for node in nodes:
        if node["id"] in existing_ids:
            continue
        node["visible"] = (shaft_mode == "all" or
                           shaft_mode == "endpoints" and
                           (node["id"] in endpoint_ids or degree.get(node["id"], 0) != 2))
        if node["visible"]:
            node["name"] = _shaft_name(kind, next_numbers)
            node["structure_type"] = "round"
        validate_shaft(node, allow_hidden=True)
    validate_network(pipes, nodes)
    return {"shafts": tuple(new_nodes), "pipes": tuple(pipes),
            "next_numbers": next_numbers}


def validate_pipe(value):
    if not isinstance(value, dict) or value.get("schema") != SCHEMA:
        raise SewerError("Unbekannte Kanalrohrdaten.")
    result = copy.deepcopy(value)
    result["id"] = _identity(result.get("id"), "Rohridentität")
    result["start_id"] = _identity(result.get("start_id"), "Anfangsschacht")
    result["end_id"] = _identity(result.get("end_id"), "Endschacht")
    if result["start_id"] == result["end_id"]:
        raise SewerError("Eine Kanalstrecke benötigt zwei verschiedene Knoten.")
    result["kind"] = _kind(result.get("kind"))
    result["dn_mm"] = _dn(result.get("dn_mm"))
    supplied_outside = result.get("outside_diameter_mm")
    result["outside_diameter_explicit"] = bool(
        result.get("outside_diameter_explicit", supplied_outside is not None))
    result["outside_diameter_mm"] = number(
        supplied_outside if supplied_outside is not None else result["dn_mm"],
        "Rohraußendurchmesser")
    if not 0.0 < result["outside_diameter_mm"] <= 20000.0:
        raise SewerError(
            "Der Rohraußendurchmesser muss größer als null und höchstens 20000 mm sein.")
    result["wall_thickness_mm"] = number(
        result.get("wall_thickness_mm", 10.0), "Rohrwandstärke")
    if not 0.0 < result["wall_thickness_mm"] < result["outside_diameter_mm"] * 0.5:
        raise SewerError(
            "Die Rohrwandstärke muss größer als null und kleiner als der halbe Außendurchmesser sein.")
    result["hollow_3d"] = bool(result.get("hollow_3d", True))
    result["material"] = _material(result.get("material"))
    for key, label in (("start_invert_m", "Anfangssohle"), ("end_invert_m", "Endsohle"),
                       ("length_m", "Länge")):
        result[key] = number(result.get(key), label)
    if result["length_m"] <= 1e-6:
        raise SewerError("Die Rohrlänge muss größer als null sein.")
    calculated = slope_percent(result["start_invert_m"], result["end_invert_m"], result["length_m"])
    if calculated < -1e-9:
        raise SewerError("Rohrsohlen widersprechen der Fließrichtung.")
    result["slope_percent"] = max(0.0, calculated)
    result["label_layout"] = str(result.get("label_layout", "one_line"))
    if result["label_layout"] not in ("one_line", "two_line"):
        raise SewerError("Ungültiges Beschriftungsformat.")
    result["label_width_m"] = number(result.get("label_width_m", 0.0), "Beschriftungsbreite")
    if not 0.0 <= result["label_width_m"] <= 100.0:
        raise SewerError("Beschriftungsbreite muss zwischen 0,00 m und 100,00 m liegen.")
    result["join_style"] = str(result.get("join_style", "round"))
    if result["join_style"] not in ("round", "bevel", "miter"):
        raise SewerError("Ungültige Eckverbindung.")
    result["fillet_radius_m"] = number(result.get("fillet_radius_m", 0.20), "Ausrundungsradius")
    if not 0.01 <= result["fillet_radius_m"] <= 20.0:
        raise SewerError("Ausrundungsradius muss zwischen 0,01 m und 20,00 m liegen.")
    result["flow_arrow_scale"] = number(
        result.get("flow_arrow_scale", 1.0), "Fließrichtungspfeil-Skalierung")
    if not 0.1 <= result["flow_arrow_scale"] <= 20.0:
        raise SewerError("Die Skalierung des Fließrichtungspfeils muss zwischen 0,10 und 20,00 liegen.")
    result["draw_3d"] = bool(result.get("draw_3d", True))
    result["graphics_mode"] = str(result.get("graphics_mode", "double_line"))
    if result["graphics_mode"] not in GRAPHICS_MODES:
        raise SewerError("Ungültige Kanal-Liniendarstellung.")
    try:
        result["line_type"] = int(result.get("line_type", 1))
    except (TypeError, ValueError) as error:
        raise SewerError("Ungültige Linienart der Einliniengrafik.") from error
    if not -32767 <= result["line_type"] <= 71:
        raise SewerError("Die Linienart der Einliniengrafik ist ungültig.")
    try:
        result["axis_line_type"] = int(result.get("axis_line_type", 2))
    except (TypeError, ValueError) as error:
        raise SewerError("Ungültige Linienart der Kanalachse.") from error
    if not -32767 <= result["axis_line_type"] <= 71:
        raise SewerError("Die Linienart der Kanalachse ist ungültig.")
    return result


def validate_shaft(value, allow_hidden=False):
    if not isinstance(value, dict) or value.get("schema") != SCHEMA:
        raise SewerError("Unbekannte Schachtdaten.")
    result = copy.deepcopy(value)
    result["id"] = _identity(result.get("id"), "Schachtidentität")
    result["kind"] = _kind(result.get("kind"))
    result["visible"] = bool(result.get("visible", True))
    raw_diameter = number(result.get("diameter_m", 0.0), "Schachtdurchmesser")
    default_type = "round" if result["visible"] and raw_diameter > 0.0 else "junction"
    result["structure_type"] = str(result.get("structure_type", default_type))
    if result["structure_type"] not in STRUCTURE_TYPES:
        raise SewerError("Unbekannter Kanalbauwerkstyp.")
    result["name"] = str(result.get("name") or "").strip()
    if (result["visible"] and (not result["name"] or len(result["name"]) > 64 or
                               any(character in result["name"] for character in "\r\n\t"))):
        raise SewerError("Schachtname muss aus 1 bis 64 druckbaren Zeichen bestehen.")
    result["note"] = str(result.get("note") or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    if len(result["note"]) > 512 or "\t" in result["note"]:
        raise SewerError("Der Schacht-Zusatztext ist ungültig oder zu lang.")
    if not result["visible"] and not allow_hidden:
        raise SewerError("Unsichtbarer Verbindungsknoten ist kein bearbeitbarer Schacht.")
    for key, label in (("x_m", "Schacht-X"), ("y_m", "Schacht-Y"),
                       ("kd_m", "Deckelhöhe"), ("ks_m", "Sohlhöhe"),
                       ("diameter_m", "Schachtdurchmesser")):
        result[key] = number(result.get(key), label)
    if result["diameter_m"] < 0.0:
        raise SewerError("Schachtdurchmesser darf nicht negativ sein.")
    result["construction_material"] = shaft_construction_material(
        result.get("construction_material", "PP"))
    default_wall = (DEFAULT_CONCRETE_WALL_THICKNESS_M
                    if result["construction_material"] == "concrete" else 0.0)
    result["wall_thickness_m"] = number(
        result.get("wall_thickness_m", default_wall), "Schachtwandstärke")
    if result["diameter_m"] <= 0.0 or result["construction_material"] == "PP":
        result["wall_thickness_m"] = 0.0
    elif not 0.01 <= result["wall_thickness_m"] <= 1.0:
        raise SewerError("Betonschacht-Wandstärke muss zwischen 0,01 m und 1,00 m liegen.")
    outline = result.get("special_outline_m", ())
    result["special_outline_m"] = (
        list(special_outline(outline)) if result["structure_type"] == "special" else [])
    result["cover_diameter_m"] = number(
        result.get("cover_diameter_m", 0.625), "Schachtdeckeldurchmesser")
    if result["structure_type"] in ("round", "special") and result["diameter_m"] > 0.0:
        if result["cover_diameter_m"] < 0.1:
            raise SewerError("Schachtdeckeldurchmesser muss mindestens 0,10 m betragen.")
        # A smaller shaft must remain directly editable.  Adapt the cover to
        # the shaft instead of rejecting an otherwise valid diameter change.
        result["cover_diameter_m"] = min(
            result["cover_diameter_m"], shaft_outer_diameter_m(result))
    result["cover_symbol"] = str(result.get("cover_symbol") or "").strip()
    if len(result["cover_symbol"]) > 255 or any(
            character in result["cover_symbol"] for character in "\r\n\t"):
        raise SewerError("Ungültiger Name des Schachtdeckelsymbols.")
    result["cover_placement"] = str(result.get("cover_placement", "auto"))
    if result["cover_placement"] not in ("auto", "center"):
        raise SewerError("Ungültige Lage des Schachtdeckels.")
    result["cover_rotation_deg"] = number(
        result.get("cover_rotation_deg", 0.0), "Schachtdeckeldrehung") % 360.0
    result["terminal_symbol"] = str(result.get("terminal_symbol") or "").strip()
    if len(result["terminal_symbol"]) > 255 or any(
            character in result["terminal_symbol"] for character in "\r\n\t"):
        raise SewerError("Ungültiger Name des Bodenablaufsymbols.")
    result["terminal_symbol_has_3d"] = bool(result.get("terminal_symbol_has_3d", False))
    result["terminal_width_m"] = number(
        result.get("terminal_width_m", 0.30), "Breite des Bodenablaufs")
    result["terminal_depth_m"] = number(
        result.get("terminal_depth_m", 0.60), "Tiefe des Bodenablaufs")
    if not 0.05 <= result["terminal_width_m"] <= 5.0:
        raise SewerError("Die Breite des Bodenablaufs muss zwischen 0,05 m und 5,00 m liegen.")
    if not 0.05 <= result["terminal_depth_m"] <= 10.0:
        raise SewerError("Die Tiefe des Bodenablaufs muss zwischen 0,05 m und 10,00 m liegen.")
    stub = result.get("stub")
    if result["structure_type"] == "stub":
        if not isinstance(stub, dict):
            raise SewerError("Daten des Kanalstutzens fehlen.")
        main_start_id = str(stub.get("main_start_id") or "").strip()
        main_end_id = str(stub.get("main_end_id") or "").strip()
        main_pipe_ids = tuple(str(value or "").strip()
                              for value in stub.get("main_pipe_ids", ()))
        if any(not value for value in main_pipe_ids):
            raise SewerError("Ungültige Hauptleitungsreferenz am Kanalstutzen.")
        station_enabled = bool(stub.get(
            "station_enabled", bool(main_start_id and main_end_id and main_pipe_ids)))
        if station_enabled and (not main_start_id or not main_end_id or len(main_pipe_ids) != 2):
            raise SewerError("Die Stationierung des Kanalstutzens ist nicht vollständig verknüpft.")
        station_m = stub.get("station_m")
        if station_m is not None:
            station_m = number(station_m, "Station des Kanalstutzens")
            if station_m < 0.0:
                raise SewerError("Die Station des Kanalstutzens darf nicht negativ sein.")
        station_basis = str(stub.get("station_basis") or "")
        if station_basis not in ("", "lower_invert", "equal_invert_end"):
            raise SewerError("Ungültige Bezugsregel der Stutzenstationierung.")
        station_zero_name = str(stub.get("station_zero_name") or "").strip()
        if len(station_zero_name) > 64 or any(
                character in station_zero_name for character in "\r\n\t"):
            raise SewerError("Ungültige Bezeichnung des Stationierungsnullpunkts.")
        result["stub"] = {
            "alignment": str(stub.get("alignment", "invert")),
            "main_dn_mm": _dn(stub.get("main_dn_mm")),
            "branch_dn_mm": _dn(stub.get("branch_dn_mm")),
            "connection_invert_m": number(stub.get("connection_invert_m"), "Anschlusshöhe"),
            "station_enabled": station_enabled,
            "main_start_id": main_start_id,
            "main_end_id": main_end_id,
            "main_pipe_ids": list(main_pipe_ids),
            "station_m": station_m,
            "station_zero_id": str(stub.get("station_zero_id") or "").strip(),
            "station_zero_name": station_zero_name,
            "station_equal_inverts": bool(stub.get("station_equal_inverts", False)),
            "station_basis": station_basis,
        }
        connection_alignment_label(result["stub"]["alignment"])
    else:
        result["stub"] = None
    drops = []
    for value in result.get("drops", ()):
        if not isinstance(value, dict):
            raise SewerError("Ungültige Absturzdaten.")
        upper = number(value.get("upper_invert_m"), "Höhe der ankommenden Leitung")
        lower = number(value.get("lower_invert_m"), "Unterkante der Absturzleitung")
        if upper + 1e-9 < lower:
            raise SewerError("Die obere Absturzhöhe muss über der unteren liegen.")
        drops.append({"pipe_id": _identity(value.get("pipe_id"), "Haltung am Absturz"),
                      "upper_invert_m": upper, "lower_invert_m": lower})
    result["drops"] = drops
    if result["kd_m"] < result["ks_m"]:
        raise SewerError("Deckelhöhe KD muss über oder auf der Sohlhöhe KS liegen.")
    return result


def round_join_geometry(first_direction, second_direction, radius, half_width,
                        maximum_step_degrees=10.0):
    """Return a tangent circular band between two outward junction rays.

    Coordinates and radii may use any one consistent unit.  ``None`` means
    that the two rays are already straight and need no separate bend object.
    The requested radius describes the pipe centre line and is enlarged only
    when required to keep the inner boundary geometrically valid.
    """
    radius = number(radius, "Ausrundungsradius")
    half_width = number(half_width, "Rohrhalbe")
    maximum_step_degrees = number(maximum_step_degrees, "Bogenauflösung")
    if radius <= 0.0 or half_width <= 0.0 or not 1.0 <= maximum_step_degrees <= 45.0:
        raise SewerError("Ungültige Geometrie für den Leitungszusammenschluss.")

    def unit(value):
        if not isinstance(value, (tuple, list)) or len(value) != 2:
            raise SewerError("Ungültige Richtung am Leitungszusammenschluss.")
        x = number(value[0], "Richtungs-X")
        y = number(value[1], "Richtungs-Y")
        length = math.hypot(x, y)
        if length <= 1e-9:
            raise SewerError("Leitungszusammenschluss besitzt eine Richtung ohne Länge.")
        return x / length, y / length

    first = unit(first_direction)
    second = unit(second_direction)
    dot = max(-1.0, min(1.0, first[0] * second[0] + first[1] * second[1]))
    angle = math.acos(dot)
    sweep = math.pi - angle
    if sweep <= 1e-7:
        return None
    if angle <= math.radians(1.0):
        raise SewerError("Leitungen mit nahezu gleicher Richtung können nicht ausgerundet werden.")

    centerline_radius = max(radius, half_width * 1.001)
    tangent = centerline_radius / math.tan(angle * 0.5)
    bisector = first[0] + second[0], first[1] + second[1]
    bisector_length = math.hypot(*bisector)
    if bisector_length <= 1e-9:
        return None
    center_distance = centerline_radius / math.sin(angle * 0.5)
    center = (bisector[0] / bisector_length * center_distance,
              bisector[1] / bisector_length * center_distance)
    first_tangent = first[0] * tangent, first[1] * tangent
    first_angle = math.atan2(first_tangent[1] - center[1],
                             first_tangent[0] - center[0])
    turn = -1.0 if first[0] * second[1] - first[1] * second[0] > 0.0 else 1.0
    steps = max(2, int(math.ceil(math.degrees(sweep) / maximum_step_degrees)))
    angles = tuple(first_angle + turn * sweep * index / steps
                   for index in range(steps + 1))

    def arc(boundary_radius):
        return tuple((center[0] + math.cos(value) * boundary_radius,
                      center[1] + math.sin(value) * boundary_radius)
                     for value in angles)

    outer = arc(centerline_radius + half_width)
    inner = arc(centerline_radius - half_width)
    centerline = arc(centerline_radius)
    return {
        "trim": tangent,
        "radius": centerline_radius,
        "center": center,
        "centerline": centerline,
        "outer": outer,
        "inner": inner,
        "fill": outer + tuple(reversed(inner)),
    }


def validate_network(pipes, shafts):
    pipes = tuple(validate_pipe(value) for value in pipes)
    shafts = tuple(validate_shaft(value, allow_hidden=True) for value in shafts)
    shaft_ids = [value["id"] for value in shafts]
    if len(shaft_ids) != len(set(shaft_ids)):
        raise SewerError("Schachtidentitäten sind doppelt vorhanden.")
    names = [value["name"] for value in shafts if value["visible"]]
    if len(names) != len(set(names)):
        raise SewerError("Schachtbezeichnungen sind doppelt vorhanden.")
    known = set(shaft_ids)
    for pipe in pipes:
        if pipe["start_id"] not in known or pipe["end_id"] not in known:
            raise SewerError("Eine Kanalstrecke besitzt ein nicht verbundenes Ende.")
    return pipes, shafts


def update_pipe(pipe, length_m, changes):
    result = validate_pipe(pipe)
    result.update({key: copy.deepcopy(value) for key, value in changes.items()
                   if key not in ("start_invert_m", "end_invert_m", "slope_percent")})
    length = number(length_m, "Länge")
    mode = str(changes.get("calculation_mode", "end"))
    default_reference = result["end_invert_m"] if mode == "start" else result["start_invert_m"]
    start = number(changes.get("start_invert_m", default_reference),
                   "Endsohle" if mode == "start" else "Anfangssohle")
    value = changes.get("calculation_value", result["end_invert_m"])
    elevations, _ = elevation_series(((0.0, 0.0), (length, 0.0)), start, mode, value)
    result.update(start_invert_m=elevations[0], end_invert_m=elevations[1], length_m=length)
    return validate_pipe(result)


def reverse_pipe(pipe):
    result = validate_pipe(pipe)
    result["start_id"], result["end_id"] = result["end_id"], result["start_id"]
    result["start_invert_m"], result["end_invert_m"] = (
        result["end_invert_m"], result["start_invert_m"])
    if result["start_invert_m"] + 1e-9 < result["end_invert_m"]:
        raise SewerError("Nach dem Richtungswechsel steigt das Rohr in Fließrichtung an.")
    return validate_pipe(result)


def project_on_pipe(start_xy, end_xy, point_xy, tolerance_m=0.25):
    """Return station fraction and projected point for an interior split."""
    start = point(start_xy)
    end = point(end_xy)
    target = point(point_xy)
    dx, dy = end[0] - start[0], end[1] - start[1]
    squared = dx * dx + dy * dy
    if squared <= 1e-12:
        raise SewerError("Die Kanalstrecke besitzt keine teilbare Länge.")
    fraction = ((target[0] - start[0]) * dx + (target[1] - start[1]) * dy) / squared
    projected = start[0] + fraction * dx, start[1] + fraction * dy
    if math.dist(target, projected) > number(tolerance_m, "Fangtoleranz"):
        raise SewerError("Der Teilungspunkt liegt nicht auf der gewählten Kanalstrecke.")
    if not 1e-4 < fraction < 1.0 - 1e-4:
        raise SewerError("Die Teilung muss innerhalb der Kanalstrecke liegen.")
    return fraction, projected


def split_pipe(pipe, new_shaft_id, fraction, identity_factory=None):
    """Split a pipe into two direction-preserving pipes at an interpolated invert."""
    original = validate_pipe(pipe)
    ratio = number(fraction, "Teilungsposition")
    if not 1e-4 < ratio < 1.0 - 1e-4:
        raise SewerError("Die Teilung muss innerhalb der Kanalstrecke liegen.")
    node_id = _identity(new_shaft_id, "Neuer Schacht")
    factory = identity_factory or (lambda: str(uuid.uuid4()))
    middle = original["start_invert_m"] + (
        original["end_invert_m"] - original["start_invert_m"]) * ratio
    first = copy.deepcopy(original)
    first.update(id=_identity(factory(), "Rohridentität"), end_id=node_id,
                 end_invert_m=middle, length_m=original["length_m"] * ratio)
    second = copy.deepcopy(original)
    second.update(id=_identity(factory(), "Rohridentität"), start_id=node_id,
                  start_invert_m=middle, length_m=original["length_m"] * (1.0 - ratio))
    return validate_pipe(first), validate_pipe(second)


def merge_pipes(first_pipe, second_pipe, shared_shaft_id, identity_factory=None):
    """Merge two pipes that meet in flow direction at one shared node."""
    first = validate_pipe(first_pipe)
    second = validate_pipe(second_pipe)
    shared = _identity(shared_shaft_id, "Gemeinsamer Schacht")
    if first["end_id"] == shared and second["start_id"] == shared:
        upstream, downstream = first, second
    elif second["end_id"] == shared and first["start_id"] == shared:
        upstream, downstream = second, first
    else:
        raise SewerError("Die Rohre müssen in Fließrichtung an einem gemeinsamen Knoten anschließen.")
    for key, label in (("kind", "Kanalart"), ("dn_mm", "DN"),
                       ("material", "Material"), ("draw_3d", "3D-Darstellung"),
                       ("wall_thickness_mm", "Rohrwandstärke"),
                       ("hollow_3d", "hohle 3D-Darstellung"),
                       ("join_style", "Eckverbindung"),
                       ("fillet_radius_m", "Ausrundungsradius")):
        if upstream[key] != downstream[key]:
            raise SewerError("Zum Vereinigen muss %s beider Rohre übereinstimmen." % label)
    factory = identity_factory or (lambda: str(uuid.uuid4()))
    result = copy.deepcopy(upstream)
    result.update(id=_identity(factory(), "Rohridentität"), end_id=downstream["end_id"],
                  end_invert_m=downstream["end_invert_m"],
                  length_m=upstream["length_m"] + downstream["length_m"])
    return validate_pipe(result)


def format_number(value, decimals):
    return (("%%.%df" % int(decimals)) % number(value, "Zahl")).replace(".", ",")


def pipe_label(pipe, preferences):
    pipe = validate_pipe(pipe)
    slope = format_number(pipe["slope_percent"], preferences["slope_decimals"])
    length = format_number(pipe["length_m"], preferences["length_decimals"])
    first = "%s %% | %s m" % (slope, length)
    second = "DN %d %s" % (pipe["dn_mm"], pipe["material"])
    return first + ("\n" if pipe["label_layout"] == "two_line" else " | ") + second


def shaft_label(shaft, endpoint_rows, preferences):
    shaft = validate_shaft(shaft, allow_hidden=True)
    if not shaft["visible"]:
        return ""
    def height(value):
        return format_number(value, preferences["height_decimals"])
    detailed = bool(endpoint_rows and isinstance(endpoint_rows[0], dict))
    if detailed:
        rows = []
        for index, value in enumerate(endpoint_rows, 1):
            role = value.get("role")
            if role not in ("in", "out"):
                raise SewerError("Ungültige Anschlussart in der Schachtbeschriftung.")
            tag = str(value.get("tag") or ("Z" if role == "in" else "A") + str(index))
            rows.append({
                "tag": tag,
                "role": role,
                "role_label": "Zulauf" if role == "in" else "Ablauf",
                "height": number(value.get("invert_m"), "Anschlusshöhe"),
                "dn_mm": _dn(value.get("dn_mm")),
                "material": _material(value.get("material")),
                "bearing_deg": number(value.get("bearing_deg", 0.0), "Anschlusswinkel") % 360.0,
            })
        incoming = [row["height"] for row in rows if row["role"] == "in"]
        outgoing = [row["height"] for row in rows if row["role"] == "out"]
    else:
        rows = []
        incoming = sorted({round(row[1], 9) for row in endpoint_rows if row[0] == "in"}, reverse=True)
        outgoing = sorted({round(row[1], 9) for row in endpoint_rows if row[0] == "out"}, reverse=True)
    if shaft["structure_type"] == "stub":
        stub = shaft["stub"]
        lines = ["Stutzen DN %d" % stub["branch_dn_mm"],
                 connection_alignment_label(stub["alignment"]),
                 "Anschluss KS = %s m" % height(stub["connection_invert_m"])]
        if stub.get("station_enabled") and stub.get("station_m") is not None:
            zero = stub.get("station_zero_name") or stub.get("station_zero_id") or "Endschacht"
            station = "Station = %s m ab %s" % (
                format_number(stub["station_m"], preferences["length_decimals"]), zero)
            if stub.get("station_equal_inverts"):
                station += " (gleichsohlig: Fließ-/Objektrichtung)"
            lines.append(station)
        return "\n".join(lines)
    if shaft["structure_type"] == "floor_drain":
        return "%s\nOK = %s m\nUK = %s m" % (
            shaft["name"], height(shaft["kd_m"]), height(shaft["ks_m"]))
    if shaft["structure_type"] == "house":
        return "%s\nAnschlusshöhe = %s m" % (shaft["name"], height(shaft["ks_m"]))
    if shaft["diameter_m"] == 0.0:
        if detailed:
            if len(rows) == 1:
                return "KS = %s m" % height(rows[0]["height"])
            return "\n".join(
                "%s %s | KS = %s m" %
                (row["tag"], row["role_label"], height(row["height"]))
                for row in rows)
        values = incoming + [value for value in outgoing if value not in incoming]
        return "KS = %s m" % height(min(values) if values else shaft["ks_m"])
    depth = format_number(shaft["kd_m"] - shaft["ks_m"], preferences["length_decimals"])
    lines = [shaft["name"]]
    if shaft["note"]:
        lines.extend(shaft["note"].splitlines())
    if shaft["structure_type"] != "special":
        diameter = format_number(shaft["diameter_m"], preferences["length_decimals"])
        lines.append("Bauart = %s" % shaft_construction_material_label(
            shaft["construction_material"]))
        if shaft["construction_material"] == "concrete":
            wall = format_number(shaft["wall_thickness_m"], preferences["length_decimals"])
            outside = format_number(shaft_outer_diameter_m(shaft), preferences["length_decimals"])
            lines.append("Ø innen = %s m | Wand = %s m | Ø außen = %s m" %
                         (diameter, wall, outside))
        else:
            lines.append("Ø = %s m" % diameter)
    lines.append("KD = %s m" % height(shaft["kd_m"]))
    if detailed:
        for row in rows:
            lines.append("%s %s | KS = %s m | DN %d %s | %s°" %
                         (row["tag"], row["role_label"], height(row["height"]),
                          row["dn_mm"], row["material"],
                          format_number(row["bearing_deg"], 1)))
    elif incoming and outgoing and (len(incoming) > 1 or len(outgoing) > 1 or incoming != outgoing):
        lines.append("KS Zulauf = %s m" % " / ".join(height(value) for value in incoming))
        lines.append("KS Ablauf = %s m" % " / ".join(height(value) for value in outgoing))
    else:
        values = incoming + [value for value in outgoing if value not in incoming]
        lines.append("KS = %s m" % height(min(values) if values else shaft["ks_m"]))
    lines.append("Tiefe = %s m" % depth)
    for drop in shaft.get("drops", ()):
        lines.append("Absturz OK = %s m / UK = %s m" % (
            height(drop["upper_invert_m"]), height(drop["lower_invert_m"])))
    return "\n".join(lines)
