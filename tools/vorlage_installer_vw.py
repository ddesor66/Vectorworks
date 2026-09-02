# --------------------------------------------------------------- Ablauf ------
# Ab hier steht die Installationslogik. Sie wird beim Bauen unverändert an den
# erzeugten Kopf (PAYLOAD, PRUEFSUMME, VERSION, DATEINAME, LOADER) angehängt.
import base64
import hashlib
import os


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


def zielordner(api):
    """Benutzer-Plug-ins-Ordner von Vectorworks ermitteln (GetFolderPath -2)."""
    try:
        pfad = str(api.GetFolderPath(-2) or "").strip()
    except (AttributeError, TypeError) as fehler:
        raise InstallationsFehler(
            "Der Benutzer-Plug-ins-Ordner konnte nicht abgefragt werden.") from fehler
    if not pfad or not os.path.isdir(pfad):
        raise InstallationsFehler(
            "Der Benutzer-Plug-ins-Ordner wurde nicht gefunden:\n%s" % (pfad or "(leer)"))
    return pfad


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


def _aufraeumen(pfad):
    try:
        if os.path.exists(pfad):
            os.remove(pfad)
    except OSError:
        pass


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
        "Skript: %s" % ergebnis["ziel"],
        "Loader-Text: %s" % ergebnis["loader"],
        "",
        "Einmalig noch der Menübefehl:",
        "1. Extras > Plug-ins > Plug-in-Manager > Neu > Menübefehl,",
        "   Name: Gelände-Quelldaten, Sprache: Python.",
        "2. Den Inhalt der oben genannten Loader-Datei in den Skripteditor einfügen.",
        "3. Arbeitsbereich-Editor: den Befehl in ein Menü ziehen.",
        "",
        "Danach genügt für jedes Update ein erneuter Lauf dieses Installers;",
        "der Menübefehl bleibt unverändert.",
        "",
        "Ohne Menübefehl: ein Python-Skript in der Skript-Palette mit dem",
        "Inhalt der Loader-Datei anlegen – das funktioniert genauso.",
    ))


def melden(api, text):
    try:
        api.AlertInform(str(text), "", False)
    except (AttributeError, TypeError):
        api.AlrtDialog(str(text))


def ausfuehren(api):
    """Gesamtablauf des Installers innerhalb von Vectorworks."""
    try:
        ergebnis = installieren(zielordner(api))
    except InstallationsFehler as fehler:
        melden(api, "Installation abgebrochen.\n\n%s" % fehler)
        return None
    melden(api, bericht(ergebnis))
    return ergebnis


def _autostart():
    if os.environ.get("PD_GELAENDE_INSTALLER_KEIN_AUTOSTART"):
        return
    try:
        import vs
    except ImportError:
        return
    ausfuehren(vs)


_autostart()
