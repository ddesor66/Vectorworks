# -*- coding: utf-8 -*-
"""Pure connection and A4 shaft-sheet layout logic.

The pipe endpoints remain the canonical connection store.  This module only
derives deterministic views for labels and reports, so a regenerated sheet
always reflects the current network without duplicated shaft data.
"""
from __future__ import absolute_import

import math

from . import core


MAX_CONNECTIONS_PER_SHEET = 24
CLOCK_MODES = ("plan_north", "deepest_outlet")
HEIGHT_MODES = ("absolute", "relative")


def _bearing(dx, dy):
    """Clockwise bearing in degrees, with drawing +Y at twelve o'clock."""
    return math.degrees(math.atan2(dx, dy)) % 360.0


def _clock_label(angle_deg):
    # Five-minute steps are accurate to 2.5 degrees and remain readable.
    minutes = int(round((float(angle_deg) % 360.0) * 2.0 / 5.0) * 5) % 720
    hours, minute = divmod(minutes, 60)
    return "%d:%02d" % (12 if hours == 0 else hours, minute)


def derive_connections(shaft, pipes, shafts, clock_mode="plan_north",
                       north_rotation_deg=0.0):
    """Return every connected pipe endpoint as one independent record."""
    shaft = core.validate_shaft(shaft, allow_hidden=True)
    if clock_mode not in CLOCK_MODES:
        raise core.SewerError("Ungültiger Bezug der Schacht-Winkeluhr.")
    north_rotation_deg = core.number(north_rotation_deg, "Plannord-Drehung") % 360.0
    shaft_map = {}
    for value in shafts:
        row = core.validate_shaft(value, allow_hidden=True)
        if row["id"] in shaft_map:
            raise core.SewerError("Doppelte Schachtidentität %s." % row["id"])
        shaft_map[row["id"]] = row
    shaft_map.setdefault(shaft["id"], shaft)
    seen_pipe_ids = set()
    rows = []
    for value in pipes:
        pipe = core.validate_pipe(value)
        if pipe["id"] in seen_pipe_ids:
            raise core.SewerError("Doppelte Haltungsidentität %s." % pipe["id"])
        seen_pipe_ids.add(pipe["id"])
        if pipe["start_id"] == shaft["id"]:
            endpoint, role = "start", "out"
            invert_m, other_id = pipe["start_invert_m"], pipe["end_id"]
        elif pipe["end_id"] == shaft["id"]:
            endpoint, role = "end", "in"
            invert_m, other_id = pipe["end_invert_m"], pipe["start_id"]
        else:
            continue
        other = shaft_map.get(other_id)
        if other is None:
            raise core.SewerError(
                "Haltung %s verweist auf einen fehlenden Nachbarschacht." % pipe["id"])
        dx = other["x_m"] - shaft["x_m"]
        dy = other["y_m"] - shaft["y_m"]
        distance = math.hypot(dx, dy)
        if distance <= 1e-9:
            raise core.SewerError(
                "Haltung %s besitzt am Schacht keine eindeutige Anschlussrichtung." % pipe["id"])
        plan_bearing = (_bearing(dx, dy) - north_rotation_deg) % 360.0
        rows.append({
            "connection_id": "%s:%s" % (pipe["id"], endpoint),
            "pipe_id": pipe["id"],
            "pipe_name": pipe.get("name", ""),
            "shaft_id": shaft["id"],
            "other_shaft_id": other_id,
            "other_shaft_name": other.get("name", ""),
            "endpoint": endpoint,
            "role": role,
            "role_label": "Zulauf" if role == "in" else "Ablauf",
            "invert_m": invert_m,
            "dn_mm": pipe["dn_mm"],
            "material": pipe["material"],
            "kind": pipe["kind"],
            "distance_m": distance,
            "direction": (dx / distance, dy / distance),
            "plan_bearing_deg": plan_bearing,
        })
    reference = 0.0
    if clock_mode == "deepest_outlet":
        outlets = [row for row in rows if row["role"] == "out"]
        if not outlets:
            raise core.SewerError(
                "Für den BFR-Winkelbezug benötigt der Schacht mindestens einen Ablauf.")
        reference = min(
            outlets, key=lambda row: (row["invert_m"], row["pipe_id"], row["endpoint"]))[
                "plan_bearing_deg"]
    for row in rows:
        row["bearing_deg"] = (row["plan_bearing_deg"] - reference) % 360.0
        row["clock"] = _clock_label(row["bearing_deg"])
    rows.sort(key=lambda row: (row["bearing_deg"], row["role"], row["pipe_id"],
                               row["endpoint"]))
    counts = {"in": 0, "out": 0}
    for row in rows:
        counts[row["role"]] += 1
        row["tag"] = ("Z" if row["role"] == "in" else "A") + str(counts[row["role"]])
    return tuple(rows)


def validate_sheet_request(shaft, connections, project_name, channel_type,
                           include_section=True):
    """Return normalized report metadata or one understandable complete error."""
    shaft = core.validate_shaft(shaft, allow_hidden=False)
    project_name = str(project_name or "").strip()
    channel_type = str(channel_type or "").strip()
    errors = []
    if not project_name:
        errors.append("Bauvorhaben")
    if not channel_type:
        errors.append("Kanalart")
    if not connections:
        errors.append("mindestens ein Zu- oder Ablauf")
    if len(connections) > MAX_CONNECTIONS_PER_SHEET:
        errors.append("höchstens %d Anschlüsse für eine lesbare A4-Seite" %
                      MAX_CONNECTIONS_PER_SHEET)
    if errors:
        raise core.SewerError(
            "Schachtblatt %s: Pflichtangaben fehlen: %s." %
            (shaft["name"], ", ".join(errors)))
    return {
        "project_name": project_name,
        "channel_type": channel_type,
        "include_section": bool(include_section),
    }


def height_text(value, preferences, mode="absolute", datum_m=0.0):
    if mode not in HEIGHT_MODES:
        raise core.SewerError("Ungültige Höhenangabe im Schachtblatt.")
    shown = core.number(value, "Höhe")
    prefix = ""
    if mode == "relative":
        shown -= core.number(datum_m, "Bezugshöhe")
        prefix = "+" if shown >= 0.0 else ""
    return prefix + core.format_number(shown, preferences["height_decimals"]) + " m"


def connection_register(connections, preferences, height_mode="absolute", datum_m=0.0):
    """Rows used by both the on-drawing information box and A4 register."""
    result = []
    for row in connections:
        result.append({
            "tag": row["tag"],
            "clock": row["clock"],
            "angle": "%s°" % core.format_number(row["bearing_deg"], 1),
            "role": row["role_label"],
            "dn": "DN %d" % row["dn_mm"],
            "material": row["material"],
            "height": height_text(row["invert_m"], preferences, height_mode, datum_m),
            "target": row["other_shaft_name"] or row["other_shaft_id"],
            "connection_id": row["connection_id"],
        })
    return tuple(result)


def plan_label_layout(connections, center=(85.5, 88.0), shaft_radius_mm=17.0,
                      left_x=28.0, right_x=143.0, min_gap_mm=8.0):
    """Deterministic two-bank leader layout for dense clock diagrams."""
    cx, cy = center
    banks = {"left": [], "right": []}
    for row in connections:
        angle = math.radians(row["bearing_deg"])
        ux, uy = math.sin(angle), math.cos(angle)
        side = "right" if ux >= 0.0 else "left"
        banks[side].append((cy - uy * 42.0, row, ux, uy))
    result = []
    for side, items in banks.items():
        items.sort(key=lambda item: (-item[0], item[1]["bearing_deg"],
                                    item[1]["connection_id"]))
        top, bottom = cy + 46.0, cy - 46.0
        ys = []
        for preferred, _row, _ux, _uy in items:
            ys.append(min(top, max(bottom, preferred)))
        for index in range(1, len(ys)):
            ys[index] = min(ys[index], ys[index - 1] - min_gap_mm)
        if ys and ys[-1] < bottom:
            shift = bottom - ys[-1]
            ys = [value + shift for value in ys]
            for index in range(len(ys) - 2, -1, -1):
                ys[index] = max(ys[index], ys[index + 1] + min_gap_mm)
        for y, (_preferred, row, ux, uy) in zip(ys, items):
            start = (cx + ux * shaft_radius_mm, cy - uy * shaft_radius_mm)
            elbow = (cx + ux * (shaft_radius_mm + 7.0), y)
            label_x = right_x if side == "right" else left_x
            result.append({
                "connection_id": row["connection_id"],
                "tag": row["tag"],
                "side": side,
                "label": (label_x, y),
                "leader": (start, elbow, (label_x - 2.0 if side == "right" else label_x + 2.0, y)),
            })
    return tuple(sorted(result, key=lambda item: item["connection_id"]))


def section_label_layout(connections, top_mm=55.0, bottom_mm=126.0,
                         min_gap_mm=4.0):
    """Place all true heights on separated label baselines without altering values."""
    values = sorted(connections, key=lambda row: (-row["invert_m"], row["connection_id"]))
    if not values:
        return ()
    high = values[0]["invert_m"]
    low = values[-1]["invert_m"]
    span = max(high - low, 0.001)
    baselines = []
    for row in values:
        preferred = top_mm + (high - row["invert_m"]) / span * (bottom_mm - top_mm)
        baselines.append(preferred)
    for index in range(1, len(baselines)):
        baselines[index] = max(baselines[index], baselines[index - 1] + min_gap_mm)
    if baselines and baselines[-1] > bottom_mm:
        shift = baselines[-1] - bottom_mm
        baselines = [value - shift for value in baselines]
        for index in range(len(baselines) - 2, -1, -1):
            baselines[index] = min(baselines[index], baselines[index + 1] - min_gap_mm)
    return tuple({"connection_id": row["connection_id"], "tag": row["tag"],
                  "invert_m": row["invert_m"], "baseline_mm": baseline}
                 for row, baseline in zip(values, baselines))
