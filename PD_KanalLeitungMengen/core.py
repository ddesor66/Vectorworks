# -*- coding: utf-8 -*-
"""Pure quantity calculations for canals, shafts and utility routes.

The module intentionally has no Vectorworks dependency.  DIN EN 1610 selects
the clear trench-width minimum from DN, real outside diameter and depth.  The
user-required 0.15 m shoring thickness is added on both sides only afterwards.
"""
from __future__ import absolute_import

import math


DEPTH_THRESHOLDS_M = (1.0, 1.75, 4.0)
SHAFT_WORKSPACE_M = 0.50
DEFAULT_SHORING_THICKNESS_M = 0.15


class QuantityError(ValueError):
    pass


def number(value, label, minimum=None, allow_zero=True):
    try:
        result = float(value)
    except (TypeError, ValueError) as error:
        raise QuantityError("%s ist keine gültige Zahl." % label) from error
    if not math.isfinite(result):
        raise QuantityError("%s muss endlich sein." % label)
    if minimum is not None and (result < minimum or (not allow_zero and result <= minimum)):
        raise QuantityError("%s ist kleiner als der zulässige Wert." % label)
    return result


def dn_width_addition_m(dn_mm):
    dn = number(dn_mm, "Nennweite", 0.0, False)
    if dn <= 225.0:
        return 0.40
    if dn <= 350.0:
        return 0.50
    if dn <= 700.0:
        return 0.70
    if dn <= 1200.0:
        return 0.85
    return 1.00


def depth_minimum_width_m(depth_m):
    depth = number(depth_m, "Grabentiefe", 0.0)
    if depth < 1.0:
        return None
    if depth <= 1.75:
        return 0.80
    if depth <= 4.0:
        return 0.90
    return 1.00


def trench_widths_m(dn_mm, outside_diameter_m, depth_m,
                    shoring_thickness_m=DEFAULT_SHORING_THICKNESS_M):
    outside = number(outside_diameter_m, "Rohraußendurchmesser", 0.0, False)
    shoring = number(shoring_thickness_m, "Verbaudicke", 0.0)
    by_pipe = outside + dn_width_addition_m(dn_mm)
    by_depth = depth_minimum_width_m(depth_m)
    clear = max(by_pipe, by_depth) if by_depth is not None else by_pipe
    return {
        "pipe_minimum_m": by_pipe,
        "depth_minimum_m": by_depth,
        "clear_width_m": clear,
        "excavation_width_m": clear + 2.0 * shoring,
    }


def _depth_at(start_depth_m, end_depth_m, fraction):
    return start_depth_m + (end_depth_m - start_depth_m) * fraction


def trench_segments(length_m, dn_mm, outside_diameter_m,
                    start_depth_m, end_depth_m,
                    shoring_thickness_m=DEFAULT_SHORING_THICKNESS_M):
    """Split a linearly changing trench at every depth-width threshold."""
    length = number(length_m, "Grabenlänge", 0.0)
    start = number(start_depth_m, "Grabentiefe am Anfang", 0.0)
    end = number(end_depth_m, "Grabentiefe am Ende", 0.0)
    if length <= 1e-9:
        return ()
    fractions = [0.0, 1.0]
    delta = end - start
    if abs(delta) > 1e-12:
        for threshold in DEPTH_THRESHOLDS_M:
            fraction = (threshold - start) / delta
            if 1e-12 < fraction < 1.0 - 1e-12:
                fractions.append(fraction)
    fractions = sorted(set(fractions))
    result = []
    for first, second in zip(fractions, fractions[1:]):
        first_depth = _depth_at(start, end, first)
        second_depth = _depth_at(start, end, second)
        middle_depth = _depth_at(start, end, (first + second) * 0.5)
        segment_length = length * (second - first)
        widths = trench_widths_m(
            dn_mm, outside_diameter_m, middle_depth, shoring_thickness_m)
        average_depth = (first_depth + second_depth) * 0.5
        result.append({
            "station_start_m": length * first,
            "station_end_m": length * second,
            "length_m": segment_length,
            "depth_start_m": first_depth,
            "depth_end_m": second_depth,
            "depth_average_m": average_depth,
            "pipe_minimum_m": widths["pipe_minimum_m"],
            "depth_minimum_m": widths["depth_minimum_m"],
            "clear_width_m": widths["clear_width_m"],
            "excavation_width_m": widths["excavation_width_m"],
            "clear_volume_m3": segment_length * widths["clear_width_m"] * average_depth,
            "excavation_volume_m3": (
                segment_length * widths["excavation_width_m"] * average_depth),
            "shoring_area_m2": 2.0 * segment_length * average_depth,
        })
    return tuple(result)


def trench_totals(length_m, dn_mm, outside_diameter_m,
                  start_depth_m, end_depth_m,
                  shoring_thickness_m=DEFAULT_SHORING_THICKNESS_M):
    segments = trench_segments(
        length_m, dn_mm, outside_diameter_m, start_depth_m, end_depth_m,
        shoring_thickness_m)
    return {
        "segments": segments,
        "clear_volume_m3": sum(row["clear_volume_m3"] for row in segments),
        "excavation_volume_m3": sum(row["excavation_volume_m3"] for row in segments),
        "shoring_allowance_volume_m3": sum(
            row["excavation_volume_m3"] - row["clear_volume_m3"] for row in segments),
        "shoring_area_m2": sum(row["shoring_area_m2"] for row in segments),
        "minimum_clear_width_m": min(
            (row["clear_width_m"] for row in segments), default=0.0),
        "maximum_clear_width_m": max(
            (row["clear_width_m"] for row in segments), default=0.0),
        "minimum_excavation_width_m": min(
            (row["excavation_width_m"] for row in segments), default=0.0),
        "maximum_excavation_width_m": max(
            (row["excavation_width_m"] for row in segments), default=0.0),
    }


def shaft_pit(width_m, height_m, depth_m, workspace_m=SHAFT_WORKSPACE_M,
              shoring_thickness_m=DEFAULT_SHORING_THICKNESS_M):
    """Rectangular shaft pit with work room and shoring on every side."""
    width = number(width_m, "Schachtaußenbreite", 0.0, False)
    height = number(height_m, "Schachtaußenlänge", 0.0, False)
    depth = number(depth_m, "Schachttiefe", 0.0)
    workspace = number(workspace_m, "Arbeitsraum", 0.0)
    shoring = number(shoring_thickness_m, "Verbaudicke", 0.0)
    clear_width = width + 2.0 * workspace
    clear_height = height + 2.0 * workspace
    excavation_width = clear_width + 2.0 * shoring
    excavation_height = clear_height + 2.0 * shoring
    return {
        "body_width_m": width,
        "body_height_m": height,
        "clear_width_m": clear_width,
        "clear_height_m": clear_height,
        "excavation_width_m": excavation_width,
        "excavation_height_m": excavation_height,
        "excavation_volume_m3": excavation_width * excavation_height * depth,
        "shoring_area_m2": 2.0 * (excavation_width + excavation_height) * depth,
    }


def path_length_2d(points):
    values = tuple((number(row[0], "X"), number(row[1], "Y")) for row in points)
    return sum(math.hypot(second[0] - first[0], second[1] - first[1])
               for first, second in zip(values, values[1:]))


def path_length_3d(points, heights_m):
    values = tuple((number(row[0], "X"), number(row[1], "Y")) for row in points)
    heights = tuple(number(value, "Höhe") for value in heights_m)
    if len(values) != len(heights):
        raise QuantityError("Punkte und Höhen einer Leitung sind unvollständig.")
    return sum(math.sqrt(
        (second[0] - first[0]) ** 2 + (second[1] - first[1]) ** 2 +
        (second_height - first_height) ** 2)
        for first, second, first_height, second_height in zip(
            values, values[1:], heights, heights[1:]))


def shaft_body_dimensions(shaft):
    outline = tuple(shaft.get("special_outline_m") or ())
    if shaft.get("structure_type") == "special" and outline:
        xs = [number(row[0], "Sonderschacht-X") for row in outline]
        ys = [number(row[1], "Sonderschacht-Y") for row in outline]
        width, height = max(xs) - min(xs), max(ys) - min(ys)
        if width > 1e-9 and height > 1e-9:
            return width, height
    diameter = number(shaft.get("diameter_m", 0.0), "Schachtdurchmesser", 0.0)
    if diameter <= 0.0:
        return 0.0, 0.0
    wall = number(shaft.get("wall_thickness_m", 0.0), "Schachtwandstärke", 0.0)
    if str(shaft.get("construction_material") or "PP") != "concrete":
        wall = 0.0
    outside = diameter + 2.0 * wall
    return outside, outside


def shaft_counts(pipes, shaft_id):
    return (sum(1 for pipe in pipes if pipe.get("end_id") == shaft_id),
            sum(1 for pipe in pipes if pipe.get("start_id") == shaft_id))


def shaft_pit_projection_m(shaft, direction_xy,
                           shoring_thickness_m=DEFAULT_SHORING_THICKNESS_M):
    """Distance from shaft centre to its rectangular excavation boundary."""
    width, height = shaft_body_dimensions(shaft)
    if width <= 0.0 or height <= 0.0 or not shaft.get("visible", False):
        return 0.0
    dx = number(direction_xy[0], "Richtung X")
    dy = number(direction_xy[1], "Richtung Y")
    magnitude = math.hypot(dx, dy)
    if magnitude <= 1e-12:
        return 0.0
    ux, uy = abs(dx / magnitude), abs(dy / magnitude)
    half_width = width * 0.5 + SHAFT_WORKSPACE_M + shoring_thickness_m
    half_height = height * 0.5 + SHAFT_WORKSPACE_M + shoring_thickness_m
    candidates = []
    if ux > 1e-12:
        candidates.append(half_width / ux)
    if uy > 1e-12:
        candidates.append(half_height / uy)
    return min(candidates) if candidates else 0.0


def analyze(canals, shafts, utility_lines,
            shoring_thickness_m=DEFAULT_SHORING_THICKNESS_M):
    """Build auditable summaries and details from normalized live records."""
    pipes = tuple(dict(row) for row in canals)
    shaft_rows = tuple(dict(row) for row in shafts)
    utilities = tuple(dict(row) for row in utility_lines)
    shaft_index = {row["id"]: row for row in shaft_rows}
    warnings = []
    canal_details = []
    earth_segments = []
    shaft_details = []
    utility_details = []

    for pipe in pipes:
        start = shaft_index.get(pipe.get("start_id"))
        end = shaft_index.get(pipe.get("end_id"))
        if not start or not end:
            warnings.append("Haltung %s: Anfangs- oder Endknoten fehlt." % pipe.get("id", ""))
            continue
        length_2d = number(pipe.get("length_m"), "Haltungslänge", 0.0)
        delta = number(pipe.get("end_invert_m"), "Endsohle") - number(
            pipe.get("start_invert_m"), "Anfangssohle")
        length_3d = math.hypot(length_2d, delta)
        dn = int(number(pipe.get("dn_mm"), "Nennweite", 0.0, False))
        outside_mm = number(pipe.get("outside_diameter_mm", dn), "Rohraußendurchmesser", 0.0, False)
        explicit = bool(pipe.get("outside_diameter_explicit", False))
        if not explicit:
            warnings.append(
                "Haltung %s: OD fehlt; für die Vorermittlung wurde DN %d als Außendurchmesser verwendet."
                % (pipe.get("id", ""), dn))
        start_depth = max(0.0, number(start.get("kd_m"), "Deckelhöhe") -
                          number(pipe.get("start_invert_m"), "Anfangssohle"))
        end_depth = max(0.0, number(end.get("kd_m"), "Deckelhöhe") -
                        number(pipe.get("end_invert_m"), "Endsohle"))
        direction = (
            number(end.get("x_m"), "Endpunkt X") - number(start.get("x_m"), "Anfangspunkt X"),
            number(end.get("y_m"), "Endpunkt Y") - number(start.get("y_m"), "Anfangspunkt Y"))
        start_trim = shaft_pit_projection_m(start, direction, shoring_thickness_m)
        end_trim = shaft_pit_projection_m(
            end, (-direction[0], -direction[1]), shoring_thickness_m)
        if start_trim + end_trim > length_2d and start_trim + end_trim > 1e-12:
            factor = length_2d / (start_trim + end_trim)
            start_trim, end_trim = start_trim * factor, end_trim * factor
        trench_length = max(0.0, length_2d - start_trim - end_trim)
        start_fraction = start_trim / length_2d if length_2d > 1e-12 else 0.0
        end_fraction = 1.0 - end_trim / length_2d if length_2d > 1e-12 else 1.0
        trench_start_depth = _depth_at(start_depth, end_depth, start_fraction)
        trench_end_depth = _depth_at(start_depth, end_depth, end_fraction)
        quantities = trench_totals(
            trench_length, dn, outside_mm / 1000.0,
            trench_start_depth, trench_end_depth, shoring_thickness_m)
        detail = {
            "id": pipe.get("id", ""), "network_id": pipe.get("network_id", ""),
            "kind": pipe.get("kind", ""), "dn_mm": dn,
            "outside_diameter_mm": outside_mm,
            "outside_diameter_explicit": explicit,
            "material": pipe.get("material", ""),
            "start_name": start.get("name", ""), "end_name": end.get("name", ""),
            "start_invert_m": pipe.get("start_invert_m"),
            "end_invert_m": pipe.get("end_invert_m"),
            "start_depth_m": start_depth, "end_depth_m": end_depth,
            "length_2d_m": length_2d, "length_3d_m": length_3d,
            "trench_length_m": trench_length,
            "shaft_pit_overlap_length_m": start_trim + end_trim,
            "clear_volume_m3": quantities["clear_volume_m3"],
            "excavation_volume_m3": quantities["excavation_volume_m3"],
            "shoring_allowance_volume_m3": quantities["shoring_allowance_volume_m3"],
            "shoring_area_m2": quantities["shoring_area_m2"],
            "minimum_clear_width_m": quantities["minimum_clear_width_m"],
            "maximum_clear_width_m": quantities["maximum_clear_width_m"],
            "minimum_excavation_width_m": quantities["minimum_excavation_width_m"],
            "maximum_excavation_width_m": quantities["maximum_excavation_width_m"],
        }
        canal_details.append(detail)
        for index, segment in enumerate(quantities["segments"], 1):
            row = dict(segment)
            row["station_start_m"] += start_trim
            row["station_end_m"] += start_trim
            row.update(pipe_id=detail["id"], kind=detail["kind"], dn_mm=dn,
                       material=detail["material"], segment=index,
                       outside_diameter_mm=outside_mm)
            earth_segments.append(row)

    for shaft in shaft_rows:
        if not shaft.get("visible", False):
            continue
        body_width, body_height = shaft_body_dimensions(shaft)
        if body_width <= 0.0 or body_height <= 0.0:
            continue
        depth = max(0.0, number(shaft.get("kd_m"), "Deckelhöhe") -
                    number(shaft.get("ks_m"), "Schachtsohle"))
        pit = shaft_pit(body_width, body_height, depth,
                        SHAFT_WORKSPACE_M, shoring_thickness_m)
        inlets, outlets = shaft_counts(pipes, shaft["id"])
        shaft_details.append({
            "id": shaft["id"], "name": shaft.get("name", ""),
            "kind": shaft.get("kind", ""),
            "structure_type": shaft.get("structure_type", "round"),
            "construction_material": shaft.get("construction_material", "PP"),
            "inside_diameter_m": shaft.get("diameter_m", 0.0),
            "wall_thickness_m": shaft.get("wall_thickness_m", 0.0),
            "body_width_m": body_width, "body_height_m": body_height,
            "kd_m": shaft.get("kd_m"), "ks_m": shaft.get("ks_m"),
            "height_m": depth, "inlets": inlets, "outlets": outlets,
            "pit_clear_width_m": pit["clear_width_m"],
            "pit_clear_height_m": pit["clear_height_m"],
            "pit_excavation_width_m": pit["excavation_width_m"],
            "pit_excavation_height_m": pit["excavation_height_m"],
            "pit_volume_m3": pit["excavation_volume_m3"],
            "pit_shoring_area_m2": pit["shoring_area_m2"],
        })

    for line in utilities:
        utility_details.append({
            "id": line.get("id", ""), "route_id": line.get("route_id", ""),
            "route_name": line.get("route_name", ""),
            "utility_type": line.get("utility_type", ""),
            "dn_mm": int(number(line.get("dn_mm"), "Leitungsnennweite", 0.0, False)),
            "outside_diameter_mm": number(
                line.get("outside_diameter_mm", line.get("dn_mm")),
                "Leitungsaußendurchmesser", 0.0, False),
            "outside_diameter_explicit": bool(line.get("outside_diameter_explicit", False)),
            "material": line.get("material", ""),
            "length_2d_m": number(line.get("length_2d_m"), "Leitungslänge", 0.0),
            "length_3d_m": number(line.get("length_3d_m"), "3D-Leitungslänge", 0.0),
        })
        if not utility_details[-1]["outside_diameter_explicit"]:
            warnings.append(
                "Leitung %s: OD fehlt; DN wird nur als gekennzeichneter Ersatzwert geführt."
                % utility_details[-1]["id"])

    canal_summary = _canal_summary(canal_details, shaft_details)
    utility_summary = _utility_summary(utility_details)
    totals = {
        "canal_length_2d_m": sum(row["length_2d_m"] for row in canal_details),
        "canal_length_3d_m": sum(row["length_3d_m"] for row in canal_details),
        "utility_length_2d_m": sum(row["length_2d_m"] for row in utility_details),
        "utility_length_3d_m": sum(row["length_3d_m"] for row in utility_details),
        "shaft_count": len(shaft_details),
        "shaft_height_m": sum(row["height_m"] for row in shaft_details),
        "trench_excavation_m3": sum(row["excavation_volume_m3"] for row in canal_details),
        "shaft_pit_excavation_m3": sum(row["pit_volume_m3"] for row in shaft_details),
        "trench_shoring_m2": sum(row["shoring_area_m2"] for row in canal_details),
        "shaft_pit_shoring_m2": sum(row["pit_shoring_area_m2"] for row in shaft_details),
    }
    totals["earthwork_total_m3"] = (totals["trench_excavation_m3"] +
                                     totals["shaft_pit_excavation_m3"])
    totals["shoring_total_m2"] = (totals["trench_shoring_m2"] +
                                   totals["shaft_pit_shoring_m2"])
    return {
        "canal_summary": canal_summary, "utility_summary": utility_summary,
        "canals": tuple(canal_details), "shafts": tuple(shaft_details),
        "utilities": tuple(utility_details), "earth_segments": tuple(earth_segments),
        "totals": totals, "warnings": tuple(dict.fromkeys(warnings)),
    }


def _canal_summary(canals, shafts):
    keys = sorted({row["kind"] for row in canals} | {row["kind"] for row in shafts})
    result = []
    for kind in keys:
        pipe_rows = [row for row in canals if row["kind"] == kind]
        shaft_rows = [row for row in shafts if row["kind"] == kind]
        dns = sorted({row["dn_mm"] for row in pipe_rows})
        materials = sorted({row["material"] for row in pipe_rows})
        result.append({
            "kind": kind,
            "dn_mm": dns[0] if len(dns) == 1 else "verschieden",
            "material": materials[0] if len(materials) == 1 else "verschieden",
            "length_2d_m": sum(row["length_2d_m"] for row in pipe_rows),
            "length_3d_m": sum(row["length_3d_m"] for row in pipe_rows),
            "shaft_count": len(shaft_rows),
            "shaft_height_m": sum(row["height_m"] for row in shaft_rows),
            "inlets_0": sum(row["inlets"] == 0 for row in shaft_rows),
            "inlets_1": sum(row["inlets"] == 1 for row in shaft_rows),
            "inlets_2": sum(row["inlets"] == 2 for row in shaft_rows),
            "inlets_3": sum(row["inlets"] == 3 for row in shaft_rows),
            "inlets_4_plus": sum(row["inlets"] >= 4 for row in shaft_rows),
            "trench_excavation_m3": sum(row["excavation_volume_m3"] for row in pipe_rows),
            "trench_shoring_m2": sum(row["shoring_area_m2"] for row in pipe_rows),
        })
    return tuple(result)


def _utility_summary(lines):
    keys = sorted({(row["utility_type"], row["dn_mm"], row["material"]) for row in lines})
    return tuple({
        "utility_type": utility_type, "dn_mm": dn, "material": material,
        "line_count": len([row for row in lines if
                           (row["utility_type"], row["dn_mm"], row["material"]) == key]),
        "length_2d_m": sum(row["length_2d_m"] for row in lines if
                           (row["utility_type"], row["dn_mm"], row["material"]) == key),
        "length_3d_m": sum(row["length_3d_m"] for row in lines if
                           (row["utility_type"], row["dn_mm"], row["material"]) == key),
    } for key in keys for utility_type, dn, material in (key,))
