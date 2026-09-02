# -*- coding: utf-8 -*-
"""Live collectors, Vectorworks worksheet and XLSX output."""
from __future__ import absolute_import

import datetime
import os

import vs

from PD_KanalTool import live as canal_live
from PD_LeitungsTool import core as utility_core
from PD_LeitungsTool import live as utility_live
from PD_LeitungsTool import live_objects as utility_objects
from PD_Massenermittlung.xlsx_writer import (
    STYLE_GROUP, STYLE_HEADER, STYLE_INTEGER, STYLE_NUMBER, STYLE_TOTAL,
    STYLE_WARNING, styled, write_xlsx)

from . import core


WORKSHEET_NAME = "PD Kanal- und Leitungsmengen"
SUMMARY_WORKSHEET_NAME = "PD Kanal- und Leitungssummen"
_REFRESHING = False
_LAST_REFRESH = None
_SUSPEND_DEPTH = 0
_PENDING_REFRESH = False


def _interpolate(stations, values, targets):
    stations = tuple(float(value) for value in stations)
    values = tuple(float(value) for value in values)
    result = []
    for target in targets:
        target = float(target)
        if target <= stations[0]:
            result.append(values[0])
            continue
        if target >= stations[-1]:
            result.append(values[-1])
            continue
        for index, (first, second) in enumerate(zip(stations, stations[1:])):
            if target <= second + 1e-9:
                factor = (target - first) / (second - first)
                result.append(values[index] + (values[index + 1] - values[index]) * factor)
                break
    return tuple(result)


def collect_live():
    shafts = tuple(value for _handle, value in canal_live.shaft_records())
    canals = tuple(value for _handle, value in canal_live.pipe_records())
    utility_lines = []
    for handle, data in utility_objects.objects():
        route = utility_live.read_route(handle, data, persist_move=False)
        rendered = utility_core.render_route_paths(route)
        base_stations = utility_core.stations(route["points_m"])
        for index, (points, render_stations) in enumerate(rendered):
            if route.get("surface_profile_stations_m"):
                height_stations = route["surface_profile_stations_m"][index]
                source_heights = route["surface_profile_heights_m"][index]
            else:
                height_stations = base_stations
                source_heights = route["route_heights_m"][index]
            heights = _interpolate(height_stations, source_heights, render_stations)
            utility_lines.append({
                "id": "%s-%02d" % (route["id"], index + 1),
                "route_id": route["id"], "route_name": route.get("route_name", ""),
                "utility_type": route["utility_type"], "material": route["material"],
                "dn_mm": route["dns_mm"][index],
                "outside_diameter_mm": route["outside_diameters_mm"][index],
                "outside_diameter_explicit": route["outside_diameters_explicit"],
                "length_2d_m": core.path_length_2d(points),
                "length_3d_m": core.path_length_3d(points, heights),
            })
    report = core.analyze(canals, shafts, utility_lines)
    report["metadata"] = {
        "document": str(vs.GetFName() or "Unbenannt"),
        "path": str(vs.GetFPathName() or ""),
        "created": datetime.datetime.now().strftime("%d.%m.%Y %H:%M"),
        "standard": "DIN EN 1610:2015-12 / Berichtigung 2016-09",
        "shoring": "Verbaute Gräben; 0,15 m Verbaudicke je Seite",
    }
    return report


def _style_row(values, style):
    return [styled(value, style) for value in values]


def summary_sheet(report):
    totals = report["totals"]
    rows = [
        _style_row(("KANAL- UND LEITUNGSSUMMEN", "Wert", "Einheit"), STYLE_HEADER),
        ("Dokument", report["metadata"]["document"], ""),
        ("Berechnungsstand", report["metadata"]["created"], ""),
        ("Kanal-Achslänge 2D", styled(totals["canal_length_2d_m"], STYLE_NUMBER), "m"),
        ("Kanal-Rohrlänge 3D", styled(totals["canal_length_3d_m"], STYLE_NUMBER), "m"),
        ("Versorgungsleitungen 2D", styled(totals["utility_length_2d_m"], STYLE_NUMBER), "m"),
        ("Versorgungsleitungen 3D", styled(totals["utility_length_3d_m"], STYLE_NUMBER), "m"),
        ("Schächte", styled(totals["shaft_count"], STYLE_INTEGER), "Stk."),
        ("Kanalstutzen", styled(totals["stub_count"], STYLE_INTEGER), "Stk."),
        ("Summe Schachthöhen KD-KS", styled(totals["shaft_height_m"], STYLE_NUMBER), "m"),
        ("Aushub Rohrgräben", styled(totals["trench_excavation_m3"], STYLE_NUMBER), "m³"),
        ("Aushub Schachtbaugruben", styled(totals["shaft_pit_excavation_m3"], STYLE_NUMBER), "m³"),
        _style_row(("Aushub gesamt", totals["earthwork_total_m3"], "m³"), STYLE_TOTAL),
        ("Verbau Rohrgräben", styled(totals["trench_shoring_m2"], STYLE_NUMBER), "m²"),
        ("Verbau Schachtbaugruben", styled(totals["shaft_pit_shoring_m2"], STYLE_NUMBER), "m²"),
        _style_row(("Verbau gesamt", totals["shoring_total_m2"], "m²"), STYLE_TOTAL),
        (),
        _style_row(("KANALROHRE", "DN", "Material", "Haltungen", "Länge 2D [m]",
                    "Länge 3D [m]", "Aushub [m³]", "Verbau [m²]"), STYLE_HEADER),
    ]
    for row in report["pipe_summary"]:
        rows.append((row["kind"], row["dn_mm"], row["material"], row["holding_count"],
                     row["length_2d_m"], row["length_3d_m"],
                     row["trench_excavation_m3"], row["trench_shoring_m2"]))

    rows.extend(((), _style_row(
        ("KANALSTUTZEN", "DN", "Material", "Anschlussart", "Anzahl"),
        STYLE_HEADER)))
    alignment_labels = {
        "invert": "Sohlgleich", "axis": "Achsgleich",
        "springline": "Kämpfergleich", "crown": "Scheitelgleich",
    }
    for row in report["stub_summary"]:
        rows.append((row["kind"], row["dn_mm"], row["material"],
                     alignment_labels.get(row["alignment"], row["alignment"]),
                     row["stub_count"]))

    rows.extend(((), _style_row(
        ("SCHÄCHTE", "Bauform", "Material", "Innen-Ø [m]", "Anzahl",
         "Gesamthöhe [m]", "0 Zul.", "1 Zul.", "2 Zul.", "3 Zul.",
         "4+ Zul.", "Aushub [m³]", "Verbau [m²]"), STYLE_HEADER)))
    for row in report["shaft_summary"]:
        rows.append((
            row["kind"], row["structure_type"], row["construction_material"],
            row["inside_diameter_m"], row["shaft_count"], row["shaft_height_m"],
            row["inlets_0"], row["inlets_1"], row["inlets_2"], row["inlets_3"],
            row["inlets_4_plus"], row["pit_excavation_m3"], row["pit_shoring_m2"]))

    rows.extend(((), _style_row(
        ("LEITUNGSTYP", "DN", "Material", "Einzelleitungen", "Länge 2D [m]", "Länge 3D [m]"),
        STYLE_HEADER)))
    for row in report["utility_summary"]:
        rows.append((row["utility_type"], row["dn_mm"], row["material"],
                     row["line_count"], row["length_2d_m"], row["length_3d_m"]))

    rows.extend(((), _style_row(
        ("ERDMASSEN UND VERBAU", "Menge", "Einheit"), STYLE_HEADER),
        ("Aushub Rohrgräben", totals["trench_excavation_m3"], "m³"),
        ("Aushub Schachtbaugruben", totals["shaft_pit_excavation_m3"], "m³"),
        _style_row(("Aushub gesamt", totals["earthwork_total_m3"], "m³"), STYLE_TOTAL),
        ("Verbau Rohrgräben", totals["trench_shoring_m2"], "m²"),
        ("Verbau Schachtbaugruben", totals["shaft_pit_shoring_m2"], "m²"),
        _style_row(("Verbau gesamt", totals["shoring_total_m2"], "m²"), STYLE_TOTAL),
    ))
    return {
        "name": "00_Summen", "rows": rows,
        "widths": (36, 22, 18, 18, 18, 18, 16, 16, 13, 13, 13, 18, 18),
        "freeze_rows": 1,
    }


def detail_sheets(report):

    canal_headers = ("Haltung", "Art", "DN", "OD [mm]", "Wand [mm]", "3D hohl",
                     "OD bestätigt", "Material", "Von", "Nach",
                     "X A [m]", "Y A [m]", "X E [m]", "Y E [m]",
                     "Sohle A [m]", "Sohle E [m]", "Achse A [m]", "Achse E [m]", "Gefälle [%]", "Tiefe A [m]",
                     "Tiefe E [m]", "Länge 2D [m]", "Länge 3D [m]",
                     "Grabenlänge netto [m]", "Schachtgruben-Abzug [m]",
                     "lichte Breite min [m]",
                     "lichte Breite max [m]", "Aushubbreite min [m]", "Aushubbreite max [m]",
                     "Aushub [m³]", "Verbau [m²]")
    canal_rows = [_style_row(canal_headers, STYLE_HEADER)]
    for row in report["canals"]:
        canal_rows.append((row["name"], row["kind"], row["dn_mm"],
                           row["outside_diameter_mm"], row["wall_thickness_mm"],
                           "Ja" if row["hollow_3d"] else "Nein",
                           "Ja" if row["outside_diameter_explicit"] else "NEIN",
                           row["material"], row["start_name"], row["end_name"],
                           row["start_x_m"], row["start_y_m"], row["end_x_m"], row["end_y_m"],
                           row["start_invert_m"], row["end_invert_m"],
                           row["start_axis_m"], row["end_axis_m"], row["slope_percent"], row["start_depth_m"],
                           row["end_depth_m"], row["length_2d_m"], row["length_3d_m"],
                           row["trench_length_m"], row["shaft_pit_overlap_length_m"],
                           row["minimum_clear_width_m"], row["maximum_clear_width_m"],
                           row["minimum_excavation_width_m"], row["maximum_excavation_width_m"],
                           row["excavation_volume_m3"], row["shoring_area_m2"]))

    shaft_headers = ("Schacht", "Kanalart", "Bauform", "Material", "Innen-Ø [m]",
                     "Wand [m]", "Außenbreite [m]", "Außenlänge [m]", "KD [m]", "KS [m]",
                     "Höhe KD-KS [m]", "Zuläufe", "Abläufe", "Baugrube licht B [m]",
                     "Baugrube licht L [m]", "Aushubmaß B [m]", "Aushubmaß L [m]",
                     "Aushub [m³]", "Verbau [m²]")
    shaft_rows = [_style_row(shaft_headers, STYLE_HEADER)]
    for row in report["shafts"]:
        shaft_rows.append((row["name"], row["kind"], row["structure_type"],
                           row["construction_material"], row["inside_diameter_m"],
                           row["wall_thickness_m"], row["body_width_m"], row["body_height_m"],
                           row["kd_m"], row["ks_m"], row["height_m"], row["inlets"], row["outlets"],
                           row["pit_clear_width_m"], row["pit_clear_height_m"],
                           row["pit_excavation_width_m"], row["pit_excavation_height_m"],
                           row["pit_volume_m3"], row["pit_shoring_area_m2"]))

    utility_headers = ("Trasse", "Leitungstyp", "DN", "OD [mm]",
                       "OD bestätigt", "Material", "Länge 2D [m]", "Länge 3D [m]")
    utility_rows = [_style_row(utility_headers, STYLE_HEADER)]
    for row in report["utilities"]:
        utility_rows.append((row["route_name"], row["utility_type"],
                             row["dn_mm"], row["outside_diameter_mm"],
                             "Ja" if row["outside_diameter_explicit"] else "NEIN",
                             row["material"], row["length_2d_m"], row["length_3d_m"]))

    earth_headers = ("Haltung", "Art", "DN", "OD [mm]", "Material", "Abschnitt",
                     "Station A [m]", "Station E [m]", "Länge [m]", "Tiefe A [m]",
                     "Tiefe E [m]", "lichte Breite [m]", "Aushubbreite [m]",
                     "Aushub [m³]", "Verbau [m²]")
    earth_rows = [_style_row(earth_headers, STYLE_HEADER)]
    for row in report["earth_segments"]:
        earth_rows.append((row["pipe_name"], row["kind"], row["dn_mm"],
                           row["outside_diameter_mm"], row["material"], row["segment"],
                           row["station_start_m"], row["station_end_m"], row["length_m"],
                           row["depth_start_m"], row["depth_end_m"], row["clear_width_m"],
                           row["excavation_width_m"], row["excavation_volume_m3"],
                           row["shoring_area_m2"]))

    notes = [
        _style_row(("GRUNDLAGEN UND PRÜFHINWEISE", "Wert"), STYLE_HEADER),
        ("Regelwerk", report["metadata"]["standard"]),
        ("Grabenart", report["metadata"]["shoring"]),
        ("Mindestbreite", "max(OD + DN-Zuschlag; tiefenabhängige Mindestbreite)"),
        ("DN-Zuschläge", "≤225: 0,40; ≤350: 0,50; ≤700: 0,70; ≤1200: 0,85; >1200: 1,00 m"),
        ("Tiefenbreiten", "<1,00: keine Zusatzvorgabe; bis 1,75: 0,80; bis 4,00: 0,90; >4,00: 1,00 m"),
        ("Schachtbaugrube", "rechteckig; Außenmaß + 0,50 m Arbeitsraum + 0,15 m Verbau je Seite"),
        ("Schachthöhe", "hydraulische Höhe KD − KS; keine Baukörper-Unterkante im Objektmodell"),
        ("Aushub", "Rohrgräben werden an den äußeren Grenzen der rechteckigen Schachtbaugruben gekürzt; keine Doppelmenge"),
        (), _style_row(("STATUS", "HINWEIS"), STYLE_HEADER),
    ]
    if report["warnings"]:
        notes.extend(_style_row(("WARNUNG", warning), STYLE_WARNING)
                     for warning in report["warnings"])
    else:
        notes.append(("OK", "Keine unvollständigen Mengengrundlagen erkannt."))

    return [
        {"name": "01_Kanalhaltungen", "rows": canal_rows, "widths": (26, 12, 10) + (14,) * 28, "freeze_rows": 1},
        {"name": "02_Schaechte", "rows": shaft_rows, "widths": (18, 12, 18, 16) + (15,) * 15, "freeze_rows": 1},
        {"name": "03_Leitungen", "rows": utility_rows, "widths": (24, 24, 10, 12, 14, 18, 18, 18), "freeze_rows": 1},
        {"name": "04_Erdmassen", "rows": earth_rows, "widths": (38, 12, 10, 12, 16, 12) + (16,) * 9, "freeze_rows": 1},
        {"name": "05_Annahmen_Pruefung", "rows": notes, "widths": (28, 90), "freeze_rows": 1},
    ]


def xlsx_sheets(report):
    return [summary_sheet(report)] + detail_sheets(report)


def export_xlsx(path, report=None):
    report = report or collect_live()
    return write_xlsx(path, xlsx_sheets(report), creator="plan ° D Ingenieure")


def default_xlsx_name():
    path = str(vs.GetFPathName() or "")
    base = os.path.splitext(os.path.basename(path))[0] if path else "Vectorworks"
    return "%s_Kanal-Leitungsmengen_%s.xlsx" % (
        base, datetime.datetime.now().strftime("%Y%m%d_%H%M"))


def worksheet_rows(report, summary=False):
    sheets = [summary_sheet(report)] if summary else detail_sheets(report)
    result = []
    for spec in sheets:
        result.append({"kind": "section", "values": (spec["name"].replace("_", " "),)})
        for row in spec["rows"]:
            values = []
            kind = "normal"
            for cell in row:
                if isinstance(cell, tuple) and len(cell) == 2:
                    values.append(cell[0])
                    if cell[1] == STYLE_HEADER:
                        kind = "header"
                    elif cell[1] in (STYLE_GROUP, STYLE_TOTAL):
                        kind = "total"
                    elif cell[1] == STYLE_WARNING:
                        kind = "warning"
                else:
                    values.append(cell)
            result.append({"kind": kind, "values": tuple(values)})
        result.append({"kind": "normal", "values": ()})
    return tuple(result)


def _set_cell(ws, row, column, value):
    if isinstance(value, float):
        value = ("%.12f" % value).rstrip("0").rstrip(".") or "0"
    else:
        value = str(value if value is not None else "")
        if value.startswith("="):
            value = "'" + value
    vs.SetWSCellFormulaN(ws, row, column, row, column, value)


def _resize(ws, rows, columns):
    current_rows, current_columns = vs.GetWSRowColumnCount(ws)
    if current_rows < rows:
        vs.InsertWSRows(ws, current_rows + 1, rows - current_rows)
    elif current_rows > rows:
        vs.DeleteWSRows(ws, rows + 1, current_rows - rows)
    if current_columns < columns:
        vs.InsertWSColumns(ws, current_columns + 1, columns - current_columns)
    elif current_columns > columns:
        vs.DeleteWSColumns(ws, columns + 1, current_columns - columns)
    vs.ClearWSCell(ws, 1, 1, rows, columns)


def _populate(ws, rows):
    column_count = max([len(row["values"]) for row in rows] or [1])
    original = bool(vs.GetWSAutoRecalcState(ws))
    try:
        vs.SetWSAutoRecalcState(ws, False)
        _resize(ws, len(rows), column_count)
        for row_number, row in enumerate(rows, 1):
            for column, value in enumerate(row["values"], 1):
                _set_cell(ws, row_number, column, value)
            if row["kind"] in ("section", "header", "total"):
                vs.SetWSCellTextFormat(ws, row_number, 1, row_number, column_count, -1, 10, 1)
            if row["kind"] == "section":
                vs.SetWSCellFill(ws, row_number, 1, row_number, column_count, 1, 0, 0, 5)
                vs.SetWSRowHeight(ws, row_number, row_number, 24, False, False)
            elif row["kind"] == "header":
                vs.SetWSCellFill(ws, row_number, 1, row_number, column_count, 1, 0, 0, 5)
            elif row["kind"] == "warning":
                vs.SetWSCellFill(ws, row_number, 1, row_number, column_count, 1, 0, 0, 2)
        for column in range(1, column_count + 1):
            vs.SetWSColumnWidth(ws, column, column, 110 if column > 3 else 150)
        vs.RecalculateWS(ws)
    finally:
        vs.SetWSAutoRecalcState(ws, original)


def _update_named_worksheet(name, rows, show=False):
    columns = max([len(row["values"]) for row in rows] or [1])
    temporary = vs.CreateWS(name + " – Prüfung", len(rows), columns)
    if not temporary:
        raise RuntimeError("Das Mengen-Arbeitsblatt konnte nicht vorbereitet werden.")
    try:
        _populate(temporary, rows)
        existing = vs.GetObject(name)
        if existing:
            _populate(existing, rows)
            vs.DelObject(temporary)
            worksheet = existing
        else:
            vs.SetName(temporary, name)
            worksheet = temporary
        image = vs.GetWSImage(worksheet)
        if image:
            vs.SetWSImgShowDBHeader(image, False, True)
        if show:
            vs.ShowWS(worksheet, True)
        return worksheet
    except Exception:
        if temporary:
            try:
                vs.SetName(temporary, name + " – Wiederherstellung")
            except Exception:
                pass
        raise


def update_worksheet(report=None, show=True):
    """Update the detail report and the separate summary-only worksheet."""
    report = report or collect_live()
    detail = _update_named_worksheet(
        WORKSHEET_NAME, worksheet_rows(report, summary=False), show=False)
    summary = _update_named_worksheet(
        SUMMARY_WORKSHEET_NAME, worksheet_rows(report, summary=True), show=show)
    return summary if show else detail


def begin_changes():
    """Suspend expensive worksheet rebuilds during one compound command."""
    global _SUSPEND_DEPTH
    _SUSPEND_DEPTH += 1


def end_changes(refresh=False):
    """Resume reporting and perform at most one pending rebuild."""
    global _SUSPEND_DEPTH, _PENDING_REFRESH
    if _SUSPEND_DEPTH <= 0:
        return False
    _SUSPEND_DEPTH -= 1
    if _SUSPEND_DEPTH:
        if refresh:
            _PENDING_REFRESH = True
        return False
    pending = bool(refresh or _PENDING_REFRESH)
    _PENDING_REFRESH = False
    return refresh_existing(force=True) if pending else False


def refresh_existing(force=False):
    """Refresh an already-created report; never creates one implicitly."""
    global _REFRESHING, _LAST_REFRESH, _PENDING_REFRESH
    if _SUSPEND_DEPTH:
        _PENDING_REFRESH = True
        return False
    if _REFRESHING or not (
            vs.GetObject(WORKSHEET_NAME) or vs.GetObject(SUMMARY_WORKSHEET_NAME)):
        return False
    now = datetime.datetime.now()
    if (not force and _LAST_REFRESH is not None and
            (now - _LAST_REFRESH).total_seconds() < 0.25):
        return False
    _REFRESHING = True
    try:
        update_worksheet(show=False)
        # Measure the cooldown from the completed rebuild.  A large report may
        # itself take longer than the cooldown; using its start time would let
        # the following reset event immediately rebuild the same report again.
        _LAST_REFRESH = datetime.datetime.now()
        return True
    finally:
        _REFRESHING = False
