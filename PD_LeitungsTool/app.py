# -*- coding: utf-8 -*-
"""Interactive workflow for the independent utility-route module."""
from __future__ import absolute_import

from PD_KanalTool import vw_adapter as adapter

from . import core
from . import live
from . import settings
from . import ui


def _options(preferences):
    utility_type = preferences["default_type"]
    dn = preferences["default_dn_mm"]
    return {
        "utility_type": utility_type,
        "route_name": "",
        "description": "",
        "material": preferences["default_material"],
        "count": preferences["count"],
        "spacing_m": preferences["spacing_m"],
        "axis_reference": preferences["axis_reference"],
        "dns_mm": [dn],
        "outside_diameters_mm": [dn],
        "outside_diameters_explicit": False,
        "graphics_mode": preferences["graphics_mode"],
        "line_type": preferences["line_type"],
        "axis_line_type": preferences["axis_line_type"],
        "round_corners": preferences["round_corners"],
        "fillet_radius_m": preferences["fillet_radius_m"],
        "show_fittings": preferences["show_fittings"],
        "label_bend_angles": preferences["label_bend_angles"],
        "slope_percent": preferences["slope_percent"],
        "start_height_m": preferences["start_height_m"],
        "elevation_mode": preferences["elevation_mode"],
        "cover_depth_m": preferences["cover_depth_m"],
        "surface_tin_type": preferences["surface_tin_type"],
        "surface_model_name": "",
        "show_heights": preferences["show_heights"],
        "regular_label": preferences["regular_label"],
        "label_text": preferences["label_text"],
        "label_interval_m": preferences["label_interval_m"],
        "label_frame": preferences["label_frame"],
        "label_fill": preferences["label_fill"],
        "font_name": preferences["font_name"],
        "font_size_pt": preferences["font_size_pt"],
        "draw_3d": preferences["draw_3d"],
        "line_color": preferences["colors"][utility_type],
        "text_color": preferences["text_color"],
        "frame_color": preferences["frame_color"],
        "fill_color": preferences["fill_color"],
    }


def _create(preferences, paths=None):
    paths = tuple(paths or ())
    values = ui.route_dialog(preferences, None, len(paths))
    if values is None:
        return
    values.pop("_rebuild_heights", None)
    values.pop("schema", None)
    values.pop("id", None)
    values.pop("points_m", None)
    values.pop("heights_m", None)
    values.pop("route_heights_m", None)

    def complete(point_paths):
        handles = live.create(point_paths, values, preferences)
        adapter.alert(
            "%d Leitungstrasse(n) erstellt. Doppelklick öffnet die Bearbeitung; "
            "Höhenketten bleiben je Einzelleitung getrennt." % len(handles))
    if paths:
        complete(paths)
    else:
        adapter.draw_points(
            lambda points: complete((points,)),
            help_text=("LEITUNG: Trassenpunkte anklicken. Doppelklick beendet; Esc bricht ab."),
            undo_name="PD Leitungstrasse zeichnen")


def _editable_route(original, values):
    rebuild = bool(values.pop("_rebuild_heights", False))
    result = dict(original)
    result.update(values)
    count_changed = int(result["count"]) != int(original["count"])
    if rebuild or count_changed:
        heights = core.initial_heights(
            original["points_m"], result["start_height_m"], result["slope_percent"])
        result["route_heights_m"] = [heights for _index in range(int(result["count"]))]
        result["heights_m"] = heights
    else:
        result["route_heights_m"] = original["route_heights_m"]
        result["heights_m"] = original["heights_m"]
    result = core.validate_route(result)
    terrain_geometry_keys = (
        "spacing_m", "axis_reference", "round_corners", "fillet_radius_m",
        "surface_tin_type", "surface_model_name")
    terrain_geometry_changed = any(
        result[key] != original[key] for key in terrain_geometry_keys)
    if result["elevation_mode"] == "surface_cover" and (rebuild or count_changed or
            terrain_geometry_changed or
            result["elevation_mode"] != original["elevation_mode"] or
            result["cover_depth_m"] != original["cover_depth_m"] or
            result["outside_diameters_mm"] != original["outside_diameters_mm"]):
        result = live.surface_route(result, True)
    return result


def _single(managed):
    if len(managed) != 1:
        raise core.UtilityError("Bitte genau eine Leitungstrasse markieren.")
    return managed[0][0]


_QUANTITY_MUTATIONS = frozenset((
    "sources", "draw", "edit", "chain", "terrain", "delete", "settings",
))


def run(action=None):
    quantity_reporting = None
    quantity_batch = False
    try:
        adapter.cancel_point_input()
        preferences = settings.load()
        sources = live.selected_source_paths()
        managed = live.selected_managed()
        if action is None:
            action = ui.home_dialog(len(sources), len(managed))
        if action is None:
            return
        if action in _QUANTITY_MUTATIONS:
            from PD_KanalLeitungMengen import reporting as quantity_reporting
            quantity_reporting.begin_changes()
            quantity_batch = True
        if action == "sources":
            _create(preferences, sources)
        elif action == "draw":
            _create(preferences)
        elif action == "edit":
            handle = _single(managed)
            object_preferences = live.object_preferences(handle)
            original = live.read_route(handle)
            values = ui.route_dialog(object_preferences, original)
            if values is not None:
                live.update(handle, _editable_route(original, values), object_preferences)
                adapter.alert("Leitungstrasse und 3D-Darstellung wurden aktualisiert.")
        elif action == "chain":
            handle = _single(managed)
            changed = ui.height_chain_dialog(live.read_route(handle))
            if changed is not None:
                live.update(handle, changed, None, "PD Leitungshöhenkette bearbeiten")
                adapter.alert("Höhenkette der Leitungstrasse wurde aktualisiert.")
        elif action == "terrain":
            handle = _single(managed)
            route = live.read_route(handle)
            if not route.get("outside_diameters_explicit", False):
                raise core.UtilityError(
                    "Vor der DGM-Anpassung bitte in 'Bearbeiten' die realen Außendurchmesser bestätigen.")
            live.refresh_surface(handle, None, True)
            adapter.alert(
                "Leitungsachsen wurden mit der eingestellten Überdeckung unter dem Geländemodell aktualisiert.")
        elif action == "delete":
            if ui.confirm_delete(len(managed)):
                count = live.delete(managed)
                adapter.alert("%d Leitungstrasse(n) gelöscht. Rückgängig bleibt verfügbar." % count)
        elif action == "validate":
            report = live.validate_document()
            text = (
                "Leitungsprüfung ohne Datenfehler: %d Trassen, %d Einzelleitungen, "
                "%.2f m Grundrisslänge, %.2f m 3D-Länge, %d Winkelpunkte." %
                (report["routes"], report["lines"], report["length_2d_m"],
                 report["length_3d_m"], report["bends"]))
            if report["cover_samples"]:
                text += (
                    " DGM-Prüfung: %d Stützpunkte (Abstand höchstens 1,00 m), "
                    "Überdeckung %.3f bis %.3f m, %d Unterschreitung(en)." %
                    (report["cover_samples"], report["minimum_cover_m"],
                     report["maximum_cover_m"], report["cover_shortfalls"]))
            adapter.alert(text)
        elif action == "quantities":
            from PD_KanalLeitungMengen import app as quantities_app
            quantities_app.run()
        elif action == "settings":
            changed = ui.preferences_dialog(preferences)
            if changed is not None:
                settings.save(changed)
                adapter.alert("Leitungsstandards wurden gespeichert; bestehende Trassen bleiben unverändert.")
        else:
            raise core.UtilityError("Unbekannte Leitungsaktion.")
        if quantity_batch:
            quantity_reporting.end_changes(refresh=True)
            quantity_batch = False
    except (core.UtilityError, RuntimeError, ValueError) as error:
        adapter.alert(error)
    except Exception as error:
        adapter.alert("Leitungstool: unerwarteter Fehler: %s" % error)
    finally:
        if quantity_batch:
            quantity_reporting.end_changes(refresh=False)
