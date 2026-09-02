"""Station control vertices on a native curve; calculations use arc length.

The supplied evaluator accepts metres of distance along the original curve
and returns (point_in_metres, unit_tangent). No tessellated chord sums are used.
"""
import math

from .core import SlopeError


def squared_distance(a, b):
    return (a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2


def station_vertices(vertices, length_m, evaluate):
    if len(vertices) < 2 or not math.isfinite(length_m) or length_m <= 1e-9:
        raise SlopeError("Die Gefällekurve besitzt keine gültige Länge.")
    # A coarse search brackets a nearest point; golden section then queries
    # the actual native curve to sub-millimetre station tolerance.
    count = min(4096, max(128, 16 * len(vertices)))
    sampled = [(length_m * i / count, evaluate(length_m * i / count)[0])
               for i in range(count + 1)]
    stations = [0.0]
    for vertex in vertices[1:-1]:
        target = (vertex["x_m"], vertex["y_m"])
        nearest = min(range(count + 1), key=lambda i: squared_distance(sampled[i][1], target))
        lo, hi = sampled[max(0, nearest - 1)][0], sampled[min(count, nearest + 1)][0]
        ratio = (math.sqrt(5.0) - 1.0) * .5
        x1, x2 = hi - ratio * (hi - lo), lo + ratio * (hi - lo)
        f1, f2 = squared_distance(evaluate(x1)[0], target), squared_distance(evaluate(x2)[0], target)
        for _ in range(64):
            if hi - lo <= 1e-7:
                break
            if f1 > f2:
                lo, x1, f1 = x1, x2, f2
                x2 = lo + ratio * (hi - lo)
                f2 = squared_distance(evaluate(x2)[0], target)
            else:
                hi, x2, f2 = x2, x1, f1
                x1 = hi - ratio * (hi - lo)
                f1 = squared_distance(evaluate(x1)[0], target)
        station = .5 * (lo + hi)
        point = evaluate(station)[0]
        # Only corners have an exact on-path contract. Native VW2026 cubic
        # evaluation also projects controls: the measured (5,5) control maps
        # to (5,4.989711934...) in BOTH polyline and converted NURBS APIs.
        # Keep all controls unchanged; station the marker on the native path.
        if vertex["type"] == 0 and squared_distance(point, target) > 1e-8:
            raise SlopeError("Ein Stützpunkt konnte nicht eindeutig auf der Kurve bestimmt werden.")
        if station <= stations[-1] + 1e-6 or station >= length_m - 1e-6:
            raise SlopeError(
                "Kurvenstützpunkte sind nicht eindeutig in Zeichenrichtung zuordenbar. "
                "Bitte die Kurve an dieser Stelle aufteilen.")
        stations.append(station)
    stations.append(length_m)
    points = tuple(evaluate(s)[0] for s in stations)
    labels = []
    for first, second in zip(stations, stations[1:]):
        point, tangent = evaluate(.5 * (first + second))
        labels.append(dict(x_m=point[0], y_m=point[1], tx=tangent[0], ty=tangent[1]))
    return points, stations, labels
