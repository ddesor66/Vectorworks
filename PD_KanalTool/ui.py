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
        # Reserve the normal width of Vectorworks' docked right palettes.
        palette_width = max(280, min(420, int(screen_width * 0.22)))
        x = max(left + 12, right - palette_width - width - 12)
        y = max(top + 12, min(top + 42, bottom - height - 12))
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


def _height_text(value):
    """Format a visible elevation without changing its stored precision."""
    return ("%.2f" % float(value)).replace(".", ",")


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


def home_dialog(source_count, managed_count, managed_role=None, selected_shaft_count=0,
                selected_pipe_count=0):
    del managed_role, selected_shaft_count, selected_pipe_count
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
    vs.CreateStaticText(
        dialog, 15,
        ("Objektbezogene Befehle für die %d markierte(n) Kanalobjekt(e) stehen rechts in der "
         "Objekt-Info-Palette: bearbeiten, anschließen, Schacht–Schacht, einsetzen, vereinigen, "
         "Schachtblatt und löschen." % managed_count
         if managed_count else
         "Objektbezogene Befehle erscheinen nach Auswahl einer Haltung oder eines Schachts rechts in der Objekt-Info-Palette."),
        82)
    vs.SetFirstLayoutItem(dialog, 10)
    vs.SetBelowItem(dialog, 10, 11, 0, 6)
    vs.SetBelowItem(dialog, 11, 12, 0, 8)
    vs.SetRightItem(dialog, 12, 13, 8, 0)
    vs.SetBelowItem(dialog, 12, 14, 0, 7)
    vs.SetBelowItem(dialog, 14, 15, 0, 5)
    # The two creation paths are deliberately stable and always visible.  A
    # missing source selection is reported after choosing the conversion
    # command instead of hiding the command from the user.
    actions = [
        ("Neue Kanalanlage durch Punkte zeichnen", "draw"),
        ("Vorhandene Linie, Polylinie oder Polygon in Kanalanlage umwandeln", "sources"),
        ("Rigolenbauwerk als einzelnes Element einsetzen", "rigole"),
        ("Bodenablauf setzen und vom Ablauf zur Hauptleitung zeichnen", "floor_drain"),
        ("Hausanschluss vom freien Ende zur Hauptleitung zeichnen", "house"),
        ("Kanalnetz prüfen", "validate"),
        ("Massenermittlung, Erdmassen, Verbau und Excel …", "quantities"),
        ("Farben, DN, Material und Darstellung einstellen", "settings"),
    ]
    result = {"value": None}
    state = {"choices_loaded": False}

    def handler(item, _data):
        if item == INIT and not state["choices_loaded"]:
            for index, row in enumerate(actions):
                vs.AddChoice(dialog, 13, row[0], index)
            vs.SelectChoice(dialog, 13, 0, True)
            state["choices_loaded"] = True
        elif item == 1:
            result["value"] = actions[_choice(dialog, 13)][1]
        return item
    return result["value"] if _run(dialog, handler) == 1 else None


def rigole_dialog(initial=None):
    """Collect the complete engineering and appearance data of one rigole."""
    current = copy.deepcopy(initial or {})
    current.setdefault("name", "")
    current.setdefault("length_m", 10.0)
    current.setdefault("width_m", 3.0)
    current.setdefault("height_m", 1.0)
    current.setdefault("bottom_m", 99.0)
    current.setdefault("terrain_top_m", 101.0)
    current.setdefault("rotation_deg", 0.0)
    current.setdefault("slope_angle_deg", 60.0)
    current.setdefault("fill_color", [36000, 52000, 65535])
    current.setdefault("pen_color", [0, 20000, 50000])
    current.setdefault("transparency_percent", 50.0)
    current.setdefault("note", "")
    editing = bool(initial)
    dialog = vs.CreateResizableLayout(
        _title("Rigolenbauwerk bearbeiten" if editing else "Rigolenbauwerk einsetzen"),
        True, "Übernehmen" if editing else "Einsetzen", "Abbrechen", True, True)
    vs.CreateStyledStatic(dialog, 10, "RIGOLE  |  Bauwerk, Rückhaltevolumen und Erdarbeiten", -1, TITLE_STYLE)
    controls = (
        (11, "Bezeichnung (leer = automatisch):", 12, current["name"]),
        (13, "Länge [m]:", 14, current["length_m"]),
        (15, "Breite [m]:", 16, current["width_m"]),
        (17, "Höhe [m]:", 18, current["height_m"]),
        (19, "Unterkante Rigole [m]:", 20, current["bottom_m"]),
        (21, "Oberkante Gelände [m]:", 22, current["terrain_top_m"]),
        (23, "Drehung im Grundriss [°]:", 24, current["rotation_deg"]),
        (27, "Transparenz der Füllung [%]:", 28, current["transparency_percent"]),
        (29, "Freier Beschriftungstext:", 30, current["note"]),
    )
    for label_id, label, field_id, value in controls:
        vs.CreateStaticText(dialog, label_id, label, -1)
        if field_id == 30:
            vs.CreateEditTextBox(
                dialog, field_id, str(value).replace("\n", "\r\n"), 52, 4)
        else:
            text = (_height_text(value) if field_id in (20, 22)
                    else str(value).replace(".", ","))
            vs.CreateEditText(dialog, field_id, text,
                              52 if field_id == 12 else 18)
    vs.CreateStaticText(dialog, 25, "Böschung der Baugrube:", -1)
    vs.CreatePullDownMenu(dialog, 26, 24)
    vs.CreateStaticText(dialog, 31, "Füllfarbe:", -1)
    vs.CreateColorPopup(dialog, 32, 24)
    vs.CreateStaticText(dialog, 33, "Umrahmungsfarbe:", -1)
    vs.CreateColorPopup(dialog, 34, 24)
    vs.CreateStaticText(dialog, 35, "", 78)
    vs.CreateStaticText(
        dialog, 36,
        "Die Beschriftung wird zuerst mittig eingesetzt. Nach dem Verschieben erhält sie automatisch einen Rahmen mit Bezugslinie zur Rigole.",
        82)
    vs.SetFirstLayoutItem(dialog, 10)
    previous = 10
    for label_id, _label, field_id, _value in controls[:7]:
        vs.SetBelowItem(dialog, previous, label_id, 0, 6)
        vs.SetRightItem(dialog, label_id, field_id, 8, 0)
        previous = label_id
    vs.SetBelowItem(dialog, previous, 25, 0, 6)
    vs.SetRightItem(dialog, 25, 26, 8, 0)
    vs.SetBelowItem(dialog, 25, 31, 0, 6)
    vs.SetRightItem(dialog, 31, 32, 8, 0)
    vs.SetBelowItem(dialog, 31, 33, 0, 6)
    vs.SetRightItem(dialog, 33, 34, 8, 0)
    vs.SetBelowItem(dialog, 33, 27, 0, 6)
    vs.SetRightItem(dialog, 27, 28, 8, 0)
    vs.SetBelowItem(dialog, 27, 29, 0, 6)
    vs.SetRightItem(dialog, 29, 30, 8, 0)
    vs.SetBelowItem(dialog, 29, 35, 0, 7)
    vs.SetBelowItem(dialog, 35, 36, 0, 5)
    slopes = (45.0, 60.0)
    result = {"value": None}

    def preview():
        try:
            length = _float(dialog, 14, "Rigolenlänge")
            width = _float(dialog, 16, "Rigolenbreite")
            height = _float(dialog, 18, "Rigolenhöhe")
            gross = length * width * height
            vs.SetItemText(
                dialog, 35,
                "Automatische Berechnung: Rigolenvolumen %.2f m³ | Rückhaltevolumen bei 95 %% Füllvolumen %.2f m³"
                % (gross, gross * core.RIGOLE_FILL_FACTOR))
        except (core.SewerError, ValueError):
            vs.SetItemText(dialog, 35, "Automatische Berechnung folgt nach vollständiger Zahleneingabe.")

    def handler(item, _data):
        if item == INIT:
            for index, slope in enumerate(slopes):
                vs.AddChoice(dialog, 26, "%d°" % int(slope), index)
            selected_slope = (slopes.index(float(current["slope_angle_deg"]))
                              if float(current["slope_angle_deg"]) in slopes else 1)
            vs.SelectChoice(dialog, 26, selected_slope, True)
            vs.SetColorChoice(dialog, 32, vs.RGBToColorIndex(*current["fill_color"]))
            vs.SetColorChoice(dialog, 34, vs.RGBToColorIndex(*current["pen_color"]))
            preview()
        elif item in (14, 16, 18):
            preview()
        elif item == 1:
            candidate = dict(current)
            candidate.update(
                schema=core.SCHEMA, id=str(candidate.get("id") or "preview"),
                name=str(vs.GetItemText(dialog, 12) or "").strip() or "RIG.001",
                x_m=float(candidate.get("x_m", 0.0)), y_m=float(candidate.get("y_m", 0.0)),
                length_m=_float(dialog, 14, "Rigolenlänge"),
                width_m=_float(dialog, 16, "Rigolenbreite"),
                height_m=_float(dialog, 18, "Rigolenhöhe"),
                bottom_m=_float(dialog, 20, "Unterkante Rigole"),
                terrain_top_m=_float(dialog, 22, "Oberkante Gelände"),
                rotation_deg=_float(dialog, 24, "Rigolendrehung"),
                slope_angle_deg=slopes[_choice(dialog, 26)],
                fill_color=list(vs.ColorIndexToRGB(vs.GetColorChoice(dialog, 32))),
                pen_color=list(vs.ColorIndexToRGB(vs.GetColorChoice(dialog, 34))),
                transparency_percent=_float(dialog, 28, "Rigolen-Transparenz"),
                note=str(vs.GetItemText(dialog, 30) or "").strip())
            normalized = core.validate_rigole(candidate)
            result["value"] = {key: normalized[key] for key in (
                "name", "length_m", "width_m", "height_m", "bottom_m",
                "terrain_top_m", "rotation_deg", "slope_angle_deg", "fill_color",
                "pen_color", "transparency_percent", "note")}
        return item
    return result["value"] if _run(dialog, handler, (650, 690)) == 1 else None


def rigole_connection_height_dialog(rigole):
    value = core.validate_rigole(rigole)
    dialog = vs.CreateResizableLayout(
        _title("Kanal an Rigole anschließen"), True, "Weiter", "Abbrechen", True, True)
    vs.CreateStyledStatic(dialog, 10, "RIGOLENANSCHLUSS  |  Anschlusshöhe", -1, TITLE_STYLE)
    vs.CreateStaticText(
        dialog, 11,
        "%s: zulässiger Bereich %s m bis %s m. Im nächsten Schritt Leitungseigenschaften festlegen und zuerst die Anschlussstelle auf der Rigole anklicken."
        % (value["name"], _height_text(value["bottom_m"]),
           _height_text(value["top_m"])), 76)
    vs.CreateStaticText(dialog, 12, "Anschlusshöhe KS [m]:", -1)
    vs.CreateEditText(dialog, 13, _height_text(value["bottom_m"]), 18)
    vs.SetFirstLayoutItem(dialog, 10)
    vs.SetBelowItem(dialog, 10, 11, 0, 6)
    vs.SetBelowItem(dialog, 11, 12, 0, 7)
    vs.SetRightItem(dialog, 12, 13, 8, 0)
    result = {"value": None}

    def handler(item, _data):
        if item == 1:
            height = _float(dialog, 13, "Anschlusshöhe an der Rigole")
            if not value["bottom_m"] - 1e-9 <= height <= value["top_m"] + 1e-9:
                vs.AlrtDialog("Die Anschlusshöhe muss innerhalb der Rigolenhöhe liegen.")
                return -1
            result["value"] = height
        return item
    return result["value"] if _run(dialog, handler, (560, 300)) == 1 else None


def shaft_connection_dialog(first, second, preferences):
    """Collect the few properties needed for a holding between two shafts."""
    preferences = settings.validate(preferences)
    first = core.validate_shaft(first, allow_hidden=True)
    second = core.validate_shaft(second, allow_hidden=True)
    if first["kind"] != second["kind"]:
        raise core.SewerError("Zwei Schächte unterschiedlicher Kanalart können nicht verbunden werden.")
    upstream, downstream = first, second
    if (downstream["ks_m"] > upstream["ks_m"] or
            downstream["ks_m"] == upstream["ks_m"] and
            (downstream["name"], downstream["id"]) < (upstream["name"], upstream["id"])):
        upstream, downstream = downstream, upstream

    dialog = vs.CreateResizableLayout(
        _title("Schächte mit Haltung verbinden"), True, "Verbinden", "Abbrechen", True, True)
    vs.CreateStyledStatic(dialog, 10, "HALTUNG  |  Zwei vorhandene Schächte", -1, TITLE_STYLE)
    vs.CreateStaticText(
        dialog, 11,
        "%s (KS %s m)  →  %s (KS %s m)\nDie Fließrichtung wird automatisch von der höheren zur tieferen Sohle angelegt." %
        (upstream["name"], _height_text(upstream["ks_m"]),
         downstream["name"], _height_text(downstream["ks_m"])), 68)
    vs.CreateStaticText(dialog, 12, "Nennweite:", -1)
    vs.CreatePullDownMenu(dialog, 13, 24)
    vs.CreateStaticText(dialog, 14, "Material:", -1)
    vs.CreatePullDownMenu(dialog, 15, 24)
    vs.CreateStaticText(dialog, 16, "Darstellung:", -1)
    vs.CreatePullDownMenu(dialog, 17, 34)
    vs.CreateCheckBox(dialog, 18, "Zusätzliches 3D-Rohr erzeugen")
    vs.CreateStaticText(
        dialog, 19,
        "Die Haltung wird an beiden vorhandenen Schächten angeschlossen. "
        "Schachtsohlen und Schachtbezeichnungen bleiben unverändert.", 68)
    vs.SetFirstLayoutItem(dialog, 10)
    vs.SetBelowItem(dialog, 10, 11, 0, 6)
    vs.SetBelowItem(dialog, 11, 12, 0, 8)
    vs.SetRightItem(dialog, 12, 13, 8, 0)
    vs.SetBelowItem(dialog, 12, 14, 0, 6)
    vs.SetRightItem(dialog, 14, 15, 8, 0)
    vs.SetBelowItem(dialog, 14, 16, 0, 6)
    vs.SetRightItem(dialog, 16, 17, 8, 0)
    vs.SetBelowItem(dialog, 16, 18, 0, 7)
    vs.SetBelowItem(dialog, 18, 19, 0, 6)
    result = {"value": None}
    graphics = (("Einliniengrafik", "single_line"),
                ("Gefüllte Doppelliniengrafik mit Achslinie", "double_line"))

    def handler(item, _data):
        if item == INIT:
            for index, value in enumerate(preferences["dns"]):
                vs.AddChoice(dialog, 13, "DN %d" % value, index)
            vs.SelectChoice(
                dialog, 13, preferences["dns"].index(preferences["default_dn_mm"]), True)
            for index, value in enumerate(preferences["materials"]):
                vs.AddChoice(dialog, 15, value, index)
            vs.SelectChoice(
                dialog, 15, preferences["materials"].index(preferences["default_material"]), True)
            for index, row in enumerate(graphics):
                vs.AddChoice(dialog, 17, row[0], index)
            vs.SelectChoice(
                dialog, 17,
                [row[1] for row in graphics].index(preferences["graphics_mode"]), True)
            vs.SetBooleanItem(dialog, 18, preferences["draw_3d"])
        elif item == 1:
            result["value"] = {
                "dn_mm": preferences["dns"][_choice(dialog, 13)],
                "material": preferences["materials"][_choice(dialog, 15)],
                "graphics_mode": graphics[_choice(dialog, 17)][1],
                "wall_thickness_mm": preferences["pipe_wall_thickness_mm"],
                "hollow_3d": preferences["hollow_3d"],
                "draw_3d": _selected(dialog, 18),
            }
        return item

    return result["value"] if _run(dialog, handler, (500, 340)) == 1 else None


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
        "%d markierte Kanalobjekt(e) wirklich löschen? Bei einem Schacht oder einer Rigole werden auch die angeschlossenen Rohre gelöscht."
        % int(count)))


def confirm_flow_reversal(descriptions):
    """Confirm height-induced flow reversals before any model is committed."""
    descriptions = tuple(str(value) for value in descriptions if str(value).strip())
    count = len(descriptions)
    if not count:
        return True
    shown = descriptions[:8]
    details = "\n".join("• " + value for value in shown)
    if count > len(shown):
        details += "\n• … und %d weitere Haltung(en)" % (count - len(shown))
    return bool(vs.YNDialog(
        "Durch die Höhenänderung ändert sich die Fließrichtung bei %d Haltung(en):\n\n"
        "%s\n\nSoll die Fließrichtung jetzt umgekehrt werden?\n"
        "Zu-/Ablaufzuordnung, Gefälle, Fließrichtungspfeil und Beschriftungen werden angepasst."
        % (count, details)))


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
    layouts = (("Technische Angaben in einer Zeile", "one_line"),
               ("Technische Angaben in zwei Zeilen", "two_line"))
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
              (70, "Beschriftungsdrehung [°]:"),
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
    current_mode = current.get("calculation_mode", "slope")
    for item, value, width in (
            (19, current.get("start_invert_m", 100.0), 18),
            (23, current.get("calculation_value", current.get("end_invert_m", 1.5)), 18),
            (26, current.get("cover_height_m", current.get("start_invert_m", 100.0) + preferences["cover_offset_m"]), 18),
            (28, current.get("shaft_diameter_m", preferences["shaft_diameter_m"]), 18),
            (51, current.get("shaft_wall_thickness_m", preferences["shaft_wall_thickness_m"]), 18),
            (43, current.get("fillet_radius_m", preferences["fillet_radius_m"]), 18),
            (47, current.get("flow_arrow_scale", preferences["flow_arrow_scale"]), 18),
            (45, current.get("label_width_m", 0.0), 18),
            (71, current.get("label_rotation_deg", preferences["label_rotation_deg"]), 18),
             (41, current.get("name", ""), 34)):
        is_height = item in (19, 26) or (item == 23 and current_mode == "end")
        vs.CreateEditText(dialog, item,
                          _height_text(value) if is_height else str(value).replace(".", ","),
                          width)
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
    for label, field in ((31, 32), (42, 43), (46, 47), (33, 34), (44, 45),
                         (70, 71)):
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
            vs.SetItemText(dialog, 19, _height_text(reference))

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
                "label_rotation_deg": _float(dialog, 71, "Beschriftungsdrehung"),
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


def _shaft_inlet_rows(values):
    """Normalize legacy numeric values and live per-pipe inlet records."""
    rows = []
    for index, source in enumerate(tuple(values or ()), 1):
        if isinstance(source, dict):
            pipe_id = str(source.get("pipe_id") or source.get("connection_id") or
                          "inlet-%d" % index)
            tag = str(source.get("tag") or "Z%d" % index)
            pipe_name = str(source.get("pipe_name") or "").strip()
            invert_m = core.number(source.get("invert_m"), "Zulaufsohle %s" % tag)
        else:
            pipe_id = "inlet-%d" % index
            tag = "Z%d" % index
            pipe_name = ""
            invert_m = core.number(source, "Zulaufsohle %s" % tag)
        rows.append({
            "pipe_id": pipe_id,
            "tag": tag,
            "pipe_name": pipe_name,
            "invert_m": invert_m,
        })
    return tuple(rows)


def shaft_dialog(shaft, preferences, inlet_inverts=(), outlet_inverts=()):
    current = core.validate_shaft(shaft, allow_hidden=True)
    inlet_rows = _shaft_inlet_rows(inlet_inverts)
    incoming = tuple(row["invert_m"] for row in inlet_rows)
    outgoing = tuple(core.number(value, "Ablaufsohle") for value in outlet_inverts)
    inlet_value = min(incoming) if incoming else current["ks_m"]
    outlet_value = min(outgoing) if outgoing else current["ks_m"]
    kinds = list(core.KINDS)
    shaft_pen_colors = preferences.get("shaft_pen_colors", preferences["colors"])
    shaft_fill_colors = preferences.get("shaft_fill_colors", shaft_pen_colors)
    shaft_transparencies = preferences.get(
        "shaft_fill_transparency_percent", {kind: 50.0 for kind in kinds})
    dialog = vs.CreateResizableLayout(_title("Kanalschacht bearbeiten"), True,
                                      "Übernehmen", "Abbrechen", True, True)
    vs.CreateStyledStatic(dialog, 10, "SCHACHT  |  Lage bleibt direkt verschiebbar", -1, TITLE_STYLE)
    rows = ((11, "Schachtname:", 12, current["name"]),
            (15, "Deckelhöhe KD [m]:", 16, current["kd_m"]),
            (34, "Kanalsohle Ablauf [m]:", 35, outlet_value),
            (19, "Lichter Innendurchmesser [m]:", 20, current["diameter_m"]))
    height_fields = (16, 35)
    for label, text, field, value in rows:
        vs.CreateStaticText(dialog, label, text, -1)
        vs.CreateEditText(dialog, field,
                          _height_text(value) if field in height_fields
                          else str(value).replace(".", ","), 24)
    vs.CreateStaticText(dialog, 13, "Kanalart:", -1)
    vs.CreatePullDownMenu(dialog, 14, 20)
    vs.CreateStaticText(dialog, 38, "Schachtbauart:", -1)
    vs.CreatePullDownMenu(dialog, 39, 28)
    vs.CreateStaticText(dialog, 40, "Beton-Wandstärke [m]:", -1)
    vs.CreateEditText(dialog, 41, str(current["wall_thickness_m"]).replace(".", ","), 24)
    vs.CreateCheckBox(dialog, 21, "Individuelle Schacht-Linienfarbe")
    vs.CreateColorPopup(dialog, 22, 22)
    vs.CreateCheckBox(dialog, 55, "Individuelle Schachtfüllung")
    vs.CreateColorPopup(dialog, 56, 22)
    vs.CreateStaticText(dialog, 57, "Fülltransparenz [%]:", -1)
    vs.CreateEditText(dialog, 58, "", 12)
    vs.CreateStaticText(dialog, 24, "Schachtdeckel-Ø [m]:", -1)
    vs.CreateEditText(dialog, 25, str(current["cover_diameter_m"]).replace(".", ","), 24)
    vs.CreateStaticText(dialog, 26, "Schachtdeckellage:", -1)
    vs.CreatePullDownMenu(dialog, 27, 42)
    vs.CreateStaticText(dialog, 28, "Symboldrehung [°]:", -1)
    vs.CreateEditText(dialog, 29, str(current["cover_rotation_deg"]).replace(".", ","), 24)
    vs.CreateCheckBox(dialog, 30, "2D-Symbol aus Dokument oder Bibliothek verwenden")
    vs.CreateResourcePopup(dialog, 31, 42)
    vs.CreateStaticText(dialog, 32, "Bauarttext (B, PP oder frei):", -1)
    vs.CreateEditText(dialog, 33, current["construction_label"], 24)
    vs.CreateStaticText(dialog, 42, "Zusatztext unter Schachtname:", -1)
    vs.CreateEditText(dialog, 43, current.get("note", ""), 24)
    # The editor is deliberately divided into short native tabs. Inlets are
    # arranged as a compact multi-column matrix: every value remains visible
    # at once without an unbounded single column or a scrolling selector.
    vs.CreateTabControl(dialog, 50)
    vs.CreateGroupBox(dialog, 51, "Allgemein", False)
    vs.CreateGroupBox(dialog, 52, "Anschlusshöhen", False)
    vs.CreateGroupBox(dialog, 53, "Schachtbau", False)
    vs.CreateGroupBox(dialog, 54, "Deckel und Darstellung", False)

    def inlet_caption(row, inlet_height=None, outlet_height=None):
        target = " · %s" % row["pipe_name"] if row["pipe_name"] else ""
        offset = " · ΔA —"
        if inlet_height is not None and outlet_height is not None:
            delta_cm = (float(inlet_height) - float(outlet_height)) * 100.0
            offset = (" · ΔA %+.1f cm" % delta_cm).replace(".", ",")
        return "%s%s%s" % (row["tag"], target, offset)

    inlet_controls = []
    for index, row in enumerate(inlet_rows):
        label_id = 100 + index * 2
        field_id = label_id + 1
        vs.CreateStaticText(
            dialog, label_id,
            inlet_caption(
                row, row["invert_m"], outlet_value if outgoing else None), -1)
        vs.CreateEditText(
            dialog, field_id, _height_text(row["invert_m"]), 13)
        inlet_controls.append((label_id, field_id, row))
    if not inlet_controls:
        vs.CreateStaticText(dialog, 45, "Keine Zulaufhaltung angeschlossen.", -1)
    vs.CreateCheckBox(dialog, 36, "Alle Zu- und Abläufe mit gleicher Höhe")
    vs.CreateStaticText(
        dialog, 37,
        "Alle Zulaufhöhen sind gleichzeitig sichtbar. Jede Höhe gehört nur zur angegebenen Haltung. "
        "ΔA = Zulaufsohle minus Ablaufsohle in cm; positiv bedeutet Zulauf höher. Gefälle, "
        "Fließrichtung und Beschriftungen werden gemeinsam geprüft.", 68)
    vs.CreateStaticText(dialog, 23,
                        "Beim Verschieben dieses Schachtobjekts werden angeschlossene Rohre automatisch neu aufgebaut.", 64)
    vs.SetFirstLayoutItem(dialog, 10)
    vs.SetBelowItem(dialog, 10, 50, 0, 7)

    # Allgemein.
    vs.SetFirstGroupItem(dialog, 51, 11)
    previous = None
    for label, field in ((11, 12), (42, 43), (32, 33), (13, 14), (15, 16)):
        if previous is not None:
            vs.SetBelowItem(dialog, previous, label, 0, 6)
        vs.SetRightItem(dialog, label, field, 8, 0)
        previous = label
    vs.SetBelowItem(dialog, previous, 23, 0, 6)

    # Anschlusshöhen: at most four compact cards per row. Even the supported
    # maximum of 24 connections therefore needs only six matrix rows.
    inlet_columns = min(4, max(1, len(inlet_controls)))
    if inlet_controls:
        vs.SetFirstGroupItem(dialog, 52, inlet_controls[0][0])
        for index, (label, field, _row) in enumerate(inlet_controls):
            column = index % inlet_columns
            if column:
                vs.SetRightItem(
                    dialog, inlet_controls[index - 1][0], label, 14, 0)
            elif index:
                vs.SetBelowItem(
                    dialog, inlet_controls[index - inlet_columns][1], label, 0, 5)
            vs.SetBelowItem(dialog, label, field, 0, 2)
        final_row_start = ((len(inlet_controls) - 1) // inlet_columns) * inlet_columns
        height_anchor = inlet_controls[final_row_start][1]
    else:
        vs.SetFirstGroupItem(dialog, 52, 45)
        height_anchor = 45
    vs.SetBelowItem(dialog, height_anchor, 34, 0, 7)
    vs.SetRightItem(dialog, 34, 35, 8, 0)
    vs.SetBelowItem(dialog, 34, 36, 0, 5)
    vs.SetBelowItem(dialog, 36, 37, 0, 3)

    # Schachtbau.
    vs.SetFirstGroupItem(dialog, 53, 19)
    previous = None
    for label, field in ((19, 20), (38, 39), (40, 41)):
        if previous is not None:
            vs.SetBelowItem(dialog, previous, label, 0, 6)
        vs.SetRightItem(dialog, label, field, 8, 0)
        previous = label

    # Deckel und Darstellung.
    vs.SetFirstGroupItem(dialog, 54, 24)
    previous = None
    for label, field in ((24, 25), (26, 27), (28, 29)):
        if previous is not None:
            vs.SetBelowItem(dialog, previous, label, 0, 6)
        vs.SetRightItem(dialog, label, field, 8, 0)
        previous = label
    vs.SetBelowItem(dialog, previous, 30, 0, 6)
    vs.SetBelowItem(dialog, 30, 31, 0, 4)
    vs.SetBelowItem(dialog, 31, 21, 0, 6)
    vs.SetRightItem(dialog, 21, 22, 8, 0)
    vs.SetBelowItem(dialog, 21, 55, 0, 6)
    vs.SetRightItem(dialog, 55, 56, 8, 0)
    vs.SetBelowItem(dialog, 55, 57, 0, 5)
    vs.SetRightItem(dialog, 57, 58, 8, 0)
    for pane in (51, 52, 53, 54):
        vs.CreateTabPane(dialog, 50, pane)
    vs.SetEdgeBinding(dialog, 50, True, True, True, True)
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

    def update_construction_label():
        value = str(vs.GetItemText(dialog, 33) or "").strip()
        if value in ("", "B", "PP"):
            material = shaft_materials[_choice(dialog, 39)][1]
            vs.SetItemText(dialog, 33, "B" if material == "concrete" else "PP")

    def update_inlet_offsets():
        try:
            outlet = _float(dialog, 35, "Ablaufsohle") if outgoing else None
        except core.SewerError:
            outlet = None
        for label, field, row in inlet_controls:
            try:
                inlet = _float(dialog, field, "Zulaufsohle %s" % row["tag"])
            except core.SewerError:
                inlet = None
            vs.SetItemText(dialog, label, inlet_caption(row, inlet, outlet))

    def update_graphic_defaults():
        kind = kinds[_choice(dialog, 14)]
        if not _selected(dialog, 21):
            vs.SetColorChoice(
                dialog, 22, vs.RGBToColorIndex(*shaft_pen_colors[kind]))
        if not _selected(dialog, 55):
            vs.SetColorChoice(
                dialog, 56, vs.RGBToColorIndex(*shaft_fill_colors[kind]))
            vs.SetItemText(
                dialog, 58,
                str(shaft_transparencies[kind]).replace(".", ","))

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
            vs.EnableItem(dialog, 35, bool(outgoing))
            vs.EnableItem(dialog, 36, bool(incoming and outgoing))
            pen_override = current.get(
                "pen_color_override", current.get("color_override"))
            fill_override = current.get("fill_color_override")
            transparency_override = current.get(
                "fill_transparency_percent_override")
            vs.SetBooleanItem(dialog, 21, pen_override is not None)
            vs.SetColorChoice(
                dialog, 22, vs.RGBToColorIndex(*(
                    pen_override or shaft_pen_colors[current["kind"]])))
            vs.SetBooleanItem(
                dialog, 55,
                fill_override is not None or transparency_override is not None)
            vs.SetColorChoice(
                dialog, 56, vs.RGBToColorIndex(*(
                    fill_override or shaft_fill_colors[current["kind"]])))
            vs.SetItemText(
                dialog, 58, str(
                    transparency_override if transparency_override is not None
                    else shaft_transparencies[current["kind"]]).replace(".", ","))
            vs.EnableItem(dialog, 22, pen_override is not None)
            for control in (56, 57, 58):
                vs.EnableItem(
                    dialog, control,
                    fill_override is not None or transparency_override is not None)
            update_cover_state()
            update_inlet_offsets()
        elif item == 14:
            update_graphic_defaults()
        elif item == 21:
            vs.EnableItem(dialog, 22, _selected(dialog, 21))
            update_graphic_defaults()
        elif item == 55:
            enabled = _selected(dialog, 55)
            for control in (56, 57, 58):
                vs.EnableItem(dialog, control, enabled)
            update_graphic_defaults()
        elif item == 39:
            update_construction_label()
            update_cover_state()
        elif item in (20, 41):
            update_cover_state()
        elif item == 30:
            update_cover_state()
        elif item in (35, 36) or item in tuple(
                field for _label, field, _row in inlet_controls):
            same = _selected(dialog, 36)
            if item != 35 and same and inlet_controls:
                source_value = str(vs.GetItemText(dialog, inlet_controls[0][1]) or "")
                for _label, field, _row in inlet_controls[1:]:
                    vs.SetItemText(dialog, field, source_value)
                vs.SetItemText(dialog, 35, source_value)
            for _label, field, _row in inlet_controls[1:]:
                vs.EnableItem(dialog, field, not same)
            vs.EnableItem(dialog, 35, bool(outgoing) and not same)
            update_inlet_offsets()
        elif item == 1:
            try:
                # Some Vectorworks dialog states return an empty string for an
                # unchanged first edit field. Numeric edits must not erase the
                # already valid shaft identity in that case.
                name = _shaft_name_text(dialog, 12, current["name"])
                inlet_values = {
                    row["pipe_id"]: _float(
                        dialog, field, "Zulaufsohle %s" % row["tag"])
                    for _label, field, row in inlet_controls}
                inlet = min(inlet_values.values()) if inlet_values else inlet_value
                outlet = _float(dialog, 35, "Ablaufsohle") if outgoing else outlet_value
                equal = bool(incoming and outgoing and _selected(dialog, 36))
                if equal:
                    common = inlet_values[inlet_rows[0]["pipe_id"]]
                    inlet_values = {key: common for key in inlet_values}
                    inlet = common
                    outlet = common
                endpoint_values = list(inlet_values.values()) + ([outlet] if outgoing else [])
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
                pen_override = (
                    list(vs.ColorIndexToRGB(vs.GetColorChoice(dialog, 22)))
                    if _selected(dialog, 21) else None)
                fill_override = (
                    list(vs.ColorIndexToRGB(vs.GetColorChoice(dialog, 56)))
                    if _selected(dialog, 55) else None)
                transparency_override = (
                    _float(dialog, 58, "Schacht-Fülltransparenz")
                    if _selected(dialog, 55) else None)
                value.update(name=name,
                             note=str(vs.GetItemText(dialog, 43) or "").strip(),
                             construction_label=str(vs.GetItemText(dialog, 33) or "").strip(),
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
                             color_override=pen_override,
                             pen_color_override=pen_override,
                             fill_color_override=fill_override,
                             fill_transparency_percent_override=
                             transparency_override)
                result["value"] = {
                    "shaft": core.validate_shaft(value, allow_hidden=True),
                    "inlet_invert_m": inlet,
                    "inlet_inverts_m": inlet_values,
                    "outlet_invert_m": outlet,
                    "equal_inverts": equal,
                    "inlet_changed": any(
                        abs(inlet_values[row["pipe_id"]] - row["invert_m"]) > 1e-9
                        for row in inlet_rows),
                    "inlet_changed_by_pipe": {
                        row["pipe_id"]: (
                            abs(inlet_values[row["pipe_id"]] - row["invert_m"]) > 1e-9)
                        for row in inlet_rows},
                    "outlet_changed": bool(outgoing) and (
                        equal or abs(outlet - outlet_value) > 1e-9),
                }
            except core.SewerError as error:
                vs.AlrtDialog(str(error))
                result["value"] = None
                return -1
        return item
    preferred_width = min(860, 360 + inlet_columns * 125)
    return result["value"] if _run(
        dialog, handler, (preferred_width, 520)) == 1 else None


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
        (_height_text(abs(delta)), direction, count), 72)
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


def preferences_dialog(preferences, default_scope="save"):
    current = copy.deepcopy(preferences)
    dialog = vs.CreateResizableLayout(_title("Kanalanlage – Voreinstellungen"), True,
                                      "Speichern", "Abbrechen", True, True)
    vs.CreateStyledStatic(dialog, 10, "VOREINSTELLUNGEN  |  Kanalnetz", -1, TITLE_STYLE)

    # Native tab panes keep the dialog usable on smaller screens.  Every pane
    # contains at most seven rows; Vectorworks therefore never has to create
    # the former screen-high single column.
    vs.CreateGroupBox(dialog, 101, "Kataloge und Farben", False)
    for index, kind in enumerate(core.KINDS):
        label, field = 11 + index * 2, 12 + index * 2
        vs.CreateStaticText(dialog, label, "Standardfarbe %s:" % kind, -1)
        vs.CreateColorPopup(dialog, field, 24)
    vs.CreateStaticText(dialog, 17, "DN-Werte [mm], mit Semikolon getrennt:", -1)
    vs.CreateEditText(dialog, 18, "; ".join(str(value) for value in current["dns"]), 68)
    vs.CreateStaticText(dialog, 19, "Materialien, mit Semikolon getrennt:", -1)
    vs.CreateEditText(dialog, 20, "; ".join(current["materials"]), 68)

    vs.CreateGroupBox(dialog, 105, "Schachtfarben nach Kanalsystem", False)
    for index, kind in enumerate(core.KINDS):
        label = 62 + index * 4
        vs.CreateStaticText(
            dialog, label,
            "%s-Schacht – Linie | Füllung | Transparenz [%%]:" % kind, -1)
        vs.CreateColorPopup(dialog, label + 1, 18)
        vs.CreateColorPopup(dialog, label + 2, 18)
        vs.CreateEditText(
            dialog, label + 3,
            str(current["shaft_fill_transparency_percent"][kind]).replace(".", ","),
            10)

    vs.CreateGroupBox(dialog, 102, "Darstellung", False)
    vs.CreateStaticText(dialog, 21, "Schriftgröße [pt]:", -1)
    vs.CreateEditText(dialog, 22, str(current["point_size"]).replace(".", ","), 14)
    vs.CreateStaticText(dialog, 53, "Schachtname-Schriftgröße [pt]:", -1)
    vs.CreateEditText(
        dialog, 54, str(current["shaft_name_point_size"]).replace(".", ","), 14)
    vs.CreateStaticText(dialog, 55, "Schachtname-Schriftstil:", -1)
    vs.CreatePullDownMenu(dialog, 56, 32)
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

    vs.CreateGroupBox(dialog, 104, "Beschriftung", False)
    vs.CreateCheckBox(dialog, 57, "Automatischen Haltungsnamen anzeigen")
    vs.CreateStaticText(dialog, 58, "Schriftgröße Haltungsname [pt]:", -1)
    vs.CreateEditText(
        dialog, 59, str(current["pipe_name_point_size"]).replace(".", ","), 14)
    vs.CreateStaticText(dialog, 60, "Schriftgröße Zu-/Ablaufhöhen [pt]:", -1)
    vs.CreateEditText(
        dialog, 61, str(current["connection_point_size"]).replace(".", ","), 14)
    vs.CreateCheckBox(
        dialog, 74, "Zu-/Ablaufbeschriftungen direkt am Schacht anzeigen")

    vs.CreateGroupBox(dialog, 106, "Stutzen und Anschlusspunkte", False)
    vs.CreateCheckBox(dialog, 75, "Stutzen-Stationierung anzeigen")
    vs.CreateStaticText(dialog, 76, "Schriftgröße Stationierung [pt]:", -1)
    vs.CreateEditText(
        dialog, 77, str(current["stub_station_point_size"]).replace(".", ","), 14)
    vs.CreateCheckBox(dialog, 78, "Stutzen-Anschlusshöhe anzeigen")
    vs.CreateStaticText(dialog, 79, "Schriftgröße Anschlusshöhe [pt]:", -1)
    vs.CreateEditText(
        dialog, 80, str(current["stub_height_point_size"]).replace(".", ","), 14)
    vs.CreateCheckBox(dialog, 81, "Bodenablaufbeschriftung anzeigen")
    vs.CreateStaticText(dialog, 82, "Schriftgröße Bodenablauf [pt]:", -1)
    vs.CreateEditText(
        dialog, 83, str(current["floor_drain_label_point_size"]).replace(".", ","), 14)
    vs.CreateStaticText(dialog, 84, "Bodenablauf Länge [m]:", -1)
    vs.CreateEditText(
        dialog, 85, str(current["floor_drain_length_m"]).replace(".", ","), 14)
    vs.CreateStaticText(dialog, 86, "Bodenablauf Breite [m]:", -1)
    vs.CreateEditText(
        dialog, 87, str(current["floor_drain_width_m"]).replace(".", ","), 14)
    vs.CreateStaticText(dialog, 88, "Bodenablauf Höhe [m]:", -1)
    vs.CreateEditText(
        dialog, 89, str(current["floor_drain_height_m"]).replace(".", ","), 14)

    vs.CreateGroupBox(dialog, 103, "Schächte und Schachtdeckel", False)
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

    vs.CreateTabControl(dialog, 100)

    vs.CreateStaticText(dialog, 49, "Neue Einstellungen anwenden auf:", -1)
    vs.CreatePullDownMenu(dialog, 50, 62)
    vs.CreateStaticText(
        dialog, 51,
        "Bei einer Aktualisierung bleiben Sohlhöhen, Schachtnamen, DN, Material, Lage und individuelle Farben erhalten.",
        82)
    vs.CreateStaticText(
        dialog, 52,
        "Kataloglisten wirken auf neue Objekte. Darstellungs-, Farb-, Text- und Schachtstandards können unten gezielt auf vorhandene Objekte übertragen werden.",
        82)

    vs.SetFirstLayoutItem(dialog, 10)
    vs.SetBelowItem(dialog, 10, 100, 0, 6)

    # Pane 1: catalogs and channel colors.
    previous = None
    for index in range(3):
        label, field = 11 + index * 2, 12 + index * 2
        if previous is None:
            vs.SetFirstGroupItem(dialog, 101, label)
        else:
            vs.SetBelowItem(dialog, previous, label, 0, 6)
        vs.SetRightItem(dialog, label, field, 8, 0)
        previous = label
    for label, field in ((17, 18), (19, 20)):
        vs.SetBelowItem(dialog, previous, label, 0, 6)
        vs.SetRightItem(dialog, label, field, 8, 0)
        previous = label

    # Pane 2: shaft contour, fill and fill transparency per channel type.
    previous = None
    for index in range(3):
        label = 62 + index * 4
        if previous is None:
            vs.SetFirstGroupItem(dialog, 105, label)
        else:
            vs.SetBelowItem(dialog, previous, label, 0, 8)
        vs.SetRightItem(dialog, label, label + 1, 8, 0)
        vs.SetRightItem(dialog, label + 1, label + 2, 5, 0)
        vs.SetRightItem(dialog, label + 2, label + 3, 5, 0)
        previous = label

    # Pane 3: drawing geometry defaults.
    previous = None
    for label, field in ((27, 28), (37, 38), (39, 40), (41, 42), (43, 44)):
        if previous is None:
            vs.SetFirstGroupItem(dialog, 102, label)
        else:
            vs.SetBelowItem(dialog, previous, label, 0, 6)
        vs.SetRightItem(dialog, label, field, 8, 0)
        previous = label

    # Pane 4: text and name defaults.
    previous = None
    for label, field in ((21, 22), (53, 54), (55, 56), (23, 24)):
        if previous is None:
            vs.SetFirstGroupItem(dialog, 104, label)
        else:
            vs.SetBelowItem(dialog, previous, label, 0, 6)
        vs.SetRightItem(dialog, label, field, 8, 0)
        previous = label
    vs.SetBelowItem(dialog, previous, 57, 0, 6)
    vs.SetBelowItem(dialog, 57, 58, 0, 6)
    vs.SetRightItem(dialog, 58, 59, 8, 0)
    vs.SetBelowItem(dialog, 58, 60, 0, 6)
    vs.SetRightItem(dialog, 60, 61, 8, 0)
    vs.SetBelowItem(dialog, 60, 74, 0, 6)

    # Pane 5: shaft defaults.
    previous = None
    for label, field in ((45, 46), (47, 48), (29, 30), (31, 32), (33, 34)):
        if previous is None:
            vs.SetFirstGroupItem(dialog, 103, label)
        else:
            vs.SetBelowItem(dialog, previous, label, 0, 6)
        vs.SetRightItem(dialog, label, field, 8, 0)
        previous = label
    vs.SetBelowItem(dialog, previous, 35, 0, 6)
    vs.SetBelowItem(dialog, 35, 36, 0, 4)
    # Pane 6: stub annotations and floor-drain defaults.
    vs.SetFirstGroupItem(dialog, 106, 75)
    vs.SetBelowItem(dialog, 75, 76, 0, 5)
    vs.SetRightItem(dialog, 76, 77, 8, 0)
    vs.SetBelowItem(dialog, 76, 78, 0, 7)
    vs.SetBelowItem(dialog, 78, 79, 0, 5)
    vs.SetRightItem(dialog, 79, 80, 8, 0)
    vs.SetBelowItem(dialog, 79, 81, 0, 7)
    vs.SetBelowItem(dialog, 81, 82, 0, 5)
    vs.SetRightItem(dialog, 82, 83, 8, 0)
    vs.SetBelowItem(dialog, 82, 84, 0, 7)
    vs.SetRightItem(dialog, 84, 85, 8, 0)
    vs.SetBelowItem(dialog, 84, 86, 0, 5)
    vs.SetRightItem(dialog, 86, 87, 8, 0)
    vs.SetBelowItem(dialog, 86, 88, 0, 5)
    vs.SetRightItem(dialog, 88, 89, 8, 0)
    vs.CreateTabPane(dialog, 100, 101)
    vs.CreateTabPane(dialog, 100, 105)
    vs.CreateTabPane(dialog, 100, 102)
    vs.CreateTabPane(dialog, 100, 104)
    vs.CreateTabPane(dialog, 100, 103)
    vs.CreateTabPane(dialog, 100, 106)
    vs.SetBelowItem(dialog, 100, 49, 0, 7)
    vs.SetRightItem(dialog, 49, 50, 8, 0)
    vs.SetBelowItem(dialog, 49, 51, 0, 5)
    vs.SetBelowItem(dialog, 51, 52, 0, 4)
    result = {"value": None, "scope": "save"}
    resource_id = "PD.Kanal.Schachtdeckel.Voreinstellung"
    shaft_materials = (("PP-Schacht", "PP"), ("Betonschacht", "concrete"))
    update_scopes = (
        ("Nur als Voreinstellung für neue Objekte speichern", "save"),
        ("Nur markierte Kanalobjekte aktualisieren", "selection"),
        ("Angeschlossene Kanalsysteme der Markierung aktualisieren", "systems"),
        ("Alle Kanalobjekte der Zeichnung aktualisieren", "drawing"),
    )
    scope_values = [row[1] for row in update_scopes]
    default_scope = str(default_scope or "save")
    if default_scope not in scope_values:
        default_scope = "save"
    shaft_name_styles = (
        ("Normal", "normal"),
        ("Fett", "bold"),
        ("Unterstrichen", "underline"),
        ("Fett und unterstrichen", "bold_underline"),
    )

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
                label = 62 + index * 4
                vs.SetColorChoice(
                    dialog, label + 1,
                    vs.RGBToColorIndex(*current["shaft_pen_colors"][kind]))
                vs.SetColorChoice(
                    dialog, label + 2,
                    vs.RGBToColorIndex(*current["shaft_fill_colors"][kind]))
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
            vs.SetBooleanItem(dialog, 57, current["pipe_name_visible"])
            vs.SetBooleanItem(
                dialog, 74, current["shaft_connection_labels_visible"])
            vs.SetBooleanItem(dialog, 75, current["stub_station_label_visible"])
            vs.SetBooleanItem(dialog, 78, current["stub_height_label_visible"])
            vs.SetBooleanItem(dialog, 81, current["floor_drain_label_visible"])
            vs.EnableItem(dialog, 76, current["stub_station_label_visible"])
            vs.EnableItem(dialog, 77, current["stub_station_label_visible"])
            vs.EnableItem(dialog, 79, current["stub_height_label_visible"])
            vs.EnableItem(dialog, 80, current["stub_height_label_visible"])
            vs.EnableItem(dialog, 82, current["floor_drain_label_visible"])
            vs.EnableItem(dialog, 83, current["floor_drain_label_visible"])
            vs.EnableItem(dialog, 58, current["pipe_name_visible"])
            vs.EnableItem(dialog, 59, current["pipe_name_visible"])
            for index, row in enumerate(shaft_name_styles):
                vs.AddChoice(dialog, 56, row[0], index)
            vs.SelectChoice(
                dialog, 56,
                [row[1] for row in shaft_name_styles].index(
                    current["shaft_name_text_style"]), True)
            for index, row in enumerate(shaft_materials):
                vs.AddChoice(dialog, 46, row[0], index)
            vs.SelectChoice(
                dialog, 46,
                [row[1] for row in shaft_materials].index(
                    current["shaft_construction_material"]), True)
            for index, row in enumerate(update_scopes):
                vs.AddChoice(dialog, 50, row[0], index)
            # Existing drawings should visibly adopt a changed drawing mode on
            # Save.  The caller selects the safest useful scope: current
            # selection, whole drawing, or defaults only for an empty drawing.
            vs.SelectChoice(dialog, 50, scope_values.index(default_scope), True)
            update_shaft_material()
        elif item == 35:
            vs.EnableItem(dialog, 36, _selected(dialog, 35))
        elif item == 46:
            update_shaft_material()
        elif item == 57:
            vs.EnableItem(dialog, 58, _selected(dialog, 57))
            vs.EnableItem(dialog, 59, _selected(dialog, 57))
        elif item in (75, 78, 81):
            pair = {75: (76, 77), 78: (79, 80), 81: (82, 83)}[item]
            for control in pair:
                vs.EnableItem(dialog, control, _selected(dialog, item))
        elif item == 1:
            try:
                value = copy.deepcopy(current)
                value["colors"] = {kind: list(vs.ColorIndexToRGB(vs.GetColorChoice(dialog, 12 + index * 2)))
                                   for index, kind in enumerate(core.KINDS)}
                value["shaft_pen_colors"] = {
                    kind: list(vs.ColorIndexToRGB(vs.GetColorChoice(
                        dialog, 63 + index * 4)))
                    for index, kind in enumerate(core.KINDS)}
                value["shaft_fill_colors"] = {
                    kind: list(vs.ColorIndexToRGB(vs.GetColorChoice(
                        dialog, 64 + index * 4)))
                    for index, kind in enumerate(core.KINDS)}
                value["shaft_fill_transparency_percent"] = {
                    kind: _float(
                        dialog, 65 + index * 4,
                        "Schacht-Fülltransparenz für %s" % kind)
                    for index, kind in enumerate(core.KINDS)}
                value["dns"] = [core._dn(row) for row in split(18)]
                value["materials"] = [core._material(row) for row in split(20)]
                value["point_size"] = _float(dialog, 22, "Schriftgröße")
                value["pipe_name_visible"] = _selected(dialog, 57)
                value["pipe_name_point_size"] = _float(
                    dialog, 59, "Schriftgröße des Haltungsnamens")
                value["shaft_name_point_size"] = _float(
                    dialog, 54, "Schriftgröße des Schachtnamens")
                value["connection_point_size"] = _float(
                    dialog, 61, "Schriftgröße der Zu- und Ablaufhöhen")
                value["shaft_connection_labels_visible"] = _selected(dialog, 74)
                value["stub_station_label_visible"] = _selected(dialog, 75)
                value["stub_station_point_size"] = _float(
                    dialog, 77, "Schriftgröße der Stutzen-Stationierung")
                value["stub_height_label_visible"] = _selected(dialog, 78)
                value["stub_height_point_size"] = _float(
                    dialog, 80, "Schriftgröße der Stutzen-Anschlusshöhe")
                value["floor_drain_label_visible"] = _selected(dialog, 81)
                value["floor_drain_label_point_size"] = _float(
                    dialog, 83, "Schriftgröße der Bodenablaufbeschriftung")
                value["floor_drain_length_m"] = _float(
                    dialog, 85, "Länge des Bodenablaufs")
                value["floor_drain_width_m"] = _float(
                    dialog, 87, "Breite des Bodenablaufs")
                value["floor_drain_height_m"] = _float(
                    dialog, 89, "Höhe des Bodenablaufs")
                value["shaft_name_text_style"] = shaft_name_styles[_choice(dialog, 56)][1]
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
                result["scope"] = update_scopes[_choice(dialog, 50)][1]
            except core.SewerError as error:
                vs.AlrtDialog(str(error))
                result["value"] = None
                return -1
        return item
    return ((result["value"], result["scope"])
            if _run(dialog, handler, (680, 560)) == 1 else (None, "save"))


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
    vs.CreateStaticText(
        dialog, 11,
        "Ein Objekt oder mehrere Haltungen mit Strg-/Umschalt-Klick auswählen. "
        "Ein gemeinsames Gefälle wird auf alle markierten Haltungen angewendet.", 78)
    vs.CreateStaticText(dialog, 12, "Kettenobjekte:", -1)
    vs.CreateLB(dialog, 13, 78, 12)
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
    vs.SetBelowItem(dialog, 11, 12, 0, 6)
    vs.SetBelowItem(dialog, 12, 13, 0, 3)
    previous = 13
    for label, field in ((14, 15), (16, 17), (18, 19), (20, 21)):
        vs.SetBelowItem(dialog, previous, label, 0, 6)
        vs.SetRightItem(dialog, label, field, 8, 0)
        previous = label
    vs.SetBelowItem(dialog, previous, 22, 0, 7)
    vs.SetBelowItem(dialog, 22, 23, 0, 5)
    vs.SetEdgeBinding(dialog, 13, True, True, True, True)
    result = {"value": None, "changes": 0}
    state = {"filling": False}

    def fmt(value):
        return ("%.4f" % float(value)).replace(".", ",")

    def height_fmt(value):
        return _height_text(value)

    def selected_indexes():
        return [index for index in range(len(rows))
                if vs.IsLBItemSelected(dialog, 13, index)]

    def selected_rows():
        return [rows[index] for index in selected_indexes()]

    def fill_table(selected=()):
        state["filling"] = True
        try:
            vs.EnableLBUpdates(dialog, 13, False)
            vs.DeleteAllLBItems(dialog, 13)
            for row_index, (role, identity, title) in enumerate(rows):
                value = shafts[identity] if role == "shaft" else pipes[identity]
                if role == "pipe":
                    title = "Rohr %s → %s" % (
                        shafts[value["start_id"]]["name"],
                        shafts[value["end_id"]]["name"])
                inserted = vs.InsertLBItem(dialog, 13, row_index, title)
                if inserted != row_index:
                    raise core.SewerError("Die Kanalkette konnte nicht vollständig angezeigt werden.")
                if role == "shaft":
                    values = (height_fmt(value["ks_m"]), "", "")
                else:
                    values = (height_fmt(value["start_invert_m"]),
                              height_fmt(value["end_invert_m"]), fmt(value["slope_percent"]))
                for column, text_value in enumerate(values, 1):
                    if vs.SetLBItemInfo(
                            dialog, 13, row_index, column, text_value, -1) is False:
                        raise core.SewerError("Die Kanalkette konnte nicht vollständig angezeigt werden.")
            if rows:
                vs.SetLBSelection(dialog, 13, 0, len(rows) - 1, False)
            for index in selected:
                if 0 <= index < len(rows):
                    vs.SetLBSelection(dialog, 13, index, index, True)
        finally:
            vs.EnableLBUpdates(dialog, 13, True)
            state["filling"] = False

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
        selected = selected_rows()
        if highlight:
            highlight(tuple((role, identity) for role, identity, _title_value in selected))
        if not selected:
            for item in (15, 17, 19, 21, 22):
                vs.EnableItem(dialog, item, False)
            vs.SetItemText(dialog, 23, "Bitte mindestens ein Kettenobjekt auswählen.")
            return
        if len(selected) > 1:
            if any(role != "pipe" for role, _identity, _title_value in selected):
                for item in (15, 17, 19, 21, 22):
                    vs.EnableItem(dialog, item, False)
                vs.SetItemText(
                    dialog, 23,
                    "Mehrfachauswahl ist für Haltungen vorgesehen. Schächte bitte einzeln bearbeiten.")
                return
            vs.SetItemText(dialog, 14, "Anfangssohle KS [m]:")
            vs.SetItemText(dialog, 16, "Endsohle KS [m]:")
            vs.SetItemText(dialog, 15, "")
            vs.SetItemText(dialog, 17, "")
            slopes = [pipes[identity]["slope_percent"]
                      for _role, identity, _title_value in selected]
            vs.SetItemText(dialog, 19, fmt(slopes[0]) if all(
                abs(value - slopes[0]) <= 1e-9 for value in slopes) else "")
            vs.EnableItem(dialog, 15, False)
            vs.EnableItem(dialog, 17, False)
            vs.EnableItem(dialog, 19, True)
            vs.EnableItem(dialog, 21, True)
            vs.EnableItem(dialog, 22, True)
            vs.SetItemText(
                dialog, 23,
                "%d Haltungen ausgewählt. Neues gemeinsames Gefälle eingeben und vormerken." %
                len(selected))
            return
        role, identity, _title_value = selected[0]
        if role == "shaft":
            shaft = shafts[identity]
            vs.SetItemText(dialog, 14, "Deckelhöhe KD [m]:")
            vs.SetItemText(dialog, 16, "Sohlhöhe KS [m]:")
            vs.SetItemText(dialog, 15, height_fmt(shaft["kd_m"]))
            vs.SetItemText(dialog, 17, height_fmt(shaft["ks_m"]))
            vs.SetItemText(dialog, 19, "")
            vs.EnableItem(dialog, 15, True)
            vs.EnableItem(dialog, 17, True)
            vs.EnableItem(dialog, 19, False)
            vs.EnableItem(dialog, 21, False)
        else:
            pipe = pipes[identity]
            vs.SetItemText(dialog, 14, "Anfangssohle KS [m]:")
            vs.SetItemText(dialog, 16, "Endsohle KS [m]:")
            vs.SetItemText(dialog, 15, height_fmt(pipe["start_invert_m"]))
            vs.SetItemText(dialog, 17, height_fmt(pipe["end_invert_m"]))
            vs.SetItemText(dialog, 19, fmt(pipe["slope_percent"]))
            vs.EnableItem(dialog, 15, False)
            vs.EnableItem(dialog, 17, False)
            vs.EnableItem(dialog, 19, True)
            vs.EnableItem(dialog, 21, True)
        vs.EnableItem(dialog, 22, True)

    def stage():
        shaft_snapshot, pipe_snapshot = copy.deepcopy(shafts), copy.deepcopy(pipes)
        selected_snapshot = selected_indexes()

        def restore(message=None):
            shafts.clear()
            shafts.update(shaft_snapshot)
            pipes.clear()
            pipes.update(pipe_snapshot)
            fill_table(selected_snapshot)
            show()
            if message:
                vs.SetItemText(dialog, 23, message)

        try:
            selected = selected_rows()
            if not selected:
                raise core.SewerError("Bitte mindestens ein Kettenobjekt auswählen.")
            if len(selected) > 1 and any(
                    role != "pipe" for role, _identity, _title_value in selected):
                raise core.SewerError(
                    "Mehrere Schächte können nicht gemeinsam geändert werden. "
                    "Bitte Schächte einzeln oder mehrere Haltungen auswählen.")
            if len(selected) == 1 and selected[0][0] == "shaft":
                _role, identity, _title_value = selected[0]
                shaft = shafts[identity]
                old_soil = shaft["ks_m"]
                new_soil = _float(dialog, 17, "Sohlhöhe")
                shaft["kd_m"] = _float(dialog, 15, "Deckelhöhe")
                connected = endpoints(identity)
                if connected:
                    for pipe, key in connected:
                        if abs(pipe[key] - old_soil) <= 0.001:
                            pipe[key] = new_soil
                            # The new endpoint may intentionally turn this
                            # holding around.  Validate only after the user has
                            # confirmed that direction change below.
                            pipes[pipe["id"]] = pipe
                    minimum = min(pipe[key] for pipe, key in connected)
                    if abs(minimum - new_soil) > 0.001:
                        raise core.SewerError(
                            "Die neue Schachtsohle liegt über einer weiteren angeschlossenen Rohrsohle.")
                shaft["ks_m"] = new_soil
                shafts[identity] = core.validate_shaft(shaft, allow_hidden=True)
            else:
                slope = _float(dialog, 19, "Rohrgefälle")
                if slope < 0.0:
                    raise core.SewerError("Rohrgefälle darf nicht negativ sein.")
                fixed_start = _choice(dialog, 21) == 0
                touched = set()
                for _role, identity, _title_value in selected:
                    pipe = pipes[identity]
                    if fixed_start:
                        pipe["end_invert_m"] = (
                            pipe["start_invert_m"] - pipe["length_m"] * slope / 100.0)
                    else:
                        pipe["start_invert_m"] = (
                            pipe["end_invert_m"] + pipe["length_m"] * slope / 100.0)
                    pipes[identity] = core.validate_pipe(pipe)
                    touched.update((pipe["start_id"], pipe["end_id"]))
                recompute_soils(touched)
            reversals = []
            for identity, pipe in pipes.items():
                if not core.pipe_flow_reversal_required(pipe):
                    continue
                start_name = shafts[pipe["start_id"]]["name"]
                end_name = shafts[pipe["end_id"]]["name"]
                reversals.append((identity, "%s → %s wird zu %s → %s" %
                                  (start_name, end_name, end_name, start_name)))
            if reversals and not confirm_flow_reversal(
                    tuple(description for _identity, description in reversals)):
                restore("Richtungsänderung nicht übernommen. Die bisherigen Höhen bleiben erhalten.")
                return False
            reversal_ids = {identity for identity, _description in reversals}
            for identity, pipe in tuple(pipes.items()):
                if identity in reversal_ids:
                    pipes[identity], _reversed = core.orient_pipe_downhill(pipe)
                else:
                    pipes[identity] = core.validate_pipe(pipe)
            core.validate_network(tuple(pipes.values()), tuple(shafts.values()))
            result["changes"] += 1
            vs.SetItemText(dialog, 23, "%d Änderung(en) vorgemerkt. Weitere Kettenobjekte wählen oder alles übernehmen." % result["changes"])
            indexes = selected_indexes()
            fill_table(indexes)
            show()
        except (core.SewerError, ValueError, TypeError) as error:
            restore()
            vs.AlrtDialog(str(error))
            return False
        return True

    def handler(item, _data):
        if item == INIT:
            for column, (title, width) in enumerate(
                    (("Objekt", 250), ("KS Start", 88), ("KS Ende", 88), ("Gefälle [%]", 88))):
                vs.InsertLBColumn(dialog, 13, column, title, width)
                vs.SetLBControlType(dialog, 13, column, 1)
                vs.SetLBItemDisplayType(dialog, 13, column, 0)
            vs.EnableLBColumnLines(dialog, 13, True)
            vs.EnableLBSingleLineSelection(dialog, 13, False)
            vs.EnableLBSorting(dialog, 13, False)
            fill_table((0,))
            vs.AddChoice(dialog, 21, "Anfangssohle", 0)
            vs.AddChoice(dialog, 21, "Endsohle", 1)
            vs.SelectChoice(dialog, 21, 0, True)
            show()
        elif abs(item) == 13 and not state["filling"]:
            show()
        elif item == 22:
            stage()
        elif item == 1:
            if not stage():
                return -1
            result["value"] = (tuple(shafts.values()), tuple(pipes.values()))
        return item
    return result["value"] if _run(dialog, handler) == 1 else None


def stub_alignment_dialog(default="invert", editing=False):
    """Select the vertical relation between main and branch pipe."""
    rows = (("Sohlgleich", "invert"), ("Achsgleich", "axis"),
            ("Kämpfergleich", "springline"), ("Scheitelgleich", "crown"))
    dialog = vs.CreateResizableLayout(
        _title("Kanalstutzen bearbeiten" if editing else "Kanalstutzen nach DIN"),
        True, "Übernehmen" if editing else "Weiter", "Abbrechen", True, True)
    vs.CreateStyledStatic(dialog, 10, "KANALSTUTZEN  |  Anschlussart und Anschlusshöhe", -1, TITLE_STYLE)
    vs.CreateStaticText(
        dialog, 11,
        ("Die Hauptleitung bleibt unverändert. Anschlusssohle, Gefälle, 3D-Geometrie und "
         "Beschriftung der vorhandenen Anschlussleitung werden gemeinsam aktualisiert."
         if editing else
         "Zuerst wurde die Haltung gewählt. Nach dieser Einstellung die Lage des Stutzens "
         "anklicken und die Anschlussleitung zeichnen."), 76)
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
            rows.append((pipe, "DN %d %s | ankommend KS %s m" %
                         (pipe["dn_mm"], pipe["material"], _height_text(elevation)), elevation))
    if not rows:
        raise core.SewerError("Am gewählten Schacht ist keine ankommende Haltung vorhanden.")
    dialog = vs.CreateResizableLayout(
        _title("Absturz vor Schacht"), True, "Übernehmen", "Abbrechen", True, True)
    vs.CreateStyledStatic(dialog, 10, "ABSTURZ  |  Obere Spülleitung und untere Absturzleitung", -1, TITLE_STYLE)
    vs.CreateStaticText(dialog, 11, "Ankommende Haltung:", -1)
    vs.CreatePullDownMenu(dialog, 12, 52)
    vs.CreateStaticText(dialog, 13, "Obere ankommende Sohlhöhe [m]:", -1)
    vs.CreateEditText(dialog, 14, _height_text(rows[0][2]), 18)
    vs.CreateStaticText(dialog, 15, "Unterkante Absturzleitung [m]:", -1)
    vs.CreateEditText(dialog, 16, _height_text(shaft["ks_m"]), 18)
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
            vs.SetItemText(dialog, 14, _height_text(rows[_choice(dialog, 12)][2]))
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
                        "Anschlusshöhe / Unterkante [m] (leer = automatisch):" if floor else
                        "Höhe des freien Anschlusspunktes [m]:", -1)
    vs.CreateEditText(dialog, 19, "", 18)
    vs.CreateStaticText(dialog, 20, "Anschlussart am Hauptkanal:", -1)
    vs.CreatePullDownMenu(dialog, 21, 30)
    vs.CreateStaticText(dialog, 22, "Länge des Bodenablaufs [m]:", -1)
    vs.CreateEditText(dialog, 23, str(preferences["floor_drain_length_m"]).replace(".", ","), 18)
    vs.CreateStaticText(dialog, 24, "Breite des Bodenablaufs [m]:", -1)
    vs.CreateEditText(dialog, 25, str(preferences["floor_drain_width_m"]).replace(".", ","), 18)
    vs.CreateStaticText(dialog, 29, "Höhe des Bodenablaufs [m]:", -1)
    vs.CreateEditText(dialog, 30, str(preferences["floor_drain_height_m"]).replace(".", ","), 18)
    vs.CreateCheckBox(dialog, 31, "Bodenablaufsymbol aus Dokument oder Bibliothek verwenden")
    vs.CreateResourcePopup(dialog, 32, 44)
    vs.CreateCheckBox(dialog, 33, "Gewähltes Symbol besitzt bereits einen 3D-Anteil")
    vs.CreateCheckBox(dialog, 34, "Bodenablaufbeschriftung anzeigen")
    vs.CreateStaticText(dialog, 35, "Schriftgröße der Beschriftung [pt]:", -1)
    vs.CreateEditText(dialog, 36, str(preferences["floor_drain_label_point_size"]).replace(".", ","), 18)
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
    vs.SetBelowItem(dialog, 24, 29, 0, 6)
    vs.SetRightItem(dialog, 29, 30, 8, 0)
    vs.SetBelowItem(dialog, 29, 31, 0, 6)
    vs.SetBelowItem(dialog, 31, 32, 0, 4)
    vs.SetBelowItem(dialog, 32, 33, 0, 4)
    vs.SetBelowItem(dialog, 33, 34, 0, 6)
    vs.SetBelowItem(dialog, 34, 35, 0, 4)
    vs.SetRightItem(dialog, 35, 36, 8, 0)
    for item in (22, 23, 24, 25, 29, 30, 31, 32, 33, 34, 35, 36):
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
                _init_cover_resource(dialog, 32, resource_id, preferences["floor_drain_symbol"])
                vs.SetBooleanItem(dialog, 31, bool(preferences["floor_drain_symbol"]))
                vs.SetBooleanItem(dialog, 33, bool(preferences["floor_drain_symbol_has_3d"]))
                vs.SetBooleanItem(dialog, 34, preferences["floor_drain_label_visible"])
                vs.EnableItem(dialog, 32, bool(preferences["floor_drain_symbol"]))
                vs.EnableItem(dialog, 33, bool(preferences["floor_drain_symbol"]))
                vs.EnableItem(dialog, 35, preferences["floor_drain_label_visible"])
                vs.EnableItem(dialog, 36, preferences["floor_drain_label_visible"])
        elif item == 31 and floor:
            vs.EnableItem(dialog, 32, _selected(dialog, 31))
            vs.EnableItem(dialog, 33, _selected(dialog, 31))
        elif item == 34 and floor:
            vs.EnableItem(dialog, 35, _selected(dialog, 34))
            vs.EnableItem(dialog, 36, _selected(dialog, 34))
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
                "terminal_bottom_m": core.number(raw_height, "Anschlusshöhe") if raw_height else None,
                "alignment": alignments[_choice(dialog, 21)][1],
                "terminal_length_m": _float(dialog, 23, "Länge") if floor else 0.50,
                "terminal_width_m": _float(dialog, 25, "Breite") if floor else 0.30,
                "terminal_height_m": _float(dialog, 30, "Höhe") if floor else 0.60,
                "terminal_symbol": _cover_symbol(resource_id, _selected(dialog, 31)) if floor else "",
                "terminal_symbol_has_3d": bool(_selected(dialog, 33)) if floor else False,
                "terminal_label_visible": bool(_selected(dialog, 34)) if floor else True,
                "terminal_label_point_size": (_float(
                    dialog, 36, "Schriftgröße der Bodenablaufbeschriftung")
                    if floor else preferences["point_size"]),
            }
            result["value"] = value
        return item
    return result["value"] if _run(dialog, handler) == 1 else None


def terminal_properties_dialog(shaft, preferences):
    """Edit the body and lower-edge height of a terminal object."""
    current = core.validate_shaft(shaft, allow_hidden=True)
    floor = current["structure_type"] == "floor_drain"
    if current["structure_type"] not in ("floor_drain", "house"):
        raise core.SewerError("Das gewählte Objekt ist kein Anschluss-Endpunkt.")
    noun = "Bodenablauf" if floor else "Hausanschluss"
    dialog = vs.CreateResizableLayout(
        _title(noun + " bearbeiten"), True, "Übernehmen", "Abbrechen", True, True)
    vs.CreateStyledStatic(dialog, 10, "%s  |  %s" % (noun.upper(), current["name"]), -1, TITLE_STYLE)
    vs.CreateStaticText(dialog, 11, "Anschlusshöhe / Unterkante [m]:", -1)
    vs.CreateEditText(dialog, 12, _height_text(current["ks_m"]), 18)
    vs.CreateStaticText(dialog, 13, "Länge [m]:", -1)
    vs.CreateEditText(dialog, 14, str(current["terminal_length_m"]).replace(".", ","), 18)
    vs.CreateStaticText(dialog, 15, "Breite [m]:", -1)
    vs.CreateEditText(dialog, 16, str(current["terminal_width_m"]).replace(".", ","), 18)
    vs.CreateStaticText(dialog, 17, "Höhe [m]:", -1)
    vs.CreateEditText(dialog, 18, str(current["terminal_height_m"]).replace(".", ","), 18)
    vs.CreateCheckBox(dialog, 19, "Beschriftung anzeigen")
    vs.CreateStaticText(dialog, 20, "Schriftgröße [pt]:", -1)
    vs.CreateEditText(dialog, 21, str(current["terminal_label_point_size"]).replace(".", ","), 18)
    vs.SetFirstLayoutItem(dialog, 10)
    previous = 10
    for label, field in ((11, 12), (13, 14), (15, 16), (17, 18)):
        vs.SetBelowItem(dialog, previous, label, 0, 6)
        vs.SetRightItem(dialog, label, field, 8, 0)
        previous = label
    vs.SetBelowItem(dialog, previous, 19, 0, 7)
    vs.SetBelowItem(dialog, 19, 20, 0, 5)
    vs.SetRightItem(dialog, 20, 21, 8, 0)
    for item in (13, 14, 15, 16, 17, 18):
        vs.EnableItem(dialog, item, floor)
    result = {"value": None}

    def handler(item, _data):
        if item == INIT:
            vs.SetBooleanItem(dialog, 19, current["terminal_label_visible"])
            vs.EnableItem(dialog, 20, current["terminal_label_visible"])
            vs.EnableItem(dialog, 21, current["terminal_label_visible"])
        elif item == 19:
            vs.EnableItem(dialog, 20, _selected(dialog, 19))
            vs.EnableItem(dialog, 21, _selected(dialog, 19))
        elif item == 1:
            try:
                bottom = _float(dialog, 12, "Anschlusshöhe")
                updated = copy.deepcopy(current)
                updated["ks_m"] = bottom
                updated["terminal_label_visible"] = _selected(dialog, 19)
                updated["terminal_label_point_size"] = _float(
                    dialog, 21, "Schriftgröße der Beschriftung")
                if floor:
                    updated["terminal_length_m"] = _float(dialog, 14, "Länge")
                    updated["terminal_width_m"] = _float(dialog, 16, "Breite")
                    updated["terminal_height_m"] = _float(dialog, 18, "Höhe")
                    updated["terminal_depth_m"] = updated["terminal_height_m"]
                    updated["kd_m"] = bottom + updated["terminal_height_m"]
                else:
                    updated["kd_m"] = bottom
                result["value"] = core.validate_shaft(updated, allow_hidden=True)
            except core.SewerError as error:
                vs.AlrtDialog(str(error))
                return -1
        return item
    return result["value"] if _run(dialog, handler, (480, 390)) == 1 else None
