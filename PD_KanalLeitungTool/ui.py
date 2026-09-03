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


def _fit_dialog(dialog, preferred_size=None):
    """Size and position the chooser inside the active monitor."""
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
            _fit_dialog(dialog, (500, 290))
        elif item == 1:
            selected["value"] = ("kanal" if vs.GetBooleanItem(dialog, KANAL) else
                                 "leitung" if vs.GetBooleanItem(dialog, LEITUNG) else
                                 "mengen")
        return item

    if not vs.VerifyLayout(dialog):
        raise RuntimeError("Der Auswahldialog konnte nicht aufgebaut werden.")
    _fit_dialog(dialog, (500, 290))
    return selected["value"] if vs.RunLayoutDialog(dialog, handler) == 1 else None
