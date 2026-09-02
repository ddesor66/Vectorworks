# -*- coding: utf-8 -*-
"""Pure, deterministic 2D geometry used by the Vectorworks adapters."""

from __future__ import absolute_import

import math


def quantize(value, tolerance):
    tolerance = max(abs(float(tolerance)), 1.0e-12)
    return int(round(float(value) / tolerance))


def quantized_point(point, tolerance):
    return (quantize(point[0], tolerance), quantize(point[1], tolerance))


def _same_direction_collinear(first, middle, last):
    """Return True when ``middle`` only subdivides one straight segment."""
    first_dx = middle[0] - first[0]
    first_dy = middle[1] - first[1]
    second_dx = last[0] - middle[0]
    second_dy = last[1] - middle[1]
    return (first_dx * second_dy - first_dy * second_dx == 0 and
            first_dx * second_dx + first_dy * second_dy >= 0)


def normalized_path(points, closed, tolerance):
    """Quantize a path and remove representation-only intermediate vertices.

    Vectorworks can store the same visible path as a line, polygon or polyline.
    A polyline may also contain repeated or collinear support points which do
    not change its geometry.  Duplicate detection must compare the drawn path,
    not those storage details.
    """
    values = []
    for source_point in points:
        value = quantized_point(source_point, tolerance)
        if not values or value != values[-1]:
            values.append(value)
    if closed and len(values) > 1 and values[0] == values[-1]:
        values.pop()

    changed = True
    while changed and len(values) >= (3 if not closed else 4):
        changed = False
        if closed:
            keep = []
            count = len(values)
            for index, middle in enumerate(values):
                first = values[(index - 1) % count]
                last = values[(index + 1) % count]
                if _same_direction_collinear(first, middle, last):
                    changed = True
                else:
                    keep.append(middle)
            values = keep
        else:
            keep = [values[0]]
            for index in range(1, len(values) - 1):
                if _same_direction_collinear(
                        keep[-1], values[index], values[index + 1]):
                    changed = True
                else:
                    keep.append(values[index])
            keep.append(values[-1])
            values = keep
    return tuple(values)


def canonical_path(points, closed, tolerance):
    """Direction-independent fingerprint; closed rings also ignore start vertex."""
    values = normalized_path(points, closed, tolerance)
    if not values:
        return ()
    if not closed:
        reverse = tuple(reversed(values))
        return min(values, reverse)
    candidates = []
    for sequence in (values, tuple(reversed(values))):
        for index in range(len(sequence)):
            candidates.append(sequence[index:] + sequence[:index])
    return min(candidates)


def bbox_normalized(bounds):
    first, second = bounds
    return (
        min(float(first[0]), float(second[0])),
        min(float(first[1]), float(second[1])),
        max(float(first[0]), float(second[0])),
        max(float(first[1]), float(second[1])),
    )


def bbox_center(bounds):
    left, bottom, right, top = bounds
    return ((left + right) * 0.5, (bottom + top) * 0.5)


def bbox_signature(bounds, tolerance):
    return tuple(quantize(value, tolerance) for value in bounds)


def polyline_length(points, closed=False):
    points = tuple(points)
    if len(points) < 2:
        return 0.0
    pairs = list(zip(points, points[1:]))
    if closed:
        pairs.append((points[-1], points[0]))
    return sum(math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in pairs)


def point_at_distance(points, distance, closed=False):
    points = tuple(points)
    if len(points) < 2:
        return (points[0], 0.0) if points else ((0.0, 0.0), 0.0)
    segments = list(zip(points, points[1:]))
    if closed:
        segments.append((points[-1], points[0]))
    remaining = max(0.0, float(distance))
    for first, second in segments:
        dx, dy = second[0] - first[0], second[1] - first[1]
        length = math.hypot(dx, dy)
        if length <= 1.0e-12:
            continue
        if remaining <= length:
            ratio = remaining / length
            return ((first[0] + ratio * dx, first[1] + ratio * dy),
                    math.degrees(math.atan2(dy, dx)))
        remaining -= length
    first, second = segments[-1]
    return (second, math.degrees(math.atan2(
        second[1] - first[1], second[0] - first[0])))


def repeated_path_positions(points, spacing, closed=False):
    length = polyline_length(points, closed)
    if length <= 1.0e-12:
        return ()
    spacing = max(float(spacing), length / 50.0, 1.0e-9)
    count = max(1, int(math.floor(length / spacing)))
    step = length / float(count)
    return tuple(point_at_distance(points, (index + 0.5) * step, closed)
                 for index in range(count))


def support_segment_midpoints(points, minimum_spacing=0.0, closed=False):
    """Return midpoint and tangent for each support-point segment.

    Candidates are retained in path order.  When two consecutive candidates
    are closer than ``minimum_spacing`` along the path, the later one is
    omitted.  A valid path always keeps at least its first segment midpoint.
    """
    points = tuple(points)
    if len(points) < 2:
        return ()
    segments = list(zip(points, points[1:]))
    if closed:
        segments.append((points[-1], points[0]))
    minimum_spacing = max(0.0, float(minimum_spacing))
    candidates = []
    station = 0.0
    total_length = 0.0
    for first, second in segments:
        dx, dy = second[0] - first[0], second[1] - first[1]
        length = math.hypot(dx, dy)
        if length <= 1.0e-12:
            continue
        midpoint = ((first[0] + second[0]) * 0.5,
                    (first[1] + second[1]) * 0.5)
        midpoint_station = station + length * 0.5
        candidates.append((midpoint_station, midpoint,
                           math.degrees(math.atan2(dy, dx))))
        station += length
        total_length += length
    if not candidates:
        return ()
    kept = [candidates[0]]
    for candidate in candidates[1:]:
        if candidate[0] - kept[-1][0] + 1.0e-12 >= minimum_spacing:
            kept.append(candidate)
    if (closed and len(kept) > 1 and
            total_length - kept[-1][0] + kept[0][0] + 1.0e-12 <
            minimum_spacing):
        kept.pop()
    return tuple((candidate[1], candidate[2]) for candidate in kept)


def label_frame_dimensions(text_width, text_height, frame_shape,
                           padding_factor=0.30):
    """Return collision/creation dimensions for an optional text frame."""
    width = max(0.0, float(text_width))
    height = max(0.0, float(text_height))
    if int(frame_shape or 0) == 0:
        return width, height
    padding = max(0.0, float(padding_factor)) * height
    width += padding * 2.0
    height += padding * 2.0
    if int(frame_shape) == 1:
        diameter = max(width, height)
        return diameter, diameter
    return width, height


def point_in_polygon(point, polygon):
    polygon = tuple(polygon)
    if len(polygon) < 3:
        return False
    inside = False
    x, y = point
    previous = polygon[-1]
    for current in polygon:
        x1, y1 = previous
        x2, y2 = current
        if ((y1 > y) != (y2 > y)):
            crossing = (x2 - x1) * (y - y1) / (y2 - y1) + x1
            if x < crossing:
                inside = not inside
        previous = current
    return inside


def area_positions(bounds, spacing, polygon=()):
    left, bottom, right, top = bounds
    width, height = right - left, top - bottom
    if width <= 0.0 or height <= 0.0:
        return (bbox_center(bounds),)
    spacing = max(float(spacing), 1.0e-9)
    columns = max(1, min(12, int(width / spacing)))
    rows = max(1, min(12, int(height / spacing)))
    points = []
    for row in range(rows):
        y = bottom + (row + 0.5) * height / rows
        for column in range(columns):
            x = left + (column + 0.5) * width / columns
            candidate = (x, y)
            if not polygon or point_in_polygon(candidate, polygon):
                points.append(candidate)
    return tuple(points) or (bbox_center(bounds),)


def rotated_text_aabb(origin, width, height, angle_degrees, padding=0.0):
    angle = math.radians(float(angle_degrees))
    cosine, sine = abs(math.cos(angle)), abs(math.sin(angle))
    half_width = (float(width) * cosine + float(height) * sine) * 0.5
    half_height = (float(width) * sine + float(height) * cosine) * 0.5
    return (origin[0] - half_width - padding,
            origin[1] - half_height - padding,
            origin[0] + half_width + padding,
            origin[1] + half_height + padding)


def boxes_overlap(first, second):
    return not (first[2] <= second[0] or second[2] <= first[0] or
                first[3] <= second[1] or second[3] <= first[1])


def placement_without_collision(preferred, width, height, angle, occupied,
                                offset_step):
    offsets = ((0, 0), (0, 1), (0, -1), (1, 0), (-1, 0),
               (1, 1), (-1, 1), (1, -1), (-1, -1),
               (0, 2), (0, -2), (2, 0), (-2, 0))
    for dx, dy in offsets:
        point = (preferred[0] + dx * offset_step,
                 preferred[1] + dy * offset_step)
        box = rotated_text_aabb(point, width, height, angle, height * 0.18)
        if not any(boxes_overlap(box, previous) for previous in occupied):
            return point, box
    return None


def principal_segment(points):
    """Return the longest segment and its normalized direction."""
    points = tuple(points)
    best = None
    for first, second in zip(points, points[1:]):
        dx, dy = second[0] - first[0], second[1] - first[1]
        length = math.hypot(dx, dy)
        if length > 1.0e-12 and (best is None or length > best[0]):
            best = (length, first, second, dx / length, dy / length)
    return best


def paths_parallel_and_close(first, second, threshold, angle_tolerance=1.0e-4):
    """Conservative parallel test for representative path segments."""
    a = principal_segment(first)
    b = principal_segment(second)
    if a is None or b is None:
        return False
    cross = abs(a[3] * b[4] - a[4] * b[3])
    if cross > angle_tolerance:
        return False
    normal = (-a[4], a[3])
    distance = abs((b[1][0] - a[1][0]) * normal[0] +
                   (b[1][1] - a[1][1]) * normal[1])
    if distance > float(threshold):
        return False
    axis = (a[3], a[4])
    def interval(path):
        values = [point[0] * axis[0] + point[1] * axis[1] for point in path]
        return min(values), max(values)
    ia, ib = interval(first), interval(second)
    return min(ia[1], ib[1]) - max(ia[0], ib[0]) > 1.0e-9


def collapse_parallel_paths(records, threshold):
    """Keep one path from each same-class close parallel cluster."""
    kept = []
    for record in records:
        if any(record.get("class_name") == previous.get("class_name") and
               paths_parallel_and_close(record.get("points", ()),
                                        previous.get("points", ()), threshold)
               for previous in kept):
            continue
        kept.append(record)
    return tuple(kept)
