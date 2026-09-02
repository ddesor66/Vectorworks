# -*- coding: utf-8 -*-
"""Pure preparation of object-attached Vectorworks mass records."""

from __future__ import absolute_import

import datetime
import math


RECORD_NAME = "Datenbank Massen"

# Vectorworks NewField limits names to 20 characters.  Text fields keep the
# stored SI values independent of document-unit and decimal-format changes.
FIELD_SPECS = (
    ("Lauf-ID", "", 4, 0),
    ("Zeitstempel", "", 4, 0),
    ("Plugin-Version", "", 4, 0),
    ("Objekt-ID", "", 4, 0),
    ("Klasse", "", 4, 0),
    ("Ebene", "", 4, 0),
    ("Ebenen-ID", "", 4, 0),
    ("Elementart", "", 4, 0),
    ("Elementtyp", "", 4, 0),
    ("Geometrietyp", "", 4, 0),
    ("Objekt-Länge [m]", "0", 4, 0),
    ("Objekt-Fläche [m²]", "0", 4, 0),
    ("Objekt-Stück", "0", 4, 0),
    ("Zeile Länge roh", "0", 4, 0),
    ("Zeile Länge netto", "0", 4, 0),
    ("Zeile Fläche roh", "0", 4, 0),
    ("Zeile Fläche netto", "0", 4, 0),
    ("Zeile Stück roh", "0", 4, 0),
    ("Zeile Stück netto", "0", 4, 0),
    ("Gruppe", "", 4, 0),
    ("Produkt", "", 4, 0),
    ("Beschreibung", "", 4, 0),
    ("Abmessung", "", 4, 0),
    ("Farbe", "", 4, 0),
    ("Hersteller", "", 4, 0),
    ("Anpassungen", "", 4, 0),
    ("Repräsentant", "", 4, 0),
    ("Hinweise", "", 4, 0),
)
FIELD_NAMES = tuple(spec[0] for spec in FIELD_SPECS)

if len(set(FIELD_NAMES)) != len(FIELD_NAMES):
    raise ValueError("duplicate Vectorworks record field name")
if any(len(name) > 20 for name in FIELD_NAMES):
    raise ValueError("Vectorworks record field name exceeds 20 characters")


_KIND_LABELS = {
    "line": "Linie",
    "rectangle": "Rechteck",
    "oval": "Kreis/Oval",
    "polygon": "Polygon",
    "arc": "Kreisbogen",
    "rounded_rectangle": "Abgerundetes Rechteck",
    "polyline": "Polylinie",
    "generic_geometry": "Geometrie",
    "group": "Gruppe",
    "symbol": "Symbol",
    "unsupported": "Nicht ausgewertet",
}


def _number(value):
    value = float(value or 0.0)
    if not math.isfinite(value):
        raise ValueError("record value must be finite")
    text = "%.6f" % value
    return text.rstrip("0").rstrip(".") or "0"


def _timestamp(value):
    try:
        return datetime.datetime.fromtimestamp(int(value)).isoformat(
            sep=" ", timespec="seconds")
    except (OverflowError, OSError, TypeError, ValueError):
        return str(value or "")


def _catalog_values(catalog, class_name):
    value = (catalog or {}).get(class_name, {})
    if not isinstance(value, dict):
        value = {"product": value}
    return {
        "product": str(value.get("product") or ""),
        "description": str(value.get("description") or ""),
        "dimensions": str(value.get("dimensions") or ""),
        "color": str(value.get("color") or ""),
        "manufacturer": str(value.get("manufacturer") or ""),
    }


def _adjustment_description(adjustment):
    parts = [str(adjustment.kind)]
    if abs(float(adjustment.length_delta_m)) > 1e-12:
        parts.append("ΔL=" + _number(adjustment.length_delta_m) + " m")
    if abs(float(adjustment.area_delta_m2)) > 1e-12:
        parts.append("ΔA=" + _number(adjustment.area_delta_m2) + " m²")
    if int(adjustment.piece_delta):
        parts.append("ΔStück=" + str(int(adjustment.piece_delta)))
    if adjustment.note:
        parts.append(str(adjustment.note))
    return "; ".join(parts)


def build_object_record_values(
        facts, rows, adjustments, group_titles, catalog, timestamp,
        plugin_version, run_id, group_assignments=None):
    """Return complete record values keyed by stable Vectorworks object UUID.

    Object measurements are stored once per object.  Row gross/net values are
    deliberately labelled as row totals because duplicate and parallel
    reductions can span several objects and have no truthful per-object split.
    """

    rows_by_key = dict((row.source_key, row) for row in (rows or ()))
    group_assignments = dict(group_assignments or {})
    group_titles = dict(group_titles or {})
    adjustments_by_object = {}
    for adjustment in adjustments or ():
        description = _adjustment_description(adjustment)
        for object_id in adjustment.object_ids:
            adjustments_by_object.setdefault(object_id, []).append(description)

    result = {}
    for fact in facts or ():
        key = fact.source_key
        row = rows_by_key.get(key)
        group_id = row.group_id if row is not None else group_assignments.get(key)
        group_title = str(group_titles.get(group_id, "") or "")
        catalog_value = _catalog_values(catalog, key.class_name)
        kind = getattr(fact.kind, "value", str(fact.kind))
        values = {
            "Lauf-ID": str(run_id or ""),
            "Zeitstempel": _timestamp(timestamp),
            "Plugin-Version": str(plugin_version or ""),
            "Objekt-ID": str(fact.object_id),
            "Klasse": str(key.class_name),
            "Ebene": str(key.layer_name),
            "Ebenen-ID": str(key.layer_id),
            "Elementart": str(key.element_kind),
            "Elementtyp": str(key.element_name),
            "Geometrietyp": _KIND_LABELS.get(str(kind), str(kind)),
            "Objekt-Länge [m]": _number(fact.measured_length_m),
            "Objekt-Fläche [m²]": _number(fact.measured_area_m2),
            "Objekt-Stück": str(int(fact.piece_count)),
            "Zeile Länge roh": _number(row.raw_length_m if row else 0.0),
            "Zeile Länge netto": _number(row.net_length_m if row else 0.0),
            "Zeile Fläche roh": _number(row.raw_area_m2 if row else 0.0),
            "Zeile Fläche netto": _number(row.net_area_m2 if row else 0.0),
            "Zeile Stück roh": str(int(row.raw_piece_count if row else 0)),
            "Zeile Stück netto": str(int(row.net_piece_count if row else 0)),
            "Gruppe": group_title,
            "Produkt": catalog_value["product"],
            "Beschreibung": catalog_value["description"],
            "Abmessung": catalog_value["dimensions"],
            "Farbe": catalog_value["color"],
            "Hersteller": catalog_value["manufacturer"],
            "Anpassungen": " | ".join(
                adjustments_by_object.get(fact.object_id, ())),
            "Repräsentant": str(fact.representative_id or fact.object_id),
            "Hinweise": " | ".join(str(value) for value in fact.warnings),
        }
        if set(values) != set(FIELD_NAMES):
            raise ValueError("incomplete Vectorworks object record")
        result[fact.object_id] = values
    return result
