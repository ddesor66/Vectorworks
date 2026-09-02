# -*- coding: utf-8 -*-
"""Vectorworks worksheet output for terrain comparisons."""
from __future__ import absolute_import

import datetime

import vs

from . import core


WORKSHEET_NAME = "PD Gelände – Massenvergleich"


def _literal(value):
    text = str(value if value is not None else "").replace("\r", " ").replace("\n", " ")
    return "'" + text if text[:1] in ("=", "+", "-", "@") else text


def _rows(result, reference_name, comparison_name, boundary):
    status_text = {
        "converged": "Konvergiert",
        "provisional": "Vorläufig – Raster verfeinern",
        "partial_coverage": "Teilüberdeckung – keine vollständige Menge",
    }.get(result.get("status"), str(result.get("status") or "Unbekannt"))
    return [
        ("GELÄNDE- UND BAUGRUBENMENGEN", "Wert", "Einheit"),
        ("Referenzmodell", reference_name, ""),
        ("Vergleichsmodell", comparison_name, ""),
        ("Berechnungsdatum", datetime.datetime.now().strftime("%d.%m.%Y %H:%M"), ""),
        ("Vorzeichen", "Vergleich − Referenz; positiv = Auftrag", ""),
        ("Methode", result.get("method", ""), ""),
        ("Qualitätsstatus", status_text, ""),
        ("Begrenzung", "%d Polygonpunkte" % len(tuple(boundary or ())), ""),
        ("Sichtbare Rasterweite", result.get("spacing_m", 0.0), "m"),
        ("Integrationsraster", result.get("integration_spacing_m", result.get("spacing_m", 0.0)), "m"),
        ("Rasterwinkel", result.get("angle_degrees", 0.0), "°"),
        ("Vergleichsfläche", result.get("comparison_area_m2", 0.0), "m²"),
        ("Fläche ohne gemeinsame Daten", result.get("no_data_area_m2", 0.0), "m²"),
        ("Abtragsfläche", result.get("cut_area_m2", 0.0), "m²"),
        ("Auftragsfläche", result.get("fill_area_m2", 0.0), "m²"),
        ("Abtragsvolumen", result.get("cut_volume_m3", 0.0), "m³"),
        ("Auftragsvolumen", result.get("fill_volume_m3", 0.0), "m³"),
        ("Differenz Auftrag − Abtrag", result.get("difference_m3", 0.0), "m³"),
        ("Maximale Abtragshöhe", result.get("maximum_cut_m", 0.0), "m"),
        ("Maximale Auftragshöhe", result.get("maximum_fill_m", 0.0), "m"),
        ("Mittlere Abtragshöhe", result.get("mean_cut_m", 0.0), "m"),
        ("Mittlere Auftragshöhe", result.get("mean_fill_m", 0.0), "m"),
        ("Konvergenzabweichung", result.get("convergence_absolute_m3", 0.0), "m³"),
        ("Relative Konvergenzabweichung", result.get("convergence_relative", 0.0) * 100.0, "%"),
        ("Gültige sichtbare Rasterfelder", result.get("valid_cells", 0), "Stk."),
        ("Keine-Daten-Felder", result.get("no_data_cells", 0), "Stk."),
    ]


def _resize(worksheet, rows, columns):
    current_rows, current_columns = vs.GetWSRowColumnCount(worksheet)
    if current_rows < rows:
        vs.InsertWSRows(worksheet, current_rows + 1, rows - current_rows)
    elif current_rows > rows:
        vs.DeleteWSRows(worksheet, rows + 1, current_rows - rows)
    if current_columns < columns:
        vs.InsertWSColumns(worksheet, current_columns + 1, columns - current_columns)
    elif current_columns > columns:
        vs.DeleteWSColumns(worksheet, columns + 1, current_columns - columns)


def _populate(worksheet, rows):
    previous = bool(vs.GetWSAutoRecalcState(worksheet))
    vs.SetWSAutoRecalcState(worksheet, False)
    try:
        _resize(worksheet, len(rows), 3)
        vs.ClearWSCell(worksheet, 1, 1, len(rows), 3)
        for row_index, row in enumerate(rows, 1):
            for column_index, value in enumerate(row, 1):
                if isinstance(value, (int, float)) and not isinstance(value, bool):
                    formula = "=%.12g" % core.number(value, "Tabellenwert")
                else:
                    formula = _literal(value)
                vs.SetWSCellFormula(worksheet, row_index, column_index,
                                    row_index, column_index, formula)
        vs.SetWSColumnWidth(worksheet, 1, 1, 260)
        vs.SetWSColumnWidth(worksheet, 2, 2, 235)
        vs.SetWSColumnWidth(worksheet, 3, 3, 80)
        vs.SetWSCellTextFormat(worksheet, 1, 1, 1, 3, 0, 11, 1)
        vs.SetWSCellFill(worksheet, 1, 1, 1, 3, 1,
                         (65535, 65535, 65535), (9000, 12000, 15000), 1)
        vs.SetWSCellTextColor(worksheet, 1, 1, 1, 3, (65535, 65535, 65535))
        vs.SetWSCellWrapTextFlag(worksheet, 1, 1, len(rows), 3, True)
        vs.SetWSCellNumberFormat(worksheet, 9, 2, len(rows), 2, 1, 3, "", "")
        vs.RecalculateWS(worksheet)
        actual_rows, actual_columns = vs.GetWSRowColumnCount(worksheet)
        if actual_rows != len(rows) or actual_columns != 3:
            raise core.TerrainError("Die Ergebnistabelle besitzt eine unerwartete Größe.")
    finally:
        vs.SetWSAutoRecalcState(worksheet, previous)


def update(result, reference_name, comparison_name, boundary):
    rows = _rows(result, reference_name, comparison_name, boundary)
    temporary_name = WORKSHEET_NAME + " – Prüfung"
    suffix = 2
    while vs.GetObject(temporary_name):
        temporary_name = WORKSHEET_NAME + " – Prüfung %d" % suffix
        suffix += 1
    temporary = vs.CreateWS(temporary_name, len(rows), 3)
    if not temporary:
        raise core.TerrainError("Die Prüfungstabelle konnte nicht angelegt werden.")
    _populate(temporary, rows)
    existing = vs.GetObject(WORKSHEET_NAME)
    if existing:
        try:
            _populate(existing, rows)
        except Exception:
            vs.SetName(temporary, WORKSHEET_NAME + " – Wiederherstellung")
            raise
        vs.DelObject(temporary)
        worksheet = existing
    else:
        vs.SetName(temporary, WORKSHEET_NAME)
        worksheet = temporary
    vs.ShowWS(worksheet, True)
    return worksheet
