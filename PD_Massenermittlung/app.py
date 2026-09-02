# -*- coding: utf-8 -*-
"""Application orchestration for the PD Vectorworks tool suite."""

from __future__ import absolute_import

import os
import traceback

from .core_duplicates import (
    DuplicatePolicy,
    analyze_duplicates,
    detect_parallel_source_keys,
)
from .core_patterns import RenameStatus, RenameStep
from .core_quantities import ObjectKind, SourceKey, aggregate_quantities
from .document_database import (
    FIELD_SPECS as DOCUMENT_DATABASE_FIELDS,
    RECORD_NAME as DOCUMENT_DATABASE_NAME,
    build_object_record_values,
)
from .reporting import (
    create_vectorworks_worksheet,
    default_xlsx_path,
    export_xlsx,
    read_catalog_from_worksheet,
    replace_vectorworks_worksheet,
    show_vectorworks_worksheet,
    worksheet_resource_name,
)
from .mass_database import (
    DATABASE_FILENAME,
    MassDatabase,
    MassDatabaseError,
    SCHEMA_VERSION as MASS_DATABASE_SCHEMA_VERSION,
    complete_catalog_record,
    normalize_catalog,
)
from .product_database import (
    ProductDatabase,
    ProductDatabaseError,
    SCHEMA_VERSION as PRODUCT_DATABASE_SCHEMA_VERSION,
)
from .report_columns import normalize_visible_columns, validate_editable_columns
from .state_store import StateStore
from .user_storage import data_path
from . import ui
from . import vw_adapter


VERSION = "2.3.0"


def _module_directory():
    return os.path.dirname(os.path.abspath(__file__))


def _logo_path():
    for name in ("PD_Logo.png", "PD_MW_Logo.png"):
        candidate = os.path.join(_module_directory(), "assets", name)
        if os.path.isfile(candidate):
            return candidate
        candidate = os.path.join(_module_directory(), name)
        if os.path.isfile(candidate):
            return candidate
    return ""


def _state_store():
    return StateStore(_data_path("PD_Massenermittlung_Status.json"))


def _data_path(filename):
    folder = vw_adapter._call("GetFolderPath", -12, default="")
    return data_path(filename, _module_directory(), str(folder or ""))


def _product_database():
    """Return the legacy product-only database used for one-time migration."""
    return ProductDatabase(_data_path("PD_Massentabelle.sqlite3"))


def _mass_database():
    return MassDatabase(_data_path(DATABASE_FILENAME))


def _name_undo_event(name):
    vw_adapter._call("NameUndoEvent", str(name))


def run_visibility():
    settings = ui.visibility_dialog(_logo_path())
    if settings is None:
        return
    snapshot = vw_adapter.capture_visibility()
    store = _state_store()
    document_key = vw_adapter.document_key()
    try:
        _name_undo_event("PD Klassen-/Ebenensichtbarkeit")
        vw_adapter.apply_visibility_action(
            settings["classes"], settings["layers"], settings["action"],
            settings["affect_classes"], settings["affect_layers"])
        store.push_visibility(
            document_key, snapshot, vw_adapter.now_timestamp())
    except Exception:
        # The captured state remains authoritative until both the Vectorworks
        # change and its persisted history entry have succeeded.
        try:
            vw_adapter.apply_visibility_snapshot(snapshot)
        except Exception:
            pass
        raise
    vw_adapter.info(
        "PD Sichtbarkeit angewendet – Rückkehr über "
        "„PD Sichtbarkeit zurück“ (maximal 3 Schritte).")


def run_visibility_restore(redo=False):
    store = _state_store()
    key = vw_adapter.document_key()
    current = vw_adapter.capture_visibility()
    snapshot = (store.peek_visibility_redo(key) if redo
                else store.peek_visibility_undo(key))
    verb = "wiederholt" if redo else "wiederhergestellt"
    if snapshot is None:
        vw_adapter.alert(
            "Für dieses Dokument ist kein weiterer Sichtbarkeitsschritt vorhanden.",
            "PD Sichtbarkeit")
        return
    _name_undo_event("PD Sichtbarkeit " + verb)
    try:
        vw_adapter.apply_visibility_snapshot(snapshot)
        if redo:
            store.commit_visibility_redo(
                key, snapshot, current, vw_adapter.now_timestamp())
        else:
            store.commit_visibility_undo(
                key, snapshot, current, vw_adapter.now_timestamp())
    except Exception:
        try:
            vw_adapter.apply_visibility_snapshot(current)
        except Exception:
            pass
        raise
    vw_adapter.info("PD Sichtbarkeit wurde %s." % verb)


def _unique_path(path):
    if not path or not os.path.exists(path):
        return path
    root, extension = os.path.splitext(path)
    counter = 2
    while True:
        candidate = "%s_%d%s" % (root, counter, extension)
        if not os.path.exists(candidate):
            return candidate
        counter += 1


def _quantity_state_payload(
        rows, facts, group_titles=None, catalog=None, worksheet_name="",
        visible_columns=None, settings=None):
    group_titles = dict(group_titles or {})
    fact_by_id = dict((fact.object_id, fact) for fact in facts)
    payload_rows = []
    for row in rows:
        parent_ids = set()
        for object_id in row.object_ids:
            fact = fact_by_id.get(object_id)
            if fact is not None:
                parent_ids.update(fact.parent_ids)
        payload_rows.append({
            "class_name": row.source_key.class_name,
            "layer_name": row.source_key.layer_name,
            "element_kind": row.source_key.element_kind,
            "element_name": row.source_key.element_name,
            "group_id": row.group_id,
            "object_ids": list(row.object_ids),
            "parent_ids": sorted(parent_ids),
            "net_area_m2": row.net_area_m2,
            "net_length_m": row.net_length_m,
            "net_piece_count": row.net_piece_count,
        })
    # Keep the user's exact capitalization/spelling.  ``group_id`` is a
    # case-folded technical key and must never be used as the display title.
    persisted_titles = dict(
        (group_id, str(title))
        for group_id, title in group_titles.items()
        if group_id in set(row.group_id for row in rows)
    )
    normalized_catalog = normalize_catalog(catalog)
    payload = {
        "version": VERSION,
        "rows": payload_rows,
        "group_titles": persisted_titles,
        "catalog": dict(
            (str(class_name), complete_catalog_record(values))
            for class_name, values in normalized_catalog.items()
            if str(class_name).strip() and
            any(complete_catalog_record(values).values())),
        # Keep the old product-only payload readable by version 1.2.5 and by
        # existing project status files during a rollback.
        "products": dict(
            (str(class_name), complete_catalog_record(values)["product"])
            for class_name, values in normalized_catalog.items()
            if str(class_name).strip() and
            complete_catalog_record(values)["product"]),
        "product_database_schema": PRODUCT_DATABASE_SCHEMA_VERSION,
        "mass_database_schema": MASS_DATABASE_SCHEMA_VERSION,
        "worksheet_name": str(worksheet_name or ""),
        "visible_columns": list(normalize_visible_columns(visible_columns)),
    }
    if settings:
        payload["query"] = _quantity_query_payload(settings)
    return payload


def _source_key_payload(key):
    return {
        "class_name": key.class_name,
        "layer_id": key.layer_id,
        "layer_name": key.layer_name,
        "element_kind": key.element_kind,
        "element_name": key.element_name,
    }


def _source_key_signature(value):
    """Return the stable, user-visible identity of a quantity source row."""

    if isinstance(value, SourceKey):
        return (
            value.class_name, value.layer_name,
            value.element_kind, value.element_name)
    if not isinstance(value, dict):
        return None
    return (
        str(value.get("class_name") or "").strip(),
        str(value.get("layer_name") or "").strip(),
        str(value.get("element_kind") or "geometry").strip().casefold(),
        str(value.get("element_name") or "Geometrie").strip(),
    )


def _quantity_query_payload(settings):
    """Persist the exact analysis configuration for a repeatable update."""

    keys = tuple(sorted(settings.get("keys") or ()))
    assignments = settings.get("group_assignments") or {}
    spacing = settings.get("parallel_spacing_cm") or {}
    return {
        "keys": [_source_key_payload(key) for key in keys],
        "exact": bool(settings.get("exact", True)),
        "group_assignments": [
            {
                "source": _source_key_payload(key),
                "group_id": str(assignments[key]),
            }
            for key in keys if key in assignments
        ],
        "parallel_spacing_cm": [
            {
                "source": _source_key_payload(key),
                "value": float(spacing[key]),
            }
            for key in keys if key in spacing
        ],
        "worksheet": bool(settings.get("worksheet", True)),
        "xlsx": bool(settings.get("xlsx", False)),
        "show_results": bool(settings.get("show_results", False)),
        "show_audit": bool(settings.get("show_audit", True)),
    }


def _previous_quantity_settings(all_facts, previous_payload, parallel_keys=()):
    """Restore the last query against the document's current source keys.

    Vectorworks worksheet recalculation cannot rerun this plug-in's duplicate,
    parallel and grouping analysis.  A real update therefore recollects the
    drawing and maps the saved user-visible source identities to the current
    handles.  The mapping deliberately ignores ``layer_id`` so the update also
    survives a reopened or migrated document with new internal layer handles.
    """

    if not isinstance(previous_payload, dict):
        return None
    query = previous_payload.get("query")
    query = query if isinstance(query, dict) else {}
    saved_keys = query.get("keys") or previous_payload.get("rows") or ()
    signatures = set(
        signature for signature in
        (_source_key_signature(item) for item in saved_keys)
        if signature and all(signature))
    if not signatures:
        return None

    current_keys = tuple(sorted(set(
        fact.source_key for fact in (all_facts or ())
        if _source_key_signature(fact.source_key) in signatures
    )))
    if not current_keys:
        return None
    key_by_signature = dict(
        (_source_key_signature(key), key) for key in current_keys)

    assignments = {}
    saved_assignments = query.get("group_assignments") or ()
    if saved_assignments:
        for item in saved_assignments:
            if not isinstance(item, dict):
                continue
            key = key_by_signature.get(_source_key_signature(item.get("source")))
            group_id = str(item.get("group_id") or "").strip()
            if key is not None and group_id:
                assignments[key] = group_id
    else:
        for item in previous_payload.get("rows") or ():
            key = key_by_signature.get(_source_key_signature(item))
            group_id = str(item.get("group_id") or "").strip()
            if key is not None and group_id:
                assignments[key] = group_id

    saved_spacing = {}
    for item in query.get("parallel_spacing_cm") or ():
        if not isinstance(item, dict):
            continue
        try:
            value = float(item.get("value"))
        except (TypeError, ValueError):
            continue
        if value > 0.01:
            saved_spacing[_source_key_signature(item.get("source"))] = value
    detected = set(parallel_keys or ())
    spacing = dict(
        (key, saved_spacing.get(
            _source_key_signature(key), ui.DEFAULT_PARALLEL_SPACING_CM))
        for key in current_keys if key in detected
    )
    return {
        "keys": current_keys,
        "exact": bool(query.get("exact", True)),
        "group_assignments": assignments,
        "group_titles": dict(previous_payload.get("group_titles") or {}),
        "parallel_spacing_cm": spacing,
        # The fast path updates the persistent Vectorworks table and both
        # databases. It intentionally does not create another XLSX copy or
        # open the modal result chooser.
        "worksheet": True,
        "xlsx": False,
        "show_results": False,
        "show_audit": bool(query.get("show_audit", True)),
        "visible_columns": normalize_visible_columns(
            previous_payload.get("visible_columns")),
    }


def _synchronize_catalog(
        database, previous_payload, worksheet_catalog, class_names,
        document_key, timestamp, legacy_products=None):
    """Migrate legacy values and apply only actual worksheet field edits."""

    previous_payload = (
        previous_payload if isinstance(previous_payload, dict) else {})
    baseline = normalize_catalog(previous_payload.get("catalog") or {})
    if not baseline:
        baseline = normalize_catalog(previous_payload.get("products") or {})

    database.merge_missing(baseline, timestamp, document_key)
    database.merge_missing(
        normalize_catalog(legacy_products or {}), timestamp, document_key)

    edits = {}
    for class_name, partial in normalize_catalog(
            worksheet_catalog or {}).items():
        old = complete_catalog_record(baseline.get(class_name, {}))
        changed = dict(
            (field, value) for field, value in partial.items()
            if value != old.get(field, ""))
        if changed:
            edits[class_name] = changed
    if edits:
        database.apply_catalog_updates(edits, timestamp, document_key)
    return database.catalog_for_classes(class_names)


def _synchronize_products(database, previous_payload, worksheet_products,
                          class_names, document_key, timestamp):
    """Migrate old values and apply only actual edits from the last worksheet."""
    previous_payload = previous_payload if isinstance(previous_payload, dict) else {}
    baseline = dict(
        (str(class_name).strip(), str(product or "").strip())
        for class_name, product in
        (previous_payload.get("products") or {}).items()
        if str(class_name).strip()
    )
    try:
        prior_schema = int(previous_payload.get("product_database_schema", 0))
    except (TypeError, ValueError):
        prior_schema = 0
    database_was_missing = not os.path.isfile(database.path)
    if database_was_missing or prior_schema < PRODUCT_DATABASE_SCHEMA_VERSION:
        database.merge_missing(baseline, timestamp, document_key)

    edits = {}
    if worksheet_products is not None:
        for class_name, product in worksheet_products.items():
            class_name = str(class_name or "").strip()
            product = str(product or "").strip()
            if class_name and product != baseline.get(class_name, ""):
                edits[class_name] = product
    if edits:
        database.apply_updates(edits, timestamp, document_key)
    return database.products_for_classes(class_names)


def _select_quantity_row(row, facts):
    fact_by_id = dict((fact.object_id, fact) for fact in facts)
    parents = set()
    for object_id in row.object_ids:
        fact = fact_by_id.get(object_id)
        if fact is not None:
            parents.update(fact.parent_ids)
    count = vw_adapter.select_object_ids(row.object_ids, sorted(parents))
    if not count:
        vw_adapter.alert(
            "Die Objekte dieser Zeile konnten nicht mehr gefunden werden. "
            "Bitte die Massenermittlung aktualisieren.")
        return
    if _reveal_quantity_source(
            row.source_key, tuple(row.object_ids) + tuple(sorted(parents))):
        vw_adapter.info(
            "Die Quellklasse/-ebene wurde für die Hervorhebung sichtbar "
            "gemacht. Der vorherige Zustand ist über „PD Sichtbarkeit "
            "zurück“ wiederherstellbar.")


def _notify_quantity_completion(message, non_modal=False):
    """Report completion without leaving an invisible blocking alert.

    A Vectorworks worksheet is a separate application window.  A modal
    AlrtDialog opened after the result chooser can land behind that worksheet;
    the worksheet then appears frozen because the hidden alert owns the input
    focus.  Message is non-modal and keeps both worksheet and drawing usable.
    """
    if non_modal:
        vw_adapter.info(message)
    else:
        vw_adapter.alert(message, "PD Massenermittlung abgeschlossen")


def _repeat_result_selection(
        rows, group_titles, on_selected, on_closed=None):
    """Reopen the chooser and finish only after its explicit close action."""
    while True:
        selected_index = ui.result_selection_dialog(
            rows, group_titles, _logo_path())
        if selected_index is None:
            if on_closed is not None:
                on_closed()
            return
        on_selected(selected_index)


def _reveal_quantity_source(source_key, object_ids=()):
    """Reveal result objects and all currently resolvable container classes."""
    before = vw_adapter.capture_visibility()
    try:
        object_classes, object_layers = vw_adapter.object_class_layer_names(
            object_ids)
        classes = set(object_classes)
        layers = set(object_layers)
        classes.add(source_key.class_name)
        layers.add(source_key.layer_name)
        _name_undo_event("PD Mengenergebnis sichtbar machen")
        vw_adapter.apply_visibility_action(
            tuple(classes), tuple(layers),
            "show", True, True)
        # A design-layer object cannot be displayed while a sheet layer is
        # active.  Activating the result layer is part of the same journaled
        # transaction; the snapshot restores the previous sheet/design layer.
        if not vw_adapter.activate_design_layer(source_key.layer_name):
            for layer_name in sorted(object_layers, key=str.casefold):
                if vw_adapter.activate_design_layer(layer_name):
                    break
        vw_adapter.redraw()
        after = vw_adapter.capture_visibility()
        if after == before:
            return False
        _state_store().push_visibility(
            vw_adapter.document_key(), before, vw_adapter.now_timestamp())
        return True
    except Exception:
        try:
            vw_adapter.apply_visibility_snapshot(before)
        except Exception:
            pass
        raise


def run_quantities():
    all_facts, _document_skipped = vw_adapter.collect_object_facts()
    if not all_facts:
        vw_adapter.alert(
            "Im Dokument wurden keine auswertbaren Klassen-/Ebeneneinträge gefunden.",
            "PD Massenermittlung")
        return
    parallel_keys = detect_parallel_source_keys(all_facts)
    store = _state_store()
    document_key = vw_adapter.document_key()
    previous_payload = store.get_last_quantities(document_key) or {}
    if not isinstance(previous_payload.get("query"), dict):
        # Releases up to 1.2.20 stored the exact query in the external mass
        # database but not in the compact status JSON. Import it read-only so
        # the very first 1.2.21 update preserves customized parallel spacing
        # and duplicate/group settings instead of silently using defaults.
        try:
            legacy_query = _mass_database().latest_query(document_key)
        except MassDatabaseError:
            legacy_query = None
        if legacy_query:
            previous_payload = dict(previous_payload)
            previous_payload["query"] = legacy_query
    previous_settings = _previous_quantity_settings(
        all_facts, previous_payload, parallel_keys)
    start_action = ui.quantity_update_choice_dialog(
        previous_payload.get("worksheet_name"), _logo_path(),
        can_update=previous_settings is not None)
    if start_action is None:
        return
    new_analysis = start_action == "new"
    update_existing = start_action == "update"
    if update_existing:
        if previous_settings is None:
            raise ValueError("Keine gültigen Einstellungen für die Aktualisierung vorhanden.")
        settings = previous_settings
    else:
        settings = ui.quantity_dialog(
            all_facts, _logo_path(), parallel_keys=parallel_keys,
            default_visible_columns=previous_payload.get("visible_columns"),
            default_show_audit=(previous_settings or {}).get("show_audit", True),
            new_analysis=new_analysis)
    if settings is None:
        return
    keys = set(settings["keys"])
    try:
        validate_editable_columns(settings.get("visible_columns"))
    except ValueError as error:
        vw_adapter.alert(str(error), "Spalten auswählen")
        return
    facts = tuple(fact for fact in all_facts if fact.source_key in keys)
    selected_has_unsupported = any(
        fact.kind == ObjectKind.UNSUPPORTED for fact in facts)
    selected_parallel_keys = tuple(
        key for key in parallel_keys if key in keys)
    spacing_by_key = settings.get("parallel_spacing_cm") or {}
    policies = dict(
        (key, DuplicatePolicy(
            exact_enabled=bool(settings["exact"]),
            parallel_enabled=key in selected_parallel_keys,
            max_spacing_m=(float(spacing_by_key[key]) / 100.0
                           if key in selected_parallel_keys else 0.0),
            angle_tolerance_deg=0.01,
        ))
        for key in keys
    )
    analysis = analyze_duplicates(facts, policies=policies)
    rows = aggregate_quantities(
        facts, analysis.adjustments, settings["group_assignments"])

    previous_worksheet_name = str(
        "" if new_analysis else previous_payload.get("worksheet_name") or "")
    worksheet_catalog = None
    if previous_worksheet_name:
        try:
            worksheet_catalog = read_catalog_from_worksheet(
                previous_worksheet_name)
        except ValueError as error:
            vw_adapter.alert(str(error), "Zusatzfelder prüfen")
            return

    database = _mass_database()
    timestamp = vw_adapter.now_timestamp()
    try:
        legacy_products = {}
        legacy_database = _product_database()
        if os.path.isfile(legacy_database.path):
            legacy_products = legacy_database.all_products()
        catalog = _synchronize_catalog(
            database, previous_payload, worksheet_catalog,
            set(key.class_name for key in keys),
            document_key, timestamp, legacy_products)
        database_counts = database.counts()
    except (MassDatabaseError, ProductDatabaseError) as error:
        vw_adapter.alert(str(error), "Datenbank Massen prüfen")
        return

    completed = []
    failures = []
    worksheet_name = previous_worksheet_name
    database_worksheet_name = ""
    worksheet = None
    if settings["worksheet"]:
        try:
            show_worksheet_now = not (settings["show_results"] and rows)
            if previous_worksheet_name:
                worksheet = replace_vectorworks_worksheet(
                    previous_worksheet_name,
                    rows, settings["group_titles"], analysis, catalog,
                    show=show_worksheet_now,
                    visible_columns=settings["visible_columns"],
                    show_audit=settings["show_audit"])
            else:
                worksheet = create_vectorworks_worksheet(
                    rows, settings["group_titles"], analysis, catalog,
                    show=show_worksheet_now,
                    visible_columns=settings["visible_columns"],
                    show_audit=settings["show_audit"])
            worksheet_name = worksheet_resource_name(worksheet)
            database_worksheet_name = worksheet_name
            completed.append("Vectorworks-Arbeitsblatt erstellt/aktualisiert")
        except Exception as error:
            failures.append("Arbeitsblatt: " + str(error))
    xlsx_path = ""
    database_xlsx_path = ""
    if settings["xlsx"]:
        try:
            xlsx_path = default_xlsx_path(vw_adapter.document_path())
            if not xlsx_path:
                xlsx_path = vw_adapter.choose_save_path(
                    "XLSX-Massenermittlung speichern",
                    "PD_Massenermittlung.xlsx")
            xlsx_path = _unique_path(xlsx_path)
            if xlsx_path:
                export_xlsx(
                    xlsx_path, rows, settings["group_titles"], analysis,
                    catalog, visible_columns=settings["visible_columns"],
                    show_audit=settings["show_audit"])
                database_xlsx_path = xlsx_path
                completed.append("XLSX: " + xlsx_path)
        except Exception as error:
            failures.append("XLSX: " + str(error))

    database_run_id = ""
    try:
        database_run_id = database.record_run(
            timestamp=timestamp,
            document_key=document_key,
            document_path=vw_adapter.document_path(),
            plugin_version=VERSION,
            query_keys=tuple(sorted(keys)),
            rows=rows,
            facts=facts,
            adjustments=analysis.adjustments,
            group_titles=settings["group_titles"],
            catalog=catalog,
            worksheet_name=database_worksheet_name,
            xlsx_path=database_xlsx_path,
            exact_enabled=bool(settings["exact"]),
            group_assignments=settings["group_assignments"],
            parallel_spacing_cm=settings.get("parallel_spacing_cm") or {},
        )
        database_counts = database.counts()
        completed.append("Externe Datenbank Massen")
    except MassDatabaseError as error:
        failures.append("Externe Datenbank Massen: " + str(error))

    if database_run_id:
        try:
            values_by_object_id = build_object_record_values(
                facts=facts,
                rows=rows,
                adjustments=analysis.adjustments,
                group_titles=settings["group_titles"],
                catalog=catalog,
                timestamp=timestamp,
                plugin_version=VERSION,
                run_id=database_run_id,
                group_assignments=settings["group_assignments"],
            )
            _name_undo_event("PD Datenbank Massen an Objekte")
            link_result = vw_adapter.write_object_records(
                DOCUMENT_DATABASE_NAME,
                DOCUMENT_DATABASE_FIELDS,
                values_by_object_id,
            )
            completed.append(
                "Vectorworks-Datenbank Massen (%d Objekt(e))" %
                int(link_result["linked"]))
            if link_result["missing_ids"]:
                failures.append(
                    "Vectorworks-Datenbank Massen: %d inzwischen nicht mehr "
                    "auffindbare(s) Objekt(e)" %
                    len(link_result["missing_ids"]))
        except Exception as error:
            failures.append(
                "Vectorworks-Datenbank Massen: " + str(error))

    store.set_last_quantities(
        document_key,
        _quantity_state_payload(
            rows, facts, settings["group_titles"], catalog,
            worksheet_name, settings["visible_columns"], settings),
        timestamp)

    if settings["show_results"] and rows:
        def show_created_worksheet():
            if worksheet is None:
                return
            try:
                show_vectorworks_worksheet(worksheet)
            except Exception as error:
                failures.append("Arbeitsblatt öffnen: " + str(error))

        _repeat_result_selection(
            rows,
            settings["group_titles"],
            lambda selected_index: _select_quantity_row(
                rows[selected_index], facts),
            on_closed=show_created_worksheet,
        )

    message = "%d Klassen-/Ebenen-/Elementzeile(n) ausgewertet." % len(rows)
    if update_existing:
        message = (
            "Massentabelle mit den letzten Einstellungen aktualisiert.\n\n" +
            message)
    if completed:
        message += "\n\nErzeugt:\n- " + "\n- ".join(completed)
    if selected_has_unsupported:
        message += ("\n\nNicht mengenwirksame Objekttypen wurden in den "
                    "Prüfhinweisen protokolliert.")
    if failures:
        message += "\n\nNicht vollständig:\n- " + "\n- ".join(failures)
    message += (
        "\n\nDatenbank Massen: %d Abfragelauf/-läufe, %d Objekt(e), "
        "%d Klassenkatalog-Zuordnung(en)." %
        (database_counts["runs"], database_counts["objects"],
         database_counts["catalog"]))
    _notify_quantity_completion(
        message,
        non_modal=(
            bool(settings["show_results"]) or
            "Vectorworks-Arbeitsblatt" in completed),
    )


def run_last_results():
    payload = _state_store().get_last_quantities(vw_adapter.document_key())
    if not payload or not payload.get("rows"):
        vw_adapter.alert(
            "Für dieses Dokument liegt noch keine gespeicherte Massenermittlung vor.")
        return
    # A compact persisted result chooser. Each individual dialog closes before
    # the drawing selection changes, then it is rebuilt for another choice.
    # The explicit Close action exits the loop and leaves the drawing/worksheet
    # fully interactive without a hidden modal owner.
    rows = payload["rows"]
    import types
    display_rows = []
    for item in rows:
        element_kind = item.get("element_kind", "geometry")
        element_name = item.get("element_name", "Geometrie")
        element_prefix = {
            "symbol": "Symbol", "group": "Gruppe",
        }.get(element_kind, "Element")
        key = types.SimpleNamespace(
            class_name=item["class_name"], layer_name=item["layer_name"],
            element_kind=element_kind, element_name=element_name,
            element_label=(
                element_name if element_kind == "geometry"
                else "%s: %s" % (element_prefix, element_name)))
        display_rows.append(types.SimpleNamespace(
            source_key=key, group_id=item.get("group_id"),
            net_area_m2=float(item.get("net_area_m2", 0.0)),
            net_length_m=float(item.get("net_length_m", 0.0)),
            net_piece_count=int(item.get("net_piece_count", 0)),
        ))
    saved_titles = payload.get("group_titles") or {}
    titles = dict(
        (item.get("group_id"),
         saved_titles.get(
             item.get("group_id"),
             item.get("group_id") or "Nicht gruppiert"))
        for item in rows
    )
    def select_saved_result(selected_index):
        item = rows[selected_index]
        count = vw_adapter.select_object_ids(
            item.get("object_ids", ()), item.get("parent_ids", ()))
        if not count:
            vw_adapter.alert(
                "Die gespeicherten Objekte existieren nicht mehr. Bitte die "
                "Massenermittlung neu erzeugen.")
        elif _reveal_quantity_source(
                display_rows[selected_index].source_key,
                tuple(item.get("object_ids", ())) +
                tuple(item.get("parent_ids", ()))):
            vw_adapter.info(
                "Die Quellklasse/-ebene wurde für die Hervorhebung sichtbar "
                "gemacht. Der vorherige Zustand ist über „PD Sichtbarkeit "
                "zurück“ wiederherstellbar.")

    _repeat_result_selection(display_rows, titles, select_saved_result)


def _apply_rename_steps(steps, journal):
    """Apply steps one at a time and journal only verified mutations."""
    for step in steps:
        vw_adapter.rename_classes((step,))
        journal.append(step)


def _rollback_rename(executed_steps):
    """Undo exactly the verified steps, in strict reverse order.

    Deriving the current class from the complete plan is unsafe: when the
    first step of a cyclic rename fails, all original names still exist and
    such a guess can silently rotate the classes.  The execution journal is
    unambiguous and reverse-order undo also frees cyclic destinations in the
    correct sequence.
    """
    for step in reversed(tuple(executed_steps)):
        vw_adapter.rename_classes((RenameStep(
            old_name=step.new_name,
            new_name=step.old_name,
            source_name=step.source_name,
        ),))


def run_rename():
    plan = ui.rename_rule_dialog(_logo_path())
    if plan is None:
        return
    if not ui.rename_preview_dialog(plan, _logo_path()):
        return
    if not plan.catalog_is_current(vw_adapter.class_names()):
        vw_adapter.alert(
            "Der Klassenbestand hat sich seit der Vorschau geändert. "
            "Bitte die Vorschau erneut erzeugen.", "Umbenennung abgebrochen")
        return
    if plan.has_conflicts or not plan.can_apply:
        vw_adapter.alert("Die Vorschau enthält blockierende Konflikte.")
        return
    _name_undo_event("PD Klassennamen mehrfach ändern")
    mapping = dict(
        (proposal.old_name, proposal.new_name)
        for proposal in plan.proposals
        if proposal.status == RenameStatus.READY)
    executed_steps = []
    try:
        _apply_rename_steps(plan.phase_to_temporary, executed_steps)
        _apply_rename_steps(plan.phase_to_final, executed_steps)
        _state_store().remap_class_names(
            vw_adapter.document_key(), mapping, vw_adapter.now_timestamp())
    except Exception:
        try:
            _rollback_rename(executed_steps)
        except Exception as rollback_error:
            raise RuntimeError(
                "Umbenennung fehlgeschlagen; auch die automatische Rücksetzung "
            "war nicht vollständig: %s" % rollback_error)
        raise
    database_warning = ""
    try:
        _mass_database().remap_class_names(
            mapping, vw_adapter.now_timestamp(), vw_adapter.document_key())
        # Preserve the old product-only database as a rollback/migration
        # source if it is still present on this workstation.
        legacy_database = _product_database()
        if os.path.isfile(legacy_database.path):
            legacy_database.remap_class_names(
                mapping, vw_adapter.now_timestamp(), vw_adapter.document_key())
    except (MassDatabaseError, ProductDatabaseError) as error:
        database_warning = (
            "\n\nDie Klassen wurden umbenannt, aber die Datenbank Massen "
            "konnte nicht angepasst werden:\n" + str(error))
    renamed = sum(1 for proposal in plan.proposals
                  if proposal.status == RenameStatus.READY)
    vw_adapter.alert(
        "%d Klasse(n) wurden konfliktfrei umbenannt.%s" %
        (renamed, database_warning),
        "PD Klassennamen")


def main(mode="home"):
    selected_mode = str(mode or "home")
    if selected_mode == "home":
        selected_mode = ui.home_dialog(_logo_path())
        if selected_mode is None:
            return
    actions = {
        "visibility": run_visibility,
        "restore": lambda: run_visibility_restore(False),
        "redo": lambda: run_visibility_restore(True),
        "quantities": run_quantities,
        "results": run_last_results,
        "rename": run_rename,
    }
    action = actions.get(selected_mode)
    if action is None:
        raise ValueError("Unbekannter Startmodus: " + selected_mode)
    action()


def guarded_main(mode="home"):
    try:
        main(mode)
    except Exception as error:
        details = traceback.format_exc()
        log_path = ""
        try:
            log_path = _data_path("PD_Massenermittlung_Fehler.log")
            with open(log_path, "a", encoding="utf-8") as stream:
                stream.write(details + "\n")
        except (OSError, RuntimeError):
            log_path = ""
        print(details)
        message = ("Die Massenermittlung wurde abgebrochen.\n"
                   "Grund: " + str(error) +
                   "\nBitte den Fehlerbericht an den Support weitergeben.")
        if log_path:
            message += "\nFehlerprotokoll: " + log_path
        vw_adapter.alert(message, "PD Massenermittlung")
