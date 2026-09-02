# -*- coding: utf-8 -*-
"""Automatic collision-aware object and line labeling."""

from __future__ import absolute_import

from datetime import datetime
import json
import math
import uuid

import vs

from . import core_geometry as geometry
from . import ui
from . import vw_bridge


LINE_TYPES = (vw_bridge.TYPE_LINE, vw_bridge.TYPE_POLYGON,
              vw_bridge.TYPE_POLYLINE)
LAST_PLACEMENT_STATS = {"collisions": 0, "unreadable_paths": 0}


def _placement_notice():
    return ("\nAusgelassen: %d kollidierende Positionen; %d nicht lesbare Kurven."
            % (LAST_PLACEMENT_STATS["collisions"], LAST_PLACEMENT_STATS["unreadable_paths"]))


def _upright_angle(angle):
    angle = float(angle) % 360.0
    if 90.0 < angle <= 270.0:
        angle = (angle + 180.0) % 360.0
    return angle


def _line_angle(source_angle, options):
    mode = options["angle_mode"]
    if mode == 1:
        return 0.0
    if mode == 2:
        return float(options["custom_angle"])
    return _upright_angle(source_angle)


def _text_dimensions(text, point_size, layer_scale, meters_per_unit):
    line_height_m = float(point_size) / 72.0 * 0.0254 * float(layer_scale)
    lines = str(text).replace("\r\n", "\n").replace("\r", "\n").split("\n")
    width_m = max(
        line_height_m,
        max(len(line) for line in lines) * 0.56 * line_height_m)
    height_m = line_height_m * (1.0 + 1.20 * (len(lines) - 1))
    return width_m / meters_per_unit, height_m / meters_per_unit


def build_placements(records, descriptions, options, layer_scale,
                     meters_per_unit):
    LAST_PLACEMENT_STATS.update(collisions=0, unreadable_paths=0)
    point_size = options["point_size"]
    representative_height = (
        float(point_size) / 72.0 * 0.0254 * float(layer_scale) /
        meters_per_unit)
    parallel_threshold = options["parallel_cm"] / 100.0 / meters_per_unit
    occupied = []
    placements = []
    line_records = [record for record in records
                    if record["type"] in LINE_TYPES and record["points"]]
    if options["mode"] == 1:
        # Closed areas must always retain their own surface label.  Only open
        # linework participates in the "parallel up to ... cm only once"
        # reduction; its perimeter is handled separately below when requested.
        closed_records = [record for record in line_records
                          if record.get("closed")]
        open_records = [record for record in line_records
                        if not record.get("closed") and not record.get("curved")]
        curves = [record for record in line_records if record.get("curved")]
        line_records = closed_records + curves + list(geometry.collapse_parallel_paths(
            open_records, parallel_threshold))
    kept_line_ids = set(id(record) for record in line_records)

    def add(record, preferred, angle, stay_on_source=False):
        text = descriptions[record["class_name"]]
        text_width, text_height = _text_dimensions(
            text, point_size, layer_scale, meters_per_unit)
        width, height = geometry.label_frame_dimensions(
            text_width, text_height, options.get("frame_shape", 0))
        if stay_on_source:
            # The text origin is centered by create_text().  Keep that origin
            # exactly on the path; a conflicting candidate is skipped instead
            # of moving the label away from its source geometry.
            point = preferred
            box = geometry.rotated_text_aabb(
                point, width, height, angle, height * 0.18)
            if any(geometry.boxes_overlap(box, previous)
                   for previous in occupied):
                LAST_PLACEMENT_STATS["collisions"] += 1
                return False
        else:
            placed = geometry.placement_without_collision(
                preferred, width, height, angle, occupied,
                max(height * 1.25, representative_height))
            if placed is None:
                LAST_PLACEMENT_STATS["collisions"] += 1
                return False
            point, box = placed
        occupied.append(box)
        placements.append({
            "text": text, "point": point, "angle": angle,
            "class_name": record["class_name"],
            "frame_width": width, "frame_height": height,
        })
        return True

    def line_positions(record):
        requested_interval = (
            float(options.get("line_spacing_cm", 250.0)) /
            100.0 / meters_per_unit)
        if record.get("curved"):
            positions = vw_bridge.path_label_positions(record, requested_interval)
            if not positions:
                LAST_PLACEMENT_STATS["unreadable_paths"] += 1
            return positions
        return geometry.support_segment_midpoints(
            record["points"], requested_interval,
            bool(record.get("closed")))

    for record in records:
        if record["type"] == vw_bridge.TYPE_ARC:
            # A standalone arc is not a polyline; its bounding-box center is
            # not an on-curve labeling point. Do not generate a wrong label.
            LAST_PLACEMENT_STATS["unreadable_paths"] += 1
            continue
        bounds = record.get("bbox")
        if not bounds:
            continue
        is_line = record["type"] in LINE_TYPES and record["points"]
        is_closed_area = bool(record.get("closed") and record.get("area", 0.0) > 0.0)
        if is_line and not is_closed_area and options["mode"] != 1:
            for candidate, tangent in line_positions(record):
                add(record, candidate, _line_angle(tangent, options), True)
            continue
        if is_line and options["mode"] == 1:
            if id(record) not in kept_line_ids:
                continue
            if is_closed_area:
                area_spacing = max(representative_height * 7.0, 1.0e-9)
                for candidate in geometry.area_positions(
                        bounds, area_spacing, record["points"]):
                    add(record, candidate, 0.0)
                if not options["closed_boundaries"]:
                    continue
            for candidate, tangent in line_positions(record):
                add(record, candidate, _line_angle(tangent, options), True)
            continue

        if is_closed_area:
            spacing = max(representative_height * 7.0, 1.0e-9)
            for candidate in geometry.area_positions(
                    bounds, spacing, record["points"]):
                add(record, candidate, 0.0)
            if options["closed_boundaries"]:
                for candidate, tangent in line_positions(record):
                    add(record, candidate, _line_angle(tangent, options), True)
            continue

        add(record, geometry.bbox_center(bounds), 0.0)
    return tuple(placements)


def _batch_name():
    return (vw_bridge.BATCH_PREFIX +
            datetime.utcnow().strftime("%Y%m%d_%H%M%S_%f") + "_" +
            uuid.uuid4().hex[:8])


def _metadata(classes, layers, descriptions, options):
    return json.dumps({
        "version": 2,
        "classes": list(classes),
        "layers": list(layers),
        "descriptions": dict(descriptions),
        "options": dict(options),
    }, ensure_ascii=True, sort_keys=True, separators=(",", ":"))


def _read_metadata(group_handle):
    raw = vw_bridge.read_label_metadata(group_handle)
    if not raw:
        return None
    try:
        value = json.loads(raw)
    except (TypeError, ValueError):
        return None
    if not isinstance(value, dict):
        return None
    if not isinstance(value.get("classes"), list):
        return None
    if not isinstance(value.get("descriptions"), dict):
        return None
    if not isinstance(value.get("options"), dict):
        return None
    return value


def _stored_configuration(candidate):
    stored = _read_metadata(candidate[1]) if candidate else None
    if not stored:
        return None
    classes = tuple(str(value) for value in stored["classes"])
    raw_layers = stored.get("layers", ())
    layers = tuple(str(value) for value in raw_layers) if isinstance(
        raw_layers, (tuple, list)) else ()
    descriptions = dict((str(key), str(value))
                        for key, value in stored["descriptions"].items())
    for class_name in classes:
        descriptions.setdefault(class_name, class_name)
    return classes, layers, descriptions, dict(stored["options"])


def _replace_last_batch(candidate, classes, layers, descriptions, options,
                        undo_name):
    """Build and validate a replacement before deleting the old batch."""
    records = vw_bridge.collect_label_records(
        classes, layers if layers else None)
    if not records:
        raise RuntimeError(
            "In den gespeicherten Klassen und Ebenen wurden keine aktuellen Elemente gefunden.")
    placements = build_placements(
        records, descriptions, options, vw_bridge.active_layer_scale(),
        vw_bridge.units_to_meters())
    if not placements:
        raise RuntimeError(
            "Mit den gewählten Einstellungen konnte keine Beschriftung erzeugt werden.")
    new_name = _batch_name()
    try:
        vs.NameUndoEvent(undo_name)
    except Exception:
        pass
    created, new_group = vw_bridge.create_label_batch(
        placements, options, new_name,
        _metadata(classes, layers, descriptions, options))
    if not vw_bridge.delete_label_batch(candidate[0], candidate[1]):
        vw_bridge.delete_label_batch(new_name, new_group)
        raise RuntimeError(
            "Der bisherige Beschriftungsstapel konnte nicht sicher ersetzt werden. Die Änderung wurde zurückgesetzt.")
    return created


def edit_last():
    candidate = vw_bridge.last_label_batch()
    if not candidate:
        vw_bridge.alert(
            "Es wurde keine frühere automatische Beschriftung gefunden.",
            "Beschriftung")
        return
    configuration = _stored_configuration(candidate)
    if not configuration:
        vw_bridge.alert(
            "Der letzte Beschriftungsstapel enthält noch keine bearbeitbaren Einstellungen. Bitte einmal neu beschriften.",
            "Beschriftung")
        return
    classes, layers, previous_descriptions, previous_options = configuration
    descriptions = ui.class_descriptions(classes, previous_descriptions)
    if descriptions is None:
        return
    options = ui.label_options(previous_options)
    if options is None:
        return
    try:
        created = _replace_last_batch(
            candidate, classes, layers, descriptions, options,
            "Letzte automatische Beschriftung bearbeiten")
    except Exception as error:
        vw_bridge.alert(
            "Die Beschriftung konnte nicht aktualisiert werden. Der bisherige Stapel bleibt erhalten.\n" +
            str(error), "Beschriftung")
        return
    vw_bridge.alert(
        "%d Beschriftungen wurden mit den angepassten Einstellungen neu erzeugt. Klassen- und Ebenenauswahl blieben erhalten."
        % created + _placement_notice(), "Beschriftung")


def change_line_spacing():
    candidate = vw_bridge.last_label_batch()
    if not candidate:
        vw_bridge.alert(
            "Es wurde keine frühere automatische Beschriftung gefunden.",
            "Beschriftung")
        return
    configuration = _stored_configuration(candidate)
    if not configuration:
        vw_bridge.alert(
            "Der letzte Beschriftungsstapel stammt aus einer älteren Version und enthält noch keine änderbaren Einstellungen. Bitte einmal neu beschriften.",
            "Beschriftung")
        return
    classes, layers, descriptions, options = configuration
    current = float(options.get("line_spacing_cm", 250.0))
    spacing = ui.line_spacing_dialog(current)
    if spacing is None:
        return
    options["line_spacing_cm"] = spacing
    try:
        created = _replace_last_batch(
            candidate, classes, layers, descriptions, options,
            "Beschriftungsabstand ändern")
    except Exception as error:
        vw_bridge.alert(
            "Der neue Beschriftungsstapel konnte nicht erstellt werden. Der bisherige Stapel bleibt erhalten.\n" +
            str(error), "Beschriftung")
        return
    vw_bridge.alert(
        "%d Beschriftungen wurden mit %g cm Linienabstand neu erzeugt."
        % (created, spacing) + _placement_notice(), "Beschriftung")


def undo_last():
    candidate = vw_bridge.last_label_batch()
    if not candidate:
        vw_bridge.alert("Es wurde keine frühere automatische Beschriftung gefunden.",
                        "Beschriftung")
        return
    answer = vs.AlertQuestion(
        "Letzte automatische Beschriftung zurücknehmen?",
        "Beschriftungsstapel: " + candidate[0], 0,
        "Zurücknehmen", "Abbrechen", "", "")
    if answer != 1:
        return
    try:
        vs.NameUndoEvent("Letzte automatische Beschriftung zurücknehmen")
    except Exception:
        pass
    name = vw_bridge.delete_last_label_batch()
    if name:
        vw_bridge.alert("Die letzte automatische Beschriftung wurde entfernt.",
                        "Beschriftung")


def run():
    action = vs.AlertQuestion(
        "Möchten Sie eine neue automatische Beschriftung erstellen?",
        "Sie können außerdem die letzte Beschriftung zurücknehmen oder mit allen bisherigen Einstellungen weiterbearbeiten.",
        1, "Neue Beschriftung", "Abbrechen", "Letzte zurücknehmen",
        "Letzte bearbeiten")
    if action == 2:
        undo_last()
        return
    if action == 3:
        edit_last()
        return
    if action != 1:
        return
    occupied = vw_bridge.occupied_class_layers()
    if not occupied:
        vw_bridge.alert("Die Zeichnung enthält keine beschriftbaren Elemente.",
                        "Beschriftung")
        return
    scope = ui.label_source_scope(occupied)
    if not scope:
        return
    selected = ui.choose_classes(scope["classes"])
    if not selected:
        return
    descriptions = ui.class_descriptions(selected)
    if not descriptions:
        return
    options = ui.label_options()
    if not options:
        return
    records = vw_bridge.collect_label_records(selected, scope["layers"])
    if not records:
        vw_bridge.alert("In den ausgewählten Klassen wurden keine Elemente gefunden.",
                        "Beschriftung")
        return
    scale = vw_bridge.active_layer_scale()
    placements = build_placements(
        records, descriptions, options, scale, vw_bridge.units_to_meters())
    if not placements:
        vw_bridge.alert(
            "Es konnte keine kollisionsfreie Beschriftungsposition ermittelt werden.",
            "Beschriftung")
        return
    batch_name = _batch_name()
    try:
        vs.NameUndoEvent("Automatische Beschriftung erstellen")
    except Exception:
        pass
    try:
        created, _group = vw_bridge.create_label_batch(
            placements, options, batch_name,
            _metadata(selected, scope["layers"], descriptions, options))
    except Exception as error:
        vw_bridge.alert("Beschriftung fehlgeschlagen:\n" + str(error),
                        "Beschriftung")
        return
    vw_bridge.alert(
        "%d Beschriftungen wurden auf der Ebene „%s“ erzeugt. Jede Beschriftung liegt auf derselben Klasse wie ihr Quellelement."
        % (created, vw_bridge.ANNOTATION_LAYER) + _placement_notice(), "Beschriftung")
