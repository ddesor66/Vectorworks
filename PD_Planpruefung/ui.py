# -*- coding: utf-8 -*-
"""Small native dialogs for both independent tools."""

from __future__ import absolute_import

import vs

from . import core_filters
from . import vw_bridge
from . import VERSION


INIT_EVENT = 12255
TITLE_STYLE = 213
SECTION_STYLE = 211
MANUFACTURER = "manufactured by Dirk D."


def _dialog_title(title):
    return "%s | v%s | %s" % (str(title), VERSION, MANUFACTURER)


def _selection_status_text(class_names, layer_names):
    """Return the same explicit preselection guidance in every source dialog."""
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
            inserted = vs.InsertLBItem(dialog, item_id, row_index, str(values[0]))
            if not isinstance(inserted, int) or inserted < 0:
                inserted = row_index
            for column_index, value in enumerate(values[1:], 1):
                vs.SetLBItemInfo(dialog, item_id, inserted, column_index,
                                 str(value), -1)
    finally:
        vs.EnableLBUpdates(dialog, item_id, True)


def _selected_rows(dialog, item_id, count):
    result = []
    for index in range(count):
        try:
            if vs.IsLBItemSelected(dialog, item_id, index):
                result.append(index)
        except Exception:
            pass
    return result


def _run(dialog, handler):
    if not vs.VerifyLayout(dialog):
        vw_bridge.alert("Der Dialog konnte nicht sicher aufgebaut werden.")
        return 2
    return vs.RunLayoutDialog(dialog, handler)


def _choose_names(title, names):
    I_OK, I_CANCEL = 1, 2
    I_HINT, I_LIST = 10, 11
    result = {"values": None}
    names = tuple(names)
    display_title = title if str(title).startswith("PD ") else "PD " + str(title)
    dialog = vs.CreateResizableLayout(
        _dialog_title(display_title), True,
        "Übernehmen", "Abbrechen", True, True)
    vs.CreateStaticText(
        dialog, I_HINT, "Mehrfachauswahl mit Strg/Umschalt.", 62)
    vs.CreateLB(dialog, I_LIST, 62, 8)
    vs.SetFirstLayoutItem(dialog, I_HINT)
    vs.SetBelowItem(dialog, I_HINT, I_LIST, 0, 4)
    vs.SetEdgeBinding(dialog, I_LIST, True, True, True, True)

    def handler(item, _data):
        if item == INIT_EVENT:
            _setup_lb(dialog, I_LIST, (("Exakter Name", 440),), False)
            _fill_lb(dialog, I_LIST, [(name,) for name in names])
        elif item == I_OK:
            indexes = _selected_rows(dialog, I_LIST, len(names))
            if not indexes:
                vw_bridge.alert("Bitte mindestens einen Eintrag markieren.")
                return -1
            result["values"] = tuple(names[index] for index in indexes)
        return item

    response = _run(dialog, handler)
    return result["values"] if response == I_OK else None


def label_source_scope(occupied_rows):
    """Filter occupied class/layer pairs before class selection."""
    I_OK, I_CANCEL = 1, 2
    (I_TITLE, I_HINT, I_C_HEAD, I_C_ACTIVE, I_C_IN_L, I_C_IN,
     I_C_EX_L, I_C_EX, I_C_PICK, I_L_HEAD, I_L_ACTIVE, I_L_IN_L,
     I_L_IN, I_L_EX_L, I_L_EX, I_L_PICK, I_SELECT_HEAD,
     I_SELECT_STATUS, I_FROM_SELECTION, I_REFRESH, I_LIST_HEAD,
     I_LIST, I_STATUS) = range(10, 33)
    occupied_rows = tuple(occupied_rows)
    class_catalog = tuple(sorted(
        set(row[0] for row in occupied_rows), key=str.casefold))
    layer_catalog = tuple(sorted(
        set(row[1] for row in occupied_rows), key=str.casefold))
    selected_classes, selected_layers = (
        vw_bridge.selected_class_layer_names())
    selected_classes = frozenset(selected_classes)
    selected_layers = frozenset(selected_layers)
    state = {
        "manual_classes": set(), "manual_layers": set(),
        "rows": (), "result": None,
    }
    dialog = vs.CreateResizableLayout(
        _dialog_title("PD Beschriftung – Quelle eingrenzen"), True,
        "Weiter", "Abbrechen",
        True, True)
    vs.CreateStyledStatic(
        dialog, I_TITLE, "BESCHRIFTUNG  |  Klassen und Ebenen eingrenzen",
        -1, TITLE_STYLE)
    vs.CreateStaticText(
        dialog, I_HINT,
        "Ausgewertet werden nur tatsächlich vorhandene Zeichnungselemente. "
        "* = beliebig viele Zeichen, ? = genau ein Zeichen; mehrere Muster "
        "mit ; trennen.", 92)
    vs.CreateStyledStatic(dialog, I_C_HEAD, "KLASSENFILTER", -1, SECTION_STYLE)
    vs.CreateCheckBox(dialog, I_C_ACTIVE, "Klassen eingrenzen")
    vs.CreateStaticText(dialog, I_C_IN_L, "Einschließen:", -1)
    vs.CreateEditText(dialog, I_C_IN, "*", 40)
    vs.CreateStaticText(dialog, I_C_EX_L, "Ausschließen:", -1)
    vs.CreateEditText(dialog, I_C_EX, "", 40)
    vs.CreatePushButton(dialog, I_C_PICK, "Klassen aus Liste wählen …")
    vs.CreateStyledStatic(dialog, I_L_HEAD, "EBENENFILTER", -1, SECTION_STYLE)
    vs.CreateCheckBox(dialog, I_L_ACTIVE, "Ebenen eingrenzen")
    vs.CreateStaticText(dialog, I_L_IN_L, "Einschließen:", -1)
    vs.CreateEditText(dialog, I_L_IN, "*", 40)
    vs.CreateStaticText(dialog, I_L_EX_L, "Ausschließen:", -1)
    vs.CreateEditText(dialog, I_L_EX, "", 40)
    vs.CreatePushButton(dialog, I_L_PICK, "Ebenen aus Liste wählen …")
    vs.CreateStyledStatic(
        dialog, I_SELECT_HEAD, "AUSWAHL DIREKT IN DER ZEICHNUNG", -1,
        SECTION_STYLE)
    vs.CreateStaticText(
        dialog, I_SELECT_STATUS,
        _selection_status_text(selected_classes, selected_layers), 92)
    vs.CreateCheckBox(
        dialog, I_FROM_SELECTION,
        "Auswahl übernehmen: nur Klassen der markierten Zeichnungselemente")
    vs.CreatePushButton(dialog, I_REFRESH, "Trefferliste aktualisieren")
    vs.CreateStyledStatic(
        dialog, I_LIST_HEAD, "BELEGTE KLASSEN UND EBENEN", -1,
        SECTION_STYLE)
    vs.CreateLB(dialog, I_LIST, 78, 7)
    vs.CreateStaticText(dialog, I_STATUS, "", 92)

    vs.SetFirstLayoutItem(dialog, I_TITLE)
    vs.SetBelowItem(dialog, I_TITLE, I_HINT, 0, 7)
    vs.SetBelowItem(dialog, I_HINT, I_C_HEAD, 0, 8)
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
    vs.SetBelowItem(dialog, I_C_PICK, I_SELECT_HEAD, 0, 8)
    vs.SetBelowItem(dialog, I_SELECT_HEAD, I_SELECT_STATUS, 0, 2)
    vs.SetBelowItem(dialog, I_SELECT_STATUS, I_FROM_SELECTION, 0, 3)
    vs.SetBelowItem(dialog, I_FROM_SELECTION, I_REFRESH, 0, 4)
    vs.SetBelowItem(dialog, I_REFRESH, I_LIST_HEAD, 0, 8)
    vs.SetBelowItem(dialog, I_LIST_HEAD, I_LIST, 0, 2)
    vs.SetBelowItem(dialog, I_LIST, I_STATUS, 0, 3)
    vs.SetEdgeBinding(dialog, I_LIST, True, True, True, True)
    vs.SetEdgeBinding(dialog, I_STATUS, True, True, False, True)

    def enable_filters():
        for item_id in (I_C_IN_L, I_C_IN, I_C_EX_L, I_C_EX, I_C_PICK):
            vs.EnableItem(dialog, item_id,
                          bool(vs.GetBooleanItem(dialog, I_C_ACTIVE)))
        for item_id in (I_L_IN_L, I_L_IN, I_L_EX_L, I_L_EX, I_L_PICK):
            vs.EnableItem(dialog, item_id,
                          bool(vs.GetBooleanItem(dialog, I_L_ACTIVE)))

    def refresh():
        rows = core_filters.filter_occupied_rows(
            occupied_rows,
            class_enabled=bool(vs.GetBooleanItem(dialog, I_C_ACTIVE)),
            class_include=vs.GetItemText(dialog, I_C_IN),
            class_exclude=vs.GetItemText(dialog, I_C_EX),
            manual_classes=state["manual_classes"],
            layer_enabled=bool(vs.GetBooleanItem(dialog, I_L_ACTIVE)),
            layer_include=vs.GetItemText(dialog, I_L_IN),
            layer_exclude=vs.GetItemText(dialog, I_L_EX),
            manual_layers=state["manual_layers"])
        if bool(vs.GetBooleanItem(dialog, I_FROM_SELECTION)):
            rows = tuple(
                row for row in rows if row[0] in selected_classes)
        state["rows"] = rows
        _fill_lb(dialog, I_LIST, rows)
        classes = set(row[0] for row in rows)
        layers = set(row[1] for row in rows)
        count = sum(row[2] for row in rows)
        vs.SetItemText(
            dialog, I_STATUS,
            "%d belegte Klassen, %d Ebenen, %d Zeichnungselemente im Filter."
            % (len(classes), len(layers), count))

    def handler(item, _data):
        if item == INIT_EVENT:
            _setup_lb(dialog, I_LIST,
                      (("Klasse", 310), ("Ebene", 310), ("Elemente", 90)),
                      False)
            vs.SetBooleanItem(dialog, I_C_ACTIVE, False)
            vs.SetBooleanItem(dialog, I_L_ACTIVE, False)
            vs.SetBooleanItem(
                dialog, I_FROM_SELECTION, bool(selected_classes))
            vs.EnableItem(dialog, I_FROM_SELECTION, bool(selected_classes))
            enable_filters()
            refresh()
        elif item in (I_C_ACTIVE, I_L_ACTIVE, I_FROM_SELECTION):
            enable_filters()
            refresh()
        elif item == I_C_PICK:
            values = _choose_names("PD Beschriftung – Klassenfilter", class_catalog)
            if values is not None:
                state["manual_classes"] = set(values)
                vs.SetItemText(dialog, I_C_IN, "")
                vs.SetBooleanItem(dialog, I_C_ACTIVE, True)
                enable_filters()
                refresh()
        elif item == I_L_PICK:
            values = _choose_names("PD Beschriftung – Ebenenfilter", layer_catalog)
            if values is not None:
                state["manual_layers"] = set(values)
                vs.SetItemText(dialog, I_L_IN, "")
                vs.SetBooleanItem(dialog, I_L_ACTIVE, True)
                enable_filters()
                refresh()
        elif item == I_REFRESH:
            refresh()
        elif item == I_OK:
            refresh()
            if not state["rows"]:
                vw_bridge.alert(
                    "Die Eingrenzung enthält keine Zeichnungselemente.")
                return -1
            state["result"] = {
                "classes": tuple(sorted(
                    set(row[0] for row in state["rows"]), key=str.casefold)),
                "layers": tuple(sorted(
                    set(row[1] for row in state["rows"]), key=str.casefold)),
            }
        return item

    response = _run(dialog, handler)
    return state["result"] if response == I_OK else None


def choose_classes(names):
    I_OK, I_CANCEL = 1, 2
    I_TITLE, I_HINT, I_LIST = 10, 11, 12
    result = {"values": None}
    dialog = vs.CreateResizableLayout(
        _dialog_title("PD Beschriftung – Klassen auswählen"), True,
        "Weiter", "Abbrechen",
        True, True)
    vs.CreateStyledStatic(dialog, I_TITLE,
                          "BESCHRIFTUNG  |  Klassen auswählen", -1, TITLE_STYLE)
    vs.CreateStaticText(dialog, I_HINT,
                        "Mehrfachauswahl mit Strg/Umschalt. Angezeigt werden nur Klassen mit Zeichnungselementen.", 78)
    vs.CreateLB(dialog, I_LIST, 70, 8)
    vs.SetFirstLayoutItem(dialog, I_TITLE)
    vs.SetBelowItem(dialog, I_TITLE, I_HINT, 0, 8)
    vs.SetBelowItem(dialog, I_HINT, I_LIST, 0, 4)
    vs.SetEdgeBinding(dialog, I_LIST, True, True, True, True)

    def handler(item, _data):
        if item == INIT_EVENT:
            _setup_lb(dialog, I_LIST, (("Klasse", 470),), False)
            _fill_lb(dialog, I_LIST, [(name,) for name in names])
        elif item == I_OK:
            indexes = _selected_rows(dialog, I_LIST, len(names))
            if not indexes:
                vw_bridge.alert("Bitte mindestens eine Klasse markieren.")
                return -1
            result["values"] = tuple(names[index] for index in indexes)
        return item

    response = _run(dialog, handler)
    return result["values"] if response == I_OK else None


def class_descriptions(classes, initial=None):
    I_OK, I_CANCEL = 1, 2
    I_TITLE, I_HINT, I_LIST, I_EDIT_LABEL, I_EDIT = range(10, 15)
    initial = initial if isinstance(initial, dict) else {}
    values = [str(initial.get(name, name)) for name in classes]
    current = {"row": 0, "result": None}
    dialog = vs.CreateResizableLayout(
        _dialog_title("PD Beschriftung – Texte festlegen"), True,
        "Weiter", "Zurück",
        True, True)
    vs.CreateStyledStatic(dialog, I_TITLE,
                          "BESCHRIFTUNG  |  Kürzel oder Beschreibung", -1,
                          TITLE_STYLE)
    vs.CreateStaticText(dialog, I_HINT,
                        "Eine Tabellenzeile anklicken und den mehrzeiligen Text direkt darunter bearbeiten. Änderungen werden beim Zeilenwechsel und mit „Weiter“ automatisch übernommen. Maximal 30 sichtbare Zeichen.", 82)
    vs.CreateLB(dialog, I_LIST, 76, 7)
    vs.CreateStaticText(dialog, I_EDIT_LABEL,
                        "Text der markierten Klasse (mehrzeilig):", 40)
    vs.CreateEditTextBox(
        dialog, I_EDIT, values[0] if values else "", 52, 4)
    vs.SetFirstLayoutItem(dialog, I_TITLE)
    vs.SetBelowItem(dialog, I_TITLE, I_HINT, 0, 8)
    vs.SetBelowItem(dialog, I_HINT, I_LIST, 0, 4)
    vs.SetBelowItem(dialog, I_LIST, I_EDIT_LABEL, 0, 7)
    vs.SetRightItem(dialog, I_EDIT_LABEL, I_EDIT, 6, 0)
    vs.SetEdgeBinding(dialog, I_LIST, True, True, True, True)
    vs.SetEdgeBinding(dialog, I_EDIT_LABEL, True, False, False, True)
    vs.SetEdgeBinding(dialog, I_EDIT, True, True, False, True)

    def selected_row():
        rows = _selected_rows(dialog, I_LIST, len(classes))
        return rows[0] if rows else current["row"]

    def table_text(value):
        return " ↵ ".join(str(value).splitlines())

    def commit(row=None):
        if row is None:
            row = current["row"]
        text = str(vs.GetItemText(dialog, I_EDIT) or "")
        text = text.replace("\r\n", "\n").replace("\r", "\n").strip()
        if not text:
            vw_bridge.alert("Der Beschriftungstext darf nicht leer sein.")
            return False
        visible_length = len(text.replace("\n", ""))
        if visible_length > 30:
            vw_bridge.alert(
                "Der Beschriftungstext darf höchstens 30 sichtbare Zeichen enthalten. Zeilenumbrüche werden nicht mitgezählt.")
            return False
        values[row] = text
        vs.SetLBItemInfo(dialog, I_LIST, row, 1, table_text(text), -1)
        current["row"] = row
        return True

    def handler(item, _data):
        if item == INIT_EVENT:
            _setup_lb(dialog, I_LIST, (("Klasse", 280), ("Kürzel / Beschreibung", 330)), True)
            _fill_lb(dialog, I_LIST,
                     [(name, table_text(value))
                      for name, value in zip(classes, values)])
        elif item == I_LIST:
            row = selected_row()
            if row != current["row"] and not commit(current["row"]):
                return -1
            current["row"] = row
            vs.SetItemText(dialog, I_EDIT, values[row])
            try:
                vs.SetFocusOnItem(dialog, I_EDIT)
            except Exception:
                pass
        elif item == I_OK:
            if not commit():
                return -1
            current["result"] = dict(zip(classes, values))
        return item

    response = _run(dialog, handler)
    return current["result"] if response == I_OK else None


def label_options(initial=None):
    I_OK, I_CANCEL = 1, 2
    (I_TITLE, I_SIZE_L, I_SIZE, I_MODE_L, I_MODE, I_PAR_L, I_PAR,
     I_LINE_SPACING_L, I_LINE_SPACING, I_BOUNDARY, I_ANGLE_L, I_ANGLE,
     I_CUSTOM_L, I_CUSTOM, I_TEXT_COLOR_L, I_TEXT_COLOR, I_SOLID,
     I_FILL_COLOR_L, I_FILL_COLOR, I_FRAME_L, I_FRAME, I_FRAME_PEN_L,
     I_FRAME_PEN, I_FRAME_FILL_L, I_FRAME_FILL, I_HINT) = range(10, 36)
    defaults = {
        "point_size": 10.0,
        "mode": 0,
        "parallel_cm": 20.0,
        "line_spacing_cm": 250.0,
        "closed_boundaries": False,
        "angle_mode": 0,
        "custom_angle": 0.0,
        "text_color": (0, 0, 0),
        "solid_fill": False,
        "fill_color": (65535, 65535, 65535),
        "frame_shape": 0,
        "frame_pen_color": (0, 0, 0),
        "frame_fill_color": (65535, 65535, 65535),
    }
    editing = isinstance(initial, dict)
    if editing:
        for key in defaults:
            if key in initial:
                defaults[key] = initial[key]

    def choice(key, maximum):
        try:
            return max(0, min(maximum, int(defaults[key])))
        except (TypeError, ValueError):
            return 0

    def rgb(key, fallback):
        try:
            value = tuple(max(0, min(65535, int(component)))
                          for component in defaults[key])
        except (TypeError, ValueError):
            return fallback
        return value if len(value) == 3 else fallback

    def number_text(key):
        try:
            return "%g" % float(defaults[key])
        except (TypeError, ValueError):
            return "0"

    result = {"values": None}
    dialog = vs.CreateLayout(
        _dialog_title("PD Beschriftung – Einstellungen"), True,
        "Aktualisieren" if editing else "Beschriften", "Abbrechen")
    vs.CreateStyledStatic(dialog, I_TITLE,
                          "BESCHRIFTUNG  |  Platzierung", -1, TITLE_STYLE)
    vs.CreateStaticText(dialog, I_SIZE_L, "Schriftgröße im aktuellen Maßstab [pt]:", 42)
    vs.CreateEditText(dialog, I_SIZE, number_text("point_size"), 12)
    vs.CreateStaticText(dialog, I_MODE_L, "Art der Beschriftung:", 30)
    vs.CreatePullDownMenu(dialog, I_MODE, 52)
    vs.CreateStaticText(dialog, I_PAR_L,
                        "Parallele Linien bis Abstand [cm] nur einmal:", 48)
    vs.CreateEditText(dialog, I_PAR, number_text("parallel_cm"), 12)
    vs.CreateStaticText(dialog, I_LINE_SPACING_L,
                        "Beschriftungsabstand auf Linien [cm]:", 48)
    vs.CreateEditText(
        dialog, I_LINE_SPACING, number_text("line_spacing_cm"), 12)
    vs.CreateCheckBox(dialog, I_BOUNDARY,
                      "Umgrenzungslinien geschlossener Flächen zusätzlich beschriften")
    vs.CreateStaticText(dialog, I_ANGLE_L, "Ausrichtung von Linienbeschriftungen:", 42)
    vs.CreatePullDownMenu(dialog, I_ANGLE, 42)
    vs.CreateStaticText(dialog, I_CUSTOM_L, "Eigener Winkel [°]:", 24)
    vs.CreateEditText(dialog, I_CUSTOM, number_text("custom_angle"), 12)
    vs.CreateStaticText(dialog, I_TEXT_COLOR_L, "Schriftfarbe:", 24)
    vs.CreateColorPopup(dialog, I_TEXT_COLOR, 28)
    vs.CreateCheckBox(dialog, I_SOLID,
                      "Solid-Füllung hinter der Beschriftung")
    vs.CreateStaticText(dialog, I_FILL_COLOR_L, "Füllfarbe:", 24)
    vs.CreateColorPopup(dialog, I_FILL_COLOR, 28)
    vs.CreateStaticText(dialog, I_FRAME_L,
                        "Rahmen um die Beschriftung:", 34)
    vs.CreatePullDownMenu(dialog, I_FRAME, 30)
    vs.CreateStaticText(dialog, I_FRAME_PEN_L, "Rahmen-Linienfarbe:", 28)
    vs.CreateColorPopup(dialog, I_FRAME_PEN, 28)
    vs.CreateStaticText(dialog, I_FRAME_FILL_L, "Rahmen-Füllfarbe:", 28)
    vs.CreateColorPopup(dialog, I_FRAME_FILL, 28)
    vs.CreateStaticText(dialog, I_HINT,
                        "Bei Linien liegt je Stützpunktabschnitt eine Beschriftung in dessen Mitte. Ist der vorgegebene Abstand unterschritten, wird die nächste Beschriftung ausgelassen. Der Abstand lässt sich später ändern.", 76)
    vs.SetFirstLayoutItem(dialog, I_TITLE)
    vs.SetBelowItem(dialog, I_TITLE, I_SIZE_L, 0, 9)
    vs.SetRightItem(dialog, I_SIZE_L, I_SIZE, 8, 0)
    vs.SetBelowItem(dialog, I_SIZE_L, I_MODE_L, 0, 6)
    vs.SetRightItem(dialog, I_MODE_L, I_MODE, 8, 0)
    vs.SetBelowItem(dialog, I_MODE_L, I_PAR_L, 0, 6)
    vs.SetRightItem(dialog, I_PAR_L, I_PAR, 8, 0)
    vs.SetBelowItem(dialog, I_PAR_L, I_LINE_SPACING_L, 0, 6)
    vs.SetRightItem(dialog, I_LINE_SPACING_L, I_LINE_SPACING, 8, 0)
    vs.SetBelowItem(dialog, I_LINE_SPACING_L, I_BOUNDARY, 0, 6)
    vs.SetBelowItem(dialog, I_BOUNDARY, I_ANGLE_L, 0, 6)
    vs.SetRightItem(dialog, I_ANGLE_L, I_ANGLE, 8, 0)
    vs.SetBelowItem(dialog, I_ANGLE_L, I_CUSTOM_L, 0, 6)
    vs.SetRightItem(dialog, I_CUSTOM_L, I_CUSTOM, 8, 0)
    vs.SetBelowItem(dialog, I_CUSTOM_L, I_TEXT_COLOR_L, 0, 6)
    vs.SetRightItem(dialog, I_TEXT_COLOR_L, I_TEXT_COLOR, 8, 0)
    vs.SetBelowItem(dialog, I_TEXT_COLOR_L, I_SOLID, 0, 6)
    vs.SetBelowItem(dialog, I_SOLID, I_FILL_COLOR_L, 0, 6)
    vs.SetRightItem(dialog, I_FILL_COLOR_L, I_FILL_COLOR, 8, 0)
    vs.SetBelowItem(dialog, I_FILL_COLOR_L, I_FRAME_L, 0, 8)
    vs.SetRightItem(dialog, I_FRAME_L, I_FRAME, 8, 0)
    vs.SetBelowItem(dialog, I_FRAME_L, I_FRAME_PEN_L, 0, 6)
    vs.SetRightItem(dialog, I_FRAME_PEN_L, I_FRAME_PEN, 8, 0)
    vs.SetBelowItem(dialog, I_FRAME_PEN_L, I_FRAME_FILL_L, 0, 6)
    vs.SetRightItem(dialog, I_FRAME_FILL_L, I_FRAME_FILL, 8, 0)
    vs.SetBelowItem(dialog, I_FRAME_FILL_L, I_HINT, 0, 9)

    def number(item_id, minimum, maximum, label):
        try:
            value = float(str(vs.GetItemText(dialog, item_id)).replace(",", "."))
        except (TypeError, ValueError):
            vw_bridge.alert(label + " ist keine gültige Zahl.")
            return None
        if value < minimum or value > maximum:
            vw_bridge.alert("%s muss zwischen %g und %g liegen." % (label, minimum, maximum))
            return None
        return value

    def handler(item, _data):
        if item == INIT_EVENT:
            for index, label in enumerate((
                    "Im Schwerpunkt / Mittelpunkt",
                    "Auf Linien; Flächen im Schwerpunkt")):
                vs.AddChoice(dialog, I_MODE, label, index)
            for index, label in enumerate((
                    "Mit dem Linienverlauf", "Immer 0°", "Eigener Winkel")):
                vs.AddChoice(dialog, I_ANGLE, label, index)
            for index, label in enumerate((
                    "Kein Rahmen", "Kreis", "Rechteck")):
                vs.AddChoice(dialog, I_FRAME, label, index)
            # Vectorworks 2026 exposes SelectChoice for setting the active
            # item.  SetSelectedChoiceIndex exists in neither VectorScript
            # nor the Python API and would leave an error pending after the
            # dialog had otherwise completed.
            mode = choice("mode", 1)
            angle_mode = choice("angle_mode", 2)
            frame_shape = choice("frame_shape", 2)
            solid_fill = bool(defaults["solid_fill"])
            vs.SelectChoice(dialog, I_MODE, mode, True)
            vs.SelectChoice(dialog, I_ANGLE, angle_mode, True)
            vs.SelectChoice(dialog, I_FRAME, frame_shape, True)
            vs.SetBooleanItem(
                dialog, I_BOUNDARY, bool(defaults["closed_boundaries"]))
            vs.SetBooleanItem(dialog, I_SOLID, solid_fill)
            vs.SetColorChoice(
                dialog, I_TEXT_COLOR,
                int(vs.RGBToColorIndex(*rgb(
                    "text_color", (0, 0, 0)))))
            vs.SetColorChoice(
                dialog, I_FILL_COLOR,
                int(vs.RGBToColorIndex(*rgb(
                    "fill_color", (65535, 65535, 65535)))))
            vs.SetColorChoice(
                dialog, I_FRAME_PEN,
                int(vs.RGBToColorIndex(*rgb(
                    "frame_pen_color", (0, 0, 0)))))
            vs.SetColorChoice(
                dialog, I_FRAME_FILL,
                int(vs.RGBToColorIndex(*rgb(
                    "frame_fill_color", (65535, 65535, 65535)))))
            vs.EnableItem(dialog, I_FILL_COLOR_L, solid_fill)
            vs.EnableItem(dialog, I_FILL_COLOR, solid_fill)
            for item_id in (I_FRAME_PEN_L, I_FRAME_PEN,
                            I_FRAME_FILL_L, I_FRAME_FILL):
                vs.EnableItem(dialog, item_id, frame_shape != 0)
        elif item == I_SOLID:
            enabled = bool(vs.GetBooleanItem(dialog, I_SOLID))
            vs.EnableItem(dialog, I_FILL_COLOR_L, enabled)
            vs.EnableItem(dialog, I_FILL_COLOR, enabled)
        elif item == I_FRAME:
            enabled = int(vs.GetSelectedChoiceIndex(
                dialog, I_FRAME, 0)) != 0
            for item_id in (I_FRAME_PEN_L, I_FRAME_PEN,
                            I_FRAME_FILL_L, I_FRAME_FILL):
                vs.EnableItem(dialog, item_id, enabled)
        elif item == I_OK:
            size = number(I_SIZE, 1.0, 144.0, "Schriftgröße")
            spacing = number(I_PAR, 0.0, 100000.0, "Parallelabstand")
            line_spacing = number(
                I_LINE_SPACING, 0.1, 100000.0,
                "Beschriftungsabstand auf Linien")
            custom = number(I_CUSTOM, -3600.0, 3600.0, "Beschriftungswinkel")
            if None in (size, spacing, line_spacing, custom):
                return -1
            text_color = tuple(int(value) for value in vs.ColorIndexToRGB(
                int(vs.GetColorChoice(dialog, I_TEXT_COLOR))))
            fill_color = tuple(int(value) for value in vs.ColorIndexToRGB(
                int(vs.GetColorChoice(dialog, I_FILL_COLOR))))
            frame_pen_color = tuple(
                int(value) for value in vs.ColorIndexToRGB(
                    int(vs.GetColorChoice(dialog, I_FRAME_PEN))))
            frame_fill_color = tuple(
                int(value) for value in vs.ColorIndexToRGB(
                    int(vs.GetColorChoice(dialog, I_FRAME_FILL))))
            result["values"] = {
                "point_size": size,
                "mode": int(vs.GetSelectedChoiceIndex(dialog, I_MODE, 0)),
                "parallel_cm": spacing,
                "line_spacing_cm": line_spacing,
                "closed_boundaries": bool(vs.GetBooleanItem(dialog, I_BOUNDARY)),
                "angle_mode": int(vs.GetSelectedChoiceIndex(dialog, I_ANGLE, 0)),
                "custom_angle": custom,
                "text_color": text_color,
                "solid_fill": bool(vs.GetBooleanItem(dialog, I_SOLID)),
                "fill_color": fill_color,
                "frame_shape": int(vs.GetSelectedChoiceIndex(
                    dialog, I_FRAME, 0)),
                "frame_pen_color": frame_pen_color,
                "frame_fill_color": frame_fill_color,
            }
        return item

    response = _run(dialog, handler)
    return result["values"] if response == I_OK else None


def line_spacing_dialog(current_cm):
    """Ask for a replacement line-label spacing in document-independent cm."""
    I_OK, I_CANCEL = 1, 2
    I_TITLE, I_LABEL, I_VALUE, I_HINT = range(10, 14)
    result = {"value": None}
    dialog = vs.CreateLayout(
        _dialog_title("PD Beschriftung – Abstand ändern"), True,
        "Aktualisieren", "Abbrechen")
    vs.CreateStyledStatic(dialog, I_TITLE,
                          "BESCHRIFTUNG  |  Linienabstand ändern", -1,
                          TITLE_STYLE)
    vs.CreateStaticText(dialog, I_LABEL,
                        "Beschriftungsabstand auf Linien [cm]:", 46)
    vs.CreateEditText(dialog, I_VALUE, ("%g" % float(current_cm)), 14)
    vs.CreateStaticText(dialog, I_HINT,
                        "Der zuletzt erzeugte Beschriftungsstapel wird anhand der aktuellen Zeichnung neu aufgebaut. Alle übrigen Einstellungen bleiben erhalten.", 70)
    vs.SetFirstLayoutItem(dialog, I_TITLE)
    vs.SetBelowItem(dialog, I_TITLE, I_LABEL, 0, 9)
    vs.SetRightItem(dialog, I_LABEL, I_VALUE, 8, 0)
    vs.SetBelowItem(dialog, I_LABEL, I_HINT, 0, 9)

    def handler(item, _data):
        if item == I_OK:
            try:
                value = float(str(vs.GetItemText(
                    dialog, I_VALUE)).replace(",", "."))
            except (TypeError, ValueError):
                vw_bridge.alert("Der Beschriftungsabstand ist keine gültige Zahl.")
                return -1
            if value < 0.1 or value > 100000.0:
                vw_bridge.alert(
                    "Der Beschriftungsabstand muss zwischen 0,1 und 100000 cm liegen.")
                return -1
            result["value"] = value
        return item

    response = _run(dialog, handler)
    return result["value"] if response == I_OK else None
