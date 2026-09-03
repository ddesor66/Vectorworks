# -*- coding: utf-8 -*-
"""Application workflow for the independent PD Kanaltool."""
from __future__ import absolute_import

from . import core
from . import live
from . import settings
from . import shaft_sheets_vw
from . import ui
from . import vw_adapter as adapter


# Descriptive aliases keep the proven workflow readable while its package is
# now independent from PD_GefaelleTool.
sewer_live = live
sewer_settings = settings
sewer_ui = ui


def _with_quantity_refresh(callback):
    """Keep reporting outside an asynchronous drawing transaction.

    Native VST callbacks run after ``app.run`` has returned.  Rebuilding a
    large worksheet synchronously here can delay the visible result by up to a
    minute.  The complete network change is therefore one reporting batch and
    only marks an existing report stale.  Opening or exporting quantities
    always rebuilds it from the current objects.
    """
    def complete(*args, **kwargs):
        from PD_KanalLeitungMengen import reporting as quantity_reporting
        quantity_reporting.begin_changes()
        succeeded = False
        try:
            result = callback(*args, **kwargs)
            succeeded = True
            return result
        finally:
            try:
                quantity_reporting.end_changes(
                    refresh=False, mark_dirty=succeeded)
            except Exception:
                # Reporting state must never undo or delay valid geometry.
                pass
    return complete


def _drawing_defaults(options, preferences):
    value = dict(options)
    value.setdefault("graphics_mode", preferences["graphics_mode"])
    value.setdefault("line_type", preferences["single_line_type"])
    value.setdefault("axis_line_type", preferences["axis_line_type"])
    value.setdefault("label_rotation_deg", preferences["label_rotation_deg"])
    return value


def _preference_default_scope(managed, has_channel_objects):
    """Choose an immediately visible but bounded settings-update scope."""
    if managed:
        # A shaft has no line representation of its own.  Applying a changed
        # one-/double-line standard only to that shaft would appear to do
        # nothing, so include its connected system by default.
        if all(data.get("role") == "sewer_shaft" for _handle, data in managed):
            return "systems"
        return "selection"
    return "drawing" if has_channel_objects else "save"


def _create(preferences, paths=None):
    paths = tuple(paths or ())
    options = sewer_ui.pipe_properties_dialog(preferences, source_count=len(paths))
    if options is None:
        return
    options = _drawing_defaults(options, preferences)

    def complete(values):
        handles = sewer_live.create(values, options, preferences)
        adapter.alert(
            "Kanalanlage mit %d Kanalstrecke(n) erstellt. Rohrhöhen werden als Sohlhöhen geführt; "
            "3D-Rohre und Schächte aktualisieren sich mit den verknüpften Objekten." % len(handles))
    if paths:
        complete(paths)
    else:
        adapter.draw_points(_with_quantity_refresh(
            lambda points: complete((points,))))


def _edit(preferences, managed):
    if not managed:
        raise core.SewerError("Zuerst eine Kanalstrecke, einen Schacht oder deren Beschriftung markieren.")
    if len(managed) == 1:
        if managed[0][1].get("role") == "sewer_rigole":
            handle = managed[0][0]
            current = sewer_live.read_rigole(handle)
            changed = sewer_ui.rigole_dialog(current)
            if changed is not None and sewer_live.update_rigole(
                    handle, changed, preferences):
                adapter.alert(
                    "Rigolenbauwerk wurde aktualisiert. Eine vorhandene Mengenliste "
                    "wird beim nächsten Öffnen oder Export neu berechnet.")
            return
        if sewer_live.edit(managed[0][0], preferences):
            adapter.alert("Kanalobjekt und angeschlossene Darstellung wurden aktualisiert.")
        return
    if all(data.get("role") == "sewer_shaft" for _handle, data in managed):
        if sewer_live.edit_shafts(
                tuple(handle for handle, _data in managed), preferences):
            adapter.alert(
                "%d Schächte mit sämtlichen gewählten Einzelwerten und angeschlossenen Haltungen aktualisiert."
                % len(managed))
        return
    if sewer_live.edit_network_chain(
            tuple(handle for handle, _data in managed), preferences):
        adapter.alert(
            "Kanalkette mit den ausgewählten Haltungen und Schächten wurde aktualisiert.")


def _split(preferences, managed):
    if len(managed) != 1 or managed[0][1].get("role") != "sewer_pipe":
        raise core.SewerError("Zum Teilen genau eine Kanalstrecke markieren.")

    def complete(point_m):
        try:
            sewer_live.split_selected(managed[0][0], point_m, preferences)
            adapter.alert("Kanalstrecke geteilt und neuer verbundener Schacht angelegt.")
        except Exception as error:
            adapter.alert("Kanalstrecke konnte nicht geteilt werden: %s" % error)
    adapter.pick_connection_point(_with_quantity_refresh(complete))


def _connect(preferences, managed):
    if len(managed) != 1 or managed[0][1].get("role") not in (
            "sewer_pipe", "sewer_shaft", "sewer_rigole"):
        raise core.SewerError(
            "Zum Anschließen genau eine Haltung, einen Schacht oder eine Rigole markieren.")
    handle, data = managed[0]
    role = data["role"]
    if role == "sewer_rigole":
        owner = sewer_live.read_rigole(handle)
        connection_height = sewer_ui.rigole_connection_height_dialog(owner)
        if connection_height is None:
            return
        initial = {
            "kind": preferences["default_kind"],
            "dn_mm": preferences["default_dn_mm"],
            "material": preferences["default_material"],
            "start_invert_m": connection_height,
            "calculation_mode": "start", "calculation_value": 1.5,
            "reverse_flow": True, "cover_height_m": owner["terrain_top_m"],
            "shaft_diameter_m": preferences["shaft_diameter_m"],
            "shaft_mode": "all",
            "shaft_construction_material": preferences["shaft_construction_material"],
            "shaft_wall_thickness_m": preferences["shaft_wall_thickness_m"],
            "cover_diameter_m": preferences["shaft_cover_diameter_m"],
            "cover_symbol": preferences["shaft_cover_symbol"],
            "cover_placement": preferences["shaft_cover_placement"],
            "cover_rotation_deg": preferences["shaft_cover_rotation_deg"],
            "join_style": preferences["join_style"],
            "fillet_radius_m": preferences["fillet_radius_m"],
            "flow_arrow_scale": preferences["flow_arrow_scale"],
            "label_layout": preferences["label_layout"],
            "label_width_m": 0.0,
            "label_rotation_deg": preferences["label_rotation_deg"],
            "draw_3d": preferences["draw_3d"],
            "graphics_mode": preferences["graphics_mode"],
            "color_override": None,
        }
        options = sewer_ui.pipe_properties_dialog(
            preferences, initial, source_count=0, editing=False, purpose="connect")
        if options is None:
            return
        options = _drawing_defaults(options, preferences)
        options["rigole_connection_invert_m"] = connection_height

        def complete_rigole(points):
            try:
                created, height = sewer_live.connect_from_rigole(
                    handle, (points,), options, preferences)
                adapter.alert(
                    "%d Haltung(en) bei KS = %.2f m an %s angeschlossen." %
                    (len(created), height, owner["name"]))
            except Exception as error:
                adapter.alert("Kanal konnte nicht an die Rigole angeschlossen werden: %s" % error)
        adapter.draw_points(
            _with_quantity_refresh(complete_rigole),
            help_text=("RIGOLENANSCHLUSS: Zuerst die Lage auf der markierten Rigole anklicken, "
                       "danach weitere Kanalpunkte setzen. Doppelklick oder Enter beendet."),
            undo_name="PD Kanal an Rigole anschließen")
        return
    if role == "sewer_pipe":
        owner = sewer_live.read_pipe(handle)
        connection_proposal = (owner["start_invert_m"] + owner["end_invert_m"]) * 0.5
        initial = dict(owner)
    else:
        owner = sewer_live.read_shaft(handle)
        connection_proposal = owner["ks_m"]
        initial = {
            "kind": owner["kind"],
            "dn_mm": preferences["dns"][0],
            "material": preferences["materials"][0],
            "join_style": preferences["join_style"],
            "fillet_radius_m": preferences["fillet_radius_m"],
            "flow_arrow_scale": preferences["flow_arrow_scale"],
            "label_layout": preferences["label_layout"],
            "label_width_m": 0.0,
            "label_rotation_deg": preferences["label_rotation_deg"],
            "draw_3d": preferences["draw_3d"],
        }
    initial.update(
        start_invert_m=connection_proposal, calculation_mode="start",
        calculation_value=max(float(initial.get("slope_percent", 1.5)), 0.1),
        reverse_flow=True,
        cover_height_m=connection_proposal + preferences["cover_offset_m"],
        shaft_diameter_m=preferences["shaft_diameter_m"], shaft_mode="all",
        shaft_construction_material=preferences["shaft_construction_material"],
        shaft_wall_thickness_m=preferences["shaft_wall_thickness_m"],
        cover_diameter_m=preferences["shaft_cover_diameter_m"],
        cover_symbol=preferences["shaft_cover_symbol"],
        cover_placement=preferences["shaft_cover_placement"],
        cover_rotation_deg=preferences["shaft_cover_rotation_deg"])
    options = sewer_ui.pipe_properties_dialog(
        preferences, initial, source_count=0, editing=False, purpose="connect")
    if options is None:
        return
    options = _drawing_defaults(options, preferences)

    def draw_from(start_xy, connector):
        def complete(points):
            try:
                created, height = connector((points,))
                adapter.alert(
                    "%d neue Kanalstrecke(n) bei KS = %.2f m höhengleich angeschlossen." %
                    (len(created), height))
            except Exception as error:
                adapter.alert("Neue Leitung konnte nicht angeschlossen werden: %s" % error)
        adapter.draw_points(
            _with_quantity_refresh(complete), first_point=start_xy,
            help_text=("KANALANSCHLUSS: Weitere Schacht-, Knick- oder Endpunkte anklicken. "
                       "Doppelklick beendet den neuen Kanalstrang."),
            undo_name="PD Kanalstrang anschließen")

    if role == "sewer_shaft":
        start_xy = owner["x_m"], owner["y_m"]
        draw_from(start_xy, lambda paths: sewer_live.connect_from_shaft(
            handle, paths, options, preferences))
        return

    def complete_pipe_branch(points):
        try:
            pipe = sewer_live.read_pipe(handle)
            (_start_handle, start), (_end_handle, end) = sewer_live._endpoints(pipe)
            fraction, xy = core.project_on_pipe(
                (start["x_m"], start["y_m"]), (end["x_m"], end["y_m"]), points[0])
            connection = (pipe["start_invert_m"] +
                          (pipe["end_invert_m"] - pipe["start_invert_m"]) * fraction)
            adjusted = dict(options)
            adjusted["cover_height_m"] = (connection +
                                           (options["cover_height_m"] - connection_proposal))
            branch = (xy,) + tuple(points[1:])
            created, height = sewer_live.connect_branch(
                handle, xy, (branch,), adjusted, preferences)
            adapter.alert(
                "%d neue Kanalstrecke(n) bei KS = %.2f m höhengleich angeschlossen." %
                (len(created), height))
        except Exception as error:
            adapter.alert("Neue Leitung konnte nicht angeschlossen werden: %s" % error)
    # Use one native tool session for the connection point and the complete
    # branch. Starting a second graphical tool from RunTempTool's cleanup
    # callback is not reliable in Vectorworks 2026 and caused the branch tool
    # to disappear after the first click on an existing pipe.
    adapter.draw_points(
        _with_quantity_refresh(complete_pipe_branch),
        help_text=("KANALANSCHLUSS: Als ersten Punkt die markierte Haltung anklicken. "
                   "Danach weitere Schacht-, Knick- oder Endpunkte setzen. "
                   "Doppelklick beendet den neuen Kanalstrang."),
        undo_name="PD Kanalstrang an Haltung anschließen")


def _connection_shaft_handles(managed, picker=None):
    """Use up to two selected shafts, then acquire missing shafts graphically."""
    picker = picker or adapter.pick_shaft
    handles = []
    for handle, data in managed:
        if data.get("role") == "sewer_shaft" and handle not in handles:
            handles.append(handle)
    if len(handles) > 2:
        raise core.SewerError(
            "Zum Verbinden höchstens zwei Schächte markieren oder die Auswahl aufheben.")
    prompts = (
        "ERSTER SCHACHT: Ersten vorhandenen Kanalschacht anklicken. Esc: abbrechen.",
        "ZWEITER SCHACHT: Zweiten vorhandenen Kanalschacht anklicken. Esc: abbrechen.")
    while len(handles) < 2:
        handle = picker(prompts[len(handles)])
        if not handle:
            return ()
        if handle in handles:
            raise core.SewerError("Bitte zwei unterschiedliche Schächte wählen.")
        handles.append(handle)
    return tuple(handles)


def _connect_shafts(preferences, managed):
    handles = _connection_shaft_handles(managed)
    if not handles:
        return
    first = sewer_live.read_shaft(handles[0])
    second = sewer_live.read_shaft(handles[1])
    selected = sewer_ui.shaft_connection_dialog(first, second, preferences)
    if selected is None:
        return
    dn_mm = selected["dn_mm"]
    options = _drawing_defaults({
        "kind": first["kind"],
        "network_id": first["kind"],
        "name": "",
        "dn_mm": dn_mm,
        "outside_diameter_mm": dn_mm,
        "outside_diameter_explicit": False,
        "material": selected["material"],
        "shaft_diameter_m": preferences["shaft_diameter_m"],
        "shaft_construction_material": preferences["shaft_construction_material"],
        "shaft_wall_thickness_m": preferences["shaft_wall_thickness_m"],
        "cover_diameter_m": preferences["shaft_cover_diameter_m"],
        "cover_symbol": preferences["shaft_cover_symbol"],
        "cover_placement": preferences["shaft_cover_placement"],
        "cover_rotation_deg": preferences["shaft_cover_rotation_deg"],
        "join_style": preferences["join_style"],
        "fillet_radius_m": preferences["fillet_radius_m"],
        "flow_arrow_scale": preferences["flow_arrow_scale"],
        "label_layout": preferences["label_layout"],
        "label_width_m": 0.0,
        "label_rotation_deg": preferences["label_rotation_deg"],
        "draw_3d": selected["draw_3d"],
        "graphics_mode": selected["graphics_mode"],
        "color_override": None,
    }, preferences)
    sewer_live.connect_selected_shafts(
        handles, options, preferences)
    adapter.alert(
        "Die Schächte %s und %s wurden mit einer Haltung DN %d verbunden." %
        (first["name"], second["name"], dn_mm))


def _selected_or_picked(managed, role):
    rows = tuple(row for row in managed if row[1].get("role") == role)
    if len(rows) == 1:
        return rows[0][0]
    if rows:
        raise core.SewerError("Bitte genau ein Kanalobjekt für diese Aktion markieren.")
    return (adapter.pick_pipe() if role == "sewer_pipe" else adapter.pick_shaft())


def _stub(preferences, managed):
    handle = _selected_or_picked(managed, "sewer_pipe")
    if not handle:
        return
    pipe = sewer_live.read_pipe(handle)
    initial = dict(
        kind=pipe["kind"], dn_mm=preferences["stub_dn_mm"],
        material=preferences["default_material"],
        start_invert_m=pipe["end_invert_m"], calculation_mode="start",
        calculation_value=max(pipe["slope_percent"], 1.0), reverse_flow=True,
        cover_height_m=max(pipe["start_invert_m"], pipe["end_invert_m"]) + preferences["cover_offset_m"],
        shaft_diameter_m=0.0, shaft_mode="endpoints",
        cover_diameter_m=preferences["shaft_cover_diameter_m"], cover_symbol="",
        cover_placement="center", cover_rotation_deg=0.0,
        join_style=preferences["join_style"], fillet_radius_m=preferences["fillet_radius_m"],
        flow_arrow_scale=preferences["flow_arrow_scale"], label_layout=preferences["label_layout"],
        label_width_m=0.0, label_rotation_deg=preferences["label_rotation_deg"],
        draw_3d=preferences["draw_3d"])
    dialog_preferences = dict(preferences)
    dialog_preferences["dns"] = sorted(set(preferences["dns"] + [preferences["stub_dn_mm"]]))
    options = sewer_ui.pipe_properties_dialog(
        dialog_preferences, initial, source_count=0, editing=False, purpose="connect")
    if options is None:
        return
    alignment = sewer_ui.stub_alignment_dialog()
    if alignment is None:
        return
    options = _drawing_defaults(options, preferences)
    options.update(connection_alignment=alignment, as_stub=True, shaft_diameter_m=0.0,
                   stub_stationing=True)

    def complete(points):
        try:
            owner = sewer_live.read_pipe(handle)
            (_start_handle, start), (_end_handle, end) = sewer_live._endpoints(owner)
            _fraction, xy = core.project_on_pipe(
                (start["x_m"], start["y_m"]), (end["x_m"], end["y_m"]), points[0])
            branch = (xy,) + tuple(points[1:])
            created, height = sewer_live.connect_stub(
                handle, xy, (branch,), options, preferences)
            adapter.alert(
                "Kanalstutzen %s bei Anschlusshöhe %.2f m und %d Anschlussleitung(en) erstellt." %
                (core.connection_alignment_label(alignment), height, len(created)))
        except Exception as error:
            adapter.alert("Kanalstutzen konnte nicht erstellt werden: %s" % error)
    adapter.draw_points(
        _with_quantity_refresh(complete),
        help_text=("KANALSTUTZEN: Zuerst die Lage auf der gewählten Haltung anklicken. "
                   "Danach die DN-%d-Anschlussleitung zeichnen; Doppelklick beendet." % options["dn_mm"]),
        undo_name="PD Kanalstutzen herstellen")


def _special(preferences, managed):
    shaft = _selected_or_picked(managed, "sewer_shaft")
    if not shaft:
        return
    polygon = adapter.pick_polygon(
        "Geschlossene, frei gezeichnete Kontur auf der Konstruktionsebene anklicken. "
        "Die Geometrie innerhalb eines Kanalobjekts kann nicht als Vorlage verwendet werden. Esc: abbrechen.")
    if not polygon:
        return
    sewer_live.replace_with_special(shaft, polygon, preferences)
    adapter.alert("Der runde Schacht wurde durch den gewählten Sonderschacht ersetzt.")


def _drop(preferences, managed):
    handle = _selected_or_picked(managed, "sewer_shaft")
    if not handle:
        return
    shaft = sewer_live.read_shaft(handle)
    pipes = tuple(value for _pipe_handle, value in sewer_live._connected_pipes(shaft["id"]))
    value = sewer_ui.drop_dialog(shaft, pipes)
    if value is None:
        return
    sewer_live.set_drop(handle, value, preferences)
    adapter.alert("Absturz vor Schacht %s wurde angelegt und beschriftet." % shaft["name"])


def _terminal(preferences, structure_type):
    value = sewer_ui.terminal_dialog(structure_type, preferences)
    if value is None:
        return

    def complete(points):
        try:
            created, height = sewer_live.connect_terminal(points, value, preferences)
            noun = "Bodenablauf" if structure_type == "floor_drain" else "Hausanschluss"
            adapter.alert("%s mit %d Haltung(en) bei Anschluss KS = %.2f m erstellt." %
                          (noun, len(created), height))
        except Exception as error:
            adapter.alert("Anschluss konnte nicht erstellt werden: %s" % error)
    adapter.draw_points(
        _with_quantity_refresh(complete),
        help_text=("Vom Bodenablauf zur Hauptleitung zeichnen. " if structure_type == "floor_drain" else
                   "Vom freien Hausanschlussende zur Hauptleitung zeichnen. ") +
                  "Der Doppelklickpunkt muss auf der bestehenden Haltung liegen.",
        undo_name="PD Bodenablauf anschließen" if structure_type == "floor_drain" else
                  "PD Hausanschluss anschließen")


def _rigole(preferences):
    values = sewer_ui.rigole_dialog()
    if values is None:
        return

    def complete(point_m):
        try:
            handle = sewer_live.create_rigole(point_m, values, preferences)
            rigole = sewer_live.read_rigole(handle)
            adapter.alert(
                "%s eingesetzt: Rigolenvolumen %.2f m³, Rückhaltevolumen (95 %% FV) %.2f m³."
                % (rigole["name"], rigole["gross_volume_m3"],
                   rigole["storage_volume_m3"]))
        except Exception as error:
            adapter.alert("Rigolenbauwerk konnte nicht eingesetzt werden: %s" % error)
    adapter.pick_connection_point(
        _with_quantity_refresh(complete),
        "RIGOLE: Mittelpunkt des Bauwerks anklicken. Esc: abbrechen.")


def _shaft_sheets(preferences, managed):
    handles = tuple(handle for handle, data in managed
                    if data.get("role") == "sewer_shaft")
    if not handles:
        raise core.SewerError("Bitte einen oder mehrere runde Schächte oder Sonderschächte markieren.")
    shafts = tuple(sewer_live.read_shaft(handle) for handle in handles)
    config = sewer_ui.shaft_sheet_dialog(
        tuple(shaft["name"] for shaft in shafts), preferences)
    if config is None:
        return
    all_shafts = tuple(shaft for _handle, shaft in sewer_live.shaft_records())
    all_pipes = tuple(pipe for _handle, pipe in sewer_live.pipe_records())
    layer_names = shaft_sheets_vw.prepare_pages(
        handles, config, preferences, sewer_live.read_shaft, all_shafts, all_pipes)
    updated = dict(preferences)
    for source, target in (
            ("project_name", "sheet_project_name"),
            ("channel_type", "sheet_channel_type"),
            ("comments", "sheet_comments"),
            ("logo_path", "sheet_logo_path"),
            ("height_mode", "sheet_height_mode"),
            ("clock_mode", "sheet_clock_mode"),
            ("north_rotation_deg", "sheet_north_rotation_deg"),
            ("include_section", "sheet_include_section")):
        updated[target] = config[source]
    sewer_settings.save(updated)
    if config["output"] == "pdf":
        if shaft_sheets_vw.export_pdf(layer_names, config["project_name"] + " Schachtblätter"):
            adapter.alert(
                "%d DIN-A4-Schachtblätter wurden als gemeinsame mehrseitige PDF-Datei exportiert." %
                len(layer_names))
        else:
            adapter.alert("PDF-Ausgabe abgebrochen; die Schachtblatt-Vorschau bleibt erhalten.")
    elif config["output"] == "print":
        shaft_sheets_vw.print_pages(layer_names)
        adapter.alert("Druckdialog für %d Schachtblatt/Schachtblätter abgeschlossen." % len(layer_names))
    else:
        adapter.alert(
            "%d Schachtblatt/Schachtblätter als DIN-A4-Layoutebenen erzeugt. "
            "Die erste Seite ist zur Vorschau geöffnet." % len(layer_names))


_QUANTITY_MUTATIONS = frozenset((
    "sources", "draw", "edit", "split", "connect", "connect_shafts", "stub",
    "special", "drop", "floor_drain", "house", "rigole", "merge", "delete",
    "terrain_covers", "settings", "smart",
))
_NATIVE_TOOL_MUTATIONS = frozenset((
    "draw", "connect", "stub", "floor_drain", "house",
))


def run(action=None):
    quantity_reporting = None
    quantity_batch = False
    try:
        adapter.cancel_point_input()
        preferences = sewer_settings.load()
        sources = sewer_live.selected_source_paths()
        managed = sewer_live.selected_managed()
        if action is None:
            managed_role = managed[0][1].get("role") if len(managed) == 1 else None
            selected_shaft_count = sum(
                1 for _handle, data in managed if data.get("role") == "sewer_shaft")
            selected_pipe_count = sum(
                1 for _handle, data in managed if data.get("role") == "sewer_pipe")
            action = sewer_ui.home_dialog(
                len(sources), len(managed), managed_role, selected_shaft_count,
                selected_pipe_count)
        if action is None:
            return
        native_tool_change = (
            action in _NATIVE_TOOL_MUTATIONS or
            action == "smart" and not managed and not sources)
        if action in _QUANTITY_MUTATIONS and not native_tool_change:
            from PD_KanalLeitungMengen import reporting as quantity_reporting
            quantity_reporting.begin_changes()
            quantity_batch = True
        if action == "sources":
            if not sources:
                raise core.SewerError(
                    "Zuerst eine vorhandene Linie, offene Polylinie oder ein Polygon markieren "
                    "und den Befehl erneut öffnen.")
            _create(preferences, sources)
        elif action == "draw":
            _create(preferences)
        elif action == "rigole":
            _rigole(preferences)
        elif action == "edit":
            _edit(preferences, managed)
        elif action == "split":
            _split(preferences, managed)
        elif action == "connect":
            _connect(preferences, managed)
        elif action == "connect_shafts":
            _connect_shafts(preferences, managed)
        elif action == "stub":
            _stub(preferences, managed)
        elif action == "special":
            _special(preferences, managed)
        elif action == "drop":
            _drop(preferences, managed)
        elif action == "floor_drain":
            _terminal(preferences, "floor_drain")
        elif action == "house":
            _terminal(preferences, "house")
        elif action == "merge":
            sewer_live.merge_selected(managed, preferences)
            adapter.alert("Zwei Kanalstrecken wurden vereinigt; der Zwischenknoten wurde entfernt.")
        elif action == "delete":
            if sewer_ui.confirm_delete(len(managed)):
                pipes, shafts, rigoles = sewer_live.delete_selected(managed)
                adapter.alert(
                    "%d Kanalstrecke(n), %d Schacht/Schächte und %d Rigole(n) gelöscht. Rückgängig bleibt verfügbar."
                    % (pipes, shafts, rigoles))
        elif action == "validate":
            result = sewer_live.validate_document(preferences)
            adapter.alert(
                "Kanalnetz fehlerfrei: %d Rohrstrecken, %d sichtbare Schächte, %d Verbindungsknoten, %d Rigolen."
                % (result["pipes"], result["shafts"], result["nodes"], result["rigoles"]))
        elif action == "terrain_covers":
            selected_shafts = tuple(handle for handle, data in managed
                                    if data.get("role") == "sewer_shaft")
            result = sewer_live.align_shaft_covers_to_site_model(
                selected_shafts or None, "", 2)
            adapter.alert(
                "%d Schachtdeckel an den Ist-/Soll-Zustand des gewählten Geländemodells angepasst. "
                "Schachtsohlen und Kanalrohre blieben unverändert." % result["shafts"])
        elif action == "shaft_sheets":
            _shaft_sheets(preferences, managed)
        elif action == "quantities":
            from PD_KanalLeitungMengen import app as quantities_app
            quantities_app.run()
        elif action == "settings":
            has_channel_objects = bool(
                sewer_live.objects("sewer_pipe") or
                sewer_live.objects("sewer_shaft") or
                sewer_live.objects("sewer_rigole"))
            updated, update_scope = sewer_ui.preferences_dialog(
                preferences,
                _preference_default_scope(managed, has_channel_objects))
            if updated is not None:
                preferences = sewer_settings.save(updated)
                sewer_live.ensure_classes(preferences)
                count = (sewer_live.apply_preferences(
                    preferences, managed, update_scope)
                         if update_scope != "save" else 0)
                scope_labels = {
                    "selection": "in der Markierung",
                    "systems": "in den angeschlossenen Kanalsystemen",
                    "drawing": "in der gesamten Zeichnung",
                }
                adapter.alert(
                    "Kanaleinstellungen gespeichert.%s" %
                    ((" %d Kanalobjekt(e) %s aktualisiert. Sohlhöhen, Namen, DN und Material "
                      "blieben erhalten." % (count, scope_labels[update_scope]))
                     if update_scope != "save" else ""))
        elif action == "smart":
            if managed:
                _edit(preferences, managed)
            elif sources:
                _create(preferences, sources)
            else:
                _create(preferences)
        else:
            raise core.SewerError("Unbekannte Kanalaktion.")
        if quantity_batch:
            quantity_reporting.end_changes(refresh=False, mark_dirty=True)
            quantity_batch = False
    except (core.SewerError, RuntimeError, ValueError) as error:
        adapter.alert(error)
    except Exception as error:
        adapter.alert("Kanalanlage: unerwarteter Fehler: %s" % error)
    finally:
        if quantity_batch:
            quantity_reporting.end_changes(refresh=False)
