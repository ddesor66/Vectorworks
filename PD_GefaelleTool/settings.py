# -*- coding: utf-8 -*-
"""Persistent user preferences for PD Gefälle-Tool."""

from __future__ import absolute_import

import json
import os
import pathlib
import tempfile
from .point_output import DEFAULTS as POINT_DEFAULTS, options
from .core import SlopeError, _number
from . import label_format


DEFAULTS = {
    "labels": label_format.options(),
    "point_output": dict(POINT_DEFAULTS),
    "classes": {
        "height": {"name": "PD-GEF-Höhe", "color": [0, 42000, 0]},
        "number": {"name": "PD-GEF-Nr", "color": [0, 0, 0]},
        "line": {"name": "PD-GEF-Linie", "color": [7000, 7000, 7000]},
        "slope": {"name": "PD-GEF-Gefälle", "color": [60000, 19000, 0]},
        "length": {"name": "PD-GEF-Länge", "color": [0, 18000, 52000]},
    },
    "font": "Arial",
    "point_size": 9.0,
    "offset_mm": 2.5,
    "align_text_to_plan": False,
    "height_decimals": 2,
    "slope_decimals": 2,
    "length_decimals": 2,
    "default_level": "Standard",
}


def _clone(value):
    return json.loads(json.dumps(value))


def settings_path():
    root = os.environ.get("APPDATA")
    if not root:
        root = str(pathlib.Path.home() / "AppData" / "Roaming")
    return pathlib.Path(root) / "Nemetschek" / "Vectorworks" / "2026" / \
        "Settings" / "PD_GefaelleTool.json"


def _merge(default, supplied):
    result = _clone(default)
    if not isinstance(supplied, dict):
        return result
    for key, value in supplied.items():
        if key in result and isinstance(result[key], dict):
            result[key] = _merge(result[key], value)
        elif key in result:
            result[key] = value
    return result


def load(path=None):
    target = pathlib.Path(path) if path else settings_path()
    try:
        value = json.loads(target.read_text(encoding="utf-8-sig"))
    except FileNotFoundError:
        value = {}
    except (OSError, ValueError) as error:
        raise RuntimeError(
            "Gefälle-Einstellungen konnten nicht gelesen werden; die Datei bleibt "
            "unverändert: %s" % target) from error
    if not isinstance(value, dict):
        raise RuntimeError("Ungültige Gefälle-Einstellungen; Datei bleibt unverändert: %s" % target)
    return validate(value)


def validate(value):
    if not isinstance(value, dict):
        raise SlopeError("Ungültige Gefälle-Einstellungen.")
    result = _merge(DEFAULTS, value)
    # Normalize the original value before merging can hide its old schema.
    result["point_output"] = options(value.get("point_output"))
    result["labels"] = label_format.options(value.get("labels"))
    result["point_size"] = _number(result["point_size"], "Schriftgröße")
    result["offset_mm"] = _number(result["offset_mm"], "Textabstand")
    if not 1 <= result["point_size"] <= 200:
        raise SlopeError("Schriftgröße zwischen 1 und 200 pt eingeben.")
    if not 0 <= result["offset_mm"] <= 100:
        raise SlopeError("Textabstand zwischen 0 und 100 mm Papier eingeben.")
    for key in ("height_decimals", "slope_decimals", "length_decimals"):
        if type(result[key]) is not int or not 0 <= result[key] <= 6:
            raise SlopeError("Nachkommastellen müssen zwischen 0 und 6 liegen.")
    if not isinstance(result["align_text_to_plan"], bool):
        raise SlopeError("Ungültige Einstellung zur Plandrehung.")
    for key in ("font", "default_level"):
        if not isinstance(result[key], str) or not result[key].strip():
            raise SlopeError("Schrift und Standard-Level benötigen einen Namen.")
    for item in result["classes"].values():
        if not isinstance(item["name"], str) or not item["name"].strip():
            raise SlopeError("Jede Klasse benötigt einen Namen.")
        color = item["color"]
        if (not isinstance(color, (list, tuple)) or len(color) != 3
                or any(type(v) is not int or not 0 <= v <= 65535 for v in color)):
            raise SlopeError("Ungültige Klassenfarbe.")
    return result


def save(value, path=None):
    target = pathlib.Path(path) if path else settings_path()
    normalized = validate(value)
    target.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(
        prefix="PD_GefaelleTool_", suffix=".tmp", dir=str(target.parent))
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(normalized, stream, ensure_ascii=False, indent=2,
                      sort_keys=True, allow_nan=False)
        os.replace(temporary, str(target))
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return normalized
