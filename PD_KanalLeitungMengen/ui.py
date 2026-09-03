# -*- coding: utf-8 -*-
"""Dialogs for the canal and utility quantity module."""
from __future__ import absolute_import

import vs

from . import __version__


INIT = 12255


def _fit_dialog(dialog, preferred_size=None):
    """Keep the quantity dialog fully inside the active monitor."""
    try:
        left, top, right, bottom = (int(value) for value in vs.GetScreen())
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


def action_dialog(has_worksheet, warning_count=0, preferences=None):
    preferences = preferences or {}
    dialog = vs.CreateResizableLayout(
        "Kanal- und Leitungsmengen | v%s | manufactured by Dirk D." % __version__, True,
        "Ausführen", "Abbrechen", True, True)
    vs.CreateStyledStatic(dialog, 10, "MASSENERMITTLUNG  |  Kanal, Leitung, Erdmassen und Verbau", -1, 213)
    vs.CreateStaticText(
        dialog, 11,
        "Die Mengen werden unmittelbar aus den verwalteten Kanal- und Leitungsobjekten neu berechnet. "
        "Vor dem Erzeugen wird gewählt, ob die kompakte Summenliste oder die vollständige "
        "Einzelmassenliste mit eigenen Summenzeilen ausgegeben wird.", 82)
    vs.CreateStaticText(dialog, 12, "Ausgabe:", -1)
    vs.CreatePullDownMenu(dialog, 13, 58)
    vs.CreateStaticText(dialog, 19, "Listeninhalt:", -1)
    vs.CreatePullDownMenu(dialog, 20, 58)
    vs.CreateStaticText(
        dialog, 14,
        ("Mindestens eines der laufenden Arbeitsblätter ist bereits vorhanden." if has_worksheet else
         "Beim ersten Aufruf wird das ausgewählte Arbeitsblatt angelegt."), 72)
    vs.CreateStaticText(dialog, 15, "%d Prüfhinweis(e) in der aktuellen Berechnung." % warning_count, 72)
    vs.CreateCheckBox(
        dialog, 16,
        "Künftigen Oberbau bei der Wiederverfüllung berücksichtigen")
    vs.CreateStaticText(dialog, 17, "Oberbaustärke [m]:", -1)
    vs.CreateEditReal(dialog, 18, 3, float(preferences.get(
        "earthwork_pavement_thickness_m", 0.0)), 10)
    vs.SetFirstLayoutItem(dialog, 10)
    vs.SetBelowItem(dialog, 10, 11, 0, 6)
    vs.SetBelowItem(dialog, 11, 12, 0, 8)
    vs.SetRightItem(dialog, 12, 13, 8, 0)
    vs.SetBelowItem(dialog, 12, 19, 0, 6)
    vs.SetRightItem(dialog, 19, 20, 8, 0)
    vs.SetBelowItem(dialog, 19, 14, 0, 6)
    vs.SetBelowItem(dialog, 14, 15, 0, 4)
    vs.SetBelowItem(dialog, 15, 16, 0, 8)
    vs.SetBelowItem(dialog, 16, 17, 0, 5)
    vs.SetRightItem(dialog, 17, 18, 8, 0)
    actions = (("Gewähltes Arbeitsblatt aktualisieren", "worksheet"),
               ("Excel-Datei exportieren", "xlsx"),
               ("Gewähltes Arbeitsblatt aktualisieren und Excel exportieren", "both"))
    list_modes = (("Summenliste", "summary"),
                  ("Alle Einzelmassen mit Summenzeilen", "details"))
    result = {"value": None}

    def handler(item, _data):
        if item == INIT:
            for index, row in enumerate(actions):
                vs.AddChoice(dialog, 13, row[0], index)
            vs.SelectChoice(dialog, 13, 0, True)
            for index, row in enumerate(list_modes):
                vs.AddChoice(dialog, 20, row[0], index)
            vs.SelectChoice(dialog, 20, 0, True)
            enabled = bool(preferences.get("earthwork_include_pavement", False))
            vs.SetBooleanItem(dialog, 16, enabled)
            vs.EnableItem(dialog, 18, enabled)
            _fit_dialog(dialog, (620, 430))
        elif item == 16:
            vs.EnableItem(dialog, 18, bool(vs.GetBooleanItem(dialog, 16)))
        elif item == 1:
            selected = int(vs.GetSelectedChoiceIndex(dialog, 13, 0))
            if selected < 0:
                raise RuntimeError("Bitte eine Ausgabe auswählen.")
            selected_mode = int(vs.GetSelectedChoiceIndex(dialog, 20, 0))
            if selected_mode < 0:
                raise RuntimeError("Bitte Summenliste oder Einzelmassen auswählen.")
            enabled = bool(vs.GetBooleanItem(dialog, 16))
            thickness = float(vs.GetEditReal(dialog, 18, 1)[1])
            if enabled and thickness <= 0.0:
                vs.AlrtDialog(
                    "Für den berücksichtigten Oberbau ist eine Stärke größer als 0 m anzugeben.")
                return -1
            result["value"] = {
                "action": actions[selected][1],
                "report_mode": list_modes[selected_mode][1],
                "include_pavement": enabled,
                "pavement_thickness_m": thickness,
            }
        return item
    if not vs.VerifyLayout(dialog):
        raise RuntimeError("Der Mengendialog konnte nicht aufgebaut werden.")
    _fit_dialog(dialog, (620, 430))
    return result["value"] if vs.RunLayoutDialog(dialog, handler) == 1 else None
