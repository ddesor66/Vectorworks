"""Non-mutating projection, interpolation and connection splitting in metres."""
import bisect
import copy
import math

from . import core


MIN_PART_M = 1e-5


def stations(chain):
    xy = [(p["x_m"], p["y_m"]) for p in chain["points"]]
    return core.cumulative_lengths(xy, core.curve_lengths(chain.get("curve"), xy))


def _label(evaluate, first, second):
    point, tangent = evaluate((first + second) * .5)
    return dict(x_m=point[0], y_m=point[1], tx=tangent[0], ty=tangent[1])


def nearest_station(chain, click, evaluate=None):
    """Project to the actual connection, never to a curve's control polygon."""
    core.validate_chain(chain)
    target = (core._number(click[0], "X"), core._number(click[1], "Y"))
    distances = stations(chain)
    candidates = []

    def squared(p):
        return (p[0] - target[0]) ** 2 + (p[1] - target[1]) ** 2

    if chain.get("curve"):
        if evaluate is None:
            raise core.SlopeError("Die originale Gefällekurve ist für die Punkteingabe erforderlich.")
        # Search every sampled local minimum, not only the first interval.
        # Refine with the native arc-length evaluator; endpoints stay exact.
        count = min(4096, max(128, 32 * len(chain["curve"]["vertices"])))
        sampled = sorted(set(distances + tuple(distances[-1] * i / count for i in range(count + 1))))
        values = [squared(evaluate(s)[0]) for s in sampled]
        candidates.extend((values[i], sampled[i]) for i in (0, len(sampled) - 1))
        ratio = (math.sqrt(5) - 1) * .5
        for i in range(1, len(sampled) - 1):
            if values[i] > values[i-1] or values[i] > values[i+1]:
                continue
            candidates.append((values[i], sampled[i]))
            lo, hi = sampled[i-1], sampled[i+1]
            a, b = hi - ratio * (hi-lo), lo + ratio * (hi-lo)
            fa, fb = squared(evaluate(a)[0]), squared(evaluate(b)[0])
            for _ in range(64):
                if hi-lo <= 1e-8:
                    break
                if fa > fb:
                    lo, a, fa = a, b, fb
                    b = lo + ratio * (hi-lo)
                    fb = squared(evaluate(b)[0])
                else:
                    hi, b, fb = b, a, fa
                    a = hi - ratio * (hi-lo)
                    fa = squared(evaluate(a)[0])
            s = (lo+hi) * .5
            candidates.append((squared(evaluate(s)[0]), s))
    else:
        for i, (a, b) in enumerate(zip(chain["points"], chain["points"][1:])):
            dx, dy = b["x_m"]-a["x_m"], b["y_m"]-a["y_m"]
            t = max(0., min(1., ((target[0]-a["x_m"])*dx + (target[1]-a["y_m"])*dy) / (dx*dx+dy*dy)))
            p = a["x_m"]+t*dx, a["y_m"]+t*dy
            candidates.append((squared(p), distances[i]+t*(distances[i+1]-distances[i])))
    candidates.sort()
    best_distance, station = candidates[0]
    if any(abs(s-station) > MIN_PART_M and abs(d-best_distance) <= 1e-12
           for d, s in candidates[1:]):
        raise core.SlopeError("An dieser Stelle sind mehrere Verbindungen gleich nah. Bitte eine eindeutige Stelle wählen.")
    return station, math.sqrt(best_distance)


def insert_at_station(chain, station_m, number, evaluate=None):
    """Return a replacement and its preview; the source is never modified."""
    core.validate_chain(chain)
    distance = stations(chain)
    s = core._number(station_m, "Einfügestation")
    number = int(number)
    if number < 1 or any(int(p["number"]) == number for p in chain["points"]):
        raise core.SlopeError("Die neue Punktnummer muss positiv und noch frei sein.")
    if not 0 < s < distance[-1] or any(abs(s-d) <= MIN_PART_M for d in distance):
        raise core.SlopeError("Hier liegt bereits ein Höhenpunkt oder ein Linienende. Bitte eine Stelle dazwischen wählen.")
    i = bisect.bisect_right(distance, s) - 1
    a, b = chain["points"][i:i+2]
    part, rest = s-distance[i], distance[i+1]-s
    fraction = part/(part+rest)
    height = a["height_m"] + (b["height_m"]-a["height_m"]) * fraction
    changed = copy.deepcopy(chain)
    if chain.get("curve"):
        if evaluate is None:
            raise core.SlopeError("Die originale Gefällekurve fehlt; kein Rückfall auf Sehnenlängen.")
        xy = evaluate(s)[0]
        curve = changed["curve"]
        curve["control_stations_m"] = list(curve.get("control_stations_m", distance))
        curve["stations_m"] = list(distance[:i+1]) + [s] + list(distance[i+1:])
        curve["labels"] = list(curve["labels"])
        curve["labels"][i:i+1] = [_label(evaluate, distance[i], s), _label(evaluate, s, distance[i+1])]
    else:
        xy = (a["x_m"]+(b["x_m"]-a["x_m"])*fraction,
              a["y_m"]+(b["y_m"]-a["y_m"])*fraction)
    changed["points"].insert(i+1, dict(number=number, x_m=xy[0], y_m=xy[1], height_m=height))
    changed["schema"] = core.SCHEMA_VERSION
    core.validate_chain(changed)
    return changed, dict(number=number, height_m=height, x_m=xy[0], y_m=xy[1],
                         from_number=a["number"], to_number=b["number"],
                         first_length_m=part, second_length_m=rest,
                         station_m=s, curved=bool(chain.get("curve")))


def preview(chain, click, number, evaluate=None):
    station, offset = nearest_station(chain, click, evaluate)
    changed, info = insert_at_station(chain, station, number, evaluate)
    info["click_offset_m"] = offset
    return changed, info


def rebase_curve(chain, source_curve, evaluate):
    """Preserve inserted stations when the native curve is moved or edited.

    The fraction within the original control-to-control interval is retained,
    rather than distributing old numbered points over a new control polygon.
    """
    old = chain["curve"]
    controls = old.get("control_stations_m", old["stations_m"])
    new_controls = source_curve["stations_m"]
    if len(controls) != len(new_controls):
        raise core.SlopeError("Die Zahl der Kurvenstützpunkte wurde geändert; bitte als neues Gefälle übernehmen.")
    mapped = []
    for s in old["stations_m"]:
        i = min(len(controls)-2, max(0, bisect.bisect_right(controls, s)-1))
        fraction = (s-controls[i])/(controls[i+1]-controls[i])
        mapped.append(new_controls[i]+fraction*(new_controls[i+1]-new_controls[i]))
    changed = copy.deepcopy(chain)
    curve = changed["curve"] = copy.deepcopy(source_curve)
    curve["control_stations_m"] = list(new_controls)
    curve["stations_m"] = mapped
    curve["labels"] = [_label(evaluate, a, b) for a, b in zip(mapped, mapped[1:])]
    for p, s in zip(changed["points"], mapped):
        p["x_m"], p["y_m"] = evaluate(s)[0]
    changed["schema"] = core.SCHEMA_VERSION
    return core.validate_chain(changed)
