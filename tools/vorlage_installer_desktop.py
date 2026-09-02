# --------------------------------------------------------------- Ablauf ------
# Ab hier steht die Installationslogik. Sie wird beim Bauen unverändert an den
# erzeugten Kopf (PAYLOAD, PRUEFSUMME, VERSION, DATEINAME, LOADER) angehängt.
import argparse
import base64
import hashlib
import os
import sys

# Bekannte Ablageorte des Benutzer-Plug-ins-Ordners von Vectorworks.
JAHRE = ("2026", "2025", "2024", "2023")


class InstallationsFehler(Exception):
    """Abbruch mit einer für den Anwender verständlichen Meldung."""


def quelltext():
    """Eingebettete Skriptdatei entpacken und gegen die Prüfsumme halten."""
    try:
        daten = base64.b64decode(PAYLOAD.encode("ascii"))
    except Exception as fehler:
        raise InstallationsFehler("Der eingebettete Inhalt ist unlesbar.") from fehler
    gefunden = hashlib.sha256(daten).hexdigest()
    if gefunden != PRUEFSUMME:
        raise InstallationsFehler(
            "Der eingebettete Inhalt ist beschädigt.\nErwartet: %s\nGefunden: %s"
            % (PRUEFSUMME, gefunden))
    return daten


def kandidaten(startpunkt=None, plattform=None):
    """Mögliche Benutzer-Plug-ins-Ordner je Betriebssystem aufzählen."""
    plattform = plattform or sys.platform
    heim = startpunkt or os.path.expanduser("~")
    pfade = []
    if plattform.startswith("win"):
        if startpunkt:
            basis = os.path.join(heim, "AppData", "Roaming")
        else:
            basis = os.environ.get("APPDATA") or os.path.join(heim, "AppData", "Roaming")
        for jahr in JAHRE:
            pfade.append(os.path.join(basis, "Nemetschek", "Vectorworks", jahr, "Plug-ins"))
    elif plattform == "darwin":
        for jahr in JAHRE:
            pfade.append(os.path.join(heim, "Library", "Application Support",
                                      "Vectorworks", jahr, "Plug-ins"))
    else:
        for jahr in JAHRE:
            pfade.append(os.path.join(heim, "Vectorworks", jahr, "Plug-ins"))
    return tuple(pfade)


def gefundene_ordner(startpunkt=None, plattform=None):
    return tuple(pfad for pfad in kandidaten(startpunkt, plattform) if os.path.isdir(pfad))


def zielordner(vorgabe=None, startpunkt=None, plattform=None):
    """Zielordner bestimmen: Vorgabe hat Vorrang, sonst der neueste gefundene."""
    if vorgabe:
        pfad = os.path.abspath(os.path.expanduser(vorgabe))
        if not os.path.isdir(pfad):
            raise InstallationsFehler("Der angegebene Ordner existiert nicht:\n" + pfad)
        return pfad
    gefunden = gefundene_ordner(startpunkt, plattform)
    if not gefunden:
        raise InstallationsFehler(
            "Der Benutzer-Plug-ins-Ordner von Vectorworks wurde nicht gefunden.\n"
            "Gesucht wurde in:\n  " + "\n  ".join(kandidaten(startpunkt, plattform)) +
            "\n\nBitte den Ordner mit --ziel angeben. In Vectorworks steht er unter\n"
            "Extras > Programm-Einstellungen > Benutzerordner.")
    return gefunden[0]


def _aufraeumen(pfad):
    try:
        if os.path.exists(pfad):
            os.remove(pfad)
    except OSError:
        pass


def datei_schreiben(ordner, name, daten):
    """Datei erst vollständig schreiben, prüfen und dann an ihren Platz setzen."""
    ziel = os.path.join(ordner, name)
    zwischen = ziel + ".neu"
    try:
        with open(zwischen, "wb") as datei:
            datei.write(daten)
        with open(zwischen, "rb") as datei:
            geschrieben = datei.read()
        if hashlib.sha256(geschrieben).hexdigest() != hashlib.sha256(daten).hexdigest():
            raise InstallationsFehler("Die geschriebene Datei stimmt nicht überein: " + ziel)
        os.replace(zwischen, ziel)
    except InstallationsFehler:
        _aufraeumen(zwischen)
        raise
    except OSError as fehler:
        _aufraeumen(zwischen)
        raise InstallationsFehler(
            "Die Datei konnte nicht geschrieben werden:\n%s\n\n%s" % (ziel, fehler)) from fehler
    return ziel


def vorhandene_version(ordner):
    """Version einer bereits installierten Fassung lesen, sonst None."""
    ziel = os.path.join(ordner, DATEINAME)
    if not os.path.isfile(ziel):
        return None
    try:
        with open(ziel, "r", encoding="utf-8") as datei:
            for zeile in datei:
                if zeile.startswith("VERSION"):
                    return zeile.split("=", 1)[1].strip().strip('"\'')
    except OSError:
        return None
    return None


def installieren(ordner):
    """Skript und Loader-Text in den Plug-ins-Ordner schreiben."""
    vorher = vorhandene_version(ordner)
    ziel = datei_schreiben(ordner, DATEINAME, quelltext())
    loader = datei_schreiben(ordner, LOADER_DATEI, LOADER.encode("utf-8"))
    return {"ziel": ziel, "loader": loader, "vorher": vorher, "version": VERSION}


def bericht(ergebnis):
    zustand = ("Aktualisiert von Version %s auf %s." % (ergebnis["vorher"], ergebnis["version"])
               if ergebnis["vorher"] else "Neu installiert, Version %s." % ergebnis["version"])
    return "\n".join((
        "Gelände-Quelldaten: Installation abgeschlossen.",
        "",
        zustand,
        "Skript:      %s" % ergebnis["ziel"],
        "Loader-Text: %s" % ergebnis["loader"],
        "",
        "Einmalig noch in Vectorworks:",
        "  1. Extras > Plug-ins > Plug-in-Manager > Neu > Menübefehl,",
        "     Name: Gelände-Quelldaten, Sprache: Python.",
        "  2. Den Inhalt der Loader-Datei in den Skripteditor einfügen.",
        "  3. Arbeitsbereich-Editor: den Befehl in ein Menü ziehen.",
        "",
        "Alternativ ohne Plug-in: ein Python-Skript in der Skript-Palette",
        "mit dem Inhalt der Loader-Datei anlegen.",
        "",
        "Vectorworks nach der Installation einmal neu starten.",
    ))


def als_programm():
    """True, wenn dieses Setup als gebautes Programm (EXE) läuft."""
    return bool(getattr(sys, "frozen", False))


def warten():
    """Nach einem Doppelklick das Fenster offen halten, bis quittiert wurde."""
    if not als_programm():
        return
    try:
        input("\nZum Schließen die Eingabetaste drücken … ")
    except (EOFError, KeyboardInterrupt, OSError):
        pass


def main(argumente=None):
    zerleger = argparse.ArgumentParser(
        description="Installiert das Vectorworks-Skript Gelände-Quelldaten "
                    "in den Benutzer-Plug-ins-Ordner.")
    zerleger.add_argument("--ziel", default=None,
                          help="Benutzer-Plug-ins-Ordner von Vectorworks (sonst automatisch)")
    zerleger.add_argument("--zeigen", action="store_true",
                          help="nur die gefundenen Ordner anzeigen, nichts schreiben")
    werte = zerleger.parse_args(argumente)
    try:
        if werte.zeigen:
            gefunden = gefundene_ordner()
            print("Gefundene Vectorworks-Plug-ins-Ordner:")
            for pfad in gefunden or ():
                print("  " + pfad)
            if not gefunden:
                print("  (keiner)")
            warten()
            return 0
        ergebnis = installieren(zielordner(werte.ziel))
    except InstallationsFehler as fehler:
        print("Installation abgebrochen.\n\n%s" % fehler)
        warten()
        return 1
    print(bericht(ergebnis))
    warten()
    return 0


if __name__ == "__main__":
    sys.exit(main())
