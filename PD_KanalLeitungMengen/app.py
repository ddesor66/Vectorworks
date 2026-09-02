# -*- coding: utf-8 -*-
"""Application workflow for live quantities and Excel output."""
from __future__ import absolute_import

import vs

from . import reporting, ui


def _save_path(default_name):
    value = vs.PutFile("Kanal- und Leitungsmengen als Excel speichern", default_name)
    if vs.DidCancel():
        return ""
    return str(value or "").strip()


def run(action=None):
    try:
        report = reporting.collect_live()
        if action is None:
            action = ui.action_dialog(
                bool(vs.GetObject(reporting.WORKSHEET_NAME)), len(report["warnings"]))
        if action is None:
            return
        if action in ("worksheet", "both"):
            reporting.update_worksheet(report, show=True)
        path = ""
        if action in ("xlsx", "both"):
            path = _save_path(reporting.default_xlsx_name())
            if path:
                reporting.export_xlsx(path, report)
        if action == "worksheet":
            vs.AlrtDialog("Das laufende Mengen-Arbeitsblatt wurde vollständig aktualisiert.")
        elif path:
            vs.AlrtDialog("Mengen-Arbeitsblatt und Excel-Ausgabe wurden aktualisiert:\n" + path)
    except Exception as error:
        vs.AlrtDialog("Kanal- und Leitungsmengen: " + str(error))

