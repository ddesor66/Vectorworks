# -*- coding: utf-8 -*-
"""Compact, native Vectorworks dialogs for PD Gefälle-Tool."""

from __future__ import absolute_import

import vs

from . import vw_adapter
from . import point_output
from . import chain_edit
from . import core
from . import settings
from . import label_format
from . import networks
from . import VERSION


INIT_EVENT = 12255
MANUFACTURER = "manufactured by Dirk D."
TITLE_STYLE = 213
SECTION_STYLE = 211
SYMBOL_DEFINITION_TYPE = 16
LIBRARIES_FOLDER = 13


def _title(value):
    return "%s | v%s | %s" % (value, VERSION, MANUFACTURER)


def _run(dialog, handler):
    if not vs.VerifyLayout(dialog):
        vw_adapter.alert("Das Fenster konnte nicht sicher aufgebaut werden.")
        return 2
    return vs.RunLayoutDialog(dialog, handler)


def _choice_index(dialog, item_id):
    index = int(vs.GetSelectedChoiceIndex(dialog, item_id, 0))
    if index < 0:
        raise ValueError("Bitte zuerst einen Eintrag auswählen.")
    return index


def _float(dialog, item_id, label):
    value = str(vs.GetItemText(dialog, item_id) or "").strip().replace(",", ".")
    try:
        return core._number(value, label)
    except ValueError:
        raise ValueError("%s ist keine gültige Zahl." % label)


def _init_symbol_resource(dialog, control, unique_id, selected_name):
    """Bind document and Vectorworks-library symbols to a resource popup."""
    vs.ResList_Init(unique_id, SYMBOL_DEFINITION_TYPE)
    vs.ResList_AddCont1(unique_id, LIBRARIES_FOLDER, "")
    vs.ResList_DlgInit(unique_id, dialog, control)
    if selected_name:
        vs.ResList_SetSel(unique_id, selected_name)


def _selected_symbol(unique_id, enabled, label):
    if not enabled:
        return ""
    if not vs.ResList_IsSelValid(unique_id):
        raise ValueError("Bitte ein gültiges %s auswählen." % label)
    selected = str(vs.ResList_GetSel(unique_id) or "").strip()
    handle = vs.GetObject(selected) if vs.ResList_GetSelIsDoc(unique_id) else None
    if not handle:
        handle = vs.ResList_ImportItemN(unique_id, 2)
    name = str(vs.GetName(handle) or selected).strip() if handle else ""
    if not name or not vs.GetObject(name):
        raise ValueError("Das gewählte %s konnte nicht importiert werden." % label)
    return name


def home_dialog(selection_status):
    I_TITLE, I_HINT, I_ACTION_L, I_ACTION, I_STATUS = range(10, 15)
    actions = (
        "Voreinstellungen",
        "Markierte Linie als neues Gefälle",
        "Neues Gefälle durch Punkte zeichnen",
        "Von vorhandenem Höhenpunkt weiterzeichnen",
        "Höhe eines Punktes ändern",
        "Gefälle eines Segments ändern",
        "Markiertes Gefälle neu zeichnen",
        "Alle Gefälle neu zeichnen",
        "Darstellung / Geländewirkung ändern (Punkt oder Verbindung)",
        "Geländedaten aus markierten Gefällen bereitstellen",
        "Höhenpunkt auf Verbindung einfügen",
        "Kette auswählen und Gefälle ändern",
        "Einzelnen Höhenpunkt setzen",
        "Vorhandene Höhenpunkte mit Linie verbinden",
    )
    action_ids = (7, 0, 1, 2, 3, 4, 5, 6, 8, 9, 10, 11, 12, 13)
    result = {"action": None}
    dialog = vs.CreateResizableLayout(
        _title("PD Gefälle-Tool"), True, "Weiter", "Abbrechen", True, True)
    vs.CreateStyledStatic(dialog, I_TITLE, "GEFÄLLE-TOOL  |  Berechnen und beschriften", -1, TITLE_STYLE)
    vs.CreateStaticText(
        dialog, I_HINT,
        "Vorhandene Linie verwenden: zuerst genau eine Linie, Polylinie oder "
        "ein Polygon markieren und den Befehl erneut öffnen. Ein Gefälle ändern: "
        "zuerst eine Gefälleverbindung oder einen zugehörigen Höhenpunkt markieren. Höhenpunkt einfügen: "
        "danach eine Stelle auf ihrer Verbindung anklicken und die angezeigte Höhe bestätigen. "
        "Kette ändern: Verbindung markieren, anschließend Punkte oder Verbindungen in der Liste auswählen. "
        "Einzelne Höhenpunkte können jederzeit nachträglich verbunden werden.", 74)
    vs.CreateStaticText(dialog, I_ACTION_L, "Aktion:", -1)
    vs.CreatePullDownMenu(dialog, I_ACTION, 48)
    vs.CreateStaticText(dialog, I_STATUS, str(selection_status), 74)
    vs.SetFirstLayoutItem(dialog, I_TITLE)
    vs.SetBelowItem(dialog, I_TITLE, I_HINT, 0, 7)
    vs.SetBelowItem(dialog, I_HINT, I_ACTION_L, 0, 8)
    vs.SetRightItem(dialog, I_ACTION_L, I_ACTION, 8, 0)
    vs.SetBelowItem(dialog, I_ACTION_L, I_STATUS, 0, 7)
    vs.SetEdgeBinding(dialog, I_HINT, True, True, True, False)
    vs.SetEdgeBinding(dialog, I_ACTION, True, False, True, False)
    vs.SetEdgeBinding(dialog, I_STATUS, True, True, True, False)

    def handler(item, _data):
        if item == INIT_EVENT:
            for index, label in enumerate(actions):
                vs.AddChoice(dialog, I_ACTION, label, index)
            vs.SelectChoice(dialog, I_ACTION, 0, True)
        elif item == 1:
            result["action"] = action_ids[_choice_index(dialog, I_ACTION)]
        return item

    return result["action"] if _run(dialog, handler) == 1 else None


def network_dialog(rows, preferred):
    """Choose membership before graphical acquisition; never create here."""
    dialog = vs.CreateResizableLayout(_title("PD Gefälle-Tool – Gefällenetz wählen"), True,
                                      "Weiter", "Abbrechen", True, True)
    vs.CreateStyledStatic(dialog, 10, "GEFÄLLENETZ  |  Vorhandenes Level oder neues Netz", -1, TITLE_STYLE)
    vs.CreateStaticText(dialog, 11, "Es sind bereits Höhenpunkte vorhanden. Zu welchem Gefällenetz sollen "
                        "die weiteren Punkte gehören? Die Punktnummern bleiben über alle Netze hinweg eindeutig.", 76)
    vs.CreateStaticText(dialog, 12, "Gefällenetz / Level:", -1)
    vs.CreatePullDownMenu(dialog, 13, 60)
    vs.CreateStaticText(dialog, 14, "Name des neuen Netzes:", -1)
    vs.CreateEditText(dialog, 15, "", 38)
    vs.CreateStaticText(dialog, 16, "Beispiele: SW-Netz, Wegegefälle, RW-Netz. Jedes Netz verwendet die "
                        "zugehörige GEF-Ebene. Ein neues Netz entsteht erst, wenn Punkte tatsächlich angelegt werden.", 76)
    vs.SetFirstLayoutItem(dialog, 10)
    vs.SetBelowItem(dialog, 10, 11, 0, 5)
    vs.SetBelowItem(dialog, 11, 12, 0, 6)
    vs.SetRightItem(dialog, 12, 13, 6, 0)
    vs.SetBelowItem(dialog, 12, 14, 0, 5)
    vs.SetRightItem(dialog, 14, 15, 6, 0)
    vs.SetBelowItem(dialog, 14, 16, 0, 5)
    result = {"value": None}

    def handler(item, _data):
        if item == INIT_EVENT:
            for index, row in enumerate(rows):
                vs.AddChoice(dialog, 13, "%s  |  Höhenpunkte: %d  |  Gefälle: %d" %
                             (row["name"], row["point_count"], row["chain_count"]), index)
            vs.AddChoice(dialog, 13, "Neues Netz …", len(rows))
            initial = next((i for i, row in enumerate(rows) if networks.key(row["name"]) == networks.key(preferred)), 0)
            vs.SelectChoice(dialog, 13, initial, True)
            vs.EnableItem(dialog, 15, initial == len(rows))
        elif item == 13:
            vs.EnableItem(dialog, 15, _choice_index(dialog, 13) == len(rows))
        elif item == 1:
            try:
                index = _choice_index(dialog, 13)
                result["value"] = (networks.new_name(vs.GetItemText(dialog, 15), rows)
                                   if index == len(rows) else rows[index]["name"])
            except (ValueError, IndexError) as error:
                vw_adapter.alert(error)
                return -1
        return item
    return result["value"] if _run(dialog, handler) == 1 else None


def single_point_dialog(number, level, lock_level=False, default_height=0.0,
                        allow_multiple=True):
    dialog = vs.CreateResizableLayout(_title("PD Gefälle-Tool – Einzelner Höhenpunkt"), True,
                                      "Punkt setzen", "Abbrechen", True, True)
    vs.CreateStyledStatic(dialog, 10, "EINZELNER HÖHENPUNKT  |  P:%d" % number, -1, TITLE_STYLE)
    vs.CreateStaticText(dialog, 11, "Höhe [m]:", -1)
    vs.CreateEditText(dialog, 12, str(default_height).replace(".", ","), 18)
    vs.CreateStaticText(dialog, 13, "Level / Gefällebene:", -1)
    vs.CreateEditText(dialog, 14, str(level), 28)
    vs.CreateCheckBox(dialog, 16, "Mehrere Höhenpunkte nacheinander setzen")
    vs.CreateStaticText(dialog, 15, "Danach die Position in der Zeichnung anklicken. Bei mehreren Punkten "
                        "werden die Nummern fortlaufend erhöht; die letzte Höhe wird jeweils vorgeschlagen. "
                        "Abschluss der Positionsfolge per Doppelklick. Esc bricht die Punkteingabe ab.", 70)
    vs.SetFirstLayoutItem(dialog, 10)
    vs.SetBelowItem(dialog, 10, 11, 0, 5)
    vs.SetRightItem(dialog, 11, 12, 6, 0)
    vs.SetBelowItem(dialog, 11, 13, 0, 5)
    vs.SetRightItem(dialog, 13, 14, 6, 0)
    vs.SetBelowItem(dialog, 13, 16, 0, 5)
    vs.SetBelowItem(dialog, 16, 15, 0, 5)
    result = {"value": None}

    def handler(item, _data):
        if item == INIT_EVENT:
            vs.EnableItem(dialog, 14, not lock_level)
            vs.SetBooleanItem(dialog, 16, False)
            vs.EnableItem(dialog, 16, allow_multiple)
        elif item == 1:
            try:
                height = _float(dialog, 12, "Höhe")
                chosen_level = level if lock_level else str(vs.GetItemText(dialog, 14) or "").strip()
                if not chosen_level:
                    raise core.SlopeError("Bitte ein Level eingeben.")
                result["value"] = dict(
                    height_m=height, level=chosen_level,
                    multiple=allow_multiple and bool(vs.GetBooleanItem(dialog, 16)))
            except ValueError as error:
                vw_adapter.alert(error)
                return -1
        return item
    return result["value"] if _run(dialog, handler) == 1 else None


def connect_points_dialog(points, level):
    dialog = vs.CreateResizableLayout(_title("PD Gefälle-Tool – Höhenpunkte verbinden"), True,
                                      "Verbinden", "Abbrechen", True, True)
    vs.CreateStyledStatic(dialog, 10, "VERBINDUNG  |  Vorhandene Höhenpunkte", -1, TITLE_STYLE)
    vs.CreateStaticText(dialog, 11, "Von Punkt:", -1)
    vs.CreatePullDownMenu(dialog, 12, 38)
    vs.CreateStaticText(dialog, 13, "Zu Punkt:", -1)
    vs.CreatePullDownMenu(dialog, 14, 38)
    vs.CreateStaticText(dialog, 15, "Level / Gefällebene:", -1)
    vs.CreateEditText(dialog, 16, str(level), 28)
    vs.CreateStaticText(dialog, 17, "Beide Höhen bleiben erhalten. Länge und Gefälle werden aus den vorhandenen "
                        "Punkten berechnet und beim Verschieben automatisch aktualisiert.", 72)
    vs.SetFirstLayoutItem(dialog, 10)
    vs.SetBelowItem(dialog, 10, 11, 0, 5)
    vs.SetRightItem(dialog, 11, 12, 6, 0)
    vs.SetBelowItem(dialog, 11, 13, 0, 5)
    vs.SetRightItem(dialog, 13, 14, 6, 0)
    vs.SetBelowItem(dialog, 13, 15, 0, 5)
    vs.SetRightItem(dialog, 15, 16, 6, 0)
    vs.SetBelowItem(dialog, 15, 17, 0, 5)
    result = {"value": None}

    def handler(item, _data):
        if item == INIT_EVENT:
            for index, (_, point) in enumerate(points):
                caption = "P:%d  |  H=%s m" % (point["number"], ("%.3f" % point["height_m"]).replace(".", ","))
                vs.AddChoice(dialog, 12, caption, index)
                vs.AddChoice(dialog, 14, caption, index)
            vs.SelectChoice(dialog, 12, 0, True)
            vs.SelectChoice(dialog, 14, 1, True)
        elif item == 1:
            try:
                first, second = _choice_index(dialog, 12), _choice_index(dialog, 14)
                chosen_level = str(vs.GetItemText(dialog, 16) or "").strip()
                if first == second:
                    raise core.SlopeError("Bitte zwei unterschiedliche Höhenpunkte wählen.")
                if not chosen_level:
                    raise core.SlopeError("Bitte ein Level eingeben.")
                result["value"] = dict(first=points[first][0], second=points[second][0], level=chosen_level)
            except (ValueError, IndexError) as error:
                vw_adapter.alert(error)
                return -1
        return item
    return result["value"] if _run(dialog, handler) == 1 else None


def insert_point_dialog(info):
    """Read-only preview. Only the explicit OK result authorizes replacement."""
    dialog = vs.CreateResizableLayout(
        _title("PD Gefälle-Tool – Höhenpunkt einfügen"), True,
        "Höhenpunkt setzen", "Abbrechen", True, True)
    def fmt(value):
        return ("%.4f" % value).replace(".", ",")
    rows = (
        (10, "ANSCHLUSSHÖHE PRÜFEN", TITLE_STYLE),
        (11, "Neuer Punkt P:%d   |   Höhe H=%s m" % (info["number"], fmt(info["height_m"])), SECTION_STYLE),
        (12, "Verbindung P:%d → P:%d wird in zwei Gefällesegmente geteilt." %
         (info["from_number"], info["to_number"]), None),
        (13, "P:%d → P:%d: %s m\nP:%d → P:%d: %s m" %
         (info["from_number"], info["number"], fmt(info["first_length_m"]),
          info["number"], info["to_number"], fmt(info["second_length_m"])), None),
        (14, "Position auf der Verbindung: X=%s m, Y=%s m\nAbstand vom Klick zur Verbindung: %s m" %
         (fmt(info["x_m"]), fmt(info["y_m"]), fmt(info["click_offset_m"])), None),
        (15, ("Interpolation entlang des Bogens, nicht entlang der Sehne. " if info["curved"] else "") +
         "Vorhandene Höhen und Punktnummern bleiben erhalten. Erst mit 'Höhenpunkt setzen' "
         "wird die Zeichnung geändert. 'Abbrechen' verwirft die Eingabe vollständig.", None),
    )
    previous = None
    for item, text, style in rows:
        if style is None:
            vs.CreateStaticText(dialog, item, text, 68)
        else:
            vs.CreateStyledStatic(dialog, item, text, -1, style)
        if previous is None:
            vs.SetFirstLayoutItem(dialog, item)
        else:
            vs.SetBelowItem(dialog, previous, item, 0, 7)
        vs.SetEdgeBinding(dialog, item, True, True, True, False)
        previous = item
    return _run(dialog, lambda item, data: item) == 1


def calculation_dialog(default_level, start_number, draw_mode=False, curved=False, lock_level=False):
    (I_TITLE, I_START_L, I_START, I_MODE_L, I_MODE, I_VALUE_L, I_VALUE,
     I_LEVEL_L, I_LEVEL, I_NUMBER_L, I_NUMBER, I_INFO) = range(10, 22)
    result = {"value": None}
    dialog = vs.CreateResizableLayout(
        _title("PD Gefälle-Tool – neues Gefälle"), True,
        "Punkte wählen" if draw_mode else "Berechnen", "Abbrechen", True, True)
    vs.CreateStyledStatic(dialog, I_TITLE, "NEUES GEFÄLLE  |  Höhenvorgabe", -1, TITLE_STYLE)
    vs.CreateStaticText(dialog, I_START_L, "Anfangshöhe [m]:", -1)
    vs.CreateEditText(dialog, I_START, "0,00", 14)
    vs.CreateStaticText(dialog, I_MODE_L, "Berechnung:", -1)
    vs.CreatePullDownMenu(dialog, I_MODE, 34)
    vs.CreateStaticText(dialog, I_VALUE_L, "Gefälle [%]:", -1)
    vs.CreateEditText(dialog, I_VALUE, "2,00", 14)
    vs.CreateStaticText(dialog, I_LEVEL_L, "Level / Ebene:", -1)
    vs.CreateEditText(dialog, I_LEVEL, str(default_level), 34)
    vs.CreateStaticText(dialog, I_NUMBER_L, "Erste Punktnummer:", -1)
    vs.CreateEditInteger(dialog, I_NUMBER, int(start_number), 8)
    vs.CreateStaticText(
        dialog, I_INFO,
        "Positive Prozentwerte bedeuten: Die Höhe fällt in Zeichenrichtung. "
        "Die Ebene wird automatisch mit GEF- angelegt."
        + (" Gebogene Polylinie erkannt: Höhenpunkte liegen auf der Kurve; "
           "Höhen und Längen werden entlang des Bogens berechnet." if curved else "")
        + (" Danach beliebig viele Punkte der Reihe nach anklicken. "
           "Abschließen: den letzten Punkt nochmals anklicken. "
           "Mindestens zwei verschiedene Punkte sind nötig. Esc bricht ohne Erstellung ab."
           if draw_mode else ""), 70)
    vs.SetFirstLayoutItem(dialog, I_TITLE)
    previous = I_TITLE
    for label, control in ((I_START_L, I_START), (I_MODE_L, I_MODE),
                           (I_VALUE_L, I_VALUE), (I_LEVEL_L, I_LEVEL),
                           (I_NUMBER_L, I_NUMBER)):
        vs.SetBelowItem(dialog, previous, label, 0, 6)
        vs.SetRightItem(dialog, label, control, 10, 0)
        previous = label
    vs.SetBelowItem(dialog, previous, I_INFO, 0, 8)
    vs.SetEdgeBinding(dialog, I_INFO, True, True, True, False)

    def update_mode():
        end_mode = _choice_index(dialog, I_MODE) == 1
        vs.SetItemText(dialog, I_VALUE_L, "Endhöhe [m]:" if end_mode else "Gefälle [%]:")

    def handler(item, _data):
        if item == INIT_EVENT:
            vs.EnableItem(dialog, I_LEVEL, not lock_level)
            vs.AddChoice(dialog, I_MODE, "Durchgängiges Gefälle in Prozent", 0)
            vs.AddChoice(dialog, I_MODE, "Anfangs- und Endhöhe interpolieren", 1)
            vs.SelectChoice(dialog, I_MODE, 0, True)
        elif item == I_MODE:
            update_mode()
        elif item == 1:
            try:
                mode = "end" if _choice_index(dialog, I_MODE) == 1 else "slope"
                result["value"] = {
                    "start_height_m": _float(dialog, I_START, "Anfangshöhe"),
                    "mode": mode,
                    "value": _float(dialog, I_VALUE, "Endhöhe" if mode == "end" else "Gefälle"),
                    "level": default_level if lock_level else str(vs.GetItemText(dialog, I_LEVEL) or "Standard").strip() or "Standard",
                    "start_number": int(vs.GetEditInteger(dialog, I_NUMBER)[1]),
                }
                if result["value"]["start_number"] < 1:
                    raise ValueError("Die erste Punktnummer muss mindestens 1 sein.")
            except (ValueError, TypeError) as error:
                vw_adapter.alert(error)
                return -1
        return item

    return result["value"] if _run(dialog, handler) == 1 else None


def branch_dialog(points, default_level, next_number, lock_level=False):
    (I_TITLE, I_POINT_L, I_POINT, I_MODE_L, I_MODE, I_VALUE_L, I_VALUE,
     I_LEVEL_L, I_LEVEL, I_INFO) = range(10, 20)
    result = {"value": None}
    points = tuple(points)
    dialog = vs.CreateResizableLayout(
        _title("PD Gefälle-Tool – Gefälle fortsetzen"), True,
        "Weiterzeichnen", "Abbrechen", True, True)
    vs.CreateStyledStatic(dialog, I_TITLE, "GEFÄLLE FORTSETZEN  |  Anschlusspunkt", -1, TITLE_STYLE)
    vs.CreateStaticText(dialog, I_POINT_L, "Ausgangspunkt:", -1)
    vs.CreatePullDownMenu(dialog, I_POINT, 38)
    vs.CreateStaticText(dialog, I_MODE_L, "Berechnung:", -1)
    vs.CreatePullDownMenu(dialog, I_MODE, 34)
    vs.CreateStaticText(dialog, I_VALUE_L, "Gefälle [%]:", -1)
    vs.CreateEditText(dialog, I_VALUE, "2,00", 14)
    vs.CreateStaticText(dialog, I_LEVEL_L, "Level / Ebene:", -1)
    vs.CreateEditText(dialog, I_LEVEL, str(default_level), 32)
    vs.CreateStaticText(dialog, I_INFO,
                        "Neue Punkte beginnen mit P:%d. Danach beliebig viele neue Punkte "
                        "der Reihe nach anklicken; der Ausgangspunkt ist bereits festgelegt. "
                        "Abschließen: den letzten neuen Punkt nochmals anklicken. "
                        "Esc bricht ohne neues Gefälle ab." % next_number, 66)
    vs.SetFirstLayoutItem(dialog, I_TITLE)
    previous = I_TITLE
    for label, control in ((I_POINT_L, I_POINT), (I_MODE_L, I_MODE),
                           (I_VALUE_L, I_VALUE), (I_LEVEL_L, I_LEVEL)):
        vs.SetBelowItem(dialog, previous, label, 0, 6)
        vs.SetRightItem(dialog, label, control, 10, 0)
        previous = label
    vs.SetBelowItem(dialog, previous, I_INFO, 0, 8)

    def handler(item, _data):
        if item == INIT_EVENT:
            vs.EnableItem(dialog, I_LEVEL, not lock_level)
            for index, row in enumerate(points):
                vs.AddChoice(dialog, I_POINT, "P:%d  H=%.3fm  |  %s" % (
                    row[2], row[3], row[1]), index)
            vs.SelectChoice(dialog, I_POINT, 0, True)
            vs.AddChoice(dialog, I_MODE, "Durchgängiges Gefälle in Prozent", 0)
            vs.AddChoice(dialog, I_MODE, "Endhöhe interpolieren", 1)
            vs.SelectChoice(dialog, I_MODE, 0, True)
        elif item == I_MODE:
            end_mode = _choice_index(dialog, I_MODE) == 1
            vs.SetItemText(dialog, I_VALUE_L, "Endhöhe [m]:" if end_mode else "Gefälle [%]:")
        elif item == 1:
            try:
                index = _choice_index(dialog, I_POINT)
                mode = "end" if _choice_index(dialog, I_MODE) == 1 else "slope"
                result["value"] = {
                    "chain_id": points[index][0], "point_number": points[index][2],
                    "mode": mode, "value": _float(dialog, I_VALUE, "Berechnungswert"),
                    "level": default_level if lock_level else str(vs.GetItemText(dialog, I_LEVEL) or "Standard").strip() or "Standard",
                }
            except (ValueError, IndexError, TypeError) as error:
                vw_adapter.alert(error)
                return -1
        return item

    return result["value"] if _run(dialog, handler) == 1 else None


def edit_point_dialog(chain):
    I_TITLE, I_POINT_L, I_POINT, I_HEIGHT_L, I_HEIGHT, I_INFO = range(10, 16)
    points = tuple(chain["points"])
    result = {"value": None}
    dialog = vs.CreateResizableLayout(
        _title("PD Gefälle-Tool – Punkthöhe ändern"), True,
        "Ändern", "Abbrechen", True, True)
    vs.CreateStyledStatic(dialog, I_TITLE, "PUNKTHÖHE ÄNDERN", -1, TITLE_STYLE)
    vs.CreateStaticText(dialog, I_POINT_L, "Punktnummer:", -1)
    vs.CreatePullDownMenu(dialog, I_POINT, 28)
    vs.CreateStaticText(dialog, I_HEIGHT_L, "Neue Höhe [m]:", -1)
    vs.CreateEditText(dialog, I_HEIGHT, "", 14)
    vs.CreateStaticText(dialog, I_INFO, "Die Gefällewerte zu den benachbarten Punkten werden automatisch neu berechnet.", 64)
    vs.SetFirstLayoutItem(dialog, I_TITLE)
    vs.SetBelowItem(dialog, I_TITLE, I_POINT_L, 0, 7)
    vs.SetRightItem(dialog, I_POINT_L, I_POINT, 9, 0)
    vs.SetBelowItem(dialog, I_POINT_L, I_HEIGHT_L, 0, 5)
    vs.SetRightItem(dialog, I_HEIGHT_L, I_HEIGHT, 9, 0)
    vs.SetBelowItem(dialog, I_HEIGHT_L, I_INFO, 0, 8)

    def handler(item, _data):
        if item == INIT_EVENT:
            for index, point in enumerate(points):
                vs.AddChoice(dialog, I_POINT, "P:%d  H=%.3fm" % (
                    point["number"], point["height_m"]), index)
            vs.SelectChoice(dialog, I_POINT, 0, True)
            vs.SetItemText(dialog, I_HEIGHT, "%.3f" % points[0]["height_m"])
        elif item == I_POINT:
            point = points[_choice_index(dialog, I_POINT)]
            vs.SetItemText(dialog, I_HEIGHT, "%.3f" % point["height_m"])
        elif item == 1:
            try:
                point = points[_choice_index(dialog, I_POINT)]
                result["value"] = (point["number"], _float(dialog, I_HEIGHT, "Höhe"))
            except (ValueError, IndexError) as error:
                vw_adapter.alert(error)
                return -1
        return item
    return result["value"] if _run(dialog, handler) == 1 else None


def edit_slope_dialog(chain, segments):
    I_TITLE, I_SEG_L, I_SEG, I_SLOPE_L, I_SLOPE, I_ADJUST_L, I_ADJUST, I_INFO = range(10, 18)
    segments = tuple(segments)
    result = {"value": None}
    dialog = vs.CreateResizableLayout(
        _title("PD Gefälle-Tool – Gefälle ändern"), True,
        "Ändern", "Abbrechen", True, True)
    vs.CreateStyledStatic(dialog, I_TITLE, "GEFÄLLE ÄNDERN", -1, TITLE_STYLE)
    vs.CreateStaticText(dialog, I_SEG_L, "Segment:", -1)
    vs.CreatePullDownMenu(dialog, I_SEG, 34)
    vs.CreateStaticText(dialog, I_SLOPE_L, "Neues Gefälle [%]:", -1)
    vs.CreateEditText(dialog, I_SLOPE, "", 14)
    vs.CreateStaticText(dialog, I_ADJUST_L, "Anzupassender Höhenpunkt:", -1)
    vs.CreatePullDownMenu(dialog, I_ADJUST, 18)
    vs.CreateStaticText(dialog, I_INFO, "Der nicht gewählte Punkt bleibt höhenmäßig unverändert.", 62)
    vs.SetFirstLayoutItem(dialog, I_TITLE)
    previous = I_TITLE
    for label, control in ((I_SEG_L, I_SEG), (I_SLOPE_L, I_SLOPE),
                           (I_ADJUST_L, I_ADJUST)):
        vs.SetBelowItem(dialog, previous, label, 0, 6)
        vs.SetRightItem(dialog, label, control, 9, 0)
        previous = label
    vs.SetBelowItem(dialog, previous, I_INFO, 0, 8)

    def fill_adjust(segment):
        # Vectorworks exposes RemoveChoice, not a cross-version
        # RemoveAllChoices call.  This menu always contains exactly two rows.
        for _unused in range(2):
            try:
                vs.RemoveChoice(dialog, I_ADJUST, 0)
            except Exception:
                break
        vs.AddChoice(dialog, I_ADJUST, "P:%d" % segment["from"], 0)
        vs.AddChoice(dialog, I_ADJUST, "P:%d" % segment["to"], 1)
        vs.SelectChoice(dialog, I_ADJUST, 1, True)
        vs.SetItemText(dialog, I_SLOPE, "%.3f" % segment["slope_percent"])

    def handler(item, _data):
        if item == INIT_EVENT:
            for index, segment in enumerate(segments):
                vs.AddChoice(dialog, I_SEG, "P:%d → P:%d  (%.3f %%)" % (
                    segment["from"], segment["to"], segment["slope_percent"]), index)
            vs.SelectChoice(dialog, I_SEG, 0, True)
            fill_adjust(segments[0])
        elif item == I_SEG:
            fill_adjust(segments[_choice_index(dialog, I_SEG)])
        elif item == 1:
            try:
                segment = segments[_choice_index(dialog, I_SEG)]
                adjust = segment["from"] if _choice_index(dialog, I_ADJUST) == 0 else segment["to"]
                result["value"] = (segment["from"], segment["to"],
                                   _float(dialog, I_SLOPE, "Gefälle"), adjust)
            except (ValueError, IndexError) as error:
                vw_adapter.alert(error)
                return -1
        return item
    return result["value"] if _run(dialog, handler) == 1 else None


def _chain_table_columns(dialog, item, columns, single=False):
    for column, (label, width) in enumerate(columns):
        vs.InsertLBColumn(dialog, item, column, label, width)
        vs.SetLBControlType(dialog, item, column, 1)
        vs.SetLBItemDisplayType(dialog, item, column, 0)
    vs.EnableLBColumnLines(dialog, item, True)
    vs.EnableLBSingleLineSelection(dialog, item, single)
    vs.EnableLBSorting(dialog, item, False)  # row order IS the path order


def _chain_table_rows(dialog, item, rows):
    vs.EnableLBUpdates(dialog, item, False)
    try:
        vs.DeleteAllLBItems(dialog, item)
        for row, values in enumerate(rows):
            inserted = vs.InsertLBItem(dialog, item, row, str(values[0]))
            if inserted != row:
                raise ValueError("Die Kettenliste konnte nicht vollständig aufgebaut werden.")
            for column, value in enumerate(values[1:], 1):
                if vs.SetLBItemInfo(dialog, item, row, column, str(value), -1) is False:
                    raise ValueError("Die Kettenliste konnte nicht vollständig angezeigt werden.")
    finally:
        vs.EnableLBUpdates(dialog, item, True)


def chain_selection_dialog(chain, previous=None, highlight=None):
    """Draft individual heights or regrade a selection; no drawing changes."""
    (TITLE, HINT, MODE_L, MODE, LIST, ALL, NONE, STATUS, SLOPE_L, SLOPE,
     FIX_L, FIX, NUMBER_L, NUMBER, NOTE) = range(10, 25)
    HEIGHT_L, HEIGHT, APPLY_HEIGHT, CLEAR_HEIGHTS = range(25, 29)
    points = chain["points"]
    segments = core.segment_rows(chain)
    previous = previous or dict(mode="points", rows=(), slope_percent=segments[0]["slope_percent"], fixed="first")
    result = {"value": None}
    state = {"count": 0, "edit_row": None, "edit_text": "", "filling": False}
    overrides = dict(previous.get("height_overrides", {}))
    def fmt(value):
        return ("%.4f" % value).replace(".", ",")
    dialog = vs.CreateResizableLayout(_title("PD Gefälle-Tool – Kette auswählen"), False,
                                      "Vorschau", "Abbrechen", True, True)
    vs.CreateStyledStatic(dialog, TITLE, "KETTE ÄNDERN  |  Punkthöhen und Gefälle", -1, TITLE_STYLE)
    vs.CreateStaticText(dialog, HINT, "Einzelhöhe: Punkt markieren oder doppelklicken, unten Höhe eingeben. "
                        "Kettengefälle: mehrere Punkte mit Strg-/Umschalt-Klick auswählen.", 72)
    vs.CreateStaticText(dialog, MODE_L, "Auswahl über:", -1)
    vs.CreatePullDownMenu(dialog, MODE, 34)
    vs.CreateLB(dialog, LIST, 94, 16)
    vs.CreatePushButton(dialog, ALL, "Ganze Kette auswählen")
    vs.CreatePushButton(dialog, NONE, "Auswahl leeren")
    vs.CreateStaticText(dialog, STATUS, "Noch keine Kette gewählt.", 72)
    vs.CreateStaticText(dialog, HEIGHT_L, "Punkthöhe [m]:", -1)
    vs.CreateEditText(dialog, HEIGHT, "", 16)
    vs.CreatePushButton(dialog, APPLY_HEIGHT, "Höhe in Liste übernehmen")
    vs.CreatePushButton(dialog, CLEAR_HEIGHTS, "Höhenänderungen verwerfen")
    vs.CreateStaticText(dialog, SLOPE_L, "Neues Gefälle [%]:", -1)
    vs.CreateEditText(dialog, SLOPE, fmt(previous["slope_percent"]), 12)
    vs.CreateStaticText(dialog, FIX_L, "Höhe unverändert lassen:", -1)
    vs.CreatePullDownMenu(dialog, FIX, 36)
    vs.CreateStaticText(dialog, NUMBER_L, "Feste Punktnummer P:", -1)
    initial_number = previous["fixed"] if isinstance(previous["fixed"], int) else points[0]["number"]
    vs.CreateEditInteger(dialog, NUMBER, initial_number, 8)
    vs.CreateStaticText(dialog, NOTE, "* = geänderte Punkthöhe im Entwurf. Weitere Punkte einzeln bearbeiten; "
                        "alle anderen Höhen bleiben fest. Alternativ Entwurf verwerfen und Kettengefälle ändern. "
                        "Positives Gefälle fällt in Tabellenrichtung. Schreiben erst nach Vorschau.", 72)
    vs.SetFirstLayoutItem(dialog, TITLE)
    vs.SetBelowItem(dialog, TITLE, HINT, 0, 6)
    vs.SetBelowItem(dialog, HINT, MODE_L, 0, 6)
    vs.SetRightItem(dialog, MODE_L, MODE, 8, 0)
    vs.SetBelowItem(dialog, MODE_L, LIST, 0, 6)
    vs.SetBelowItem(dialog, LIST, ALL, 0, 5)
    vs.SetRightItem(dialog, ALL, NONE, 6, 0)
    vs.SetBelowItem(dialog, ALL, STATUS, 0, 5)
    vs.SetBelowItem(dialog, STATUS, HEIGHT_L, 0, 5)
    vs.SetRightItem(dialog, HEIGHT_L, HEIGHT, 8, 0)
    vs.SetRightItem(dialog, HEIGHT, APPLY_HEIGHT, 8, 0)
    vs.SetBelowItem(dialog, HEIGHT_L, CLEAR_HEIGHTS, 0, 5)
    prior = CLEAR_HEIGHTS
    for label, control in ((SLOPE_L,SLOPE), (FIX_L,FIX), (NUMBER_L,NUMBER)):
        vs.SetBelowItem(dialog, prior, label, 0, 5)
        vs.SetRightItem(dialog, label, control, 8, 0)
        prior = label
    vs.SetBelowItem(dialog, prior, NOTE, 0, 6)
    vs.SetEdgeBinding(dialog, LIST, True, True, True, True)
    for item in (HINT,):
        vs.SetEdgeBinding(dialog, item, True, True, True, False)
    for item in (ALL,NONE,STATUS,HEIGHT_L,HEIGHT,APPLY_HEIGHT,CLEAR_HEIGHTS,
                 SLOPE_L,SLOPE,FIX_L,FIX,NUMBER_L,NUMBER,NOTE):
        vs.SetEdgeBinding(dialog, item, True, item in (STATUS,NOTE), False, True)

    def mode():
        return "points" if _choice_index(dialog, MODE) == 0 else "segments"

    def selected_rows():
        return [i for i in range(state["count"]) if vs.IsLBItemSelected(dialog, LIST, i)]

    def status():
        try:
            if overrides:
                vs.SetItemText(dialog, STATUS, "%d Punkthöhe(n) geändert (*). Nur diese Höhen und ihre Anschlüsse werden angepasst." % len(overrides))
                return
            rows = selected_rows()
            if mode() == "points" and len(rows) == 1:
                vs.SetItemText(dialog, STATUS, "P:%d ausgewählt: Höhe unten bearbeiten. Für ein Kettengefälle weitere Punkte markieren."
                               % points[rows[0]]["number"])
                return
            first, last = chain_edit.selection_span(chain, mode(), rows)
            text = "Kette P:%d → P:%d: %d Höhenpunkte, %d Verbindungen. Alle Zwischenpunkte werden einbezogen." % (
                points[first]["number"], points[last]["number"], last-first+1, last-first)
        except ValueError as error:
            text = str(error)
        vs.SetItemText(dialog, STATUS, text)

    def fill(rows=()):
        state["filling"] = True
        try:
            if mode() == "points":
                data = [("P:%d%s" % (p["number"], " *" if p["number"] in overrides else ""),
                         fmt(overrides.get(p["number"], p["height_m"])), "", "") for p in points]
            else:
                draft = chain_edit.edit_heights(chain, overrides)[0] if overrides else chain
                data = [("P:%d → P:%d" % (s["from"],s["to"]), "", fmt(s["length_m"]), fmt(s["slope_percent"]))
                        for s in core.segment_rows(draft)]
            _chain_table_rows(dialog, LIST, data)
            state["count"] = len(data)
            vs.SetLBSelection(dialog, LIST, 0, len(data)-1, False)
            for i in rows:
                if 0 <= i < len(data):
                    vs.SetLBSelection(dialog, LIST, i, i, True)
            load_editor()
            status()
            fix_controls()
            if highlight:
                highlight(mode(), selected_rows())
        finally:
            state["filling"] = False

    def load_editor():
        rows = selected_rows()
        row = rows[0] if mode() == "points" and len(rows) == 1 else None
        state["edit_row"] = row
        text, label = "", "Punkthöhe [m]:"
        if row is not None:
            point = points[row]
            text = fmt(overrides.get(point["number"], point["height_m"]))
            label = "Höhe P:%d [m]:" % point["number"]
        state["edit_text"] = text
        vs.SetItemText(dialog, HEIGHT, text)
        vs.SetItemText(dialog, HEIGHT_L, label)
        for item in (HEIGHT, APPLY_HEIGHT):
            vs.EnableItem(dialog, item, row is not None)

    def keep_pending_height():
        # Compare the input text before parsing: merely selecting a row must
        # never round its full-precision stored height to the displayed value.
        row = state["edit_row"]
        if row is None or vs.GetItemText(dialog, HEIGHT) == state["edit_text"]:
            return
        value = core._number(_float(dialog, HEIGHT, "Punkthöhe"), "Punkthöhe")
        point = points[row]
        if value == point["height_m"]:
            overrides.pop(point["number"], None)
        else:
            overrides[point["number"]] = value
        state["edit_text"] = vs.GetItemText(dialog, HEIGHT)

    def fix_controls():
        for item in (SLOPE_L,SLOPE,FIX_L,FIX):
            vs.EnableItem(dialog, item, not overrides)
        vs.EnableItem(dialog, CLEAR_HEIGHTS, bool(overrides) or state["edit_row"] is not None)
        custom = not overrides and _choice_index(dialog, FIX) == 2
        vs.EnableItem(dialog, NUMBER_L, custom)
        vs.EnableItem(dialog, NUMBER, custom)

    def handler(item, _data):
        if state["filling"]:
            return item
        if item in (MODE,ALL,NONE,APPLY_HEIGHT,1) or abs(item) == LIST:
            try:
                keep_pending_height()
            except (ValueError, TypeError) as error:
                vw_adapter.alert(error)
                vs.SetFocusOnItem(dialog, HEIGHT)
                return -1
        if item == INIT_EVENT:
            vs.AddChoice(dialog, MODE, "Höhenpunkte (mit allen Zwischenpunkten)", 0)
            vs.AddChoice(dialog, MODE, "Zusammenhängende Verbindungen", 1)
            vs.SelectChoice(dialog, MODE, 0 if previous["mode"] == "points" else 1, True)
            for i, name in enumerate(("Erster Punkt der gewählten Kette", "Letzter Punkt der gewählten Kette", "Bestimmte Punktnummer in der Kette")):
                vs.AddChoice(dialog, FIX, name, i)
            vs.SelectChoice(dialog, FIX, 0 if previous["fixed"] == "first" else 1 if previous["fixed"] == "last" else 2, True)
            _chain_table_columns(dialog, LIST, (("Punkt / Verbindung",185), ("Höhe [m]",100), ("Länge [m]",100), ("Gefälle [%]",100)))
            fill(previous["rows"])
            fix_controls()
        elif item == MODE:
            fill()
        elif abs(item) == LIST:
            event = vs.GetLBEventInfo(dialog, LIST)
            fill(selected_rows())
            if event and event[0] and event[1] == -5 and state["edit_row"] is not None:
                vs.SetFocusOnItem(dialog, HEIGHT)
        elif item in (ALL,NONE):
            vs.SetLBSelection(dialog, LIST, 0, state["count"]-1, item == ALL)
            fill(selected_rows())
        elif item == APPLY_HEIGHT:
            fill(selected_rows())
        elif item == CLEAR_HEIGHTS:
            overrides.clear()
            fill(selected_rows())
        elif item == FIX:
            fix_controls()
        elif item == 1:
            try:
                fixed = previous["fixed"] if overrides else ("first", "last", None)[_choice_index(dialog, FIX)]
                if fixed is None:
                    ok, fixed = vs.GetEditInteger(dialog, NUMBER)
                    if not ok:
                        raise ValueError("Bitte eine gültige Punktnummer eingeben.")
                choice = dict(mode=mode(), rows=selected_rows(),
                              slope_percent=previous["slope_percent"] if overrides else _float(dialog, SLOPE, "Gefälle"), fixed=fixed)
                if overrides:
                    choice["height_overrides"] = dict(overrides)
                chain_edit.preview(chain, **choice)
                result["value"] = choice
            except (ValueError, IndexError, TypeError) as error:
                vw_adapter.alert(error)
                return -1
        return item
    return result["value"] if _run(dialog, handler) == 1 else None


def chain_preview_dialog(info):
    TITLE, SUMMARY, LIST, BOUNDARY, NOTE = range(10,15)
    def fmt(value):
        return ("%.4f" % value).replace(".", ",")
    manual = info.get("operation") == "heights"
    apply_label = "Höhen anwenden" if manual else "Gefälle anwenden"
    dialog = vs.CreateResizableLayout(_title("PD Gefälle-Tool – Kettenvorschau"), False,
                                      apply_label, "Zurück", True, True)
    vs.CreateStyledStatic(dialog, TITLE, "NEUE KETTENHÖHEN PRÜFEN", -1, TITLE_STYLE)
    summary = ("%d manuell geänderte Punkthöhe(n). Alle übrigen Höhen bleiben unverändert."
               % len(info["points"]) if manual else
        "P:%d → P:%d | Länge %s m | neues Gefälle %s %%\nFest: P:%d auf H=%s m" % (
            info["from_number"],info["to_number"],fmt(info["length_m"]),fmt(info["slope_percent"]),
            info["fixed_number"],fmt(info["fixed_height_m"])))
    vs.CreateStaticText(dialog, SUMMARY, summary, 72)
    vs.CreateLB(dialog, LIST, 94, 16)
    boundary = "\n".join("Anschluss P:%d → P:%d: %s %% → %s %%" % (
        b["from_number"], b["to_number"], fmt(b["old_slope"]), fmt(b["new_slope"])) for b in info["boundary"][:6])
    if len(info["boundary"]) > 6:
        boundary += "\nWeitere %d Anschlussgefälle werden ebenfalls neu berechnet." % (len(info["boundary"])-6)
    if info.get("connected_groups"):
        boundary += "\n%d angeschlossene Gruppe(n): gemeinsame Höhen und Anschlussgefälle werden mitgeführt; übrige Punkthöhen bleiben fest." % info["connected_groups"]
    vs.CreateStaticText(dialog, BOUNDARY, boundary or "Keine angrenzenden Gefälle werden verändert.", 72)
    vs.CreateStaticText(dialog, NOTE, "Punktnummern, XY-Lage, Kurvenform und 2D-/3D-Einstellungen bleiben erhalten. "
                        "'Zurück': Entwurf anpassen, ohne Änderungen. Erst '%s' schreibt die neuen Höhen." % apply_label, 72)
    vs.SetFirstLayoutItem(dialog, TITLE)
    prior = TITLE
    for item in (SUMMARY,LIST,BOUNDARY,NOTE):
        vs.SetBelowItem(dialog, prior, item, 0, 6)
        prior = item
    vs.SetEdgeBinding(dialog, SUMMARY, True, True, True, False)
    vs.SetEdgeBinding(dialog, LIST, True, True, True, True)
    for item in (BOUNDARY,NOTE):
        vs.SetEdgeBinding(dialog, item, True, True, False, True)

    def handler(item, _data):
        if item == INIT_EVENT:
            _chain_table_columns(dialog, LIST, (("Höhenpunkt",140), ("Bisher [m]",115), ("Neu [m]",115), ("Änderung [m]",115)), single=True)
            _chain_table_rows(dialog, LIST, [("P:%d%s" % (p["number"], " (fest)" if p["fixed"] else ""),
                                            fmt(p["old_height_m"]),fmt(p["new_height_m"]),fmt(p["delta_m"])) for p in info["points"]])
        return item
    return _run(dialog, handler) == 1


def label_format_dialog(preferences):
    """Literal text fields, with a preview of the actual drawing formatter."""
    value = label_format.options(preferences.get("labels"))
    dialog = vs.CreateResizableLayout(_title("PD Gefälle-Tool – Beschriftungen"), True,
                                      "Übernehmen", "Abbrechen", True, True)
    vs.CreateStyledStatic(dialog, 10, "BESCHRIFTUNGEN  |  Präfix + Zahlenwert + Suffix", -1, TITLE_STYLE)
    vs.CreateStaticText(dialog, 11,
                        "Präfix steht vor, Suffix hinter der Zahl. Leere Felder sind erlaubt. "
                        "Gewünschte Leerzeichen mit eingeben; Einheiten werden nicht automatisch ergänzt.", 76)
    vs.SetFirstLayoutItem(dialog, 10)
    vs.SetBelowItem(dialog, 10, 11, 0, 7)
    rows = (("height", "Höhe", 20, 123.45), ("length", "Länge", 30, 12.34),
            ("slope", "Gefälle / Prozent", 40, 2.5))
    previous = 11
    for kind, caption, first, example in rows:
        vs.CreateStyledStatic(dialog, first, caption, -1, SECTION_STYLE)
        vs.CreateStaticText(dialog, first+1, "Präfix:", -1)
        vs.CreateEditText(dialog, first+2, value[kind]["prefix"], 28)
        vs.CreateStaticText(dialog, first+3, "Suffix:", -1)
        vs.CreateEditText(dialog, first+4, value[kind]["suffix"], 28)
        vs.CreateStaticText(dialog, first+5, "Vorschau: " + label_format.annotation(kind, example, preferences), 76)
        vs.SetBelowItem(dialog, previous, first, 0, 9)
        vs.SetBelowItem(dialog, first, first+1, 0, 4)
        vs.SetRightItem(dialog, first+1, first+2, 6, 0)
        vs.SetRightItem(dialog, first+2, first+3, 12, 0)
        vs.SetRightItem(dialog, first+3, first+4, 6, 0)
        vs.SetBelowItem(dialog, first+1, first+5, 0, 4)
        vs.SetEdgeBinding(dialog, first+5, True, True, True, False)
        previous = first+5
    result = {"value": None}

    def handler(item, _data):
        if item == 1 or item in tuple(first+i for _, _, first, _ in rows for i in (2, 4)):
            try:
                supplied = {kind: {"prefix": vs.GetItemText(dialog, first+2),
                                   "suffix": vs.GetItemText(dialog, first+4)}
                            for kind, _, first, _ in rows}
                updated = label_format.options(supplied)
                preview = dict(preferences, labels=updated)
                for kind, _, first, example in rows:
                    vs.SetItemText(dialog, first+5, "Vorschau: " + label_format.annotation(kind, example, preview))
                if item == 1:
                    result["value"] = updated
            except (ValueError, TypeError) as error:
                vw_adapter.alert(error)
                return -1
        return item
    return result["value"] if _run(dialog, handler) == 1 else None


def preferences_dialog(preferences):
    I_TITLE, I_INFO = 10, 11
    row_ids = {}
    next_id = 20
    labels = (("height", "Gefällehöhe"), ("number", "Punktnummer"),
              ("line", "Gefällelinie"), ("slope", "Gefälletext"),
              ("length", "Längentext"))
    result = {"value": None}
    dialog = vs.CreateResizableLayout(
        _title("PD Gefälle-Tool – Voreinstellungen"), True,
        "Speichern", "Abbrechen", True, True)
    vs.CreateStyledStatic(dialog, I_TITLE, "VOREINSTELLUNGEN  |  Klassen und Darstellung", -1, TITLE_STYLE)
    vs.CreateStaticText(dialog, I_INFO, "Klassenname und Stiftfarbe festlegen. Bestehende Klassen werden aktualisiert.", 72)
    for key, label in labels:
        row_ids[key] = (next_id, next_id + 1, next_id + 2)
        vs.CreateStaticText(dialog, next_id, label + ":", -1)
        vs.CreateEditText(dialog, next_id + 1, str(preferences["classes"][key]["name"]), 30)
        vs.CreateColorPopup(dialog, next_id + 2, 18)
        next_id += 3
    extra = {
        "font_size": (next_id, next_id + 1),
        "offset": (next_id + 2, next_id + 3),
        "level": (next_id + 4, next_id + 5),
    }
    I_ALIGN, I_ALIGN_HINT = next_id + 6, next_id + 7
    I_POINTS = next_id + 8
    I_LABELS = next_id + 9
    pending_points = {"value": point_output.options(preferences.get("point_output"))}
    pending_labels = {"value": label_format.options(preferences.get("labels"))}
    vs.CreateStaticText(dialog, extra["font_size"][0], "Schriftgröße [pt]:", -1)
    vs.CreateEditText(dialog, extra["font_size"][1], str(preferences["point_size"]), 10)
    vs.CreateStaticText(dialog, extra["offset"][0], "Textabstand [mm Papier]:", -1)
    vs.CreateEditText(dialog, extra["offset"][1], str(preferences["offset_mm"]), 10)
    vs.CreateStaticText(dialog, extra["level"][0], "Standard-Level:", -1)
    vs.CreateEditText(dialog, extra["level"][1], str(preferences["default_level"]), 28)
    vs.CreateCheckBox(dialog, I_ALIGN, "Texte an aktueller Plandrehung ausrichten")
    vs.CreatePushButton(dialog, I_POINTS, "Darstellung: 2D / zusätzlich 3D, Punktsymbole …")
    vs.CreatePushButton(dialog, I_LABELS, "Beschriftungen: Präfix und Suffix für Höhe, Länge, Prozent …")
    vs.CreateStaticText(dialog, I_ALIGN_HINT,
                        "Punktnummern und Höhen: waagerecht zur gedrehten Ansicht. "
                        "Gefälle und Länge: entlang der Linie, in der Ansicht lesbar. "
                        "Vorhandene Texte: anschließend 'Gefälle neu zeichnen' wählen.", 72)
    vs.SetFirstLayoutItem(dialog, I_TITLE)
    vs.SetBelowItem(dialog, I_TITLE, I_INFO, 0, 7)
    previous = I_INFO
    for key, _label in labels:
        label_id, edit_id, color_id = row_ids[key]
        vs.SetBelowItem(dialog, previous, label_id, 0, 5)
        vs.SetRightItem(dialog, label_id, edit_id, 8, 0)
        vs.SetRightItem(dialog, edit_id, color_id, 5, 0)
        previous = label_id
    for label_id, edit_id in extra.values():
        vs.SetBelowItem(dialog, previous, label_id, 0, 5)
        vs.SetRightItem(dialog, label_id, edit_id, 8, 0)
        previous = label_id
    vs.SetBelowItem(dialog, previous, I_ALIGN, 0, 6)
    vs.SetBelowItem(dialog, I_ALIGN, I_ALIGN_HINT, 0, 4)
    vs.SetBelowItem(dialog, I_ALIGN_HINT, I_POINTS, 0, 5)
    vs.SetBelowItem(dialog, I_POINTS, I_LABELS, 0, 5)
    vs.SetEdgeBinding(dialog, I_ALIGN_HINT, True, True, True, False)

    def handler(item, _data):
        if item == INIT_EVENT:
            vs.SetBooleanItem(dialog, I_ALIGN, bool(preferences.get("align_text_to_plan", False)))
            for key, _label in labels:
                color = preferences["classes"][key]["color"]
                index = vs.RGBToColorIndex(*color)
                vs.SetColorChoice(dialog, row_ids[key][2], index)
        elif item == I_LABELS:
            updated = label_format_dialog(dict(preferences, labels=pending_labels["value"]))
            if updated is not None:
                pending_labels["value"] = updated
        elif item == I_POINTS:
            line_class = str(vs.GetItemText(dialog, row_ids["line"][1]) or "").strip()
            if not line_class:
                vw_adapter.alert("Bitte zuerst die 2D-Linienklasse eingeben.")
                return -1
            updated = point_output_dialog(pending_points["value"], line_class)
            if updated is not None:
                pending_points["value"] = updated
        elif item == 1:
            try:
                value = dict(preferences)
                value["point_output"] = pending_points["value"]
                value["labels"] = pending_labels["value"]
                value["align_text_to_plan"] = bool(vs.GetBooleanItem(dialog, I_ALIGN))
                value["classes"] = {}
                for key, _label in labels:
                    _label_id, edit_id, color_id = row_ids[key]
                    name = str(vs.GetItemText(dialog, edit_id) or "").strip()
                    if not name:
                        raise ValueError("Jede Klasse benötigt einen Namen.")
                    color = tuple(vs.ColorIndexToRGB(vs.GetColorChoice(dialog, color_id)))
                    value["classes"][key] = {"name": name, "color": list(color)}
                value["point_size"] = _float(dialog, extra["font_size"][1], "Schriftgröße")
                value["offset_mm"] = _float(dialog, extra["offset"][1], "Textabstand")
                value["default_level"] = str(vs.GetItemText(dialog, extra["level"][1]) or "Standard").strip() or "Standard"
                result["value"] = settings.validate(value)
            except (ValueError, TypeError) as error:
                vw_adapter.alert(error)
                return -1
        return item
    return result["value"] if _run(dialog, handler) == 1 else None


def point_output_dialog(value, line_class=None):
    value = (point_output.for_line_class(value, line_class) if line_class is not None
             else point_output.options(value))
    dialog = vs.CreateResizableLayout(_title("PD Gefälle-Tool – 2D und zusätzliche 3D-Ausgabe"), True,
                                      "Übernehmen", "Abbrechen", True, True)
    vs.CreateStyledStatic(dialog, 10, "DARSTELLUNG  |  Vollständiger 2D-Plan + optional 3D", -1, TITLE_STYLE)
    rows = ((11, 12, "Ausgabe:"), (13, 14, "2D-Punktsymbol:"), (25, 26, "Zusätzliches 3D-Punktsymbol:"),
            (15, 16, "Symbolfaktor:"),
            (18, 19, "Bogenabweichung [mm Modell]:"), (20, 21, "Klasse Höhenpunkte:"),
            (28, 29, "3D-Punktklasse (automatisch):"), (22, 23, "3D-Linienklasse (automatisch):"))
    for label, _control, text in rows:
        vs.CreateStaticText(dialog, label, text, -1)
    vs.CreatePullDownMenu(dialog, 12, 35)
    vs.CreateResourcePopup(dialog, 14, 35)
    vs.CreateResourcePopup(dialog, 26, 35)
    vs.CreateCheckBox(dialog, 33, "Eigenes 2D-Symbol aus Dokument oder Bibliothek")
    vs.CreateCheckBox(dialog, 34, "Eigenes 3D-/Hybridsymbol aus Dokument oder Bibliothek")
    vs.CreateEditText(dialog, 16, str(value["scale"]), 10)
    vs.CreateEditText(dialog, 19, str(value["curve_tolerance_mm"]), 10)
    vs.CreateEditText(dialog, 21, value["point_class"], 30)
    vs.CreateStaticText(dialog, 29, point_output.class_3d(value["point_class"]), 38)
    vs.CreateStaticText(dialog, 23, value["line_class"], 38)
    vs.CreateCheckBox(dialog, 30, "3D-Linien automatisch als Geländemodifikatoren")
    vs.CreateCheckBox(dialog, 32, "3D-Punkte automatisch als Geländemodifikatoren")
    vs.CreateStaticText(dialog, 31,
                        "Bei jeder 3D-Ausgabe sind Punkt und Verbindung unmittelbar native Geländemodifikatoren. "
                        "Verschieben, Höhenänderungen und Kurvenänderungen bauen sie automatisch mit dem Gefällenetz neu auf. "
                        "Im Geländemodell die Ebene GEF-<Netz> für Modifikatoren zulassen und das Geländemodell aktualisieren.", 76)
    vs.CreateStaticText(dialog, 24,
                        "2D bleibt vollständig erhalten: Linien, Punktsymbole, Nummern und Texte. "
                        "Zusätzlich 3D erzeugt Höhenpunkte und Verbindungen auf den jeweiligen 2D-Klassen + _3D. "
                        "Texte bleiben ausschließlich 2D. Absolute Höhen berücksichtigen die Ebenenhöhe. "
                        "Standard-Kreuz: 10 cm bei Faktor 1. Eigene Symbole: 2D-Symbol oben, 3D-/Hybridsymbol zusätzlich. "
                        "Bestehende Punkte oder Verbindungen über 'Darstellung / Geländewirkung ändern' aktualisieren.", 76)
    vs.SetFirstLayoutItem(dialog, 10)
    vs.SetBelowItem(dialog, 10, 11, 0, 4)
    vs.SetRightItem(dialog, 11, 12, 8, 0)
    vs.SetBelowItem(dialog, 11, 13, 0, 4)
    vs.SetRightItem(dialog, 13, 14, 8, 0)
    vs.SetBelowItem(dialog, 14, 33, 0, 2)
    vs.SetBelowItem(dialog, 33, 25, 0, 4)
    vs.SetRightItem(dialog, 25, 26, 8, 0)
    vs.SetBelowItem(dialog, 26, 34, 0, 2)
    previous = 34
    for label, control, _text in rows[3:]:
        vs.SetBelowItem(dialog, previous, label, 0, 4)
        vs.SetRightItem(dialog, label, control, 8, 0)
        previous = label
    vs.SetBelowItem(dialog, previous, 30, 0, 6)
    vs.SetBelowItem(dialog, 30, 32, 0, 3)
    vs.SetBelowItem(dialog, 32, 31, 0, 2)
    vs.SetBelowItem(dialog, 31, 24, 0, 6)
    vs.SetEdgeBinding(dialog, 24, True, True, True, False)
    result = {"value": None}
    resource_2d = "PD.Gefaelle.Punktsymbol.2D"
    resource_3d = "PD.Gefaelle.Punktsymbol.3D"

    def update():
        enabled = _choice_index(dialog, 12) == 1
        vs.EnableItem(dialog, 26, enabled and bool(vs.GetBooleanItem(dialog, 34)))
        vs.EnableItem(dialog, 34, enabled)
        vs.EnableItem(dialog, 19, enabled)
        vs.SetBooleanItem(dialog, 30, enabled)
        vs.SetBooleanItem(dialog, 32, enabled)
        vs.EnableItem(dialog, 30, False)
        vs.EnableItem(dialog, 32, False)
        name = str(vs.GetItemText(dialog, 21) or "").strip()
        vs.SetItemText(dialog, 29, point_output.class_3d(name) if name else "Bitte 2D-Punktklasse eingeben")

    def handler(item, _data):
        if item == INIT_EVENT:
            vs.AddChoice(dialog, 12, "Nur 2D (vollständige Plandarstellung)", 0)
            vs.AddChoice(dialog, 12, "2D + zusätzliche 3D-Punkte und Linien", 1)
            vs.SelectChoice(dialog, 12, int(value["mode"] == "3d"), True)
            _init_symbol_resource(dialog, 14, resource_2d, value["symbol"])
            _init_symbol_resource(dialog, 26, resource_3d, value["symbol_3d"])
            vs.SetBooleanItem(dialog, 33, bool(value["symbol"]))
            vs.SetBooleanItem(dialog, 34, bool(value["symbol_3d"]))
            vs.EnableItem(dialog, 14, bool(value["symbol"]))
            vs.EnableItem(dialog, 26, bool(value["symbol_3d"]) and value["mode"] == "3d")
            vs.SetBooleanItem(dialog, 30, value["terrain_modifier"])
            vs.SetBooleanItem(dialog, 32, value["point_terrain_modifier"])
            update()
        elif item in (12, 21):
            update()
        elif item == 33:
            vs.EnableItem(dialog, 14, bool(vs.GetBooleanItem(dialog, 33)))
        elif item == 34:
            vs.EnableItem(dialog, 26, bool(vs.GetBooleanItem(dialog, 34)) and
                          _choice_index(dialog, 12) == 1)
        elif item == 1:
            try:
                result["value"] = point_output.options(dict(
                    schema=4,
                    mode="3d" if _choice_index(dialog, 12) == 1 else "2d",
                    symbol=_selected_symbol(
                        resource_2d, bool(vs.GetBooleanItem(dialog, 33)), "2D-Punktsymbol"),
                    symbol_3d=_selected_symbol(
                        resource_3d,
                        bool(vs.GetBooleanItem(dialog, 34)) and _choice_index(dialog, 12) == 1,
                        "3D-/Hybrid-Punktsymbol"),
                    scale=_float(dialog, 16, "Symbolfaktor"),
                    point_class=vs.GetItemText(dialog, 21), line_class=value["line_class"],
                    terrain_modifier=vs.GetBooleanItem(dialog, 30),
                    point_terrain_modifier=vs.GetBooleanItem(dialog, 32),
                    curve_tolerance_mm=_float(dialog, 19, "Bogenabweichung")))
            except (ValueError, IndexError, TypeError) as error:
                vw_adapter.alert(error)
                return -1
        return item
    return result["value"] if _run(dialog, handler) == 1 else None


def terrain_dialog():
    dialog = vs.CreateResizableLayout(_title("PD Gefälle-Tool – Geländedaten"), True,
                                      "Bereitstellen", "Abbrechen", True, True)
    vs.CreateStyledStatic(dialog, 10, "GELÄNDEMODELL  |  Ausgangsdaten", -1, TITLE_STYLE)
    vs.CreatePullDownMenu(dialog, 11, 48)
    vs.CreateStaticText(dialog, 12,
                        "Zuerst eine oder mehrere 3D-Gefällegruppen markieren. "
                        "Die Daten werden ungruppiert auf einer neuen GEF-Geländedaten-Ebene "
                        "erstellt und markiert. Gemeinsame Höhenpunkte werden nur einmal übernommen. "
                        "Danach die markierten Daten mit Vectorworks prüfen und ein Geländemodell daraus erstellen. "
                        "Dies ist eine Momentaufnahme; bestehende Geländemodelle werden nicht verändert.", 68)
    vs.SetFirstLayoutItem(dialog, 10)
    vs.SetBelowItem(dialog, 10, 11, 0, 6)
    vs.SetBelowItem(dialog, 11, 12, 0, 6)
    result = {"kind": None}

    def handler(item, _data):
        if item == INIT_EVENT:
            vs.AddChoice(dialog, 11, "Nur Höhenpunkte (3D-Punkte)", 0)
            vs.AddChoice(dialog, 11, "Nur Verbindungslinien (offene 3D-Polygone)", 1)
            vs.SelectChoice(dialog, 11, 0, True)
        elif item == 1:
            result["kind"] = "lines" if _choice_index(dialog, 11) == 1 else "points"
        return item
    return result["kind"] if _run(dialog, handler) == 1 else None
