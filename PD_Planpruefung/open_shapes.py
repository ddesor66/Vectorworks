"""Sequential review with explicit single and batch confirmation."""
import vs

from . import open_shapes_vw as bridge


def run():
    candidates, skipped = bridge.scan()
    details = ("%d gesperrte und %d zu kurze offene Formen ausgelassen. "
               "%d Symbol-/Plugin-Container nicht verändert."
               % (skipped["locked"], skipped["too_few_vertices"],
                  skipped["containers_not_entered"]))
    if not candidates:
        vs.AlrtDialog("Keine bearbeitbaren offenen Polygone/Polylinien mit "
                      "Solid- oder Schraffurfüllung gefunden.\n\n" + details)
        return
    view = bridge.ReviewView()
    closed = 0
    try:
        remaining = list(candidates)
        index = 0
        while index < len(remaining):
            candidate = remaining[index]
            view.focus(candidate)
            action = vs.AlertQuestion(
                "Nicht geschlossene Fläche %d von %d" % (index + 1, len(remaining)),
                "Klasse: %s\nEbene: %s%s\n\n"
                "Das Element ist markiert. Schließen verbindet Ende und Anfang. "
                "Die gewünschte Kontur bitte vorher prüfen; eine geschlossene "
                "Form ist nicht automatisch frei von Selbstüberschneidungen."
                % (candidate.class_name, candidate.layer_name,
                   "\nInnerhalb einer Gruppe; die Gruppe ist zusätzlich markiert."
                   if candidate.ancestors else ""),
                0, "Schließen / Weiter", "Beenden", "Überspringen", "Alle schließen …")
            if action == 0:
                break
            if action == 1:
                closed += bridge.close_candidates((candidate,))
                index += 1
            elif action == 2:
                index += 1
            elif action == 3:
                # Include previously skipped candidates: the button means ALL
                # still-open eligible filled objects, not just following rows.
                pending, _ignored = bridge.scan()
                confirm = vs.AlertQuestion(
                    "Alle %d noch offenen gefüllten Flächen schließen?" % len(pending),
                    "Dies schließt auch zuvor übersprungene Funde auf allen "
                    "Konstruktionsebenen. Gesperrte Objekte, Symboldefinitionen "
                    "und Plugin-Inhalte bleiben unverändert. Mit Rückgängig "
                    "kann diese Sammeländerung zurückgenommen werden.",
                    0, "Alle schließen", "Abbrechen", "", "")
                if confirm == 1:
                    closed += bridge.close_candidates(pending)
                    break
            else:
                break
    finally:
        view.restore()
    vs.AlrtDialog("Flächenprüfung beendet: %d geschlossen.\n\n%s\n\n"
                  "Vorhandene Massenermittlungen anschließend aktualisieren."
                  % (closed, details))


def guarded_run():
    try:
        run()
    except Exception as error:
        vs.AlrtDialog("Flächenprüfung abgebrochen:\n" + str(error))
        raise
