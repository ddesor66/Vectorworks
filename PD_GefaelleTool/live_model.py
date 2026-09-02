"""Pure identities, coordinates and validation for independent height points."""
import copy
import math

from . import core


SCHEMA = 1
PLUGIN = "PD GEF Objekt"
POINT_PREFIX = "PD-GEF-P-"
CHAIN_PREFIX = "PD-GEF-K-"


def point_value(number, xy, height, identity=None):
    if type(number) is not int or number < 1:
        raise core.SlopeError("Punktnummer muss positiv sein.")
    values = tuple(core._number(v, "Punktkoordinate/Höhe") for v in (*xy, height))
    if len(values) != 3:
        raise core.SlopeError("Ungültige Punktkoordinate.")
    result = dict(number=number, x_m=values[0], y_m=values[1], height_m=values[2])
    if identity is not None:
        if not isinstance(identity, str) or not identity.strip():
            raise core.SlopeError("Ungültige Punktidentität.")
        result["point_id"] = identity
    return result


def connection(first, second, level, curve=None):
    """Connect existing point identities; never recalculate their heights."""
    points = [copy.deepcopy(first), copy.deepcopy(second)]
    if not all(p.get("point_id") for p in points):
        raise core.SlopeError("Bitte zwei eigenständige Höhenpunkte wählen.")
    result = core.make_chain([(p["x_m"], p["y_m"]) for p in points], first["height_m"],
                             "end", second["height_m"], level=level, curve=curve)
    result.update(points=points, mode="manual", value=0.)
    return core.validate_chain(result)


def continuation(first, additional_points, mode, value, start_number, level):
    """Continue from one persistent point selected graphically."""
    if not first.get("point_id"):
        raise core.SlopeError("Der grafisch gewählte Höhenpunkt besitzt keine stabile Identität.")
    additional = tuple(tuple(row) for row in additional_points)
    if not additional:
        raise core.SlopeError("Mindestens einen neuen Höhenpunkt anklicken.")
    coordinates = ((first["x_m"], first["y_m"]),) + additional
    result = core.make_chain(
        coordinates, first["height_m"], mode, value,
        int(start_number) - 1, level=level)
    result["points"][0] = copy.deepcopy(first)
    return core.validate_chain(result)


def resolve_chain(stored, points):
    """References, never proximity, define junctions; retain every fixed height."""
    result = copy.deepcopy(stored)
    if len(points) != len(stored["points"]):
        raise core.SlopeError("Eine Punktverknüpfung fehlt.")
    for old, current in zip(stored["points"], points):
        if old["number"] != current["number"]:
            raise core.SlopeError("Punktnummer und Verknüpfung stimmen nicht überein.")
        if old.get("point_id") and old["point_id"] != current.get("point_id"):
            raise core.SlopeError("Die gespeicherte Punktidentität stimmt nicht mit dem Verweis überein.")
        if stored.get("curve") and math.hypot(old["x_m"]-current["x_m"], old["y_m"]-current["y_m"]) > 1e-6:
            # A free move cannot silently turn a native curve into its chords.
            raise core.SlopeError("Dieser Punkt gehört zu einer echten Kurve. Freies Verschieben würde den Kurvenverlauf ändern; die Bewegung wurde nicht übernommen.")
    result["points"] = copy.deepcopy(points)
    result["schema"] = core.SCHEMA_VERSION
    return core.validate_chain(result)


def local_xy(xy, origin, angle):
    radians = math.radians(angle)
    c, s = math.cos(radians), math.sin(radians)
    x, y = xy[0]-origin[0], xy[1]-origin[1]
    return x*c+y*s, -x*s+y*c


def local_chain(chain, origin_m, angle):
    """Drawing frame only: insertion/rotation of a connector cannot detach it."""
    result = copy.deepcopy(chain)
    for point in result["points"]:
        point["x_m"], point["y_m"] = local_xy((point["x_m"], point["y_m"]), origin_m, angle)
    curve = result.get("curve")
    if curve:
        for value in curve["vertices"] + curve["labels"]:
            value["x_m"], value["y_m"] = local_xy((value["x_m"], value["y_m"]), origin_m, angle)
            if "tx" in value:
                value["tx"], value["ty"] = local_xy((value["tx"], value["ty"]), (0, 0), angle)
    return result


def unique_point_numbers(points):
    numbers = [p["number"] for p in points]
    if len(numbers) != len(set(numbers)):
        raise core.SlopeError("Mehrere eigenständige Höhenpunkte besitzen dieselbe Nummer.")
    return set(numbers)
