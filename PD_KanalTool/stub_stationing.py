# -*- coding: utf-8 -*-
"""Pure stationing rules for a fitting on a sewer main holding."""
from __future__ import absolute_import

import math


class StubStationingError(ValueError):
    pass


def _number(value, label):
    try:
        result = float(value)
    except (TypeError, ValueError) as error:
        raise StubStationingError("%s ist keine gültige Zahl." % label) from error
    if not math.isfinite(result):
        raise StubStationingError("%s muss endlich sein." % label)
    return result


def _endpoint(value, label):
    if not isinstance(value, dict) or not str(value.get("id") or ""):
        raise StubStationingError("%s ist unvollständig." % label)
    return {
        "id": str(value["id"]),
        "x_m": _number(value.get("x_m"), "%s-X" % label),
        "y_m": _number(value.get("y_m"), "%s-Y" % label),
        "invert_m": _number(value.get("invert_m"), "%s-Sohle" % label),
    }


def _path_length(points):
    values = tuple(points)
    if len(values) < 2:
        raise StubStationingError("Die tatsächliche Hauptleitungsachse ist unvollständig.")
    result = 0.0
    previous = None
    for index, value in enumerate(values):
        try:
            point = (_number(value[0], "Achsen-X"), _number(value[1], "Achsen-Y"))
        except (TypeError, IndexError) as error:
            raise StubStationingError("Achsenpunkt %d ist ungültig." % (index + 1)) from error
        if previous is not None:
            segment = math.dist(previous, point)
            if segment <= 1e-9:
                raise StubStationingError("Die Hauptleitungsachse enthält einen Nullabschnitt.")
            result += segment
        previous = point
    return result


def calculate(main_start, main_end, connection_xy, start_axis=None, end_axis=None):
    """Calculate station from the lower main-shaft to the fitting.

    For equal invert elevations the persisted object/flow direction is the
    deterministic tie breaker: the main holding's end shaft is the zero
    point.  ``start_axis`` and ``end_axis`` allow callers to provide the real
    axis from either endpoint to the connection instead of a chord.
    """
    start = _endpoint(main_start, "Anfangsschacht")
    end = _endpoint(main_end, "Endschacht")
    try:
        connection = (_number(connection_xy[0], "Stutzen-X"),
                      _number(connection_xy[1], "Stutzen-Y"))
    except (TypeError, IndexError) as error:
        raise StubStationingError("Die Lage des Kanalstutzens ist ungültig.") from error
    equal = abs(start["invert_m"] - end["invert_m"]) <= 1e-9
    if start["invert_m"] < end["invert_m"]:
        zero, axis = start, start_axis
        basis = "lower_invert"
    else:
        # Normal flow and the equal-invert tie both use the stored main end.
        zero, axis = end, end_axis
        basis = "equal_invert_end" if equal else "lower_invert"
    if axis is None:
        axis = ((zero["x_m"], zero["y_m"]), connection)
    station = _path_length(axis)
    return {
        "station_m": station,
        "station_zero_id": zero["id"],
        "station_equal_inverts": equal,
        "station_basis": basis,
    }
