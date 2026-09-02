# -*- coding: utf-8 -*-
"""Native staged dialogs for channel-network creation and editing."""
from __future__ import absolute_import

import copy
import re
import unicodedata

import vs

from . import core
from . import settings
from . import VERSION


INIT = 12255
TITLE_STYLE = 213
MANUFACTURER = "manufactured by Dirk D."
SYMBOL_DEFINITION_TYPE = 16
LIBRARIES_FOLDER = 13
COVER_PLACEMENTS = (("Automatisch im größten freien Kanalwinkel", "auto"),
                    ("Mittig im Schacht", "center"))


def _title(value):
    return "%s | v%s | %s" % (value, VERSION, MANUFACTURER)


def _right_side_position(dialog, preferred_size=None):
    """Place native Python dialogs beside the docked Object Info palette.

    Vectorworks' Python layout API creates modal dialogs, not SDK palettes.
    Keeping these narrow and at the right edge gives the requested palette-
    like workflow while the persistent command buttons remain in the OIP.
    """
    try:
        if preferred_size:
            vs.SetLayoutDialogSize(dialog, int(preferred_size[0]), int(preferred_size[1]))
        size = vs.GetLayoutDialogSize(dialog)
        screen = vs.GetScreen()
        if (not isinstance(size, (tuple, list)) or len(size) != 2 or
                not isinstance(screen, (tuple, list)) or len(screen) != 4):
            return
        width, height = max(320, int(size[0])), max(240, int(size[1]))
        left, top, right, bottom = (int(value) for value in screen)
        screen_width = max(1, right - left)
        # Reserve the normal width of Vectorworks' docked right palettes.
        palette_width = max(280, min(420, int(screen_width * 0.22)))
        x = max(left + 12, right - palette_width - width - 12)
        y = max(top + 42, min(top + 72, bottom - height - 24))
        vs.SetLayoutDialogPosition(dialog, x, y)
    except (AttributeError, TypeError, ValueError):
        # Layout and screen queries are presentation-only. A missing value
        # must not block drawing or editing in a non-standard workspace.
        return


def _run(dialog, handler, preferred_size=None):
    if not vs.VerifyLayout(dialog):
        raise core.SewerError("Kanaldialog konnte nicht aufgebaut werden.")
    # Position once before the window is shown.  Repeating this on INIT keeps
    # the placement stable when Vectorworks recalculates the native layout.
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
        raise core.SewerError("Bitte einen Listeneintrag auswählen.")
    return index


def _float(dialog, item, label):
    return core.number(str(vs.GetItemText(dialog, item) or "").strip().replace(",", "."), label)


def _selected(dialog, item):
    return bool(vs.GetBooleanItem(dialog, item))


def _line_type_choice(dialog, item, fallback):
    """Read a native line-style popup; keep a deterministic test fallback."""
    try:
        value = vs.GetLineTypeChoice(dialog, item)
        return int(fallback if value is None else value)
    except (AttributeError, TypeError, ValueError):
        return int(fallback)


def _shaft_name_text(dialog, item, fallback):
    raw = vs.GetItemText(dialog, item)
    if isinstance(raw, (tuple, list)):
        raw = next((value for value in reversed(raw) if isinstance(value, str)), "")
    value = unicodedata.normalize("NFKC", str(raw or ""))
    value = "".join(character for character in value
                    if unicodedata.category(character) != "Cf")
    value = re.sub(r"\s+", " ", value).strip()
    return value or str(fallback)


def _init_cover_resource(dialog, control, unique_id, selected_name):
    """Bind a Vectorworks 2026 resource popup to document/library symbols."""
    vs.ResList_Init(unique_id, SYMBOL_DEFINITION_TYPE)
    vs.ResList_AddCont1(unique_id, LIBRARIES_FOLDER, "")
    vs.ResList_DlgInit(unique_id, dialog, control)
    if selected_name:
        vs.ResList_SetSel(unique_id, selected_name)


def _cover_symbol(unique_id, enabled):
    if not enabled:
        return ""
    if not vs.ResList_IsSelValid(unique_id):
        raise core.SewerError("Bitte ein gültiges 2D-Schachtdeckelsymbol auswählen.")
    selected = str(vs.ResList_GetSel(unique_id) or "").strip()
    handle = vs.GetObject(selected) if vs.ResList_GetSelIsDoc(unique_id) else None
    if not handle:
        handle = vs.ResList_ImportItemN(unique_id, 2)
    name = str(vs.GetName(handle) or selected).strip() if handle else ""
    if not name or not vs.GetObject(name):
        raise core.SewerError("Das gewählte Schachtdeckelsymbol konnte nicht importiert werden.")
    return name


def home_dialog(source_count, managed_count, managed_role=None, selected_shaft_count=0):
    dialog = vs.CreateResizableLayout(
        _title("PD Kanaltool"), True, "Weiter", "Abbrechen", True, True)
    vs.CreateStyledStatic(dialog, 10, "KANALANLAGE  |  Rohre, Schächte und Beschriftungen", -1, TITLE_STYLE)
    vs.CreateStaticText(dialog, 11,
                        "Aus vorhandenen Linien: eine oder mehrere Linien, offene Polylinien oder Polygone markieren. "
                        "Neu zeichnen: beliebig viele Punkte, Abschluss mit Doppelklick. Rohrhöhen werden als Sohlhöhen geführt.", 78)
    vs.CreateStaticText(dialog, 12, "Aktion:", -1)
    vs.CreatePullDownMenu(dialog, 13, 52)
    vs.CreateStaticText(dialog, 14,
                        "%d geeignete Ausgangsstrecke(n), %d Kanalobjekt(e) markiert." %
                        (source_count, managed_count), 72)
    connectable = managed_count == 1 and managed_role in ("sewer_pipe", "sewer_shaft")
    if connectable:
        selection = "HALTUNG" if managed_role == "sewer_pipe" else "SCHACHT"
        vs.CreateStyledStatic(
            dialog, 15, "SCHNELLSTART  |  NEUEN KANALSTRANG AN MARKIERTE %s ANSCHLIESSEN" % selection,
            -1, TITLE_STYLE)
        vs.CreateStaticText(
            dialog, 16,
            ("1. Unten 'Weiter' wählen und Rohrdaten bestätigen.  2. Anschlusspunkt auf der Haltung anklicken.  "
             "3. Weitere Haltungen zeichnen; Doppelklick beendet den neuen Strang."
             if managed_role == "sewer_pipe" else
             "1. Unten 'Weiter' wählen und Rohrdaten bestätigen.  2. Vom markierten Schacht aus weitere "
             "Haltungen zeichnen; Doppelklick beendet den neuen Strang."), 82)
    vs.SetFirstLayoutItem(dialog, 10)
    previous = 10
    if connectable:
        vs.SetBelowItem(dialog, previous, 15, 0, 6)
        vs.SetBelowItem(dialog, 15, 16, 0, 4)
        previous = 16
    vs.SetBelowItem(dialog, previous, 11, 0, 6)
    vs.SetBelowItem(dialog, 11, 12, 0, 8)
    vs.SetRightItem(dialog, 12, 13, 8, 0)
    vs.SetBelowItem(dialog, 12, 14, 0, 7)
    # The two creation paths are deliberately stable and always visible.  A
    # missing source selection is reported after choosing the conversion
    # command instead of hiding the command from the user.
    actions = [
        ("Neue Kanalanlage durch Punkte zeichnen", "draw"),
        ("Vorhandene Linie, Polylinie oder Polygon in Kanalanlage umwandeln", "sources"),
    ]
    if connectable:
        actions.append((
            ("▶ NEUEN KANALSTRANG AN MARKIERTE HALTUNG ANSCHLIESSEN …"
             if managed_role == "sewer_pipe" else
             "▶ NEUEN KANALSTRANG AN MARKIERTEN SCHACHT ANSCHLIESSEN …"),
            "connect"))
    if managed_count:
        actions.append(("Markierte Kanalobjekte bearbeiten", "edit"))
        actions.append(("Markierte Kanalobjekte löschen …", "delete"))
    if selected_shaft_count:
        actions.append(("Schachtblätter aus markierten Schächten erstellen …", "shaft_sheets"))
    if managed_count == 1:
        if managed_role == "sewer_pipe":
            actions.append(("Schacht in markierte Haltung einsetzen (Leitung darunter entfernen)", "split"))
    if managed_count == 2:
        actions.append(("Zwei geradlinige Kanalstrecken vereinigen", "merge"))
    actions.extend((("Kanalstutzen an Haltung herstellen und Anschlussleitung zeichnen", "stub"),
                    ("Runden Schacht mit Polygon/Polylinie in Sonderschacht umwandeln", "special"),
                    ("Absturz vor einem Schacht anlegen / bearbeiten", "drop"),
                    ("Bodenablauf setzen und vom Ablauf zur Hauptleitung zeichnen", "floor_drain"),
                    ("Hausanschluss vom freien Ende zur Hauptleitung zeichnen", "house"),
                    (("Markierte Schachtdeckel an Geländemodell anpassen"
                      if managed_count else "Alle Schachtdeckel an Geländemodell anpassen"),
                     "terrain_covers"),
                     ("Kanalnetz prüfen", "validate"),
                     ("Massenermittlung, Erdmassen, Verbau und Excel …", "quantities"),
                     ("Farben, DN, Material und Darstellung einstellen", "settings")))
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


def shaft_sheet_dialog(shaft_names, preferences):
    """Collect report metadata once for all selected one-page shaft sheets."""
    names = tuple(str(value) for value in shaft_names)
    if not names:
        raise core.SewerError("Bitte einen oder mehrere Schächte markieren.")
    dialog = vs.CreateResizableLayout(
        _title("Schachtblätter erstellen"), True, "Ausführen", "Abbrechen", True, True)
    vs.CreateStyledStatic(dialog, 10, "SCHACHTBLÄTTER  |  DIN A4 quer", -1, TITLE_STYLE)
    vs.CreateStaticText(
        dialog, 11,
        "%d Schacht/Schächte ausgewählt: %s. Pro Schacht wird genau eine Seite erzeugt." %
        (len(names), ", ".join(names[:8]) + (" …" if len(names) > 8 else "")), 86)
    vs.CreateStaticText(dialog, 12, "Bauvorhaben *:", -1)
    vs.CreateEditText(dialog, 13, preferences.get("sheet_project_name", ""), 48)
    vs.CreateStaticText(dialog, 14, "Kanalart * (Auswahl oder Freitext):", -1)
    vs.CreateEditText(dialog, 15, preferences.get("sheet_channel_type", ""), 48)
    vs.CreateStaticText(dialog, 16, "Bemerkung:", -1)
    vs.CreateEditText(dialog, 17, preferences.get("sheet_comments", ""), 48)
    vs.CreateStaticText(dialog, 18, "Firmenlogo-Datei (PNG/JPG, leer = PD-Logo):", -1)
    vs.CreateEditText(dialog, 19, preferences.get("sheet_logo_path", ""), 48)
    vs.CreateStaticText(dialog, 20, "Höhenangabe:", -1)
    vs.CreatePullDownMenu(dialog, 21, 34)
    vs.CreateStaticText(dialog, 22, "Winkeluhr-Bezug:", -1)
    vs.CreatePullDownMenu(dialog, 23, 42)
    vs.CreateStaticText(dialog, 24, "Plannord-Drehung im Uhrzeigersinn [°]:", -1)
    vs.CreateEditText(
        dialog, 25, str(preferences.get("sheet_north_rotation_deg", 0.0)).replace(".", ","), 16)
    vs.CreateCheckBox(dialog, 26, "Zusätzlich schematischen Schnitt darstellen")
    vs.CreateStaticText(dialog, 27, "Ausgabe:", -1)
    vs.CreatePullDownMenu(dialog, 28, 38)
    vs.CreateStaticText(
        dialog, 29,
        "Die Vorschau wird als verwaltete Layoutebene erzeugt. PDF und Druck verwenden exakt dieselbe "
        "Vektorgeometrie. Fehlende Pflichtdaten werden vor der Ausgabe vollständig gemeldet.", 86)
    vs.SetFirstLayoutItem(dialog, 10)
    vs.SetBelowItem(dialog, 10, 11, 0, 5)
    previous = 11
    for label, field in ((12, 13), (14, 15), (16, 17), (18, 19),
                         (20, 21), (22, 23), (24, 25)):
        vs.SetBelowItem(dialog, previous, label, 0, 6)
        vs.SetRightItem(dialog, label, field, 8, 0)
        previous = label
    vs.SetBelowItem(dialog, previous, 26, 0, 6)
    vs.SetBelowItem(dialog, 26, 27, 0, 6)
    vs.SetRightItem(dialog, 27, 28, 8, 0)
    vs.SetBelowItem(dialog, 27, 29, 0, 6)
    height_modes = (("Absolute Höhen [m]", "absolute"),
                    ("Relative Höhen bezogen auf Schachtsohle", "relative"))
    clock_modes = (("Plannord: 12 Uhr = Plannord", "plan_north"),
                   ("BFR: 12 Uhr = tiefster Ablauf", "deepest_outlet"))
    outputs = (("Vorschau auf Layoutebenen", "preview"),
               ("Gemeinsame mehrseitige PDF-Datei", "pdf"),
               ("Schachtblätter über Druckdialog drucken", "print"))
    result = {"value": None}

    def handler(item, _data):
        if item == INIT:
            for control, rows, selected in (
                    (21, height_modes, preferences.get("sheet_height_mode", "absolute")),
                    (23, clock_modes, preferences.get("sheet_clock_mode", "plan_north")),
                    (28, outputs, "preview")):
                for index, row in enumerate(rows):
                    vs.AddChoice(dialog, control, row[0], index)
                values = [row[1] for row in rows]
                vs.SelectChoice(dialog, control, values.index(selected), True)
            vs.SetBooleanItem(dialog, 26, bool(preferences.get("sheet_include_section", True)))
        elif item == 1:
            project = str(vs.GetItemText(dialog, 13) or "").strip()
            channel = str(vs.GetItemText(dialog, 15) or "").strip()
            if not project or not channel:
                vs.AlrtDialog("Bitte Bauvorhaben und Kanalart vollständig angeben.")
                return -1
            result["value"] = {
                "project_name": project,
                "channel_type": channel,
                "comments": str(vs.GetItemText(dialog, 17) or "").strip(),
                "logo_path": str(vs.GetItemText(dialog, 19) or "").strip(),
                "height_mode": height_modes[_choice(dialog, 21)][1],
                "clock_mode": clock_modes[_choice(dialog, 23)][1],
                "north_rotation_deg": _float(dialog, 25, "Plannord-Drehung") % 360.0,
                "include_section": _selected(dialog, 26),
                "output": outputs[_choice(dialog, 28)][1],
            }
        return item
    return result["value"] if _run(dialog, handler) == 1 else None


def confirm_delete(count):
    return bool(vs.YNDialog(
        "%d markierte Kanalobjekt(e) wirklich löschen? Bei einem Schacht werden auch seine angeschlossenen Rohre gelöscht."
        % int(count)))


def pipe_properties_dialog(preferences, initial=None, source_count=0, editing=None,
                           purpose=None):
    """Creation and single-pipe dialog; calculation value is staged and explicit."""
    current = copy.deepcopy(initial or {})
    editing = bool(initial) if editing is None else bool(editing)
    kind_values = list(core.KINDS)
    dn_values = list(preferences["dns"])
    material_values = list(preferences["materials"])
    modes = (("Endsohle aus Anfangssohle und Gefälle", "slope"),
             ("Anfangssohle aus Endsohle und Gefälle", "start"),
             ("Gefälle aus Anfangs- und Endsohle", "end"))
    shaft_modes = (("An Anfang, Ende, Knick und Abzweig", "all"),
                   ("Nur Anfang, Ende und Abzweig", "endpoints"),
                   ("Keine sichtbaren Schächte automatisch", "manual"))
    joins = (("Rund", "round"), ("Abgeschrägt", "bevel"), ("Gehrung", "miter"))
    layouts = (("Eine Zeile", "one_line"), ("Zwei Zeilen", "two_line"))
    graphics = (("Gefüllte Doppellinie mit gestrichelter Achslinie", "double_line"),
                ("Einliniengrafik", "single_line"))
    shaft_materials = (("PP-Schacht", "PP"), ("Betonschacht", "concrete"))
    connecting = purpose == "connect"
    dialog = vs.CreateResizableLayout(
        _title("Kanalstrecke bearbeiten" if editing else
               "Neuen Kanalstrang anschließen" if connecting else "Kanalanlage anlegen"),
        True, "Übernehmen" if editing else "Zeichnen", "Abbrechen", True, True)
    vs.CreateStyledStatic(
        dialog, 10,
        ("KANALANSCHLUSS  |  Neuer Strang ab markiertem Kanalobjekt"
         if connecting else "KANALSTRECKE  |  Sohlhöhen und Rohrdaten"),
        -1, TITLE_STYLE)
    vs.CreateStaticText(dialog, 11,
                        ("Ausgewählte Kanalstrecke bearbeiten." if editing else
                         "Nach 'Zeichnen' den Anschlusspunkt bzw. die weiteren Haltungen anklicken; "
                         "Doppelklick beendet den neuen Strang." if connecting else
                         "%s. Die Punktreihenfolge bestimmt standardmäßig die Fließrichtung." %
                         ("%d markierte Ausgangsstrecken" % source_count if source_count else "Neue Punktfolge")), 74)
    labels = ((12, "Kanalart:"), (14, "Nenndurchmesser:"), (16, "Material:"),
              (52, "Rohr-Außendurchmesser OD [mm]:"),
              (18, "Anfangssohle KS [m]:"), (20, "Berechnung:"),
              (22, "Gefälle [%]:"), (25, "Deckelhöhe KD [m]:"),
              (27, "Lichter Schacht-Ø [m]:"),
              (48, "Schachtbauart:"), (50, "Beton-Wandstärke [m]:"),
              (29, "Schächte:"),
              (31, "Außenlinien am Knick:"), (33, "Rohrbeschriftung:"),
              (42, "Ausrundungsradius [m]:"),
              (46, "Fließpfeil – Skalierungsfaktor:"),
              (44, "Beschriftungsbreite [m] (0 = auto):"),
              (40, "Freie Bezeichnung:"),
              (61, "Darstellung der Haltung:"),
              (63, "Linienart Einliniengrafik:"),
              (65, "Gestrichelte Achslinie:"),
              (67, "Rohrwandstärke [mm]:"))
    for item, text in labels:
        vs.CreateStaticText(dialog, item, text, -1)
    for item, width in ((13, 18), (15, 18), (17, 22), (21, 38), (30, 40), (32, 22), (34, 22)):
        vs.CreatePullDownMenu(dialog, item, width)
    vs.CreatePullDownMenu(dialog, 49, 28)
    vs.CreatePullDownMenu(dialog, 62, 48)
    vs.CreateLineStylePopup(dialog, 64)
    vs.CreateLineStylePopup(dialog, 66)
    vs.CreateEditText(
        dialog, 68,
        str(current.get("wall_thickness_mm", preferences["pipe_wall_thickness_mm"])).replace(".", ","), 18)
    for item, value, width in (
            (19, current.get("start_invert_m", 100.0), 18),
            (23, current.get("calculation_value", current.get("end_invert_m", 1.5)), 18),
            (26, current.get("cover_height_m", current.get("start_invert_m", 100.0) + preferences["cover_offset_m"]), 18),
            (28, current.get("shaft_diameter_m", preferences["shaft_diameter_m"]), 18),
            (51, current.get("shaft_wall_thickness_m", preferences["shaft_wall_thickness_m"]), 18),
            (43, current.get("fillet_radius_m", preferences["fillet_radius_m"]), 18),
            (47, current.get("flow_arrow_scale", preferences["flow_arrow_scale"]), 18),
            (45, current.get("label_width_m", 0.0), 18),
             (41, current.get("name", ""), 34)):
        vs.CreateEditText(dialog, item, str(value).replace(".", ","), width)
    vs.CreateEditText(
        dialog, 53,
        str(current.get("outside_diameter_mm",
                        current.get("dn_mm", preferences["default_dn_mm"]))).replace(".", ","), 18)
    vs.CreateCheckBox(dialog, 24, "Fließrichtung gegenüber der Punktfolge umkehren")
    vs.CreateCheckBox(dialog, 35, "Zusätzliche 3D-Rohre und 3D-Schächte erzeugen")
    vs.CreateCheckBox(dialog, 69, "3D-Rohre mit sichtbarer Innenkontur (hohl) erzeugen")
    vs.CreateCheckBox(dialog, 36, "Individuelle Farbe für diese Strecke verwenden")
    vs.CreateColorPopup(dialog, 37, 22)
    vs.CreateStaticText(dialog, 38,
                        "Standardfarben gelten global je Kanalart. Eine Einzelabweichung bleibt am Objekt gespeichert.", 48)
    # One compact column per native tab. The former three simultaneous
    # columns collided at Windows/Vectorworks text scaling above 100%.
    vs.CreateTabControl(dialog, 57)
    vs.CreateGroupBox(dialog, 58, "Rohr + Höhen", False)
    vs.CreateGroupBox(dialog, 59, "Schächte", False)
    vs.CreateGroupBox(dialog, 60, "Darstellung", False)
    vs.SetFirstLayoutItem(dialog, 10)
    vs.SetBelowItem(dialog, 10, 11, 0, 5)
    vs.SetBelowItem(dialog, 11, 57, 0, 8)
    vs.SetFirstGroupItem(dialog, 58, 12)
    previous = None
    for label, field in ((12, 13), (14, 15), (16, 17), (52, 53),
                         (18, 19), (20, 21), (22, 23)):
        if previous is not None:
            vs.SetBelowItem(dialog, previous, label, 0, 7)
        vs.SetRightItem(dialog, label, field, 8, 0)
        previous = label
    vs.SetBelowItem(dialog, previous, 24, 0, 5)
    vs.SetFirstGroupItem(dialog, 59, 25)
    previous = None
    for label, field in ((25, 26), (27, 28), (48, 49), (50, 51),
                         (29, 30)):
        if previous is not None:
            vs.SetBelowItem(dialog, previous, label, 0, 7)
        vs.SetRightItem(dialog, label, field, 8, 0)
        previous = label
    vs.SetFirstGroupItem(dialog, 60, 61)
    vs.SetRightItem(dialog, 61, 62, 8, 0)
    vs.SetBelowItem(dialog, 61, 63, 0, 7)
    vs.SetRightItem(dialog, 63, 64, 8, 0)
    vs.SetBelowItem(dialog, 63, 65, 0, 7)
    vs.SetRightItem(dialog, 65, 66, 8, 0)
    vs.SetBelowItem(dialog, 65, 67, 0, 7)
    vs.SetRightItem(dialog, 67, 68, 8, 0)
    vs.SetBelowItem(dialog, 67, 69, 0, 5)
    previous = None
    for label, field in ((31, 32), (42, 43), (46, 47), (33, 34), (44, 45)):
        if previous is not None:
            vs.SetBelowItem(dialog, previous, label, 0, 7)
        else:
            vs.SetBelowItem(dialog, 69, label, 0, 7)
        vs.SetRightItem(dialog, label, field, 8, 0)
        previous = label
    vs.SetBelowItem(dialog, previous, 35, 0, 5)
    vs.SetBelowItem(dialog, 35, 36, 0, 5)
    vs.SetRightItem(dialog, 36, 37, 8, 0)
    vs.SetBelowItem(dialog, 36, 38, 0, 4)
    vs.SetBelowItem(dialog, 38, 40, 0, 5)
    vs.SetRightItem(dialog, 40, 41, 8, 0)
    for pane in (58, 59, 60):
        vs.CreateTabPane(dialog, 57, pane)
    vs.SetEdgeBinding(dialog, 11, True, True, True, False)
    vs.SetEdgeBinding(dialog, 57, True, True, True, True)
    result = {"value": None}

    def select_value(item, values, value):
        index = values.index(value) if value in values else 0
        vs.SelectChoice(dialog, item, index, True)

    def update_mode(reset_reference=False):
        mode = modes[_choice(dialog, 21)][1]
        vs.SetItemText(dialog, 18, "Endsohle KS [m]:" if mode == "start" else "Anfangssohle KS [m]:")
        vs.SetItemText(dialog, 22, "Endsohle KS [m]:" if mode == "end" else "Gefälle [%]:")
        if reset_reference and editing:
            reference = current["end_invert_m"] if mode == "start" else current["start_invert_m"]
            vs.SetItemText(dialog, 19, str(reference).replace(".", ","))

    def update_shaft_material():
        material = shaft_materials[_choice(dialog, 49)][1]
        concrete = material == "concrete"
        vs.EnableItem(dialog, 50, concrete)
        vs.EnableItem(dialog, 51, concrete)
        if concrete:
            try:
                wall = _float(dialog, 51, "Schachtwandstärke")
            except core.SewerError:
                wall = 0.0
            if wall <= 0.0:
                vs.SetItemText(dialog, 51, str(
                    preferences["shaft_wall_thickness_m"]).replace(".", ","))

    def handler(item, _data):
        if item == INIT:
            for control, values in ((13, kind_values), (15, ["DN %d" % value for value in dn_values]),
                                    (17, material_values), (21, [row[0] for row in modes]),
                                    (30, [row[0] for row in shaft_modes]),
                                    (32, [row[0] for row in joins]), (34, [row[0] for row in layouts]),
                                    (62, [row[0] for row in graphics])):
                for index, value in enumerate(values):
                    vs.AddChoice(dialog, control, str(value), index)
            select_value(13, kind_values, current.get("kind", preferences["default_kind"]))
            select_value(15, dn_values, int(current.get("dn_mm", preferences["default_dn_mm"])))
            select_value(17, material_values, current.get("material", preferences["default_material"]))
            select_value(21, [row[1] for row in modes], current.get("calculation_mode", "end" if editing else "slope"))
            select_value(30, [row[1] for row in shaft_modes], current.get("shaft_mode", preferences["shaft_mode"]))
            select_value(32, [row[1] for row in joins], current.get("join_style", preferences["join_style"]))
            select_value(34, [row[1] for row in layouts], current.get("label_layout", preferences["label_layout"]))
            select_value(62, [row[1] for row in graphics],
                         current.get("graphics_mode", preferences["graphics_mode"]))
            vs.SetLineTypeChoice(
                dialog, 64, int(current.get("line_type", preferences["single_line_type"])))
            vs.SetLineTypeChoice(
                dialog, 66, int(current.get("axis_line_type", preferences["axis_line_type"])))
            for index, row in enumerate(shaft_materials):
                vs.AddChoice(dialog, 49, row[0], index)
            select_value(
                49, [row[1] for row in shaft_materials],
                current.get("shaft_construction_material",
                            preferences["shaft_construction_material"]))
            vs.SetBooleanItem(dialog, 24, bool(current.get("reverse_flow", False)))
            vs.SetBooleanItem(dialog, 35, bool(current.get("draw_3d", preferences["draw_3d"])))
            vs.SetBooleanItem(dialog, 69, bool(current.get("hollow_3d", preferences["hollow_3d"])))
            override = current.get("color_override")
            vs.SetBooleanItem(dialog, 36, override is not None)
            color = override or preferences["colors"][kind_values[_choice(dialog, 13)]]
            vs.SetColorChoice(dialog, 37, vs.RGBToColorIndex(*color))
            update_mode()
            update_shaft_material()
        elif item == 21:
            update_mode(True)
        elif item == 49:
            update_shaft_material()
        elif item == 1:
            mode = modes[_choice(dialog, 21)][1]
            kind = kind_values[_choice(dialog, 13)]
            override = (list(vs.ColorIndexToRGB(vs.GetColorChoice(dialog, 37)))
                        if _selected(dialog, 36) else None)
            result["value"] = {
                "kind": kind, "dn_mm": dn_values[_choice(dialog, 15)],
                "outside_diameter_mm": _float(dialog, 53, "Rohraußendurchmesser"),
                "outside_diameter_explicit": True,
                "material": material_values[_choice(dialog, 17)],
                "start_invert_m": _float(dialog, 19, "Endsohle" if mode == "start" else "Anfangssohle"),
                "calculation_mode": mode,
                "calculation_value": _float(dialog, 23, "Endsohle" if mode == "end" else "Gefälle"),
                "reverse_flow": _selected(dialog, 24),
                "cover_height_m": _float(dialog, 26, "Deckelhöhe"),
                "shaft_diameter_m": _float(dialog, 28, "Schachtdurchmesser"),
                "shaft_construction_material": shaft_materials[_choice(dialog, 49)][1],
                "shaft_wall_thickness_m": (
                    _float(dialog, 51, "Schachtwandstärke")
                    if shaft_materials[_choice(dialog, 49)][1] == "concrete" else 0.0),
                "cover_diameter_m": preferences["shaft_cover_diameter_m"],
                "cover_symbol": preferences["shaft_cover_symbol"],
                "cover_placement": preferences["shaft_cover_placement"],
                "cover_rotation_deg": preferences["shaft_cover_rotation_deg"],
                "shaft_mode": shaft_modes[_choice(dialog, 30)][1],
                "join_style": joins[_choice(dialog, 32)][1],
                "fillet_radius_m": _float(dialog, 43, "Ausrundungsradius"),
                "flow_arrow_scale": _float(dialog, 47, "Fließrichtungspfeil-Skalierung"),
                "label_layout": layouts[_choice(dialog, 34)][1],
                "label_width_m": _float(dialog, 45, "Beschriftungsbreite"),
                "graphics_mode": graphics[_choice(dialog, 62)][1],
                "line_type": _line_type_choice(
                    dialog, 64, current.get("line_type", preferences["single_line_type"])),
                "axis_line_type": _line_type_choice(
                    dialog, 66, current.get("axis_line_type", preferences["axis_line_type"])),
                "wall_thickness_mm": _float(dialog, 68, "Rohrwandstärke"),
                "hollow_3d": _selected(dialog, 69),
                "draw_3d": _selected(dialog, 35), "color_override": override,
                "name": str(vs.GetItemText(dialog, 41) or "").strip(),
            }
        return item
    return result["value"] if _run(dialog, handler, (560, 540)) == 1 else None


def shaft_dialog(shaft, preferences, inlet_inverts=(), outlet_inverts=()):
    current = core.validate_shaft(shaft, allow_hidden=True)
    incoming = tuple(core.number(value, "Zulaufsohle") for value in inlet_inverts)
    outgoing = tuple(core.number(value, "Ablaufsohle") for value in outlet_inverts)
    inlet_value = min(incoming) if incoming else current["ks_m"]
    outlet_value = min(outgoing) if outgoing else current["ks_m"]
    kinds = list(core.KINDS)
    dialog = vs.CreateResizableLayout(_title("Kanalschacht bearbeiten"), True,
                                      "Übernehmen", "Abbrechen", True, True)
    vs.CreateStyledStatic(dialog, 10, "SCHACHT  |  Lage bleibt direkt verschiebbar", -1, TITLE_STYLE)
    rows = ((11, "Schachtname:", 12, current["name"]),
            (15, "Deckelhöhe KD [m]:", 16, current["kd_m"]),
            (17, "Kanalsohle Zulauf [m]:", 18, inlet_value),
            (34, "Kanalsohle Ablauf [m]:", 35, outlet_value),
            (19, "Lichter Innendurchmesser [m]:", 20, current["diameter_m"]))
    for label, text, field, value in rows:
        vs.CreateStaticText(dialog, label, text, -1)
        vs.CreateEditText(dialog, field, str(value).replace(".", ","), 24)
    vs.CreateStaticText(dialog, 13, "Kanalart:", -1)
    vs.CreatePullDownMenu(dialog, 14, 20)
    vs.CreateStaticText(dialog, 38, "Schachtbauart:", -1)
    vs.CreatePullDownMenu(dialog, 39, 28)
    vs.CreateStaticText(dialog, 40, "Beton-Wandstärke [m]:", -1)
    vs.CreateEditText(dialog, 41, str(current["wall_thickness_m"]).replace(".", ","), 24)
    vs.CreateCheckBox(dialog, 21, "Individuelle Schachtfarbe")
    vs.CreateColorPopup(dialog, 22, 22)
    vs.CreateStaticText(dialog, 24, "Schachtdeckel-Ø [m]:", -1)
    vs.CreateEditText(dialog, 25, str(current["cover_diameter_m"]).replace(".", ","), 24)
    vs.CreateStaticText(dialog, 26, "Schachtdeckellage:", -1)
    vs.CreatePullDownMenu(dialog, 27, 42)
    vs.CreateStaticText(dialog, 28, "Symboldrehung [°]:", -1)
    vs.CreateEditText(dialog, 29, str(current["cover_rotation_deg"]).replace(".", ","), 24)
    vs.CreateCheckBox(dialog, 30, "2D-Symbol aus Dokument oder Bibliothek verwenden")
    vs.CreateResourcePopup(dialog, 31, 42)
    vs.CreateStaticText(dialog, 32, "Zusatztext unter dem Schachtnamen:", -1)
    vs.CreateEditText(dialog, 33, current["note"], 42)
    vs.CreateCheckBox(dialog, 36, "Zu- und Ablauf mit gleicher Höhe")
    vs.CreateStaticText(
        dialog, 37,
        "Die Zulaufhöhe gilt für alle einmündenden Leitungen, die Ablaufhöhe für alle abgehenden Leitungen. "
        "Die Rohrgefälle und die Schachtbeschriftung werden gemeinsam geprüft und neu aufgebaut.", 72)
    vs.CreateStaticText(dialog, 23,
                        "Beim Verschieben dieses Schachtobjekts werden angeschlossene Rohre automatisch neu aufgebaut.", 72)
    vs.SetFirstLayoutItem(dialog, 10)
    previous = 10
    for label, _text, field, _value in rows[:1]:
        vs.SetBelowItem(dialog, previous, label, 0, 6)
        vs.SetRightItem(dialog, label, field, 8, 0)
        previous = label
    vs.SetBelowItem(dialog, previous, 32, 0, 6)
    vs.SetRightItem(dialog, 32, 33, 8, 0)
    previous = 32
    vs.SetBelowItem(dialog, previous, 13, 0, 6)
    vs.SetRightItem(dialog, 13, 14, 8, 0)
    previous = 13
    for label, _text, field, _value in rows[1:3]:
        vs.SetBelowItem(dialog, previous, label, 0, 6)
        vs.SetRightItem(dialog, label, field, 8, 0)
        previous = label
    vs.SetBelowItem(dialog, previous, 36, 0, 4)
    vs.SetBelowItem(dialog, 36, 37, 0, 3)
    previous = 37
    for label, _text, field, _value in rows[3:]:
        vs.SetBelowItem(dialog, previous, label, 0, 6)
        vs.SetRightItem(dialog, label, field, 8, 0)
        previous = label
    for label, field in ((38, 39), (40, 41)):
        vs.SetBelowItem(dialog, previous, label, 0, 6)
        vs.SetRightItem(dialog, label, field, 8, 0)
        previous = label
    for label, field in ((24, 25), (26, 27), (28, 29)):
        vs.SetBelowItem(dialog, previous, label, 0, 6)
        vs.SetRightItem(dialog, label, field, 8, 0)
        previous = label
    vs.SetBelowItem(dialog, previous, 30, 0, 6)
    vs.SetBelowItem(dialog, 30, 31, 0, 4)
    vs.SetBelowItem(dialog, 31, 21, 0, 6)
    vs.SetRightItem(dialog, 21, 22, 8, 0)
    vs.SetBelowItem(dialog, 21, 23, 0, 5)
    result = {"value": None}
    resource_id = "PD.Kanal.Schachtdeckel.Schacht"
    shaft_materials = (("PP-Schacht", "PP"), ("Betonschacht", "concrete"))

    def update_cover_state():
        try:
            diameter = _float(dialog, 20, "Schachtdurchmesser")
        except core.SewerError:
            return
        enabled = diameter > 0.0
        material = shaft_materials[_choice(dialog, 39)][1]
        concrete = enabled and material == "concrete"
        vs.EnableItem(dialog, 40, concrete)
        vs.EnableItem(dialog, 41, concrete)
        wall = 0.0
        if concrete:
            try:
                wall = _float(dialog, 41, "Schachtwandstärke")
            except core.SewerError:
                wall = 0.0
        outside = diameter + 2.0 * max(0.0, wall)
        if enabled:
            try:
                cover = _float(dialog, 25, "Schachtdeckeldurchmesser")
                if cover > outside:
                    vs.SetItemText(dialog, 25, str(outside).replace(".", ","))
            except core.SewerError:
                pass
        for item_id in (25, 27, 29, 30):
            vs.EnableItem(dialog, item_id, enabled)
        vs.EnableItem(dialog, 31, enabled and _selected(dialog, 30))

    def handler(item, _data):
        if item == INIT:
            for index, kind in enumerate(kinds):
                vs.AddChoice(dialog, 14, kind, index)
            vs.SelectChoice(dialog, 14, kinds.index(current["kind"]), True)
            for index, row in enumerate(shaft_materials):
                vs.AddChoice(dialog, 39, row[0], index)
            vs.SelectChoice(
                dialog, 39,
                [row[1] for row in shaft_materials].index(current["construction_material"]), True)
            for index, row in enumerate(COVER_PLACEMENTS):
                vs.AddChoice(dialog, 27, row[0], index)
            placement_values = [row[1] for row in COVER_PLACEMENTS]
            vs.SelectChoice(dialog, 27, placement_values.index(current["cover_placement"]), True)
            _init_cover_resource(dialog, 31, resource_id, current["cover_symbol"])
            vs.SetBooleanItem(dialog, 30, bool(current["cover_symbol"]))
            vs.EnableItem(dialog, 31, bool(current["cover_symbol"]))
            vs.SetBooleanItem(dialog, 36, False)
            vs.EnableItem(dialog, 18, bool(incoming))
            vs.EnableItem(dialog, 35, bool(outgoing))
            vs.EnableItem(dialog, 36, bool(incoming and outgoing))
            override = current.get("color_override")
            vs.SetBooleanItem(dialog, 21, override is not None)
            vs.SetColorChoice(dialog, 22, vs.RGBToColorIndex(*(override or preferences["colors"][current["kind"]])))
            update_cover_state()
        elif item in (20, 39, 41):
            update_cover_state()
        elif item == 30:
            update_cover_state()
        elif item in (18, 36):
            same = _selected(dialog, 36)
            if same:
                vs.SetItemText(dialog, 35, str(vs.GetItemText(dialog, 18) or ""))
            vs.EnableItem(dialog, 35, bool(outgoing) and not same)
        elif item == 1:
            try:
                # Some Vectorworks dialog states return an empty string for an
                # unchanged first edit field. Numeric edits must not erase the
                # already valid shaft identity in that case.
                name = _shaft_name_text(dialog, 12, current["name"])
                inlet = _float(dialog, 18, "Zulaufsohle") if incoming else inlet_value
                outlet = _float(dialog, 35, "Ablaufsohle") if outgoing else outlet_value
                equal = bool(incoming and outgoing and _selected(dialog, 36))
                if equal:
                    outlet = inlet
                endpoint_values = ([inlet] if incoming else []) + ([outlet] if outgoing else [])
                diameter = _float(dialog, 20, "Schachtdurchmesser")
                construction_material = shaft_materials[_choice(dialog, 39)][1]
                wall_thickness = (_float(dialog, 41, "Schachtwandstärke")
                                  if construction_material == "concrete" and diameter > 0.0
                                  else 0.0)
                outside_diameter = diameter + 2.0 * wall_thickness
                cover_diameter = current["cover_diameter_m"]
                if diameter > 0.0:
                    cover_diameter = min(
                        _float(dialog, 25, "Schachtdeckeldurchmesser"), outside_diameter)
                value = dict(current)
                value.update(name=name,
                             note=str(vs.GetItemText(dialog, 33) or "").strip(),
                             kind=kinds[_choice(dialog, 14)],
                             kd_m=_float(dialog, 16, "Deckelhöhe"),
                             ks_m=min(endpoint_values) if endpoint_values else current["ks_m"],
                             diameter_m=diameter,
                             construction_material=construction_material,
                             wall_thickness_m=wall_thickness,
                             cover_diameter_m=cover_diameter,
                             cover_symbol=_cover_symbol(resource_id, _selected(dialog, 30)),
                             cover_placement=COVER_PLACEMENTS[_choice(dialog, 27)][1],
                             cover_rotation_deg=_float(dialog, 29, "Schachtdeckeldrehung"),
                             color_override=(list(vs.ColorIndexToRGB(vs.GetColorChoice(dialog, 22)))
                                             if _selected(dialog, 21) else None))
                result["value"] = {
                    "shaft": core.validate_shaft(value, allow_hidden=True),
                    "inlet_invert_m": inlet,
                    "outlet_invert_m": outlet,
                    "equal_inverts": equal,
                }
            except core.SewerError as error:
                vs.AlrtDialog(str(error))
                result["value"] = None
                return -1
        return item
    return result["value"] if _run(dialog, handler) == 1 else None


def downstream_height_dialog(delta_m, pipe_count):
    """Ask how a changed invert is handed to the downstream network."""
    delta = core.number(delta_m, "Höhenänderung")
    count = int(pipe_count)
    if count < 1:
        return "slope"
    direction = "angehoben" if delta > 0 else "abgesenkt"
    dialog = vs.CreateResizableLayout(
        _title("Kanalhöhen weiterführen"), True, "Übernehmen", "Abbrechen", True, True)
    vs.CreateStyledStatic(dialog, 10, "FOLGENDE KANÄLE  |  Höhenänderung festlegen", -1, TITLE_STYLE)
    vs.CreateStaticText(
        dialog, 11,
        "Die Sohle wurde um %s m %s. %d nachfolgende Haltung(en) sind betroffen." %
        (("%.3f" % abs(delta)).replace(".", ","), direction, count), 72)
    vs.CreateStaticText(dialog, 12, "Weiterführung:", -1)
    vs.CreatePullDownMenu(dialog, 13, 68)
    vs.CreateStaticText(
        dialog, 14,
        "Mitverschieben erhält die vorhandenen Gefälle aller nachfolgenden Kanäle. "
        "Nicht mitverschieben hält die folgenden Schachthöhen fest; dadurch wird nur das Gefälle "
        "der unmittelbar folgenden Haltung neu berechnet.", 76)
    vs.SetFirstLayoutItem(dialog, 10)
    vs.SetBelowItem(dialog, 10, 11, 0, 6)
    vs.SetBelowItem(dialog, 11, 12, 0, 7)
    vs.SetRightItem(dialog, 12, 13, 8, 0)
    vs.SetBelowItem(dialog, 12, 14, 0, 7)
    choices = (
        ("Nachfolgende Kanäle mitverschieben – vorhandene Gefälle erhalten", "shift"),
        ("Folgende Schächte festhalten – Gefälle der nächsten Haltung ändern", "slope"),
    )
    result = {"value": None}

    def handler(item, _data):
        if item == INIT:
            for index, row in enumerate(choices):
                vs.AddChoice(dialog, 13, row[0], index)
            vs.SelectChoice(dialog, 13, 0, True)
        elif item == 1:
            try:
                result["value"] = choices[_choice(dialog, 13)][1]
            except (IndexError, ValueError) as error:
                vs.AlrtDialog(str(error))
                return -1
        return item
    return result["value"] if _run(dialog, handler) == 1 else None


def batch_pipe_dialog(preferences):
    dialog = vs.CreateResizableLayout(_title("Mehrere Kanalstrecken bearbeiten"), True,
                                      "Übernehmen", "Abbrechen", True, True)
    vs.CreateStyledStatic(dialog, 10, "SAMMELÄNDERUNG  |  Nur gewählte Werte werden ersetzt", -1, TITLE_STYLE)
    labels = ((11, "Kanalart:"), (13, "DN:"), (15, "Material:"))
    for label, text in labels:
        vs.CreateStaticText(dialog, label, text, -1)
        vs.CreatePullDownMenu(dialog, label + 1, 28)
    vs.SetFirstLayoutItem(dialog, 10)
    previous = 10
    for label, _text in labels:
        vs.SetBelowItem(dialog, previous, label, 0, 7)
        vs.SetRightItem(dialog, label, label + 1, 8, 0)
        previous = label
    values = ((12, list(core.KINDS)), (14, list(preferences["dns"])),
              (16, list(preferences["materials"])))
    result = {"value": None}

    def handler(item, _data):
        if item == INIT:
            for control, rows in values:
                vs.AddChoice(dialog, control, "(nicht ändern)", 0)
                for index, value in enumerate(rows, 1):
                    vs.AddChoice(dialog, control, "DN %s" % value if control == 14 else str(value), index)
                vs.SelectChoice(dialog, control, 0, True)
        elif item == 1:
            changed = {}
            for control, rows, key in ((12, values[0][1], "kind"),
                                       (14, values[1][1], "dn_mm"),
                                       (16, values[2][1], "material")):
                index = _choice(dialog, control)
                if index:
                    changed[key] = rows[index - 1]
            result["value"] = changed
        return item
    return result["value"] if _run(dialog, handler) == 1 else None


def preferences_dialog(preferences):
    current = copy.deepcopy(preferences)
    dialog = vs.CreateResizableLayout(_title("Kanalanlage – Voreinstellungen"), True,
                                      "Speichern", "Abbrechen", True, True)
    vs.CreateStyledStatic(dialog, 10, "VOREINSTELLUNGEN  |  Farben und erweiterbare Kataloge", -1, TITLE_STYLE)
    for index, kind in enumerate(core.KINDS):
        label, field = 11 + index * 2, 12 + index * 2
        vs.CreateStaticText(dialog, label, "Standardfarbe %s:" % kind, -1)
        vs.CreateColorPopup(dialog, field, 24)
    vs.CreateStaticText(dialog, 17, "DN-Werte [mm], mit Semikolon getrennt:", -1)
    vs.CreateEditText(dialog, 18, "; ".join(str(value) for value in current["dns"]), 68)
    vs.CreateStaticText(dialog, 19, "Materialien, mit Semikolon getrennt:", -1)
    vs.CreateEditText(dialog, 20, "; ".join(current["materials"]), 68)
    vs.CreateStaticText(dialog, 21, "Schriftgröße [pt]:", -1)
    vs.CreateEditText(dialog, 22, str(current["point_size"]).replace(".", ","), 14)
    vs.CreateStaticText(dialog, 23, "Textabstand auf Papier [mm]:", -1)
    vs.CreateEditText(dialog, 24, str(current["text_offset_mm"]).replace(".", ","), 14)
    vs.CreateStaticText(dialog, 27, "Standard-Ausrundungsradius [m]:", -1)
    vs.CreateEditText(dialog, 28, str(current["fillet_radius_m"]).replace(".", ","), 14)
    vs.CreateStaticText(dialog, 37, "Standard-Skalierung Fließrichtungspfeil:", -1)
    vs.CreateEditText(dialog, 38, str(current["flow_arrow_scale"]).replace(".", ","), 14)
    vs.CreateStaticText(dialog, 39, "Standard-Kanaldarstellung:", -1)
    vs.CreatePullDownMenu(dialog, 40, 34)
    vs.CreateStaticText(dialog, 41, "Linienart der Einliniengrafik:", -1)
    vs.CreateLineStylePopup(dialog, 42)
    vs.CreateStaticText(dialog, 43, "Gestrichelte schwarze Achslinie:", -1)
    vs.CreateLineStylePopup(dialog, 44)
    vs.CreateStaticText(dialog, 45, "Standard-Schachtbauart:", -1)
    vs.CreatePullDownMenu(dialog, 46, 28)
    vs.CreateStaticText(dialog, 47, "Standard-Betonwandstärke [m]:", -1)
    vs.CreateEditText(dialog, 48, str(current["shaft_wall_thickness_m"]).replace(".", ","), 14)
    vs.CreateStaticText(dialog, 29, "Standard-Schachtdeckel-Ø [m]:", -1)
    vs.CreateEditText(dialog, 30, str(current["shaft_cover_diameter_m"]).replace(".", ","), 14)
    vs.CreateStaticText(dialog, 31, "Standard-Schachtdeckellage:", -1)
    vs.CreatePullDownMenu(dialog, 32, 42)
    vs.CreateStaticText(dialog, 33, "Standard-Symboldrehung [°]:", -1)
    vs.CreateEditText(dialog, 34, str(current["shaft_cover_rotation_deg"]).replace(".", ","), 14)
    vs.CreateCheckBox(dialog, 35, "2D-Schachtdeckelsymbol aus Dokument oder Bibliothek verwenden")
    vs.CreateResourcePopup(dialog, 36, 42)
    vs.CreateCheckBox(dialog, 25, "Bestehende Kanalobjekte ohne individuelle Farbe aktualisieren")
    vs.CreateStaticText(dialog, 26,
                        "Listen können hier ergänzt, umbenannt oder gelöscht werden. Verwendete Objektwerte bleiben erhalten.", 76)
    vs.SetFirstLayoutItem(dialog, 10)
    previous = 10
    for index in range(3):
        label, field = 11 + index * 2, 12 + index * 2
        vs.SetBelowItem(dialog, previous, label, 0, 6)
        vs.SetRightItem(dialog, label, field, 8, 0)
        previous = label
    for label, field in ((17, 18), (19, 20), (21, 22), (23, 24), (27, 28), (37, 38),
                         (39, 40), (41, 42), (43, 44), (45, 46), (47, 48),
                         (29, 30), (31, 32), (33, 34)):
        vs.SetBelowItem(dialog, previous, label, 0, 6)
        vs.SetRightItem(dialog, label, field, 8, 0)
        previous = label
    vs.SetBelowItem(dialog, previous, 35, 0, 6)
    vs.SetBelowItem(dialog, 35, 36, 0, 4)
    vs.SetBelowItem(dialog, 36, 25, 0, 6)
    vs.SetBelowItem(dialog, 25, 26, 0, 5)
    result = {"value": None, "update": False}
    resource_id = "PD.Kanal.Schachtdeckel.Voreinstellung"
    shaft_materials = (("PP-Schacht", "PP"), ("Betonschacht", "concrete"))

    def split(item):
        return [value.strip() for value in str(vs.GetItemText(dialog, item) or "").split(";") if value.strip()]

    def update_shaft_material():
        concrete = shaft_materials[_choice(dialog, 46)][1] == "concrete"
        vs.EnableItem(dialog, 47, concrete)
        vs.EnableItem(dialog, 48, concrete)

    def handler(item, _data):
        if item == INIT:
            for index, kind in enumerate(core.KINDS):
                vs.SetColorChoice(dialog, 12 + index * 2, vs.RGBToColorIndex(*current["colors"][kind]))
            for index, row in enumerate(COVER_PLACEMENTS):
                vs.AddChoice(dialog, 32, row[0], index)
            placement_values = [row[1] for row in COVER_PLACEMENTS]
            vs.SelectChoice(dialog, 32, placement_values.index(current["shaft_cover_placement"]), True)
            _init_cover_resource(dialog, 36, resource_id, current["shaft_cover_symbol"])
            vs.SetBooleanItem(dialog, 35, bool(current["shaft_cover_symbol"]))
            vs.EnableItem(dialog, 36, bool(current["shaft_cover_symbol"]))
            for index, label in enumerate(("Doppellinie mit schwarzer Achse", "Einliniengrafik")):
                vs.AddChoice(dialog, 40, label, index)
            vs.SelectChoice(dialog, 40, 0 if current["graphics_mode"] == "double_line" else 1, True)
            vs.SetLineTypeChoice(dialog, 42, current["single_line_type"])
            vs.SetLineTypeChoice(dialog, 44, current["axis_line_type"])
            for index, row in enumerate(shaft_materials):
                vs.AddChoice(dialog, 46, row[0], index)
            vs.SelectChoice(
                dialog, 46,
                [row[1] for row in shaft_materials].index(
                    current["shaft_construction_material"]), True)
            update_shaft_material()
        elif item == 35:
            vs.EnableItem(dialog, 36, _selected(dialog, 35))
        elif item == 46:
            update_shaft_material()
        elif item == 1:
            try:
                value = copy.deepcopy(current)
                value["colors"] = {kind: list(vs.ColorIndexToRGB(vs.GetColorChoice(dialog, 12 + index * 2)))
                                   for index, kind in enumerate(core.KINDS)}
                value["dns"] = [core._dn(row) for row in split(18)]
                value["materials"] = [core._material(row) for row in split(20)]
                value["point_size"] = _float(dialog, 22, "Schriftgröße")
                value["text_offset_mm"] = _float(dialog, 24, "Textabstand")
                value["fillet_radius_m"] = _float(dialog, 28, "Ausrundungsradius")
                value["flow_arrow_scale"] = _float(dialog, 38, "Fließrichtungspfeil-Skalierung")
                value["graphics_mode"] = ("double_line", "single_line")[_choice(dialog, 40)]
                value["single_line_type"] = int(vs.GetLineTypeChoice(dialog, 42))
                value["axis_line_type"] = int(vs.GetLineTypeChoice(dialog, 44))
                value["shaft_construction_material"] = shaft_materials[_choice(dialog, 46)][1]
                value["shaft_wall_thickness_m"] = (
                    _float(dialog, 48, "Standard-Betonwandstärke")
                    if value["shaft_construction_material"] == "concrete" else 0.0)
                value["shaft_cover_diameter_m"] = _float(dialog, 30, "Schachtdeckeldurchmesser")
                value["shaft_cover_placement"] = COVER_PLACEMENTS[_choice(dialog, 32)][1]
                value["shaft_cover_rotation_deg"] = _float(dialog, 34, "Schachtdeckeldrehung")
                value["shaft_cover_symbol"] = _cover_symbol(resource_id, _selected(dialog, 35))
                result["value"] = settings.validate(value)
                result["update"] = _selected(dialog, 25)
            except core.SewerError as error:
                vs.AlrtDialog(str(error))
                result["value"] = None
                return -1
        return item
    return (result["value"], result["update"]) if _run(dialog, handler) == 1 else (None, False)


def network_chain_dialog(shafts, pipes, highlight=None):
    """Stage several shaft elevations and pipe slopes in one network dialog."""
    shafts = {value["id"]: core.validate_shaft(value, allow_hidden=True) for value in shafts}
    pipes = {value["id"]: core.validate_pipe(value) for value in pipes}
    rows = ([('shaft', value["id"], "Schacht %s" % value["name"])
             for value in sorted(shafts.values(), key=lambda row: (row["name"], row["id"]))] +
            [('pipe', value["id"], "Rohr %s → %s" %
              (shafts[value["start_id"]]["name"], shafts[value["end_id"]]["name"]))
             for value in sorted(pipes.values(), key=lambda row: row["id"])] )
    if not rows:
        raise core.SewerError("Das gewählte Kanalnetz enthält keine bearbeitbaren Objekte.")
    dialog = vs.CreateResizableLayout(_title("Kanalanlage – Kette bearbeiten"), True,
                                      "Alle Änderungen übernehmen", "Abbrechen", True, True)
    vs.CreateStyledStatic(dialog, 10, "KANALKETTE  |  Mehrere Gefälle und Schachthöhen", -1, TITLE_STYLE)
    vs.CreateStaticText(dialog, 11, "Objekt auswählen, Werte ändern und vormerken. Weitere Objekte können danach im selben Dialog bearbeitet werden.", 78)
    vs.CreateStaticText(dialog, 12, "Kettenobjekt:", -1)
    vs.CreatePullDownMenu(dialog, 13, 48)
    vs.CreateStaticText(dialog, 14, "Deckelhöhe KD [m]:", -1)
    vs.CreateEditText(dialog, 15, "", 18)
    vs.CreateStaticText(dialog, 16, "Sohlhöhe KS [m]:", -1)
    vs.CreateEditText(dialog, 17, "", 18)
    vs.CreateStaticText(dialog, 18, "Neues Rohrgefälle [%]:", -1)
    vs.CreateEditText(dialog, 19, "", 18)
    vs.CreateStaticText(dialog, 20, "Fest bleibende Rohrsohle:", -1)
    vs.CreatePullDownMenu(dialog, 21, 32)
    vs.CreatePushButton(dialog, 22, "Änderung vormerken")
    vs.CreateStaticText(dialog, 23, "Noch keine Änderung vorgemerkt.", 76)
    vs.SetFirstLayoutItem(dialog, 10)
    vs.SetBelowItem(dialog, 10, 11, 0, 6)
    previous = 11
    for label, field in ((12, 13), (14, 15), (16, 17), (18, 19), (20, 21)):
        vs.SetBelowItem(dialog, previous, label, 0, 6)
        vs.SetRightItem(dialog, label, field, 8, 0)
        previous = label
    vs.SetBelowItem(dialog, previous, 22, 0, 7)
    vs.SetBelowItem(dialog, 22, 23, 0, 5)
    result = {"value": None, "changes": 0}

    def fmt(value):
        return ("%.4f" % float(value)).replace(".", ",")

    def selected_row():
        return rows[_choice(dialog, 13)]

    def endpoints(identity):
        values = []
        for pipe in pipes.values():
            if pipe["start_id"] == identity:
                values.append((pipe, "start_invert_m"))
            if pipe["end_id"] == identity:
                values.append((pipe, "end_invert_m"))
        return values

    def recompute_soils(identities):
        for identity in identities:
            values = [pipe[key] for pipe, key in endpoints(identity)]
            if values:
                shafts[identity]["ks_m"] = min(values)

    def show():
        role, identity, _title_value = selected_row()
        if highlight:
            highlight(role, identity)
        if role == "shaft":
            shaft = shafts[identity]
            vs.SetItemText(dialog, 14, "Deckelhöhe KD [m]:")
            vs.SetItemText(dialog, 16, "Sohlhöhe KS [m]:")
            vs.SetItemText(dialog, 15, fmt(shaft["kd_m"]))
            vs.SetItemText(dialog, 17, fmt(shaft["ks_m"]))
            vs.SetItemText(dialog, 19, "")
            vs.EnableItem(dialog, 15, True)
            vs.EnableItem(dialog, 17, True)
            vs.EnableItem(dialog, 19, False)
            vs.EnableItem(dialog, 21, False)
        else:
            pipe = pipes[identity]
            vs.SetItemText(dialog, 14, "Anfangssohle KS [m]:")
            vs.SetItemText(dialog, 16, "Endsohle KS [m]:")
            vs.SetItemText(dialog, 15, fmt(pipe["start_invert_m"]))
            vs.SetItemText(dialog, 17, fmt(pipe["end_invert_m"]))
            vs.SetItemText(dialog, 19, fmt(pipe["slope_percent"]))
            vs.EnableItem(dialog, 15, False)
            vs.EnableItem(dialog, 17, False)
            vs.EnableItem(dialog, 19, True)
            vs.EnableItem(dialog, 21, True)

    def stage():
        shaft_snapshot, pipe_snapshot = copy.deepcopy(shafts), copy.deepcopy(pipes)
        try:
            role, identity, _title_value = selected_row()
            if role == "shaft":
                shaft = shafts[identity]
                old_soil = shaft["ks_m"]
                new_soil = _float(dialog, 17, "Sohlhöhe")
                shaft["kd_m"] = _float(dialog, 15, "Deckelhöhe")
                connected = endpoints(identity)
                if connected:
                    for pipe, key in connected:
                        if abs(pipe[key] - old_soil) <= 0.001:
                            pipe[key] = new_soil
                            pipes[pipe["id"]] = core.validate_pipe(pipe)
                    minimum = min(pipe[key] for pipe, key in connected)
                    if abs(minimum - new_soil) > 0.001:
                        raise core.SewerError(
                            "Die neue Schachtsohle liegt über einer weiteren angeschlossenen Rohrsohle.")
                shaft["ks_m"] = new_soil
                shafts[identity] = core.validate_shaft(shaft, allow_hidden=True)
            else:
                pipe = pipes[identity]
                slope = _float(dialog, 19, "Rohrgefälle")
                if slope < 0.0:
                    raise core.SewerError("Rohrgefälle darf nicht negativ sein.")
                if _choice(dialog, 21) == 0:
                    pipe["end_invert_m"] = pipe["start_invert_m"] - pipe["length_m"] * slope / 100.0
                else:
                    pipe["start_invert_m"] = pipe["end_invert_m"] + pipe["length_m"] * slope / 100.0
                pipes[identity] = core.validate_pipe(pipe)
                recompute_soils((pipe["start_id"], pipe["end_id"]))
            core.validate_network(tuple(pipes.values()), tuple(shafts.values()))
            result["changes"] += 1
            vs.SetItemText(dialog, 23, "%d Änderung(en) vorgemerkt. Weitere Kettenobjekte wählen oder alles übernehmen." % result["changes"])
            show()
        except (core.SewerError, ValueError, TypeError) as error:
            shafts.clear()
            shafts.update(shaft_snapshot)
            pipes.clear()
            pipes.update(pipe_snapshot)
            vs.AlrtDialog(str(error))
            return False
        return True

    def handler(item, _data):
        if item == INIT:
            for index, row in enumerate(rows):
                vs.AddChoice(dialog, 13, row[2], index)
            vs.SelectChoice(dialog, 13, 0, True)
            vs.AddChoice(dialog, 21, "Anfangssohle", 0)
            vs.AddChoice(dialog, 21, "Endsohle", 1)
            vs.SelectChoice(dialog, 21, 0, True)
            show()
        elif item == 13:
            show()
        elif item == 22:
            stage()
        elif item == 1:
            if not stage():
                return -1
            result["value"] = (tuple(shafts.values()), tuple(pipes.values()))
        return item
    return result["value"] if _run(dialog, handler) == 1 else None


def stub_alignment_dialog(default="invert"):
    """Select the vertical relation between main and branch pipe."""
    rows = (("Sohlgleich", "invert"), ("Achsgleich", "axis"),
            ("Kämpfergleich", "springline"), ("Scheitelgleich", "crown"))
    dialog = vs.CreateResizableLayout(
        _title("Kanalstutzen nach DIN"), True, "Weiter", "Abbrechen", True, True)
    vs.CreateStyledStatic(dialog, 10, "KANALSTUTZEN  |  Anschlussart und Anschlusshöhe", -1, TITLE_STYLE)
    vs.CreateStaticText(dialog, 11,
                        "Zuerst wurde die Haltung gewählt. Nach dieser Einstellung die Lage des Stutzens "
                        "anklicken und die Anschlussleitung zeichnen.", 76)
    vs.CreateStaticText(dialog, 12, "Vertikale Anschlussart:", -1)
    vs.CreatePullDownMenu(dialog, 13, 34)
    vs.SetFirstLayoutItem(dialog, 10)
    vs.SetBelowItem(dialog, 10, 11, 0, 6)
    vs.SetBelowItem(dialog, 11, 12, 0, 7)
    vs.SetRightItem(dialog, 12, 13, 8, 0)
    result = {"value": None}

    def handler(item, _data):
        if item == INIT:
            for index, row in enumerate(rows):
                vs.AddChoice(dialog, 13, row[0], index)
            values = [row[1] for row in rows]
            vs.SelectChoice(dialog, 13, values.index(default) if default in values else 0, True)
        elif item == 1:
            result["value"] = rows[_choice(dialog, 13)][1]
        return item
    return result["value"] if _run(dialog, handler) == 1 else None


def drop_dialog(shaft, connected_pipes):
    """Assign one incoming holding and the upper/lower drop elevations."""
    rows = []
    for pipe in connected_pipes:
        if pipe["end_id"] == shaft["id"]:
            elevation = pipe["end_invert_m"]
            rows.append((pipe, "DN %d %s | ankommend KS %.3f m" %
                         (pipe["dn_mm"], pipe["material"], elevation), elevation))
    if not rows:
        raise core.SewerError("Am gewählten Schacht ist keine ankommende Haltung vorhanden.")
    dialog = vs.CreateResizableLayout(
        _title("Absturz vor Schacht"), True, "Übernehmen", "Abbrechen", True, True)
    vs.CreateStyledStatic(dialog, 10, "ABSTURZ  |  Obere Spülleitung und untere Absturzleitung", -1, TITLE_STYLE)
    vs.CreateStaticText(dialog, 11, "Ankommende Haltung:", -1)
    vs.CreatePullDownMenu(dialog, 12, 52)
    vs.CreateStaticText(dialog, 13, "Obere ankommende Sohlhöhe [m]:", -1)
    vs.CreateEditText(dialog, 14, str(rows[0][2]).replace(".", ","), 18)
    vs.CreateStaticText(dialog, 15, "Unterkante Absturzleitung [m]:", -1)
    vs.CreateEditText(dialog, 16, str(shaft["ks_m"]).replace(".", ","), 18)
    vs.SetFirstLayoutItem(dialog, 10)
    previous = 10
    for label, field in ((11, 12), (13, 14), (15, 16)):
        vs.SetBelowItem(dialog, previous, label, 0, 7)
        vs.SetRightItem(dialog, label, field, 8, 0)
        previous = label
    result = {"value": None}

    def handler(item, _data):
        if item == INIT:
            for index, row in enumerate(rows):
                vs.AddChoice(dialog, 12, row[1], index)
            vs.SelectChoice(dialog, 12, 0, True)
        elif item == 12:
            vs.SetItemText(dialog, 14, str(rows[_choice(dialog, 12)][2]).replace(".", ","))
        elif item == 1:
            value = rows[_choice(dialog, 12)][0]
            result["value"] = {
                "pipe_id": value["id"],
                "upper_invert_m": _float(dialog, 14, "Obere Absturzhöhe"),
                "lower_invert_m": _float(dialog, 16, "Untere Absturzhöhe"),
            }
        return item
    return result["value"] if _run(dialog, handler) == 1 else None


def terminal_dialog(structure_type, preferences):
    """Settings for a floor drain or a symbol-free house connection."""
    floor = structure_type == "floor_drain"
    if structure_type not in ("floor_drain", "house"):
        raise core.SewerError("Unbekannter Anschluss-Endpunkt.")
    dialog = vs.CreateResizableLayout(
        _title("Bodenablauf" if floor else "Hausanschluss"),
        True, "Zeichnen", "Abbrechen", True, True)
    vs.CreateStyledStatic(
        dialog, 10,
        ("BODENABLAUF  |  Vom Ablauf zur Hauptleitung zeichnen" if floor else
         "HAUSANSCHLUSS  |  Vom freien Ende zur Hauptleitung zeichnen"), -1, TITLE_STYLE)
    vs.CreateStaticText(dialog, 11,
                        "Der letzte mit Doppelklick gesetzte Punkt muss auf der bestehenden Hauptleitung liegen. "
                        "Dort wird automatisch der Stutzen erzeugt.", 78)
    vs.CreateStaticText(dialog, 12, "Kanalart:", -1)
    vs.CreatePullDownMenu(dialog, 13, 24)
    vs.CreateStaticText(dialog, 14, "Anschlussleitung DN:", -1)
    vs.CreatePullDownMenu(dialog, 15, 24)
    vs.CreateStaticText(dialog, 16, "Material:", -1)
    vs.CreatePullDownMenu(dialog, 17, 24)
    vs.CreateStaticText(dialog, 18,
                        "Oberkante Ablauf [m] (leer = KD des nächsten Schachts):" if floor else
                        "Höhe des freien Anschlusspunktes [m]:", -1)
    vs.CreateEditText(dialog, 19, "", 18)
    vs.CreateStaticText(dialog, 20, "Anschlussart am Hauptkanal:", -1)
    vs.CreatePullDownMenu(dialog, 21, 30)
    vs.CreateStaticText(dialog, 22, "Breite des 3D-Ersatzkastens [m]:", -1)
    vs.CreateEditText(dialog, 23, str(preferences["floor_drain_width_m"]).replace(".", ","), 18)
    vs.CreateStaticText(dialog, 24, "Tiefe des 3D-Ersatzkastens [m]:", -1)
    vs.CreateEditText(dialog, 25, str(preferences["floor_drain_depth_m"]).replace(".", ","), 18)
    vs.CreateCheckBox(dialog, 26, "Bodenablaufsymbol aus Dokument oder Bibliothek verwenden")
    vs.CreateResourcePopup(dialog, 27, 44)
    vs.CreateCheckBox(dialog, 28, "Gewähltes Symbol besitzt bereits einen 3D-Anteil")
    vs.SetFirstLayoutItem(dialog, 10)
    vs.SetBelowItem(dialog, 10, 11, 0, 6)
    previous = 11
    for label, field in ((12, 13), (14, 15), (16, 17), (18, 19), (20, 21)):
        vs.SetBelowItem(dialog, previous, label, 0, 6)
        vs.SetRightItem(dialog, label, field, 8, 0)
        previous = label
    vs.SetBelowItem(dialog, previous, 22, 0, 6)
    vs.SetRightItem(dialog, 22, 23, 8, 0)
    vs.SetBelowItem(dialog, 22, 24, 0, 6)
    vs.SetRightItem(dialog, 24, 25, 8, 0)
    vs.SetBelowItem(dialog, 24, 26, 0, 6)
    vs.SetBelowItem(dialog, 26, 27, 0, 4)
    vs.SetBelowItem(dialog, 27, 28, 0, 4)
    for item in (22, 23, 24, 25, 26, 27, 28):
        vs.EnableItem(dialog, item, floor)
    resource_id = "PD.Kanal.Bodenablauf"
    result = {"value": None}
    preferred_dn = preferences["floor_drain_dn_mm"] if floor else preferences["house_connection_dn_mm"]
    dn_values = sorted(set(preferences["dns"] + [preferred_dn]))
    alignments = (("Sohlgleich", "invert"), ("Achsgleich", "axis"),
                  ("Kämpfergleich", "springline"), ("Scheitelgleich", "crown"))

    def handler(item, _data):
        if item == INIT:
            for index, kind in enumerate(core.KINDS):
                vs.AddChoice(dialog, 13, kind, index)
            for index, dn in enumerate(dn_values):
                vs.AddChoice(dialog, 15, "DN %d" % dn, index)
            for index, material in enumerate(preferences["materials"]):
                vs.AddChoice(dialog, 17, material, index)
            for index, row in enumerate(alignments):
                vs.AddChoice(dialog, 21, row[0], index)
            vs.SelectChoice(dialog, 13, list(core.KINDS).index(preferences["default_kind"]), True)
            vs.SelectChoice(dialog, 15, dn_values.index(preferred_dn), True)
            vs.SelectChoice(dialog, 17, preferences["materials"].index(preferences["default_material"]), True)
            vs.SelectChoice(dialog, 21, 0, True)
            if floor:
                _init_cover_resource(dialog, 27, resource_id, preferences["floor_drain_symbol"])
                vs.SetBooleanItem(dialog, 26, bool(preferences["floor_drain_symbol"]))
                vs.SetBooleanItem(dialog, 28, bool(preferences["floor_drain_symbol_has_3d"]))
                vs.EnableItem(dialog, 27, bool(preferences["floor_drain_symbol"]))
                vs.EnableItem(dialog, 28, bool(preferences["floor_drain_symbol"]))
        elif item == 26 and floor:
            vs.EnableItem(dialog, 27, _selected(dialog, 26))
            vs.EnableItem(dialog, 28, _selected(dialog, 26))
        elif item == 1:
            raw_height = str(vs.GetItemText(dialog, 19) or "").strip().replace(",", ".")
            if not floor and not raw_height:
                vs.AlrtDialog("Beim Hausanschluss muss die Höhe des freien Anschlusspunktes angegeben werden.")
                return -1
            value = {
                "structure_type": structure_type,
                "kind": core.KINDS[_choice(dialog, 13)],
                "dn_mm": dn_values[_choice(dialog, 15)],
                "material": preferences["materials"][_choice(dialog, 17)],
                "terminal_top_m": core.number(raw_height, "Anschlusshöhe") if raw_height else None,
                "alignment": alignments[_choice(dialog, 21)][1],
                "terminal_width_m": _float(dialog, 23, "Breite") if floor else 0.30,
                "terminal_depth_m": _float(dialog, 25, "Tiefe") if floor else 0.60,
                "terminal_symbol": _cover_symbol(resource_id, _selected(dialog, 26)) if floor else "",
                "terminal_symbol_has_3d": bool(_selected(dialog, 28)) if floor else False,
            }
            result["value"] = value
        return item
    return result["value"] if _run(dialog, handler) == 1 else None
