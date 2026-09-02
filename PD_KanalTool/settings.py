# -*- coding: utf-8 -*-
"""Atomic per-user settings for the channel-network module."""
from __future__ import absolute_import

import copy
import json
import os
from pathlib import Path
import tempfile

from . import core


DEFAULTS = {
    "schema": 1,
    "colors": {
        "RW": [0, 26000, 65535],
        "SW": [42000, 22000, 5000],
        "MW": [43000, 8000, 52000],
    },
    "dns": list(core.DEFAULT_DNS),
    "materials": list(core.DEFAULT_MATERIALS),
    "default_kind": "RW",
    "default_dn_mm": 300,
    "default_material": "STB",
    "shaft_diameter_m": 1.0,
    "shaft_construction_material": "concrete",
    "shaft_wall_thickness_m": core.DEFAULT_CONCRETE_WALL_THICKNESS_M,
    "shaft_cover_diameter_m": 0.625,
    "shaft_cover_symbol": "",
    "shaft_cover_placement": "auto",
    "shaft_cover_rotation_deg": 0.0,
    "cover_offset_m": 1.5,
    "point_size": 9.0,
    "text_offset_mm": 3.0,
    "height_decimals": 2,
    "slope_decimals": 2,
    "length_decimals": 2,
    "label_layout": "one_line",
    "graphics_mode": "double_line",
    "single_line_type": 1,
    "axis_line_type": 2,
    "join_style": "round",
    "fillet_radius_m": 0.20,
    "flow_arrow_scale": 1.0,
    "shaft_mode": "all",
    "draw_3d": True,
    "pipe_wall_thickness_mm": 10.0,
    "hollow_3d": True,
    "stub_dn_mm": 150,
    "floor_drain_dn_mm": 150,
    "floor_drain_width_m": 0.30,
    "floor_drain_depth_m": 0.60,
    "floor_drain_symbol": "",
    "floor_drain_symbol_has_3d": False,
    "house_connection_dn_mm": 150,
    "class_prefix": "PD-KAN",
    "flow_arrow_class": "PD-KAN-Fließrichtung",
    "text_class": "PD-TX-Kanal",
    "sheet_project_name": "",
    "sheet_channel_type": "",
    "sheet_comments": "",
    "sheet_logo_path": "",
    "sheet_height_mode": "absolute",
    "sheet_clock_mode": "plan_north",
    "sheet_north_rotation_deg": 0.0,
    "sheet_include_section": True,
}


def settings_path():
    root = os.environ.get("APPDATA") or str(Path.home() / "AppData/Roaming")
    return Path(root) / "Nemetschek/Vectorworks/2026/Settings/PD_Kanalanlage.json"


def _merge(defaults, supplied):
    result = copy.deepcopy(defaults)
    if not isinstance(supplied, dict):
        return result
    for key, value in supplied.items():
        if key in result and isinstance(result[key], dict):
            result[key] = _merge(result[key], value)
        elif key in result:
            result[key] = copy.deepcopy(value)
    return result


def validate(value):
    result = _merge(DEFAULTS, value)
    if result.get("schema") != 1:
        raise core.SewerError("Unbekannte Kanaleinstellungen.")
    colors = {}
    for kind in core.KINDS:
        color = result["colors"].get(kind)
        if (not isinstance(color, (list, tuple)) or len(color) != 3 or
                any(type(component) is not int or not 0 <= component <= 65535 for component in color)):
            raise core.SewerError("Ungültige Standardfarbe für %s." % kind)
        colors[kind] = list(color)
    result["colors"] = colors
    dns = sorted({core._dn(value) for value in result.get("dns", ())})
    if not dns:
        raise core.SewerError("Mindestens ein Nenndurchmesser ist erforderlich.")
    materials = []
    for value in result.get("materials", ()):
        material = core._material(value)
        if material not in materials:
            materials.append(material)
    if not materials:
        raise core.SewerError("Mindestens ein Material ist erforderlich.")
    result["dns"], result["materials"] = dns, materials
    result["default_kind"] = core._kind(result.get("default_kind"))
    result["default_dn_mm"] = core._dn(result.get("default_dn_mm"))
    result["default_material"] = core._material(result.get("default_material"))
    if result["default_dn_mm"] not in dns:
        dns.append(result["default_dn_mm"])
        dns.sort()
    if result["default_material"] not in materials:
        materials.append(result["default_material"])
    for key, label, low, high in (
            ("shaft_diameter_m", "Schachtdurchmesser", 0.0, 20.0),
            ("shaft_wall_thickness_m", "Schachtwandstärke", 0.0, 1.0),
            ("shaft_cover_diameter_m", "Schachtdeckeldurchmesser", 0.1, 20.0),
            ("shaft_cover_rotation_deg", "Schachtdeckeldrehung", -36000.0, 36000.0),
            ("fillet_radius_m", "Ausrundungsradius", 0.01, 20.0),
            ("flow_arrow_scale", "Fließrichtungspfeil-Skalierung", 0.1, 20.0),
            ("cover_offset_m", "Deckelabstand", 0.0, 100.0),
            ("point_size", "Schriftgröße", 1.0, 200.0),
            ("text_offset_mm", "Textabstand", 0.0, 100.0)):
        result[key] = core.number(result.get(key), label)
        if not low <= result[key] <= high:
            raise core.SewerError("%s liegt außerhalb des zulässigen Bereichs." % label)
    result["pipe_wall_thickness_mm"] = core.number(
        result.get("pipe_wall_thickness_mm", 10.0), "Standard-Rohrwandstärke")
    if not 0.1 <= result["pipe_wall_thickness_mm"] <= 1000.0:
        raise core.SewerError("Die Standard-Rohrwandstärke muss zwischen 0,1 und 1000 mm liegen.")
    result["hollow_3d"] = bool(result.get("hollow_3d", True))
    result["shaft_construction_material"] = core.shaft_construction_material(
        result.get("shaft_construction_material", "concrete"))
    if result["shaft_construction_material"] == "PP" or result["shaft_diameter_m"] <= 0.0:
        result["shaft_wall_thickness_m"] = 0.0
    elif not 0.01 <= result["shaft_wall_thickness_m"] <= 1.0:
        raise core.SewerError(
            "Standard-Wandstärke des Betonschachts muss zwischen 0,01 m und 1,00 m liegen.")
    outside = result["shaft_diameter_m"] + 2.0 * result["shaft_wall_thickness_m"]
    if (outside > 0.0 and result["shaft_cover_diameter_m"] > outside):
        raise core.SewerError("Der Schachtdeckel darf nicht größer als der Schacht sein.")
    result["shaft_cover_rotation_deg"] %= 360.0
    result["shaft_cover_symbol"] = str(result.get("shaft_cover_symbol") or "").strip()
    if len(result["shaft_cover_symbol"]) > 255 or any(
            character in result["shaft_cover_symbol"] for character in "\r\n\t"):
        raise core.SewerError("Ungültiger Name des Schachtdeckelsymbols.")
    result["shaft_cover_placement"] = str(result.get("shaft_cover_placement", "auto"))
    if result["shaft_cover_placement"] not in ("auto", "center"):
        raise core.SewerError("Ungültige Standardlage des Schachtdeckels.")
    for key in ("height_decimals", "slope_decimals", "length_decimals"):
        if type(result.get(key)) is not int or not 0 <= result[key] <= 6:
            raise core.SewerError("Nachkommastellen müssen zwischen 0 und 6 liegen.")
    if result["label_layout"] not in ("one_line", "two_line"):
        raise core.SewerError("Ungültiges Beschriftungsformat.")
    if result["join_style"] not in ("round", "bevel", "miter"):
        raise core.SewerError("Ungültige Eckverbindung.")
    if result["shaft_mode"] not in ("all", "endpoints", "manual"):
        raise core.SewerError("Ungültige Schachterzeugung.")
    result["draw_3d"] = bool(result["draw_3d"])
    result["graphics_mode"] = str(result.get("graphics_mode", "double_line"))
    if result["graphics_mode"] not in core.GRAPHICS_MODES:
        raise core.SewerError("Ungültige Standard-Liniendarstellung.")
    for key, label in (("single_line_type", "Linienart der Einliniengrafik"),
                       ("axis_line_type", "Linienart der Kanalachse")):
        try:
            result[key] = int(result.get(key, 1))
        except (TypeError, ValueError) as error:
            raise core.SewerError("%s ist ungültig." % label) from error
        if not -32767 <= result[key] <= 71:
            raise core.SewerError("%s ist ungültig." % label)
    for key in ("stub_dn_mm", "floor_drain_dn_mm", "house_connection_dn_mm"):
        result[key] = core._dn(result.get(key, 150))
    for key, label, low, high in (
            ("floor_drain_width_m", "Breite des Bodenablaufs", 0.05, 5.0),
            ("floor_drain_depth_m", "Tiefe des Bodenablaufs", 0.05, 10.0)):
        result[key] = core.number(result.get(key), label)
        if not low <= result[key] <= high:
            raise core.SewerError("%s liegt außerhalb des zulässigen Bereichs." % label)
    result["floor_drain_symbol"] = str(result.get("floor_drain_symbol") or "").strip()
    if len(result["floor_drain_symbol"]) > 255 or any(
            character in result["floor_drain_symbol"] for character in "\r\n\t"):
        raise core.SewerError("Ungültiger Name des Bodenablaufsymbols.")
    result["floor_drain_symbol_has_3d"] = bool(result.get("floor_drain_symbol_has_3d", False))
    for key, label, limit in (
            ("sheet_project_name", "Bauvorhaben", 180),
            ("sheet_channel_type", "Kanalart des Schachtblatts", 120),
            ("sheet_comments", "Bemerkung des Schachtblatts", 1000),
            ("sheet_logo_path", "Logo-Dateipfad", 1024)):
        result[key] = str(result.get(key) or "").replace("\r\n", "\n").replace("\r", "\n").strip()
        if len(result[key]) > limit or (key != "sheet_comments" and "\n" in result[key]):
            raise core.SewerError("%s ist ungültig oder zu lang." % label)
    result["sheet_height_mode"] = str(result.get("sheet_height_mode", "absolute"))
    if result["sheet_height_mode"] not in ("absolute", "relative"):
        raise core.SewerError("Ungültige Höhenangabe für Schachtblätter.")
    result["sheet_clock_mode"] = str(result.get("sheet_clock_mode", "plan_north"))
    if result["sheet_clock_mode"] not in ("plan_north", "deepest_outlet"):
        raise core.SewerError("Ungültiger Winkelbezug für Schachtblätter.")
    result["sheet_north_rotation_deg"] = core.number(
        result.get("sheet_north_rotation_deg", 0.0), "Plannord-Drehung") % 360.0
    result["sheet_include_section"] = bool(result.get("sheet_include_section", True))
    for key in ("class_prefix", "flow_arrow_class", "text_class"):
        result[key] = str(result.get(key) or "").strip()
        if not result[key] or any(char in result[key] for char in "\r\n\t"):
            raise core.SewerError("Ungültiger Klassenname.")
    return result


def load(path=None):
    target = Path(path) if path else settings_path()
    try:
        value = json.loads(target.read_text(encoding="utf-8-sig"))
    except FileNotFoundError:
        value = {}
    except (OSError, ValueError) as error:
        raise RuntimeError("Kanaleinstellungen konnten nicht gelesen werden: %s" % target) from error
    return validate(value)


def save(value, path=None):
    target = Path(path) if path else settings_path()
    normalized = validate(value)
    target.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix="PD_Kanalanlage_", suffix=".tmp", dir=str(target.parent))
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(normalized, stream, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False)
        os.replace(temporary, str(target))
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return normalized
