"""Pure rules for locating a wall's movable height reference."""

import math


class WallReferenceError(ValueError):
    """The constructed wall does not provide a usable left top point."""


def _finite(value, field):
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise WallReferenceError("Ungueltiger Wert fuer %s." % field)
    if not math.isfinite(number):
        raise WallReferenceError("Ungueltiger Wert fuer %s." % field)
    return number


def _top_at(element, x):
    points = element.get("top_pts") or ()
    clean = []
    for point in points:
        if not isinstance(point, (list, tuple)) or len(point) < 2:
            raise WallReferenceError("Ungueltige Oberkantenpunkte.")
        clean.append((_finite(point[0], "top_pts.x"),
                      _finite(point[1], "top_pts.y")))
    clean.sort(key=lambda point: point[0])
    if clean:
        if len(clean) == 1 or x <= clean[0][0]:
            return clean[0][1]
        for left, right in zip(clean, clean[1:]):
            if x <= right[0]:
                width = right[0] - left[0]
                if abs(width) <= 1e-12:
                    return max(left[1], right[1])
                factor = (x - left[0]) / width
                return left[1] + factor * (right[1] - left[1])
        return clean[-1][1]
    return _finite(element.get("ytop"), "ytop")


def left_wall_top(elements):
    """Return the local x/y of the constructed wall's left upper edge.

    Several stacked cells can begin at the same x (Gabionen). In that case
    the uppermost cell defines the reference point.
    """
    candidates = []
    for element in elements or ():
        if not isinstance(element, dict):
            raise WallReferenceError("Ungueltiges Mauerelement.")
        x = _finite(element.get("x0"), "x0")
        candidates.append((x, _top_at(element, x)))
    if not candidates:
        raise WallReferenceError("Keine Mauerelemente vorhanden.")
    left_x = min(point[0] for point in candidates)
    tolerance = max(1.0, abs(left_x)) * 1e-9
    left_tops = [point[1] for point in candidates
                 if abs(point[0] - left_x) <= tolerance]
    return left_x, max(left_tops)
