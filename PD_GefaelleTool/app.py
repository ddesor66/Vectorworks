# -*- coding: utf-8 -*-
"""Application workflow for PD Gefälle-Tool."""

from __future__ import absolute_import

from . import core
from . import settings
from . import ui
from . import vw_adapter
from . import point_output
from . import insert_point
from . import chain_edit
import copy


def _selection_status():
    source = 0
    managed = 0
    for handle in vw_adapter.selected_handles():
        object_type = vw_adapter.object_type(handle)
        if object_type in (vw_adapter.TYPE_LINE, vw_adapter.TYPE_POLYGON,
                           vw_adapter.TYPE_POLYLINE):
            source += 1
        if vw_adapter.read_chain(handle):
            managed += 1
    if source == 1:
        return "Auswahl erkannt: eine geeignete Linie ist markiert."
    if managed == 1:
        return "Auswahl erkannt: eine Gefällegruppe ist markiert."
    return "Keine eindeutige Auswahl erkannt; Zeichen- und Einstellaktionen sind weiterhin verfügbar."


def _all_chains():
    return tuple(chain for _handle, chain in vw_adapter.chain_records())


def _occupied_numbers(chains):
    return ({p["number"] for chain in chains for p in chain["points"]}
            | vw_adapter.independent_point_numbers())


def _choose_network(preferences):
    rows = vw_adapter.network_rows()
    if rows:
        return ui.network_dialog(rows, preferences["default_level"]), True
    return preferences["default_level"], False


def _new_chain(preferences, draw_mode):
    occupied = _occupied_numbers(_all_chains())
    source = None if draw_mode else vw_adapter.selected_source_path()
    source_points = source["points"] if source else None
    curve = source["curve"] if source else None
    level, lock_level = _choose_network(preferences)
    if level is None:
        return
    defaults = ui.calculation_dialog(
        level, max(occupied or {0}) + 1,
        draw_mode=draw_mode, curved=curve is not None, lock_level=lock_level)
    if defaults is None:
        return
    def complete(points):
        # The range is only known after an open-ended drawing has finished.
        existing_chains = _all_chains()
        occupied_numbers = _occupied_numbers(existing_chains)
        requested_numbers = set(range(
            int(defaults["start_number"]), int(defaults["start_number"]) + len(points)))
        conflict = sorted(occupied_numbers.intersection(requested_numbers))
        if conflict:
            raise core.SlopeError(
                "Punktnummer P:%d ist bereits vergeben. Bitte mit P:%d beginnen."
                % (conflict[0], max(occupied_numbers or {0}) + 1))
        chain = core.make_chain(
            points, defaults["start_height_m"], defaults["mode"],
            defaults["value"], defaults["start_number"], defaults["level"], curve=curve)
        core.validate_document_numbering(existing_chains + (chain,))
        vw_adapter.create_chain_group(chain, preferences)
        vw_adapter.alert(
            "Gefälle mit %d Punkten auf Ebene '%s' erstellt." % (
                len(chain["points"]), chain["layer_name"]))

    if draw_mode:
        vw_adapter.draw_points(complete)
    else:
        complete(source_points)


def _branch(preferences):
    records = tuple(vw_adapter.chain_records())
    if not vw_adapter.independent_points():
        raise core.SlopeError("Es ist noch kein Höhenpunkt vorhanden.")
    level, lock_level = _choose_network(preferences)
    if level is None:
        return
    selected = vw_adapter.pick_height_object(
        "Ausgangspunkt des neuen Gefälles grafisch anklicken. Esc: abbrechen.")
    if selected is None:
        return
    point_handle, point_data, parent_point = selected
    rows = (("graphical", point_data.get("level", "Standard"),
             int(parent_point["number"]), float(parent_point["height_m"])),)
    choice = ui.branch_dialog(
        rows, level, max(_occupied_numbers(tuple(c for _, c in records)) or {0}) + 1,
        lock_level=lock_level)
    if choice is None:
        return

    def complete(new_points):
        existing = _all_chains()
        from . import live_objects, live_model
        current = live_objects.read_point(point_handle)
        if current != parent_point:
            raise core.SlopeError("Der Anschlusspunkt wurde zwischenzeitlich geändert. Bitte erneut anschließen.")
        branch = live_model.continuation(
            current, new_points, choice["mode"],
            choice["value"], max(_occupied_numbers(existing) or {0}) + 1,
            choice["level"])
        core.validate_document_numbering(existing + (branch,))
        vw_adapter.create_chain_group(branch, preferences)
        vw_adapter.alert("Weiterführendes Gefälle wurde erstellt.")

    vw_adapter.draw_branch_points(
        (parent_point["x_m"], parent_point["y_m"]), complete)


def _edit_point(preferences):
    handle, chain = vw_adapter.selected_chain_record()
    choice = ui.edit_point_dialog(chain)
    if choice is None:
        return
    changed = core.change_point_height(chain, choice[0], choice[1])
    _replace_connected(handle, chain, changed, preferences)
    vw_adapter.alert("Punkthöhe und angrenzende Gefälle wurden aktualisiert.")


def _edit_slope(preferences):
    handle, chain = vw_adapter.selected_chain_record()
    choice = ui.edit_slope_dialog(chain, core.segment_rows(chain))
    if choice is None:
        return
    changed = core.change_segment_slope(chain, *choice)
    _replace_connected(handle, chain, changed, preferences)
    vw_adapter.alert("Gefälle und gewählte Punkthöhe wurden aktualisiert.")


def _connected_replacements(handle, original, changed):
    records = tuple(vw_adapter.chain_records())
    updates = core.connected_height_updates(original, changed,
                (chain for h, chain in records if h != handle))
    by_id = {chain["chain_id"]: h for h, chain in records}
    by_id[original["chain_id"]] = handle
    return tuple((by_id[chain["chain_id"]], chain) for chain in updates)


def _replace_connected(handle, original, changed, preferences):
    replacements = _connected_replacements(handle, original, changed)
    # Height-only edits must not apply today's defaults to all connected nets.
    return vw_adapter.replace_chain_groups(replacements, None)


def _insert_point(preferences):
    handle, original = vw_adapter.selected_chain_record()

    def unchanged():
        current = vw_adapter.read_chain(handle)
        if current != original:
            raise core.SlopeError("Die Gefällegruppe wurde zwischenzeitlich geändert. Bitte den Befehl erneut starten.")
        return current

    def complete(click):
        chain = unchanged()
        next_number = max(_occupied_numbers(_all_chains()) or {0}) + 1
        evaluate = vw_adapter.connection_evaluator(handle, chain)
        changed, info = insert_point.preview(chain, click, next_number, evaluate)
        if not ui.insert_point_dialog(info):
            return
        unchanged()
        if next_number in _occupied_numbers(_all_chains()):
            raise core.SlopeError("Die angezeigte Punktnummer ist inzwischen vergeben. Bitte erneut einfügen.")
        vw_adapter.replace_chain_group(handle, changed, None)
        vw_adapter.alert("Höhenpunkt P:%d mit H=%s m eingefügt. Beide Teilverbindungen sind aktualisiert." %
                         (next_number, ("%.2f" % info["height_m"]).replace(".", ",")))

    vw_adapter.pick_connection_point(complete)


def _edit_chain(preferences):
    handle, original = vw_adapter.selected_chain_record()
    choice = None

    def highlight(mode, rows):
        import vs
        from . import live_objects
        selected_indexes = set()
        for row in rows:
            selected_indexes.update((row,) if mode == "points" else (row, row + 1))
        data = live_objects.data_of(handle)
        vs.DSelectAll()
        vs.SetSelect(handle)
        for index, name in enumerate(data.get("points", ())):
            point_handle = vs.GetObject(name)
            if point_handle and index in selected_indexes:
                vs.SetSelect(point_handle)
        vs.ReDrawAll()

    while True:
        try:
            choice = ui.chain_selection_dialog(original, choice, highlight)
        finally:
            import vs
            if callable(getattr(vs, "DSelectAll", None)):
                vs.DSelectAll()
            if callable(getattr(vs, "SetSelect", None)):
                vs.SetSelect(handle)
            if callable(getattr(vs, "ReDrawAll", None)):
                vs.ReDrawAll()
        if choice is None:
            return
        changed, info = chain_edit.preview(original, **choice)
        try:
            replacements = _connected_replacements(handle, original, changed)
            info["connected_groups"] = len(replacements)-1
        except core.SlopeError as error:
            vw_adapter.alert(error)
            continue
        if not ui.chain_preview_dialog(info):
            # Back from preview keeps the selection and all entered values.
            continue
        current = vw_adapter.read_chain(handle)
        if current != original:
            raise core.SlopeError("Die Gefällegruppe wurde zwischenzeitlich geändert. Bitte den Befehl erneut starten.")
        current_replacements = _connected_replacements(handle, original, changed)
        if current_replacements != replacements:
            raise core.SlopeError("Die angeschlossenen Gruppen wurden zwischenzeitlich geändert. Bitte Vorschau erneut aufrufen.")
        vw_adapter.replace_chain_groups(current_replacements, None)
        if info.get("operation") == "heights":
            vw_adapter.alert("%d Punkthöhe(n) und angrenzende Gefälle aktualisiert. "
                             "Gemeinsame Anschlusspunkte wurden mitgeführt; alle anderen Höhen bleiben unverändert."
                             % len(info["points"]))
            return
        vw_adapter.alert("Kette P:%d → P:%d auf %s %% geändert. P:%d bleibt auf H=%s m." %
                         (info["from_number"], info["to_number"],
                          ("%.4f" % info["slope_percent"]).replace(".", ","), info["fixed_number"],
                          ("%.2f" % info["fixed_height_m"]).replace(".", ",")))
        return


def _single_point(preferences):
    number = max(_occupied_numbers(_all_chains()) or {0}) + 1
    level, lock_level = _choose_network(preferences)
    if level is None:
        return
    choice = ui.single_point_dialog(number, level, lock_level=lock_level)
    if choice is None:
        return

    def complete_many(points):
        drafts = [(points[0], choice["height_m"], number)]
        last_height = choice["height_m"]
        for index, xy in enumerate(points[1:], 1):
            following = ui.single_point_dialog(
                number + index, choice["level"], lock_level=True,
                default_height=last_height, allow_multiple=False)
            if following is None:
                vw_adapter.alert("Punktfolge abgebrochen; es wurde kein Höhenpunkt erstellt.")
                return
            last_height = following["height_m"]
            drafts.append((xy, last_height, number + index))
        vw_adapter.create_independent_points(drafts, choice["level"], preferences)
        vw_adapter.alert("%d Höhenpunkte P:%d bis P:%d gesetzt. Sie können direkt verschoben und verbunden werden." %
                         (len(drafts), number, number + len(drafts) - 1))

    if choice.get("multiple"):
        vw_adapter.draw_height_points(complete_many)
    else:
        def complete(xy):
            vw_adapter.create_independent_point(
                xy, choice["height_m"], number, choice["level"], preferences)
            vw_adapter.alert("Höhenpunkt P:%d gesetzt. Er kann direkt verschoben und später verbunden werden." % number)
        vw_adapter.pick_height_point(complete)


def _connect_points(preferences):
    points = vw_adapter.independent_points()
    if len(points) < 2:
        raise core.SlopeError("Zuerst mindestens zwei eigenständige Höhenpunkte setzen.")
    level, _lock_level = _choose_network(preferences)
    if level is None:
        return
    first = vw_adapter.pick_height_object(
        "Ersten Höhenpunkt der Verbindung grafisch anklicken. Esc: abbrechen.")
    if first is None:
        return
    second = vw_adapter.pick_height_object(
        "Zweiten Höhenpunkt grafisch anklicken. Esc: abbrechen.",
        (vw_adapter.object_name(first[0]),))
    if second is None:
        return
    vw_adapter.connect_existing_points(
        vw_adapter.object_name(first[0]), vw_adapter.object_name(second[0]),
        level, preferences)
    vw_adapter.alert("Vorhandene Höhenpunkte verbunden. Beide Höhen bleiben unverändert.")


def run(action=None):
    try:
        vw_adapter.cancel_point_input()
        preferences = settings.load()
        if action is None:
            action = ui.home_dialog(_selection_status())
        if action is None:
            return
        if action == 0:
            _new_chain(preferences, False)
        elif action == 1:
            _new_chain(preferences, True)
        elif action == 2:
            _branch(preferences)
        elif action == 3:
            _edit_point(preferences)
        elif action == 4:
            _edit_slope(preferences)
        elif action == 5:
            handle, chain = vw_adapter.selected_chain_record()
            vw_adapter.replace_chain_group(handle, chain, preferences)
            vw_adapter.alert("Markiertes Gefälle wurde neu gezeichnet.")
        elif action == 6:
            count = vw_adapter.redraw_all(preferences)
            vw_adapter.alert("%d Gefällegruppe(n) wurden neu gezeichnet." % count)
        elif action == 7:
            updated = ui.preferences_dialog(preferences)
            if updated is not None:
                preferences = settings.save(updated)
                vw_adapter.ensure_classes(preferences)
                vw_adapter.alert("Voreinstellungen wurden gespeichert.")
        elif action == 8:
            point = vw_adapter.selected_point_display()
            if point is not None:
                handle, data = point
                updated = ui.point_output_dialog(data["output"], data["preferences"]["classes"]["line"]["name"])
                if updated is not None:
                    vw_adapter.replace_point_display(handle, updated)
                    vw_adapter.alert("Punktdarstellung aktualisiert. Nummer, Höhe und Verbindungen bleiben erhalten. "
                                     "Bei 3D-Ausgabe wurde der Geländemodifikator automatisch erneuert; "
                                     "die Netzebene muss im Geländemodell für Modifikatoren zugelassen sein.")
                return
            handle, chain = vw_adapter.selected_chain_record()
            updated = ui.point_output_dialog(point_output.options(
                chain.get("point_output", preferences.get("point_output"))), preferences["classes"]["line"]["name"])
            if updated is not None:
                changed = copy.deepcopy(chain)
                changed["point_output"] = updated
                changed["schema"] = core.SCHEMA_VERSION
                vw_adapter.replace_chain_group(handle, changed, preferences)
                terrain_note = ""
                if updated["mode"] == "3d" and (updated["terrain_modifier"] or updated["point_terrain_modifier"]):
                    terrain_note = " Geländemodifikator aktiv: Netzebene im Geländemodell zulassen und dort 'Aktualisieren' wählen."
                elif any(chain.get("point_output", {}).get(k, False) for k in ("terrain_modifier", "point_terrain_modifier")):
                    terrain_note = " Geländewirkung deaktiviert: Geländemodell jetzt 'Aktualisieren'."
                vw_adapter.alert("Darstellung aktualisiert: vollständiger 2D-Plan" +
                                 (" mit zusätzlichen 3D-Punkten und Linien. " if updated["mode"] == "3d"
                                  else " ohne zusätzliche 3D-Ausgabe. ") + "Höhen und Nummern bleiben erhalten." + terrain_note)
        elif action == 9:
            kind = ui.terrain_dialog()
            if kind is not None:
                layer, count = vw_adapter.export_terrain_data(kind, preferences)
                vw_adapter.alert("%d Objekt(e) auf '%s' bereitgestellt und markiert. "
                                 "Jetzt Vectorworks-Geländedatenprüfung ausführen und daraus das Geländemodell erstellen. "
                                 "Bei späteren Änderungen die Ausgangsdaten erneut bereitstellen." % (count, layer))
        elif action == 10:
            _insert_point(preferences)
        elif action == 11:
            _edit_chain(preferences)
        elif action == 12:
            _single_point(preferences)
        elif action == 13:
            _connect_points(preferences)
    except (core.SlopeError, RuntimeError, ValueError) as error:
        vw_adapter.alert(error)
    except Exception as error:
        vw_adapter.alert("Gefälle-Tool: unerwarteter Fehler: %s" % error)
