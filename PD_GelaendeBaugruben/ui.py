# -*- coding: utf-8 -*-
"""Compact German five-step assistant dialogs."""
from __future__ import absolute_import

import vs

from . import core
from . import __version__


INIT = 12255
BACK = 3


def _title(value):
    return "%s | v%s | manufactured by Dirk D." % (value, __version__)


def _text(dialog, item):
    return str(vs.GetItemText(dialog, item) or "").strip()


def _real(dialog, item, label, minimum=None, maximum=None):
    valid, value = vs.GetEditReal(dialog, item, 1)
    if not valid:
        raise core.TerrainError("%s ist keine gültige Zahl." % label)
    return core.number(value, label, minimum, maximum)


def _choice(dialog, item, values):
    index = int(vs.GetSelectedChoiceIndex(dialog, item, 0) or 0)
    return values[max(0, min(len(values) - 1, index))]


def _add_choices(dialog, item, values, selected=0):
    for index, value in enumerate(values):
        vs.AddChoice(dialog, item, str(value), index)
    vs.SelectChoice(dialog, item, int(selected), True)


def home():
    dialog = vs.CreateResizableLayout(
        _title("PD Gelände und Baugruben | Assistent"), True,
        "Öffnen", "Schließen", True, True)
    vs.CreateStaticText(dialog, 4,
        "Wählen Sie den nächsten Arbeitsschritt. Jeder Schritt kann ohne Verlust zur Übersicht zurückkehren.", 72)
    actions = (
        (10, "1  Quelldaten wählen und prüfen"),
        (11, "2  Bestands- und Sollmodelle verwalten"),
        (12, "3  Baugrube und Böschung definieren"),
        (13, "4  Geländemodelle vergleichen"),
        (14, "5  Tabelle, Rasterplan und Schraffur erzeugen"),
    )
    for item, label in actions:
        vs.CreateRadioButton(dialog, item, label)
    vs.CreateStaticText(dialog, 20,
        "Technischer Hinweis: Die geprüfte Python-API kann native Geländemodelle auswerten, "
        "aber nicht vollständig erzeugen oder automatisch aktualisieren. Quelldaten werden daher "
        "sicher vorbereitet und für den nativen Vectorworks-Befehl markiert.", 72)
    vs.SetFirstLayoutItem(dialog, 4)
    previous = 4
    for item, _label in actions:
        vs.SetBelowItem(dialog, previous, item, 0, 8)
        previous = item
    vs.SetBelowItem(dialog, previous, 20, 0, 14)
    state = {"action": None}

    def handler(item, _data):
        if item == INIT:
            vs.SetBooleanItem(dialog, 10, True)
            vs.SetFocusOnItem(dialog, 10)
        elif item == 1:
            for control, _label in actions:
                if vs.GetBooleanItem(dialog, control):
                    state["action"] = control - 9
                    break
        return item
    if not vs.VerifyLayout(dialog):
        raise core.TerrainError("Der Gelände-Assistent konnte nicht aufgebaut werden.")
    return state["action"] if vs.RunLayoutDialog(dialog, handler) == 1 else None


def source_options(defaults=None):
    defaults = dict(defaults or {})
    dialog = vs.CreateResizableLayout(
        _title("PD Gelände und Baugruben | Schritt 1 Quelldaten"),
        True, "Vorschau", "Abbrechen", True, True)
    vs.CreatePushButton(dialog, BACK, "Zurück")
    labels = ((10, "Neue Quelldaten-Ebene:"), (11, "Sehnentoleranz [m]:"),
              (12, "XY-Dubletten-Toleranz [m]:"), (13, "Höhentoleranz [m]:"),
              (14, "Klassen ausschließen (Muster;):"), (15, "Ebenen ausschließen (Muster;):"),
              (16, "Gewünschter DGM-Name:"), (17, "Gewünschte DGM-Klasse:"),
              (18, "Höhenlinien-Äquidistanz [m]:"))
    for item, label in labels:
        vs.CreateStaticText(dialog, item, label, 34)
    vs.CreateEditText(dialog, 20, defaults.get("layer_name", "PD-GB-Quelldaten"), 36)
    vs.CreateEditReal(dialog, 21, 1, defaults.get("chord_tolerance_m", 0.10), 14)
    vs.CreateEditReal(dialog, 22, 1, defaults.get("xy_tolerance_m", 0.001), 14)
    vs.CreateEditReal(dialog, 23, 1, defaults.get("z_tolerance_m", 0.001), 14)
    vs.CreateEditText(dialog, 24, defaults.get("excluded_classes", "*Dach*;*Baum*;*Vegetation*"), 44)
    vs.CreateEditText(dialog, 25, defaults.get("excluded_layers", ""), 44)
    vs.CreateEditText(dialog, 26, defaults.get("model_name", "DGM Bestand"), 36)
    vs.CreateEditText(dialog, 27, defaults.get("model_class", "PD-GB-Gelaendemodell"), 36)
    vs.CreateEditReal(dialog, 28, 1, defaults.get("contour_interval_m", 0.5), 14)
    vs.CreateCheckBox(dialog, 29,
        "Unabhängig von der Markierung alle Objekte der aktiven Ebene prüfen")
    vs.SetBooleanItem(dialog, 29, defaults.get("all_active_layer", False))
    vs.CreateCheckBox(dialog, 31,
        "Erstes markiertes geschlossenes 2D-Polygon als Modellbegrenzung verwenden")
    vs.SetBooleanItem(dialog, 31, defaults.get("use_selected_boundary", False))
    vs.CreateStaticText(dialog, 30,
        "Standardmäßig werden sämtliche markierten 3D-Objekte einschließlich Gruppeninhalten "
        "geprüft. Die optionale Ebenenprüfung nimmt zusätzlich unmarkierte Objekte auf. Ohne "
        "aktivierte Begrenzungsoption schneidet keine geschlossene Fremdgeometrie Quelldaten ab.", 70)
    vs.SetFirstLayoutItem(dialog, 10)
    for label, field in zip(range(10, 19), range(20, 29)):
        vs.SetRightItem(dialog, label, field, 10, 0)
        if label < 18:
            vs.SetBelowItem(dialog, label, label + 1, 0, 8)
    vs.SetBelowItem(dialog, 18, 29, 0, 14)
    vs.SetBelowItem(dialog, 29, 31, 0, 8)
    vs.SetBelowItem(dialog, 31, 30, 0, 12)
    vs.SetBelowItem(dialog, 30, BACK, 0, 14)
    state = {"result": None, "back": False}

    def handler(item, _data):
        if item == BACK:
            state["back"] = True
            return 2
        if item == 1:
            state["result"] = {
                "layer_name": _text(dialog, 20),
                "chord_tolerance_m": _real(dialog, 21, "Sehnentoleranz", 0.001),
                "xy_tolerance_m": _real(dialog, 22, "XY-Toleranz", 1e-9),
                "z_tolerance_m": _real(dialog, 23, "Höhentoleranz", 0.0),
                "excluded_classes": _text(dialog, 24),
                "excluded_layers": _text(dialog, 25),
                "model_name": _text(dialog, 26),
                "model_class": _text(dialog, 27),
                "contour_interval_m": _real(dialog, 28, "Höhenlinien-Äquidistanz", 0.001),
                "all_active_layer": bool(vs.GetBooleanItem(dialog, 29)),
                "use_selected_boundary": bool(vs.GetBooleanItem(dialog, 31)),
            }
        return item
    if not vs.VerifyLayout(dialog):
        raise core.TerrainError("Der Quelldatendialog konnte nicht aufgebaut werden.")
    accepted = vs.RunLayoutDialog(dialog, handler) == 1
    return "back" if state["back"] else state["result"] if accepted else None


def model_options(model_names):
    if not model_names:
        raise core.TerrainError("Im Dokument wurde kein benanntes Geländemodell gefunden.")
    operations = ("Registrieren / Metadaten ändern", "Sollvariante duplizieren", "Verwaltete Sollvariante löschen")
    dialog = vs.CreateResizableLayout(
        _title("PD Gelände und Baugruben | Schritt 2 Modelle"),
        True, "Ausführen", "Abbrechen", True, True)
    vs.CreatePushButton(dialog, BACK, "Zurück")
    for item, label in ((10, "Aktion:"), (11, "Ausgangsmodell:"), (12, "Neuer Modellname:"),
                        (13, "Variantenname:"), (14, "Rolle:"), (15, "Referenzmodell:"),
                        (16, "Priorität bei Überlappung:")):
        vs.CreateStaticText(dialog, item, label, 34)
    vs.CreatePullDownMenu(dialog, 20, 38)
    vs.CreatePullDownMenu(dialog, 21, 38)
    vs.CreateEditText(dialog, 22, "", 38)
    vs.CreateEditText(dialog, 23, "Variante 1", 38)
    vs.CreatePullDownMenu(dialog, 24, 24)
    vs.CreatePullDownMenu(dialog, 25, 38)
    vs.CreateEditInteger(dialog, 26, 0, 10)
    _add_choices(dialog, 20, operations)
    _add_choices(dialog, 21, model_names)
    _add_choices(dialog, 24, ("Bestand", "Soll"))
    _add_choices(dialog, 25, ("– keine –",) + tuple(model_names))
    vs.CreateStaticText(dialog, 30,
        "Eine Kopie wird nach dem Duplizieren als echtes DGM geprüft. Löschen ist nur für vom Modul "
        "erzeugte Sollkopien zulässig. Andere Geländemodelle bleiben geschützt.", 70)
    vs.SetFirstLayoutItem(dialog, 10)
    for label, field in zip(range(10, 17), range(20, 27)):
        vs.SetRightItem(dialog, label, field, 10, 0)
        if label < 16:
            vs.SetBelowItem(dialog, label, label + 1, 0, 8)
    vs.SetBelowItem(dialog, 16, 30, 0, 14)
    vs.SetBelowItem(dialog, 30, BACK, 0, 14)
    state = {"result": None, "back": False}

    def handler(item, _data):
        if item == BACK:
            state["back"] = True
            return 2
        if item == 1:
            operation = _choice(dialog, 20, ("register", "duplicate", "delete"))
            source = _choice(dialog, 21, tuple(model_names))
            reference = _choice(dialog, 25, ("",) + tuple(model_names))
            state["result"] = {
                "operation": operation, "source_name": source,
                "new_model_name": _text(dialog, 22), "variant_name": _text(dialog, 23),
                "role": _choice(dialog, 24, ("bestand", "soll")),
                "reference_name": reference,
                "priority": int(vs.GetEditInteger(dialog, 26)[1]),
            }
        return item
    if not vs.VerifyLayout(dialog):
        raise core.TerrainError("Der Variantendialog konnte nicht aufgebaut werden.")
    accepted = vs.RunLayoutDialog(dialog, handler) == 1
    return "back" if state["back"] else state["result"] if accepted else None


def excavation_options(model_names):
    if not model_names:
        raise core.TerrainError("Für die Böschung wird ein benanntes Geländemodell benötigt.")
    dialog = vs.CreateResizableLayout(
        _title("PD Gelände und Baugruben | Schritt 3 Baugrube"),
        True, "Berechnen", "Abbrechen", True, True)
    vs.CreatePushButton(dialog, BACK, "Zurück")
    labels = ((10, "Bestandsmodell:"), (11, "Sohlenhöhe am ersten Punkt [m]:"),
              (12, "Sohlengefälle [%]:"), (13, "Gefällerichtung [°]:"),
              (14, "Böschungsneigung:"), (15, "Einheit:"),
              (16, "Maximale Ausdehnung [m]:"), (17, "Schraffurabstand [m]:"),
              (18, "Kurze Linien [%]:"), (19, "Ausgabename:"))
    for item, label in labels:
        vs.CreateStaticText(dialog, item, label, 34)
    vs.CreatePullDownMenu(dialog, 20, 38)
    vs.CreateEditReal(dialog, 21, 1, 100.0, 14)
    vs.CreateEditReal(dialog, 22, 1, 0.0, 14)
    vs.CreateEditReal(dialog, 23, 1, 0.0, 14)
    vs.CreateEditReal(dialog, 24, 1, 1.5, 14)
    vs.CreatePullDownMenu(dialog, 25, 24)
    vs.CreateEditReal(dialog, 26, 1, 20.0, 14)
    vs.CreateEditReal(dialog, 27, 1, 1.0, 14)
    vs.CreateEditReal(dialog, 28, 1, 50.0, 14)
    vs.CreateEditText(dialog, 29, "PD-GB-Baugrube", 38)
    vs.CreateCheckBox(dialog, 30, "Native Sohlenfläche als Pad-Modifikator kennzeichnen")
    _add_choices(dialog, 20, model_names)
    _add_choices(dialog, 25, ("1:n", "Prozent", "Grad"))
    vs.SetBooleanItem(dialog, 30, True)
    vs.CreateStaticText(dialog, 31,
        "Vor dem Öffnen genau eine geschlossene Baugrubenbegrenzung markieren. Weitere markierte "
        "geschlossene Polygone gelten als Hindernisse. Konflikte werden rot markiert und nicht verschwiegen.", 72)
    vs.SetFirstLayoutItem(dialog, 10)
    for label, field in zip(range(10, 20), range(20, 30)):
        vs.SetRightItem(dialog, label, field, 10, 0)
        if label < 19:
            vs.SetBelowItem(dialog, label, label + 1, 0, 8)
    vs.SetBelowItem(dialog, 19, 30, 0, 12)
    vs.SetBelowItem(dialog, 30, 31, 0, 12)
    vs.SetBelowItem(dialog, 31, BACK, 0, 14)
    state = {"result": None, "back": False}

    def handler(item, _data):
        if item == BACK:
            state["back"] = True
            return 2
        if item == 1:
            state["result"] = {
                "model_name": _choice(dialog, 20, tuple(model_names)),
                "floor_m": _real(dialog, 21, "Baugrubensohle"),
                "floor_slope_percent": _real(dialog, 22, "Sohlengefälle", -1000.0, 1000.0),
                "floor_direction_degrees": _real(dialog, 23, "Sohlengefällerichtung", -360.0, 360.0),
                "slope_value": _real(dialog, 24, "Böschungsneigung", 1e-6),
                "slope_unit": _choice(dialog, 25, ("ratio", "percent", "degree")),
                "max_extent_m": _real(dialog, 26, "Maximale Ausdehnung", 0.01),
                "hatch_spacing_m": _real(dialog, 27, "Schraffurabstand", 0.001),
                "short_ratio": _real(dialog, 28, "Kurze Linien", 1.0, 100.0) / 100.0,
                "name": _text(dialog, 29),
                "create_modifier": bool(vs.GetBooleanItem(dialog, 30)),
            }
        return item
    if not vs.VerifyLayout(dialog):
        raise core.TerrainError("Der Baugrubendialog konnte nicht aufgebaut werden.")
    accepted = vs.RunLayoutDialog(dialog, handler) == 1
    return "back" if state["back"] else state["result"] if accepted else None


def comparison_options(model_names):
    if len(model_names) < 2:
        raise core.TerrainError("Für einen Vergleich werden zwei benannte Geländemodelle benötigt.")
    dialog = vs.CreateResizableLayout(
        _title("PD Gelände und Baugruben | Schritt 4/5 Vergleich"), True,
        "Vorschau und Ausgabe", "Abbrechen", True, True)
    vs.CreatePushButton(dialog, BACK, "Zurück")
    labels = ((10, "Referenzmodell:"), (11, "Vergleichsmodell:"),
              (12, "Rasterweite [m]:"), (13, "Rasterwinkel [°]:"),
              (14, "Nachkommastellen:"), (15, "Höhentoleranz [m]:"),
              (16, "Konvergenztoleranz [%]:"), (17, "Rasterursprung X [m]:"),
              (18, "Rasterursprung Y [m]:"), (19, "Beschriftungsgröße [pt]:"))
    for item, label in labels:
        vs.CreateStaticText(dialog, item, label, 34)
    vs.CreatePullDownMenu(dialog, 20, 38)
    vs.CreatePullDownMenu(dialog, 21, 38)
    vs.CreateEditReal(dialog, 22, 1, 1.0, 14)
    vs.CreateEditReal(dialog, 23, 1, 0.0, 14)
    vs.CreateEditInteger(dialog, 24, 2, 10)
    vs.CreateEditReal(dialog, 25, 1, 0.001, 14)
    vs.CreateEditReal(dialog, 26, 1, 2.0, 14)
    vs.CreateEditReal(dialog, 27, 1, 0.0, 14)
    vs.CreateEditReal(dialog, 28, 1, 0.0, 14)
    vs.CreateEditReal(dialog, 29, 1, 8.0, 14)
    _add_choices(dialog, 20, model_names, 0)
    _add_choices(dialog, 21, model_names, 1)
    vs.CreateCheckBox(dialog, 30, "Rasterursprung automatisch am ersten Begrenzungspunkt")
    vs.SetBooleanItem(dialog, 30, True)
    vs.CreateCheckBox(dialog, 31, "Rasterplan und Verschneidungslinien erzeugen")
    vs.SetBooleanItem(dialog, 31, True)
    vs.CreateStaticText(dialog, 40,
        "Die markierte geschlossene Fläche begrenzt beide Zustände. Fehlende gemeinsame "
        "Modellüberdeckung wird als 'keine Daten' ausgewiesen und nicht als Nullhöhe gerechnet.", 72)
    vs.SetFirstLayoutItem(dialog, 10)
    for label, field in zip(range(10, 20), range(20, 30)):
        vs.SetRightItem(dialog, label, field, 10, 0)
        if label < 19:
            vs.SetBelowItem(dialog, label, label + 1, 0, 8)
    vs.SetBelowItem(dialog, 19, 30, 0, 12)
    vs.SetBelowItem(dialog, 30, 31, 0, 8)
    vs.SetBelowItem(dialog, 31, 40, 0, 12)
    vs.SetBelowItem(dialog, 40, BACK, 0, 14)
    state = {"result": None, "back": False}

    def handler(item, _data):
        if item == BACK:
            state["back"] = True
            return 2
        if item == 1:
            reference = _choice(dialog, 20, tuple(model_names))
            comparison = _choice(dialog, 21, tuple(model_names))
            if reference == comparison:
                raise core.TerrainError("Referenz- und Vergleichsmodell müssen verschieden sein.")
            state["result"] = {
                "reference_name": reference, "comparison_name": comparison,
                "spacing_m": _real(dialog, 22, "Rasterweite", 0.01),
                "angle_degrees": _real(dialog, 23, "Rasterwinkel", -360.0, 360.0),
                "decimals": int(vs.GetEditInteger(dialog, 24)[1]),
                "z_tolerance_m": _real(dialog, 25, "Höhentoleranz", 0.0),
                "volume_tolerance": _real(dialog, 26, "Konvergenztoleranz", 0.0, 100.0) / 100.0,
                "origin_x_m": _real(dialog, 27, "Rasterursprung X"),
                "origin_y_m": _real(dialog, 28, "Rasterursprung Y"),
                "label_text_size_pt": _real(dialog, 29, "Beschriftungsgröße", 1.0, 144.0),
                "automatic_origin": bool(vs.GetBooleanItem(dialog, 30)),
                "create_plan": bool(vs.GetBooleanItem(dialog, 31)),
            }
        return item
    if not vs.VerifyLayout(dialog):
        raise core.TerrainError("Der Vergleichsdialog konnte nicht aufgebaut werden.")
    accepted = vs.RunLayoutDialog(dialog, handler) == 1
    return "back" if state["back"] else state["result"] if accepted else None
