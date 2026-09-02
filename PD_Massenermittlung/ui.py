# -*- coding: utf-8 -*-
"""Compact native Vectorworks dialogs for the PD tool suite."""

from __future__ import absolute_import

import os
import math

import vs

from .core_patterns import (
    RenameRule,
    RenameStatus,
    build_rename_plan,
)
from .core_selection import (
    DimensionFilter,
    SelectionSpec,
    resolve_selection,
    selected_source_keys,
)
from .report_columns import (
    CORE_HEADERS,
    HEADERS,
    normalize_visible_columns,
    validate_editable_columns,
)
from . import vw_adapter
from . import VERSION


INIT_EVENT = 12255
TITLE_STYLE = 213
SECTION_STYLE = 211
MANUFACTURER = "manufactured by Dirk D."


def _dialog_title(title):
    return "%s | v%s | %s" % (str(title), VERSION, MANUFACTURER)


def _selection_status_text(class_names, layer_names):
    class_count = len(tuple(class_names or ()))
    layer_count = len(tuple(layer_names or ()))
    if class_count or layer_count:
        return (
            "Zeichnungsauswahl erkannt: %d Klasse(n), %d Ebene(n). "
            "Die Übernahme ist bereits aktiviert."
            % (class_count, layer_count))
    return (
        "Noch nichts markiert. So geht's: Abbrechen → gewünschte Objekte "
        "mit dem Auswahlwerkzeug markieren (mehrere mit Umschalt) → "
        "Befehl erneut öffnen.")
DEFAULT_PARALLEL_SPACING_CM = 20.0


def _patterns(text):
    value = str(text or "").replace("\r", "\n")
    result = []
    for line in value.split("\n"):
        for part in line.split(";"):
            part = part.strip()
            if part:
                result.append(part)
    return tuple(result)


def _set_logo(dialog, item_id, logo_path):
    if logo_path and os.path.isfile(logo_path):
        try:
            vs.UpdateImageControl3(dialog, item_id, logo_path)
        except Exception:
            pass


def _setup_lb(dialog, item_id, columns, single=False):
    for index, (title, width) in enumerate(columns):
        vs.InsertLBColumn(dialog, item_id, index, title, width)
        vs.SetLBControlType(dialog, item_id, index, 1)
        vs.SetLBItemDisplayType(dialog, item_id, index, 0)
    vs.EnableLBColumnLines(dialog, item_id, True)
    vs.EnableLBSingleLineSelection(dialog, item_id, bool(single))
    vs.EnableLBSorting(dialog, item_id, False)


def _fill_lb(dialog, item_id, rows):
    vs.EnableLBUpdates(dialog, item_id, False)
    try:
        vs.DeleteAllLBItems(dialog, item_id)
        for row_index, values in enumerate(rows):
            inserted = vs.InsertLBItem(dialog, item_id, row_index,
                                       str(values[0]) if values else "")
            if not isinstance(inserted, int) or inserted < 0:
                inserted = row_index
            for column_index, value in enumerate(values[1:], 1):
                vs.SetLBItemInfo(dialog, item_id, inserted, column_index,
                                 str(value), -1)
    finally:
        vs.EnableLBUpdates(dialog, item_id, True)


def _run_verified_dialog(dialog, handler):
    """Reject malformed native layouts before Vectorworks opens them."""
    if not vs.VerifyLayout(dialog):
        vw_adapter.alert(
            "Der Dialog konnte nicht sicher aufgebaut werden. Bitte die "
            "Installation prüfen oder den Administrator informieren.",
            "PD Dialogfehler",
        )
        return 2
    return vs.RunLayoutDialog(dialog, handler)


def _selected_lb_rows(dialog, item_id, count):
    selected = []
    for index in range(count):
        try:
            if vs.IsLBItemSelected(dialog, item_id, index):
                selected.append(index)
        except Exception:
            break
    return selected


def _choice(dialog, item_id, fallback=0):
    def normalized(value):
        values = value if isinstance(value, (tuple, list)) else (value,)
        for candidate in reversed(values):
            if candidate is None or isinstance(candidate, bool):
                continue
            try:
                index = int(candidate)
            except (TypeError, ValueError):
                continue
            if index >= 0:
                return index
        return None

    try:
        text = str(vs.GetItemText(dialog, item_id) or "")
        if text:
            index = normalized(vs.GetChoiceIndex(dialog, item_id, text))
            if index is not None:
                return index
    except Exception:
        pass
    try:
        index = normalized(vs.GetSelectedChoiceIndex(dialog, item_id, 0))
        return fallback if index is None else index
    except Exception:
        return fallback


def _float(dialog, item_id, fallback=0.0):
    try:
        return float(vs.GetItemText(dialog, item_id).strip().replace(",", "."))
    except Exception:
        return fallback


def choose_names(title, names, logo_path=None, selected_names=()):
    I_OK, _I_CANCEL = 1, 2
    I_TITLE, I_LOGO, I_HINT, I_LIST = 10, 11, 12, 13
    result = {"values": None}
    display_title = title if str(title).startswith("PD ") else "PD " + str(title)
    dialog = vs.CreateResizableLayout(
        _dialog_title(display_title), True, "Übernehmen", "Abbrechen", True, True)
    vs.CreateStyledStatic(
        dialog, I_TITLE, str(title).upper(), -1, TITLE_STYLE)
    try:
        vs.CreateImageControl2(dialog, I_LOGO, 76, 39, "")
    except Exception:
        pass
    vs.CreateStaticText(
        dialog, I_HINT,
        "Mehrfachauswahl mit Strg/Umschalt. Die Auswahl wird exakt übernommen.", 72)
    vs.CreateLB(dialog, I_LIST, 68, 8)
    vs.SetFirstLayoutItem(dialog, I_TITLE)
    try:
        vs.SetRightItem(dialog, I_TITLE, I_LOGO, 16, 0)
    except Exception:
        pass
    vs.SetBelowItem(dialog, I_TITLE, I_HINT, 0, 8)
    vs.SetBelowItem(dialog, I_HINT, I_LIST, 0, 4)
    vs.SetEdgeBinding(dialog, I_LIST, True, True, True, True)

    def handler(item, _data):
        if item == INIT_EVENT:
            _set_logo(dialog, I_LOGO, logo_path)
            _setup_lb(dialog, I_LIST, (("Name", 420),), single=False)
            _fill_lb(dialog, I_LIST, [(name,) for name in names])
            for index, name in enumerate(names):
                if name in selected_names:
                    vs.SetLBSelection(dialog, I_LIST, index, index, True)
        elif item == I_OK:
            indexes = _selected_lb_rows(dialog, I_LIST, len(names))
            if not indexes:
                vw_adapter.alert("Bitte mindestens einen Eintrag markieren.")
                return -1
            result["values"] = tuple(names[index] for index in indexes)
        return item

    response = _run_verified_dialog(dialog, handler)
    return result["values"] if response == I_OK and result["values"] is not None else None


def choose_report_columns(selected_columns=None, logo_path=None):
    """Choose visible quantity columns and their freely configurable order."""

    I_OK, _I_CANCEL = 1, 2
    (I_TITLE, I_LOGO, I_HINT, I_HIDDEN_LABEL, I_HIDDEN,
     I_VISIBLE_LABEL, I_VISIBLE, I_SHOW, I_HIDE, I_UP, I_DOWN,
     I_ALL, I_CORE) = range(10, 23)
    visible = list(normalize_visible_columns(selected_columns))
    result = {"values": None}
    dialog = vs.CreateResizableLayout(
        _dialog_title("PD Massentabelle – Spalten"), True,
        "Übernehmen", "Abbrechen",
        True, True)
    vs.CreateStyledStatic(
        dialog, I_TITLE, "MASSENTABELLE  |  SPALTEN UND REIHENFOLGE", -1,
        TITLE_STYLE)
    try:
        vs.CreateImageControl2(dialog, I_LOGO, 76, 39, "")
    except Exception:
        pass
    vs.CreateStaticText(
        dialog, I_HINT,
        "Spalten ein- oder ausblenden. Die rechte Liste bestimmt von oben "
        "nach unten die Reihenfolge im Vectorworks-Arbeitsblatt und in der "
        "XLSX-Ausgabe.", 88)
    vs.CreateStaticText(dialog, I_HIDDEN_LABEL, "Ausgeblendete Spalten", 38)
    vs.CreateLB(dialog, I_HIDDEN, 32, 8)
    vs.CreateStaticText(
        dialog, I_VISIBLE_LABEL, "Sichtbare Spalten – Reihenfolge", 42)
    vs.CreateLB(dialog, I_VISIBLE, 36, 8)
    vs.CreatePushButton(dialog, I_SHOW, "Anzeigen  >")
    vs.CreatePushButton(dialog, I_HIDE, "<  Ausblenden")
    vs.CreatePushButton(dialog, I_UP, "Nach oben")
    vs.CreatePushButton(dialog, I_DOWN, "Nach unten")
    vs.CreatePushButton(dialog, I_ALL, "Alle anzeigen")
    vs.CreatePushButton(dialog, I_CORE, "Nur Kerndaten")

    vs.SetFirstLayoutItem(dialog, I_TITLE)
    try:
        vs.SetRightItem(dialog, I_TITLE, I_LOGO, 16, 0)
    except Exception:
        pass
    vs.SetBelowItem(dialog, I_TITLE, I_HINT, 0, 8)
    vs.SetBelowItem(dialog, I_HINT, I_HIDDEN_LABEL, 0, 6)
    vs.SetRightItem(dialog, I_HIDDEN_LABEL, I_VISIBLE_LABEL, 18, 0)
    vs.SetBelowItem(dialog, I_HIDDEN_LABEL, I_HIDDEN, 0, 3)
    vs.SetBelowItem(dialog, I_VISIBLE_LABEL, I_VISIBLE, 0, 3)
    vs.SetBelowItem(dialog, I_HIDDEN, I_SHOW, 0, 5)
    vs.SetRightItem(dialog, I_SHOW, I_HIDE, 6, 0)
    vs.SetBelowItem(dialog, I_VISIBLE, I_UP, 0, 5)
    vs.SetRightItem(dialog, I_UP, I_DOWN, 6, 0)
    vs.SetBelowItem(dialog, I_SHOW, I_ALL, 0, 6)
    vs.SetRightItem(dialog, I_ALL, I_CORE, 6, 0)

    vs.SetEdgeBinding(dialog, I_HIDDEN, True, False, True, True)
    vs.SetEdgeBinding(dialog, I_VISIBLE, False, True, True, True)
    for item_id in (I_SHOW, I_HIDE, I_ALL, I_CORE):
        vs.SetEdgeBinding(dialog, item_id, True, False, False, True)
    for item_id in (I_UP, I_DOWN):
        vs.SetEdgeBinding(dialog, item_id, False, True, False, True)

    def hidden_columns():
        selected = set(visible)
        return [header for header in HEADERS if header not in selected]

    def select_rows(item_id, indexes, count):
        try:
            if count:
                vs.SetLBSelection(dialog, item_id, 0, count - 1, False)
            for index in indexes:
                vs.SetLBSelection(dialog, item_id, index, index, True)
        except Exception:
            pass

    def refresh(selected_visible=(), selected_hidden=()):
        hidden = hidden_columns()
        _fill_lb(dialog, I_HIDDEN, [(header,) for header in hidden])
        _fill_lb(dialog, I_VISIBLE, [(header,) for header in visible])
        select_rows(I_HIDDEN, selected_hidden, len(hidden))
        select_rows(I_VISIBLE, selected_visible, len(visible))

    def handler(item, _data):
        if item == INIT_EVENT:
            _set_logo(dialog, I_LOGO, logo_path)
            _setup_lb(dialog, I_HIDDEN, (("Spalte", 260),), single=False)
            _setup_lb(dialog, I_VISIBLE, (("Spalte", 300),), single=False)
            refresh()
        elif item == I_SHOW:
            hidden = hidden_columns()
            indexes = _selected_lb_rows(dialog, I_HIDDEN, len(hidden))
            added = [hidden[index] for index in indexes]
            first_new = len(visible)
            visible.extend(added)
            refresh(
                selected_visible=range(first_new, len(visible)))
        elif item == I_HIDE:
            indexes = _selected_lb_rows(dialog, I_VISIBLE, len(visible))
            if len(indexes) >= len(visible):
                vw_adapter.alert(
                    "Bitte mindestens eine sichtbare Spalte behalten.",
                    "Spalten auswählen")
                return -1
            removed = [visible[index] for index in indexes]
            visible[:] = [
                header for index, header in enumerate(visible)
                if index not in set(indexes)]
            hidden = hidden_columns()
            refresh(selected_hidden=[
                hidden.index(header) for header in removed])
        elif item == I_UP:
            indexes = _selected_lb_rows(dialog, I_VISIBLE, len(visible))
            selected_set = set(indexes)
            for index in indexes:
                if index > 0 and index - 1 not in selected_set:
                    visible[index - 1], visible[index] = (
                        visible[index], visible[index - 1])
            refresh(selected_visible=[max(0, index - 1) for index in indexes])
        elif item == I_DOWN:
            indexes = _selected_lb_rows(dialog, I_VISIBLE, len(visible))
            selected_set = set(indexes)
            last = len(visible) - 1
            for index in reversed(indexes):
                if index < last and index + 1 not in selected_set:
                    visible[index + 1], visible[index] = (
                        visible[index], visible[index + 1])
            refresh(selected_visible=[min(last, index + 1) for index in indexes])
        elif item == I_ALL:
            visible[:] = HEADERS
            refresh()
        elif item == I_CORE:
            visible[:] = CORE_HEADERS
            refresh()
        elif item == I_OK:
            values = tuple(visible)
            if not values:
                vw_adapter.alert(
                    "Bitte mindestens eine sichtbare Spalte auswählen.",
                    "Spalten auswählen")
                return -1
            result["values"] = values
            try:
                validate_editable_columns(values)
            except ValueError as error:
                vw_adapter.alert(str(error), "Spalten auswählen")
                result["values"] = None
                return -1
        return item

    response = _run_verified_dialog(dialog, handler)
    if response == I_OK and result["values"] is not None:
        return result["values"]
    return None


def visibility_dialog(logo_path=None):
    I_OK, _I_CANCEL = 1, 2
    (I_TITLE, I_LOGO, I_C_HEAD, I_C_ACTIVE, I_C_IN_L, I_C_IN,
     I_C_EX_L, I_C_EX, I_C_PICK, I_L_HEAD, I_L_ACTIVE, I_L_IN_L,
     I_L_IN, I_L_EX_L, I_L_EX, I_L_PICK, I_SELECT_HEAD,
     I_SELECT_STATUS, I_FROM_SELECTION, I_PREVIEW, I_LIST_HEAD, I_LIST,
     I_REMOVE, I_ACTION_L, I_ACTION, I_HINT) = range(10, 36)
    state = {
        "rows": [],
        "manual_classes": set(),
        "manual_layers": set(),
        "removed_classes": set(),
        "removed_layers": set(),
        "result": None,
    }
    current_classes, current_layers = vw_adapter.selected_class_layer_names()
    occupied_classes, occupied_layers = (
        vw_adapter.occupied_class_layer_names())
    current_classes = tuple(sorted(
        set(current_classes).intersection(occupied_classes), key=str.casefold))
    current_layers = tuple(sorted(
        set(current_layers).intersection(occupied_layers), key=str.casefold))
    dialog = vs.CreateResizableLayout(
        _dialog_title("PD Klassen- und Ebenensichtbarkeit"), True,
        "Sichtbarkeit anwenden", "Abbrechen", True, True)
    vs.CreateStyledStatic(
        dialog, I_TITLE,
        "KLASSEN UND EBENEN  |  Sichtbarkeit mit 3-stufiger Rückkehr",
        -1, TITLE_STYLE)
    try:
        vs.CreateImageControl2(dialog, I_LOGO, 82, 43, "")
    except Exception:
        pass
    vs.CreateStyledStatic(dialog, I_C_HEAD, "KLASSENFILTER", -1, SECTION_STYLE)
    vs.CreateCheckBox(dialog, I_C_ACTIVE, "Klassen verändern")
    vs.CreateStaticText(dialog, I_C_IN_L, "Einschließen (* und ?; mehrere mit ;):", -1)
    vs.CreateEditText(dialog, I_C_IN, "", 38)
    vs.CreateStaticText(dialog, I_C_EX_L, "Ausschließen:", -1)
    vs.CreateEditText(dialog, I_C_EX, "", 38)
    vs.CreatePushButton(dialog, I_C_PICK, "Klassen aus Liste wählen …")
    vs.CreateStyledStatic(dialog, I_L_HEAD, "EBENENFILTER", -1, SECTION_STYLE)
    vs.CreateCheckBox(dialog, I_L_ACTIVE, "Ebenen verändern")
    vs.CreateStaticText(dialog, I_L_IN_L, "Einschließen (* und ?; mehrere mit ;):", -1)
    vs.CreateEditText(dialog, I_L_IN, "", 38)
    vs.CreateStaticText(dialog, I_L_EX_L, "Ausschließen:", -1)
    vs.CreateEditText(dialog, I_L_EX, "", 38)
    vs.CreatePushButton(dialog, I_L_PICK, "Ebenen aus Liste wählen …")
    vs.CreateStyledStatic(
        dialog, I_SELECT_HEAD, "AUSWAHL DIREKT IN DER ZEICHNUNG", -1,
        SECTION_STYLE)
    vs.CreateStaticText(
        dialog, I_SELECT_STATUS,
        _selection_status_text(current_classes, current_layers), 88)
    vs.CreateCheckBox(
        dialog, I_FROM_SELECTION,
        "Auswahl übernehmen: Klassen und Ebenen der markierten Objekte")
    vs.CreatePushButton(dialog, I_PREVIEW, "Trefferliste aktualisieren")
    vs.CreateStyledStatic(dialog, I_LIST_HEAD, "KONTROLLLISTE", -1, SECTION_STYLE)
    # Compact initial height for notebook displays; resizing adds list rows.
    vs.CreateLB(dialog, I_LIST, 76, 4)
    vs.CreatePushButton(dialog, I_REMOVE, "Markierte Einträge aus Kontrollliste entfernen")
    vs.CreateStaticText(dialog, I_ACTION_L, "Aktion:", -1)
    vs.CreatePullDownMenu(dialog, I_ACTION, 48)
    vs.CreateStaticText(
        dialog, I_HINT,
        "Nur belegte Klassen und Ebenen werden berücksichtigt. "
        "* = beliebig viele Zeichen, ? = genau ein Zeichen. Vor jeder Änderung "
        "wird der vollständige Zustand gesichert; bis zu drei Schritte können "
        "zurück- und wiederholt werden.", 88)

    vs.SetFirstLayoutItem(dialog, I_TITLE)
    try:
        vs.SetRightItem(dialog, I_TITLE, I_LOGO, 16, 0)
    except Exception:
        pass
    vs.SetBelowItem(dialog, I_TITLE, I_C_HEAD, 0, 4)
    vs.SetBelowItem(dialog, I_C_HEAD, I_C_ACTIVE, 0, 2)
    vs.SetBelowItem(dialog, I_C_ACTIVE, I_C_IN_L, 0, 2)
    vs.SetBelowItem(dialog, I_C_IN_L, I_C_IN, 0, 1)
    vs.SetBelowItem(dialog, I_C_IN, I_C_EX_L, 0, 2)
    vs.SetBelowItem(dialog, I_C_EX_L, I_C_EX, 0, 1)
    vs.SetBelowItem(dialog, I_C_EX, I_C_PICK, 0, 3)
    vs.SetRightItem(dialog, I_C_HEAD, I_L_HEAD, 38, 0)
    vs.SetBelowItem(dialog, I_L_HEAD, I_L_ACTIVE, 0, 2)
    vs.SetBelowItem(dialog, I_L_ACTIVE, I_L_IN_L, 0, 2)
    vs.SetBelowItem(dialog, I_L_IN_L, I_L_IN, 0, 1)
    vs.SetBelowItem(dialog, I_L_IN, I_L_EX_L, 0, 2)
    vs.SetBelowItem(dialog, I_L_EX_L, I_L_EX, 0, 1)
    vs.SetBelowItem(dialog, I_L_EX, I_L_PICK, 0, 3)
    vs.SetBelowItem(dialog, I_C_PICK, I_SELECT_HEAD, 0, 4)
    vs.SetBelowItem(dialog, I_SELECT_HEAD, I_SELECT_STATUS, 0, 2)
    vs.SetBelowItem(dialog, I_SELECT_STATUS, I_FROM_SELECTION, 0, 2)
    vs.SetBelowItem(dialog, I_FROM_SELECTION, I_PREVIEW, 0, 2)
    vs.SetBelowItem(dialog, I_PREVIEW, I_LIST_HEAD, 0, 4)
    vs.SetBelowItem(dialog, I_LIST_HEAD, I_LIST, 0, 2)
    vs.SetBelowItem(dialog, I_LIST, I_REMOVE, 0, 2)
    vs.SetBelowItem(dialog, I_REMOVE, I_ACTION_L, 0, 4)
    vs.SetRightItem(dialog, I_ACTION_L, I_ACTION, 4, 0)
    vs.SetBelowItem(dialog, I_ACTION_L, I_HINT, 0, 4)

    vs.SetEdgeBinding(dialog, I_LIST, True, True, True, True)
    for item_id in (I_REMOVE, I_ACTION_L, I_ACTION):
        vs.SetEdgeBinding(dialog, item_id, True, False, False, True)
    vs.SetEdgeBinding(dialog, I_HINT, True, True, False, True)

    action_values = ("only", "hide", "show", "toggle")
    action_labels = (
        "Nur Kontrollliste sichtbar",
        "Kontrollliste ausblenden",
        "Kontrollliste einblenden",
        "Sichtbarkeit der Kontrollliste umschalten",
    )

    def refresh():
        affect_classes = bool(vs.GetBooleanItem(dialog, I_C_ACTIVE))
        affect_layers = bool(vs.GetBooleanItem(dialog, I_L_ACTIVE))
        try:
            selected_classes = set()
            selected_layers = set()
            if affect_classes:
                selected_classes.update(
                    DimensionFilter.from_expressions(
                        True, _patterns(vs.GetItemText(dialog, I_C_IN)),
                        _patterns(vs.GetItemText(dialog, I_C_EX)),
                        state["manual_classes"]).resolve(occupied_classes))
            if affect_layers:
                selected_layers.update(
                    DimensionFilter.from_expressions(
                        True, _patterns(vs.GetItemText(dialog, I_L_IN)),
                        _patterns(vs.GetItemText(dialog, I_L_EX)),
                        state["manual_layers"]).resolve(occupied_layers))
            if vs.GetBooleanItem(dialog, I_FROM_SELECTION):
                if affect_classes:
                    selected_classes.update(current_classes)
                if affect_layers:
                    selected_layers.update(current_layers)
            selected_classes.difference_update(state["removed_classes"])
            selected_layers.difference_update(state["removed_layers"])
            state["rows"] = (
                [("Klasse", name) for name in sorted(selected_classes, key=str.casefold)] +
                [("Ebene", name) for name in sorted(selected_layers, key=str.casefold)]
            )
            _fill_lb(dialog, I_LIST,
                     [(kind, name, "wird geändert") for kind, name in state["rows"]])
        except Exception as error:
            vw_adapter.alert(error, "Muster prüfen")

    def handler(item, _data):
        if item == INIT_EVENT:
            _set_logo(dialog, I_LOGO, logo_path)
            _setup_lb(dialog, I_LIST,
                      (("Art", 90), ("Exakter Name", 430), ("Status", 120)),
                      single=False)
            for index, label in enumerate(action_labels):
                vs.AddChoice(dialog, I_ACTION, label, index)
            vs.SetBooleanItem(dialog, I_C_ACTIVE, True)
            vs.SetBooleanItem(dialog, I_L_ACTIVE, False)
            vs.SetBooleanItem(dialog, I_FROM_SELECTION,
                              bool(current_classes or current_layers))
            vs.SetItemText(dialog, I_C_IN, "*" if not current_classes else "")
            vs.SetItemText(dialog, I_L_IN, "")
            refresh()
        elif item == I_C_PICK:
            values = choose_names("Klassen wählen", occupied_classes, logo_path)
            if values is not None:
                if vs.GetItemText(dialog, I_C_IN).strip() == "*":
                    vs.SetItemText(dialog, I_C_IN, "")
                state["manual_classes"].update(values)
                state["removed_classes"].difference_update(values)
                vs.SetBooleanItem(dialog, I_C_ACTIVE, True)
                refresh()
        elif item == I_L_PICK:
            values = choose_names("Ebenen wählen", occupied_layers, logo_path)
            if values is not None:
                if vs.GetItemText(dialog, I_L_IN).strip() == "*":
                    vs.SetItemText(dialog, I_L_IN, "")
                state["manual_layers"].update(values)
                state["removed_layers"].difference_update(values)
                vs.SetBooleanItem(dialog, I_L_ACTIVE, True)
                refresh()
        elif item == I_PREVIEW:
            refresh()
        elif item == I_REMOVE:
            selected = set(_selected_lb_rows(dialog, I_LIST, len(state["rows"])))
            for index in selected:
                kind, name = state["rows"][index]
                target = (state["removed_classes"] if kind == "Klasse"
                          else state["removed_layers"])
                target.add(name)
            state["rows"] = [row for index, row in enumerate(state["rows"])
                             if index not in selected]
            _fill_lb(dialog, I_LIST,
                     [(kind, name, "wird geändert") for kind, name in state["rows"]])
        elif item == I_OK:
            if not (vs.GetBooleanItem(dialog, I_C_ACTIVE) or
                    vs.GetBooleanItem(dialog, I_L_ACTIVE)):
                vw_adapter.alert("Mindestens Klassen oder Ebenen aktivieren.")
                return -1
            classes = tuple(name for kind, name in state["rows"] if kind == "Klasse")
            layers = tuple(name for kind, name in state["rows"] if kind == "Ebene")
            action_index = _choice(dialog, I_ACTION, 0)
            if not ((vs.GetBooleanItem(dialog, I_C_ACTIVE) and classes) or
                    (vs.GetBooleanItem(dialog, I_L_ACTIVE) and layers)):
                vw_adapter.alert(
                    "Die Kontrollliste enthält keine Einträge für die aktive Auswahl.")
                return -1
            if action_values[action_index] == "only":
                if vs.GetBooleanItem(dialog, I_C_ACTIVE) and not classes:
                    vw_adapter.alert("Die Klassen-Kontrollliste ist leer.")
                    return -1
                if vs.GetBooleanItem(dialog, I_L_ACTIVE) and not layers:
                    vw_adapter.alert("Die Ebenen-Kontrollliste ist leer.")
                    return -1
            state["result"] = {
                "classes": classes,
                "layers": layers,
                "affect_classes": bool(vs.GetBooleanItem(dialog, I_C_ACTIVE)),
                "affect_layers": bool(vs.GetBooleanItem(dialog, I_L_ACTIVE)),
                "action": action_values[action_index],
            }
        return item

    response = _run_verified_dialog(dialog, handler)
    return state["result"] if response == I_OK else None


def quantity_update_choice_dialog(worksheet_name, logo_path=None, can_update=True):
    """Explicit new analysis versus changes to the latest existing worksheet."""

    I_OK, _I_CANCEL = 1, 2
    I_TITLE, I_LOGO, I_HINT, I_ACTION_L, I_ACTION, I_NOTE = range(10, 16)
    choices = [("new", "Neue Massenermittlung anlegen")]
    if worksheet_name:
        if can_update:
            choices.append(("update", "Vorhandene Massentabelle jetzt aktualisieren"))
        choices.append(("settings", "Einstellungen prüfen oder Auswahl ändern"))
    actions = tuple(key for key, _label in choices)
    state = {"result": None}
    dialog = vs.CreateLayout(
        _dialog_title("PD Massenermittlung – Start"), True,
        "Weiter", "Abbrechen")
    vs.CreateStyledStatic(
        dialog, I_TITLE, "MASSENERMITTLUNG  |  NEU ODER AKTUALISIEREN", -1,
        TITLE_STYLE)
    try:
        vs.CreateImageControl2(dialog, I_LOGO, 76, 39, "")
    except Exception:
        pass
    vs.CreateStaticText(
        dialog, I_HINT,
        ("Zuletzt verwendete Massentabelle: „%s“." % str(worksheet_name)
         if worksheet_name else "Für dieses Dokument eine neue Massenermittlung anlegen."), 76)
    vs.CreateStaticText(dialog, I_ACTION_L, "Aktion:", -1)
    vs.CreatePullDownMenu(dialog, I_ACTION, 58)
    vs.CreateStaticText(
        dialog, I_NOTE,
        "Neu: separate Massentabelle erstellen; vorhandene Tabellen bleiben erhalten. "
        "Die direkte Aktualisierung liest die Zeichnung vollständig neu ein "
        "und übernimmt die zuletzt gewählten Klassen, Gruppen, Parallelabstände "
        "und sichtbaren Spalten. Produkt, Beschreibung, Abmessung, Farbe und "
        "Hersteller bleiben erhalten.", 76)
    vs.SetFirstLayoutItem(dialog, I_TITLE)
    try:
        vs.SetRightItem(dialog, I_TITLE, I_LOGO, 16, 0)
    except Exception:
        pass
    vs.SetBelowItem(dialog, I_TITLE, I_HINT, 0, 8)
    vs.SetBelowItem(dialog, I_HINT, I_ACTION_L, 0, 7)
    vs.SetRightItem(dialog, I_ACTION_L, I_ACTION, 6, 0)
    vs.SetBelowItem(dialog, I_ACTION_L, I_NOTE, 0, 8)

    def handler(item, _data):
        if item == INIT_EVENT:
            _set_logo(dialog, I_LOGO, logo_path)
            for index, (_key, label) in enumerate(choices):
                vs.AddChoice(dialog, I_ACTION, label, index)
            vs.SelectChoice(dialog, I_ACTION, 0, True)
        elif item == I_OK:
            state["result"] = actions[_choice(dialog, I_ACTION, 0)]
        return item

    response = _run_verified_dialog(dialog, handler)
    return state["result"] if response == I_OK else None


def quantity_dialog(
        all_facts, logo_path=None, parallel_keys=(),
        default_visible_columns=None, default_show_audit=True, new_analysis=False):
    I_OK, _I_CANCEL = 1, 2
    (I_TITLE, I_LOGO, I_FILTER_HEAD, I_C_ACTIVE, I_C_L, I_C, I_C_PICK,
     I_L_ACTIVE, I_L_L, I_L, I_L_PICK, I_SELECT_HEAD, I_SELECT_STATUS,
     I_CURRENT, I_REFRESH, I_LIST_HEAD, I_LIST, I_REMOVE, I_GROUP_HEAD,
     I_GROUP_L, I_GROUP, I_ASSIGN, I_CLEAR,
     I_PAR_HEAD, I_PAR_MODE_L, I_PAR_MODE, I_PAR_VALUE_L, I_PAR_VALUE,
     I_PAR_APPLY, I_OUTPUT_HEAD, I_EXACT, I_WS, I_XLSX, I_RESULTS,
     I_AUDIT, I_COLUMNS, I_COLUMNS_SUMMARY, I_HINT) = range(10, 48)
    I_TABS, I_FILTER_PANE, I_ROWS_PANE, I_OUTPUT_PANE = range(60, 64)
    source_keys = tuple(sorted({fact.source_key for fact in all_facts}))
    occupied_classes = tuple(sorted(
        {key.class_name for key in source_keys}, key=str.casefold))
    occupied_layers = tuple(sorted(
        {key.layer_name for key in source_keys}, key=str.casefold))
    detected_parallel_keys = set(parallel_keys or ())
    current_classes, current_layers = vw_adapter.selected_class_layer_names()
    state = {
        "rows": [],
        "config": {},
        "manual_classes": (),
        "manual_layers": (),
        "removed_keys": set(),
        "visible_columns": normalize_visible_columns(
            default_visible_columns),
        "result": None,
    }
    dialog = vs.CreateResizableLayout(
        _dialog_title("PD Massenermittlung"), True,
        ("Neue Massenermittlung anlegen" if new_analysis
         else "Massentabelle aktualisieren"), "Abbrechen", True, True)
    vs.CreateTabControl(dialog, I_TABS)
    vs.CreateGroupBox(dialog, I_FILTER_PANE, "1  Auswahl / Filter", False)
    vs.CreateGroupBox(dialog, I_ROWS_PANE, "2  Gruppen / Parallelabstände", False)
    vs.CreateGroupBox(dialog, I_OUTPUT_PANE, "3  Ausgabe", False)
    vs.CreateStyledStatic(
        dialog, I_TITLE,
        "MASSENERMITTLUNG  |  Klassen + Ebenen  |  prüfbar und gruppiert",
        -1, TITLE_STYLE)
    try:
        vs.CreateImageControl2(dialog, I_LOGO, 82, 43, "")
    except Exception:
        pass
    vs.CreateStyledStatic(dialog, I_FILTER_HEAD, "AUSWAHL EINGRENZEN", -1, SECTION_STYLE)
    vs.CreateCheckBox(dialog, I_C_ACTIVE, "Klassenmuster aktiv")
    vs.CreateStaticText(dialog, I_C_L, "Klassen (*, ?; mehrere mit ;):", -1)
    vs.CreateEditText(dialog, I_C, "", 64)
    vs.CreatePushButton(dialog, I_C_PICK, "Aus Liste …")
    vs.CreateCheckBox(dialog, I_L_ACTIVE, "Ebenenmuster aktiv")
    vs.CreateStaticText(dialog, I_L_L, "Ebenen (*, ?; mehrere mit ;):", -1)
    vs.CreateEditText(dialog, I_L, "", 64)
    vs.CreatePushButton(dialog, I_L_PICK, "Aus Liste …")
    vs.CreateStyledStatic(
        dialog, I_SELECT_HEAD, "AUSWAHL DIREKT IN DER ZEICHNUNG", -1,
        SECTION_STYLE)
    vs.CreateStaticText(
        dialog, I_SELECT_STATUS,
        _selection_status_text(current_classes, current_layers), 104)
    vs.CreateCheckBox(
        dialog, I_CURRENT,
        "Auswahl übernehmen: auf Klassen und Ebenen der markierten Objekte begrenzen")
    vs.CreatePushButton(dialog, I_REFRESH, "Kontrollliste neu auswerten")
    vs.CreateStyledStatic(dialog, I_LIST_HEAD, "KONTROLLLISTE KLASSE + EBENE", -1, SECTION_STYLE)
    # The list stays visible below all three setting panes, with enough width
    # for its six columns and fourteen rows instead of the previous four.
    vs.CreateLB(dialog, I_LIST, 172, 14)
    vs.CreatePushButton(dialog, I_REMOVE, "Markierte Zeilen entfernen")
    vs.CreateStyledStatic(dialog, I_GROUP_HEAD, "MARKIERTE ZEILEN EINSTELLEN", -1, SECTION_STYLE)
    vs.CreateStaticText(dialog, I_GROUP_L, "Gruppenüberschrift:", -1)
    vs.CreateEditText(dialog, I_GROUP, "", 28)
    vs.CreatePushButton(dialog, I_ASSIGN, "Auf markierte Zeilen anwenden")
    vs.CreatePushButton(dialog, I_CLEAR, "Zuordnung der markierten Zeilen löschen")
    vs.CreateStyledStatic(
        dialog, I_PAR_HEAD, "PARALLELE GEOMETRIE", -1, SECTION_STYLE)
    vs.CreateStaticText(dialog, I_PAR_MODE_L, "Abstandseinstellung:", -1)
    vs.CreatePullDownMenu(dialog, I_PAR_MODE, 48)
    vs.CreateStaticText(
        dialog, I_PAR_VALUE_L, "Einzeln messen ab [cm]:", -1)
    vs.CreateEditText(
        dialog, I_PAR_VALUE, "%g" % DEFAULT_PARALLEL_SPACING_CM, 10)
    vs.CreatePushButton(
        dialog, I_PAR_APPLY, "Auf alle Parallel-Zeilen anwenden")
    vs.CreateStyledStatic(dialog, I_OUTPUT_HEAD, "AUSGABE", -1, SECTION_STYLE)
    vs.CreateCheckBox(dialog, I_EXACT, "Exakte Dubletten nur einmal rechnen")
    vs.CreateCheckBox(dialog, I_WS, "Vectorworks-Arbeitsblatt erzeugen")
    vs.CreateCheckBox(dialog, I_XLSX, "Bearbeitbare XLSX neben der Projektdatei speichern")
    vs.CreateCheckBox(dialog, I_RESULTS, "Ergebnisliste zum Hervorheben öffnen")
    vs.CreateCheckBox(
        dialog, I_AUDIT,
        "Prüfzeilen und Prüfprotokoll in den Ausgaben anzeigen")
    vs.CreatePushButton(dialog, I_COLUMNS, "Spalten auswählen …")
    vs.CreateStaticText(dialog, I_COLUMNS_SUMMARY, "", 56)
    vs.CreateStaticText(
        dialog, I_HINT,
        "Die Kontrollliste bleibt beim Wechsel der Register sichtbar. "
        "Zeilen unten markieren und unter „Gruppen / Parallelabstände“ "
        "einstellen. Nur die angezeigten Zeilen werden ausgewertet.", 150)

    vs.SetFirstLayoutItem(dialog, I_TITLE)
    try:
        vs.SetRightItem(dialog, I_TITLE, I_LOGO, 16, 0)
    except Exception:
        pass
    vs.SetBelowItem(dialog, I_TITLE, I_TABS, 0, 4)
    vs.SetFirstGroupItem(dialog, I_FILTER_PANE, I_FILTER_HEAD)
    vs.SetBelowItem(dialog, I_FILTER_HEAD, I_C_ACTIVE, 0, 2)
    vs.SetRightItem(dialog, I_C_ACTIVE, I_C_L, 16, 0)
    vs.SetRightItem(dialog, I_C_L, I_C, 4, 0)
    vs.SetRightItem(dialog, I_C, I_C_PICK, 6, 0)
    vs.SetBelowItem(dialog, I_C_ACTIVE, I_L_ACTIVE, 0, 3)
    vs.SetRightItem(dialog, I_L_ACTIVE, I_L_L, 16, 0)
    vs.SetRightItem(dialog, I_L_L, I_L, 4, 0)
    vs.SetRightItem(dialog, I_L, I_L_PICK, 6, 0)
    vs.SetBelowItem(dialog, I_L_ACTIVE, I_SELECT_HEAD, 0, 6)
    vs.SetBelowItem(dialog, I_SELECT_HEAD, I_SELECT_STATUS, 0, 2)
    vs.SetBelowItem(dialog, I_SELECT_STATUS, I_CURRENT, 0, 3)
    vs.SetBelowItem(dialog, I_CURRENT, I_REFRESH, 0, 4)
    vs.SetBelowItem(dialog, I_TABS, I_LIST_HEAD, 0, 4)
    vs.SetBelowItem(dialog, I_LIST_HEAD, I_LIST, 0, 2)
    vs.SetBelowItem(dialog, I_LIST, I_REMOVE, 0, 2)
    vs.SetFirstGroupItem(dialog, I_ROWS_PANE, I_GROUP_HEAD)
    vs.SetBelowItem(dialog, I_GROUP_HEAD, I_GROUP_L, 0, 2)
    vs.SetRightItem(dialog, I_GROUP_L, I_GROUP, 4, 0)
    vs.SetBelowItem(dialog, I_GROUP_L, I_ASSIGN, 0, 2)
    vs.SetRightItem(dialog, I_ASSIGN, I_CLEAR, 8, 0)
    vs.SetBelowItem(dialog, I_ASSIGN, I_PAR_HEAD, 0, 4)
    vs.SetBelowItem(dialog, I_PAR_HEAD, I_PAR_MODE_L, 0, 2)
    vs.SetRightItem(dialog, I_PAR_MODE_L, I_PAR_MODE, 6, 0)
    vs.SetBelowItem(dialog, I_PAR_MODE_L, I_PAR_VALUE_L, 0, 2)
    vs.SetRightItem(dialog, I_PAR_VALUE_L, I_PAR_VALUE, 6, 0)
    vs.SetRightItem(dialog, I_PAR_VALUE, I_PAR_APPLY, 8, 0)
    vs.SetFirstGroupItem(dialog, I_OUTPUT_PANE, I_OUTPUT_HEAD)
    vs.SetBelowItem(dialog, I_OUTPUT_HEAD, I_EXACT, 0, 2)
    vs.SetRightItem(dialog, I_EXACT, I_WS, 18, 0)
    vs.SetBelowItem(dialog, I_EXACT, I_XLSX, 0, 3)
    vs.SetRightItem(dialog, I_XLSX, I_RESULTS, 18, 0)
    vs.SetBelowItem(dialog, I_XLSX, I_AUDIT, 0, 3)
    vs.SetBelowItem(dialog, I_AUDIT, I_COLUMNS, 0, 3)
    vs.SetRightItem(dialog, I_COLUMNS, I_COLUMNS_SUMMARY, 8, 0)
    vs.SetBelowItem(dialog, I_COLUMNS, I_HINT, 0, 3)
    for pane in (I_FILTER_PANE, I_ROWS_PANE, I_OUTPUT_PANE):
        vs.CreateTabPane(dialog, I_TABS, pane)

    # Settings remain at the top; the common control list takes the extra room.
    vs.SetEdgeBinding(dialog, I_TABS, True, True, True, False)
    vs.SetEdgeBinding(dialog, I_LIST, True, True, True, True)
    vs.SetEdgeBinding(dialog, I_REMOVE, True, False, False, True)

    def dimension_filter(active_item, text_item, state_key):
        text = vs.GetItemText(dialog, text_item)
        selected = state[state_key]
        # Exact picked names may contain literal '*', '?' or ';'. They are
        # exact only while the field still shows this selection. Editing the
        # field must not leave any hidden includes active.
        exact = bool(selected) and text == "; ".join(selected)
        return DimensionFilter.from_expressions(
            bool(vs.GetBooleanItem(dialog, active_item)),
            () if exact else _patterns(text),
            explicit_includes=selected if exact else ())

    def make_selection():
        class_filter = dimension_filter(I_C_ACTIVE, I_C, "manual_classes")
        layer_filter = dimension_filter(I_L_ACTIVE, I_L, "manual_layers")
        resolved = resolve_selection(
            SelectionSpec(class_filter, layer_filter),
            occupied_classes, occupied_layers)
        keys = list(selected_source_keys(source_keys, resolved))
        if vs.GetBooleanItem(dialog, I_CURRENT):
            if not current_classes and not current_layers:
                return []
            keys = [key for key in keys
                    if (not current_classes or key.class_name in current_classes)
                    and (not current_layers or key.layer_name in current_layers)]
        return [key for key in keys if key not in state["removed_keys"]]

    def display_rows():
        values = []
        for key in state["rows"]:
            config = state["config"].setdefault(
                key, {
                    "group": "",
                    "spacing_cm": DEFAULT_PARALLEL_SPACING_CM,
                })
            values.append((
                key.class_name, key.layer_name, key.element_label,
                config["group"] or "–",
                "Ja" if key in detected_parallel_keys else "Nein",
                ("%g" % float(config["spacing_cm"])
                 if key in detected_parallel_keys else "–"),
            ))
        _fill_lb(dialog, I_LIST, values)

    def display_column_summary():
        selected = state["visible_columns"]
        if len(selected) == len(HEADERS):
            text = "Alle %d Spalten sichtbar" % len(HEADERS)
        else:
            text = "%d von %d Spalten sichtbar" % (
                len(selected), len(HEADERS))
        vs.SetItemText(dialog, I_COLUMNS_SUMMARY, text)

    def refresh():
        try:
            state["rows"] = make_selection()
            display_rows()
            return True
        except Exception as error:
            vw_adapter.alert(error, "Auswahl prüfen")
            return False

    def selected_keys():
        indexes = _selected_lb_rows(dialog, I_LIST, len(state["rows"]))
        return [state["rows"][index] for index in indexes]

    def spacing_value():
        spacing = _float(dialog, I_PAR_VALUE, -1.0)
        if not math.isfinite(spacing) or spacing <= 0.01:
            vw_adapter.alert(
                "Der Mindestabstand muss endlich und größer als 0,01 cm "
                "sein.", "Abstand prüfen")
            return None
        return spacing

    def apply_spacing(require_selection=True):
        spacing = spacing_value()
        if spacing is None:
            return False
        if _choice(dialog, I_PAR_MODE, 0) == 0:
            targets = [
                key for key in state["rows"]
                if key in detected_parallel_keys]
        else:
            targets = [
                key for key in selected_keys()
                if key in detected_parallel_keys]
            if require_selection and not targets:
                vw_adapter.alert(
                    "Bitte mindestens eine Tabellenzeile mit erkannter "
                    "Parallelität markieren.")
                return False
        for key in targets:
            config = state["config"].setdefault(
                key, {"group": "", "spacing_cm": DEFAULT_PARALLEL_SPACING_CM})
            config["spacing_cm"] = spacing
        display_rows()
        return True

    def handler(item, _data):
        if item == INIT_EVENT:
            _set_logo(dialog, I_LOGO, logo_path)
            _setup_lb(dialog, I_LIST, (
                ("Klasse", 190), ("Konstruktionsebene", 170),
                ("Elementtyp", 240),
                ("Gruppe", 160), ("Parallel erkannt", 100),
                ("Einzeln ab [cm]", 105)),
                single=False)
            vs.AddChoice(
                dialog, I_PAR_MODE,
                "Ein gemeinsamer Wert für alle erkannten Zeilen", 0)
            vs.AddChoice(
                dialog, I_PAR_MODE,
                "Unterschiedliche Werte je Klasse und Ebene", 1)
            vs.SetBooleanItem(dialog, I_C_ACTIVE, False)
            vs.SetBooleanItem(dialog, I_L_ACTIVE, False)
            vs.SetBooleanItem(
                dialog, I_CURRENT, bool(current_classes or current_layers))
            vs.EnableItem(
                dialog, I_CURRENT, bool(current_classes or current_layers))
            vs.SetBooleanItem(dialog, I_EXACT, True)
            vs.SetBooleanItem(dialog, I_WS, True)
            vs.SetBooleanItem(dialog, I_XLSX, True)
            vs.SetBooleanItem(dialog, I_RESULTS, True)
            vs.SetBooleanItem(dialog, I_AUDIT, bool(default_show_audit))
            vs.SetItemText(dialog, I_C, "*")
            vs.SetItemText(dialog, I_L, "*")
            vs.SetItemText(
                dialog, I_PAR_VALUE, "%g" % DEFAULT_PARALLEL_SPACING_CM)
            display_column_summary()
            refresh()
        elif item == I_REFRESH:
            refresh()
        elif item == I_C_PICK:
            current_filter = dimension_filter(I_C_ACTIVE, I_C, "manual_classes")
            values = choose_names(
                "Klassen zur Massenermittlung wählen",
                occupied_classes, logo_path,
                current_filter.resolve(occupied_classes) if current_filter.active else ())
            if values is not None:
                state["manual_classes"] = tuple(values)
                vs.SetItemText(dialog, I_C, "; ".join(values))
                state["removed_keys"] = set(
                    key for key in state["removed_keys"]
                    if key.class_name not in set(values))
                vs.SetBooleanItem(dialog, I_C_ACTIVE, True)
                refresh()
        elif item == I_L_PICK:
            current_filter = dimension_filter(I_L_ACTIVE, I_L, "manual_layers")
            values = choose_names(
                "Ebenen zur Massenermittlung wählen",
                occupied_layers, logo_path,
                current_filter.resolve(occupied_layers) if current_filter.active else ())
            if values is not None:
                state["manual_layers"] = tuple(values)
                vs.SetItemText(dialog, I_L, "; ".join(values))
                state["removed_keys"] = set(
                    key for key in state["removed_keys"]
                    if key.layer_name not in set(values))
                vs.SetBooleanItem(dialog, I_L_ACTIVE, True)
                refresh()
        elif item == I_REMOVE:
            selected = set(_selected_lb_rows(dialog, I_LIST, len(state["rows"])))
            state["removed_keys"].update(
                state["rows"][index] for index in selected)
            state["rows"] = [key for index, key in enumerate(state["rows"])
                             if index not in selected]
            display_rows()
        elif item == I_ASSIGN:
            keys = selected_keys()
            if not keys:
                vw_adapter.alert("Bitte zuerst eine oder mehrere Tabellenzeilen markieren.")
                return -1
            group = vs.GetItemText(dialog, I_GROUP).strip()
            for key in keys:
                config = state["config"].setdefault(
                    key, {
                        "group": "",
                        "spacing_cm": DEFAULT_PARALLEL_SPACING_CM,
                    })
                config["group"] = group
            display_rows()
        elif item == I_CLEAR:
            keys = selected_keys()
            if not keys:
                vw_adapter.alert("Bitte zuerst Tabellenzeilen markieren.")
                return -1
            for key in keys:
                config = state["config"].setdefault(
                    key, {
                        "group": "",
                        "spacing_cm": DEFAULT_PARALLEL_SPACING_CM,
                    })
                config["group"] = ""
            display_rows()
        elif item == I_PAR_MODE:
            if _choice(dialog, I_PAR_MODE, 0) == 0:
                vs.SetItemText(
                    dialog, I_PAR_APPLY,
                    "Auf alle Parallel-Zeilen anwenden")
            else:
                vs.SetItemText(
                    dialog, I_PAR_APPLY,
                    "Auf markierte Parallel-Zeilen anwenden")
        elif item == I_PAR_APPLY:
            if not apply_spacing(require_selection=True):
                return -1
        elif item == I_COLUMNS:
            values = choose_report_columns(
                state["visible_columns"], logo_path)
            if values is not None:
                state["visible_columns"] = normalize_visible_columns(values)
                display_column_summary()
        elif item == I_OK:
            if not refresh():
                return -1
            if not state["rows"]:
                vw_adapter.alert("Die Kontrollliste ist leer.")
                return -1
            exact = bool(vs.GetBooleanItem(dialog, I_EXACT))
            if (_choice(dialog, I_PAR_MODE, 0) == 0 and
                    not apply_spacing(require_selection=False)):
                return -1
            assignments = {}
            titles = {}
            parallel_spacing_cm = {}
            for key in state["rows"]:
                config = state["config"].setdefault(
                    key, {
                        "group": "",
                        "spacing_cm": DEFAULT_PARALLEL_SPACING_CM,
                    })
                if config["group"]:
                    group_id = config["group"].casefold()
                    assignments[key] = group_id
                    titles[group_id] = config["group"]
                if key in detected_parallel_keys:
                    spacing = float(config["spacing_cm"])
                    if not math.isfinite(spacing) or spacing <= 0.01:
                        vw_adapter.alert(
                            "Für jede erkannte Parallel-Zeile muss ein "
                            "Mindestabstand größer als 0,01 cm eingetragen "
                            "sein.", "Abstand prüfen")
                        return -1
                    parallel_spacing_cm[key] = spacing
            state["result"] = {
                "keys": tuple(state["rows"]),
                "exact": exact,
                "group_assignments": assignments,
                "group_titles": titles,
                "parallel_spacing_cm": parallel_spacing_cm,
                "worksheet": bool(vs.GetBooleanItem(dialog, I_WS)),
                "xlsx": bool(vs.GetBooleanItem(dialog, I_XLSX)),
                "show_results": bool(vs.GetBooleanItem(dialog, I_RESULTS)),
                "show_audit": bool(vs.GetBooleanItem(dialog, I_AUDIT)),
                "visible_columns": state["visible_columns"],
            }
        return item

    response = _run_verified_dialog(dialog, handler)
    return state["result"] if response == I_OK else None


def rename_rule_dialog(logo_path=None):
    I_OK, _I_CANCEL = 1, 2
    (I_TITLE, I_LOGO, I_HEAD, I_SOURCE_L, I_SOURCE, I_TARGET_L,
     I_TARGET, I_CASE, I_SELECT_HEAD, I_SELECT_STATUS, I_CURRENT,
     I_HINT) = range(10, 22)
    current_classes, _current_layers = vw_adapter.selected_class_layer_names()
    occupied_classes, _occupied_layers = (
        vw_adapter.occupied_class_layer_names())
    state = {"result": None}
    dialog = vs.CreateLayout(
        _dialog_title("PD Klassennamen mehrfach ändern"), True,
        "Vorschau", "Abbrechen")
    vs.CreateStyledStatic(
        dialog, I_TITLE, "KLASSENNAMEN  |  sichere Serien-Umbenennung", -1,
        TITLE_STYLE)
    try:
        vs.CreateImageControl2(dialog, I_LOGO, 82, 43, "")
    except Exception:
        pass
    vs.CreateStyledStatic(dialog, I_HEAD, "SUCH- UND ERSETZUNGSREGEL", -1, SECTION_STYLE)
    vs.CreateStaticText(dialog, I_SOURCE_L, "Bisheriges Namensmuster:", -1)
    vs.CreateEditText(dialog, I_SOURCE, "", 42)
    vs.CreateStaticText(dialog, I_TARGET_L, "Neues Namensmuster:", -1)
    vs.CreateEditText(dialog, I_TARGET, "", 42)
    vs.CreateCheckBox(dialog, I_CASE, "Groß-/Kleinschreibung beachten")
    vs.CreateStyledStatic(
        dialog, I_SELECT_HEAD, "AUSWAHL DIREKT IN DER ZEICHNUNG", -1,
        SECTION_STYLE)
    vs.CreateStaticText(
        dialog, I_SELECT_STATUS,
        _selection_status_text(current_classes, ()), 76)
    vs.CreateCheckBox(
        dialog, I_CURRENT,
        "Auswahl übernehmen: nur Klassen der markierten Objekte berücksichtigen")
    vs.CreateStaticText(
        dialog, I_HINT,
        "Beispiel: *-EW-*  →  *-Entwässerung-*\n"
        "* bewahrt beliebig viele Zeichen, ? genau ein Zeichen. Alternativ können "
        "Captures mit $1, $2 … gezielt eingesetzt werden. Vor dem Umbenennen "
        "erscheint immer eine vollständige Alt/Neu-Kontrollliste. Vorschau "
        "und Sicherheitsprüfung erfolgen vor jeder Änderung.", 76)
    vs.SetFirstLayoutItem(dialog, I_TITLE)
    try:
        vs.SetRightItem(dialog, I_TITLE, I_LOGO, 16, 0)
    except Exception:
        pass
    vs.SetBelowItem(dialog, I_TITLE, I_HEAD, 0, 8)
    vs.SetBelowItem(dialog, I_HEAD, I_SOURCE_L, 0, 3)
    vs.SetRightItem(dialog, I_SOURCE_L, I_SOURCE, 6, 0)
    vs.SetBelowItem(dialog, I_SOURCE_L, I_TARGET_L, 0, 5)
    vs.SetRightItem(dialog, I_TARGET_L, I_TARGET, 6, 0)
    vs.SetBelowItem(dialog, I_TARGET_L, I_CASE, 0, 6)
    vs.SetBelowItem(dialog, I_CASE, I_SELECT_HEAD, 0, 8)
    vs.SetBelowItem(dialog, I_SELECT_HEAD, I_SELECT_STATUS, 0, 2)
    vs.SetBelowItem(dialog, I_SELECT_STATUS, I_CURRENT, 0, 3)
    vs.SetBelowItem(dialog, I_CURRENT, I_HINT, 0, 7)

    def handler(item, _data):
        if item == INIT_EVENT:
            _set_logo(dialog, I_LOGO, logo_path)
            vs.SetItemText(dialog, I_SOURCE, "*-EW-*")
            vs.SetItemText(dialog, I_TARGET, "*-Entwässerung-*")
            vs.SetBooleanItem(dialog, I_CASE, False)
            vs.SetBooleanItem(dialog, I_CURRENT, bool(current_classes))
            vs.EnableItem(dialog, I_CURRENT, bool(current_classes))
        elif item == I_OK:
            source = vs.GetItemText(dialog, I_SOURCE).strip()
            target = vs.GetItemText(dialog, I_TARGET).strip()
            if not source or not target:
                vw_adapter.alert("Such- und neues Namensmuster dürfen nicht leer sein.")
                return -1
            try:
                rule = RenameRule("Regel 1", source, target,
                                  bool(vs.GetBooleanItem(dialog, I_CASE)))
                selected = (current_classes if vs.GetBooleanItem(dialog, I_CURRENT)
                            else tuple(name for name in occupied_classes
                                       if name.casefold() not in ("none", "keine")))
                plan = build_rename_plan(
                    vw_adapter.class_names(), (rule,), selected_names=selected)
            except Exception as error:
                vw_adapter.alert(error, "Regel prüfen")
                return -1
            matches = [proposal for proposal in plan.proposals
                       if proposal.status != RenameStatus.NO_MATCH]
            if not matches:
                vw_adapter.alert("Die Regel trifft keine der berücksichtigten Klassen.")
                return -1
            state["result"] = plan
        return item

    response = _run_verified_dialog(dialog, handler)
    return state["result"] if response == I_OK else None


def rename_preview_dialog(plan, logo_path=None):
    I_OK, _I_CANCEL = 1, 2
    I_TITLE, I_LOGO, I_HINT, I_LIST, I_STATUS = range(10, 15)
    dialog = vs.CreateResizableLayout(
        _dialog_title("PD Umbenennung prüfen"), True,
        "Klassen umbenennen", "Abbrechen",
        True, True)
    vs.CreateStyledStatic(dialog, I_TITLE, "VORSCHAU  |  Alt → Neu", -1, TITLE_STYLE)
    try:
        vs.CreateImageControl2(dialog, I_LOGO, 76, 39, "")
    except Exception:
        pass
    vs.CreateStaticText(
        dialog, I_HINT,
        "Es werden keine Klassen zusammengeführt. Kollisionen blockieren die "
        "gesamte Änderung, bis die Regel eindeutig ist.", 82)
    vs.CreateLB(dialog, I_LIST, 88, 8)
    vs.CreateStaticText(dialog, I_STATUS, "", -1)
    vs.SetFirstLayoutItem(dialog, I_TITLE)
    try:
        vs.SetRightItem(dialog, I_TITLE, I_LOGO, 16, 0)
    except Exception:
        pass
    vs.SetBelowItem(dialog, I_TITLE, I_HINT, 0, 8)
    vs.SetBelowItem(dialog, I_HINT, I_LIST, 0, 4)
    vs.SetBelowItem(dialog, I_LIST, I_STATUS, 0, 5)
    vs.SetEdgeBinding(dialog, I_LIST, True, True, True, True)
    vs.SetEdgeBinding(dialog, I_STATUS, True, True, False, True)
    labels = {
        RenameStatus.READY: "Bereit",
        RenameStatus.UNCHANGED: "Unverändert",
        RenameStatus.INVALID: "Ungültig",
        RenameStatus.CONFLICT: "Konflikt",
        RenameStatus.NO_MATCH: "Kein Treffer",
    }
    proposals = [proposal for proposal in plan.proposals
                 if proposal.status != RenameStatus.NO_MATCH]

    def handler(item, _data):
        if item == INIT_EVENT:
            _set_logo(dialog, I_LOGO, logo_path)
            _setup_lb(dialog, I_LIST, (
                ("Bisheriger Klassenname", 330),
                ("Neuer Klassenname", 330),
                ("Status", 100), ("Hinweis", 260)), single=True)
            _fill_lb(dialog, I_LIST, [(
                proposal.old_name, proposal.new_name,
                labels.get(proposal.status, str(proposal.status)),
                "; ".join(proposal.messages),
            ) for proposal in proposals])
            ready = sum(1 for proposal in proposals
                        if proposal.status == RenameStatus.READY)
            conflicts = sum(1 for proposal in proposals
                            if proposal.status in (RenameStatus.INVALID,
                                                   RenameStatus.CONFLICT))
            vs.SetItemText(
                dialog, I_STATUS,
                "%d Klasse(n) bereit; %d blockierende Konflikt(e)." %
                (ready, conflicts))
            vs.EnableItem(dialog, I_OK, bool(plan.can_apply))
        return item

    return _run_verified_dialog(dialog, handler) == I_OK


def result_selection_dialog(rows, group_titles, logo_path=None):
    I_OK, _I_CANCEL = 1, 2
    I_TITLE, I_LOGO, I_HINT, I_LIST = range(10, 14)
    state = {"index": None}
    dialog = vs.CreateResizableLayout(
        _dialog_title("PD Mengenergebnis hervorheben"), True,
        "Zeile in Zeichnung markieren", "Schließen", True, True)
    vs.CreateStyledStatic(
        dialog, I_TITLE, "MENGENERGEBNIS  |  Planobjekte markieren", -1,
        TITLE_STYLE)
    try:
        vs.CreateImageControl2(dialog, I_LOGO, 76, 39, "")
    except Exception:
        pass
    vs.CreateStaticText(
        dialog, I_HINT,
        "Eine Zeile wählen und bestätigen. Die zugehörigen Objekte werden "
        "markiert und diese Liste öffnet sich erneut. Erst mit „Schließen“ "
        "wird die Auswahl beendet. Ein neu erzeugtes Arbeitsblatt öffnet sich "
        "erst danach und lässt sich dann frei verschieben.", 86)
    vs.CreateLB(dialog, I_LIST, 84, 8)
    vs.SetFirstLayoutItem(dialog, I_TITLE)
    try:
        vs.SetRightItem(dialog, I_TITLE, I_LOGO, 16, 0)
    except Exception:
        pass
    vs.SetBelowItem(dialog, I_TITLE, I_HINT, 0, 8)
    vs.SetBelowItem(dialog, I_HINT, I_LIST, 0, 4)
    vs.SetEdgeBinding(dialog, I_LIST, True, True, True, True)

    def handler(item, _data):
        if item == INIT_EVENT:
            _set_logo(dialog, I_LOGO, logo_path)
            _setup_lb(dialog, I_LIST, (
                ("Gruppe", 150), ("Klasse", 210), ("Ebene", 170),
                ("Elementtyp", 240),
                ("Fläche netto [m²]", 115), ("Länge netto [m]", 115),
                ("Stück", 70)), single=True)
            _fill_lb(dialog, I_LIST, [(
                group_titles.get(row.group_id, "Nicht gruppiert"),
                row.source_key.class_name, row.source_key.layer_name,
                row.source_key.element_label,
                "%.3f" % row.net_area_m2, "%.3f" % row.net_length_m,
                str(row.net_piece_count),
            ) for row in rows])
        elif item == I_OK:
            selected = _selected_lb_rows(dialog, I_LIST, len(rows))
            if not selected:
                vw_adapter.alert("Bitte eine Ergebniszeile markieren.")
                return -1
            state["index"] = selected[0]
        return item

    response = _run_verified_dialog(dialog, handler)
    return state["index"] if response == I_OK else None


def home_dialog(logo_path=None):
    I_OK, _I_CANCEL = 1, 2
    I_TITLE, I_LOGO, I_HEAD, I_MODE, I_HINT = range(10, 15)
    state = {"mode": None}
    dialog = vs.CreateLayout(
        _dialog_title("PD Klassen- und Mengentools"), True,
        "Werkzeug öffnen", "Abbrechen")
    vs.CreateStyledStatic(
        dialog, I_TITLE, "PD KLASSEN- UND MENGENTOOLS", -1, TITLE_STYLE)
    try:
        vs.CreateImageControl2(dialog, I_LOGO, 90, 47, "")
    except Exception:
        pass
    vs.CreateStyledStatic(dialog, I_HEAD, "WERKZEUG AUSWÄHLEN", -1, SECTION_STYLE)
    vs.CreatePullDownMenu(dialog, I_MODE, 48)
    vs.CreateStaticText(
        dialog, I_HINT,
        "Alle Eingriffe beginnen mit einer Kontrollliste. Sichtbarkeiten können "
        "bis zu drei Schritte zurück- und wiederhergestellt werden; Mengen werden "
        "als Vectorworks-Arbeitsblatt und XLSX ausgegeben.", 76)
    vs.SetFirstLayoutItem(dialog, I_TITLE)
    try:
        vs.SetRightItem(dialog, I_TITLE, I_LOGO, 16, 0)
    except Exception:
        pass
    vs.SetBelowItem(dialog, I_TITLE, I_HEAD, 0, 10)
    vs.SetBelowItem(dialog, I_HEAD, I_MODE, 0, 3)
    vs.SetBelowItem(dialog, I_MODE, I_HINT, 0, 8)
    modes = ("visibility", "quantities", "results", "rename", "restore", "redo")
    labels = (
        "Klassen und Ebenen filtern",
        "Massenermittlung / vorhandene Massentabelle aktualisieren",
        "Letztes Mengenergebnis hervorheben",
        "Zeichenkombinationen in Klassennamen ändern",
        "Letzte Sichtbarkeit wiederherstellen",
        "Wiederhergestellte Sichtbarkeit erneut anwenden",
    )

    def handler(item, _data):
        if item == INIT_EVENT:
            _set_logo(dialog, I_LOGO, logo_path)
            for index, label in enumerate(labels):
                vs.AddChoice(dialog, I_MODE, label, index)
        elif item == I_OK:
            state["mode"] = modes[_choice(dialog, I_MODE, 0)]
        return item

    response = _run_verified_dialog(dialog, handler)
    return state["mode"] if response == I_OK else None
