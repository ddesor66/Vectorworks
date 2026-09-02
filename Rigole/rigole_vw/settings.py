# -*- coding: utf-8 -*-
"""
Persistenz der zuletzt verwendeten Einstellungen (Anforderung Punkt 28).

Grundlage: vs.SetSavedSetting / vs.GetSavedSetting.
Pruefbericht A hat bestaetigt, dass auch ein 561 Zeichen langer JSON-Text
samt Umlauten verlustfrei zurueckkommt - deshalb wird alles in EINEN
Schluessel geschrieben statt in zwei Dutzend Einzelschluessel.

Die Einstellungen liegen dokumentunabhaengig in der Datei
SavedSettingsUser.xml des Benutzerordners und ueberleben damit den
Wechsel der Zeichnung und den Neustart von Vectorworks.

BEWUSST NICHT gespeichert: Rigolen_ID, Einfuegepunkt, Beschriftungsposition
und Kommentar - das sind objektspezifische Werte, die nicht als Vorgabe
fuer die naechste Rigole taugen.

Kompatibilitaet: Python 3.9.2 (Vectorworks 2026)
"""

import json

import vs

from rigole_config.constants import (
    SETTINGS_CATEGORY, PERSISTED_KEYS, PERSISTED_KEYS_POLY,
)

SETTINGS_KEY = "letzte_einstellungen_v1"

# Seit der Aufteilung in zwei Werkzeuge (24.08.2026) hat jedes seinen
# eigenen Schluessel. Sonst wuerde die Kiesrigole beim Speichern die Werte
# der Koerbe-Rigole verdraengen - beide teilen sich Namen wie
# 'storage_percent', meinen damit aber voellig verschiedene Groessen
# (0,30 gegenueber 0,95).
SETTINGS_KEY_KIES = "letzte_einstellungen_kies_v1"
SETTINGS_KEY_POLY = "letzte_einstellungen_komplex_v1"

# Werte, die niemals gespeichert werden - auch dann nicht, wenn sie
# versehentlich in PERSISTED_KEYS auftauchen.
NIEMALS_SPEICHERN = ("rigole_id", "comment", "insert_point", "label_point")


def load_settings(defaults, schluessel=None):
    """
    Liefert eine Kopie von 'defaults', ueberschrieben mit den zuletzt
    gespeicherten Werten. Fehlt oder bricht die Datei, kommen einfach die
    Standardwerte zurueck - ohne Fehlermeldung, so wie es die Referenz
    zu GetSavedSetting empfiehlt.
    """
    werte = dict(defaults)
    try:
        ok, text = vs.GetSavedSetting(SETTINGS_CATEGORY,
                                     schluessel or SETTINGS_KEY)
    except Exception:
        return werte
    if not ok or not text:
        return werte
    try:
        gespeichert = json.loads(text)
    except Exception:
        return werte
    if not isinstance(gespeichert, dict):
        return werte

    for name, wert in gespeichert.items():
        if name in NIEMALS_SPEICHERN:
            continue
        if name in werte:
            werte[name] = wert
    return werte


def save_settings(werte, schluessel=None, felder=None):
    """
    Speichert die aufgefuehrten Werte unter 'schluessel'.

    felder   Liste der zu speichernden Schluessel. Ohne Angabe gilt
             PERSISTED_KEYS (Rigole und Kiesrigole); das Werkzeug
             "Rigole komplex" uebergibt PERSISTED_KEYS_POLY.

    ACHTUNG, hier steckte bis zum 26.08.2026 ein Fehler: Die Schleifen-
    variable hiess wie der Parameter 'schluessel' und ueberschrieb ihn.
    Gespeichert wurde deshalb unter dem NAMEN DES LETZTEN FELDES statt
    unter dem gewuenschten Schluessel - die Vorbelegung beim naechsten
    Aufruf kam also nie an. Deshalb heisst die Schleifenvariable jetzt
    'name'.
    """
    liste = felder if felder is not None else PERSISTED_KEYS
    zu_speichern = {}
    for name in liste:
        if name in NIEMALS_SPEICHERN:
            continue
        if name in werte:
            zu_speichern[name] = werte[name]
    try:
        text = json.dumps(zu_speichern, ensure_ascii=False)
    except Exception:
        return False
    try:
        vs.SetSavedSetting(SETTINGS_CATEGORY,
                           schluessel or SETTINGS_KEY, text)
        return True
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Kurzzeitgedaechtnis innerhalb der laufenden Vectorworks-Sitzung
# ---------------------------------------------------------------------------
# Pruefbericht C2 (Punkt D3) hat gezeigt, dass Python-Zustand zwischen zwei
# Werkzeuglaeufen erhalten bleibt: der Zaehler im Arbeitsspeicher lief ueber
# acht Klicks hinweg durch. Damit koennen wir Einstellungen zwischen zwei
# Klicks halten, ohne jedes Mal die XML-Datei zu lesen.
#
# Das Modul selbst dient als Speicher - es bleibt in sys.modules geladen.

_SITZUNG = {}


def session_get(schluessel, standard=None):
    return _SITZUNG.get(schluessel, standard)


def session_set(schluessel, wert):
    _SITZUNG[schluessel] = wert


def session_clear():
    _SITZUNG.clear()
