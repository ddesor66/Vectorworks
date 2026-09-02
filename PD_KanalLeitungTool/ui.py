# -*- coding: utf-8 -*-
"""Small first-step chooser; detailed options stay in the selected module."""
from __future__ import absolute_import

import vs

from . import VERSION
from PD_KanalTool import VERSION as KANAL_VERSION
from PD_LeitungsTool import __version__ as LEITUNG_VERSION
from PD_KanalLeitungMengen import __version__ as MENGEN_VERSION


INIT = 12255
KANAL = 10
LEITUNG = 11
MENGEN = 12


def choose_module():
    dialog = vs.CreateResizableLayout(
        "Kanal- und Leitungstool | v%s | manufactured by Dirk D." % VERSION, True,
        "Weiter", "Abbrechen", True, True)
    vs.CreateStaticText(
        dialog, 4,
        "Was möchten Sie zeichnen oder bearbeiten?\n"
        "Das gewählte Fachmodul zeigt anschließend nur die dafür passenden Befehle.",
        64)
    vs.CreateRadioButton(dialog, KANAL, "Kanaltool | v%s" % KANAL_VERSION)
    vs.CreateRadioButton(dialog, LEITUNG, "Leitungstool | v%s" % LEITUNG_VERSION)
    vs.CreateRadioButton(dialog, MENGEN, "Massenermittlung | v%s" % MENGEN_VERSION)
    vs.CreateStaticText(
        dialog, 14,
        "Kanal: Haltungen, Schächte, Stutzen und Anschlüsse\n"
        "Leitung: Versorgungstrassen, Parallelleitungen, Bögen und Höhenketten\n"
        "Massenermittlung: laufendes Arbeitsblatt, Erdmassen, Verbau und Excel-Ausgabe\n"
        "Gelände und Baugruben besitzt ein eigenständiges Hauptmenü und Werkzeug.",
        64)
    vs.SetFirstLayoutItem(dialog, 4)
    vs.SetBelowItem(dialog, 4, KANAL, 0, 12)
    vs.SetRightItem(dialog, KANAL, LEITUNG, 12, 0)
    vs.SetBelowItem(dialog, KANAL, MENGEN, 0, 8)
    vs.SetBelowItem(dialog, MENGEN, 14, 0, 12)
    selected = {"value": None}

    def handler(item, _data):
        if item == INIT:
            vs.SetBooleanItem(dialog, KANAL, True)
            vs.SetFocusOnItem(dialog, KANAL)
            try:
                vs.SetLayoutDialogSize(dialog, 500, 290)
                width, height = vs.GetLayoutDialogSize(dialog)
                left, top, right, bottom = vs.GetScreen()
                palette_width = max(280, min(420, int((right-left)*0.22)))
                x = max(left+12, right-palette_width-int(width)-12)
                y = max(top+42, min(top+72, bottom-int(height)-24))
                vs.SetLayoutDialogPosition(dialog, x, y)
            except (AttributeError, TypeError, ValueError):
                pass
        elif item == 1:
            selected["value"] = ("kanal" if vs.GetBooleanItem(dialog, KANAL) else
                                 "leitung" if vs.GetBooleanItem(dialog, LEITUNG) else
                                 "mengen")
        return item

    if not vs.VerifyLayout(dialog):
        raise RuntimeError("Der Auswahldialog konnte nicht aufgebaut werden.")
    return selected["value"] if vs.RunLayoutDialog(dialog, handler) == 1 else None
