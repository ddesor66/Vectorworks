# -*- coding: utf-8 -*-
"""Pure geometry, validation and quantity logic in metres.

The module intentionally has no Vectorworks dependency. Existing native site
models are sampled by the adapter; all decisions and quantities are calculated
here and can therefore be regression-tested outside Vectorworks.
"""
from __future__ import absolute_import

import fnmatch
import math


SCHEMA = 1
DEFAULT_XY_TOLERANCE_M = 0.001
DEFAULT_Z_TOLERANCE_M = 0.001
DEFAULT_CHORD_TOLERANCE_M = 0.10
DEFAULT_GRID_M = 1.00
MAX_GRID_CELLS = 500000


class TerrainError(ValueError):
    pass


class CalculationCancelled(TerrainError):
    pass


def number(value, label, minimum=None, maximum=None):
    try:
        result = float(value)
    except (TypeError, ValueError) as error:
        raise TerrainError("%s ist keine gültige Zahl." % label) from error
    if not math.isfinite(result):
        raise TerrainError("%s ist nicht endlich." % label)
    if minimum is not None and result < minimum:
        raise TerrainError("%s muss mindestens %.6g betragen." % (label, minimum))
    if maximum is not None and result > maximum:
        raise TerrainError("%s darf höchstens %.6g betragen." % (label, maximum))
    return result


def point3(value, label="Punkt"):
    try:
        return (number(value[0], label + " X"), number(value[1], label + " Y"),
                number(value[2], label + " Z"))
    except (TypeError, IndexError):
        raise TerrainError("%s ist kein gültiger 3D-Punkt." % label)


def point2(value, label="Punkt"):
    try:
        return number(value[0], label + " X"), number(value[1], label + " Y")
    except (TypeError, IndexError):
        raise TerrainError("%s ist kein gültiger 2D-Punkt." % label)


def _same_xy(first, second, tolerance):
    return math.hypot(first[0] - second[0], first[1] - second[1]) <= tolerance


def polygon_area(points):
    polygon = tuple(point2(value) for value in points)
    if len(polygon) < 3:
        return 0.0
    return 0.5 * math.fsum(
        first[0] * second[1] - second[0] * first[1]
        for first, second in zip(polygon, polygon[1:] + polygon[:1]))


def normalize_polygon(points, label="Begrenzung"):
    result = [point2(value, label) for value in points]
    if len(result) > 1 and _same_xy(result[0], result[-1], 1e-12):
        result.pop()
    cleaned = []
    for value in result:
        if not cleaned or not _same_xy(cleaned[-1], value, 1e-12):
            cleaned.append(value)
    if len(cleaned) < 3 or abs(polygon_area(cleaned)) <= 1e-12:
        raise TerrainError("%s muss eine geschlossene Fläche mit mindestens drei Punkten bilden." % label)
    if polygon_area(cleaned) < 0.0:
        cleaned.reverse()
    return tuple(cleaned)


def point_on_segment(point, first, second, tolerance=1e-9):
    px, py = point2(point)
    ax, ay = point2(first)
    bx, by = point2(second)
    cross = (px - ax) * (by - ay) - (py - ay) * (bx - ax)
    scale = max(1.0, math.hypot(bx - ax, by - ay))
    if abs(cross) > tolerance * scale:
        return False
    dot = (px - ax) * (px - bx) + (py - ay) * (py - by)
    return dot <= tolerance * tolerance


def point_in_polygon(point, polygon, include_boundary=True):
    x, y = point2(point)
    ring = normalize_polygon(polygon)
    inside = False
    for first, second in zip(ring, ring[1:] + ring[:1]):
        if point_on_segment((x, y), first, second):
            return bool(include_boundary)
        if ((first[1] > y) != (second[1] > y)):
            crossing = (second[0] - first[0]) * (y - first[1]) / (second[1] - first[1]) + first[0]
            if x < crossing:
                inside = not inside
    return inside


def bounds(points):
    values = tuple(point2(value) for value in points)
    if not values:
        raise TerrainError("Für die Begrenzung fehlen Punkte.")
    return (min(p[0] for p in values), min(p[1] for p in values),
            max(p[0] for p in values), max(p[1] for p in values))


def _patterns(values):
    if isinstance(values, str):
        values = values.replace(";", "\n").splitlines()
    return tuple(str(value).strip().casefold() for value in (values or ()) if str(value).strip())


def _excluded(value, patterns):
    text = str(value or "").casefold()
    return any(fnmatch.fnmatchcase(text, pattern) for pattern in patterns)


def review_sources(elements, xy_tolerance_m=DEFAULT_XY_TOLERANCE_M,
                   z_tolerance_m=DEFAULT_Z_TOLERANCE_M, boundary=None,
                   excluded_classes=(), excluded_layers=()):
    """Validate normalized source elements without changing their geometry.

    ``elements`` contain ``id``, ``kind``, ``points`` and optionally class/layer.
    Point duplicates are removed. Breaklines are retained as complete elements.
    Same XY with materially different Z is a blocking 2.5D conflict.
    """
    xy_tolerance = number(xy_tolerance_m, "XY-Toleranz", 1e-9)
    z_tolerance = number(z_tolerance_m, "Höhentoleranz", 0.0)
    clipping = normalize_polygon(boundary, "Modellbegrenzung") if boundary else None
    class_patterns = _patterns(excluded_classes)
    layer_patterns = _patterns(excluded_layers)
    source_elements = tuple(elements or ())
    usable, excluded, problems, vertices = [], [], [], []
    seen_vertices = {}
    seen_geometry = {}

    for order, raw in enumerate(source_elements):
        identifier = str(raw.get("id") or "Quelle-%d" % (order + 1))
        kind = str(raw.get("kind") or "").strip().casefold()
        reason = None
        if _excluded(raw.get("class"), class_patterns):
            reason = "Klasse ausgeschlossen"
        elif _excluded(raw.get("layer"), layer_patterns):
            reason = "Ebene ausgeschlossen"
        try:
            points = tuple(point3(value, identifier) for value in raw.get("points", ()))
        except TerrainError as error:
            excluded.append(dict(id=identifier, reason=str(error)))
            continue
        if reason:
            excluded.append(dict(id=identifier, reason=reason))
            continue
        if kind not in ("point", "breakline", "contour", "curve"):
            excluded.append(dict(id=identifier, reason="Geometrieart nicht unterstützt"))
            continue
        minimum = 1 if kind == "point" else 2
        if len(points) < minimum:
            excluded.append(dict(id=identifier, reason="Leere oder zu kurze Geometrie"))
            continue
        inside = tuple(not clipping or point_in_polygon(value[:2], clipping) for value in points)
        if not any(inside):
            excluded.append(dict(id=identifier, reason="Außerhalb der Modellbegrenzung"))
            continue
        if not all(inside):
            problems.append(dict(id=identifier, code="boundary_crossing",
                                 message="Geometrie kreuzt die Modellbegrenzung und wird nicht still gekürzt."))
            excluded.append(dict(id=identifier, reason="Modellbegrenzung wird gekreuzt"))
            continue

        height_conflict = None
        for point in points:
            cell = (int(math.floor(point[0] / xy_tolerance)),
                    int(math.floor(point[1] / xy_tolerance)))
            for cx in range(cell[0] - 1, cell[0] + 2):
                for cy in range(cell[1] - 1, cell[1] + 2):
                    for prior_id, prior in seen_vertices.get((cx, cy), ()):
                        if (_same_xy(point, prior, xy_tolerance) and
                                abs(point[2] - prior[2]) > z_tolerance):
                            height_conflict = (prior_id, prior[2], point[2])
                            break
                    if height_conflict:
                        break
                if height_conflict:
                    break
            if height_conflict:
                break
        if height_conflict:
            problems.append(dict(
                id=identifier, code="same_xy_different_z",
                message=("Gleiche XY-Lage wie %s, aber %.4f m Höhenunterschied." %
                         (height_conflict[0], abs(height_conflict[2] - height_conflict[1])))))
            excluded.append(dict(id=identifier, reason="Widersprüchliche Höhe"))
            continue

        canonical = tuple((round(p[0] / xy_tolerance), round(p[1] / xy_tolerance),
                           round(p[2] / max(z_tolerance, 1e-9))) for p in points)
        geometry_key = (kind, min(canonical, tuple(reversed(canonical))))
        if geometry_key in seen_geometry:
            excluded.append(dict(id=identifier, reason="Identische Geometrie wie %s" % seen_geometry[geometry_key]))
            continue
        seen_geometry[geometry_key] = identifier

        if kind == "point":
            point = points[0]
            cell = (int(math.floor(point[0] / xy_tolerance)),
                    int(math.floor(point[1] / xy_tolerance)))
            duplicate = None
            for cx in range(cell[0] - 1, cell[0] + 2):
                for cy in range(cell[1] - 1, cell[1] + 2):
                    for prior_id, prior in seen_vertices.get((cx, cy), ()):
                        if (_same_xy(point, prior, xy_tolerance) and
                                abs(point[2] - prior[2]) <= z_tolerance):
                            duplicate = prior_id
            if duplicate:
                excluded.append(dict(id=identifier, reason="Doppelpunkt zu %s" % duplicate))
                continue
        usable.append(dict(id=identifier, kind=kind, points=points,
                           class_name=str(raw.get("class") or ""),
                           layer_name=str(raw.get("layer") or "")))
        for point in points:
            cell = (int(math.floor(point[0] / xy_tolerance)),
                    int(math.floor(point[1] / xy_tolerance)))
            seen_vertices.setdefault(cell, []).append((identifier, point))
        vertices.extend(points)

    # Invalid foreign geometry is reported and excluded, but must not prevent
    # the remaining valid terrain sources from being generated.
    blocking = ()
    return {
        "schema": SCHEMA,
        "input_count": len(source_elements),
        "usable_count": len(usable),
        "excluded_count": len(excluded),
        "problem_count": len(problems),
        "blocking_count": len(blocking),
        "usable": tuple(usable),
        "excluded": tuple(excluded),
        "problems": tuple(problems),
        "vertex_count": len(vertices),
        "xy_tolerance_m": xy_tolerance,
        "z_tolerance_m": z_tolerance,
        "boundary": clipping,
    }


def rotate(point, origin, angle_degrees):
    x, y = point2(point)
    ox, oy = point2(origin)
    angle = math.radians(number(angle_degrees, "Rasterwinkel"))
    cosine, sine = math.cos(angle), math.sin(angle)
    dx, dy = x - ox, y - oy
    return ox + cosine * dx - sine * dy, oy + sine * dx + cosine * dy


def _to_grid(point, origin, angle_degrees):
    return rotate(point, origin, -number(angle_degrees, "Rasterwinkel"))


def grid_centers(boundary, spacing_m, origin=None, angle_degrees=0.0,
                 max_cells=MAX_GRID_CELLS):
    ring = normalize_polygon(boundary, "Auswertungsbegrenzung")
    spacing = number(spacing_m, "Rasterweite", 1e-6)
    origin = point2(origin or ring[0], "Rasterursprung")
    local = tuple(_to_grid(value, origin, angle_degrees) for value in ring)
    minimum_x, minimum_y, maximum_x, maximum_y = bounds(local)
    start_i = int(math.floor((minimum_x - origin[0]) / spacing)) - 1
    end_i = int(math.ceil((maximum_x - origin[0]) / spacing)) + 1
    start_j = int(math.floor((minimum_y - origin[1]) / spacing)) - 1
    end_j = int(math.ceil((maximum_y - origin[1]) / spacing)) + 1
    candidate_count = max(0, end_i - start_i) * max(0, end_j - start_j)
    if candidate_count > int(max_cells):
        raise TerrainError("Das Raster würde %d Zellen erzeugen; zulässig sind höchstens %d."
                           % (candidate_count, int(max_cells)))
    result = []
    for j in range(start_j, end_j):
        for i in range(start_i, end_i):
            local_point = (origin[0] + (i + 0.5) * spacing,
                           origin[1] + (j + 0.5) * spacing)
            world = rotate(local_point, origin, angle_degrees)
            if point_in_polygon(world, ring):
                result.append((i, j, world[0], world[1]))
    return tuple(result)


def compare_surfaces(boundary, spacing_m, origin, angle_degrees,
                     reference_sampler, comparison_sampler, z_tolerance_m=0.001,
                     cancel_check=None, progress=None, max_cells=MAX_GRID_CELLS):
    """Midpoint-grid comparison with explicit partial-coverage status."""
    spacing = number(spacing_m, "Rasterweite", 1e-6)
    tolerance = number(z_tolerance_m, "Höhentoleranz", 0.0)
    cells = grid_centers(boundary, spacing, origin, angle_degrees, max_cells)
    values, no_data = [], []
    for index, (i, j, x, y) in enumerate(cells):
        if cancel_check and cancel_check():
            raise CalculationCancelled("Berechnung durch den Benutzer abgebrochen.")
        reference = reference_sampler(x, y)
        comparison = comparison_sampler(x, y)
        if reference is None or comparison is None:
            no_data.append(dict(i=i, j=j, x_m=x, y_m=y,
                                reference_m=reference, comparison_m=comparison))
        else:
            first = number(reference, "Referenzhöhe")
            second = number(comparison, "Vergleichshöhe")
            delta = second - first
            if abs(delta) <= tolerance:
                delta = 0.0
            values.append(dict(i=i, j=j, x_m=x, y_m=y, reference_m=first,
                               comparison_m=second, delta_m=delta))
        if progress and (index % 100 == 0 or index + 1 == len(cells)):
            progress(index + 1, len(cells), "Geländemodelle vergleichen")

    area = spacing * spacing
    fills = [row["delta_m"] * area for row in values if row["delta_m"] > 0.0]
    cuts = [-row["delta_m"] * area for row in values if row["delta_m"] < 0.0]
    fill_area = math.fsum(area for row in values if row["delta_m"] > 0.0)
    cut_area = math.fsum(area for row in values if row["delta_m"] < 0.0)
    fill_volume, cut_volume = math.fsum(fills), math.fsum(cuts)
    status = "grid_complete" if not no_data else "partial_coverage"
    return {
        "schema": SCHEMA,
        "method": "midpoint_grid",
        "sign": "delta = Vergleich - Referenz; positiv = Auftrag",
        "status": status,
        "spacing_m": spacing,
        "origin": point2(origin),
        "angle_degrees": number(angle_degrees, "Rasterwinkel"),
        "cell_area_m2": area,
        "candidate_cells": len(cells),
        "valid_cells": len(values),
        "no_data_cells": len(no_data),
        "comparison_area_m2": len(values) * area,
        "no_data_area_m2": len(no_data) * area,
        "fill_area_m2": fill_area,
        "cut_area_m2": cut_area,
        "fill_volume_m3": fill_volume,
        "cut_volume_m3": cut_volume,
        "difference_m3": fill_volume - cut_volume,
        "maximum_fill_m": max((row["delta_m"] for row in values), default=0.0),
        "maximum_cut_m": max((-row["delta_m"] for row in values), default=0.0),
        "mean_fill_m": fill_volume / fill_area if fill_area else 0.0,
        "mean_cut_m": cut_volume / cut_area if cut_area else 0.0,
        "cells": tuple(values),
        "no_data": tuple(no_data),
    }


def compare_converged(boundary, spacing_m, origin, angle_degrees,
                      reference_sampler, comparison_sampler, z_tolerance_m=0.001,
                      relative_volume_tolerance=0.02, cancel_check=None,
                      progress=None, max_cells=MAX_GRID_CELLS):
    """Run coarse and half-width grids and report numerical convergence.

    The requested grid remains the visible raster. Quantities use the finer
    control grid. This is a numerical DTM comparison, never presented as a
    native Vectorworks cut/fill result.
    """
    spacing = number(spacing_m, "Rasterweite", 1e-6)
    tolerance = number(relative_volume_tolerance, "Volumentoleranz", 0.0, 1.0)
    coarse = compare_surfaces(
        boundary, spacing, origin, angle_degrees, reference_sampler,
        comparison_sampler, z_tolerance_m, cancel_check, progress,
        max(1, int(max_cells) // 4))
    fine = compare_surfaces(
        boundary, spacing / 2.0, origin, angle_degrees, reference_sampler,
        comparison_sampler, z_tolerance_m, cancel_check, progress, max_cells)
    coarse_total = coarse["fill_volume_m3"] + coarse["cut_volume_m3"]
    fine_total = fine["fill_volume_m3"] + fine["cut_volume_m3"]
    absolute_error = abs(fine_total - coarse_total)
    relative_error = absolute_error / max(abs(fine_total), 1e-12)
    result = dict(fine)
    result.update({
        "method": "converged_midpoint_grid",
        "spacing_m": spacing,
        "integration_spacing_m": spacing / 2.0,
        "cells": coarse["cells"],
        "no_data": coarse["no_data"],
        "candidate_cells": coarse["candidate_cells"],
        "valid_cells": coarse["valid_cells"],
        "no_data_cells": coarse["no_data_cells"],
        "coarse_fill_volume_m3": coarse["fill_volume_m3"],
        "coarse_cut_volume_m3": coarse["cut_volume_m3"],
        "convergence_absolute_m3": absolute_error,
        "convergence_relative": relative_error,
        "convergence_tolerance": tolerance,
        "status": ("partial_coverage" if fine["no_data_cells"] or coarse["no_data_cells"]
                   else "converged" if relative_error <= tolerance else "provisional"),
    })
    return result


def slope_run_per_rise(value, unit):
    amount = number(value, "Böschungsneigung", 1e-9)
    mode = str(unit or "").strip().casefold()
    if mode in ("ratio", "1:n", "verhältnis", "verhaeltnis"):
        return amount
    if mode in ("percent", "%", "prozent"):
        return 100.0 / amount
    if mode in ("degree", "degrees", "grad", "°"):
        if amount >= 90.0:
            raise TerrainError("Der Böschungswinkel muss kleiner als 90° sein.")
        return 1.0 / math.tan(math.radians(amount))
    raise TerrainError("Unbekannte Einheit der Böschungsneigung.")


def _unit(value):
    length = math.hypot(value[0], value[1])
    if length <= 1e-12:
        return 0.0, 0.0
    return value[0] / length, value[1] / length


def outward_normals(polygon):
    ring = normalize_polygon(polygon)
    result = []
    for index, current in enumerate(ring):
        previous, following = ring[index - 1], ring[(index + 1) % len(ring)]
        incoming = _unit((current[0] - previous[0], current[1] - previous[1]))
        outgoing = _unit((following[0] - current[0], following[1] - current[1]))
        first = (incoming[1], -incoming[0])
        second = (outgoing[1], -outgoing[0])
        normal = _unit((first[0] + second[0], first[1] + second[1]))
        if normal == (0.0, 0.0):
            normal = second
        result.append(normal)
    return tuple(result)


def _outward_rays(polygon):
    """Return miter ray and perpendicular-distance factor per vertex."""
    ring = normalize_polygon(polygon)
    result = []
    for index, current in enumerate(ring):
        previous, following = ring[index - 1], ring[(index + 1) % len(ring)]
        incoming = _unit((current[0] - previous[0], current[1] - previous[1]))
        outgoing = _unit((following[0] - current[0], following[1] - current[1]))
        first = (incoming[1], -incoming[0])
        second = (outgoing[1], -outgoing[0])
        ray = _unit((first[0] + second[0], first[1] + second[1]))
        if ray == (0.0, 0.0):
            ray = second
        factor = min(abs(ray[0] * first[0] + ray[1] * first[1]),
                     abs(ray[0] * second[0] + ray[1] * second[1]))
        if factor <= 1e-9:
            raise TerrainError("Die Baugrube besitzt eine nicht auflösbare Ecke.")
        result.append((ray, factor))
    return tuple(result)


def solve_excavation(boundary, floor_elevation_m, slope_value, slope_unit,
                     max_extent_m, terrain_sampler, obstacles=(), step_m=0.25,
                     cancel_check=None, floor_slope_percent=0.0,
                     floor_direction_degrees=0.0):
    ring = normalize_polygon(boundary, "Baugrubenbegrenzung")
    floor = number(floor_elevation_m, "Baugrubensohle")
    floor_slope = number(floor_slope_percent, "Sohlengefälle", -1000.0, 1000.0)
    floor_direction = number(floor_direction_degrees, "Sohlengefällerichtung", -360.0, 360.0)
    direction = (math.cos(math.radians(floor_direction)),
                 math.sin(math.radians(floor_direction)))
    floor_origin = ring[0]

    def floor_at(point):
        return floor + ((point[0] - floor_origin[0]) * direction[0] +
                        (point[1] - floor_origin[1]) * direction[1]) * floor_slope / 100.0

    run_per_rise = slope_run_per_rise(slope_value, slope_unit)
    maximum = number(max_extent_m, "Maximale Böschungsausdehnung", 0.01)
    step = min(number(step_m, "Suchschritt", 0.001), maximum)
    obstacle_rings = []
    for index, value in enumerate(obstacles, 1):
        if isinstance(value, dict):
            polygon = value.get("polygon")
            name = str(value.get("name") or "Hindernis %d" % index)
        else:
            polygon, name = value, "Hindernis %d" % index
        obstacle_rings.append((normalize_polygon(polygon, "Hindernis"), name))
    obstacle_rings = tuple(obstacle_rings)
    for obstacle, _name in obstacle_rings:
        if (any(point_in_polygon(value, obstacle) for value in ring) or
                any(point_in_polygon(value, ring) for value in obstacle)):
            raise TerrainError("Ein Hindernis überschneidet die Baugrubensohle.")
    outer, conflicts = [], []
    for index, (point, ray_data) in enumerate(zip(ring, _outward_rays(ring))):
        normal, distance_factor = ray_data
        local_floor = floor_at(point)
        if cancel_check and cancel_check():
            raise CalculationCancelled("Böschungsberechnung abgebrochen.")
        previous_distance, previous_difference = 0.0, None
        solved = None
        distance = 0.0
        while distance <= maximum + 1e-12:
            x = point[0] + normal[0] * distance
            y = point[1] + normal[1] * distance
            hit = next((name for obstacle, name in obstacle_rings
                        if point_in_polygon((x, y), obstacle)), None)
            if hit:
                terrain = terrain_sampler(x, y)
                required = None
                if terrain is not None and terrain > local_floor:
                    required = distance * distance_factor / (terrain - local_floor)
                conflicts.append(dict(edge=index + 1, code="obstacle",
                                      point=(x, y), distance_m=distance,
                                      required_run_per_rise=required,
                                      obstacle=hit))
                break
            terrain = terrain_sampler(x, y)
            if terrain is None:
                conflicts.append(dict(edge=index + 1, code="no_data",
                                      point=(x, y), distance_m=distance))
                break
            slope_z = local_floor + distance * distance_factor / run_per_rise
            difference = number(terrain, "Geländehöhe") - slope_z
            if previous_difference is not None and difference <= 0.0 < previous_difference:
                low, high = previous_distance, distance
                for _iteration in range(40):
                    middle = (low + high) / 2.0
                    mx = point[0] + normal[0] * middle
                    my = point[1] + normal[1] * middle
                    mz = terrain_sampler(mx, my)
                    if mz is None:
                        high = middle
                        continue
                    if number(mz, "Geländehöhe") - (local_floor + middle * distance_factor / run_per_rise) > 0.0:
                        low = middle
                    else:
                        high = middle
                solved = (point[0] + normal[0] * high,
                          point[1] + normal[1] * high,
                          local_floor + high * distance_factor / run_per_rise)
                break
            if distance == 0.0 and difference <= 0.0:
                solved = (x, y, local_floor)
                break
            previous_distance, previous_difference = distance, difference
            distance = min(maximum + step, distance + step)
            if distance > maximum and previous_distance < maximum:
                distance = maximum
        if solved is None:
            if not conflicts or conflicts[-1].get("edge") != index + 1:
                x = point[0] + normal[0] * maximum
                y = point[1] + normal[1] * maximum
                terrain = terrain_sampler(x, y)
                required = (maximum * distance_factor / (terrain - local_floor)
                            if terrain is not None and terrain > local_floor else None)
                conflicts.append(dict(edge=index + 1, code="slope_does_not_daylight",
                                      point=(x, y), distance_m=maximum,
                                      required_run_per_rise=required))
            outer.append((point[0] + normal[0] * maximum,
                          point[1] + normal[1] * maximum,
                          local_floor + maximum * distance_factor / run_per_rise))
        else:
            outer.append(solved)
    return {
        "schema": SCHEMA,
        "status": "valid" if not conflicts else "invalid",
        "floor_elevation_m": floor,
        "floor_slope_percent": floor_slope,
        "floor_direction_degrees": floor_direction,
        "floor_origin": floor_origin,
        "run_per_rise": run_per_rise,
        "maximum_extent_m": maximum,
        "lower_edge": tuple((x, y, floor_at((x, y))) for x, y in ring),
        "upper_edge": tuple(outer),
        "conflicts": tuple(conflicts),
    }


def _perimeter_data(polygon):
    ring = normalize_polygon(polygon)
    lengths = [math.hypot(second[0] - first[0], second[1] - first[1])
               for first, second in zip(ring, ring[1:] + ring[:1])]
    return ring, tuple(lengths), math.fsum(lengths)


def point_at_station(polygon, station_m):
    ring, lengths, total = _perimeter_data(polygon)
    if total <= 0.0:
        raise TerrainError("Die Bezugskante besitzt keine Länge.")
    distance = number(station_m, "Station") % total
    for first, second, length in zip(ring, ring[1:] + ring[:1], lengths):
        if distance <= length or length <= 1e-12:
            factor = 0.0 if length <= 1e-12 else distance / length
            return (first[0] + (second[0] - first[0]) * factor,
                    first[1] + (second[1] - first[1]) * factor)
        distance -= length
    return ring[0]


def _point_and_outward_at_station(polygon, station_m):
    ring, lengths, total = _perimeter_data(polygon)
    distance = number(station_m, "Station") % total
    for first, second, length in zip(ring, ring[1:] + ring[:1], lengths):
        if distance <= length or length <= 1e-12:
            factor = 0.0 if length <= 1e-12 else distance / length
            point = (first[0] + (second[0] - first[0]) * factor,
                     first[1] + (second[1] - first[1]) * factor)
            tangent = _unit((second[0] - first[0], second[1] - first[1]))
            return point, (tangent[1], -tangent[0])
        distance -= length
    return ring[0], (0.0, -1.0)


def _cross(first, second):
    return first[0] * second[1] - first[1] * second[0]


def _ray_polygon_hit(point, ray, polygon):
    hits = []
    for first, second in zip(polygon, polygon[1:] + polygon[:1]):
        segment = (second[0] - first[0], second[1] - first[1])
        denominator = _cross(ray, segment)
        if abs(denominator) <= 1e-12:
            continue
        offset = (first[0] - point[0], first[1] - point[1])
        distance = _cross(offset, segment) / denominator
        position = _cross(offset, ray) / denominator
        if distance >= -1e-9 and -1e-9 <= position <= 1.0 + 1e-9:
            hits.append(max(0.0, distance))
    return min(hits) if hits else None


def _inside_slope_band(point, lower, upper):
    return (point_in_polygon(point, upper) and
            not point_in_polygon(point, lower, include_boundary=False))


def hatch_lines(lower_edge, upper_edge, spacing_m, short_ratio=0.5, anchor_m=None):
    lower = normalize_polygon(tuple(value[:2] for value in lower_edge), "Untere Böschungskante")
    upper = normalize_polygon(tuple(value[:2] for value in upper_edge), "Obere Böschungskante")
    spacing = number(spacing_m, "Schraffurabstand", 0.001)
    ratio = number(short_ratio, "Kurze Linienlänge", 0.01, 1.0)
    _ring, _lengths, total = _perimeter_data(lower)
    anchor = spacing / 2.0 if anchor_m is None else number(anchor_m, "Schraffuranker", 0.0)
    result, index, station = [], 0, anchor
    while station < total - 1e-9:
        first, outward = _point_and_outward_at_station(lower, station)
        hit = _ray_polygon_hit(first, outward, upper)
        if hit is None:
            station = anchor + (index + 1) * spacing
            index += 1
            continue
        second = (first[0] + outward[0] * hit, first[1] + outward[1] * hit)
        length_ratio = 1.0 if index % 2 == 0 else ratio
        end = (first[0] + (second[0] - first[0]) * length_ratio,
               first[1] + (second[1] - first[1]) * length_ratio)
        samples = tuple((first[0] + (end[0] - first[0]) * step / 10.0,
                         first[1] + (end[1] - first[1]) * step / 10.0)
                        for step in range(1, 11))
        if all(_inside_slope_band(value, lower, upper) for value in samples):
            result.append(dict(station_m=station, long=index % 2 == 0,
                               start=first, end=end, ratio=length_ratio))
        index += 1
        station = anchor + index * spacing
    return tuple(result)


def zero_segments(comparison):
    """Marching-squares-like zero segments from midpoint-grid values."""
    rows = {(item["i"], item["j"]): item for item in comparison.get("cells", ())}
    segments = []
    for (i, j), lower_left in sorted(rows.items()):
        corners = (lower_left, rows.get((i + 1, j)), rows.get((i + 1, j + 1)),
                   rows.get((i, j + 1)))
        if any(value is None for value in corners):
            continue
        crossings = []
        for first, second in zip(corners, corners[1:] + corners[:1]):
            da, db = first["delta_m"], second["delta_m"]
            if da == db == 0.0:
                continue
            if (da <= 0.0 <= db) or (db <= 0.0 <= da):
                denominator = abs(da) + abs(db)
                factor = 0.5 if denominator <= 1e-12 else abs(da) / denominator
                crossings.append((first["x_m"] + (second["x_m"] - first["x_m"]) * factor,
                                  first["y_m"] + (second["y_m"] - first["y_m"]) * factor))
        if len(crossings) == 2 and not _same_xy(crossings[0], crossings[1], 1e-9):
            segments.append((crossings[0], crossings[1]))
    return tuple(segments)
