"""Read a selected path without converting, editing or deleting the source object."""

import math

import vs

from ..core.stair import StairError
from ..core.stair_path import clean_points, nearest_on_segment, simplify_curve
from .stair_draw import units_per_metre


SUPPORTED_TYPES = (2, 5, 21)


def is_supported(handle):
    return bool(handle) and int(vs.GetTypeN(handle)) in SUPPORTED_TYPES


def pick():
    """Interactively highlight and choose one unmodified source path."""
    hint = "PD Treppe: Linie, Polylinie oder Polygon als Lauflinie anklicken. Esc: abbrechen."
    vs.SetTempToolHelpStr(hint)
    try:
        handle, _point = vs.TrackObject(lambda candidate: is_supported(candidate))
    finally:
        vs.SetTempToolHelpStr("")
    return extract(handle) if handle else None


def extract(handle):
    kind = vs.GetTypeN(handle)
    factor = units_per_metre()

    def point(value):
        result = tuple(float(v) / factor for v in value[:2])
        if len(result) != 2 or not all(math.isfinite(v) for v in result):
            raise StairError("Die Ausgangslinie enthält ungültige Koordinaten.")
        return result

    if kind == 2:
        points = (point(vs.GetSegPt1(handle)), point(vs.GetSegPt2(handle)))
    elif kind in (5, 21):
        count = vs.GetVertNum(handle)
        if not 2 <= count <= 1000:
            raise StairError("Bitte eine Lauflinie mit 2–1000 Stützpunkten wählen.")
        closed = vs.IsPolyClosed(handle)
        edge_count = count if closed else count - 1
        if any(not vs.GetVertexVisibility(handle, i) for i in range(edge_count)):
            raise StairError("Die Lauflinie enthält ausgeblendete Kanten. "
                             "Bitte eine durchgehende Linie wählen.")
        vertices = [(point(vs.GetPolyPt(handle, i)), 0) if kind == 5 else
                    (point(vs.GetPolylineVertex(handle, i)[0]), vs.GetPolylineVertex(handle, i)[1])
                    for i in range(1, count + 1)]
        if any(v[1] != 0 for v in vertices):
            points = _sample_curve(handle, vertices, closed, factor)
        else:
            points = tuple(v[0] for v in vertices)
            if closed and math.dist(points[-1], points[0]) > 1e-8:
                points += points[:1]
    else:
        raise StairError("Bitte genau eine Linie, Polylinie oder ein Polygon auswählen, "
                         "oder ohne Auswahl eine gerade Treppe anlegen.")
    points = clean_points(points)
    origin = points[0]
    local = tuple((x - origin[0], y - origin[1]) for x, y in points)
    return local, tuple(v * factor for v in origin)


def _sample_curve(handle, vertices, closed, factor):
    length = float(vs.HPerimN(handle)) / factor
    if not math.isfinite(length) or length < 1e-6 or length > 10000:
        raise StairError("Die Kurvenlänge ist ungültig oder zu groß.")

    def raw(station):
        return vs.PointAlongPolyN(handle, station * factor, 1e-7 * factor)

    # VW's evaluated tessellation domain can be marginally shorter than HPerimN.
    end = raw(length)
    if not end[0]:
        low, high = 0., length
        for _ in range(48):
            middle = (low + high) * .5
            test = raw(middle)
            if test[0]:
                low, end = middle, test
            else:
                high = middle
        if not end[0] or length - low > max(1e-5, length * 1e-4):
            raise StairError("Die native Kurvenstationierung ist nicht eindeutig.")
        length = low
    endpoint = vertices[0][0] if closed else vertices[-1][0]
    if math.dist(tuple(v / factor for v in end[1][:2]), endpoint) > 1e-4:
        raise StairError("Der Kurvenendpunkt stimmt nicht mit der nativen Lauflinie überein.")
    cache = {}

    def at(station):
        if station not in cache:
            ok, xy, _tangent = raw(station)
            if not ok:
                raise StairError("Ein Punkt der Lauflinie konnte nicht gelesen werden.")
            cache[station] = tuple(float(v) / factor for v in xy[:2])
        return cache[station]

    sampled = {0.: at(0.), length: at(length)}

    def subdivide(start, end, depth=0):
        a, b = at(start), at(end)
        middle = (start + end) / 2
        stations = ((3 * start + end) / 4, middle, (start + 3 * end) / 4)
        deviation = max(math.dist(at(s), nearest_on_segment(at(s), a, b))
                        for s in stations) if math.dist(a, b) > 1e-9 else float("inf")
        # 0.02 mm sagitta plus 10 cm maximum chord; explicit original corners below.
        if deviation > 2e-5 or math.dist(a, b) > .1:
            if depth > 20 or len(sampled) > 3900:
                raise StairError("Die Kurve ist zu komplex. "
                                 "Bitte einen kürzeren Treppenabschnitt wählen.")
            sampled[middle] = at(middle)
            subdivide(start, middle, depth + 1)
            subdivide(middle, end, depth + 1)

    # Several independent intervals also catch S curves and closed loops.
    for i in range(32):
        a, b = length * i / 32, length * (i + 1) / 32
        sampled[a], sampled[b] = at(a), at(b)
        subdivide(a, b)
    ordered = sorted(sampled)
    for target, kind in vertices[1:-1]:
        if kind != 0:
            continue
        nearest = min(range(len(ordered)), key=lambda i: math.dist(sampled[ordered[i]], target))
        low, high = ordered[max(0, nearest - 1)], ordered[min(len(ordered) - 1, nearest + 1)]
        for _ in range(48):
            a, b = (2 * low + high) / 3, (low + 2 * high) / 3
            if math.dist(at(a), target) < math.dist(at(b), target):
                high = b
            else:
                low = a
        station = (low + high) / 2
        if math.dist(at(station), target) > 1e-4:
            raise StairError("Ein Knick ist auf dieser Kurve nicht eindeutig zuordenbar.")
        # Replace very close samples to prevent a spurious microscopic segment at the corner.
        for key in tuple(sampled):
            if abs(key - station) < 1e-5:
                del sampled[key]
        sampled[station] = target
    return simplify_curve(tuple(sampled[s] for s in sorted(sampled)))
