# -*- coding: utf-8 -*-
"""Vectorworks 2026 sheet-layer preview, PDF and print adapter."""
from __future__ import absolute_import

import math
import os
import re
import uuid

import vs

from . import core
from . import shaft_sheet
from . import vw_adapter as adapter


A4_LANDSCAPE_INCHES = (11.6929133858, 8.2677165354)
SHEET_LAYER_TYPE = 2
SHEET_PREFIX = "PD-Schachtblatt-"
SHEET_CLASS = "PD-KAN-Schachtblatt"
BLACK = (0, 0, 0)
LIGHT_GRAY = (54000, 54000, 54000)


def _safe_name(value, fallback="Schacht"):
    result = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", str(value or ""))
    result = re.sub(r"\s+", " ", result).strip(" .")
    return (result or fallback)[:42].rstrip(" .") or fallback


def _page_xy(x_mm, y_mm, factor):
    """Top-left millimetres to centered Vectorworks sheet coordinates."""
    return ((float(x_mm) - 148.5) / 1000.0 / factor,
            (105.0 - float(y_mm)) / 1000.0 / factor)


def _new_handle(message):
    handle = vs.LNewObj()
    if not handle:
        raise core.SewerError(message)
    return handle


def _style(handle, fill=False, gray=False, weight=7):
    vs.SetClass(handle, SHEET_CLASS)
    vs.SetPenFore(handle, BLACK)
    vs.SetLW(handle, int(weight))
    vs.SetFPat(handle, 1 if fill else 0)
    if fill:
        vs.SetFillFore(handle, LIGHT_GRAY if gray else (65535, 65535, 65535))
    return handle


def _line(first, second, factor, weight=7):
    vs.MoveTo(_page_xy(first[0], first[1], factor))
    vs.LineTo(_page_xy(second[0], second[1], factor))
    return _style(_new_handle("Schachtblatt-Linie konnte nicht erzeugt werden."), weight=weight)


def _polyline(points, factor, closed=False, fill=False, gray=False, weight=7):
    vs.BeginPoly()
    for point in points:
        vs.AddPoint(_page_xy(point[0], point[1], factor))
    vs.EndPoly()
    handle = _new_handle("Schachtblatt-Polygon konnte nicht erzeugt werden.")
    vs.SetPolyClosed(handle, bool(closed))
    return _style(handle, fill=fill, gray=gray, weight=weight)


def _rect(left, top, right, bottom, factor, fill=False, gray=False, weight=7):
    vs.Rect(_page_xy(left, top, factor), _page_xy(right, bottom, factor))
    return _style(_new_handle("Schachtblatt-Rahmen konnte nicht erzeugt werden."),
                  fill=fill, gray=gray, weight=weight)


def _oval(cx, cy, rx, ry, factor, fill=False, gray=False, weight=7):
    vs.Oval(_page_xy(cx - rx, cy - ry, factor), _page_xy(cx + rx, cy + ry, factor))
    return _style(_new_handle("Schachtblatt-Kreis konnte nicht erzeugt werden."),
                  fill=fill, gray=gray, weight=weight)


def _wrap(value, width):
    result = []
    for paragraph in str(value or "").replace("\r", "").split("\n"):
        words = paragraph.split()
        line = ""
        for word in words:
            candidate = word if not line else line + " " + word
            if line and len(candidate) > width:
                result.append(line)
                line = word
            else:
                line = candidate
        result.append(line)
    return "\r".join(result)


def _text(value, x, y, factor, size=7.0, width_mm=0.0, bold=False, center=False):
    value = str(value or "")
    if not value:
        return None
    vs.TextOrigin(_page_xy(x, y, factor))
    vs.CreateText(value.replace("\n", "\r"))
    handle = _new_handle("Schachtblatt-Text konnte nicht erzeugt werden.")
    vs.SetTextStyleRef(handle, 0)
    font = int(vs.GetFontID("Arial") or 0)
    if font:
        vs.SetTextFont(handle, 0, len(value), font)
    vs.SetTextSize(handle, 0, len(value), float(size))
    if bold:
        vs.SetTextStyle(handle, 0, len(value), 1)
    vs.SetTextJust(handle, 2 if center else 1)
    vs.SetTextVertAlignN(handle, 3)
    if width_mm > 0.0:
        vs.SetTextWidth(handle, width_mm / 1000.0 / factor)
    _style(handle, weight=13 if bold else 7)
    return handle


def _ensure_class():
    active = str(vs.ActiveClass() or "")
    try:
        vs.NameClass(SHEET_CLASS)
        vs.SetClUseGraphic(SHEET_CLASS, True)
        vs.SetClFPat(SHEET_CLASS, 0)
        vs.SetClPenFore(SHEET_CLASS, BLACK)
        vs.SetClPenBack(SHEET_CLASS, BLACK)
        vs.SetClLW(SHEET_CLASS, 7)
    finally:
        if active:
            vs.NameClass(active)


def _default_logo_path():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(root, "PD_KlassenMengen", "assets", "PD_Logo.png")


def _normalized_bbox(handle):
    value = vs.GetBBox(handle)
    if (isinstance(value, (tuple, list)) and len(value) == 2 and
            all(isinstance(point, (tuple, list)) and len(point) == 2 for point in value)):
        points = value
    elif isinstance(value, (tuple, list)) and len(value) == 4:
        points = ((value[0], value[1]), (value[2], value[3]))
    else:
        raise core.SewerError("Logo-Begrenzung konnte nicht gelesen werden.")
    left, right = sorted((float(points[0][0]), float(points[1][0])))
    bottom, top = sorted((float(points[0][1]), float(points[1][1])))
    if right - left <= 1e-9 or top - bottom <= 1e-9:
        raise core.SewerError("Das Firmenlogo besitzt keine gültige Größe.")
    return left, bottom, right, top


def _logo(path, factor):
    selected = str(path or "").strip() or _default_logo_path()
    if not os.path.isfile(selected):
        if path:
            raise core.SewerError("Firmenlogo wurde nicht gefunden: %s" % selected)
        _text("plan’d", 41.0, 19.5, factor, size=17.0, bold=True, center=True)
        return
    handle = vs.ImportImageFile(selected, _page_xy(41.0, 21.0, factor))
    if not handle:
        raise core.SewerError("Firmenlogo konnte nicht importiert werden.")
    left, bottom, right, top = _normalized_bbox(handle)
    target_width = 38.0 / 1000.0 / factor
    target_height = 16.0 / 1000.0 / factor
    scale = min(target_width / (right - left), target_height / (top - bottom))
    center_x, center_y = (left + right) * 0.5, (bottom + top) * 0.5
    vs.HScale2D(handle, center_x, center_y, scale, scale, False)
    left, bottom, right, top = _normalized_bbox(handle)
    target = _page_xy(41.0, 21.0, factor)
    vs.HMove(handle, target[0] - (left + right) * 0.5,
             target[1] - (bottom + top) * 0.5)
    vs.SetClass(handle, SHEET_CLASS)


def _cover_position(shaft, connections, radius_mm, cover_radius_mm):
    if shaft.get("cover_placement") == "center":
        return 0.0, 0.0
    # core expects mathematical directions: 0° is +X, counter-clockwise.
    angles = [math.degrees(math.atan2(row["direction"][1], row["direction"][0]))
              for row in connections]
    direction = math.radians(core.largest_angular_gap_bisector(angles))
    offset = max(0.0, radius_mm - cover_radius_mm)
    return math.cos(direction) * offset, -math.sin(direction) * offset


def _draw_plan(shaft, connections, config, preferences, factor):
    left, top, right, bottom = 20.0, 34.0, 151.0, 133.0
    _rect(left, top, right, bottom, factor, weight=10)
    _text("DRAUFSICHT / WINKELUHR", left + 3.0, top + 3.0, factor, size=8.0, bold=True)
    reference = ("12 Uhr = Plannord" if config["clock_mode"] == "plan_north" else
                 "12 Uhr = tiefster Ablauf (BFR)")
    _text(reference, 104.0, top + 3.0, factor, size=7.0, center=False)
    cx, cy = 85.5, 84.0
    radius = 17.0
    if shaft["structure_type"] == "special" and shaft.get("special_outline_m"):
        values = shaft["special_outline_m"]
        xs, ys = [row[0] for row in values], [row[1] for row in values]
        width, height = max(xs) - min(xs), max(ys) - min(ys)
        scale = min(34.0 / max(width, 0.001), 34.0 / max(height, 0.001))
        outline = [(cx + (x - (min(xs) + max(xs)) * 0.5) * scale,
                    cy - (y - (min(ys) + max(ys)) * 0.5) * scale) for x, y in values]
        _polyline(outline, factor, closed=True, fill=False, weight=13)
    else:
        _oval(cx, cy, radius, radius, factor, fill=False, weight=13)
        if (shaft["construction_material"] == "concrete" and
                shaft["wall_thickness_m"] > 0.0):
            outside_m = core.shaft_outer_diameter_m(shaft)
            inner_radius = radius * shaft["diameter_m"] / outside_m
            _oval(cx, cy, inner_radius, inner_radius, factor, fill=False, weight=7)
    body_diameter = (core.shaft_outer_diameter_m(shaft)
                     if shaft["structure_type"] == "round" else shaft.get("diameter_m", 1.0))
    cover_radius = max(3.0, radius * shaft.get("cover_diameter_m", 0.625) /
                       max(body_diameter, 0.001))
    ox, oy = _cover_position(shaft, connections, radius, min(radius, cover_radius))
    _oval(cx + ox, cy + oy, min(radius, cover_radius), min(radius, cover_radius),
          factor, fill=False, weight=7)
    # Clock ticks and cardinal labels make the angular reference explicit.
    for angle, label in ((0, "12"), (90, "3"), (180, "6"), (270, "9")):
        radians = math.radians(angle)
        ux, uy = math.sin(radians), -math.cos(radians)
        _line((cx + ux * 20.0, cy + uy * 20.0),
              (cx + ux * 23.0, cy + uy * 23.0), factor)
        _text(label, cx + ux * 26.0, cy + uy * 26.0, factor, size=6.5, center=True)
    layout = {row["connection_id"]: row
              for row in shaft_sheet.plan_label_layout(
                  connections, center=(cx, cy), shaft_radius_mm=radius,
                  left_x=left + 8.0, right_x=right - 8.0, min_gap_mm=7.0)}
    for row in connections:
        angle = math.radians(row["bearing_deg"])
        ux, uy = math.sin(angle), -math.cos(angle)
        _line((cx + ux * radius, cy + uy * radius),
              (cx + ux * 31.0, cy + uy * 31.0), factor, weight=10)
        item = layout[row["connection_id"]]
        for first, second in zip(item["leader"], item["leader"][1:]):
            _line(first, second, factor)
        text = "%s %s %s" % (
            row["tag"], "Z" if row["role"] == "in" else "A",
            shaft_sheet.height_text(row["invert_m"], preferences,
                                    config["height_mode"], shaft["ks_m"]))
        _text(text, item["label"][0], item["label"][1] - 1.5, factor,
              size=7.0, center=item["side"] == "right")
    if config["clock_mode"] == "plan_north":
        _line((left + 8.0, bottom - 7.0), (left + 8.0, bottom - 19.0), factor, weight=10)
        _polyline(((left + 8.0, bottom - 19.0), (left + 5.5, bottom - 14.0),
                   (left + 10.5, bottom - 14.0)), factor, closed=True, fill=True, weight=10)
        _text("N", left + 8.0, bottom - 22.0, factor, size=7.0, bold=True, center=True)


def _draw_section(shaft, connections, config, preferences, factor):
    left, top, right, bottom = 154.0, 34.0, 287.0, 133.0
    _rect(left, top, right, bottom, factor, weight=10)
    _text("SCHEMATISCHER SCHNITT – NICHT MASSSTÄBLICH",
          left + 3.0, top + 3.0, factor, size=8.0, bold=True)
    cx = 211.0
    shaft_left, shaft_right = cx - 18.0, cx + 18.0
    shaft_top, shaft_bottom = top + 20.0, bottom - 12.0
    _rect(shaft_left, shaft_top, shaft_right, shaft_bottom, factor, weight=13)
    if (shaft["construction_material"] == "concrete" and
            shaft["wall_thickness_m"] > 0.0):
        outside_m = core.shaft_outer_diameter_m(shaft)
        inner_half_width = 18.0 * shaft["diameter_m"] / outside_m
        _line((cx - inner_half_width, shaft_top),
              (cx - inner_half_width, shaft_bottom), factor)
        _line((cx + inner_half_width, shaft_top),
              (cx + inner_half_width, shaft_bottom), factor)
    _rect(cx - 7.0, shaft_top - 2.0, cx + 7.0, shaft_top + 2.0, factor, weight=13)
    _line((shaft_left - 8.0, shaft_top), (shaft_right + 8.0, shaft_top), factor)
    _text("KD %s" % shaft_sheet.height_text(
        shaft["kd_m"], preferences, config["height_mode"], shaft["ks_m"]),
        shaft_right + 10.0, shaft_top - 1.5, factor, size=7.0)
    _line((shaft_left - 8.0, shaft_bottom), (shaft_right + 8.0, shaft_bottom), factor)
    _text("KS %s" % shaft_sheet.height_text(
        shaft["ks_m"], preferences, config["height_mode"], shaft["ks_m"]),
        shaft_right + 10.0, shaft_bottom - 1.5, factor, size=7.0)
    high = max([shaft["kd_m"]] + [row["invert_m"] for row in connections])
    low = min([shaft["ks_m"]] + [row["invert_m"] for row in connections])
    span = max(high - low, 0.001)
    layout = {row["connection_id"]: row
              for row in shaft_sheet.section_label_layout(
                  connections, top_mm=shaft_top + 8.0, bottom_mm=shaft_bottom - 5.0)}
    for index, row in enumerate(connections):
        actual_y = shaft_top + (high - row["invert_m"]) / span * (shaft_bottom - shaft_top)
        side = -1.0 if index % 2 == 0 else 1.0
        edge = shaft_left if side < 0 else shaft_right
        outer = edge + side * 14.0
        _line((edge, actual_y), (outer, actual_y), factor, weight=10)
        baseline = layout[row["connection_id"]]["baseline_mm"]
        label_x = left + 3.0 if side < 0 else right - 54.0
        _line((outer, actual_y), (outer + side * 4.0, baseline), factor)
        text = "%s %s / DN %d" % (
            row["tag"], shaft_sheet.height_text(
                row["invert_m"], preferences, config["height_mode"], shaft["ks_m"]),
            row["dn_mm"])
        _text(text, label_x, baseline - 1.5, factor, size=6.8)
    _text("Tiefe %s m" % core.format_number(
        shaft["kd_m"] - shaft["ks_m"], preferences["length_decimals"]),
        left + 4.0, bottom - 7.0, factor, size=7.0, bold=True)
    construction = core.shaft_construction_material_label(shaft["construction_material"])
    if shaft["construction_material"] == "concrete":
        construction += " | Øi %s m | t %s m | Øa %s m" % (
            core.format_number(shaft["diameter_m"], preferences["length_decimals"]),
            core.format_number(shaft["wall_thickness_m"], preferences["length_decimals"]),
            core.format_number(core.shaft_outer_diameter_m(shaft),
                               preferences["length_decimals"]))
    else:
        construction += " | Ø %s m" % core.format_number(
            shaft["diameter_m"], preferences["length_decimals"])
    _text(construction, left + 4.0, bottom - 2.5, factor, size=6.5)


def _draw_register(shaft, connections, config, preferences, factor):
    left, top, right, bottom = 20.0, 135.0, 287.0, 181.0
    _rect(left, top, right, bottom, factor, weight=10)
    rows = shaft_sheet.connection_register(
        connections, preferences, config["height_mode"], shaft["ks_m"])
    block_width = (right - left) / 3.0
    for block in range(3):
        block_left = left + block * block_width
        if block:
            _line((block_left, top), (block_left, bottom), factor)
        _text("Nr  Art  Uhr/°  DN  Mat.  Anschlusshöhe  Ziel",
              block_left + 2.0, top + 2.0, factor, size=6.6, bold=True)
        _line((block_left, top + 7.0), (block_left + block_width, top + 7.0), factor)
        for local, row in enumerate(rows[block * 8:(block + 1) * 8]):
            y = top + 9.0 + local * 4.5
            role = "ZU" if row["role"] == "Zulauf" else "AB"
            text = "%s  %s  %s/%s  %s  %s  %s  %s" % (
                row["tag"], role, row["clock"], row["angle"], row["dn"],
                row["material"], row["height"], row["target"])
            _text(_wrap(text, 53), block_left + 2.0, y, factor, size=6.6)


def _draw_footer(shaft, config, factor):
    _rect(20.0, 183.0, 168.0, 200.0, factor, weight=10)
    _text("BEMERKUNGEN", 22.0, 185.0, factor, size=7.0, bold=True)
    _text(_wrap(config.get("comments", "—") or "—", 85),
          22.0, 190.0, factor, size=6.8, width_mm=142.0)
    _rect(170.0, 183.0, 287.0, 200.0, factor, weight=10)
    _text("Schachtblatt", 172.0, 185.0, factor, size=7.0, bold=True)
    _text("Schacht: %s" % shaft["name"], 205.0, 185.0, factor, size=7.0)
    _text("Bauart: %s" % core.shaft_construction_material_label(
        shaft["construction_material"]), 172.0, 195.0, factor, size=6.5)
    _text("Winkelbezug: %s" % (
        "Plannord" if config["clock_mode"] == "plan_north" else "tiefster Ablauf (BFR)"),
        172.0, 190.0, factor, size=6.5)
    _text("Höhen: %s" % (
        "absolut" if config["height_mode"] == "absolute" else "relativ zu KS"),
        236.0, 190.0, factor, size=6.5)
    _text("PD-Tools", 264.0, 195.0, factor, size=6.5)


def _render_page(shaft, connections, config, preferences, factor):
    _rect(10.0, 10.0, 287.0, 200.0, factor, weight=13)
    _rect(20.0, 10.0, 62.0, 32.0, factor, weight=10)
    _rect(64.0, 10.0, 207.0, 32.0, factor, weight=10)
    _rect(209.0, 10.0, 287.0, 32.0, factor, weight=10)
    _logo(config.get("logo_path", ""), factor)
    _text("SCHACHTBLATT", 67.0, 13.0, factor, size=12.0, bold=True)
    _text(_wrap(config["project_name"], 58), 67.0, 21.0, factor,
          size=8.0, width_mm=135.0)
    _text("Schacht: %s" % shaft["name"], 212.0, 13.0, factor, size=9.0, bold=True)
    _text(_wrap(config["channel_type"], 34), 212.0, 21.0, factor,
          size=7.0, width_mm=72.0)
    _draw_plan(shaft, connections, config, preferences, factor)
    if config.get("include_section", True):
        _draw_section(shaft, connections, config, preferences, factor)
    else:
        _rect(154.0, 34.0, 287.0, 133.0, factor, weight=10)
        _text("Schnitt in den Ausgabeeinstellungen deaktiviert.",
              160.0, 80.0, factor, size=8.0)
    _draw_register(shaft, connections, config, preferences, factor)
    _draw_footer(shaft, config, factor)


def _create_sheet_layer(name, shaft, connections, config, preferences):
    layer = vs.CreateLayer(name, SHEET_LAYER_TYPE)
    if not layer:
        raise core.SewerError("Layoutebene für Schachtblatt konnte nicht angelegt werden.")
    try:
        vs.Layer(name)
        vs.SetDrawingRect(*A4_LANDSCAPE_INCHES)
        actual = vs.TBB_GetPageArea(layer)
        if (not isinstance(actual, (tuple, list)) or len(actual) < 2 or
                abs(float(actual[0]) - A4_LANDSCAPE_INCHES[0]) > 0.01 or
                abs(float(actual[1]) - A4_LANDSCAPE_INCHES[1]) > 0.01):
            raise core.SewerError(
                "Vectorworks hat für das Schachtblatt nicht DIN A4 quer übernommen.")
        _render_page(shaft, connections, config, preferences, adapter.units_to_meters())
        return layer
    except Exception:
        vs.DelObject(layer)
        raise


def prepare_pages(shaft_handles, config, preferences, read_shaft, all_shafts, all_pipes):
    """Validate all pages before replacing any previous managed preview."""
    _ensure_class()
    shafts = tuple(all_shafts)
    pipes = tuple(all_pipes)
    pages = []
    seen = set()
    for handle in shaft_handles:
        shaft = read_shaft(handle)
        if shaft["id"] in seen:
            continue
        seen.add(shaft["id"])
        if shaft["structure_type"] not in ("round", "special"):
            raise core.SewerError(
                "%s ist kein runder Schacht oder Sonderschacht." % shaft["name"])
        connections = shaft_sheet.derive_connections(
            shaft, pipes, shafts, config["clock_mode"], config["north_rotation_deg"])
        shaft_sheet.validate_sheet_request(
            shaft, connections, config["project_name"], config["channel_type"],
            config.get("include_section", True))
        pages.append((shaft, connections))
    if not pages:
        raise core.SewerError("Bitte einen oder mehrere Schächte markieren.")
    previous = vs.ActLayer()
    previous_name = str(vs.GetLName(previous) or "") if previous else ""
    created = []
    try:
        for shaft, connections in pages:
            temp_name = "%sTMP-%s" % (SHEET_PREFIX, uuid.uuid4().hex[:10])
            layer = _create_sheet_layer(
                temp_name, shaft, connections, config, preferences)
            created.append((layer, temp_name, SHEET_PREFIX + _safe_name(shaft["name"])))
        final_names = []
        for layer, _temp_name, final_name in created:
            old = vs.GetLayerByName(final_name)
            if old and old != layer:
                vs.DelObject(old)
            vs.SetName(layer, final_name)
            if str(vs.GetLName(layer) or "") != final_name:
                raise core.SewerError("Schachtblatt-Layoutebene konnte nicht benannt werden.")
            final_names.append(final_name)
        vs.Layer(final_names[0])
        vs.ReDrawAll()
        return tuple(final_names)
    except Exception:
        for layer, _temp_name, _final_name in created:
            try:
                vs.DelObject(layer)
            except Exception:
                pass
        if previous_name and vs.GetLayerByName(previous_name):
            vs.Layer(previous_name)
        raise


def export_pdf(layer_names, document_name):
    """Export all prepared sheets into the single file chosen by the user."""
    if not layer_names:
        raise core.SewerError("Es sind keine Schachtblätter für den PDF-Export vorbereitet.")
    if not vs.AcquireExportPDFSettingsAndLocation(False):
        return False
    opened = False
    try:
        if not vs.OpenPDFDocument(_safe_name(document_name, "PD_Schachtblaetter")):
            raise core.SewerError("Vectorworks konnte die gemeinsame PDF-Datei nicht öffnen.")
        opened = True
        for name in layer_names:
            if not vs.GetLayerByName(name):
                raise core.SewerError("Schachtblatt-Layoutebene fehlt: %s" % name)
            vs.ExportPDFPages(name)
        vs.ClosePDFDocument()
        opened = False
        return True
    finally:
        if opened:
            vs.ClosePDFDocument()


def print_pages(layer_names):
    """Use Vectorworks' documented print dialog for every prepared page."""
    if not layer_names:
        raise core.SewerError("Es sind keine Schachtblätter zum Drucken vorbereitet.")
    for name in layer_names:
        if not vs.GetLayerByName(name):
            raise core.SewerError("Schachtblatt-Layoutebene fehlt: %s" % name)
        vs.Layer(name)
        vs.PrintUsingPrintDialog()
    vs.Layer(layer_names[0])
