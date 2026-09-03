# -*- coding: utf-8 -*-
"""Application workflow for live quantities and Excel output."""
from __future__ import absolute_import

import os

import vs

from PD_KanalTool import settings as canal_settings

from . import reporting, ui


def _save_path(default_name):
    value = vs.PutFile("Kanal- und Leitungsmengen als Excel speichern", default_name)
    if vs.DidCancel():
        return ""
    path = str(value or "").strip()
    if path and os.path.splitext(path)[1].lower() != ".xlsx":
        path += ".xlsx"
    return path


def run(action=None):
    try:
        report_mode = "all"
        preferences = canal_settings.load()
        report = reporting.collect_live(preferences)
        if action is None:
            selection = ui.action_dialog(
                bool(vs.GetObject(reporting.WORKSHEET_NAME) or
                     vs.GetObject(reporting.SUMMARY_WORKSHEET_NAME)),
                len(report["warnings"]), preferences)
            if selection is None:
                return
            changes = dict(preferences)
            changes.update({
                "earthwork_include_pavement": selection["include_pavement"],
                "earthwork_pavement_thickness_m":
                    selection["pavement_thickness_m"],
            })
            preferences = canal_settings.save(changes)
            report = reporting.collect_live(preferences)
            action = selection["action"]
            report_mode = selection["report_mode"]
        if action is None:
            return
        if action in ("worksheet", "both"):
            reporting.update_worksheet(
                report, show=True, report_mode=report_mode)
        path = ""
        if action in ("xlsx", "both"):
            path = _save_path(reporting.default_xlsx_name())
            if path:
                path = reporting.export_xlsx(
                    path, report, report_mode=report_mode)
        if action == "worksheet":
            vs.AlrtDialog(
                ("Einzelmassen-Arbeitsblatt mit Summenzeilen wurde vollständig aktualisiert."
                 if report_mode == "details" else
                 "Summen-Arbeitsblatt wurde vollständig aktualisiert."))
        elif path:
            prefix = ("Gewähltes Mengen-Arbeitsblatt und Excel-Ausgabe wurden aktualisiert:\n"
                      if action == "both" else "Excel-Ausgabe wurde erstellt:\n")
            vs.AlrtDialog(prefix + path)
    except Exception as error:
        vs.AlrtDialog("Kanal- und Leitungsmengen: " + str(error))
