# -*- coding: utf-8 -*-
"""
PHASE 8 - Beschriftung.

Erzeugt ein normales Vectorworks-Textobjekt. Es liegt bewusst AUSSERHALB
der Rigolengruppe, damit es sich mit einem einzigen Klick verschieben laesst
(so entschieden am 21.08.2026). Es bekommt KEINEN Datensatz und taucht
deshalb in Datenbankunterlagen nicht als zweite Zeile auf.

Textgroesse, Abstand und Ausrichtung stehen als Konstanten in
rigole_config/constants.py und lassen sich dort zentral aendern.

Pruefbericht A (U7): Sowohl vs.Chr(13) als auch "\\n" brechen die Zeile um -
beide Testtexte waren exakt gleich hoch, und ihre Breite entsprach jeweils
nur der ersten Zeile. Verwendet wird vs.Chr(13), weil das die in Vectorworks
dokumentierte Variante ist.

Die Referenz zu CreateText warnt ausdruecklich: ohne vorher gesetzte
Textgroesse erscheint der Fehler "An incorrect object is described".
Deshalb immer PushAttrs / TextSize / ... / PopAttrs.

Kompatibilitaet: Python 3.9.2 (Vectorworks 2026)
"""

import vs

from rigole_config.constants import (
    CLASS_LABEL, CLASS_KIES_LABEL, TEXT_SIZE, TEXT_OFFSET_X, TEXT_OFFSET_Y,
    TEXT_JUST_LEFT, TEXT_VERT_TOP, TEXT_STYLE_NAME,
)
from rigole_core.calculations import default_label_position
from rigole_core.formatting import (
    build_label_text, build_kies_label_data, kies_label_fields,
    rigole_label_fields, polygon_label_fields,
)
from rigole_vw import vwutils


def label_data(werte, ergebnis, rigole_id):
    """Stellt die Werte zusammen, aus denen der Beschriftungstext entsteht."""
    from rigole_core.formatting import fmt_height

    daten = dict(ergebnis.as_dict())
    if getattr(ergebnis, "hat_schacht", False):
        schacht = u"%d x %s, OK %s / UK %s" % (
            ergebnis.schacht_anzahl, ergebnis.schacht_dn,
            fmt_height(ergebnis.schacht_ok),
            fmt_height(ergebnis.schacht_uk))
    else:
        schacht = u""
    daten.update({
        "rigole_id": rigole_id,
        "rigole_type": werte.get("rigole_type", ""),
        "system_name": werte.get("system_name", ""),
        "welded": bool(werte.get("welded", False)),
        "load_class": werte.get("load_class", ""),
        "schacht": schacht,
    })
    return daten


def build_text(werte, ergebnis, rigole_id):
    """Fertiger Beschriftungstext mit Vectorworks-Zeilenumbruch."""
    try:
        umbruch = vs.Chr(13)
    except Exception:
        umbruch = "\n"
    return build_label_text(label_data(werte, ergebnis, rigole_id),
                            rigole_label_fields(werte.get("label_fields")),
                            newline=umbruch)


def build_kies_text(werte, ergebnis, kies_id):
    """
    Beschriftungstext der KIESRIGOLE.

    Benutzt denselben Textaufbau wie die Koerbe-Rigole; nur die Datenquelle
    und die Auswahl der Zeilen unterscheiden sich (kein Korbraster, dafuer
    Material und Draenrohr).
    """
    try:
        umbruch = vs.Chr(13)
    except Exception:
        umbruch = "\n"
    daten = build_kies_label_data(
        ergebnis, kies_id,
        werte.get("rigole_type", ""),
        werte.get("system_name", ""),
        load_class=werte.get("load_class", ""))
    return build_label_text(daten,
                            kies_label_fields(werte.get("label_fields")),
                            newline=umbruch)


def polygon_label_data(werte, ergebnis, rigole_id):
    """
    Beschriftungswerte fuer "Rigole komplex".

    Die Zeile "Anordnung" bekommt hier einen fertigen Text mit: Anzahl in
    Laengs- mal Querrichtung waere irrefuehrend, weil das Raster nicht
    vollstaendig gefuellt ist.
    """
    daten = label_data(werte, ergebnis, rigole_id)
    daten["anordnung_text"] = u"%d Koerbe je Lage x %d Lagen = %d" % (
        ergebnis.koerbe_je_lage, ergebnis.count_height,
        ergebnis.basket_count)
    daten["polygon_flaeche"] = ergebnis.polygon_flaeche
    daten["belegte_flaeche"] = ergebnis.belegte_flaeche
    daten["ausnutzung"] = ergebnis.ausnutzung
    return daten


def build_polygon_text(werte, ergebnis, rigole_id):
    """Beschriftungstext der komplexen Rigole."""
    try:
        umbruch = vs.Chr(13)
    except Exception:
        umbruch = "\n"
    return build_label_text(
        polygon_label_data(werte, ergebnis, rigole_id),
        polygon_label_fields(werte.get("label_fields")),
        newline=umbruch)


def polygon_label_position_doc(instanz_punkt_doc, ergebnis, unit_ctx,
                               offset_x=None, offset_y=None):
    """
    Beschriftungsposition der komplexen Rigole.

    Sie sitzt rechts oberhalb der HUELLBOX der belegten Koerbe. Weil die
    Huellbox im gedrehten Rastersystem liegt, wird die Ecke dort bestimmt
    und anschliessend mit dem Rasterwinkel in das Zeichnungssystem
    zurueckgedreht - sonst laege der Text bei schraeg liegenden Rigolen
    quer im Bild.
    """
    from rigole_core import polygon as poly

    if offset_x is None:
        offset_x = TEXT_OFFSET_X
    if offset_y is None:
        offset_y = TEXT_OFFSET_Y

    x_m = float(ergebnis.total_length) + float(offset_x)
    y_m = float(ergebnis.total_width) + float(offset_y)
    dx, dy = poly.drehe_punkt((x_m, y_m), float(ergebnis.raster_winkel))
    return (float(instanz_punkt_doc[0]) + unit_ctx.to_doc(dx),
            float(instanz_punkt_doc[1]) + unit_ctx.to_doc(dy))


def default_position_doc(origin_doc, ergebnis, unit_ctx,
                         offset_x=None, offset_y=None, angle_deg=0.0):
    """
    Position der Beschriftung: rechts oberhalb der Rigole, in
    Dokumenteinheiten. Der Versatz kommt aus dem Dialog; fehlt er, gelten
    die Konstanten aus constants.py.
    """
    if offset_x is None:
        offset_x = TEXT_OFFSET_X
    if offset_y is None:
        offset_y = TEXT_OFFSET_Y
    x_m, y_m = default_label_position(
        0.0, 0.0, ergebnis.total_length, ergebnis.total_width,
        offset_x, offset_y)
    return vwutils.PlanFrame(angle_deg).offset(
        origin_doc, unit_ctx.to_doc(x_m), unit_ctx.to_doc(y_m))


def create_label(position_doc, text, rollback, klasse=None, name=None, angle_deg=0.0):
    """
    Erzeugt das Textobjekt an der uebergebenen Stelle.

    klasse  Beschriftungsklasse; ohne Angabe die der Koerbe-Rigole.
            Die Kiesrigole uebergibt hier CLASS_KIES_LABEL.
    name    Objektname. Nur darueber findet der Modus "Vorhandenes
            bearbeiten" die alte Beschriftung spaeter wieder.

    Rueckgabe: Handle oder None.
    """
    if not text:
        return None

    if not klasse:
        klasse = CLASS_LABEL

    vorherige_klasse = _klasse_setzen(klasse)
    h = None
    attrs_gesetzt = False
    try:
        vs.PushAttrs()
        attrs_gesetzt = True
        vs.TextSize(float(TEXT_SIZE))
        vs.TextFont(vs.GetFontID("Arial"))
        vs.TextJust(int(TEXT_JUST_LEFT))
        vs.TextVerticalAlign(int(TEXT_VERT_TOP))
        # Absolute model angle; do not inherit the last text tool's rotation.
        vs.TextRotate(float(angle_deg))
        vs.TextOrigin((float(position_doc[0]), float(position_doc[1])))
        vs.CreateText(text)
        h = rollback.merke_letztes()
    finally:
        if attrs_gesetzt:
            try:
                vs.PopAttrs()
            except Exception:
                pass
        _klasse_setzen(vorherige_klasse)

    # Klasse ausdruecklich zuweisen - nicht auf die aktive Klasse verlassen.
    if vwutils.handle_ok(h):
        vs.SetTextStyleRef(h, 0)
        vs.SetTextFont(h, 0, len(text), vs.GetFontID("Arial"))
        vs.SetTextSize(h, 0, len(text), float(TEXT_SIZE))
        try:
            vs.SetClass(h, klasse)
        except Exception:
            pass

    # Benennen - schlaegt es fehl (Name schon vergeben), ist das kein
    # Beinbruch: dann laesst sich die Beschriftung beim Bearbeiten nur nicht
    # automatisch ersetzen. Genau das meldet der Bearbeiten-Modus dann auch.
    if vwutils.handle_ok(h) and name:
        try:
            vs.SetName(h, name)
        except Exception:
            pass

    if vwutils.handle_ok(h) and TEXT_STYLE_NAME:
        # Optionaler Textstil. Bewusst ohne Fehlermeldung, wenn der Stil
        # im Dokument fehlt - die Beschriftung ist dann eben im
        # Dokumentstandard formatiert.
        try:
            vs.SetTextStyleRef(h, vs.Name2Index(TEXT_STYLE_NAME))
        except Exception:
            pass

    return h if vwutils.handle_ok(h) else None


def _klasse_setzen(name):
    vorher = ""
    try:
        vorher = vs.ActiveClass()
    except Exception:
        pass
    if name:
        try:
            vs.NameClass(name)
        except Exception:
            pass
    return vorher
