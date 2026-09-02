"""Point display settings and terrain sampling; all lengths are metres."""
import bisect
import math

from .core import SlopeError, _number


DEFAULTS = dict(schema=4, mode="2d", symbol="", symbol_3d="", scale=1.0, connect_3d=False,
                point_class="PD-GEF-Punkt", line_class="PD-GEF-Linie_3D",
                curve_tolerance_mm=1.0, terrain_modifier=False, point_terrain_modifier=False)
MAX_VERTICES = 30000


def options(value=None):
    result = dict(DEFAULTS)
    if value is not None:
        if not isinstance(value, dict):
            raise SlopeError("Ungültige Punktdarstellung.")
        schema = value.get("schema", 1)
        if type(schema) is not int or schema not in (1, 2, 3, 4):
            raise SlopeError("Unbekannte Version der Punktdarstellung.")
        value = dict(value)
        if schema == 1 and value.get("mode") == "3d":
            # The old single symbol field represented the 3D marker in this mode.
            value["symbol_3d"] = value.get("symbol_3d", value.get("symbol", ""))
            value["symbol"] = ""
        result.update({k: v for k, v in value.items() if k in result})
    result["schema"] = 4
    if result["mode"] not in ("2d", "3d"):
        raise SlopeError("Punktdarstellung muss 2D oder 3D sein.")
    result["scale"] = _number(result["scale"], "Symbolfaktor")
    result["curve_tolerance_mm"] = _number(result["curve_tolerance_mm"], "Bogenabweichung")
    if not .001 <= result["scale"] <= 1000:
        raise SlopeError("Symbolfaktor zwischen 0,001 und 1000 eingeben.")
    if not .1 <= result["curve_tolerance_mm"] <= 100:
        raise SlopeError("Bogenabweichung zwischen 0,1 und 100 mm eingeben.")
    if not isinstance(result["connect_3d"], bool):
        raise SlopeError("Ungültige Einstellung für 3D-Verbindungen.")
    result["connect_3d"] = result["mode"] == "3d"
    if any(not isinstance(result[key], bool) for key in ("terrain_modifier", "point_terrain_modifier")):
        raise SlopeError("Ungültige Einstellung für Geländemodifikatoren.")
    # 3D slope output is live terrain input by definition. Users must never
    # create a detached snapshot merely to obtain modifiers.
    automatic_modifier = result["mode"] == "3d"
    result["terrain_modifier"] = automatic_modifier
    result["point_terrain_modifier"] = automatic_modifier
    for key in ("symbol", "symbol_3d", "point_class", "line_class"):
        if not isinstance(result[key], str):
            raise SlopeError("Ungültiger Symbol- oder Klassenname.")
        result[key] = result[key].strip()
    if not result["point_class"] or not result["line_class"]:
        raise SlopeError("Punkte und 3D-Linien benötigen Klassennamen.")
    return result


def class_3d(base):
    """Append the literal requested suffix to the actual 2D class name."""
    if not isinstance(base, str) or not base.strip():
        raise SlopeError("Die 2D-Basisklasse fehlt.")
    return base.strip() + "_3D"


def for_line_class(value, line_class):
    result = options(value)
    result["line_class"] = class_3d(line_class)
    return result


def marker_options(value, mode):
    """Independent marker variants keep the complete 2D depiction intact."""
    result = options(value)
    result["mode"] = mode
    if mode == "3d":
        result["symbol"] = result["symbol_3d"]
        result["point_class"] = class_3d(result["point_class"])
    return result


def height_at(chain, station):
    stations = chain["curve"]["stations_m"]
    index = min(len(stations) - 2, max(0, bisect.bisect_right(stations, station) - 1))
    first, second = chain["points"][index:index+2]
    fraction = (station - stations[index]) / (stations[index+1] - stations[index])
    return first["height_m"] + fraction * (second["height_m"] - first["height_m"])


def terrain_vertices(chain, evaluate=None, tolerance_mm=1.0):
    """Native curve sampled adaptively, including EVERY numbered height point.

    3D polygons have straight edges. Bound station steps to 0.5m and test
    quarter points, not just midpoints (which miss symmetric S curves).
    """
    if chain.get("curve") is None:
        return tuple((p["x_m"], p["y_m"], p["height_m"]) for p in chain["points"])
    if evaluate is None:
        raise SlopeError("Native Kurve fehlt; keine geraden Ersatz-Geländedaten erzeugt.")
    tolerance = _number(tolerance_mm, "Bogenabweichung") / 1000.0
    if tolerance <= 0:
        raise SlopeError("Bogenabweichung muss positiv sein.")
    result = []

    def xyz(station):
        xy = evaluate(station)[0]
        return (xy[0], xy[1], height_at(chain, station))

    def append(point):
        if len(result) >= MAX_VERTICES:
            raise SlopeError("Zu viele 3D-Stützpunkte. Kurve aufteilen oder Bogenabweichung erhöhen.")
        result.append(point)

    def subdivide(a, b, pa, pb, depth=0):
        probes = [(fraction, xyz(a + fraction * (b-a))) for fraction in (.25, .5, .75)]
        error = max(math.hypot(p[0] - (pa[0] + t*(pb[0]-pa[0])),
                               p[1] - (pa[1] + t*(pb[1]-pa[1]))) for t, p in probes)
        if b-a <= .5 and error <= tolerance:
            append(pb)
        else:
            if depth >= 24:
                raise SlopeError("Gefällekurve kann nicht ausreichend genau abgetastet werden.")
            mid = (a+b)*.5
            subdivide(a, mid, pa, probes[1][1], depth+1)
            subdivide(mid, b, probes[1][1], pb, depth+1)

    stations = chain["curve"]["stations_m"]
    append(xyz(stations[0]))
    for a, b in zip(stations, stations[1:]):
        subdivide(a, b, xyz(a), xyz(b))
    return tuple(result)


def unique_points(points):
    """Deduplicate shared junctions, but reject contradictory elevations."""
    found = {}
    for point in points:
        if len(point) != 3 or not all(math.isfinite(v) for v in point):
            raise SlopeError("Ungültige 3D-Koordinaten in den Geländedaten.")
        key = tuple(round(v, 6) for v in point[:2])
        if key in found and abs(found[key][2] - point[2]) > 1e-5:
            raise SlopeError("Gleiche XY-Position mit unterschiedlichen Höhen: Geländedaten zuerst korrigieren.")
        found[key] = point
    return tuple(found.values())
