# -*- coding: utf-8 -*-
"""Vectorworks 2026: Zeichenfolgen in allen Klassennamen ersetzen."""

from __future__ import print_function

import re
import uuid

try:
    import vs
except ImportError:  # Erlaubt reine Logiktests ausserhalb von Vectorworks.
    vs = None


PLUGIN_VERSION = "1.0.6"
MANUFACTURER = "manufactured by Dirk D."
SETUP_EVENT = 12255
DIALOG_OK = 1
DEFAULT_SEARCH = "-EW-"
DEFAULT_REPLACEMENT = "-Entwässerung-"
MAX_PREVIEW_ROWS = 1000
TYPE_GROUP = 11
TYPE_SYMBOL_INSTANCE = 15
TYPE_SYMBOL_DEFINITION = 16
NON_DRAWING_OBJECT_TYPES = frozenset((
    0, TYPE_SYMBOL_DEFINITION, 18, 19, 31, 41, 47, 48, 49, 51, 66,
))


def _dialog_title(title):
    return "%s | v%s | %s" % (str(title), PLUGIN_VERSION, MANUFACTURER)


class PlanError(ValueError):
    pass


class RenameTransactionError(RuntimeError):
    def __init__(self, message, rollback_ok):
        RuntimeError.__init__(self, message)
        self.rollback_ok = bool(rollback_ok)


def class_names(api):
    """Return a stable snapshot of all class names in the current document."""
    result = []
    for index in range(1, int(api.ClassNum()) + 1):
        name = api.ClassList(index)
        if name:
            result.append(name)
    return result


def occupied_class_names(api):
    """Return classes assigned to genuinely placed drawing objects.

    The layer object chains are authoritative here. Resource definitions and
    their internal objects are deliberately not traversed: they are not
    placed drawing elements and previously produced misleading class choices.
    Placed groups still contribute both their own and their children's
    classes.
    """
    occupied = set()
    visited = set()

    def marker(handle):
        try:
            return int(handle)
        except (TypeError, ValueError):
            return str(handle)

    def visit(handle):
        if not handle:
            return
        key = marker(handle)
        if key in visited:
            return
        visited.add(key)
        object_type = int(api.GetTypeN(handle) or 0)
        if object_type not in NON_DRAWING_OBJECT_TYPES:
            class_name = str(api.GetClass(handle) or "").strip()
            if class_name:
                occupied.add(class_name)
        if object_type == TYPE_GROUP:
            child = api.FInGroup(handle)
            while child:
                visit(child)
                child = api.NextObj(child)

    layer = api.FLayer()
    seen_layers = set()
    while layer and marker(layer) not in seen_layers:
        seen_layers.add(marker(layer))
        handle = api.FInLayer(layer)
        while handle:
            visit(handle)
            handle = api.NextObj(handle)
        layer = api.NextLayer(layer)
    return sorted(occupied, key=str.casefold)


def selected_class_names(api):
    """Return classes of objects marked before the modal dialog opens."""
    selected = set()
    visited = set()

    def visit(handle):
        if not handle:
            return
        key = str(handle)
        if key in visited:
            return
        visited.add(key)
        class_name = str(api.GetClass(handle) or "").strip()
        if class_name:
            selected.add(class_name)
        if int(api.GetTypeN(handle) or 0) == TYPE_GROUP:
            child = api.FInGroup(handle)
            while child:
                visit(child)
                child = api.NextObj(child)

    api.ForEachObject(visit, "(SEL=TRUE)")
    return sorted(selected, key=str.casefold)


def replace_literal(text, search, replacement, case_sensitive=True):
    """Replace all literal occurrences and return (new_text, occurrence_count)."""
    if not search:
        raise PlanError("Die Suchzeichenfolge darf nicht leer sein.")
    if case_sensitive:
        return text.replace(search, replacement), text.count(search)
    pattern = re.compile(re.escape(search), re.IGNORECASE)
    return pattern.subn(lambda match: replacement, text)


def build_plan(names, search, replacement, case_sensitive=True,
               selected_names=None):
    """Build and validate the complete old/new class-name mapping."""
    if not search:
        raise PlanError("Die Suchzeichenfolge darf nicht leer sein.")

    selected_keys = (None if selected_names is None else
                     set(str(name).casefold() for name in selected_names))
    changes = []
    occurrence_count = 0
    final_names = []
    for old_name in names:
        if selected_keys is not None and old_name.casefold() not in selected_keys:
            new_name, count = old_name, 0
        else:
            new_name, count = replace_literal(
                old_name, search, replacement, case_sensitive
            )
        occurrence_count += count
        final_names.append(new_name)
        if new_name != old_name:
            if not new_name.strip():
                raise PlanError(
                    "Der Klassenname '{0}' würde leer werden.".format(old_name)
                )
            changes.append({"old": old_name, "new": new_name, "count": count})

    by_final_name = {}
    for old_name, final_name in zip(names, final_names):
        key = final_name.casefold()
        by_final_name.setdefault(key, []).append((old_name, final_name))

    collisions = [items for items in by_final_name.values() if len(items) > 1]
    if collisions:
        first = collisions[0]
        sources = "', '".join(item[0] for item in first)
        raise PlanError(
            "Namenskonflikt: Die Klassen '{0}' würden denselben Zielnamen "
            "'{1}' erhalten.".format(sources, first[0][1])
        )

    return {
        "changes": changes,
        "occurrence_count": occurrence_count,
        "final_names": final_names,
    }


def validate_named_object_conflicts(api, original_names, changes):
    """Reject target names already used by a non-class named object/resource."""
    original_keys = {name.casefold() for name in original_names}
    for change in changes:
        target = change["new"]
        if target.casefold() in original_keys:
            continue
        try:
            existing = api.GetObject(target)
        except AttributeError:
            existing = None
        if existing:
            raise PlanError(
                "Der Zielname '{0}' wird bereits von einem anderen benannten "
                "Objekt oder Zubehör verwendet.".format(target)
            )


def _selection_status_text(selected_names):
    count = len(tuple(selected_names or ()))
    if count:
        return (
            "Zeichnungsauswahl erkannt: %d belegte Klasse(n). "
            "Die Übernahme ist bereits aktiviert." % count)
    return (
        "Noch nichts markiert. So geht's: Abbrechen → gewünschte Objekte "
        "mit dem Auswahlwerkzeug markieren (mehrere mit Umschalt) → "
        "Befehl erneut öffnen.")


def input_dialog(api, selected_names=()):
    ids = {
        "search_label": 4,
        "search": 5,
        "replacement_label": 6,
        "replacement": 7,
        "case_sensitive": 8,
        "note": 9,
        "only_selected": 10,
        "selection_title": 11,
        "selection_status": 12,
    }
    dialog = api.CreateLayout(
        _dialog_title("PD Klassennamen – Suchen und ersetzen"), False,
        "Vorschau", "Abbrechen"
    )
    api.CreateStaticText(dialog, ids["search_label"], "Suchen:", 15)
    api.CreateEditText(dialog, ids["search"], DEFAULT_SEARCH, 40)
    api.CreateStaticText(dialog, ids["replacement_label"], "Ersetzen durch:", 15)
    api.CreateEditText(dialog, ids["replacement"], DEFAULT_REPLACEMENT, 40)
    api.CreateCheckBox(
        dialog, ids["case_sensitive"], "Groß-/Kleinschreibung beachten"
    )
    try:
        api.CreateStyledStatic(
            dialog, ids["selection_title"],
            "AUSWAHL DIREKT IN DER ZEICHNUNG", -1, 211)
    except AttributeError:
        api.CreateStaticText(
            dialog, ids["selection_title"],
            "AUSWAHL DIREKT IN DER ZEICHNUNG", 66)
    api.CreateStaticText(
        dialog, ids["selection_status"],
        _selection_status_text(selected_names), 66)
    api.CreateCheckBox(
        dialog, ids["only_selected"],
        "Auswahl übernehmen: nur Klassen der markierten Objekte"
    )
    api.CreateStaticText(
        dialog,
        ids["note"],
        "Die Suche ist wörtlich. Vor jeder Änderung erscheint eine vollständige "
        "Vorschau mit den bisherigen und den neuen Klassennamen.",
        66,
    )

    api.SetFirstLayoutItem(dialog, ids["search_label"])
    api.SetRightItem(dialog, ids["search_label"], ids["search"], 0, 0)
    api.SetBelowItem(dialog, ids["search_label"], ids["replacement_label"], 0, 8)
    api.SetRightItem(dialog, ids["replacement_label"], ids["replacement"], 0, 0)
    api.SetBelowItem(
        dialog, ids["replacement_label"], ids["case_sensitive"], 0, 10
    )
    api.SetBelowItem(
        dialog, ids["case_sensitive"], ids["selection_title"], 0, 10
    )
    api.SetBelowItem(
        dialog, ids["selection_title"], ids["selection_status"], 0, 2)
    api.SetBelowItem(
        dialog, ids["selection_status"], ids["only_selected"], 0, 4)
    api.SetBelowItem(dialog, ids["only_selected"], ids["note"], 0, 10)

    values = {
        "search": DEFAULT_SEARCH,
        "replacement": DEFAULT_REPLACEMENT,
        "case_sensitive": True,
        "only_selected": bool(selected_names),
    }

    def handler(item, data):
        del data
        if item == SETUP_EVENT:
            api.SetBooleanItem(dialog, ids["case_sensitive"], True)
            api.SetBooleanItem(
                dialog, ids["only_selected"], bool(selected_names))
            try:
                api.EnableItem(
                    dialog, ids["only_selected"], bool(selected_names))
            except AttributeError:
                pass
        elif item == DIALOG_OK:
            values["search"] = api.GetItemText(dialog, ids["search"])
            values["replacement"] = api.GetItemText(dialog, ids["replacement"])
            values["case_sensitive"] = bool(
                api.GetBooleanItem(dialog, ids["case_sensitive"])
            )
            values["only_selected"] = bool(
                api.GetBooleanItem(dialog, ids["only_selected"])
            )

    if api.RunLayoutDialog(dialog, handler) != DIALOG_OK:
        return None
    return values


def preview_dialog(api, changes, occurrence_count):
    ids = {"summary": 4, "list": 5, "note": 6}
    dialog = api.CreateResizableLayout(
        _dialog_title("PD Klassennamen – Vorschau"), False,
        "Ersetzen", "Abbrechen",
        True, True
    )
    summary = "{0} Klassen werden geändert; {1} Fundstellen insgesamt.".format(
        len(changes), occurrence_count
    )
    api.CreateStaticText(dialog, ids["summary"], summary, 76)
    api.CreateListBox(dialog, ids["list"], 76, 8)

    shown = changes[:MAX_PREVIEW_ROWS]
    for index, change in enumerate(shown):
        line = "{0}  ->  {1}".format(change["old"], change["new"])
        api.AddChoice(dialog, ids["list"], line, index)

    if len(changes) > len(shown):
        note = "Vorschau gekürzt: {0} weitere Klassen werden ebenfalls geändert.".format(
            len(changes) - len(shown)
        )
    else:
        note = "Erst mit 'Ersetzen' werden die Namen im Dokument geändert."
    api.CreateStaticText(dialog, ids["note"], note, 76)

    api.SetFirstLayoutItem(dialog, ids["summary"])
    api.SetBelowItem(dialog, ids["summary"], ids["list"], 0, 8)
    api.SetBelowItem(dialog, ids["list"], ids["note"], 0, 8)
    api.SetEdgeBinding(dialog, ids["list"], True, True, True, True)
    api.SetEdgeBinding(dialog, ids["note"], True, True, False, True)

    def handler(item, data):
        del item, data

    return api.RunLayoutDialog(dialog, handler) == DIALOG_OK


def _name_exists(api, name):
    return any(existing == name for existing in class_names(api))


def _make_unique_name(api, reserved_keys, token, index, purpose):
    attempt = 0
    while True:
        suffix = "" if attempt == 0 else "_{0}".format(attempt)
        candidate = "__KNE_{0}_{1}_{2:04d}{3}__".format(
            purpose, token, index, suffix
        )
        key = candidate.casefold()
        try:
            named_object = api.GetObject(candidate)
        except AttributeError:
            named_object = None
        if key not in reserved_keys and not named_object and not _name_exists(api, candidate):
            reserved_keys.add(key)
            return candidate
        attempt += 1


def _rename_verified(api, source, target):
    api.RenameClass(source, target)
    names = class_names(api)
    if target not in names or source in names:
        raise RuntimeError(
            "Vectorworks konnte die Klasse '{0}' nicht in '{1}' umbenennen.".format(
                source, target
            )
        )


def _rollback(api, entries, reserved_keys, token):
    errors = []
    staged = []

    for index, entry in enumerate(entries, 1):
        current = entry["current"]
        if current == entry["old"]:
            continue
        rollback_name = _make_unique_name(
            api, reserved_keys, token, index, "ROLLBACK"
        )
        try:
            _rename_verified(api, current, rollback_name)
            entry["current"] = rollback_name
            staged.append(entry)
        except Exception as error:
            errors.append(str(error))

    for entry in staged:
        try:
            _rename_verified(api, entry["current"], entry["old"])
            entry["current"] = entry["old"]
        except Exception as error:
            errors.append(str(error))

    missing = [entry["old"] for entry in entries if not _name_exists(api, entry["old"])]
    if missing:
        errors.append(
            "Nicht wiederhergestellte Klassen: {0}".format(", ".join(missing[:8]))
        )
    return not errors, errors


def rename_classes_transaction(api, changes):
    """Rename classes in two phases and roll back all moved names on failure."""
    token = uuid.uuid4().hex[:10]
    reserved_keys = {name.casefold() for name in class_names(api)}
    reserved_keys.update(change["new"].casefold() for change in changes)
    entries = []

    for index, change in enumerate(changes, 1):
        temporary = _make_unique_name(api, reserved_keys, token, index, "TEMP")
        entries.append(
            {
                "old": change["old"],
                "new": change["new"],
                "temp": temporary,
                "current": change["old"],
            }
        )

    try:
        for entry in entries:
            _rename_verified(api, entry["old"], entry["temp"])
            entry["current"] = entry["temp"]

        for entry in entries:
            _rename_verified(api, entry["temp"], entry["new"])
            entry["current"] = entry["new"]
    except Exception as error:
        rollback_ok, rollback_errors = _rollback(api, entries, reserved_keys, token)
        detail = str(error)
        if rollback_errors:
            detail += "\n\nRollback-Hinweis: " + " | ".join(rollback_errors[:4])
        raise RenameTransactionError(detail, rollback_ok)

    return len(entries)


def main(api):
    occupied_names = occupied_class_names(api)
    if not occupied_names:
        api.AlrtDialog(
            "Das aktive Dokument enthält keine belegten Klassen mit "
            "Zeichnungselementen.")
        return

    occupied_keys = set(name.casefold() for name in occupied_names)
    selected_names = [
        name for name in selected_class_names(api)
        if name.casefold() in occupied_keys]
    settings = input_dialog(api, selected_names)
    if settings is None:
        return

    target_names = occupied_names
    if settings["only_selected"]:
        target_names = selected_names
        if not target_names:
            api.AlrtDialog(
                "Es wurden keine Zeichnungselemente mit belegten Klassen "
                "markiert. Bitte Objekte vor dem Start des Befehls anklicken.")
            return

    names = class_names(api)

    try:
        plan = build_plan(
            names,
            settings["search"],
            settings["replacement"],
            settings["case_sensitive"],
            selected_names=target_names,
        )
        validate_named_object_conflicts(api, names, plan["changes"])
    except PlanError as error:
        api.AlrtDialog("Die Ersetzung kann nicht ausgeführt werden.\n\n" + str(error))
        return

    if not plan["changes"]:
        api.AlrtDialog(
            "Die Zeichenfolge '{0}' wurde in keinem Klassennamen gefunden.".format(
                settings["search"]
            )
        )
        return

    if not preview_dialog(api, plan["changes"], plan["occurrence_count"]):
        return

    try:
        api.NameUndoEvent("Klassennamen suchen und ersetzen")
        changed_count = rename_classes_transaction(api, plan["changes"])
        api.ReDrawAll()
    except RenameTransactionError as error:
        api.ReDrawAll()
        if error.rollback_ok:
            status = "Die ursprünglichen Klassennamen wurden wiederhergestellt."
        else:
            status = (
                "Die automatische Wiederherstellung war nicht vollständig. "
                "Bitte das Dokument nicht speichern und 'Rückgängig' ausführen."
            )
        api.AlrtDialog(
            "Die Ersetzung wurde abgebrochen.\n\n{0}\n\n{1}".format(
                str(error), status
            )
        )
        return

    api.AlrtDialog(
        "Fertig: {0} Klassen wurden geändert; {1} Fundstellen wurden ersetzt.".format(
            changed_count, plan["occurrence_count"]
        )
    )


if vs is not None:
    main(vs)
