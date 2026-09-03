# -*- coding: utf-8 -*-
"""Live collectors, Vectorworks worksheet and XLSX output."""
from __future__ import absolute_import

import datetime
import os
import uuid

import vs

from PD_KanalTool import live as canal_live
from PD_KanalTool import core as canal_core
from PD_KanalTool import live_objects as canal_objects
from PD_KanalTool import settings as canal_settings
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
_REPORT_DIRTY = False
DELETE_OBSERVER_NAME = "PD-MENGEN-LOESCHBEOBACHTER"
DELETE_OBSERVER_CLASS = "PD-Systemdaten"
RESET_ON_OWNER_DELETE = 5
REPORT_MODES = ("summary", "details", "all")


def _quantity_owners():
    """Return every live object whose deletion changes the quantity report."""
    owners = [
        handle for handle, data in canal_objects.objects()
        if data.get("role") in (
            "sewer_pipe", "sewer_shaft", "sewer_fitting",
            "sewer_floor_drain", "sewer_house_connection", "sewer_rigole")]
    owners.extend(handle for handle, _data in utility_objects.objects())
    return tuple(owners)


def _delete_observer():
    handle = vs.GetObject(DELETE_OBSERVER_NAME)
    if handle:
        data = canal_objects.data_of(handle)
        if data and data.get("role") == canal_objects.QUANTITY_OBSERVER_ROLE:
            return handle
        raise RuntimeError(
            "Der reservierte Mengen-Löschbeobachter ist durch ein anderes Objekt belegt.")
    created = []
    data = {
        "schema": canal_core.SCHEMA,
        "role": canal_objects.QUANTITY_OBSERVER_ROLE,
    }
    handle = canal_objects._new_object(
        (0.0, 0.0), data, DELETE_OBSERVER_NAME, created)
    active = str(vs.ActiveClass() or "")
    try:
        vs.NameClass(DELETE_OBSERVER_CLASS)
        vs.SetClass(handle, DELETE_OBSERVER_CLASS)
    finally:
        if active:
            vs.NameClass(active)
    return handle


def synchronize_delete_observer():
    """Attach one invisible reset target to all quantity-relevant objects."""
    required = ("AddAssociation", "RemoveAssociation", "CreateCustomObjectN")
    if any(not hasattr(vs, name) for name in required):
        # Pure worksheet tests and older non-Vectorworks runtimes do not expose
        # object events. The production host has all three documented calls.
        return None
    owners = _quantity_owners()
    if not owners:
        return vs.GetObject(DELETE_OBSERVER_NAME) or None
    observer = _delete_observer()
    for owner in owners:
        removed = 0
        for _index in range(32):
            if not vs.RemoveAssociation(owner, RESET_ON_OWNER_DELETE, observer):
                break
            removed += 1
        if not vs.AddAssociation(owner, RESET_ON_OWNER_DELETE, observer):
            for _index in range(removed):
                vs.AddAssociation(owner, RESET_ON_OWNER_DELETE, observer)
            raise RuntimeError(
                "Mengenaktualisierung konnte nicht mit einem Zeichnungsobjekt verknüpft werden.")
    return observer


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


def collect_live(preferences=None):
    preferences = preferences or canal_settings.load()
    shafts = tuple(value for _handle, value in canal_live.shaft_records())
    canals = tuple(value for _handle, value in canal_live.pipe_records())
    rigoles = tuple(value for _handle, value in canal_live.rigole_records())
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
    report = core.analyze(
        canals, shafts, utility_lines, rigoles=rigoles,
        include_pavement=preferences.get("earthwork_include_pavement", False),
        pavement_thickness_m=preferences.get(
            "earthwork_pavement_thickness_m", 0.0))
    object_errors = tuple(utility_objects.object_errors())
    if object_errors:
        report["warnings"] = tuple(dict.fromkeys(
            tuple(report.get("warnings", ())) +
            tuple("Beschädigte Leitungstrasse übersprungen: " + value
                  for value in object_errors)))
    report["metadata"] = {
        "document": str(vs.GetFName() or "Unbenannt"),
        "path": str(vs.GetFPathName() or ""),
        "created": datetime.datetime.now().strftime("%d.%m.%Y %H:%M"),
        "standard": "DIN EN 1610:2015-12 / Berichtigung 2016-09",
        "shoring": "Verbaute Gräben; 0,15 m Verbaudicke je Seite",
        "pavement": (
            "berücksichtigt; %.3f m" % (float(preferences.get(
                "earthwork_pavement_thickness_m", 0.0)))
            if preferences.get("earthwork_include_pavement", False)
            else "nicht berücksichtigt"),
    }
    return report


def _style_row(values, style):
    return [styled(value, style) for value in values]


def _detail_total(label, count, column_count, values):
    """Build one explicit, pre-calculated total row for a detail table."""
    row = [""] * int(column_count)
    row[0] = "SUMME %s (%d Positionen)" % (label, int(count))
    for column, value in values.items():
        row[int(column)] = value
    return _style_row(row, STYLE_TOTAL)


def _validated_report_mode(report_mode):
    value = str(report_mode or "all")
    if value not in REPORT_MODES:
        raise ValueError("Unbekannter Listeninhalt: %s" % value)
    return value


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
        ("Rigolen", styled(totals["rigole_count"], STYLE_INTEGER), "Stk."),
        ("Rigolen-Bruttovolumen", styled(
            totals["rigole_gross_volume_m3"], STYLE_NUMBER), "m³"),
        ("Rigolen-Wasservolumen (95 %)", styled(
            totals["rigole_storage_volume_m3"], STYLE_NUMBER), "m³"),
        ("Summe Schachthöhen KD-KS", styled(totals["shaft_height_m"], STYLE_NUMBER), "m"),
        ("Aushub Rohrgräben", styled(totals["trench_excavation_m3"], STYLE_NUMBER), "m³"),
        ("Aushub Schachtbaugruben", styled(totals["shaft_pit_excavation_m3"], STYLE_NUMBER), "m³"),
        ("Aushub Rigolenbaugruben", styled(totals["rigole_excavation_m3"], STYLE_NUMBER), "m³"),
        _style_row(("Aushub gesamt", totals["earthwork_total_m3"], "m³"), STYLE_TOTAL),
        ("Oberbau gesamt", styled(totals["pavement_total_m3"], STYLE_NUMBER), "m³"),
        _style_row(("Wiederverfüllung gesamt", totals["earthwork_backfill_m3"], "m³"), STYLE_TOTAL),
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
        ("RIGOLEN", "Länge [m]", "Breite [m]", "Höhe [m]", "Brutto [m³]",
         "Wasser 95 % [m³]", "Aushub [m³]", "Oberbau [m³]",
         "Wiederverfüllung [m³]"), STYLE_HEADER)))
    for row in report["rigoles"]:
        rows.append((row["name"], row["length_m"], row["width_m"], row["height_m"],
                     row["gross_volume_m3"], row["storage_volume_m3"],
                     row["excavation_volume_m3"], row["pavement_volume_m3"],
                     row["backfill_volume_m3"]))

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
        ("Aushub Rigolenbaugruben", totals["rigole_excavation_m3"], "m³"),
        _style_row(("Aushub gesamt", totals["earthwork_total_m3"], "m³"), STYLE_TOTAL),
        ("Oberbau Rohrgräben", totals["trench_pavement_m3"], "m³"),
        ("Oberbau Schachtbaugruben", totals["shaft_pavement_m3"], "m³"),
        ("Oberbau Rigolenbaugruben", totals["rigole_pavement_m3"], "m³"),
        _style_row(("Oberbau gesamt", totals["pavement_total_m3"], "m³"), STYLE_TOTAL),
        ("Wiederverfüllung Rohrgräben", totals["trench_backfill_m3"], "m³"),
        ("Wiederverfüllung Schachtbaugruben", totals["shaft_backfill_m3"], "m³"),
        ("Wiederverfüllung Rigolenbaugruben", totals["rigole_backfill_m3"], "m³"),
        _style_row(("Wiederverfüllung gesamt", totals["earthwork_backfill_m3"], "m³"), STYLE_TOTAL),
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
                     "Aushub [m³]", "Rohrvolumen [m³]", "Oberbau [m³]",
                     "Wiederverfüllung [m³]", "Verbau [m²]")
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
                           row["excavation_volume_m3"], row["pipe_displacement_m3"],
                           row["pavement_volume_m3"], row["backfill_volume_m3"],
                           row["shoring_area_m2"]))
    canal_rows.append(_detail_total(
        "KANALHALTUNGEN", len(report["canals"]), len(canal_headers), {
            21: sum(row["length_2d_m"] for row in report["canals"]),
            22: sum(row["length_3d_m"] for row in report["canals"]),
            23: sum(row["trench_length_m"] for row in report["canals"]),
            24: sum(row["shaft_pit_overlap_length_m"] for row in report["canals"]),
            29: sum(row["excavation_volume_m3"] for row in report["canals"]),
            30: sum(row["pipe_displacement_m3"] for row in report["canals"]),
            31: sum(row["pavement_volume_m3"] for row in report["canals"]),
            32: sum(row["backfill_volume_m3"] for row in report["canals"]),
            33: sum(row["shoring_area_m2"] for row in report["canals"]),
        }))

    shaft_headers = ("Schacht", "Kanalart", "Bauform", "Material", "Innen-Ø [m]",
                     "Wand [m]", "Außenbreite [m]", "Außenlänge [m]", "KD [m]", "KS [m]",
                     "Höhe KD-KS [m]", "Zuläufe", "Abläufe", "Baugrube licht B [m]",
                     "Baugrube licht L [m]", "Aushubmaß B [m]", "Aushubmaß L [m]",
                     "Aushub [m³]", "Schachtkörper [m³]", "Oberbau [m³]",
                     "Wiederverfüllung [m³]", "Verbau [m²]")
    shaft_rows = [_style_row(shaft_headers, STYLE_HEADER)]
    for row in report["shafts"]:
        shaft_rows.append((row["name"], row["kind"], row["structure_type"],
                           row["construction_material"], row["inside_diameter_m"],
                           row["wall_thickness_m"], row["body_width_m"], row["body_height_m"],
                           row["kd_m"], row["ks_m"], row["height_m"], row["inlets"], row["outlets"],
                           row["pit_clear_width_m"], row["pit_clear_height_m"],
                           row["pit_excavation_width_m"], row["pit_excavation_height_m"],
                           row["pit_volume_m3"], row["shaft_displacement_m3"],
                           row["pavement_volume_m3"], row["backfill_volume_m3"],
                           row["pit_shoring_area_m2"]))
    shaft_rows.append(_detail_total(
        "SCHÄCHTE", len(report["shafts"]), len(shaft_headers), {
            10: sum(row["height_m"] for row in report["shafts"]),
            11: sum(row["inlets"] for row in report["shafts"]),
            12: sum(row["outlets"] for row in report["shafts"]),
            17: sum(row["pit_volume_m3"] for row in report["shafts"]),
            18: sum(row["shaft_displacement_m3"] for row in report["shafts"]),
            19: sum(row["pavement_volume_m3"] for row in report["shafts"]),
            20: sum(row["backfill_volume_m3"] for row in report["shafts"]),
            21: sum(row["pit_shoring_area_m2"] for row in report["shafts"]),
        }))

    rigole_headers = (
        "Rigole", "Länge [m]", "Breite [m]", "Höhe [m]", "UK Rigole [m]",
        "OK Rigole [m]", "OK Gelände [m]", "Böschung [°]", "Baugrube unten L [m]",
        "Baugrube unten B [m]", "Baugrube oben L [m]", "Baugrube oben B [m]",
        "Bruttovolumen [m³]", "Wasservolumen 95 % [m³]", "Aushub [m³]",
        "Oberbau [m³]", "Wiederverfüllung [m³]", "Freitext")
    rigole_rows = [_style_row(rigole_headers, STYLE_HEADER)]
    for row in report["rigoles"]:
        rigole_rows.append((
            row["name"], row["length_m"], row["width_m"], row["height_m"],
            row["bottom_m"], row["top_m"], row["terrain_top_m"],
            row["slope_angle_deg"], row["bottom_length_m"], row["bottom_width_m"],
            row["top_length_m"], row["top_width_m"], row["gross_volume_m3"],
            row["storage_volume_m3"], row["excavation_volume_m3"],
            row["pavement_volume_m3"], row["backfill_volume_m3"],
            row.get("note", "")))
    rigole_rows.append(_detail_total(
        "RIGOLEN", len(report["rigoles"]), len(rigole_headers), {
            12: sum(row["gross_volume_m3"] for row in report["rigoles"]),
            13: sum(row["storage_volume_m3"] for row in report["rigoles"]),
            14: sum(row["excavation_volume_m3"] for row in report["rigoles"]),
            15: sum(row["pavement_volume_m3"] for row in report["rigoles"]),
            16: sum(row["backfill_volume_m3"] for row in report["rigoles"]),
        }))

    utility_headers = ("Trasse", "Leitungstyp", "DN", "OD [mm]",
                       "OD bestätigt", "Material", "Länge 2D [m]", "Länge 3D [m]")
    utility_rows = [_style_row(utility_headers, STYLE_HEADER)]
    for row in report["utilities"]:
        utility_rows.append((row["route_name"], row["utility_type"],
                             row["dn_mm"], row["outside_diameter_mm"],
                              "Ja" if row["outside_diameter_explicit"] else "NEIN",
                              row["material"], row["length_2d_m"], row["length_3d_m"]))
    utility_rows.append(_detail_total(
        "LEITUNGEN", len(report["utilities"]), len(utility_headers), {
            6: sum(row["length_2d_m"] for row in report["utilities"]),
            7: sum(row["length_3d_m"] for row in report["utilities"]),
        }))

    alignment_labels = {
        "invert": "Sohlgleich", "axis": "Achsgleich",
        "springline": "Kämpfergleich", "crown": "Scheitelgleich",
    }
    stub_headers = ("Stutzen", "Art", "DN", "Material", "Anschlussart",
                    "Anschluss-KS [m]", "Station [m]", "Anzahl")
    stub_rows = [_style_row(stub_headers, STYLE_HEADER)]
    for row in report["stubs"]:
        stub_rows.append((
            row["name"], row["kind"], row["dn_mm"], row["material"],
            alignment_labels.get(row["alignment"], row["alignment"]),
            row["connection_invert_m"], row["station_m"], 1))
    stub_rows.append(_detail_total(
        "KANALSTUTZEN", len(report["stubs"]), len(stub_headers), {
            7: len(report["stubs"]),
        }))

    earth_headers = ("Haltung", "Art", "DN", "OD [mm]", "Material", "Abschnitt",
                     "Station A [m]", "Station E [m]", "Länge [m]", "Tiefe A [m]",
                     "Tiefe E [m]", "lichte Breite [m]", "Aushubbreite [m]",
                     "Aushub [m³]", "Rohrvolumen [m³]", "Oberbau [m³]",
                     "Wiederverfüllung [m³]", "Verbau [m²]")
    earth_rows = [_style_row(earth_headers, STYLE_HEADER)]
    for row in report["earth_segments"]:
        earth_rows.append((row["pipe_name"], row["kind"], row["dn_mm"],
                           row["outside_diameter_mm"], row["material"], row["segment"],
                           row["station_start_m"], row["station_end_m"], row["length_m"],
                           row["depth_start_m"], row["depth_end_m"], row["clear_width_m"],
                           row["excavation_width_m"], row["excavation_volume_m3"],
                           row["pipe_displacement_m3"], row["pavement_volume_m3"],
                           row["backfill_volume_m3"],
                           row["shoring_area_m2"]))
    earth_rows.append(_detail_total(
        "ERDMASSEN", len(report["earth_segments"]), len(earth_headers), {
            8: sum(row["length_m"] for row in report["earth_segments"]),
            13: sum(row["excavation_volume_m3"] for row in report["earth_segments"]),
            14: sum(row["pipe_displacement_m3"] for row in report["earth_segments"]),
            15: sum(row["pavement_volume_m3"] for row in report["earth_segments"]),
            16: sum(row["backfill_volume_m3"] for row in report["earth_segments"]),
            17: sum(row["shoring_area_m2"] for row in report["earth_segments"]),
        }))

    notes = [
        _style_row(("GRUNDLAGEN UND PRÜFHINWEISE", "Wert"), STYLE_HEADER),
        ("Regelwerk", report["metadata"]["standard"]),
        ("Grabenart", report["metadata"]["shoring"]),
        ("Mindestbreite", "max(OD + DN-Zuschlag; tiefenabhängige Mindestbreite)"),
        ("DN-Zuschläge", "≤225: 0,40; ≤350: 0,50; ≤700: 0,70; ≤1200: 0,85; >1200: 1,00 m"),
        ("Tiefenbreiten", "<1,00: keine Zusatzvorgabe; bis 1,75: 0,80; bis 4,00: 0,90; >4,00: 1,00 m"),
        ("Schachtbaugrube", "rechteckig; Außenmaß + 0,50 m Arbeitsraum + 0,15 m Verbau je Seite"),
        ("Rigolenbaugrube", "Rigolenmaß + 0,50 m Arbeitsraum je Seite; Böschung 45° oder 60° bis OK Gelände"),
        ("Speichervolumen Rigole", "Länge × Breite × Höhe × 95 %"),
        ("Künftiger Oberbau", report["metadata"].get(
            "pavement", "nicht berücksichtigt")),
        ("Wiederverfüllung", "Aushub abzüglich Baukörper/Rohr und abzüglich künftiger Oberbau"),
        ("Schachthöhe", "hydraulische Höhe KD − KS; keine Baukörper-Unterkante im Objektmodell"),
        ("Aushub", "Rohrgräben werden an den äußeren Grenzen der rechteckigen Schachtbaugruben gekürzt; keine Doppelmenge"),
        (), _style_row(("STATUS", "HINWEIS"), STYLE_HEADER),
    ]
    if report["warnings"]:
        notes.extend(_style_row(("WARNUNG", warning), STYLE_WARNING)
                     for warning in report["warnings"])
    else:
        notes.append(("OK", "Keine unvollständigen Mengengrundlagen erkannt."))

    totals = report["totals"]
    overall_rows = [
        _style_row(("SUMMEN DER EINZELMASSEN", "Wert", "Einheit"), STYLE_HEADER),
        ("Kanal-Achslänge 2D", totals["canal_length_2d_m"], "m"),
        ("Kanal-Rohrlänge 3D", totals["canal_length_3d_m"], "m"),
        ("Versorgungsleitungen 2D", totals["utility_length_2d_m"], "m"),
        ("Versorgungsleitungen 3D", totals["utility_length_3d_m"], "m"),
        _style_row(("Schächte gesamt", totals["shaft_count"], "Stk."), STYLE_TOTAL),
        _style_row(("Kanalstutzen gesamt", totals["stub_count"], "Stk."), STYLE_TOTAL),
        _style_row(("Rigolen gesamt", totals["rigole_count"], "Stk."), STYLE_TOTAL),
        ("Rigolen-Bruttovolumen", totals["rigole_gross_volume_m3"], "m³"),
        ("Rigolen-Wasservolumen (95 %)", totals["rigole_storage_volume_m3"], "m³"),
        _style_row(("Aushub gesamt", totals["earthwork_total_m3"], "m³"), STYLE_TOTAL),
        _style_row(("Oberbau gesamt", totals["pavement_total_m3"], "m³"), STYLE_TOTAL),
        _style_row(("Wiederverfüllung gesamt", totals["earthwork_backfill_m3"], "m³"), STYLE_TOTAL),
        _style_row(("Verbau gesamt", totals["shoring_total_m2"], "m²"), STYLE_TOTAL),
    ]

    return [
        {"name": "01_Kanalhaltungen", "rows": canal_rows, "widths": (26, 12, 10) + (14,) * 31, "freeze_rows": 1},
        {"name": "02_Schaechte", "rows": shaft_rows, "widths": (18, 12, 18, 16) + (15,) * 18, "freeze_rows": 1},
        {"name": "03_Rigolen", "rows": rigole_rows, "widths": (22,) + (16,) * 16 + (36,), "freeze_rows": 1},
        {"name": "04_Leitungen", "rows": utility_rows, "widths": (24, 24, 10, 12, 14, 18, 18, 18), "freeze_rows": 1},
        {"name": "05_Erdmassen", "rows": earth_rows, "widths": (38, 12, 10, 12, 16, 12) + (16,) * 12, "freeze_rows": 1},
        {"name": "06_Stutzen", "rows": stub_rows, "widths": (20, 12, 10, 18, 20, 18, 18, 12), "freeze_rows": 1},
        {"name": "07_Annahmen_Pruefung", "rows": notes, "widths": (28, 90), "freeze_rows": 1},
        {"name": "08_Einzelmassen_Summen", "rows": overall_rows, "widths": (38, 20, 14), "freeze_rows": 1},
    ]


def xlsx_sheets(report, report_mode="all"):
    report_mode = _validated_report_mode(report_mode)
    if report_mode == "summary":
        return [summary_sheet(report)]
    if report_mode == "details":
        return detail_sheets(report)
    return [summary_sheet(report)] + detail_sheets(report)


def _available_export_path(path):
    """Return a new sibling name when an existing workbook is locked."""
    base, extension = os.path.splitext(os.path.abspath(path))
    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    candidate = "%s_neu_%s%s" % (base, stamp, extension or ".xlsx")
    counter = 2
    while os.path.exists(candidate):
        candidate = "%s_neu_%s_%d%s" % (
            base, stamp, counter, extension or ".xlsx")
        counter += 1
    return candidate


def export_xlsx(path, report=None, report_mode="all"):
    report = report or collect_live()
    sheets = xlsx_sheets(report, report_mode)
    try:
        return write_xlsx(path, sheets, creator="plan ° D Ingenieure")
    except PermissionError:
        if not os.path.isfile(path):
            raise
        return write_xlsx(
            _available_export_path(path), sheets,
            creator="plan ° D Ingenieure")


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


def update_worksheet(report=None, show=True, report_mode="all"):
    """Replace the selected worksheet set as one recoverable transaction."""
    global _REPORT_DIRTY
    report = report or collect_live()
    report_mode = _validated_report_mode(report_mode)
    specs = []
    if report_mode in ("details", "all"):
        specs.append((WORKSHEET_NAME, worksheet_rows(report, summary=False)))
    if report_mode in ("summary", "all"):
        specs.append((SUMMARY_WORKSHEET_NAME, worksheet_rows(report, summary=True)))
    prepared, backups, installed = [], [], []
    try:
        for final_name, rows in specs:
            columns = max([len(row["values"]) for row in rows] or [1])
            temporary_name = "%s – TMP-%s" % (final_name, uuid.uuid4().hex[:10])
            worksheet = vs.CreateWS(temporary_name, len(rows), columns)
            if not worksheet:
                raise RuntimeError("Das Mengen-Arbeitsblatt konnte nicht vorbereitet werden.")
            prepared.append((worksheet, temporary_name, final_name))
            _populate(worksheet, rows)
        for _worksheet, _temporary_name, final_name in prepared:
            old = vs.GetObject(final_name)
            if old:
                backup_name = "%s – BAK-%s" % (final_name, uuid.uuid4().hex[:10])
                vs.SetName(old, backup_name)
                if str(vs.GetName(old) or "") != backup_name:
                    raise RuntimeError(
                        "Vorhandenes Mengen-Arbeitsblatt konnte nicht gesichert werden.")
                backups.append((old, backup_name, final_name))
        by_name = {}
        for worksheet, temporary_name, final_name in prepared:
            vs.SetName(worksheet, final_name)
            if str(vs.GetName(worksheet) or "") != final_name:
                raise RuntimeError("Mengen-Arbeitsblatt konnte nicht benannt werden.")
            installed.append((worksheet, temporary_name, final_name))
            by_name[final_name] = worksheet
        for worksheet in by_name.values():
            image = vs.GetWSImage(worksheet)
            if image:
                vs.SetWSImgShowDBHeader(image, False, True)
        shown_name = (WORKSHEET_NAME if report_mode == "details" else
                      SUMMARY_WORKSHEET_NAME)
        if show:
            vs.ShowWS(by_name[shown_name], True)
        synchronize_delete_observer()
        for old, _backup_name, _final_name in backups:
            vs.DelObject(old)
        _REPORT_DIRTY = False
        return by_name[shown_name] if show else prepared[0][0]
    except Exception:
        for worksheet, temporary_name, _final_name in reversed(installed):
            try:
                vs.SetName(worksheet, temporary_name)
            except Exception:
                pass
        for old, _backup_name, final_name in reversed(backups):
            try:
                vs.SetName(old, final_name)
            except Exception:
                pass
        for worksheet, _temporary_name, _final_name in prepared:
            try:
                vs.DelObject(worksheet)
            except Exception:
                pass
        raise


def begin_changes():
    """Suspend expensive worksheet rebuilds during one compound command."""
    global _SUSPEND_DEPTH
    _SUSPEND_DEPTH += 1


def mark_existing_dirty():
    """Mark existing reports stale without rebuilding them in an object event."""
    global _REPORT_DIRTY
    if not (vs.GetObject(WORKSHEET_NAME) or
            vs.GetObject(SUMMARY_WORKSHEET_NAME)):
        return False
    _REPORT_DIRTY = True
    return True


def end_changes(refresh=False, mark_dirty=False):
    """Resume reporting; defer expensive rebuilds unless explicitly requested."""
    global _SUSPEND_DEPTH, _PENDING_REFRESH
    if _SUSPEND_DEPTH <= 0:
        return False
    _SUSPEND_DEPTH -= 1
    if _SUSPEND_DEPTH:
        if refresh or mark_dirty:
            _PENDING_REFRESH = True
        return False
    pending = bool(_PENDING_REFRESH)
    _PENDING_REFRESH = False
    if refresh:
        return refresh_existing(force=True)
    return mark_existing_dirty() if (mark_dirty or pending) else False


def refresh_existing(force=False):
    """Refresh an already-created report; never creates one implicitly."""
    global _REFRESHING, _LAST_REFRESH, _PENDING_REFRESH, _REPORT_DIRTY
    if _SUSPEND_DEPTH:
        _PENDING_REFRESH = True
        _REPORT_DIRTY = True
        return False
    if _REFRESHING or not (
            vs.GetObject(WORKSHEET_NAME) or vs.GetObject(SUMMARY_WORKSHEET_NAME)):
        return False
    if not force and not _REPORT_DIRTY:
        return False
    now = datetime.datetime.now()
    if (not force and _LAST_REFRESH is not None and
            (now - _LAST_REFRESH).total_seconds() < 0.25):
        return False
    _REFRESHING = True
    try:
        has_detail = bool(vs.GetObject(WORKSHEET_NAME))
        has_summary = bool(vs.GetObject(SUMMARY_WORKSHEET_NAME))
        if has_detail and has_summary:
            update_worksheet(show=False)
        elif has_detail:
            update_worksheet(show=False, report_mode="details")
        else:
            update_worksheet(show=False, report_mode="summary")
        # Measure the cooldown from the completed rebuild.  A large report may
        # itself take longer than the cooldown; using its start time would let
        # the following reset event immediately rebuild the same report again.
        _LAST_REFRESH = datetime.datetime.now()
        _REPORT_DIRTY = False
        return True
    finally:
        _REFRESHING = False
