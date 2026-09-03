# -*- coding: utf-8 -*-
"""Task-oriented native dialogs for utility routes."""
from __future__ import absolute_import

import copy

import vs

from . import core
from . import __version__


INIT = 12255
TITLE_STYLE = 213
MANUFACTURER = "manufactured by Dirk D."


def _title(value):
    return "%s | v%s | %s" % (value, __version__, MANUFACTURER)


def _right_side_position(dialog, preferred_size=None):
    """Keep modal Python dialogs compact beside Vectorworks' right palettes."""
    try:
        screen = vs.GetScreen()
        if not isinstance(screen, (tuple, list)) or len(screen) != 4:
            return
        left, top, right, bottom = (int(value) for value in screen)
        screen_width = max(1, right - left)
        screen_height = max(1, bottom - top)
        max_width = max(1, screen_width - 24)
        max_height = max(1, screen_height - 48)
        minimum_width = min(320, max_width)
        minimum_height = min(240, max_height)
        if preferred_size:
            vs.SetLayoutDialogSize(
                dialog,
                min(max_width, max(minimum_width, int(preferred_size[0]))),
                min(max_height, max(minimum_height, int(preferred_size[1]))))
        size = vs.GetLayoutDialogSize(dialog)
        if not isinstance(size, (tuple, list)) or len(size) != 2:
            return
        width = min(max_width, max(minimum_width, int(size[0])))
        height = min(max_height, max(minimum_height, int(size[1])))
        if (width, height) != (int(size[0]), int(size[1])):
            vs.SetLayoutDialogSize(dialog, width, height)
        palette_width = max(280, min(420, int(screen_width * 0.22)))
        x = max(left + 12, right - palette_width - width - 12)
        y = max(top + 12, min(top + 42, bottom - height - 12))
        vs.SetLayoutDialogPosition(dialog, x, y)
    except (AttributeError, TypeError, ValueError):
        return


def _run(dialog, handler, preferred_size=None):
    if not vs.VerifyLayout(dialog):
        raise core.UtilityError("Leitungsdialog konnte nicht aufgebaut werden.")
    _right_side_position(dialog, preferred_size)

    def positioned_handler(item, data):
        result = handler(item, data)
        if item == INIT:
            _right_side_position(dialog, preferred_size)
        return result

    return vs.RunLayoutDialog(dialog, positioned_handler)


def _choice(dialog, item):
    index = int(vs.GetSelectedChoiceIndex(dialog, item, 0))
    if index < 0:
        raise core.UtilityError("Bitte einen Listeneintrag auswählen.")
    return index


def _float(dialog, item, label):
    return core.number(str(vs.GetItemText(dialog, item) or "").strip().replace(",", "."), label)


def _height_text(value):
    """Format a visible elevation without rounding the model value."""
    return ("%.2f" % float(value)).replace(".", ",")


def _text(dialog, item):
    return str(vs.GetItemText(dialog, item) or "").strip()


def _selected(dialog, item):
    return bool(vs.GetBooleanItem(dialog, item))


def _line_type_choice(dialog, item, fallback):
    try:
        value = vs.GetLineTypeChoice(dialog, item)
        return int(fallback if value is None else value)
    except (AttributeError, TypeError, ValueError):
        return int(fallback)


def home_dialog(source_count, managed_count):
    dialog = vs.CreateResizableLayout(
        _title("PD Leitungstool"), True, "Weiter", "Zurück", True, True)
    vs.CreateStyledStatic(dialog, 10, "LEITUNGEN  |  Versorgungstrassen in 2D und 3D", -1, TITLE_STYLE)
    vs.CreateStaticText(
        dialog, 11,
        "Eine Linie/Polylinie markieren oder frei zeichnen. Die gezeichnete Achse kann linke Kante, "
        "Trassenmitte oder rechte Kante sein. Doppelklick beendet die Punktfolge.", 80)
    vs.CreateStaticText(dialog, 12, "Was möchten Sie tun?", -1)
    vs.CreatePullDownMenu(dialog, 13, 58)
    vs.CreateStaticText(dialog, 14,
                        "%d Ausgangsstrecke(n), %d Leitungstrasse(n) markiert." %
                        (source_count, managed_count), 74)
    vs.SetFirstLayoutItem(dialog, 10)
    vs.SetBelowItem(dialog, 10, 11, 0, 6)
    vs.SetBelowItem(dialog, 11, 12, 0, 8)
    vs.SetRightItem(dialog, 12, 13, 8, 0)
    vs.SetBelowItem(dialog, 12, 14, 0, 7)
    actions = []
    if source_count:
        actions.append(("Markierte Strecke(n) in Leitungstrasse umwandeln", "sources"))
    if managed_count == 1:
        actions.extend((("Markierte Leitungstrasse bearbeiten", "edit"),
                        ("Höhenkette der markierten Leitung bearbeiten", "chain"),
                        ("Markierte Leitung unter Geländemodell aktualisieren", "terrain")))
    if managed_count:
        actions.append(("Markierte Leitungstrasse(n) löschen …", "delete"))
    actions.extend((("Neue Leitungstrasse durch Punkte zeichnen", "draw"),
                     ("Alle Leitungstrassen prüfen und Längen ausgeben", "validate"),
                     ("Massenermittlung, Kanal-Erdmassen und Excel …", "quantities"),
                     ("Leitungsstandards und Klassen einstellen", "settings")))
    result = {"value": None}

    def handler(item, _data):
        if item == INIT:
            for index, row in enumerate(actions):
                vs.AddChoice(dialog, 13, row[0], index)
            vs.SelectChoice(dialog, 13, 0, True)
        elif item == 1:
            result["value"] = actions[_choice(dialog, 13)][1]
        return item
    return result["value"] if _run(dialog, handler) == 1 else None


def route_dialog(preferences, initial=None, source_count=0):
    current = copy.deepcopy(initial or {})
    editing = bool(initial)
    types = list(preferences["types"])
    materials = list(preferences["materials"])
    references = (("Gezeichnete Achse = linke Trassenseite", "left"),
                  ("Gezeichnete Achse = Trassenmitte", "center"),
                  ("Gezeichnete Achse = rechte Trassenseite", "right"))
    graphics = (("Einliniengrafik", "single_line"),
                ("Gefüllte Doppellinie mit gestrichelter Achslinie", "double_line"))
    elevation_modes = (("Feste Höhe / Gefälle", "fixed"),
                       ("DGM-Überdeckung, geprüft in Abständen bis 1,00 m", "surface_cover"))
    dialog = vs.CreateResizableLayout(
        _title("Leitungstrasse bearbeiten" if editing else "Leitungstrasse anlegen"),
        True, "Übernehmen" if editing else "Zeichnen", "Abbrechen", True, True)
    vs.CreateStyledStatic(dialog, 10, "LEITUNGSTRASSE  |  System und Geometrie", -1, TITLE_STYLE)
    vs.CreateStaticText(dialog, 11,
                        ("Bestehende Trasse ändern; die Höhenkette bleibt erhalten, sofern Anzahl und Punkte gleich bleiben."
                         if editing else "%d markierte Ausgangsstrecke(n). Danach wird eine verknüpfte Trasse erzeugt." % source_count),
                        82)
    labels = (
        (12, "Leitungstyp:"), (14, "Trassenname:"), (16, "Material:"),
        (18, "Anzahl paralleler Leitungen:"), (20, "Nennweiten DN [mm] (; getrennt):"),
        (22, "Außendurchmesser [mm] (; getrennt):"), (24, "Leitungsabstand [m]:"),
        (26, "Lage der gezeichneten Achse:"), (28, "Darstellung:"),
        (30, "Linienart / Achslinienart:"), (33, "Ausrundungsradius [m]:"),
        (40, "Höhenbezug:"), (42, "Anfangshöhe Leitungsachse [m]:"),
        (44, "Gefälle [%] (Vorgabe 0):"), (46, "Überdeckung über Außenkante [m]:"),
        (50, "Beschriftungstext (| = Zeilenumbruch):"), (52, "Beschriftungsabstand [m]:"),
        (58, "Schriftart / Größe [pt]:"), (75, "Drehung [°]:"),
        (77, "Textaufteilung:"))
    for item, label in labels:
        vs.CreateStaticText(dialog, item, label, -1)
    for item, width in ((13, 26), (17, 26), (27, 46), (29, 34), (41, 46)):
        vs.CreatePullDownMenu(dialog, item, width)
    vs.CreateLineStylePopup(dialog, 31)
    vs.CreateLineStylePopup(dialog, 32)
    defaults = {
        15: current.get("route_name", ""),
        19: current.get("count", preferences["count"]),
        21: ";".join(str(value) for value in current.get("dns_mm", (preferences["default_dn_mm"],))),
        23: ";".join(str(value) for value in current.get(
            "outside_diameters_mm", current.get("dns_mm", (preferences["default_dn_mm"],)))),
        25: current.get("spacing_m", preferences["spacing_m"]),
        34: current.get("fillet_radius_m", preferences["fillet_radius_m"]),
        43: current.get("start_height_m", preferences["start_height_m"]),
        45: current.get("slope_percent", preferences["slope_percent"]),
        47: current.get("cover_depth_m", preferences["cover_depth_m"]),
        51: current.get("label_text", preferences["label_text"]),
        53: current.get("label_interval_m", preferences["label_interval_m"]),
        59: current.get("font_name", preferences["font_name"]),
        60: current.get("font_size_pt", preferences["font_size_pt"]),
        76: current.get("label_rotation_deg", preferences["label_rotation_deg"]),
    }
    for item, value in defaults.items():
        text = _height_text(value) if item == 43 else str(value).replace(".", ",")
        vs.CreateEditText(dialog, item, text, 30 if item in (15, 21, 23, 51) else 14)
    vs.CreateCheckBox(dialog, 35, "Winkelpunkte mit dem angegebenen Radius ausrunden")
    vs.CreateCheckBox(dialog, 36, "Formstücke an Winkelpunkten anzeigen")
    vs.CreateCheckBox(dialog, 37, "Winkel der Formstücke beschriften")
    vs.CreateCheckBox(dialog, 48, "Punkthöhen in der Zeichnung anzeigen")
    vs.CreateCheckBox(dialog, 49, "Zusätzliche 3D-Leitungen erzeugen")
    vs.CreateCheckBox(dialog, 54, "Regelmäßig beschriften")
    vs.CreateCheckBox(dialog, 55, "Textrahmen")
    vs.CreateCheckBox(dialog, 56, "Textfüllung")
    vs.CreateCheckBox(dialog, 57, "Höhen aus Anfangshöhe/Gefälle bzw. DGM vollständig neu berechnen")
    vs.CreateCheckBox(dialog, 68, "Außendurchmesser ausdrücklich als Produktmaß bestätigt")
    vs.CreateCheckBox(dialog, 73, "Fettdruck")
    vs.CreateCheckBox(dialog, 74, "Unterstrichen")
    vs.CreatePullDownMenu(dialog, 78, 28)
    vs.CreateStaticText(dialog, 61, "Leitungsfarbe:", -1)
    vs.CreateColorPopup(dialog, 62, 18)
    vs.CreateStaticText(dialog, 63, "Text / Rahmen / Füllung:", -1)
    vs.CreateColorPopup(dialog, 64, 14)
    vs.CreateColorPopup(dialog, 65, 14)
    vs.CreateColorPopup(dialog, 66, 14)
    vs.CreateStaticText(dialog, 67,
                        "Hinweis: Für DGM-Überdeckung ist der reale Außendurchmesser erforderlich. "
                        "DN wird nicht als Wandstärken- oder Produktmaß geraten.", 82)
    vs.CreateTabControl(dialog, 69)
    vs.CreateGroupBox(dialog, 70, "System + Darstellung", False)
    vs.CreateGroupBox(dialog, 71, "Höhen + DGM", False)
    vs.CreateGroupBox(dialog, 72, "Beschriftung", False)
    vs.SetFirstLayoutItem(dialog, 10)
    vs.SetBelowItem(dialog, 10, 11, 0, 5)
    vs.SetBelowItem(dialog, 11, 69, 0, 8)
    vs.SetFirstGroupItem(dialog, 70, 12)
    previous = None
    for label, field in ((12, 13), (14, 15), (16, 17), (18, 19), (20, 21),
                         (22, 23), (24, 25), (26, 27), (28, 29), (30, 31)):
        if previous is not None:
            vs.SetBelowItem(dialog, previous, label, 0, 5)
        vs.SetRightItem(dialog, label, field, 8, 0)
        previous = label
        if label == 22:
            vs.SetBelowItem(dialog, label, 68, 0, 4)
            previous = 68
        if label == 30:
            vs.SetRightItem(dialog, field, 32, 5, 0)
    vs.SetBelowItem(dialog, previous, 33, 0, 5)
    vs.SetRightItem(dialog, 33, 34, 8, 0)
    previous = 33
    for item in (35, 36, 37):
        vs.SetBelowItem(dialog, previous, item, 0, 4)
        previous = item
    vs.SetBelowItem(dialog, previous, 61, 0, 5)
    vs.SetRightItem(dialog, 61, 62, 8, 0)
    vs.SetFirstGroupItem(dialog, 71, 40)
    previous = None
    for label, field in ((40, 41), (42, 43), (44, 45), (46, 47)):
        if previous is not None:
            vs.SetBelowItem(dialog, previous, label, 0, 5)
        vs.SetRightItem(dialog, label, field, 8, 0)
        previous = label
    for item in (48, 49, 57):
        vs.SetBelowItem(dialog, previous, item, 0, 4)
        previous = item
    vs.SetBelowItem(dialog, previous, 67, 0, 6)
    vs.SetFirstGroupItem(dialog, 72, 50)
    previous = None
    for label, field in ((50, 51), (52, 53), (58, 59), (75, 76), (77, 78)):
        if previous is not None:
            vs.SetBelowItem(dialog, previous, label, 0, 5)
        vs.SetRightItem(dialog, label, field, 8, 0)
        previous = label
        if label == 58:
            vs.SetRightItem(dialog, field, 60, 5, 0)
    for item in (54, 55, 56, 73, 74):
        vs.SetBelowItem(dialog, previous, item, 0, 4)
        previous = item
    vs.SetBelowItem(dialog, previous, 63, 0, 5)
    vs.SetRightItem(dialog, 63, 64, 8, 0)
    vs.SetRightItem(dialog, 64, 65, 5, 0)
    vs.SetRightItem(dialog, 65, 66, 5, 0)
    for pane in (70, 71, 72):
        vs.CreateTabPane(dialog, 69, pane)
    vs.SetEdgeBinding(dialog, 11, True, True, True, False)
    vs.SetEdgeBinding(dialog, 69, True, True, True, True)
    result = {"value": None}

    def select(control, rows, value):
        values = [row[1] if isinstance(row, tuple) else row for row in rows]
        vs.SelectChoice(dialog, control, values.index(value) if value in values else 0, True)

    def handler(item, _data):
        if item == INIT:
            label_layouts = (("Eine Zeile", "one_line"), ("Zwei Zeilen", "two_line"))
            for control, rows in ((13, types), (17, materials),
                                  (27, references), (29, graphics), (41, elevation_modes),
                                  (78, label_layouts)):
                for index, row in enumerate(rows):
                    vs.AddChoice(dialog, control, row[0] if isinstance(row, tuple) else row, index)
            type_value = current.get("utility_type", preferences["default_type"])
            select(13, types, type_value)
            select(17, materials, current.get("material", preferences["default_material"]))
            select(27, references, current.get("axis_reference", preferences["axis_reference"]))
            select(29, graphics, current.get("graphics_mode", preferences["graphics_mode"]))
            select(41, elevation_modes, current.get("elevation_mode", preferences["elevation_mode"]))
            select(78, label_layouts, current.get("label_layout", preferences["label_layout"]))
            vs.SetLineTypeChoice(dialog, 31, int(current.get("line_type", preferences["line_type"])))
            vs.SetLineTypeChoice(
                dialog, 32, int(current.get("axis_line_type", preferences["axis_line_type"])))
            for control, key in ((35, "round_corners"), (36, "show_fittings"),
                                 (37, "label_bend_angles"), (48, "show_heights"),
                                 (49, "draw_3d"), (54, "regular_label"),
                                 (55, "label_frame"), (56, "label_fill"),
                                 (73, "label_bold"), (74, "label_underline")):
                vs.SetBooleanItem(dialog, control, bool(current.get(key, preferences[key])))
            vs.SetBooleanItem(
                dialog, 68, bool(current.get("outside_diameters_explicit", False)))
            vs.SetBooleanItem(dialog, 57, not editing)
            color = current.get("line_color", preferences["colors"][type_value])
            for control, value in ((62, color),
                                   (64, current.get("text_color", preferences["text_color"])),
                                   (65, current.get("frame_color", preferences["frame_color"])),
                                   (66, current.get("fill_color", preferences["fill_color"]))):
                vs.SetColorChoice(dialog, control, vs.RGBToColorIndex(*value))
        elif item == 13 and not editing:
            chosen = types[_choice(dialog, 13)]
            vs.SetColorChoice(dialog, 62, vs.RGBToColorIndex(*preferences["colors"][chosen]))
        elif item == 1:
            count = core.integer(_text(dialog, 19), "Leitungsanzahl", 1, 50)
            dns = core.nominal_diameters(_text(dialog, 21), count)
            outside, outside_explicit = core.outside_diameters(
                _text(dialog, 23), dns, count, explicit=_selected(dialog, 68))
            result["value"] = dict(
                current,
                utility_type=types[_choice(dialog, 13)], route_name=_text(dialog, 15),
                description=current.get("description", ""),
                material=materials[_choice(dialog, 17)], count=count,
                dns_mm=dns, outside_diameters_mm=outside,
                outside_diameters_explicit=outside_explicit,
                spacing_m=_float(dialog, 25, "Leitungsabstand"),
                axis_reference=references[_choice(dialog, 27)][1],
                graphics_mode=graphics[_choice(dialog, 29)][1],
                line_type=_line_type_choice(
                    dialog, 31, current.get("line_type", preferences["line_type"])),
                axis_line_type=_line_type_choice(
                    dialog, 32, current.get("axis_line_type", preferences["axis_line_type"])),
                fillet_radius_m=_float(dialog, 34, "Ausrundungsradius"),
                round_corners=_selected(dialog, 35), show_fittings=_selected(dialog, 36),
                label_bend_angles=_selected(dialog, 37),
                elevation_mode=elevation_modes[_choice(dialog, 41)][1],
                start_height_m=_float(dialog, 43, "Anfangshöhe"),
                slope_percent=_float(dialog, 45, "Gefälle"),
                cover_depth_m=_float(dialog, 47, "Überdeckung"),
                surface_tin_type=current.get("surface_tin_type", preferences["surface_tin_type"]),
                surface_model_name=current.get("surface_model_name", ""),
                show_heights=_selected(dialog, 48), draw_3d=_selected(dialog, 49),
                label_text=_text(dialog, 51), label_interval_m=_float(dialog, 53, "Beschriftungsabstand"),
                regular_label=_selected(dialog, 54), label_frame=_selected(dialog, 55),
                label_fill=_selected(dialog, 56), font_name=_text(dialog, 59),
                font_size_pt=_float(dialog, 60, "Schriftgröße"),
                label_bold=_selected(dialog, 73), label_underline=_selected(dialog, 74),
                label_rotation_deg=_float(dialog, 76, "Beschriftungsdrehung"),
                label_layout=label_layouts[_choice(dialog, 78)][1],
                line_color=list(vs.ColorIndexToRGB(vs.GetColorChoice(dialog, 62))),
                text_color=list(vs.ColorIndexToRGB(vs.GetColorChoice(dialog, 64))),
                frame_color=list(vs.ColorIndexToRGB(vs.GetColorChoice(dialog, 65))),
                fill_color=list(vs.ColorIndexToRGB(vs.GetColorChoice(dialog, 66))),
                _rebuild_heights=_selected(dialog, 57))
        return item
    return result["value"] if _run(dialog, handler, (620, 580)) == 1 else None


def height_chain_dialog(route):
    current = core.validate_route(route)
    rows = [(line_index, point_index,
             "Leitung %d · Punkt %d · %s m" %
             (line_index + 1, point_index + 1,
              _height_text(current["route_heights_m"][line_index][point_index])))
            for line_index in range(current["count"])
            for point_index in range(len(current["points_m"]))]
    dialog = vs.CreateResizableLayout(
        _title("Leitung – Höhenkette bearbeiten"), True,
        "Alle Änderungen übernehmen", "Abbrechen", True, True)
    vs.CreateStyledStatic(dialog, 10, "HÖHENKETTE  |  Jede Einzelleitung separat", -1, TITLE_STYLE)
    vs.CreateStaticText(dialog, 11,
                        "Punkt wählen, neue Achshöhe eingeben und vormerken. "
                        "Weitere Punkte können anschließend im selben Dialog bearbeitet werden.", 80)
    vs.CreateStaticText(dialog, 12, "Leitung / Punkt:", -1)
    vs.CreatePullDownMenu(dialog, 13, 46)
    vs.CreateStaticText(dialog, 14, "Achshöhe [m]:", -1)
    vs.CreateEditText(dialog, 15, "", 18)
    vs.CreatePushButton(dialog, 16, "Änderung vormerken")
    vs.CreateStaticText(dialog, 17, "Noch keine Änderung vorgemerkt.", 72)
    vs.SetFirstLayoutItem(dialog, 10)
    vs.SetBelowItem(dialog, 10, 11, 0, 6)
    vs.SetBelowItem(dialog, 11, 12, 0, 7)
    vs.SetRightItem(dialog, 12, 13, 8, 0)
    vs.SetBelowItem(dialog, 12, 14, 0, 6)
    vs.SetRightItem(dialog, 14, 15, 8, 0)
    vs.SetBelowItem(dialog, 14, 16, 0, 7)
    vs.SetBelowItem(dialog, 16, 17, 0, 5)
    result = {"value": None, "changes": 0}

    def show():
        line_index, point_index, _label = rows[_choice(dialog, 13)]
        value = current["route_heights_m"][line_index][point_index]
        vs.SetItemText(dialog, 15, _height_text(value))

    def stage():
        line_index, point_index, _label = rows[_choice(dialog, 13)]
        changed = core.update_height(
            current, point_index, _float(dialog, 15, "Achshöhe"), line_index)
        current.clear()
        current.update(changed)
        result["changes"] += 1
        vs.SetItemText(dialog, 17, "%d Änderung(en) vorgemerkt." % result["changes"])

    def handler(item, _data):
        if item == INIT:
            for index, row in enumerate(rows):
                vs.AddChoice(dialog, 13, row[2], index)
            vs.SelectChoice(dialog, 13, 0, True)
            show()
        elif item == 13:
            show()
        elif item == 16:
            stage()
        elif item == 1:
            stage()
            result["value"] = current
        return item
    return result["value"] if _run(dialog, handler) == 1 else None


def confirm_delete(count):
    return bool(vs.YNDialog("%d markierte Leitungstrasse(n) wirklich löschen?" % int(count)))


def preferences_dialog(preferences):
    current = copy.deepcopy(preferences)
    dialog = vs.CreateResizableLayout(
        _title("Leitung – Voreinstellungen"), True, "Speichern", "Abbrechen", True, True)
    vs.CreateStyledStatic(dialog, 10, "STANDARDS  |  Neue Leitungstrassen", -1, TITLE_STYLE)
    labels = ((11, "Standardtyp:"), (13, "Standard-DN [mm]:"),
              (15, "Standardmaterial:"), (17, "Standardanzahl:"),
              (19, "Standardabstand [m]:"), (21, "Klassenpräfix:"),
              (23, "Textklasse:"), (25, "Farben TW / Strom / Wärme / Gas:"),
              (31, "Leitungstypen (; getrennt):"),
              (33, "Materialien (; getrennt):"))
    for item, value in labels:
        vs.CreateStaticText(dialog, item, value, -1)
    vs.CreatePullDownMenu(dialog, 12, 28)
    vs.CreateEditText(dialog, 14, str(current["default_dn_mm"]), 14)
    vs.CreatePullDownMenu(dialog, 16, 28)
    vs.CreateEditText(dialog, 18, str(current["count"]), 14)
    vs.CreateEditText(dialog, 20, str(current["spacing_m"]).replace(".", ","), 14)
    vs.CreateEditText(dialog, 22, current["class_prefix"], 30)
    vs.CreateEditText(dialog, 24, current["text_class"], 30)
    vs.CreateEditText(dialog, 32, "; ".join(current["types"]), 52)
    vs.CreateEditText(dialog, 34, "; ".join(current["materials"]), 52)
    for item in (26, 27, 28, 29):
        vs.CreateColorPopup(dialog, item, 15)
    vs.CreateStaticText(dialog, 30,
                        "Die Auswahlwerte bleiben in jeder Trasse gespeichert. Änderungen an Standards "
                        "überschreiben vorhandene Objekte nicht.", 76)
    vs.SetFirstLayoutItem(dialog, 10)
    previous = 10
    for label, field in ((11, 12), (13, 14), (15, 16), (17, 18),
                          (19, 20), (21, 22), (23, 24), (25, 26),
                          (31, 32), (33, 34)):
        vs.SetBelowItem(dialog, previous, label, 0, 6)
        vs.SetRightItem(dialog, label, field, 8, 0)
        previous = label
        if label == 25:
            vs.SetRightItem(dialog, 26, 27, 5, 0)
            vs.SetRightItem(dialog, 27, 28, 5, 0)
            vs.SetRightItem(dialog, 28, 29, 5, 0)
    vs.SetBelowItem(dialog, previous, 30, 0, 7)
    result = {"value": None}

    def handler(item, _data):
        if item == INIT:
            for index, value in enumerate(current["types"]):
                vs.AddChoice(dialog, 12, value, index)
            for index, value in enumerate(current["materials"]):
                vs.AddChoice(dialog, 16, value, index)
            vs.SelectChoice(dialog, 12, current["types"].index(current["default_type"]), True)
            vs.SelectChoice(dialog, 16, current["materials"].index(current["default_material"]), True)
            for control, utility_type in zip((26, 27, 28, 29), core.UTILITY_TYPES):
                vs.SetColorChoice(dialog, control, vs.RGBToColorIndex(*current["colors"][utility_type]))
        elif item == 1:
            types = list(dict.fromkeys(
                core.utility_type(part.strip())
                for part in _text(dialog, 32).split(";") if part.strip()))
            materials = list(dict.fromkeys(
                core.material(part.strip())
                for part in _text(dialog, 34).split(";") if part.strip()))
            if not types or not materials:
                raise core.UtilityError(
                    "Mindestens ein Leitungstyp und ein Material sind erforderlich.")
            selected_type = current["types"][_choice(dialog, 12)]
            selected_material = current["materials"][_choice(dialog, 16)]
            if selected_type not in types:
                types.append(selected_type)
            if selected_material not in materials:
                materials.append(selected_material)
            value = dict(current)
            colors = dict(current["colors"])
            colors.update({
                utility_type: list(vs.ColorIndexToRGB(vs.GetColorChoice(dialog, control)))
                for control, utility_type in zip((26, 27, 28, 29), core.UTILITY_TYPES)})
            value.update(
                types=types, materials=materials, default_type=selected_type,
                default_dn_mm=core.integer(_text(dialog, 14), "Standard-DN", 1, 10000),
                default_material=selected_material,
                count=core.integer(_text(dialog, 18), "Standardanzahl", 1, 50),
                spacing_m=_float(dialog, 20, "Standardabstand"),
                class_prefix=_text(dialog, 22), text_class=_text(dialog, 24),
                colors=colors)
            result["value"] = value
        return item
    return result["value"] if _run(dialog, handler) == 1 else None
