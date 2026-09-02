# -*- coding: utf-8 -*-
"""Orchestration for the five-step terrain and excavation assistant."""
from __future__ import absolute_import

import vs

from . import core
from . import reporting
from . import ui
from . import vw_adapter as adapter


def _count_labels(values, key):
    counts = {}
    for value in values:
        label = str(value.get(key) or "Unbekannt")
        counts[label] = counts.get(label, 0) + 1
    return ", ".join("%s: %d" % item for item in sorted(counts.items()))


def _model_names():
    return tuple(name for _handle, name in adapter.site_models() if name)


def _preview_sources(options):
    if not str(options.get("model_name") or "").strip():
        raise core.TerrainError("Der gewünschte Geländemodellname fehlt.")
    if not str(options.get("model_class") or "").strip():
        raise core.TerrainError("Der gewünschte Geländemodell-Klassenname fehlt.")
    boundaries = adapter.selected_boundaries()
    boundary_handle, boundary = boundaries[0] if boundaries else (None, None)
    sources, unsupported = adapter.extract_selected_sources(
        options["chord_tolerance_m"], boundary_handle)
    review = core.review_sources(
        sources, options["xy_tolerance_m"], options["z_tolerance_m"], boundary,
        options["excluded_classes"], options["excluded_layers"])
    message = (
        "Quelldatenprüfung\n\n"
        "Markierte Objekte: %d\nErkannte Quellen: %d\n"
        "Verwendbar: %d\nAusgeschlossen: %d\nProbleme: %d\n"
        "Nicht unterstützte Objekte: %d\nVerwendbare Stützpunkte: %d" %
        (review["input_count"] + len(unsupported), review["input_count"],
         review["usable_count"], review["excluded_count"],
         review["problem_count"], len(unsupported), review["vertex_count"]))
    if unsupported:
        message += "\nNicht unterstützt nach Typ: " + _count_labels(unsupported, "type_name")
    if review["excluded"]:
        message += "\nAusgeschlossen nach Grund: " + _count_labels(review["excluded"], "reason")
    if review["problems"]:
        message += "\n\n" + "\n".join(problem["message"] for problem in review["problems"][:8])
        message += ("\n\nDiese problematischen Objekte werden übersprungen; "
                    "alle übrigen verwendbaren Daten werden weiterverarbeitet.")
    if review["blocking_count"]:
        adapter.alert(message + "\n\nDie blockierenden Konflikte müssen zuerst behoben werden.")
        return
    if not adapter.confirm(message + "\n\nQuelldaten-Ebene jetzt erzeugen?",
                           "Originalobjekte werden weder verändert noch gelöscht."):
        return
    layer_name, created = adapter.create_source_layer(review, options["layer_name"])
    model_class = adapter.ensure_class(options["model_class"])
    adapter.alert(
        "%d geprüfte Quelldaten wurden auf der Ebene „%s“ angelegt und markiert.\n\n"
        "Nächster nativer Vectorworks-Schritt: Landschaft > Geländemodell > "
        "Geländemodell aus Ausgangsdaten. Dieser Befehl ist über die geprüfte Python-API "
        "nicht belastbar automatisierbar.\n\n"
        "Vorgaben für den nativen Dialog:\nName: %s\nKlasse: %s\n"
        "Höhenlinien-Äquidistanz: %.3f m\nHöheneinheit der Modulauswertung: Meter."
        % (len(created), layer_name, options["model_name"], model_class,
           options["contour_interval_m"]))


def _manage_models(options):
    operation = options["operation"]
    if operation == "register":
        handle = adapter.model_by_name(options["source_name"])
        data = adapter.register_model(
            handle, options["variant_name"], options["role"],
            options["reference_name"], options["priority"], False)
        adapter.alert("Geländemodell „%s“ ist als %s „%s“ registriert."
                      % (data["model_name"], data["role"], data["variant_name"]))
    elif operation == "duplicate":
        _handle, data = adapter.duplicate_variant(
            options["source_name"], options["new_model_name"], options["variant_name"])
        adapter.alert("Unabhängige Sollkopie „%s“ wurde erzeugt und geprüft." % data["model_name"])
    elif operation == "delete":
        if adapter.confirm("Verwaltete Sollvariante „%s“ wirklich löschen?" % options["source_name"],
                           "Nur das duplizierte Geländemodell wird gelöscht."):
            adapter.delete_managed_variant(options["source_name"])
            adapter.alert("Die verwaltete Sollvariante wurde gelöscht.")


def _excavation(options):
    boundaries = adapter.selected_boundaries()
    if not boundaries:
        raise core.TerrainError("Zuerst die geschlossene Baugrubenbegrenzung markieren.")
    boundary = boundaries[0][1]
    obstacles = tuple({"polygon": value, "name": adapter.object_label(handle)}
                      for handle, value in boundaries[1:])
    model = adapter.model_by_name(options["model_name"])
    result = core.solve_excavation(
        boundary, options["floor_m"], options["slope_value"], options["slope_unit"],
        options["max_extent_m"], adapter.sampler(model, 0), obstacles,
        floor_slope_percent=options["floor_slope_percent"],
        floor_direction_degrees=options["floor_direction_degrees"])
    message = (
        "Böschungsvorschau\n\nStatus: %s\nUnterkante: %d Punkte\n"
        "Oberkante: %d Punkte\nKonflikte: %d\nBöschung 1:%.3f" %
        ("herstellbar" if result["status"] == "valid" else "NICHT vollständig herstellbar",
         len(result["lower_edge"]), len(result["upper_edge"]), len(result["conflicts"]),
         result["run_per_rise"]))
    if result["conflicts"]:
        details = []
        for conflict in result["conflicts"][:8]:
            required = conflict.get("required_run_per_rise")
            cause = " – %s" % conflict["obstacle"] if conflict.get("obstacle") else ""
            details.append("Abschnitt %d: %s%s%s" % (
                conflict["edge"], conflict["code"],
                " – erforderlich höchstens 1:%.3f" % required if required else "", cause))
        message += "\n\n" + "\n".join(details)
        message += "\n\nEs wird nur eine rote Konfliktprüfung erzeugt; kein nativer Sohlenmodifikator."
    if not adapter.confirm(message + "\n\nAusgabe jetzt anlegen?", "Die gewünschte Neigung wird nicht verändert."):
        return
    adapter.create_excavation_output(
        result, options["name"], options["hatch_spacing_m"], options["short_ratio"],
        options["create_modifier"] and result["status"] == "valid")
    adapter.alert(
        "Baugrubensohle, obere/untere Böschungskante und Schraffur wurden angelegt. "
        "Die DGM-Modifikatorebene muss im nativen Geländemodell zugelassen und das Modell "
        "anschließend manuell aktualisiert werden.")


def _comparison(options):
    _handle, boundary = adapter.selected_boundary()
    if not boundary:
        raise core.TerrainError("Zuerst eine geschlossene Auswertungsbegrenzung markieren.")
    reference = adapter.model_by_name(options["reference_name"])
    comparison = adapter.model_by_name(options["comparison_name"])
    origin = (boundary[0] if options["automatic_origin"] else
              (options["origin_x_m"], options["origin_y_m"]))
    coarse_count = len(core.grid_centers(
        boundary, options["spacing_m"], origin, options["angle_degrees"],
        core.MAX_GRID_CELLS // 4))
    fine_count = len(core.grid_centers(
        boundary, options["spacing_m"] / 2.0, origin, options["angle_degrees"],
        core.MAX_GRID_CELLS))
    total = coarse_count + fine_count
    state = {"offset": 0, "last_total": None}
    ended = False
    vs.ProgressDlgOpen("Geländemodelle werden verglichen", True)
    try:
        vs.ProgressDlgStart(100.0, max(1, total))

        def cancelled():
            return bool(vs.ProgressDlgHasCancel())

        def progress(done, count, phase):
            if state["last_total"] is None:
                state["last_total"] = count
            elif count != state["last_total"]:
                state["offset"] += state["last_total"]
                state["last_total"] = count
            vs.ProgressDlgSetMeter("%s: %d / %d" % (phase, done, count))
            vs.ProgressDlgYield(min(max(1, total), state["offset"] + done))

        result = core.compare_converged(
            boundary, options["spacing_m"], origin, options["angle_degrees"],
            adapter.sampler(reference, 0), adapter.sampler(comparison, 1),
            options["z_tolerance_m"], options["volume_tolerance"],
            cancelled, progress)
        vs.ProgressDlgEnd()
        ended = True
    finally:
        if not ended:
            vs.ProgressDlgEnd()
        vs.ProgressDlgClose()
    message = (
        "Geländevergleich\n\nStatus: %s\nAbtrag: %.3f m³\nAuftrag: %.3f m³\n"
        "Differenz: %.3f m³\nVergleichsfläche: %.2f m²\nKeine Daten: %.2f m²\n"
        "Konvergenzabweichung: %.3f m³ (%.2f %%)" %
        (result["status"], result["cut_volume_m3"], result["fill_volume_m3"],
         result["difference_m3"], result["comparison_area_m2"], result["no_data_area_m2"],
         result["convergence_absolute_m3"], result["convergence_relative"] * 100.0))
    if result["status"] == "provisional":
        message += "\n\nDie Konvergenztoleranz ist nicht erreicht. Rasterweite verkleinern."
    elif result["status"] == "partial_coverage":
        message += "\n\nDie Modelle überdecken die Begrenzung nicht vollständig. Die Werte bleiben Prüfwerte."
    if not adapter.confirm(message + "\n\nTabelle und gewählte Planausgabe jetzt erzeugen?",
                           "Teil- oder vorläufige Ergebnisse werden eindeutig gekennzeichnet."):
        return
    group = None
    try:
        if options["create_plan"]:
            group = adapter.create_comparison_output(
                result, boundary, options["reference_name"], options["comparison_name"],
                options["decimals"], options["label_text_size_pt"])
        reporting.update(result, options["reference_name"], options["comparison_name"], boundary)
    except Exception:
        if group:
            vs.DelObject(group)
        raise
    vs.NameUndoEvent("PD Geländeauswertung erzeugen")
    adapter.alert("Massenvergleich, Qualitätshinweise und Rasterplan wurden aktualisiert.")


def run():
    try:
        while True:
            action = ui.home()
            if action is None:
                return
            if action == 1:
                options = ui.source_options()
                if options and options != "back":
                    _preview_sources(options)
            elif action == 2:
                options = ui.model_options(_model_names())
                if options and options != "back":
                    _manage_models(options)
            elif action == 3:
                options = ui.excavation_options(_model_names())
                if options and options != "back":
                    _excavation(options)
            elif action in (4, 5):
                options = ui.comparison_options(_model_names())
                if options and options != "back":
                    _comparison(options)
    except core.CalculationCancelled:
        adapter.alert("Die Berechnung wurde abgebrochen. Es wurden keine Ergebnisse angelegt.")
    except Exception as error:
        adapter.alert("Gelände und Baugruben: " + str(error))
