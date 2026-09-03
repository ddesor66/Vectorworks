# -*- coding: utf-8 -*-
"""Pure utility-route validation, offset, rounding and height rules."""
from __future__ import absolute_import

import copy
import math
import uuid


SCHEMA = 1
UTILITY_TYPES = ("Trinkwasser", "Strom", "Nah-/Fernwärme", "Gas")
TYPE_TOKENS = {
    "Trinkwasser": "Trinkwasser",
    "Strom": "Strom",
    "Nah-/Fernwärme": "Nah-Fernwaerme",
    "Gas": "Gas",
}
GRAPHICS_MODES = ("single_line", "double_line")
LABEL_LAYOUTS = ("one_line", "two_line")
AXIS_REFERENCES = ("left", "center", "right")
ELEVATION_MODES = ("fixed", "surface_cover")
DEFAULT_MATERIALS = ("PE", "PVC", "GGG", "Stahl", "Kabelschutzrohr")
ROUTE_PREFIX = "PD-LEI-R-"
MAX_LABEL_COUNT = 10000


class UtilityError(ValueError):
    pass


def number(value, label):
    try:
        result = float(value)
    except (TypeError, ValueError) as error:
        raise UtilityError("%s ist keine gültige Zahl." % label) from error
    if not math.isfinite(result):
        raise UtilityError("%s muss endlich sein." % label)
    return result


def integer(value, label, low, high):
    result = number(value, label)
    if not result.is_integer() or not low <= result <= high:
        raise UtilityError("%s muss eine ganze Zahl zwischen %d und %d sein." %
                           (label, low, high))
    return int(result)


def point(value):
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        raise UtilityError("Ungültiger Leitungspunkt.")
    return number(value[0], "X-Koordinate"), number(value[1], "Y-Koordinate")


def path(points):
    result = tuple(point(value) for value in points)
    if len(result) < 2:
        raise UtilityError("Eine Leitungstrasse benötigt mindestens zwei Punkte.")
    for first, second in zip(result, result[1:]):
        if math.dist(first, second) <= 1e-6:
            raise UtilityError("Aufeinanderfolgende Leitungspunkte müssen verschieden sein.")
    for previous, corner, following in zip(result, result[1:], result[2:]):
        incoming = corner[0] - previous[0], corner[1] - previous[1]
        outgoing = following[0] - corner[0], following[1] - corner[1]
        divisor = math.hypot(*incoming) * math.hypot(*outgoing)
        cross = abs(_cross(incoming, outgoing)) / divisor
        dot = (incoming[0] * outgoing[0] + incoming[1] * outgoing[1]) / divisor
        if cross <= 1e-10 and dot < 0.0:
            raise UtilityError(
                "Eine Leitungstrasse darf am selben Winkelpunkt keine Kehrtwende bilden.")
    return result


def stations(points):
    values = path(points)
    result = [0.0]
    for first, second in zip(values, values[1:]):
        result.append(result[-1] + math.dist(first, second))
    return tuple(result)


def utility_type(value):
    result = str(value or "").strip()
    if (not result or len(result) > 64 or
            any(char in result for char in "\r\n\t|;")):
        raise UtilityError("Ungültiger Leitungstyp.")
    class_token(result, "Leitungstyp")
    return result


def nominal_diameters(values, count):
    count = integer(count, "Leitungsanzahl", 1, 50)
    if isinstance(values, str):
        raw = [part.strip() for part in values.replace(",", ";").split(";") if part.strip()]
    elif isinstance(values, (int, float)):
        raw = [values]
    else:
        try:
            raw = list(values or ())
        except TypeError as error:
            raise UtilityError("Ungültige Nennweiten.") from error
    result = tuple(integer(value, "Nennweite", 1, 10000) for value in raw)
    if len(result) == 1:
        return result * count
    if len(result) != count:
        raise UtilityError(
            "Für mehrere Leitungen ist entweder eine gemeinsame Nennweite oder genau eine Nennweite je Leitung anzugeben.")
    return result


def outside_diameters(values, nominal_values, count, explicit=None):
    """Normalize real outside diameters without guessing a material table.

    When no explicit outside diameter is supplied, DN is retained as a
    conservative geometric fallback and the returned flag is ``False``.
    """
    count = integer(count, "Leitungsanzahl", 1, 50)
    dns = nominal_diameters(nominal_values, count)
    is_explicit = values is not None if explicit is None else bool(explicit)
    if not is_explicit:
        return tuple(float(value) for value in dns), False
    if isinstance(values, str):
        # Semicolons separate parallel lines; a comma inside one token is the
        # German decimal separator (for example 114,3 mm).
        raw = [part.strip().replace(",", ".")
               for part in values.split(";") if part.strip()]
    elif isinstance(values, (int, float)):
        raw = [values]
    else:
        try:
            raw = list(values)
        except TypeError as error:
            raise UtilityError("Ungültige Rohraußendurchmesser.") from error
    normalized = tuple(number(value, "Rohraußendurchmesser") for value in raw)
    if any(not 0.0 < value <= 20000.0 for value in normalized):
        raise UtilityError(
            "Rohraußendurchmesser müssen größer als null und höchstens 20000 mm sein.")
    if len(normalized) == 1:
        return normalized * count, True
    if len(normalized) != count:
        raise UtilityError(
            "Für mehrere Leitungen ist entweder ein gemeinsamer Außendurchmesser oder genau ein Außendurchmesser je Leitung anzugeben.")
    return normalized, True


def class_token(value, label):
    result = str(value or "").strip().replace("/", "-").replace("\\", "-")
    result = "-".join(part for part in result.replace(" ", "-").split("-") if part)
    if not result or len(result) > 64 or any(char in result for char in "\r\n\t:"):
        raise UtilityError("%s ist kein gültiger Klassenbestandteil." % label)
    return result


def line_class_name(prefix, type_value, dn_mm, suffix=""):
    suffix = str(suffix or "")
    if (len(suffix) > 24 or
            any(char in suffix for char in "\r\n\t:/\\")):
        raise UtilityError("Der Klassenanhang ist ungültig.")
    return "%s-%s-DN%d%s" % (
        class_token(prefix, "Leitungs-Klassenpräfix"),
        TYPE_TOKENS.get(utility_type(type_value),
                        class_token(type_value, "Leitungstyp")),
        integer(dn_mm, "Nennweite", 1, 10000), suffix)


def material(value):
    result = str(value or "").strip()
    if not result or len(result) > 48 or any(char in result for char in "\r\n\t|;"):
        raise UtilityError("Ungültiges Leitungsmaterial.")
    return result


def route_offsets(count, spacing_m, reference):
    count = integer(count, "Leitungsanzahl", 1, 50)
    spacing = number(spacing_m, "Leitungsabstand")
    if spacing < 0.0:
        raise UtilityError("Der Leitungsabstand darf nicht negativ sein.")
    if count > 1 and spacing <= 0.0:
        raise UtilityError("Der Leitungsabstand muss größer als null sein.")
    reference = str(reference or "center")
    if reference not in AXIS_REFERENCES:
        raise UtilityError("Unbekannte Lage der gezeichneten Trassenachse.")
    if reference == "left":
        return tuple(-index * spacing for index in range(count))
    if reference == "right":
        return tuple((count - 1 - index) * spacing for index in range(count))
    middle = (count - 1) * 0.5
    return tuple((middle - index) * spacing for index in range(count))


def _cross(first, second):
    return first[0] * second[1] - first[1] * second[0]


def _intersection(first, direction_first, second, direction_second):
    divisor = _cross(direction_first, direction_second)
    if abs(divisor) <= 1e-10:
        return None
    delta = second[0] - first[0], second[1] - first[1]
    factor = _cross(delta, direction_second) / divisor
    return first[0] + direction_first[0] * factor, first[1] + direction_first[1] * factor


def offset_path(points, offset_m):
    values = path(points)
    offset = number(offset_m, "Trassenversatz")
    if abs(offset) <= 1e-12:
        return values
    directions = []
    normals = []
    for first, second in zip(values, values[1:]):
        dx, dy = second[0] - first[0], second[1] - first[1]
        length = math.hypot(dx, dy)
        direction = dx / length, dy / length
        directions.append(direction)
        normals.append((-direction[1], direction[0]))
    result = [(values[0][0] + normals[0][0] * offset,
               values[0][1] + normals[0][1] * offset)]
    for index in range(1, len(values) - 1):
        first_origin = (values[index][0] + normals[index - 1][0] * offset,
                        values[index][1] + normals[index - 1][1] * offset)
        second_origin = (values[index][0] + normals[index][0] * offset,
                         values[index][1] + normals[index][1] * offset)
        joined = _intersection(first_origin, directions[index - 1],
                               second_origin, directions[index])
        if joined is None:
            joined = ((first_origin[0] + second_origin[0]) * 0.5,
                      (first_origin[1] + second_origin[1]) * 0.5)
        miter = math.dist(joined, values[index])
        if miter > abs(offset) * 10.0:
            raise UtilityError(
                "Der Trassenversatz passt an einem engen Winkelpunkt nicht in die angrenzenden Abschnitte.")
        result.append(joined)
    result.append((values[-1][0] + normals[-1][0] * offset,
                   values[-1][1] + normals[-1][1] * offset))
    if any(math.dist(first, second) <= 1e-6
           for first, second in zip(result, result[1:])):
        raise UtilityError(
            "Der Trassenversatz lässt an einem Winkelpunkt einen Leitungsabschnitt zusammenfallen.")
    return tuple(result)


def rounded_path(points, radius_m, enabled=True, maximum_step_degrees=10.0):
    """Return points and original-path stations for tangent circular corners."""
    values = path(points)
    control_stations = stations(values)
    if not enabled or len(values) < 3:
        return values, control_stations
    radius = number(radius_m, "Ausrundungsradius")
    step = number(maximum_step_degrees, "Bogenauflösung")
    if radius <= 0.0 or not 1.0 <= step <= 45.0:
        raise UtilityError("Ausrundungsradius und Bogenauflösung sind ungültig.")
    corners = [None] * len(values)
    for index in range(1, len(values) - 1):
        previous, corner, following = values[index - 1], values[index], values[index + 1]
        to_previous = previous[0] - corner[0], previous[1] - corner[1]
        to_following = following[0] - corner[0], following[1] - corner[1]
        before = math.hypot(*to_previous)
        after = math.hypot(*to_following)
        u_previous = to_previous[0] / before, to_previous[1] / before
        u_following = to_following[0] / after, to_following[1] / after
        dot = max(-1.0, min(1.0, u_previous[0] * u_following[0] +
                            u_previous[1] * u_following[1]))
        interior = math.acos(dot)
        turn = _cross((-u_previous[0], -u_previous[1]), u_following)
        if abs(math.pi - interior) <= 1e-7 or abs(turn) <= 1e-10:
            continue
        if interior <= math.radians(2.0):
            raise UtilityError("Ein Winkelpunkt ist für eine Ausrundung zu spitz.")
        tangent = radius / math.tan(interior * 0.5)
        if tangent >= before - 1e-9 or tangent >= after - 1e-9:
            raise UtilityError(
                "Der Ausrundungsradius %.3f m passt nicht in die angrenzenden Leitungsabschnitte." % radius)
        start = (corner[0] + u_previous[0] * tangent,
                 corner[1] + u_previous[1] * tangent)
        end = (corner[0] + u_following[0] * tangent,
               corner[1] + u_following[1] * tangent)
        bisector = (u_previous[0] + u_following[0],
                    u_previous[1] + u_following[1])
        bisector_length = math.hypot(*bisector)
        center_distance = radius / math.sin(interior * 0.5)
        center = (corner[0] + bisector[0] / bisector_length * center_distance,
                  corner[1] + bisector[1] / bisector_length * center_distance)
        start_angle = math.atan2(start[1] - center[1], start[0] - center[0])
        end_angle = math.atan2(end[1] - center[1], end[0] - center[0])
        direction = 1.0 if turn > 0.0 else -1.0
        sweep = (end_angle - start_angle) % (2.0 * math.pi)
        if direction < 0.0:
            sweep = -((start_angle - end_angle) % (2.0 * math.pi))
        if abs(sweep) > math.pi + 1e-7:
            sweep -= math.copysign(2.0 * math.pi, sweep)
        steps = max(2, int(math.ceil(abs(math.degrees(sweep)) / step)))
        corners[index] = {
            "tangent": tangent,
            "start": start,
            "end": end,
            "center": center,
            "start_angle": start_angle,
            "sweep": sweep,
            "steps": steps,
        }

    for segment_index, (first, second) in enumerate(zip(values, values[1:])):
        cut_at_start = (corners[segment_index] or {}).get("tangent", 0.0)
        cut_at_end = (corners[segment_index + 1] or {}).get("tangent", 0.0)
        segment_length = math.dist(first, second)
        if cut_at_start + cut_at_end >= segment_length - 1e-9:
            raise UtilityError(
                "Benachbarte Ausrundungen überdecken den dazwischenliegenden Leitungsabschnitt.")

    result = [values[0]]
    result_stations = [0.0]
    for index in range(1, len(values) - 1):
        corner_data = corners[index]
        if corner_data is None:
            result.append(values[index])
            result_stations.append(control_stations[index])
            continue
        tangent = corner_data["tangent"]
        start = corner_data["start"]
        start_station = control_stations[index] - tangent
        end_station = control_stations[index] + tangent
        if math.dist(result[-1], start) > 1e-9:
            result.append(start)
            result_stations.append(start_station)
        center = corner_data["center"]
        start_angle = corner_data["start_angle"]
        sweep = corner_data["sweep"]
        steps = corner_data["steps"]
        for arc_index in range(1, steps + 1):
            fraction = arc_index / float(steps)
            angle = start_angle + sweep * fraction
            result.append((center[0] + math.cos(angle) * radius,
                           center[1] + math.sin(angle) * radius))
            result_stations.append(start_station + (end_station - start_station) * fraction)
    result.append(values[-1])
    result_stations.append(control_stations[-1])
    return tuple(result), tuple(result_stations)


def initial_heights(points, start_height_m, slope_percent):
    start = number(start_height_m, "Anfangshöhe")
    slope = number(slope_percent, "Gefälle")
    return tuple(start - station * slope / 100.0 for station in stations(points))


def control_route_paths(route):
    value = validate_route(route)
    return tuple(offset_path(value["points_m"], offset)
                 for offset in route_offsets(
                     value["count"], value["spacing_m"], value["axis_reference"]))


def render_route_paths(route):
    """Return concentric display paths and reference stations per line.

    The common reference axis is rounded first. Offsetting that result keeps
    bundled lines parallel through bends; rounding each offset control path
    separately with one radius would not.
    """
    value = validate_route(route)
    offsets = route_offsets(
        value["count"], value["spacing_m"], value["axis_reference"])
    if value["round_corners"]:
        for previous, corner, following in zip(
                value["points_m"], value["points_m"][1:], value["points_m"][2:]):
            incoming = corner[0] - previous[0], corner[1] - previous[1]
            outgoing = following[0] - corner[0], following[1] - corner[1]
            turn = _cross(incoming, outgoing)
            relative_turn = turn / (math.hypot(*incoming) * math.hypot(*outgoing))
            if abs(relative_turn) <= 1e-10:
                continue
            turn_sign = 1.0 if relative_turn > 0.0 else -1.0
            for line_index, offset in enumerate(offsets):
                effective_radius = value["fillet_radius_m"] - turn_sign * offset
                if effective_radius <= 1e-6:
                    raise UtilityError(
                        "Der Ausrundungsradius ist für die innenliegende Parallelleitung zu klein.")
                if value["graphics_mode"] == "double_line" or value["draw_3d"]:
                    pipe_radius = value["outside_diameters_mm"][line_index] / 2000.0
                    if effective_radius <= pipe_radius + 1e-6:
                        raise UtilityError(
                            "Der Ausrundungsradius muss größer als der Rohrradius aus dem "
                            "Außendurchmesser sein.")
    reference_points, reference_stations = rounded_path(
        value["points_m"], value["fillet_radius_m"], value["round_corners"])
    return tuple((offset_path(reference_points, offset), reference_stations)
                 for offset in offsets)


def densify_path(points, station_values=None, interval_m=1.0,
                 maximum_points=100000):
    """Densify a path while preserving its supplied engineering stations."""
    values = path(points)
    interval = number(interval_m, "DGM-Prüfabstand")
    if interval <= 0.0:
        raise UtilityError("Der DGM-Prüfabstand muss größer als null sein.")
    maximum = integer(maximum_points, "Maximale DGM-Stützpunktanzahl", 2, 1000000)
    if station_values is None:
        source_stations = stations(values)
    else:
        try:
            source_stations = tuple(number(row, "Station") for row in station_values)
        except TypeError as error:
            raise UtilityError("Die DGM-Stationen sind unvollständig.") from error
        if len(source_stations) != len(values):
            raise UtilityError("Die DGM-Stationen passen nicht zur Trassengeometrie.")
        for first, second in zip(source_stations, source_stations[1:]):
            if second - first <= 1e-9:
                raise UtilityError("Die DGM-Stationen müssen streng ansteigen.")
    dense_points = [values[0]]
    dense_stations = [source_stations[0]]
    for index, (first, second) in enumerate(zip(values, values[1:])):
        length = math.dist(first, second)
        divisions = max(1, int(math.ceil(length / interval)))
        if len(dense_points) + divisions > maximum:
            raise UtilityError(
                "Die Leitungstrasse würde mehr als %d DGM-Stützpunkte erzeugen." % maximum)
        for step in range(1, divisions + 1):
            fraction = step / float(divisions)
            dense_points.append((first[0] + (second[0] - first[0]) * fraction,
                                 first[1] + (second[1] - first[1]) * fraction))
            dense_stations.append(
                source_stations[index] +
                (source_stations[index + 1] - source_stations[index]) * fraction)
    return tuple(dense_points), tuple(dense_stations)


def surface_cover_heights(surface_elevations_m, dn_mm, cover_depth_m,
                          outside_diameter_mm=None):
    """Pipe-axis heights from terrain and cover measured to outside crown.

    ``dn_mm`` remains the backwards-compatible fallback. Where nominal and
    outside diameter differ, callers must pass the real outside diameter.
    """
    integer(dn_mm, "Nennweite", 1, 10000)
    outside = dn_mm if outside_diameter_mm is None else outside_diameter_mm
    diameter = number(outside, "Rohraußendurchmesser") / 1000.0
    if not 0.0 < diameter <= 20.0:
        raise UtilityError(
            "Der Rohraußendurchmesser muss größer als null und höchstens 20000 mm sein.")
    cover = number(cover_depth_m, "Überdeckung")
    if cover < 0.0:
        raise UtilityError("Die Überdeckung darf nicht negativ sein.")
    values = tuple(number(value, "Geländehöhe") for value in surface_elevations_m)
    if len(values) < 2:
        raise UtilityError("Das Geländemodell lieferte zu wenige Höhen.")
    return tuple(value - cover - diameter * 0.5 for value in values)


def bend_rows(points):
    """Return station, angle and vertex for every non-straight control point."""
    values = path(points)
    values_stations = stations(values)
    result = []
    for index in range(1, len(values) - 1):
        previous, corner, following = values[index - 1], values[index], values[index + 1]
        first = corner[0] - previous[0], corner[1] - previous[1]
        second = following[0] - corner[0], following[1] - corner[1]
        divisor = math.hypot(*first) * math.hypot(*second)
        angle = math.degrees(math.acos(max(-1.0, min(1.0,
            (first[0] * second[0] + first[1] * second[1]) / divisor))))
        if angle > 1e-5:
            result.append((values_stations[index], angle, corner))
    return tuple(result)


def height_at(control_stations, heights_m, station_m):
    if len(control_stations) != len(heights_m) or len(heights_m) < 2:
        raise UtilityError("Höhenkette ist unvollständig.")
    normalized_stations = tuple(number(value, "Station") for value in control_stations)
    for first, second in zip(normalized_stations, normalized_stations[1:]):
        if second - first <= 1e-9:
            raise UtilityError("Die Stationen der Höhenkette müssen streng ansteigen.")
    station = number(station_m, "Station")
    if station <= normalized_stations[0]:
        return number(heights_m[0], "Leitungshöhe")
    for index in range(len(normalized_stations) - 1):
        if station <= normalized_stations[index + 1]:
            length = normalized_stations[index + 1] - normalized_stations[index]
            factor = (station - normalized_stations[index]) / length
            first = number(heights_m[index], "Leitungshöhe")
            second = number(heights_m[index + 1], "Leitungshöhe")
            return first + (second - first) * factor
    return number(heights_m[-1], "Leitungshöhe")


def sample_path(points, interval_m, maximum_labels=MAX_LABEL_COUNT):
    values = path(points)
    values_stations = stations(values)
    interval = number(interval_m, "Beschriftungsabstand")
    if interval <= 0.0:
        raise UtilityError("Der Beschriftungsabstand muss größer als null sein.")
    maximum = integer(maximum_labels, "Maximale Beschriftungsanzahl", 1, 1000000)
    targets = []
    station = interval * 0.5
    while station < values_stations[-1] - 1e-9:
        targets.append(station)
        if len(targets) > maximum:
            raise UtilityError(
                "Der Beschriftungsabstand würde mehr als %d Texte erzeugen." % maximum)
        station += interval
    if not targets:
        targets.append(values_stations[-1] * 0.5)
    result = []
    for target in targets:
        for index in range(len(values_stations) - 1):
            if target <= values_stations[index + 1]:
                length = values_stations[index + 1] - values_stations[index]
                factor = (target - values_stations[index]) / length
                first, second = values[index], values[index + 1]
                xy = (first[0] + (second[0] - first[0]) * factor,
                      first[1] + (second[1] - first[1]) * factor)
                angle = math.degrees(math.atan2(second[1] - first[1],
                                                second[0] - first[0]))
                if angle > 90.0 or angle < -90.0:
                    angle = (angle + 180.0) % 360.0
                result.append((target, xy, angle))
                break
    return tuple(result)


def validate_route(value):
    if not isinstance(value, dict) or value.get("schema") != SCHEMA:
        raise UtilityError("Unbekannte Leitungstrassendaten.")
    result = copy.deepcopy(value)
    result["id"] = str(result.get("id") or "").strip()
    if not result["id"]:
        raise UtilityError("Leitungstrassenidentität fehlt.")
    result["points_m"] = path(result.get("points_m"))
    result["utility_type"] = utility_type(result.get("utility_type"))
    result["route_name"] = str(result.get("route_name") or "").strip()
    result["description"] = str(result.get("description") or "").strip()
    if any(len(result[key]) > 255 or any(char in result[key] for char in "\r\t")
           for key in ("route_name", "description")):
        raise UtilityError("Name oder Beschreibung der Leitungstrasse ist ungültig.")
    result["material"] = material(result.get("material", "PE"))
    result["count"] = integer(result.get("count", 1), "Leitungsanzahl", 1, 50)
    result["spacing_m"] = number(result.get("spacing_m", 0.5), "Leitungsabstand")
    result["axis_reference"] = str(result.get("axis_reference", "center"))
    route_offsets(result["count"], result["spacing_m"], result["axis_reference"])
    result["dns_mm"] = nominal_diameters(result.get("dns_mm"), result["count"])
    outside_values, outside_explicit = outside_diameters(
        result.get("outside_diameters_mm"), result["dns_mm"], result["count"],
        result.get("outside_diameters_explicit"))
    result["outside_diameters_mm"] = outside_values
    result["outside_diameters_explicit"] = outside_explicit
    result["graphics_mode"] = str(result.get("graphics_mode", "single_line"))
    if result["graphics_mode"] not in GRAPHICS_MODES:
        raise UtilityError("Ungültige Leitungsdarstellung.")
    result["line_type"] = integer(result.get("line_type", 1), "Linienart", -32767, 71)
    result["axis_line_type"] = integer(result.get("axis_line_type", 2), "Achslinienart", -32767, 71)
    result["round_corners"] = bool(result.get("round_corners", True))
    result["fillet_radius_m"] = number(result.get("fillet_radius_m", 0.50), "Ausrundungsradius")
    rounded_path(result["points_m"], result["fillet_radius_m"], result["round_corners"])
    result["show_fittings"] = bool(result.get("show_fittings", True))
    result["label_bend_angles"] = bool(result.get("label_bend_angles", True))
    result["slope_percent"] = number(result.get("slope_percent", 0.0), "Gefälle")
    result["elevation_mode"] = str(result.get("elevation_mode", "fixed"))
    if result["elevation_mode"] not in ELEVATION_MODES:
        raise UtilityError("Ungültiger Höhenbezug der Leitungstrasse.")
    result["cover_depth_m"] = number(result.get("cover_depth_m", 1.0), "Überdeckung")
    if result["cover_depth_m"] < 0.0:
        raise UtilityError("Die Überdeckung darf nicht negativ sein.")
    result["surface_tin_type"] = integer(
        result.get("surface_tin_type", 2), "Geländemodellzustand", 0, 2)
    result["surface_model_name"] = str(result.get("surface_model_name") or "").strip()
    result["show_heights"] = bool(result.get("show_heights", False))
    supplied_heights = result.get("heights_m")
    if supplied_heights is None:
        supplied_heights = initial_heights(
            result["points_m"], result.get("start_height_m", 100.0), result["slope_percent"])
    if isinstance(supplied_heights, (str, bytes)):
        raise UtilityError("Höhenkette ist unvollständig.")
    try:
        result["heights_m"] = tuple(
            number(item, "Leitungshöhe") for item in supplied_heights)
    except TypeError as error:
        raise UtilityError("Höhenkette ist unvollständig.") from error
    if len(result["heights_m"]) != len(result["points_m"]):
        raise UtilityError("Für jeden Leitungspunkt ist genau eine Höhe erforderlich.")
    route_heights = result.get("route_heights_m")
    if route_heights is None:
        route_heights = [result["heights_m"] for _index in range(result["count"])]
    normalized_heights = []
    try:
        route_height_rows = tuple(route_heights)
    except TypeError as error:
        raise UtilityError("Höhenketten sind unvollständig.") from error
    for row in route_height_rows:
        if isinstance(row, (str, bytes)):
            raise UtilityError("Höhenkette ist unvollständig.")
        try:
            values = tuple(number(item, "Leitungshöhe") for item in row)
        except TypeError as error:
            raise UtilityError("Höhenkette ist unvollständig.") from error
        if len(values) != len(result["points_m"]):
            raise UtilityError("Für jede Leitung ist je Trassenpunkt genau eine Höhe erforderlich.")
        normalized_heights.append(values)
    if len(normalized_heights) != result["count"]:
        raise UtilityError("Die Anzahl der Höhenketten stimmt nicht mit der Leitungsanzahl überein.")
    result["route_heights_m"] = tuple(normalized_heights)
    result["heights_m"] = result["route_heights_m"][0]
    result["start_height_m"] = result["heights_m"][0]
    route_length = stations(result["points_m"])[-1]
    result["slope_percent"] = (
        (result["heights_m"][0] - result["heights_m"][-1]) /
        route_length * 100.0)
    profile_keys = ("surface_profile_stations_m", "surface_profile_heights_m",
                    "surface_profile_surface_m")
    if result["elevation_mode"] != "surface_cover":
        for key in profile_keys:
            result.pop(key, None)
    elif any(result.get(key) is not None for key in profile_keys):
        if not all(result.get(key) is not None for key in profile_keys):
            raise UtilityError("Das gespeicherte DGM-Höhenprofil ist unvollständig.")
        normalized_profiles = {}
        for key, label in (("surface_profile_stations_m", "DGM-Station"),
                           ("surface_profile_heights_m", "Leitungsachshöhe"),
                           ("surface_profile_surface_m", "Geländehöhe")):
            try:
                rows = tuple(tuple(number(item, label) for item in row)
                             for row in result[key])
            except TypeError as error:
                raise UtilityError("Das gespeicherte DGM-Höhenprofil ist unvollständig.") from error
            if len(rows) != result["count"] or any(len(row) < 2 for row in rows):
                raise UtilityError("Das gespeicherte DGM-Höhenprofil passt nicht zur Leitungsanzahl.")
            normalized_profiles[key] = rows
        for station_row, height_row, surface_row in zip(
                normalized_profiles["surface_profile_stations_m"],
                normalized_profiles["surface_profile_heights_m"],
                normalized_profiles["surface_profile_surface_m"]):
            if len(station_row) != len(height_row) or len(station_row) != len(surface_row):
                raise UtilityError("DGM-Stationen und Profilhöhen haben unterschiedliche Längen.")
            for first, second in zip(station_row, station_row[1:]):
                if second - first <= 1e-9:
                    raise UtilityError("Die gespeicherten DGM-Stationen müssen streng ansteigen.")
        result.update(normalized_profiles)
    result["regular_label"] = bool(result.get("regular_label", False))
    result["label_text"] = str(result.get("label_text") or "").strip()
    if result["regular_label"] and not result["label_text"]:
        raise UtilityError("Für die regelmäßige Beschriftung fehlt der Text.")
    result["label_interval_m"] = number(result.get("label_interval_m", 10.0), "Beschriftungsabstand")
    if result["label_interval_m"] <= 0.0:
        raise UtilityError("Der Beschriftungsabstand muss größer als null sein.")
    if result["regular_label"]:
        sample_path(result["points_m"], result["label_interval_m"])
    result["label_frame"] = bool(result.get("label_frame", False))
    result["label_fill"] = bool(result.get("label_fill", False))
    result["label_bold"] = bool(result.get("label_bold", False))
    result["label_underline"] = bool(result.get("label_underline", False))
    result["label_rotation_deg"] = number(
        result.get("label_rotation_deg", 0.0), "Beschriftungsdrehung") % 360.0
    result["label_layout"] = str(result.get("label_layout", "one_line"))
    if result["label_layout"] not in LABEL_LAYOUTS:
        raise UtilityError("Ungültiges Beschriftungsformat.")
    result["font_name"] = str(result.get("font_name") or "Arial").strip()
    result["font_size_pt"] = number(result.get("font_size_pt", 9.0), "Schriftgröße")
    if not result["font_name"] or not 1.0 <= result["font_size_pt"] <= 200.0:
        raise UtilityError("Schriftart oder Schriftgröße ist ungültig.")
    result["draw_3d"] = bool(result.get("draw_3d", True))
    for key in ("line_color", "text_color", "frame_color", "fill_color"):
        color = result.get(key)
        if (not isinstance(color, (list, tuple)) or len(color) != 3 or
                any(type(component) is not int or not 0 <= component <= 65535
                    for component in color)):
            raise UtilityError("Ungültige Farbeinstellung.")
        result[key] = tuple(color)
    return result


def new_route(points, options, identity_factory=None):
    result = copy.deepcopy(options or {})
    result.update(schema=SCHEMA,
                  id=str((identity_factory or uuid.uuid4)()),
                  points_m=path(points))
    result.pop("heights_m", None)
    result.pop("route_heights_m", None)
    return validate_route(result)


def update_height(route, point_index, height_m, route_index=0):
    result = validate_route(route)
    point_index = integer(point_index, "Punktindex", 0, len(result["heights_m"]) - 1)
    route_index = integer(route_index, "Leitungsindex", 0, result["count"] - 1)
    route_heights = [list(row) for row in result["route_heights_m"]]
    route_heights[route_index][point_index] = number(height_m, "Leitungshöhe")
    result["route_heights_m"] = route_heights
    result["heights_m"] = route_heights[0]
    result["elevation_mode"] = "fixed"
    for key in ("surface_profile_stations_m", "surface_profile_heights_m",
                "surface_profile_surface_m"):
        result.pop(key, None)
    return validate_route(result)
