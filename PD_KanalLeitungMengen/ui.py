# -*- coding: utf-8 -*-
"""Dialogs for the canal and utility quantity module."""
from __future__ import absolute_import

import vs

from . import __version__


INIT = 12255


def action_dialog(has_worksheet, warning_count=0):
    dialog = vs.CreateResizableLayout(
        "Kanal- und Leitungsmengen | v%s | manufactured by Dirk D." % __version__, True,
        "Ausführen", "Abbrechen", True, True)
    vs.CreateStyledStatic(dialog, 10, "MASSENERMITTLUNG  |  Kanal, Leitung, Erdmassen und Verbau", -1, 213)
    vs.CreateStaticText(
        dialog, 11,
        "Die Mengen werden unmittelbar aus den verwalteten Kanal- und Leitungsobjekten neu berechnet. "
        "Ein vorhandenes Vectorworks-Arbeitsblatt wird nach erfolgreichen Objektänderungen automatisch aktualisiert.", 82)
    vs.CreateStaticText(dialog, 12, "Ausgabe:", -1)
    vs.CreatePullDownMenu(dialog, 13, 58)
    vs.CreateStaticText(
        dialog, 14,
        ("Das laufende Arbeitsblatt ist bereits vorhanden." if has_worksheet else
         "Beim ersten Aufruf wird das laufende Arbeitsblatt angelegt."), 72)
    vs.CreateStaticText(dialog, 15, "%d Prüfhinweis(e) in der aktuellen Berechnung." % warning_count, 72)
    vs.SetFirstLayoutItem(dialog, 10)
    vs.SetBelowItem(dialog, 10, 11, 0, 6)
    vs.SetBelowItem(dialog, 11, 12, 0, 8)
    vs.SetRightItem(dialog, 12, 13, 8, 0)
    vs.SetBelowItem(dialog, 12, 14, 0, 6)
    vs.SetBelowItem(dialog, 14, 15, 0, 4)
    actions = (("Arbeitsblatt aktualisieren und öffnen", "worksheet"),
               ("Excel-Datei exportieren", "xlsx"),
               ("Arbeitsblatt aktualisieren und Excel exportieren", "both"))
    result = {"value": None}

    def handler(item, _data):
        if item == INIT:
            for index, row in enumerate(actions):
                vs.AddChoice(dialog, 13, row[0], index)
            vs.SelectChoice(dialog, 13, 0, True)
        elif item == 1:
            selected = int(vs.GetSelectedChoiceIndex(dialog, 13, 0))
            if selected < 0:
                raise RuntimeError("Bitte eine Ausgabe auswählen.")
            result["value"] = actions[selected][1]
        return item
    if not vs.VerifyLayout(dialog):
        raise RuntimeError("Der Mengendialog konnte nicht aufgebaut werden.")
    return result["value"] if vs.RunLayoutDialog(dialog, handler) == 1 else None
