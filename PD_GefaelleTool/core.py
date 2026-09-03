# -*- coding: utf-8 -*-
"""Pure calculation and persistence model for the slope tool."""

from __future__ import absolute_import

import copy
import math
import uuid


SCHEMA_VERSION = 5
EPSILON = 1.0e-9


class SlopeError(ValueError):
    pass


def _number(value, label):
    try:
        result = float(value)
    except (TypeError, ValueError):
        raise SlopeError("%s ist keine gültige Zahl." % label)
    if not math.isfinite(result):
        raise SlopeError("%s ist keine endliche Zahl." % label)
    return result


def level_layer_name(value):
    name = str(value or "Standard").strip() or "Standard"
    return name if name.casefold().startswith("gef-") else "GEF-" + name


def normalize_xy(points):
    result = []
    for index, point in enumerate(points, 1):
        if not isinstance(point, (tuple, list)) or len(point) < 2:
            raise SlopeError("Punkt %d besitzt keine gültigen Koordinaten." % index)
        result.append((_number(point[0], "X"), _number(point[1], "Y")))
    if len(result) < 2:
        raise SlopeError("Eine Gefällelinie benötigt mindestens zwei Punkte.")
    for first, second in zip(result, result[1:]):
        if math.hypot(second[0] - first[0], second[1] - first[1]) <= EPSILON:
            raise SlopeError("Zwei aufeinanderfolgende Punkte liegen aufeinander.")
    return tuple(result)


def cumulative_lengths(points, segment_lengths=None):
    points = normalize_xy(points)
    chords = tuple(math.hypot(b[0] - a[0], b[1] - a[1])
                   for a, b in zip(points, points[1:]))
    lengths = chords if segment_lengths is None else tuple(
        _number(value, "Kurvenlänge") for value in segment_lengths)
    if len(lengths) != len(chords) or any(
            length <= EPSILON or length + 1e-5 < chord
            for length, chord in zip(lengths, chords)):
        raise SlopeError("Ungültige Kurvenlängen; es wird nicht mit Sehnenlängen weitergerechnet.")
    values = [0.0]
    for length in lengths:
        values.append(values[-1] + length)
    return tuple(values)


def calculate_heights(points, start_height_m, mode, value, segment_lengths=None):
    points = normalize_xy(points)
    start = _number(start_height_m, "Anfangshöhe")
    calculation = str(mode or "slope").strip().casefold()
    distances = cumulative_lengths(points, segment_lengths)
    if calculation == "slope":
        slope = _number(value, "Gefälle")
        return tuple(start - distance * slope / 100.0 for distance in distances)
    if calculation == "end":
        end = _number(value, "Endhöhe")
        total = distances[-1]
        return tuple(start + (end - start) * distance / total
                     for distance in distances)
    raise SlopeError("Unbekannte Berechnungsart: %s" % mode)


def make_chain(points, start_height_m, mode, value, start_number=1,
               level="Standard", chain_id=None, parent=None, curve=None):
    xy = normalize_xy(points)
    heights = calculate_heights(xy, start_height_m, mode, value, curve_lengths(curve, xy))
    first_number = int(start_number)
    if first_number < 1:
        raise SlopeError("Die erste Punktnummer muss mindestens 1 sein.")
    records = []
    for index, ((x_m, y_m), height_m) in enumerate(zip(xy, heights)):
        records.append({
            "number": first_number + index,
            "x_m": x_m,
            "y_m": y_m,
            "height_m": height_m,
        })
    chain = {
        "schema": SCHEMA_VERSION,
        "chain_id": str(chain_id or uuid.uuid4()),
        "level": str(level or "Standard").strip() or "Standard",
        "layer_name": level_layer_name(level),
        "mode": str(mode).casefold(),
        "value": _number(value, "Berechnungswert"),
        "parent": copy.deepcopy(parent),
        "points": records,
    }
    if curve is not None:
        chain["curve"] = copy.deepcopy(curve)
    return chain


def curve_lengths(curve, points):
    """Validate stored native curve data. Never substitute chords for arcs."""
    if curve is None:
        return None
    if not isinstance(curve, dict) or curve.get("kind") != "polyline":
        raise SlopeError("Unbekannte Gefällekurve.")
    stations = tuple(_number(s, "Kurvenstation") for s in curve.get("stations_m", ()))
    vertices = curve.get("vertices", ())
    labels = curve.get("labels", ())
    if (len(stations) != len(points) or len(vertices) < 2
            or len(labels) != len(points) - 1 or curve.get("closed")
            or not stations or abs(stations[0]) > EPSILON
            or abs(stations[-1] - _number(curve.get("length_m"), "Kurvenlänge")) > 1e-5):
        raise SlopeError("Unvollständige Gefälle-Kurvendaten.")
    # Numbered height stations can be inserted without changing the native
    # Bezier/arc control polygon (which would change the shape).
    controls = tuple(_number(s, "Kontrollstation") for s in
                     curve.get("control_stations_m", stations))
    if (len(controls) != len(vertices) or abs(controls[0]) > EPSILON
            or abs(controls[-1] - stations[-1]) > 1e-5
            or any(b - a <= EPSILON for a, b in zip(controls, controls[1:]))
            or any(not any(abs(c - s) <= 1e-5 for s in stations) for c in controls)):
        raise SlopeError("Ungültige Zuordnung der Höhenpunkte zur Gefällekurve.")
    for vertex in vertices:
        for key in ("x_m", "y_m", "radius_m"):
            _number(vertex.get(key), "Kurvenstützpunkt")
        if vertex.get("type") not in (0, 1, 2, 3, 4):
            raise SlopeError("Unbekannte Art eines Kurvenstützpunkts.")
    for label in labels:
        for key in ("x_m", "y_m", "tx", "ty"):
            _number(label.get(key), "Kurvenbeschriftung")
        if math.hypot(label["tx"], label["ty"]) <= EPSILON:
            raise SlopeError("Kurventangente konnte nicht bestimmt werden.")
    lengths = tuple(b - a for a, b in zip(stations, stations[1:]))
    cumulative_lengths(points, lengths)
    return lengths


def make_branch(parent_chain, parent_point_number, new_points,
                mode, value, next_number, level=None):
    parent_number = int(parent_point_number)
    parent_point = next((point for point in parent_chain["points"]
                         if int(point["number"]) == parent_number), None)
    if parent_point is None:
        raise SlopeError("Punkt P:%d wurde nicht gefunden." % parent_number)
    additional = tuple(new_points)
    points = ((parent_point["x_m"], parent_point["y_m"]),) + additional
    branch = make_chain(
        points, parent_point["height_m"], mode, value,
        start_number=int(next_number) - 1,
        level=level or parent_chain.get("level", "Standard"),
        parent={
            "chain_id": parent_chain["chain_id"],
            "point_number": parent_number,
        })
    branch["points"][0]["number"] = parent_number
    for index, point in enumerate(branch["points"][1:]):
        point["number"] = int(next_number) + index
    return branch


def segment_rows(chain):
    result = []
    points = chain.get("points", ())
    xy = [(p["x_m"], p["y_m"]) for p in points]
    distances = cumulative_lengths(xy, curve_lengths(chain.get("curve"), xy))
    for index, (first, second) in enumerate(zip(points, points[1:])):
        length = distances[index + 1] - distances[index]
        if length <= EPSILON:
            raise SlopeError("Segment P:%s–P:%s hat keine Länge." % (
                first["number"], second["number"]))
        result.append({
            "from": int(first["number"]),
            "to": int(second["number"]),
            "length_m": length,
            "slope_percent": (
                float(first["height_m"]) - float(second["height_m"]))
                / length * 100.0,
        })
    return tuple(result)


def change_point_height(chain, point_number, height_m):
    changed = copy.deepcopy(chain)
    number = int(point_number)
    target = next((point for point in changed["points"]
                   if int(point["number"]) == number), None)
    if target is None:
        raise SlopeError("Punkt P:%d wurde nicht gefunden." % number)
    target["height_m"] = _number(height_m, "Höhe")
    changed["mode"] = "manual"
    changed["value"] = 0.0
    return changed


def change_segment_slope(chain, from_number, to_number,
                         slope_percent, adjust_point_number):
    changed = copy.deepcopy(chain)
    first_number, second_number = int(from_number), int(to_number)
    first = next((point for point in changed["points"]
                  if int(point["number"]) == first_number), None)
    second = next((point for point in changed["points"]
                   if int(point["number"]) == second_number), None)
    if first is None or second is None:
        raise SlopeError("Das gewählte Gefällesegment wurde nicht gefunden.")
    indices = [int(point["number"]) for point in changed["points"]]
    if abs(indices.index(first_number) - indices.index(second_number)) != 1:
        raise SlopeError("Gefälle kann nur zwischen benachbarten Punkten geändert werden.")
    segment_index = min(indices.index(first_number), indices.index(second_number))
    length = segment_rows(changed)[segment_index]["length_m"]
    slope = _number(slope_percent, "Gefälle")
    adjust = int(adjust_point_number)
    if adjust == second_number:
        second["height_m"] = first["height_m"] - length * slope / 100.0
    elif adjust == first_number:
        first["height_m"] = second["height_m"] + length * slope / 100.0
    else:
        raise SlopeError("Anzupassen ist P:%d oder P:%d." % (
            first_number, second_number))
    changed["mode"] = "manual"
    changed["value"] = 0.0
    return changed


def max_point_number(chains):
    values = [int(point.get("number", 0))
              for chain in chains for point in chain.get("points", ())]
    return max(values or (0,))


def validate_document_numbering(chains):
    """Each number has one owner; explicit branch starts only reference it.

    Coincident but independent points are not junctions. This is a read-only
    preflight: copied/damaged groups are never silently renumbered or merged.
    """
    chains = tuple(chains)
    by_id, owners, references, point_ids = {}, {}, [], {}
    for chain in chains:
        validate_chain(chain)
        identity = chain["chain_id"]
        if identity in by_id:
            raise SlopeError("Eine Gefällegruppe wurde dupliziert. Kopie als neues Gefälle übernehmen, damit Punktidentitäten eindeutig bleiben.")
        by_id[identity] = chain
        parent = chain.get("parent")
        if parent is not None and (not isinstance(parent, dict)
                or not isinstance(parent.get("chain_id"), str)
                or not parent["chain_id"].strip()
                or isinstance(parent.get("point_number"), bool)
                or not isinstance(parent.get("point_number"), int)
                or parent.get("point_number") != chain["points"][0]["number"]):
            raise SlopeError("Ungültiger Anschlussverweis in einer Gefällegruppe.")
        for index, point in enumerate(chain["points"]):
            number = point["number"]
            point_id = point.get("point_id")
            owner_id = ("point", point_id) if point_id else ("chain", identity)
            if point_id:
                if point_id in point_ids and point_ids[point_id] != number:
                    raise SlopeError("Ein Höhenpunkt besitzt widersprüchliche Punktnummern.")
                point_ids[point_id] = number
            if index == 0 and parent is not None and not point_id:
                references.append((chain, point))
            elif number in owners:
                owner = owners[number]
                if not point_id or owner[0] != owner_id:
                    raise SlopeError("Punktnummer P:%d ist in unabhängigen Gefällen mehrfach vergeben. "
                                     "Die betroffenen Gruppen zuerst korrigieren; es wurde nichts geändert." % number)
                if any(abs(point[key] - owner[1][key]) > 1e-5 for key in ("x_m", "y_m", "height_m")):
                    raise SlopeError("P:%d besitzt widersprüchliche Anschlusskoordinaten." % number)
            else:
                owners[number] = (owner_id, point)
    for chain, point in references:
        number = point["number"]
        current, seen = chain, set()
        while True:
            identity = current["chain_id"]
            if identity in seen:
                raise SlopeError("Zirkulärer Anschlussverweis bei P:%d." % number)
            seen.add(identity)
            parent = current.get("parent")
            if parent is None or current["points"][0]["number"] != number:
                break
            current = by_id.get(parent["chain_id"])
            if current is None or not any(p["number"] == number for p in current["points"]):
                raise SlopeError("Der ursprüngliche Anschlusspunkt P:%d fehlt in der Zeichnung." % number)
        owner = owners.get(number)
        origin = next((p for p in current["points"] if p["number"] == number), None)
        expected_owner = (("point", origin["point_id"]) if origin and origin.get("point_id")
                          else ("chain", current["chain_id"]))
        if owner is None or owner[0] != expected_owner:
            raise SlopeError("P:%d besitzt keinen eindeutigen ursprünglichen Höhenpunkt." % number)
        if any(abs(point[key] - owner[1][key]) > 1e-5 for key in ("x_m", "y_m", "height_m")):
            raise SlopeError("P:%d besitzt widersprüchliche Anschlusskoordinaten. Anschluss zuerst korrigieren." % number)
    return chains


def connected_height_updates(original, changed, other_chains):
    """One numbered junction has one position/height across all branches.

    Only explicitly changed heights propagate. Every other point stays fixed;
    adjacent slopes are derived again when drawing the updated groups.
    """
    validate_chain(original)
    validate_chain(changed)
    others = tuple(other_chains)
    validate_document_numbering((original,) + others)
    positions = {p["number"]: p for p in original["points"]}
    heights = {p["number"]: p["height_m"] for p in changed["points"]
               if p["number"] in positions and abs(p["height_m"]-positions[p["number"]]["height_m"]) > 1e-9}
    updates = [changed]
    for other in others:
        if not any(p["number"] in heights for p in other["points"]):
            continue
        update = copy.deepcopy(other)
        for point in update["points"]:
            if point["number"] in heights:
                point["height_m"] = heights[point["number"]]
        update["mode"], update["value"] = "manual", 0.0
        validate_chain(update)
        updates.append(update)
    by_id = {c["chain_id"]: c for c in (original,) + others}
    by_id.update((c["chain_id"], c) for c in updates)
    validate_document_numbering(by_id.values())
    return tuple(updates)


def validate_chain(chain):
    if not isinstance(chain, dict) or chain.get("schema", 1) not in (1, 2, 3, 4, SCHEMA_VERSION):
        raise SlopeError("Unbekannte Version der Gefälledaten.")
    required = ("chain_id", "level", "layer_name", "points")
    if not all(key in chain for key in required):
        raise SlopeError("Unvollständige Gefälledaten.")
    points = chain.get("points")
    if (not isinstance(points, (tuple, list)) or len(points) < 2 or
            any(not isinstance(point, dict) for point in points)):
        raise SlopeError("Die Gefälledaten enthalten keine vollständige Punktfolge.")
    point_fields = ("number", "x_m", "y_m", "height_m")
    if any(any(key not in point for key in point_fields) for point in points):
        raise SlopeError("Ein Höhenpunkt besitzt unvollständige gespeicherte Daten.")
    xy = [(point["x_m"], point["y_m"]) for point in points]
    normalize_xy(xy)
    if not isinstance(chain["chain_id"], str) or not chain["chain_id"].strip():
        raise SlopeError("Die Gefällegruppe besitzt keine gültige Identität.")
    numbers = [point["number"] for point in points]
    if any(isinstance(n, bool) or not isinstance(n, int) or n < 1 for n in numbers):
        raise SlopeError("Punktnummern müssen positive ganze Zahlen sein.")
    if len(set(numbers)) != len(numbers):
        raise SlopeError("Punktnummern innerhalb einer Kette sind nicht eindeutig.")
    for point in points:
        _number(point["height_m"], "Punkthöhe")
        if "point_id" in point and (not isinstance(point["point_id"], str) or not point["point_id"].strip()):
            raise SlopeError("Ungültige Identität eines Höhenpunkts.")
    identities = [point["point_id"] for point in points if "point_id" in point]
    if len(identities) != len(set(identities)):
        raise SlopeError("Ein Höhenpunkt wird in derselben Kette mehrfach verwendet.")
    segment_rows(chain)
    if "point_output" in chain:
        from .point_output import options
        options(chain["point_output"])
    return chain
