# -*- coding: utf-8 -*-
"""Interactive duplicate-object review."""

from __future__ import absolute_import

import vs

from . import vw_bridge


def run():
    groups = vw_bridge.duplicate_sets()
    if not groups:
        vw_bridge.alert(
            "Es wurden keine exakt übereinanderliegenden gleichen Texte, "
            "Symbole, Gruppen, Objekte oder Linien auf derselben Klasse "
            "gefunden. Eine Vorauswahl ist für diese Prüfung nicht nötig; "
            "geprüft wurde die gesamte Zeichnung.\n"
            "%d Objekt(e) waren nicht sicher vergleichbar und wurden ausgelassen."
            % vw_bridge.LAST_DUPLICATE_SKIPPED,
            "Überlagernde Linien")
        return
    deleted = 0
    index = 0
    while index < len(groups):
        group = groups[index]
        visible = tuple(record for record in group if record.get("handle"))
        if len(visible) < 2:
            index += 1
            continue
        vw_bridge.select_and_fit(visible)
        first = visible[0]
        layers = ", ".join(sorted(set(r["layer_name"] for r in visible), key=str.casefold))
        answer = vs.AlertQuestion(
            "Fund %d von %d: %d überlagernde Elemente" %
            (index + 1, len(groups), len(visible)),
            "Typ: %s\nKlasse: %s\nEbene(n): %s\n\nAlle Elemente dieses "
            "Fundes sind markiert und im Zeichenfenster fokussiert. Eine "
            "Vorauswahl war nicht erforderlich."
            % (first["type_label"], first["class_name"], layers),
            1, "Behalten / Weiter", "Prüfung beenden", "Doppelte löschen", "Zurück")
        if answer == 0:
            break
        if answer == 3:
            index = max(0, index - 1)
            continue
        if answer == 1:
            index += 1
            continue
        if answer == 2:
            confirm = vs.AlertQuestion(
                "%d doppelte Elemente löschen und genau ein Element behalten?" %
                (len(visible) - 1),
                "Die Löschung kann mit Vectorworks „Rückgängig“ zurückgenommen werden.",
                0, "Löschen", "Abbrechen", "", "")
            if confirm == 1:
                try:
                    vs.NameUndoEvent("Überlagernde Elemente löschen")
                except Exception:
                    pass
                deleted += vw_bridge.delete_duplicates(visible)
                index += 1
    vw_bridge.deselect_all_objects()
    vw_bridge.redraw()
    vw_bridge.alert(
        "Prüfung beendet: %d Objekte geprüft, %d Fundgruppen, %d gelöscht. "
        "%d Objekte nicht sicher vergleichbar. Je gelöschtem Fund blieb ein Original erhalten."
        % (vw_bridge.LAST_DUPLICATE_SCANNED, len(groups), deleted,
           vw_bridge.LAST_DUPLICATE_SKIPPED), "Überlagernde Linien")
