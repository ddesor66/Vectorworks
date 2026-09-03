# -*- coding: utf-8 -*-
"""Atomic, per-user defaults for the independent utility-route module."""
from __future__ import absolute_import

import copy
import json
import os
from pathlib import Path
import tempfile

from . import core


DEFAULT_COLORS = {
    "Trinkwasser": [0, 26000, 65535],
    "Strom": [60000, 8000, 8000],
    "Nah-/Fernwärme": [65535, 30000, 0],
    "Gas": [60000, 50000, 0],
}

DEFAULTS = {
    "schema": 1,
    "colors": DEFAULT_COLORS,
    "types": list(core.UTILITY_TYPES),
    "default_type": "Trinkwasser",
    "materials": list(core.DEFAULT_MATERIALS),
    "default_material": "PE",
    "dns": [25, 32, 40, 50, 63, 75, 90, 100, 110, 125, 150, 200, 250, 300, 400],
    "default_dn_mm": 100,
    "count": 1,
    "spacing_m": 0.50,
    "axis_reference": "center",
    "graphics_mode": "single_line",
    "line_type": 1,
    "axis_line_type": 2,
    "round_corners": True,
    "fillet_radius_m": 0.50,
    "show_fittings": True,
    "label_bend_angles": True,
    "slope_percent": 0.0,
    "start_height_m": 100.0,
    "elevation_mode": "fixed",
    "cover_depth_m": 1.00,
    "surface_tin_type": 2,
    "show_heights": False,
    "regular_label": False,
    "label_text": "TW",
    "label_interval_m": 10.0,
    "label_frame": False,
    "label_fill": False,
    "label_bold": False,
    "label_underline": False,
    "label_rotation_deg": 0.0,
    "label_layout": "one_line",
    "font_name": "Arial",
    "font_size_pt": 9.0,
    "draw_3d": True,
    "text_color": [0, 0, 0],
    "frame_color": [0, 0, 0],
    "fill_color": [65535, 65535, 65535],
    "class_prefix": "PD-LEI",
    "axis_class": "PD-LEI-Achse",
    "fitting_class": "PD-LEI-Formteile",
    "text_class": "PD-TX-Leitung",
}


def settings_path():
    root = os.environ.get("APPDATA") or str(Path.home() / "AppData/Roaming")
    return Path(root) / "Nemetschek/Vectorworks/2026/Settings/PD_Leitungstool.json"


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


def _color(value, label):
    if (not isinstance(value, (list, tuple)) or len(value) != 3 or
            any(type(component) is not int or not 0 <= component <= 65535
                for component in value)):
        raise core.UtilityError("Ungültige Farbe für %s." % label)
    return list(value)


def validate(value):
    result = _merge(DEFAULTS, value)
    if result.get("schema") != 1:
        raise core.UtilityError("Unbekannte Leitungseinstellungen.")
    result["types"] = list(dict.fromkeys(
        list(core.UTILITY_TYPES) +
        [core.utility_type(item) for item in result.get("types", core.UTILITY_TYPES)]))
    if not result["types"]:
        raise core.UtilityError("Mindestens ein Leitungstyp ist erforderlich.")
    result["default_type"] = core.utility_type(result.get("default_type"))
    if result["default_type"] not in result["types"]:
        result["types"].append(result["default_type"])
    supplied_colors = result.get("colors", {})
    result["colors"] = {
        utility_type: _color(
            supplied_colors.get(utility_type, DEFAULT_COLORS.get(utility_type, [0, 0, 0])),
            utility_type)
        for utility_type in result["types"]
    }
    result["materials"] = list(dict.fromkeys(
        core.material(item) for item in result.get("materials", ())))
    if not result["materials"]:
        raise core.UtilityError("Mindestens ein Leitungsmaterial ist erforderlich.")
    result["default_material"] = core.material(result.get("default_material"))
    if result["default_material"] not in result["materials"]:
        result["materials"].append(result["default_material"])
    result["dns"] = sorted({core.integer(item, "Nennweite", 1, 10000)
                             for item in result.get("dns", ())})
    if not result["dns"]:
        raise core.UtilityError("Mindestens eine Nennweite ist erforderlich.")
    result["default_dn_mm"] = core.integer(
        result.get("default_dn_mm"), "Standard-Nennweite", 1, 10000)
    if result["default_dn_mm"] not in result["dns"]:
        result["dns"].append(result["default_dn_mm"])
        result["dns"].sort()
    result["count"] = core.integer(result.get("count"), "Leitungsanzahl", 1, 50)
    result["spacing_m"] = core.number(result.get("spacing_m"), "Leitungsabstand")
    result["axis_reference"] = str(result.get("axis_reference"))
    core.route_offsets(result["count"], result["spacing_m"], result["axis_reference"])
    result["graphics_mode"] = str(result.get("graphics_mode"))
    if result["graphics_mode"] not in core.GRAPHICS_MODES:
        raise core.UtilityError("Ungültige Leitungsdarstellung.")
    for key, label in (("line_type", "Linienart"),
                       ("axis_line_type", "Achslinienart")):
        result[key] = core.integer(result.get(key), label, -32767, 71)
    result["round_corners"] = bool(result.get("round_corners"))
    result["fillet_radius_m"] = core.number(
        result.get("fillet_radius_m"), "Ausrundungsradius")
    if not 0.01 <= result["fillet_radius_m"] <= 100.0:
        raise core.UtilityError("Der Ausrundungsradius muss zwischen 0,01 m und 100 m liegen.")
    result["show_fittings"] = bool(result.get("show_fittings"))
    result["label_bend_angles"] = bool(result.get("label_bend_angles"))
    result["slope_percent"] = core.number(result.get("slope_percent"), "Gefälle")
    result["start_height_m"] = core.number(result.get("start_height_m"), "Anfangshöhe")
    result["elevation_mode"] = str(result.get("elevation_mode"))
    if result["elevation_mode"] not in core.ELEVATION_MODES:
        raise core.UtilityError("Ungültiger Höhenbezug.")
    result["cover_depth_m"] = core.number(result.get("cover_depth_m"), "Überdeckung")
    if not 0.0 <= result["cover_depth_m"] <= 100.0:
        raise core.UtilityError("Die Überdeckung muss zwischen 0 und 100 m liegen.")
    result["surface_tin_type"] = core.integer(
        result.get("surface_tin_type"), "Geländemodellzustand", 0, 2)
    for key in ("show_heights", "regular_label", "label_frame", "label_fill",
                "label_bold", "label_underline", "draw_3d"):
        result[key] = bool(result.get(key))
    result["label_text"] = str(result.get("label_text") or "").strip()
    result["label_interval_m"] = core.number(
        result.get("label_interval_m"), "Beschriftungsabstand")
    if result["label_interval_m"] <= 0.0:
        raise core.UtilityError("Der Beschriftungsabstand muss größer als null sein.")
    result["label_rotation_deg"] = core.number(
        result.get("label_rotation_deg", 0.0), "Beschriftungsdrehung") % 360.0
    result["label_layout"] = str(result.get("label_layout", "one_line"))
    if result["label_layout"] not in core.LABEL_LAYOUTS:
        raise core.UtilityError("Ungültiges Beschriftungsformat.")
    result["font_name"] = str(result.get("font_name") or "Arial").strip()
    result["font_size_pt"] = core.number(result.get("font_size_pt"), "Schriftgröße")
    if not result["font_name"] or not 1.0 <= result["font_size_pt"] <= 200.0:
        raise core.UtilityError("Schriftart oder Schriftgröße ist ungültig.")
    for key in ("text_color", "frame_color", "fill_color"):
        result[key] = _color(result.get(key), key)
    for key in ("class_prefix", "axis_class", "fitting_class", "text_class"):
        result[key] = str(result.get(key) or "").strip()
        if not result[key] or any(char in result[key] for char in "\r\n\t"):
            raise core.UtilityError("Ungültiger Klassenname.")
    return result


def load(path=None):
    target = Path(path) if path else settings_path()
    try:
        supplied = json.loads(target.read_text(encoding="utf-8-sig"))
    except FileNotFoundError:
        supplied = {}
    except (OSError, ValueError) as error:
        raise RuntimeError("Leitungseinstellungen konnten nicht gelesen werden: %s" % target) from error
    return validate(supplied)


def save(value, path=None):
    target = Path(path) if path else settings_path()
    normalized = validate(value)
    target.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(
        prefix="PD_Leitungstool_", suffix=".tmp", dir=str(target.parent))
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(normalized, stream, ensure_ascii=False, indent=2,
                      sort_keys=True, allow_nan=False)
        os.replace(temporary, str(target))
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return normalized
