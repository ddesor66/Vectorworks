# -*- coding: utf-8 -*-
"""Pure column-selection helpers shared by dialogs and report writers."""

from __future__ import absolute_import


HEADERS = (
    "Grafik", "Gruppe", "Klasse", "Elementtyp", "Produkt", "Beschreibung",
    "Abmessung", "Farbe", "Hersteller", "Konstruktionsebene",
    "Fläche brutto [m²]", "Fläche netto [m²]",
    "Länge brutto [m]", "Länge netto [m]",
    "Stück brutto", "Stück netto", "Gruppen/Blöcke", "Symbole",
    "Prüfhinweis",
)


WORKSHEET_WIDTHS = (
    58, 120, 220, 180, 240, 150, 140, 180, 180, 150,
    105, 105, 105, 105, 85, 85, 95, 75, 260,
)


XLSX_WIDTHS = (
    14, 22, 34, 36, 28, 38, 24, 22, 28, 28,
    16, 16, 16, 16, 14, 14, 16, 12, 48,
)


CORE_HEADERS = (
    "Gruppe", "Klasse", "Elementtyp", "Produkt", "Konstruktionsebene",
    "Fläche netto [m²]", "Länge netto [m]", "Stück netto",
)


def normalize_visible_columns(values=None):
    """Return known columns once and in the canonical report order.

    Missing, malformed, or empty persisted settings deliberately restore all
    columns so that an old or damaged status file cannot create a blank table.
    """

    if values is None or isinstance(values, (str, bytes)):
        return HEADERS
    try:
        selected = set(str(value) for value in values)
    except TypeError:
        return HEADERS
    normalized = tuple(header for header in HEADERS if header in selected)
    return normalized or HEADERS


def validate_editable_columns(values):
    columns = normalize_visible_columns(values)
    if "Klasse" not in columns and any(name in columns for name in
            ("Produkt", "Beschreibung", "Abmessung", "Farbe", "Hersteller")):
        raise ValueError(
            "Zum Bearbeiten und Wiederverwenden der Zusatzfelder muss auch "
            "die Spalte Klasse sichtbar bleiben. Bitte Klasse einblenden "
            "oder die Zusatzfelder ebenfalls ausblenden.")
    return columns


def visible_column_indices(values=None):
    selected = set(normalize_visible_columns(values))
    return tuple(
        index for index, header in enumerate(HEADERS) if header in selected)


def project_values(values, visible_columns=None):
    values = tuple(values)
    if len(values) != len(HEADERS):
        raise ValueError(
            "Die Tabellenzeile hat %d statt %d Spalten."
            % (len(values), len(HEADERS)))
    return tuple(values[index] for index in visible_column_indices(
        visible_columns))


def project_widths(widths, visible_columns=None):
    widths = tuple(widths)
    if len(widths) != len(HEADERS):
        raise ValueError(
            "Die Spaltenbreiten haben %d statt %d Einträge."
            % (len(widths), len(HEADERS)))
    return tuple(widths[index] for index in visible_column_indices(
        visible_columns))
