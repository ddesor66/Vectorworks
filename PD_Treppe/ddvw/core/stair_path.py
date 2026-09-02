"""Stationed stair bands, landings and collision checks. All distances in metres.

Sharp changes above five degrees receive a landing. Smooth curves are sampled
by the native adapter and stationed on their *middle* line after side alignment.
No invalid inner offset or self-intersecting footprint is silently repaired.
"""

import bisect
import math
from dataclasses import dataclass

from .stair import StairError

EPS = 1e-8


def add(a, b):
    return a[0] + b[0], a[1] + b[1]


def sub(a, b):
    return a[0] - b[0], a[1] - b[1]


def mul(a, value):
    return a[0] * value, a[1] * value


def dot(a, b):
    return a[0] * b[0] + a[1] * b[1]


def cross(a, b):
    return a[0] * b[1] - a[1] * b[0]


def unit(a):
    length = math.hypot(*a)
    if length < EPS:
        raise StairError("Die Lauflinie enthält doppelte Punkte oder ein zu kurzes Segment.")
    return mul(a, 1 / length)


def normal(tangent):
    return -tangent[1], tangent[0]


def nearest_on_segment(point, a, b):
    delta = sub(b, a)
    t = max(0., min(1., dot(sub(point, a), delta) / dot(delta, delta)))
    return add(a, mul(delta, t))


def clean_points(points):
    cleaned = []
    for point in points:
        point = tuple(point)
        if cleaned and math.dist(cleaned[-1], point) < EPS:
            continue
        while len(cleaned) >= 2:
            first, second = sub(cleaned[-1], cleaned[-2]), sub(point, cleaned[-1])
            if abs(cross(unit(first), unit(second))) > 1e-8 or dot(first, second) <= 0:
                break
            cleaned.pop()
        cleaned.append(point)
    if len(cleaned) < 2:
        raise StairError("Die Lauflinie ist zu kurz.")
    return tuple(cleaned)


def simplify_curve(points, tolerance=1e-4):
    """Remove native tessellation micro-edges within 0.1 mm; retain sharp corners.

    VW's curve evaluator alternates long chords with tiny intermediate segments.
    Mitering those tiny segments magnifies numerical kinks into false offset loops.
    A bounded simplification removes them, without smoothing real path corners.
    """
    points = clean_points(points)
    keep = {0, len(points) - 1}
    for i in range(1, len(points) - 1):
        before = unit(sub(points[i], points[i - 1]))
        after = unit(sub(points[i + 1], points[i]))
        if dot(before, after) < math.cos(math.radians(5)):
            keep.add(i)
    anchors = sorted(keep)
    stack = list(zip(anchors, anchors[1:]))
    while stack:
        start, end = stack.pop()
        if end - start <= 1:
            continue
        distances = [(math.dist(p, nearest_on_segment(p, points[start], points[end])), i)
                     for i, p in enumerate(points[start + 1:end], start + 1)]
        distance, index = max(distances)
        if distance > tolerance:
            keep.add(index)
            stack.extend(((start, index), (index, end)))
    return tuple(points[i] for i in sorted(keep))


def miters(points):
    tangents = tuple(unit(sub(b, a)) for a, b in zip(points, points[1:]))
    normals = [normal(tangents[0])]
    for before, after in zip(tangents, tangents[1:]):
        cosine = dot(before, after)
        if cosine < math.cos(math.radians(170)):
            raise StairError("Fast rückläufiger Knick: Hier passt kein überschneidungsfreies "
                             "Podest. Die Ausgangslinie bitte mit mehr Abstand führen.")
        normals.append(mul(add(normal(before), normal(after)), 1 / (1 + cosine)))
    normals.append(normal(tangents[-1]))
    return tuple(normals)


def offset(points, distance):
    if not distance:
        return points
    return clean_points(tuple(add(p, mul(n, distance)) for p, n in zip(points, miters(points))))


def intersects(a, b, c, d):
    ab, cd = sub(b, a), sub(d, c)
    denominator = cross(ab, cd)
    if abs(denominator) > EPS * max(1., math.hypot(*ab), math.hypot(*cd)):
        t, u = cross(sub(c, a), cd) / denominator, cross(sub(c, a), ab) / denominator
        return -EPS <= t <= 1 + EPS and -EPS <= u <= 1 + EPS
    return min(math.dist(nearest_on_segment(p, a, b), p) for p in (c, d)) < EPS or min(
        math.dist(nearest_on_segment(p, c, d), p) for p in (a, b)) < EPS


def validate_polygon(points):
    points = tuple(points)
    if len(points) < 3:
        raise StairError("Treppenfläche ohne ausreichende Eckpunkte.")
    edges = list(zip(points, points[1:] + points[:1]))
    if any(math.dist(a, b) < EPS for a, b in edges):
        raise StairError("Die innere Treppenkante fällt zusammen. Breite oder Lauflinie ändern.")
    area = sum(cross(a, b) for a, b in edges) * .5
    if abs(area) < EPS:
        raise StairError("Die Treppenfläche besitzt keine gültige Fläche.")
    # Bounding-box sweep avoids quadratic work on long sampled curves.
    boxes = sorted((min(a[0], b[0]), max(a[0], b[0]), min(a[1], b[1]),
                    max(a[1], b[1]), i) for i, (a, b) in enumerate(edges))
    active = []
    for box in boxes:
        active = [other for other in active if other[1] >= box[0] - EPS]
        for other in active:
            i, j = box[4], other[4]
            if abs(i - j) in (1, len(edges) - 1):
                continue
            if other[3] < box[2] - EPS or box[3] < other[2] - EPS:
                continue
            if intersects(*edges[i], *edges[j]):
                raise StairError("Treppenflächen würden sich überschneiden. "
                                 "Lauflinie weiter auseinander führen oder Breite reduzieren.")
        active.append(box)
    return area


@dataclass(frozen=True)
class Span:
    kind: str
    step: int
    start: float
    end: float
    automatic: bool = False


@dataclass(frozen=True)
class Layout:
    points: tuple
    stations: tuple
    width_m: float
    spans: tuple
    length_m: float
    outline: tuple
    bounds: tuple

    def at(self, station):
        station = max(0., min(self.stations[-1], station))
        i = min(len(self.points) - 2, bisect.bisect_right(self.stations, station) - 1)
        a, b = self.points[i:i + 2]
        tangent = unit(sub(b, a))
        return add(a, mul(tangent, station - self.stations[i])), tangent

    def section(self, station):
        point, tangent = self.at(station)
        # At a true corner a section joins the two mitered boundaries.
        i = bisect.bisect_left(self.stations, station)
        if 0 < i < len(self.points) - 1 and abs(self.stations[i] - station) < EPS:
            before = unit(sub(self.points[i], self.points[i - 1]))
            after = unit(sub(self.points[i + 1], self.points[i]))
            n = mul(add(normal(before), normal(after)), 1 / (1 + dot(before, after)))
        else:
            n = normal(tangent)
        return add(point, mul(n, self.width_m / 2)), sub(point, mul(n, self.width_m / 2))

    def band(self, start, end):
        values = [start] + [s for s in self.stations if start + EPS < s < end - EPS] + [end]
        sections = [self.section(s) for s in values]
        return tuple(s[0] for s in sections) + tuple(s[1] for s in reversed(sections))

    def center_path(self, start, end):
        return (self.at(start)[0],) + tuple(p for p, s in zip(self.points, self.stations)
                                           if start + EPS < s < end - EPS) + (self.at(end)[0],)


def _critical_corners(points, stations, width):
    corners = []
    for i in range(1, len(points) - 1):
        before, after = unit(sub(points[i], points[i - 1])), unit(sub(points[i + 1], points[i]))
        angle = math.acos(max(-1., min(1., dot(before, after))))
        if angle > math.radians(5) + EPS:
            margin = width * .5 * math.tan(angle * .5) + .05
            corners.append((stations[i] - margin, stations[i] + margin))
    return corners


def build_layout(result):
    spec, going = result.spec, result.going_m
    manual = dict(spec.landings)
    raw = spec.path_points
    if raw:
        if spec.reverse_path:
            raw = tuple(reversed(raw))
        points = clean_points(raw)
        distance = {"left": .5, "center": 0., "right": -.5}[spec.alignment] * spec.width_m
        points = offset(points, distance)
    else:
        length = result.treads * going + sum(manual.values())
        points = ((spec.width_m / 2, 0.), (spec.width_m / 2, length))
    miters(points)  # Reject near reversals even for centered alignment.
    stations = [0.]
    for a, b in zip(points, points[1:]):
        stations.append(stations[-1] + math.dist(a, b))
    corners = _critical_corners(points, stations, spec.width_m)
    spans, position, corner_index = [], 0., 0

    def landing(after, requested, automatic):
        nonlocal position, corner_index
        start, end = position, position + requested
        while corner_index < len(corners) and corners[corner_index][0] < end + EPS:
            end = max(end, corners[corner_index][1])
            corner_index += 1
        spans.append(Span("landing", after, start, end, automatic))
        position = end

    for step in range(1, result.treads + 1):
        if corner_index < len(corners) and position + going > corners[corner_index][0] + EPS:
            minimum = spec.landing_steps * spec.step_length_cm / 100
            landing(step - 1, max(minimum, corners[corner_index][1] - position), True)
        spans.append(Span("tread", step, position, position + going))
        position += going
        if step in manual:
            landing(step, manual[step], False)
    if position > stations[-1] + 1e-7:
        raise StairError(f"Lauflinie zu kurz: benötigt {position:.3f} m einschließlich Podeste, "
                         f"verfügbar {stations[-1]:.3f} m. Bitte die Ausgangslinie verlängern.")
    draft = Layout(points, tuple(stations), spec.width_m, tuple(spans), position, (), ())
    outline = draft.band(0., position)
    validate_polygon(outline)
    for span in spans:
        if validate_polygon(draft.band(span.start, span.end)) > 0:
            raise StairError("Die innere Treppenkante läuft rückwärts. "
                             "Kurvenradius vergrößern oder Treppenbreite reduzieren.")
    bounds = (min(p[0] for p in outline), min(p[1] for p in outline),
              max(p[0] for p in outline), max(p[1] for p in outline))
    return Layout(points, tuple(stations), spec.width_m, tuple(spans), position, outline, bounds)


def height_label(result, span, scale):
    """Lower-left of tread, aligned to its front edge; height <= 3/4 going."""
    layout = result.layout
    left, right = layout.section(span.start)
    across = unit(sub(right, left))
    forward = normal(across)
    inset = min(.03, result.going_m * .08, result.spec.width_m * .03)
    position = add(add(left, mul(across, inset)), mul(forward, inset))
    size = min(result.spec.height_font_pt, .75 * result.going_m * 1000 / scale * 72 / 25.4)
    angle = math.degrees(math.atan2(across[1], across[0]))
    return position, size, angle, math.dist(left, right) - 2 * inset
