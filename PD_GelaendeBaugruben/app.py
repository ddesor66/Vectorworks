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
        if key == "reason" and label.startswith("Identische Geometrie wie "):
            label = "Identische Geometrie"
        counts[label] = counts.get(label, 0) + 1
    return ", ".join("%s: %d" % item for item in sorted(counts.items()))


def _model_names():
    return tuple(name for _handle, name in adapter.site_models() if name)


def _preview_sources(options):
    if not str(options.get("model_name") or "").strip():
        raise core.TerrainError("Der gewünschte Geländemodellname fehlt.")
    if not str(options.get("model_class") or "").strip():
        raise core.TerrainError("Der gewünschte Geländemodell-Klassenname fehlt.")
    selected = adapter.selected_handles()
    vectorworks_selection_count = adapter.selected_object_count()
    boundaries = (adapter.selected_boundaries(selected)
                  if options.get("use_selected_boundary", False) else ())
    boundary_handle, boundary = boundaries[0] if boundaries else (None, None)
    # The DGM source set is defined exclusively by the current Vectorworks
    # selection. selected_handles() already combines several native selected-
    # only iterators and a complete document walk guarded by Selected(handle).
    # Never broaden this set to a complete layer: separate selections must be
    # able to create separate terrain models without importing one another.
    handles = selected
    if not handles:
        raise core.TerrainError("Es wurden keine Objekte markiert.")
    sources, unsupported = adapter.extract_sources(
        handles, options["chord_tolerance_m"], boundary_handle)
    review = core.review_sources(
        sources, options["xy_tolerance_m"], options["z_tolerance_m"], boundary,
        options["excluded_classes"], options["excluded_layers"], retain_all=True)
    message = (
        "Quelldatenprüfung\n\n"
        "%s: %d\nErkannte Quellgeometrien: %d\n"
        "Verwendbar: %d\nAusgeschlossen: %d\nProbleme: %d\n"
        "Nicht unterstützte Objekte: %d\nVerwendbare Stützpunkte: %d" %
        ("Geprüfte markierte Objekte",
         len(handles), review["input_count"],
         review["usable_count"], review["excluded_count"],
         review["problem_count"], len(unsupported), review["vertex_count"]))
    message += "\nErfassungsbereich: ausschließlich markierte Objekte"
    message += "\nVectorworks-Auswahlzähler: %d" % vectorworks_selection_count
    if vectorworks_selection_count != len(handles):
        message += (" (abweichend; es wurden keine unmarkierten "
                    "Ebenenobjekte ergänzt)")
    message += ("\nModellbegrenzung: %s" %
                ("markiertes Polygon" if boundary else "keine"))
    message += "\nEingelesene Vectorworks-Objekttypen: " + _count_labels(
        adapter.source_handle_types(handles), "type_name")
    if unsupported:
        message += "\nNicht unterstützt nach Typ: " + _count_labels(unsupported, "type_name")
    if review["excluded"]:
        message += "\nAusgeschlossen nach Grund: " + _count_labels(review["excluded"], "reason")
    message += "\nQuellgeometrien nach Art: " + _count_labels(sources, "kind")
    if review["problems"]:
        message += "\n\n" + "\n".join(problem["message"] for problem in review["problems"][:8])
        message += ("\n\nRäumlich lesbare markierte Objekte bleiben trotz Höhen- oder "
                    "Dublettenhinweisen erhalten. Nur ausdrücklich gefilterte, außerhalb einer "
                    "aktivierten Begrenzung liegende oder technisch unlesbare Objekte entfallen.")
    if review["blocking_count"]:
        adapter.alert(message + "\n\nDie blockierenden Konflikte müssen zuerst behoben werden.")
        return
    if not adapter.confirm(message + "\n\nQuelldaten-Ebene jetzt erzeugen?",
                           "Originalobjekte und bestehende DGM werden weder verändert noch "
                           "gelöscht. Dieser Lauf erhält eigene, eindeutige Quell- und "
                           "Kontrollebenen."):
        return
    layer_name, created, verification = adapter.create_source_layer(
        review, options["layer_name"])
    model_class = adapter.ensure_class(options["model_class"])
    usable_type_counts = {}
    for value in review["usable"]:
        label = str(value.get("source_type_name") or "Unbekannt")
        usable_type_counts[label] = usable_type_counts.get(label, 0) + 1
    text_height_counts = {}
    for value in review["usable"]:
        if value.get("source_type") != adapter.TYPE_TEXT:
            continue
        label = str(value.get("height_source") or "unknown")
        text_height_counts[label] = text_height_counts.get(label, 0) + 1
    spatial_text_heights = sum(
        text_height_counts.get(label, 0)
        for label in ("object_matrix", "3d_center", "layer_elevation"))
    source_summary = (
        "%d geprüfte 3D-Quellobjekte wurden auf der aktiven Ebene „%s“ angelegt.\n"
        "Geprüft: %d Punkte, %d Bruchkanten; %d Objekte markiert.\n"
        "Davon aus Texten umgesetzt: %d; aus Linien umgesetzt: %d.\n"
        "Text-Höhen aus tatsächlicher 3D-Objektlage: %d; "
        "ersatzweise aus Textinhalt: %d.\n"
        "Kontrollebene „%s“: %d Texte, %d Linien."
        % (len(created), layer_name, verification["points"], verification["lines"],
           verification["selected"], usable_type_counts.get("Text", 0),
           usable_type_counts.get("Linie", 0), spatial_text_heights,
           text_height_counts.get("text_content", 0), verification["control_layer"],
           verification["control_texts"], verification["control_lines"]))
    result = adapter.create_site_model_from_selected_sources(
        options["model_name"], model_class, verification.get("xy_anchor_m"),
        created, verification.get("control_layer"))
    if not result:
        adapter.alert(
            source_summary +
            "\n\nDer native DGM-Dialog wurde abgebrochen oder hat kein neues "
            "Geländemodell erzeugt. Die geprüften Quellen bleiben erhalten.")
        return
    adapter.alert(
        source_summary +
        "\n\nGeländemodell „%s“ wurde von Vectorworks erzeugt, auf Ebene „%s“ "
        "und Klasse „%s“ sichtbar geschaltet, einzeln markiert und in das "
        "Zeichenfenster eingepasst.\n"
        "Die Triangulation wurde zur Vermeidung von Koordinatenverzerrungen "
        "am internen Nullpunkt berechnet und danach auf die ursprüngliche "
        "Datenfläche zurückgesetzt; die Dokument-Georeferenz bleibt erhalten.\n"
        "Native Höhenprüfung: %d von %d Quellstützpunkten gültig; "
        "maximale Abweichung %.3f m.\n"
        "Das Geländemodell ist fertig; der Vectorworks-Befehl „Geländemodell "
        "aus Ausgangsdaten“ darf nicht nochmals aufgerufen werden.\n"
        "Höhenlinien-Äquidistanz im nativen Dialog: %.3f m; "
        "Höheneinheit der Modulauswertung: Meter."
        % (result["name"], result["layer"] or layer_name, result["class"],
           result["validated_points"], review["vertex_count"],
           result["maximum_error_m"], options["contour_interval_m"]))


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
